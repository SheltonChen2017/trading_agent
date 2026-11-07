"""Genuine NEW body/receipt creator with fabricated kernel flags only."""
import ast
import ctypes
import errno
import inspect
import os
from pathlib import Path
import socket
import sys
import textwrap
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload

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

from scripts import short_interest_body_receipt_custody as custody
from scripts import short_interest_body_receipt_monitor as monitor
from scripts import short_interest_targeted_immutable_monitor as tiny_monitor
from scripts import diagnose_short_interest_body_receipt_custody as body_proof
from test_short_interest_body_receipt_custody_proof import h as proof_h

_GENUINE_PREPARE = custody.prepare_owned_body_receipt
_GENUINE_OBSERVER = monitor.observe_original_transition
_GENUINE_PROOF_BINDING = body_proof.binding
_GENUINE_NATIVE = monitor._NATIVE


class Clock:
    def __init__(self): self.value = 10.0
    def __call__(self): return self.value
    def sleep(self, seconds): self.value += seconds


class Harness:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path / "fabricated-pair"; self.root.mkdir(mode=0o700)
        self.owned = custody._OwnedOutput(self.root, lambda: None)
        self.body = b"B" * (2 * 1024 ** 2)
        self.clock, self.flags, self.calls = Clock(), {}, []
        self.hook, self.native_hook = lambda: None, lambda fd, flags: None
        self.initial = 64
        harness = self
        class Operation:
            def __call__(self, fd, flags):
                harness.calls.append((fd, flags))
                info = os.fstat(fd); harness.flags[info.st_dev, info.st_ino] = flags
                os.fchmod(fd, 0o600)  # Fabricated preseal ctime transition only.
                harness.native_hook(fd, flags)
                ctypes.set_errno(0); return 0
        self.operation = Operation()
        class Library: fchflags = self.operation
        def library(name, *, use_errno):
            assert name == custody.immutable.LIBRARY and use_errno is True
            return Library()
        monkeypatch.setattr(custody.immutable.ctypes, "CDLL", library)
        monkeypatch.setattr(custody.immutable, "_platform", lambda: None)
        monkeypatch.setattr(custody.immutable, "_flags", lambda info:
            self.flags.get((info.st_dev, info.st_ino), self.initial))
        self.binding = custody.freeze_body_receipt_binding(request_sha256="1" * 64,
            attempt_sha256="2" * 64, reservation_sha256="3" * 64, protocol_sha256="4" * 64)
    def boundary(self): self.hook()
    def observer(self):
        return monitor.observe_original_transition(directory_fd=self.owned._anchor[2], binding=self.binding)
    def prepare(self, body=None):
        return custody.prepare_owned_body_receipt(self.owned, self.body if body is None else body,
            binding=self.binding, boundary=self.boundary, monotonic=self.clock, sleep=self.clock.sleep)
    def close(self): self.owned.close()


@pytest.fixture(autouse=True)
def controlled_runtime(monkeypatch):
    if sys.monitoring.get_tool(4) is not None or sys.monitoring.get_events(4) != 0:
        pytest.skip("tool4 already occupied; never replace an external monitor")
    assert sys.gettrace() is None
    def denied(*args, **kwargs): raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    try: yield
    finally:
        # TEST-only repair of deliberately corrupted CPU monitoring resources.
        sys.settrace(None)
        backend = monitor._MONITOR
        if backend.get_tool(4) is None: backend.use_tool_id(4, "fixed-test-cleanup")
        backend.set_events(4, 0)
        for record in monitor._MINTED.values():
            for code, unused in record[4][1]: backend.set_local_events(4, code, 0)
        for unused, event in monitor._EVENTS: backend.register_callback(4, event, None)
        backend.free_tool_id(4)


@pytest.fixture
def h(tmp_path, monkeypatch):
    value = Harness(tmp_path, monkeypatch)
    try: yield value
    finally: value.close()


def closed(observed):
    value = observed.report()["diagnostic"]
    assert value["schema"] == "si-body-receipt-immutable-monitoring-diagnostic-v1"
    assert value["monitoring_context_closed"] is True and value["backend"] == monitor.BACKEND
    restoration = value["resource_restoration"]
    assert restoration["tool_id"] == 4 and restoration["scope"] == monitor.SCOPE
    assert restoration["foreign_ownership_preserved"] is False
    assert all(item is True for key, item in restoration.items() if key not in {
        "tool_id", "scope", "foreign_ownership_preserved"})
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0 and sys.gettrace() is None
    return value


