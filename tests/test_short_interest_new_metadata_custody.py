"""Fresh fabricated NONCLAIM files only; no original evidence or provider I/O."""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
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

from data.hashing import canonical_json, hash_bytes

from scripts import short_interest_new_metadata_custody as custody


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


class Clock:
    def __init__(self): self.now, self.sleeps, self.hook = 0.0, [], lambda: None
    def __call__(self): return self.now
    def sleep(self, seconds): self.sleeps.append(seconds); self.now += seconds; self.hook()


class Harness:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.output = tmp_path / "fresh-run"; self.output.mkdir(mode=0o700)
        self.owned = custody._OwnedOutput(self.output, lambda: None)
        self.clock, self.name = Clock(), "fresh-nonclaim.private.json"
        self.raw = b'{"is_capture_claim":false,"safe":"fabricated"}'
        self.boundary_hook = lambda: None
        self.boundary = lambda: self.boundary_hook()
    def prepare(self, **changes):
        return custody.prepare_owned_metadata(self.owned, changes.pop("name", self.name),
            changes.pop("raw", self.raw), boundary=changes.pop("boundary", self.boundary),
            monotonic=changes.pop("monotonic", self.clock), sleep=changes.pop("sleep", self.clock.sleep), **changes)
    @property
    def path(self): return self.root / self.name
    def close(self): self.owned.close()


@pytest.fixture
def h(tmp_path):
    value = Harness(tmp_path)
    try: yield value
    finally: value.close()


def test_one_fresh_inode_seals_once_after_quiet_and_keeps_original_readonly_fd(h):
    with h.prepare() as value:
        original = value.observation()
        assert original["phase"] == "UNSEALED" and not original["original_HeldFiles_attempted"]
        readonly = value._anchor[7]
        assert fcntl.fcntl(readonly, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        value.seal_once(); value.check()
        assert value.read() == h.raw and value.read(len(h.raw)) == h.raw
        observed = value.observation()
        assert observed["creation_stamp_sha256"] == original["creation_stamp_sha256"]
        assert observed["seal_stamp_sha256"] == original["creation_stamp_sha256"]
        assert len(observed["samples"]) == 5 and h.clock.sleeps == [0.25] * 4
        assert observed["samples"][-1]["quiet_milliseconds"] >= 1000
        assert observed["authority"]["source_admitted"] is False
        assert observed["authority"]["provider_HTTP"] == observed["authority"]["credential_reads"] == 0
        observed["samples"][0]["event"] = "SECRET"
        assert "SECRET" not in canonical_json(value.observation())
    assert value.observation()["closed"] is True and value.observation()["phase"] == "CLOSED"
    assert h.path.read_bytes() == h.raw
    with pytest.raises(OSError): os.fstat(readonly)


def test_ctime_only_may_evolve_before_first_seal_without_rewriting_creation(h):
    changed = []
    def mutate():
        if not changed:
            changed.append(True); h.path.chmod(0o600)
    h.clock.hook = mutate
    with h.prepare() as value:
        creation = value.observation()["creation_stamp_sha256"]
        value.seal_once()
        observed = value.observation()
        assert observed["creation_stamp_sha256"] == creation != observed["seal_stamp_sha256"]
        assert observed["preseal_ctime_changes"] >= 1
        assert any(row["changed_fields"] == ["ctime_ns"] for row in observed["samples"])
        assert len(observed["samples"]) >= 6 and value.read() == h.raw


@pytest.mark.parametrize("mutation", ["mode", "size", "mtime", "inode", "nlink", "bytes_same_size"])
def test_nonctime_changes_refuse_even_before_first_seal(h, mutation):
    with pytest.raises((custody.NewMetadataRefusal, custody.cache.contract.AnchorCacheRefusal)):
        with h.prepare() as value:
            before = h.path.stat()
            if mutation == "mode": h.path.chmod(0o644)
            elif mutation == "size": h.path.write_bytes(h.raw + b"extra")
            elif mutation == "mtime": os.utime(h.path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000))
            elif mutation == "inode":
                h.path.rename(h.root / "retained-original"); h.path.write_bytes(h.raw); h.path.chmod(0o600)
            elif mutation == "nlink": os.link(h.path, h.root / "retained-link")
            else:
                h.path.write_bytes(h.raw.replace(b"false", b"False"))
                os.utime(h.path, ns=(before.st_atime_ns, before.st_mtime_ns))
            value.seal_once()
    assert value.observation()["phase"] == "REFUSED"
    assert not value.observation()["original_HeldFiles_attempted"]


