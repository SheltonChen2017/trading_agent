"""Exact R244/R245 A2-only recovery after spent pre-create QC attempts."""

import dataclasses

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_exclusion_three_name as script
from tests.analyst_revisions_v2.test_qc_relaxed_submission import ORG


_PROJECTS = {"R244": 37065932, "R245": 37065931}


@pytest.fixture(scope="module", params=("R244", "R245"))
def candidate_projection(request):
    candidate = request.param
    return candidate, script.projected(candidate)[0]


@pytest.fixture
def recovery(tmp_path, monkeypatch, candidate_projection):
    candidate, projection = candidate_projection
    project_id = _PROJECTS[candidate]
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", 2,
                              family="qcom_exclusion_three_name")
    prior = dataclasses.replace(plan, attempt=1)
    adapter.common._write(adapter._path(prior, "claim"), adapter.preview(prior, projection))
    row = adapter._candidate(plan)
    adapter.common._write(adapter._path(plan, "project"), {
        "candidate_id": candidate, "project_id": project_id,
        "project_name": row["project_name"]})
    monkeypatch.setattr(adapter, "_require_inputs", lambda _plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda _api: None)
    calls = []
    inventories = [[], []]
    files = [{"projectId": project_id, "name": item.project_path,
              "content": item.source_bytes.decode("ascii")}
             for item in projection.source_files]

    def post(_api, endpoint, body):
        calls.append((endpoint, body))
        if endpoint == "authenticate":
            return {}
        if endpoint == "projects/read":
            return {"projects": [{"projectId": project_id,
                "name": row["project_name"], "organizationId": ORG,
                "language": "Py", "owner": True, "codeRunning": False,
                "public": False, "collaborators": [{"owner": True}]}]}
        if endpoint == "files/read":
            return {"files": files}
        if endpoint == "backtests/list":
            rows = inventories.pop(0)
            return {"count": len(rows), "backtests": rows}
        if endpoint == "compile/create":
            return {"compileId": "three-name-recovery-compile"}
        if endpoint == "compile/read":
            return {"compileId": "three-name-recovery-compile", "state": "BuildSuccess"}
        if endpoint == "backtests/create":
            return {"backtest": {"projectId": project_id,
                "name": body["backtestName"],
                "backtestId": f"{candidate.lower()}-recovered-a2",
                "status": "In Queue..."}}
        raise AssertionError(f"unexpected remote endpoint {endpoint}")

    monkeypatch.setattr(adapter.common, "_post", post)
    return plan, prior, projection, calls, inventories, files


def test_a2_reuses_exact_project_and_requires_two_fresh_zero_censuses(
        recovery, monkeypatch):
    plan, prior, projection, calls, _inventories, _files = recovery
    original_write = adapter.common._write

    def write(path, value):
        if path == adapter._path(plan, "claim"):
            assert [endpoint for endpoint, _body in calls].count("backtests/list") == 1
            assert not any(endpoint == "compile/create" for endpoint, _body in calls)
        original_write(path, value)

    monkeypatch.setattr(adapter.common, "_write", write)
    receipt = adapter.launch(plan, projection, object())
    endpoints = [endpoint for endpoint, _body in calls]
    assert receipt["candidate_id"] == plan.candidate_id
    assert receipt["project_id"] == _PROJECTS[plan.candidate_id]
    assert receipt["backtest_id"] == f"{plan.candidate_id.lower()}-recovered-a2"
    assert receipt["attempt"] == 2
    assert endpoints.count("backtests/list") == 2
    assert endpoints.index("backtests/list") < endpoints.index("compile/create")
    assert endpoints[-2:] == ["backtests/list", "backtests/create"]
    assert not any(endpoint in {"projects/create", "files/create", "files/update",
                                "files/delete"} for endpoint in endpoints)
    assert adapter._path(prior, "claim").exists()
    assert adapter._path(plan, "claim").exists()


@pytest.mark.parametrize("defect", (
    "changed_a1_claim", "wrong_project_receipt", "prior_launch",
    "remote_source_changed", "early_orphan", "late_orphan",
))
def test_a2_refuses_ambiguous_a1_or_changed_identity(recovery, defect):
    plan, prior, projection, calls, inventories, files = recovery
    if defect == "changed_a1_claim":
        claim_path = adapter._path(prior, "claim")
        claim_path.unlink()
        adapter.common._write(claim_path, {
            **adapter.preview(prior, projection), "profile_sha256": "0" * 64})
    elif defect == "wrong_project_receipt":
        receipt_path = adapter._path(plan, "project")
        receipt_path.unlink()
        adapter.common._write(receipt_path, {
            "candidate_id": plan.candidate_id,
            "project_id": _PROJECTS[plan.candidate_id] + 1,
            "project_name": adapter._candidate(plan)["project_name"]})
    elif defect == "prior_launch":
        adapter.common._write(adapter._path(prior, "launch"), {"unexpected": True})
    elif defect == "remote_source_changed":
        files[0]["content"] += "# changed\n"
    elif defect == "early_orphan":
        inventories[0] = [{"backtestId": "delayed-a1"}]
    elif defect == "late_orphan":
        inventories[1] = [{"backtestId": "delayed-a1"}]
    with pytest.raises((adapter.RelaxedQcSubmissionError,
                        adapter.common.SixUniverseSettlementSubmissionError)):
        adapter.launch(plan, projection, object())
    endpoints = [endpoint for endpoint, _body in calls]
    expected_censuses = 1 if defect == "early_orphan" else 2 if defect == "late_orphan" else 0
    assert endpoints.count("backtests/list") == expected_censuses
    if defect == "late_orphan":
        assert endpoints.count("compile/create") == 1
    else:
        assert "compile/create" not in endpoints
    assert not any(endpoint == "backtests/create" for endpoint, _body in calls)
    assert not any(endpoint in {"projects/create", "files/create", "files/update",
                                "files/delete"} for endpoint, _body in calls)


def test_other_three_name_candidate_and_later_attempt_cannot_enter_recovery(
        tmp_path, monkeypatch, candidate_projection):
    candidate, projection = candidate_projection
    for other_candidate, attempt in (("R242", 2), (candidate, 3)):
        plan = adapter.build_plan(other_candidate, ORG,
            tmp_path / f"controls-{other_candidate}-{attempt}", attempt,
            family="qcom_exclusion_three_name")
        other_projection = (script.projected(other_candidate)[0]
                            if other_candidate != candidate else projection)
        monkeypatch.setattr(adapter, "_require_inputs", lambda _plan: None)
        monkeypatch.setattr(adapter.common, "_client", lambda _api: None)
        monkeypatch.setattr(adapter.common, "_post", lambda *_args: {})
        with pytest.raises((adapter.RelaxedQcSubmissionError,
                            adapter.common.SixUniverseSettlementSubmissionError)):
            adapter.launch(plan, other_projection, object())
        assert not adapter._path(plan, "claim").exists()
