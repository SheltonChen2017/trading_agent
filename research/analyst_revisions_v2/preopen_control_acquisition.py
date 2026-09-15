"""Reviewed, outcome-free acquisition authority for production pre-open controls.

The ARV2 production-truth gate must not authenticate a universe merely because
the caller supplied a self-consistent tuple and re-hashed it.  This module is
the narrow bridge from a separately reviewed QuantConnect control-construction
run to that gate.  It accepts only an exact content-addressed output manifest
and an independent review receipt plus owner-signed physical pin which bind the
source bytes, QC execution receipt, every session terminal commitment, and the
persisted control shards.

The loader is deliberately pure: it has no filesystem, provider, credential,
QuantConnect, Object Store, price, outcome, result, deployment, order, or
trading capability.  Loading a receipt does not authorize the run which
created it and does not authorize a later outcome run.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import threading
import weakref
from typing import Any

from .canonical import (
    canonical_json_bytes,
    parse_date,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from .stock_evaluation_contract import CONTROL_DEFINITION


class PreopenControlAcquisitionError(ValueError):
    """A pre-open control manifest or its independent review is invalid."""


CONTRACT_SCHEMA = "arv2-preopen-control-construction-contract-v1"
OUTPUT_MANIFEST_SCHEMA = "arv2-preopen-control-output-manifest-v1"
REVIEW_RECEIPT_SCHEMA = "arv2-preopen-control-independent-review-v1"
UNIVERSE_SESSION_COMMITMENT_SCHEMA = (
    "arv2-preopen-control-universe-session-commitment-v1"
)
CONTROL_SESSION_COMMITMENT_SCHEMA = (
    "arv2-preopen-control-session-commitment-v1"
)
OUTPUT_TERMINAL_SCHEMA = "arv2-preopen-control-terminal-v1"
OUTPUT_SHARD_SCHEMA = "arv2-preopen-control-output-shard-v1"
SOURCE_VIEW_ID = "conservative_censored_current_vintage_non_pristine_pit"
GUIDANCE_CLOCK_POLICY_ID = (
    "massive_guidance_date_only_three_session_lag_prior_date_censor-v1"
)

CONTINUOUS_CONTROL_NAMES = tuple(CONTROL_DEFINITION["continuous_columns"])
BINARY_CONTROL_NAMES = tuple(CONTROL_DEFINITION["binary_columns"])
CONTROL_NAMES = (*CONTINUOUS_CONTROL_NAMES, *BINARY_CONTROL_NAMES)


def preopen_control_contract_record() -> dict[str, Any]:
    """Return the exact definitions implemented by the QC control worker."""

    return {
        "schema": CONTRACT_SCHEMA,
        "population": (
            "reviewed_point_in_time_eligible_US_common_stock_security_session_"
            "census_with_one_accepted_or_named_refused_terminal"
        ),
        "identity": {
            "security_id": "QuantConnect_permanent_SecurityIdentifier_round_trip",
            "issuer_id": "Sharadar_permaticker",
            "share_class_id": "point_in_time_FIGI_or_reviewed_share_class_identity",
            "listing_id": (
                "content_identity_of_permaticker_ticker_exchange_firstpricedate_"
                "lastpricedate_listing_record"
            ),
            "required_cross_binding": (
                "QC_security_id_issuer_share_class_listing_security_master_row_hash"
            ),
            "qc_sid_mapping_authority": (
                "separately_reviewed_PIT_Sharadar_identity_to_QC_permanent_SID_"
                "artifact_with_one_bound_row_per_distinct_universe_security"
            ),
            "ticker_role": "historical_display_only_never_permanent_identity",
        },
        "timing": {
            "decision_clock": "NYSE_regular_session_open_in_America/New_York",
            "strict_rule": "every_input_available_at_less_than_decision_open",
            "completed_session_rule": "bar_end_less_than_or_equal_prior_session_close",
            "future_seed_rows": "ignored_and_cannot_change_prior_session_output",
            "missing_or_late": "named_refusal_no_imputation",
        },
        "market_inputs": {
            "return_price": "QC_TotalReturn_adjusted_daily_close",
            "raw_price_and_volume": "QC_Raw_daily_close_and_raw_share_volume",
            "benchmark": "SPY_permanent_QC_security_id_TotalReturn_daily_close",
            "history_end": "decision_open_exclusive",
            "calculation_clock": (
                "post_sample_calculation_session_strictly_after_last_decision_session"
            ),
            "acquisition_shape": (
                "two_security_batch_major_full_sample_passes_with_48_security_"
                "History_batches_and_no_decision_block_history_refetch"
            ),
            "memory_shape": (
                "retain_only_one_48_security_full_sample_market_batch_plus_"
                "bounded_session_peer_aggregates_and_terminal_shard_buffers"
            ),
            "lineage": (
                "one_deduplicated_benchmark_and_every_security_session_lineage_"
                "enter_a_batch_order_independent_logical_session_commitment_"
                "bound_into_each_terminal_market_root"
            ),
            "target_horizon_prices": False,
            "delisting_price": False,
        },
        "continuous_controls": {
            "order": list(CONTINUOUS_CONTROL_NAMES),
            "momentum_20d": "TR_close[t-1]/TR_close[t-21]-1",
            "momentum_60d": "TR_close[t-1]/TR_close[t-61]-1",
            "momentum_12_1": "TR_close[t-21]/TR_close[t-252]-1",
            "sector_momentum_20d": (
                "equal_weight_mean_of_momentum_20d_for_every_accepted_same_session_"
                "same_sector_member_including_self_full_peer_census_required"
            ),
            "sector_momentum_60d": (
                "equal_weight_mean_of_momentum_60d_for_every_accepted_same_session_"
                "same_sector_member_including_self_full_peer_census_required"
            ),
            "sector_momentum_12_1": (
                "equal_weight_mean_of_momentum_12_1_for_every_accepted_same_session_"
                "same_sector_member_including_self_full_peer_census_required"
            ),
            "industry_momentum_20d": (
                "equal_weight_mean_of_momentum_20d_for_every_accepted_same_session_"
                "same_industry_member_including_self_full_peer_census_required"
            ),
            "industry_momentum_60d": (
                "equal_weight_mean_of_momentum_60d_for_every_accepted_same_session_"
                "same_industry_member_including_self_full_peer_census_required"
            ),
            "industry_momentum_12_1": (
                "equal_weight_mean_of_momentum_12_1_for_every_accepted_same_session_"
                "same_industry_member_including_self_full_peer_census_required"
            ),
            "market_beta_252d": (
                "covariance_of_252_stock_and_SPY_simple_TR_close_returns_divided_"
                "by_SPY_sample_variance_same_252_completed_returns"
            ),
            "realized_volatility_60d": (
                "sample_standard_deviation_of_60_simple_TR_close_returns_times_"
                "sqrt_252"
            ),
            "value_book_to_market": (
                "latest_PIT_book_equity_USD_available_preopen_divided_by_prior_"
                "raw_close_times_latest_PIT_shares_outstanding_available_preopen"
            ),
            "growth_trailing_revenue": (
                "latest_PIT_revenue_TTM_USD_divided_by_same_issuer_revenue_TTM_"
                "for_the_comparable_prior_fiscal_year_minus_one"
            ),
            "size_market_cap": (
                "natural_log_of_prior_raw_close_times_latest_PIT_shares_outstanding"
            ),
            "liquidity_dollar_volume_60d": (
                "natural_log_of_median_raw_close_times_raw_share_volume_over_"
                "60_completed_sessions"
            ),
            "turnover_60d": (
                "median_of_raw_share_volume_divided_by_latest_PIT_shares_"
                "outstanding_over_60_completed_sessions"
            ),
            "analyst_coverage_60d": (
                "count_distinct_admitted_analyst_ids_in_conservative_censored_"
                "rating_view_over_prior_60_completed_sessions"
            ),
            "event_intensity_20d": (
                "count_distinct_institution_security_eligible_session_tuples_in_"
                "conservative_censored_rating_view_over_prior_20_completed_sessions"
            ),
            "event_diversity_20d": (
                "count_distinct_admitted_common_event_ids_in_conservative_censored_"
                "rating_view_over_prior_20_completed_sessions"
            ),
        },
        "binary_controls": {
            "order": list(BINARY_CONTROL_NAMES),
            "earnings_anchor": (
                "from_earnings_rows_public_preopen_choose_earliest_report_session_"
                "on_or_after_decision_else_latest_prior_report_session"
            ),
            "exact_earnings_day": "anchor_session_equals_decision_session",
            "one_to_two_days_after_earnings": (
                "decision_is_one_or_two_NYSE_sessions_after_prior_anchor"
            ),
            "three_to_five_days_after_earnings": (
                "decision_is_three_through_five_NYSE_sessions_after_prior_anchor"
            ),
            "over_five_days_after_earnings": (
                "decision_is_more_than_five_NYSE_sessions_after_prior_anchor"
            ),
            "pre_earnings": "chosen_anchor_is_after_decision_session",
            "public_guidance_proximity": (
                "at_least_one_guidance_record_admitted_by_the_three_session_"
                "date_only_policy_and_public_preopen_with_eligible_session_"
                "in_decision_session_or_prior_five_completed_NYSE_sessions"
            ),
            "earnings_buckets": (
                "mutually_exclusive_when_anchor_exists_all_zero_when_none"
            ),
        },
        "arithmetic": {
            "numeric_type": "Decimal_from_canonical_base10_text_never_binary_float",
            "decimal_precision": 50,
            "rounding": "ROUND_HALF_EVEN",
            "median": "ordered_middle_or_exact_mean_of_two_middle_values",
            "undefined_denominator_or_nonpositive_log_input": "named_refusal",
            "peer_missing_member": "refuse_entire_affected_peer_group_control_row",
        },
        "output": {
            "control_order": list(CONTROL_NAMES),
            "terminal": "one_accepted_or_named_refused_per_universe_security_session",
            "encoding": "canonical_JSON_lines_UTF8_LF_gzip_level9_mtime0",
            "persistence": "private_QC_Object_Store_content_addressed_shards",
            "physical_partition": (
                "security_batch_by_decision_chunk_with_authenticated_bounds"
            ),
            "logical_order": (
                "bounded_k_way_merge_by_decision_session_then_security_id"
            ),
            "receipt": "hash_count_only_custom_summary_statistics",
            "formal_runtime": "direct_Object_Store_consumption_no_host_download_required",
        },
        "forbidden": {
            "target_horizon_or_forward_return": True,
            "outcome_or_result_read": True,
            "orders_or_portfolio_actions": True,
            "logs_containing_rows_or_values": True,
        },
    }


CONTRACT_BYTES = canonical_json_bytes(preopen_control_contract_record())
CONTRACT_SHA256 = sha256_bytes(CONTRACT_BYTES)
CONTRACT_ID = f"arv2-preopen-control-contract-{CONTRACT_SHA256[:16]}"


def render_preopen_control_contract_bytes() -> bytes:
    return bytes(CONTRACT_BYTES)


def _exact_str(value: object, name: str) -> str:
    if type(value) is not str:
        raise PreopenControlAcquisitionError(f"{name} must be an exact string")
    return value


def _canonical_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise PreopenControlAcquisitionError(f"{name} must be nonempty exact bytes")
    try:
        value = strict_json_loads(payload.decode("utf-8"), name)
    except (UnicodeError, ValueError) as exc:
        raise PreopenControlAcquisitionError(f"{name} is not UTF-8 JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise PreopenControlAcquisitionError(f"{name} is not one canonical JSON object")
    return value


def _exact_fields(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise PreopenControlAcquisitionError(f"{name} fields changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class UniverseSessionAcquisitionCommitment:
    decision_session: str
    accepted_count: int
    refusal_count: int
    terminal_count: int
    terminal_merkle_root: str

    def __post_init__(self) -> None:
        _exact_str(self.decision_session, "decision_session")
        parse_date(self.decision_session, "decision_session")
        for name in ("accepted_count", "refusal_count", "terminal_count"):
            require_int(getattr(self, name), name, minimum=0)
        if self.terminal_count != self.accepted_count + self.refusal_count:
            raise PreopenControlAcquisitionError("universe session census does not reconcile")
        require_sha256(self.terminal_merkle_root, "terminal_merkle_root")

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": UNIVERSE_SESSION_COMMITMENT_SCHEMA,
            "decision_session": self.decision_session,
            "accepted_count": self.accepted_count,
            "refusal_count": self.refusal_count,
            "terminal_count": self.terminal_count,
            "terminal_merkle_root": self.terminal_merkle_root,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ControlSessionAcquisitionCommitment:
    decision_session: str
    accepted_count: int
    refusal_count: int
    terminal_count: int
    terminal_merkle_root: str
    market_observation_count: int
    market_observation_sha256: str

    def __post_init__(self) -> None:
        _exact_str(self.decision_session, "decision_session")
        parse_date(self.decision_session, "decision_session")
        for name in (
            "accepted_count", "refusal_count", "terminal_count",
            "market_observation_count",
        ):
            require_int(getattr(self, name), name, minimum=0)
        if self.terminal_count != self.accepted_count + self.refusal_count:
            raise PreopenControlAcquisitionError("control session census does not reconcile")
        require_sha256(self.terminal_merkle_root, "terminal_merkle_root")
        require_sha256(
            self.market_observation_sha256, "market_observation_sha256"
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": CONTROL_SESSION_COMMITMENT_SCHEMA,
            "decision_session": self.decision_session,
            "accepted_count": self.accepted_count,
            "refusal_count": self.refusal_count,
            "terminal_count": self.terminal_count,
            "terminal_merkle_root": self.terminal_merkle_root,
            "market_observation_count": self.market_observation_count,
            "market_observation_sha256": self.market_observation_sha256,
        }


@dataclasses.dataclass(frozen=True, init=False)
class PreopenControlAcquisitionReceipt:
    contract_id: str
    contract_sha256: str
    artifact_id: str
    artifact_sha256: str
    content_sha256: str
    byte_count: int
    input_manifest_id: str
    input_manifest_sha256: str
    input_manifest_byte_count: int
    eligible_universe_artifact_id: str
    eligible_universe_artifact_sha256: str
    eligible_universe_artifact_byte_count: int
    qc_sid_mapping_artifact_id: str
    qc_sid_mapping_artifact_sha256: str
    qc_sid_mapping_artifact_byte_count: int
    qc_sid_mapping_row_count: int
    input_source_inventory_sha256: str
    input_role_bindings: tuple[tuple[object, ...], ...]
    truth_source_bindings: tuple[tuple[str, str, str], ...]
    rating_source_complete: bool
    earnings_source_complete: bool
    guidance_source_complete: bool
    earnings_pit_policy_id: str
    guidance_clock_policy_id: str
    run_authority_id: str
    run_authority_sha256: str
    construction_resource_census_sha256: str
    project_source_set_sha256: str
    output_shard_inventory_sha256: str
    universe_terminal_projection_sha256: str
    control_terminal_projection_sha256: str
    universe_sessions: tuple[UniverseSessionAcquisitionCommitment, ...]
    control_sessions: tuple[ControlSessionAcquisitionCommitment, ...]
    universe_terminal_count: int
    control_accepted_count: int
    control_refusal_count: int
    control_terminal_count: int
    review_receipt_id: str
    review_receipt_sha256: str
    qc_execution_receipt_id: str
    qc_execution_receipt_sha256: str
    external_review_pin_id: str
    external_review_pin_sha256: str
    output_shard_payload_projection_sha256: str
    q_data_measurement_count: int
    q_data_measurement_projection_sha256: str
    complete_source_inventory_verified: bool
    per_session_universe_terminal_completeness_verified: bool
    control_formula_equivalence_verified: bool
    strict_preopen_timing_verified: bool
    no_outcomes_verified: bool
    object_store_persistence_verified: bool
    formal_runtime_direct_consumption_verified: bool
    output_manifest_bytes: bytes
    review_receipt_bytes: bytes
    provider_access: bool
    credential_access: bool
    filesystem_access: bool
    quantconnect_access: bool
    object_store_access: bool
    price_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


def _commitment_root(records: list[dict[str, Any]], domain: str) -> str:
    return sha256_bytes(canonical_json_bytes({"domain": domain, "records": records}))


def _parse_universe_sessions(value: object) -> tuple[UniverseSessionAcquisitionCommitment, ...]:
    if type(value) is not list:
        raise PreopenControlAcquisitionError("universe session commitments must be a list")
    result = []
    for raw in value:
        parsed = _exact_fields(
            raw,
            frozenset(
                {
                    "schema", "decision_session", "accepted_count", "refusal_count",
                    "terminal_count", "terminal_merkle_root",
                }
            ),
            "universe session commitment",
        )
        if parsed["schema"] != UNIVERSE_SESSION_COMMITMENT_SCHEMA:
            raise PreopenControlAcquisitionError("universe commitment schema changed")
        result.append(
            UniverseSessionAcquisitionCommitment(
                decision_session=parsed["decision_session"],
                accepted_count=parsed["accepted_count"],
                refusal_count=parsed["refusal_count"],
                terminal_count=parsed["terminal_count"],
                terminal_merkle_root=parsed["terminal_merkle_root"],
            )
        )
    built = tuple(result)
    if not built or tuple(item.decision_session for item in built) != tuple(
        sorted({item.decision_session for item in built})
    ):
        raise PreopenControlAcquisitionError(
            "universe session commitments repeat, are empty, or are not sorted"
        )
    return built


def _parse_control_sessions(value: object) -> tuple[ControlSessionAcquisitionCommitment, ...]:
    if type(value) is not list:
        raise PreopenControlAcquisitionError("control session commitments must be a list")
    result = []
    for raw in value:
        parsed = _exact_fields(
            raw,
            frozenset(
                {
                    "schema", "decision_session", "accepted_count", "refusal_count",
                    "terminal_count", "terminal_merkle_root",
                    "market_observation_count", "market_observation_sha256",
                }
            ),
            "control session commitment",
        )
        if parsed["schema"] != CONTROL_SESSION_COMMITMENT_SCHEMA:
            raise PreopenControlAcquisitionError("control commitment schema changed")
        result.append(
            ControlSessionAcquisitionCommitment(
                decision_session=parsed["decision_session"],
                accepted_count=parsed["accepted_count"],
                refusal_count=parsed["refusal_count"],
                terminal_count=parsed["terminal_count"],
                terminal_merkle_root=parsed["terminal_merkle_root"],
                market_observation_count=parsed["market_observation_count"],
                market_observation_sha256=parsed[
                    "market_observation_sha256"
                ],
            )
        )
    built = tuple(result)
    if not built or tuple(item.decision_session for item in built) != tuple(
        sorted({item.decision_session for item in built})
    ):
        raise PreopenControlAcquisitionError(
            "control session commitments repeat, are empty, or are not sorted"
        )
    return built


_MANIFEST_FIELDS = frozenset(
    {
        "schema", "contract_id", "contract_sha256", "input_manifest",
        "eligible_universe_source", "qc_sid_mapping_source", "source_policy",
        "construction_resource_census", "run_authority",
        "input_role_bindings", "truth_source_bindings",
        "input_source_inventory_sha256", "project_source_set_sha256",
        "construction_intermediates",
        "output_shards", "output_shard_inventory_sha256",
        "universe_sessions", "control_sessions",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256", "census", "capabilities",
    }
)
_BINDING_FIELDS = frozenset(
    {"artifact_id", "content_sha256", "artifact_sha256", "byte_count"}
)
_SID_MAPPING_BINDING_FIELDS = frozenset({
    *_BINDING_FIELDS, "row_count", "mapping_semantics",
})
_INPUT_ROLE_ORDER = (
    "universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings"
)
_TRUTH_SOURCE_ORDER = (
    "accepted_risk_capture", "eligible_universe", "security_master",
    "firm_ontology", "common_event", "sector_classification",
    "preopen_control", "data_quality",
)
_INPUT_ROLE_BINDING_FIELDS = frozenset({
    "role", "descriptor_projection_sha256", "shard_count", "row_count",
    "compressed_byte_count", "uncompressed_byte_count",
})
_TRUTH_SOURCE_BINDING_FIELDS = frozenset(
    {"kind", "artifact_id", "artifact_sha256"}
)
_OUTPUT_SHARD_FIELDS = frozenset({
    "schema", "role", "ordinal", "object_store_key", "compression",
    "encoding", "row_schema", "compressed_sha256", "compressed_byte_count",
    "uncompressed_sha256", "uncompressed_byte_count", "row_count",
    "decision_chunk_ordinal", "security_batch_ordinal",
    "partition_first_session", "partition_last_session",
    "first_security_id", "last_security_id",
})
_CONSTRUCTION_INTERMEDIATE_FIELDS = frozenset({
    "schema", "peer_aggregate_record_count",
    "peer_aggregate_projection_sha256", "market_session_commitment_count",
    "market_session_projection_sha256", "physical_terminal_shard_count",
    "logical_terminal_order", "q_data_measurement_count",
    "q_data_measurement_projection_sha256",
})
_CONSTRUCTION_INTERMEDIATE_SCHEMA = (
    "arv2-preopen-control-construction-intermediate-commitment-v1"
)
_SOURCE_POLICY_FIELDS = frozenset({
    "rating_source_view", "rating_source_complete", "earnings_source_complete",
    "earnings_pit_policy_id", "guidance_source_complete",
    "guidance_clock_policy_id", "unknown_event_archive_or_clock_is_zero",
})
_RUN_AUTHORITY_FIELDS = frozenset({
    "schema", "pin_id", "pin_sha256", "closed_input_manifest_sha256",
    "input_source_inventory_sha256", "source_policy_sha256",
    "resource_census_sha256", "qc_sid_mapping_source_sha256",
    "target_qc_capacity_reviewed", "qc_sid_mapping_reviewed",
})
_CENSUS_FIELDS = frozenset(
    {
        "universe_terminal_count", "control_accepted_count",
        "control_refusal_count", "control_terminal_count",
    }
)
_CAPABILITY_FIELDS = frozenset(
    {
        "provider_access", "credential_access", "filesystem_access",
        "quantconnect_access", "object_store_access", "price_access",
        "outcome_access", "result_access", "deployment", "orders", "trading",
    }
)
_REVIEW_BOOLEAN_FIELDS = (
    "complete_source_inventory_verified",
    "per_session_universe_terminal_completeness_verified",
    "control_formula_equivalence_verified",
    "strict_preopen_timing_verified",
    "no_outcomes_verified",
    "object_store_persistence_verified",
    "formal_runtime_direct_consumption_verified",
)
_REVIEW_FIELDS = frozenset(
    {
        "schema", "output_manifest", "input_source_inventory_sha256",
        "project_source_set_sha256", "output_shard_inventory_sha256",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256", "review_receipt_id",
        "review_receipt_sha256", *_REVIEW_BOOLEAN_FIELDS,
    }
)


def _validate_binding(value: object, name: str) -> dict[str, Any]:
    result = _exact_fields(value, _BINDING_FIELDS, name)
    require_identifier(_exact_str(result["artifact_id"], f"{name}.artifact_id"), "artifact_id")
    require_sha256(_exact_str(result["content_sha256"], f"{name}.content_sha256"), "content_sha256")
    require_sha256(_exact_str(result["artifact_sha256"], f"{name}.artifact_sha256"), "artifact_sha256")
    require_int(result["byte_count"], f"{name}.byte_count", minimum=1)
    return result


def _validate_output_shards(value: object) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        raise PreopenControlAcquisitionError("output shard inventory is empty")
    result: list[dict[str, Any]] = []
    keys: set[str] = set()
    partitions: list[tuple[int, int]] = []
    for expected_ordinal, raw in enumerate(value):
        item = _exact_fields(raw, _OUTPUT_SHARD_FIELDS, "output shard")
        if (
            item["schema"] != OUTPUT_SHARD_SCHEMA
            or item["role"] != "control_terminals"
            or item["ordinal"] != expected_ordinal
            or item["compression"] != "gzip-level9-mtime0"
            or item["encoding"] != "canonical-json-lines-utf8-lf"
            or item["row_schema"] != OUTPUT_TERMINAL_SCHEMA
        ):
            raise PreopenControlAcquisitionError("output shard protocol changed")
        key = _exact_str(item["object_store_key"], "output shard key")
        if (
            not key.startswith("arv2/preopen/output/content/control_terminals/")
            or key in keys
        ):
            raise PreopenControlAcquisitionError("output shard key changed or repeats")
        keys.add(key)
        chunk = require_int(
            item["decision_chunk_ordinal"], "decision_chunk_ordinal", minimum=0
        )
        batch = require_int(
            item["security_batch_ordinal"], "security_batch_ordinal", minimum=0
        )
        partitions.append((chunk, batch))
        first_session = _exact_str(
            item["partition_first_session"], "partition_first_session"
        )
        last_session = _exact_str(
            item["partition_last_session"], "partition_last_session"
        )
        if parse_date(first_session, "partition_first_session") > parse_date(
            last_session, "partition_last_session"
        ):
            raise PreopenControlAcquisitionError("output shard sessions reversed")
        first_security = require_identifier(
            _exact_str(item["first_security_id"], "first_security_id"),
            "first_security_id",
        )
        last_security = require_identifier(
            _exact_str(item["last_security_id"], "last_security_id"),
            "last_security_id",
        )
        if first_security > last_security:
            raise PreopenControlAcquisitionError("output shard securities reversed")
        compressed_hash = require_sha256(
            _exact_str(item["compressed_sha256"], "compressed_sha256"),
            "compressed_sha256",
        )
        require_sha256(
            _exact_str(item["uncompressed_sha256"], "uncompressed_sha256"),
            "uncompressed_sha256",
        )
        expected_key = (
            "arv2/preopen/output/content/control_terminals/"
            f"chunk-{chunk:04d}/security-batch-{batch:04d}/"
            f"{compressed_hash}-jsonl.gz"
        )
        if key != expected_key:
            raise PreopenControlAcquisitionError("output shard key is not content-derived")
        require_int(item["compressed_byte_count"], "compressed_byte_count", minimum=1)
        require_int(
            item["uncompressed_byte_count"], "uncompressed_byte_count", minimum=1
        )
        require_int(item["row_count"], "row_count", minimum=1)
        if (
            item["compressed_byte_count"] > 32 * 1024 * 1024
            or item["uncompressed_byte_count"] > 256 * 1024 * 1024
            or item["row_count"] > 5_000
        ):
            raise PreopenControlAcquisitionError("output shard exceeds reviewed bound")
        result.append(item)
    if partitions != sorted(set(partitions)):
        raise PreopenControlAcquisitionError(
            "output shard partitions repeat or are not canonical"
        )
    return result


def _validate_manifest(
    payload: bytes,
) -> tuple[
    dict[str, Any],
    tuple[UniverseSessionAcquisitionCommitment, ...],
    tuple[ControlSessionAcquisitionCommitment, ...],
]:
    value = _exact_fields(_canonical_object(payload, "output manifest"), _MANIFEST_FIELDS, "output manifest")
    if (
        value["schema"] != OUTPUT_MANIFEST_SCHEMA
        or value["contract_id"] != CONTRACT_ID
        or value["contract_sha256"] != CONTRACT_SHA256
    ):
        raise PreopenControlAcquisitionError("output manifest contract changed")
    _validate_binding(value["input_manifest"], "input manifest binding")
    _validate_binding(value["eligible_universe_source"], "eligible universe source")
    sid_mapping = _exact_fields(
        value["qc_sid_mapping_source"],
        _SID_MAPPING_BINDING_FIELDS,
        "QC SID mapping source",
    )
    require_identifier(
        _exact_str(sid_mapping["artifact_id"], "QC SID mapping artifact_id"),
        "QC SID mapping artifact_id",
    )
    for name in ("content_sha256", "artifact_sha256"):
        require_sha256(
            _exact_str(sid_mapping[name], f"QC SID mapping {name}"), name
        )
    if sid_mapping["content_sha256"] != sid_mapping["artifact_sha256"]:
        raise PreopenControlAcquisitionError(
            "QC SID mapping content and artifact identities differ"
        )
    require_int(sid_mapping["byte_count"], "QC SID mapping byte_count", minimum=1)
    require_int(sid_mapping["row_count"], "QC SID mapping row_count", minimum=1)
    if sid_mapping["mapping_semantics"] != (
        "canonical_content_addressed_exact_QC_SecurityIdentifier_to_"
        "Sharadar_CUSIP_permaticker_FIGI_binding;_current_ticker_is_"
        "display_only_and_the_runtime_must_use_self.symbol_encoded_SID"
    ):
        raise PreopenControlAcquisitionError("QC SID mapping semantics changed")
    role_bindings = value["input_role_bindings"]
    if (
        type(role_bindings) is not list
        or tuple(item.get("role") for item in role_bindings) != _INPUT_ROLE_ORDER
    ):
        raise PreopenControlAcquisitionError("input role bindings changed")
    parsed_role_bindings = []
    for item in role_bindings:
        parsed = _exact_fields(
            item, _INPUT_ROLE_BINDING_FIELDS, "input role binding"
        )
        parsed_role_bindings.append(parsed)
        require_sha256(
            _exact_str(
                parsed["descriptor_projection_sha256"],
                "descriptor_projection_sha256",
            ),
            "descriptor_projection_sha256",
        )
        for name in (
            "shard_count", "row_count", "compressed_byte_count",
            "uncompressed_byte_count",
        ):
            require_int(parsed[name], name, minimum=0)
    sid_mapping_role = next(
        item for item in parsed_role_bindings if item["role"] == "sid_mapping"
    )
    if (
        sid_mapping["content_sha256"]
        != sid_mapping_role["descriptor_projection_sha256"]
        or sid_mapping["row_count"] != sid_mapping_role["row_count"]
    ):
        raise PreopenControlAcquisitionError(
            "QC SID mapping source differs from its physical input role"
        )
    truth_sources = value["truth_source_bindings"]
    if (
        type(truth_sources) is not list
        or tuple(item.get("kind") for item in truth_sources)
        != _TRUTH_SOURCE_ORDER
    ):
        raise PreopenControlAcquisitionError("truth source bindings changed")
    for item in truth_sources:
        parsed = _exact_fields(
            item, _TRUTH_SOURCE_BINDING_FIELDS, "truth source binding"
        )
        require_identifier(
            _exact_str(parsed["artifact_id"], "truth artifact_id"),
            "truth artifact_id",
        )
        require_sha256(
            _exact_str(parsed["artifact_sha256"], "truth artifact_sha256"),
            "truth artifact_sha256",
        )
    policy = _exact_fields(value["source_policy"], _SOURCE_POLICY_FIELDS, "source policy")
    if policy["rating_source_view"] != SOURCE_VIEW_ID:
        raise PreopenControlAcquisitionError("rating source view changed")
    for name in (
        "rating_source_complete", "earnings_source_complete",
        "guidance_source_complete", "unknown_event_archive_or_clock_is_zero",
    ):
        require_exact_bool(policy[name], name)
    if policy["unknown_event_archive_or_clock_is_zero"] is not False:
        raise PreopenControlAcquisitionError("unknown event input was silently zeroed")
    for name in ("earnings_pit_policy_id", "guidance_clock_policy_id"):
        require_identifier(_exact_str(policy[name], name), name)
    if (
        policy["guidance_source_complete"] is True
        and policy["guidance_clock_policy_id"] != GUIDANCE_CLOCK_POLICY_ID
    ):
        raise PreopenControlAcquisitionError(
            "complete guidance does not use the reviewed date-only lag policy"
        )
    if type(value["construction_resource_census"]) is not dict:
        raise PreopenControlAcquisitionError("construction resource census changed")
    run_authority = _exact_fields(
        value["run_authority"], _RUN_AUTHORITY_FIELDS, "run authority"
    )
    if run_authority["schema"] != "arv2-preopen-control-private-run-authority-v1":
        raise PreopenControlAcquisitionError("run authority schema changed")
    for name in (
        "pin_sha256", "closed_input_manifest_sha256",
        "input_source_inventory_sha256", "source_policy_sha256",
        "resource_census_sha256", "qc_sid_mapping_source_sha256",
    ):
        require_sha256(_exact_str(run_authority[name], name), name)
    require_identifier(_exact_str(run_authority["pin_id"], "pin_id"), "pin_id")
    for name in ("target_qc_capacity_reviewed", "qc_sid_mapping_reviewed"):
        require_exact_bool(run_authority[name], name)
        if run_authority[name] is not True:
            raise PreopenControlAcquisitionError(
                "private run authority did not review capacity and QC SID mapping"
            )
    if (
        run_authority["input_source_inventory_sha256"]
        != value["input_source_inventory_sha256"]
        or run_authority["source_policy_sha256"]
        != sha256_bytes(canonical_json_bytes(policy))
        or run_authority["resource_census_sha256"]
        != sha256_bytes(canonical_json_bytes(value["construction_resource_census"]))
        or run_authority["qc_sid_mapping_source_sha256"]
        != sha256_bytes(canonical_json_bytes(sid_mapping))
    ):
        raise PreopenControlAcquisitionError("run authority binding changed")
    for name in (
        "input_source_inventory_sha256", "project_source_set_sha256",
        "output_shard_inventory_sha256", "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
    ):
        require_sha256(_exact_str(value[name], name), name)
    output_shards = _validate_output_shards(value["output_shards"])
    if value["output_shard_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(value["output_shards"])
    ):
        raise PreopenControlAcquisitionError("output shard inventory hash changed")
    universe = _parse_universe_sessions(value["universe_sessions"])
    controls = _parse_control_sessions(value["control_sessions"])
    if tuple(item.decision_session for item in universe) != tuple(
        item.decision_session for item in controls
    ):
        raise PreopenControlAcquisitionError("universe/control session geometry differs")
    universe_root = _commitment_root(
        [item.to_record() for item in universe],
        "arv2-preopen-universe-session-projection-v1",
    )
    control_root = _commitment_root(
        [item.to_record() for item in controls],
        "arv2-preopen-control-session-projection-v1",
    )
    if (
        value["universe_terminal_projection_sha256"] != universe_root
        or value["control_terminal_projection_sha256"] != control_root
    ):
        raise PreopenControlAcquisitionError("session commitment projection changed")
    census = _exact_fields(value["census"], _CENSUS_FIELDS, "output census")
    for name in _CENSUS_FIELDS:
        require_int(census[name], name, minimum=0)
    if (
        census["universe_terminal_count"] != sum(item.terminal_count for item in universe)
        or census["control_accepted_count"] != sum(item.accepted_count for item in controls)
        or census["control_refusal_count"] != sum(item.refusal_count for item in controls)
        or census["control_terminal_count"] != sum(item.terminal_count for item in controls)
        or census["control_terminal_count"] != census["universe_terminal_count"]
        or census["control_terminal_count"]
        != sum(item["row_count"] for item in output_shards)
    ):
        raise PreopenControlAcquisitionError("output census is not exhaustive")
    intermediates = _exact_fields(
        value["construction_intermediates"],
        _CONSTRUCTION_INTERMEDIATE_FIELDS,
        "construction intermediates",
    )
    if (
        intermediates["schema"] != _CONSTRUCTION_INTERMEDIATE_SCHEMA
        or intermediates["logical_terminal_order"]
        != "decision_session_then_security_id"
    ):
        raise PreopenControlAcquisitionError(
            "construction intermediate protocol changed"
        )
    for name in (
        "peer_aggregate_record_count", "market_session_commitment_count",
        "physical_terminal_shard_count", "q_data_measurement_count",
    ):
        require_int(intermediates[name], name, minimum=0)
    for name in (
        "peer_aggregate_projection_sha256", "market_session_projection_sha256",
        "q_data_measurement_projection_sha256",
    ):
        require_sha256(_exact_str(intermediates[name], name), name)
    if (
        intermediates["physical_terminal_shard_count"] != len(output_shards)
        or intermediates["market_session_commitment_count"] != len(controls)
        or intermediates["q_data_measurement_count"]
        != census["control_accepted_count"]
    ):
        raise PreopenControlAcquisitionError(
            "construction intermediate census does not reconcile"
        )
    capabilities = _exact_fields(value["capabilities"], _CAPABILITY_FIELDS, "output capabilities")
    for name in _CAPABILITY_FIELDS:
        require_exact_bool(capabilities[name], name)
    if any(capabilities.values()):
        raise PreopenControlAcquisitionError("persisted control receipt acquired a capability")
    return value, universe, controls


def _receipt_fingerprint(
    value: PreopenControlAcquisitionReceipt,
) -> tuple[object, ...]:
    return (
        id(value.universe_sessions),
        tuple(id(item) for item in value.universe_sessions),
        id(value.control_sessions),
        tuple(id(item) for item in value.control_sessions),
        value.output_manifest_bytes,
        value.review_receipt_bytes,
        tuple(
            getattr(value, field.name)
            for field in dataclasses.fields(PreopenControlAcquisitionReceipt)
            if field.name not in {
                "universe_sessions", "control_sessions", "output_manifest_bytes",
                "review_receipt_bytes",
            }
        ),
    )


def _review_hash(value: dict[str, Any]) -> str:
    seed = dict(value)
    seed["review_receipt_id"] = None
    seed["review_receipt_sha256"] = None
    return sha256_bytes(canonical_json_bytes(seed))


def _mint_physically_reviewed_preopen_control_acquisition_receipt_implementation(
    *, output_manifest_bytes: bytes, independent_review_receipt_bytes: bytes,
    qc_execution_receipt_id: str, qc_execution_receipt_sha256: str,
    external_review_pin_id: str, external_review_pin_sha256: str,
    output_shard_payload_projection_sha256: str,
) -> PreopenControlAcquisitionReceipt:
    """Private mint called only by the physical QC receipt loader."""

    manifest, universe, controls = _validate_manifest(output_manifest_bytes)
    manifest_hash = sha256_bytes(output_manifest_bytes)
    manifest_binding = {
        "artifact_id": f"arv2-preopen-control-output-{manifest_hash[:24]}",
        "content_sha256": manifest_hash,
        "artifact_sha256": manifest_hash,
        "byte_count": len(output_manifest_bytes),
    }
    review = _exact_fields(
        _canonical_object(independent_review_receipt_bytes, "independent review receipt"),
        _REVIEW_FIELDS,
        "independent review receipt",
    )
    if review["schema"] != REVIEW_RECEIPT_SCHEMA:
        raise PreopenControlAcquisitionError("independent review receipt schema changed")
    if _validate_binding(review["output_manifest"], "reviewed output manifest") != manifest_binding:
        raise PreopenControlAcquisitionError("review did not bind the exact output manifest")
    for name in (
        "input_source_inventory_sha256", "project_source_set_sha256",
        "output_shard_inventory_sha256", "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
    ):
        if review[name] != manifest[name]:
            raise PreopenControlAcquisitionError(f"review did not bind {name}")
    for name in _REVIEW_BOOLEAN_FIELDS:
        require_exact_bool(review[name], name)
        if review[name] is not True:
            raise PreopenControlAcquisitionError(f"independent review gate remains closed: {name}")
    digest = _review_hash(review)
    require_sha256(_exact_str(review["review_receipt_sha256"], "review_receipt_sha256"), "review_receipt_sha256")
    require_identifier(_exact_str(review["review_receipt_id"], "review_receipt_id"), "review_receipt_id")
    if (
        review["review_receipt_sha256"] != digest
        or review["review_receipt_id"] != f"arv2-preopen-control-review-{digest[:24]}"
    ):
        raise PreopenControlAcquisitionError("review receipt identity is not content-derived")
    input_binding = manifest["input_manifest"]
    universe_binding = manifest["eligible_universe_source"]
    sid_mapping_binding = manifest["qc_sid_mapping_source"]
    census = manifest["census"]
    capabilities = manifest["capabilities"]
    policy = manifest["source_policy"]
    run_authority = manifest["run_authority"]
    for name, value in (
        ("qc_execution_receipt_id", qc_execution_receipt_id),
        ("external_review_pin_id", external_review_pin_id),
    ):
        require_identifier(_exact_str(value, name), name)
    for name, value in (
        ("qc_execution_receipt_sha256", qc_execution_receipt_sha256),
        ("external_review_pin_sha256", external_review_pin_sha256),
        (
            "output_shard_payload_projection_sha256",
            output_shard_payload_projection_sha256,
        ),
    ):
        require_sha256(_exact_str(value, name), name)
    values: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "artifact_id": manifest_binding["artifact_id"],
        "artifact_sha256": manifest_hash,
        "content_sha256": manifest_hash,
        "byte_count": len(output_manifest_bytes),
        "input_manifest_id": input_binding["artifact_id"],
        "input_manifest_sha256": input_binding["content_sha256"],
        "input_manifest_byte_count": input_binding["byte_count"],
        "eligible_universe_artifact_id": universe_binding["artifact_id"],
        "eligible_universe_artifact_sha256": universe_binding["artifact_sha256"],
        "eligible_universe_artifact_byte_count": universe_binding["byte_count"],
        "qc_sid_mapping_artifact_id": sid_mapping_binding["artifact_id"],
        "qc_sid_mapping_artifact_sha256": sid_mapping_binding[
            "artifact_sha256"
        ],
        "qc_sid_mapping_artifact_byte_count": sid_mapping_binding["byte_count"],
        "qc_sid_mapping_row_count": sid_mapping_binding["row_count"],
        "input_source_inventory_sha256": manifest["input_source_inventory_sha256"],
        "input_role_bindings": tuple(
            tuple(item[name] for name in (
                "role", "descriptor_projection_sha256", "shard_count",
                "row_count", "compressed_byte_count", "uncompressed_byte_count",
            ))
            for item in manifest["input_role_bindings"]
        ),
        "truth_source_bindings": tuple(
            (item["kind"], item["artifact_id"], item["artifact_sha256"])
            for item in manifest["truth_source_bindings"]
        ),
        "rating_source_complete": policy["rating_source_complete"],
        "earnings_source_complete": policy["earnings_source_complete"],
        "guidance_source_complete": policy["guidance_source_complete"],
        "earnings_pit_policy_id": policy["earnings_pit_policy_id"],
        "guidance_clock_policy_id": policy["guidance_clock_policy_id"],
        "run_authority_id": run_authority["pin_id"],
        "run_authority_sha256": run_authority["pin_sha256"],
        "construction_resource_census_sha256": sha256_bytes(
            canonical_json_bytes(manifest["construction_resource_census"])
        ),
        "project_source_set_sha256": manifest["project_source_set_sha256"],
        "output_shard_inventory_sha256": manifest["output_shard_inventory_sha256"],
        "universe_terminal_projection_sha256": manifest["universe_terminal_projection_sha256"],
        "control_terminal_projection_sha256": manifest["control_terminal_projection_sha256"],
        "universe_sessions": universe,
        "control_sessions": controls,
        "universe_terminal_count": census["universe_terminal_count"],
        "control_accepted_count": census["control_accepted_count"],
        "control_refusal_count": census["control_refusal_count"],
        "control_terminal_count": census["control_terminal_count"],
        "review_receipt_id": review["review_receipt_id"],
        "review_receipt_sha256": digest,
        "qc_execution_receipt_id": qc_execution_receipt_id,
        "qc_execution_receipt_sha256": qc_execution_receipt_sha256,
        "external_review_pin_id": external_review_pin_id,
        "external_review_pin_sha256": external_review_pin_sha256,
        "output_shard_payload_projection_sha256": (
            output_shard_payload_projection_sha256
        ),
        "q_data_measurement_count": manifest["construction_intermediates"][
            "q_data_measurement_count"
        ],
        "q_data_measurement_projection_sha256": manifest[
            "construction_intermediates"
        ]["q_data_measurement_projection_sha256"],
        **{name: True for name in _REVIEW_BOOLEAN_FIELDS},
        "output_manifest_bytes": bytes(output_manifest_bytes),
        "review_receipt_bytes": bytes(independent_review_receipt_bytes),
        **capabilities,
    }
    result = object.__new__(PreopenControlAcquisitionReceipt)
    for name, item in values.items():
        object.__setattr__(result, name, item)
    return result


def load_reviewed_preopen_control_acquisition_receipt(
    *, output_manifest_bytes: bytes, independent_review_receipt_bytes: bytes
) -> PreopenControlAcquisitionReceipt:
    """Refuse content-only self-minting; use the physical QC loader instead."""

    del output_manifest_bytes, independent_review_receipt_bytes
    raise PreopenControlAcquisitionError(
        "physical output shards, QC execution receipt, and private external pin required"
    )


def _require_reviewed_preopen_control_acquisition_receipt_implementation(
    value: PreopenControlAcquisitionReceipt,
    authority: tuple[
        weakref.ReferenceType[PreopenControlAcquisitionReceipt],
        tuple[object, ...],
    ] | None,
) -> PreopenControlAcquisitionReceipt:
    if type(value) is not PreopenControlAcquisitionReceipt:
        raise PreopenControlAcquisitionError("pre-open acquisition receipt type changed")
    if authority is None or authority[0]() is not value:
        raise PreopenControlAcquisitionError("pre-open acquisition receipt is not loader-authenticated")
    manifest, universe, controls = _validate_manifest(value.output_manifest_bytes)
    review = _canonical_object(value.review_receipt_bytes, "independent review receipt")
    if (
        value.universe_sessions != universe
        or value.control_sessions != controls
        or value.artifact_sha256 != sha256_bytes(value.output_manifest_bytes)
        or value.content_sha256 != value.artifact_sha256
        or value.byte_count != len(value.output_manifest_bytes)
        or value.review_receipt_sha256 != _review_hash(review)
        or value.input_manifest_id != manifest["input_manifest"]["artifact_id"]
        or value.input_manifest_sha256 != manifest["input_manifest"]["content_sha256"]
        or value.input_manifest_byte_count != manifest["input_manifest"]["byte_count"]
        or value.eligible_universe_artifact_id
        != manifest["eligible_universe_source"]["artifact_id"]
        or value.eligible_universe_artifact_sha256
        != manifest["eligible_universe_source"]["artifact_sha256"]
        or value.eligible_universe_artifact_byte_count
        != manifest["eligible_universe_source"]["byte_count"]
        or value.qc_sid_mapping_artifact_id
        != manifest["qc_sid_mapping_source"]["artifact_id"]
        or value.qc_sid_mapping_artifact_sha256
        != manifest["qc_sid_mapping_source"]["artifact_sha256"]
        or value.qc_sid_mapping_artifact_byte_count
        != manifest["qc_sid_mapping_source"]["byte_count"]
        or value.qc_sid_mapping_row_count
        != manifest["qc_sid_mapping_source"]["row_count"]
        or value.input_role_bindings != tuple(
            tuple(item[name] for name in (
                "role", "descriptor_projection_sha256", "shard_count",
                "row_count", "compressed_byte_count", "uncompressed_byte_count",
            ))
            for item in manifest["input_role_bindings"]
        )
        or value.truth_source_bindings != tuple(
            (item["kind"], item["artifact_id"], item["artifact_sha256"])
            for item in manifest["truth_source_bindings"]
        )
        or value.rating_source_complete
        is not manifest["source_policy"]["rating_source_complete"]
        or value.earnings_source_complete
        is not manifest["source_policy"]["earnings_source_complete"]
        or value.guidance_source_complete
        is not manifest["source_policy"]["guidance_source_complete"]
        or value.earnings_pit_policy_id
        != manifest["source_policy"]["earnings_pit_policy_id"]
        or value.guidance_clock_policy_id
        != manifest["source_policy"]["guidance_clock_policy_id"]
        or value.run_authority_id != manifest["run_authority"]["pin_id"]
        or value.run_authority_sha256 != manifest["run_authority"]["pin_sha256"]
        or value.construction_resource_census_sha256 != sha256_bytes(
            canonical_json_bytes(manifest["construction_resource_census"])
        )
        or value.q_data_measurement_count
        != manifest["construction_intermediates"]["q_data_measurement_count"]
        or value.q_data_measurement_projection_sha256
        != manifest["construction_intermediates"][
            "q_data_measurement_projection_sha256"
        ]
        or _receipt_fingerprint(value) != authority[1]
    ):
        raise PreopenControlAcquisitionError("pre-open acquisition receipt changed")
    for name in (*_REVIEW_BOOLEAN_FIELDS, *_CAPABILITY_FIELDS):
        flag = getattr(value, name)
        if type(flag) is not bool:
            raise PreopenControlAcquisitionError("pre-open acquisition flag type changed")
        if name in _REVIEW_BOOLEAN_FIELDS and flag is not True:
            raise PreopenControlAcquisitionError("pre-open acquisition review gate reopened")
        if name in _CAPABILITY_FIELDS and flag is not False:
            raise PreopenControlAcquisitionError("pre-open acquisition acquired a capability")
    for name in (
        "rating_source_complete", "earnings_source_complete",
        "guidance_source_complete",
    ):
        if type(getattr(value, name)) is not bool:
            raise PreopenControlAcquisitionError(
                "pre-open source completeness flag type changed"
            )
    return value


def _make_preopen_acquisition_receipt_authority(
    mint_implementation,
    require_implementation,
):
    """Seal receipt registration and issue one minter to the exact I/O module."""

    records: tuple[
        tuple[
            int,
            weakref.ReferenceType[PreopenControlAcquisitionReceipt],
            tuple[object, ...],
        ],
        ...,
    ] = ()
    rlock_factory = threading.RLock
    getpid = os.getpid
    realpath = os.path.realpath
    exact_type = type
    exact_tuple = tuple
    any_true = any
    identity = id
    read_vars = vars
    zip_strict = zip
    system_module = sys
    module_registry = system_module.modules
    weak_reference = weakref.ref
    lock = rlock_factory()
    authority_pid = getpid()
    minter_claimed = False
    fingerprint = _receipt_fingerprint
    receipt_type = PreopenControlAcquisitionReceipt
    error_type = PreopenControlAcquisitionError
    expected_module_name = (
        "research.analyst_revisions_v2_qc.preopen_control_acquisition_io"
    )
    expected_module_path = realpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "analyst_revisions_v2_qc",
            "preopen_control_acquisition_io.py",
        )
    )
    expected_loader_name = (
        "load_physically_reviewed_preopen_control_acquisition_receipt"
    )
    function_type = exact_type(lambda: None)

    def current(value: PreopenControlAcquisitionReceipt):
        if getpid() != authority_pid:
            return None
        with lock:
            value_identity = identity(value)
            for key, reference, registered_fingerprint in records:
                if key == value_identity:
                    return reference, registered_fingerprint
            return None

    def require_reviewed_preopen_control_acquisition_receipt(
        value: PreopenControlAcquisitionReceipt,
    ) -> PreopenControlAcquisitionReceipt:
        return require_implementation(value, current(value))

    def forget(identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            records = exact_tuple(
                item
                for item in records
                if not (item[0] == identity and item[1] is reference)
            )

    def claim_preopen_acquisition_receipt_minter(loader_function):
        nonlocal minter_claimed
        try:
            import inspect

            caller = inspect.currentframe().f_back
            currentframe = inspect.currentframe
            caller_globals = caller.f_globals
            caller_name = caller_globals.get("__name__")
            caller_path = realpath(caller.f_code.co_filename)
            caller_code_name = caller.f_code.co_name
            registered = module_registry.get(expected_module_name)
            loader_code = loader_function.__code__
            loader_globals = loader_function.__globals__
            loader_module = loader_function.__module__
            loader_path = realpath(loader_code.co_filename)
            loader_name = loader_code.co_name
        except (AttributeError, OSError, TypeError):
            caller = None
            caller_globals = None
            caller_name = None
            caller_path = ""
            caller_code_name = ""
            registered = None
            loader_code = None
            loader_globals = None
            loader_module = None
            loader_path = ""
            loader_name = ""
        if (
            getpid() != authority_pid
            or caller_name != expected_module_name
            or registered is None
            or read_vars(registered) is not caller_globals
            or caller_path != expected_module_path
            or caller_code_name != "<module>"
            or exact_type(loader_function) is not function_type
            or loader_globals is not caller_globals
            or loader_module != expected_module_name
            or loader_path != expected_module_path
            or loader_name != expected_loader_name
        ):
            raise error_type("pre-open acquisition minter claim is loader-private")
        with lock:
            if minter_claimed:
                raise error_type("pre-open acquisition minter is already claimed")
            minter_claimed = True
        minter_pid = getpid()
        expected_loader_globals = loader_globals
        expected_loader_freevars = exact_tuple(loader_code.co_freevars)
        expected_loader_bindings = exact_tuple(
            (name, cell.cell_contents)
            for name, cell in zip_strict(
                expected_loader_freevars,
                loader_function.__closure__ or (),
                strict=True,
            )
            if name not in ("loader_guard", "receipt_minter")
        )

        def mint(**kwargs) -> PreopenControlAcquisitionReceipt:
            nonlocal records
            try:
                mint_caller = currentframe().f_back
                mint_caller_globals = mint_caller.f_globals
                mint_caller_code = mint_caller.f_code
                mint_caller_path = realpath(mint_caller_code.co_filename)
                mint_caller_locals = mint_caller.f_locals
            except (AttributeError, OSError, TypeError):
                mint_caller = None
                mint_caller_globals = None
                mint_caller_code = None
                mint_caller_path = ""
                mint_caller_locals = {}
            if (
                getpid() != minter_pid
                or mint_caller_code is not loader_code
                or mint_caller_globals is not expected_loader_globals
                or mint_caller_path != expected_module_path
                or system_module.modules is not module_registry
                or module_registry.get(expected_module_name) is not registered
                or read_vars(registered) is not mint_caller_globals
                or mint_caller_globals.get(expected_loader_name)
                is not loader_function
                or exact_tuple(mint_caller_code.co_freevars)
                != expected_loader_freevars
                or any_true(
                    mint_caller_locals.get(name) is not expected
                    for name, expected in expected_loader_bindings
                )
                or mint_caller_locals.get("receipt_minter") is not mint
            ):
                raise error_type(
                    "pre-open acquisition mint is loader-private"
                )
            del mint_caller
            value = mint_implementation(**kwargs)
            if exact_type(value) is not receipt_type:
                raise error_type("pre-open acquisition minter type changed")
            value_identity = identity(value)
            reference = weak_reference(
                value,
                lambda ref, key=value_identity: forget(key, ref),
            )
            with lock:
                if any_true(item[0] == value_identity for item in records):
                    raise error_type(
                        "pre-open acquisition identity is already registered"
                    )
                records = (
                    *records,
                    (value_identity, reference, fingerprint(value)),
                )
            return require_reviewed_preopen_control_acquisition_receipt(value)

        globals().pop("_claim_preopen_acquisition_receipt_minter", None)
        if caller_globals is not None:
            caller_globals.pop("_claim_preopen_acquisition_receipt_minter", None)
        del caller
        return mint

    def reset_after_fork() -> None:
        nonlocal records, lock
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return (
        claim_preopen_acquisition_receipt_minter,
        require_reviewed_preopen_control_acquisition_receipt,
    )


(
    _claim_preopen_acquisition_receipt_minter,
    require_reviewed_preopen_control_acquisition_receipt,
) = _make_preopen_acquisition_receipt_authority(
    _mint_physically_reviewed_preopen_control_acquisition_receipt_implementation,
    _require_reviewed_preopen_control_acquisition_receipt_implementation,
)
del _make_preopen_acquisition_receipt_authority
del _mint_physically_reviewed_preopen_control_acquisition_receipt_implementation
del _require_reviewed_preopen_control_acquisition_receipt_implementation


def acquisition_truth_source_binding_records(
    value: PreopenControlAcquisitionReceipt,
) -> tuple[dict[str, str], ...]:
    """Return the exact physically pinned truth-source identities."""

    require_reviewed_preopen_control_acquisition_receipt(value)
    return tuple(
        {"kind": kind, "artifact_id": artifact_id, "artifact_sha256": digest}
        for kind, artifact_id, digest in value.truth_source_bindings
    )


def acquisition_output_shard_descriptor_records(
    value: PreopenControlAcquisitionReceipt,
) -> tuple[dict[str, object], ...]:
    """Return independently authenticated descriptors for re-iterable shard reads."""

    require_reviewed_preopen_control_acquisition_receipt(value)
    manifest, _, _ = _validate_manifest(value.output_manifest_bytes)
    return tuple(dict(item) for item in manifest["output_shards"])


def acquisition_qc_sid_mapping_binding_record(
    value: PreopenControlAcquisitionReceipt,
) -> dict[str, object]:
    """Return the separately reviewed PIT Sharadar-to-QC SID source binding."""

    require_reviewed_preopen_control_acquisition_receipt(value)
    return {
        "artifact_id": value.qc_sid_mapping_artifact_id,
        "content_sha256": value.qc_sid_mapping_artifact_sha256,
        "artifact_sha256": value.qc_sid_mapping_artifact_sha256,
        "byte_count": value.qc_sid_mapping_artifact_byte_count,
        "row_count": value.qc_sid_mapping_row_count,
    }


def acquisition_q_data_measurement_projection_record(
    value: PreopenControlAcquisitionReceipt,
) -> dict[str, object]:
    """Return the physically verified same-key q-data measurement commitment."""

    require_reviewed_preopen_control_acquisition_receipt(value)
    return {
        "schema": "arv2-qdata-physical-measurement-projection-v1",
        "measurement_count": value.q_data_measurement_count,
        "projection_sha256": value.q_data_measurement_projection_sha256,
    }


def acquisition_receipt_artifact_binding_record(
    value: PreopenControlAcquisitionReceipt,
) -> dict[str, object]:
    """Return the exact ``ArtifactBinding``-compatible output manifest identity."""

    require_reviewed_preopen_control_acquisition_receipt(value)
    return {
        "artifact_id": value.artifact_id,
        "content_sha256": value.content_sha256,
        "artifact_sha256": value.artifact_sha256,
        "byte_count": value.byte_count,
    }


__all__ = [
    "BINARY_CONTROL_NAMES",
    "CONTRACT_BYTES",
    "CONTRACT_ID",
    "CONTRACT_SCHEMA",
    "CONTRACT_SHA256",
    "CONTINUOUS_CONTROL_NAMES",
    "CONTROL_NAMES",
    "CONTROL_SESSION_COMMITMENT_SCHEMA",
    "ControlSessionAcquisitionCommitment",
    "GUIDANCE_CLOCK_POLICY_ID",
    "OUTPUT_MANIFEST_SCHEMA",
    "OUTPUT_SHARD_SCHEMA",
    "OUTPUT_TERMINAL_SCHEMA",
    "PreopenControlAcquisitionError",
    "PreopenControlAcquisitionReceipt",
    "REVIEW_RECEIPT_SCHEMA",
    "SOURCE_VIEW_ID",
    "UNIVERSE_SESSION_COMMITMENT_SCHEMA",
    "UniverseSessionAcquisitionCommitment",
    "acquisition_receipt_artifact_binding_record",
    "acquisition_output_shard_descriptor_records",
    "acquisition_qc_sid_mapping_binding_record",
    "acquisition_q_data_measurement_projection_record",
    "acquisition_truth_source_binding_records",
    "load_reviewed_preopen_control_acquisition_receipt",
    "preopen_control_contract_record",
    "render_preopen_control_contract_bytes",
    "require_reviewed_preopen_control_acquisition_receipt",
]
