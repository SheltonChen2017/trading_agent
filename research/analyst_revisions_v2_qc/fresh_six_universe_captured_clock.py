"""Host-only successor projection for one captured decision clock.

R279 A2's source reads ``algorithm.time`` once in the scheduled callback and
again inside persistence.  LEAN may advance that property between reads even
within one callback.  This projector authenticates the exact frozen R279 A2
two-file source, then creates a prospective source pair in which the callback
captures one firing instant and passes that same value through date selection
and persistence.  No frozen R247/R279 source, manifest, or run is changed.

This module has no QC client, credentials, transport, candidate, launch plan,
or action on import.  Its sole permitted input boundary is R279 A2's already
authenticated source loader.
"""

from __future__ import annotations

import hashlib
import json

from .fresh_six_universe_clock_successor_a2 import (
    RUNTIME_SHA256 as _DECLARED_PARENT_RUNTIME_SHA256,
    SOURCE_MANIFEST_SHA256 as _DECLARED_PARENT_MANIFEST_SHA256,
    _files as _load_authenticated_parent_source,
)


class FreshCapturedClockProjectionError(ValueError):
    """The parent source, transform anchors, or projected bytes changed."""


SCHEMA = "arv2-fresh-six-universe-captured-clock-source-projection-v1"
PARENT_SOURCE_MANIFEST_SHA256 = (
    "440b6e7ccfa561668e2ce40a8e737d4ab2c1529e40cd149f1439b382004755f6"
)
PARENT_RUNTIME_SHA256 = (
    "6b2d2f4d03d2b7e749c112f053f45685a21b4f9f69359130ac64551b1792047a"
)
PARENT_MAIN_SHA256 = (
    "39d319efdcf29c766ef091ba647d576b6c6bc1d4fc4e78629b768a72cbc47232"
)
RUNTIME_SHA256 = "05b1efcdee316c3183a38cdc5fb9a99f3c57494b5deb0bfbc80dca9be477bc98"
MAIN_SHA256 = "277803f84faa3deaab76946c28f765f0a424de76aab9404de847319274b0e02e"
SOURCE_MANIFEST_SHA256 = (
    "77f6a80901f867f822b7b9913679a944c3755e1fea87a6777ff2e50123652ea5"
)
MAX_SOURCE_FILE_BYTES = 64_000

_PATHS = ("fresh_six_universe_snapshot.py", "main.py")
_OLD_CLOCK = b'''def _callback_time(algorithm):
    value = algorithm.time
    # QC's Python bridge may supply a datetime subtype. Other completed lane
    # runtimes accept that shape; exact-type equality rejected it at initialize.
    if not isinstance(value, datetime):
        _refuse("QC callback clock is unavailable")
    # LEAN algorithm.time is normally naive in the algorithm time zone.
    local = value.replace(tzinfo=NEW_YORK) if value.tzinfo is None else value.astimezone(NEW_YORK)
    return local.isoformat(timespec="seconds")
'''
_NEW_CLOCK = b'''def _clock_text(value):
    # QC's Python bridge may supply a datetime subtype. Other completed lane
    # runtimes accept that shape; exact-type equality rejected it at initialize.
    if not isinstance(value, datetime):
        _refuse("QC callback clock is unavailable")
    # LEAN algorithm.time is normally naive in the algorithm time zone.
    local = value.replace(tzinfo=NEW_YORK) if value.tzinfo is None else value.astimezone(NEW_YORK)
    return local.isoformat(timespec="seconds")


def _callback_time(algorithm):
    return _clock_text(algorithm.time)
'''
_OLD_PERSIST_SIGNATURE = b"    def persist_at_decision(self):\n"
_NEW_PERSIST_SIGNATURE = b"    def persist_at_decision(self, firing_time):\n"
_OLD_DECISION = b"        decision = _callback_time(self.algorithm)\n"
_NEW_DECISION = b"        decision = _clock_text(firing_time)\n"
_OLD_IMPORT = (
    b"from fresh_six_universe_snapshot import ETFS, FreshSixUniverseSnapshot\n"
)
_NEW_IMPORT = (
    b"from fresh_six_universe_snapshot import "
    b"ETFS, FreshSixUniverseSnapshot, _clock_text\n"
)
_OLD_CALLBACK = b'''    def _at_decision(self):
        if self.time.date().isoformat() == '2026-09-28':
            self._snapshot.persist_at_decision()
'''
_NEW_CALLBACK = b'''    def _at_decision(self):
        firing_time = self.time
        # Keep the frozen runtime's explicit second-resolution normalization.
        if _clock_text(firing_time)[:10] == '2026-09-28':
            self._snapshot.persist_at_decision(firing_time)
'''


def _fail(message: str) -> None:
    raise FreshCapturedClockProjectionError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FreshCapturedClockProjectionError(
            "captured-clock projection is not canonical ASCII JSON"
        ) from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(files: tuple[tuple[str, bytes], ...]) -> list[dict[str, object]]:
    return [
        {"path": path, "sha256": _digest(raw), "bytes": len(raw)}
        for path, raw in files
    ]


