"""Pure bounded benchmark-tilt and benchmark-lineage arithmetic.

The functions in this module have no provider, runtime, or transport access.
They accept exact in-memory Decimal inputs, apply the frozen bounded-tilt
construction, and return only deterministic aggregate records or digests.
"""

import dataclasses
import hashlib
import json
from decimal import ROUND_DOWN, Decimal, localcontext

try:
    import accepted_risk_preliminary_rating_evaluator as _base
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )


class BoundedBenchmarkTiltError(ValueError):
    """The frozen tilt or prospective benchmark binding is invalid."""


TARGET_GROSS_EXPOSURE = Decimal("0.98")
PORTFOLIO_WEIGHT_QUANTUM = Decimal("1e-48")
MINIMUM_TILT_RANKED_NAME_COUNT = 40
MINIMUM_TILT_POSITIVE_SCORE_COUNT = 20
MINIMUM_TILT_NEGATIVE_SCORE_COUNT = 20
MAXIMUM_RELATIVE_TILT = Decimal("0.20")
MAXIMUM_ABSOLUTE_OVERWEIGHT = Decimal("0.005") * TARGET_GROSS_EXPOSURE
MAXIMUM_ONE_WAY_ACTIVE_SHARE = Decimal("0.05") * TARGET_GROSS_EXPOSURE
MAXIMUM_HHI_MULTIPLE = Decimal("1.44")
TILT_ENABLED = "TILT_ENABLED"
TILT_UNDERFILLED = "TILT_UNDERFILLED"
RESERVED_STRUCTURAL_ZERO_SECTOR_ID = (
    "arv2-structural-zero-unmapped-unscored"
)
TILT_AGGREGATES_SCHEMA = (
    "arv2-market-cap-stock-portfolio-tilt-aggregates-v2"
)
BENCHMARK_RAW_OBSERVATION_SCHEMA = (
    "arv2-market-cap-stock-benchmark-used-observations-v1"
)
BENCHMARK_RETURN_PATH_SCHEMA = (
    "arv2-market-cap-stock-benchmark-used-return-path-v1"
)
BENCHMARK_NORMALIZATION_MODE = "total_return"
BENCHMARK_OBSERVATION = "session_open"
BENCHMARK_SERIES_META_FIELDS = frozenset(
    {
        "benchmark_logical_id",
        "benchmark_history_normalization_mode",
        "benchmark_history_observation",
        "benchmark_first_used_session",
        "benchmark_last_used_session",
        "benchmark_observation_count",
        "benchmark_return_interval_count",
        "benchmark_raw_observation_sha256",
        "benchmark_return_path_sha256",
    }
)


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise BoundedBenchmarkTiltError(
            "tilt value must be an exact finite Decimal"
        )
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _positive_decimal_map(value, name):
    if type(value) is not dict or not value:
        raise BoundedBenchmarkTiltError(f"{name} must be a nonempty exact dict")
    if any(type(security_id) is not str or not security_id for security_id in value):
        raise BoundedBenchmarkTiltError(f"{name} security id changed")
    if any(
        type(item) is not Decimal or not item.is_finite() or item <= 0
        for item in value.values()
    ):
        raise BoundedBenchmarkTiltError(
            f"{name} values must be exact positive finite Decimal"
        )
    return tuple(sorted(value))


def _conserve_total(
    allocations,
    total,
    *,
    floors=None,
    ceilings=None,
    adjustable_ids=None,
):
    allocations = dict(sorted(allocations.items()))
    candidates = (
        tuple(sorted(allocations))
        if adjustable_ids is None
        else tuple(sorted(adjustable_ids))
    )
    if not candidates or not set(candidates).issubset(allocations):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt residual census changed"
        )
    for _attempt in range(2):
        residual = +(total - _base._stable_sum(allocations.values()))
        if residual == 0:
            return allocations
        first_valid = None
        for security_id in candidates:
            candidate = +(allocations[security_id] + residual)
            minimum = (
                Decimal(0)
                if floors is None
                else floors[security_id]
            )
            if candidate < minimum or (
                ceilings is not None
                and candidate > ceilings[security_id]
            ):
                continue
            if first_valid is None:
                first_valid = (security_id, candidate)
            trial = dict(allocations)
            trial[security_id] = candidate
            if _base._stable_sum(trial.values()) == total:
                return dict(sorted(trial.items()))
        if first_valid is None:
            break
        allocations[first_valid[0]] = first_valid[1]
    raise BoundedBenchmarkTiltError(
        "benchmark tilt allocation violated exact conservation"
    )


def _floor_weight(value):
    with localcontext(_base._context()):
        return value.quantize(PORTFOLIO_WEIGHT_QUANTUM, rounding=ROUND_DOWN)


@dataclasses.dataclass(frozen=True)
class TiltConstruction:
    benchmark_weights: dict
    selected_weights: dict
    rank_tilts: dict
    status: str
    ranked_nonzero_score_count: int
    positive_score_count: int
    negative_score_count: int
    tilted_name_count: int
    one_way_active_share: Decimal
    maximum_overweight: Decimal
    hhi_ratio_to_benchmark: Decimal
    minimum_weight_ratio_to_benchmark: Decimal
    maximum_weight_ratio_to_benchmark: Decimal
    sector_count: int
    maximum_absolute_sector_active_weight: Decimal


