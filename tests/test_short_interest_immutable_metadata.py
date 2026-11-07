"""Fabricated metadata and fake Darwin kernel only; never real flag setting."""
import ctypes
import errno
import os
import socket

import pytest
# fcntl is POSIX-only and this module uses it directly, so it cannot be collected on
# the supported Windows host; see the lane record SI-CR18-001.
fcntl = pytest.importorskip(
    "fcntl",
    reason=(
        "the protected-capture runtime and this test use the POSIX-only module "
        "fcntl at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from data.hashing import canonical_json, hash_bytes, hash_payload

from scripts import short_interest_immutable_metadata as immutable
import test_short_interest_new_metadata_custody as original

REAL_NATIVE_SET = immutable._native_set
REFUSALS = (immutable.ImmutableMetadataRefusal, immutable.creator.NewMetadataRefusal,
    immutable.creator.cache.contract.AnchorCacheRefusal)


@pytest.fixture(autouse=True)
def deny_external_and_real_kernel(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("network or real flag setting forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(immutable, "_native_set", denied)


@pytest.fixture
def h(tmp_path):
    value = original.Harness(tmp_path)
    try: yield value
    finally: value.close()


@pytest.fixture
def kernel(monkeypatch):
    flags, calls = {}, []
    def read_flags(info): return flags.get((info.st_dev, info.st_ino), 0)
    def set_immutable(fd, initial_flags=0):
        info = os.fstat(fd)
        assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        assert immutable._flags(info) == initial_flags and initial_flags in (0, 64)
        calls.append(fd); flags[info.st_dev, info.st_ino] = initial_flags | immutable.IMMUTABLE_FLAG
        # Fake only: represent the kernel's PRESEAL metadata transition with
        # an ordinary chmod of this fabricated inode. Never set real flags.
        os.fchmod(fd, 0o600)
    monkeypatch.setattr(immutable, "_flags", read_flags)
    monkeypatch.setattr(immutable, "_native_set", set_immutable)
    return flags, calls


def prepare(h, **changes):
    return immutable.prepare_owned_immutable_metadata(h.owned, h.name, h.raw,
        boundary=changes.pop("boundary", h.boundary), monotonic=h.clock,
        sleep=h.clock.sleep, **changes)


def test_one_original_creator_one_original_seal_and_original_nine_field_closure(h, kernel, monkeypatch):
    calls, original_init = [], immutable.creator.cache.HeldFiles.__init__
    def init(held, *args, **kwargs): calls.append(1); return original_init(held, *args, **kwargs)
    monkeypatch.setattr(immutable.creator.cache.HeldFiles, "__init__", init)
    with prepare(h) as value:
        duplicate = value._anchor[3]
        original_fd = value._anchor[1][7]
        assert duplicate != original_fd and value.observation()["phase"] == "UNSEALED"
        value.seal_once(); value.check()
        assert value.read() == h.raw
        observed = value.observation()
        chosen = value._anchor[0]._state_identity["seal_stamp"]
        assert immutable._MINTED[id(value)][2]["seal"] == (*chosen, immutable.IMMUTABLE_FLAG)
        assert observed["seal_stamp_sha256"] == hash_payload([*chosen, immutable.IMMUTABLE_FLAG])
        assert observed["original_creator_observation"]["seal_stamp_sha256"] == hash_payload(list(chosen))
        assert "redacted" in repr(value) and str(h.path) not in canonical_json(observed)
    summary = value.closed_summary()
    assert summary["status"] == "closed_kernel_immutable_new_metadata_only"
    assert summary["seal_stamp_sha256"] == observed["seal_stamp_sha256"]
    assert summary["expected_raw_sha256"] == hash_bytes(h.raw)
    assert summary["authority"]["source_admitted"] is summary["authority"]["ready_for_backtest"] is False
    assert summary["original_creator_observation"]["phase"] == "CLOSED"
    summary["authority"]["source_admitted"] = True
    assert value.closed_summary()["authority"]["source_admitted"] is False
    for fd in (duplicate, original_fd):
        with pytest.raises(OSError): os.fstat(fd)
    assert len(calls) == len(kernel[1]) == 1 and h.path.read_bytes() == h.raw


def test_original_flags_are_not_adopted_or_cleared(h, kernel):
    flags, calls = kernel
    def boundary():
        if h.path.exists():
            info = h.path.stat(); flags[info.st_dev, info.st_ino] = 4
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="initial_flags_refused"):
        with prepare(h, boundary=boundary): pytest.fail("old flags adopted")
    assert not calls and h.path.read_bytes() == h.raw


def test_existing_matching_file_is_never_opened_or_flagged(h, kernel):
    h.path.write_bytes(h.raw); h.path.chmod(0o600)
    before = h.path.stat()
    with pytest.raises(FileExistsError):
        with prepare(h): pytest.fail("old file adopted")
    assert not kernel[1] and h.path.read_bytes() == h.raw and h.path.stat().st_ino == before.st_ino


@pytest.mark.parametrize("change", ["flags", "ctime", "mtime", "bytes", "mode", "inode", "hardlink"])
def test_every_postseal_change_refuses_permanently_without_reseal(h, kernel, change):
    with pytest.raises(REFUSALS):
        with prepare(h) as value:
            value.seal_once(); old = h.path.stat()
            if change == "flags": kernel[0][old.st_dev, old.st_ino] = 0
            elif change == "ctime": h.path.chmod(0o600)
            elif change == "mtime": os.utime(h.path, ns=(old.st_atime_ns, old.st_mtime_ns + 1))
            elif change == "bytes": h.path.write_bytes(h.raw.replace(b"false", b"False"))
            elif change == "mode": h.path.chmod(0o640)
            elif change == "inode":
                h.path.rename(h.root / "retained-original"); h.path.write_bytes(h.raw); h.path.chmod(0o600)
            else: os.link(h.path, h.root / "retained-link")
            with pytest.raises(REFUSALS): value.check()
            assert value.observation()["phase"] == "REFUSED"
            with pytest.raises(immutable.ImmutableMetadataRefusal): value.seal_once()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()
    assert len(kernel[1]) == 1


def test_flags_checked_inside_original_constructor_boundary(h, kernel, monkeypatch):
    init = immutable.creator.cache.HeldFiles.__init__
    def changed(held, *args, **kwargs):
        info = h.path.stat(); kernel[0][info.st_dev, info.st_ino] = 0
        try: return init(held, *args, **kwargs)
        finally: kernel[0][info.st_dev, info.st_ino] = immutable.IMMUTABLE_FLAG
    monkeypatch.setattr(immutable.creator.cache.HeldFiles, "__init__", changed)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"):
        with prepare(h) as value: value.seal_once()
    assert value.observation()["phase"] == "REFUSED"


@pytest.mark.parametrize("when", ["inner_close", "duplicate_close"])
def test_successful_original_or_duplicate_close_cannot_hide_late_stamp_change(h, kernel, monkeypatch, when):
    if when == "inner_close":
        close = immutable.creator.NewMetadataCustody._close
        def altered(cap, *, validate):
            close(cap, validate=validate)
            if validate: h.path.chmod(0o600)
        monkeypatch.setattr(immutable.creator.NewMetadataCustody, "_close", altered)
    else:
        close = os.close
        duplicate = [None]
        def altered(fd):
            close(fd)
            if fd == duplicate[0]: h.path.chmod(0o600)
        monkeypatch.setattr(os, "close", altered)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="stamp_changed"):
        with prepare(h) as value:
            if when == "duplicate_close": duplicate[0] = value._anchor[3]
            value.seal_once()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


@pytest.mark.parametrize("failure", ["body", "early_closed", "binding", "original_binding", "unsealed"])
def test_errors_cannot_be_swallowed_restored_or_converted_to_closed_proof(h, kernel, failure):
    with pytest.raises((*REFUSALS, RuntimeError)):
        with prepare(h) as value:
            if failure == "body": raise RuntimeError("fabricated body")
            if failure == "unsealed": pass
            elif failure == "early_closed":
                with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()
            else:
                value.seal_once()
                target = value if failure == "binding" else value._anchor[0]
                original_anchor = target._anchor
                target._anchor = target._identity = tuple(list(original_anchor))
                with pytest.raises(immutable.ImmutableMetadataRefusal): value.read()
                target._anchor = target._identity = original_anchor
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()
    assert h.path.read_bytes() == h.raw


def test_duplicate_cleanup_survives_unrestored_reflection(h, kernel, monkeypatch):
    duplicates = []
    duplicate = os.dup
    def dup(fd):
        result = duplicate(fd); duplicates.append(result); return result
    monkeypatch.setattr(os, "dup", dup)
    with pytest.raises(immutable.ImmutableMetadataRefusal):
        with prepare(h) as value:
            value.seal_once(); value._anchor = (); value.check()
    assert len(duplicates) == 1
    with pytest.raises(OSError): os.fstat(duplicates[0])


def test_reported_kernel_success_without_the_flag_is_not_a_seal(h, kernel, monkeypatch):
    monkeypatch.setattr(immutable, "_native_set", lambda fd, initial_flags=0: None)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"):
        with prepare(h): pytest.fail("kernel no-op accepted")
    assert h.path.read_bytes() == h.raw


def test_duplicate_close_error_never_issues_a_closed_witness(h, kernel, monkeypatch):
    close, duplicate = os.close, [None]
    def failing(fd):
        close(fd)
        if fd == duplicate[0]: raise OSError(errno.EIO, "SECRET close")
    monkeypatch.setattr(os, "close", failing)
    with pytest.raises(OSError):
        with prepare(h) as value:
            duplicate[0] = value._anchor[3]; value.seal_once()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


def test_kernel_phase_does_not_reset_the_original_eight_second_creation_window(h, kernel, monkeypatch):
    setter = immutable._native_set
    def delayed(fd, initial_flags=0): setter(fd, initial_flags=initial_flags); h.clock.now = 9.0
    monkeypatch.setattr(immutable, "_native_set", delayed)
    with pytest.raises(immutable.creator.NewMetadataRefusal, match="window_exhausted"):
        with prepare(h): pytest.fail("late flagging reset the original window")
    assert h.path.read_bytes() == h.raw


def test_original_chosen_stamp_cannot_be_replaced_by_a_new_nine_field_baseline(h, kernel):
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="seal_changed"):
        with prepare(h) as value:
            value.seal_once()
            cap = value._anchor[0]
            original = cap._state_identity["seal_stamp"]
            cap._state_identity["seal_stamp"] = (*original[:-1], original[-1] + 1)
            value.check()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


def test_unsupported_platform_fails_before_a_new_inode(h, monkeypatch):
    monkeypatch.setattr(immutable.sys, "platform", "not-darwin")
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="platform_refused"):
        with prepare(h): pytest.fail("unsupported platform created a file")
    assert not h.path.exists()


