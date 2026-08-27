"""Cross-process serialization for broker dispatch and emergency containment.

The durable kill switch answers *whether* a submission may proceed.  This
module closes the separate time-of-check/time-of-use race by giving every
broker-contacting dispatch and every containment operation the same exclusive
OS-backed fence.  A process-local re-entrant lock is paired with the file lock
because POSIX ``flock`` locks are process-scoped and therefore do not serialize
threads in one process by themselves.

The lock file is permanent and contains no state.  Ownership lives entirely in
the open file descriptor, so the operating system releases it after an
unexpected process exit.  Callers must not delete the file: replacing its inode
would allow two processes to believe they hold the same named fence.
"""
from __future__ import annotations

import math
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterator


DEFAULT_DISPATCH_FENCE_TIMEOUT_SECONDS = 30.0
DEFAULT_DISPATCH_FENCE_POLL_SECONDS = 0.01
_LOCK_DIRECTORY_NAME = "locks"
_LOCK_FILE_NAME = "execution-dispatch.lock"
_STATE_LOCK_FILE_NAME = "execution-state.lock"
_STATE_DIRECTORY_NAME = "state"
_EMERGENCY_STOP_FILE_NAME = "execution-emergency-stop.json"
_DISPATCH_ATTEMPTS_FILE_NAME = "execution-dispatch-attempts.json"
_RUNTIME_STOP_STATE_VERSION = 2
_DISPATCH_ATTEMPT_STATE_VERSION = 1
_DISPATCH_ATTEMPT_RETENTION_SECONDS = 24 * 60 * 60
_MAX_RUNTIME_DISPATCH_ATTEMPTS = 4096


class DispatchFenceTimeout(TimeoutError):
    """The execution dispatch fence could not be acquired in time."""


class RuntimeDispatchAttemptConflictError(RuntimeError):
    """Shared broker-attempt identity was reused or its ledger was damaged."""


@dataclass(frozen=True, slots=True)
class ExecutionDispatchPermit:
    """Opaque, process-local authority for one final broker contact.

    The identifier is not authority by itself.  A permit is accepted only
    while this exact object remains identity-registered in this process; a
    reconstructed dataclass (even with the same identifier) is refused.
    """

    permit_id: str


@dataclass(frozen=True, slots=True)
class _DispatchPermitRecord:
    permit: ExecutionDispatchPermit
    broker_session: object
    owner_pid: int
    database: str
    proposal_id: str
    idempotency_key: str
    attempted_at: str
    account_id: str
    account_mode: str
    snapshot_id: str
    policy_fingerprint: str
    runtime_stop_generation: str
    expires_at: datetime


_DISPATCH_PERMITS_GUARD = threading.Lock()
_DISPATCH_PERMITS: dict[str, _DispatchPermitRecord] = {}
_DISPATCH_PERMIT_TTL_SECONDS = 30
_RUNTIME_STOP_LOCAL_FAILURE: str | None = None


def _latch_runtime_emergency_stop_failure(error: object) -> None:
    """Keep this process fail-closed when global persistence cannot be proven."""
    global _RUNTIME_STOP_LOCAL_FAILURE
    _RUNTIME_STOP_LOCAL_FAILURE = str(error)


def _canonical_runtime_root() -> Path:
    """Resolve the one execution runtime shared by every local database.

    This namespace is deliberately not configurable through an application
    environment variable. Allowing each process or worktree to choose a root
    would split the very fence and emergency-stop authority this module exists
    to make global. Tests isolate it by monkeypatching the private module
    constant after import; production callers have no public namespace seam.

    The platform location is stable per operating-system user.  That is the
    executable runtime boundary: processes under different OS identities do
    not share credentials, environment, or a writable state directory and
    therefore cannot safely coordinate through one permissionless lock file.
    """
    if sys.platform == "win32":
        # Resolve LocalAppData through the Windows known-folder API. Process
        # environment variables (LOCALAPPDATA/TMP/etc.) are mutable and would
        # let two execution processes choose different containment authorities.
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(
            None, 0x001C, None, 0, buffer  # CSIDL_LOCAL_APPDATA
        )
        candidate = Path(buffer.value) if result == 0 and buffer.value else None
        if candidate is None or not candidate.is_absolute():
            raise RuntimeError(
                "Windows LocalAppData known folder is unavailable; refusing "
                "to create a split execution runtime"
            )
        return candidate / "trading_agent" / "runtime"

    if not hasattr(os, "getuid"):
        raise RuntimeError("OS user identity is unavailable for execution runtime")
    uid = os.getuid()
    run_user = Path(f"/run/user/{uid}")
    if run_user.is_dir():
        status = os.lstat(run_user)
        if (
            stat.S_ISDIR(status.st_mode)
            and status.st_uid == uid
            and status.st_mode & 0o077 == 0
        ):
            return run_user / "trading_agent"

    # /tmp itself is shared, so create and verify one literal, user-named
    # 0700 directory. Never consult TMPDIR/TEMP or follow a pre-created link.
    user_root = Path(f"/tmp/trading-agent-{uid}")
    try:
        os.mkdir(user_root, 0o700)
    except FileExistsError:
        pass
    status = os.lstat(user_root)
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != uid
        or status.st_mode & 0o077 != 0
    ):
        raise RuntimeError(
            "fixed execution runtime directory is not privately owned by this user"
        )
    return user_root / "runtime"


