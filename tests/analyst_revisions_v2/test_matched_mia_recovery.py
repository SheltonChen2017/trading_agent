"""Recovery-reader proofs on fake QC; no credentials, launches or research look."""

import copy
import dataclasses
import hashlib

import pytest

from research.analyst_revisions_v2_qc import matched_mia_recovery as sut
from tests.analyst_revisions_v2.test_qc_matched_study_submission import (
    manifest_fixture, order_statistics,
)
from tests.analyst_revisions_v2.test_qc_relaxed_submission import ORG


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    manifest, _ = manifest_fixture()
    candidate = manifest["candidates"][0]
    monkeypatch.setattr(sut.adapter, "_candidate", lambda plan: candidate)
    monkeypatch.setattr(sut.adapter, "_receipt", lambda plan, receipt: receipt)
    monkeypatch.setattr(sut.common, "_client", lambda api: None)
    plan = sut.adapter.RelaxedQcPlan("R225", ORG, tmp_path / "control", 3, "matched_study")
    files = {"main.py": "repaired = 1\n", **{
        f"fixture_{index:02d}.py": f"value = {index}\n" for index in range(16)}}
    inventory = sorted([name, hashlib.sha256(text.encode("ascii")).hexdigest(), len(text)]
        for name, text in files.items())
    baseline = copy.deepcopy(inventory)
    next(row for row in baseline if row[0] == "main.py")[1:] = ["a" * 64, 6]
    originals = {}
    for slot in range(1, 4):
        prior = dataclasses.replace(plan, attempt=slot)
        run = sut.FAILED_A3_ID if slot == 3 else f"failed-{slot}"
        launch = {"project_id": sut.PROJECT_ID, "backtest_id": run, "source_files": baseline}
        terminal = {"candidate_id": "R225", "attempt": slot, "project_id": sut.PROJECT_ID,
            "backtest_id": run, "status": "Runtime Error"}
        for suffix, value in (("launch", launch), ("terminal", terminal)):
            path = sut.adapter._path(prior, suffix)
            sut.common._write(path, value)
            originals[path] = path.read_bytes()
    evidence = {"schema": sut.SCHEMA, "candidate_id": "R225", "project_id": sut.PROJECT_ID,
        "backtest_id": "mia-independent-run", "backtest_name": "Mia R225 fee recovery",
        "snapshot_id": 100, "created": "2026-09-26T12:01:00",
        "source_attested_at": "2026-09-26T12:00:00", "source_files": inventory}
    run = {"projectId": sut.PROJECT_ID, "backtestId": evidence["backtest_id"],
        "name": evidence["backtest_name"], "snapshotId": 100,
        "created": evidence["created"], "status": "Completed."}
    api = {"calls": [], "project": {"projectId": sut.PROJECT_ID,
        "name": candidate["project_name"], "organizationId": ORG, "language": "Py",
        "owner": True, "codeRunning": False, "collaborators": [{"owner": True}]},
        "files": [{"projectId": sut.PROJECT_ID, "name": name, "content": text,
            "modified": "2026-09-26T11:59:00"} for name, text in files.items()],
        "listed": copy.deepcopy(run), "outcome": {**run,
            "statistics": {**order_statistics(candidate), "Net Profit": "IGNORE"},
            "orders": "DO NOT RETAIN", "logs": "DO NOT RETAIN"}}
    def post(client, endpoint, payload):
        assert client is api
        api["calls"].append((endpoint, payload))
        if endpoint == "projects/read":
            return {"projects": [api["project"]]}
        if endpoint == "files/read":
            return {"files": api["files"]}
        if endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            return {"count": 1, "backtests": [api["listed"]]}
        if endpoint == "backtests/read":
            assert sut._path(plan, "read-claim").exists()
            return {"backtest": api["outcome"]}
        raise AssertionError("Forbidden QC endpoint: " + endpoint)
    monkeypatch.setattr(sut.common, "_post", post)
    return plan, evidence, api, originals