@pytest.mark.parametrize("result,number,expected", [(-1, errno.EPERM, "EPERM"),
    (-1, errno.ENOTSUP, "ENOTSUP"), (-1, 987654, None), (False, 0, None)])
def test_exact_darwin_symbol_abi_fixed_errno_and_bad_results(monkeypatch, result, number, expected):
    calls = []
    class Operation:
        def __call__(self, fd, flags):
            calls.append((fd, flags)); ctypes.set_errno(number); return result
    operation = Operation()
    class Library: fchflags = operation
    def load(name, *, use_errno):
        assert name == "/usr/lib/libSystem.B.dylib" and use_errno is True
        return Library()
    monkeypatch.setattr(immutable.ctypes, "CDLL", load)
    with pytest.raises(immutable.ImmutableMetadataRefusal) as failure: REAL_NATIVE_SET(77)
    assert operation.argtypes == (ctypes.c_int, ctypes.c_uint) and operation.restype is ctypes.c_int
    assert calls == [(77, 2)] and immutable.failure_summary(failure.value)["errno_name"] == expected


def test_missing_kernel_symbol_and_hostile_diagnostics_are_fixed(monkeypatch):
    monkeypatch.setattr(immutable.ctypes, "CDLL", lambda *args, **kwargs: object())
    with pytest.raises(immutable.ImmutableMetadataRefusal) as failure: REAL_NATIVE_SET(77)
    assert immutable.failure_summary(failure.value)["contract_code"] == "immutable_kernel_unavailable"
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile property")
        def __str__(self): pytest.fail("hostile formatting")
    assert immutable.failure_summary(Error())["contract_code"] is None
    error = immutable.ImmutableMetadataRefusal("SECRET", 987654)
    assert "SECRET" not in canonical_json(immutable.failure_summary(error))


