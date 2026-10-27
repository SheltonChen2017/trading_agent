"""Original Python setter/control flow, fake native library, fabricated files."""
import ctypes
import errno
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap

import pytest

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_immutable_metadata as immutable
from scripts import short_interest_immutable_transition_diagnostics as transition
from scripts import diagnose_short_interest_immutable_metadata as proof
from test_short_interest_new_metadata_custody import Clock


class Harness:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path / "fabricated-new-output"
        self.root.mkdir(mode=0o700)
        self.owned = immutable.creator._OwnedOutput(self.root, lambda: None)
        self.clock = Clock()
        self.flags, self.calls, self.native_hook = {}, [], lambda fd: None
        self.boundary_hook = lambda: None
        prefix = b'{"is_capture_claim":false,"safe":"fabricated"}'
        self.raw = prefix + b" " * (186 - len(prefix))
        assert len(self.raw) == 186
        harness = self
        class Operation:
            def __call__(self, fd, flags):
                harness.calls.append((fd, flags))
                info = os.fstat(fd)
                harness.flags[info.st_dev, info.st_ino] = flags
                os.fchmod(fd, 0o600)  # Fake preseal metadata transition only.
                harness.native_hook(fd)
                ctypes.set_errno(0)
                return 0
        self.operation = Operation()
        class Library:
            fchflags = self.operation
        def library(name, *, use_errno):
            assert name == "/usr/lib/libSystem.B.dylib" and use_errno is True
            return Library()
        monkeypatch.setattr(immutable.ctypes, "CDLL", library)
        monkeypatch.setattr(immutable, "_platform", lambda: None)
        monkeypatch.setattr(immutable, "_flags", lambda info: self.flags.get((info.st_dev, info.st_ino), 64))

    @property
    def path(self):
        return self.root / transition.NAME

    def observer(self, **changes):
        return transition.observe_original_transition(directory_fd=self.owned._anchor[2],
            name=transition.NAME, **changes)

    def prepare(self):
        return immutable.prepare_owned_immutable_metadata(self.owned, transition.NAME,
            self.raw, parent=False, boundary=lambda: self.boundary_hook(),
            monotonic=self.clock, sleep=self.clock.sleep)

    def close(self):
        self.owned.close()


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden in fabricated diagnostics")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    assert sys.gettrace() is None
    try:
        yield
    finally:
        # Every test checks restoration explicitly; preserve the test runner
        # even when an assertion in an adversarial trace-loss test fails.
        sys.settrace(None)


@pytest.fixture
def h(tmp_path, monkeypatch):
    value = Harness(tmp_path, monkeypatch)
    try:
        yield value
    finally:
        value.close()


def test_original_native_call_is_traced_not_replaced_and_report_is_post_exit_copy(h):
    original = immutable._native_set
    with h.observer() as observed:
        with pytest.raises(transition.TransitionDiagnosticRefusal, match="not_closed"):
            observed.report()
        with h.prepare() as cap:
            cap.seal_once()
            cap.check()
            assert cap.read() == h.raw
    assert immutable._native_set is original is transition._NATIVE
    report = observed.report()
    value = report["diagnostic"]
    assert report["diagnostic_sha256"] == hash_payload(value)
    assert value["observer_complete"] is True and value["native_call_count"] == 1
    assert value["native_result"] == 0 and value["native_errno_name"] is None
    assert value["before_native"]["fd_flags"] == value["before_native"]["name_flags"] == 64
    assert value["immediate_after_native"]["fd_flags"] == value["immediate_after_native"]["name_flags"] == 66
    assert all(value["immediate_after_native"][key] for key in (
        "same_original_inode", "protections_match", "size_and_mtime_unchanged", "retained_fd_readonly"))
    assert value["classification"] == "required_flags_observed_without_recorded_loss"
    assert value["first_controlled_refusal"] is None and value["controlled_refusals"] == []
    assert len(h.calls) == 1 and h.calls[0][1] == 66
    assert h.operation.argtypes == (ctypes.c_int, ctypes.c_uint) and h.operation.restype is ctypes.c_int
    assert sys.gettrace() is None and cap.closed_summary()["phase"] == "CLOSED"
    assert str(h.path) not in canonical_json(value) and h.raw.decode() not in canonical_json(value)
    value["authority"]["source_admitted"] = True
    assert observed.report()["diagnostic"]["authority"] == transition.authority()


def test_returned_zero_without_immediate_bit_is_not_claimed_never_transiently_set(h):
    def no_bit(fd):
        info = os.fstat(fd)
        h.flags[info.st_dev, info.st_ino] = 64
    h.native_hook = no_bit
    observed = h.observer()
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"):
        with observed:
            with h.prepare():
                pytest.fail("unchanged flag admitted")
    value = observed.report()["diagnostic"]
    assert value["observer_complete"] is True and value["native_result"] == 0
    assert value["immediate_after_native"]["fd_flags"] == 64
    assert value["classification"] == "required_flags_absent_at_immediate_observation"
    assert value["first_controlled_refusal"]["contract_code"] == "immutable_flags_changed"
    assert sys.gettrace() is None and len(h.calls) == 1


