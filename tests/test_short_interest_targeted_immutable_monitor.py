"""Original metadata control flow with fake native flags; CPU monitoring only."""
import ctypes
import errno
import json
import os
import socket
import sys
import threading

import pytest

from data.hashing import canonical_json, hash_payload
pytest.importorskip("resource", reason="protected original capture runtime imports POSIX resource")
pytest.importorskip("fcntl", reason="protected original metadata runtime imports POSIX fcntl")
if not hasattr(sys, "monitoring"):
    pytest.skip("targeted backend requires Python monitoring API", allow_module_level=True)
from scripts import short_interest_targeted_immutable_monitor as monitor
from scripts import short_interest_immutable_transition_diagnostics as previous
from scripts import diagnose_short_interest_immutable_metadata as proof
from test_short_interest_immutable_transition_diagnostics import Harness as OriginalHarness


class Harness(OriginalHarness):
    def observer(self, **changes):
        return monitor.observe_original_transition(directory_fd=self.owned._anchor[2], name=monitor.NAME, **changes)


@pytest.fixture(autouse=True)
def controlled_runtime(monkeypatch):
    if sys.monitoring.get_tool(4) is not None or sys.monitoring.get_events(4) != 0:
        pytest.skip("tool4 already occupied; never replace an external monitor")
    assert sys.gettrace() is None
    def denied(*args, **kwargs): raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    try:
        yield
    finally:
        # TEST-ONLY recovery of deliberately corrupted resources in this child
        # process. Production must leave a foreign ownership lease unchanged.
        sys.settrace(None)
        backend = monitor._MONITOR
        if backend.get_tool(4) is None:
            backend.use_tool_id(4, "fixed-test-cleanup")
        backend.set_events(4, 0)
        codes = {code for record in monitor._MINTED.values() for code, unused in record[4][1]}
        for code in codes: backend.set_local_events(4, code, 0)
        for unused, event in monitor._EVENTS: backend.register_callback(4, event, None)
        backend.free_tool_id(4)


@pytest.fixture
def h(tmp_path, monkeypatch):
    value = Harness(tmp_path, monkeypatch)
    try: yield value
    finally: value.close()


def assert_closed(observed):
    value = observed.report()["diagnostic"]
    assert value["schema"] == "si-targeted-immutable-monitoring-diagnostic-v1"
    assert value["backend"] == monitor.BACKEND and value["monitoring_context_closed"] is True
    restoration = value["resource_restoration"]
    assert restoration["tool_id"] == 4 and restoration["scope"] == monitor.SCOPE
    assert restoration["foreign_ownership_preserved"] is False
    assert all(item is True for key, item in restoration.items()
        if key not in {"tool_id", "scope", "foreign_ownership_preserved"})
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0
    assert sys.gettrace() is None and value["authority"] == monitor.authority()
    return value


def test_original_native_and_all_meaningful_samples_survive_targeted_backend(h):
    native = monitor.immutable._native_set
    with h.observer() as observed:
        with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()
        with h.prepare() as cap:
            cap.seal_once(); cap.check(); assert cap.read() == h.raw
    value = assert_closed(observed)
    assert monitor.immutable._native_set is native is monitor._NATIVE
    assert value["observer_complete"] is True and value["native_call_count"] == 1
    assert value["native_result"] == 0 and value["native_errno_name"] is None
    assert value["before_native"]["fd_flags"] == value["before_native"]["name_flags"] == 64
    assert value["immediate_after_native"]["fd_flags"] == value["immediate_after_native"]["name_flags"] == 66
    assert value["after_callbacks"] and value["classification"] == "required_flags_observed_without_recorded_loss"
    assert value["controlled_refusals"] == [] and len(h.calls) == 1
    value["authority"]["source_admitted"] = True
    assert observed.report()["diagnostic"]["authority"]["source_admitted"] is False


