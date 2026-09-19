"""Pure six-universe analyst-revision gate portfolio construction.

This module is deliberately below every provider, QuantConnect, price, order,
and outcome boundary.  It turns six already-point-in-time constituent
snapshots into deterministic target weights for two frozen diagnostics:

* a conservative-censored R055 firm-specific-score gate; and
* a count-matched point-in-time market-cap comparator.

All portfolio arithmetic uses exact :class:`~decimal.Decimal` values.  The
six nominally equal sleeves need a two-quantum reconciliation because 0.98/6
has no finite decimal representation; that residue is assigned to the final
frozen sleeve and is disclosed in the profile record.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, localcontext


class SixUniverseGateError(ValueError):
    """A frozen input or portfolio invariant was refused."""


TARGET_GROSS_EXPOSURE = Decimal("0.98")
DIRECT_STOCK_WEIGHT_CAP = Decimal("0.098")
WEIGHT_QUANTUM = Decimal("1e-24")
MINIMUM_POSITIVE_SCORE_COUNT = 5
MINIMUM_TOTAL_REPORTED_WEIGHT = Decimal("0.95")
MAXIMUM_TOTAL_REPORTED_WEIGHT = Decimal("1.05")
MINIMUM_SID_NAME_MAPPING_RATIO = Decimal("0.90")
MINIMUM_MARKET_CAP_WEIGHT_COVERAGE_RATIO = Decimal("0.99")
SOURCE_VIEW_ID = "conservative_censored_current_vintage_non_pristine_pit"
SCORE_ARM_ID = "firm_specific"
PROFILE_SCHEMA = "arv2-six-universe-gate-profile-v1"
CONSTRUCTION_SCHEMA = "arv2-six-universe-gate-construction-v1"
DECIMAL_RESIDUAL_RULE = (
    "floor_each_nominal_equal_sleeve_to_1e-24_and_assign_the_residual_"
    "to_the_final_frozen_sleeve"
)


@dataclasses.dataclass(frozen=True, slots=True)
class UniverseSpec:
    universe_id: str
    etf_ticker: str


UNIVERSE_SPECS = (
    UniverseSpec("SPY", "SPY"),
    UniverseSpec("QQQ", "QQQ"),
    UniverseSpec("SOXX", "SOXX"),
    UniverseSpec("XLV", "XLV"),
    UniverseSpec("REMX", "REMX"),
    UniverseSpec("XLE", "XLE"),
)
UNIVERSE_IDS = tuple(item.universe_id for item in UNIVERSE_SPECS)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise SixUniverseGateError(
            "six-universe record is not canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise SixUniverseGateError(f"{name} must be exact nonempty text")
    return value


def _require_decimal(
    value: object,
    name: str,
    *,
    positive: bool = False,
) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise SixUniverseGateError(f"{name} must be an exact finite Decimal")
    decimal_tuple = value.as_tuple()
    if len(decimal_tuple.digits) > 64 or not -48 <= decimal_tuple.exponent <= 48:
        raise SixUniverseGateError(f"{name} escaped the canonical Decimal bound")
    if positive and value <= 0:
        raise SixUniverseGateError(f"{name} must be strictly positive")
    return value


def _decimal_text(value: Decimal) -> str:
    _require_decimal(value, "record Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _sum(values) -> Decimal:
    with localcontext() as context:
        context.prec = 96
        total = Decimal(0)
        for value in values:
            total += value
        return +total


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        raise SixUniverseGateError("coverage ratio denominator is not positive")
    with localcontext() as context:
        context.prec = 96
        return +(numerator / denominator)


def _sleeve_budgets() -> tuple[Decimal, ...]:
    with localcontext() as context:
        context.prec = 96
        nominal = (TARGET_GROSS_EXPOSURE / Decimal(len(UNIVERSE_SPECS))).quantize(
            WEIGHT_QUANTUM,
            rounding=ROUND_DOWN,
        )
        values = [nominal] * len(UNIVERSE_SPECS)
        values[-1] += TARGET_GROSS_EXPOSURE - _sum(values)
    result = tuple(values)
    if _sum(result) != TARGET_GROSS_EXPOSURE or any(item <= 0 for item in result):
        raise SixUniverseGateError("six-universe sleeve budgets do not conserve")
    return result


SLEEVE_BUDGETS = _sleeve_budgets()


def _profile_semantic(label: str, slot_count: int) -> dict[str, object]:
    return {
        "schema": PROFILE_SCHEMA,
        "label": label,
        "slot_count_per_sleeve": slot_count,
        "universe_ids_and_etf_tickers": [
            {
                "universe_id": item.universe_id,
                "etf_ticker": item.etf_ticker,
            }
            for item in UNIVERSE_SPECS
        ],
        "source_view_id": SOURCE_VIEW_ID,
        "score_arm_id": SCORE_ARM_ID,
        "minimum_positive_score_count": MINIMUM_POSITIVE_SCORE_COUNT,
        "target_gross_exposure": _decimal_text(TARGET_GROSS_EXPOSURE),
        "sleeve_budget_decimals": [
            _decimal_text(item) for item in SLEEVE_BUDGETS
        ],
        "decimal_residual_rule": DECIMAL_RESIDUAL_RULE,
        "direct_stock_weight_cap": _decimal_text(DIRECT_STOCK_WEIGHT_CAP),
        "minimum_total_reported_weight": _decimal_text(
            MINIMUM_TOTAL_REPORTED_WEIGHT
        ),
        "maximum_total_reported_weight": _decimal_text(
            MAXIMUM_TOTAL_REPORTED_WEIGHT
        ),
        "minimum_sid_name_mapping_ratio": _decimal_text(
            MINIMUM_SID_NAME_MAPPING_RATIO
        ),
        "minimum_market_cap_weight_coverage_ratio": _decimal_text(
            MINIMUM_MARKET_CAP_WEIGHT_COVERAGE_RATIO
        ),
        "signal_rank_rule": "strictly_positive_score_desc_then_security_id",
        "matched_rank_rule": (
            "point_in_time_market_cap_desc_then_security_id_count_matched"
        ),
        "underfill_rule": (
            "five_to_slot_count_uses_available_stock_slots_and_own_etf_"
            "fallback_for_unfilled_slots;fewer_than_five_is_full_etf_fallback"
        ),
        "invalid_coverage_rule": "full_own_etf_fallback",
        "duplicate_security_rule": (
            "aggregate_in_frozen_universe_order_cap_direct_stock_at_0.098_"
            "and_return_excess_to_the_contributing_sleeve_etf"
        ),
        "cross_sleeve_redistribution": False,
        "etf_basket_comparator": "six_frozen_sleeve_budgets_in_actual_etfs",
    }


@dataclasses.dataclass(frozen=True, slots=True)
class GateProfile:
    profile_id: str
    profile_sha256: str
    label: str
    slot_count: int

    def to_record(self) -> dict[str, object]:
        semantic = _profile_semantic(self.label, self.slot_count)
        if _sha256(semantic) != self.profile_sha256:
            raise SixUniverseGateError("six-universe profile authority changed")
        return {
            **semantic,
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
        }


def _build_profile(label: str, slot_count: int) -> GateProfile:
    semantic = _profile_semantic(label, slot_count)
    digest = _sha256(semantic)
    return GateProfile(
        profile_id=f"arv2-six-universe-gate-{label}-{digest[:24]}",
        profile_sha256=digest,
        label=label,
        slot_count=slot_count,
    )


TOP10_PRIMARY_PROFILE = _build_profile("top10-primary-v1", 10)
TOP5_SENSITIVITY_PROFILE = _build_profile("top5-sensitivity-v1", 5)
PROFILES = (TOP10_PRIMARY_PROFILE, TOP5_SENSITIVITY_PROFILE)


@dataclasses.dataclass(frozen=True, slots=True)
class UniverseConstituent:
    """One point-in-time ETF constituent row.

    ``None`` is the only accepted representation of a missing mapping, score,
    or market cap.  A missing score is a structural zero for selection.  A
    missing mapping or cap contributes to the relevant coverage denominator.
    """

    reported_weight: Decimal
    security_id: str | None
    security_name: str | None
    pit_market_cap: Decimal | None
    firm_specific_score: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    universe_id: str
    etf_ticker: str
    etf_security_id: str
    constituents: tuple[UniverseConstituent, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class CoverageAssessment:
    member_count: int
    mapped_member_count: int
    total_reported_weight: Decimal
    cap_covered_reported_weight: Decimal
    mapping_ratio: Decimal
    cap_weight_coverage_ratio: Decimal
    valid: bool
    refusal_reasons: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "member_count": self.member_count,
            "mapped_member_count": self.mapped_member_count,
            "total_reported_weight": _decimal_text(self.total_reported_weight),
            "cap_covered_reported_weight": _decimal_text(
                self.cap_covered_reported_weight
            ),
            "mapping_ratio": _decimal_text(self.mapping_ratio),
            "cap_weight_coverage_ratio": _decimal_text(
                self.cap_weight_coverage_ratio
            ),
            "valid": self.valid,
            "refusal_reasons": list(self.refusal_reasons),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SleeveConstruction:
    universe_id: str
    etf_ticker: str
    etf_security_id: str
    budget: Decimal
    coverage: CoverageAssessment
    positive_score_count: int
    signal_security_ids: tuple[str, ...]
    matched_security_ids: tuple[str, ...]
    signal_stock_weights: tuple[tuple[str, Decimal], ...]
    matched_stock_weights: tuple[tuple[str, Decimal], ...]
    signal_etf_fallback_weight: Decimal
    matched_etf_fallback_weight: Decimal

    def to_record(self) -> dict[str, object]:
        return {
            "universe_id": self.universe_id,
            "etf_ticker": self.etf_ticker,
            "etf_security_id": self.etf_security_id,
            "budget": _decimal_text(self.budget),
            "coverage": self.coverage.to_record(),
            "positive_score_count": self.positive_score_count,
            "signal_security_ids": list(self.signal_security_ids),
            "matched_security_ids": list(self.matched_security_ids),
            "signal_stock_weights": [
                [security_id, _decimal_text(weight)]
                for security_id, weight in self.signal_stock_weights
            ],
            "matched_stock_weights": [
                [security_id, _decimal_text(weight)]
                for security_id, weight in self.matched_stock_weights
            ],
            "signal_etf_fallback_weight": _decimal_text(
                self.signal_etf_fallback_weight
            ),
            "matched_etf_fallback_weight": _decimal_text(
                self.matched_etf_fallback_weight
            ),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PortfolioWeight:
    security_id: str
    asset_kind: str
    weight: Decimal

    def to_record(self) -> dict[str, str]:
        return {
            "security_id": self.security_id,
            "asset_kind": self.asset_kind,
            "weight": _decimal_text(self.weight),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SixUniverseConstruction:
    profile: GateProfile
    sleeves: tuple[SleeveConstruction, ...]
    signal_weights: tuple[PortfolioWeight, ...]
    matched_weights: tuple[PortfolioWeight, ...]
    etf_basket_weights: tuple[PortfolioWeight, ...]

    def to_record(self) -> dict[str, object]:
        semantic = {
            "schema": CONSTRUCTION_SCHEMA,
            "profile_id": self.profile.profile_id,
            "profile_sha256": self.profile.profile_sha256,
            "sleeves": [item.to_record() for item in self.sleeves],
            "signal_weights": [item.to_record() for item in self.signal_weights],
            "matched_weights": [item.to_record() for item in self.matched_weights],
            "etf_basket_weights": [
                item.to_record() for item in self.etf_basket_weights
            ],
        }
        digest = _sha256(semantic)
        return {
            **semantic,
            "construction_id": f"arv2-six-universe-construction-{digest[:24]}",
            "construction_sha256": digest,
        }


def _validate_profile(value: object) -> GateProfile:
    if type(value) is not GateProfile or value not in PROFILES:
        raise SixUniverseGateError("six-universe profile is not frozen")
    value.to_record()
    return value


def _validated_constituents(
    snapshot: UniverseSnapshot,
) -> tuple[UniverseConstituent, ...]:
    if type(snapshot.constituents) is not tuple or not snapshot.constituents:
        raise SixUniverseGateError("universe constituents must be a nonempty tuple")
    seen: set[str] = set()
    result = []
    for row in snapshot.constituents:
        if type(row) is not UniverseConstituent:
            raise SixUniverseGateError("universe constituent type changed")
        _require_decimal(row.reported_weight, "reported weight", positive=True)
        if row.security_id is not None:
            _require_text(row.security_id, "constituent security id")
        if row.security_name is not None:
            _require_text(row.security_name, "constituent security name")
        if row.pit_market_cap is not None:
            _require_decimal(
                row.pit_market_cap,
                "point-in-time market cap",
                positive=True,
            )
        if row.firm_specific_score is not None:
            _require_decimal(row.firm_specific_score, "firm-specific score")
        if row.security_id is not None:
            if row.security_id in seen:
                raise SixUniverseGateError(
                    "universe constituent security id is duplicated"
                )
            seen.add(row.security_id)
        result.append(row)
    return tuple(result)


def _coverage(rows: tuple[UniverseConstituent, ...]) -> CoverageAssessment:
    total_weight = _sum(row.reported_weight for row in rows)
    mapped = tuple(
        row
        for row in rows
        if row.security_id is not None and row.security_name is not None
    )
    cap_covered_weight = _sum(
        row.reported_weight
        for row in rows
        if row.security_id is not None
        and row.security_name is not None
        and row.pit_market_cap is not None
    )
    mapping_ratio = _ratio(Decimal(len(mapped)), Decimal(len(rows)))
    cap_ratio = _ratio(cap_covered_weight, total_weight)
    reasons = []
    if not (
        MINIMUM_TOTAL_REPORTED_WEIGHT
        <= total_weight
        <= MAXIMUM_TOTAL_REPORTED_WEIGHT
    ):
        reasons.append("TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE")
    if mapping_ratio < MINIMUM_SID_NAME_MAPPING_RATIO:
        reasons.append("SID_NAME_MAPPING_BELOW_MINIMUM")
    if cap_ratio < MINIMUM_MARKET_CAP_WEIGHT_COVERAGE_RATIO:
        reasons.append("MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")
    return CoverageAssessment(
        member_count=len(rows),
        mapped_member_count=len(mapped),
        total_reported_weight=total_weight,
        cap_covered_reported_weight=cap_covered_weight,
        mapping_ratio=mapping_ratio,
        cap_weight_coverage_ratio=cap_ratio,
        valid=not reasons,
        refusal_reasons=tuple(reasons),
    )


def _selected_ids(
    rows: tuple[UniverseConstituent, ...],
    coverage: CoverageAssessment,
    slot_count: int,
) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    positive = tuple(
        sorted(
            (
                row
                for row in rows
                if row.security_id is not None
                and row.security_name is not None
                and row.pit_market_cap is not None
                and row.firm_specific_score is not None
                and row.firm_specific_score > 0
            ),
            key=lambda row: (-row.firm_specific_score, row.security_id),
        )
    )
    positive_count = len(positive)
    if not coverage.valid or positive_count < MINIMUM_POSITIVE_SCORE_COUNT:
        return (), (), positive_count
    signal = positive[:slot_count]
    matched_count = len(signal)
    cap_ranked = tuple(
        sorted(
            (
                row
                for row in rows
                if row.security_id is not None
                and row.security_name is not None
                and row.pit_market_cap is not None
            ),
            key=lambda row: (-row.pit_market_cap, row.security_id),
        )
    )
    if len(cap_ranked) < matched_count:
        raise SixUniverseGateError("count-matched size comparator underfilled")
    return (
        tuple(row.security_id for row in signal),
        tuple(row.security_id for row in cap_ranked[:matched_count]),
        positive_count,
    )


def _raw_sleeve(
    snapshot: UniverseSnapshot,
    budget: Decimal,
    profile: GateProfile,
) -> tuple[
    CoverageAssessment,
    int,
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, Decimal], ...],
    tuple[tuple[str, Decimal], ...],
    Decimal,
    Decimal,
]:
    rows = _validated_constituents(snapshot)
    coverage = _coverage(rows)
    signal_ids, matched_ids, positive_count = _selected_ids(
        rows,
        coverage,
        profile.slot_count,
    )
    with localcontext() as context:
        context.prec = 96
        slot_weight = +(budget / Decimal(profile.slot_count))
    signal_weights = tuple((security_id, slot_weight) for security_id in signal_ids)
    matched_weights = tuple((security_id, slot_weight) for security_id in matched_ids)
    signal_fallback = budget - _sum(weight for _, weight in signal_weights)
    matched_fallback = budget - _sum(weight for _, weight in matched_weights)
    if signal_fallback < 0 or matched_fallback < 0:
        raise SixUniverseGateError("six-universe sleeve over-allocated")
    return (
        coverage,
        positive_count,
        signal_ids,
        matched_ids,
        signal_weights,
        matched_weights,
        signal_fallback,
        matched_fallback,
    )


def _apply_duplicate_cap(
    raw_sleeves,
    role: str,
) -> tuple[tuple[PortfolioWeight, ...], tuple[tuple[tuple[str, Decimal], ...], ...], tuple[Decimal, ...]]:
    stock_totals: dict[str, Decimal] = {}
    etf_totals: dict[str, Decimal] = {}
    post_cap_rows = []
    post_cap_fallbacks = []
    for snapshot, raw in raw_sleeves:
        if role == "signal":
            raw_weights = raw[4]
            fallback = raw[6]
        elif role == "matched":
            raw_weights = raw[5]
            fallback = raw[7]
        else:
            raise SixUniverseGateError("portfolio role changed")
        accepted_rows = []
        for security_id, proposed in raw_weights:
            current = stock_totals.get(security_id, Decimal(0))
            capacity = max(Decimal(0), DIRECT_STOCK_WEIGHT_CAP - current)
            accepted = min(proposed, capacity)
            excess = proposed - accepted
            if accepted:
                stock_totals[security_id] = current + accepted
                accepted_rows.append((security_id, accepted))
            fallback += excess
        etf_totals[snapshot.etf_security_id] = (
            etf_totals.get(snapshot.etf_security_id, Decimal(0)) + fallback
        )
        post_cap_rows.append(tuple(accepted_rows))
        post_cap_fallbacks.append(fallback)

    weights = tuple(
        [
            PortfolioWeight(security_id, "stock", weight)
            for security_id, weight in sorted(stock_totals.items())
            if weight > 0
        ]
        + [
            PortfolioWeight(security_id, "etf", weight)
            for security_id, weight in sorted(etf_totals.items())
            if weight > 0
        ]
    )
    if any(
        item.asset_kind == "stock" and item.weight > DIRECT_STOCK_WEIGHT_CAP
        for item in weights
    ):
        raise SixUniverseGateError("direct-stock cap was exceeded")
    if _sum(item.weight for item in weights) != TARGET_GROSS_EXPOSURE:
        raise SixUniverseGateError("capped portfolio gross did not conserve")
    return weights, tuple(post_cap_rows), tuple(post_cap_fallbacks)


def build_six_universe_construction(
    snapshots: tuple[UniverseSnapshot, ...],
    profile: GateProfile,
) -> SixUniverseConstruction:
    """Build the frozen score-gated, size-matched, and ETF-basket targets."""

    profile = _validate_profile(profile)
    if type(snapshots) is not tuple or len(snapshots) != len(UNIVERSE_SPECS):
        raise SixUniverseGateError("exactly six universe snapshots are required")
    by_id = {}
    etf_security_ids = set()
    for snapshot in snapshots:
        if type(snapshot) is not UniverseSnapshot:
            raise SixUniverseGateError("universe snapshot type changed")
        universe_id = _require_text(snapshot.universe_id, "universe id")
        _require_text(snapshot.etf_ticker, "ETF ticker")
        etf_security_id = _require_text(snapshot.etf_security_id, "ETF security id")
        if universe_id in by_id:
            raise SixUniverseGateError("universe snapshot is duplicated")
        if etf_security_id in etf_security_ids:
            raise SixUniverseGateError("ETF security identity is duplicated")
        by_id[universe_id] = snapshot
        etf_security_ids.add(etf_security_id)
    if set(by_id) != set(UNIVERSE_IDS):
        raise SixUniverseGateError("six-universe snapshot census changed")

    ordered = []
    member_security_ids = set()
    for spec in UNIVERSE_SPECS:
        snapshot = by_id[spec.universe_id]
        if snapshot.etf_ticker != spec.etf_ticker:
            raise SixUniverseGateError("universe ETF ticker changed")
        rows = _validated_constituents(snapshot)
        member_security_ids.update(
            row.security_id for row in rows if row.security_id is not None
        )
        ordered.append(snapshot)
    if member_security_ids & etf_security_ids:
        raise SixUniverseGateError("ETF and direct-stock identities collide")

    raw_sleeves = tuple(
        (
            snapshot,
            _raw_sleeve(snapshot, SLEEVE_BUDGETS[index], profile),
        )
        for index, snapshot in enumerate(ordered)
    )
    signal_weights, signal_post_cap, signal_fallbacks = _apply_duplicate_cap(
        raw_sleeves, "signal"
    )
    matched_weights, matched_post_cap, matched_fallbacks = _apply_duplicate_cap(
        raw_sleeves, "matched"
    )
    sleeves = tuple(
        SleeveConstruction(
            universe_id=snapshot.universe_id,
            etf_ticker=snapshot.etf_ticker,
            etf_security_id=snapshot.etf_security_id,
            budget=SLEEVE_BUDGETS[index],
            coverage=raw[0],
            positive_score_count=raw[1],
            signal_security_ids=raw[2],
            matched_security_ids=raw[3],
            signal_stock_weights=signal_post_cap[index],
            matched_stock_weights=matched_post_cap[index],
            signal_etf_fallback_weight=signal_fallbacks[index],
            matched_etf_fallback_weight=matched_fallbacks[index],
        )
        for index, (snapshot, raw) in enumerate(raw_sleeves)
    )
    etf_basket_weights = tuple(
        PortfolioWeight(snapshot.etf_security_id, "etf", SLEEVE_BUDGETS[index])
        for index, snapshot in enumerate(ordered)
    )
    if _sum(item.weight for item in etf_basket_weights) != TARGET_GROSS_EXPOSURE:
        raise SixUniverseGateError("six-ETF basket gross did not conserve")
    value = SixUniverseConstruction(
        profile=profile,
        sleeves=sleeves,
        signal_weights=signal_weights,
        matched_weights=matched_weights,
        etf_basket_weights=etf_basket_weights,
    )
    value.to_record()
    return value


__all__ = (
    "CONSTRUCTION_SCHEMA",
    "DIRECT_STOCK_WEIGHT_CAP",
    "GateProfile",
    "MAXIMUM_TOTAL_REPORTED_WEIGHT",
    "MINIMUM_MARKET_CAP_WEIGHT_COVERAGE_RATIO",
    "MINIMUM_POSITIVE_SCORE_COUNT",
    "MINIMUM_SID_NAME_MAPPING_RATIO",
    "MINIMUM_TOTAL_REPORTED_WEIGHT",
    "PortfolioWeight",
    "PROFILES",
    "SCORE_ARM_ID",
    "SOURCE_VIEW_ID",
    "SLEEVE_BUDGETS",
    "SixUniverseConstruction",
    "SixUniverseGateError",
    "SleeveConstruction",
    "TARGET_GROSS_EXPOSURE",
    "TOP10_PRIMARY_PROFILE",
    "TOP5_SENSITIVITY_PROFILE",
    "UNIVERSE_IDS",
    "UNIVERSE_SPECS",
    "UniverseConstituent",
    "UniverseSnapshot",
    "WEIGHT_QUANTUM",
    "build_six_universe_construction",
)