def test_exact_unwrapped_guard_callback_distinguishes_later_loss_after_immediate_66(h):
    def lose_after_native():
        if h.calls:
            info = h.path.stat()
            h.flags[info.st_dev, info.st_ino] = 64
    h.boundary_hook = lose_after_native
    observed = h.observer()
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"):
        with observed:
            with h.prepare():
                pytest.fail("later loss admitted")
    value = observed.report()["diagnostic"]
    assert value["observer_complete"] is True
    assert value["immediate_after_native"]["fd_flags"] == 66
    assert value["after_callbacks"][-1]["fd_flags"] == 64
    assert value["classification"] == "required_flags_observed_then_lost"
    assert value["first_controlled_refusal"]["phase"] == "immutable_guard_callback"
    assert sys.gettrace() is None and len(h.calls) == 1


def test_first_exact_proof_refusal_survives_a_different_cleanup_refusal(h, monkeypatch):
    original_close = immutable.creator.NewMetadataCustody._close
    def cleanup(cap, *, validate):
        original_close(cap, validate=validate)
        if not validate:
            immutable.creator.require(False, "new_metadata_sealed_required")
    monkeypatch.setattr(immutable.creator.NewMetadataCustody, "_close", cleanup)
    observed = h.observer(proof_binding=(proof.require, proof.ImmutableProofRefusal, proof._CODES))
    with pytest.raises((proof.ImmutableProofRefusal, immutable.creator.NewMetadataRefusal)):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
                proof.require(False, "immutable_proof_challenge_not_denied")
    value = observed.report()["diagnostic"]
    assert value["observer_complete"] is True
    assert value["first_controlled_refusal"] == {"role": "proof", "phase": "proof_require",
        "contract_code": "immutable_proof_challenge_not_denied"}
    assert value["controlled_refusals"][0]["role"] == "proof"
    assert any(row["role"] == "creator" for row in value["controlled_refusals"][1:])
    assert len(value["controlled_refusals"]) <= transition.MAXIMUM_REFUSALS
    assert sys.gettrace() is None


def test_trace_loss_vetoes_otherwise_closed_original_capability(h):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_lost"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
                sys.settrace(None)
    assert cap.closed_summary()["phase"] == "CLOSED"
    value = observed.report()["diagnostic"]
    assert value["observer_complete"] is False and value["observer_failure"] == "transition_observer_lost"
    assert sys.gettrace() is None


def test_missing_original_native_call_never_qualifies_as_complete_observer(h):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="missing_native_observation"):
        with observed:
            pass
    assert observed.report()["diagnostic"]["observer_complete"] is False
    assert not h.calls and not h.path.exists() and sys.gettrace() is None


def test_original_native_replacement_is_refused_before_installing_trace_or_creation(h, monkeypatch):
    observed = h.observer()
    monkeypatch.setattr(immutable, "_native_set", lambda *args, **kwargs: None)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="original_code_changed"):
        with observed:
            pytest.fail("replacement entered")
    assert not h.path.exists() and not h.calls and sys.gettrace() is None


def test_second_native_call_is_blocked_before_its_body_even_if_same_flags(h):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="multiple_native_calls"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
                immutable._native_set(cap._anchor[3], initial_flags=64)
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_multiple_native_calls"
    assert value["native_call_count"] == 2 and len(h.calls) == 1 and sys.gettrace() is None


def test_observer_internal_failure_is_fixed_and_does_not_emit_arbitrary_exception_text(h, monkeypatch):
    observed = h.observer()
    def invalid(*args):
        raise RuntimeError("SECRET path/account/exception text")
    monkeypatch.setattr(transition.ImmutableTransitionDiagnostic, "_sample", invalid)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_error"):
        with observed:
            with h.prepare():
                pytest.fail("broken observer yielded")
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_observer_error"
    assert "SECRET" not in canonical_json(value) and len(h.calls) == 0 and sys.gettrace() is None


def test_event_overflow_vetoes_result_and_restores_trace(h, monkeypatch):
    observed = h.observer()
    monkeypatch.setattr(transition, "MAXIMUM_EVENTS", 1)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_overflow"):
        with observed:
            with h.prepare():
                pytest.fail("overflow observer yielded")
    assert observed.report()["diagnostic"]["observer_complete"] is False and sys.gettrace() is None


