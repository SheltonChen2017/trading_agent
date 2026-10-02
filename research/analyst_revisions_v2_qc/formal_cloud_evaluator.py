"""Cloud-safe wrapper around the exact reviewed ARV2 formal evaluator.

The QuantConnect projection uploads this module together with the *unchanged*
``formal_evaluation.py`` source.  Consequently the cloud path does not carry a
second implementation of the statistical or economic rules.  It validates
the two complete typed inputs, invokes that same evaluator, and returns one
canonical aggregate document suitable for a chunked backtest-summary receipt.

All inputs are already in memory.  This module has no filesystem, environment,
network, provider, QuantConnect API, Object Store, order, deployment, or
trading surface.
"""
from __future__ import annotations

import dataclasses
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import threading
import weakref
import zlib
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from . import formal_evaluation as _evaluation


class FormalCloudEvaluationError(ValueError):
    """Cloud evaluator inputs or aggregate identity are not exact."""


SCHEMA = "arv2-formal-cloud-evaluation-aggregate-v1"
STATUS = "aggregate_computed_no_result_read_or_action_authority"
AUTHORITY = (
    "pure_in_memory_evaluation_only_no_result_read_disposition_deployment_"
    "order_or_trading_authority"
)
TERMINAL_POLICY_ID = "arv2-terminal-payoff-benchmark-splice-v1"
FORMAL_INPUT_CONTRACT_SCHEMA = "arv2-formal-qc-formal-input-contract-v1"
STREAMED_FORMAL_CONTRACT_VARIANT = "arv2-streamed-physical-formal-input-v1"
STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA = (
    "arv2-streamed-formal-input-manifest-lineage-v1"
)
STREAMED_FORMAL_PREKNOWN_BINDINGS_SCHEMA = (
    "arv2-streamed-formal-evaluation-preknown-bindings-v1"
)
_STREAMED_FORMAL_PREKNOWN_BINDING_FIELDS = (
    "schema", "input_manifest_sha256", "production_scoring_census_id",
    "production_scoring_census_sha256", "evaluation_input_bundle_id",
    "evaluation_input_bundle_sha256", "terminal_disposition_package_id",
    "terminal_disposition_package_sha256", "preopen_control_stage_output",
    "formal_evaluator_source_sha256", "evaluator_source_closure_sha256",
    "execution_plan_sha256", "capacity_plan_sha256",
    "formal_contract_sha256", "economic_execution_binding_id",
    "economic_execution_binding_sha256", "economic_execution_definition_id",
    "economic_execution_definition_sha256",
    "economic_h20_terminal_liquidation_session", "formal_report_contract_id",
    "formal_report_contract_sha256", "formal_report_contract_artifact_sha256",
    "secondary_hypothesis_registry_sha256",
    "deflated_sharpe_trial_registry_sha256", "stock_bootstrap_seed_sha256",
)
CONTRIBUTION_SEED_SCHEMA = "arv2-formal-qc-contribution-seed-v1"
DECISION_JOIN_SCHEMA = "arv2-formal-qc-decision-market-join-v1"
ECONOMIC_JOIN_SCHEMA = "arv2-formal-qc-economic-market-join-v1"
DAILY_REQUIREMENT_SCHEMA = "arv2-formal-qc-daily-total-return-requirement-v1"
MINUTE_REQUIREMENT_SCHEMA = "arv2-formal-qc-prepublication-minute-requirement-v1"
TERMINAL_OBJECT_SCHEMA = "arv2-formal-qc-terminal-disposition-v2"
DAILY_OBSERVATION_SCHEMA = "arv2-formal-qc-daily-open-observation-v1"
MINUTE_OBSERVATION_SCHEMA = "arv2-formal-qc-prepublication-minute-observation-v1"
SCORING_CONTRACT_ID = "arv2-production-scoring-contract-05311c7a38dfab59"
SCORING_CONTRACT_SHA256 = (
    "05311c7a38dfab5976829a8e6e4cb94d0e733c35ac5904bd07ccce0be405d1b6"
)
CONTRIBUTION_STATE_DOMAIN = "arv2-formal-qc-contribution-state-v1"
MARKET_PANEL_DOMAIN = "arv2-formal-qc-shared-market-panel-v1"
MARKET_OBSERVATION_PANEL_SCHEMA = "arv2-formal-qc-market-observation-panel-v1"
MARKET_PANEL_STREAM_SCHEMA = "arv2-formal-qc-market-panel-stream-v1"
COMPACT_STREAM_SCHEMA = "arv2-formal-cloud-compact-session-stream-v1"
STREAM_INPUT_SCHEMA = "arv2-formal-cloud-stream-input-binding-v1"
TERMINAL_KEY_CENSUS_DOMAIN = "arv2-formal-terminal-key-census-v2"
STREAM_LAYOUT_ID = "arv2-formal-qc-fold-session-stream-layout-v1"
STREAMING_METHOD_ID = "arv2-formal-session-streamed-disk-mgs-qr-v1"
APPEARANCE_SEED_SEMANTICS = (
    "one_exact_single_session_seed_per_active_decision_contribution"
)
STREAM_ROLE_SORT_KEYS = {
    "formal_contract": ("singleton",),
    "contribution_seeds": (
        "first_active_session_position", "source_view_id", "fold_id",
        "security_id", "seed_id",
    ),
    "decision_joins": (
        "fold_id", "session_position", "source_view_id", "security_id",
    ),
    "economic_joins": ("fold_id", "session_position", "source_view_id"),
    "daily_requirements": ("session", "security_id", "requirement_id"),
    "minute_requirements": (
        "first_active_session_position", "publication_at_utc", "security_id",
        "requirement_id",
    ),
    "terminal_dispositions": ("slot_kind", "slot_id", "horizon"),
}
INPUT_MANIFEST_SCHEMA = "arv2-formal-qc-compact-input-manifest-v2"
HALF_LIFE_SESSIONS = 20
SOURCE_VIEW_IDS = _evaluation.SOURCE_VIEW_IDS
FORMAL_FOLD_IDS = _evaluation.FORMAL_FOLD_IDS
DESCRIPTIVE_FOLD_IDS = _evaluation.DESCRIPTIVE_FOLD_IDS
HORIZONS = _evaluation.HORIZONS
EVALUATION_ID = _evaluation.EVALUATION_ID
BOOTSTRAP_RESAMPLES = _evaluation.BOOTSTRAP_RESAMPLES
REPORT_FAMILY_IDS = (
    "event_returns_by_rating_action_horizon_and_cohort",
    "event_time_cumulative_abnormal_returns_by_rating_action",
    "information_coefficient_summary_by_horizon_and_year",
    "fama_macbeth_coefficients_hac_and_pair_counts",
    "firm_vs_global_paired_comparison_and_coverage",
    "direct_stock_gross_net_turnover_and_overlap",
    "refusal_coverage_component_and_power_accounting",
    "plot_data_percentile_vs_future_return",
    "plot_data_rolling_ic_and_sharpe",
    "plot_data_year_by_year_out_of_sample_alpha",
    "plot_data_signal_decay",
    "plot_data_turnover_vs_net_return",
    "plot_data_drawdown_and_time_underwater",
)
_REPORT_ONLY_PORTFOLIO_VARIANT_IDS = (
    "direct_stock_inverse_volatility",
    "direct_stock_score_weight",
)
GLOBAL_COMPARATOR_LEDGER_IDS = (
    "endpoint_pair_mapping",
    "active_security_date_rows",
    "common_event_components",
    "component_member_incidence",
    "score_capable_dates",
)
GLOBAL_COMPARATOR_ATTRIBUTION_RULE = (
    "one_C2_hash_occurrence_per_source_view_fold_when_its_lineage_is_present_"
    "in_any_firm_baseline_ACTIVE_H20_test_row_after_exact_firm_only_"
    "institution_security_session_daily_dedupe_and_before_global_map_"
    "exclusions;_pooled_counts_are_exact_integer_sums_of_the_six_fold_"
    "occurrences"
)
ECONOMIC_OBSERVATION_KINDS = (
    "non_economic_decision_session",
    "h20_decision_return_interval",
    "h20_runoff_return_interval",
    "terminal_liquidation_cost",
)
REPORT_FAMILY_CHUNK_SCHEMA = "arv2-formal-report-family-gzip-chunk-v1"
REPORT_FAMILY_CHUNK_ENCODING = (
    "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
)
REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA = (
    "arv2-formal-report-family-object-reference-v1"
)
FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA = (
    "arv2-formal-cloud-evaluation-output-envelope-v1"
)
REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX = "arv2/formal/output/report-families/"
MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
MAX_REPORT_FAMILY_CHUNK_COMPRESSED_BYTES = 4_200_000

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_SECURITY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,511}\Z")
_DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_NEW_YORK = ZoneInfo("America/New_York")
_CONTRACT_RECORD = {
    "schema": SCHEMA,
    "evaluation_id": EVALUATION_ID,
    "source_view_ids": list(SOURCE_VIEW_IDS),
    "formal_fold_ids": list(FORMAL_FOLD_IDS),
    "descriptive_fold_ids": list(DESCRIPTIVE_FOLD_IDS),
    "horizons": list(HORIZONS),
    "primary_horizon": 20,
    "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
    "bootstrap_seed_sha256": _evaluation.BOOTSTRAP_SEED_SHA256,
    "terminal_policy_id": TERMINAL_POLICY_ID,
    "source_view_reports_are_separate": True,
    "descriptive_slice_cannot_replace_or_rescue_formal": True,
    "raw_outcome_rows_exported": False,
    "orders_placed": 0,
}

_AGGREGATE_FIELDS = (
    "schema",
    "status",
    "authority",
    "evaluation_id",
    "formal_cloud_evaluator_contract_sha256",
    "bindings",
    "bootstrap_resamples",
    "bootstrap_seed_sha256",
    "formal_fold_ids",
    "descriptive_fold_ids",
    "descriptive_slice_cannot_replace_or_rescue_formal",
    "source_view_ids",
    "source_view_reports_are_separate",
    "horizons",
    "primary_horizon",
    "input_bindings",
    "source_view_census",
    "fold_horizon_axis_count",
    "fold_horizon_census",
    "source_view_fold_horizon_axis_count",
    "source_view_fold_horizon_census",
    "report_count",
    "reports",
    "report_disposition_counts",
    "terminal_census",
    "shared_market_panel_sha256",
    "shared_market_panel_observation_count",
    "failed_arm_omission_count",
    "silently_omitted_slot_count",
    "raw_outcome_rows_exported",
    "orders_placed",
)

_STREAMED_REPORT_AGGREGATE_FIELDS = _AGGREGATE_FIELDS + (
    "formal_report_contract_binding",
    "report_family_count",
    "report_family_chunks",
    "secondary_hypothesis_adjustment_count",
    "secondary_hypothesis_adjustments",
    "strategy_trial_report_count",
    "strategy_trial_reports",
)

_STREAMED_REPORT_ROOT_FIELDS = _AGGREGATE_FIELDS + (
    "streamed_preknown_bindings",
    "formal_report_contract_binding",
    "report_family_count",
    "report_family_object_inventory_sha256",
    "report_family_object_total_uncompressed_byte_count",
    "report_family_object_total_compressed_byte_count",
    "report_family_objects",
    "secondary_hypothesis_adjustment_count",
    "secondary_hypothesis_adjustments",
    "strategy_trial_report_count",
    "strategy_trial_reports",
)


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise FormalCloudEvaluationError(
            "cloud aggregate is not canonical JSON"
        ) from exc


def _terminal_key_census_sha256(
    keys: Sequence[Mapping[str, object]],
) -> str:
    """Hash a canonical key stream without retaining its serialized census."""

    digest = hashlib.sha256()
    digest.update(TERMINAL_KEY_CENSUS_DOMAIN.encode("ascii") + b"\0")
    prior: tuple[str, int, str] | None = None
    for raw in keys:
        row = _exact_object(
            raw, ("fold_id", "session_position", "security_id"),
            "terminal census key",
        )
        key = (
            _safe_id(row["fold_id"], "terminal census fold"),
            _count(row["session_position"], "terminal census position"),
            _security_id(row["security_id"], "terminal census security"),
        )
        if prior is not None and key <= prior:
            raise FormalCloudEvaluationError(
                "terminal census keys are duplicated or reordered"
            )
        prior = key
        payload = _canonical_bytes(row)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _duplicate_safe_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FormalCloudEvaluationError("aggregate contains a duplicate key")
        result[key] = value
    return result


def _reject_number(_value: str) -> object:
    raise FormalCloudEvaluationError("aggregate JSON floats are forbidden")


def _strict_aggregate_object(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise FormalCloudEvaluationError("aggregate must be nonempty exact bytes")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_duplicate_safe_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalCloudEvaluationError):
            raise
        raise FormalCloudEvaluationError("aggregate is not strict JSON") from exc
    if type(value) is not dict or _canonical_bytes(value) != payload:
        raise FormalCloudEvaluationError("aggregate is not canonical JSON")
    return value


FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256 = hashlib.sha256(
    _canonical_bytes(_CONTRACT_RECORD)
).hexdigest()


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalCloudEvaluationError(f"{name} is not a lowercase SHA-256")
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalCloudEvaluationError(f"{name} is not a safe identifier")
    return value


def _security_id(value: object, name: str) -> str:
    if type(value) is not str or _SECURITY_ID.fullmatch(value) is None:
        raise FormalCloudEvaluationError(f"{name} is not a permanent security id")
    return value


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FormalCloudEvaluationError(
            f"{name} is not an exact integer >= {minimum}"
        )
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalCloudEvaluationBindings:
    """Exact pre-run identities embedded in the projected cloud source."""

    input_manifest_sha256: str
    production_scoring_census_sha256: str
    evaluation_input_bundle_id: str
    evaluation_input_bundle_sha256: str
    terminal_disposition_package_sha256: str
    shared_market_panel_sha256: str
    shared_market_panel_observation_count: int
    formal_evaluator_source_sha256: str
    evaluator_source_closure_sha256: str
    execution_plan_sha256: str
    capacity_plan_sha256: str
    formal_contract_sha256: str | None = None
    economic_execution_binding_id: str | None = None
    economic_execution_binding_sha256: str | None = None
    economic_execution_definition_id: str | None = None
    economic_execution_definition_sha256: str | None = None
    economic_h20_terminal_liquidation_session: str | None = None
    formal_report_contract_id: str | None = None
    formal_report_contract_sha256: str | None = None
    formal_report_contract_artifact_sha256: str | None = None
    secondary_hypothesis_registry_sha256: str | None = None
    deflated_sharpe_trial_registry_sha256: str | None = None
    stock_bootstrap_seed_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_id(self.evaluation_input_bundle_id, "evaluation input bundle id")
        optional_values = tuple(
            getattr(self, name)
            for name in (
                "formal_contract_sha256",
                "economic_execution_binding_id",
                "economic_execution_binding_sha256",
                "economic_execution_definition_id",
                "economic_execution_definition_sha256",
                "economic_h20_terminal_liquidation_session",
                "formal_report_contract_id",
                "formal_report_contract_sha256",
                "formal_report_contract_artifact_sha256",
                "secondary_hypothesis_registry_sha256",
                "deflated_sharpe_trial_registry_sha256",
                "stock_bootstrap_seed_sha256",
            )
        )
        if any(item is not None for item in optional_values) and any(
            item is None for item in optional_values
        ):
            raise FormalCloudEvaluationError(
                "streamed evaluation binding ancestry is partial"
            )
        for field in dataclasses.fields(self):
            item = getattr(self, field.name)
            if field.name.endswith("_sha256") and item is not None:
                _sha(item, field.name)
        for name in (
            "economic_execution_binding_id",
            "economic_execution_definition_id",
            "formal_report_contract_id",
        ):
            item = getattr(self, name)
            if item is not None:
                _safe_id(item, name)
        if self.economic_h20_terminal_liquidation_session is not None:
            _iso_date(
                self.economic_h20_terminal_liquidation_session,
                "economic H20 terminal liquidation session",
            )
        _count(
            self.shared_market_panel_observation_count,
            "shared market-panel observation count",
            minimum=1,
        )

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalCloudTerminalCensus:
    """Exhaustive runtime terminal policy census, including accepted splices."""

    terminal_policy_id: str
    terminal_requirement_count: int
    terminal_payoff_count: int
    benchmark_splice_continuation_count: int
    named_terminal_refusal_count: int
    used_terminal_disposition_count: int
    unused_terminal_disposition_count: int
    silently_omitted_terminal_count: int

    def __post_init__(self) -> None:
        if self.terminal_policy_id != TERMINAL_POLICY_ID:
            raise FormalCloudEvaluationError("terminal policy changed")
        for field in dataclasses.fields(self):
            if field.name.endswith("_count"):
                _count(getattr(self, field.name), field.name)
        if (
            self.terminal_payoff_count
            + self.benchmark_splice_continuation_count
            + self.named_terminal_refusal_count
            != self.terminal_requirement_count
            or self.used_terminal_disposition_count
            + self.unused_terminal_disposition_count
            != self.terminal_requirement_count
            or self.silently_omitted_terminal_count != 0
        ):
            raise FormalCloudEvaluationError(
                "terminal requirements lack an exhaustive payoff/splice/refusal census"
            )

    @property
    def complete_without_named_refusal(self) -> bool:
        return self.named_terminal_refusal_count == 0

    def to_record(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "complete_without_named_refusal": self.complete_without_named_refusal,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalCloudCompactStream:
    """Opaque one-use handle for bounded compact-session evaluation."""

    stream_id: str
    schema: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalMarketPanelDigest:
    """Opaque bounded-memory digest for either immutable History pass."""

    digest_id: str
    schema: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalCloudEvaluationOutput:
    """Opaque one-use carrier for a root manifest and 26 family objects."""

    output_id: str
    output_sha256: str
    schema: str
    root_manifest_sha256: str
    root_manifest_byte_count: int
    bootstrap_resamples: int
    family_object_count: int
    total_uncompressed_byte_count: int
    total_compressed_byte_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class FormalCloudReportFamilyObjectDescriptor:
    """Exact read-only Object Store plan derived from an authenticated root."""

    schema: str
    role: str
    ordinal: int
    source_view_id: str
    family_id: str
    family_output_id: str
    family_output_sha256: str
    payload_schema: str
    row_count: int
    formal_cloud_evaluator_contract_sha256: str
    input_manifest_sha256: str
    formal_report_contract_sha256: str
    object_store_key_suffix: str
    uncompressed_byte_count: int
    uncompressed_sha256: str
    compressed_byte_count: int
    compressed_sha256: str
    encoding: str

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class _ReportFamilyObject:
    descriptor: dict[str, object]
    payload: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(slots=True)
class _CloudEvaluationOutputState:
    creator_pid: int
    owner_thread_id: int
    root_manifest: bytes
    family_objects: tuple[_ReportFamilyObject, ...]
    consumed: bool
    failed: bool


@dataclasses.dataclass(slots=True)
class _MarketPanelDigestState:
    creator_pid: int
    owner_thread_id: int
    expected_count: int
    count: int
    modular_sum: int
    bitwise_xor: int
    last_keys: dict[int, tuple[object, ...]]
    finished: bool
    failed: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _DirectionalEventReportObservation:
    source_view_id: str
    fold_id: str
    decision_session: date
    session_position: int
    event_id: str
    security_id: str
    common_event_component_id: str | None
    rating_action: str
    earnings_anchor_signed_session_distance: int | None
    horizon_sessions: int
    gross_security_total_return: Decimal | None
    benchmark_total_return: Decimal | None
    gross_excess_total_return: Decimal | None
    refusal_reason: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class _DecisionReportObservation:
    source_view_id: str
    fold_id: str
    decision_session: date
    session_position: int
    security_id: str
    common_event_component_id: str | None
    rating_actions: tuple[str, ...]
    earnings_anchor_signed_session_distance: int | None
    horizon_sessions: int
    firm_specific_score: Decimal | None
    global_score: Decimal | None
    gross_excess_total_return: Decimal | None
    refusal_reason: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class _SubsetFmReportObservation:
    source_view_id: str
    fold_id: str
    decision_session: date
    session_position: int
    subset_id: str
    bullish_beta: Decimal | None
    refusal_reason: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class _ReportVariantSleeve:
    remaining_intervals: int
    original_weights: tuple[tuple[str, Decimal], ...]
    active_security_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class _ReportTrialObservation:
    trial_id: str
    portfolio_variant_id: str
    cost_bps_per_side: int
    fold_id: str
    session: date
    session_position: int
    gross_portfolio_total_return: Decimal
    benchmark_total_return: Decimal
    net_portfolio_total_return: Decimal
    net_excess_daily_total_return: Decimal
    turnover: Decimal
    sleeve_security_incidence_count: int
    duplicate_sleeve_security_incidence_count: int
    terminal_liquidation: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _ReportTrialFoldCensus:
    trial_id: str
    portfolio_variant_id: str
    cost_bps_per_side: int
    fold_id: str
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


@dataclasses.dataclass(slots=True)
class _ReportVariantFoldState:
    active_sleeves: list[_ReportVariantSleeve]
    pretrade_weights: dict[str, Decimal]
    observations: list[_ReportTrialObservation]
    refusal_counts_by_session: list[
        tuple[date, tuple[tuple[str, int], ...]]
    ]
    session_count: int
    refused_session_count: int
    invested_session_count: int
    cash_sleeve_count: int
    selected_sleeve_count: int
    terminal_liquidation_turnover: Decimal
    refusal_counts: Counter[str]
    fold_state_valid: bool


@dataclasses.dataclass(slots=True)
class _CompactStreamState:
    creator_pid: int
    owner_thread_id: int
    manifest: dict[str, object]
    contract: dict[str, object]
    bindings: FormalCloudEvaluationBindings
    preknown_bindings: dict[str, object]
    axes: tuple[_evaluation.FoldSessionAxis, ...]
    economic_axes: tuple[_evaluation.EconomicObservationAxis, ...]
    power_floor: _evaluation.PowerFloorBinding
    economic_joins: dict[tuple[str, str, int], dict[str, object]]
    expected_blocks: tuple[tuple[str, str, int], ...]
    host_streams: tuple[_evaluation.FormalEvaluationStream, ...]
    next_block_index: int
    active_sleeves: dict[tuple[str, str], list[_evaluation._ActiveSleeve]]
    seeds: dict[tuple[str, str, str], list[dict[str, object]]]
    minute_requirements: dict[str, dict[str, object]]
    minute_observations: dict[str, dict[str, object]]
    minute_requirement_commitments: dict[str, str]
    minute_observation_commitments: dict[str, str]
    terminal_dispositions: dict[
        tuple[str, str, int | None], dict[str, object]
    ]
    seen_seed_ids: set[str]
    seen_terminal_keys: set[tuple[str, str, int | None]]
    terminal_counts: Counter[str]
    terminal_attribution: dict[str, Counter[object]]
    partition_counts: dict[str, Counter[object]]
    partition_hashes: dict[str, object]
    last_partition_keys: dict[str, tuple[str, int, str] | None]
    directional_event_report_observations: list[
        _DirectionalEventReportObservation
    ]
    decision_report_observations: list[_DecisionReportObservation]
    subset_fm_report_observations: list[_SubsetFmReportObservation]
    variant_fold_states: dict[
        tuple[str, str, str], _ReportVariantFoldState
    ]
    finished: bool
    failed: bool


_HASH_STATE_TYPE = type(hashlib.sha256())
_EVALUATION_STATE_DATACLASS_TYPES = tuple(
    value
    for value in tuple(vars(_evaluation).values())
    if isinstance(value, type) and dataclasses.is_dataclass(value)
)
_CLOUD_STATE_DATACLASS_TYPES = (
    FormalCloudEvaluationBindings,
    FormalCloudTerminalCensus,
    FormalCloudCompactStream,
    FormalMarketPanelDigest,
    FormalCloudEvaluationOutput,
    FormalCloudReportFamilyObjectDescriptor,
    _ReportFamilyObject,
    _CloudEvaluationOutputState,
    _MarketPanelDigestState,
    _DirectionalEventReportObservation,
    _DecisionReportObservation,
    _SubsetFmReportObservation,
    _ReportVariantSleeve,
    _ReportTrialObservation,
    _ReportTrialFoldCensus,
    _ReportVariantFoldState,
    _CompactStreamState,
    *_EVALUATION_STATE_DATACLASS_TYPES,
)


def _cloud_state_canonical(
    value: object,
    memo: dict[int, int] | None = None,
    *,
    _dataclass_types: tuple[type[object], ...] = _CLOUD_STATE_DATACLASS_TYPES,
    _hash_type: type[object] = _HASH_STATE_TYPE,
) -> object:
    """Return an exact, topology-sensitive form of private mutable state."""

    if memo is None:
        memo = {}
    value_type = type(value)
    if value is None or value_type in (str, int, bool):
        return value
    if value_type is bytes:
        return {"bytes": base64.b64encode(value).decode("ascii")}
    if value_type is Decimal:
        if not value.is_finite():
            raise FormalCloudEvaluationError("cloud authority Decimal changed")
        return {"decimal": str(value)}
    if value_type is Fraction:
        return {"fraction": [value.numerator, value.denominator]}
    if value_type is date:
        return {"date": value.isoformat()}
    if value_type is datetime:
        return {"datetime": value.isoformat()}
    if value_type is time:
        return {"time": value.isoformat()}
    if value_type is _hash_type:
        return {
            "hash": value.copy().hexdigest(),
            "identity": id(value),
            "name": value.name,
        }
    identity = id(value)
    if identity in memo:
        return {"reference": memo[identity]}
    memo[identity] = len(memo)
    if value_type in (tuple, list):
        return {
            "container": value_type.__name__,
            "identity": identity,
            "items": [_cloud_state_canonical(item, memo) for item in value],
        }
    if value_type in (set, frozenset):
        items = [_cloud_state_canonical(item, memo) for item in value]
        items.sort(
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            )
        )
        return {
            "container": value_type.__name__,
            "identity": identity,
            "items": items,
        }
    if value_type in (dict, Counter, defaultdict):
        items = [
            [_cloud_state_canonical(key, memo), _cloud_state_canonical(item, memo)]
            for key, item in value.items()
        ]
        items.sort(
            key=lambda item: json.dumps(
                item[0], sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            )
        )
        return {
            "container": value_type.__name__,
            "identity": identity,
            "items": items,
        }
    if value_type in _dataclass_types:
        return {
            "dataclass": value_type.__module__ + "." + value_type.__qualname__,
            "identity": identity,
            "fields": {
                field.name: _cloud_state_canonical(getattr(value, field.name), memo)
                for field in dataclasses.fields(value)
            },
        }
    raise FormalCloudEvaluationError("cloud authority state changed type")


def _cloud_state_sha256(value: object) -> str:
    """Fingerprint exact state without materializing a second full JSON tree."""

    digest = hashlib.sha256()
    memo: dict[int, int] = {}

    def emit(payload: bytes) -> None:
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)

    def visit(item: object) -> None:
        item_type = type(item)
        emit((item_type.__module__ + "." + item_type.__qualname__).encode("ascii"))
        if item is None:
            return
        if item_type is str:
            emit(item.encode("utf-8"))
            return
        if item_type is bytes:
            emit(item)
            return
        if item_type in (int, bool, Decimal, Fraction):
            emit(str(item).encode("ascii"))
            return
        if item_type in (date, datetime, time):
            emit(item.isoformat().encode("ascii"))
            return
        if item_type is _HASH_STATE_TYPE:
            emit(str(id(item)).encode("ascii"))
            emit(item.copy().digest())
            emit(item.name.encode("ascii"))
            return
        identity = id(item)
        if identity in memo:
            emit(b"reference")
            emit(str(memo[identity]).encode("ascii"))
            return
        memo[identity] = len(memo)
        emit(str(identity).encode("ascii"))
        if item_type in (tuple, list):
            emit(str(len(item)).encode("ascii"))
            for child in item:
                visit(child)
            return
        if item_type in (set, frozenset):
            # Internal set members are exact immutable scalars/tuples.  The
            # repr ordering is process-local only; it is never persisted.
            ordered = sorted(item, key=lambda child: (type(child).__name__, repr(child)))
            emit(str(len(ordered)).encode("ascii"))
            for child in ordered:
                visit(child)
            return
        if item_type in (dict, Counter, defaultdict):
            emit(str(len(item)).encode("ascii"))
            for key, child in item.items():
                visit(key)
                visit(child)
            return
        if item_type in _CLOUD_STATE_DATACLASS_TYPES:
            for field in dataclasses.fields(item):
                emit(field.name.encode("ascii"))
                visit(getattr(item, field.name))
            return
        raise FormalCloudEvaluationError("cloud authority state changed type")

    try:
        visit(value)
    except FormalCloudEvaluationError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise FormalCloudEvaluationError(
            "cloud authority state is not canonical"
        ) from exc
    return digest.hexdigest()


def _build_cloud_stream_authorities():
    """Keep one-use authority state outside the module namespace.

    The returned functions are deliberately narrow: no caller can obtain or
    replace either registry.  In particular, assigning a look-alike public
    ``_COMPACT_STREAMS`` or ``_MARKET_PANEL_DIGESTS`` dictionary cannot mint,
    unlock, or reseal a handle after outcome-bearing state has been consumed.
    """

    error_type = FormalCloudEvaluationError
    state_fingerprint = _cloud_state_sha256
    make_reference = weakref.ref
    get_frame = sys._getframe
    get_pid = os.getpid
    real_path = os.path.realpath
    new_lock = threading.RLock
    module_globals_identity = id(globals())

    # Every registry replacement is atomic and the authority-bearing closure
    # contains no mutable container that reflection can edit in place.
    compact_streams: tuple[tuple[object, ...], ...] = ()
    market_panel_digests: tuple[tuple[object, ...], ...] = ()
    evaluation_outputs: tuple[tuple[object, ...], ...] = ()
    producer_provenance: tuple[tuple[tuple[object, ...], ...], ...] = ()
    transition_provenance: tuple[tuple[tuple[object, ...], ...], ...] = ()
    authority_lock = new_lock()
    authority_pid = get_pid()
    module_name = __name__
    module_path = real_path(__file__)
    authority_module = sys.modules.get(module_name)

    missing_closure_value = object()

    def caller_is_exact(
        alternatives: tuple[tuple[tuple[object, ...], ...], ...],
    ) -> bool:
        frame = None
        try:
            frame = get_frame(2)
            if (
                get_pid() != authority_pid
                or authority_module is None
                or sys.modules.get(module_name) is not authority_module
            ):
                return False
            for chain in alternatives:
                current = frame
                matched = True
                for position, provenance in enumerate(chain):
                    (
                        expected_function,
                        expected_code,
                        expected_name,
                        expected_global_bindings,
                        expected_closure,
                    ) = provenance
                    if (
                        current is None
                        or current.f_code is not expected_code
                        or current.f_code.co_name != expected_name
                        or id(current.f_globals) != module_globals_identity
                        or vars(authority_module) is not current.f_globals
                        or current.f_globals.get("__name__") != module_name
                        or real_path(
                            current.f_globals.get("__file__", "")
                        ) != module_path
                        or expected_function.__code__ is not expected_code
                        or expected_function.__globals__ is not current.f_globals
                        or expected_function.__name__ != expected_name
                        or any(
                            expected_function.__globals__.get(
                                name, missing_closure_value
                            ) is not expected
                            or current.f_globals.get(
                                name, missing_closure_value
                            ) is not expected
                            for name, expected in expected_global_bindings
                        )
                        or tuple(expected_function.__code__.co_freevars)
                        != tuple(item[0] for item in expected_closure)
                        or len(expected_function.__closure__ or ())
                        != len(expected_closure)
                        or any(
                            cell.cell_contents is not expected
                            for cell, (_name, expected) in zip(
                                expected_function.__closure__ or (),
                                expected_closure,
                                strict=True,
                            )
                        )
                        or any(
                            current.f_locals.get(
                                name, missing_closure_value
                            ) is not expected
                            for name, expected in expected_closure
                        )
                        or (
                            position == len(chain) - 1
                            and current.f_globals.get(expected_name)
                            is not expected_function
                        )
                    ):
                        matched = False
                        break
                    current = current.f_back
                if matched:
                    return True
            return False
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            return False
        finally:
            del frame

    def find_entry(
        registry: tuple[tuple[object, ...], ...], identity: int,
    ) -> tuple[object, ...] | None:
        matches = tuple(item for item in registry if item[0] == identity)
        return matches[0] if len(matches) == 1 else None

    def forget_compact(
        identity: int,
        reference: weakref.ReferenceType[FormalCloudCompactStream],
    ) -> None:
        nonlocal compact_streams
        with authority_lock:
            current = find_entry(compact_streams, identity)
            if current is not None and current[1] is reference:
                compact_streams = tuple(
                    item for item in compact_streams if item is not current
                )

    def register_compact(
        value: FormalCloudCompactStream,
        static: bytes,
        state: _CompactStreamState,
    ) -> None:
        nonlocal compact_streams
        if not caller_is_exact(producer_provenance):
            raise error_type(
                "compact evaluation stream registrar caller changed"
            )
        identity = id(value)
        reference = make_reference(
            value,
            lambda ref, key=identity: forget_compact(key, ref),
        )
        entry = (
            identity, reference, static, state, state_fingerprint(state),
        )
        with authority_lock:
            if find_entry(compact_streams, identity) is not None:
                raise error_type(
                    "compact evaluation stream identity was already registered"
                )
            compact_streams = (*compact_streams, entry)

    def lookup_compact(
        value: FormalCloudCompactStream,
    ) -> tuple[bytes, _CompactStreamState] | None:
        with authority_lock:
            registered = find_entry(compact_streams, id(value))
        if (
            registered is None
            or registered[1]() is not value
            or registered[4] != state_fingerprint(registered[3])
        ):
            return None
        return registered[2], registered[3]

    def update_compact(
        value: FormalCloudCompactStream,
        state: _CompactStreamState,
    ) -> None:
        nonlocal compact_streams
        if not caller_is_exact(transition_provenance):
            raise error_type(
                "compact evaluation stream transition caller changed"
            )
        with authority_lock:
            current = find_entry(compact_streams, id(value))
            if current is None or current[1]() is not value or current[3] is not state:
                raise error_type(
                    "compact evaluation stream authority changed"
                )
            replacement = (*current[:4], state_fingerprint(state))
            compact_streams = tuple(
                replacement if item is current else item for item in compact_streams
            )

    def forget_panel(
        identity: int,
        reference: weakref.ReferenceType[FormalMarketPanelDigest],
    ) -> None:
        nonlocal market_panel_digests
        with authority_lock:
            current = find_entry(market_panel_digests, identity)
            if current is not None and current[1] is reference:
                market_panel_digests = tuple(
                    item for item in market_panel_digests if item is not current
                )

    def register_panel(
        value: FormalMarketPanelDigest,
        static: bytes,
        state: _MarketPanelDigestState,
    ) -> None:
        nonlocal market_panel_digests
        if not caller_is_exact(producer_provenance):
            raise error_type(
                "market-panel digest registrar caller changed"
            )
        identity = id(value)
        reference = make_reference(
            value,
            lambda ref, key=identity: forget_panel(key, ref),
        )
        entry = (
            identity, reference, static, state, state_fingerprint(state),
        )
        with authority_lock:
            if find_entry(market_panel_digests, identity) is not None:
                raise error_type(
                    "market-panel digest identity was already registered"
                )
            market_panel_digests = (*market_panel_digests, entry)

    def lookup_panel(
        value: FormalMarketPanelDigest,
    ) -> tuple[bytes, _MarketPanelDigestState] | None:
        with authority_lock:
            registered = find_entry(market_panel_digests, id(value))
        if (
            registered is None
            or registered[1]() is not value
            or registered[4] != state_fingerprint(registered[3])
        ):
            return None
        return registered[2], registered[3]

    def update_panel(
        value: FormalMarketPanelDigest,
        state: _MarketPanelDigestState,
    ) -> None:
        nonlocal market_panel_digests
        if not caller_is_exact(transition_provenance):
            raise error_type(
                "market-panel digest transition caller changed"
            )
        with authority_lock:
            current = find_entry(market_panel_digests, id(value))
            if current is None or current[1]() is not value or current[3] is not state:
                raise error_type(
                    "market-panel digest authority changed"
                )
            replacement = (*current[:4], state_fingerprint(state))
            market_panel_digests = tuple(
                replacement if item is current else item
                for item in market_panel_digests
            )

    def forget_output(
        identity: int,
        reference: weakref.ReferenceType[FormalCloudEvaluationOutput],
    ) -> None:
        nonlocal evaluation_outputs
        with authority_lock:
            current = find_entry(evaluation_outputs, identity)
            if current is not None and current[1] is reference:
                evaluation_outputs = tuple(
                    item for item in evaluation_outputs if item is not current
                )

    def register_output(
        value: FormalCloudEvaluationOutput,
        static: bytes,
        state: _CloudEvaluationOutputState,
    ) -> None:
        nonlocal evaluation_outputs
        if not caller_is_exact(producer_provenance):
            raise error_type(
                "cloud evaluation output registrar caller changed"
            )
        identity = id(value)
        reference = make_reference(
            value,
            lambda ref, key=identity: forget_output(key, ref),
        )
        entry = (
            identity, reference, static, state, state_fingerprint(state),
        )
        with authority_lock:
            if find_entry(evaluation_outputs, identity) is not None:
                raise error_type(
                    "cloud evaluation output identity was already registered"
                )
            evaluation_outputs = (*evaluation_outputs, entry)

    def lookup_output(
        value: FormalCloudEvaluationOutput,
    ) -> tuple[bytes, _CloudEvaluationOutputState] | None:
        with authority_lock:
            registered = find_entry(evaluation_outputs, id(value))
        if (
            registered is None
            or registered[1]() is not value
            or registered[4] != state_fingerprint(registered[3])
        ):
            return None
        return registered[2], registered[3]

    def update_output(
        value: FormalCloudEvaluationOutput,
        state: _CloudEvaluationOutputState,
    ) -> None:
        nonlocal evaluation_outputs
        if not caller_is_exact(transition_provenance):
            raise error_type(
                "cloud evaluation output transition caller changed"
            )
        with authority_lock:
            current = find_entry(evaluation_outputs, id(value))
            if current is None or current[1]() is not value or current[3] is not state:
                raise error_type(
                    "cloud evaluation output authority changed"
                )
            replacement = (*current[:4], state_fingerprint(state))
            evaluation_outputs = tuple(
                replacement if item is current else item
                for item in evaluation_outputs
            )

    def configure_callers(
        producers: tuple[tuple[object, ...], ...],
        transitions: tuple[tuple[object, ...], ...],
    ) -> None:
        nonlocal producer_provenance, transition_provenance
        function_type = type(configure_callers)
        if producer_provenance or transition_provenance:
            raise error_type(
                "cloud authority caller provenance is already configured"
            )
        if (
            type(producers) is not tuple
            or len(producers) != 3
            or type(transitions) is not tuple
            or len(transitions) != 6
        ):
            raise error_type(
                "cloud authority caller provenance changed"
            )
        for chain in (*producers, *transitions):
            if type(chain) is not tuple or len(chain) < 2:
                raise error_type(
                    "cloud authority caller provenance changed"
                )
            for item in chain:
                if (
                    type(item) is not function_type
                    or id(item.__globals__) != module_globals_identity
                    or item.__module__ != module_name
                    or real_path(item.__code__.co_filename) != module_path
                ):
                    raise error_type(
                        "cloud authority caller provenance changed"
                    )
        try:
            provenance = tuple(
                tuple(
                    (
                        item,
                        item.__code__,
                        item.__name__,
                        tuple(
                            (
                                name,
                                item.__globals__.get(
                                    name, missing_closure_value
                                ),
                            )
                            for name in item.__code__.co_names
                        ),
                        tuple(
                            (name, cell.cell_contents)
                            for name, cell in zip(
                                item.__code__.co_freevars,
                                item.__closure__ or (),
                                strict=True,
                            )
                        ),
                    )
                    for item in chain
                )
                for chain in (*producers, *transitions)
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise error_type(
                "cloud authority caller provenance changed"
            ) from exc
        producer_provenance = provenance[:len(producers)]
        transition_provenance = provenance[len(producers):]

    def reset_after_fork() -> None:
        nonlocal compact_streams, market_panel_digests, evaluation_outputs
        nonlocal authority_lock, authority_pid
        compact_streams = ()
        market_panel_digests = ()
        evaluation_outputs = ()
        authority_lock = new_lock()
        authority_pid = get_pid()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    return (
        register_compact,
        lookup_compact,
        update_compact,
        register_panel,
        lookup_panel,
        update_panel,
        register_output,
        lookup_output,
        update_output,
        configure_callers,
    )


(
    _register_compact_stream_authority,
    _lookup_compact_stream_authority,
    _update_compact_stream_authority,
    _register_market_panel_authority,
    _lookup_market_panel_authority,
    _update_market_panel_authority,
    _register_cloud_evaluation_output_authority,
    _lookup_cloud_evaluation_output_authority,
    _update_cloud_evaluation_output_authority,
    _configure_cloud_stream_authority_callers,
) = _build_cloud_stream_authorities()
del _build_cloud_stream_authorities


def _exact_object(
    value: object, fields: tuple[str, ...], name: str
) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(fields):
        raise FormalCloudEvaluationError(f"{name} fields changed")
    return value


def _exact_list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise FormalCloudEvaluationError(f"{name} is not an exact list")
    return value


def _require_canonical_row_order(rows: list[object], name: str) -> None:
    if rows != sorted(rows, key=_canonical_bytes):
        raise FormalCloudEvaluationError(f"{name} are not in canonical shard order")


def _role_row_key(role: str, value: object) -> tuple[object, ...]:
    if type(value) is not dict:
        raise FormalCloudEvaluationError(f"{role} row changed type")
    try:
        if role == "formal_contract":
            return (0,)
        if role == "contribution_seeds":
            intervals = value["active_intervals"]
            return (
                min(item[0] for item in intervals),
                SOURCE_VIEW_IDS.index(value["source_view_id"]),
                FORMAL_FOLD_IDS.index(value["fold_id"]),
                value["security_id"], value["seed_id"],
            )
        if role == "decision_joins":
            return (
                FORMAL_FOLD_IDS.index(value["fold_id"]),
                value["session_position"],
                SOURCE_VIEW_IDS.index(value["source_view_id"]),
                value["security_id"],
            )
        if role == "economic_joins":
            return (
                FORMAL_FOLD_IDS.index(value["fold_id"]),
                value["session_position"],
                SOURCE_VIEW_IDS.index(value["source_view_id"]),
            )
        if role == "daily_requirements":
            return (value["session"], value["security_id"], value["requirement_id"])
        if role == "minute_requirements":
            return (
                value["first_active_session_position"],
                value["publication_at_utc"], value["security_id"],
                value["requirement_id"],
            )
        if role == "terminal_dispositions":
            return (
                value["slot_kind"], value["slot_id"],
                -1 if value["horizon"] is None else value["horizon"],
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError(f"{role} stream key changed") from exc
    raise FormalCloudEvaluationError("unknown compact shard role")


def _require_role_row_order(rows: list[object], role: str) -> None:
    encoded = [_canonical_bytes(item) for item in rows]
    if len(set(encoded)) != len(encoded) or rows != sorted(
        rows, key=lambda item: _role_row_key(role, item)
    ):
        raise FormalCloudEvaluationError(
            f"{role} rows violate the frozen stream layout"
        )


def _iso_date(value: object, name: str) -> date:
    if type(value) is not str:
        raise FormalCloudEvaluationError(f"{name} is not an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FormalCloudEvaluationError(f"{name} is not an ISO date") from exc
    if parsed.isoformat() != value:
        raise FormalCloudEvaluationError(f"{name} is not a canonical ISO date")
    return parsed


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise FormalCloudEvaluationError(f"{name} is not a UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FormalCloudEvaluationError(f"{name} is not a UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FormalCloudEvaluationError(f"{name} is not UTC")
    return parsed


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    if type(value) is not str or _DECIMAL_TEXT.fullmatch(value) is None:
        raise FormalCloudEvaluationError(f"{name} is not canonical Decimal text")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise FormalCloudEvaluationError(f"{name} is not a Decimal") from exc
    if not result.is_finite() or format(result, "f") != value:
        raise FormalCloudEvaluationError(f"{name} is not canonical Decimal text")
    if positive and result <= 0:
        raise FormalCloudEvaluationError(f"{name} must be positive")
    return result


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _context() -> Context:
    return Context(prec=50, rounding=ROUND_HALF_EVEN)


def _decay(age: int) -> Decimal:
    _count(age, "contribution age")
    with localcontext(_context()):
        whole, remainder = divmod(age, HALF_LIFE_SESSIONS)
        weight = Decimal("0.5") ** whole
        if remainder:
            exponent = -Decimal(remainder) / Decimal(HALF_LIFE_SESSIONS)
            weight *= (exponent * Decimal(2).ln()).exp()
        return +weight


def _identified(prefix: str, schema: str, record: Mapping[str, object]) -> tuple[str, str]:
    digest = hashlib.sha256(_canonical_bytes({"schema": schema, **record})).hexdigest()
    return prefix + digest[:24], digest


def build_daily_market_requirement_id(*, security_id: str, session: str) -> str:
    _security_id(security_id, "daily requirement security")
    _iso_date(session, "daily requirement session")
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "domain": DAILY_REQUIREMENT_SCHEMA,
                "observation": "session_open_total_return_adjusted",
                "security_id": security_id,
                "session": session,
            }
        )
    ).hexdigest()
    return "arv2-daily-requirement-" + digest


def build_minute_market_requirement_id(
    *, security_id: str, publication_at_utc: str
) -> str:
    _security_id(security_id, "minute requirement security")
    _utc(publication_at_utc, "minute requirement publication")
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "domain": MINUTE_REQUIREMENT_SCHEMA,
                "price_selection": (
                    "last_tradable_minute_strictly_before_publication"
                ),
                "publication_at_utc": publication_at_utc,
                "security_id": security_id,
            }
        )
    ).hexdigest()
    return "arv2-minute-requirement-" + digest


def build_decision_terminal_slot_id(*, decision_id: str, horizon: int) -> str:
    _safe_id(decision_id, "decision terminal parent")
    if type(horizon) is not int or horizon not in HORIZONS:
        raise FormalCloudEvaluationError("decision terminal horizon changed")
    digest = hashlib.sha256(
        _canonical_bytes(
            {"domain": "arv2-decision-terminal-slot-v1", "decision_id": decision_id,
             "horizon": horizon}
        )
    ).hexdigest()
    return "arv2-decision-terminal-slot-" + digest


def build_economic_terminal_slot_id(
    *, view_id: str, fold_id: str, session_position: int, security_id: str
) -> str:
    for value, name in ((view_id, "view"), (fold_id, "fold")):
        _safe_id(value, name)
    _security_id(security_id, "economic terminal security")
    _count(session_position, "economic terminal session position")
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "domain": "arv2-economic-terminal-slot-v1",
                "fold_id": fold_id,
                "security_id": security_id,
                "session_position": session_position,
                "view_id": view_id,
            }
        )
    ).hexdigest()
    return "arv2-economic-terminal-slot-" + digest


_FORMAL_CONTRACT_FIELDS = (
    "schema", "evaluation_id", "evaluation_input_bundle_id",
    "evaluation_input_bundle_sha256", "production_scoring_census_id",
    "production_scoring_census_sha256", "scoring_contract_id",
    "scoring_contract_sha256", "scoring_result_bindings",
    "production_truth_artifact_id", "production_truth_artifact_sha256",
    "preopen_control_stage_output", "formal_evaluator_source_sha256",
    "accepted_risk", "power_floor", "terminal_package_id",
    "terminal_package_sha256", "terminal_census", "source_view_partitions",
    "stream_layout",
)

_STREAMED_FORMAL_CONTRACT_FIELDS = (
    "schema", "contract_variant", "evaluation_id", "streamed_scoring_id",
    "streamed_scoring_sha256", "scoring_contract_id",
    "scoring_contract_sha256", "scoring_result_bindings",
    "paired_bootstrap_authority", "fold_horizon_axes",
    "global_comparator_fold_coverages",
    "global_comparator_pooled_coverages",
    "physical_preopen_archive", "production_evidence_receipt",
    "accepted_risk", "formal_power", "power_floor",
    "economic_execution_binding", "economic_execution_definition",
    "formal_report_contract", "terminal_package_id",
    "terminal_package_sha256", "terminal_policy_id", "terminal_census",
    "source_view_partitions", "stream_layout", "benchmark_security_id",
    "calculation_as_of_date", "streaming_method_id",
    "appearance_seed_semantics", "legacy_six_result_materialization_used",
    "outcome_or_qc_action_authorized",
)

_STREAMED_FORMAL_INPUT_LINEAGE_FIELDS = (
    "schema", "contract_variant", "formal_contract_sha256",
    "streamed_input_candidate_id", "streamed_input_candidate_sha256",
    "streamed_scoring_id", "streamed_scoring_sha256",
    "physical_formal_shard_archive_id",
    "physical_formal_shard_archive_sha256", "physical_preopen_archive_id",
    "physical_preopen_archive_sha256", "preopen_acquisition_id",
    "preopen_acquisition_sha256", "production_evidence_receipt_id",
    "production_evidence_receipt_sha256", "accepted_risk_sha256",
    "formal_power_sha256", "power_floor_sha256",
    "economic_execution_binding_id", "economic_execution_binding_sha256",
    "economic_execution_definition_id",
    "economic_execution_definition_sha256",
    "economic_execution_definition_payload_sha256",
    "economic_execution_binding_record_sha256",
    "economic_execution_definition_record_sha256",
    "economic_h20_terminal_liquidation_session",
    "formal_report_contract_id", "formal_report_contract_sha256",
    "formal_report_contract_artifact_sha256",
    "formal_report_contract_economic_execution_definition_sha256",
    "formal_report_contract_secondary_hypothesis_registry_sha256",
    "formal_report_contract_deflated_sharpe_trial_registry_sha256",
    "formal_report_contract_stock_bootstrap_seed_sha256",
    "formal_report_contract_report_family_count",
    "formal_report_contract_secondary_hypothesis_count",
    "formal_report_contract_strategy_trial_count",
    "formal_report_contract_record_sha256",
    "scoring_result_bindings_sha256", "paired_bootstrap_authority_sha256",
    "fold_horizon_axes_sha256", "terminal_package_id",
    "terminal_package_sha256", "terminal_census_sha256",
    "source_view_partitions_sha256", "production_input_package",
    "preopen_control_stage_output", "formal_evaluator_source_sha256",
    "benchmark_security_id", "calculation_as_of_date",
)

_DECISION_FIELDS = (
    "schema", "decision_id", "decision_lineage_sha256", "source_view_id",
    "fold_id", "decision_session", "session_position", "security_id",
    "disposition", "scoring_disposition", "source_row_sha256",
    "scoring_result_id", "scoring_result_sha256", "scoring_contract_id",
    "scoring_contract_sha256", "industry_id", "common_event_component_id",
    "structural_zero", "firm_specific_score", "global_score",
    "continuous_controls", "binary_controls", "realized_volatility_60d",
    "earnings_anchor_signed_session_distance", "contribution_count",
    "contribution_state_sha256", "entry_daily_requirement_id",
    "benchmark_entry_daily_requirement_id", "horizon_exits",
)

_SEED_FIELDS = (
    "schema", "seed_id", "seed_sha256", "source_view_id", "fold_id",
    "security_id", "representative_c2_row_sha256", "linked_c2_row_sha256s",
    "representative_provider_event_id", "institution_id", "common_event_id",
    "rating_action", "publication_at_utc", "minute_requirement_id", "eligible_session",
    "eligible_session_position", "base_absolute_firm_weight", "active_intervals",
)

_ECONOMIC_FIELDS = (
    "schema", "source_view_id", "fold_id", "session", "session_position",
    "next_session", "next_session_position", "source_lineage_sha256",
)
_STREAMED_ECONOMIC_FIELDS = (
    "schema", "source_view_id", "fold_id", "session", "session_position",
    "next_session", "next_session_position", "h20_decision_eligible",
    "economic_observation_kind",
    "source_lineage_sha256",
)

_DAILY_REQUIREMENT_FIELDS = (
    "schema", "requirement_id", "security_id", "session",
)

_MINUTE_REQUIREMENT_FIELDS = (
    "schema", "requirement_id", "security_id", "publication_at_utc",
    "first_active_session_position", "last_active_session_position",
)

_TERMINAL_FIELDS = (
    "schema", "slot_kind", "slot_id", "horizon", "disposition",
    "stock_return", "reason", "terminal_lineage_sha256", "available_at_utc",
)


def _artifact_binding_record(value: object, name: str) -> dict[str, object]:
    record = _exact_object(
        value,
        ("artifact_id", "content_sha256", "artifact_sha256", "byte_count"),
        name,
    )
    _safe_id(record["artifact_id"], f"{name} artifact id")
    _sha(record["content_sha256"], f"{name} content hash")
    _sha(record["artifact_sha256"], f"{name} artifact hash")
    _count(record["byte_count"], f"{name} byte count", minimum=1)
    return record


def _validate_scoring_result_bindings(
    contract: Mapping[str, object],
) -> None:
    result_bindings = _exact_list(
        contract["scoring_result_bindings"], "scoring result bindings"
    )
    if len(result_bindings) != 6:
        raise FormalCloudEvaluationError("formal contract lacks six scoring results")
    observed_folds = []
    for item in result_bindings:
        binding = _exact_object(
            item,
            ("fold_id", "result_id", "result_sha256", "precontrol_batch_id",
             "precontrol_batch_sha256", "model_sha256s"),
            "scoring result binding",
        )
        observed_folds.append(_safe_id(binding["fold_id"], "scoring fold"))
        for name in ("result_id", "precontrol_batch_id"):
            _safe_id(binding[name], name)
        for name in ("result_sha256", "precontrol_batch_sha256"):
            _sha(binding[name], name)
        models = _exact_list(binding["model_sha256s"], "model hashes")
        if len(models) != 2:
            raise FormalCloudEvaluationError("scoring binding lacks two models")
        for item_hash in models:
            _sha(item_hash, "model hash")
    if tuple(observed_folds) != FORMAL_FOLD_IDS:
        raise FormalCloudEvaluationError("scoring results are omitted or reordered")


def _validate_stream_layout(contract: Mapping[str, object]) -> None:
    layout = _exact_object(
        contract["stream_layout"],
        ("layout_id", "role_sort_keys",
         "session_or_market_day_blocks_never_split_across_shards",
         "formal_contract_and_economic_axis_are_bounded_headers",
         "terminal_dispositions_are_the_actual_lifecycle_subset",
         "market_observation_collection_passes",
         "maximum_horizon_session_lookahead",
         "second_pass_rederives_observations",
         "terminal_subset_is_capacity_bounded_header"),
        "formal stream layout",
    )
    expected_sort_keys = {
        role: list(fields) for role, fields in STREAM_ROLE_SORT_KEYS.items()
    }
    if (
        layout["layout_id"] != STREAM_LAYOUT_ID
        or layout["role_sort_keys"] != expected_sort_keys
        or layout["session_or_market_day_blocks_never_split_across_shards"]
        is not True
        or layout["formal_contract_and_economic_axis_are_bounded_headers"]
        is not True
        or layout["terminal_dispositions_are_the_actual_lifecycle_subset"]
        is not True
        or layout["market_observation_collection_passes"] != 2
        or layout["maximum_horizon_session_lookahead"] != 60
        or layout["second_pass_rederives_observations"] is not True
        or layout["terminal_subset_is_capacity_bounded_header"] is not True
    ):
        raise FormalCloudEvaluationError("formal stream layout changed")


def _validate_paired_bootstrap_authority(
    contract: Mapping[str, object],
) -> dict[str, object]:
    authority = _exact_object(
        contract["paired_bootstrap_authority"],
        (
            "schema", "global_rating_map_id", "global_rating_map_sha256",
            "matched_comparison_contract_id",
            "matched_comparison_contract_sha256", "successor_stock_spec_id",
            "successor_stock_spec_sha256", "evaluation_id", "seed_record",
            "seed_record_sha256", "fold_axis_summaries",
        ),
        "paired bootstrap authority",
    )
    seed = _exact_object(
        authority["seed_record"],
        (
            "domain", "successor_stock_spec_sha256",
            "matched_row_contract_sha256", "global_rating_map_sha256",
            "fold_manifest_sha256", "evaluation_id", "sampler_version",
        ),
        "paired bootstrap seed record",
    )
    expected_seed = dict(_evaluation.PAIRED_BOOTSTRAP_SEED_RECORD)
    if (
        authority["schema"] != "arv2-streamed-paired-bootstrap-authority-v1"
        or authority["evaluation_id"] != EVALUATION_ID
        or seed != expected_seed
        or authority["seed_record_sha256"]
        != _evaluation.BOOTSTRAP_SEED_SHA256
        or hashlib.sha256(_canonical_bytes(seed)).hexdigest()
        != authority["seed_record_sha256"]
    ):
        raise FormalCloudEvaluationError(
            "paired bootstrap seed differs from the accepted global contract"
        )
    identity_fields = (
        (
            "global_rating_map_id", "global_rating_map_sha256",
            "arv2-global-rating-map-", seed["global_rating_map_sha256"],
        ),
        (
            "matched_comparison_contract_id",
            "matched_comparison_contract_sha256", "arv2-global-matched-",
            seed["matched_row_contract_sha256"],
        ),
        (
            "successor_stock_spec_id", "successor_stock_spec_sha256",
            "arv2-stock-historical-successor-",
            seed["successor_stock_spec_sha256"],
        ),
    )
    for id_name, hash_name, prefix, expected_hash in identity_fields:
        _safe_id(authority[id_name], id_name)
        _sha(authority[hash_name], hash_name)
        if (
            authority[hash_name] != expected_hash
            or authority[id_name] != prefix + expected_hash[:16]
        ):
            raise FormalCloudEvaluationError(
                "paired bootstrap parent identity changed"
            )
    supplied = _exact_list(
        authority["fold_axis_summaries"],
        "paired bootstrap fold-axis summaries",
    )
    expected_summaries = []
    h20 = {
        fold: (start, end, count, digest)
        for fold, horizon, start, end, count, digest
        in _evaluation.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES
        if horizon == 20
    }
    for fold, count, digest, allowed, blocks in (
        _evaluation.PAIRED_BOOTSTRAP_FOLD_AXIS_SUMMARIES
    ):
        start, end, axis_count, axis_digest = h20[fold]
        if axis_count != count or axis_digest != digest:
            raise FormalCloudEvaluationError(
                "paired bootstrap and reviewed H20 axes disagree"
            )
        expected_summaries.append({
            "fold_id": f"{fold}-h20",
            "test_start_inclusive": start,
            "test_end_exclusive": end,
            "session_count": count,
            "session_axis_sha256": digest,
            "allowed_start_count": allowed,
            "blocks_drawn": blocks,
            "final_block_sessions_retained": count % 20 or 20,
        })
    parsed = [
        _exact_object(
            item,
            (
                "fold_id", "test_start_inclusive", "test_end_exclusive",
                "session_count", "session_axis_sha256", "allowed_start_count",
                "blocks_drawn", "final_block_sessions_retained",
            ),
            "paired bootstrap fold-axis summary",
        )
        for item in supplied
    ]
    if parsed != expected_summaries:
        raise FormalCloudEvaluationError(
            "paired bootstrap fold axes differ from the accepted contract"
        )
    return authority


def _validate_fold_horizon_axes(
    contract: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    supplied = _exact_list(
        contract["fold_horizon_axes"], "formal fold-horizon axes"
    )
    expected = tuple(_evaluation.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES)
    if len(supplied) != len(expected):
        raise FormalCloudEvaluationError("formal fold-horizon axis count changed")
    result = []
    for item, frozen in zip(supplied, expected, strict=True):
        record = _exact_object(
            item,
            (
                "fold_id", "horizon_sessions", "test_start",
                "test_end_exclusive", "session_count", "session_axis_sha256",
            ),
            "formal fold-horizon axis",
        )
        expected_record = {
            "fold_id": frozen[0],
            "horizon_sessions": frozen[1],
            "test_start": frozen[2],
            "test_end_exclusive": frozen[3],
            "session_count": frozen[4],
            "session_axis_sha256": frozen[5],
        }
        if record != expected_record:
            raise FormalCloudEvaluationError(
                "formal fold-horizon axis differs from reviewed geometry"
            )
        result.append(record)
    return tuple(result)


def _validate_streamed_economic_execution(
    contract: Mapping[str, object],
    lineage: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    binding = _exact_object(
        contract["economic_execution_binding"],
        (
            "schema", "binding_id", "binding_sha256", "definition_id",
            "definition_sha256", "definition_payload_sha256",
            "definition_byte_count", "source_stock_spec_id",
            "source_stock_spec_sha256", "source_evaluation_id",
            "source_parent_plan_id", "source_parent_plan_sha256",
            "source_fold_manifest_id", "source_fold_manifest_sha256",
            "bootstrap_base_ancestry_sha256", "status", "authority",
            "runtime_action_authority",
        ),
        "streamed economic execution binding",
    )
    definition = _exact_object(
        contract["economic_execution_definition"],
        (
            "schema", "status", "authority", "definition_id",
            "definition_sha256", "source_definition_closure",
            "execution_plan_ancestry", "sample_and_clock",
            "eligible_ranking_and_sleeves", "daily_arithmetic_and_naming",
            "turnover_cost_and_wealth_state", "terminal_and_refusal_handling",
            "inference", "exact_denominators", "capabilities",
        ),
        "streamed economic execution definition",
    )
    for name in (
        "binding_id", "definition_id", "source_stock_spec_id",
        "source_parent_plan_id", "source_fold_manifest_id",
    ):
        _safe_id(binding[name], f"economic {name}")
    for name in (
        "binding_sha256", "definition_sha256", "definition_payload_sha256",
        "source_stock_spec_sha256", "source_parent_plan_sha256",
        "source_fold_manifest_sha256", "bootstrap_base_ancestry_sha256",
    ):
        _sha(binding[name], f"economic {name}")
    _count(binding["definition_byte_count"], "economic definition bytes", minimum=1)
    definition_seed = dict(definition)
    definition_seed["definition_id"] = None
    definition_seed["definition_sha256"] = None
    definition_sha256 = hashlib.sha256(
        _canonical_bytes(definition_seed)
    ).hexdigest()
    definition_payload_sha256 = hashlib.sha256(
        _canonical_bytes(definition)
    ).hexdigest()
    binding_seed = dict(binding)
    binding_seed["binding_id"] = None
    binding_seed["binding_sha256"] = None
    binding_sha256 = hashlib.sha256(_canonical_bytes(binding_seed)).hexdigest()
    if (
        binding["schema"] != "arv2-formal-economic-execution-binding-v1"
        or definition["schema"]
        != "arv2-formal-economic-execution-definition-v1"
        or binding["runtime_action_authority"] is not False
        or definition["definition_sha256"]
        != _evaluation.ECONOMIC_EXECUTION_DEFINITION_SHA256
        or definition["definition_sha256"] != definition_sha256
        or definition["definition_id"]
        != "arv2-formal-economic-execution-" + definition_sha256[:24]
        or binding["definition_id"] != definition["definition_id"]
        or binding["definition_sha256"] != definition_sha256
        or binding["definition_payload_sha256"] != definition_payload_sha256
        or binding["definition_byte_count"] != len(_canonical_bytes(definition))
        or binding["binding_sha256"] != binding_sha256
        or binding["binding_id"]
        != "arv2-formal-economic-execution-binding-" + binding_sha256[:24]
        or lineage["economic_execution_binding_id"] != binding["binding_id"]
        or lineage["economic_execution_binding_sha256"] != binding_sha256
        or lineage["economic_execution_definition_id"]
        != definition["definition_id"]
        or lineage["economic_execution_definition_sha256"] != definition_sha256
        or lineage["economic_execution_definition_payload_sha256"]
        != definition_payload_sha256
        or hashlib.sha256(_canonical_bytes(binding)).hexdigest()
        != lineage["economic_execution_binding_record_sha256"]
        or definition_payload_sha256
        != lineage["economic_execution_definition_record_sha256"]
    ):
        raise FormalCloudEvaluationError(
            "streamed economic execution lineage changed"
        )
    sample = _exact_object(
        definition["sample_and_clock"],
        (
            "primary_slice_id", "descriptive_slice_id", "ranking_sample",
            "new_sleeves_outside_decision_axes", "post_last_decision_behavior",
            "folds_are_independent_wealth_paths", "fold_geometry",
        ),
        "economic sample and clock",
    )
    geometry = _exact_list(sample["fold_geometry"], "economic fold geometry")
    if len(geometry) != 6:
        raise FormalCloudEvaluationError("economic fold geometry count changed")
    last_decision_sessions = (
        "2020-12-31", "2021-12-31", "2022-12-30",
        "2023-12-29", "2024-12-31", "2025-12-31",
    )
    for raw, frozen, last_decision in zip(
        geometry,
        _evaluation.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES,
        last_decision_sessions,
        strict=True,
    ):
        item = _exact_object(
            raw,
            (
                "fold_id", "decision_axis_start_inclusive",
                "decision_axis_end_exclusive", "decision_session_count",
                "decision_axis_sha256", "last_decision_session",
                "return_interval_start_axis_end_exclusive",
                "return_interval_count", "return_interval_start_axis_sha256",
                "terminal_liquidation_session",
                "economic_observation_count_including_terminal_cost",
                "economic_observation_axis_sha256",
            ),
            "economic fold geometry",
        )
        expected = {
            "fold_id": frozen[0],
            "decision_axis_start_inclusive": frozen[1],
            "decision_axis_end_exclusive": frozen[2],
            "decision_session_count": frozen[3],
            "decision_axis_sha256": frozen[4],
            "last_decision_session": last_decision,
            "return_interval_start_axis_end_exclusive": frozen[5],
            "return_interval_count": frozen[6],
            "return_interval_start_axis_sha256": frozen[7],
            "terminal_liquidation_session": frozen[5],
            "economic_observation_count_including_terminal_cost": frozen[8],
            "economic_observation_axis_sha256": frozen[9],
        }
        if item != expected:
            raise FormalCloudEvaluationError(
                "economic fold geometry differs from reviewed execution"
            )
    if (
        _iso_date(
            lineage["economic_h20_terminal_liquidation_session"],
            "economic H20 terminal liquidation session",
        ).isoformat()
        != geometry[-1]["terminal_liquidation_session"]
    ):
        raise FormalCloudEvaluationError(
            "economic H20 terminal session differs from its exact definition"
        )
    return binding, definition


def _validate_streamed_report_contract(
    contract: Mapping[str, object],
    lineage: Mapping[str, object],
    *,
    economic_definition_sha256: str,
) -> dict[str, object]:
    report = _exact_object(
        contract["formal_report_contract"],
        (
            "authority", "bootstrap", "capabilities", "classification",
            "contains_results", "contract_id", "contract_sha256",
            "current_execution_authorized", "dimensions", "evaluation_id",
            "global_comparator_coverage", "numeric_and_output_rules",
            "parents", "primary_gate_composition", "report_schemas",
            "required_report_family_ids", "result_sha256", "schema",
            "secondary_hypothesis_registry", "status",
            "strategy_trial_registry",
        ),
        "streamed formal report contract",
    )
    semantic = dict(report)
    semantic.pop("contract_id")
    semantic.pop("contract_sha256")
    contract_sha256 = hashlib.sha256(_canonical_bytes(semantic)).hexdigest()
    artifact_sha256 = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    parents = _exact_object(
        report["parents"],
        (
            "economic_execution_definition_sha256", "fold_manifest_sha256",
            "matched_comparison_sha256", "qc_first_plan_sha256",
            "stock_successor_sha256",
        ),
        "formal report contract parents",
    )
    secondary = _exact_object(
        report["secondary_hypothesis_registry"],
        (
            "benjamini_hochberg", "evaluation_id", "ordered_hypotheses",
            "registry_id", "registry_sha256", "required_cohort_baseline",
            "required_reporting_bindings", "schema",
        ),
        "secondary hypothesis registry",
    )
    trials = _exact_object(
        report["strategy_trial_registry"],
        (
            "annualization_sessions", "common_session_rule", "daily_value",
            "deflated_sharpe", "evaluation_id", "ordered_trials",
            "registry_id", "registry_sha256", "sample", "schema", "sharpe",
        ),
        "strategy trial registry",
    )
    secondary_seed = dict(secondary)
    secondary_seed.pop("registry_id")
    secondary_seed.pop("registry_sha256")
    trial_seed = dict(trials)
    trial_seed.pop("registry_id")
    trial_seed.pop("registry_sha256")
    secondary_sha = hashlib.sha256(_canonical_bytes(secondary_seed)).hexdigest()
    trial_sha = hashlib.sha256(_canonical_bytes(trial_seed)).hexdigest()
    bootstrap = _exact_object(
        report["bootstrap"],
        (
            "block_length", "block_start_domain", "blocks_drawn_per_fold",
            "draw_domain", "draw_preimage", "eligible_block_start",
            "empty_replicate", "fold_boundaries_crossed", "fold_ordinal",
            "metric_encoding", "metric_ids", "noncircular_complete_axis",
            "null_centering", "operative_seed_precedence",
            "paired_IC_sampler", "pooled_replicate_statistic",
            "replicate_fold_length", "resample_ordinal", "resamples",
            "seed_record_encoding", "slice_encoding", "source_view_encoding",
            "stock_FM_and_economic_seed_record",
            "stock_FM_and_economic_seed_sha256", "test_statistic",
            "two_sided_p_value", "uniform_conversion",
        ),
        "formal report bootstrap",
    )
    bootstrap_seed = _exact_object(
        bootstrap["stock_FM_and_economic_seed_record"],
        (
            "domain", "qc_first_plan_sha256", "fold_manifest_sha256",
            "evaluation_id", "economic_execution_definition_sha256",
            "secondary_hypothesis_registry_sha256",
            "deflated_sharpe_trial_registry_sha256", "sampler_version",
        ),
        "formal stock bootstrap seed",
    )
    seed_sha = hashlib.sha256(_canonical_bytes(bootstrap_seed)).hexdigest()
    families = _exact_list(
        report["required_report_family_ids"], "required report families"
    )
    schemas = _exact_list(report["report_schemas"], "formal report schemas")
    parsed_schemas = tuple(
        _exact_object(
            item,
            (
                "family_id", "ordered_key_fields", "ordered_value_fields",
                "maximum_rows_per_source_view", "canonical_order",
                "missing_rule", "execution_rule",
                "raw_security_event_or_market_rows_permitted",
            ),
            "formal report family schema",
        )
        for item in schemas
    )
    capabilities = _exact_object(
        report["capabilities"],
        (
            "compile", "credentials", "deployment", "filesystem",
            "input_read", "launch", "network", "orders", "outcome_access",
            "provider", "quantconnect", "result_disposition", "result_read",
            "trading", "upload",
        ),
        "formal report contract capabilities",
    )
    if (
        report["schema"] != "arv2-formal-report-execution-contract-v1"
        or report["evaluation_id"] != EVALUATION_ID
        or report["contains_results"] is not False
        or report["result_sha256"] is not None
        or report["current_execution_authorized"] is not False
        or any(value is not False for value in capabilities.values())
        or parents["economic_execution_definition_sha256"]
        != economic_definition_sha256
        or report["contract_sha256"] != contract_sha256
        or report["contract_id"]
        != "arv2-formal-report-contract-" + contract_sha256[:24]
        or tuple(families) != REPORT_FAMILY_IDS
        or len(parsed_schemas) != 13
        or tuple(item["family_id"] for item in parsed_schemas)
        != REPORT_FAMILY_IDS
        or any(
            item["raw_security_event_or_market_rows_permitted"] is not False
            for item in parsed_schemas
        )
        or secondary["registry_sha256"] != secondary_sha
        or secondary["registry_id"]
        != "arv2-secondary-hypothesis-registry-" + secondary_sha[:24]
        or len(_exact_list(
            secondary["ordered_hypotheses"], "secondary hypotheses"
        )) != 19
        or trials["registry_sha256"] != trial_sha
        or trials["registry_id"]
        != "arv2-strategy-trial-registry-" + trial_sha[:24]
        or len(_exact_list(trials["ordered_trials"], "strategy trials")) != 6
        or bootstrap_seed["economic_execution_definition_sha256"]
        != economic_definition_sha256
        or bootstrap_seed["secondary_hypothesis_registry_sha256"] != secondary_sha
        or bootstrap_seed["deflated_sharpe_trial_registry_sha256"] != trial_sha
        or bootstrap["stock_FM_and_economic_seed_sha256"] != seed_sha
        or bootstrap["resamples"] != 19_999
        or bootstrap["draw_domain"]
        != "arv2-stock-formal-noncircular-mbb-hash-counter-v1"
        or lineage["formal_report_contract_id"] != report["contract_id"]
        or lineage["formal_report_contract_sha256"] != contract_sha256
        or lineage["formal_report_contract_artifact_sha256"] != artifact_sha256
        or lineage[
            "formal_report_contract_economic_execution_definition_sha256"
        ] != economic_definition_sha256
        or lineage[
            "formal_report_contract_secondary_hypothesis_registry_sha256"
        ] != secondary_sha
        or lineage[
            "formal_report_contract_deflated_sharpe_trial_registry_sha256"
        ] != trial_sha
        or lineage["formal_report_contract_stock_bootstrap_seed_sha256"]
        != seed_sha
        or lineage["formal_report_contract_report_family_count"] != 13
        or lineage["formal_report_contract_secondary_hypothesis_count"] != 19
        or lineage["formal_report_contract_strategy_trial_count"] != 6
        or lineage["formal_report_contract_record_sha256"] != artifact_sha256
    ):
        raise FormalCloudEvaluationError(
            "streamed formal report contract or operative sampler changed"
        )
    return report


def _coverage_named_counts(
    value: object, names: tuple[str, ...], label: str,
) -> dict[str, int]:
    rows = _exact_list(value, label)
    if len(rows) != len(names):
        raise FormalCloudEvaluationError(f"{label} census changed")
    result: dict[str, int] = {}
    for raw, expected in zip(rows, names, strict=True):
        if type(raw) is not list or len(raw) != 2 or raw[0] != expected:
            raise FormalCloudEvaluationError(f"{label} order changed")
        result[expected] = _count(raw[1], f"{label} {expected}")
    return result


def _coverage_global_label_diagnostics(
    value: Mapping[str, object],
) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    raw_rows = _exact_list(
        value["raw_canonical_label_counts"],
        "coverage raw/canonical label diagnostics",
    )
    if len(raw_rows) > 4096:
        raise FormalCloudEvaluationError(
            "coverage raw/canonical label diagnostic census is unbounded"
        )
    normalized: list[list[object]] = []
    raw_counts: Counter[tuple[str, str]] = Counter()
    canonical_counts: Counter[tuple[str, str]] = Counter()
    raw_forms: dict[str, set[str]] = defaultdict(set)
    canonical_instances: Counter[str] = Counter()
    prior: tuple[str, str, str] | None = None
    for row in raw_rows:
        if type(row) is not list or len(row) != 4:
            raise FormalCloudEvaluationError(
                "coverage raw/canonical label diagnostic row changed"
            )
        raw_sha = _sha(row[0], "coverage raw label hash")
        canonical_sha = _sha(row[1], "coverage canonical label hash")
        status = row[2]
        count = _count(row[3], "coverage label count", minimum=1)
        if status not in ("mapped", "measured_refusal", "unknown", "invalid"):
            raise FormalCloudEvaluationError(
                "coverage label diagnostic status changed"
            )
        key = (raw_sha, canonical_sha, status)
        if prior is not None and key <= prior:
            raise FormalCloudEvaluationError(
                "coverage label diagnostics are duplicated or reordered"
            )
        prior = key
        normalized.append([*key, count])
        raw_counts[(raw_sha, status)] += count
        canonical_counts[(canonical_sha, status)] += count
        if canonical_sha != "0" * 64:
            raw_forms[canonical_sha].add(raw_sha)
            canonical_instances[canonical_sha] += count
    expected_raw = [[*key, count] for key, count in sorted(raw_counts.items())]
    expected_canonical = [
        [*key, count] for key, count in sorted(canonical_counts.items())
    ]
    colliding = {key for key, forms in raw_forms.items() if len(forms) > 1}
    expected_collisions = [
        ["canonical_keys_with_multiple_raw_forms", len(colliding)],
        ["canonical_keys_with_any_raw_form", len(raw_forms)],
        [
            "endpoint_instances_in_colliding_canonical_keys",
            sum(canonical_instances[key] for key in colliding),
        ],
        [
            "canonicalizable_endpoint_instances",
            sum(canonical_instances.values()),
        ],
    ]
    if (
        value["raw_label_disposition_counts"] != expected_raw
        or value["canonical_label_disposition_counts"]
        != expected_canonical
        or value["raw_form_collision_counts"] != expected_collisions
    ):
        raise FormalCloudEvaluationError(
            "coverage global-label diagnostics do not reconcile"
        )
    return expected_raw, expected_canonical, expected_collisions


def _validate_global_comparator_coverage_record(
    raw: object,
    *,
    expected_scope: str,
    expected_view: str,
    expected_folds: tuple[str, ...],
    expected_bindings: Sequence[object],
    expected_h20_intervals: Sequence[tuple[str, str, str]],
) -> dict[str, object]:
    value = _exact_object(
        raw,
        (
            "schema", "scope_id", "source_view_id", "fold_ids",
            "result_bindings", "h20_test_intervals", "ledgers",
            "endpoint_status_counts", "endpoint_pair_status_counts",
            "direction_status_counts", "raw_canonical_label_counts",
            "raw_label_disposition_counts",
            "canonical_label_disposition_counts",
            "raw_form_collision_counts", "date_diagnostic_counts",
            "diagnostic_ratios", "ready", "reasons", "attribution_rule",
            "outcome_free", "coverage_id", "coverage_sha256",
        ),
        "global comparator coverage",
    )
    pooled = len(expected_folds) == 6
    expected_schema = (
        "arv2-formal-global-comparator-pooled-coverage-v1"
        if pooled
        else "arv2-formal-global-comparator-fold-coverage-v1"
    )
    bindings = _exact_list(value["result_bindings"], "coverage result bindings")
    intervals = _exact_list(value["h20_test_intervals"], "coverage H20 intervals")
    if (
        value["schema"] != expected_schema
        or value["scope_id"] != expected_scope
        or value["source_view_id"] != expected_view
        or value["fold_ids"] != list(expected_folds)
        or bindings != list(expected_bindings)
        or intervals != [list(item) for item in expected_h20_intervals]
        or value["ready"] is not True
        or value["reasons"] != []
        or value["attribution_rule"] != GLOBAL_COMPARATOR_ATTRIBUTION_RULE
        or value["outcome_free"] is not True
    ):
        raise FormalCloudEvaluationError(
            "global comparator coverage scope or readiness changed"
        )
    ledgers = _exact_list(value["ledgers"], "global coverage ledgers")
    if len(ledgers) != 5:
        raise FormalCloudEvaluationError("global coverage ledger census changed")
    parsed_ledgers: dict[str, tuple[int, int]] = {}
    for raw_ledger, ledger_id in zip(
        ledgers, GLOBAL_COMPARATOR_LEDGER_IDS, strict=True
    ):
        ledger = _exact_object(
            raw_ledger,
            (
                "ledger_id", "numerator", "denominator",
                "threshold_numerator", "threshold_denominator", "passes",
                "disposition", "reasons",
            ),
            "global coverage ledger",
        )
        numerator = _count(ledger["numerator"], "coverage numerator")
        denominator = _count(ledger["denominator"], "coverage denominator")
        if (
            ledger["ledger_id"] != ledger_id
            or numerator > denominator
            or denominator == 0
            or ledger["threshold_numerator"] != 19
            or ledger["threshold_denominator"] != 20
            or numerator * 20 < denominator * 19
            or ledger["passes"] is not True
            or ledger["disposition"] != "PASS"
            or ledger["reasons"] != []
        ):
            raise FormalCloudEvaluationError(
                "global coverage 19-of-20 gate is closed"
            )
        parsed_ledgers[ledger_id] = (numerator, denominator)
    endpoint = _coverage_named_counts(
        value["endpoint_status_counts"],
        ("mapped", "measured_refusal", "unknown", "invalid"),
        "coverage endpoint status",
    )
    endpoint_pairs = _coverage_named_counts(
        value["endpoint_pair_status_counts"],
        ("mapped", "measured_refusal", "unknown", "invalid"),
        "coverage endpoint pair status",
    )
    directions = _coverage_named_counts(
        value["direction_status_counts"],
        ("expected_sign", "opposite_sign", "zero_delta"),
        "coverage direction status",
    )
    _coverage_global_label_diagnostics(value)
    dates = _coverage_named_counts(
        value["date_diagnostic_counts"],
        (
            "firm_totalized_zero_dates", "global_totalized_zero_dates",
            "both_arms_constant_dates", "score_refused_candidate_dates",
            "preoutcome_candidate_dates",
        ),
        "coverage date diagnostic",
    )
    ratios = _exact_list(value["diagnostic_ratios"], "coverage diagnostics")
    ratio_ids = (
        "global_tier_collapse_zero_share", "global_direction_conflict_share",
        "firm_totalized_zero_date_share", "global_totalized_zero_date_share",
        "both_arms_constant_date_share",
    )
    expected_ratios = (
        (directions["zero_delta"], endpoint_pairs["mapped"]),
        (directions["opposite_sign"], endpoint_pairs["mapped"]),
        (dates["firm_totalized_zero_dates"], dates["preoutcome_candidate_dates"]),
        (dates["global_totalized_zero_dates"], dates["preoutcome_candidate_dates"]),
        (dates["both_arms_constant_dates"], dates["preoutcome_candidate_dates"]),
    )
    for raw_ratio, ratio_id, expected in zip(
        ratios, ratio_ids, expected_ratios, strict=True
    ):
        ratio = _exact_object(
            raw_ratio,
            ("ratio_id", "numerator", "denominator", "available"),
            "coverage diagnostic ratio",
        )
        if (
            ratio["ratio_id"] != ratio_id
            or (ratio["numerator"], ratio["denominator"]) != expected
            or ratio["available"] is not (expected[1] > 0)
        ):
            raise FormalCloudEvaluationError(
                "global coverage diagnostic reconciliation changed"
            )
    if (
        sum(endpoint.values()) != 2 * sum(endpoint_pairs.values())
        or sum(row[3] for row in value["raw_canonical_label_counts"])
        != sum(endpoint.values())
        or sum(directions.values()) != endpoint_pairs["mapped"]
        or parsed_ledgers["endpoint_pair_mapping"]
        != (
            directions["expected_sign"] + directions["zero_delta"],
            sum(endpoint_pairs.values()),
        )
        or parsed_ledgers["score_capable_dates"]
        != (
            dates["preoutcome_candidate_dates"]
            - dates["both_arms_constant_dates"]
            - dates["score_refused_candidate_dates"],
            dates["preoutcome_candidate_dates"],
        )
    ):
        raise FormalCloudEvaluationError(
            "global comparator coverage arithmetic changed"
        )
    seed = dict(value)
    coverage_id = seed.pop("coverage_id")
    coverage_sha256 = seed.pop("coverage_sha256")
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    if (
        coverage_sha256 != digest
        or coverage_id
        != "arv2-formal-global-comparator-coverage-" + digest[:24]
    ):
        raise FormalCloudEvaluationError(
            "global comparator coverage identity changed"
        )
    return value


def _validate_global_comparator_coverages(
    contract: Mapping[str, object],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    bindings = _exact_list(
        contract["scoring_result_bindings"], "scoring result bindings"
    )
    axes = {
        item["fold_id"]: (
            item["fold_id"], item["test_start"], item["test_end_exclusive"]
        )
        for item in _validate_fold_horizon_axes(contract)
        if item["horizon_sessions"] == 20
    }
    fold_values = _exact_list(
        contract["global_comparator_fold_coverages"],
        "global comparator fold coverages",
    )
    pooled_values = _exact_list(
        contract["global_comparator_pooled_coverages"],
        "global comparator pooled coverages",
    )
    if len(fold_values) != 12 or len(pooled_values) != 2:
        raise FormalCloudEvaluationError(
            "global comparator coverage object census changed"
        )
    parsed_folds: list[dict[str, object]] = []
    for fold_index, fold_id in enumerate(FORMAL_FOLD_IDS):
        for view_index, view in enumerate(SOURCE_VIEW_IDS):
            parsed_folds.append(_validate_global_comparator_coverage_record(
                fold_values[fold_index * 2 + view_index],
                expected_scope=fold_id,
                expected_view=view,
                expected_folds=(fold_id,),
                expected_bindings=(bindings[fold_index],),
                expected_h20_intervals=(axes[fold_id],),
            ))
    parsed_pooled: list[dict[str, object]] = []
    for view_index, view in enumerate(SOURCE_VIEW_IDS):
        pooled = _validate_global_comparator_coverage_record(
            pooled_values[view_index],
            expected_scope="pooled",
            expected_view=view,
            expected_folds=FORMAL_FOLD_IDS,
            expected_bindings=bindings,
            expected_h20_intervals=tuple(axes[item] for item in FORMAL_FOLD_IDS),
        )
        parents = tuple(parsed_folds[index * 2 + view_index] for index in range(6))
        for field in (
            "endpoint_status_counts", "endpoint_pair_status_counts",
            "direction_status_counts", "date_diagnostic_counts",
        ):
            parent_rows = [item[field] for item in parents]
            expected_rows = [
                [parent_rows[0][row_index][0], sum(
                    value[row_index][1] for value in parent_rows
                )]
                for row_index in range(len(parent_rows[0]))
            ]
            if pooled[field] != expected_rows:
                raise FormalCloudEvaluationError(
                    "pooled comparator diagnostic is not the integer fold sum"
                )
        for field, key_width in (
            ("raw_canonical_label_counts", 3),
            ("raw_label_disposition_counts", 2),
            ("canonical_label_disposition_counts", 2),
        ):
            combined: Counter[tuple[object, ...]] = Counter()
            for parent in parents:
                for row in parent[field]:
                    combined[tuple(row[:key_width])] += row[key_width]
            expected_rows = [
                [*key, count] for key, count in sorted(combined.items())
            ]
            if pooled[field] != expected_rows:
                raise FormalCloudEvaluationError(
                    "pooled comparator label diagnostic is not the integer fold sum"
                )
        for ledger_index in range(5):
            if (
                pooled["ledgers"][ledger_index]["numerator"]
                != sum(item["ledgers"][ledger_index]["numerator"] for item in parents)
                or pooled["ledgers"][ledger_index]["denominator"]
                != sum(item["ledgers"][ledger_index]["denominator"] for item in parents)
            ):
                raise FormalCloudEvaluationError(
                    "pooled comparator ledger is not the integer fold sum"
                )
        parsed_pooled.append(pooled)
    return tuple(parsed_folds), tuple(parsed_pooled)


def _streamed_manifest_lineage(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    lineage = _exact_object(
        manifest.get("streamed_formal_input_lineage"),
        _STREAMED_FORMAL_INPUT_LINEAGE_FIELDS,
        "streamed formal input manifest lineage",
    )
    if (
        lineage["schema"] != STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA
        or lineage["contract_variant"] != STREAMED_FORMAL_CONTRACT_VARIANT
    ):
        raise FormalCloudEvaluationError(
            "streamed formal input manifest lineage identity changed"
        )
    for name in (
        "streamed_input_candidate_id", "streamed_scoring_id",
        "physical_formal_shard_archive_id", "physical_preopen_archive_id",
        "preopen_acquisition_id", "production_evidence_receipt_id",
        "economic_execution_binding_id", "economic_execution_definition_id",
        "formal_report_contract_id", "terminal_package_id",
    ):
        _safe_id(lineage[name], name)
    for name in (
        "formal_contract_sha256", "streamed_input_candidate_sha256",
        "streamed_scoring_sha256", "physical_formal_shard_archive_sha256",
        "physical_preopen_archive_sha256", "preopen_acquisition_sha256",
        "production_evidence_receipt_sha256", "accepted_risk_sha256",
        "formal_power_sha256", "power_floor_sha256",
        "economic_execution_binding_sha256",
        "economic_execution_definition_sha256",
        "economic_execution_definition_payload_sha256",
        "economic_execution_binding_record_sha256",
        "economic_execution_definition_record_sha256",
        "formal_report_contract_sha256",
        "formal_report_contract_artifact_sha256",
        "formal_report_contract_economic_execution_definition_sha256",
        "formal_report_contract_secondary_hypothesis_registry_sha256",
        "formal_report_contract_deflated_sharpe_trial_registry_sha256",
        "formal_report_contract_stock_bootstrap_seed_sha256",
        "formal_report_contract_record_sha256",
        "scoring_result_bindings_sha256",
        "paired_bootstrap_authority_sha256", "fold_horizon_axes_sha256",
        "terminal_package_sha256",
        "terminal_census_sha256", "source_view_partitions_sha256",
        "formal_evaluator_source_sha256",
    ):
        _sha(lineage[name], name)
    for name, expected in (
        ("formal_report_contract_report_family_count", 13),
        ("formal_report_contract_secondary_hypothesis_count", 19),
        ("formal_report_contract_strategy_trial_count", 6),
    ):
        if _count(lineage[name], name) != expected:
            raise FormalCloudEvaluationError(
                "streamed report-contract census changed"
            )
    package = _artifact_binding_record(
        lineage["production_input_package"],
        "streamed lineage production input package",
    )
    preopen = _artifact_binding_record(
        lineage["preopen_control_stage_output"],
        "streamed lineage preopen-control output",
    )
    if (
        package != manifest.get("production_input_package")
        or preopen != manifest.get("preopen_control_stage_output")
        or lineage["preopen_acquisition_id"] != preopen["artifact_id"]
        or lineage["preopen_acquisition_sha256"] != preopen["artifact_sha256"]
        or lineage["benchmark_security_id"]
        != manifest.get("benchmark_security_id")
        or lineage["calculation_as_of_date"]
        != manifest.get("calculation_as_of_date")
    ):
        raise FormalCloudEvaluationError(
            "streamed manifest lineage diverged from its runtime manifest"
        )
    _security_id(lineage["benchmark_security_id"], "lineage benchmark security")
    _iso_date(lineage["calculation_as_of_date"], "lineage calculation date")
    return lineage


def _streamed_power_floor(
    contract: Mapping[str, object], lineage: Mapping[str, object]
) -> dict[str, object]:
    formal_power = _exact_object(
        contract["formal_power"],
        (
            "receipt_id", "receipt_sha256", "protocol_id", "protocol_sha256",
            "manifest_id", "manifest_content_sha256", "required_valid_dates",
            "required_connected_components", "fixed_h20_test_session_capacity",
            "disposition",
        ),
        "streamed formal power binding",
    )
    for name in ("receipt_id", "protocol_id", "manifest_id"):
        _safe_id(formal_power[name], f"formal power {name}")
    for name in (
        "receipt_sha256", "protocol_sha256", "manifest_content_sha256",
    ):
        _sha(formal_power[name], f"formal power {name}")
    _count(formal_power["required_valid_dates"], "required valid dates", minimum=50)
    _count(
        formal_power["required_connected_components"],
        "required connected components",
        minimum=50,
    )
    _count(
        formal_power["fixed_h20_test_session_capacity"],
        "fixed H20 TEST-session capacity",
        minimum=1,
    )
    power = _exact_object(
        contract["power_floor"],
        (
            "numeric_receipt", "stock_successor", "disposition",
            "required_valid_dates", "observed_preoutcome_valid_dates",
            "required_connected_components",
            "observed_preoutcome_connected_components",
            "h20_test_session_capacity", "preoutcome_candidate_date_count",
            "valid_h20_test_session_count",
            "refused_h20_test_session_count",
            "missing_h20_test_session_count",
            "connected_component_instance_count",
        ),
        "streamed formal power floor",
    )
    numeric = _artifact_binding_record(
        power["numeric_receipt"], "streamed numeric power receipt"
    )
    _artifact_binding_record(
        power["stock_successor"], "streamed stock-power successor"
    )
    for name in (
        "required_valid_dates", "observed_preoutcome_valid_dates",
        "required_connected_components",
        "observed_preoutcome_connected_components",
        "h20_test_session_capacity", "preoutcome_candidate_date_count",
        "valid_h20_test_session_count", "refused_h20_test_session_count",
        "missing_h20_test_session_count", "connected_component_instance_count",
    ):
        _count(
            power[name], name,
            minimum=(
                1 if name in {
                    "required_valid_dates", "observed_preoutcome_valid_dates",
                    "required_connected_components",
                    "observed_preoutcome_connected_components",
                    "h20_test_session_capacity",
                } else 0
            ),
        )
    if (
        formal_power["disposition"]
        != "FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt"
        or power["disposition"] != formal_power["disposition"]
        or numeric["artifact_id"] != formal_power["receipt_id"]
        or numeric["content_sha256"] != formal_power["receipt_sha256"]
        or power["required_valid_dates"] != formal_power["required_valid_dates"]
        or power["required_connected_components"]
        != formal_power["required_connected_components"]
        or power["observed_preoutcome_valid_dates"]
        < power["required_valid_dates"]
        or power["observed_preoutcome_connected_components"]
        < power["required_connected_components"]
        or power["h20_test_session_capacity"]
        != formal_power["fixed_h20_test_session_capacity"]
        or power["preoutcome_candidate_date_count"]
        != (
            power["valid_h20_test_session_count"]
            + power["refused_h20_test_session_count"]
        )
        or power["h20_test_session_capacity"]
        != (
            power["preoutcome_candidate_date_count"]
            + power["missing_h20_test_session_count"]
        )
        or power["observed_preoutcome_valid_dates"]
        != power["valid_h20_test_session_count"]
        or power["observed_preoutcome_connected_components"]
        != power["connected_component_instance_count"]
        or hashlib.sha256(_canonical_bytes(formal_power)).hexdigest()
        != lineage["formal_power_sha256"]
        or hashlib.sha256(_canonical_bytes(power)).hexdigest()
        != lineage["power_floor_sha256"]
    ):
        raise FormalCloudEvaluationError(
            "streamed formal power lineage or feasible floor changed"
        )
    return {
        "receipt_id": numeric["artifact_id"],
        "receipt_sha256": numeric["content_sha256"],
        "required_valid_dates": power["required_valid_dates"],
        "required_connected_components": power["required_connected_components"],
        "h20_test_session_capacity": power["h20_test_session_capacity"],
        "preoutcome_candidate_date_count": (
            power["preoutcome_candidate_date_count"]
        ),
        "valid_h20_test_session_count": power["valid_h20_test_session_count"],
        "refused_h20_test_session_count": (
            power["refused_h20_test_session_count"]
        ),
        "missing_h20_test_session_count": power["missing_h20_test_session_count"],
        "connected_component_instance_count": (
            power["connected_component_instance_count"]
        ),
    }


def _parse_legacy_contract(
    value: object, manifest: Mapping[str, object]
) -> dict[str, object]:
    contract = _exact_object(value, _FORMAL_CONTRACT_FIELDS, "formal contract")
    if (
        contract["schema"] != FORMAL_INPUT_CONTRACT_SCHEMA
        or contract["evaluation_id"] != EVALUATION_ID
        or contract["scoring_contract_id"] != SCORING_CONTRACT_ID
        or contract["scoring_contract_sha256"] != SCORING_CONTRACT_SHA256
    ):
        raise FormalCloudEvaluationError("formal contract identity changed")
    for name in (
        "evaluation_input_bundle_id", "production_scoring_census_id",
        "production_truth_artifact_id", "terminal_package_id",
    ):
        _safe_id(contract[name], name)
    for name in (
        "evaluation_input_bundle_sha256", "production_scoring_census_sha256",
        "production_truth_artifact_sha256", "terminal_package_sha256",
        "formal_evaluator_source_sha256",
    ):
        _sha(contract[name], name)
    package = _artifact_binding_record(
        manifest.get("production_input_package"),
        "manifest production input package",
    )
    if (
        package["artifact_id"] != contract["evaluation_input_bundle_id"]
        or package["content_sha256"] != contract["evaluation_input_bundle_sha256"]
    ):
        raise FormalCloudEvaluationError("manifest and formal contract diverged")
    preopen = _artifact_binding_record(
        contract["preopen_control_stage_output"],
        "formal contract preopen-control binding",
    )
    if preopen != manifest.get("preopen_control_stage_output"):
        raise FormalCloudEvaluationError(
            "manifest and formal contract preopen-control binding diverged"
        )
    _validate_scoring_result_bindings(contract)
    _validate_stream_layout(contract)
    return contract


def _parse_streamed_contract(
    value: object, manifest: Mapping[str, object]
) -> dict[str, object]:
    contract = _exact_object(
        value, _STREAMED_FORMAL_CONTRACT_FIELDS, "streamed formal contract"
    )
    lineage = _streamed_manifest_lineage(manifest)
    if (
        contract["schema"] != FORMAL_INPUT_CONTRACT_SCHEMA
        or contract["contract_variant"] != STREAMED_FORMAL_CONTRACT_VARIANT
        or contract["evaluation_id"] != EVALUATION_ID
        or contract["scoring_contract_id"] != SCORING_CONTRACT_ID
        or contract["scoring_contract_sha256"] != SCORING_CONTRACT_SHA256
        or contract["terminal_policy_id"] != TERMINAL_POLICY_ID
        or contract["streaming_method_id"] != STREAMING_METHOD_ID
        or contract["appearance_seed_semantics"] != APPEARANCE_SEED_SEMANTICS
        or contract["legacy_six_result_materialization_used"] is not False
        or contract["outcome_or_qc_action_authorized"] is not False
        or contract["benchmark_security_id"]
        != manifest.get("benchmark_security_id")
        or contract["calculation_as_of_date"]
        != manifest.get("calculation_as_of_date")
    ):
        raise FormalCloudEvaluationError("streamed formal contract identity changed")
    _safe_id(contract["streamed_scoring_id"], "streamed scoring id")
    _sha(contract["streamed_scoring_sha256"], "streamed scoring hash")
    _security_id(contract["benchmark_security_id"], "streamed benchmark security")
    _iso_date(contract["calculation_as_of_date"], "streamed calculation date")
    physical = _exact_object(
        contract["physical_preopen_archive"],
        (
            "archive_id", "archive_sha256", "preopen_acquisition_id",
            "preopen_acquisition_sha256",
        ),
        "streamed physical preopen archive",
    )
    evidence = _exact_object(
        contract["production_evidence_receipt"],
        ("receipt_id", "receipt_sha256"),
        "streamed production evidence receipt",
    )
    for name in ("archive_id", "preopen_acquisition_id"):
        _safe_id(physical[name], f"physical preopen {name}")
    for name in ("archive_sha256", "preopen_acquisition_sha256"):
        _sha(physical[name], f"physical preopen {name}")
    _safe_id(evidence["receipt_id"], "production evidence receipt id")
    _sha(evidence["receipt_sha256"], "production evidence receipt hash")
    accepted_risk = _exact_object(
        contract["accepted_risk"],
        (
            "pair", "capture_id", "capture_sha256",
            "current_source_included_count", "censored_source_included_count",
            "current_admitted_decision_count",
            "current_named_preoutcome_refusal_count",
            "censored_admitted_decision_count",
            "censored_named_preoutcome_refusal_count", "guidance_admitted_count",
            "pre_2013_admitted_count", "pristine_point_in_time",
            "views_share_one_capture",
        ),
        "streamed accepted-risk binding",
    )
    _artifact_binding_record(accepted_risk["pair"], "accepted-risk pair")
    _safe_id(accepted_risk["capture_id"], "accepted-risk capture id")
    _sha(accepted_risk["capture_sha256"], "accepted-risk capture hash")
    for name in (
        "current_source_included_count", "censored_source_included_count",
        "current_admitted_decision_count",
        "current_named_preoutcome_refusal_count",
        "censored_admitted_decision_count",
        "censored_named_preoutcome_refusal_count", "guidance_admitted_count",
        "pre_2013_admitted_count",
    ):
        _count(accepted_risk[name], name)
    if (
        accepted_risk["current_source_included_count"] < 1
        or accepted_risk["censored_source_included_count"]
        > accepted_risk["current_source_included_count"]
        or accepted_risk["current_admitted_decision_count"]
        + accepted_risk["current_named_preoutcome_refusal_count"]
        != accepted_risk["current_source_included_count"]
        or accepted_risk["censored_admitted_decision_count"]
        + accepted_risk["censored_named_preoutcome_refusal_count"]
        != accepted_risk["censored_source_included_count"]
        or accepted_risk["guidance_admitted_count"] != 0
        or accepted_risk["pre_2013_admitted_count"] != 0
        or accepted_risk["pristine_point_in_time"] is not False
        or accepted_risk["views_share_one_capture"] is not True
    ):
        raise FormalCloudEvaluationError("streamed accepted-risk binding changed")
    terminal = _exact_object(
        contract["terminal_census"],
        (
            "terminal_policy_id", "terminal_requirement_count",
            "terminal_payoff_count", "benchmark_splice_continuation_count",
            "named_terminal_refusal_count", "silently_omitted_count",
        ),
        "streamed terminal census",
    )
    for name in (
        "terminal_requirement_count", "terminal_payoff_count",
        "benchmark_splice_continuation_count", "named_terminal_refusal_count",
        "silently_omitted_count",
    ):
        _count(terminal[name], name)
    if (
        terminal["terminal_policy_id"] != TERMINAL_POLICY_ID
        or terminal["terminal_requirement_count"]
        != terminal["terminal_payoff_count"]
        + terminal["benchmark_splice_continuation_count"]
        + terminal["named_terminal_refusal_count"]
        or terminal["silently_omitted_count"] != 0
    ):
        raise FormalCloudEvaluationError("streamed terminal census changed")
    paired_bootstrap = _validate_paired_bootstrap_authority(contract)
    fold_horizon_axes = _validate_fold_horizon_axes(contract)
    economic_binding, economic_definition = (
        _validate_streamed_economic_execution(contract, lineage)
    )
    report_contract = _validate_streamed_report_contract(
        contract,
        lineage,
        economic_definition_sha256=economic_definition["definition_sha256"],
    )
    fold_coverages, pooled_coverages = (
        _validate_global_comparator_coverages(contract)
    )
    expected_hashes = {
        "accepted_risk_sha256": accepted_risk,
        "scoring_result_bindings_sha256": contract["scoring_result_bindings"],
        "paired_bootstrap_authority_sha256": paired_bootstrap,
        "fold_horizon_axes_sha256": list(fold_horizon_axes),
        "terminal_census_sha256": terminal,
        "source_view_partitions_sha256": contract["source_view_partitions"],
    }
    if (
        hashlib.sha256(_canonical_bytes(contract)).hexdigest()
        != lineage["formal_contract_sha256"]
        or contract["streamed_scoring_id"] != lineage["streamed_scoring_id"]
        or contract["streamed_scoring_sha256"]
        != lineage["streamed_scoring_sha256"]
        or physical["archive_id"] != lineage["physical_preopen_archive_id"]
        or physical["archive_sha256"]
        != lineage["physical_preopen_archive_sha256"]
        or physical["preopen_acquisition_id"]
        != lineage["preopen_acquisition_id"]
        or physical["preopen_acquisition_sha256"]
        != lineage["preopen_acquisition_sha256"]
        or evidence["receipt_id"] != lineage["production_evidence_receipt_id"]
        or evidence["receipt_sha256"]
        != lineage["production_evidence_receipt_sha256"]
        or contract["terminal_package_id"] != lineage["terminal_package_id"]
        or contract["terminal_package_sha256"]
        != lineage["terminal_package_sha256"]
        or any(
            hashlib.sha256(_canonical_bytes(record)).hexdigest()
            != lineage[name]
            for name, record in expected_hashes.items()
        )
    ):
        raise FormalCloudEvaluationError(
            "streamed formal contract diverged from its authenticated lineage"
        )
    _safe_id(contract["terminal_package_id"], "terminal package id")
    _sha(contract["terminal_package_sha256"], "terminal package hash")
    _validate_scoring_result_bindings(contract)
    _validate_stream_layout(contract)
    normalized_power = _streamed_power_floor(contract, lineage)
    package = lineage["production_input_package"]
    preopen = lineage["preopen_control_stage_output"]
    return {
        "contract_variant": STREAMED_FORMAL_CONTRACT_VARIANT,
        "schema": contract["schema"],
        "evaluation_id": contract["evaluation_id"],
        "evaluation_input_bundle_id": package["artifact_id"],
        "evaluation_input_bundle_sha256": package["content_sha256"],
        "production_scoring_census_id": contract["streamed_scoring_id"],
        "production_scoring_census_sha256": contract["streamed_scoring_sha256"],
        "scoring_contract_id": contract["scoring_contract_id"],
        "scoring_contract_sha256": contract["scoring_contract_sha256"],
        "scoring_result_bindings": contract["scoring_result_bindings"],
        "paired_bootstrap_authority": paired_bootstrap,
        "fold_horizon_axes": list(fold_horizon_axes),
        "global_comparator_fold_coverages": list(fold_coverages),
        "global_comparator_pooled_coverages": list(pooled_coverages),
        "economic_execution_binding": economic_binding,
        "economic_execution_definition": economic_definition,
        "formal_report_contract": report_contract,
        "preopen_control_stage_output": preopen,
        "formal_evaluator_source_sha256": lineage[
            "formal_evaluator_source_sha256"
        ],
        "accepted_risk": accepted_risk,
        "power_floor": normalized_power,
        "terminal_package_id": contract["terminal_package_id"],
        "terminal_package_sha256": contract["terminal_package_sha256"],
        "terminal_census": terminal,
        "source_view_partitions": contract["source_view_partitions"],
        "stream_layout": contract["stream_layout"],
    }


def _parse_contract(rows: object, manifest: Mapping[str, object]) -> dict[str, object]:
    values = _exact_list(rows, "formal contract rows")
    if len(values) != 1:
        raise FormalCloudEvaluationError("formal contract shard must contain one row")
    value = values[0]
    if type(value) is dict and "contract_variant" in value:
        return _parse_streamed_contract(value, manifest)
    return _parse_legacy_contract(value, manifest)


def _parse_daily_requirements(
    rows: object, *, allow_empty: bool = False,
) -> dict[str, dict[str, object]]:
    supplied = _exact_list(rows, "daily requirements")
    _require_role_row_order(supplied, "daily_requirements")
    result: dict[str, dict[str, object]] = {}
    for value in supplied:
        row = _exact_object(value, _DAILY_REQUIREMENT_FIELDS, "daily requirement")
        if row["schema"] != DAILY_REQUIREMENT_SCHEMA:
            raise FormalCloudEvaluationError("daily requirement schema changed")
        security = _security_id(row["security_id"], "daily security")
        session = _iso_date(row["session"], "daily session").isoformat()
        requirement_id = _safe_id(row["requirement_id"], "daily requirement id")
        if requirement_id != build_daily_market_requirement_id(
            security_id=security, session=session
        ) or requirement_id in result:
            raise FormalCloudEvaluationError("daily requirement identity duplicated or changed")
        result[requirement_id] = row
    if not result and not allow_empty:
        raise FormalCloudEvaluationError("daily requirements are empty")
    return result


def _parse_minute_requirements(rows: object) -> dict[str, dict[str, object]]:
    supplied = _exact_list(rows, "minute requirements")
    _require_role_row_order(supplied, "minute_requirements")
    result: dict[str, dict[str, object]] = {}
    for value in supplied:
        row = _exact_object(value, _MINUTE_REQUIREMENT_FIELDS, "minute requirement")
        if row["schema"] != MINUTE_REQUIREMENT_SCHEMA:
            raise FormalCloudEvaluationError("minute requirement schema changed")
        security = _security_id(row["security_id"], "minute security")
        publication = row["publication_at_utc"]
        _utc(publication, "minute publication")
        first_active = _count(
            row["first_active_session_position"],
            "minute first active session position",
        )
        last_active = _count(
            row["last_active_session_position"],
            "minute last active session position",
        )
        if last_active < first_active:
            raise FormalCloudEvaluationError(
                "minute active-session interval changed"
            )
        requirement_id = _safe_id(row["requirement_id"], "minute requirement id")
        if requirement_id != build_minute_market_requirement_id(
            security_id=security, publication_at_utc=publication
        ) or requirement_id in result:
            raise FormalCloudEvaluationError("minute requirement identity duplicated or changed")
        result[requirement_id] = row
    return result


def _parse_observations(
    observations: object,
    daily_requirements: Mapping[str, dict[str, object]],
    minute_requirements: Mapping[str, dict[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], str, int]:
    supplied = _exact_object(
        observations, ("schema", "daily", "minute"), "market observations"
    )
    if supplied["schema"] != MARKET_OBSERVATION_PANEL_SCHEMA:
        raise FormalCloudEvaluationError("market observation panel schema changed")
    daily: dict[str, dict[str, object]] = {}
    minute: dict[str, dict[str, object]] = {}
    daily_fields = (
        "schema", "requirement_id", "security_id", "session", "disposition",
        "open", "reason",
    )
    minute_fields = (
        "schema", "requirement_id", "security_id", "publication_at_utc",
        "disposition", "last_price", "last_bar_end_utc", "reason",
    )
    for value in _exact_list(supplied["daily"], "daily observations"):
        row = _exact_object(value, daily_fields, "daily observation")
        requirement_id = _safe_id(row["requirement_id"], "daily observation id")
        requirement = daily_requirements.get(requirement_id)
        if (
            row["schema"] != DAILY_OBSERVATION_SCHEMA
            or requirement is None
            or row["security_id"] != requirement["security_id"]
            or row["session"] != requirement["session"]
            or requirement_id in daily
        ):
            raise FormalCloudEvaluationError("daily observation does not match its requirement")
        if row["disposition"] == "observation":
            _decimal(row["open"], "daily open", positive=True)
            if row["reason"] is not None:
                raise FormalCloudEvaluationError("daily observation carries a refusal")
        elif row["disposition"] == "named_refusal":
            if row["open"] is not None:
                raise FormalCloudEvaluationError("daily refusal carries an open")
            _safe_id(row["reason"], "daily refusal reason")
        else:
            raise FormalCloudEvaluationError("daily observation disposition changed")
        daily[requirement_id] = row
    for value in _exact_list(supplied["minute"], "minute observations"):
        row = _exact_object(value, minute_fields, "minute observation")
        requirement_id = _safe_id(row["requirement_id"], "minute observation id")
        requirement = minute_requirements.get(requirement_id)
        if (
            row["schema"] != MINUTE_OBSERVATION_SCHEMA
            or requirement is None
            or row["security_id"] != requirement["security_id"]
            or row["publication_at_utc"] != requirement["publication_at_utc"]
            or requirement_id in minute
        ):
            raise FormalCloudEvaluationError("minute observation does not match its requirement")
        publication = _utc(row["publication_at_utc"], "minute publication")
        if row["disposition"] == "observation":
            _decimal(row["last_price"], "minute last price", positive=True)
            ended = _utc(row["last_bar_end_utc"], "minute bar end")
            if ended >= publication or row["reason"] is not None:
                raise FormalCloudEvaluationError(
                    "minute observation is not strictly prepublication"
                )
        elif row["disposition"] == "named_refusal":
            if row["last_price"] is not None or row["last_bar_end_utc"] is not None:
                raise FormalCloudEvaluationError("minute refusal carries a price")
            _safe_id(row["reason"], "minute refusal reason")
        else:
            raise FormalCloudEvaluationError("minute observation disposition changed")
        minute[requirement_id] = row
    if set(daily) != set(daily_requirements) or set(minute) != set(minute_requirements):
        raise FormalCloudEvaluationError("market observation census is incomplete or expanded")
    panel = begin_formal_market_panel_digest(
        expected_observation_count=len(daily) + len(minute)
    )
    for requirement in sorted(
        daily_requirements.values(),
        key=lambda item: _role_row_key("daily_requirements", item),
    ):
        consume_formal_market_panel_digest_row(
            panel, requirement=requirement,
            observation=daily[requirement["requirement_id"]],
        )
    for requirement in sorted(
        minute_requirements.values(),
        key=lambda item: _role_row_key("minute_requirements", item),
    ):
        consume_formal_market_panel_digest_row(
            panel, requirement=requirement,
            observation=minute[requirement["requirement_id"]],
        )
    panel_hash, panel_count = finish_formal_market_panel_digest(panel)
    return daily, minute, panel_hash, panel_count


def _market_panel_digest_static(value: FormalMarketPanelDigest) -> bytes:
    return _canonical_bytes({"digest_id": value.digest_id, "schema": value.schema})


def _require_market_panel_digest_impl(
    value: FormalMarketPanelDigest,
    *,
    _authority_lookup: object,
) -> tuple[FormalMarketPanelDigest, _MarketPanelDigestState]:
    if type(value) is not FormalMarketPanelDigest:
        raise FormalCloudEvaluationError("market-panel digest changed type")
    registered = _authority_lookup(value)
    if (
        registered is None
        or registered[0] != _market_panel_digest_static(value)
        or value.schema != MARKET_PANEL_STREAM_SCHEMA
    ):
        raise FormalCloudEvaluationError(
            "market-panel digest is not builder-authenticated"
        )
    state = registered[1]
    if (
        state.creator_pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
    ):
        state.failed = True
        raise FormalCloudEvaluationError(
            "market-panel digest process or owner thread changed"
        )
    if state.failed:
        raise FormalCloudEvaluationError(
            "market-panel digest is locked after a failed transition"
        )
    return value, state


def _begin_formal_market_panel_digest_impl(
    expected_observation_count: int,
    *,
    _authority_register: object,
    _authority_require: object,
) -> FormalMarketPanelDigest:
    """Begin one bounded-memory, canonical market-panel digest pass."""

    expected = _count(
        expected_observation_count, "expected market observation count",
        minimum=0,
    )
    identity_seed = _canonical_bytes({
        "schema": MARKET_PANEL_STREAM_SCHEMA,
        "expected_observation_count": expected,
    })
    digest = hashlib.sha256(identity_seed).hexdigest()
    value = object.__new__(FormalMarketPanelDigest)
    object.__setattr__(value, "digest_id", f"arv2-market-panel-digest-{digest[:24]}")
    object.__setattr__(value, "schema", MARKET_PANEL_STREAM_SCHEMA)
    state = _MarketPanelDigestState(
        creator_pid=os.getpid(), owner_thread_id=threading.get_ident(),
        expected_count=expected, count=0, modular_sum=0, bitwise_xor=0,
        last_keys={}, finished=False, failed=False,
    )
    _authority_register(
        value, _market_panel_digest_static(value), state
    )
    return _authority_require(value)[0]


def _consume_formal_market_panel_digest_row_impl(
    digest: FormalMarketPanelDigest, *, requirement: Mapping[str, object],
    observation: Mapping[str, object],
    _authority_require: object,
    _authority_update: object,
) -> FormalMarketPanelDigest:
    """Validate and hash the next globally ordered requirement/observation pair."""

    value, state = _authority_require(digest)
    if state.finished or state.count >= state.expected_count:
        raise FormalCloudEvaluationError("market-panel digest is sealed or full")
    if type(requirement) is not dict or type(observation) is not dict:
        raise FormalCloudEvaluationError("market-panel row changed type")
    schema = requirement.get("schema")
    if schema == DAILY_REQUIREMENT_SCHEMA:
        checked = _parse_daily_requirements([dict(requirement)])
        requirement_id = next(iter(checked))
        checked_observation = _exact_object(
            dict(observation),
            ("schema", "requirement_id", "security_id", "session",
             "disposition", "open", "reason"),
            "daily observation",
        )
        if (
            checked_observation["schema"] != DAILY_OBSERVATION_SCHEMA
            or checked_observation["requirement_id"] != requirement_id
            or checked_observation["security_id"]
            != checked[requirement_id]["security_id"]
            or checked_observation["session"] != checked[requirement_id]["session"]
        ):
            raise FormalCloudEvaluationError(
                "daily observation does not match its requirement"
            )
        if checked_observation["disposition"] == "observation":
            _decimal(checked_observation["open"], "daily open", positive=True)
            if checked_observation["reason"] is not None:
                raise FormalCloudEvaluationError("daily observation carries a refusal")
        elif checked_observation["disposition"] == "named_refusal":
            if checked_observation["open"] is not None:
                raise FormalCloudEvaluationError("daily refusal carries an open")
            _safe_id(checked_observation["reason"], "daily refusal reason")
        else:
            raise FormalCloudEvaluationError("daily observation disposition changed")
        role = "daily_requirements"
        role_ordinal = 0
    elif schema == MINUTE_REQUIREMENT_SCHEMA:
        checked = _parse_minute_requirements([dict(requirement)])
        requirement_id = next(iter(checked))
        checked_observation = _exact_object(
            dict(observation),
            ("schema", "requirement_id", "security_id", "publication_at_utc",
             "disposition", "last_price", "last_bar_end_utc", "reason"),
            "minute observation",
        )
        if (
            checked_observation["schema"] != MINUTE_OBSERVATION_SCHEMA
            or checked_observation["requirement_id"] != requirement_id
            or checked_observation["security_id"]
            != checked[requirement_id]["security_id"]
            or checked_observation["publication_at_utc"]
            != checked[requirement_id]["publication_at_utc"]
        ):
            raise FormalCloudEvaluationError(
                "minute observation does not match its requirement"
            )
        publication = _utc(
            checked_observation["publication_at_utc"], "minute publication"
        )
        if checked_observation["disposition"] == "observation":
            _decimal(
                checked_observation["last_price"], "minute last price",
                positive=True,
            )
            ended = _utc(
                checked_observation["last_bar_end_utc"], "minute bar end"
            )
            if ended >= publication or checked_observation["reason"] is not None:
                raise FormalCloudEvaluationError(
                    "minute observation is not strictly prepublication"
                )
        elif checked_observation["disposition"] == "named_refusal":
            if (
                checked_observation["last_price"] is not None
                or checked_observation["last_bar_end_utc"] is not None
            ):
                raise FormalCloudEvaluationError("minute refusal carries a price")
            _safe_id(checked_observation["reason"], "minute refusal reason")
        else:
            raise FormalCloudEvaluationError("minute observation disposition changed")
        role = "minute_requirements"
        role_ordinal = 1
    else:
        raise FormalCloudEvaluationError("unknown market-panel requirement schema")
    key = _role_row_key(role, requirement)
    if role_ordinal in state.last_keys and key <= state.last_keys[role_ordinal]:
        raise FormalCloudEvaluationError(
            "market-panel rows are duplicated or reordered within a role"
        )
    state.last_keys[role_ordinal] = key
    payload = _canonical_bytes({"role": role, "observation": checked_observation})
    row_digest = int.from_bytes(
        hashlib.sha256(b"arv2-formal-market-panel-row-v1\0" + payload).digest(),
        "big",
    )
    state.modular_sum = (state.modular_sum + row_digest) % (1 << 256)
    state.bitwise_xor ^= row_digest
    state.count += 1
    _authority_update(value, state)
    return value


def _finish_formal_market_panel_digest_impl(
    digest: FormalMarketPanelDigest,
    *,
    _authority_require: object,
    _authority_update: object,
) -> tuple[str, int]:
    """Seal one History pass and return its exact digest and census."""

    _value, state = _authority_require(digest)
    if state.finished or state.count != state.expected_count:
        raise FormalCloudEvaluationError(
            "market-panel digest is already sealed or incomplete"
        )
    state.finished = True
    commitment = {
        "domain": MARKET_PANEL_DOMAIN,
        "schema": MARKET_PANEL_STREAM_SCHEMA,
        "observation_count": state.count,
        "row_digest_modular_sum": f"{state.modular_sum:064x}",
        "row_digest_bitwise_xor": f"{state.bitwise_xor:064x}",
    }
    _authority_update(_value, state)
    return hashlib.sha256(_canonical_bytes(commitment)).hexdigest(), state.count


def _parse_terminal_rows(rows: object) -> dict[tuple[str, str, int | None], dict[str, object]]:
    supplied = _exact_list(rows, "terminal dispositions")
    _require_role_row_order(supplied, "terminal_dispositions")
    result: dict[tuple[str, str, int | None], dict[str, object]] = {}
    for value in supplied:
        row = _exact_object(value, _TERMINAL_FIELDS, "terminal disposition")
        if row["schema"] != TERMINAL_OBJECT_SCHEMA:
            raise FormalCloudEvaluationError("terminal disposition schema changed")
        kind = _safe_id(row["slot_kind"], "terminal slot kind")
        if kind not in {"decision_horizon", "economic_daily"}:
            raise FormalCloudEvaluationError("terminal slot kind changed")
        horizon = row["horizon"]
        if kind == "decision_horizon":
            if type(horizon) is not int or horizon not in HORIZONS:
                raise FormalCloudEvaluationError("terminal decision horizon changed")
        elif horizon is not None:
            raise FormalCloudEvaluationError("economic terminal gained a horizon")
        slot_id = _safe_id(row["slot_id"], "terminal slot id")
        key = (kind, slot_id, horizon)
        if key in result:
            raise FormalCloudEvaluationError("terminal slot duplicated")
        disposition = row["disposition"]
        if disposition == "terminal_payoff":
            payoff = _decimal(row["stock_return"], "terminal payoff")
            if payoff < Decimal("-1") or row["reason"] is not None:
                raise FormalCloudEvaluationError("terminal payoff changed")
        elif disposition == "benchmark_splice_continuation":
            if kind != "economic_daily" or row["stock_return"] is not None or row["reason"] is not None:
                raise FormalCloudEvaluationError("benchmark splice changed")
        elif disposition == "named_terminal_refusal":
            if row["stock_return"] is not None:
                raise FormalCloudEvaluationError("terminal refusal carries a payoff")
            _safe_id(row["reason"], "terminal refusal reason")
        else:
            raise FormalCloudEvaluationError("terminal disposition changed")
        _sha(row["terminal_lineage_sha256"], "terminal lineage")
        _utc(row["available_at_utc"], "terminal availability")
        result[key] = row
    return result


def _seed_record_without_identity(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: row[key]
        for key in _SEED_FIELDS
        if key not in {"schema", "seed_id", "seed_sha256"}
    }


def _parse_contribution_seeds(
    rows: object,
    minute_requirements: Mapping[str, dict[str, object]],
) -> dict[tuple[str, str, str], tuple[dict[str, object], ...]]:
    supplied = _exact_list(rows, "contribution seeds")
    _require_role_row_order(supplied, "contribution_seeds")
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    seen: set[str] = set()
    for value in supplied:
        row = _exact_object(value, _SEED_FIELDS, "contribution seed")
        if row["schema"] != CONTRIBUTION_SEED_SCHEMA:
            raise FormalCloudEvaluationError("contribution seed schema changed")
        view = _safe_id(row["source_view_id"], "seed view")
        fold = _safe_id(row["fold_id"], "seed fold")
        security = _security_id(row["security_id"], "seed security")
        if view not in SOURCE_VIEW_IDS or fold not in FORMAL_FOLD_IDS:
            raise FormalCloudEvaluationError("contribution seed escaped formal geometry")
        for name in (
            "representative_c2_row_sha256", "seed_sha256",
        ):
            _sha(row[name], name)
        linked = _exact_list(row["linked_c2_row_sha256s"], "linked C2 hashes")
        if not linked or linked != sorted(set(linked)):
            raise FormalCloudEvaluationError("contribution seed C2 hashes changed")
        for digest in linked:
            _sha(digest, "linked C2 hash")
        if row["representative_c2_row_sha256"] not in linked:
            raise FormalCloudEvaluationError("representative C2 hash is not linked")
        for name in (
            "representative_provider_event_id", "institution_id", "common_event_id",
        ):
            _safe_id(row[name], name)
        if row["rating_action"] not in {"upgrades", "downgrades"}:
            raise FormalCloudEvaluationError("contribution seed rating action changed")
        eligible = _iso_date(row["eligible_session"], "seed eligible session")
        eligible_position = _count(
            row["eligible_session_position"], "seed eligible position"
        )
        publication = row["publication_at_utc"]
        minute_id = row["minute_requirement_id"]
        if publication is None:
            if minute_id is not None:
                raise FormalCloudEvaluationError("missing publication gained a minute request")
        else:
            published = _utc(publication, "seed publication")
            opened = datetime.combine(eligible, time(9, 30), _NEW_YORK).astimezone(
                timezone.utc
            )
            if published >= opened:
                raise FormalCloudEvaluationError("seed publication is not pre-open")
            if (
                type(minute_id) is not str
                or minute_id != build_minute_market_requirement_id(
                    security_id=security, publication_at_utc=publication
                )
                or minute_id not in minute_requirements
            ):
                raise FormalCloudEvaluationError("seed minute requirement changed")
        _decimal(row["base_absolute_firm_weight"], "base firm weight", positive=True)
        intervals = _exact_list(row["active_intervals"], "seed active intervals")
        previous_end: int | None = None
        checked_intervals: list[tuple[int, int]] = []
        for raw in intervals:
            pair = _exact_list(raw, "seed active interval")
            if len(pair) != 2:
                raise FormalCloudEvaluationError("seed active interval shape changed")
            start = _count(pair[0], "seed interval start")
            end = _count(pair[1], "seed interval end", minimum=1)
            if start >= end or start < eligible_position or (
                previous_end is not None and start <= previous_end
            ):
                raise FormalCloudEvaluationError("seed active intervals overlap or changed")
            checked_intervals.append((start, end))
            previous_end = end
        if not checked_intervals:
            raise FormalCloudEvaluationError("contribution seed has no active interval")
        expected_id, expected_hash = _identified(
            "arv2-formal-contribution-seed-",
            CONTRIBUTION_SEED_SCHEMA,
            _seed_record_without_identity(row),
        )
        seed_id = _safe_id(row["seed_id"], "contribution seed id")
        if seed_id != expected_id or row["seed_sha256"] != expected_hash or seed_id in seen:
            raise FormalCloudEvaluationError("contribution seed identity changed")
        seen.add(seed_id)
        key = (view, fold, security)
        grouped.setdefault(key, []).append(row)
    return {
        key: tuple(sorted(value, key=lambda item: item["seed_id"]))
        for key, value in grouped.items()
    }


def _seed_is_active(row: Mapping[str, object], position: int) -> bool:
    return any(start <= position < end for start, end in row["active_intervals"])


def _contribution_for_decision(
    seed: Mapping[str, object], decision_session: str, decision_position: int
) -> dict[str, object]:
    age = decision_position - seed["eligible_session_position"]
    if age < 0:
        raise FormalCloudEvaluationError("active contribution is from the future")
    decay = _decay(age)
    with localcontext(_context()):
        weight = +(
            _decimal(seed["base_absolute_firm_weight"], "base firm weight") * decay
        )
    semantic = {
        "representative_c2_row_sha256": seed["representative_c2_row_sha256"],
        "linked_c2_row_sha256s": seed["linked_c2_row_sha256s"],
        "representative_provider_event_id": seed["representative_provider_event_id"],
        "decision_session": decision_session,
        "security_id": seed["security_id"],
        "institution_id": seed["institution_id"],
        "common_event_id": seed["common_event_id"],
        "rating_action": seed["rating_action"],
        "publication_at_utc": seed["publication_at_utc"],
        "eligible_session": seed["eligible_session"],
        "age_sessions": age,
        "decay_weight": _decimal_text(decay),
        "firm_absolute_decayed_weight": _decimal_text(weight),
    }
    lineage = hashlib.sha256(_canonical_bytes(semantic)).hexdigest()
    return {
        "contribution_seed_id": seed["seed_id"],
        "contribution_lineage_sha256": lineage,
        "publication_at_utc": seed["publication_at_utc"],
        "minute_requirement_id": seed["minute_requirement_id"],
        "firm_absolute_decayed_weight": _decimal_text(weight),
    }


def _contribution_state(
    seeds: Sequence[Mapping[str, object]], decision_session: str, position: int
) -> tuple[tuple[dict[str, object], ...], str]:
    values = tuple(
        _contribution_for_decision(seed, decision_session, position)
        for seed in seeds if _seed_is_active(seed, position)
    )
    values = tuple(sorted(values, key=lambda item: item["contribution_lineage_sha256"]))
    digest = hashlib.sha256(
        _canonical_bytes({"domain": CONTRIBUTION_STATE_DOMAIN, "contributions": values})
    ).hexdigest()
    return values, digest


def _decision_identity(row: Mapping[str, object]) -> tuple[str, str]:
    if row["disposition"] == "scored_decision":
        record = {
            "source_view_id": row["source_view_id"],
            "fold_id": row["fold_id"],
            "decision_session": row["decision_session"],
            "security_id": row["security_id"],
            "final_scoring_row_sha256": row["source_row_sha256"],
            "scoring_result_id": row["scoring_result_id"],
            "scoring_result_sha256": row["scoring_result_sha256"],
            "scoring_contract_id": row["scoring_contract_id"],
            "scoring_contract_sha256": row["scoring_contract_sha256"],
        }
        return _identified(
            "arv2-formal-production-decision-",
            "arv2-formal-production-decision-lineage-v1",
            record,
        )
    record = {
        "source_view_id": row["source_view_id"],
        "fold_id": row["fold_id"],
        "decision_session": row["decision_session"],
        "security_id": row["security_id"],
        "disposition": row["scoring_disposition"],
        "source_refusal_sha256": row["source_row_sha256"],
        "scoring_result_id": row["scoring_result_id"],
        "scoring_result_sha256": row["scoring_result_sha256"],
    }
    return _identified(
        "arv2-formal-production-refusal-",
        "arv2-formal-production-scoring-refusal-v1",
        record,
    )


def _axis_horizon_lookup(
    axes: tuple[_evaluation.FoldSessionAxis, ...],
) -> dict[tuple[str, int], tuple[date, tuple[int, ...]]]:
    temporary: dict[tuple[str, int], tuple[date, list[int]]] = {}
    for axis in axes:
        for point in axis.sessions:
            key = (axis.fold_id, point.session_position)
            prior = temporary.setdefault(key, (point.session, []))
            if prior[0] != point.session:
                raise FormalCloudEvaluationError(
                    "fold axes assign one position to multiple sessions"
                )
            prior[1].append(axis.horizon_sessions)
    return {
        key: (session, tuple(horizons))
        for key, (session, horizons) in temporary.items()
    }


def _parse_decisions(
    rows: object,
    seeds: Mapping[tuple[str, str, str], tuple[dict[str, object], ...]],
    daily_requirements: Mapping[str, dict[str, object]],
    result_bindings: Sequence[Mapping[str, object]],
    benchmark_security_id: str,
    fold_axes: tuple[_evaluation.FoldSessionAxis, ...],
) -> tuple[dict[str, object], ...]:
    supplied = _exact_list(rows, "decision joins")
    _require_role_row_order(supplied, "decision_joins")
    results = {item["result_id"]: item for item in result_bindings}
    parsed: list[dict[str, object]] = []
    order: list[tuple[int, int, str]] = []
    keys_by_view: dict[str, set[tuple[str, int, str]]] = {
        view: set() for view in SOURCE_VIEW_IDS
    }
    component_dates: dict[tuple[str, str], str] = {}
    axis_horizons = _axis_horizon_lookup(fold_axes)
    for value in supplied:
        row = _exact_object(value, _DECISION_FIELDS, "decision join")
        if row["schema"] != DECISION_JOIN_SCHEMA:
            raise FormalCloudEvaluationError("decision join schema changed")
        view = _safe_id(row["source_view_id"], "decision view")
        fold = _safe_id(row["fold_id"], "decision fold")
        if view not in SOURCE_VIEW_IDS or fold not in FORMAL_FOLD_IDS:
            raise FormalCloudEvaluationError("decision escaped formal geometry")
        session = _iso_date(row["decision_session"], "decision session").isoformat()
        position = _count(row["session_position"], "decision position")
        axis_entry = axis_horizons.get((fold, position))
        if axis_entry is None or axis_entry[0].isoformat() != session:
            raise FormalCloudEvaluationError(
                "decision is outside the exact fold-horizon axes"
            )
        expected_horizons = axis_entry[1]
        security = _security_id(row["security_id"], "decision security")
        result = results.get(row["scoring_result_id"])
        if (
            result is None
            or result["fold_id"] != fold
            or row["scoring_result_sha256"] != result["result_sha256"]
            or row["scoring_contract_id"] != SCORING_CONTRACT_ID
            or row["scoring_contract_sha256"] != SCORING_CONTRACT_SHA256
        ):
            raise FormalCloudEvaluationError("decision scorer binding changed")
        _sha(row["source_row_sha256"], "decision source row hash")
        expected_id, expected_hash = _decision_identity(row)
        if row["decision_id"] != expected_id or row["decision_lineage_sha256"] != expected_hash:
            raise FormalCloudEvaluationError("decision lineage does not rederive")
        base_key = (fold, position, security)
        if base_key in keys_by_view[view]:
            raise FormalCloudEvaluationError("decision terminal duplicated")
        keys_by_view[view].add(base_key)
        if row["disposition"] == "named_preoutcome_refusal":
            _safe_id(row["scoring_disposition"], "scoring refusal")
            nullable = (
                "industry_id", "common_event_component_id", "structural_zero",
                "firm_specific_score", "global_score", "continuous_controls",
                "binary_controls", "realized_volatility_60d",
                "earnings_anchor_signed_session_distance",
                "contribution_state_sha256",
                "entry_daily_requirement_id", "benchmark_entry_daily_requirement_id",
            )
            if any(row[name] is not None for name in nullable) or row["contribution_count"] != 0 or row["horizon_exits"] != []:
                raise FormalCloudEvaluationError("preoutcome refusal carries scored/outcome fields")
        elif row["disposition"] == "scored_decision":
            if row["scoring_disposition"] not in {"included_active", "included_structural_zero"}:
                raise FormalCloudEvaluationError("scored decision disposition changed")
            industry = _safe_id(row["industry_id"], "decision industry")
            component = _safe_id(
                row["common_event_component_id"], "decision common-event component"
            )
            prior = component_dates.setdefault((view, component), session)
            if prior != session:
                raise FormalCloudEvaluationError("common-event component crosses dates")
            if type(row["structural_zero"]) is not bool:
                raise FormalCloudEvaluationError("structural-zero flag changed")
            firm = _decimal(row["firm_specific_score"], "firm score")
            global_score = _decimal(row["global_score"], "global score")
            if not Decimal("-4") <= firm <= Decimal("4") or not Decimal("-4") <= global_score <= Decimal("4"):
                raise FormalCloudEvaluationError("decision score escaped clip")
            continuous = _exact_list(row["continuous_controls"], "continuous controls")
            binary = _exact_list(row["binary_controls"], "binary controls")
            if len(continuous) != 19 or len(binary) != 6:
                raise FormalCloudEvaluationError("decision lacks all 25 controls")
            for control in continuous:
                _decimal(control, "continuous control")
            if any(type(control) is not int or control not in {0, 1} for control in binary):
                raise FormalCloudEvaluationError("binary controls changed")
            _decimal(
                row["realized_volatility_60d"],
                "decision realized volatility",
            )
            earnings_distance = row["earnings_anchor_signed_session_distance"]
            if earnings_distance is not None and type(earnings_distance) is not int:
                raise FormalCloudEvaluationError(
                    "earnings-anchor signed session distance changed type"
                )
            contributions, state_hash = _contribution_state(
                seeds.get((view, fold, security), ()), session, position
            )
            if (
                row["contribution_count"] != len(contributions)
                or row["contribution_state_sha256"] != state_hash
                or (row["structural_zero"] and contributions)
                or (row["structural_zero"] and (firm != 0 or global_score != 0))
            ):
                raise FormalCloudEvaluationError("decision contribution state changed")
            entry_id = row["entry_daily_requirement_id"]
            benchmark_entry_id = row["benchmark_entry_daily_requirement_id"]
            expected_entry = build_daily_market_requirement_id(
                security_id=security, session=session
            )
            expected_benchmark = build_daily_market_requirement_id(
                security_id=benchmark_security_id, session=session
            )
            if (
                entry_id != expected_entry or benchmark_entry_id != expected_benchmark
                or entry_id not in daily_requirements
                or benchmark_entry_id not in daily_requirements
            ):
                raise FormalCloudEvaluationError("decision entry requirement changed")
            exits = _exact_list(row["horizon_exits"], "decision horizon exits")
            if len(exits) != len(expected_horizons):
                raise FormalCloudEvaluationError(
                    "decision horizon exits differ from its exact fold axes"
                )
            for raw_exit, expected_horizon in zip(
                exits, expected_horizons, strict=True
            ):
                exit_row = _exact_object(
                    raw_exit,
                    ("horizon", "exit_session", "exit_session_position",
                     "stock_daily_requirement_id", "benchmark_daily_requirement_id"),
                    "decision horizon exit",
                )
                if exit_row["horizon"] != expected_horizon or exit_row["exit_session_position"] != position + expected_horizon:
                    raise FormalCloudEvaluationError("decision exit is not its exact horizon")
                exit_session = _iso_date(exit_row["exit_session"], "exit session").isoformat()
                stock_id = build_daily_market_requirement_id(
                    security_id=security, session=exit_session
                )
                benchmark_id = build_daily_market_requirement_id(
                    security_id=benchmark_security_id, session=exit_session
                )
                if (
                    exit_row["stock_daily_requirement_id"] != stock_id
                    or exit_row["benchmark_daily_requirement_id"] != benchmark_id
                    or stock_id not in daily_requirements
                    or benchmark_id not in daily_requirements
                ):
                    raise FormalCloudEvaluationError("decision exit requirement changed")
            # Keep local variables live in the exact row validation; values are
            # re-parsed when constructing typed evaluator rows below.
            _ = industry
        else:
            raise FormalCloudEvaluationError("decision disposition changed")
        parsed.append(row)
        order.append((SOURCE_VIEW_IDS.index(view) * len(FORMAL_FOLD_IDS) + FORMAL_FOLD_IDS.index(fold), position, security))
    if keys_by_view[SOURCE_VIEW_IDS[0]] != keys_by_view[SOURCE_VIEW_IDS[1]]:
        raise FormalCloudEvaluationError("current/censored decision terminal census differs")
    return tuple(parsed)


def _parse_economic_joins(
    rows: object, *, streamed: bool = False,
) -> tuple[dict[str, object], ...]:
    supplied = _exact_list(rows, "economic joins")
    _require_role_row_order(supplied, "economic_joins")
    result: list[dict[str, object]] = []
    order: list[tuple[int, int, int]] = []
    keys: dict[str, set[tuple[str, int]]] = {view: set() for view in SOURCE_VIEW_IDS}
    date_positions: dict[str, int] = {}
    position_dates: dict[int, str] = {}
    for value in supplied:
        fields = _STREAMED_ECONOMIC_FIELDS if streamed else _ECONOMIC_FIELDS
        row = _exact_object(value, fields, "economic join")
        if row["schema"] != ECONOMIC_JOIN_SCHEMA:
            raise FormalCloudEvaluationError("economic join schema changed")
        view = _safe_id(row["source_view_id"], "economic view")
        fold = _safe_id(row["fold_id"], "economic fold")
        if view not in SOURCE_VIEW_IDS or fold not in FORMAL_FOLD_IDS:
            raise FormalCloudEvaluationError("economic join escaped formal geometry")
        session = _iso_date(row["session"], "economic session").isoformat()
        position = _count(row["session_position"], "economic position")
        if streamed:
            kind = row["economic_observation_kind"]
            if (
                kind not in ECONOMIC_OBSERVATION_KINDS
                or type(row["h20_decision_eligible"]) is not bool
                or row["h20_decision_eligible"]
                is not (kind == "h20_decision_return_interval")
            ):
                raise FormalCloudEvaluationError(
                    "streamed economic observation kind changed"
                )
            if kind == "terminal_liquidation_cost":
                if row["next_session"] is not None or row["next_session_position"] is not None:
                    raise FormalCloudEvaluationError(
                        "terminal liquidation acquired a next session"
                    )
            else:
                next_session = _iso_date(
                    row["next_session"], "next economic session"
                ).isoformat()
                if (
                    row["next_session_position"] != position + 1
                    or next_session <= session
                ):
                    raise FormalCloudEvaluationError(
                        "economic next session changed"
                    )
        else:
            next_session = _iso_date(
                row["next_session"], "next economic session"
            ).isoformat()
            if row["next_session_position"] != position + 1 or next_session <= session:
                raise FormalCloudEvaluationError("economic next session changed")
        if date_positions.setdefault(session, position) != position or position_dates.setdefault(position, session) != session:
            raise FormalCloudEvaluationError("economic session position is inconsistent")
        record = {
            key: row[key]
            for key in fields
            if key not in {"schema", "source_lineage_sha256"}
        }
        expected_hash = hashlib.sha256(
            _canonical_bytes({"schema": ECONOMIC_JOIN_SCHEMA, **record})
        ).hexdigest()
        if row["source_lineage_sha256"] != expected_hash:
            raise FormalCloudEvaluationError("economic join lineage changed")
        key = (fold, position)
        if key in keys[view]:
            raise FormalCloudEvaluationError("economic join duplicated")
        keys[view].add(key)
        result.append(row)
        order.append((SOURCE_VIEW_IDS.index(view), FORMAL_FOLD_IDS.index(fold), position))
    if keys[SOURCE_VIEW_IDS[0]] != keys[SOURCE_VIEW_IDS[1]]:
        raise FormalCloudEvaluationError("economic source-view axes differ")
    for view in SOURCE_VIEW_IDS:
        for fold in FORMAL_FOLD_IDS:
            if sum(item[0] == fold for item in keys[view]) < 20:
                raise FormalCloudEvaluationError("economic fold lacks a block-capable axis")
    return tuple(sorted(
        result,
        key=lambda row: (
            SOURCE_VIEW_IDS.index(row["source_view_id"]),
            FORMAL_FOLD_IDS.index(row["fold_id"]), row["session_position"],
        ),
    ))


def _daily_open(
    requirement_id: str, observations: Mapping[str, dict[str, object]]
) -> Decimal | None:
    value = observations[requirement_id]
    return (
        _decimal(value["open"], "daily open", positive=True)
        if value["disposition"] == "observation"
        else None
    )


def _market_return(
    start_requirement_id: str,
    end_requirement_id: str,
    observations: Mapping[str, dict[str, object]],
) -> Decimal | None:
    start = _daily_open(start_requirement_id, observations)
    end = _daily_open(end_requirement_id, observations)
    if start is None or end is None:
        return None
    with localcontext(_context()):
        return +(end / start - Decimal(1))


def _decision_jump(
    *, row: Mapping[str, object], contributions: Sequence[Mapping[str, object]],
    daily: Mapping[str, dict[str, object]], minute: Mapping[str, dict[str, object]],
) -> Decimal | None:
    if row["structural_zero"] is True:
        return Decimal(0)
    entry = _daily_open(row["entry_daily_requirement_id"], daily)
    if not contributions:
        return Decimal(0)
    if entry is None:
        return None
    numerator = Decimal(0)
    denominator = Decimal(0)
    with localcontext(_context()):
        for item in contributions:
            minute_id = item["minute_requirement_id"]
            if minute_id is None:
                return None
            observation = minute[minute_id]
            if observation["disposition"] != "observation":
                return None
            publication_price = _decimal(
                observation["last_price"], "publication price", positive=True
            )
            weight = _decimal(
                item["firm_absolute_decayed_weight"], "jump weight", positive=True
            )
            numerator += weight * abs(entry / publication_price - Decimal(1))
            denominator += weight
        if denominator <= 0:
            return None
        return +(numerator / denominator)


def _terminal_for_decision(
    *, row: Mapping[str, object], horizon: int,
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
) -> tuple[Decimal | None, _evaluation.RefusalReason | None, tuple[str, str, int | None] | None]:
    slot_id = build_decision_terminal_slot_id(
        decision_id=row["decision_id"], horizon=horizon
    )
    key = ("decision_horizon", slot_id, horizon)
    terminal = terminals.get(key)
    if terminal is None:
        return None, _evaluation.RefusalReason.MISSING_OUTCOME, None
    if terminal["disposition"] == "terminal_payoff":
        return _decimal(terminal["stock_return"], "terminal return"), None, key
    return None, _evaluation.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED, key


def _decision_terminal_key(
    *, row: Mapping[str, object], horizon: int,
) -> tuple[str, str, int]:
    """Derive the exact lifecycle slot before consulting ordinary bars.

    A row in the terminal package is an affirmative statement that the
    ordinary market-data continuation is not authoritative for this slot.
    Therefore its presence must be decided before a potentially fill-forward
    or otherwise numeric daily observation is considered.
    """

    return (
        "decision_horizon",
        build_decision_terminal_slot_id(
            decision_id=row["decision_id"], horizon=horizon
        ),
        horizon,
    )


def _outcome_lineage(domain: str, record: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes({"domain": domain, **record})).hexdigest()


def _event_rows(
    *, view: str, decisions: Sequence[Mapping[str, object]],
    seeds: Mapping[tuple[str, str, str], tuple[dict[str, object], ...]],
    daily: Mapping[str, dict[str, object]],
    minute: Mapping[str, dict[str, object]],
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
    used_terminals: set[tuple[str, str, int | None]],
    fold_axes: tuple[_evaluation.FoldSessionAxis, ...],
) -> tuple[tuple[_evaluation.EvaluationRow, ...], tuple[_evaluation.EvaluationRefusal, ...]]:
    accepted: list[_evaluation.EvaluationRow] = []
    refused: list[_evaluation.EvaluationRefusal] = []
    axis_horizons = _axis_horizon_lookup(fold_axes)
    for row in decisions:
        if row["source_view_id"] != view:
            continue
        fold = row["fold_id"]
        session = _iso_date(row["decision_session"], "decision session")
        position = row["session_position"]
        security = row["security_id"]
        axis_entry = axis_horizons.get((fold, position))
        if axis_entry is None or axis_entry[0] != session:
            raise FormalCloudEvaluationError(
                "evaluation row escaped its exact fold-horizon axes"
            )
        active_horizons = axis_entry[1]
        if row["disposition"] == "named_preoutcome_refusal":
            for horizon in active_horizons:
                refused.append(
                    _evaluation.build_evaluation_refusal(
                        source_lineage_sha256=row["decision_lineage_sha256"],
                        fold_id=fold,
                        decision_session=session,
                        session_position=position,
                        security_id=security,
                        horizon_sessions=horizon,
                        reason=_evaluation.RefusalReason.MISSING_PREOPEN_CONTROL,
                    )
                )
            continue
        decision_seeds = seeds.get((view, fold, security), ())
        contributions, _ = _contribution_state(
            decision_seeds, row["decision_session"], position
        )
        active_actions = tuple(sorted({
            seed["rating_action"] for seed in decision_seeds
            if _seed_is_active(seed, position)
        }))
        rating_action = active_actions[0] if len(active_actions) == 1 else None
        jump = _decision_jump(
            row=row, contributions=contributions, daily=daily, minute=minute
        )
        for exit_row in row["horizon_exits"]:
            horizon = exit_row["horizon"]
            reason: _evaluation.RefusalReason | None = None
            if jump is None:
                reason = _evaluation.RefusalReason.MISSING_OUTCOME
            benchmark_return = _market_return(
                row["benchmark_entry_daily_requirement_id"],
                exit_row["benchmark_daily_requirement_id"], daily,
            )
            if benchmark_return is None:
                reason = _evaluation.RefusalReason.MISSING_OUTCOME
            terminal_key: tuple[str, str, int | None] | None = None
            candidate_terminal_key = _decision_terminal_key(
                row=row, horizon=horizon
            )
            if candidate_terminal_key in terminals:
                stock_return, terminal_reason, terminal_key = _terminal_for_decision(
                    row=row, horizon=horizon, terminals=terminals
                )
                if terminal_key is not None:
                    used_terminals.add(terminal_key)
                if terminal_reason is not None:
                    reason = terminal_reason
            else:
                stock_return = _market_return(
                    row["entry_daily_requirement_id"],
                    exit_row["stock_daily_requirement_id"], daily,
                )
                if stock_return is None:
                    reason = _evaluation.RefusalReason.MISSING_OUTCOME
            if reason is not None:
                refused.append(
                    _evaluation.build_evaluation_refusal(
                        source_lineage_sha256=row["decision_lineage_sha256"],
                        fold_id=fold, decision_session=session,
                        session_position=position, security_id=security,
                        horizon_sessions=horizon, reason=reason,
                    )
                )
                continue
            assert jump is not None and stock_return is not None and benchmark_return is not None
            with localcontext(_context()):
                excess = +(stock_return - benchmark_return)
            accepted.append(
                _evaluation.build_evaluation_row(
                    source_lineage_sha256=row["decision_lineage_sha256"],
                    fold_id=fold, decision_session=session,
                    session_position=position, security_id=security,
                    industry_id=row["industry_id"],
                    common_event_component_id=row["common_event_component_id"],
                    horizon_sessions=horizon,
                    firm_specific_score=_decimal(row["firm_specific_score"], "firm score"),
                    global_score=_decimal(row["global_score"], "global score"),
                    structural_zero=row["structural_zero"],
                    continuous_control_values=tuple(
                        _decimal(item, "continuous control")
                        for item in row["continuous_controls"]
                    ),
                    binary_control_values=tuple(row["binary_controls"]),
                    active_event_indicator=int(not row["structural_zero"]),
                    absolute_contribution_weighted_publication_to_entry_jump=jump,
                    excess_total_return=excess,
                    rating_action=rating_action,
                    earnings_anchor_signed_session_distance=(
                        row["earnings_anchor_signed_session_distance"]
                    ),
                    gross_security_total_return=stock_return,
                    benchmark_total_return=benchmark_return,
                )
            )
    key = lambda item: (
        FORMAL_FOLD_IDS.index(item.fold_id), item.session_position,
        item.security_id, item.horizon_sessions,
    )
    return tuple(sorted(accepted, key=key)), tuple(sorted(refused, key=key))


def _earnings_cohort(distance: int | None) -> str | None:
    if distance is None:
        return None
    if distance == 0:
        return "exact_earnings_day"
    if 1 <= distance <= 2:
        return "one_to_two_days_after_earnings"
    if 3 <= distance <= 5:
        return "three_to_five_days_after_earnings"
    if distance > 5:
        return "over_five_days_after_earnings"
    return "pre_earnings"


def _capture_report_sufficient_statistics(
    *, state: _CompactStreamState, view: str,
    decisions: Sequence[Mapping[str, object]],
    accepted: Sequence[_evaluation.EvaluationRow],
    refused: Sequence[_evaluation.EvaluationRefusal],
    fold_id: str, decision_session: date, session_position: int,
    h20_axis_active: bool,
) -> None:
    """Retain report-only typed sufficient statistics, never market rows."""

    accepted_by_key = {
        (item.security_id, item.horizon_sessions): item for item in accepted
    }
    refused_by_key = {
        (item.security_id, item.horizon_sessions): item for item in refused
    }
    if len(accepted_by_key) != len(accepted) or len(refused_by_key) != len(refused):
        raise FormalCloudEvaluationError(
            "report outcome sufficient-statistic key duplicated"
        )
    decision_rows = {
        item["security_id"]: item for item in decisions
        if item["source_view_id"] == view
    }
    if len(decision_rows) != sum(
        item["source_view_id"] == view for item in decisions
    ):
        raise FormalCloudEvaluationError("report decision security duplicated")
    for security_id, decision in decision_rows.items():
        active_seeds = tuple(
            seed for seed in state.seeds.get(
                (view, decision["fold_id"], security_id), ()
            )
            if _seed_is_active(seed, decision["session_position"])
        )
        action_ids = tuple(sorted({seed["rating_action"] for seed in active_seeds}))
        event_seeds: dict[tuple[str, str, str], Mapping[str, object]] = {}
        for seed in active_seeds:
            event_key = (
                seed["representative_provider_event_id"],
                seed["common_event_id"], seed["rating_action"],
            )
            prior = event_seeds.setdefault(event_key, seed)
            if prior["representative_c2_row_sha256"] != seed[
                "representative_c2_row_sha256"
            ]:
                raise FormalCloudEvaluationError(
                    "directional event maps to multiple representative rows"
                )
        decision_horizons = tuple(sorted(
            horizon
            for candidate_security, horizon in (
                set(accepted_by_key) | set(refused_by_key)
            )
            if candidate_security == security_id
        ))
        if not decision_horizons:
            raise FormalCloudEvaluationError(
                "report decision has no exact horizon terminal"
            )
        for horizon in decision_horizons:
            outcome = accepted_by_key.get((security_id, horizon))
            refusal = refused_by_key.get((security_id, horizon))
            if (outcome is None) is (refusal is None):
                raise FormalCloudEvaluationError(
                    "report outcome terminal is not exhaustive"
                )
            state.decision_report_observations.append(
                _DecisionReportObservation(
                    source_view_id=view, fold_id=decision["fold_id"],
                    decision_session=_iso_date(
                        decision["decision_session"], "report decision session"
                    ),
                    session_position=decision["session_position"],
                    security_id=security_id,
                    common_event_component_id=(
                        None if outcome is None
                        else outcome.common_event_component_id
                    ),
                    rating_actions=action_ids,
                    earnings_anchor_signed_session_distance=(
                        decision["earnings_anchor_signed_session_distance"]
                    ),
                    horizon_sessions=horizon,
                    firm_specific_score=(
                        None if decision["firm_specific_score"] is None
                        else _decimal(
                            decision["firm_specific_score"], "report firm score"
                        )
                    ),
                    global_score=(
                        None if decision["global_score"] is None
                        else _decimal(
                            decision["global_score"], "report global score"
                        )
                    ),
                    gross_excess_total_return=(
                        None if outcome is None else outcome.excess_total_return
                    ),
                    refusal_reason=(
                        None if refusal is None else refusal.reason.value
                    ),
                )
            )
            for event_key, seed in event_seeds.items():
                state.directional_event_report_observations.append(
                    _DirectionalEventReportObservation(
                        source_view_id=view, fold_id=decision["fold_id"],
                        decision_session=_iso_date(
                            decision["decision_session"],
                            "directional event decision session",
                        ),
                        session_position=decision["session_position"],
                        event_id=event_key[0], security_id=security_id,
                        common_event_component_id=(
                            decision["common_event_component_id"]
                            if decision["common_event_component_id"] is not None
                            else seed["common_event_id"]
                        ),
                        rating_action=seed["rating_action"],
                        earnings_anchor_signed_session_distance=(
                            decision["earnings_anchor_signed_session_distance"]
                        ),
                        horizon_sessions=horizon,
                        gross_security_total_return=(
                            None if outcome is None
                            else outcome.gross_security_total_return
                        ),
                        benchmark_total_return=(
                            None if outcome is None
                            else outcome.benchmark_total_return
                        ),
                        gross_excess_total_return=(
                            None if outcome is None
                            else outcome.excess_total_return
                        ),
                        refusal_reason=(
                            None if refusal is None else refusal.reason.value
                        ),
                    )
                )

    h20_rows = tuple(item for item in accepted if item.horizon_sessions == 20)
    h20_refusals = tuple(item for item in refused if item.horizon_sessions == 20)
    if not h20_axis_active:
        return
    subset_specs = (
        *(f"cohort:{item}" for item in (
            "exact_earnings_day", "one_to_two_days_after_earnings",
            "three_to_five_days_after_earnings",
            "over_five_days_after_earnings", "pre_earnings",
        )),
        "exclusion:earnings_exclusion_pm2",
        "exclusion:earnings_exclusion_pm5",
    )
    # Use this block's decision rows directly; the retained observation list
    # above spans prior sessions and is not an input to the date cross-section.
    decision_by_security = {
        item["security_id"]: item for item in decisions
        if item["source_view_id"] == view
    }
    for subset_id in subset_specs:
        if subset_id.startswith("cohort:"):
            cohort_id = subset_id.split(":", 1)[1]
            selected_rows = tuple(
                item for item in h20_rows
                if _earnings_cohort(
                    decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ]
                ) == cohort_id
            )
            selected_refusals = tuple(
                item for item in h20_refusals
                if _earnings_cohort(
                    decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ]
                ) == cohort_id
            )
            unknown_anchor = False
        else:
            exclusion_id = subset_id.split(":", 1)[1]
            radius = 2 if exclusion_id.endswith("pm2") else 5
            selected_rows = tuple(
                item for item in h20_rows
                if (
                    decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ] is not None
                    and abs(decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ]) > radius
                )
            )
            selected_refusals = tuple(
                item for item in h20_refusals
                if (
                    decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ] is not None
                    and abs(decision_by_security[item.security_id][
                        "earnings_anchor_signed_session_distance"
                    ]) > radius
                )
            )
            unknown_anchor = any(
                item["earnings_anchor_signed_session_distance"] is None
                for item in decision_by_security.values()
            )
        beta: Decimal | None = None
        reason: str | None = None
        if unknown_anchor:
            reason = "unknown_earnings_anchor"
        elif selected_refusals:
            reason = "subset_has_named_outcome_refusal"
        else:
            candidate = _evaluation._weighted_fama_macbeth_date(
                selected_rows, arm="firm_specific"
            )
            if type(candidate) is str:
                reason = candidate
            else:
                beta = candidate[0]
        state.subset_fm_report_observations.append(
            _SubsetFmReportObservation(
                source_view_id=view, fold_id=fold_id,
                decision_session=decision_session,
                session_position=session_position,
                subset_id=subset_id, bullish_beta=beta,
                refusal_reason=reason,
            )
        )


def _selected_sleeve(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    positive = tuple(
        sorted(
            (
                (_decimal(row["firm_specific_score"], "economic score"), row["security_id"])
                for row in rows
                if row["disposition"] == "scored_decision"
                and _decimal(row["firm_specific_score"], "economic score") > 0
            ),
            key=lambda item: (-item[0], item[1]),
        )
    )
    count = (len(positive) + 4) // 5
    if count < 5:
        return ()
    return tuple(item[1] for item in positive[:count])


def _economic_security_outcome(
    *, view: str, fold: str, position: int, session: str, next_session: str,
    security: str, benchmark_return: Decimal | None,
    daily: Mapping[str, dict[str, object]],
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
    used_terminals: set[tuple[str, str, int | None]],
) -> _evaluation.EconomicSecurityOutcome:
    start_id = build_daily_market_requirement_id(security_id=security, session=session)
    end_id = build_daily_market_requirement_id(security_id=security, session=next_session)
    terminal_applied = False
    terminal = None
    terminal_key: tuple[str, str, int | None] = (
        "economic_daily",
        build_economic_terminal_slot_id(
            view_id=view, fold_id=fold, session_position=position,
            security_id=security,
        ),
        None,
    )
    terminal = terminals.get(terminal_key)
    if terminal is not None:
        used_terminals.add(terminal_key)
        if terminal["disposition"] == "terminal_payoff":
            value = _decimal(terminal["stock_return"], "economic terminal payoff")
            terminal_applied = True
        elif terminal["disposition"] == "benchmark_splice_continuation":
            value = benchmark_return
        else:
            value = None
    else:
        value = _market_return(start_id, end_id, daily)
    # A known terminal disposition is the return source.  Do not inspect a
    # market value merely to decorate lineage after that physical fact has
    # already resolved (or explicitly refused) the held-name return.
    lineage_record = {
        "view_id": view, "fold_id": fold, "session_position": position,
        "security_id": security, "start_requirement_id": start_id,
        "end_requirement_id": end_id,
        "start_observation": None if terminal is not None else daily[start_id],
        "end_observation": None if terminal is not None else daily[end_id],
        "terminal": terminal,
    }
    lineage = _outcome_lineage("arv2-economic-security-outcome-v1", lineage_record)
    if value is None:
        reason = (
            _evaluation.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED
            if terminal is not None
            else _evaluation.RefusalReason.MISSING_DAILY_SECURITY_RETURN
        )
        return _evaluation.build_economic_security_outcome(
            outcome_lineage_sha256=lineage, security_id=security,
            disposition=_evaluation.EconomicOutcomeDisposition.NAMED_REFUSAL,
            gross_total_return=None, reason=reason,
            terminal_payoff_applied=False,
        )
    return _evaluation.build_economic_security_outcome(
        outcome_lineage_sha256=lineage, security_id=security,
        disposition=_evaluation.EconomicOutcomeDisposition.RETURN,
        gross_total_return=value, reason=None,
        terminal_payoff_applied=terminal_applied,
    )


def _economic_sessions(
    *, view: str, decisions: Sequence[Mapping[str, object]],
    accepted_h20_keys: set[tuple[str, int, str]],
    joins: Sequence[Mapping[str, object]], daily: Mapping[str, dict[str, object]],
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
    used_terminals: set[tuple[str, str, int | None]], benchmark_security_id: str,
) -> tuple[_evaluation.EconomicSession, ...]:
    streamed = any("economic_observation_kind" in row for row in joins)
    by_session: dict[tuple[str, int], tuple[Mapping[str, object], ...]] = {}
    for fold in FORMAL_FOLD_IDS:
        positions = sorted(
            row["session_position"] for row in joins
            if row["source_view_id"] == view and row["fold_id"] == fold
            and (
                not streamed
                or row["economic_observation_kind"]
                == "h20_decision_return_interval"
            )
        )
        for position in positions:
            by_session[(fold, position)] = tuple(
                row for row in decisions
                if row["source_view_id"] == view and row["fold_id"] == fold
                and row["session_position"] == position
                and row["disposition"] == "scored_decision"
                and (fold, position, row["security_id"]) in accepted_h20_keys
            )
    output: list[_evaluation.EconomicSession] = []
    active: dict[str, list[_evaluation._ActiveSleeve]] = {
        fold: [] for fold in FORMAL_FOLD_IDS
    }
    for join in joins:
        if join["source_view_id"] != view:
            continue
        kind = (
            join["economic_observation_kind"]
            if streamed else "h20_decision_return_interval"
        )
        if kind == "non_economic_decision_session":
            continue
        fold = join["fold_id"]
        position = join["session_position"]
        session = join["session"]
        next_session = join["next_session"]
        decision_eligible = kind == "h20_decision_return_interval"
        terminal_liquidation = kind == "terminal_liquidation_cost"
        current = by_session.get((fold, position), ()) if decision_eligible else ()
        selected = _selected_sleeve(current)
        if decision_eligible:
            active[fold].append(_evaluation._v2_new_sleeve(selected))
        target = _evaluation._v2_targets(active[fold])
        held = tuple(sorted(target))
        if terminal_liquidation:
            if active[fold] or held or next_session is not None:
                raise FormalCloudEvaluationError(
                    "economic liquidation arrived before all sleeves expired"
                )
            benchmark_return = Decimal(0)
            benchmark_reason = None
        else:
            benchmark_start = build_daily_market_requirement_id(
                security_id=benchmark_security_id, session=session
            )
            benchmark_end = build_daily_market_requirement_id(
                security_id=benchmark_security_id, session=next_session
            )
            benchmark_return = _market_return(
                benchmark_start, benchmark_end, daily
            )
            benchmark_reason = (
                None if benchmark_return is not None
                else _evaluation.RefusalReason.MISSING_DAILY_BENCHMARK_RETURN
            )
        economic_decisions = tuple(
            _evaluation.build_economic_decision(
                decision_lineage_sha256=row["decision_lineage_sha256"],
                security_id=row["security_id"],
                firm_specific_score=_decimal(row["firm_specific_score"], "economic score"),
                realized_volatility_60d=_decimal(
                    row["realized_volatility_60d"],
                    "economic realized volatility",
                ),
            )
            for row in sorted(current, key=lambda item: item["security_id"])
        )
        security_outcomes = tuple(
            _economic_security_outcome(
                view=view, fold=fold, position=position, session=session,
                next_session=next_session, security=security,
                benchmark_return=benchmark_return, daily=daily,
                terminals=terminals, used_terminals=used_terminals,
            )
            for security in held
        )
        output.append(
            _evaluation.build_economic_session(
                source_lineage_sha256=join["source_lineage_sha256"],
                fold_id=fold, session=_iso_date(session, "economic session"),
                session_position=position,
                benchmark_total_return=benchmark_return,
                benchmark_refusal_reason=benchmark_reason,
                decisions=economic_decisions,
                security_outcomes=security_outcomes,
            )
        )
        if not terminal_liquidation:
            terminal_security_ids = frozenset(
                item.security_id
                for item in security_outcomes
                if item.terminal_payoff_applied
            )
            active[fold] = _evaluation._v2_advance_sleeves(
                active[fold], terminal_security_ids
            )
    return tuple(output)


def _fold_axes(
    contract: Mapping[str, object],
    joins: Sequence[Mapping[str, object]],
) -> tuple[_evaluation.FoldSessionAxis, ...]:
    current = SOURCE_VIEW_IDS[0]
    result: list[_evaluation.FoldSessionAxis] = []
    if contract.get("contract_variant") != STREAMED_FORMAL_CONTRACT_VARIANT:
        for fold in FORMAL_FOLD_IDS:
            union = tuple(
                _evaluation.SessionPoint(
                    session=_iso_date(row["session"], "fold-axis session"),
                    session_position=row["session_position"],
                )
                for row in joins
                if row["source_view_id"] == current and row["fold_id"] == fold
            )
            for horizon in HORIZONS:
                frozen = next(
                    item
                    for item in _evaluation.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES
                    if item[:2] == (fold, horizon)
                )
                start = date.fromisoformat(frozen[2])
                end = date.fromisoformat(frozen[3])
                points = tuple(
                    point for point in union if start <= point.session < end
                )
                result.append(
                    _evaluation.FoldSessionAxis(
                        fold_id=fold, horizon_sessions=horizon, sessions=points
                    )
                )
        return tuple(result)

    axis_records = _validate_fold_horizon_axes(contract)
    by_geometry = {
        (row["fold_id"], row["horizon_sessions"]): row
        for row in axis_records
    }
    for fold in FORMAL_FOLD_IDS:
        union = tuple(
            _evaluation.SessionPoint(
                session=_iso_date(row["session"], "fold-axis session"),
                session_position=row["session_position"],
            )
            for row in joins
            if (
                row["source_view_id"] == current
                and row["fold_id"] == fold
                and row["economic_observation_kind"]
                in {
                    "non_economic_decision_session",
                    "h20_decision_return_interval",
                }
            )
        )
        for horizon in HORIZONS:
            record = by_geometry[(fold, horizon)]
            start = _iso_date(record["test_start"], "fold-axis start")
            end = _iso_date(record["test_end_exclusive"], "fold-axis end")
            points = tuple(
                point for point in union if start <= point.session < end
            )
            payload = json.dumps(
                tuple(point.session.isoformat() for point in points),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            if (
                len(points) != record["session_count"]
                or not points
                or points[0].session != start
                or hashlib.sha256(payload).hexdigest()
                != record["session_axis_sha256"]
            ):
                raise FormalCloudEvaluationError(
                    "streamed fold axis differs from its exact session commitment"
                )
            result.append(
                _evaluation.FoldSessionAxis(
                    fold_id=fold, horizon_sessions=horizon, sessions=points
                )
            )
        h20_positions = {point.session_position for point in result[-2].sessions}
        h1_positions = {point.session_position for point in result[-4].sessions}
        for view in SOURCE_VIEW_IDS:
            rows = tuple(
                row for row in joins
                if row["source_view_id"] == view and row["fold_id"] == fold
            )
            decision_rows = tuple(
                row for row in rows
                if row["economic_observation_kind"]
                in {
                    "non_economic_decision_session",
                    "h20_decision_return_interval",
                }
            )
            if (
                len(decision_rows) != len(union)
                or {row["session_position"] for row in decision_rows}
                != h1_positions
                or any(
                    row["h20_decision_eligible"]
                    is not (row["session_position"] in h20_positions)
                    or row["economic_observation_kind"]
                    != (
                        "h20_decision_return_interval"
                        if row["session_position"] in h20_positions
                        else "non_economic_decision_session"
                    )
                    for row in decision_rows
                )
            ):
                raise FormalCloudEvaluationError(
                    "streamed decision/economic kinds differ from the exact H1/H20 axes"
                )
    return tuple(result)


def _economic_axes(
    contract: Mapping[str, object],
    joins: Sequence[Mapping[str, object]],
) -> tuple[_evaluation.EconomicObservationAxis, ...]:
    """Rebuild the six exact H20 decision/runoff/liquidation axes."""

    current = SOURCE_VIEW_IDS[0]
    streamed = contract.get("contract_variant") == STREAMED_FORMAL_CONTRACT_VARIANT
    result: list[_evaluation.EconomicObservationAxis] = []
    for frozen in _evaluation.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES:
        fold = frozen[0]
        rows = tuple(
            row for row in joins
            if row["source_view_id"] == current and row["fold_id"] == fold
            and (
                (
                    not streamed
                    and date.fromisoformat(frozen[1])
                    <= _iso_date(row["session"], "economic-axis session")
                    <= date.fromisoformat(frozen[5])
                )
                or (
                    streamed
                    and row["economic_observation_kind"]
                    != "non_economic_decision_session"
                )
            )
        )
        points = tuple(
            _evaluation.SessionPoint(
                session=_iso_date(row["session"], "economic-axis session"),
                session_position=row["session_position"],
            )
            for row in rows
        )
        if streamed:
            decision_count = frozen[3]
            return_count = frozen[6]
            expected_kinds = (
                ("h20_decision_return_interval",) * decision_count
                + ("h20_runoff_return_interval",)
                * (return_count - decision_count)
                + ("terminal_liquidation_cost",)
            )
            if (
                tuple(row["economic_observation_kind"] for row in rows)
                != expected_kinds
                or any(
                    row["h20_decision_eligible"]
                    is not (index < decision_count)
                    for index, row in enumerate(rows)
                )
            ):
                raise FormalCloudEvaluationError(
                    "streamed economic decision/runoff/liquidation sequence changed"
                )
        result.append(
            _evaluation.EconomicObservationAxis(fold_id=fold, sessions=points)
        )
    try:
        _evaluation._require_economic_observation_axes(tuple(result))
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError(
            "economic observation axes differ from the reviewed definition"
        ) from exc
    for view in SOURCE_VIEW_IDS[1:]:
        other = tuple(
            (row["fold_id"], row["session"], row["session_position"],
             row.get("economic_observation_kind"))
            for row in joins if row["source_view_id"] == view
            and (
                not streamed
                or row["economic_observation_kind"]
                != "non_economic_decision_session"
            )
        )
        expected = tuple(
            (row["fold_id"], row["session"], row["session_position"],
             row.get("economic_observation_kind"))
            for row in joins if row["source_view_id"] == current
            and (
                not streamed
                or row["economic_observation_kind"]
                != "non_economic_decision_session"
            )
        )
        if other != expected:
            raise FormalCloudEvaluationError(
                "economic source-view observation axes differ"
            )
    return tuple(result)


def _contract_power_floor(contract: Mapping[str, object]) -> _evaluation.PowerFloorBinding:
    power = _exact_object(
        contract["power_floor"],
        ("receipt_id", "receipt_sha256", "required_valid_dates",
         "required_connected_components", "h20_test_session_capacity",
         "preoutcome_candidate_date_count", "valid_h20_test_session_count",
         "refused_h20_test_session_count", "missing_h20_test_session_count",
         "connected_component_instance_count"),
        "formal power floor",
    )
    return _evaluation.PowerFloorBinding(
        receipt_id=_safe_id(power["receipt_id"], "power receipt id"),
        receipt_sha256=_sha(power["receipt_sha256"], "power receipt hash"),
        required_valid_dates=_count(
            power["required_valid_dates"], "required valid dates", minimum=50
        ),
        required_connected_components=_count(
            power["required_connected_components"],
            "required connected components", minimum=50,
        ),
        h20_test_session_capacity=_count(
            power["h20_test_session_capacity"],
            "H20 TEST-session capacity", minimum=1,
        ),
        preoutcome_candidate_date_count=_count(
            power["preoutcome_candidate_date_count"],
            "preoutcome candidate-date count",
        ),
        valid_h20_test_session_count=_count(
            power["valid_h20_test_session_count"],
            "valid H20 TEST-session count",
        ),
        refused_h20_test_session_count=_count(
            power["refused_h20_test_session_count"],
            "refused H20 TEST-session count",
        ),
        missing_h20_test_session_count=_count(
            power["missing_h20_test_session_count"],
            "missing H20 TEST-session count",
        ),
        connected_component_instance_count=_count(
            power["connected_component_instance_count"],
            "connected-component instance count",
        ),
    )


def _terminal_census(
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
    used: set[tuple[str, str, int | None]],
) -> FormalCloudTerminalCensus:
    counts = Counter(row["disposition"] for row in terminals.values())
    return FormalCloudTerminalCensus(
        terminal_policy_id=TERMINAL_POLICY_ID,
        terminal_requirement_count=len(terminals),
        terminal_payoff_count=counts["terminal_payoff"],
        benchmark_splice_continuation_count=counts[
            "benchmark_splice_continuation"
        ],
        named_terminal_refusal_count=counts["named_terminal_refusal"],
        used_terminal_disposition_count=len(used),
        unused_terminal_disposition_count=len(terminals) - len(used),
        silently_omitted_terminal_count=0,
    )


def _evaluation_execution_plan(manifest: Mapping[str, object]) -> dict[str, object]:
    return {
        "runtime_start": manifest.get("runtime_start"),
        "runtime_end": manifest.get("runtime_end"),
        "calculation_as_of_date": manifest.get("calculation_as_of_date"),
        "formal_primary_fold_ids": manifest.get("formal_primary_fold_ids"),
        "descriptive_sensitivity_fold_ids": manifest.get(
            "descriptive_sensitivity_fold_ids"
        ),
        "source_view_ids": manifest.get("source_view_ids"),
        "horizons": manifest.get("horizons"),
        "market_contract": manifest.get("market_contract"),
        "shards": manifest.get("shards"),
    }


def _evaluation_closure_and_capacity(
    manifest: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    cloud = _artifact_binding_record(
        manifest.get("cloud_evaluator"), "cloud evaluator binding"
    )
    capacity = _exact_object(
        manifest.get("capacity_review"),
        (
            "candidate_sha256", "receipt_id", "receipt_sha256", "limits",
            "representative_full_census_verified",
            "target_tier_limits_observed", "cloud_evaluator_equivalence_verified",
            "object_store_input_transport_verified",
            "object_store_output_write_once_transport_verified",
            "summary_statistics_channel_verified",
            "summary_root_result_channel_verified",
        ),
        "capacity binding",
    )
    _sha(capacity["candidate_sha256"], "capacity candidate hash")
    _safe_id(capacity["receipt_id"], "capacity receipt id")
    _sha(capacity["receipt_sha256"], "capacity receipt hash")
    if type(capacity["limits"]) is not dict:
        raise FormalCloudEvaluationError("capacity limits changed type")
    for name in (
        "representative_full_census_verified", "target_tier_limits_observed",
        "cloud_evaluator_equivalence_verified",
        "object_store_input_transport_verified",
        "object_store_output_write_once_transport_verified",
        "summary_statistics_channel_verified",
        "summary_root_result_channel_verified",
    ):
        if capacity[name] is not True:
            raise FormalCloudEvaluationError(
                "capacity/equivalence gate is not affirmative"
            )
    return cloud, capacity


def derive_streamed_formal_evaluation_preknown_bindings_record(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Derive every non-QC binding from one exact streamed runtime manifest."""

    _manifest_geometry(manifest)
    lineage = _streamed_manifest_lineage(manifest)
    cloud, capacity = _evaluation_closure_and_capacity(manifest)
    package = lineage["production_input_package"]
    terminal_id = lineage["terminal_package_id"]
    terminal_sha256 = lineage["terminal_package_sha256"]
    return {
        "schema": STREAMED_FORMAL_PREKNOWN_BINDINGS_SCHEMA,
        "input_manifest_sha256": hashlib.sha256(
            _canonical_bytes(manifest)
        ).hexdigest(),
        "production_scoring_census_id": lineage["streamed_scoring_id"],
        "production_scoring_census_sha256": lineage["streamed_scoring_sha256"],
        "evaluation_input_bundle_id": package["artifact_id"],
        "evaluation_input_bundle_sha256": package["content_sha256"],
        "terminal_disposition_package_id": terminal_id,
        "terminal_disposition_package_sha256": terminal_sha256,
        "preopen_control_stage_output": lineage[
            "preopen_control_stage_output"
        ],
        "formal_evaluator_source_sha256": lineage[
            "formal_evaluator_source_sha256"
        ],
        "evaluator_source_closure_sha256": cloud["content_sha256"],
        "execution_plan_sha256": hashlib.sha256(
            _canonical_bytes(_evaluation_execution_plan(manifest))
        ).hexdigest(),
        "capacity_plan_sha256": capacity["receipt_sha256"],
        "formal_contract_sha256": lineage["formal_contract_sha256"],
        "economic_execution_binding_id": lineage[
            "economic_execution_binding_id"
        ],
        "economic_execution_binding_sha256": lineage[
            "economic_execution_binding_sha256"
        ],
        "economic_execution_definition_id": lineage[
            "economic_execution_definition_id"
        ],
        "economic_execution_definition_sha256": lineage[
            "economic_execution_definition_sha256"
        ],
        "economic_h20_terminal_liquidation_session": lineage[
            "economic_h20_terminal_liquidation_session"
        ],
        "formal_report_contract_id": lineage["formal_report_contract_id"],
        "formal_report_contract_sha256": lineage[
            "formal_report_contract_sha256"
        ],
        "formal_report_contract_artifact_sha256": lineage[
            "formal_report_contract_artifact_sha256"
        ],
        "secondary_hypothesis_registry_sha256": lineage[
            "formal_report_contract_secondary_hypothesis_registry_sha256"
        ],
        "deflated_sharpe_trial_registry_sha256": lineage[
            "formal_report_contract_deflated_sharpe_trial_registry_sha256"
        ],
        "stock_bootstrap_seed_sha256": lineage[
            "formal_report_contract_stock_bootstrap_seed_sha256"
        ],
    }


def _bindings(
    *, manifest: Mapping[str, object], contract: Mapping[str, object],
    market_panel_sha256: str, market_panel_count: int,
) -> FormalCloudEvaluationBindings:
    cloud, capacity = _evaluation_closure_and_capacity(manifest)
    execution = _evaluation_execution_plan(manifest)
    if contract.get("contract_variant") == STREAMED_FORMAL_CONTRACT_VARIANT:
        preknown = derive_streamed_formal_evaluation_preknown_bindings_record(
            manifest
        )
        if (
            contract["production_scoring_census_id"]
            != preknown["production_scoring_census_id"]
            or contract["production_scoring_census_sha256"]
            != preknown["production_scoring_census_sha256"]
            or contract["evaluation_input_bundle_id"]
            != preknown["evaluation_input_bundle_id"]
            or contract["evaluation_input_bundle_sha256"]
            != preknown["evaluation_input_bundle_sha256"]
            or contract["terminal_package_id"]
            != preknown["terminal_disposition_package_id"]
            or contract["terminal_package_sha256"]
            != preknown["terminal_disposition_package_sha256"]
            or contract["formal_evaluator_source_sha256"]
            != preknown["formal_evaluator_source_sha256"]
        ):
            raise FormalCloudEvaluationError(
                "streamed normalized bindings diverged from runtime lineage"
            )
    streamed_preknown = (
        derive_streamed_formal_evaluation_preknown_bindings_record(manifest)
        if contract.get("contract_variant") == STREAMED_FORMAL_CONTRACT_VARIANT
        else None
    )
    return FormalCloudEvaluationBindings(
        input_manifest_sha256=hashlib.sha256(_canonical_bytes(manifest)).hexdigest(),
        production_scoring_census_sha256=_sha(
            contract["production_scoring_census_sha256"],
            "production scoring census hash",
        ),
        evaluation_input_bundle_id=_safe_id(
            contract["evaluation_input_bundle_id"], "evaluation input bundle id"
        ),
        evaluation_input_bundle_sha256=_sha(
            contract["evaluation_input_bundle_sha256"],
            "evaluation input bundle hash",
        ),
        terminal_disposition_package_sha256=_sha(
            contract["terminal_package_sha256"], "terminal package hash"
        ),
        shared_market_panel_sha256=_sha(
            market_panel_sha256, "shared market-panel hash"
        ),
        shared_market_panel_observation_count=_count(
            market_panel_count, "shared market-panel observation count", minimum=1
        ),
        formal_evaluator_source_sha256=_sha(
            contract["formal_evaluator_source_sha256"],
            "formal evaluator source hash",
        ),
        evaluator_source_closure_sha256=_sha(
            cloud["content_sha256"], "evaluator source closure hash"
        ),
        execution_plan_sha256=hashlib.sha256(_canonical_bytes(execution)).hexdigest(),
        capacity_plan_sha256=_sha(
            capacity["receipt_sha256"], "capacity review receipt hash"
        ),
        **(
            {
                name: streamed_preknown[name]
                for name in (
                    "formal_contract_sha256",
                    "economic_execution_binding_id",
                    "economic_execution_binding_sha256",
                    "economic_execution_definition_id",
                    "economic_execution_definition_sha256",
                    "economic_h20_terminal_liquidation_session",
                    "formal_report_contract_id",
                    "formal_report_contract_sha256",
                    "formal_report_contract_artifact_sha256",
                    "secondary_hypothesis_registry_sha256",
                    "deflated_sharpe_trial_registry_sha256",
                    "stock_bootstrap_seed_sha256",
                )
            }
            if streamed_preknown is not None
            else {}
        ),
    )


def _manifest_geometry(manifest: Mapping[str, object]) -> str:
    if type(manifest) is not dict:
        raise FormalCloudEvaluationError("compact input manifest changed type")
    if (
        manifest.get("schema") != INPUT_MANIFEST_SCHEMA
        or manifest.get("evaluation_id") != EVALUATION_ID
        or tuple(manifest.get("formal_primary_fold_ids", ()))
        != FORMAL_FOLD_IDS
        or tuple(manifest.get("descriptive_sensitivity_fold_ids", ()))
        != DESCRIPTIVE_FOLD_IDS
        or manifest.get(
            "descriptive_sensitivity_cannot_replace_or_rescue_primary"
        )
        is not True
        or tuple(manifest.get("source_view_ids", ())) != SOURCE_VIEW_IDS
        or tuple(manifest.get("horizons", ())) != HORIZONS
        or manifest.get("primary_horizon") != 20
        or manifest.get("economic_holding_sessions") != 20
        or manifest.get("orders_authorized") is not False
    ):
        raise FormalCloudEvaluationError("compact input manifest geometry changed")
    runtime_start = _iso_date(manifest.get("runtime_start"), "runtime start")
    runtime_end = _iso_date(manifest.get("runtime_end"), "runtime end")
    calculation_as_of = _iso_date(
        manifest.get("calculation_as_of_date"), "calculation as-of date"
    )
    if runtime_start >= runtime_end or calculation_as_of <= runtime_end:
        raise FormalCloudEvaluationError("runtime date interval changed")
    benchmark = _security_id(
        manifest.get("benchmark_security_id"), "benchmark security id"
    )
    market = manifest.get("market_contract")
    if (
        type(market) is not dict
        or market.get("daily_normalization") != "TotalReturn"
        or market.get("daily_observation") != "open_to_next_open"
        or market.get("publication_price")
        != "last_tradable_minute_strictly_before_publication"
        or market.get("positive_firm_weighted_jump") is not True
        or market.get("empty_positive_firm_weight_set_jump") != "0"
        or market.get("terminal_policy_id") != TERMINAL_POLICY_ID
        or market.get("qc_delisting_price_is_terminal_payoff") is not False
        or market.get("failed_arm_omission_forbidden") is not True
        or market.get("shared_market_panel_across_views") is not True
    ):
        raise FormalCloudEvaluationError("compact market contract changed")
    return benchmark


def _resource_census(
    manifest: Mapping[str, object], shards: Mapping[str, object]
) -> None:
    census = manifest.get("resource_census")
    if type(census) is not dict:
        raise FormalCloudEvaluationError("runtime resource census changed type")
    role_fields = {
        "formal_contract": "formal_contract_count",
        "contribution_seeds": "contribution_seed_count",
        "decision_joins": "decision_join_count",
        "economic_joins": "economic_join_count",
        "daily_requirements": "daily_requirement_count",
        "minute_requirements": "minute_requirement_count",
        "terminal_dispositions": "terminal_disposition_count",
    }
    for role, field in role_fields.items():
        if _count(census.get(field), field) != len(_exact_list(shards[role], role)):
            raise FormalCloudEvaluationError("runtime resource row census changed")
    if census.get("formal_contract_count") != 1:
        raise FormalCloudEvaluationError("formal contract resource census changed")


def _validate_contract_censuses(
    *, contract: Mapping[str, object], decisions: Sequence[Mapping[str, object]],
    terminal_census: FormalCloudTerminalCensus,
) -> None:
    partitions = _exact_list(
        contract["source_view_partitions"], "source-view partitions"
    )
    if len(partitions) != 2:
        raise FormalCloudEvaluationError("source-view partition census changed")
    for expected_view, raw in zip(SOURCE_VIEW_IDS, partitions, strict=True):
        row = _exact_object(
            raw,
            (
                "view_id", "decision_count", "scored_decision_count",
                "named_preoutcome_refusal_count", "terminal_key_sha256",
            ),
            "source-view partition",
        )
        selected = tuple(
            item for item in decisions if item["source_view_id"] == expected_view
        )
        scored = sum(item["disposition"] == "scored_decision" for item in selected)
        refused = len(selected) - scored
        terminal_keys = sorted((
            {
                "fold_id": item["fold_id"],
                "session_position": item["session_position"],
                "security_id": item["security_id"],
            }
            for item in selected
        ), key=lambda item: (
            FORMAL_FOLD_IDS.index(item["fold_id"]),
            item["session_position"], item["security_id"],
        ))
        terminal_hash = _terminal_key_census_sha256(terminal_keys)
        if (
            row["view_id"] != expected_view
            or row["decision_count"] != len(selected)
            or row["scored_decision_count"] != scored
            or row["named_preoutcome_refusal_count"] != refused
            or row["terminal_key_sha256"] != terminal_hash
        ):
            raise FormalCloudEvaluationError("source-view partition census diverged")
    terminal = _exact_object(
        contract["terminal_census"],
        (
            "terminal_policy_id", "terminal_requirement_count",
            "terminal_payoff_count", "benchmark_splice_continuation_count",
            "named_terminal_refusal_count", "silently_omitted_count",
        ),
        "formal terminal census",
    )
    expected_terminal = {
        "terminal_policy_id": TERMINAL_POLICY_ID,
        "terminal_requirement_count": terminal_census.terminal_requirement_count,
        "terminal_payoff_count": terminal_census.terminal_payoff_count,
        "benchmark_splice_continuation_count": (
            terminal_census.benchmark_splice_continuation_count
        ),
        "named_terminal_refusal_count": terminal_census.named_terminal_refusal_count,
        "silently_omitted_count": terminal_census.silently_omitted_terminal_count,
    }
    if terminal != expected_terminal:
        raise FormalCloudEvaluationError("formal terminal census diverged")


def _validate_runtime_resource_values(
    *, manifest: Mapping[str, object], daily: Mapping[str, object],
    minute: Mapping[str, object],
) -> None:
    census = manifest["resource_census"]
    batch_width = _count(
        census.get("maximum_dynamic_subscription_count"),
        "maximum dynamic subscription count", minimum=1,
    )
    daily_securities = {item["security_id"] for item in daily.values()}
    minute_securities = {
        item["security_id"] for item in minute.values()
    }
    securities = daily_securities | minute_securities
    daily_by_block: dict[int, set[str]] = {}
    for item in daily.values():
        block = _iso_date(item["session"], "daily resource session").toordinal() // 32
        daily_by_block.setdefault(block, set()).add(item["security_id"])
    minute_by_activation_day: dict[tuple[int, str], set[str]] = {}
    for item in minute.values():
        key = (
            item["first_active_session_position"],
            item["publication_at_utc"][:10],
        )
        minute_by_activation_day.setdefault(key, set()).add(item["security_id"])
    daily_batches = 2 * sum(
        (len(items) + batch_width - 1) // batch_width
        for items in daily_by_block.values()
    )
    minute_batches = 2 * sum(
        (len(items) + batch_width - 1) // batch_width
        for items in minute_by_activation_day.values()
    )
    if (
        census.get("distinct_security_count") != len(securities)
        or census.get("daily_history_batch_count") != daily_batches
        or census.get("minute_history_batch_count") != minute_batches
    ):
        raise FormalCloudEvaluationError("runtime market resource census diverged")


def _compact_stream_static(value: FormalCloudCompactStream) -> bytes:
    return _canonical_bytes({"schema": value.schema, "stream_id": value.stream_id})


def _cloud_evaluation_output_static(
    value: FormalCloudEvaluationOutput,
) -> bytes:
    return _canonical_bytes({
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(FormalCloudEvaluationOutput)
    })


def _require_cloud_evaluation_output_impl(
    value: FormalCloudEvaluationOutput,
    *,
    _authority_lookup: object,
) -> tuple[FormalCloudEvaluationOutput, _CloudEvaluationOutputState]:
    if type(value) is not FormalCloudEvaluationOutput:
        raise FormalCloudEvaluationError("cloud evaluation output changed type")
    registered = _authority_lookup(value)
    if (
        registered is None
        or registered[0] != _cloud_evaluation_output_static(value)
        or value.schema != FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
    ):
        raise FormalCloudEvaluationError(
            "cloud evaluation output is not builder-authenticated"
        )
    state = registered[1]
    if (
        state.creator_pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
    ):
        state.failed = True
        raise FormalCloudEvaluationError(
            "cloud evaluation output process or owner thread changed"
        )
    if state.failed:
        raise FormalCloudEvaluationError(
            "cloud evaluation output is locked after a failed transition"
        )
    return value, state


def _require_compact_stream_impl(
    value: FormalCloudCompactStream,
    *,
    _authority_lookup: object,
) -> tuple[FormalCloudCompactStream, _CompactStreamState]:
    if type(value) is not FormalCloudCompactStream:
        raise FormalCloudEvaluationError("compact evaluation stream changed type")
    registered = _authority_lookup(value)
    if (
        registered is None
        or value.schema != COMPACT_STREAM_SCHEMA
        or registered[0] != _compact_stream_static(value)
    ):
        raise FormalCloudEvaluationError(
            "compact evaluation stream is not builder-authenticated"
        )
    state = registered[1]
    if (
        state.creator_pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
    ):
        state.failed = True
        raise FormalCloudEvaluationError(
            "compact evaluation stream process or owner thread changed"
        )
    if state.failed:
        raise FormalCloudEvaluationError(
            "compact evaluation stream is locked after a failed transition"
        )
    return value, state


def _stream_input_identity(
    *, view: str, bindings: FormalCloudEvaluationBindings,
    axes: tuple[_evaluation.FoldSessionAxis, ...],
    economic_axes: tuple[_evaluation.EconomicObservationAxis, ...],
    economic_execution_definition_sha256: str,
    power_floor: _evaluation.PowerFloorBinding,
) -> tuple[str, str]:
    record = {
        "schema": STREAM_INPUT_SCHEMA,
        "source_view_id": view,
        "input_manifest_sha256": bindings.input_manifest_sha256,
        "evaluation_input_bundle_id": bindings.evaluation_input_bundle_id,
        "evaluation_input_bundle_sha256": bindings.evaluation_input_bundle_sha256,
        "shared_market_panel_sha256": bindings.shared_market_panel_sha256,
        "shared_market_panel_observation_count": (
            bindings.shared_market_panel_observation_count
        ),
        "fold_axes_sha256": hashlib.sha256(
            _evaluation._v2_bytes(axes)
        ).hexdigest(),
        "economic_observation_axes_sha256": hashlib.sha256(
            _evaluation._v2_bytes(economic_axes)
        ).hexdigest(),
        "economic_execution_definition_sha256": (
            economic_execution_definition_sha256
        ),
        "power_floor": dataclasses.asdict(power_floor),
    }
    digest = hashlib.sha256(_canonical_bytes(record)).hexdigest()
    return f"arv2-formal-evaluation-input-{digest[:24]}", digest


def _new_partition_hasher() -> object:
    digest = hashlib.sha256()
    digest.update(TERMINAL_KEY_CENSUS_DOMAIN.encode("ascii") + b"\0")
    return digest


def _begin_compact_formal_evaluation_impl(
    *, manifest: Mapping[str, object], formal_contract_rows: Sequence[object],
    economic_joins: Sequence[object], terminal_dispositions: Sequence[object],
    shared_market_panel_sha256: str,
    shared_market_panel_observation_count: int,
    _authority_register: object,
    _authority_require: object,
) -> FormalCloudCompactStream:
    """Begin a bounded run after the projected collector seals its panel.

    Only the formal contract and the small fold/session axis are retained.
    Decision, outcome, and held-name rows enter one complete session at a time.
    """

    panel_hash = _sha(shared_market_panel_sha256, "shared market-panel hash")
    panel_count = _count(
        shared_market_panel_observation_count,
        "shared market-panel observation count", minimum=1,
    )
    try:
        manifest_copy = json.loads(_canonical_bytes(manifest).decode("ascii"))
        benchmark_security_id = _manifest_geometry(manifest_copy)
        contract = _parse_contract(list(formal_contract_rows), manifest_copy)
        joins = _parse_economic_joins(
            list(economic_joins),
            streamed=contract.get("contract_variant")
            == STREAMED_FORMAL_CONTRACT_VARIANT,
        )
        terminals = _parse_terminal_rows(list(terminal_dispositions))
        axes = _fold_axes(contract, joins)
        economic_axes = _economic_axes(contract, joins)
        if contract.get("contract_variant") != STREAMED_FORMAL_CONTRACT_VARIANT:
            # The legacy materialized contract predates the explicit economic
            # observation-kind columns.  Normalize its already-authenticated
            # exact axes internally so both entry paths exercise the same
            # decision/runoff/terminal state machine.  No caller-supplied kind
            # is accepted on this path.
            normalized: list[dict[str, object]] = []
            by_fold = {axis.fold_id: axis.sessions for axis in economic_axes}
            horizon_lookup = _axis_horizon_lookup(axes)
            for row in joins:
                points = by_fold[row["fold_id"]]
                axis_entry = horizon_lookup.get(
                    (row["fold_id"], row["session_position"])
                )
                if axis_entry is not None:
                    kind = (
                        "h20_decision_return_interval"
                        if 20 in axis_entry[1]
                        else "non_economic_decision_session"
                    )
                else:
                    index = next(
                        offset for offset, point in enumerate(points)
                        if point.session_position == row["session_position"]
                    )
                    kind = (
                        "h20_runoff_return_interval"
                        if index + 1 < len(points)
                        else "terminal_liquidation_cost"
                    )
                normalized_row = dict(row)
                normalized_row["economic_observation_kind"] = kind
                normalized_row["h20_decision_eligible"] = (
                    kind == "h20_decision_return_interval"
                )
                if kind == "terminal_liquidation_cost":
                    normalized_row["next_session"] = None
                    normalized_row["next_session_position"] = None
                normalized.append(normalized_row)
            joins = tuple(normalized)
        economic_definition_sha256 = (
            contract["economic_execution_definition"]["definition_sha256"]
            if contract.get("contract_variant")
            == STREAMED_FORMAL_CONTRACT_VARIANT
            else _evaluation.ECONOMIC_EXECUTION_DEFINITION_SHA256
        )
        power_floor = _contract_power_floor(contract)
        bindings = _bindings(
            manifest=manifest_copy, contract=contract,
            market_panel_sha256=panel_hash, market_panel_count=panel_count,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalCloudEvaluationError):
            raise
        raise FormalCloudEvaluationError(
            "compact stream header could not be authenticated"
        ) from exc
    census = manifest_copy.get("resource_census")
    if type(census) is not dict:
        raise FormalCloudEvaluationError("runtime resource census changed type")
    if (
        _count(census.get("formal_contract_count"), "formal contract count") != 1
        or _count(census.get("economic_join_count"), "economic join count")
        != len(joins)
        or _count(census.get("terminal_disposition_count"), "terminal count")
        != len(terminals)
    ):
        raise FormalCloudEvaluationError("stream header resource census diverged")
    expected = tuple(
        (row["fold_id"], row["session"], row["session_position"])
        for row in joins if row["source_view_id"] == SOURCE_VIEW_IDS[0]
    )
    join_map = {
        (row["source_view_id"], row["fold_id"], row["session_position"]): row
        for row in joins
    }
    if len(join_map) != len(joins) or not expected:
        raise FormalCloudEvaluationError("economic stream axis is not exact")
    host_streams = tuple(
        _evaluation.begin_formal_evaluation_stream(
            source_view_id=view,
            input_id=_stream_input_identity(
                view=view, bindings=bindings, axes=axes,
                economic_axes=economic_axes,
                economic_execution_definition_sha256=(
                    economic_definition_sha256
                ),
                power_floor=power_floor,
            )[0],
            input_sha256=_stream_input_identity(
                view=view, bindings=bindings, axes=axes,
                economic_axes=economic_axes,
                economic_execution_definition_sha256=(
                    economic_definition_sha256
                ),
                power_floor=power_floor,
            )[1],
            fold_axes=axes,
            economic_observation_axes=economic_axes,
            economic_execution_definition_sha256=economic_definition_sha256,
            power_floor=power_floor,
        )
        for view in SOURCE_VIEW_IDS
    )
    state = _CompactStreamState(
        creator_pid=os.getpid(), owner_thread_id=threading.get_ident(),
        manifest=manifest_copy, contract=contract, bindings=bindings,
        preknown_bindings=(
            derive_streamed_formal_evaluation_preknown_bindings_record(
                manifest_copy
            )
            if contract.get("contract_variant")
            == STREAMED_FORMAL_CONTRACT_VARIANT
            else {}
        ),
        axes=axes, economic_axes=economic_axes, power_floor=power_floor,
        economic_joins=join_map,
        expected_blocks=expected, host_streams=host_streams,
        next_block_index=0,
        active_sleeves={
            (view, fold): [] for view in SOURCE_VIEW_IDS for fold in FORMAL_FOLD_IDS
        },
        seeds={}, minute_requirements={}, minute_observations={},
        minute_requirement_commitments={}, minute_observation_commitments={},
        terminal_dispositions=terminals,
        seen_seed_ids=set(), seen_terminal_keys=set(), terminal_counts=Counter(),
        terminal_attribution={view: Counter() for view in SOURCE_VIEW_IDS},
        partition_counts={view: Counter() for view in SOURCE_VIEW_IDS},
        partition_hashes={view: _new_partition_hasher() for view in SOURCE_VIEW_IDS},
        last_partition_keys={view: None for view in SOURCE_VIEW_IDS},
        directional_event_report_observations=[],
        decision_report_observations=[],
        subset_fm_report_observations=[],
        variant_fold_states={
            (view, fold, variant): _ReportVariantFoldState(
                active_sleeves=[], pretrade_weights={}, observations=[],
                refusal_counts_by_session=[], session_count=0,
                refused_session_count=0, invested_session_count=0,
                cash_sleeve_count=0, selected_sleeve_count=0,
                terminal_liquidation_turnover=Decimal(0),
                refusal_counts=Counter(), fold_state_valid=True,
            )
            for view in SOURCE_VIEW_IDS
            for fold in FORMAL_FOLD_IDS
            for variant in _REPORT_ONLY_PORTFOLIO_VARIANT_IDS
        },
        finished=False, failed=False,
    )
    stream_digest = hashlib.sha256(_canonical_bytes({
        "schema": COMPACT_STREAM_SCHEMA,
        "input_manifest_sha256": bindings.input_manifest_sha256,
        "shared_market_panel_sha256": panel_hash,
        "expected_block_count": len(expected),
    })).hexdigest()
    value = object.__new__(FormalCloudCompactStream)
    object.__setattr__(value, "stream_id", f"arv2-compact-stream-{stream_digest[:24]}")
    object.__setattr__(value, "schema", COMPACT_STREAM_SCHEMA)
    _authority_register(
        value, _compact_stream_static(value), state
    )
    _ = benchmark_security_id
    return _authority_require(value)[0]


def _stream_economic_session(
    *, state: _CompactStreamState, view: str, fold: str, session: str,
    position: int, decisions: Sequence[Mapping[str, object]],
    accepted_h20: set[str], daily: Mapping[str, dict[str, object]],
    terminals: Mapping[tuple[str, str, int | None], dict[str, object]],
    used_terminals: set[tuple[str, str, int | None]],
    benchmark_security_id: str,
) -> tuple[_evaluation.EconomicSession, set[str]]:
    join = state.economic_joins[(view, fold, position)]
    if join["session"] != session:
        raise FormalCloudEvaluationError("economic join escaped its session block")
    kind = join["economic_observation_kind"]
    next_session = join["next_session"]
    decision_eligible = kind == "h20_decision_return_interval"
    terminal_liquidation = kind == "terminal_liquidation_cost"
    if kind not in {
        "h20_decision_return_interval",
        "h20_runoff_return_interval",
        "terminal_liquidation_cost",
    }:
        raise FormalCloudEvaluationError(
            "non-economic block entered the economic accumulator"
        )
    current = tuple(
        row for row in decisions
        if decision_eligible
        and row["source_view_id"] == view
        and row["disposition"] == "scored_decision"
        and row["security_id"] in accepted_h20
    )
    selected = _selected_sleeve(current)
    active = state.active_sleeves[(view, fold)]
    if decision_eligible:
        active.append(_evaluation._v2_new_sleeve(selected))
    target = _evaluation._v2_targets(active)
    held = tuple(sorted(target))
    used_daily: set[str] = set()
    if terminal_liquidation:
        if active or held or next_session is not None:
            raise FormalCloudEvaluationError(
                "terminal liquidation arrived before all sleeves expired"
            )
        benchmark_return = Decimal(0)
        benchmark_reason = None
    else:
        benchmark_start = build_daily_market_requirement_id(
            security_id=benchmark_security_id, session=session
        )
        benchmark_end = build_daily_market_requirement_id(
            security_id=benchmark_security_id, session=next_session
        )
        used_daily.update((benchmark_start, benchmark_end))
        benchmark_return = _market_return(
            benchmark_start, benchmark_end, daily
        )
        benchmark_reason = (
            None if benchmark_return is not None
            else _evaluation.RefusalReason.MISSING_DAILY_BENCHMARK_RETURN
        )
    economic_decisions = tuple(
        _evaluation.build_economic_decision(
            decision_lineage_sha256=row["decision_lineage_sha256"],
            security_id=row["security_id"],
            firm_specific_score=_decimal(row["firm_specific_score"], "economic score"),
            realized_volatility_60d=_decimal(
                row["realized_volatility_60d"],
                "economic realized volatility",
            ),
        )
        for row in sorted(current, key=lambda item: item["security_id"])
    )
    outcomes = []
    for security in held:
        terminal_key = (
            "economic_daily",
            build_economic_terminal_slot_id(
                view_id=view, fold_id=fold, session_position=position,
                security_id=security,
            ),
            None,
        )
        if terminal_key not in terminals:
            used_daily.update((
                build_daily_market_requirement_id(
                    security_id=security, session=session
                ),
                build_daily_market_requirement_id(
                    security_id=security, session=next_session
                ),
            ))
        outcomes.append(_economic_security_outcome(
            view=view, fold=fold, position=position, session=session,
            next_session=next_session, security=security,
            benchmark_return=benchmark_return, daily=daily,
            terminals=terminals, used_terminals=used_terminals,
        ))
    terminal_security_ids = frozenset(
        item.security_id for item in outcomes if item.terminal_payoff_applied
    )
    if not terminal_liquidation:
        state.active_sleeves[(view, fold)] = _evaluation._v2_advance_sleeves(
            active, terminal_security_ids
        )
    return _evaluation.build_economic_session(
        source_lineage_sha256=join["source_lineage_sha256"],
        fold_id=fold, session=_iso_date(session, "economic session"),
        session_position=position, benchmark_total_return=benchmark_return,
        benchmark_refusal_reason=benchmark_reason,
        decisions=economic_decisions, security_outcomes=tuple(outcomes),
    ), used_daily


def _update_stream_partition(
    state: _CompactStreamState, row: Mapping[str, object],
    active_horizons: Sequence[int],
) -> None:
    view = row["source_view_id"]
    key = (
        FORMAL_FOLD_IDS.index(row["fold_id"]), row["session_position"],
        row["security_id"],
    )
    prior = state.last_partition_keys[view]
    if prior is not None and key <= prior:
        raise FormalCloudEvaluationError(
            "stream decision terminal keys are duplicated or reordered"
        )
    state.last_partition_keys[view] = key
    semantic = {
        "fold_id": row["fold_id"],
        "session_position": row["session_position"],
        "security_id": row["security_id"],
    }
    payload = _canonical_bytes(semantic)
    digest = state.partition_hashes[view]
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    counts = state.partition_counts[view]
    counts["decision"] += 1
    disposition = (
        "scored" if row["disposition"] == "scored_decision" else "refused"
    )
    counts[disposition] += 1
    counts[(row["fold_id"], "decision")] += 1
    counts[(row["fold_id"], disposition)] += 1
    for horizon in active_horizons:
        if horizon not in HORIZONS:
            raise FormalCloudEvaluationError(
                "stream partition acquired an unknown horizon"
            )
        counts[(row["fold_id"], horizon, "decision")] += 1
        counts[(row["fold_id"], horizon, disposition)] += 1


def _report_variant_new_sleeve(
    *, variant: str, decisions: Sequence[_evaluation.EconomicDecision],
) -> _ReportVariantSleeve:
    """Build one exact report-only weighting variant on the frozen name set."""

    selected_ids = _evaluation._v2_selected_sleeve(decisions)
    decision_by_id = {item.security_id: item for item in decisions}
    if len(decision_by_id) != len(decisions):
        raise FormalCloudEvaluationError(
            "report economic decision security was duplicated"
        )
    weights: tuple[tuple[str, Decimal], ...] = ()
    if selected_ids:
        selected = tuple(decision_by_id[item] for item in selected_ids)
        if variant == "direct_stock_inverse_volatility":
            if all(
                item.realized_volatility_60d is not None
                and item.realized_volatility_60d > 0
                for item in selected
            ):
                with localcontext(_evaluation._context()):
                    raw = tuple(
                        +(Decimal(1) / item.realized_volatility_60d)
                        for item in selected
                    )
                    denominator = _evaluation._stable_sum(raw)
                    weights = tuple(sorted(
                        (
                            item.security_id,
                            +(raw[index] / denominator),
                        )
                        for index, item in enumerate(selected)
                    ))
        elif variant == "direct_stock_score_weight":
            if all(item.firm_specific_score > 0 for item in selected):
                with localcontext(_evaluation._context()):
                    raw = tuple(item.firm_specific_score for item in selected)
                    denominator = _evaluation._stable_sum(raw)
                    weights = tuple(sorted(
                        (
                            item.security_id,
                            +(raw[index] / denominator),
                        )
                        for index, item in enumerate(selected)
                    ))
        else:
            raise FormalCloudEvaluationError(
                "report economic portfolio variant changed"
            )
    return _ReportVariantSleeve(
        remaining_intervals=_evaluation.SLEEVE_HOLDING_SESSIONS,
        original_weights=weights,
        active_security_ids=tuple(item[0] for item in weights),
    )


def _report_variant_targets(
    sleeves: Sequence[_ReportVariantSleeve],
) -> dict[str, Decimal]:
    target: dict[str, Decimal] = {}
    with localcontext(_evaluation._context()):
        for sleeve in sleeves:
            original = dict(sleeve.original_weights)
            if (
                len(original) != len(sleeve.original_weights)
                or tuple(sorted(original))
                != tuple(item[0] for item in sleeve.original_weights)
                or tuple(sorted(set(sleeve.active_security_ids)))
                != sleeve.active_security_ids
                or not set(sleeve.active_security_ids).issubset(original)
                or sleeve.remaining_intervals < 1
            ):
                raise FormalCloudEvaluationError(
                    "report economic sleeve state changed"
                )
            for security_id in sleeve.active_security_ids:
                target[security_id] = +(
                    target.get(security_id, Decimal(0))
                    + original[security_id]
                    / Decimal(_evaluation.SLEEVE_HOLDING_SESSIONS)
                )
    return target


def _report_variant_advance_sleeves(
    sleeves: Sequence[_ReportVariantSleeve],
    terminal_security_ids: frozenset[str],
) -> list[_ReportVariantSleeve]:
    return [
        _ReportVariantSleeve(
            remaining_intervals=item.remaining_intervals - 1,
            original_weights=item.original_weights,
            active_security_ids=tuple(
                security_id for security_id in item.active_security_ids
                if security_id not in terminal_security_ids
            ),
        )
        for item in sleeves if item.remaining_intervals > 1
    ]


def _consume_report_variant_economic_session(
    *, state: _CompactStreamState, source_view_id: str,
    economic: _evaluation.EconomicSession, decision_eligible: bool,
    terminal_liquidation: bool,
) -> None:
    """Consume both frozen cost-10 weighting variants from one typed session."""

    row_map = {item.security_id: item for item in economic.security_outcomes}
    if len(row_map) != len(economic.security_outcomes):
        raise FormalCloudEvaluationError(
            "report economic outcome security was duplicated"
        )
    terminal_security_ids = frozenset(
        item.security_id for item in economic.security_outcomes
        if item.terminal_payoff_applied
    )
    for variant in _REPORT_ONLY_PORTFOLIO_VARIANT_IDS:
        current = state.variant_fold_states[
            (source_view_id, economic.fold_id, variant)
        ]
        current.session_count += 1
        if decision_eligible:
            sleeve = _report_variant_new_sleeve(
                variant=variant, decisions=economic.decisions
            )
            current.active_sleeves.append(sleeve)
            if sleeve.active_security_ids:
                current.selected_sleeve_count += 1
            else:
                current.cash_sleeve_count += 1
        target = _report_variant_targets(current.active_sleeves)
        current.invested_session_count += int(bool(target))
        incidence = sum(
            len(item.active_security_ids) for item in current.active_sleeves
        )
        duplicate_incidence = incidence - len(target)
        if not set(target).issubset(row_map):
            raise FormalCloudEvaluationError(
                "report economic variant escaped the authenticated outcome union"
            )
        benchmark_refusals = {
            economic.benchmark_refusal_reason.value
        } if economic.benchmark_refusal_reason is not None else set()
        security_refusals = {
            row_map[security_id].reason.value
            for security_id in target
            if row_map[security_id].disposition
            is _evaluation.EconomicOutcomeDisposition.NAMED_REFUSAL
            and row_map[security_id].reason is not None
        }
        session_refusals = benchmark_refusals | security_refusals
        dated_refusals = Counter(session_refusals)
        if session_refusals:
            current.refused_session_count += 1
            current.refusal_counts.update(session_refusals)
        if security_refusals:
            current.fold_state_valid = False
        if current.fold_state_valid:
            securities = set(current.pretrade_weights) | set(target)
            with localcontext(_evaluation._context()):
                turnover = _evaluation._stable_sum(tuple(
                    +(
                        target.get(name, Decimal(0))
                        - current.pretrade_weights.get(name, Decimal(0))
                    ).copy_abs()
                    for name in securities
                ))
                gross = _evaluation._stable_sum(tuple(
                    +(weight * row_map[name].gross_total_return)
                    for name, weight in target.items()
                ))
                net = +(
                    gross - turnover * Decimal(10) / Decimal(10_000)
                )
                ending_wealth = +(Decimal(1) + net)
            if ending_wealth <= 0:
                current.fold_state_valid = False
                reason = "nonpositive_post_cost_wealth"
                current.refusal_counts[reason] += 1
                if not session_refusals:
                    current.refused_session_count += 1
                    dated_refusals[reason] += 1
            else:
                if terminal_liquidation:
                    current.terminal_liquidation_turnover = turnover
                with localcontext(_evaluation._context()):
                    current.pretrade_weights = {
                        name: +(
                            weight
                            * (Decimal(1) + row_map[name].gross_total_return)
                            / ending_wealth
                        )
                        for name, weight in target.items()
                        if weight != 0 and name not in terminal_security_ids
                    }
                    excess = +(
                        net - economic.benchmark_total_return
                    ) if economic.benchmark_total_return is not None else None
                if excess is not None:
                    current.observations.append(_ReportTrialObservation(
                        trial_id=f"{variant}_cost10",
                        portfolio_variant_id=variant,
                        cost_bps_per_side=10,
                        fold_id=economic.fold_id,
                        session=economic.session,
                        session_position=economic.session_position,
                        gross_portfolio_total_return=gross,
                        benchmark_total_return=economic.benchmark_total_return,
                        net_portfolio_total_return=net,
                        net_excess_daily_total_return=excess,
                        turnover=turnover,
                        sleeve_security_incidence_count=incidence,
                        duplicate_sleeve_security_incidence_count=(
                            duplicate_incidence
                        ),
                        terminal_liquidation=terminal_liquidation,
                    ))
        if dated_refusals:
            current.refusal_counts_by_session.append((
                economic.session, tuple(sorted(dated_refusals.items()))
            ))
        if terminal_liquidation:
            if current.active_sleeves or current.pretrade_weights:
                raise FormalCloudEvaluationError(
                    "report economic variant did not liquidate exactly"
                )
        else:
            current.active_sleeves = _report_variant_advance_sleeves(
                current.active_sleeves, terminal_security_ids
            )


def _finish_report_variant_state(
    *, state: _CompactStreamState, source_view_id: str,
) -> tuple[
    tuple[_ReportTrialObservation, ...],
    tuple[_ReportTrialFoldCensus, ...],
]:
    observations: list[_ReportTrialObservation] = []
    censuses: list[_ReportTrialFoldCensus] = []
    axes = {item.fold_id: item.sessions for item in state.economic_axes}
    for variant in _REPORT_ONLY_PORTFOLIO_VARIANT_IDS:
        trial_id = f"{variant}_cost10"
        for fold in FORMAL_FOLD_IDS:
            current = state.variant_fold_states[
                (source_view_id, fold, variant)
            ]
            dated = list(current.refusal_counts_by_session)
            retained = list(current.observations)
            if not current.fold_state_valid:
                retained = []
                prior_dates = {item[0] for item in dated}
                reason = _evaluation.ECONOMIC_FOLD_STATE_LOSS_EXCLUSION
                dated.extend(
                    (point.session, ((reason, 1),))
                    for point in axes[fold] if point.session not in prior_dates
                )
                missing = current.session_count - current.refused_session_count
                if missing < 0:
                    raise FormalCloudEvaluationError(
                        "report economic refusal census exceeded its axis"
                    )
                current.refusal_counts[reason] += missing
                current.refused_session_count += missing
            dated.sort(key=lambda item: item[0])
            if (
                current.session_count != len(axes[fold])
                or len(dated) != current.refused_session_count
                or len(retained) + current.refused_session_count
                != current.session_count
                or tuple(item.session for item in retained)
                != tuple(sorted(item.session for item in retained))
            ):
                raise FormalCloudEvaluationError(
                    "report economic variant terminal census is incomplete"
                )
            observations.extend(retained)
            censuses.append(_ReportTrialFoldCensus(
                trial_id=trial_id, portfolio_variant_id=variant,
                cost_bps_per_side=10, fold_id=fold,
                session_count=current.session_count,
                valid_return_session_count=len(retained),
                refused_return_session_count=current.refused_session_count,
                invested_session_count=current.invested_session_count,
                cash_sleeve_count=current.cash_sleeve_count,
                selected_sleeve_count=current.selected_sleeve_count,
                terminal_liquidation_turnover=(
                    current.terminal_liquidation_turnover
                ),
                refusal_counts=tuple(sorted(current.refusal_counts.items())),
                refusal_counts_by_session=tuple(dated),
            ))
    return tuple(observations), tuple(censuses)


def _consume_compact_formal_session_block_impl(
    stream: FormalCloudCompactStream,
    *, fold_id: str, session: str, session_position: int,
    decision_joins: Sequence[object],
    new_contribution_seeds: Sequence[object],
    daily_requirements: Sequence[object],
    minute_requirements: Sequence[object],
    observations: Mapping[str, object],
    _authority_require: object,
    _authority_update: object,
) -> FormalCloudCompactStream:
    """Parse and consume the next complete two-view fold/session block."""

    value, state = _authority_require(stream)
    if state.finished:
        raise FormalCloudEvaluationError("compact evaluation stream is sealed")
    if state.next_block_index >= len(state.expected_blocks):
        raise FormalCloudEvaluationError("compact evaluation stream is complete")
    fold, expected_session, position = state.expected_blocks[state.next_block_index]
    if (
        fold_id != fold or session != expected_session
        or session_position != position
    ):
        raise FormalCloudEvaluationError(
            "compact session block is missing or reordered"
        )
    try:
        daily_req = _parse_daily_requirements(
            list(daily_requirements), allow_empty=True
        )
        minute_req = _parse_minute_requirements(list(minute_requirements))
        daily, new_minute, _unused_panel_hash, _unused_count = _parse_observations(
            observations, daily_req, minute_req
        )
        for requirement_id, requirement in minute_req.items():
            requirement_commitment = hashlib.sha256(
                _canonical_bytes(requirement)
            ).hexdigest()
            observation_commitment = hashlib.sha256(
                _canonical_bytes(new_minute[requirement_id])
            ).hexdigest()
            prior_requirement = state.minute_requirement_commitments.get(
                requirement_id
            )
            prior_observation = state.minute_observation_commitments.get(
                requirement_id
            )
            if (
                prior_requirement is not None
                and (
                    prior_requirement != requirement_commitment
                    or prior_observation != observation_commitment
                )
            ):
                raise FormalCloudEvaluationError(
                    "reactivated minute fact differs from its authenticated commitment"
                )
            state.minute_requirement_commitments.setdefault(
                requirement_id, requirement_commitment
            )
            state.minute_observation_commitments.setdefault(
                requirement_id, observation_commitment
            )
            state.minute_requirements[requirement_id] = requirement
            state.minute_observations[requirement_id] = new_minute[requirement_id]
        parsed_new_seeds = _parse_contribution_seeds(
            list(new_contribution_seeds), state.minute_requirements
        )
        for rows in parsed_new_seeds.values():
            for row in rows:
                if row["seed_id"] in state.seen_seed_ids:
                    raise FormalCloudEvaluationError(
                        "contribution seed was replayed across session blocks"
                    )
                state.seen_seed_ids.add(row["seed_id"])
        for key, rows in parsed_new_seeds.items():
            state.seeds.setdefault(key, []).extend(rows)
            state.seeds[key].sort(key=lambda item: item["seed_id"])
        decisions = _parse_decisions(
            list(decision_joins),
            {key: tuple(rows) for key, rows in state.seeds.items()},
            daily_req, state.contract["scoring_result_bindings"],
            state.manifest["benchmark_security_id"],
            state.axes,
        )
        if any(
            row["fold_id"] != fold or row["decision_session"] != session
            or row["session_position"] != position
            for row in decisions
        ):
            raise FormalCloudEvaluationError(
                "decision escaped the next compact session block"
            )
        terminals = state.terminal_dispositions
        used_terminals: set[tuple[str, str, int | None]] = set()
        all_minute = dict(state.minute_observations)
        used_daily: set[str] = set()
        blocks: list[_evaluation.FormalEvaluationSessionBlock] = []
        axis_entry = _axis_horizon_lookup(state.axes).get((fold, position))
        current_join = state.economic_joins[
            (SOURCE_VIEW_IDS[0], fold, position)
        ]
        kind = current_join["economic_observation_kind"]
        if any(
            state.economic_joins[(view, fold, position)][
                "economic_observation_kind"
            ] != kind
            for view in SOURCE_VIEW_IDS
        ):
            raise FormalCloudEvaluationError(
                "economic observation kind differs between source views"
            )
        if kind in {
            "non_economic_decision_session",
            "h20_decision_return_interval",
        }:
            if axis_entry is None or axis_entry[0].isoformat() != session:
                raise FormalCloudEvaluationError(
                    "decision block escaped its exact fold-horizon axes"
                )
            expected_h20 = kind == "h20_decision_return_interval"
            if (20 in axis_entry[1]) is not expected_h20:
                raise FormalCloudEvaluationError(
                    "economic kind differs from exact H20 decision axis"
                )
        elif axis_entry is not None or decisions:
            raise FormalCloudEvaluationError(
                "runoff/liquidation block acquired a decision-axis row"
            )
        economic_required = kind != "non_economic_decision_session"
        for view_index, view_id in enumerate(SOURCE_VIEW_IDS):
            prior_terminal_keys = frozenset(used_terminals)
            accepted, refused = _event_rows(
                view=view_id, decisions=decisions,
                seeds={key: tuple(rows) for key, rows in state.seeds.items()},
                daily=daily, minute=all_minute, terminals=terminals,
                used_terminals=used_terminals,
                fold_axes=state.axes,
            )
            _capture_report_sufficient_statistics(
                state=state, view=view_id, decisions=decisions,
                accepted=accepted, refused=refused,
                fold_id=fold,
                decision_session=_iso_date(session, "report block session"),
                session_position=position,
                h20_axis_active=(
                    axis_entry is not None and 20 in axis_entry[1]
                ),
            )
            accepted_h20 = {
                row.security_id for row in accepted
                if row.horizon_sessions == 20
            }
            join = state.economic_joins[(view_id, fold, position)]
            if (
                join["h20_decision_eligible"]
                is not (kind == "h20_decision_return_interval")
                or (join["economic_observation_kind"] != kind)
            ):
                raise FormalCloudEvaluationError(
                    "economic observation kind changed after authentication"
                )
            economic = None
            if economic_required:
                economic, economic_daily = _stream_economic_session(
                    state=state, view=view_id, fold=fold, session=session,
                    position=position, decisions=decisions,
                    accepted_h20=accepted_h20, daily=daily,
                    terminals=terminals, used_terminals=used_terminals,
                    benchmark_security_id=state.manifest[
                        "benchmark_security_id"
                    ],
                )
                used_daily.update(economic_daily)
            newly_used_terminals = used_terminals.difference(
                prior_terminal_keys
            )
            attribution = state.terminal_attribution[view_id]
            for terminal_key in newly_used_terminals:
                terminal_disposition = terminals[terminal_key]["disposition"]
                attribution[(fold, "terminal")] += 1
                attribution[(fold, terminal_disposition)] += 1
            for row in decisions:
                if row["source_view_id"] != view_id:
                    continue
                _update_stream_partition(state, row, axis_entry[1])
                if row["disposition"] == "scored_decision":
                    used_daily.update((
                        row["entry_daily_requirement_id"],
                        row["benchmark_entry_daily_requirement_id"],
                    ))
                    for exit_row in row["horizon_exits"]:
                        used_daily.update((
                            exit_row["stock_daily_requirement_id"],
                            exit_row["benchmark_daily_requirement_id"],
                        ))
            block = _evaluation.build_formal_evaluation_session_block(
                fold_id=fold, decision_session=_iso_date(session, "stream session"),
                session_position=position, rows=accepted, refusals=refused,
                economic_session=economic,
            )
            _evaluation.consume_formal_evaluation_session_block(
                state.host_streams[view_index], block
            )
            if economic is not None:
                _consume_report_variant_economic_session(
                    state=state, source_view_id=view_id, economic=economic,
                    decision_eligible=(
                        kind == "h20_decision_return_interval"
                    ),
                    terminal_liquidation=(kind == "terminal_liquidation_cost"),
                )
            blocks.append(block)
        if not used_daily.issubset(daily_req):
            raise FormalCloudEvaluationError(
                "session block lacks a required daily observation"
            )
        if state.seen_terminal_keys.intersection(used_terminals):
            raise FormalCloudEvaluationError(
                "terminal disposition was replayed across session blocks"
            )
        state.seen_terminal_keys.update(used_terminals)
        state.terminal_counts.update(
            terminals[key]["disposition"] for key in used_terminals
        )
        state.next_block_index += 1
        # Retain only contribution seeds whose final active interval can still
        # reach a later block; this bounds seed/minute state by the lookback.
        for key in tuple(state.seeds):
            retained = [
                row for row in state.seeds[key]
                if max(interval[1] for interval in row["active_intervals"])
                > position + 1
            ]
            if retained:
                state.seeds[key] = retained
            else:
                state.seeds.pop(key)
        for requirement_id in tuple(state.minute_requirements):
            # A deduplicated fact may be referenced again after a security or
            # view-specific inactivity gap.  Its authenticated global
            # first/last lifetime is the capacity-reviewed retention bound.
            if (
                state.minute_requirements[requirement_id][
                    "last_active_session_position"
                ] <= position
            ):
                state.minute_requirements.pop(requirement_id)
                state.minute_observations.pop(requirement_id)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        state.failed = True
        _authority_update(value, state)
        if isinstance(exc, FormalCloudEvaluationError):
            raise
        raise FormalCloudEvaluationError(
            "compact session block could not build the frozen evaluator block"
        ) from exc
    _authority_update(value, state)
    return value


def _validate_stream_contract_census(
    state: _CompactStreamState, terminal: FormalCloudTerminalCensus
) -> None:
    partitions = _exact_list(
        state.contract["source_view_partitions"], "source-view partitions"
    )
    if len(partitions) != 2:
        raise FormalCloudEvaluationError("source-view partition census changed")
    for view, raw in zip(SOURCE_VIEW_IDS, partitions, strict=True):
        expected = _exact_object(
            raw,
            ("view_id", "decision_count", "scored_decision_count",
             "named_preoutcome_refusal_count", "terminal_key_sha256"),
            "source-view partition",
        )
        counts = state.partition_counts[view]
        digest = state.partition_hashes[view].hexdigest()
        if expected != {
            "view_id": view,
            "decision_count": counts["decision"],
            "scored_decision_count": counts["scored"],
            "named_preoutcome_refusal_count": counts["refused"],
            "terminal_key_sha256": digest,
        }:
            raise FormalCloudEvaluationError(
                "stream source-view partition census diverged"
            )
    expected_terminal = _exact_object(
        state.contract["terminal_census"],
        ("terminal_policy_id", "terminal_requirement_count",
         "terminal_payoff_count", "benchmark_splice_continuation_count",
         "named_terminal_refusal_count", "silently_omitted_count"),
        "formal terminal census",
    )
    if expected_terminal != {
        "terminal_policy_id": TERMINAL_POLICY_ID,
        "terminal_requirement_count": terminal.terminal_requirement_count,
        "terminal_payoff_count": terminal.terminal_payoff_count,
        "benchmark_splice_continuation_count": (
            terminal.benchmark_splice_continuation_count
        ),
        "named_terminal_refusal_count": terminal.named_terminal_refusal_count,
        "silently_omitted_count": 0,
    }:
        raise FormalCloudEvaluationError("stream terminal census diverged")


def _streaming_aggregate(
    *, results: tuple[_evaluation.FormalEvaluationStreamingResult, ...],
    streams: tuple[_evaluation.FormalEvaluationStream, ...],
    bindings: FormalCloudEvaluationBindings,
    preknown_bindings: Mapping[str, object],
    terminal_census: FormalCloudTerminalCensus,
    report_contract: Mapping[str, object] | None,
    coverages: Sequence[Mapping[str, object]],
    partition_counts: Mapping[str, Counter[object]],
    terminal_attribution: Mapping[str, Counter[object]],
    variant_trial_states: Mapping[
        str,
        tuple[
            tuple[_ReportTrialObservation, ...],
            tuple[_ReportTrialFoldCensus, ...],
        ],
    ],
    directional_event_observations: Sequence[
        _DirectionalEventReportObservation
    ],
    decision_report_observations: Sequence[_DecisionReportObservation],
    subset_fm_report_observations: Sequence[_SubsetFmReportObservation],
    resamples: int,
    externalize_report_families: bool = False,
) -> tuple[bytes, tuple[_ReportFamilyObject, ...]]:
    reports = tuple(item.report for item in results)
    report_documents = tuple(_report_document(item) for item in reports)
    view_axis = []
    fold_axis = []
    for view, result in zip(SOURCE_VIEW_IDS, results, strict=True):
        for fold, horizon, accepted, refused in result.fold_horizon_census:
            view_axis.append({
                "view_id": view, "fold_id": fold, "horizon": horizon,
                "accepted_count": accepted, "refused_count": refused,
                "slot_count": accepted + refused,
            })
    for fold in FORMAL_FOLD_IDS:
        for horizon in HORIZONS:
            selected = [
                row for row in view_axis
                if row["fold_id"] == fold and row["horizon"] == horizon
            ]
            accepted = sum(row["accepted_count"] for row in selected)
            refused = sum(row["refused_count"] for row in selected)
            fold_axis.append({
                "fold_id": fold, "horizon": horizon,
                "accepted_count": accepted, "refused_count": refused,
                "slot_count": accepted + refused,
            })
    dispositions = Counter(item.disposition.value for item in reports)
    source_view_census = [
        {
            "view_id": view,
            "accepted_count": result.accepted_row_count,
            "refused_count": result.refused_row_count,
            "slot_count": result.accepted_row_count + result.refused_row_count,
            "economic_session_count": result.economic_session_count,
        }
        for view, result in zip(SOURCE_VIEW_IDS, results, strict=True)
    ]
    document = {
        "schema": SCHEMA, "status": STATUS, "authority": AUTHORITY,
        "evaluation_id": EVALUATION_ID,
        "formal_cloud_evaluator_contract_sha256": (
            FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
        ),
        "bindings": bindings.to_record(), "bootstrap_resamples": resamples,
        "bootstrap_seed_sha256": _evaluation.BOOTSTRAP_SEED_SHA256,
        "formal_fold_ids": list(FORMAL_FOLD_IDS),
        "descriptive_fold_ids": list(DESCRIPTIVE_FOLD_IDS),
        "descriptive_slice_cannot_replace_or_rescue_formal": True,
        "source_view_ids": list(SOURCE_VIEW_IDS),
        "source_view_reports_are_separate": True,
        "horizons": list(HORIZONS), "primary_horizon": 20,
        "input_bindings": [
            {
                "source_view_id": view, "input_id": item.input_id,
                "input_sha256": item.input_sha256,
            }
            for view, item in zip(SOURCE_VIEW_IDS, streams, strict=True)
        ],
        "source_view_census": source_view_census,
        "fold_horizon_axis_count": 24,
        "fold_horizon_census": fold_axis,
        "source_view_fold_horizon_axis_count": 48,
        "source_view_fold_horizon_census": view_axis,
        "report_count": 2,
        "reports": list(report_documents),
        "report_disposition_counts": dict(sorted(dispositions.items())),
        "terminal_census": terminal_census.to_record(),
        "shared_market_panel_sha256": bindings.shared_market_panel_sha256,
        "shared_market_panel_observation_count": (
            bindings.shared_market_panel_observation_count
        ),
        "failed_arm_omission_count": 0, "silently_omitted_slot_count": 0,
        "raw_outcome_rows_exported": False, "orders_placed": 0,
    }
    family_objects: tuple[_ReportFamilyObject, ...] = ()
    if externalize_report_families:
        if (
            type(preknown_bindings) is not dict
            or preknown_bindings.get("schema")
            != STREAMED_FORMAL_PREKNOWN_BINDINGS_SCHEMA
        ):
            raise FormalCloudEvaluationError(
                "multipart result lacks exact streamed preknown bindings"
            )
        document["streamed_preknown_bindings"] = dict(preknown_bindings)
    if report_contract is not None:
        expanded, family_objects = _expanded_report_outputs(
            reports=report_documents,
            results=results,
            report_contract=report_contract,
            coverages=coverages,
            fold_axes=streams[0].fold_axes,
            economic_axes=streams[0].economic_observation_axes,
            power_floor=streams[0].power_floor,
            partition_counts=partition_counts,
            terminal_attribution=terminal_attribution,
            variant_trial_states=variant_trial_states,
            directional_event_observations=directional_event_observations,
            decision_report_observations=decision_report_observations,
            subset_fm_report_observations=subset_fm_report_observations,
            resamples=resamples,
            externalize_report_families=externalize_report_families,
            input_manifest_sha256=bindings.input_manifest_sha256,
        )
        document.update(expanded)
    payload = _canonical_bytes(document)
    if report_contract is not None:
        rules = report_contract["numeric_and_output_rules"]
        if len(payload) > rules["aggregate_decompressed_byte_ceiling"]:
            raise FormalCloudEvaluationError(
                "content-addressed report envelope exceeds its reviewed raw capacity"
            )
        compressed = bytearray(gzip.compress(payload, compresslevel=9, mtime=0))
        compressed[9] = 255
        if len(compressed) > rules["aggregate_compressed_byte_ceiling"]:
            raise FormalCloudEvaluationError(
                "content-addressed report envelope exceeds its reviewed wire capacity"
            )
    return payload, family_objects


def _finish_compact_formal_evaluation(
    stream: FormalCloudCompactStream,
    *,
    resamples: int,
    externalize_report_families: bool,
    _authority_require: object,
    _authority_update: object,
) -> tuple[bytes, tuple[_ReportFamilyObject, ...]]:
    """Seal one stream into either the legacy or multipart representation."""

    value, state = _authority_require(stream)
    if state.finished:
        raise FormalCloudEvaluationError("compact evaluation stream is sealed")
    if state.next_block_index != len(state.expected_blocks):
        raise FormalCloudEvaluationError("compact evaluation stream is incomplete")
    census = state.manifest["resource_census"]
    if (
        state.partition_counts[SOURCE_VIEW_IDS[0]]["decision"]
        + state.partition_counts[SOURCE_VIEW_IDS[1]]["decision"]
        != _count(census.get("decision_join_count"), "decision join count")
        or len(state.seen_seed_ids)
        != _count(census.get("contribution_seed_count"), "contribution seed count")
        or len(state.minute_requirement_commitments)
        != _count(census.get("minute_requirement_count"), "minute requirement count")
        or len(state.seen_terminal_keys)
        != _count(census.get("terminal_disposition_count"), "terminal count")
    ):
        raise FormalCloudEvaluationError("streamed shard resource census diverged")
    terminal = FormalCloudTerminalCensus(
        terminal_policy_id=TERMINAL_POLICY_ID,
        terminal_requirement_count=len(state.seen_terminal_keys),
        terminal_payoff_count=state.terminal_counts["terminal_payoff"],
        benchmark_splice_continuation_count=state.terminal_counts[
            "benchmark_splice_continuation"
        ],
        named_terminal_refusal_count=state.terminal_counts[
            "named_terminal_refusal"
        ],
        used_terminal_disposition_count=len(state.seen_terminal_keys),
        unused_terminal_disposition_count=0,
        silently_omitted_terminal_count=0,
    )
    _validate_stream_contract_census(state, terminal)
    try:
        results = tuple(
            _evaluation.finish_formal_evaluation_stream(item, resamples=resamples)
            for item in state.host_streams
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError(
            "frozen streaming evaluator refused the compact census"
        ) from exc
    state.finished = True
    variant_trial_states = {
        view: _finish_report_variant_state(
            state=state, source_view_id=view
        )
        for view in SOURCE_VIEW_IDS
    }
    payload, family_objects = _streaming_aggregate(
        results=results, streams=state.host_streams,
        bindings=state.bindings, preknown_bindings=state.preknown_bindings,
        terminal_census=terminal,
        report_contract=state.contract.get("formal_report_contract"),
        coverages=(
            *state.contract.get("global_comparator_fold_coverages", ()),
            *state.contract.get("global_comparator_pooled_coverages", ()),
        ),
        partition_counts=state.partition_counts,
        terminal_attribution=state.terminal_attribution,
        variant_trial_states=variant_trial_states,
        directional_event_observations=(
            state.directional_event_report_observations
        ),
        decision_report_observations=state.decision_report_observations,
        subset_fm_report_observations=(
            state.subset_fm_report_observations
        ),
        resamples=resamples,
        externalize_report_families=externalize_report_families,
    )
    require_formal_cloud_evaluation_aggregate_bytes(
        payload, expected_bindings=state.bindings,
        expected_bootstrap_resamples=resamples,
        report_family_object_payloads=(
            {
                item.descriptor["object_store_key_suffix"]: item.payload
                for item in family_objects
            }
            if family_objects else None
        ),
    )
    _authority_update(value, state)
    return payload, family_objects


def _finish_compact_formal_evaluation_legacy_impl(
    stream: FormalCloudCompactStream, *, resamples: int = BOOTSTRAP_RESAMPLES,
    _finish_impl: object,
) -> bytes:
    """Legacy local-only aggregate with embedded family payloads.

    The projected streamed runtime never calls this compatibility entrypoint;
    it uses :func:`finish_compact_formal_evaluation_output` so the 26 family
    payloads cannot overflow the summary-statistics channel.
    """

    payload, family_objects = _finish_impl(
        stream, resamples=resamples, externalize_report_families=False,
    )
    if family_objects:
        raise FormalCloudEvaluationError(
            "legacy aggregate unexpectedly externalized report families"
        )
    return payload


def _finish_compact_formal_evaluation_output_impl(
    stream: FormalCloudCompactStream, *, resamples: int = BOOTSTRAP_RESAMPLES,
    _finish_impl: object,
    _authority_register: object,
    _authority_require: object,
) -> FormalCloudEvaluationOutput:
    """Seal the production stream into one root plus 26 exact gzip objects."""

    root_manifest, family_objects = _finish_impl(
        stream, resamples=resamples, externalize_report_families=True,
    )
    if len(family_objects) != 2 * len(REPORT_FAMILY_IDS):
        raise FormalCloudEvaluationError(
            "multipart evaluation output omitted a report-family object"
        )
    total_uncompressed = sum(
        item.descriptor["uncompressed_byte_count"] for item in family_objects
    )
    total_compressed = sum(len(item.payload) for item in family_objects)
    root_sha256 = hashlib.sha256(root_manifest).hexdigest()
    seed = {
        "schema": FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA,
        "root_manifest_sha256": root_sha256,
        "root_manifest_byte_count": len(root_manifest),
        "bootstrap_resamples": resamples,
        "family_object_count": len(family_objects),
        "total_uncompressed_byte_count": total_uncompressed,
        "total_compressed_byte_count": total_compressed,
        "family_object_inventory_sha256": hashlib.sha256(_canonical_bytes([
            item.descriptor for item in family_objects
        ])).hexdigest(),
    }
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    value = object.__new__(FormalCloudEvaluationOutput)
    fields = {
        "output_id": f"arv2-formal-cloud-output-{digest[:24]}",
        "output_sha256": digest,
        **{key: item for key, item in seed.items() if key != "family_object_inventory_sha256"},
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    state = _CloudEvaluationOutputState(
        creator_pid=os.getpid(), owner_thread_id=threading.get_ident(),
        root_manifest=root_manifest, family_objects=family_objects,
        consumed=False, failed=False,
    )
    _authority_register(
        value, _cloud_evaluation_output_static(value), state
    )
    return _authority_require(value)[0]


def _require_formal_cloud_evaluation_output_impl(
    value: FormalCloudEvaluationOutput,
    *,
    _authority_require: object,
) -> FormalCloudEvaluationOutput:
    """Reauthenticate one unconsumed multipart output handle."""

    output, state = _authority_require(value)
    if state.consumed:
        raise FormalCloudEvaluationError(
            "cloud evaluation output payloads were already consumed"
        )
    return output


def _consume_formal_cloud_evaluation_output_impl(
    value: FormalCloudEvaluationOutput,
    *,
    _authority_require: object,
    _authority_update: object,
) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    """Return exact output bytes once, invalidating the in-process carrier."""

    output, state = _authority_require(value)
    if state.consumed:
        raise FormalCloudEvaluationError(
            "cloud evaluation output payloads were already consumed"
        )
    payloads = {
        item.descriptor["object_store_key_suffix"]: item.payload
        for item in state.family_objects
    }
    if len(payloads) != len(state.family_objects):
        state.failed = True
        _authority_update(output, state)
        raise FormalCloudEvaluationError(
            "cloud evaluation output duplicated an Object Store suffix"
        )
    try:
        if (
            len(state.root_manifest) != output.root_manifest_byte_count
            or hashlib.sha256(state.root_manifest).hexdigest()
            != output.root_manifest_sha256
            or len(state.family_objects) != output.family_object_count
            or sum(
                item.descriptor["uncompressed_byte_count"]
                for item in state.family_objects
            ) != output.total_uncompressed_byte_count
            or sum(len(item.payload) for item in state.family_objects)
            != output.total_compressed_byte_count
        ):
            raise FormalCloudEvaluationError(
                "cloud evaluation output carrier identity changed"
            )
        require_formal_cloud_evaluation_aggregate_bytes(
            state.root_manifest,
            expected_bootstrap_resamples=output.bootstrap_resamples,
            report_family_object_payloads=payloads,
        )
    except (
        FormalCloudEvaluationError, AttributeError, KeyError, TypeError,
        ValueError,
    ):
        state.failed = True
        _authority_update(output, state)
        raise
    state.consumed = True
    _authority_update(output, state)
    return (
        state.root_manifest,
        tuple(
            (item.descriptor["object_store_key_suffix"], item.payload)
            for item in state.family_objects
        ),
    )


def _bind_cloud_evaluation_authorities(
    *,
    configure_callers: object,
    register_compact: object,
    lookup_compact: object,
    update_compact: object,
    register_panel: object,
    lookup_panel: object,
    update_panel: object,
    register_output: object,
    lookup_output: object,
    update_output: object,
    require_compact_impl: object,
    require_panel_impl: object,
    require_output_impl: object,
    begin_compact_impl: object,
    consume_compact_impl: object,
    finish_compact_impl: object,
    finish_legacy_impl: object,
    finish_output_impl: object,
    require_output_public_impl: object,
    consume_output_impl: object,
    begin_panel_impl: object,
    consume_panel_impl: object,
    finish_panel_impl: object,
) -> tuple[object, ...]:
    """Bind every authority mutation to its single legal state transition.

    The returned API never exposes an authority registrar, registry lookup, or
    reset callback.  The at-fork callback was registered while the vault was
    still lexical, so deleting the temporary module bindings below does not
    weaken child-process invalidation.
    """

    def require_compact_internal(
        value: FormalCloudCompactStream,
    ) -> tuple[FormalCloudCompactStream, _CompactStreamState]:
        return require_compact_impl(value, _authority_lookup=lookup_compact)

    def require_panel_internal(
        value: FormalMarketPanelDigest,
    ) -> tuple[FormalMarketPanelDigest, _MarketPanelDigestState]:
        return require_panel_impl(value, _authority_lookup=lookup_panel)

    def require_output_internal(
        value: FormalCloudEvaluationOutput,
    ) -> tuple[FormalCloudEvaluationOutput, _CloudEvaluationOutputState]:
        return require_output_impl(value, _authority_lookup=lookup_output)

    def begin_formal_market_panel_digest(
        expected_observation_count: int,
    ) -> FormalMarketPanelDigest:
        return begin_panel_impl(
            expected_observation_count,
            _authority_register=register_panel,
            _authority_require=require_panel_internal,
        )

    def consume_formal_market_panel_digest_row(
        digest: FormalMarketPanelDigest,
        *,
        requirement: Mapping[str, object],
        observation: Mapping[str, object],
    ) -> FormalMarketPanelDigest:
        return consume_panel_impl(
            digest,
            requirement=requirement,
            observation=observation,
            _authority_require=require_panel_internal,
            _authority_update=update_panel,
        )

    def finish_formal_market_panel_digest(
        digest: FormalMarketPanelDigest,
    ) -> tuple[str, int]:
        return finish_panel_impl(
            digest, _authority_require=require_panel_internal,
            _authority_update=update_panel,
        )

    def begin_compact_formal_evaluation(
        *,
        manifest: Mapping[str, object],
        formal_contract_rows: Sequence[object],
        economic_joins: Sequence[object],
        terminal_dispositions: Sequence[object],
        shared_market_panel_sha256: str,
        shared_market_panel_observation_count: int,
    ) -> FormalCloudCompactStream:
        return begin_compact_impl(
            manifest=manifest,
            formal_contract_rows=formal_contract_rows,
            economic_joins=economic_joins,
            terminal_dispositions=terminal_dispositions,
            shared_market_panel_sha256=shared_market_panel_sha256,
            shared_market_panel_observation_count=(
                shared_market_panel_observation_count
            ),
            _authority_register=register_compact,
            _authority_require=require_compact_internal,
        )

    def consume_compact_formal_session_block(
        stream: FormalCloudCompactStream,
        *,
        fold_id: str,
        session: str,
        session_position: int,
        decision_joins: Sequence[object],
        new_contribution_seeds: Sequence[object],
        daily_requirements: Sequence[object],
        minute_requirements: Sequence[object],
        observations: Mapping[str, object],
    ) -> FormalCloudCompactStream:
        return consume_compact_impl(
            stream,
            fold_id=fold_id,
            session=session,
            session_position=session_position,
            decision_joins=decision_joins,
            new_contribution_seeds=new_contribution_seeds,
            daily_requirements=daily_requirements,
            minute_requirements=minute_requirements,
            observations=observations,
            _authority_require=require_compact_internal,
            _authority_update=update_compact,
        )

    def finish_compact_internal(
        stream: FormalCloudCompactStream,
        *,
        resamples: int,
        externalize_report_families: bool,
    ) -> tuple[bytes, tuple[_ReportFamilyObject, ...]]:
        return finish_compact_impl(
            stream,
            resamples=resamples,
            externalize_report_families=externalize_report_families,
            _authority_require=require_compact_internal,
            _authority_update=update_compact,
        )

    def finish_compact_formal_evaluation(
        stream: FormalCloudCompactStream,
        *,
        resamples: int = BOOTSTRAP_RESAMPLES,
    ) -> bytes:
        return finish_legacy_impl(
            stream, resamples=resamples, _finish_impl=finish_compact_internal
        )

    def finish_compact_formal_evaluation_output(
        stream: FormalCloudCompactStream,
        *,
        resamples: int = BOOTSTRAP_RESAMPLES,
    ) -> FormalCloudEvaluationOutput:
        return finish_output_impl(
            stream,
            resamples=resamples,
            _finish_impl=finish_compact_internal,
            _authority_register=register_output,
            _authority_require=require_output_internal,
        )

    def require_formal_cloud_evaluation_output(
        value: FormalCloudEvaluationOutput,
    ) -> FormalCloudEvaluationOutput:
        return require_output_public_impl(
            value, _authority_require=require_output_internal
        )

    def consume_formal_cloud_evaluation_output(
        value: FormalCloudEvaluationOutput,
    ) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
        return consume_output_impl(
            value, _authority_require=require_output_internal,
            _authority_update=update_output,
        )

    def seal_authority_callers() -> None:
        # Seal only after the complete module has been defined.  Some exact
        # implementations resolve validators declared below this binder; an
        # early absence snapshot would otherwise invalidate legitimate calls.
        configure_callers(
            (
                (begin_compact_impl, begin_compact_formal_evaluation),
                (begin_panel_impl, begin_formal_market_panel_digest),
                (finish_output_impl, finish_compact_formal_evaluation_output),
            ),
            (
                (consume_compact_impl, consume_compact_formal_session_block),
                (
                    finish_compact_impl, finish_compact_internal,
                    finish_legacy_impl, finish_compact_formal_evaluation,
                ),
                (
                    finish_compact_impl, finish_compact_internal,
                    finish_output_impl,
                    finish_compact_formal_evaluation_output,
                ),
                (consume_panel_impl, consume_formal_market_panel_digest_row),
                (finish_panel_impl, finish_formal_market_panel_digest),
                (consume_output_impl, consume_formal_cloud_evaluation_output),
            ),
        )

    return (
        begin_formal_market_panel_digest,
        consume_formal_market_panel_digest_row,
        finish_formal_market_panel_digest,
        begin_compact_formal_evaluation,
        consume_compact_formal_session_block,
        finish_compact_formal_evaluation,
        finish_compact_formal_evaluation_output,
        require_formal_cloud_evaluation_output,
        consume_formal_cloud_evaluation_output,
        seal_authority_callers,
    )


(
    begin_formal_market_panel_digest,
    consume_formal_market_panel_digest_row,
    finish_formal_market_panel_digest,
    begin_compact_formal_evaluation,
    consume_compact_formal_session_block,
    finish_compact_formal_evaluation,
    finish_compact_formal_evaluation_output,
    require_formal_cloud_evaluation_output,
    consume_formal_cloud_evaluation_output,
    _seal_cloud_evaluation_authority_callers,
) = _bind_cloud_evaluation_authorities(
    configure_callers=_configure_cloud_stream_authority_callers,
    register_compact=_register_compact_stream_authority,
    lookup_compact=_lookup_compact_stream_authority,
    update_compact=_update_compact_stream_authority,
    register_panel=_register_market_panel_authority,
    lookup_panel=_lookup_market_panel_authority,
    update_panel=_update_market_panel_authority,
    register_output=_register_cloud_evaluation_output_authority,
    lookup_output=_lookup_cloud_evaluation_output_authority,
    update_output=_update_cloud_evaluation_output_authority,
    require_compact_impl=_require_compact_stream_impl,
    require_panel_impl=_require_market_panel_digest_impl,
    require_output_impl=_require_cloud_evaluation_output_impl,
    begin_compact_impl=_begin_compact_formal_evaluation_impl,
    consume_compact_impl=_consume_compact_formal_session_block_impl,
    finish_compact_impl=_finish_compact_formal_evaluation,
    finish_legacy_impl=_finish_compact_formal_evaluation_legacy_impl,
    finish_output_impl=_finish_compact_formal_evaluation_output_impl,
    require_output_public_impl=_require_formal_cloud_evaluation_output_impl,
    consume_output_impl=_consume_formal_cloud_evaluation_output_impl,
    begin_panel_impl=_begin_formal_market_panel_digest_impl,
    consume_panel_impl=_consume_formal_market_panel_digest_row_impl,
    finish_panel_impl=_finish_formal_market_panel_digest_impl,
)

del _bind_cloud_evaluation_authorities
del _register_compact_stream_authority
del _lookup_compact_stream_authority
del _update_compact_stream_authority
del _register_market_panel_authority
del _lookup_market_panel_authority
del _update_market_panel_authority
del _register_cloud_evaluation_output_authority
del _lookup_cloud_evaluation_output_authority
del _update_cloud_evaluation_output_authority
del _configure_cloud_stream_authority_callers
del _require_compact_stream_impl
del _require_market_panel_digest_impl
del _require_cloud_evaluation_output_impl
del _begin_compact_formal_evaluation_impl
del _consume_compact_formal_session_block_impl
del _finish_compact_formal_evaluation
del _finish_compact_formal_evaluation_legacy_impl
del _finish_compact_formal_evaluation_output_impl
del _require_formal_cloud_evaluation_output_impl
del _consume_formal_cloud_evaluation_output_impl
del _begin_formal_market_panel_digest_impl
del _consume_formal_market_panel_digest_row_impl
del _finish_formal_market_panel_digest_impl


def build_cloud_formal_evaluation_inputs(
    *, manifest: Mapping[str, object], shards: Mapping[str, object],
    observations: Mapping[str, object],
) -> tuple[
    tuple[_evaluation.FormalEvaluationInput, ...],
    FormalCloudEvaluationBindings,
    FormalCloudTerminalCensus,
]:
    """Expand compact authenticated joins into the exact frozen host inputs."""

    benchmark_security_id = _manifest_geometry(manifest)
    if type(shards) is not dict or set(shards) != {
        "formal_contract", "contribution_seeds", "decision_joins",
        "economic_joins", "daily_requirements", "minute_requirements",
        "terminal_dispositions",
    }:
        raise FormalCloudEvaluationError("compact shard role inventory changed")
    _resource_census(manifest, shards)
    contract = _parse_contract(shards["formal_contract"], manifest)
    daily_requirements = _parse_daily_requirements(shards["daily_requirements"])
    minute_requirements = _parse_minute_requirements(shards["minute_requirements"])
    _validate_runtime_resource_values(
        manifest=manifest, daily=daily_requirements, minute=minute_requirements
    )
    daily, minute, panel_sha256, panel_count = _parse_observations(
        observations, daily_requirements, minute_requirements
    )
    terminals = _parse_terminal_rows(shards["terminal_dispositions"])
    seeds = _parse_contribution_seeds(
        shards["contribution_seeds"], minute_requirements
    )
    economic_joins = _parse_economic_joins(
        shards["economic_joins"],
        streamed=contract.get("contract_variant")
        == STREAMED_FORMAL_CONTRACT_VARIANT,
    )
    axes = _fold_axes(contract, economic_joins)
    economic_axes = _economic_axes(contract, economic_joins)
    decisions = _parse_decisions(
        shards["decision_joins"], seeds, daily_requirements,
        contract["scoring_result_bindings"], benchmark_security_id, axes,
    )
    runtime_start = _iso_date(manifest["runtime_start"], "runtime start")
    runtime_end = _iso_date(manifest["runtime_end"], "runtime end")
    for row in decisions:
        decision_date = _iso_date(row["decision_session"], "decision session")
        if decision_date < runtime_start or decision_date > runtime_end:
            raise FormalCloudEvaluationError("decision escaped runtime interval")
        for exit_row in row["horizon_exits"]:
            if _iso_date(exit_row["exit_session"], "exit session") > runtime_end:
                raise FormalCloudEvaluationError("decision exit escaped runtime interval")
    for row in economic_joins:
        session_date = _iso_date(row["session"], "economic session")
        next_date = (
            None
            if row["next_session"] is None
            else _iso_date(row["next_session"], "next economic session")
        )
        if session_date < runtime_start or session_date > runtime_end or (
            next_date is not None and next_date > runtime_end
        ):
            raise FormalCloudEvaluationError("economic session escaped runtime interval")
    used_terminals: set[tuple[str, str, int | None]] = set()
    power_floor = _contract_power_floor(contract)
    inputs: list[_evaluation.FormalEvaluationInput] = []
    try:
        for view in SOURCE_VIEW_IDS:
            rows, refusals = _event_rows(
                view=view, decisions=decisions, seeds=seeds, daily=daily,
                minute=minute, terminals=terminals,
                used_terminals=used_terminals,
                fold_axes=axes,
            )
            accepted_h20_keys = {
                (item.fold_id, item.session_position, item.security_id)
                for item in rows if item.horizon_sessions == 20
            }
            economic_sessions = _economic_sessions(
                view=view, decisions=decisions,
                accepted_h20_keys=accepted_h20_keys, joins=economic_joins,
                daily=daily, terminals=terminals,
                used_terminals=used_terminals,
                benchmark_security_id=benchmark_security_id,
            )
            inputs.append(
                _evaluation.build_formal_evaluation_input(
                    source_view_id=view,
                    source_bundle_id=contract["evaluation_input_bundle_id"],
                    source_bundle_sha256=contract["evaluation_input_bundle_sha256"],
                    source_artifact_sha256=panel_sha256,
                    fold_axes=axes,
                    economic_observation_axes=economic_axes,
                    economic_execution_definition_sha256=(
                        contract["economic_execution_definition"][
                            "definition_sha256"
                        ]
                        if contract.get("contract_variant")
                        == STREAMED_FORMAL_CONTRACT_VARIANT
                        else _evaluation.ECONOMIC_EXECUTION_DEFINITION_SHA256
                    ),
                    power_floor=power_floor,
                    rows=rows,
                    refusals=refusals,
                    economic_sessions=economic_sessions,
                )
            )
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalCloudEvaluationError):
            raise
        raise FormalCloudEvaluationError(
            "compact joins could not build the frozen formal inputs"
        ) from exc
    terminal_census = _terminal_census(terminals, used_terminals)
    if used_terminals != set(terminals):
        raise FormalCloudEvaluationError(
            "an actual lifecycle terminal disposition was not consumed"
        )
    _validate_contract_censuses(
        contract=contract, decisions=decisions, terminal_census=terminal_census
    )
    bindings = _bindings(
        manifest=manifest, contract=contract,
        market_panel_sha256=panel_sha256, market_panel_count=panel_count,
    )
    return tuple(inputs), bindings, terminal_census


def execute_compact_formal_evaluation(
    *, manifest: Mapping[str, object], shards: Mapping[str, object],
    observations: Mapping[str, object],
) -> bytes:
    """Cloud entrypoint: validate, expand, evaluate, and return aggregates only."""

    inputs, bindings, terminal_census = build_cloud_formal_evaluation_inputs(
        manifest=manifest, shards=shards, observations=observations
    )
    return execute_cloud_formal_evaluation(
        inputs=inputs, bindings=bindings, terminal_census=terminal_census
    )


def _axis_censuses(
    inputs: tuple[_evaluation.FormalEvaluationInput, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    fold_axis: list[dict[str, object]] = []
    view_axis: list[dict[str, object]] = []
    for fold in FORMAL_FOLD_IDS:
        for horizon in HORIZONS:
            accepted = sum(
                row.fold_id == fold and row.horizon_sessions == horizon
                for value in inputs for row in value.rows
            )
            refused = sum(
                row.fold_id == fold and row.horizon_sessions == horizon
                for value in inputs for row in value.refusals
            )
            fold_axis.append(
                {
                    "fold_id": fold,
                    "horizon": horizon,
                    "accepted_count": accepted,
                    "refused_count": refused,
                    "slot_count": accepted + refused,
                }
            )
    for value in inputs:
        for fold in FORMAL_FOLD_IDS:
            for horizon in HORIZONS:
                accepted = sum(
                    row.fold_id == fold and row.horizon_sessions == horizon
                    for row in value.rows
                )
                refused = sum(
                    row.fold_id == fold and row.horizon_sessions == horizon
                    for row in value.refusals
                )
                view_axis.append(
                    {
                        "view_id": value.source_view_id,
                        "fold_id": fold,
                        "horizon": horizon,
                        "accepted_count": accepted,
                        "refused_count": refused,
                        "slot_count": accepted + refused,
                    }
                )
    return fold_axis, view_axis


def _validate_inputs(
    inputs: tuple[_evaluation.FormalEvaluationInput, ...],
    bindings: FormalCloudEvaluationBindings,
) -> tuple[_evaluation.FormalEvaluationInput, _evaluation.FormalEvaluationInput]:
    if (
        type(inputs) is not tuple
        or len(inputs) != 2
        or any(type(item) is not _evaluation.FormalEvaluationInput for item in inputs)
    ):
        raise FormalCloudEvaluationError("exactly two typed source-view inputs are required")
    if type(bindings) is not FormalCloudEvaluationBindings:
        raise FormalCloudEvaluationError("cloud evaluation bindings changed type")
    bindings.__post_init__()
    try:
        for item in inputs:
            _evaluation.require_formal_evaluation_input(item)
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError("formal evaluation input changed") from exc
    if tuple(item.source_view_id for item in inputs) != SOURCE_VIEW_IDS:
        raise FormalCloudEvaluationError("source views are omitted, collapsed, or reordered")
    current, censored = inputs
    if (
        current.fold_axes != censored.fold_axes
        or current.economic_observation_axes
        != censored.economic_observation_axes
        or current.economic_execution_definition_sha256
        != censored.economic_execution_definition_sha256
        or current.source_bundle_id != bindings.evaluation_input_bundle_id
        or censored.source_bundle_id != bindings.evaluation_input_bundle_id
        or current.source_bundle_sha256 != bindings.evaluation_input_bundle_sha256
        or censored.source_bundle_sha256 != bindings.evaluation_input_bundle_sha256
        or current.source_artifact_sha256 != bindings.shared_market_panel_sha256
        or censored.source_artifact_sha256 != bindings.shared_market_panel_sha256
    ):
        raise FormalCloudEvaluationError(
            "source views do not bind one exact input bundle and market panel"
        )
    return current, censored


def _report_document(
    report: _evaluation.FormalEvaluationReport,
) -> dict[str, object]:
    _evaluation.require_formal_evaluation_report(report)
    try:
        value = json.loads(report._canonical_document.decode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise FormalCloudEvaluationError(
            "formal evaluator returned noncanonical report bytes"
        ) from exc
    if type(value) is not dict or json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii") != report._canonical_document:
        raise FormalCloudEvaluationError(
            "formal evaluator report replay bytes changed"
        )
    return value


def _report_family_document(
    *, contract_sha256: str, source_view_id: str,
    schema: Mapping[str, object], rows: Sequence[Mapping[str, object]],
    report_contract: Mapping[str, object],
) -> dict[str, object]:
    keys = tuple(schema["ordered_key_fields"])
    values = tuple(schema["ordered_value_fields"])
    fields = (*keys, *values)
    prepared: list[tuple[tuple[object, ...], list[object]]] = []
    expected_fields = set((*keys, *values))
    observed_keys: set[tuple[object, ...]] = set()
    for raw in rows:
        row = dict(raw)
        if set(row) != expected_fields or row.get("source_view_id") != source_view_id:
            raise FormalCloudEvaluationError("report-family cell fields changed")
        key = tuple(row[name] for name in keys)
        try:
            duplicate = key in observed_keys
        except TypeError as exc:
            raise FormalCloudEvaluationError(
                "report-family key cell is not scalar"
            ) from exc
        if duplicate:
            raise FormalCloudEvaluationError("report-family duplicated a cell")
        observed_keys.add(key)
        cells = [_report_wire_cell(row[name]) for name in fields]
        if any(len(_canonical_bytes(cell)) > 8_192 for cell in cells):
            raise FormalCloudEvaluationError(
                "report-family cell exceeds the authenticated byte ceiling"
            )
        maximum_row_bytes = report_contract["numeric_and_output_rules"].get(
            "maximum_encoded_bytes_per_report_row"
        )
        if (
            type(maximum_row_bytes) is not int
            or maximum_row_bytes < 1
            or len(_canonical_bytes(cells)) > maximum_row_bytes
        ):
            raise FormalCloudEvaluationError(
                "report-family row exceeds the authenticated byte ceiling"
            )
        prepared.append((
            _report_family_order_key(row, schema, report_contract), cells
        ))
    prepared.sort(key=lambda item: item[0])
    if any(
        prepared[index - 1][0] >= prepared[index][0]
        for index in range(1, len(prepared))
    ):
        raise FormalCloudEvaluationError(
            "report-family cells do not have one strict canonical order"
        )
    normalized = [cells for _key, cells in prepared]
    if not normalized:
        raise FormalCloudEvaluationError(
            "report-family omitted its required explicit cells"
        )
    if len(normalized) > schema["maximum_rows_per_source_view"]:
        raise FormalCloudEvaluationError("report-family row limit exceeded")
    seed = {
        "schema": "arv2-formal-report-family-output-v1",
        "formal_report_contract_sha256": contract_sha256,
        "source_view_id": source_view_id,
        "family_schema": dict(schema),
        "row_count": len(normalized),
        "rows": normalized,
        "raw_security_event_or_market_rows_exported": False,
    }
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    return {
        **seed,
        "family_output_id": f"arv2-formal-report-family-output-{digest[:24]}",
        "family_output_sha256": digest,
    }


def _report_wire_cell(value: object) -> object:
    """Translate evaluator wrappers to the compact report-cell encoding."""

    if type(value) in {str, int, bool} or value is None:
        return value
    if type(value) is Decimal:
        if not value.is_finite():
            raise FormalCloudEvaluationError("report Decimal cell is not finite")
        return _decimal_text(value)
    if type(value) is Fraction:
        return [value.numerator, value.denominator]
    if type(value) is list:
        return [_report_wire_cell(item) for item in value]
    if type(value) is dict:
        if set(value) == {"decimal"}:
            return _decimal_text(
                _decimal(value["decimal"], "report Decimal cell")
            )
        if set(value) == {"fraction"}:
            raw = value["fraction"]
            if (
                type(raw) is not list or len(raw) != 2
                or type(raw[0]) is not int or type(raw[1]) is not int
                or raw[1] <= 0
            ):
                raise FormalCloudEvaluationError(
                    "report Fraction cell changed"
                )
            reduced = Fraction(*raw)
            if (reduced.numerator, reduced.denominator) != tuple(raw):
                raise FormalCloudEvaluationError(
                    "report Fraction cell is not reduced"
                )
            return [reduced.numerator, reduced.denominator]
        return {
            str(key): _report_wire_cell(item)
            for key, item in sorted(value.items())
        }
    raise FormalCloudEvaluationError("report cell has an unsupported type")


def _gzip_report_family(
    family: Mapping[str, object],
    *,
    uncompressed_byte_ceiling: int,
    compressed_byte_ceiling: int,
) -> tuple[bytes, bytes]:
    raw = _canonical_bytes(family)
    if len(raw) > uncompressed_byte_ceiling:
        raise FormalCloudEvaluationError(
            "report-family output exceeds its predeclared object capacity"
        )
    payload_buffer = bytearray(gzip.compress(raw, compresslevel=9, mtime=0))
    payload_buffer[9] = 255
    payload = bytes(payload_buffer)
    if len(payload) > compressed_byte_ceiling:
        raise FormalCloudEvaluationError(
            "compressed report-family object exceeds its predeclared capacity"
        )
    return raw, payload


def _report_family_chunk(family: Mapping[str, object]) -> dict[str, object]:
    raw, payload = _gzip_report_family(
        family,
        uncompressed_byte_ceiling=MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES,
        compressed_byte_ceiling=MAX_REPORT_FAMILY_CHUNK_COMPRESSED_BYTES,
    )
    return {
        "schema": REPORT_FAMILY_CHUNK_SCHEMA,
        "source_view_id": family["source_view_id"],
        "family_id": family["family_schema"]["family_id"],
        "family_output_id": family["family_output_id"],
        "family_output_sha256": family["family_output_sha256"],
        "uncompressed_byte_count": len(raw),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_byte_count": len(payload),
        "compressed_sha256": hashlib.sha256(payload).hexdigest(),
        "encoding": REPORT_FAMILY_CHUNK_ENCODING,
        "payload": base64.urlsafe_b64encode(payload).decode("ascii"),
    }


def _report_family_object_capacity(
    report_contract: Mapping[str, object], family_id: str,
) -> tuple[int, int]:
    rules = report_contract.get("numeric_and_output_rules")
    if type(rules) is not dict:
        raise FormalCloudEvaluationError("report output rules changed type")
    capacities = rules.get("report_family_object_capacities")
    if type(capacities) is not list:
        raise FormalCloudEvaluationError(
            "report-family object capacities changed type"
        )
    by_id: dict[str, dict[str, object]] = {}
    for raw in capacities:
        if type(raw) is not dict or set(raw) != {
            "family_id", "maximum_row_count_per_source_view",
            "maximum_encoded_bytes_per_row",
            "uncompressed_byte_ceiling", "compressed_byte_ceiling",
        }:
            raise FormalCloudEvaluationError(
                "report-family object capacity fields changed"
            )
        current_id = _safe_id(raw["family_id"], "capacity family id")
        if current_id in by_id:
            raise FormalCloudEvaluationError(
                "report-family object capacity was duplicated"
            )
        by_id[current_id] = raw
    if tuple(by_id) != REPORT_FAMILY_IDS or family_id not in by_id:
        raise FormalCloudEvaluationError(
            "report-family object capacity inventory changed"
        )
    capacity = by_id[family_id]
    schema = next(
        item for item in report_contract["report_schemas"]
        if item["family_id"] == family_id
    )
    maximum_rows = _count(
        capacity["maximum_row_count_per_source_view"],
        "capacity maximum row count", minimum=1,
    )
    maximum_row_bytes = _count(
        capacity["maximum_encoded_bytes_per_row"],
        "capacity maximum row bytes", minimum=1,
    )
    uncompressed = _count(
        capacity["uncompressed_byte_ceiling"],
        "capacity uncompressed family bytes", minimum=1,
    )
    compressed = _count(
        capacity["compressed_byte_ceiling"],
        "capacity compressed family bytes", minimum=1,
    )
    if (
        maximum_rows != schema["maximum_rows_per_source_view"]
        or maximum_row_bytes
        != rules.get("maximum_encoded_bytes_per_report_row")
        or uncompressed != MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES
        or compressed != MAX_REPORT_FAMILY_CHUNK_COMPRESSED_BYTES
        or rules.get("report_family_operational_capacity_precedence")
        != (
            "the_fixed_per_family_and_total_object_byte_ceilings_are_the_"
            "authoritative_first_formal_run_admission_caps_and_supersede_"
            "the_larger_combinatorial_row_envelope;_an_oversize_family_"
            "refuses_the_run_before_any_root_manifest_is_published"
        )
    ):
        raise FormalCloudEvaluationError(
            "report-family object capacity arithmetic changed"
        )
    return uncompressed, compressed


def _report_family_object(
    family: Mapping[str, object],
    *,
    ordinal: int,
    input_manifest_sha256: str,
    report_contract: Mapping[str, object],
) -> _ReportFamilyObject:
    family_id = _safe_id(
        family["family_schema"]["family_id"], "report-family id"
    )
    uncompressed_ceiling, compressed_ceiling = (
        _report_family_object_capacity(report_contract, family_id)
    )
    raw, payload = _gzip_report_family(
        family,
        uncompressed_byte_ceiling=uncompressed_ceiling,
        compressed_byte_ceiling=compressed_ceiling,
    )
    compressed_sha256 = hashlib.sha256(payload).hexdigest()
    suffix = (
        REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
        + _sha(input_manifest_sha256, "input manifest hash")
        + "/"
        + str(ordinal).zfill(2)
        + "-"
        + compressed_sha256
        + "-json.gz"
    )
    descriptor = {
        "schema": REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
        "role": "formal_report_family",
        "ordinal": ordinal,
        "source_view_id": family["source_view_id"],
        "family_id": family_id,
        "family_output_id": family["family_output_id"],
        "family_output_sha256": family["family_output_sha256"],
        "payload_schema": "arv2-formal-report-family-output-v1",
        "row_count": family["row_count"],
        "formal_cloud_evaluator_contract_sha256": (
            FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
        ),
        "input_manifest_sha256": input_manifest_sha256,
        "formal_report_contract_sha256": report_contract["contract_sha256"],
        "object_store_key_suffix": suffix,
        "uncompressed_byte_count": len(raw),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_byte_count": len(payload),
        "compressed_sha256": compressed_sha256,
        "encoding": REPORT_FAMILY_CHUNK_ENCODING,
    }
    return _ReportFamilyObject(descriptor=descriptor, payload=payload)


def _decode_report_family_chunk(value: object) -> dict[str, object]:
    chunk = _exact_object(
        value,
        (
            "schema", "source_view_id", "family_id", "family_output_id",
            "family_output_sha256", "uncompressed_byte_count",
            "uncompressed_sha256", "compressed_byte_count",
            "compressed_sha256", "encoding", "payload",
        ),
        "report-family chunk",
    )
    if (
        chunk["schema"] != REPORT_FAMILY_CHUNK_SCHEMA
        or chunk["encoding"] != REPORT_FAMILY_CHUNK_ENCODING
        or type(chunk["uncompressed_byte_count"]) is not int
        or not 0 < chunk["uncompressed_byte_count"]
        <= MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES
        or type(chunk["compressed_byte_count"]) is not int
        or not 0 < chunk["compressed_byte_count"]
        <= MAX_REPORT_FAMILY_CHUNK_COMPRESSED_BYTES
        or type(chunk["payload"]) is not str or not chunk["payload"]
    ):
        raise FormalCloudEvaluationError("report-family chunk contract changed")
    try:
        payload = base64.b64decode(
            chunk["payload"].encode("ascii"), altchars=b"-_", validate=True
        )
    except (UnicodeError, ValueError) as exc:
        raise FormalCloudEvaluationError(
            "report-family chunk is not strict URL-safe base64"
        ) from exc
    if (
        base64.urlsafe_b64encode(payload).decode("ascii") != chunk["payload"]
        or len(payload) != chunk["compressed_byte_count"]
        or hashlib.sha256(payload).hexdigest() != chunk["compressed_sha256"]
        or len(payload) < 18 or payload[:4] != b"\x1f\x8b\x08\x00"
        or payload[4:8] != b"\x00\x00\x00\x00"
        or payload[8] != 2 or payload[9] != 255
    ):
        raise FormalCloudEvaluationError("report-family chunk identity changed")
    try:
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        raw = decoder.decompress(
            payload, MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES + 1
        )
        if (
            len(raw) > MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES
            or decoder.unconsumed_tail
        ):
            raise FormalCloudEvaluationError(
                "report-family chunk exceeded its decompression bound"
            )
        raw += decoder.flush(
            MAX_REPORT_FAMILY_CHUNK_UNCOMPRESSED_BYTES - len(raw) + 1
        )
    except (ValueError, zlib.error) as exc:
        raise FormalCloudEvaluationError(
            "report-family chunk is not canonical gzip"
        ) from exc
    if (
        len(raw) != chunk["uncompressed_byte_count"]
        or hashlib.sha256(raw).hexdigest() != chunk["uncompressed_sha256"]
        or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
    ):
        raise FormalCloudEvaluationError(
            "report-family chunk decompressed identity changed"
        )
    family = _strict_aggregate_object(raw)
    if (
        family.get("source_view_id") != chunk["source_view_id"]
        or family.get("family_schema", {}).get("family_id")
        != chunk["family_id"]
        or family.get("family_output_id") != chunk["family_output_id"]
        or family.get("family_output_sha256")
        != chunk["family_output_sha256"]
    ):
        raise FormalCloudEvaluationError(
            "report-family chunk descriptor differs from its content"
        )
    return family


def _decode_report_family_object(
    descriptor: object,
    payload: bytes,
    *,
    report_contract: Mapping[str, object],
    input_manifest_sha256: str,
) -> dict[str, object]:
    reference = _exact_object(
        descriptor,
        (
            "schema", "role", "ordinal", "source_view_id", "family_id",
            "family_output_id", "family_output_sha256",
            "payload_schema", "row_count",
            "formal_cloud_evaluator_contract_sha256",
            "input_manifest_sha256", "formal_report_contract_sha256",
            "object_store_key_suffix", "uncompressed_byte_count",
            "uncompressed_sha256", "compressed_byte_count",
            "compressed_sha256", "encoding",
        ),
        "report-family object reference",
    )
    family_id = _safe_id(reference["family_id"], "report-family id")
    uncompressed_ceiling, compressed_ceiling = (
        _report_family_object_capacity(report_contract, family_id)
    )
    if (
        reference["schema"] != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        or reference["role"] != "formal_report_family"
        or reference["payload_schema"]
        != "arv2-formal-report-family-output-v1"
        or reference["formal_cloud_evaluator_contract_sha256"]
        != FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
        or reference["input_manifest_sha256"] != input_manifest_sha256
        or reference["formal_report_contract_sha256"]
        != report_contract["contract_sha256"]
        or type(reference["row_count"]) is not int
        or reference["row_count"] < 1
        or reference["encoding"] != REPORT_FAMILY_CHUNK_ENCODING
        or type(reference["ordinal"]) is not int
        or not 0 <= reference["ordinal"] < 2 * len(REPORT_FAMILY_IDS)
        or type(reference["uncompressed_byte_count"]) is not int
        or not 0 < reference["uncompressed_byte_count"] <= uncompressed_ceiling
        or type(reference["compressed_byte_count"]) is not int
        or not 0 < reference["compressed_byte_count"] <= compressed_ceiling
        or type(payload) is not bytes
        or not payload
    ):
        raise FormalCloudEvaluationError(
            "report-family object reference contract changed"
        )
    expected_suffix = (
        REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
        + _sha(input_manifest_sha256, "input manifest hash")
        + "/"
        + str(reference["ordinal"]).zfill(2)
        + "-"
        + _sha(reference["compressed_sha256"], "compressed family hash")
        + "-json.gz"
    )
    if reference["object_store_key_suffix"] != expected_suffix:
        raise FormalCloudEvaluationError(
            "report-family Object Store key suffix changed"
        )
    if (
        len(payload) != reference["compressed_byte_count"]
        or hashlib.sha256(payload).hexdigest()
        != reference["compressed_sha256"]
        or len(payload) < 18
        or payload[:4] != b"\x1f\x8b\x08\x00"
        or payload[4:8] != b"\x00\x00\x00\x00"
        or payload[8] != 2
        or payload[9] != 255
    ):
        raise FormalCloudEvaluationError(
            "report-family object compressed identity changed"
        )
    try:
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        raw = decoder.decompress(payload, uncompressed_ceiling + 1)
        if len(raw) > uncompressed_ceiling or decoder.unconsumed_tail:
            raise FormalCloudEvaluationError(
                "report-family object exceeded its decompression bound"
            )
        raw += decoder.flush(uncompressed_ceiling - len(raw) + 1)
    except (ValueError, zlib.error) as exc:
        raise FormalCloudEvaluationError(
            "report-family object is not canonical gzip"
        ) from exc
    if (
        len(raw) != reference["uncompressed_byte_count"]
        or hashlib.sha256(raw).hexdigest()
        != reference["uncompressed_sha256"]
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
    ):
        raise FormalCloudEvaluationError(
            "report-family object decompressed identity changed"
        )
    family = _strict_aggregate_object(raw)
    if (
        family.get("source_view_id") != reference["source_view_id"]
        or family.get("family_schema", {}).get("family_id") != family_id
        or family.get("family_output_id") != reference["family_output_id"]
        or family.get("family_output_sha256")
        != reference["family_output_sha256"]
        or family.get("row_count") != reference["row_count"]
        or family.get("formal_report_contract_sha256")
        != reference["formal_report_contract_sha256"]
    ):
        raise FormalCloudEvaluationError(
            "report-family object descriptor differs from its content"
        )
    return family


def _report_family_order_key(
    row: Mapping[str, object], schema: Mapping[str, object],
    report_contract: Mapping[str, object],
) -> tuple[object, ...]:
    dimensions = report_contract["dimensions"]
    slices = tuple(item["slice_id"] for item in dimensions["slices"])
    slice_index = {item: index for index, item in enumerate(slices)}
    fold_indexes = {
        item["slice_id"]: {
            fold: index
            for index, fold in enumerate(item["report_fold_scope_ids"])
        }
        for item in dimensions["slices"]
    }
    ordered = {
        "source_view_id": {
            item: index for index, item in enumerate(SOURCE_VIEW_IDS)
        },
        "slice_id": slice_index,
        "rating_action": {
            item: index for index, item in enumerate(dimensions["rating_actions"])
        },
        "horizon_sessions": {
            item: index for index, item in enumerate(dimensions["horizons_sessions"])
        },
        "cohort_id": {
            item["cohort_id"]: index
            for index, item in enumerate(dimensions["cohorts"])
        },
        "score_arm": {
            item: index for index, item in enumerate(dimensions["score_arm_ids"])
        },
        "coefficient": {
            item: index
            for index, item in enumerate(
                dimensions["fama_macbeth_coefficient_ids"]
            )
        },
        "event_time_session": {
            item: index
            for index, item in enumerate(dimensions["event_time_sessions"])
        },
        "series_id": {
            item: index
            for index, item in enumerate(dimensions["rolling_series_ids"])
        },
        "trial_id": {
            item["trial_id"]: index
            for index, item in enumerate(
                report_contract["strategy_trial_registry"]["ordered_trials"]
            )
        },
        "record_kind": {
            "preoutcome_coverage_ledger": 0,
            "paired_information_coefficient": 1,
        },
        "accounting_kind": {
            item["accounting_kind"]: index
            for index, item in enumerate(dimensions["f6_accounting_axis"])
        },
    }
    result: list[object] = []
    for name in schema["ordered_key_fields"]:
        value = row[name]
        if name == "fold_id":
            try:
                result.append(fold_indexes[row["slice_id"]][value])
            except (KeyError, TypeError) as exc:
                raise FormalCloudEvaluationError(
                    "report-family fold scope changed"
                ) from exc
        elif name == "record_id" and row.get("record_kind") == (
            "preoutcome_coverage_ledger"
        ):
            try:
                result.append(GLOBAL_COMPARATOR_LEDGER_IDS.index(value))
            except ValueError as exc:
                raise FormalCloudEvaluationError(
                    "report-family coverage ledger changed"
                ) from exc
        elif name == "record_id" and row.get("record_kind") == (
            "paired_information_coefficient"
        ):
            try:
                result.append(HORIZONS.index(int(str(value).rsplit(":h", 1)[1])))
            except (IndexError, ValueError) as exc:
                raise FormalCloudEvaluationError(
                    "report-family paired record changed"
                ) from exc
        elif name == "reason_or_component":
            try:
                accounting_kind = row["accounting_kind"]
                axis = next(
                    item for item in dimensions["f6_accounting_axis"]
                    if item["accounting_kind"] == accounting_kind
                )
                reasons = axis["reason_or_component_ids"]
                if reasons == "exact_six_strategy_trial_registry_ids":
                    reasons = [
                        item["trial_id"] for item in report_contract[
                            "strategy_trial_registry"
                        ]["ordered_trials"]
                    ]
                result.append(tuple(reasons).index(value))
            except (KeyError, StopIteration, TypeError, ValueError) as exc:
                raise FormalCloudEvaluationError(
                    "report-family accounting reason/component changed"
                ) from exc
        elif name in ordered:
            try:
                result.append(ordered[name][value])
            except (KeyError, TypeError) as exc:
                raise FormalCloudEvaluationError(
                    f"report-family {name} dimension changed"
                ) from exc
        else:
            result.append(value)
    return tuple(result)


def _report_cell_status(value: object) -> str:
    if value in {"PASS", "FAIL", "RECONCILED", "READY"}:
        return "AVAILABLE"
    if value in {"INCONCLUSIVE", "INVALID_DATA", "REFUSED", "UNAVAILABLE"}:
        return str(value)
    raise FormalCloudEvaluationError("report cell status changed")


def _report_cell_reasons(value: object, status: str) -> list[str]:
    if status == "AVAILABLE":
        return []
    if type(value) is list and value:
        return [
            "source_summary_named_" + status.lower()
        ]
    return ["source_summary_named_" + status.lower()]


def _scope_fold(value: object) -> str:
    return "POOLED" if value is None else str(value)


def _summary_reasons(raw: Mapping[str, object]) -> list[str]:
    reasons = raw.get("reasons")
    if type(reasons) is list:
        return [str(item) for item in reasons]
    invalid = raw.get("invalid_dates_by_reason")
    if type(invalid) is list:
        return [f"{item[0]}:{item[1]}" for item in invalid]
    return []


def _ic_family_rows(
    report: Mapping[str, object], view: str,
) -> list[dict[str, object]]:
    rows = []
    for raw in report["ic_summaries"]:
        status = _report_cell_status(raw["status"])
        rows.append({
            "source_view_id": view,
            "slice_id": raw["slice_id"],
            "fold_id": _scope_fold(raw["fold_id"]),
            "horizon_sessions": raw["horizon_sessions"],
            "score_arm": (
                "global_map" if raw["arm"] == "global" else raw["arm"]
            ),
            "status": status,
            "valid_date_count": raw["valid_date_count"],
            "invalid_date_count": raw["invalid_date_count"],
            "invalid_dates_by_reason": raw["invalid_dates_by_reason"],
            "mean": raw["mean"],
            "median": raw["median"],
            "positive_date_share": raw["positive_date_share"],
            "icir": raw["icir"],
            "hac_lag_sessions": raw["hac_lag_sessions"],
            "hac_pair_counts": raw["hac_pair_counts"],
            "hac_standard_error": raw["hac_standard_error"],
            "hac_t": raw["hac_t"],
            "reasons": _report_cell_reasons(_summary_reasons(raw), status),
        })
    return rows


def _fm_family_rows(
    report: Mapping[str, object], view: str,
) -> list[dict[str, object]]:
    rows = []
    for raw in report["fama_macbeth_summaries"]:
        if raw["arm"] != "firm_specific":
            continue
        status = _report_cell_status(raw["status"])
        rows.append({
            "source_view_id": view,
            "slice_id": raw["slice_id"],
            "fold_id": _scope_fold(raw["fold_id"]),
            "horizon_sessions": raw["horizon_sessions"],
            "coefficient": raw["coefficient"],
            "status": status,
            "valid_date_count": raw["valid_date_count"],
            "invalid_date_count": raw["invalid_date_count"],
            "invalid_dates_by_reason": raw["invalid_dates_by_reason"],
            "parameter_count_by_date": raw["parameter_count_by_date"],
            "mean_beta": raw["mean_beta"],
            "median_beta": raw["median_beta"],
            "hac_lag_sessions": raw["hac_lag_sessions"],
            "hac_pair_counts": raw["hac_pair_counts"],
            "hac_standard_error": raw["hac_standard_error"],
            "hac_t": raw["hac_t"],
            "bootstrap_resamples": raw["bootstrap_resamples"],
            "centered_two_sided_p_value": raw[
                "centered_two_sided_p_value"
            ],
            "reasons": _report_cell_reasons(_summary_reasons(raw), status),
        })
    return rows


def _report_status(
    *, accepted_count: int, refused_reasons: Counter[str],
) -> tuple[str, list[str]]:
    refused_count = sum(refused_reasons.values())
    if refused_reasons.get("outcome_identity_invalid", 0):
        return "INVALID_DATA", ["outcome_identity_invalid"]
    if accepted_count and not refused_count:
        return "AVAILABLE", []
    if accepted_count:
        return "INCONCLUSIVE", ["named_refusal_in_report_cell"]
    if refused_count:
        return "INCONCLUSIVE", ["all_report_cell_observations_refused"]
    return "UNAVAILABLE", ["no_observation_in_report_cell"]


def _event_return_family_rows(
    *, observations: Sequence[_DirectionalEventReportObservation],
    source_view_id: str, report_contract: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    dimensions = report_contract["dimensions"]
    for slice_id, folds, fold_scopes in _report_slice_scopes(report_contract):
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            for action in dimensions["rating_actions"]:
                for horizon in dimensions["horizons_sessions"]:
                    for cohort_record in dimensions["cohorts"]:
                        cohort = cohort_record["cohort_id"]
                        selected = tuple(
                            item for item in observations
                            if item.source_view_id == source_view_id
                            and item.fold_id in selected_folds
                            and item.rating_action == action
                            and item.horizon_sessions == horizon
                            and (
                                cohort == "all"
                                or _earnings_cohort(
                                    item.earnings_anchor_signed_session_distance
                                ) == cohort
                            )
                        )
                        accepted = tuple(
                            item for item in selected
                            if item.gross_excess_total_return is not None
                        )
                        refused_reasons = Counter(
                            item.refusal_reason for item in selected
                            if item.refusal_reason is not None
                        )
                        component_values: dict[
                            str, tuple[Decimal, Decimal, Decimal]
                        ] = {}
                        by_component: dict[
                            str, list[_DirectionalEventReportObservation]
                        ] = defaultdict(list)
                        for item in accepted:
                            if item.common_event_component_id is None:
                                raise FormalCloudEvaluationError(
                                    "accepted directional event lacks a component"
                                )
                            by_component[item.common_event_component_id].append(item)
                        for component_id, component_rows in by_component.items():
                            gross_values = tuple(
                                item.gross_security_total_return
                                for item in component_rows
                            )
                            benchmark_values = tuple(
                                item.benchmark_total_return for item in component_rows
                            )
                            excess_values = tuple(
                                item.gross_excess_total_return
                                for item in component_rows
                            )
                            if any(item is None for item in (
                                *gross_values, *benchmark_values, *excess_values,
                            )):
                                raise FormalCloudEvaluationError(
                                    "accepted event-return component is incomplete"
                                )
                            component_values[component_id] = (
                                _evaluation._mean(gross_values),
                                _evaluation._mean(benchmark_values),
                                _evaluation._mean(excess_values),
                            )
                        status, reasons = _report_status(
                            accepted_count=len(accepted),
                            refused_reasons=refused_reasons,
                        )
                        gross_components = tuple(
                            value[0] for value in component_values.values()
                        )
                        benchmark_components = tuple(
                            value[1] for value in component_values.values()
                        )
                        excess_components = tuple(
                            value[2] for value in component_values.values()
                        )
                        dated: dict[int, list[Decimal]] = defaultdict(list)
                        for item in accepted:
                            assert item.gross_excess_total_return is not None
                            dated[item.session_position].append(
                                item.gross_excess_total_return
                            )
                        dated_means = tuple(
                            (position, _evaluation._mean(tuple(values)))
                            for position, values in sorted(dated.items())
                        )
                        hac_pairs, hac_se, hac_t = _evaluation._v2_hac(
                            dated_means, horizon
                        )
                        rows.append({
                            "source_view_id": source_view_id,
                            "slice_id": slice_id, "fold_id": fold_id,
                            "rating_action": action,
                            "horizon_sessions": horizon, "cohort_id": cohort,
                            "status": status,
                            "accepted_event_count": len(accepted),
                            "refused_event_count": sum(refused_reasons.values()),
                            "connected_component_count": len(component_values),
                            "mean_gross_security_total_return": (
                                None if not gross_components
                                else _evaluation._mean(gross_components)
                            ),
                            "mean_SPY_total_return": (
                                None if not benchmark_components
                                else _evaluation._mean(benchmark_components)
                            ),
                            "mean_gross_excess_total_return": (
                                None if not excess_components
                                else _evaluation._mean(excess_components)
                            ),
                            "median_gross_excess_total_return": (
                                None if not excess_components
                                else _evaluation._median(excess_components)
                            ),
                            "hac_lag_sessions": horizon,
                            "hac_pair_counts": list(hac_pairs),
                            "hac_standard_error": hac_se, "hac_t": hac_t,
                            "reasons": reasons,
                        })
    return rows


def _event_time_family_rows(
    *, observations: Sequence[_DirectionalEventReportObservation],
    source_view_id: str, report_contract: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    dimensions = report_contract["dimensions"]
    for slice_id, folds, fold_scopes in _report_slice_scopes(report_contract):
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            for action in dimensions["rating_actions"]:
                action_rows = tuple(
                    item for item in observations
                    if item.source_view_id == source_view_id
                    and item.fold_id in selected_folds
                    and item.rating_action == action
                )
                for event_time in dimensions["event_time_sessions"]:
                    if event_time == 0:
                        # One preoutcome terminal per directional event.  Use
                        # its lowest exact horizon only to deduplicate the four
                        # later outcome terminals; no outcome value is read.
                        by_event: dict[
                            tuple[str, str, str, int],
                            _DirectionalEventReportObservation,
                        ] = {}
                        for item in action_rows:
                            key = (
                                item.fold_id, item.event_id, item.security_id,
                                item.session_position,
                            )
                            prior = by_event.get(key)
                            if prior is None or item.horizon_sessions < prior.horizon_sessions:
                                by_event[key] = item
                        accepted_count = sum(
                            item.refusal_reason != "missing_preopen_control"
                            for item in by_event.values()
                        )
                        refused_reasons = Counter(
                            "missing_preopen_control"
                            for item in by_event.values()
                            if item.refusal_reason == "missing_preopen_control"
                        )
                        security_values = benchmark_values = excess_values = (
                            Decimal(0),
                        ) if accepted_count else ()
                    else:
                        selected = tuple(
                            item for item in action_rows
                            if item.horizon_sessions == event_time
                        )
                        accepted = tuple(
                            item for item in selected
                            if item.gross_excess_total_return is not None
                        )
                        accepted_count = len(accepted)
                        refused_reasons = Counter(
                            item.refusal_reason for item in selected
                            if item.refusal_reason is not None
                        )
                        security_values = tuple(
                            item.gross_security_total_return for item in accepted
                        )
                        benchmark_values = tuple(
                            item.benchmark_total_return for item in accepted
                        )
                        excess_values = tuple(
                            item.gross_excess_total_return for item in accepted
                        )
                    status, reasons = _report_status(
                        accepted_count=accepted_count,
                        refused_reasons=refused_reasons,
                    )
                    rows.append({
                        "source_view_id": source_view_id,
                        "slice_id": slice_id, "fold_id": fold_id,
                        "rating_action": action,
                        "event_time_session": event_time,
                        "status": status,
                        "accepted_event_count": accepted_count,
                        "refused_event_count": sum(refused_reasons.values()),
                        "mean_security_total_return": (
                            None if not security_values
                            else _evaluation._mean(security_values)
                        ),
                        "mean_SPY_total_return": (
                            None if not benchmark_values
                            else _evaluation._mean(benchmark_values)
                        ),
                        "mean_cumulative_abnormal_return": (
                            None if not excess_values
                            else _evaluation._mean(excess_values)
                        ),
                        "reasons": reasons,
                    })
    return rows


def _percentile_decile_assignments(
    values: Sequence[_DecisionReportObservation], *, arm: str,
) -> dict[int, list[_DecisionReportObservation]]:
    score_name = "firm_specific_score" if arm == "firm_specific" else "global_score"
    scored = tuple(item for item in values if getattr(item, score_name) is not None)
    ordered = sorted(
        scored, key=lambda item: (getattr(item, score_name), item.security_id)
    )
    bins: dict[int, list[_DecisionReportObservation]] = {
        value: [] for value in range(1, 11)
    }
    index = 0
    while index < len(ordered):
        end = index + 1
        score = getattr(ordered[index], score_name)
        while end < len(ordered) and getattr(ordered[end], score_name) == score:
            end += 1
        average_rank = Fraction((index + 1) + end, 2)
        decile = min(10, 1 + int(
            Fraction(10, 1) * (average_rank - 1) / len(ordered)
        ))
        bins[decile].extend(ordered[index:end])
        index = end
    return bins


def _percentile_family_rows(
    *, observations: Sequence[_DecisionReportObservation],
    source_view_id: str, report_contract: Mapping[str, object],
) -> list[dict[str, object]]:
    dimensions = report_contract["dimensions"]
    by_date: dict[
        tuple[str, int, int], list[_DecisionReportObservation]
    ] = defaultdict(list)
    for item in observations:
        if item.source_view_id == source_view_id:
            by_date[(
                item.fold_id, item.session_position, item.horizon_sessions
            )].append(item)
    rows: list[dict[str, object]] = []
    for slice_id, folds, fold_scopes in _report_slice_scopes(report_contract):
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            for horizon in dimensions["horizons_sessions"]:
                for arm in dimensions["score_arm_ids"]:
                    bins: dict[int, list[_DecisionReportObservation]] = {
                        value: [] for value in dimensions["percentile_bins"]
                    }
                    for (fold, _position, candidate_horizon), values in by_date.items():
                        if fold in selected_folds and candidate_horizon == horizon:
                            assigned = _percentile_decile_assignments(
                                values, arm=arm
                            )
                            for decile, selected in assigned.items():
                                bins[decile].extend(selected)
                    score_name = (
                        "firm_specific_score" if arm == "firm_specific"
                        else "global_score"
                    )
                    for decile in dimensions["percentile_bins"]:
                        assigned = bins[decile]
                        accepted = tuple(
                            item for item in assigned
                            if item.gross_excess_total_return is not None
                        )
                        refused_reasons = Counter(
                            item.refusal_reason for item in assigned
                            if item.refusal_reason is not None
                        )
                        status, reasons = _report_status(
                            accepted_count=len(accepted),
                            refused_reasons=refused_reasons,
                        )
                        scores = tuple(
                            getattr(item, score_name) for item in accepted
                        )
                        outcomes = tuple(
                            item.gross_excess_total_return for item in accepted
                        )
                        rows.append({
                            "source_view_id": source_view_id,
                            "slice_id": slice_id, "fold_id": fold_id,
                            "horizon_sessions": horizon, "score_arm": arm,
                            "percentile_decile": decile, "status": status,
                            "row_count": len(accepted),
                            "mean_score": (
                                None if not scores else _evaluation._mean(scores)
                            ),
                            "mean_future_gross_excess_return": (
                                None if not outcomes
                                else _evaluation._mean(outcomes)
                            ),
                            "median_future_gross_excess_return": (
                                None if not outcomes
                                else _evaluation._median(outcomes)
                            ),
                            "reasons": reasons,
                        })
    return rows


def _signal_decay_family_rows(
    *, observations: Sequence[_DecisionReportObservation],
    source_view_id: str, report_contract: Mapping[str, object],
) -> list[dict[str, object]]:
    dimensions = report_contract["dimensions"]
    rows: list[dict[str, object]] = []
    for slice_id, folds, fold_scopes in _report_slice_scopes(report_contract):
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            cells: dict[tuple[str, str, int], dict[str, object]] = {}
            for action in dimensions["rating_actions"]:
                for arm in dimensions["score_arm_ids"]:
                    score_name = (
                        "firm_specific_score" if arm == "firm_specific"
                        else "global_score"
                    )
                    for horizon in dimensions["horizons_sessions"]:
                        selected = tuple(
                            item for item in observations
                            if item.source_view_id == source_view_id
                            and item.fold_id in selected_folds
                            and item.horizon_sessions == horizon
                            and action in item.rating_actions
                        )
                        by_date: dict[int, list[_DecisionReportObservation]] = (
                            defaultdict(list)
                        )
                        for item in selected:
                            by_date[item.session_position].append(item)
                        date_ics: list[Decimal] = []
                        outcomes: list[Decimal] = []
                        invalid = 0
                        for date_rows in by_date.values():
                            valid = tuple(
                                item for item in date_rows
                                if getattr(item, score_name) is not None
                                and item.gross_excess_total_return is not None
                            )
                            if len(valid) < 2 or len(valid) != len(date_rows):
                                invalid += 1
                                continue
                            try:
                                date_ics.append(_evaluation._spearman(
                                    tuple(getattr(item, score_name) for item in valid),
                                    tuple(
                                        item.gross_excess_total_return
                                        for item in valid
                                    ),
                                ))
                            except (TypeError, ValueError):
                                invalid += 1
                                continue
                            outcomes.extend(
                                item.gross_excess_total_return for item in valid
                            )
                        mean_ic = (
                            None if not date_ics
                            else _evaluation._mean(tuple(date_ics))
                        )
                        mean_excess = (
                            None if not outcomes
                            else _evaluation._mean(tuple(outcomes))
                        )
                        cells[(action, arm, horizon)] = {
                            "valid_date_count": len(date_ics),
                            "mean_ic": mean_ic, "mean_excess": mean_excess,
                            "invalid": invalid,
                        }
            for action in dimensions["rating_actions"]:
                for arm in dimensions["score_arm_ids"]:
                    h1 = cells[(action, arm, 1)]["mean_excess"]
                    for horizon in dimensions["horizons_sessions"]:
                        cell = cells[(action, arm, horizon)]
                        available = (
                            cell["valid_date_count"] >= 50
                            and cell["mean_ic"] is not None
                            and cell["mean_excess"] is not None
                        )
                        ratio: Decimal | None = None
                        if available and h1 not in (None, Decimal(0)):
                            with localcontext(_evaluation._context()):
                                ratio = +(cell["mean_excess"] / h1)
                        status = "AVAILABLE" if available and ratio is not None else (
                            "INCONCLUSIVE" if cell["valid_date_count"] else "UNAVAILABLE"
                        )
                        rows.append({
                            "source_view_id": source_view_id,
                            "slice_id": slice_id, "fold_id": fold_id,
                            "rating_action": action, "score_arm": arm,
                            "horizon_sessions": horizon, "status": status,
                            "valid_date_count": cell["valid_date_count"],
                            "mean_ic": cell["mean_ic"],
                            "mean_gross_excess_return": cell["mean_excess"],
                            "ratio_to_h1_effect": ratio,
                            "reasons": [] if status == "AVAILABLE" else [
                                "signal_decay_valid_date_or_h1_effect_unavailable"
                            ],
                        })
    return rows


def _paired_coverage_family_rows(
    report: Mapping[str, object], view: str,
    coverages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for coverage in coverages:
        if coverage["source_view_id"] != view:
            continue
        fold_id = coverage["fold_ids"][0] if len(coverage["fold_ids"]) == 1 else "POOLED"
        diagnostic_counts = {
            "endpoint_status_counts": coverage["endpoint_status_counts"],
            "endpoint_pair_status_counts": coverage[
                "endpoint_pair_status_counts"
            ],
            "direction_status_counts": coverage["direction_status_counts"],
            "date_diagnostic_counts": coverage["date_diagnostic_counts"],
            "raw_form_collision_counts": coverage[
                "raw_form_collision_counts"
            ],
        }
        for ledger in coverage["ledgers"]:
            status = _report_cell_status(ledger["disposition"])
            rows.append({
                "source_view_id": view,
                "slice_id": _evaluation.FORMAL_SLICE_ID,
                "fold_id": fold_id,
                "record_kind": "preoutcome_coverage_ledger",
                "record_id": ledger["ledger_id"],
                "status": status,
                "numerator": ledger["numerator"],
                "denominator": ledger["denominator"],
                "passes_19_of_20": ledger["passes"],
                "valid_date_count": None,
                "mean_firm_ic": None,
                "mean_global_ic": None,
                "observed_difference": None,
                "one_sided_q95": None,
                "one_sided_lcb95": None,
                "diagnostic_counts": diagnostic_counts,
                "reasons": _report_cell_reasons(ledger["reasons"], status),
            })
    for raw in report["paired_ic_summaries"]:
        status = _report_cell_status(raw["status"])
        record_id = (
            f"{raw['slice_id']}:{_scope_fold(raw['fold_id'])}:"
            f"h{raw['horizon_sessions']}"
        )
        rows.append({
            "source_view_id": view,
            "slice_id": raw["slice_id"],
            "fold_id": _scope_fold(raw["fold_id"]),
            "record_kind": "paired_information_coefficient",
            "record_id": record_id,
            "status": status,
            "numerator": None,
            "denominator": None,
            "passes_19_of_20": None,
            "valid_date_count": raw["valid_date_count"],
            "mean_firm_ic": raw["mean_firm_ic"],
            "mean_global_ic": raw["mean_global_ic"],
            "observed_difference": raw["observed_difference"],
            "one_sided_q95": raw["one_sided_q95"],
            "one_sided_lcb95": raw["one_sided_lcb95"],
            "diagnostic_counts": {
                "invalid_date_count": raw["invalid_date_count"],
                "invalid_dates_by_reason": raw["invalid_dates_by_reason"],
            },
            "reasons": _report_cell_reasons(_summary_reasons(raw), status),
        })
    return rows


def _economic_family_rows(
    report: Mapping[str, object], view: str,
    trials: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    summaries = {
        (raw["slice_id"], raw["cost_bps_per_side"]): raw
        for raw in report["economic_summaries"]
    }
    rows: list[dict[str, object]] = []
    for slice_id in (_evaluation.FORMAL_SLICE_ID, _evaluation.DESCRIPTIVE_SLICE_ID):
        for trial in trials:
            equal_weight = trial["portfolio_variant_id"] == "direct_stock_equal_weight"
            # Only equal-weight is computed by the authenticated economic
            # evaluator today.  A trial sharing its 10-bps cost is not its
            # result parent: inverse-volatility and score-weight rows stay
            # wholly unavailable until their own typed inputs/computation
            # exist.
            raw = (
                summaries.get((slice_id, trial["cost_bps_per_side"]))
                if equal_weight else None
            )
            reasons = (
                _summary_reasons(raw) if raw is not None else []
            )
            reasons.append(
                "gross_benchmark_overlap_and_variant_series_not_retained"
                if equal_weight
                else "portfolio_variant_sufficient_statistics_not_retained"
            )
            rows.append({
                "source_view_id": view,
                "slice_id": slice_id,
                "fold_id": "POOLED",
                "trial_id": trial["trial_id"],
                "status": "UNAVAILABLE",
                "portfolio_variant_id": (
                    trial["portfolio_variant_id"] if equal_weight else None
                ),
                "cost_bps_per_side": (
                    trial["cost_bps_per_side"] if equal_weight else None
                ),
                "session_count": None if raw is None else raw["session_count"],
                "valid_return_session_count": None if raw is None else raw["valid_return_session_count"],
                "refused_return_session_count": None if raw is None else raw["refused_return_session_count"],
                "invested_session_count": None if raw is None else raw["invested_session_count"],
                "cash_sleeve_count": None if raw is None else raw["cash_sleeve_count"],
                "selected_sleeve_count": None if raw is None else raw["selected_sleeve_count"],
                "mean_gross_portfolio_total_return": None,
                "mean_SPY_total_return": None,
                "mean_net_portfolio_total_return": None,
                "mean_net_excess_daily_total_return": None if raw is None else raw["mean_net_excess_daily_return"],
                "cumulative_net_portfolio_total_return": None if raw is None else raw["cumulative_net_total_return"],
                "cumulative_SPY_total_return": None,
                "geometric_relative_total_return": None,
                "mean_daily_turnover": None if raw is None else raw["mean_daily_turnover"],
                "terminal_liquidation_turnover": None if raw is None else raw["terminal_liquidation_turnover"],
                "sleeve_security_incidence_count": None,
                "duplicate_sleeve_security_incidence_count": None,
                "sleeve_overlap_share": None,
                "hac_lag_sessions": 20,
                "hac_pair_counts": [],
                "bootstrap_resamples": None if raw is None else raw["bootstrap_resamples"],
                "centered_two_sided_p_value": None if raw is None else raw["centered_two_sided_p_value"],
                "reasons": [
                    "required_economic_sufficient_statistics_unavailable"
                ],
            })
    return rows


def _accounting_family_rows(
    *, view: str, report_contract: Mapping[str, object],
    coverages: Sequence[Mapping[str, object]],
    fold_axes: Sequence[_evaluation.FoldSessionAxis],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
    power_floor: _evaluation.PowerFloorBinding,
    partition_counts: Counter[object], terminal_attribution: Counter[object],
    family_rows: Mapping[str, Sequence[Mapping[str, object]]],
    trial_censuses: Mapping[tuple[str, str], _ReportTrialFoldCensus],
) -> list[dict[str, object]]:
    """Emit the exact F6 accounting axis from independent authenticated parents."""

    axis = report_contract["dimensions"].get("f6_accounting_axis")
    expected_axis_kinds = (
        "preoutcome_decision_terminal", "horizon_outcome_terminal",
        "economic_trial_terminal", "lifecycle_terminal_disposition",
        "global_comparator_coverage_ledger", "report_family_terminal",
        "power_floor",
    )
    if (
        type(axis) is not list
        or tuple(item.get("accounting_kind") for item in axis)
        != expected_axis_kinds
        or report_contract["dimensions"].get("f6_accounting_equality")
        != (
            "expected_count_equals_terminal_count_equals_accepted_count_plus_"
            "refused_count_for_every_exact_F6_key"
        )
    ):
        raise FormalCloudEvaluationError("F6 accounting authority changed")
    reasons_by_kind: dict[str, tuple[str, ...]] = {}
    trial_ids = tuple(
        item["trial_id"] for item in report_contract["strategy_trial_registry"][
            "ordered_trials"
        ]
    )
    for item in axis:
        reasons = item["reason_or_component_ids"]
        if reasons == "exact_six_strategy_trial_registry_ids":
            reasons = trial_ids
        if type(reasons) is not list and type(reasons) is not tuple:
            raise FormalCloudEvaluationError("F6 accounting reason axis changed")
        reasons_by_kind[item["accounting_kind"]] = tuple(reasons)

    # Freeze the complete F6 key grid before constructing a single F6 value.
    # Its own report-family terminal is included in this independent fixed
    # grid, so an emitted/truncated row list can never define its denominator.
    scopes = _report_slice_scopes(report_contract)
    expected_base_keys: list[tuple[str, str, str, str]] = []

    def expect_key(
        slice_id: str, fold_id: str, accounting_kind: str,
        reason_or_component: str,
    ) -> None:
        key = (slice_id, fold_id, accounting_kind, reason_or_component)
        if key in expected_base_keys:
            raise FormalCloudEvaluationError("F6 expected key was duplicated")
        expected_base_keys.append(key)

    for slice_id, slice_folds, fold_scopes in scopes:
        for fold_id in fold_scopes:
            expect_key(
                slice_id, fold_id, "preoutcome_decision_terminal", "all"
            )
            for horizon in HORIZONS:
                expect_key(
                    slice_id, fold_id, "horizon_outcome_terminal",
                    f"h{horizon}",
                )
            for trial_id in trial_ids:
                expect_key(
                    slice_id, fold_id, "economic_trial_terminal", trial_id
                )
            selected_folds = (
                slice_folds if fold_id == "POOLED" else (fold_id,)
            )
            if sum(
                terminal_attribution[(fold, "terminal")]
                for fold in selected_folds
            ):
                expect_key(
                    slice_id, fold_id,
                    "lifecycle_terminal_disposition", "all",
                )
    for fold_id in (*FORMAL_FOLD_IDS, "POOLED"):
        for ledger_id in GLOBAL_COMPARATOR_LEDGER_IDS:
            expect_key(
                _evaluation.FORMAL_SLICE_ID, fold_id,
                "global_comparator_coverage_ledger", ledger_id,
            )
    for reason in reasons_by_kind["power_floor"]:
        expect_key(
            _evaluation.FORMAL_SLICE_ID, "POOLED", "power_floor", reason
        )

    expected_by_family: dict[str, tuple[dict[str, object], ...]] = {}
    report_terminal_scopes: dict[str, tuple[tuple[str, str], ...]] = {}
    for family_id in REPORT_FAMILY_IDS:
        if family_id == REPORT_FAMILY_IDS[6]:
            continue
        expected_keys = _expected_report_family_key_rows(
            family_id=family_id, source_view_id=view,
            report_contract=report_contract, fold_axes=fold_axes,
            economic_axes=economic_axes,
        )
        expected_by_family[family_id] = expected_keys
        report_terminal_scopes[family_id] = tuple(dict.fromkeys(
            (item["slice_id"], item["fold_id"]) for item in expected_keys
        ))
    f6_scopes = tuple(dict.fromkeys((
        *((item[0], item[1]) for item in expected_base_keys),
        *(
            scope
            for family_id in REPORT_FAMILY_IDS
            if family_id != REPORT_FAMILY_IDS[6]
            for scope in report_terminal_scopes[family_id]
        ),
    )))
    report_terminal_scopes[REPORT_FAMILY_IDS[6]] = f6_scopes
    expected_f6_keys = tuple((
        *expected_base_keys,
        *(
            (slice_id, fold_id, "report_family_terminal", family_id)
            for family_id in REPORT_FAMILY_IDS
            for slice_id, fold_id in report_terminal_scopes[family_id]
        ),
    ))
    if len(set(expected_f6_keys)) != len(expected_f6_keys):
        raise FormalCloudEvaluationError("F6 complete expected key grid duplicated")
    expected_f6_scope_counts = Counter(
        (slice_id, fold_id)
        for slice_id, fold_id, _kind, _reason in expected_f6_keys
    )

    rows: list[dict[str, object]] = []

    def add(
        *, slice_id: str, fold_id: str, accounting_kind: str,
        reason_or_component: str, expected: int, accepted: int, refused: int,
        terminal: int, connected_components: int | None = None,
        component_incidence: int | None = None,
        required_power_floor: int | None = None,
    ) -> None:
        if (
            accounting_kind not in reasons_by_kind
            or reason_or_component not in reasons_by_kind[accounting_kind]
            or any(
                type(value) is not int or value < 0
                for value in (expected, accepted, refused, terminal)
            )
            or expected != terminal or expected != accepted + refused
            or connected_components is not None
            and (type(connected_components) is not int or connected_components < 0)
            or component_incidence is not None
            and (type(component_incidence) is not int or component_incidence < 0)
            or required_power_floor is not None
            and (type(required_power_floor) is not int or required_power_floor < 0)
        ):
            raise FormalCloudEvaluationError(
                "F6 accounting row does not reconcile exactly"
            )
        rows.append({
            "source_view_id": view, "slice_id": slice_id,
            "fold_id": fold_id, "accounting_kind": accounting_kind,
            "reason_or_component": reason_or_component,
            "status": "AVAILABLE", "expected_count": expected,
            "accepted_count": accepted, "refused_count": refused,
            "terminal_count": terminal,
            "connected_component_count": connected_components,
            "component_member_incidence_count": component_incidence,
            "power_floor": required_power_floor,
            "reconciles_exactly": True, "reasons": [],
        })

    fold_horizon = {
        (fold, horizon): (accepted, refused)
        for fold, horizon, accepted, refused in result.fold_horizon_census
    }
    if tuple(fold_horizon) != tuple(
        (fold, horizon) for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    ):
        raise FormalCloudEvaluationError("F6 fold/horizon parent census changed")
    economic_axis_counts = {
        item.fold_id: len(item.sessions) for item in economic_axes
    }
    if tuple(economic_axis_counts) != FORMAL_FOLD_IDS:
        raise FormalCloudEvaluationError("F6 economic axis changed")

    coverage_by_scope: dict[str, Mapping[str, object]] = {}
    for coverage in coverages:
        if coverage["source_view_id"] != view:
            continue
        fold_id = (
            coverage["fold_ids"][0]
            if len(coverage["fold_ids"]) == 1 else "POOLED"
        )
        if fold_id in coverage_by_scope:
            raise FormalCloudEvaluationError("F6 coverage parent duplicated")
        coverage_by_scope[fold_id] = coverage
    if tuple(coverage_by_scope) != (*FORMAL_FOLD_IDS, "POOLED"):
        raise FormalCloudEvaluationError("F6 coverage parent census changed")

    # Pre-outcome decisions and every horizon outcome have distinct terminal
    # domains.  Pooling is exact integer addition over the declared slice.
    for slice_id, slice_folds, fold_scopes in scopes:
        for fold_id in fold_scopes:
            selected_folds = slice_folds if fold_id == "POOLED" else (fold_id,)
            expected = sum(
                partition_counts[(fold, "decision")] for fold in selected_folds
            )
            accepted = sum(
                partition_counts[(fold, "scored")] for fold in selected_folds
            )
            refused = sum(
                partition_counts[(fold, "refused")] for fold in selected_folds
            )
            add(
                slice_id=slice_id, fold_id=fold_id,
                accounting_kind="preoutcome_decision_terminal",
                reason_or_component="all", expected=expected,
                accepted=accepted, refused=refused, terminal=expected,
            )
            for horizon in HORIZONS:
                expected = sum(
                    partition_counts[(fold, horizon, "decision")]
                    for fold in selected_folds
                )
                preoutcome_accepted = sum(
                    partition_counts[(fold, horizon, "scored")]
                    for fold in selected_folds
                )
                preoutcome_refused = sum(
                    partition_counts[(fold, horizon, "refused")]
                    for fold in selected_folds
                )
                accepted = sum(
                    fold_horizon[(fold, horizon)][0] for fold in selected_folds
                )
                refused = sum(
                    fold_horizon[(fold, horizon)][1] for fold in selected_folds
                )
                if (
                    preoutcome_accepted + preoutcome_refused != expected
                    or accepted + refused != expected
                ):
                    raise FormalCloudEvaluationError(
                        "F6 horizon terminals diverged from their preoutcome axis"
                    )
                add(
                    slice_id=slice_id, fold_id=fold_id,
                    accounting_kind="horizon_outcome_terminal",
                    reason_or_component=f"h{horizon}",
                    expected=expected, accepted=accepted,
                    refused=refused, terminal=expected,
                )
            for trial in report_contract["strategy_trial_registry"][
                "ordered_trials"
            ]:
                trial_id = trial["trial_id"]
                expected = sum(
                    economic_axis_counts[fold] for fold in selected_folds
                )
                accepted = sum(
                    trial_censuses[(trial_id, fold)].valid_return_session_count
                    for fold in selected_folds
                )
                refused = sum(
                    trial_censuses[(trial_id, fold)].refused_return_session_count
                    for fold in selected_folds
                )
                add(
                    slice_id=slice_id, fold_id=fold_id,
                    accounting_kind="economic_trial_terminal",
                    reason_or_component=trial_id, expected=expected,
                    accepted=accepted, refused=refused, terminal=expected,
                )
            lifecycle_terminal = sum(
                terminal_attribution[(fold, "terminal")]
                for fold in selected_folds
            )
            if lifecycle_terminal:
                lifecycle_accepted = sum(
                    terminal_attribution[(fold, "terminal_payoff")]
                    + terminal_attribution[(
                        fold, "benchmark_splice_continuation"
                    )]
                    for fold in selected_folds
                )
                lifecycle_refused = sum(
                    terminal_attribution[(fold, "named_terminal_refusal")]
                    for fold in selected_folds
                )
                add(
                    slice_id=slice_id, fold_id=fold_id,
                    accounting_kind="lifecycle_terminal_disposition",
                    reason_or_component="all", expected=lifecycle_terminal,
                    accepted=lifecycle_accepted, refused=lifecycle_refused,
                    terminal=lifecycle_terminal,
                )

    for fold_id in (*FORMAL_FOLD_IDS, "POOLED"):
        coverage = coverage_by_scope[fold_id]
        ledgers = {item["ledger_id"]: item for item in coverage["ledgers"]}
        if tuple(ledgers) != GLOBAL_COMPARATOR_LEDGER_IDS:
            raise FormalCloudEvaluationError("F6 coverage ledger order changed")
        for ledger_id in GLOBAL_COMPARATOR_LEDGER_IDS:
            ledger = ledgers[ledger_id]
            expected = ledger["denominator"]
            accepted = ledger["numerator"]
            add(
                slice_id=_evaluation.FORMAL_SLICE_ID, fold_id=fold_id,
                accounting_kind="global_comparator_coverage_ledger",
                reason_or_component=ledger_id, expected=expected,
                accepted=accepted, refused=expected - accepted,
                terminal=expected,
                connected_components=(
                    accepted if ledger_id == "common_event_components" else None
                ),
                component_incidence=(
                    accepted
                    if ledger_id == "component_member_incidence" else None
                ),
            )

    add(
        slice_id=_evaluation.FORMAL_SLICE_ID, fold_id="POOLED",
        accounting_kind="power_floor",
        reason_or_component="valid_h20_fm_dates",
        expected=power_floor.h20_test_session_capacity,
        accepted=power_floor.valid_h20_test_session_count,
        refused=(
            power_floor.refused_h20_test_session_count
            + power_floor.missing_h20_test_session_count
        ),
        terminal=power_floor.h20_test_session_capacity,
        required_power_floor=power_floor.required_valid_dates,
    )
    add(
        slice_id=_evaluation.FORMAL_SLICE_ID, fold_id="POOLED",
        accounting_kind="power_floor",
        reason_or_component="connected_h20_components",
        expected=power_floor.connected_component_instance_count,
        accepted=power_floor.connected_component_instance_count,
        refused=0,
        terminal=power_floor.connected_component_instance_count,
        connected_components=power_floor.connected_component_instance_count,
        required_power_floor=power_floor.required_connected_components,
    )

    actual_scope_counts: dict[
        tuple[str, str, str], Counter[str]
    ] = {}
    for family_id in REPORT_FAMILY_IDS:
        if family_id == REPORT_FAMILY_IDS[6]:
            continue
        expected_keys = expected_by_family[family_id]
        schema = next(
            item for item in report_contract["report_schemas"]
            if item["family_id"] == family_id
        )
        key_fields = tuple(schema["ordered_key_fields"])
        actual = tuple(family_rows[family_id])
        expected_key_tuples = {
            tuple(item[name] for name in key_fields) for item in expected_keys
        }
        actual_key_tuples = {
            tuple(item[name] for name in key_fields) for item in actual
        }
        if (
            len(expected_key_tuples) != len(expected_keys)
            or len(actual_key_tuples) != len(actual)
            or actual_key_tuples != expected_key_tuples
        ):
            raise FormalCloudEvaluationError(
                "report family differs from its independent expected key grid"
            )
        for item in actual:
            scope_key = (family_id, item["slice_id"], item["fold_id"])
            counts = actual_scope_counts.setdefault(scope_key, Counter())
            counts["terminal"] += 1
            counts[
                "accepted" if item["status"] == "AVAILABLE" else "refused"
            ] += 1
    for family_id in REPORT_FAMILY_IDS:
        for slice_id, fold_id in report_terminal_scopes[family_id]:
            if family_id == REPORT_FAMILY_IDS[6]:
                expected = expected_f6_scope_counts[(slice_id, fold_id)]
                accepted, refused = expected, 0
            else:
                expected = sum(
                    item["slice_id"] == slice_id and item["fold_id"] == fold_id
                    for item in expected_by_family[family_id]
                )
                counts = actual_scope_counts[(family_id, slice_id, fold_id)]
                accepted, refused = counts["accepted"], counts["refused"]
                if counts["terminal"] != expected:
                    raise FormalCloudEvaluationError(
                        "report-family terminal census changed"
                    )
            add(
                slice_id=slice_id, fold_id=fold_id,
                accounting_kind="report_family_terminal",
                reason_or_component=family_id, expected=expected,
                accepted=accepted, refused=refused, terminal=expected,
            )
    actual_f6_keys = tuple(
        (
            item["slice_id"], item["fold_id"], item["accounting_kind"],
            item["reason_or_component"],
        )
        for item in rows
    )
    if set(actual_f6_keys) != set(expected_f6_keys) or len(
        actual_f6_keys
    ) != len(expected_f6_keys):
        raise FormalCloudEvaluationError(
            "F6 emitted key grid differs from its predeclared authority"
        )
    return rows


def _unavailable_report_row(
    schema: Mapping[str, object], **key_values: object,
) -> dict[str, object]:
    keys = tuple(schema["ordered_key_fields"])
    values = tuple(schema["ordered_value_fields"])
    if set(key_values) != set(keys):
        raise FormalCloudEvaluationError(
            "unavailable report cell key dimensions changed"
        )
    row = {name: key_values[name] for name in keys}
    row.update({name: None for name in values})
    row["status"] = "UNAVAILABLE"
    row["reasons"] = [
        "required_sufficient_statistics_not_retained"
    ]
    return row


def _report_slice_scopes(
    report_contract: Mapping[str, object],
) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    slices = report_contract["dimensions"]["slices"]
    result = tuple(
        (
            item["slice_id"], tuple(item["fold_ids"]),
            tuple(item["report_fold_scope_ids"]),
        )
        for item in slices
    )
    if result != (
        (
            _evaluation.FORMAL_SLICE_ID, FORMAL_FOLD_IDS,
            (*FORMAL_FOLD_IDS, "POOLED"),
        ),
        (
            _evaluation.DESCRIPTIVE_SLICE_ID, DESCRIPTIVE_FOLD_IDS,
            (*DESCRIPTIVE_FOLD_IDS, "POOLED"),
        ),
    ):
        raise FormalCloudEvaluationError("report slice geometry changed")
    return result


def _expected_report_family_key_rows(
    *, family_id: str, source_view_id: str,
    report_contract: Mapping[str, object],
    fold_axes: Sequence[_evaluation.FoldSessionAxis],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
) -> tuple[dict[str, object], ...]:
    """Build a report family's complete key grid from pre-outcome authority.

    This deliberately does not inspect emitted rows.  F6 uses the result as
    its report-slot denominator, including empty/unavailable cells.
    """

    schemas = {
        item["family_id"]: item for item in report_contract["report_schemas"]
    }
    schema = schemas[family_id]
    key_fields = tuple(schema["ordered_key_fields"])

    def keys(row: Mapping[str, object]) -> dict[str, object]:
        return {name: row[name] for name in key_fields}

    if family_id in {
        REPORT_FAMILY_IDS[0], REPORT_FAMILY_IDS[1], REPORT_FAMILY_IDS[7],
        REPORT_FAMILY_IDS[8], REPORT_FAMILY_IDS[9], REPORT_FAMILY_IDS[10],
        REPORT_FAMILY_IDS[11], REPORT_FAMILY_IDS[12],
    }:
        return tuple(keys(row) for row in _unavailable_family_rows(
            family_id=family_id, schema=schema,
            source_view_id=source_view_id, report_contract=report_contract,
            fold_axes=fold_axes, economic_axes=economic_axes,
        ))
    rows: list[dict[str, object]] = []
    scopes = _report_slice_scopes(report_contract)
    if family_id == REPORT_FAMILY_IDS[2]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for horizon in report_contract["dimensions"]["horizons_sessions"]:
                    for arm in report_contract["dimensions"]["score_arm_ids"]:
                        rows.append(keys({
                            "source_view_id": source_view_id,
                            "slice_id": slice_id, "fold_id": fold_id,
                            "horizon_sessions": horizon, "score_arm": arm,
                        }))
    elif family_id == REPORT_FAMILY_IDS[3]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for horizon in report_contract["dimensions"]["horizons_sessions"]:
                    for coefficient in report_contract["dimensions"][
                        "fama_macbeth_coefficient_ids"
                    ]:
                        rows.append(keys({
                            "source_view_id": source_view_id,
                            "slice_id": slice_id, "fold_id": fold_id,
                            "horizon_sessions": horizon,
                            "coefficient": coefficient,
                        }))
    elif family_id == REPORT_FAMILY_IDS[4]:
        for fold_id in (*FORMAL_FOLD_IDS, "POOLED"):
            for ledger_id in GLOBAL_COMPARATOR_LEDGER_IDS:
                rows.append(keys({
                    "source_view_id": source_view_id,
                    "slice_id": _evaluation.FORMAL_SLICE_ID,
                    "fold_id": fold_id,
                    "record_kind": "preoutcome_coverage_ledger",
                    "record_id": ledger_id,
                }))
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for horizon in report_contract["dimensions"]["horizons_sessions"]:
                    rows.append(keys({
                        "source_view_id": source_view_id,
                        "slice_id": slice_id, "fold_id": fold_id,
                        "record_kind": "paired_information_coefficient",
                        "record_id": f"{slice_id}:{fold_id}:h{horizon}",
                    }))
    elif family_id == REPORT_FAMILY_IDS[5]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for trial in report_contract["strategy_trial_registry"][
                    "ordered_trials"
                ]:
                    rows.append(keys({
                        "source_view_id": source_view_id,
                        "slice_id": slice_id, "fold_id": fold_id,
                        "trial_id": trial["trial_id"],
                    }))
    else:
        raise FormalCloudEvaluationError(
            "report family lacks an independent expected key grid"
        )
    return tuple(rows)


def _unavailable_family_rows(
    *, family_id: str, schema: Mapping[str, object], source_view_id: str,
    report_contract: Mapping[str, object],
    fold_axes: Sequence[_evaluation.FoldSessionAxis],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
) -> list[dict[str, object]]:
    dimensions = report_contract["dimensions"]
    scopes = _report_slice_scopes(report_contract)
    rows: list[dict[str, object]] = []

    def add(**keys: object) -> None:
        rows.append(_unavailable_report_row(schema, **keys))

    if family_id == REPORT_FAMILY_IDS[0]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for action in dimensions["rating_actions"]:
                    for horizon in dimensions["horizons_sessions"]:
                        for cohort in dimensions["cohorts"]:
                            add(
                                source_view_id=source_view_id, slice_id=slice_id,
                                fold_id=fold_id, rating_action=action,
                                horizon_sessions=horizon,
                                cohort_id=cohort["cohort_id"],
                            )
    elif family_id == REPORT_FAMILY_IDS[1]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for action in dimensions["rating_actions"]:
                    for event_time in dimensions["event_time_sessions"]:
                        add(
                            source_view_id=source_view_id, slice_id=slice_id,
                            fold_id=fold_id, rating_action=action,
                            event_time_session=event_time,
                        )
    elif family_id == REPORT_FAMILY_IDS[7]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for horizon in dimensions["horizons_sessions"]:
                    for arm in dimensions["score_arm_ids"]:
                        for percentile in dimensions["percentile_bins"]:
                            add(
                                source_view_id=source_view_id, slice_id=slice_id,
                                fold_id=fold_id, horizon_sessions=horizon,
                                score_arm=arm, percentile_decile=percentile,
                            )
    elif family_id == REPORT_FAMILY_IDS[8]:
        h20 = {
            axis.fold_id: axis.sessions for axis in fold_axes
            if axis.horizon_sessions == 20
        }
        for slice_id, folds, _fold_scopes in scopes:
            points = sorted(
                (point for fold in folds for point in h20[fold]),
                key=lambda item: item.session_position,
            )
            for point in points:
                for series_id in dimensions["rolling_series_ids"]:
                    add(
                        source_view_id=source_view_id, slice_id=slice_id,
                        fold_id="POOLED",
                        window_end_session=point.session.isoformat(),
                        series_id=series_id,
                    )
    elif family_id == REPORT_FAMILY_IDS[9]:
        for slice_id, folds, fold_scopes in scopes:
            years = tuple(int(fold.rsplit("-", 1)[1]) for fold in folds)
            for fold_id in fold_scopes:
                selected = years if fold_id == "POOLED" else (
                    int(fold_id.rsplit("-", 1)[1]),
                )
                for year in selected:
                    add(
                        source_view_id=source_view_id, slice_id=slice_id,
                        fold_id=fold_id, calendar_year=year,
                    )
    elif family_id == REPORT_FAMILY_IDS[10]:
        for slice_id, _folds, fold_scopes in scopes:
            for fold_id in fold_scopes:
                for action in dimensions["rating_actions"]:
                    for arm in dimensions["score_arm_ids"]:
                        for horizon in dimensions["horizons_sessions"]:
                            add(
                                source_view_id=source_view_id, slice_id=slice_id,
                                fold_id=fold_id, rating_action=action,
                                score_arm=arm, horizon_sessions=horizon,
                            )
    elif family_id == REPORT_FAMILY_IDS[11]:
        trials = report_contract["strategy_trial_registry"]["ordered_trials"]
        for slice_id, _folds, _fold_scopes in scopes:
            for trial in trials:
                for decile in dimensions["percentile_bins"]:
                    add(
                        source_view_id=source_view_id, slice_id=slice_id,
                        fold_id="POOLED", trial_id=trial["trial_id"],
                        turnover_decile=decile,
                    )
    elif family_id == REPORT_FAMILY_IDS[12]:
        by_fold = {axis.fold_id: axis.sessions for axis in economic_axes}
        for slice_id, folds, _fold_scopes in scopes:
            for fold_id in folds:
                for point in by_fold[fold_id]:
                    add(
                        source_view_id=source_view_id, slice_id=slice_id,
                        fold_id=fold_id, session=point.session.isoformat(),
                    )
    else:
        raise FormalCloudEvaluationError(
            "report family has no explicit unavailable-cell axis"
        )
    return rows


def _economic_required_family_rows(
    *, report: Mapping[str, object], source_view_id: str,
    schema: Mapping[str, object], report_contract: Mapping[str, object],
    trial_observations: Mapping[str, tuple[_ReportTrialObservation, ...]],
    trial_censuses: Mapping[tuple[str, str], _ReportTrialFoldCensus],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
    resamples: int,
) -> list[dict[str, object]]:
    report_summaries = {
        (row["slice_id"], row["cost_bps_per_side"]): row
        for row in report["economic_summaries"]
    }
    bootstrap_axes = {
        axis.fold_id: tuple(point.session_position for point in axis.sessions)
        for axis in economic_axes
    }
    if tuple(bootstrap_axes) != FORMAL_FOLD_IDS:
        raise FormalCloudEvaluationError("economic report bootstrap axis changed")
    rows: list[dict[str, object]] = []
    for slice_id, slice_folds, fold_scopes in _report_slice_scopes(report_contract):
        for fold_id in fold_scopes:
            folds = slice_folds if fold_id == "POOLED" else (fold_id,)
            for trial in report_contract["strategy_trial_registry"][
                "ordered_trials"
            ]:
                trial_id = trial["trial_id"]
                variant = trial["portfolio_variant_id"]
                cost = trial["cost_bps_per_side"]
                selected = tuple(
                    item for item in trial_observations[trial_id]
                    if item.fold_id in folds
                )
                selected_census = tuple(
                    trial_censuses[(trial_id, fold)] for fold in folds
                )
                session_count = sum(item.session_count for item in selected_census)
                refused_count = sum(
                    item.refused_return_session_count for item in selected_census
                )
                valid_count = len(selected)
                if valid_count + refused_count != session_count:
                    raise FormalCloudEvaluationError(
                        "economic trial observation census is not exhaustive"
                    )
                gross = tuple(
                    item.gross_portfolio_total_return for item in selected
                )
                benchmark = tuple(item.benchmark_total_return for item in selected)
                net = tuple(item.net_portfolio_total_return for item in selected)
                excess = tuple(
                    item.net_excess_daily_total_return for item in selected
                )
                turnover = tuple(item.turnover for item in selected)
                cumulative_net = _compound_total_return(net)
                cumulative_benchmark = _compound_total_return(benchmark)
                geometric_relative: Decimal | None = None
                if (
                    cumulative_net is not None
                    and cumulative_benchmark is not None
                    and Decimal(1) + cumulative_benchmark > 0
                ):
                    with localcontext(_evaluation._context()):
                        geometric_relative = +(
                            (Decimal(1) + cumulative_net)
                            / (Decimal(1) + cumulative_benchmark)
                            - Decimal(1)
                        )
                status = "AVAILABLE"
                reasons: list[str] = []
                if refused_count:
                    status = (
                        "INVALID_DATA"
                        if any(
                            reason == "outcome_identity_invalid" and count
                            for item in selected_census
                            for reason, count in item.refusal_counts
                        )
                        else "INCONCLUSIVE"
                    )
                    reasons = ["economic_fold_has_named_refusal"]
                if (
                    valid_count < _evaluation.MINIMUM_VALID_DATES
                    and status != "INVALID_DATA"
                ):
                    status = "INCONCLUSIVE"
                    reasons = ["valid_return_session_floor_not_met"]
                host_summary = (
                    report_summaries.get((slice_id, cost))
                    if variant == "direct_stock_equal_weight"
                    and fold_id == "POOLED" else None
                )
                host_summary_status = (
                    _report_cell_status(host_summary["status"])
                    if host_summary is not None else None
                )
                if host_summary_status == "INVALID_DATA":
                    status = "INVALID_DATA"
                    reasons = _report_cell_reasons(
                        _summary_reasons(host_summary), host_summary_status
                    )
                elif status == "AVAILABLE" and host_summary_status is not None:
                    status = host_summary_status
                    reasons = _report_cell_reasons(
                        _summary_reasons(host_summary), host_summary_status
                    )
                elif (
                    host_summary_status == "AVAILABLE"
                    and status != "AVAILABLE"
                ):
                    reasons = list(dict.fromkeys((
                        *reasons, "source_summary_incorrectly_claimed_complete",
                    )))
                dated_excess = tuple(
                    (item.session_position, item.net_excess_daily_total_return)
                    for item in selected
                )
                hac_pairs, hac_se, hac_t = _evaluation._v2_hac(
                    dated_excess, 20
                )
                incidence = sum(
                    item.sleeve_security_incidence_count for item in selected
                )
                duplicate_incidence = sum(
                    item.duplicate_sleeve_security_incidence_count
                    for item in selected
                )
                bootstrap_count: int | None = None
                p_value: Fraction | None = None
                if (
                    slice_id == _evaluation.FORMAL_SLICE_ID
                    and fold_id == "POOLED" and status == "AVAILABLE"
                    and excess
                ):
                    metric_id = (
                        "primary_economic_equal_weight_cost10"
                        if trial_id == "direct_stock_equal_weight_cost10"
                        else f"secondary_economic_{trial_id}"
                    )
                    replicates = _report_stock_centered_bootstrap(
                        report_contract=report_contract,
                        values=tuple(
                            (
                                item.fold_id, item.session_position,
                                item.net_excess_daily_total_return,
                            )
                            for item in selected
                        ),
                        axes=bootstrap_axes,
                        block_length=_evaluation.SLEEVE_HOLDING_SESSIONS,
                        source_view_id=source_view_id,
                        metric_id=metric_id,
                        resamples=resamples,
                    )
                    if replicates is None:
                        status = "INCONCLUSIVE"
                        reasons = ["complete_session_bootstrap_unavailable"]
                    else:
                        bootstrap_count = resamples
                        p_value = _report_two_sided_p(
                            _evaluation._mean(excess), replicates
                        )
                if host_summary is not None:
                    expected_host_p = _fraction_from_document(
                        host_summary["centered_two_sided_p_value"]
                    )
                    if (
                        host_summary["session_count"] != session_count
                        or host_summary["valid_return_session_count"]
                        != valid_count
                        or host_summary["refused_return_session_count"]
                        != refused_count
                        or host_summary["mean_net_excess_daily_return"]
                        != _report_wire_cell(
                            None if not excess
                            else _evaluation._mean(excess)
                        )
                        or expected_host_p != p_value
                    ):
                        raise FormalCloudEvaluationError(
                            "economic report diverged from host cost path"
                        )
                rows.append({
                    "source_view_id": source_view_id,
                    "slice_id": slice_id,
                    "fold_id": fold_id,
                    "trial_id": trial_id,
                    "status": status,
                    "portfolio_variant_id": variant,
                    "cost_bps_per_side": cost,
                    "session_count": session_count,
                    "valid_return_session_count": valid_count,
                    "refused_return_session_count": refused_count,
                    "invested_session_count": sum(
                        item.invested_session_count for item in selected_census
                    ),
                    "cash_sleeve_count": sum(
                        item.cash_sleeve_count for item in selected_census
                    ),
                    "selected_sleeve_count": sum(
                        item.selected_sleeve_count for item in selected_census
                    ),
                    "mean_gross_portfolio_total_return": (
                        None if not gross else _evaluation._mean(gross)
                    ),
                    "mean_SPY_total_return": (
                        None if not benchmark else _evaluation._mean(benchmark)
                    ),
                    "mean_net_portfolio_total_return": (
                        None if not net else _evaluation._mean(net)
                    ),
                    "mean_net_excess_daily_total_return": (
                        None if not excess else _evaluation._mean(excess)
                    ),
                    "cumulative_net_portfolio_total_return": (
                        cumulative_net if refused_count == 0 else None
                    ),
                    "cumulative_SPY_total_return": (
                        cumulative_benchmark if refused_count == 0 else None
                    ),
                    "geometric_relative_total_return": (
                        geometric_relative if refused_count == 0 else None
                    ),
                    "mean_daily_turnover": (
                        None if not turnover else _evaluation._mean(turnover)
                    ),
                    "terminal_liquidation_turnover": _evaluation._stable_sum(
                        tuple(
                            item.terminal_liquidation_turnover
                            for item in selected_census
                        )
                    ),
                    "sleeve_security_incidence_count": incidence,
                    "duplicate_sleeve_security_incidence_count": (
                        duplicate_incidence
                    ),
                    "sleeve_overlap_share": (
                        None if incidence == 0
                        else Fraction(duplicate_incidence, incidence)
                    ),
                    "hac_lag_sessions": 20,
                    "hac_pair_counts": list(hac_pairs),
                    "bootstrap_resamples": bootstrap_count,
                    "centered_two_sided_p_value": p_value,
                    "reasons": reasons,
                })
    return rows


def _compound_total_return(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    with localcontext(_evaluation._context()):
        wealth = Decimal(1)
        for item in values:
            wealth = +(wealth * (Decimal(1) + item))
        return +(wealth - Decimal(1))


def _report_stock_unbiased_start(
    *, report_contract: Mapping[str, object], modulus: int,
    source_view_id: str, slice_id: str, metric_id: str,
    replicate: int, fold_ordinal: int, block_ordinal: int,
) -> int:
    bootstrap = report_contract["bootstrap"]
    if (
        type(modulus) is not int or modulus < 1
        or source_view_id not in SOURCE_VIEW_IDS
        or slice_id != _evaluation.FORMAL_SLICE_ID
        or metric_id not in bootstrap["metric_ids"]
        or type(replicate) is not int
        or not 0 <= replicate < bootstrap["resamples"]
        or type(fold_ordinal) is not int
        or not 0 <= fold_ordinal < len(FORMAL_FOLD_IDS)
        or type(block_ordinal) is not int or block_ordinal < 0
    ):
        raise FormalCloudEvaluationError(
            "report stock bootstrap draw geometry changed"
        )

    def encoded_text(value: str) -> bytes:
        raw = value.encode("ascii")
        if len(raw) >= 1 << 16:
            raise FormalCloudEvaluationError(
                "report stock bootstrap identifier is too long"
            )
        return len(raw).to_bytes(2, "big") + raw

    prefix = (
        bootstrap["draw_domain"].encode("ascii") + b"\x00"
        + bytes.fromhex(bootstrap["stock_FM_and_economic_seed_sha256"])
        + encoded_text(source_view_id) + encoded_text(slice_id)
        + encoded_text(metric_id) + replicate.to_bytes(8, "big")
        + fold_ordinal.to_bytes(8, "big")
        + block_ordinal.to_bytes(8, "big")
    )
    ceiling = 1 << 256
    limit = ceiling - ceiling % modulus
    for rejection in range(1 << 32):
        word = int.from_bytes(
            hashlib.sha256(
                prefix + rejection.to_bytes(8, "big")
            ).digest(),
            "big",
        )
        if word < limit:
            return word % modulus
    raise FormalCloudEvaluationError(
        "report stock bootstrap rejection counter overflow"
    )


def _report_stock_centered_bootstrap(
    *, report_contract: Mapping[str, object],
    values: tuple[tuple[str, int, Decimal], ...],
    axes: Mapping[str, tuple[int, ...]], block_length: int,
    source_view_id: str, metric_id: str, resamples: int,
) -> tuple[Decimal, ...] | None:
    if (
        not values or tuple(axes) != FORMAL_FOLD_IDS
        or type(block_length) is not int or block_length < 1
        or type(resamples) is not int
        or not 1 <= resamples <= report_contract["bootstrap"]["resamples"]
    ):
        return None
    observed = _evaluation._mean(tuple(item[2] for item in values))
    with localcontext(_evaluation._context()):
        centered = {
            (fold, position): +(item - observed)
            for fold, position, item in values
        }
    if len(centered) != len(values):
        raise FormalCloudEvaluationError(
            "report stock bootstrap values duplicated a session"
        )
    eligible: dict[str, tuple[int, ...]] = {}
    counts: dict[str, int] = {}
    for fold in FORMAL_FOLD_IDS:
        axis = axes[fold]
        if type(axis) is not tuple or len(axis) < block_length or any(
            type(position) is not int for position in axis
        ):
            raise FormalCloudEvaluationError(
                "report stock bootstrap axis changed"
            )
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
    output: list[Decimal] = []
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
                selected = _report_stock_unbiased_start(
                    report_contract=report_contract, modulus=len(starts),
                    source_view_id=source_view_id,
                    slice_id=_evaluation.FORMAL_SLICE_ID,
                    metric_id=metric_id, replicate=replicate,
                    fold_ordinal=fold_ordinal,
                    block_ordinal=block_ordinal,
                )
                start = starts[selected]
                fold_sample.extend(
                    centered[(fold, position)]
                    for position in axes[fold][start:start + block_length]
                )
            sampled.extend(fold_sample[:target_count])
        if len(sampled) != len(values):
            raise FormalCloudEvaluationError(
                "report stock bootstrap replicate changed its census"
            )
        output.append(_evaluation._mean(tuple(sampled)))
    return tuple(output)


def _report_two_sided_p(
    observed: Decimal, replicates: Sequence[Decimal],
) -> Fraction:
    return Fraction(
        1 + sum(
            item.copy_abs() >= observed.copy_abs()
            for item in replicates
        ),
        len(replicates) + 1,
    )


def _subset_fm_hypothesis_p_values(
    *, observations: Sequence[_SubsetFmReportObservation],
    source_view_id: str, report_contract: Mapping[str, object],
    fold_axes: Sequence[_evaluation.FoldSessionAxis], resamples: int,
) -> dict[str, Fraction | None]:
    h20_axes = {
        axis.fold_id: tuple(point.session_position for point in axis.sessions)
        for axis in fold_axes if axis.horizon_sessions == 20
    }
    if tuple(h20_axes) != FORMAL_FOLD_IDS:
        raise FormalCloudEvaluationError("subset FM H20 axis changed")
    by_subset: dict[str, list[_SubsetFmReportObservation]] = defaultdict(list)
    for item in observations:
        by_subset[item.subset_id].append(item)
    output: dict[str, Fraction | None] = {}
    for hypothesis in report_contract["secondary_hypothesis_registry"][
        "ordered_hypotheses"
    ]:
        cohort = hypothesis["cohort_id"]
        exclusion = hypothesis["earnings_exclusion_id"]
        if cohort != "all":
            subset_id = f"cohort:{cohort}"
        elif exclusion != "none":
            subset_id = f"exclusion:{exclusion}"
        else:
            continue
        selected = tuple(by_subset.get(subset_id, ()))
        expected_keys = tuple(
            (fold, position)
            for fold in FORMAL_FOLD_IDS for position in h20_axes[fold]
        )
        if tuple((item.fold_id, item.session_position) for item in selected) != (
            expected_keys
        ):
            raise FormalCloudEvaluationError(
                "subset FM date disposition axis is incomplete or reordered"
            )
        values = tuple(
            (item.fold_id, item.session_position, item.bullish_beta)
            for item in selected if item.bullish_beta is not None
        )
        p_value: Fraction | None = None
        if len(values) >= _evaluation.MINIMUM_VALID_DATES:
            replicates = _report_stock_centered_bootstrap(
                report_contract=report_contract, values=values,
                axes=h20_axes,
                block_length=_evaluation.SLEEVE_HOLDING_SESSIONS,
                source_view_id=source_view_id,
                metric_id=hypothesis["hypothesis_id"],
                resamples=resamples,
            )
            if replicates is not None:
                p_value = _report_two_sided_p(
                    _evaluation._mean(tuple(item[2] for item in values)),
                    replicates,
                )
        output[hypothesis["hypothesis_id"]] = p_value
    return output


def _economic_result_state(
    result: _evaluation.FormalEvaluationStreamingResult,
) -> tuple[
    tuple[_evaluation.EconomicTrialObservation, ...],
    dict[tuple[str, int], _evaluation.EconomicTrialFoldCensus],
]:
    observations = result.economic_trial_observations
    censuses = result.economic_trial_fold_census
    if type(observations) is not tuple or type(censuses) is not tuple:
        raise FormalCloudEvaluationError("economic trial state changed container type")
    expected_census_keys = tuple(
        (fold, cost)
        for fold in FORMAL_FOLD_IDS for cost in _evaluation.COST_BPS_GRID
    )
    observed_census_keys: list[tuple[str, int]] = []
    census_by_key: dict[
        tuple[str, int], _evaluation.EconomicTrialFoldCensus
    ] = {}
    for item in censuses:
        if type(item) is not _evaluation.EconomicTrialFoldCensus:
            raise FormalCloudEvaluationError("economic fold census changed type")
        key = (item.fold_id, item.cost_bps_per_side)
        observed_census_keys.append(key)
        if (
            type(item.refusal_counts) is not tuple
            or type(item.refusal_counts_by_session) is not tuple
            or type(item.reasons) is not tuple
            or any(type(reason) is not str or not reason for reason in item.reasons)
            or type(item.terminal_liquidation_turnover) is not Decimal
            or not item.terminal_liquidation_turnover.is_finite()
            or item.terminal_liquidation_turnover < 0
        ):
            raise FormalCloudEvaluationError(
                "economic fold refusal accounting changed type"
            )
        refusal_totals: Counter[str] = Counter()
        prior_refusal_session: date | None = None
        for refusal_session, refusal_rows in item.refusal_counts_by_session:
            if (
                type(refusal_session) is not date
                or prior_refusal_session is not None
                and refusal_session <= prior_refusal_session
                or type(refusal_rows) is not tuple
                or not refusal_rows
            ):
                raise FormalCloudEvaluationError(
                    "economic dated refusal census is duplicated or reordered"
                )
            prior_refusal_session = refusal_session
            prior_reason: str | None = None
            for reason, count in refusal_rows:
                if (
                    type(reason) is not str or not reason
                    or prior_reason is not None and reason <= prior_reason
                    or type(count) is not int or count <= 0
                ):
                    raise FormalCloudEvaluationError(
                        "economic dated refusal reason census changed"
                    )
                prior_reason = reason
                refusal_totals[reason] += count
        aggregate_refusals: Counter[str] = Counter()
        prior_reason = None
        for reason, count in item.refusal_counts:
            if (
                type(reason) is not str or not reason
                or prior_reason is not None and reason <= prior_reason
                or type(count) is not int or count <= 0
            ):
                raise FormalCloudEvaluationError(
                    "economic aggregate refusal reason census changed"
                )
            prior_reason = reason
            aggregate_refusals[reason] += count
        if (
            item.fold_id not in FORMAL_FOLD_IDS
            or item.cost_bps_per_side not in _evaluation.COST_BPS_GRID
            or item.valid_return_session_count
            + item.refused_return_session_count != item.session_count
            or len(item.refusal_counts_by_session)
            != item.refused_return_session_count
            or refusal_totals != aggregate_refusals
            or any(
                type(value) is not int or value < 0
                for value in (
                    item.session_count, item.valid_return_session_count,
                    item.refused_return_session_count,
                    item.invested_session_count, item.cash_sleeve_count,
                    item.selected_sleeve_count,
                )
            )
        ):
            raise FormalCloudEvaluationError("economic fold census changed")
        census_by_key[key] = item
    if tuple(observed_census_keys) != expected_census_keys:
        raise FormalCloudEvaluationError("economic fold census is incomplete or reordered")
    prior: tuple[int, int, int] | None = None
    observed_counts: Counter[tuple[str, int]] = Counter()
    for item in observations:
        if type(item) is not _evaluation.EconomicTrialObservation:
            raise FormalCloudEvaluationError("economic trial observation changed type")
        key = (
            FORMAL_FOLD_IDS.index(item.fold_id),
            _evaluation.COST_BPS_GRID.index(item.cost_bps_per_side),
            item.session_position,
        )
        if prior is not None and key <= prior:
            raise FormalCloudEvaluationError(
                "economic trial observations are duplicated or reordered"
            )
        prior = key
        for value in (
            item.gross_portfolio_total_return, item.benchmark_total_return,
            item.net_portfolio_total_return,
            item.net_excess_daily_total_return, item.turnover,
        ):
            if type(value) is not Decimal or not value.is_finite():
                raise FormalCloudEvaluationError(
                    "economic trial observation is not finite Decimal"
                )
        with localcontext(_evaluation._context()):
            expected_net = +(
                item.gross_portfolio_total_return
                - item.turnover * Decimal(item.cost_bps_per_side)
                / Decimal(10_000)
            )
            expected_excess = +(
                item.net_portfolio_total_return - item.benchmark_total_return
            )
        if (
            item.net_portfolio_total_return != expected_net
            or item.net_excess_daily_total_return != expected_excess
            or item.turnover < 0
            or type(item.sleeve_security_incidence_count) is not int
            or type(item.duplicate_sleeve_security_incidence_count) is not int
            or not 0 <= item.duplicate_sleeve_security_incidence_count <= (
                item.sleeve_security_incidence_count
            )
            or type(item.terminal_liquidation) is not bool
        ):
            raise FormalCloudEvaluationError(
                "economic trial observation arithmetic changed"
            )
        observed_counts[(item.fold_id, item.cost_bps_per_side)] += 1
    if any(
        observed_counts[key] != census_by_key[key].valid_return_session_count
        for key in expected_census_keys
    ):
        raise FormalCloudEvaluationError(
            "economic trial observations do not reconcile to fold census"
        )
    return observations, census_by_key


def _report_trial_state(
    *, result: _evaluation.FormalEvaluationStreamingResult,
    registry: Mapping[str, object],
    variant_observations: Sequence[_ReportTrialObservation],
    variant_censuses: Sequence[_ReportTrialFoldCensus],
) -> tuple[
    dict[str, tuple[_ReportTrialObservation, ...]],
    dict[tuple[str, str], _ReportTrialFoldCensus],
]:
    """Normalize the four host cost paths and two cloud weighting variants."""

    host_observations, host_censuses = _economic_result_state(result)
    observed_variant_keys = tuple(
        (item.trial_id, item.fold_id) for item in variant_censuses
    )
    expected_variant_keys = tuple(
        (f"{variant}_cost10", fold)
        for variant in _REPORT_ONLY_PORTFOLIO_VARIANT_IDS
        for fold in FORMAL_FOLD_IDS
    )
    if (
        type(variant_observations) not in {tuple, list}
        or type(variant_censuses) not in {tuple, list}
        or observed_variant_keys != expected_variant_keys
        or any(
            type(item) is not _ReportTrialObservation
            for item in variant_observations
        )
        or any(
            type(item) is not _ReportTrialFoldCensus
            for item in variant_censuses
        )
    ):
        raise FormalCloudEvaluationError(
            "report economic variant state is incomplete or reordered"
        )
    variant_by_trial: dict[str, list[_ReportTrialObservation]] = defaultdict(list)
    for item in variant_observations:
        variant_by_trial[item.trial_id].append(item)
    variant_census_by_key = {
        (item.trial_id, item.fold_id): item for item in variant_censuses
    }
    output: dict[str, tuple[_ReportTrialObservation, ...]] = {}
    census_output: dict[tuple[str, str], _ReportTrialFoldCensus] = {}
    trials = registry["ordered_trials"]
    for trial in trials:
        trial_id = trial["trial_id"]
        variant = trial["portfolio_variant_id"]
        cost = trial["cost_bps_per_side"]
        if variant == "direct_stock_equal_weight":
            output[trial_id] = tuple(
                _ReportTrialObservation(
                    trial_id=trial_id, portfolio_variant_id=variant,
                    cost_bps_per_side=cost, fold_id=item.fold_id,
                    session=item.session, session_position=item.session_position,
                    gross_portfolio_total_return=(
                        item.gross_portfolio_total_return
                    ),
                    benchmark_total_return=item.benchmark_total_return,
                    net_portfolio_total_return=item.net_portfolio_total_return,
                    net_excess_daily_total_return=(
                        item.net_excess_daily_total_return
                    ),
                    turnover=item.turnover,
                    sleeve_security_incidence_count=(
                        item.sleeve_security_incidence_count
                    ),
                    duplicate_sleeve_security_incidence_count=(
                        item.duplicate_sleeve_security_incidence_count
                    ),
                    terminal_liquidation=item.terminal_liquidation,
                )
                for item in host_observations
                if item.cost_bps_per_side == cost
            )
            for fold in FORMAL_FOLD_IDS:
                source = host_censuses[(fold, cost)]
                census_output[(trial_id, fold)] = _ReportTrialFoldCensus(
                    trial_id=trial_id, portfolio_variant_id=variant,
                    cost_bps_per_side=cost, fold_id=fold,
                    session_count=source.session_count,
                    valid_return_session_count=(
                        source.valid_return_session_count
                    ),
                    refused_return_session_count=(
                        source.refused_return_session_count
                    ),
                    invested_session_count=source.invested_session_count,
                    cash_sleeve_count=source.cash_sleeve_count,
                    selected_sleeve_count=source.selected_sleeve_count,
                    terminal_liquidation_turnover=(
                        source.terminal_liquidation_turnover
                    ),
                    refusal_counts=source.refusal_counts,
                    refusal_counts_by_session=source.refusal_counts_by_session,
                )
        elif variant in _REPORT_ONLY_PORTFOLIO_VARIANT_IDS and cost == 10:
            output[trial_id] = tuple(variant_by_trial[trial_id])
            for fold in FORMAL_FOLD_IDS:
                census_output[(trial_id, fold)] = variant_census_by_key[
                    (trial_id, fold)
                ]
        else:
            raise FormalCloudEvaluationError(
                "strategy trial registry escaped its six frozen paths"
            )
    if tuple(output) != tuple(item["trial_id"] for item in trials):
        raise FormalCloudEvaluationError("strategy trial state order changed")
    for trial_id, observations in output.items():
        prior: tuple[int, int] | None = None
        observed = Counter(item.fold_id for item in observations)
        for item in observations:
            key = (FORMAL_FOLD_IDS.index(item.fold_id), item.session_position)
            if prior is not None and key <= prior:
                raise FormalCloudEvaluationError(
                    "strategy trial observations are duplicated or reordered"
                )
            prior = key
        for fold in FORMAL_FOLD_IDS:
            census = census_output[(trial_id, fold)]
            if (
                observed[fold] != census.valid_return_session_count
                or census.valid_return_session_count
                + census.refused_return_session_count != census.session_count
            ):
                raise FormalCloudEvaluationError(
                    "strategy trial observations do not reconcile"
                )
    return output, census_output


def _sample_standard_deviation(values: Sequence[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _evaluation._mean(tuple(values))
    with localcontext(_evaluation._context()):
        variance = +(
            _evaluation._stable_sum(tuple(
                +((item - mean) ** 2) for item in values
            )) / Decimal(len(values) - 1)
        )
        return +variance.sqrt()


def _rolling_family_rows(
    *, result: _evaluation.FormalEvaluationStreamingResult,
    source_view_id: str, report_contract: Mapping[str, object],
    fold_axes: Sequence[_evaluation.FoldSessionAxis],
) -> list[dict[str, object]]:
    observations, _censuses = _economic_result_state(result)
    ic_rows = result.daily_information_coefficient_observations
    if type(ic_rows) is not tuple or any(
        type(item) is not _evaluation.DailyInformationCoefficientObservation
        for item in ic_rows
    ):
        raise FormalCloudEvaluationError("daily IC observation state changed")
    h20_axes = {
        axis.fold_id: axis.sessions for axis in fold_axes
        if axis.horizon_sessions == 20
    }
    ic_maps = {
        "firm_specific_H20_daily_IC": {
            (item.fold_id, item.session_position): item.firm_specific_ic
            for item in ic_rows if item.horizon_sessions == 20
        },
        "global_map_H20_daily_IC": {
            (item.fold_id, item.session_position): item.global_map_ic
            for item in ic_rows if item.horizon_sessions == 20
        },
        "direct_stock_equal_weight_cost10_daily_net_excess_return": {
            (item.fold_id, item.session_position): (
                item.net_excess_daily_total_return
            )
            for item in observations if item.cost_bps_per_side == 10
        },
    }
    rows: list[dict[str, object]] = []
    for slice_id, folds, _fold_scopes in _report_slice_scopes(report_contract):
        axis = tuple(
            (fold, point)
            for fold in folds for point in h20_axes[fold]
        )
        for fold, point in axis:
            first_position = max(0, point.session_position - 59)
            # A rolling window is an exact XNYS-position interval, not the
            # last 60 emitted H20 test rows.  Non-test gaps and refused dates
            # remain in the 60-position denominator and never cause rows from
            # another fold to slide into the window.
            window = tuple(
                candidate for candidate in h20_axes[fold]
                if first_position <= candidate.session_position <= (
                    point.session_position
                )
            )
            axis_session_count = point.session_position - first_position + 1
            for series_id in report_contract["dimensions"]["rolling_series_ids"]:
                values = tuple(
                    value
                    for candidate in window
                    if (
                        value := ic_maps[series_id].get(
                            (fold, candidate.session_position)
                        )
                    ) is not None
                )
                standard_deviation = _sample_standard_deviation(values)
                status = "AVAILABLE"
                reasons: list[str] = []
                if len(values) < 50:
                    status = "UNAVAILABLE"
                    reasons.append("rolling_valid_observation_floor_not_met")
                elif standard_deviation in (None, Decimal(0)):
                    status = "UNAVAILABLE"
                    reasons.append("rolling_zero_sample_standard_deviation")
                mean = None if not values else _evaluation._mean(values)
                annualized: Decimal | None = None
                if status == "AVAILABLE":
                    assert mean is not None and standard_deviation is not None
                    with localcontext(_evaluation._context()):
                        annualized = +(
                            mean / standard_deviation * Decimal(252).sqrt()
                        )
                rows.append({
                    "source_view_id": source_view_id,
                    "slice_id": slice_id,
                    "fold_id": "POOLED",
                    "window_end_session": point.session.isoformat(),
                    "series_id": series_id,
                    "status": status,
                    "axis_session_count": axis_session_count,
                    "valid_observation_count": len(values),
                    "rolling_mean": mean,
                    "rolling_sample_standard_deviation": standard_deviation,
                    "annualized_sharpe_or_icir": annualized,
                    "reasons": reasons,
                })
    return rows


def _year_alpha_family_rows(
    *, result: _evaluation.FormalEvaluationStreamingResult,
    source_view_id: str, report_contract: Mapping[str, object],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
) -> list[dict[str, object]]:
    observations, censuses = _economic_result_state(result)
    axes = {axis.fold_id: axis.sessions for axis in economic_axes}
    rows: list[dict[str, object]] = []
    for slice_id, folds, fold_scopes in _report_slice_scopes(report_contract):
        years = tuple(int(fold.rsplit("-", 1)[1]) for fold in folds)
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            selected_years = years if fold_id == "POOLED" else (
                int(fold_id.rsplit("-", 1)[1]),
            )
            for year in selected_years:
                selected = tuple(
                    item for item in observations
                    if item.cost_bps_per_side == 10
                    and item.fold_id in selected_folds
                    and item.session.year == year
                )
                expected_session_count = sum(
                    point.session.year == year
                    for fold in selected_folds for point in axes[fold]
                )
                values = tuple(
                    item.net_excess_daily_total_return for item in selected
                )
                dated = tuple(
                    (item.session_position, item.net_excess_daily_total_return)
                    for item in selected
                )
                pairs, standard_error, hac_t = _evaluation._v2_hac(dated, 20)
                refused = expected_session_count - len(values)
                if refused < 0:
                    raise FormalCloudEvaluationError(
                        "year-alpha valid census exceeded its exact dated axis"
                    )
                identity_invalid = any(
                    refusal_session.year == year
                    and reason == "outcome_identity_invalid" and count
                    for fold in selected_folds
                    for refusal_session, refusal_rows
                    in censuses[(fold, 10)].refusal_counts_by_session
                    for reason, count in refusal_rows
                )
                status = (
                    "INVALID_DATA" if identity_invalid
                    else "AVAILABLE" if values and refused == 0
                    else "INCONCLUSIVE"
                )
                reasons = [] if status == "AVAILABLE" else [
                    "year_alpha_has_missing_or_refused_sessions"
                ]
                mean = None if not values else _evaluation._mean(values)
                with localcontext(_evaluation._context()):
                    annualized = None if mean is None else +(mean * Decimal(252))
                rows.append({
                    "source_view_id": source_view_id,
                    "slice_id": slice_id,
                    "fold_id": fold_id,
                    "calendar_year": year,
                    "status": status,
                    "valid_session_count": len(values),
                    "mean_net_excess_daily_total_return": mean,
                    "annualized_arithmetic_net_excess_return": annualized,
                    "hac_lag_sessions": 20,
                    "hac_pair_counts": list(pairs),
                    "hac_standard_error": standard_error,
                    "hac_t": hac_t,
                    "reasons": reasons,
                })
    return rows


def _turnover_decile(
    ordered: Sequence[_ReportTrialObservation], index: int,
) -> int:
    value = ordered[index].turnover
    first = index
    while first and ordered[first - 1].turnover == value:
        first -= 1
    last = index
    while last + 1 < len(ordered) and ordered[last + 1].turnover == value:
        last += 1
    average_rank = Fraction((first + 1) + (last + 1), 2)
    return min(10, 1 + int(
        Fraction(10, 1) * (average_rank - 1) / len(ordered)
    ))


def _turnover_family_rows(
    *, source_view_id: str, report_contract: Mapping[str, object],
    trial_observations: Mapping[str, tuple[_ReportTrialObservation, ...]],
    trial_censuses: Mapping[tuple[str, str], _ReportTrialFoldCensus],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    trials = report_contract["strategy_trial_registry"]["ordered_trials"]
    for slice_id, folds, _fold_scopes in _report_slice_scopes(report_contract):
        for trial in trials:
            trial_id = trial["trial_id"]
            cost = trial["cost_bps_per_side"]
            selected = sorted(
                (
                    item for item in trial_observations[trial_id]
                    if item.fold_id in folds
                ),
                key=lambda item: (
                    item.turnover, item.session_position, item.fold_id
                ),
            )
            bins: dict[int, list[_ReportTrialObservation]] = {
                decile: [] for decile in range(1, 11)
            }
            for index, item in enumerate(selected):
                bins[_turnover_decile(selected, index)].append(item)
            refused = sum(
                trial_censuses[(trial_id, fold)].refused_return_session_count
                for fold in folds
            )
            for decile in range(1, 11):
                values = bins[decile]
                status = (
                    "AVAILABLE" if values and refused == 0
                    else "INCONCLUSIVE" if values
                    else "UNAVAILABLE"
                )
                reasons = (
                    [] if status == "AVAILABLE"
                    else ["turnover_decile_has_missing_or_refused_sessions"]
                    if values else ["turnover_decile_is_empty"]
                )
                rows.append({
                    "source_view_id": source_view_id,
                    "slice_id": slice_id,
                    "fold_id": "POOLED",
                    "trial_id": trial_id,
                    "turnover_decile": decile,
                    "status": status,
                    "portfolio_variant_id": trial["portfolio_variant_id"],
                    "cost_bps_per_side": cost,
                    "session_count": len(values),
                    "mean_turnover": (
                        None if not values else _evaluation._mean(tuple(
                            item.turnover for item in values
                        ))
                    ),
                    "mean_net_total_return": (
                        None if not values else _evaluation._mean(tuple(
                            item.net_portfolio_total_return for item in values
                        ))
                    ),
                    "mean_net_excess_total_return": (
                        None if not values else _evaluation._mean(tuple(
                            item.net_excess_daily_total_return for item in values
                        ))
                    ),
                    "reasons": reasons,
                })
    return rows


def _drawdown_family_rows(
    *, result: _evaluation.FormalEvaluationStreamingResult,
    source_view_id: str, report_contract: Mapping[str, object],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
) -> list[dict[str, object]]:
    observations, censuses = _economic_result_state(result)
    observation_map = {
        (item.fold_id, item.session_position): item
        for item in observations if item.cost_bps_per_side == 10
    }
    axes = {axis.fold_id: axis.sessions for axis in economic_axes}
    rows: list[dict[str, object]] = []
    for slice_id, folds, _fold_scopes in _report_slice_scopes(report_contract):
        for fold in folds:
            census = censuses[(fold, 10)]
            complete = census.refused_return_session_count == 0
            portfolio_wealth = Decimal(1)
            benchmark_wealth = Decimal(1)
            running_peak = Decimal(1)
            maximum_drawdown = Decimal(0)
            underwater = 0
            maximum_underwater = 0
            for point in axes[fold]:
                observation = observation_map.get((fold, point.session_position))
                if not complete or observation is None:
                    rows.append({
                        "source_view_id": source_view_id,
                        "slice_id": slice_id, "fold_id": fold,
                        "session": point.session.isoformat(),
                        "status": "INCONCLUSIVE",
                        "net_portfolio_wealth": None, "SPY_wealth": None,
                        "drawdown": None, "underwater_session_count": None,
                        "maximum_drawdown_to_date": None,
                        "maximum_underwater_sessions_to_date": None,
                        "reasons": ["economic_fold_has_missing_or_refused_session"],
                    })
                    continue
                with localcontext(_evaluation._context()):
                    portfolio_wealth = +(
                        portfolio_wealth
                        * (Decimal(1) + observation.net_portfolio_total_return)
                    )
                    benchmark_wealth = +(
                        benchmark_wealth
                        * (Decimal(1) + observation.benchmark_total_return)
                    )
                    running_peak = max(running_peak, portfolio_wealth)
                    drawdown = +(portfolio_wealth / running_peak - Decimal(1))
                underwater = 0 if drawdown == 0 else underwater + 1
                maximum_drawdown = min(maximum_drawdown, drawdown)
                maximum_underwater = max(maximum_underwater, underwater)
                rows.append({
                    "source_view_id": source_view_id,
                    "slice_id": slice_id, "fold_id": fold,
                    "session": point.session.isoformat(), "status": "AVAILABLE",
                    "net_portfolio_wealth": portfolio_wealth,
                    "SPY_wealth": benchmark_wealth, "drawdown": drawdown,
                    "underwater_session_count": underwater,
                    "maximum_drawdown_to_date": maximum_drawdown,
                    "maximum_underwater_sessions_to_date": maximum_underwater,
                    "reasons": [],
                })
    return rows


def _fraction_from_document(value: object) -> Fraction | None:
    if (
        type(value) is dict
        and set(value) == {"fraction"}
        and type(value["fraction"]) is list
        and len(value["fraction"]) == 2
        and all(type(item) is int for item in value["fraction"])
        and value["fraction"][1] > 0
    ):
        result = Fraction(value["fraction"][0], value["fraction"][1])
        return result if 0 <= result <= 1 else None
    return None


def _secondary_adjustments(
    *, report: Mapping[str, object], view: str,
    registry: Mapping[str, object],
    economic_rows: Sequence[Mapping[str, object]],
    subset_p_values: Mapping[str, Fraction | None],
) -> list[dict[str, object]]:
    hypotheses = registry["ordered_hypotheses"]
    supplied: list[tuple[Fraction, int, Mapping[str, object], list[str]]] = []
    for hypothesis in hypotheses:
        p_value: Fraction | None = None
        reasons: list[str] = []
        if (
            hypothesis["metric"] == "fama_macbeth_beta"
            and hypothesis["cohort_id"] == "all"
            and hypothesis["earnings_exclusion_id"] == "none"
        ):
            match = next((
                raw for raw in report["fama_macbeth_summaries"]
                if raw["slice_id"] == _evaluation.FORMAL_SLICE_ID
                and raw["fold_id"] is None
                and raw["arm"] == hypothesis["score_arm_id"]
                and raw["horizon_sessions"] == hypothesis["horizon_sessions"]
                and raw["coefficient"] == hypothesis["coefficient"]
            ), None)
            if match is not None and match["status"] == "PASS":
                p_value = _fraction_from_document(
                    match["centered_two_sided_p_value"]
                )
        elif hypothesis["metric"] == "fama_macbeth_beta":
            p_value = subset_p_values.get(hypothesis["hypothesis_id"])
        elif hypothesis["metric"] == "mean_net_excess_daily_total_return":
            match = next((
                raw for raw in economic_rows
                if raw["slice_id"] == _evaluation.FORMAL_SLICE_ID
                and raw["fold_id"] == "POOLED"
                and raw["cost_bps_per_side"] == hypothesis["cost_bps_per_side"]
                and raw["portfolio_variant_id"]
                == hypothesis["portfolio_variant_id"]
            ), None)
            if (
                match is not None
                and match["status"] == "AVAILABLE"
            ):
                candidate = match["centered_two_sided_p_value"]
                p_value = (
                    candidate if type(candidate) is Fraction
                    else _fraction_from_document(candidate)
                )
        if p_value is None:
            p_value = Fraction(1, 1)
            reasons.append("registered_hypothesis_p_value_named_unavailable")
        supplied.append((p_value, hypothesis["registry_ordinal"], hypothesis, reasons))
    ranked = sorted(supplied, key=lambda item: (item[0], item[1]))
    family_size = len(ranked)
    raw_adjusted: list[Fraction] = []
    for rank, (p_value, _ordinal, _hypothesis, _reasons) in enumerate(ranked, 1):
        raw_adjusted.append(min(Fraction(1, 1), family_size * p_value / rank))
    q_values = list(raw_adjusted)
    for index in range(len(q_values) - 2, -1, -1):
        q_values[index] = min(q_values[index], q_values[index + 1])
    by_ordinal: dict[int, tuple[int, Fraction, Fraction]] = {}
    for rank, ((_, ordinal, _, _), raw, q_value) in enumerate(
        zip(ranked, raw_adjusted, q_values, strict=True), 1
    ):
        by_ordinal[ordinal] = (rank, raw, q_value)
    output = []
    for p_value, ordinal, hypothesis, reasons in supplied:
        rank, raw, q_value = by_ordinal[ordinal]
        output.append({
            "source_view_id": view,
            "hypothesis_id": hypothesis["hypothesis_id"],
            "registry_ordinal": ordinal,
            "p_value_status": "AVAILABLE" if not reasons else "UNAVAILABLE",
            "p_value_numerator": p_value.numerator,
            "p_value_denominator": p_value.denominator,
            "rank": rank,
            "raw_adjusted_numerator": raw.numerator,
            "raw_adjusted_denominator": raw.denominator,
            "q_value_numerator": q_value.numerator,
            "q_value_denominator": q_value.denominator,
            "rejected_at_q_lte_0_05": q_value <= Fraction(1, 20),
            "reasons": reasons,
        })
    return output


def _strategy_trial_reports(
    *, view: str, registry: Mapping[str, object],
    trial_observations: Mapping[str, tuple[_ReportTrialObservation, ...]],
    trial_censuses: Mapping[tuple[str, str], _ReportTrialFoldCensus],
) -> list[dict[str, object]]:
    trials = registry["ordered_trials"]
    series: dict[str, tuple[_ReportTrialObservation, ...]] = {}
    for trial in trials:
        trial_id = trial["trial_id"]
        if all(
            trial_censuses[(trial_id, fold)].refused_return_session_count == 0
            for fold in FORMAL_FOLD_IDS
        ):
            series[trial_id] = trial_observations[trial_id]
    common_axis: tuple[tuple[str, int], ...] | None = None
    complete = len(series) == len(trials)
    if complete:
        axes = tuple(
            tuple((item.fold_id, item.session_position) for item in series[
                trial["trial_id"]
            ])
            for trial in trials
        )
        complete = bool(axes[0]) and all(axis == axes[0] for axis in axes[1:])
        if complete:
            common_axis = axes[0]
    descriptive: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    if complete:
        for trial in trials:
            values = tuple(
                item.net_excess_daily_total_return
                for item in series[trial["trial_id"]]
            )
            stats = _trial_moments(values)
            if stats is not None:
                descriptive[trial["trial_id"]] = stats
    trial_variance: Decimal | None = None
    expected_maximum: Decimal | None = None
    if complete and len(descriptive) == len(trials):
        sharpes = tuple(
            descriptive[trial["trial_id"]][0] for trial in trials
        )
        mean_sharpe = _evaluation._mean(sharpes)
        with localcontext(_evaluation._context()):
            trial_variance = +(
                _evaluation._stable_sum(tuple(
                    +((item - mean_sharpe) ** 2) for item in sharpes
                )) / Decimal(len(sharpes) - 1)
            )
            expected_maximum = +(
                trial_variance.sqrt()
                * Decimal("1.300140787845584")
            )
    output: list[dict[str, object]] = []
    for trial in trials:
        trial_id = trial["trial_id"]
        values = tuple(
            item.net_excess_daily_total_return
            for item in series.get(trial_id, ())
        ) if complete else ()
        stats = descriptive.get(trial_id) if complete else None
        z_value: Decimal | None = None
        probability: Decimal | None = None
        if (
            common_axis is not None and stats is not None
            and trial_variance is not None and expected_maximum is not None
        ):
            daily_sharpe, _annualized, skewness, kurtosis = stats
            with localcontext(_evaluation._context()):
                denominator_squared = +(
                    Decimal(1) - skewness * daily_sharpe
                    + (kurtosis - Decimal(1)) / Decimal(4)
                    * daily_sharpe * daily_sharpe
                )
                if denominator_squared > 0:
                    z_value = +(
                        (daily_sharpe - expected_maximum)
                        * Decimal(len(values) - 1).sqrt()
                        / denominator_squared.sqrt()
                    )
                    probability = _decimal_normal_cdf(z_value)
        available = probability is not None
        reasons = [] if available else [
            "six_trial_common_daily_series_not_retained"
            if not complete else "deflated_sharpe_moment_domain_unavailable"
        ]
        output.append({
            "source_view_id": view,
            "trial_id": trial_id,
            "T": len(values) if values else None,
            "daily_sharpe": None if stats is None else str(stats[0]),
            "annualized_sharpe": None if stats is None else str(stats[1]),
            "skewness": None if stats is None else str(stats[2]),
            "kurtosis": None if stats is None else str(stats[3]),
            "trial_sharpe_variance": (
                None if trial_variance is None else str(trial_variance)
            ),
            "expected_maximum_sharpe": (
                None if expected_maximum is None else str(expected_maximum)
            ),
            "deflated_sharpe_z": None if z_value is None else str(z_value),
            "deflated_sharpe_probability": (
                None if probability is None else str(probability)
            ),
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "reasons": reasons,
        })
    return output


def _trial_moments(
    values: tuple[Decimal, ...],
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    if len(values) < 50:
        return None
    mean = _evaluation._mean(values)
    with localcontext(_evaluation._context()):
        centered = tuple(+(item - mean) for item in values)
        sample_variance = +(
            _evaluation._stable_sum(tuple(+(item ** 2) for item in centered))
            / Decimal(len(values) - 1)
        )
        if sample_variance == 0:
            return None
        sample_standard_deviation = +sample_variance.sqrt()
        daily_sharpe = +(mean / sample_standard_deviation)
        annualized = +(daily_sharpe * Decimal(252).sqrt())
        second = +(
            _evaluation._stable_sum(tuple(+(item ** 2) for item in centered))
            / Decimal(len(values))
        )
        third = +(
            _evaluation._stable_sum(tuple(+(item ** 3) for item in centered))
            / Decimal(len(values))
        )
        fourth = +(
            _evaluation._stable_sum(tuple(+(item ** 4) for item in centered))
            / Decimal(len(values))
        )
        skewness = +(third / (second ** (Decimal(3) / Decimal(2))))
        kurtosis = +(fourth / (second ** 2))
    return daily_sharpe, annualized, skewness, kurtosis


def _decimal_normal_cdf(value: Decimal) -> Decimal:
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        if value <= Decimal(-8):
            return Decimal(0)
        if value >= Decimal(8):
            return Decimal(1)
        x = +(value / Decimal(2).sqrt())
        power_over_factorial = x
        total = Decimal(0)
        epsilon = Decimal("1e-70")
        for index in range(10_000):
            term = +(power_over_factorial / Decimal(2 * index + 1))
            total = +(total + term)
            if abs(term) < epsilon:
                break
            power_over_factorial = +(
                -power_over_factorial * x * x / Decimal(index + 1)
            )
        else:
            raise FormalCloudEvaluationError(
                "deflated-Sharpe normal CDF did not converge"
            )
        pi = Decimal(
            "3.14159265358979323846264338327950288419716939937510"
            "58209749445923078164"
        )
        erf = +(Decimal(2) / pi.sqrt() * total)
        result = +((Decimal(1) + erf) / Decimal(2))
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return +result


def _report_optional_decimal(value: object, name: str) -> Decimal | None:
    return None if value is None else _decimal(value, name)


def _report_optional_fraction(value: object, name: str) -> Fraction | None:
    if value is None:
        return None
    if (
        type(value) is not list or len(value) != 2
        or any(type(item) is not int for item in value)
        or value[1] <= 0
    ):
        raise FormalCloudEvaluationError(f"{name} changed exact Fraction encoding")
    result = Fraction(value[0], value[1])
    if [result.numerator, result.denominator] != value:
        raise FormalCloudEvaluationError(f"{name} is not a reduced Fraction")
    return result


def _report_axis_sha256(values: Sequence[str], *, economic: bool) -> str:
    payload = json.dumps(
        list(values), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if economic:
        payload += b"\n"
    return hashlib.sha256(payload).hexdigest()


def _require_strategy_trial_reports(
    *, rows: Sequence[Mapping[str, object]], registry: Mapping[str, object],
) -> None:
    trials = registry["ordered_trials"]
    expected = tuple(
        (view, trial["trial_id"])
        for view in SOURCE_VIEW_IDS for trial in trials
    )
    if tuple((row.get("source_view_id"), row.get("trial_id")) for row in rows) != expected:
        raise FormalCloudEvaluationError("strategy DSR trial order changed")
    fields = {
        "source_view_id", "trial_id", "T", "daily_sharpe",
        "annualized_sharpe", "skewness", "kurtosis",
        "trial_sharpe_variance", "expected_maximum_sharpe",
        "deflated_sharpe_z", "deflated_sharpe_probability",
        "status", "reasons",
    }
    by_view: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        if type(row) is not dict or set(row) != fields:
            raise FormalCloudEvaluationError("strategy DSR trial fields changed")
        by_view[row["source_view_id"]].append(row)
    for view, selected in by_view.items():
        available = [row for row in selected if row["status"] == "AVAILABLE"]
        if available and len(available) != len(trials):
            raise FormalCloudEvaluationError(
                "strategy DSR used a partial six-trial family"
            )
        common_t: int | None = None
        parsed_sharpes: list[Decimal] = []
        for row, trial in zip(selected, trials, strict=True):
            numeric_names = (
                "daily_sharpe", "annualized_sharpe", "skewness", "kurtosis",
                "trial_sharpe_variance", "expected_maximum_sharpe",
                "deflated_sharpe_z", "deflated_sharpe_probability",
            )
            if row["T"] is not None:
                t_value = _count(row["T"], "strategy trial T", minimum=50)
                if common_t is None:
                    common_t = t_value
                elif available and t_value != common_t:
                    raise FormalCloudEvaluationError(
                        "strategy DSR common session axis changed"
                    )
            daily = _report_optional_decimal(row["daily_sharpe"], "daily Sharpe")
            annualized = _report_optional_decimal(
                row["annualized_sharpe"], "annualized Sharpe"
            )
            if (daily is None) is not (annualized is None):
                raise FormalCloudEvaluationError("strategy Sharpe pair is partial")
            if daily is not None:
                with localcontext(_evaluation._context()):
                    if annualized != +(daily * Decimal(252).sqrt()):
                        raise FormalCloudEvaluationError(
                            "strategy Sharpe annualization changed"
                        )
                parsed_sharpes.append(daily)
            probability = _report_optional_decimal(
                row["deflated_sharpe_probability"],
                "deflated Sharpe probability",
            )
            if probability is not None and not Decimal(0) <= probability <= Decimal(1):
                raise FormalCloudEvaluationError(
                    "deflated Sharpe probability left [0,1]"
                )
            if row["status"] == "AVAILABLE":
                if row["reasons"] or any(
                    row[name] is None for name in numeric_names
                ) or row["T"] is None:
                    raise FormalCloudEvaluationError(
                        "available DSR trial is incomplete"
                    )
            elif (
                row["status"] != "UNAVAILABLE"
                or type(row["reasons"]) is not list or not row["reasons"]
            ):
                raise FormalCloudEvaluationError("strategy DSR status changed")
        if available:
            mean_sharpe = _evaluation._mean(tuple(parsed_sharpes))
            with localcontext(_evaluation._context()):
                variance = +(
                    _evaluation._stable_sum(tuple(
                        +((item - mean_sharpe) ** 2) for item in parsed_sharpes
                    )) / Decimal(len(parsed_sharpes) - 1)
                )
                expected_maximum = +(
                    variance.sqrt() * Decimal("1.300140787845584")
                )
            for row in available:
                if (
                    _decimal(row["trial_sharpe_variance"], "trial variance")
                    != variance
                    or _decimal(
                        row["expected_maximum_sharpe"], "expected maximum Sharpe"
                    ) != expected_maximum
                    or _decimal(
                        row["deflated_sharpe_probability"], "DSR probability"
                    ) != _decimal_normal_cdf(
                        _decimal(row["deflated_sharpe_z"], "DSR z")
                    )
                ):
                    raise FormalCloudEvaluationError(
                        "strategy DSR cross-trial arithmetic changed"
                    )


def _require_economic_report_family(
    *, rows: Sequence[Mapping[str, object]], report: Mapping[str, object],
    view: str, report_contract: Mapping[str, object],
    schema: Mapping[str, object],
) -> None:
    trials = report_contract["strategy_trial_registry"]["ordered_trials"]
    expected_keys = tuple(
        (slice_id, fold_id, trial["trial_id"])
        for slice_id, _folds, fold_scopes in _report_slice_scopes(report_contract)
        for fold_id in fold_scopes for trial in trials
    )
    if tuple(
        (row["slice_id"], row["fold_id"], row["trial_id"])
        for row in rows
    ) != expected_keys:
        raise FormalCloudEvaluationError("economic report trial grid changed")
    trial_by_id = {item["trial_id"]: item for item in trials}
    summaries = {
        (item["slice_id"], item["cost_bps_per_side"]): item
        for item in report["economic_summaries"]
    }
    numeric_names = (
        "mean_gross_portfolio_total_return", "mean_SPY_total_return",
        "mean_net_portfolio_total_return",
        "mean_net_excess_daily_total_return",
        "cumulative_net_portfolio_total_return",
        "cumulative_SPY_total_return", "geometric_relative_total_return",
        "mean_daily_turnover", "terminal_liquidation_turnover",
    )
    count_names = (
        "session_count", "valid_return_session_count",
        "refused_return_session_count", "invested_session_count",
        "cash_sleeve_count", "selected_sleeve_count",
        "sleeve_security_incidence_count",
        "duplicate_sleeve_security_incidence_count",
    )
    for row in rows:
        trial = trial_by_id[row["trial_id"]]
        if (
            row["portfolio_variant_id"] != trial["portfolio_variant_id"]
            or row["cost_bps_per_side"] != trial["cost_bps_per_side"]
        ):
            raise FormalCloudEvaluationError("economic trial registry binding changed")
        counts = {
            name: _count(row[name], f"economic report {name}")
            for name in count_names
        }
        if (
            counts["valid_return_session_count"]
            + counts["refused_return_session_count"]
            != counts["session_count"]
            or counts["duplicate_sleeve_security_incidence_count"]
            > counts["sleeve_security_incidence_count"]
        ):
            raise FormalCloudEvaluationError("economic report census changed")
        decimals = {
            name: _report_optional_decimal(row[name], f"economic report {name}")
            for name in numeric_names
        }
        if any(
            decimals[name] is not None and decimals[name] < 0
            for name in ("mean_daily_turnover", "terminal_liquidation_turnover")
        ):
            raise FormalCloudEvaluationError("economic turnover became negative")
        overlap = _report_optional_fraction(
            row["sleeve_overlap_share"], "economic overlap share"
        )
        incidence = counts["sleeve_security_incidence_count"]
        expected_overlap = (
            None if incidence == 0 else Fraction(
                counts["duplicate_sleeve_security_incidence_count"], incidence
            )
        )
        if overlap != expected_overlap:
            raise FormalCloudEvaluationError("economic overlap share changed")
        gross = decimals["mean_gross_portfolio_total_return"]
        benchmark = decimals["mean_SPY_total_return"]
        net = decimals["mean_net_portfolio_total_return"]
        excess = decimals["mean_net_excess_daily_total_return"]
        turnover = decimals["mean_daily_turnover"]
        if all(item is not None for item in (gross, benchmark, net, excess, turnover)):
            with localcontext(_evaluation._context()):
                if net != +(
                    gross - turnover * Decimal(row["cost_bps_per_side"])
                    / Decimal(10_000)
                ) or excess != +(net - benchmark):
                    raise FormalCloudEvaluationError(
                        "economic report mean arithmetic changed"
                    )
        cumulative_net = decimals["cumulative_net_portfolio_total_return"]
        cumulative_benchmark = decimals["cumulative_SPY_total_return"]
        relative = decimals["geometric_relative_total_return"]
        if all(item is not None for item in (
            cumulative_net, cumulative_benchmark, relative
        )):
            with localcontext(_evaluation._context()):
                if Decimal(1) + cumulative_benchmark <= 0 or relative != +(
                    (Decimal(1) + cumulative_net)
                    / (Decimal(1) + cumulative_benchmark) - Decimal(1)
                ):
                    raise FormalCloudEvaluationError(
                        "economic geometric relative return changed"
                    )
        if (
            row["fold_id"] == "POOLED"
            and trial["portfolio_variant_id"] == "direct_stock_equal_weight"
        ):
            summary = summaries[(
                row["slice_id"], row["cost_bps_per_side"]
            )]
            expected = {
                "session_count": summary["session_count"],
                "valid_return_session_count": summary[
                    "valid_return_session_count"
                ],
                "refused_return_session_count": summary[
                    "refused_return_session_count"
                ],
                "invested_session_count": summary["invested_session_count"],
                "cash_sleeve_count": summary["cash_sleeve_count"],
                "selected_sleeve_count": summary["selected_sleeve_count"],
                "mean_net_excess_daily_total_return": summary[
                    "mean_net_excess_daily_return"
                ],
                "cumulative_net_portfolio_total_return": summary[
                    "cumulative_net_total_return"
                ],
                "mean_daily_turnover": summary["mean_daily_turnover"],
                "terminal_liquidation_turnover": summary[
                    "terminal_liquidation_turnover"
                ],
                "bootstrap_resamples": summary["bootstrap_resamples"],
                "centered_two_sided_p_value": summary[
                    "centered_two_sided_p_value"
                ],
            }
            if any(row[name] != _report_wire_cell(value) for name, value in expected.items()):
                raise FormalCloudEvaluationError(
                    "economic report does not reconcile to authenticated summary"
                )


def _require_event_and_plot_report_families(
    *, decoded: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    view: str, report_contract: Mapping[str, object],
) -> None:
    schema_by_id = {
        item["family_id"]: item for item in report_contract["report_schemas"]
    }
    for family_id in (
        REPORT_FAMILY_IDS[0], REPORT_FAMILY_IDS[1], REPORT_FAMILY_IDS[7],
        REPORT_FAMILY_IDS[10],
    ):
        rows = decoded[(view, family_id)]
        schema = schema_by_id[family_id]
        expected = _expected_report_family_key_rows(
            family_id=family_id, source_view_id=view,
            report_contract=report_contract, fold_axes=(), economic_axes=(),
        )
        key_fields = tuple(schema["ordered_key_fields"])
        if tuple(
            tuple(row[name] for name in key_fields) for row in rows
        ) != tuple(
            tuple(row[name] for name in key_fields) for row in expected
        ):
            raise FormalCloudEvaluationError(
                "report family differs from its complete expected key grid"
            )

    for row in decoded[(view, REPORT_FAMILY_IDS[0])]:
        accepted = _count(row["accepted_event_count"], "event accepted count")
        refused = _count(row["refused_event_count"], "event refused count")
        components = _count(
            row["connected_component_count"], "event component count"
        )
        decimals = tuple(
            _report_optional_decimal(row[name], f"event report {name}")
            for name in (
                "mean_gross_security_total_return", "mean_SPY_total_return",
                "mean_gross_excess_total_return",
                "median_gross_excess_total_return", "hac_standard_error",
                "hac_t",
            )
        )
        if (
            components > accepted
            or row["hac_lag_sessions"] != row["horizon_sessions"]
            or type(row["hac_pair_counts"]) is not list
            or any(type(item) is not int or item < 0 for item in row[
                "hac_pair_counts"
            ])
            or accepted == 0 and any(item is not None for item in decimals[:4])
            or accepted > 0 and any(item is None for item in decimals[:4])
        ):
            raise FormalCloudEvaluationError("event-return report cell changed")
        gross, benchmark, excess = decimals[:3]
        if gross is not None:
            with localcontext(_evaluation._context()):
                if excess != +(gross - benchmark):
                    raise FormalCloudEvaluationError(
                        "event-return report arithmetic changed"
                    )
        if row["status"] == "AVAILABLE" and (
            accepted == 0 or refused != 0 or components == 0
        ):
            raise FormalCloudEvaluationError(
                "available event-return report cell is incomplete"
            )

    for row in decoded[(view, REPORT_FAMILY_IDS[1])]:
        accepted = _count(row["accepted_event_count"], "event-time accepted count")
        refused = _count(row["refused_event_count"], "event-time refused count")
        values = tuple(
            _report_optional_decimal(row[name], f"event-time {name}")
            for name in (
                "mean_security_total_return", "mean_SPY_total_return",
                "mean_cumulative_abnormal_return",
            )
        )
        if (
            accepted == 0 and any(item is not None for item in values)
            or accepted > 0 and any(item is None for item in values)
            or row["status"] == "AVAILABLE" and (accepted == 0 or refused)
        ):
            raise FormalCloudEvaluationError("event-time report cell changed")
        if accepted:
            with localcontext(_evaluation._context()):
                if values[2] != +(values[0] - values[1]):
                    raise FormalCloudEvaluationError(
                        "event-time abnormal-return arithmetic changed"
                    )
            if row["event_time_session"] == 0 and any(
                item != 0 for item in values
            ):
                raise FormalCloudEvaluationError(
                    "event-time zero cell acquired an outcome"
                )

    for row in decoded[(view, REPORT_FAMILY_IDS[7])]:
        count = _count(row["row_count"], "percentile report row count")
        values = tuple(
            _report_optional_decimal(row[name], f"percentile report {name}")
            for name in (
                "mean_score", "mean_future_gross_excess_return",
                "median_future_gross_excess_return",
            )
        )
        if (
            not 1 <= row["percentile_decile"] <= 10
            or count == 0 and any(item is not None for item in values)
            or count > 0 and any(item is None for item in values)
            or row["status"] == "AVAILABLE" and count == 0
        ):
            raise FormalCloudEvaluationError("percentile report cell changed")

    decay_rows = decoded[(view, REPORT_FAMILY_IDS[10])]
    for row in decay_rows:
        valid = _count(row["valid_date_count"], "signal-decay valid dates")
        mean_ic = _report_optional_decimal(row["mean_ic"], "signal-decay mean IC")
        mean_excess = _report_optional_decimal(
            row["mean_gross_excess_return"], "signal-decay mean excess"
        )
        ratio = _report_optional_decimal(
            row["ratio_to_h1_effect"], "signal-decay H1 ratio"
        )
        if (
            valid == 0 and any(item is not None for item in (mean_ic, mean_excess))
            or row["status"] == "AVAILABLE" and (
                valid < 50 or mean_ic is None or mean_excess is None
                or ratio is None
            )
        ):
            raise FormalCloudEvaluationError("signal-decay report cell changed")
    by_base = defaultdict(dict)
    for row in decay_rows:
        by_base[(
            row["slice_id"], row["fold_id"], row["rating_action"],
            row["score_arm"],
        )][row["horizon_sessions"]] = row
    for horizon_rows in by_base.values():
        h1 = _report_optional_decimal(
            horizon_rows[1]["mean_gross_excess_return"], "signal-decay H1 effect"
        )
        for row in horizon_rows.values():
            ratio = _report_optional_decimal(
                row["ratio_to_h1_effect"], "signal-decay ratio"
            )
            effect = _report_optional_decimal(
                row["mean_gross_excess_return"], "signal-decay effect"
            )
            if ratio is not None:
                if h1 in (None, Decimal(0)) or effect is None:
                    raise FormalCloudEvaluationError(
                        "signal-decay ratio lacks its H1 denominator"
                    )
                with localcontext(_evaluation._context()):
                    if ratio != +(effect / h1):
                        raise FormalCloudEvaluationError(
                            "signal-decay ratio arithmetic changed"
                        )


def _require_dated_report_families(
    *, decoded: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    view: str, report_contract: Mapping[str, object],
) -> None:
    annual = decoded[(view, REPORT_FAMILY_IDS[9])]
    for row in annual:
        valid = _count(row["valid_session_count"], "annual alpha valid sessions")
        mean = _report_optional_decimal(
            row["mean_net_excess_daily_total_return"], "annual alpha mean"
        )
        annualized = _report_optional_decimal(
            row["annualized_arithmetic_net_excess_return"],
            "annualized arithmetic net excess",
        )
        if (
            row["hac_lag_sessions"] != 20
            or type(row["hac_pair_counts"]) is not list
            or any(type(item) is not int or item < 0 for item in row[
                "hac_pair_counts"
            ])
            or valid == 0 and (mean is not None or annualized is not None)
            or (mean is None) is not (annualized is None)
        ):
            raise FormalCloudEvaluationError("annual alpha report cell changed")
        if mean is not None:
            with localcontext(_evaluation._context()):
                if annualized != +(mean * Decimal(252)):
                    raise FormalCloudEvaluationError(
                        "annual alpha arithmetic annualization changed"
                    )

    turnover_rows = decoded[(view, REPORT_FAMILY_IDS[11])]
    trials = {
        item["trial_id"]: item for item in report_contract[
            "strategy_trial_registry"
        ]["ordered_trials"]
    }
    for row in turnover_rows:
        trial = trials[row["trial_id"]]
        count = _count(row["session_count"], "turnover-decile session count")
        values = tuple(
            _report_optional_decimal(row[name], f"turnover report {name}")
            for name in (
                "mean_turnover", "mean_net_total_return",
                "mean_net_excess_total_return",
            )
        )
        if (
            row["portfolio_variant_id"] != trial["portfolio_variant_id"]
            or row["cost_bps_per_side"] != trial["cost_bps_per_side"]
            or not 1 <= row["turnover_decile"] <= 10
            or count == 0 and any(item is not None for item in values)
            or count > 0 and any(item is None for item in values)
            or values[0] is not None and values[0] < 0
            or row["status"] == "AVAILABLE" and count == 0
        ):
            raise FormalCloudEvaluationError("turnover report cell changed")

    rolling = decoded[(view, REPORT_FAMILY_IDS[8])]
    series_ids = tuple(report_contract["dimensions"]["rolling_series_ids"])
    for slice_id, folds, _fold_scopes in _report_slice_scopes(report_contract):
        selected = [row for row in rolling if row["slice_id"] == slice_id]
        expected_count = sum(
            item[4] for item in _evaluation.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES
            if item[1] == 20 and item[0] in folds
        )
        if len(selected) != expected_count * len(series_ids):
            raise FormalCloudEvaluationError("rolling report axis census changed")
        dates = tuple(
            row["window_end_session"] for row in selected
            if row["series_id"] == series_ids[0]
        )
        offset = 0
        for frozen in _evaluation.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES:
            if frozen[1] != 20 or frozen[0] not in folds:
                continue
            segment = dates[offset:offset + frozen[4]]
            offset += frozen[4]
            if _report_axis_sha256(segment, economic=False) != frozen[5]:
                raise FormalCloudEvaluationError("rolling report date axis changed")
        for row in selected:
            axis_count = _count(row["axis_session_count"], "rolling axis count", minimum=1)
            valid_count = _count(row["valid_observation_count"], "rolling valid count")
            if axis_count != 60 or valid_count > axis_count:
                raise FormalCloudEvaluationError("rolling report window changed")
            mean = _report_optional_decimal(row["rolling_mean"], "rolling mean")
            deviation = _report_optional_decimal(
                row["rolling_sample_standard_deviation"], "rolling deviation"
            )
            annualized = _report_optional_decimal(
                row["annualized_sharpe_or_icir"], "rolling annualized value"
            )
            if row["status"] == "AVAILABLE":
                if (
                    valid_count < 50 or mean is None or deviation is None
                    or deviation <= 0 or annualized is None
                ):
                    raise FormalCloudEvaluationError("available rolling cell is incomplete")
                with localcontext(_evaluation._context()):
                    if annualized != +(mean / deviation * Decimal(252).sqrt()):
                        raise FormalCloudEvaluationError(
                            "rolling annualization arithmetic changed"
                        )

    drawdown = decoded[(view, REPORT_FAMILY_IDS[12])]
    for slice_id, folds, _fold_scopes in _report_slice_scopes(report_contract):
        for fold in folds:
            rows = [
                row for row in drawdown
                if row["slice_id"] == slice_id and row["fold_id"] == fold
            ]
            frozen = next(
                item for item in _evaluation.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
                if item[0] == fold
            )
            if (
                len(rows) != frozen[8]
                or _report_axis_sha256(
                    tuple(row["session"] for row in rows), economic=True
                ) != frozen[9]
            ):
                raise FormalCloudEvaluationError("drawdown report axis changed")
            prior_max_drawdown = Decimal(0)
            prior_max_underwater = 0
            for row in rows:
                value_fields = (
                    "net_portfolio_wealth", "SPY_wealth", "drawdown",
                    "underwater_session_count", "maximum_drawdown_to_date",
                    "maximum_underwater_sessions_to_date",
                )
                if row["status"] != "AVAILABLE":
                    if any(row[name] is not None for name in value_fields):
                        raise FormalCloudEvaluationError(
                            "unavailable drawdown cell retained numeric values"
                        )
                    continue
                wealth = _decimal(row["net_portfolio_wealth"], "portfolio wealth", positive=True)
                _decimal(row["SPY_wealth"], "SPY wealth", positive=True)
                draw = _decimal(row["drawdown"], "drawdown")
                maximum = _decimal(row["maximum_drawdown_to_date"], "maximum drawdown")
                underwater = _count(row["underwater_session_count"], "underwater count")
                maximum_underwater = _count(
                    row["maximum_underwater_sessions_to_date"],
                    "maximum underwater count",
                )
                if (
                    draw > 0 or maximum > 0 or maximum > prior_max_drawdown
                    or maximum_underwater < prior_max_underwater
                    or maximum_underwater < underwater or wealth <= 0
                ):
                    raise FormalCloudEvaluationError("drawdown path arithmetic changed")
                prior_max_drawdown = maximum
                prior_max_underwater = maximum_underwater


def _require_accounting_report_family(
    *, document: Mapping[str, object],
    decoded: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    view: str, report_contract: Mapping[str, object],
) -> None:
    rows = decoded[(view, REPORT_FAMILY_IDS[6])]
    keyed: dict[tuple[str, str, str, str], Mapping[str, object]] = {}
    for row in rows:
        key = (
            row["slice_id"], row["fold_id"], row["accounting_kind"],
            row["reason_or_component"],
        )
        if key in keyed:
            raise FormalCloudEvaluationError("F6 accounting key duplicated")
        keyed[key] = row
        expected = _count(row["expected_count"], "F6 expected count")
        accepted = _count(row["accepted_count"], "F6 accepted count")
        refused = _count(row["refused_count"], "F6 refused count")
        terminal = _count(row["terminal_count"], "F6 terminal count")
        if (
            row["status"] != "AVAILABLE" or row["reasons"]
            or row["reconciles_exactly"] is not True
            or expected != terminal or expected != accepted + refused
        ):
            raise FormalCloudEvaluationError("F6 accounting equality changed")
        for name in (
            "connected_component_count", "component_member_incidence_count",
            "power_floor",
        ):
            if row[name] is not None:
                _count(row[name], f"F6 {name}")

    view_axis = {
        (item["fold_id"], item["horizon"]): item
        for item in document["source_view_fold_horizon_census"]
        if item["view_id"] == view
    }
    if tuple(view_axis) != tuple(
        (fold, horizon) for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    ):
        raise FormalCloudEvaluationError("F6 source-view horizon parent changed")
    scopes = _report_slice_scopes(report_contract)
    required_keys: set[tuple[str, str, str, str]] = set()
    for slice_id, folds, fold_scopes in scopes:
        for fold_id in fold_scopes:
            selected_folds = folds if fold_id == "POOLED" else (fold_id,)
            pre_key = (
                slice_id, fold_id, "preoutcome_decision_terminal", "all"
            )
            required_keys.add(pre_key)
            pre_row = keyed.get(pre_key)
            expected_decisions = sum(
                view_axis[(fold, 1)]["slot_count"] for fold in selected_folds
            )
            if pre_row is None or pre_row["expected_count"] != expected_decisions:
                raise FormalCloudEvaluationError(
                    "F6 preoutcome decision domain changed"
                )
            for horizon in HORIZONS:
                key = (
                    slice_id, fold_id, "horizon_outcome_terminal",
                    f"h{horizon}",
                )
                required_keys.add(key)
                row = keyed.get(key)
                accepted = sum(
                    view_axis[(fold, horizon)]["accepted_count"]
                    for fold in selected_folds
                )
                refused = sum(
                    view_axis[(fold, horizon)]["refused_count"]
                    for fold in selected_folds
                )
                if row is None or (
                    row["expected_count"], row["accepted_count"],
                    row["refused_count"], row["terminal_count"],
                ) != (accepted + refused, accepted, refused, accepted + refused):
                    raise FormalCloudEvaluationError(
                        "F6 horizon outcome accounting changed"
                    )
            family5 = decoded[(view, REPORT_FAMILY_IDS[5])]
            for trial in report_contract["strategy_trial_registry"][
                "ordered_trials"
            ]:
                key = (
                    slice_id, fold_id, "economic_trial_terminal",
                    trial["trial_id"],
                )
                required_keys.add(key)
                parent = next((
                    item for item in family5
                    if item["slice_id"] == slice_id
                    and item["fold_id"] == fold_id
                    and item["trial_id"] == trial["trial_id"]
                ), None)
                row = keyed.get(key)
                if parent is None or row is None or (
                    row["expected_count"], row["accepted_count"],
                    row["refused_count"], row["terminal_count"],
                ) != (
                    parent["session_count"],
                    parent["valid_return_session_count"],
                    parent["refused_return_session_count"],
                    parent["session_count"],
                ):
                    raise FormalCloudEvaluationError(
                        "F6 economic trial accounting changed"
                    )

    coverage_rows = tuple(
        item for item in decoded[(view, REPORT_FAMILY_IDS[4])]
        if item["record_kind"] == "preoutcome_coverage_ledger"
    )
    for parent in coverage_rows:
        key = (
            _evaluation.FORMAL_SLICE_ID, parent["fold_id"],
            "global_comparator_coverage_ledger", parent["record_id"],
        )
        required_keys.add(key)
        row = keyed.get(key)
        if row is None or (
            row["expected_count"], row["accepted_count"],
            row["refused_count"], row["terminal_count"],
        ) != (
            parent["denominator"], parent["numerator"],
            parent["denominator"] - parent["numerator"],
            parent["denominator"],
        ):
            raise FormalCloudEvaluationError("F6 coverage accounting changed")

    for family_id in REPORT_FAMILY_IDS:
        parent_rows = decoded[(view, family_id)]
        scopes_for_family = tuple(dict.fromkeys(
            (item["slice_id"], item["fold_id"]) for item in parent_rows
        ))
        for slice_id, fold_id in scopes_for_family:
            key = (
                slice_id, fold_id, "report_family_terminal", family_id
            )
            required_keys.add(key)
            parent_scope = tuple(
                item for item in parent_rows
                if item["slice_id"] == slice_id and item["fold_id"] == fold_id
            )
            expected = len(parent_scope)
            accepted = sum(item["status"] == "AVAILABLE" for item in parent_scope)
            if family_id == REPORT_FAMILY_IDS[6]:
                # Every F6 cell is an AVAILABLE exact reconciliation terminal.
                accepted = expected
            row = keyed.get(key)
            if row is None or (
                row["expected_count"], row["accepted_count"],
                row["refused_count"], row["terminal_count"],
            ) != (expected, accepted, expected - accepted, expected):
                raise FormalCloudEvaluationError(
                    "F6 report-family terminal accounting changed"
                )

    power_valid = keyed.get((
        _evaluation.FORMAL_SLICE_ID, "POOLED", "power_floor",
        "valid_h20_fm_dates",
    ))
    power_components = keyed.get((
        _evaluation.FORMAL_SLICE_ID, "POOLED", "power_floor",
        "connected_h20_components",
    ))
    required_keys.update((
        (
            _evaluation.FORMAL_SLICE_ID, "POOLED", "power_floor",
            "valid_h20_fm_dates",
        ),
        (
            _evaluation.FORMAL_SLICE_ID, "POOLED", "power_floor",
            "connected_h20_components",
        ),
    ))
    if (
        power_valid is None or power_components is None
        or power_valid["expected_count"] != 1388
        or power_valid["accepted_count"] < power_valid["power_floor"]
        or power_components["accepted_count"]
        < power_components["power_floor"]
        or power_components["connected_component_count"]
        != power_components["accepted_count"]
    ):
        raise FormalCloudEvaluationError("F6 authenticated power accounting changed")

    lifecycle = tuple(
        row for row in rows
        if row["accounting_kind"] == "lifecycle_terminal_disposition"
    )
    required_keys.update(
        (
            row["slice_id"], row["fold_id"], row["accounting_kind"],
            row["reason_or_component"],
        )
        for row in lifecycle
    )
    # Each physical slot is attributed exactly once across both views.  The
    # all-view equality is checked after the per-view validators below.
    if set(keyed) != required_keys:
        raise FormalCloudEvaluationError(
            "F6 accounting grid is missing or has an undeclared key"
        )


def _expanded_report_outputs(
    *, reports: Sequence[Mapping[str, object]],
    results: Sequence[_evaluation.FormalEvaluationStreamingResult],
    report_contract: Mapping[str, object],
    coverages: Sequence[Mapping[str, object]],
    fold_axes: Sequence[_evaluation.FoldSessionAxis],
    economic_axes: Sequence[_evaluation.EconomicObservationAxis],
    power_floor: _evaluation.PowerFloorBinding,
    partition_counts: Mapping[str, Counter[object]],
    terminal_attribution: Mapping[str, Counter[object]],
    variant_trial_states: Mapping[
        str,
        tuple[
            tuple[_ReportTrialObservation, ...],
            tuple[_ReportTrialFoldCensus, ...],
        ],
    ],
    directional_event_observations: Sequence[
        _DirectionalEventReportObservation
    ],
    decision_report_observations: Sequence[_DecisionReportObservation],
    subset_fm_report_observations: Sequence[_SubsetFmReportObservation],
    resamples: int,
    externalize_report_families: bool = False,
    input_manifest_sha256: str | None = None,
) -> tuple[dict[str, object], tuple[_ReportFamilyObject, ...]]:
    schemas = report_contract["report_schemas"]
    by_id = {item["family_id"]: item for item in schemas}
    if tuple(by_id) != REPORT_FAMILY_IDS:
        raise FormalCloudEvaluationError("report-family schema order changed")
    contract_sha = report_contract["contract_sha256"]
    families: list[dict[str, object]] = []
    adjustments: list[dict[str, object]] = []
    trials: list[dict[str, object]] = []
    trial_registry = report_contract["strategy_trial_registry"]
    for report, result, view in zip(
        reports, results, SOURCE_VIEW_IDS, strict=True
    ):
        variant_observations, variant_censuses = variant_trial_states[view]
        trial_observations, trial_censuses = _report_trial_state(
            result=result, registry=trial_registry,
            variant_observations=variant_observations,
            variant_censuses=variant_censuses,
        )
        subset_p_values = _subset_fm_hypothesis_p_values(
            observations=tuple(
                item for item in subset_fm_report_observations
                if item.source_view_id == view
            ),
            source_view_id=view, report_contract=report_contract,
            fold_axes=fold_axes, resamples=resamples,
        )
        builders: dict[str, list[dict[str, object]]] = {
            REPORT_FAMILY_IDS[0]: _event_return_family_rows(
                observations=directional_event_observations,
                source_view_id=view, report_contract=report_contract,
            ),
            REPORT_FAMILY_IDS[1]: _event_time_family_rows(
                observations=directional_event_observations,
                source_view_id=view, report_contract=report_contract,
            ),
            REPORT_FAMILY_IDS[2]: _ic_family_rows(report, view),
            REPORT_FAMILY_IDS[3]: _fm_family_rows(report, view),
            REPORT_FAMILY_IDS[4]: _paired_coverage_family_rows(
                report, view, coverages
            ),
            REPORT_FAMILY_IDS[5]: _economic_required_family_rows(
                report=report, source_view_id=view,
                schema=by_id[REPORT_FAMILY_IDS[5]],
                report_contract=report_contract,
                trial_observations=trial_observations,
                trial_censuses=trial_censuses,
                economic_axes=economic_axes,
                resamples=resamples,
            ),
            REPORT_FAMILY_IDS[7]: _percentile_family_rows(
                observations=decision_report_observations,
                source_view_id=view, report_contract=report_contract,
            ),
            REPORT_FAMILY_IDS[8]: _rolling_family_rows(
                result=result, source_view_id=view,
                report_contract=report_contract, fold_axes=fold_axes,
            ),
            REPORT_FAMILY_IDS[9]: _year_alpha_family_rows(
                result=result, source_view_id=view,
                report_contract=report_contract,
                economic_axes=economic_axes,
            ),
            REPORT_FAMILY_IDS[10]: _signal_decay_family_rows(
                observations=decision_report_observations,
                source_view_id=view, report_contract=report_contract,
            ),
            REPORT_FAMILY_IDS[11]: _turnover_family_rows(
                source_view_id=view,
                report_contract=report_contract,
                trial_observations=trial_observations,
                trial_censuses=trial_censuses,
            ),
            REPORT_FAMILY_IDS[12]: _drawdown_family_rows(
                result=result, source_view_id=view,
                report_contract=report_contract,
                economic_axes=economic_axes,
            ),
        }
        for family_id in REPORT_FAMILY_IDS:
            if family_id == REPORT_FAMILY_IDS[6]:
                continue
            if family_id not in builders:
                builders[family_id] = _unavailable_family_rows(
                    family_id=family_id, schema=by_id[family_id],
                    source_view_id=view, report_contract=report_contract,
                    fold_axes=fold_axes, economic_axes=economic_axes,
                )
        builders[REPORT_FAMILY_IDS[6]] = _accounting_family_rows(
            view=view,
            report_contract=report_contract, coverages=coverages,
            fold_axes=fold_axes, economic_axes=economic_axes,
            power_floor=power_floor,
            partition_counts=partition_counts[view],
            terminal_attribution=terminal_attribution[view],
            family_rows=builders,
            trial_censuses=trial_censuses,
        )
        for family_id in REPORT_FAMILY_IDS:
            rows = builders[family_id]
            families.append(_report_family_document(
                contract_sha256=contract_sha,
                source_view_id=view,
                schema=by_id[family_id], rows=rows,
                report_contract=report_contract,
            ))
        adjustments.extend(_secondary_adjustments(
            report=report, view=view,
            registry=report_contract["secondary_hypothesis_registry"],
            economic_rows=builders[REPORT_FAMILY_IDS[5]],
            subset_p_values=subset_p_values,
        ))
        trials.extend(_strategy_trial_reports(
            view=view, registry=trial_registry,
            trial_observations=trial_observations,
            trial_censuses=trial_censuses,
        ))
    binding = {
        "contract_id": report_contract["contract_id"],
        "contract_sha256": contract_sha,
        "artifact_sha256": hashlib.sha256(
            _canonical_bytes(report_contract)
        ).hexdigest(),
        "economic_execution_definition_sha256": report_contract["parents"][
            "economic_execution_definition_sha256"
        ],
        "secondary_hypothesis_registry_sha256": report_contract[
            "secondary_hypothesis_registry"
        ]["registry_sha256"],
        "deflated_sharpe_trial_registry_sha256": trial_registry[
            "registry_sha256"
        ],
        "stock_bootstrap_seed_sha256": report_contract["bootstrap"][
            "stock_FM_and_economic_seed_sha256"
        ],
        "report_family_count_per_source_view": 13,
        "secondary_hypothesis_count_per_source_view": 19,
        "strategy_trial_count_per_source_view": 6,
        "contract_record": report_contract,
    }
    common = {
        "formal_report_contract_binding": binding,
        "report_family_count": len(families),
        "secondary_hypothesis_adjustment_count": len(adjustments),
        "secondary_hypothesis_adjustments": adjustments,
        "strategy_trial_report_count": len(trials),
        "strategy_trial_reports": trials,
    }
    if not externalize_report_families:
        return ({
            **common,
            "report_family_chunks": [
                _report_family_chunk(family) for family in families
            ],
        }, ())
    if input_manifest_sha256 is None:
        raise FormalCloudEvaluationError(
            "external report-family objects require the input manifest identity"
        )
    objects = tuple(
        _report_family_object(
            family, ordinal=ordinal,
            input_manifest_sha256=input_manifest_sha256,
            report_contract=report_contract,
        )
        for ordinal, family in enumerate(families)
    )
    descriptors = [item.descriptor for item in objects]
    rules = report_contract["numeric_and_output_rules"]
    total_uncompressed = sum(
        item["uncompressed_byte_count"] for item in descriptors
    )
    total_compressed = sum(
        item["compressed_byte_count"] for item in descriptors
    )
    if (
        len(objects) != rules["report_family_object_count"]
        or total_uncompressed
        > rules["report_family_object_total_uncompressed_byte_ceiling"]
        or total_compressed
        > rules["report_family_object_total_compressed_byte_ceiling"]
    ):
        raise FormalCloudEvaluationError(
            "report-family object inventory exceeds its reviewed capacity"
        )
    return ({
        **common,
        "report_family_object_inventory_sha256": hashlib.sha256(
            _canonical_bytes(descriptors)
        ).hexdigest(),
        "report_family_object_total_uncompressed_byte_count": (
            total_uncompressed
        ),
        "report_family_object_total_compressed_byte_count": total_compressed,
        "report_family_objects": descriptors,
    }, objects)


def _execute_cloud_formal_evaluation(
    *,
    inputs: tuple[_evaluation.FormalEvaluationInput, ...],
    bindings: FormalCloudEvaluationBindings,
    terminal_census: FormalCloudTerminalCensus,
    resamples: int,
) -> bytes:
    """Shared implementation; tests use fewer resamples for equivalence speed."""

    current, censored = _validate_inputs(inputs, bindings)
    if type(terminal_census) is not FormalCloudTerminalCensus:
        raise FormalCloudEvaluationError("cloud terminal census changed type")
    terminal_census.__post_init__()
    _count(resamples, "bootstrap resamples", minimum=1)
    if resamples > BOOTSTRAP_RESAMPLES:
        raise FormalCloudEvaluationError("bootstrap resamples exceed the frozen run")
    try:
        reports = tuple(
            _evaluation._build_formal_evaluation_report(item, resamples=resamples)
            for item in (current, censored)
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError("formal evaluator refused cloud input") from exc
    fold_axis, view_axis = _axis_censuses((current, censored))
    dispositions = Counter(item.disposition.value for item in reports)
    source_view_census = [
        {
            "view_id": item.source_view_id,
            "accepted_count": len(item.rows),
            "refused_count": len(item.refusals),
            "slot_count": len(item.rows) + len(item.refusals),
            "economic_session_count": len(item.economic_sessions),
        }
        for item in (current, censored)
    ]
    return _canonical_bytes(
        {
            "schema": SCHEMA,
            "status": STATUS,
            "authority": AUTHORITY,
            "evaluation_id": EVALUATION_ID,
            "formal_cloud_evaluator_contract_sha256": (
                FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
            ),
            "bindings": bindings.to_record(),
            "bootstrap_resamples": resamples,
            "bootstrap_seed_sha256": _evaluation.BOOTSTRAP_SEED_SHA256,
            "formal_fold_ids": list(FORMAL_FOLD_IDS),
            "descriptive_fold_ids": list(DESCRIPTIVE_FOLD_IDS),
            "descriptive_slice_cannot_replace_or_rescue_formal": True,
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "source_view_reports_are_separate": True,
            "horizons": list(HORIZONS),
            "primary_horizon": 20,
            "input_bindings": [
                {
                    "source_view_id": item.source_view_id,
                    "input_id": item.input_id,
                    "input_sha256": item.input_sha256,
                }
                for item in (current, censored)
            ],
            "source_view_census": source_view_census,
            "fold_horizon_axis_count": 24,
            "fold_horizon_census": fold_axis,
            "source_view_fold_horizon_axis_count": 48,
            "source_view_fold_horizon_census": view_axis,
            "report_count": 2,
            "reports": [_report_document(item) for item in reports],
            "report_disposition_counts": dict(sorted(dispositions.items())),
            "terminal_census": terminal_census.to_record(),
            "shared_market_panel_sha256": bindings.shared_market_panel_sha256,
            "shared_market_panel_observation_count": (
                bindings.shared_market_panel_observation_count
            ),
            "failed_arm_omission_count": 0,
            "silently_omitted_slot_count": 0,
            "raw_outcome_rows_exported": False,
            "orders_placed": 0,
        }
    )


def execute_cloud_formal_evaluation(
    *,
    inputs: tuple[_evaluation.FormalEvaluationInput, ...],
    bindings: FormalCloudEvaluationBindings,
    terminal_census: FormalCloudTerminalCensus,
) -> bytes:
    """Run both views with the exact frozen 19,999-replicate evaluator."""

    return _execute_cloud_formal_evaluation(
        inputs=inputs,
        bindings=bindings,
        terminal_census=terminal_census,
        resamples=BOOTSTRAP_RESAMPLES,
    )


def _require_expanded_report_outputs(
    document: Mapping[str, object], bindings: FormalCloudEvaluationBindings,
) -> None:
    binding = _exact_object(
        document["formal_report_contract_binding"],
        (
            "contract_id", "contract_sha256", "artifact_sha256",
            "economic_execution_definition_sha256",
            "secondary_hypothesis_registry_sha256",
            "deflated_sharpe_trial_registry_sha256",
            "stock_bootstrap_seed_sha256",
            "report_family_count_per_source_view",
            "secondary_hypothesis_count_per_source_view",
            "strategy_trial_count_per_source_view",
        ),
        "aggregate formal report contract binding",
    )
    if (
        binding["contract_id"] != bindings.formal_report_contract_id
        or binding["contract_sha256"]
        != bindings.formal_report_contract_sha256
        or binding["artifact_sha256"]
        != bindings.formal_report_contract_artifact_sha256
        or binding["economic_execution_definition_sha256"]
        != bindings.economic_execution_definition_sha256
        or binding["secondary_hypothesis_registry_sha256"]
        != bindings.secondary_hypothesis_registry_sha256
        or binding["deflated_sharpe_trial_registry_sha256"]
        != bindings.deflated_sharpe_trial_registry_sha256
        or binding["stock_bootstrap_seed_sha256"]
        != bindings.stock_bootstrap_seed_sha256
        or binding["report_family_count_per_source_view"] != 13
        or binding["secondary_hypothesis_count_per_source_view"] != 19
        or binding["strategy_trial_count_per_source_view"] != 6
    ):
        raise FormalCloudEvaluationError(
            "aggregate report contract differs from exact runtime ancestry"
        )
    chunks = _exact_list(
        document["report_family_chunks"], "report-family chunks"
    )
    if document["report_family_count"] != 26 or len(chunks) != 26:
        raise FormalCloudEvaluationError("aggregate report-family census changed")
    families = [_decode_report_family_chunk(chunk) for chunk in chunks]
    expected_family_order = tuple(
        (view, family)
        for view in SOURCE_VIEW_IDS for family in REPORT_FAMILY_IDS
    )
    observed_family_order: list[tuple[str, str]] = []
    for raw in families:
        family = _exact_object(
            raw,
            (
                "schema", "formal_report_contract_sha256", "source_view_id",
                "family_schema", "status", "reasons", "row_count", "rows",
                "raw_security_event_or_market_rows_exported",
                "family_output_id", "family_output_sha256",
            ),
            "report-family output",
        )
        schema = _exact_object(
            family["family_schema"],
            (
                "family_id", "ordered_key_fields", "ordered_value_fields",
                "maximum_rows_per_source_view", "canonical_order",
                "missing_rule", "execution_rule",
                "raw_security_event_or_market_rows_permitted",
            ),
            "report-family schema",
        )
        view = _safe_id(family["source_view_id"], "report-family view")
        family_id = _safe_id(schema["family_id"], "report-family id")
        observed_family_order.append((view, family_id))
        keys = _exact_list(schema["ordered_key_fields"], "report-family keys")
        values = _exact_list(
            schema["ordered_value_fields"], "report-family values"
        )
        if (
            family["schema"] != "arv2-formal-report-family-output-v1"
            or family["formal_report_contract_sha256"]
            != binding["contract_sha256"]
            or schema["raw_security_event_or_market_rows_permitted"] is not False
            or schema["missing_rule"]
            != "retain_expected_cell_with_named_status_and_reason_never_zero_fill"
            or type(schema["maximum_rows_per_source_view"]) is not int
            or schema["maximum_rows_per_source_view"] < 1
            or not keys or not values
            or any(type(item) is not str or not item for item in (*keys, *values))
            or len(set((*keys, *values))) != len((*keys, *values))
            or family["raw_security_event_or_market_rows_exported"] is not False
        ):
            raise FormalCloudEvaluationError("report-family contract changed")
        rows = _exact_list(family["rows"], "report-family rows")
        reasons = _exact_list(family["reasons"], "report-family reasons")
        if (
            family["row_count"] != len(rows)
            or len(rows) > schema["maximum_rows_per_source_view"]
            or rows != sorted(rows, key=_canonical_bytes)
            or (
                family["status"] == "EMITTED"
                and (not rows or reasons)
            )
            or (
                family["status"] == "NAMED_UNAVAILABLE"
                and (rows or not reasons)
            )
            or family["status"] not in {"EMITTED", "NAMED_UNAVAILABLE"}
        ):
            raise FormalCloudEvaluationError(
                "report-family availability is not explicit and exhaustive"
            )
        fields = set((*keys, *values))
        if any(
            type(row) is not dict
            or set(row) != fields
            or row.get("source_view_id") != view
            for row in rows
        ):
            raise FormalCloudEvaluationError("report-family cell fields changed")
        seed = {
            key: value for key, value in family.items()
            if key not in {"family_output_id", "family_output_sha256"}
        }
        digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
        if (
            family["family_output_sha256"] != digest
            or family["family_output_id"]
            != f"arv2-formal-report-family-output-{digest[:24]}"
        ):
            raise FormalCloudEvaluationError(
                "report-family output identity changed"
            )
    if tuple(observed_family_order) != expected_family_order:
        raise FormalCloudEvaluationError(
            "report-family outputs are omitted or reordered"
        )

    adjustments = _exact_list(
        document["secondary_hypothesis_adjustments"],
        "secondary hypothesis adjustments",
    )
    if (
        document["secondary_hypothesis_adjustment_count"] != 38
        or len(adjustments) != 38
    ):
        raise FormalCloudEvaluationError("secondary BH census changed")
    hypothesis_ids = (
        "secondary_fm_bullish_h1", "secondary_fm_bullish_h5",
        "secondary_fm_bullish_h60", "secondary_fm_bearish_h1",
        "secondary_fm_bearish_h5", "secondary_fm_bearish_h20",
        "secondary_fm_bearish_h60",
        "secondary_fm_bullish_h20_cohort_exact_earnings_day",
        "secondary_fm_bullish_h20_cohort_one_to_two_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_three_to_five_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_over_five_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_pre_earnings",
        "secondary_fm_bullish_h20_earnings_exclusion_pm2",
        "secondary_fm_bullish_h20_earnings_exclusion_pm5",
        "secondary_economic_direct_stock_inverse_volatility_cost10",
        "secondary_economic_direct_stock_score_weight_cost10",
        "secondary_economic_direct_stock_equal_weight_cost0",
        "secondary_economic_direct_stock_equal_weight_cost5",
        "secondary_economic_direct_stock_equal_weight_cost20",
    )
    adjustment_fields = {
        "source_view_id", "hypothesis_id", "registry_ordinal",
        "p_value_status", "p_value_numerator", "p_value_denominator",
        "rank", "raw_adjusted_numerator", "raw_adjusted_denominator",
        "q_value_numerator", "q_value_denominator",
        "rejected_at_q_lte_0_05", "reasons",
    }
    for view_index, view in enumerate(SOURCE_VIEW_IDS):
        rows = adjustments[view_index * 19:(view_index + 1) * 19]
        if tuple(row.get("hypothesis_id") for row in rows) != hypothesis_ids:
            raise FormalCloudEvaluationError(
                "secondary hypothesis registry slots changed"
            )
        ranked_values: list[tuple[Fraction, int]] = []
        for ordinal, row in enumerate(rows):
            if type(row) is not dict or set(row) != adjustment_fields:
                raise FormalCloudEvaluationError("secondary BH row fields changed")
            if (
                row["source_view_id"] != view
                or row["registry_ordinal"] != ordinal
                or row["p_value_status"] != "NAMED_UNAVAILABLE"
                or row["p_value_numerator"] != 1
                or row["p_value_denominator"] != 1
                or row["reasons"]
                != ["registered_hypothesis_p_value_named_unavailable"]
            ):
                raise FormalCloudEvaluationError(
                    "secondary unavailable p-value slot changed"
                )
            p_value = Fraction(
                row["p_value_numerator"], row["p_value_denominator"]
            )
            ranked_values.append((p_value, ordinal))
        order = sorted(ranked_values)
        raw_values = [
            min(Fraction(1), 19 * item[0] / rank)
            for rank, item in enumerate(order, 1)
        ]
        q_values = list(raw_values)
        for index in range(17, -1, -1):
            q_values[index] = min(q_values[index], q_values[index + 1])
        expected = {
            ordinal: (rank, raw, q)
            for rank, ((_, ordinal), raw, q) in enumerate(
                zip(order, raw_values, q_values, strict=True), 1
            )
        }
        for row in rows:
            rank, raw, q_value = expected[row["registry_ordinal"]]
            if (
                row["rank"] != rank
                or (row["raw_adjusted_numerator"], row["raw_adjusted_denominator"])
                != (raw.numerator, raw.denominator)
                or (row["q_value_numerator"], row["q_value_denominator"])
                != (q_value.numerator, q_value.denominator)
                or row["rejected_at_q_lte_0_05"]
                is not (q_value <= Fraction(1, 20))
            ):
                raise FormalCloudEvaluationError(
                    "secondary BH arithmetic changed"
                )

    trial_rows = _exact_list(
        document["strategy_trial_reports"], "strategy trial reports"
    )
    if document["strategy_trial_report_count"] != 12 or len(trial_rows) != 12:
        raise FormalCloudEvaluationError("strategy DSR trial census changed")
    trial_ids = (
        "direct_stock_equal_weight_cost0",
        "direct_stock_equal_weight_cost5",
        "direct_stock_equal_weight_cost10",
        "direct_stock_equal_weight_cost20",
        "direct_stock_inverse_volatility_cost10",
        "direct_stock_score_weight_cost10",
    )
    trial_fields = {
        "source_view_id", "trial_id", "T", "daily_sharpe",
        "annualized_sharpe", "skewness", "kurtosis",
        "trial_sharpe_variance", "expected_maximum_sharpe",
        "deflated_sharpe_z", "deflated_sharpe_probability",
        "status", "reasons",
    }
    for view_index, view in enumerate(SOURCE_VIEW_IDS):
        rows = trial_rows[view_index * 6:(view_index + 1) * 6]
        if tuple(row.get("trial_id") for row in rows) != trial_ids:
            raise FormalCloudEvaluationError("strategy trial registry slots changed")
        for row in rows:
            if (
                type(row) is not dict or set(row) != trial_fields
                or row["source_view_id"] != view
                or row["status"] != "NAMED_UNAVAILABLE"
                or row["reasons"]
                != ["six_trial_common_daily_series_not_retained"]
                or any(
                    row[name] is not None for name in trial_fields
                    - {"source_view_id", "trial_id", "status", "reasons"}
                )
            ):
                raise FormalCloudEvaluationError(
                    "strategy DSR unavailable trial changed"
                )


def _require_expanded_report_outputs_v2(
    document: Mapping[str, object], bindings: FormalCloudEvaluationBindings,
    *,
    report_family_object_payloads: Mapping[str, bytes] | None = None,
) -> None:
    binding = _exact_object(
        document["formal_report_contract_binding"],
        (
            "contract_id", "contract_sha256", "artifact_sha256",
            "economic_execution_definition_sha256",
            "secondary_hypothesis_registry_sha256",
            "deflated_sharpe_trial_registry_sha256",
            "stock_bootstrap_seed_sha256",
            "report_family_count_per_source_view",
            "secondary_hypothesis_count_per_source_view",
            "strategy_trial_count_per_source_view", "contract_record",
        ),
        "aggregate formal report contract binding",
    )
    contract = binding["contract_record"]
    if type(contract) is not dict:
        raise FormalCloudEvaluationError("report contract record changed type")
    artifact_sha256 = hashlib.sha256(_canonical_bytes(contract)).hexdigest()
    if (
        binding["contract_id"] != bindings.formal_report_contract_id
        or binding["contract_sha256"]
        != bindings.formal_report_contract_sha256
        or binding["artifact_sha256"]
        != bindings.formal_report_contract_artifact_sha256
        or artifact_sha256 != binding["artifact_sha256"]
        or contract.get("contract_id") != binding["contract_id"]
        or contract.get("contract_sha256") != binding["contract_sha256"]
        or binding["economic_execution_definition_sha256"]
        != bindings.economic_execution_definition_sha256
        or contract.get("parents", {}).get(
            "economic_execution_definition_sha256"
        ) != binding["economic_execution_definition_sha256"]
        or binding["secondary_hypothesis_registry_sha256"]
        != bindings.secondary_hypothesis_registry_sha256
        or contract.get("secondary_hypothesis_registry", {}).get(
            "registry_sha256"
        ) != binding["secondary_hypothesis_registry_sha256"]
        or binding["deflated_sharpe_trial_registry_sha256"]
        != bindings.deflated_sharpe_trial_registry_sha256
        or contract.get("strategy_trial_registry", {}).get(
            "registry_sha256"
        ) != binding["deflated_sharpe_trial_registry_sha256"]
        or binding["stock_bootstrap_seed_sha256"]
        != bindings.stock_bootstrap_seed_sha256
        or contract.get("bootstrap", {}).get(
            "stock_FM_and_economic_seed_sha256"
        ) != binding["stock_bootstrap_seed_sha256"]
        or binding["stock_bootstrap_seed_sha256"]
        != _evaluation.STOCK_BOOTSTRAP_SEED_SHA256
        or binding["report_family_count_per_source_view"] != 13
        or binding["secondary_hypothesis_count_per_source_view"] != 19
        or binding["strategy_trial_count_per_source_view"] != 6
        or tuple(contract.get("required_report_family_ids", ()))
        != REPORT_FAMILY_IDS
    ):
        raise FormalCloudEvaluationError(
            "aggregate report contract differs from exact runtime ancestry"
        )
    schemas = contract.get("report_schemas")
    if type(schemas) is not list or len(schemas) != 13:
        raise FormalCloudEvaluationError("report schema census changed")
    schema_by_id = {
        item.get("family_id"): item for item in schemas
        if type(item) is dict
    }
    if tuple(schema_by_id) != REPORT_FAMILY_IDS:
        raise FormalCloudEvaluationError("report schema order changed")

    expected_family_order = tuple(
        (view, family_id)
        for view in SOURCE_VIEW_IDS for family_id in REPORT_FAMILY_IDS
    )
    if "report_family_chunks" in document:
        chunks = _exact_list(
            document["report_family_chunks"], "report-family chunks"
        )
        if report_family_object_payloads is not None:
            raise FormalCloudEvaluationError(
                "legacy embedded report gained external family objects"
            )
        if document["report_family_count"] != 26 or len(chunks) != 26:
            raise FormalCloudEvaluationError(
                "aggregate report-family census changed"
            )
        families = [_decode_report_family_chunk(chunk) for chunk in chunks]
    else:
        references = _exact_list(
            document["report_family_objects"], "report-family object references"
        )
        rules = contract.get("numeric_and_output_rules")
        if type(rules) is not dict:
            raise FormalCloudEvaluationError("report output rules changed type")
        if (
            document["report_family_count"]
            != rules.get("report_family_object_count")
            or len(references) != 26
            or type(report_family_object_payloads) is not dict
        ):
            raise FormalCloudEvaluationError(
                "external report-family object census changed"
            )
        observed_suffixes = [
            reference.get("object_store_key_suffix")
            if type(reference) is dict else None
            for reference in references
        ]
        if (
            len(set(observed_suffixes)) != len(observed_suffixes)
            or set(report_family_object_payloads) != set(observed_suffixes)
            or document["report_family_object_inventory_sha256"]
            != hashlib.sha256(_canonical_bytes(references)).hexdigest()
            or document["report_family_object_total_uncompressed_byte_count"]
            != sum(
                reference.get("uncompressed_byte_count", -1)
                for reference in references
                if type(reference) is dict
            )
            or document["report_family_object_total_compressed_byte_count"]
            != sum(
                reference.get("compressed_byte_count", -1)
                for reference in references
                if type(reference) is dict
            )
            or document["report_family_object_total_uncompressed_byte_count"]
            > rules.get(
                "report_family_object_total_uncompressed_byte_ceiling", -1
            )
            or document["report_family_object_total_compressed_byte_count"]
            > rules.get(
                "report_family_object_total_compressed_byte_ceiling", -1
            )
        ):
            raise FormalCloudEvaluationError(
                "external report-family object inventory changed"
            )
        families = []
        for ordinal, (reference, expected) in enumerate(
            zip(references, expected_family_order, strict=True)
        ):
            if (
                type(reference) is not dict
                or reference.get("ordinal") != ordinal
                or (
                    reference.get("source_view_id"),
                    reference.get("family_id"),
                ) != expected
            ):
                raise FormalCloudEvaluationError(
                    "external report-family objects are reordered"
                )
            suffix = reference["object_store_key_suffix"]
            families.append(_decode_report_family_object(
                reference,
                report_family_object_payloads[suffix],
                report_contract=contract,
                input_manifest_sha256=bindings.input_manifest_sha256,
            ))
    decoded: dict[tuple[str, str], list[dict[str, object]]] = {}
    family_documents: dict[tuple[str, str], dict[str, object]] = {}
    observed_family_order: list[tuple[str, str]] = []
    for raw in families:
        family = _exact_object(
            raw,
            (
                "schema", "formal_report_contract_sha256", "source_view_id",
                "family_schema", "row_count", "rows",
                "raw_security_event_or_market_rows_exported",
                "family_output_id", "family_output_sha256",
            ),
            "report-family output",
        )
        schema = family["family_schema"]
        if type(schema) is not dict:
            raise FormalCloudEvaluationError("report-family schema changed type")
        family_id = schema.get("family_id")
        view = family["source_view_id"]
        if (
            view not in SOURCE_VIEW_IDS or family_id not in REPORT_FAMILY_IDS
            or schema != schema_by_id[family_id]
            or family["schema"] != "arv2-formal-report-family-output-v1"
            or family["formal_report_contract_sha256"]
            != binding["contract_sha256"]
            or family["raw_security_event_or_market_rows_exported"] is not False
        ):
            raise FormalCloudEvaluationError("report-family contract changed")
        observed_family_order.append((view, family_id))
        keys = tuple(schema["ordered_key_fields"])
        values = tuple(schema["ordered_value_fields"])
        fields = (*keys, *values)
        rows = _exact_list(family["rows"], "report-family rows")
        if (
            family["row_count"] != len(rows) or not rows
            or len(rows) > schema["maximum_rows_per_source_view"]
        ):
            raise FormalCloudEvaluationError("report-family row census changed")
        decoded_rows: list[dict[str, object]] = []
        order: list[tuple[object, ...]] = []
        key_census: set[tuple[object, ...]] = set()
        for cells in rows:
            if type(cells) is not list or len(cells) != len(fields):
                raise FormalCloudEvaluationError(
                    "report-family row is not an aligned cell array"
                )
            if any(len(_canonical_bytes(cell)) > 8_192 for cell in cells):
                raise FormalCloudEvaluationError(
                    "report-family cell exceeds the authenticated byte ceiling"
                )
            row = dict(zip(fields, cells, strict=True))
            key = tuple(row[name] for name in keys)
            try:
                if key in key_census:
                    raise FormalCloudEvaluationError(
                        "report-family duplicated a cell"
                    )
                key_census.add(key)
            except TypeError as exc:
                raise FormalCloudEvaluationError(
                    "report-family key cell is not scalar"
                ) from exc
            if row.get("source_view_id") != view:
                raise FormalCloudEvaluationError(
                    "report-family cell escaped its source view"
                )
            status = row.get("status")
            reasons = row.get("reasons")
            if (
                status not in {
                    "AVAILABLE", "UNAVAILABLE", "REFUSED",
                    "INCONCLUSIVE", "INVALID_DATA",
                }
                or type(reasons) is not list
                or any(
                    type(reason) is not str
                    or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", reason) is None
                    for reason in reasons
                )
                or (status == "AVAILABLE" and reasons)
                or (status != "AVAILABLE" and not reasons)
            ):
                raise FormalCloudEvaluationError(
                    "report-family availability cell changed"
                )
            decoded_rows.append(row)
            order.append(_report_family_order_key(row, schema, contract))
        if any(
            order[index - 1] >= order[index]
            for index in range(1, len(order))
        ):
            raise FormalCloudEvaluationError(
                "report-family rows changed frozen dimension order"
            )
        seed = {
            key: value for key, value in family.items()
            if key not in {"family_output_id", "family_output_sha256"}
        }
        digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
        if (
            family["family_output_sha256"] != digest
            or family["family_output_id"]
            != f"arv2-formal-report-family-output-{digest[:24]}"
        ):
            raise FormalCloudEvaluationError(
                "report-family output identity changed"
            )
        decoded[(view, family_id)] = decoded_rows
        family_documents[(view, family_id)] = family
    if tuple(observed_family_order) != expected_family_order:
        raise FormalCloudEvaluationError(
            "report-family outputs are omitted or reordered"
        )

    reports = document["reports"]
    if type(reports) is not list or len(reports) != 2:
        raise FormalCloudEvaluationError("report reconciliation parents changed")
    supported = (REPORT_FAMILY_IDS[2], REPORT_FAMILY_IDS[3])
    for report, view in zip(reports, SOURCE_VIEW_IDS, strict=True):
        expected_rows = {
            REPORT_FAMILY_IDS[2]: _ic_family_rows(report, view),
            REPORT_FAMILY_IDS[3]: _fm_family_rows(report, view),
        }
        for family_id in supported:
            expected = _report_family_document(
                contract_sha256=binding["contract_sha256"],
                source_view_id=view, schema=schema_by_id[family_id],
                rows=expected_rows[family_id], report_contract=contract,
            )
            if family_documents[(view, family_id)] != expected:
                raise FormalCloudEvaluationError(
                    "report-family cells do not reconcile to authenticated summary"
                )
        paired = [
            row for row in decoded[(view, REPORT_FAMILY_IDS[4])]
            if row["record_kind"] == "paired_information_coefficient"
        ]
        expected_paired = _paired_coverage_family_rows(report, view, ())
        expected_paired = [
            {
                key: _report_wire_cell(value) for key, value in row.items()
            }
            for row in expected_paired
        ]
        expected_paired.sort(key=lambda row: _report_family_order_key(
            row, schema_by_id[REPORT_FAMILY_IDS[4]], contract
        ))
        if paired != expected_paired:
            raise FormalCloudEvaluationError(
                "paired report cells do not reconcile to authenticated summary"
            )
        coverage = [
            row for row in decoded[(view, REPORT_FAMILY_IDS[4])]
            if row["record_kind"] == "preoutcome_coverage_ledger"
        ]
        expected_coverage_keys = tuple(
            (fold, ledger)
            for fold in (*FORMAL_FOLD_IDS, "POOLED")
            for ledger in GLOBAL_COMPARATOR_LEDGER_IDS
        )
        if tuple(
            (row["fold_id"], row["record_id"]) for row in coverage
        ) != expected_coverage_keys:
            raise FormalCloudEvaluationError(
                "all fold and pooled coverage ledgers are not reported"
            )
        for row in coverage:
            if (
                row["slice_id"] != _evaluation.FORMAL_SLICE_ID
                or row["status"] != "AVAILABLE"
                or type(row["numerator"]) is not int
                or type(row["denominator"]) is not int
                or row["denominator"] <= 0
                or row["passes_19_of_20"] is not True
                or row["numerator"] * 20 < row["denominator"] * 19
                or row["valid_date_count"] is not None
                or row["mean_firm_ic"] is not None
                or row["mean_global_ic"] is not None
                or row["observed_difference"] is not None
                or row["one_sided_q95"] is not None
                or row["one_sided_lcb95"] is not None
                or type(row["diagnostic_counts"]) is not dict
            ):
                raise FormalCloudEvaluationError(
                    "reported comparator coverage is not ready"
                )

    for view in SOURCE_VIEW_IDS:
        _require_event_and_plot_report_families(
            decoded=decoded, view=view, report_contract=contract,
        )
        report = reports[SOURCE_VIEW_IDS.index(view)]
        _require_economic_report_family(
            rows=decoded[(view, REPORT_FAMILY_IDS[5])], report=report,
            view=view, report_contract=contract,
            schema=schema_by_id[REPORT_FAMILY_IDS[5]],
        )
        _require_dated_report_families(
            decoded=decoded, view=view, report_contract=contract,
        )
        _require_accounting_report_family(
            document=document, decoded=decoded, view=view,
            report_contract=contract,
        )

    lifecycle_terminal_count = sum(
        row["terminal_count"]
        for view in SOURCE_VIEW_IDS
        for row in decoded[(view, REPORT_FAMILY_IDS[6])]
        if row["accounting_kind"] == "lifecycle_terminal_disposition"
        and row["slice_id"] == _evaluation.FORMAL_SLICE_ID
        and row["fold_id"] != "POOLED"
    )
    if lifecycle_terminal_count != document["terminal_census"][
        "terminal_requirement_count"
    ]:
        raise FormalCloudEvaluationError(
            "F6 lifecycle accounting differs from terminal census"
        )

    adjustments = _exact_list(
        document["secondary_hypothesis_adjustments"],
        "secondary hypothesis adjustments",
    )
    expected_adjustments: list[dict[str, object]] = []
    for report, view in zip(reports, SOURCE_VIEW_IDS, strict=True):
        supplied_for_view = tuple(
            item for item in adjustments if item.get("source_view_id") == view
        )
        subset_p_values = {
            item["hypothesis_id"]: (
                Fraction(
                    item["p_value_numerator"], item["p_value_denominator"]
                )
                if item.get("p_value_status") == "AVAILABLE" else None
            )
            for item in supplied_for_view
            if item.get("hypothesis_id") in {
                hypothesis["hypothesis_id"]
                for hypothesis in contract["secondary_hypothesis_registry"][
                    "ordered_hypotheses"
                ]
                if hypothesis["cohort_id"] != "all"
                or hypothesis["earnings_exclusion_id"] != "none"
            }
        }
        expected_adjustments.extend(_secondary_adjustments(
            report=report, view=view,
            registry=contract["secondary_hypothesis_registry"],
            economic_rows=decoded[(view, REPORT_FAMILY_IDS[5])],
            subset_p_values=subset_p_values,
        ))
    if (
        document["secondary_hypothesis_adjustment_count"] != 38
        or adjustments != expected_adjustments
    ):
        raise FormalCloudEvaluationError(
            "secondary BH outputs do not reconcile exactly"
        )
    trial_rows = _exact_list(
        document["strategy_trial_reports"], "strategy trial reports"
    )
    _require_strategy_trial_reports(
        rows=trial_rows, registry=contract["strategy_trial_registry"]
    )
    if document["strategy_trial_report_count"] != 12:
        raise FormalCloudEvaluationError("strategy DSR trial census changed")


def derive_formal_cloud_evaluation_family_object_read_plan(
    root_manifest: bytes,
    *,
    expected_preknown_bindings: Mapping[str, object],
) -> tuple[
    FormalCloudEvaluationBindings,
    tuple[FormalCloudReportFamilyObjectDescriptor, ...],
]:
    """Authenticate preknown ancestry and derive QC-learned panel bindings."""

    preknown = _exact_object(
        expected_preknown_bindings,
        _STREAMED_FORMAL_PREKNOWN_BINDING_FIELDS,
        "expected streamed preknown bindings",
    )
    if preknown["schema"] != STREAMED_FORMAL_PREKNOWN_BINDINGS_SCHEMA:
        raise FormalCloudEvaluationError(
            "expected streamed preknown binding schema changed"
        )
    document = _strict_aggregate_object(root_manifest)
    embedded = document.get("streamed_preknown_bindings")
    if (
        type(embedded) is not dict
        or set(embedded) != set(_STREAMED_FORMAL_PREKNOWN_BINDING_FIELDS)
        or _canonical_bytes(embedded) != _canonical_bytes(preknown)
    ):
        raise FormalCloudEvaluationError(
            "formal result root preknown bindings differ from submission ancestry"
        )
    try:
        bindings = FormalCloudEvaluationBindings(**document["bindings"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError(
            "formal result root full bindings changed"
        ) from exc
    mapped = {
        "input_manifest_sha256": bindings.input_manifest_sha256,
        "production_scoring_census_sha256": (
            bindings.production_scoring_census_sha256
        ),
        "evaluation_input_bundle_id": bindings.evaluation_input_bundle_id,
        "evaluation_input_bundle_sha256": (
            bindings.evaluation_input_bundle_sha256
        ),
        "terminal_disposition_package_sha256": (
            bindings.terminal_disposition_package_sha256
        ),
        "formal_evaluator_source_sha256": (
            bindings.formal_evaluator_source_sha256
        ),
        "evaluator_source_closure_sha256": (
            bindings.evaluator_source_closure_sha256
        ),
        "execution_plan_sha256": bindings.execution_plan_sha256,
        "capacity_plan_sha256": bindings.capacity_plan_sha256,
        "formal_contract_sha256": bindings.formal_contract_sha256,
        "economic_execution_binding_id": (
            bindings.economic_execution_binding_id
        ),
        "economic_execution_binding_sha256": (
            bindings.economic_execution_binding_sha256
        ),
        "economic_execution_definition_id": (
            bindings.economic_execution_definition_id
        ),
        "economic_execution_definition_sha256": (
            bindings.economic_execution_definition_sha256
        ),
        "economic_h20_terminal_liquidation_session": (
            bindings.economic_h20_terminal_liquidation_session
        ),
        "formal_report_contract_id": bindings.formal_report_contract_id,
        "formal_report_contract_sha256": (
            bindings.formal_report_contract_sha256
        ),
        "formal_report_contract_artifact_sha256": (
            bindings.formal_report_contract_artifact_sha256
        ),
        "secondary_hypothesis_registry_sha256": (
            bindings.secondary_hypothesis_registry_sha256
        ),
        "deflated_sharpe_trial_registry_sha256": (
            bindings.deflated_sharpe_trial_registry_sha256
        ),
        "stock_bootstrap_seed_sha256": bindings.stock_bootstrap_seed_sha256,
    }
    if any(preknown[name] != value for name, value in mapped.items()):
        raise FormalCloudEvaluationError(
            "formal result root non-QC bindings changed"
        )
    _sha(bindings.shared_market_panel_sha256, "QC-derived market-panel hash")
    _count(
        bindings.shared_market_panel_observation_count,
        "QC-derived market-panel observation count", minimum=1,
    )
    return bindings, formal_cloud_evaluation_family_object_read_plan(
        root_manifest, expected_bindings=bindings
    )


def formal_cloud_evaluation_family_object_read_plan(
    root_manifest: bytes,
    *,
    expected_bindings: FormalCloudEvaluationBindings,
) -> tuple[FormalCloudReportFamilyObjectDescriptor, ...]:
    """Derive the only 26 Object Store suffixes a signed run may read.

    This validates the authenticated root and all pre-known lineage before any
    result-family object is opened.  Full family semantics are validated only
    after all 26 exact payloads have been reopened and supplied to
    :func:`require_formal_cloud_evaluation_aggregate_bytes`.
    """

    if type(expected_bindings) is not FormalCloudEvaluationBindings:
        raise FormalCloudEvaluationError("expected bindings changed type")
    expected_bindings.__post_init__()
    if len(root_manifest) > 4_194_304:
        raise FormalCloudEvaluationError(
            "formal result root exceeds its absolute decompressed bound"
        )
    document = _strict_aggregate_object(root_manifest)
    if set(document) != set(_STREAMED_REPORT_ROOT_FIELDS):
        raise FormalCloudEvaluationError(
            "formal result root manifest fields changed"
        )
    if (
        document.get("schema") != SCHEMA
        or document.get("status") != STATUS
        or document.get("authority") != AUTHORITY
        or document.get("evaluation_id") != EVALUATION_ID
        or document.get("formal_cloud_evaluator_contract_sha256")
        != FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
        or document.get("bindings") != expected_bindings.to_record()
        or document.get("raw_outcome_rows_exported") is not False
        or document.get("orders_placed") != 0
    ):
        raise FormalCloudEvaluationError(
            "formal result root lineage or authority changed"
        )
    binding = document.get("formal_report_contract_binding")
    if type(binding) is not dict or set(binding) != {
        "contract_id", "contract_sha256", "artifact_sha256",
        "economic_execution_definition_sha256",
        "secondary_hypothesis_registry_sha256",
        "deflated_sharpe_trial_registry_sha256",
        "stock_bootstrap_seed_sha256",
        "report_family_count_per_source_view",
        "secondary_hypothesis_count_per_source_view",
        "strategy_trial_count_per_source_view", "contract_record",
    }:
        raise FormalCloudEvaluationError(
            "formal result root report binding fields changed"
        )
    contract = binding["contract_record"]
    if (
        type(contract) is not dict
        or hashlib.sha256(_canonical_bytes(contract)).hexdigest()
        != binding["artifact_sha256"]
        or binding["contract_id"] != expected_bindings.formal_report_contract_id
        or binding["contract_sha256"]
        != expected_bindings.formal_report_contract_sha256
        or binding["artifact_sha256"]
        != expected_bindings.formal_report_contract_artifact_sha256
        or binding["economic_execution_definition_sha256"]
        != expected_bindings.economic_execution_definition_sha256
        or binding["secondary_hypothesis_registry_sha256"]
        != expected_bindings.secondary_hypothesis_registry_sha256
        or binding["deflated_sharpe_trial_registry_sha256"]
        != expected_bindings.deflated_sharpe_trial_registry_sha256
        or binding["stock_bootstrap_seed_sha256"]
        != expected_bindings.stock_bootstrap_seed_sha256
    ):
        raise FormalCloudEvaluationError(
            "formal result root report ancestry changed"
        )
    rules = contract.get("numeric_and_output_rules")
    references = document.get("report_family_objects")
    if type(rules) is not dict or type(references) is not list:
        raise FormalCloudEvaluationError(
            "formal result root object inventory changed type"
        )
    if (
        rules.get("summary_root_decompressed_byte_ceiling") != 4_194_304
        or rules.get("summary_root_compressed_byte_ceiling") != 200_000
        or len(root_manifest) > rules["summary_root_decompressed_byte_ceiling"]
    ):
        raise FormalCloudEvaluationError(
            "formal result root capacity contract changed"
        )
    compressed_root = bytearray(
        gzip.compress(root_manifest, compresslevel=9, mtime=0)
    )
    compressed_root[9] = 255
    if len(compressed_root) > rules["summary_root_compressed_byte_ceiling"]:
        raise FormalCloudEvaluationError(
            "formal result root exceeds its reviewed summary bound"
        )
    if (
        document.get("report_family_count") != 26
        or rules.get("report_family_object_count") != 26
        or len(references) != 26
        or document.get("report_family_object_inventory_sha256")
        != hashlib.sha256(_canonical_bytes(references)).hexdigest()
    ):
        raise FormalCloudEvaluationError(
            "formal result root object census changed"
        )
    expected_order = tuple(
        (view, family_id)
        for view in SOURCE_VIEW_IDS for family_id in REPORT_FAMILY_IDS
    )
    descriptors: list[FormalCloudReportFamilyObjectDescriptor] = []
    suffixes: set[str] = set()
    total_uncompressed = 0
    total_compressed = 0
    descriptor_fields = {
        field.name
        for field in dataclasses.fields(FormalCloudReportFamilyObjectDescriptor)
    }
    for ordinal, (raw, expected) in enumerate(
        zip(references, expected_order, strict=True)
    ):
        if type(raw) is not dict or set(raw) != descriptor_fields:
            raise FormalCloudEvaluationError(
                "formal result family-object descriptor fields changed"
            )
        if (
            raw["schema"] != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
            or raw["role"] != "formal_report_family"
            or raw["ordinal"] != ordinal
            or (raw["source_view_id"], raw["family_id"]) != expected
            or raw["payload_schema"]
            != "arv2-formal-report-family-output-v1"
            or raw["formal_cloud_evaluator_contract_sha256"]
            != FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
            or raw["input_manifest_sha256"]
            != expected_bindings.input_manifest_sha256
            or raw["formal_report_contract_sha256"]
            != expected_bindings.formal_report_contract_sha256
            or type(raw["row_count"]) is not int
            or raw["row_count"] < 1
        ):
            raise FormalCloudEvaluationError(
                "formal result family-object descriptor lineage changed"
            )
        uncompressed_cap, compressed_cap = _report_family_object_capacity(
            contract, raw["family_id"]
        )
        for name in (
            "family_output_id", "object_store_key_suffix",
        ):
            _safe_id(raw[name], f"family-object {name}")
        for name in (
            "family_output_sha256", "uncompressed_sha256",
            "compressed_sha256",
        ):
            _sha(raw[name], f"family-object {name}")
        if (
            type(raw["uncompressed_byte_count"]) is not int
            or not 0 < raw["uncompressed_byte_count"] <= uncompressed_cap
            or type(raw["compressed_byte_count"]) is not int
            or not 0 < raw["compressed_byte_count"] <= compressed_cap
            or raw["encoding"] != REPORT_FAMILY_CHUNK_ENCODING
            or raw["object_store_key_suffix"]
            != (
                REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
                + expected_bindings.input_manifest_sha256
                + "/"
                + str(ordinal).zfill(2)
                + "-"
                + raw["compressed_sha256"]
                + "-json.gz"
            )
            or raw["object_store_key_suffix"] in suffixes
        ):
            raise FormalCloudEvaluationError(
                "formal result family-object capacity or key changed"
            )
        suffixes.add(raw["object_store_key_suffix"])
        total_uncompressed += raw["uncompressed_byte_count"]
        total_compressed += raw["compressed_byte_count"]
        descriptors.append(FormalCloudReportFamilyObjectDescriptor(**raw))
    if (
        document.get("report_family_object_total_uncompressed_byte_count")
        != total_uncompressed
        or document.get("report_family_object_total_compressed_byte_count")
        != total_compressed
        or total_uncompressed
        > rules.get(
            "report_family_object_total_uncompressed_byte_ceiling", -1
        )
        or total_compressed
        > rules.get("report_family_object_total_compressed_byte_ceiling", -1)
    ):
        raise FormalCloudEvaluationError(
            "formal result family-object total capacity changed"
        )
    return tuple(descriptors)


def require_formal_cloud_evaluation_family_object_payload(
    root_manifest: bytes,
    *,
    expected_bindings: FormalCloudEvaluationBindings,
    descriptor: FormalCloudReportFamilyObjectDescriptor,
    payload: bytes,
) -> FormalCloudReportFamilyObjectDescriptor:
    """Validate one planned family object without exporting its outcome rows.

    The caller must still provide all 26 exact payloads to
    :func:`require_formal_cloud_evaluation_aggregate_bytes` before any final
    result authority can be minted.  This narrow seam exists so a host adapter
    can authenticate each bounded Object Store read as it occurs without
    reconstructing gzip, schema, ordering, or lineage policy.
    """

    if type(descriptor) is not FormalCloudReportFamilyObjectDescriptor:
        raise FormalCloudEvaluationError(
            "formal result family-object descriptor changed type"
        )
    plan = formal_cloud_evaluation_family_object_read_plan(
        root_manifest, expected_bindings=expected_bindings
    )
    if (
        descriptor.ordinal >= len(plan)
        or plan[descriptor.ordinal] != descriptor
    ):
        raise FormalCloudEvaluationError(
            "formal result family object escaped its authenticated read plan"
        )
    document = _strict_aggregate_object(root_manifest)
    contract = document["formal_report_contract_binding"]["contract_record"]
    family = _decode_report_family_object(
        descriptor.to_record(), payload,
        report_contract=contract,
        input_manifest_sha256=expected_bindings.input_manifest_sha256,
    )
    family = _exact_object(
        family,
        (
            "schema", "formal_report_contract_sha256", "source_view_id",
            "family_schema", "row_count", "rows",
            "raw_security_event_or_market_rows_exported",
            "family_output_id", "family_output_sha256",
        ),
        "report-family output",
    )
    schemas = contract.get("report_schemas")
    if type(schemas) is not list:
        raise FormalCloudEvaluationError("report schema census changed type")
    schema = next(
        (
            item for item in schemas
            if type(item) is dict
            and item.get("family_id") == descriptor.family_id
        ),
        None,
    )
    rows = family.get("rows")
    if (
        schema is None
        or family["schema"] != "arv2-formal-report-family-output-v1"
        or family["formal_report_contract_sha256"]
        != expected_bindings.formal_report_contract_sha256
        or family["source_view_id"] != descriptor.source_view_id
        or family["family_schema"] != schema
        or family["raw_security_event_or_market_rows_exported"] is not False
        or type(rows) is not list
        or not rows
        or family["row_count"] != len(rows)
        or len(rows) > schema["maximum_rows_per_source_view"]
    ):
        raise FormalCloudEvaluationError(
            "report-family object semantic envelope changed"
        )
    keys = tuple(schema["ordered_key_fields"])
    fields = (*keys, *tuple(schema["ordered_value_fields"]))
    observed_keys: set[tuple[object, ...]] = set()
    observed_order: list[tuple[object, ...]] = []
    for cells in rows:
        if (
            type(cells) is not list
            or len(cells) != len(fields)
            or len(_canonical_bytes(cells))
            > contract["numeric_and_output_rules"][
                "maximum_encoded_bytes_per_report_row"
            ]
            or any(len(_canonical_bytes(cell)) > 8_192 for cell in cells)
        ):
            raise FormalCloudEvaluationError(
                "report-family object row envelope changed"
            )
        row = dict(zip(fields, cells, strict=True))
        key = tuple(row[name] for name in keys)
        try:
            if key in observed_keys:
                raise FormalCloudEvaluationError(
                    "report-family object duplicated a cell"
                )
            observed_keys.add(key)
        except TypeError as exc:
            raise FormalCloudEvaluationError(
                "report-family object key cell is not scalar"
            ) from exc
        observed_order.append(_report_family_order_key(row, schema, contract))
    if any(
        observed_order[index - 1] >= observed_order[index]
        for index in range(1, len(observed_order))
    ):
        raise FormalCloudEvaluationError(
            "report-family object rows changed frozen dimension order"
        )
    seed = {
        key: value for key, value in family.items()
        if key not in {"family_output_id", "family_output_sha256"}
    }
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    if (
        family["family_output_sha256"] != digest
        or family["family_output_id"]
        != f"arv2-formal-report-family-output-{digest[:24]}"
    ):
        raise FormalCloudEvaluationError(
            "report-family object output identity changed"
        )
    return descriptor


def require_formal_cloud_evaluation_aggregate_bytes(
    payload: bytes,
    *,
    expected_bindings: FormalCloudEvaluationBindings | None = None,
    expected_bootstrap_resamples: int = BOOTSTRAP_RESAMPLES,
    report_family_object_payloads: Mapping[str, bytes] | None = None,
) -> dict[str, object]:
    """Independently validate exact aggregate bytes returned through QC.

    This is content validation only.  The post-run bridge additionally needs a
    process-authenticated terminal/result-read receipt before it may mint an
    outcome authority.
    """

    document = _strict_aggregate_object(payload)
    fields = set(document)
    embedded = fields == set(_STREAMED_REPORT_AGGREGATE_FIELDS)
    external = fields == set(_STREAMED_REPORT_ROOT_FIELDS)
    expanded = embedded or external
    legacy = fields == set(_AGGREGATE_FIELDS)
    if not expanded and not legacy:
        raise FormalCloudEvaluationError("aggregate fields changed")
    if (
        document["schema"] != SCHEMA
        or document["status"] != STATUS
        or document["authority"] != AUTHORITY
        or document["evaluation_id"] != EVALUATION_ID
        or document["formal_cloud_evaluator_contract_sha256"]
        != FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256
        or document["bootstrap_resamples"] != expected_bootstrap_resamples
        or document["bootstrap_seed_sha256"]
        != _evaluation.BOOTSTRAP_SEED_SHA256
        or tuple(document["formal_fold_ids"]) != FORMAL_FOLD_IDS
        or tuple(document["descriptive_fold_ids"]) != DESCRIPTIVE_FOLD_IDS
        or document["descriptive_slice_cannot_replace_or_rescue_formal"] is not True
        or tuple(document["source_view_ids"]) != SOURCE_VIEW_IDS
        or document["source_view_reports_are_separate"] is not True
        or tuple(document["horizons"]) != HORIZONS
        or document["primary_horizon"] != 20
        or document["report_count"] != 2
        or document["failed_arm_omission_count"] != 0
        or document["silently_omitted_slot_count"] != 0
        or document["raw_outcome_rows_exported"] is not False
        or document["orders_placed"] != 0
    ):
        raise FormalCloudEvaluationError("aggregate frozen contract changed")
    if type(document["bindings"]) is not dict:
        raise FormalCloudEvaluationError("aggregate bindings changed type")
    try:
        bindings = FormalCloudEvaluationBindings(**document["bindings"])
    except (TypeError, ValueError) as exc:
        raise FormalCloudEvaluationError("aggregate bindings changed") from exc
    if expected_bindings is not None:
        if type(expected_bindings) is not FormalCloudEvaluationBindings:
            raise FormalCloudEvaluationError("expected bindings changed type")
        expected_bindings.__post_init__()
        if bindings != expected_bindings:
            raise FormalCloudEvaluationError("aggregate does not bind this exact run")
    if expanded is (bindings.formal_report_contract_id is None):
        raise FormalCloudEvaluationError(
            "aggregate report surface and streamed binding ancestry disagree"
        )
    if (
        document["shared_market_panel_sha256"]
        != bindings.shared_market_panel_sha256
        or document["shared_market_panel_observation_count"]
        != bindings.shared_market_panel_observation_count
    ):
        raise FormalCloudEvaluationError("aggregate market-panel binding changed")
    if external:
        formal_cloud_evaluation_family_object_read_plan(
            payload, expected_bindings=bindings
        )

    raw_inputs = document["input_bindings"]
    raw_views = document["source_view_census"]
    raw_reports = document["reports"]
    if not all(type(item) is list for item in (raw_inputs, raw_views, raw_reports)):
        raise FormalCloudEvaluationError("aggregate source-view containers changed")
    if len(raw_inputs) != 2 or len(raw_views) != 2 or len(raw_reports) != 2:
        raise FormalCloudEvaluationError("aggregate omitted a source-view arm")
    input_by_view: dict[str, dict[str, object]] = {}
    for raw in raw_inputs:
        if type(raw) is not dict or set(raw) != {
            "source_view_id", "input_id", "input_sha256"
        }:
            raise FormalCloudEvaluationError("aggregate input binding fields changed")
        view = _safe_id(raw["source_view_id"], "aggregate input view")
        _safe_id(raw["input_id"], "aggregate input id")
        _sha(raw["input_sha256"], "aggregate input hash")
        if view in input_by_view:
            raise FormalCloudEvaluationError("aggregate duplicated an input view")
        input_by_view[view] = raw
    if tuple(input_by_view) != SOURCE_VIEW_IDS:
        raise FormalCloudEvaluationError("aggregate input views are reordered")

    view_census: dict[str, dict[str, object]] = {}
    for raw in raw_views:
        if type(raw) is not dict or set(raw) != {
            "view_id", "accepted_count", "refused_count", "slot_count",
            "economic_session_count",
        }:
            raise FormalCloudEvaluationError("aggregate source-view census changed")
        view = _safe_id(raw["view_id"], "aggregate census view")
        for name in (
            "accepted_count", "refused_count", "slot_count",
            "economic_session_count",
        ):
            _count(raw[name], name)
        if raw["accepted_count"] + raw["refused_count"] != raw["slot_count"]:
            raise FormalCloudEvaluationError("aggregate view census is not exhaustive")
        if view in view_census:
            raise FormalCloudEvaluationError("aggregate duplicated a view census")
        view_census[view] = raw
    if tuple(view_census) != SOURCE_VIEW_IDS:
        raise FormalCloudEvaluationError("aggregate view census is reordered")

    view_axes = document["source_view_fold_horizon_census"]
    fold_axes = document["fold_horizon_census"]
    if (
        type(view_axes) is not list
        or type(fold_axes) is not list
        or document["source_view_fold_horizon_axis_count"] != 48
        or len(view_axes) != 48
        or document["fold_horizon_axis_count"] != 24
        or len(fold_axes) != 24
    ):
        raise FormalCloudEvaluationError("aggregate lacks all 24/48 axes")
    expected_view_axes = tuple(
        (view, fold, horizon)
        for view in SOURCE_VIEW_IDS
        for fold in FORMAL_FOLD_IDS
        for horizon in HORIZONS
    )
    observed_view_axes: list[tuple[str, str, int]] = []
    view_totals = Counter()
    fold_totals = Counter()
    for raw in view_axes:
        if type(raw) is not dict or set(raw) != {
            "view_id", "fold_id", "horizon", "accepted_count",
            "refused_count", "slot_count",
        }:
            raise FormalCloudEvaluationError("aggregate view-axis fields changed")
        key = (
            _safe_id(raw["view_id"], "view-axis view"),
            _safe_id(raw["fold_id"], "view-axis fold"),
            raw["horizon"],
        )
        if type(key[2]) is not int:
            raise FormalCloudEvaluationError("view-axis horizon changed type")
        observed_view_axes.append(key)
        for name in ("accepted_count", "refused_count", "slot_count"):
            _count(raw[name], name)
        if raw["accepted_count"] + raw["refused_count"] != raw["slot_count"]:
            raise FormalCloudEvaluationError("view-axis census is not exhaustive")
        view_totals[(key[0], "accepted")] += raw["accepted_count"]
        view_totals[(key[0], "refused")] += raw["refused_count"]
        fold_totals[(key[1], key[2], "accepted")] += raw["accepted_count"]
        fold_totals[(key[1], key[2], "refused")] += raw["refused_count"]
    if tuple(observed_view_axes) != expected_view_axes:
        raise FormalCloudEvaluationError("aggregate 48 axes are incomplete or reordered")
    expected_fold_axes = tuple(
        (fold, horizon) for fold in FORMAL_FOLD_IDS for horizon in HORIZONS
    )
    observed_fold_axes: list[tuple[str, int]] = []
    for raw in fold_axes:
        if type(raw) is not dict or set(raw) != {
            "fold_id", "horizon", "accepted_count", "refused_count", "slot_count"
        }:
            raise FormalCloudEvaluationError("aggregate fold-axis fields changed")
        key = (_safe_id(raw["fold_id"], "fold-axis fold"), raw["horizon"])
        if type(key[1]) is not int:
            raise FormalCloudEvaluationError("fold-axis horizon changed type")
        observed_fold_axes.append(key)
        accepted = fold_totals[(key[0], key[1], "accepted")]
        refused = fold_totals[(key[0], key[1], "refused")]
        if (
            raw["accepted_count"] != accepted
            or raw["refused_count"] != refused
            or raw["slot_count"] != accepted + refused
        ):
            raise FormalCloudEvaluationError("24-axis and 48-axis censuses disagree")
    if tuple(observed_fold_axes) != expected_fold_axes:
        raise FormalCloudEvaluationError("aggregate 24 axes are incomplete or reordered")
    for view in SOURCE_VIEW_IDS:
        if (
            view_census[view]["accepted_count"] != view_totals[(view, "accepted")]
            or view_census[view]["refused_count"] != view_totals[(view, "refused")]
        ):
            raise FormalCloudEvaluationError("view and axis censuses disagree")

    dispositions = Counter()
    for raw, view in zip(raw_reports, SOURCE_VIEW_IDS, strict=True):
        if type(raw) is not dict:
            raise FormalCloudEvaluationError("aggregate report changed type")
        required = {
            "report_id", "report_sha256", "schema", "status", "authority",
            "evaluation_id", "source_view_id", "input_id", "input_sha256",
            "bootstrap_seed_sha256", "formal_fold_ids", "descriptive_fold_ids",
            "coverage", "ic_summaries", "fama_macbeth_summaries",
            "paired_ic_summaries", "economic_summaries", "primary_gates",
            "disposition", "disposition_reasons",
        }
        if set(raw) != required:
            raise FormalCloudEvaluationError("aggregate report fields changed")
        digest_seed = {
            key: value for key, value in raw.items()
            if key not in {"report_id", "report_sha256"}
        }
        digest = hashlib.sha256(
            json.dumps(
                digest_seed, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("ascii")
        ).hexdigest()
        if (
            raw["report_sha256"] != digest
            or raw["report_id"] != f"arv2-formal-evaluation-report-{digest[:24]}"
            or raw["schema"] != _evaluation.SCHEMA
            or raw["status"] != _evaluation.STATUS
            or raw["authority"] != _evaluation.AUTHORITY
            or raw["evaluation_id"] != EVALUATION_ID
            or raw["source_view_id"] != view
            or raw["input_id"] != input_by_view[view]["input_id"]
            or raw["input_sha256"] != input_by_view[view]["input_sha256"]
            or raw["bootstrap_seed_sha256"] != _evaluation.BOOTSTRAP_SEED_SHA256
            or tuple(raw["formal_fold_ids"]) != FORMAL_FOLD_IDS
            or tuple(raw["descriptive_fold_ids"]) != DESCRIPTIVE_FOLD_IDS
            or type(raw["coverage"]) is not list or len(raw["coverage"]) != 52
            or type(raw["ic_summaries"]) is not list or len(raw["ic_summaries"]) != 104
            or type(raw["fama_macbeth_summaries"]) is not list
            or len(raw["fama_macbeth_summaries"]) != 208
            or type(raw["paired_ic_summaries"]) is not list
            or len(raw["paired_ic_summaries"]) != 52
            or type(raw["economic_summaries"]) is not list
            or len(raw["economic_summaries"]) != 8
            or type(raw["primary_gates"]) is not list
            or len(raw["primary_gates"]) != 3
        ):
            raise FormalCloudEvaluationError("aggregate report identity or census changed")
        dispositions[_safe_id(raw["disposition"], "report disposition")] += 1
    if document["report_disposition_counts"] != dict(sorted(dispositions.items())):
        raise FormalCloudEvaluationError("aggregate report disposition census changed")
    if expanded:
        _require_expanded_report_outputs_v2(
            document, bindings,
            report_family_object_payloads=report_family_object_payloads,
        )
    elif report_family_object_payloads is not None:
        raise FormalCloudEvaluationError(
            "legacy aggregate gained external report-family objects"
        )

    terminal = document["terminal_census"]
    if type(terminal) is not dict or set(terminal) != {
        "terminal_policy_id", "terminal_requirement_count",
        "terminal_payoff_count", "benchmark_splice_continuation_count",
        "named_terminal_refusal_count", "used_terminal_disposition_count",
        "unused_terminal_disposition_count", "silently_omitted_terminal_count",
        "complete_without_named_refusal",
    }:
        raise FormalCloudEvaluationError("aggregate terminal census fields changed")
    derived_complete = terminal.pop("complete_without_named_refusal")
    try:
        terminal_value = FormalCloudTerminalCensus(**terminal)
    finally:
        terminal["complete_without_named_refusal"] = derived_complete
    if derived_complete is not terminal_value.complete_without_named_refusal:
        raise FormalCloudEvaluationError("aggregate terminal completeness changed")
    return document


__all__ = (
    "AUTHORITY",
    "BOOTSTRAP_RESAMPLES",
    "EVALUATION_ID",
    "FORMAL_CLOUD_EVALUATOR_CONTRACT_SHA256",
    "FormalCloudCompactStream",
    "FormalCloudEvaluationBindings",
    "FormalCloudEvaluationError",
    "FormalCloudEvaluationOutput",
    "FormalCloudReportFamilyObjectDescriptor",
    "FormalCloudTerminalCensus",
    "FormalMarketPanelDigest",
    "MARKET_PANEL_STREAM_SCHEMA",
    "FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA",
    "REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX",
    "REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA",
    "SCHEMA",
    "STATUS",
    "STREAMED_FORMAL_CONTRACT_VARIANT",
    "STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA",
    "STREAMED_FORMAL_PREKNOWN_BINDINGS_SCHEMA",
    "begin_compact_formal_evaluation",
    "begin_formal_market_panel_digest",
    "build_cloud_formal_evaluation_inputs",
    "consume_compact_formal_session_block",
    "consume_formal_cloud_evaluation_output",
    "consume_formal_market_panel_digest_row",
    "derive_formal_cloud_evaluation_family_object_read_plan",
    "derive_streamed_formal_evaluation_preknown_bindings_record",
    "execute_compact_formal_evaluation",
    "execute_cloud_formal_evaluation",
    "formal_cloud_evaluation_family_object_read_plan",
    "finish_compact_formal_evaluation",
    "finish_compact_formal_evaluation_output",
    "finish_formal_market_panel_digest",
    "require_formal_cloud_evaluation_aggregate_bytes",
    "require_formal_cloud_evaluation_family_object_payload",
    "require_formal_cloud_evaluation_output",
)


_seal_cloud_evaluation_authority_callers()
del _seal_cloud_evaluation_authority_callers
