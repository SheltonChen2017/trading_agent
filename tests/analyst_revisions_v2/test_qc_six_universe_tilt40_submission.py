"""Offline exact-identity and one-use controls for the R185 40% tilt."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt40_qc_projection as projector
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap90
from research.analyst_revisions_v2_qc import six_universe_tilt40_submission as subject
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    FORMAL_EXECUTION_PURPOSE,
    OwnerSignatureAuthorityError,
)
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_submission as r184_tests


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
TARGET_PATH_SHA256 = (
    "b825663b4dfdee835f1c118a49fdd49e0a8d37387b8045060d77b5b3bbdcadbc"
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
    return projector.build_accepted_risk_six_universe_order_tilt40_qc_projection(
        package
    )


def _plan(tmp_path, projection):
    return subject.Tilt40QcPlan(
        organization_id="a" * 32,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


def _predecessors(monkeypatch, plan, *, valid=True,
                  target_path=TARGET_PATH_SHA256):
    return r184_tests._predecessors(
        monkeypatch, plan, valid=valid, target_path=target_path,
    )


def _signed(monkeypatch):
    token = object()

    def verify(authority, *, authority_payload):
        if authority is not token:
            raise OwnerSignatureAuthorityError("missing owner signature")
        return SimpleNamespace(
            purpose=FORMAL_EXECUTION_PURPOSE,
            authority_payload_sha256=hashlib.sha256(authority_payload).hexdigest(),
            authority_sha256="a" * 64,
            signature_sha256="b" * 64,
        )

    monkeypatch.setattr(subject, "require_formal_execution_owner_signature", verify)
    return token


def _fake_qc(monkeypatch, plan, projection, *, source_corrupt=False, compile_error=False):
    files = {"main.py": "# default\n", "research.ipynb": "{}"}
    calls = []
    state = {"launched": False, "statistics": None}

    def post(_api, endpoint, payload):
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
            state["launched"] = True
            return {"success": True, "backtest": {
                "projectId": 111, "backtestId": "tilt40-a1",
                "name": plan.backtest_name, "status": "In Queue...",
            }}
        if endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            return {"success": True, "count": 1 if state["launched"] else 0,
                    "backtests": ([{
                        "projectId": 111, "backtestId": "tilt40-a1",
                        "name": plan.backtest_name, "status": "Completed.",
                    }] if state["launched"] else [])}
        if endpoint == "backtests/read":
            assert state["statistics"] is not None
            return {"success": True, "backtest": {
                "projectId": 111, "backtestId": "tilt40-a1",
                "name": plan.backtest_name, "status": "Completed.",
                "statistics": state["statistics"],
                "orders": [{"forbidden": True}],
            }}
        raise AssertionError(endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls, state


def _statistics(plan, launch, *, fraction="0.40", defect=None):
    """Adapt R184's otherwise identical bridge aggregate to R185 lineage."""
    statistics = r184_tests._statistics(plan, launch)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate["schema"] = projector.TILT40_SUMMARY_SCHEMA
    aggregate["matched_baseline_target_path_sha256"] = TARGET_PATH_SHA256
    aggregate["tilt_rank_rule_id"] = projector.TILT40_RANK_RULE_ID
    aggregate["maximum_stock_weight_change_fraction"] = fraction
    if defect == "negative_cash":
        aggregate["minimum_end_day_cash"] = "-1"
    elif defect == "gross":
        aggregate["maximum_gross_exposure"] = "1.01"
    elif defect == "tracking":
        aggregate["execution"]["maximum_target_weight_l1_error"] = "0.06"
    elif defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    aggregate_raw = subject._canonical(aggregate)
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregate_schema"] = projector.TILT40_SUMMARY_SCHEMA
    meta["aggregate_sha256"] = hashlib.sha256(aggregate_raw).hexdigest()
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: aggregate_raw.decode("ascii"),
        "Net Profit": "999%",  # Standard statistics are never retained.
    }


def test_exact_preview_and_signed_payload_bind_r185_identity(projection, tmp_path,
                                                             monkeypatch):
    plan = _plan(tmp_path, projection)
    identity = subject.preview(plan, projection)
    assert identity["candidate_id"] == "R185"
    assert identity["attempt"] == 1
    assert len(identity["source_files"]) == 16
    assert projection.total_source_byte_count == 422_758
    _predecessors(monkeypatch, plan)
    payload_bytes = subject.render_owner_launch_permit(plan, projection)
    payload = json.loads(payload_bytes)
    assert subject._canonical(payload) == payload_bytes
    assert payload["schema"] == subject._LAUNCH_PERMIT_SCHEMA
    assert payload["signature_purpose"] == FORMAL_EXECUTION_PURPOSE
    assert payload["candidate_id"] == "R185"
    assert payload["attempt"] == 1
    assert payload["project_id"] is None
    assert payload["project_name"] == subject._PROJECT_NAME
    assert payload["backtest_name"] == subject._BACKTEST_NAME
    assert payload["projection_sha256"] == subject._PROJECTION_SHA256
    assert payload["profile_sha256"] == subject._PROFILE_SHA256
    assert payload["matched_baseline_target_path_sha256"] == TARGET_PATH_SHA256
    assert payload["mutating_endpoint_budget"]["files/create"] == 16
    assert payload["maximum_backtest_submissions"] == 1
    assert payload["aggregate_only_result_read_authorized"] is True
    assert payload["maximum_result_reads"] == 1
    assert payload["paper_live_deployment_funded_trading_authorized"] is False