@dataclasses.dataclass(frozen=True)
class ExecutableTarget:
    weights: dict
    locked_sector_over_target_count: int
    sector_target_underfill_count: int


@dataclasses.dataclass(frozen=True)
class BenchmarkSeriesBinding:
    logical_benchmark_id: str
    normalization_mode: str
    observation: str
    first_used_session: str
    last_used_session: str
    observation_count: int
    return_interval_count: int
    raw_observation_sha256: str
    return_path_sha256: str

    def summary_fields(self):
        return {
            "benchmark_logical_id": self.logical_benchmark_id,
            "benchmark_history_normalization_mode": self.normalization_mode,
            "benchmark_history_observation": self.observation,
            "benchmark_first_used_session": self.first_used_session,
            "benchmark_last_used_session": self.last_used_session,
            "benchmark_observation_count": self.observation_count,
            "benchmark_return_interval_count": self.return_interval_count,
            "benchmark_raw_observation_sha256": self.raw_observation_sha256,
            "benchmark_return_path_sha256": self.return_path_sha256,
        }


def benchmark_weights(market_caps):
    security_ids = _positive_decimal_map(market_caps, "benchmark market cap")
    with localcontext(_base._context()):
        cap_total = +_base._stable_sum(market_caps.values())
        weights = {
            security_id: _floor_weight(
                TARGET_GROSS_EXPOSURE
                * market_caps[security_id]
                / cap_total
            )
            for security_id in security_ids
        }
        if any(weight <= 0 for weight in weights.values()):
            raise BoundedBenchmarkTiltError(
                "benchmark tilt weight fell below its exact quantum"
            )
        residual = +(
            TARGET_GROSS_EXPOSURE
            - _base._stable_sum(weights.values())
        )
        for security_id in security_ids:
            if residual == 0:
                break
            weights[security_id] = +(
                weights[security_id] + PORTFOLIO_WEIGHT_QUANTUM
            )
            residual = +(residual - PORTFOLIO_WEIGHT_QUANTUM)
        if residual != 0:
            raise BoundedBenchmarkTiltError(
                "benchmark tilt quantum residual escaped its security census"
            )
    if (
        any(weight <= 0 for weight in weights.values())
        or _base._stable_sum(weights.values()) != TARGET_GROSS_EXPOSURE
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt base weights violated conservation"
        )
    return dict(sorted(weights.items()))


def _sector_mapping(value, security_ids):
    if type(value) is not dict:
        raise BoundedBenchmarkTiltError(
            "benchmark tilt sector mapping must be an exact dict"
        )
    if set(value) != set(security_ids) or len(value) != len(security_ids):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt sector mapping is not exhaustive"
        )
    if any(
        type(security_id) is not str
        or not security_id
        or type(sector_id) is not str
        or not sector_id
        for security_id, sector_id in value.items()
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt sector mapping changed"
        )
    return dict(sorted(value.items()))


def sector_map_from_memberships(market_caps, memberships, arm_scores=None):
    security_ids = _positive_decimal_map(
        market_caps, "benchmark sector market cap"
    )
    if type(memberships) is not tuple or any(
        type(item) is not _base.SecurityMembership for item in memberships
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt memberships must be an exact tuple"
        )
    relevant = tuple(
        item for item in memberships if item.security_id in market_caps
    )
    if arm_scores is None and len(relevant) != len(security_ids):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt membership mapping is not exhaustive"
        )
    mapping = {item.security_id: item.sector_id for item in relevant}
    if len(mapping) != len(relevant):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt membership mapping is not one-to-one"
        )
    if arm_scores is not None:
        if type(arm_scores) is not dict:
            raise BoundedBenchmarkTiltError(
                "benchmark tilt R055 score map must be an exact dict"
            )
        missing = set(security_ids) - set(mapping)
        if missing & set(arm_scores):
            raise BoundedBenchmarkTiltError(
                "benchmark tilt scored security lacks membership mapping"
            )
        if missing and RESERVED_STRUCTURAL_ZERO_SECTOR_ID in mapping.values():
            raise BoundedBenchmarkTiltError(
                "benchmark tilt reserved structural-zero sector collision"
            )
        mapping.update(
            (security_id, RESERVED_STRUCTURAL_ZERO_SECTOR_ID)
            for security_id in sorted(missing)
        )
    return _sector_mapping(mapping, security_ids)


def average_rank_tilts(scores):
    if type(scores) is not dict:
        raise BoundedBenchmarkTiltError(
            "benchmark tilt score map must be an exact dict"
        )
    if any(type(security_id) is not str or not security_id for security_id in scores):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt score security id changed"
        )
    if any(
        type(score) is not Decimal or not score.is_finite()
        for score in scores.values()
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt scores must be exact finite Decimal"
        )
    ordered = tuple(sorted(scores.items(), key=lambda item: (item[1], item[0])))
    count = len(ordered)
    if count < 2:
        return {}
    result = {}
    cursor = 0
    with localcontext(_base._context()):
        while cursor < count:
            end = cursor + 1
            while end < count and ordered[end][1] == ordered[cursor][1]:
                end += 1
            midrank = +(
                (Decimal(cursor + 1) + Decimal(end)) / Decimal(2)
            )
            rank_tilt = +(
                Decimal(2)
                * (midrank - Decimal(1))
                / Decimal(count - 1)
                - Decimal(1)
            )
            for index in range(cursor, end):
                result[ordered[index][0]] = rank_tilt
            cursor = end
    return dict(sorted(result.items()))


