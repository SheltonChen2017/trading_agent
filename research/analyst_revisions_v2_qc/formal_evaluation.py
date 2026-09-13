"""Pure, fail-closed ARV2 formal inference and economic evaluation.

The caller supplies an already captured, content-addressed evaluation census.
This module has no filesystem, environment, provider, QuantConnect, result-
reader, deployment, order, or trading surface.  Computing a development
screen is deliberately distinct from authority to fetch it or act on it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import threading
import weakref
from collections import Counter
from datetime import date
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Underflow,
    localcontext,
)
from fractions import Fraction
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Sequence


class FormalEvaluationError(ValueError):
    """The supplied evaluation lineage or output census is not authentic."""


# Production-shaped evaluator; it has no dependency on the synthetic fixture
# transport used by the earlier QC refusal smoke.

SCHEMA = "arv2-qc-formal-evaluation-v2"
INPUT_SCHEMA = "arv2-qc-formal-evaluation-input-v1"
STATUS = "offline_development_evaluation_no_external_or_action_authority"
AUTHORITY = (
    "caller_supplied_authenticated_arithmetic_only_no_io_qc_result_reader_"
    "disposition_deployment_order_or_trading_authority"
)
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
HORIZONS = (1, 5, 20, 60)
FORMAL_FOLD_IDS = tuple(f"arv2-wf-test-{year}" for year in range(2020, 2026))
DESCRIPTIVE_FOLD_IDS = tuple(f"arv2-wf-test-{year}" for year in range(2021, 2026))
FORMAL_SLICE_ID = "formal_2020_2025_primary"
DESCRIPTIVE_SLICE_ID = "owner_2021_2025_descriptive_sensitivity"
SOURCE_VIEW_IDS = (
    "current_row_current_vintage_non_pristine_pit",
    "conservative_censored_current_vintage_non_pristine_pit",
)
MINIMUM_IC_ROWS = 20
MINIMUM_VALID_DATES = 50
H20_TEST_SESSION_CAPACITY = 1388
MINIMUM_SLEEVE_SIZE = 5
SLEEVE_HOLDING_SESSIONS = 20
BOOTSTRAP_RESAMPLES = 19_999
PRIMARY_SIZE = Fraction(1, 20)
PAIRED_LCB_PROBABILITY = Fraction(19, 20)
RANK_RELATIVE_THRESHOLD = Decimal("1e-20")
PRIMARY_COST_BPS = 10
COST_BPS_GRID = (0, 5, 10, 20)
ECONOMIC_FOLD_STATE_LOSS_EXCLUSION = (
    "economic_fold_excluded_after_holding_state_loss"
)

CONTINUOUS_CONTROL_NAMES = (
    "momentum_20d", "momentum_60d", "momentum_12_1",
    "sector_momentum_20d", "sector_momentum_60d", "sector_momentum_12_1",
    "industry_momentum_20d", "industry_momentum_60d", "industry_momentum_12_1",
    "market_beta_252d", "realized_volatility_60d", "value_book_to_market",
    "growth_trailing_revenue", "size_market_cap", "liquidity_dollar_volume_60d",
    "turnover_60d", "analyst_coverage_60d", "event_intensity_20d",
    "event_diversity_20d",
)
BINARY_CONTROL_NAMES = (
    "exact_earnings_day", "one_to_two_days_after_earnings",
    "three_to_five_days_after_earnings", "over_five_days_after_earnings",
    "pre_earnings", "public_guidance_proximity",
)
OUTCOME_ONLY_CONTROL_NAMES = (
    "active_event_indicator",
    "absolute_contribution_weighted_publication_to_entry_jump",
)
ALL_CONTROL_NAMES = (
    *CONTINUOUS_CONTROL_NAMES, *BINARY_CONTROL_NAMES, *OUTCOME_ONLY_CONTROL_NAMES,
)
_V2_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_V2_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_V2_SECURITY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,511}\Z")
PAIRED_BOOTSTRAP_SAMPLER_DOMAIN = (
    "arv2-paired-ic-noncircular-mbb-hash-counter-v1"
)
_STATIC_SEED_RECORD = {
    "domain": PAIRED_BOOTSTRAP_SAMPLER_DOMAIN,
    "successor_stock_spec_sha256": (
        "a9a2210b8f6582bc3ce9e533ce33e9b51ffc0a0b3203b62ad21d9d373ce06f95"
    ),
    "matched_row_contract_sha256": (
        "b94a3457b848c4dc1f6dee77ef366002362573431eb9cc2fc3b8f530ec7f89c9"
    ),
    "global_rating_map_sha256": (
        "aaf5830c3c3fb403b0e84f5ad22d1f20fa3f91df41cf3bd64f33695875d2e3d9"
    ),
    "fold_manifest_sha256": (
        "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
    ),
    "evaluation_id": EVALUATION_ID,
    "sampler_version": "v1",
}
PAIRED_BOOTSTRAP_SEED_RECORD = MappingProxyType(dict(_STATIC_SEED_RECORD))
BOOTSTRAP_SEED_SHA256 = hashlib.sha256(
    json.dumps(
        _STATIC_SEED_RECORD, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8") + b"\n"
).hexdigest()
PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES = (
    ("arv2-wf-test-2020", 233,
     "6547133cb7292c1b94f0a25eb54c97b252aae3b8b273c5bf6175db92e6b218b2",
     214, 12),
    ("arv2-wf-test-2021", 232,
     "e29e4bd66e3706bf0f339c5c3ec03f3eed59ca77345838d711cc855f010cf6d1",
     213, 12),
    ("arv2-wf-test-2022", 231,
     "0a58fb5ac63cf6199f131ff64f558f10ca8d4f238d610cb368a5e1d6f4acdb63",
     212, 12),
    ("arv2-wf-test-2023", 230,
     "76f0ed5e01babd1b376537e249f000fa35c1390ca9b2d1f446c54f7039111bed",
     211, 12),
    ("arv2-wf-test-2024", 232,
     "9fab5c021d29fd02409b44a80ce770d9cb599a9432c943362e5a2365d7a235e0",
     213, 12),
    ("arv2-wf-test-2025", 230,
     "a289bed633d8c12471dafa462c769d75fd1df0daf1f4c7c0497072421ab8722b",
     211, 12),
)
FORMAL_FOLD_HORIZON_AXIS_SUMMARIES = (
    ("arv2-wf-test-2020", 1, "2020-01-03", "2021-01-04", 252, "03d1cd30c2af014c07d57fca2203b6bc2f8b42b77bed42ed595115c7350c3d56"),
    ("arv2-wf-test-2020", 5, "2020-01-09", "2021-01-04", 248, "b97ab9fb4b17fca07445f839e86424c94458a059cc35c89d3d199bd88e8bdf8c"),
    ("arv2-wf-test-2020", 20, "2020-01-31", "2021-01-04", 233, "6547133cb7292c1b94f0a25eb54c97b252aae3b8b273c5bf6175db92e6b218b2"),
    ("arv2-wf-test-2020", 60, "2020-03-30", "2021-01-04", 193, "cd814ae505f3c060e92975676ba0c708ae4c659a13726a0ed1e4104d770dea75"),
    ("arv2-wf-test-2021", 1, "2021-01-05", "2022-01-03", 251, "eb2c380a9ec7306c7d3168c7e682e1ae4a58a3849edd2cd52654606d6db005b5"),
    ("arv2-wf-test-2021", 5, "2021-01-11", "2022-01-03", 247, "b03eded079fdf3a14a45f93a8a729243293810265f350201ea3f9ae7397c80f3"),
    ("arv2-wf-test-2021", 20, "2021-02-02", "2022-01-03", 232, "e29e4bd66e3706bf0f339c5c3ec03f3eed59ca77345838d711cc855f010cf6d1"),
    ("arv2-wf-test-2021", 60, "2021-03-31", "2022-01-03", 192, "cfd0839c8caaa452d9bb2ea2b0bbca822802025818e0e5e27af88060893cff1f"),
    ("arv2-wf-test-2022", 1, "2022-01-04", "2023-01-03", 250, "9710876785f40404a0a6ac40a2f06f80deaa24675cad57b6387348a79bb9f09c"),
    ("arv2-wf-test-2022", 5, "2022-01-10", "2023-01-03", 246, "cb652b4f4908783a1d60e091c99b3396a958bdaad7e375559692e76622ec411f"),
    ("arv2-wf-test-2022", 20, "2022-02-01", "2023-01-03", 231, "0a58fb5ac63cf6199f131ff64f558f10ca8d4f238d610cb368a5e1d6f4acdb63"),
    ("arv2-wf-test-2022", 60, "2022-03-30", "2023-01-03", 191, "e35017f87be021debe8c4c396e11fe85919537685b0a92eaa34c7c0ac80e62d5"),
    ("arv2-wf-test-2023", 1, "2023-01-04", "2024-01-02", 249, "c051818f12f98f1cb22f80294a3a724ed6e756077054849849261e5b9c421a07"),
    ("arv2-wf-test-2023", 5, "2023-01-10", "2024-01-02", 245, "6173fb46abea07e4e7e5c7ee07a571e91ce21e4729e420626f0522d7dc200340"),
    ("arv2-wf-test-2023", 20, "2023-02-01", "2024-01-02", 230, "76f0ed5e01babd1b376537e249f000fa35c1390ca9b2d1f446c54f7039111bed"),
    ("arv2-wf-test-2023", 60, "2023-03-30", "2024-01-02", 190, "16d0707553b3642edbcf95225fed7b4f910ffc117f4863a67badb600809bbca0"),
    ("arv2-wf-test-2024", 1, "2024-01-03", "2025-01-02", 251, "64dd1c296af8dfe82e7cfe92c3d0b728d3652601588d84bf2d3fb0012101c6c2"),
    ("arv2-wf-test-2024", 5, "2024-01-09", "2025-01-02", 247, "01903c5da928d066c3d86fb505f7f147c896c008d5c86e5d87b988e6b8946cbb"),
    ("arv2-wf-test-2024", 20, "2024-01-31", "2025-01-02", 232, "9fab5c021d29fd02409b44a80ce770d9cb599a9432c943362e5a2365d7a235e0"),
    ("arv2-wf-test-2024", 60, "2024-03-28", "2025-01-02", 192, "a335836b5e1d38746e4ac64b6e4296fc66728af70a9e82439793c65e77fd0d61"),
    ("arv2-wf-test-2025", 1, "2025-01-03", "2026-01-02", 249, "3ac6891864f934f5411b7ca1bf3bec21688618b08086aff6aca809c1ba0c33d5"),
    ("arv2-wf-test-2025", 5, "2025-01-10", "2026-01-02", 245, "bf9a7156ff85dbc596efff64d2d8784ba0ab66e4e5ab560a00bab987fd34a8d7"),
    ("arv2-wf-test-2025", 20, "2025-02-03", "2026-01-02", 230, "a289bed633d8c12471dafa462c769d75fd1df0daf1f4c7c0497072421ab8722b"),
    ("arv2-wf-test-2025", 60, "2025-04-01", "2026-01-02", 190, "a99846acda4eaef759c4235be2958c8648a3f9a26300e9001add643ae1fbf0e5"),
)
ECONOMIC_EXECUTION_DEFINITION_SHA256 = (
    "a3f46021fd8149625f544fc1af0197e89cd3c7e81de080a38f9733042922f032"
)
STOCK_BOOTSTRAP_SEED_SHA256 = (
    "3ec58554b08753742f82143fd0de3d34f5f3aadf67f31ccc01c4f0d0da048af4"
)
STOCK_BOOTSTRAP_SAMPLER_DOMAIN = (
    "arv2-stock-formal-noncircular-mbb-hash-counter-v1"
)
STOCK_BOOTSTRAP_METRIC_IDS = (
    "primary_fm_bullish_h20",
    "primary_economic_equal_weight_cost10",
    "secondary_fm_bullish_h1",
    "secondary_fm_bullish_h5",
    "secondary_fm_bullish_h60",
    "secondary_fm_bearish_h1",
    "secondary_fm_bearish_h5",
    "secondary_fm_bearish_h20",
    "secondary_fm_bearish_h60",
    "secondary_economic_direct_stock_equal_weight_cost0",
    "secondary_economic_direct_stock_equal_weight_cost5",
    "secondary_economic_direct_stock_equal_weight_cost20",
)
ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES = (
    ("arv2-wf-test-2020", "2020-01-31", "2021-01-04", 233,
     "d05d7c37f0ae3deacef369bba8bc7888b6de9295c45053fa6af4042765f7fe3b",
     "2021-02-01", 252,
     "f340decb2447196b0084f59c3ac606c3b84260dedc6a4c7afb2d8250cc507a3d",
     253, "a3315753e5b35f1562b8db5ced691bec922aac83b730f2b7e76d1f93628c19d6"),
    ("arv2-wf-test-2021", "2021-02-02", "2022-01-03", 232,
     "d05832a87f18577559247c705bb2fa67b150704f73328a83129bec0c6bd3953f",
     "2022-01-31", 251,
     "58101ba1116e4aabd7c5834d98c1ba6a52c861602b183fad8259faec6610dc8b",
     252, "6f8172c17ba51852fbbceff4a14f38efe6f5aec6c86c7df51aa6b2d751b451f3"),
    ("arv2-wf-test-2022", "2022-02-01", "2023-01-03", 231,
     "c20e0f699a72136b2adfbe701b7e31b8f6d634f2565086ded27d956eb2b5d1c5",
     "2023-01-31", 250,
     "203de931639379ab7dda41b3579ddebeaaff838c8ccaa6d0ba71b60fbf4e5b57",
     251, "650a1bc52ce253d5e240869e2a6aa3408fd99b6fbf438b03c070fb6150cb1dc2"),
    ("arv2-wf-test-2023", "2023-02-01", "2024-01-02", 230,
     "e023ce427c9c6b0bb50a91c647dc6c29149483f5dee5b0275ee7c414ec867de4",
     "2024-01-30", 249,
     "a180c5b8e47568ea7e2f25047da7bcd0f02a79b70707bdb8869a222ef7daa24c",
     250, "190ca48ba3b49be18b3b14c19738be910e908a530087bfbded6b63a3aa3222a3"),
    ("arv2-wf-test-2024", "2024-01-31", "2025-01-02", 232,
     "8e05e03d97ebd5d5b4df582754c6f93cfe64900d3c90ed7e33d85b19278ea8b8",
     "2025-01-31", 251,
     "d58d7eb723b502451084f09498e0f4ff788a91cde58b2d883a97082cfaeb578b",
     252, "8931210f30fe4812340ea42716116a6a43f22de60f7550279cf73a2c08d09a66"),
    ("arv2-wf-test-2025", "2025-02-03", "2026-01-02", 230,
     "070c2d06e6f91432c35064c50affbb6e540ba35dd0a665f3e8e4a269bc4bf74f",
     "2026-01-30", 249,
     "fa2ee8d3a5deed8f57c8c184365fd9c00bf4958fdcda8916650fbf793ac74ca3",
     250, "45ac3285620a129beb41756aa2a3ed56d035992897d19df61be8d2aa6f512acc"),
)
GENERIC_FM_BOOTSTRAP_EXECUTION_DEFINED = False
ECONOMIC_BOOTSTRAP_EXECUTION_DEFINED = False


def _context() -> Context:
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[DivisionByZero, InvalidOperation, Overflow, Underflow],
    )


def _decimal(value: Fraction) -> Decimal:
    with localcontext(_context()):
        return +(Decimal(value.numerator) / Decimal(value.denominator))


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    # Decimal.__abs__ applies the active arithmetic context and can therefore
    # round a wider input before it is used as the deterministic ordering key.
    # copy_abs() is exact and preserves the frozen magnitude/signed ordering.
    ordered = sorted(tuple(values), key=lambda value: (value.copy_abs(), value))
    with localcontext(_context()):
        total = Decimal(0)
        for value in ordered:
            total = +(total + value)
        return total


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise FormalEvaluationError("mean requires at least one value")
    with localcontext(_context()):
        return +(_stable_sum(values) / Decimal(len(values)))


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise FormalEvaluationError("median requires at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext(_context()):
        return +((ordered[middle - 1] + ordered[middle]) / Decimal(2))


def _average_ranks(values: tuple[Decimal, ...]) -> tuple[Fraction, ...]:
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [Fraction(0) for _ in values]
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = Fraction((start + 1) + end, 2)
        for position in range(start, end):
            result[ordered[position]] = rank
        start = end
    return tuple(result)


def _spearman(scores: tuple[Decimal, ...], outcomes: tuple[Decimal, ...]) -> Decimal:
    if len(scores) != len(outcomes) or len(scores) < 2:
        raise FormalEvaluationError("Spearman inputs must have equal nontrivial length")
    score_ranks = _average_ranks(scores)
    outcome_ranks = _average_ranks(outcomes)
    score_mean = sum(score_ranks, Fraction(0)) / len(score_ranks)
    outcome_mean = sum(outcome_ranks, Fraction(0)) / len(outcome_ranks)
    numerator = sum(
        ((left - score_mean) * (right - outcome_mean)
         for left, right in zip(score_ranks, outcome_ranks, strict=True)),
        Fraction(0),
    )
    left_square = sum(
        ((value - score_mean) ** 2 for value in score_ranks), Fraction(0)
    )
    right_square = sum(
        ((value - outcome_mean) ** 2 for value in outcome_ranks), Fraction(0)
    )
    if left_square == 0 or right_square == 0:
        raise FormalEvaluationError("Spearman input is constant")
    with localcontext(_context()):
        denominator = (_decimal(left_square) * _decimal(right_square)).sqrt()
        return +(_decimal(numerator) / denominator)


class Disposition(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID_DATA = "INVALID_DATA"


class RefusalReason(str, Enum):
    MISSING_OUTCOME = "missing_outcome"
    MISSING_PREOPEN_CONTROL = "missing_preopen_control"
    IMMATURE_OUTCOME = "immature_outcome"
    TERMINAL_PAYOFF_UNRESOLVED = "terminal_payoff_unresolved"
    CROSS_DATE_COMMON_EVENT_COMPONENT = "cross_date_common_event_component"
    OUTCOME_IDENTITY_INVALID = "outcome_identity_invalid"
    MISSING_DAILY_SECURITY_RETURN = "missing_daily_security_return"
    MISSING_DAILY_BENCHMARK_RETURN = "missing_daily_benchmark_return"


class EconomicOutcomeDisposition(str, Enum):
    RETURN = "one_session_total_return"
    NAMED_REFUSAL = "named_return_refusal"


@dataclasses.dataclass(frozen=True, slots=True)
class NamedDecimal:
    name: str
    value: Decimal


@dataclasses.dataclass(frozen=True, slots=True)
class NamedBinary:
    name: str
    value: int


@dataclasses.dataclass(frozen=True, slots=True)
class SessionPoint:
    session: date
    session_position: int


@dataclasses.dataclass(frozen=True, slots=True)
class FoldSessionAxis:
    fold_id: str
    horizon_sessions: int
    sessions: tuple[SessionPoint, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicObservationAxis:
    fold_id: str
    sessions: tuple[SessionPoint, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class PowerFloorBinding:
    receipt_id: str
    receipt_sha256: str
    required_valid_dates: int
    required_connected_components: int
    h20_test_session_capacity: int
    preoutcome_candidate_date_count: int
    valid_h20_test_session_count: int
    refused_h20_test_session_count: int
    missing_h20_test_session_count: int
    connected_component_instance_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class EvaluationRow:
    row_id: str
    row_sha256: str
    source_lineage_sha256: str
    fold_id: str
    decision_session: date
    session_position: int
    security_id: str
    industry_id: str
    common_event_component_id: str
    horizon_sessions: int
    firm_specific_score: Decimal
    global_score: Decimal
    structural_zero: bool
    continuous_controls: tuple[NamedDecimal, ...]
    binary_controls: tuple[NamedBinary, ...]
    active_event_indicator: int
    absolute_contribution_weighted_publication_to_entry_jump: Decimal
    excess_total_return: Decimal
    rating_action: str | None
    earnings_anchor_signed_session_distance: int | None
    gross_security_total_return: Decimal | None
    benchmark_total_return: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class EvaluationRefusal:
    refusal_id: str
    refusal_sha256: str
    source_lineage_sha256: str
    fold_id: str
    decision_session: date
    session_position: int
    security_id: str
    horizon_sessions: int
    reason: RefusalReason


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicDecision:
    row_id: str
    row_sha256: str
    decision_lineage_sha256: str
    security_id: str
    firm_specific_score: Decimal
    realized_volatility_60d: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicSecurityOutcome:
    row_id: str
    row_sha256: str
    outcome_lineage_sha256: str
    security_id: str
    disposition: EconomicOutcomeDisposition
    gross_total_return: Decimal | None
    reason: RefusalReason | None
    terminal_payoff_applied: bool


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicSession:
    session_id: str
    session_sha256: str
    source_lineage_sha256: str
    fold_id: str
    session: date
    session_position: int
    benchmark_total_return: Decimal | None
    benchmark_refusal_reason: RefusalReason | None
    decisions: tuple[EconomicDecision, ...]
    security_outcomes: tuple[EconomicSecurityOutcome, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class FormalEvaluationInput:
    input_id: str
    input_sha256: str
    schema: str
    source_view_id: str
    source_bundle_id: str
    source_bundle_sha256: str
    source_artifact_sha256: str
    bootstrap_seed_sha256: str
    fold_axes: tuple[FoldSessionAxis, ...]
    economic_observation_axes: tuple[EconomicObservationAxis, ...]
    economic_execution_definition_sha256: str
    power_floor: PowerFloorBinding
    rows: tuple[EvaluationRow, ...]
    refusals: tuple[EvaluationRefusal, ...]
    economic_sessions: tuple[EconomicSession, ...]

    @property
    def filesystem_available(self) -> bool:
        return False

    @property
    def network_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def quantconnect_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, slots=True)
class CoverageSummary:
    slice_id: str
    fold_id: str | None
    horizon_sessions: int
    accepted_rows: int
    refused_rows: int
    refusals_by_reason: tuple[tuple[str, int], ...]
    accepted_component_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class IcSummary:
    slice_id: str
    fold_id: str | None
    horizon_sessions: int
    arm: str
    status: Disposition
    valid_date_count: int
    invalid_date_count: int
    invalid_dates_by_reason: tuple[tuple[str, int], ...]
    mean: Decimal | None
    median: Decimal | None
    positive_date_share: Fraction | None
    icir: Decimal | None
    hac_lag_sessions: int
    hac_pair_counts: tuple[int, ...]
    hac_standard_error: Decimal | None
    hac_t: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class FamaMacBethSummary:
    slice_id: str
    fold_id: str | None
    horizon_sessions: int
    arm: str
    coefficient: str
    status: Disposition
    valid_date_count: int
    invalid_date_count: int
    invalid_dates_by_reason: tuple[tuple[str, int], ...]
    parameter_count_by_date: tuple[tuple[str, int], ...]
    mean_beta: Decimal | None
    median_beta: Decimal | None
    hac_lag_sessions: int
    hac_pair_counts: tuple[int, ...]
    hac_standard_error: Decimal | None
    hac_t: Decimal | None
    bootstrap_resamples: int | None
    centered_two_sided_p_value: Fraction | None


@dataclasses.dataclass(frozen=True, slots=True)
class PairedIcSummary:
    slice_id: str
    fold_id: str | None
    horizon_sessions: int
    status: Disposition
    valid_date_count: int
    invalid_date_count: int
    invalid_dates_by_reason: tuple[tuple[str, int], ...]
    mean_firm_ic: Decimal | None
    mean_global_ic: Decimal | None
    observed_difference: Decimal | None
    bootstrap_resamples: int | None
    one_sided_q95: Decimal | None
    one_sided_lcb95: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicCostSummary:
    slice_id: str
    cost_bps_per_side: int
    status: Disposition
    session_count: int
    valid_return_session_count: int
    refused_return_session_count: int
    invested_session_count: int
    cash_sleeve_count: int
    selected_sleeve_count: int
    mean_net_excess_daily_return: Decimal | None
    cumulative_net_total_return: Decimal | None
    mean_daily_turnover: Decimal | None
    terminal_liquidation_turnover: Decimal
    bootstrap_resamples: int | None
    centered_two_sided_p_value: Fraction | None
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicTrialObservation:
    """One admissible dated economic observation retained for reporting.

    The formal statistic is net excess return, but portfolio wealth, SPY
    wealth, drawdown, turnover, overlap, and DSR require the constituent
    values.  Keeping this fixed-axis aggregate avoids both raw market export
    and the earlier incorrect compounding of excess return as portfolio
    wealth.
    """

    fold_id: str
    session: date
    session_position: int
    cost_bps_per_side: int
    gross_portfolio_total_return: Decimal
    benchmark_total_return: Decimal
    net_portfolio_total_return: Decimal
    net_excess_daily_total_return: Decimal
    turnover: Decimal
    sleeve_security_incidence_count: int
    duplicate_sleeve_security_incidence_count: int
    terminal_liquidation: bool


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicTrialFoldCensus:
    """Exact fold-local accounting paired with retained daily aggregates."""

    fold_id: str
    cost_bps_per_side: int
    session_count: int
    valid_return_session_count: int
    refused_return_session_count: int
    invested_session_count: int
    cash_sleeve_count: int
    selected_sleeve_count: int
    terminal_liquidation_turnover: Decimal
    refusal_counts: tuple[tuple[str, int], ...]
    refusal_counts_by_session: tuple[
        tuple[date, tuple[tuple[str, int], ...]], ...
    ]
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class DailyInformationCoefficientObservation:
    """Fixed-axis daily IC sufficient statistics for required report plots."""

    fold_id: str
    decision_session: date
    session_position: int
    horizon_sessions: int
    firm_specific_ic: Decimal | None
    firm_specific_reason: str | None
    global_map_ic: Decimal | None
    global_map_reason: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class PrimaryGateSummary:
    gate_id: str
    status: Disposition
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class FormalEvaluationReportV2:
    report_id: str
    report_sha256: str
    schema: str
    status: str
    authority: str
    evaluation_id: str
    source_view_id: str
    input_id: str
    input_sha256: str
    bootstrap_seed_sha256: str
    formal_fold_ids: tuple[str, ...]
    descriptive_fold_ids: tuple[str, ...]
    coverage: tuple[CoverageSummary, ...]
    ic_summaries: tuple[IcSummary, ...]
    fama_macbeth_summaries: tuple[FamaMacBethSummary, ...]
    paired_ic_summaries: tuple[PairedIcSummary, ...]
    economic_summaries: tuple[EconomicCostSummary, ...]
    primary_gates: tuple[PrimaryGateSummary, ...]
    disposition: Disposition
    disposition_reasons: tuple[str, ...]
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def result_read_authority_available(self) -> bool:
        return False

    @property
    def result_disposition_authority_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


# The successor deliberately owns the public report name.
FormalEvaluationReport = FormalEvaluationReportV2


def _v2_finite_decimal(
    value: object, name: str, *, nonnegative: bool = False
) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise FormalEvaluationError(f"{name} must be an exact finite Decimal")
    if nonnegative and value < 0:
        raise FormalEvaluationError(f"{name} must be nonnegative")
    return value


def _v2_safe_id(value: object, name: str) -> str:
    if type(value) is not str or _V2_SAFE_ID.fullmatch(value) is None:
        raise FormalEvaluationError(f"{name} must be a bounded safe identifier")
    return value


def _v2_security_id(value: object, name: str) -> str:
    if type(value) is not str or _V2_SECURITY_ID.fullmatch(value) is None:
        raise FormalEvaluationError(
            f"{name} must be a bounded permanent security identifier"
        )
    return value


def _v2_session_axis_sha256(points: tuple[SessionPoint, ...]) -> str:
    payload = json.dumps(
        tuple(point.session.isoformat() for point in points),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v2_economic_axis_sha256(points: tuple[SessionPoint, ...]) -> str:
    payload = (
        json.dumps(
            [point.session.isoformat() for point in points],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v2_sha(value: object, name: str) -> str:
    if type(value) is not str or _V2_HEX64.fullmatch(value) is None:
        raise FormalEvaluationError(f"{name} must be a lowercase SHA-256")
    return value


def _v2_int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FormalEvaluationError(f"{name} must be an exact integer >= {minimum}")
    return value


def _require_power_floor_binding(
    value: PowerFloorBinding, *, context: str,
) -> PowerFloorBinding:
    if type(value) is not PowerFloorBinding:
        raise FormalEvaluationError(f"{context} power floor changed type")
    _v2_safe_id(value.receipt_id, f"{context} power receipt_id")
    _v2_sha(value.receipt_sha256, f"{context} power receipt_sha256")
    _v2_int(
        value.required_valid_dates,
        f"{context} required valid dates",
        minimum=MINIMUM_VALID_DATES,
    )
    _v2_int(
        value.required_connected_components,
        f"{context} required connected components",
        minimum=50,
    )
    census_counts = (
        value.h20_test_session_capacity,
        value.preoutcome_candidate_date_count,
        value.valid_h20_test_session_count,
        value.refused_h20_test_session_count,
        value.missing_h20_test_session_count,
        value.connected_component_instance_count,
    )
    if any(type(item) is not int or item < 0 for item in census_counts):
        raise FormalEvaluationError(
            f"{context} authenticated H20 census count changed"
        )
    if (
        value.h20_test_session_capacity != H20_TEST_SESSION_CAPACITY
        or value.preoutcome_candidate_date_count
        != (
            value.valid_h20_test_session_count
            + value.refused_h20_test_session_count
        )
        or value.h20_test_session_capacity
        != (
            value.preoutcome_candidate_date_count
            + value.missing_h20_test_session_count
        )
        or value.valid_h20_test_session_count < value.required_valid_dates
        or value.connected_component_instance_count
        < value.required_connected_components
    ):
        raise FormalEvaluationError(
            f"{context} authenticated H20 power census does not reconcile"
        )
    return value


_V2_CANONICAL_TYPES = (
    NamedDecimal, NamedBinary, SessionPoint, FoldSessionAxis,
    EconomicObservationAxis, PowerFloorBinding,
    EvaluationRow, EvaluationRefusal, EconomicDecision,
    EconomicSecurityOutcome, EconomicSession,
    FormalEvaluationInput, CoverageSummary, IcSummary, FamaMacBethSummary,
    PairedIcSummary, EconomicCostSummary, PrimaryGateSummary,
    FormalEvaluationReportV2,
)


def _v2_canonical(value: object, *, omit_identity: bool = False) -> object:
    if type(value) in {str, int, bool} or value is None:
        return value
    if type(value) is Decimal:
        _v2_finite_decimal(value, "canonical Decimal")
        return {"decimal": str(value)}
    if type(value) is Fraction:
        return {"fraction": [value.numerator, value.denominator]}
    if type(value) is date:
        return {"date": value.isoformat()}
    if type(value) is tuple:
        return [_v2_canonical(item, omit_identity=omit_identity) for item in value]
    if type(value) in {Disposition, RefusalReason, EconomicOutcomeDisposition}:
        return value.value
    if type(value) in _V2_CANONICAL_TYPES:
        omitted = {"_canonical_document"}
        if omit_identity:
            identity_fields = {
                EvaluationRow: {"row_id", "row_sha256"},
                EvaluationRefusal: {"refusal_id", "refusal_sha256"},
                EconomicDecision: {"row_id", "row_sha256"},
                EconomicSecurityOutcome: {"row_id", "row_sha256"},
                EconomicSession: {"session_id", "session_sha256"},
                FormalEvaluationInput: {"input_id", "input_sha256"},
                FormalEvaluationReportV2: {"report_id", "report_sha256"},
            }
            omitted.update(identity_fields.get(type(value), set()))
        return {
            field.name: _v2_canonical(
                getattr(value, field.name), omit_identity=omit_identity
            )
            for field in dataclasses.fields(value)
            if field.name not in omitted
        }
    raise FormalEvaluationError("noncanonical value in evaluation artifact")


def _v2_bytes(value: object, *, omit_identity: bool = False) -> bytes:
    return json.dumps(
        _v2_canonical(value, omit_identity=omit_identity),
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")


def _v2_digest(value: object) -> str:
    return hashlib.sha256(_v2_bytes(value, omit_identity=True)).hexdigest()


def _v2_identity(prefix: str, digest: str) -> str:
    return f"{prefix}{digest[:24]}"


def build_evaluation_row(
    *, source_lineage_sha256: str, fold_id: str, decision_session: date,
    session_position: int, security_id: str, industry_id: str,
    common_event_component_id: str, horizon_sessions: int,
    firm_specific_score: Decimal, global_score: Decimal, structural_zero: bool,
    continuous_control_values: tuple[Decimal, ...],
    binary_control_values: tuple[int, ...], active_event_indicator: int,
    absolute_contribution_weighted_publication_to_entry_jump: Decimal,
    excess_total_return: Decimal,
    rating_action: str | None = None,
    earnings_anchor_signed_session_distance: int | None = None,
    gross_security_total_return: Decimal | None = None,
    benchmark_total_return: Decimal | None = None,
) -> EvaluationRow:
    """Construct one content-addressed all-controls outcome row."""
    if type(continuous_control_values) is not tuple or len(continuous_control_values) != 19:
        raise FormalEvaluationError("exactly 19 continuous controls are required")
    if type(binary_control_values) is not tuple or len(binary_control_values) != 6:
        raise FormalEvaluationError("exactly six binary controls are required")
    value = EvaluationRow(
        "", "", source_lineage_sha256, fold_id, decision_session,
        session_position, security_id, industry_id, common_event_component_id,
        horizon_sessions, firm_specific_score, global_score, structural_zero,
        tuple(NamedDecimal(name, item) for name, item in zip(
            CONTINUOUS_CONTROL_NAMES, continuous_control_values, strict=True
        )),
        tuple(NamedBinary(name, item) for name, item in zip(
            BINARY_CONTROL_NAMES, binary_control_values, strict=True
        )),
        active_event_indicator,
        absolute_contribution_weighted_publication_to_entry_jump,
        excess_total_return,
        rating_action, earnings_anchor_signed_session_distance,
        gross_security_total_return, benchmark_total_return,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, row_id=_v2_identity("arv2-evaluation-row-", digest),
        row_sha256=digest,
    )
    _require_evaluation_row(result)
    return result


def build_evaluation_refusal(
    *, source_lineage_sha256: str, fold_id: str, decision_session: date,
    session_position: int, security_id: str, horizon_sessions: int,
    reason: RefusalReason,
) -> EvaluationRefusal:
    value = EvaluationRefusal(
        "", "", source_lineage_sha256, fold_id, decision_session,
        session_position, security_id, horizon_sessions, reason,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, refusal_id=_v2_identity("arv2-evaluation-refusal-", digest),
        refusal_sha256=digest,
    )
    _require_refusal(result)
    return result


def build_economic_decision(
    *, decision_lineage_sha256: str, security_id: str,
    firm_specific_score: Decimal,
    realized_volatility_60d: Decimal | None = None,
) -> EconomicDecision:
    """Bind one current-session TEST score used to form a new sleeve."""

    value = EconomicDecision(
        "", "", decision_lineage_sha256, security_id, firm_specific_score,
        realized_volatility_60d,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, row_id=_v2_identity("arv2-economic-decision-", digest),
        row_sha256=digest,
    )
    _require_economic_decision(result)
    return result


def build_economic_security_outcome(
    *, outcome_lineage_sha256: str, security_id: str,
    disposition: EconomicOutcomeDisposition,
    gross_total_return: Decimal | None, reason: RefusalReason | None,
    terminal_payoff_applied: bool,
) -> EconomicSecurityOutcome:
    """Bind one held name's one-session return or its named refusal."""

    value = EconomicSecurityOutcome(
        "", "", outcome_lineage_sha256, security_id, disposition,
        gross_total_return, reason, terminal_payoff_applied,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, row_id=_v2_identity("arv2-economic-outcome-", digest),
        row_sha256=digest,
    )
    _require_economic_security_outcome(result)
    return result