@pytest.mark.parametrize("changed", ("project", "run", "role", "attempt", "source"))
def test_changed_plan_or_source_refuses_before_qc_or_claim(
    projection, tmp_path, monkeypatch, changed,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    if changed == "project":
        plan = dataclasses.replace(plan, project_name="other private project")
    elif changed == "run":
        plan = dataclasses.replace(plan, backtest_name="other run")
    elif changed == "role":
        plan = dataclasses.replace(plan, role="matched_revision_tilt")
    elif changed == "attempt":
        plan = dataclasses.replace(plan, attempt=2)
    else:
        source_files = list(projection.source_files)
        item = source_files[0]
        raw = item.source_bytes + b"# altered\n"
        source_files[0] = dataclasses.replace(
            item, source_bytes=raw, byte_count=len(raw),
            content_sha256=hashlib.sha256(raw).hexdigest(),
        )
        projection = dataclasses.replace(
            projection, source_files=tuple(source_files),
            total_source_byte_count=projection.total_source_byte_count + len(b"# altered\n"),
        )
    with pytest.raises(subject.SixUniverseTilt40SubmissionError):
        subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert calls == []
    assert not list(plan.control_directory.glob("R185-A1-claim.json"))


@pytest.mark.parametrize("predecessor", ("absent", "invalid", "missing_path"))
def test_predecessor_gate_refuses_before_qc(
    projection, tmp_path, monkeypatch, predecessor,
):
    plan = _plan(tmp_path, projection)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    if predecessor != "absent":
        _predecessors(
            monkeypatch, plan, valid=predecessor != "invalid",
            target_path=None if predecessor == "missing_path" else TARGET_PATH_SHA256,
        )
    with pytest.raises(subject.SixUniverseTilt40SubmissionError):
        subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_different_well_formed_r182_target_path_refuses_before_qc(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan, target_path="f" * 64)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError,
                       match="preregistered pin"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_signed_launch_is_one_use_and_missing_signature_refuses(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="signature"):
        subject.launch_a1(plan, projection, object())
    assert calls == []
    launch = subject.launch_a1(plan, projection, object(), owner_signature=signature)
    claim = subject._read(subject._control_path(plan, "claim"))
    expected_sha = hashlib.sha256(subject.render_owner_launch_permit(plan, projection)).hexdigest()
    assert claim["owner_signed_payload_sha256"] == expected_sha
    assert launch["owner_signed_payload_sha256"] == expected_sha
    assert launch["project_name"] == subject._PROJECT_NAME
    assert calls.count("backtests/create") == 1
    assert calls.count("compile/create") == 1
    assert subject.poll_status(plan, launch, object()) == "Completed."
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="already claimed"):
        subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert calls.count("backtests/create") == 1


@pytest.mark.parametrize("defect", ("source", "compile"))
def test_upload_mismatch_or_compile_failure_spends_attempt_without_backtest(
    projection, tmp_path, monkeypatch, defect,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(
        monkeypatch, plan, projection,
        source_corrupt=defect == "source", compile_error=defect == "compile",
    )
    signature = _signed(monkeypatch)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError):
        subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert subject._control_path(plan, "claim").exists()
    assert "backtests/create" not in calls


@pytest.mark.parametrize("fraction,defect,accepted", (
    ("0.40", None, True), ("0.20", None, False),
    ("0.40", "negative_cash", False), ("0.40", "gross", False),
    ("0.40", "tracking", False), ("0.40", "invalid_order", False),
))
def test_result_read_binds_40_percent_and_bridge_validity_gates(
    projection, tmp_path, monkeypatch, fraction, defect, accepted,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    launch = subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch, fraction=fraction, defect=defect)
    before = len(calls)
    if accepted:
        result = subject.read_aggregates_once(plan, launch, object())
        assert result["run_valid"] is True
        assert result["aggregates"]["maximum_stock_weight_change_fraction"] == "0.40"
        assert subject._control_path(plan, "result-valid").exists()
    else:
        with pytest.raises(subject.SixUniverseTilt40SubmissionError):
            subject.read_aggregates_once(plan, launch, object())
        assert not subject._control_path(plan, "result-valid").exists()
    assert calls[before:] == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-read-claim").exists()
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())


