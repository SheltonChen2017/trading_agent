"""Operate the ML-LR-6 shadow evidence loop.

This is deliberately separate from every trading/operations command.  It can
write model registrations, evidence epochs, shadow attempts, realized
outcomes, monitoring snapshots, and operational alerts.  It cannot create a
proposal, authorization, order, or execution reservation.

Typical setup and daily cadence::

    python scripts/run_ml_shadow.py --database data/paper.db \
      --config config/ml-shadow-volatility.json --artifact-dir artifacts/vol \
      register

    python scripts/run_ml_shadow.py ... predict \
      --scheduled-for 2026-08-03T20:00:00+00:00
    python scripts/run_ml_shadow.py ... mature
    python scripts/run_ml_shadow.py ... monitor --output artifacts/ml-shadow-status.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.operations import append_alerts_jsonl
from assistant.storage import AssistantStore
from ml.artifacts import ArtifactError, load_model_manifest
from ml.contracts import ContractError, ModelManifest
from ml.labels import LabelError
from ml.experiment_contracts import ExperimentContractError, ExperimentSpec
from ml.monitoring_reports import (
    ShadowMonitoringGate,
    build_epoch_monitoring_report,
)
from ml.presentation import (
    EXPERIMENTAL_LABEL,
    build_presentation,
)
from ml.shadow import (
    ShadowScheduleError,
    build_lineage,
    decide_maturity,
    epoch_key,
    is_trading_session,
    resolve_decision_cutoff,
    resolve_target_availability,
)
from ml.shadow_runtime import (
    REQUIRED_BENCHMARKS,
    ShadowProviderError,
    ShadowRuntimeConfig,
    ShadowRuntimeError,
    build_unavailable_prediction,
    build_volatility_outcome,
    build_volatility_prediction,
    load_price_frames,
    load_shadow_config,
    verify_runtime_artifacts,
)

_EASTERN = ZoneInfo("America/New_York")


class ShadowCommandError(RuntimeError):
    """A command cannot safely continue."""


class MissingModelRegistration(ShadowCommandError):
    pass


class EvidenceEpochMismatch(ShadowCommandError):
    pass


def _parse_instant(value: str, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ShadowScheduleError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowScheduleError(
            f"{name} must be a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShadowScheduleError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _current_commit() -> str:
    repository = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    clean = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--"], cwd=repository, check=False
    )
    if clean.returncode != 0:
        raise ShadowCommandError(
            "tracked working-tree changes are not represented by the current commit"
        )
    commit = result.stdout.strip()
    if len(commit) not in (40, 64) or any(c not in "0123456789abcdef" for c in commit):
        raise ShadowCommandError("git HEAD is not a canonical commit hash")
    return commit


def _failure_kind(error: BaseException) -> str:
    text = str(error).lower()
    if isinstance(error, ArtifactError) or "hash mismatch" in text:
        return "artifact_mismatch"
    if isinstance(error, MissingModelRegistration) or "not registered" in text:
        return "missing_model_registration"
    if isinstance(error, ShadowProviderError):
        return "provider_failure"
    if isinstance(error, ShadowScheduleError) or "timezone" in text or "clock" in text:
        return "clock_or_timezone_error"
    if isinstance(error, sqlite3.OperationalError) and "lock" in text:
        return "database_lock_after_bounded_retries"
    if "scheduled slot" in text or "different configuration" in text:
        return "duplicate_or_conflicting_scheduled_run"
    if isinstance(error, EvidenceEpochMismatch) or "evidence epoch" in text:
        return "evidence_epoch_mismatch"
    if "feature" in text or "stale" in text:
        return "stale_or_missing_features"
    return "unexpected_schema_or_model_output"


def _record_alert(
    store: AssistantStore,
    config: ShadowRuntimeConfig | None,
    *,
    kind: str,
    message: str,
    details: Mapping[str, Any],
    severity: str = "warning",
    alerts_jsonl: Path | None = None,
) -> dict[str, Any]:
    identity = config.schedule_key if config is not None else "unparsed-config"
    fingerprint = hashlib.sha256(
        f"ml_shadow:{identity}:{kind}".encode("utf-8")
    ).hexdigest()
    detail_payload = dict(details)
    nested_summary = detail_payload.get("summary")
    evidence_epoch = detail_payload.get("evidence_epoch")
    if evidence_epoch is None and isinstance(nested_summary, Mapping):
        evidence_epoch = nested_summary.get("evidence_epoch")
    alert = store.upsert_operational_alert(
        fingerprint=fingerprint,
        severity=severity,
        category="ml_shadow",
        message=f"{kind}: {message}",
        details={
            "kind": kind,
            "schedule_key": config.schedule_key if config is not None else None,
            "model_key": config.model_key if config is not None else None,
            **detail_payload,
            "evidence_epoch": evidence_epoch,
        },
    )
    if alerts_jsonl is not None:
        append_alerts_jsonl([alert], alerts_jsonl)
    return alert


def _set_heartbeat(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    command: str,
    summary: Mapping[str, Any],
) -> None:
    store.set_system_state(
        f"ml_shadow_{command}_heartbeat:{config.schedule_key}",
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "schedule_key": config.schedule_key,
            "ok": bool(summary.get("ok")),
            "summary": dict(summary),
        },
    )


def _load_manifest_identity(
    config: ShadowRuntimeConfig, artifact_directory: Path
) -> ModelManifest:
    manifest = load_model_manifest(
        directory=artifact_directory,
        filename=config.manifest_filename,
        model_id=config.model_id,
        model_version=config.model_version,
        expected_manifest_hash=config.manifest_hash,
    )
    if manifest.task != config.task:
        raise ShadowRuntimeError(
            f"manifest task {manifest.task!r} does not match config {config.task!r}"
        )
    return manifest


def _require_registration(
    store: AssistantStore, config: ShadowRuntimeConfig, manifest: ModelManifest
) -> dict[str, Any]:
    registration = store.get_ml_model_registration(config.model_key)
    if registration is None:
        raise MissingModelRegistration(
            f"model {config.model_key!r} is not registered; run the register command"
        )
    if registration["status"] != "shadow":
        raise MissingModelRegistration(
            f"model {config.model_key!r} registration is {registration['status']!r}, not shadow"
        )
    try:
        registered_manifest = ModelManifest.from_dict(registration["manifest"])
    except (ContractError, ValueError) as exc:
        raise MissingModelRegistration(
            f"registered manifest for {config.model_key!r} is invalid: {exc}"
        ) from exc
    if registered_manifest != manifest:
        raise MissingModelRegistration(
            f"registered manifest for {config.model_key!r} differs from the verified artifact manifest"
        )
    return registration


def _lineage(
    config: ShadowRuntimeConfig, manifest: ModelManifest, code_commit: str
) -> dict[str, str]:
    return build_lineage(
        model_artifact_hash=manifest.artifact_hash,
        evaluation_report_hash=manifest.evaluation_report_hash,
        feature_set_version=manifest.feature_set_version,
        label_version=manifest.label_version,
        data_provider_id=config.provider_id,
        configuration_hash=config.configuration_hash,
        code_commit=code_commit,
        schedule_version=config.schedule_version,
    )


def _ensure_epoch(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    manifest: ModelManifest,
    code_commit: str,
    *,
    started_at: str,
) -> dict[str, Any]:
    lineage = _lineage(config, manifest, code_commit)
    expected = epoch_key(config.model_key, config.task, lineage)
    active = store.get_active_ml_evidence_epoch(config.model_key, config.task)
    if active is not None and active["evidence_epoch"] != expected:
        raise EvidenceEpochMismatch(
            f"active evidence epoch {active['evidence_epoch']!r} has different lineage; "
            "close it explicitly before starting a new model/config/provider epoch"
        )
    existing = store.get_ml_evidence_epoch(expected)
    if existing is not None and existing["status"] == "closed":
        raise EvidenceEpochMismatch(
            f"evidence epoch {expected!r} is closed; change a lineage-bearing config "
            "or schedule version before collecting a new epoch"
        )
    return store.open_ml_evidence_epoch(
        evidence_epoch=expected,
        model_key=config.model_key,
        task=config.task,
        lineage=lineage,
        created_by="scripts/run_ml_shadow.py",
        started_at=started_at,
    )


def _resolve_epoch(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    evidence_epoch: str | None,
) -> dict[str, Any]:
    epoch = (
        store.get_ml_evidence_epoch(evidence_epoch)
        if evidence_epoch
        else store.get_active_ml_evidence_epoch(config.model_key, config.task)
    )
    if epoch is None:
        raise EvidenceEpochMismatch("no matching ML evidence epoch exists")
    if epoch["model_key"] != config.model_key or epoch["task"] != config.task:
        raise EvidenceEpochMismatch(
            f"evidence epoch {epoch['evidence_epoch']!r} belongs to another model/task"
        )
    lineage = epoch["lineage"]
    expected = {
        "configuration_hash": config.configuration_hash,
        "data_provider_id": config.provider_id,
        "schedule_version": config.schedule_version,
    }
    mismatches = {
        key: {"epoch": lineage.get(key), "config": value}
        for key, value in expected.items()
        if lineage.get(key) != value
    }
    if mismatches:
        raise EvidenceEpochMismatch(
            f"evidence epoch lineage does not match current config: {mismatches}"
        )
    return epoch


def command_register(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    artifact_directory: Path,
) -> dict[str, Any]:
    manifest, _bundle, _report = verify_runtime_artifacts(config, artifact_directory)
    registration = store.register_ml_model(config.model_key, manifest.to_dict())
    summary = {
        "ok": True,
        "command": "register",
        "model_key": config.model_key,
        "manifest_hash": config.manifest_hash,
        "artifact_hash": manifest.artifact_hash,
        "registration_status": registration["status"],
        "production_authoritative": False,
    }
    _set_heartbeat(store, config, "register", summary)
    return summary


def _scheduled_session(scheduled_for: str) -> tuple[str, str]:
    scheduled = _parse_instant(scheduled_for, "scheduled_for")
    session = scheduled.astimezone(_EASTERN).date().isoformat()
    if not is_trading_session(session):
        raise ShadowScheduleError(f"scheduled_for resolves to non-trading session {session}")
    cutoff = resolve_decision_cutoff(session)
    if scheduled < _parse_instant(cutoff, "decision_cutoff"):
        raise ShadowScheduleError(
            f"scheduled_for {scheduled_for} precedes finalized market data at {cutoff}"
        )
    return session, cutoff


def _default_scheduled_for(now: datetime | None = None) -> str | None:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ShadowScheduleError("scheduler clock must be timezone-aware")
    session = current.astimezone(_EASTERN).date().isoformat()
    if not is_trading_session(session):
        return None
    return resolve_decision_cutoff(session)


def _fail_claimed_run(
    store: AssistantStore, run: Mapping[str, Any], error: BaseException
) -> None:
    if run.get("status") != "claimed":
        return
    predictions = store.list_ml_predictions(shadow_run_id=str(run["run_id"]))
    store.complete_ml_shadow_run(
        str(run["run_id"]),
        status="failed",
        prediction_count=len(predictions),
        unavailable_count=sum(not row["available"] for row in predictions),
        error={
            "kind": _failure_kind(error),
            "exception_type": type(error).__name__,
            "detail": str(error),
        },
    )


def _record_unavailable_for_remaining_subjects(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    manifest: ModelManifest,
    run: Mapping[str, Any],
    *,
    session: str,
    cutoff: str,
    target_available_at: str,
    error: BaseException,
) -> None:
    existing = {
        row["subject_key"]
        for row in store.list_ml_predictions(shadow_run_id=str(run["run_id"]))
    }
    reason = _failure_kind(error)
    for subject in config.subjects:
        if subject in existing:
            continue
        payload = build_unavailable_prediction(
            config=config,
            manifest=manifest,
            subject=subject,
            as_of_session=session,
            generated_at=str(run["started_at"]),
            data_available_at=cutoff,
            target_available_at=target_available_at,
            reasons=(reason,),
            feature_freshness={
                "missing_count": len(manifest.ordered_feature_names),
                "stale_count": 0,
                "maximum_age_sessions": 0,
            },
            evidence_epoch=str(run["evidence_epoch"]),
            shadow_run_id=str(run["run_id"]),
            snapshot_material={
                "exception_type": type(error).__name__,
                "detail": str(error),
            },
        )
        store.record_ml_prediction(payload)


def command_predict(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    config_path: Path,
    artifact_directory: Path,
    *,
    scheduled_for: str,
    code_commit: str,
    started_at: str | None,
) -> dict[str, Any]:
    run: dict[str, Any] | None = None
    session, cutoff = _scheduled_session(scheduled_for)
    if started_at is not None and config.data_provider["kind"] != "fixture_json":
        raise ShadowCommandError(
            "--started-at is allowed only for deterministic fixture runs, never live providers"
        )
    started = _parse_instant(
        started_at or datetime.now(timezone.utc).isoformat(), "started_at"
    ).isoformat()
    scheduled_instant = _parse_instant(scheduled_for, "scheduled_for")
    existing_slot = next(
        (
            candidate
            for candidate in store.list_ml_shadow_runs(schedule_key=config.schedule_key)
            if _parse_instant(candidate["scheduled_for"], "shadow_run.scheduled_for")
            == scheduled_instant
        ),
        None,
    )
    if (
        existing_slot is None
        and _parse_instant(started, "started_at").astimezone(_EASTERN).date().isoformat()
        != session
    ):
        raise ShadowScheduleError(
            "a new run's started_at must fall on the scheduled market session in "
            "America/New_York; only an already-claimed slot may resume later"
        )
    manifest = _load_manifest_identity(config, artifact_directory)
    epoch = _ensure_epoch(
        store, config, manifest, code_commit, started_at=scheduled_instant.isoformat()
    )
    try:
        run = store.claim_ml_shadow_run(
            schedule_key=config.schedule_key,
            scheduled_for=scheduled_for,
            evidence_epoch=epoch["evidence_epoch"],
            code_commit=code_commit,
            configuration_hash=config.configuration_hash,
            started_at=started,
        )
        if run["status"] != "claimed":
            summary = {
                "ok": run["status"] == "completed",
                "command": "predict",
                "idempotent_retry": True,
                "run": run,
                "production_authoritative": False,
            }
            _set_heartbeat(store, config, "predict", summary)
            return summary

        target_available_at = resolve_target_availability(
            session, config.horizon_sessions
        )
        try:
            _require_registration(store, config, manifest)
            verified_manifest, bundle, _report = verify_runtime_artifacts(
                config, artifact_directory
            )
            frames = load_price_frames(
                config,
                config_directory=config_path.parent,
                requested_tickers=(*config.subjects, *REQUIRED_BENCHMARKS),
            )
        except Exception as exc:
            _record_unavailable_for_remaining_subjects(
                store,
                config,
                manifest,
                run,
                session=session,
                cutoff=cutoff,
                target_available_at=target_available_at,
                error=exc,
            )
            raise
        existing = {
            row["subject_key"]: row
            for row in store.list_ml_predictions(shadow_run_id=run["run_id"])
        }
        recorded = []
        fatal_error: Exception | None = None
        for subject in config.subjects:
            if subject in existing:
                recorded.append(existing[subject])
                continue
            try:
                payload = build_volatility_prediction(
                    config,
                    verified_manifest,
                    bundle,
                    frames,
                    subject=subject,
                    as_of_session=session,
                    generated_at=run["started_at"],
                    decision_cutoff=cutoff,
                    target_available_at=target_available_at,
                    evidence_epoch=epoch["evidence_epoch"],
                    shadow_run_id=run["run_id"],
                )
            except Exception as exc:
                fatal_error = fatal_error or exc
                payload = build_unavailable_prediction(
                    config=config,
                    manifest=verified_manifest,
                    subject=subject,
                    as_of_session=session,
                    generated_at=run["started_at"],
                    data_available_at=cutoff,
                    target_available_at=target_available_at,
                    reasons=(_failure_kind(exc),),
                    feature_freshness={
                        "missing_count": len(verified_manifest.ordered_feature_names),
                        "stale_count": 0,
                        "maximum_age_sessions": 0,
                    },
                    evidence_epoch=epoch["evidence_epoch"],
                    shadow_run_id=run["run_id"],
                    snapshot_material={
                        "exception_type": type(exc).__name__,
                        "detail": str(exc),
                    },
                )
            recorded.append(store.record_ml_prediction(payload))
        if fatal_error is not None:
            raise fatal_error
        unavailable = sum(not row["available"] for row in recorded)
        completed = store.complete_ml_shadow_run(
            run["run_id"],
            status="completed",
            prediction_count=len(recorded),
            unavailable_count=unavailable,
        )
        summary = {
            "ok": unavailable == 0,
            "command": "predict",
            "run": completed,
            "as_of_session": session,
            "decision_cutoff": cutoff,
            "available_count": len(recorded) - unavailable,
            "unavailable_count": unavailable,
            "production_authoritative": False,
        }
        _set_heartbeat(store, config, "predict", summary)
        return summary
    except BaseException as exc:
        if run is not None:
            try:
                _fail_claimed_run(store, run, exc)
            except Exception:
                # Preserve the original error. The outer command handler will
                # still persist an operational alert; a database-lock failure
                # may make both writes impossible until the next scheduler run.
                pass
        raise


def command_mature(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    config_path: Path,
    artifact_directory: Path,
    *,
    as_of: str | None,
    evidence_epoch: str | None,
) -> dict[str, Any]:
    epoch = _resolve_epoch(store, config, evidence_epoch)
    manifest = _load_manifest_identity(config, artifact_directory)
    if (
        epoch["lineage"].get("model_artifact_hash") != manifest.artifact_hash
        or epoch["lineage"].get("evaluation_report_hash")
        != manifest.evaluation_report_hash
        or epoch["lineage"].get("feature_set_version") != manifest.feature_set_version
        or epoch["lineage"].get("label_version") != manifest.label_version
    ):
        raise EvidenceEpochMismatch(
            "verified manifest identity does not match the evidence epoch lineage"
        )
    current = _parse_instant(
        as_of or datetime.now(timezone.utc).isoformat(), "as_of"
    ).isoformat()
    predictions = store.list_ml_predictions(evidence_epoch=epoch["evidence_epoch"])
    outcomes = {
        row["prediction_id"]: row for row in store.list_ml_prediction_outcomes()
    }
    ready: list[tuple[dict[str, Any], Any]] = []
    pending = 0
    unavailable = 0
    for prediction in predictions:
        if prediction["prediction_id"] in outcomes:
            continue
        decision = decide_maturity(prediction, now=current)
        if decision.ready:
            ready.append((prediction, decision))
        elif not prediction["available"]:
            unavailable += 1
        else:
            pending += 1
    frames: dict[str, Any] = {}
    if ready:
        frames = load_price_frames(
            config,
            config_directory=config_path.parent,
            requested_tickers=(
                *tuple(dict.fromkeys(row["subject_key"] for row, _ in ready)),
                *REQUIRED_BENCHMARKS,
            ),
        )
    matured = 0
    underfilled: list[dict[str, str]] = []
    for prediction, decision in ready:
        subject = prediction["subject_key"]
        try:
            if subject not in frames:
                raise ShadowProviderError(f"provider omitted target bars for {subject}")
            outcome = build_volatility_outcome(
                config,
                prediction,
                frames[subject],
                target_session=str(decision.target_session),
                label_version=manifest.label_version,
            )
            store.record_ml_prediction_outcome(
                prediction["prediction_id"], outcome, matured_at=current
            )
            matured += 1
        except (ShadowProviderError, ShadowRuntimeError, LabelError, ValueError) as exc:
            underfilled.append(
                {"prediction_id": prediction["prediction_id"], "reason": str(exc)}
            )
    summary = {
        "ok": not underfilled,
        "command": "mature",
        "evidence_epoch": epoch["evidence_epoch"],
        "matured_count": matured,
        "already_matured_count": len(outcomes.keys() & {p["prediction_id"] for p in predictions}),
        "pending_count": pending,
        "unavailable_count": unavailable,
        "outcome_underfill_count": len(underfilled),
        "outcome_underfill": underfilled,
        "production_authoritative": False,
    }
    _set_heartbeat(store, config, "mature", summary)
    return summary


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def command_monitor(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    *,
    evidence_epoch: str | None,
    output: Path | None,
    artifact_directory: Path | None = None,
    confirmation_spec: Path | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    epoch = _resolve_epoch(store, config, evidence_epoch)
    predictions = store.list_ml_predictions(evidence_epoch=epoch["evidence_epoch"])
    prediction_ids = {row["prediction_id"] for row in predictions}
    outcomes = [
        row
        for row in store.list_ml_prediction_outcomes()
        if row["prediction_id"] in prediction_ids
    ]
    runs = store.list_ml_shadow_runs(evidence_epoch=epoch["evidence_epoch"])
    gate = None
    if confirmation_spec is not None:
        try:
            spec_payload = json.loads(Path(confirmation_spec).read_text(encoding="utf-8"))
            spec = ExperimentSpec.from_dict(spec_payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ExperimentContractError) as exc:
            raise ShadowCommandError(f"could not load confirmation spec: {exc}") from exc
        if spec.mode != "confirmation":
            raise ShadowCommandError("--confirmation-spec must be a confirmation-mode spec")
        if spec.task != config.task:
            raise ShadowCommandError("confirmation spec task does not match shadow task")
        gate = ShadowMonitoringGate.from_confirmation_spec(spec.to_dict())
    feature_reference = None
    if artifact_directory is not None:
        _manifest, bundle, _evaluation = verify_runtime_artifacts(
            config, artifact_directory
        )
        raw_reference = bundle.get("feature_reference")
        if isinstance(raw_reference, Mapping):
            feature_reference = raw_reference
    alerts = [
        alert
        for alert in store.list_operational_alerts(status=None, limit=10_000)
        if alert.get("category") == "ml_shadow"
        and (
            not isinstance(alert.get("details"), Mapping)
            or (
                alert["details"].get("schedule_key") in (None, config.schedule_key)
                and alert["details"].get("evidence_epoch")
                in (None, epoch["evidence_epoch"])
            )
        )
    ]
    report = build_epoch_monitoring_report(
        evidence_epoch=epoch["evidence_epoch"],
        lineage_hash=epoch["lineage_hash"],
        predictions=predictions,
        outcomes=outcomes,
        runs=runs,
        operational_alerts=alerts,
        expected_subjects=config.subjects,
        feature_reference=feature_reference,
        gate=gate,
        as_of=as_of,
    )
    summary = {
        "ok": True,
        "command": "monitor",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_epoch": epoch["evidence_epoch"],
        "lineage_hash": epoch["lineage_hash"],
        "run_status_counts": dict(sorted(Counter(run["status"] for run in runs).items())),
        "prediction_count": len(predictions),
        "outcome_count": len(outcomes),
        "monitoring": report,
        "production_authoritative": False,
    }
    if output is not None:
        _atomic_json_write(output, summary)
        summary["output"] = str(output)
    _set_heartbeat(store, config, "monitor", summary)
    return summary


def _load_monitoring_report(path: Path | None) -> tuple[Mapping[str, Any] | None, str | None]:
    """Load a supplied monitoring report, returning a reason instead of raising.

    A presentation input that cannot be read must not abort the status
    command, because the failure path writes an operational alert and this
    command is required to be read-only.
    """
    if path is None:
        return None, None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"could not read monitoring report: {exc}"
    if not isinstance(payload, Mapping):
        return None, "monitoring report is not a JSON object"
    # `monitor --output` writes a CLI envelope with the real report nested
    # under "monitoring"; build_epoch_monitoring_report returns the report
    # itself. Accept either, so the file this tool emits is the file this
    # tool consumes, and unwrap only when the nested object is the one
    # carrying the verifiable report_hash.
    nested = payload.get("monitoring")
    if isinstance(nested, Mapping) and "report_hash" in nested:
        return nested, None
    return payload, None


def command_status(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    *,
    task: str | None = None,
    evidence_epoch: str | None = None,
    subject: str | None = None,
    monitoring_report: Path | None = None,
) -> dict[str, Any]:
    # `--task` is an assertion, not a selector. This runtime is configured
    # for exactly one task, so the only honest response to a mismatch is to
    # say so rather than silently show a different task's evidence.
    if task is not None and task != config.task:
        raise ShadowCommandError(
            f"--task {task!r} does not match the configured task {config.task!r}"
        )
    if subject is not None and subject not in config.subjects:
        raise ShadowCommandError(
            f"--subject {subject!r} is not a configured subject for this runtime"
        )

    registration = store.get_ml_model_registration(config.model_key)
    epochs = [
        epoch
        for epoch in store.list_ml_evidence_epochs()
        if epoch["model_key"] == config.model_key and epoch["task"] == config.task
    ]
    epoch_ids = {epoch["evidence_epoch"] for epoch in epochs}
    runs = [
        run for run in store.list_ml_shadow_runs() if run["evidence_epoch"] in epoch_ids
    ]
    predictions = store.list_ml_predictions(model_key=config.model_key)
    prediction_ids = {row["prediction_id"] for row in predictions}
    outcomes = [
        row
        for row in store.list_ml_prediction_outcomes()
        if row["prediction_id"] in prediction_ids
    ]
    alerts = [
        alert
        for alert in store.list_operational_alerts(status="open", limit=1000)
        if alert["category"] == "ml_shadow"
    ]
    active_epoch = next(
        (epoch["evidence_epoch"] for epoch in epochs if epoch["status"] == "active"),
        None,
    )

    # Presentation is strictly additive to the operational summary below. It
    # is built inside a try/except because a presentation failure must never
    # reach main()'s handler, which records an operational alert -- that is a
    # write, and this command must not write.
    selected_epoch = evidence_epoch if evidence_epoch is not None else active_epoch
    epoch_record = next(
        (epoch for epoch in epochs if epoch["evidence_epoch"] == selected_epoch), None
    )
    # The general inventory above retains the command's historical 10,000-row
    # bound.  Presentation cannot use a bounded oldest-first result, however:
    # after enough shadow sessions it would silently omit the newest attempt
    # and display a stale prediction.  Read the explicitly selected epoch in
    # full; this is one local, single-user evidence stream.
    presentation_predictions = (
        store.list_ml_predictions(
            model_key=config.model_key,
            evidence_epoch=selected_epoch,
            limit=None,
        )
        if epoch_record is not None
        else []
    )
    report_payload, report_error = _load_monitoring_report(monitoring_report)
    try:
        if evidence_epoch is not None and epoch_record is None:
            presentation = {
                "presentation_available": False,
                "reason": (
                    f"evidence epoch {evidence_epoch!r} does not belong to this model "
                    "and task"
                ),
                "observations": [],
                "promotion_blockers": ["requested_evidence_epoch_not_found"],
                "production_authoritative": False,
                "label": EXPERIMENTAL_LABEL,
            }
        else:
            presentation = build_presentation(
                task=config.task,
                model_key=config.model_key,
                evidence_epoch=selected_epoch,
                epoch_status=epoch_record["status"] if epoch_record else None,
                predictions=presentation_predictions,
                monitoring_report=report_payload,
                subjects=[subject] if subject else list(config.subjects),
            )
        if report_error is not None:
            presentation["monitoring"] = {
                "status": "rejected",
                "reason": report_error,
                "report_hash": None,
                "evidence_epoch": None,
                "promotion_blockers": [],
            }
            presentation["promotion_blockers"] = list(
                dict.fromkeys(
                    [*presentation.get("promotion_blockers", []), "monitoring_report_rejected"]
                )
            )
    except Exception as exc:
        presentation = {
            "presentation_available": False,
            "reason": f"presentation could not be built: {exc}",
            "observations": [],
            "promotion_blockers": ["presentation_unavailable"],
            "production_authoritative": False,
            "label": EXPERIMENTAL_LABEL,
        }

    return {
        "ok": True,
        "command": "status",
        "model_key": config.model_key,
        "registration_status": registration["status"] if registration else "missing",
        "active_evidence_epoch": active_epoch,
        "evidence_epoch_count": len(epochs),
        "run_status_counts": dict(sorted(Counter(run["status"] for run in runs).items())),
        "prediction_count": len(predictions),
        "outcome_count": len(outcomes),
        "open_ml_alert_count": len(alerts),
        "open_ml_alerts": alerts,
        "production_authoritative": False,
        "presentation": presentation,
    }


def command_close_epoch(
    store: AssistantStore,
    config: ShadowRuntimeConfig,
    *,
    evidence_epoch: str,
    closed_at: str | None,
) -> dict[str, Any]:
    epoch = _resolve_epoch(store, config, evidence_epoch)
    closed = store.close_ml_evidence_epoch(
        epoch["evidence_epoch"],
        closed_at=closed_at or datetime.now(timezone.utc).isoformat(),
    )
    return {
        "ok": True,
        "command": "close-epoch",
        "epoch": closed,
        "production_authoritative": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate the non-authoritative ML shadow evidence loop."
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--alerts-jsonl", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("register", help="Verify and register one shadow model.")

    predict = subparsers.add_parser("predict", help="Run one scheduled prediction slot.")
    predict.add_argument(
        "--scheduled-for",
        help="Timezone-aware slot. Defaults to today's exact NYSE close.",
    )
    predict.add_argument("--code-commit")
    predict.add_argument(
        "--started-at",
        help="Fixture-only deterministic clock. Live providers always use now.",
    )

    mature = subparsers.add_parser("mature", help="Attach newly observable outcomes once.")
    mature.add_argument("--as-of", help="Timezone-aware instant; defaults to now.")
    mature.add_argument("--evidence-epoch")

    monitor = subparsers.add_parser("monitor", help="Build one read-only epoch report.")
    monitor.add_argument("--evidence-epoch")
    monitor.add_argument("--output", type=Path)
    monitor.add_argument(
        "--confirmation-spec",
        type=Path,
        help=(
            "Frozen confirmation spec containing task_parameters.shadow_monitoring_gate. "
            "Without it every sample-dependent conclusion is explicitly insufficient."
        ),
    )
    monitor.add_argument(
        "--as-of",
        help="Timezone-aware report cutoff; defaults to now.",
    )

    status = subparsers.add_parser(
        "status",
        help=(
            "Show registration, epoch, run, and alert status, plus the read-only "
            "experimental model observation. Never writes."
        ),
    )
    status.add_argument(
        "--task",
        help=(
            "Assert the configured task (presentation alias). A mismatch is an "
            "error, not a selector for a different task."
        ),
    )
    status.add_argument(
        "--evidence-epoch",
        help="Epoch to display. Defaults to the active epoch; epochs are never pooled.",
    )
    status.add_argument("--subject", help="Display one configured subject only.")
    status.add_argument(
        "--monitoring-report",
        type=Path,
        help=(
            "Monitoring report JSON to display alongside the observation. Its "
            "report_hash and evidence epoch are verified before it is trusted."
        ),
    )

    close = subparsers.add_parser("close-epoch", help="Explicitly close one evidence epoch.")
    close.add_argument("--evidence-epoch", required=True)
    close.add_argument("--closed-at")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AssistantStore(args.database)
    config: ShadowRuntimeConfig | None = None
    try:
        config, _payload = load_shadow_config(args.config)
        if args.command == "register":
            summary = command_register(store, config, args.artifact_dir)
        elif args.command == "predict":
            scheduled_for = args.scheduled_for or _default_scheduled_for()
            if scheduled_for is None:
                summary = {
                    "ok": True,
                    "command": "predict",
                    "skipped": True,
                    "reason": "today is not an NYSE trading session",
                    "production_authoritative": False,
                }
                _set_heartbeat(store, config, "predict", summary)
            else:
                code_commit = args.code_commit or _current_commit()
                summary = command_predict(
                    store,
                    config,
                    args.config,
                    args.artifact_dir,
                    scheduled_for=scheduled_for,
                    code_commit=code_commit,
                    started_at=args.started_at,
                )
        elif args.command == "mature":
            summary = command_mature(
                store,
                config,
                args.config,
                args.artifact_dir,
                as_of=args.as_of,
                evidence_epoch=args.evidence_epoch,
            )
        elif args.command == "monitor":
            summary = command_monitor(
                store,
                config,
                evidence_epoch=args.evidence_epoch,
                output=args.output,
                artifact_directory=args.artifact_dir,
                confirmation_spec=args.confirmation_spec,
                as_of=args.as_of,
            )
        elif args.command == "status":
            summary = command_status(
                store,
                config,
                task=args.task,
                evidence_epoch=args.evidence_epoch,
                subject=args.subject,
                monitoring_report=args.monitoring_report,
            )
        else:
            summary = command_close_epoch(
                store,
                config,
                evidence_epoch=args.evidence_epoch,
                closed_at=args.closed_at,
            )
    except (Exception, KeyboardInterrupt) as exc:
        kind = _failure_kind(exc)
        alert_error = None
        if args.command == "status":
            # Status is the dedicated read-only surface.  Even invalid CLI
            # assertions or corrupt presentation inputs must not turn a read
            # into an operational-alert write (or a JSONL fallback write).
            alert_id = None
            alert_error = "status is read-only; alert persistence was skipped"
        else:
            try:
                alert = _record_alert(
                    store,
                    config,
                    kind=kind,
                    message=str(exc),
                    details={"command": args.command, "exception_type": type(exc).__name__},
                    severity="critical" if kind in {"artifact_mismatch", "database_lock_after_bounded_retries"} else "warning",
                    alerts_jsonl=args.alerts_jsonl,
                )
                alert_id = alert["alert_id"]
            except Exception as persist_error:
                alert_id = None
                alert_error = f"{type(persist_error).__name__}: {persist_error}"
                if args.alerts_jsonl is not None:
                    try:
                        append_alerts_jsonl(
                            [
                                {
                                    "category": "ml_shadow",
                                    "severity": (
                                        "critical"
                                        if kind
                                        in {
                                            "artifact_mismatch",
                                            "database_lock_after_bounded_retries",
                                        }
                                        else "warning"
                                    ),
                                    "kind": kind,
                                    "message": str(exc),
                                    "command": args.command,
                                    "seen_at": datetime.now(timezone.utc).isoformat(),
                                    "database_alert_error": alert_error,
                                }
                            ],
                            args.alerts_jsonl,
                        )
                        alert_error += "; durable JSONL fallback written"
                    except Exception as fallback_error:
                        alert_error += (
                            "; JSONL fallback failed: "
                            f"{type(fallback_error).__name__}: {fallback_error}"
                        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": args.command,
                    "error_kind": kind,
                    "error": f"{type(exc).__name__}: {exc}",
                    "alert_id": alert_id,
                    "alert_error": alert_error,
                    "production_authoritative": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    if config is not None and summary.get("unavailable_count", 0):
        _record_alert(
            store,
            config,
            kind="stale_or_missing_features",
            message=f"{summary['unavailable_count']} shadow subject attempt(s) unavailable",
            details=summary,
            alerts_jsonl=args.alerts_jsonl,
        )
    if config is not None and summary.get("outcome_underfill_count", 0):
        _record_alert(
            store,
            config,
            kind="outcome_underfill",
            message=f"{summary['outcome_underfill_count']} mature outcome(s) underfilled",
            details=summary,
            alerts_jsonl=args.alerts_jsonl,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