def build_economic_session(
    *, source_lineage_sha256: str, fold_id: str, session: date,
    session_position: int, benchmark_total_return: Decimal | None,
    benchmark_refusal_reason: RefusalReason | None,
    decisions: tuple[EconomicDecision, ...],
    security_outcomes: tuple[EconomicSecurityOutcome, ...],
) -> EconomicSession:
    value = EconomicSession(
        "", "", source_lineage_sha256, fold_id, session, session_position,
        benchmark_total_return, benchmark_refusal_reason, decisions,
        security_outcomes,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, session_id=_v2_identity("arv2-economic-session-", digest),
        session_sha256=digest,
    )
    _require_economic_session(result)
    return result


def build_formal_evaluation_input(
    *, source_view_id: str, source_bundle_id: str, source_bundle_sha256: str,
    source_artifact_sha256: str, fold_axes: tuple[FoldSessionAxis, ...],
    economic_observation_axes: tuple[EconomicObservationAxis, ...],
    economic_execution_definition_sha256: str,
    power_floor: PowerFloorBinding, rows: tuple[EvaluationRow, ...],
    refusals: tuple[EvaluationRefusal, ...],
    economic_sessions: tuple[EconomicSession, ...],
) -> FormalEvaluationInput:
    value = FormalEvaluationInput(
        "", "", INPUT_SCHEMA, source_view_id, source_bundle_id,
        source_bundle_sha256,
        source_artifact_sha256, BOOTSTRAP_SEED_SHA256, fold_axes,
        economic_observation_axes, economic_execution_definition_sha256,
        power_floor, rows, refusals, economic_sessions,
    )
    digest = _v2_digest(value)
    result = dataclasses.replace(
        value, input_id=_v2_identity("arv2-formal-evaluation-input-", digest),
        input_sha256=digest,
    )
    require_formal_evaluation_input(result)
    return result


def _require_evaluation_row(value: EvaluationRow) -> EvaluationRow:
    if type(value) is not EvaluationRow:
        raise FormalEvaluationError("evaluation row changed type")
    _v2_safe_id(value.row_id, "row_id")
    _v2_sha(value.row_sha256, "row_sha256")
    _v2_sha(value.source_lineage_sha256, "source_lineage_sha256")
    if type(value.decision_session) is not date:
        raise FormalEvaluationError("decision_session changed type")
    _v2_int(value.session_position, "session_position")
    _v2_security_id(value.security_id, "security_id")
    for item, name in (
        (value.fold_id, "fold_id"), (value.industry_id, "industry_id"),
        (value.common_event_component_id, "common_event_component_id"),
    ):
        _v2_safe_id(item, name)
    if value.fold_id not in FORMAL_FOLD_IDS:
        raise FormalEvaluationError("evaluation row fold is outside the formal folds")
    if type(value.horizon_sessions) is not int or value.horizon_sessions not in HORIZONS:
        raise FormalEvaluationError("evaluation row horizon is not frozen")
    for item, name in (
        (value.firm_specific_score, "firm_specific_score"),
        (value.global_score, "global_score"),
    ):
        score = _v2_finite_decimal(item, name)
        if score < Decimal("-4") or score > Decimal("4"):
            raise FormalEvaluationError(f"{name} is outside the frozen clip")
    if type(value.structural_zero) is not bool:
        raise FormalEvaluationError("structural_zero changed type")
    if value.structural_zero and (
        value.firm_specific_score != 0 or value.global_score != 0
    ):
        raise FormalEvaluationError("structural-zero scores must remain exact zero")
    if type(value.continuous_controls) is not tuple or len(value.continuous_controls) != 19:
        raise FormalEvaluationError("evaluation row lacks all 19 continuous controls")
    if type(value.binary_controls) is not tuple or len(value.binary_controls) != 6:
        raise FormalEvaluationError("evaluation row lacks all six binary controls")
    for index, (item, expected) in enumerate(zip(
        value.continuous_controls, CONTINUOUS_CONTROL_NAMES, strict=True
    )):
        if type(item) is not NamedDecimal or type(item.name) is not str:
            raise FormalEvaluationError("continuous control topology changed")
        if item.name != expected:
            raise FormalEvaluationError(f"continuous control {index} name changed")
        _v2_finite_decimal(item.value, f"continuous control {expected}")
    for index, (item, expected) in enumerate(zip(
        value.binary_controls, BINARY_CONTROL_NAMES, strict=True
    )):
        if type(item) is not NamedBinary or type(item.name) is not str:
            raise FormalEvaluationError("binary control topology changed")
        if item.name != expected or type(item.value) is not int or item.value not in {0, 1}:
            raise FormalEvaluationError(f"binary control {index} changed")
    if type(value.active_event_indicator) is not int or value.active_event_indicator not in {0, 1}:
        raise FormalEvaluationError("active_event_indicator must be exact zero or one")
    _v2_finite_decimal(
        value.absolute_contribution_weighted_publication_to_entry_jump,
        "absolute_contribution_weighted_publication_to_entry_jump",
        nonnegative=True,
    )
    if value.structural_zero and (
        value.active_event_indicator != 0
        or value.absolute_contribution_weighted_publication_to_entry_jump != 0
    ):
        raise FormalEvaluationError(
            "structural-zero rows must have zero active-event outcome controls"
        )
    if not value.structural_zero and value.active_event_indicator != 1:
        raise FormalEvaluationError(
            "active signal rows must carry active_event_indicator one"
        )
    excess_total_return = _v2_finite_decimal(
        value.excess_total_return, "excess_total_return"
    )
    if value.rating_action is not None and (
        type(value.rating_action) is not str
        or value.rating_action not in {"upgrades", "downgrades"}
    ):
        raise FormalEvaluationError(
            "evaluation row rating_action is not a frozen directional action"
        )
    if value.earnings_anchor_signed_session_distance is not None and type(
        value.earnings_anchor_signed_session_distance
    ) is not int:
        raise FormalEvaluationError(
            "earnings anchor signed session distance changed type"
        )
    gross_return = value.gross_security_total_return
    benchmark_return = value.benchmark_total_return
    if (gross_return is None) is not (benchmark_return is None):
        raise FormalEvaluationError(
            "evaluation row gross and benchmark return presence differs"
        )
    if gross_return is not None:
        gross_return = _v2_finite_decimal(
            gross_return, "gross_security_total_return"
        )
        benchmark_return = _v2_finite_decimal(
            benchmark_return, "benchmark_total_return"
        )
        if gross_return < Decimal("-1") or benchmark_return < Decimal("-1"):
            raise FormalEvaluationError(
                "unlevered gross or benchmark total return is below -1"
            )
        with localcontext(_context()):
            derived_excess = +(gross_return - benchmark_return)
        if derived_excess != excess_total_return:
            raise FormalEvaluationError(
                "evaluation row excess return differs from gross minus benchmark"
            )
    digest = _v2_digest(value)
    if value.row_sha256 != digest or value.row_id != _v2_identity(
        "arv2-evaluation-row-", digest
    ):
        raise FormalEvaluationError("evaluation row content identity changed")
    return value


def _require_refusal(value: EvaluationRefusal) -> EvaluationRefusal:
    if type(value) is not EvaluationRefusal:
        raise FormalEvaluationError("evaluation refusal changed type")
    _v2_safe_id(value.refusal_id, "refusal_id")
    _v2_sha(value.refusal_sha256, "refusal_sha256")
    _v2_sha(value.source_lineage_sha256, "refusal source lineage")
    if type(value.fold_id) is not str or value.fold_id not in FORMAL_FOLD_IDS:
        raise FormalEvaluationError("refusal fold is outside the formal folds")
    if type(value.decision_session) is not date:
        raise FormalEvaluationError("refusal decision session changed type")
    _v2_int(value.session_position, "refusal session_position")
    _v2_security_id(value.security_id, "refusal security_id")
    if type(value.horizon_sessions) is not int or value.horizon_sessions not in HORIZONS:
        raise FormalEvaluationError("refusal horizon is not frozen")
    if type(value.reason) is not RefusalReason:
        raise FormalEvaluationError("refusal reason changed type")
    digest = _v2_digest(value)
    if value.refusal_sha256 != digest or value.refusal_id != _v2_identity(
        "arv2-evaluation-refusal-", digest
    ):
        raise FormalEvaluationError("evaluation refusal content identity changed")
    return value


def _require_economic_decision(value: EconomicDecision) -> EconomicDecision:
    if type(value) is not EconomicDecision:
        raise FormalEvaluationError("economic decision changed type")
    _v2_safe_id(value.row_id, "economic decision row_id")
    _v2_sha(value.row_sha256, "economic decision row_sha256")
    _v2_sha(value.decision_lineage_sha256, "economic decision lineage")
    _v2_security_id(value.security_id, "economic decision security_id")
    score = _v2_finite_decimal(value.firm_specific_score, "economic score")
    if score < Decimal("-4") or score > Decimal("4"):
        raise FormalEvaluationError("economic score is outside the frozen clip")
    if value.realized_volatility_60d is not None:
        _v2_finite_decimal(
            value.realized_volatility_60d,
            "economic decision realized_volatility_60d",
        )
    digest = _v2_digest(value)
    if value.row_sha256 != digest or value.row_id != _v2_identity(
        "arv2-economic-decision-", digest
    ):
        raise FormalEvaluationError("economic decision content identity changed")
    return value


def _require_economic_security_outcome(
    value: EconomicSecurityOutcome,
) -> EconomicSecurityOutcome:
    if type(value) is not EconomicSecurityOutcome:
        raise FormalEvaluationError("economic security outcome changed type")
    _v2_safe_id(value.row_id, "economic outcome row_id")
    _v2_sha(value.row_sha256, "economic outcome row_sha256")
    _v2_sha(value.outcome_lineage_sha256, "economic outcome lineage")
    _v2_security_id(value.security_id, "economic outcome security_id")
    if type(value.disposition) is not EconomicOutcomeDisposition:
        raise FormalEvaluationError("economic outcome disposition changed type")
    if type(value.terminal_payoff_applied) is not bool:
        raise FormalEvaluationError("terminal-payoff flag changed type")
    if value.disposition is EconomicOutcomeDisposition.RETURN:
        total_return = _v2_finite_decimal(
            value.gross_total_return, "one-session gross_total_return"
        )
        if total_return < Decimal("-1"):
            raise FormalEvaluationError("unlevered one-session return is below -1")
        if value.reason is not None:
            raise FormalEvaluationError("available economic return carries a refusal")
    else:
        if value.gross_total_return is not None:
            raise FormalEvaluationError("named return refusal carries a return")
        if type(value.reason) is not RefusalReason or value.reason not in {
            RefusalReason.MISSING_DAILY_SECURITY_RETURN,
            RefusalReason.TERMINAL_PAYOFF_UNRESOLVED,
            RefusalReason.OUTCOME_IDENTITY_INVALID,
        }:
            raise FormalEvaluationError("economic return refusal reason is not frozen")
        if value.terminal_payoff_applied:
            raise FormalEvaluationError("refused return claims a terminal payoff")
    digest = _v2_digest(value)
    if value.row_sha256 != digest or value.row_id != _v2_identity(
        "arv2-economic-outcome-", digest
    ):
        raise FormalEvaluationError("economic outcome content identity changed")
    return value


