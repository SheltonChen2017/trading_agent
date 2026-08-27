"""Deterministic, long-only Analyst Revisions V2 portfolio state machine."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    require_canonical_json_bytes,
    require_exact_keys,
)
from research.analyst_revisions_v2.formulas import (
    FormulaError,
    ResearchSourceKind,
    VerifiedAnalystPolicy,
    analyst_decimal_context,
    require_registered_source_bytes,
    require_verified_analyst_policy,
)
from research.analyst_revisions_v2.holdings import (
    HoldingsError,
    VerifiedHoldingsEvidence,
    require_verified_holdings_evidence,
)


class PortfolioConstructionError(ValueError):
    """A portfolio input or constraint is ambiguous or invalid."""


def _d(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise PortfolioConstructionError(f"{name} must be finite, not bool")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioConstructionError(f"{name} must be finite") from exc
    if not parsed.is_finite():
        raise PortfolioConstructionError(f"{name} must be finite")
    return parsed


def _canonical_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PortfolioConstructionError(f"{name} must be canonical and non-empty")
    return value


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PortfolioConstructionError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _canonical_instant(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PortfolioConstructionError(
            f"{name} must be a canonical aware ISO timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioConstructionError(
            f"{name} must be a canonical aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortfolioConstructionError(f"{name} must be timezone-aware")
    canonical = parsed.isoformat()
    if value not in {canonical, canonical.replace("+00:00", "Z")}:
        raise PortfolioConstructionError(f"{name} must use canonical ISO-8601 spelling")
    return parsed.astimezone(timezone.utc)


@dataclasses.dataclass(frozen=True)
class LookThroughExposure:
    group_id: str
    fraction: Decimal | str | int | float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.group_id, str)
            or not self.group_id
            or self.group_id != self.group_id.strip()
        ):
            raise PortfolioConstructionError("group_id must be canonical and non-empty")
        fraction = _d(self.fraction, "fraction")
        if not 0 < fraction <= 1:
            raise PortfolioConstructionError("look-through fractions must be in (0,1]")
        object.__setattr__(self, "fraction", fraction)


_VERIFIED_CLASSIFICATION_TOKEN = object()
_VERIFIED_CROSS_SECTION_TOKEN = object()
_CROSS_SECTION_ZERO_ACCESS_REASON = (
    "cross-section authority is zero-access until the reviewed strategy freezes "
    "the complete universe, score-to-rank, tie, and inverse-volatility derivation"
)
_CROSS_SECTION_SOURCE_ZERO_ACCESS_REASON = (
    f"{_CROSS_SECTION_ZERO_ACCESS_REASON}; external cross-section source authority "
    "is also zero-access"
)
_CLASSIFICATION_SOURCE_SCHEMA = "arv2-classification-source-v1"
_CLASSIFICATION_SOURCE_KEYS = {
    "schema",
    "source_id",
    "evidence_epoch_id",
    "effective_at",
    "available_at",
    "etf_security_id",
    "holdings_snapshot_content_sha256",
    "decision_at",
    "sector_exposures",
    "overlap_clusters",
}
_EXPOSURE_SOURCE_KEYS = {"group_id", "fraction"}
_CROSS_SECTION_SOURCE_SCHEMA = "arv2-cross-section-source-v1"
_CROSS_SECTION_SOURCE_KEYS = {
    "schema",
    "source_id",
    "evidence_epoch_id",
    "effective_at",
    "available_at",
    "decision_at",
    "policy_sha256",
    "candidates",
}
_CROSS_SECTION_CANDIDATE_KEYS = {
    "etf_security_id",
    "peer_rank",
    "inverse_volatility",
}


def _validated_exposures(
    sector_exposures: Iterable[LookThroughExposure],
    overlap_clusters: Iterable[LookThroughExposure],
) -> tuple[tuple[LookThroughExposure, ...], tuple[LookThroughExposure, ...]]:
    validated: list[tuple[LookThroughExposure, ...]] = []
    for name, values in (
        ("sector_exposures", sector_exposures),
        ("overlap_clusters", overlap_clusters),
    ):
        try:
            rows = tuple(values)
        except TypeError as exc:
            raise PortfolioConstructionError(f"{name} must be an iterable") from exc
        if not rows or any(type(row) is not LookThroughExposure for row in rows):
            raise PortfolioConstructionError(f"{name} must contain typed exposures")
        ids = [row.group_id for row in rows]
        if len(ids) != len(set(ids)):
            raise PortfolioConstructionError(f"{name} contains duplicate group IDs")
        if name == "sector_exposures":
            with analyst_decimal_context():
                total = sum(
                    (_d(row.fraction, "sector fraction") for row in rows),
                    Decimal("0"),
                )
                if total != Decimal("1"):
                    raise PortfolioConstructionError(
                        "sector look-through must reconcile to one"
                    )
        elif any(_d(row.fraction, "cluster membership") != 1 for row in rows):
            raise PortfolioConstructionError(
                "overlap-cluster membership is non-dilutable and must equal one"
            )
        validated.append(rows)
    return validated[0], validated[1]


def _parse_classification_source(
    source_bytes: object,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[LookThroughExposure, ...],
    tuple[LookThroughExposure, ...],
]:
    try:
        raw = require_canonical_json_bytes(source_bytes, "classification source")
        if not isinstance(raw, dict):
            raise PortfolioConstructionError("classification source must be an object")
        require_exact_keys(raw, _CLASSIFICATION_SOURCE_KEYS, "classification source")
    except CanonicalEvidenceError as exc:
        raise PortfolioConstructionError(
            "classification source is not canonical evidence"
        ) from exc
    if raw["schema"] != _CLASSIFICATION_SOURCE_SCHEMA:
        raise PortfolioConstructionError("classification source schema is unsupported")
    source_id = _canonical_text(raw["source_id"], "source_id")
    evidence_epoch_id = _canonical_text(
        raw["evidence_epoch_id"], "evidence_epoch_id"
    )
    etf_id = _canonical_text(raw["etf_security_id"], "source etf_security_id")
    holdings_digest = _sha256(
        raw["holdings_snapshot_content_sha256"],
        "source holdings_snapshot_content_sha256",
    )
    effective = _canonical_instant(raw["effective_at"], "source effective_at")
    available = _canonical_instant(raw["available_at"], "source available_at")
    decision_instant = _canonical_instant(raw["decision_at"], "source decision_at")
    effective_text = effective.isoformat()
    available_text = available.isoformat()
    decision = decision_instant.isoformat()
    if (
        raw["effective_at"] != effective_text
        or raw["available_at"] != available_text
        or raw["decision_at"] != decision
    ):
        raise PortfolioConstructionError(
            "classification source timestamps must use canonical UTC"
        )
    if not effective <= available <= decision_instant:
        raise PortfolioConstructionError(
            "classification source must satisfy effective <= available <= decision"
        )

    parsed_exposures: list[tuple[LookThroughExposure, ...]] = []
    for name in ("sector_exposures", "overlap_clusters"):
        records = raw[name]
        if not isinstance(records, list):
            raise PortfolioConstructionError(f"source {name} must be a list")
        rows: list[LookThroughExposure] = []
        for record in records:
            try:
                require_exact_keys(record, _EXPOSURE_SOURCE_KEYS, f"source {name}")
            except CanonicalEvidenceError as exc:
                raise PortfolioConstructionError(
                    f"source {name} record has missing or unknown fields"
                ) from exc
            if not isinstance(record["fraction"], str):
                raise PortfolioConstructionError(
                    f"source {name} fractions must be exact decimal strings"
                )
            rows.append(
                LookThroughExposure(
                    record["group_id"],
                    _exact_source_decimal(record["fraction"], f"{name}.fraction"),
                )
            )
        ordered_rows = tuple(sorted(rows, key=lambda row: row.group_id))
        if tuple(rows) != ordered_rows:
            raise PortfolioConstructionError(
                f"source {name} must be canonically group-sorted"
            )
        parsed_exposures.append(ordered_rows)
    sectors, clusters = _validated_exposures(
        parsed_exposures[0], parsed_exposures[1]
    )
    return (
        source_id,
        evidence_epoch_id,
        etf_id,
        holdings_digest,
        effective_text,
        available_text,
        decision,
        sectors,
        clusters,
    )


def _classification_evidence_sha256(
    *,
    source_sha256: str,
    source_id: str,
    evidence_epoch_id: str,
    etf_security_id: str,
    holdings_snapshot_content_sha256: str,
    effective_at: str,
    available_at: str,
    decision_at: str,
    sector_exposures: tuple[LookThroughExposure, ...],
    overlap_clusters: tuple[LookThroughExposure, ...],
) -> str:
    def records(values: tuple[LookThroughExposure, ...]) -> list[dict[str, str]]:
        return [
            {"group_id": row.group_id, "fraction": format(_d(row.fraction, "fraction"), "f")}
            for row in sorted(values, key=lambda item: item.group_id)
        ]

    payload = json.dumps(
        {
            "schema": "arv2-classification-evidence-v1",
            "source_sha256": source_sha256,
            "source_id": source_id,
            "evidence_epoch_id": evidence_epoch_id,
            "etf_security_id": etf_security_id,
            "holdings_snapshot_content_sha256": holdings_snapshot_content_sha256,
            "effective_at": effective_at,
            "available_at": available_at,
            "decision_at": decision_at,
            "sector_exposures": records(sector_exposures),
            "overlap_clusters": records(overlap_clusters),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedClassificationEvidence:
    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_sha256: str
    source_id: str
    evidence_epoch_id: str
    etf_security_id: str
    holdings_snapshot_content_sha256: str
    effective_at: str
    available_at: str
    decision_at: str
    sector_exposures: tuple[LookThroughExposure, ...]
    overlap_clusters: tuple[LookThroughExposure, ...]
    evidence_sha256: str
    _token: object = dataclasses.field(repr=False, compare=False)

def build_verified_classification_evidence(
    *,
    source_bytes: bytes,
) -> VerifiedClassificationEvidence:
    """Verify source bytes and bind their classifications to one PIT snapshot."""
    try:
        immutable_source, source_digest = require_registered_source_bytes(
            ResearchSourceKind.CLASSIFICATION, source_bytes
        )
    except FormulaError as exc:
        raise PortfolioConstructionError(
            "classification source authority is zero-access"
        ) from exc
    (
        source_id,
        evidence_epoch_id,
        source_etf,
        source_holdings,
        effective_at,
        available_at,
        source_decision,
        sectors,
        clusters,
    ) = _parse_classification_source(immutable_source)
    values = {
        "source_sha256": source_digest,
        "source_id": source_id,
        "evidence_epoch_id": evidence_epoch_id,
        "etf_security_id": source_etf,
        "holdings_snapshot_content_sha256": source_holdings,
        "effective_at": effective_at,
        "available_at": available_at,
        "decision_at": source_decision,
        "sector_exposures": sectors,
        "overlap_clusters": clusters,
    }
    value = object.__new__(VerifiedClassificationEvidence)
    for name, item in {
        "source_bytes": immutable_source,
        **values,
        "evidence_sha256": _classification_evidence_sha256(**values),
        "_token": _VERIFIED_CLASSIFICATION_TOKEN,
    }.items():
        object.__setattr__(value, name, item)
    return require_verified_classification_evidence(value)


def require_verified_classification_evidence(
    value: object,
) -> VerifiedClassificationEvidence:
    if (
        type(value) is not VerifiedClassificationEvidence
        or value._token is not _VERIFIED_CLASSIFICATION_TOKEN
    ):
        raise PortfolioConstructionError(
            "portfolio eligibility requires verified classification evidence"
        )
    try:
        source_bytes, source_digest = require_registered_source_bytes(
            ResearchSourceKind.CLASSIFICATION, value.source_bytes
        )
    except FormulaError as exc:
        raise PortfolioConstructionError(
            "classification source authority is zero-access"
        ) from exc
    (
        source_id,
        evidence_epoch_id,
        etf_id,
        holdings_digest,
        effective_at,
        available_at,
        decision,
        sectors,
        clusters,
    ) = _parse_classification_source(source_bytes)
    if (
        value.source_sha256 != source_digest
        or value.source_id != source_id
        or value.evidence_epoch_id != evidence_epoch_id
        or value.etf_security_id != etf_id
        or value.holdings_snapshot_content_sha256 != holdings_digest
        or value.effective_at != effective_at
        or value.available_at != available_at
        or value.decision_at != decision
        or value.sector_exposures != sectors
        or value.overlap_clusters != clusters
    ):
        raise PortfolioConstructionError(
            "classification evidence differs from authenticated source bytes"
        )
    expected = _classification_evidence_sha256(
        source_sha256=source_digest,
        source_id=source_id,
        evidence_epoch_id=evidence_epoch_id,
        etf_security_id=etf_id,
        holdings_snapshot_content_sha256=holdings_digest,
        effective_at=effective_at,
        available_at=available_at,
        decision_at=decision,
        sector_exposures=sectors,
        overlap_clusters=clusters,
    )
    if value.evidence_sha256 != expected:
        raise PortfolioConstructionError("classification evidence content hash mismatch")
    return value


@dataclasses.dataclass(frozen=True)
class CrossSectionCandidate:
    etf_security_id: str
    peer_rank: Decimal
    inverse_volatility: Decimal


def _exact_source_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PortfolioConstructionError(f"{name} must be an exact decimal string")
    parsed = _d(value, name)
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if parsed == 0:
        canonical = "0"
    if value != canonical:
        raise PortfolioConstructionError(f"{name} must use canonical decimal spelling")
    return parsed


def _parse_cross_section_source(
    source_bytes: bytes,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[CrossSectionCandidate, ...],
]:
    try:
        raw = require_canonical_json_bytes(source_bytes, "cross-section source")
        if not isinstance(raw, dict):
            raise PortfolioConstructionError("cross-section source must be an object")
        require_exact_keys(raw, _CROSS_SECTION_SOURCE_KEYS, "cross-section source")
    except CanonicalEvidenceError as exc:
        raise PortfolioConstructionError(
            "cross-section source is not canonical evidence"
        ) from exc
    if raw["schema"] != _CROSS_SECTION_SOURCE_SCHEMA:
        raise PortfolioConstructionError("cross-section source schema is unsupported")
    source_id = _canonical_text(raw["source_id"], "cross-section source_id")
    epoch = _canonical_text(raw["evidence_epoch_id"], "evidence_epoch_id")
    policy_sha256 = _sha256(raw["policy_sha256"], "policy_sha256")
    effective = _canonical_instant(raw["effective_at"], "effective_at")
    available = _canonical_instant(raw["available_at"], "available_at")
    decision = _canonical_instant(raw["decision_at"], "decision_at")
    times = (effective.isoformat(), available.isoformat(), decision.isoformat())
    if (raw["effective_at"], raw["available_at"], raw["decision_at"]) != times:
        raise PortfolioConstructionError(
            "cross-section timestamps must use canonical UTC spelling"
        )
    if not effective <= available <= decision:
        raise PortfolioConstructionError(
            "cross-section must satisfy effective <= available <= decision"
        )
    records = raw["candidates"]
    if not isinstance(records, list) or not records:
        raise PortfolioConstructionError("cross-section candidates must be non-empty")
    candidates: list[CrossSectionCandidate] = []
    for index, record in enumerate(records):
        try:
            require_exact_keys(
                record, _CROSS_SECTION_CANDIDATE_KEYS, f"candidates[{index}]"
            )
        except CanonicalEvidenceError as exc:
            raise PortfolioConstructionError(
                "cross-section candidate fields are not exact"
            ) from exc
        etf = _canonical_text(record["etf_security_id"], "etf_security_id")
        rank = _exact_source_decimal(record["peer_rank"], "peer_rank")
        inverse_volatility = _exact_source_decimal(
            record["inverse_volatility"], "inverse_volatility"
        )
        if not 0 <= rank <= 100 or inverse_volatility <= 0:
            raise PortfolioConstructionError(
                "cross-section rank must be [0,100] and inverse volatility positive"
            )
        candidates.append(CrossSectionCandidate(etf, rank, inverse_volatility))
    ordered = tuple(sorted(candidates, key=lambda row: row.etf_security_id))
    if tuple(candidates) != ordered or len(ordered) != len(
        {row.etf_security_id for row in ordered}
    ):
        raise PortfolioConstructionError(
            "cross-section candidates must be uniquely ETF-sorted"
        )
    return source_id, epoch, policy_sha256, *times, ordered


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedCrossSectionEvidence:
    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_sha256: str
    source_id: str
    evidence_epoch_id: str
    policy_sha256: str
    effective_at: str
    available_at: str
    decision_at: str
    candidates: tuple[CrossSectionCandidate, ...]
    _token: object = dataclasses.field(repr=False, compare=False)


def build_verified_cross_section_evidence(
    *, source_bytes: bytes, policy: VerifiedAnalystPolicy
) -> VerifiedCrossSectionEvidence:
    try:
        require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise PortfolioConstructionError(
            "cross-section policy authority is unavailable"
        ) from exc
    if type(source_bytes) is not bytes or not source_bytes:
        raise PortfolioConstructionError(
            "cross-section source must be non-empty immutable bytes"
        )
    try:
        require_registered_source_bytes(ResearchSourceKind.CROSS_SECTION, source_bytes)
    except FormulaError as exc:
        raise PortfolioConstructionError(
            _CROSS_SECTION_SOURCE_ZERO_ACCESS_REASON
        ) from exc
    raise PortfolioConstructionError(_CROSS_SECTION_ZERO_ACCESS_REASON)


def require_verified_cross_section_evidence(
    value: object, *, policy: VerifiedAnalystPolicy
) -> VerifiedCrossSectionEvidence:
    try:
        require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise PortfolioConstructionError(
            "cross-section policy authority is unavailable"
        ) from exc
    if (
        type(value) is VerifiedCrossSectionEvidence
        and getattr(value, "_token", None) is _VERIFIED_CROSS_SECTION_TOKEN
    ):
        try:
            require_registered_source_bytes(
                ResearchSourceKind.CROSS_SECTION, value.source_bytes
            )
        except FormulaError as exc:
            raise PortfolioConstructionError(
                _CROSS_SECTION_SOURCE_ZERO_ACCESS_REASON
            ) from exc
    raise PortfolioConstructionError(_CROSS_SECTION_ZERO_ACCESS_REASON)


@dataclasses.dataclass(frozen=True)
class PortfolioCandidate:
    etf_security_id: str
    holdings_evidence: VerifiedHoldingsEvidence
    classification_evidence: VerifiedClassificationEvidence
    cross_section_evidence: VerifiedCrossSectionEvidence
    policy: VerifiedAnalystPolicy = dataclasses.field(repr=False)

    @property
    def ranking(self) -> CrossSectionCandidate:
        return next(
            row
            for row in self.cross_section_evidence.candidates
            if row.etf_security_id == self.etf_security_id
        )

    @property
    def peer_rank(self) -> Decimal:
        return self.ranking.peer_rank

    @property
    def inverse_volatility(self) -> Decimal:
        return self.ranking.inverse_volatility

    @property
    def sector_exposures(self) -> tuple[LookThroughExposure, ...]:
        return self.classification_evidence.sector_exposures

    @property
    def overlap_clusters(self) -> tuple[LookThroughExposure, ...]:
        return self.classification_evidence.overlap_clusters

    def __post_init__(self) -> None:
        if (
            not isinstance(self.etf_security_id, str)
            or not self.etf_security_id
            or self.etf_security_id != self.etf_security_id.strip()
        ):
            raise PortfolioConstructionError("etf_security_id must be canonical and non-empty")
        try:
            policy = require_verified_analyst_policy(self.policy)
        except FormulaError as exc:
            raise PortfolioConstructionError("candidate policy is not verified") from exc
        cross_section = require_verified_cross_section_evidence(
            self.cross_section_evidence, policy=policy
        )
        matches = [
            row for row in cross_section.candidates
            if row.etf_security_id == self.etf_security_id
        ]
        if len(matches) != 1:
            raise PortfolioConstructionError(
                "candidate ETF is absent from the verified cross-section"
            )
        try:
            evidence = require_verified_holdings_evidence(
                self.holdings_evidence, policy=policy
            )
        except HoldingsError as exc:
            raise PortfolioConstructionError(
                "holdings_evidence must be derived from a verified PIT snapshot"
            ) from exc
        if evidence.etf_security_id != self.etf_security_id:
            raise PortfolioConstructionError(
                "holdings evidence belongs to a different ETF security"
            )
        classification = require_verified_classification_evidence(
            self.classification_evidence
        )
        if classification.etf_security_id != self.etf_security_id:
            raise PortfolioConstructionError(
                "classification evidence belongs to a different ETF security"
            )
        if (
            classification.holdings_snapshot_content_sha256
            != evidence.snapshot_content_sha256
        ):
            raise PortfolioConstructionError(
                "classification evidence belongs to a different holdings snapshot"
            )
        if classification.decision_at != evidence.decision_at:
            raise PortfolioConstructionError(
                "classification and holdings evidence use different decision instants"
            )
        if (
            cross_section.decision_at != evidence.decision_at
            or cross_section.evidence_epoch_id != evidence.evidence_epoch_id
            or classification.evidence_epoch_id != evidence.evidence_epoch_id
        ):
            raise PortfolioConstructionError(
                "candidate evidence does not share one decision and evidence epoch"
            )


class PortfolioRules:
    """Compatibility name that refuses caller-authored V2 policy values."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise PortfolioConstructionError(
            "PortfolioRules is no longer caller-constructible; use verified policy"
        )