def _authenticate_parent() -> tuple[tuple[str, bytes], ...]:
    """Load only R279 A2, then authenticate its exact two-file identity."""
    try:
        files = tuple(_load_authenticated_parent_source())
    except (OSError, UnicodeError, TypeError, ValueError, SyntaxError) as exc:
        raise FreshCapturedClockProjectionError(
            "R279 A2 parent source is unavailable"
        ) from exc
    if (
        len(files) != 2
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not bytes
            or not 0 < len(item[1]) <= MAX_SOURCE_FILE_BYTES
            or not item[1].isascii()
            for item in files
        )
    ):
        _fail("R279 A2 parent file inventory changed")
    if tuple(path for path, _ in files) != _PATHS:
        _fail("R279 A2 parent file inventory changed")
    observed = dict(files)
    if (
        _digest(observed[_PATHS[0]]) != PARENT_RUNTIME_SHA256
        or _digest(observed[_PATHS[1]]) != PARENT_MAIN_SHA256
        or _digest(_canonical(_inventory(files)))
        != PARENT_SOURCE_MANIFEST_SHA256
        or PARENT_SOURCE_MANIFEST_SHA256 != _DECLARED_PARENT_MANIFEST_SHA256
        or PARENT_RUNTIME_SHA256 != _DECLARED_PARENT_RUNTIME_SHA256
    ):
        _fail("R279 A2 parent source identity changed")
    return files


def _replace_once(source: bytes, old: bytes, new: bytes, name: str) -> bytes:
    if source.count(old) != 1 or new in source:
        _fail(name + " anchor changed")
    projected = source.replace(old, new, 1)
    if old in projected or projected.count(new) != 1:
        _fail(name + " projection changed")
    return projected


def _project_authenticated_parent(
    parent_files: tuple[tuple[str, bytes], ...],
) -> tuple[tuple[str, bytes], ...]:
    """Apply only the exact captured-clock source transformations."""
    try:
        parent = dict(parent_files)
        runtime = parent[_PATHS[0]]
        main = parent[_PATHS[1]]
    except (TypeError, ValueError, KeyError) as exc:
        raise FreshCapturedClockProjectionError(
            "captured-clock parent file inventory changed"
        ) from exc
    if len(parent) != 2 or tuple(sorted(parent)) != _PATHS:
        _fail("captured-clock parent file inventory changed")
    runtime = _replace_once(runtime, _OLD_CLOCK, _NEW_CLOCK, "callback clock")
    runtime = _replace_once(
        runtime, _OLD_PERSIST_SIGNATURE, _NEW_PERSIST_SIGNATURE,
        "persistence signature",
    )
    runtime = _replace_once(
        runtime, _OLD_DECISION, _NEW_DECISION, "persistence decision clock",
    )
    main = _replace_once(main, _OLD_IMPORT, _NEW_IMPORT, "clock normalizer import")
    main = _replace_once(main, _OLD_CALLBACK, _NEW_CALLBACK, "scheduled callback")
    files = tuple(sorted(((_PATHS[0], runtime), (_PATHS[1], main))))
    for path, raw in files:
        if (
            type(raw) is not bytes
            or not 0 < len(raw) <= MAX_SOURCE_FILE_BYTES
            or not raw.isascii()
        ):
            _fail("captured-clock projected source bounds changed")
        try:
            compile(raw, path, "exec")
        except (SyntaxError, ValueError) as exc:
            raise FreshCapturedClockProjectionError(
                "captured-clock projected source does not compile"
            ) from exc
    return files


def project_source_files() -> tuple[tuple[str, bytes], ...]:
    """Return the exact versioned successor source after all byte checks."""
    files = _project_authenticated_parent(_authenticate_parent())
    observed = dict(files)
    if (
        _digest(observed[_PATHS[0]]) != RUNTIME_SHA256
        or _digest(observed[_PATHS[1]]) != MAIN_SHA256
        or _digest(_canonical(_inventory(files))) != SOURCE_MANIFEST_SHA256
    ):
        _fail("captured-clock projected source identity changed")
    return files


def preview_projection() -> dict[str, object]:
    """Return source identity only; this surface cannot upload or launch."""
    files = project_source_files()
    return {
        "schema": SCHEMA,
        "parent_candidate_id": "R279",
        "parent_attempt": 2,
        "decision_session": "2026-09-28",
        "parent_source_manifest_sha256": PARENT_SOURCE_MANIFEST_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_files": _inventory(files),
        "clock_reads_in_scheduled_callback": 1,
        "quantconnect_io_performed": False,
        "provider_io_performed": False,
        "order_and_outcome_access": False,
    }


__all__ = (
    "FreshCapturedClockProjectionError",
    "MAIN_SHA256",
    "PARENT_MAIN_SHA256",
    "PARENT_RUNTIME_SHA256",
    "PARENT_SOURCE_MANIFEST_SHA256",
    "RUNTIME_SHA256",
    "SCHEMA",
    "SOURCE_MANIFEST_SHA256",
    "preview_projection",
    "project_source_files",
)
