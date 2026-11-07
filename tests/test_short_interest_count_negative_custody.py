"""Explicit fake LIVE issuers/native filesystem; genuine private-file kernels.

Never creates an image, calls a source/key/provider or uses real kernel flags.
No fake observation in this module is actual wire/capture evidence.
"""
import _thread
import errno
import json
import os
from pathlib import Path
import socket
import stat
from types import SimpleNamespace

import pytest
pytest.importorskip("resource")
fcntl = pytest.importorskip("fcntl")

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_negative_custody as negative
from scripts import capture_short_interest_durable_counts as coordinator
import test_short_interest_count_durable_budget as budget_support
from test_short_interest_body_receipt_custody import kernel
from test_short_interest_new_metadata_custody import Clock


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("_LEASES", "_STATES", "_STATE_PINS", "_ROOTS", "_STORED", "_HOLDS",
            "_SOURCES", "_SOURCE_PINS", "_FINAL_ISSUED", "_FINAL_PINS", "_FINAL_MINTS", "_AUTHORITY_PINS"):
        monkeypatch.setattr(negative, name, {})
    for name in ("_USED_OPERATIONS", "_ATTEMPTED", "_CORRUPT", "_BLOCKED", "_FINAL_ATTEMPTED"):
        monkeypatch.setattr(negative, name, set())
    for name, value in (("_BUDGETS", {}), ("_TICKETS", {}), ("_LOCKS", {}), ("_FAILED", set()), ("_CONSUMED", set())):
        monkeypatch.setattr(negative.accounting, name, value)
    for name in ("_OPERATIONS", "_DRAINED", "_OBSERVATIONS", "_DRAIN_ORIGINS", "_DOWNGRADES"):
        monkeypatch.setattr(negative.transport, name, {})
    monkeypatch.setattr(negative.transport, "_FAILED", set())
    monkeypatch.setattr(coordinator, "_DIRECTORIES", {})
    def denied(*args, **kwargs): raise AssertionError("real network/kernel/source forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(negative.immutable.ctypes, "CDLL", denied)


@pytest.fixture
def h(monkeypatch, tmp_path, request):
    if getattr(request, "param", None) == "negative8":
        unused, unused2, plan = budget_support.support.genuine_exposure_plan(monkeypatch)
        monkeypatch.setattr(negative.accounting, "_EXPECTED_SOURCE_PROFILE", negative.accounting._source_profile())
    else: plan = budget_support.genuine_plan(monkeypatch)
    budget = negative.accounting.open_durable_count_budget(plan)
    mount = tmp_path / "original-mount"; mount.mkdir(mode=0o700)
    fd = os.open(mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd); root_pin = info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)
    root_identity = info.st_dev, info.st_ino, info.st_uid, info.st_gid
    native = {"fsid": (123, 456), "owner": os.getuid(), "flags": 0x101000, "flags_ext": 0,
        "type": 24, "subtype": 0, "fstype": "apfs", "mounted_on": str(mount), "mounted_from": "/dev/disk77"}
    device_pin = 1, 2, info.st_dev, stat.S_IFBLK | 0o600, os.getuid(), os.getgid()
    op = object.__new__(negative.transport.CountCaptureOperation)
    op_anchor = op, budget, plan, budget.budget_identity, 1, "a" * 64, "b" * 64, tmp_path, "c" * 40, "d" * 40, plan.sha256, _thread.RLock(), object(), object()
    op._anchor = op._identity = op_anchor
    negative.transport._OPERATIONS[op] = op_anchor, ("LIVE", (), (), (), None, None)
    volume = object.__new__(negative.storage.CountResponseVolume)
    volume._anchor = volume._identity = (object(),)
    origin = volume, op, mount, fd, root_pin, root_identity, negative.storage._mount_identity(native), device_pin, volume._anchor, object()
    active_calls, accessor_calls, failed, wire_block = [], [], [False], [None]
    def active(value):
        active_calls.append(value)
        assert not failed[0], "normal source/operation guard used after failure"
        assert value is op
        return op_anchor
    def accessor(supplied, operation):
        accessor_calls.append(supplied)
        assert not failed[0], "normal LIVE volume accessor used after failure"
        assert supplied is volume and operation is op
        return origin
    def native_read(supplied_fd):
        assert os.fstat(supplied_fd).st_ino == info.st_ino
        return dict(native)
    def node(device, mount_device):
        assert device == "/dev/disk77" and mount_device == info.st_dev
        return device_pin
    monkeypatch.setattr(negative.transport, "active_operation_binding", active)
    monkeypatch.setattr(negative.storage, "preservation_volume_origin", accessor)
    monkeypatch.setattr(negative.storage, "_native_statfs", native_read)
    monkeypatch.setattr(negative.storage, "_node_pin", node)
    monkeypatch.setattr(negative.transport, "unqualified_preservation_blocker", lambda obs: wire_block[0], raising=False)
    monkeypatch.setattr(negative, "PRESERVATION_POLICY_SHA256", hash_payload(negative.policy()))
    clock = Clock()
    def lease(): return negative._prepare_original_preservation_lease(op, volume, monotonic=clock, sleep=clock.sleep)
    def emit(raw=b"SYNTHETIC_PRIVATE_PREFIX", *, position=5, qualified=False, status=200):
        ticket = budget.reserve_start_slot(position)
        ticket_origin = negative.accounting.ticket_binding(ticket)
        cls = negative.transport.HttpObservation if qualified else negative.transport.UnqualifiedHttpObservation
        obs = object.__new__(cls)
        observed = obs, op, ticket, object(), object(), ticket_origin[8], "e" * 64, op_anchor[5], True, status, raw, "application/json", "2026-10-27T12:00:00Z", None, "f" * 64, object()
        obs._anchor = obs._identity = observed
        (negative.transport._OBSERVATIONS if qualified else negative.transport._DRAINED)[obs] = observed
        state = negative.transport._OPERATIONS[op][1]
        negative.transport._OPERATIONS[op] = op_anchor, (state[0], (*state[1], ticket), (), (*state[3], obs), None, None)
        return obs
    def fail(): failed[0] = True; negative.transport._FAILED.add(op)
    value = SimpleNamespace(op=op, anchor=op_anchor, budget=budget, volume=volume, origin=origin, mount=mount,
        original_fd=fd, lease=lease, emit=emit, fail=fail, failed=failed, clock=clock,
        native=native, active_calls=active_calls, accessor_calls=accessor_calls, wire_block=wire_block)
    real_close = os.close
    try: yield value
    finally:
        # Test-only lifetime release. Production deliberately exposes no close.
        descriptors = {fd, *(row[5] for row in negative._LEASES.values()),
            *(row[0] for row in negative._ROOTS.values())}
        for descriptor in descriptors:
            try: real_close(descriptor)
            except OSError: pass


