"""Focused offline launch/receipt controls for one R186 80% tilt look."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt80_qc_projection as projector
from research.analyst_revisions_v2_qc import six_universe_tilt40_submission as prior_submission
from research.analyst_revisions_v2_qc import six_universe_tilt80_submission as subject
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    FORMAL_EXECUTION_PURPOSE,
    OwnerSignatureAuthorityError,
)
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt40_submission as r185_tests


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
TARGET_PATH_SHA256 = r185_tests.TARGET_PATH_SHA256


@pytest.fixture(scope="module")
def projection():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return projector.build_accepted_risk_six_universe_order_tilt80_qc_projection(
        package
    )


def _plan(tmp_path, projection):
    return subject.Tilt80QcPlan(
        organization_id="a" * 32,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


def _predecessors(monkeypatch, plan, *, target_path=TARGET_PATH_SHA256):
    r185_tests._predecessors(monkeypatch, plan, target_path=target_path)


def _fake_qc(monkeypatch, plan, projection, **kwargs):
    # Reuse the unchanged QC envelope fixture, but route its monkeypatches to
    # this candidate. R186's own launch/read gates are never monkeypatched.
    monkeypatch.setattr(r185_tests, "subject", subject)
    return r185_tests._fake_qc(monkeypatch, plan, projection, **kwargs)


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


def _statistics(plan, launch, *, fraction="0.80", defect=None):
    values = r185_tests._statistics(
        plan, launch, fraction="0.40", defect=defect,
    )
    aggregate = json.loads(values[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate["schema"] = projector.TILT80_SUMMARY_SCHEMA
    aggregate["maximum_stock_weight_change_fraction"] = fraction
    aggregate_raw = subject._canonical(aggregate)
    meta = json.loads(values[runtime.META_STATISTIC_NAME])
    meta["aggregate_schema"] = projector.TILT80_SUMMARY_SCHEMA
    meta["aggregate_sha256"] = hashlib.sha256(aggregate_raw).hexdigest()
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: aggregate_raw.decode("ascii"),
        "Net Profit": "999%",  # Standard QC statistics are not retained.
    }


def test_exact_r186_preview_and_one_use_signed_scope(projection, tmp_path,
                                                    monkeypatch):
    plan = _plan(tmp_path, projection)
    identity = subject.preview(plan, projection)
    assert identity["candidate_id"] == "R186"
    assert identity["attempt"] == 1
    assert len(identity["source_files"]) == 16
    assert projection.total_source_byte_count == subject._TOTAL_SOURCE_BYTES
    _predecessors(monkeypatch, plan)
    payload = json.loads(subject.render_owner_launch_permit(plan, projection))
    assert payload["project_name"] == subject._PROJECT_NAME
    assert payload["backtest_name"] == subject._BACKTEST_NAME
    assert payload["source_files_sha256"] == subject._SOURCE_FILES_SHA256
    assert payload["matched_baseline_target_path_sha256"] == TARGET_PATH_SHA256
    assert payload["maximum_backtest_submissions"] == 1
    assert payload["maximum_result_reads"] == 1
    assert payload["raw_logs_orders_charts_authorized"] is False
    assert payload["paper_live_deployment_funded_trading_authorized"] is False


@pytest.mark.parametrize("change", ("project", "source", "profile", "predecessor"))
def test_changed_identity_or_predecessor_refuses_before_network(
    projection, tmp_path, monkeypatch, change,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan,
                  target_path="f" * 64 if change == "predecessor" else TARGET_PATH_SHA256)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    if change == "project":
        plan = dataclasses.replace(plan, project_name="another project")
    elif change == "profile":
        projection = dataclasses.replace(projection, profile_sha256="f" * 64)
    elif change == "source":
        item = projection.source_files[0]
        raw = item.source_bytes + b"# altered\n"
        files = list(projection.source_files)
        files[0] = dataclasses.replace(
            item, source_bytes=raw, byte_count=len(raw),
            content_sha256=hashlib.sha256(raw).hexdigest(),
        )
        projection = dataclasses.replace(
            projection, source_files=tuple(files),
            total_source_byte_count=projection.total_source_byte_count + len(b"# altered\n"),
        )
    with pytest.raises(subject.SixUniverseTilt80SubmissionError):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


@pytest.mark.parametrize("authority", ("missing", "wrong", "mixed"))
def test_waiver_requires_distinct_exact_r186_authority(
    projection, tmp_path, monkeypatch, authority,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    token = _signed(monkeypatch)
    kwargs = {
        "missing": {},
        "wrong": {"owner_waiver_id": prior_submission._WAIVER_ID},
        "mixed": {"owner_waiver_id": subject._WAIVER_ID, "owner_signature": token},
    }[authority]
    with pytest.raises(subject.SixUniverseTilt80SubmissionError):
        subject.launch_a1(plan, projection, object(), **kwargs)
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


def test_waived_a1_launch_and_single_aggregate_read(projection, tmp_path,
                                                    monkeypatch):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    assert launch["candidate_id"] == "R186"
    assert launch["owner_launch_waiver_id"] == subject._WAIVER_ID
    assert calls.count("backtests/create") == 1
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    before = len(calls)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["aggregates"]["maximum_stock_weight_change_fraction"] == "0.80"
    assert set(result) == {"meta", "aggregates", "run_valid"}
    assert calls[before:] == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-valid").exists()
    with pytest.raises(subject.SixUniverseTilt80SubmissionError, match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())
    with pytest.raises(subject.SixUniverseTilt80SubmissionError, match="already claimed"):
        subject.launch_a1(
            plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
        )


@pytest.mark.parametrize("fraction,defect", (
    ("0.40", None), ("0.81", None),
    ("0.80", "negative_cash"), ("0.80", "invalid_order"),
))
def test_result_reader_rejects_non_80_percent_or_invalid_aggregate(
    projection, tmp_path, monkeypatch, fraction, defect,
):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(), owner_waiver_id=subject._WAIVER_ID,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(
        plan, launch, fraction=fraction, defect=defect,
    )
    before = len(calls)
    with pytest.raises(subject.SixUniverseTilt80SubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == ["files/read", "backtests/read"]
    assert not subject._control_path(plan, "result-valid").exists()


def test_signed_route_remains_available(projection, tmp_path, monkeypatch):
    plan = _plan(tmp_path, projection)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    token = _signed(monkeypatch)
    launch = subject.launch_a1(plan, projection, object(), owner_signature=token)
    assert launch["owner_signed_payload_sha256"] == hashlib.sha256(
        subject.render_owner_launch_permit(plan, projection)
    ).hexdigest()
    assert "owner_launch_waiver_id" not in launch
    assert calls.count("backtests/create") == 1