def _require_economic_session(value: EconomicSession) -> EconomicSession:
    if type(value) is not EconomicSession:
        raise FormalEvaluationError("economic session changed type")
    _v2_safe_id(value.session_id, "economic session_id")
    _v2_sha(value.session_sha256, "economic session_sha256")
    _v2_sha(value.source_lineage_sha256, "economic session source lineage")
    if type(value.fold_id) is not str or value.fold_id not in FORMAL_FOLD_IDS:
        raise FormalEvaluationError("economic session fold is outside formal folds")
    if type(value.session) is not date:
        raise FormalEvaluationError("economic session date changed type")
    _v2_int(value.session_position, "economic session_position")
    if value.benchmark_refusal_reason is None:
        benchmark = _v2_finite_decimal(
            value.benchmark_total_return, "benchmark_total_return"
        )
        if benchmark < Decimal("-1"):
            raise FormalEvaluationError("benchmark total return is below -1")
    else:
        if (
            type(value.benchmark_refusal_reason) is not RefusalReason
            or value.benchmark_refusal_reason not in {
                RefusalReason.MISSING_DAILY_BENCHMARK_RETURN,
                RefusalReason.OUTCOME_IDENTITY_INVALID,
            }
            or value.benchmark_total_return is not None
        ):
            raise FormalEvaluationError("benchmark refusal is not a frozen XOR state")
    if type(value.decisions) is not tuple:
        raise FormalEvaluationError("economic decisions changed container type")
    previous: str | None = None
    for item in value.decisions:
        _require_economic_decision(item)
        if previous is not None and item.security_id <= previous:
            raise FormalEvaluationError(
                "economic decisions must have unique ascending security IDs"
            )
        previous = item.security_id
    if type(value.security_outcomes) is not tuple:
        raise FormalEvaluationError("economic outcomes changed container type")
    previous = None
    for item in value.security_outcomes:
        _require_economic_security_outcome(item)
        if previous is not None and item.security_id <= previous:
            raise FormalEvaluationError(
                "economic outcomes must have unique ascending security IDs"
            )
        previous = item.security_id
    digest = _v2_digest(value)
    if value.session_sha256 != digest or value.session_id != _v2_identity(
        "arv2-economic-session-", digest
    ):
        raise FormalEvaluationError("economic session content identity changed")
    return value


def _require_economic_observation_axes(
    axes: tuple[EconomicObservationAxis, ...],
    *,
    global_date_positions: dict[date, int] | None = None,
    global_position_dates: dict[int, date] | None = None,
) -> dict[tuple[str, date], int]:
    if type(axes) is not tuple or len(axes) != len(FORMAL_FOLD_IDS):
        raise FormalEvaluationError(
            "all six economic observation axes are required"
        )
    date_positions = {} if global_date_positions is None else global_date_positions
    position_dates = {} if global_position_dates is None else global_position_dates
    result: dict[tuple[str, date], int] = {}
    for axis, frozen in zip(
        axes, ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES, strict=True
    ):
        if (
            type(axis) is not EconomicObservationAxis
            or axis.fold_id != frozen[0]
            or type(axis.sessions) is not tuple
            or len(axis.sessions) != frozen[8]
            or not axis.sessions
            or axis.sessions[0].session.isoformat() != frozen[1]
            or axis.sessions[-1].session.isoformat() != frozen[5]
            or _v2_economic_axis_sha256(axis.sessions) != frozen[9]
        ):
            raise FormalEvaluationError(
                "economic observation axis differs from its reviewed definition"
            )
        return_points = axis.sessions[:-1]
        decision_points = tuple(
            point
            for point in return_points
            if point.session < date.fromisoformat(frozen[2])
        )
        if (
            len(return_points) != frozen[6]
            or _v2_economic_axis_sha256(return_points) != frozen[7]
            or len(decision_points) != frozen[3]
            or _v2_economic_axis_sha256(decision_points) != frozen[4]
        ):
            raise FormalEvaluationError(
                "economic decision, runoff, or liquidation axis changed"
            )
        prior_date: date | None = None
        prior_position: int | None = None
        for point in axis.sessions:
            if type(point) is not SessionPoint or type(point.session) is not date:
                raise FormalEvaluationError(
                    "economic observation point changed type"
                )
            _v2_int(point.session_position, "economic observation position")
            if (
                (prior_date is not None and point.session <= prior_date)
                or (
                    prior_position is not None
                    and point.session_position <= prior_position
                )
                or date_positions.setdefault(
                    point.session, point.session_position
                ) != point.session_position
                or position_dates.setdefault(
                    point.session_position, point.session
                ) != point.session
            ):
                raise FormalEvaluationError(
                    "economic observation axis is not globally monotone"
                )
            key = (axis.fold_id, point.session)
            if key in result:
                raise FormalEvaluationError(
                    "economic observation axis duplicated a session"
                )
            result[key] = point.session_position
            prior_date = point.session
            prior_position = point.session_position
    return result


def require_formal_evaluation_input(
    value: FormalEvaluationInput,
) -> FormalEvaluationInput:
    """Reauthenticate the entire typed census before any outcome arithmetic."""
    if type(value) is not FormalEvaluationInput:
        raise FormalEvaluationError("formal evaluation input changed type")
    for name in (
        "filesystem_available", "network_available", "outcome_access_available",
        "quantconnect_available",
    ):
        if getattr(value, name) is not False:
            raise FormalEvaluationError("formal evaluation input acquired authority")
    _v2_safe_id(value.input_id, "input_id")
    _v2_sha(value.input_sha256, "input_sha256")
    if type(value.schema) is not str or value.schema != INPUT_SCHEMA:
        raise FormalEvaluationError("formal evaluation input schema changed")
    if type(value.source_view_id) is not str or value.source_view_id not in SOURCE_VIEW_IDS:
        raise FormalEvaluationError("formal evaluation input source view is not frozen")
    _v2_safe_id(value.source_bundle_id, "source_bundle_id")
    _v2_sha(value.source_bundle_sha256, "source_bundle_sha256")
    _v2_sha(value.source_artifact_sha256, "source_artifact_sha256")
    _v2_sha(value.bootstrap_seed_sha256, "bootstrap_seed_sha256")
    if value.bootstrap_seed_sha256 != BOOTSTRAP_SEED_SHA256:
        raise FormalEvaluationError("bootstrap seed is not the frozen pre-outcome seed")
    _v2_sha(
        value.economic_execution_definition_sha256,
        "economic execution definition sha256",
    )
    if (
        value.economic_execution_definition_sha256
        != ECONOMIC_EXECUTION_DEFINITION_SHA256
    ):
        raise FormalEvaluationError(
            "economic execution definition is not the reviewed definition"
        )
    if type(value.fold_axes) is not tuple or len(value.fold_axes) != 24:
        raise FormalEvaluationError("all 24 fold-horizon axes are required")
    _require_power_floor_binding(value.power_floor, context="formal input")
    axis_lookup: dict[tuple[str, int, date], int] = {}
    global_date_positions: dict[date, int] = {}
    global_position_dates: dict[int, date] = {}
    expected_axes = tuple(
        (fold, horizon) for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    )
    for axis_index, (axis, expected) in enumerate(zip(
        value.fold_axes, expected_axes, strict=True
    )):
        if type(axis) is not FoldSessionAxis or type(axis.fold_id) is not str:
            raise FormalEvaluationError("fold axis topology changed")
        if (
            axis.fold_id != expected[0]
            or type(axis.horizon_sessions) is not int
            or axis.horizon_sessions != expected[1]
        ):
            raise FormalEvaluationError("fold-horizon axes are incomplete or reordered")
        if type(axis.sessions) is not tuple or len(axis.sessions) < 20:
            raise FormalEvaluationError("fold axis is not a complete block-capable axis")
        frozen = FORMAL_FOLD_HORIZON_AXIS_SUMMARIES[axis_index]
        if (
            frozen[:2] != expected
            or len(axis.sessions) != frozen[4]
            or axis.sessions[0].session.isoformat() != frozen[2]
            or _v2_session_axis_sha256(axis.sessions) != frozen[5]
        ):
            raise FormalEvaluationError(
                "fold axis differs from the exact reviewed horizon geometry"
            )
        previous_date: date | None = None
        previous_position: int | None = None
        for point in axis.sessions:
            if type(point) is not SessionPoint or type(point.session) is not date:
                raise FormalEvaluationError("session point topology changed")
            _v2_int(point.session_position, "axis session_position")
            if previous_date is not None and point.session <= previous_date:
                raise FormalEvaluationError("fold session dates are not strictly increasing")
            if previous_position is not None and point.session_position <= previous_position:
                raise FormalEvaluationError("fold session positions are not strictly increasing")
            existing_position = global_date_positions.setdefault(
                point.session, point.session_position
            )
            if existing_position != point.session_position:
                raise FormalEvaluationError("one session has inconsistent global positions")
            existing_date = global_position_dates.setdefault(
                point.session_position, point.session
            )
            if existing_date != point.session:
                raise FormalEvaluationError("one global position names two sessions")
            axis_key = (axis.fold_id, axis.horizon_sessions, point.session)
            if axis_key in axis_lookup:
                raise FormalEvaluationError("session appears twice in one fold-horizon axis")
            axis_lookup[axis_key] = point.session_position
            previous_date = point.session
            previous_position = point.session_position
        if axis_index >= len(HORIZONS):
            previous_same_horizon = value.fold_axes[axis_index - len(HORIZONS)]
            if axis.sessions[0].session_position <= previous_same_horizon.sessions[-1].session_position:
                raise FormalEvaluationError("same-horizon formal fold axes overlap")
    if sum(
        len(axis.sessions)
        for axis in value.fold_axes
        if axis.horizon_sessions == SLEEVE_HOLDING_SESSIONS
    ) != value.power_floor.h20_test_session_capacity:
        raise FormalEvaluationError(
            "formal input H20 axis differs from authenticated power census"
        )
    economic_axis_lookup = _require_economic_observation_axes(
        value.economic_observation_axes,
        global_date_positions=global_date_positions,
        global_position_dates=global_position_dates,
    )
    for field_name in ("rows", "refusals", "economic_sessions"):
        if type(getattr(value, field_name)) is not tuple:
            raise FormalEvaluationError(f"{field_name} changed container type")
    accepted_keys: set[tuple[str, date, str, int]] = set()
    row_order: list[tuple[int, int, str, int]] = []
    invariant_by_security_date: dict[tuple[str, date, str], tuple[object, ...]] = {}
    lineage_by_security_date: dict[tuple[str, date, str], str] = {}
    component_dates: dict[str, date] = {}
    h20_by_date_security: dict[tuple[str, date, str], EvaluationRow] = {}
    fold_ord = {fold: index for index, fold in enumerate(FORMAL_FOLD_IDS)}
    for row in value.rows:
        _require_evaluation_row(row)
        position = axis_lookup.get((
            row.fold_id, row.horizon_sessions, row.decision_session
        ))
        if position is None or position != row.session_position:
            raise FormalEvaluationError("evaluation row is not on its exact fold axis")
        key = (row.fold_id, row.decision_session, row.security_id, row.horizon_sessions)
        if key in accepted_keys:
            raise FormalEvaluationError("duplicate accepted census row")
        accepted_keys.add(key)
        row_order.append((fold_ord[row.fold_id], row.session_position, row.security_id, row.horizon_sessions))
        invariant = (
            row.source_lineage_sha256, row.industry_id,
            row.common_event_component_id, row.firm_specific_score,
            row.global_score, row.structural_zero, row.continuous_controls,
            row.binary_controls, row.active_event_indicator,
            row.absolute_contribution_weighted_publication_to_entry_jump,
            row.rating_action,
            row.earnings_anchor_signed_session_distance,
        )
        invariant_key = (row.fold_id, row.decision_session, row.security_id)
        prior_lineage = lineage_by_security_date.setdefault(
            invariant_key, row.source_lineage_sha256
        )
        if prior_lineage != row.source_lineage_sha256:
            raise FormalEvaluationError("horizon rows disagree on source lineage")
        prior = invariant_by_security_date.setdefault(invariant_key, invariant)
        if invariant != prior:
            raise FormalEvaluationError("horizon rows disagree on pre-outcome fields")
        prior_component_date = component_dates.setdefault(
            row.common_event_component_id, row.decision_session
        )
        if prior_component_date != row.decision_session:
            raise FormalEvaluationError("accepted common-event component crosses dates")
        if row.horizon_sessions == 20:
            h20_by_date_security[invariant_key] = row
    if row_order != sorted(row_order):
        raise FormalEvaluationError("evaluation rows are not in canonical order")
    refusal_keys: set[tuple[str, date, str, int]] = set()
    refusal_order: list[tuple[int, int, str, int]] = []
    for item in value.refusals:
        _require_refusal(item)
        position = axis_lookup.get((
            item.fold_id, item.horizon_sessions, item.decision_session
        ))
        if position is None or position != item.session_position:
            raise FormalEvaluationError("evaluation refusal is not on its fold axis")
        key = (item.fold_id, item.decision_session, item.security_id, item.horizon_sessions)
        if key in accepted_keys or key in refusal_keys:
            raise FormalEvaluationError("accepted/refused census identity is duplicated")
        lineage_key = (item.fold_id, item.decision_session, item.security_id)
        prior_lineage = lineage_by_security_date.setdefault(
            lineage_key, item.source_lineage_sha256
        )
        if prior_lineage != item.source_lineage_sha256:
            raise FormalEvaluationError(
                "accepted/refused horizons disagree on source lineage"
            )
        refusal_keys.add(key)
        refusal_order.append((fold_ord[item.fold_id], item.session_position, item.security_id, item.horizon_sessions))
    if refusal_order != sorted(refusal_order):
        raise FormalEvaluationError("evaluation refusals are not in canonical order")
    economic_order: list[tuple[int, int]] = []
    economic_keys: set[tuple[str, date]] = set()
    active_by_fold: dict[str, list[_ActiveSleeve]] = {
        fold: [] for fold in FORMAL_FOLD_IDS
    }
    for session in value.economic_sessions:
        _require_economic_session(session)
        position = economic_axis_lookup.get((session.fold_id, session.session))
        if position is None or position != session.session_position:
            raise FormalEvaluationError(
                "economic session is not on its exact observation axis"
            )
        session_key = (session.fold_id, session.session)
        if session_key in economic_keys:
            raise FormalEvaluationError("duplicate economic session")
        economic_keys.add(session_key)
        economic_order.append((fold_ord[session.fold_id], session.session_position))
        decision_eligible = (
            session.fold_id, SLEEVE_HOLDING_SESSIONS, session.session
        ) in axis_lookup
        expected_decisions = {
            security_id: row
            for (fold_id, decision_date, security_id), row
            in h20_by_date_security.items()
            if fold_id == session.fold_id and decision_date == session.session
        }
        if tuple(item.security_id for item in session.decisions) != tuple(
            sorted(expected_decisions)
        ):
            raise FormalEvaluationError(
                "economic decision census differs from the exact H20 census"
            )
        for row in session.decisions:
            decision = h20_by_date_security.get(
                (session.fold_id, session.session, row.security_id)
            )
            if decision is None:
                raise FormalEvaluationError("economic row lacks an identical H20 decision row")
            if (
                row.decision_lineage_sha256 != decision.source_lineage_sha256
                or row.firm_specific_score != decision.firm_specific_score
            ):
                raise FormalEvaluationError("economic row changed decision score lineage")
        active = active_by_fold[session.fold_id]
        selected = _v2_selected_sleeve(session.decisions)
        if decision_eligible:
            active.append(_v2_new_sleeve(selected))
        elif session.decisions:
            raise FormalEvaluationError(
                "runoff or liquidation observation created a new sleeve"
            )
        expected_outcomes = tuple(sorted(_v2_targets(active)))
        if tuple(item.security_id for item in session.security_outcomes) != expected_outcomes:
            raise FormalEvaluationError(
                "economic held-name outcome census is not the exact active union"
            )
        terminal_session = date.fromisoformat(
            ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES[
                fold_ord[session.fold_id]
            ][5]
        )
        if session.session == terminal_session:
            if expected_outcomes or session.security_outcomes:
                raise FormalEvaluationError(
                    "terminal liquidation observation retained a target holding"
                )
            if (
                session.benchmark_total_return != Decimal(0)
                or session.benchmark_refusal_reason is not None
            ):
                raise FormalEvaluationError(
                    "terminal liquidation benchmark increment is not exact zero"
                )
        else:
            active_by_fold[session.fold_id] = _v2_advance_sleeves(
                active,
                frozenset(
                    item.security_id
                    for item in session.security_outcomes
                    if item.terminal_payoff_applied
                ),
            )
    if economic_order != sorted(economic_order):
        raise FormalEvaluationError("economic sessions are not in canonical order")
    expected_economic_keys = set(economic_axis_lookup)
    if economic_keys != expected_economic_keys:
        raise FormalEvaluationError("economic session axis is incomplete")
    digest = _v2_digest(value)
    if value.input_sha256 != digest or value.input_id != _v2_identity(
        "arv2-formal-evaluation-input-", digest
    ):
        raise FormalEvaluationError("formal evaluation input identity changed")
    return value