def _quantized_pro_rata(total, capacities, *, bounded):
    security_ids = _positive_decimal_map(
        capacities, "bounded benchmark tilt capacity"
    )
    if (
        type(total) is not Decimal
        or not total.is_finite()
        or total < 0
        or _floor_weight(total) != total
        or any(_floor_weight(value) != value for value in capacities.values())
    ):
        raise BoundedBenchmarkTiltError(
            "bounded benchmark tilt capacity changed its exact quantum"
        )
    if total == 0:
        return {security_id: Decimal(0) for security_id in security_ids}
    with localcontext(_base._context()):
        capacity_total = +_base._stable_sum(capacities.values())
        if bounded and total > capacity_total:
            raise BoundedBenchmarkTiltError(
                "benchmark tilt allocation exceeded capacity"
            )
        allocations = {
            security_id: _floor_weight(
                total * capacities[security_id] / capacity_total
            )
            for security_id in security_ids
        }
        residual = +(total - _base._stable_sum(allocations.values()))
        for security_id in security_ids:
            if residual == 0:
                break
            candidate = +(
                allocations[security_id] + PORTFOLIO_WEIGHT_QUANTUM
            )
            if bounded and candidate > capacities[security_id]:
                continue
            allocations[security_id] = candidate
            residual = +(residual - PORTFOLIO_WEIGHT_QUANTUM)
    if residual != 0:
        raise BoundedBenchmarkTiltError(
            "benchmark tilt quantum residual exceeded capacity"
        )
    if (
        _base._stable_sum(allocations.values()) != total
        or any(
            allocation < 0
            or (bounded and allocation > capacities[security_id])
            for security_id, allocation in allocations.items()
        )
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark tilt allocation violated exact bounds"
    )
    return dict(sorted(allocations.items()))


def bounded_pro_rata(total, capacities):
    return _quantized_pro_rata(total, capacities, bounded=True)


def _underfilled(
    benchmark,
    rank_tilts,
    ranked_count,
    positive_count,
    negative_count,
    sector_count,
):
    return TiltConstruction(
        benchmark_weights=dict(benchmark),
        selected_weights=dict(benchmark),
        rank_tilts=dict(rank_tilts),
        status=TILT_UNDERFILLED,
        ranked_nonzero_score_count=ranked_count,
        positive_score_count=positive_count,
        negative_score_count=negative_count,
        tilted_name_count=0,
        one_way_active_share=Decimal(0),
        maximum_overweight=Decimal(0),
        hhi_ratio_to_benchmark=Decimal(1),
        minimum_weight_ratio_to_benchmark=Decimal(1),
        maximum_weight_ratio_to_benchmark=Decimal(1),
        sector_count=sector_count,
        maximum_absolute_sector_active_weight=Decimal(0),
    )


