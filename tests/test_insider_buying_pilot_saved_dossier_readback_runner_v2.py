"""Invented caller/Git/role gates; the outer caller supplies native isolation.

No real native install, child, Git command, retained leaf or receipt is used.
These tests prove source/receipt acceptance ordering and refusal paths; they
do not substitute mocked calls for the required native health/readback runs.
"""
from collections import deque
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from research import insider_buying_pilot_saved_dossier_readback_runner_v2 as m


def _identity(head="b" * 40, sources=None):
    sources = dict(sources or {m.SELF: m.sha(b"invented source")})
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": head,
            "clean": True, "source_sha256": sources,
            "source_inventory_sha256": m.sha(m.raw(sources))}


def _manifest():
    identity = _identity()
    admin = {"common": str(m.isolation.EXPECTED_COMMON), "worktree": str(m.isolation.EXPECTED_GITDIR),
             "files": {str(path): {"present": True, "bytes": 4, "sha256": "a" * 64,
                        "version": [1, 2, 0o100644, 1, 501, 20, 4, 8, 9, 0]}
                       for path in m.isolation._admin_paths()}}
    return {"identity": identity,
            "versions": {name: [1, 2, 0o100644, 1, 501, 20, len(b"invented source"), 8, 9, 0]
                         for name in identity["source_sha256"]},
            "admin": admin,
            "tree": {"directories": [str(m.ROOT)], "ignores": []},
            "runtime_pins": {path: {"bytes": 1, "sha256": "c" * 64}
                             for path in ("/opt/invented-runtime/bin/python", str(m.isolation.GIT_IMAGE))},
            "ignore_pins": {}}


def _runtime_shape(monkeypatch):
    monkeypatch.setattr(m.isolation, "runtime_layout", lambda: (
        (Path("/opt/invented-runtime"),), (Path("/opt/invented-runtime/bin/python"),), ()))


def test_empty_package_initializer_is_authenticated_instead_of_omitted(monkeypatch, tmp_path):
    leaf = tmp_path / "__init__.py"
    leaf.write_bytes(b"")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.isolation, "validate_source_names", lambda names: names)
    body, observed = m.code_bytes("__init__.py")
    assert body == b"" and observed[6] == 0


def test_source_manifest_accepts_a_pinned_empty_git_source(monkeypatch):
    _runtime_shape(monkeypatch)
    manifest = _manifest()
    manifest["versions"][m.SELF][6] = 0
    manifest["identity"]["source_sha256"][m.SELF] = m.sha(b"")
    manifest["identity"]["source_inventory_sha256"] = m.sha(m.raw(manifest["identity"]["source_sha256"]))
    assert m.validate_manifest(manifest) is manifest


def test_tree_plan_adds_only_the_fixed_optional_directory_not_a_data_subtree(monkeypatch):
    monkeypatch.setattr(m, "git_position", lambda *a, **k: None)
    monkeypatch.setattr(m, "git", lambda args, admin: b"research\n" if "-d" in args else b".gitignore\n")
    monkeypatch.setattr(Path, "is_dir", lambda path: path == m.ROOT / "tmp")
    tree = m.tree_plan("b" * 40, {})
    assert tree == {"directories": [str(m.ROOT), str(m.ROOT / "research"), str(m.ROOT / "tmp")],
                    "ignores": [str(m.ROOT / ".gitignore")]}


def _verified(manifest, original):
    return {"schema": m.SCHEMA + "/verified-sources", "completed": True,
            "reader_head": manifest["identity"]["head"],
            "reader_inventory": manifest["identity"]["source_inventory_sha256"],
            "reader_source_images_verified": len(manifest["identity"]["source_sha256"]),
            "original_inventory": original["source_inventory_sha256"] if original is not None else None,
            "original_source_images_verified": len(original["source_sha256"]) if original is not None else 0,
            "admin_sha256": m.sha(m.raw(manifest["admin"])),
            "runtime_sha256": m.sha(m.raw(manifest["runtime_pins"])),
            "ignore_sha256": m.sha(m.raw(manifest["ignore_pins"]))}