def _v2_dot(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal:
    if len(left) != len(right):
        raise FormalEvaluationError("dot-product vectors changed length")
    with localcontext(_context()):
        return +_stable_sum(tuple(+(a * b) for a, b in zip(left, right, strict=True)))


def _weighted_fama_macbeth_date(
    rows: tuple[EvaluationRow, ...], *, arm: str
) -> tuple[Decimal, Decimal, int] | str:
    """Fit one full weighted date cross-section with Decimal MGS QR."""
    if arm not in {"firm_specific", "global"}:
        raise FormalEvaluationError("unknown Fama-MacBeth arm")
    industries = tuple(sorted({row.industry_id for row in rows}))
    if not industries:
        return "empty_date"
    reference = industries[0]
    dummy_levels = industries[1:]
    parameter_count = 1 + 2 + len(ALL_CONTROL_NAMES) + len(dummy_levels)
    if len(rows) <= parameter_count + 20:
        return "not_strictly_more_than_parameter_count_plus_20"
    component_counts = Counter(row.common_event_component_id for row in rows)
    component_count = len(component_counts)
    if component_count == 0:
        return "no_common_event_components"
    design: list[tuple[Decimal, ...]] = []
    outcomes: list[Decimal] = []
    weights: list[Decimal] = []
    with localcontext(_context()):
        for row in rows:
            score = (
                row.firm_specific_score if arm == "firm_specific"
                else row.global_score
            )
            bullish = max(score, Decimal(0))
            bearish = min(score, Decimal(0))
            controls = tuple(item.value for item in row.continuous_controls) + tuple(
                Decimal(item.value) for item in row.binary_controls
            ) + (
                Decimal(row.active_event_indicator),
                row.absolute_contribution_weighted_publication_to_entry_jump,
            )
            design.append((
                Decimal(1), bullish, bearish, *controls,
                *(Decimal(row.industry_id == level) for level in dummy_levels),
            ))
            outcomes.append(row.excess_total_return)
            weights.append(+(
                Decimal(1) / Decimal(component_count)
                / Decimal(component_counts[row.common_event_component_id])
            ))
    columns = tuple(
        tuple(design[row_index][column_index] for row_index in range(len(rows)))
        for column_index in range(parameter_count)
    )
    weighted_columns: list[tuple[Decimal, ...]] = []
    weighted_y: tuple[Decimal, ...]
    with localcontext(_context()):
        square_roots = tuple(weight.sqrt() for weight in weights)
        weighted_columns = [
            tuple(+(value * root) for value, root in zip(column, square_roots, strict=True))
            for column in columns
        ]
        weighted_y = tuple(+(value * root) for value, root in zip(
            outcomes, square_roots, strict=True
        ))
    q_columns: list[tuple[Decimal, ...]] = []
    r_matrix = [[Decimal(0) for _ in range(parameter_count)] for _ in range(parameter_count)]
    diagonals: list[Decimal] = []
    with localcontext(_context()):
        for column_index, source in enumerate(weighted_columns):
            vector = list(source)
            for prior_index, q_column in enumerate(q_columns):
                projection = _v2_dot(q_column, tuple(vector))
                r_matrix[prior_index][column_index] = projection
                vector = [
                    +(item - projection * basis)
                    for item, basis in zip(vector, q_column, strict=True)
                ]
            norm_square = _v2_dot(tuple(vector), tuple(vector))
            if norm_square <= 0:
                return "rank_deficient_design"
            diagonal = norm_square.sqrt()
            diagonals.append(diagonal)
            r_matrix[column_index][column_index] = diagonal
            q_columns.append(tuple(+(item / diagonal) for item in vector))
        largest = max(diagonals)
        if any(item <= +(largest * RANK_RELATIVE_THRESHOLD) for item in diagonals):
            return "rank_deficient_design"
        qty = [_v2_dot(column, weighted_y) for column in q_columns]
        beta = [Decimal(0) for _ in range(parameter_count)]
        for row_index in range(parameter_count - 1, -1, -1):
            tail = _stable_sum(tuple(
                +(r_matrix[row_index][column_index] * beta[column_index])
                for column_index in range(row_index + 1, parameter_count)
            ))
            beta[row_index] = +(
                (qty[row_index] - tail) / r_matrix[row_index][row_index]
            )
    # positions 1 and 2 are the frozen bullish and bearish coefficients.
    del reference
    return beta[1], beta[2], parameter_count


def _v2_groups(
    value: FormalEvaluationInput, fold_ids: tuple[str, ...], horizon: int
) -> tuple[
    dict[tuple[str, date], tuple[EvaluationRow, ...]],
    dict[tuple[str, date], tuple[EvaluationRefusal, ...]],
]:
    rows: dict[tuple[str, date], list[EvaluationRow]] = {
        (axis.fold_id, point.session): []
        for axis in value.fold_axes
        if axis.fold_id in fold_ids and axis.horizon_sessions == horizon
        for point in axis.sessions
    }
    refusals: dict[tuple[str, date], list[EvaluationRefusal]] = {
        key: [] for key in rows
    }
    for item in value.rows:
        if item.fold_id in fold_ids and item.horizon_sessions == horizon:
            rows.setdefault((item.fold_id, item.decision_session), []).append(item)
    for item in value.refusals:
        if item.fold_id in fold_ids and item.horizon_sessions == horizon:
            refusals.setdefault((item.fold_id, item.decision_session), []).append(item)
    keys = sorted(set(rows) | set(refusals), key=lambda item: (
        FORMAL_FOLD_IDS.index(item[0]), item[1]
    ))
    return (
        {key: tuple(sorted(rows.get(key, ()), key=lambda row: row.security_id)) for key in keys},
        {key: tuple(sorted(refusals.get(key, ()), key=lambda row: row.security_id)) for key in keys},
    )


def _v2_single_ics(
    rows_by_date: dict[tuple[str, date], tuple[EvaluationRow, ...]],
    refusals_by_date: dict[tuple[str, date], tuple[EvaluationRefusal, ...]],
    *, arm: str,
) -> tuple[tuple[tuple[str, int, Decimal], ...], Counter[str]]:
    valid: list[tuple[str, int, Decimal]] = []
    invalid: Counter[str] = Counter()
    for key, rows in rows_by_date.items():
        refused = refusals_by_date[key]
        if refused:
            invalid[
                "outcome_identity_invalid"
                if any(item.reason is RefusalReason.OUTCOME_IDENTITY_INVALID for item in refused)
                else "named_row_refusal_present"
            ] += 1
            continue
        scores = tuple(
            row.firm_specific_score if arm == "firm_specific" else row.global_score
            for row in rows
        )
        outcomes = tuple(row.excess_total_return for row in rows)
        if len(rows) < MINIMUM_IC_ROWS:
            invalid["fewer_than_20_rows"] += 1
        elif len(set(scores)) == 1:
            invalid["constant_score"] += 1
        elif len(set(outcomes)) == 1:
            invalid["constant_outcome"] += 1
        else:
            valid.append((key[0], rows[0].session_position, _spearman(scores, outcomes)))
    return tuple(valid), invalid


def _v2_paired_ics(
    rows_by_date: dict[tuple[str, date], tuple[EvaluationRow, ...]],
    refusals_by_date: dict[tuple[str, date], tuple[EvaluationRefusal, ...]],
) -> tuple[tuple[tuple[str, int, Decimal, Decimal], ...], Counter[str]]:
    valid: list[tuple[str, int, Decimal, Decimal]] = []
    invalid: Counter[str] = Counter()
    for key, rows in rows_by_date.items():
        refused = refusals_by_date[key]
        if refused:
            invalid[
                "outcome_identity_invalid"
                if any(item.reason is RefusalReason.OUTCOME_IDENTITY_INVALID for item in refused)
                else "named_row_refusal_present"
            ] += 1
            continue
        firm = tuple(row.firm_specific_score for row in rows)
        global_scores = tuple(row.global_score for row in rows)
        outcomes = tuple(row.excess_total_return for row in rows)
        if len(rows) < MINIMUM_IC_ROWS:
            invalid["fewer_than_20_identical_rows"] += 1
        elif len(set(outcomes)) == 1:
            invalid["constant_shared_outcome"] += 1
        elif len(set(firm)) == 1 and len(set(global_scores)) == 1:
            invalid["both_arms_constant_score"] += 1
        else:
            firm_ic = Decimal(0) if len(set(firm)) == 1 else _spearman(firm, outcomes)
            global_ic = (
                Decimal(0) if len(set(global_scores)) == 1
                else _spearman(global_scores, outcomes)
            )
            valid.append((key[0], rows[0].session_position, firm_ic, global_ic))
    return tuple(valid), invalid


def _v2_fama_macbeth(
    rows_by_date: dict[tuple[str, date], tuple[EvaluationRow, ...]],
    refusals_by_date: dict[tuple[str, date], tuple[EvaluationRefusal, ...]],
    *, arm: str,
) -> tuple[
    tuple[tuple[str, int, Decimal, Decimal], ...], Counter[str],
    tuple[tuple[str, int], ...],
]:
    valid: list[tuple[str, int, Decimal, Decimal]] = []
    invalid: Counter[str] = Counter()
    parameter_counts: list[tuple[str, int]] = []
    for key, rows in rows_by_date.items():
        if refusals_by_date[key]:
            invalid[
                "outcome_identity_invalid"
                if any(
                    item.reason is RefusalReason.OUTCOME_IDENTITY_INVALID
                    for item in refusals_by_date[key]
                ) else "named_row_refusal_present"
            ] += 1
            continue
        fit = _weighted_fama_macbeth_date(rows, arm=arm)
        if type(fit) is str:
            invalid[fit] += 1
            continue
        bullish, bearish, count = fit
        parameter_counts.append((f"{key[0]}:{key[1].isoformat()}", count))
        valid.append((key[0], rows[0].session_position, bullish, bearish))
    return tuple(valid), invalid, tuple(parameter_counts)


def _v2_hac(
    values: tuple[tuple[int, Decimal], ...], lag: int
) -> tuple[tuple[int, ...], Decimal | None, Decimal | None]:
    """Bartlett HAC on actual session positions, never a compressed index."""
    if not values:
        return (), None, None
    mean = _mean(tuple(value for _, value in values))
    by_position = {position: value for position, value in values}
    if len(by_position) != len(values):
        raise FormalEvaluationError("HAC received duplicate session positions")
    gammas: list[Decimal] = []
    counts: list[int] = []
    with localcontext(_context()):
        for distance in range(lag + 1):
            products = tuple(
                +((value - mean) * (by_position[position - distance] - mean))
                for position, value in values
                if position - distance in by_position
            )
            counts.append(len(products))
            gammas.append(
                Decimal(0) if not products
                else +(_stable_sum(products) / Decimal(len(values)))
            )
        long_run = gammas[0]
        for distance in range(1, lag + 1):
            weight = Decimal(lag + 1 - distance) / Decimal(lag + 1)
            long_run = +(long_run + Decimal(2) * weight * gammas[distance])
        if long_run <= 0:
            return tuple(counts), None, None
        standard_error = +(long_run / Decimal(len(values))).sqrt()
        return tuple(counts), standard_error, +(mean / standard_error)


def _v2_fold_axes(
    value: FormalEvaluationInput, folds: tuple[str, ...], horizon: int
) -> dict[str, tuple[int, ...]]:
    return {
        axis.fold_id: tuple(point.session_position for point in axis.sessions)
        for axis in value.fold_axes
        if axis.fold_id in folds and axis.horizon_sessions == horizon
    }


def _v2_economic_axes(
    value: FormalEvaluationInput, folds: tuple[str, ...]
) -> dict[str, tuple[int, ...]]:
    return {
        axis.fold_id: tuple(point.session_position for point in axis.sessions)
        for axis in value.economic_observation_axes
        if axis.fold_id in folds
    }


def _v2_paired_unbiased_start(
    *, modulus: int, replicate: int, fold_ordinal: int, block_ordinal: int,
) -> int:
    if (
        type(replicate) is not int or replicate < 0
        or replicate >= BOOTSTRAP_RESAMPLES
        or type(fold_ordinal) is not int
        or fold_ordinal < 0
        or fold_ordinal >= len(PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES)
        or type(block_ordinal) is not int
        or block_ordinal < 0
        or block_ordinal
        >= PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES[fold_ordinal][4]
        or type(modulus) is not int
        or modulus
        != PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES[fold_ordinal][3]
    ):
        raise FormalEvaluationError(
            "paired bootstrap ordinal or allowed-start count changed"
        )
    ceiling = 1 << 256
    limit = ceiling - ceiling % modulus
    seed = bytes.fromhex(BOOTSTRAP_SEED_SHA256)
    for rejection in range(1 << 32):
        preimage = (
            PAIRED_BOOTSTRAP_SAMPLER_DOMAIN.encode("utf-8") + b"\x00"
            + seed
            + replicate.to_bytes(8, "big")
            + fold_ordinal.to_bytes(8, "big")
            + block_ordinal.to_bytes(8, "big")
            + rejection.to_bytes(8, "big")
        )
        word = int.from_bytes(hashlib.sha256(preimage).digest(), "big")
        if word < limit:
            return word % modulus
    raise FormalEvaluationError("hash-counter rejection overflow")


def _v2_paired_axes_exact(axes: dict[str, tuple[int, ...]]) -> None:
    if tuple(axes) != FORMAL_FOLD_IDS:
        raise FormalEvaluationError("paired bootstrap lacks the six frozen folds")
    for fold_id, count, axis_sha256, allowed, blocks in (
        PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES
    ):
        axis = axes[fold_id]
        if (
            len(axis) != count
            or len(axis) - SLEEVE_HOLDING_SESSIONS + 1 != allowed
            or (len(axis) + SLEEVE_HOLDING_SESSIONS - 1)
            // SLEEVE_HOLDING_SESSIONS != blocks
        ):
            raise FormalEvaluationError(
                "paired bootstrap fold-axis geometry changed"
            )
        _v2_sha(axis_sha256, "paired bootstrap frozen axis hash")


def _v2_paired_centered_bootstrap(
    *, values: tuple[tuple[str, int, Decimal], ...],
    axes: dict[str, tuple[int, ...]], resamples: int,
) -> tuple[Decimal, ...] | None:
    if not values:
        return None
    _v2_paired_axes_exact(axes)
    observed = _mean(tuple(item[2] for item in values))
    with localcontext(_context()):
        centered = {
            (fold, position): +(item - observed)
            for fold, position, item in values
        }
    results: list[Decimal] = []
    ordered_folds = FORMAL_FOLD_IDS
    for replicate in range(resamples):
        sampled: list[Decimal] = []
        for fold_ordinal, fold in enumerate(ordered_folds):
            axis = axes[fold]
            block_length = SLEEVE_HOLDING_SESSIONS
            draws = PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES[fold_ordinal][4]
            selected_positions: list[int] = []
            for block_ordinal in range(draws):
                start = _v2_paired_unbiased_start(
                    modulus=len(axis) - block_length + 1,
                    replicate=replicate, fold_ordinal=fold_ordinal,
                    block_ordinal=block_ordinal,
                )
                selected_positions.extend(axis[start:start + block_length])
            for position in selected_positions[:len(axis)]:
                item = centered.get((fold, position))
                if item is not None:
                    sampled.append(item)
        if not sampled:
            return None
        results.append(_mean(tuple(sampled)))
    return tuple(results)


def _v2_stock_bootstrap_metric_id(
    *, statistic: str, horizon: int | None = None,
    coefficient: str | None = None, cost_bps: int | None = None,
) -> str | None:
    """Return the sole reviewed stock-bootstrap metric identifier, if any."""

    if statistic == "fama_macbeth":
        if (
            type(horizon) is not int or horizon not in HORIZONS
            or coefficient not in {"bullish", "bearish"}
            or cost_bps is not None
        ):
            raise FormalEvaluationError("stock FM bootstrap metric changed")
        if coefficient == "bullish" and horizon == 20:
            return "primary_fm_bullish_h20"
        return f"secondary_fm_{coefficient}_h{horizon}"
    if statistic == "economic_equal_weight":
        if (
            horizon is not None or coefficient is not None
            or type(cost_bps) is not int or cost_bps not in COST_BPS_GRID
        ):
            raise FormalEvaluationError("stock economic bootstrap metric changed")
        if cost_bps == PRIMARY_COST_BPS:
            return "primary_economic_equal_weight_cost10"
        return f"secondary_economic_direct_stock_equal_weight_cost{cost_bps}"
    raise FormalEvaluationError("unknown stock bootstrap statistic")


def _v2_stock_unbiased_start(
    *, modulus: int, source_view_id: str, slice_id: str, metric_id: str,
    replicate: int, fold_ordinal: int, block_ordinal: int,
) -> int:
    """Exact report-contract hash-counter draw with rejection sampling."""

    if (
        type(modulus) is not int or modulus < 1
        or source_view_id not in SOURCE_VIEW_IDS
        or slice_id != FORMAL_SLICE_ID
        or metric_id not in STOCK_BOOTSTRAP_METRIC_IDS
        or type(replicate) is not int or not 0 <= replicate < BOOTSTRAP_RESAMPLES
        or type(fold_ordinal) is not int
        or not 0 <= fold_ordinal < len(FORMAL_FOLD_IDS)
        or type(block_ordinal) is not int or block_ordinal < 0
    ):
        raise FormalEvaluationError("stock bootstrap draw geometry changed")
    seed = bytes.fromhex(STOCK_BOOTSTRAP_SEED_SHA256)

    def encoded_text(value: str) -> bytes:
        raw = value.encode("ascii")
        if len(raw) >= 1 << 16:
            raise FormalEvaluationError("stock bootstrap identifier is too long")
        return len(raw).to_bytes(2, "big") + raw

    prefix = (
        STOCK_BOOTSTRAP_SAMPLER_DOMAIN.encode("ascii") + b"\x00" + seed
        + encoded_text(source_view_id)
        + encoded_text(slice_id)
        + encoded_text(metric_id)
        + replicate.to_bytes(8, "big")
        + fold_ordinal.to_bytes(8, "big")
        + block_ordinal.to_bytes(8, "big")
    )
    ceiling = 1 << 256
    limit = ceiling - ceiling % modulus
    for rejection in range(1 << 32):
        word = int.from_bytes(
            hashlib.sha256(prefix + rejection.to_bytes(8, "big")).digest(),
            "big",
        )
        if word < limit:
            return word % modulus
    raise FormalEvaluationError("stock bootstrap hash-counter rejection overflow")


def _v2_stock_centered_bootstrap(
    *, values: tuple[tuple[str, int, Decimal], ...],
    axes: dict[str, tuple[int, ...]], block_length: int,
    source_view_id: str, slice_id: str, metric_id: str, resamples: int,
) -> tuple[Decimal, ...] | None:
    """Reviewed noncircular complete-block stock FM/economic sampler."""

    if (
        not values or tuple(axes) != FORMAL_FOLD_IDS
        or type(block_length) is not int or block_length < 1
        or type(resamples) is not int or not 1 <= resamples <= BOOTSTRAP_RESAMPLES
    ):
        return None
    observed = _mean(tuple(item[2] for item in values))
    with localcontext(_context()):
        centered = {
            (fold, position): +(item - observed)
            for fold, position, item in values
        }
    if len(centered) != len(values):
        raise FormalEvaluationError("stock bootstrap values duplicate a session")
    eligible: dict[str, tuple[int, ...]] = {}
    counts: dict[str, int] = {}
    for fold in FORMAL_FOLD_IDS:
        axis = axes[fold]
        if type(axis) is not tuple or len(axis) < block_length or any(
            type(position) is not int for position in axis
        ):
            raise FormalEvaluationError("stock bootstrap axis changed")
        counts[fold] = sum((fold, position) in centered for position in axis)
        eligible[fold] = tuple(
            start for start in range(len(axis) - block_length + 1)
            if all(
                (fold, position) in centered
                for position in axis[start:start + block_length]
            )
        )
        if counts[fold] and not eligible[fold]:
            return None
    results: list[Decimal] = []
    for replicate in range(resamples):
        sampled: list[Decimal] = []
        for fold_ordinal, fold in enumerate(FORMAL_FOLD_IDS):
            target_count = counts[fold]
            if target_count == 0:
                continue
            starts = eligible[fold]
            block_count = (target_count + block_length - 1) // block_length
            fold_sample: list[Decimal] = []
            for block_ordinal in range(block_count):
                selected = _v2_stock_unbiased_start(
                    modulus=len(starts), source_view_id=source_view_id,
                    slice_id=slice_id, metric_id=metric_id,
                    replicate=replicate, fold_ordinal=fold_ordinal,
                    block_ordinal=block_ordinal,
                )
                start = starts[selected]
                fold_sample.extend(
                    centered[(fold, position)]
                    for position in axes[fold][start:start + block_length]
                )
            sampled.extend(fold_sample[:target_count])
        if len(sampled) != len(values):
            raise FormalEvaluationError(
                "stock bootstrap replicate changed its observation census"
            )
        results.append(_mean(tuple(sampled)))
    return tuple(results)


def _v2_two_sided_p(
    observed: Decimal, replicates: tuple[Decimal, ...]
) -> Fraction:
    exceed = sum(
        item.copy_abs() >= observed.copy_abs() for item in replicates
    )
    return Fraction(1 + exceed, len(replicates) + 1)


def _v2_type7(
    values: tuple[Decimal, ...], probability: Fraction
) -> Decimal:
    if not values:
        raise FormalEvaluationError("type-7 quantile requires values")
    ordered = sorted(values)
    location = Fraction(len(ordered) - 1) * probability
    lower = location.numerator // location.denominator
    fraction = location - lower
    upper = min(lower + 1, len(ordered) - 1)
    with localcontext(_context()):
        return +(
            ordered[lower] * _decimal(1 - fraction)
            + ordered[upper] * _decimal(fraction)
        )


def _v2_summary_status(
    *, valid_dates: int, required_dates: int, invalid: Counter[str]
) -> Disposition:
    if invalid.get("outcome_identity_invalid", 0):
        return Disposition.INVALID_DATA
    if valid_dates < required_dates:
        return Disposition.INCONCLUSIVE
    return Disposition.PASS


def _v2_ic_summary(
    *, slice_id: str, fold_id: str | None, horizon: int, arm: str,
    valid: tuple[tuple[str, int, Decimal], ...], invalid: Counter[str],
    required_dates: int,
) -> IcSummary:
    status = _v2_summary_status(
        valid_dates=len(valid), required_dates=required_dates, invalid=invalid
    )
    if not valid:
        return IcSummary(
            slice_id, fold_id, horizon, arm, status, 0, sum(invalid.values()),
            tuple(sorted(invalid.items())), None, None, None, None, horizon,
            (), None, None,
        )
    values = tuple(item[2] for item in valid)
    mean = _mean(values)
    with localcontext(_context()):
        variance = +(_stable_sum(tuple(+((item - mean) ** 2) for item in values))
                     / Decimal(len(values)))
        icir = None if variance == 0 else +(mean / variance.sqrt())
    pairs, standard_error, hac_t = _v2_hac(
        tuple((item[1], item[2]) for item in valid), horizon
    )
    return IcSummary(
        slice_id, fold_id, horizon, arm, status, len(valid),
        sum(invalid.values()), tuple(sorted(invalid.items())), mean,
        _median(values), Fraction(sum(item > 0 for item in values), len(values)),
        icir, horizon, pairs, standard_error, hac_t,
    )


def _v2_fm_summaries(
    *, value: FormalEvaluationInput, slice_id: str, fold_id: str | None,
    folds: tuple[str, ...], horizon: int, arm: str,
    valid: tuple[tuple[str, int, Decimal, Decimal], ...],
    invalid: Counter[str], parameter_counts: tuple[tuple[str, int], ...],
    required_dates: int, resamples: int,
) -> tuple[FamaMacBethSummary, FamaMacBethSummary]:
    base_status = _v2_summary_status(
        valid_dates=len(valid), required_dates=required_dates, invalid=invalid
    )
    result: list[FamaMacBethSummary] = []
    for coefficient, item_index in (("bullish", 2), ("bearish", 3)):
        status = base_status
        dated = tuple((item[1], item[item_index]) for item in valid)
        values = tuple(item[1] for item in dated)
        pairs, standard_error, hac_t = _v2_hac(dated, horizon)
        bootstrap_count: int | None = None
        p_value: Fraction | None = None
        is_registered_bootstrap = (
            slice_id == FORMAL_SLICE_ID and fold_id is None
            and arm == "firm_specific"
        )
        if is_registered_bootstrap and values:
            metric_id = _v2_stock_bootstrap_metric_id(
                statistic="fama_macbeth", horizon=horizon,
                coefficient=coefficient,
            )
            replicates = _v2_stock_centered_bootstrap(
                values=tuple(
                    (item[0], item[1], item[item_index])
                    for item in valid
                ),
                axes=_v2_fold_axes(value, folds, horizon),
                block_length=horizon,
                source_view_id=value.source_view_id,
                slice_id=slice_id,
                metric_id=metric_id,
                resamples=resamples,
            )
            if replicates is None:
                status = (
                    Disposition.INVALID_DATA
                    if status is Disposition.INVALID_DATA
                    else Disposition.INCONCLUSIVE
                )
            else:
                bootstrap_count = resamples
                p_value = _v2_two_sided_p(_mean(values), replicates)
        if status is not Disposition.PASS:
            # A numerical draw from an inadmissible/refused summary is not a
            # registered hypothesis p-value.  Keep the underlying invalid
            # census, but never let multiplicity code promote that number.
            p_value = None
        result.append(FamaMacBethSummary(
            slice_id, fold_id, horizon, arm, coefficient, status, len(valid),
            sum(invalid.values()), tuple(sorted(invalid.items())),
            parameter_counts, None if not values else _mean(values),
            None if not values else _median(values), horizon, pairs,
            standard_error, hac_t, bootstrap_count, p_value,
        ))
    return result[0], result[1]


def _v2_paired_summary(
    *, value: FormalEvaluationInput, slice_id: str, fold_id: str | None,
    folds: tuple[str, ...], horizon: int,
    valid: tuple[tuple[str, int, Decimal, Decimal], ...],
    invalid: Counter[str], required_dates: int, resamples: int,
) -> PairedIcSummary:
    status = _v2_summary_status(
        valid_dates=len(valid), required_dates=required_dates, invalid=invalid
    )
    if not valid:
        return PairedIcSummary(
            slice_id, fold_id, horizon, status, 0, sum(invalid.values()),
            tuple(sorted(invalid.items())), None, None, None, None, None, None,
        )
    firm = tuple(item[2] for item in valid)
    global_values = tuple(item[3] for item in valid)
    with localcontext(_context()):
        differences = tuple(+(left - right) for left, right in zip(
            firm, global_values, strict=True
        ))
    observed = _mean(differences)
    bootstrap_count: int | None = None
    q95: Decimal | None = None
    lcb: Decimal | None = None
    if (
        slice_id == FORMAL_SLICE_ID
        and fold_id is None
        and folds == FORMAL_FOLD_IDS
        and horizon == 20
    ):
        bootstrap_count = resamples
        with localcontext(_context()):
            paired_values = tuple(
                (item[0], item[1], +(item[2] - item[3])) for item in valid
            )
        replicates = _v2_paired_centered_bootstrap(
            values=paired_values,
            axes=_v2_fold_axes(value, folds, 20), resamples=resamples,
        )
        if replicates is None:
            status = Disposition.INCONCLUSIVE
        else:
            q95 = _v2_type7(replicates, PAIRED_LCB_PROBABILITY)
            with localcontext(_context()):
                lcb = +(observed - q95)
    return PairedIcSummary(
        slice_id, fold_id, horizon, status, len(valid), sum(invalid.values()),
        tuple(sorted(invalid.items())), _mean(firm), _mean(global_values),
        observed, bootstrap_count, q95, lcb,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _ActiveSleeve:
    remaining_intervals: int
    original_name_count: int
    active_security_ids: tuple[str, ...]


def _v2_new_sleeve(selected: tuple[str, ...]) -> _ActiveSleeve:
    return _ActiveSleeve(
        SLEEVE_HOLDING_SESSIONS, len(selected), tuple(sorted(selected))
    )


def _v2_targets(sleeves: Sequence[_ActiveSleeve]) -> dict[str, Decimal]:
    target: dict[str, Decimal] = {}
    with localcontext(_context()):
        for sleeve in sleeves:
            if sleeve.original_name_count == 0:
                if sleeve.active_security_ids:
                    raise FormalEvaluationError(
                        "cash sleeve acquired active security IDs"
                    )
                continue
            if (
                sleeve.original_name_count < len(sleeve.active_security_ids)
                or tuple(sorted(set(sleeve.active_security_ids)))
                != sleeve.active_security_ids
            ):
                raise FormalEvaluationError(
                    "active sleeve changed its original denominator"
                )
            per_name = +(Decimal(1) / Decimal(SLEEVE_HOLDING_SESSIONS)
                         / Decimal(sleeve.original_name_count))
            for security_id in sleeve.active_security_ids:
                target[security_id] = +(target.get(security_id, Decimal(0)) + per_name)
    return target


def _v2_advance_sleeves(
    sleeves: Sequence[_ActiveSleeve],
    terminal_security_ids: frozenset[str],
) -> list[_ActiveSleeve]:
    result: list[_ActiveSleeve] = []
    for sleeve in sleeves:
        if sleeve.remaining_intervals <= 1:
            continue
        result.append(_ActiveSleeve(
            remaining_intervals=sleeve.remaining_intervals - 1,
            original_name_count=sleeve.original_name_count,
            active_security_ids=tuple(
                item
                for item in sleeve.active_security_ids
                if item not in terminal_security_ids
            ),
        ))
    return result


def _v2_selected_sleeve(
    decisions: Sequence[EconomicDecision],
) -> tuple[str, ...]:
    """Freeze the deterministic positive-score top-quintile selection."""

    positive = tuple(
        row for row in sorted(
            decisions,
            # Decimal.__neg__ obeys the ambient arithmetic context. Ranking
            # is exact, so preserve every coefficient digit in the sort key.
            key=lambda row: (
                row.firm_specific_score.copy_negate(), row.security_id
            ),
        ) if row.firm_specific_score > 0
    )
    quintile_count = (len(positive) + 4) // 5
    if quintile_count < MINIMUM_SLEEVE_SIZE:
        return ()
    return tuple(row.security_id for row in positive[:quintile_count])


def _v2_economic_cost_summary(
    *, value: FormalEvaluationInput, slice_id: str, folds: tuple[str, ...],
    cost_bps: int, required_dates: int, resamples: int,
) -> EconomicCostSummary:
    sessions = tuple(
        item for item in value.economic_sessions if item.fold_id in folds
    )
    by_fold = {
        fold: tuple(item for item in sessions if item.fold_id == fold)
        for fold in folds
    }
    axes = _v2_economic_axes(value, folds)
    decision_axes = _v2_fold_axes(value, folds, 20)
    reasons: list[str] = []
    for fold in folds:
        observed_positions = tuple(item.session_position for item in by_fold[fold])
        if observed_positions != axes[fold]:
            reasons.append(f"{fold}:economic_axis_incomplete")
    daily: list[EconomicTrialObservation] = []
    daily_turnover: list[Decimal] = []
    invested_count = 0
    cash_sleeves = 0
    selected_sleeves = 0
    terminal_liquidation = Decimal(0)
    refused_session_count = 0
    refusal_counts: Counter[str] = Counter()
    for fold in folds:
        active: list[_ActiveSleeve] = []
        # These are the actual close-to-close holdings carried into the next
        # rebalance, not yesterday's target weights.  A target-only comparison
        # silently treats return-induced drift as zero turnover and understates
        # both costs and the final liquidation.
        pretrade_weights: dict[str, Decimal] = {}
        fold_daily: list[EconomicTrialObservation] = []
        fold_turnover: list[Decimal] = []
        fold_state_valid = True
        fold_refused_session_count = 0
        for session in by_fold[fold]:
            decision_eligible = session.session_position in decision_axes[fold]
            terminal_liquidation_session = (
                session.session_position == axes[fold][-1]
            )
            if not decision_eligible and session.decisions:
                raise FormalEvaluationError(
                    "economic runoff observation created a new sleeve"
                )
            selected = (
                _v2_selected_sleeve(session.decisions)
                if decision_eligible else ()
            )
            if decision_eligible:
                if not selected:
                    cash_sleeves += 1
                else:
                    selected_sleeves += 1
            if decision_eligible:
                active.append(_v2_new_sleeve(selected))
            target = _v2_targets(active)
            sleeve_incidence_count = sum(
                len(sleeve.active_security_ids) for sleeve in active
            )
            duplicate_sleeve_incidence_count = (
                sleeve_incidence_count - len(target)
            )
            row_map = {row.security_id: row for row in session.security_outcomes}
            benchmark_refusals: set[str] = set()
            if session.benchmark_refusal_reason is not None:
                benchmark_refusals.add(session.benchmark_refusal_reason.value)
            security_refusals = {
                row.reason.value
                for row in session.security_outcomes
                if row.disposition is EconomicOutcomeDisposition.NAMED_REFUSAL
                and row.reason is not None
            }
            session_refusals = benchmark_refusals | security_refusals
            terminal_security_ids = frozenset(
                row.security_id
                for row in session.security_outcomes
                if row.terminal_payoff_applied
            )
            if session_refusals:
                fold_refused_session_count += 1
                refusal_counts.update(session_refusals)
            if target:
                invested_count += 1
            # Once any held-name return is unknown, the wealth and holding
            # weights carried into every later rebalance in this independent
            # fold are unknowable.  Do not restart from the next target or mix
            # the pre-gap prefix with another fold; the complete fold is kept
            # out of point estimates and resampling below.
            if fold_state_valid and security_refusals:
                fold_state_valid = False
            if fold_state_valid:
                securities = set(pretrade_weights) | set(target)
                with localcontext(_context()):
                    turnover = _stable_sum(tuple(
                        +(
                            target.get(name, Decimal(0))
                            - pretrade_weights.get(name, Decimal(0))
                        ).copy_abs()
                        for name in securities
                    ))
                    gross = _stable_sum(tuple(
                        +(weight * row_map[name].gross_total_return)
                        for name, weight in target.items()
                    ))
                    cost = +(turnover * Decimal(cost_bps) / Decimal(10_000))
                    net_portfolio_return = +(gross - cost)
                    ending_wealth = +(Decimal(1) + net_portfolio_return)
                if ending_wealth <= 0:
                    fold_state_valid = False
                    refusal_counts.update(("nonpositive_post_cost_wealth",))
                    fold_refused_session_count += int(not session_refusals)
                else:
                    fold_turnover.append(turnover)
                    if terminal_liquidation_session:
                        terminal_liquidation = +(
                            terminal_liquidation + turnover
                        )
                    with localcontext(_context()):
                        pretrade_weights = {
                            name: +(
                                weight
                                * (Decimal(1) + row_map[name].gross_total_return)
                                / ending_wealth
                            )
                            for name, weight in target.items()
                            if weight != 0 and name not in terminal_security_ids
                        }
                    if not benchmark_refusals:
                        with localcontext(_context()):
                            excess = +(
                                net_portfolio_return
                                - session.benchmark_total_return
                            )
                        fold_daily.append(EconomicTrialObservation(
                            fold_id=fold,
                            session=session.session,
                            session_position=session.session_position,
                            cost_bps_per_side=cost_bps,
                            gross_portfolio_total_return=gross,
                            benchmark_total_return=session.benchmark_total_return,
                            net_portfolio_total_return=net_portfolio_return,
                            net_excess_daily_total_return=excess,
                            turnover=turnover,
                            sleeve_security_incidence_count=(
                                sleeve_incidence_count
                            ),
                            duplicate_sleeve_security_incidence_count=(
                                duplicate_sleeve_incidence_count
                            ),
                            terminal_liquidation=terminal_liquidation_session,
                        ))
            if terminal_liquidation_session:
                if active:
                    raise FormalEvaluationError(
                        "terminal liquidation arrived before every sleeve expired"
                    )
            else:
                active = _v2_advance_sleeves(
                    active, terminal_security_ids
                )
        if fold_state_valid:
            if pretrade_weights:
                raise FormalEvaluationError(
                    "economic fold sealed before explicit terminal liquidation"
                )
            daily.extend(fold_daily)
            daily_turnover.extend(fold_turnover)
            refused_session_count += fold_refused_session_count
        else:
            # The return path is stateful within a fold: after one held-name
            # return is unavailable, neither the already-computed prefix nor
            # any later rebalance has an admissible wealth/weight state.  The
            # whole fold is therefore excluded.  Charge every otherwise
            # unaccounted session to that named exclusion so the result census
            # remains exhaustive instead of self-rejecting at validation.
            # ``fold_daily`` omits benchmark-refusal sessions, while this
            # fold-local counter already includes those sessions and the
            # session that first lost holding state.  The residual is exactly
            # the otherwise-computable prefix/suffix discarded with the fold.
            unaccounted = len(by_fold[fold]) - fold_refused_session_count
            if unaccounted < 0:
                raise FormalEvaluationError(
                    "economic fold refusal census exceeded its session axis"
                )
            refusal_counts[ECONOMIC_FOLD_STATE_LOSS_EXCLUSION] += unaccounted
            fold_refused_session_count += unaccounted
            refused_session_count += fold_refused_session_count
            reasons.append(
                f"{fold}:{ECONOMIC_FOLD_STATE_LOSS_EXCLUSION}"
            )
    reasons.extend(
        f"{reason}:{count}" for reason, count in sorted(refusal_counts.items())
    )
    status = (
        Disposition.INVALID_DATA
        if refusal_counts.get(RefusalReason.OUTCOME_IDENTITY_INVALID.value, 0)
        else (
            Disposition.INCONCLUSIVE
            if refused_session_count > 0
            else Disposition.PASS
        )
    )
    if status is not Disposition.INVALID_DATA and len(daily) < required_dates:
        status = Disposition.INCONCLUSIVE
        reasons.append("valid_return_session_floor_not_met")
    # Named gaps are never compressed into zeros. Point estimates and resampling
    # use only valid observations at their original global session positions.
    values = tuple(item.net_excess_daily_total_return for item in daily)
    mean = None if not values else _mean(values)
    cumulative: Decimal | None = None
    if values and refused_session_count == 0:
        with localcontext(_context()):
            accumulator = Decimal(1)
            for item in daily:
                accumulator = +(
                    accumulator
                    * (Decimal(1) + item.net_portfolio_total_return)
                )
            cumulative = +(accumulator - Decimal(1))
    bootstrap_count: int | None = None
    p_value: Fraction | None = None
    if slice_id == FORMAL_SLICE_ID and folds == FORMAL_FOLD_IDS and values:
        metric_id = _v2_stock_bootstrap_metric_id(
            statistic="economic_equal_weight", cost_bps=cost_bps,
        )
        replicates = _v2_stock_centered_bootstrap(
            values=tuple(
                (
                    item.fold_id, item.session_position,
                    item.net_excess_daily_total_return,
                )
                for item in daily
            ), axes=axes,
            block_length=SLEEVE_HOLDING_SESSIONS,
            source_view_id=value.source_view_id, slice_id=slice_id,
            metric_id=metric_id, resamples=resamples,
        )
        if replicates is None:
            status = (
                Disposition.INVALID_DATA
                if status is Disposition.INVALID_DATA
                else Disposition.INCONCLUSIVE
            )
            reasons.append("economic_bootstrap_has_no_complete_block_domain")
        else:
            bootstrap_count = resamples
            p_value = _v2_two_sided_p(mean, replicates)
    if status is not Disposition.PASS:
        p_value = None
    return EconomicCostSummary(
        slice_id, cost_bps, status, len(sessions), len(daily),
        refused_session_count, invested_count, cash_sleeves, selected_sleeves,
        mean, cumulative,
        None if not daily_turnover else _mean(tuple(daily_turnover)),
        terminal_liquidation, bootstrap_count, p_value, tuple(reasons),
    )


# The materialized evaluator above remains the byte-for-byte reference.  The
# stream boundary below computes the same per-date sufficient statistics while
# retaining only one cross-section, 20 live sleeves, and the dated aggregate
# series needed by HAC/bootstrap.  Mutable state lives only in the private
# registry; the public handle is opaque and cannot be copied or caller-edited
# into a second authority.
STREAM_SCHEMA = "arv2-formal-evaluation-session-stream-v1"


@dataclasses.dataclass(frozen=True, slots=True)
class FormalEvaluationSessionBlock:
    block_id: str
    block_sha256: str
    fold_id: str
    decision_session: date
    session_position: int
    rows: tuple[EvaluationRow, ...]
    refusals: tuple[EvaluationRefusal, ...]
    economic_session: EconomicSession | None


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalEvaluationStream:
    stream_id: str
    schema: str
    source_view_id: str
    input_id: str
    input_sha256: str
    fold_axes: tuple[FoldSessionAxis, ...]
    economic_observation_axes: tuple[EconomicObservationAxis, ...]
    economic_execution_definition_sha256: str
    power_floor: PowerFloorBinding


@dataclasses.dataclass(frozen=True, slots=True)
class FormalEvaluationStreamingResult:
    report: FormalEvaluationReportV2
    accepted_row_count: int
    refused_row_count: int
    economic_session_count: int
    fold_horizon_census: tuple[tuple[str, int, int, int], ...]
    economic_trial_observations: tuple[EconomicTrialObservation, ...]
    economic_trial_fold_census: tuple[EconomicTrialFoldCensus, ...]
    daily_information_coefficient_observations: tuple[
        DailyInformationCoefficientObservation, ...
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamDateStat:
    fold_id: str
    decision_session: date
    session_position: int
    horizon_sessions: int
    accepted_rows: int
    refused_rows: int
    refusals_by_reason: tuple[tuple[str, int], ...]
    accepted_component_count: int
    firm_ic: Decimal | None
    firm_ic_invalid: str | None
    global_ic: Decimal | None
    global_ic_invalid: str | None
    paired_firm_ic: Decimal | None
    paired_global_ic: Decimal | None
    paired_invalid: str | None
    firm_fm_bullish: Decimal | None
    firm_fm_bearish: Decimal | None
    firm_fm_parameter_count: int | None
    firm_fm_invalid: str | None
    global_fm_bullish: Decimal | None
    global_fm_bearish: Decimal | None
    global_fm_parameter_count: int | None
    global_fm_invalid: str | None
    paired_candidate: bool
    paired_capable: bool


@dataclasses.dataclass(slots=True)
class _StreamCostState:
    cost_bps: int
    pretrade_weights: dict[str, Decimal]
    fold_daily: list[EconomicTrialObservation]
    fold_turnover: list[Decimal]
    refusal_counts_by_session: list[
        tuple[date, tuple[tuple[str, int], ...]]
    ] = dataclasses.field(default_factory=list)
    fold_state_valid: bool = True
    session_count: int = 0
    refused_session_count: int = 0
    invested_count: int = 0
    cash_sleeves: int = 0
    selected_sleeves: int = 0
    terminal_liquidation: Decimal = Decimal(0)
    refusal_counts: Counter[str] = dataclasses.field(default_factory=Counter)


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamEconomicFold:
    fold_id: str
    cost_bps: int
    session_count: int
    daily: tuple[EconomicTrialObservation, ...]
    daily_turnover: tuple[Decimal, ...]
    refused_session_count: int
    invested_count: int
    cash_sleeves: int
    selected_sleeves: int
    terminal_liquidation: Decimal
    refusal_counts: tuple[tuple[str, int], ...]
    refusal_counts_by_session: tuple[
        tuple[date, tuple[tuple[str, int], ...]], ...
    ]
    reasons: tuple[str, ...]


@dataclasses.dataclass(slots=True)
class _StreamState:
    creator_pid: int
    owner_thread_id: int
    epoch: int
    next_block_index: int
    expected_blocks: tuple[tuple[str, date, int], ...]
    horizon_block_keys: frozenset[tuple[str, date, int, int]]
    economic_block_keys: frozenset[tuple[str, date, int]]
    economic_decision_keys: frozenset[tuple[str, date, int]]
    economic_terminal_keys: frozenset[tuple[str, date, int]]
    date_stats: list[_StreamDateStat]
    active_sleeves: dict[str, list[_ActiveSleeve]]
    costs: dict[tuple[str, int], _StreamCostState]
    economic_folds: dict[tuple[str, int], _StreamEconomicFold]
    accepted_row_count: int
    refused_row_count: int
    finished: bool
    failed: bool


_STREAM_STATE_DATACLASS_TYPES = (
    _ActiveSleeve,
    _StreamDateStat,
    _StreamCostState,
    _StreamEconomicFold,
    EconomicTrialObservation,
)


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamHistoryCommitment:
    label: str
    container_identity: int
    item_identities: tuple[int, ...]
    chain_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamStateAuthority:
    creator_pid: int
    owner_thread_id: int
    epoch: int
    fast_sha256: str
    histories: tuple[_StreamHistoryCommitment, ...]


def _stream_state_canonical(value: object) -> object:
    """Canonicalize the private mutable accumulator with exact topology.

    The state lives behind the opaque stream handle, but Python callers can
    still obtain the private registry during tests or through introspection.
    Persisting this topology-and-content commitment prevents a caller from
    editing counters, accumulated statistics, sleeve state, or economic
    observations and then asking ``finish`` to authenticate the mutation.
    """

    if type(value) in {str, int, bool} or value is None:
        return value
    if type(value) is date:
        return {"date": value.isoformat()}
    if type(value) is Decimal:
        _v2_finite_decimal(value, "stream-state Decimal")
        return {"decimal": str(value)}
    if type(value) in {tuple, list}:
        return {
            "container": type(value).__name__,
            "identity": id(value),
            "items": [_stream_state_canonical(item) for item in value],
        }
    if type(value) is frozenset:
        items = [_stream_state_canonical(item) for item in value]
        items.sort(
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            )
        )
        return {
            "container": "frozenset",
            "identity": id(value),
            "items": items,
        }
    if type(value) in {dict, Counter}:
        items = [
            [_stream_state_canonical(key), _stream_state_canonical(item)]
            for key, item in value.items()
        ]
        items.sort(
            key=lambda item: json.dumps(
                item[0], sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            )
        )
        return {
            "container": type(value).__name__,
            "identity": id(value),
            "items": items,
        }
    if type(value) in _STREAM_STATE_DATACLASS_TYPES or type(value) is _StreamState:
        return {
            "dataclass": type(value).__name__,
            "identity": id(value),
            "fields": {
                field.name: _stream_state_canonical(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    raise FormalEvaluationError("formal evaluation stream state changed type")


def _stream_state_payload_sha256(value: object) -> str:
    """Hash one bounded state record without ambient Decimal rounding."""

    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, FormalEvaluationError):
            raise
        raise FormalEvaluationError(
            "formal evaluation stream state is not canonical"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _stream_state_fast_sha256(state: _StreamState) -> str:
    """Commit the live frontier while histories use append-only hash chains."""

    if type(state) is not _StreamState:
        raise FormalEvaluationError("formal evaluation stream state changed type")
    costs = [
        {
            "key": list(key),
            "cost_state_identity": id(current),
            "cost_bps": current.cost_bps,
            "pretrade_weights": _stream_state_canonical(
                current.pretrade_weights
            ),
            "fold_state_valid": current.fold_state_valid,
            "session_count": current.session_count,
            "refused_session_count": current.refused_session_count,
            "invested_count": current.invested_count,
            "cash_sleeves": current.cash_sleeves,
            "selected_sleeves": current.selected_sleeves,
            "terminal_liquidation": _stream_state_canonical(
                current.terminal_liquidation
            ),
            "refusal_counts": _stream_state_canonical(
                current.refusal_counts
            ),
            "fold_daily": [id(current.fold_daily), len(current.fold_daily)],
            "fold_turnover": [
                id(current.fold_turnover), len(current.fold_turnover)
            ],
            "refusal_counts_by_session": [
                id(current.refusal_counts_by_session),
                len(current.refusal_counts_by_session),
            ],
        }
        for key, current in sorted(state.costs.items())
    ]
    return _stream_state_payload_sha256({
        "domain": "arv2-formal-evaluation-stream-state-frontier-v1",
        "creator_pid": state.creator_pid,
        "owner_thread_id": state.owner_thread_id,
        "epoch": state.epoch,
        "next_block_index": state.next_block_index,
        "expected_blocks": [id(state.expected_blocks), len(state.expected_blocks)],
        "horizon_block_keys": [
            id(state.horizon_block_keys), len(state.horizon_block_keys)
        ],
        "economic_block_keys": [
            id(state.economic_block_keys), len(state.economic_block_keys)
        ],
        "economic_decision_keys": [
            id(state.economic_decision_keys), len(state.economic_decision_keys)
        ],
        "economic_terminal_keys": [
            id(state.economic_terminal_keys), len(state.economic_terminal_keys)
        ],
        "date_stats": [id(state.date_stats), len(state.date_stats)],
        "active_sleeves": _stream_state_canonical(state.active_sleeves),
        "costs_container": id(state.costs),
        "costs": costs,
        "economic_folds": [
            id(state.economic_folds),
            [list(key) for key in sorted(state.economic_folds)],
        ],
        "accepted_row_count": state.accepted_row_count,
        "refused_row_count": state.refused_row_count,
        "finished": state.finished,
        "failed": state.failed,
    })


def _stream_history_sequences(
    state: _StreamState,
) -> tuple[tuple[str, int, tuple[object, ...]], ...]:
    result: list[tuple[str, int, tuple[object, ...]]] = [
        ("date_stats", id(state.date_stats), tuple(state.date_stats)),
    ]
    for (fold, cost), current in sorted(state.costs.items()):
        prefix = f"cost:{fold}:{cost}"
        result.extend((
            (f"{prefix}:daily", id(current.fold_daily), tuple(current.fold_daily)),
            (
                f"{prefix}:turnover", id(current.fold_turnover),
                tuple(current.fold_turnover),
            ),
            (
                f"{prefix}:refusals", id(current.refusal_counts_by_session),
                tuple(current.refusal_counts_by_session),
            ),
        ))
    result.append((
        "economic_folds",
        id(state.economic_folds),
        tuple(state.economic_folds[key] for key in sorted(state.economic_folds)),
    ))
    return tuple(result)


def _stream_history_initial_digest(label: str) -> str:
    return hashlib.sha256(
        f"arv2-formal-evaluation-history-v1:{label}\n".encode("ascii")
    ).hexdigest()


def _stream_history_extend(
    *, label: str, prior_sha256: str, start_index: int,
    items: tuple[object, ...],
) -> str:
    digest = prior_sha256
    for offset, item in enumerate(items, start=start_index):
        record = {
            "index": offset,
            "item": _stream_state_canonical(item),
            "prior_sha256": digest,
        }
        digest = _stream_state_payload_sha256(record)
    return digest


def _build_stream_state_authority(
    state: _StreamState,
    *, prior: _StreamStateAuthority | None = None,
) -> _StreamStateAuthority:
    if (
        type(state.creator_pid) is not int
        or state.creator_pid <= 0
        or type(state.owner_thread_id) is not int
        or state.owner_thread_id <= 0
        or type(state.epoch) is not int
        or state.epoch < 0
    ):
        raise FormalEvaluationError(
            "formal evaluation stream process lease changed"
        )
    if prior is None:
        if state.epoch != 0:
            raise FormalEvaluationError(
                "formal evaluation stream initial epoch changed"
            )
    elif (
        state.creator_pid != prior.creator_pid
        or state.owner_thread_id != prior.owner_thread_id
        or state.epoch != prior.epoch + 1
    ):
        raise FormalEvaluationError(
            "formal evaluation stream epoch is not an exact successor"
        )
    sequences = _stream_history_sequences(state)
    prior_by_label = (
        {} if prior is None else {item.label: item for item in prior.histories}
    )
    if prior is not None and tuple(prior_by_label) != tuple(
        label for label, _identity, _items in sequences
    ):
        raise FormalEvaluationError("formal evaluation history topology changed")
    histories: list[_StreamHistoryCommitment] = []
    for label, container_identity, items in sequences:
        identities = tuple(id(item) for item in items)
        previous = prior_by_label.get(label)
        if previous is None:
            prior_digest = _stream_history_initial_digest(label)
            start = 0
        else:
            if (
                len(identities) < len(previous.item_identities)
                or identities[:len(previous.item_identities)]
                != previous.item_identities
            ):
                raise FormalEvaluationError(
                    "formal evaluation append-only history changed"
                )
            prior_digest = previous.chain_sha256
            start = len(previous.item_identities)
        histories.append(_StreamHistoryCommitment(
            label=label,
            container_identity=container_identity,
            item_identities=identities,
            chain_sha256=_stream_history_extend(
                label=label, prior_sha256=prior_digest,
                start_index=start, items=items[start:],
            ),
        ))
    return _StreamStateAuthority(
        creator_pid=state.creator_pid,
        owner_thread_id=state.owner_thread_id,
        epoch=state.epoch,
        fast_sha256=_stream_state_fast_sha256(state),
        histories=tuple(histories),
    )


def _require_stream_state_authority(
    state: _StreamState, authority: _StreamStateAuthority, *, deep: bool,
) -> None:
    if (
        type(authority) is not _StreamStateAuthority
        or authority.creator_pid != state.creator_pid
        or authority.owner_thread_id != state.owner_thread_id
        or authority.epoch != state.epoch
        or authority.fast_sha256 != _stream_state_fast_sha256(state)
    ):
        raise FormalEvaluationError("formal evaluation stream mutable state changed")
    sequences = _stream_history_sequences(state)
    if len(sequences) != len(authority.histories):
        raise FormalEvaluationError("formal evaluation stream history changed")
    for sequence, commitment in zip(
        sequences, authority.histories, strict=True
    ):
        label, container_identity, items = sequence
        if (
            type(commitment) is not _StreamHistoryCommitment
            or commitment.label != label
            or commitment.container_identity != container_identity
            or commitment.item_identities != tuple(id(item) for item in items)
        ):
            raise FormalEvaluationError(
                "formal evaluation append-only history changed"
            )
        if deep:
            digest = _stream_history_extend(
                label=label,
                prior_sha256=_stream_history_initial_digest(label),
                start_index=0,
                items=items,
            )
            if digest != commitment.chain_sha256:
                raise FormalEvaluationError(
                    "formal evaluation append-only history content changed"
                )


_STREAMS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalEvaluationStream],
        bytes,
        tuple[object, ...],
        _StreamState,
        _StreamStateAuthority,
    ],
] = {}
_LOCKED_STREAMS: dict[
    int, weakref.ReferenceType[FormalEvaluationStream]
] = {}
_STREAMS_LOCK = threading.RLock()


def _reset_stream_authorities_after_fork() -> None:
    global _STREAMS, _LOCKED_STREAMS, _STREAMS_LOCK
    _STREAMS = {}
    _LOCKED_STREAMS = {}
    _STREAMS_LOCK = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_stream_authorities_after_fork)


def _stream_block_bytes(
    *, fold_id: str, decision_session: date, session_position: int,
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
    economic_session: EconomicSession | None,
) -> bytes:
    return _v2_bytes((
        STREAM_SCHEMA, fold_id, decision_session, session_position,
        rows, refusals, economic_session,
    ))


def build_formal_evaluation_session_block(
    *, fold_id: str, decision_session: date, session_position: int,
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
    economic_session: EconomicSession | None,
) -> FormalEvaluationSessionBlock:
    payload = _stream_block_bytes(
        fold_id=fold_id, decision_session=decision_session,
        session_position=session_position, rows=rows, refusals=refusals,
        economic_session=economic_session,
    )
    digest = hashlib.sha256(payload).hexdigest()
    value = FormalEvaluationSessionBlock(
        _v2_identity("arv2-formal-session-block-", digest), digest,
        fold_id, decision_session, session_position, rows, refusals,
        economic_session,
    )
    return _require_formal_evaluation_session_block(value)


def _require_formal_evaluation_session_block(
    value: FormalEvaluationSessionBlock,
) -> FormalEvaluationSessionBlock:
    if type(value) is not FormalEvaluationSessionBlock:
        raise FormalEvaluationError("formal session block changed type")
    if (
        type(value.fold_id) is not str
        or value.fold_id not in FORMAL_FOLD_IDS
        or type(value.decision_session) is not date
    ):
        raise FormalEvaluationError("formal session block geometry changed")
    _v2_int(value.session_position, "formal session block position")
    if type(value.rows) is not tuple or type(value.refusals) is not tuple:
        raise FormalEvaluationError("formal session block containers changed")
    row_order: list[tuple[str, int]] = []
    refusal_order: list[tuple[str, int]] = []
    invariants: dict[str, tuple[object, ...]] = {}
    accepted_h20: dict[str, EvaluationRow] = {}
    accepted_keys: set[tuple[str, int]] = set()
    refused_keys: set[tuple[str, int]] = set()
    for row in value.rows:
        _require_evaluation_row(row)
        if (
            row.fold_id != value.fold_id
            or row.decision_session != value.decision_session
            or row.session_position != value.session_position
        ):
            raise FormalEvaluationError("evaluation row escaped its session block")
        key = (row.security_id, row.horizon_sessions)
        if key in accepted_keys:
            raise FormalEvaluationError("session block duplicates an accepted row")
        accepted_keys.add(key)
        row_order.append(key)
        invariant = (
            row.source_lineage_sha256, row.industry_id,
            row.common_event_component_id, row.firm_specific_score,
            row.global_score, row.structural_zero, row.continuous_controls,
            row.binary_controls, row.active_event_indicator,
            row.absolute_contribution_weighted_publication_to_entry_jump,
        )
        if invariants.setdefault(row.security_id, invariant) != invariant:
            raise FormalEvaluationError("session-block horizons disagree")
        if row.horizon_sessions == SLEEVE_HOLDING_SESSIONS:
            accepted_h20[row.security_id] = row
    for refusal in value.refusals:
        _require_refusal(refusal)
        if (
            refusal.fold_id != value.fold_id
            or refusal.decision_session != value.decision_session
            or refusal.session_position != value.session_position
        ):
            raise FormalEvaluationError("evaluation refusal escaped its session block")
        key = (refusal.security_id, refusal.horizon_sessions)
        if key in accepted_keys or key in refused_keys:
            raise FormalEvaluationError("session block duplicates a terminal row")
        refused_keys.add(key)
        refusal_order.append(key)
    if row_order != sorted(row_order) or refusal_order != sorted(refusal_order):
        raise FormalEvaluationError("session block rows are not canonical")
    economic = value.economic_session
    if economic is None:
        if accepted_h20 or any(
            item.horizon_sessions == SLEEVE_HOLDING_SESSIONS
            for item in value.refusals
        ):
            raise FormalEvaluationError(
                "H20 rows cannot appear without their economic session"
            )
    else:
        _require_economic_session(economic)
        if (
            economic.fold_id != value.fold_id
            or economic.session != value.decision_session
            or economic.session_position != value.session_position
        ):
            raise FormalEvaluationError("economic session escaped its session block")
        if tuple(item.security_id for item in economic.decisions) != tuple(
            sorted(accepted_h20)
        ):
            raise FormalEvaluationError(
                "economic decision census differs from the session H20 census"
            )
        for item in economic.decisions:
            source = accepted_h20[item.security_id]
            if (
                item.decision_lineage_sha256 != source.source_lineage_sha256
                or item.firm_specific_score != source.firm_specific_score
            ):
                raise FormalEvaluationError("economic decision changed H20 lineage")
    payload = _stream_block_bytes(
        fold_id=value.fold_id, decision_session=value.decision_session,
        session_position=value.session_position, rows=value.rows,
        refusals=value.refusals, economic_session=value.economic_session,
    )
    digest = hashlib.sha256(payload).hexdigest()
    if (
        value.block_sha256 != digest
        or value.block_id != _v2_identity("arv2-formal-session-block-", digest)
    ):
        raise FormalEvaluationError("formal session block identity changed")
    return value


def _stream_static_bytes(value: FormalEvaluationStream) -> bytes:
    return _v2_bytes((
        STREAM_SCHEMA, value.source_view_id, value.input_id,
        value.input_sha256, value.fold_axes, value.economic_observation_axes,
        value.economic_execution_definition_sha256, value.power_floor,
    ))


def _stream_topology(value: FormalEvaluationStream) -> tuple[object, ...]:
    return (
        id(value.fold_axes), tuple(id(item) for item in value.fold_axes),
        tuple(id(point) for axis in value.fold_axes for point in axis.sessions),
        id(value.economic_observation_axes),
        tuple(id(item) for item in value.economic_observation_axes),
        tuple(
            id(point)
            for axis in value.economic_observation_axes
            for point in axis.sessions
        ),
        id(value.power_floor),
    )


def _forget_stream(
    identity: int, reference: weakref.ReferenceType[FormalEvaluationStream]
) -> None:
    with _STREAMS_LOCK:
        current = _STREAMS.get(identity)
        if current is not None and current[0] is reference:
            _STREAMS.pop(identity, None)
        locked = _LOCKED_STREAMS.get(identity)
        if locked is reference:
            _LOCKED_STREAMS.pop(identity, None)


def _stream_axes(
    axes: tuple[FoldSessionAxis, ...],
    economic_axes: tuple[EconomicObservationAxis, ...],
) -> tuple[tuple[str, date, int], ...]:
    if type(axes) is not tuple or len(axes) != 24:
        raise FormalEvaluationError("stream requires all 24 fold-horizon axes")
    expected = tuple(
        (fold, horizon) for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    )
    by_fold: dict[str, dict[int, tuple[SessionPoint, ...]]] = {}
    global_dates: dict[date, int] = {}
    global_positions: dict[int, date] = {}
    for axis, geometry in zip(axes, expected, strict=True):
        if (
            type(axis) is not FoldSessionAxis
            or (axis.fold_id, axis.horizon_sessions) != geometry
            or type(axis.sessions) is not tuple
            or len(axis.sessions) < 20
        ):
            raise FormalEvaluationError("stream fold axes changed geometry")
        frozen = FORMAL_FOLD_HORIZON_AXIS_SUMMARIES[expected.index(geometry)]
        if (
            frozen[:2] != geometry
            or len(axis.sessions) != frozen[4]
            or axis.sessions[0].session.isoformat() != frozen[2]
            or _v2_session_axis_sha256(axis.sessions) != frozen[5]
        ):
            raise FormalEvaluationError(
                "stream fold axis differs from the reviewed horizon geometry"
            )
        prior_date: date | None = None
        prior_position: int | None = None
        for point in axis.sessions:
            if type(point) is not SessionPoint or type(point.session) is not date:
                raise FormalEvaluationError("stream session point changed type")
            _v2_int(point.session_position, "stream session position")
            if (
                (prior_date is not None and point.session <= prior_date)
                or (
                    prior_position is not None
                    and point.session_position <= prior_position
                )
                or global_dates.setdefault(point.session, point.session_position)
                != point.session_position
                or global_positions.setdefault(point.session_position, point.session)
                != point.session
            ):
                raise FormalEvaluationError("stream session axis is not monotone")
            prior_date = point.session
            prior_position = point.session_position
        by_fold.setdefault(axis.fold_id, {})[axis.horizon_sessions] = axis.sessions
    for fold in FORMAL_FOLD_IDS:
        fold_axes = by_fold.get(fold)
        if fold_axes is None or tuple(fold_axes) != HORIZONS:
            raise FormalEvaluationError("stream fold-horizon axes are incomplete")
        # The frozen horizon-specific walk-forward geometry has a common
        # exclusive end and successively later starts.  Therefore each longer
        # horizon axis must be an exact suffix of the preceding axis; accepting
        # merely equal counts would reintroduce the old H60-axis collapse.
        for shorter, longer in zip(HORIZONS, HORIZONS[1:]):
            shorter_axis = fold_axes[shorter]
            longer_axis = fold_axes[longer]
            if (
                len(longer_axis) >= len(shorter_axis)
                or shorter_axis[-len(longer_axis):] != longer_axis
            ):
                raise FormalEvaluationError(
                    "stream horizon axes are not exact nested frozen suffixes"
                )
    for index in range(1, len(FORMAL_FOLD_IDS)):
        prior = by_fold[FORMAL_FOLD_IDS[index - 1]][HORIZONS[0]]
        current = by_fold[FORMAL_FOLD_IDS[index]][HORIZONS[0]]
        if current[0].session_position <= prior[-1].session_position:
            raise FormalEvaluationError("stream fold axes overlap")
    _require_economic_observation_axes(
        economic_axes,
        global_date_positions=global_dates,
        global_position_dates=global_positions,
    )
    economic_by_fold = {axis.fold_id: axis.sessions for axis in economic_axes}
    result: list[tuple[str, date, int]] = []
    for fold in FORMAL_FOLD_IDS:
        points = {
            point.session: point
            for point in (
                *by_fold[fold][HORIZONS[0]], *economic_by_fold[fold]
            )
        }
        result.extend(
            (fold, point.session, point.session_position)
            for point in sorted(points.values(), key=lambda item: item.session)
        )
    return tuple(result)


def _stream_horizon_block_keys(
    axes: tuple[FoldSessionAxis, ...],
) -> frozenset[tuple[str, date, int, int]]:
    return frozenset(
        (
            axis.fold_id,
            point.session,
            point.session_position,
            axis.horizon_sessions,
        )
        for axis in axes
        for point in axis.sessions
    )


def _stream_economic_block_keys(
    axes: tuple[EconomicObservationAxis, ...],
) -> frozenset[tuple[str, date, int]]:
    return frozenset(
        (axis.fold_id, point.session, point.session_position)
        for axis in axes
        for point in axis.sessions
    )


def _stream_economic_terminal_keys(
    axes: tuple[EconomicObservationAxis, ...],
) -> frozenset[tuple[str, date, int]]:
    return frozenset(
        (axis.fold_id, axis.sessions[-1].session,
         axis.sessions[-1].session_position)
        for axis in axes
    )


def begin_formal_evaluation_stream(
    *, source_view_id: str, input_id: str, input_sha256: str,
    fold_axes: tuple[FoldSessionAxis, ...],
    economic_observation_axes: tuple[EconomicObservationAxis, ...],
    economic_execution_definition_sha256: str,
    power_floor: PowerFloorBinding,
) -> FormalEvaluationStream:
    """Create an opaque one-pass sufficient-statistics accumulator."""

    if source_view_id not in SOURCE_VIEW_IDS:
        raise FormalEvaluationError("stream source view is not frozen")
    _v2_safe_id(input_id, "stream input_id")
    _v2_sha(input_sha256, "stream input_sha256")
    _v2_sha(
        economic_execution_definition_sha256,
        "stream economic execution definition sha256",
    )
    if (
        economic_execution_definition_sha256
        != ECONOMIC_EXECUTION_DEFINITION_SHA256
    ):
        raise FormalEvaluationError(
            "stream economic execution definition changed"
        )
    _require_power_floor_binding(power_floor, context="stream")
    expected_blocks = _stream_axes(fold_axes, economic_observation_axes)
    if sum(
        len(axis.sessions)
        for axis in fold_axes
        if axis.horizon_sessions == SLEEVE_HOLDING_SESSIONS
    ) != power_floor.h20_test_session_capacity:
        raise FormalEvaluationError(
            "stream H20 axis differs from authenticated power census"
        )
    digest = hashlib.sha256(_v2_bytes((
        STREAM_SCHEMA, source_view_id, input_id, input_sha256,
        fold_axes, economic_observation_axes,
        economic_execution_definition_sha256, power_floor,
    ))).hexdigest()
    value = object.__new__(FormalEvaluationStream)
    for name, item in {
        "stream_id": _v2_identity("arv2-formal-evaluation-stream-", digest),
        "schema": STREAM_SCHEMA,
        "source_view_id": source_view_id,
        "input_id": input_id,
        "input_sha256": input_sha256,
        "fold_axes": fold_axes,
        "economic_observation_axes": economic_observation_axes,
        "economic_execution_definition_sha256": (
            economic_execution_definition_sha256
        ),
        "power_floor": power_floor,
    }.items():
        object.__setattr__(value, name, item)
    state = _StreamState(
        creator_pid=os.getpid(),
        owner_thread_id=threading.get_ident(),
        epoch=0,
        next_block_index=0,
        expected_blocks=expected_blocks,
        horizon_block_keys=_stream_horizon_block_keys(fold_axes),
        economic_block_keys=_stream_economic_block_keys(
            economic_observation_axes
        ),
        economic_decision_keys=frozenset(
            (axis.fold_id, point.session, point.session_position)
            for axis in fold_axes
            if axis.horizon_sessions == SLEEVE_HOLDING_SESSIONS
            for point in axis.sessions
        ),
        economic_terminal_keys=_stream_economic_terminal_keys(
            economic_observation_axes
        ),
        date_stats=[],
        active_sleeves={fold: [] for fold in FORMAL_FOLD_IDS},
        costs={
            (fold, cost): _StreamCostState(cost, {}, [], [])
            for fold in FORMAL_FOLD_IDS for cost in COST_BPS_GRID
        },
        economic_folds={}, accepted_row_count=0, refused_row_count=0,
        finished=False, failed=False,
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_stream(key, ref)
    )
    with _STREAMS_LOCK:
        _STREAMS[identity] = (
            reference, _stream_static_bytes(value), _stream_topology(value),
            state, _build_stream_state_authority(state),
        )
    return _require_stream(value)[0]


def _lock_stream_after_failed_transition(
    value: FormalEvaluationStream,
) -> None:
    """Irreversibly consume authority after a staged transition fails."""

    registered = _STREAMS.pop(id(value), None)
    if registered is not None and registered[0]() is value:
        _LOCKED_STREAMS[id(value)] = registered[0]


def _clone_stream_state(state: _StreamState) -> _StreamState:
    """Create an isolated candidate for one exact compare-and-swap update."""

    return _StreamState(
        creator_pid=state.creator_pid,
        owner_thread_id=state.owner_thread_id,
        epoch=state.epoch,
        next_block_index=state.next_block_index,
        expected_blocks=state.expected_blocks,
        horizon_block_keys=state.horizon_block_keys,
        economic_block_keys=state.economic_block_keys,
        economic_decision_keys=state.economic_decision_keys,
        economic_terminal_keys=state.economic_terminal_keys,
        date_stats=list(state.date_stats),
        active_sleeves={
            fold: list(sleeves)
            for fold, sleeves in state.active_sleeves.items()
        },
        costs={
            key: _StreamCostState(
                cost_bps=current.cost_bps,
                pretrade_weights=dict(current.pretrade_weights),
                fold_daily=list(current.fold_daily),
                fold_turnover=list(current.fold_turnover),
                refusal_counts_by_session=list(
                    current.refusal_counts_by_session
                ),
                fold_state_valid=current.fold_state_valid,
                session_count=current.session_count,
                refused_session_count=current.refused_session_count,
                invested_count=current.invested_count,
                cash_sleeves=current.cash_sleeves,
                selected_sleeves=current.selected_sleeves,
                terminal_liquidation=current.terminal_liquidation,
                refusal_counts=Counter(current.refusal_counts),
            )
            for key, current in state.costs.items()
        },
        economic_folds=dict(state.economic_folds),
        accepted_row_count=state.accepted_row_count,
        refused_row_count=state.refused_row_count,
        finished=state.finished,
        failed=state.failed,
    )


def _require_stream(
    value: FormalEvaluationStream, *, deep: bool = False,
) -> tuple[FormalEvaluationStream, _StreamState]:
    if type(value) is not FormalEvaluationStream:
        raise FormalEvaluationError("formal evaluation stream changed type")
    with _STREAMS_LOCK:
        registered = _STREAMS.get(id(value))
        locked = _LOCKED_STREAMS.get(id(value))
    if locked is not None and locked() is value:
        raise FormalEvaluationError(
            "formal evaluation stream is locked after a failed consumption"
        )
    if registered is not None and (
        registered[4].creator_pid != os.getpid()
        or registered[4].owner_thread_id != threading.get_ident()
    ):
        with _STREAMS_LOCK:
            _lock_stream_after_failed_transition(value)
        raise FormalEvaluationError(
            "formal evaluation stream process or owner thread changed"
        )
    if (
        registered is None
        or registered[0]() is not value
        or value.schema != STREAM_SCHEMA
        or registered[1] != _stream_static_bytes(value)
        or registered[2] != _stream_topology(value)
    ):
        raise FormalEvaluationError(
            "formal evaluation stream is not builder-authenticated"
        )
    try:
        _require_stream_state_authority(
            registered[3], registered[4], deep=deep
        )
    except (AttributeError, TypeError, ValueError) as exc:
        with _STREAMS_LOCK:
            _lock_stream_after_failed_transition(value)
        raise FormalEvaluationError(
            "formal evaluation stream mutable state changed"
        ) from exc
    if registered[3].failed:
        raise FormalEvaluationError(
            "formal evaluation stream is locked after a failed consumption"
        )
    _stream_axes(value.fold_axes, value.economic_observation_axes)
    return value, registered[3]


def _single_stat(
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
    *, fold_id: str, decision_session: date, arm: str,
) -> tuple[Decimal | None, str | None]:
    key = (fold_id, decision_session)
    valid, invalid = _v2_single_ics({key: rows}, {key: refusals}, arm=arm)
    if valid:
        return valid[0][2], None
    if sum(invalid.values()) != 1:
        raise FormalEvaluationError("stream IC date disposition is not exhaustive")
    return None, next(iter(invalid))


def _paired_stat(
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
    *, fold_id: str, decision_session: date,
) -> tuple[Decimal | None, Decimal | None, str | None]:
    key = (fold_id, decision_session)
    valid, invalid = _v2_paired_ics({key: rows}, {key: refusals})
    if valid:
        return valid[0][2], valid[0][3], None
    if sum(invalid.values()) != 1:
        raise FormalEvaluationError("stream paired-IC disposition is not exhaustive")
    return None, None, next(iter(invalid))


def _fm_stat(
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
    *, fold_id: str, decision_session: date, arm: str,
) -> tuple[Decimal | None, Decimal | None, int | None, str | None]:
    key = (fold_id, decision_session)
    valid, invalid, counts = _v2_fama_macbeth(
        {key: rows}, {key: refusals}, arm=arm
    )
    if valid:
        return valid[0][2], valid[0][3], counts[0][1], None
    if sum(invalid.values()) != 1:
        raise FormalEvaluationError("stream Fama-MacBeth disposition is not exhaustive")
    return None, None, None, next(iter(invalid))


def _stream_date_stat(
    *, fold_id: str, session: date, position: int, horizon: int,
    rows: tuple[EvaluationRow, ...], refusals: tuple[EvaluationRefusal, ...],
) -> _StreamDateStat:
    firm_ic, firm_ic_invalid = _single_stat(
        rows, refusals, fold_id=fold_id, decision_session=session,
        arm="firm_specific",
    )
    global_ic, global_ic_invalid = _single_stat(
        rows, refusals, fold_id=fold_id, decision_session=session, arm="global",
    )
    paired_firm, paired_global, paired_invalid = _paired_stat(
        rows, refusals, fold_id=fold_id, decision_session=session,
    )
    firm_bull, firm_bear, firm_parameters, firm_fm_invalid = _fm_stat(
        rows, refusals, fold_id=fold_id, decision_session=session,
        arm="firm_specific",
    )
    global_bull, global_bear, global_parameters, global_fm_invalid = _fm_stat(
        rows, refusals, fold_id=fold_id, decision_session=session, arm="global",
    )
    candidate = (
        horizon == 20 and len(rows) >= 20 and not refusals
    )
    capable = candidate and not (
        len({item.firm_specific_score for item in rows}) == 1
        and len({item.global_score for item in rows}) == 1
    )
    return _StreamDateStat(
        fold_id, session, position, horizon, len(rows), len(refusals),
        tuple(sorted(Counter(item.reason.value for item in refusals).items())),
        len({item.common_event_component_id for item in rows}),
        firm_ic, firm_ic_invalid, global_ic, global_ic_invalid,
        paired_firm, paired_global, paired_invalid,
        firm_bull, firm_bear, firm_parameters, firm_fm_invalid,
        global_bull, global_bear, global_parameters, global_fm_invalid,
        candidate, capable,
    )


def _consume_economic(
    state: _StreamState, block: FormalEvaluationSessionBlock,
) -> None:
    fold = block.fold_id
    session = block.economic_session
    if session is None:
        raise FormalEvaluationError(
            "economic session is absent from its observation axis"
        )
    key = (fold, session.session, session.session_position)
    decision_eligible = key in state.economic_decision_keys
    terminal_liquidation = key in state.economic_terminal_keys
    if terminal_liquidation and decision_eligible:
        raise FormalEvaluationError(
            "economic terminal observation overlaps a decision session"
        )
    if not decision_eligible and session.decisions:
        raise FormalEvaluationError(
            "economic runoff observation created a new sleeve"
        )
    selected = (
        _v2_selected_sleeve(session.decisions) if decision_eligible else ()
    )
    active = state.active_sleeves[fold]
    if decision_eligible:
        active.append(_v2_new_sleeve(selected))
    target = _v2_targets(active)
    sleeve_incidence_count = sum(
        len(sleeve.active_security_ids) for sleeve in active
    )
    duplicate_sleeve_incidence_count = sleeve_incidence_count - len(target)
    expected_outcomes = tuple(sorted(target))
    if tuple(item.security_id for item in session.security_outcomes) != expected_outcomes:
        raise FormalEvaluationError(
            "stream economic held-name census is not the exact active union"
        )
    row_map = {item.security_id: item for item in session.security_outcomes}
    benchmark_refusals: set[str] = set()
    if session.benchmark_refusal_reason is not None:
        benchmark_refusals.add(session.benchmark_refusal_reason.value)
    security_refusals = {
        item.reason.value
        for item in session.security_outcomes
        if item.disposition is EconomicOutcomeDisposition.NAMED_REFUSAL
        and item.reason is not None
    }
    session_refusals = benchmark_refusals | security_refusals
    terminal_security_ids = frozenset(
        item.security_id
        for item in session.security_outcomes
        if item.terminal_payoff_applied
    )
    if terminal_liquidation and (
        target
        or session.security_outcomes
        or session.benchmark_total_return != Decimal(0)
        or session.benchmark_refusal_reason is not None
    ):
        raise FormalEvaluationError(
            "terminal liquidation observation changed its cost-only semantics"
        )
    for cost in COST_BPS_GRID:
        current = state.costs[(fold, cost)]
        current.session_count += 1
        dated_refusals = Counter(session_refusals)
        if decision_eligible:
            current.cash_sleeves += int(not selected)
            current.selected_sleeves += int(bool(selected))
        current.invested_count += int(bool(target))
        if session_refusals:
            current.refused_session_count += 1
            current.refusal_counts.update(session_refusals)
        if current.fold_state_valid and security_refusals:
            current.fold_state_valid = False
        if current.fold_state_valid:
            securities = set(current.pretrade_weights) | set(target)
            with localcontext(_context()):
                turnover = _stable_sum(tuple(
                    +(
                        target.get(name, Decimal(0))
                        - current.pretrade_weights.get(name, Decimal(0))
                    ).copy_abs()
                    for name in securities
                ))
                gross = _stable_sum(tuple(
                    +(weight * row_map[name].gross_total_return)
                    for name, weight in target.items()
                ))
                transaction_cost = +(
                    turnover * Decimal(cost) / Decimal(10_000)
                )
                net = +(gross - transaction_cost)
                ending_wealth = +(Decimal(1) + net)
            if ending_wealth <= 0:
                current.fold_state_valid = False
                current.refusal_counts.update(("nonpositive_post_cost_wealth",))
                current.refused_session_count += int(not session_refusals)
                if not session_refusals:
                    dated_refusals["nonpositive_post_cost_wealth"] += 1
            else:
                current.fold_turnover.append(turnover)
                if terminal_liquidation:
                    current.terminal_liquidation = turnover
                with localcontext(_context()):
                    current.pretrade_weights = {
                        name: +(
                            weight
                            * (Decimal(1) + row_map[name].gross_total_return)
                            / ending_wealth
                        )
                        for name, weight in target.items() if weight != 0
                        and name not in terminal_security_ids
                    }
                if not benchmark_refusals:
                    with localcontext(_context()):
                        excess = +(net - session.benchmark_total_return)
                    current.fold_daily.append(EconomicTrialObservation(
                        fold_id=fold,
                        session=session.session,
                        session_position=session.session_position,
                        cost_bps_per_side=cost,
                        gross_portfolio_total_return=gross,
                        benchmark_total_return=session.benchmark_total_return,
                        net_portfolio_total_return=net,
                        net_excess_daily_total_return=excess,
                        turnover=turnover,
                        sleeve_security_incidence_count=(
                            sleeve_incidence_count
                        ),
                        duplicate_sleeve_security_incidence_count=(
                            duplicate_sleeve_incidence_count
                        ),
                        terminal_liquidation=terminal_liquidation,
                    ))
        if dated_refusals:
            current.refusal_counts_by_session.append((
                session.session, tuple(sorted(dated_refusals.items()))
            ))
    if terminal_liquidation:
        if active:
            raise FormalEvaluationError(
                "terminal liquidation arrived before every sleeve expired"
            )
    else:
        state.active_sleeves[fold] = _v2_advance_sleeves(
            active, terminal_security_ids
        )


def _finish_economic_fold(state: _StreamState, fold: str) -> None:
    for cost in COST_BPS_GRID:
        current = state.costs[(fold, cost)]
        daily = list(current.fold_daily)
        turnover = list(current.fold_turnover)
        refusal_counts_by_session = list(current.refusal_counts_by_session)
        reasons: list[str] = []
        liquidation = current.terminal_liquidation
        if current.fold_state_valid:
            if current.pretrade_weights:
                raise FormalEvaluationError(
                    "economic fold sealed before explicit terminal liquidation"
                )
        else:
            daily = []
            turnover = []
            unaccounted = current.session_count - current.refused_session_count
            if unaccounted < 0:
                raise FormalEvaluationError(
                    "economic fold refusal census exceeded its session axis"
                )
            current.refusal_counts[
                ECONOMIC_FOLD_STATE_LOSS_EXCLUSION
            ] += unaccounted
            current.refused_session_count += unaccounted
            refused_dates = {item[0] for item in refusal_counts_by_session}
            refusal_counts_by_session.extend(
                (
                    observation.session,
                    ((ECONOMIC_FOLD_STATE_LOSS_EXCLUSION, 1),),
                )
                for observation in current.fold_daily
                if observation.session not in refused_dates
            )
            # Sessions after holding-state loss have no retained observation,
            # so derive their dates from the exact economic axis already
            # consumed for this fold.  The stream does not retain raw rows,
            # but each cost path advances in lockstep and its session count is
            # exact; callers need a dated refusal ledger rather than a blanket
            # invalidation of every calendar year in the fold.
            observed_dates = {
                item[0] for item in refusal_counts_by_session
            } | {item.session for item in current.fold_daily}
            fold_sessions = tuple(
                key[1]
                for key in state.expected_blocks[:state.next_block_index]
                if key[0] == fold and key in state.economic_block_keys
            )
            refusal_counts_by_session.extend(
                (
                    session,
                    ((ECONOMIC_FOLD_STATE_LOSS_EXCLUSION, 1),),
                )
                for session in fold_sessions
                if session not in observed_dates
            )
            reasons.append(
                f"{fold}:{ECONOMIC_FOLD_STATE_LOSS_EXCLUSION}"
            )
        refusal_counts_by_session.sort(key=lambda item: item[0])
        if len(refusal_counts_by_session) != current.refused_session_count:
            raise FormalEvaluationError(
                "economic fold dated refusal census is not exhaustive"
            )
        state.economic_folds[(fold, cost)] = _StreamEconomicFold(
            fold, cost, current.session_count, tuple(daily), tuple(turnover),
            current.refused_session_count, current.invested_count,
            current.cash_sleeves, current.selected_sleeves, liquidation,
            tuple(sorted(current.refusal_counts.items())),
            tuple(refusal_counts_by_session), tuple(reasons),
        )


def consume_formal_evaluation_session_block(
    stream: FormalEvaluationStream,
    block: FormalEvaluationSessionBlock,
) -> FormalEvaluationStream:
    """Consume exactly the next complete fold/session cross-section."""

    with _STREAMS_LOCK:
        value, state = _require_stream(stream)
        registered = _STREAMS.get(id(value))
        if registered is None or registered[3] is not state:
            raise FormalEvaluationError(
                "formal evaluation stream authority disappeared"
            )
        prior_authority = registered[4]
        _require_formal_evaluation_session_block(block)
        if state.finished:
            raise FormalEvaluationError(
                "formal evaluation stream is already sealed"
            )
        if state.next_block_index >= len(state.expected_blocks) or (
            block.fold_id, block.decision_session, block.session_position
        ) != state.expected_blocks[state.next_block_index]:
            raise FormalEvaluationError(
                "formal session block is missing or reordered"
            )
        allowed_horizons = tuple(
            horizon
            for horizon in HORIZONS
            if (
                block.fold_id,
                block.decision_session,
                block.session_position,
                horizon,
            ) in state.horizon_block_keys
        )
        supplied_horizons = {
            item.horizon_sessions for item in (*block.rows, *block.refusals)
        }
        if not supplied_horizons.issubset(allowed_horizons):
            raise FormalEvaluationError(
                "formal session block carries a row outside its exact horizon axis"
            )
        economic_required = (
            block.fold_id, block.decision_session, block.session_position
        ) in state.economic_block_keys
        if (block.economic_session is not None) is not economic_required:
            raise FormalEvaluationError(
                "economic session presence differs from its exact observation axis"
            )
        # Derive every pure per-date statistic before touching the accumulator.
        # Once mutation begins, any later error permanently locks the stream;
        # a retry can therefore never combine a partial first attempt with a
        # second observation of the same session.
        new_stats: list[_StreamDateStat] = []
        for horizon in allowed_horizons:
            rows = tuple(
                item for item in block.rows if item.horizon_sessions == horizon
            )
            refusals = tuple(
                item
                for item in block.refusals
                if item.horizon_sessions == horizon
            )
            new_stats.append(_stream_date_stat(
                fold_id=block.fold_id,
                session=block.decision_session,
                position=block.session_position,
                horizon=horizon,
                rows=rows,
                refusals=refusals,
            ))
        staged = _clone_stream_state(state)
        mutation_started = False
        try:
            mutation_started = True
            staged.date_stats.extend(new_stats)
            staged.accepted_row_count += len(block.rows)
            staged.refused_row_count += len(block.refusals)
            if economic_required:
                _consume_economic(staged, block)
            staged.next_block_index += 1
            if (
                staged.next_block_index == len(staged.expected_blocks)
                or staged.expected_blocks[staged.next_block_index][0]
                != block.fold_id
            ):
                _finish_economic_fold(staged, block.fold_id)
            staged.epoch = state.epoch + 1
            next_authority = _build_stream_state_authority(
                staged, prior=prior_authority
            )
            current = _STREAMS.get(id(value))
            if (
                current is not registered
                or current[3] is not state
                or current[4] is not prior_authority
            ):
                raise FormalEvaluationError(
                    "formal evaluation stream transition lost compare-and-swap"
                )
            _require_stream_state_authority(
                state, prior_authority, deep=False
            )
            _STREAMS[id(value)] = (
                registered[0], registered[1], registered[2],
                staged, next_authority,
            )
        except BaseException:
            if mutation_started:
                _lock_stream_after_failed_transition(value)
            raise
        return value


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamAxisCarrier:
    source_view_id: str
    fold_axes: tuple[FoldSessionAxis, ...]


def _stream_economic_summary(
    *, stream: FormalEvaluationStream, state: _StreamState, slice_id: str,
    folds: tuple[str, ...], cost_bps: int, required_dates: int,
    resamples: int,
) -> EconomicCostSummary:
    selected = tuple(state.economic_folds[(fold, cost_bps)] for fold in folds)
    daily = tuple(item for fold in selected for item in fold.daily)
    turnover = tuple(item for fold in selected for item in fold.daily_turnover)
    refusal_counts: Counter[str] = Counter()
    reasons: list[str] = []
    for fold in selected:
        refusal_counts.update(dict(fold.refusal_counts))
        reasons.extend(fold.reasons)
    reasons.extend(
        f"{reason}:{count}" for reason, count in sorted(refusal_counts.items())
    )
    refused_sessions = sum(item.refused_session_count for item in selected)
    status = (
        Disposition.INVALID_DATA
        if refusal_counts.get(RefusalReason.OUTCOME_IDENTITY_INVALID.value, 0)
        else (
            Disposition.INCONCLUSIVE
            if refused_sessions > 0
            else Disposition.PASS
        )
    )
    if status is not Disposition.INVALID_DATA and len(daily) < required_dates:
        status = Disposition.INCONCLUSIVE
        reasons.append("valid_return_session_floor_not_met")
    values = tuple(item.net_excess_daily_total_return for item in daily)
    mean = None if not values else _mean(values)
    cumulative: Decimal | None = None
    if values and refused_sessions == 0:
        with localcontext(_context()):
            accumulator = Decimal(1)
            for item in daily:
                accumulator = +(
                    accumulator
                    * (Decimal(1) + item.net_portfolio_total_return)
                )
            cumulative = +(accumulator - Decimal(1))
    bootstrap_count: int | None = None
    p_value: Fraction | None = None
    if slice_id == FORMAL_SLICE_ID and folds == FORMAL_FOLD_IDS and values:
        metric_id = _v2_stock_bootstrap_metric_id(
            statistic="economic_equal_weight", cost_bps=cost_bps,
        )
        replicates = _v2_stock_centered_bootstrap(
            values=tuple(
                (
                    item.fold_id, item.session_position,
                    item.net_excess_daily_total_return,
                )
                for item in daily
            ),
            axes={
                fold: tuple(
                    point.session_position for point in axis.sessions
                )
                for axis in stream.economic_observation_axes
                if (fold := axis.fold_id) in folds
            },
            block_length=SLEEVE_HOLDING_SESSIONS,
            source_view_id=stream.source_view_id, slice_id=slice_id,
            metric_id=metric_id, resamples=resamples,
        )
        if replicates is None:
            status = (
                Disposition.INVALID_DATA
                if status is Disposition.INVALID_DATA
                else Disposition.INCONCLUSIVE
            )
            reasons.append("economic_bootstrap_has_no_complete_block_domain")
        else:
            bootstrap_count = resamples
            p_value = _v2_two_sided_p(mean, replicates)
    if status is not Disposition.PASS:
        p_value = None
    return EconomicCostSummary(
        slice_id, cost_bps, status,
        sum(item.session_count for item in selected), len(daily),
        refused_sessions, sum(item.invested_count for item in selected),
        sum(item.cash_sleeves for item in selected),
        sum(item.selected_sleeves for item in selected), mean, cumulative,
        None if not turnover else _mean(turnover),
        _stable_sum(tuple(item.terminal_liquidation for item in selected)),
        bootstrap_count, p_value, tuple(reasons),
    )


def _stream_report(
    stream: FormalEvaluationStream, state: _StreamState, *, resamples: int,
) -> FormalEvaluationReportV2:
    slices = (
        (FORMAL_SLICE_ID, FORMAL_FOLD_IDS),
        (DESCRIPTIVE_SLICE_ID, DESCRIPTIVE_FOLD_IDS),
    )
    coverage: list[CoverageSummary] = []
    ic_summaries: list[IcSummary] = []
    fm_summaries: list[FamaMacBethSummary] = []
    paired_summaries: list[PairedIcSummary] = []
    required_global = max(
        MINIMUM_VALID_DATES, stream.power_floor.required_valid_dates
    )
    carrier = _StreamAxisCarrier(stream.source_view_id, stream.fold_axes)
    for slice_id, folds in slices:
        scopes = tuple((fold, (fold,)) for fold in folds) + ((None, folds),)
        for fold_id, scope_folds in scopes:
            required_dates = (
                MINIMUM_VALID_DATES if fold_id is not None else required_global
            )
            for horizon in HORIZONS:
                stats = tuple(
                    item for item in state.date_stats
                    if item.fold_id in scope_folds
                    and item.horizon_sessions == horizon
                )
                refusal_counts: Counter[str] = Counter()
                for item in stats:
                    refusal_counts.update(dict(item.refusals_by_reason))
                coverage.append(CoverageSummary(
                    slice_id, fold_id, horizon,
                    sum(item.accepted_rows for item in stats),
                    sum(item.refused_rows for item in stats),
                    tuple(sorted(refusal_counts.items())),
                    sum(item.accepted_component_count for item in stats),
                ))
                for arm in ("firm_specific", "global"):
                    ic_valid: list[tuple[str, int, Decimal]] = []
                    ic_invalid: Counter[str] = Counter()
                    fm_valid: list[tuple[str, int, Decimal, Decimal]] = []
                    fm_invalid: Counter[str] = Counter()
                    parameter_counts: list[tuple[str, int]] = []
                    for item in stats:
                        ic_value = (
                            item.firm_ic if arm == "firm_specific"
                            else item.global_ic
                        )
                        ic_reason = (
                            item.firm_ic_invalid if arm == "firm_specific"
                            else item.global_ic_invalid
                        )
                        if ic_reason is None:
                            assert ic_value is not None
                            ic_valid.append((item.fold_id, item.session_position, ic_value))
                        else:
                            ic_invalid[ic_reason] += 1
                        bullish = (
                            item.firm_fm_bullish if arm == "firm_specific"
                            else item.global_fm_bullish
                        )
                        bearish = (
                            item.firm_fm_bearish if arm == "firm_specific"
                            else item.global_fm_bearish
                        )
                        parameter_count = (
                            item.firm_fm_parameter_count
                            if arm == "firm_specific"
                            else item.global_fm_parameter_count
                        )
                        fm_reason = (
                            item.firm_fm_invalid if arm == "firm_specific"
                            else item.global_fm_invalid
                        )
                        if fm_reason is None:
                            assert (
                                bullish is not None and bearish is not None
                                and parameter_count is not None
                            )
                            fm_valid.append((
                                item.fold_id, item.session_position,
                                bullish, bearish,
                            ))
                            parameter_counts.append((
                                f"{item.fold_id}:{item.decision_session.isoformat()}",
                                parameter_count,
                            ))
                        else:
                            fm_invalid[fm_reason] += 1
                    ic_summaries.append(_v2_ic_summary(
                        slice_id=slice_id, fold_id=fold_id, horizon=horizon,
                        arm=arm, valid=tuple(ic_valid), invalid=ic_invalid,
                        required_dates=required_dates,
                    ))
                    fm_summaries.extend(_v2_fm_summaries(
                        value=carrier, slice_id=slice_id, fold_id=fold_id,
                        folds=scope_folds, horizon=horizon, arm=arm,
                        valid=tuple(fm_valid), invalid=fm_invalid,
                        parameter_counts=tuple(parameter_counts),
                        required_dates=required_dates, resamples=resamples,
                    ))
                paired_valid: list[tuple[str, int, Decimal, Decimal]] = []
                paired_invalid: Counter[str] = Counter()
                for item in stats:
                    if item.paired_invalid is None:
                        assert (
                            item.paired_firm_ic is not None
                            and item.paired_global_ic is not None
                        )
                        paired_valid.append((
                            item.fold_id, item.session_position,
                            item.paired_firm_ic, item.paired_global_ic,
                        ))
                    else:
                        paired_invalid[item.paired_invalid] += 1
                paired_summaries.append(_v2_paired_summary(
                    value=carrier, slice_id=slice_id, fold_id=fold_id,
                    folds=scope_folds, horizon=horizon,
                    valid=tuple(paired_valid), invalid=paired_invalid,
                    required_dates=required_dates, resamples=resamples,
                ))
    economic_summaries = tuple(
        _stream_economic_summary(
            stream=stream, state=state, slice_id=slice_id, folds=folds,
            cost_bps=cost, required_dates=required_global,
            resamples=resamples,
        )
        for slice_id, folds in slices for cost in COST_BPS_GRID
    )
    primary_fm = next(item for item in fm_summaries if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20 and item.arm == "firm_specific"
        and item.coefficient == "bullish"
    ))
    component_count = next(item.accepted_component_count for item in coverage if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20
    ))
    fm_reasons: list[str] = []
    fm_status = primary_fm.status
    if component_count < stream.power_floor.required_connected_components:
        fm_status = Disposition.INCONCLUSIVE
        fm_reasons.append("required_connected_component_floor_not_met")
    if primary_fm.mean_beta is None or primary_fm.centered_two_sided_p_value is None:
        fm_status = (
            Disposition.INVALID_DATA
            if fm_status is Disposition.INVALID_DATA else Disposition.INCONCLUSIVE
        )
        fm_reasons.append("primary_bullish_beta_or_bootstrap_unavailable")
    elif fm_status is Disposition.PASS and not (
        primary_fm.mean_beta > 0
        and primary_fm.centered_two_sided_p_value < PRIMARY_SIZE
    ):
        fm_status = Disposition.FAIL
        fm_reasons.append("bullish_h20_mean_or_two_sided_p_failed")
    primary_paired = next(item for item in paired_summaries if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20
    ))
    paired_reasons: list[str] = []
    for fold in FORMAL_FOLD_IDS:
        selected = tuple(
            item for item in state.date_stats
            if item.fold_id == fold and item.horizon_sessions == 20
        )
        candidates = sum(item.paired_candidate for item in selected)
        capable = sum(item.paired_capable for item in selected)
        if candidates == 0:
            paired_reasons.append(f"{fold}:zero_preoutcome_candidate_dates")
        elif capable * 20 < candidates * 19:
            paired_reasons.append(
                f"{fold}:paired_score_capable_coverage_below_19_of_20"
            )
    paired_status = primary_paired.status
    if paired_reasons:
        paired_status = Disposition.INVALID_DATA
    if (
        primary_paired.observed_difference is None
        or primary_paired.one_sided_lcb95 is None
    ):
        if paired_status is not Disposition.INVALID_DATA:
            paired_status = Disposition.INCONCLUSIVE
        paired_reasons.append("paired_difference_or_lcb_unavailable")
    elif paired_status is Disposition.PASS and not (
        primary_paired.observed_difference >= 0
        and primary_paired.one_sided_lcb95 >= 0
    ):
        paired_status = Disposition.FAIL
        paired_reasons.append(
            "firm_specific_no_worse_with_confidence_gate_failed"
        )
    primary_economic = next(item for item in economic_summaries if (
        item.slice_id == FORMAL_SLICE_ID
        and item.cost_bps_per_side == PRIMARY_COST_BPS
    ))
    economic_status = primary_economic.status
    economic_reasons = list(primary_economic.reasons)
    if (
        primary_economic.mean_net_excess_daily_return is None
        or primary_economic.centered_two_sided_p_value is None
    ):
        economic_status = (
            Disposition.INVALID_DATA
            if economic_status is Disposition.INVALID_DATA
            else Disposition.INCONCLUSIVE
        )
        economic_reasons.append("economic_mean_or_bootstrap_unavailable")
    elif economic_status is Disposition.PASS and not (
        primary_economic.mean_net_excess_daily_return > 0
        and primary_economic.centered_two_sided_p_value < PRIMARY_SIZE
    ):
        economic_status = Disposition.FAIL
        economic_reasons.append("net_10bps_mean_or_two_sided_p_failed")
    primary_gates = (
        _v2_gate("bullish_20_session_fama_macbeth", fm_status, fm_reasons),
        _v2_gate(
            "firm_specific_vs_global_map_paired_20_session_ic",
            paired_status, paired_reasons,
        ),
        _v2_gate("net_20_session_sleeve", economic_status, economic_reasons),
    )
    disposition = _v2_conjunction_disposition(
        tuple(item.status for item in primary_gates)
    )
    disposition_reasons = tuple(
        f"{gate.gate_id}:{reason}"
        for gate in primary_gates for reason in gate.reasons
    )
    placeholder = FormalEvaluationReportV2(
        "", "", SCHEMA, STATUS, AUTHORITY, EVALUATION_ID,
        stream.source_view_id, stream.input_id, stream.input_sha256,
        BOOTSTRAP_SEED_SHA256, FORMAL_FOLD_IDS, DESCRIPTIVE_FOLD_IDS,
        tuple(coverage), tuple(ic_summaries), tuple(fm_summaries),
        tuple(paired_summaries), economic_summaries, primary_gates,
        disposition, disposition_reasons, b"",
    )
    digest = _v2_digest(placeholder)
    report = dataclasses.replace(
        placeholder,
        report_id=_v2_identity("arv2-formal-evaluation-report-", digest),
        report_sha256=digest,
    )
    report = dataclasses.replace(report, _canonical_document=_v2_bytes(report))
    return require_formal_evaluation_report(report)