def test_after_seal_ctime_change_is_terminal_without_rebaseline_or_second_constructor(h, monkeypatch):
    calls = []
    original = custody.cache.HeldFiles.__init__
    def init(held, *args, **kwargs): calls.append(None); return original(held, *args, **kwargs)
    monkeypatch.setattr(custody.cache.HeldFiles, "__init__", init)
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            value.seal_once(); chosen = value.observation()["seal_stamp_sha256"]
            h.path.chmod(0o600)
            with pytest.raises(custody.NewMetadataRefusal): value.check()
            assert value.observation()["phase"] == "REFUSED"
            with pytest.raises(custody.NewMetadataRefusal): value.seal_once()
            assert value.observation()["seal_stamp_sha256"] == chosen
    assert len(calls) == 1 and h.path.read_bytes() == h.raw


def test_choice_to_original_constructor_gap_cannot_capture_a_newer_stamp(h, monkeypatch):
    original = custody.cache.HeldFiles.__init__; calls = []
    def init(held, *args, **kwargs):
        calls.append(None); h.path.chmod(0o600)
        return original(held, *args, **kwargs)
    monkeypatch.setattr(custody.cache.HeldFiles, "__init__", init)
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value: value.seal_once()
    assert value.observation()["phase"] == "REFUSED" and len(calls) == 1
    assert value.observation()["original_HeldFiles_attempted"] is True


def test_original_constructor_failure_is_terminal_and_never_reconstructed(h, monkeypatch):
    calls = []
    def init(held, *args, **kwargs):
        calls.append(None)
        raise custody.cache.contract.AnchorCacheRefusal("held_custody_file_changed")
    monkeypatch.setattr(custody.cache.HeldFiles, "__init__", init)
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            with pytest.raises(custody.cache.contract.AnchorCacheRefusal): value.seal_once()
            with pytest.raises(custody.NewMetadataRefusal): value.seal_once()
    assert len(calls) == 1 and value.observation()["phase"] == "REFUSED"


def test_existing_file_can_never_be_adopted_even_when_bytes_match(h):
    h.path.write_bytes(h.raw); h.path.chmod(0o600); before = h.path.stat()
    with pytest.raises(FileExistsError):
        with h.prepare(): pytest.fail("existing inode adopted")
    assert h.path.read_bytes() == h.raw and h.path.stat().st_ino == before.st_ino


@pytest.mark.parametrize("name", ["../private", "/tmp/private", "x/y", "..", ".", "", "a\\b", 5])
def test_no_other_path_or_coerced_name(h, name):
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare(name=name): pytest.fail("invalid path accepted")
    assert not h.path.exists()


@pytest.mark.parametrize("raw", [b"", b"x" * 1025, "private text", bytearray(b"metadata")])
def test_only_original_bounded_byte_type(h, raw):
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare(raw=raw): pytest.fail("unbounded or coerced raw accepted")
    assert not h.path.exists()


@pytest.mark.parametrize("where", ["before_create", "after_write", "caller_delay", "during_guards"])
def test_eight_second_clock_covers_entire_creation_and_never_resets_at_seal(h, monkeypatch, where):
    if where == "before_create": h.boundary = lambda: setattr(h.clock, "now", 9.0)
    elif where == "after_write":
        original = custody.os.write
        def write(fd, raw):
            value = original(fd, raw); h.clock.now = 9.0; return value
        monkeypatch.setattr(custody.os, "write", write)
    with pytest.raises(custody.NewMetadataRefusal, match="window_exhausted"):
        with h.prepare() as value:
            if where == "caller_delay": h.clock.now = 9.0
            if where == "during_guards":
                h.boundary_hook = lambda: setattr(h.clock, "now", 9.0)
            value.seal_once()
    if where == "before_create": assert not h.path.exists()
    else: assert h.path.exists()


