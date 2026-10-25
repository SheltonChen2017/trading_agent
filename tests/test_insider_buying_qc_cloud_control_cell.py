"""Invented-only QC cell execution; no real SDK, account or retained inputs."""
from __future__ import annotations

import contextlib
import ast
import copy
import io
import json
import os
import sys
import types

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody")
pytest.importorskip("termios", reason="macOS/POSIX custody")
from research import insider_buying_qc_cloud_control_cell as m


NONCE = "a" * 64
PRIVATE_DETAIL = "invented-unretained-cloud-control-detail"


class Store:
    def __init__(self, *, exists=False, saved=True, fail=None):
        self.exists, self.saved, self.fail = exists, saved, fail
        self.calls = []

    def contains_key(self, key):
        self.calls.append(("contains_key", key))
        print(PRIVATE_DETAIL)
        print(PRIVATE_DETAIL, file=sys.stderr)
        if self.fail == "precheck":
            raise RuntimeError(PRIVATE_DETAIL)
        return self.exists

    def save(self, key, text):
        self.calls.append(("save", key, text))
        print(PRIVATE_DETAIL)
        print(PRIVATE_DETAIL, file=sys.stderr)
        if self.fail == "save":
            raise RuntimeError(PRIVATE_DETAIL)
        return self.saved

    def __getattr__(self, name):
        self.calls.append(("forbidden", name))
        raise AssertionError(PRIVATE_DETAIL)


def execute_cell(monkeypatch, store=None, *, project_id=m.PROJECT_ID, factory_failure=False,
                 namespace=None, cell_raw=None):
    store = Store() if store is None else store
    constructed = []
    package, research = types.ModuleType("QuantConnect"), types.ModuleType("QuantConnect.Research")
    package.__path__ = []
    def factory():
        constructed.append(1)
        print(PRIVATE_DETAIL)
        print(PRIVATE_DETAIL, file=sys.stderr)
        if factory_failure:
            raise RuntimeError(PRIVATE_DETAIL)
        return types.SimpleNamespace(project_id=project_id, object_store=store)
    research.QuantBook = factory
    package.Research = research
    monkeypatch.setitem(sys.modules, "QuantConnect", package)
    monkeypatch.setitem(sys.modules, "QuantConnect.Research", research)
    registration_raw, generated = m.build_invented_cell(NONCE)
    stdout, stderr = io.StringIO(), io.StringIO()
    namespace = {} if namespace is None else namespace
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exec(generated if cell_raw is None else cell_raw, namespace)
    raw = stdout.getvalue().encode()
    assert stderr.getvalue() == "" and PRIVATE_DETAIL.encode() not in raw
    assert len(raw.splitlines()) == 1
    ack = m.validate_acknowledgement(raw, registration_raw=registration_raw)
    return ack, raw, namespace, constructed, store


def run_core(registration, *, factory=None, namespace=None, expected_sha=None):
    """Execute the TRUE generated core against an invented in-memory SDK."""
    raw = m._raw(registration)
    output, errors = io.StringIO(), io.StringIO()
    namespace = {} if namespace is None else namespace
    if factory is None:
        factory = lambda: types.SimpleNamespace(project_id=m.PROJECT_ID,
            object_store=types.SimpleNamespace(contains_key=lambda key: False, save=lambda key, text: True))
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        exec(m.CORE_SOURCE, namespace)
        namespace["_ib_control_run"](factory, raw.decode(), m._sha(raw) if expected_sha is None else expected_sha)
    assert errors.getvalue() == ""
    return json.loads(output.getvalue()), output.getvalue().encode(), namespace


@pytest.mark.parametrize("field,bad", (
    ("exact_own_key_prechecks", True),
    ("maximum_saves", True),
    ("reads_downloads_lists_deletes", False),
    ("dataset_or_history_calls", False),
    ("jobs_backtests", False),
    ("atomic_create_or_immutability_guaranteed", 0),
))
def test_coherently_rehashed_scope_bool_count_laundering_refuses_before_sdk(field, bad):
    registration_raw, _ = m.build_invented_cell(NONCE)
    registration = json.loads(registration_raw)
    registration["scope"][field] = bad
    def forbidden():
        pytest.fail("invalid coherent registration must not construct QuantBook")
    ack, _, _ = run_core(registration, factory=forbidden)
    assert ack == {"schema": m.SCHEMA + "/acknowledgement", "disposition": "registration_refused"}