def finish_formal_evaluation_stream(
    stream: FormalEvaluationStream, *, resamples: int = BOOTSTRAP_RESAMPLES,
) -> FormalEvaluationStreamingResult:
    """Seal a complete stream and return its bounded aggregate result."""

    with _STREAMS_LOCK:
        return _finish_formal_evaluation_stream_locked(
            stream, resamples=resamples
        )


def _finish_formal_evaluation_stream_locked(
    stream: FormalEvaluationStream, *, resamples: int,
) -> FormalEvaluationStreamingResult:
    """Finalize while serializing the last state check and one-use seal."""

    value, state = _require_stream(stream, deep=True)
    if state.finished:
        raise FormalEvaluationError("formal evaluation stream is already sealed")
    if state.next_block_index != len(state.expected_blocks):
        raise FormalEvaluationError("formal evaluation stream is incomplete")
    _v2_int(resamples, "stream bootstrap resamples", minimum=1)
    if resamples > BOOTSTRAP_RESAMPLES:
        raise FormalEvaluationError("stream bootstrap count exceeds the frozen run")
    report = _stream_report(value, state, resamples=resamples)
    census = tuple(
        (
            fold, horizon,
            sum(
                item.accepted_rows for item in state.date_stats
                if item.fold_id == fold and item.horizon_sessions == horizon
            ),
            sum(
                item.refused_rows for item in state.date_stats
                if item.fold_id == fold and item.horizon_sessions == horizon
            ),
        )
        for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    )
    result = FormalEvaluationStreamingResult(
        report, state.accepted_row_count, state.refused_row_count,
        sum(len(axis.sessions) for axis in value.economic_observation_axes),
        census,
        tuple(
            observation
            for fold in FORMAL_FOLD_IDS
            for cost in COST_BPS_GRID
            for observation in state.economic_folds[(fold, cost)].daily
        ),
        tuple(
            EconomicTrialFoldCensus(
                fold_id=item.fold_id,
                cost_bps_per_side=item.cost_bps,
                session_count=item.session_count,
                valid_return_session_count=len(item.daily),
                refused_return_session_count=item.refused_session_count,
                invested_session_count=item.invested_count,
                cash_sleeve_count=item.cash_sleeves,
                selected_sleeve_count=item.selected_sleeves,
                terminal_liquidation_turnover=item.terminal_liquidation,
                refusal_counts=item.refusal_counts,
                refusal_counts_by_session=item.refusal_counts_by_session,
                reasons=item.reasons,
            )
            for fold in FORMAL_FOLD_IDS
            for cost in COST_BPS_GRID
            for item in (state.economic_folds[(fold, cost)],)
        ),
        tuple(
            DailyInformationCoefficientObservation(
                fold_id=item.fold_id,
                decision_session=item.decision_session,
                session_position=item.session_position,
                horizon_sessions=item.horizon_sessions,
                firm_specific_ic=item.firm_ic,
                firm_specific_reason=item.firm_ic_invalid,
                global_map_ic=item.global_ic,
                global_map_reason=item.global_ic_invalid,
            )
            for item in state.date_stats
        ),
    )
    registered = _STREAMS.get(id(value))
    if registered is None or registered[3] is not state:
        raise FormalEvaluationError(
            "formal evaluation stream seal lost compare-and-swap"
        )
    _STREAMS.pop(id(value), None)
    return result


