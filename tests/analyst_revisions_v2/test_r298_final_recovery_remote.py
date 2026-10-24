"""Synthetic pure helper tests; the real projection smoke reads public code only."""
import copy
import dataclasses
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_final_recovery_remote as m


@pytest.fixture
def state(monkeypatch):
    # No real organization identifier is embedded in synthetic fixtures.
    organization = "a" * 32
    pin = m._sha(organization.encode("ascii"))
    monkeypatch.setattr(m, "ORGANIZATION_SHA256", pin)
    sources = {name: ("# exact synthetic " + name + "\n").encode("ascii") for name in m.SOURCE_NAMES}
    entries = tuple(SimpleNamespace(project_path=name, source_bytes=raw)
        for name, raw in sorted(sources.items()))
    manifest = [{"project_path": item.project_path, "byte_count": len(item.source_bytes),
        "content_sha256": m._sha(item.source_bytes)} for item in entries]
    projection = SimpleNamespace(projection_sha256=m.PROJECTION_SHA256,
        source_files=entries, to_record=lambda: {"candidate_id": m.PROJECTION_CANDIDATE_ID, "source_files": manifest})
    value = SimpleNamespace(sources=sources, files={"main.py": m.frozen.DEFAULT_MAIN.decode("ascii")},
        calls=[], events=[], prior_runs=[], busy=False, mutation=None, compile_state="BuildSuccess",
        organization=organization, organization_pin=pin, projection=projection)
    value.project = {"projectId": m.PROJECT_ID, "organizationId": organization,
        "name": m.PROJECT_NAME, "language": "Py", "owner": True, "public": False,
        "codeRunning": False, "collaborators": [{"owner": True}]}

    def journal(marker, event):
        assert set(event) == {"event", "endpoint", "sha256"}
        assert not any(old == marker and previous["event"] == event["event"] for old, previous in value.events)
        value.events.append((marker, copy.deepcopy(event)))

    def request(endpoint, payload):
        assert value.events[-1][1] == {"event": "intent", "endpoint": endpoint,
            "sha256": m._sha(m._canonical(payload))}
        value.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == "projects/read":
            result = {"projects": [copy.deepcopy(value.project)]}
        elif endpoint == "backtests/list":
            result = {"projectId": m.PROJECT_ID, "count": len(value.prior_runs),
                "backtests": copy.deepcopy(value.prior_runs)}
        elif endpoint == "files/read":
            result = {"files": [{"projectId": m.PROJECT_ID, "name": name, "content": raw}
                for name, raw in value.files.items()]}
        elif endpoint in ("files/create", "files/update"):
            assert (payload["name"] in value.files) == (endpoint == "files/update")
            value.files[payload["name"]] = payload["content"]
            result = {}
        elif endpoint == "compile/create":
            result = {"projectId": m.PROJECT_ID, "compileId": "compile-a3"}
        elif endpoint == "compile/read":
            result = {"projectId": m.PROJECT_ID, "compileId": payload["compileId"], "state": value.compile_state}
        elif endpoint == "projects/nodes/read":
            result = {"nodes": {"backtest": [{"busy": value.busy, "active": False}]}, "autoSelectNode": True}
        elif endpoint == "backtests/create":
            row = {"projectId": m.PROJECT_ID, "backtestId": "run-a3", "name": payload["backtestName"],
                "status": "In Queue..."}
            value.prior_runs = [copy.deepcopy(row)]
            result = {"backtest": row}
        else:
            pytest.fail("unexpected endpoint")
        result["success"] = True
        if value.mutation:
            value.mutation(endpoint, payload, result)
        return result

    value.request, value.journal = request, journal
    value.remote = m.FinalRecovery(projection, pin, request, journal)
    return value


def exact(state):
    state.files = {name: raw.decode("ascii") for name, raw in state.sources.items()}


def writes(state):
    return [item for item in state.calls if item[0] in
        ("files/create", "files/update", "compile/create", "backtests/create")]