def test_continuous_preseal_ctime_activity_exhausts_fixed_samples_without_HeldFiles(h):
    h.clock.hook = lambda: h.path.chmod(0o600)
    with pytest.raises(custody.NewMetadataRefusal, match="samples_exhausted"):
        with h.prepare() as value: value.seal_once()
    observed = value.observation()
    assert len(observed["samples"]) == 16 and not observed["original_HeldFiles_attempted"]
    assert all(seconds == 0.25 for seconds in h.clock.sleeps)


@pytest.mark.parametrize("operation", ["invalid_read", "second_seal", "unsealed_read"])
def test_explicit_capability_operation_error_is_permanent(h, operation):
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            if operation != "unsealed_read": value.seal_once()
            with pytest.raises(custody.NewMetadataRefusal):
                value.read(Path("not-a-path-api")) if operation == "invalid_read" else value.seal_once() if operation == "second_seal" else value.read()
            assert value.observation()["phase"] == "REFUSED"
            with pytest.raises(custody.NewMetadataRefusal): value.seal_once()


def test_readonly_open_precedes_last_writer_close_and_all_descriptors_close(h, monkeypatch):
    live, operations = set(), []
    original_open, original_close = custody.os.open, custody.os.close
    def open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        live.add(fd); operations.append(("open", flags & os.O_ACCMODE, fd)); return fd
    def close(fd):
        operations.append(("close", None, fd)); live.discard(fd); return original_close(fd)
    monkeypatch.setattr(custody.os, "open", open); monkeypatch.setattr(custody.os, "close", close)
    with h.prepare() as value:
        reader = value._anchor[7]
        writer = operations[0][2]
        assert operations.index(("open", os.O_RDONLY, reader)) < operations.index(("close", None, writer))
        value.seal_once()
    assert not live


def test_exception_early_exit_preserves_file_and_closes_original_fd(h):
    with pytest.raises(RuntimeError, match="fabricated"):
        with h.prepare() as value:
            reader = value._anchor[7]
            raise RuntimeError("fabricated")
    assert value.observation()["phase"] == "REFUSED" and h.path.read_bytes() == h.raw
    with pytest.raises(OSError): os.fstat(reader)


def test_normal_exit_without_seal_refuses_and_closes_fd(h):
    with pytest.raises(custody.NewMetadataRefusal, match="not_sealed_before_close"):
        with h.prepare() as value: reader = value._anchor[7]
    with pytest.raises(OSError): os.fstat(reader)
    assert h.path.read_bytes() == h.raw


def test_safe_literal_failure_catalogue_and_hostile_properties():
    class Hostile:
        def __str__(self): pytest.fail("hostile formatting")
        def __eq__(self, other): pytest.fail("hostile equality")
    class Text(str):
        def startswith(self, *args): pytest.fail("hostile method")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile exception property")
    for error in (custody.NewMetadataRefusal(Hostile()), custody.NewMetadataRefusal(Text("REFUSED: SECRET")), Error()):
        value = custody.failure_summary(error)
        assert value["contract_code"] is None and "SECRET" not in canonical_json(value)
    assert custody.failure_summary(custody.NewMetadataRefusal("REFUSED: new_metadata_seal_once_required"))["contract_code"] == "new_metadata_seal_once_required"
    assert custody.failure_summary(custody.NewMetadataRefusal("REFUSED: SECRET"))["contract_code"] is None
    assert custody.failure_summary(OSError(errno.ENOSPC, "SECRET"))["errno_name"] == "ENOSPC"


