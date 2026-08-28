from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.contracts import (
    CanonicalSourceEvent,
    DataAvailabilityQuality,
    EventState,
    NormalizedRating,
    RevisionKind,
)
from research.analyst_revisions_v2.dataset import (
    CleanGitLineage,
    capture_clean_git_lineage,
    compute_package_source_sha256,
)
from research.analyst_revisions_v2.evidence import SourceRowLocator
from research.analyst_revisions_v2.normalization import (
    NormalizationProvenance,
    NormalizationRefusal,
    NormalizationResult,
    RefusalReason,
)
from research.analyst_revisions_v2.snapshot import (
    SNAPSHOT_MANIFEST_SCHEMA,
    VerifiedSnapshot,
    load_verified_snapshot,
)


FIXED_VERIFIED_AT = "2026-08-26T12:00:00.000000Z"
CONFIG_HASH = "1" * 64
CODE_HASH = "2" * 64
EVIDENCE_HASH = "3" * 64
PROVIDER_CONTRACT_HASH = "4" * 64
COMMIT = "a" * 40


def raw_row(event_year: int, row_id: str) -> dict[str, Any]:
    return {
        "event_year": event_year,
        "provider_row_id": row_id,
        "provider_event_id": f"provider-event-{row_id}",
        "provider_version_id": f"provider-version-{row_id}",
        "identity_mapping_status": "matched",
        "issuer_id": f"issuer-{row_id}",
        "security_id": f"security-{row_id}",
        "share_class_id": f"share-class-{row_id}",
        "availability_evidence_status": "present",
        "rating_ontology_status": "valid",
    }


def refusal_raw_row(event_year: int, row_id: str) -> dict[str, Any]:
    row = raw_row(event_year, row_id)
    row["identity_mapping_status"] = "missing"
    row.pop("issuer_id")
    row.pop("security_id")
    row.pop("share_class_id")
    return row


def write_snapshot(
    root: Path,
    *,
    rows_by_year: dict[int, list[dict[str, Any]]],
    requested_first_year: int | None = None,
    requested_last_year: int | None = None,
    complete: bool = True,
    pages_per_year: int = 1,
    snapshot_id: str = "snapshot-main",
    provider_contract_id: str = "provider-contract-v1",
    provider_contract_sha256: str = PROVIDER_CONTRACT_HASH,
    captured_at: str = "2026-08-26T11:59:00.000000Z",
) -> Path:
    root.mkdir(parents=True)
    if rows_by_year:
        first = min(rows_by_year) if requested_first_year is None else requested_first_year
        last = max(rows_by_year) if requested_last_year is None else requested_last_year
    else:
        first = 2020 if requested_first_year is None else requested_first_year
        last = first if requested_last_year is None else requested_last_year
    partitions: list[dict[str, Any]] = []
    total = 0
    for year in sorted(rows_by_year):
        year_rows = rows_by_year[year]
        chunks: list[list[dict[str, Any]]] = []
        if pages_per_year == 1:
            chunks = [year_rows]
        else:
            for index in range(pages_per_year):
                chunks.append(year_rows[index::pages_per_year])
        pages: list[dict[str, Any]] = []
        for page_number, rows in enumerate(chunks, start=1):
            relative = f"pages/year={year}/page-{page_number:04d}.jsonl"
            path = root / Path(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = b"".join(canonical_json_bytes(row) for row in rows)
            path.write_bytes(payload)
            pages.append(
                {
                    "page_number": page_number,
                    "filename": relative,
                    "sha256": sha256_bytes(payload),
                    "row_count": len(rows),
                }
            )
        partitions.append({"year": year, "row_count": len(year_rows), "pages": pages})
        total += len(year_rows)
    manifest = {
        "schema": SNAPSHOT_MANIFEST_SCHEMA,
        "snapshot_id": snapshot_id,
        "provider_contract_id": provider_contract_id,
        "provider_contract_sha256": provider_contract_sha256,
        "captured_at": captured_at,
        "complete": complete,
        "terminated_naturally": complete,
        "requested_first_year": first,
        "requested_last_year": last,
        "partition_key": "event_year",
        "source_row_count": total,
        "partitions": partitions,
    }
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return root


def read_manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))


def verified_snapshot(
    root: Path,
    row_count: int = 1,
    *,
    event_year: int = 2020,
    refusal_row_indices: frozenset[int] = frozenset(),
) -> VerifiedSnapshot:
    rows = [
        (
            refusal_raw_row(event_year, f"row-{index}")
            if index in refusal_row_indices
            else raw_row(event_year, f"row-{index}")
        )
        for index in range(row_count)
    ]
    write_snapshot(root, rows_by_year={event_year: rows})
    return load_verified_snapshot(root, verified_at=FIXED_VERIFIED_AT)