def receipt():
    return {"project_id": m.PROJECT_ID, "compile_id": "compile-a3", "backtest_id": "run-a3",
        "backtest_name": m.BACKTEST_NAME, "status": "In Queue...", "projection_sha256": m.PROJECTION_SHA256}


def test_full_partial_source_sequence_and_own_a3_status(state):
    state.files.update({"accepted_risk_order_level_core.py": state.sources["accepted_risk_order_level_core.py"].decode("ascii"),
        "accepted_risk_order_level_forced_exit.py": state.sources["accepted_risk_order_level_forced_exit.py"].decode("ascii"),
        "accepted_risk_order_level_input_runtime.py": "#"})
    initial = state.remote.inspect()
    completed = state.remote.complete(initial)
    assert len(completed["files"]) == 11
    assert len(writes(state)) == 9
    assert sum(endpoint == "files/create" for endpoint, _ in writes(state)) == 7
    assert sum(endpoint == "files/update" for endpoint, _ in writes(state)) == 2
    assert state.files == {name: raw.decode("ascii") for name, raw in state.sources.items()}
    compiled = state.remote.compile_once(completed)
    assert state.remote.poll_compile(compiled["compile_id"], 0)["state"] == "BuildSuccess"
    launched = state.remote.launch_once(compiled["compile_id"])
    assert launched == receipt() and " A3 " in launched["backtest_name"]
    assert " A2 " not in repr(state.calls)
    assert state.remote.read_status(launched, 0) == receipt()
    assert all(payload["projectId"] == m.PROJECT_ID for _, payload in state.calls)
    assert all(set(event) == {"event", "endpoint", "sha256"} for _, event in state.events)
    assert sum(endpoint == "compile/create" for endpoint, _ in state.calls) == 1
    assert sum(endpoint == "backtests/create" for endpoint, _ in state.calls) == 1


def test_inherited_exact_reconciliation_is_unchanged():
    for name in ("inspect", "complete", "compile_once", "poll_compile", "_files", "_rpc", "_event", "_compile_state"):
        assert getattr(m.FinalRecovery, name) is getattr(m.frozen.RemoteRecovery, name)


@pytest.mark.parametrize("key,value,code", [
    ("projectId", True, "owned_project_id"), ("projectId", m.PROJECT_ID + 1, "owned_project_id"),
    ("organizationId", "b" * 32, "owned_organization"), ("organizationId", None, "owned_organization"),
    ("organizationId", "a" * 31, "owned_organization"), ("organizationId", "A" * 32, "owned_organization"),
    ("name", "different project", "owned_name"), ("language", "C#", "owned_language"),
    ("owner", False, "owned_owner"), ("owner", 1, "owned_owner"),
    ("public", True, "owned_private"), ("public", 0, "owned_private"),
    ("codeRunning", True, "owned_idle"), ("codeRunning", 0, "owned_idle"),
    ("collaborators", None, "owned_collaborators"), ("collaborators", [{"owner": False}], "owned_collaborators"),
    ("collaborators", [{"owner": True}] * 2, "owned_collaborators"),
    ("collaborators", [{"owner": 1}], "owned_collaborators"),
])
def test_split_ownership_refusals_preserve_finite_predicate(state, key, value, code):
    state.project[key] = value
    with pytest.raises(m.RecoveryError, match="^" + code + "$") as caught:
        state.remote.inspect()
    assert m.finite_error(caught.value) == {"helper_code": code, "predicate": m.OWNERSHIP_PREDICATES[code]}
    assert len(state.calls) == 1 and writes(state) == []


@pytest.mark.parametrize("key,code", [
    ("projectId", "owned_project_id"), ("organizationId", "owned_organization"),
    ("name", "owned_name"), ("language", "owned_language"), ("owner", "owned_owner"),
    ("codeRunning", "owned_idle"), ("collaborators", "owned_collaborators"),
])
def test_missing_required_ownership_field_refuses(state, key, code):
    del state.project[key]
    with pytest.raises(m.RecoveryError, match="^" + code + "$"):
        state.remote.inspect()
    assert writes(state) == []