@pytest.mark.parametrize("initial", [0, 64])
def test_maximum_body_and_internal_receipt_have_two_genuine_disjoint_role_observations(h, initial):
    h.initial = initial
    with h.observer() as observed:
        with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="not_closed"): observed.report()
        with h.prepare() as pair:
            assert pair.read_body() == h.body
            receipt = pair.read_receipt(); pair.check()
    value = closed(observed)
    assert value["observer_complete"] is True and value["native_call_count"] == 2
    assert value["distinct_original_inodes"] is True and len(h.calls) == 2
    assert [row["role"] for row in value["files"]] == ["body", "receipt"]
    for row, name, raw in zip(value["files"], (monitor.BODY_NAME, monitor.RECEIPT_NAME), (h.body, receipt)):
        assert row["name"] == name and row["bytes"] == len(raw) and row["raw_sha256"] == hash_bytes(raw)
        assert row["native_call_count"] == 1 and row["native_result"] == 0 and row["native_errno_name"] is None
        assert row["before_native"]["fd_flags"] == initial and row["immediate_after_native"]["fd_flags"] == initial | 2
        assert row["after_callbacks"] and row["classification"] == "required_flags_observed_without_recorded_loss"
    assert value["authority"]["source_admitted"] is value["authority"]["ready_for_backtest"] is False
    assert value["authority"]["source_budget_released"] is False
    assert pair.closed_summary()["status"] == "closed_body_receipt_custody_only"


def test_fake_binding_is_refused_before_files_native_or_monitor_lease(h):
    fake = object.__new__(custody.BodyReceiptBinding)
    fake._parts, fake._identity = h.binding._parts, h.binding._identity
    with pytest.raises(custody.BodyReceiptRefusal, match="binding_changed"):
        monitor.observe_original_transition(directory_fd=h.owned._anchor[2], binding=fake)
    assert not h.calls and not list(h.root.iterdir()) and sys.monitoring.get_tool(4) is None


def test_copied_file_cap_anchor_is_not_a_genuine_creator_token(h, monkeypatch):
    original = monitor.BodyReceiptImmutableMonitor._observe
    replaced = []
    def counterfeit(self, state, phase, event, code, frame, arguments):
        if event == "PY_START" and code is monitor._NATIVE_CODE and not replaced:
            parent = frame.f_back; genuine = parent.f_locals["file_cap"]
            fake = object.__new__(custody.BodyReceiptFileCustody)
            fake._anchor = fake._identity = genuine._anchor
            parent.f_locals["file_cap"] = fake; replaced.append(True)
            try: return original(self, state, phase, event, code, frame, arguments)
            finally: parent.f_locals["file_cap"] = genuine
        return original(self, state, phase, event, code, frame, arguments)
    monkeypatch.setattr(monitor.BodyReceiptImmutableMonitor, "_observe", counterfeit)
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal):
        with observed:
            with h.prepare(): pytest.fail("counterfeit cap admitted")
    assert replaced and not h.calls and sys.monitoring.get_tool(4) is None
    assert closed(observed)["observer_complete"] is False


@pytest.mark.parametrize("role", ["body", "receipt"])
def test_genuine_creator_noop_native_is_observed_as_negative_without_completing_pair(h, role):
    def lose(fd, flags):
        if (len(h.calls) == 1) == (role == "body"):
            info = os.fstat(fd); h.flags[info.st_dev, info.st_ino] = h.initial
    h.native_hook = lose
    observed = h.observer()
    with pytest.raises((custody.BodyReceiptRefusal, monitor.BodyReceiptMonitorRefusal)):
        with observed:
            with h.prepare(): pytest.fail("no-op native admitted")
    value = closed(observed)
    assert value["observer_complete"] is (role == "receipt")
    row = value["files"][0 if role == "body" else 1]
    assert row["native_result"] == 0 and row["immediate_after_native"]["fd_flags"] == h.initial
    assert row["classification"] == "required_flags_absent_at_immediate_observation"