def test_frozen_policy_has_false_authority_and_rejects_missing_registration(monkeypatch):
    value = negative.policy()
    assert value["maximum_attempts"] == 528 and value["maximum_body_bytes"] == 2097152
    assert value["maximum_metadata_bytes"] == 1024 and value["maximum_leases"] == 133
    assert negative.PRESERVATION_POLICY_SHA256 == hash_payload(value)
    negative._registered()
    monkeypatch.setattr(negative, "PRESERVATION_POLICY_SHA256", "PENDING")
    with pytest.raises(negative.NegativePreservationRefusal, match="registration_pending"): negative._registered()
    for name in ("HTTP_authority", "retry_authority", "budget_release_authority", "source_admitted", "ready_for_backtest"):
        assert value["authority"][name] is False


def test_live_lease_duplicates_original_mount_before_claim_and_survives_original_teardown(h, kernel):
    lease = h.lease(); owned_fd = lease._anchor[5]
    assert owned_fd != h.original_fd and os.fstat(owned_fd).st_ino == h.origin[4][1]
    assert fcntl.fcntl(owned_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
    assert len(h.accessor_calls) == 2 and not hasattr(lease, "close")
    obs = h.emit(); state = h.budget._state
    os.close(h.original_fd); h.original_fd = -1
    h.fail(); calls = len(h.active_calls), len(h.accessor_calls)
    report = negative.preserve_failed_observation(lease, obs)
    assert report["status"] == "negative_quarantine_incomplete_process_must_remain_alive" and report["requires_process_hold"]
    assert not report["final_negative_manifest_issued"]
    assert report["verified_durable_negative_attempts"] == 1 and report["original_mount_FD_retained"]
    assert (len(h.active_calls), len(h.accessor_calls)) == calls and h.budget._state is state
    files = sorted((h.mount / "quarantine" / "000001" / "pair").iterdir())
    assert len(files) == 2 and any(path.read_bytes() == b"SYNTHETIC_PRIVATE_PREFIX" for path in files)
    assert len(kernel.calls) == 2


def test_maximum_body_full_postclose_audit_does_not_use_old_1024_reader(h, kernel):
    lease = h.lease(); raw = b"S" * 2097152; obs = h.emit(raw); h.fail()
    report = negative.preserve_failed_observation(lease, obs)
    assert report["verified_durable_negative_attempts"] == 1 and report["requires_process_hold"]
    assert (h.mount / "quarantine/000001/pair" / negative.primitive.BODY_NAME).read_bytes() == raw
    assert negative.preservation_binding(lease)["requires_process_hold"]
    assert negative.creator.MAXIMUM_BYTES == 1024


def test_all_dispatched_tickets_must_persist_before_process_hold_can_end(h, kernel):
    lease = h.lease(); first = h.emit(); second = h.emit(position=6); h.fail()
    report = negative.preserve_failed_observation(lease, first)
    assert report["requires_process_hold"] and report["pending_already_started_attempts"] == 1
    assert report["verified_durable_negative_attempts"] == 1 and not report["blockers"]
    report = negative.preserve_failed_observation(lease, second)
    assert report["requires_process_hold"] and report["pending_already_started_attempts"] == 0
    assert not report["final_negative_manifest_issued"]
    assert report["verified_durable_negative_attempts"] == 2 and len(kernel.calls) == 4


def test_dispatch_drain_gap_before_observation_append_still_requires_live_process(h, kernel):
    lease = h.lease(); ticket = h.budget.reserve_start_slot(5)
    state = negative.transport._OPERATIONS[h.op][1]
    negative.transport._OPERATIONS[h.op] = h.anchor, (state[0], (ticket,), (), (), None, None)
    h.fail(); report = negative.preservation_binding(lease)
    assert report["requires_process_hold"] and report["pending_already_started_attempts"] == 1
    assert not kernel.calls and report["original_mount_FD_retained"]


@pytest.mark.parametrize("raw", [None, b""])
def test_no_body_has_only_small_metadata_full_page_unreleased_and_no_empty_pair(h, kernel, raw):
    lease = h.lease(); obs = h.emit(raw, status=None); before = h.budget._state; h.fail()
    report = negative.preserve_failed_observation(lease, obs)
    assert report["requires_process_hold"] and h.budget._state is before and not negative.accounting._CONSUMED
    files = tuple((h.mount / "quarantine/000001/metadata").iterdir())
    assert len(files) == 1 and 0 < files[0].stat().st_size <= 1024
    assert not (h.mount / "quarantine/000001/pair").exists() and len(kernel.calls) == 1


def test_failed_budget_and_source_guards_are_not_reset_or_reentered(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail(); negative.accounting._FAILED.add(h.budget)
    report = negative.preserve_failed_observation(lease, obs)
    assert report["requires_process_hold"] and h.op in negative.transport._FAILED
    assert h.budget in negative.accounting._FAILED and not negative.accounting._CONSUMED


def test_prior_qualified_result_must_be_original_downgrade_not_a_cast(h, kernel):
    lease = h.lease(); original = h.emit(qualified=True); h.fail()
    downgraded = negative.transport.downgrade_http_observation_for_preservation(original)
    result = negative.preserve_failed_observation(lease, downgraded)
    assert result["requires_process_hold"] and negative._HOLDS[lease][0] is downgraded
    assert negative.transport.drained_http_observation_binding(downgraded)[10] is original._anchor[10]


@pytest.mark.parametrize("value", [True, {}, b"secret", "complete"])
def test_caller_payload_bool_bytes_or_status_can_never_publish(h, kernel, value):
    lease = h.lease(); h.fail()
    report = negative.preserve_failed_observation(lease, value)
    assert report["requires_process_hold"] and report["verified_durable_negative_attempts"] == 0
    assert not negative._HOLDS.get(lease) and not kernel.calls and not (h.mount / "quarantine").exists()


def test_reflected_unqualified_observation_without_original_registry_cannot_publish(h, kernel):
    lease = h.lease(); original = h.emit(); h.fail()
    forged = object.__new__(negative.transport.UnqualifiedHttpObservation)
    forged._anchor = forged._identity = original._anchor
    result = negative.preserve_failed_observation(lease, forged)
    assert result["requires_process_hold"] and not negative._HOLDS.get(lease) and not kernel.calls


def test_unknown_native_partial_chain_is_a_blocker_not_lossless_prefix_claim(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail(); h.wire_block[0] = "native_partial_chain_unproven"
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and result["verified_durable_negative_attempts"] == 0
    assert negative._HOLDS[lease] == (obs,) and not kernel.calls
    assert os.fstat(lease._anchor[5]).st_ino == h.origin[4][1]


def test_no_failed_operation_no_negative_activation(h, kernel):
    lease = h.lease(); obs = h.emit()
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and result["blockers"][0]["contract_code"] == "negative_failed_operation_required"
    assert not kernel.calls


def test_each_original_ticket_is_once_only_and_duplicate_hold_is_bounded(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail()
    assert negative.preserve_failed_observation(lease, obs)["verified_durable_negative_attempts"] == 1
    for unused in range(10): result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and result["originally_closed_negative_attempts"] == 1
    assert len(negative._HOLDS[lease]) == 1 and len(negative._STATE_PINS[lease][2]) == 1 and len(kernel.calls) == 2


@pytest.mark.parametrize("change", ["native", "volume_anchor", "fd", "mask"])
def test_changed_native_root_or_runtime_policy_refuses_before_new_inode(h, kernel, monkeypatch, change):
    lease = h.lease(); obs = h.emit(); h.fail()
    if change == "native": h.native["flags"] = 0
    elif change == "volume_anchor": h.volume._anchor = (object(),)
    elif change == "fd": os.close(lease._anchor[5])
    else: monkeypatch.setattr(negative.storage, "MNT_DONTBROWSE", 0)
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and not kernel.calls and not (h.mount / "quarantine").exists()
    assert negative._HOLDS[lease] == (obs,)


def test_own_inmemory_code_change_is_not_adopted_and_keeps_original_FD_raw(h, kernel, monkeypatch):
    lease = h.lease(); obs = h.emit(); h.fail()
    monkeypatch.setattr(negative, "_audit_files", lambda *args: None)
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and not kernel.calls and negative._HOLDS[lease] == (obs,)
    assert result["blockers"][0]["contract_code"] == "negative_original_code_changed"


def test_replacing_code_checker_itself_cannot_skip_original_frozen_check(h, kernel, monkeypatch):
    lease = h.lease(); obs = h.emit(); h.fail()
    monkeypatch.setattr(negative, "_check_code", lambda *args: None)
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and not kernel.calls
    assert result["blockers"][0]["contract_code"] == "negative_original_code_changed"


def test_changed_wire_blocker_is_refused_before_invoking_the_replacement(h, kernel, monkeypatch):
    lease = h.lease(); obs = h.emit(); h.fail(); invoked = []
    def replacement(value): invoked.append(value); return None
    monkeypatch.setattr(negative.transport, "unqualified_preservation_blocker", replacement)
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and not invoked and not kernel.calls
    assert negative._HOLDS[lease] == (obs,)


def test_missing_fixed_wire_blocker_prevents_lease_before_claim_key_or_dup(h, kernel, monkeypatch):
    monkeypatch.setattr(negative.transport, "unqualified_preservation_blocker", None)
    with pytest.raises(negative.NegativePreservationRefusal, match="wire_blocker_pending"): h.lease()
    assert not negative._LEASES and not h.accessor_calls and not kernel.calls


def test_equal_reconstructed_volume_origin_is_not_an_original_live_issuer(h, kernel, monkeypatch):
    monkeypatch.setattr(negative.storage, "preservation_volume_origin", lambda volume, op: tuple(list(h.origin)))
    with pytest.raises(negative.NegativePreservationRefusal, match="original_volume_changed"): h.lease()
    assert not kernel.calls
    for anchor in negative._LEASES.values():
        with pytest.raises(OSError): os.fstat(anchor[5])


def test_oversized_opaque_prefix_is_retained_without_truncating_or_extra_namespace(h, kernel):
    lease = h.lease(); raw = b"x" * (2097152 + 1); obs = h.emit(raw); h.fail()
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and negative._HOLDS[lease][0]._anchor[10] is raw
    assert not kernel.calls and not (h.mount / "quarantine").exists()


def test_caller_state_reset_cannot_clear_blocker_or_original_observation(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail(); h.wire_block[0] = "native_partial_chain_unproven"
    negative.preserve_failed_observation(lease, obs)
    negative._STATES[lease] = (), (), ()
    h.wire_block[0] = None
    report = negative.preservation_binding(lease)
    assert report["requires_process_hold"] and negative._HOLDS[lease] == (obs,)
    assert not kernel.calls and os.fstat(lease._anchor[5]).st_ino == h.origin[4][1]


def test_existing_quarantine_or_failed_inode_is_never_adopted_or_retried(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail()
    directory = h.mount / "quarantine"; directory.mkdir(mode=0o700)
    (directory / "preserve-me").write_bytes(b"OLD_UNQUALIFIED")
    report = negative.preserve_failed_observation(lease, obs)
    assert report["requires_process_hold"] and (directory / "preserve-me").read_bytes() == b"OLD_UNQUALIFIED"
    assert not kernel.calls and len(negative._ATTEMPTED) == 1


def test_substituted_quarantine_FD_cannot_create_an_inode_outside_original_volume(h, kernel):
    lease = h.lease(); first, second = h.emit(), h.emit(position=6); h.fail()
    negative.preserve_failed_observation(lease, first)
    foreign = h.mount.parent / "foreign-directory"; foreign.mkdir(mode=0o700)
    foreign_fd = os.open(foreign, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.dup2(foreign_fd, negative._ROOTS[lease][0])
    finally: os.close(foreign_fd)
    report = negative.preserve_failed_observation(lease, second)
    assert report["requires_process_hold"] and not tuple(foreign.iterdir())
    assert report["original_mount_FD_retained"] and negative._HOLDS[lease] == (first, second)


def test_pre_registration_code_pin_failure_closes_only_unreturned_duplicate(h, kernel, monkeypatch):
    real_dup = os.dup; copies = []
    def duplicate(fd):
        copied = real_dup(fd); copies.append(copied); return copied
    def refused(): raise OSError(errno.EMFILE, "PRIVATE_SECRET")
    monkeypatch.setattr(negative.os, "dup", duplicate)
    monkeypatch.setattr(negative, "_code_pins", refused)
    with pytest.raises(OSError): h.lease()
    assert len(copies) == 1 and not negative._LEASES
    with pytest.raises(OSError): os.fstat(copies[0])
    assert os.fstat(h.original_fd).st_ino == h.origin[4][1]


def test_failed_small_metadata_inode_is_spent_preserved_and_cannot_be_retried(h, kernel, monkeypatch):
    real_sync = os.fsync; fault = [False]
    def sync(fd):
        if fault[0]: raise OSError(errno.EIO, "PRIVATE_SECRET")
        return real_sync(fd)
    monkeypatch.setattr(negative.os, "fsync", sync)
    lease = h.lease(); obs = h.emit(None, status=None); h.fail(); fault[0] = True
    result = negative.preserve_failed_observation(lease, obs)
    path = h.mount / "quarantine/000001/metadata" / negative.RECEIPT_NAME
    original = path.read_bytes()
    assert result["requires_process_hold"] and result["blockers"][0]["errno_name"] == "EIO"
    fault[0] = False
    again = negative.preserve_failed_observation(lease, obs)
    assert again["requires_process_hold"] and path.read_bytes() == original and not kernel.calls


def test_blocked_errno_retains_original_bytes_and_fd_without_a_release_API(h, kernel, monkeypatch):
    # Fault exists before the lease code freeze; only its trigger changes.
    real_write = os.write; fault = [False]
    def write(fd, raw):
        if fault[0]: raise OSError(errno.ENOSPC, "PRIVATE_PATH_SECRET")
        return real_write(fd, raw)
    monkeypatch.setattr(negative.os, "write", write)
    lease = h.lease(); obs = h.emit(); h.fail(); fault[0] = True
    result = negative.preserve_failed_observation(lease, obs)
    assert result["requires_process_hold"] and result["blockers"][0]["errno_name"] == "ENOSPC"
    assert "SECRET" not in str(result) and negative._HOLDS[lease][0]._anchor[10] == b"SYNTHETIC_PRIVATE_PREFIX"
    assert result["original_mount_FD_retained"] and not hasattr(lease, "close")


def test_fixed_blocker_projection_never_formats_hostile_exception_values():
    class Hostile:
        def __str__(self): pytest.fail("secret formatting")
        def __repr__(self): pytest.fail("secret repr")
        def __eq__(self, unused): pytest.fail("secret comparison")
    class Error(Exception):
        def __getattribute__(self, unused): pytest.fail("secret property")
    for error in (Error(), negative.NegativePreservationRefusal(Hostile()), negative.NegativePreservationRefusal("SECRET")):
        assert negative.failure_summary(error)["contract_code"] is None


def source_file(h, relative, raw=b"SYNTHETIC_PARTIAL", *, original_directories=True):
    """Explicit fabricated source partial; never creates a semantic cap."""
    path = h.mount / relative
    for parent in reversed(path.parents):
        if parent == h.mount or h.mount not in parent.parents: continue
        if not parent.exists(): parent.mkdir(mode=0o700)
        if original_directories:
            rows = coordinator._DIRECTORIES.get(h.op, ())
            if not any(item[0] == parent for item in rows):
                coordinator._DIRECTORIES[h.op] = (*rows, (parent, negative._directory(parent.lstat())))
    fd = os.open(path, os.O_WRONLY | os.O_EXCL | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try: os.write(fd, raw); os.fsync(fd)
    finally: os.close(fd)
    return path


def manifest(h):
    return json.loads((h.mount / "quarantine/closure" / negative.primitive.BODY_NAME).read_bytes())


@pytest.mark.parametrize("h", ["negative8"], indirect=True)
def test_negative_manifest_carries_original_permanent_exposure_without_changing_known_B3(h, kernel):
    plan = h.budget.plan; profile = plan.budget_profile(); baseline = plan._parts[1].public_summary()
    lease = h.lease(); h.fail(); before = h.budget._state
    report = negative.finalize_failed_chunk(lease)
    assert report["final_negative_manifest_issued"] and not report["requires_process_hold"]
    result = manifest(h)
    assert result["historical_START_debits"] == baseline["START_debits"]
    assert result["historical_charged_bytes"] == baseline["charged_response_bytes"]
    assert result["permanent_unknown_START_upper_debits"] == 8
    assert result["permanent_unknown_byte_debits"] == 8 * 2097152
    assert result["negative_exposure_sha256"] == plan.negative_exposure().sha256
    assert result["operative_initial_START_upper_bound"] == baseline["START_debits"] + 8
    assert result["operative_cumulative_byte_upper_bound"] == profile["initial_byte_upper_bound"]
    assert result["current_full_page_reservations"] == 0 and h.budget._state is before
    assert result["source_contexts_closed"] is result["process_closed"] is False


@pytest.mark.parametrize("h", ["negative8"], indirect=True)
def test_failed_negative_path_keeps_new_full_pages_and_the_permanent_floor(h, kernel):
    profile = h.budget.plan.budget_profile(); lease = h.lease(); observed = h.emit(); before = h.budget._state
    h.fail(); negative.preserve_failed_observation(lease, observed)
    report = negative.finalize_failed_chunk(lease)
    assert report["final_negative_manifest_issued"] and not report["requires_process_hold"]
    result = manifest(h)
    assert result["current_full_page_reservations"] == 2097152
    assert result["operative_cumulative_byte_upper_bound"] == profile["initial_byte_upper_bound"] + 2097152
    assert result["permanent_unknown_byte_debits"] == 8 * 2097152 and h.budget._state is before


@pytest.mark.parametrize("h", ["negative8"], indirect=True)
def test_original_plan_profile_method_is_pinned_before_failure(h, monkeypatch):
    lease = h.lease(); h.fail()
    monkeypatch.setattr(negative.accounting.research_budget.CountRecoveryPlan, "budget_profile", lambda self: {})
    report = negative.finalize_failed_chunk(lease)
    assert report["requires_process_hold"] and not report["final_negative_manifest_issued"]
    assert report["blockers"][0]["contract_code"] == "negative_original_code_changed"


def original_empty_source_containers(h, monkeypatch):
    """Actual coordinator mkdir/pins with explicit fabricated source guards."""
    base = h.mount / "capture"
    def volume_binding(operation, *, live):
        assert operation is h.op and live is True
    monkeypatch.setattr(negative.transport, "_control_volume_binding", volume_binding)
    monkeypatch.setattr(coordinator, "source_lease_binding", lambda lease: (None,) * 11 + (base,))
    for path in (base, base / "starts", base / "received", base / "responses", h.mount / "claim"):
        coordinator._new_directory(h.op, path)


def test_zero_tickets_with_original_preclaim_containers_closes_only_negative_manifest(h, kernel, monkeypatch):
    original_empty_source_containers(h, monkeypatch)
    pins = coordinator._DIRECTORIES[h.op]
    assert {path.relative_to(h.mount).as_posix() for path, pin in pins} == {
        "capture", "capture/starts", "capture/received", "capture/responses", "claim"}
    assert h.budget.current_tickets() == ()
    lease = h.lease(); before = h.budget._state; h.fail()
    result = negative.finalize_failed_chunk(lease)
    assert result["final_negative_manifest_issued"] and not result["requires_process_hold"]
    assert result["status"] == "preservation_manifest_sealed_only"
    assert h.budget._state is before and coordinator._DIRECTORIES[h.op] is pins
    payload = manifest(h)
    assert payload["all_current_reserved_tickets"] == [] and payload["current_full_page_reservations"] == 0
    assert payload["source_contexts_closed"] is False and payload["process_closed"] is False
    assert all(row["state"] == "ABSENT_NOT_A_START_REFUND" for row in payload["source_members"])
    assert len(kernel.calls) == 2 and not payload["authority"]["budget_release_authority"]
    assert negative.preservation_binding(lease)["final_negative_manifest_issued"]


@pytest.mark.parametrize("extra", ["capture/foreign", "capture/starts/000001", "capture/received/000001", "capture/responses/000001"])
def test_zero_tickets_fixed_containers_do_not_admit_unknown_children(h, kernel, monkeypatch, extra):
    original_empty_source_containers(h, monkeypatch)
    lease = h.lease(); path = h.mount / extra; path.mkdir(mode=0o700)
    h.fail(); report = negative.finalize_failed_chunk(lease)
    assert report["requires_process_hold"] and not report["final_negative_manifest_issued"]
    assert report["blockers"][0]["contract_code"] == "negative_source_catalogue_changed"
    assert not kernel.calls and not (h.mount / "quarantine").exists() and path.is_dir()
    assert report["original_mount_FD_retained"] and h.budget._state[1:3] == ((), ())


@pytest.mark.parametrize("change", ["mode", "inode", "symlink"])
def test_zero_tickets_fixed_containers_retain_original_directory_checks(h, kernel, monkeypatch, change):
    original_empty_source_containers(h, monkeypatch)
    lease = h.lease(); path = h.mount / "capture/starts"
    if change == "mode": path.chmod(0o755)
    else:
        original = h.mount / "original-starts-outside-capture"
        path.rename(original)
        if change == "inode": path.mkdir(mode=0o700)
        else: path.symlink_to(original, target_is_directory=True)
    h.fail(); report = negative.finalize_failed_chunk(lease)
    assert report["requires_process_hold"] and not report["final_negative_manifest_issued"]
    expected = "negative_source_member_changed" if change == "inode" else "negative_owned_directory_changed"
    assert report["blockers"][0]["contract_code"] == expected
    assert not kernel.calls and not (h.mount / "quarantine").exists()
    assert report["original_mount_FD_retained"] and h.budget._state[1:3] == ((), ())


def test_zero_observations_requires_original_global_negative_before_exit(h, kernel):
    lease = h.lease(); h.fail()
    missing = negative.preservation_binding(lease)
    assert missing["requires_process_hold"] and not missing["final_negative_manifest_issued"]
    result = negative.finalize_failed_chunk(lease)
    assert not result["requires_process_hold"] and result["final_negative_manifest_issued"]
    assert result["status"] == "preservation_manifest_sealed_only"
    payload = manifest(h)
    assert payload["source_contexts_closed"] is False and payload["process_closed"] is False
    assert payload["all_current_reserved_tickets"] == [] and payload["current_full_page_reservations"] == 0
    assert payload["historical_START_debits"] == negative.accounting.research_budget.PRIOR_STARTS
    assert payload["historical_charged_bytes"] == negative.accounting.research_budget.PRIOR_CHARGED_BYTES
    assert len(kernel.calls) == 2 and all(value is False for key, value in payload["authority"].items()
        if key.endswith("authority") or key in ("source_admitted", "ready_for_backtest"))
    assert negative.preservation_binding(lease)["final_negative_manifest_issued"]


def test_partial_START_claim_and_undispatched_reservation_remain_unknown_full_debit(h, kernel):
    lease = h.lease(); ticket = h.budget.reserve_start_slot(5); before = h.budget._state
    original = source_file(h, "claim/claim.spent.json")
    started = source_file(h, "capture/starts/000001/START.spent.json", original_directories=False)
    h.fail(); result = negative.finalize_failed_chunk(lease)
    assert result["final_negative_manifest_issued"] and not result["requires_process_hold"]
    assert h.budget._state is before and h.budget._state[2] == (ticket,)
    payload = manifest(h); rows = {row["name"]: row for row in payload["source_members"]}
    for name in ("claim/claim.spent.json", "capture/starts/000001/START.spent.json"):
        assert rows[name]["state"] == "UNKNOWN_UNSEALED_OR_PARTIAL" and "sha256" not in rows[name]
    assert payload["current_full_page_reservations"] == 2097152
    assert payload["all_current_reserved_tickets"][0]["negative_full_page_charge_unchanged"] == 2097152
    assert original.read_bytes() == started.read_bytes() == b"SYNTHETIC_PARTIAL"


def test_every_received_attempt_needs_quarantine_and_final_marker(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail()
    pending = negative.finalize_failed_chunk(lease)
    assert pending["requires_process_hold"] and lease not in negative._FINAL_ATTEMPTED
    assert not pending["blockers"] and not (h.mount / "quarantine").exists()
    preserved = negative.preserve_failed_observation(lease, obs)
    assert preserved["requires_process_hold"] and not preserved["final_negative_manifest_issued"]
    result = negative.finalize_failed_chunk(lease)
    assert result["final_negative_manifest_issued"] and not result["requires_process_hold"]
    assert len(kernel.calls) == 4 and manifest(h)["current_full_page_reservations"] == 2097152


def test_global_final_marker_does_not_spend_namespace_while_inflight(h, kernel):
    lease = h.lease(); h.fail(); state = negative.transport._OPERATIONS[h.op][1]
    negative.transport._OPERATIONS[h.op] = h.anchor, (state[0], (), (object(),), (), None, None)
    result = negative.finalize_failed_chunk(lease)
    assert result["requires_process_hold"] and not result["blockers"]
    assert lease not in negative._FINAL_ATTEMPTED and not kernel.calls


def test_foreign_source_extra_is_rejected_before_reading_even_known_partial_bytes(h, kernel, monkeypatch):
    real_read = os.read; source_reads = []; enabled = [False]
    def read(fd, amount):
        if enabled[0]: source_reads.append(os.fstat(fd).st_ino)
        return real_read(fd, amount)
    monkeypatch.setattr(negative.os, "read", read)
    lease = h.lease(); h.budget.reserve_start_slot(5)
    source_file(h, "capture/starts/000001/START.spent.json")
    extra = source_file(h, "capture/starts/000001/FOREIGN_SECRET", b"PRIVATE_NOT_TO_READ")
    h.fail(); enabled[0] = True; report = negative.finalize_failed_chunk(lease)
    assert report["requires_process_hold"] and not report["final_negative_manifest_issued"]
    assert not source_reads and not kernel.calls and extra.read_bytes() == b"PRIVATE_NOT_TO_READ"
    assert report["blockers"][0]["contract_code"] == "negative_source_catalogue_changed"
    assert "SECRET" not in str(report)


def test_late_positive_intent_is_unknown_and_cannot_override_global_negative(h, kernel):
    lease = h.lease(); final = source_file(h, "capture/final_closed/closed.json", b'{"status":"complete"}')
    h.fail(); result = negative.finalize_failed_chunk(lease)
    assert result["final_negative_manifest_issued"]
    payload = manifest(h)
    assert payload["positive_intent_has_no_authority"] is True
    row = next(row for row in payload["source_members"] if row["name"] == "capture/final_closed/closed.json")
    assert row["state"] == "UNKNOWN_UNSEALED_OR_PARTIAL" and final.read_bytes() == b'{"status":"complete"}'


def test_late_source_membership_after_marker_seal_prevents_issued_fact(h, kernel, monkeypatch):
    real_audit = negative._audit_files; enabled = [False]
    def audit(lease, files):
        result = real_audit(lease, files)
        if enabled[0] and files[0][0].parent.name == "closure":
            enabled[0] = False; source_file(h, "capture/final_closed/closed.json")
        return result
    monkeypatch.setattr(negative, "_audit_files", audit)
    lease = h.lease(); h.fail(); enabled[0] = True
    result = negative.finalize_failed_chunk(lease)
    assert result["requires_process_hold"] and not result["final_negative_manifest_issued"]
    assert (h.mount / "quarantine/closure" / negative.primitive.BODY_NAME).exists()
    assert (h.mount / "capture/final_closed/closed.json").exists()


def test_partial_native_wire_blocker_cannot_be_hidden_by_global_manifest(h, kernel):
    lease = h.lease(); obs = h.emit(); h.fail(); h.wire_block[0] = "native_partial_chain_unproven"
    negative.preserve_failed_observation(lease, obs)
    result = negative.finalize_failed_chunk(lease)
    assert result["requires_process_hold"] and not result["final_negative_manifest_issued"]
    assert negative._HOLDS[lease] == (obs,) and not kernel.calls


def test_failed_final_native_publication_is_spent_and_holds_original_FD(h, kernel, monkeypatch):
    real_write = os.write; enabled = [False]
    def write(fd, value):
        if enabled[0]: raise OSError(errno.ENOSPC, "PRIVATE_SECRET")
        return real_write(fd, value)
    monkeypatch.setattr(negative.os, "write", write)
    lease = h.lease(); h.fail(); enabled[0] = True
    result = negative.finalize_failed_chunk(lease)
    assert result["requires_process_hold"] and result["original_mount_FD_retained"]
    assert not result["final_negative_manifest_issued"] and result["blockers"][0]["errno_name"] == "ENOSPC"
    enabled[0] = False; again = negative.finalize_failed_chunk(lease)
    assert again["requires_process_hold"] and not again["final_negative_manifest_issued"] and not kernel.calls
    assert "SECRET" not in str(again)


def test_final_manifest_original_nonce_and_files_cannot_be_forged_or_rebased(h, kernel):
    lease = h.lease(); h.fail(); assert negative.finalize_failed_chunk(lease)["final_negative_manifest_issued"]
    original = negative._FINAL_ISSUED[lease]
    replacement = (*original[:7], object())
    negative._FINAL_ISSUED[lease] = negative._FINAL_PINS[lease] = replacement
    result = negative.preservation_binding(lease)
    assert result["requires_process_hold"] and not result["final_negative_manifest_issued"]
    negative._FINAL_ISSUED[lease] = negative._FINAL_PINS[lease] = original
    assert negative.preservation_binding(lease)["requires_process_hold"]


def test_changed_authority_function_cannot_escape_in_a_blocked_public_report(h, kernel, monkeypatch):
    lease = h.lease(); h.fail(); original = negative.authority()
    monkeypatch.setattr(negative, "authority", lambda: {**original, "source_admitted": True, "HTTP_authority": True})
    report = negative.preservation_binding(lease)
    assert report["requires_process_hold"] and report["authority"] == original
    assert report["authority"]["source_admitted"] is report["authority"]["HTTP_authority"] is False
    assert not kernel.calls and report["blockers"][0]["contract_code"] == "negative_original_code_changed"


def test_global_negative_retains_original_settlement_journal_and_new_full_pages(h, kernel, monkeypatch):
    # Explicit fabricated reader seam, genuine plan/budget/ticket/account7
    # append. This test authenticates no real source or terminal HTTP.
    fake = budget_support.fabricated_reader.__wrapped__(monkeypatch)
    h.budget.reserve_start_slot(5); h.budget.reserve_start_slot(6)
    closed = fake.mint(h.budget, outcomes=(("durable", 11), ("durable", 19)))
    h.budget.settle_closed_chunk(closed)
    original_view = negative.accounting.settled_chunk_accounting(h.budget)
    anchor = (*h.anchor[:4], 2, *h.anchor[5:]); h.op._anchor = h.op._identity = anchor
    negative.transport._OPERATIONS[h.op] = anchor, ("LIVE", (), (), (), None, None)
    monkeypatch.setattr(negative.transport, "active_operation_binding", lambda value: anchor)
    lease = h.lease(); ticket = h.budget.reserve_start_slot(7); before = h.budget._state
    h.fail(); negative.accounting._FAILED.add(h.budget)
    result = negative.finalize_failed_chunk(lease)
    assert result["final_negative_manifest_issued"] and not result["requires_process_hold"]
    assert h.budget._state is before and negative.accounting.settled_chunk_accounting(h.budget) is original_view
    assert negative._FINAL_ISSUED[lease][1] is original_view
    payload = manifest(h)
    row = payload["original_irreversible_settlements"][0]
    assert row["charged_bytes"] == 30 and row["START_reservations"] == 2
    assert row["ordered_charges_sha256"] == hash_payload((11, 19))
    assert row["terminal_transport_covered_count"] == 2
    assert payload["original_irreversible_settlements"][0]["original_closure_sha256"] == original_view[3][0][6]
    assert payload["all_current_reserved_tickets"][0]["ordinal"] == negative.accounting._TICKETS[ticket][4] == 3
    assert payload["current_full_page_reservations"] == 2097152


def test_original_closed_control_is_audited_but_partial_neighbor_is_never_read(h, kernel, monkeypatch):
    # Explicit fixed-control issuer seam: the private raw and original9seal
    # are registered as CLOSED, while the second fixed role remains partial.
    real_read = os.read; reads = []; enabled = [False]
    def read(fd, maximum):
        if enabled[0]: reads.append(os.fstat(fd).st_ino)
        return real_read(fd, maximum)
    monkeypatch.setattr(negative.os, "read", read)
    lease = h.lease(); h.budget.reserve_start_slot(5)
    closed = source_file(h, "claim/claim.spent.json", b"SYNTHETIC_CLOSED_CLAIM")
    partial = source_file(h, "capture/starts/000001/START.spent.json")
    with negative.primitive._OwnedOutput(closed.parent, lambda: None) as owned:
        info = closed.lstat(); kernel.flags[info.st_dev, info.st_ino] = 2
        raw = b"SYNTHETIC_CLOSED_CLAIM"; stamp = negative.immutable._stamp(closed.lstat())
        origin = owned, owned._anchor, "claim", closed.name, raw, hash_bytes(raw), owned._anchor[2], -1, stamp[:8], 0, 2, None, 0, None, None
        cap = object.__new__(negative.controls.CountClaim); cap._anchor = cap._identity = origin
        original = origin, h.op, None, None, "claim", "2026-10-27T12:00:00Z", object(), None, None
        negative.controls._CAPS[cap] = negative.controls._ISSUED[cap] = original
        negative.controls._CHOICES[cap] = stamp
    h.fail(); enabled[0] = True; report = negative.finalize_failed_chunk(lease)
    assert report["final_negative_manifest_issued"]
    assert closed.stat().st_ino in reads and partial.stat().st_ino not in reads
    rows = {row["name"]: row for row in manifest(h)["source_members"]}
    assert rows["claim/claim.spent.json"]["state"] == "ORIGINAL_CLOSED_SEAL_AUDITED"
    assert rows["capture/starts/000001/START.spent.json"]["state"] == "UNKNOWN_UNSEALED_OR_PARTIAL"


@pytest.mark.parametrize("change", ["source", "quarantine", "manifest"])
def test_post_marker_original_file_or_membership_drift_permanently_holds(h, kernel, change):
    lease = h.lease(); h.fail(); assert negative.finalize_failed_chunk(lease)["final_negative_manifest_issued"]
    if change == "source": source_file(h, "capture/final_closed/closed.json")
    elif change == "quarantine": (h.mount / "quarantine/FOREIGN").mkdir(mode=0o700)
    else: os.utime(h.mount / "quarantine/closure" / negative.primitive.BODY_NAME, None)
    result = negative.preservation_binding(lease)
    assert result["requires_process_hold"] and not result["final_negative_manifest_issued"]
    assert result["original_mount_FD_retained"] and lease in negative._BLOCKED


def test_maximum_133_chunk_manifest_projection_fits_unchanged_2MiB_cap(monkeypatch):
    """Formatting-only upper bound; NO operational/custody witness is minted.

   132prior chunks,512positions+16extra tickets each, followed by the full
   528current ticket catalogue. The full original account7 objects stay out
    of serialized prior rows and remain required by the real factory.
    """
    registry, accounts = {}, []
    for chunk in range(1, 133):
        tickets = tuple(object() for unused in range(528))
        for ordinal, ticket in enumerate(tickets): registry[ticket] = (None,) * 9 + (hash_payload((chunk, ordinal)),)
        accounts.append((object(), object(), chunk, tickets, (2097152,) * 528,
            tuple(range((chunk - 1) * 512 + 1, chunk * 512 + 1)), hash_payload(("closure", chunk))))
    monkeypatch.setattr(negative.accounting, "_TICKETS", registry)
    settled = object(), object(), object(), tuple(accounts)
    rows = negative._settlement_rows(settled)
    parts = tuple((None, None, None, 133, ordinal, ordinal, None, 3, "f" * 64, "e" * 64) for ordinal in range(1, 529))
    names = negative._catalogue(parts)[0]
    worst = {"original_irreversible_settlements": rows,
        "all_current_reserved_tickets": [{"ordinal": row[4], "position": 999999999, "lifetime_try": 3,
            "request_sha256": "f" * 64, "reservation_sha256": "e" * 64,
            "negative_full_page_charge_unchanged": 2097152} for row in parts],
        "source_members": [{"name": name, "state": "ORIGINAL_CLOSED_SEAL_AUDITED", "bytes": 2097152,
            "sha256": "d" * 64} for name in names],
        "negative_observation_sha256s": ["a" * 64] * 528, "remaining_fixed_control_overhead": "x" * 16384}
    encoded = canonical_json(worst).encode()
    assert len(rows) == 132 and len(names) == 528 * 4 + 5
    assert len(encoded) < 1024 * 1024 < negative.MAXIMUM_BODY_BYTES
    assert all(type(row["charged_bytes"]) is int and "reservation_sha256s" not in row
        and "terminal_transport_covered_positions" not in row for row in rows)


def test_changed_lease_class_hash_refuses_before_any_registry_callback(h, kernel, monkeypatch):
    lease = h.lease(); h.fail(); callbacks = []
    def changed(value): callbacks.append(value); return object.__hash__(value)
    monkeypatch.setattr(negative.OriginalPreservationLease, "__hash__", changed)
    with pytest.raises(negative.NegativePreservationRefusal, match="negative_lease_changed"):
        negative.preservation_binding(lease)
    assert not callbacks and not kernel.calls


def test_changed_operation_class_hash_cannot_run_in_blocked_report(h, kernel, monkeypatch):
    lease = h.lease(); h.fail(); callbacks = []
    def changed(value): callbacks.append(value); return object.__hash__(value)
    monkeypatch.setattr(negative.transport.CountCaptureOperation, "__hash__", changed)
    report = negative.preservation_binding(lease)
    assert report["requires_process_hold"] and not callbacks and not kernel.calls


def test_final_component_cannot_drift_to_a_retry_namespace(h, kernel, monkeypatch):
    lease = h.lease(); h.fail()
    monkeypatch.setattr(negative, "CLOSURE_NAME", "not-a-new-namespace")
    result = negative.finalize_failed_chunk(lease)
    assert result["requires_process_hold"] and not result["final_negative_manifest_issued"]
    assert not (h.mount / "quarantine").exists() and not kernel.calls
