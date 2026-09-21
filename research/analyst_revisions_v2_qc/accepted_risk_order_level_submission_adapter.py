"""One-use private QuantConnect adapter for the two QQQ order-level runs.

This module is deliberately separate from the historical preliminary adapter.
It can create one private QC project, upload one authenticated compact package
with its activation manifest last, install one exact source projection,
compile, and launch one backtest.  Status polling never requests statistics.
A distinct one-use control permits exactly one completed-result read, from
which only the two profile-bound ``ARV2_*`` aggregate statistics are selected.

It has no deployment, paper/live brokerage, cancellation, raw-order, log,
chart, or provider-row endpoint.  ``MarketOnOpenOrder`` exists only inside the
reviewed backtest source projection; this host adapter never submits an order.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import time
import types
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Callable, Mapping, NoReturn

from research.analyst_revisions_v2.canonical import canonical_json_bytes

from . import accepted_risk_delta_order_package as delta_package_builder
from . import accepted_risk_order_level_forced_exit as forced_exit_builder
from . import accepted_risk_order_level_qc_projection as projection_builder
from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_qqq_order_level_qc_runtime as runtime_builder
from . import accepted_risk_qqq_order_level_v12_qc_runtime as v12_runtime_builder
from . import accepted_risk_qqq_order_level_v13_qc_runtime as v13_runtime_builder
from . import accepted_risk_qqq_order_level_v14_qc_runtime as v14_runtime_builder
from . import accepted_risk_qqq_order_level_v15_qc_runtime as v15_runtime_builder
from . import formal_submission_adapter as formal
from .formal_qc_transport import FormalQcTransport
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_formal_execution_owner_signature,
    require_formal_result_read_owner_signature,
)


class AcceptedRiskOrderLevelSubmissionError(ValueError):
    """The plan, one-use state, QC envelope, or aggregate result changed."""


class AcceptedRiskOrderLevelSubmissionLocked(RuntimeError):
    """A durable one-use action was spent and is never retried implicitly."""

    def __init__(self, phase: str, control_id: str, detail: str) -> None:
        super().__init__(
            f"{phase}: {detail}; order-level one-use control remains consumed"
        )
        self.phase = phase
        self.control_id = control_id


class AcceptedRiskOrderLevelTerminalFailure(RuntimeError):
    """The exact backtest reached a non-success terminal state."""

    def __init__(self, receipt: "OrderLevelTerminalStatus") -> None:
        super().__init__("order-level backtest reached authenticated terminal failure")
        self.receipt = receipt


PLAN_SCHEMA = "arv2-order-level-qc-submission-plan-v1"
UPLOAD_SCHEMA = "arv2-order-level-qc-upload-entry-v1"
LAUNCH_CONTROL_SCHEMA = "arv2-order-level-qc-launch-one-use-control-v2"
LAUNCH_CHECKPOINT_SCHEMA = "arv2-order-level-qc-launch-checkpoint-v1"
LAUNCH_RECOVERY_CONTROL_SCHEMA = (
    "arv2-order-level-qc-launch-recovery-one-use-control-v1"
)
LAUNCH_SCHEMA = "arv2-order-level-qc-launch-receipt-v1"
TERMINAL_SCHEMA = "arv2-order-level-qc-terminal-status-v1"
STATUS_POLL_CHECKPOINT_SCHEMA = (
    "arv2-order-level-qc-status-poll-checkpoint-v1"
)
RESULT_CONTROL_SCHEMA = "arv2-order-level-qc-result-one-use-control-v2"
RESULT_SCHEMA = "arv2-order-level-qc-aggregate-result-v1"
EXECUTION_AUTHORITY_SCHEMA = "arv2-order-level-qc-execution-authority-v1"
RESULT_READ_AUTHORITY_SCHEMA = "arv2-order-level-qc-result-read-authority-v1"

PROFILE_IDS = (
    "arv2-qqq-order-level-tilt-2025-cutoff-v4",
    "arv2-qqq-order-level-tilt-2026-cutoff-v4",
    "arv2-qqq-order-level-tilt-2025-cutoff-v5",
    "arv2-qqq-order-level-tilt-2026-cutoff-v5",
    "arv2-qqq-order-level-tilt-2025-cutoff-v6",
    "arv2-qqq-order-level-tilt-2026-cutoff-v6",
    "arv2-qqq-order-level-tilt-2025-cutoff-v7",
    "arv2-qqq-order-level-tilt-2026-cutoff-v7",
    "arv2-qqq-order-level-tilt-2025-cutoff-v8",
    "arv2-qqq-order-level-tilt-2026-cutoff-v8",
    "arv2-qqq-order-level-tilt-2025-cutoff-v9",
    "arv2-qqq-order-level-tilt-2026-cutoff-v9",
    "arv2-qqq-order-level-tilt-2025-cutoff-v10",
    "arv2-qqq-order-level-tilt-2026-cutoff-v10",
    "arv2-qqq-order-level-tilt-2025-cutoff-v11",
    "arv2-qqq-order-level-tilt-2026-cutoff-v11",
    "arv2-qqq-order-level-tilt-2025-cutoff-v12",
    "arv2-qqq-order-level-tilt-2026-cutoff-v12",
    "arv2-qqq-order-level-tilt-2025-cutoff-v13",
    "arv2-qqq-order-level-tilt-2026-cutoff-v13",
    "arv2-qqq-order-level-tilt-2025-cutoff-v14",
    "arv2-qqq-order-level-tilt-2026-cutoff-v14",
    "arv2-qqq-order-level-tilt-2025-cutoff-v15",
    "arv2-qqq-order-level-tilt-2026-cutoff-v15",
)
PROXY_PROFILE_IDS = PROFILE_IDS[2:]
ROLLOVER_PROFILE_IDS = tuple(v13_runtime_builder.ROLLOVER_PROFILE_IDS)
DIAGNOSTIC_PROFILE_IDS = tuple(v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS)
ACCOUNT_PROFILE_IDS = tuple(v15_runtime_builder.ACCOUNT_PROFILE_IDS)
FORCED_EXIT_PROFILE_IDS = (
    tuple(v12_runtime_builder.FORCED_EXIT_PROFILE_IDS)
    + ROLLOVER_PROFILE_IDS
    + DIAGNOSTIC_PROFILE_IDS
    + ACCOUNT_PROFILE_IDS
)
_PINNED_PROFILE_CENSUS = (
    (PROFILE_IDS[0], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[1], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[2], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[3], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[4], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[5], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[6], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[7], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[8], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[9], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[10], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[11], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[12], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[13], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[14], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[15], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[16], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[17], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[18], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[19], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[20], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[21], "2026-01-05", 39, 178, 177),
    (PROFILE_IDS[22], "2025-01-03", 91, 428, 427),
    (PROFILE_IDS[23], "2026-01-05", 39, 178, 177),
)
MAX_PROJECT_NAME_BYTES = 100
MAX_BACKTEST_NAME_BYTES = 200
MAX_CONTROL_BYTES = 1024 * 1024
MAX_STATISTIC_BYTES = 4096
MAX_TICKET_STATISTIC_BYTES = 8192
_TICKET_STATISTIC_PROFILE_IDS = (
    tuple(runtime_builder.TICKET_PROFILE_IDS)
    + tuple(runtime_builder.REFLECTED_TICKET_PROFILE_IDS)
    + FORCED_EXIT_PROFILE_IDS
)
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 1_440
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
DEFAULT_NOTEBOOK = "research.ipynb"
RECOVERED_LAUNCH_INITIAL_STATUS = "RECOVERED_BY_STATISTICS_FREE_LIST"


def _maximum_statistic_bytes(
    profile_id,
    _ticket_ids=_TICKET_STATISTIC_PROFILE_IDS,
    _legacy_limit=MAX_STATISTIC_BYTES,
    _ticket_limit=MAX_TICKET_STATISTIC_BYTES,
):
    # V10+ retain the exact aggregate instead of trimming decimals or hashes.
    return (
        _ticket_limit if profile_id in _ticket_ids else _legacy_limit
    )

EXECUTION_ENDPOINT_BUDGET_NAMES = frozenset(
    {
        "authenticate",
        "projects/read",
        "projects/create",
        "object/set",
        "object/properties",
        "files/read",
        "files/create",
        "files/update",
        "files/delete",
        "compile/create",
        "compile/read",
        "backtests/create",
    }
)
STATUS_ENDPOINT_BUDGET_NAMES = frozenset({"backtests/list"})
RESULT_ENDPOINT_BUDGET_NAMES = frozenset({"backtests/read"})
FORBIDDEN_ENDPOINT_TOKENS = frozenset(
    {
        "broker",
        "cancel",
        "deploy",
        "deployment",
        "live",
        "log",
        "order",
        "paper",
    }
)

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_RESULT_DECIMAL_TEXT = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z"
)

_PINNED_REQUIRE_PACKAGE = package_builder.require_accepted_risk_preliminary_package
_PINNED_ITER_UPLOADS = package_builder.iter_accepted_risk_preliminary_upload_objects
_PINNED_REQUIRE_PROJECTION = (
    projection_builder.require_accepted_risk_order_level_qc_projection
)
_PINNED_REQUIRE_LEGACY_PROFILE = runtime_builder.require_qqq_order_level_profile
_PINNED_REQUIRE_V12_PROFILE = v12_runtime_builder.require_qqq_order_level_profile
_PINNED_REQUIRE_V13_PROFILE = v13_runtime_builder.require_qqq_order_level_profile
_PINNED_REQUIRE_V14_PROFILE = v14_runtime_builder.require_qqq_order_level_profile
_PINNED_REQUIRE_V15_PROFILE = v15_runtime_builder.require_qqq_order_level_profile
_PINNED_EXPECTED_LEGACY_NAMES = (
    runtime_builder.expected_custom_summary_statistic_names
)
_PINNED_EXPECTED_V12_NAMES = (
    v12_runtime_builder.expected_custom_summary_statistic_names
)
_PINNED_EXPECTED_V13_NAMES = (
    v13_runtime_builder.expected_custom_summary_statistic_names
)
_PINNED_EXPECTED_V14_NAMES = (
    v14_runtime_builder.expected_custom_summary_statistic_names
)
_PINNED_EXPECTED_V15_NAMES = (
    v15_runtime_builder.expected_custom_summary_statistic_names
)
_PINNED_RUNTIME_PROFILE_IDS = (
    tuple(runtime_builder.PROFILE_IDS)
    + tuple(v12_runtime_builder.FORCED_EXIT_PROFILE_IDS)
    + tuple(v13_runtime_builder.ROLLOVER_PROFILE_IDS)
    + tuple(v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS)
    + tuple(v15_runtime_builder.ACCOUNT_PROFILE_IDS)
)
_PINNED_META_STATISTIC_NAME = runtime_builder.META_STATISTIC_NAME
_PINNED_AGGREGATES_STATISTIC_NAME = runtime_builder.AGGREGATES_STATISTIC_NAME
_PINNED_LEGACY_META_SCHEMA = "arv2-qqq-order-level-tilt-runtime-meta-v1"
_PINNED_FORCED_EXIT_META_SCHEMA = "arv2-qqq-order-level-tilt-runtime-meta-v2"
_PINNED_DIAGNOSTIC_META_SCHEMA = "arv2-qqq-order-level-tilt-runtime-meta-v3"
_PINNED_RUNTIME_SUMMARY_SCHEMA = runtime_builder.SUMMARY_SCHEMA
_PINNED_PROXY_SUMMARY_SCHEMA = runtime_builder.PROXY_SUMMARY_SCHEMA
_PINNED_FORCED_EXIT_SUMMARY_SCHEMA = v12_runtime_builder.FORCED_EXIT_SUMMARY_SCHEMA
_PINNED_DIAGNOSTIC_SUMMARY_SCHEMA = v14_runtime_builder.DIAGNOSTIC_SUMMARY_SCHEMA
_PINNED_ACCOUNT_SUMMARY_SCHEMA = v15_runtime_builder.ACCOUNT_SUMMARY_SCHEMA
_PINNED_RETIRED_TARGET_PATH_SCHEMA = (
    v15_runtime_builder.RETIRED_TARGET_PATH_SCHEMA
)
_PINNED_EXACT_COMPLEMENT_POLICY = v14_runtime_builder.EXACT_COMPLEMENT_POLICY
_PINNED_EXACT_COMPLEMENT_DECIMAL_PRECISION = (
    v14_runtime_builder.EXACT_COMPLEMENT_DECIMAL_PRECISION
)
_PINNED_SKIPPED_UNPRICED_EVIDENCE_POLICY = (
    v14_runtime_builder.SKIPPED_UNPRICED_EVIDENCE_POLICY
)
_PINNED_SKIPPED_UNPRICED_EVIDENCE_SCHEMA = (
    v14_runtime_builder.SKIPPED_UNPRICED_EVIDENCE_SCHEMA
)
_PINNED_SKIPPED_UNPRICED_PATH_SCHEMA = (
    v14_runtime_builder.SKIPPED_UNPRICED_PATH_SCHEMA
)
_PINNED_MISSING_SECURITY_PATH_SCHEMA = (
    v14_runtime_builder.MISSING_SECURITY_PATH_SCHEMA
)
_PINNED_MAXIMUM_RETAINED_SKIPPED_DECISIONS = (
    v14_runtime_builder.MAXIMUM_RETAINED_SKIPPED_DECISIONS
)
_PINNED_MAXIMUM_RETAINED_MISSING_SECURITY_HASHES = (
    v14_runtime_builder.MAXIMUM_RETAINED_MISSING_SECURITY_HASHES
)
_PINNED_FORCED_DELISTING_SUMMARY_SCHEMA = (
    forced_exit_builder.FORCED_DELISTING_SUMMARY_SCHEMA
)
_PINNED_REQUIRE_TRANSPORT = formal._require_concrete_transport
_PINNED_TRANSPORT_CALL = formal._transport_call


def _pinned_require_profile(
    profile_id,
    _v15_ids=ACCOUNT_PROFILE_IDS,
    _v14_ids=DIAGNOSTIC_PROFILE_IDS,
    _v13_ids=ROLLOVER_PROFILE_IDS,
    _v12_ids=tuple(v12_runtime_builder.FORCED_EXIT_PROFILE_IDS),
    _v15_requirer=_PINNED_REQUIRE_V15_PROFILE,
    _v14_requirer=_PINNED_REQUIRE_V14_PROFILE,
    _v13_requirer=_PINNED_REQUIRE_V13_PROFILE,
    _v12_requirer=_PINNED_REQUIRE_V12_PROFILE,
    _legacy_requirer=_PINNED_REQUIRE_LEGACY_PROFILE,
):
    return (
        _v15_requirer(profile_id)
        if profile_id in _v15_ids
        else _v14_requirer(profile_id)
        if profile_id in _v14_ids
        else _v13_requirer(profile_id)
        if profile_id in _v13_ids
        else _v12_requirer(profile_id)
        if profile_id in _v12_ids
        else _legacy_requirer(profile_id)
    )


def _pinned_expected_names(
    profile_id,
    _v15_ids=ACCOUNT_PROFILE_IDS,
    _v14_ids=DIAGNOSTIC_PROFILE_IDS,
    _v13_ids=ROLLOVER_PROFILE_IDS,
    _v12_ids=tuple(v12_runtime_builder.FORCED_EXIT_PROFILE_IDS),
    _v15_names=_PINNED_EXPECTED_V15_NAMES,
    _v14_names=_PINNED_EXPECTED_V14_NAMES,
    _v13_names=_PINNED_EXPECTED_V13_NAMES,
    _v12_names=_PINNED_EXPECTED_V12_NAMES,
    _legacy_names=_PINNED_EXPECTED_LEGACY_NAMES,
):
    return (
        _v15_names(profile_id)
        if profile_id in _v15_ids
        else _v14_names(profile_id)
        if profile_id in _v14_ids
        else _v13_names(profile_id)
        if profile_id in _v13_ids
        else _v12_names(profile_id)
        if profile_id in _v12_ids
        else _legacy_names(profile_id)
    )


# Retain the reviewed mutation surface name; action closures bind the exact
# combined dispatcher above and therefore remain independent of rebinding.
_PINNED_EXPECTED_NAMES = _pinned_expected_names


def _make_exact_order_transport_operations():
    """Seal this action path to formal's exact reviewed method surface."""

    formal_module = formal
    transport_map = formal_module._PINNED_TRANSPORT_METHODS
    exact_bindings = tuple(transport_map.items())
    exact_transport_type = FormalQcTransport
    exact_mapping_type = type(transport_map)
    formal_verifier = formal_module._require_concrete_transport
    get_attribute = getattr
    exact_tuple = tuple
    exact_type = type
    exact_length = len
    zip_values = zip
    error_type = AcceptedRiskOrderLevelSubmissionError
    missing = object()

    def require_exact_order_transport(
        value: FormalQcTransport,
    ) -> FormalQcTransport:
        current_map = get_attribute(
            formal_module, "_PINNED_TRANSPORT_METHODS", missing
        )
        current_bindings = (
            exact_tuple(current_map.items())
            if exact_type(current_map) is exact_mapping_type
            else ()
        )
        if (
            current_map is not transport_map
            or exact_length(current_bindings) != exact_length(exact_bindings)
            or any(
                actual_name is not expected_name
                or actual_implementation is not expected_implementation
                for (actual_name, actual_implementation),
                (expected_name, expected_implementation) in zip_values(
                    current_bindings, exact_bindings,
                )
            )
            or any(
                get_attribute(exact_transport_type, name, missing)
                is not implementation
                for name, implementation in exact_bindings
            )
        ):
            raise error_type("exact order-level transport surface changed")
        try:
            return formal_verifier(value)
        except Exception as exc:
            raise error_type("exact order-level transport surface changed") from exc

    def transport_call(
        client: FormalQcTransport, capability, method: str, *args,
    ) -> object:
        require_exact_order_transport(client)
        for name, implementation in exact_bindings:
            if method == name:
                return implementation(client, capability, *args)
        raise error_type("order-level transport method is not allowlisted")

    return require_exact_order_transport, transport_call


