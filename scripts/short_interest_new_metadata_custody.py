"""Creator-only custody for one fresh, bounded NONCLAIM metadata file.

This is not an existing-file loader or recovery from a custody failure. Only
ctime may evolve before the one seal; afterwards every original HeldFiles
predicate stays strict. No source, provider, credential or admission API exists.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import capture_short_interest_native_anchor_cache as cache
from scripts import short_interest_recovery_diagnostics as diagnostics
from scripts.continue_short_interest_native_identity import _OwnedOutput

MAXIMUM_BYTES = 1024
MAXIMUM_SAMPLES = 16
SAMPLE_SECONDS = 0.25
QUIET_SECONDS = 1.0
MAXIMUM_SECONDS = 8.0
_FIELDS = ("dev", "ino", "uid", "mode", "nlink", "size", "mtime_ns", "ctime_ns")
_CODES = frozenset("""
new_metadata_factory_required new_metadata_binding_changed new_metadata_state_changed
new_metadata_owned_output_changed new_metadata_arguments_refused new_metadata_closed
new_metadata_readonly_provenance_refused new_metadata_original_inode_or_protection_changed
new_metadata_original_size_or_mtime_changed new_metadata_original_bytes_changed
new_metadata_stamp_changed_after_seal new_metadata_write_refused new_metadata_write_progress_changed
new_metadata_clock_refused new_metadata_window_exhausted new_metadata_samples_exhausted
new_metadata_seal_once_required new_metadata_sealed_required new_metadata_held_stamp_changed
new_metadata_read_bound_refused new_metadata_not_sealed_before_close
""".split())


class NewMetadataRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise NewMetadataRefusal("REFUSED: " + code)


def failure_summary(error):
    """Exact own class/literal catalogue; never format arbitrary exceptions."""
    if type(error) is not NewMetadataRefusal:
        return diagnostics.fixed_local_failure(error)
    arguments = BaseException.args.__get__(error, BaseException)
    code = None
    if (type(arguments) is tuple and len(arguments) == 1 and type(arguments[0]) is str
        and len(arguments[0]) <= 256 and arguments[0].startswith("REFUSED: ")):
        candidate = arguments[0][len("REFUSED: "):]
        if candidate in _CODES:
            code = candidate
    return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _valid_tick(value):
    return type(value) in (int, float) and 0 <= value <= 2 ** 53


def _protected(info, original):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        and _stamp(info)[:5] == original[:5], "new_metadata_original_inode_or_protection_changed")


def _read_expected(fd, raw):
    os.lseek(fd, 0, os.SEEK_SET)
    parts, length = [], 0
    for unused in range(MAXIMUM_BYTES + 1):
        part = os.read(fd, MAXIMUM_BYTES + 1 - length)
        if not part:
            break
        parts.append(part); length += len(part)
        require(length <= MAXIMUM_BYTES, "new_metadata_original_bytes_changed")
    observed = b"".join(parts)
    require(observed == raw and hash_bytes(observed) == hash_bytes(raw), "new_metadata_original_bytes_changed")
    return observed


class NewMetadataCustody:
    """Factory-sealed capability; paths and original inode stamps stay private."""
    __slots__ = ("_anchor", "_identity", "_state", "_state_identity", "_failed", "_held_identity")

    def __init__(self):
        raise NewMetadataRefusal("REFUSED: new_metadata_factory_required")

    def _latch_refused(self):
        # Never trust a replaced _anchor or _state to locate original custody.
        if type(self) is not NewMetadataCustody:
            return
        try:
            original = object.__getattribute__(self, "_state_identity")
        except AttributeError:
            return
        object.__setattr__(self, "_failed", True)
        if type(original) is dict:
            original["phase"] = "REFUSED"

    def _guard(self):
        require(type(self) is NewMetadataCustody, "new_metadata_binding_changed")
        try:
            anchor, identity, state, original_state, failed, held_identity = (object.__getattribute__(self, name)
                for name in ("_anchor", "_identity", "_state", "_state_identity", "_failed", "_held_identity"))
        except AttributeError:
            raise NewMetadataRefusal("REFUSED: new_metadata_binding_changed") from None
        require(anchor is identity and type(anchor) is tuple and len(anchor) == 15
            and type(failed) is bool, "new_metadata_binding_changed")
        require(state is original_state and type(state) is dict
            and all(type(key) is str for key in state) and set(state) == {
            "phase", "closed", "attempted", "held_attempted", "held", "seal_stamp", "samples",
            "ctime_changes", "last_ctime", "last_tick"} and type(state["phase"]) is str
            and state["phase"] in {"UNSEALED", "SEALING", "SEALED", "REFUSED", "CLOSED"}
            and all(type(state[name]) is bool for name in ("closed", "attempted", "held_attempted"))
            and type(state["samples"]) is list and len(state["samples"]) <= MAXIMUM_SAMPLES
            and type(state["ctime_changes"]) is int and 0 <= state["ctime_changes"] <= 4 * MAXIMUM_SAMPLES
            and type(state["last_ctime"]) is int and type(state["last_tick"]) in (int, float)
            and _valid_tick(state["last_tick"]) and (failed is False or state["phase"] == "REFUSED")
            and state["held"] is held_identity
            and (held_identity is None or type(held_identity) is cache.HeldFiles),
            "new_metadata_state_changed")
        for ordinal, row in enumerate(state["samples"], 1):
            require(type(row) is dict and all(type(key) is str for key in row)
                and set(row) == {"sample", "event", "changed_fields", "ctime_transitions",
                "full_stamp_sha256", "internally_stable", "quiet_milliseconds"}
                and type(row["sample"]) is int and row["sample"] == ordinal
                and type(row["event"]) is str and row["event"] == "UNSEALED_original_byte_observation"
                and type(row["changed_fields"]) is list and len(row["changed_fields"]) <= 1
                and all(type(field) is str and field == "ctime_ns" for field in row["changed_fields"])
                and type(row["ctime_transitions"]) is int and 0 <= row["ctime_transitions"] <= 4
                and type(row["full_stamp_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["full_stamp_sha256"])
                and type(row["internally_stable"]) is bool and type(row["quiet_milliseconds"]) is int
                and 0 <= row["quiet_milliseconds"] <= 8000, "new_metadata_state_changed")
        return state

    def _tick(self):
        state = self._guard()
        value = self._anchor[10]()
        require(_valid_tick(value)
            and value >= state["last_tick"], "new_metadata_clock_refused")
        require(value - self._anchor[13] <= MAXIMUM_SECONDS, "new_metadata_window_exhausted")
        state["last_tick"] = value
        return value

    def _owned(self):
        owned, original_anchor, unused_name, unused_raw, unused_hash, unused_parent, unused_dirfd, unused_fd, unused_creation, boundary, unused_clock, unused_sleep, unused_path, unused_began, unused_last = self._anchor
        require(type(owned) is _OwnedOutput and owned._anchor is original_anchor,
            "new_metadata_owned_output_changed")
        for check in (owned.check, boundary, owned.check):
            check()
            if self._state["phase"] in {"UNSEALED", "SEALING"}: self._tick()

    def _pair(self):
        unused_owned, unused_anchor, name, unused_raw, unused_hash, unused_parent, dirfd, fd, creation, unused_boundary, unused_clock, unused_sleep, unused_path, unused_began, unused_last = self._anchor
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "new_metadata_readonly_provenance_refused")
        observed = os.fstat(fd), os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        for info in observed:
            _protected(info, creation)
            require(_stamp(info)[5:7] == creation[5:7], "new_metadata_original_size_or_mtime_changed")
        return tuple(_stamp(info) for info in observed)

    def _strict(self):
        state = self._guard()
        require(state["closed"] is False, "new_metadata_closed")
        require(state["phase"] in {"SEALING", "SEALED"} and type(state["seal_stamp"]) is tuple,
            "new_metadata_sealed_required")
        self._owned()
        for stamp in self._pair():
            require(stamp == state["seal_stamp"], "new_metadata_stamp_changed_after_seal")
        _read_expected(self._anchor[7], self._anchor[3])
        for stamp in self._pair():
            require(stamp == state["seal_stamp"], "new_metadata_stamp_changed_after_seal")
        self._owned()

    def seal_once(self):
        state = None
        quiet_at, prior_stamp = None, None
        try:
            state = self._guard()
            sleep = self._anchor[11]
            require(state["closed"] is False, "new_metadata_closed")
            require(state["phase"] == "UNSEALED" and state["attempted"] is False,
                "new_metadata_seal_once_required")
            state["attempted"] = True
            self._tick()
            for ordinal in range(1, MAXIMUM_SAMPLES + 1):
                if ordinal > 1:
                    sleep(SAMPLE_SECONDS); self._tick()
                self._owned(); self._tick()
                before = self._pair()
                _read_expected(self._anchor[7], self._anchor[3])
                after = self._pair()
                self._owned(); observed_at = self._tick()
                stamps = (*before, *after)
                transitions = 0
                for stamp in stamps:
                    if stamp[-1] != state["last_ctime"]:
                        transitions += 1; state["last_ctime"] = stamp[-1]
                state["ctime_changes"] += transitions
                candidate = stamps[-1]
                internally_stable = all(stamp == candidate for stamp in stamps)
                if not internally_stable or candidate != prior_stamp:
                    quiet_at = observed_at if internally_stable else None
                elif quiet_at is None:
                    quiet_at = observed_at
                quiet_for = 0 if quiet_at is None else observed_at - quiet_at
                state["samples"].append({"sample": ordinal, "event": "UNSEALED_original_byte_observation",
                    "changed_fields": ["ctime_ns"] if transitions else [], "ctime_transitions": transitions,
                    "full_stamp_sha256": hash_payload(list(candidate)), "internally_stable": internally_stable,
                    "quiet_milliseconds": min(8000, max(0, int(quiet_for * 1000)))})
                prior_stamp = candidate
                if internally_stable and quiet_for >= QUIET_SECONDS:
                    state["seal_stamp"] = candidate
                    state["phase"] = "SEALING"
                    state["held_attempted"] = True
                    # Exactly one untouched original constructor. Any failure
                    # is terminal; no stamp is ever chosen again afterwards.
                    held = cache.HeldFiles((self._anchor[12],), protected=True, boundary=self._strict)
                    self._held_identity = held
                    state["held"] = held
                    expected = candidate[0], candidate[1], candidate[5], candidate[6], candidate[7]
                    require(held._anchor[1][0][3] == expected and held._anchor[1][0][4:6] == candidate[2:4],
                        "new_metadata_held_stamp_changed")
                    state["phase"] = "SEALED"
                    self.check(); self._tick()
                    return self
            raise NewMetadataRefusal("REFUSED: new_metadata_samples_exhausted")
        except BaseException:
            self._latch_refused()
            raise

    def check(self):
        try:
            state = self._guard()
            require(state["phase"] == "SEALED", "new_metadata_sealed_required")
            self._strict()
            require(type(state["held"]) is cache.HeldFiles, "new_metadata_state_changed")
            state["held"].check()
            require(state["held"].read(self._anchor[12], MAXIMUM_BYTES) == self._anchor[3],
                "new_metadata_original_bytes_changed")
            self._strict()
        except BaseException:
            self._latch_refused()
            raise

    def read(self, maximum=MAXIMUM_BYTES):
        try:
            self._guard()
            require(type(maximum) is int and len(self._anchor[3]) <= maximum <= MAXIMUM_BYTES,
                "new_metadata_read_bound_refused")
            self.check()
            return self._anchor[3]
        except BaseException:
            self._latch_refused()
            raise

    def observation(self):
        try:
            return self._observation()
        except BaseException:
            self._latch_refused()
            raise

    def _observation(self):
        state = self._guard()
        value = {"schema": "si-new-owned-metadata-custody-observation-v1", "phase": state["phase"],
            "closed": state["closed"], "bytes": len(self._anchor[3]), "expected_raw_sha256": self._anchor[4],
            "creation_stamp_sha256": hash_payload(list(self._anchor[8])),
            "creation_observations": ["O_EXCL_original_inode", "postwrite_fsync_original_bytes_verified",
                "readonly_opened_and_original_inode_verified_before_writer_close", "writer_closed_before_UNSEALED"],
            "seal_stamp_sha256": None if state["seal_stamp"] is None else hash_payload(list(state["seal_stamp"])),
            "seal_attempted": state["attempted"], "original_HeldFiles_attempted": state["held_attempted"],
            "preseal_ctime_changes": state["ctime_changes"], "samples": state["samples"],
            "authority": {"new_metadata_only": True, "is_capture_claim": False, "provider_HTTP": 0,
                "credential_reads": 0, "source_START_debits": 0, "source_admitted": False,
                "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}}
        return json.loads(canonical_json(value))

    def _close(self, *, validate):
        original = object.__getattribute__(self, "_state_identity")
        original_held = object.__getattribute__(self, "_held_identity")
        try:
            state = self._guard()
            if state["closed"]: return
            if validate:
                require(state["phase"] == "SEALED", "new_metadata_not_sealed_before_close")
                self.check()
        except BaseException:
            self._latch_refused()
            raise
        finally:
            try:
                if type(original_held) is cache.HeldFiles: original_held.close()
            except BaseException:
                self._latch_refused()
                raise
            finally:
                original["closed"] = True
                if original["phase"] != "REFUSED": original["phase"] = "CLOSED"


@contextmanager
def prepare_owned_metadata(owned, name, raw, *, parent=True, boundary,
                           monotonic=time.monotonic, sleep=time.sleep):
    """Create a NEW inode, yield UNSEALED capability, preserve its bytes forever."""
    require(type(owned) is _OwnedOutput and type(name) is str
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", name) is not None
        and name not in {".", ".."} and type(raw) is bytes and 0 < len(raw) <= MAXIMUM_BYTES
        and type(parent) is bool and all(callable(value) for value in (boundary, monotonic, sleep)),
        "new_metadata_arguments_refused")
    require(MAXIMUM_BYTES == 1024 and MAXIMUM_SAMPLES == 16 and SAMPLE_SECONDS == 0.25
        and QUIET_SECONDS == 1.0 and MAXIMUM_SECONDS == 8.0, "new_metadata_arguments_refused")
    began = monotonic()
    require(_valid_tick(began), "new_metadata_clock_refused")
    previous = began
    def tick():
        nonlocal previous
        value = monotonic()
        require(_valid_tick(value) and value >= previous,
            "new_metadata_clock_refused")
        require(value - began <= MAXIMUM_SECONDS, "new_metadata_window_exhausted")
        previous = value
        return value
    for check in (owned.check, boundary, owned.check): check(); tick()
    original_owned = owned._anchor
    dirfd = original_owned[3 if parent else 2]
    path = original_owned[1 if parent else 0] / name
    writer, reader, custody, lifetime_reader = None, None, None, None
    try:
        writer = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=dirfd)
        tick(); os.fchmod(writer, 0o600); tick()
        created = _stamp(os.fstat(writer))
        def creation_check(offset):
            for check in (owned.check, boundary, owned.check): check(); tick()
            require(owned._anchor is original_owned, "new_metadata_owned_output_changed")
            for info in (os.fstat(writer), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
                _protected(info, created)
                require(info.st_size == offset, "new_metadata_write_progress_changed")
        offset = 0
        while offset < len(raw):
            creation_check(offset)
            size = os.write(writer, memoryview(raw)[offset:])
            tick()
            require(type(size) is int and size > 0, "new_metadata_write_refused")
            offset += size
        os.fsync(writer); tick(); os.fsync(dirfd); tick(); creation_check(len(raw))
        creation = _stamp(os.fstat(writer))
        _read_expected(writer, raw); tick()
        reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        tick()
        require(fcntl.fcntl(reader, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "new_metadata_readonly_provenance_refused")
        for info in (os.fstat(reader), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
            _protected(info, creation)
            require(_stamp(info)[5:7] == creation[5:7], "new_metadata_readonly_provenance_refused")
        _read_expected(reader, raw); tick()
        os.close(writer); writer = None; tick()
        custody = object.__new__(NewMetadataCustody)
        anchor = (owned, original_owned, name, raw, hash_bytes(raw), parent, dirfd, reader,
            creation, boundary, monotonic, sleep, path, began, previous)
        custody._anchor = custody._identity = anchor
        custody._failed = False
        custody._held_identity = None
        state = {"phase": "UNSEALED", "closed": False, "attempted": False,
            "held_attempted": False, "held": None, "seal_stamp": None, "samples": [],
            "ctime_changes": 0, "last_ctime": creation[-1], "last_tick": previous}
        custody._state = custody._state_identity = state
        custody._guard()
        custody._owned(); custody._pair(); _read_expected(reader, raw); tick(); custody._pair(); custody._owned()
        lifetime_reader, reader = reader, None
        try:
            yield custody
        except BaseException:
            custody._latch_refused()
            custody._close(validate=False)
            raise
        else:
            custody._close(validate=True)
    finally:
        if writer is not None: os.close(writer)
        if reader is not None: os.close(reader)
        if lifetime_reader is not None: os.close(lifetime_reader)
