"""Fresh fabricated files + original native caller with a fake C library only."""
import ctypes
import errno
import json
import os
import socket
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("resource")
fcntl = pytest.importorskip("fcntl")

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_body_receipt_custody as custody
import test_short_interest_new_metadata_custody as old

REFUSALS = (custody.BodyReceiptRefusal, custody.immutable.ImmutableMetadataRefusal,
    custody.cache.contract.AnchorCacheRefusal)


@pytest.fixture(autouse=True)
def no_external_or_real_native(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("network/real kernel forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(custody.immutable.ctypes, "CDLL", denied)


@pytest.fixture
def kernel(monkeypatch):
    flags, calls, hooks = {}, [], []
    def read_flags(info): return flags.get((info.st_dev, info.st_ino), 0)
    class Operation:
        def __call__(self, fd, target):
            info = os.fstat(fd); initial = read_flags(info)
            assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            assert initial in (0, 64) and target == initial | 2
            calls.append((fd, target)); flags[info.st_dev, info.st_ino] = target
            os.fchmod(fd, 0o600)  # Fake preseal ctime transition, never real flags.
            for hook in hooks: hook(fd)
            return 0
    operation = Operation()
    class Library: fchflags = operation
    def library(name, *, use_errno):
        assert name == "/usr/lib/libSystem.B.dylib" and use_errno is True
        return Library()
    monkeypatch.setattr(custody.immutable, "_flags", read_flags)
    monkeypatch.setattr(custody.immutable.ctypes, "CDLL", library)
    return SimpleNamespace(flags=flags, calls=calls, hooks=hooks, operation=operation)


@pytest.fixture
def h(tmp_path):
    original = old.Harness(tmp_path)
    original.body = b'{"synthetic":"body"}'
    original.binding = custody.freeze_body_receipt_binding(request_sha256="1" * 64,
        attempt_sha256="2" * 64, reservation_sha256="3" * 64, protocol_sha256="4" * 64)
    try: yield original
    finally: original.close()


def prepare(h, body=None, binding=None):
    return custody.prepare_owned_body_receipt(h.owned, h.body if body is None else body,
        binding=h.binding if binding is None else binding, boundary=h.boundary,
        monotonic=h.clock, sleep=h.clock.sleep)


def test_maximum_body_and_internal_receipt_close_only_both_original_contexts(h, kernel):
    body = b"synthetic-owned-only\n" * 104857 + b"x" * 12
    body = (body * 2)[:custody.MAXIMUM_BODY_BYTES]
    assert len(body) == 2 * 1024 ** 2
    with prepare(h, body=body) as pair:
        pair.check(); assert pair.read_body() == body
        raw = pair.read_receipt(); receipt = json.loads(raw)
        assert 0 < len(raw) <= 1024 and raw == canonical_json(receipt).encode()
        assert receipt["binding"] == h.binding.to_payload() and receipt["binding_sha256"] == h.binding.sha256
        assert receipt["body_sha256"] == hash_bytes(body) and receipt["body_bytes"] == len(body)
        assert custody._clock(receipt["creation_started_at"]) <= custody._clock(receipt["receipt_built_at"])
        observation = pair.observation()
        assert [row["role"] for row in observation["files"]] == ["body", "receipt"]
        assert not any(row["original_context_closed"] for row in observation["files"])
        caps = pair._anchor[3]; original_fds = [cap._anchor[7] for cap in caps]
        assert all(custody._file_anchor(cap) is cap._anchor for cap in caps)
    closed = pair.closed_summary()
    assert closed["status"] == "closed_body_receipt_custody_only"
    assert all(row["original_context_closed"] for row in closed["files"])
    assert [row["seal_stamp_sha256"] for row in closed["files"]] == [row["seal_stamp_sha256"] for row in observation["files"]]
    assert closed["authority"]["budget_release_authority"] is closed["authority"]["source_admitted"] is False
    assert h.clock.sleeps == [.25] * 8 and len(kernel.calls) == 2
    for fd in original_fds:
        with pytest.raises(OSError): os.fstat(fd)
    h.owned.close(); pair.check_after_close()
    assert pair.closed_summary() == closed
    assert custody.creator.MAXIMUM_BYTES == 1024


@pytest.mark.parametrize("body", [b"", b"x" * (2097152 + 1), "secret", bytearray(b"x"), True])
def test_bounds_and_exact_bytes_are_checked_before_any_file(h, body):
    with pytest.raises(custody.BodyReceiptRefusal, match="bounds_refused"):
        with prepare(h, body=body): pytest.fail("invalid body accepted")
    assert list(h.output.iterdir()) == []


def test_partial_writes_keep_original_progress_and_full_bytes(h, kernel, monkeypatch):
    write = os.write
    monkeypatch.setattr(os, "write", lambda fd, raw: write(fd, raw[:7]))
    with prepare(h) as pair: assert pair.read_body() == h.body
    assert pair.closed_summary()["files"][0]["bytes"] == len(h.body)


@pytest.mark.parametrize("amount", [0, True, -1])
def test_invalid_write_progress_preserves_prefix_and_refuses_pair(h, kernel, monkeypatch, amount):
    monkeypatch.setattr(os, "write", lambda *args: amount)
    with pytest.raises(custody.BodyReceiptRefusal, match="write_progress_changed"):
        with prepare(h): pytest.fail("write progress accepted")
    assert (h.output / custody.BODY_NAME).exists() and kernel.calls == []


def test_body_remains_held_through_receipt_creation_and_seal(h, kernel):
    def drift(unused):
        if len(kernel.calls) == 2: (h.output / custody.BODY_NAME).chmod(0o600)
    kernel.hooks.append(drift)
    with pytest.raises(REFUSALS):
        with prepare(h): pytest.fail("late first-file drift escaped")
    assert {path.name for path in h.output.iterdir()} == {custody.BODY_NAME, custody.RECEIPT_NAME}
    assert (h.output / custody.BODY_NAME).read_bytes() == h.body


@pytest.mark.parametrize("role", [0, 1])
@pytest.mark.parametrize("change", ["ctime", "flags", "bytes", "mode", "hardlink"])
def test_either_postseal_change_dominates_pair_and_cannot_be_resealed(h, kernel, role, change):
    with pytest.raises(REFUSALS):
        with prepare(h) as pair:
            cap = pair._anchor[3][role]; origin = custody._file_anchor(cap); path = h.output / origin[3]
            if change == "ctime": path.chmod(0o600)
            elif change == "flags": kernel.flags[origin[8][0], origin[8][1]] = 0
            elif change == "bytes": path.write_bytes(b"x" * len(origin[4]))
            elif change == "mode": path.chmod(0o640)
            else: os.link(path, h.output / "retained-link")
            with pytest.raises(REFUSALS): pair.check()
    with pytest.raises(REFUSALS): pair.closed_summary()


def test_file_reseal_is_terminal_not_a_second_original_constructor(h, kernel):
    with pytest.raises(custody.BodyReceiptRefusal):
        with prepare(h) as pair:
            with pytest.raises(custody.BodyReceiptRefusal, match="seal_once_required"):
                pair._anchor[3][0].seal_once()
    assert len(kernel.calls) == 2


@pytest.mark.parametrize("field", ["last_tick", "samples", "flag_set", "phase"])
def test_mutable_file_state_cannot_reset_provenance_and_restore_after_failure(h, kernel, field):
    with pytest.raises(custody.BodyReceiptRefusal):
        with prepare(h) as pair:
            cap = pair._anchor[3][0]; state = cap._binding()[1]; original = state[field]
            state[field] = -1.0 if field == "last_tick" else () if field == "samples" else False if field == "flag_set" else "UNSEALED"
            with pytest.raises(custody.BodyReceiptRefusal): pair.check()
            state[field] = original
            with pytest.raises(custody.BodyReceiptRefusal): pair.check()
    with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()


def test_backward_clock_during_first_file_seal_never_resets(h, kernel):
    h.clock.hook = lambda: setattr(h.clock, "now", -1.0)
    with pytest.raises(custody.BodyReceiptRefusal, match="clock_refused"):
        with prepare(h): pytest.fail("backdated clock accepted")


def test_each_file_gets_its_original_eight_seconds_not_an_enlarged_pair_window(h, kernel):
    def late(unused):
        if len(kernel.calls) == 2: h.clock.now += 8.01
    kernel.hooks.append(late)
    with pytest.raises(custody.BodyReceiptRefusal, match="window_exhausted"):
        with prepare(h): pytest.fail("second file deadline reset")
    assert len(kernel.calls) == 2


@pytest.mark.parametrize("change", ["authority", "kernel", "bool", "subclass"])
def test_full_exact_policy_fails_before_creation(h, monkeypatch, change):
    if change == "authority":
        old_authority = custody.authority
        monkeypatch.setattr(custody, "authority", lambda: {**old_authority(), "source_admitted": True})
    elif change == "kernel":
        old_policy = custody.immutable.policy
        monkeypatch.setattr(custody.immutable, "policy", lambda: {**old_policy(), "extra": "not admitted"})
    elif change == "bool": monkeypatch.setattr(custody, "QUIET_SECONDS", True)
    else:
        class Text(str): pass
        monkeypatch.setattr(custody, "BODY_NAME", Text(custody.BODY_NAME))
    with pytest.raises(custody.BodyReceiptRefusal, match="policy_changed"): custody._check_policy()
    with pytest.raises(custody.BodyReceiptRefusal):
        with prepare(h): pytest.fail("changed policy accepted")
    assert list(h.output.iterdir()) == []


@pytest.mark.parametrize("closed", [False, True])
def test_policy_changes_veto_live_and_closed_access_and_latch(h, kernel, monkeypatch, closed):
    if closed:
        with prepare(h) as pair: pair.check()
        original = custody.authority
        monkeypatch.setattr(custody, "authority", lambda: {**original(), "source_admitted": True})
        with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()
    else:
        with pytest.raises(custody.BodyReceiptRefusal):
            with prepare(h) as pair:
                original = custody.authority
                monkeypatch.setattr(custody, "authority", lambda: {**original(), "source_admitted": True})
                pair.check()
    monkeypatch.setattr(custody, "authority", original)
    with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()


def test_live_phase_and_copied_fields_cannot_mint_a_closed_pair(h, kernel):
    with pytest.raises(custody.BodyReceiptRefusal):
        with prepare(h) as pair:
            origin, state = pair._binding(); state["phase"] = "CLOSED"
            with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()
            state["phase"] = "LIVE"
            with pytest.raises(custody.BodyReceiptRefusal): pair.check()
    forged = object.__new__(custody.BodyReceiptCustody); forged._anchor = forged._identity = origin
    with pytest.raises(custody.BodyReceiptRefusal): forged.closed_summary()


def test_binding_and_original_file_forgery_are_not_old_metadata_capabilities(h, kernel):
    with pytest.raises(custody.BodyReceiptRefusal): custody.BodyReceiptBinding()
    fake = object.__new__(custody.BodyReceiptBinding); fake._parts = fake._identity = h.binding._parts
    with pytest.raises(custody.BodyReceiptRefusal): custody._binding_anchor(fake)
    with prepare(h) as pair:
        cap = pair._anchor[3][0]
        fake_file = object.__new__(custody.BodyReceiptFileCustody); fake_file._anchor = fake_file._identity = cap._anchor
        with pytest.raises(custody.BodyReceiptRefusal): custody._file_anchor(fake_file)


def test_both_pair_duplicates_drain_even_when_first_close_fails(h, kernel, monkeypatch):
    duplicates, closed = [], []
    duplicate, close = os.dup, os.close
    def dup(fd): result = duplicate(fd); duplicates.append(result); return result
    def failing(fd):
        close(fd)
        if fd in duplicates:
            closed.append(fd)
            if len(closed) == 1: raise OSError(errno.EIO, "SECRET close")
    monkeypatch.setattr(os, "dup", dup); monkeypatch.setattr(os, "close", failing)
    with pytest.raises(OSError):
        with prepare(h) as pair: pair.check()
    assert len(duplicates) == len(closed) == 2 and set(duplicates) == set(closed)
    for fd in duplicates:
        with pytest.raises(OSError): os.fstat(fd)
    with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()


def test_closed_path_parent_descriptors_drain_after_first_close_error(h, kernel, monkeypatch):
    with prepare(h) as pair: pair.check()
    opened, closed = [], []
    original_open, original_close = os.open, os.close
    def open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        if args[1] & os.O_DIRECTORY and args[0] != ".": opened.append(fd)
        return fd
    def close(fd):
        original_close(fd)
        if fd in opened:
            closed.append(fd)
            if len(closed) == 1: raise OSError(errno.EIO, "SECRET closed audit")
    monkeypatch.setattr(os, "open", open); monkeypatch.setattr(os, "close", close)
    with pytest.raises(OSError): pair.check_after_close()
    assert len(opened) == len(closed) == 2 and set(opened) == set(closed)
    with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()


def test_reopened_read_descriptor_must_really_be_readonly(h, kernel, monkeypatch):
    with prepare(h) as pair: pair.check()
    original = os.open
    def open(name, flags, *args, **kwargs):
        if name in (custody.BODY_NAME, custody.RECEIPT_NAME): flags = (flags & ~os.O_ACCMODE) | os.O_RDWR
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", open)
    with pytest.raises(custody.BodyReceiptRefusal, match="readonly_required"): pair.check_after_close()


@pytest.mark.parametrize("number", list(custody._OS_ERRNOS) + [987654])
def test_builtin_os_errors_preserve_only_allowlisted_errno(number):
    error = OSError(number, "SECRET body or path", "/SECRET/private")
    value = custody.failure_summary(error)
    assert value == {"category": "local_os_error", "errno_name": custody._OS_ERRNOS.get(number), "contract_code": None}
    assert "SECRET" not in canonical_json(value)


def test_hostile_diagnostics_never_format_values_or_dynamic_types():
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile property")
        def __str__(self): pytest.fail("hostile formatting")
    class Text(str):
        def __eq__(self, other): pytest.fail("hostile comparison")
    for error in (Error(), custody.BodyReceiptRefusal(Text("SECRET")), custody.BodyReceiptRefusal("SECRET")):
        value = custody.failure_summary(error)
        assert value["contract_code"] is None and "SECRET" not in canonical_json(value)


def test_original_monitor_catalogue_contains_no_caller_phase_codes():
    codes = custody.monitor_phase_codes()
    assert codes["body_receipt_native_creator"] is custody._prepare_original_file.__wrapped__.__code__
    assert codes["body_receipt_guard_callback"].co_name == "guarded_boundary"
    assert {"origin", "file_cap"}.issubset(codes["body_receipt_guard_callback"].co_freevars)


def test_rollback_after_original_creation_tick_refuses_before_native(h, kernel, monkeypatch):
    close, read = os.close, custody._read_original
    advanced = []
    def closing(fd):
        writer = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR
        close(fd)
        if writer and not advanced: advanced.append(True); h.clock.now = 5.0
    def reading(*args, **kwargs):
        h.clock.now = 1.0
        return read(*args, **kwargs)
    monkeypatch.setattr(os, "close", closing); monkeypatch.setattr(custody, "_read_original", reading)
    with pytest.raises(custody.BodyReceiptRefusal, match="clock_refused"):
        with prepare(h): pytest.fail("known rollback reached native setter")
    assert kernel.calls == [] and (h.output / custody.BODY_NAME).exists()


@pytest.mark.parametrize("closed", [False, True])
def test_negative_sibling_during_last_receipt_read_refuses_and_latches(h, kernel, monkeypatch, closed):
    read = custody._read_original; inserted = []
    if closed:
        with prepare(h) as pair: pair.check()
    def reading(origin, *args, **kwargs):
        result = read(origin, *args, **kwargs)
        expected_caller = custody._audit_closed_paths.__code__ if closed else custody._audit_pair.__code__
        if origin[2] == "receipt" and not inserted and sys._getframe(1).f_code is expected_caller:
            inserted.append(True); (h.output / "fixed-negative.private.json").write_bytes(b'{"refused":true}')
        return result
    monkeypatch.setattr(custody, "_read_original", reading)
    with pytest.raises(custody.BodyReceiptRefusal, match="membership_changed"):
        if closed: pair.check_after_close()
        else:
            with prepare(h): pytest.fail("third member admitted")
    assert (h.output / "fixed-negative.private.json").read_bytes() == b'{"refused":true}'
    if closed:
        with pytest.raises(custody.BodyReceiptRefusal): pair.closed_summary()


@pytest.mark.parametrize("change", ["mtime", "tracked"])
def test_original_pre_native_properties_are_not_rebased_to_a_current_stat(h, kernel, monkeypatch, change):
    fstat = os.fstat; changed = []
    def observed(fd):
        info = fstat(fd)
        pending = [entry for entry in custody._FILES.values() if entry[0][0] is h.owned and entry[0][7] == fd
            and entry[1]["phase"] == "UNSEALED" and entry[1]["flag_set"] is False]
        if pending and not changed:
            changed.append(True); origin = pending[0][0]
            if change == "mtime":
                os.utime(h.output / origin[3], ns=(info.st_atime_ns, info.st_mtime_ns + 1))
            else: kernel.flags[info.st_dev, info.st_ino] = 64
            info = fstat(fd)
        return info
    monkeypatch.setattr(os, "fstat", observed)
    with pytest.raises(custody.BodyReceiptRefusal):
        with prepare(h): pytest.fail("known original drift reached the setter")
    assert changed and kernel.calls == [] and (h.output / custody.BODY_NAME).read_bytes() == h.body


def test_receipt_write_failure_never_mints_a_pair_or_loses_the_original_body(h, kernel, monkeypatch):
    write = os.write
    def writing(fd, raw):
        if (h.output / custody.RECEIPT_NAME).exists(): raise OSError(errno.ENOSPC, "SECRET disk path")
        return write(fd, raw)
    monkeypatch.setattr(os, "write", writing)
    with pytest.raises(OSError) as failure:
        with prepare(h): pytest.fail("receipt failure admitted")
    assert custody.failure_summary(failure.value)["errno_name"] == "ENOSPC"
    assert (h.output / custody.BODY_NAME).read_bytes() == h.body and len(kernel.calls) == 1
    assert (h.output / custody.RECEIPT_NAME).exists()


def test_existing_body_is_never_adopted_or_rewritten(h):
    path = h.output / custody.BODY_NAME; path.write_bytes(h.body); before = path.stat()
    with pytest.raises(custody.BodyReceiptRefusal, match="membership_changed"):
        with prepare(h): pytest.fail("existing body adopted")
    assert path.read_bytes() == h.body and path.stat() == before