@pytest.mark.parametrize("collaborators", [[], [{"owner": True}]])
def test_frozen_optional_public_and_owner_only_shapes_remain_supported(state, collaborators):
    del state.project["public"]
    state.project["collaborators"] = collaborators
    assert len(state.remote.inspect()["files"]) == 1
    assert not hasattr(state.remote, "_organization")


@pytest.mark.parametrize("value", [None, [], [{}, {}], [False]])
def test_project_shape_refuses(state, value):
    state.mutation = lambda endpoint, payload, result: result.update(projects=value) if endpoint == "projects/read" else None
    with pytest.raises(m.RecoveryError, match="^project_shape$"):
        state.remote.inspect()
    assert writes(state) == []


@pytest.mark.parametrize("value", [None, "", "a" * 64, "a" * 32, True])
def test_fixed_organization_hash_is_mandatory(state, value):
    with pytest.raises(m.RecoveryError, match="^organization_pin$"):
        m.FinalRecovery(state.projection, value, state.request, state.journal)
    assert state.calls == state.events == []


def test_actual_source_bytes_must_match_manifest(state):
    state.projection.source_files[0].source_bytes += b"# changed\n"
    with pytest.raises(m.RecoveryError, match="^source_manifest_binding$"):
        m.FinalRecovery(state.projection, state.organization_pin, state.request, state.journal)
    assert state.calls == []


@pytest.mark.parametrize("value", ["R298", "R299", "arv2-newrule-8-ar0-2026-v1", "arv2-newrule-6-ar100-2026-v1"])
def test_family_cell_id_or_changed_strategy_identity_does_not_replace_projection_identity(state, value):
    record = state.projection.to_record()
    record["candidate_id"] = value
    state.projection.to_record = lambda: record
    with pytest.raises(m.RecoveryError, match="^projection_binding$"):
        m.FinalRecovery(state.projection, state.organization_pin, state.request, state.journal)
    assert state.calls == []


def test_already_exact_sources_are_never_overwritten(state):
    exact(state)
    initial = state.remote.inspect()
    assert state.remote.complete(initial) == initial
    assert writes(state) == []


def test_unknown_cloud_content_is_not_overwritten(state):
    state.files["main.py"] += "# concurrent edit\n"
    with pytest.raises(m.RecoveryError, match="^unexpected_cloud_content$"):
        state.remote.inspect()
    assert writes(state) == []


def test_evolving_source_readback_detects_mutation(state):
    initial = state.remote.inspect()
    def mutate(endpoint, payload, result):
        if endpoint in ("files/create", "files/update"):
            state.files[payload["name"]] += "# altered remotely\n"
    state.mutation = mutate
    with pytest.raises(m.RecoveryError, match="^unexpected_cloud_content$"):
        state.remote.complete(initial)
    assert len(writes(state)) == 1


def test_final_readback_precedes_compile(state):
    exact(state)
    initial = state.remote.inspect()
    completed = state.remote.complete(initial)
    state.files["main.py"] = "#"
    with pytest.raises(m.RecoveryError, match="^unexpected_cloud_content$"):
        state.remote.compile_once(completed)
    assert writes(state) == []


def test_old_a2_receipt_refuses_without_dispatch(state):
    old = receipt()
    old["backtest_name"] = old["backtest_name"].replace(" A3 ", " A2 ")
    with pytest.raises(m.RecoveryError, match="^launch_receipt$"):
        state.remote.read_status(old, 0)
    assert state.calls == []


