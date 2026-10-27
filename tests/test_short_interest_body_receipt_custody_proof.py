"""Explicit fabricated pair/kernel, volume and Git seams; no actual proof."""
from contextlib import contextmanager
from copy import deepcopy
import errno
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("resource", reason="original protected runtime imports POSIX resource")
pytest.importorskip("fcntl", reason="original immutable runtime imports POSIX fcntl")
from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_body_receipt_custody as proof


class Pair:
    """Fabricated ORIGINAL pair-seal/closure seam, never a source capability."""
    def __init__(self, h, owned, body):
        self.h, self.owned, self.phase = h, owned, "LIVE"
        receipt = canonical_json({"synthetic": True, "body_sha256": hash_bytes(body),
            "bytes": len(body), "source_admitted": False}).encode()
        self.files = []
        for role, name, raw in (("body", proof.custody.BODY_NAME, body), ("receipt", proof.custody.RECEIPT_NAME, receipt)):
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=owned._anchor[2])
            try:
                view = memoryview(raw)
                while view: view = view[os.write(fd, view):]
                os.fsync(fd)
            finally: os.close(fd)
            info = (owned._anchor[0] / name).lstat()
            self.files.append({"role": role, "name": name, "raw": raw,
                "seal_stamp_sha256": hash_payload(list(proof.base.immutable._stamp(info)))})
        self.check()

    def _original(self):
        for row in self.files:
            path = self.owned._anchor[0] / row["name"]
            assert hash_payload(list(proof.base.immutable._stamp(path.lstat()))) == row["seal_stamp_sha256"]
            assert path.read_bytes() == row["raw"]

    def check(self):
        assert self.phase == "LIVE"; self._original(); self.h.pair_checks += 1

    def read_body(self): self.check(); return self.files[0]["raw"]
    def read_receipt(self): self.check(); return self.files[1]["raw"]
    def observation(self):
        return {"files": [{key: row[key] for key in ("role", "name", "seal_stamp_sha256")} for row in self.files]}
    def check_after_close(self):
        assert self.phase == "CLOSED"; self._original(); self.h.pair_after += 1
    def closed_summary(self):
        self.check_after_close()
        return {"status": "fabricated_original_pair_closed", "source_admitted": False,
            "files": self.observation()["files"]}


class Volume:
    def __init__(self, h, boundary):
        self.h, self.boundary, self.phase = h, boundary, "LIVE"
        self.mountpoint = h.root / "proof-parent" / "new-volume"
        self.mountpoint.mkdir(mode=0o700)
    def check(self):
        assert self.phase == "LIVE"; self.boundary(); self.boundary()
    def check_after_close(self):
        assert self.phase == "CLOSED"; self.h.volume_after += 1; self.h.volume_after_hook()
    def closed_summary(self):
        self.check_after_close(); return {"status": "fabricated_volume_closed", "source_admitted": False}


class Diagnostic:
    def __init__(self, h): self.h, self.closed = h, False
    def report(self):
        assert self.closed
        return {"diagnostic": {"observer_complete": True, "native_call_count": 2,
            "distinct_original_inodes": True, "source_admitted": False}, "diagnostic_sha256": "f" * 64}


