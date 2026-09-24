"""Offline boundary tests for the cap-90 order family A1 submission."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_projection as projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as subject
from research.quantconnect import QuantConnectClient, QuantConnectCredentials


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def projections():
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return {
        candidate: projector.build_accepted_risk_six_universe_order_qc_projection(
            package, role=role, variant=runtime.CAP90_VARIANT,
        )
        for candidate, role in subject._ROLES.items()
    }


def _plan(tmp_path, projection, candidate="R181"):
    return subject.Cap90QcPlan(
        candidate_id=candidate,
        attempt=1,
        role=subject._ROLES[candidate],
        project_name="104 ARV2 SIX CAP90 " + candidate + " A1",
        backtest_name="ARV2 " + candidate + " A1 cap90 2021 2025",
        organization_id="a" * 32,
        projection_sha256=projection.projection_sha256,
        profile_sha256=projection.profile_sha256,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


@pytest.mark.parametrize("candidate", ("R181", "R182", "R183"))
def test_preview_authenticates_exact_role_and_source(projections, tmp_path, candidate):
    value = projections[candidate]
    plan = _plan(tmp_path, value, candidate)
    result = subject.preview(plan, value)
    assert result["role"] == plan.role
    assert len(result["source_files"]) == 13
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.preview(dataclasses.replace(plan, attempt=2), value)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.preview(dataclasses.replace(plan, profile_sha256="0" * 64), value)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.preview(dataclasses.replace(plan, role="matched" if plan.role != "matched" else "signal"), value)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.preview(plan, dataclasses.replace(value, projection_sha256="0" * 64))


def _project_row(plan, project_id=987):
    return {
        "projectId": project_id, "name": plan.project_name,
        "organizationId": plan.organization_id, "language": "Py",
        "owner": True, "codeRunning": False,
        "collaborators": [{"owner": True}],
    }


def _fake_qc(monkeypatch, plan, projection, *, corrupt_readback=False, private=True,
             compile_state="BuildSuccess", project_exists=False):
    calls = []
    project_id = 987
    uploaded = {"main.py": "default"}

    def post(_api, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read" and not payload:
            return {"success": True, "projects": [_project_row(plan)] if project_exists else []}
        if endpoint == "projects/create":
            return {"success": True, "projects": [_project_row(plan)]}
        if endpoint == "projects/read":
            row = _project_row(plan)
            if not private:
                row["collaborators"].append({"owner": False})
            return {"success": True, "projects": [row]}
        if endpoint == "files/read":
            return {"success": True, "files": [
                {"projectId": project_id, "name": path,
                 "content": content + ("# changed" if corrupt_readback and path == "main.py" and content != "default" else "")}
                for path, content in uploaded.items()
            ]}
        if endpoint in {"files/create", "files/update"}:
            uploaded[payload["name"]] = payload["content"]
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-a1"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "compile-a1", "state": compile_state}
        if endpoint == "backtests/create":
            return {"success": True, "backtest": {
                "projectId": project_id, "backtestId": "run-a1",
                "name": plan.backtest_name, "status": "In Queue...",
            }}
        raise AssertionError("unexpected endpoint " + endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls


def test_launch_claims_before_first_mutation_uploads_exact_bytes_and_launches_once(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    calls = _fake_qc(monkeypatch, plan, value)
    receipt = subject.launch_a1(plan, value, object())
    assert receipt["backtest_id"] == "run-a1"
    assert subject._read_control(subject._control_path(plan, "claim"))["projection_sha256"] == value.projection_sha256
    assert [endpoint for endpoint, _ in calls].count("backtests/create") == 1
    assert [endpoint for endpoint, _ in calls].count("compile/create") == 1
    assert len([endpoint for endpoint, _ in calls if endpoint in {"files/create", "files/update"}]) == 13
    before = len(calls)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_a1(plan, value, object())
    assert len(calls) == before


@pytest.mark.parametrize(
    "defect,expected_mutation",
    (("project_exists", False), ("private", True), ("corrupt_readback", True),
     ("compile_error", True)),
)
def test_launch_refuses_nonfresh_private_or_mismatched_source_and_spends_claim(
    monkeypatch, projections, tmp_path, defect, expected_mutation,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    opts = {
        "project_exists": defect == "project_exists",
        "private": defect != "private",
        "corrupt_readback": defect == "corrupt_readback",
        "compile_state": "BuildError" if defect == "compile_error" else "BuildSuccess",
    }
    calls = _fake_qc(monkeypatch, plan, value, **opts)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_a1(plan, value, object())
    mutations = [endpoint for endpoint, _ in calls if endpoint in {
        "projects/create", "files/create", "files/update", "compile/create", "backtests/create",
    }]
    assert bool(mutations) is expected_mutation
    assert not any(endpoint == "backtests/create" for endpoint, _ in calls)
    if defect == "project_exists":
        assert not subject._control_path(plan, "claim").exists()
    else:
        assert subject._control_path(plan, "claim").exists()
        if defect == "compile_error":
            assert subject._read_control(subject._control_path(plan, "terminal"))["status"] == "BuildError"


def _launched(plan):
    return {
        "candidate_id": plan.candidate_id, "role": plan.role,
        "project_id": 987, "project_name": plan.project_name,
        "compile_id": "compile-a1", "backtest_id": "run-a1",
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": runtime.require_six_universe_order_profile(
            plan.role, variant=runtime.CAP90_VARIANT,
        )["profile_id"],
        "profile_sha256": plan.profile_sha256,
    }


def _prepare_completed(plan, projection):
    launch = _launched(plan)
    identity = subject.preview(plan, projection)
    subject._write_once(subject._control_path(plan, "claim"), identity)
    subject._write_once(subject._control_path(plan, "launch"), launch)
    subject._write_once(subject._control_path(plan, "terminal"), {
        "candidate_id": plan.candidate_id, "status": "Completed.",
        "project_id": 987, "backtest_id": "run-a1",
    })
    return launch


def test_status_poll_ignores_extra_fields_and_requires_exact_run(monkeypatch, projections, tmp_path):
    plan = _plan(tmp_path, projections["R181"])
    launch = _launched(plan)
    subject._write_once(subject._control_path(plan, "launch"), launch)
    monkeypatch.setattr(subject, "_client", lambda _api: None)
    calls = []

    def post(_api, endpoint, payload):
        calls.append((endpoint, payload))
        assert endpoint == "backtests/list"
        return {"success": True, "count": 1, "backtests": [{
            "projectId": 987, "backtestId": "run-a1",
            "name": plan.backtest_name, "status": "Completed.",
            "statistics": {"Standard" : "ignored"}, "netProfit": 999,
        }]}

    monkeypatch.setattr(subject, "_post", post)
    assert subject.poll_status(plan, launch, object()) == "Completed."
    assert calls[0][1]["includeStatistics"] is False
    assert subject.poll_status(plan, launch, object()) == "Completed."
    assert len(calls) == 1


def _statistics(plan, launch, *, valid=True, bad_digest=False):
    account = {
        "observation_count": runtime.EXPECTED_SESSION_COUNT,
        "first_observation_session": runtime.EVALUATION_START_SESSION,
        "last_observation_session": runtime.EVALUATION_END_SESSION,
        "starting_equity": "1000000", "ending_equity": "1100000",
        "cumulative_return": "0.1", "maximum_drawdown": "-0.1",
        "annualized_volatility": "0.2", "zero_rate_sharpe": "0.5",
    }
    execution = {key: 0 for key in subject._EXECUTION_FIELDS}
    execution.update({
        "schema": "arv2-simulated-moo-executor-summary-v1",
        "decision_count": runtime.EXPECTED_DECISION_COUNT,
        **{key: "0" for key in subject._EXECUTION_DECIMALS},
        **{key: "0" * 64 for key in subject._EXECUTION_DIGESTS},
        "target_weight_l1_error_mark_basis": "prior_close_reference_prices_not_realized_open_prices",
        "fee_mismatch": False, "execution_failure": not valid, "run_valid": valid,
        "complete_holding_census_before_each_submission": True,
        "raw_order_rows_in_summary": False, "raw_security_rows_in_summary": False,
        "backtest_only": True, "simulated_market_on_open_orders": True,
        "live_orders": False, "paper_orders": False, "funded_orders": False,
        "deployment": False, "trading": False,
    })
    forced = {key: 0 for key in subject._FORCED_FIELDS}
    forced.update({
        "schema": runtime._forced.FORCED_DELISTING_SUMMARY_SCHEMA,
        "filled_notional": "0", "actual_engine_fee_amount": "0",
        "accounting_complete": True, "ledger_sha256": "0" * 64,
        "raw_order_rows_in_summary": False, "raw_security_rows_in_summary": False,
    })
    sleeve_rows = [
        [ticker, ticker, runtime.EXPECTED_DECISION_COUNT, 0,
         runtime.EXPECTED_DECISION_COUNT, 0, 0, 0, "0", "0", {},
         {"SIX_ETF_BASKET": runtime.EXPECTED_DECISION_COUNT}]
        for ticker in subject._UNIVERSES
    ]
    aggregate = {key: None for key in subject._AGGREGATE_FIELDS}
    aggregate.update({
        "schema": runtime.CAP90_SUMMARY_SCHEMA,
        "role": plan.role, "profile_id": launch["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "account": account,
        **{key: "0" * 64 for key in subject._AGGREGATE_DIGESTS},
        "mean_gross_exposure": "0.98", "maximum_gross_exposure": "0.98",
        "target_path_id": "arv2-target-path-v1",
        "fallback_counts": {"SIX_ETF_BASKET": 6 * runtime.EXPECTED_DECISION_COUNT},
        "sleeve_diagnostics": {
            "schema": "arv2-six-universe-order-sleeve-summary-table-v1",
            "fields": list(subject._SLEEVE_FIELDS), "rows": sleeve_rows,
        },
        "execution": execution, "engine_forced_delisting": forced,
        "reference_history_call_count": runtime.EXPECTED_DECISION_COUNT,
        "active_dynamic_minute_security_count": 0,
        "maximum_active_dynamic_minute_security_count": 0,
        "removed_dynamic_minute_security_count": 0,
        "pit_callback_source_row_count": 0,
        "fundamental_snapshot_unavailable_decision_count": 0,
        "constituent_collection_unavailable_decision_count": 0,
        "constituent_collection_unavailable_universe_counts": {
            ticker: 0 for ticker in subject._UNIVERSES
        },
        "preliminary": True, "formal": False,
        "backtest_only": True, "trading": False,
        "live_orders": False, "paper_orders": False,
        "funded_orders": False, "deployment": False,
        "run_valid": valid,
    })
    aggregate_text = subject._canonical(aggregate).decode("ascii")
    meta = {
        "schema": runtime.META_SCHEMA, "role": plan.role,
        "profile_id": launch["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "package_id": "arv2-preliminary-qc-package-v1",
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "arv2-symbol-resolution-v1",
        "symbol_resolution_sha256": "0" * 64,
        "aggregate_schema": runtime.CAP90_SUMMARY_SCHEMA,
        "aggregate_sha256": "0" * 64 if bad_digest else hashlib.sha256(aggregate_text.encode("ascii")).hexdigest(),
        "result_transport": "two_bounded_custom_summary_statistics",
        "raw_provider_rows": False, "raw_price_rows": False,
        "raw_order_rows": False, "preliminary": True, "formal": False,
        "backtest_only": True, "trading": False,
    }
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: aggregate_text,
        "Net Profit": "1000%",
    }


@pytest.mark.parametrize("valid", (True, False))
def test_one_result_read_hashes_raw_canonical_aggregate_and_distinguishes_invalid_run(
    monkeypatch, projections, tmp_path, valid,
):
    plan = _plan(tmp_path, projections["R181"])
    launch = _prepare_completed(plan, projections["R181"])
    monkeypatch.setattr(subject, "_client", lambda _api: None)
    calls = []

    def post(_api, endpoint, payload):
        calls.append(endpoint)
        if endpoint == "files/read":
            return {"success": True, "files": [{
                "projectId": 987, "name": item.project_path,
                "content": item.source_bytes.decode("ascii"),
            } for item in projections["R181"].source_files]}
        return {"success": True, "backtest": {
            "projectId": 987, "backtestId": "run-a1", "name": plan.backtest_name,
            "status": "Completed.", "statistics": _statistics(plan, launch, valid=valid),
            "orders": {"do-not-retain": True},
        }}

    monkeypatch.setattr(subject, "_post", post)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is valid
    assert set(result) == {"meta", "aggregates", "run_valid"}
    assert calls == ["files/read", "backtests/read"]
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls == ["files/read", "backtests/read"]


def test_result_digest_mismatch_is_refused_after_one_use_claim(monkeypatch, projections, tmp_path):
    plan = _plan(tmp_path, projections["R181"])
    launch = _prepare_completed(plan, projections["R181"])
    monkeypatch.setattr(subject, "_client", lambda _api: None)
    def post(_api, endpoint, _payload):
        if endpoint == "files/read":
            return {"success": True, "files": [{
                "projectId": 987, "name": item.project_path,
                "content": item.source_bytes.decode("ascii"),
            } for item in projections["R181"].source_files]}
        return {"success": True, "backtest": {
            "projectId": 987, "backtestId": "run-a1", "name": plan.backtest_name,
            "status": "Completed.",
            "statistics": _statistics(plan, launch, bad_digest=True),
        },
    }
    monkeypatch.setattr(subject, "_post", post)
    with pytest.raises(subject.Cap90QcSubmissionError, match="digest"):
        subject.read_aggregates_once(plan, launch, object())
    assert subject._control_path(plan, "result-read-claim").exists()


@pytest.mark.parametrize("insertion", ("top", "execution", "sleeve_reason", "forced"))
def test_result_reader_refuses_extra_fields_even_with_recomputed_digest(
    monkeypatch, projections, tmp_path, insertion,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    launch = _prepare_completed(plan, value)
    statistics = _statistics(plan, launch)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    if insertion == "top":
        aggregate["raw_orders"] = ["not-authorized"]
    elif insertion == "execution":
        aggregate["execution"]["raw_orders"] = ["not-authorized"]
    elif insertion == "sleeve_reason":
        aggregate["sleeve_diagnostics"]["rows"][0][10]["SECURITY-123"] = 1
    else:
        aggregate["engine_forced_delisting"]["raw_orders"] = ["not-authorized"]
    raw = subject._canonical(aggregate)
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = raw.decode("ascii")
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregate_sha256"] = hashlib.sha256(raw).hexdigest()
    statistics[runtime.META_STATISTIC_NAME] = subject._canonical(meta).decode("ascii")
    calls = []

    def post(_api, endpoint, _payload):
        calls.append(endpoint)
        if endpoint == "files/read":
            return {"success": True, "files": [{
                "projectId": 987, "name": item.project_path,
                "content": item.source_bytes.decode("ascii"),
            } for item in value.source_files]}
        return {"success": True, "backtest": {
            "projectId": 987, "backtestId": "run-a1", "name": plan.backtest_name,
            "status": "Completed.", "statistics": statistics,
        }}

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-read-claim").exists()


def test_result_reader_refuses_modified_cloud_source_before_outcome_read(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    launch = _prepare_completed(plan, value)
    calls = []

    def post(_api, endpoint, _payload):
        calls.append(endpoint)
        assert endpoint == "files/read"
        return {"success": True, "files": [{
            "projectId": 987, "name": item.project_path,
            "content": item.source_bytes.decode("ascii")
            + ("# changed" if item.project_path == "main.py" else ""),
        } for item in value.source_files]}

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    with pytest.raises(subject.Cap90QcSubmissionError, match="source bytes changed"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls == ["files/read"]
    assert not subject._control_path(plan, "result-read-claim").exists()


def test_later_roles_require_prior_authenticated_valid_result(
    monkeypatch, projections, tmp_path,
):
    plan = _plan(tmp_path, projections["R182"], "R182")
    calls = _fake_qc(monkeypatch, plan, projections["R182"])
    with pytest.raises(subject.Cap90QcSubmissionError, match="unavailable"):
        subject.launch_a1(plan, projections["R182"], object())
    assert calls == []


def test_default_qc_client_is_refused_even_with_offline_credentials():
    client = QuantConnectClient(
        QuantConnectCredentials("offline", "offline-token"),
    )
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject._client(client)
