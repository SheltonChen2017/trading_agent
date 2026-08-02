"""Independent supervisor for paper and ML evidence collection (ML-FS-7)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.operations import append_alerts_jsonl
from assistant.storage import AssistantStore
from ml.evidence_operations import (
    EvidenceOperationsPolicy,
    build_evidence_operations_report,
)
from ml.shadow_runtime import load_shadow_config, verify_runtime_artifacts


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(payload), indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _fingerprint(schedule_key: str, check_name: str) -> str:
    return hashlib.sha256(
        f"ml_evidence_operations:{schedule_key}:{check_name}".encode("utf-8")
    ).hexdigest()


def _backup_state(store: AssistantStore) -> Mapping[str, Any] | None:
    state = store.get_system_state("last_database_backup")
    if not isinstance(state, Mapping):
        return None
    result = dict(state)
    path = result.get("path")
    if path:
        try:
            result["integrity"] = store.verify_database_file(path)
        except Exception as exc:
            result["integrity"] = [f"verification failed: {type(exc).__name__}: {exc}"]
    return result


def command_check(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = AssistantStore(args.database)
    config, _ = load_shadow_config(args.config)
    artifact_integrity = ["ok"]
    try:
        verify_runtime_artifacts(config, args.artifact_dir)
    except Exception as exc:
        artifact_integrity = [f"{type(exc).__name__}: {exc}"]

    paper_epoch = store.get_active_paper_evidence_epoch()
    paper_observations = (
        store.list_paper_account_observations(paper_epoch["evidence_epoch"])
        if paper_epoch is not None
        else []
    )
    paper_captures = (
        store.list_portfolio_capture_sessions(evidence_epoch=paper_epoch["evidence_epoch"])
        if paper_epoch is not None
        else []
    )
    ml_epoch = store.get_active_ml_evidence_epoch(config.model_key, config.task)
    epoch_id = ml_epoch["evidence_epoch"] if ml_epoch is not None else None
    runs = store.list_ml_shadow_runs(
        schedule_key=config.schedule_key,
        evidence_epoch=epoch_id,
    ) if epoch_id is not None else []
    predictions = store.list_ml_predictions(evidence_epoch=epoch_id) if epoch_id else []
    prediction_ids = {row["prediction_id"] for row in predictions}
    outcomes = [
        row for row in store.list_ml_prediction_outcomes()
        if row["prediction_id"] in prediction_ids
    ]
    credentials = {
        name: bool(os.environ.get(name, "").strip())
        for name in args.required_credential
    }
    policy = EvidenceOperationsPolicy(
        lookback_sessions=args.lookback_sessions,
        post_close_grace_minutes=args.post_close_grace_minutes,
        maximum_worker_heartbeat_age_hours=args.maximum_worker_heartbeat_age_hours,
        maximum_supervisor_heartbeat_age_minutes=args.maximum_operations_heartbeat_age_minutes,
        maximum_backup_age_hours=args.maximum_backup_age_hours,
        maximum_restore_drill_age_days=args.maximum_restore_drill_age_days,
    )
    current = datetime.now(timezone.utc) if args.as_of is None else datetime.fromisoformat(
        args.as_of.replace("Z", "+00:00")
    )
    report = build_evidence_operations_report(
        now=current,
        policy=policy,
        database_integrity=store.verify_database_file(store.path),
        runtime_artifact_integrity=artifact_integrity,
        required_credentials=credentials,
        paper_epoch=paper_epoch,
        paper_observations=paper_observations,
        portfolio_captures=paper_captures,
        ml_epoch=ml_epoch,
        ml_runs=runs,
        expected_subjects=config.subjects,
        predictions=predictions,
        outcomes=outcomes,
        worker_heartbeats={
            command: store.get_system_state(
                f"ml_shadow_{command}_heartbeat:{config.schedule_key}"
            )
            for command in ("predict", "mature", "monitor")
        },
        operations_heartbeat=store.get_system_state("operations_heartbeat"),
        backup_state=_backup_state(store),
        restore_drill_state=store.get_system_state("last_backup_restore_drill"),
    )
    alerts = []
    for check in report["checks"]:
        if check["ok"]:
            continue
        alerts.append(store.upsert_operational_alert(
            fingerprint=_fingerprint(config.schedule_key, check["name"]),
            severity=check["severity"],
            category="ml_evidence_operations",
            message=f"{check['name']}: {check['detail']}",
            details={
                "schedule_key": config.schedule_key,
                "evidence_epoch": epoch_id,
                "check": check,
                "checked_at": report["checked_at"],
            },
            seen_at=report["checked_at"],
        ))
    if args.alerts_jsonl and alerts:
        append_alerts_jsonl(alerts, args.alerts_jsonl)
    summary = {
        "ok": report["healthy"],
        "command": "check",
        "schedule_key": config.schedule_key,
        "evidence_epoch": epoch_id,
        "report": report,
        "alert_count": len(alerts),
        "alerts": alerts,
        "production_authoritative": False,
    }
    heartbeat = {
        "at": report["checked_at"],
        "ok": report["healthy"],
        "failed_check_count": report["failed_check_count"],
        "schedule_key": config.schedule_key,
        "evidence_epoch": epoch_id,
    }
    store.set_system_state(
        f"ml_evidence_supervisor_heartbeat:{config.schedule_key}", heartbeat
    )
    if args.output:
        _atomic_json(args.output, summary)
    return summary, 0 if report["healthy"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently supervise paper and ML evidence collection."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--alerts-jsonl", type=Path)
    parser.add_argument(
        "--required-credential",
        action="append",
        default=[],
        help="Environment variable name whose non-empty presence is required; values are never emitted.",
    )
    parser.add_argument("--lookback-sessions", type=int, default=10)
    parser.add_argument("--post-close-grace-minutes", type=int, default=120)
    parser.add_argument("--maximum-worker-heartbeat-age-hours", type=float, default=26.0)
    parser.add_argument("--maximum-operations-heartbeat-age-minutes", type=float, default=30.0)
    parser.add_argument("--maximum-backup-age-hours", type=float, default=24.0)
    parser.add_argument("--maximum-restore-drill-age-days", type=float, default=30.0)
    parser.add_argument("--as-of", help="Testing/incident replay clock; defaults to now.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary, exit_code = command_check(args)
    except Exception as exc:
        summary = {
            "ok": False,
            "command": "check",
            "error": f"{type(exc).__name__}: {exc}",
            "production_authoritative": False,
        }
        exit_code = 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
