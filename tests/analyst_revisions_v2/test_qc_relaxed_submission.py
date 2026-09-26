"""Focused fake-cloud red/green checks; no credentials, network or outcomes."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as sut


ORG = "a" * 32


def canonical(value):
    return sut.common._canonical(value)


class Projection:
    def __init__(self, raw=b"x = 1\n"):
        digest = hashlib.sha256(raw).hexdigest()
        self.source_files = (SimpleNamespace(project_path="main.py", source_bytes=raw,
            byte_count=len(raw), content_sha256=digest),)
        self.schema = "test-projection-v1"
        self.profile_id, self.profile_sha256 = "test-profile", "b" * 64
        self.package_sha256, self.activation_manifest_sha256 = "c" * 64, "d" * 64
        self.total_source_byte_count = len(raw)
        self.projection_id = "test-projection"
        self.projection_sha256 = sut._sha(self.semantic())

    def semantic(self):
        return {"schema": self.schema, "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256, "package_sha256": self.package_sha256,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "total_source_byte_count": self.total_source_byte_count,
            "source_files": [[item.project_path, item.content_sha256, item.byte_count]
                             for item in self.source_files]}

    def to_record(self):
        return {**self.semantic(), "projection_id": self.projection_id,
                "projection_sha256": self.projection_sha256}


class Fake:
    def __init__(self):
        self.calls, self.files, self.created = [], {}, False
        self.compile_state, self.status = "BuildSuccess", "In Progress..."
        self.collaborators = [{"owner": True}]
        self.statistics = {}

    def post(self, api, endpoint, body):
        self.calls.append((endpoint, body))
        if endpoint == "authenticate":
            return {}
        if endpoint == "projects/create":
            self.created = True
            self.name = body["name"]
            self.files = {"main.py": "default = 1\n", "research.ipynb": "{}"}
            return {"projects": [{"projectId": 123}]}
        if endpoint == "projects/read":
            rows = ([{"projectId": 123, "name": self.name, "organizationId": ORG,
                "language": "Py", "owner": True, "codeRunning": False,
                "collaborators": self.collaborators}] if self.created else [])
            return {"projects": rows}
        if endpoint == "files/read":
            return {"files": [{"projectId": 123, "name": name, "content": raw}
                              for name, raw in self.files.items()]}
        if endpoint == "files/delete":
            del self.files[body["name"]]
            return {}
        if endpoint in {"files/update", "files/create"}:
            self.files[body["name"]] = body["content"]
            return {}
        if endpoint == "compile/create":
            return {"compileId": "compile-1"}
        if endpoint == "compile/read":
            return {"compileId": "compile-1", "state": self.compile_state}
        if endpoint == "backtests/create":
            self.backtest_name = body["backtestName"]
            return {"backtest": {"projectId": 123, "backtestId": "run-1",
                "name": self.backtest_name, "status": self.status}}
        if endpoint == "backtests/list":
            assert body["includeStatistics"] is False
            return {"count": 1, "backtests": [{"projectId": 123,
                "backtestId": "run-1", "name": self.backtest_name, "status": self.status}]}
        if endpoint == "backtests/read":
            return {"backtest": {"projectId": 123, "backtestId": "run-1",
                "name": self.backtest_name, "status": self.status,
                "statistics": self.statistics, "orders": "NOT RETAINED"}}
        raise AssertionError(endpoint)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    projection = Projection()
    row = {"candidate_id": "R209", "project_name": "131 ARV2 TEST COVERAGE",
        "backtest_name": "ARV2 R209 coverage", "kind": "coverage", "role": "coverage",
        "projection_schema": projection.schema, "projection_sha256": projection.projection_sha256,
        "profile_id": projection.profile_id, "profile_sha256": projection.profile_sha256,
        "source_file_count": 1, "total_source_bytes": projection.total_source_byte_count,
        "source_files_sha256": sut._sha(projection.semantic()["source_files"]),
        "statistic_names": ["ARV2_SIX_COVERAGE_META"] + ["ARV2_SIX_COVERAGE_" + ticker for ticker in sut._TICKERS],
        "meta_schema": "test-meta-v1", "sleeve_schema": "test-sleeve-v1", "summary_schema": "test"}
    manifest = {"schema": "test-family-v1", "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "input_control_directory": str(tmp_path), "candidates": [row]}
    path = tmp_path / "manifest.json"
    path.write_bytes(canonical(manifest))
    monkeypatch.setattr(sut, "MANIFEST_PATH", path)
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(sut, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(sut.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(sut.common, "_post", fake.post)
    plan = sut.build_plan("R209", ORG, tmp_path / "control")
    return plan, projection, fake, row


def coverage_stats(row):
    sleeves = [{"schema": row["sleeve_schema"], "universe_id": ticker,
        "totals": {"decision_count": 61}, "years": [{"year": 2025, "decision_count": 22},
            {"year": 2026, "decision_count": 39}]} for ticker in sut._TICKERS]
    meta = {"schema": row["meta_schema"], "profile_id": row["profile_id"],
        "profile_sha256": row["profile_sha256"], "package_sha256": "c" * 64,
        "activation_manifest_sha256": "d" * 64, "decision_count": 61,
        "sleeve_decision_count": 366, "raw_rows_or_identifiers_emitted": False,
        "price_or_return_access": False, "orders": False, "backtest_only": True,
        "sleeve_sha256s": {ticker: sut._sha(sleeve) for ticker, sleeve in zip(sut._TICKERS, sleeves)},
        "aggregate_sha256": sut._sha(sleeves)}
    return {"ARV2_SIX_COVERAGE_META": canonical(meta).decode("ascii"),
        **{"ARV2_SIX_COVERAGE_" + ticker: canonical(sleeve).decode("ascii")
           for ticker, sleeve in zip(sut._TICKERS, sleeves)}}


def test_launch_claim_precedes_first_mutation_and_persists_project(frozen, monkeypatch):
    plan, projection, fake, row = frozen
    real = fake.post
    def checked(api, endpoint, body):
        if endpoint in {"projects/create", "files/delete", "files/create", "files/update", "compile/create", "backtests/create"}:
            assert sut._path(plan, "claim").exists()
        if endpoint in {"files/delete", "files/create", "files/update", "compile/create", "backtests/create"}:
            assert sut._path(plan, "project").exists()
        return real(api, endpoint, body)
    monkeypatch.setattr(sut.common, "_post", checked)
    launch = sut.launch(plan, projection, fake)
    assert launch["project_id"] == 123
    assert fake.files == {"main.py": "x = 1\n"}
    with pytest.raises(sut.RelaxedQcSubmissionError, match="consumed"):
        sut.launch(plan, projection, fake)


@pytest.mark.parametrize("attempt", [0, 4, True])
def test_attempt_bound(frozen, attempt):
    plan, _, _, _ = frozen
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bound"):
        sut._candidate(dataclasses.replace(plan, attempt=attempt))


def test_future_import_fails_before_any_api(frozen, monkeypatch):
    plan, _, fake, row = frozen
    projection = Projection(b"from __future__ import annotations\n")
    family = json.loads(sut.MANIFEST_PATH.read_bytes())
    row = family["candidates"][0]
    row.update(projection_sha256=projection.projection_sha256,
        source_files_sha256=sut._sha(projection.semantic()["source_files"]),
        total_source_bytes=projection.total_source_byte_count)
    sut.MANIFEST_PATH.write_bytes(canonical(family))
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(sut.MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="prelude"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_manifest_corruption_refused(frozen):
    plan, projection, fake, _ = frozen
    sut.MANIFEST_PATH.write_bytes(b"{}")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_compile_failure_spends_slot_and_retry_reuses_project(frozen):
    plan, projection, fake, _ = frozen
    fake.compile_state = "BuildError"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="compile failed"):
        sut.launch(plan, projection, fake)
    assert sut._path(plan, "claim").exists()
    fake.compile_state = "BuildSuccess"
    second = dataclasses.replace(plan, attempt=2)
    launch = sut.launch(second, projection, fake)
    assert launch["project_id"] == 123
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1


def test_nonterminal_retry_refused(frozen):
    plan, projection, fake, _ = frozen
    sut.launch(plan, projection, fake)
    before = len(fake.calls)
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.launch(dataclasses.replace(plan, attempt=2), projection, fake)
    assert len(fake.calls) == before


def test_collaborator_refused_after_atomic_project_receipt(frozen):
    plan, projection, fake, _ = frozen
    fake.collaborators.append({"owner": False})
    with pytest.raises(sut.RelaxedQcSubmissionError, match="private"):
        sut.launch(plan, projection, fake)
    assert sut._path(plan, "project").exists()
    assert not any(endpoint == "compile/create" for endpoint, _ in fake.calls)


def test_result_one_read_bounded_custom_only(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    assert sut.poll_status(plan, launch, fake) == "Completed."
    fake.statistics = {**coverage_stats(row), "Net Profit": "DO NOT RETAIN"}
    result = sut.read_result_once(plan, launch, fake)
    assert result["run_valid"] is True
    assert "Net Profit" not in str(result)
    assert "NOT RETAINED" not in str(result)
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.read_result_once(plan, launch, fake)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


def test_source_changed_refuses_before_outcome_read(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.files["main.py"] += "x = 2\n"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bytes"):
        sut.read_result_once(plan, launch, fake)
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


def test_bad_digest_still_consumes_one_read(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.statistics = coverage_stats(row)
    meta = json.loads(fake.statistics["ARV2_SIX_COVERAGE_META"])
    meta["aggregate_sha256"] = "e" * 64
    fake.statistics["ARV2_SIX_COVERAGE_META"] = canonical(meta).decode("ascii")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="digest"):
        sut.read_result_once(plan, launch, fake)
    assert sut._path(plan, "read-claim").exists()


@pytest.mark.parametrize("value", ["{} ", "[]", "{\"x\":NaN}", "é", " " * 8193])
def test_noncanonical_or_oversized_statistic_refused(value):
    with pytest.raises((sut.RelaxedQcSubmissionError, ValueError)):
        sut._statistic(value)