@pytest.mark.parametrize("kind", ["no_bit", "later_loss"])
def test_original_unchanged_flag_refusals_have_same_meaningful_classification(h, kind):
    if kind == "no_bit":
        def lose(fd):
            info = os.fstat(fd); h.flags[info.st_dev, info.st_ino] = 64
        h.native_hook = lose
    else:
        def boundary():
            if h.calls:
                info = h.path.stat(); h.flags[info.st_dev, info.st_ino] = 64
        h.boundary_hook = boundary
    observed = h.observer()
    with pytest.raises(monitor.immutable.ImmutableMetadataRefusal, match="flags_changed"):
        with observed:
            with h.prepare(): pytest.fail("bad flags admitted")
    value = assert_closed(observed)
    assert value["observer_complete"] is True and value["native_call_count"] == 1
    expected = "required_flags_absent_at_immediate_observation" if kind == "no_bit" else "required_flags_observed_then_lost"
    assert value["classification"] == expected


def test_exceptional_native_unwind_keeps_minus_one_errno_and_immediate_sample(h, monkeypatch):
    class Failed:
        def __call__(self, fd, flags):
            h.calls.append((fd, flags)); ctypes.set_errno(errno.EPERM); return -1
    operation = Failed()
    monkeypatch.setattr(monitor.immutable.ctypes, "CDLL", lambda *args, **kwargs:
        type("Library", (), {"fchflags": operation})())
    observed = h.observer()
    with pytest.raises(monitor.immutable.ImmutableMetadataRefusal):
        with observed:
            with h.prepare(): pytest.fail("failed native admitted")
    value = assert_closed(observed)
    assert value["observer_complete"] is True and value["native_call_count"] == 1
    assert value["native_result"] == -1 and value["native_errno_name"] == "EPERM"
    assert value["immediate_after_native"]["fd_flags"] == 64
    assert value["classification"] == "required_flags_absent_at_immediate_observation"


def test_exceptional_guarded_boundary_unwind_still_samples_callback_return(h):
    def refuse():
        if h.calls: monitor.immutable.creator.require(False, "new_metadata_read_bound_refused")
    h.boundary_hook = refuse
    observed = h.observer()
    with pytest.raises(monitor.immutable.creator.NewMetadataRefusal, match="read_bound_refused"):
        with observed:
            with h.prepare(): pytest.fail("callback refusal admitted")
    value = assert_closed(observed)
    assert value["observer_complete"] is True and value["immediate_after_native"]["fd_flags"] == 66
    assert value["after_callbacks"] and value["after_callbacks"][-1]["fd_flags"] == 66
    assert value["first_controlled_refusal"]["contract_code"] == "new_metadata_read_bound_refused"


def test_incoming_generator_throw_proof_refusal_precedes_different_cleanup_refusal(h, monkeypatch):
    original_close = monitor.immutable.creator.NewMetadataCustody._close
    def cleanup(cap, *, validate):
        original_close(cap, validate=validate)
        if not validate: monitor.immutable.creator.require(False, "new_metadata_sealed_required")
    monkeypatch.setattr(monitor.immutable.creator.NewMetadataCustody, "_close", cleanup)
    observed = h.observer(proof_binding=(proof.require, proof.ImmutableProofRefusal, proof._CODES))
    with pytest.raises((proof.ImmutableProofRefusal, monitor.immutable.creator.NewMetadataRefusal)):
        with observed:
            with h.prepare() as cap:
                cap.seal_once()
                raise proof.ImmutableProofRefusal("REFUSED: immutable_proof_challenge_not_denied")
    value = assert_closed(observed)
    assert value["observer_complete"] is True
    assert value["first_controlled_refusal"]["role"] == "proof"
    assert value["first_controlled_refusal"]["contract_code"] == "immutable_proof_challenge_not_denied"
    assert any(row["role"] == "creator" for row in value["controlled_refusals"][1:])


def test_unrelated_normal_functions_are_not_globally_traced_or_locally_modified(h):
    def unrelated(): return 1
    before = sys.monitoring.get_local_events(4, unrelated.__code__)
    with h.observer() as observed:
        for unused in range(1000): assert unrelated() == 1
        assert sys.gettrace() is None and sys.monitoring.get_local_events(4, unrelated.__code__) == before
        with h.prepare() as cap: cap.seal_once()
    assert_closed(observed)


def test_busy_foreign_tool_is_never_overwritten(h):
    sys.monitoring.use_tool_id(4, "fixed-foreign-owner")
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="monitor_busy"): observed.__enter__()
    assert sys.monitoring.get_tool(4) == "fixed-foreign-owner" and not h.calls and not h.path.exists()