def build_benchmark_tilt(market_caps, arm_scores, sector_by_security_id):
    if type(arm_scores) is not dict:
        raise BoundedBenchmarkTiltError(
            "benchmark tilt R055 score map must be an exact dict"
    )
    benchmark = benchmark_weights(market_caps)
    sector_by_security_id = _sector_mapping(
        sector_by_security_id, tuple(benchmark)
    )
    sector_ids = tuple(sorted(set(sector_by_security_id.values())))
    members_by_sector = {
        sector_id: tuple(
            security_id
            for security_id in benchmark
            if sector_by_security_id[security_id] == sector_id
        )
        for sector_id in sector_ids
    }
    nonzero_scores = {}
    positive_count = 0
    negative_count = 0
    for security_id in sorted(market_caps):
        score = arm_scores.get(security_id)
        if score is None:
            continue
        if type(score) is not Decimal or not score.is_finite():
            raise BoundedBenchmarkTiltError(
                "benchmark tilt R055 score must be exact finite Decimal"
            )
        if score == 0:
            continue
        nonzero_scores[security_id] = score
        positive_count += score > 0
        negative_count += score < 0
    ranked_count = len(nonzero_scores)
    rank_tilts = average_rank_tilts(nonzero_scores)
    if (
        ranked_count < MINIMUM_TILT_RANKED_NAME_COUNT
        or positive_count < MINIMUM_TILT_POSITIVE_SCORE_COUNT
        or negative_count < MINIMUM_TILT_NEGATIVE_SCORE_COUNT
    ):
        return _underfilled(
            benchmark,
            rank_tilts,
            ranked_count,
            positive_count,
            negative_count,
            len(sector_ids),
        )
    with localcontext(_base._context()):
        receivers = {
            security_id: _floor_weight(
                min(
                    MAXIMUM_RELATIVE_TILT
                    * benchmark[security_id]
                    * rank_tilts[security_id],
                    MAXIMUM_ABSOLUTE_OVERWEIGHT,
                )
            )
            for security_id in sorted(rank_tilts)
            if rank_tilts[security_id] > 0
        }
        donors = {
            security_id: _floor_weight(
                MAXIMUM_RELATIVE_TILT
                * benchmark[security_id]
                * -rank_tilts[security_id]
            )
            for security_id in sorted(rank_tilts)
            if rank_tilts[security_id] < 0
        }
        receivers = {
            security_id: value
            for security_id, value in receivers.items()
            if value > 0
        }
        donors = {
            security_id: value
            for security_id, value in donors.items()
            if value > 0
        }
        sector_capacities = {}
        for sector_id in sector_ids:
            sector_receivers = {
                security_id: receivers[security_id]
                for security_id in members_by_sector[sector_id]
                if security_id in receivers
            }
            sector_donors = {
                security_id: donors[security_id]
                for security_id in members_by_sector[sector_id]
                if security_id in donors
            }
            if sector_receivers and sector_donors:
                capacity = +min(
                    _base._stable_sum(sector_receivers.values()),
                    _base._stable_sum(sector_donors.values()),
                )
                if capacity > 0:
                    sector_capacities[sector_id] = capacity
        transfer = _floor_weight(
            min(
                MAXIMUM_ONE_WAY_ACTIVE_SHARE,
                _base._stable_sum(sector_capacities.values()),
            )
        )
    tilted_ids = {
        security_id
        for sector_id in sector_capacities
        for security_id in members_by_sector[sector_id]
        if security_id in receivers or security_id in donors
    }
    if len(tilted_ids) < MINIMUM_TILT_RANKED_NAME_COUNT or transfer <= 0:
        return _underfilled(
            benchmark,
            rank_tilts,
            ranked_count,
            positive_count,
            negative_count,
            len(sector_ids),
        )
    sector_transfers = bounded_pro_rata(transfer, sector_capacities)
    overweights = {}
    underweights = {}
    for sector_id in sorted(sector_transfers):
        sector_transfer = sector_transfers[sector_id]
        overweights.update(
            bounded_pro_rata(
                sector_transfer,
                {
                    security_id: receivers[security_id]
                    for security_id in members_by_sector[sector_id]
                    if security_id in receivers
                },
            )
        )
        underweights.update(
            bounded_pro_rata(
                sector_transfer,
                {
                    security_id: donors[security_id]
                    for security_id in members_by_sector[sector_id]
                    if security_id in donors
                },
            )
        )
    with localcontext(_base._context()):
        selected = dict(benchmark)
        for security_id, overweight in overweights.items():
            selected[security_id] = +(selected[security_id] + overweight)
        for security_id, underweight in underweights.items():
            selected[security_id] = +(selected[security_id] - underweight)
        selected = dict(sorted(selected.items()))
        active = {
            security_id: +(selected[security_id] - benchmark[security_id])
            for security_id in selected
        }
        one_way_active_share = +(
            _base._stable_sum(abs(value) for value in active.values())
            / Decimal(2)
        )
        maximum_overweight = +max(Decimal(0), max(active.values()))
        ratios = tuple(
            +(selected[security_id] / benchmark[security_id])
            for security_id in selected
        )
        benchmark_hhi = +_base._stable_sum(
            (weight / TARGET_GROSS_EXPOSURE) ** 2
            for weight in benchmark.values()
        )
        selected_hhi = +_base._stable_sum(
            (weight / TARGET_GROSS_EXPOSURE) ** 2
            for weight in selected.values()
        )
        hhi_ratio = +(selected_hhi / benchmark_hhi)
        sector_active_weights = tuple(
            +(
                _base._stable_sum(
                    selected[security_id]
                    for security_id in members_by_sector[sector_id]
                )
                - _base._stable_sum(
                    benchmark[security_id]
                    for security_id in members_by_sector[sector_id]
                )
            )
            for sector_id in sector_ids
        )
        maximum_absolute_sector_active_weight = max(
            abs(value) for value in sector_active_weights
        )
    tilted_count = sum(value != 0 for value in active.values())
    neutral = set(market_caps) - set(overweights) - set(underweights)
    with localcontext(_base._context()):
        bounds_violated = (
            _base._stable_sum(selected.values()) != TARGET_GROSS_EXPOSURE
            or any(
                not Decimal("0.8") * benchmark[security_id]
                <= selected[security_id]
                <= Decimal("1.2") * benchmark[security_id]
                for security_id in selected
            )
            or maximum_overweight > MAXIMUM_ABSOLUTE_OVERWEIGHT
            or one_way_active_share > MAXIMUM_ONE_WAY_ACTIVE_SHARE
            or tilted_count < MINIMUM_TILT_RANKED_NAME_COUNT
            or selected_hhi > MAXIMUM_HHI_MULTIPLE * benchmark_hhi
            or maximum_absolute_sector_active_weight != 0
            or any(
                selected[security_id] != benchmark[security_id]
                for security_id in neutral
            )
        )
    if bounds_violated:
        raise BoundedBenchmarkTiltError(
            "benchmark tilt violated its frozen portfolio bounds"
        )
    return TiltConstruction(
        benchmark_weights=benchmark,
        selected_weights=selected,
        rank_tilts=rank_tilts,
        status=TILT_ENABLED,
        ranked_nonzero_score_count=ranked_count,
        positive_score_count=positive_count,
        negative_score_count=negative_count,
        tilted_name_count=tilted_count,
        one_way_active_share=one_way_active_share,
        maximum_overweight=maximum_overweight,
        hhi_ratio_to_benchmark=hhi_ratio,
        minimum_weight_ratio_to_benchmark=min(ratios),
        maximum_weight_ratio_to_benchmark=max(ratios),
        sector_count=len(sector_ids),
        maximum_absolute_sector_active_weight=(
            maximum_absolute_sector_active_weight
        ),
    )


