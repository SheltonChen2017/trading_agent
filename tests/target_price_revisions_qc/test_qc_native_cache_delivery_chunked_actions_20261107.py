"""Fixed OFF chunked delivery-dispatch boundaries; synthetic custody/wires only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys

import pytest

from research.target_price_revisions_qc import native_cache_delivery_chunked_actions_20261107 as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)
OWNER, ORG, TOKEN = 123, "a" * 32, "SYNTHETIC-CACHE-ACTIONS-TOKEN"
HEAD, COMPILE_ID, JOB = "a" * 40, "synthetic-cache-compile", "c" * 32
PROBE = "TPR-CACHE-20261104-SYNTHETIC-001"


@pytest.fixture(autouse=True)
def deny_real_effects(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("real credential/network/subprocess forbidden")
    monkeypatch.setattr(m.api.ops, "credential", deny)
    monkeypatch.setattr(m.projects.http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(m.api.subprocess, "run", deny)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def wire(value):
    return m.api._canonical(value)


def source_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in m.REQUIRED_SOURCES}


def registry(sources=None):
    sources = source_hashes() if sources is None else sources
    return {"schema": "tpr-cmp28-five-project-bindings-v1", "round_id": m.projects.ROUND_ID,
        "owner_instruction_sha256": m.CREATION_OWNER_SHA256,
        "git_head": "b" * 40, "adapter_source_sha256": sources[m.api.PROJECTS_MODULE],
        "organization_id": ORG, "owner_id": OWNER, "baseline_receipt_sha256": "d" * 64,
        "privacy_basis": "documented_private_default_and_observed_collaborators",
        "explicit_privacy_flag_observed": False, "independent_native_origin_attested": False,
        "projects": {key: {"project_id": project, "name": m.projects.RESERVED_NAMES[key],
            "organization_id": ORG, "owner_id": OWNER, "language": "Py",
            "create_receipt_sha256": sha(("create-" + key).encode()),
            "read_receipt_sha256": sha(("read-" + key).encode()),
            "collaboration_receipt_sha256": sha(("collab-" + key).encode()),
            "collaborator_count": 1, "nonowner_collaborator_count": 0,
            "collaborators_sha256": "9" * 64} for key, project in m.api.REGISTERED_PROJECTS.items()}}


def fixture_main():
    return m.builder._build_fixture(helper_source=helper_source(), operation_id=PROBE, git_head=HEAD)[0]


def helper_source():
    return (ROOT / m.builder.reader.MODULE).read_bytes()


def files(phase="upload"):
    content = {"main.py": b"# preserved prior diagnostic\n" if phase in ("helper", "upload") else fixture_main(),
        "legacy.py": b"# preserved unused source\n", "research.ipynb": b'{"cells":[]}',
        "mia.ipynb": b'{"cells":[],"opaque":true}'}
    content.update({"historical_"+str(index)+".py": ("# preserved historical "+str(index)+"\n").encode("ascii")
        for index in range(8)})
    if phase != "helper":
        content[m.HELPER_FILENAME] = m.builder.helper_module_source(helper_source())
    return content


def inventory(content):
    return {name: {"bytes": len(raw), "sha256": sha(raw)} for name, raw in content.items()}


def arguments(phase="upload", **changes):
    sources = source_hashes()
    raw = wire(registry(sources))
    args = dict(phase=phase, helper_source=helper_source(), project_bindings_raw=raw,
        expected_project_bindings_sha256=sha(raw), source_hashes=sources,
        operation_id="TPR-CMP29-API-CACHE-SYNTHETIC-" + phase.upper(),
        probe_operation_id=PROBE, git_head=HEAD, latest_owner_instruction_sha256=m.OWNER_SHA256,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(), expires_utc=(NOW+timedelta(seconds=239)).isoformat(),
        diagnostic_attempt=1, attempt_id="TPR-CACHE-ATTEMPT-SYNTHETIC-001",
        diagnostic_look_id="TPR-CACHE-LOOK-SYNTHETIC-001", source_inventory=inventory(files(phase)),
        compile_id=COMPILE_ID if phase in ("build", "launch") else None, compile_evidence=None)
    args.update(changes)
    return args


def action(phase="upload", **changes):
    return m._prepare_fixture(**arguments(phase, **changes))


def body(request, content):
    endpoint, payload = request["endpoint"], request["payload"]
    project = 38609822
    if endpoint == "projects/read":
        return {"success": True, "projects": [{"projectId": project, "organizationId": ORG,
            "ownerId": OWNER, "owner": True, "name": m.projects.RESERVED_NAMES["OFF"],
            "language": "Py", "created": "2026-10-29T12:00:00+00:00", "collaborators": []}]}
    if endpoint == "projects/collaboration/read":
        return {"success": True, "projectId": project, "collaborators": [],
            "userPermissions": "write", "userLiveControl": True}
    if endpoint == "backtests/list":
        return {"success": True, "projectId": project, "backtests": [
            {"backtestId": "d" * 32, "projectId": project, "completed": True, "status": "Completed."}], "count": 1}
    if endpoint == "files/read":
        return {"success": True, "projectId": project, "files": [
            {"name": name, "content": raw.decode("ascii"), "projectId": project} for name, raw in content.items()]}
    if endpoint == "files/create":
        assert payload["name"] == m.HELPER_FILENAME and m.HELPER_FILENAME not in content
        assert payload["content"].encode("ascii") == m.builder.helper_module_source(helper_source())
        content[m.HELPER_FILENAME] = payload["content"].encode("ascii")
        return {"success": True, "projectId": project}
    if endpoint == "files/update":
        assert payload["name"] == "main.py"
        content["main.py"] = payload["content"].encode("ascii")
        return {"success": True, "projectId": project}
    if endpoint in ("compile/create", "compile/read"):
        return {"success": True, "projectId": project, "compileId": COMPILE_ID, "state": "BuildSuccess"}
    if endpoint == "backtests/create":
        return {"success": True, "projectId": project, "backtest": {
            "backtestId": JOB, "projectId": project, "completed": False, "status": "In Queue"}}
    raise AssertionError("unexpected synthetic endpoint")


def backend(a, content=None, effects=None, transform=lambda value, request: value):
    content = files(a["phase"]) if content is None else content
    effects = [] if effects is None else effects
    sequence = iter(m._requests(a))
    def transport(endpoint, raw, seconds, maximum, expected_owner):
        request = next(sequence)
        assert request["endpoint"] == endpoint and json.loads(raw) == request["payload"]
        assert expected_owner == OWNER and seconds == request["seconds"]
        assert maximum == request["max_response_bytes"]
        effects.append(endpoint)
        return wire(transform(body(request, content), request)), 200, TOKEN, OWNER
    return transport


MAC_CUSTODY_REASON = (
    "Owner-selected Mac-only native custody (TPR-CR25-003): POSIX no-follow/UID/mode/directory-fsync "
    "custody is not Windows custody evidence"
)


def execute(tmp_path, a=None, **kwargs):
    # The executor wraps a missing POSIX primitive into ActionRefusal, so off the Mac a
    # positive case would fail and a refusal case would pass vacuously (TPR-CR35-001).
    if sys.platform != "darwin":
        pytest.skip(MAC_CUSTODY_REASON)
    a = action() if a is None else a
    return m._execute_fixture(a, kwargs.pop("root", tmp_path / "cache-actions"),
        transport=kwargs.pop("transport", backend(a)), clock=kwargs.pop("clock", lambda: NOW), **kwargs)


def test_constructor_is_fixed_off_main_only_and_preserves_other_cloud_files():
    a = action()
    requests = m._requests(a)
    assert [row["endpoint"] for row in requests] == ["projects/read", "projects/collaboration/read",
        "backtests/list", "files/read", "files/update", "files/read"]
    assert all(row["payload"]["projectId"] == 38609822 for row in requests)
    assert a["api_plan"]["allowed_source_hashes"] == {"main.py": sha(fixture_main())}
    assert a["source_inventory"]["main.py"] == {"bytes": len(fixture_main()), "sha256": sha(fixture_main())}
    for name, descriptor in a["before_inventory"].items():
        if name != "main.py": assert a["source_inventory"][name] == descriptor
    assert a["api_plan"]["owner_instruction_sha256"] == m.CREATION_OWNER_SHA256
    assert a["latest_owner_instruction_sha256"] == m.OWNER_SHA256


def test_production_never_accepts_the_synthetic_identity_or_fixture_action():
    with pytest.raises(m.ActionRefusal):
        m.prepare_action(parent_probe_config_json="{}", **arguments())
    with pytest.raises(m.ActionRefusal):
        m.execute_action(action())


@pytest.mark.parametrize("changes", [{"phase": "delete"}, {"diagnostic_attempt": True},
    {"operation_id": "TPR-CMP29-API-FOREIGN"}, {"probe_operation_id": "foreign"},
    {"latest_owner_instruction_sha256": "f" * 64}, {"source_hashes": {}},
    {"attempt_id": "financial-attempt"}, {"diagnostic_look_id": "financial-look"},
    {"expires_utc": (NOW+timedelta(seconds=601)).isoformat()}])
def test_open_or_wrong_authority_constructor_refuses(changes):
    args = arguments()
    args.update(changes)
    with pytest.raises(m.ActionRefusal): m._prepare_fixture(**args)


def test_foreign_registered_project_refuses_even_when_registry_is_self_hashed():
    value = registry()
    value["projects"]["OFF"]["project_id"] = 42
    raw = wire(value)
    with pytest.raises(m.ActionRefusal):
        action(project_bindings_raw=raw, expected_project_bindings_sha256=sha(raw))


@pytest.mark.parametrize("fault", ["endpoint", "project", "source", "owner", "extra"])
def test_tampered_action_never_reaches_transport(tmp_path, fault):
    a = action()
    if fault == "endpoint": a["api_plan"]["requests"][1]["endpoint"] = "projects/delete"
    elif fault == "project": a["api_plan"]["project_id"] = 42
    elif fault == "source": a["source_inventory"]["legacy.py"]["sha256"] = "f" * 64
    elif fault == "owner": a["latest_owner_instruction_sha256"] = "f" * 64
    else: a["noneconomic_override"] = True
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, transport=lambda *_: pytest.fail("tamper reached transport"))


def test_durable_claims_precede_every_effect_and_success_is_nonfinancial(tmp_path):
    a, root, effects = action(), tmp_path / "cache-actions", []
    content = files()
    native = backend(a, content, effects)
    requests = m._requests(a)
    def transport(*args):
        request = requests[len(effects)]
        op = a["api_plan"]["operation_id"]
        assert (root / (op + ".action.spent.json")).exists()
        assert (root / (op + "." + request["id"] + ".request.spent.json")).exists()
        assert (root / "comparison-api.lock").exists()
        return native(*args)
    result = execute(tmp_path, a, root=root, transport=transport)
    assert result["status"] == "completed" and result["receipt_published"] and result["lock_cleanup_complete"]
    assert result["transport_calls_attempted"] == len(requests) == 6
    assert content["main.py"] == fixture_main() and content["mia.ipynb"] == files()["mia.ipynb"]
    assert not (root / "comparison-api.lock").exists()
    assert result["financial_acceptance"] is False and result["economics_accepted"] is False
    assert result["native_origin_authenticated"] is False and result["backtesting_ready"] is False


@pytest.mark.parametrize("fault", ["active_job", "unknown_job", "foreign_job", "wrong_owner", "nonowner_collaborator",
    "nonwrite", "source_before", "source_after_extra", "source_after_missing",
    "count_mismatch", "count_missing", "empty_nonzero_count", "duplicate_job"])
def test_native_preconditions_stop_without_policy_or_source_broadening(tmp_path, fault):
    a, effects = action(), []
    reads = [0]
    def mutate(value, request):
        endpoint = request["endpoint"]
        if endpoint == "projects/read" and fault == "wrong_owner": value["projects"][0]["ownerId"] = OWNER+1
        if endpoint == "projects/collaboration/read":
            if fault == "nonwrite": value["userPermissions"] = "read"
            if fault == "nonowner_collaborator": value["collaborators"] = [
                {"uid": OWNER+1, "owner": False, "permission": "write", "liveControl": False}]
        if endpoint == "backtests/list":
            if fault == "active_job": value["backtests"][0].update(completed=False, status="Running")
            if fault == "unknown_job": value["backtests"][0]["status"] = "Unknown"
            if fault == "foreign_job": value["backtests"][0]["projectId"] = 42
            if fault == "count_mismatch": value["count"] = 5
            if fault == "count_missing": del value["count"]
            if fault == "empty_nonzero_count": value["count"], value["backtests"] = 3, []
            if fault == "duplicate_job":
                value["backtests"].append(dict(value["backtests"][0]));value["count"] = 2
        if endpoint == "files/read":
            reads[0] += 1
            if fault == "source_before" and reads[0] == 1: value["files"][1]["content"] += "drift"
            if fault == "source_after_extra" and reads[0] == 2: value["files"].append({"name": "new.py", "content": "pass"})
            if fault == "source_after_missing" and reads[0] == 2: value["files"] = [r for r in value["files"] if r["name"] != "mia.ipynb"]
        return value
    result = execute(tmp_path, a, transport=backend(a, effects=effects, transform=mutate))
    assert result["status"] == "failed_or_uncertain" and result["receipt_published"]
    if fault not in ("source_after_extra", "source_after_missing"): assert "files/update" not in effects


def test_claim_replay_and_actual_lock_contention_never_dispatch(tmp_path):
    a, root = action(), tmp_path / "cache-actions"
    assert execute(tmp_path, a, root=root)["status"] == "completed"
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, root=root, transport=lambda *_: pytest.fail("spent action dispatched"))
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    lock = other / "comparison-api.lock"
    lock.write_bytes(b"other controller")
    lock.chmod(0o600)
    result = execute(tmp_path, a, root=other, transport=lambda *_: pytest.fail("contention dispatched"))
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert lock.read_bytes() == b"other controller" and result["receipt_published"]


@pytest.mark.parametrize("encoded", [False, True])
def test_credential_echo_refuses_before_private_raw_retention(tmp_path, encoded):
    a = action()
    value = body(m._requests(a)[0], files())
    value["freeText"] = TOKEN
    raw = wire(value)
    if encoded: raw = raw.replace(TOKEN.encode(), "".join("\\u%04x" % ord(c) for c in TOKEN).encode())
    result = execute(tmp_path, a, transport=lambda *_: (raw, 200, TOKEN, OWNER))
    assert result["status"] == "failed_or_uncertain" and result["requests"][0]["raw_response"] is None
    assert not list((tmp_path / "cache-actions").glob("*.response.raw"))


def test_authenticated_uid_mismatch_never_retains_or_accepts_the_response(tmp_path):
    a = action()
    raw = wire(body(m._requests(a)[0], files()))
    result = execute(tmp_path, a, transport=lambda *_: (raw, 200, TOKEN, OWNER+1))
    assert result["status"] == "failed_or_uncertain" and result["requests"][0]["raw_response"] is None


def test_postclaim_remaining_wall_budget_must_cover_whole_transport(tmp_path):
    a, effects = action(), []
    expires = datetime.fromisoformat(a["api_plan"]["expires_utc"])
    seconds = m._requests(a)[0]["seconds"]
    result = execute(tmp_path, a, transport=backend(a, effects=effects),
        clock=lambda: expires-timedelta(seconds=seconds-1))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["requests"][0]["request_claim"] is not None and result["receipt_published"]


def test_request_claim_fsync_can_exhaust_monotonic_budget_before_credentials(tmp_path, monkeypatch):
    a, effects, tick = action(), [], [0.0]
    publish = m.api._publish
    seconds = m._requests(a)[0]["seconds"]
    def spent_time(root, name, raw):
        descriptor = publish(root, name, raw)
        if name.endswith(".request.spent.json"): tick[0] = m.PHASE_SECONDS-(seconds-1)
        return descriptor
    monkeypatch.setattr(m.api, "_publish", spent_time)
    result = execute(tmp_path, a, transport=backend(a, effects=effects), monotonic=lambda: tick[0])
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["requests"][0]["request_claim"] is not None and result["receipt_published"]


def test_source_guard_change_after_request_claim_stops_before_native_effect(tmp_path):
    a, root = action(), tmp_path / "cache-actions"
    def guard(_):
        if list(root.glob("*.request.spent.json")): raise m.ActionRefusal("synthetic drift")
    result = execute(tmp_path, a, root=root, guard=guard, transport=lambda *_: pytest.fail("drift dispatched"))
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert result["receipt_published"] and result["lock_cleanup_complete"]


def test_cancellation_retains_spent_claim_receipt_and_cleans_owned_lock(tmp_path):
    def cancelled(*args): raise KeyboardInterrupt()
    with pytest.raises(m.ActionCancelled) as error:
        execute(tmp_path, transport=cancelled)
    assert error.value.report["status"] == "cancelled"
    assert error.value.report["receipt_published"] and error.value.report["lock_cleanup_complete"]


def compile_evidence(tmp_path, *, content=None, **changes):
    root = tmp_path / "cache-actions"
    compile_action = action("compile", **changes)
    content = files("compile") if content is None else content
    compiled = execute(tmp_path, compile_action, root=root, transport=backend(compile_action, content=content))
    assert compiled["status"] == "completed"
    build_action = action("build", **changes)
    built = execute(tmp_path, build_action, root=root, transport=backend(build_action, content=content))
    assert built["status"] == "completed"
    cop, bop = compile_action["api_plan"]["operation_id"], build_action["api_plan"]["operation_id"]
    names = {"compile_plan": cop+".action.spent.json", "compile_result": cop+".result.json",
        "source_before": cop+".before.response.raw", "compile_response": cop+".compile.response.raw",
        "source_after": cop+".after.response.raw", "build_plan": bop+".action.spent.json",
        "build_result": bop+".result.json", "build_response": bop+".build.response.raw"}
    raw = {key: (root/name).read_bytes() for key, name in names.items()}
    descriptors = {key: {"name": names[key], "bytes": len(value), "sha256": sha(value)} for key, value in raw.items()}
    return root, descriptors, raw


def test_launch_requires_exact_retained_compile_chain_then_creates_only_diagnostic_job(tmp_path):
    root, descriptors, _ = compile_evidence(tmp_path)
    launch = action("launch", compile_evidence=descriptors)
    result = execute(tmp_path, launch, root=root)
    assert result["status"] == "completed" and result["receipt_published"]
    assert result["financial_acceptance"] is False and result["economics_accepted"] is False
    assert result["native_origin_authenticated"] is False and result["backtesting_ready"] is False
    assert any(row["endpoint"] == "backtests/create" for row in result["requests"])


@pytest.mark.parametrize("fault", ["digest", "name", "compile_id", "build_state", "source_after", "foreign_job", "result_operation"])
def test_forged_or_mismatched_compile_evidence_never_reaches_launch_transport(tmp_path, fault):
    root, descriptors, raw = compile_evidence(tmp_path)
    kwargs = {}
    if fault == "digest": descriptors["source_before"]["sha256"] = "f" * 64
    elif fault == "name": descriptors["build_response"]["name"] = "other.response.raw"
    elif fault == "compile_id": kwargs["compile_id"] = "different-compile"
    elif fault == "foreign_job":
        kwargs["probe_operation_id"] = "TPR-CACHE-20261104-FOREIGN-001"
        content = files("launch")
        content["main.py"] = m.builder._build_fixture(helper_source=helper_source(), operation_id=kwargs["probe_operation_id"], git_head=HEAD)[0]
        kwargs["source_inventory"] = inventory(content)
    else:
        key = "build_response" if fault == "build_state" else "compile_result" if fault == "result_operation" else "source_after"
        value = json.loads(raw[key])
        if fault == "build_state": value["state"] = "BuildError"
        elif fault == "result_operation": value["operation_id"] = "TPR-CMP29-API-CACHE-FOREIGN-COMPILE"
        else: value["files"][1]["content"] += "drift"
        changed = wire(value)
        (root / descriptors[key]["name"]).write_bytes(changed)
        descriptors[key].update(bytes=len(changed), sha256=sha(changed))
    launch = action("launch", compile_evidence=descriptors, **kwargs)
    result = execute(tmp_path, launch, root=root, transport=lambda *_: pytest.fail("forged proof dispatched"))
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert result["receipt_published"]


def test_interrupt_after_first_durable_action_claim_retains_cancel_receipt_without_replay(tmp_path, monkeypatch):
    a, root = action(), tmp_path / "cache-actions"
    op = a["api_plan"]["operation_id"]
    publish = m.api._publish
    def interrupted_after_publication(directory, name, raw):
        descriptor = publish(directory, name, raw)
        if name == op + ".action.spent.json":
            raise KeyboardInterrupt()
        return descriptor
    monkeypatch.setattr(m.api, "_publish", interrupted_after_publication)
    caught = None
    try:
        execute(tmp_path, a, root=root, transport=lambda *_: pytest.fail("interrupted action reached native"))
    except BaseException as error:
        if not isinstance(error, KeyboardInterrupt):
            raise  # native-effect pytest failures and unrelated errors stay visible
        caught = error
    assert isinstance(caught, m.ActionCancelled)
    report = caught.report
    assert report["status"] == "cancelled" and report["receipt_published"] is True
    assert report["transport_calls_attempted"] == 0
    claim, receipt = root / (op + ".action.spent.json"), root / (op + ".result.json")
    assert claim.exists() and receipt.exists()
    assert json.loads(receipt.read_bytes())["status"] == "cancelled"
    before = claim.read_bytes(), receipt.read_bytes()
    monkeypatch.setattr(m.api, "_publish", publish)
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, root=root, transport=lambda *_: pytest.fail("spent cancelled action reached native"))
    assert (claim.read_bytes(), receipt.read_bytes()) == before


def test_replaced_proof_fifo_is_opened_nonblocking_then_refused_before_native_effect(tmp_path, monkeypatch):
    root, descriptors, _ = compile_evidence(tmp_path)
    descriptor = descriptors["source_before"]
    target = root / descriptor["name"]
    target.unlink()
    os.mkfifo(target, mode=0o600)
    original_open, observed = os.open, []
    def checked_open(path, flags, *args, **kwargs):
        if Path(os.fspath(path)).name == descriptor["name"]:
            observed.append(flags)
            # Assertion precedes real open, so the old blocking reader cannot
            # hang this regression even though the leaf is an actual FIFO.
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", checked_open)
    a = action("launch", compile_evidence=descriptors)
    result = execute(tmp_path, a, root=root, transport=lambda *_: pytest.fail("FIFO proof reached native"))
    assert observed and all(flags & os.O_NONBLOCK for flags in observed)
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert result["receipt_published"] is True and target.is_fifo()


@pytest.mark.parametrize("field,changed", [
    ("git_head", "e" * 40), ("project_id", 42), ("candidate_config_sha256", "e" * 64),
    ("phase", "upload"), ("operation_id", "TPR-CMP29-API-CACHE-FOREIGN-COMPILE"),
    ("actual_new_diagnostic_jobs", False), ("actual_new_diagnostic_jobs", 0.0),
    ("automatic_retry", True), ("observed_job_ids", ["e" * 32]),
    ("financial_attempts_created", 1), ("financial_outcome_looks", 1),
    ("compile_requests_attempted", 0), ("transport_calls_attempted", 0),
])
def test_compile_receipt_headers_strict_zero_counters_and_hidden_jobs_are_proof_bindings(tmp_path, field, changed):
    root, descriptors, raw = compile_evidence(tmp_path)
    value = json.loads(raw["compile_result"])
    value[field] = changed
    forged = wire(value)
    descriptor = descriptors["compile_result"]
    (root / descriptor["name"]).write_bytes(forged)
    descriptor.update(bytes=len(forged), sha256=sha(forged))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert effects == [] and result["receipt_published"] is True


def test_distinct_operation_cannot_relaunch_a_spent_diagnostic_attempt_look_and_candidate(tmp_path):
    root, descriptors, _ = compile_evidence(tmp_path)
    first = action("launch", compile_evidence=descriptors)
    assert execute(tmp_path, first, root=root)["status"] == "completed"
    second = action("launch", compile_evidence=descriptors,
        operation_id="TPR-CMP29-API-CACHE-SYNTHETIC-LAUNCH-SECOND")
    effects = []
    try:
        result = execute(tmp_path, second, root=root, transport=backend(second, effects=effects))
    except m.ActionRefusal:
        result = None
    assert effects == []
    if result is not None:
        assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
        assert result["receipt_published"] is True


def test_partial_launch_reservation_collision_preserves_first_spend_and_old_look(tmp_path):
    root, descriptors, _ = compile_evidence(tmp_path)
    launch = action("launch", compile_evidence=descriptors)
    names = m._reservation_names(launch)
    assert len(names) == len(set(names)) == 3
    preexisting = root / names[1]
    preexisting.write_bytes(b"previous diagnostic look reservation")
    preexisting.chmod(0o600)
    before, effects = preexisting.read_bytes(), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert effects == [] and result["status"] == "failed_or_uncertain"
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"] is True
    assert (root / names[0]).exists() and preexisting.read_bytes() == before
    assert not (root / names[2]).exists()
    assert len(result["launch_reservations"]) == 1
    assert result["launch_reservations"][0]["name"] == names[0]


def test_lock_close_failure_preserves_cancellation_and_retains_body_free_receipt(tmp_path, monkeypatch):
    a, root, lock_fd = action(), tmp_path / "cache-actions", [None]
    real_open, real_close, faulted = os.open, os.close, [False]
    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if Path(os.fspath(path)).name == "comparison-api.lock": lock_fd[0] = fd
        return fd
    def closed(fd):
        if fd == lock_fd[0] and not faulted[0]:
            faulted[0] = True
            raise OSError("PRIVATE-CLOSE-FAILURE")
        return real_close(fd)
    def cancelled(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(m.os, "open", opened)
    monkeypatch.setattr(m.os, "close", closed)
    with pytest.raises(m.ActionCancelled) as error:
        execute(tmp_path, a, root=root, transport=cancelled)
    report = error.value.report
    assert faulted[0] and report["status"] == "cancelled" and report["receipt_published"] is True
    assert b"PRIVATE-CLOSE-FAILURE" not in (root / report["receipt"]["name"]).read_bytes()
    with pytest.raises(OSError): os.fstat(lock_fd[0])


SYNTHETIC_MIA_PUBLIC_ID = "A-" + "d" * 32


def authorized_mia_rows():
    return [{"uid": OWNER, "owner": True, "permission": "write", "liveControl": True},
        {"uid": None, "owner": False, "name": "Mia", "permission": "write", "liveControl": True,
            "publicId": SYNTHETIC_MIA_PUBLIC_ID}]


def with_authorized_mia(value, request):
    if request["endpoint"] == "projects/read":
        value["projects"][0]["collaborators"] = authorized_mia_rows()
    elif request["endpoint"] == "projects/collaboration/read":
        value["collaborators"] = authorized_mia_rows()
    return value


def test_exact_owner_authorized_mia_component_is_distinct_from_an_unknown_human(tmp_path, monkeypatch):
    # A fake identifier only: no actual publicId, email, credential, or person is
    # stored in the fixture. The narrow production matcher remains hash-bound.
    monkeypatch.setattr(m, "MIA_PUBLIC_ID_SHA256", sha(SYNTHETIC_MIA_PUBLIC_ID.encode("ascii")), raising=False)
    a = action()
    result = execute(tmp_path, a, transport=backend(a, transform=with_authorized_mia))
    assert result["status"] == "completed" and result["receipt_published"] is True
    for row in result["requests"]:
        if row["id"] not in ("metadata", "collaborators"):
            continue
        projection = row["projection"]
        assert projection["collaborator_count"] == 2
        assert projection["nonowner_collaborator_count"] == projection["recognized_mia_count"] == 1
        assert projection["unknown_other_count"] == 0 and projection["owner_only"] is False
        assert projection["independent_agent_identity_attested"] is False
        assert projection["privacy_basis"] == m.MIA_PRIVACY_BASIS
    assert all(result[key] is False for key in m.builder.FLAGS)


MIA_COMPONENT_FAULTS = (
    "changed_id", "malformed_id", "changed_name", "name_case", "name_whitespace", "uid_missing", "uid_bool",
    "uid_false", "uid_zero", "uid_string", "uid_foreign", "owner_missing", "owner_true", "owner_nonbool", "owner_string",
    "role_read", "role_missing", "role_unknown", "live_false", "live_missing", "live_nonbool",
    "duplicate_mia", "duplicate_owner", "unknown_human", "extra_actor", "wrong_owner_row_uid",
    "public_project", "shared_project", "wrong_org", "wrong_owner", "wrong_project")


@pytest.mark.parametrize("fault", MIA_COMPONENT_FAULTS)
@pytest.mark.parametrize("location", ("metadata", "collaborators"))
def test_mia_component_compatibility_cannot_admit_any_other_actor_or_project(tmp_path, monkeypatch, fault, location):
    monkeypatch.setattr(m, "MIA_PUBLIC_ID_SHA256", sha(SYNTHETIC_MIA_PUBLIC_ID.encode("ascii")), raising=False)
    a, effects = action(), []
    def mutate(value, request):
        value = with_authorized_mia(value, request)
        if request["id"] != location:
            return value
        context = value["projects"][0] if location == "metadata" else value
        rows = context["collaborators"]
        owner, mia = rows
        if fault == "changed_id": mia["publicId"] = "A-" + "e" * 32
        elif fault == "malformed_id": mia["publicId"] = "A-" + "d" * 31
        elif fault == "changed_name": mia["name"] = "Other"
        elif fault == "name_case": mia["name"] = "MIA"
        elif fault == "name_whitespace": mia["name"] = "Mia "
        elif fault == "uid_missing": del mia["uid"]
        elif fault == "uid_bool": mia["uid"] = True
        elif fault == "uid_false": mia["uid"] = False
        elif fault == "uid_zero": mia["uid"] = 0
        elif fault == "uid_string": mia["uid"] = str(OWNER)
        elif fault == "uid_foreign": mia["uid"] = OWNER + 1
        elif fault == "owner_missing": del mia["owner"]
        elif fault == "owner_true": mia["owner"] = True
        elif fault == "owner_nonbool": mia["owner"] = 0
        elif fault == "owner_string": mia["owner"] = "false"
        elif fault == "role_read": mia["permission"] = "read"
        elif fault == "role_missing": del mia["permission"]
        elif fault == "role_unknown": mia["permission"] = "admin"
        elif fault == "live_false": mia["liveControl"] = False
        elif fault == "live_missing": del mia["liveControl"]
        elif fault == "live_nonbool": mia["liveControl"] = 1
        elif fault == "duplicate_mia": rows.append(deepcopy(mia))
        elif fault == "duplicate_owner": rows.append(deepcopy(owner))
        elif fault == "unknown_human": rows.append({"uid": OWNER + 1, "owner": False,
            "permission": "write", "liveControl": True, "name": "Other"})
        elif fault == "extra_actor": rows.append({"uid": None, "owner": False, "name": "Other",
            "permission": "write", "liveControl": True, "publicId": "A-" + "e" * 32})
        elif fault == "wrong_owner_row_uid": owner["uid"] = OWNER + 1
        elif fault == "public_project": context["isPublic"] = True
        elif fault == "shared_project": context["shared"] = True
        elif fault == "wrong_org": context["organizationId"] = "e" * 32
        elif fault == "wrong_owner": context["ownerId"] = OWNER + 1
        elif fault == "wrong_project": context["projectId"] = 42
        return value
    result = execute(tmp_path, a, transport=backend(a, effects=effects, transform=mutate))
    assert result["status"] == "failed_or_uncertain" and result["receipt_published"] is True
    assert result["transport_calls_attempted"] <= (1 if location == "metadata" else 2)
    assert not {"files/update", "compile/create", "backtests/create"} & set(effects)


def test_mia_hash_is_production_bound_without_public_identifier_or_allow_flag():
    import re
    raw = Path(m.__file__).read_bytes()
    assert m.MIA_PUBLIC_ID_SHA256 == "790fd84f9177e87e0c5bc385f8bef44e107330b3d2ff329d9b59f26298704ee1"
    assert re.search(rb"A-[a-f0-9]{32}", raw) is None
    assert not {"allow_mia", "allow_component", "mia_public_id", "noneconomic_override"} & set(inspect.signature(m.prepare_action).parameters)
    parameter = inspect.signature(m._projection).parameters["latest_owner_instruction_sha256"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("owner_hash", ("f" * 64, None, m.CREATION_OWNER_SHA256))
def test_component_recognition_requires_the_actual_latest_owner_authority(owner_hash, monkeypatch):
    monkeypatch.setattr(m, "MIA_PUBLIC_ID_SHA256", sha(SYNTHETIC_MIA_PUBLIC_ID.encode("ascii")), raising=False)
    a = action()
    request = m._requests(a)[0]
    value = with_authorized_mia(body(request, files()), request)
    with pytest.raises(m.ActionRefusal):
        m._projection(value, request, registry(), latest_owner_instruction_sha256=owner_hash)


def test_old_v2_action_cannot_be_promoted_to_the_new_collaborator_policy(tmp_path):
    a = action()
    assert a["schema"] != "tpr-fixed-parent-cache-action-v2"
    a["schema"] = "tpr-fixed-parent-cache-action-v2"
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, transport=lambda *_: pytest.fail("old component policy reached transport"))


@pytest.mark.parametrize("key,old_schema", (("compile_plan", "tpr-fixed-parent-cache-action-v2"),
    ("compile_result", "tpr-fixed-parent-cache-action-result-v2"),
    ("build_plan", "tpr-fixed-parent-cache-action-v2"), ("build_result", "tpr-fixed-parent-cache-action-result-v2")))
def test_old_v2_compile_custody_cannot_mix_with_the_new_component_policy(tmp_path, key, old_schema):
    root, descriptors, raw = compile_evidence(tmp_path)
    value = json.loads(raw[key])
    assert value["schema"] != old_schema
    value["schema"] = old_schema
    changed = wire(value)
    descriptor = descriptors[key]
    (root / descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and result["receipt_published"] is True
    assert effects == [] and result["transport_calls_attempted"] == 0


@pytest.mark.parametrize("value", [38609822, m.evidence.JsonNumber("38609822")])
def test_standard_native_integer_lexeme_and_plain_fixture_integer_are_both_accepted(value):
    assert m._native_integer(value) == 38609822


@pytest.mark.parametrize("value", [True, False, 38609822.0, "38609822",
    m.evidence.JsonNumber("38609822.0"), m.evidence.JsonNumber("38609822.5"),
    m.evidence.JsonNumber("3.8609822e7")])
def test_noninteger_type_or_noninteger_native_lexeme_is_never_normalized_into_an_id(value):
    with pytest.raises(m.ActionRefusal): m._native_integer(value)


@pytest.mark.parametrize("token", [b"38609822.0", b"38609822.5", b"3.8609822e7", b"true"])
@pytest.mark.parametrize("location", ["metadata_project", "top_project", "job_project", "file_project"])
def test_wire_project_id_lexemes_are_strict_before_any_mutation(tmp_path, token, location):
    a, effects = action(), []
    underlying = backend(a, effects=effects)
    def transport(endpoint, raw, seconds, maximum, expected_owner):
        returned, status, credential, owner = underlying(endpoint, raw, seconds, maximum, expected_owner)
        value = json.loads(returned)
        if location == "metadata_project" and endpoint == "projects/read":
            value["projects"][0]["projectId"] = "NUMERIC-PROJECT-PLACEHOLDER"
        elif location == "top_project" and endpoint == "projects/collaboration/read":
            value["projectId"] = "NUMERIC-PROJECT-PLACEHOLDER"
        elif location == "job_project" and endpoint == "backtests/list":
            value["backtests"][0]["projectId"] = "NUMERIC-PROJECT-PLACEHOLDER"
        elif location == "file_project" and endpoint == "files/read":
            value["files"][1]["projectId"] = "NUMERIC-PROJECT-PLACEHOLDER"
        returned = wire(value).replace(b'"NUMERIC-PROJECT-PLACEHOLDER"', token)
        return returned, status, credential, owner
    result = execute(tmp_path, a, transport=transport)
    assert result["status"] == "failed_or_uncertain" and result["receipt_published"]
    assert "files/update" not in effects


@pytest.mark.parametrize("token", [b"38609822.0", b"38609822.5", b"3.8609822e7", b"true"])
def test_returned_launch_job_project_id_requires_native_integer_lexeme(tmp_path, token):
    root, descriptors, _ = compile_evidence(tmp_path)
    a = action("launch", compile_evidence=descriptors)
    underlying = backend(a)
    def transport(endpoint, raw, seconds, maximum, expected_owner):
        returned, status, credential, owner = underlying(endpoint, raw, seconds, maximum, expected_owner)
        if endpoint == "backtests/create":
            value = json.loads(returned)
            value["backtest"]["projectId"] = "NUMERIC-PROJECT-PLACEHOLDER"
            returned = wire(value).replace(b'"NUMERIC-PROJECT-PLACEHOLDER"', token)
        return returned, status, credential, owner
    result = execute(tmp_path, a, root=root, transport=transport)
    assert result["status"] == "failed_or_uncertain" and result["receipt_published"]


def test_native_parent_interface_closes_all_sources_and_has_no_local_sid_or_body_input():
    a = action()
    signature = inspect.signature(m.prepare_action)
    assert {"parent_probe_config_json", "helper_source"} <= set(signature.parameters)
    assert not {"target_sid_text", "parent_body", "source", "endpoint", "noneconomic_override"} & set(signature.parameters)
    assert "target_sid_text" not in a and b"SYNTHETIC.CACHE 1" not in wire(a)
    assert a["helper_source_utf8"].encode("utf-8") == helper_source()
    assert sha(helper_source()) == m.builder.HELPER_SHA256 == a["api_plan"]["source_hashes"][m.builder.reader.MODULE]
    expected = m.api.REQUIRED_SOURCES | m.builder.REQUIRED_SOURCES | {m.MODULE, m.custody.MODULE}
    assert m.REQUIRED_SOURCES == expected == set(a["api_plan"]["source_hashes"])
    assert m.PINS[m.builder.MODULE] == "73d17c8ca462cbddd0c9c1aa5afe887e5d9ee56da0db6b5883e65fba854b58a4"
    assert all(sha((ROOT/name).read_bytes()) == digest for name, digest in m.PINS.items())
    assert 0 < len(fixture_main()) <= 60000  # the unchanged API payload bound


@pytest.mark.parametrize("field,value", [("parent_probe_config_json", "{}"),
    ("helper_source_utf8", "raise RuntimeError('arbitrary caller source')"),
    ("target_sid_text", "forbidden local SID argument")])
def test_changed_parent_helper_or_legacy_sid_action_is_refused_before_effect(tmp_path, field, value):
    a = action()
    a[field] = value
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, transport=lambda *_: pytest.fail("open parent input reached transport"))


@pytest.mark.parametrize("name", sorted(m.builder.REQUIRED_SOURCES))
def test_every_native_parent_source_pin_is_required(name):
    args = arguments()
    args["source_hashes"][name] = "f" * 64
    with pytest.raises(m.ActionRefusal): m._prepare_fixture(**args)


@pytest.mark.parametrize("value", [b"pass\n", bytearray(b"pass\n"), "pass\n"])
def test_only_exact_public_validator_bytes_can_enter_the_closed_builder(value):
    args = arguments(helper_source=value)
    with pytest.raises(m.ActionRefusal): m._prepare_fixture(**args)


def test_prior_v3_action_is_refused_by_the_observability_v4_epoch():
    prior = action()
    prior["schema"] = "tpr-fixed-parent-cache-action-v3"
    with pytest.raises(m.ActionRefusal): m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_prior_v3_compile_chain_cannot_mix_with_observability_v4(tmp_path, key):
    root, descriptors, raw = compile_evidence(tmp_path)
    prior = json.loads(raw[key])
    prior["schema"] = ("tpr-fixed-parent-cache-action-result-v3" if key.endswith("result")
        else "tpr-fixed-parent-cache-action-v3")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0


def test_prior_v4_action_is_refused_by_configuration_diagnostic_v5():
    prior = action()
    prior["schema"] = "tpr-fixed-parent-cache-action-v4"
    with pytest.raises(m.ActionRefusal): m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_prior_v4_compile_chain_cannot_mix_with_configuration_diagnostic_v5(tmp_path, key):
    root, descriptors, raw = compile_evidence(tmp_path)
    prior = json.loads(raw[key])
    prior["schema"] = ("tpr-fixed-parent-cache-action-result-v4" if key.endswith("result")
        else "tpr-fixed-parent-cache-action-v4")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0


def test_prior_v5_action_is_refused_by_internal_control_v6_epoch():
    prior = action()
    prior["schema"] = "tpr-fixed-parent-cache-action-v5"
    with pytest.raises(m.ActionRefusal):
        m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_prior_v5_compile_chain_cannot_mix_with_internal_control_v6(tmp_path, key):
    root, descriptors, raw = compile_evidence(tmp_path)
    prior = json.loads(raw[key])
    prior["schema"] = ("tpr-fixed-parent-cache-action-result-v5" if key.endswith("result")
        else "tpr-fixed-parent-cache-action-v5")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


def test_prior_parent_v4_builder_pin_cannot_enter_internal_control_epoch():
    sources = source_hashes()
    sources[m.builder.MODULE] = "e45e5eb3364f0986573476d4158f9e3370140462c7c9cbf73e1dbca0cbb41603"
    with pytest.raises(m.ActionRefusal):
        action(source_hashes=sources)


@pytest.mark.parametrize("fault", ("head", "source_closure", "configuration", "other_source"))
def test_valid_foreign_parent_compile_lineage_is_refused_before_launch(tmp_path, fault):
    changes, content = {}, files("compile")
    if fault == "head":
        changes["git_head"] = "b"*40
    elif fault == "source_closure":
        sources = source_hashes()
        sources[m.MODULE] = "f"*64
        changes["source_hashes"] = sources
    elif fault == "configuration":
        changes["probe_operation_id"] = "TPR-CACHE-20261104-SYNTHETIC-002"
    else:
        content["legacy.py"] = b"# distinct synthetic frozen source epoch\n"
    content["main.py"] = m.builder._build_fixture(helper_source=helper_source(),
        operation_id=changes.get("probe_operation_id", PROBE), git_head=changes.get("git_head", HEAD))[0]
    changes["source_inventory"] = inventory(content)
    root, descriptors, _ = compile_evidence(tmp_path, content=content, **changes)
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["receipt_published"] and result["transport_calls_attempted"] == 0


def test_post_launch_guard_failure_retains_the_returned_job_identity(tmp_path):
    """TPR-CR35-004: a source/clock failure right after a launch must not lose the running job."""
    root, descriptors, _ = compile_evidence(tmp_path)
    launch = action("launch", compile_evidence=descriptors)
    inner, launched = backend(launch), []
    def transport(endpoint, *rest):
        out = inner(endpoint, *rest)
        if endpoint == "backtests/create":
            launched.append(True)
        return out
    def guard(_plan):
        if launched:
            raise ValueError("source moved after the launch returned")
    result = execute(tmp_path, launch, root=root, transport=transport, guard=guard)
    row = next(item for item in result["requests"] if item["id"] == "launch")
    assert launched and row["raw_response"] is not None and len(result["observed_job_ids"]) == 1
    assert result["actual_new_diagnostic_jobs"] == 1 and result["status"] == "failed_or_uncertain"
    assert (root / (launch["api_plan"]["operation_id"]+".launch.response.raw")).exists()


def test_unpublished_receipt_is_never_reported_completed(tmp_path, monkeypatch):
    """TPR-CR35-005."""
    real = m.api._publish
    def publish(root, name, raw):
        if name.endswith(".result.json"):
            raise OSError("synthetic receipt failure")
        return real(root, name, raw)
    monkeypatch.setattr(m.api, "_publish", publish)
    result = execute(tmp_path)
    assert result["receipt_published"] is False and result["status"] == "failed_or_uncertain"


def test_build_error_wire_is_refused(tmp_path):
    """TPR-CR35-007: BuildSuccess is the only state gate before a compile becomes launchable."""
    a = action("build")
    def mutate(value, request):
        value["state"] = "BuildError"
        return value
    result = execute(tmp_path, a, transport=backend(a, content=files("build"), transform=mutate))
    assert result["status"] == "failed_or_uncertain"


def test_launch_refuses_compile_id_never_returned_by_pinned_compile(tmp_path):
    """TPR-CR35-007: only the compile of the pinned source can supply the launched compile ID."""
    root, content = tmp_path / "cache-actions", files("compile")
    compile_action = action("compile")
    def other(value, request):
        if request["endpoint"] == "compile/create":
            value["compileId"] = "unrelated-compile"
        return value
    assert execute(tmp_path, compile_action, root=root,
        transport=backend(compile_action, content=content, transform=other))["status"] == "completed"
    build_action = action("build")
    assert execute(tmp_path, build_action, root=root,
        transport=backend(build_action, content=content))["status"] == "completed"
    cop, bop = compile_action["api_plan"]["operation_id"], build_action["api_plan"]["operation_id"]
    names = {"compile_plan": cop+".action.spent.json", "compile_result": cop+".result.json",
        "source_before": cop+".before.response.raw", "compile_response": cop+".compile.response.raw",
        "source_after": cop+".after.response.raw", "build_plan": bop+".action.spent.json",
        "build_result": bop+".result.json", "build_response": bop+".build.response.raw"}
    evidence = {key: {"name": name, "bytes": len((root/name).read_bytes()), "sha256": sha((root/name).read_bytes())}
        for key, name in names.items()}
    launch, effects = action("launch", compile_evidence=evidence), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and "backtests/create" not in effects


def test_prior_parent_v6_action_is_refused_by_delivery_epoch():
    prior = action()
    assert prior["schema"] == "tpr-fixed-cache-delivery-chunked-action-v1"
    prior["schema"] = "tpr-fixed-parent-cache-action-v6"
    with pytest.raises(m.ActionRefusal):
        m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_prior_parent_v6_compile_proof_cannot_mix_with_delivery_epoch(tmp_path, key):
    root, descriptors, raws = compile_evidence(tmp_path)
    prior = json.loads(raws[key])
    prior["schema"] = ("tpr-fixed-parent-cache-action-result-v6" if key.endswith("result")
        else "tpr-fixed-parent-cache-action-v6")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


def test_delivery_launch_name_and_source_epoch_are_distinct():
    a = action("launch", compile_evidence={
        key: {"name": key+".synthetic", "bytes": 1, "sha256": "d"*64} for key in m.PROOF_KEYS})
    request = next(row for row in m._requests(a) if row["id"] == "launch")
    assert request["payload"]["backtestName"] == "TPR-DELIVERY-CHUNKED-20261107-OFF-D1"
    assert m.PRIVATE_ROOT.name == "native-cache-delivery-chunked-actions-20261107"
    assert m.builder.MODULE == "research/target_price_revisions_qc/native_cache_delivery_chunked_probe_20261107.py"
    assert m.builder.EPOCH != "TPR-NATIVE-PARENT-PREOPEN-CACHE-20261104-v5"


def test_production_guard_requires_exact_imported_predecessor_path(monkeypatch):
    monkeypatch.setattr(m.api, "_guard", lambda _plan: None)
    monkeypatch.setattr(m.builder.prior, "__file__", str(ROOT/"foreign_predecessor.py"))
    with pytest.raises(m.ActionRefusal):
        m._guard({})


def test_frozen_delivery_attempt_identifiers_fit_the_closed_adapter():
    a = action(operation_id="TPR-CMP29-API-CACHE-R120-CHUNKED-UPLOAD-001",
        probe_operation_id="TPR-CACHE-20261104-CHUNKED-OFF-001",
        attempt_id="TPR-CACHE-ATTEMPT-CHUNKED-OFF-001",
        diagnostic_look_id="TPR-CACHE-LOOK-CHUNKED-OFF-001")
    assert a["diagnostic_attempt"] == 1
    assert a["probe_operation_id"] == "TPR-CACHE-20261104-CHUNKED-OFF-001"
    assert a["api_plan"]["operation_id"] == "TPR-CMP29-API-CACHE-R120-CHUNKED-UPLOAD-001"
    assert a["attempt_id"] == "TPR-CACHE-ATTEMPT-CHUNKED-OFF-001"
    assert a["diagnostic_look_id"] == "TPR-CACHE-LOOK-CHUNKED-OFF-001"


def test_helper_phase_uses_one_literal_create_outside_the_readonly_generic_plan():
    a = action("helper")
    plan, requests = a["api_plan"], m._requests(a)
    assert len(a["before_inventory"]) == 12 and len(a["source_inventory"]) == 13
    assert [row["endpoint"] for row in plan["requests"]] == ["files/read", "files/read"]
    assert plan["allowed_source_hashes"] == {} and plan["attempt_id"] is None and plan["reserved_look_id"] is None
    assert m.HELPER_FILENAME not in m.api.WRITE_FILES
    assert [row["endpoint"] for row in requests] == ["projects/read", "projects/collaboration/read",
        "backtests/list", "files/read", "files/create", "files/read"]
    assert requests[4]["id"] == "helper_create"
    assert requests[4]["payload"] == {"projectId": 38609822, "name": m.HELPER_FILENAME,
        "content": m.builder.helper_module_source(helper_source()).decode("ascii")}
    assert all(a["source_inventory"][name] == row for name, row in a["before_inventory"].items())
    assert not {"helper_filename", "helper_module", "endpoint", "transport", "source"} & set(inspect.signature(m.prepare_action).parameters)
    assert m._validated(a) == a


@pytest.mark.parametrize("fault", ("present_exact", "present_unknown", "case_alias", "missing_old", "extra_old"))
def test_helper_phase_refuses_preexisting_helper_or_wrong_twelve_file_boundary(fault):
    content = files("helper")
    if fault.startswith("present_"):
        content[m.HELPER_FILENAME] = (m.builder.helper_module_source(helper_source()) if fault == "present_exact" else b"# unknown helper\n")
    elif fault == "case_alias":
        del content["historical_7.py"]
        content[m.HELPER_FILENAME.upper()] = b"# unknown case alias\n"
    elif fault == "missing_old":
        del content["historical_7.py"]
    else:
        content["extra.py"] = b"# unexpected extra\n"
    with pytest.raises(m.ActionRefusal):
        action("helper", source_inventory=inventory(content))


@pytest.mark.parametrize("phase", ("upload", "compile", "build", "launch"))
@pytest.mark.parametrize("fault", ("missing", "wrong_bytes", "wrong_digest", "case_alias", "extra", "missing_old"))
def test_every_later_phase_requires_exact_helper_and_thirteen_file_inventory(phase, fault):
    rows = inventory(files(phase))
    if fault == "missing": del rows[m.HELPER_FILENAME]
    elif fault == "wrong_bytes": rows[m.HELPER_FILENAME]["bytes"] += 1
    elif fault == "wrong_digest": rows[m.HELPER_FILENAME]["sha256"] = "d"*64
    elif fault == "case_alias": rows[m.HELPER_FILENAME.upper()] = rows.pop(m.HELPER_FILENAME)
    elif fault == "extra": rows["extra.py"] = {"bytes": 1, "sha256": "e"*64}
    else: del rows["historical_7.py"]
    proof = {key: {"name": key+".synthetic", "bytes": 1, "sha256": "d"*64} for key in m.PROOF_KEYS} if phase == "launch" else None
    with pytest.raises(m.ActionRefusal):
        action(phase, source_inventory=rows, compile_evidence=proof)


def test_helper_create_success_is_retained_before_separate_main_upload(tmp_path):
    content, effects = files("helper"), []
    original = dict(content)
    helper_action = action("helper")
    made = execute(tmp_path, helper_action, transport=backend(helper_action, content, effects))
    assert made["status"] == "completed" and made["transport_calls_attempted"] == 6
    assert made["actual_new_diagnostic_jobs"] == 0 and made["compile_requests_attempted"] == 0
    assert content["main.py"] == original["main.py"] and len(content) == 13
    assert all(content[name] == raw for name, raw in original.items())
    assert content[m.HELPER_FILENAME] == m.builder.helper_module_source(helper_source())
    upload = action("upload", source_inventory=inventory(content))
    updated = execute(tmp_path, upload, transport=backend(upload, content, effects))
    assert updated["status"] == "completed" and content["main.py"] == fixture_main()
    assert all(content[name] == raw for name, raw in original.items() if name != "main.py")
    assert effects.count("files/create") == effects.count("files/update") == 1
    assert "compile/create" not in effects and "backtests/create" not in effects


@pytest.mark.parametrize("fault", ("create_refusal", "create_errors", "after_drift", "after_missing", "after_extra", "after_interrupt"))
def test_helper_partial_effect_is_retained_without_main_update_or_automatic_replay(tmp_path, fault):
    a, content, effects = action("helper"), files("helper"), []
    original_main = content["main.py"]
    def mutate(value, request):
        if request["id"] == "helper_create":
            if fault == "create_refusal": value["success"] = False
            if fault == "create_errors": value["errors"] = ["synthetic refusal"]
        if request["id"] == "after":
            if fault == "after_drift": next(row for row in value["files"] if row["name"] == m.HELPER_FILENAME)["content"] += "drift"
            elif fault == "after_missing": value["files"] = [row for row in value["files"] if row["name"] != m.HELPER_FILENAME]
            elif fault == "after_extra": value["files"].append({"name": "extra.py", "content": "pass"})
            elif fault == "after_interrupt": raise KeyboardInterrupt()
        return value
    if fault == "after_interrupt":
        with pytest.raises(m.ActionCancelled) as error:
            execute(tmp_path, a, transport=backend(a, content, effects, mutate))
        result = error.value.report
    else:
        result = execute(tmp_path, a, transport=backend(a, content, effects, mutate))
    assert result["status"] in ("failed_or_uncertain", "cancelled") and result["receipt_published"]
    assert result["lock_cleanup_complete"] and result["automatic_retry"] is False
    assert content["main.py"] == original_main
    assert content[m.HELPER_FILENAME] == m.builder.helper_module_source(helper_source())
    assert effects.count("files/create") == 1
    assert not {"files/update", "compile/create", "backtests/create", "files/delete"} & set(effects)
    with pytest.raises(m.ActionRefusal):
        execute(tmp_path, a, transport=lambda *_: pytest.fail("spent helper replay reached native"))
    op, root = a["api_plan"]["operation_id"], tmp_path/"cache-actions"
    assert (root/(op+".action.spent.json")).exists()
    assert (root/(op+".helper_create.request.spent.json")).exists()
    assert (root/(op+".helper_create.response.raw")).exists()


@pytest.mark.parametrize("key", ("source_before", "source_after"))
def test_changed_plain_helper_cannot_be_smuggled_through_rehashed_compile_source_proof(tmp_path, key):
    root, descriptors, raws = compile_evidence(tmp_path)
    value = json.loads(raws[key])
    next(row for row in value["files"] if row["name"] == m.HELPER_FILENAME)["content"] += "# drift\n"
    changed = wire(value)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


def test_production_guard_requires_exact_imported_delivery_dependency_path(monkeypatch):
    monkeypatch.setattr(m.api, "_guard", lambda _plan: None)
    monkeypatch.setattr(m.builder.delivery, "__file__", str(ROOT/"foreign_delivery.py"))
    with pytest.raises(m.ActionRefusal):
        m._guard({})


@pytest.mark.parametrize("phase", ("helper", "upload", "compile", "build", "launch"))
def test_plain_phase_deadlines_are_fixed_at_two_hundred_forty_seconds(phase):
    proof = {key: {"name": key+".synthetic", "bytes": 1, "sha256": "d"*64} for key in m.PROOF_KEYS} if phase == "launch" else None
    a = action(phase, compile_evidence=proof)
    assert len(m._requests(a)) == (1 if phase == "build" else 6)
    assert all(row["seconds"] == 20 for row in m._requests(a))
    with pytest.raises(m.ActionRefusal):
        action(phase, compile_evidence=proof, expires_utc=(NOW+timedelta(seconds=240)).isoformat())


def test_packed_delivery_schema_cannot_be_promoted_to_plain_action():
    prior = action()
    prior["schema"] = "tpr-fixed-cache-delivery-action-v1"
    with pytest.raises(m.ActionRefusal):
        m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_packed_delivery_compile_proof_cannot_mix_with_plain_epoch(tmp_path, key):
    root, descriptors, raws = compile_evidence(tmp_path)
    prior = json.loads(raws[key])
    prior["schema"] = ("tpr-fixed-cache-delivery-action-result-v1" if key.endswith("result")
        else "tpr-fixed-cache-delivery-action-v1")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


def test_plain_delivery_schema_cannot_be_promoted_to_chunked_action():
    prior = action()
    prior["schema"] = "tpr-fixed-cache-delivery-plain-action-v1"
    with pytest.raises(m.ActionRefusal):
        m._validated(prior)


@pytest.mark.parametrize("key", ("compile_plan", "compile_result", "build_plan", "build_result"))
def test_plain_delivery_compile_proof_cannot_mix_with_chunked_epoch(tmp_path, key):
    root, descriptors, raws = compile_evidence(tmp_path)
    prior = json.loads(raws[key])
    prior["schema"] = ("tpr-fixed-cache-delivery-plain-action-result-v1" if key.endswith("result")
        else "tpr-fixed-cache-delivery-plain-action-v1")
    changed = wire(prior)
    descriptor = descriptors[key]
    (root/descriptor["name"]).write_bytes(changed)
    descriptor.update(bytes=len(changed), sha256=sha(changed))
    launch, effects = action("launch", compile_evidence=descriptors), []
    result = execute(tmp_path, launch, root=root, transport=backend(launch, effects=effects))
    assert result["status"] == "failed_or_uncertain" and effects == []
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


def test_production_guard_requires_exact_imported_plain_dependency_path(monkeypatch):
    monkeypatch.setattr(m.api, "_guard", lambda _plan: None)
    monkeypatch.setattr(m.builder.plain, "__file__", str(ROOT/"foreign_plain.py"))
    with pytest.raises(m.ActionRefusal):
        m._guard({})


def test_plain_builder_pin_cannot_enter_chunked_epoch():
    sources = source_hashes()
    sources[m.builder.MODULE] = "818304661420287e6b9b3fc900d597a233f83254978e1fd3755cf426e4fdee46"
    with pytest.raises(m.ActionRefusal):
        action(source_hashes=sources)


def test_existing_exact_plain_helper_allows_only_main_upload_for_new_chunked_candidate():
    a = action("upload")
    assert len(a["before_inventory"]) == len(a["source_inventory"]) == 13
    assert a["before_inventory"][m.HELPER_FILENAME] == a["source_inventory"][m.HELPER_FILENAME]
    assert m.builder.HELPER_MODULE_BYTES == 17368
    assert m.builder.HELPER_MODULE_SHA256 == "8ab9c6dd9bbeb57c4e29dc88f4b0131046cba15a90899ddc44382ed73e13a98a"
    assert [row["endpoint"] for row in m._requests(a)].count("files/update") == 1
    assert all(row["endpoint"] != "files/create" for row in m._requests(a))
    with pytest.raises(m.ActionRefusal):
        action("helper", source_inventory=inventory(files("upload")))