def test_refusal_overflow_is_bounded_and_preserves_first_fixed_error(h, monkeypatch):
    observed = h.observer()
    monkeypatch.setattr(transition, "MAXIMUM_REFUSALS", 1)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_overflow"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
                try:
                    immutable.require(False, "immutable_read_bound_refused")
                except immutable.ImmutableMetadataRefusal:
                    pass
                immutable.creator.require(False, "new_metadata_read_bound_refused")
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_observer_overflow"
    assert len(value["controlled_refusals"]) == 1
    assert value["first_controlled_refusal"]["contract_code"] == "immutable_read_bound_refused"
    assert sys.gettrace() is None


def test_occupied_original_trace_is_never_replaced(h):
    observed = h.observer()
    def occupied(*args):
        return occupied
    sys.settrace(occupied)
    try:
        with pytest.raises(transition.TransitionDiagnosticRefusal, match="trace_occupied"):
            observed.__enter__()
        assert sys.gettrace() is occupied
    finally:
        sys.settrace(None)
    assert not h.path.exists()


@pytest.mark.parametrize("name", ["other", "../one-safe-nonclaim.private.json", "", None])
def test_only_fixed_new_name_is_accepted(h, name):
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="arguments_refused"):
        transition.observe_original_transition(directory_fd=h.owned._anchor[2], name=name)
    assert sys.gettrace() is None and not h.path.exists()


def test_existing_file_is_not_adopted_or_changed_by_observer(h):
    h.path.write_bytes(h.raw)
    before = h.path.stat()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="arguments_refused"):
        h.observer()
    assert h.path.read_bytes() == h.raw and h.path.stat() == before and not h.calls


def test_refused_and_terminal_reports_have_no_source_or_closed_proof_authority(h):
    observed = h.observer()
    with observed:
        with h.prepare() as cap:
            cap.seal_once()
    value = observed.report()["diagnostic"]
    assert value["authority"] == transition.authority()
    assert value["authority"]["source_admitted"] is value["authority"]["ready_for_backtest"] is False
    assert "closed_offline_new_inode_only" not in canonical_json(value)
    assert value["policy_sha256"] == hash_payload(transition.policy())
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="already_entered"):
        observed.__enter__()


def test_failure_projector_only_exposes_its_own_fixed_literal_catalogue():
    error = transition.TransitionDiagnosticRefusal("REFUSED: transition_observer_lost")
    assert transition.failure_summary(error) == {"category": "local_contract_refusal",
        "contract_code": "transition_observer_lost", "errno_name": None}
    assert transition.failure_summary(RuntimeError("SECRET"))["contract_code"] is None
    assert "SECRET" not in canonical_json(transition.failure_summary(RuntimeError("SECRET")))


def test_caught_observer_fault_cannot_be_reset_to_a_complete_report(h, monkeypatch):
    observed = h.observer()
    original_event = transition.ImmutableTransitionDiagnostic._event
    fired = []
    def fault_after_original_return(value, state):
        if state["immediate_after_native"] is not None and not fired:
            fired.append(True)
            raise transition.TransitionDiagnosticRefusal("REFUSED: transition_observer_overflow")
        return original_event(value, state)
    monkeypatch.setattr(transition.ImmutableTransitionDiagnostic, "_event", fault_after_original_return)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_overflow"):
        with observed:
            try:
                with h.prepare():
                    pytest.fail("faulty observer yielded")
            except transition.TransitionDiagnosticRefusal:
                state = observed._state()
                state["observer_failure"] = None
                sys.settrace(state["tracer"])
    assert fired and len(h.calls) == 1 and sys.gettrace() is None
    assert observed.report()["diagnostic"]["observer_complete"] is False


def test_caller_state_cannot_issue_a_report_before_original_context_exit(h):
    observed = h.observer()
    state = observed._state()
    state["closed"] = True
    state["report_raw"] = canonical_json({"SECRET": "arbitrary caller text", "observer_complete": True})
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="not_closed"):
        observed.report()


def test_real_bounded_unmatched_observer_has_no_audited_numeric_identity_keys(tmp_path):
    # Original factory and unmatched original trace calls only. The child never
    # enters observation or invokes a creator/native/source/proof operation.
    tmp_path.chmod(0o700)
    code = textwrap.dedent("""
        import json, os, sys
        from scripts import short_interest_immutable_transition_diagnostics as transition
        fd = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
        try:
            observed = transition.observe_original_transition(directory_fd=fd, name=transition.NAME)
        finally:
            os.close(fd)
        counts = {"numeric_id": 0, "frame_code": 0, "network": 0}
        def audit(event, args):
            if event == "builtins.id": counts["numeric_id"] += 1
            if event == "object.__getattr__" and len(args) == 2 and args[1] == "f_code":
                counts["frame_code"] += 1
            if event.startswith("socket."):
                counts["network"] += 1
                raise RuntimeError("fixed_network_denied")
        frame = sys._getframe()
        sys.addaudithook(audit)
        for unused in range(1000):
            assert observed._trace(frame, "call", None) is None
        print(json.dumps(counts, sort_keys=True))
    """)
    completed = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False,
        text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert completed.returncode == 0
    import json
    assert json.loads(completed.stdout) == {"numeric_id": 0, "frame_code": 1000, "network": 0}


