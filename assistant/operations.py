"""Operational health, durable alerting, and backup/restore verification."""
from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from assistant.policy import (
    TradingPolicy,
    compute_policy_fingerprint,
    load_policy,
)
from assistant.readiness import transaction_readiness
from assistant.storage import AssistantStore
from data.operational_alerts import append_alerts_jsonl


class OperationsError(RuntimeError):
    """An operational control could not be evaluated safely."""


# These are deliberately separate state rows. A fast operations cycle must
# not make a dead long-running watchdog or order monitor look alive. The
# watchdog retains the historical ``operations_heartbeat`` state key used by
# the existing UI and ML-evidence supervisor consumers.
OPERATIONAL_POLICY_HEARTBEAT_KEYS = {
    "cycle": "operations_cycle_heartbeat",
    "monitor": "order_monitor_heartbeat",
    "observation": "paper_observation_heartbeat",
    "watchdog": "operations_heartbeat",
    "operations_check": "operations_check_heartbeat",
}
REQUIRED_OPERATIONAL_POLICY_HEARTBEATS = (
    "cycle",
    "monitor",
    "observation",
    "watchdog",
)


def operational_policy_identity(
    policy: TradingPolicy,
    policy_path: str | Path,
) -> dict[str, str]:
    """Return a canonical, disk-verified policy identity.

    The object fingerprint and the file fingerprint must agree. This catches
    a policy file changed after a long-running process loaded it instead of
    letting that process keep certifying obsolete limits.
    """
    try:
        resolved = Path(policy_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise OperationsError(
            f"Operational policy path is not readable: {policy_path}"
        ) from exc
    if not resolved.is_file():
        raise OperationsError(
            f"Operational policy path is not a file: {resolved}"
        )
    object_fingerprint = compute_policy_fingerprint(policy)
    disk_fingerprint = compute_policy_fingerprint(load_policy(resolved))
    if object_fingerprint != disk_fingerprint:
        raise OperationsError(
            "The loaded operational policy no longer matches its policy file."
        )
    return {
        "policy_path": str(resolved),
        "policy_fingerprint": object_fingerprint,
    }


def record_operational_policy_heartbeat(
    store: AssistantStore,
    task: str,
    policy: TradingPolicy,
    policy_path: str | Path,
    *,
    at: str | None = None,
    healthy: bool | None = None,
    **details: Any,
) -> dict[str, Any]:
    """Persist one task heartbeat bound to the exact governing policy."""
    if task not in OPERATIONAL_POLICY_HEARTBEAT_KEYS:
        raise OperationsError(f"Unknown operational heartbeat task: {task!r}")
    if healthy is not None and not isinstance(healthy, bool):
        raise OperationsError("heartbeat healthy must be bool or None")
    identity = operational_policy_identity(policy, policy_path)
    heartbeat = dict(details)
    heartbeat.update(
        {
            "at": at or datetime.now(timezone.utc).isoformat(),
            "healthy": healthy,
            **identity,
        }
    )
    store.set_system_state(OPERATIONAL_POLICY_HEARTBEAT_KEYS[task], heartbeat)
    return heartbeat


def verify_operational_policy_heartbeats(
    store: AssistantStore,
    policy: TradingPolicy,
    policy_path: str | Path,
    *,
    require_all: bool = True,
) -> dict[str, Any]:
    """Compare every operational task heartbeat to one on-disk policy.

    Missing never-ran tasks may be reported as degraded during installation
    preview verification. Once task execution is required, missing heartbeats
    fail exactly like mismatches. A present heartbeat always fails on a bad
    fingerprint, changed file, unreadable path, or different canonical path.
    """
    expected = operational_policy_identity(policy, policy_path)
    expected_path = Path(expected["policy_path"])
    checks: dict[str, dict[str, Any]] = {}
    for task in REQUIRED_OPERATIONAL_POLICY_HEARTBEATS:
        state_key = OPERATIONAL_POLICY_HEARTBEAT_KEYS[task]
        heartbeat = store.get_system_state(state_key)
        if not isinstance(heartbeat, dict):
            checks[task] = {
                "ok": False,
                "status": "missing",
                "state_key": state_key,
                "detail": "heartbeat has not been recorded",
            }
            continue

        recorded_path = heartbeat.get("policy_path")
        recorded_fingerprint = heartbeat.get("policy_fingerprint")
        if not isinstance(recorded_path, str) or not recorded_path.strip():
            checks[task] = {
                "ok": False,
                "status": "invalid",
                "state_key": state_key,
                "detail": "heartbeat policy_path is missing or invalid",
            }
            continue
        try:
            recorded_policy = load_policy(recorded_path)
            observed = operational_policy_identity(
                recorded_policy, recorded_path
            )
            observed_path = Path(observed["policy_path"])
        except Exception as exc:
            checks[task] = {
                "ok": False,
                "status": "unreadable",
                "state_key": state_key,
                "detail": f"recorded policy is unreadable: {exc}",
            }
            continue

        path_matches = os.path.normcase(str(observed_path)) == os.path.normcase(
            str(expected_path)
        )
        fingerprint_matches = (
            isinstance(recorded_fingerprint, str)
            and recorded_fingerprint == observed["policy_fingerprint"]
            and recorded_fingerprint == expected["policy_fingerprint"]
        )
        ok = path_matches and fingerprint_matches
        checks[task] = {
            "ok": ok,
            "status": "matched" if ok else "mismatched",
            "state_key": state_key,
            "policy_path": observed["policy_path"],
            "policy_fingerprint": recorded_fingerprint,
            "detail": (
                "policy path and fingerprint match"
                if ok
                else (
                    f"path_matches={path_matches}, "
                    f"fingerprint_matches={fingerprint_matches}"
                )
            ),
        }

    failures = [
        task
        for task, check in checks.items()
        if not check["ok"]
        and (require_all or check["status"] != "missing")
    ]
    degraded = any(not check["ok"] for check in checks.values())
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "degraded": degraded,
        "require_all": bool(require_all),
        "expected_policy": expected,
        "checks": checks,
        "failed_tasks": failures,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        if value == "":
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    try:
        if parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _require_positive_finite_number(name: str, value: Any) -> None:
    valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
    try:
        finite = valid_type and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        finite = False
    if not finite or value <= 0:
        raise OperationsError(f"{name} must be positive and finite")


def _check(
    name: str,
    ok: bool,
    detail: str,
    *,
    severity: str,
    category: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        "severity": severity,
        "category": category,
    }


_CRITICAL_READINESS_CHECKS = {
    "database_integrity",
    "ambiguous_broker_outcomes",
    "broker_account",
}


def operational_health(
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    broker_module=None,
    now: datetime | None = None,
    check_broker: bool = True,
    max_backup_age_hours: float = 24.0,
    max_ledger_reconciliation_age_minutes: float = 30.0,
    max_restore_drill_age_days: float = 30.0,
) -> dict[str, Any]:
    """Build a health report without changing execution authority."""
    explicit_now = now
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise OperationsError("now must be timezone-aware")
    for name, value in (
        ("max_backup_age_hours", max_backup_age_hours),
        (
            "max_ledger_reconciliation_age_minutes",
            max_ledger_reconciliation_age_minutes,
        ),
        ("max_restore_drill_age_days", max_restore_drill_age_days),
    ):
        _require_positive_finite_number(name, value)

    readiness = transaction_readiness(
        store,
        policy,
        broker_module=broker_module,
        # AP-11: forward the CALLER's clock, never the entry clock
        # manufactured above. Passing `now=now` handed the nested freshness
        # checks an "explicit" clock captured before this function's own
        # integrity/broker work, which froze their post-read AP-7 clocks and
        # re-armed the concurrent-write race in every production run
        # (observed live: a healthy reconciliation alerted as future-dated,
        # age_seconds=-0.117315). `explicit_now` is None on the live
        # watchdog/cycle path, so readiness captures its clock after the
        # read; a genuine caller-supplied as-of clock still freezes the
        # whole chain.
        now=explicit_now,
        check_broker=check_broker,
    )
    checks = [
        _check(
            item["name"],
            item["ok"],
            item["detail"],
            severity=(
                "critical"
                if item["name"] in _CRITICAL_READINESS_CHECKS
                else "warning"
            ),
            category="transaction_readiness",
        )
        for item in readiness["checks"]
    ]

    latest_reconciliation = store.get_latest_ledger_reconciliation()
    # AP-7: compare a row with a clock captured *after* reading that row.
    # The scheduled processes overlap, so a second process may commit between
    # this function's entry clock and this query. Reusing the entry clock made
    # that valid concurrent row look future-dated. An explicitly supplied
    # clock remains frozen for deterministic/as-of evaluation and continues
    # to reject genuinely future-dated state.
    reconciliation_checked_at = (
        explicit_now or datetime.now(timezone.utc)
    )
    reconciliation_at = _parse_timestamp(
        latest_reconciliation.get("reconciled_at")
        if isinstance(latest_reconciliation, dict)
        else None
    )
    # FCS-017: lower bound too. `now - at <= limit` is True for ANY future
    # timestamp, so clock skew or a hand-inserted row made a stale control read
    # as fresh. `_should_create_backup` below and every check in
    # ml/evidence_operations.py already guard this; these three did not.
    reconciliation_age = (
        None
        if reconciliation_at is None
        else reconciliation_checked_at - reconciliation_at
    )
    reconciliation_ok = (
        reconciliation_at is not None
        and timedelta(0) <= reconciliation_age
        <= timedelta(minutes=max_ledger_reconciliation_age_minutes)
        and bool(latest_reconciliation.get("matched"))
    )
    checks.append(
        _check(
            "portfolio_ledger_reconciliation",
            reconciliation_ok,
            (
                "never completed"
                if reconciliation_at is None
                else (
                    f"at={reconciliation_at.isoformat()}, "
                    f"age_seconds={reconciliation_age.total_seconds():.6f}, "
                    f"matched={latest_reconciliation.get('matched')}, "
                    f"mismatches={latest_reconciliation.get('mismatch_count')}"
                )
            ),
            severity="critical",
            category="portfolio_accounting",
        )
    )

    backup = store.get_system_state("last_database_backup")
    backup_at = _parse_timestamp(
        backup.get("completed_at") if isinstance(backup, dict) else None
    )
    backup_path = (
        Path(backup["path"])
        if isinstance(backup, dict) and backup.get("path")
        else None
    )
    backup_integrity: list[str] | None = None
    if backup_path is not None and backup_path.exists():
        try:
            backup_integrity = store.verify_database_file(backup_path)
        except Exception as exc:
            backup_integrity = [f"verification failed: {exc}"]
    backup_checked_at = explicit_now or datetime.now(timezone.utc)
    backup_age = None if backup_at is None else backup_checked_at - backup_at
    backup_ok = (
        backup_at is not None
        and timedelta(0) <= backup_age <= timedelta(hours=max_backup_age_hours)  # FCS-017/AP-7
        and backup_path is not None
        and backup_path.exists()
        and backup_integrity == ["ok"]
    )
    checks.append(
        _check(
            "database_backup",
            backup_ok,
            (
                "never completed"
                if backup_at is None
                else (
                    f"at={backup_at.isoformat()}, "
                    f"age_seconds={backup_age.total_seconds():.6f}, "
                    f"path={backup_path}, "
                    f"integrity={backup_integrity}"
                )
            ),
            severity="warning",
            category="recovery",
        )
    )

    drill = store.get_system_state("last_backup_restore_drill")
    drill_at = _parse_timestamp(
        drill.get("completed_at") if isinstance(drill, dict) else None
    )
    drill_checked_at = explicit_now or datetime.now(timezone.utc)
    drill_age = None if drill_at is None else drill_checked_at - drill_at
    drill_ok = (
        drill_at is not None
        and timedelta(0) <= drill_age <= timedelta(days=max_restore_drill_age_days)  # FCS-017/AP-7
        and bool(drill.get("passed"))
    )
    checks.append(
        _check(
            "backup_restore_drill",
            drill_ok,
            (
                "never completed"
                if drill_at is None
                else (
                    f"at={drill_at.isoformat()}, "
                    f"age_seconds={drill_age.total_seconds():.6f}, "
                    f"passed={drill.get('passed')}"
                )
            ),
            severity="warning",
            category="recovery",
        )
    )

    report_checked_at = explicit_now or datetime.now(timezone.utc)
    return {
        "healthy": all(check["ok"] for check in checks),
        "checked_at": report_checked_at.isoformat(),
        "checks": checks,
        "transaction_readiness": readiness,
    }


def _alert_fingerprint(check: dict[str, Any]) -> str:
    material = f"{check['category']}:{check['name']}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def run_operational_check(
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    broker_module=None,
    now: datetime | None = None,
    check_broker: bool = True,
    policy_path: str | Path | None = None,
    heartbeat_task: str = "operations_check",
    **health_options,
) -> dict[str, Any]:
    """Run health checks, persist failures as deduplicated alerts and heartbeat."""
    report = operational_health(
        store,
        policy,
        broker_module=broker_module,
        now=now,
        check_broker=check_broker,
        **health_options,
    )
    alerts = []
    for check in report["checks"]:
        if check["ok"]:
            continue
        alerts.append(
            store.upsert_operational_alert(
                fingerprint=_alert_fingerprint(check),
                severity=check["severity"],
                category=check["category"],
                message=f"{check['name']}: {check['detail']}",
                details={"check": check, "checked_at": report["checked_at"]},
                seen_at=report["checked_at"],
            )
        )
    heartbeat = {
        "at": report["checked_at"],
        "healthy": report["healthy"],
        "failed_check_count": sum(
            not check["ok"] for check in report["checks"]
        ),
        "emitted_alert_count": len(alerts),
    }
    if policy_path is None:
        # Compatibility for library callers that do not own an entry-point
        # policy path. Scheduled operational callers always pass one.
        store.set_system_state("operations_heartbeat", heartbeat)
    else:
        heartbeat = record_operational_policy_heartbeat(
            store,
            heartbeat_task,
            policy,
            policy_path,
            **heartbeat,
        )
    report["alerts"] = alerts
    report["heartbeat"] = heartbeat
    return report