_RUNTIME_FENCE_ROOT = _canonical_runtime_root()


def dispatch_fence_path(database: str | Path) -> Path:
    """Return the process runtime's single execution-dispatch lock path.

    ``database`` remains in the public signature for caller compatibility, but
    it deliberately cannot choose the lock namespace.  Multiple databases and
    worktrees can operate the same broker account; deriving the fence from a
    database parent would let one process dispatch while another process's
    emergency cancel-all believed it held the exclusive containment boundary.
    """
    if not isinstance(database, (str, os.PathLike)):
        raise TypeError("database must be a filesystem path")
    return _RUNTIME_FENCE_ROOT / _LOCK_DIRECTORY_NAME / _LOCK_FILE_NAME


def runtime_emergency_stop_path(database: str | Path) -> Path:
    """Return the durable stop shared by every database using this fence."""
    dispatch_fence_path(database)  # preserve the public path type validation
    return (
        _RUNTIME_FENCE_ROOT
        / _STATE_DIRECTORY_NAME
        / _EMERGENCY_STOP_FILE_NAME
    )


def runtime_state_fence_path(database: str | Path) -> Path:
    """Return the short-held lock protecting runtime JSON state updates."""
    dispatch_fence_path(database)
    return _RUNTIME_FENCE_ROOT / _LOCK_DIRECTORY_NAME / _STATE_LOCK_FILE_NAME


