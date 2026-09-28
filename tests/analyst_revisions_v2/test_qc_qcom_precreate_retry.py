"""One-off R237 A2 recovery after a spent pre-create transport failure."""

import dataclasses

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_exclusion_tilt as script
from tests.analyst_revisions_v2.test_qc_relaxed_submission import ORG


@pytest.fixture(scope="module")
def projection():
    return script.projected("R237")[0]


@pytest.fixture
def recovery(tmp_path, monkeypatch, projection):
    plan = adapter.build_plan("R237", ORG, tmp_path / "controls", 2,
                              family="qcom_exclusion_tilt")
    prior = dataclasses.replace(plan, attempt=1)
    adapter.common._write(adapter._path(prior, "claim"), adapter.preview(prior, projection))
    row = adapter._candidate(plan)
    adapter.common._write(adapter._path(plan, "project"), {
        "candidate_id": "R237", "project_id": 37060477,
        "project_name": row["project_name"]})
    monkeypatch.setattr(adapter, "_require_inputs", lambda _plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda _api: None)
    calls = []
    inventory = [[], []]
    files = [{"projectId": 37060477, "name": item.project_path,
              "content": item.source_bytes.decode("ascii")}
             for item in projection.source_files]

    def post(_api, endpoint, body):
        calls.append((endpoint, body))
        if endpoint == "authenticate":
            return {}
        if endpoint == "projects/read":
            return {"projects": [{"projectId": 37060477,
                "name": row["project_name"], "organizationId": ORG,
                "language": "Py", "owner": True, "codeRunning": False,
                "public": False, "collaborators": [{"owner": True}]}]}
        if endpoint == "files/read":
            return {"files": files}
        if endpoint == "backtests/list":
            rows = inventory.pop(0)
            return {"count": len(rows), "backtests": rows}
        if endpoint == "compile/create":
            return {"compileId": "compile-recovery"}
        if endpoint == "compile/read":
            return {"compileId": "compile-recovery", "state": "BuildSuccess"}
        if endpoint == "backtests/create":
            return {"backtest": {"projectId": 37060477,
                "name": body["backtestName"], "backtestId": "r237-recovered-a2",
                "status": "In Queue..."}}
        raise AssertionError(f"unexpected remote endpoint {endpoint}")

    monkeypatch.setattr(adapter.common, "_post", post)
    return plan, prior, projection, calls, inventory, files


def test_r237_a2_reuses_exact_project_and_requires_two_empty_run_censuses(recovery):
    plan, prior, projection, calls, _inventory, _files = recovery
    receipt = adapter.launch(plan, projection, object())
    endpoints = [endpoint for endpoint, _body in calls]
    assert receipt["project_id"] == 37060477
    assert receipt["backtest_id"] == "r237-recovered-a2"
    assert endpoints.count("backtests/list") == 2
    assert endpoints.index("backtests/list") < endpoints.index("compile/create")
    assert endpoints[-2:] == ["backtests/list", "backtests/create"]
    assert not any(endpoint in {"projects/create", "files/create", "files/update", "files/delete"}
                   for endpoint in endpoints)
    assert adapter._path(prior, "claim").exists()
    assert adapter._path(plan, "claim").exists()


@pytest.mark.parametrize("defect", ("wrong_claim", "wrong_project", "prior_launch",
    "wrong_source", "remote_orphan", "late_orphan"))
def test_r237_a2_precreate_recovery_refuses_ambiguous_predecessor(recovery, defect):
    plan, prior, projection, calls, inventory, files = recovery
    if defect == "wrong_claim":
        # O_EXCL records are immutable; the test exercises refusal through a
        # different, incomplete predecessor slot rather than rewriting one.
        adapter._path(prior, "claim").unlink()
    elif defect == "wrong_project":
        adapter._path(plan, "project").unlink()
    elif defect == "prior_launch":
        adapter.common._write(adapter._path(prior, "launch"), {"unexpected": True})
    elif defect == "wrong_source":
        files[0]["content"] += "# changed\n"
    elif defect == "remote_orphan":
        inventory[0] = [{"backtestId": "orphan"}]
    elif defect == "late_orphan":
        inventory[1] = [{"backtestId": "orphan"}]
    with pytest.raises((adapter.RelaxedQcSubmissionError,
                        adapter.common.SixUniverseSettlementSubmissionError)):
        adapter.launch(plan, projection, object())
    assert not any(endpoint == "backtests/create" for endpoint, _body in calls)