def test_equal_tampered_signature_digests_refuse_before_result_network_read(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    launch = subject.launch_a1(plan, projection, object(), owner_signature=signature)
    assert subject.poll_status(plan, launch, object()) == "Completed."
    claim_path = subject._control_path(plan, "claim")
    launch_path = subject._control_path(plan, "launch")
    claim = subject._read(claim_path)
    claim["owner_signed_payload_sha256"] = "0" * 64
    claim_path.write_bytes(subject._canonical(claim))
    launch = {**launch, "owner_signed_payload_sha256": "0" * 64}
    launch_path.write_bytes(subject._canonical(launch))
    before = len(calls)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="signature"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == []
    assert not subject._control_path(plan, "result-read-claim").exists()


@pytest.mark.parametrize("authority", ("missing", "wrong", "mixed"))
def test_r185_waiver_refuses_missing_wrong_or_mixed_authority_before_network(
    projection, tmp_path, monkeypatch, authority,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    signature = _signed(monkeypatch)
    kwargs = {
        "missing": {},
        "wrong": {"owner_waiver_id": cap90._R183_BRIDGE_WAIVER_ID},
        "mixed": {
            "owner_waiver_id": subject._WAIVER_ID,
            "owner_signature": signature,
        },
    }[authority]
    with pytest.raises(subject.SixUniverseTilt40SubmissionError):
        subject.launch_a1(plan, projection, object(), **kwargs)
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_r185_exact_waiver_binds_one_use_launch_and_aggregate_read(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    claim = subject._read(subject._control_path(plan, "claim"))
    waived_payload = subject._render_waived_launch_payload(
        plan, subject.preview(plan, projection),
        matched_baseline_target_path_sha256=TARGET_PATH_SHA256,
    )
    scope = json.loads(waived_payload)
    assert subject._canonical(scope) == waived_payload
    assert scope["schema"] == subject._WAIVER_SCHEMA
    assert scope["owner_launch_waiver_id"] == subject._WAIVER_ID
    assert scope["project_name"] == plan.project_name
    assert scope["backtest_name"] == plan.backtest_name
    assert scope["source_files_sha256"] == subject._SOURCE_FILES_SHA256
    assert scope["matched_baseline_target_path_sha256"] == TARGET_PATH_SHA256
    assert scope["aggregate_only_result_read_authorized"] is True
    assert scope["maximum_result_reads"] == 1
    assert scope["paper_live_deployment_funded_trading_authorized"] is False
    permit_sha = hashlib.sha256(waived_payload).hexdigest()
    expected = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": subject._WAIVER_SCHEMA,
        "owner_launch_waiver_id": subject._WAIVER_ID,
        "owner_waived_payload_sha256": permit_sha,
    }
    assert {key: claim[key] for key in expected} == expected
    assert {key: launch[key] for key in expected} == expected
    assert not any(key.startswith("owner_signature") for key in claim)
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert calls.count("backtests/create") == 1
    assert calls.count("backtests/read") == 1
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="already claimed"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )


def test_equal_tampered_waiver_digests_refuse_before_result_network_read(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    claim_path = subject._control_path(plan, "claim")
    launch_path = subject._control_path(plan, "launch")
    claim = subject._read(claim_path)
    claim["owner_waived_payload_sha256"] = "0" * 64
    claim_path.write_bytes(subject._canonical(claim))
    launch = {**launch, "owner_waived_payload_sha256": "0" * 64}
    launch_path.write_bytes(subject._canonical(launch))
    before = len(calls)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="waiver"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == []
    assert not subject._control_path(plan, "result-read-claim").exists()


def test_waiver_claim_rejects_equal_source_manifest_tamper_before_result_read(
    projection, tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    claim_path = subject._control_path(plan, "claim")
    claim = subject._read(claim_path)
    claim["source_files"][0][1] = "0" * 64
    claim["owner_waived_payload_sha256"] = hashlib.sha256(
        subject._render_waived_launch_payload(
            plan, claim, matched_baseline_target_path_sha256=TARGET_PATH_SHA256,
        )
    ).hexdigest()
    claim_path.write_bytes(subject._canonical(claim))
    launch = {**launch, "owner_waived_payload_sha256": claim["owner_waived_payload_sha256"]}
    subject._control_path(plan, "launch").write_bytes(subject._canonical(launch))
    before = len(calls)
    with pytest.raises(subject.SixUniverseTilt40SubmissionError, match="source claim"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == []
