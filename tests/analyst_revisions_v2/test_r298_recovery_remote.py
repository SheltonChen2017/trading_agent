"""Synthetic-only injected transport; no private artifact or remote access."""
import copy
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_recovery_remote as m


@pytest.fixture
def state():
    sources = {name: ("# exact synthetic " + name + "\n").encode("ascii") for name in m.SOURCE_NAMES}
    manifest = [{"project_path": name, "byte_count": len(raw), "content_sha256": m._sha(raw)}
        for name, raw in sorted(sources.items())]
    projection = SimpleNamespace(projection_sha256=m.PROJECTION_SHA256,
        source_files=tuple(SimpleNamespace(project_path=name, source_bytes=raw)
            for name, raw in sorted(sources.items())),
        to_record=lambda: {"candidate_id": "R298", "source_files": manifest})
    value = SimpleNamespace(sources=sources, files={"main.py": "#"}, calls=[], events=[],
        compile_state="BuildSuccess", prior_runs=[], busy=False, mutation=None)
    value.project = {"projectId": m.PROJECT_ID, "organizationId": "a" * 32,
        "name": m.PROJECT_NAME, "language": "Py", "owner": True, "public": False,
        "codeRunning": False, "collaborators": [{"owner": True}]}
    def journal(marker, event):
        assert set(event) == {"event", "endpoint", "sha256"}
        assert len(event["sha256"]) == 64 and event["endpoint"] in m.ENDPOINTS
        assert not any(old == marker and previous["event"] == event["event"] for old, previous in value.events)
        value.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert value.events[-1][1] == {"event": "intent", "endpoint": endpoint,
            "sha256": m._sha(m._canonical(payload))}
        value.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == "projects/read":
            result = {"projects": [copy.deepcopy(value.project)]}
        elif endpoint == "backtests/list":
            result = {"projectId": m.PROJECT_ID, "count": len(value.prior_runs), "backtests": copy.deepcopy(value.prior_runs)}
        elif endpoint == "files/read":
            result = {"files": [{"projectId": m.PROJECT_ID, "name": name, "content": raw} for name, raw in value.files.items()]}
        elif endpoint in {"files/create", "files/update"}:
            assert (payload["name"] in value.files) == (endpoint == "files/update")
            value.files[payload["name"]] = payload["content"]
            result = {}
        elif endpoint == "compile/create":
            result = {"projectId": m.PROJECT_ID, "compileId": "compile-one"}
        elif endpoint == "compile/read":
            result = {"projectId": m.PROJECT_ID, "compileId": payload["compileId"], "state": value.compile_state}
        elif endpoint == "projects/nodes/read":
            result = {"nodes": {"backtest": [{"busy": value.busy, "active": False}]}, "autoSelectNode": True}
        elif endpoint == "backtests/create":
            result = {"backtest": {"projectId": m.PROJECT_ID, "backtestId": "run-one",
                "name": payload["backtestName"], "status": "In Queue..."}}
        else:
            pytest.fail("unexpected endpoint")
        result["success"] = True
        if value.mutation:
            value.mutation(endpoint, payload, result)
        return result
    value.journal, value.request, value.projection = journal, request, projection
    value.remote = m.RemoteRecovery(projection, "a" * 32, request, journal)
    return value


def exact(state):
    state.files = {name: raw.decode("ascii") for name, raw in state.sources.items()}


def writes(state):
    return [row for row in state.calls if row[0] in {"files/create", "files/update", "compile/create", "backtests/create"}]


def test_inspect_returns_only_hash_size_inventory(state):
    result = state.remote.inspect()
    assert result["files"] == [{"name": "main.py", "byte_count": 1, "sha256": m._sha(b"#")}]
    assert all(set(row) == {"name", "byte_count", "sha256"} for row in result["files"])
    assert writes(state) == [] and len(state.calls) == 3 and len(state.events) == 6


