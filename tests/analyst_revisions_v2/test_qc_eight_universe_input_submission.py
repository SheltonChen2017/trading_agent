"""Fake-cloud R267 tests: source attestation and one-use count-only result read."""

import hashlib
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_eight_universe_input_qc_projection as projection
from research.analyst_revisions_v2_qc import accepted_risk_eight_universe_input_qc_runtime as runtime
from research.analyst_revisions_v2_qc import eight_universe_input_submission as subject


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def projected():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local private delta package is unavailable")
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return projection.build_eight_universe_input_qc_projection(package)


def _statistics(value):
    sleeves = []
    statistics = {}
    for ticker in runtime.UNIVERSE_IDS:
        total = runtime._six._counts_record(runtime._empty_counts())
        total["decision_count"] = 261
        total["constituent_callback_age_bins"]["missing"] = 261
        years = []
        for year, count in zip(runtime.YEARS, (52, 52, 52, 52, 53)):
            annual = runtime._six._counts_record(runtime._empty_counts())
            annual["decision_count"] = count
            annual["constituent_callback_age_bins"]["missing"] = count
            years.append({"year": year, **annual})
        sleeve = {
            "schema": runtime.SLEEVE_SCHEMA, "universe_id": ticker,
            "totals": total, "years": years,
        }
        sleeves.append(sleeve)
        statistics[runtime.SLEEVE_STATISTIC_PREFIX + ticker] = subject._canonical(sleeve).decode("ascii")
    overlap_total = runtime._empty_overlap()
    overlap_total["decision_count"] = 261
    overlap_years = []
    for year, count in zip(runtime.YEARS, (52, 52, 52, 52, 53)):
        annual = runtime._empty_overlap()
        annual["decision_count"] = count
        overlap_years.append({"year": year, **annual})
    overlap = {"schema": runtime.OVERLAP_SCHEMA, "totals": overlap_total, "years": overlap_years}
    statistics[runtime.OVERLAP_STATISTIC_NAME] = subject._canonical(overlap).decode("ascii")
    meta = {
        "schema": runtime.META_SCHEMA,
        "profile_id": runtime._PROFILE["profile_id"],
        "profile_sha256": value.profile_sha256,
        "package_id": value.package_id,
        "package_sha256": value.package_sha256,
        "activation_manifest_sha256": value.activation_manifest_sha256,
        "symbol_resolution_id": "resolution",
        "symbol_resolution_sha256": "c" * 64,
        "decision_count": 261,
        "sleeve_decision_count": 2088,
        "callback_source_row_count": 0,
        "input_path_sha256": hashlib.sha256(b"").hexdigest(),
        "sleeve_sha256s": {
            ticker: subject._sha(sleeve)
            for ticker, sleeve in zip(runtime.UNIVERSE_IDS, sleeves)
        },
        "overlap_sha256": subject._sha(overlap),
        "aggregate_sha256": subject._sha(sleeves + [overlap]),
        "raw_rows_or_identifiers_emitted": False,
        "price_or_return_access": False,
        "orders": False,
        "backtest_only": True,
    }
    statistics[runtime.META_STATISTIC_NAME] = subject._canonical(meta).decode("ascii")
    return statistics


class FakeCloud:
    def __init__(self, value):
        self.value = value
        self.files = {"main.py": "# default"}
        self.calls = []
        self.corrupt_readback = False
        self.project_created = False
        self.backtest_creates = 0
        self.statistics = _statistics(value)

    def post(self, api, endpoint, payload):
        self.calls.append(endpoint)
        project = {
            "projectId": 42, "name": projection.PROJECT_NAME,
            "organizationId": "a" * 32, "language": "Py",
            "owner": True, "codeRunning": False,
            "collaborators": [{"owner": True}],
        }
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            return {"success": True, "projects": [project] if payload or self.project_created else []}
        if endpoint == "projects/create":
            self.project_created = True
            return {"success": True, "projects": [project]}
        if endpoint == "files/read":
            items = [{"projectId": 42, "name": path, "content": content}
                     for path, content in self.files.items()]
            if self.corrupt_readback and len(items) == 10:
                items[0]["content"] += "# corrupted"
            return {"success": True, "files": items}
        if endpoint in {"files/create", "files/update"}:
            self.files[payload["name"]] = payload["content"]
            return {"success": True}
        if endpoint == "files/delete":
            self.files.pop(payload["name"])
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-1"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "compile-1", "state": "BuildSuccess"}
        if endpoint == "backtests/create":
            self.backtest_creates += 1
            return {"success": True, "backtest": {
                "backtestId": f"backtest-{self.backtest_creates}", "projectId": 42,
                "name": payload["backtestName"], "status": "In Queue...",
            }}
        if endpoint == "backtests/list":
            return {"success": True, "count": 1, "backtests": [{
                "backtestId": "backtest-1", "projectId": 42,
                "name": "ARV2 R267 eight-universe input readiness 2021-2025",
                "status": "Completed.",
            }]}
        if endpoint == "backtests/read":
            return {"success": True, "backtest": {
                "projectId": 42, "backtestId": "backtest-1",
                "name": "ARV2 R267 eight-universe input readiness 2021-2025",
                "status": "Completed.", "statistics": self.statistics,
                "orders": [{"raw": "must never be retained"}],
                "charts": {"equity": "must never be retained"},
            }}
        raise AssertionError(endpoint)