@pytest.mark.parametrize("initial,expected", [(0, 2), (64, 66)])
def test_fixed_native_success_preserves_observed_tracked_and_never_unlocks(monkeypatch, initial, expected):
    calls = []
    class Operation:
        def __call__(self, fd, flags): calls.append((fd, flags)); return 0
    class Library: fchflags = Operation()
    monkeypatch.setattr(immutable.ctypes, "CDLL", lambda *args, **kwargs: Library())
    REAL_NATIVE_SET(88, initial_flags=initial)
    assert calls == [(88, expected)]


def test_factory_forgery_policy_changes_and_subclasses_refuse(h, kernel, monkeypatch):
    with pytest.raises(immutable.ImmutableMetadataRefusal): immutable.ImmutableMetadataCustody()
    empty = object.__new__(immutable.ImmutableMetadataCustody)
    with pytest.raises(immutable.ImmutableMetadataRefusal): empty.read()
    with pytest.raises(immutable.ImmutableMetadataRefusal):
        with prepare(h) as value:
            value.seal_once()
            monkeypatch.setattr(immutable, "LIBRARY", "SECRET")
            value.read()


def test_live_mutable_state_cannot_mint_a_terminal_closed_receipt(h, kernel):
    escaped = []
    with pytest.raises(immutable.ImmutableMetadataRefusal):
        with prepare(h) as value:
            value.seal_once()
            state = value._binding()[1]
            original = state["closed"], state["closed_raw"]
            state["closed"] = True
            state["closed_raw"] = canonical_json({"status": "closed_kernel_immutable_new_metadata_only",
                "phase": "CLOSED", "authority": immutable.authority()}).encode()
            with pytest.raises(immutable.ImmutableMetadataRefusal): escaped.append(value.closed_summary())
            state["closed"], state["closed_raw"] = original
            with pytest.raises(immutable.ImmutableMetadataRefusal, match="latched_failure"): value.check()
    assert escaped == []
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


