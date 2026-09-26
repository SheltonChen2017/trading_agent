"""Offline boundaries for the one-attempt coverage QC path."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.quantconnect import QuantConnectClient, QuantConnectCredentials
from research.analyst_revisions_v2_qc.owner_signature_authority import OwnerSignatureAuthorityError
from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
    accepted_risk_six_universe_coverage_qc_projection as projection_builder,
    accepted_risk_six_universe_coverage_qc_runtime as runtime,
    six_universe_coverage_submission as subject,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
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
    return projection_builder.build_six_universe_coverage_qc_projection(package)


def _plan(tmp_path, projection, attempt=1):
    return subject.CoverageQcPlan(
        candidate_id="COVERAGE_DIAGNOSTIC",
        attempt=attempt,
        project_name=f"103. ARV2_SIX_COVERAGE_A{attempt} - 20260922",
        backtest_name=f"ARV2 coverage diagnostic A{attempt}",
        organization_id="a" * 32,
        projection_sha256=projection.projection_sha256,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        symbol_resolution_sha256="d" * 64,
        control_directory=tmp_path / "private",
    )


def _statistics(plan, projection):
    counts = runtime._counts_record(runtime._empty_counts())
    annual = []
    for year, decisions in zip(runtime.YEARS, (52, 52, 52, 52, 53)):
        row = copy.deepcopy(counts)
        row["decision_count"] = decisions
        annual.append({"year": year, **row})
    total = copy.deepcopy(counts)
    total["decision_count"] = runtime.EXPECTED_DECISION_COUNT
    sleeves = {
        ticker: {
            "schema": runtime.SLEEVE_SCHEMA,
            "universe_id": ticker,
            "totals": copy.deepcopy(total),
            "years": copy.deepcopy(annual),
        }
        for ticker in ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
    }
    meta = {
        "schema": runtime.META_SCHEMA,
        "profile_id": projection.profile_id,
        "profile_sha256": projection.profile_sha256,
        "package_id": "fixture-package",
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "fixture-resolution",
        "symbol_resolution_sha256": plan.symbol_resolution_sha256,
        "decision_count": runtime.EXPECTED_DECISION_COUNT,
        "sleeve_decision_count": runtime.EXPECTED_SLEEVE_DECISION_COUNT,
        "callback_source_row_count": 0,
        "coverage_path_sha256": "e" * 64,
        "sleeve_sha256s": {ticker: subject._sha(row) for ticker, row in sleeves.items()},
        "aggregate_sha256": subject._sha(list(sleeves.values())),
        "raw_rows_or_identifiers_emitted": False,
        "price_or_return_access": False,
        "orders": False,
        "backtest_only": True,
    }
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        **{
            runtime.SLEEVE_STATISTIC_PREFIX + ticker: subject._canonical(row).decode("ascii")
            for ticker, row in sleeves.items()
        },
    }


class FakeQc:
    def __init__(self, plan, projection):
        self.plan = plan
        self.projection = projection
        self.calls = []
        self.files = {"main.py": "# default", "research.ipynb": "{}"}
        self.project = None
        self.status = "Completed."
        self.corrupt_readback = False
        self.statistics = _statistics(plan, projection)
        self.compile_reads = 0
        self.file_modified = "2026-09-23 06:52:43"

    def __call__(self, url, body, headers, timeout):
        assert url.startswith("https://www.quantconnect.com/api/v2/")
        assert headers["Authorization"].startswith("Basic ")
        assert type(timeout) is float and timeout > 0
        endpoint = url.split("/api/v2/", 1)[1]
        payload = json.loads(body)
        self.calls.append((endpoint, payload))
        response = {"success": True}
        if endpoint == "projects/read":
            response["projects"] = [] if self.project is None else [self.project]
        elif endpoint == "projects/create":
            self.project = {
                "projectId": 123, "name": self.plan.project_name,
                "organizationId": self.plan.organization_id,
                "language": "Py", "owner": True, "codeRunning": False,
                "collaborators": [{"owner": True}],
            }
            response["projects"] = [self.project]
        elif endpoint == "files/read":
            response["files"] = [
                {"projectId": 123, "name": name,
                 "content": content + ("CORRUPT" if self.corrupt_readback and name == "main.py" else ""),
                 "modified": self.file_modified}
                for name, content in self.files.items()
            ]
        elif endpoint == "files/delete":
            del self.files[payload["name"]]
        elif endpoint in {"files/create", "files/update"}:
            self.files[payload["name"]] = payload["content"]
        elif endpoint == "compile/create":
            response.update(compileId="compile-1", state="InQueue", projectId=123)
        elif endpoint == "compile/read":
            self.compile_reads += 1
            response.update(compileId="compile-1", state=(
                "InQueue" if self.compile_reads == 1 else "BuildSuccess"
            ))
        elif endpoint == "backtests/create":
            response["backtest"] = {
                "projectId": 123, "backtestId": "backtest-1",
                "name": self.plan.backtest_name, "status": "In Queue...",
            }
        elif endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            response.update(count=1, backtests=[{
                "projectId": 123, "backtestId": "backtest-1",
                "name": self.plan.backtest_name, "status": self.status,
                "created": "2026-09-23 06:52:46", "snapshotId": 987,
                "sharpeRatio": 999,
            }])
        elif endpoint == "backtests/read":
            response["backtest"] = {
                "projectId": 123, "backtestId": "backtest-1",
                "name": self.plan.backtest_name, "status": self.status,
                "snapshotId": 987,
                "statistics": {"Sharpe Ratio": "DO-NOT-RETAIN", **self.statistics},
                "orders": [{"secret": "DO-NOT-RETAIN"}],
                "logs": ["DO-NOT-RETAIN"],
            }
        return 200, subject._canonical(response)


def _client(monkeypatch, fake):
    monkeypatch.setattr(subject, "_default_http_transport", fake)
    return QuantConnectClient(
        QuantConnectCredentials("123", "offline-fixture-token"),
        transport=subject._bounded_transport,
    )


def _allow_owner_signature(monkeypatch, plan, projection):
    """Verify the exact rendered launch bytes without using an owner private key."""
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
            raise OwnerSignatureAuthorityError("wrong signed coverage payload")
        return verified

    monkeypatch.setattr(subject, "require_formal_execution_owner_signature", require)
    return signature, calls


def test_unsigned_coverage_launch_refuses_before_any_qc_or_claim(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    api = _client(monkeypatch, fake)
    with pytest.raises(subject.CoverageQcSubmissionError, match="owner launch signature"):
        subject.prepare_and_launch_once(plan, projection, api)
    assert fake.calls == []
    assert not plan.control_directory.exists()


def test_coverage_permit_binds_exact_attempt_source_and_single_counts_only_run(
    tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    raw = subject.render_owner_launch_permit(plan, projection)
    permit = json.loads(raw)
    assert subject._canonical(permit) == raw
    assert permit["schema"] == subject._LAUNCH_PERMIT_SCHEMA
    assert permit["signature_purpose"] == subject.FORMAL_EXECUTION_PURPOSE
    assert permit["action"] == "one_private_exploratory_coverage_backtest_launch"
    assert permit["candidate_id"] == plan.candidate_id
    assert permit["attempt"] == 1
    assert permit["projection_sha256"] == projection.projection_sha256
    assert permit["profile_sha256"] == projection.profile_sha256
    assert permit["symbol_resolution_sha256"] == plan.symbol_resolution_sha256
    assert permit["maximum_backtest_submissions"] == 1
    assert permit["mutating_endpoint_budget"]["backtests/create"] == 1
    assert permit["result_read_authorized"] is False
    assert permit["prices_returns_orders_authorized"] is False
    assert permit["paper_live_deployment_funded_trading_authorized"] is False
    for changed in (
        dataclasses.replace(plan, attempt=2),
        dataclasses.replace(plan, candidate_id="OTHER_DIAGNOSTIC"),
        dataclasses.replace(plan, project_name=plan.project_name + " changed"),
        dataclasses.replace(plan, backtest_name=plan.backtest_name + " changed"),
        dataclasses.replace(plan, organization_id="b" * 32),
        dataclasses.replace(plan, symbol_resolution_sha256=None),
        dataclasses.replace(plan, control_directory=tmp_path / "another"),
    ):
        assert subject.render_owner_launch_permit(changed, projection) != raw
    assert not plan.control_directory.exists()


def test_coverage_permit_loader_uses_exact_rendered_bytes(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    allowed = tmp_path / "allowed-signers"
    detached = tmp_path / "launch.sig"
    observed = []
    sentinel = object()

    def load(**kwargs):
        observed.append(kwargs)
        return sentinel

    monkeypatch.setattr(subject, "load_formal_execution_owner_signature", load)
    assert subject.load_owner_launch_permit(
        plan, projection, allowed_signers_path=allowed, signature_path=detached,
    ) is sentinel
    assert observed == [{
        "authority_payload": subject.render_owner_launch_permit(plan, projection),
        "allowed_signers_path": allowed, "signature_path": detached,
    }]


def test_coverage_wrong_signed_scope_refuses_before_any_qc_or_claim(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    api = _client(monkeypatch, fake)
    signature, checks = _allow_owner_signature(monkeypatch, plan, projection)
    changed = dataclasses.replace(plan, backtest_name=plan.backtest_name + " changed")
    with pytest.raises(subject.CoverageQcSubmissionError, match="owner launch signature"):
        subject.prepare_and_launch_once(
            changed, projection, api, owner_signature=signature,
        )
    assert len(checks) == 1
    assert fake.calls == []
    assert not plan.control_directory.exists()


def test_preview_is_local_bounded_and_omits_organization(tmp_path, projection):
    plan = _plan(tmp_path, projection)
    preview = subject.preview_plan(plan, projection)
    assert preview["quantconnect_io_performed"] is False
    assert preview["projection_sha256"] == projection.projection_sha256
    assert len(preview["source_files"]) == 9
    assert "organization_id" not in preview
    assert plan.organization_id not in repr(plan)
    assert not plan.control_directory.exists()


def test_launch_and_count_read_are_one_use_and_ignore_unrelated_results(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    api = _client(monkeypatch, fake)
    monkeypatch.setattr(subject.time, "sleep", lambda _: None)
    signature, checks = _allow_owner_signature(monkeypatch, plan, projection)
    launch = subject.prepare_and_launch_once(
        plan, projection, api, owner_signature=signature,
    )
    assert len(checks) == 1
    assert launch["owner_signature_sha256"] == "b" * 64
    assert launch["owner_signed_payload_sha256"] == hashlib.sha256(
        subject.render_owner_launch_permit(plan, projection)
    ).hexdigest()
    claim = subject._read_control(subject._path(plan, "claim"))
    assert claim["owner_signature_sha256"] == "b" * 64
    assert fake.compile_reads == 2
    assert sum(path == "backtests/create" for path, _ in fake.calls) == 1
    assert len(fake.files) == 9
    prior_calls = len(fake.calls)
    with pytest.raises(subject.CoverageQcSubmissionError, match="already exists"):
        subject.prepare_and_launch_once(
            plan, projection, api, owner_signature=signature,
        )
    assert len(fake.calls) == prior_calls
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    counts = subject.read_counts_once(plan, launch, api)
    assert set(counts["sleeves"]) == {"SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"}
    assert counts["sleeves"]["SPY"]["totals"]["decision_count"] == 261
    assert "DO-NOT-RETAIN" not in repr(counts)
    prior_calls = len(fake.calls)
    with pytest.raises(subject.CoverageQcSubmissionError, match="already spent"):
        subject.read_counts_once(plan, launch, api)
    assert len(fake.calls) == prior_calls


def test_existing_unsigned_coverage_receipt_remains_readable(
    monkeypatch, tmp_path, projection,
):
    """The new launch gate does not erase an already completed R180 receipt."""
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    api = _client(monkeypatch, fake)
    legacy_launch = {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": 123, "project_name": plan.project_name,
        "compile_id": "compile-1", "backtest_id": "backtest-1",
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": projection.profile_id,
        "profile_sha256": projection.profile_sha256,
    }
    subject._write_once(subject._path(plan, "launch"), legacy_launch)
    assert subject.poll_status_once(plan, legacy_launch, api) == "Completed."
    result = subject.read_counts_once(plan, legacy_launch, api)
    assert result["sleeves"]["SPY"]["totals"]["decision_count"] == 261
    assert not any(name in legacy_launch for name in (
        "owner_signature_sha256", "owner_signed_payload_sha256",
    ))


def test_source_readback_change_stops_before_compile(monkeypatch, tmp_path, projection):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    fake.corrupt_readback = True
    api = _client(monkeypatch, fake)
    signature, _ = _allow_owner_signature(monkeypatch, plan, projection)
    with pytest.raises(subject.CoverageQcSubmissionError, match="readback bytes"):
        subject.prepare_and_launch_once(
            plan, projection, api, owner_signature=signature,
        )
    assert not any(path == "compile/create" for path, _ in fake.calls)
    assert (plan.control_directory / "COVERAGE_DIAGNOSTIC-A1-claim.json").exists()


def test_mia_completed_import_reads_only_counts_once_after_source_attestation(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    fake.project = {
        "projectId": 123, "name": plan.project_name,
        "organizationId": plan.organization_id, "language": "Py",
        "owner": True, "collaborators": [{"owner": True}],
    }
    fake.files = {
        item.project_path: item.source_bytes.decode("ascii")
        for item in projection.source_files
    }
    api = _client(monkeypatch, fake)
    result = subject.read_imported_counts_once(
        plan, projection, project_id=123, backtest_id="backtest-1",
        snapshot_id=987, api=api,
    )
    assert result["sleeves"]["SPY"]["totals"]["decision_count"] == 261
    assert "DO-NOT-RETAIN" not in repr(result)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    with pytest.raises(subject.CoverageQcSubmissionError, match="already spent"):
        subject.read_imported_counts_once(
            plan, projection, project_id=123, backtest_id="backtest-1",
            snapshot_id=987, api=api,
        )
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


@pytest.mark.parametrize("defect", ["source", "late_source"])
def test_mia_completed_import_refuses_unproven_source_before_result_read(
    monkeypatch, tmp_path, projection, defect,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    fake.project = {
        "projectId": 123, "name": plan.project_name,
        "organizationId": plan.organization_id, "language": "Py",
        "owner": True, "collaborators": [{"owner": True}],
    }
    fake.files = {
        item.project_path: item.source_bytes.decode("ascii")
        for item in projection.source_files
    }
    if defect == "source":
        fake.files["main.py"] += "# changed\n"
    else:
        fake.file_modified = "2026-09-23 06:52:47"
    api = _client(monkeypatch, fake)
    with pytest.raises(subject.CoverageQcSubmissionError, match="source"):
        subject.read_imported_counts_once(
            plan, projection, project_id=123, backtest_id="backtest-1",
            snapshot_id=987, api=api,
        )
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


def test_mia_import_refuses_unpinned_prior_source_time_after_identical_resave(
    monkeypatch, tmp_path, projection,
):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    fake.project = {
        "projectId": 123, "name": plan.project_name,
        "organizationId": plan.organization_id, "language": "Py",
        "owner": True, "collaborators": [{"owner": True}],
    }
    fake.files = {
        item.project_path: item.source_bytes.decode("ascii")
        for item in projection.source_files
    }
    fake.file_modified = "2026-09-23 07:24:38"
    api = _client(monkeypatch, fake)
    with pytest.raises(
        subject.CoverageQcSubmissionError,
        match="pinned prior attestation",
    ):
        subject.read_imported_counts_once(
            plan, projection, project_id=123, backtest_id="backtest-1",
            snapshot_id=987, api=api,
            prior_source_modified_at="2026-09-23 06:52:43",
        )
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


def test_only_the_committed_r180_prior_source_observation_is_recognized():
    identity = (
        "R180_MIA_RECONCILED_COUNTS",
        "3d91e1c9c6138a9642154bf1e96124933e5c9c934f538d31413b77a1d0e76876",
        36854638,
        "2af50aacf72be8725f537d2a40740533",
        36856156,
        "2026-09-23 06:52:43",
    )
    assert subject._has_pinned_prior_source_attestation(*identity)
    for index, changed in enumerate((
        "ANOTHER_CANDIDATE", "a" * 64, 36854639,
        "another-backtest", 36856157, "2026-09-23 06:52:42",
    )):
        corrupted = list(identity)
        corrupted[index] = changed
        assert not subject._has_pinned_prior_source_attestation(*corrupted)


def test_unknown_custom_statistic_is_refused_after_one_read(monkeypatch, tmp_path, projection):
    plan = _plan(tmp_path, projection)
    fake = FakeQc(plan, projection)
    fake.statistics["ARV2_SIX_COVERAGE_RAW"] = "secret"
    api = _client(monkeypatch, fake)
    monkeypatch.setattr(subject.time, "sleep", lambda _: None)
    signature, _ = _allow_owner_signature(monkeypatch, plan, projection)
    launch = subject.prepare_and_launch_once(
        plan, projection, api, owner_signature=signature,
    )
    subject.poll_status_once(plan, launch, api)
    with pytest.raises(subject.CoverageQcSubmissionError, match="inventory"):
        subject.read_counts_once(plan, launch, api)
    assert sum(path == "backtests/read" for path, _ in fake.calls) == 1


def test_fourth_attempt_refuses_in_local_preview(tmp_path, projection):
    plan = _plan(tmp_path, projection, attempt=4)
    with pytest.raises(subject.CoverageQcSubmissionError, match="plan identity"):
        subject.preview_plan(plan, projection)


def test_qc_computed_resolution_digest_is_not_invented_before_run(
    monkeypatch, tmp_path, projection,
):
    plan = dataclasses.replace(
        _plan(tmp_path, projection), symbol_resolution_sha256=None
    )
    fake = FakeQc(plan, projection)
    meta = json.loads(fake.statistics[runtime.META_STATISTIC_NAME])
    meta["symbol_resolution_sha256"] = "d" * 64
    fake.statistics[runtime.META_STATISTIC_NAME] = subject._canonical(meta).decode("ascii")
    api = _client(monkeypatch, fake)
    monkeypatch.setattr(subject.time, "sleep", lambda _: None)
    assert subject.preview_plan(plan, projection)["quantconnect_io_performed"] is False
    signature, _ = _allow_owner_signature(monkeypatch, plan, projection)
    launch = subject.prepare_and_launch_once(
        plan, projection, api, owner_signature=signature,
    )
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    assert subject.read_counts_once(plan, launch, api)["meta"]["symbol_resolution_sha256"] == "d" * 64


def test_redirect_status_and_oversize_response_are_refused(monkeypatch):
    monkeypatch.setattr(subject, "_default_http_transport", lambda *_: (302, b'{"success":true}'))
    with pytest.raises(subject.CoverageQcSubmissionError, match="status or byte bound"):
        subject._bounded_transport("https://www.quantconnect.com/api/v2/authenticate", b"{}", {}, 1.0)
    monkeypatch.setattr(
        subject, "_default_http_transport",
        lambda *_: (200, b"x" * (subject.MAX_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(subject.CoverageQcSubmissionError, match="status or byte bound"):
        subject._bounded_transport("https://www.quantconnect.com/api/v2/authenticate", b"{}", {}, 1.0)