def test_orphan_callback_refusal_restores_the_exact_original_callback(h):
    def original(*args): return None
    sys.monitoring.use_tool_id(4, "fixed-old-owner")
    sys.monitoring.register_callback(4, sys.monitoring.events.LINE, original)
    sys.monitoring.free_tool_id(4)
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="monitor_busy"): observed.__enter__()
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0
    sys.monitoring.use_tool_id(4, "fixed-inspection")
    assert sys.monitoring.register_callback(4, sys.monitoring.events.LINE, original) is original
    sys.monitoring.free_tool_id(4)
    assert not h.calls and not h.path.exists()


def test_orphan_target_local_mask_is_refused_and_preserved(h):
    code = monitor._NATIVE_CODE
    sys.monitoring.use_tool_id(4, "fixed-old-owner")
    sys.monitoring.set_local_events(4, code, sys.monitoring.events.PY_START)
    sys.monitoring.free_tool_id(4)
    with pytest.raises(monitor.TargetedMonitorRefusal, match="monitor_busy"): h.observer().__enter__()
    assert sys.monitoring.get_tool(4) is None
    assert sys.monitoring.get_local_events(4, code) == sys.monitoring.events.PY_START


def test_partial_local_activation_failure_restores_all_successful_mutations(h, monkeypatch):
    original = monitor._call; calls = []
    def interrupted(name, *args):
        if name == "set_local_events" and args[-1] == monitor._LOCAL_MASK:
            calls.append(True)
            if len(calls) == 3: raise RuntimeError("PRIVATE secret failure")
        return original(name, *args)
    monkeypatch.setattr(monitor, "_call", interrupted)
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="observer_error"): observed.__enter__()
    assert len(calls) == 3 and sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0
    assert all(sys.monitoring.get_local_events(4, code) == 0 for code, unused in monitor._MINTED[observed][4][1])
    assert not h.calls and not h.path.exists()


@pytest.mark.parametrize("kind", ["callback", "global_mask", "local_mask", "code", "thread", "identity"])
def test_late_resource_code_thread_or_identity_tamper_vetoes_observer(h, monkeypatch, kind):
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            if kind == "callback": sys.monitoring.register_callback(4, sys.monitoring.events.LINE, lambda *args: None)
            elif kind == "global_mask": sys.monitoring.set_events(4, 0)
            elif kind == "local_mask": sys.monitoring.set_local_events(4, monitor._NATIVE_CODE, 0)
            elif kind == "code": monkeypatch.setattr(monitor.immutable, "_native_set", lambda *args, **kwargs: None)
            elif kind == "thread": monitor._MINTED[observed][2]["thread"] = -1
            else: observed._identity = object()
    assert sys.monitoring.get_tool(4) == (monitor.TOOL_NAME if kind == "callback" else None)
    assert sys.monitoring.get_events(4) == 0


def test_foreign_ownership_loss_is_preserved_without_claiming_cleanup_or_report(h):
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            sys.monitoring.set_events(4, 0)
            for code, unused in monitor._MINTED[observed][4][1]: sys.monitoring.set_local_events(4, code, 0)
            for unused, event in monitor._EVENTS: sys.monitoring.register_callback(4, event, None)
            sys.monitoring.free_tool_id(4); sys.monitoring.use_tool_id(4, "fixed-foreign-owner")
    assert sys.monitoring.get_tool(4) == "fixed-foreign-owner"
    with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()


@pytest.mark.parametrize("key", ["observer_failure", "before_native", "after_callbacks", "native_calls"])
def test_corrupt_original_mutable_state_refuses_after_resource_cleanup(h, key):
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            del monitor._MINTED[observed][2][key]
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0
    with pytest.raises(monitor.TargetedMonitorRefusal): observed.report()