def _run_setup(monkeypatch, *, mode="health", reader_fault=None, verifier_fault=None,
               summary_refusal=False, late_close=None):
    manifest, events, workers = _manifest(), [], []
    original = _identity("d" * 40)
    summary = {"invented_summary": True}
    installed = {"value": False}

    class Guard:
        def __init__(self): self.closed = False; events.append("guard-open")
        def check(self): assert not self.closed; events.append("guard-check")
        def close(self):
            self.closed = True; events.append("guard-close")
            if late_close == "guard": raise RuntimeError("invented late refusal")

    class Worker:
        def __init__(self, role):
            self.role = role
            self.profile_sha256, self.command_sha256 = "c" * 64, "d" * 64
            workers.append(self)
        def activate(self, payload):
            assert installed["value"]
            events.append(("activate", self.role, deepcopy(payload)))
            if self.role == "readback":
                assert payload == {}
                if mode == "health":
                    result = {"schema": m.SCHEMA + "/health", "completed": True, "data_leaves": 0,
                              "reader_inventory": manifest["identity"]["source_inventory_sha256"]}
                else:
                    result = {"schema": m.SCHEMA + "/saved", "completed": True,
                              "original_identity": original, "summary": summary}
                if reader_fault: reader_fault(result)
            else:
                assert payload == {"original_identity": None if mode == "health" else original}
                result = _verified(manifest, payload["original_identity"])
                if verifier_fault: verifier_fault(result)
            return deepcopy(result)
        def close(self):
            events.append(("close", self.role))
            if late_close == self.role: raise RuntimeError("invented late refusal")

    def preflight(head):
        assert head == manifest["identity"]["head"]
        events.append("preflight"); return deepcopy(manifest)
    def prepare(role, bound, requested_mode):
        assert not installed["value"] and bound == manifest and requested_mode == mode
        events.append(("prepare", role)); return Worker(role)
    def policy(**kwargs):
        assert kwargs == {"sources": manifest["identity"]["source_sha256"], "controller": True}
        events.append("read-only-parent-profile"); return "invented read-only profile"
    def install(profile):
        assert profile == "invented read-only profile" and not installed["value"]
        installed["value"] = True; events.append("install-parent")
    def native_proof(*, source):
        assert installed["value"] and source is False; events.append("parent-native-proof")
    def current(value):
        assert value == manifest; events.append("source-current")
    def validate(value, **kwargs):
        events.append("validate-saved-summary")
        assert value == summary and kwargs == {"original_identity": original,
                                               "reader_identity": manifest["identity"]}
        if summary_refusal: raise m.receipt.SavedReadbackError("saved_summary_refused")
        return deepcopy(value)

    monkeypatch.setattr(m.native, "_WorkerMemoryGuard", Guard)
    monkeypatch.setattr(m, "source_preflight", preflight)
    monkeypatch.setattr(m, "prepare", prepare)
    monkeypatch.setattr(m.isolation, "policy", policy)
    monkeypatch.setattr(m, "install_parent", install)
    monkeypatch.setattr(m, "native_proof", native_proof)
    monkeypatch.setattr(m, "source_current", current)
    monkeypatch.setattr(m.receipt, "validate_summary", validate)
    return manifest, original, events, workers


def test_health_prepares_both_readers_then_installs_before_any_activation(monkeypatch):
    manifest, _original, events, workers = _run_setup(monkeypatch)
    result = m.run(manifest["identity"]["head"], mode="health")
    assert result["completed"] is True and result["files_written"] == 0
    assert result["original_input_leaves_replayed"] == 0
    assert result["authority"] == m.prior.transition.authority()
    assert events.index("preflight") < events.index(("prepare", "readback"))
    assert events.index(("prepare", "readback")) < events.index(("prepare", "source"))
    assert events.index(("prepare", "source")) < events.index("install-parent")
    first_activation = next(i for i, item in enumerate(events) if isinstance(item, tuple) and item[0] == "activate")
    assert events.index("parent-native-proof") < first_activation
    assert events[-3:] == [("close", "source"), ("close", "readback"), "guard-close"]
    assert len(workers) == 2