def event_for(
    locator: SourceRowLocator,
    *,
    provider_event_id: str = "provider-event-1",
    event_version_id: str = "version-0",
    revision_sequence: int = 0,
    supersedes_event_version_id: str | None = None,
    revision_kind: RevisionKind = RevisionKind.ORIGINAL,
    event_state: EventState = EventState.ACTIVE_ORIGINAL,
    effective_at: str = "2020-01-02T14:00:00.000000Z",
    public_at: str | None = "2020-01-02T15:00:00.000000Z",
    public_date: str | None = None,
    available_at: str = "2020-01-02T15:00:00.000000Z",
    ingested_at: str = "2020-01-02T15:01:00.000000Z",
    availability_quality: DataAvailabilityQuality | None = None,
    issuer_id: str = "issuer-1",
    security_id: str = "security-1",
    share_class_id: str = "share-class-1",
    historical_ticker: str = "AAA",
    normalized_rating: NormalizedRating | None = NormalizedRating.BUY,
    raw_rating: str = "Buy",
    ticker_valid_from: str = "2019-01-01",
    ticker_valid_to: str | None = "2021-01-01",
    identity_mapping_valid_from: str = "2019-01-01",
    identity_mapping_valid_to: str | None = "2021-01-01",
    identity_mapping_available_at: str = "2020-01-01T00:00:00.000000Z",
    rating_ontology_valid_from: str = "2019-01-01",
    rating_ontology_valid_to: str | None = "2021-01-01",
    rating_ontology_available_at: str = "2020-01-01T00:00:00.000000Z",
    config_hash: str = CONFIG_HASH,
    code_hash: str = CODE_HASH,
    producing_commit: str = COMMIT,
) -> CanonicalSourceEvent:
    from research.analyst_revisions_v2.availability import derive_event_availability
    from research.analyst_revisions_v2.canonical import format_utc_timestamp

    if public_at is None:
        if public_date is None:
            raise ValueError("date-only helper events require public_date")
        eligibility = derive_event_availability(
            evidence_id="timing-evidence-1", public_date=public_date
        )
        resolved_availability_quality = (
            DataAvailabilityQuality.PROVIDER_RECEIPT
            if availability_quality is None
            else availability_quality
        )
    else:
        public_for_eligibility = datetime.fromisoformat(
            public_at.replace("Z", "+00:00")
        ).isoformat()
        eligibility = derive_event_availability(
            evidence_id="timing-evidence-1", public_at=public_for_eligibility
        )
        if public_date is not None and public_date != eligibility.public_date:
            raise ValueError("public_date disagrees with exact public_at")
        public_date = eligibility.public_date
        resolved_availability_quality = (
            DataAvailabilityQuality.PROVIDER_PUBLICATION
            if availability_quality is None
            else availability_quality
        )
    eligible_at = format_utc_timestamp(
        datetime.fromisoformat(eligibility.eligible_at.replace("Z", "+00:00"))
    )
    return CanonicalSourceEvent.create(
        source_locator=locator,
        provider_contract_id="provider-contract-v1",
        provider_contract_sha256=PROVIDER_CONTRACT_HASH,
        provider_event_id=provider_event_id,
        event_version_id=event_version_id,
        revision_sequence=revision_sequence,
        supersedes_event_version_id=supersedes_event_version_id,
        revision_kind=revision_kind,
        event_state=event_state,
        effective_at=effective_at,
        public_at=public_at,
        public_date=public_date,
        available_at=available_at,
        ingested_at=ingested_at,
        availability_quality=resolved_availability_quality,
        availability_evidence_sha256=EVIDENCE_HASH,
        eligibility_quality=eligibility.quality,
        eligibility_evidence_id=eligibility.evidence_id,
        eligible_session=eligibility.eligible_session,
        eligible_at=eligible_at,
        provider_firm_id="provider-firm-1",
        provider_analyst_id="provider-analyst-1",
        raw_firm_name="Broker One",
        raw_analyst_name="Analyst One",
        institution_id="institution-1",
        analyst_id="analyst-1",
        issuer_id=issuer_id,
        security_id=security_id,
        share_class_id=share_class_id,
        historical_ticker=historical_ticker,
        ticker_valid_from=ticker_valid_from,
        ticker_valid_to=ticker_valid_to,
        identity_mapping_version_id="identity-map-1",
        identity_mapping_valid_from=identity_mapping_valid_from,
        identity_mapping_valid_to=identity_mapping_valid_to,
        identity_mapping_available_at=identity_mapping_available_at,
        identity_mapping_evidence_sha256=EVIDENCE_HASH,
        raw_rating=raw_rating,
        normalized_rating=normalized_rating,
        rating_ontology_version_id="ontology-1",
        rating_ontology_valid_from=rating_ontology_valid_from,
        rating_ontology_valid_to=rating_ontology_valid_to,
        rating_ontology_available_at=rating_ontology_available_at,
        rating_ontology_evidence_sha256=EVIDENCE_HASH,
        normalizer_config_sha256=config_hash,
        normalizer_code_sha256=code_hash,
        producing_commit=producing_commit,
    )