def _v2_paired_coverage_reasons(
    value: FormalEvaluationInput,
) -> tuple[str, ...]:
    reasons: list[str] = []
    rows, refusals = _v2_groups(value, FORMAL_FOLD_IDS, 20)
    for fold in FORMAL_FOLD_IDS:
        candidate = 0
        capable = 0
        keys = tuple(key for key in rows if key[0] == fold)
        for key in keys:
            date_rows = rows[key]
            if len(date_rows) < 20 or refusals[key]:
                continue
            candidate += 1
            firm = {item.firm_specific_score for item in date_rows}
            global_scores = {item.global_score for item in date_rows}
            if not (len(firm) == 1 and len(global_scores) == 1):
                capable += 1
        if candidate == 0:
            reasons.append(f"{fold}:zero_preoutcome_candidate_dates")
        elif capable * 20 < candidate * 19:
            reasons.append(f"{fold}:paired_score_capable_coverage_below_19_of_20")
    return tuple(reasons)


def _v2_gate(
    gate_id: str, status: Disposition, reasons: Sequence[str]
) -> PrimaryGateSummary:
    return PrimaryGateSummary(gate_id, status, tuple(reasons))


def _v2_conjunction_disposition(
    statuses: tuple[Disposition, ...],
) -> Disposition:
    """Apply the no-rescue precedence to the three formal gates."""
    if type(statuses) is not tuple or not statuses or any(
        type(item) is not Disposition for item in statuses
    ):
        raise FormalEvaluationError("formal gate status census changed")
    if Disposition.INVALID_DATA in statuses:
        return Disposition.INVALID_DATA
    if Disposition.FAIL in statuses:
        return Disposition.FAIL
    if Disposition.INCONCLUSIVE in statuses:
        return Disposition.INCONCLUSIVE
    if all(item is Disposition.PASS for item in statuses):
        return Disposition.PASS
    raise FormalEvaluationError("formal gate status is unknown")