def test_saved_summary_is_validated_before_original_source_verifier_activation(monkeypatch):
    manifest, original, events, _workers = _run_setup(monkeypatch, mode="readback")
    result = m.run(manifest["identity"]["head"], mode="readback")
    verify = ("activate", "source", {"original_identity": original})
    assert events.index("validate-saved-summary") < events.index(verify)
    assert result["source_verification"] == _verified(manifest, original)
    assert result["receipt"] == {"invented_summary": True}


@pytest.mark.parametrize("fault", ("completed-only", "completed-alias", "leaves-alias", "inventory", "extra"))
def test_health_refuses_incomplete_untyped_or_unbound_result_before_source_activation(monkeypatch, fault):
    def mutate(value):
        if fault == "completed-only": value.clear(); value["completed"] = True
        elif fault == "completed-alias": value["completed"] = 1
        elif fault == "leaves-alias": value["data_leaves"] = False
        elif fault == "inventory": value["reader_inventory"] = "0" * 64
        else: value["PRIVATE-UNKNOWN"] = True
    manifest, _original, events, _workers = _run_setup(monkeypatch, reader_fault=mutate)
    with pytest.raises(m.ReadbackError, match="health_result_refused"):
        m.run(manifest["identity"]["head"], mode="health")
    assert not any(isinstance(item, tuple) and item[:2] == ("activate", "source") for item in events)
    assert events[-1] == "guard-close"


def test_saved_summary_refusal_stops_before_source_verification(monkeypatch):
    manifest, _original, events, _workers = _run_setup(monkeypatch, mode="readback", summary_refusal=True)
    with pytest.raises(m.receipt.SavedReadbackError, match="saved_summary_refused"):
        m.run(manifest["identity"]["head"], mode="readback")
    assert "validate-saved-summary" in events
    assert not any(isinstance(item, tuple) and item[:2] == ("activate", "source") for item in events)


@pytest.mark.parametrize("field,value", (("completed", 1), ("original_source_images_verified", False),
    ("reader_head", "c" * 40), ("runtime_sha256", "0" * 64)))
def test_source_verifier_result_requires_exact_types_and_reader_binding(monkeypatch, field, value):
    def mutate(result): result[field] = value
    manifest, _original, _events, _workers = _run_setup(monkeypatch, verifier_fault=mutate)
    with pytest.raises(m.ReadbackError, match="source_result_refused"):
        m.run(manifest["identity"]["head"], mode="health")


@pytest.mark.parametrize("late_close", ("source", "readback", "guard"))
def test_late_cleanup_failure_prevents_an_apparent_success_and_closes_all(monkeypatch, late_close):
    manifest, _original, events, _workers = _run_setup(monkeypatch, late_close=late_close)
    with pytest.raises(m.ReadbackError, match="cleanup_refused"):
        m.run(manifest["identity"]["head"], mode="health")
    assert events[-3:] == [("close", "source"), ("close", "readback"), "guard-close"]


def _preflight_setup(monkeypatch, *, tree_fault=None, source_fault=None):
    manifest, events = _manifest(), []
    _runtime_shape(monkeypatch)
    names = tuple(manifest["identity"]["source_sha256"])
    monkeypatch.setattr(m, "PARENT_INSTALLED", False)
    monkeypatch.setattr(m, "source_names", lambda: names)
    monkeypatch.setattr(m.isolation, "discover_admin", lambda: deepcopy(manifest["admin"]))
    monkeypatch.setattr(m, "source_profile", lambda requested, admin, tree=None: "invented source profile")
    monkeypatch.setattr(m, "command", lambda function, args, profile: (function, args, profile))
    monkeypatch.setattr(m, "source_current", lambda value: events.append(("current", deepcopy(value))))
    def launch(command, *, timeout):
        assert command[:4] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=en_US.UTF-8")
        function, args, _profile = command[4:]
        events.append((function, deepcopy(args), timeout))
        if function == "tree_worker":
            value = {"schema": m.SCHEMA + "/tree", "completed": True,
                     "head": manifest["identity"]["head"], "tree": deepcopy(manifest["tree"])}
            if tree_fault: tree_fault(value)
        else:
            assert function == "source_worker"
            value = {"schema": m.SCHEMA + "/source", "completed": True, "manifest": deepcopy(manifest)}
            if source_fault: source_fault(value)
        return value
    monkeypatch.setattr(m.stable.source, "_launch", launch)
    return manifest, events