def test_completion_compile_poll_launch_fixed_project(state):
    before = state.remote.inspect()
    saved = copy.deepcopy(before)
    finished = state.remote.complete(before)
    assert before == saved
    assert len(finished["files"]) == 11 and len(writes(state)) == 11
    assert [endpoint for endpoint, payload in writes(state)].count("files/update") == 1
    assert all(payload["projectId"] == m.PROJECT_ID for _, payload in state.calls)
    compiled = state.remote.compile_once(finished)
    assert compiled["compile_id"] == "compile-one"
    assert state.remote.poll_compile(compiled["compile_id"], 0)["state"] == "BuildSuccess"
    launched = state.remote.launch_once(compiled["compile_id"])
    assert launched["status"] == "In Queue..." and launched["backtest_id"] == "run-one"
    assert launched["backtest_name"] == f"{m.PROJECT_NAME} A2 {m.PROJECTION_SHA256[:8]}"
    assert [endpoint for endpoint, _ in state.calls].count("compile/create") == 1
    assert [endpoint for endpoint, _ in state.calls].count("backtests/create") == 1
    assert all("content" not in event for _, event in state.events)


def test_no_mutation_of_already_exact_files(state):
    exact(state)
    inventory = state.remote.inspect()
    assert state.remote.complete(inventory) == inventory
    assert writes(state) == []


def test_exact_browser_default_main_can_be_completed(state):
    assert len(m.DEFAULT_MAIN) == 406
    state.files["main.py"] = m.DEFAULT_MAIN.decode("ascii")
    original = state.remote.inspect()
    state.remote.complete(original)
    assert state.files["main.py"].encode("ascii") == state.sources["main.py"]


@pytest.mark.parametrize("name,suffix", [("main.py", " "), ("newrule_legacy_primitives.py", "")])
def test_default_main_near_match_or_wrong_name_refuses(state, name, suffix):
    state.files[name] = m.DEFAULT_MAIN.decode("ascii") + suffix
    with pytest.raises(m.RecoveryError, match="unexpected_cloud_content"):
        state.remote.inspect()
    assert writes(state) == []


@pytest.mark.parametrize("key,value", [("projectId", True), ("projectId", m.PROJECT_ID + 1),
    ("organizationId", "b" * 32), ("name", "another lane"), ("language", "C#"),
    ("owner", False), ("public", True), ("codeRunning", True),
    ("collaborators", [{"owner": False}]), ("collaborators", [{"owner": True}] * 2)])
def test_project_bindings_refuse(state, key, value):
    state.project[key] = value
    with pytest.raises(m.RecoveryError, match="private_owned_idle_project"):
        state.remote.inspect()
    assert writes(state) == []


@pytest.mark.parametrize("count", [True, 1, "0", 0.0])
def test_prior_count_not_coerced(state, count):
    state.mutation = lambda endpoint, payload, result: result.update(count=count) if endpoint == "backtests/list" else None
    with pytest.raises(m.RecoveryError, match="prior_backtests"):
        state.remote.inspect()


def test_prior_run_refuses(state):
    state.prior_runs = [{"backtestId": "older"}]
    with pytest.raises(m.RecoveryError, match="prior_backtests"):
        state.remote.inspect()


@pytest.mark.parametrize("changes", [{"stranger.py": "#"}, {"main.py": "# arbitrary"},
    {"main.py": "print('secret')"}, {"main.py": ""}, {"main.py": "＃"}])
def test_unknown_source_refuses_without_overwrite(state, changes):
    state.files.update(changes)
    with pytest.raises(m.RecoveryError):
        state.remote.inspect()
    assert writes(state) == []


@pytest.mark.parametrize("mutation", ["duplicate", "foreign", "boolean", "missingcontent", "oversize"])
def test_inventory_malformed_refused(state, mutation):
    def mutate(endpoint, payload, result):
        if endpoint != "files/read":
            return
        row = result["files"][0]
        if mutation == "duplicate": result["files"].append(copy.deepcopy(row))
        if mutation == "foreign": row["projectId"] += 1
        if mutation == "boolean": row["projectId"] = True
        if mutation == "missingcontent": del row["content"]
        if mutation == "oversize": row["content"] = "#" * 64001
    state.mutation = mutate
    with pytest.raises(m.RecoveryError, match="cloud_file"):
        state.remote.inspect()


def test_original_inventory_changed_refuses_before_writes(state):
    original = state.remote.inspect()
    state.files["main.py"] = "#\n"
    with pytest.raises(m.RecoveryError, match="inventory_changed"):
        state.remote.complete(original)
    assert writes(state) == []