def read(recovery):
    plan, evidence, api, _ = recovery
    return sut.read_result_once(plan, evidence, sut.adapter._sha(evidence), api)


def test_valid_import_keeps_failed_attempts_unchanged_and_reads_only_custom_stats(recovery):
    plan, evidence, api, originals = recovery
    result = read(recovery)
    assert result["run_valid"] is True
    assert [endpoint for endpoint, _ in api["calls"]] == [
        "projects/read", "files/read", "backtests/list", "backtests/read"]
    raw = sut.adapter._read_artifact(sut._path(plan, "raw-custom"))
    assert set(raw["statistics"]) == set(sut.adapter._candidate(plan)["statistic_names"])
    assert "orders" not in raw and "logs" not in raw
    assert raw["origin"] == "independent_Mia_recovery"
    assert all(path.read_bytes() == data for path, data in originals.items())
    count = len(api["calls"])
    assert sut.authenticated_cached_result(plan, evidence, sut.adapter._sha(evidence)) == result
    assert len(api["calls"]) == count
    with pytest.raises(ValueError, match="spent|unavailable"):
        read(recovery)
    assert sum(endpoint == "backtests/read" for endpoint, _ in api["calls"]) == 1


@pytest.mark.parametrize("field,value", [
    ("project_id", 123), ("candidate_id", "R226"),
    ("backtest_id", sut.FAILED_A3_ID), ("snapshot_id", True),
    ("source_attested_at", "2026-09-26T12:02:00"),
    ("created", "2026-09-26T12:01:00Z"), ("backtest_name", ""),
])
def test_recovery_refuses_wrong_or_relabelled_frozen_identity(recovery, field, value):
    recovery[1][field] = value
    with pytest.raises(ValueError):
        read(recovery)
    assert recovery[2]["calls"] == []


def test_changed_evidence_digest_refused_before_qc(recovery):
    plan, evidence, api, _ = recovery
    digest = sut.adapter._sha(evidence)
    evidence["backtest_name"] += "changed"
    with pytest.raises(ValueError, match="frozen identity"):
        sut.read_result_once(plan, evidence, digest, api)
    assert api["calls"] == []


def test_read_response_may_omit_snapshot_and_created_already_pinned_by_listing(recovery):
    recovery[2]["outcome"].pop("snapshotId")
    recovery[2]["outcome"].pop("created")
    assert read(recovery)["run_valid"] is True


@pytest.mark.parametrize("field", ["snapshotId", "created"])
def test_listing_must_pin_snapshot_and_created_even_when_outcome_omits_them(recovery, field):
    recovery[2]["listed"].pop(field)
    recovery[2]["outcome"].pop(field)
    with pytest.raises(ValueError, match="terminal run identity"):
        read(recovery)
    assert not sut._path(recovery[0], "read-claim").exists()


@pytest.mark.parametrize("change", [{"attempt": 4}, {"attempt": 2},
    {"candidate_id": "R226"}, {"family": "relaxed"}])
def test_reader_never_accepts_a_fourth_or_another_candidate_attempt(recovery, change):
    plan, evidence, api, _ = recovery
    with pytest.raises(ValueError, match="exhausted R225 A3"):
        sut.read_result_once(dataclasses.replace(plan, **change), evidence,
            sut.adapter._sha(evidence), api)
    assert api["calls"] == []


@pytest.mark.parametrize("defect", ["extra", "duplicate", "other_module", "main_unchanged"])
def test_source_attestation_requires_seventeen_paths_and_only_main_changed(recovery, defect):
    source = recovery[1]["source_files"]
    if defect == "extra":
        source.append(["extra.py", "b" * 64, 1])
    elif defect == "duplicate":
        source[1] = source[0]
    elif defect == "other_module":
        source[0][1] = "c" * 64
    else:
        next(row for row in source if row[0] == "main.py")[1:] = ["a" * 64, 6]
    with pytest.raises(ValueError, match="source|only"):
        read(recovery)
    assert recovery[2]["calls"] == []