(
    _ORDER_TRANSPORT_VERIFIER,
    _ORDER_TRANSPORT_CALL,
) = _make_exact_order_transport_operations()
del _make_exact_order_transport_operations
_PINNED_READ_PROJECTS = formal._read_project_inventory
_PINNED_PROJECT_RECORD = formal._project_record
_PINNED_CREATED_PROJECT = formal._created_project
_PINNED_READ_FILES = formal._read_files
_PINNED_SUCCESS = formal._success
_PINNED_OBJECT_METADATA = formal._object_metadata_matches
_PINNED_COMPILE_ID = formal._compile_id
_PINNED_COMPILE_STATE = formal._compile_state
_PINNED_CREATED_BACKTEST = formal._created_backtest
_PINNED_PARSE_STATUS = formal.parse_statistics_free_backtest_list
_PINNED_PARSE_UNIQUE_RUN = formal._parse_statistics_free_unique_project_run
_PINNED_COMPILE_TERMINAL_STATES = formal.COMPILE_TERMINAL_STATES
_PINNED_BACKTEST_TERMINAL_STATES = formal.BACKTEST_TERMINAL_STATUSES
_PINNED_BACKTEST_STATUS_KEYS = formal._BACKTEST_STATUS_KEYS
_PINNED_DISCARDED_BACKTEST_KEYS = formal._DISCARDED_BACKTEST_SUMMARY_KEYS


def _capture_runtime_profile_bindings():
    bindings = []
    for census in _PINNED_PROFILE_CENSUS:
        profile_id = census[0]
        profile = _pinned_require_profile(profile_id)
        bindings.append(
            (
                profile_id,
                profile["profile_sha256"],
                profile["score_source_view_id"],
                *census[1:],
                tuple(_pinned_expected_names(profile_id)),
            )
        )
    return tuple(bindings)


_PINNED_RUNTIME_PROFILE_BINDINGS = _capture_runtime_profile_bindings()
del _capture_runtime_profile_bindings

_META_FIELDS = frozenset(
    {
        "schema", "profile_id", "profile_sha256", "package_id",
        "package_sha256", "activation_manifest_sha256",
        "symbol_resolution_id", "symbol_resolution_sha256",
        "score_source_view_id",
        "aggregates_sha256", "result_transport", "backtest_only",
        "simulated_order_submission", "live_orders", "paper_orders",
        "funded_orders", "deployment", "trading",
    }
)
_AGGREGATE_FIELDS = frozenset(
    {
        "schema", "score_source_view_id", "decision_count", "completed_rebalance_count",
        "submitted_order_count", "skipped_unpriced_decision_count",
        "tilt_enabled_count", "tilt_underfilled_count",
        "mean_tilted_name_count", "mean_one_way_active_share",
        "pit_history_call_count", "pit_source_row_count",
        "named_figi_refusal_count", "modeled_fee_bps_per_side",
        "modeled_fee_amount", "lifecycle_modeled_fee_basis",
        "engine_fee_model_basis", "total_filled_notional",
        "actual_engine_fee_amount",
        "actual_engine_fee_effective_bps_per_side",
        "modeled_minus_actual_fee_amount", "fee_mismatch",
        "filled_order_count_sum", "canceled_order_count_sum",
        "invalid_order_count_sum", "orders_with_any_fill_count_sum",
        "mean_reference_mark_target_weight_l1_error",
        "maximum_reference_mark_target_weight_l1_error",
        "execution_failure", "run_valid", "coverage_decision_count",
        "positive_weight_member_count_sum",
        "resolved_positive_weight_member_count_sum",
        "mean_resolved_member_count_ratio",
        "mean_resolved_constituent_weight_ratio",
        "minimum_resolved_member_count_ratio",
        "minimum_resolved_constituent_weight_ratio",
        "minimum_required_resolved_constituent_weight_ratio",
        "target_weight_basis", "pit_target_weight_path_sha256",
        "mean_positive_constituent_weight_total",
        "minimum_positive_constituent_weight_total",
        "maximum_positive_constituent_weight_total",
        "minimum_required_positive_constituent_weight_total",
        "maximum_allowed_positive_constituent_weight_total",
        "maximum_constituent_snapshot_age_sessions",
        "pit_coverage_path_sha256", "starting_equity",
        "ending_equity", "strategy_total_return",
        "strategy_maximum_drawdown", "strategy_annualized_volatility",
        "strategy_zero_rate_sharpe", "mean_gross_exposure",
        "mean_cash_weight", "strategy_equity_path_sha256",
        "QQQ_total_return", "QQQ_normalization_mode", "QQQ_observation",
        "QQQ_first_execution_session", "QQQ_target_gross_exposure",
        "QQQ_entry_fee_bps_per_side",
        "QQQ_maximum_drawdown", "QQQ_annualized_volatility",
        "QQQ_zero_rate_sharpe", "strategy_minus_QQQ_total_return",
        "QQQ_observation_count", "QQQ_return_interval_count",
        "QQQ_raw_observation_sha256", "QQQ_return_path_sha256",
        "QQQ_calendar_close_total_return",
        "QQQ_calendar_close_observation_count",
        "QQQ_calendar_close_raw_observation_sha256",
        "QQQ_calendar_close_return_path_sha256",
        "order_lifecycle_sha256", "raw_order_rows_in_summary",
        "raw_security_rows_in_summary", "backtest_only",
        "simulated_orders", "live_orders", "trading",
    }
)
_PROXY_AGGREGATE_FIELDS = _AGGREGATE_FIELDS | frozenset({
    "qqq_proxy_overlap_disclosure",
    "mean_qqq_proxy_constituent_weight_ratio",
    "minimum_qqq_proxy_constituent_weight_ratio",
    "maximum_qqq_proxy_constituent_weight_ratio",
})
_FORCED_EXIT_AGGREGATE_FIELDS = _PROXY_AGGREGATE_FIELDS | frozenset({
    "engine_forced_delisting",
    "forced_exit_invalidated_pending_rebalance_count",
})
_DIAGNOSTIC_AGGREGATE_FIELDS = _FORCED_EXIT_AGGREGATE_FIELDS | frozenset({
    "qqq_proxy_complement_policy",
    "skipped_unpriced_decision_evidence_policy",
    "skipped_unpriced_decision_evidence",
})
_ACCOUNT_AGGREGATE_FIELDS = _DIAGNOSTIC_AGGREGATE_FIELDS | frozenset({
    "delisted_zero_holding_target_retirement_count",
    "delisted_zero_holding_target_retirement_decision_count",
    "delisted_zero_holding_target_retired_weight_total",
    "delisted_zero_holding_target_path_sha256",
    "terminal_account_observation_adjustment",
    "terminal_account_observation_prior_equity",
    "terminal_account_observation_equity",
})
_FORCED_DELISTING_FIELDS = frozenset({
    "schema", "order_count", "event_count", "fill_event_count",
    "terminal_order_count", "absolute_filled_quantity", "filled_notional",
    "actual_engine_fee_amount", "accounting_complete", "ledger_sha256",
    "raw_order_rows_in_summary", "raw_security_rows_in_summary",
})
_SKIPPED_UNPRICED_EVIDENCE_FIELDS = frozenset({
    "schema", "skipped_decision_count", "retained_decision_count",
    "omitted_decision_count", "records", "path_sha256",
})
_SKIPPED_UNPRICED_RECORD_FIELDS = frozenset({
    "decision_session", "missing_security_count",
    "retained_missing_security_sha256s",
    "omitted_missing_security_count", "missing_security_path_sha256",
})


def _error(message: str) -> NoReturn:
    raise AcceptedRiskOrderLevelSubmissionError(message)


def _make_canonicalizer(dumps, error_type):
    def canonical(value: object) -> bytes:
        try:
            return dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise error_type(
                "order-level control is not canonical ASCII JSON"
            ) from exc

    return canonical


_canonical = _make_canonicalizer(
    json.dumps, AcceptedRiskOrderLevelSubmissionError
)
del _make_canonicalizer


def _code_global_names(code):
    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            names.update(_code_global_names(constant))
    return names


def _seal_local_function_graph(*roots):
    """Clone the reachable adapter-function graph over one globals snapshot."""

    module_name = __name__
    module_globals = globals()
    pending = [
        value
        for value in roots
        if isinstance(value, types.FunctionType)
        and value.__module__ == module_name
    ]
    discovered = []
    seen = set()
    while pending:
        function = pending.pop()
        if id(function) in seen:
            continue
        seen.add(id(function))
        discovered.append(function)
        for name in _code_global_names(function.__code__):
            dependency = function.__globals__.get(name)
            if (
                isinstance(dependency, types.FunctionType)
                and dependency.__module__ == module_name
            ):
                pending.append(dependency)
        for value in function.__defaults__ or ():
            if (
                isinstance(value, types.FunctionType)
                and value.__module__ == module_name
            ):
                pending.append(value)
        for value in (function.__kwdefaults__ or {}).values():
            if (
                isinstance(value, types.FunctionType)
                and value.__module__ == module_name
            ):
                pending.append(value)

    sealed_globals = dict(module_globals)
    clones = {}
    for function in discovered:
        clone = types.FunctionType(
            function.__code__,
            sealed_globals,
            name=function.__name__,
            argdefs=function.__defaults__,
            closure=function.__closure__,
        )
        clone.__doc__ = function.__doc__
        clone.__qualname__ = function.__qualname__
        clone.__annotations__ = dict(function.__annotations__)
        clones[function] = clone
    by_identity = {id(original): clone for original, clone in clones.items()}
    for name, value in tuple(sealed_globals.items()):
        replacement = by_identity.get(id(value))
        if replacement is not None:
            sealed_globals[name] = replacement
    for original, clone in clones.items():
        clone.__defaults__ = tuple(
            by_identity.get(id(value), value)
            for value in original.__defaults__ or ()
        ) or None
        clone.__kwdefaults__ = {
            name: by_identity.get(id(value), value)
            for name, value in (original.__kwdefaults__ or {}).items()
        } or None
    return tuple(clones.get(value, value) for value in roots)


def _make_module_dependency_guard(label, *roots):
    """Pin every lane-global lookup reachable from exact action roots."""

    module_prefix = "research.analyst_revisions_v2"
    missing = object()
    pending = [
        value for value in roots
        if isinstance(value, types.FunctionType)
        and str(value.__module__).startswith(module_prefix)
    ]
    seen = set()
    expected = {}
    while pending:
        function = pending.pop()
        if id(function) in seen:
            continue
        seen.add(id(function))
        namespace = function.__globals__
        for name in _code_global_names(function.__code__):
            dependency = namespace.get(name, missing)
            expected[(id(namespace), name)] = (
                str(function.__module__),
                namespace,
                name,
                dependency,
            )
            if (
                isinstance(dependency, types.FunctionType)
                and str(dependency.__module__).startswith(module_prefix)
            ):
                pending.append(dependency)
        for value in (
            *(function.__defaults__ or ()),
            *(function.__kwdefaults__ or {}).values(),
            *(
                cell.cell_contents
                for cell in function.__closure__ or ()
            ),
        ):
            if (
                isinstance(value, types.FunctionType)
                and str(value.__module__).startswith(module_prefix)
            ):
                pending.append(value)

    bindings = tuple(
        sorted(expected.values(), key=lambda item: (item[0], item[2]))
    )
    error_type = AcceptedRiskOrderLevelSubmissionError

    def require_current_dependencies():
        if any(
            namespace.get(name, missing) is not value
            for _module, namespace, name, value in bindings
        ):
            raise error_type(label + " dependency changed")

    return require_current_dependencies


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > MAX_CONTROL_BYTES:
        _error(f"{name} exceeded its exact byte bound")
    parse_failed = False
    try:
        value = json.loads(payload.decode("ascii"), parse_constant=lambda _v: None)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Do not retain JSONDecodeError.doc or decoder input in an exception
        # chain.  The refusal is raised only after the caught exception has
        # left scope, so even recursive cause/context inspection is value-free.
        parse_failed = True
        value = None
    if parse_failed:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} is not canonical ASCII JSON"
        ) from None
    if type(value) is not dict or _canonical(value) != payload:
        _error(f"{name} is not an exact canonical object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(f"{name} is not an exact SHA-256")
    return value


def _safe_name(value: object, name: str, maximum: int) -> str:
    if (
        type(value) is not str
        or _SAFE_NAME.fullmatch(value) is None
        or len(value.encode("ascii")) > maximum
    ):
        _error(f"{name} is not an exact safe name")
    return value


def _result_decimal(value: object, name: str, *, optional=False) -> Decimal | None:
    if optional and value is None:
        return None
    if (
        type(value) is not str
        or not value
        or len(value) > 256
        or value == "-0"
        or _RESULT_DECIMAL_TEXT.fullmatch(value) is None
    ):
        _error(f"{name} is not an exact decimal string")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} is not an exact decimal string"
        ) from exc
    if not result.is_finite():
        _error(f"{name} is not an exact decimal string")
    return result


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        _error(f"{name} is not an exact UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} is not an exact UTC instant"
        ) from exc
    if parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != value:
        _error(f"{name} is not an exact UTC instant")
    return value


def _result_session(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 10:
        _error(f"{name} is not an exact session date")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} is not an exact session date"
        ) from exc
    if parsed.date().isoformat() != value or parsed.time().isoformat() != "00:00:00":
        _error(f"{name} is not an exact session date")
    return value


