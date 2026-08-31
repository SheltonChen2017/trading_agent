"""One-and-only-one normalization disposition for every verified source row.

The public constructor intentionally accepts a :class:`VerifiedSnapshot`, not
an untyped manifest digest.  That prevents a caller from blessing loose event
and refusal lists after merely copying a hash out of a manifest.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping

from . import CANONICAL_EVENT_SCHEMA
from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    parse_utc_timestamp,
    require_exact_keys,
    require_git_object,
    require_identifier,
    require_sha256,
    sha256_bytes,
)
from .contracts import CanonicalSourceEvent, validate_revision_lineage
from .evidence import SourceRowLocator, derive_refusal_id
from .provider_history import classify_provider_era
from .snapshot import (
    SNAPSHOT_MANIFEST_SCHEMA,
    VerifiedSnapshot,
    VerifiedSourceRow,
    revalidate_verified_snapshot,
)


REFUSAL_SCHEMA = "arv2-normalization-refusal-v1"
NORMALIZATION_RESULT_SCHEMA = "arv2-normalization-result-v1"
BUILD_RECIPE_SCHEMA = "arv2-normalization-build-recipe-v1"
REFUSAL_EVIDENCE_SCHEMA = "arv2-normalization-refusal-evidence-v1"
ACCEPTED_EVENT_ZERO_ACCESS_REASON = (
    "accepted canonical events are zero-access until an independently reviewed "
    "provider-contract-specific deterministic raw-to-canonical derivation exists"
)

_REFUSAL_KEYS = frozenset(
    {
        "schema",
        "refusal_id",
        "source_locator",
        "reason",
        "evidence_sha256",
        "normalizer_config_sha256",
        "normalizer_code_sha256",
        "producing_commit",
    }
)


class NormalizationContractError(CanonicalEvidenceError):
    """A normalization result is incomplete, ambiguous, or unbound."""


class RefusalReason(str, Enum):
    PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013 = (
        "provider_backfill_semantics_unverified_pre_2013"
    )
    MISSING_PROVIDER_EVENT_ID = "missing_provider_event_id"
    MISSING_PROVIDER_VERSION_ID = "missing_provider_version_id"
    INVALID_PROVIDER_LINEAGE = "invalid_provider_lineage"
    MISSING_IDENTITY_MAPPING = "missing_identity_mapping"
    AMBIGUOUS_IDENTITY_MAPPING = "ambiguous_identity_mapping"
    MISSING_AVAILABILITY_EVIDENCE = "missing_availability_evidence"
    INVALID_RATING_ONTOLOGY = "invalid_rating_ontology"
    INVALID_SOURCE_ROW = "invalid_source_row"
    UNSUPPORTED_PROVIDER_SEMANTICS = "unsupported_provider_semantics"


def _refusal_reason(value: object) -> RefusalReason:
    if not isinstance(value, str):
        raise NormalizationContractError("refusal reason must be a string enum")
    try:
        return RefusalReason(value)
    except ValueError as exc:
        raise NormalizationContractError(f"unknown refusal reason: {value!r}") from exc


def _refusal_evidence_sha256(
    source_locator: SourceRowLocator, reason: RefusalReason
) -> str:
    """Bind refusal evidence to the exact raw row, source position and reason."""
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": REFUSAL_EVIDENCE_SCHEMA,
                "source_locator": source_locator.to_record(),
                "raw_row_sha256": source_locator.raw_row_sha256,
                "reason": reason.value,
            }
        )
    )


@dataclasses.dataclass(frozen=True, init=False)
class NormalizationRefusal:
    """Auditable terminal refusal to normalize exactly one source row."""

    schema: str
    refusal_id: str
    source_locator: SourceRowLocator
    reason: RefusalReason
    evidence_sha256: str
    normalizer_config_sha256: str
    normalizer_code_sha256: str
    producing_commit: str

    @classmethod
    def create(
        cls,
        *,
        source_locator: SourceRowLocator,
        reason: RefusalReason,
        evidence_sha256: str | None = None,
        normalizer_config_sha256: str,
        normalizer_code_sha256: str,
        producing_commit: str,
    ) -> "NormalizationRefusal":
        if not isinstance(reason, RefusalReason):
            raise NormalizationContractError("reason must be a RefusalReason")
        if type(source_locator) is not SourceRowLocator:
            raise NormalizationContractError(
                "refusal source_locator must be a SourceRowLocator"
            )
        expected_evidence = _refusal_evidence_sha256(source_locator, reason)
        if evidence_sha256 is not None and evidence_sha256 != expected_evidence:
            raise NormalizationContractError(
                "refusal evidence must be deterministically bound to its raw source row"
            )
        return _normalization_refusal(
            schema=REFUSAL_SCHEMA,
            refusal_id=derive_refusal_id(source_locator, reason.value),
            source_locator=source_locator,
            reason=reason,
            evidence_sha256=expected_evidence,
            normalizer_config_sha256=normalizer_config_sha256,
            normalizer_code_sha256=normalizer_code_sha256,
            producing_commit=producing_commit,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "refusal_id": self.refusal_id,
            "source_locator": self.source_locator.to_record(),
            "reason": self.reason.value,
            "evidence_sha256": self.evidence_sha256,
            "normalizer_config_sha256": self.normalizer_config_sha256,
            "normalizer_code_sha256": self.normalizer_code_sha256,
            "producing_commit": self.producing_commit,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "NormalizationRefusal":
        require_exact_keys(record, _REFUSAL_KEYS, "normalization refusal")
        fields = dict(record)
        raw_locator = fields.pop("source_locator")
        if not isinstance(raw_locator, Mapping):
            raise NormalizationContractError("refusal source_locator must be an object")
        fields["source_locator"] = SourceRowLocator.from_record(raw_locator)
        fields["reason"] = _refusal_reason(fields["reason"])
        return _normalization_refusal(**fields)


def _normalization_refusal(
    *,
    schema: str,
    refusal_id: str,
    source_locator: SourceRowLocator,
    reason: RefusalReason,
    evidence_sha256: str,
    normalizer_config_sha256: str,
    normalizer_code_sha256: str,
    producing_commit: str,
) -> NormalizationRefusal:
    if schema != REFUSAL_SCHEMA:
        raise NormalizationContractError("unsupported normalization refusal schema")
    if type(source_locator) is not SourceRowLocator:
        raise NormalizationContractError(
            "refusal source_locator must be a SourceRowLocator"
        )
    if not isinstance(reason, RefusalReason):
        raise NormalizationContractError("reason must be a RefusalReason")
    expected_id = derive_refusal_id(source_locator, reason.value)
    if refusal_id != expected_id:
        raise NormalizationContractError(
            "refusal_id does not match immutable source/reason"
        )
    expected_evidence = _refusal_evidence_sha256(source_locator, reason)
    if evidence_sha256 != expected_evidence:
        raise NormalizationContractError(
            "refusal evidence is not bound to the exact raw source row and reason"
        )
    require_sha256(normalizer_config_sha256, "normalizer_config_sha256")
    require_sha256(normalizer_code_sha256, "normalizer_code_sha256")
    require_git_object(producing_commit, "producing_commit")
    value = object.__new__(NormalizationRefusal)
    for name, item in {
        "schema": schema,
        "refusal_id": refusal_id,
        "source_locator": source_locator,
        "reason": reason,
        "evidence_sha256": evidence_sha256,
        "normalizer_config_sha256": normalizer_config_sha256,
        "normalizer_code_sha256": normalizer_code_sha256,
        "producing_commit": producing_commit,
    }.items():
        object.__setattr__(value, name, item)
    return value


def _missing_text(record: Mapping[str, Any], key: str) -> bool:
    value = record.get(key)
    return value is None or (isinstance(value, str) and not value.strip())


def _invalid_lineage(record: Mapping[str, Any]) -> bool:
    if not any(
        key in record
        for key in (
            "revision_sequence",
            "supersedes_event_version_id",
            "revision_kind",
        )
    ):
        return False
    sequence = record.get("revision_sequence")
    supersedes = record.get("supersedes_event_version_id")
    kind = record.get("revision_kind")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        return True
    if sequence == 0 and supersedes is not None:
        return True
    if sequence > 0 and _missing_text(record, "supersedes_event_version_id"):
        return True
    return kind not in {"original", "correction", "withdrawal", "tombstone"}


def _applicable_refusal_reason(source_row: VerifiedSourceRow) -> RefusalReason | None:
    """Derive the one admissible terminal refusal from authenticated raw data.

    The precedence is deliberate: a row cannot be relabelled with a later,
    more discretionary reason when an earlier objective defect applies.
    Reasons that require provider-specific evidence are admitted only through
    explicit fields in the authenticated raw row; otherwise normalization
    must fail closed instead of inventing an explanation.
    """
    record = source_row.parsed_record()
    era = classify_provider_era(
        f"{source_row.locator.partition_year:04d}-01-01"
    )
    if not era.admissible:
        return RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
    if _missing_text(record, "provider_event_id"):
        return RefusalReason.MISSING_PROVIDER_EVENT_ID
    if _missing_text(record, "provider_version_id") and _missing_text(
        record, "event_version_id"
    ):
        return RefusalReason.MISSING_PROVIDER_VERSION_ID
    if _invalid_lineage(record):
        return RefusalReason.INVALID_PROVIDER_LINEAGE
    identity_status = record.get("identity_mapping_status")
    if identity_status == "ambiguous":
        return RefusalReason.AMBIGUOUS_IDENTITY_MAPPING
    if identity_status == "missing" or any(
        _missing_text(record, key)
        for key in ("issuer_id", "security_id", "share_class_id")
    ):
        return RefusalReason.MISSING_IDENTITY_MAPPING
    if record.get("availability_evidence_status") == "missing":
        return RefusalReason.MISSING_AVAILABILITY_EVIDENCE
    if record.get("rating_ontology_status") == "invalid":
        return RefusalReason.INVALID_RATING_ONTOLOGY
    if record.get("provider_semantics_supported") is False:
        return RefusalReason.UNSUPPORTED_PROVIDER_SEMANTICS
    if record.get("normalization_status") == "invalid_source_row":
        return RefusalReason.INVALID_SOURCE_ROW
    return None


def compute_build_recipe_sha256(
    *,
    snapshot: VerifiedSnapshot,
    normalizer_config_sha256: str,
    normalizer_code_sha256: str,
    evidence_epoch_id: str,
    build_recipe_id: str,
    producing_commit: str,
) -> str:
    """Bind the complete input contract for a repeatable normalization build."""
    if type(snapshot) is not VerifiedSnapshot:
        raise NormalizationContractError("build recipe requires a VerifiedSnapshot")
    revalidate_verified_snapshot(snapshot)
    require_sha256(normalizer_config_sha256, "normalizer_config_sha256")
    require_sha256(normalizer_code_sha256, "normalizer_code_sha256")
    require_identifier(evidence_epoch_id, "evidence_epoch_id")
    require_identifier(build_recipe_id, "build_recipe_id")
    require_git_object(producing_commit, "producing_commit")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": BUILD_RECIPE_SCHEMA,
                "snapshot_schema": snapshot.schema,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_manifest_sha256": snapshot.manifest_sha256,
                "provider_contract_id": snapshot.provider_contract_id,
                "provider_contract_sha256": snapshot.provider_contract_sha256,
                "canonical_event_schema": CANONICAL_EVENT_SCHEMA,
                "refusal_schema": REFUSAL_SCHEMA,
                "normalization_result_schema": NORMALIZATION_RESULT_SCHEMA,
                "normalizer_config_sha256": normalizer_config_sha256,
                "normalizer_code_sha256": normalizer_code_sha256,
                "evidence_epoch_id": evidence_epoch_id,
                "build_recipe_id": build_recipe_id,
                "producing_commit": producing_commit,
            }
        )
    )


@dataclasses.dataclass(frozen=True)
class NormalizationProvenance:
    normalizer_config_sha256: str
    normalizer_code_sha256: str
    evidence_epoch_id: str
    build_recipe_id: str
    build_recipe_sha256: str
    producing_commit: str

    def __post_init__(self) -> None:
        require_sha256(
            self.normalizer_config_sha256, "normalizer_config_sha256"
        )
        require_sha256(self.normalizer_code_sha256, "normalizer_code_sha256")
        require_identifier(self.evidence_epoch_id, "evidence_epoch_id")
        require_identifier(self.build_recipe_id, "build_recipe_id")
        require_sha256(self.build_recipe_sha256, "build_recipe_sha256")
        require_git_object(self.producing_commit, "producing_commit")

    @classmethod
    def create(
        cls,
        *,
        snapshot: VerifiedSnapshot,
        normalizer_config_sha256: str,
        normalizer_code_sha256: str,
        evidence_epoch_id: str,
        build_recipe_id: str,
        producing_commit: str,
    ) -> "NormalizationProvenance":
        recipe_hash = compute_build_recipe_sha256(
            snapshot=snapshot,
            normalizer_config_sha256=normalizer_config_sha256,
            normalizer_code_sha256=normalizer_code_sha256,
            evidence_epoch_id=evidence_epoch_id,
            build_recipe_id=build_recipe_id,
            producing_commit=producing_commit,
        )
        return cls(
            normalizer_config_sha256=normalizer_config_sha256,
            normalizer_code_sha256=normalizer_code_sha256,
            evidence_epoch_id=evidence_epoch_id,
            build_recipe_id=build_recipe_id,
            build_recipe_sha256=recipe_hash,
            producing_commit=producing_commit,
        )


@dataclasses.dataclass(frozen=True)
class NormalizationResult:
    """Frozen, exhaustive terminal dispositions for one verified snapshot."""

    snapshot: VerifiedSnapshot
    events: tuple[CanonicalSourceEvent, ...]
    refusals: tuple[NormalizationRefusal, ...]
    provenance: NormalizationProvenance

    def __post_init__(self) -> None:
        if type(self.snapshot) is not VerifiedSnapshot:
            raise NormalizationContractError(
                "normalization requires a complete VerifiedSnapshot"
            )
        revalidate_verified_snapshot(self.snapshot)
        if type(self.events) is not tuple or any(
            type(event) is not CanonicalSourceEvent for event in self.events
        ):
            raise NormalizationContractError("events must be a tuple of canonical events")
        if self.events:
            raise NormalizationContractError(ACCEPTED_EVENT_ZERO_ACCESS_REASON)
        if type(self.refusals) is not tuple or any(
            type(refusal) is not NormalizationRefusal for refusal in self.refusals
        ):
            raise NormalizationContractError(
                "refusals must be a tuple of normalization refusals"
            )
        if type(self.provenance) is not NormalizationProvenance:
            raise NormalizationContractError(
                "provenance must be a NormalizationProvenance"
            )

        expected_recipe_hash = compute_build_recipe_sha256(
            snapshot=self.snapshot,
            normalizer_config_sha256=self.provenance.normalizer_config_sha256,
            normalizer_code_sha256=self.provenance.normalizer_code_sha256,
            evidence_epoch_id=self.provenance.evidence_epoch_id,
            build_recipe_id=self.provenance.build_recipe_id,
            producing_commit=self.provenance.producing_commit,
        )
        if self.provenance.build_recipe_sha256 != expected_recipe_hash:
            raise NormalizationContractError("build recipe hash is not bound to inputs")

        raw_locators = self.snapshot.source_locators
        if len(raw_locators) != len(set(raw_locators)):
            raise NormalizationContractError("verified source locators are not unique")
        event_locators = tuple(event.source_locator for event in self.events)
        refusal_locators = tuple(refusal.source_locator for refusal in self.refusals)
        if event_locators != tuple(
            sorted(event_locators, key=lambda locator: locator.sort_key)
        ):
            raise NormalizationContractError("events are not canonically source-sorted")
        if refusal_locators != tuple(
            sorted(refusal_locators, key=lambda locator: locator.sort_key)
        ):
            raise NormalizationContractError("refusals are not canonically source-sorted")
        terminal_locators = event_locators + refusal_locators
        if len(terminal_locators) != len(set(terminal_locators)):
            raise NormalizationContractError(
                "a source row has more than one terminal disposition"
            )
        if set(terminal_locators) != set(raw_locators):
            missing = len(set(raw_locators) - set(terminal_locators))
            extra = len(set(terminal_locators) - set(raw_locators))
            raise NormalizationContractError(
                "terminal dispositions do not exactly cover source rows; "
                f"missing={missing}, extra={extra}"
            )
        if len(terminal_locators) != self.snapshot.source_row_count:
            raise NormalizationContractError(
                "accepted plus refused count does not equal source_row_count"
            )

        source_rows = {row.locator: row for row in self.snapshot.rows}
        for event in self.events:
            source_row = source_rows.get(event.source_locator)
            if source_row is None:
                raise NormalizationContractError(
                    "canonical event does not bind an authenticated raw source row"
                )
            event_date = parse_utc_timestamp(
                event.effective_at, "effective_at"
            ).date()
            if event_date.year != event.source_locator.partition_year:
                raise NormalizationContractError(
                    "canonical event effective year does not match its source partition"
                )
            era_decision = classify_provider_era(event_date.isoformat())
            if not era_decision.admissible:
                raise NormalizationContractError(
                    "pre-2013 provider events cannot be accepted; they require "
                    f"refusal reason {era_decision.refusal_reason!r}"
                )
            applicable_refusal = _applicable_refusal_reason(source_row)
            if applicable_refusal is not None:
                raise NormalizationContractError(
                    "canonical event cannot replace an objectively required refusal; "
                    f"expected={applicable_refusal.value}"
                )
            if event.provider_contract_id != self.snapshot.provider_contract_id:
                raise NormalizationContractError(
                    "event provider contract does not match snapshot"
                )
            if (
                event.provider_contract_sha256
                != self.snapshot.provider_contract_sha256
            ):
                raise NormalizationContractError(
                    "event provider contract hash does not match snapshot"
                )
            if (
                event.normalizer_config_sha256
                != self.provenance.normalizer_config_sha256
                or event.normalizer_code_sha256
                != self.provenance.normalizer_code_sha256
                or event.producing_commit != self.provenance.producing_commit
            ):
                raise NormalizationContractError(
                    "event normalization provenance does not match result"
                )
        for refusal in self.refusals:
            source_row = source_rows.get(refusal.source_locator)
            if source_row is None:
                raise NormalizationContractError(
                    "refusal does not bind an authenticated raw source row"
                )
            expected_evidence = _refusal_evidence_sha256(
                source_row.locator, refusal.reason
            )
            if refusal.evidence_sha256 != expected_evidence:
                raise NormalizationContractError(
                    "refusal evidence changed or does not bind the raw row"
                )
            applicable_reason = _applicable_refusal_reason(source_row)
            if refusal.reason is not applicable_reason:
                if (
                    refusal.reason
                    is RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
                ):
                    raise NormalizationContractError(
                        "the pre-2013 provider-era refusal cannot label a post-2013 source row"
                    )
                if (
                    applicable_reason
                    is RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
                ):
                    raise NormalizationContractError(
                        "pre-2013 source rows require the exact provider-era refusal"
                    )
                expected_name = (
                    applicable_reason.value
                    if applicable_reason is not None
                    else "no refusal; canonical event required"
                )
                raise NormalizationContractError(
                    "refusal reason is not applicable to authenticated raw evidence; "
                    f"expected={expected_name}"
                )
            if (
                refusal.normalizer_config_sha256
                != self.provenance.normalizer_config_sha256
                or refusal.normalizer_code_sha256
                != self.provenance.normalizer_code_sha256
                or refusal.producing_commit != self.provenance.producing_commit
            ):
                raise NormalizationContractError(
                    "refusal normalization provenance does not match result"
                )

        event_ids = [event.canonical_event_id for event in self.events]
        refusal_ids = [refusal.refusal_id for refusal in self.refusals]
        if len(event_ids) != len(set(event_ids)):
            raise NormalizationContractError("canonical event IDs are not unique")
        if len(refusal_ids) != len(set(refusal_ids)):
            raise NormalizationContractError("normalization refusal IDs are not unique")
        if set(event_ids) & set(refusal_ids):
            raise NormalizationContractError("event and refusal IDs are not disjoint")
        validate_revision_lineage(self.events)

    @property
    def result_sha256(self) -> str:
        validated = revalidate_normalization_result(self)
        return _normalization_result_sha256(validated)


def revalidate_normalization_result(
    result: NormalizationResult,
) -> NormalizationResult:
    """Reparse every record and rerun exhaustive disposition validation."""
    if type(result) is not NormalizationResult:
        raise NormalizationContractError(
            "normalization authority requires a NormalizationResult"
        )
    revalidate_verified_snapshot(result.snapshot)
    events = tuple(
        CanonicalSourceEvent.from_record(event.to_record())
        for event in result.events
    )
    refusals = tuple(
        NormalizationRefusal.from_record(refusal.to_record())
        for refusal in result.refusals
    )
    provenance = NormalizationProvenance(
        normalizer_config_sha256=result.provenance.normalizer_config_sha256,
        normalizer_code_sha256=result.provenance.normalizer_code_sha256,
        evidence_epoch_id=result.provenance.evidence_epoch_id,
        build_recipe_id=result.provenance.build_recipe_id,
        build_recipe_sha256=result.provenance.build_recipe_sha256,
        producing_commit=result.provenance.producing_commit,
    )
    return NormalizationResult(
        snapshot=result.snapshot,
        events=events,
        refusals=refusals,
        provenance=provenance,
    )


def _normalization_result_sha256(result: NormalizationResult) -> str:
    """Hash only a result freshly reconstructed by the public revalidator."""
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": NORMALIZATION_RESULT_SCHEMA,
                "snapshot_schema": SNAPSHOT_MANIFEST_SCHEMA,
                "snapshot_id": result.snapshot.snapshot_id,
                "snapshot_manifest_sha256": result.snapshot.manifest_sha256,
                "provider_contract_id": result.snapshot.provider_contract_id,
                "provider_contract_sha256": result.snapshot.provider_contract_sha256,
                "source_row_count": result.snapshot.source_row_count,
                "normalizer_config_sha256": (
                    result.provenance.normalizer_config_sha256
                ),
                "normalizer_code_sha256": result.provenance.normalizer_code_sha256,
                "evidence_epoch_id": result.provenance.evidence_epoch_id,
                "build_recipe_id": result.provenance.build_recipe_id,
                "build_recipe_sha256": result.provenance.build_recipe_sha256,
                "producing_commit": result.provenance.producing_commit,
                "events": [event.to_record() for event in result.events],
                "refusals": [refusal.to_record() for refusal in result.refusals],
            }
        )
    )
