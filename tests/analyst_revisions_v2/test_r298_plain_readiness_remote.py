"""Injected public-source/response fixtures, never an operational QC client."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_plain_readiness_remote as m


@pytest.fixture
def cloud(monkeypatch):
    organization = "a" * 32
    organization_pin = m.sha(organization.encode("ascii"))
    monkeypatch.setattr(m.access, "ORGANIZATION_SHA256", organization_pin)
    monkeypatch.setattr(m.predecessor.diagnostic.projection, "ORGANIZATION_SHA256", organization_pin)
    old = {name: ("# synthetic frozen " + name + "\n").encode("ascii") for name in m.SOURCE_NAMES}
    sources = dict(old, **{"main.py": b"# synthetic plain package main\n",
        "accepted_risk_order_level_input_runtime.py": b"# synthetic plain JSONL loader\n"})
    pairs = tuple(sorted(sources.items()))
    record = {"schema": "arv2-r298-plain-projection-v1", "candidate_id": "R298",
        "package_sha256": m.PACKAGE_SHA256, "profile_sha256": m.PROFILE_SHA256,
        "activation_manifest_sha256": m.ACTIVATION_SHA256,
        "source_files": [{"project_path": name, "byte_count": len(raw), "content_sha256": m.sha(raw)}
            for name, raw in pairs]}
    record_bytes = m.canonical(record)[:-1]
    monkeypatch.setattr(m, "PROJECTION_SHA256", m.sha(record_bytes))
    monkeypatch.setattr(m.evidence, "reconstruct_projection", lambda: SimpleNamespace(source_files=tuple(
        SimpleNamespace(project_path=name, source_bytes=raw) for name, raw in old.items())))
    owner = {"owner": True, "uid": 123, "publicId": "synthetic-owner", "name": "Synthetic Owner",
        "permission": "write", "liveControl": True}
    extra = {"owner": False, "uid": None, "publicId": m.CODE_SOURCE_ID, "name": m.CODE_SOURCE_ID,
        "permission": "write", "liveControl": True, "test-only-extra": 7}
    monkeypatch.setattr(m.access, "OWNER_ROW_SHA256", m.sha(m.canonical(owner)))
    monkeypatch.setattr(m.access, "A5_ROW_SHA256", m.sha(m.canonical(extra)))
    manual = {"projectId": m.PROJECT_ID, "backtestId": m.predecessor.MANUAL_BACKTEST_ID,
        "name": m.predecessor.MANUAL_BACKTEST_NAME, "status": "Completed."}
    state = SimpleNamespace(sources=sources, old=old, pairs=pairs, record=record, record_bytes=record_bytes,
        owner=owner, extra=extra, manual=manual, calls=[], events=[], observations=[], mutation=None,
        prior=[copy.deepcopy(manual)], compile_state="BuildSuccess", compile_id="compile-a11",
        files={"main.py": m.DEFAULT_MAIN.decode("ascii"), "accepted_risk_order_level_input_runtime.py": "#",
            **{name: sources[name].decode("ascii") for name in m.RETAINED}})
    state.project = {"projectId": m.PROJECT_ID, "organizationId": organization, "ownerId": 123,
        "name": m.access.PROJECT_NAME, "language": "Py", "owner": True,
        "codeRunning": False, "collaborators": [copy.deepcopy(owner)]}
    state.dedicated = {"collaborators": [copy.deepcopy(owner)], "userPermissions": "write", "userLiveControl": True}
    def journal(marker, event):
        assert not any(old_marker == marker and old_event["event"] == event["event"]
            for old_marker, old_event in state.events)
        state.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert state.events[-1][1] == {"event": "intent", "endpoint": endpoint, "sha256": m.sha(m.canonical(payload))}
        state.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == "projects/read":
            result = {"projects": [copy.deepcopy(state.project)]}
        elif endpoint == m.COLLABORATION_ENDPOINT:
            result = copy.deepcopy(state.dedicated)
        elif endpoint == m.LOCK_ENDPOINT:
            result = {}
        elif endpoint == "backtests/list":
            result = {"backtests": copy.deepcopy(state.prior), "count": len(state.prior), "projectId": m.PROJECT_ID}
        elif endpoint == "files/read":
            result = {"files": [{"projectId": m.PROJECT_ID, "name": name, "content": content}
                for name, content in state.files.items()]}
        elif endpoint in ("files/create", "files/update"):
            assert (payload["name"] in state.files) is (endpoint == "files/update")
            assert payload["content"].encode("ascii") == state.sources[payload["name"]]
            state.files[payload["name"]] = payload["content"]
            result = {}
        elif endpoint == "compile/create":
            result = {"projectId": m.PROJECT_ID, "compileId": state.compile_id}
        elif endpoint == "compile/read":
            result = {"projectId": m.PROJECT_ID, "compileId": payload["compileId"], "state": state.compile_state}
        else:
            pytest.fail("forbidden endpoint reached injected transport")
        result["success"] = True
        if state.mutation:
            state.mutation(endpoint, payload, result)
        return result
    def observe(marker, packet):
        assert marker == packet["stage"] + "-access"
        assert state.events[-1][0] == packet["stage"] + "-collaborators"
        state.observations.append((marker, copy.deepcopy(packet)))
    state.request, state.journal, state.observe = request, journal, observe
    state.runner = m.PlainReadiness(record_bytes, pairs, request=request, journal=journal, observe_access=observe)
    return state


def compile_candidate(cloud, polls=0):
    inspected = cloud.runner.inspect()
    completed = cloud.runner.complete(inspected)
    compiled = cloud.runner.compile_once(completed)
    for index in range(polls):
        cloud.runner.poll_compile(compiled["compile_id"], index)
    return inspected, completed, compiled


def test_public_fixed_contract_and_default_main_import():
    assert m.ATTEMPT == 11 and m.PROJECT_ID == 38364439
    assert m.DEFAULT_MAIN is m.predecessor.frozen.frozen.DEFAULT_MAIN
    assert m.PROJECTION_SHA256 == "9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5"
    assert m.PACKAGE_SHA256 == "1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2"
    assert m.PROFILE_SHA256 == "89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e"
    assert m.ACTIVATION_SHA256 == "ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b"
    assert len(m.SOURCE_NAMES) == 11
    assert not hasattr(m.PlainReadiness, "launch_once") and not hasattr(m.PlainReadiness, "read_status")


def test_packet_exact_digest_and_immutable_public_sources(cloud):
    record, files = m.validate_public_packet(cloud.record_bytes, cloud.pairs)
    assert record == cloud.record and files == cloud.sources
    record["source_files"].clear()
    files["main.py"] = b"changed"
    assert cloud.runner._sources["main.py"] == cloud.sources["main.py"]
    with pytest.raises(m.Refused, match="^binding$"):
        m.validate_public_packet(cloud.record_bytes + b"\n", cloud.pairs)


@pytest.mark.parametrize("change", ["hash", "list", "missing", "duplicate", "unknown", "nonascii", "oversized", "order"])
def test_packet_source_mismatch_refuses_before_any_callback(cloud, change):
    pairs = list(cloud.pairs)
    if change == "hash":
        pairs[0] = (pairs[0][0], b"# different\n")
    elif change == "missing":
        pairs.pop()
    elif change == "duplicate":
        pairs[0] = pairs[1]
    elif change == "unknown":
        pairs[0] = ("unexpected.py", pairs[0][1])
    elif change == "nonascii":
        pairs[0] = (pairs[0][0], b"\xff")
    elif change == "oversized":
        pairs[0] = (pairs[0][0], b"x" * 64001)
    elif change == "order":
        pairs.reverse()
    with pytest.raises(m.Refused):
        m.PlainReadiness(cloud.record_bytes, pairs if change == "list" else tuple(pairs),
            request=cloud.request, journal=cloud.journal, observe_access=cloud.observe)
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize("name", ["accepted_risk_order_level_core.py", "accepted_risk_order_level_forced_exit.py"])
def test_nine_unchanged_modules_verified_against_public_parent(cloud, monkeypatch, name):
    assert name in m.SOURCE_NAMES
    sources = dict(cloud.sources)
    sources[name] += b"# unexpected economic implementation change\n"
    pairs = tuple(sorted(sources.items()))
    record = copy.deepcopy(cloud.record)
    record["source_files"] = [{"project_path": path, "byte_count": len(raw), "content_sha256": m.sha(raw)}
        for path, raw in pairs]
    raw = m.canonical(record)[:-1]
    monkeypatch.setattr(m, "PROJECTION_SHA256", m.sha(raw))
    with pytest.raises(m.Refused, match="^old_sources$"):
        m.PlainReadiness(raw, pairs, request=cloud.request, journal=cloud.journal, observe_access=cloud.observe)
    assert cloud.calls == []


def test_full_source_compile_ready_flow_has_no_capacity_or_launch(cloud):
    inspected, completed, compiled = compile_candidate(cloud, polls=20)
    receipt = cloud.runner.ready_once(compiled)
    assert len(inspected["files"]) == 4 and len(completed["files"]) == 11
    assert len(cloud.calls) == 57
    assert receipt["schema"] == m.READY_SCHEMA and receipt["attempt"] == 11
    assert receipt["state"] == "compiled_exact_source_ready" and receipt["compile_id"] == "compile-a11"
    assert receipt["source_manifest_sha256"] == m.sha(m.canonical(completed))
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    writes = [(endpoint, payload) for endpoint, payload in cloud.calls if endpoint in ("files/create", "files/update")]
    assert len(writes) == len({payload["name"] for _, payload in writes}) == 9
    assert sum(endpoint == "files/create" for endpoint, _ in writes) == 7
    assert sum(endpoint == "files/update" for endpoint, _ in writes) == 2
    assert sum(endpoint == m.LOCK_ENDPOINT for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == "compile/create" for endpoint, _ in cloud.calls) == 1
    for index, (endpoint, _) in enumerate(cloud.calls):
        if endpoint in ("files/create", "files/update"):
            assert cloud.calls[index + 1][0] == "files/read"
    assert [marker for marker, _ in cloud.observations] == [stage + "-access" for stage in ("inspect", "complete", "compile", "ready")]
    assert cloud.files == {name: raw.decode("ascii") for name, raw in cloud.sources.items()}
    assert not any(endpoint in ("projects/nodes/read", "backtests/create", "backtests/read") for endpoint, _ in cloud.calls)


@pytest.mark.parametrize("endpoint", ["projects/nodes/read", "backtests/create", "backtests/read",
    "backtests/orders/read", "projects/create", "files/delete", "projects/collaboration/delete",
    "projects/collaboration/update", "live/create"])
def test_forbidden_endpoints_refuse_before_intent(cloud, endpoint):
    with pytest.raises(m.Refused, match="^endpoint$"):
        cloud.runner._rpc("forbidden", endpoint, {"projectId": m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize("marker", ["any-history", "launch-backtests", "ready-backtests-other"])
def test_manual_history_endpoint_requires_exact_owned_stage_marker(cloud, marker):
    with pytest.raises(m.Refused):
        cloud.runner._rpc(marker, "backtests/list", {"projectId": m.PROJECT_ID, "includeStatistics": False})
    assert cloud.calls == cloud.events == []


def test_compile_create_cannot_dispatch_outside_compile_once(cloud):
    with pytest.raises(m.Refused):
        cloud.runner._rpc("forged-compile", "compile/create", {"projectId": m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize("method", ["rpc", "state"])
def test_direct_compile_reads_cannot_bypass_sequential_poll_gate(cloud, method):
    _, _, compiled = compile_candidate(cloud)
    count = len(cloud.calls)
    with pytest.raises(m.Refused):
        if method == "rpc":
            cloud.runner._rpc("compile-poll-000", "compile/read",
                {"projectId": m.PROJECT_ID, "compileId": compiled["compile_id"]})
        else:
            cloud.runner._compile_state(compiled["compile_id"], "compile-poll-019")
    assert len(cloud.calls) == count


@pytest.mark.parametrize("change", ["scope", "code_source", "content", "without_stage"])
def test_file_write_gate_rejects_unbound_direct_dispatch(cloud, change):
    cloud.runner.inspect()
    payload = {"projectId": m.PROJECT_ID, "name": "main.py", "content": cloud.sources["main.py"].decode("ascii")}
    if change == "scope":
        payload["projectId"] = True
    elif change == "code_source":
        payload["codeSourceId"] = "different-agent"
    elif change == "content":
        payload["content"] = "# changed economics\n"
    count = len(cloud.calls)
    with pytest.raises(m.Refused):
        cloud.runner._rpc("forged-write", "files/update", payload)
    assert len(cloud.calls) == count


@pytest.mark.parametrize("mode", ["owner", "owner_a5"])
def test_current_owner_or_exact_a5_preserves_strict_access_policy(cloud, mode):
    if mode == "owner_a5":
        cloud.project["collaborators"].append(copy.deepcopy(cloud.extra))
    cloud.runner.inspect()
    packet = cloud.observations[0][1]
    assert packet["project_observation"]["collaborators"]["count"] == (2 if mode == "owner_a5" else 1)
    assert packet["dedicated_observation"]["collaborators"]["count"] == 1
    m.predecessor.validate_access_observation(packet)


@pytest.mark.parametrize("change", ["owner_hash", "a5_hash", "mia", "third", "permission", "live", "busy", "public"])
def test_access_refusal_keeps_safe_observation_before_history_or_lock(cloud, change):
    cloud.project["collaborators"].append(copy.deepcopy(cloud.extra))
    if change == "owner_hash":
        cloud.project["collaborators"][0]["synthetic_changed"] = 1
        cloud.dedicated["collaborators"][0]["synthetic_changed"] = 1
    elif change == "a5_hash":
        cloud.project["collaborators"][1]["test-only-extra"] = 8
    elif change == "mia":
        cloud.project["collaborators"][1]["name"] = "Mia"
    elif change == "third":
        cloud.project["collaborators"].append(copy.deepcopy(cloud.extra))
    elif change == "permission":
        cloud.dedicated["userPermissions"] = "read"
    elif change == "live":
        cloud.dedicated["userLiveControl"] = False
    elif change == "busy":
        cloud.project["codeRunning"] = True
    else:
        cloud.project["public"] = True
    with pytest.raises(m.access.AccessRefused):
        cloud.runner.inspect()
    assert [endpoint for endpoint, _ in cloud.calls] == ["projects/read", m.COLLABORATION_ENDPOINT]
    assert len(cloud.observations) == 1


def test_observation_sink_failure_blocks_history_and_lock(cloud):
    def refuse(*_):
        raise RuntimeError("synthetic sink failure")
    cloud.runner._observe_access = refuse
    with pytest.raises(RuntimeError, match="synthetic sink failure"):
        cloud.runner.inspect()
    assert [endpoint for endpoint, _ in cloud.calls] == ["projects/read", m.COLLABORATION_ENDPOINT]


def test_intent_sink_failure_prevents_request_and_spends_inspection(cloud):
    cloud.runner._journal = lambda *_: True
    with pytest.raises(m.Refused, match="^journal$"):
        cloud.runner.inspect()
    assert cloud.calls == []
    with pytest.raises(m.Refused, match="^inspect_once$"):
        cloud.runner.inspect()


@pytest.mark.parametrize("change", ["new", "missing", "name", "status", "count", "project"])
def test_only_exact_preexisting_manual_history_is_allowed(cloud, change):
    if change == "new":
        cloud.prior.append(dict(cloud.manual, backtestId="different"))
    elif change == "missing":
        cloud.prior.clear()
    elif change == "name":
        cloud.prior[0]["name"] = "different"
    elif change == "status":
        cloud.prior[0]["status"] = "In Progress..."
    else:
        def mutation(endpoint, _payload, result):
            if endpoint == "backtests/list":
                result["count" if change == "count" else "projectId"] = 999
        cloud.mutation = mutation
    with pytest.raises((m.Refused, m.predecessor.RecoveryError)):
        cloud.runner.inspect()
    assert len(cloud.calls) == 3


@pytest.mark.parametrize("name", ["main.py", "accepted_risk_order_level_input_runtime.py"])
@pytest.mark.parametrize("variant", ["old", "new", "stub", "stub_lf"])
def test_only_transitioned_files_admit_exact_old_new_or_stub(cloud, name, variant):
    raw = {"old": cloud.old[name], "new": cloud.sources[name], "stub": b"#", "stub_lf": b"#\n"}[variant]
    cloud.files[name] = raw.decode("ascii")
    cloud.runner.inspect()


def test_other_present_module_placeholder_is_not_a_source_transition(cloud):
    name = next(name for name in sorted(m.SOURCE_NAMES - m.RETAINED)
        if name not in ("main.py", "accepted_risk_order_level_input_runtime.py"))
    cloud.files[name] = "#"
    with pytest.raises(m.Refused, match="^cloud_content$"):
        cloud.runner.inspect()


@pytest.mark.parametrize("change", ["unknown", "duplicate", "project", "nonascii", "oversized", "unexpected_source"])
def test_inventory_refuses_unbound_cloud_files(cloud, change):
    def mutation(endpoint, _payload, result):
        if endpoint != "files/read":
            return
        row = result["files"][0]
        if change == "unknown":
            row["name"] = "unknown.py"
        elif change == "duplicate":
            result["files"].append(dict(row))
        elif change == "project":
            row["projectId"] = True
        elif change == "nonascii":
            row["content"] = "\u2603"
        elif change == "oversized":
            row["content"] = "x" * 64001
        else:
            row["content"] = "# arbitrary code\n"
    cloud.mutation = mutation
    with pytest.raises(m.Refused):
        cloud.runner.inspect()


def test_single_lock_and_inspection_even_after_refusal(cloud):
    cloud.runner.inspect()
    calls = len(cloud.calls)
    with pytest.raises(m.Refused, match="^inspect_once$"):
        cloud.runner.inspect()
    with pytest.raises(m.Refused):
        cloud.runner._rpc("another-lock", m.LOCK_ENDPOINT, {"projectId": m.PROJECT_ID, "codeSourceId": m.CODE_SOURCE_ID})
    assert len(cloud.calls) == calls


def test_source_change_between_inspect_and_complete_blocks_all_writes(cloud):
    original = cloud.runner.inspect()
    cloud.files["main.py"] = cloud.sources["main.py"].decode("ascii")
    with pytest.raises(m.Refused, match="^changed$"):
        cloud.runner.complete(original)
    assert not any(endpoint in ("files/create", "files/update") for endpoint, _ in cloud.calls)


def test_readback_changed_after_first_write_stops_without_next_write(cloud):
    original = cloud.runner.inspect()
    def mutation(endpoint, _payload, result):
        if endpoint == "files/read" and any(name in ("files/create", "files/update") for name, _ in cloud.calls):
            result["files"][0]["content"] = "# unexpected source\n"
    cloud.mutation = mutation
    with pytest.raises(m.Refused):
        cloud.runner.complete(original)
    assert sum(endpoint in ("files/create", "files/update") for endpoint, _ in cloud.calls) == 1
    with pytest.raises(m.Refused, match="^complete_once$"):
        cloud.runner.complete(original)


def test_complete_with_all_exact_files_makes_no_write(cloud):
    cloud.files = {name: raw.decode("ascii") for name, raw in cloud.sources.items()}
    original = cloud.runner.inspect()
    result = cloud.runner.complete(original)
    assert len(result["files"]) == 11
    assert not any(endpoint in ("files/create", "files/update") for endpoint, _ in cloud.calls)


def test_failed_write_consumed_once_no_retry_and_no_compile(cloud):
    original = cloud.runner.inspect()
    def mutation(endpoint, _payload, result):
        if endpoint in ("files/create", "files/update"):
            result["success"] = False
    cloud.mutation = mutation
    with pytest.raises(m.Refused, match="^response$"):
        cloud.runner.complete(original)
    assert len(cloud.runner._written) == 1
    assert sum(endpoint in ("files/create", "files/update") for endpoint, _ in cloud.calls) == 1
    assert not any(endpoint == "compile/create" for endpoint, _ in cloud.calls)
    with pytest.raises(m.Refused, match="^complete_once$"):
        cloud.runner.complete(original)


@pytest.mark.parametrize("key,value", [("compile_id", "forged"), ("source_manifest_sha256", "0" * 64),
    ("project_id", True), ("projection_sha256", "0" * 64)])
def test_ready_requires_exact_locally_created_compile_receipt(cloud, key, value):
    _, _, compiled = compile_candidate(cloud)
    compiled[key] = value
    count = len(cloud.calls)
    with pytest.raises(m.Refused):
        cloud.runner.ready_once(compiled)
    assert len(cloud.calls) == count


def test_compile_once_cannot_repeat_or_run_without_completion(cloud):
    with pytest.raises(m.Refused, match="^compile_once$"):
        cloud.runner.compile_once({})
    _, completed, _ = compile_candidate(cloud)
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match="^compile_once$"):
        cloud.runner.compile_once(completed)
    assert len(cloud.calls) == count


@pytest.mark.parametrize("index", [True, -1, 1, 20])
def test_poll_indices_start_zero_and_are_strict_integers(cloud, index):
    _, _, compiled = compile_candidate(cloud)
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match="^compile_poll$"):
        cloud.runner.poll_compile(compiled["compile_id"], index)
    assert len(cloud.calls) == count


def test_twenty_polls_are_finite_and_no_repeated_index(cloud):
    _, _, compiled = compile_candidate(cloud, polls=20)
    count = len(cloud.calls)
    for index in (19, 20):
        with pytest.raises(m.Refused, match="^compile_poll$"):
            cloud.runner.poll_compile(compiled["compile_id"], index)
    assert len(cloud.calls) == count


@pytest.mark.parametrize("state", ["InQueue", "Building", "BuildError", "Completed.", None, True])
def test_readiness_requires_fresh_successful_compile(cloud, state):
    _, _, compiled = compile_candidate(cloud)
    cloud.compile_state = state
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match="^compile_state$"):
        cloud.runner.ready_once(compiled)
    assert [endpoint for endpoint, _ in cloud.calls[count:]] == ["compile/read"]


@pytest.mark.parametrize("change", ["missing", "stub", "old", "unexpected"])
def test_readiness_rechecks_fresh_exact_eleven_source_inventory(cloud, change):
    _, _, compiled = compile_candidate(cloud)
    if change == "missing":
        del cloud.files["main.py"]
    elif change == "stub":
        cloud.files["main.py"] = "#"
    elif change == "old":
        cloud.files["main.py"] = cloud.old["main.py"].decode("ascii")
    else:
        cloud.files["main.py"] = "# unknown\n"
    count = len(cloud.calls)
    with pytest.raises(m.Refused):
        cloud.runner.ready_once(compiled)
    assert [endpoint for endpoint, _ in cloud.calls[count:]] == ["compile/read", "projects/read",
        m.COLLABORATION_ENDPOINT, "backtests/list", "files/read"]


def test_readiness_is_one_use_and_does_not_authorize_launch(cloud):
    _, _, compiled = compile_candidate(cloud)
    cloud.runner.ready_once(compiled)
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match="^ready_once$"):
        cloud.runner.ready_once(compiled)
    assert len(cloud.calls) == count


def test_ready_full_manifest_hash_not_only_count_or_names(cloud, monkeypatch):
    _, _, compiled = compile_candidate(cloud)
    original = cloud.runner._files
    def substituted(marker, **kwargs):
        value = original(marker, **kwargs)
        if marker == "ready-files":
            value["files"][0]["sha256"] = "0" * 64
        return value
    monkeypatch.setattr(cloud.runner, "_files", substituted)
    with pytest.raises(m.Refused, match="^changed$"):
        cloud.runner.ready_once(compiled)


def test_safe_finite_exception_classifier():
    class Hostile(ValueError):
        def __str__(self):
            raise AssertionError("no exception serialization")
    assert m.finite(Hostile("synthetic-secret")) == "unknown"
    assert m.finite(m.Refused("changed")) == "changed"
    assert m.finite(m.Refused("untrusted-text")) == "unknown"


def test_output_ready_receipt_is_detached_and_performs_no_rpc(cloud):
    _, _, compiled = compile_candidate(cloud)
    ready = cloud.runner.ready_once(compiled)
    count = len(cloud.calls)
    result = m.validate_ready_receipt(ready, expected_source_manifest_sha256=compiled['source_manifest_sha256'])
    assert result == ready and result is not ready and len(cloud.calls) == count


@pytest.mark.parametrize('key,value', [
    ('schema', 'other'), ('project_id', True), ('project_id', 1), ('attempt', True),
    ('attempt', 10), ('compile_id', ''), ('compile_id', True), ('compile_id', 'x' * 129),
    ('compile_id', 'a b'), ('projection_sha256', '0' * 64),
    ('source_manifest_sha256', '0' * 64), ('state', 'Completed.'),
    *[(name, item) for name in m.FALSE_FLAGS for item in (True, 0, None)],
])
def test_output_ready_receipt_refuses_wrong_binding_or_type(cloud, key, value):
    _, _, compiled = compile_candidate(cloud)
    ready = cloud.runner.ready_once(compiled)
    ready[key] = value
    with pytest.raises(m.Refused, match='^ready_binding$'):
        m.validate_ready_receipt(ready, expected_source_manifest_sha256=compiled['source_manifest_sha256'])


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'list', 'bad_pin', 'false_pin'])
def test_output_ready_receipt_has_exact_fields_and_external_pin(cloud, mutation):
    _, _, compiled = compile_candidate(cloud)
    ready = cloud.runner.ready_once(compiled)
    pin = compiled['source_manifest_sha256']
    if mutation == 'extra': ready['extra'] = False
    elif mutation == 'missing': del ready['attempt']
    elif mutation == 'list': ready = [ready]
    elif mutation == 'bad_pin': pin = 'bad'
    else: pin = False
    with pytest.raises(m.Refused, match='^ready_binding$'):
        m.validate_ready_receipt(ready, expected_source_manifest_sha256=pin)