def test_source_preflight_binds_both_native_source_stages_and_current_manifest(monkeypatch):
    manifest, events = _preflight_setup(monkeypatch)
    assert m.source_preflight(manifest["identity"]["head"]) == manifest
    assert events[0][0] == "tree_worker" and events[1][0] == "source_worker"
    assert events[0][2] == 120 and events[1][2] == 180
    assert events[1][1][-1] == manifest["tree"]
    assert events[-1] == ("current", manifest)


@pytest.mark.parametrize("fault", ("extra", "completed-alias", "head", "missing"))
def test_source_preflight_refuses_unbound_tree_stage_before_manifest_launch(monkeypatch, fault):
    def mutate(value):
        if fault == "extra": value["PRIVATE"] = True
        elif fault == "completed-alias": value["completed"] = 1
        elif fault == "head": value["head"] = "c" * 40
        else: value.pop("tree")
    manifest, events = _preflight_setup(monkeypatch, tree_fault=mutate)
    with pytest.raises(m.ReadbackError, match="tree_refused"):
        m.source_preflight(manifest["identity"]["head"])
    assert len(events) == 1 and events[0][0] == "tree_worker"


@pytest.mark.parametrize("fault", ("extra-envelope", "completed-alias", "extra-manifest", "head", "names", "admin", "tree"))
def test_source_preflight_refuses_stale_or_differently_scoped_manifest(monkeypatch, fault):
    def mutate(value):
        if fault == "extra-envelope": value["PRIVATE"] = True
        elif fault == "completed-alias": value["completed"] = 1
        else:
            manifest = value["manifest"]
            if fault == "extra-manifest": manifest["PRIVATE"] = True
            elif fault == "head": manifest["identity"]["head"] = "c" * 40
            elif fault == "names":
                manifest["identity"]["source_sha256"]["research/invented_extra.py"] = "e" * 64
                manifest["identity"]["source_inventory_sha256"] = m.sha(m.raw(manifest["identity"]["source_sha256"]))
            elif fault == "admin": manifest["admin"]["files"][next(iter(manifest["admin"]["files"]))]["sha256"] = "0" * 64
            else: manifest["tree"]["directories"].append(str(m.ROOT / "research"))
    manifest, events = _preflight_setup(monkeypatch, source_fault=mutate)
    with pytest.raises(m.ReadbackError, match="source_refused"):
        m.source_preflight(manifest["identity"]["head"])
    assert not any(item[0] == "current" for item in events)


@pytest.mark.parametrize("fault", ("version-bool", "version-extra", "runtime-bool", "runtime-extra", "ignore-extra"))
def test_manifest_requires_exact_version_runtime_and_ignore_shapes(monkeypatch, fault):
    manifest = _manifest(); _runtime_shape(monkeypatch)
    if fault == "version-bool": manifest["versions"][m.SELF][0] = True
    elif fault == "version-extra": manifest["versions"][m.SELF].append(0)
    elif fault == "runtime-bool": manifest["runtime_pins"][str(m.isolation.GIT_IMAGE)]["bytes"] = True
    elif fault == "runtime-extra": manifest["runtime_pins"][str(m.isolation.GIT_IMAGE)]["PRIVATE"] = True
    else: manifest["ignore_pins"]["/private/invented"] = {}
    with pytest.raises((m.ReadbackError, m.isolation.IsolationError)):
        m.validate_manifest(manifest)