@pytest.mark.parametrize("change", ["raw", "phase", "seal", "held"])
def test_issued_original_closure_and_seal_cannot_be_reconstructed_or_restored(h, kernel, change):
    with prepare(h) as value: value.seal_once()
    state = value._binding()[1]
    field = {"raw": "closed_raw", "phase": "closed", "seal": "seal", "held": "held"}[change]
    original = state[field]
    state[field] = (bytes(bytearray(original)) if change == "raw" else False if change == "phase"
        else tuple(list(original)) if change == "seal" else None)
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()
    state[field] = original
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="latched_failure"): value.closed_summary()


def test_mutable_failed_flag_cannot_reset_the_independent_refusal_latch(h, kernel):
    with pytest.raises(immutable.ImmutableMetadataRefusal):
        with prepare(h) as value:
            value.seal_once(); state = value._binding()[1]
            with pytest.raises(immutable.ImmutableMetadataRefusal): value.read(0)
            state["failed"] = False
            with pytest.raises(immutable.ImmutableMetadataRefusal): value.read()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


def test_fresh_tracked_inode_preserves_exact_66_through_original_seal_and_closure(h, kernel, monkeypatch):
    flags, calls = kernel
    monkeypatch.setattr(immutable, "_flags", lambda info: flags.get((info.st_dev, info.st_ino), 64))
    with prepare(h) as value:
        assert value.observation()["initial_flags"] == 64
        assert value.observation()["expected_flags"] == 66
        value.seal_once(); value.check(); assert value.read() == h.raw
        chosen = value._anchor[0]._state_identity["seal_stamp"]
        expected = hash_payload([*chosen, 66])
        assert value.observation()["seal_stamp_sha256"] == expected
    summary = value.closed_summary()
    assert summary["expected_flags"] == 66 and summary["initial_flags"] == 64
    assert summary["seal_stamp_sha256"] == expected
    assert flags[h.path.stat().st_dev, h.path.stat().st_ino] == 66 and len(calls) == 1
    assert immutable.policy()["schema"] == "si-new-kernel-immutable-metadata-policy-v2"
    assert immutable.policy()["initial_flags_allowed"] == [0, 64]