def refusal_for(
    locator: SourceRowLocator,
    *,
    config_hash: str = CONFIG_HASH,
    code_hash: str = CODE_HASH,
    producing_commit: str = COMMIT,
    reason: RefusalReason = RefusalReason.MISSING_IDENTITY_MAPPING,
) -> NormalizationRefusal:
    return NormalizationRefusal.create(
        source_locator=locator,
        reason=reason,
        normalizer_config_sha256=config_hash,
        normalizer_code_sha256=code_hash,
        producing_commit=producing_commit,
    )


def historical_event_for(
    locator: SourceRowLocator,
    *,
    event_year: int,
    config_hash: str = CONFIG_HASH,
    code_hash: str = CODE_HASH,
    producing_commit: str = COMMIT,
) -> CanonicalSourceEvent:
    return event_for(
        locator,
        effective_at=f"{event_year:04d}-06-15T14:00:00.000000Z",
        public_at=f"{event_year:04d}-06-15T15:00:00.000000Z",
        available_at=f"{event_year:04d}-06-15T15:00:00.000000Z",
        ingested_at=f"{event_year:04d}-06-15T15:01:00.000000Z",
        ticker_valid_from=f"{event_year - 2:04d}-01-01",
        ticker_valid_to=f"{event_year + 2:04d}-01-01",
        identity_mapping_valid_from=f"{event_year - 2:04d}-01-01",
        identity_mapping_valid_to=f"{event_year + 2:04d}-01-01",
        identity_mapping_available_at=(
            f"{event_year:04d}-01-01T00:00:00.000000Z"
        ),
        rating_ontology_valid_from=f"{event_year - 2:04d}-01-01",
        rating_ontology_valid_to=f"{event_year + 2:04d}-01-01",
        rating_ontology_available_at=(
            f"{event_year:04d}-01-01T00:00:00.000000Z"
        ),
        config_hash=config_hash,
        code_hash=code_hash,
        producing_commit=producing_commit,
    )


def result_for(
    snapshot: VerifiedSnapshot,
    *,
    events: Iterable[CanonicalSourceEvent],
    refusals: Iterable[NormalizationRefusal] = (),
    config_hash: str = CONFIG_HASH,
    code_hash: str = CODE_HASH,
    producing_commit: str = COMMIT,
) -> NormalizationResult:
    provenance = NormalizationProvenance.create(
        snapshot=snapshot,
        normalizer_config_sha256=config_hash,
        normalizer_code_sha256=code_hash,
        evidence_epoch_id="evidence-epoch-1",
        build_recipe_id="normalizer-recipe-1",
        producing_commit=producing_commit,
    )
    return NormalizationResult(
        snapshot=snapshot,
        events=tuple(events),
        refusals=tuple(refusals),
        provenance=provenance,
    )


def run_git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def clean_source_repository(tmp_path: Path, workspace_root: Path) -> tuple[Path, CleanGitLineage, str]:
    repository = tmp_path / "source-repository"
    package_target = repository / "research" / "analyst_revisions_v2"
    package_target.parent.mkdir(parents=True)
    shutil.copytree(
        workspace_root / "research" / "analyst_revisions_v2",
        package_target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (repository / "research" / "__init__.py").write_text("", encoding="utf-8")
    run_git(repository, "init", "--quiet")
    run_git(repository, "config", "user.email", "arv2-tests@example.invalid")
    run_git(repository, "config", "user.name", "ARV2 Tests")
    run_git(repository, "add", "research")
    run_git(repository, "commit", "--quiet", "-m", "clean source fixture")
    lineage = capture_clean_git_lineage(repository)
    return repository, lineage, compute_package_source_sha256(repository)