def test_source_current_positive_control_rechecks_hash_versions_and_runtime(monkeypatch):
    manifest = _manifest(); _runtime_shape(monkeypatch)
    seen = []
    def code(name):
        seen.append(name); return b"invented source", deepcopy(manifest["versions"][name])
    monkeypatch.setattr(m, "code_bytes", code)
    monkeypatch.setattr(m, "runtime_pins", lambda: deepcopy(manifest["runtime_pins"]))
    m.source_current(manifest)
    assert seen == [m.SELF]


@pytest.mark.parametrize("fault", ("hash", "version", "runtime"))
def test_source_current_refuses_live_drift_before_acceptance(monkeypatch, fault):
    manifest = _manifest(); _runtime_shape(monkeypatch)
    observed = deepcopy(manifest["versions"][m.SELF])
    if fault == "version": observed[8] += 1
    monkeypatch.setattr(m, "code_bytes", lambda _name: (
        b"changed source" if fault == "hash" else b"invented source", observed))
    runtime = deepcopy(manifest["runtime_pins"])
    if fault == "runtime": runtime[str(m.isolation.GIT_IMAGE)]["sha256"] = "0" * 64
    monkeypatch.setattr(m, "runtime_pins", lambda: runtime)
    with pytest.raises(m.ReadbackError, match="runtime_changed" if fault == "runtime" else "source_changed"):
        m.source_current(manifest)


def _source_verification_setup(monkeypatch, *, git_fault=None, late_head=False):
    bodies = {m.SELF: b"invented source", "research/invented_old_a.py": b"old-a",
              "research/invented_old_b.py": b"old-b"}
    sources = {name: m.sha(body) for name, body in bodies.items()}
    manifest = _manifest(); manifest["identity"] = _identity(sources=sources)
    manifest["versions"] = {name: [1, 2, 0o100644, 1, 501, 20, len(body), 8, 9, 0]
                            for name, body in bodies.items()}
    original = _identity("d" * 40, {name: sources[name] for name in bodies if name != m.SELF})
    monkeypatch.setattr(m.receipt, "ORIGINAL_HEAD", original["head"])
    monkeypatch.setattr(m.receipt, "ORIGINAL_INVENTORY", original["source_inventory_sha256"])
    monkeypatch.setattr(m.receipt, "ORIGINAL_SOURCE_COUNT", len(original["source_sha256"]))
    events, calls, positions = [], [], []
    monkeypatch.setattr(m, "source_current", lambda value: events.append(("current", deepcopy(value))))
    monkeypatch.setattr(m.isolation, "check_admin", lambda value: events.append(("admin", deepcopy(value))))
    def position(head, admin, *, clean):
        assert head == manifest["identity"]["head"] and admin == manifest["admin"] and clean is True
        positions.append(head); events.append("position")
        if late_head and len(positions) == 2: raise m.ReadbackError("source_refused")
    def ignores(tree, *, head, admin):
        assert tree == manifest["tree"] and head == manifest["identity"]["head"] and admin == manifest["admin"]
        return deepcopy(manifest["ignore_pins"])
    monkeypatch.setattr(m, "git_position", position)
    monkeypatch.setattr(m, "ignore_pins", ignores)
    monkeypatch.setattr(m, "tree_plan", lambda head, admin: deepcopy(manifest["tree"]))
    def git(arguments, admin):
        assert admin == manifest["admin"] and arguments[0] == "show"
        head, name = arguments[1].split(":", 1); calls.append((head, name)); events.append(("git", head, name))
        if git_fault == (head, name): return b"different Git bytes"
        return bodies[name]
    monkeypatch.setattr(m, "git", git)
    return manifest, original, events, calls, positions


def test_source_verifier_checks_every_original_and_current_git_blob_before_success(monkeypatch):
    manifest, original, events, calls, positions = _source_verification_setup(monkeypatch)
    result = m.verify_sources(manifest, original)
    assert result == _verified(manifest, original)
    assert calls == [(original["head"], name) for name in original["source_sha256"]] + [
        (manifest["identity"]["head"], name) for name in manifest["identity"]["source_sha256"]]
    assert len(positions) == 2
    assert events[0] == events[-1] == ("current", manifest)