@pytest.mark.parametrize("defect", ["main_bytes", "extra_file", "post_creation_edit", "unowned"])
def test_current_cloud_source_and_owner_checked_before_outcome(recovery, defect):
    api = recovery[2]
    if defect == "main_bytes":
        next(row for row in api["files"] if row["name"] == "main.py")["content"] += "changed"
    elif defect == "extra_file":
        api["files"].append(copy.deepcopy(api["files"][0]))
    elif defect == "post_creation_edit":
        api["files"][0]["modified"] = "2026-09-26T12:02:00"
    else:
        api["project"]["owner"] = False
    with pytest.raises(ValueError):
        read(recovery)
    assert all(endpoint != "backtests/read" for endpoint, _ in api["calls"])
    assert not sut._path(recovery[0], "read-claim").exists()


@pytest.mark.parametrize("phase", ["listed", "outcome"])
@pytest.mark.parametrize("field,value", [("backtestId", "another-run"), ("snapshotId", 101),
    ("name", "another name"), ("status", "Runtime Error"), ("created", "2026-09-26T12:00:59")])
def test_terminal_and_outcome_run_identity_pinned(recovery, phase, field, value):
    recovery[2][phase][field] = value
    with pytest.raises(ValueError, match="run identity"):
        read(recovery)
    assert sut._path(recovery[0], "read-claim").exists() == (phase == "outcome")


def test_failed_outcome_identity_still_consumes_sole_read(recovery):
    recovery[2]["outcome"]["snapshotId"] = 101
    with pytest.raises(ValueError):
        read(recovery)
    recovery[2]["outcome"]["snapshotId"] = 100
    with pytest.raises(ValueError):
        read(recovery)
    assert sum(endpoint == "backtests/read" for endpoint, _ in recovery[2]["calls"]) == 1


@pytest.mark.parametrize("defect", ["extra_custom", "oversized", "wrong_lineage"])
def test_only_three_bounded_reauthenticated_statistics_can_be_imported(recovery, defect):
    statistics = recovery[2]["outcome"]["statistics"]
    if defect == "extra_custom":
        statistics["ARV2_SIX_GATE_ORDER_UNREVIEWED"] = "{}"
    elif defect == "oversized":
        statistics["ARV2_SIX_GATE_ORDER_META"] = " " * 8193
    else:
        import json
        meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
        meta["package_sha256"] = "f" * 64
        statistics["ARV2_SIX_GATE_ORDER_META"] = sut.common._canonical(meta).decode("ascii")
    with pytest.raises(ValueError):
        read(recovery)
    assert sut._path(recovery[0], "read-claim").exists()
    assert not sut._path(recovery[0], "result").exists()


def test_original_failed_a3_cannot_be_promoted_to_completed(recovery):
    plan, _, api, _ = recovery
    path = sut.adapter._path(plan, "terminal")
    path.write_bytes(sut.common._canonical({"candidate_id": "R225", "attempt": 3,
        "project_id": sut.PROJECT_ID, "backtest_id": sut.FAILED_A3_ID, "status": "Completed."}))
    with pytest.raises(ValueError, match="failure census"):
        read(recovery)
    assert api["calls"] == []


def test_cached_result_and_statistic_tampering_refused_without_qc(recovery):
    plan, evidence, api, _ = recovery
    read(recovery)
    path = sut._path(plan, "result")
    saved = sut.adapter._read_artifact(path)
    saved["parsed_result"]["run_valid"] = False
    path.write_bytes(sut.common._canonical(saved))
    calls = len(api["calls"])
    with pytest.raises(ValueError, match="cached result differs"):
        sut.authenticated_cached_result(plan, evidence, sut.adapter._sha(evidence))
    assert len(api["calls"]) == calls