def test_factory_and_reflection_do_not_make_another_path_reader(h):
    with pytest.raises(custody.NewMetadataRefusal): custody.NewMetadataCustody()
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            value.seal_once()
            original = value._identity
            object.__setattr__(value, "_anchor", tuple(list(original)))
            with pytest.raises(custody.NewMetadataRefusal, match="binding_changed"): value.read()
            object.__setattr__(value, "_anchor", original)
            assert value.observation()["phase"] == "REFUSED"
            for operation in (value.read, value.check, value.seal_once):
                with pytest.raises(custody.NewMetadataRefusal): operation()


def test_unrestored_binding_failure_still_closes_original_retained_descriptors(h, monkeypatch):
    live = set()
    original_open, original_close = custody.os.open, custody.os.close
    def open(*args, **kwargs):
        fd = original_open(*args, **kwargs); live.add(fd); return fd
    def close(fd): live.discard(fd); return original_close(fd)
    monkeypatch.setattr(custody.os, "open", open); monkeypatch.setattr(custody.os, "close", close)
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            value.seal_once()
            object.__setattr__(value, "_anchor", ())
            value.read()
    assert not live and h.path.read_bytes() == h.raw


@pytest.mark.parametrize("clock", [lambda: float("nan"), lambda: float("inf"), lambda: -1,
    lambda: 10 ** 1000, lambda: True])
def test_invalid_initial_clock_is_fixed_refusal_before_creation(h, clock):
    with pytest.raises(custody.NewMetadataRefusal, match="clock_refused"):
        with h.prepare(monotonic=clock): pytest.fail("bad clock accepted")
    assert not h.path.exists()


def test_backdated_clock_after_creation_cannot_seal(h):
    h.clock.now = 1.0
    with pytest.raises(custody.NewMetadataRefusal, match="clock_refused"):
        with h.prepare() as value:
            h.clock.now = 0
            value.seal_once()
    assert not value.observation()["original_HeldFiles_attempted"]


def test_parent_false_is_still_bound_to_owned_original_directory(h):
    with h.prepare(parent=False) as value:
        value.seal_once(); assert value.read() == h.raw
    assert not h.path.exists() and (h.output / h.name).read_bytes() == h.raw


def test_forged_or_subclass_capability_and_owned_types_cannot_be_used(h):
    class Hostile:
        def __getattribute__(self, name): pytest.fail("hostile owned property")
    with pytest.raises(custody.NewMetadataRefusal):
        with custody.prepare_owned_metadata(Hostile(), h.name, h.raw, boundary=lambda: None): pass
    empty = object.__new__(custody.NewMetadataCustody)
    with pytest.raises(custody.NewMetadataRefusal, match="binding_changed"): empty.read()
    class Child(custody.NewMetadataCustody): pass
    child = object.__new__(Child)
    with pytest.raises(custody.NewMetadataRefusal): child.read()
    assert not h.path.exists()


def test_hostile_reflected_sample_row_cannot_be_serialized_or_restored(h):
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            value.seal_once()
            original = value._state_identity["samples"][0].copy()
            value._state_identity["samples"][0]["event"] = "SECRET_reflected"
            with pytest.raises(custody.NewMetadataRefusal): value.observation()
            value._state_identity["samples"][0] = original
            assert value.observation()["phase"] == "REFUSED"
            with pytest.raises(custody.NewMetadataRefusal): value.read()


@pytest.mark.parametrize("field", ["st_uid", "st_dev", "st_mode"])
def test_nonctime_provenance_predicates_remain_strict_before_seal(h, monkeypatch, field):
    with pytest.raises(custody.NewMetadataRefusal):
        with h.prepare() as value:
            original_fstat = custody.os.fstat
            reader = value._anchor[7]
            def fstat(fd):
                info = original_fstat(fd)
                if fd != reader: return info
                fields = {name: getattr(info, name) for name in ("st_dev", "st_ino", "st_uid", "st_mode",
                    "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")}
                fields[field] = fields[field] + 1 if field != "st_mode" else 0o010600
                return type("FabricatedStat", (), fields)()
            monkeypatch.setattr(custody.os, "fstat", fstat)
            value.seal_once()