def ensure_recent_database_backup(
    store: AssistantStore,
    destination_directory: str | Path,
    *,
    now: datetime | None = None,
    max_age_hours: float = 20.0,
) -> dict[str, Any]:
    """Create a verified backup only when the last one is absent or stale."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise OperationsError("now must be timezone-aware")
    _require_positive_finite_number("max_age_hours", max_age_hours)
    previous = store.get_system_state("last_database_backup", default={})
    previous_at = _parse_timestamp(
        previous.get("completed_at") if isinstance(previous, dict) else None
    )
    previous_path = (
        Path(previous["path"])
        if isinstance(previous, dict) and previous.get("path")
        else None
    )
    if (
        previous_at is not None
        and timedelta(0) <= current - previous_at
        <= timedelta(hours=max_age_hours)
        and previous_path is not None
        and previous_path.exists()
        and store.verify_database_file(previous_path) == ["ok"]
    ):
        return {
            "created": False,
            "path": str(previous_path),
            "completed_at": previous_at.isoformat(),
            "reason": "recent verified backup already exists",
        }
    destination = Path(destination_directory)
    timestamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = store.backup_to(
        destination / f"trading-assistant-{timestamp}.db"
    )
    state = store.get_system_state("last_database_backup")
    return {
        "created": True,
        "path": str(target),
        "completed_at": state["completed_at"],
        "reason": "missing or stale backup replaced",
    }


def _table_counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
        return {
            table: int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            )
            for table in tables
        }
    finally:
        connection.close()


def run_backup_restore_drill(
    store: AssistantStore, backup_destination: str | Path
) -> dict[str, Any]:
    """Create, restore and compare a backup without touching the live DB."""
    backup = store.backup_to(backup_destination)
    with tempfile.TemporaryDirectory(prefix="trading-assistant-restore-") as temp:
        restored = Path(temp) / "restored.db"
        source_connection = sqlite3.connect(backup)
        restored_connection = sqlite3.connect(restored)
        try:
            source_connection.backup(restored_connection)
        finally:
            restored_connection.close()
            source_connection.close()
        source_integrity = store.verify_database_file(backup)
        restored_integrity = store.verify_database_file(restored)
        source_counts = _table_counts(backup)
        restored_counts = _table_counts(restored)
        passed = (
            source_integrity == ["ok"]
            and restored_integrity == ["ok"]
            and source_counts == restored_counts
        )
        report = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "backup_path": str(backup),
            "source_integrity": source_integrity,
            "restored_integrity": restored_integrity,
            "table_counts_match": source_counts == restored_counts,
            "table_counts": restored_counts,
        }
    store.set_system_state("last_backup_restore_drill", report)
    epoch = store.get_active_paper_evidence_epoch()
    if epoch is not None:
        store.record_operational_drill(
            drill_type="backup_restore",
            performed_at=report["completed_at"],
            passed=bool(report["passed"]),
            evidence_epoch=epoch["evidence_epoch"],
            code_commit=epoch["lineage"]["code_commit"],
            evidence=report,
        )
    return report
