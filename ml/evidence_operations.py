"""Pure supervised-evidence health rules for ML-FS-7.

The scheduled adapter supplies persisted rows and machine checks.  This module
only decides whether expected evidence exists; it cannot create predictions,
outcomes, portfolio captures, or trading state.
"""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ml.shadow import session_close_instant, trading_sessions

_EASTERN = ZoneInfo("America/New_York")


class EvidenceOperationsError(ValueError):
    """Evidence supervision inputs cannot be evaluated safely."""


def _instant(value: Any, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceOperationsError(f"{name} must be timezone-aware ISO-8601") from exc
    else:
        raise EvidenceOperationsError(f"{name} must be timezone-aware ISO-8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceOperationsError(f"{name} must be timezone-aware ISO-8601")
    return parsed.astimezone(timezone.utc)


def _positive(value: Any, name: str, *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceOperationsError(f"{name} must be positive")
    if not math.isfinite(float(value)) or value <= 0 or (integer and not isinstance(value, int)):
        raise EvidenceOperationsError(f"{name} must be positive")
    return int(value) if integer else float(value)


@dataclasses.dataclass(frozen=True)
class EvidenceOperationsPolicy:
    lookback_sessions: int = 10
    post_close_grace_minutes: int = 120
    maximum_worker_heartbeat_age_hours: float = 26.0
    maximum_supervisor_heartbeat_age_minutes: float = 30.0
    maximum_backup_age_hours: float = 24.0
    maximum_restore_drill_age_days: float = 30.0

    def __post_init__(self) -> None:
        for name in ("lookback_sessions", "post_close_grace_minutes"):
            _positive(getattr(self, name), name, integer=True)
        for name in (
            "maximum_worker_heartbeat_age_hours",
            "maximum_supervisor_heartbeat_age_minutes",
            "maximum_backup_age_hours",
            "maximum_restore_drill_age_days",
        ):
            _positive(getattr(self, name), name)


def _check(
    name: str,
    ok: bool,
    detail: str,
    *,
    severity: str = "critical",
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "severity": severity,
        "detail": detail,
        "evidence": dict(evidence or {}),
    }


def expected_completed_sessions(
    *,
    now: datetime,
    epoch_started_at: str,
    lookback_sessions: int,
    post_close_grace_minutes: int,
) -> tuple[str, ...]:
    current = _instant(now, "now")
    started = _instant(epoch_started_at, "epoch_started_at")
    if started > current:
        raise EvidenceOperationsError("evidence epoch starts after the supervisor clock")
    start_date = started.astimezone(_EASTERN).date()
    end_date = current.astimezone(_EASTERN).date()
    sessions = trading_sessions(start_date, end_date)
    completed = [
        session
        for session in sessions
        if started <= session_close_instant(session.isoformat())
        and current
        >= session_close_instant(session.isoformat())
        + timedelta(minutes=post_close_grace_minutes)
    ]
    return tuple(session.isoformat() for session in completed[-lookback_sessions:])


def _heartbeat_check(
    name: str,
    heartbeat: Mapping[str, Any] | None,
    *,
    now: datetime,
    maximum_age: timedelta,
) -> dict[str, Any]:
    if not isinstance(heartbeat, Mapping) or not heartbeat.get("at"):
        return _check(name, False, "heartbeat has never been recorded")
    try:
        at = _instant(heartbeat["at"], f"{name}.at")
    except EvidenceOperationsError as exc:
        return _check(name, False, str(exc))
    age = now - at
    declared_healthy = heartbeat.get("ok", heartbeat.get("healthy"))
    ok = timedelta(0) <= age <= maximum_age and declared_healthy is True
    return _check(
        name,
        ok,
        f"at={at.isoformat()}, age_seconds={int(age.total_seconds())}, ok={declared_healthy}",
        evidence={"at": at.isoformat(), "age_seconds": int(age.total_seconds())},
    )


def build_evidence_operations_report(
    *,
    now: datetime,
    policy: EvidenceOperationsPolicy,
    database_integrity: Sequence[str],
    runtime_artifact_integrity: Sequence[str],
    required_credentials: Mapping[str, bool],
    paper_epoch: Mapping[str, Any] | None,
    paper_observations: Sequence[Mapping[str, Any]],
    portfolio_captures: Sequence[Mapping[str, Any]],
    ml_epoch: Mapping[str, Any] | None,
    ml_runs: Sequence[Mapping[str, Any]],
    expected_subjects: Sequence[str],
    predictions: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    worker_heartbeats: Mapping[str, Mapping[str, Any] | None],
    operations_heartbeat: Mapping[str, Any] | None,
    backup_state: Mapping[str, Any] | None,
    restore_drill_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    current = _instant(now, "now")
    checks: list[dict[str, Any]] = []
    checks.append(_check(
        "database_integrity",
        list(database_integrity) == ["ok"],
        f"result={list(database_integrity)}",
    ))
    checks.append(_check(
        "runtime_artifact_integrity",
        list(runtime_artifact_integrity) == ["ok"],
        f"result={list(runtime_artifact_integrity)}",
    ))
    missing_credentials = sorted(
        name for name, available in required_credentials.items() if available is not True
    )
    checks.append(_check(
        "required_credentials",
        not missing_credentials,
        "all configured credential names are present" if not missing_credentials else f"missing={missing_credentials}",
        evidence={"required_names": sorted(required_credentials), "missing_names": missing_credentials},
    ))

    paper_expected: tuple[str, ...] = ()
    if not isinstance(paper_epoch, Mapping) or paper_epoch.get("status") != "active":
        checks.append(_check("active_paper_evidence_epoch", False, "no active paper evidence epoch"))
    else:
        checks.append(_check(
            "active_paper_evidence_epoch", True,
            f"evidence_epoch={paper_epoch.get('evidence_epoch')}",
        ))
        paper_expected = expected_completed_sessions(
            now=current,
            epoch_started_at=str(paper_epoch["started_at"]),
            lookback_sessions=policy.lookback_sessions,
            post_close_grace_minutes=policy.post_close_grace_minutes,
        )
    observation_by_session = {
        str(row.get("session_date")): row for row in paper_observations
    }
    missing_observations = [
        session for session in paper_expected if session not in observation_by_session
    ]
    checks.append(_check(
        "paper_observation_session_coverage",
        not missing_observations,
        f"expected={len(paper_expected)}, missing={missing_observations}",
        evidence={"expected_sessions": list(paper_expected), "missing_sessions": missing_observations},
    ))
    captures_by_observation = {
        str(row.get("observation_id")): row for row in portfolio_captures
    }
    incomplete_captures = [
        {
            "session_date": session,
            "observation_id": observation.get("observation_id"),
        }
        for session, observation in observation_by_session.items()
        if session in paper_expected
        and str(observation.get("observation_id")) not in captures_by_observation
    ]
    checks.append(_check(
        "portfolio_capture_manifest_completeness",
        not incomplete_captures,
        f"incomplete={incomplete_captures}",
        evidence={"incomplete_captures": incomplete_captures},
    ))

    ml_expected: tuple[str, ...] = ()
    if not isinstance(ml_epoch, Mapping) or ml_epoch.get("status") != "active":
        checks.append(_check("active_ml_evidence_epoch", False, "no active ML evidence epoch"))
    else:
        checks.append(_check(
            "active_ml_evidence_epoch", True,
            f"evidence_epoch={ml_epoch.get('evidence_epoch')}",
        ))
        ml_expected = expected_completed_sessions(
            now=current,
            epoch_started_at=str(ml_epoch["started_at"]),
            lookback_sessions=policy.lookback_sessions,
            post_close_grace_minutes=policy.post_close_grace_minutes,
        )
    run_sessions: set[str] = set()
    failed_runs: list[str] = []
    noncompleted_runs: list[str] = []
    for run in ml_runs:
        try:
            session = _instant(run.get("scheduled_for"), "run.scheduled_for").astimezone(_EASTERN).date().isoformat()
        except EvidenceOperationsError:
            continue
        run_sessions.add(session)
        if run.get("status") == "failed":
            failed_runs.append(str(run.get("run_id")))
        if run.get("status") != "completed":
            noncompleted_runs.append(str(run.get("run_id")))
    missed_runs = [session for session in ml_expected if session not in run_sessions]
    checks.append(_check(
        "ml_prediction_run_coverage",
        not missed_runs and not noncompleted_runs,
        f"expected={len(ml_expected)}, missed={missed_runs}, noncompleted_runs={noncompleted_runs}",
        evidence={
            "expected_sessions": list(ml_expected),
            "missed_sessions": missed_runs,
            "failed_run_ids": failed_runs,
            "noncompleted_run_ids": noncompleted_runs,
        },
    ))

    expected_subject_set = {str(subject) for subject in expected_subjects}
    predictions_by_run: dict[str, list[Mapping[str, Any]]] = {}
    for prediction in predictions:
        predictions_by_run.setdefault(str(prediction.get("shadow_run_id")), []).append(
            prediction
        )
    incomplete_attempts: list[dict[str, Any]] = []
    for run in ml_runs:
        try:
            session = (
                _instant(run.get("scheduled_for"), "run.scheduled_for")
                .astimezone(_EASTERN)
                .date()
                .isoformat()
            )
        except EvidenceOperationsError:
            continue
        if session not in ml_expected:
            continue
        run_id = str(run.get("run_id"))
        run_predictions = predictions_by_run.get(run_id, [])
        actual_subjects = {str(row.get("subject_key")) for row in run_predictions}
        try:
            declared_count = int(run.get("prediction_count"))
        except (TypeError, ValueError):
            declared_count = -1
        missing_subjects = sorted(expected_subject_set - actual_subjects)
        unexpected_subjects = sorted(actual_subjects - expected_subject_set)
        if (
            missing_subjects
            or unexpected_subjects
            or declared_count != len(run_predictions)
        ):
            incomplete_attempts.append({
                "run_id": run_id,
                "session_date": session,
                "declared_prediction_count": declared_count,
                "stored_prediction_count": len(run_predictions),
                "missing_subjects": missing_subjects,
                "unexpected_subjects": unexpected_subjects,
            })
    checks.append(_check(
        "ml_prediction_attempt_completeness",
        bool(expected_subject_set) and not incomplete_attempts,
        (
            f"configured_subjects={len(expected_subject_set)}, incomplete={incomplete_attempts}"
            if expected_subject_set
            else "no configured subjects"
        ),
        evidence={
            "expected_subjects": sorted(expected_subject_set),
            "incomplete_attempts": incomplete_attempts,
        },
    ))

    outcome_ids = {str(row.get("prediction_id")) for row in outcomes}
    outcome_underfill: list[str] = []
    for prediction in predictions:
        if not prediction.get("available"):
            continue
        try:
            available_at = _instant(prediction.get("target_available_at"), "prediction.target_available_at")
        except EvidenceOperationsError:
            outcome_underfill.append(str(prediction.get("prediction_id")))
            continue
        prediction_id = str(prediction.get("prediction_id"))
        if current >= available_at and prediction_id not in outcome_ids:
            outcome_underfill.append(prediction_id)
    checks.append(_check(
        "matured_prediction_outcomes",
        not outcome_underfill,
        f"matured_without_outcome={outcome_underfill}",
        evidence={"prediction_ids": outcome_underfill},
    ))

    for key in ("predict", "mature", "monitor"):
        checks.append(_heartbeat_check(
            f"ml_{key}_heartbeat",
            worker_heartbeats.get(key),
            now=current,
            maximum_age=timedelta(hours=policy.maximum_worker_heartbeat_age_hours),
        ))
    checks.append(_heartbeat_check(
        "operations_watchdog_heartbeat",
        operations_heartbeat,
        now=current,
        maximum_age=timedelta(minutes=policy.maximum_supervisor_heartbeat_age_minutes),
    ))

    backup_at = None
    if isinstance(backup_state, Mapping) and backup_state.get("completed_at"):
        try:
            backup_at = _instant(backup_state["completed_at"], "backup.completed_at")
        except EvidenceOperationsError:
            pass
    backup_ok = (
        backup_at is not None
        and timedelta(0) <= current - backup_at <= timedelta(hours=policy.maximum_backup_age_hours)
        and backup_state.get("integrity") == ["ok"]
    )
    checks.append(_check(
        "verified_database_backup",
        backup_ok,
        "missing or stale verified backup" if backup_at is None else f"at={backup_at.isoformat()}, integrity={backup_state.get('integrity')}",
        severity="warning",
    ))
    drill_at = None
    if isinstance(restore_drill_state, Mapping) and restore_drill_state.get("completed_at"):
        try:
            drill_at = _instant(restore_drill_state["completed_at"], "restore.completed_at")
        except EvidenceOperationsError:
            pass
    drill_ok = (
        drill_at is not None
        and timedelta(0) <= current - drill_at <= timedelta(days=policy.maximum_restore_drill_age_days)
        and restore_drill_state.get("passed") is True
    )
    checks.append(_check(
        "backup_restore_drill",
        drill_ok,
        "missing, stale, or failed restore drill" if drill_at is None else f"at={drill_at.isoformat()}, passed={restore_drill_state.get('passed')}",
        severity="warning",
    ))

    failed = [check for check in checks if not check["ok"]]
    return {
        "schema_version": "1",
        "checked_at": current.isoformat(),
        "healthy": not failed,
        "checks": checks,
        "failed_check_count": len(failed),
        "critical_failure_count": sum(check["severity"] == "critical" for check in failed),
        "warning_failure_count": sum(check["severity"] == "warning" for check in failed),
        "paper_expected_sessions": list(paper_expected),
        "ml_expected_sessions": list(ml_expected),
        "production_authoritative": False,
    }