def executable_selected_target(
    frozen_weights,
    sector_by_security_id,
    desired,
    tradable,
    locked,
):
    security_ids = _positive_decimal_map(
        frozen_weights, "frozen selected target"
    )
    if _base._stable_sum(frozen_weights.values()) != TARGET_GROSS_EXPOSURE:
        raise BoundedBenchmarkTiltError(
            "frozen selected target violated conservation"
        )
    sector_by_security_id = _sector_mapping(
        sector_by_security_id, security_ids
    )
    if (
        type(desired) is not tuple
        or desired != tuple(sorted(set(desired)))
        or set(desired) != set(security_ids)
    ):
        raise BoundedBenchmarkTiltError(
            "frozen selected target desired census changed"
        )
    if (
        type(tradable) is not tuple
        or tradable != tuple(sorted(set(tradable)))
        or not set(tradable).issubset(desired)
    ):
        raise BoundedBenchmarkTiltError(
            "frozen selected target tradable census changed"
        )
    if type(locked) is not dict or any(
        type(security_id) is not str
        or not security_id
        or type(weight) is not Decimal
        or not weight.is_finite()
        or weight <= 0
        for security_id, weight in locked.items()
    ):
        raise BoundedBenchmarkTiltError(
            "frozen selected target locked weights changed"
        )
    if set(tradable) & set(locked):
        raise BoundedBenchmarkTiltError(
            "frozen selected target tradable name is locked"
        )
    if not set(locked).issubset(desired):
        raise BoundedBenchmarkTiltError(
            "frozen selected target locked census changed"
        )
    targets = {
        **dict(sorted(locked.items())),
        **{
            security_id: frozen_weights[security_id]
            for security_id in tradable
        },
    }
    targets = dict(sorted(targets.items()))
    locked_over_target_sectors = set()
    underfilled_sectors = set()
    for sector_id in sorted(set(sector_by_security_id.values())):
        members = tuple(
            security_id
            for security_id in security_ids
            if sector_by_security_id[security_id] == sector_id
        )
        missing = set(members) - set(tradable) - set(locked)
        locked_above_frozen = any(
            locked[security_id] > frozen_weights[security_id]
            for security_id in members
            if security_id in locked
        )
        locked_below_frozen = any(
            locked[security_id] < frozen_weights[security_id]
            for security_id in members
            if security_id in locked
        )
        with localcontext(_base._context()):
            sector_target = +_base._stable_sum(
                frozen_weights[security_id] for security_id in members
            )
            executed_sector = +_base._stable_sum(
                targets.get(security_id, Decimal(0))
                for security_id in members
            )
        if locked_above_frozen or executed_sector > sector_target:
            locked_over_target_sectors.add(sector_id)
        if missing or locked_below_frozen or executed_sector < sector_target:
            underfilled_sectors.add(sector_id)
    if any(targets[security_id] != weight for security_id, weight in locked.items()):
        raise BoundedBenchmarkTiltError(
            "executable target changed a locked weight"
        )
    return ExecutableTarget(
        targets,
        len(locked_over_target_sectors),
        len(underfilled_sectors),
    )