def test_arbitrary_failure_text_and_forged_closed_state_cannot_issue_success(h):
    observed = h.observer()
    state = monitor._MINTED[observed][2]
    state["closed"] = True; state["report_raw"] = canonical_json({"PRIVATE": "secret"})
    with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()
    state["closed"] = False; state["report_raw"] = None
    with pytest.raises(monitor.TargetedMonitorRefusal, match="observer_error"):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            state["observer_failure"] = "PRIVATE_SECRET_PATH"
    value = assert_closed(observed)
    assert value["observer_complete"] is False and value["observer_failure"] == "targeted_observer_error"
    assert "PRIVATE" not in canonical_json(value)


def test_fixed_failure_projector_and_policy_have_no_source_or_backtest_authority():
    assert monitor.failure_summary(monitor.TargetedMonitorRefusal("REFUSED: targeted_monitor_busy")) == {
        "category": "local_contract_refusal", "contract_code": "targeted_monitor_busy", "errno_name": None}
    assert "PRIVATE" not in json.dumps(monitor.failure_summary(RuntimeError("PRIVATE")))
    value = monitor.policy()
    assert value["global_trace_installed"] is False and value["tool_id"] == 4
    assert value["authority"]["source_admitted"] is value["authority"]["ready_for_backtest"] is False


@pytest.mark.parametrize("kind", ["failed_native", "callback_exception"])
def test_old_and_targeted_backends_have_equal_exceptional_meaningful_observations(tmp_path, monkeypatch, kind):
    def run(cls, directory):
        directory.mkdir(mode=0o700)
        value = cls(directory, monkeypatch)
        if kind == "failed_native":
            class Failed:
                def __call__(self, fd, flags):
                    value.calls.append((fd, flags)); ctypes.set_errno(errno.EPERM); return -1
            operation = Failed()
            monkeypatch.setattr(monitor.immutable.ctypes, "CDLL", lambda *args, **kwargs:
                type("Library", (), {"fchflags": operation})())
        else:
            def refuse():
                if value.calls: monitor.immutable.creator.require(False, "new_metadata_read_bound_refused")
            value.boundary_hook = refuse
        observed = value.observer()
        try:
            with pytest.raises((monitor.immutable.ImmutableMetadataRefusal, monitor.immutable.creator.NewMetadataRefusal)):
                with observed:
                    with value.prepare(): pytest.fail("fabricated failure admitted")
            return observed.report()["diagnostic"]
        finally:
            value.close()
    old, targeted = run(OriginalHarness, tmp_path / "old"), run(Harness, tmp_path / "targeted")
    fields = set(old) - {"schema", "policy_sha256"}
    assert {key: old[key] for key in fields} == {key: targeted[key] for key in fields}


def test_cleanup_failure_leaves_visible_owned_lease_and_never_issues_closure(h, monkeypatch):
    original = monitor._call
    def interrupted(name, *args):
        if name == "set_events" and args[-1] == 0:
            raise RuntimeError("PRIVATE cleanup failure")
        return original(name, *args)
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="cleanup_failed"):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            monkeypatch.setattr(monitor, "_call", interrupted)
    assert sys.monitoring.get_tool(4) == monitor.TOOL_NAME
    assert sys.monitoring.get_events(4) == monitor._GLOBAL_MASK
    with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()


def test_exact_phase_on_another_thread_permanently_refuses_without_native_call(h):
    errors = []
    def worker():
        try: monitor.immutable.require(True, "immutable_flags_changed")
        except monitor.TargetedMonitorRefusal as error: errors.append(monitor.failure_summary(error))
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="wrong_thread"):
        with observed:
            thread = threading.Thread(target=worker); thread.start(); thread.join(timeout=5)
            assert not thread.is_alive()
    value = assert_closed(observed)
    assert value["observer_complete"] is False and value["native_call_count"] == 0
    assert errors == [{"category": "local_contract_refusal", "contract_code": "targeted_wrong_thread", "errno_name": None}]
    assert not h.calls and not h.path.exists()


@pytest.mark.parametrize("attribute", ["__hash__", "__eq__"])
def test_hostile_identity_methods_are_never_called_during_failure_cleanup(h, monkeypatch, attribute):
    observed = h.observer()
    def hostile(*args): raise AssertionError("hostile identity method invoked")
    with pytest.raises(monitor.TargetedMonitorRefusal, match="binding_changed"):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            monkeypatch.setattr(monitor.TargetedImmutableMonitor, attribute, hostile)
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0