def test_real_native_failure_retains_role_errno_and_unwind_sample(h, monkeypatch):
    class Failed:
        def __call__(self, fd, flags): h.calls.append((fd, flags)); ctypes.set_errno(errno.EPERM); return -1
    operation = Failed()
    monkeypatch.setattr(custody.immutable.ctypes, "CDLL", lambda *args, **kwargs:
        type("Library", (), {"fchflags": operation})())
    observed = h.observer()
    with pytest.raises((custody.immutable.ImmutableMetadataRefusal, monitor.BodyReceiptMonitorRefusal)):
        with observed:
            with h.prepare(): pytest.fail("failed native admitted")
    value = closed(observed)
    assert value["observer_complete"] is False
    assert value["files"][0]["native_result"] == -1 and value["files"][0]["native_errno_name"] == "EPERM"
    assert value["files"][0]["immediate_after_native"]["fd_flags"] == h.initial


def test_per_role_metadata_tamper_and_caught_reset_cannot_produce_positive_report(h):
    observed = h.observer()
    state = monitor._MINTED[observed][2]
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="binding_changed"):
        with observed:
            with h.prepare() as pair: pair.check()
            original = state["files"]["body"]["bytes"]
            state["files"]["body"]["bytes"] = 186
            with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="binding_changed"): observed._state()
            state["files"]["body"]["bytes"] = original; state["observer_failure"] = None
    assert closed(observed)["observer_complete"] is False


def test_one_body_and_receipt_call_required_not_forged_total_two(h):
    observed = h.observer()
    state = monitor._MINTED[observed][2]
    with pytest.raises(monitor.BodyReceiptMonitorRefusal):
        with observed:
            state["native_calls"] = 2
            state["files"]["body"]["native_call_count"] = 1
            state["files"]["receipt"]["native_call_count"] = 1
    with pytest.raises(monitor.BodyReceiptMonitorRefusal): observed.report()
    assert not h.calls and not list(h.root.iterdir()) and sys.monitoring.get_tool(4) is None


def test_forged_preclose_report_and_mutable_failure_text_never_grant_authority(h):
    observed = h.observer(); state = monitor._MINTED[observed][2]
    state["closed"] = True; state["report_raw"] = canonical_json({"PRIVATE": "secret"})
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="not_closed"): observed.report()
    state["closed"] = False; state["report_raw"] = None
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="observer_error"):
        with observed:
            with h.prepare() as pair: pair.check()
            state["observer_failure"] = "PRIVATE_SECRET_PATH"
    value = closed(observed)
    assert value["observer_complete"] is False and "PRIVATE" not in canonical_json(value)


def test_tool_busy_or_orphan_callback_never_overwrites_original(h):
    def orphan(*args): return None
    sys.monitoring.use_tool_id(4, "fixed-old-owner")
    sys.monitoring.register_callback(4, sys.monitoring.events.LINE, orphan); sys.monitoring.free_tool_id(4)
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="monitor_busy"): h.observer().__enter__()
    assert sys.monitoring.get_tool(4) is None
    sys.monitoring.use_tool_id(4, "fixed-inspection")
    assert sys.monitoring.register_callback(4, sys.monitoring.events.LINE, orphan) is orphan
    sys.monitoring.free_tool_id(4)


def test_late_replacement_callback_is_preserved_and_failed_lease_is_held(h):
    def replacement(*args): return None
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal):
        with observed:
            with h.prepare() as pair: pair.check()
            sys.monitoring.register_callback(4, sys.monitoring.events.LINE, replacement)
    assert sys.monitoring.get_tool(4) == monitor.TOOL_NAME
    assert sys.monitoring.register_callback(4, sys.monitoring.events.LINE, replacement) is replacement
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="not_closed"): observed.report()