def runtime_dispatch_attempts_path(database: str | Path) -> Path:
    """Return the cross-database broker-attempt ledger path."""
    dispatch_fence_path(database)
    return (
        _RUNTIME_FENCE_ROOT
        / _STATE_DIRECTORY_NAME
        / _DISPATCH_ATTEMPTS_FILE_NAME
    )


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    """Crash-durably replace one small runtime coordination record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        # POSIX needs the directory entry flushed as well. Windows does not
        # permit opening a directory this way; the replaced file itself has
        # already been flushed there.
        if os.name != "nt":
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _aware_iso_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _runtime_incident_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 192
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None
    ):
        raise ValueError(
            "runtime emergency-stop incident_id must be a canonical identifier"
        )
    return value


def _validated_runtime_incident(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "incident_id",
        "reason",
        "activated_at",
        "origin_database",
    }:
        raise ValueError("runtime emergency-stop incident is malformed")
    incident_id = _runtime_incident_id(value.get("incident_id"))
    reason = value.get("reason")
    origin_database = value.get("origin_database")
    activated_at = value.get("activated_at")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or reason != reason.strip()
        or not isinstance(origin_database, str)
        or not origin_database.strip()
        or not Path(origin_database).is_absolute()
        or str(Path(origin_database).expanduser().resolve()) != origin_database
        or _aware_iso_text(activated_at, name="activated_at") != activated_at
    ):
        raise ValueError("runtime emergency-stop incident is malformed")
    return {
        "incident_id": incident_id,
        "reason": reason,
        "activated_at": activated_at,
        "origin_database": origin_database,
    }


def _runtime_stop_reason(incidents: list[dict[str, str]]) -> str:
    if not incidents:
        return ""
    return "; ".join(
        f"{item['incident_id']}={item['reason']}" for item in incidents
    )


def activate_runtime_emergency_stop(
    database: str | Path,
    *,
    incident_id: str,
    reason: str,
    changed_at: str,
) -> dict[str, Any]:
    """Add one independently clearable runtime-wide containment incident."""
    incident_id = _runtime_incident_id(incident_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("runtime emergency-stop reason must be non-empty")
    reason = reason.strip()
    changed_at = _aware_iso_text(changed_at, name="changed_at")
    origin_database = str(Path(database).expanduser().resolve())
    with runtime_state_fence(database):
        current = get_runtime_emergency_stop(database)
        if current.get("integrity_error"):
            raise RuntimeError(current["reason"])
        incidents = list(current["open_incidents"])
        for existing in incidents:
            if existing["incident_id"] != incident_id:
                continue
            if (
                existing["reason"] == reason
                and existing["origin_database"] == origin_database
            ):
                return dict(current)
            raise RuntimeError(
                "runtime emergency-stop incident ID was reused with different content"
            )
        incidents.append(
            {
                "incident_id": incident_id,
                "reason": reason,
                "activated_at": changed_at,
                "origin_database": origin_database,
            }
        )
        incidents.sort(key=lambda item: item["incident_id"])
        state = {
            "version": _RUNTIME_STOP_STATE_VERSION,
            "active": True,
            "scope": "execution_runtime",
            "generation": current["generation"] + 1,
            "reason": _runtime_stop_reason(incidents),
            "changed_at": changed_at,
            "open_incidents": incidents,
            "last_clear": current["last_clear"],
        }
        try:
            _atomic_json_write(runtime_emergency_stop_path(database), state)
        except Exception as exc:
            # Physical persistence can fail (permissions/full disk). Retain a
            # process-global fail-closed latch so this process cannot mint or
            # consume execution authority after observing that failure.
            global _RUNTIME_STOP_LOCAL_FAILURE
            _RUNTIME_STOP_LOCAL_FAILURE = str(exc)
            raise
    return dict(state)


def get_runtime_emergency_stop(database: str | Path) -> dict[str, Any]:
    """Read the shared stop; corrupt or unreadable state fails closed."""
    if _RUNTIME_STOP_LOCAL_FAILURE is not None:
        return {
            "version": _RUNTIME_STOP_STATE_VERSION,
            "active": True,
            "scope": "execution_runtime",
            "generation": -1,
            "reason": (
                "runtime emergency-stop persistence failed in this process: "
                f"{_RUNTIME_STOP_LOCAL_FAILURE}"
            ),
            "changed_at": None,
            "open_incidents": [],
            "last_clear": None,
            "integrity_error": _RUNTIME_STOP_LOCAL_FAILURE,
        }
    path = runtime_emergency_stop_path(database)
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict) or type(state.get("version")) is not int:
            raise ValueError("runtime emergency-stop record is malformed")
        if state["version"] != _RUNTIME_STOP_STATE_VERSION:
            raise ValueError("runtime emergency-stop record is malformed")
        active = state.get("active")
        expected_fields = {
            "version",
            "active",
            "scope",
            "generation",
            "reason",
            "changed_at",
            "open_incidents",
            "last_clear",
        }
        incidents = state.get("open_incidents")
        if (
            type(active) is not bool
            or set(state) != expected_fields
            or state.get("scope") != "execution_runtime"
            or type(state.get("generation")) is not int
            or state["generation"] < 1
            or not isinstance(state.get("reason"), str)
            or not state["reason"].strip()
            or not isinstance(incidents, list)
            or active is not bool(incidents)
            or _aware_iso_text(state.get("changed_at"), name="changed_at")
            != state.get("changed_at")
        ):
            raise ValueError("runtime emergency-stop record is malformed")
        normalized_incidents = [
            _validated_runtime_incident(item) for item in incidents
        ]
        if (
            incidents != normalized_incidents
            or incidents != sorted(incidents, key=lambda item: item["incident_id"])
            or len({item["incident_id"] for item in incidents}) != len(incidents)
            or (
                active
                and state["reason"] != _runtime_stop_reason(incidents)
            )
        ):
            raise ValueError("runtime emergency-stop record is malformed")
        last_clear = state.get("last_clear")
        if last_clear is not None:
            if not isinstance(last_clear, dict) or set(last_clear) != {
                "incident_id",
                "reason",
                "cleared_at",
                "origin_database",
            }:
                raise ValueError("runtime emergency-stop record is malformed")
            _runtime_incident_id(last_clear.get("incident_id"))
            if (
                not isinstance(last_clear.get("reason"), str)
                or not last_clear["reason"].strip()
                or last_clear["reason"] != last_clear["reason"].strip()
                or _aware_iso_text(last_clear.get("cleared_at"), name="cleared_at")
                != last_clear.get("cleared_at")
                or not isinstance(last_clear.get("origin_database"), str)
                or not Path(last_clear["origin_database"]).is_absolute()
                or str(
                    Path(last_clear["origin_database"]).expanduser().resolve()
                )
                != last_clear["origin_database"]
            ):
                raise ValueError("runtime emergency-stop record is malformed")
        if not active and (
            last_clear is None or state["reason"] != last_clear["reason"]
        ):
            raise ValueError("runtime emergency-stop record is malformed")
        return dict(state)
    except FileNotFoundError:
        return {
            "version": _RUNTIME_STOP_STATE_VERSION,
            "active": False,
            "scope": "execution_runtime",
            "generation": 0,
            "reason": "",
            "changed_at": None,
            "open_incidents": [],
            "last_clear": None,
        }
    except Exception as exc:
        return {
            "version": _RUNTIME_STOP_STATE_VERSION,
            "active": True,
            "scope": "execution_runtime",
            "generation": -1,
            "reason": f"runtime emergency-stop state is unreadable: {exc}",
            "changed_at": None,
            "open_incidents": [],
            "last_clear": None,
            "integrity_error": str(exc),
        }


def clear_runtime_emergency_stop(
    database: str | Path,
    *,
    incident_id: str,
    expected_generation: int,
    reason: str,
    changed_at: str,
) -> dict[str, Any]:
    """Clear one incident from exactly the observed runtime generation.

    A stale operator screen cannot clear a newer incident set. Other open
    incidents remain active, so one incident owner cannot erase another
    independent containment request.
    """
    incident_id = _runtime_incident_id(incident_id)
    if type(expected_generation) is not int or expected_generation < 1:
        raise ValueError("expected_generation must be a positive integer")
    changed_at = _aware_iso_text(changed_at, name="changed_at")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("runtime emergency-stop reason must be non-empty")
    with execution_dispatch_fence(database):
        with runtime_state_fence(database):
            current = get_runtime_emergency_stop(database)
            if current.get("integrity_error"):
                raise RuntimeError(current["reason"])
            if current.get("active") is not True:
                raise RuntimeError("runtime emergency stop is not active")
            if current.get("generation") != expected_generation:
                raise RuntimeError(
                    "runtime emergency-stop generation changed after it was observed; "
                    "re-read before clearing"
                )
            expected_origin = str(Path(database).expanduser().resolve())
            incidents = list(current["open_incidents"])
            matching = [
                item for item in incidents if item["incident_id"] == incident_id
            ]
            if not matching:
                raise RuntimeError("runtime emergency-stop incident is not open")
            if matching[0]["origin_database"] != expected_origin:
                raise RuntimeError(
                    "runtime emergency-stop incident may only be cleared from "
                    "the database that activated it"
                )
            remaining = [
                item for item in incidents if item["incident_id"] != incident_id
            ]
            state = {
                "version": _RUNTIME_STOP_STATE_VERSION,
                "active": bool(remaining),
                "scope": "execution_runtime",
                "generation": current["generation"] + 1,
                "reason": (
                    _runtime_stop_reason(remaining) if remaining else reason.strip()
                ),
                "changed_at": changed_at,
                "open_incidents": remaining,
                "last_clear": {
                    "incident_id": incident_id,
                    "reason": reason.strip(),
                    "cleared_at": changed_at,
                    "origin_database": expected_origin,
                },
            }
            _atomic_json_write(runtime_emergency_stop_path(database), state)
            return dict(state)


_RUNTIME_DISPATCH_ATTEMPT_FIELDS = frozenset(
    {
        "proposal_id",
        "idempotency_key",
        "attempted_at",
        "account_id",
        "account_mode",
        "state",
        "order_id",
        "database",
    }
)
_RUNTIME_DISPATCH_ATTEMPT_STATES = frozenset(
    {"pre_contact", "broker_accepted", "reconciled_after_submit_error"}
)


def _validated_runtime_dispatch_attempt(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _RUNTIME_DISPATCH_ATTEMPT_FIELDS:
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt row has missing or unknown fields"
        )
    result = dict(value)
    for name in ("proposal_id", "idempotency_key", "account_id"):
        field = result.get(name)
        if (
            not isinstance(field, str)
            or not field
            or field != field.strip()
        ):
            raise RuntimeDispatchAttemptConflictError(
                f"runtime dispatch-attempt {name} is non-canonical"
            )
    if result.get("account_mode") not in {"paper", "live"}:
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt account_mode is invalid"
        )
    if result.get("state") not in _RUNTIME_DISPATCH_ATTEMPT_STATES:
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt state is unknown"
        )
    order_id = result.get("order_id")
    if order_id is not None and (
        not isinstance(order_id, str)
        or not order_id
        or order_id != order_id.strip()
    ):
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt order_id is non-canonical"
        )
    if (
        result["state"] == "pre_contact"
        and order_id is not None
    ) or (
        result["state"] != "pre_contact"
        and order_id is None
    ):
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt state and order_id are inconsistent"
        )
    attempted_at = _aware_iso_text(result.get("attempted_at"), name="attempted_at")
    if attempted_at != result.get("attempted_at"):
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt attempted_at is non-canonical"
        )
    database = result.get("database")
    if (
        not isinstance(database, str)
        or not Path(database).is_absolute()
        or str(Path(database).expanduser().resolve()) != database
    ):
        raise RuntimeDispatchAttemptConflictError(
            "runtime dispatch-attempt database is non-canonical"
        )
    return result


def _runtime_dispatch_attempt_identity(
    attempt: dict[str, Any],
) -> tuple[str, str, str, str, str, str]:
    return (
        attempt["database"],
        attempt["proposal_id"],
        attempt["idempotency_key"],
        attempt["attempted_at"],
        attempt["account_id"],
        attempt["account_mode"],
    )


def _contain_runtime_dispatch_attempt_integrity(
    database: str | Path, reason: str
) -> None:
    database_text = str(Path(database).expanduser().resolve())
    incident_id = "dispatch-attempt-integrity:" + hashlib.sha256(
        f"{database_text}:{reason}".encode("utf-8")
    ).hexdigest()[:40]
    changed_at = datetime.now(timezone.utc).isoformat()
    activation_error: Exception | None = None
    try:
        activate_runtime_emergency_stop(
            database,
            incident_id=incident_id,
            reason=reason,
            changed_at=changed_at,
        )
    except Exception as exc:
        activation_error = exc

    def _incident_is_open(observed: dict[str, Any]) -> bool:
        return any(
            item.get("incident_id") == incident_id
            and item.get("reason") == reason
            and item.get("origin_database") == database_text
            for item in observed.get("open_incidents", [])
        )

    try:
        with execution_dispatch_fence(database):
            observed = get_runtime_emergency_stop(database)
            if observed.get("integrity_error") or _incident_is_open(observed):
                return
            try:
                activate_runtime_emergency_stop(
                    database,
                    incident_id=incident_id,
                    reason=reason,
                    changed_at=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as retry_error:
                activation_error = retry_error
            observed = get_runtime_emergency_stop(database)
            if not observed.get("integrity_error") and not _incident_is_open(observed):
                _latch_runtime_emergency_stop_failure(
                    activation_error
                    or RuntimeError(
                        "runtime dispatch-attempt containment incident was cleared "
                        "before the global dispatch drain completed"
                    )
                )
    except Exception as fence_error:
        _latch_runtime_emergency_stop_failure(fence_error)


def record_runtime_dispatch_attempt(
    database: str | Path,
    *,
    proposal_id: str,
    idempotency_key: str,
    attempted_at: str,
    account_id: str,
    account_mode: str,
    order_id: str | None = None,
    state: str = "pre_contact",
) -> dict[str, Any]:
    """Upsert one broker attempt while the caller holds the dispatch fence.

    Records deliberately remain after projection for the broker-indexing grace
    window. Emergency cancellation in another worktree can therefore resolve
    the exact client ID even when the broker open-order endpoint is lagging.
    """
    attempted_at = _aware_iso_text(attempted_at, name="attempted_at")
    if account_mode not in {"paper", "live"}:
        raise ValueError("runtime dispatch attempt account_mode must be paper or live")
    required = {
        "proposal_id": proposal_id,
        "idempotency_key": idempotency_key,
        "attempted_at": attempted_at,
        "account_id": account_id,
        "account_mode": account_mode,
        "state": state,
    }
    for name, value in required.items():
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise ValueError(
                f"runtime dispatch attempt {name} must be canonical and non-empty"
            )
    if state not in {
        "pre_contact",
        "broker_accepted",
        "reconciled_after_submit_error",
    }:
        raise ValueError("runtime dispatch attempt state is unknown")
    if order_id is not None and (
        not isinstance(order_id, str)
        or not order_id
        or order_id != order_id.strip()
    ):
        raise ValueError(
            "runtime dispatch attempt order_id must be canonical and non-empty or None"
        )

    path = runtime_dispatch_attempts_path(database)
    attempt = _validated_runtime_dispatch_attempt(
        {
            **required,
            "order_id": order_id,
            "database": str(Path(database).expanduser().resolve()),
        }
    )
    identity = _runtime_dispatch_attempt_identity(attempt)
    try:
        with runtime_state_fence(database):
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    ledger = json.load(handle)
                if (
                    not isinstance(ledger, dict)
                    or set(ledger) != {"version", "attempts"}
                    or type(ledger.get("version")) is not int
                    or ledger["version"] != _DISPATCH_ATTEMPT_STATE_VERSION
                    or not isinstance(ledger.get("attempts"), list)
                ):
                    raise RuntimeDispatchAttemptConflictError(
                        "runtime dispatch-attempt ledger is malformed"
                    )
            else:
                ledger = {
                    "version": _DISPATCH_ATTEMPT_STATE_VERSION,
                    "attempts": [],
                }

            existing_attempts = [
                _validated_runtime_dispatch_attempt(item)
                for item in ledger["attempts"]
            ]
            same_client = [
                item
                for item in existing_attempts
                if item["idempotency_key"] == idempotency_key
            ]
            if any(
                _runtime_dispatch_attempt_identity(item) != identity
                for item in same_client
            ):
                raise RuntimeDispatchAttemptConflictError(
                    "runtime dispatch-attempt idempotency key is already bound "
                    "to a different database/proposal/account/attempt"
                )
            matching = [
                item
                for item in existing_attempts
                if _runtime_dispatch_attempt_identity(item) == identity
            ]
            if len(matching) > 1:
                raise RuntimeDispatchAttemptConflictError(
                    "runtime dispatch-attempt ledger contains duplicate identities"
                )
            if matching:
                prior = matching[0]
                allowed_transition = (
                    prior["state"] == "pre_contact"
                    and attempt["state"]
                    in {"broker_accepted", "reconciled_after_submit_error"}
                    and prior["order_id"] is None
                    and attempt["order_id"] is not None
                )
                exact_replay = (
                    prior["state"] == attempt["state"]
                    and prior["order_id"] == attempt["order_id"]
                )
                if not (allowed_transition or exact_replay):
                    raise RuntimeDispatchAttemptConflictError(
                        "runtime dispatch-attempt mutable state regressed or "
                        "changed accepted order identity"
                    )
            elif attempt["state"] != "pre_contact":
                raise RuntimeDispatchAttemptConflictError(
                    "runtime dispatch-attempt terminal state has no retained "
                    "pre_contact identity"
                )

            retention_cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=_DISPATCH_ATTEMPT_RETENTION_SECONDS
            )
            attempts = [
                item
                for item in existing_attempts
                if _runtime_dispatch_attempt_identity(item) != identity
                and datetime.fromisoformat(item["attempted_at"]) >= retention_cutoff
            ]
            attempts.append(attempt)
            attempts.sort(
                key=lambda item: (
                    item["attempted_at"],
                    item["database"],
                    item["proposal_id"],
                    item["idempotency_key"],
                )
            )
            if len(attempts) > _MAX_RUNTIME_DISPATCH_ATTEMPTS:
                raise RuntimeError("runtime dispatch-attempt ledger capacity exceeded")
            ledger = {
                "version": _DISPATCH_ATTEMPT_STATE_VERSION,
                "attempts": attempts,
            }
            _atomic_json_write(path, ledger)
            return dict(attempt)
    except (RuntimeDispatchAttemptConflictError, ValueError) as exc:
        _contain_runtime_dispatch_attempt_integrity(database, str(exc))
        raise


def list_runtime_dispatch_attempts(database: str | Path) -> list[dict[str, Any]]:
    """Read the strict shared attempt ledger; corruption stays explicit."""
    path = runtime_dispatch_attempts_path(database)
    try:
        with path.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except FileNotFoundError:
        return []
    try:
        if (
            not isinstance(ledger, dict)
            or set(ledger) != {"version", "attempts"}
            or type(ledger.get("version")) is not int
            or ledger["version"] != _DISPATCH_ATTEMPT_STATE_VERSION
            or not isinstance(ledger.get("attempts"), list)
        ):
            raise RuntimeDispatchAttemptConflictError(
                "runtime dispatch-attempt ledger is malformed"
            )
        attempts = [
            _validated_runtime_dispatch_attempt(item) for item in ledger["attempts"]
        ]
        identities: set[tuple[str, ...]] = set()
        clients: dict[str, tuple[str, ...]] = {}
        for item in attempts:
            identity = _runtime_dispatch_attempt_identity(item)
            if identity in identities:
                raise RuntimeDispatchAttemptConflictError(
                    "runtime dispatch-attempt ledger contains duplicate identities"
                )
            identities.add(identity)
            prior = clients.setdefault(item["idempotency_key"], identity)
            if prior != identity:
                raise RuntimeDispatchAttemptConflictError(
                    "runtime dispatch-attempt idempotency key has conflicting identities"
                )
        if attempts != sorted(
            attempts,
            key=lambda item: (
                item["attempted_at"],
                item["database"],
                item["proposal_id"],
                item["idempotency_key"],
            ),
        ):
            raise RuntimeDispatchAttemptConflictError(
                "runtime dispatch-attempt ledger is non-canonical"
            )
        return attempts
    except (RuntimeDispatchAttemptConflictError, ValueError) as exc:
        _contain_runtime_dispatch_attempt_integrity(database, str(exc))
        raise


def _finite_nonnegative_seconds(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative real number")
    parsed = float(value)
    if (
        not math.isfinite(parsed)
        or parsed < 0
        or parsed > threading.TIMEOUT_MAX
    ):
        raise ValueError(f"{name} must be a finite non-negative real number")
    return parsed


def _try_lock_file(handle: BinaryIO) -> None:
    """Acquire one byte non-blockingly or raise ``OSError``."""
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass
class _ProcessFenceState:
    gate: threading.RLock = field(default_factory=threading.RLock)
    depth: int = 0
    handle: BinaryIO | None = None
    owner_thread_id: int | None = None


_STATES_GUARD = threading.Lock()
_STATES: dict[Path, _ProcessFenceState] = {}


def _reset_after_fork() -> None:
    """Discard process-local ownership inherited by a POSIX fork child.

    ``flock`` state follows the inherited open file description.  Treating an
    inherited ``depth`` as same-thread re-entry would let the child enter the
    critical section without independently contending with its parent.  Close
    only the child's duplicated handles (never issue an unlock against the
    shared description), then rebuild all thread locks and state.
    """
    global _STATES, _STATES_GUARD, _DISPATCH_PERMITS, _DISPATCH_PERMITS_GUARD
    for state in _STATES.values():
        if state.handle is not None:
            try:
                state.handle.close()
            except OSError:
                pass
    _STATES = {}
    _STATES_GUARD = threading.Lock()
    _DISPATCH_PERMITS = {}
    _DISPATCH_PERMITS_GUARD = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


def _state_for(path: Path) -> _ProcessFenceState:
    with _STATES_GUARD:
        return _STATES.setdefault(path, _ProcessFenceState())


def _open_lock_file(path: Path) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        # Do not read byte zero to decide whether initialization is needed.
        # On Windows an existing owner has locked that byte, and a contender's
        # read would fail before it ever reaches the non-blocking lock/retry
        # loop.  Seeking to the end inspects only the file offset/size.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


def _acquire_os_lock(
    path: Path,
    *,
    deadline: float,
    poll_seconds: float,
) -> BinaryIO:
    handle = _open_lock_file(path)
    try:
        while True:
            try:
                _try_lock_file(handle)
                return handle
            except OSError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DispatchFenceTimeout(
                        f"timed out waiting for execution dispatch fence {path}"
                    ) from exc
                time.sleep(min(poll_seconds, remaining))
    except BaseException:
        handle.close()
        raise


@contextmanager
def execution_dispatch_fence(
    database: str | Path,
    *,
    timeout_seconds: float = DEFAULT_DISPATCH_FENCE_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_DISPATCH_FENCE_POLL_SECONDS,
) -> Iterator[Path]:
    """Hold the runtime's re-entrant, crash-released execution fence.

    The timeout covers both a competing thread in this process and a competing
    process.  Nested acquisition by the owning thread reuses the same OS lock,
    which lets a fenced dispatch invoke fail-closed containment without
    deadlocking itself.
    """
    timeout = _finite_nonnegative_seconds(
        timeout_seconds, name="timeout_seconds"
    )
    poll = _finite_nonnegative_seconds(poll_seconds, name="poll_seconds")
    if poll == 0:
        raise ValueError("poll_seconds must be greater than zero")

    path = dispatch_fence_path(database)
    state = _state_for(path)
    deadline = time.monotonic() + timeout
    if not state.gate.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise DispatchFenceTimeout(
            f"timed out waiting for execution dispatch fence {path}"
        )

    entered = False
    try:
        if state.depth == 0:
            state.handle = _acquire_os_lock(
                path,
                deadline=deadline,
                poll_seconds=poll,
            )
            state.owner_thread_id = threading.get_ident()
        elif state.handle is None:
            raise RuntimeError("dispatch fence re-entry has no OS lock handle")
        elif state.owner_thread_id != threading.get_ident():
            raise RuntimeError("dispatch fence re-entry changed owning thread")
        state.depth += 1
        entered = True
        yield path
    finally:
        try:
            if entered:
                state.depth -= 1
                if state.depth == 0:
                    handle = state.handle
                    state.handle = None
                    state.owner_thread_id = None
                    if handle is None:
                        raise RuntimeError("dispatch fence lost its OS lock handle")
                    try:
                        _unlock_file(handle)
                    finally:
                        handle.close()
        finally:
            state.gate.release()


def _require_digest(value: object, *, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_binding_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a canonical non-empty string")
    return value


def _runtime_stop_generation(state: dict[str, Any]) -> str:
    """Content-address one fully validated runtime-stop observation."""
    material = json.dumps(
        state,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _require_dispatch_fence_owner(database: str | Path) -> None:
    path = dispatch_fence_path(database)
    state = _state_for(path)
    if (
        state.depth <= 0
        or state.handle is None
        or state.owner_thread_id != threading.get_ident()
    ):
        raise PermissionError(
            "An execution dispatch permit may only be used while the current "
            "thread holds the global dispatch fence."
        )


def _registered_dispatch_permit(
    permit: object,
) -> _DispatchPermitRecord:
    if not isinstance(permit, ExecutionDispatchPermit):
        raise PermissionError(
            "Broker submission requires an identity-registered dispatch permit."
        )
    with _DISPATCH_PERMITS_GUARD:
        record = _DISPATCH_PERMITS.get(permit.permit_id)
    if record is None or record.permit is not permit:
        raise PermissionError(
            "Dispatch permit is forged, foreign, expired, or already consumed."
        )
    if record.owner_pid != os.getpid():
        raise PermissionError("Dispatch permit belongs to a different process.")
    if record.expires_at <= datetime.now(timezone.utc):
        with _DISPATCH_PERMITS_GUARD:
            current = _DISPATCH_PERMITS.get(permit.permit_id)
            if current is record:
                del _DISPATCH_PERMITS[permit.permit_id]
        raise PermissionError("Dispatch permit has expired.")
    return record


def _assert_dispatch_permit_bindings(
    record: _DispatchPermitRecord,
    *,
    broker_session: object,
    idempotency_key: str,
    expected_snapshot_id: str,
    expected_policy_fingerprint: str,
    expected_account_mode: str,
    expected_account_id: str | None = None,
) -> None:
    if record.broker_session is not broker_session:
        raise PermissionError("Dispatch permit belongs to a different broker session.")
    if record.idempotency_key != idempotency_key:
        raise PermissionError("Dispatch permit idempotency binding does not match.")
    if record.snapshot_id != expected_snapshot_id:
        raise PermissionError("Dispatch permit snapshot binding does not match.")
    if record.policy_fingerprint != expected_policy_fingerprint:
        raise PermissionError("Dispatch permit policy binding does not match.")
    if record.account_mode != expected_account_mode:
        raise PermissionError("Dispatch permit account-mode binding does not match.")
    if expected_account_id is not None and record.account_id != expected_account_id:
        raise PermissionError("Dispatch permit broker-account binding does not match.")


def _mint_execution_service_dispatch_permit(
    database: str | Path,
    *,
    broker_session: object,
    proposal_id: str,
    idempotency_key: str,
    attempted_at: str,
    account_id: str,
    account_mode: str,
    snapshot_id: str,
    policy_fingerprint: str,
) -> ExecutionDispatchPermit:
    """Mint one process-local permit after durable pre-contact recording.

    The current thread must already hold the global dispatch fence.  The
    runtime stop must be inactive and the exact attempt must already exist in
    the shared ledger.  This keeps the broker adapter from becoming an
    unfenced alternate execution entry point.
    """
    database_text = str(Path(database).expanduser().resolve())
    _require_dispatch_fence_owner(database_text)
    if broker_session is None:
        raise TypeError("broker_session is required")
    proposal_id = _require_binding_text(proposal_id, name="proposal_id")
    idempotency_key = _require_binding_text(
        idempotency_key, name="idempotency_key"
    )
    account_id = _require_binding_text(account_id, name="account_id")
    if account_mode not in {"paper", "live"}:
        raise ValueError("account_mode must be paper or live")
    snapshot_id = _require_digest(snapshot_id, name="snapshot_id")
    policy_fingerprint = _require_digest(
        policy_fingerprint, name="policy_fingerprint"
    )
    attempted_at = _aware_iso_text(attempted_at, name="attempted_at")

    state = get_runtime_emergency_stop(database_text)
    if state.get("active") is not False:
        raise PermissionError(
            "Runtime emergency stop is active; dispatch permit cannot be minted."
        )
    generation = _runtime_stop_generation(state)
    matching_attempts = [
        item
        for item in list_runtime_dispatch_attempts(database_text)
        if item.get("proposal_id") == proposal_id
        and item.get("idempotency_key") == idempotency_key
        and item.get("attempted_at") == attempted_at
        and item.get("account_id") == account_id
        and item.get("account_mode") == account_mode
        and item.get("state") == "pre_contact"
        and item.get("database") == database_text
    ]
    if len(matching_attempts) != 1:
        raise PermissionError(
            "Dispatch permit requires one exact durable pre-contact attempt record."
        )

    now = datetime.now(timezone.utc)
    permit = ExecutionDispatchPermit(secrets.token_hex(32))
    record = _DispatchPermitRecord(
        permit=permit,
        broker_session=broker_session,
        owner_pid=os.getpid(),
        database=database_text,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        attempted_at=attempted_at,
        account_id=account_id,
        account_mode=account_mode,
        snapshot_id=snapshot_id,
        policy_fingerprint=policy_fingerprint,
        runtime_stop_generation=generation,
        expires_at=now + timedelta(seconds=_DISPATCH_PERMIT_TTL_SECONDS),
    )
    with _DISPATCH_PERMITS_GUARD:
        expired = [
            permit_id
            for permit_id, existing in _DISPATCH_PERMITS.items()
            if existing.owner_pid != os.getpid() or existing.expires_at <= now
        ]
        for permit_id in expired:
            del _DISPATCH_PERMITS[permit_id]
        if len(_DISPATCH_PERMITS) >= _MAX_RUNTIME_DISPATCH_ATTEMPTS:
            raise RuntimeError("dispatch-permit registry capacity exceeded")
        if permit.permit_id in _DISPATCH_PERMITS:
            raise RuntimeError("dispatch-permit identifier collision")
        _DISPATCH_PERMITS[permit.permit_id] = record
    return permit


@contextmanager
def execution_dispatch_permit_fence(
    permit: object,
    *,
    broker_session: object,
    idempotency_key: str,
    expected_snapshot_id: str,
    expected_policy_fingerprint: str,
    expected_account_mode: str,
) -> Iterator[None]:
    """Reacquire the permit's global fence and validate pre-read bindings."""
    record = _registered_dispatch_permit(permit)
    _assert_dispatch_permit_bindings(
        record,
        broker_session=broker_session,
        idempotency_key=idempotency_key,
        expected_snapshot_id=expected_snapshot_id,
        expected_policy_fingerprint=expected_policy_fingerprint,
        expected_account_mode=expected_account_mode,
    )
    with execution_dispatch_fence(record.database):
        # Hold the state fence through the adapter's final broker contact too.
        # Emergency activation therefore linearizes either wholly before this
        # recheck (and refuses) or wholly after contact; it cannot publish an
        # active generation in the consume-to-contact gap.
        with runtime_state_fence(record.database):
            current = _registered_dispatch_permit(permit)
            if current is not record:
                raise PermissionError("Dispatch permit registration changed.")
            _assert_dispatch_permit_bindings(
                current,
                broker_session=broker_session,
                idempotency_key=idempotency_key,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
                expected_account_mode=expected_account_mode,
            )
            state = get_runtime_emergency_stop(record.database)
            if (
                state.get("active") is not False
                or _runtime_stop_generation(state) != record.runtime_stop_generation
            ):
                raise PermissionError(
                    "Runtime emergency-stop generation changed before broker dispatch."
                )
            yield