def _private_directory(value: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _error("order-level control directory must be an exact absolute Path")
    if value.exists():
        mode = value.stat(follow_symlinks=False).st_mode
        if (
            stat.S_ISLNK(mode)
            or not stat.S_ISDIR(mode)
            or stat.S_IMODE(mode) != 0o700
            or value.stat(follow_symlinks=False).st_uid != os.getuid()
        ):
            _error("order-level control directory is not private")
    else:
        value.mkdir(mode=0o700, parents=True)
    return value


def _read_private(path: Path, name: str) -> bytes:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or path.parent != _private_directory(path.parent)
    ):
        _error(f"{name} path changed")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} is unavailable"
        ) from exc
    try:
        before = os.fstat(descriptor)
        payload = os.read(descriptor, MAX_CONTROL_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        "st_dev", "st_ino", "st_uid", "st_mode", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if (
        any(getattr(before, field) != getattr(after, field) for field in identity)
        or not stat.S_ISREG(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or before.st_size != len(payload)
        or not 0 < len(payload) <= MAX_CONTROL_BYTES
    ):
        _error(f"{name} is not one stable owner-only regular file")
    return payload


def _write_private_once(path: Path, payload: bytes, name: str) -> None:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or type(payload) is not bytes
        or not payload
        or len(payload) > MAX_CONTROL_BYTES
    ):
        _error(f"{name} write boundary changed")
    directory = _private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(path, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            f"{name} already exists or could not be published"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory_descriptor = os.open(
        directory, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    if _read_private(path, name) != payload:
        _error(f"{name} changed after publication")


def _write_once(path: Path, payload: bytes, name: str) -> None:
    try:
        _write_private_once(path, payload, name)
    except AcceptedRiskOrderLevelSubmissionError as exc:
        raise AcceptedRiskOrderLevelSubmissionLocked(
            name,
            hashlib.sha256(payload).hexdigest(),
            "control already exists or is unavailable",
        ) from exc


def _identified(schema: str, prefix: str, record: dict[str, object]):
    seed = {"schema": schema, "id": None, "sha256": None, **record}
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    identity = prefix + digest[:24]
    return identity, digest, _canonical({**seed, "id": identity, "sha256": digest})


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelUploadEntry:
    schema: str
    role: str
    ordinal: int
    object_store_key: str
    byte_count: int
    content_sha256: str
    content_md5: str
    activation_manifest: bool


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str = dataclasses.field(repr=False)
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    control_directory: Path
    delta_lineage_sha256: str
    package_id: str
    package_sha256: str
    projection_id: str
    projection_sha256: str
    profile_id: str
    profile_sha256: str
    upload_entries: tuple[OrderLevelUploadEntry, ...]
    source_files: tuple[projection_builder.OrderLevelQcSourceFile, ...]
    expected_custom_statistic_names: tuple[str, ...]
    expected_custom_statistic_names_sha256: str
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    delta_package: delta_package_builder.AcceptedRiskDeltaOrderPackage = dataclasses.field(repr=False)
    projection: projection_builder.AcceptedRiskOrderLevelQcProjection = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelLaunchControl:
    control_id: str
    control_sha256: str
    plan_sha256: str
    execution_authority_sha256: str
    owner_signature_authority_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    control_path: Path
    control_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelLaunchCheckpoint:
    checkpoint_id: str
    checkpoint_sha256: str
    plan_sha256: str
    control_sha256: str
    project_id: int
    compile_id: str
    backtest_name: str


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelLaunchRecoveryControl:
    control_id: str
    control_sha256: str
    plan_sha256: str
    launch_control_sha256: str
    checkpoint_sha256: str
    control_path: Path
    control_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    control_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelTerminalStatus:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    poll_count: int
    include_statistics: bool


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelStatusPollCheckpoint:
    checkpoint_id: str
    checkpoint_sha256: str
    plan_sha256: str
    execution_authority_sha256: str
    owner_signature_authority_sha256: str
    owner_signature_sha256: str
    launch_control_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    poll_count: int
    previous_checkpoint_sha256: str | None
    status_poll_limit: int
    endpoint: str
    include_statistics: bool
    request_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelResultControl:
    control_id: str
    control_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    result_read_authority_sha256: str
    owner_signature_authority_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    control_path: Path
    control_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelAggregateResult:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    result_control_sha256: str
    project_id: int
    backtest_id: str
    profile_id: str
    profile_sha256: str
    custom_statistics: tuple[tuple[str, str], ...]
    custom_statistics_sha256: str
    persisted_path: Path
    backtests_read_call_count: int
    raw_orders_logs_charts_selected: bool


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelExecutionAuthority:
    """Detached owner authority for one exact order-level execution plan."""

    authority_id: str
    authority_sha256: str
    plan_id: str
    plan_sha256: str
    delta_lineage_sha256: str
    package_id: str
    package_sha256: str
    projection_id: str
    projection_sha256: str
    profile_id: str
    profile_sha256: str
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    execution_call_budget: tuple[tuple[str, int], ...]
    status_poll_call_budget: tuple[tuple[str, int], ...]
    launch_recovery_call_budget: tuple[tuple[str, int], ...]
    maximum_backtest_submissions: int
    result_read_authorized: bool
    raw_logs_orders_live_authorized: bool
    owner_signature_authority_id: str
    owner_signature_authority_sha256: str
    owner_signature_public_key_blob_sha256: str
    owner_signature_sha256: str
    owner_signature_purpose: str
    owner_signed_payload_sha256: str
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _owner_signature: OwnerSignatureAuthority = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelResultReadAuthority:
    """Separately scoped owner authority for one aggregate-only result read."""

    authority_id: str
    authority_sha256: str
    plan_id: str
    plan_sha256: str
    execution_authority_sha256: str
    launch_control_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    project_id: int
    backtest_id: str
    profile_id: str
    profile_sha256: str
    expected_custom_statistic_names_sha256: str
    result_call_budget: tuple[tuple[str, int], ...]
    maximum_result_reads: int
    aggregate_only: bool
    raw_logs_orders_live_authorized: bool
    retry_after_ambiguity: bool
    owner_signature_authority_id: str
    owner_signature_authority_sha256: str
    owner_signature_public_key_blob_sha256: str
    owner_signature_sha256: str
    owner_signature_purpose: str
    owner_signed_payload_sha256: str
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _owner_signature: OwnerSignatureAuthority = dataclasses.field(repr=False)


def _make_receipt_authority():
    launches = {}
    terminals = {}

    def register_launch(value, plan, control, payload):
        launches[id(value)] = (
            value,
            plan.plan_sha256,
            control.control_sha256,
            payload,
        )
        return value

    def require_launch(value, plan, control, payload):
        entry = launches.get(id(value))
        if entry != (
            value,
            plan.plan_sha256,
            control.control_sha256,
            payload,
        ) or entry[0] is not value:
            _error("order-level launch receipt lacks durable adapter provenance")

    def register_terminal(value, plan, launch, payload):
        terminals[id(value)] = (
            value,
            plan.plan_sha256,
            launch.receipt_sha256,
            payload,
        )
        return value

    def require_terminal(value, plan, launch, payload):
        entry = terminals.get(id(value))
        if entry != (
            value,
            plan.plan_sha256,
            launch.receipt_sha256,
            payload,
        ) or entry[0] is not value:
            _error("order-level terminal receipt lacks durable adapter provenance")

    return register_launch, require_launch, register_terminal, require_terminal


(
    _register_launch_authority,
    _require_launch_authority,
    _register_terminal_authority,
    _require_terminal_authority,
) = _make_receipt_authority()
del _make_receipt_authority


def _upload_entries(package) -> tuple[OrderLevelUploadEntry, ...]:
    entries = []
    descriptors = getattr(package, "upload_objects", None)
    if type(descriptors) is not tuple or not descriptors:
        _error("order-level package upload inventory changed")
    try:
        paired = zip(
            _PINNED_ITER_UPLOADS(package), descriptors, strict=True
        )
        for position, (observed, expected) in enumerate(paired):
            descriptor, payload = observed
            activation_expected = position == len(descriptors) - 1
            if (
                descriptor is not expected
                or type(payload) is not bytes
                or len(payload) != descriptor.byte_count
                or hashlib.sha256(payload).hexdigest()
                != descriptor.content_sha256
                or descriptor.activation_manifest is not activation_expected
            ):
                _error("order-level package upload inventory changed")
            entries.append(
                OrderLevelUploadEntry(
                    UPLOAD_SCHEMA,
                    descriptor.role,
                    descriptor.ordinal,
                    descriptor.object_store_key,
                    descriptor.byte_count,
                    descriptor.content_sha256,
                    hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                    descriptor.activation_manifest,
                )
            )
    except (AttributeError, TypeError, ValueError):
        _error("order-level package upload inventory changed")
    if (
        len(entries) != len(descriptors)
        or entries[-1].activation_manifest is not True
        or any(item.activation_manifest for item in entries[:-1])
    ):
        _error("order-level package activation sequence changed")
    return tuple(entries)


def _require_delta_package(value):
    if type(value) is not delta_package_builder.AcceptedRiskDeltaOrderPackage:
        _error("order-level delta package type changed")
    package = _PINNED_REQUIRE_PACKAGE(value.package)
    if (
        type(value.lineage) is not dict
        or value.lineage_sha256
        != hashlib.sha256(canonical_json_bytes(value.lineage)).hexdigest()
        or package.source_disposition_sha256 != value.lineage_sha256
        or value.decision_cutoff_session
        != delta_package_builder.DELTA_DECISION_END_SESSION
        or value.final_execution_session
        != delta_package_builder.FINAL_EXECUTION_SESSION
        or value.current_snapshot_identity_only is not True
        or value.refreshed_security_master is not False
        or any(
            getattr(value, field) is not False
            for field in (
                "provider_access",
                "quantconnect_access",
                "outcome_access",
                "orders",
                "trading",
            )
        )
    ):
        _error("order-level delta package lineage or disclosure changed")
    return value, package


def _plan_record(
    *, delta_package, projection, organization_hash, project_name,
    backtest_name, control_directory, upload_entries, expected_names,
) -> dict[str, object]:
    return {
        "delta_lineage_sha256": delta_package.lineage_sha256,
        "package_id": delta_package.package.package_id,
        "package_sha256": delta_package.package.package_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "profile_id": projection.profile_id,
        "profile_sha256": projection.profile_sha256,
        "organization_id_sha256": organization_hash,
        "project_name": project_name,
        "backtest_name": backtest_name,
        "control_directory": str(control_directory),
        "upload_entries": [dataclasses.asdict(item) for item in upload_entries],
        "source_files": [item.to_record() for item in projection.source_files],
        "expected_custom_statistic_names": list(expected_names),
        "expected_custom_statistic_names_sha256": hashlib.sha256(
            _canonical(list(expected_names))
        ).hexdigest(),
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "private_project": True,
        "backtest_only": True,
        "simulated_market_on_open_orders": True,
        "raw_orders_logs_charts_result_access": False,
        "paper": False,
        "live": False,
        "deployment": False,
        "broker_credentials": False,
        "funded_trading": False,
    }


def build_order_level_submission_plan(
    *,
    delta_package: delta_package_builder.AcceptedRiskDeltaOrderPackage,
    projection: projection_builder.AcceptedRiskOrderLevelQcProjection,
    organization_id: str,
    project_name: str,
    backtest_name: str,
    control_directory: Path,
) -> OrderLevelSubmissionPlan:
    delta_package, package = _require_delta_package(delta_package)
    projection = _PINNED_REQUIRE_PROJECTION(projection)
    _safe_name(organization_id, "organization id", 512)
    _safe_name(project_name, "project name", MAX_PROJECT_NAME_BYTES)
    _safe_name(backtest_name, "backtest name", MAX_BACKTEST_NAME_BYTES)
    if (
        _PINNED_RUNTIME_PROFILE_IDS != PROFILE_IDS
        or projection.profile_id not in PROFILE_IDS
    ):
        _error("order-level profile is not allowlisted")
    profile_binding = next(
        (
            binding
            for binding in _PINNED_RUNTIME_PROFILE_BINDINGS
            if binding[0] == projection.profile_id
        ),
        None,
    )
    if profile_binding is None:
        _error("order-level profile binding is unavailable")
    expected_names = profile_binding[-1]
    if (
        delta_package.lineage_sha256 != projection.package_lineage_sha256
        or package.package_id != projection.package_id
        or package.package_sha256 != projection.package_sha256
        or profile_binding[1] != projection.profile_sha256
        or expected_names
        != tuple(
            sorted(
                (
                    _PINNED_META_STATISTIC_NAME,
                    _PINNED_AGGREGATES_STATISTIC_NAME,
                )
            )
        )
    ):
        _error("order-level package projection and runtime are not exact peers")
    uploads = _upload_entries(package)
    control_directory = _private_directory(control_directory)
    organization_hash = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()
    record = _plan_record(
        delta_package=delta_package,
        projection=projection,
        organization_hash=organization_hash,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=control_directory,
        upload_entries=uploads,
        expected_names=expected_names,
    )
    identity, digest, _payload = _identified(PLAN_SCHEMA, "arv2-order-level-plan-", record)
    return OrderLevelSubmissionPlan(
        identity,
        digest,
        organization_id,
        organization_hash,
        project_name,
        backtest_name,
        control_directory,
        delta_package.lineage_sha256,
        package.package_id,
        package.package_sha256,
        projection.projection_id,
        projection.projection_sha256,
        projection.profile_id,
        projection.profile_sha256,
        uploads,
        projection.source_files,
        expected_names,
        record["expected_custom_statistic_names_sha256"],
        MAX_COMPILE_POLLS,
        MAX_STATUS_POLLS,
        1,
        delta_package,
        projection,
    )


def require_order_level_submission_plan(value: OrderLevelSubmissionPlan) -> OrderLevelSubmissionPlan:
    if type(value) is not OrderLevelSubmissionPlan:
        _error("order-level submission plan type changed")
    rebuilt = build_order_level_submission_plan(
        delta_package=value.delta_package,
        projection=value.projection,
        organization_id=value.organization_id,
        project_name=value.project_name,
        backtest_name=value.backtest_name,
        control_directory=value.control_directory,
    )
    if value != rebuilt:
        _error("order-level submission plan identity changed")
    return value


def _execution_call_budget(plan: OrderLevelSubmissionPlan) -> dict[str, int]:
    return {
        "authenticate": 1,
        "projects/read": 2,
        "projects/create": 1,
        "object/set": len(plan.upload_entries),
        "object/properties": len(plan.upload_entries),
        "files/read": 2,
        "files/create": len(plan.source_files),
        "files/update": len(plan.source_files),
        "files/delete": 1,
        "compile/create": 1,
        "compile/read": plan.compile_poll_limit,
        "backtests/create": plan.maximum_backtest_submissions,
    }


def _signature_metadata(value: OwnerSignatureAuthority) -> tuple[str, ...]:
    try:
        result = (
            value.authority_id,
            value.authority_sha256,
            value.public_key_blob_sha256,
            value.signature_sha256,
            value.purpose,
            value.authority_payload_sha256,
        )
    except AttributeError as exc:
        raise AcceptedRiskOrderLevelSubmissionError(
            "owner signature authority changed"
        ) from exc
    if any(type(item) is not str or not item for item in result):
        _error("owner signature authority changed")
    return result


def _make_execution_authority_operations(
    *, signature_requirer, plan_requirer,
    exact_plan_type=OrderLevelSubmissionPlan,
    _graph_sealer=_seal_local_function_graph,
):
    """Seal execution authority reauthentication away from module rebinding."""

    plan_requirer, signature_metadata = _graph_sealer(
        plan_requirer, _signature_metadata
    )

    authority_type = OrderLevelExecutionAuthority
    error_type = AcceptedRiskOrderLevelSubmissionError
    signature_error_type = OwnerSignatureAuthorityError
    asdict = dataclasses.asdict
    canonical = _canonical
    sha256 = hashlib.sha256
    schema = EXECUTION_AUTHORITY_SCHEMA
    prefix = "arv2-order-level-execution-authority-"
    compile_poll_seconds = COMPILE_POLL_SECONDS
    status_poll_seconds = STATUS_POLL_SECONDS

    def candidate(plan):
        plan = plan_requirer(plan)
        if type(plan) is not exact_plan_type:
            raise error_type("order-level submission plan type changed")
        upload_inventory = [asdict(item) for item in plan.upload_entries]
        source_inventory = [item.to_record() for item in plan.source_files]
        execution_budget = {
            "authenticate": 1,
            "projects/read": 2,
            "projects/create": 1,
            "object/set": len(plan.upload_entries),
            "object/properties": len(plan.upload_entries),
            "files/read": 2,
            "files/create": len(plan.source_files),
            "files/update": len(plan.source_files),
            "files/delete": 1,
            "compile/create": 1,
            "compile/read": plan.compile_poll_limit,
            "backtests/create": plan.maximum_backtest_submissions,
        }
        record = {
            "status": "requires_exact_owner_ed25519_signature",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "delta_lineage_sha256": plan.delta_lineage_sha256,
            "package_id": plan.package_id,
            "package_sha256": plan.package_sha256,
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "profile_id": plan.profile_id,
            "profile_sha256": plan.profile_sha256,
            "organization_id_sha256": plan.organization_id_sha256,
            "project_name": plan.project_name,
            "backtest_name": plan.backtest_name,
            "upload_entry_count": len(upload_inventory),
            "upload_inventory_sha256": sha256(
                canonical(upload_inventory)
            ).hexdigest(),
            "source_file_count": len(source_inventory),
            "source_inventory_sha256": sha256(
                canonical(source_inventory)
            ).hexdigest(),
            "expected_custom_statistic_names": list(
                plan.expected_custom_statistic_names
            ),
            "expected_custom_statistic_names_sha256": (
                plan.expected_custom_statistic_names_sha256
            ),
            "execution_call_budget": execution_budget,
            "status_poll_call_budget": {
                "backtests/list": plan.status_poll_limit,
            },
            "launch_recovery_call_budget": {"backtests/list": 1},
            "compile_poll_interval_seconds": compile_poll_seconds,
            "status_poll_interval_seconds": status_poll_seconds,
            "maximum_backtest_submissions": plan.maximum_backtest_submissions,
            "private_project": True,
            "backtest_only": True,
            "simulated_market_on_open_orders": True,
            "result_read_authorized": False,
            "raw_provider_rows_authorized": False,
            "raw_logs_orders_charts_authorized": False,
            "paper_live_deployment_funded_trading_authorized": False,
        }
        seed = {"schema": schema, "id": None, "sha256": None, **record}
        digest = sha256(canonical(seed)).hexdigest()
        identity = prefix + digest[:24]
        payload = canonical({**seed, "id": identity, "sha256": digest})
        return plan, identity, digest, payload, execution_budget

    def render(*, plan):
        """Render the exact plan-scoped bytes the owner must sign."""

        return candidate(plan)[3]

    def load(*, plan, receipt_bytes, owner_signature):
        plan, identity, digest, expected, execution_budget = candidate(plan)
        if type(receipt_bytes) is not bytes or receipt_bytes != expected:
            raise error_type(
                "order-level execution authority receipt bytes changed"
            )
        try:
            verified = signature_requirer(
                owner_signature, authority_payload=expected
            )
        except signature_error_type as exc:
            raise error_type(
                "non-self-mintable owner execution signature is unavailable"
            ) from exc
        signature = signature_metadata(verified)
        return authority_type(
            identity,
            digest,
            plan.plan_id,
            plan.plan_sha256,
            plan.delta_lineage_sha256,
            plan.package_id,
            plan.package_sha256,
            plan.projection_id,
            plan.projection_sha256,
            plan.profile_id,
            plan.profile_sha256,
            plan.organization_id_sha256,
            plan.project_name,
            plan.backtest_name,
            tuple(sorted(execution_budget.items())),
            (("backtests/list", plan.status_poll_limit),),
            (("backtests/list", 1),),
            plan.maximum_backtest_submissions,
            False,
            False,
            *signature,
            bytes(receipt_bytes),
            verified,
        )

    def require(*, value, plan):
        if type(value) is not authority_type:
            raise error_type("exact order-level execution authority is required")
        rebuilt = load(
            plan=plan,
            receipt_bytes=value._receipt_bytes,
            owner_signature=value._owner_signature,
        )
        if value != rebuilt:
            raise error_type("order-level execution authority changed")
        return value

    return render, load, require


(
    render_order_level_execution_authority_candidate,
    load_order_level_execution_authority,
    require_order_level_execution_authority,
) = _make_execution_authority_operations(
    signature_requirer=require_formal_execution_owner_signature,
    plan_requirer=require_order_level_submission_plan,
)


def _submission_plan_path(plan) -> Path:
    return plan.control_directory / (
        "submission-plan-" + plan.plan_sha256[:24] + ".json"
    )


def _submission_plan_bytes(plan) -> bytes:
    record = _plan_record(
        delta_package=plan.delta_package,
        projection=plan.projection,
        organization_hash=plan.organization_id_sha256,
        project_name=plan.project_name,
        backtest_name=plan.backtest_name,
        control_directory=plan.control_directory,
        upload_entries=plan.upload_entries,
        expected_names=plan.expected_custom_statistic_names,
    )
    identity, digest, payload = _identified(
        PLAN_SCHEMA, "arv2-order-level-plan-", record
    )
    if identity != plan.plan_id or digest != plan.plan_sha256:
        _error("order-level persisted submission plan identity changed")
    return payload


def persist_order_level_submission_plan(plan) -> Path:
    plan = require_order_level_submission_plan(plan)
    path = _submission_plan_path(plan)
    payload = _submission_plan_bytes(plan)
    try:
        observed = _read_private(path, "submission plan")
    except AcceptedRiskOrderLevelSubmissionError:
        _write_private_once(path, payload, "submission plan")
    else:
        if observed != payload:
            _error("persisted order-level submission plan changed")
    return path


def load_order_level_submission_plan(
    *, plan_path, delta_package, projection, organization_id,
):
    _safe_name(organization_id, "organization id", 512)
    payload = _read_private(plan_path, "submission plan")
    raw = _strict_object(payload, "submission plan")
    project_name = _safe_name(
        raw.get("project_name"),
        "persisted order-level project name",
        MAX_PROJECT_NAME_BYTES,
    )
    backtest_name = _safe_name(
        raw.get("backtest_name"),
        "persisted order-level backtest name",
        MAX_BACKTEST_NAME_BYTES,
    )
    control = raw.get("control_directory")
    if type(control) is not str or not control or len(control.encode("utf-8")) > 4096:
        _error("persisted order-level control directory changed")
    rebuilt = build_order_level_submission_plan(
        delta_package=delta_package,
        projection=projection,
        organization_id=organization_id,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=Path(control),
    )
    if (
        plan_path != _submission_plan_path(rebuilt)
        or payload != _submission_plan_bytes(rebuilt)
    ):
        _error("persisted order-level submission plan does not match inputs")
    return rebuilt


def _launch_control_path(plan) -> Path:
    return plan.control_directory / ("launch-control-" + plan.plan_sha256[:24] + ".json")


def _result_control_path(plan) -> Path:
    return plan.control_directory / ("result-control-" + plan.plan_sha256[:24] + ".json")


def _launch_checkpoint_path(plan) -> Path:
    return plan.control_directory / (
        "launch-checkpoint-" + plan.plan_sha256[:24] + ".json"
    )


def _launch_recovery_control_path(plan) -> Path:
    return plan.control_directory / (
        "launch-recovery-control-" + plan.plan_sha256[:24] + ".json"
    )


def _launch_receipt_path(plan) -> Path:
    return plan.control_directory / (
        "launch-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _terminal_receipt_path(plan) -> Path:
    return plan.control_directory / (
        "terminal-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _status_poll_checkpoint_path(plan, poll_count: int) -> Path:
    if type(poll_count) is not int or not 1 <= poll_count <= plan.status_poll_limit:
        _error("order-level status poll checkpoint ordinal changed")
    return plan.control_directory / (
        "status-poll-checkpoint-"
        + plan.plan_sha256[:24]
        + f"-{poll_count:04d}.json"
    )


def _result_receipt_path(plan) -> Path:
    return plan.control_directory / (
        "aggregate-result-" + plan.plan_sha256[:24] + ".json"
    )


def _launch_control_record(plan, execution_authority, started_at_utc):
    return {
        "plan_sha256": plan.plan_sha256,
        "execution_authority_sha256": execution_authority.authority_sha256,
        "owner_signature_authority_sha256": (
            execution_authority.owner_signature_authority_sha256
        ),
        "owner_signature_sha256": execution_authority.owner_signature_sha256,
        "package_sha256": plan.package_sha256,
        "projection_sha256": plan.projection_sha256,
        "profile_id": plan.profile_id,
        "profile_sha256": plan.profile_sha256,
        "started_at_utc": started_at_utc,
        "maximum_backtest_submissions": 1,
        "retry_inside_adapter": False,
    }


def _spend_launch_control(
    plan, execution_authority, started_at_utc
) -> OrderLevelLaunchControl:
    _utc(started_at_utc, "launch started_at")
    record = _launch_control_record(plan, execution_authority, started_at_utc)
    identity, digest, payload = _identified(
        LAUNCH_CONTROL_SCHEMA, "arv2-order-level-launch-control-", record
    )
    value = OrderLevelLaunchControl(
        identity, digest, plan.plan_sha256,
        execution_authority.authority_sha256,
        execution_authority.owner_signature_authority_sha256,
        execution_authority.owner_signature_sha256,
        started_at_utc,
        _launch_control_path(plan), payload,
    )
    _write_once(value.control_path, value.control_bytes, "launch")
    return value


def load_order_level_launch_control(*, plan, execution_authority):
    plan = require_order_level_submission_plan(plan)
    path = _launch_control_path(plan)
    payload = _read_private(path, "launch control")
    raw = _strict_object(payload, "launch control")
    expected = {
        "schema", "id", "sha256", "plan_sha256", "package_sha256",
        "projection_sha256", "profile_id", "profile_sha256",
        "execution_authority_sha256", "owner_signature_authority_sha256",
        "owner_signature_sha256",
        "started_at_utc", "maximum_backtest_submissions",
        "retry_inside_adapter",
    }
    if set(raw) != expected:
        _error("order-level launch control fields changed")
    started = _utc(raw.get("started_at_utc"), "persisted launch started_at")
    identity, digest, exact = _identified(
        LAUNCH_CONTROL_SCHEMA,
        "arv2-order-level-launch-control-",
        _launch_control_record(plan, execution_authority, started),
    )
    value = OrderLevelLaunchControl(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("execution_authority_sha256"),
        raw.get("owner_signature_authority_sha256"),
        raw.get("owner_signature_sha256"),
        started,
        path, payload,
    )
    if (
        value.control_id != identity
        or value.control_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.execution_authority_sha256
        != execution_authority.authority_sha256
        or value.owner_signature_authority_sha256
        != execution_authority.owner_signature_authority_sha256
        or value.owner_signature_sha256
        != execution_authority.owner_signature_sha256
        or payload != exact
    ):
        _error("persisted order-level launch control changed")
    return value


def _checkpoint_record(plan, control, project_id, compile_id):
    if type(project_id) is not int or project_id <= 0:
        _error("order-level launch checkpoint project id changed")
    _safe_name(compile_id, "order-level checkpoint compile id", 512)
    return {
        "plan_sha256": plan.plan_sha256,
        "control_sha256": control.control_sha256,
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_name": plan.backtest_name,
    }


def _persist_launch_checkpoint(plan, control, project_id, compile_id):
    record = _checkpoint_record(plan, control, project_id, compile_id)
    identity, digest, payload = _identified(
        LAUNCH_CHECKPOINT_SCHEMA, "arv2-order-level-launch-checkpoint-", record
    )
    value = OrderLevelLaunchCheckpoint(identity, digest, **record)
    _write_private_once(
        _launch_checkpoint_path(plan), payload, "launch checkpoint"
    )
    return value


def _load_launch_checkpoint(plan, control):
    payload = _read_private(_launch_checkpoint_path(plan), "launch checkpoint")
    raw = _strict_object(payload, "launch checkpoint")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "control_sha256",
        "project_id", "compile_id", "backtest_name",
    }:
        _error("order-level launch checkpoint fields changed")
    record = _checkpoint_record(
        plan, control, raw.get("project_id"), raw.get("compile_id")
    )
    identity, digest, exact = _identified(
        LAUNCH_CHECKPOINT_SCHEMA, "arv2-order-level-launch-checkpoint-", record
    )
    value = OrderLevelLaunchCheckpoint(
        raw.get("id"), raw.get("sha256"), **record
    )
    if (
        value.checkpoint_id != identity
        or value.checkpoint_sha256 != digest
        or value.control_sha256 != control.control_sha256
        or value.backtest_name != plan.backtest_name
        or payload != exact
    ):
        _error("persisted order-level launch checkpoint changed")
    return value


def _make_transport_dispatch(transport_call):
    def transport(client, capability, method: str, *args):
        return transport_call(client, capability, method, *args)

    return transport


_transport = _make_transport_dispatch(_ORDER_TRANSPORT_CALL)
del _make_transport_dispatch


def _wait(seconds: int) -> None:
    if type(seconds) is not int or seconds not in {COMPILE_POLL_SECONDS, STATUS_POLL_SECONDS}:
        _error("order-level poll interval changed")
    time.sleep(seconds)


def _launch_record(value):
    return {
        "plan_sha256": value.plan_sha256,
        "control_sha256": value.control_sha256,
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }


def _launch_receipt_bytes(value):
    identity, digest, payload = _identified(
        LAUNCH_SCHEMA, "arv2-order-level-launch-", _launch_record(value)
    )
    if value.receipt_id != identity or value.receipt_sha256 != digest:
        _error("order-level durable launch receipt identity changed")
    return payload


def _new_launch(plan, control, project_id, compile_id, backtest_id, initial):
    record = {
        "plan_sha256": plan.plan_sha256,
        "control_sha256": control.control_sha256,
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "initial_status": initial,
    }
    identity, digest, _payload = _identified(
        LAUNCH_SCHEMA, "arv2-order-level-launch-", record
    )
    return OrderLevelLaunchReceipt(identity, digest, **record)


def load_order_level_launch_receipt(
    *, plan, execution_authority, launch_control
):
    plan = require_order_level_submission_plan(plan)
    persisted_control = load_order_level_launch_control(
        plan=plan, execution_authority=execution_authority
    )
    if persisted_control != launch_control:
        _error("order-level launch control identity changed during reload")
    payload = _read_private(_launch_receipt_path(plan), "launch receipt")
    raw = _strict_object(payload, "launch receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "control_sha256",
        "project_id", "compile_id", "backtest_id", "backtest_name",
        "initial_status",
    }:
        _error("order-level launch receipt fields changed")
    value = OrderLevelLaunchReceipt(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("control_sha256"), raw.get("project_id"),
        raw.get("compile_id"), raw.get("backtest_id"),
        raw.get("backtest_name"), raw.get("initial_status"),
    )
    if payload != _launch_receipt_bytes(value):
        _error("persisted order-level launch receipt changed")
    _register_launch_authority(value, plan, launch_control, payload)
    return _require_launch(value, plan, launch_control)


def _execute_order_level_submission_once_impl(
    *, plan, execution_authority, client, started_at_utc, minter,
    transport_verifier, authority_verifier, _transport=_transport,
):
    plan = require_order_level_submission_plan(plan)
    execution_authority = authority_verifier(
        value=execution_authority, plan=plan
    )
    transport_verifier(client)
    # Reject a changed transport surface before creating any local artifact.
    persist_order_level_submission_plan(plan)
    control = _spend_launch_control(
        plan, execution_authority, started_at_utc
    )
    capability = minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-order-level-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "execution_authority_sha256": (
                execution_authority.authority_sha256
            ),
            "control_sha256": control.control_sha256,
            "package_sha256": plan.package_sha256,
            "projection_sha256": plan.projection_sha256,
            "profile_sha256": plan.profile_sha256,
        },
        call_budget=dict(execution_authority.execution_call_budget),
    )
    failure_type = None
    outcome = None
    try:
        _PINNED_SUCCESS(
            _transport(client, capability, "_request_json", "authenticate", {}),
            frozenset({"success", "errors", "messages"}),
            "authenticate",
        )
        inventory = _PINNED_READ_PROJECTS(
            _transport(client, capability, "_request_json", "projects/read", {})
        )
        if any(type(item) is dict and item.get("name") == plan.project_name for item in inventory):
            _error("exact order-level project already exists")
        created = _PINNED_CREATED_PROJECT(
            _transport(
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py", "organizationId": plan.organization_id},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact = _PINNED_READ_PROJECTS(
            _transport(
                client, capability, "_request_json", "projects/read", {"projectId": project_id}
            )
        )
        if len(exact) != 1:
            _error("new order-level project identity is ambiguous")
        _PINNED_PROJECT_RECORD(
            exact[0], name=plan.project_name, organization_id=plan.organization_id
        )

        observed = []
        for descriptor, payload in _PINNED_ITER_UPLOADS(plan.delta_package.package):
            entry = plan.upload_entries[len(observed)]
            if (
                descriptor.object_store_key != entry.object_store_key
                or descriptor.content_sha256 != entry.content_sha256
                or descriptor.byte_count != entry.byte_count
                or hashlib.md5(payload, usedforsecurity=False).hexdigest() != entry.content_md5
                or descriptor.activation_manifest != entry.activation_manifest
            ):
                _error("order-level package changed during upload")
            _transport(
                client, capability, "_set_object_multipart",
                plan.organization_id, entry.object_store_key, payload,
            )
            _PINNED_OBJECT_METADATA(
                _transport(
                    client, capability, "_read_object_properties",
                    plan.organization_id, entry.object_store_key,
                ),
                entry,
            )
            observed.append(entry)
        if tuple(observed) != plan.upload_entries or observed[-1].activation_manifest is not True:
            _error("order-level upload inventory changed")

        existing = _PINNED_READ_FILES(
            _transport(
                client, capability, "_request_json", "files/read", {"projectId": project_id}
            ),
            expected_project_id=project_id,
        )
        projected = {item.project_path: item for item in plan.source_files}
        unexpected = set(existing) - set(projected)
        if unexpected - {DEFAULT_NOTEBOOK}:
            _error("new order-level project contains an unprojected source")
        if DEFAULT_NOTEBOOK in unexpected:
            _PINNED_SUCCESS(
                _transport(
                    client, capability, "_request_json", "files/delete",
                    {"projectId": project_id, "name": DEFAULT_NOTEBOOK},
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            _PINNED_SUCCESS(
                _transport(
                    client, capability, "_request_json", endpoint,
                    {
                        "projectId": project_id,
                        "name": path,
                        "content": source.source_bytes.decode("ascii"),
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                endpoint,
            )
        readback = _PINNED_READ_FILES(
            _transport(
                client, capability, "_request_json", "files/read", {"projectId": project_id}
            ),
            expected_project_id=project_id,
        )
        if set(readback) != set(projected):
            _error("order-level project source inventory is not exact")
        for path, source in projected.items():
            try:
                payload = readback[path].encode("ascii")
            except UnicodeError as exc:
                raise AcceptedRiskOrderLevelSubmissionError(
                    "order-level source readback is not exact ASCII"
                ) from exc
            if payload != source.source_bytes or hashlib.sha256(payload).hexdigest() != source.content_sha256:
                _error("order-level project source readback changed")

        compile_id = _PINNED_COMPILE_ID(
            _transport(
                client, capability, "_request_json", "compile/create", {"projectId": project_id}
            ),
            expected_project_id=project_id,
        )
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = _PINNED_COMPILE_STATE(
                _transport(
                    client, capability, "_request_json", "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ),
                compile_id,
            )
            if compile_state in _PINNED_COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                _error("order-level compile polling exhausted")
            _wait(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            _error("order-level project did not compile BuildSuccess")
        _persist_launch_checkpoint(
            plan, control, project_id, compile_id
        )
        backtest_id, initial_status = _PINNED_CREATED_BACKTEST(
            _transport(
                client,
                capability,
                "_request_json",
                "backtests/create",
                {
                    "projectId": project_id,
                    "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        launch = _new_launch(
            plan,
            control,
            project_id,
            compile_id,
            backtest_id,
            initial_status,
        )
        _write_private_once(
            _launch_receipt_path(plan),
            _launch_receipt_bytes(launch),
            "launch receipt",
        )
        _register_launch_authority(
            launch, plan, control, _launch_receipt_bytes(launch)
        )
        outcome = (control, launch)
    except AcceptedRiskOrderLevelSubmissionLocked:
        raise
    except Exception as exc:
        failure_type = type(exc).__name__
    if failure_type is not None:
        # Do not retain the transport object, minted capability, or any
        # remotely derived upload/readback values in the refusal traceback.
        # The caught exception is already out of scope here, so clearing these
        # locals also makes its inner transport frames unreachable.
        client = None
        capability = None
        inventory = None
        created = None
        exact = None
        observed = None
        payload = None
        existing = None
        projected = None
        readback = None
        compile_state = None
        launch = None
        outcome = None
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "submission", control.control_id, failure_type
        ) from None
    return outcome


def _require_launch(value, plan, control):
    if type(value) is not OrderLevelLaunchReceipt:
        _error("order-level launch receipt type changed")
    record = {
        "plan_sha256": value.plan_sha256,
        "control_sha256": value.control_sha256,
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }
    identity, digest, _payload = _identified(LAUNCH_SCHEMA, "arv2-order-level-launch-", record)
    if (
        value.receipt_id != identity
        or value.receipt_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.control_sha256 != control.control_sha256
        or value.backtest_name != plan.backtest_name
    ):
        _error("order-level launch receipt identity changed")
    payload = _read_private(_launch_receipt_path(plan), "launch receipt")
    if payload != _launch_receipt_bytes(value):
        _error("order-level launch receipt durable bytes changed")
    _require_launch_authority(value, plan, control, payload)
    return value


def _spend_launch_recovery_control(plan, control, checkpoint):
    record = {
        "plan_sha256": plan.plan_sha256,
        "launch_control_sha256": control.control_sha256,
        "checkpoint_sha256": checkpoint.checkpoint_sha256,
        "maximum_statistics_free_backtests_list_calls": 1,
        "may_create_or_compile": False,
    }
    identity, digest, payload = _identified(
        LAUNCH_RECOVERY_CONTROL_SCHEMA,
        "arv2-order-level-launch-recovery-control-",
        record,
    )
    value = OrderLevelLaunchRecoveryControl(
        identity,
        digest,
        plan.plan_sha256,
        control.control_sha256,
        checkpoint.checkpoint_sha256,
        _launch_recovery_control_path(plan),
        payload,
    )
    _write_once(value.control_path, value.control_bytes, "launch_recovery")
    return value


def _recover_order_level_launch_receipt_once_impl(
    *, plan, execution_authority, launch_control, client, minter,
    transport_verifier, authority_verifier, _transport=_transport,
):
    plan = require_order_level_submission_plan(plan)
    execution_authority = authority_verifier(
        value=execution_authority, plan=plan
    )
    persisted_control = load_order_level_launch_control(
        plan=plan, execution_authority=execution_authority
    )
    if persisted_control != launch_control:
        _error("order-level launch recovery control lineage changed")
    if os.path.lexists(_launch_receipt_path(plan)):
        return load_order_level_launch_receipt(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
        )
    checkpoint = _load_launch_checkpoint(plan, launch_control)
    transport_verifier(client)
    recovery = _spend_launch_recovery_control(
        plan, launch_control, checkpoint
    )
    capability = minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-order-level-launch-recovery-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "execution_authority_sha256": (
                execution_authority.authority_sha256
            ),
            "launch_control_sha256": launch_control.control_sha256,
            "checkpoint_sha256": checkpoint.checkpoint_sha256,
            "recovery_control_sha256": recovery.control_sha256,
        },
        call_budget=dict(execution_authority.launch_recovery_call_budget),
    )
    failure_type = None
    outcome = None
    try:
        status = _PINNED_PARSE_UNIQUE_RUN(
            _transport(
                client,
                capability,
                "_request_json",
                "backtests/list",
                {
                    "projectId": checkpoint.project_id,
                    "includeStatistics": False,
                },
            ),
            expected_project_id=checkpoint.project_id,
            expected_backtest_name=checkpoint.backtest_name,
        )
        launch = _new_launch(
            plan,
            launch_control,
            checkpoint.project_id,
            checkpoint.compile_id,
            status.backtest_id,
            RECOVERED_LAUNCH_INITIAL_STATUS,
        )
        _write_private_once(
            _launch_receipt_path(plan),
            _launch_receipt_bytes(launch),
            "launch receipt",
        )
        _register_launch_authority(
            launch, plan, launch_control, _launch_receipt_bytes(launch)
        )
        outcome = launch
    except AcceptedRiskOrderLevelSubmissionLocked:
        raise
    except Exception as exc:
        failure_type = type(exc).__name__
    if failure_type is not None:
        client = None
        capability = None
        status = None
        launch = None
        outcome = None
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "launch_recovery", recovery.control_id, failure_type
        ) from None
    return outcome


def _status_poll_checkpoint_record(
    plan, execution_authority, launch_control, launch, poll_count,
    previous_checkpoint_sha256,
):
    if type(poll_count) is not int or not 1 <= poll_count <= plan.status_poll_limit:
        _error("order-level status poll checkpoint ordinal changed")
    if poll_count == 1:
        if previous_checkpoint_sha256 is not None:
            _error("order-level first status poll checkpoint predecessor changed")
    else:
        _sha(
            previous_checkpoint_sha256,
            "order-level status poll checkpoint predecessor",
        )
    request = {
        "projectId": launch.project_id,
        "includeStatistics": False,
    }
    return {
        "plan_sha256": plan.plan_sha256,
        "execution_authority_sha256": execution_authority.authority_sha256,
        "owner_signature_authority_sha256": (
            execution_authority.owner_signature_authority_sha256
        ),
        "owner_signature_sha256": execution_authority.owner_signature_sha256,
        "launch_control_sha256": launch_control.control_sha256,
        "launch_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "poll_count": poll_count,
        "previous_checkpoint_sha256": previous_checkpoint_sha256,
        "status_poll_limit": plan.status_poll_limit,
        "endpoint": "backtests/list",
        "include_statistics": False,
        "request_sha256": hashlib.sha256(_canonical(request)).hexdigest(),
    }


def _spend_status_poll_checkpoint(
    plan, execution_authority, launch_control, launch, prior_checkpoints
):
    if type(prior_checkpoints) is not tuple:
        _error("order-level prior status poll checkpoint inventory changed")
    poll_count = len(prior_checkpoints) + 1
    if poll_count > plan.status_poll_limit:
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "terminal_status",
            launch_control.control_id,
            "status poll budget exhausted",
        )
    previous_sha256 = (
        prior_checkpoints[-1].checkpoint_sha256
        if prior_checkpoints
        else None
    )
    record = _status_poll_checkpoint_record(
        plan,
        execution_authority,
        launch_control,
        launch,
        poll_count,
        previous_sha256,
    )
    identity, digest, payload = _identified(
        STATUS_POLL_CHECKPOINT_SCHEMA,
        "arv2-order-level-status-poll-",
        record,
    )
    checkpoint = OrderLevelStatusPollCheckpoint(
        identity, digest, **record
    )
    try:
        _write_private_once(
            _status_poll_checkpoint_path(plan, poll_count),
            payload,
            "status poll checkpoint",
        )
    except AcceptedRiskOrderLevelSubmissionError as exc:
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "terminal_status",
            launch_control.control_id,
            "status poll checkpoint already exists or is unavailable",
        ) from exc
    return checkpoint


def _load_status_poll_checkpoints(
    plan, execution_authority, launch_control, launch
):
    checkpoints = []
    gap_seen = False
    for poll_count in range(1, plan.status_poll_limit + 1):
        path = _status_poll_checkpoint_path(plan, poll_count)
        present = os.path.lexists(path)
        if not present:
            gap_seen = True
            continue
        if gap_seen:
            _error("order-level status poll checkpoint sequence changed")
        payload = _read_private(path, "status poll checkpoint")
        raw = _strict_object(payload, "status poll checkpoint")
        if set(raw) != {
            "schema", "id", "sha256", "plan_sha256",
            "execution_authority_sha256",
            "owner_signature_authority_sha256", "owner_signature_sha256",
            "launch_control_sha256", "launch_sha256", "project_id",
            "backtest_id", "poll_count", "previous_checkpoint_sha256",
            "status_poll_limit", "endpoint", "include_statistics",
            "request_sha256",
        }:
            _error("order-level status poll checkpoint fields changed")
        previous_sha256 = (
            checkpoints[-1].checkpoint_sha256 if checkpoints else None
        )
        record = _status_poll_checkpoint_record(
            plan,
            execution_authority,
            launch_control,
            launch,
            poll_count,
            previous_sha256,
        )
        if (
            raw.get("plan_sha256") != plan.plan_sha256
            or raw.get("execution_authority_sha256")
            != execution_authority.authority_sha256
            or raw.get("owner_signature_authority_sha256")
            != execution_authority.owner_signature_authority_sha256
            or raw.get("owner_signature_sha256")
            != execution_authority.owner_signature_sha256
            or raw.get("launch_control_sha256")
            != launch_control.control_sha256
            or raw.get("launch_sha256") != launch.receipt_sha256
            or raw.get("project_id") != launch.project_id
            or raw.get("backtest_id") != launch.backtest_id
        ):
            _error("order-level status poll checkpoint lineage changed")
        identity, digest, exact = _identified(
            STATUS_POLL_CHECKPOINT_SCHEMA,
            "arv2-order-level-status-poll-",
            record,
        )
        checkpoint = OrderLevelStatusPollCheckpoint(
            raw.get("id"), raw.get("sha256"), **record
        )
        if (
            checkpoint.checkpoint_id != identity
            or checkpoint.checkpoint_sha256 != digest
            or raw.get("poll_count") != poll_count
            or raw.get("previous_checkpoint_sha256") != previous_sha256
            or payload != exact
        ):
            _error("persisted order-level status poll checkpoint changed")
        checkpoints.append(checkpoint)
    return tuple(checkpoints)


def _terminal_record(value):
    return {
        "plan_sha256": value.plan_sha256,
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
    }


def _terminal_receipt_bytes(value):
    identity, digest, payload = _identified(
        TERMINAL_SCHEMA, "arv2-order-level-terminal-", _terminal_record(value)
    )
    if value.receipt_id != identity or value.receipt_sha256 != digest:
        _error("order-level durable terminal receipt identity changed")
    return payload


def load_order_level_terminal_status(
    *, plan, execution_authority, launch_control, launch
):
    plan = require_order_level_submission_plan(plan)
    persisted_launch = load_order_level_launch_receipt(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=launch_control,
    )
    if persisted_launch != launch:
        _error("order-level terminal reload launch lineage changed")
    payload = _read_private(_terminal_receipt_path(plan), "terminal receipt")
    raw = _strict_object(payload, "terminal receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "project_id", "backtest_id", "terminal_status", "poll_count",
        "include_statistics",
    }:
        _error("order-level terminal receipt fields changed")
    value = OrderLevelTerminalStatus(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("launch_sha256"), raw.get("project_id"),
        raw.get("backtest_id"), raw.get("terminal_status"),
        raw.get("poll_count"), raw.get("include_statistics"),
    )
    if (
        type(value.terminal_status) is not str
        or value.terminal_status not in _PINNED_BACKTEST_TERMINAL_STATES
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
        or value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or payload != _terminal_receipt_bytes(value)
    ):
        _error("persisted order-level terminal receipt changed")
    _register_terminal_authority(value, plan, launch, payload)
    return value


def _inspect_order_level_terminal_status_impl(
    *, plan, execution_authority, launch_control, launch, client, minter,
    transport_verifier, authority_verifier,
    checkpoint_loader=_load_status_poll_checkpoints,
    checkpoint_spender=_spend_status_poll_checkpoint,
    _transport=_transport,
):
    plan = require_order_level_submission_plan(plan)
    execution_authority = authority_verifier(
        value=execution_authority, plan=plan
    )
    if dict(execution_authority.status_poll_call_budget) != {
        "backtests/list": plan.status_poll_limit
    }:
        _error("order-level signed status poll budget changed")
    persisted_control = load_order_level_launch_control(
        plan=plan, execution_authority=execution_authority
    )
    if persisted_control != launch_control:
        _error("order-level status launch control lineage changed")
    launch = _require_launch(launch, plan, launch_control)
    if os.path.lexists(_terminal_receipt_path(plan)):
        terminal = load_order_level_terminal_status(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
        )
        if terminal.terminal_status != "Completed.":
            raise AcceptedRiskOrderLevelTerminalFailure(terminal)
        return terminal
    checkpoints = checkpoint_loader(
        plan, execution_authority, launch_control, launch
    )
    if len(checkpoints) >= plan.status_poll_limit:
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "terminal_status",
            launch_control.control_id,
            "status poll budget exhausted",
        )
    transport_verifier(client)
    while len(checkpoints) < plan.status_poll_limit:
        checkpoint = checkpoint_spender(
            plan,
            execution_authority,
            launch_control,
            launch,
            checkpoints,
        )
        checkpoints = (*checkpoints, checkpoint)
        failure_type = None
        try:
            capability = minter(
                transport=client,
                scope="status",
                binding_record={
                    "schema": "arv2-order-level-status-capability-v1",
                    "plan_sha256": plan.plan_sha256,
                    "execution_authority_sha256": (
                        execution_authority.authority_sha256
                    ),
                    "launch_sha256": launch.receipt_sha256,
                    "status_poll_checkpoint_sha256": (
                        checkpoint.checkpoint_sha256
                    ),
                    "cumulative_poll_count": checkpoint.poll_count,
                },
                call_budget={"backtests/list": 1},
            )
            status = _PINNED_PARSE_STATUS(
                _transport(
                    client, capability, "_request_json", "backtests/list",
                    {"projectId": launch.project_id, "includeStatistics": False},
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            failure_type = type(exc).__name__
            status = None
        if failure_type is not None:
            # Raise after the remote exception has left scope.  This prevents
            # parser payloads and transport bodies from surviving as a cause
            # or context of the durable refusal.
            client = None
            capability = None
            status = None
            raise AcceptedRiskOrderLevelSubmissionLocked(
                "terminal_status", launch_control.control_id, failure_type
            ) from None
        if status.status in _PINNED_BACKTEST_TERMINAL_STATES:
            record = {
                "plan_sha256": plan.plan_sha256,
                "launch_sha256": launch.receipt_sha256,
                "project_id": launch.project_id,
                "backtest_id": launch.backtest_id,
                "terminal_status": status.status,
                "poll_count": checkpoint.poll_count,
                "include_statistics": False,
            }
            identity, digest, _payload = _identified(
                TERMINAL_SCHEMA, "arv2-order-level-terminal-", record
            )
            terminal = OrderLevelTerminalStatus(identity, digest, **record)
            _write_private_once(
                _terminal_receipt_path(plan),
                _terminal_receipt_bytes(terminal),
                "terminal receipt",
            )
            _register_terminal_authority(
                terminal, plan, launch, _terminal_receipt_bytes(terminal)
            )
            if terminal.terminal_status != "Completed.":
                raise AcceptedRiskOrderLevelTerminalFailure(terminal)
            return terminal
        if checkpoint.poll_count == plan.status_poll_limit:
            raise AcceptedRiskOrderLevelSubmissionLocked(
                "terminal_status", launch_control.control_id, "poll limit exhausted"
            )
        _wait(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable order-level status loop")


def _require_terminal(value, plan, launch):
    if type(value) is not OrderLevelTerminalStatus:
        _error("order-level terminal receipt type changed")
    record = {
        "plan_sha256": value.plan_sha256,
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
    }
    identity, digest, _payload = _identified(
        TERMINAL_SCHEMA, "arv2-order-level-terminal-", record
    )
    if (
        value.receipt_id != identity
        or value.receipt_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or value.terminal_status != "Completed."
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
    ):
        _error("order-level terminal receipt identity changed")
    payload = _read_private(_terminal_receipt_path(plan), "terminal receipt")
    if payload != _terminal_receipt_bytes(value):
        _error("order-level terminal receipt durable bytes changed")
    _require_terminal_authority(value, plan, launch, payload)
    return value


def _require_result_context(
    *,
    plan: OrderLevelSubmissionPlan,
    execution_authority: OrderLevelExecutionAuthority,
    launch_control: OrderLevelLaunchControl,
    launch: OrderLevelLaunchReceipt,
    terminal: OrderLevelTerminalStatus,
) -> tuple[
    OrderLevelSubmissionPlan,
    OrderLevelLaunchControl,
    OrderLevelLaunchReceipt,
    OrderLevelTerminalStatus,
]:
    plan = require_order_level_submission_plan(plan)
    persisted_control = load_order_level_launch_control(
        plan=plan, execution_authority=execution_authority
    )
    if persisted_control != launch_control:
        _error("order-level result launch control lineage changed")
    launch = _require_launch(launch, plan, launch_control)
    terminal = _require_terminal(terminal, plan, launch)
    return plan, launch_control, launch, terminal


def _make_result_read_authority_operations(
    *, signature_requirer, execution_authority_requirer, context_requirer,
    exact_plan_type=OrderLevelSubmissionPlan,
    _graph_sealer=_seal_local_function_graph,
):
    """Seal result-read reauthentication away from module rebinding."""

    (
        execution_authority_requirer,
        context_requirer,
        signature_metadata,
    ) = _graph_sealer(
        execution_authority_requirer,
        context_requirer,
        _signature_metadata,
    )

    authority_type = OrderLevelResultReadAuthority
    execution_authority_type = OrderLevelExecutionAuthority
    control_type = OrderLevelLaunchControl
    launch_type = OrderLevelLaunchReceipt
    terminal_type = OrderLevelTerminalStatus
    error_type = AcceptedRiskOrderLevelSubmissionError
    signature_error_type = OwnerSignatureAuthorityError
    canonical = _canonical
    sha256 = hashlib.sha256
    schema = RESULT_READ_AUTHORITY_SCHEMA
    prefix = "arv2-order-level-result-read-authority-"
    meta_fields = tuple(sorted(_META_FIELDS))
    legacy_aggregate_fields = tuple(sorted(_AGGREGATE_FIELDS))
    proxy_aggregate_fields = tuple(sorted(_PROXY_AGGREGATE_FIELDS))
    forced_exit_aggregate_fields = tuple(
        sorted(_FORCED_EXIT_AGGREGATE_FIELDS)
    )
    diagnostic_aggregate_fields = tuple(
        sorted(_DIAGNOSTIC_AGGREGATE_FIELDS)
    )
    account_aggregate_fields = tuple(sorted(_ACCOUNT_AGGREGATE_FIELDS))
    statistic_limit = _maximum_statistic_bytes

    def candidate(
        *, plan, execution_authority, launch_control, launch, terminal
    ):
        execution_authority = execution_authority_requirer(
            value=execution_authority, plan=plan
        )
        plan, launch_control, launch, terminal = context_requirer(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
        )
        if (
            type(plan) is not exact_plan_type
            or type(execution_authority) is not execution_authority_type
            or type(launch_control) is not control_type
            or type(launch) is not launch_type
            or type(terminal) is not terminal_type
        ):
            raise error_type("order-level result authority context changed")
        aggregate_fields = (
            account_aggregate_fields
            if plan.profile_id in ACCOUNT_PROFILE_IDS
            else diagnostic_aggregate_fields
            if plan.profile_id in DIAGNOSTIC_PROFILE_IDS
            else forced_exit_aggregate_fields
            if plan.profile_id in FORCED_EXIT_PROFILE_IDS
            else proxy_aggregate_fields
            if plan.profile_id in PROXY_PROFILE_IDS
            else legacy_aggregate_fields
        )
        maximum_statistic_bytes = statistic_limit(plan.profile_id)
        record = {
            "status": "requires_separate_exact_owner_ed25519_signature",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "execution_authority_sha256": execution_authority.authority_sha256,
            "launch_control_sha256": launch_control.control_sha256,
            "launch_receipt_id": launch.receipt_id,
            "launch_receipt_sha256": launch.receipt_sha256,
            "terminal_receipt_id": terminal.receipt_id,
            "terminal_receipt_sha256": terminal.receipt_sha256,
            "terminal_status": terminal.terminal_status,
            "project_id": launch.project_id,
            "backtest_id": launch.backtest_id,
            "project_name": plan.project_name,
            "backtest_name": plan.backtest_name,
            "profile_id": plan.profile_id,
            "profile_sha256": plan.profile_sha256,
            "expected_custom_statistic_names": list(
                plan.expected_custom_statistic_names
            ),
            "expected_custom_statistic_names_sha256": (
                plan.expected_custom_statistic_names_sha256
            ),
            "meta_field_inventory_sha256": sha256(
                canonical(list(meta_fields))
            ).hexdigest(),
            "aggregate_field_inventory_sha256": sha256(
                canonical(list(aggregate_fields))
            ).hexdigest(),
            "maximum_custom_statistic_bytes_each": maximum_statistic_bytes,
            "result_call_budget": {"backtests/read": 1},
            "maximum_result_reads": 1,
            "aggregate_only": True,
            "raw_provider_or_security_rows_authorized": False,
            "standard_statistics_authorized": False,
            "logs_orders_charts_runtime_statistics_authorized": False,
            "paper_live_deployment_funded_trading_authorized": False,
            "retry_after_ambiguity": False,
        }
        seed = {"schema": schema, "id": None, "sha256": None, **record}
        digest = sha256(canonical(seed)).hexdigest()
        identity = prefix + digest[:24]
        payload = canonical({**seed, "id": identity, "sha256": digest})
        return (
            plan,
            execution_authority,
            launch_control,
            launch,
            terminal,
            identity,
            digest,
            payload,
        )

    def render(
        *, plan, execution_authority, launch_control, launch, terminal
    ):
        """Render exact aggregate-only bytes for external owner signing."""

        return candidate(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
        )[7]

    def load(
        *, plan, execution_authority, launch_control, launch, terminal, receipt_bytes,
        owner_signature,
    ):
        (
            plan,
            execution_authority,
            launch_control,
            launch,
            terminal,
            identity,
            digest,
            expected,
        ) = candidate(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
        )
        if type(receipt_bytes) is not bytes or receipt_bytes != expected:
            raise error_type(
                "order-level result-read authority receipt bytes changed"
            )
        try:
            verified = signature_requirer(
                owner_signature, authority_payload=expected
            )
        except signature_error_type as exc:
            raise error_type(
                "non-self-mintable owner result-read signature is unavailable"
            ) from exc
        signature = signature_metadata(verified)
        return authority_type(
            identity,
            digest,
            plan.plan_id,
            plan.plan_sha256,
            execution_authority.authority_sha256,
            launch_control.control_sha256,
            launch.receipt_id,
            launch.receipt_sha256,
            terminal.receipt_id,
            terminal.receipt_sha256,
            launch.project_id,
            launch.backtest_id,
            plan.profile_id,
            plan.profile_sha256,
            plan.expected_custom_statistic_names_sha256,
            (("backtests/read", 1),),
            1,
            True,
            False,
            False,
            *signature,
            bytes(receipt_bytes),
            verified,
        )

    def require(
        *, value, plan, execution_authority, launch_control, launch, terminal
    ):
        if type(value) is not authority_type:
            raise error_type("exact order-level result-read authority is required")
        rebuilt = load(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
            receipt_bytes=value._receipt_bytes,
            owner_signature=value._owner_signature,
        )
        if value != rebuilt:
            raise error_type("order-level result-read authority changed")
        return value

    return render, load, require


(
    render_order_level_result_read_authority_candidate,
    load_order_level_result_read_authority,
    require_order_level_result_read_authority,
) = _make_result_read_authority_operations(
    signature_requirer=require_formal_result_read_owner_signature,
    execution_authority_requirer=require_order_level_execution_authority,
    context_requirer=_require_result_context,
)


def _result_control_record(
    plan, launch, terminal, result_read_authority, started_at_utc
):
    return {
        "plan_sha256": plan.plan_sha256,
        "launch_sha256": launch.receipt_sha256,
        "terminal_sha256": terminal.receipt_sha256,
        "result_read_authority_sha256": result_read_authority.authority_sha256,
        "owner_signature_authority_sha256": (
            result_read_authority.owner_signature_authority_sha256
        ),
        "owner_signature_sha256": result_read_authority.owner_signature_sha256,
        "started_at_utc": started_at_utc,
        "maximum_backtests_read_calls": 1,
        "retry_inside_adapter": False,
    }


def _spend_result_control(
    plan, launch, terminal, result_read_authority, started_at_utc
):
    _utc(started_at_utc, "result read started_at")
    record = _result_control_record(
        plan, launch, terminal, result_read_authority, started_at_utc
    )
    identity, digest, payload = _identified(
        RESULT_CONTROL_SCHEMA, "arv2-order-level-result-control-", record
    )
    value = OrderLevelResultControl(
        identity,
        digest,
        plan.plan_sha256,
        launch.receipt_sha256,
        terminal.receipt_sha256,
        result_read_authority.authority_sha256,
        result_read_authority.owner_signature_authority_sha256,
        result_read_authority.owner_signature_sha256,
        started_at_utc,
        _result_control_path(plan),
        payload,
    )
    _write_once(value.control_path, value.control_bytes, "result_read")
    return value


def load_order_level_result_control(
    *, plan, launch, terminal, result_read_authority
):
    plan = require_order_level_submission_plan(plan)
    path = _result_control_path(plan)
    payload = _read_private(path, "result control")
    raw = _strict_object(payload, "result control")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "result_read_authority_sha256",
        "owner_signature_authority_sha256", "owner_signature_sha256",
        "started_at_utc", "maximum_backtests_read_calls",
        "retry_inside_adapter",
    }:
        _error("order-level result control fields changed")
    started = _utc(raw.get("started_at_utc"), "persisted result read started_at")
    identity, digest, exact = _identified(
        RESULT_CONTROL_SCHEMA,
        "arv2-order-level-result-control-",
        _result_control_record(
            plan, launch, terminal, result_read_authority, started
        ),
    )
    value = OrderLevelResultControl(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("launch_sha256"), raw.get("terminal_sha256"),
        raw.get("result_read_authority_sha256"),
        raw.get("owner_signature_authority_sha256"),
        raw.get("owner_signature_sha256"),
        started,
        path, payload,
    )
    if (
        value.control_id != identity
        or value.control_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.result_read_authority_sha256
        != result_read_authority.authority_sha256
        or value.owner_signature_authority_sha256
        != result_read_authority.owner_signature_authority_sha256
        or value.owner_signature_sha256
        != result_read_authority.owner_signature_sha256
        or payload != exact
    ):
        _error("persisted order-level result control changed")
    return value


def _parse_result(response, plan, launch):
    if (
        type(response) is not dict
        or not set(response).issubset({"success", "errors", "messages", "backtest"})
        or response.get("success") is not True
    ):
        _error("order-level backtests/read envelope changed")
    for key in ("errors", "messages"):
        if key in response and (
            type(response[key]) is not list
            or any(type(item) is not str for item in response[key])
        ):
            _error("order-level backtests/read message envelope changed")
    backtest = response.get("backtest")
    allowed = _PINNED_BACKTEST_STATUS_KEYS | _PINNED_DISCARDED_BACKTEST_KEYS | {"statistics"}
    if type(backtest) is not dict or any(type(key) is not str or key not in allowed for key in backtest):
        _error("order-level backtests/read backtest envelope changed")
    if (
        backtest.get("backtestId") != launch.backtest_id
        or backtest.get("projectId") != launch.project_id
        or backtest.get("name") != launch.backtest_name
        or backtest.get("status") != "Completed."
    ):
        _error("order-level backtests/read returned another run")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or any(type(key) is not str for key in statistics):
        _error("order-level backtests/read omitted exact statistics mapping")
    expected_profile_binding = next(
        (
            binding
            for binding in _PINNED_RUNTIME_PROFILE_BINDINGS
            if binding[0] == plan.profile_id
        ),
        None,
    )
    if (
        tuple(
            binding[0] for binding in _PINNED_RUNTIME_PROFILE_BINDINGS
        )
        != PROFILE_IDS
        or expected_profile_binding is None
    ):
        _error("order-level execution-session authority changed")
    (
        _profile_id,
        expected_profile_sha256,
        score_source_view_id,
        expected_first_execution_session,
        expected_decision_count,
        expected_observation_count,
        expected_return_interval_count,
        expected_names,
    ) = expected_profile_binding
    selected_names = tuple(sorted(key for key in statistics if key.startswith("ARV2_")))
    if (
        selected_names != expected_names
        or plan.expected_custom_statistic_names != expected_names
        or plan.expected_custom_statistic_names_sha256
        != hashlib.sha256(_canonical(list(expected_names))).hexdigest()
    ):
        _error("order-level custom result key inventory changed")
    pairs = []
    parsed = {}
    for name in selected_names:
        value = statistics[name]
        if type(value) is not str or not value:
            _error("order-level custom result value exceeded its exact bound")
        if not value.isascii():
            raise AcceptedRiskOrderLevelSubmissionError(
                "order-level custom result is not ASCII JSON"
            ) from None
        payload = value.encode("ascii")
        if len(payload) > _maximum_statistic_bytes(plan.profile_id):
            _error("order-level custom result value exceeded its exact bound")
        parsed[name] = _strict_object(payload, "order-level custom statistic")
        pairs.append((name, value))
    meta = parsed[_PINNED_META_STATISTIC_NAME]
    aggregates = parsed[_PINNED_AGGREGATES_STATISTIC_NAME]
    proxy_mode = plan.profile_id in PROXY_PROFILE_IDS
    account_mode = plan.profile_id in ACCOUNT_PROFILE_IDS
    diagnostic_mode = (
        plan.profile_id in DIAGNOSTIC_PROFILE_IDS or account_mode
    )
    forced_exit_mode = (
        plan.profile_id in FORCED_EXIT_PROFILE_IDS
    )
    activation_entry = (
        plan.upload_entries[-1]
        if type(plan.upload_entries) is tuple and plan.upload_entries
        else None
    )
    if set(meta) != _META_FIELDS:
        _error("order-level aggregate META field inventory changed")
    expected_aggregate_fields = (
        _ACCOUNT_AGGREGATE_FIELDS
        if account_mode
        else _DIAGNOSTIC_AGGREGATE_FIELDS
        if diagnostic_mode
        else _FORCED_EXIT_AGGREGATE_FIELDS
        if forced_exit_mode
        else _PROXY_AGGREGATE_FIELDS
        if proxy_mode
        else _AGGREGATE_FIELDS
    )
    if set(aggregates) != expected_aggregate_fields:
        _error("order-level aggregate field inventory changed")
    if (
        meta.get("schema") != (
            _PINNED_DIAGNOSTIC_META_SCHEMA
            if diagnostic_mode
            else _PINNED_FORCED_EXIT_META_SCHEMA
            if forced_exit_mode else _PINNED_LEGACY_META_SCHEMA
        )
        or meta.get("profile_id") != plan.profile_id
        or meta.get("profile_sha256") != plan.profile_sha256
        or plan.profile_sha256 != expected_profile_sha256
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or type(activation_entry) is not OrderLevelUploadEntry
        or activation_entry.activation_manifest is not True
        or meta.get("activation_manifest_sha256")
        != activation_entry.content_sha256
        or meta.get("score_source_view_id") != score_source_view_id
        or meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or meta.get("backtest_only") is not True
        or meta.get("simulated_order_submission") is not True
        or any(
            meta.get(name) is not False
            for name in (
                "live_orders", "paper_orders", "funded_orders",
                "deployment", "trading",
            )
        )
    ):
        _error("order-level aggregate runtime lineage changed")
    for name in (
        "profile_sha256", "package_sha256", "activation_manifest_sha256",
        "symbol_resolution_sha256", "aggregates_sha256",
    ):
        _sha(meta.get(name), "order-level aggregate META " + name)
    _safe_name(
        meta.get("symbol_resolution_id"),
        "order-level aggregate symbol resolution id",
        512,
    )
    count_fields = (
        "decision_count", "completed_rebalance_count",
        "submitted_order_count", "skipped_unpriced_decision_count",
        "tilt_enabled_count", "tilt_underfilled_count",
        "pit_history_call_count", "pit_source_row_count",
        "named_figi_refusal_count", "QQQ_observation_count",
        "QQQ_calendar_close_observation_count",
        "QQQ_return_interval_count", "filled_order_count_sum",
        "canceled_order_count_sum", "invalid_order_count_sum",
        "orders_with_any_fill_count_sum", "coverage_decision_count",
        "positive_weight_member_count_sum",
        "resolved_positive_weight_member_count_sum",
        "maximum_constituent_snapshot_age_sessions",
    ) + (
        ("forced_exit_invalidated_pending_rebalance_count",)
        if forced_exit_mode else ()
    ) + (
        (
            "delisted_zero_holding_target_retirement_count",
            "delisted_zero_holding_target_retirement_decision_count",
        )
        if account_mode else ()
    )
    if (
        aggregates.get("schema") != (
            _PINNED_ACCOUNT_SUMMARY_SCHEMA if account_mode
            else _PINNED_DIAGNOSTIC_SUMMARY_SCHEMA if diagnostic_mode
            else _PINNED_FORCED_EXIT_SUMMARY_SCHEMA if forced_exit_mode
            else _PINNED_PROXY_SUMMARY_SCHEMA if proxy_mode
            else _PINNED_RUNTIME_SUMMARY_SCHEMA
        )
        or aggregates.get("score_source_view_id") != score_source_view_id
        or any(
            type(aggregates.get(name)) is not int
            or aggregates[name] < 0
            for name in count_fields
        )
        or aggregates.get("modeled_fee_bps_per_side") != 10
        or aggregates.get("lifecycle_modeled_fee_basis")
        != "actual_fill_price_times_filled_quantity"
        or aggregates.get("engine_fee_model_basis")
        != (
            "current_minute_trade_bar_open_times_full_order_quantity_"
            "at_fee_assessment"
        )
        or aggregates.get("QQQ_normalization_mode") != "TOTAL_RETURN"
        or aggregates.get("QQQ_observation")
        != (
            "start_cash_then_first_execution_session_adjusted_open_entry_"
            "and_session_close_marks"
        )
        or aggregates.get("QQQ_entry_fee_bps_per_side") != 10
        or aggregates.get("target_weight_basis")
        != (
            runtime_builder.PROXY_TARGET_WEIGHT_BASIS if proxy_mode
            else runtime_builder.TARGET_WEIGHT_BASIS
        )
        or aggregates.get("raw_order_rows_in_summary") is not False
        or aggregates.get("raw_security_rows_in_summary") is not False
        or aggregates.get("backtest_only") is not True
        or aggregates.get("simulated_orders") is not True
        or aggregates.get("live_orders") is not False
        or aggregates.get("trading") is not False
        or aggregates.get("QQQ_observation_count") < 2
        or aggregates.get("QQQ_return_interval_count")
        != aggregates.get("QQQ_observation_count") - 1
        or aggregates.get("QQQ_calendar_close_observation_count")
        != aggregates.get("QQQ_observation_count")
        or type(aggregates.get("execution_failure")) is not bool
        or type(aggregates.get("run_valid")) is not bool
        or type(aggregates.get("fee_mismatch")) is not bool
    ):
        _error("order-level aggregate schema or safety flags changed")
    forced_delisting = (
        aggregates.get("engine_forced_delisting")
        if forced_exit_mode else None
    )
    if forced_exit_mode:
        if (
            type(forced_delisting) is not dict
            or set(forced_delisting) != _FORCED_DELISTING_FIELDS
            or forced_delisting.get("schema")
            != _PINNED_FORCED_DELISTING_SUMMARY_SCHEMA
            or any(
                type(forced_delisting.get(name)) is not int
                or forced_delisting[name] < 0
                for name in (
                    "order_count", "event_count", "fill_event_count",
                    "terminal_order_count", "absolute_filled_quantity",
                )
            )
            or forced_delisting.get("accounting_complete") is not True
            or forced_delisting.get("raw_order_rows_in_summary") is not False
            or forced_delisting.get("raw_security_rows_in_summary") is not False
        ):
            _error("order-level forced delisting summary changed")
        _sha(
            forced_delisting.get("ledger_sha256"),
            "order-level forced delisting ledger digest",
        )
        forced_delisting_notional = _result_decimal(
            forced_delisting.get("filled_notional"),
            "order-level forced delisting filled notional",
        )
        forced_delisting_fee = _result_decimal(
            forced_delisting.get("actual_engine_fee_amount"),
            "order-level forced delisting actual engine fee",
        )
        if (
            forced_delisting["order_count"]
            != forced_delisting["event_count"]
            or forced_delisting["event_count"]
            != forced_delisting["fill_event_count"]
            or forced_delisting["fill_event_count"]
            != forced_delisting["terminal_order_count"]
            or forced_delisting_notional < 0
            or forced_delisting_fee != 0
            or aggregates["forced_exit_invalidated_pending_rebalance_count"]
            > forced_delisting["order_count"]
        ):
            _error("order-level forced delisting accounting changed")
    if diagnostic_mode:
        evidence = aggregates.get("skipped_unpriced_decision_evidence")
        if (
            aggregates.get("qqq_proxy_complement_policy")
            != _PINNED_EXACT_COMPLEMENT_POLICY
            or aggregates.get("skipped_unpriced_decision_evidence_policy")
            != _PINNED_SKIPPED_UNPRICED_EVIDENCE_POLICY
            or type(evidence) is not dict
            or set(evidence) != _SKIPPED_UNPRICED_EVIDENCE_FIELDS
            or evidence.get("schema")
            != _PINNED_SKIPPED_UNPRICED_EVIDENCE_SCHEMA
            or any(
                type(evidence.get(name)) is not int or evidence[name] < 0
                for name in (
                    "skipped_decision_count", "retained_decision_count",
                    "omitted_decision_count",
                )
            )
            or type(evidence.get("records")) is not list
            or evidence.get("skipped_decision_count")
            != aggregates["skipped_unpriced_decision_count"]
            or evidence.get("retained_decision_count")
            != len(evidence.get("records", ()))
            or evidence.get("retained_decision_count")
            != min(
                evidence.get("skipped_decision_count", 0),
                _PINNED_MAXIMUM_RETAINED_SKIPPED_DECISIONS,
            )
            or evidence.get("omitted_decision_count")
            != evidence.get("skipped_decision_count", 0)
            - evidence.get("retained_decision_count", 0)
        ):
            _error("order-level skipped-unpriced evidence changed")
        _sha(
            evidence.get("path_sha256"),
            "order-level skipped-unpriced evidence path digest",
        )
        prior_session = None
        complete_records = []
        for record in evidence["records"]:
            if (
                type(record) is not dict
                or set(record) != _SKIPPED_UNPRICED_RECORD_FIELDS
                or type(record.get("missing_security_count")) is not int
                or record.get("missing_security_count", 0) <= 0
                or type(record.get("retained_missing_security_sha256s"))
                is not list
                or not record.get("retained_missing_security_sha256s")
                or len(record["retained_missing_security_sha256s"])
                != min(
                    record["missing_security_count"],
                    _PINNED_MAXIMUM_RETAINED_MISSING_SECURITY_HASHES,
                )
                or type(record.get("omitted_missing_security_count")) is not int
                or record.get("omitted_missing_security_count", -1)
                != record["missing_security_count"]
                - len(record["retained_missing_security_sha256s"])
            ):
                _error("order-level skipped-unpriced evidence changed")
            session = _result_session(
                record.get("decision_session"),
                "order-level skipped-unpriced decision session",
            )
            hashes = tuple(record["retained_missing_security_sha256s"])
            for digest in hashes:
                _sha(
                    digest,
                    "order-level skipped-unpriced security digest",
                )
            if (
                prior_session is not None and session <= prior_session
            ) or hashes != tuple(sorted(set(hashes))):
                _error("order-level skipped-unpriced evidence changed")
            prior_session = session
            missing_path_sha256 = _sha(
                record.get("missing_security_path_sha256"),
                "order-level skipped-unpriced security path digest",
            )
            if record["omitted_missing_security_count"] == 0:
                if missing_path_sha256 != hashlib.sha256(_canonical({
                    "schema": _PINNED_MISSING_SECURITY_PATH_SCHEMA,
                    "security_sha256s": list(hashes),
                })).hexdigest():
                    _error("order-level skipped-unpriced evidence changed")
                complete_records.append({
                    "decision_session": session,
                    "missing_security_sha256s": list(hashes),
                })
        if (
            evidence["omitted_decision_count"] == 0
            and len(complete_records) == len(evidence["records"])
            and evidence["path_sha256"]
            != hashlib.sha256(_canonical({
                "schema": _PINNED_SKIPPED_UNPRICED_PATH_SCHEMA,
                "records": complete_records,
            })).hexdigest()
        ):
            _error("order-level skipped-unpriced evidence changed")
    if account_mode:
        retirement_count = aggregates[
            "delisted_zero_holding_target_retirement_count"
        ]
        retirement_decision_count = aggregates[
            "delisted_zero_holding_target_retirement_decision_count"
        ]
        retired_weight_total = _result_decimal(
            aggregates["delisted_zero_holding_target_retired_weight_total"],
            "order-level aggregate retired delisted target weight total",
        )
        retirement_path_sha256 = _sha(
            aggregates["delisted_zero_holding_target_path_sha256"],
            "order-level aggregate retired delisted target path digest",
        )
        if (
            retirement_decision_count > retirement_count
            or retirement_decision_count > aggregates["decision_count"]
            or retirement_count > (
                forced_delisting["order_count"]
                * aggregates["decision_count"]
            )
            or retired_weight_total < 0
            or retired_weight_total > (
                Decimal("0.98") * Decimal(retirement_decision_count)
            )
            or (
                retirement_count == 0
                and (
                    retirement_decision_count != 0
                    or retired_weight_total != 0
                    or retirement_path_sha256
                    != hashlib.sha256(_canonical({
                        "schema": _PINNED_RETIRED_TARGET_PATH_SCHEMA,
                        "records": [],
                    })).hexdigest()
                )
            )
            or (
                retirement_count > 0
                and (
                    retirement_decision_count == 0
                    or retired_weight_total <= 0
                )
            )
        ):
            _error("order-level retired delisted target accounting changed")
    for name in (
        "mean_tilted_name_count", "mean_one_way_active_share",
        "modeled_fee_amount", "total_filled_notional", "starting_equity",
        "ending_equity", "strategy_total_return",
        "strategy_maximum_drawdown", "strategy_annualized_volatility",
        "mean_gross_exposure", "mean_cash_weight", "QQQ_total_return",
        "QQQ_target_gross_exposure", "QQQ_calendar_close_total_return",
        "QQQ_maximum_drawdown", "QQQ_annualized_volatility",
        "strategy_minus_QQQ_total_return",
        "mean_reference_mark_target_weight_l1_error",
        "maximum_reference_mark_target_weight_l1_error",
        "mean_resolved_member_count_ratio",
        "mean_resolved_constituent_weight_ratio",
        "minimum_resolved_member_count_ratio",
        "minimum_resolved_constituent_weight_ratio",
        "minimum_required_resolved_constituent_weight_ratio",
        "actual_engine_fee_amount",
        "actual_engine_fee_effective_bps_per_side",
        "modeled_minus_actual_fee_amount",
        "mean_positive_constituent_weight_total",
        "minimum_positive_constituent_weight_total",
        "maximum_positive_constituent_weight_total",
        "minimum_required_positive_constituent_weight_total",
        "maximum_allowed_positive_constituent_weight_total",
    ) + ((
        "mean_qqq_proxy_constituent_weight_ratio",
        "minimum_qqq_proxy_constituent_weight_ratio",
        "maximum_qqq_proxy_constituent_weight_ratio",
    ) if proxy_mode else ()):
        _result_decimal(
            aggregates.get(name), "order-level aggregate " + name
        )
    for name in ("strategy_zero_rate_sharpe", "QQQ_zero_rate_sharpe"):
        _result_decimal(
            aggregates.get(name),
            "order-level aggregate " + name,
            optional=True,
        )
    for name in (
        "strategy_equity_path_sha256", "QQQ_raw_observation_sha256",
        "QQQ_return_path_sha256", "order_lifecycle_sha256",
        "pit_coverage_path_sha256", "pit_target_weight_path_sha256",
        "QQQ_calendar_close_raw_observation_sha256",
        "QQQ_calendar_close_return_path_sha256",
    ):
        _sha(aggregates.get(name), "order-level aggregate " + name)
    execution_failure = (
        aggregates["canceled_order_count_sum"] != 0
        or aggregates["invalid_order_count_sum"] != 0
        or aggregates["filled_order_count_sum"]
        != aggregates["submitted_order_count"]
        or aggregates["fee_mismatch"]
        or (
            forced_exit_mode
            and forced_delisting["accounting_complete"] is not True
        )
    )
    run_valid = (
        not execution_failure
        and aggregates["skipped_unpriced_decision_count"] == 0
        and (
            aggregates["completed_rebalance_count"]
            + (
                aggregates["forced_exit_invalidated_pending_rebalance_count"]
                if forced_exit_mode else 0
            )
            == aggregates["decision_count"]
        )
    )
    floor = _result_decimal(
        aggregates["minimum_required_resolved_constituent_weight_ratio"],
        "order-level aggregate minimum coverage floor",
    )
    minimum_covered_weight = _result_decimal(
        aggregates["minimum_resolved_constituent_weight_ratio"],
        "order-level aggregate minimum covered weight",
    )
    modeled_fee = _result_decimal(
        aggregates["modeled_fee_amount"],
        "order-level aggregate modeled fee",
    )
    actual_fee = _result_decimal(
        aggregates["actual_engine_fee_amount"],
        "order-level aggregate actual engine fee",
    )
    total_filled_notional = _result_decimal(
        aggregates["total_filled_notional"],
        "order-level aggregate total filled notional",
    )
    actual_effective_bps = _result_decimal(
        aggregates["actual_engine_fee_effective_bps_per_side"],
        "order-level aggregate actual effective fee bps",
    )
    modeled_minus_actual = _result_decimal(
        aggregates["modeled_minus_actual_fee_amount"],
        "order-level aggregate modeled-minus-actual fee",
    )
    minimum_weight_total = _result_decimal(
        aggregates["minimum_positive_constituent_weight_total"],
        "order-level aggregate minimum constituent weight total",
    )
    mean_weight_total = _result_decimal(
        aggregates["mean_positive_constituent_weight_total"],
        "order-level aggregate mean constituent weight total",
    )
    maximum_weight_total = _result_decimal(
        aggregates["maximum_positive_constituent_weight_total"],
        "order-level aggregate maximum constituent weight total",
    )
    minimum_required_weight_total = _result_decimal(
        aggregates["minimum_required_positive_constituent_weight_total"],
        "order-level aggregate required minimum constituent weight total",
    )
    maximum_allowed_weight_total = _result_decimal(
        aggregates["maximum_allowed_positive_constituent_weight_total"],
        "order-level aggregate allowed maximum constituent weight total",
    )
    if proxy_mode:
        proxy_minimum = _result_decimal(
            aggregates["minimum_qqq_proxy_constituent_weight_ratio"],
            "order-level aggregate minimum QQQ proxy ratio",
        )
        proxy_mean = _result_decimal(
            aggregates["mean_qqq_proxy_constituent_weight_ratio"],
            "order-level aggregate mean QQQ proxy ratio",
        )
        proxy_maximum = _result_decimal(
            aggregates["maximum_qqq_proxy_constituent_weight_ratio"],
            "order-level aggregate maximum QQQ proxy ratio",
        )
        mean_resolved = _result_decimal(
            aggregates["mean_resolved_constituent_weight_ratio"],
            "order-level aggregate mean resolved ratio",
        )
        minimum_resolved = _result_decimal(
            aggregates["minimum_resolved_constituent_weight_ratio"],
            "order-level aggregate minimum resolved ratio",
        )
        # This precision exceeds even V10's 8,192-byte transport cap, keeping
        # decimal complements exact rather than default-context rounded.
        with localcontext() as ratio_context:
            ratio_context.prec = (
                _PINNED_EXACT_COMPLEMENT_DECIMAL_PRECISION
                if diagnostic_mode else MAX_STATISTIC_BYTES * 4
            )
            ratios_conserve = (
                proxy_mean + mean_resolved == Decimal(1)
                and proxy_maximum + minimum_resolved == Decimal(1)
            )
        if (
            aggregates["qqq_proxy_overlap_disclosure"]
            != runtime_builder.QQQ_PROXY_OVERLAP_DISCLOSURE
            or not Decimal(0) <= proxy_minimum <= proxy_mean <= proxy_maximum
            <= Decimal("0.20")
            or not ratios_conserve
        ):
            _error("order-level QQQ ETF proxy accounting changed")
    benchmark_target_gross = _result_decimal(
        aggregates["QQQ_target_gross_exposure"],
        "order-level aggregate QQQ target gross exposure",
    )
    starting_equity = _result_decimal(
        aggregates["starting_equity"],
        "order-level aggregate starting equity",
    )
    ending_equity = _result_decimal(
        aggregates["ending_equity"],
        "order-level aggregate ending equity",
    )
    strategy_total_return = _result_decimal(
        aggregates["strategy_total_return"],
        "order-level aggregate strategy total return",
    )
    if account_mode:
        terminal_prior_equity = _result_decimal(
            aggregates["terminal_account_observation_prior_equity"],
            "order-level aggregate terminal prior equity",
        )
        terminal_observation_equity = _result_decimal(
            aggregates["terminal_account_observation_equity"],
            "order-level aggregate terminal observation equity",
        )
        terminal_adjustment = _result_decimal(
            aggregates["terminal_account_observation_adjustment"],
            "order-level aggregate terminal observation adjustment",
        )
        terminal_reconciliation_is_exact = (
            terminal_prior_equity > 0
            and terminal_observation_equity == ending_equity
            and terminal_adjustment
            == terminal_observation_equity - terminal_prior_equity
        )
    else:
        terminal_reconciliation_is_exact = True
    qqq_total_return = _result_decimal(
        aggregates["QQQ_total_return"],
        "order-level aggregate QQQ total return",
    )
    strategy_minus_qqq_total_return = _result_decimal(
        aggregates["strategy_minus_QQQ_total_return"],
        "order-level aggregate strategy-minus-QQQ total return",
    )
    strategy_maximum_drawdown = _result_decimal(
        aggregates["strategy_maximum_drawdown"],
        "order-level aggregate strategy maximum drawdown",
    )
    qqq_maximum_drawdown = _result_decimal(
        aggregates["QQQ_maximum_drawdown"],
        "order-level aggregate QQQ maximum drawdown",
    )
    strategy_annualized_volatility = _result_decimal(
        aggregates["strategy_annualized_volatility"],
        "order-level aggregate strategy annualized volatility",
    )
    qqq_annualized_volatility = _result_decimal(
        aggregates["QQQ_annualized_volatility"],
        "order-level aggregate QQQ annualized volatility",
    )
    calendar_qqq_total_return = _result_decimal(
        aggregates["QQQ_calendar_close_total_return"],
        "order-level aggregate calendar QQQ total return",
    )
    mean_gross_exposure = _result_decimal(
        aggregates["mean_gross_exposure"],
        "order-level aggregate mean gross exposure",
    )
    mean_cash_weight = _result_decimal(
        aggregates["mean_cash_weight"],
        "order-level aggregate mean cash weight",
    )
    mean_tilted_name_count = _result_decimal(
        aggregates["mean_tilted_name_count"],
        "order-level aggregate mean tilted name count",
    )
    mean_one_way_active_share = _result_decimal(
        aggregates["mean_one_way_active_share"],
        "order-level aggregate mean one-way active share",
    )
    mean_target_error = _result_decimal(
        aggregates["mean_reference_mark_target_weight_l1_error"],
        "order-level aggregate mean target-weight error",
    )
    maximum_target_error = _result_decimal(
        aggregates["maximum_reference_mark_target_weight_l1_error"],
        "order-level aggregate maximum target-weight error",
    )
    _safe_name(
        aggregates.get("QQQ_first_execution_session"),
        "order-level aggregate QQQ first execution session",
        10,
    )
    ratio_names = (
        "mean_resolved_member_count_ratio",
        "mean_resolved_constituent_weight_ratio",
        "minimum_resolved_member_count_ratio",
        "minimum_resolved_constituent_weight_ratio",
    )
    minimum_mean_ratio_pairs = (
        (
            "minimum_resolved_member_count_ratio",
            "mean_resolved_member_count_ratio",
        ),
        (
            "minimum_resolved_constituent_weight_ratio",
            "mean_resolved_constituent_weight_ratio",
        ),
    )
    with localcontext() as arithmetic_context:
        arithmetic_context.prec = MAX_STATISTIC_BYTES * 4
        modeled_fee_is_exact = (
            modeled_fee == total_filled_notional * Decimal("0.001")
        )
        modeled_minus_actual_is_exact = (
            modeled_minus_actual == modeled_fee - actual_fee
        )
        actual_effective_bps_is_exact = (
            actual_effective_bps
            == (
                Decimal(0)
                if total_filled_notional == 0
                else actual_fee
                / total_filled_notional
                * Decimal(10_000)
            )
        )
        strategy_return_is_exact = (
            ending_equity
            == starting_equity * (Decimal(1) + strategy_total_return)
        )
        strategy_minus_qqq_is_exact = (
            strategy_total_return - qqq_total_return
            == strategy_minus_qqq_total_return
        )
        exposure_sum_is_exact = (
            mean_gross_exposure + mean_cash_weight == Decimal(1)
        )
    if (
        aggregates["execution_failure"] is not execution_failure
        or aggregates["run_valid"] is not run_valid
        or aggregates["decision_count"] != expected_decision_count
        or aggregates["tilt_enabled_count"]
        + aggregates["tilt_underfilled_count"]
        != aggregates["decision_count"]
        or aggregates["pit_history_call_count"]
        != aggregates["decision_count"]
        or aggregates["coverage_decision_count"]
        != aggregates["decision_count"]
        or aggregates["resolved_positive_weight_member_count_sum"]
        > aggregates["positive_weight_member_count_sum"]
        or aggregates["filled_order_count_sum"]
        > aggregates["orders_with_any_fill_count_sum"]
        or aggregates["orders_with_any_fill_count_sum"]
        > aggregates["submitted_order_count"]
        or floor != (Decimal("0.80") if proxy_mode else Decimal("0.95"))
        or minimum_covered_weight < floor
        or aggregates["pit_target_weight_path_sha256"]
        == aggregates["pit_coverage_path_sha256"]
        or not modeled_fee_is_exact
        or actual_fee < 0
        or actual_effective_bps < 0
        or not modeled_minus_actual_is_exact
        or not actual_effective_bps_is_exact
        or (actual_fee != modeled_fee and not aggregates["fee_mismatch"])
        or minimum_required_weight_total != Decimal("0.95")
        or maximum_allowed_weight_total != Decimal("1.05")
        or benchmark_target_gross != Decimal("0.98")
        or starting_equity != Decimal("1000000")
        or ending_equity <= 0
        or not terminal_reconciliation_is_exact
        or not strategy_return_is_exact
        or strategy_total_return <= Decimal(-1)
        or qqq_total_return <= Decimal(-1)
        or calendar_qqq_total_return <= Decimal(-1)
        or not strategy_minus_qqq_is_exact
        or aggregates["QQQ_first_execution_session"]
        != expected_first_execution_session
        or aggregates["QQQ_observation_count"]
        != expected_observation_count
        or aggregates["QQQ_calendar_close_observation_count"]
        != expected_observation_count
        or aggregates["QQQ_return_interval_count"]
        != expected_return_interval_count
        or not Decimal(-1) <= strategy_maximum_drawdown <= Decimal(0)
        or not Decimal(-1) <= qqq_maximum_drawdown <= Decimal(0)
        or strategy_annualized_volatility < 0
        or qqq_annualized_volatility < 0
        or mean_gross_exposure < 0
        or mean_cash_weight < 0
        or not exposure_sum_is_exact
        or mean_tilted_name_count < 0
        or not Decimal(0) <= mean_one_way_active_share <= Decimal(1)
        or not Decimal(0) <= mean_target_error <= maximum_target_error
        or not (
            minimum_required_weight_total
            <= minimum_weight_total
            <= mean_weight_total
            <= maximum_weight_total
            <= maximum_allowed_weight_total
        )
        or any(
            not Decimal(0)
            <= _result_decimal(
                aggregates[name], "order-level aggregate " + name
            )
            <= Decimal(1)
            for name in ratio_names
        )
        or any(
            _result_decimal(
                aggregates[minimum_name],
                "order-level aggregate " + minimum_name,
            )
            > _result_decimal(
                aggregates[mean_name],
                "order-level aggregate " + mean_name,
            )
            for minimum_name, mean_name in minimum_mean_ratio_pairs
        )
        or total_filled_notional < 0
        or modeled_fee < 0
        or aggregates["maximum_constituent_snapshot_age_sessions"] != 1
    ):
        _error("order-level aggregate execution or coverage invariant changed")
    expected_aggregate_sha = hashlib.sha256(
        _canonical(aggregates)
    ).hexdigest()
    if meta.get("aggregates_sha256") != expected_aggregate_sha:
        _error("order-level aggregate digest changed")
    return tuple(pairs)


(_SEALED_RESULT_PARSER,) = _seal_local_function_graph(_parse_result)


def _aggregate_result_record(value):
    return {
        "plan_sha256": value.plan_sha256,
        "launch_sha256": value.launch_sha256,
        "terminal_sha256": value.terminal_sha256,
        "result_control_sha256": value.result_control_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "profile_id": value.profile_id,
        "profile_sha256": value.profile_sha256,
        "custom_statistics": [list(item) for item in value.custom_statistics],
        "custom_statistics_sha256": value.custom_statistics_sha256,
        "persisted_path": str(value.persisted_path),
        "backtests_read_call_count": value.backtests_read_call_count,
        "raw_orders_logs_charts_selected": value.raw_orders_logs_charts_selected,
    }


def _aggregate_result_bytes(value):
    identity, digest, payload = _identified(
        RESULT_SCHEMA, "arv2-order-level-result-", _aggregate_result_record(value)
    )
    if value.receipt_id != identity or value.receipt_sha256 != digest:
        _error("order-level durable aggregate result identity changed")
    return payload


def _load_order_level_aggregate_result_impl(
    *, plan, execution_authority, launch_control, launch, terminal,
    result_read_authority, result_control, execution_authority_verifier,
    result_authority_verifier, result_parser,
):
    plan = require_order_level_submission_plan(plan)
    execution_authority = execution_authority_verifier(
        value=execution_authority, plan=plan
    )
    _require_launch(launch, plan, launch_control)
    _require_terminal(terminal, plan, launch)
    result_read_authority = result_authority_verifier(
        value=result_read_authority,
        plan=plan,
        execution_authority=execution_authority,
        launch_control=launch_control,
        launch=launch,
        terminal=terminal,
    )
    persisted_control = load_order_level_result_control(
        plan=plan,
        launch=launch,
        terminal=terminal,
        result_read_authority=result_read_authority,
    )
    if persisted_control != result_control:
        _error("order-level aggregate result control lineage changed")
    path = _result_receipt_path(plan)
    payload = _read_private(path, "aggregate result")
    raw = _strict_object(payload, "aggregate result")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "result_control_sha256", "project_id",
        "backtest_id", "profile_id", "profile_sha256",
        "custom_statistics", "custom_statistics_sha256", "persisted_path",
        "backtests_read_call_count", "raw_orders_logs_charts_selected",
    }:
        _error("order-level aggregate result fields changed")
    rows = raw.get("custom_statistics")
    if type(rows) is not list or any(
        type(item) is not list
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        for item in rows
    ):
        _error("persisted order-level custom statistics changed")
    pairs = tuple((item[0], item[1]) for item in rows)
    result_parser(
        {
            "success": True,
            "backtest": {
                "backtestId": launch.backtest_id,
                "projectId": launch.project_id,
                "name": launch.backtest_name,
                "status": "Completed.",
                "statistics": dict(pairs),
            },
        },
        plan,
        launch,
    )
    value = OrderLevelAggregateResult(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("launch_sha256"), raw.get("terminal_sha256"),
        raw.get("result_control_sha256"), raw.get("project_id"),
        raw.get("backtest_id"), raw.get("profile_id"),
        raw.get("profile_sha256"), pairs,
        raw.get("custom_statistics_sha256"), Path(raw.get("persisted_path")),
        raw.get("backtests_read_call_count"),
        raw.get("raw_orders_logs_charts_selected"),
    )
    pairs_sha = hashlib.sha256(
        _canonical([list(item) for item in pairs])
    ).hexdigest()
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.result_control_sha256 != result_control.control_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or value.profile_id != plan.profile_id
        or value.profile_sha256 != plan.profile_sha256
        or value.custom_statistics_sha256 != pairs_sha
        or value.persisted_path != path
        or value.backtests_read_call_count != 1
        or value.raw_orders_logs_charts_selected is not False
        or payload != _aggregate_result_bytes(value)
    ):
        _error("persisted order-level aggregate result changed")
    return value


def _bind_aggregate_result_loader(
    *, loader_impl, execution_authority_verifier,
    result_authority_verifier, result_parser, dependency_guard,
):
    """Capture all signed reload authorities and the exact result parser."""

    def load_order_level_aggregate_result(
        *, plan, execution_authority, launch_control, launch, terminal,
        result_read_authority, result_control,
    ):
        dependency_guard()
        return loader_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_read_authority,
            result_control=result_control,
            execution_authority_verifier=execution_authority_verifier,
            result_authority_verifier=result_authority_verifier,
            result_parser=result_parser,
        )

    return load_order_level_aggregate_result


load_order_level_aggregate_result = _bind_aggregate_result_loader(
    loader_impl=_load_order_level_aggregate_result_impl,
    execution_authority_verifier=require_order_level_execution_authority,
    result_authority_verifier=require_order_level_result_read_authority,
    result_parser=_SEALED_RESULT_PARSER,
    dependency_guard=_make_module_dependency_guard(
        "order-level aggregate loader",
        _load_order_level_aggregate_result_impl,
    ),
)
del _bind_aggregate_result_loader


def _read_order_level_aggregate_result_once_impl(
    *, plan, execution_authority, launch_control, launch, terminal,
    result_read_authority, client, started_at_utc, minter,
    transport_verifier, result_authority_verifier, result_parser,
    _transport=_transport,
):
    plan = require_order_level_submission_plan(plan)
    launch = _require_launch(launch, plan, launch_control)
    terminal = _require_terminal(terminal, plan, launch)
    result_read_authority = result_authority_verifier(
        value=result_read_authority,
        plan=plan,
        execution_authority=execution_authority,
        launch_control=launch_control,
        launch=launch,
        terminal=terminal,
    )
    transport_verifier(client)
    result_control = _spend_result_control(
        plan, launch, terminal, result_read_authority, started_at_utc
    )
    capability = minter(
        transport=client,
        scope="result_read",
        binding_record={
            "schema": "arv2-order-level-result-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "result_read_authority_sha256": (
                result_read_authority.authority_sha256
            ),
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal.receipt_sha256,
            "result_control_sha256": result_control.control_sha256,
        },
        call_budget=dict(result_read_authority.result_call_budget),
    )
    failure_type = None
    outcome = None
    try:
        pairs = result_parser(
            _transport(
                client,
                capability,
                "_read_backtest_result",
                launch.project_id,
                launch.backtest_id,
            ),
            plan,
            launch,
        )
        statistics_sha = hashlib.sha256(_canonical([list(item) for item in pairs])).hexdigest()
        path = _result_receipt_path(plan)
        provisional = OrderLevelAggregateResult(
            "",
            "",
            plan.plan_sha256,
            launch.receipt_sha256,
            terminal.receipt_sha256,
            result_control.control_sha256,
            launch.project_id,
            launch.backtest_id,
            plan.profile_id,
            plan.profile_sha256,
            pairs,
            statistics_sha,
            path,
            1,
            False,
        )
        record = _aggregate_result_record(provisional)
        identity, digest, _payload = _identified(
            RESULT_SCHEMA, "arv2-order-level-result-", record
        )
        result = dataclasses.replace(
            provisional, receipt_id=identity, receipt_sha256=digest
        )
        _write_private_once(
            path, _aggregate_result_bytes(result), "aggregate result"
        )
        outcome = (result_control, result)
    except AcceptedRiskOrderLevelSubmissionLocked:
        raise
    except Exception as exc:
        failure_type = type(exc).__name__
        client = None
        capability = None
        pairs = None
        statistics_sha = None
        path = None
        provisional = None
        record = None
        identity = None
        digest = None
        _payload = None
        result = None
        outcome = None
    if failure_type is not None:
        # The response parser can observe remote strings.  Raise only after
        # the original exception is out of scope so neither cause nor context
        # can expose those strings through the adapter boundary.
        raise AcceptedRiskOrderLevelSubmissionLocked(
            "result_read", result_control.control_id, failure_type
        ) from None
    return outcome


def _bind_public_actions(
    *, minter, seal_minter, transport_verifier,
    execution_authority_verifier, result_authority_verifier, result_parser,
    transport_dispatch, dependency_guard,
):
    execute_impl = _execute_order_level_submission_once_impl
    inspect_impl = _inspect_order_level_terminal_status_impl
    recover_impl = _recover_order_level_launch_receipt_once_impl
    read_impl = _read_order_level_aggregate_result_once_impl

    def execute_order_level_submission_once(
        *, plan: OrderLevelSubmissionPlan,
        execution_authority: OrderLevelExecutionAuthority,
        client: FormalQcTransport, started_at_utc: str,
    ):
        dependency_guard()
        return execute_impl(
            plan=plan,
            execution_authority=execution_authority,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            transport_verifier=transport_verifier,
            authority_verifier=execution_authority_verifier,
            _transport=transport_dispatch,
        )

    def inspect_order_level_terminal_status(
        *, plan: OrderLevelSubmissionPlan,
        execution_authority: OrderLevelExecutionAuthority,
        launch_control: OrderLevelLaunchControl,
        launch: OrderLevelLaunchReceipt,
        client: FormalQcTransport,
    ):
        dependency_guard()
        return inspect_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            client=client,
            minter=minter,
            transport_verifier=transport_verifier,
            authority_verifier=execution_authority_verifier,
            _transport=transport_dispatch,
        )

    def recover_order_level_launch_receipt_once(
        *, plan: OrderLevelSubmissionPlan,
        execution_authority: OrderLevelExecutionAuthority,
        launch_control: OrderLevelLaunchControl,
        client: FormalQcTransport,
    ):
        dependency_guard()
        return recover_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            client=client,
            minter=minter,
            transport_verifier=transport_verifier,
            authority_verifier=execution_authority_verifier,
            _transport=transport_dispatch,
        )

    def read_order_level_aggregate_result_once(
        *, plan: OrderLevelSubmissionPlan,
        execution_authority: OrderLevelExecutionAuthority,
        launch_control: OrderLevelLaunchControl,
        launch: OrderLevelLaunchReceipt,
        terminal: OrderLevelTerminalStatus,
        result_read_authority: OrderLevelResultReadAuthority,
        client: FormalQcTransport,
        started_at_utc: str,
    ):
        dependency_guard()
        return read_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=launch_control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_read_authority,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            transport_verifier=transport_verifier,
            result_authority_verifier=result_authority_verifier,
            result_parser=result_parser,
            _transport=transport_dispatch,
        )

    seal_minter(
        (
            (
                "submission",
                ((execute_impl, execute_order_level_submission_once),),
            ),
            (
                "status",
                (
                    (
                        inspect_impl,
                        inspect_order_level_terminal_status,
                    ),
                    (
                        recover_impl,
                        recover_order_level_launch_receipt_once,
                    ),
                ),
            ),
            (
                "result_read",
                ((read_impl, read_order_level_aggregate_result_once),),
            ),
        )
    )
    return (
        execute_order_level_submission_once,
        inspect_order_level_terminal_status,
        recover_order_level_launch_receipt_once,
        read_order_level_aggregate_result_once,
    )


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_accepted_risk_order_level_transport_capability_minter()

