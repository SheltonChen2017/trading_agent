"""Invented newly created publications only; actual inputs remain denied."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX private publication custody")
from research import insider_buying_pilot_publication_seal_v1 as m


@pytest.fixture
def leaf(tmp_path):
    directory = tmp_path / "invented-private"; directory.mkdir(mode=0o700)
    name, raw = "reservation.json", b'{"fixture_only":true,"known":"own publication"}'
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: yield parent, name, raw, path
    finally: os.close(parent)


class Clock:
    def __init__(self): self.now, self.sleeps = 0.0, []
    def clock(self): return self.now
    def sleep(self, seconds):
        assert 0 < seconds <= m.POLL_SECONDS
        self.sleeps.append(seconds); self.now += seconds


def _seal(leaf, clock, observe=m._observe):
    fd, name, raw, _ = leaf
    return m._seal(fd, name, raw, clock=clock.clock, sleep=clock.sleep, observe=observe)


def test_delayed_ctime_waits_for_full_quiet_window_without_weakening_other_fields(leaf):
    clock = Clock(); original = None; examined = []
    def observe(*args):
        nonlocal original
        value = m._observe(*args)
        original = value.version if original is None else original
        version = (*value.version[:6], original[6] + (1000 if clock.now >= 0.25 else 0))
        examined.append((clock.now, version))
        return replace(value, version=version)
    pin = _seal(leaf, clock, observe)
    assert 4.25 <= clock.now < 4.4
    assert pin["version"][:6] == original[:6] and pin["version"][6] == original[6] + 1000
    assert pin["bytes"] == len(leaf[2]) and pin["sha256"] == hashlib.sha256(leaf[2]).hexdigest()
    assert len(examined) >= 86 and len(clock.sleeps) >= 85


@pytest.mark.parametrize("events", ((0.219, 0.648, 3.286), (0.215, 0.911, 2.949), (0.215, 0.969, 2.958)))
def test_observed_delayed_metadata_profiles_require_quiet_after_last_event(leaf, events):
    clock = Clock(); initial = None
    def observe(*args):
        nonlocal initial
        value = m._observe(*args); initial = value.version if initial is None else initial
        count = sum(clock.now >= event for event in events)
        return replace(value, version=(*value.version[:6], initial[6] + count))
    pin = _seal(leaf, clock, observe)
    assert events[-1] + 4.0 <= clock.now < events[-1] + 4.15
    assert pin["version"][:6] == initial[:6] and pin["version"][6] == initial[6] + len(events)


def test_final_independent_probe_ctime_change_restarts_quiet_interval(leaf):
    clock = Clock(); initial = None; previous_time = None; changed = False
    def observe(*args):
        nonlocal initial, previous_time, changed
        value = m._observe(*args); initial = value.version if initial is None else initial
        if clock.now >= 4.0 and previous_time == clock.now: changed = True
        previous_time = clock.now
        return replace(value, version=(*value.version[:6], initial[6] + int(changed)))
    pin = _seal(leaf, clock, observe)
    assert changed and clock.now >= 8.0 and pin["version"][6] == initial[6] + 1


def test_incoherent_named_and_fd_ctime_observation_restarts_quiet_even_if_last_value_repeats(leaf):
    clock = Clock()
    def observe(*args):
        value = m._observe(*args)
        return replace(value, coherent=not (0.24 < clock.now < 0.26))
    _seal(leaf, clock, observe)
    assert clock.now >= 4.25


@pytest.mark.parametrize("field", ("dev", "inode", "mode", "nlink", "size", "mtime", "uid", "gid"))
def test_every_non_ctime_identity_or_custody_change_refuses(leaf, field):
    clock = Clock()
    def observe(*args):
        value = m._observe(*args)
        if clock.now < 0.1: return value
        if field in {"uid", "gid"}: return replace(value, **{field: getattr(value, field) + 1})
        index = {"dev": 0, "inode": 1, "mode": 2, "nlink": 3, "size": 4, "mtime": 5}[field]
        version = list(value.version); version[index] += 1
        return replace(value, version=tuple(version))
    with pytest.raises(m.PublicationSealError, match="publication_seal_changed"):
        _seal(leaf, clock, observe)


def test_content_change_is_never_tolerated_during_settling(leaf):
    clock = Clock(); changed = False
    def observe(*args):
        nonlocal changed
        if clock.now >= 0.1 and not changed:
            original = leaf[3].stat(); altered = leaf[2].replace(b"own", b"bad")
            assert len(altered) == len(leaf[2]) and altered != leaf[2]
            leaf[3].write_bytes(altered)
            os.utime(leaf[3], ns=(original.st_atime_ns, original.st_mtime_ns))
            changed = True
        return m._observe(*args)
    with pytest.raises(m.PublicationSealError, match="publication_seal_changed"):
        _seal(leaf, clock, observe)
    assert changed


@pytest.mark.parametrize("fault", ("mode", "hardlink", "owner"))
def test_private_custody_is_checked_before_any_content_read(leaf, monkeypatch, fault):
    if fault == "mode": leaf[3].chmod(0o644)
    if fault == "hardlink": os.link(leaf[3], leaf[3].with_name("alias.json"))
    if fault == "owner":
        original_stat, original_fstat = m.os.stat, m.os.fstat
        class ForeignOwner:
            def __init__(self, value): self.value, self.st_uid = value, value.st_uid + 1
            def __getattr__(self, name): return getattr(self.value, name)
        def mapped(value): return ForeignOwner(value) if stat.S_ISREG(value.st_mode) else value
        monkeypatch.setattr(m.os, "stat", lambda *a, **k: mapped(original_stat(*a, **k)))
        monkeypatch.setattr(m.os, "fstat", lambda *a, **k: mapped(original_fstat(*a, **k)))
    monkeypatch.setattr(m.os, "read", lambda *a: pytest.fail("publication content read before private custody"))
    with pytest.raises(m.PublicationSealError, match="publication_seal_changed"):
        _seal(leaf, Clock())


def test_symlink_and_private_directory_refuse_before_content_open(leaf, monkeypatch):
    leaf[3].unlink(); leaf[3].symlink_to(leaf[3].with_name("foreign.json"))
    with pytest.raises(m.PublicationSealError, match="publication_seal_refused"):
        _seal(leaf, Clock())
    leaf[3].parent.chmod(0o750)
    monkeypatch.setattr(m.os, "open", lambda *a, **k: pytest.fail("leaf opened under nonprivate parent"))
    with pytest.raises(m.PublicationSealError, match="publication_seal_refused"):
        _seal(leaf, Clock())


def test_continuously_changing_ctime_hits_fixed_deadline(leaf):
    clock = Clock(); count = 0
    def observe(*args):
        nonlocal count
        count += 1; value = m._observe(*args)
        return replace(value, version=(*value.version[:6], value.version[6] + count))
    with pytest.raises(m.PublicationSealError, match="publication_seal_timeout"):
        _seal(leaf, clock, observe)
    assert clock.now == m.MAX_SECONDS and count <= 201


def test_probe_time_is_inside_deadline_and_no_final_pin_is_returned_late(leaf):
    clock = Clock()
    def observe(*args):
        value = m._observe(*args); clock.now += 5.1
        return value
    with pytest.raises(m.PublicationSealError, match="publication_seal_timeout"):
        _seal(leaf, clock, observe)
    assert clock.now > m.MAX_SECONDS


def test_deadline_is_rechecked_after_final_full_hash_probe(leaf):
    clock = Clock(); previous_time = None
    def observe(*args):
        nonlocal previous_time
        value = m._observe(*args)
        if clock.now >= 4.0 and previous_time == clock.now:
            clock.now = m.MAX_SECONDS + 0.1
        previous_time = clock.now
        return value
    with pytest.raises(m.PublicationSealError, match="publication_seal_timeout"):
        _seal(leaf, clock, observe)


@pytest.mark.parametrize("fault", ("nan", "boolean", "backwards", "stalled", "sleep_error"))
def test_invalid_or_nonprogressing_clock_cannot_bypass_bounds(leaf, fault):
    clock = Clock()
    if fault == "nan": clock.clock = lambda: float("nan")
    if fault == "boolean": clock.clock = lambda: True
    if fault == "backwards":
        values = iter((1.0, 0.0)); clock.clock = lambda: next(values)
    if fault == "stalled": clock.sleep = lambda _: None
    if fault == "sleep_error":
        def failed(_): raise RuntimeError("PRIVATE timer error")
        clock.sleep = failed
    with pytest.raises(m.PublicationSealError, match="publication_seal_clock_refused") as caught:
        _seal(leaf, clock)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("primary", (False, True))
def test_close_failure_refuses_success_and_preserves_an_existing_refusal(leaf, monkeypatch, primary):
    opened, attempts = [], []
    original_open, original_close = m.os.open, m.os.close
    def opened_leaf(*args, **kwargs):
        fd = original_open(*args, **kwargs); opened.append(fd); return fd
    def failed_close(fd):
        if fd in opened:
            attempts.append(fd); raise OSError("PRIVATE close error")
        return original_close(fd)
    def observe(*args):
        if primary: raise m.PublicationSealError("publication_seal_changed")
        return m._observe(*args)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(m.os, "open", opened_leaf); patch.setattr(m.os, "close", failed_close)
            expected = "publication_seal_changed" if primary else "publication_seal_cleanup_refused"
            with pytest.raises(m.PublicationSealError, match=expected): _seal(leaf, Clock(), observe)
        assert len(opened) == len(attempts) == 1
    finally:
        for fd in opened: original_close(fd)


def test_public_entry_has_fixed_clock_and_retains_complete_version(leaf):
    pin = m.seal_written(leaf[0], leaf[1], leaf[2])
    assert pin == {"bytes": len(leaf[2]), "sha256": hashlib.sha256(leaf[2]).hexdigest(),
        "version": m.custody._version(leaf[3].stat())}
    with pytest.raises(TypeError): m.seal_written(leaf[0], leaf[1], leaf[2], fixture_clock=Clock())
    assert m.QUIET_SECONDS == 4.0 and m.MAX_SECONDS == 10.0 and m.POLL_SECONDS == 0.05 and m.MAX_POLLS == 256


@pytest.mark.parametrize("fault", ("fd", "name", "empty", "oversized"))
def test_argument_and_raw_size_limits_refuse_before_open(leaf, monkeypatch, fault):
    fd, name, raw = leaf[:3]
    if fault == "fd": fd = True
    if fault == "name": name = "../escape.json"
    if fault == "empty": raw = b""
    if fault == "oversized": raw = b"x" * (m.MAX_BYTES + 1)
    monkeypatch.setattr(m.os, "open", lambda *a, **k: pytest.fail("invalid arguments reached open"))
    with pytest.raises(m.PublicationSealError, match="publication_seal_refused"):
        m._seal(fd, name, raw, clock=Clock().clock, sleep=lambda _: None, observe=m._observe)