@pytest.fixture
def h(monkeypatch, tmp_path):
    h = SimpleNamespace(root=tmp_path, tick=100.0, pair=None, volume=None, diagnostic=None,
        pair_checks=0, pair_after=0, volume_after=0, volume_after_hook=lambda: None,
        pair_close_hook=lambda: None, volume_close_hook=lambda: None, mapping={})
    for name in ("_RUN_USED", "_CLOSED_FAILED"):
        monkeypatch.setattr(proof, name, False)
    for name in ("_CLOSED_RECORD", "_CLOSED_ORIGINAL", "_LAST_TRANSITION"):
        monkeypatch.setattr(proof, name, None)
    for name in proof.code_paths():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode()); path.chmod(0o600); h.mapping[name] = hash_bytes(name.encode())
    (tmp_path / "proof-parent").mkdir(mode=0o700)
    class Guard:
        def __init__(self, *args, **kwargs): pass
        def check(self): pass
        def refresh(self): pass
        def binding(self): return tmp_path, "c" * 40, "b" * 40
    monkeypatch.setattr(proof.base.previous.lane, "ROOT", tmp_path)
    monkeypatch.setattr(proof.base.previous.lane, "LaneGuard", Guard)
    monkeypatch.setattr(proof.base.previous.count.old.cache, "_git", lambda root, args, guard:
        (args[1] if args[0] == "check-ignore" else args[1].split(":", 1)[1]).encode())
    monkeypatch.setattr(proof, "__file__", str(tmp_path / proof.DRIVER))
    monkeypatch.setattr(proof.time, "monotonic", lambda: h.tick)
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: setattr(h, "tick", h.tick + seconds))
    # Fabricated flag observation only; no native setter is reached.
    monkeypatch.setattr(proof.base.immutable, "_flags", lambda info: 2)
    def never(*args, **kwargs): raise AssertionError("actual native/provider seam forbidden")
    monkeypatch.setattr(proof.base.immutable, "_native_set", never)
    monkeypatch.setattr(proof.storage, "_run", never)
    monkeypatch.setattr(proof.base.previous.count, "run_registered", never)
    monkeypatch.setattr(proof.base.previous.count, "read_named_keychain", never)
    monkeypatch.setattr(proof.base.previous.count.transport, "http", never)
    @contextmanager
    def volume(root, *, boundary):
        assert h.volume is None; h.volume = Volume(h, boundary); h.volume.check()
        yield h.volume
        h.volume.check(); h.volume_close_hook(); h.volume.phase = "CLOSED"
    @contextmanager
    def pair(owned, body, *, binding, boundary):
        assert h.pair is None and len(body) == 2097152
        h.pair = Pair(h, owned, body); boundary()
        yield h.pair
        h.pair.check(); h.pair_close_hook(); h.pair.phase = "CLOSED"
    @contextmanager
    def monitor(*, directory_fd, binding):
        assert h.diagnostic is None; h.diagnostic = Diagnostic(h)
        yield h.diagnostic
        h.diagnostic.closed = True
    monkeypatch.setattr(proof.storage, "prepare_registered_volume", volume)
    monkeypatch.setattr(proof.custody, "prepare_owned_body_receipt", pair)
    monkeypatch.setattr(proof.monitor, "observe_original_transition", monitor)
    monkeypatch.setattr(proof, "binding", lambda: SimpleNamespace(sha256="e" * 64))
    monkeypatch.setattr(proof, "_challenge", lambda *args: [
        {"challenge": name, "result": "denied", "errno_name": "EPERM"}
        for name in ("write_open", "same_mode_fchmod", "fixed_fsetxattr")])
    monkeypatch.setattr(proof, "PROTOCOL_SHA256", hash_payload(proof.protocol()))
    h.run = lambda: proof.run_registered(tmp_path, runtime_head="c" * 40, actual_remote="b" * 40,
        complete_code_manifest=h.mapping)
    return h


def test_complete_fabricated_composition_closes_original_pair_code_output_volume(h):
    result = h.run()
    assert result["status"] == "closed_offline_synthetic_maximum_body_receipt_only"
    assert result["files"][0]["bytes"] == 2097152
    assert result["files"][0]["raw_sha256"] == proof.BODY_SHA256
    assert h.pair.phase == h.volume.phase == "CLOSED" and h.diagnostic.closed
    assert h.tick >= 105 and h.pair_after >= 2 and h.volume_after >= 3
    assert proof.validate_closed_result(result) is True
    assert result["authority"]["source_admitted"] is False
    assert result["authority"]["persistent_storage_qualified"] is False
    assert result["authority"]["budget_settlement_authority"] is False


def test_original_terminal_result_is_not_a_matching_clone_or_claimed_hash(h):
    result = h.run()
    with pytest.raises(proof.BodyReceiptProofRefusal, match="not_original_closed"):
        proof.validate_closed_result(deepcopy(result))
    with pytest.raises(proof.BodyReceiptProofRefusal): proof.validate_closed_result(result)


def test_postissue_result_mutation_cannot_be_restored_and_admitted(h):
    result = h.run(); prior = result["files"][0]["raw_sha256"]
    result["files"][0]["raw_sha256"] = "0" * 64
    with pytest.raises(proof.BodyReceiptProofRefusal): proof.validate_closed_result(result)
    result["files"][0]["raw_sha256"] = prior
    with pytest.raises(proof.BodyReceiptProofRefusal): proof.validate_closed_result(result)


@pytest.mark.parametrize("role", [0, 1])
def test_postissue_original_file_drift_permanently_vetoes_closure(h, role):
    result = h.run(); row = h.pair.files[role]
    (h.pair.owned._anchor[0] / row["name"]).chmod(0o600)
    with pytest.raises((AssertionError, proof.BodyReceiptProofRefusal)): proof.validate_closed_result(result)
    assert proof._CLOSED_FAILED is True


def test_late_code_drift_after_factory_issuance_cannot_be_skipped(h):
    result = h.run(); (h.root / proof.DRIVER).write_bytes(b"changed original code")
    with pytest.raises(Exception): proof.validate_closed_result(result)
    assert proof._CLOSED_FAILED is True


def test_pair_inner_close_failure_prevents_any_terminal_issuance(h):
    def fail(): raise RuntimeError("fabricated pair close failure")
    h.pair_close_hook = fail
    with pytest.raises(RuntimeError, match="pair close failure"): h.run()
    assert proof._CLOSED_RECORD is None


def test_volume_close_failure_cannot_promote_closed_pair(h):
    def fail(): raise RuntimeError("fabricated volume close failure")
    h.volume_close_hook = fail
    with pytest.raises(RuntimeError, match="volume close failure"): h.run()
    assert h.pair.phase == "CLOSED" and proof._CLOSED_RECORD is None


def test_volume_postclose_failure_prevents_issuance(h):
    def fail(): raise proof.storage.IsolatedVolumeRefusal("isolated_mount_filesystem_refused")
    h.volume_after_hook = fail
    with pytest.raises(proof.storage.IsolatedVolumeRefusal): h.run()
    assert proof._CLOSED_RECORD is None


