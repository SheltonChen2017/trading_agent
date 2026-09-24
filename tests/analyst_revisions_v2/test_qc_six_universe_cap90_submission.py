"""Offline boundary tests for the cap-90 order family A1 submission."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_projection as projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_bridge_qc_projection as bridge_projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_bridge_qc_runtime as bridge_runtime
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as subject
from research.analyst_revisions_v2_qc.owner_signature_authority import OwnerSignatureAuthorityError
from research.quantconnect import QuantConnectClient, QuantConnectCredentials


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
EXECUTION_FIELDS = (
    "schema", "decision_count", "submitted_rebalance_count",
    "completed_rebalance_count", "holding_drift_skipped_rebalance_count",
    "submitted_order_count", "filled_order_count_sum", "canceled_order_count_sum",
    "invalid_order_count_sum", "orders_with_any_fill_count_sum",
    "modeled_fee_bps_per_side", "modeled_fee_amount", "actual_engine_fee_amount",
    "total_filled_notional", "mean_target_weight_l1_error",
    "maximum_target_weight_l1_error", "target_weight_l1_error_mark_basis",
    "fee_mismatch", "execution_failure", "run_valid", "plan_path_sha256",
    "submitted_plan_path_sha256", "holding_drift_path_sha256",
    "order_lifecycle_sha256", "external_order_event_count",
    "external_order_event_path_sha256", "corporate_action_replan_count",
    "corporate_action_replan_path_sha256",
    "complete_holding_census_before_each_submission", "raw_order_rows_in_summary",
    "raw_security_rows_in_summary", "backtest_only",
    "simulated_market_on_open_orders", "live_orders", "paper_orders",
    "funded_orders", "deployment", "trading",
)
FORCED_FIELDS = (
    "schema", "order_count", "event_count", "fill_event_count",
    "terminal_order_count", "absolute_filled_quantity", "filled_notional",
    "actual_engine_fee_amount", "accounting_complete", "ledger_sha256",
    "raw_order_rows_in_summary", "raw_security_rows_in_summary",
)
EXECUTION_DECIMALS = (
    "modeled_fee_amount", "actual_engine_fee_amount", "total_filled_notional",
    "mean_target_weight_l1_error", "maximum_target_weight_l1_error",
)
EXECUTION_DIGESTS = (
    "plan_path_sha256", "submitted_plan_path_sha256", "holding_drift_path_sha256",
    "order_lifecycle_sha256", "external_order_event_path_sha256",
    "corporate_action_replan_path_sha256",
)
AGGREGATE_DIGESTS = (
    "account_observation_path_sha256", "gross_exposure_path_sha256",
    "target_path_sha256", "construction_path_sha256",
    "decision_target_path_sha256",
    "fundamental_snapshot_unavailable_session_sha256",
    "constituent_collection_unavailable_path_sha256",
)


@pytest.fixture(scope="module")
def projections():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
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


@pytest.fixture(scope="module")
def bridge_projections():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return {
        candidate: bridge_projector.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=subject._ROLES[candidate],
        )
        for candidate in ("R181", "R182")
    }


def _bridge_plan(tmp_path, projection, candidate="R181"):
    attempt = 3 if candidate == "R181" else 1
    project_name = (
        subject._R181_A2_PROJECT_NAME if candidate == "R181"
        else "105 ARV2 SIX CAP90 MATCHED R182 2021 2025"
    )
    run_prefix = (
        "ARV2 R181A3 six cap90 bridge signal 2021 2025 "
        if candidate == "R181" else
        "ARV2 R182A1 six cap90 bridge matched 2021 2025 "
    )
    return dataclasses.replace(
        _plan(tmp_path, projection, candidate),
        attempt=attempt,
        project_name=project_name,
        backtest_name=run_prefix + projection.projection_sha256[:8],
    )


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


def _allow_owner_signature(monkeypatch, plan, projection):
    """Pin the actual rendered bytes while avoiding the owner's private key."""
    payload = subject.render_owner_launch_permit(plan, projection)
    signature = object()
    verified = SimpleNamespace(
        purpose=subject.FORMAL_EXECUTION_PURPOSE,
        authority_payload_sha256=hashlib.sha256(payload).hexdigest(),
        authority_sha256="a" * 64,
        signature_sha256="b" * 64,
    )
    calls = []

    def require(value, *, authority_payload):
        calls.append((value, authority_payload))
        if value is not signature or authority_payload != payload:
            raise OwnerSignatureAuthorityError("wrong signed launch payload")
        return verified

    monkeypatch.setattr(subject, "require_formal_execution_owner_signature", require)
    return signature, calls


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