def build_benchmark_series_binding(
    observations,
    expected_sessions,
    *,
    logical_benchmark_id,
):
    if type(logical_benchmark_id) is not str or not logical_benchmark_id:
        raise BoundedBenchmarkTiltError(
            "benchmark logical identity changed"
        )
    if (
        type(expected_sessions) is not tuple
        or len(expected_sessions) < 2
        or expected_sessions != tuple(sorted(set(expected_sessions)))
        or any(type(session) is not str or not session for session in expected_sessions)
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark used-session axis changed"
        )
    if type(observations) is not tuple:
        raise BoundedBenchmarkTiltError(
            "benchmark used observations must be an exact tuple"
        )
    by_session = {}
    for item in observations:
        if type(item) is not tuple or len(item) != 2:
            raise BoundedBenchmarkTiltError(
                "benchmark used observation shape changed"
            )
        session, value = item
        if type(session) is not str or not session:
            raise BoundedBenchmarkTiltError(
                "benchmark used observation session changed"
            )
        if session in by_session:
            raise BoundedBenchmarkTiltError(
                "benchmark used observation is duplicated"
            )
        if type(value) is not Decimal or not value.is_finite() or value <= 0:
            raise BoundedBenchmarkTiltError(
                "benchmark used observation must be exact positive Decimal"
            )
        by_session[session] = value
    if (
        len(by_session) != len(expected_sessions)
        or set(by_session) != set(expected_sessions)
    ):
        raise BoundedBenchmarkTiltError(
            "benchmark used observations are incomplete or changed"
        )
    ordered = tuple(
        (session, by_session[session]) for session in expected_sessions
    )
    common = {
        "logical_benchmark_id": logical_benchmark_id,
        "normalization_mode": BENCHMARK_NORMALIZATION_MODE,
        "observation": BENCHMARK_OBSERVATION,
        "first_used_session": expected_sessions[0],
        "last_used_session": expected_sessions[-1],
        "observation_count": len(ordered),
        "return_interval_count": len(ordered) - 1,
    }
    raw_record = {
        "schema": BENCHMARK_RAW_OBSERVATION_SCHEMA,
        **common,
        "used_observations": [
            {"session": session, "adjusted_open": _decimal_text(value)}
            for session, value in ordered
        ],
    }
    intervals = []
    with localcontext(_base._context()):
        for (prior_session, prior), (session, current) in zip(
            ordered[:-1], ordered[1:], strict=True
        ):
            intervals.append(
                {
                    "prior_session": prior_session,
                    "session": session,
                    "gross_return_ratio": _decimal_text(+(current / prior)),
                }
            )
    return_record = {
        "schema": BENCHMARK_RETURN_PATH_SCHEMA,
        **common,
        "used_return_intervals": intervals,
    }
    return BenchmarkSeriesBinding(
        logical_benchmark_id=logical_benchmark_id,
        normalization_mode=BENCHMARK_NORMALIZATION_MODE,
        observation=BENCHMARK_OBSERVATION,
        first_used_session=expected_sessions[0],
        last_used_session=expected_sessions[-1],
        observation_count=len(ordered),
        return_interval_count=len(ordered) - 1,
        raw_observation_sha256=_sha(raw_record),
        return_path_sha256=_sha(return_record),
    )


def account_aggregates(account, return_count, sector_neutral=False):
    def metric_text(value):
        return "0" if value == 0 else format(value, "f")

    def mean_or_zero(values):
        if not values:
            return Decimal(0)
        with localcontext(_base._context()):
            return +(
                _base._stable_sum(values) / Decimal(len(values))
            )

    with localcontext(_base._context()):
        average_holdings = +(
            Decimal(account.holding_count_sum) / Decimal(return_count)
        )
        average_turnover = +(
            account.turnover_sum / Decimal(return_count)
        )
        average_cash = +(
            account.cash_weight_sum / Decimal(return_count)
        )
    record = {
        "rebalance_execution_count": account.rebalance_execution_count,
        "full_target_execution_count": account.full_target_execution_count,
        "underfilled_target_execution_count": (
            account.underfilled_target_execution_count
        ),
        "locked_exposure_over_target_count": (
            account.locked_exposure_over_target_count
        ),
        "mean_executed_gross_exposure": metric_text(
            mean_or_zero(account.executed_gross_observations)
        ),
        "minimum_executed_gross_exposure": metric_text(
            min(account.executed_gross_observations)
            if account.executed_gross_observations
            else Decimal(0)
        ),
        "maximum_executed_gross_exposure": metric_text(
            max(account.executed_gross_observations)
            if account.executed_gross_observations
            else Decimal(0)
        ),
        "mean_maximum_position_weight": metric_text(
            mean_or_zero(account.maximum_weight_observations)
        ),
        "maximum_position_weight": metric_text(
            max(account.maximum_weight_observations)
            if account.maximum_weight_observations
            else Decimal(0)
        ),
        "mean_invested_weight_hhi": metric_text(
            mean_or_zero(account.hhi_observations)
        ),
        "mean_effective_holding_count": metric_text(
            mean_or_zero(account.effective_holding_observations)
        ),
        "average_holding_count": metric_text(average_holdings),
        "average_daily_two_sided_turnover": metric_text(average_turnover),
        "average_cash_weight": metric_text(average_cash),
        "entry_price_refusal_count": account.entry_price_refusal_count,
        "stale_mark_session_count": account.stale_mark_session_count,
        "partial_rebalance_decision_count": (
            account.partial_rebalance_decision_count
        ),
        "stale_position_deferral_count": (
            account.stale_position_deferral_count
        ),
        "selection_exit_deferral_count": (
            account.selection_exit_deferral_count
        ),
        "eligibility_exit_liquidation_count": (
            account.eligibility_exit_liquidation_count
        ),
        "eligibility_exit_zero_recovery_count": (
            account.eligibility_exit_zero_recovery_count
        ),
    }
    if sector_neutral:
        record.update(
            locked_sector_over_target_count=(
                account.locked_sector_over_target_count
            ),
            sector_target_underfill_count=(
                account.sector_target_underfill_count
            ),
        )
    return record