def test_existing_a2_or_any_prior_run_blocks_new_launch(state):
    exact(state)
    state.prior_runs = [{"backtestId": "old", "name": m.BACKTEST_NAME.replace(" A3 ", " A2 ")}]
    with pytest.raises(m.RecoveryError, match="^prior_backtests$"):
        state.remote.launch_once("compile-a3")
    assert writes(state) == []


def test_capacity_busy_wait_never_creates_or_changes_job(state):
    exact(state)
    state.busy = True
    assert state.remote.launch_once("compile-a3") == {"project_id": m.PROJECT_ID, "state": "wait", "available_count": 0}
    assert writes(state) == []
    with pytest.raises(m.RecoveryError, match="^duplicate_or_endpoint$"):
        state.remote.launch_once("compile-a3")
    assert writes(state) == []


def test_duplicate_launch_refuses_before_second_dispatch(state):
    exact(state)
    state.remote.launch_once("compile-a3")
    count = len(state.calls)
    with pytest.raises(m.RecoveryError, match="^duplicate_or_endpoint$"):
        state.remote.launch_once("compile-a3")
    assert len(state.calls) == count
    assert sum(endpoint == "backtests/create" for endpoint, _ in state.calls) == 1


def test_duplicate_status_observation_refuses(state):
    state.prior_runs = [{"projectId": m.PROJECT_ID, "backtestId": "run-a3", "name": m.BACKTEST_NAME, "status": "In Progress..."}]
    state.remote.read_status(receipt(), 0)
    with pytest.raises(m.RecoveryError, match="^duplicate_or_endpoint$"):
        state.remote.read_status(receipt(), 0)
    assert len(state.calls) == 1


@pytest.mark.parametrize("status", ["In Queue...", "In Progress...", "Completed.", "Runtime Error"])
def test_exact_status_is_not_success_or_outcome_acceptance(state, status):
    state.prior_runs = [{"projectId": m.PROJECT_ID, "backtestId": "run-a3", "name": m.BACKTEST_NAME,
        "status": status, "statistics": {"private": "SECRET"}, "error": "SECRET"}]
    observed = state.remote.read_status(receipt(), 0)
    assert observed == {**receipt(), "status": status}
    assert "SECRET" not in repr(observed)
    assert state.calls == [("backtests/list", {"projectId": m.PROJECT_ID, "includeStatistics": False})]


@pytest.mark.parametrize("field,value", [("name", m.BACKTEST_NAME.replace(" A3 ", " A2 ")),
    ("backtestId", "other"), ("projectId", True), ("status", "Completed")])
def test_status_mismatched_identity_and_terminal_spelling_refuse(state, field, value):
    row = {"projectId": m.PROJECT_ID, "backtestId": "run-a3", "name": m.BACKTEST_NAME, "status": "In Progress..."}
    row[field] = value
    state.prior_runs = [row]
    with pytest.raises(m.RecoveryError, match="^backtest_status$"):
        state.remote.read_status(receipt(), 0)


@pytest.mark.parametrize("code", sorted(m.FINITE_CODES))
def test_all_finite_codes_preserved_without_raw_text(code):
    assert m.finite_error(m.RecoveryError(code)) == {"helper_code": code, "predicate": m.OWNERSHIP_PREDICATES.get(code)}


@pytest.mark.parametrize("args", [(), ("SECRET",), ("owned_idle", "SECRET"), (b"owned_idle",), ("x" * 97,), (None,)])
def test_unknown_or_noncanonical_args_are_not_exposed(args):
    assert m.finite_error(m.RecoveryError(*args)) == {"helper_code": "unknown", "predicate": None}


def test_hostile_strings_and_subclasses_are_not_invoked():
    class Hostile(str):
        def __hash__(self):
            raise AssertionError("hash must not run")
        def __len__(self):
            raise AssertionError("length must not run")
        def __str__(self):
            raise AssertionError("string must not run")
    class ChildError(m.RecoveryError):
        @property
        def args(self):
            raise AssertionError("args property must not run")
    for error in (m.RecoveryError(Hostile("owned_idle")), ChildError("owned_idle"), ValueError("owned_idle")):
        assert m.finite_error(error) == {"helper_code": "unknown", "predicate": None}