@dataclasses.dataclass(frozen=True)
class Allocation:
    etf_security_id: str
    weight: Decimal


@dataclasses.dataclass(frozen=True)
class ForcedExit:
    etf_security_id: str
    reason: str


@dataclasses.dataclass(frozen=True)
class PortfolioDecision:
    allocations: tuple[Allocation, ...]
    cash_weight: Decimal
    forced_exits: tuple[ForcedExit, ...]
    eligible_order: tuple[str, ...]
    underfill_reasons: tuple[str, ...]


def _allocate_in_context(
    selected: tuple[PortfolioCandidate, ...], policy: VerifiedAnalystPolicy
) -> tuple[tuple[Allocation, ...], Decimal, tuple[str, ...]]:
    tolerance = Decimal("1e-18")
    weights = {row.etf_security_id: Decimal("0") for row in selected}
    by_id = {row.etf_security_id: row for row in selected}
    sector_used: dict[str, Decimal] = {}
    cluster_used: dict[str, Decimal] = {}
    active = [row.etf_security_id for row in selected]
    cash = Decimal("1")

    # Proportional inverse-volatility water filling. Binding constraints remove
    # a name from subsequent redistribution; constraints are never relaxed.
    while cash > tolerance and active:
        denominator = sum(
            (_d(by_id[key].inverse_volatility, "inverse_volatility") for key in active),
            Decimal("0"),
        )
        if denominator <= 0:
            raise PortfolioConstructionError("active inverse-volatility mass vanished")
        proposed = {
            key: cash * _d(by_id[key].inverse_volatility, "inverse_volatility") / denominator
            for key in active
        }
        # Coupled sector/cluster constraints must scale the whole active
        # proposal at once. Sequentially mutating group usage lets the first
        # candidate consume a shared cap and breaks inverse-volatility weights.
        scale = Decimal("1")
        etf_cap = policy.etf_cap
        sector_cap = policy.sector_cap
        cluster_cap = policy.overlap_cluster_cap
        for key in active:
            if proposed[key] > 0:
                scale = min(
                    scale,
                    max(Decimal("0"), etf_cap - weights[key]) / proposed[key],
                )
        for exposures_name, used, cap in (
            ("sector_exposures", sector_used, sector_cap),
            ("overlap_clusters", cluster_used, cluster_cap),
        ):
            group_proposed: dict[str, Decimal] = {}
            for key in active:
                for exposure in getattr(by_id[key], exposures_name):
                    group_proposed[exposure.group_id] = (
                        group_proposed.get(exposure.group_id, Decimal("0"))
                        + proposed[key] * _d(exposure.fraction, "exposure fraction")
                    )
            for group_id, proposal in group_proposed.items():
                if proposal > 0:
                    scale = min(
                        scale,
                        max(Decimal("0"), cap - used.get(group_id, Decimal("0")))
                        / proposal,
                    )
        if scale <= tolerance:
            break

        additions = {key: proposed[key] * scale for key in active}
        allocated_this_round = sum(additions.values(), Decimal("0"))
        for key, addition in additions.items():
            if addition <= 0:
                continue
            candidate = by_id[key]
            weights[key] += addition
            for exposure in candidate.sector_exposures:
                sector_used[exposure.group_id] = (
                    sector_used.get(exposure.group_id, Decimal("0"))
                    + addition * _d(exposure.fraction, "sector fraction")
                )
            for exposure in candidate.overlap_clusters:
                cluster_used[exposure.group_id] = (
                    cluster_used.get(exposure.group_id, Decimal("0"))
                    + addition * _d(exposure.fraction, "cluster fraction")
                )
        if allocated_this_round <= tolerance:
            break
        cash -= allocated_this_round
        if cash < tolerance:
            cash = Decimal("0")
        if scale >= Decimal("1") - tolerance:
            # The simultaneous proposals sum to all remaining cash.
            break
        full_sectors = {
            group_id
            for group_id, used in sector_used.items()
            if used >= sector_cap - tolerance
        }
        full_clusters = {
            group_id
            for group_id, used in cluster_used.items()
            if used >= cluster_cap - tolerance
        }
        next_active: list[str] = []
        for key in active:
            candidate = by_id[key]
            blocked = (
                weights[key] >= etf_cap - tolerance
                or any(row.group_id in full_sectors for row in candidate.sector_exposures)
                or any(row.group_id in full_clusters for row in candidate.overlap_clusters)
            )
            if not blocked:
                next_active.append(key)
        if len(next_active) == len(active):
            raise PortfolioConstructionError(
                "a binding allocation constraint could not be identified"
            )
        active = next_active

    allocations = tuple(
        Allocation(row.etf_security_id, weights[row.etf_security_id])
        for row in selected
        if weights[row.etf_security_id] > tolerance
    )
    invested = sum((row.weight for row in allocations), Decimal("0"))
    cash = max(Decimal("0"), Decimal("1") - invested)
    if invested > Decimal("1") + tolerance:
        raise PortfolioConstructionError("allocation exceeded one unit of NAV")
    for allocation in allocations:
        if allocation.weight > policy.etf_cap + tolerance:
            raise PortfolioConstructionError("allocation escaped the ETF hard cap")
    for group_id, used in sector_used.items():
        if used > policy.sector_cap + tolerance:
            raise PortfolioConstructionError(
                f"allocation escaped sector cap for {group_id}"
            )
    for group_id, used in cluster_used.items():
        if used > policy.overlap_cluster_cap + tolerance:
            raise PortfolioConstructionError(
                f"allocation escaped overlap-cluster cap for {group_id}"
            )
    reasons: list[str] = []
    if len(selected) < policy.maximum_holdings:
        reasons.append("fewer_than_maximum_eligible_candidates")
    if cash > tolerance:
        reasons.append("constraints_leave_residual_cash")
    return allocations, cash, tuple(reasons)