def consume_execution_dispatch_permit(
    permit: object,
    *,
    broker_session: object,
    idempotency_key: str,
    expected_account_id: str,
    expected_account_mode: str,
    expected_snapshot_id: str,
    expected_policy_fingerprint: str,
) -> None:
    """Atomically consume one permit at the final pre-contact boundary."""
    record = _registered_dispatch_permit(permit)
    _require_dispatch_fence_owner(record.database)
    _assert_dispatch_permit_bindings(
        record,
        broker_session=broker_session,
        idempotency_key=idempotency_key,
        expected_snapshot_id=expected_snapshot_id,
        expected_policy_fingerprint=expected_policy_fingerprint,
        expected_account_mode=expected_account_mode,
        expected_account_id=expected_account_id,
    )
    state = get_runtime_emergency_stop(record.database)
    if (
        state.get("active") is not False
        or _runtime_stop_generation(state) != record.runtime_stop_generation
    ):
        raise PermissionError(
            "Runtime emergency-stop generation changed before broker contact."
        )
    with _DISPATCH_PERMITS_GUARD:
        current = _DISPATCH_PERMITS.get(record.permit.permit_id)
        if current is not record or current.permit is not permit:
            raise PermissionError("Dispatch permit was already consumed.")
        del _DISPATCH_PERMITS[record.permit.permit_id]


