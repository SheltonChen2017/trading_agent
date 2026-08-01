"""Build an ML-LR-7 read-only promotion-review dossier.

This command reads immutable research/shadow artifacts and operational state,
writes one content-hashed JSON report, and exits.  It has no registry import,
no status transition, and no proposal/broker/execution write path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.proposal_status import EXECUTED, RECONCILING, SUBMISSION_UNKNOWN, SUBMITTING
from assistant.storage import AssistantStore
from ml.hashing import hash_bytes
from ml.experiment_contracts import ExperimentContractError, ExperimentSpec
from ml.contracts import ContractError, DatasetManifest
from ml.promotion import (
    PromotionDossierError,
    build_promotion_dossier,
    evidence_snapshot,
)
from ml.shadow_runtime import load_shadow_config, verify_runtime_artifacts


def _read_json(path: Path, name: str) -> tuple[dict[str, Any], str]:
    try:
        raw = Path(path).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionDossierError(f"could not read {name} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PromotionDossierError(f"{name} must contain one JSON object")
    return payload, hash_bytes(raw)


def _optional_json(path: Path | None, name: str) -> dict[str, Any] | None:
    if path is None:
        return None
    payload, digest = _read_json(path, name)
    return evidence_snapshot(sha256=digest, result=payload)


def _optional_experiment_spec(
    path: Path | None, name: str, expected_mode: str
) -> dict[str, Any] | None:
    snapshot = _optional_json(path, name)
    if snapshot is None:
        return None
    try:
        spec = ExperimentSpec.from_dict(snapshot["result"])
    except ExperimentContractError as exc:
        raise PromotionDossierError(f"invalid {name}: {exc}") from exc
    if spec.mode != expected_mode:
        raise PromotionDossierError(
            f"{name} must use mode={expected_mode!r}, got {spec.mode!r}"
        )
    snapshot["result"] = spec.to_dict()
    return snapshot


def _optional_dataset_manifest(
    path: Path | None,
) -> dict[str, Any] | None:
    snapshot = _optional_json(path, "dataset manifest")
    if snapshot is None:
        return None
    try:
        manifest = DatasetManifest.from_dict(snapshot["result"])
    except ContractError as exc:
        raise PromotionDossierError(f"invalid dataset manifest: {exc}") from exc
    snapshot["result"] = manifest.to_dict()
    return snapshot


def _optional_file(path: Path | None, name: str) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PromotionDossierError(f"could not read {name} {path}: {exc}") from exc
    result: dict[str, Any] = {
        "filename": Path(path).name,
        "byte_count": len(raw),
        "format": Path(path).suffix.lower().lstrip(".") or "binary",
    }
    if Path(path).suffix.lower() == ".json":
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PromotionDossierError(f"{name} has a .json suffix but is invalid: {exc}") from exc
        if isinstance(parsed, Mapping):
            result.update(dict(parsed))
        else:
            result["record_count"] = len(parsed) if isinstance(parsed, list) else None
    return evidence_snapshot(sha256=hash_bytes(raw), result=result)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only, non-authoritative ML promotion dossier."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--evidence-epoch", required=True)
    parser.add_argument("--discovery-spec", type=Path)
    parser.add_argument("--discovery-report", type=Path)
    parser.add_argument("--confirmation-spec", type=Path)
    parser.add_argument(
        "--confirmation-report",
        type=Path,
        help="Defaults to the model's hash-verified evaluation report.",
    )
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--availability-manifest", type=Path)
    parser.add_argument("--universe-manifest", type=Path)
    parser.add_argument("--economic-simulation", type=Path)
    parser.add_argument("--monitoring-report", type=Path)
    parser.add_argument("--proposed-adapter-scope", type=Path)
    parser.add_argument("--known-limitation", action="append", default=[])
    parser.add_argument("--generated-at", help="Timezone-aware; defaults to now.")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def command_build(args: argparse.Namespace) -> dict[str, Any]:
    store = AssistantStore(args.database)
    config, _ = load_shadow_config(args.config)
    manifest, _bundle, verified_report = verify_runtime_artifacts(
        config, args.artifact_dir
    )
    epoch = store.get_ml_evidence_epoch(args.evidence_epoch)
    if epoch is None:
        raise PromotionDossierError(
            f"evidence epoch {args.evidence_epoch!r} does not exist"
        )
    if epoch["model_key"] != config.model_key or epoch["task"] != config.task:
        raise PromotionDossierError(
            "evidence epoch belongs to a different model or task"
        )

    report_path = args.confirmation_report or (
        Path(args.artifact_dir) / config.evaluation_report_filename
    )
    evidence: dict[str, Any] = {
        "discovery_specification": _optional_experiment_spec(
            args.discovery_spec, "discovery spec", "discovery"
        ),
        "discovery_report": _optional_json(args.discovery_report, "discovery report"),
        "confirmation_specification": _optional_experiment_spec(
            args.confirmation_spec, "confirmation spec", "confirmation"
        ),
        "confirmation_report": _optional_json(report_path, "confirmation report"),
        "dataset_manifest": _optional_dataset_manifest(args.dataset_manifest),
        "availability_manifest": _optional_file(args.availability_manifest, "availability manifest"),
        "universe_manifest": _optional_file(args.universe_manifest, "universe manifest"),
        "model_manifest": evidence_snapshot(
            sha256=config.manifest_hash, result=manifest.to_dict()
        ),
        "model_artifact": evidence_snapshot(
            sha256=manifest.artifact_hash,
            result={
                "model_id": manifest.model_id,
                "model_version": manifest.model_version,
                "algorithm": manifest.algorithm,
                "artifact_hash": manifest.artifact_hash,
            },
        ),
        "economic_simulation": _optional_json(args.economic_simulation, "economic simulation"),
        "shadow_monitoring_report": _optional_json(args.monitoring_report, "monitoring report"),
    }
    # `verify_runtime_artifacts` already proved the default report hash; pin it
    # again here so an explicit different report cannot masquerade as the
    # model's evaluation.
    if (
        report_path == Path(args.artifact_dir) / config.evaluation_report_filename
        and evidence["confirmation_report"]["result"] != dict(verified_report)
    ):
        raise PromotionDossierError("verified evaluation report changed while building dossier")
    if evidence["confirmation_report"]["sha256"] != manifest.evaluation_report_hash:
        raise PromotionDossierError(
            "confirmation report hash does not match the model manifest's evaluation report"
        )

    scope: dict[str, Any] = {}
    if args.proposed_adapter_scope is not None:
        scope, _scope_hash = _read_json(
            args.proposed_adapter_scope, "proposed adapter scope"
        )
    unresolved_alerts = [
        alert
        for alert in store.list_operational_alerts(status="open", limit=10_000)
        if alert.get("category") == "ml_shadow"
        and (
            not isinstance(alert.get("details"), Mapping)
            or (
                alert["details"].get("schedule_key") in (None, config.schedule_key)
                and alert["details"].get("evidence_epoch")
                in (None, args.evidence_epoch)
            )
        )
    ]
    ambiguous = store.list_proposals_by_statuses(
        (SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING, EXECUTED), limit=10_000
    )
    incidents = [
        {"kind": "ml_operational_alert", **alert} for alert in unresolved_alerts
    ] + [
        {
            "kind": "ambiguous_broker_outcome",
            "proposal_id": proposal.get("proposal_id"),
            "status": proposal.get("status"),
            "updated_at": proposal.get("updated_at"),
        }
        for proposal in ambiguous
    ]
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    dossier = build_promotion_dossier(
        generated_at=generated_at,
        task=config.task,
        model_key=config.model_key,
        evidence_epoch=args.evidence_epoch,
        evidence=evidence,
        known_limitations=tuple(args.known_limitation),
        unresolved_incidents=incidents,
        proposed_adapter_scope=scope,
    )
    payload = dossier.to_dict()
    _atomic_write(args.output, payload)
    return {
        "ok": True,
        "output": str(args.output),
        "dossier_id": dossier.dossier_id,
        "dossier_hash": payload["dossier_hash"],
        "eligible_for_separate_owner_review": dossier.eligible_for_separate_owner_review,
        "promotion_blockers": list(dossier.promotion_blockers),
        "production_authoritative": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = command_build(args)
    except (PromotionDossierError, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "production_authoritative": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