def _allocate(
    selected: tuple[PortfolioCandidate, ...], policy: VerifiedAnalystPolicy
) -> tuple[tuple[Allocation, ...], Decimal, tuple[str, ...]]:
    with analyst_decimal_context():
        return _allocate_in_context(selected, policy)


def construct_portfolio(
    candidates: Iterable[PortfolioCandidate],
    *,
    policy: VerifiedAnalystPolicy,
    previous_holdings: Iterable[str] = (),
) -> PortfolioDecision:
    """Apply forced exits, hysteresis, ranking, hard cap, then constraints.

    Eligible incumbents and entrants share one total order: descending rank,
    incumbent before entrant on an exact tie, then permanent ETF security ID.
    Consequently a strictly stronger entrant evicts the weakest retained name,
    while a tie preserves hysteresis. Look-through caps are applied only after
    the hard five-name selection and any infeasibility remains cash.
    """
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise PortfolioConstructionError("portfolio requires verified policy") from exc
    materialized = tuple(candidates)
    if any(type(row) is not PortfolioCandidate for row in materialized):
        raise PortfolioConstructionError("candidates must contain PortfolioCandidate records")
    for row in materialized:
        # Frozen dataclasses remain mutable through object.__setattr__.  Re-run
        # every nested authority check at the public construction boundary;
        # constructor-time validation is not a lasting trust grant.
        row.__post_init__()
        require_verified_cross_section_evidence(
            row.cross_section_evidence, policy=verified_policy
        )
        require_verified_classification_evidence(row.classification_evidence)
    candidate_ids = [row.etf_security_id for row in materialized]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise PortfolioConstructionError("duplicate candidate ETF security ID")
    if materialized:
        cross_sections = {
            (
                row.cross_section_evidence.source_sha256,
                row.cross_section_evidence.source_id,
                row.cross_section_evidence.evidence_epoch_id,
                row.cross_section_evidence.decision_at,
                row.cross_section_evidence.policy_sha256,
            )
            for row in materialized
        }
        if len(cross_sections) != 1:
            raise PortfolioConstructionError(
                "all candidates must share one verified cross-section"
            )
        cross_section = require_verified_cross_section_evidence(
            materialized[0].cross_section_evidence, policy=verified_policy
        )
        if set(candidate_ids) != {
            row.etf_security_id for row in cross_section.candidates
        }:
            raise PortfolioConstructionError(
                "candidate list must exactly cover the verified cross-section"
            )
    incumbents = tuple(previous_holdings)
    if any(not isinstance(value, str) or not value or value != value.strip() for value in incumbents):
        raise PortfolioConstructionError("previous_holdings must be canonical IDs")
    if len(incumbents) != len(set(incumbents)):
        raise PortfolioConstructionError("previous_holdings contains duplicates")
    incumbent_set = set(incumbents)
    by_id = {row.etf_security_id: row for row in materialized}
    forced: list[ForcedExit] = []
    eligible: list[PortfolioCandidate] = []
    entry = verified_policy.entry_rank
    exit_rank = verified_policy.exit_rank

    for incumbent in incumbents:
        if incumbent not in by_id:
            forced.append(ForcedExit(incumbent, "missing_candidate_record"))
    for row in materialized:
        is_incumbent = row.etf_security_id in incumbent_set
        evidence = require_verified_holdings_evidence(
            row.holdings_evidence, policy=verified_policy
        )
        if not evidence.eligible:
            if is_incumbent:
                forced.append(
                    ForcedExit(
                        row.etf_security_id,
                        evidence.refusal_reason or "invalid_holdings_evidence",
                    )
                )
            continue
        rank = _d(row.peer_rank, "peer_rank")
        threshold = exit_rank if is_incumbent else entry
        if rank < threshold:
            if is_incumbent:
                forced.append(ForcedExit(row.etf_security_id, "below_exit_rank"))
            continue
        eligible.append(row)

    with analyst_decimal_context():
        eligible.sort(
            key=lambda row: (
                -_d(row.peer_rank, "peer_rank"),
                0 if row.etf_security_id in incumbent_set else 1,
                row.etf_security_id,
            )
        )
        selected = tuple(eligible[: verified_policy.maximum_holdings])
    allocations, cash, reasons = _allocate(selected, verified_policy)
    return PortfolioDecision(
        allocations=allocations,
        cash_weight=cash,
        forced_exits=tuple(sorted(forced, key=lambda row: (row.etf_security_id, row.reason))),
        eligible_order=tuple(row.etf_security_id for row in eligible),
        underfill_reasons=reasons,
    )