def test_scoped_resource_cleanup_is_exact_versioned_tiny_backend_ast():
    old = ast.parse(textwrap.dedent(inspect.getsource(tiny_monitor.TargetedImmutableMonitor._cleanup)))
    new = ast.parse(textwrap.dedent(inspect.getsource(monitor.BodyReceiptImmutableMonitor._cleanup)))
    class Normalize(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == "BodyReceiptImmutableMonitor": node.id = "TargetedImmutableMonitor"
            return node
        def visit_Constant(self, node):
            if type(node.value) is str: node.value = node.value.replace("body_monitor_", "targeted_")
            return node
    assert ast.dump(Normalize().visit(new), include_attributes=False) == ast.dump(old, include_attributes=False)


def test_receipt_cannot_reuse_the_body_observed_inode(h, monkeypatch):
    original = monitor.BodyReceiptImmutableMonitor._sample
    def alias(self, state, file):
        result = original(self, state, file)
        if file["name"] == monitor.RECEIPT_NAME and file["immediate_after_native"] is None:
            file["original"] = state["files"]["body"]["original"]
        return result
    monkeypatch.setattr(monitor.BodyReceiptImmutableMonitor, "_sample", alias)
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="original_factory_changed"):
        with observed:
            with h.prepare(): pytest.fail("same observed inode admitted")
    # The attempted alias also corrupts the original-tuple pointer. Preserve
    # that refusal rather than reconstructing a report from corrupted state.
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="binding_changed"):
        observed.report()
    assert sys.monitoring.get_tool(4) is None and sys.monitoring.get_events(4) == 0
    assert len(h.calls) == 1


def test_third_native_call_is_refused_before_the_unchanged_setter_body(h):
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="multiple_native_calls"):
        with observed:
            with h.prepare() as pair:
                cap = pair._anchor[3][0]
                custody.immutable._native_set(cap._anchor[7], initial_flags=h.initial)
    assert len(h.calls) == 2 and closed(observed)["observer_complete"] is False


def test_unknown_callback_code_never_runs_caller_hash_or_equality(h):
    calls = []
    class Unknown:
        def __hash__(self): calls.append("hash"); raise AssertionError("PRIVATE")
        def __eq__(self, other): calls.append("eq"); raise AssertionError("PRIVATE")
    observed = h.observer(); callbacks = monitor._MINTED[observed][2]["callbacks"]
    assert callbacks["RAISE"](Unknown(), 0, RuntimeError("PRIVATE")) is None
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="original_code_changed"):
        callbacks["PY_START"](Unknown(), 0)
    assert calls == [] and not h.calls and not list(h.root.iterdir())


def test_first_sample_wrong_inode_never_becomes_a_new_original(h, monkeypatch):
    original_sample = monitor.BodyReceiptImmutableMonitor._sample
    real_fstat, real_stat = os.fstat, os.stat
    fired, observations = [], []
    def changed(info):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        values["st_ino"] += 123456
        return SimpleNamespace(**values)
    def wrong_first(self, state, file):
        if not fired:
            fired.append(True)
            with monkeypatch.context() as changes:
                changes.setattr(monitor.os, "fstat", lambda fd: changed(real_fstat(fd)))
                changes.setattr(monitor.os, "stat", lambda *args, **kwargs: changed(real_stat(*args, **kwargs)))
                result = original_sample(self, state, file)
            observations.append(result)
            return result
        return original_sample(self, state, file)
    monkeypatch.setattr(monitor.BodyReceiptImmutableMonitor, "_sample", wrong_first)
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="before_native_changed"):
        with observed:
            with h.prepare(): pytest.fail("known wrong original inode admitted")
    assert fired and observations[0]["same_original_inode"] is False
    state = monitor._MINTED[observed][2]
    assert state["files"]["body"]["original"] is state["files"]["body"]["origin"][8]
    assert not h.calls and closed(observed)["observer_complete"] is False


def test_new_creator_negative_projector_preserves_only_exact_fixed_code():
    value = monitor.failure_summary(custody.BodyReceiptRefusal("REFUSED: body_receipt_flags_changed"))
    assert value == {"category": "local_contract_refusal", "contract_code": "body_receipt_flags_changed", "errno_name": None}
    assert "PRIVATE" not in canonical_json(monitor.failure_summary(custody.BodyReceiptRefusal("PRIVATE")))


def test_observed_flag_drift_at_native_entry_refuses_before_unchanged_setter_body(h, monkeypatch):
    original_sample = monitor.BodyReceiptImmutableMonitor._sample
    fired = []
    def changed(self, state, file):
        if not fired:
            fired.append(True)
            info = os.fstat(file["fd"])
            h.flags[info.st_dev, info.st_ino] = h.initial | 2
        return original_sample(self, state, file)
    monkeypatch.setattr(monitor.BodyReceiptImmutableMonitor, "_sample", changed)
    observed = h.observer()
    with pytest.raises(monitor.BodyReceiptMonitorRefusal, match="before_native_changed"):
        with observed:
            with h.prepare(): pytest.fail("known changed original flags admitted")
    assert fired and h.calls == []
    value = closed(observed)
    assert value["observer_complete"] is False and value["files"][0]["before_native"]["fd_flags"] == h.initial | 2