def _build_formal_evaluation_report(
    evaluation_input: FormalEvaluationInput, *, resamples: int
) -> FormalEvaluationReportV2:
    """Private test seam; the public entry always supplies exactly 19,999."""
    require_formal_evaluation_input(evaluation_input)
    if type(resamples) is not int or resamples < 1 or resamples > BOOTSTRAP_RESAMPLES:
        raise FormalEvaluationError("private bootstrap count is outside its test seam")
    slices = (
        (FORMAL_SLICE_ID, FORMAL_FOLD_IDS),
        (DESCRIPTIVE_SLICE_ID, DESCRIPTIVE_FOLD_IDS),
    )
    coverage: list[CoverageSummary] = []
    ic_summaries: list[IcSummary] = []
    fm_summaries: list[FamaMacBethSummary] = []
    paired_summaries: list[PairedIcSummary] = []
    required_global = max(
        MINIMUM_VALID_DATES, evaluation_input.power_floor.required_valid_dates
    )
    for slice_id, folds in slices:
        scopes = tuple((fold, (fold,)) for fold in folds) + ((None, folds),)
        for fold_id, scope_folds in scopes:
            required_dates = MINIMUM_VALID_DATES if fold_id is not None else required_global
            for horizon in HORIZONS:
                rows_by_date, refusals_by_date = _v2_groups(
                    evaluation_input, scope_folds, horizon
                )
                accepted_rows = tuple(
                    item for values in rows_by_date.values() for item in values
                )
                refused_rows = tuple(
                    item for values in refusals_by_date.values() for item in values
                )
                coverage.append(CoverageSummary(
                    slice_id, fold_id, horizon, len(accepted_rows), len(refused_rows),
                    tuple(sorted(Counter(item.reason.value for item in refused_rows).items())),
                    len({
                        (item.fold_id, item.decision_session,
                         item.common_event_component_id)
                        for item in accepted_rows
                    }),
                ))
                for arm in ("firm_specific", "global"):
                    ic_values, ic_invalid = _v2_single_ics(
                        rows_by_date, refusals_by_date, arm=arm
                    )
                    ic_summaries.append(_v2_ic_summary(
                        slice_id=slice_id, fold_id=fold_id, horizon=horizon,
                        arm=arm, valid=ic_values, invalid=ic_invalid,
                        required_dates=required_dates,
                    ))
                    fm_values, fm_invalid, parameter_counts = _v2_fama_macbeth(
                        rows_by_date, refusals_by_date, arm=arm
                    )
                    fm_summaries.extend(_v2_fm_summaries(
                        value=evaluation_input, slice_id=slice_id,
                        fold_id=fold_id, folds=scope_folds, horizon=horizon,
                        arm=arm, valid=fm_values, invalid=fm_invalid,
                        parameter_counts=parameter_counts,
                        required_dates=required_dates, resamples=resamples,
                    ))
                paired_values, paired_invalid = _v2_paired_ics(
                    rows_by_date, refusals_by_date
                )
                paired_summaries.append(_v2_paired_summary(
                    value=evaluation_input, slice_id=slice_id, fold_id=fold_id,
                    folds=scope_folds, horizon=horizon, valid=paired_values,
                    invalid=paired_invalid, required_dates=required_dates,
                    resamples=resamples,
                ))
    economic_summaries = tuple(
        _v2_economic_cost_summary(
            value=evaluation_input, slice_id=slice_id, folds=folds,
            cost_bps=cost, required_dates=required_global,
            resamples=resamples,
        )
        for slice_id, folds in slices for cost in COST_BPS_GRID
    )

    primary_fm = next(item for item in fm_summaries if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20 and item.arm == "firm_specific"
        and item.coefficient == "bullish"
    ))
    component_count = next(item.accepted_component_count for item in coverage if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20
    ))
    fm_reasons: list[str] = []
    fm_status = primary_fm.status
    if component_count < evaluation_input.power_floor.required_connected_components:
        fm_status = Disposition.INCONCLUSIVE
        fm_reasons.append("required_connected_component_floor_not_met")
    if primary_fm.mean_beta is None or primary_fm.centered_two_sided_p_value is None:
        fm_status = (
            Disposition.INVALID_DATA if fm_status is Disposition.INVALID_DATA
            else Disposition.INCONCLUSIVE
        )
        fm_reasons.append("primary_bullish_beta_or_bootstrap_unavailable")
    elif fm_status is Disposition.PASS and not (
        primary_fm.mean_beta > 0
        and primary_fm.centered_two_sided_p_value < PRIMARY_SIZE
    ):
        fm_status = Disposition.FAIL
        fm_reasons.append("bullish_h20_mean_or_two_sided_p_failed")

    primary_paired = next(item for item in paired_summaries if (
        item.slice_id == FORMAL_SLICE_ID and item.fold_id is None
        and item.horizon_sessions == 20
    ))
    paired_reasons = list(_v2_paired_coverage_reasons(evaluation_input))
    paired_status = primary_paired.status
    if paired_reasons:
        paired_status = Disposition.INVALID_DATA
    if (
        primary_paired.observed_difference is None
        or primary_paired.one_sided_lcb95 is None
    ):
        if paired_status is not Disposition.INVALID_DATA:
            paired_status = Disposition.INCONCLUSIVE
        paired_reasons.append("paired_difference_or_lcb_unavailable")
    elif paired_status is Disposition.PASS and not (
        primary_paired.observed_difference >= 0
        and primary_paired.one_sided_lcb95 >= 0
    ):
        paired_status = Disposition.FAIL
        paired_reasons.append("firm_specific_no_worse_with_confidence_gate_failed")

    primary_economic = next(item for item in economic_summaries if (
        item.slice_id == FORMAL_SLICE_ID
        and item.cost_bps_per_side == PRIMARY_COST_BPS
    ))
    economic_status = primary_economic.status
    economic_reasons = list(primary_economic.reasons)
    if (
        primary_economic.mean_net_excess_daily_return is None
        or primary_economic.centered_two_sided_p_value is None
    ):
        economic_status = (
            Disposition.INVALID_DATA
            if economic_status is Disposition.INVALID_DATA
            else Disposition.INCONCLUSIVE
        )
        economic_reasons.append("economic_mean_or_bootstrap_unavailable")
    elif economic_status is Disposition.PASS and not (
        primary_economic.mean_net_excess_daily_return > 0
        and primary_economic.centered_two_sided_p_value < PRIMARY_SIZE
    ):
        economic_status = Disposition.FAIL
        economic_reasons.append("net_10bps_mean_or_two_sided_p_failed")

    primary_gates = (
        _v2_gate("bullish_20_session_fama_macbeth", fm_status, fm_reasons),
        _v2_gate(
            "firm_specific_vs_global_map_paired_20_session_ic",
            paired_status, paired_reasons,
        ),
        _v2_gate("net_20_session_sleeve", economic_status, economic_reasons),
    )
    statuses = tuple(item.status for item in primary_gates)
    disposition = _v2_conjunction_disposition(statuses)
    disposition_reasons = tuple(
        f"{gate.gate_id}:{reason}"
        for gate in primary_gates for reason in gate.reasons
    )
    placeholder = FormalEvaluationReportV2(
        "", "", SCHEMA, STATUS, AUTHORITY, EVALUATION_ID,
        evaluation_input.source_view_id, evaluation_input.input_id,
        evaluation_input.input_sha256,
        BOOTSTRAP_SEED_SHA256, FORMAL_FOLD_IDS, DESCRIPTIVE_FOLD_IDS,
        tuple(coverage), tuple(ic_summaries), tuple(fm_summaries),
        tuple(paired_summaries), economic_summaries, primary_gates,
        disposition, disposition_reasons, b"",
    )
    digest = _v2_digest(placeholder)
    report = dataclasses.replace(
        placeholder,
        report_id=_v2_identity("arv2-formal-evaluation-report-", digest),
        report_sha256=digest,
    )
    report = dataclasses.replace(report, _canonical_document=_v2_bytes(report))
    return require_formal_evaluation_report(report)