(
    execute_order_level_submission_once,
    inspect_order_level_terminal_status,
    recover_order_level_launch_receipt_once,
    read_order_level_aggregate_result_once,
) = _bind_public_actions(
    minter=_transport_capability_minter,
    seal_minter=_seal_transport_capability_callers,
    transport_verifier=_ORDER_TRANSPORT_VERIFIER,
    execution_authority_verifier=require_order_level_execution_authority,
    result_authority_verifier=require_order_level_result_read_authority,
    result_parser=_SEALED_RESULT_PARSER,
    transport_dispatch=_transport,
    dependency_guard=_make_module_dependency_guard(
        "order-level public action",
        _execute_order_level_submission_once_impl,
        _inspect_order_level_terminal_status_impl,
        _recover_order_level_launch_receipt_once_impl,
        _read_order_level_aggregate_result_once_impl,
    ),
)

del _transport_capability_minter
del _seal_transport_capability_callers
del _bind_public_actions
del _make_module_dependency_guard


__all__ = (
    "AcceptedRiskOrderLevelSubmissionError",
    "AcceptedRiskOrderLevelSubmissionLocked",
    "AcceptedRiskOrderLevelTerminalFailure",
    "OrderLevelAggregateResult",
    "OrderLevelExecutionAuthority",
    "OrderLevelLaunchControl",
    "OrderLevelLaunchCheckpoint",
    "OrderLevelLaunchReceipt",
    "OrderLevelLaunchRecoveryControl",
    "OrderLevelResultControl",
    "OrderLevelResultReadAuthority",
    "OrderLevelStatusPollCheckpoint",
    "OrderLevelSubmissionPlan",
    "OrderLevelTerminalStatus",
    "OrderLevelUploadEntry",
    "PROFILE_IDS",
    "build_order_level_submission_plan",
    "execute_order_level_submission_once",
    "inspect_order_level_terminal_status",
    "load_order_level_aggregate_result",
    "load_order_level_execution_authority",
    "load_order_level_launch_control",
    "load_order_level_launch_receipt",
    "load_order_level_result_control",
    "load_order_level_result_read_authority",
    "load_order_level_submission_plan",
    "load_order_level_terminal_status",
    "persist_order_level_submission_plan",
    "read_order_level_aggregate_result_once",
    "render_order_level_execution_authority_candidate",
    "render_order_level_result_read_authority_candidate",
    "recover_order_level_launch_receipt_once",
    "require_order_level_submission_plan",
    "require_order_level_execution_authority",
    "require_order_level_result_read_authority",
)
