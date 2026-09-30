"""Isolate R281's exact spent-A1, pre-backtest A2 recovery path."""

import dataclasses

import pytest

from research.analyst_revisions_v2_qc import eight_universe_execution_stress_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts.run_arv2_qcom_restored import package
from tests.analyst_revisions_v2.test_qc_relaxed_submission import ORG


PROJECT_ID = 37165262


@pytest.fixture(scope="module")
def projection():
    return study.build_projection(package(), "R281")[0]


@pytest.fixture
def recovery(tmp_path, monkeypatch, projection):
    plan = adapter.build_plan("R281", ORG, tmp_path / "controls", 2,
                              family="eight_execution_stress")
    prior = dataclasses.replace(plan, attempt=1)
    row = adapter._candidate(plan)
    adapter.common._write(adapter._path(prior, "claim"),
                          adapter.preview(prior, projection))
    adapter.common._write(adapter._path(prior, "project"), {
        "candidate_id": "R281", "project_id": PROJECT_ID,
        "project_name": row["project_name"]})
    monkeypatch.setattr(study, "require_parents", lambda _plan: None)
    monkeypatch.setattr(adapter, "_require_inputs", lambda _plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda _api: None)
    calls = []
    inventories = [[], []]
    files = [{"projectId": PROJECT_ID, "name": item.project_path,
              "content": item.source_bytes.decode("ascii")}
             for item in projection.source_files]

    def post(_api, endpoint, body):
        calls.append((endpoint, body))
        if endpoint == "authenticate":
            return {}
        if endpoint == "projects/read":
            return {"projects": [{"projectId": PROJECT_ID,
                "name": row["project_name"], "organizationId": ORG,
                "language": "Py", "owner": True, "codeRunning": False,
                "public": False, "collaborators": [{"owner": True}]}]}
        if endpoint == "files/read":
            return {"files": files}
        if endpoint == "backtests/list":
            rows = inventories.pop(0)
            return {"count": len(rows), "backtests": rows}
        if endpoint == "compile/create":
            return {"compileId": "compile-r281-a2"}
        if endpoint == "compile/read":
            return {"compileId": "compile-r281-a2", "state": "BuildSuccess"}
        if endpoint == "backtests/create":
            return {"backtest": {"projectId": PROJECT_ID,
                "name": body["backtestName"], "backtestId": "r281-recovered-a2",
                "status": "In Queue..."}}
        raise AssertionError(f"unexpected QC endpoint {endpoint}")

    monkeypatch.setattr(adapter.common, "_post", post)
    return plan, prior, projection, calls, inventories, files


def test_r281_a2_reuses_exact_project_source_and_two_empty_run_censuses(recovery):
    plan, prior, projection, calls, _inventories, files = recovery
    assert len(files) == 17
    receipt = adapter.launch(plan, projection, object())
    endpoints = [endpoint for endpoint, _body in calls]
    assert receipt["project_id"] == PROJECT_ID
    assert receipt["backtest_id"] == "r281-recovered-a2"
    assert receipt["projection_sha256"] == (
        "7a725fe4dc8d913cf56916b1f3d87409e6019a0cb01c7f1c73231e679fdddc2d")
    assert endpoints.count("backtests/list") == 2
    assert endpoints.index("backtests/list") < endpoints.index("compile/create")
    assert endpoints[-2:] == ["backtests/list", "backtests/create"]
    assert not any(endpoint in {"projects/create", "files/create", "files/update",
                                "files/delete"} for endpoint in endpoints)
    assert adapter._path(prior, "claim").exists()
    assert adapter._path(plan, "claim").exists()
    assert adapter._path(prior, "project") == adapter._path(plan, "project")


@pytest.mark.parametrize("defect", (
    "wrong_claim", "wrong_project", "prior_launch", "wrong_source",
    "remote_orphan", "late_orphan", "missing_recovery_pin", "wrong_recovery_pin",
))
def test_r281_a2_refuses_ambiguous_spent_a1_state(recovery, monkeypatch, defect):
    plan, prior, projection, calls, inventories, files = recovery
    if defect == "wrong_claim":
        adapter._path(prior, "claim").unlink()
    elif defect == "wrong_project":
        adapter._path(plan, "project").unlink()
    elif defect == "prior_launch":
        adapter.common._write(adapter._path(prior, "launch"), {"unexpected": True})
    elif defect == "wrong_source":
        files[0]["content"] += "# changed\n"
    elif defect == "remote_orphan":
        inventories[0] = [{"backtestId": "orphan"}]
    elif defect == "late_orphan":
        inventories[1] = [{"backtestId": "orphan"}]
    elif defect == "missing_recovery_pin":
        monkeypatch.delitem(adapter._PRECREATE_A2_RECOVERY,
                            ("eight_execution_stress", "R281"))
    elif defect == "wrong_recovery_pin":
        manifest, _projection, project_id = adapter._PRECREATE_A2_RECOVERY[
            ("eight_execution_stress", "R281")]
        monkeypatch.setitem(adapter._PRECREATE_A2_RECOVERY,
                            ("eight_execution_stress", "R281"),
                            (manifest, "0" * 64, project_id))
    with pytest.raises((adapter.RelaxedQcSubmissionError,
                        adapter.common.SixUniverseSettlementSubmissionError)):
        adapter.launch(plan, projection, object())
    assert not any(endpoint == "backtests/create" for endpoint, _body in calls)
