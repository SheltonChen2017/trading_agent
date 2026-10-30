"""Fabricated code/lane and fake kernel composition, never a real source run."""
from contextlib import contextmanager
import ctypes
import errno
import os
from pathlib import Path
import socket

import pytest

from data.hashing import hash_bytes, hash_payload

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "fcntl",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "fcntl at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts import diagnose_short_interest_immutable_metadata as proof
from scripts import short_interest_immutable_metadata as immutable
from test_short_interest_immutable_metadata import kernel, REAL_NATIVE_SET

REAL_CHALLENGE = proof._challenge


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("external seam forbidden in fabricated proof")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(immutable, "_native_set", denied)
    for module, name in ((proof.previous.count, "run_registered"),
        (proof.previous.count, "capture_chunk"), (proof.previous.count, "read_named_keychain"),
        (proof.previous.count.old, "run_registered"), (proof.previous.count.old, "read_named_keychain"),
        (proof.previous.count.transport, "http")):
        monkeypatch.setattr(module, name, denied)


class Harness:
    def __init__(self, monkeypatch, root):
        self.root, self.tick, self.metadata, self.events = root, 100.0, None, []
        self.boundary_hook = lambda: None
        self.native_noop = False
        fake_set = immutable._native_set
        class Operation:
            def __call__(unused, fd, flags):
                assert flags in (2, 66)
                if not self.native_noop:
                    fake_set(fd, initial_flags=flags & ~2)
                ctypes.set_errno(0)
                return 0
        class Library:
            fchflags = Operation()
        # Exercise the exact original Python/ctypes call body; only the
        # fabricated native boundary is replaced, never a real file flag.
        monkeypatch.setattr(immutable, "_native_set", REAL_NATIVE_SET)
        monkeypatch.setattr(immutable.ctypes, "CDLL", lambda *args, **kwargs: Library())
        self.mapping = {}
        for name in proof.code_paths():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            path.chmod(0o600)
            self.mapping[name] = hash_bytes(name.encode())
        class Guard:
            def __init__(unused, *args, **kwargs): pass
            def refresh(unused): self.events.append("refresh")
            def check(unused): self.boundary_hook()
            def binding(unused): return root, "c" * 40, "b" * 40
        monkeypatch.setattr(proof.previous.lane, "LaneGuard", Guard)
        monkeypatch.setattr(proof.previous.lane, "ROOT", root)
        monkeypatch.setattr(proof, "__file__", str(root / proof.DRIVER))
        (root / "proof-parent").mkdir(mode=0o700)
        monkeypatch.setattr(proof, "OUTPUT", Path("proof-parent/fresh-offline-proof"))
        monkeypatch.setattr(proof.time, "monotonic", lambda: self.tick)
        monkeypatch.setattr(proof.time, "sleep", self.sleep)
        monkeypatch.setattr(proof.previous.count.old.cache, "_git",
            lambda unused_root, args, unused_guard: (args[1] if args[0] == "check-ignore"
                else args[1].split(":", 1)[1]).encode())
        prepare = immutable.prepare_owned_immutable_metadata
        @contextmanager
        def wrapped(*args, **kwargs):
            with prepare(*args, **kwargs, monotonic=lambda: self.tick, sleep=self.sleep) as value:
                self.metadata = value
                yield value
        monkeypatch.setattr(immutable, "prepare_owned_immutable_metadata", wrapped)
        monkeypatch.setattr(proof, "_challenge", lambda *args: [
            {"challenge": name, "result": "denied", "errno_name": "EPERM"}
            for name in ("write_open", "same_mode_fchmod", "fixed_fsetxattr")])
        monkeypatch.setattr(proof, "PROTOCOL_SHA256", hash_payload(proof.protocol()))

    def sleep(self, seconds): self.tick += seconds
    def run(self):
        return proof.run_registered(self.root, runtime_head="c" * 40,
            actual_remote="b" * 40, complete_code_manifest=self.mapping)
    @property
    def path(self): return self.root / proof.OUTPUT / proof.NAME