def profile_fields():
    """Return detached V3-only frozen profile fields."""

    return {
        "selection": (
            "full_point_in_time_eligible_benchmark_with_R055_as_a_"
            "breadth_confirmed_bounded_helper_not_an_admission_gate"
        ),
        "maximum_holdings": None,
        "signal_weighting": (
            "98_percent_point_in_time_market_cap_benchmark_plus_"
            "the_exact_bounded_R055_rank_tilt"
        ),
        "matched_comparator": (
            "same_full_point_in_time_eligible_benchmark_at_exact_"
            "98_percent_market_cap_weights"
        ),
        "sector_neutrality_rule": (
            "exact_selected_weight_equals_benchmark_weight_within_each_"
            "point_in_time_sector"
        ),
        "sector_mapping_rule": (
            "exhaustive_exact_security_to_sector_mapping_from_R055_"
            "membership_hook"
        ),
        "sector_neutral_execution_rule": (
            "execute_each_tradable_name_at_its_exact_frozen_target_preserve_"
            "each_locked_weight_never_redistribute_missing_or_locked_budget_"
            "and_count_sector_target_underfill_for_missing_or_below_frozen_"
            "locks_or_sector_gross_under_and_locked_sector_over_target_for_"
            "above_frozen_locks_or_sector_gross_over"
        ),
        "rank_rule": (
            "average_rank_over_exact_nonzero_R055_scores_then_"
            "2_times_midrank_minus_1_divided_by_m_minus_1_minus_1"
        ),
        "minimum_ranked_nonzero_score_count": MINIMUM_TILT_RANKED_NAME_COUNT,
        "minimum_positive_score_count": MINIMUM_TILT_POSITIVE_SCORE_COUNT,
        "minimum_negative_score_count": MINIMUM_TILT_NEGATIVE_SCORE_COUNT,
        "maximum_relative_tilt": _decimal_text(MAXIMUM_RELATIVE_TILT),
        "maximum_absolute_overweight": _decimal_text(
            MAXIMUM_ABSOLUTE_OVERWEIGHT
        ),
        "maximum_one_way_active_share": _decimal_text(
            MAXIMUM_ONE_WAY_ACTIVE_SHARE
        ),
        "maximum_hhi_multiple": _decimal_text(MAXIMUM_HHI_MULTIPLE),
        "underfilled_rule": "exact_benchmark_and_TILT_UNDERFILLED",
        "missing_or_zero_score_rule": "exact_benchmark_weight",
        "division_residual": "assigned_deterministically_by_security_id",
        "portfolio_weight_quantum": _decimal_text(
            PORTFOLIO_WEIGHT_QUANTUM
        ),
        "benchmark_series_binding": (
            "prospective_raw_used_observation_and_scale_invariant_"
            "used_return_path_SHA256_without_raw_values"
        ),
    }


def profile_fields_v4():
    """Return detached V4 fields for the one membership-gap correction."""

    fields = profile_fields()
    fields.update(
        {
            "sector_mapping_rule": (
                "exact_membership_sector_for_mapped_names_and_reserved_"
                "structural_zero_sector_only_for_unscored_unmapped_"
                "eligible_names_which_keep_exact_benchmark_weight_and_"
                "cannot_donate_or_receive_scored_unmapped_refuses"
            ),
            "reserved_structural_zero_sector_id": (
                RESERVED_STRUCTURAL_ZERO_SECTOR_ID
            ),
        }
    )
    return fields


