"""Offline one-use submission checks for the separate R184 tilt candidate."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_qc_projection as projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_qc_runtime as tilt_runtime
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap90
from research.analyst_revisions_v2_qc import six_universe_tilt_submission as subject
from research.quantconnect import QuantConnectClient, QuantConnectCredentials


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def projection():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return projector.build_accepted_risk_six_universe_order_tilt_qc_projection(
        package
    )


def _plan(tmp_path, projection):
    return subject.TiltQcPlan(
        organization_id="a" * 32,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


def _predecessors(monkeypatch, plan, *, valid=True, target_path="f" * 64):
    observed = []
    monkeypatch.setattr(
        cap90, "_require_prior_valid_role",
        lambda prior: observed.append((prior.candidate_id, prior.attempt)),
    )
    root = plan.control_directory
    root.mkdir(mode=0o700)
    waiver = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": cap90._EXPLORATORY_WAIVER_SCHEMA,
        "owner_launch_waiver_id": cap90._EXPLORATORY_WAIVER_ID,
        "owner_waived_payload_sha256": "d" * 64,
    }
    receipts = {
        "claim": {
            "candidate_id": "R182", "role": "matched",
            "projection_sha256": cap90._R182_BRIDGE_PROJECTION_SHA256,
            "profile_sha256": cap90._R182_BRIDGE_PROFILE_SHA256,
            "source_files": [["main.py", "0" * 64, 1]] * 14,
            **waiver,
        },
        "launch": {
            "candidate_id": "R182", "role": "matched",
            "project_name": subject._PREDECESSOR_PROJECT_NAME,
            "backtest_name": (
                "ARV2 R182A1 six cap90 bridge matched 2021 2025 "
                + cap90._R182_BRIDGE_PROJECTION_SHA256[:8]
            ),
            "projection_sha256": cap90._R182_BRIDGE_PROJECTION_SHA256,
            "profile_sha256": cap90._R182_BRIDGE_PROFILE_SHA256,
            "project_id": 900, "backtest_id": "matched-a1", **waiver,
        },
        "terminal": {
            "candidate_id": "R182", "status": "Completed.",
            "project_id": 900, "backtest_id": "matched-a1",
        },
        "result-read-claim": {
            "candidate_id": "R182", "project_id": 900,
            "backtest_id": "matched-a1",
        },
        "result-valid": {
            "candidate_id": "R182", "attempt": 1, "run_valid": valid,
            "aggregate_sha256": "e" * 64,
            **({"target_path_sha256": target_path} if target_path is not None else {}),
            "projection_sha256": cap90._R182_BRIDGE_PROJECTION_SHA256,
            "profile_sha256": cap90._R182_BRIDGE_PROFILE_SHA256,
            "project_id": 900, "backtest_id": "matched-a1",
        },
    }
    for name, content in receipts.items():
        cap90._write_once(root / ("R182-A1-" + name + ".json"), content)
    return observed


def _fake_qc(monkeypatch, plan, projection, *, source_corrupt=False,
             compile_error=False):
    files = {
        "main.py": "# default\n", "research.ipynb": "{}",
    }
    calls = []
    launched = False

    def post(_api, endpoint, payload):
        nonlocal launched
        calls.append(endpoint)
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            if not payload:
                return {"success": True, "projects": []}
            return {"success": True, "projects": [{
                "projectId": 111, "name": plan.project_name,
                "organizationId": plan.organization_id, "language": "Py",
                "owner": True, "codeRunning": False,
                "collaborators": [{"owner": True}],
            }]}
        if endpoint == "projects/create":
            return {"success": True, "projects": [{"projectId": 111}]}
        if endpoint == "files/read":
            content = dict(files)
            if source_corrupt and len(content) == 16:
                content["main.py"] += "# cloud edit"
            return {"success": True, "files": [{
                "projectId": 111, "name": name, "content": value,
            } for name, value in content.items()]}
        if endpoint == "files/delete":
            del files[payload["name"]]
            return {"success": True}
        if endpoint in {"files/update", "files/create"}:
            files[payload["name"]] = payload["content"]
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-a1"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "compile-a1",
                    "state": "BuildError" if compile_error else "BuildSuccess"}
        if endpoint == "backtests/create":
            launched = True
            return {"success": True, "backtest": {
                "projectId": 111, "backtestId": "tilt-a1",
                "name": plan.backtest_name, "status": "In Queue...",
            }}
        if endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            return {"success": True, "count": 1 if launched else 0,
                    "backtests": ([{
                        "projectId": 111, "backtestId": "tilt-a1",
                        "name": plan.backtest_name, "status": "Completed.",
                        "statistics": {"ignored": "not read"},
                    }] if launched else [])}
        raise AssertionError(endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls


def test_preview_binds_exact_16_file_projection_and_waiver_payload(projection, tmp_path):
    plan = _plan(tmp_path, projection)
    identity = subject.preview(plan, projection)
    assert identity["projection_sha256"] == subject._PROJECTION_SHA256
    assert len(identity["source_files"]) == 16
    payload = json.loads(subject._waived_launch_payload(
        plan, identity, matched_baseline_target_path_sha256="f" * 64,
    ))
    assert payload["maximum_backtest_submissions"] == 1
    assert payload["matched_baseline_target_path_sha256"] == "f" * 64
    assert payload["mutating_endpoint_budget"]["backtests/create"] == 1
    assert payload["paper_live_deployment_funded_trading_authorized"] is False
    for changed in (
        dataclasses.replace(plan, project_name="106 ARV2 SIX CAP90 ETF R183 2021 2025"),
        dataclasses.replace(plan, attempt=2),
        dataclasses.replace(plan, profile_sha256="0" * 64),
    ):
        with pytest.raises(subject.SixUniverseTiltSubmissionError):
            subject.preview(changed, projection)
    with pytest.raises(subject.SixUniverseTiltSubmissionError):
        subject.preview(
            plan, dataclasses.replace(projection, projection_sha256="0" * 64)
        )


def test_predecessor_absence_and_invalid_result_refuse_before_qc(
    monkeypatch, projection, tmp_path,
):
    plan = _plan(tmp_path, projection)
    calls = _fake_qc(monkeypatch, plan, projection)
    with pytest.raises(subject.SixUniverseTiltSubmissionError):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []
    _predecessors(monkeypatch, plan, valid=False)
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="R182 A1"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_predecessor_valid_receipt_without_target_path_refuses_before_qc(
    monkeypatch, projection, tmp_path,
):
    plan = _plan(tmp_path, projection)
    calls = _fake_qc(monkeypatch, plan, projection)
    _predecessors(monkeypatch, plan, target_path=None)
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="R182 A1"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []


def test_r181_gate_and_exact_waiver_precede_first_qc_call(
    monkeypatch, projection, tmp_path,
):
    plan = _plan(tmp_path, projection)
    calls = _fake_qc(monkeypatch, plan, projection)
    observed = _predecessors(monkeypatch, plan)
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="waiver"):
        subject.launch_a1(plan, projection, object(), owner_waiver_id="wrong")
    assert calls == []
    assert observed == []
    monkeypatch.setattr(cap90, "_require_prior_valid_role", lambda _plan:
                        (_ for _ in ()).throw(cap90.Cap90QcSubmissionError("invalid A3")))
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="R181 A3"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []


def test_tilt_a1_launches_once_in_private_project_and_polls_only_status(
    monkeypatch, projection, tmp_path,
):
    plan = _plan(tmp_path, projection)
    observed = _predecessors(monkeypatch, plan)
    calls = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    assert observed == [("R182", 1)]
    assert launch["project_name"] == subject._PROJECT_NAME
    assert launch["owner_launch_waiver_id"] == subject._WAIVER_ID
    assert calls.count("backtests/create") == 1
    assert calls.count("compile/create") == 1
    assert subject.poll_status(plan, launch, object()) == "Completed."
    assert calls[-1] == "backtests/list"
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="already claimed"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls.count("backtests/create") == 1


@pytest.mark.parametrize("defect", ("cloud_source", "compile_error"))
def test_upload_mismatch_or_compile_error_spends_a1_without_backtest(
    monkeypatch, projection, tmp_path, defect,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls = _fake_qc(
        monkeypatch, plan, projection,
        source_corrupt=defect == "cloud_source",
        compile_error=defect == "compile_error",
    )
    with pytest.raises(subject.SixUniverseTiltSubmissionError):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert subject._control_path(plan, "claim").exists()
    assert "backtests/create" not in calls


def test_default_qc_transport_is_not_the_bounded_client():
    client = QuantConnectClient(
        QuantConnectCredentials("offline", "offline-token")
    )
    with pytest.raises(subject.SixUniverseTiltSubmissionError):
        subject._client(client)


def _completed(plan, projection):
    identity = subject.preview(plan, projection)
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": subject._WAIVER_SCHEMA,
        "owner_launch_waiver_id": subject._WAIVER_ID,
        "owner_waived_payload_sha256": hashlib.sha256(
            subject._waived_launch_payload(
                plan, identity,
                matched_baseline_target_path_sha256="f" * 64,
            )
        ).hexdigest(),
    }
    subject._write(subject._control_path(plan, "claim"), {
        **identity, **authority,
        "matched_baseline_target_path_sha256": "f" * 64,
    })
    launch = {
        **{key: value for key, value in identity.items() if key != "source_files"},
        **authority, "project_id": 111, "project_name": plan.project_name,
        "matched_baseline_target_path_sha256": "f" * 64,
        "compile_id": "compile-a1", "backtest_id": "tilt-a1",
        "backtest_name": plan.backtest_name,
    }
    subject._write(subject._control_path(plan, "launch"), launch)
    subject._write(subject._control_path(plan, "terminal"), {
        "candidate_id": "R184", "status": "Completed.",
        "project_id": 111, "backtest_id": "tilt-a1",
    })
    return launch


def _statistics(plan, launch, *, valid=True, tamper=None):
    account = {
        "observation_count": runtime.EXPECTED_SESSION_COUNT,
        "first_observation_session": runtime.EVALUATION_START_SESSION,
        "last_observation_session": runtime.EVALUATION_END_SESSION,
        "starting_equity": "1000000", "ending_equity": "1100000",
        "cumulative_return": "0.1", "maximum_drawdown": "-0.1",
        "annualized_volatility": "0.2", "zero_rate_sharpe": "0.5",
    }
    execution = {
        "schema": "arv2-simulated-moo-executor-summary-v1",
        "decision_count": runtime.EXPECTED_DECISION_COUNT,
        "submitted_rebalance_count": 0, "completed_rebalance_count": 0,
        "submitted_order_count": 0, "filled_order_count_sum": 0,
        "canceled_order_count_sum": 0, "invalid_order_count_sum": 0,
        "modeled_fee_amount": "0", "actual_engine_fee_amount": "0",
        "total_filled_notional": "0", "mean_target_weight_l1_error": "0.01",
        "maximum_target_weight_l1_error": "0.03",
        "run_valid": valid, "execution_failure": not valid,
        "raw_order_rows_in_summary": False,
        "raw_security_rows_in_summary": False,
        "backtest_only": True, "live_orders": False,
        "paper_orders": False, "funded_orders": False,
        "deployment": False, "trading": False,
    }
    rows = [[
        ticker, ticker, runtime.EXPECTED_DECISION_COUNT,
        0, runtime.EXPECTED_DECISION_COUNT, 0, 0, 0,
        "0", "0", {}, {"SIX_ETF_BASKET": runtime.EXPECTED_DECISION_COUNT},
    ] for ticker in cap90._UNIVERSES]
    aggregate = {key: None for key in cap90._BRIDGE_AGGREGATE_FIELDS | subject._TILT_FIELDS}
    aggregate.update({
        "schema": tilt_runtime.TILT_SUMMARY_SCHEMA,
        "role": plan.role, "profile_id": launch["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "account": account,
        "mean_gross_exposure": "0.98", "maximum_gross_exposure": "0.98",
        "fallback_counts": {"SIX_ETF_BASKET": 6 * runtime.EXPECTED_DECISION_COUNT},
        "sleeve_diagnostics": {
            "schema": "arv2-six-universe-order-sleeve-summary-table-v1",
            "fields": list(cap90._SLEEVE_FIELDS), "rows": rows,
        },
        "execution": execution,
        "engine_forced_delisting": {
            "schema": runtime._forced.FORCED_DELISTING_SUMMARY_SCHEMA,
            "accounting_complete": True,
            "raw_order_rows_in_summary": False,
            "raw_security_rows_in_summary": False,
            "order_count": 0, "event_count": 0,
        },
        "reference_history_call_count": runtime.EXPECTED_DECISION_COUNT,
        "pit_callback_source_row_count": 0,
        "fundamental_snapshot_unavailable_decision_count": 0,
        "constituent_collection_unavailable_decision_count": 0,
        "constituent_collection_unavailable_universe_counts": {
            ticker: 0 for ticker in cap90._UNIVERSES
        },
        "preliminary": True, "formal": False, "backtest_only": True,
        "live_orders": False, "paper_orders": False,
        "funded_orders": False, "deployment": False, "trading": False,
        "run_valid": valid,
        "admission_leverage": "2", "target_gross_exposure": "0.98",
        "minimum_end_day_cash": "1000", "daily_cash_nonnegative": True,
        "order_event_cash_observation_count": 10,
        "minimum_observed_order_event_cash": "1000",
        "order_event_cash_nonnegative": True,
        "cash_observation_granularity": (
            "daily_close_and_post_order_event_not_continuous_intraday"
        ),
        "end_day_gross_at_most_one": True,
        "target_tracking_valid": True,
        "maximum_mean_target_weight_l1_error": "0.02",
        "maximum_single_target_weight_l1_error": "0.05",
        "matched_baseline_profile_sha256": (
            tilt_runtime.BASELINE_MATCHED_PROFILE_SHA256
        ),
        "matched_baseline_target_path_sha256": "f" * 64,
        "tilt_rank_rule_id": "scored_tied_midrank_centered_v1",
        "maximum_stock_weight_change_fraction": "0.20",
    })
    if tamper == "negative_cash":
        aggregate["minimum_end_day_cash"] = "-1"
    elif tamper == "target_error":
        aggregate["execution"]["maximum_target_weight_l1_error"] = "0.06"
    elif tamper == "wrong_baseline":
        aggregate["matched_baseline_profile_sha256"] = "0" * 64
    elif tamper == "wrong_baseline_path":
        aggregate["matched_baseline_target_path_sha256"] = "0" * 64
    elif tamper == "extra_field":
        aggregate["raw_order_rows"] = ["forbidden"]
    raw = subject._canonical(aggregate)
    meta = {
        "schema": runtime.META_SCHEMA,
        "role": plan.role, "profile_id": launch["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "package_id": "arv2-preliminary-qc-package-v1",
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "arv2-symbol-resolution-v1",
        "symbol_resolution_sha256": "0" * 64,
        "aggregate_schema": tilt_runtime.TILT_SUMMARY_SCHEMA,
        "aggregate_sha256": hashlib.sha256(raw).hexdigest(),
        "result_transport": "two_bounded_custom_summary_statistics",
        "raw_provider_rows": False, "raw_price_rows": False,
        "raw_order_rows": False, "preliminary": True,
        "formal": False, "backtest_only": True, "trading": False,
    }
    if tamper == "digest":
        meta["aggregate_sha256"] = "0" * 64
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: raw.decode("ascii"),
        "Net Profit": "999%",  # Never retained.
    }


@pytest.mark.parametrize("valid", (True, False))
def test_completed_tilt_read_is_single_use_and_retains_only_aggregate(
    monkeypatch, projection, tmp_path, valid,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    launch = _completed(plan, projection)
    statistics = _statistics(plan, launch, valid=valid)
    calls = []

    def post(_api, endpoint, payload):
        calls.append(endpoint)
        if endpoint == "files/read":
            return {"success": True, "files": [{
                "projectId": 111, "name": item.project_path,
                "content": item.source_bytes.decode("ascii"),
            } for item in projection.source_files]}
        if endpoint == "backtests/read":
            return {"success": True, "backtest": {
                "projectId": 111, "backtestId": "tilt-a1",
                "name": plan.backtest_name, "status": "Completed.",
                "statistics": statistics, "orders": [{"forbidden": True}],
            }}
        raise AssertionError(endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is valid
    assert set(result) == {"meta", "aggregates", "run_valid"}
    assert result["aggregates"]["matched_baseline_target_path_sha256"] == "f" * 64
    assert calls == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-valid").exists() is valid
    with pytest.raises(subject.SixUniverseTiltSubmissionError, match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls == ["files/read", "backtests/read"]


@pytest.mark.parametrize("tamper", (
    "negative_cash", "target_error", "wrong_baseline", "wrong_baseline_path",
    "extra_field", "digest",
))
def test_tilt_result_refuses_bad_bridge_or_lineage_after_one_read_claim(
    monkeypatch, projection, tmp_path, tamper,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    launch = _completed(plan, projection)
    statistics = _statistics(plan, launch, tamper=tamper)
    calls = []

    def post(_api, endpoint, _payload):
        calls.append(endpoint)
        if endpoint == "files/read":
            return {"success": True, "files": [{
                "projectId": 111, "name": item.project_path,
                "content": item.source_bytes.decode("ascii"),
            } for item in projection.source_files]}
        return {"success": True, "backtest": {
            "projectId": 111, "backtestId": "tilt-a1",
            "name": plan.backtest_name, "status": "Completed.",
            "statistics": statistics,
        }}

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    with pytest.raises(subject.SixUniverseTiltSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-read-claim").exists()
    assert not subject._control_path(plan, "result-valid").exists()