def test_owner_permit_binds_exact_attempt_source_project_and_one_submission(
    projections, tmp_path,
):
    value = projections["R181"]
    a1 = _plan(tmp_path, value)
    raw = subject.render_owner_launch_permit(a1, value)
    permit = json.loads(raw)
    assert subject._canonical(permit) == raw
    assert permit["schema"] == subject._LAUNCH_PERMIT_SCHEMA
    assert permit["signature_purpose"] == subject.FORMAL_EXECUTION_PURPOSE
    assert permit["action"] == "one_private_exploratory_order_backtest_launch"
    assert permit["attempt"] == 1
    assert permit["project_id"] is None
    assert permit["projection_sha256"] == value.projection_sha256
    assert permit["profile_sha256"] == value.profile_sha256
    assert permit["maximum_backtest_submissions"] == 1
    assert permit["mutating_endpoint_budget"]["backtests/create"] == 1
    assert permit["result_read_authorized"] is False
    assert permit["paper_live_deployment_funded_trading_authorized"] is False
    for changed in (
        dataclasses.replace(a1, project_name=a1.project_name + " changed"),
        dataclasses.replace(a1, backtest_name=a1.backtest_name + " changed"),
        dataclasses.replace(a1, control_directory=tmp_path / "other"),
        dataclasses.replace(a1, organization_id="b" * 32),
    ):
        assert subject.render_owner_launch_permit(changed, value) != raw
    a2 = _a2_plan(tmp_path, value)
    a2_permit = json.loads(subject.render_owner_launch_permit(a2, value))
    assert a2_permit["attempt"] == 2
    assert a2_permit["project_id"] == subject._R181_A2_PROJECT_ID
    assert a2_permit["mutating_endpoint_budget"] == {
        "files/create": 1, "files/update": 2,
        "compile/create": 1, "backtests/create": 1,
    }
    assert subject.render_owner_launch_permit(a2, value) != raw