def test_concurrent_changed_file_before_write_refuses(state):
    original = state.remote.inspect()
    observed = 0
    def mutate(endpoint, payload, result):
        nonlocal observed
        if endpoint == "files/read":
            observed += 1
            if observed == 2:
                result["files"][0]["content"] = "#\n"
    state.mutation = mutate
    with pytest.raises(m.RecoveryError, match="inventory_changed"):
        state.remote.complete(original)
    assert writes(state) == []


def test_no_compile_before_whole_manifest_verified(state):
    inventory = state.remote.inspect()
    with pytest.raises(m.RecoveryError, match="unexpected_cloud_content|incomplete_cloud_source"):
        state.remote.compile_once(inventory)
    assert writes(state) == []


def test_stale_completed_inventory_refuses_compile(state):
    exact(state)
    inventory = state.remote.inspect()
    inventory["files"][0]["byte_count"] += 1
    with pytest.raises(m.RecoveryError, match="inventory_changed"):
        state.remote.compile_once(inventory)
    assert writes(state) == []


def test_journal_failure_blocks_request(state):
    def broken(*args):
        raise OSError("SECRET")
    remote = m.RemoteRecovery(state.projection, "a" * 32, state.request, broken)
    with pytest.raises(m.RecoveryError, match="^journal_failed$"):
        remote.inspect()
    assert state.calls == []


def test_request_failure_does_not_repeat_and_drops_exception(state):
    calls = []
    def broken(*args):
        calls.append(args)
        raise OSError("SECRET")
    remote = m.RemoteRecovery(state.projection, "a" * 32, broken, state.journal)
    with pytest.raises(m.RecoveryError, match="^request_ambiguous$"):
        remote.inspect()
    with pytest.raises(m.RecoveryError, match="duplicate_or_endpoint"):
        remote.inspect()
    assert len(calls) == 1 and len(state.events) == 1


def test_cross_instance_duplicate_durable_journal_prevents_contact(state):
    state.remote.inspect()
    remote = m.RemoteRecovery(state.projection, "a" * 32, state.request, state.journal)
    with pytest.raises(m.RecoveryError, match="journal_failed"):
        remote.inspect()
    assert len(state.calls) == 3


@pytest.mark.parametrize("state_name", ["InQueue", "Building", "BuildError"])
def test_compile_not_success_never_launches(state, state_name):
    exact(state)
    state.compile_state = state_name
    with pytest.raises(m.RecoveryError, match="compile_not_ready"):
        state.remote.launch_once("compile-one")
    assert writes(state) == []


@pytest.mark.parametrize("index", [-1, 60, True, "0", 0.0])
def test_poll_index_bound(state, index):
    with pytest.raises(m.RecoveryError, match="poll_index"):
        state.remote.poll_compile("compile-one", index)
    assert state.calls == []


def test_busy_wait_never_launches(state):
    exact(state)
    state.busy = True
    assert state.remote.launch_once("compile-one") == {"project_id": m.PROJECT_ID, "state": "wait", "available_count": 0}
    assert writes(state) == []


def test_exact_source_is_reread_before_launch(state):
    with pytest.raises(m.RecoveryError, match="unexpected_cloud_content"):
        state.remote.launch_once("compile-one")
    assert writes(state) == []


@pytest.mark.parametrize("field,value", [("projectId", True), ("projectId", 1),
    ("name", "another"), ("status", "InQueue"), ("backtestId", "bad\n")])
def test_created_backtest_binding_is_strict(state, field, value):
    exact(state)
    state.mutation = lambda endpoint, payload, result: result["backtest"].update({field: value}) if endpoint == "backtests/create" else None
    with pytest.raises(m.RecoveryError):
        state.remote.launch_once("compile-one")
    assert [endpoint for endpoint, _ in state.calls].count("backtests/create") == 1


def test_compile_project_binding(state):
    exact(state)
    inventory = state.remote.inspect()
    state.mutation = lambda endpoint, payload, result: result.update(projectId=True) if endpoint == "compile/create" else None
    with pytest.raises(m.RecoveryError, match="compile_project"):
        state.remote.compile_once(inventory)