def test_caught_counter_reset_cannot_erase_original_nonce_failure(h):
    observed = h.observer()
    state = monitor._MINTED[observed][2]
    with pytest.raises(monitor.TargetedMonitorRefusal, match="binding_changed"):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            original = state["native_calls"]
            state["native_calls"] = 0
            with pytest.raises(monitor.TargetedMonitorRefusal, match="binding_changed"): observed._state()
            state["native_calls"] = original
            state["observer_failure"] = None
    assert assert_closed(observed)["observer_complete"] is False


def test_meaningful_event_cap_still_refuses_and_restores_resources(h, monkeypatch):
    monkeypatch.setattr(monitor, "MAXIMUM_EVENTS", 1)
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="observer_overflow"):
        with observed:
            with h.prepare(): pytest.fail("overflow admitted")
    assert assert_closed(observed)["observer_complete"] is False


def test_same_tool_masks_on_unknown_code_are_preserved_untouched(h):
    def unrelated(): return 1
    sys.monitoring.use_tool_id(4, "fixed-orphan-local")
    sys.monitoring.set_local_events(4, unrelated.__code__, sys.monitoring.events.LINE)
    sys.monitoring.free_tool_id(4)
    try:
        with h.observer() as observed:
            with h.prepare() as cap: cap.seal_once()
        value = assert_closed(observed)
        assert value["resource_restoration"]["scope"] == monitor.SCOPE
        assert sys.monitoring.get_local_events(4, unrelated.__code__) == sys.monitoring.events.LINE
    finally:
        sys.monitoring.use_tool_id(4, "fixed-orphan-cleanup")
        sys.monitoring.set_local_events(4, unrelated.__code__, 0)
        sys.monitoring.free_tool_id(4)


def test_unbound_local_start_callback_is_a_fixed_refusal_not_silently_filtered(h):
    def unrelated(): return 1
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="original_code_changed"):
        with observed:
            sys.monitoring.set_local_events(4, unrelated.__code__, sys.monitoring.events.PY_START)
            try: unrelated()
            finally: sys.monitoring.set_local_events(4, unrelated.__code__, 0)
    assert assert_closed(observed)["observer_complete"] is False


def test_unbound_global_exception_callback_filters_before_state_or_frame_inspection(h, monkeypatch):
    observed = h.observer()
    callback = monitor._MINTED[observed][2]["callbacks"]["RAISE"]
    def unrelated(): return None
    def forbidden(*args, **kwargs): raise AssertionError("unbound callback touched state")
    monkeypatch.setattr(monitor.TargetedImmutableMonitor, "_state", forbidden)
    assert callback(unrelated.__code__, 0, RuntimeError("PRIVATE")) is None


@pytest.mark.parametrize("kind", ["forged_frame", "equal_cloned_code"])
def test_registered_callback_requires_original_code_identity_and_real_origin_frame(h, kind):
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal, match="frame_changed|original_code_changed"):
        with observed:
            code = monitor._NATIVE_CODE if kind == "forged_frame" else monitor._NATIVE_CODE.replace()
            assert code == monitor._NATIVE_CODE
            if kind == "equal_cloned_code": assert code is not monitor._NATIVE_CODE
            monitor._MINTED[observed][2]["callbacks"]["PY_START"](code, 0)
    assert assert_closed(observed)["observer_complete"] is False


def test_changed_api_attribute_refuses_but_original_retained_api_cleans_own_resources(h, monkeypatch):
    observed = h.observer()
    with monkeypatch.context() as changes:
        with pytest.raises(monitor.TargetedMonitorRefusal, match="monitor_changed"):
            with observed:
                with h.prepare() as cap: cap.seal_once()
                changes.setattr(sys.monitoring, "get_events", lambda *args: 0)
    assert assert_closed(observed)["observer_complete"] is False