def test_true_generated_wrapper_uses_exact_single_precheck_and_two_argument_save(monkeypatch):
    ack, raw, _, constructed, store = execute_cell(monkeypatch)
    registration_raw, cell = m.build_invented_cell(NONCE)
    registration = json.loads(registration_raw)
    assert constructed == [1]
    assert store.calls == [("contains_key", registration["key"]),
        ("save", registration["key"], registration["payload_text"])]
    assert ack["disposition"] == "save_acknowledged_true"
    assert ack["own_key_precheck_invocations"] == ack["save_invocations"] == 1
    assert ack["save_returned_true"] is True and ack["fixture_only"] is True
    for key in ("object_store_contents_exported", "independent_stored_bytes_verified",
                "atomic_create_or_immutability_guaranteed", "backtesting_ready"):
        assert ack[key] is False
    assert type(ack["dataset_or_history_calls"]) is int and ack["dataset_or_history_calls"] == 0
    assert type(ack["jobs_backtests"]) is int and ack["jobs_backtests"] == 0
    assert ack["core_sha256"] == m._sha(m.CORE_SOURCE.encode()) == m.CORE_SHA256
    assert ack["registration_sha256"] == m._sha(registration_raw)
    assert registration["payload_text"].encode() not in raw
    assert b"from QuantConnect.Research import QuantBook" in cell


def test_true_generated_cell_second_execution_same_globals_never_calls_sdk_again(monkeypatch):
    first, _, namespace, first_constructed, store = execute_cell(monkeypatch)
    prior_calls = list(store.calls)
    second, _, _, constructed, _ = execute_cell(monkeypatch, store, namespace=namespace)
    assert first["disposition"] == "save_acknowledged_true" and first_constructed == [1]
    assert second["disposition"] == "kernel_claim_already_consumed"
    assert second["own_key_precheck_invocations"] == second["save_invocations"] == 0
    assert second["save_returned_true"] is None and constructed == [] and store.calls == prior_calls


@pytest.mark.parametrize("saved,disposition,reported", (
    (False, "save_acknowledged_false_no_retry", False),
    (0, "save_nonboolean_no_retry", None),
    (1, "save_nonboolean_no_retry", None),
    (None, "save_nonboolean_no_retry", None),
    ("true", "save_nonboolean_no_retry", None),
))
def test_save_false_and_nonboolean_never_retry_or_claim_success(monkeypatch, saved, disposition, reported):
    ack, _, namespace, _, store = execute_cell(monkeypatch, Store(saved=saved))
    assert ack["disposition"] == disposition and ack["save_returned_true"] is reported
    assert ack["own_key_precheck_invocations"] == ack["save_invocations"] == 1
    second, _, _, constructed, _ = execute_cell(monkeypatch, store, namespace=namespace)
    assert second["disposition"] == "kernel_claim_already_consumed" and constructed == []
    assert [c[0] for c in store.calls] == ["contains_key", "save"]


@pytest.mark.parametrize("exists,disposition", (
    (True, "own_key_already_exists_no_save"), (1, "own_key_precheck_nonboolean"),
    (0, "own_key_precheck_nonboolean"), (None, "own_key_precheck_nonboolean"),
    ("false", "own_key_precheck_nonboolean"),
))
def test_existing_and_nonboolean_precheck_never_save(monkeypatch, exists, disposition):
    ack, _, _, _, store = execute_cell(monkeypatch, Store(exists=exists))
    assert ack["disposition"] == disposition and ack["save_returned_true"] is None
    assert ack["own_key_precheck_invocations"] == 1 and ack["save_invocations"] == 0
    assert [c[0] for c in store.calls] == ["contains_key"]


@pytest.mark.parametrize("project_id", (True, False, 37465795.0, "37465795", 37465796, None))
def test_wrong_or_untyped_project_id_refuses_before_object_store(monkeypatch, project_id):
    ack, _, _, constructed, store = execute_cell(monkeypatch, project_id=project_id)
    assert ack["disposition"] == "project_mismatch" and constructed == [1] and store.calls == []
    assert ack["own_key_precheck_invocations"] == ack["save_invocations"] == 0


