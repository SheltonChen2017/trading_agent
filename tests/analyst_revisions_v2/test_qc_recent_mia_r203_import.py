"""Focused red/green checks for the owner/Mia R203 second-run import."""

import copy
import dataclasses
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import six_universe_recent_settlement_submission as subject
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from tests.analyst_revisions_v2 import test_qc_six_universe_settlement_recent_submission as fixtures
from tests.analyst_revisions_v2.test_qc_six_universe_settlement_recent_submission import offline_recent_projections


@pytest.fixture
def prepared(offline_recent_projections, monkeypatch, tmp_path):
    retry, prior, _digest, _calls, _state = fixtures._failed_a1(
        monkeypatch, tmp_path, offline_recent_projections)
    plan = dataclasses.replace(retry, attempt=1)
    files = tuple(common.base_projection._source_file(item.project_path,
        item.source_bytes + b"\n# Test-only Mia transport correction.\n")
        if item.project_path == subject._MIA_INPUT_PATH else item
        for item in prior.source_files)
    corrected = dataclasses.replace(prior,
        schema="arv2-six-universe-order-qc-projection-tilt100-recent-direct-read-v2",
        source_files=files, total_source_byte_count=sum(item.byte_count for item in files))
    semantic = {key: value for key, value in corrected.to_record().items()
                if key not in {"projection_id", "projection_sha256"}}
    digest = hashlib.sha256(common._canonical(semantic)).hexdigest()
    corrected = dataclasses.replace(corrected, projection_sha256=digest,
        projection_id="arv2-six-universe-order-tilt100-recent-direct-read-qc-projection-" + digest[:24])
    manifest = tuple((item.project_path, item.content_sha256, item.byte_count) for item in files)
    candidate = dataclasses.replace(common._candidate(plan), projection_schema=corrected.schema,
        projection_sha256=digest, source_files_sha256=hashlib.sha256(common._canonical(manifest)).hexdigest(),
        total_source_bytes=corrected.total_source_byte_count)
    monkeypatch.setattr(subject, "MIA_R203_CANDIDATE", candidate)
    changed = next(item for item in files if item.project_path == subject._MIA_INPUT_PATH)
    monkeypatch.setattr(subject, "_MIA_INPUT_SHA256", changed.content_sha256)
    monkeypatch.setattr(subject, "_MIA_INPUT_BYTES", changed.byte_count)
    old_launch = common._read(common._control_path(plan, "launch"))
    statistics = fixtures._recent_statistics(plan, old_launch)
    mia_run = {"projectId": subject._A2_PROJECT_ID, "backtestId": subject._MIA_BACKTEST_ID,
        "name": subject._MIA_RUN_NAME, "status": "Completed.",
        "snapshotId": subject._MIA_SNAPSHOT_ID, "created": subject._MIA_CREATED_AT}
    state = {
        "project": {"projectId": subject._A2_PROJECT_ID, "name": plan.project_name,
            "organizationId": plan.organization_id, "language": "Py", "owner": True,
            "codeRunning": True, "collaborators": [{"owner": True},
                {"owner": False, "publicId": subject._MIA_COLLABORATOR_PUBLIC_ID}]},
        "files": [{"projectId": subject._A2_PROJECT_ID, "name": item.project_path,
            "content": item.source_bytes.decode("ascii"), "modified": subject._MIA_MODIFIED_AT}
            for item in corrected.source_files],
        "runs": [{"projectId": subject._A2_PROJECT_ID, "backtestId": subject._A1_BACKTEST_ID,
            "name": plan.backtest_name, "status": "Runtime Error"}, copy.deepcopy(mia_run)],
        "result": {**mia_run, "statistics": statistics},
    }
    calls = []
    def post(api, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == "projects/read":
            return {"projects": [copy.deepcopy(state["project"])]}
        if endpoint == "files/read":
            return {"files": copy.deepcopy(state["files"])}
        if endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            return {"backtests": copy.deepcopy(state["runs"]), "count": len(state["runs"])}
        if endpoint == "backtests/read":
            assert common._read(subject._mia_control_path(plan, "mia-result-read-claim"))
            return {"backtest": copy.deepcopy(state["result"])}
        pytest.fail("Mia import used unauthorized endpoint: " + endpoint)
    monkeypatch.setattr(common, "_post", post)
    monkeypatch.setattr(common, "_client", lambda api: None)
    return plan, corrected, state, calls


def test_mia_import_reads_once_preserves_provenance_and_offline_anchor(prepared):
    plan, projection, _state, calls = prepared
    result = subject.read_imported_r203_once(plan, projection, object())
    assert result["run_valid"] is True
    assert result["comparison_valid"] is False
    assert "Net Profit" not in result
    receipt = common._read(subject._mia_control_path(plan, "mia-result-valid"))
    assert receipt["historical_snapshot_bytes_verified"] is False
    assert receipt["codex_launch_or_waiver_claimed"] is False
    assert receipt["attempts_spent_including_mia"] == 2
    assert subject._verified_mia_imported_anchor(plan) == (2, "d" * 64)
    assert subject._valid_comparison_anchor(plan) == (2, "d" * 64)
    assert subject._verified_mia_imported_anchor(dataclasses.replace(plan, candidate_id="R204")) == (2, "d" * 64)
    assert not common._control_path(dataclasses.replace(plan, attempt=2), "claim").exists()
    assert [endpoint for endpoint, _ in calls].count("backtests/read") == 1
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="already claimed"):
        subject.read_imported_r203_once(plan, projection, object())
    assert [endpoint for endpoint, _ in calls].count("backtests/read") == 1