def test_genuine_full_driver_pair_monitor_composition_keeps_original_hold_and_polling(proof_h, monkeypatch):
    # The existing proof fixture supplies ONLY fabricated volume/Git/challenge
    # seams here. Restore the genuine new creator/monitor/binding/native Python
    # functions before running the complete driver control flow.
    monkeypatch.setattr(custody, "prepare_owned_body_receipt", _GENUINE_PREPARE)
    monkeypatch.setattr(monitor, "observe_original_transition", _GENUINE_OBSERVER)
    monkeypatch.setattr(body_proof, "binding", _GENUINE_PROOF_BINDING)
    monkeypatch.setattr(custody.immutable, "_native_set", _GENUINE_NATIVE)
    flags, calls, sleeps = {}, [], []
    native_code = _GENUINE_NATIVE.__code__
    creator_code = _GENUINE_PREPARE.__wrapped__.__code__
    def read_flags(info): return flags.get((info.st_dev, info.st_ino), 0)
    class Operation:
        def __call__(self, fd, target):
            info = os.fstat(fd)
            assert target == read_flags(info) | 2
            calls.append((fd, target)); flags[info.st_dev, info.st_ino] = target
            os.fchmod(fd, 0o600)  # Fake kernel transition; no real flags.
            ctypes.set_errno(0); return 0
    operation = Operation()
    class Library: fchflags = operation
    monkeypatch.setattr(custody.immutable, "_flags", read_flags)
    monkeypatch.setattr(custody.immutable, "_platform", lambda: None)  # Explicit platform fixture only.
    monkeypatch.setattr(custody.immutable.ctypes, "CDLL", lambda *args, **kwargs: Library())
    def clock(): return proof_h.tick
    def sleep(seconds):
        assert seconds == .25
        sleeps.append(seconds); proof_h.tick += seconds
    monkeypatch.setattr(body_proof.time, "monotonic", clock)
    monkeypatch.setattr(body_proof.time, "sleep", sleep)
    defaults = dict(_GENUINE_PREPARE.__wrapped__.__kwdefaults__)
    monkeypatch.setattr(_GENUINE_PREPARE.__wrapped__, "__kwdefaults__", {
        **defaults, "monotonic": clock, "sleep": sleep})
    monkeypatch.setattr(body_proof, "PROTOCOL_SHA256", hash_payload(body_proof.protocol()))
    try:
        result = proof_h.run()
    except BaseException as error:
        observed = body_proof._LAST_TRANSITION
        record = monitor._MINTED.get(observed)
        events, natives = monitor._COUNTS[record[1]] if record is not None else (-1, -1)
        code = monitor.failure_summary(error)["contract_code"] or "unknown_fixed_failure"
        pytest.fail("genuine_driver_composition_refused code=" + code
            + " meaningful_events=" + str(events) + " native_calls=" + str(natives), pytrace=False)
    assert _GENUINE_NATIVE.__code__ is native_code and _GENUINE_PREPARE.__wrapped__.__code__ is creator_code
    assert result["status"] == "closed_offline_synthetic_maximum_body_receipt_only"
    assert result["files"][0]["bytes"] == 2 * 1024 ** 2 and result["files"][0]["raw_sha256"] == body_proof.BODY_SHA256
    assert len(calls) == 2 and sleeps == [.25] * 28  # Eight sealing samples + full twenty hold polls.
    assert proof_h.tick == 107.0 and proof_h.volume.phase == "CLOSED"
    pair, observed = body_proof._CLOSED_RECORD[2], body_proof._CLOSED_RECORD[4]
    assert type(pair) is custody.BodyReceiptCustody and type(observed) is monitor.BodyReceiptImmutableMonitor
    value = closed(observed)
    assert value["observer_complete"] is True and value["native_call_count"] == 2
    assert value["distinct_original_inodes"] is True
    counters = monitor._COUNTS[monitor._MINTED[observed][1]]
    assert 0 < counters[0] <= monitor.MAXIMUM_EVENTS and counters[1] == 2
    assert pair.closed_summary()["status"] == "closed_body_receipt_custody_only"
    assert body_proof.validate_closed_result(result) is True
    assert result["authority"]["source_admitted"] is result["authority"]["budget_settlement_authority"] is False