@pytest.mark.parametrize("failure,prechecks,saves", (("factory", 0, 0), ("precheck", 1, 0), ("save", 1, 1)))
def test_sdk_exceptions_are_sanitized_and_permanently_consume_kernel_claim(monkeypatch, failure, prechecks, saves):
    ack, raw, namespace, _, store = execute_cell(monkeypatch, Store(fail=failure), factory_failure=failure == "factory")
    assert ack["disposition"] == "cloud_control_exception_no_retry"
    assert (ack["own_key_precheck_invocations"], ack["save_invocations"]) == (prechecks, saves)
    assert ack["save_returned_true"] is None and PRIVATE_DETAIL.encode() not in raw
    before = list(store.calls)
    second, _, _, constructed, _ = execute_cell(monkeypatch, store, namespace=namespace)
    assert second["disposition"] == "kernel_claim_already_consumed" and constructed == [] and store.calls == before


@pytest.mark.parametrize("field,bad", (
    ("schema", "unapproved"), ("audit_id", "other"), ("project_id", True),
    ("project_id", 37465795.0), ("notebook", "research.ipynb"), ("cell_index", False),
    ("cell_index", 1), ("fixture_only", 1), ("nonce", "A" * 64),
    ("nonce", "a" * 63), ("nonce", "a" * 65), ("nonce", "../" + "a" * 61),
    ("core_sha256", "z" * 64), ("core_sha256", "a" * 63),
    ("key", "37465795/foreign/control.json"), ("payload_text", "private"),
    ("scope", {}), ("scope", []), ("scope", None), ("unknown", False),
))
def test_coherent_malformed_registration_refuses_before_quantbook(field, bad):
    registration_raw, _ = m.build_invented_cell(NONCE)
    registration = json.loads(registration_raw)
    registration[field] = bad
    calls = []
    def forbidden():
        calls.append(1)
        raise AssertionError("SDK must remain unused")
    ack, _, namespace = run_core(registration, factory=forbidden)
    assert ack == {"schema": m.SCHEMA + "/acknowledgement", "disposition": "registration_refused"}
    assert calls == [] and not any(key.startswith("_ib_qc_cloud_control_claim_") for key in namespace)


@pytest.mark.parametrize("expected_sha", ("0" * 64, "", "a" * 63, None, True))
def test_registration_digest_mismatch_refuses_without_sdk(expected_sha):
    registration_raw, _ = m.build_invented_cell(NONCE)
    output = io.StringIO()
    namespace = {}
    exec(m.CORE_SOURCE, namespace)
    calls = []
    with contextlib.redirect_stdout(output):
        namespace["_ib_control_run"](lambda: calls.append(1), registration_raw.decode(), expected_sha)
    assert json.loads(output.getvalue())["disposition"] == "registration_refused" and calls == []


@pytest.mark.parametrize("nonce", (None, True, 1, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "../" + "a" * 61))
def test_builder_refuses_untyped_malformed_or_traversal_nonce(nonce):
    with pytest.raises(m.CloudControlError):
        m.build_invented_cell(nonce)


@pytest.mark.parametrize("field,bad", (
    ("own_key_precheck_invocations", True), ("save_invocations", True),
    ("save_returned_true", 1), ("project_id", 37465795.0), ("cell_index", False),
    ("dataset_or_history_calls", False), ("jobs_backtests", False),
    ("object_store_contents_exported", 0), ("independent_stored_bytes_verified", 0),
    ("atomic_create_or_immutability_guaranteed", 0), ("backtesting_ready", 0),
    ("fixture_only", 1), ("key", "foreign"), ("registration_sha256", "0" * 64),
    ("core_sha256", "0" * 64), ("disposition", "Completed"), ("unknown", False),
))
def test_acknowledgement_strictly_rejects_coherent_bool_count_laundering_and_changed_metadata(monkeypatch, field, bad):
    ack, _, _, _, _ = execute_cell(monkeypatch)
    registration_raw, _ = m.build_invented_cell(NONCE)
    ack[field] = bad
    with pytest.raises(m.CloudControlError):
        m.validate_acknowledgement(m._raw(ack), registration_raw=registration_raw)