def test_preview_freezes_private_three_attempt_non_order_identity(projected, tmp_path):
    plan = subject.build_plan("a" * 32, tmp_path)
    identity = subject.preview(plan, projected)
    assert identity["quantconnect_io_performed"] is False
    assert identity["maximum_attempts"] == 3
    assert identity["source_file_count"] == 10
    with pytest.raises(subject.EightInputQcSubmissionError, match="destination or attempt"):
        subject.build_plan("a" * 32, tmp_path, 4)


def test_fake_cloud_launch_attests_every_file_then_reads_counts_once(projected, tmp_path, monkeypatch):
    fake = FakeCloud(projected)
    monkeypatch.setattr(subject.common, "_client", lambda _: None)
    monkeypatch.setattr(subject, "_post", fake.post)
    plan = subject.build_plan("a" * 32, tmp_path)
    receipt = subject.launch(plan, projected, object())
    assert receipt["project_id"] == 42
    assert len(fake.files) == 10
    assert "compile/create" in fake.calls and "backtests/create" in fake.calls
    assert subject.poll_status(plan, receipt, object()) == "Completed."
    result = subject.read_counts_once(plan, receipt, object())
    assert result["meta"]["decision_count"] == 261
    assert set(result) == {"meta", "sleeves", "overlap"}
    assert "must never be retained" not in str(result)
    assert result["overlap"]["totals"]["decision_count"] == 261
    assert fake.calls.count("backtests/read") == 1
    with pytest.raises(subject.common.CoverageQcSubmissionError, match="one-use"):
        subject.read_counts_once(plan, receipt, object())
    assert fake.calls.count("backtests/read") == 1


def test_source_readback_mutation_consumes_attempt_before_compile(projected, tmp_path, monkeypatch):
    fake = FakeCloud(projected)
    fake.corrupt_readback = True
    monkeypatch.setattr(subject.common, "_client", lambda _: None)
    monkeypatch.setattr(subject, "_post", fake.post)
    plan = subject.build_plan("a" * 32, tmp_path)
    with pytest.raises(subject.EightInputQcSubmissionError, match="source readback bytes"):
        subject.launch(plan, projected, object())
    assert subject._path(plan, "claim").exists()
    assert "compile/create" not in fake.calls
    with pytest.raises(subject.EightInputQcSubmissionError, match="project name is not fresh"):
        subject.launch(plan, projected, object())


def test_retry_reuses_exact_project_only_after_terminal_failure(projected, tmp_path, monkeypatch):
    fake = FakeCloud(projected)
    monkeypatch.setattr(subject.common, "_client", lambda _: None)
    monkeypatch.setattr(subject, "_post", fake.post)
    first = subject.build_plan("a" * 32, tmp_path, 1)
    first_receipt = subject.launch(first, projected, object())
    assert first_receipt["backtest_id"] == "backtest-1"
    second = subject.build_plan("a" * 32, tmp_path, 2)
    assert second.project_name == first.project_name
    with pytest.raises(subject.EightInputQcSubmissionError, match="unresolved"):
        subject.launch(second, projected, object())
    subject.common._write_once(subject._path(first, "terminal"), {
        "candidate_id": "R267", "attempt": 1,
        "project_id": 42, "backtest_id": "backtest-1",
        "status": "Runtime Error",
    })
    second_receipt = subject.launch(second, projected, object())
    assert second_receipt["backtest_id"] == "backtest-2"
    assert second_receipt["project_id"] == first_receipt["project_id"] == 42
    assert fake.calls.count("projects/create") == 1
    assert fake.calls.count("backtests/create") == 2
    assert fake.calls.count("files/create") == 9


def test_result_parser_refuses_extra_custom_stat_and_digest_mutation(projected, tmp_path):
    plan = subject.build_plan("a" * 32, tmp_path)
    receipt = {
        "project_id": 42, "backtest_id": "backtest-1",
        "backtest_name": "ARV2 R267 eight-universe input readiness 2021-2025",
    }
    fake = FakeCloud(projected)
    value = fake.post(None, "backtests/read", {})
    value["backtest"]["statistics"]["ARV2_EIGHT_INPUT_RAW"] = "secret"
    with pytest.raises(subject.EightInputQcSubmissionError, match="inventory"):
        subject.parse_counts_response(value, plan, receipt)
    del value["backtest"]["statistics"]["ARV2_EIGHT_INPUT_RAW"]
    value["backtest"]["statistics"][runtime.SLEEVE_STATISTIC_PREFIX + "XLI"] += " "
    with pytest.raises(subject.EightInputQcSubmissionError, match="canonical"):
        subject.parse_counts_response(value, plan, receipt)