@dataclasses.dataclass
class TiltCensus:
    decision_count: int = 0
    enabled_count: int = 0
    underfilled_count: int = 0
    minimum_ranked_count: int | None = None
    minimum_positive_count: int | None = None
    minimum_negative_count: int | None = None
    minimum_tilted_count: int | None = None
    maximum_active_share: Decimal = Decimal(0)
    maximum_overweight: Decimal = Decimal(0)
    maximum_hhi_ratio: Decimal = Decimal(0)
    minimum_weight_ratio: Decimal | None = None
    maximum_weight_ratio: Decimal = Decimal(0)
    minimum_sector_count: int | None = None
    maximum_absolute_sector_active_weight: Decimal = Decimal(0)

    def observe(self, value):
        if type(value) is not TiltConstruction:
            raise BoundedBenchmarkTiltError(
                "benchmark tilt census observation changed"
            )
        self.decision_count += 1
        self.minimum_ranked_count = (
            value.ranked_nonzero_score_count
            if self.minimum_ranked_count is None
            else min(self.minimum_ranked_count, value.ranked_nonzero_score_count)
        )
        self.minimum_positive_count = (
            value.positive_score_count
            if self.minimum_positive_count is None
            else min(self.minimum_positive_count, value.positive_score_count)
        )
        self.minimum_negative_count = (
            value.negative_score_count
            if self.minimum_negative_count is None
            else min(self.minimum_negative_count, value.negative_score_count)
        )
        self.minimum_sector_count = (
            value.sector_count
            if self.minimum_sector_count is None
            else min(self.minimum_sector_count, value.sector_count)
        )
        self.maximum_absolute_sector_active_weight = max(
            self.maximum_absolute_sector_active_weight,
            value.maximum_absolute_sector_active_weight,
        )
        if (
            value.sector_count <= 0
            or value.maximum_absolute_sector_active_weight != 0
        ):
            raise BoundedBenchmarkTiltError(
                "benchmark tilt sector neutrality changed"
            )
        if value.status == TILT_UNDERFILLED:
            self.underfilled_count += 1
            if (
                value.selected_weights != value.benchmark_weights
                or value.tilted_name_count != 0
                or value.one_way_active_share != 0
            ):
                raise BoundedBenchmarkTiltError(
                    "underfilled tilt is not the exact benchmark"
                )
            return
        if value.status != TILT_ENABLED:
            raise BoundedBenchmarkTiltError(
                "benchmark tilt status changed"
            )
        self.enabled_count += 1
        self.minimum_tilted_count = (
            value.tilted_name_count
            if self.minimum_tilted_count is None
            else min(self.minimum_tilted_count, value.tilted_name_count)
        )
        self.maximum_active_share = max(
            self.maximum_active_share, value.one_way_active_share
        )
        self.maximum_overweight = max(
            self.maximum_overweight, value.maximum_overweight
        )
        self.maximum_hhi_ratio = max(
            self.maximum_hhi_ratio, value.hhi_ratio_to_benchmark
        )
        self.minimum_weight_ratio = (
            value.minimum_weight_ratio_to_benchmark
            if self.minimum_weight_ratio is None
            else min(
                self.minimum_weight_ratio,
                value.minimum_weight_ratio_to_benchmark,
            )
        )
        self.maximum_weight_ratio = max(
            self.maximum_weight_ratio,
            value.maximum_weight_ratio_to_benchmark,
        )

    def aggregates(self):
        if (
            self.decision_count <= 0
            or self.enabled_count + self.underfilled_count != self.decision_count
            or self.minimum_ranked_count is None
            or self.minimum_positive_count is None
            or self.minimum_negative_count is None
            or self.minimum_sector_count is None
            or (self.enabled_count > 0 and self.minimum_tilted_count is None)
        ):
            raise BoundedBenchmarkTiltError(
                "benchmark tilt decision census changed"
            )
        return {
            "schema": TILT_AGGREGATES_SCHEMA,
            "decision_session_count": self.decision_count,
            "tilt_enabled_decision_count": self.enabled_count,
            "tilt_underfilled_decision_count": self.underfilled_count,
            "minimum_ranked_nonzero_score_count": self.minimum_ranked_count,
            "minimum_positive_score_count": self.minimum_positive_count,
            "minimum_negative_score_count": self.minimum_negative_count,
            "minimum_tilted_name_count_when_enabled": (
                self.minimum_tilted_count if self.enabled_count else 0
            ),
            "maximum_one_way_active_share": _decimal_text(
                self.maximum_active_share
            ),
            "maximum_overweight": _decimal_text(self.maximum_overweight),
            "maximum_hhi_ratio_to_benchmark": _decimal_text(
                self.maximum_hhi_ratio
            ),
            "minimum_weight_ratio_to_benchmark_when_enabled": _decimal_text(
                self.minimum_weight_ratio
                if self.minimum_weight_ratio is not None
                else Decimal(0)
            ),
            "maximum_weight_ratio_to_benchmark_when_enabled": _decimal_text(
                self.maximum_weight_ratio
            ),
            "minimum_point_in_time_sector_count": self.minimum_sector_count,
            "sector_mapping_exhaustive": True,
            "sector_neutrality_exact": True,
            "sector_neutrality_scope": "frozen_target",
            "maximum_absolute_sector_active_weight": _decimal_text(
                self.maximum_absolute_sector_active_weight
            ),
            "underfilled_exact_benchmark": True,
            "missing_or_zero_score_exact_benchmark": True,
        }


__all__ = (
    "BENCHMARK_NORMALIZATION_MODE",
    "BENCHMARK_OBSERVATION",
    "BENCHMARK_RAW_OBSERVATION_SCHEMA",
    "BENCHMARK_RETURN_PATH_SCHEMA",
    "BENCHMARK_SERIES_META_FIELDS",
    "BenchmarkSeriesBinding",
    "BoundedBenchmarkTiltError",
    "ExecutableTarget",
    "MAXIMUM_ABSOLUTE_OVERWEIGHT",
    "MAXIMUM_HHI_MULTIPLE",
    "MAXIMUM_ONE_WAY_ACTIVE_SHARE",
    "MAXIMUM_RELATIVE_TILT",
    "MINIMUM_TILT_NEGATIVE_SCORE_COUNT",
    "MINIMUM_TILT_POSITIVE_SCORE_COUNT",
    "MINIMUM_TILT_RANKED_NAME_COUNT",
    "PORTFOLIO_WEIGHT_QUANTUM",
    "RESERVED_STRUCTURAL_ZERO_SECTOR_ID",
    "TARGET_GROSS_EXPOSURE",
    "TILT_AGGREGATES_SCHEMA",
    "TILT_ENABLED",
    "TILT_UNDERFILLED",
    "TiltCensus",
    "TiltConstruction",
    "account_aggregates",
    "average_rank_tilts",
    "benchmark_weights",
    "bounded_pro_rata",
    "build_benchmark_series_binding",
    "build_benchmark_tilt",
    "executable_selected_target",
    "profile_fields",
    "profile_fields_v4",
    "sector_map_from_memberships",
)