def test_cpu_only_throw_event_is_observed_before_generator_replaces_it_in_finally(h, monkeypatch):
    seen = []
    def suspended():
        try:
            yield None
        finally:
            monitor.immutable.creator.require(False, "new_metadata_sealed_required")
    original_phases = monitor._phases
    def explicit_toy_catalogue(binding):
        # Fabricated CPU-only target seam; unmodified production has only the
        # exact original immutable/creator/proof code catalogue.
        phases, catalogues = original_phases(binding)
        phases[suspended.__code__] = "fixed_toy_generator"
        return phases, catalogues
    monkeypatch.setattr(monitor, "_phases", explicit_toy_catalogue)
    original_observe = monitor.TargetedImmutableMonitor._observe
    def record_toy_event(self, state, phase, event, code, frame, arguments):
        if code is suspended.__code__ and event in monitor._EXCEPTION_NAMES:
            seen.append(event)
        return original_observe(self, state, phase, event, code, frame, arguments)
    monkeypatch.setattr(monitor.TargetedImmutableMonitor, "_observe", record_toy_event)
    observed = h.observer(proof_binding=(proof.require, proof.ImmutableProofRefusal, proof._CODES))
    with pytest.raises(monitor.immutable.creator.NewMetadataRefusal, match="sealed_required"):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            generator = suspended(); next(generator)
            generator.throw(proof.ImmutableProofRefusal("REFUSED: immutable_proof_challenge_not_denied"))
    value = assert_closed(observed)
    assert value["first_controlled_refusal"] == {"role": "proof", "phase": "fixed_toy_generator",
        "contract_code": "immutable_proof_challenge_not_denied"}
    assert value["controlled_refusals"][1]["role"] == "creator"
    assert seen.count("PY_THROW") == 1 and seen.index("PY_THROW") < seen.index("PY_UNWIND")


def test_non_code_global_argument_is_ignored_and_local_argument_fixed_refuses_without_hashing(h):
    calls = []
    class Unknown:
        def __hash__(self): calls.append("hash"); raise AssertionError("PRIVATE unknown code hash")
        def __eq__(self, other): calls.append("eq"); raise AssertionError("PRIVATE unknown code equality")
    observed = h.observer()
    callbacks = monitor._MINTED[observed][2]["callbacks"]
    assert callbacks["RAISE"](Unknown(), 0, RuntimeError("PRIVATE")) is None
    with pytest.raises(monitor.TargetedMonitorRefusal, match="original_code_changed"):
        callbacks["PY_START"](Unknown(), 0)
    assert calls == [] and sys.monitoring.get_tool(4) is None


def test_same_owner_unexpected_callback_survives_teardown_and_holds_failed_lease(h):
    def replacement(*args): return None
    observed = h.observer()
    with pytest.raises(monitor.TargetedMonitorRefusal):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            sys.monitoring.register_callback(4, sys.monitoring.events.LINE, replacement)
    assert sys.monitoring.get_tool(4) == monitor.TOOL_NAME
    assert sys.monitoring.register_callback(4, sys.monitoring.events.LINE, replacement) is replacement
    assert sys.monitoring.get_events(4) == 0
    with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()


def test_observed_takeover_during_cleanup_stops_all_later_mutations(h, monkeypatch):
    observed = h.observer()
    original = monitor._call
    armed, taken, later_mutations = [], [], []
    mutations = {"set_events", "set_local_events", "register_callback", "free_tool_id"}
    def takeover(name, *args):
        if taken and name in mutations: later_mutations.append(name)
        value = original(name, *args)
        if armed and not taken and name == "get_events":
            original("set_events", 4, 0)
            for code, unused in monitor._MINTED[observed][4][1]: original("set_local_events", 4, code, 0)
            for unused, event in monitor._EVENTS: original("register_callback", 4, event, None)
            original("free_tool_id", 4); original("use_tool_id", 4, "fixed-takeover-owner")
            original("set_events", 4, sys.monitoring.events.LINE)
            taken.append(True)
        return value
    monkeypatch.setattr(monitor, "_call", takeover)
    with pytest.raises(monitor.TargetedMonitorRefusal):
        with observed:
            with h.prepare() as cap: cap.seal_once()
            armed.append(True)
    assert taken and later_mutations == []
    assert sys.monitoring.get_tool(4) == "fixed-takeover-owner"
    assert sys.monitoring.get_events(4) == sys.monitoring.events.LINE
    with pytest.raises(monitor.TargetedMonitorRefusal, match="not_closed"): observed.report()
