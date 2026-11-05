"""Seal an exclusively written private publication after metadata settles.

The caller closes/fsyncs its creator first and independently binds the returned
non-ctime version fields to that creator. During this bounded pre-seal window,
only ctime may migrate. Once returned, the complete version including ctime is
binding. Local filesystem calls are bounded in bytes; the deadline is checked
between calls rather than claiming that the OS can never stall inside one.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
import re
import stat
import sys
import time

from research import insider_buying_pilot_firstrate_qualification_v1 as source

custody = source.native.custody
MAX_BYTES = 2 * 1024 * 1024
QUIET_SECONDS = 4.0
MAX_SECONDS = 10.0
POLL_SECONDS = 0.05
MAX_POLLS = 256
_CODES = frozenset({"publication_seal_refused", "publication_seal_changed", "publication_seal_timeout",
    "publication_seal_clock_refused", "publication_seal_cleanup_refused"})


class PublicationSealError(ValueError):
    """Finite own refusal codes; no paths, contents or foreign error text."""


def _need(condition, code):
    if not condition:
        raise PublicationSealError(code)


def safe_failure(error):
    return str(error) if type(error) is PublicationSealError and str(error) in _CODES else "publication_seal_refused"


@dataclass(frozen=True)
class _Observation:
    version: tuple
    uid: int
    gid: int
    coherent: bool


def _directory(fd):
    info = os.fstat(fd)
    _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid(), "publication_seal_refused")
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


def _observe(directory_fd, leaf_fd, name, raw, digest):
    """No-follow named/held metadata surrounds an exact bounded content read."""
    before = (os.stat(name, dir_fd=directory_fd, follow_symlinks=False), os.fstat(leaf_fd))
    def private(value):
        _need(stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o600
            and value.st_uid == os.geteuid() and value.st_nlink == 1 and value.st_size == len(raw),
            "publication_seal_changed")
    for value in before: private(value)
    _need(custody._version(before[0])[:6] == custody._version(before[1])[:6]
        and before[0].st_uid == before[1].st_uid and before[0].st_gid == before[1].st_gid,
        "publication_seal_changed")
    os.lseek(leaf_fd, 0, os.SEEK_SET)
    computed, count = hashlib.sha256(), 0
    while True:
        chunk = os.read(leaf_fd, min(65536, len(raw) + 1 - count))
        _need(type(chunk) is bytes and count + len(chunk) <= len(raw), "publication_seal_changed")
        if not chunk:
            break
        _need(chunk == raw[count:count + len(chunk)], "publication_seal_changed")
        count += len(chunk); computed.update(chunk)
    _need(count == len(raw) and computed.hexdigest() == digest, "publication_seal_changed")
    after = (os.fstat(leaf_fd), os.stat(name, dir_fd=directory_fd, follow_symlinks=False))
    values = (*before, *after)
    for value in after: private(value)
    versions = tuple(custody._version(value) for value in values)
    _need(all(version[:6] == versions[0][:6] for version in versions)
        and all(value.st_uid == values[0].st_uid and value.st_gid == values[0].st_gid for value in values),
        "publication_seal_changed")
    return _Observation(versions[-1], values[-1].st_uid, values[-1].st_gid,
        all(version == versions[0] for version in versions))


def _time(clock, previous=None):
    try:
        value = clock()
    except Exception:
        raise PublicationSealError("publication_seal_clock_refused") from None
    _need(type(value) in {int, float} and math.isfinite(value)
        and (previous is None or value >= previous), "publication_seal_clock_refused")
    return value


def _observation(value):
    _need(type(value) is _Observation and type(value.version) is tuple and len(value.version) == 7
        and all(type(v) is int for v in value.version) and type(value.uid) is type(value.gid) is int
        and type(value.coherent) is bool, "publication_seal_refused")
    return value


def _seal(directory_fd, name, raw, *, clock, sleep, observe):
    """Private invented-clock/probe seams; public callers cannot override them."""
    _need(type(directory_fd) is int and directory_fd >= 0 and type(name) is str
        and re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,99}", name) and type(raw) is bytes
        and 0 < len(raw) <= MAX_BYTES and callable(clock) and callable(sleep) and callable(observe),
        "publication_seal_refused")
    leaf_fd = None
    try:
        started = last_time = _time(clock)
        deadline = started + MAX_SECONDS
        parent = _directory(directory_fd)
        leaf_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        digest = hashlib.sha256(raw).hexdigest()
        initial = _observation(observe(directory_fd, leaf_fd, name, raw, digest))
        last_time = _time(clock, last_time)
        _need(last_time < deadline, "publication_seal_timeout")
        anchor = initial.version[:6], initial.uid, initial.gid
        last_version, quiet_since = initial.version, last_time
        for _ in range(MAX_POLLS):
            now = _time(clock, last_time); last_time = now
            _need(now < deadline, "publication_seal_timeout")
            try:
                sleep(min(POLL_SECONDS, deadline - now))
            except Exception:
                raise PublicationSealError("publication_seal_clock_refused") from None
            last_time = _time(clock, last_time)
            _need(last_time < deadline, "publication_seal_timeout")
            _need(_directory(directory_fd) == parent, "publication_seal_changed")
            current = _observation(observe(directory_fd, leaf_fd, name, raw, digest))
            last_time = _time(clock, last_time)
            _need(last_time < deadline, "publication_seal_timeout")
            _need((current.version[:6], current.uid, current.gid) == anchor, "publication_seal_changed")
            if not current.coherent or current.version != last_version:
                last_version, quiet_since = current.version, last_time
                continue
            if last_time - quiet_since < QUIET_SECONDS:
                continue
            # The final full hash and named/FD comparison are independent of
            # the observation that completed the quiet interval.
            final = _observation(observe(directory_fd, leaf_fd, name, raw, digest))
            last_time = _time(clock, last_time)
            _need(last_time < deadline, "publication_seal_timeout")
            _need(_directory(directory_fd) == parent
                and (final.version[:6], final.uid, final.gid) == anchor, "publication_seal_changed")
            if not final.coherent or final.version != last_version:
                last_version, quiet_since = final.version, last_time
                continue
            return {"bytes": len(raw), "sha256": digest, "version": final.version}
        raise PublicationSealError("publication_seal_clock_refused")
    except PublicationSealError:
        raise
    except (OSError, ValueError, TypeError, OverflowError):
        raise PublicationSealError("publication_seal_refused") from None
    finally:
        if leaf_fd is not None:
            primary = sys.exc_info()[0] is not None
            try:
                os.close(leaf_fd)
            except OSError:
                # Preserve an already-active finite refusal over cleanup.
                if not primary:
                    raise PublicationSealError("publication_seal_cleanup_refused") from None


def seal_written(directory_fd, name, raw):
    """Fixed 4s quiet / 10s deadline policy, after creator close and fsync."""
    return _seal(directory_fd, name, raw, clock=time.monotonic, sleep=time.sleep, observe=_observe)