@pytest.mark.parametrize("initial,changed", [(0, 66), (64, 2)])
def test_tracked_addition_or_removal_after_seal_is_not_adopted_or_restored(h, kernel, monkeypatch, initial, changed):
    flags, unused = kernel
    monkeypatch.setattr(immutable, "_flags", lambda info: flags.get((info.st_dev, info.st_ino), initial))
    with pytest.raises(immutable.ImmutableMetadataRefusal):
        with prepare(h) as value:
            value.seal_once(); info = h.path.stat(); key = info.st_dev, info.st_ino
            flags[key] = changed
            with pytest.raises(immutable.ImmutableMetadataRefusal, match="flags_changed"): value.check()
            flags[key] = initial | 2
            with pytest.raises(immutable.ImmutableMetadataRefusal, match="latched_failure"): value.check()
    with pytest.raises(immutable.ImmutableMetadataRefusal): value.closed_summary()


@pytest.mark.parametrize("initial", [2, 66, 4, 128, 192, 0x10000])
def test_every_other_initial_flag_value_refuses_before_any_setter(h, kernel, monkeypatch, initial):
    flags, calls = kernel
    monkeypatch.setattr(immutable, "_flags", lambda unused: initial)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="initial_flags_refused"):
        with prepare(h): pytest.fail("unknown/already-immutable flag adopted")
    assert calls == [] and h.path.read_bytes() == h.raw


def test_named_and_fd_initial_flags_must_match_even_when_each_value_is_allowed(h, kernel, monkeypatch):
    observed = iter((0, 64))
    monkeypatch.setattr(immutable, "_flags", lambda unused: next(observed))
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="initial_flags_refused"):
        with prepare(h): pytest.fail("different initial name/FD flags adopted")
    assert kernel[1] == []


@pytest.mark.parametrize("initial", [False, True, -1, 2, 66, 128, "64"])
def test_native_shim_never_accepts_arbitrary_flags_or_boolean_coercion(monkeypatch, initial):
    def denied(*args, **kwargs): pytest.fail("invalid flags reached the native library")
    monkeypatch.setattr(immutable.ctypes, "CDLL", denied)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="initial_flags_refused"):
        REAL_NATIVE_SET(77, initial_flags=initial)


def test_platform_tracked_flag_must_match_the_explicit_64_policy(h, monkeypatch):
    monkeypatch.setattr(immutable.stat, "UF_TRACKED", 32)
    with pytest.raises(immutable.ImmutableMetadataRefusal, match="platform_refused"):
        with prepare(h): pytest.fail("wrong platform flag definition accepted")
    assert not h.path.exists()