@pytest.mark.parametrize("raw", (b"", b" " * 8193, b"{}", b"[]", b"null", b"not json", b'{"a":1,"a":1}', b'{"x":NaN}'))
def test_acknowledgement_unknown_malformed_and_duplicate_shapes_refuse(raw):
    registration_raw, _ = m.build_invented_cell(NONCE)
    with pytest.raises(m.CloudControlError):
        m.validate_acknowledgement(raw, registration_raw=registration_raw)


def test_acknowledgement_uses_canonical_bytes_and_allows_only_one_terminal_lf(monkeypatch):
    ack, raw, _, _, _ = execute_cell(monkeypatch)
    registration_raw, _ = m.build_invented_cell(NONCE)
    assert m.validate_acknowledgement(raw.removesuffix(b"\n"), registration_raw=registration_raw) == ack
    for altered in (raw + b"\n", b" " + raw, json.dumps(ack, indent=1).encode()):
        with pytest.raises(m.CloudControlError):
            m.validate_acknowledgement(altered, registration_raw=registration_raw)


def folder(root):
    return root.joinpath(*m.ARTIFACT_PARTS)


def test_local_preparation_private_exclusive_106_source_intent_is_not_execution(tmp_path):
    events, observed = [], []
    def preflight(identity):
        assert not folder(tmp_path).exists()
        assert len(identity["source_sha256"]) == 106
        events.append("preflight")
        observed.append(copy.deepcopy(identity))
        return m._proof(identity, True)
    def guard():
        events.append("guard")
    result = m.prepare_invented_cell(tmp_path, nonce=NONCE, guard=guard, preflight=preflight)
    assert events[0] == "guard" and events[1] == "preflight"
    assert result["fixture_only"] is True and result["cloud_execution_observed"] is False
    assert result["local_scope_permanently_consumed"] is True and result["qc_or_credential_accesses"] == 0
    assert result["backtesting_ready"] is False
    assert set(path.name for path in folder(tmp_path).iterdir()) == {"scope.lock", "registration.json", "cell.py", "intent.json", "ready.json"}
    raw = {path.name: path.read_bytes() for path in folder(tmp_path).iterdir()}
    for path in folder(tmp_path).iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    assert folder(tmp_path).stat().st_mode & 0o777 == 0o700
    registration_raw, cell = m.build_invented_cell(NONCE)
    intent, ready = json.loads(raw["intent.json"]), json.loads(raw["ready.json"])
    assert raw["registration.json"] == registration_raw and raw["cell.py"] == cell
    assert result["cell_source"] == cell.decode()
    assert intent["execution_identity"] == observed[0]
    assert intent["registration_sha256"] == m._sha(registration_raw)
    assert intent["core_sha256"] == m.CORE_SHA256 and intent["cell_sha256"] == m._sha(cell)
    assert intent["cell_bytes"] == len(cell)
    assert intent["source_preflight"] == m._proof(observed[0], True)
    assert intent["maximum_selected_cell_executions"] == 1 and intent["no_retry_even_after_kernel_reset"] is True
    assert intent["cloud_execution_observed"] is False and intent["cloud_or_credential_accesses_by_preparer"] == 0
    assert ready["intent_sha256"] == m._sha(raw["intent.json"]) and result["ready_sha256"] == m._sha(raw["ready.json"])
    with pytest.raises((ValueError, OSError)):
        m.prepare_invented_cell(tmp_path, nonce="b" * 64)
    assert raw == {path.name: path.read_bytes() for path in folder(tmp_path).iterdir()}


@pytest.mark.parametrize("bad_proof", ("exception", "source_count_bool", "false_native_claim", "unknown"))
def test_preflight_refusal_is_before_nonce_or_output_creation(tmp_path, monkeypatch, bad_proof):
    def preflight(identity):
        if bad_proof == "exception":
            raise m.CloudControlError("invented_preflight_refusal")
        proof = m._proof(identity, True)
        if bad_proof == "source_count_bool":
            proof["source_count"] = True
        elif bad_proof == "false_native_claim":
            proof["initial_native_network_fork_allwrite_securityexec_denial"] = True
        else:
            proof["unknown"] = False
        return proof
    original = m._cell
    def cell(nonce, fixture):
        assert nonce == "0" * 64, "a real selected nonce cannot be consumed before proof"
        return original(nonce, fixture)
    monkeypatch.setattr(m, "_cell", cell)
    with pytest.raises(m.CloudControlError):
        m.prepare_invented_cell(tmp_path, preflight=preflight)
    assert not folder(tmp_path).exists()