@pytest.mark.parametrize("scope", ("original", "current"))
def test_source_verifier_refuses_git_byte_drift_in_either_source_epoch(monkeypatch, scope):
    manifest, original, _events, _calls, _positions = _source_verification_setup(monkeypatch)
    name = next(iter(original["source_sha256"])) if scope == "original" else m.SELF
    head = original["head"] if scope == "original" else manifest["identity"]["head"]
    _source_verification_setup(monkeypatch, git_fault=(head, name))
    with pytest.raises(m.ReadbackError, match="original_source_refused" if scope == "original" else "source_refused"):
        m.verify_sources(manifest, original)


def test_source_verifier_refuses_head_advancement_after_the_blob_checks(monkeypatch):
    manifest, original, events, calls, positions = _source_verification_setup(monkeypatch, late_head=True)
    with pytest.raises(m.ReadbackError, match="source_refused"):
        m.verify_sources(manifest, original)
    assert len(calls) == len(original["source_sha256"]) + len(manifest["identity"]["source_sha256"])
    assert len(positions) == 2 and events[-1] == "position"


@pytest.mark.parametrize("fault", ("head", "branch", "root", "dirty"))
def test_git_position_rejects_stale_or_wrong_checkout_identity(monkeypatch, fault):
    head, admin = "b" * 40, _manifest()["admin"]
    def git(arguments, supplied):
        assert supplied == admin
        values = {("rev-parse", "--show-toplevel"): str(m.ROOT).encode(),
                  ("rev-parse", "HEAD"): head.encode(),
                  ("rev-parse", "--abbrev-ref", "HEAD"): m.BRANCH.encode(),
                  ("status", "--porcelain=v1", "--untracked-files=all"): b""}
        if fault == "head": values[("rev-parse", "HEAD")] = b"c" * 40
        elif fault == "branch": values[("rev-parse", "--abbrev-ref", "HEAD")] = b"other-lane"
        elif fault == "root": values[("rev-parse", "--show-toplevel")] = b"/invented/other-checkout"
        else: values[("status", "--porcelain=v1", "--untracked-files=all")] = b"?? invented-new.py\n"
        return values[arguments]
    monkeypatch.setattr(m, "git", git)
    with pytest.raises(m.ReadbackError, match="source_dirty" if fault == "dirty" else "source_refused"):
        m.git_position(head, admin, clean=True)


@pytest.mark.parametrize("changed", (False, True))
def test_ignore_source_requires_committed_git_bytes_even_if_live_metadata_is_stable(monkeypatch, changed):
    name, body = str(m.ROOT / ".gitignore"), b"invented-ignore\n"
    pin = {"present": True, "bytes": len(body), "sha256": m.sha(body),
           "version": [1, 2, 0o100644, 1, 501, 20, len(body), 8, 9, 0]}
    admin, head, calls = _manifest()["admin"], "b" * 40, []
    monkeypatch.setattr(m.isolation, "_read_admin", lambda path: (body, deepcopy(pin)))
    def git(arguments, supplied):
        assert arguments == ("show", head + ":.gitignore") and supplied == admin
        calls.append(arguments)
        return b"different committed ignore" if changed else body
    monkeypatch.setattr(m, "git", git)
    if changed:
        with pytest.raises(m.ReadbackError, match="ignore_changed"):
            m.ignore_pins({"ignores": [name]}, head=head, admin=admin)
    else:
        assert m.ignore_pins({"ignores": [name]}, head=head, admin=admin) == {name: pin}
    assert calls == [("show", head + ":.gitignore")]