@pytest.mark.parametrize("defect", (
    "missing_run", "unexpected_run", "source", "source_time", "collaborator",
))
def test_mia_inventory_or_predecessor_refusal_never_consumes_outcome(prepared, defect):
    plan, projection, state, calls = prepared
    if defect == "missing_run":
        state["runs"].pop()
    elif defect == "unexpected_run":
        state["runs"].append({"backtestId": "third-run"})
    elif defect == "source":
        state["files"][0]["content"] += "\n# changed"
    elif defect == "source_time":
        state["files"][0]["modified"] = "2026-09-26 08:02:37"
    else:
        state["project"]["collaborators"][1]["publicId"] = "unrelated-collaborator"
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.read_imported_r203_once(plan, projection, object())
    assert not subject._mia_control_path(plan, "mia-result-read-claim").exists()
    assert "backtests/read" not in [endpoint for endpoint, _ in calls]


@pytest.mark.parametrize("defect", ("digest", "census"))
def test_mia_result_refusal_spends_one_read_without_valid_anchor(prepared, defect):
    plan, projection, state, calls = prepared
    statistics = state["result"]["statistics"]
    meta = json.loads(statistics[common.base_runtime.META_STATISTIC_NAME])
    aggregate = json.loads(statistics[common.base_runtime.AGGREGATES_STATISTIC_NAME])
    if defect == "digest":
        meta["aggregate_sha256"] = "0" * 64
    else:
        aggregate["execution"]["completed_rebalance_count"] = 60
    raw = common._canonical(aggregate)
    if defect != "digest":
        meta["aggregate_sha256"] = hashlib.sha256(raw).hexdigest()
    statistics[common.base_runtime.META_STATISTIC_NAME] = common._canonical(meta).decode("ascii")
    statistics[common.base_runtime.AGGREGATES_STATISTIC_NAME] = raw.decode("ascii")
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.read_imported_r203_once(plan, projection, object())
    assert subject._mia_control_path(plan, "mia-result-read-claim").exists()
    assert not subject._mia_control_path(plan, "mia-result-valid").exists()
    assert subject._verified_mia_imported_anchor(plan) is None
    assert [endpoint for endpoint, _ in calls].count("backtests/read") == 1


@pytest.mark.parametrize("target", ("claim", "aggregate"))
def test_mia_offline_anchor_refuses_each_changed_durable_link(prepared, target):
    plan, projection, _state, calls = prepared
    subject.read_imported_r203_once(plan, projection, object())
    assert subject._verified_mia_imported_anchor(plan) is not None
    name = {"claim": "mia-result-read-claim", "aggregate": "mia-authorized-aggregate"}[target]
    path = subject._mia_control_path(plan, name)
    value = common._read(path)
    if target == "aggregate":
        value["aggregates"]["account"]["cumulative_return"] = "0.123"
    else:
        value["snapshot_id"] += 1
    path.write_bytes(common._canonical(value))
    assert subject._verified_mia_imported_anchor(plan) is None
    assert [endpoint for endpoint, _ in calls].count("backtests/read") == 1