@pytest.mark.parametrize("attribute", ["__hash__", "__eq__"])
def test_original_object_key_requires_exact_default_hash_and_equality(h, monkeypatch, attribute):
    observed = h.observer()
    called = []
    def hostile(*args):
        called.append(True)
        raise RuntimeError("SECRET hostile object method")
    monkeypatch.setattr(transition.ImmutableTransitionDiagnostic, attribute, hostile)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
        observed._state()
    assert called == []


@pytest.mark.parametrize("attribute", ["__hash__", "__eq__"])
def test_factory_refuses_changed_object_hash_or_equality_before_registration(h, monkeypatch, attribute):
    before = len(transition._MINTED)
    monkeypatch.setattr(transition.ImmutableTransitionDiagnostic, attribute, lambda *args: 0)
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
        h.observer()
    assert len(transition._MINTED) == before and not h.path.exists()


@pytest.mark.parametrize("attribute", ["__hash__", "__eq__", "_identity"])
def test_terminal_identity_tamper_never_hashes_hostile_object_and_restores_trace(h, monkeypatch, attribute):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            if attribute == "_identity":
                observed._identity = object()
            else:
                def hostile(*args):
                    raise AssertionError("hostile identity method was invoked")
                monkeypatch.setattr(transition.ImmutableTransitionDiagnostic, attribute, hostile)
    assert sys.gettrace() is None


def test_caught_identity_fault_is_permanently_latched_after_public_identity_reset(h):
    observed = h.observer()
    identity = observed._identity
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            observed._identity = object()
            try:
                with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
                    observed._state()
            finally:
                observed._identity = identity
            observed._state()["observer_failure"] = None
    assert observed.report()["diagnostic"]["observer_complete"] is False
    assert sys.gettrace() is None


def test_complete_original_report_cannot_survive_caught_post_exit_identity_reset(h):
    observed = h.observer()
    with observed:
        with h.prepare() as cap:
            cap.seal_once()
    identity = observed._identity
    observed._identity = object()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
        observed.report()
    observed._identity = identity
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="not_closed"):
        observed.report()


def test_unregistered_exact_or_unknown_type_cannot_adopt_an_observer_identity(h):
    original = h.observer()
    unregistered = object.__new__(transition.ImmutableTransitionDiagnostic)
    unregistered._identity = original._identity
    class Unknown:
        _identity = original._identity
        def __hash__(self):
            raise AssertionError("unknown object was hashed")
        def __eq__(self, other):
            raise AssertionError("unknown object was compared")
    for value in (unregistered, Unknown()):
        with pytest.raises(transition.TransitionDiagnosticRefusal, match="binding_changed"):
            transition.ImmutableTransitionDiagnostic._state(value)
    assert original._state()["entered"] is False and sys.gettrace() is None


@pytest.mark.parametrize("key", ["observer_failure", "tracer", "native_calls", "after_callbacks"])
def test_original_state_key_deletion_restores_trace_and_never_issues_a_report(h, key):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_error"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            del observed._state()[key]
    assert sys.gettrace() is None
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="not_closed"):
        observed.report()


@pytest.mark.parametrize("failure", ["PRIVATE_SECRET_PATH", 17, False, ["PRIVATE_SECRET_PATH"]])
def test_mutable_failure_value_is_fixed_before_latch_or_original_report(h, failure):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_error"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            observed._state()["observer_failure"] = failure
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_observer_error"
    assert value["observer_complete"] is False and "PRIVATE_SECRET_PATH" not in canonical_json(value)
    assert sys.gettrace() is None


def test_direct_failure_latch_rejects_uncontrolled_text_without_losing_prior_literal(h):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_lost"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            observed._fail("transition_observer_lost")
            observed._fail("PRIVATE_SECRET_PATH")
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_observer_lost"
    assert "PRIVATE_SECRET_PATH" not in canonical_json(value) and sys.gettrace() is None


def test_direct_invalid_failure_latch_issues_only_fixed_error(h):
    observed = h.observer()
    with pytest.raises(transition.TransitionDiagnosticRefusal, match="observer_error"):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
            observed._fail("PRIVATE_SECRET_PATH")
    value = observed.report()["diagnostic"]
    assert value["observer_failure"] == "transition_observer_error"
    assert "PRIVATE_SECRET_PATH" not in canonical_json(value) and sys.gettrace() is None