def test_source_names_cover_eight_own_files_and_string_named_verifiers(monkeypatch):
    frozen = "research/invented_string_only_verifier.py"
    module = SimpleNamespace(__file__=str(m.ROOT / "research/invented_loaded.py"), FROZEN={frozen: "a" * 64})
    with monkeypatch.context() as patch:
        patch.setattr(m.custody, "_internal_source_paths", lambda _root: (m.SELF,))
        patch.setattr(m.sys, "modules", {"invented-loaded": module})
        patch.setattr(Path, "is_file", lambda _path: True)
        names = m.source_names()
    assert len(m.OWN) == 8 and set(m.OWN) <= set(names)
    assert frozen in names and set(m.prior.OWN) <= set(names)


@pytest.mark.parametrize("entry", ("preflight", "prepare"))
def test_no_late_source_or_reader_preparation_after_parent_install(monkeypatch, entry):
    monkeypatch.setattr(m, "PARENT_INSTALLED", True)
    monkeypatch.setattr(m, "source_names", lambda: pytest.fail("late source preparation"))
    monkeypatch.setattr(m.transport, "Prepared", lambda *_a, **_k: pytest.fail("late reader preparation"))
    with pytest.raises(m.ReadbackError, match="parent_refused"):
        if entry == "preflight": m.source_preflight("b" * 40)
        else: m.prepare("readback", _manifest(), "health")


@pytest.mark.parametrize("fault", (None, "stderr", "overflow", "exit"))
def test_git_wrapper_uses_hardened_command_environment_and_refuses_foreign_output(monkeypatch, fault):
    admin = _manifest()["admin"]
    arguments = ("rev-parse", "HEAD")
    expected_command = m.isolation.git_command(arguments, admin)
    expected_environment = m.isolation.git_environment(admin)
    calls, closed, killed_groups = [], [], []
    queues = {101: deque([b"invented result", b""]),
              102: deque([b"invented private stderr", b""] if fault == "stderr" else [b""])}

    class Stream:
        def __init__(self, descriptor): self.descriptor = descriptor
        def fileno(self): return self.descriptor
        def close(self): closed.append(self.descriptor)

    class Process:
        def __init__(self): self.stdout, self.stderr, self.pid = Stream(101), Stream(102), 12345
        def poll(self): return 0
        def wait(self, *, timeout):
            assert timeout > 0
            return 2 if fault == "exit" else 0

    class Selector:
        def __init__(self): self.items = {}
        def register(self, stream, _event, role):
            self.items[stream.fileno()] = SimpleNamespace(fileobj=stream, data=role)
        def unregister(self, stream): self.items.pop(stream.fileno())
        def get_map(self): return self.items
        def select(self, timeout):
            assert timeout > 0
            return [(next(iter(self.items.values())), 1)]
        def close(self): pass

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()
    def read(descriptor, cap):
        chunk = queues[descriptor].popleft()
        if len(chunk) > cap:
            queues[descriptor].appendleft(chunk[cap:]); chunk = chunk[:cap]
        return chunk

    with monkeypatch.context() as patch:
        patch.setattr(m.subprocess, "Popen", popen)
        patch.setattr(m.selectors, "DefaultSelector", Selector)
        patch.setattr(m.os, "set_blocking", lambda *_args: None)
        patch.setattr(m.os, "read", read)
        patch.setattr(m.os, "getpgrp", lambda: 12345)
        patch.setattr(m.os, "getpid", lambda: 12345)
        patch.setattr(m.os, "killpg", lambda *args: killed_groups.append(args))
        if fault:
            with pytest.raises(m.ReadbackError, match="git_refused"):
                m.git(arguments, admin, limit=2 if fault == "overflow" else 64)
        else:
            assert m.git(arguments, admin, limit=64) == b"invented result"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == expected_command
    assert kwargs["cwd"] == m.ROOT and kwargs["env"] == expected_environment
    assert kwargs["stdout"] == kwargs["stderr"] == m.subprocess.PIPE
    assert kwargs["start_new_session"] is False and kwargs.get("shell", False) is False
    assert "core.fsmonitor=false" in command and "core.hooksPath=/dev/null" in command
    assert "--no-replace-objects" in command and expected_environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert set(closed) == {101, 102}
    assert killed_groups == ([(12345, m.signal.SIGKILL)] if fault else [])