def test_registered_composition_closes_original_code_and_metadata_without_source_dispatch(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    result = h.run()
    assert result["status"] == "closed_offline_new_inode_only"
    assert result["original_code_and_metadata_contexts_closed"] is True
    assert result["seal_stamp_sha256"] == h.metadata.closed_summary()["seal_stamp_sha256"]
    assert result["helper_closed_summary_sha256"] == hash_payload(h.metadata.closed_summary())
    assert h.path.read_bytes() == proof.previous.metadata_bytes()
    assert [path.name for path in h.path.parent.iterdir()] == [proof.NAME]
    assert result["authority"] == proof.authority()
    assert result["authority"]["historical_repair_established"] is False
    assert len(kernel[1]) == 1 and h.tick >= 106


def test_genuine_registered_composition_preserves_initial_document_tracking(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    def inherit_tracked():
        if h.path.exists():
            info = h.path.stat()
            kernel[0].setdefault((info.st_dev, info.st_ino), 64)
    h.boundary_hook = inherit_tracked
    result = h.run()
    assert result["status"] == "closed_offline_new_inode_only"
    observed = h.metadata.closed_summary()
    assert observed["initial_flags"] == 64 and observed["expected_flags"] == 66
    assert result["seal_stamp_sha256"] == observed["seal_stamp_sha256"]
    assert len(kernel[1]) == 1


@pytest.mark.parametrize("when", ["code_exit", "fresh_code", "after_metadata_close", "output_close", "output_close_code"])
def test_late_mutation_always_refuses_original_seal_without_adoption(monkeypatch, tmp_path, kernel, when):
    h = Harness(monkeypatch, tmp_path)
    if when in {"code_exit", "fresh_code"}:
        old = proof._code; calls = []
        def code(*args):
            result = old(*args); calls.append(1)
            if len(calls) == (2 if when == "code_exit" else 3): h.path.chmod(0o600)
            return result
        monkeypatch.setattr(proof, "_code", code)
    elif when == "after_metadata_close":
        old = immutable.ImmutableMetadataCustody.closed_summary
        def summary(value):
            result = old(value); h.path.chmod(0o600); return result
        monkeypatch.setattr(immutable.ImmutableMetadataCustody, "closed_summary", summary)
    else:
        old = proof.previous.prior._OwnedOutput.close
        def close(value):
            old(value)
            if value._anchor[0] == h.path.parent:
                if when == "output_close": h.path.chmod(0o600)
                else: (h.root / proof.HELPER).write_bytes(b"fabricated code changed after output close")
        monkeypatch.setattr(proof.previous.prior._OwnedOutput, "close", close)
    with pytest.raises((proof.ImmutableProofRefusal, immutable.ImmutableMetadataRefusal,
            immutable.creator.NewMetadataRefusal, immutable.creator.cache.contract.AnchorCacheRefusal)):
        h.run()
    assert h.path.read_bytes() == proof.previous.metadata_bytes() and len(kernel[1]) == 1


def test_original_parent_anchor_cannot_be_replaced_after_output_close(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    old = proof.previous.prior._OwnedOutput.close
    def close(value):
        old(value)
        if value._anchor[0] == h.path.parent:
            parent = h.path.parent.parent
            retained = h.root / "retained-original-parent"
            parent.rename(retained); parent.mkdir(mode=0o700)
            (retained / h.path.parent.name).rename(h.path.parent)
    monkeypatch.setattr(proof.previous.prior._OwnedOutput, "close", close)
    with pytest.raises(proof.ImmutableProofRefusal, match="original_stamp_changed"): h.run()
    assert h.path.read_bytes() == proof.previous.metadata_bytes()


def test_deadline_after_last_code_audit_refuses(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    old = proof._code; calls = []
    def code(*args):
        result = old(*args); calls.append(1)
        if len(calls) == 3: h.tick += 121
        return result
    monkeypatch.setattr(proof, "_code", code)
    with pytest.raises(proof.ImmutableProofRefusal, match="deadline"): h.run()


def test_code_change_before_final_exit_cannot_emit_closed_result(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    old = proof._code; calls = []
    def code(*args):
        calls.append(1)
        if len(calls) == 3: (h.root / proof.HELPER).write_bytes(b"fabricated different code")
        return old(*args)
    monkeypatch.setattr(proof, "_code", code)
    with pytest.raises((proof.ImmutableProofRefusal,
            immutable.creator.cache.contract.AnchorCacheRefusal)) as refused:
        h.run()
    assert proof.failure_summary(refused.value)["category"] == "local_contract_refusal"


def test_kernel_noop_cannot_be_published_as_a_pass(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    h.native_noop = True
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"): h.run()
    report = proof.failure_summary(immutable.ImmutableMetadataRefusal("immutable_flags_changed"))
    observed = report["native_transition"]["diagnostic"]
    assert observed["observer_complete"] is True and observed["native_result"] == 0
    assert observed["immediate_after_native"]["fd_flags"] == 0
    assert observed["classification"] == "required_flags_absent_at_immediate_observation"


def test_direct_proof_refusal_names_its_own_frame_not_the_parent_registered_runner(monkeypatch, tmp_path, kernel):
    h = Harness(monkeypatch, tmp_path)
    monkeypatch.setattr(proof, "_challenge", REAL_CHALLENGE)
    with pytest.raises(proof.ImmutableProofRefusal, match="challenge_not_denied") as failed:
        h.run()
    report = proof.failure_summary(failed.value)["native_transition"]["diagnostic"]
    assert report["first_controlled_refusal"]["phase"] == "proof__challenge"
    assert report["first_controlled_refusal"]["contract_code"] == "immutable_proof_challenge_not_denied"


@pytest.mark.parametrize("ticks", [(100.0, float("nan"), 100.0), (100.0, 106.0, 105.0)])
def test_every_hold_sample_is_validated_and_cannot_hide_a_skipped_or_backdated_hold(monkeypatch, tmp_path, kernel, ticks):
    h = Harness(monkeypatch, tmp_path)
    samples = []
    def challenge(*unused):
        samples.extend(value + h.tick - 100 if value == value else value for value in ticks)
        if all(value == value for value in ticks): h.tick = samples[-1]
        return []
    monkeypatch.setattr(proof, "_challenge", challenge)
    monkeypatch.setattr(proof.time, "monotonic", lambda: samples.pop(0) if samples else h.tick)
    with pytest.raises(proof.ImmutableProofRefusal, match="deadline"): h.run()


def test_protocol_has_no_old_evidence_or_provider_authority():
    value = proof.protocol()
    assert len(value["code_paths"]) == len(set(value["code_paths"])) == 61
    assert value["new_inodes"] == 1 and value["retries"] == 0
    assert value["old_evidence_reopened"] is False
    assert value["required_errno"] == "EPERM"
    assert value["minimum_hold_seconds"] == 5 and value["maximum_seconds"] == 120
    assert value["immutable_helper_policy_sha256"] == hash_payload(immutable.policy())


@pytest.mark.parametrize("which", [1, 2])
def test_original_and_terminal_code_context_close_failure_cannot_return_a_pass(monkeypatch, tmp_path, kernel, which):
    h = Harness(monkeypatch, tmp_path)
    original = proof.previous.count.old.cache.HeldFiles.__exit__
    count = []
    def close(value, *args):
        is_code = len(value._anchor[1]) == 61
        result = original(value, *args)
        if is_code:
            count.append(1)
            if len(count) == which: raise RuntimeError("fabricated code context close")
        return result
    monkeypatch.setattr(proof.previous.count.old.cache.HeldFiles, "__exit__", close)
    with pytest.raises(RuntimeError, match="fabricated code context close"): h.run()
    assert h.path.read_bytes() == proof.previous.metadata_bytes()


@pytest.mark.parametrize("result,number", [(False, errno.EPERM), (1, errno.EPERM),
    (-1.0, errno.EPERM), (-1, errno.EACCES)])
def test_fsetxattr_requires_exact_darwin_result_and_errno(monkeypatch, result, number):
    class Operation:
        def __call__(self, *args): ctypes.set_errno(number); return result
    call = Operation()
    class Library: fsetxattr = call
    monkeypatch.setattr(proof.ctypes, "CDLL", lambda name, use_errno: Library())
    def denied(*args, **kwargs): raise OSError(errno.EPERM, "fabricated")
    monkeypatch.setattr(proof.os, "open", denied)
    monkeypatch.setattr(proof.os, "fchmod", denied)
    class Owned: _anchor = (None, None, 5)
    with pytest.raises(proof.ImmutableProofRefusal): proof._challenge(7, Owned())
    assert call.argtypes == [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    assert call.restype is ctypes.c_int


@pytest.mark.parametrize("operation", ["write_open", "same_mode_fchmod", "fixed_fsetxattr"])
def test_challenges_require_each_exact_denial(monkeypatch, operation):
    class Operation:
        def __call__(self, *args):
            ctypes.set_errno(errno.EPERM)
            return -1
    class Library: fsetxattr = Operation()
    monkeypatch.setattr(proof.ctypes, "CDLL", lambda *a, **kw: Library())
    class Owned: _anchor = (None, None, 5)
    def open(*args, **kwargs):
        if operation == "write_open": return 44
        raise OSError(errno.EPERM, "fabricated")
    monkeypatch.setattr(proof.os, "open", open)
    monkeypatch.setattr(proof.os, "close", lambda unused: None)
    def chmod(*args):
        if operation != "same_mode_fchmod": raise OSError(errno.EPERM, "fabricated")
    monkeypatch.setattr(proof.os, "fchmod", chmod)
    if operation == "fixed_fsetxattr":
        monkeypatch.setattr(Library.fsetxattr, "__call__", lambda *args: 0)
        class Pass:
            def __call__(self, *args): return 0
        Library.fsetxattr = Pass()
    with pytest.raises(proof.ImmutableProofRefusal, match="not_denied"):
        proof._challenge(7, Owned())
