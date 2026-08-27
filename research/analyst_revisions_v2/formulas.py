"""Outcome-free canonical Analyst Revisions V2 formula primitives."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import statistics
import weakref
from collections import defaultdict
from contextlib import contextmanager
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping

from .canonical import CanonicalEvidenceError, require_canonical_json_bytes


class FormulaError(ValueError):
    """A formula input is invalid or statistically underidentified."""


ANALYST_DECIMAL_PRECISION = 50
_ANALYST_DECIMAL_CONTEXT = Context(
    prec=ANALYST_DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
)
NUMERICAL_ZERO = Decimal("1e-18")
MINIMUM_TOTAL_NAMES = 20
MINIMUM_ACTIVE_NAMES = 5
MAXIMUM_HOLDINGS_LAG_SESSIONS = 1
MAXIMUM_PARTICIPATION = Decimal("0.10")
MINIMUM_FEE_DOLLARS = Decimal("0")
_POLICY_TOKEN = object()
_POLICY_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType["VerifiedAnalystPolicy"], str]
] = {}


@contextmanager
def analyst_decimal_context() -> Iterator[Context]:
    """Run authoritative ARV2 arithmetic under one process-independent context."""
    with localcontext(_ANALYST_DECIMAL_CONTEXT) as context:
        yield context


class ResearchSourceKind(str, Enum):
    HOLDINGS = "holdings"
    STOCK_SCORE = "stock_score"
    CLASSIFICATION = "classification"
    CROSS_SECTION = "cross_section"
    TERMINAL_EVENT = "terminal_event"
    TRADE_COST = "trade_cost"


RESEARCH_SOURCE_AUTHORITY_SCHEMA = "arv2-research-source-authority-v1"
ZERO_ACCESS_SOURCE_AUTHORITY_ID = "arv2-zero-access-no-external-source-authority"


def _require_zero_access_source_authority() -> str:
    """Re-read the canonical declaration that no real source has authority.

    The repository intentionally has no positive source-registry implementation.
    Even substitution of this local file cannot grant authority because the
    loader accepts only the exact empty ``zero_access`` declaration.
    """
    try:
        module_path = Path(__file__)
        if module_path.is_symlink():
            raise FormulaError(
                "research-source authority module path cannot be a symlink"
            )
        candidate = (
            module_path.resolve(strict=True).parent
            / "specs"
            / "research_source_authority.json"
        )
        if candidate.is_symlink():
            raise FormulaError(
                "research-source authority cannot be supplied through a symlink"
            )
        path = candidate.resolve(strict=True)
        if not path.is_file():
            raise FormulaError(
                "research-source authority must be a regular zero-access artifact"
            )
        raw = require_canonical_json_bytes(
            path.read_bytes(), "research-source authority"
        )
    except (OSError, CanonicalEvidenceError) as exc:
        raise FormulaError(
            "research-source authority is absent or noncanonical; source access remains zero-access"
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema",
        "authority_mode",
        "authority_id",
        "entries",
    }:
        raise FormulaError("research-source authority fields are invalid")
    if (
        raw["schema"] != RESEARCH_SOURCE_AUTHORITY_SCHEMA
        or raw["authority_mode"] != "zero_access"
        or raw["authority_id"] != ZERO_ACCESS_SOURCE_AUTHORITY_ID
        or raw["entries"] != []
    ):
        raise FormulaError(
            "no independently reviewed committed research-source registry is configured; "
            "the repository authority must remain zero-access"
        )
    return ZERO_ACCESS_SOURCE_AUTHORITY_ID


def require_registered_source_bytes(
    kind: ResearchSourceKind, source_bytes: object
) -> tuple[bytes, str]:
    """Refuse all source bytes until external registry authority is implemented."""
    if not isinstance(kind, ResearchSourceKind):
        raise FormulaError("research source kind must be typed")
    if type(source_bytes) is not bytes or not source_bytes:
        raise FormulaError("research source must be non-empty immutable bytes")
    _require_zero_access_source_authority()
    raise FormulaError(
        f"{kind.value} source authority is zero-access until an independently "
        "reviewed committed external registry exists"
    )


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedAnalystPolicy:
    """Reviewed policy values used by every authoritative ARV2 primitive."""

    spec_id: str
    spec_hash: str
    authorized_normalized_dataset_ids: tuple[str, ...]
    half_life_sessions: int
    score_threshold: Decimal
    score_clip: Decimal
    minimum_total_names: int
    minimum_active_names: int
    maximum_holdings_lag_sessions: int
    minimum_mapped_candidate_weight: Decimal
    entry_rank: Decimal
    exit_rank: Decimal
    maximum_holdings: int
    etf_cap: Decimal
    sector_cap: Decimal
    overlap_cluster_cap: Decimal
    cost_scenario_bps: tuple[Decimal, ...]
    maximum_participation: Decimal
    minimum_fee_dollars: Decimal
    decimal_precision: int
    evidence_sha256: str
    _token: object = dataclasses.field(repr=False, compare=False)


def _policy_payload(values: Mapping[str, object]) -> bytes:
    serializable = {
        key: (
            [format(item, "f") for item in value]
            if key == "cost_scenario_bps"
            else format(value, "f")
            if isinstance(value, Decimal)
            else value
        )
        for key, value in values.items()
    }
    return json.dumps(
        {"schema": "arv2-verified-policy-v1", **serializable},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _register_policy_authority(policy: VerifiedAnalystPolicy) -> None:
    """Record loader-derived policy identity outside the mutable value itself."""
    identity = id(policy)

    def remove(reference: weakref.ReferenceType[VerifiedAnalystPolicy]) -> None:
        registered = _POLICY_AUTHORITIES.get(identity)
        if registered is not None and registered[0] is reference:
            _POLICY_AUTHORITIES.pop(identity, None)

    reference = weakref.ref(policy, remove)
    _POLICY_AUTHORITIES[identity] = (reference, policy.evidence_sha256)


def _create_verified_analyst_policy(
    *,
    spec_id: str,
    spec_hash: str,
    authorized_normalized_dataset_ids: Iterable[object],
    half_life_sessions: object,
    score_threshold: object,
    score_clip: object,
    minimum_mapped_candidate_weight: object,
    entry_rank: object,
    exit_rank: object,
    maximum_holdings: object,
    etf_cap: object,
    sector_cap: object,
    overlap_cluster_cap: object,
    cost_scenario_bps: Iterable[object],
) -> VerifiedAnalystPolicy:
    """Internal constructor; public authority comes only from the reviewed spec."""
    if not isinstance(spec_id, str) or not spec_id or spec_id != spec_id.strip():
        raise FormulaError("policy spec_id must be canonical text")
    if (
        not isinstance(spec_hash, str)
        or len(spec_hash) != 64
        or any(character not in "0123456789abcdef" for character in spec_hash)
    ):
        raise FormulaError("policy spec_hash must be lowercase SHA-256")
    dataset_ids = tuple(authorized_normalized_dataset_ids)
    if (
        not dataset_ids
        or dataset_ids != tuple(sorted(dataset_ids))
        or len(dataset_ids) != len(set(dataset_ids))
        or any(
            not isinstance(value, str)
            or not value.startswith("arv2_ds_")
            or len(value) != 72
            or any(character not in "0123456789abcdef" for character in value[8:])
            for value in dataset_ids
        )
    ):
        raise FormulaError(
            "policy requires canonical reviewed normalized-dataset identities"
        )
    if (
        isinstance(half_life_sessions, bool)
        or not isinstance(half_life_sessions, int)
        or half_life_sessions != 20
    ):
        raise FormulaError("canonical half-life must remain 20 sessions")
    if (
        isinstance(maximum_holdings, bool)
        or not isinstance(maximum_holdings, int)
        or maximum_holdings != 5
    ):
        raise FormulaError("canonical maximum holdings must remain five")
    threshold = _decimal(score_threshold, "score_threshold")
    clip = _decimal(score_clip, "score_clip")
    minimum_coverage = _decimal(
        minimum_mapped_candidate_weight, "minimum_mapped_candidate_weight"
    )
    entry = _decimal(entry_rank, "entry_rank")
    exit_value = _decimal(exit_rank, "exit_rank")
    etf = _decimal(etf_cap, "etf_cap")
    sector = _decimal(sector_cap, "sector_cap")
    cluster = _decimal(overlap_cluster_cap, "overlap_cluster_cap")
    scenarios = tuple(
        _decimal(value, f"cost_scenario_bps[{index}]")
        for index, value in enumerate(cost_scenario_bps)
    )
    if (
        threshold != 0
        or clip != 4
        or minimum_coverage != Decimal("0.99")
        or entry != 90
        or exit_value != 70
        or etf != Decimal("0.20")
        or sector != Decimal("0.40")
        or cluster != Decimal("0.30")
        or scenarios != tuple(map(Decimal, ("0", "5", "10", "20")))
    ):
        raise FormulaError("reviewed policy differs from the canonical ARV2 family")
    values: dict[str, object] = {
        "spec_id": spec_id,
        "spec_hash": spec_hash,
        "authorized_normalized_dataset_ids": dataset_ids,
        "half_life_sessions": half_life_sessions,
        "score_threshold": threshold,
        "score_clip": clip,
        "minimum_total_names": MINIMUM_TOTAL_NAMES,
        "minimum_active_names": MINIMUM_ACTIVE_NAMES,
        "maximum_holdings_lag_sessions": MAXIMUM_HOLDINGS_LAG_SESSIONS,
        "minimum_mapped_candidate_weight": minimum_coverage,
        "entry_rank": entry,
        "exit_rank": exit_value,
        "maximum_holdings": maximum_holdings,
        "etf_cap": etf,
        "sector_cap": sector,
        "overlap_cluster_cap": cluster,
        "cost_scenario_bps": scenarios,
        "maximum_participation": MAXIMUM_PARTICIPATION,
        "minimum_fee_dollars": MINIMUM_FEE_DOLLARS,
        "decimal_precision": ANALYST_DECIMAL_PRECISION,
    }
    policy = object.__new__(VerifiedAnalystPolicy)
    for name, value in {
        **values,
        "evidence_sha256": hashlib.sha256(_policy_payload(values)).hexdigest(),
        "_token": _POLICY_TOKEN,
    }.items():
        object.__setattr__(policy, name, value)
    return policy


def derive_verified_analyst_policy(spec: object) -> VerifiedAnalystPolicy:
    """Derive policy authority from a loader-authenticated reviewed spec."""
    from .preregistration import (  # Lazy: formulas remain outcome/network free.
        ReviewedPreregistration,
        require_reviewed_preregistration,
    )

    if type(spec) is not ReviewedPreregistration:
        raise FormulaError("policy requires a reviewed preregistration")
    try:
        spec = require_reviewed_preregistration(spec)
        topology = spec.cell("stock_topology")
        primary_id = topology["primary_cell_id"]
        primary = next(
            cell for cell in topology["cells"] if cell["cell_id"] == primary_id
        )
        holdings = spec.cell("holdings_contract")
        portfolio = spec.cell("portfolio_contract")
        costs = spec.cell("cost_contract")
        dataset_ids = tuple(
            sorted({look.dataset_id for look in spec.looks})
        )
        policy = _create_verified_analyst_policy(
            spec_id=spec.spec_id,
            spec_hash=spec.spec_hash,
            authorized_normalized_dataset_ids=dataset_ids,
            half_life_sessions=primary["half_life_sessions"],
            score_threshold=primary["threshold"],
            score_clip=primary["clip"],
            minimum_mapped_candidate_weight=holdings[
                "minimum_mapped_candidate_weight"
            ],
            entry_rank="90",
            exit_rank="70",
            maximum_holdings=portfolio["maximum_holdings"],
            etf_cap=portfolio["etf_cap"],
            sector_cap=portfolio["sector_cap"],
            overlap_cluster_cap=portfolio["cluster_cap"],
            cost_scenario_bps=costs["scenario_bps"],
        )
        _register_policy_authority(policy)
        return require_verified_analyst_policy(policy)
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise FormulaError("reviewed preregistration cannot derive ARV2 policy") from exc


def require_verified_analyst_policy(value: object) -> VerifiedAnalystPolicy:
    if type(value) is not VerifiedAnalystPolicy or value._token is not _POLICY_TOKEN:
        raise FormulaError("authoritative calculation requires verified ARV2 policy")
    authority = _POLICY_AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != value.evidence_sha256
    ):
        raise FormulaError(
            "ARV2 policy was not derived from loader-authenticated reviewed authority"
        )
    fields = {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {"evidence_sha256", "_token"}
    }
    if (
        value.evidence_sha256 != hashlib.sha256(_policy_payload(fields)).hexdigest()
        or not isinstance(value.spec_id, str)
        or not value.spec_id
        or value.spec_id != value.spec_id.strip()
        or not isinstance(value.spec_hash, str)
        or len(value.spec_hash) != 64
        or any(character not in "0123456789abcdef" for character in value.spec_hash)
        or not value.authorized_normalized_dataset_ids
        or value.authorized_normalized_dataset_ids
        != tuple(sorted(value.authorized_normalized_dataset_ids))
        or len(value.authorized_normalized_dataset_ids)
        != len(set(value.authorized_normalized_dataset_ids))
        or any(
            not isinstance(dataset_id, str)
            or not dataset_id.startswith("arv2_ds_")
            or len(dataset_id) != 72
            or any(
                character not in "0123456789abcdef"
                for character in dataset_id[8:]
            )
            for dataset_id in value.authorized_normalized_dataset_ids
        )
        or value.half_life_sessions != 20
        or value.score_threshold != 0
        or value.score_clip != 4
        or value.decimal_precision != ANALYST_DECIMAL_PRECISION
        or value.minimum_total_names != MINIMUM_TOTAL_NAMES
        or value.minimum_active_names != MINIMUM_ACTIVE_NAMES
        or value.maximum_holdings_lag_sessions != MAXIMUM_HOLDINGS_LAG_SESSIONS
        or value.minimum_mapped_candidate_weight != Decimal("0.99")
        or value.entry_rank != 90
        or value.exit_rank != 70
        or value.maximum_holdings != 5
        or value.etf_cap != Decimal("0.20")
        or value.sector_cap != Decimal("0.40")
        or value.overlap_cluster_cap != Decimal("0.30")
        or value.cost_scenario_bps
        != tuple(map(Decimal, ("0", "5", "10", "20")))
        or value.maximum_participation != MAXIMUM_PARTICIPATION
        or value.minimum_fee_dollars != MINIMUM_FEE_DOLLARS
    ):
        raise FormulaError("verified ARV2 policy was relabelled or weakened")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise FormulaError(f"{name} must be a finite real number, not bool")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FormulaError(f"{name} must be a finite real number") from exc
    if not parsed.is_finite():
        raise FormulaError(f"{name} must be finite")
    return parsed


def _stable_decimal_sum(values: Iterable[Decimal]) -> Decimal:
    """Sum in one canonical order so input permutation cannot change results."""
    ordered = sorted(values, key=lambda value: (abs(value), value))
    return sum(ordered, Decimal("0"))


def effective_contributors(contributions: Iterable[object]) -> Decimal:
    """Return inverse-Herfindahl breadth without epsilon normalization.

    At or below the preregistered numerical-zero threshold the correct answer
    is zero evidence, not an arbitrarily huge contributor count.
    """
    with analyst_decimal_context():
        absolute = [
            abs(_decimal(value, f"contributions[{i}]"))
            for i, value in enumerate(contributions)
        ]
        total = _stable_decimal_sum(absolute)
        if total <= NUMERICAL_ZERO:
            return Decimal("0")
        positive = sorted(value for value in absolute if value > 0)
        sum_squares = _stable_decimal_sum(value * value for value in positive)
        if sum_squares <= 0:
            raise FormulaError("positive contribution mass produced no probability mass")
        numerator = total * total
        count = Decimal(len(positive))
        # Prove the inverse-Herfindahl bounds in the unnormalized domain before
        # allowing a final rounding clamp at the Decimal context boundary.
        if numerator < sum_squares or numerator > count * sum_squares:
            raise FormulaError("effective contributor result violated analytical bounds")
        result = numerator / sum_squares
        return max(Decimal("1"), min(count, result))


@dataclasses.dataclass(frozen=True)
class IndependentContribution:
    institution_id: str
    common_event_id: str
    value: Decimal | str | int | float

    def __post_init__(self) -> None:
        for name in ("institution_id", "common_event_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise FormulaError(f"{name} must be a canonical non-empty string")
        object.__setattr__(self, "value", _decimal(self.value, "value"))


@dataclasses.dataclass(frozen=True)
class EvidenceBreadth:
    institution_effective_n: Decimal
    catalyst_effective_n: Decimal
    independent_effective_n: Decimal
    raw_event_count: int


def independent_evidence_breadth(
    rows: Iterable[IndependentContribution],
) -> EvidenceBreadth:
    """Conservatively combine institution and common-catalyst independence.

    Events are first aggregated by stable institution and separately by
    common catalyst. The canonical independent breadth is the smaller of the
    two effective counts, so repeated actions by one firm or many firms
    reacting to one catalyst cannot multiply reliability. Raw intensity is
    retained only as a diagnostic.
    """
    with analyst_decimal_context():
        materialized = tuple(rows)
        by_institution: dict[str, list[Decimal]] = defaultdict(list)
        by_catalyst: dict[str, list[Decimal]] = defaultdict(list)
        for row in materialized:
            if not isinstance(row, IndependentContribution):
                raise FormulaError("rows must contain IndependentContribution records")
            value = _decimal(row.value, "value")
            by_institution[row.institution_id].append(value)
            by_catalyst[row.common_event_id].append(value)
        institution_totals = (
            _stable_decimal_sum(by_institution[key])
            for key in sorted(by_institution)
        )
        catalyst_totals = (
            _stable_decimal_sum(by_catalyst[key]) for key in sorted(by_catalyst)
        )
        institution_n = effective_contributors(institution_totals)
        catalyst_n = effective_contributors(catalyst_totals)
        return EvidenceBreadth(
            institution_effective_n=institution_n,
            catalyst_effective_n=catalyst_n,
            independent_effective_n=min(institution_n, catalyst_n),
            raw_event_count=len(materialized),
        )


class ObservationState(str, Enum):
    SIGNAL = "signal"
    STRUCTURAL_ZERO = "structural_zero"
    MISSING = "missing"
    INVALID = "invalid"


@dataclasses.dataclass(frozen=True)
class SignalObservation:
    security_id: str
    state: ObservationState
    value: Decimal | str | int | float | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.security_id, str)
            or not self.security_id
            or self.security_id != self.security_id.strip()
        ):
            raise FormulaError("security_id must be non-empty")
        if not isinstance(self.state, ObservationState):
            raise FormulaError("state must be an ObservationState")
        if self.state is ObservationState.STRUCTURAL_ZERO:
            if self.value not in (None, 0, "0", Decimal("0")):
                raise FormulaError("structural_zero cannot carry a nonzero value")
        elif self.state is ObservationState.SIGNAL:
            if self.value is None or _decimal(self.value, "value") == 0:
                raise FormulaError("signal observations require a nonzero finite value")
            object.__setattr__(self, "value", _decimal(self.value, "value"))
        elif self.value is not None:
            raise FormulaError("missing/invalid observations cannot carry a value")


@dataclasses.dataclass(frozen=True)
class RobustNormalization:
    available: bool
    standardized: Mapping[str, Decimal]
    reason: str | None
    total_names: int
    active_names: int
    median: Decimal | None
    mad: Decimal | None


def robust_group_normalize(
    observations: Iterable[SignalObservation],
    *,
    policy: VerifiedAnalystPolicy,
) -> RobustNormalization:
    """MAD-normalize a preregistered PIT peer group or return a named refusal.

    Missing rows never enter the cross-section, while any invalid row refuses
    the group before normalization. Structural zeros are valid zeros. Sparse
    groups and zero-MAD groups refuse; epsilon is not substituted as an
    invented variance estimate. Fixed-score clipping is explicitly not called
    winsorization.
    """
    verified_policy = require_verified_analyst_policy(policy)
    minimum_total_names = verified_policy.minimum_total_names
    minimum_active_names = verified_policy.minimum_active_names
    clip = verified_policy.score_clip
    with analyst_decimal_context():
        materialized = tuple(observations)
        if any(not isinstance(row, SignalObservation) for row in materialized):
            raise FormulaError("observations must contain SignalObservation records")
        ids = [row.security_id for row in materialized]
        if len(ids) != len(set(ids)):
            raise FormulaError("peer group contains duplicate security_id")
        if any(row.state is ObservationState.INVALID for row in materialized):
            raise FormulaError(
                "invalid observations refuse the complete peer-group calculation"
            )
        usable: dict[str, Decimal] = {}
        active = 0
        for row in materialized:
            if row.state is ObservationState.SIGNAL:
                usable[row.security_id] = _decimal(row.value, "value")
                active += 1
            elif row.state is ObservationState.STRUCTURAL_ZERO:
                usable[row.security_id] = Decimal("0")
        if len(usable) < minimum_total_names:
            return RobustNormalization(
                False,
                MappingProxyType({}),
                "insufficient_total_names",
                len(usable),
                active,
                None,
                None,
            )
        if active < minimum_active_names:
            return RobustNormalization(
                False,
                MappingProxyType({}),
                "insufficient_active_names",
                len(usable),
                active,
                None,
                None,
            )
        median = Decimal(str(statistics.median(usable.values())))
        absolute_deviations = [abs(value - median) for value in usable.values()]
        mad = Decimal(str(statistics.median(absolute_deviations)))
        if mad == 0:
            return RobustNormalization(
                False, MappingProxyType({}), "zero_mad", len(usable), active, median, mad
            )
        scale = Decimal("1.4826") * mad
        standardized = {
            security_id: max(-clip, min(clip, (value - median) / scale))
            for security_id, value in sorted(usable.items())
        }
        return RobustNormalization(
            True, MappingProxyType(standardized), None, len(usable), active, median, mad
        )


def analyst_reliability(
    *, coverage: object, independent_effective_n: object, quality: object
) -> Decimal:
    """Heuristic evidence reliability; deliberately not named confidence."""
    with analyst_decimal_context():
        coverage_d = _decimal(coverage, "coverage")
        n_eff = _decimal(independent_effective_n, "independent_effective_n")
        quality_d = _decimal(quality, "quality")
        if not 0 <= coverage_d <= 1 or n_eff < 0 or not 0 <= quality_d <= 1:
            raise FormulaError("coverage/quality must be in [0,1] and N_eff nonnegative")
        breadth = min(Decimal("1"), (n_eff / Decimal("5")).sqrt())
        return coverage_d.sqrt() * breadth * quality_d