def test_terminal_clock_delay_permanently_vetoes_validation(h):
    result = h.run(); h.tick += 421
    with pytest.raises(proof.BodyReceiptProofRefusal, match="deadline"): proof.validate_closed_result(result)
    assert proof._CLOSED_FAILED is True


def test_delayed_final_UTC_sample_cannot_escape_whole_deadline(h, monkeypatch):
    original = proof.base.previous.prior._utc_now
    def delayed():
        value = original()
        if h.volume is not None and h.volume.phase == "CLOSED": h.tick += 421
        return value
    monkeypatch.setattr(proof.base.previous.prior, "_utc_now", delayed)
    with pytest.raises(proof.BodyReceiptProofRefusal, match="deadline"): h.run()
    assert proof._CLOSED_RECORD is None


def test_failed_independent_fd_close_still_drains_other_original_fd(monkeypatch):
    calls = []
    def close(fd):
        calls.append(fd)
        if fd == 42: raise OSError("fabricated close failure")
    monkeypatch.setattr(proof.os, "close", close)
    fds = [41, 42]
    with pytest.raises(proof.BodyReceiptProofRefusal, match="fd_close_failed"): proof._drain_fds(fds)
    assert calls == [42, 41] and fds == []


def test_unregistered_proof_does_not_enter_volume_or_pair(h, monkeypatch):
    monkeypatch.setattr(proof, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(proof.BodyReceiptProofRefusal, match="registration_changed"): h.run()
    assert h.volume is h.pair is None
    with pytest.raises(proof.BodyReceiptProofRefusal, match="already_invoked"): h.run()


def test_policy_and_body_have_exact_finite_false_authority():
    value = proof.protocol()
    assert len(proof.synthetic_body()) == 2097152
    assert hash_bytes(proof.synthetic_body()) == proof.BODY_SHA256
    assert len(proof.code_paths()) == len(set(proof.code_paths())) == 70
    assert value["native_set_calls"] == value["new_probe_inodes"] == 2
    assert value["native_roles"] == ["body", "receipt"]
    assert value["per_file_creation_seal_seconds"] == 8 and value["minimum_hold_seconds"] == 5
    assert value["retries"] == 0 and value["old_evidence_reopened"] is False
    assert value["authority"]["budget_settlement_authority"] is False


def test_fixed_failure_projection_does_not_emit_exception_text(monkeypatch):
    monkeypatch.setattr(proof, "_LAST_TRANSITION", None)
    monkeypatch.setattr(proof.storage, "association_diagnostic", lambda: {"status": "not_observed"})
    value = proof.failure_summary(RuntimeError("PRIVATE PATH AND SECRET"))
    assert "PRIVATE" not in canonical_json(value) and "SECRET" not in canonical_json(value)


@pytest.mark.parametrize("number,name", [(errno.ENOSPC, "ENOSPC"), (errno.EIO, "EIO")])
def test_original_os_errno_survives_proof_projection_without_paths_or_messages(monkeypatch, number, name):
    monkeypatch.setattr(proof, "_LAST_TRANSITION", None)
    monkeypatch.setattr(proof.storage, "association_diagnostic", lambda: {"status": "not_observed"})
    value = proof.failure_summary(OSError(number, "PRIVATE MESSAGE SECRET", "/PRIVATE/FILENAME"))
    assert value["category"] == "local_os_error" and value["errno_name"] == name
    assert value["contract_code"] is None
    assert "PRIVATE" not in canonical_json(value) and "SECRET" not in canonical_json(value)


def test_exact_runtime_ast_plus_one_bound_antecedent_equals_held_manifest():
    import ast
    root = Path(__file__).parents[1]
    def resolve(module):
        base = root / module.replace(".", "/")
        return next((path.relative_to(root).as_posix() for path in
            (base.with_suffix(".py"), base / "__init__.py") if path.is_file()), None)
    pending, found = [proof.WRAPPER], set()
    def add(module):
        parts = module.split(".")
        for length in range(1, len(parts) + 1):
            path = resolve(".".join(parts[:length]))
            if path and path not in found: pending.append(path)
    while pending:
        path = pending.pop()
        if path in found: continue
        found.add(path)
        package = path[:-3].replace("/", ".").rsplit(".", 1)[0]
        for node in ast.walk(ast.parse((root / path).read_bytes())):
            if isinstance(node, ast.Import):
                for alias in node.names: add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    parts = package.split(".")
                    module = ".".join(parts[:len(parts) - node.level + 1]
                        + ([module] if module else []))
                add(module)
                for alias in node.names:
                    if alias.name != "*": add(module + "." + alias.name)
    antecedents = set(proof.protocol()["bound_antecedent_not_runtime_imported"])
    assert len(found) == 69 and antecedents == {proof.previous.WRAPPER}
    assert not found.intersection(antecedents)
    assert found | antecedents == set(proof.code_paths())
    assert len(proof.code_paths()) == 70