def test_source_guard_refusal_before_proof_never_claims_output(tmp_path):
    calls = []
    def guard():
        raise m.CloudControlError("invented_source_changed")
    def preflight(identity):
        calls.append(1)
        return m._proof(identity, True)
    with pytest.raises(m.CloudControlError):
        m.prepare_invented_cell(tmp_path, guard=guard, preflight=preflight)
    assert calls == [] and not folder(tmp_path).exists()


def test_invalid_selected_nonce_permanently_consumes_new_scope_after_lock(tmp_path):
    with pytest.raises(m.CloudControlError):
        m.prepare_invented_cell(tmp_path, nonce="invalid")
    assert set(p.name for p in folder(tmp_path).iterdir()) == {"scope.lock"}
    assert (folder(tmp_path) / "scope.lock").read_bytes() == m.LOCK_BYTES
    with pytest.raises((ValueError, OSError)):
        m.prepare_invented_cell(tmp_path)


def test_publication_failure_preserves_claim_and_closes_handles(tmp_path, monkeypatch):
    publish, close = m.publication._NewDirectory.publish, m.publication._close_all
    closed = []
    def broken(self, name, raw, **kwargs):
        if name == "intent.json":
            raise m.CloudControlError("invented_publication_failure")
        return publish(self, name, raw, **kwargs)
    def observed_close(folders, *args):
        closed.extend(item for item in folders if item is not None)
        return close(folders, *args)
    monkeypatch.setattr(m.publication._NewDirectory, "publish", broken)
    monkeypatch.setattr(m.publication, "_close_all", observed_close)
    with pytest.raises(m.CloudControlError):
        m.prepare_invented_cell(tmp_path)
    assert len(closed) == 2 and set(p.name for p in folder(tmp_path).iterdir()) == {"scope.lock", "registration.json", "cell.py"}
    for item in closed:
        descriptor = getattr(item, "fd", None)
        if descriptor is not None:
            with pytest.raises(OSError):
                os.fstat(descriptor)
    with pytest.raises((ValueError, OSError)):
        m.prepare_invented_cell(tmp_path)


def test_guard_change_after_lock_refuses_without_retry_or_unclaim(tmp_path):
    def guard():
        if (folder(tmp_path) / "scope.lock").exists():
            raise m.CloudControlError("invented_mid_preparation_source_change")
    with pytest.raises(m.CloudControlError):
        m.prepare_invented_cell(tmp_path, guard=guard)
    assert set(p.name for p in folder(tmp_path).iterdir()) == {"scope.lock"}
    with pytest.raises((ValueError, OSError)):
        m.prepare_invented_cell(tmp_path)