@pytest.fixture(scope="module")
def genuine_projection():
    from scripts import arv2_r298_recovery_evidence as evidence
    return evidence.reconstruct_projection()


def test_genuine_public_projection_constructs_without_a_client(genuine_projection):
    from scripts import arv2_r298_recovery_evidence as evidence
    assert m.ORGANIZATION_SHA256 == evidence.ORGANIZATION
    projected = genuine_projection
    def forbidden(*args):
        pytest.fail("pure construction must not dispatch or journal")
    runner = m.FinalRecovery(projected, m.ORGANIZATION_SHA256, forbidden, forbidden)
    record = projected.to_record()
    assert record["candidate_id"] == m.PROJECTION_CANDIDATE_ID == "arv2-newrule-6-ar0-2026-v1"
    assert m._sha(projected.record_bytes) == evidence.PROJECTION == m.PROJECTION_SHA256
    assert len(runner._sources) == 11
    assert record["source_files"] == [{"project_path": name, "byte_count": len(raw),
        "content_sha256": m._sha(raw)} for name, raw in runner._sources.items()]
    assert all(raw.isascii() and 0 < len(raw) <= 64000 for raw in runner._sources.values())
    assert not hasattr(runner, "_organization")
    # The spent helper deterministically rejects this same genuine projection
    # before any injected request or journal callback. It stays unmodified.
    with pytest.raises(m.RecoveryError, match="^projection_binding$"):
        m.frozen.RemoteRecovery(projected, "a" * 32, forbidden, forbidden)


@pytest.mark.parametrize("kind", ["candidate", "schema", "record_bytes", "source_bytes"])
def test_genuine_projection_identity_and_true_bytes_cannot_be_rebound(genuine_projection, kind):
    projected = genuine_projection
    if kind in ("candidate", "schema"):
        record = projected.to_record()
        record["candidate_id" if kind == "candidate" else "schema"] = "R298" if kind == "candidate" else "different-schema"
        raw = m._canonical(record)
        projected = dataclasses.replace(projected, record_bytes=raw, projection_sha256=m._sha(raw))
    elif kind == "record_bytes":
        projected = dataclasses.replace(projected, record_bytes=projected.record_bytes + b" ")
    else:
        files = list(projected.source_files)
        files[0] = dataclasses.replace(files[0], source_bytes=files[0].source_bytes + b"# changed\n")
        projected = dataclasses.replace(projected, source_files=tuple(files))
    def forbidden(*args):
        pytest.fail("refused projection must not dispatch or journal")
    with pytest.raises(ValueError):
        m.FinalRecovery(projected, m.ORGANIZATION_SHA256, forbidden, forbidden)


def test_fixed_finite_inventory_covers_both_helpers_literal_refusals():
    import ast
    from pathlib import Path
    def literals(module):
        tree = ast.parse(Path(module.__file__).read_text())
        return {node.args[-1].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"_require", "RecoveryError"} and node.args
            and isinstance(node.args[-1], ast.Constant) and type(node.args[-1].value) is str}
    old, current = literals(m.frozen), literals(m)
    assert len(old) == 36 and old <= m.FINITE_CODES
    assert current <= m.FINITE_CODES and len(m.FINITE_CODES) == 45


def test_length_guard_precedes_allowlist_lookup(monkeypatch):
    class ForbiddenLookup:
        def __contains__(self, value):
            raise AssertionError("oversized message must not reach lookup")
    monkeypatch.setattr(m, "FINITE_CODES", ForbiddenLookup())
    assert m.finite_error(m.RecoveryError("x" * 97)) == {"helper_code": "unknown", "predicate": None}


def test_module_has_no_operational_io_imports():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports == {"json", "re"}
    assert all(node.module == "scripts" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