def build_formal_evaluation_report(
    *, evaluation_input: FormalEvaluationInput
) -> FormalEvaluationReportV2:
    """Evaluate one authenticated census with the exact 19,999 replicates."""
    return _build_formal_evaluation_report(
        evaluation_input, resamples=BOOTSTRAP_RESAMPLES
    )


def _v2_optional_decimal(value: object, name: str) -> None:
    if value is not None:
        _v2_finite_decimal(value, name)


def _v2_optional_fraction(value: object, name: str) -> None:
    if value is not None:
        if type(value) is not Fraction or value < 0 or value > 1:
            raise FormalEvaluationError(f"{name} must be an exact probability")


def _v2_reason_counts(value: object, name: str) -> None:
    if type(value) is not tuple:
        raise FormalEvaluationError(f"{name} changed container type")
    prior: str | None = None
    for item in value:
        if (
            type(item) is not tuple or len(item) != 2
            or type(item[0]) is not str or type(item[1]) is not int
            or item[1] < 0
        ):
            raise FormalEvaluationError(f"{name} contains a malformed count")
        if prior is not None and item[0] <= prior:
            raise FormalEvaluationError(f"{name} is not uniquely sorted")
        prior = item[0]


def require_formal_evaluation_report(
    report: FormalEvaluationReportV2,
) -> FormalEvaluationReportV2:
    """Reauthenticate report topology, semantics, identity, and authority."""
    if type(report) is not FormalEvaluationReportV2:
        raise FormalEvaluationError("formal evaluation report changed type")
    for name in (
        "result_read_authority_available",
        "result_disposition_authority_available", "deployment_available",
        "orders_available", "trading_available",
    ):
        if getattr(report, name) is not False:
            raise FormalEvaluationError("formal evaluation report acquired authority")
    string_fields = (
        report.report_id, report.report_sha256, report.schema, report.status,
        report.authority, report.evaluation_id, report.input_id,
        report.source_view_id, report.input_sha256, report.bootstrap_seed_sha256,
    )
    if any(type(item) is not str for item in string_fields):
        raise FormalEvaluationError("formal evaluation report scalar type changed")
    _v2_safe_id(report.report_id, "report_id")
    _v2_sha(report.report_sha256, "report_sha256")
    _v2_safe_id(report.input_id, "report input_id")
    _v2_sha(report.input_sha256, "report input_sha256")
    if (
        report.schema != SCHEMA or report.status != STATUS
        or report.authority != AUTHORITY or report.evaluation_id != EVALUATION_ID
        or report.source_view_id not in SOURCE_VIEW_IDS
        or report.bootstrap_seed_sha256 != BOOTSTRAP_SEED_SHA256
        or report.formal_fold_ids != FORMAL_FOLD_IDS
        or report.descriptive_fold_ids != DESCRIPTIVE_FOLD_IDS
    ):
        raise FormalEvaluationError("formal evaluation report static contract changed")
    for name in (
        "coverage", "ic_summaries", "fama_macbeth_summaries",
        "paired_ic_summaries", "economic_summaries", "primary_gates",
        "disposition_reasons",
    ):
        if type(getattr(report, name)) is not tuple:
            raise FormalEvaluationError(f"report {name} changed container type")
    if len(report.coverage) != 52 or len(report.ic_summaries) != 104:
        raise FormalEvaluationError("report IC or coverage census is incomplete")
    if len(report.fama_macbeth_summaries) != 208:
        raise FormalEvaluationError("report Fama-MacBeth census is incomplete")
    if len(report.paired_ic_summaries) != 52 or len(report.economic_summaries) != 8:
        raise FormalEvaluationError("report paired or economic census is incomplete")
    allowed_slices = {FORMAL_SLICE_ID, DESCRIPTIVE_SLICE_ID}
    for item in report.coverage:
        if type(item) is not CoverageSummary:
            raise FormalEvaluationError("coverage summary topology changed")
        if (
            type(item.slice_id) is not str or item.slice_id not in allowed_slices
            or not (item.fold_id is None or type(item.fold_id) is str)
            or type(item.horizon_sessions) is not int
            or item.horizon_sessions not in HORIZONS
        ):
            raise FormalEvaluationError("coverage summary scope changed")
        for count in (
            item.accepted_rows, item.refused_rows, item.accepted_component_count
        ):
            _v2_int(count, "coverage count")
        _v2_reason_counts(item.refusals_by_reason, "coverage refusal counts")
    for item in report.ic_summaries:
        if type(item) is not IcSummary or type(item.status) is not Disposition:
            raise FormalEvaluationError("IC summary topology changed")
        if item.slice_id not in allowed_slices or item.arm not in {
            "firm_specific", "global"
        } or item.horizon_sessions not in HORIZONS:
            raise FormalEvaluationError("IC summary semantics changed")
        _v2_int(item.valid_date_count, "IC valid dates")
        _v2_int(item.invalid_date_count, "IC invalid dates")
        _v2_reason_counts(item.invalid_dates_by_reason, "IC invalid reasons")
        for field, name in (
            (item.mean, "IC mean"), (item.median, "IC median"),
            (item.icir, "ICIR"), (item.hac_standard_error, "IC HAC SE"),
            (item.hac_t, "IC HAC t"),
        ):
            _v2_optional_decimal(field, name)
        _v2_optional_fraction(item.positive_date_share, "positive date share")
        if type(item.hac_pair_counts) is not tuple or any(
            type(count) is not int or count < 0 for count in item.hac_pair_counts
        ):
            raise FormalEvaluationError("IC HAC pair counts changed")
    for item in report.fama_macbeth_summaries:
        if type(item) is not FamaMacBethSummary or type(item.status) is not Disposition:
            raise FormalEvaluationError("Fama-MacBeth summary topology changed")
        if (
            item.slice_id not in allowed_slices
            or item.arm not in {"firm_specific", "global"}
            or item.coefficient not in {"bullish", "bearish"}
            or item.horizon_sessions not in HORIZONS
        ):
            raise FormalEvaluationError("Fama-MacBeth summary semantics changed")
        _v2_int(item.valid_date_count, "Fama-MacBeth valid dates")
        _v2_int(item.invalid_date_count, "Fama-MacBeth invalid dates")
        _v2_reason_counts(
            item.invalid_dates_by_reason, "Fama-MacBeth invalid reasons"
        )
        if type(item.parameter_count_by_date) is not tuple:
            raise FormalEvaluationError("parameter-count census changed type")
        for parameter in item.parameter_count_by_date:
            if (
                type(parameter) is not tuple or len(parameter) != 2
                or type(parameter[0]) is not str or type(parameter[1]) is not int
                or parameter[1] < 1
            ):
                raise FormalEvaluationError("parameter-count census is malformed")
        for field, name in (
            (item.mean_beta, "mean beta"), (item.median_beta, "median beta"),
            (item.hac_standard_error, "Fama-MacBeth HAC SE"),
            (item.hac_t, "Fama-MacBeth HAC t"),
        ):
            _v2_optional_decimal(field, name)
        if type(item.hac_pair_counts) is not tuple or any(
            type(count) is not int or count < 0 for count in item.hac_pair_counts
        ):
            raise FormalEvaluationError("Fama-MacBeth HAC pair counts changed")
        if item.bootstrap_resamples is not None:
            _v2_int(item.bootstrap_resamples, "bootstrap resamples", minimum=1)
            if item.bootstrap_resamples > BOOTSTRAP_RESAMPLES:
                raise FormalEvaluationError("bootstrap resamples exceed the frozen run")
        _v2_optional_fraction(item.centered_two_sided_p_value, "Fama-MacBeth p")
    for item in report.paired_ic_summaries:
        if type(item) is not PairedIcSummary or type(item.status) is not Disposition:
            raise FormalEvaluationError("paired summary topology changed")
        if item.slice_id not in allowed_slices or item.horizon_sessions not in HORIZONS:
            raise FormalEvaluationError("paired summary semantics changed")
        _v2_int(item.valid_date_count, "paired valid dates")
        _v2_int(item.invalid_date_count, "paired invalid dates")
        _v2_reason_counts(item.invalid_dates_by_reason, "paired invalid reasons")
        for field, name in (
            (item.mean_firm_ic, "mean firm IC"),
            (item.mean_global_ic, "mean global IC"),
            (item.observed_difference, "paired difference"),
            (item.one_sided_q95, "paired q95"),
            (item.one_sided_lcb95, "paired LCB"),
        ):
            _v2_optional_decimal(field, name)
        if item.bootstrap_resamples is not None:
            _v2_int(item.bootstrap_resamples, "paired bootstrap resamples", minimum=1)

    for item in report.economic_summaries:
        if type(item) is not EconomicCostSummary or type(item.status) is not Disposition:
            raise FormalEvaluationError("economic summary topology changed")
        if item.slice_id not in allowed_slices or item.cost_bps_per_side not in COST_BPS_GRID:
            raise FormalEvaluationError("economic summary semantics changed")
        for count in (
            item.session_count, item.valid_return_session_count,
            item.refused_return_session_count, item.invested_session_count,
            item.cash_sleeve_count, item.selected_sleeve_count,
        ):
            _v2_int(count, "economic count")
        if (
            item.valid_return_session_count + item.refused_return_session_count
            != item.session_count
        ):
            raise FormalEvaluationError("economic return-session census changed")
        for field, name in (
            (item.mean_net_excess_daily_return, "economic mean"),
            (item.cumulative_net_total_return, "economic cumulative return"),
            (item.mean_daily_turnover, "economic turnover"),
            (item.terminal_liquidation_turnover, "terminal turnover"),
        ):
            _v2_optional_decimal(field, name)
        if item.terminal_liquidation_turnover < 0:
            raise FormalEvaluationError("terminal liquidation turnover is negative")
        if type(item.reasons) is not tuple or any(type(reason) is not str for reason in item.reasons):
            raise FormalEvaluationError("economic reasons changed type")
        if item.bootstrap_resamples is not None:
            _v2_int(item.bootstrap_resamples, "economic bootstrap resamples", minimum=1)
        _v2_optional_fraction(item.centered_two_sided_p_value, "economic p")
    expected_gate_ids = (
        "bullish_20_session_fama_macbeth",
        "firm_specific_vs_global_map_paired_20_session_ic",
        "net_20_session_sleeve",
    )
    if len(report.primary_gates) != 3:
        raise FormalEvaluationError("primary gate conjunction is incomplete")
    for item, expected in zip(report.primary_gates, expected_gate_ids, strict=True):
        if (
            type(item) is not PrimaryGateSummary
            or type(item.gate_id) is not str or item.gate_id != expected
            or type(item.status) is not Disposition
            or type(item.reasons) is not tuple
            or any(type(reason) is not str for reason in item.reasons)
        ):
            raise FormalEvaluationError("primary gate topology changed")
    if type(report.disposition) is not Disposition or any(
        type(reason) is not str for reason in report.disposition_reasons
    ):
        raise FormalEvaluationError("formal disposition topology changed")
    gate_statuses = tuple(item.status for item in report.primary_gates)
    expected_disposition = _v2_conjunction_disposition(gate_statuses)
    if report.disposition is not expected_disposition:
        raise FormalEvaluationError("primary conjunction disposition changed")
    digest = _v2_digest(report)
    if report.report_sha256 != digest or report.report_id != _v2_identity(
        "arv2-formal-evaluation-report-", digest
    ):
        raise FormalEvaluationError("formal evaluation report identity changed")
    if type(report._canonical_document) is not bytes:
        raise FormalEvaluationError("formal evaluation canonical document changed type")
    if report._canonical_document != _v2_bytes(report):
        raise FormalEvaluationError("formal evaluation canonical document changed")
    return report


CAPABILITIES = MappingProxyType({
    "filesystem": False, "environment": False, "network": False,
    "provider": False, "credentials": False, "outcome_access": False,
    "quantconnect_api": False, "object_store": False,
    "result_read": False, "result_disposition": False,
    "deployment": False, "orders": False, "trading": False,
})

__all__ = (
    "ALL_CONTROL_NAMES", "AUTHORITY", "BINARY_CONTROL_NAMES",
    "BOOTSTRAP_RESAMPLES", "BOOTSTRAP_SEED_SHA256", "CAPABILITIES",
    "CONTINUOUS_CONTROL_NAMES", "COST_BPS_GRID", "CoverageSummary",
    "DESCRIPTIVE_FOLD_IDS", "DESCRIPTIVE_SLICE_ID", "Disposition",
    "EVALUATION_ID", "EconomicCostSummary", "EconomicDecision",
    "EconomicOutcomeDisposition", "EconomicSecurityOutcome", "EconomicSession",
    "EvaluationRefusal", "EvaluationRow",
    "FORMAL_FOLD_IDS", "FORMAL_SLICE_ID", "FoldSessionAxis",
    "FormalEvaluationError", "FormalEvaluationInput",
    "FormalEvaluationReport", "FormalEvaluationSessionBlock",
    "FormalEvaluationStream", "FormalEvaluationStreamingResult",
    "HORIZONS", "INPUT_SCHEMA", "IcSummary",
    "MINIMUM_SLEEVE_SIZE", "NamedBinary", "NamedDecimal",
    "OUTCOME_ONLY_CONTROL_NAMES", "PRIMARY_COST_BPS", "PRIMARY_SIZE",
    "PairedIcSummary", "PowerFloorBinding", "PrimaryGateSummary",
    "RefusalReason", "SCHEMA", "SLEEVE_HOLDING_SESSIONS", "SOURCE_VIEW_IDS",
    "STATUS", "STREAM_SCHEMA",
    "SessionPoint", "FamaMacBethSummary", "build_economic_decision",
    "build_economic_security_outcome", "build_economic_session",
    "build_evaluation_refusal",
    "build_evaluation_row", "build_formal_evaluation_input",
    "build_formal_evaluation_report", "build_formal_evaluation_session_block",
    "begin_formal_evaluation_stream", "consume_formal_evaluation_session_block",
    "finish_formal_evaluation_stream", "require_formal_evaluation_input",
    "require_formal_evaluation_report",
)