@pytest.mark.parametrize("path", ("/research/x.py", "research/../x.py", "research//x.py", "research/x.txt", "tests/x.py/../z.py"))
def test_source_identity_refuses_wrong_scope_traversal_and_non_python_names(tmp_path, path):
    identity = {"root": str(tmp_path), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": {m.SELF_PATH: "a" * 64, m.TEST_PATH: "b" * 64, path: "c" * 64}}
    identity["source_inventory_sha256"] = m._sha(m._raw(identity["source_sha256"]))
    with pytest.raises(m.CloudControlError):
        m._source_identity(identity, tmp_path)


def test_capacity_failure_is_before_preflight_nonce_or_output(tmp_path):
    sources = {m.SELF_PATH: "a" * 64, m.TEST_PATH: "b" * 64,
        **{f"research/{'long_control_' * 18}{i:04}.py": "c" * 64 for i in range(1900)}}
    identity = {"root": str(tmp_path), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}
    calls = []
    with pytest.raises(m.CloudControlError):
        m._prepare(tmp_path, identity, fixture=True, guard=lambda: None,
            preflight=lambda value: calls.append("preflight"), nonce_factory=lambda n: calls.append("nonce"))
    assert calls == [] and not folder(tmp_path).exists()


def source_identity():
    inventory = {m.SELF_PATH: m._sha(b"own-source"), m.TEST_PATH: m._sha(b"own-tests")}
    return {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "a" * 40,
        "clean": True, "source_sha256": inventory, "source_inventory_sha256": m._sha(m._raw(inventory))}


def test_actual_front_requires_initial_isolation_before_source_or_output(monkeypatch):
    monkeypatch.setattr(m, "_identity", lambda _: pytest.fail("no source or output before isolation"))
    monkeypatch.setattr(m.sys, "pycache_prefix", "wrong-cache-prefix")
    with pytest.raises(m.CloudControlError, match="cloud_control_initial_isolation_required"):
        m.prepare_actual_cell("a" * 40)


def test_worker_native_proof_precedes_source_capacity_and_final_source_checks(monkeypatch):
    events = []
    identity = source_identity()
    monkeypatch.setattr(m, "_isolated", lambda: events.append("initial-flags"))
    monkeypatch.setattr(m.sources, "_prove_isolation", lambda: events.append("native-proof"))
    monkeypatch.setattr(m, "_current", lambda _: events.append("source"))
    monkeypatch.setattr(m, "_capacity", lambda _, mode: events.append(("capacity", mode)))
    assert m._worker(identity) == m._proof(identity, False)
    assert events == ["initial-flags", "native-proof", "source", ("capacity", False), "source"]


def test_worker_missing_initial_native_proof_never_checks_sources_or_capacity(monkeypatch):
    monkeypatch.setattr(m, "_isolated", lambda: None)
    def refusal():
        raise m.CloudControlError("invented_native_proof_refused")
    monkeypatch.setattr(m.sources, "_prove_isolation", refusal)
    monkeypatch.setattr(m, "_current", lambda _: pytest.fail("source path before native proof"))
    with pytest.raises(m.CloudControlError, match="invented_native_proof_refused"):
        m._worker(source_identity())


def test_missing_loaded_closure_refuses_before_source_read(monkeypatch):
    identity = source_identity()
    monkeypatch.setattr(m.sources.custody, "_internal_source_paths", lambda _: (m.SELF_PATH, "research/missing.py"))
    monkeypatch.setattr(m.sources.custody, "_source_bytes", lambda *args: pytest.fail("incomplete closure must refuse first"))
    with pytest.raises(m.CloudControlError, match="cloud_control_loaded_closure_missing"):
        m._current(identity)


@pytest.mark.parametrize("changed", ("source", "frozen"))
def test_current_and_frozen_bytes_are_both_binding(monkeypatch, changed):
    identity = source_identity()
    monkeypatch.setattr(m.sources.custody, "_internal_source_paths", lambda _: tuple(identity["source_sha256"]))
    def source_bytes(root, names):
        if tuple(names) == tuple(identity["source_sha256"]):
            return {**identity["source_sha256"], m.SELF_PATH: "0" * 64} if changed == "source" else identity["source_sha256"]
        assert tuple(names) == tuple(m.sources.FROZEN)
        return {**m.sources.FROZEN, next(iter(m.sources.FROZEN)): "0" * 64} if changed == "frozen" else m.sources.FROZEN
    monkeypatch.setattr(m.sources.custody, "_source_bytes", source_bytes)
    with pytest.raises(m.CloudControlError, match="cloud_control_current_or_frozen_source_changed"):
        m._current(identity)


@pytest.mark.parametrize("changed", (None, m.SELF_PATH, m.TEST_PATH))
def test_committed_identity_explicitly_checks_both_owned_git_images(monkeypatch, changed):
    identity, seen = source_identity(), []
    monkeypatch.setattr(m.sources.custody, "_identity", lambda head: copy.deepcopy(identity))
    monkeypatch.setattr(m.sources.custody, "_source_bytes", lambda root, names: identity["source_sha256"])
    def git(root, operation, target):
        name = target.split(":", 1)[1]; seen.append(name)
        return b"mismatched-committed-image" if name == changed else (b"own-source" if name == m.SELF_PATH else b"own-tests")
    monkeypatch.setattr(m.sources.custody, "_git", git)
    monkeypatch.setattr(m, "_current", lambda _: None)
    if changed is None:
        assert m._identity("a" * 40) == identity
        assert seen == [m.SELF_PATH, m.TEST_PATH]
    else:
        with pytest.raises(m.CloudControlError, match="uncommitted_cloud_control_source"):
            m._identity("a" * 40)
        assert changed in seen


def test_real_shaped_genuine_internal_roster_is_accepted_by_actual_identity_front(monkeypatch):
    # The genuine custody producer includes these internal roots; do not bypass
    # either our validator or _current while testing its real-shaped output.
    identity = source_identity()
    identity["source_sha256"].update({"data/__init__.py": m._sha(b"data-init"),
        "data/hashing.py": m._sha(b"data-hashing"), "ml/immutable_io.py": m._sha(b"immutable-io"),
        "backtest/__init__.py": m._sha(b"backtest-init")})
    identity["source_inventory_sha256"] = m._sha(m._raw(identity["source_sha256"]))
    monkeypatch.setattr(m.sources.custody, "_identity", lambda head: copy.deepcopy(identity))
    monkeypatch.setattr(m.sources.custody, "_internal_source_paths", lambda root: tuple(identity["source_sha256"]))
    def source_bytes(root, names):
        if tuple(names) == tuple(m.sources.FROZEN):
            return m.sources.FROZEN
        return {name: identity["source_sha256"][name] for name in names}
    monkeypatch.setattr(m.sources.custody, "_source_bytes", source_bytes)
    monkeypatch.setattr(m.sources.custody, "_git", lambda root, operation, target:
        b"own-source" if target.endswith(":" + m.SELF_PATH) else b"own-tests")
    assert m._identity("a" * 40) == identity
    m._capacity(identity, False)


@pytest.mark.parametrize("bad", (None, "returncode", "stderr", "bool-count", "extra-lf"))
def test_native_source_preflight_exact_policy_command_and_typed_receipt(monkeypatch, bad):
    identity, observed = source_identity(), []
    proof = m._proof(identity, False)
    if bad == "bool-count":
        proof["source_count"] = True
    stdout = m._raw(proof) + (b"\n\n" if bad == "extra-lf" else b"\n")
    def launcher(command, **kwargs):
        observed.append((command, kwargs))
        return types.SimpleNamespace(returncode=2 if bad == "returncode" else 0,
            stderr=b"not accepted" if bad == "stderr" else b"", stdout=stdout)
    monkeypatch.setattr(m.sources.launcher, "run_child", launcher)
    if bad is None:
        assert m._source_preflight(identity) == m._proof(identity, False)
    else:
        with pytest.raises(m.CloudControlError, match="cloud_control_source_preflight_refused"):
            m._source_preflight(identity)
    assert len(observed) == 1
    command, kwargs = observed[0]
    assert command[:3] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin")
    policy = command[command.index("-p") + 1]
    assert all(rule in policy for rule in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", "/usr/bin/security"))
    assert all(flag in command for flag in ("-I", "-S", "-B", "pycache_prefix=" + m.EMPTY_CACHE_PREFIX))
    assert "_worker(identity)" in command[-1] and "_git(" not in command[-1]
    assert "QC_USER_ID" not in str(command) and "QC_API_TOKEN" not in str(command)
    assert kwargs == {"cwd": m.LANE_ROOT, "env": None, "timeout": 60, "cap": 8192}


def test_generated_cell_has_only_fixed_control_sdk_calls_and_explicit_import():
    _, cell = m.build_invented_cell(NONCE)
    tree = ast.parse(cell)
    imported = [(node.module, tuple(alias.name for alias in node.names))
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert imported == [("QuantConnect.Research", ("QuantBook",))]
    assert {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} == {"contextlib", "hashlib", "json"}
    attributes = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert attributes <= {"dumps", "loads", "sha256", "encode", "hexdigest", "redirect_stdout", "redirect_stderr", "contains_key", "save"}
    names = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not names & {"open", "exec", "eval", "compile", "getattr", "setattr", "__import__"}
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "contains_key" for node in ast.walk(tree)) == 1
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "save" for node in ast.walk(tree)) == 1


def test_cli_mistaken_private_looking_arguments_are_never_echoed(capsys):
    with pytest.raises(SystemExit) as exc:
        m.main(["--expected-head", "a" * 40, "--api-token", "invented-not-a-token"])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "cloud_control_argument_refused\n"