@contextmanager
def runtime_state_fence(
    database: str | Path,
    *,
    timeout_seconds: float = DEFAULT_DISPATCH_FENCE_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_DISPATCH_FENCE_POLL_SECONDS,
) -> Iterator[Path]:
    """Serialize short runtime JSON read/modify/write operations.

    This is deliberately distinct from the broker-dispatch fence. Cancel-all
    must be able to publish a stop *before* waiting for an in-flight dispatch,
    while a generation-bound clear must not race and erase that publication.
    """
    timeout = _finite_nonnegative_seconds(timeout_seconds, name="timeout_seconds")
    poll = _finite_nonnegative_seconds(poll_seconds, name="poll_seconds")
    if poll == 0:
        raise ValueError("poll_seconds must be greater than zero")

    path = runtime_state_fence_path(database)
    state = _state_for(path)
    deadline = time.monotonic() + timeout
    if not state.gate.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise DispatchFenceTimeout(
            f"timed out waiting for execution runtime-state fence {path}"
        )
    entered = False
    try:
        if state.depth == 0:
            state.handle = _acquire_os_lock(
                path,
                deadline=deadline,
                poll_seconds=poll,
            )
        elif state.handle is None:
            raise RuntimeError("runtime-state fence re-entry has no OS lock handle")
        state.depth += 1
        entered = True
        yield path
    finally:
        try:
            if entered:
                state.depth -= 1
                if state.depth == 0:
                    handle = state.handle
                    state.handle = None
                    if handle is None:
                        raise RuntimeError("runtime-state fence lost its OS lock handle")
                    try:
                        _unlock_file(handle)
                    finally:
                        handle.close()
        finally:
            state.gate.release()