def test_load_owner_permit_passes_exact_bytes_to_reviewed_verifier(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    allowed = tmp_path / "allowed-signers"
    detached = tmp_path / "launch.sig"
    observed = []
    sentinel = object()

    def load(**kwargs):
        observed.append(kwargs)
        return sentinel

    monkeypatch.setattr(subject, "load_formal_execution_owner_signature", load)
    assert subject.load_owner_launch_permit(
        plan, value, allowed_signers_path=allowed, signature_path=detached,
    ) is sentinel
    assert observed == [{
        "authority_payload": subject.render_owner_launch_permit(plan, value),
        "allowed_signers_path": allowed, "signature_path": detached,
    }]


def test_unsigned_or_wrongly_signed_launch_refuses_before_any_qc_or_claim(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _plan(tmp_path, value)
    calls = _fake_qc(monkeypatch, plan, value)
    with pytest.raises(subject.Cap90QcSubmissionError, match="owner launch signature"):
        subject.launch_a1(plan, value, object())
    assert calls == []
    assert not (plan.control_directory / "R181-A1-claim.json").exists()

    signature, checks = _allow_owner_signature(monkeypatch, plan, value)
    changed = dataclasses.replace(plan, backtest_name=plan.backtest_name + " changed")
    with pytest.raises(subject.Cap90QcSubmissionError, match="owner launch signature"):
        subject.launch_a1(changed, value, object(), owner_signature=signature)
    assert len(checks) == 1
    assert calls == []
    assert not (plan.control_directory / "R181-A1-claim.json").exists()


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
    signature, signature_calls = _allow_owner_signature(monkeypatch, plan, value)
    calls = _fake_qc(monkeypatch, plan, value)
    receipt = subject.launch_a1(plan, value, object(), owner_signature=signature)
    assert receipt["backtest_id"] == "run-a1"
    assert receipt["owner_signature_sha256"] == "b" * 64
    assert len(signature_calls) == 1
    assert subject._read_control(subject._control_path(plan, "claim"))["projection_sha256"] == value.projection_sha256
    assert [endpoint for endpoint, _ in calls].count("backtests/create") == 1
    assert [endpoint for endpoint, _ in calls].count("compile/create") == 1
    assert len([endpoint for endpoint, _ in calls if endpoint in {"files/create", "files/update"}]) == 13
    before = len(calls)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_a1(plan, value, object(), owner_signature=signature)
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
    signature, _ = _allow_owner_signature(monkeypatch, plan, value)
    opts = {
        "project_exists": defect == "project_exists",
        "private": defect != "private",
        "corrupt_readback": defect == "corrupt_readback",
        "compile_state": "BuildError" if defect == "compile_error" else "BuildSuccess",
    }
    calls = _fake_qc(monkeypatch, plan, value, **opts)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_a1(plan, value, object(), owner_signature=signature)
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
    execution = {key: 0 for key in EXECUTION_FIELDS}
    execution.update({
        "schema": "arv2-simulated-moo-executor-summary-v1",
        "decision_count": runtime.EXPECTED_DECISION_COUNT,
        **{key: "0" for key in EXECUTION_DECIMALS},
        **{key: "0" * 64 for key in EXECUTION_DIGESTS},
        "target_weight_l1_error_mark_basis": "prior_close_reference_prices_not_realized_open_prices",
        "fee_mismatch": False, "execution_failure": not valid, "run_valid": valid,
        "complete_holding_census_before_each_submission": True,
        "raw_order_rows_in_summary": False, "raw_security_rows_in_summary": False,
        "backtest_only": True, "simulated_market_on_open_orders": True,
        "live_orders": False, "paper_orders": False, "funded_orders": False,
        "deployment": False, "trading": False,
    })
    forced = {key: 0 for key in FORCED_FIELDS}
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
        **{key: "0" * 64 for key in AGGREGATE_DIGESTS},
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
    if insertion in {"top", "sleeve_reason"}:
        with pytest.raises(subject.Cap90QcSubmissionError):
            subject.read_aggregates_once(plan, launch, object())
    else:
        result = subject.read_aggregates_once(plan, launch, object())
        assert "raw_orders" not in result["aggregates"][
            "execution" if insertion == "execution" else "engine_forced_delisting"
        ]
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
    monkeypatch, bridge_projections, tmp_path,
):
    value = bridge_projections["R182"]
    plan = _bridge_plan(tmp_path, value, "R182")
    calls = _fake_qc(monkeypatch, plan, value)
    with pytest.raises(subject.Cap90QcSubmissionError, match="unavailable"):
        subject.launch_a1(
            plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
    assert calls == []


def test_default_qc_client_is_refused_even_with_offline_credentials():
    client = QuantConnectClient(
        QuantConnectCredentials("offline", "offline-token"),
    )
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject._client(client)


def _a2_plan(tmp_path, projection):
    return dataclasses.replace(
        _plan(tmp_path, projection),
        attempt=2,
        project_name=subject._R181_A2_PROJECT_NAME,
        backtest_name="ARV2 R181A2 six cap90 signal 2021 2025 b68661ec",
    )


def _a2_residue(monkeypatch, plan, projection):
    old_files = []
    for item in projection.source_files:
        if item.project_path == subject._R181_RUNTIME_PATH:
            old_files.append([
                item.project_path,
                "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
                67316,
            ])
        else:
            old_files.append([item.project_path, item.content_sha256, item.byte_count])
    claim = {
        "candidate_id": "R181", "role": "signal",
        "profile_id": projection.profile_id,
        "profile_sha256": projection.profile_sha256,
        "projection_sha256": subject._R181_A1_PROJECTION_SHA256,
        "source_files": old_files,
    }
    raw = subject._canonical(claim)
    monkeypatch.setattr(subject, "_R181_A1_CLAIM_SHA256", hashlib.sha256(raw).hexdigest())
    subject._write_once(
        subject._control_path(dataclasses.replace(plan, attempt=1), "claim"),
        claim,
    )
    default_main = "#" * 406
    monkeypatch.setattr(subject, "_R181_A1_DEFAULT_MAIN", (
        len(default_main), hashlib.sha256(default_main.encode("ascii")).hexdigest(),
    ))
    uploaded = {
        item.project_path: item.source_bytes.decode("ascii")
        for item in projection.source_files
        if item.project_path not in {
            subject._R181_RUNTIME_PATH, subject._R181_TARGETS_PATH, "main.py",
        }
    }
    uploaded[subject._R181_RUNTIME_PATH] = "#"
    uploaded["main.py"] = default_main
    return uploaded


def _fake_a2_qc(monkeypatch, plan, projection, uploaded, *, defect=None):
    calls = []
    launched = False
    file_reads = 0

    def post(_api, endpoint, payload):
        nonlocal launched, file_reads
        calls.append((endpoint, payload))
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            row = _project_row(plan, subject._R181_A2_PROJECT_ID)
            if defect == "public":
                row["collaborators"].append({"owner": False})
            return {"success": True, "projects": [row]}
        if endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            if defect == "prior_run":
                return {"success": True, "count": 1, "backtests": [{"backtestId": "other"}]}
            if not launched:
                return {"success": True, "count": 0, "backtests": []}
            return {"success": True, "count": 1, "backtests": [{
                "projectId": subject._R181_A2_PROJECT_ID,
                "backtestId": "run-a2", "name": plan.backtest_name,
                "status": "Completed.",
            }]}
        if endpoint == "files/read":
            file_reads += 1
            return {"success": True, "files": [{
                "projectId": subject._R181_A2_PROJECT_ID,
                "name": path,
                "content": content + ("#" if defect == "bad_readback" and file_reads == 2 and path == "main.py" else ""),
            } for path, content in uploaded.items()]}
        if endpoint in {"files/create", "files/update"}:
            uploaded[payload["name"]] = payload["content"]
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-a2"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "compile-a2", "state": (
                "BuildError" if defect == "compile_error" else "BuildSuccess"
            )}
        if endpoint == "backtests/create":
            launched = True
            return {"success": True, "backtest": {
                "projectId": subject._R181_A2_PROJECT_ID,
                "backtestId": "run-a2", "name": plan.backtest_name,
                "status": "In Queue...",
            }}
        if endpoint == "backtests/read":
            receipt = subject._read_control(subject._control_path(plan, "launch"))
            return {"success": True, "backtest": {
                "projectId": subject._R181_A2_PROJECT_ID,
                "backtestId": "run-a2", "name": plan.backtest_name,
                "status": "Completed.",
                "statistics": _statistics(plan, receipt),
                "orders": {"not-retained": True},
            }}
        raise AssertionError("unexpected endpoint " + endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls


def test_r181_a2_unsigned_refuses_before_existing_project_read_or_mutation(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded)
    with pytest.raises(subject.Cap90QcSubmissionError, match="owner launch signature"):
        subject.launch_r181_a2(plan, value, object())
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_r181_a2_resumes_same_project_and_authenticates_completed_result(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    signature, signature_calls = _allow_owner_signature(monkeypatch, plan, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded)

    receipt = subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    assert receipt["attempt"] == 2
    assert receipt["owner_signature_sha256"] == "b" * 64
    assert len(signature_calls) == 1
    assert receipt["project_id"] == subject._R181_A2_PROJECT_ID
    assert [endpoint for endpoint, _ in calls].count("backtests/create") == 1
    assert [endpoint for endpoint, _ in calls].count("compile/create") == 1
    assert [endpoint for endpoint, _ in calls if endpoint in {"files/create", "files/update"}] == [
        "files/update", "files/create", "files/update",
    ]
    assert not any(endpoint in {"projects/create", "files/delete"} for endpoint, _ in calls)
    assert subject.poll_status(plan, receipt, object()) == "Completed."
    result = subject.read_aggregates_once(plan, receipt, object())
    assert result["run_valid"] is True
    valid = subject._read_control(subject._control_path(plan, "result-valid"))
    assert valid["attempt"] == 2
    assert valid["projection_sha256"] == value.projection_sha256
    assert [endpoint for endpoint, _ in calls].count("backtests/read") == 1
    before = len(calls)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_a1(plan, value, object())
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.read_aggregates_once(plan, receipt, object())
    assert len(calls) == before


@pytest.mark.parametrize("defect", (
    "runtime", "main", "missing_file", "extra_file", "public", "prior_run",
))
def test_r181_a2_refuses_changed_residue_or_project_before_claim_or_mutation(
    monkeypatch, projections, tmp_path, defect,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    signature, _ = _allow_owner_signature(monkeypatch, plan, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    if defect == "runtime":
        uploaded[subject._R181_RUNTIME_PATH] = "!"
    elif defect == "main":
        uploaded["main.py"] += "#"
    elif defect == "missing_file":
        uploaded.pop("accepted_risk_preliminary_rating_policy.py")
    elif defect == "extra_file":
        uploaded["unexpected.py"] = "#"
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded, defect=defect)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    assert not subject._control_path(plan, "claim").exists()
    assert not any(endpoint in {
        "projects/create", "files/create", "files/update", "compile/create", "backtests/create",
    } for endpoint, _ in calls)


@pytest.mark.parametrize("defect", ("bad_readback", "compile_error"))
def test_r181_a2_claim_remains_spent_after_upload_or_compile_failure(
    monkeypatch, projections, tmp_path, defect,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    signature, _ = _allow_owner_signature(monkeypatch, plan, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded, defect=defect)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    assert subject._control_path(plan, "claim").exists()
    assert not any(endpoint == "backtests/create" for endpoint, _ in calls)
    assert not any(endpoint == "projects/create" for endpoint, _ in calls)
    if defect == "compile_error":
        assert subject._read_control(subject._control_path(plan, "terminal"))["status"] == "BuildError"
    else:
        assert not any(endpoint == "compile/create" for endpoint, _ in calls)
    before = len(calls)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    assert len(calls) == before


def test_r181_a2_refuses_a1_claim_mutation_before_qc_access(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    signature, _ = _allow_owner_signature(monkeypatch, plan, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded)
    monkeypatch.setattr(subject, "_R181_A1_CLAIM_SHA256", "0" * 64)
    with pytest.raises(subject.Cap90QcSubmissionError, match="claim bytes changed"):
        subject.launch_r181_a2(plan, value, object(), owner_signature=signature)
    assert calls == []


def test_r181_a2_pins_new_runtime_bytes_not_only_claimed_projection_digest(
    monkeypatch, projections, tmp_path,
):
    value = projections["R181"]
    plan = _a2_plan(tmp_path, value)
    signature, _ = _allow_owner_signature(monkeypatch, plan, value)
    uploaded = _a2_residue(monkeypatch, plan, value)
    calls = _fake_a2_qc(monkeypatch, plan, value, uploaded)
    items = []
    for item in value.source_files:
        if item.project_path == subject._R181_RUNTIME_PATH:
            changed = item.source_bytes + b"#"
            item = dataclasses.replace(
                item, source_bytes=changed, byte_count=len(changed),
                content_sha256=hashlib.sha256(changed).hexdigest(),
            )
        items.append(item)
    altered = dataclasses.replace(
        value, source_files=tuple(items),
        total_source_byte_count=value.total_source_byte_count + 1,
    )
    # Even though the projection advertises its old digest, the signed source
    # inventory refuses the split view before QC. A newly signed split view
    # must still hit the independent exact A2 per-file pin.
    with pytest.raises(subject.Cap90QcSubmissionError, match="owner launch signature"):
        subject.launch_r181_a2(plan, altered, object(), owner_signature=signature)
    assert calls == []
    altered_signature, _ = _allow_owner_signature(monkeypatch, plan, altered)
    with pytest.raises(subject.Cap90QcSubmissionError, match="changes more"):
        subject.launch_r181_a2(plan, altered, object(), owner_signature=altered_signature)
    assert calls == []


def _synthetic_a2_invalid_receipts(monkeypatch, plan, old_projection):
    """Create private, count-only spent-A2 evidence without real QC I/O."""
    root = plan.control_directory
    root.mkdir(mode=0o700)
    project = subject._R181_A2_PROJECT_ID
    backtest = subject._R181_A2_BACKTEST_ID
    original = {
        "claim": {
            "candidate_id": "R181", "attempt": 2, "role": "signal",
            "project_id": project,
            "projection_sha256": subject._R181_A2_PROJECTION_SHA256,
            "profile_sha256": subject._R181_A2_PROFILE_SHA256,
            "source_files": [
                [item.project_path, item.content_sha256, item.byte_count]
                for item in old_projection.source_files
            ],
        },
        "launch": {
            "candidate_id": "R181", "attempt": 2,
            "project_id": project, "backtest_id": backtest,
            "projection_sha256": subject._R181_A2_PROJECTION_SHA256,
            "profile_sha256": subject._R181_A2_PROFILE_SHA256,
        },
        "terminal": {
            "candidate_id": "R181", "status": "Completed.",
            "project_id": project, "backtest_id": backtest,
        },
        "result-read-claim": {
            "candidate_id": "R181", "project_id": project,
            "backtest_id": backtest,
        },
    }
    digests = {}
    for name, value in original.items():
        subject._write_once(root / ("R181-A2-" + name + ".json"), value)
        digests[name] = hashlib.sha256(subject._canonical(value)).hexdigest()
    common = {
        "aggregate_sha256": subject._R181_A2_AGGREGATE_SHA256,
        "backtest_id": backtest, "project_id": project,
        "profile_sha256": subject._R181_A2_PROFILE_SHA256,
        "receipt_sha256": {
            "R181-A2-" + key + ".json": digest for key, digest in digests.items()
        },
        "raw_order_values_retained": False,
    }
    v4_claim = {**common, "schema": "synthetic-v4-claim"}
    v4_result = {
        "schema": "arv2-r181-a2-redacted-order-reasons-v4",
        "filled_order_count": 6267, "invalid_order_count": 22,
        "reason_counts": {"INSUFFICIENT_BUYING_POWER": 22},
    }
    for name, value in (
        ("invalid-order-diagnostic-v4-claim", v4_claim),
        ("invalid-order-diagnostic-v4-result", v4_result),
    ):
        subject._write_once(root / ("R181-A2-" + name + ".json"), value)
        digests[name] = hashlib.sha256(subject._canonical(value)).hexdigest()
    v5_claim = {
        **common, "schema": "synthetic-v5-claim",
        "v4_claim_sha256": digests["invalid-order-diagnostic-v4-claim"],
        "v4_result_sha256": digests["invalid-order-diagnostic-v4-result"],
    }
    v5_result = {
        "schema": "arv2-r181-a2-buying-power-timing-v5",
        "filled_order_count": 6267, "invalid_order_count": 22,
        "direction_counts": {"BUY": 22, "SELL": 0, "UNKNOWN": 0},
        "time_bin_counts": {
            "PRE_OPEN": 22, "AT_OR_AFTER_OPEN": 0, "UNKNOWN": 0,
        },
    }
    for name, value in (
        ("buying-power-timing-v5-claim", v5_claim),
        ("buying-power-timing-v5-result", v5_result),
    ):
        subject._write_once(root / ("R181-A2-" + name + ".json"), value)
        digests[name] = hashlib.sha256(subject._canonical(value)).hexdigest()
    monkeypatch.setattr(subject, "_R181_A2_CONTROL_SHA256", digests)
    return {
        item.project_path: item.source_bytes.decode("ascii")
        for item in old_projection.source_files
    }


def _fake_a3_qc(monkeypatch, plan, uploaded, *, defect=None):
    calls = []
    launched = False
    file_reads = 0

    def post(_api, endpoint, payload):
        nonlocal launched, file_reads
        calls.append((endpoint, payload))
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            row = _project_row(plan, subject._R181_A2_PROJECT_ID)
            if defect == "public":
                row["collaborators"].append({"owner": False})
            return {"success": True, "projects": [row]}
        if endpoint == "backtests/list":
            if launched:
                return {"success": True, "count": 1, "backtests": [{
                    "projectId": subject._R181_A2_PROJECT_ID,
                    "backtestId": "run-a3", "name": plan.backtest_name,
                    "status": "Completed.",
                }]}
            return {"success": True, "count": 1, "backtests": [{
                "projectId": subject._R181_A2_PROJECT_ID,
                "backtestId": (
                    "unexpected" if defect == "extra_run"
                    else subject._R181_A2_BACKTEST_ID
                ),
                "name": "ARV2 R181A2 six cap90 signal 2021 2025 b68661ec",
                "status": "Completed.",
            }]}
        if endpoint == "files/read":
            file_reads += 1
            return {"success": True, "files": [{
                "projectId": subject._R181_A2_PROJECT_ID,
                "name": path,
                "content": content + (
                    "#" if defect == "bad_readback" and file_reads == 2
                    and path == "main.py" else ""
                ),
            } for path, content in uploaded.items()]}
        if endpoint in {"files/create", "files/update"}:
            uploaded[payload["name"]] = payload["content"]
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-a3"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "compile-a3", "state": (
                "BuildError" if defect == "compile_error" else "BuildSuccess"
            )}
        if endpoint == "backtests/create":
            launched = True
            return {"success": True, "backtest": {
                "projectId": subject._R181_A2_PROJECT_ID,
                "backtestId": "run-a3", "name": plan.backtest_name,
                "status": "In Queue...",
            }}
        raise AssertionError("unexpected endpoint " + endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls


def test_r181_a3_exact_waiver_and_a2_evidence_precede_all_qc_access(
    monkeypatch, projections, bridge_projections, tmp_path,
):
    value = bridge_projections["R181"]
    plan = _bridge_plan(tmp_path, value)
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, plan, projections["R181"])
    calls = _fake_a3_qc(monkeypatch, plan, uploaded)
    with pytest.raises(subject.Cap90QcSubmissionError, match="owner launch signature"):
        subject.launch_r181_a3(plan, value, object())
    with pytest.raises(subject.Cap90QcSubmissionError, match="waiver"):
        subject.launch_r181_a3(
            plan, value, object(), owner_waiver_id="different-owner-waiver",
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()

    # Both A2's invalid diagnosis and the per-file source are predecessor
    # authority, not a caller assertion. A modified private receipt refuses.
    tampered = plan.control_directory / "R181-A2-buying-power-timing-v5-result.json"
    tampered.write_bytes(tampered.read_bytes() + b" ")
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a3(
            plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_r181_a3_reuses_only_a2_project_and_launches_once(
    monkeypatch, projections, bridge_projections, tmp_path,
):
    value = bridge_projections["R181"]
    plan = _bridge_plan(tmp_path, value)
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, plan, projections["R181"])
    calls = _fake_a3_qc(monkeypatch, plan, uploaded)
    receipt = subject.launch_r181_a3(
        plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
    )
    assert receipt["attempt"] == 3
    assert receipt["project_id"] == subject._R181_A2_PROJECT_ID
    assert receipt["owner_launch_waiver_id"] == subject._EXPLORATORY_WAIVER_ID
    claim = subject._read_control(subject._control_path(plan, "claim"))
    assert claim["owner_waived_payload_sha256"] == receipt["owner_waived_payload_sha256"]
    assert len(claim["source_files"]) == 14
    endpoints = [endpoint for endpoint, _ in calls]
    assert endpoints.count("backtests/create") == 1
    assert endpoints.count("compile/create") == 1
    assert [endpoint for endpoint in endpoints if endpoint in {
        "projects/create", "files/create", "files/update", "files/delete",
    }] == ["files/update", "files/create"]
    assert not any(endpoint == "backtests/read" for endpoint in endpoints)
    assert subject.poll_status(plan, receipt, object()) == "Completed."
    before = len(calls)
    with pytest.raises(subject.Cap90QcSubmissionError, match="already claimed"):
        subject.launch_r181_a3(
            plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
    assert len(calls) == before


@pytest.mark.parametrize("defect", (
    "source", "public", "extra_run", "bad_readback", "compile_error",
))
def test_r181_a3_refuses_bad_preflight_or_spends_only_final_claim(
    monkeypatch, projections, bridge_projections, tmp_path, defect,
):
    value = bridge_projections["R181"]
    plan = _bridge_plan(tmp_path, value)
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, plan, projections["R181"])
    if defect == "source":
        uploaded["main.py"] += "# changed"
    calls = _fake_a3_qc(monkeypatch, plan, uploaded, defect=defect)
    with pytest.raises(subject.Cap90QcSubmissionError):
        subject.launch_r181_a3(
            plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
    endpoints = [endpoint for endpoint, _ in calls]
    assert endpoints.count("backtests/create") == 0
    assert endpoints.count("projects/create") == 0
    if defect in {"source", "public", "extra_run"}:
        assert not subject._control_path(plan, "claim").exists()
        assert not any(endpoint in {
            "files/create", "files/update", "compile/create",
        } for endpoint in endpoints)
    else:
        assert subject._control_path(plan, "claim").exists()


def test_bridge_source_split_view_refuses_before_qc_even_with_waiver(
    monkeypatch, projections, bridge_projections, tmp_path,
):
    value = bridge_projections["R181"]
    plan = _bridge_plan(tmp_path, value)
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, plan, projections["R181"])
    calls = _fake_a3_qc(monkeypatch, plan, uploaded)
    changed_files = []
    for item in value.source_files:
        if item.project_path == "main.py":
            raw = item.source_bytes + b"# altered\n"
            item = dataclasses.replace(
                item, source_bytes=raw, byte_count=len(raw),
                content_sha256=hashlib.sha256(raw).hexdigest(),
            )
        changed_files.append(item)
    altered = dataclasses.replace(
        value, source_files=tuple(changed_files),
        total_source_byte_count=value.total_source_byte_count + len(b"# altered\n"),
    )
    with pytest.raises(subject.Cap90QcSubmissionError, match="self-authenticating"):
        subject.launch_r181_a3(
            plan, altered, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def _bridge_statistics(plan, launch, *, valid=True, tracking_error=False):
    statistics = _statistics(plan, launch, valid=valid)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate.update({
        "schema": bridge_runtime.BRIDGE_SUMMARY_SCHEMA,
        "admission_leverage": "2", "target_gross_exposure": "0.98",
        "minimum_end_day_cash": "1000",
        "daily_cash_nonnegative": True,
        "order_event_cash_observation_count": 10,
        "minimum_observed_order_event_cash": "1000",
        "order_event_cash_nonnegative": True,
        "cash_observation_granularity": (
            "daily_close_and_post_order_event_not_continuous_intraday"
        ),
        "end_day_gross_at_most_one": True,
        "target_tracking_valid": not tracking_error,
        "maximum_mean_target_weight_l1_error": "0.02",
        "maximum_single_target_weight_l1_error": "0.05",
        "run_valid": valid and not tracking_error,
    })
    aggregate["execution"]["mean_target_weight_l1_error"] = "0.01"
    aggregate["execution"]["maximum_target_weight_l1_error"] = (
        "0.10" if tracking_error else "0.03"
    )
    raw = subject._canonical(aggregate)
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = raw.decode("ascii")
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregate_schema"] = bridge_runtime.BRIDGE_SUMMARY_SCHEMA
    meta["aggregate_sha256"] = hashlib.sha256(raw).hexdigest()
    statistics[runtime.META_STATISTIC_NAME] = subject._canonical(meta).decode("ascii")
    return statistics


@pytest.mark.parametrize("valid,tracking_error", ((True, False), (False, False), (True, True)))
def test_bridge_result_read_requires_cash_exposure_and_target_tracking_before_valid_receipt(
    monkeypatch, projections, bridge_projections, tmp_path, valid, tracking_error,
):
    value = bridge_projections["R181"]
    plan = _bridge_plan(tmp_path, value)
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, plan, projections["R181"])
    _fake_a3_qc(monkeypatch, plan, uploaded)
    launch = subject.launch_r181_a3(
        plan, value, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    previous_post = subject._post
    statistics = _bridge_statistics(
        plan, launch, valid=valid, tracking_error=tracking_error,
    )

    def post(api, endpoint, payload):
        if endpoint == "backtests/read":
            return {"success": True, "backtest": {
                "projectId": launch["project_id"],
                "backtestId": launch["backtest_id"],
                "name": plan.backtest_name, "status": "Completed.",
                "statistics": statistics,
                "orders": {"unread": True},
            }}
        return previous_post(api, endpoint, payload)

    monkeypatch.setattr(subject, "_post", post)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is (valid and not tracking_error)
    assert result["aggregates"]["minimum_end_day_cash"] == "1000"
    assert result["aggregates"]["maximum_target_weight_l1_error"] == (
        "0.10" if tracking_error else "0.03"
    )
    valid_path = subject._control_path(plan, "result-valid")
    assert valid_path.exists() is (valid and not tracking_error)
    if valid and not tracking_error:
        receipt = subject._read_control(valid_path)
        assert receipt["attempt"] == 3
        assert receipt["projection_sha256"] == value.projection_sha256
        assert receipt["profile_sha256"] == value.profile_sha256
        assert receipt["project_id"] == subject._R181_A2_PROJECT_ID


@pytest.mark.parametrize("defect", (
    "negative_cash", "cash_flag", "negative_event_cash", "event_cash_flag",
    "event_cash_missing", "excess_gross", "gross_flag",
    "tracking_flag", "tracking_error", "invalid_order", "admission_leverage",
))
def test_bridge_aggregate_guard_isolates_actual_cash_exposure_and_tracking(
    bridge_projections, tmp_path, defect,
):
    plan = _bridge_plan(tmp_path, bridge_projections["R181"])
    launch = _launched(plan)
    aggregate = json.loads(
        _bridge_statistics(plan, launch)[runtime.AGGREGATES_STATISTIC_NAME]
    )
    if defect == "negative_cash":
        aggregate["minimum_end_day_cash"] = "-1"
    elif defect == "cash_flag":
        aggregate["daily_cash_nonnegative"] = False
    elif defect == "negative_event_cash":
        aggregate["minimum_observed_order_event_cash"] = "-1"
    elif defect == "event_cash_flag":
        aggregate["order_event_cash_nonnegative"] = False
    elif defect == "event_cash_missing":
        aggregate["minimum_observed_order_event_cash"] = None
    elif defect == "excess_gross":
        aggregate["maximum_gross_exposure"] = "1.01"
    elif defect == "gross_flag":
        aggregate["end_day_gross_at_most_one"] = False
    elif defect == "tracking_flag":
        aggregate["target_tracking_valid"] = False
    elif defect == "tracking_error":
        aggregate["execution"]["maximum_target_weight_l1_error"] = "0.051"
    elif defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    else:
        aggregate["admission_leverage"] = "1"
    with pytest.raises(subject.Cap90QcSubmissionError, match="bridge cash, exposure, or target tracking"):
        subject._project_aggregate(aggregate, bridge=True)


def test_r182_bridge_requires_valid_a3_chain_not_invalid_a2(
    monkeypatch, projections, bridge_projections, tmp_path,
):
    signal = bridge_projections["R181"]
    matched = bridge_projections["R182"]
    signal_plan = _bridge_plan(tmp_path, signal)
    matched_plan = _bridge_plan(tmp_path, matched, "R182")
    uploaded = _synthetic_a2_invalid_receipts(monkeypatch, signal_plan, projections["R181"])
    calls = _fake_a3_qc(monkeypatch, signal_plan, uploaded)
    with pytest.raises(subject.Cap90QcSubmissionError, match="unavailable"):
        subject._require_prior_valid_role(matched_plan)
    assert calls == []
    signal_launch = subject.launch_r181_a3(
        signal_plan, signal, object(), owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
    )
    assert subject.poll_status(signal_plan, signal_launch, object()) == "Completed."
    subject._write_once(subject._control_path(signal_plan, "result-read-claim"), {
        "candidate_id": "R181", "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": signal_launch["backtest_id"],
    })
    subject._write_once(subject._control_path(signal_plan, "result-valid"), {
        "candidate_id": "R181", "attempt": 3, "run_valid": True,
        "aggregate_sha256": "a" * 64,
        "projection_sha256": signal.projection_sha256,
        "profile_sha256": signal.profile_sha256,
        "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": signal_launch["backtest_id"],
    })
    subject._require_prior_valid_role(matched_plan)
    monkeypatch.setattr(subject, "_R181_A3_PROJECTION_SHA256", "0" * 64)
    with pytest.raises(subject.Cap90QcSubmissionError, match="preceding matched"):
        subject._require_prior_valid_role(matched_plan)


def test_r182_bridge_launch_is_waived_only_after_exact_valid_a3(
    monkeypatch, bridge_projections, tmp_path,
):
    signal = bridge_projections["R181"]
    matched = bridge_projections["R182"]
    signal_plan = _bridge_plan(tmp_path, signal)
    plan = _bridge_plan(tmp_path, matched, "R182")
    claim = {
        **subject.preview_bridge(signal_plan, signal),
        "attempt": 3, "project_id": subject._R181_A2_PROJECT_ID,
        "a2_control_sha256": dict(subject._R181_A2_CONTROL_SHA256),
    }
    launch = {
        "candidate_id": "R181", "attempt": 3,
        "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": "run-a3",
        "projection_sha256": signal.projection_sha256,
        "profile_sha256": signal.profile_sha256,
    }
    subject._write_once(subject._control_path(signal_plan, "claim"), claim)
    subject._write_once(subject._control_path(signal_plan, "launch"), launch)
    subject._write_once(subject._control_path(signal_plan, "terminal"), {
        "candidate_id": "R181", "status": "Completed.",
        "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": "run-a3",
    })
    subject._write_once(subject._control_path(signal_plan, "result-read-claim"), {
        "candidate_id": "R181", "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": "run-a3",
    })
    subject._write_once(subject._control_path(signal_plan, "result-valid"), {
        "candidate_id": "R181", "attempt": 3,
        "run_valid": True, "aggregate_sha256": "a" * 64,
        "projection_sha256": signal.projection_sha256,
        "profile_sha256": signal.profile_sha256,
        "project_id": subject._R181_A2_PROJECT_ID,
        "backtest_id": "run-a3",
    })
    calls = _fake_qc(monkeypatch, plan, matched)
    receipt = subject.launch_a1(
        plan, matched, object(),
        owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
    )
    assert receipt["candidate_id"] == "R182"
    assert receipt["owner_launch_waiver_id"] == subject._EXPLORATORY_WAIVER_ID
    assert len(subject._read_control(subject._control_path(plan, "claim"))["source_files"]) == 14
    endpoints = [endpoint for endpoint, _ in calls]
    assert endpoints.count("projects/create") == 1
    assert endpoints.count("backtests/create") == 1
    assert endpoints.count("compile/create") == 1


@pytest.mark.parametrize("candidate,attempt", (
    ("R181", 1), ("R181", 2), ("R183", 1),
))
def test_exploratory_waiver_cannot_replace_unrelated_signed_permits(
    projections, tmp_path, candidate, attempt,
):
    value = projections[candidate]
    plan = _plan(tmp_path, value, candidate)
    if attempt == 2:
        plan = _a2_plan(tmp_path, value)
    with pytest.raises(subject.Cap90QcSubmissionError, match="waiver"):
        subject._launch_authority(
            plan, value, owner_signature=None,
            owner_waiver_id=subject._EXPLORATORY_WAIVER_ID,
        )