@pytest.mark.parametrize("value", [None, False, "yes"])
def test_response_success_requires_true(state, value):
    state.mutation = lambda endpoint, payload, result: result.update(success=value)
    with pytest.raises(m.RecoveryError, match="response_refused"):
        state.remote.inspect()
    assert len(state.events) == 2 and writes(state) == []


def test_no_api_capability_imports():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(m.__file__).read_text())
    modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert modules == {"hashlib", "json", "re"}
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))


def test_mutated_projection_bytes_cannot_reuse_old_manifest(state):
    state.projection.source_files[0].source_bytes += b"# mutated\n"
    with pytest.raises(m.RecoveryError, match="source_manifest_binding"):
        m.RemoteRecovery(state.projection, "a" * 32, state.request, state.journal)
    assert state.calls == []


@pytest.mark.parametrize("endpoint", ["compile/create", "compile/read"])
def test_compile_project_id_absent_retains_frozen_response_qualification(state, endpoint):
    exact(state)
    inventory = state.remote.inspect()
    state.mutation = lambda seen, payload, result: result.pop("projectId", None) if seen == endpoint else None
    if endpoint == "compile/create":
        assert state.remote.compile_once(inventory)["compile_id"] == "compile-one"
    else:
        assert state.remote.poll_compile("compile-one", 0)["state"] == "BuildSuccess"


def receipt():
    return {"project_id": m.PROJECT_ID, "compile_id": "compile-one", "backtest_id": "run-one",
        "backtest_name": f"{m.PROJECT_NAME} A2 {m.PROJECTION_SHA256[:8]}",
        "status": "In Queue...", "projection_sha256": m.PROJECTION_SHA256}


@pytest.mark.parametrize("status", ["In Queue...", "In Progress...", "Completed.", "Runtime Error"])
def test_own_status_only_no_statistics_or_error_text(state, status):
    own = receipt()
    state.prior_runs = [{"projectId": m.PROJECT_ID, "backtestId": own["backtest_id"],
        "name": own["backtest_name"], "status": status, "error": "SECRET", "statistics": {"secret": "SECRET"}}]
    result = state.remote.read_status(own, 0)
    assert result == {**own, "status": status}
    assert state.calls == [("backtests/list", {"projectId": m.PROJECT_ID, "includeStatistics": False})]
    assert "SECRET" not in repr(result) and "SECRET" not in repr(state.events)


@pytest.mark.parametrize("key,value", [("project_id", True), ("project_id", 1),
    ("projection_sha256", "b" * 64), ("backtest_name", "another"),
    ("backtest_id", ""), ("compile_id", "bad\n"), ("status", "Completed.")])
def test_status_supplied_receipt_must_be_exact_original_launch(state, key, value):
    own = receipt()
    own[key] = value
    with pytest.raises(m.RecoveryError):
        state.remote.read_status(own, 0)
    assert state.calls == []


@pytest.mark.parametrize("key,value", [("projectId", True), ("projectId", 1),
    ("backtestId", "different"), ("name", "different"), ("status", "Completed")])
def test_other_remote_job_refuses_status(state, key, value):
    own = receipt()
    row = {"projectId": m.PROJECT_ID, "backtestId": own["backtest_id"],
        "name": own["backtest_name"], "status": "In Progress..."}
    row[key] = value
    state.prior_runs = [row]
    with pytest.raises(m.RecoveryError, match="backtest_status"):
        state.remote.read_status(own, 0)


@pytest.mark.parametrize("index", [-1, 240, True, "0"])
def test_status_poll_bound(state, index):
    with pytest.raises(m.RecoveryError, match="status_poll_index"):
        state.remote.read_status(receipt(), index)
    assert state.calls == []


@pytest.mark.parametrize("attempt", ["A1", "A3"])
def test_only_newly_authorized_a2_receipt_admitted(state, attempt):
    own = receipt()
    own["backtest_name"] = f"{m.PROJECT_NAME} {attempt} {m.PROJECTION_SHA256[:8]}"
    with pytest.raises(m.RecoveryError, match="launch_receipt"):
        state.remote.read_status(own, 0)
    assert state.calls == []
