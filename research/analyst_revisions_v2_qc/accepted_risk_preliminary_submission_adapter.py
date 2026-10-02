"""Signed, one-use host adapter for the accepted-risk preliminary QC run.

The adapter is intentionally narrower than the formal evaluator adapter.  It
binds one already-authenticated compact package and its exact QC source
projection, spends an owner-only local permit before any network access,
creates one new private project, uploads the package activation object last,
compiles, and creates exactly one backtest.  Status polling is statistics-free.

After a completed run, a separately signed ``formal_qc_result_read`` authority
spends a second one-use local permit before exactly one ``backtests/read``
call.  Only the exact profile-bound preliminary ``ARV2_*`` aggregate custom
statistics are selected, validated, returned, and persisted.  Raw provider
rows, price rows, logs, charts, orders, trades, deployment, and trading are
outside this module.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import threading
import time
import weakref
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Callable, Mapping, NoReturn

from research.analyst_revisions_v2 import preregistration

from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_preliminary_qc_projection as projection_builder
from . import accepted_risk_preliminary_qc_runtime as preliminary_runtime
from . import accepted_risk_preliminary_rating_evaluator as preliminary_evaluator
from . import accepted_risk_regime_rating_evaluator as regime_evaluator
from . import accepted_risk_etf_baseline_evaluator as etf_evaluator
from . import accepted_risk_etf_baseline_qc_runtime as etf_runtime
from . import accepted_risk_stock_portfolio_evaluator as stock_portfolio_evaluator
from . import (
    accepted_risk_market_cap_stock_portfolio_evaluator as market_cap_evaluator,
)
from . import (
    accepted_risk_market_cap_stock_portfolio_qc_runtime as market_cap_runtime,
)
from . import (
    accepted_risk_objective_synthetic_leverage_evaluator as leverage_evaluator,
)
from . import (
    accepted_risk_objective_synthetic_leverage_qc_runtime as leverage_runtime,
)
from . import accepted_risk_six_universe_gate as six_universe_gate
from . import (
    accepted_risk_six_universe_gate_evaluator as six_universe_evaluator,
)
from . import (
    accepted_risk_six_universe_gate_qc_runtime as six_universe_runtime,
)
from . import formal_submission_adapter as formal
from .formal_qc_transport import FormalQcTransport
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_formal_execution_owner_signature,
    require_formal_result_read_owner_signature,
)


class AcceptedRiskPreliminarySubmissionError(ValueError):
    """A local authority, plan, QC envelope, or aggregate result is invalid."""


class AcceptedRiskPreliminarySubmissionLocked(RuntimeError):
    """A durable one-use permit was spent and the external action is final."""

    def __init__(self, phase: str, permit_id: str, detail: str) -> None:
        super().__init__(
            f"{phase}: {detail}; accepted-risk preliminary permit remains consumed"
        )
        self.phase = phase
        self.permit_id = permit_id


class AcceptedRiskPreliminaryTerminalFailure(RuntimeError):
    """The exact preliminary run reached a non-success terminal state."""

    def __init__(self, receipt: "AcceptedRiskPreliminaryTerminalStatus") -> None:
        super().__init__(
            "accepted-risk preliminary backtest reached authenticated terminal failure"
        )
        self.receipt = receipt


PLAN_SCHEMA = "arv2-accepted-risk-preliminary-qc-submission-plan-v1"
REGIME_PLAN_SCHEMA = "arv2-accepted-risk-preliminary-qc-submission-plan-v2"
EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-execution-authority-v1"
)
EXECUTION_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-execution-one-use-permit-v1"
)
PRECREATE_CONTROL_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-pre-create-control-v1"
)
LAUNCH_RECOVERY_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-launch-recovery-one-use-permit-v1"
)
LAUNCH_SCHEMA = "arv2-accepted-risk-preliminary-qc-launch-receipt-v1"
TERMINAL_SCHEMA = "arv2-accepted-risk-preliminary-qc-terminal-status-v1"
RESULT_AUTHORITY_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-result-read-authority-v1"
)
RESULT_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-result-read-one-use-permit-v1"
)
RESULT_RECEIPT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-aggregate-result-receipt-v1"
)
UPLOAD_ENTRY_SCHEMA = "arv2-accepted-risk-preliminary-qc-submission-upload-v1"
HOST_CLOSURE_SCHEMA = "arv2-accepted-risk-preliminary-qc-host-closure-v1"
MAX_CONTROL_BYTES = 1024 * 1024
MAX_HOST_SOURCE_BYTES = 4 * 1024 * 1024
MAX_PROJECT_NAME_BYTES = 100
MAX_BACKTEST_NAME_BYTES = 200
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 1_440
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
QC_DEFAULT_RESEARCH_NOTEBOOK_PATH = "research.ipynb"
RECOVERED_LAUNCH_INITIAL_STATUS = "RECOVERED_BY_STATISTICS_FREE_LIST"

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_CELL_NAME = re.compile(
    r"ARV2_IC_(CUR|CEN)_(FIRM|GLOBAL)_H(1|5|20|60)_"
    r"(2020_2025|2021_2025)\Z"
)
# Bind the complete lane-local host implementation, not merely the handful of
# entry-point modules.  Package authentication and aggregate validation call
# through several lane helpers (including canonical/artifact IO and the cloud
# runtime/evaluator contract); a signature must not survive a fresh-process
# change to any of those semantics.  The two directories are inventoried
# exactly and deterministically, while the small set of imported helpers that
# live outside them is named explicitly.
HOST_CODE_DIRECTORY_PATHS = (
    "research/analyst_revisions_v2",
    "research/analyst_revisions_v2_qc",
)
HOST_CODE_PATHS = (
    "data/__init__.py",
    "data/exchange_calendar.py",
    "data/financial_primitives.py",
    "research/__init__.py",
    "research/quantconnect.py",
    "scripts/build_arv2_historical_preopen_bridge.py",
    "scripts/build_arv2_massive_input_pair.py",
    "scripts/build_arv2_preopen_input.py",
    "scripts/capture_arv2_massive.py",
    "scripts/capture_arv2_sharadar.py",
)
_PINNED_REQUIRE_PACKAGE = package_builder.require_accepted_risk_preliminary_package
_PINNED_ITER_UPLOADS = package_builder.iter_accepted_risk_preliminary_upload_objects
_PINNED_REQUIRE_PROJECTION = (
    projection_builder.require_accepted_risk_preliminary_qc_projection
)
_PINNED_PROJECTION_PROFILE_CALLABLE = projection_builder._profile
_PINNED_PROJECTION_SOURCE_PATHS_CALLABLE = (
    projection_builder.project_source_paths_for_profile
)
_PINNED_PROJECTION_STOCK_SOURCE_PATHS = tuple(
    projection_builder.STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS
)
_PINNED_PROJECTION_STOCK_PROFILE_IDS = tuple(
    projection_builder.STOCK_PORTFOLIO_PROFILE_IDS
)
_PINNED_PROJECTION_STOCK_UNIVERSE_PROFILE_IDS = tuple(
    projection_builder.STOCK_UNIVERSE_PROFILE_IDS
)
_PINNED_PROJECTION_STOCK_PROFILE_SHA256S_OBJECT = (
    projection_builder.STOCK_PORTFOLIO_PROFILE_SHA256S
)
_PINNED_PROJECTION_STOCK_PROFILE_SHA256_ROWS = tuple(
    sorted(_PINNED_PROJECTION_STOCK_PROFILE_SHA256S_OBJECT.items())
)
_PINNED_EXPECTED_RESULT_NAMES = tuple(
    preliminary_runtime.EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES
)
_PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE = (
    preliminary_runtime.expected_custom_summary_statistic_names
)
_PINNED_MAX_TRAIN_SLICE_COUNT = preliminary_runtime.MAX_TRAIN_SLICE_COUNT
_PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_ID = (
    preliminary_runtime.STOCK_PORTFOLIO_PROFILE_ID
)
_PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_IDS = tuple(
    preliminary_runtime.STOCK_PORTFOLIO_PROFILE_IDS
)
_PINNED_RUNTIME_STOCK_UNIVERSE_PROFILE_IDS = tuple(
    preliminary_runtime.STOCK_UNIVERSE_PROFILE_IDS
)
_PINNED_RUNTIME_STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS = tuple(
    preliminary_runtime.STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
)
_PINNED_RUNTIME_STOCK_MEMBERSHIP_ONLY_PROFILE_IDS = tuple(
    preliminary_runtime.STOCK_MEMBERSHIP_ONLY_PROFILE_IDS
)
_PINNED_REQUIRE_REGIME_PROFILE = regime_evaluator.require_regime_profile
_PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE = (
    stock_portfolio_evaluator.require_stock_portfolio_profile
)
_PINNED_STOCK_PORTFOLIO_RESULT_NAMES_CALLABLE = (
    stock_portfolio_evaluator.expected_custom_summary_statistic_names
)
_PINNED_STOCK_PORTFOLIO_CONSTITUENT_TICKERS_CALLABLE = (
    stock_portfolio_evaluator.constituent_etf_tickers_for_profile
)
_PINNED_STOCK_PORTFOLIO_SNAPSHOT_MAXIMUM_AGE_CALLABLE = (
    stock_portfolio_evaluator.constituent_snapshot_maximum_age_calendar_days_for_profile
)
_PINNED_STOCK_PORTFOLIO_POSITIVE_COUNT_BOUNDS_CALLABLE = (
    stock_portfolio_evaluator.constituent_positive_count_bounds_for_profile
)
_PINNED_STOCK_PORTFOLIO_PROFILE_OBJECT = stock_portfolio_evaluator._PROFILE
_PINNED_STOCK_PORTFOLIO_PROFILE_ID = stock_portfolio_evaluator.PROFILE_ID
_PINNED_STOCK_PORTFOLIO_PROFILE_IDS = tuple(
    stock_portfolio_evaluator.PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_VARIANT_PROFILE_IDS = tuple(
    stock_portfolio_evaluator.VARIANT_PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_UNIVERSE_PROFILE_IDS = tuple(
    stock_portfolio_evaluator.UNIVERSE_PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_STATE_UNTIL_SUPERSEDED_PROFILE_IDS = tuple(
    stock_portfolio_evaluator.STATE_UNTIL_SUPERSEDED_PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_MEMBERSHIP_ONLY_PROFILE_IDS = tuple(
    stock_portfolio_evaluator.MEMBERSHIP_ONLY_PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_CANONICAL_ROWS_OBJECT = (
    stock_portfolio_evaluator._PROFILE_CANONICAL_ROWS
)
_PINNED_STOCK_PORTFOLIO_CONTRACT_ID = stock_portfolio_evaluator.CONTRACT_ID
_PINNED_STOCK_PORTFOLIO_SUMMARY_SCHEMA = stock_portfolio_evaluator.SUMMARY_SCHEMA
_PINNED_STOCK_PORTFOLIO_CELL_SCHEMA = (
    stock_portfolio_evaluator.PORTFOLIO_CELL_SCHEMA
)
_PINNED_STOCK_PORTFOLIO_EXPECTED_DECISIONS = (
    stock_portfolio_evaluator.EXPECTED_DECISION_SESSION_COUNT
)
_PINNED_STOCK_PORTFOLIO_EXPECTED_RETURNS = (
    stock_portfolio_evaluator.EXPECTED_RETURN_SESSION_COUNT
)
_PINNED_STOCK_PORTFOLIO_MAXIMUM_HOLDINGS = (
    stock_portfolio_evaluator.MAXIMUM_HOLDINGS
)
_PINNED_STOCK_PORTFOLIO_MINIMUM_INVESTED_RETURNS = (
    stock_portfolio_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS
)
_PINNED_STOCK_PORTFOLIO_COSTS = tuple(
    stock_portfolio_evaluator.COST_BPS_SCENARIOS
)
_PINNED_STOCK_PORTFOLIO_PRIMARY_COST = (
    stock_portfolio_evaluator.PRIMARY_COST_BPS
)
_PINNED_STOCK_PORTFOLIO_ANNUALIZATION_SESSIONS = (
    stock_portfolio_evaluator.ANNUALIZATION_SESSIONS
)
_PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS = tuple(
    (
        profile_id,
        json.dumps(
            _PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE(profile_id),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii"),
        _PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE(profile_id)[
            "profile_sha256"
        ],
        tuple(
            sorted(
                (
                    *_PINNED_STOCK_PORTFOLIO_RESULT_NAMES_CALLABLE(
                        profile_id
                    ),
                    "ARV2_RUNTIME_META",
                )
            )
        ),
    )
    for profile_id in _PINNED_STOCK_PORTFOLIO_PROFILE_IDS
)
_PINNED_STOCK_PORTFOLIO_PROFILE_BYTES = (
    _PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS[0][1]
)
_PINNED_STOCK_PORTFOLIO_PROFILE_SHA256 = (
    _PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS[0][2]
)
_PINNED_STOCK_PORTFOLIO_RESULT_NAMES = (
    _PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS[0][3]
)
_PINNED_PROJECTION_MARKET_CAP_SOURCE_PATHS = tuple(
    projection_builder.MARKET_CAP_PROJECT_SOURCE_PATHS
)
_PINNED_PROJECTION_MARKET_CAP_LEGACY_SOURCE_PATHS = tuple(
    projection_builder.MARKET_CAP_LEGACY_PROJECT_SOURCE_PATHS
)
_PINNED_PROJECTION_MARKET_CAP_PROFILE_IDS = tuple(
    projection_builder.MARKET_CAP_PROFILE_IDS
)
_PINNED_PROJECTION_MARKET_CAP_V1_PROFILE_IDS = tuple(
    projection_builder.MARKET_CAP_V1_PROFILE_IDS
)
_PINNED_PROJECTION_MARKET_CAP_V2_PROFILE_IDS = tuple(
    projection_builder.MARKET_CAP_V2_PROFILE_IDS
)
_PINNED_PROJECTION_MARKET_CAP_V3_PROFILE_IDS = tuple(
    projection_builder.MARKET_CAP_V3_PROFILE_IDS
)
_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_IDS = tuple(
    projection_builder.MARKET_CAP_ALL_PROFILE_IDS
)
_PINNED_PROJECTION_SUPERSEDED_UNSPENT_PROFILE_IDS = tuple(
    projection_builder.SUPERSEDED_UNSPENT_PROFILE_IDS
)
_PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256S_OBJECT = (
    projection_builder.MARKET_CAP_PROFILE_SHA256S
)
_PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256_ROWS = tuple(
    sorted(_PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256S_OBJECT.items())
)
_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256S_OBJECT = (
    projection_builder.MARKET_CAP_ALL_PROFILE_SHA256S
)
_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256_ROWS = tuple(
    sorted(_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256S_OBJECT.items())
)
_PINNED_REQUIRE_MARKET_CAP_PROFILE = (
    market_cap_evaluator.require_market_cap_stock_portfolio_profile
)
_PINNED_MARKET_CAP_RESULT_NAMES_CALLABLE = (
    market_cap_evaluator.expected_custom_summary_statistic_names
)
_PINNED_MARKET_CAP_CONSTITUENT_TICKERS_CALLABLE = (
    market_cap_evaluator.constituent_etf_tickers_for_profile
)
_PINNED_MARKET_CAP_PROFILE_IDS = tuple(market_cap_evaluator.PROFILE_IDS)
_PINNED_MARKET_CAP_V1_PROFILE_IDS = tuple(market_cap_evaluator.V1_PROFILE_IDS)
_PINNED_MARKET_CAP_V2_PROFILE_IDS = tuple(market_cap_evaluator.V2_PROFILE_IDS)
_PINNED_MARKET_CAP_V3_PROFILE_IDS = tuple(market_cap_evaluator.V3_PROFILE_IDS)
_PINNED_MARKET_CAP_TILT_PROFILE_IDS = tuple(
    market_cap_evaluator.TILT_PROFILE_IDS
)
_PINNED_MARKET_CAP_ALL_PROFILE_IDS = tuple(
    market_cap_evaluator.ALL_PROFILE_IDS
)
_PINNED_MARKET_CAP_QQQ_PROFILE_IDS = tuple(
    market_cap_evaluator.QQQ_PROFILE_IDS
)
_PINNED_MARKET_CAP_SPY_PROFILE_IDS = tuple(
    market_cap_evaluator.SPY_PROFILE_IDS
)
_PINNED_MARKET_CAP_PROFILE_CANONICAL_OBJECT = (
    market_cap_evaluator._PROFILE_CANONICAL
)
_PINNED_MARKET_CAP_PROFILE_CANONICAL_ROWS = tuple(
    sorted(_PINNED_MARKET_CAP_PROFILE_CANONICAL_OBJECT.items())
)
_PINNED_MARKET_CAP_CONTRACT_ID = market_cap_evaluator.CONTRACT_ID
_PINNED_MARKET_CAP_SUMMARY_SCHEMA = market_cap_evaluator.SUMMARY_SCHEMA
_PINNED_MARKET_CAP_CELL_SCHEMA = market_cap_evaluator.PORTFOLIO_CELL_SCHEMA
_PINNED_MARKET_CAP_META_STATISTIC_NAME = (
    market_cap_evaluator.META_STATISTIC_NAME
)
_PINNED_MARKET_CAP_SELECTED_AGGREGATES_STATISTIC_NAME = (
    market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
)
_PINNED_MARKET_CAP_MATCHED_AGGREGATES_STATISTIC_NAME = (
    market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME
)
_PINNED_MARKET_CAP_TILT_AGGREGATES_STATISTIC_NAME = (
    market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
)
_PINNED_MARKET_CAP_TILT_AGGREGATES_SCHEMA = (
    market_cap_evaluator.TILT_AGGREGATES_SCHEMA
)
_PINNED_MARKET_CAP_MAXIMUM_HOLDINGS = market_cap_evaluator.MAXIMUM_HOLDINGS
_PINNED_MARKET_CAP_TARGET_GROSS = market_cap_evaluator.TARGET_GROSS_EXPOSURE
_PINNED_MARKET_CAP_PORTFOLIO_WEIGHT_QUANTUM = (
    market_cap_evaluator.PORTFOLIO_WEIGHT_QUANTUM
)
_PINNED_MARKET_CAP_MINIMUM_TILT_RANKED_NAMES = (
    market_cap_evaluator.MINIMUM_TILT_RANKED_NAME_COUNT
)
_PINNED_MARKET_CAP_MINIMUM_TILT_POSITIVE_SCORES = (
    market_cap_evaluator.MINIMUM_TILT_POSITIVE_SCORE_COUNT
)
_PINNED_MARKET_CAP_MINIMUM_TILT_NEGATIVE_SCORES = (
    market_cap_evaluator.MINIMUM_TILT_NEGATIVE_SCORE_COUNT
)
_PINNED_MARKET_CAP_MAXIMUM_RELATIVE_TILT = (
    market_cap_evaluator.MAXIMUM_RELATIVE_TILT
)
_PINNED_MARKET_CAP_MAXIMUM_ABSOLUTE_OVERWEIGHT = (
    market_cap_evaluator.MAXIMUM_ABSOLUTE_OVERWEIGHT
)
_PINNED_MARKET_CAP_MAXIMUM_ONE_WAY_ACTIVE_SHARE = (
    market_cap_evaluator.MAXIMUM_ONE_WAY_ACTIVE_SHARE
)
_PINNED_MARKET_CAP_MAXIMUM_HHI_MULTIPLE = (
    market_cap_evaluator.MAXIMUM_HHI_MULTIPLE
)
_PINNED_MARKET_CAP_MINIMUM_INVESTED_RETURNS = (
    market_cap_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS
)
_PINNED_MARKET_CAP_COSTS = tuple(market_cap_evaluator.COST_BPS_SCENARIOS)
_PINNED_MARKET_CAP_PRIMARY_COST = market_cap_evaluator.PRIMARY_COST_BPS
_PINNED_MARKET_CAP_ANNUALIZATION_SESSIONS = (
    market_cap_evaluator.ANNUALIZATION_SESSIONS
)
_PINNED_MARKET_CAP_RUNTIME_EXPECTED_NAMES = (
    market_cap_runtime.expected_custom_summary_statistic_names
)
_PINNED_MARKET_CAP_RUNTIME_PROFILE_IDS = tuple(market_cap_runtime.PROFILE_IDS)
_PINNED_MARKET_CAP_RUNTIME_MAX_TRAIN_SLICES = (
    market_cap_runtime.MAX_TRAIN_SLICE_COUNT
)
_PINNED_MARKET_CAP_RUNTIME_MAX_HISTORY_CHUNKS = (
    market_cap_runtime.MAX_HISTORY_CHUNKS
)
_PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS = (
    market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT
)
_PINNED_MARKET_CAP_RUNTIME_MAX_TOTAL_SOURCE_ROWS = (
    market_cap_runtime.MAX_TOTAL_SOURCE_ROWS
)
_PINNED_MARKET_CAP_PROFILE_BINDINGS = tuple(
    (
        profile_id,
        json.dumps(
            _PINNED_REQUIRE_MARKET_CAP_PROFILE(profile_id),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii"),
        _PINNED_REQUIRE_MARKET_CAP_PROFILE(profile_id)["profile_sha256"],
        tuple(
            sorted(
                (
                    *_PINNED_MARKET_CAP_RESULT_NAMES_CALLABLE(profile_id),
                    "ARV2_RUNTIME_META",
                )
            )
        ),
    )
    for profile_id in _PINNED_MARKET_CAP_ALL_PROFILE_IDS
)
_PINNED_PROJECTION_LEVERAGE_SOURCE_PATHS = tuple(
    projection_builder.OBJECTIVE_LEVERAGE_PROJECT_SOURCE_PATHS
)
_PINNED_PROJECTION_LEVERAGE_PROFILE_IDS = tuple(
    projection_builder.OBJECTIVE_LEVERAGE_PROFILE_IDS
)
_PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256S_OBJECT = (
    projection_builder.OBJECTIVE_LEVERAGE_PROFILE_SHA256S
)
_PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256_ROWS = tuple(
    sorted(_PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256S_OBJECT.items())
)
_PINNED_REQUIRE_LEVERAGE_PROFILE = leverage_evaluator.require_profile
_PINNED_LEVERAGE_RESULT_NAMES_CALLABLE = (
    leverage_evaluator.expected_custom_summary_statistic_names
)
_PINNED_LEVERAGE_PROFILE_IDS = tuple(leverage_evaluator.PROFILE_IDS)
_PINNED_LEVERAGE_V1_PROFILE_IDS = tuple(leverage_evaluator.V1_PROFILE_IDS)
_PINNED_LEVERAGE_V2_PROFILE_IDS = tuple(leverage_evaluator.V2_PROFILE_IDS)
_PINNED_LEVERAGE_ALL_PROFILE_IDS = tuple(leverage_evaluator.ALL_PROFILE_IDS)
_PINNED_LEVERAGE_PROFILE_CANONICAL_OBJECT = leverage_evaluator._PROFILE_CANONICAL
_PINNED_LEVERAGE_PROFILE_CANONICAL_ROWS = tuple(
    sorted(_PINNED_LEVERAGE_PROFILE_CANONICAL_OBJECT.items())
)
_PINNED_LEVERAGE_CONTRACT_ID = leverage_evaluator.CONTRACT_ID
_PINNED_LEVERAGE_SUMMARY_SCHEMA = leverage_evaluator.SUMMARY_SCHEMA
_PINNED_LEVERAGE_CELL_SCHEMA = leverage_evaluator.CELL_SCHEMA
_PINNED_LEVERAGE_META_STATISTIC_NAME = leverage_evaluator.META_STATISTIC_NAME
_PINNED_LEVERAGE_SELECTED_BASE_AGGREGATES_STATISTIC_NAME = (
    leverage_evaluator.SELECTED_BASE_AGGREGATES_STATISTIC_NAME
)
_PINNED_LEVERAGE_MATCHED_BASE_AGGREGATES_STATISTIC_NAME = (
    leverage_evaluator.MATCHED_BASE_AGGREGATES_STATISTIC_NAME
)
_PINNED_LEVERAGE_BASE_SOURCE_SHA256 = (
    leverage_evaluator.BASE_EVALUATOR_SOURCE_SHA256
)
_PINNED_LEVERAGE_FACTORS = tuple(leverage_evaluator.LEVERAGE_FACTORS)
_PINNED_LEVERAGE_SCENARIOS = tuple(leverage_evaluator.SCENARIOS)
_PINNED_LEVERAGE_PRIMARY_SCENARIO_ID = (
    leverage_evaluator.PRIMARY_SCENARIO_ID
)
_PINNED_LEVERAGE_ADVERSE_SCENARIO_ID = (
    leverage_evaluator.ADVERSE_SCENARIO_ID
)
_PINNED_LEVERAGE_ANNUALIZATION_SESSIONS = (
    leverage_evaluator.ANNUALIZATION_SESSIONS
)
_PINNED_LEVERAGE_RUNTIME_EXPECTED_NAMES = (
    leverage_runtime.expected_custom_summary_statistic_names
)
_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_CALLABLE = (
    leverage_runtime.base_market_cap_profile_id_for_profile
)
_PINNED_LEVERAGE_RUNTIME_CONSTITUENT_TICKERS_CALLABLE = (
    leverage_runtime.constituent_etf_tickers_for_profile
)
_PINNED_LEVERAGE_RUNTIME_PROFILE_IDS = tuple(leverage_runtime.PROFILE_IDS)
_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_MAP_OBJECT = (
    leverage_runtime._BASE_PROFILE_BY_LEVERAGE
)
_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_ROWS = tuple(
    sorted(_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_MAP_OBJECT.items())
)
_PINNED_LEVERAGE_RUNTIME_SCHEMA = leverage_runtime.RUNTIME_META_SCHEMA
_PINNED_LEVERAGE_RUNTIME_STATUS = leverage_runtime.RUNTIME_COMPLETED_STATUS
_PINNED_LEVERAGE_RUNTIME_MAX_TRAIN_SLICES = (
    leverage_runtime.MAX_TRAIN_SLICE_COUNT
)
_PINNED_LEVERAGE_PROFILE_BINDINGS = tuple(
    (
        profile_id,
        json.dumps(
            _PINNED_REQUIRE_LEVERAGE_PROFILE(profile_id),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii"),
        _PINNED_REQUIRE_LEVERAGE_PROFILE(profile_id)["profile_sha256"],
        tuple(
            sorted(
                (
                    *_PINNED_LEVERAGE_RESULT_NAMES_CALLABLE(profile_id),
                    "ARV2_RUNTIME_META",
                )
            )
        ),
    )
    for profile_id in _PINNED_LEVERAGE_PROFILE_IDS
)
_PINNED_PROJECTION_SIX_UNIVERSE_SOURCE_PATHS = tuple(
    projection_builder.SIX_UNIVERSE_PROJECT_SOURCE_PATHS
)
_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_IDS = tuple(
    projection_builder.SIX_UNIVERSE_PROFILE_IDS
)
_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256S_OBJECT = (
    projection_builder.SIX_UNIVERSE_PROFILE_SHA256S
)
_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256_ROWS = tuple(
    sorted(_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256S_OBJECT.items())
)
_PINNED_REQUIRE_SIX_UNIVERSE_PROFILE = six_universe_evaluator.require_profile
_PINNED_SIX_UNIVERSE_RESULT_NAMES_CALLABLE = (
    six_universe_evaluator.expected_custom_summary_statistic_names
)
_PINNED_SIX_UNIVERSE_PROFILE_IDS = tuple(six_universe_evaluator.PROFILE_IDS)
_PINNED_SIX_UNIVERSE_PROFILE_BINDINGS = tuple(
    (
        profile_id,
        json.dumps(
            _PINNED_REQUIRE_SIX_UNIVERSE_PROFILE(profile_id).to_record(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii"),
        _PINNED_REQUIRE_SIX_UNIVERSE_PROFILE(profile_id).profile_sha256,
        tuple(
            sorted(
                (
                    *_PINNED_SIX_UNIVERSE_RESULT_NAMES_CALLABLE(profile_id),
                    six_universe_runtime.RUNTIME_META_STATISTIC_NAME,
                )
            )
        ),
    )
    for profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS
)
_PINNED_SIX_UNIVERSE_PROFILE_SCHEMA = six_universe_evaluator.PROFILE_SCHEMA
_PINNED_SIX_UNIVERSE_SUMMARY_SCHEMA = six_universe_evaluator.SUMMARY_SCHEMA
_PINNED_SIX_UNIVERSE_ACCOUNT_SCHEMA = six_universe_evaluator.ACCOUNT_SCHEMA
_PINNED_SIX_UNIVERSE_SLEEVE_SCHEMA = six_universe_evaluator.SLEEVE_SCHEMA
_PINNED_SIX_UNIVERSE_SERIES_SCHEMA = six_universe_evaluator.SERIES_SCHEMA
_PINNED_SIX_UNIVERSE_STATISTIC_NAMES = (
    six_universe_evaluator.META_STATISTIC_NAME,
    six_universe_evaluator.SIGNAL_STATISTIC_NAME,
    six_universe_evaluator.MATCHED_STATISTIC_NAME,
    six_universe_evaluator.ETF_BASKET_STATISTIC_NAME,
    six_universe_evaluator.SLEEVES_STATISTIC_NAME,
    six_universe_evaluator.SERIES_STATISTIC_NAME,
    six_universe_runtime.RUNTIME_META_STATISTIC_NAME,
)
_PINNED_SIX_UNIVERSE_DECISION_START = (
    six_universe_evaluator.DECISION_START_SESSION
)
_PINNED_SIX_UNIVERSE_EVALUATION_END = (
    six_universe_evaluator.EVALUATION_END_SESSION
)
_PINNED_SIX_UNIVERSE_EXPECTED_SESSIONS = (
    six_universe_evaluator.EXPECTED_SESSION_COUNT
)
_PINNED_SIX_UNIVERSE_EXPECTED_RETURNS = (
    six_universe_evaluator.EXPECTED_RETURN_SESSION_COUNT
)
_PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS = (
    six_universe_evaluator.EXPECTED_DECISION_SESSION_COUNT
)
_PINNED_SIX_UNIVERSE_PRIMARY_COST = (
    six_universe_evaluator.PRIMARY_COST_BPS_PER_SIDE
)
_PINNED_SIX_UNIVERSE_MODELED_COST_RATE = (
    six_universe_evaluator.MODELED_COST_RATE_PER_SIDE
)
_PINNED_SIX_UNIVERSE_ANNUALIZATION_SESSIONS = (
    six_universe_evaluator.ANNUALIZATION_SESSIONS
)
_PINNED_SIX_UNIVERSE_GATE_SCORE_QUANTUM = (
    six_universe_evaluator.GATE_SCORE_QUANTUM
)
_PINNED_SIX_UNIVERSE_MINIMUM_INVESTED_RETURNS = (
    six_universe_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS
)
_PINNED_SIX_UNIVERSE_TARGET_GROSS = six_universe_gate.TARGET_GROSS_EXPOSURE
_PINNED_SIX_UNIVERSE_IDS = tuple(six_universe_gate.UNIVERSE_IDS)
_PINNED_SIX_UNIVERSE_SOURCE_VIEW = six_universe_gate.SOURCE_VIEW_ID
_PINNED_SIX_UNIVERSE_RUNTIME_MAX_TRAIN_SLICES = (
    six_universe_runtime.MAXIMUM_TRAIN_SLICE_COUNT
)
_PINNED_SIX_UNIVERSE_RUNTIME_WORK_UNITS = (
    six_universe_runtime.TRAIN_WORK_UNITS_PER_SLICE
)
_PINNED_SIX_UNIVERSE_RUNTIME_HISTORY_CHUNK_DECISIONS = (
    six_universe_runtime.HISTORY_CHUNK_DECISION_COUNT
)
_PINNED_SIX_UNIVERSE_RUNTIME_MAX_SOURCE_ROWS = (
    six_universe_runtime.MAXIMUM_TOTAL_SOURCE_ROWS
)
_PINNED_JSON_DUMPS = json.dumps
_PINNED_REQUIRE_EXECUTION_SIGNATURE = require_formal_execution_owner_signature
_PINNED_REQUIRE_RESULT_SIGNATURE = require_formal_result_read_owner_signature
_PINNED_LOAD_INFRASTRUCTURE_LEDGER = preregistration.load_infrastructure_look_ledger
_PINNED_REQUIRE_INFRASTRUCTURE_LEDGER = (
    preregistration.require_infrastructure_look_ledger
)
_PINNED_INFRASTRUCTURE_LEDGER = _PINNED_REQUIRE_INFRASTRUCTURE_LEDGER(
    _PINNED_LOAD_INFRASTRUCTURE_LEDGER()
)
_PINNED_REQUIRE_TRANSPORT = formal._require_concrete_transport
_PINNED_TRANSPORT_CALL = formal._transport_call
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
_PINNED_BACKTEST_STATUS_KEYS = formal._BACKTEST_STATUS_KEYS
_PINNED_DISCARDED_BACKTEST_KEYS = formal._DISCARDED_BACKTEST_SUMMARY_KEYS
_PINNED_COMPILE_TERMINAL_STATES = formal.COMPILE_TERMINAL_STATES
_PINNED_BACKTEST_TERMINAL_STATES = formal.BACKTEST_TERMINAL_STATUSES
_PINNED_LEXISTS = os.path.lexists
_PINNED_SCANDIR = os.scandir

EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/set_package_objects_activation_last",
    "object/properties_verify_exact_key_size_md5",
    "files/read_exact_inventory",
    "files/delete_only_exact_default_research_ipynb",
    "files/create_or_update_exact_profile_bound_projection",
    "files/readback_exact_profile_bound_source_bytes",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "persist_authenticated_pre_create_control",
    "backtests/create_once",
    "recover_unique_named_run_statistics_free_once_if_create_is_ambiguous",
    "backtests/list_identity_status_includeStatistics_false",
)
RESULT_ACTIONS = (
    "backtests/read_once",
    "select_exact_expected_ARV2_custom_summary_keys_only",
    "persist_exact_validated_aggregate_custom_statistics_only",
)


@dataclasses.dataclass(frozen=True, slots=True)
class _EvaluationRunSpec:
    profile_id: str | None
    evaluation_id: str
    ledger_entry_id: str
    run_level_looks_before: int
    run_level_looks_after: int
    development_evaluations_before: int
    development_evaluations_after: int
    cell_count: int
    lifetime_alpha_cell_floor_before: int
    lifetime_alpha_cell_floor_after: int


def _stock_portfolio_profile_binding(
    profile_id: str,
) -> tuple[bytes, str, tuple[str, ...]]:
    for (
        candidate_profile_id,
        profile_bytes,
        profile_sha256,
        result_names,
    ) in _PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS:
        if candidate_profile_id == profile_id:
            return profile_bytes, profile_sha256, result_names
    _error("stock portfolio profile is not allowlisted")


def _market_cap_profile_binding(
    profile_id: str,
) -> tuple[bytes, str, tuple[str, ...]]:
    for (
        candidate_profile_id,
        profile_bytes,
        profile_sha256,
        result_names,
    ) in _PINNED_MARKET_CAP_PROFILE_BINDINGS:
        if candidate_profile_id == profile_id:
            return profile_bytes, profile_sha256, result_names
    _error("market-cap stock portfolio profile is not allowlisted")


def _leverage_profile_binding(
    profile_id: str,
) -> tuple[bytes, str, tuple[str, ...]]:
    for (
        candidate_profile_id,
        profile_bytes,
        profile_sha256,
        result_names,
    ) in _PINNED_LEVERAGE_PROFILE_BINDINGS:
        if candidate_profile_id == profile_id:
            return profile_bytes, profile_sha256, result_names
    _error("objective leverage profile is not allowlisted")


def _six_universe_profile_binding(
    profile_id: str,
) -> tuple[bytes, str, tuple[str, ...]]:
    for (
        candidate_profile_id,
        profile_bytes,
        profile_sha256,
        result_names,
    ) in _PINNED_SIX_UNIVERSE_PROFILE_BINDINGS:
        if candidate_profile_id == profile_id:
            return profile_bytes, profile_sha256, result_names
    _error("six-universe profile is not allowlisted")


# The R-058/R-059 baselines are conditional ledger successors.  The host
# orchestrator creates either plan only after authenticating the preceding
# aggregate receipt; this adapter binds one selected run and does not claim to
# authenticate a predecessor receipt that it is not given.
_EVALUATION_RUN_SPECS = (
    _EvaluationRunSpec(
        None,
        "arv2-eval-stock-historical-qc-001",
        "R-055",
        55,
        56,
        2,
        3,
        32,
        484,
        516,
    ),
    _EvaluationRunSpec(
        "arv2-stock-ic-2019-2023",
        "arv2-eval-stock-historical-qc-002",
        "R-057",
        56,
        57,
        3,
        4,
        16,
        516,
        532,
    ),
    _EvaluationRunSpec(
        "arv2-stock-ic-2023-2025",
        "arv2-eval-stock-historical-qc-003",
        "R-058",
        57,
        58,
        4,
        5,
        16,
        532,
        548,
    ),
    _EvaluationRunSpec(
        "arv2-stock-ic-2013-2019",
        "arv2-eval-stock-historical-qc-004",
        "R-059",
        58,
        59,
        5,
        6,
        16,
        548,
        564,
    ),
    _EvaluationRunSpec(
        etf_evaluator.PROFILE_ID,
        "arv2-eval-etf-sector-baseline-qc-002",
        "R-061",
        60,
        61,
        7,
        8,
        7,
        564,
        571,
    ),
    _EvaluationRunSpec(
        _PINNED_STOCK_PORTFOLIO_PROFILE_ID,
        "arv2-eval-stock-portfolio-historical-qc-004",
        "R-065",
        64,
        65,
        11,
        12,
        4,
        575,
        579,
    ),
    _EvaluationRunSpec(
        stock_portfolio_evaluator.SP500_PROFILE_ID,
        "arv2-eval-stock-spy-holdings-intersection-qc-011",
        "R-072",
        69,
        70,
        16,
        17,
        4,
        579,
        583,
    ),
    _EvaluationRunSpec(
        stock_portfolio_evaluator.NASDAQ100_MEMBERSHIP_ONLY_PROFILE_ID,
        "arv2-eval-stock-qqq-holdings-intersection-qc-016",
        "R-077",
        72,
        73,
        19,
        20,
        4,
        583,
        587,
    ),
    _EvaluationRunSpec(
        stock_portfolio_evaluator.UNION_MEMBERSHIP_ONLY_PROFILE_ID,
        "arv2-eval-stock-spy-qqq-intersection-union-qc-017",
        "R-078",
        73,
        74,
        20,
        21,
        4,
        587,
        591,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2021_2025_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2021-2025-qc-018",
        "R-083",
        78,
        79,
        21,
        22,
        4,
        591,
        595,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2021_2025_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2021-2025-qc-019",
        "R-084",
        79,
        80,
        22,
        23,
        4,
        595,
        599,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2019_2023_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2019-2023-qc-020",
        "R-085",
        80,
        81,
        23,
        24,
        4,
        599,
        603,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2019_2023_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2019-2023-qc-021",
        "R-086",
        81,
        82,
        24,
        25,
        4,
        603,
        607,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2023_2025_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2023-2025-qc-022",
        "R-087",
        82,
        83,
        25,
        26,
        4,
        607,
        611,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2023_2025_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2023-2025-qc-023",
        "R-088",
        83,
        84,
        26,
        27,
        4,
        611,
        615,
    ),
    _EvaluationRunSpec(
        leverage_evaluator.QQQ_2021_2025_PROFILE_ID,
        "arv2-eval-objective-synthetic-leverage-qqq-2021-2025-qc-024",
        "R-089",
        84,
        85,
        27,
        28,
        4,
        615,
        619,
    ),
    _EvaluationRunSpec(
        leverage_evaluator.SPY_2021_2025_PROFILE_ID,
        "arv2-eval-objective-synthetic-leverage-spy-2021-2025-qc-025",
        "R-090",
        85,
        86,
        28,
        29,
        4,
        619,
        623,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2021_2025_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2021-2025-qc-042",
        "R-107",
        81,
        82,
        24,
        25,
        4,
        591,
        595,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2021_2025_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2021-2025-qc-043",
        "R-108",
        82,
        83,
        25,
        26,
        4,
        595,
        599,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2019_2023_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2019-2023-qc-044",
        "R-109",
        83,
        84,
        26,
        27,
        4,
        599,
        603,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2019_2023_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2019-2023-qc-045",
        "R-110",
        84,
        85,
        27,
        28,
        4,
        603,
        607,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2023_2025_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-qqq-2023-2025-qc-046",
        "R-111",
        85,
        86,
        28,
        29,
        4,
        607,
        611,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2023_2025_V2_PROFILE_ID,
        "arv2-eval-market-cap-stock-spy-2023-2025-qc-047",
        "R-112",
        86,
        87,
        29,
        30,
        4,
        611,
        615,
    ),
    _EvaluationRunSpec(
        leverage_evaluator.QQQ_2021_2025_V3_PROFILE_ID,
        "arv2-eval-objective-synthetic-leverage-qqq-2021-2025-qc-048",
        "R-113",
        87,
        88,
        30,
        31,
        4,
        615,
        619,
    ),
    _EvaluationRunSpec(
        leverage_evaluator.SPY_2021_2025_V3_PROFILE_ID,
        "arv2-eval-objective-synthetic-leverage-spy-2021-2025-qc-049",
        "R-114",
        88,
        89,
        31,
        32,
        4,
        619,
        623,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2021_2025_V3_PROFILE_ID,
        "arv2-eval-bounded-tilt-stock-qqq-2021-2025-qc-050",
        "R-115",
        83,
        84,
        26,
        27,
        4,
        599,
        603,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2021_2025_V3_PROFILE_ID,
        "arv2-eval-bounded-tilt-stock-spy-2021-2025-qc-051",
        "R-116",
        84,
        85,
        27,
        28,
        4,
        603,
        607,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.QQQ_2021_2025_V4_PROFILE_ID,
        "arv2-eval-bounded-tilt-stock-qqq-2021-2025-qc-052",
        "R-117",
        84,
        85,
        27,
        28,
        4,
        599,
        603,
    ),
    _EvaluationRunSpec(
        market_cap_evaluator.SPY_2021_2025_V4_PROFILE_ID,
        "arv2-eval-bounded-tilt-stock-spy-2021-2025-qc-053",
        "R-118",
        85,
        86,
        28,
        29,
        4,
        603,
        607,
    ),
    _EvaluationRunSpec(
        six_universe_evaluator.TOP10_PRIMARY_PROFILE.profile_id,
        "arv2-eval-six-universe-gate-top10-2021-2025-qc-056",
        "R-121",
        88,
        89,
        31,
        32,
        3,
        609,
        612,
    ),
    _EvaluationRunSpec(
        six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id,
        "arv2-eval-six-universe-gate-top5-2021-2025-qc-057",
        "R-122",
        89,
        90,
        32,
        33,
        3,
        612,
        615,
    ),
)

_SUPERSEDED_UNSPENT_PROFILE_IDS = (
    _PINNED_PROJECTION_SUPERSEDED_UNSPENT_PROFILE_IDS
)


def _require_fresh_launch_profile(plan):
    profile_id = plan.projection.evaluation_profile_id
    if profile_id in _SUPERSEDED_UNSPENT_PROFILE_IDS:
        _error("preliminary evaluation profile is superseded and cannot launch")
    return plan


def _run_spec(evaluation_profile_id: str | None) -> _EvaluationRunSpec:
    if evaluation_profile_id is not None and type(evaluation_profile_id) is not str:
        _error("preliminary evaluation profile is not allowlisted")
    for spec in _EVALUATION_RUN_SPECS:
        if spec.profile_id == evaluation_profile_id:
            if evaluation_profile_id == etf_evaluator.PROFILE_ID:
                etf_evaluator.require_etf_baseline_profile(
                    evaluation_profile_id
                )
            elif evaluation_profile_id in _PINNED_STOCK_PORTFOLIO_PROFILE_IDS:
                if not _stock_portfolio_contract_bindings_are_current():
                    _error("stock portfolio financial contract changed")
            elif evaluation_profile_id in _PINNED_MARKET_CAP_ALL_PROFILE_IDS:
                if not _market_cap_contract_bindings_are_current():
                    _error("market-cap stock portfolio financial contract changed")
            elif evaluation_profile_id in _PINNED_LEVERAGE_PROFILE_IDS:
                if (
                    evaluation_profile_id
                    not in _SUPERSEDED_UNSPENT_PROFILE_IDS
                    and not _leverage_contract_bindings_are_current()
                ):
                    _error("objective leverage financial contract changed")
            elif evaluation_profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS:
                if not _six_universe_contract_bindings_are_current():
                    _error("six-universe financial contract changed")
            elif evaluation_profile_id is not None:
                _PINNED_REQUIRE_REGIME_PROFILE(evaluation_profile_id)
            return spec
    _error("preliminary evaluation profile is not allowlisted")


def _expected_result_names(evaluation_profile_id: str | None) -> tuple[str, ...]:
    spec = _run_spec(evaluation_profile_id)
    if evaluation_profile_id is None:
        names = _PINNED_EXPECTED_RESULT_NAMES
    elif evaluation_profile_id == etf_evaluator.PROFILE_ID:
        names = tuple(
            etf_runtime.expected_custom_summary_statistic_names(
                evaluation_profile_id
            )
        )
    elif evaluation_profile_id in _PINNED_STOCK_PORTFOLIO_PROFILE_IDS:
        _profile_bytes, _profile_sha256, names = (
            _stock_portfolio_profile_binding(evaluation_profile_id)
        )
    elif evaluation_profile_id in _PINNED_MARKET_CAP_ALL_PROFILE_IDS:
        _profile_bytes, _profile_sha256, names = (
            _market_cap_profile_binding(evaluation_profile_id)
        )
    elif evaluation_profile_id in _PINNED_LEVERAGE_PROFILE_IDS:
        _profile_bytes, _profile_sha256, names = (
            _leverage_profile_binding(evaluation_profile_id)
        )
    elif evaluation_profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS:
        _profile_bytes, _profile_sha256, names = (
            _six_universe_profile_binding(evaluation_profile_id)
        )
    else:
        names = tuple(
            _PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE(evaluation_profile_id)
        )
    split_account_profiles = (
        _PINNED_MARKET_CAP_ALL_PROFILE_IDS + _PINNED_LEVERAGE_PROFILE_IDS
    )
    if evaluation_profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS:
        non_cell_statistic_count = 4
    elif evaluation_profile_id in split_account_profiles:
        non_cell_statistic_count = (
            5
            if evaluation_profile_id in _PINNED_MARKET_CAP_TILT_PROFILE_IDS
            else 4
        )
    else:
        non_cell_statistic_count = 2
    if (
        type(names) is not tuple
        or len(names) != spec.cell_count + non_cell_statistic_count
        or names != tuple(sorted(names))
        or len(set(names)) != len(names)
        or (
            (
                six_universe_runtime.RUNTIME_META_STATISTIC_NAME
                if evaluation_profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS
                else "ARV2_RUNTIME_META"
            )
            not in names
        )
    ):
        _error("preliminary expected result inventory changed")
    return names


def _look_accounting(
    *,
    stage: str = "reservation",
    evaluation_profile_id: str | None = None,
) -> dict[str, object]:
    """Return prospective, launched, or authenticated-result look accounting."""
    if stage not in {"reservation", "launch", "result"}:
        _error("preliminary look-accounting stage changed")
    launched = stage in {"launch", "result"}
    aggregate_authenticated = stage == "result"
    spec = _run_spec(evaluation_profile_id)
    binding = _PINNED_REQUIRE_INFRASTRUCTURE_LEDGER(
        _PINNED_INFRASTRUCTURE_LEDGER
    )
    try:
        infrastructure_ledger = json.loads(binding.payload.decode("ascii"))
        append_only_contract = infrastructure_ledger[
            "append_only_contract"
        ]
        infrastructure_entries = infrastructure_ledger["entries"]
        infrastructure_totals = infrastructure_ledger["totals"]
        infrastructure_look_count = infrastructure_totals[
            "infrastructure_research_looks_spent"
        ]
        ledger_entry_count = append_only_contract["entry_count"]
    except (
        AttributeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ):
        _error("authenticated infrastructure-look accounting changed")
    if (
        type(infrastructure_ledger) is not dict
        or type(append_only_contract) is not dict
        or type(infrastructure_entries) is not list
        or type(infrastructure_totals) is not dict
        or type(infrastructure_look_count) is not int
        or type(ledger_entry_count) is not int
        or infrastructure_look_count < 0
        or infrastructure_look_count != ledger_entry_count
        or infrastructure_look_count != len(infrastructure_entries)
    ):
        _error("authenticated infrastructure-look accounting changed")
    return {
        "schema": "arv2-qc-research-look-accounting-v1",
        "classification": "development_evaluation",
        "evaluation_id": spec.evaluation_id,
        "shared_look_ledger_entry_id": spec.ledger_entry_id,
        "accounting_stage": stage,
        "run_level_looks_before": spec.run_level_looks_before,
        "run_level_looks_after": (
            spec.run_level_looks_after
            if launched
            else spec.run_level_looks_before
        ),
        "planned_run_level_looks_after_launch": spec.run_level_looks_after,
        "arv2_development_evaluations_before": (
            spec.development_evaluations_before
        ),
        "arv2_development_evaluations_after": (
            spec.development_evaluations_after
            if launched
            else spec.development_evaluations_before
        ),
        "planned_arv2_development_evaluations_after_launch": (
            spec.development_evaluations_after
        ),
        "planned_maximum_preliminary_ic_cell_count": spec.cell_count,
        "emitted_preliminary_ic_cell_count": (
            spec.cell_count if aggregate_authenticated else 0
        ),
        "lifetime_alpha_cell_floor_before": (
            spec.lifetime_alpha_cell_floor_before
        ),
        "lifetime_alpha_cell_floor_after": (
            spec.lifetime_alpha_cell_floor_after
            if aggregate_authenticated
            else spec.lifetime_alpha_cell_floor_before
        ),
        "aggregate_result_authenticated": aggregate_authenticated,
        "infrastructure_looks_before": infrastructure_look_count,
        "infrastructure_looks_after": infrastructure_look_count,
        "authenticated_infrastructure_look_count": infrastructure_look_count,
        "infrastructure_look_ledger_id": binding.ledger_id,
        "infrastructure_look_ledger_hash": binding.ledger_hash,
        "infrastructure_look_ledger_artifact_sha256": binding.artifact_sha256,
        "permanent_looks_before": 0,
        "permanent_looks_after": 0,
        "confirmatory_looks_before": 0,
        "confirmatory_looks_after": 0,
        "confirmatory_look_spent": False,
        "execution_permit_alone_consumes_look": False,
        "pre_create_control_marks_launch_ambiguity_and_consumes_look": True,
        "backtest_create_attempt_consumes_look_on_success_failure_or_ambiguity": True,
        "technical_corrected_rerun_requires_new_ledger_entry": True,
        "retry_may_overwrite_shared_ledger_entry": False,
    }


def _error(message: str) -> NoReturn:
    raise AcceptedRiskPreliminarySubmissionError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary submission value is not canonical ASCII JSON"
        ) from exc


def _stock_portfolio_contract_bindings_are_current() -> bool:
    """Refuse in-memory weakening of any exact active stock contract."""

    namespace = stock_portfolio_evaluator.__dict__
    if type(namespace) is not dict:
        return False

    def exact_json_tree(value: object) -> bool:
        if type(value) in (str, int, bool) or value is None:
            return True
        if type(value) is list:
            return all(exact_json_tree(item) for item in value)
        if type(value) is dict:
            return all(
                type(key) is str and exact_json_tree(item)
                for key, item in value.items()
            )
        return False

    scalar_bindings = (
        (stock_portfolio_evaluator.PROFILE_ID, _PINNED_STOCK_PORTFOLIO_PROFILE_ID, str),
        (stock_portfolio_evaluator.CONTRACT_ID, _PINNED_STOCK_PORTFOLIO_CONTRACT_ID, str),
        (stock_portfolio_evaluator.SUMMARY_SCHEMA, _PINNED_STOCK_PORTFOLIO_SUMMARY_SCHEMA, str),
        (stock_portfolio_evaluator.PORTFOLIO_CELL_SCHEMA, _PINNED_STOCK_PORTFOLIO_CELL_SCHEMA, str),
        (
            stock_portfolio_evaluator.EXPECTED_DECISION_SESSION_COUNT,
            _PINNED_STOCK_PORTFOLIO_EXPECTED_DECISIONS,
            int,
        ),
        (
            stock_portfolio_evaluator.EXPECTED_RETURN_SESSION_COUNT,
            _PINNED_STOCK_PORTFOLIO_EXPECTED_RETURNS,
            int,
        ),
        (
            stock_portfolio_evaluator.MAXIMUM_HOLDINGS,
            _PINNED_STOCK_PORTFOLIO_MAXIMUM_HOLDINGS,
            int,
        ),
        (
            stock_portfolio_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS,
            _PINNED_STOCK_PORTFOLIO_MINIMUM_INVESTED_RETURNS,
            int,
        ),
        (
            stock_portfolio_evaluator.PRIMARY_COST_BPS,
            _PINNED_STOCK_PORTFOLIO_PRIMARY_COST,
            int,
        ),
    )
    if any(type(observed) is not expected_type or observed != expected for (
        observed, expected, expected_type
    ) in scalar_bindings):
        return False
    costs = stock_portfolio_evaluator.COST_BPS_SCENARIOS
    if (
        type(costs) is not tuple
        or any(type(item) is not int for item in costs)
        or costs != _PINNED_STOCK_PORTFOLIO_COSTS
    ):
        return False
    annualization_sessions = stock_portfolio_evaluator.ANNUALIZATION_SESSIONS
    if (
        type(annualization_sessions) is not Decimal
        or annualization_sessions
        != _PINNED_STOCK_PORTFOLIO_ANNUALIZATION_SESSIONS
        or annualization_sessions != Decimal("252")
    ):
        return False
    stock_source_paths = projection_builder.STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS
    if (
        type(stock_source_paths) is not tuple
        or any(type(item) is not str for item in stock_source_paths)
        or stock_source_paths != _PINNED_PROJECTION_STOCK_SOURCE_PATHS
    ):
        return False
    try:
        profile = namespace.get("_PROFILE")
        profile_ids = namespace.get("PROFILE_IDS")
        variant_profile_ids = namespace.get("VARIANT_PROFILE_IDS")
        universe_profile_ids = namespace.get("UNIVERSE_PROFILE_IDS")
        projection_profile_ids = projection_builder.STOCK_PORTFOLIO_PROFILE_IDS
        projection_universe_profile_ids = (
            projection_builder.STOCK_UNIVERSE_PROFILE_IDS
        )
        projection_hashes = (
            projection_builder.STOCK_PORTFOLIO_PROFILE_SHA256S
        )
        if (
            namespace.get("require_stock_portfolio_profile")
            is not _PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE
            or namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_STOCK_PORTFOLIO_RESULT_NAMES_CALLABLE
            or namespace.get("constituent_etf_tickers_for_profile")
            is not _PINNED_STOCK_PORTFOLIO_CONSTITUENT_TICKERS_CALLABLE
            or namespace.get(
                "constituent_snapshot_maximum_age_calendar_days_for_profile"
            )
            is not _PINNED_STOCK_PORTFOLIO_SNAPSHOT_MAXIMUM_AGE_CALLABLE
            or namespace.get("constituent_positive_count_bounds_for_profile")
            is not _PINNED_STOCK_PORTFOLIO_POSITIVE_COUNT_BOUNDS_CALLABLE
            or projection_builder._profile
            is not _PINNED_PROJECTION_PROFILE_CALLABLE
            or projection_builder.project_source_paths_for_profile
            is not _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE
            or preliminary_runtime.expected_custom_summary_statistic_names
            is not _PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE
            or type(preliminary_runtime.STOCK_PORTFOLIO_PROFILE_ID) is not str
            or preliminary_runtime.STOCK_PORTFOLIO_PROFILE_ID
            != _PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_ID
            or preliminary_runtime.STOCK_PORTFOLIO_PROFILE_ID
            != _PINNED_STOCK_PORTFOLIO_PROFILE_ID
            or type(preliminary_runtime.STOCK_PORTFOLIO_PROFILE_IDS)
            is not tuple
            or preliminary_runtime.STOCK_PORTFOLIO_PROFILE_IDS
            != _PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_IDS
            or preliminary_runtime.STOCK_PORTFOLIO_PROFILE_IDS != profile_ids
            or type(preliminary_runtime.STOCK_UNIVERSE_PROFILE_IDS)
            is not tuple
            or preliminary_runtime.STOCK_UNIVERSE_PROFILE_IDS
            != _PINNED_RUNTIME_STOCK_UNIVERSE_PROFILE_IDS
            or preliminary_runtime.STOCK_UNIVERSE_PROFILE_IDS
            != universe_profile_ids
            or type(
                preliminary_runtime.STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            )
            is not tuple
            or preliminary_runtime.STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            != _PINNED_RUNTIME_STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            or preliminary_runtime.STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            != _PINNED_STOCK_PORTFOLIO_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            or type(preliminary_runtime.STOCK_MEMBERSHIP_ONLY_PROFILE_IDS)
            is not tuple
            or preliminary_runtime.STOCK_MEMBERSHIP_ONLY_PROFILE_IDS
            != _PINNED_RUNTIME_STOCK_MEMBERSHIP_ONLY_PROFILE_IDS
            or preliminary_runtime.STOCK_MEMBERSHIP_ONLY_PROFILE_IDS
            != _PINNED_STOCK_PORTFOLIO_MEMBERSHIP_ONLY_PROFILE_IDS
            or type(profile_ids) is not tuple
            or profile_ids != _PINNED_STOCK_PORTFOLIO_PROFILE_IDS
            or namespace.get("ALL_PROFILE_IDS") != profile_ids
            or type(variant_profile_ids) is not tuple
            or variant_profile_ids
            != _PINNED_STOCK_PORTFOLIO_VARIANT_PROFILE_IDS
            or type(universe_profile_ids) is not tuple
            or universe_profile_ids
            != _PINNED_STOCK_PORTFOLIO_UNIVERSE_PROFILE_IDS
            or namespace.get("STATE_UNTIL_SUPERSEDED_PROFILE_IDS")
            != _PINNED_STOCK_PORTFOLIO_STATE_UNTIL_SUPERSEDED_PROFILE_IDS
            or namespace.get("MEMBERSHIP_ONLY_PROFILE_IDS")
            != _PINNED_STOCK_PORTFOLIO_MEMBERSHIP_ONLY_PROFILE_IDS
            or variant_profile_ids != profile_ids[1:]
            or universe_profile_ids != variant_profile_ids
            or (
                namespace.get("SP500_PROFILE_ID"),
                namespace.get("NASDAQ100_PROFILE_ID"),
                namespace.get("UNION_PROFILE_ID"),
                namespace.get(
                    "NASDAQ100_STATE_UNTIL_SUPERSEDED_PROFILE_ID"
                ),
                namespace.get("UNION_STATE_UNTIL_SUPERSEDED_PROFILE_ID"),
                namespace.get("NASDAQ100_MEMBERSHIP_ONLY_PROFILE_ID"),
                namespace.get("UNION_MEMBERSHIP_ONLY_PROFILE_ID"),
            )
            != variant_profile_ids
            or any(type(item) is not str for item in profile_ids)
            or len(set(profile_ids)) != 8
            or namespace.get("_PROFILE_CANONICAL_ROWS")
            is not _PINNED_STOCK_PORTFOLIO_CANONICAL_ROWS_OBJECT
            or type(projection_profile_ids) is not tuple
            or projection_profile_ids
            != _PINNED_PROJECTION_STOCK_PROFILE_IDS
            or projection_profile_ids != profile_ids
            or type(projection_universe_profile_ids) is not tuple
            or projection_universe_profile_ids
            != _PINNED_PROJECTION_STOCK_UNIVERSE_PROFILE_IDS
            or projection_universe_profile_ids != universe_profile_ids
            or type(projection_hashes) is not dict
            or projection_hashes
            is not _PINNED_PROJECTION_STOCK_PROFILE_SHA256S_OBJECT
            or tuple(sorted(projection_hashes.items()))
            != _PINNED_PROJECTION_STOCK_PROFILE_SHA256_ROWS
            or type(projection_builder.STOCK_PORTFOLIO_PROFILE_ID) is not str
            or projection_builder.STOCK_PORTFOLIO_PROFILE_ID
            != _PINNED_STOCK_PORTFOLIO_PROFILE_ID
            or type(projection_builder.STOCK_PORTFOLIO_PROFILE_SHA256) is not str
            or projection_builder.STOCK_PORTFOLIO_PROFILE_SHA256
            != _PINNED_STOCK_PORTFOLIO_PROFILE_SHA256
            or profile is not _PINNED_STOCK_PORTFOLIO_PROFILE_OBJECT
            or not exact_json_tree(profile)
            or _PINNED_JSON_DUMPS(
                profile,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
            != _PINNED_STOCK_PORTFOLIO_PROFILE_BYTES
        ):
            return False
        for (
            profile_id,
            expected_profile_bytes,
            expected_profile_sha256,
            expected_result_names,
        ) in _PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS:
            observed_profile = _PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE(
                profile_id
            )
            observed_result_names = tuple(
                sorted(
                    (
                        *_PINNED_STOCK_PORTFOLIO_RESULT_NAMES_CALLABLE(
                            profile_id
                        ),
                        "ARV2_RUNTIME_META",
                    )
                )
            )
            observed_projection_profile = (
                _PINNED_PROJECTION_PROFILE_CALLABLE(profile_id)
            )
            observed_runtime_result_names = (
                _PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE(profile_id)
            )
            observed_source_paths = (
                _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE(profile_id)
            )
            expected_tickers = tuple(
                observed_profile.get("constituent_etf_tickers", ())
            )
            if (
                not exact_json_tree(observed_profile)
                or _PINNED_JSON_DUMPS(
                    observed_profile,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("ascii")
                != expected_profile_bytes
                or observed_profile.get("profile_id") != profile_id
                or observed_profile.get("profile_sha256")
                != expected_profile_sha256
                or projection_hashes.get(profile_id)
                != expected_profile_sha256
                or observed_projection_profile
                != {
                    "profile_id": profile_id,
                    "profile_sha256": expected_profile_sha256,
                }
                or type(observed_source_paths) is not tuple
                or observed_source_paths
                != _PINNED_PROJECTION_STOCK_SOURCE_PATHS
                or observed_result_names != expected_result_names
                or observed_runtime_result_names != expected_result_names
                or _PINNED_STOCK_PORTFOLIO_CONSTITUENT_TICKERS_CALLABLE(
                    profile_id
                )
                != expected_tickers
                or (profile_id == _PINNED_STOCK_PORTFOLIO_PROFILE_ID)
                is not (expected_tickers == ())
            ):
                return False
        return True
    except (Exception, RecursionError):
        return False


def _market_cap_contract_bindings_are_current() -> bool:
    """Refuse weakening of active tilt or preserved market-cap contracts."""

    namespace = market_cap_evaluator.__dict__
    runtime_namespace = market_cap_runtime.__dict__
    if type(namespace) is not dict or type(runtime_namespace) is not dict:
        return False
    scalar_bindings = (
        (market_cap_evaluator.CONTRACT_ID, _PINNED_MARKET_CAP_CONTRACT_ID, str),
        (market_cap_evaluator.SUMMARY_SCHEMA, _PINNED_MARKET_CAP_SUMMARY_SCHEMA, str),
        (market_cap_evaluator.PORTFOLIO_CELL_SCHEMA, _PINNED_MARKET_CAP_CELL_SCHEMA, str),
        (
            market_cap_evaluator.META_STATISTIC_NAME,
            _PINNED_MARKET_CAP_META_STATISTIC_NAME,
            str,
        ),
        (
            market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME,
            _PINNED_MARKET_CAP_SELECTED_AGGREGATES_STATISTIC_NAME,
            str,
        ),
        (
            market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME,
            _PINNED_MARKET_CAP_MATCHED_AGGREGATES_STATISTIC_NAME,
            str,
        ),
        (
            market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME,
            _PINNED_MARKET_CAP_TILT_AGGREGATES_STATISTIC_NAME,
            str,
        ),
        (
            market_cap_evaluator.TILT_AGGREGATES_SCHEMA,
            _PINNED_MARKET_CAP_TILT_AGGREGATES_SCHEMA,
            str,
        ),
        (market_cap_evaluator.MAXIMUM_HOLDINGS, _PINNED_MARKET_CAP_MAXIMUM_HOLDINGS, int),
        (
            market_cap_evaluator.MINIMUM_TILT_RANKED_NAME_COUNT,
            _PINNED_MARKET_CAP_MINIMUM_TILT_RANKED_NAMES,
            int,
        ),
        (
            market_cap_evaluator.MINIMUM_TILT_POSITIVE_SCORE_COUNT,
            _PINNED_MARKET_CAP_MINIMUM_TILT_POSITIVE_SCORES,
            int,
        ),
        (
            market_cap_evaluator.MINIMUM_TILT_NEGATIVE_SCORE_COUNT,
            _PINNED_MARKET_CAP_MINIMUM_TILT_NEGATIVE_SCORES,
            int,
        ),
        (
            market_cap_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS,
            _PINNED_MARKET_CAP_MINIMUM_INVESTED_RETURNS,
            int,
        ),
        (market_cap_evaluator.PRIMARY_COST_BPS, _PINNED_MARKET_CAP_PRIMARY_COST, int),
        (
            market_cap_runtime.MAX_TRAIN_SLICE_COUNT,
            _PINNED_MARKET_CAP_RUNTIME_MAX_TRAIN_SLICES,
            int,
        ),
        (
            market_cap_runtime.MAX_HISTORY_CHUNKS,
            _PINNED_MARKET_CAP_RUNTIME_MAX_HISTORY_CHUNKS,
            int,
        ),
        (
            market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT,
            _PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS,
            int,
        ),
        (
            market_cap_runtime.MAX_TOTAL_SOURCE_ROWS,
            _PINNED_MARKET_CAP_RUNTIME_MAX_TOTAL_SOURCE_ROWS,
            int,
        ),
    )
    if any(
        type(observed) is not expected_type or observed != expected
        for observed, expected, expected_type in scalar_bindings
    ):
        return False
    decimal_bindings = (
        (
            market_cap_evaluator.TARGET_GROSS_EXPOSURE,
            _PINNED_MARKET_CAP_TARGET_GROSS,
            Decimal("0.98"),
        ),
        (
            market_cap_evaluator.PORTFOLIO_WEIGHT_QUANTUM,
            _PINNED_MARKET_CAP_PORTFOLIO_WEIGHT_QUANTUM,
            Decimal("1e-48"),
        ),
        (
            market_cap_evaluator.ANNUALIZATION_SESSIONS,
            _PINNED_MARKET_CAP_ANNUALIZATION_SESSIONS,
            Decimal("252"),
        ),
        (
            market_cap_evaluator.MAXIMUM_RELATIVE_TILT,
            _PINNED_MARKET_CAP_MAXIMUM_RELATIVE_TILT,
            Decimal("0.20"),
        ),
        (
            market_cap_evaluator.MAXIMUM_ABSOLUTE_OVERWEIGHT,
            _PINNED_MARKET_CAP_MAXIMUM_ABSOLUTE_OVERWEIGHT,
            Decimal("0.00490"),
        ),
        (
            market_cap_evaluator.MAXIMUM_ONE_WAY_ACTIVE_SHARE,
            _PINNED_MARKET_CAP_MAXIMUM_ONE_WAY_ACTIVE_SHARE,
            Decimal("0.0490"),
        ),
        (
            market_cap_evaluator.MAXIMUM_HHI_MULTIPLE,
            _PINNED_MARKET_CAP_MAXIMUM_HHI_MULTIPLE,
            Decimal("1.44"),
        ),
    )
    if any(
        type(observed) is not Decimal
        or observed != expected
        or observed != literal
        for observed, expected, literal in decimal_bindings
    ):
        return False
    try:
        profile_ids = namespace.get("PROFILE_IDS")
        v1_profile_ids = namespace.get("V1_PROFILE_IDS")
        v2_profile_ids = namespace.get("V2_PROFILE_IDS")
        v3_profile_ids = namespace.get("V3_PROFILE_IDS")
        tilt_profile_ids = namespace.get("TILT_PROFILE_IDS")
        all_profile_ids = namespace.get("ALL_PROFILE_IDS")
        qqq_profile_ids = namespace.get("QQQ_PROFILE_IDS")
        spy_profile_ids = namespace.get("SPY_PROFILE_IDS")
        canonical_profiles = namespace.get("_PROFILE_CANONICAL")
        projection_profile_ids = projection_builder.MARKET_CAP_PROFILE_IDS
        projection_v1_profile_ids = projection_builder.MARKET_CAP_V1_PROFILE_IDS
        projection_v2_profile_ids = projection_builder.MARKET_CAP_V2_PROFILE_IDS
        projection_v3_profile_ids = projection_builder.MARKET_CAP_V3_PROFILE_IDS
        projection_all_profile_ids = projection_builder.MARKET_CAP_ALL_PROFILE_IDS
        superseded_profile_ids = (
            projection_builder.SUPERSEDED_UNSPENT_PROFILE_IDS
        )
        projection_hashes = projection_builder.MARKET_CAP_PROFILE_SHA256S
        projection_all_hashes = (
            projection_builder.MARKET_CAP_ALL_PROFILE_SHA256S
        )
        source_paths = projection_builder.MARKET_CAP_PROJECT_SOURCE_PATHS
        legacy_source_paths = (
            projection_builder.MARKET_CAP_LEGACY_PROJECT_SOURCE_PATHS
        )
        costs = namespace.get("COST_BPS_SCENARIOS")
        if (
            namespace.get("require_market_cap_stock_portfolio_profile")
            is not _PINNED_REQUIRE_MARKET_CAP_PROFILE
            or namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_MARKET_CAP_RESULT_NAMES_CALLABLE
            or namespace.get("constituent_etf_tickers_for_profile")
            is not _PINNED_MARKET_CAP_CONSTITUENT_TICKERS_CALLABLE
            or runtime_namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_MARKET_CAP_RUNTIME_EXPECTED_NAMES
            or projection_builder._profile
            is not _PINNED_PROJECTION_PROFILE_CALLABLE
            or projection_builder.project_source_paths_for_profile
            is not _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE
            or type(profile_ids) is not tuple
            or profile_ids != _PINNED_MARKET_CAP_PROFILE_IDS
            or v1_profile_ids != _PINNED_MARKET_CAP_V1_PROFILE_IDS
            or v2_profile_ids != _PINNED_MARKET_CAP_V2_PROFILE_IDS
            or v3_profile_ids != _PINNED_MARKET_CAP_V3_PROFILE_IDS
            or tilt_profile_ids != _PINNED_MARKET_CAP_TILT_PROFILE_IDS
            or all_profile_ids != _PINNED_MARKET_CAP_ALL_PROFILE_IDS
            or tilt_profile_ids != v3_profile_ids + profile_ids
            or all_profile_ids
            != v1_profile_ids + v2_profile_ids + tilt_profile_ids
            or len(v1_profile_ids) != 6
            or len(v2_profile_ids) != 6
            or len(v3_profile_ids) != 2
            or len(profile_ids) != 2
            or any(type(item) is not str for item in all_profile_ids)
            or len(set(all_profile_ids)) != len(all_profile_ids)
            or type(qqq_profile_ids) is not tuple
            or qqq_profile_ids != _PINNED_MARKET_CAP_QQQ_PROFILE_IDS
            or type(spy_profile_ids) is not tuple
            or spy_profile_ids != _PINNED_MARKET_CAP_SPY_PROFILE_IDS
            or set(qqq_profile_ids).isdisjoint(spy_profile_ids) is not True
            or tuple(item for item in profile_ids if item in qqq_profile_ids)
            != qqq_profile_ids
            or tuple(item for item in profile_ids if item in spy_profile_ids)
            != spy_profile_ids
            or type(costs) is not tuple
            or any(type(item) is not int for item in costs)
            or costs != _PINNED_MARKET_CAP_COSTS
            or type(canonical_profiles) is not dict
            or canonical_profiles is not _PINNED_MARKET_CAP_PROFILE_CANONICAL_OBJECT
            or tuple(sorted(canonical_profiles.items()))
            != _PINNED_MARKET_CAP_PROFILE_CANONICAL_ROWS
            or any(
                type(key) is not str or type(value) is not bytes
                for key, value in canonical_profiles.items()
            )
            or type(projection_profile_ids) is not tuple
            or projection_profile_ids
            != _PINNED_PROJECTION_MARKET_CAP_PROFILE_IDS
            or projection_profile_ids != profile_ids
            or projection_v1_profile_ids
            != _PINNED_PROJECTION_MARKET_CAP_V1_PROFILE_IDS
            or projection_v1_profile_ids != v1_profile_ids
            or projection_v2_profile_ids
            != _PINNED_PROJECTION_MARKET_CAP_V2_PROFILE_IDS
            or projection_v2_profile_ids != v2_profile_ids
            or projection_v3_profile_ids
            != _PINNED_PROJECTION_MARKET_CAP_V3_PROFILE_IDS
            or projection_v3_profile_ids != v3_profile_ids
            or projection_all_profile_ids
            != _PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_IDS
            or projection_all_profile_ids != all_profile_ids
            or type(superseded_profile_ids) is not tuple
            or superseded_profile_ids
            != _PINNED_PROJECTION_SUPERSEDED_UNSPENT_PROFILE_IDS
            or superseded_profile_ids
            != _SUPERSEDED_UNSPENT_PROFILE_IDS
            or type(projection_hashes) is not dict
            or projection_hashes
            is not _PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256S_OBJECT
            or tuple(sorted(projection_hashes.items()))
            != _PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256_ROWS
            or set(projection_hashes) != set(profile_ids)
            or type(projection_all_hashes) is not dict
            or projection_all_hashes
            is not _PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256S_OBJECT
            or tuple(sorted(projection_all_hashes.items()))
            != _PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256_ROWS
            or set(projection_all_hashes) != set(all_profile_ids)
            or type(source_paths) is not tuple
            or any(type(item) is not str for item in source_paths)
            or source_paths != _PINNED_PROJECTION_MARKET_CAP_SOURCE_PATHS
            or type(legacy_source_paths) is not tuple
            or any(type(item) is not str for item in legacy_source_paths)
            or legacy_source_paths
            != _PINNED_PROJECTION_MARKET_CAP_LEGACY_SOURCE_PATHS
            or type(runtime_namespace.get("PROFILE_IDS")) is not tuple
            or runtime_namespace.get("PROFILE_IDS")
            != _PINNED_MARKET_CAP_RUNTIME_PROFILE_IDS
            or runtime_namespace.get("PROFILE_IDS") != profile_ids
        ):
            return False
        for (
            profile_id,
            expected_profile_bytes,
            expected_profile_sha256,
            expected_result_names,
        ) in _PINNED_MARKET_CAP_PROFILE_BINDINGS:
            observed_profile = _PINNED_REQUIRE_MARKET_CAP_PROFILE(profile_id)
            if (
                type(observed_profile) is not dict
                or _PINNED_JSON_DUMPS(
                    observed_profile,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("ascii")
                != expected_profile_bytes
                or observed_profile.get("profile_id") != profile_id
                or observed_profile.get("profile_sha256")
                != expected_profile_sha256
                or projection_all_hashes.get(profile_id)
                != expected_profile_sha256
                or _PINNED_PROJECTION_PROFILE_CALLABLE(profile_id)
                != observed_profile
                or _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE(profile_id)
                != _PINNED_PROJECTION_MARKET_CAP_SOURCE_PATHS
                or _PINNED_MARKET_CAP_RUNTIME_EXPECTED_NAMES(profile_id)
                != expected_result_names
                or tuple(
                    sorted(
                        (
                            *_PINNED_MARKET_CAP_RESULT_NAMES_CALLABLE(
                                profile_id
                            ),
                            "ARV2_RUNTIME_META",
                        )
                    )
                )
                != expected_result_names
                or _PINNED_MARKET_CAP_CONSTITUENT_TICKERS_CALLABLE(
                    profile_id
                )
                != (observed_profile.get("universe_proxy_ticker"),)
            ):
                return False
        return True
    except (Exception, RecursionError):
        return False


def _leverage_contract_bindings_are_current() -> bool:
    """Refuse any drift in the objective leverage or inherited base contract."""

    namespace = leverage_evaluator.__dict__
    runtime_namespace = leverage_runtime.__dict__
    if type(namespace) is not dict or type(runtime_namespace) is not dict:
        return False
    try:
        profile_ids = namespace.get("PROFILE_IDS")
        canonical_profiles = namespace.get("_PROFILE_CANONICAL")
        factors = namespace.get("LEVERAGE_FACTORS")
        scenarios = namespace.get("SCENARIOS")
        source_paths = projection_builder.OBJECTIVE_LEVERAGE_PROJECT_SOURCE_PATHS
        projection_profile_ids = projection_builder.OBJECTIVE_LEVERAGE_PROFILE_IDS
        projection_hashes = projection_builder.OBJECTIVE_LEVERAGE_PROFILE_SHA256S
        runtime_profile_ids = runtime_namespace.get("PROFILE_IDS")
        base_map = runtime_namespace.get("_BASE_PROFILE_BY_LEVERAGE")
        if (
            namespace.get("require_profile") is not _PINNED_REQUIRE_LEVERAGE_PROFILE
            or namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_LEVERAGE_RESULT_NAMES_CALLABLE
            or runtime_namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_LEVERAGE_RUNTIME_EXPECTED_NAMES
            or runtime_namespace.get("base_market_cap_profile_id_for_profile")
            is not _PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_CALLABLE
            or runtime_namespace.get("constituent_etf_tickers_for_profile")
            is not _PINNED_LEVERAGE_RUNTIME_CONSTITUENT_TICKERS_CALLABLE
            or projection_builder._profile
            is not _PINNED_PROJECTION_PROFILE_CALLABLE
            or projection_builder.project_source_paths_for_profile
            is not _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE
            or type(namespace.get("CONTRACT_ID")) is not str
            or namespace.get("CONTRACT_ID") != _PINNED_LEVERAGE_CONTRACT_ID
            or type(namespace.get("SUMMARY_SCHEMA")) is not str
            or namespace.get("SUMMARY_SCHEMA") != _PINNED_LEVERAGE_SUMMARY_SCHEMA
            or type(namespace.get("CELL_SCHEMA")) is not str
            or namespace.get("CELL_SCHEMA") != _PINNED_LEVERAGE_CELL_SCHEMA
            or type(namespace.get("META_STATISTIC_NAME")) is not str
            or namespace.get("META_STATISTIC_NAME")
            != _PINNED_LEVERAGE_META_STATISTIC_NAME
            or type(namespace.get("SELECTED_BASE_AGGREGATES_STATISTIC_NAME"))
            is not str
            or namespace.get("SELECTED_BASE_AGGREGATES_STATISTIC_NAME")
            != _PINNED_LEVERAGE_SELECTED_BASE_AGGREGATES_STATISTIC_NAME
            or type(namespace.get("MATCHED_BASE_AGGREGATES_STATISTIC_NAME"))
            is not str
            or namespace.get("MATCHED_BASE_AGGREGATES_STATISTIC_NAME")
            != _PINNED_LEVERAGE_MATCHED_BASE_AGGREGATES_STATISTIC_NAME
            or type(namespace.get("BASE_EVALUATOR_SOURCE_SHA256")) is not str
            or namespace.get("BASE_EVALUATOR_SOURCE_SHA256")
            != _PINNED_LEVERAGE_BASE_SOURCE_SHA256
            or hashlib.sha256(
                Path(market_cap_evaluator.__file__).read_bytes()
            ).hexdigest()
            != _PINNED_LEVERAGE_BASE_SOURCE_SHA256
            or type(profile_ids) is not tuple
            or profile_ids != _PINNED_LEVERAGE_PROFILE_IDS
            or namespace.get("V1_PROFILE_IDS")
            != _PINNED_LEVERAGE_V1_PROFILE_IDS
            or namespace.get("V2_PROFILE_IDS")
            != _PINNED_LEVERAGE_V2_PROFILE_IDS
            or namespace.get("ALL_PROFILE_IDS")
            != _PINNED_LEVERAGE_ALL_PROFILE_IDS
            or namespace.get("ALL_PROFILE_IDS")
            != (
                namespace.get("V1_PROFILE_IDS")
                + namespace.get("V2_PROFILE_IDS")
                + profile_ids
            )
            or len(profile_ids) != 2
            or any(type(item) is not str for item in profile_ids)
            or len(set(profile_ids)) != len(profile_ids)
            or type(canonical_profiles) is not dict
            or canonical_profiles is not _PINNED_LEVERAGE_PROFILE_CANONICAL_OBJECT
            or tuple(sorted(canonical_profiles.items()))
            != _PINNED_LEVERAGE_PROFILE_CANONICAL_ROWS
            or any(
                type(key) is not str or type(value) is not bytes
                for key, value in canonical_profiles.items()
            )
            or type(factors) is not tuple
            or factors != _PINNED_LEVERAGE_FACTORS
            or factors != (2, 3)
            or any(type(item) is not int for item in factors)
            or type(scenarios) is not tuple
            or scenarios != _PINNED_LEVERAGE_SCENARIOS
            or any(
                type(row) is not tuple
                or len(row) != 4
                or type(row[0]) is not str
                or type(row[1]) is not Decimal
                or type(row[2]) is not int
                or type(row[3]) is not bool
                for row in scenarios
            )
            or scenarios
            != (
                (
                    _PINNED_LEVERAGE_PRIMARY_SCENARIO_ID,
                    Decimal("0.06"),
                    10,
                    True,
                ),
                (
                    _PINNED_LEVERAGE_ADVERSE_SCENARIO_ID,
                    Decimal("0.10"),
                    20,
                    False,
                ),
            )
            or type(namespace.get("ANNUALIZATION_SESSIONS")) is not Decimal
            or namespace.get("ANNUALIZATION_SESSIONS")
            != _PINNED_LEVERAGE_ANNUALIZATION_SESSIONS
            or namespace.get("ANNUALIZATION_SESSIONS") != Decimal(252)
            or type(source_paths) is not tuple
            or source_paths != _PINNED_PROJECTION_LEVERAGE_SOURCE_PATHS
            or any(type(item) is not str for item in source_paths)
            or type(projection_profile_ids) is not tuple
            or projection_profile_ids != _PINNED_PROJECTION_LEVERAGE_PROFILE_IDS
            or projection_profile_ids != profile_ids
            or type(projection_hashes) is not dict
            or projection_hashes
            is not _PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256S_OBJECT
            or tuple(sorted(projection_hashes.items()))
            != _PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256_ROWS
            or type(runtime_profile_ids) is not tuple
            or runtime_profile_ids != _PINNED_LEVERAGE_RUNTIME_PROFILE_IDS
            or runtime_profile_ids != profile_ids
            or type(base_map) is not dict
            or base_map is not _PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_MAP_OBJECT
            or tuple(sorted(base_map.items()))
            != _PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_ROWS
            or type(runtime_namespace.get("RUNTIME_META_SCHEMA")) is not str
            or runtime_namespace.get("RUNTIME_META_SCHEMA")
            != _PINNED_LEVERAGE_RUNTIME_SCHEMA
            or type(runtime_namespace.get("RUNTIME_COMPLETED_STATUS")) is not str
            or runtime_namespace.get("RUNTIME_COMPLETED_STATUS")
            != _PINNED_LEVERAGE_RUNTIME_STATUS
            or type(runtime_namespace.get("MAX_TRAIN_SLICE_COUNT")) is not int
            or runtime_namespace.get("MAX_TRAIN_SLICE_COUNT")
            != _PINNED_LEVERAGE_RUNTIME_MAX_TRAIN_SLICES
        ):
            return False
        for (
            profile_id,
            expected_profile_bytes,
            expected_profile_sha256,
            expected_result_names,
        ) in _PINNED_LEVERAGE_PROFILE_BINDINGS:
            observed_profile = _PINNED_REQUIRE_LEVERAGE_PROFILE(profile_id)
            base_profile_id = observed_profile.get("base_profile_id")
            base_profile = _PINNED_REQUIRE_MARKET_CAP_PROFILE(base_profile_id)
            if (
                type(observed_profile) is not dict
                or _PINNED_JSON_DUMPS(
                    observed_profile,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("ascii")
                != expected_profile_bytes
                or observed_profile.get("profile_id") != profile_id
                or observed_profile.get("profile_sha256")
                != expected_profile_sha256
                or observed_profile.get("base_contract_id")
                != _PINNED_MARKET_CAP_CONTRACT_ID
                or observed_profile.get("base_evaluator_source_sha256")
                != _PINNED_LEVERAGE_BASE_SOURCE_SHA256
                or observed_profile.get("base_profile_sha256")
                != base_profile.get("profile_sha256")
                or base_map.get(profile_id) != base_profile_id
                or projection_hashes.get(profile_id)
                != expected_profile_sha256
                or _PINNED_PROJECTION_PROFILE_CALLABLE(profile_id)
                != observed_profile
                or _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE(profile_id)
                != _PINNED_PROJECTION_LEVERAGE_SOURCE_PATHS
                or _PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_CALLABLE(profile_id)
                != base_profile_id
                or _PINNED_LEVERAGE_RUNTIME_CONSTITUENT_TICKERS_CALLABLE(
                    profile_id
                )
                != (observed_profile.get("universe_proxy_ticker"),)
                or _PINNED_LEVERAGE_RUNTIME_EXPECTED_NAMES(profile_id)
                != expected_result_names
                or tuple(
                    sorted(
                        (
                            *_PINNED_LEVERAGE_RESULT_NAMES_CALLABLE(
                                profile_id
                            ),
                            "ARV2_RUNTIME_META",
                        )
                    )
                )
                != expected_result_names
            ):
                return False
        return _market_cap_contract_bindings_are_current()
    except (Exception, RecursionError):
        return False


def _six_universe_contract_bindings_are_current() -> bool:
    """Refuse drift in the three frozen six-universe diagnostic profiles."""

    evaluator_namespace = six_universe_evaluator.__dict__
    runtime_namespace = six_universe_runtime.__dict__
    gate_namespace = six_universe_gate.__dict__
    if any(
        type(item) is not dict
        for item in (evaluator_namespace, runtime_namespace, gate_namespace)
    ):
        return False
    try:
        profile_ids = evaluator_namespace.get("PROFILE_IDS")
        projection_profile_ids = projection_builder.SIX_UNIVERSE_PROFILE_IDS
        projection_hashes = projection_builder.SIX_UNIVERSE_PROFILE_SHA256S
        source_paths = projection_builder.SIX_UNIVERSE_PROJECT_SOURCE_PATHS
        scalar_bindings = (
            (
                evaluator_namespace.get("PROFILE_SCHEMA"),
                _PINNED_SIX_UNIVERSE_PROFILE_SCHEMA,
                str,
            ),
            (
                evaluator_namespace.get("SUMMARY_SCHEMA"),
                _PINNED_SIX_UNIVERSE_SUMMARY_SCHEMA,
                str,
            ),
            (
                evaluator_namespace.get("ACCOUNT_SCHEMA"),
                _PINNED_SIX_UNIVERSE_ACCOUNT_SCHEMA,
                str,
            ),
            (
                evaluator_namespace.get("SLEEVE_SCHEMA"),
                _PINNED_SIX_UNIVERSE_SLEEVE_SCHEMA,
                str,
            ),
            (
                evaluator_namespace.get("SERIES_SCHEMA"),
                _PINNED_SIX_UNIVERSE_SERIES_SCHEMA,
                str,
            ),
            (
                evaluator_namespace.get("DECISION_START_SESSION"),
                _PINNED_SIX_UNIVERSE_DECISION_START,
                str,
            ),
            (
                evaluator_namespace.get("EVALUATION_END_SESSION"),
                _PINNED_SIX_UNIVERSE_EVALUATION_END,
                str,
            ),
            (
                evaluator_namespace.get("EXPECTED_SESSION_COUNT"),
                _PINNED_SIX_UNIVERSE_EXPECTED_SESSIONS,
                int,
            ),
            (
                evaluator_namespace.get("EXPECTED_RETURN_SESSION_COUNT"),
                _PINNED_SIX_UNIVERSE_EXPECTED_RETURNS,
                int,
            ),
            (
                evaluator_namespace.get("EXPECTED_DECISION_SESSION_COUNT"),
                _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS,
                int,
            ),
            (
                evaluator_namespace.get("PRIMARY_COST_BPS_PER_SIDE"),
                _PINNED_SIX_UNIVERSE_PRIMARY_COST,
                int,
            ),
            (
                evaluator_namespace.get("MODELED_COST_RATE_PER_SIDE"),
                _PINNED_SIX_UNIVERSE_MODELED_COST_RATE,
                Decimal,
            ),
            (
                evaluator_namespace.get("ANNUALIZATION_SESSIONS"),
                _PINNED_SIX_UNIVERSE_ANNUALIZATION_SESSIONS,
                Decimal,
            ),
            (
                evaluator_namespace.get("GATE_SCORE_QUANTUM"),
                _PINNED_SIX_UNIVERSE_GATE_SCORE_QUANTUM,
                Decimal,
            ),
            (
                evaluator_namespace.get("MINIMUM_INVESTED_RETURN_SESSIONS"),
                _PINNED_SIX_UNIVERSE_MINIMUM_INVESTED_RETURNS,
                int,
            ),
            (
                runtime_namespace.get("MAXIMUM_TRAIN_SLICE_COUNT"),
                _PINNED_SIX_UNIVERSE_RUNTIME_MAX_TRAIN_SLICES,
                int,
            ),
            (
                runtime_namespace.get("TRAIN_WORK_UNITS_PER_SLICE"),
                _PINNED_SIX_UNIVERSE_RUNTIME_WORK_UNITS,
                int,
            ),
            (
                runtime_namespace.get("HISTORY_CHUNK_DECISION_COUNT"),
                _PINNED_SIX_UNIVERSE_RUNTIME_HISTORY_CHUNK_DECISIONS,
                int,
            ),
            (
                runtime_namespace.get("MAXIMUM_TOTAL_SOURCE_ROWS"),
                _PINNED_SIX_UNIVERSE_RUNTIME_MAX_SOURCE_ROWS,
                int,
            ),
        )
        if any(
            type(observed) is not expected_type or observed != expected
            for observed, expected, expected_type in scalar_bindings
        ):
            return False
        observed_statistic_names = (
            evaluator_namespace.get("META_STATISTIC_NAME"),
            evaluator_namespace.get("SIGNAL_STATISTIC_NAME"),
            evaluator_namespace.get("MATCHED_STATISTIC_NAME"),
            evaluator_namespace.get("ETF_BASKET_STATISTIC_NAME"),
            evaluator_namespace.get("SLEEVES_STATISTIC_NAME"),
            evaluator_namespace.get("SERIES_STATISTIC_NAME"),
            runtime_namespace.get("RUNTIME_META_STATISTIC_NAME"),
        )
        if (
            observed_statistic_names != _PINNED_SIX_UNIVERSE_STATISTIC_NAMES
            or type(profile_ids) is not tuple
            or profile_ids != _PINNED_SIX_UNIVERSE_PROFILE_IDS
            or len(profile_ids) != 4
            or len(set(profile_ids)) != 4
            or any(type(item) is not str for item in profile_ids)
            or type(projection_profile_ids) is not tuple
            or projection_profile_ids
            != _PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_IDS
            or projection_profile_ids != profile_ids
            or type(projection_hashes) is not dict
            or projection_hashes
            is not _PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256S_OBJECT
            or tuple(sorted(projection_hashes.items()))
            != _PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256_ROWS
            or type(source_paths) is not tuple
            or source_paths != _PINNED_PROJECTION_SIX_UNIVERSE_SOURCE_PATHS
            or any(type(item) is not str for item in source_paths)
            or evaluator_namespace.get("require_profile")
            is not _PINNED_REQUIRE_SIX_UNIVERSE_PROFILE
            or evaluator_namespace.get("expected_custom_summary_statistic_names")
            is not _PINNED_SIX_UNIVERSE_RESULT_NAMES_CALLABLE
            or projection_builder._profile
            is not _PINNED_PROJECTION_PROFILE_CALLABLE
            or projection_builder.project_source_paths_for_profile
            is not _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE
            or gate_namespace.get("UNIVERSE_IDS")
            != _PINNED_SIX_UNIVERSE_IDS
            or gate_namespace.get("TARGET_GROSS_EXPOSURE")
            != _PINNED_SIX_UNIVERSE_TARGET_GROSS
            or type(gate_namespace.get("TARGET_GROSS_EXPOSURE")) is not Decimal
        ):
            return False
        for (
            profile_id,
            expected_profile_bytes,
            expected_profile_sha256,
            expected_result_names,
        ) in _PINNED_SIX_UNIVERSE_PROFILE_BINDINGS:
            observed_profile = _PINNED_REQUIRE_SIX_UNIVERSE_PROFILE(profile_id)
            observed_record = observed_profile.to_record()
            if (
                type(observed_record) is not dict
                or _PINNED_JSON_DUMPS(
                    observed_record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("ascii")
                != expected_profile_bytes
                or observed_profile.profile_id != profile_id
                or observed_profile.profile_sha256
                != expected_profile_sha256
                or projection_hashes.get(profile_id)
                != expected_profile_sha256
                or _PINNED_PROJECTION_PROFILE_CALLABLE(profile_id)
                != observed_record
                or _PINNED_PROJECTION_SOURCE_PATHS_CALLABLE(profile_id)
                != _PINNED_PROJECTION_SIX_UNIVERSE_SOURCE_PATHS
                or tuple(
                    sorted(
                        (
                            *_PINNED_SIX_UNIVERSE_RESULT_NAMES_CALLABLE(
                                profile_id
                            ),
                            _PINNED_SIX_UNIVERSE_STATISTIC_NAMES[-1],
                        )
                    )
                )
                != expected_result_names
            ):
                return False
        return True
    except (Exception, RecursionError):
        return False


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > MAX_CONTROL_BYTES:
        _error(f"{name} is not bounded exact bytes")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=unique,
            parse_constant=lambda _item: (_ for _ in ()).throw(
                ValueError("nonstandard constant")
            ),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} is not strict ASCII JSON"
        ) from exc
    if type(value) is not dict or _canonical(value) != payload:
        _error(f"{name} is not one canonical JSON object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(f"{name} is not an exact SHA-256")
    return value


def _safe_name(value: object, name: str, maximum: int) -> str:
    if (
        type(value) is not str
        or _SAFE_NAME.fullmatch(value) is None
        or len(value.encode("utf-8")) > maximum
    ):
        _error(f"{name} is not an exact safe bounded name")
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        _error(f"{name} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} is not canonical UTC"
        ) from exc
    if (
        parsed.tzinfo != timezone.utc
        or parsed.microsecond != 0
        or parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        _error(f"{name} is not canonical UTC")
    return value


def _private_directory(value: Path) -> Path:
    if type(value) is not type(Path()) or not value.is_absolute() or ".." in value.parts:
        _error("preliminary control directory must be an absolute exact Path")
    current = Path(value.anchor)
    try:
        for part in value.parts[1:]:
            current /= part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                _error("preliminary control directory ancestry must be nonsymlink")
        observed = os.stat(value)
    except AcceptedRiskPreliminarySubmissionError:
        raise
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary control directory is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o700
        or observed.st_uid != os.getuid()
        or value.resolve(strict=True) != value
    ):
        _error("preliminary control directory must be owner-only mode 0700")
    return value


def _read_private(path: Path, name: str) -> bytes:
    if type(path) is not type(Path()) or path.parent != _private_directory(path.parent):
        _error(f"{name} path changed")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(f"{name} is unavailable") from exc
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
    directory = _private_directory(path.parent)
    if (
        type(path.name) is not str
        or not path.name
        or "/" in path.name
        or type(payload) is not bytes
        or not 0 < len(payload) <= MAX_CONTROL_BYTES
    ):
        _error(f"{name} path or payload changed")
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
                raise OSError("short control write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} already exists or could not be published"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory_descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    if _read_private(path, name) != payload:
        _error(f"{name} changed after publication")


def _identified(schema: str, prefix: str, record: dict[str, object]) -> tuple[str, str, bytes]:
    seed = {"schema": schema, "id": None, "sha256": None, **record}
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    identity = prefix + digest[:24]
    return identity, digest, _canonical({**seed, "id": identity, "sha256": digest})


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryHostSourceBinding:
    path: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryHostClosureBinding:
    closure_id: str
    closure_sha256: str
    worktree_root: str
    sources: tuple[AcceptedRiskPreliminaryHostSourceBinding, ...]
    canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": HOST_CLOSURE_SCHEMA,
            "closure_id": self.closure_id,
            "closure_sha256": self.closure_sha256,
            "worktree_root": self.worktree_root,
            "sources": [item.to_record() for item in self.sources],
        }


def _read_host_source(path: Path, *, root: Path) -> bytes:
    try:
        path.relative_to(root)
        original = os.lstat(path)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary host source escaped the exact worktree"
        ) from exc
    if resolved != path or stat.S_ISLNK(original.st_mode):
        _error("preliminary host source path uses a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary host source is unavailable"
        ) from exc
    try:
        before = os.fstat(descriptor)
        chunks = []
        remaining = MAX_HOST_SOURCE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 256 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        "st_dev", "st_ino", "st_uid", "st_mode", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if (
        any(getattr(original, field) != getattr(before, field) for field in identity)
        or
        any(getattr(before, field) != getattr(after, field) for field in identity)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or before.st_mode & 0o022
        or before.st_size != len(payload)
        or len(payload) > MAX_HOST_SOURCE_BYTES
        or (payload and not payload.endswith(b"\n"))
        or b"\r" in payload
    ):
        _error("preliminary host source is not one stable canonical file")
    return payload


def _walk_host_python_sources(directory: Path, root: Path) -> tuple[str, ...]:
    paths = []
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            with _PINNED_SCANDIR(current) as scanner:
                entries = sorted(scanner, key=lambda item: item.name)
        except OSError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary host source directory is unavailable"
            ) from exc
        for entry in entries:
            try:
                if entry.is_symlink():
                    _error("preliminary host source inventory contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                    continue
                regular = entry.is_file(follow_symlinks=False)
            except OSError as exc:
                raise AcceptedRiskPreliminarySubmissionError(
                    "preliminary host source inventory changed during scan"
                ) from exc
            if not regular:
                _error("preliminary host source inventory contains a special node")
            if entry.name.endswith(".py"):
                paths.append(str(Path(entry.path).relative_to(root)))
    return tuple(paths)


def _host_code_inventory_paths(root: Path) -> tuple[str, ...]:
    paths = list(HOST_CODE_PATHS)
    for relative_directory in HOST_CODE_DIRECTORY_PATHS:
        directory = root / relative_directory
        try:
            original = os.lstat(directory)
            resolved = directory.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary host code directory escaped the exact worktree"
            ) from exc
        if (
            resolved != directory
            or stat.S_ISLNK(original.st_mode)
            or not stat.S_ISDIR(original.st_mode)
        ):
            _error("preliminary host code directory changed or uses a symlink")
        paths.extend(_walk_host_python_sources(directory, root))
    result = tuple(sorted(paths))
    if (
        not result
        or len(result) != len(set(result))
        or any(type(item) is not str or not item.endswith(".py") for item in result)
    ):
        _error("preliminary host source inventory changed")
    return result


def _build_host_closure(worktree_root: Path) -> AcceptedRiskPreliminaryHostClosureBinding:
    if type(worktree_root) is not type(Path()) or not worktree_root.is_absolute():
        _error("preliminary worktree root must be an absolute exact Path")
    try:
        root = worktree_root.resolve(strict=True)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary worktree root is unavailable"
        ) from exc
    if root != worktree_root or not root.is_dir():
        _error("preliminary worktree root changed")
    sources = tuple(
        AcceptedRiskPreliminaryHostSourceBinding(
            relative,
            hashlib.sha256(
                payload := _read_host_source(root / relative, root=root)
            ).hexdigest(),
            len(payload),
        )
        for relative in _host_code_inventory_paths(root)
    )
    seed = {
        "schema": HOST_CLOSURE_SCHEMA,
        "closure_id": None,
        "closure_sha256": None,
        "worktree_root": str(root),
        "sources": [item.to_record() for item in sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    identity = "arv2-preliminary-qc-host-closure-" + digest[:24]
    document = _canonical(
        {**seed, "closure_id": identity, "closure_sha256": digest}
    )
    return AcceptedRiskPreliminaryHostClosureBinding(
        identity, digest, str(root), sources, document
    )


def _require_host_closure(
    value: AcceptedRiskPreliminaryHostClosureBinding,
) -> AcceptedRiskPreliminaryHostClosureBinding:
    if type(value) is not AcceptedRiskPreliminaryHostClosureBinding:
        _error("preliminary host closure type changed")
    rebuilt = _build_host_closure(Path(value.worktree_root))
    if value != rebuilt or value.canonical_document != rebuilt.canonical_document:
        _error("preliminary live host source closure changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryUploadEntry:
    schema: str
    role: str
    ordinal: int
    object_store_key: str
    byte_count: int
    content_sha256: str
    content_md5: str
    activation_manifest: bool

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminarySubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    control_directory: Path
    package_id: str
    package_sha256: str
    evaluator_manifest_id: str
    evaluator_manifest_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    upload_entries: tuple[AcceptedRiskPreliminaryUploadEntry, ...]
    projection_id: str
    projection_sha256: str
    evaluation_profile_id: str | None
    evaluation_profile_sha256: str | None
    project_source_set_sha256: str
    source_files: tuple[projection_builder.PreliminaryQcSourceFile, ...]
    host_closure: AcceptedRiskPreliminaryHostClosureBinding
    expected_custom_statistic_names: tuple[str, ...]
    expected_custom_statistic_names_sha256: str
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    package: package_builder.AcceptedRiskPreliminaryPackage = dataclasses.field(repr=False)
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection = dataclasses.field(repr=False)


def _upload_entries(package) -> tuple[AcceptedRiskPreliminaryUploadEntry, ...]:
    descriptors = package.upload_objects
    entries = []
    for index, ((descriptor, payload), expected) in enumerate(
        zip(_PINNED_ITER_UPLOADS(package), descriptors, strict=True)
    ):
        if (
            descriptor is not expected
            or descriptor.ordinal != expected.ordinal
            or len(payload) != descriptor.byte_count
            or hashlib.sha256(payload).hexdigest() != descriptor.content_sha256
            or descriptor.activation_manifest != (index == len(descriptors) - 1)
        ):
            _error("preliminary package upload sequence changed")
        entries.append(
            AcceptedRiskPreliminaryUploadEntry(
                UPLOAD_ENTRY_SCHEMA,
                descriptor.role,
                descriptor.ordinal,
                descriptor.object_store_key,
                descriptor.byte_count,
                descriptor.content_sha256,
                hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                descriptor.activation_manifest,
            )
        )
    if not entries or entries[-1].activation_manifest is not True:
        _error("preliminary package activation is not last")
    return tuple(entries)


def _plan_record(
    *, package, projection, organization_hash: str, project_name: str,
    backtest_name: str, control_directory: Path,
    upload_entries: tuple[AcceptedRiskPreliminaryUploadEntry, ...],
    host_closure: AcceptedRiskPreliminaryHostClosureBinding,
) -> dict[str, object]:
    source_records = [item.to_record() for item in projection.source_files]
    source_hash = hashlib.sha256(_canonical(source_records)).hexdigest()
    expected_result_names = _expected_result_names(
        projection.evaluation_profile_id
    )
    names_hash = hashlib.sha256(
        _canonical(list(expected_result_names))
    ).hexdigest()
    record = {
        "schema": (
            PLAN_SCHEMA
            if projection.evaluation_profile_id is None
            else REGIME_PLAN_SCHEMA
        ),
        "plan_id": None,
        "plan_sha256": None,
        "organization_id_sha256": organization_hash,
        "project_name": project_name,
        "backtest_name": backtest_name,
        "control_directory": str(control_directory),
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "evaluator_manifest_id": package.evaluator_manifest_id,
        "evaluator_manifest_sha256": package.evaluator_manifest_sha256,
        "activation_manifest_key": projection.activation_manifest_key,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "upload_entries": [item.to_record() for item in upload_entries],
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": source_hash,
        "source_files": source_records,
        "host_code_closure": host_closure.to_record(),
        "expected_custom_statistic_names": list(expected_result_names),
        "expected_custom_statistic_names_sha256": names_hash,
        "look_accounting": _look_accounting(
            evaluation_profile_id=projection.evaluation_profile_id
        ),
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "include_statistics_during_status": False,
        "result_read_calls": 1,
        "preliminary": True,
        "formal": False,
        "deployment": False,
        "orders": False,
        "trading": False,
        "retry_inside_adapter": False,
    }
    if projection.evaluation_profile_id is not None:
        record["evaluation_profile_id"] = projection.evaluation_profile_id
        record["evaluation_profile_sha256"] = projection.evaluation_profile_sha256
    return record


def build_accepted_risk_preliminary_submission_plan(
    *,
    package: package_builder.AcceptedRiskPreliminaryPackage,
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection,
    organization_id: str,
    project_name: str,
    backtest_name: str,
    control_directory: Path,
    worktree_root: Path,
) -> AcceptedRiskPreliminarySubmissionPlan:
    package = _PINNED_REQUIRE_PACKAGE(package)
    projection = _PINNED_REQUIRE_PROJECTION(projection)
    _safe_name(organization_id, "organization id", 512)
    _safe_name(project_name, "project name", MAX_PROJECT_NAME_BYTES)
    _safe_name(backtest_name, "backtest name", MAX_BACKTEST_NAME_BYTES)
    control_directory = _private_directory(control_directory)
    if (
        projection.package_id != package.package_id
        or projection.package_sha256 != package.package_sha256
    ):
        _error("preliminary package and profile-bound projection are not exact peers")
    uploads = _upload_entries(package)
    host_closure = _build_host_closure(worktree_root)
    organization_hash = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()
    record = _plan_record(
        package=package,
        projection=projection,
        organization_hash=organization_hash,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=control_directory,
        upload_entries=uploads,
        host_closure=host_closure,
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    identity = "arv2-preliminary-qc-submission-" + digest[:24]
    source_hash = record["project_source_set_sha256"]
    names_hash = record["expected_custom_statistic_names_sha256"]
    value = AcceptedRiskPreliminarySubmissionPlan(
        identity,
        digest,
        organization_id,
        organization_hash,
        project_name,
        backtest_name,
        control_directory,
        package.package_id,
        package.package_sha256,
        package.evaluator_manifest_id,
        package.evaluator_manifest_sha256,
        projection.activation_manifest_key,
        projection.activation_manifest_sha256,
        uploads,
        projection.projection_id,
        projection.projection_sha256,
        projection.evaluation_profile_id,
        projection.evaluation_profile_sha256,
        source_hash,
        projection.source_files,
        host_closure,
        _expected_result_names(projection.evaluation_profile_id),
        names_hash,
        MAX_COMPILE_POLLS,
        MAX_STATUS_POLLS,
        1,
        package,
        projection,
    )
    _PINNED_REQUIRE_PACKAGE(package)
    _PINNED_REQUIRE_PROJECTION(projection)
    return value


def require_accepted_risk_preliminary_submission_plan(
    value: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPlan:
    if type(value) is not AcceptedRiskPreliminarySubmissionPlan:
        _error("preliminary submission plan type changed")
    rebuilt = build_accepted_risk_preliminary_submission_plan(
        package=value.package,
        projection=value.projection,
        organization_id=value.organization_id,
        project_name=value.project_name,
        backtest_name=value.backtest_name,
        control_directory=value.control_directory,
        worktree_root=Path(value.host_closure.worktree_root),
    )
    if value != rebuilt:
        _error("preliminary submission plan changed")
    return value


def _submission_plan_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "submission-plan-" + plan.plan_sha256[:24] + ".json"
    )


def _submission_plan_bytes(plan: AcceptedRiskPreliminarySubmissionPlan) -> bytes:
    record = _plan_record(
        package=plan.package,
        projection=plan.projection,
        organization_hash=plan.organization_id_sha256,
        project_name=plan.project_name,
        backtest_name=plan.backtest_name,
        control_directory=plan.control_directory,
        upload_entries=plan.upload_entries,
        host_closure=_require_host_closure(plan.host_closure),
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    identity = "arv2-preliminary-qc-submission-" + digest[:24]
    if digest != plan.plan_sha256 or identity != plan.plan_id:
        _error("preliminary persisted plan identity changed")
    return _canonical(
        {**record, "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256}
    )


def persist_accepted_risk_preliminary_submission_plan(
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> Path:
    """Publish or reauthenticate the exact canonical plan in its private run dir."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    path = _submission_plan_path(plan)
    payload = _submission_plan_bytes(plan)
    try:
        observed = _read_private(path, "submission plan")
    except AcceptedRiskPreliminarySubmissionError:
        _write_private_once(path, payload, "submission plan")
    else:
        if observed != payload:
            _error("persisted preliminary submission plan changed")
    return path


def load_accepted_risk_preliminary_submission_plan(
    *,
    plan_path: Path,
    package: package_builder.AcceptedRiskPreliminaryPackage,
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection,
    organization_id: str,
) -> AcceptedRiskPreliminarySubmissionPlan:
    """Rebuild a plan in a later process and authenticate it to durable bytes."""
    _safe_name(organization_id, "organization id", 512)
    payload = _read_private(plan_path, "submission plan")
    raw = _strict_object(payload, "submission plan")
    project_name = _safe_name(
        raw.get("project_name"), "persisted project name", MAX_PROJECT_NAME_BYTES
    )
    backtest_name = _safe_name(
        raw.get("backtest_name"), "persisted backtest name", MAX_BACKTEST_NAME_BYTES
    )
    raw_control_directory = raw.get("control_directory")
    if (
        type(raw_control_directory) is not str
        or not raw_control_directory
        or len(raw_control_directory.encode("utf-8")) > 4096
    ):
        _error("persisted control directory changed")
    control_directory = Path(raw_control_directory)
    raw_host_closure = raw.get("host_code_closure")
    if (
        type(raw_host_closure) is not dict
        or type(raw_host_closure.get("worktree_root")) is not str
        or not raw_host_closure["worktree_root"]
        or len(raw_host_closure["worktree_root"].encode("utf-8")) > 4096
    ):
        _error("persisted preliminary host closure changed")
    rebuilt = build_accepted_risk_preliminary_submission_plan(
        package=package,
        projection=projection,
        organization_id=organization_id,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=control_directory,
        worktree_root=Path(raw_host_closure["worktree_root"]),
    )
    if (
        plan_path != _submission_plan_path(rebuilt)
        or payload != _submission_plan_bytes(rebuilt)
    ):
        _error("persisted preliminary submission plan does not match inputs")
    return rebuilt


def _execution_authority(plan: AcceptedRiskPreliminarySubmissionPlan) -> bytes:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    record = {
        "schema": EXECUTION_AUTHORITY_SCHEMA,
        "signature_purpose": "formal_qc_execution",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "organization_id_sha256": plan.organization_id_sha256,
        "project_name": plan.project_name,
        "backtest_name": plan.backtest_name,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "project_source_set_sha256": plan.project_source_set_sha256,
        "package_upload_count": len(plan.upload_entries),
        "project_source_count": len(plan.source_files),
        "host_code_closure": _require_host_closure(
            plan.host_closure
        ).to_record(),
        "look_accounting": _look_accounting(
            evaluation_profile_id=plan.projection.evaluation_profile_id
        ),
        "actions": list(EXECUTION_ACTIONS),
        "maximum_backtest_submissions": 1,
        "statistics_free_status": True,
        "result_read_authority_separate": True,
        "retries_inside_adapter": 0,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if plan.evaluation_profile_id is not None:
        record["evaluation_profile_id"] = plan.evaluation_profile_id
        record["evaluation_profile_sha256"] = plan.evaluation_profile_sha256
    return _canonical(record)


def render_accepted_risk_preliminary_execution_authority_candidate(
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> bytes:
    return _execution_authority(plan)


def _require_execution_signature(
    value: OwnerSignatureAuthority | None, payload: bytes,
) -> OwnerSignatureAuthority:
    try:
        return _PINNED_REQUIRE_EXECUTION_SIGNATURE(value, authority_payload=payload)
    except (OwnerSignatureAuthorityError, TypeError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "detached formal_qc_execution owner signature is unavailable"
        ) from exc


def _require_result_signature(
    value: OwnerSignatureAuthority | None, payload: bytes,
) -> OwnerSignatureAuthority:
    try:
        return _PINNED_REQUIRE_RESULT_SIGNATURE(value, authority_payload=payload)
    except (OwnerSignatureAuthorityError, TypeError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "detached formal_qc_result_read owner signature is unavailable"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminarySubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


def _execution_permit_path(plan) -> Path:
    return plan.control_directory / (
        "execution-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _build_execution_permit(plan, signature, started_at_utc):
    _utc(started_at_utc, "execution started_at")
    record = {
        "plan_sha256": plan.plan_sha256,
        "owner_signature_sha256": _sha(
            signature.authority_sha256, "execution signature authority"
        ),
        "look_accounting": _look_accounting(
            evaluation_profile_id=plan.projection.evaluation_profile_id
        ),
        "started_at_utc": started_at_utc,
        "submission_attempt_count": 1,
        "ambiguous_submission_consumes_permit": True,
        "retry_authorized_inside_adapter": False,
    }
    identity, digest, payload = _identified(
        EXECUTION_PERMIT_SCHEMA, "arv2-preliminary-qc-execution-permit-", record
    )
    return AcceptedRiskPreliminarySubmissionPermit(
        identity,
        digest,
        plan.plan_sha256,
        signature.authority_sha256,
        started_at_utc,
        _execution_permit_path(plan),
        payload,
    )


def _spend_execution_permit(plan, signature, started_at_utc):
    permit = _build_execution_permit(plan, signature, started_at_utc)
    try:
        _write_private_once(permit.permit_path, permit.permit_bytes, "execution permit")
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "execution_permit", permit.permit_id, "permit already spent or unavailable"
        ) from exc
    return permit


def require_accepted_risk_preliminary_submission_permit(
    value: AcceptedRiskPreliminarySubmissionPermit,
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
    owner_signature: OwnerSignatureAuthority,
) -> AcceptedRiskPreliminarySubmissionPermit:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_signature(owner_signature, _execution_authority(plan))
    return _require_execution_permit_bytes(value, plan)


def _require_execution_permit_bytes(
    value: AcceptedRiskPreliminarySubmissionPermit,
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPermit:
    if type(value) is not AcceptedRiskPreliminarySubmissionPermit:
        _error("preliminary execution permit type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_path != _execution_permit_path(plan)
        or _read_private(value.permit_path, "execution permit")
        != value.permit_bytes
    ):
        _error("preliminary execution permit changed")
    raw = _strict_object(value.permit_bytes, "execution permit")
    seed = dict(raw)
    if set(seed) != {
        "schema", "id", "sha256", "plan_sha256",
        "owner_signature_sha256", "look_accounting", "started_at_utc",
        "submission_attempt_count", "ambiguous_submission_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary execution permit fields changed")
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != EXECUTION_PERMIT_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("owner_signature_sha256") != value.owner_signature_sha256
        or raw.get("look_accounting")
        != _look_accounting(
            evaluation_profile_id=plan.projection.evaluation_profile_id
        )
        or raw.get("started_at_utc") != value.started_at_utc
        or raw.get("submission_attempt_count") != 1
        or raw.get("ambiguous_submission_consumes_permit") is not True
        or raw.get("retry_authorized_inside_adapter") is not False
        or declared_id != value.permit_id
        or declared_sha != value.permit_sha256
        or digest != value.permit_sha256
        or value.permit_id != "arv2-preliminary-qc-execution-permit-" + digest[:24]
    ):
        _error("preliminary execution permit identity changed")
    _sha(value.owner_signature_sha256, "execution permit owner signature")
    _utc(value.started_at_utc, "execution permit started_at")
    return value


def load_accepted_risk_preliminary_submission_permit(
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPermit:
    """Authenticate and rehydrate the already-spent execution permit."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    path = _execution_permit_path(plan)
    payload = _read_private(path, "execution permit")
    raw = _strict_object(payload, "execution permit")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256",
        "owner_signature_sha256", "look_accounting", "started_at_utc",
        "submission_attempt_count", "ambiguous_submission_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary execution permit fields changed")
    value = AcceptedRiskPreliminarySubmissionPermit(
        raw["id"],
        raw["sha256"],
        raw["plan_sha256"],
        raw["owner_signature_sha256"],
        raw["started_at_utc"],
        path,
        payload,
    )
    return _require_execution_permit_bytes(value, plan)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryPreCreateControl:
    control_id: str
    control_sha256: str
    plan_sha256: str
    permit_sha256: str
    project_id: int
    compile_id: str
    backtest_name: str
    control_path: Path
    control_bytes: bytes = dataclasses.field(repr=False)


def _precreate_control_path(plan) -> Path:
    return plan.control_directory / (
        "pre-create-control-" + plan.plan_sha256[:24] + ".json"
    )


def _build_precreate_control(plan, permit, project_id, compile_id):
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "package_sha256": plan.package_sha256,
        "projection_sha256": plan.projection_sha256,
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_name": plan.backtest_name,
        "look_accounting": _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        ),
        "backtests_create_call_limit": 1,
        "backtests_create_may_have_occurred": True,
        "statistics_free_recovery_only": True,
    }
    identity, digest, payload = _identified(
        PRECREATE_CONTROL_SCHEMA,
        "arv2-preliminary-qc-pre-create-",
        record,
    )
    return AcceptedRiskPreliminaryPreCreateControl(
        identity, digest, plan.plan_sha256, permit.permit_sha256,
        project_id, compile_id, plan.backtest_name,
        _precreate_control_path(plan), payload,
    )


def _require_precreate_control(value, plan, permit):
    if type(value) is not AcceptedRiskPreliminaryPreCreateControl:
        _error("preliminary pre-create control type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.backtest_name != plan.backtest_name
        or value.control_path != _precreate_control_path(plan)
        or _read_private(value.control_path, "pre-create control")
        != value.control_bytes
    ):
        _error("preliminary pre-create control lineage changed")
    raw = _strict_object(value.control_bytes, "pre-create control")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "package_sha256", "projection_sha256", "project_id", "compile_id",
        "backtest_name", "look_accounting", "backtests_create_call_limit",
        "backtests_create_may_have_occurred", "statistics_free_recovery_only",
    }:
        _error("preliminary pre-create control fields changed")
    seed = dict(raw)
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != PRECREATE_CONTROL_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("permit_sha256") != permit.permit_sha256
        or raw.get("package_sha256") != plan.package_sha256
        or raw.get("projection_sha256") != plan.projection_sha256
        or type(value.project_id) is not int
        or value.project_id <= 0
        or raw.get("project_id") != value.project_id
        or raw.get("compile_id") != value.compile_id
        or raw.get("backtest_name") != value.backtest_name
        or raw.get("look_accounting")
        != _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        )
        or raw.get("backtests_create_call_limit") != 1
        or raw.get("backtests_create_may_have_occurred") is not True
        or raw.get("statistics_free_recovery_only") is not True
        or declared_id != value.control_id
        or declared_sha != value.control_sha256
        or digest != value.control_sha256
        or value.control_id != "arv2-preliminary-qc-pre-create-" + digest[:24]
    ):
        _error("preliminary pre-create control identity changed")
    _safe_name(value.compile_id, "pre-create compile id", 512)
    return value


def load_accepted_risk_preliminary_pre_create_control(
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
    permit: AcceptedRiskPreliminarySubmissionPermit,
) -> AcceptedRiskPreliminaryPreCreateControl:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    path = _precreate_control_path(plan)
    payload = _read_private(path, "pre-create control")
    raw = _strict_object(payload, "pre-create control")
    value = AcceptedRiskPreliminaryPreCreateControl(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("permit_sha256"), raw.get("project_id"), raw.get("compile_id"),
        raw.get("backtest_name"), path, payload,
    )
    return _require_precreate_control(value, plan, permit)


def _launch_recovery_permit_path(plan) -> Path:
    return plan.control_directory / (
        "launch-recovery-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _launch_recovery_permit_record(plan, permit, control):
    return {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "precreate_control_sha256": control.control_sha256,
        "look_accounting": _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        ),
        "statistics_free_backtests_list_call_limit": 1,
        "retry_inside_adapter": False,
    }


def _spend_launch_recovery_permit(plan, permit, control) -> str:
    identity, digest, payload = _identified(
        LAUNCH_RECOVERY_PERMIT_SCHEMA,
        "arv2-preliminary-qc-launch-recovery-permit-",
        _launch_recovery_permit_record(plan, permit, control),
    )
    if identity != "arv2-preliminary-qc-launch-recovery-permit-" + digest[:24]:
        _error("preliminary launch-recovery permit identity changed")
    try:
        _write_private_once(
            _launch_recovery_permit_path(plan),
            payload,
            "launch-recovery permit",
        )
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "launch_recovery", permit.permit_id, "recovery permit already spent"
        ) from exc
    return digest


def _require_launch_recovery_permit(plan, permit, control, expected_sha256):
    _sha(expected_sha256, "launch-recovery permit")
    payload = _read_private(
        _launch_recovery_permit_path(plan), "launch-recovery permit"
    )
    identity, digest, expected = _identified(
        LAUNCH_RECOVERY_PERMIT_SCHEMA,
        "arv2-preliminary-qc-launch-recovery-permit-",
        _launch_recovery_permit_record(plan, permit, control),
    )
    if (
        payload != expected
        or digest != expected_sha256
        or identity
        != "arv2-preliminary-qc-launch-recovery-permit-" + digest[:24]
    ):
        _error("preliminary launch-recovery permit lineage changed")
    return digest


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    precreate_control_sha256: str
    launch_recovery_permit_sha256: str | None
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryTerminalStatus:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    poll_count: int
    include_statistics: bool
    result_values_selected: bool


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryResultReadPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryAggregateResult:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    result_permit_sha256: str
    project_id: int
    backtest_id: str
    custom_statistics: tuple[tuple[str, str], ...]
    custom_statistics_sha256: str
    persisted_path: Path
    backtests_read_call_count: int
    raw_provider_rows_selected: bool
    logs_selected: bool
    charts_selected: bool
    orders_selected: bool


def _launch_record(
    value: AcceptedRiskPreliminaryLaunchReceipt,
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "precreate_control_sha256": value.precreate_control_sha256,
        "launch_recovery_permit_sha256": value.launch_recovery_permit_sha256,
        "look_accounting": _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        ),
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }


def _terminal_record(value: AcceptedRiskPreliminaryTerminalStatus) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
        "result_values_selected": value.result_values_selected,
    }


def _result_record(
    value: AcceptedRiskPreliminaryAggregateResult,
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "launch_sha256": value.launch_sha256,
        "terminal_sha256": value.terminal_sha256,
        "result_permit_sha256": value.result_permit_sha256,
        "look_accounting": _look_accounting(
            stage="result",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        ),
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "custom_statistics": [list(item) for item in value.custom_statistics],
        "custom_statistics_sha256": value.custom_statistics_sha256,
        "persisted_path": str(value.persisted_path),
        "backtests_read_call_count": value.backtests_read_call_count,
        "raw_provider_rows_selected": value.raw_provider_rows_selected,
        "logs_selected": value.logs_selected,
        "charts_selected": value.charts_selected,
        "orders_selected": value.orders_selected,
    }


def _launch_receipt_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "launch-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _terminal_receipt_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "terminal-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _identified_receipt_bytes(
    *, schema: str, prefix: str, record: dict[str, object],
    receipt_id: str, receipt_sha256: str,
) -> bytes:
    expected_id, expected_sha, payload = _identified(schema, prefix, record)
    if receipt_id != expected_id or receipt_sha256 != expected_sha:
        _error("preliminary durable receipt identity changed")
    return payload


def _launch_receipt_bytes(
    value: AcceptedRiskPreliminaryLaunchReceipt,
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> bytes:
    return _identified_receipt_bytes(
        schema=LAUNCH_SCHEMA,
        prefix="arv2-preliminary-qc-launch-",
        record=_launch_record(value, plan),
        receipt_id=value.receipt_id,
        receipt_sha256=value.receipt_sha256,
    )


def _terminal_receipt_bytes(value: AcceptedRiskPreliminaryTerminalStatus) -> bytes:
    return _identified_receipt_bytes(
        schema=TERMINAL_SCHEMA,
        prefix="arv2-preliminary-qc-terminal-",
        record=_terminal_record(value),
        receipt_id=value.receipt_id,
        receipt_sha256=value.receipt_sha256,
    )


def _load_launch_receipt_impl(*, plan, permit, register_launch):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    control = load_accepted_risk_preliminary_pre_create_control(
        plan=plan, permit=permit
    )
    payload = _read_private(_launch_receipt_path(plan), "launch receipt")
    raw = _strict_object(payload, "launch receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "precreate_control_sha256", "launch_recovery_permit_sha256",
        "look_accounting", "project_id", "compile_id", "backtest_id", "backtest_name",
        "initial_status",
    }:
        _error("preliminary launch receipt fields changed")
    value = AcceptedRiskPreliminaryLaunchReceipt(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["permit_sha256"],
        raw["precreate_control_sha256"], raw["launch_recovery_permit_sha256"],
        raw["project_id"], raw["compile_id"], raw["backtest_id"],
        raw["backtest_name"], raw["initial_status"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.precreate_control_sha256 != control.control_sha256
        or value.project_id != control.project_id
        or value.compile_id != control.compile_id
        or raw.get("look_accounting")
        != _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        )
        or type(value.project_id) is not int
        or value.project_id <= 0
        or value.backtest_name != plan.backtest_name
    ):
        _error("preliminary launch receipt lineage changed")
    if value.initial_status == RECOVERED_LAUNCH_INITIAL_STATUS:
        _require_launch_recovery_permit(
            plan,
            permit,
            control,
            value.launch_recovery_permit_sha256,
        )
    elif value.launch_recovery_permit_sha256 is not None:
        _error("preliminary direct launch unexpectedly binds recovery")
    _safe_name(value.compile_id, "persisted compile id", 512)
    _safe_name(value.backtest_id, "persisted backtest id", 512)
    _safe_name(value.initial_status, "persisted initial status", 512)
    if payload != _launch_receipt_bytes(value, plan):
        _error("persisted preliminary launch receipt changed")
    register_launch(value, plan, permit)
    return value


def _load_terminal_receipt_impl(
    *, plan, permit, launch, require_launch, register_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    require_launch(launch, plan, permit)
    payload = _read_private(_terminal_receipt_path(plan), "terminal receipt")
    raw = _strict_object(payload, "terminal receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "launch_sha256", "project_id", "backtest_id", "terminal_status",
        "poll_count", "include_statistics", "result_values_selected",
    }:
        _error("preliminary terminal receipt fields changed")
    value = AcceptedRiskPreliminaryTerminalStatus(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["permit_sha256"],
        raw["launch_sha256"], raw["project_id"], raw["backtest_id"],
        raw["terminal_status"], raw["poll_count"], raw["include_statistics"],
        raw["result_values_selected"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or type(value.terminal_status) is not str
        or value.terminal_status not in _PINNED_BACKTEST_TERMINAL_STATES
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
        or value.result_values_selected is not False
        or payload != _terminal_receipt_bytes(value)
    ):
        _error("preliminary terminal receipt lineage changed")
    register_terminal(value, plan, permit, launch)
    return value


def _make_return_authority():
    lock = threading.RLock()
    launch_state: dict[int, tuple[object, ...]] = {}
    terminal_state: dict[int, tuple[object, ...]] = {}
    result_state: dict[int, tuple[object, ...]] = {}
    authority_pid = os.getpid()

    def register_launch(value, plan, permit):
        with lock:
            launch_state[id(value)] = (
                weakref.ref(value), plan, permit,
                _canonical(_launch_record(value, plan)),
                authority_pid,
            )

    def require_launch(value, plan, permit):
        if type(value) is not AcceptedRiskPreliminaryLaunchReceipt:
            _error("preliminary launch receipt type changed")
        with lock:
            state = launch_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] != _canonical(_launch_record(value, plan))
            or state[4] != os.getpid()
        ):
            _error("preliminary launch receipt lacks process-return authority")
        seed = {
            "schema": LAUNCH_SCHEMA,
            "id": None,
            "sha256": None,
            **_launch_record(value, plan),
        }
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-launch-" + digest[:24]:
            _error("preliminary launch receipt identity changed")
        return value

    def register_terminal(value, plan, permit, launch):
        require_launch(launch, plan, permit)
        with lock:
            terminal_state[id(value)] = (
                weakref.ref(value), plan, permit, launch,
                _canonical(_terminal_record(value)), authority_pid,
            )

    def require_terminal(value, plan, permit, launch):
        require_launch(launch, plan, permit)
        if type(value) is not AcceptedRiskPreliminaryTerminalStatus:
            _error("preliminary terminal receipt type changed")
        with lock:
            state = terminal_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] is not launch
            or state[4] != _canonical(_terminal_record(value))
            or state[5] != os.getpid()
        ):
            _error("preliminary terminal receipt lacks process-return authority")
        seed = {"schema": TERMINAL_SCHEMA, "id": None, "sha256": None, **_terminal_record(value)}
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-terminal-" + digest[:24]:
            _error("preliminary terminal receipt identity changed")
        return value

    def register_result(value, plan, permit, launch, terminal, result_permit):
        require_terminal(terminal, plan, permit, launch)
        with lock:
            result_state[id(value)] = (
                weakref.ref(value), plan, permit, launch, terminal, result_permit,
                _canonical(_result_record(value, plan)), authority_pid,
            )

    def require_result(value, plan, permit, launch, terminal, result_permit):
        require_terminal(terminal, plan, permit, launch)
        if type(value) is not AcceptedRiskPreliminaryAggregateResult:
            _error("preliminary result receipt type changed")
        with lock:
            state = result_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] is not launch
            or state[4] is not terminal
            or state[5] is not result_permit
            or state[6] != _canonical(_result_record(value, plan))
            or state[7] != os.getpid()
        ):
            _error("preliminary result receipt lacks process-return authority")
        seed = {
            "schema": RESULT_RECEIPT_SCHEMA,
            "id": None,
            "sha256": None,
            **_result_record(value, plan),
        }
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-result-" + digest[:24]:
            _error("preliminary result receipt identity changed")
        return value

    return register_launch, require_launch, register_terminal, require_terminal, register_result, require_result


(
    _register_launch,
    _require_launch,
    _register_terminal,
    _require_terminal,
    _register_result,
    _require_result,
) = _make_return_authority()
del _make_return_authority


def _wait(seconds: int) -> None:
    if seconds not in (COMPILE_POLL_SECONDS, STATUS_POLL_SECONDS):
        _error("preliminary polling interval changed")
    time.sleep(seconds)


def _transport(client, capability, method: str, *args):
    return _PINNED_TRANSPORT_CALL(client, capability, method, *args)


def _new_launch(
    plan, permit, control, backtest_id, initial,
    launch_recovery_permit_sha256=None,
):
    if initial == RECOVERED_LAUNCH_INITIAL_STATUS:
        _sha(launch_recovery_permit_sha256, "launch-recovery permit")
    elif launch_recovery_permit_sha256 is not None:
        _error("preliminary direct launch unexpectedly binds recovery")
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "precreate_control_sha256": control.control_sha256,
        "launch_recovery_permit_sha256": launch_recovery_permit_sha256,
        "project_id": control.project_id,
        "compile_id": control.compile_id,
        "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "initial_status": initial,
    }
    identity, digest, _payload = _identified(
        LAUNCH_SCHEMA,
        "arv2-preliminary-qc-launch-",
        {
            **record,
            "look_accounting": _look_accounting(
                stage="launch",
                evaluation_profile_id=plan.projection.evaluation_profile_id,
            ),
        },
    )
    return AcceptedRiskPreliminaryLaunchReceipt(identity, digest, **record)


def _execute_accepted_risk_preliminary_submission_once_impl(
    *, plan, owner_signature, client, started_at_utc,
    minter, signature_verifier, transport_verifier, register_launch,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_fresh_launch_profile(plan)
    signature = signature_verifier(owner_signature, _execution_authority(plan))
    persist_accepted_risk_preliminary_submission_plan(plan)
    transport_verifier(client)
    permit = _spend_execution_permit(plan, signature, started_at_utc)
    capability = minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "package_sha256": plan.package_sha256,
            "projection_sha256": plan.projection_sha256,
        },
        call_budget={
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
            "backtests/create": 1,
        },
    )
    try:
        _transport(client, capability, "_request_json", "authenticate", {})
        inventory = _PINNED_READ_PROJECTS(
            _transport(client, capability, "_request_json", "projects/read", {})
        )
        if any(type(item) is dict and item.get("name") == plan.project_name for item in inventory):
            _error("exact preliminary project already exists")
        created = _PINNED_CREATED_PROJECT(
            _transport(
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact = _PINNED_READ_PROJECTS(
            _transport(
                client,
                capability,
                "_request_json",
                "projects/read",
                {"projectId": project_id},
            )
        )
        if len(exact) != 1:
            _error("new preliminary project identity is ambiguous")
        _PINNED_PROJECT_RECORD(
            exact[0], name=plan.project_name, organization_id=plan.organization_id
        )

        observed_entries = []
        for descriptor, payload in _PINNED_ITER_UPLOADS(plan.package):
            entry = plan.upload_entries[len(observed_entries)]
            if (
                descriptor.object_store_key != entry.object_store_key
                or descriptor.content_sha256 != entry.content_sha256
                or descriptor.byte_count != entry.byte_count
                or hashlib.md5(payload, usedforsecurity=False).hexdigest()
                != entry.content_md5
                or descriptor.activation_manifest != entry.activation_manifest
            ):
                _error("preliminary package changed during upload")
            _transport(
                client,
                capability,
                "_set_object_multipart",
                plan.organization_id,
                entry.object_store_key,
                payload,
            )
            _PINNED_OBJECT_METADATA(
                _transport(
                    client,
                    capability,
                    "_read_object_properties",
                    plan.organization_id,
                    entry.object_store_key,
                ),
                entry,
            )
            observed_entries.append(entry)
        if tuple(observed_entries) != plan.upload_entries or observed_entries[-1].activation_manifest is not True:
            _error("preliminary package upload inventory changed")

        existing = _PINNED_READ_FILES(
            _transport(
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        projected = {item.project_path: item for item in plan.source_files}
        unexpected = set(existing) - set(projected)
        if unexpected - {QC_DEFAULT_RESEARCH_NOTEBOOK_PATH}:
            _error("new preliminary project contains an unprojected source")
        if QC_DEFAULT_RESEARCH_NOTEBOOK_PATH in unexpected:
            _PINNED_SUCCESS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    "files/delete",
                    {"projectId": project_id, "name": QC_DEFAULT_RESEARCH_NOTEBOOK_PATH},
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            _PINNED_SUCCESS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    endpoint,
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
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if set(readback) != set(projected):
            _error("preliminary project source inventory is not exact")
        for path, source in projected.items():
            try:
                payload = readback[path].encode("ascii")
            except UnicodeError as exc:
                raise AcceptedRiskPreliminarySubmissionError(
                    "preliminary source readback is not exact ASCII"
                ) from exc
            if (
                payload != source.source_bytes
                or len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                _error("preliminary project source readback changed")
        compile_id = _PINNED_COMPILE_ID(
            _transport(
                client, capability, "_request_json", "compile/create",
                {"projectId": project_id},
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
                _error("preliminary compile polling exhausted")
            _wait(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            _error("preliminary project did not compile BuildSuccess")
        control = _build_precreate_control(
            plan, permit, project_id, compile_id
        )
        _write_private_once(
            control.control_path,
            control.control_bytes,
            "pre-create control",
        )
        _require_precreate_control(control, plan, permit)
        backtest_id, initial = _PINNED_CREATED_BACKTEST(
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
        launch = _new_launch(plan, permit, control, backtest_id, initial)
        _write_private_once(
            _launch_receipt_path(plan),
            _launch_receipt_bytes(launch, plan),
            "launch receipt",
        )
        register_launch(launch, plan, permit)
        return permit, launch
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "submission", permit.permit_id, type(exc).__name__
        ) from exc


def _recover_accepted_risk_preliminary_launch_once_impl(
    *, plan, owner_signature, permit, client,
    minter, signature_verifier, transport_verifier,
    load_launch, register_launch,
):
    """Recover the unique run after create may have succeeded without a receipt."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    signature_verifier(owner_signature, _execution_authority(plan))
    _require_execution_permit_bytes(permit, plan)
    launch_path = _launch_receipt_path(plan)
    if _PINNED_LEXISTS(launch_path):
        return load_launch(
            plan=plan,
            permit=permit,
            register_launch=register_launch,
        )
    control = load_accepted_risk_preliminary_pre_create_control(
        plan=plan, permit=permit
    )
    transport_verifier(client)
    recovery_permit_sha256 = _spend_launch_recovery_permit(
        plan, permit, control
    )
    capability = minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-launch-recovery-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "precreate_control_sha256": control.control_sha256,
            "project_id": control.project_id,
            "backtest_name": control.backtest_name,
        },
        call_budget={"backtests/list": 1},
    )
    try:
        status = _PINNED_PARSE_UNIQUE_RUN(
            _transport(
                client,
                capability,
                "_request_json",
                "backtests/list",
                {
                    "projectId": control.project_id,
                    "includeStatistics": False,
                },
            ),
            expected_project_id=control.project_id,
            expected_backtest_name=control.backtest_name,
        )
        launch = _new_launch(
            plan,
            permit,
            control,
            status.backtest_id,
            RECOVERED_LAUNCH_INITIAL_STATUS,
            recovery_permit_sha256,
        )
        _write_private_once(
            launch_path,
            _launch_receipt_bytes(launch, plan),
            "launch receipt",
        )
        register_launch(launch, plan, permit)
        return launch
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "launch_recovery", permit.permit_id, type(exc).__name__
        ) from exc


def _new_terminal(plan, permit, launch, status, count):
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "launch_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": status,
        "poll_count": count,
        "include_statistics": False,
        "result_values_selected": False,
    }
    identity, digest, _payload = _identified(
        TERMINAL_SCHEMA, "arv2-preliminary-qc-terminal-", record
    )
    return AcceptedRiskPreliminaryTerminalStatus(identity, digest, **record)


def _inspect_accepted_risk_preliminary_terminal_status_impl(
    *, plan, owner_signature, permit, launch, client,
    minter, signature_verifier, transport_verifier, require_launch,
    register_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    signature_verifier(owner_signature, _execution_authority(plan))
    _require_execution_permit_bytes(permit, plan)
    require_launch(launch, plan, permit)
    transport_verifier(client)
    capability = minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-status-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_sha256": launch.receipt_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = _PINNED_PARSE_STATUS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    "backtests/list",
                    {"projectId": launch.project_id, "includeStatistics": False},
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise AcceptedRiskPreliminarySubmissionLocked(
                "terminal_status", permit.permit_id, type(exc).__name__
            ) from exc
        if status.status in _PINNED_BACKTEST_TERMINAL_STATES:
            terminal = _new_terminal(plan, permit, launch, status.status, index + 1)
            _write_private_once(
                _terminal_receipt_path(plan),
                _terminal_receipt_bytes(terminal),
                "terminal receipt",
            )
            register_terminal(terminal, plan, permit, launch)
            if terminal.terminal_status != "Completed.":
                raise AcceptedRiskPreliminaryTerminalFailure(terminal)
            return terminal
        if index + 1 == plan.status_poll_limit:
            raise AcceptedRiskPreliminarySubmissionLocked(
                "terminal_status", permit.permit_id, "poll limit exhausted"
            )
        _wait(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable preliminary status loop")


def _result_permit_path(plan):
    return plan.control_directory / (
        "result-read-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _build_result_permit(plan, launch, terminal, signature, started_at_utc):
    _utc(started_at_utc, "result read started_at")
    record = {
        "plan_sha256": plan.plan_sha256,
        "launch_sha256": launch.receipt_sha256,
        "terminal_sha256": terminal.receipt_sha256,
        "owner_signature_sha256": _sha(
            signature.authority_sha256, "result signature authority"
        ),
        "started_at_utc": started_at_utc,
        "backtests_read_call_count": 1,
        "ambiguous_result_read_consumes_permit": True,
        "retry_authorized_inside_adapter": False,
    }
    identity, digest, payload = _identified(
        RESULT_PERMIT_SCHEMA, "arv2-preliminary-qc-result-permit-", record
    )
    return AcceptedRiskPreliminaryResultReadPermit(
        identity,
        digest,
        plan.plan_sha256,
        launch.receipt_sha256,
        terminal.receipt_sha256,
        signature.authority_sha256,
        started_at_utc,
        _result_permit_path(plan),
        payload,
    )


def _require_result_permit_bytes(value, plan, launch, terminal):
    if type(value) is not AcceptedRiskPreliminaryResultReadPermit:
        _error("preliminary result-read permit type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.permit_path != _result_permit_path(plan)
        or _read_private(value.permit_path, "result-read permit")
        != value.permit_bytes
    ):
        _error("preliminary result-read permit lineage changed")
    raw = _strict_object(value.permit_bytes, "result-read permit")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "owner_signature_sha256", "started_at_utc",
        "backtests_read_call_count", "ambiguous_result_read_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary result-read permit fields changed")
    seed = dict(raw)
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != RESULT_PERMIT_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("launch_sha256") != launch.receipt_sha256
        or raw.get("terminal_sha256") != terminal.receipt_sha256
        or raw.get("owner_signature_sha256") != value.owner_signature_sha256
        or raw.get("started_at_utc") != value.started_at_utc
        or raw.get("backtests_read_call_count") != 1
        or raw.get("ambiguous_result_read_consumes_permit") is not True
        or raw.get("retry_authorized_inside_adapter") is not False
        or declared_id != value.permit_id
        or declared_sha != value.permit_sha256
        or digest != value.permit_sha256
        or value.permit_id != "arv2-preliminary-qc-result-permit-" + digest[:24]
    ):
        _error("preliminary result-read permit identity changed")
    _sha(value.owner_signature_sha256, "result permit owner signature")
    _utc(value.started_at_utc, "result permit started_at")
    return value


def _load_result_permit_impl(
    *, plan, execution_permit, launch, terminal, require_launch, require_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    path = _result_permit_path(plan)
    payload = _read_private(path, "result-read permit")
    raw = _strict_object(payload, "result-read permit")
    required = {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "owner_signature_sha256", "started_at_utc",
        "backtests_read_call_count", "ambiguous_result_read_consumes_permit",
        "retry_authorized_inside_adapter",
    }
    if set(raw) != required:
        _error("preliminary result-read permit fields changed")
    value = AcceptedRiskPreliminaryResultReadPermit(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["launch_sha256"],
        raw["terminal_sha256"], raw["owner_signature_sha256"],
        raw["started_at_utc"], path, payload,
    )
    return _require_result_permit_bytes(value, plan, launch, terminal)


def _parse_custom_result(response, plan, launch):
    if type(response) is not dict or not set(response).issubset(
        {"success", "errors", "messages", "backtest"}
    ) or response.get("success") is not True:
        _error("preliminary backtests/read envelope changed")
    for key in ("errors", "messages"):
        if key in response and (
            type(response[key]) is not list
            or any(type(item) is not str for item in response[key])
        ):
            _error("preliminary backtests/read message envelope changed")
    backtest = response.get("backtest")
    if type(backtest) is not dict:
        _error("preliminary backtests/read omitted its backtest")
    allowed = _PINNED_BACKTEST_STATUS_KEYS | _PINNED_DISCARDED_BACKTEST_KEYS | {"statistics"}
    if any(type(key) is not str or key not in allowed for key in backtest.keys()):
        _error("preliminary backtests/read backtest envelope changed")
    if (
        backtest.get("backtestId") != launch.backtest_id
        or backtest.get("projectId") != launch.project_id
        or backtest.get("name") != launch.backtest_name
        or backtest.get("status") != "Completed."
    ):
        _error("preliminary backtests/read returned another run")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or any(type(key) is not str for key in statistics):
        _error("preliminary backtests/read omitted exact statistics mapping")
    selected_names = tuple(sorted(key for key in statistics if key.startswith("ARV2_")))
    if selected_names != plan.expected_custom_statistic_names:
        _error("preliminary custom result key inventory changed")
    pairs = []
    parsed = {}
    for name in selected_names:
        value = statistics[name]
        if type(value) is not str or not value or len(value) > 4_096:
            _error("preliminary custom result value exceeded its exact bound")
        try:
            payload = value.encode("ascii")
        except UnicodeError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary custom result is not ASCII JSON"
            ) from exc
        parsed[name] = _strict_object(payload, "preliminary custom statistic")
        pairs.append((name, value))
    _validate_aggregate_records(parsed, plan)
    return tuple(pairs)


_CELL_FIELDS = frozenset(
    {
        "schema", "source_view_id", "score_arm", "horizon_sessions",
        "window_id", "status", "eligible_score_row_count",
        "accepted_outcome_pair_count", "missing_outcome_pair_count",
        "sector_refused_row_count", "valid_ic_date_count",
        "invalid_ic_date_count", "mean_daily_spearman_ic",
        "median_daily_spearman_ic", "positive_ic_date_share",
        "mean_of_daily_cross_section_mean_excess_returns",
        "median_of_daily_cross_section_mean_excess_returns",
        "outcome_definition", "formal_accept_reject_disposition",
    }
)
_RUNTIME_META_FIELDS = frozenset(
    {
        "schema", "status", "package_id", "package_sha256",
        "activation_manifest_sha256", "symbol_resolution_id",
        "symbol_resolution_sha256", "resolved_security_count",
        "named_security_refusal_count", "training_slice_count",
        "result_transport", "host_object_store_export_required",
        "preliminary", "point_in_time", "formal", "control_residualized",
        "economic_portfolio", "etf_or_leverage", "deployment", "orders",
        "trading",
    }
)
_PRELIMINARY_META_FIELDS = frozenset(
    {
        "schema", "contract_id", "manifest_id", "manifest_sha256", "status",
        "source_lineage_sha256s", "windows", "source_view_ids", "score_arms",
        "horizons", "outcome_definition", "history_normalization_mode",
        "history_value_field", "decay_state_method", "benchmark_role",
        "q_data_policy_id", "input_security_count", "input_contribution_count",
        "completed_callback_count", "accepted_risk_disclosures",
        "omitted_formal_components", "raw_provider_rows_in_summary",
        "raw_security_outcome_rows_in_summary", "raw_price_rows_in_summary",
        "formal_result", "alpha_claim_authorized", "summary_id",
        "summary_sha256",
    }
)
_REGIME_RUNTIME_META_FIELDS = frozenset(
    (_RUNTIME_META_FIELDS - {"training_slice_count"})
    | {
        "evaluation_profile_id",
        "evaluation_profile_sha256",
        "runtime_slice_count",
    }
)
_REGIME_CELL_FIELDS = frozenset(
    {
        "schema",
        "source_view_id",
        "score_arm",
        "horizon_sessions",
        "profile_id",
        "window_start_session",
        "window_end_session",
        "status",
        "eligible_score_row_count",
        "accepted_outcome_pair_count",
        "missing_outcome_pair_count",
        "benchmark_endpoint_unavailable_pair_count",
        "named_figi_resolution_refusal_pair_count",
        "security_entry_unavailable_pair_count",
        "membership_ended_by_exit_with_exit_unavailable_pair_count",
        "within_membership_exit_unavailable_pair_count",
        "missing_pair_counter_sum_matches_total",
        "sector_refused_row_count",
        "valid_ic_date_count",
        "invalid_ic_date_count",
        "mean_daily_spearman_ic",
        "median_daily_spearman_ic",
        "positive_ic_date_share",
        "mean_of_daily_cross_section_mean_excess_returns",
        "median_of_daily_cross_section_mean_excess_returns",
        "outcome_definition",
        "endpoint_price_conditioning",
        "membership_ended_by_exit_interpretation",
        "formal_accept_reject_disposition",
    }
)
_REGIME_META_FIELDS = frozenset(
    {
        "schema",
        "contract_id",
        "input_contract_id",
        "manifest_id",
        "manifest_sha256",
        "status",
        "source_lineage_sha256s",
        "profile",
        "source_view_ids",
        "score_arms",
        "horizons",
        "outcome_definition",
        "history_normalization_mode",
        "history_value_field",
        "decay_state_method",
        "benchmark_role",
        "q_data_policy_id",
        "input_security_count",
        "input_contribution_count",
        "named_figi_resolution_refusal_count",
        "completed_callback_count",
        "r055_signal_rule_changed",
        "outcome_availability_disclosures",
        "accepted_risk_disclosures",
        "raw_provider_rows_in_summary",
        "raw_security_outcome_rows_in_summary",
        "raw_price_rows_in_summary",
        "terminal_payoff_applied",
        "economic_portfolio_evaluation",
        "formal_result",
        "alpha_claim_authorized",
        "summary_id",
        "summary_sha256",
    }
)
_ETF_RUNTIME_META_FIELDS = frozenset(
    {
        "schema",
        "status",
        "profile_id",
        "profile_sha256",
        "package_id",
        "package_sha256",
        "activation_manifest_sha256",
        "symbol_resolution_id",
        "symbol_resolution_sha256",
        "resolved_security_count",
        "named_security_refusal_count",
        "candidate_etf_count",
        "result_transport",
        "host_object_store_export_required",
        "preliminary",
        "point_in_time",
        "formal",
        "control_residualized",
        "economic_portfolio",
        "etf",
        "leverage",
        "deployment",
        "orders",
        "trading",
    }
)
_ETF_META_FIELDS = frozenset(
    {
        "schema",
        "contract_id",
        "profile",
        "package_id",
        "package_sha256",
        "input_manifest_id",
        "input_manifest_sha256",
        "status",
        "decision_session_count",
        "portfolio_return_session_count",
        "invested_return_session_count",
        "selected_decision_session_count",
        "mean_eligible_etf_count",
        "mean_selected_etf_count",
        "holdings_snapshot_refusal_count",
        "stale_holdings_snapshot_refusal_count",
        "holdings_completeness_refusal_count",
        "mapping_refusal_count",
        "liquidity_refusal_count",
        "stock_sector_refusal_session_count",
        "holdings_source",
        "holdings_point_in_time_claim",
        "fixed_sleeve_is_exhaustive_reverse_index",
        "aum_filter_applied",
        "aum_filter_omission",
        "peer_normalization",
        "direct_stock_comparator_present",
        "industry_comparator_present",
        "market_benchmark_present",
        "terminal_payoff_applied",
        "current_vintage_non_pristine_pit_input",
        "raw_provider_rows_in_summary",
        "raw_constituent_rows_in_summary",
        "raw_price_rows_in_summary",
        "formal_result",
        "alpha_claim_authorized",
        "economic_portfolio_evaluation",
        "leverage",
        "deployment",
        "orders",
        "trading",
        "summary_id",
        "summary_sha256",
    }
)
_ETF_IC_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "horizon_sessions",
        "status",
        "valid_ic_date_count",
        "invalid_ic_date_count",
        "accepted_outcome_pair_count",
        "missing_outcome_pair_count",
        "mean_daily_spearman_ic",
        "median_daily_spearman_ic",
        "positive_ic_date_share",
        "entry_timing",
        "benchmark",
        "formal_accept_reject_disposition",
    }
)
_ETF_PORTFOLIO_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "cost_bps_per_side",
        "primary_cost_scenario",
        "status",
        "return_session_count",
        "invested_return_session_count",
        "cumulative_return",
        "spy_cumulative_return",
        "cumulative_return_minus_spy",
        "annualized_arithmetic_return",
        "annualized_volatility",
        "zero_rate_sharpe",
        "zero_rate_sortino",
        "maximum_drawdown",
        "average_daily_two_sided_turnover",
        "average_cash_weight",
        "leverage",
        "orders_submitted",
        "formal_accept_reject_disposition",
    }
)
_STOCK_PORTFOLIO_RUNTIME_META_FIELDS = frozenset(
    (_REGIME_RUNTIME_META_FIELDS)
)
_STOCK_PORTFOLIO_META_FIELDS = frozenset(
    {
        "schema",
        "contract_id",
        "profile_id",
        "profile_sha256",
        "package_id",
        "package_sha256",
        "input_manifest_id",
        "input_manifest_sha256",
        "status",
        "decision_session_count",
        "portfolio_return_session_count",
        "invested_return_session_count",
        "signal_selected_decision_count",
        "selected_execution_count",
        "rebalance_execution_count",
        "full_target_execution_count",
        "underfilled_target_execution_count",
        "matched_rebalance_execution_count",
        "matched_target_met_execution_count",
        "matched_underfilled_target_execution_count",
        "sector_refused_decision_count",
        "mean_eligible_score_count",
        "mean_selected_name_count",
        "mean_executed_target_gross_exposure",
        "matched_mean_executed_target_gross_exposure",
        "average_holding_count",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "deferred_rebalance_count",
        "partial_rebalance_decision_count",
        "stale_position_deferral_count",
        "mean_locked_gross_at_partial_decisions",
        "locked_exposure_over_target_count",
        "membership_end_liquidation_count",
        "membership_end_zero_recovery_count",
        "membership_end_entry_refusal_count",
        "matched_entry_price_refusal_count",
        "matched_stale_mark_session_count",
        "matched_deferred_rebalance_count",
        "matched_partial_rebalance_decision_count",
        "matched_stale_position_deferral_count",
        "matched_mean_locked_gross_at_partial_decisions",
        "matched_locked_exposure_over_target_count",
        "matched_membership_end_liquidation_count",
        "matched_membership_end_zero_recovery_count",
        "matched_membership_end_entry_refusal_count",
        "named_figi_resolution_refusal_count",
        "history_normalization_mode",
        "history_value_field",
        "r055_signal_rule_changed",
        "liquidity_filter_applied",
        "terminal_payoff_applied",
        "membership_end_liquidation_is_terminal_payoff",
        "membership_end_missing_price_policy",
        "matched_exposure_targeted_to_signal_executed_gross",
        "current_vintage_non_pristine_pit_input",
        "raw_provider_rows_in_summary",
        "raw_security_outcome_rows_in_summary",
        "raw_price_rows_in_summary",
        "formal_result",
        "alpha_claim_authorized",
        "economic_portfolio_evaluation",
        "leverage",
        "deployment",
        "orders",
        "trading",
        "summary_id",
        "summary_sha256",
    }
)
_STOCK_PORTFOLIO_CELL_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "cost_bps_per_side",
        "primary_cost_scenario",
        "status",
        "return_metric_conditioning",
        "risk_metrics_are_price_proxy_conditioned",
        "exposure_underfill_present",
        "return_session_count",
        "invested_return_session_count",
        "cumulative_return",
        "matched_eligible_stock_cumulative_return",
        "spy_cumulative_return",
        "cumulative_return_minus_matched",
        "cumulative_return_minus_spy",
        "annualized_arithmetic_return",
        "annualized_volatility",
        "zero_rate_sharpe",
        "zero_rate_sortino",
        "maximum_drawdown",
        "average_daily_two_sided_turnover",
        "average_cash_weight",
        "matched_annualized_arithmetic_return",
        "matched_annualized_volatility",
        "matched_zero_rate_sharpe",
        "matched_zero_rate_sortino",
        "matched_maximum_drawdown",
        "matched_average_daily_two_sided_turnover",
        "matched_average_cash_weight",
        "leverage",
        "orders_submitted",
        "formal_accept_reject_disposition",
    }
)
_MARKET_CAP_RUNTIME_META_FIELDS = frozenset(
    {
        "schema",
        "status",
        "package_id",
        "package_sha256",
        "activation_manifest_sha256",
        "symbol_resolution_id",
        "symbol_resolution_sha256",
        "resolved_security_count",
        "named_security_refusal_count",
        "evaluation_profile_id",
        "evaluation_profile_sha256",
        "runtime_slice_count",
        "point_in_time_history_call_count",
        "point_in_time_fetched_source_row_count",
        "point_in_time_eligible_score_bearing_count",
        "point_in_time_market_cap_covered_count",
        "point_in_time_market_cap_uncovered_count",
        "result_transport",
        "host_object_store_export_required",
        "preliminary",
        "point_in_time",
        "formal",
        "control_residualized",
        "economic_portfolio",
        "etf_or_leverage",
        "deployment",
        "orders",
        "trading",
    }
)
_MARKET_CAP_META_FIELDS = frozenset(
    {
        "schema",
        "contract_id",
        "profile_id",
        "profile_sha256",
        "package_id",
        "package_sha256",
        "input_manifest_id",
        "input_manifest_sha256",
        "status",
        "decision_session_count",
        "portfolio_return_session_count",
        "mean_point_in_time_eligible_count",
        "mean_eligible_score_count",
        "mean_selected_name_count",
        "eligible_without_R055_score_count",
        "sector_refused_decision_count",
        "named_figi_resolution_refusal_count",
        "r055_signal_rule_changed",
        "point_in_time_market_cap_weighting",
        "selected_and_matched_target_same_gross",
        "market_cap_values_in_summary",
        "raw_security_ids_in_summary",
        "raw_price_rows_in_summary",
        "formal_result",
        "alpha_claim_authorized",
        "economic_portfolio_evaluation",
        "leverage",
        "deployment",
        "orders",
        "trading",
        "summary_id",
        "summary_sha256",
    }
)
_MARKET_CAP_TILT_META_FIELDS = frozenset(
    {
        *_MARKET_CAP_META_FIELDS,
        "analyst_revisions_role",
        "benchmark_logical_id",
        "benchmark_history_normalization_mode",
        "benchmark_history_observation",
        "benchmark_raw_observation_sha256",
        "benchmark_return_path_sha256",
        "benchmark_observation_count",
        "benchmark_return_interval_count",
        "benchmark_first_used_session",
        "benchmark_last_used_session",
    }
)
_MARKET_CAP_ACCOUNT_FIELDS = frozenset(
    {
        "rebalance_execution_count",
        "full_target_execution_count",
        "underfilled_target_execution_count",
        "locked_exposure_over_target_count",
        "mean_executed_gross_exposure",
        "minimum_executed_gross_exposure",
        "maximum_executed_gross_exposure",
        "mean_maximum_position_weight",
        "maximum_position_weight",
        "mean_invested_weight_hhi",
        "mean_effective_holding_count",
        "average_holding_count",
        "average_daily_two_sided_turnover",
        "average_cash_weight",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "partial_rebalance_decision_count",
        "stale_position_deferral_count",
        "selection_exit_deferral_count",
        "eligibility_exit_liquidation_count",
        "eligibility_exit_zero_recovery_count",
    }
)
_MARKET_CAP_TILT_ACCOUNT_FIELDS = frozenset(
    {
        *_MARKET_CAP_ACCOUNT_FIELDS,
        "locked_sector_over_target_count",
        "sector_target_underfill_count",
    }
)
_MARKET_CAP_TILT_FIELDS = frozenset(
    {
        "schema",
        "decision_session_count",
        "tilt_enabled_decision_count",
        "tilt_underfilled_decision_count",
        "minimum_ranked_nonzero_score_count",
        "minimum_positive_score_count",
        "minimum_negative_score_count",
        "minimum_tilted_name_count_when_enabled",
        "minimum_point_in_time_sector_count",
        "maximum_one_way_active_share",
        "maximum_overweight",
        "maximum_hhi_ratio_to_benchmark",
        "minimum_weight_ratio_to_benchmark_when_enabled",
        "maximum_weight_ratio_to_benchmark_when_enabled",
        "maximum_absolute_sector_active_weight",
        "underfilled_exact_benchmark",
        "missing_or_zero_score_exact_benchmark",
        "sector_mapping_exhaustive",
        "sector_neutrality_exact",
        "sector_neutrality_scope",
    }
)
_MARKET_CAP_CELL_FIELDS = _STOCK_PORTFOLIO_CELL_FIELDS
_LEVERAGE_RUNTIME_META_FIELDS = frozenset(
    {
        "schema",
        "status",
        "package_id",
        "package_sha256",
        "activation_manifest_sha256",
        "symbol_resolution_id",
        "symbol_resolution_sha256",
        "resolved_security_count",
        "named_security_refusal_count",
        "evaluation_profile_id",
        "evaluation_profile_sha256",
        "base_market_cap_profile_id",
        "base_market_cap_profile_sha256",
        "runtime_slice_count",
        "point_in_time_history_call_count",
        "point_in_time_fetched_source_row_count",
        "point_in_time_eligible_score_bearing_count",
        "point_in_time_market_cap_covered_count",
        "point_in_time_market_cap_uncovered_count",
        "leverage_factors",
        "scenario_ids",
        "result_transport",
        "host_object_store_export_required",
        "preliminary",
        "point_in_time",
        "formal",
        "control_residualized",
        "economic_portfolio",
        "etf_or_leverage",
        "synthetic_leverage",
        "margin_calls_modeled",
        "borrow_availability_modeled",
        "deployment",
        "orders",
        "trading",
    }
)
_LEVERAGE_META_FIELDS = frozenset(
    {
        "schema",
        "contract_id",
        "profile_id",
        "profile_sha256",
        "package_id",
        "package_sha256",
        "input_manifest_id",
        "input_manifest_sha256",
        "status",
        "base_contract_id",
        "base_profile_id",
        "base_profile_sha256",
        "base_evaluator_source_sha256",
        "decision_session_count",
        "return_session_count",
        "r055_signal_rule_changed",
        "base_security_selection_changed",
        "point_in_time_membership_and_market_cap_weighting",
        "matched_comparator_levered_identically",
        "raw_security_ids_in_summary",
        "raw_price_rows_in_summary",
        "raw_provider_rows_in_summary",
        "synthetic_only",
        "formal_result",
        "alpha_claim_authorized",
        "evaluator_io",
        "margin_calls_modeled",
        "borrow_availability_modeled",
        "orders",
        "deployment",
        "trading",
        "summary_id",
        "summary_sha256",
    }
)
_LEVERAGE_PATH_PREFIXES = ("selected_", "matched_", "synthetic_spy_")
_LEVERAGE_PATH_SUFFIXES = (
    "cumulative_return",
    "cumulative_return_before_financing",
    "cumulative_financing_drag",
    "arithmetic_financing_debit",
    "annualized_arithmetic_return",
    "annualized_volatility",
    "zero_rate_sharpe",
    "zero_rate_sortino",
    "maximum_drawdown",
    "financing_session_count",
)
_LEVERAGE_CELL_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "base_profile_id",
        "scenario_id",
        "primary_scenario",
        "leverage_factor",
        "annual_financing_rate",
        "underlying_cost_bps_per_side",
        "underlying_cost_is_already_in_base_return",
        "second_transaction_cost_deduction",
        "status",
        "return_session_count",
        *(
            prefix + suffix
            for prefix in _LEVERAGE_PATH_PREFIXES
            for suffix in _LEVERAGE_PATH_SUFFIXES
        ),
        "selected_minus_matched_cumulative_return",
        "selected_minus_synthetic_spy_cumulative_return",
        "portfolio_level_daily_reset",
        "synthetic_only",
        "margin_calls_modeled",
        "borrow_availability_modeled",
        "security_level_financing_modeled",
        "broker_liquidation_modeled",
        "orders_submitted",
        "formal_accept_reject_disposition",
    }
)
_SIX_UNIVERSE_META_FIELDS = frozenset(
    {
        "schema",
        "status",
        "profile_id",
        "profile_sha256",
        "gate_profile_id",
        "gate_profile_sha256",
        "package_id",
        "package_sha256",
        "input_manifest_id",
        "input_manifest_sha256",
        "symbol_resolution_id",
        "symbol_resolution_sha256",
        "construction_path_sha256",
        "result_fragments_sha256",
        "decision_session_count",
        "price_history_batch_count",
        "pit_history_call_count",
        "pit_source_row_count",
        "analyst_source_view",
        "point_in_time_etf_membership_and_market_cap",
        "point_in_time_analyst_archive",
        "current_vintage_identity_basis",
        "aggregate_only",
        "raw_rows_in_output",
        "orders",
        "deployment",
        "trading",
        "summary_id",
        "summary_sha256",
    }
)
_SIX_UNIVERSE_ACCOUNT_FIELDS = frozenset(
    {
        "schema",
        "role",
        "cost_bps_per_side",
        "cumulative_return",
        "annualized_arithmetic_return",
        "annualized_volatility",
        "zero_rate_sharpe",
        "maximum_drawdown",
        "average_daily_two_sided_turnover",
        "annualized_two_sided_turnover",
        "average_cash_weight",
        "mean_holding_count",
        "mean_target_effective_holdings",
        "maximum_target_weight",
        "return_session_count",
        "invested_return_session_count",
        "rebalance_count",
        "full_target_count",
        "underfilled_target_count",
        "locked_over_target_count",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "stale_position_deferral_count",
        "eligibility_exit_zero_recovery_count",
        "return_metric_conditioning",
        "equity_return_path_sha256",
        "raw_price_rows_in_output",
        "raw_security_ids_in_output",
    }
)
_SIX_UNIVERSE_SLEEVES_FIELDS = frozenset({"schema", "universes"})
_SIX_UNIVERSE_SLEEVE_FIELDS = frozenset(
    {
        "universe_id",
        "decision_count",
        "coverage_valid_count",
        "signal_full_etf_fallback_count",
        "signal_partial_etf_fallback_count",
        "matched_full_etf_fallback_count",
        "mean_positive_score_count",
        "mean_signal_stock_count",
        "mean_matched_stock_count",
        "minimum_mapping_ratio",
        "minimum_cap_weight_coverage_ratio",
    }
)
_SIX_UNIVERSE_SERIES_FIELDS = frozenset({"schema", "series"})
_SIX_UNIVERSE_SERIES_ROW_FIELDS = frozenset(
    {
        "universe_id",
        "normalization_mode",
        "observation",
        "expected_session_count",
        "observation_count",
        "raw_observation_sha256",
        "used_return_path_sha256",
    }
)
_SIX_UNIVERSE_RUNTIME_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "profile_sha256",
        "package_id",
        "package_sha256",
        "symbol_resolution_id",
        "symbol_resolution_sha256",
        "runtime_slice_count",
        "pit_history_call_count",
        "pit_source_row_count",
        "price_history_call_count",
        "result_transport",
        "host_object_store_export_required",
        "backtest_only",
        "orders",
        "deployment",
        "trading",
    }
)
_CELL_COUNT_FIELDS = (
    "eligible_score_row_count",
    "accepted_outcome_pair_count",
    "missing_outcome_pair_count",
    "sector_refused_row_count",
    "valid_ic_date_count",
    "invalid_ic_date_count",
)
_REGIME_MISSING_COUNT_FIELDS = (
    "benchmark_endpoint_unavailable_pair_count",
    "named_figi_resolution_refusal_pair_count",
    "security_entry_unavailable_pair_count",
    "membership_ended_by_exit_with_exit_unavailable_pair_count",
    "within_membership_exit_unavailable_pair_count",
)
_CELL_METRIC_FIELDS = (
    "mean_daily_spearman_ic",
    "median_daily_spearman_ic",
    "positive_ic_date_share",
    "mean_of_daily_cross_section_mean_excess_returns",
    "median_of_daily_cross_section_mean_excess_returns",
)
_REGIME_PROFILE_NAME_TOKENS = (
    ("arv2-stock-ic-2019-2023", "2019_2023"),
    ("arv2-stock-ic-2023-2025", "2023_2025"),
    ("arv2-stock-ic-2013-2019", "2013_2019"),
)
_EXPECTED_OUTCOME_AVAILABILITY_DISCLOSURES = (
    ("reported_ic_conditioned_on_endpoint_price_availability", True),
    (
        "endpoint_price_conditioning",
        "security_and_benchmark_entry_and_exit_prices_required",
    ),
    ("endpoint_price_conditioning_direction", "unknown"),
    ("missing_pair_categories_mutually_exclusive", True),
    (
        "missing_pair_classification_precedence",
        (
            "benchmark_endpoint_then_named_figi_refusal_then_security_entry_"
            "then_exit_membership_state"
        ),
    ),
    ("membership_ended_by_exit_is_confirmed_terminal", False),
    (
        "membership_ended_by_exit_interpretation",
        "membership_end_is_not_a_confirmed_terminal_or_terminal_payoff",
    ),
    ("terminal_payoff_policy_applied", False),
)
_DECIMAL_METRIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def _authenticated_evaluator_manifest(plan) -> dict[str, object]:
    observed = None
    for descriptor, payload in _PINNED_ITER_UPLOADS(plan.package):
        if descriptor.role != "evaluator_manifest":
            continue
        if observed is not None or not payload.endswith(b"\n"):
            _error("authenticated evaluator manifest inventory changed")
        observed = _strict_object(payload[:-1], "authenticated evaluator manifest")
    if (
        type(observed) is not dict
        or observed.get("manifest_id") != plan.evaluator_manifest_id
        or observed.get("manifest_sha256") != plan.evaluator_manifest_sha256
    ):
        _error("authenticated evaluator manifest lineage changed")
    return observed


def _cell_metric(value: object, name: str) -> Decimal:
    if type(value) is not str or _DECIMAL_METRIC.fullmatch(value) is None:
        _error(f"preliminary {name} is not canonical finite Decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"preliminary {name} is not canonical finite Decimal text"
        ) from exc
    if (
        not parsed.is_finite()
        or format(parsed, "f") != value
        or (parsed == 0 and value != "0")
    ):
        _error(f"preliminary {name} is not canonical finite Decimal text")
    return parsed


def _outcome_availability_disclosures() -> dict[str, object]:
    expected = dict(_EXPECTED_OUTCOME_AVAILABILITY_DISCLOSURES)
    observed = dict(regime_evaluator.OUTCOME_AVAILABILITY_DISCLOSURES)
    if observed != expected:
        _error("preliminary regime outcome disclosure contract changed")
    return expected


def _validate_cell_semantics(record: dict[str, object]) -> int:
    if any(
        type(record.get(name)) is not int or record[name] < 0
        for name in _CELL_COUNT_FIELDS
    ):
        _error("preliminary aggregate cell count changed")
    eligible = record["eligible_score_row_count"]
    accepted = record["accepted_outcome_pair_count"]
    missing = record["missing_outcome_pair_count"]
    sector_refused = record["sector_refused_row_count"]
    valid = record["valid_ic_date_count"]
    invalid = record["invalid_ic_date_count"]
    if (
        eligible != accepted + missing
        or accepted < valid * preliminary_evaluator.MINIMUM_IC_ROWS
        or (sector_refused > 0 and invalid == 0)
    ):
        _error("preliminary aggregate cell count invariants changed")
    expected_status = (
        "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
        if valid >= 50
        else "INCONCLUSIVE_UNDERFILLED"
    )
    if record.get("status") != expected_status:
        _error("preliminary aggregate cell status changed")
    metrics = tuple(record.get(name) for name in _CELL_METRIC_FIELDS)
    if valid == 0:
        if any(value is not None for value in metrics):
            _error("preliminary aggregate cell unavailable metrics changed")
    else:
        if any(value is None for value in metrics):
            _error("preliminary aggregate cell available metrics changed")
        parsed = tuple(
            _cell_metric(value, name)
            for name, value in zip(_CELL_METRIC_FIELDS, metrics, strict=True)
        )
        if (
            not Decimal("-1") <= parsed[0] <= Decimal("1")
            or not Decimal("-1") <= parsed[1] <= Decimal("1")
            or not Decimal("0") <= parsed[2] <= Decimal("1")
        ):
            _error("preliminary aggregate cell bounded metric changed")
    return valid + invalid


def _require_runtime_meta(
    runtime_meta: object,
    plan: AcceptedRiskPreliminarySubmissionPlan,
    profile: dict[str, object] | None,
) -> dict[str, object]:
    expected_fields = (
        _RUNTIME_META_FIELDS if profile is None else _REGIME_RUNTIME_META_FIELDS
    )
    expected_schema = (
        "arv2-accepted-risk-preliminary-qc-runtime-meta-v1"
        if profile is None
        else "arv2-accepted-risk-regime-qc-runtime-meta-v1"
    )
    slice_field = "training_slice_count" if profile is None else "runtime_slice_count"
    if (
        type(runtime_meta) is not dict
        or set(runtime_meta) != expected_fields
        or runtime_meta.get("schema") != expected_schema
        or runtime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY_COMPLETED"
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "preliminary symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "preliminary symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "point_in_time",
                "formal",
                "control_residualized",
                "economic_portfolio",
                "etf_or_leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
        or type(runtime_meta.get("resolved_security_count")) is not int
        or type(runtime_meta.get("named_security_refusal_count")) is not int
        or runtime_meta["resolved_security_count"] < 0
        or runtime_meta["named_security_refusal_count"] < 0
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
        or type(runtime_meta.get(slice_field)) is not int
        or not 1
        <= runtime_meta[slice_field]
        <= _PINNED_MAX_TRAIN_SLICE_COUNT
        or (
            profile is not None
            and (
                runtime_meta.get("evaluation_profile_id")
                != profile["profile_id"]
                or runtime_meta.get("evaluation_profile_sha256")
                != profile["profile_sha256"]
            )
        )
    ):
        _error("preliminary runtime aggregate metadata changed")
    return runtime_meta


def _validate_legacy_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    runtime_meta = records.get("ARV2_RUNTIME_META")
    preliminary_meta = records.get("ARV2_PRELIMINARY_META")
    if type(runtime_meta) is not dict or type(preliminary_meta) is not dict:
        _error("preliminary aggregate metadata is absent")
    _require_runtime_meta(runtime_meta, plan, None)
    if (
        set(preliminary_meta) != _PRELIMINARY_META_FIELDS
    ):
        _error("preliminary evaluator aggregate metadata changed")
    cells_by_axis = {}
    date_geometry: dict[str, set[int]] = {}
    score_geometry: dict[tuple[str, str], set[tuple[int, int]]] = {}
    for name, record in records.items():
        match = _CELL_NAME.fullmatch(name)
        if match is None:
            continue
        if type(record) is not dict or set(record) != _CELL_FIELDS:
            _error("preliminary aggregate cell fields changed")
        view_token, arm_token, horizon_text, window_token = match.groups()
        expected_view = preliminary_evaluator.SOURCE_VIEW_IDS[
            0 if view_token == "CUR" else 1
        ]
        expected_arm = "firm_specific" if arm_token == "FIRM" else "global_comparator"
        expected_horizon = int(horizon_text)
        expected_window = (
            preliminary_evaluator.PRIMARY_WINDOW["window_id"]
            if window_token == "2020_2025"
            else preliminary_evaluator.DESCRIPTIVE_WINDOW["window_id"]
        )
        if (
            record.get("schema") != preliminary_evaluator.CELL_SCHEMA
            or record.get("source_view_id") != expected_view
            or record.get("score_arm") != expected_arm
            or record.get("horizon_sessions") != expected_horizon
            or record.get("window_id") != expected_window
            or record.get("outcome_definition")
            != preliminary_evaluator.HISTORY_OBSERVATION
            or record.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary aggregate cell axis changed")
        date_geometry.setdefault(expected_window, set()).add(
            _validate_cell_semantics(record)
        )
        score_geometry.setdefault((expected_window, expected_view), set()).add(
            (
                record["eligible_score_row_count"],
                record["sector_refused_row_count"],
            )
        )
        cells_by_axis[(expected_window, expected_view, expected_arm, expected_horizon)] = record
    expected_axes = tuple(
        (window["window_id"], view, arm, horizon)
        for window in preliminary_evaluator.WINDOWS
        for view in preliminary_evaluator.SOURCE_VIEW_IDS
        for arm in preliminary_evaluator.SCORE_ARMS
        for horizon in preliminary_evaluator.HORIZONS
    )
    if set(cells_by_axis) != set(expected_axes):
        _error("preliminary aggregate cell inventory changed")
    if any(len(values) != 1 for values in date_geometry.values()) or any(
        len(values) != 1 for values in score_geometry.values()
    ):
        _error("preliminary aggregate cell geometry changed")
    if (
        preliminary_meta.get("schema") != preliminary_evaluator.SUMMARY_SCHEMA
        or preliminary_meta.get("contract_id") != preliminary_evaluator.CONTRACT_ID
        or preliminary_meta.get("manifest_id") != plan.evaluator_manifest_id
        or preliminary_meta.get("manifest_sha256") != plan.evaluator_manifest_sha256
        or preliminary_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY"
        or preliminary_meta.get("windows")
        != [dict(item) for item in preliminary_evaluator.WINDOWS]
        or preliminary_meta.get("source_view_ids")
        != list(preliminary_evaluator.SOURCE_VIEW_IDS)
        or preliminary_meta.get("score_arms")
        != list(preliminary_evaluator.SCORE_ARMS)
        or preliminary_meta.get("horizons")
        != list(preliminary_evaluator.HORIZONS)
        or preliminary_meta.get("outcome_definition")
        != preliminary_evaluator.HISTORY_OBSERVATION
        or preliminary_meta.get("history_normalization_mode") != "TOTAL_RETURN"
        or preliminary_meta.get("history_value_field") != "open"
        or preliminary_meta.get("decay_state_method")
        != (
            "sparse_positive_common_scale_mathematically_equivalent_"
            "not_byte_identical_to_formal_per_event_replay"
        )
        or preliminary_meta.get("benchmark_role")
        != "matching_SPY_open_to_open_total_return"
        or preliminary_meta.get("q_data_policy_id")
        != preliminary_evaluator.Q_DATA_POLICY_ID
        or preliminary_meta.get("accepted_risk_disclosures")
        != dict(preliminary_evaluator.ACCEPTED_RISK_DISCLOSURES)
        or preliminary_meta.get("omitted_formal_components")
        != list(preliminary_evaluator.OMITTED_FORMAL_COMPONENTS)
        or any(
            type(preliminary_meta.get(name)) is not int
            or preliminary_meta[name] < 0
            for name in (
                "input_security_count", "input_contribution_count",
                "completed_callback_count",
            )
        )
        or preliminary_meta.get("input_security_count")
        != plan.package.runtime_symbol_binding_count
        or preliminary_meta.get("input_contribution_count")
        != authenticated_manifest.get("contribution_row_count")
        or preliminary_meta.get("completed_callback_count") == 0
        or preliminary_meta.get("formal_result") is not False
        or preliminary_meta.get("alpha_claim_authorized") is not False
        or any(
            preliminary_meta.get(name) is not False
            for name in (
                "raw_provider_rows_in_summary",
                "raw_security_outcome_rows_in_summary",
                "raw_price_rows_in_summary",
            )
        )
    ):
        _error("preliminary evaluator aggregate metadata changed")
    lineage = preliminary_meta.get("source_lineage_sha256s")
    if (
        type(lineage) is not dict
        or set(lineage) != set(preliminary_evaluator._SOURCE_LINEAGE_FIELDS)
        or any(_sha(lineage[name], name) != lineage[name] for name in lineage)
        or lineage != authenticated_manifest.get("source_lineage_sha256s")
    ):
        _error("preliminary evaluator source lineage changed")
    summary_id = preliminary_meta.get("summary_id")
    summary_sha = preliminary_meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary evaluator summary identity is absent")
    record = {
        key: value
        for key, value in preliminary_meta.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    record["cells"] = [cells_by_axis[axis] for axis in expected_axes]
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if summary_sha != digest or summary_id != "arv2-preliminary-rating-summary-" + digest[:24]:
        _error("preliminary evaluator summary identity changed")


def _regime_axis_inventory(evaluation_profile_id: str):
    profile = _PINNED_REQUIRE_REGIME_PROFILE(evaluation_profile_id)
    token = next(
        (
            candidate
            for profile_id, candidate in _REGIME_PROFILE_NAME_TOKENS
            if profile_id == evaluation_profile_id
        ),
        None,
    )
    if token is None:
        _error("preliminary evaluation profile is not allowlisted")
    axes = tuple(
        (
            "ARV2_REGIME_"
            + token
            + "_"
            + ("CUR" if view == preliminary_evaluator.SOURCE_VIEW_IDS[0] else "CEN")
            + "_"
            + ("FIRM" if arm == "firm_specific" else "GLOBAL")
            + "_H"
            + str(horizon),
            (view, arm, horizon),
        )
        for view in preliminary_evaluator.SOURCE_VIEW_IDS
        for arm in preliminary_evaluator.SCORE_ARMS
        for horizon in preliminary_evaluator.HORIZONS
    )
    meta_name = "ARV2_REGIME_" + token + "_META"
    expected_names = _expected_result_names(evaluation_profile_id)
    if set(expected_names) != {
        "ARV2_RUNTIME_META",
        meta_name,
        *(name for name, _axis in axes),
    }:
        _error("preliminary regime result-name binding changed")
    return profile, meta_name, axes


def _validate_regime_cell_semantics(record: dict[str, object]) -> int:
    date_count = _validate_cell_semantics(record)
    if (
        any(
            type(record.get(name)) is not int or record[name] < 0
            for name in _REGIME_MISSING_COUNT_FIELDS
        )
        or sum(record[name] for name in _REGIME_MISSING_COUNT_FIELDS)
        != record["missing_outcome_pair_count"]
        or record.get("missing_pair_counter_sum_matches_total") is not True
    ):
        _error("preliminary regime missing-outcome census changed")
    disclosures = _outcome_availability_disclosures()
    if (
        record.get("endpoint_price_conditioning")
        != disclosures["endpoint_price_conditioning"]
        or record.get("membership_ended_by_exit_interpretation")
        != disclosures["membership_ended_by_exit_interpretation"]
    ):
        _error("preliminary regime outcome conditioning changed")
    return date_count


def _validate_regime_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
    evaluation_profile_id: str,
) -> None:
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    profile, meta_name, named_axes = _regime_axis_inventory(
        evaluation_profile_id
    )
    runtime_meta = _require_runtime_meta(
        records.get("ARV2_RUNTIME_META"), plan, profile
    )
    regime_meta = records.get(meta_name)
    if type(regime_meta) is not dict or set(regime_meta) != _REGIME_META_FIELDS:
        _error("preliminary regime aggregate metadata changed")

    cells_by_axis = {}
    date_geometry: set[int] = set()
    score_geometry: dict[str, set[tuple[int, int]]] = {}
    availability_geometry: dict[
        tuple[str, int], set[tuple[int, ...]]
    ] = {}
    for name, axis in named_axes:
        record = records.get(name)
        if type(record) is not dict or set(record) != _REGIME_CELL_FIELDS:
            _error("preliminary regime aggregate cell fields changed")
        view, arm, horizon = axis
        if (
            record.get("schema") != regime_evaluator.REGIME_CELL_SCHEMA
            or record.get("source_view_id") != view
            or record.get("score_arm") != arm
            or record.get("horizon_sessions") != horizon
            or record.get("profile_id") != evaluation_profile_id
            or record.get("window_start_session") != profile["start_session"]
            or record.get("window_end_session") != profile["end_session"]
            or record.get("outcome_definition")
            != preliminary_evaluator.HISTORY_OBSERVATION
            or record.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary regime aggregate cell axis changed")
        date_geometry.add(_validate_regime_cell_semantics(record))
        score_geometry.setdefault(view, set()).add(
            (
                record["eligible_score_row_count"],
                record["sector_refused_row_count"],
            )
        )
        availability_geometry.setdefault((view, horizon), set()).add(
            tuple(record[field] for field in _REGIME_MISSING_COUNT_FIELDS)
        )
        cells_by_axis[axis] = record
    expected_axes = tuple(axis for _name, axis in named_axes)
    if (
        set(cells_by_axis) != set(expected_axes)
        or len(date_geometry) != 1
        or date_geometry != {profile["expected_session_count"]}
        or any(len(values) != 1 for values in score_geometry.values())
        or any(len(values) != 1 for values in availability_geometry.values())
        or (
            runtime_meta["named_security_refusal_count"] == 0
            and any(
                record["named_figi_resolution_refusal_pair_count"] != 0
                for record in cells_by_axis.values()
            )
        )
    ):
        _error("preliminary regime aggregate cell geometry changed")

    disclosures = _outcome_availability_disclosures()
    if (
        regime_meta.get("schema") != regime_evaluator.REGIME_SUMMARY_SCHEMA
        or regime_meta.get("contract_id") != regime_evaluator.REGIME_CONTRACT_ID
        or regime_meta.get("input_contract_id")
        != preliminary_evaluator.CONTRACT_ID
        or regime_meta.get("manifest_id") != plan.evaluator_manifest_id
        or regime_meta.get("manifest_sha256") != plan.evaluator_manifest_sha256
        or regime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_REGIME_ONLY"
        or regime_meta.get("profile") != profile
        or regime_meta.get("source_view_ids")
        != list(preliminary_evaluator.SOURCE_VIEW_IDS)
        or regime_meta.get("score_arms")
        != list(preliminary_evaluator.SCORE_ARMS)
        or regime_meta.get("horizons")
        != list(preliminary_evaluator.HORIZONS)
        or regime_meta.get("outcome_definition")
        != preliminary_evaluator.HISTORY_OBSERVATION
        or regime_meta.get("history_normalization_mode") != "TOTAL_RETURN"
        or regime_meta.get("history_value_field") != "open"
        or regime_meta.get("decay_state_method")
        != (
            "R055_sparse_positive_common_scale_mathematically_equivalent_"
            "not_byte_identical_to_formal_per_event_replay"
        )
        or regime_meta.get("benchmark_role")
        != "matching_SPY_open_to_open_total_return"
        or regime_meta.get("q_data_policy_id")
        != preliminary_evaluator.Q_DATA_POLICY_ID
        or regime_meta.get("outcome_availability_disclosures") != disclosures
        or regime_meta.get("accepted_risk_disclosures")
        != dict(preliminary_evaluator.ACCEPTED_RISK_DISCLOSURES)
        or any(
            type(regime_meta.get(name)) is not int
            or regime_meta[name] < 0
            for name in (
                "input_security_count",
                "input_contribution_count",
                "named_figi_resolution_refusal_count",
                "completed_callback_count",
            )
        )
        or regime_meta.get("input_security_count")
        != plan.package.runtime_symbol_binding_count
        or regime_meta.get("input_contribution_count")
        != authenticated_manifest.get("contribution_row_count")
        or regime_meta.get("named_figi_resolution_refusal_count")
        != runtime_meta["named_security_refusal_count"]
        or regime_meta.get("completed_callback_count") == 0
        or regime_meta.get("r055_signal_rule_changed") is not False
        or regime_meta.get("terminal_payoff_applied") is not False
        or regime_meta.get("economic_portfolio_evaluation") is not False
        or regime_meta.get("formal_result") is not False
        or regime_meta.get("alpha_claim_authorized") is not False
        or any(
            regime_meta.get(name) is not False
            for name in (
                "raw_provider_rows_in_summary",
                "raw_security_outcome_rows_in_summary",
                "raw_price_rows_in_summary",
            )
        )
    ):
        _error("preliminary regime evaluator aggregate metadata changed")
    lineage = regime_meta.get("source_lineage_sha256s")
    if (
        type(lineage) is not dict
        or set(lineage) != set(preliminary_evaluator._SOURCE_LINEAGE_FIELDS)
        or any(_sha(lineage[name], name) != lineage[name] for name in lineage)
        or lineage != authenticated_manifest.get("source_lineage_sha256s")
    ):
        _error("preliminary regime evaluator source lineage changed")
    summary_id = regime_meta.get("summary_id")
    summary_sha = regime_meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary regime evaluator summary identity is absent")
    record = {
        key: value
        for key, value in regime_meta.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    record["cells"] = [cells_by_axis[axis] for axis in expected_axes]
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-regime-rating-summary-" + digest[:24]
    ):
        _error("preliminary regime evaluator summary identity changed")


def _validate_etf_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile = etf_evaluator.require_etf_baseline_profile(
        etf_evaluator.PROFILE_ID
    )
    runtime_meta = records.get("ARV2_RUNTIME_META")
    if (
        type(runtime_meta) is not dict
        or set(runtime_meta) != _ETF_RUNTIME_META_FIELDS
        or runtime_meta.get("schema")
        != "arv2-accepted-risk-etf-sector-qc-runtime-meta-v1"
        or runtime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_UNLEVERED_ETF_BASELINE_COMPLETED"
        or runtime_meta.get("profile_id") != etf_evaluator.PROFILE_ID
        or runtime_meta.get("profile_sha256") != profile["profile_sha256"]
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "ETF symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "ETF symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or runtime_meta.get("candidate_etf_count")
        != len(etf_evaluator.CANDIDATE_ETFS)
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or runtime_meta.get("economic_portfolio") is not True
        or runtime_meta.get("etf") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "point_in_time",
                "formal",
                "control_residualized",
                "leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
        or any(
            type(runtime_meta.get(name)) is not int
            or runtime_meta[name] < 0
            for name in (
                "resolved_security_count",
                "named_security_refusal_count",
            )
        )
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
    ):
        _error("preliminary ETF runtime metadata changed")

    meta = records.get("ARV2_ETF_2021_2025_META")
    if type(meta) is not dict or set(meta) != _ETF_META_FIELDS:
        _error("preliminary ETF aggregate metadata changed")
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    count_fields = (
        "decision_session_count",
        "portfolio_return_session_count",
        "invested_return_session_count",
        "selected_decision_session_count",
        "holdings_snapshot_refusal_count",
        "stale_holdings_snapshot_refusal_count",
        "holdings_completeness_refusal_count",
        "mapping_refusal_count",
        "liquidity_refusal_count",
        "stock_sector_refusal_session_count",
    )
    if (
        meta.get("schema") != etf_evaluator.SUMMARY_SCHEMA
        or meta.get("contract_id") != etf_evaluator.CONTRACT_ID
        or meta.get("profile") != profile
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("input_manifest_id") != plan.evaluator_manifest_id
        or meta.get("input_manifest_sha256")
        != plan.evaluator_manifest_sha256
        or meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_UNLEVERED_ETF_BASELINE"
        or any(
            type(meta.get(name)) is not int or meta[name] < 0
            for name in count_fields
        )
        or meta["decision_session_count"] == 0
        or meta["portfolio_return_session_count"] < 252
        or meta["invested_return_session_count"]
        > meta["portfolio_return_session_count"]
        or meta["selected_decision_session_count"]
        > meta["decision_session_count"]
        or meta["stale_holdings_snapshot_refusal_count"]
        > meta["holdings_snapshot_refusal_count"]
        or meta.get("holdings_source")
        != "QuantConnect_US_ETF_Constituents"
        or meta.get("holdings_point_in_time_claim")
        != "QC_callback_observation_from_exact_previous_authenticated_session"
        or meta.get("fixed_sleeve_is_exhaustive_reverse_index") is not False
        or meta.get("aum_filter_applied") is not False
        or meta.get("aum_filter_omission")
        != "no_reliable_point_in_time_AUM_input"
        or meta.get("peer_normalization")
        != "global_fixed_sleeve_percentile"
        or meta.get("direct_stock_comparator_present") is not False
        or meta.get("industry_comparator_present") is not False
        or meta.get("market_benchmark_present") is not True
        or meta.get("terminal_payoff_applied") is not False
        or meta.get("current_vintage_non_pristine_pit_input") is not True
        or meta.get("economic_portfolio_evaluation") is not True
        or any(
            meta.get(name) is not False
            for name in (
                "raw_provider_rows_in_summary",
                "raw_constituent_rows_in_summary",
                "raw_price_rows_in_summary",
                "formal_result",
                "alpha_claim_authorized",
                "leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
        or authenticated_manifest.get("manifest_id")
        != meta.get("input_manifest_id")
    ):
        _error("preliminary ETF aggregate metadata semantics changed")
    for name in ("mean_eligible_etf_count", "mean_selected_etf_count"):
        parsed = _cell_metric(meta.get(name), name)
        upper = (
            etf_evaluator.MAXIMUM_HOLDINGS
            if name == "mean_selected_etf_count"
            else len(etf_evaluator.CANDIDATE_ETFS)
        )
        if parsed < 0 or parsed > upper:
            _error("preliminary ETF mean count is out of bounds")

    ic_cells = []
    for horizon in etf_evaluator.HORIZONS:
        cell = records.get("ARV2_ETF_IC_H" + str(horizon))
        if type(cell) is not dict or set(cell) != _ETF_IC_FIELDS:
            _error("preliminary ETF IC cell fields changed")
        valid = cell.get("valid_ic_date_count")
        invalid = cell.get("invalid_ic_date_count")
        accepted = cell.get("accepted_outcome_pair_count")
        missing = cell.get("missing_outcome_pair_count")
        if (
            cell.get("schema") != etf_evaluator.IC_CELL_SCHEMA
            or cell.get("profile_id") != etf_evaluator.PROFILE_ID
            or cell.get("horizon_sessions") != horizon
            or any(
                type(value) is not int or value < 0
                for value in (valid, invalid, accepted, missing)
            )
            or cell.get("status")
            != (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if valid >= 50
                else "INCONCLUSIVE_UNDERFILLED"
            )
            or cell.get("entry_timing") != "next_session_open"
            or cell.get("benchmark")
            != "SPY_total_return_adjusted_open_to_open"
            or cell.get("formal_accept_reject_disposition") is not None
            or valid + invalid != meta["decision_session_count"]
        ):
            _error("preliminary ETF IC cell semantics changed")
        metrics = (
            cell.get("mean_daily_spearman_ic"),
            cell.get("median_daily_spearman_ic"),
            cell.get("positive_ic_date_share"),
        )
        if valid == 0:
            if any(value is not None for value in metrics):
                _error("preliminary ETF unavailable IC metrics changed")
        else:
            parsed = tuple(
                _cell_metric(value, "ETF IC metric") for value in metrics
            )
            if (
                not Decimal("-1") <= parsed[0] <= Decimal("1")
                or not Decimal("-1") <= parsed[1] <= Decimal("1")
                or not Decimal("0") <= parsed[2] <= Decimal("1")
            ):
                _error("preliminary ETF IC metric escaped bounds")
        ic_cells.append(cell)

    portfolio_cells = []
    spy_values = set()
    cumulative_by_cost = {}
    for cost in etf_evaluator.COST_BPS_SCENARIOS:
        cell = records.get("ARV2_ETF_PORTFOLIO_COST_" + str(cost))
        if type(cell) is not dict or set(cell) != _ETF_PORTFOLIO_FIELDS:
            _error("preliminary ETF portfolio cell fields changed")
        if (
            cell.get("schema") != etf_evaluator.PORTFOLIO_CELL_SCHEMA
            or cell.get("profile_id") != etf_evaluator.PROFILE_ID
            or cell.get("cost_bps_per_side") != cost
            or cell.get("primary_cost_scenario")
            is not (cost == etf_evaluator.PRIMARY_COST_BPS)
            or cell.get("status")
            != (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if (
                    meta["portfolio_return_session_count"] >= 252
                    and meta["invested_return_session_count"]
                    >= etf_evaluator.MINIMUM_INVESTED_RETURN_SESSIONS
                )
                else "INCONCLUSIVE_UNDERFILLED"
            )
            or cell.get("return_session_count")
            != meta["portfolio_return_session_count"]
            or cell.get("invested_return_session_count")
            != meta["invested_return_session_count"]
            or cell.get("leverage") is not False
            or cell.get("orders_submitted") != 0
            or cell.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary ETF portfolio cell semantics changed")
        decimal_names = (
            "cumulative_return",
            "spy_cumulative_return",
            "cumulative_return_minus_spy",
            "annualized_arithmetic_return",
            "annualized_volatility",
            "maximum_drawdown",
            "average_daily_two_sided_turnover",
            "average_cash_weight",
        )
        parsed = {
            name: _cell_metric(cell.get(name), "ETF " + name)
            for name in decimal_names
        }
        for name in ("zero_rate_sharpe", "zero_rate_sortino"):
            value = cell.get(name)
            parsed[name] = (
                None
                if value is None
                else _cell_metric(value, "ETF " + name)
            )
        with localcontext(preliminary_evaluator._context()):
            exact_excess = +(
                parsed["cumulative_return"]
                - parsed["spy_cumulative_return"]
            )
        if (
            parsed["cumulative_return"] <= Decimal("-1")
            or parsed["spy_cumulative_return"] <= Decimal("-1")
            or parsed["cumulative_return_minus_spy"]
            != exact_excess
            or parsed["annualized_volatility"] < 0
            or not Decimal("-1") <= parsed["maximum_drawdown"] <= 0
            or parsed["average_daily_two_sided_turnover"] < 0
            or not Decimal("0") <= parsed["average_cash_weight"] <= 1
        ):
            _error("preliminary ETF portfolio metric escaped bounds")
        spy_values.add(cell["spy_cumulative_return"])
        cumulative_by_cost[cost] = parsed["cumulative_return"]
        portfolio_cells.append(cell)
    if len(spy_values) != 1 or any(
        cumulative_by_cost[left] < cumulative_by_cost[right]
        for left, right in zip(
            etf_evaluator.COST_BPS_SCENARIOS,
            etf_evaluator.COST_BPS_SCENARIOS[1:],
        )
    ):
        _error("preliminary ETF cost-scenario ordering changed")

    summary_id = meta.get("summary_id")
    summary_sha = meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary ETF summary identity is absent")
    record = {
        key: value
        for key, value in meta.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    record["ic_cells"] = ic_cells
    record["portfolio_cells"] = portfolio_cells
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-etf-sector-baseline-summary-" + digest[:24]
    ):
        _error("preliminary ETF evaluator summary identity changed")


def _validate_stock_portfolio_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile_id = plan.projection.evaluation_profile_id
    profile_bytes, profile_sha256, _result_names = (
        _stock_portfolio_profile_binding(profile_id)
    )
    if (
        plan.evaluation_profile_id != profile_id
        or plan.evaluation_profile_sha256 != profile_sha256
        or plan.projection.evaluation_profile_sha256 != profile_sha256
    ):
        _error("preliminary stock-portfolio plan profile binding changed")
    runtime_meta = records.get("ARV2_RUNTIME_META")
    if (
        type(runtime_meta) is not dict
        or set(runtime_meta) != _STOCK_PORTFOLIO_RUNTIME_META_FIELDS
        or runtime_meta.get("schema")
        != "arv2-accepted-risk-stock-portfolio-qc-runtime-meta-v1"
        or runtime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO_COMPLETED"
        or runtime_meta.get("evaluation_profile_id")
        != profile_id
        or runtime_meta.get("evaluation_profile_sha256")
        != profile_sha256
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "stock portfolio symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "stock portfolio symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or runtime_meta.get("economic_portfolio") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "point_in_time",
                "formal",
                "control_residualized",
                "etf_or_leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
        or any(
            type(runtime_meta.get(name)) is not int
            or runtime_meta[name] < 0
            for name in (
                "resolved_security_count",
                "named_security_refusal_count",
                "runtime_slice_count",
            )
        )
        or runtime_meta["runtime_slice_count"] == 0
        or runtime_meta["runtime_slice_count"]
        > _PINNED_MAX_TRAIN_SLICE_COUNT
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
    ):
        _error("preliminary stock-portfolio runtime metadata changed")

    meta = records.get("ARV2_STOCK_PORTFOLIO_META")
    if type(meta) is not dict or set(meta) != _STOCK_PORTFOLIO_META_FIELDS:
        _error("preliminary stock-portfolio aggregate metadata changed")
    count_fields = (
        "decision_session_count",
        "portfolio_return_session_count",
        "invested_return_session_count",
        "signal_selected_decision_count",
        "selected_execution_count",
        "rebalance_execution_count",
        "full_target_execution_count",
        "underfilled_target_execution_count",
        "matched_rebalance_execution_count",
        "matched_target_met_execution_count",
        "matched_underfilled_target_execution_count",
        "sector_refused_decision_count",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "deferred_rebalance_count",
        "partial_rebalance_decision_count",
        "stale_position_deferral_count",
        "locked_exposure_over_target_count",
        "membership_end_liquidation_count",
        "membership_end_zero_recovery_count",
        "membership_end_entry_refusal_count",
        "matched_entry_price_refusal_count",
        "matched_stale_mark_session_count",
        "matched_deferred_rebalance_count",
        "matched_partial_rebalance_decision_count",
        "matched_stale_position_deferral_count",
        "matched_locked_exposure_over_target_count",
        "matched_membership_end_liquidation_count",
        "matched_membership_end_zero_recovery_count",
        "matched_membership_end_entry_refusal_count",
        "named_figi_resolution_refusal_count",
    )
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    if (
        meta.get("schema") != _PINNED_STOCK_PORTFOLIO_SUMMARY_SCHEMA
        or meta.get("contract_id") != _PINNED_STOCK_PORTFOLIO_CONTRACT_ID
        or meta.get("profile_id") != profile_id
        or meta.get("profile_sha256")
        != profile_sha256
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("input_manifest_id") != plan.evaluator_manifest_id
        or meta.get("input_manifest_sha256") != plan.evaluator_manifest_sha256
        or meta.get("input_manifest_id")
        != authenticated_manifest.get("manifest_id")
        or meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO"
        or any(
            type(meta.get(name)) is not int or meta[name] < 0
            for name in count_fields
        )
        or meta["decision_session_count"] == 0
        or meta["decision_session_count"]
        != _PINNED_STOCK_PORTFOLIO_EXPECTED_DECISIONS
        or meta["portfolio_return_session_count"]
        != _PINNED_STOCK_PORTFOLIO_EXPECTED_RETURNS
        or meta["invested_return_session_count"]
        > meta["portfolio_return_session_count"]
        or meta["signal_selected_decision_count"]
        > meta["decision_session_count"]
        or meta["selected_execution_count"]
        > meta["signal_selected_decision_count"]
        or meta["selected_execution_count"]
        > meta["rebalance_execution_count"]
        or meta["full_target_execution_count"]
        > meta["selected_execution_count"]
        or meta["full_target_execution_count"]
        + meta["underfilled_target_execution_count"]
        + meta["locked_exposure_over_target_count"]
        != meta["rebalance_execution_count"]
        or meta["rebalance_execution_count"] != meta["decision_session_count"]
        or meta["deferred_rebalance_count"] != 0
        or meta["matched_target_met_execution_count"]
        + meta["matched_underfilled_target_execution_count"]
        + meta["matched_locked_exposure_over_target_count"]
        != meta["matched_rebalance_execution_count"]
        or meta["matched_rebalance_execution_count"]
        != meta["decision_session_count"]
        or meta["matched_deferred_rebalance_count"] != 0
        or meta["partial_rebalance_decision_count"]
        > meta["rebalance_execution_count"]
        or meta["matched_partial_rebalance_decision_count"]
        > meta["matched_rebalance_execution_count"]
        or meta["partial_rebalance_decision_count"]
        > meta["stale_mark_session_count"]
        or meta["matched_partial_rebalance_decision_count"]
        > meta["matched_stale_mark_session_count"]
        or meta["stale_mark_session_count"]
        > meta["portfolio_return_session_count"]
        or meta["matched_stale_mark_session_count"]
        > meta["portfolio_return_session_count"]
        or meta["stale_position_deferral_count"]
        < meta["partial_rebalance_decision_count"]
        or meta["matched_stale_position_deferral_count"]
        < meta["matched_partial_rebalance_decision_count"]
        or (meta["partial_rebalance_decision_count"] == 0)
        is not (meta["stale_position_deferral_count"] == 0)
        or (meta["matched_partial_rebalance_decision_count"] == 0)
        is not (meta["matched_stale_position_deferral_count"] == 0)
        or meta["stale_position_deferral_count"]
        > (
            meta["partial_rebalance_decision_count"]
            * plan.package.runtime_symbol_binding_count
        )
        or meta["matched_stale_position_deferral_count"]
        > (
            meta["matched_partial_rebalance_decision_count"]
            * plan.package.runtime_symbol_binding_count
        )
        or meta["locked_exposure_over_target_count"]
        > meta["partial_rebalance_decision_count"]
        or meta["matched_locked_exposure_over_target_count"]
        > meta["matched_partial_rebalance_decision_count"]
        or meta["sector_refused_decision_count"]
        > meta["decision_session_count"]
        or meta["membership_end_zero_recovery_count"]
        > meta["membership_end_liquidation_count"]
        or meta["matched_membership_end_zero_recovery_count"]
        > meta["matched_membership_end_liquidation_count"]
        or meta["named_figi_resolution_refusal_count"]
        != runtime_meta["named_security_refusal_count"]
        or meta.get("history_normalization_mode") != "TOTAL_RETURN"
        or meta.get("history_value_field") != "open"
        or meta.get("r055_signal_rule_changed") is not False
        or meta.get("liquidity_filter_applied") is not False
        or meta.get("terminal_payoff_applied") is not False
        or meta.get("membership_end_liquidation_is_terminal_payoff") is not False
        or meta.get("membership_end_missing_price_policy")
        != "zero_recovery_conservative_lower_bound"
        or meta.get("matched_exposure_targeted_to_signal_executed_gross")
        is not True
        or meta.get("current_vintage_non_pristine_pit_input") is not True
        or meta.get("economic_portfolio_evaluation") is not True
        or any(
            meta.get(name) is not False
            for name in (
                "raw_provider_rows_in_summary",
                "raw_security_outcome_rows_in_summary",
                "raw_price_rows_in_summary",
                "formal_result",
                "alpha_claim_authorized",
                "leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        _error("preliminary stock-portfolio aggregate metadata semantics changed")
    metric_bounds = (
        ("mean_eligible_score_count", Decimal(0), Decimal(plan.package.runtime_symbol_binding_count)),
        ("mean_selected_name_count", Decimal(0), Decimal(_PINNED_STOCK_PORTFOLIO_MAXIMUM_HOLDINGS)),
        ("mean_executed_target_gross_exposure", Decimal(0), Decimal(1)),
        ("matched_mean_executed_target_gross_exposure", Decimal(0), Decimal(1)),
        ("mean_locked_gross_at_partial_decisions", Decimal(0), Decimal(1)),
        ("matched_mean_locked_gross_at_partial_decisions", Decimal(0), Decimal(1)),
        ("average_holding_count", Decimal(0), Decimal(_PINNED_STOCK_PORTFOLIO_MAXIMUM_HOLDINGS)),
    )
    parsed_meta_metrics = {}
    for name, lower, upper in metric_bounds:
        parsed = _cell_metric(meta.get(name), "stock portfolio " + name)
        parsed_meta_metrics[name] = parsed
        if not lower <= parsed <= upper:
            _error("preliminary stock-portfolio mean count escaped bounds")
    signal_mean_gross = parsed_meta_metrics[
        "mean_executed_target_gross_exposure"
    ]
    matched_mean_gross = parsed_meta_metrics[
        "matched_mean_executed_target_gross_exposure"
    ]
    signal_mean_locked = parsed_meta_metrics[
        "mean_locked_gross_at_partial_decisions"
    ]
    matched_mean_locked = parsed_meta_metrics[
        "matched_mean_locked_gross_at_partial_decisions"
    ]
    rebalance_count = meta["rebalance_execution_count"]
    if rebalance_count == 0:
        invalid_target_means = signal_mean_gross != 0 or matched_mean_gross != 0
    else:
        with localcontext(preliminary_evaluator._context()):
            full_signal_floor = +(
                Decimal(meta["full_target_execution_count"])
                * Decimal("0.98")
                / Decimal(rebalance_count)
            )
        invalid_target_means = (
            signal_mean_gross < full_signal_floor
            or (meta["selected_execution_count"] == 0) is not (
                signal_mean_gross == 0
            )
            or (
                meta["underfilled_target_execution_count"] == 0
                and meta["locked_exposure_over_target_count"] == 0
                and signal_mean_gross != Decimal("0.98")
            )
            or (
                meta["underfilled_target_execution_count"] > 0
                and meta["locked_exposure_over_target_count"] == 0
                and signal_mean_gross >= Decimal("0.98")
            )
            or (
                meta["matched_rebalance_execution_count"] == 0
                and matched_mean_gross != 0
            )
            or (
                meta["matched_underfilled_target_execution_count"] == 0
                and meta["matched_locked_exposure_over_target_count"] == 0
                and matched_mean_gross != signal_mean_gross
            )
            or (
                meta["matched_underfilled_target_execution_count"] > 0
                and meta["matched_locked_exposure_over_target_count"] == 0
                and matched_mean_gross >= signal_mean_gross
            )
            or (meta["partial_rebalance_decision_count"] == 0)
            is not (signal_mean_locked == 0)
            or (meta["matched_partial_rebalance_decision_count"] == 0)
            is not (matched_mean_locked == 0)
        )
    with localcontext(preliminary_evaluator._context()):
        signal_target_gross_sum = +(
            signal_mean_gross * Decimal(rebalance_count)
        )
        matched_target_gross_sum = +(
            matched_mean_gross
            * Decimal(meta["matched_rebalance_execution_count"])
        )
        matched_locked_gross_sum = +(
            matched_mean_locked
            * Decimal(meta["matched_partial_rebalance_decision_count"])
        )
    invalid_target_means = (
        invalid_target_means
        or matched_target_gross_sum
        > signal_target_gross_sum + matched_locked_gross_sum
    )
    if invalid_target_means:
        _error("preliminary stock-portfolio target exposure changed")

    cells = []
    spy_values = set()
    signal_by_cost = {}
    matched_by_cost = {}
    signal_annual_by_cost = {}
    matched_annual_by_cost = {}
    path_invariants = {
        name: set()
        for name in (
            "average_daily_two_sided_turnover",
            "average_cash_weight",
            "matched_average_daily_two_sided_turnover",
            "matched_average_cash_weight",
        )
    }
    if (
        meta["portfolio_return_session_count"] < 252
        or meta["invested_return_session_count"]
        < _PINNED_STOCK_PORTFOLIO_MINIMUM_INVESTED_RETURNS
    ):
        expected_status = "INCONCLUSIVE_UNDERFILLED"
    elif (
        meta["membership_end_zero_recovery_count"]
        or meta["matched_membership_end_zero_recovery_count"]
    ):
        expected_status = (
            "PRELIMINARY_DESCRIPTIVE_LOWER_BOUND_WITH_ZERO_RECOVERY"
        )
    elif (
        meta["stale_mark_session_count"]
        or meta["matched_stale_mark_session_count"]
    ):
        expected_status = (
            "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
        )
    elif (
        meta["underfilled_target_execution_count"]
        or meta["matched_underfilled_target_execution_count"]
    ):
        expected_status = (
            "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_EXPOSURE_UNDERFILL"
        )
    else:
        expected_status = "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
    for cost in _PINNED_STOCK_PORTFOLIO_COSTS:
        cell = records.get("ARV2_STOCK_PORTFOLIO_COST_" + str(cost))
        if type(cell) is not dict or set(cell) != _STOCK_PORTFOLIO_CELL_FIELDS:
            _error("preliminary stock-portfolio cell fields changed")
        if (
            cell.get("schema")
            != _PINNED_STOCK_PORTFOLIO_CELL_SCHEMA
            or cell.get("profile_id") != profile_id
            or cell.get("cost_bps_per_side") != cost
            or cell.get("primary_cost_scenario")
            is not (cost == _PINNED_STOCK_PORTFOLIO_PRIMARY_COST)
            or cell.get("status") != expected_status
            or cell.get("return_metric_conditioning")
            != (
                "conditioned_on_zero_recovery_lower_bound_and_possible_"
                "stale_mark_path"
                if (
                    meta["membership_end_zero_recovery_count"]
                    or meta["matched_membership_end_zero_recovery_count"]
                )
                else (
                    "conditioned_on_stale_mark_path"
                    if (
                        meta["stale_mark_session_count"]
                        or meta["matched_stale_mark_session_count"]
                    )
                    else "no_price_proxy"
                )
            )
            or cell.get("risk_metrics_are_price_proxy_conditioned")
            is not (
                bool(
                    meta["stale_mark_session_count"]
                    or meta["membership_end_zero_recovery_count"]
                    or meta["matched_stale_mark_session_count"]
                    or meta["matched_membership_end_zero_recovery_count"]
                )
            )
            or cell.get("exposure_underfill_present")
            is not bool(
                meta["underfilled_target_execution_count"]
                or meta["matched_underfilled_target_execution_count"]
            )
            or cell.get("return_session_count")
            != meta["portfolio_return_session_count"]
            or cell.get("invested_return_session_count")
            != meta["invested_return_session_count"]
            or cell.get("leverage") is not False
            or cell.get("orders_submitted") != 0
            or cell.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary stock-portfolio cell semantics changed")
        decimal_names = (
            "cumulative_return",
            "matched_eligible_stock_cumulative_return",
            "spy_cumulative_return",
            "cumulative_return_minus_matched",
            "cumulative_return_minus_spy",
            "annualized_arithmetic_return",
            "annualized_volatility",
            "maximum_drawdown",
            "average_daily_two_sided_turnover",
            "average_cash_weight",
            "matched_annualized_arithmetic_return",
            "matched_annualized_volatility",
            "matched_maximum_drawdown",
            "matched_average_daily_two_sided_turnover",
            "matched_average_cash_weight",
        )
        parsed = {
            name: _cell_metric(cell.get(name), "stock portfolio " + name)
            for name in decimal_names
        }
        for name in (
            "zero_rate_sharpe",
            "zero_rate_sortino",
            "matched_zero_rate_sharpe",
            "matched_zero_rate_sortino",
        ):
            value = cell.get(name)
            parsed[name] = (
                None
                if value is None
                else _cell_metric(value, "stock portfolio " + name)
            )
        with localcontext(preliminary_evaluator._context()):
            exact_matched = +(
                parsed["cumulative_return"]
                - parsed["matched_eligible_stock_cumulative_return"]
            )
            exact_spy = +(
                parsed["cumulative_return"] - parsed["spy_cumulative_return"]
            )
            exact_sharpe = (
                None
                if parsed["annualized_volatility"] == 0
                else +(
                    parsed["annualized_arithmetic_return"]
                    / parsed["annualized_volatility"]
                )
            )
            exact_matched_sharpe = (
                None
                if parsed["matched_annualized_volatility"] == 0
                else +(
                    parsed["matched_annualized_arithmetic_return"]
                    / parsed["matched_annualized_volatility"]
                )
            )
        if (
            parsed["cumulative_return"] <= -1
            or parsed["matched_eligible_stock_cumulative_return"] <= -1
            or parsed["spy_cumulative_return"] <= -1
            or parsed["cumulative_return_minus_matched"] != exact_matched
            or parsed["cumulative_return_minus_spy"] != exact_spy
            or parsed["zero_rate_sharpe"] != exact_sharpe
            or parsed["matched_zero_rate_sharpe"] != exact_matched_sharpe
            or (
                parsed["zero_rate_sortino"] is None
                and parsed["annualized_arithmetic_return"] < 0
            )
            or (
                parsed["zero_rate_sortino"] is not None
                and (
                    (
                        parsed["annualized_arithmetic_return"] > 0
                        and parsed["zero_rate_sortino"] <= 0
                    )
                    or (
                        parsed["annualized_arithmetic_return"] < 0
                        and parsed["zero_rate_sortino"] >= 0
                    )
                    or (
                        parsed["annualized_arithmetic_return"] == 0
                        and parsed["zero_rate_sortino"] != 0
                    )
                )
            )
            or (
                parsed["matched_zero_rate_sortino"] is None
                and parsed["matched_annualized_arithmetic_return"] < 0
            )
            or (
                parsed["matched_zero_rate_sortino"] is not None
                and (
                    (
                        parsed["matched_annualized_arithmetic_return"] > 0
                        and parsed["matched_zero_rate_sortino"] <= 0
                    )
                    or (
                        parsed["matched_annualized_arithmetic_return"] < 0
                        and parsed["matched_zero_rate_sortino"] >= 0
                    )
                    or (
                        parsed["matched_annualized_arithmetic_return"] == 0
                        and parsed["matched_zero_rate_sortino"] != 0
                    )
                )
            )
            or parsed["annualized_volatility"] < 0
            or parsed["matched_annualized_volatility"] < 0
            or not -1 <= parsed["maximum_drawdown"] <= 0
            or not -1 <= parsed["matched_maximum_drawdown"] <= 0
            or parsed["average_daily_two_sided_turnover"] < 0
            or parsed["matched_average_daily_two_sided_turnover"] < 0
            or not 0 <= parsed["average_cash_weight"] <= 1
            or not 0 <= parsed["matched_average_cash_weight"] <= 1
        ):
            _error("preliminary stock-portfolio metric escaped bounds")
        spy_values.add(cell["spy_cumulative_return"])
        for name in path_invariants:
            path_invariants[name].add(cell[name])
        signal_by_cost[cost] = parsed["cumulative_return"]
        matched_by_cost[cost] = parsed[
            "matched_eligible_stock_cumulative_return"
        ]
        signal_annual_by_cost[cost] = parsed[
            "annualized_arithmetic_return"
        ]
        matched_annual_by_cost[cost] = parsed[
            "matched_annualized_arithmetic_return"
        ]
        cells.append(cell)

    if len(spy_values) != 1 or any(
        len(values) != 1 for values in path_invariants.values()
    ):
        _error("preliminary stock-portfolio cost path invariance changed")
    signal_turnover = _cell_metric(
        next(iter(path_invariants["average_daily_two_sided_turnover"])),
        "stock portfolio average_daily_two_sided_turnover",
    )
    matched_turnover = _cell_metric(
        next(
            iter(
                path_invariants[
                    "matched_average_daily_two_sided_turnover"
                ]
            )
        ),
        "stock portfolio matched_average_daily_two_sided_turnover",
    )
    with localcontext(preliminary_evaluator._context()):
        for cost in _PINNED_STOCK_PORTFOLIO_COSTS:
            expected_signal_annual = +(
                signal_annual_by_cost[0]
                - Decimal(cost)
                / Decimal(10000)
                * signal_turnover
                * _PINNED_STOCK_PORTFOLIO_ANNUALIZATION_SESSIONS
            )
            expected_matched_annual = +(
                matched_annual_by_cost[0]
                - Decimal(cost)
                / Decimal(10000)
                * matched_turnover
                * _PINNED_STOCK_PORTFOLIO_ANNUALIZATION_SESSIONS
            )
            if (
                abs(
                    signal_annual_by_cost[cost]
                    - expected_signal_annual
                )
                > Decimal("1e-40")
                or abs(
                    matched_annual_by_cost[cost]
                    - expected_matched_annual
                )
                > Decimal("1e-40")
            ):
                _error("preliminary stock-portfolio cost arithmetic changed")
    if any(
        signal_by_cost[left] < signal_by_cost[right]
        or matched_by_cost[left] < matched_by_cost[right]
        for left, right in zip(
            _PINNED_STOCK_PORTFOLIO_COSTS,
            _PINNED_STOCK_PORTFOLIO_COSTS[1:],
        )
    ):
        _error("preliminary stock-portfolio cost monotonicity changed")

    summary_id = meta.get("summary_id")
    summary_sha = meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary stock-portfolio summary identity is absent")
    record = {
        key: value
        for key, value in meta.items()
        if key
        not in {
            "profile_id",
            "profile_sha256",
            "summary_id",
            "summary_sha256",
        }
    }
    record["profile"] = json.loads(
        profile_bytes.decode("ascii")
    )
    record["portfolio_cells"] = cells
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-stock-portfolio-summary-" + digest[:24]
    ):
        _error("preliminary stock-portfolio summary identity changed")


def _validate_market_cap_account_aggregate(
    value: object,
    *,
    role: str,
    decision_count: int,
    return_count: int,
    runtime_security_count: int,
    selected_full_universe: bool = False,
    sector_neutral: bool = False,
) -> dict[str, Decimal]:
    if (
        type(selected_full_universe) is not bool
        or type(sector_neutral) is not bool
    ):
        _error("preliminary market-cap selected breadth mode changed")
    expected_fields = (
        _MARKET_CAP_TILT_ACCOUNT_FIELDS
        if sector_neutral
        else _MARKET_CAP_ACCOUNT_FIELDS
    )
    if type(value) is not dict or set(value) != expected_fields:
        _error("preliminary market-cap account aggregate fields changed")
    integer_fields = (
        "rebalance_execution_count",
        "full_target_execution_count",
        "underfilled_target_execution_count",
        "locked_exposure_over_target_count",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "partial_rebalance_decision_count",
        "stale_position_deferral_count",
        "selection_exit_deferral_count",
        "eligibility_exit_liquidation_count",
        "eligibility_exit_zero_recovery_count",
        *(
            (
                "locked_sector_over_target_count",
                "sector_target_underfill_count",
            )
            if sector_neutral
            else ()
        ),
    )
    if any(
        type(value.get(name)) is not int or value[name] < 0
        for name in integer_fields
    ):
        _error("preliminary market-cap account count changed")
    if (
        value["rebalance_execution_count"] != decision_count
        or value["full_target_execution_count"]
        + value["underfilled_target_execution_count"]
        + value["locked_exposure_over_target_count"]
        != decision_count
        or value["stale_mark_session_count"] > return_count
        or value["partial_rebalance_decision_count"] > decision_count
        or value["partial_rebalance_decision_count"]
        > value["stale_mark_session_count"]
        or value["stale_position_deferral_count"]
        < value["partial_rebalance_decision_count"]
        or value["stale_position_deferral_count"]
        > value["partial_rebalance_decision_count"] * runtime_security_count
        or (value["partial_rebalance_decision_count"] == 0)
        is not (value["stale_position_deferral_count"] == 0)
        or value["entry_price_refusal_count"]
        > decision_count * runtime_security_count
        or value["selection_exit_deferral_count"]
        > value["stale_position_deferral_count"]
        or (
            role == "matched"
            and value["selection_exit_deferral_count"] != 0
        )
        or value["eligibility_exit_liquidation_count"]
        > return_count * runtime_security_count
        or value["eligibility_exit_zero_recovery_count"]
        > return_count * runtime_security_count
        or (
            sector_neutral
            and (
                value["locked_sector_over_target_count"]
                > decision_count * runtime_security_count
                or value["sector_target_underfill_count"]
                > decision_count * runtime_security_count
            )
        )
    ):
        _error("preliminary market-cap account count semantics changed")
    decimal_fields = (
        "mean_executed_gross_exposure",
        "minimum_executed_gross_exposure",
        "maximum_executed_gross_exposure",
        "mean_maximum_position_weight",
        "maximum_position_weight",
        "mean_invested_weight_hhi",
        "mean_effective_holding_count",
        "average_holding_count",
        "average_daily_two_sided_turnover",
        "average_cash_weight",
    )
    parsed = {
        name: _cell_metric(value.get(name), "market-cap " + name)
        for name in decimal_fields
    }
    maximum_names = (
        Decimal(_PINNED_MARKET_CAP_MAXIMUM_HOLDINGS)
        if role == "selected" and not selected_full_universe
        else Decimal(runtime_security_count)
    )
    unit_interval = (
        "mean_executed_gross_exposure",
        "minimum_executed_gross_exposure",
        "maximum_executed_gross_exposure",
        "mean_maximum_position_weight",
        "maximum_position_weight",
        "mean_invested_weight_hhi",
        "average_cash_weight",
    )
    if (
        any(not Decimal(0) <= parsed[name] <= Decimal(1) for name in unit_interval)
        or not Decimal(0) <= parsed["mean_effective_holding_count"] <= maximum_names
        or not Decimal(0) <= parsed["average_holding_count"] <= maximum_names
        or not Decimal(0) <= parsed["average_daily_two_sided_turnover"] <= Decimal(2)
        or parsed["minimum_executed_gross_exposure"]
        > parsed["mean_executed_gross_exposure"]
        or parsed["mean_executed_gross_exposure"]
        > parsed["maximum_executed_gross_exposure"]
        or parsed["mean_maximum_position_weight"]
        > parsed["maximum_position_weight"]
        or (
            value["underfilled_target_execution_count"] == 0
            and value["locked_exposure_over_target_count"] == 0
            and (
                parsed["mean_executed_gross_exposure"]
                != _PINNED_MARKET_CAP_TARGET_GROSS
                or parsed["minimum_executed_gross_exposure"]
                != _PINNED_MARKET_CAP_TARGET_GROSS
                or parsed["maximum_executed_gross_exposure"]
                != _PINNED_MARKET_CAP_TARGET_GROSS
            )
        )
        or (
            value["underfilled_target_execution_count"] > 0
            and value["locked_exposure_over_target_count"] == 0
            and parsed["minimum_executed_gross_exposure"]
            >= _PINNED_MARKET_CAP_TARGET_GROSS
        )
        or (
            value["locked_exposure_over_target_count"] > 0
            and parsed["maximum_executed_gross_exposure"]
            <= _PINNED_MARKET_CAP_TARGET_GROSS
        )
    ):
        _error("preliminary market-cap account metric escaped bounds")
    return parsed


def _validate_market_cap_tilt_aggregate(
    value: object,
    *,
    decision_count: int,
    runtime_security_count: int,
) -> dict[str, Decimal]:
    if type(value) is not dict or set(value) != _MARKET_CAP_TILT_FIELDS:
        _error("preliminary market-cap tilt aggregate fields changed")
    count_fields = (
        "decision_session_count",
        "tilt_enabled_decision_count",
        "tilt_underfilled_decision_count",
        "minimum_ranked_nonzero_score_count",
        "minimum_positive_score_count",
        "minimum_negative_score_count",
        "minimum_tilted_name_count_when_enabled",
        "minimum_point_in_time_sector_count",
    )
    if any(
        type(value.get(name)) is not int or value[name] < 0
        for name in count_fields
    ):
        _error("preliminary market-cap tilt aggregate count changed")
    enabled = value["tilt_enabled_decision_count"]
    underfilled = value["tilt_underfilled_decision_count"]
    ranked = value["minimum_ranked_nonzero_score_count"]
    positive = value["minimum_positive_score_count"]
    negative = value["minimum_negative_score_count"]
    tilted = value["minimum_tilted_name_count_when_enabled"]
    sector_count = value["minimum_point_in_time_sector_count"]
    if (
        value.get("schema") != _PINNED_MARKET_CAP_TILT_AGGREGATES_SCHEMA
        or value["decision_session_count"] != decision_count
        or enabled + underfilled != decision_count
        or ranked > runtime_security_count
        or positive > runtime_security_count
        or negative > runtime_security_count
        or tilted > runtime_security_count
        or not 0 < sector_count <= runtime_security_count
        or positive + negative > ranked
        or (
            underfilled == 0
            and (
                ranked < _PINNED_MARKET_CAP_MINIMUM_TILT_RANKED_NAMES
                or positive
                < _PINNED_MARKET_CAP_MINIMUM_TILT_POSITIVE_SCORES
                or negative
                < _PINNED_MARKET_CAP_MINIMUM_TILT_NEGATIVE_SCORES
            )
        )
        or (
            enabled == 0
            and tilted != 0
        )
        or (
            enabled > 0
            and tilted < _PINNED_MARKET_CAP_MINIMUM_TILT_RANKED_NAMES
        )
        or value.get("underfilled_exact_benchmark") is not True
        or value.get("missing_or_zero_score_exact_benchmark") is not True
        or value.get("sector_mapping_exhaustive") is not True
        or value.get("sector_neutrality_exact") is not True
        or value.get("sector_neutrality_scope") != "frozen_target"
    ):
        _error("preliminary market-cap tilt aggregate count semantics changed")
    decimal_fields = (
        "maximum_one_way_active_share",
        "maximum_overweight",
        "maximum_hhi_ratio_to_benchmark",
        "minimum_weight_ratio_to_benchmark_when_enabled",
        "maximum_weight_ratio_to_benchmark_when_enabled",
        "maximum_absolute_sector_active_weight",
    )
    parsed = {
        name: _cell_metric(value.get(name), "market-cap tilt " + name)
        for name in decimal_fields
    }
    active_share = parsed["maximum_one_way_active_share"]
    maximum_overweight = parsed["maximum_overweight"]
    hhi_ratio = parsed["maximum_hhi_ratio_to_benchmark"]
    minimum_ratio = parsed[
        "minimum_weight_ratio_to_benchmark_when_enabled"
    ]
    maximum_ratio = parsed[
        "maximum_weight_ratio_to_benchmark_when_enabled"
    ]
    maximum_sector_active_weight = parsed[
        "maximum_absolute_sector_active_weight"
    ]
    if enabled == 0:
        if any(metric != 0 for metric in parsed.values()):
            _error("preliminary market-cap tilt fallback metrics changed")
    elif (
        not 0 < active_share <= _PINNED_MARKET_CAP_MAXIMUM_ONE_WAY_ACTIVE_SHARE
        or not 0
        < maximum_overweight
        <= _PINNED_MARKET_CAP_MAXIMUM_ABSOLUTE_OVERWEIGHT
        or not 0 < hhi_ratio <= _PINNED_MARKET_CAP_MAXIMUM_HHI_MULTIPLE
        or not Decimal(1) - _PINNED_MARKET_CAP_MAXIMUM_RELATIVE_TILT
        <= minimum_ratio
        < Decimal(1)
        or not Decimal(1)
        < maximum_ratio
        <= Decimal(1) + _PINNED_MARKET_CAP_MAXIMUM_RELATIVE_TILT
        or minimum_ratio >= maximum_ratio
        or maximum_sector_active_weight != 0
    ):
        _error("preliminary market-cap tilt aggregate metric escaped bounds")
    return parsed


def _validate_market_cap_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile_id = plan.projection.evaluation_profile_id
    profile_bytes, profile_sha256, _result_names = (
        _market_cap_profile_binding(profile_id)
    )
    profile = json.loads(profile_bytes.decode("ascii"))
    tilt_profile = profile_id in _PINNED_MARKET_CAP_TILT_PROFILE_IDS
    if (
        plan.evaluation_profile_id != profile_id
        or plan.evaluation_profile_sha256 != profile_sha256
        or plan.projection.evaluation_profile_sha256 != profile_sha256
    ):
        _error("preliminary market-cap plan profile binding changed")
    runtime_meta = records.get("ARV2_RUNTIME_META")
    runtime_count_fields = (
        "resolved_security_count",
        "named_security_refusal_count",
        "runtime_slice_count",
        "point_in_time_history_call_count",
        "point_in_time_fetched_source_row_count",
        "point_in_time_eligible_score_bearing_count",
        "point_in_time_market_cap_covered_count",
        "point_in_time_market_cap_uncovered_count",
    )
    expected_decisions = profile["expected_decision_session_count"]
    expected_history_calls = 2 * (
        (
            expected_decisions
            + _PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS
            - 1
        )
        // _PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS
    )
    if (
        type(runtime_meta) is not dict
        or set(runtime_meta) != _MARKET_CAP_RUNTIME_META_FIELDS
        or runtime_meta.get("schema")
        != "arv2-accepted-risk-market-cap-stock-portfolio-qc-runtime-meta-v1"
        or runtime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_MARKET_CAP_STOCK_PORTFOLIO_COMPLETED"
        or runtime_meta.get("evaluation_profile_id") != profile_id
        or runtime_meta.get("evaluation_profile_sha256") != profile_sha256
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "market-cap symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "market-cap symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or any(
            type(runtime_meta.get(name)) is not int
            or runtime_meta[name] < 0
            for name in runtime_count_fields
        )
        or runtime_meta["runtime_slice_count"] == 0
        or runtime_meta["runtime_slice_count"]
        > _PINNED_MARKET_CAP_RUNTIME_MAX_TRAIN_SLICES
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
        or runtime_meta["point_in_time_history_call_count"]
        != expected_history_calls
        or runtime_meta["point_in_time_history_call_count"]
        > 2 * _PINNED_MARKET_CAP_RUNTIME_MAX_HISTORY_CHUNKS
        or not 0
        < runtime_meta["point_in_time_fetched_source_row_count"]
        <= _PINNED_MARKET_CAP_RUNTIME_MAX_TOTAL_SOURCE_ROWS
        or runtime_meta["point_in_time_market_cap_covered_count"]
        + runtime_meta["point_in_time_market_cap_uncovered_count"]
        != runtime_meta["point_in_time_eligible_score_bearing_count"]
        or runtime_meta["point_in_time_market_cap_covered_count"]
        < expected_decisions
        or runtime_meta["point_in_time_eligible_score_bearing_count"]
        > expected_decisions * runtime_meta["resolved_security_count"]
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or runtime_meta.get("point_in_time") is not True
        or runtime_meta.get("economic_portfolio") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "formal",
                "control_residualized",
                "etf_or_leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        _error("preliminary market-cap runtime metadata changed")

    meta = records.get(_PINNED_MARKET_CAP_META_STATISTIC_NAME)
    expected_meta_fields = (
        _MARKET_CAP_TILT_META_FIELDS
        if tilt_profile
        else _MARKET_CAP_META_FIELDS
    )
    if type(meta) is not dict or set(meta) != expected_meta_fields:
        _error("preliminary market-cap aggregate metadata changed")
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    count_fields = (
        "decision_session_count",
        "portfolio_return_session_count",
        "eligible_without_R055_score_count",
        "sector_refused_decision_count",
        "named_figi_resolution_refusal_count",
    )
    if (
        meta.get("schema") != _PINNED_MARKET_CAP_SUMMARY_SCHEMA
        or meta.get("contract_id") != _PINNED_MARKET_CAP_CONTRACT_ID
        or meta.get("profile_id") != profile_id
        or meta.get("profile_sha256") != profile_sha256
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("input_manifest_id") != plan.evaluator_manifest_id
        or meta.get("input_manifest_sha256")
        != plan.evaluator_manifest_sha256
        or meta.get("input_manifest_id")
        != authenticated_manifest.get("manifest_id")
        or meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_MARKET_CAP_STOCK_PORTFOLIO"
        or any(
            type(meta.get(name)) is not int or meta[name] < 0
            for name in count_fields
        )
        or meta["decision_session_count"] != expected_decisions
        or meta["portfolio_return_session_count"]
        != profile["expected_return_session_count"]
        or meta["sector_refused_decision_count"] > expected_decisions
        or meta["named_figi_resolution_refusal_count"]
        != runtime_meta["named_security_refusal_count"]
        or meta.get("r055_signal_rule_changed") is not False
        or meta.get("point_in_time_market_cap_weighting") is not True
        or meta.get("selected_and_matched_target_same_gross") is not True
        or meta.get("economic_portfolio_evaluation") is not True
        or (
            tilt_profile
            and (
                meta.get("analyst_revisions_role")
                != "bounded_helper_overlay_not_an_admission_gate"
                or meta.get("benchmark_logical_id") != "SPY"
                or meta.get("benchmark_history_normalization_mode")
                != "total_return"
                or meta.get("benchmark_history_observation")
                != "session_open"
                or _sha(
                    meta.get("benchmark_raw_observation_sha256"),
                    "market-cap raw benchmark observations",
                )
                != meta.get("benchmark_raw_observation_sha256")
                or _sha(
                    meta.get("benchmark_return_path_sha256"),
                    "market-cap benchmark return path",
                )
                != meta.get("benchmark_return_path_sha256")
                or type(meta.get("benchmark_observation_count")) is not int
                or meta.get("benchmark_observation_count") != 1_254
                or type(meta.get("benchmark_return_interval_count"))
                is not int
                or meta.get("benchmark_return_interval_count") != 1_253
                or meta.get("benchmark_first_used_session")
                != "2021-01-05"
                or meta.get("benchmark_last_used_session")
                != "2025-12-31"
            )
        )
        or any(
            meta.get(name) is not False
            for name in (
                "market_cap_values_in_summary",
                "raw_security_ids_in_summary",
                "raw_price_rows_in_summary",
                "formal_result",
                "alpha_claim_authorized",
                "leverage",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        _error("preliminary market-cap aggregate metadata semantics changed")
    mean_point_in_time = _cell_metric(
        meta.get("mean_point_in_time_eligible_count"),
        "market-cap mean_point_in_time_eligible_count",
    )
    mean_score = _cell_metric(
        meta.get("mean_eligible_score_count"),
        "market-cap mean_eligible_score_count",
    )
    mean_selected = _cell_metric(
        meta.get("mean_selected_name_count"),
        "market-cap mean_selected_name_count",
    )
    with localcontext(preliminary_evaluator._context()):
        point_total = +(mean_point_in_time * Decimal(expected_decisions))
        score_total = +(mean_score * Decimal(expected_decisions))
        selected_total = +(mean_selected * Decimal(expected_decisions))
        selected_integral = selected_total.to_integral_value()
    census_tolerance = Decimal("1e-40")
    if (
        not Decimal(0)
        < mean_point_in_time
        <= Decimal(runtime_meta["resolved_security_count"])
        or not Decimal(0) <= mean_score <= mean_point_in_time
        or not Decimal(0)
        <= mean_selected
        <= Decimal(
            runtime_meta["resolved_security_count"]
            if tilt_profile
            else _PINNED_MARKET_CAP_MAXIMUM_HOLDINGS
        )
        or abs(
            point_total
            - Decimal(runtime_meta["point_in_time_market_cap_covered_count"])
        )
        > census_tolerance
        or abs(
            score_total
            + Decimal(meta["eligible_without_R055_score_count"])
            - point_total
        )
        > census_tolerance
        or abs(selected_total - selected_integral) > census_tolerance
        or (
            tilt_profile
            and abs(selected_total - point_total) > census_tolerance
        )
        or (
            not tilt_profile
            and selected_total > score_total + census_tolerance
        )
    ):
        _error("preliminary market-cap eligibility census changed")

    selected_raw = records.get(
        _PINNED_MARKET_CAP_SELECTED_AGGREGATES_STATISTIC_NAME
    )
    matched_raw = records.get(
        _PINNED_MARKET_CAP_MATCHED_AGGREGATES_STATISTIC_NAME
    )
    selected = _validate_market_cap_account_aggregate(
        selected_raw,
        role="selected",
        decision_count=expected_decisions,
        return_count=meta["portfolio_return_session_count"],
        runtime_security_count=runtime_meta["resolved_security_count"],
        selected_full_universe=tilt_profile,
        sector_neutral=tilt_profile,
    )
    matched = _validate_market_cap_account_aggregate(
        matched_raw,
        role="matched",
        decision_count=expected_decisions,
        return_count=meta["portfolio_return_session_count"],
        runtime_security_count=runtime_meta["resolved_security_count"],
        sector_neutral=tilt_profile,
    )
    tilt_raw = None
    if tilt_profile:
        tilt_raw = records.get(
            _PINNED_MARKET_CAP_TILT_AGGREGATES_STATISTIC_NAME
        )
        _validate_market_cap_tilt_aggregate(
            tilt_raw,
            decision_count=expected_decisions,
            runtime_security_count=runtime_meta["resolved_security_count"],
        )
    if (
        selected_raw["eligibility_exit_zero_recovery_count"]
        or matched_raw["eligibility_exit_zero_recovery_count"]
    ):
        available_status = (
            "PRELIMINARY_DESCRIPTIVE_ZERO_RECOVERY_SENSITIVITY"
        )
    elif (
        selected_raw["stale_mark_session_count"]
        or matched_raw["stale_mark_session_count"]
    ):
        available_status = "PRELIMINARY_DESCRIPTIVE_STALE_MARK_SENSITIVITY"
    elif (
        selected_raw["underfilled_target_execution_count"]
        or matched_raw["underfilled_target_execution_count"]
    ):
        available_status = "PRELIMINARY_DESCRIPTIVE_EXPOSURE_UNDERFILL"
    else:
        available_status = "PRELIMINARY_DESCRIPTIVE_AVAILABLE"

    cells = []
    spy_values = set()
    signal_by_cost = {}
    matched_by_cost = {}
    signal_annual_by_cost = {}
    matched_annual_by_cost = {}
    path_invariants = {
        name: set()
        for name in (
            "invested_return_session_count",
            "average_daily_two_sided_turnover",
            "average_cash_weight",
            "matched_average_daily_two_sided_turnover",
            "matched_average_cash_weight",
        )
    }
    for cost in _PINNED_MARKET_CAP_COSTS:
        cell = records.get("ARV2_STOCK_PORTFOLIO_COST_" + str(cost))
        if type(cell) is not dict or set(cell) != _MARKET_CAP_CELL_FIELDS:
            _error("preliminary market-cap portfolio cell fields changed")
        if (
            cell.get("schema") != _PINNED_MARKET_CAP_CELL_SCHEMA
            or cell.get("profile_id") != profile_id
            or cell.get("cost_bps_per_side") != cost
            or cell.get("primary_cost_scenario")
            is not (cost == _PINNED_MARKET_CAP_PRIMARY_COST)
            or type(cell.get("invested_return_session_count")) is not int
            or not 0
            <= cell["invested_return_session_count"]
            <= meta["portfolio_return_session_count"]
            or cell.get("status")
            != (
                "INCONCLUSIVE_UNDERFILLED"
                if (
                    meta["portfolio_return_session_count"] < 252
                    or cell["invested_return_session_count"]
                    < _PINNED_MARKET_CAP_MINIMUM_INVESTED_RETURNS
                )
                else available_status
            )
            or cell.get("return_metric_conditioning")
            != (
                "zero_recovery_for_missing_eligibility_exits_and_stale_mark_"
                "carry_with_trade_deferral_within_eligibility"
            )
            or cell.get("risk_metrics_are_price_proxy_conditioned")
            is not bool(
                selected_raw["eligibility_exit_zero_recovery_count"]
                or matched_raw["eligibility_exit_zero_recovery_count"]
                or selected_raw["stale_mark_session_count"]
                or matched_raw["stale_mark_session_count"]
            )
            or cell.get("exposure_underfill_present")
            is not bool(
                selected_raw["underfilled_target_execution_count"]
                or matched_raw["underfilled_target_execution_count"]
            )
            or cell.get("return_session_count")
            != meta["portfolio_return_session_count"]
            or cell.get("leverage") is not False
            or cell.get("orders_submitted") != 0
            or cell.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary market-cap portfolio cell semantics changed")
        decimal_names = (
            "cumulative_return",
            "matched_eligible_stock_cumulative_return",
            "spy_cumulative_return",
            "cumulative_return_minus_matched",
            "cumulative_return_minus_spy",
            "annualized_arithmetic_return",
            "annualized_volatility",
            "maximum_drawdown",
            "average_daily_two_sided_turnover",
            "average_cash_weight",
            "matched_annualized_arithmetic_return",
            "matched_annualized_volatility",
            "matched_maximum_drawdown",
            "matched_average_daily_two_sided_turnover",
            "matched_average_cash_weight",
        )
        parsed = {
            name: _cell_metric(cell.get(name), "market-cap " + name)
            for name in decimal_names
        }
        for name in (
            "zero_rate_sharpe",
            "zero_rate_sortino",
            "matched_zero_rate_sharpe",
            "matched_zero_rate_sortino",
        ):
            value = cell.get(name)
            parsed[name] = (
                None
                if value is None
                else _cell_metric(value, "market-cap " + name)
            )
        with localcontext(preliminary_evaluator._context()):
            exact_matched = +(
                parsed["cumulative_return"]
                - parsed["matched_eligible_stock_cumulative_return"]
            )
            exact_spy = +(
                parsed["cumulative_return"] - parsed["spy_cumulative_return"]
            )
            exact_sharpe = (
                None
                if parsed["annualized_volatility"] == 0
                else +(
                    parsed["annualized_arithmetic_return"]
                    / parsed["annualized_volatility"]
                )
            )
            exact_matched_sharpe = (
                None
                if parsed["matched_annualized_volatility"] == 0
                else +(
                    parsed["matched_annualized_arithmetic_return"]
                    / parsed["matched_annualized_volatility"]
                )
            )
        if (
            parsed["cumulative_return"] <= -1
            or parsed["matched_eligible_stock_cumulative_return"] <= -1
            or parsed["spy_cumulative_return"] <= -1
            or parsed["cumulative_return_minus_matched"] != exact_matched
            or parsed["cumulative_return_minus_spy"] != exact_spy
            or parsed["zero_rate_sharpe"] != exact_sharpe
            or parsed["matched_zero_rate_sharpe"] != exact_matched_sharpe
            or (
                parsed["zero_rate_sortino"] is None
                and parsed["annualized_arithmetic_return"] < 0
            )
            or (
                parsed["zero_rate_sortino"] is not None
                and (
                    (
                        parsed["annualized_arithmetic_return"] > 0
                        and parsed["zero_rate_sortino"] <= 0
                    )
                    or (
                        parsed["annualized_arithmetic_return"] < 0
                        and parsed["zero_rate_sortino"] >= 0
                    )
                    or (
                        parsed["annualized_arithmetic_return"] == 0
                        and parsed["zero_rate_sortino"] != 0
                    )
                )
            )
            or (
                parsed["matched_zero_rate_sortino"] is None
                and parsed["matched_annualized_arithmetic_return"] < 0
            )
            or (
                parsed["matched_zero_rate_sortino"] is not None
                and (
                    (
                        parsed["matched_annualized_arithmetic_return"] > 0
                        and parsed["matched_zero_rate_sortino"] <= 0
                    )
                    or (
                        parsed["matched_annualized_arithmetic_return"] < 0
                        and parsed["matched_zero_rate_sortino"] >= 0
                    )
                    or (
                        parsed["matched_annualized_arithmetic_return"] == 0
                        and parsed["matched_zero_rate_sortino"] != 0
                    )
                )
            )
            or parsed["annualized_volatility"] < 0
            or parsed["matched_annualized_volatility"] < 0
            or not -1 <= parsed["maximum_drawdown"] <= 0
            or not -1 <= parsed["matched_maximum_drawdown"] <= 0
            or parsed["average_daily_two_sided_turnover"] < 0
            or parsed["matched_average_daily_two_sided_turnover"] < 0
            or not 0 <= parsed["average_cash_weight"] <= 1
            or not 0 <= parsed["matched_average_cash_weight"] <= 1
        ):
            _error("preliminary market-cap portfolio metric escaped bounds")
        spy_values.add(cell["spy_cumulative_return"])
        for name in path_invariants:
            path_invariants[name].add(cell[name])
        signal_by_cost[cost] = parsed["cumulative_return"]
        matched_by_cost[cost] = parsed[
            "matched_eligible_stock_cumulative_return"
        ]
        signal_annual_by_cost[cost] = parsed["annualized_arithmetic_return"]
        matched_annual_by_cost[cost] = parsed[
            "matched_annualized_arithmetic_return"
        ]
        cells.append(cell)
    if (
        len(spy_values) != 1
        or any(len(values) != 1 for values in path_invariants.values())
        or next(iter(path_invariants["average_daily_two_sided_turnover"]))
        != selected_raw["average_daily_two_sided_turnover"]
        or next(iter(path_invariants["average_cash_weight"]))
        != selected_raw["average_cash_weight"]
        or next(
            iter(
                path_invariants[
                    "matched_average_daily_two_sided_turnover"
                ]
            )
        )
        != matched_raw["average_daily_two_sided_turnover"]
        or next(iter(path_invariants["matched_average_cash_weight"]))
        != matched_raw["average_cash_weight"]
    ):
        _error("preliminary market-cap cost path invariance changed")
    signal_turnover = selected["average_daily_two_sided_turnover"]
    matched_turnover = matched["average_daily_two_sided_turnover"]
    with localcontext(preliminary_evaluator._context()):
        for cost in _PINNED_MARKET_CAP_COSTS:
            expected_signal_annual = +(
                signal_annual_by_cost[0]
                - Decimal(cost)
                / Decimal(10000)
                * signal_turnover
                * _PINNED_MARKET_CAP_ANNUALIZATION_SESSIONS
            )
            expected_matched_annual = +(
                matched_annual_by_cost[0]
                - Decimal(cost)
                / Decimal(10000)
                * matched_turnover
                * _PINNED_MARKET_CAP_ANNUALIZATION_SESSIONS
            )
            if (
                abs(signal_annual_by_cost[cost] - expected_signal_annual)
                > Decimal("1e-40")
                or abs(
                    matched_annual_by_cost[cost]
                    - expected_matched_annual
                )
                > Decimal("1e-40")
            ):
                _error("preliminary market-cap cost arithmetic changed")
    if any(
        signal_by_cost[left] < signal_by_cost[right]
        or matched_by_cost[left] < matched_by_cost[right]
        for left, right in zip(
            _PINNED_MARKET_CAP_COSTS,
            _PINNED_MARKET_CAP_COSTS[1:],
        )
    ):
        _error("preliminary market-cap cost monotonicity changed")

    summary_id = meta.get("summary_id")
    summary_sha = meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary market-cap summary identity is absent")
    record = {
        key: value
        for key, value in meta.items()
        if key
        not in {
            "profile_id",
            "profile_sha256",
            "summary_id",
            "summary_sha256",
        }
    }
    record["profile"] = profile
    record["selected_aggregates"] = selected_raw
    record["matched_aggregates"] = matched_raw
    if tilt_profile:
        record["tilt_aggregates"] = tilt_raw
    record["portfolio_cells"] = cells
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-market-cap-stock-summary-" + digest[:24]
    ):
        _error("preliminary market-cap summary identity changed")


def _validate_leverage_path(
    cell: dict[str, object],
    *,
    prefix: str,
    leverage_factor: int,
    annual_financing_rate: Decimal,
    return_count: int,
) -> dict[str, Decimal | int | None]:
    financing_count = cell.get(prefix + "financing_session_count")
    if (
        type(financing_count) is not int
        or not 0 <= financing_count <= return_count
        or (prefix == "synthetic_spy_" and financing_count != return_count - 1)
    ):
        _error("preliminary objective leverage financing census changed")
    parsed: dict[str, Decimal | int | None] = {
        "financing_session_count": financing_count
    }
    for suffix in (
        "cumulative_return",
        "cumulative_return_before_financing",
        "cumulative_financing_drag",
        "arithmetic_financing_debit",
        "annualized_arithmetic_return",
        "annualized_volatility",
        "maximum_drawdown",
    ):
        parsed[suffix] = _cell_metric(
            cell.get(prefix + suffix),
            "objective leverage " + prefix + suffix,
        )
    for suffix in ("zero_rate_sharpe", "zero_rate_sortino"):
        value = cell.get(prefix + suffix)
        parsed[suffix] = (
            None
            if value is None
            else _cell_metric(
                value,
                "objective leverage " + prefix + suffix,
            )
        )
    cumulative = parsed["cumulative_return"]
    before_financing = parsed["cumulative_return_before_financing"]
    cumulative_drag = parsed["cumulative_financing_drag"]
    arithmetic_debit = parsed["arithmetic_financing_debit"]
    annual = parsed["annualized_arithmetic_return"]
    volatility = parsed["annualized_volatility"]
    sharpe = parsed["zero_rate_sharpe"]
    sortino = parsed["zero_rate_sortino"]
    drawdown = parsed["maximum_drawdown"]
    if any(
        type(value) is not Decimal
        for value in (
            cumulative,
            before_financing,
            cumulative_drag,
            arithmetic_debit,
            annual,
            volatility,
            drawdown,
        )
    ):
        _error("preliminary objective leverage path metric changed")
    with localcontext(preliminary_evaluator._context()):
        expected_drag = +(before_financing - cumulative)
        expected_debit = +(
            (Decimal(leverage_factor) - Decimal(1))
            * annual_financing_rate
            / _PINNED_LEVERAGE_ANNUALIZATION_SESSIONS
            * Decimal(financing_count)
        )
        expected_sharpe = (
            None if volatility == 0 else +(annual / volatility)
        )
    tolerance = Decimal("1e-40")
    if (
        cumulative <= -1
        or before_financing <= -1
        or cumulative_drag < 0
        or arithmetic_debit < 0
        or abs(cumulative_drag - expected_drag) > tolerance
        or abs(arithmetic_debit - expected_debit) > tolerance
        or volatility < 0
        or sharpe != expected_sharpe
        or not -1 <= drawdown <= 0
        or (sortino is None and annual < 0)
        or (
            sortino is not None
            and (
                (annual > 0 and sortino <= 0)
                or (annual < 0 and sortino >= 0)
                or (annual == 0 and sortino != 0)
            )
        )
    ):
        _error("preliminary objective leverage path arithmetic changed")
    return parsed


def _validate_leverage_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile_id = plan.projection.evaluation_profile_id
    profile_bytes, profile_sha256, _result_names = _leverage_profile_binding(
        profile_id
    )
    profile = json.loads(profile_bytes.decode("ascii"))
    base_profile_id = profile["base_profile_id"]
    base_profile = _PINNED_REQUIRE_MARKET_CAP_PROFILE(base_profile_id)
    if (
        plan.evaluation_profile_id != profile_id
        or plan.evaluation_profile_sha256 != profile_sha256
        or plan.projection.evaluation_profile_sha256 != profile_sha256
        or profile.get("base_contract_id") != _PINNED_MARKET_CAP_CONTRACT_ID
        or profile.get("base_profile_sha256")
        != base_profile.get("profile_sha256")
        or profile.get("base_evaluator_source_sha256")
        != _PINNED_LEVERAGE_BASE_SOURCE_SHA256
    ):
        _error("preliminary objective leverage plan lineage changed")

    expected_decisions = base_profile["expected_decision_session_count"]
    expected_returns = profile["expected_return_session_count"]
    expected_history_calls = 2 * (
        (
            expected_decisions
            + _PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS
            - 1
        )
        // _PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS
    )
    runtime_meta = records.get("ARV2_RUNTIME_META")
    runtime_count_fields = (
        "resolved_security_count",
        "named_security_refusal_count",
        "runtime_slice_count",
        "point_in_time_history_call_count",
        "point_in_time_fetched_source_row_count",
        "point_in_time_eligible_score_bearing_count",
        "point_in_time_market_cap_covered_count",
        "point_in_time_market_cap_uncovered_count",
    )
    if (
        type(runtime_meta) is not dict
        or set(runtime_meta) != _LEVERAGE_RUNTIME_META_FIELDS
        or runtime_meta.get("schema") != _PINNED_LEVERAGE_RUNTIME_SCHEMA
        or runtime_meta.get("status") != _PINNED_LEVERAGE_RUNTIME_STATUS
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or runtime_meta.get("evaluation_profile_id") != profile_id
        or runtime_meta.get("evaluation_profile_sha256") != profile_sha256
        or runtime_meta.get("base_market_cap_profile_id") != base_profile_id
        or runtime_meta.get("base_market_cap_profile_sha256")
        != base_profile["profile_sha256"]
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "objective leverage symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "objective leverage symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or any(
            type(runtime_meta.get(name)) is not int
            or runtime_meta[name] < 0
            for name in runtime_count_fields
        )
        or runtime_meta["runtime_slice_count"] == 0
        or runtime_meta["runtime_slice_count"]
        > _PINNED_LEVERAGE_RUNTIME_MAX_TRAIN_SLICES
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
        or runtime_meta["point_in_time_history_call_count"]
        != expected_history_calls
        or runtime_meta["point_in_time_history_call_count"]
        > 2 * _PINNED_MARKET_CAP_RUNTIME_MAX_HISTORY_CHUNKS
        or not 0
        < runtime_meta["point_in_time_fetched_source_row_count"]
        <= _PINNED_MARKET_CAP_RUNTIME_MAX_TOTAL_SOURCE_ROWS
        or runtime_meta["point_in_time_market_cap_covered_count"]
        + runtime_meta["point_in_time_market_cap_uncovered_count"]
        != runtime_meta["point_in_time_eligible_score_bearing_count"]
        or runtime_meta["point_in_time_market_cap_covered_count"]
        < expected_decisions
        or runtime_meta["point_in_time_eligible_score_bearing_count"]
        > expected_decisions * runtime_meta["resolved_security_count"]
        or runtime_meta.get("leverage_factors")
        != list(_PINNED_LEVERAGE_FACTORS)
        or runtime_meta.get("scenario_ids")
        != [item[0] for item in _PINNED_LEVERAGE_SCENARIOS]
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or runtime_meta.get("point_in_time") is not True
        or runtime_meta.get("economic_portfolio") is not True
        or runtime_meta.get("etf_or_leverage") is not True
        or runtime_meta.get("synthetic_leverage") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "formal",
                "control_residualized",
                "margin_calls_modeled",
                "borrow_availability_modeled",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        _error("preliminary objective leverage runtime metadata changed")

    meta = records.get(_PINNED_LEVERAGE_META_STATISTIC_NAME)
    if type(meta) is not dict or set(meta) != _LEVERAGE_META_FIELDS:
        _error("preliminary objective leverage aggregate metadata changed")
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    if (
        meta.get("schema") != _PINNED_LEVERAGE_SUMMARY_SCHEMA
        or meta.get("contract_id") != _PINNED_LEVERAGE_CONTRACT_ID
        or meta.get("profile_id") != profile_id
        or meta.get("profile_sha256") != profile_sha256
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("input_manifest_id") != plan.evaluator_manifest_id
        or meta.get("input_manifest_sha256")
        != plan.evaluator_manifest_sha256
        or meta.get("input_manifest_id")
        != authenticated_manifest.get("manifest_id")
        or meta.get("status")
        != "PRELIMINARY_OBJECTIVE_SYNTHETIC_LEVERAGE"
        or meta.get("base_contract_id") != _PINNED_MARKET_CAP_CONTRACT_ID
        or meta.get("base_profile_id") != base_profile_id
        or meta.get("base_profile_sha256")
        != base_profile["profile_sha256"]
        or meta.get("base_evaluator_source_sha256")
        != _PINNED_LEVERAGE_BASE_SOURCE_SHA256
        or type(meta.get("decision_session_count")) is not int
        or meta["decision_session_count"] != expected_decisions
        or type(meta.get("return_session_count")) is not int
        or meta["return_session_count"] != expected_returns
        or meta.get("r055_signal_rule_changed") is not False
        or meta.get("base_security_selection_changed") is not False
        or meta.get("point_in_time_membership_and_market_cap_weighting")
        is not True
        or meta.get("matched_comparator_levered_identically") is not True
        or meta.get("synthetic_only") is not True
        or meta.get("evaluator_io")
        != {"provider": False, "network": False, "object_store": False}
        or any(
            meta.get(name) is not False
            for name in (
                "raw_security_ids_in_summary",
                "raw_price_rows_in_summary",
                "raw_provider_rows_in_summary",
                "formal_result",
                "alpha_claim_authorized",
                "margin_calls_modeled",
                "borrow_availability_modeled",
                "orders",
                "deployment",
                "trading",
            )
        )
    ):
        _error("preliminary objective leverage aggregate semantics changed")

    selected_raw = records.get(
        _PINNED_LEVERAGE_SELECTED_BASE_AGGREGATES_STATISTIC_NAME
    )
    matched_raw = records.get(
        _PINNED_LEVERAGE_MATCHED_BASE_AGGREGATES_STATISTIC_NAME
    )
    selected_base = _validate_market_cap_account_aggregate(
        selected_raw,
        role="selected",
        decision_count=expected_decisions,
        return_count=expected_returns,
        runtime_security_count=runtime_meta["resolved_security_count"],
    )
    matched_base = _validate_market_cap_account_aggregate(
        matched_raw,
        role="matched",
        decision_count=expected_decisions,
        return_count=expected_returns,
        runtime_security_count=runtime_meta["resolved_security_count"],
    )
    del selected_base, matched_base
    if (
        selected_raw["eligibility_exit_zero_recovery_count"]
        or matched_raw["eligibility_exit_zero_recovery_count"]
    ):
        available_status = (
            "PRELIMINARY_DESCRIPTIVE_ZERO_RECOVERY_SENSITIVITY"
        )
    elif (
        selected_raw["stale_mark_session_count"]
        or matched_raw["stale_mark_session_count"]
    ):
        available_status = "PRELIMINARY_DESCRIPTIVE_STALE_MARK_SENSITIVITY"
    elif (
        selected_raw["underfilled_target_execution_count"]
        or matched_raw["underfilled_target_execution_count"]
    ):
        available_status = "PRELIMINARY_DESCRIPTIVE_EXPOSURE_UNDERFILL"
    else:
        available_status = "PRELIMINARY_DESCRIPTIVE_AVAILABLE"

    cells = []
    grid: dict[tuple[int, str], dict[str, dict[str, Decimal | int | None]]] = {}
    selected_counts = set()
    matched_counts = set()
    for leverage_factor in _PINNED_LEVERAGE_FACTORS:
        for scenario_id, financing_rate, cost_bps, primary in (
            _PINNED_LEVERAGE_SCENARIOS
        ):
            suffix = "PRIMARY" if primary else "ADVERSE"
            name = "ARV2_LEVERAGE_L" + str(leverage_factor) + "_" + suffix
            cell = records.get(name)
            if type(cell) is not dict or set(cell) != _LEVERAGE_CELL_FIELDS:
                _error("preliminary objective leverage cell fields changed")
            expected_status = (
                "INCONCLUSIVE_UNDERFILLED"
                if (
                    expected_returns < 252
                    or type(cell.get("selected_financing_session_count"))
                    is not int
                    or cell["selected_financing_session_count"]
                    < _PINNED_MARKET_CAP_MINIMUM_INVESTED_RETURNS
                )
                else available_status
            )
            if (
                cell.get("schema") != _PINNED_LEVERAGE_CELL_SCHEMA
                or cell.get("profile_id") != profile_id
                or cell.get("base_profile_id") != base_profile_id
                or cell.get("scenario_id") != scenario_id
                or cell.get("primary_scenario") is not primary
                or cell.get("leverage_factor") != leverage_factor
                or type(cell.get("leverage_factor")) is not int
                or cell.get("annual_financing_rate")
                != (
                    "0"
                    if financing_rate == 0
                    else format(financing_rate, "f")
                )
                or cell.get("underlying_cost_bps_per_side") != cost_bps
                or type(cell.get("underlying_cost_bps_per_side")) is not int
                or cell.get("underlying_cost_is_already_in_base_return")
                is not True
                or cell.get("second_transaction_cost_deduction") is not False
                or cell.get("status") != expected_status
                or cell.get("return_session_count") != expected_returns
                or type(cell.get("return_session_count")) is not int
                or cell.get("portfolio_level_daily_reset") is not True
                or cell.get("synthetic_only") is not True
                or any(
                    cell.get(field) is not False
                    for field in (
                        "margin_calls_modeled",
                        "borrow_availability_modeled",
                        "security_level_financing_modeled",
                        "broker_liquidation_modeled",
                    )
                )
                or cell.get("orders_submitted") != 0
                or type(cell.get("orders_submitted")) is not int
                or cell.get("formal_accept_reject_disposition") is not None
            ):
                _error("preliminary objective leverage cell semantics changed")
            paths = {
                prefix: _validate_leverage_path(
                    cell,
                    prefix=prefix,
                    leverage_factor=leverage_factor,
                    annual_financing_rate=financing_rate,
                    return_count=expected_returns,
                )
                for prefix in _LEVERAGE_PATH_PREFIXES
            }
            selected_counts.add(paths["selected_"]["financing_session_count"])
            matched_counts.add(paths["matched_"]["financing_session_count"])
            selected_minus_matched = _cell_metric(
                cell.get("selected_minus_matched_cumulative_return"),
                "objective leverage selected-minus-matched",
            )
            selected_minus_spy = _cell_metric(
                cell.get("selected_minus_synthetic_spy_cumulative_return"),
                "objective leverage selected-minus-SPY",
            )
            with localcontext(preliminary_evaluator._context()):
                exact_matched = +(
                    paths["selected_"]["cumulative_return"]
                    - paths["matched_"]["cumulative_return"]
                )
                exact_spy = +(
                    paths["selected_"]["cumulative_return"]
                    - paths["synthetic_spy_"]["cumulative_return"]
                )
            if (
                selected_minus_matched != exact_matched
                or selected_minus_spy != exact_spy
            ):
                _error("preliminary objective leverage relative return changed")
            grid[(leverage_factor, scenario_id)] = paths
            cells.append(cell)

    if len(selected_counts) != 1 or len(matched_counts) != 1:
        _error("preliminary objective leverage path census invariance changed")
    for leverage_factor in _PINNED_LEVERAGE_FACTORS:
        primary_paths = grid[
            (leverage_factor, _PINNED_LEVERAGE_PRIMARY_SCENARIO_ID)
        ]
        adverse_paths = grid[
            (leverage_factor, _PINNED_LEVERAGE_ADVERSE_SCENARIO_ID)
        ]
        for prefix in _LEVERAGE_PATH_PREFIXES:
            if (
                primary_paths[prefix]["cumulative_return"]
                < adverse_paths[prefix]["cumulative_return"]
            ):
                _error("preliminary objective leverage scenario monotonicity changed")
        if (
            primary_paths["selected_"]["cumulative_return_before_financing"]
            < adverse_paths["selected_"]["cumulative_return_before_financing"]
            or primary_paths["matched_"]["cumulative_return_before_financing"]
            < adverse_paths["matched_"]["cumulative_return_before_financing"]
            or primary_paths["synthetic_spy_"][
                "cumulative_return_before_financing"
            ]
            != adverse_paths["synthetic_spy_"][
                "cumulative_return_before_financing"
            ]
        ):
            _error("preliminary objective leverage underlying path changed")

    summary_id = meta.get("summary_id")
    summary_sha = meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary objective leverage summary identity is absent")
    record = {
        key: value
        for key, value in meta.items()
        if key
        not in {
            "profile_id",
            "profile_sha256",
            "summary_id",
            "summary_sha256",
        }
    }
    record["profile"] = profile
    record["selected_base_aggregates"] = selected_raw
    record["matched_base_aggregates"] = matched_raw
    record["cells"] = cells
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-objective-leverage-summary-" + digest[:24]
    ):
        _error("preliminary objective leverage summary identity changed")


def _validate_six_universe_account_aggregate(
    value: object,
    *,
    role: str,
    annualization_sessions: Decimal,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != _SIX_UNIVERSE_ACCOUNT_FIELDS:
        _error("preliminary six-universe account fields changed")
    if (
        value.get("schema") != _PINNED_SIX_UNIVERSE_ACCOUNT_SCHEMA
        or value.get("role") != role
        or value.get("cost_bps_per_side")
        != _PINNED_SIX_UNIVERSE_PRIMARY_COST
        or value.get("return_session_count")
        != _PINNED_SIX_UNIVERSE_EXPECTED_RETURNS
        or value.get("return_metric_conditioning")
        != "per_name_stale_mark_carry_and_eligibility_exit_zero_recovery"
        or value.get("raw_price_rows_in_output") is not False
        or value.get("raw_security_ids_in_output") is not False
    ):
        _error("preliminary six-universe account semantics changed")
    count_fields = (
        "invested_return_session_count",
        "rebalance_count",
        "full_target_count",
        "underfilled_target_count",
        "locked_over_target_count",
        "entry_price_refusal_count",
        "stale_mark_session_count",
        "stale_position_deferral_count",
        "eligibility_exit_zero_recovery_count",
    )
    if any(
        type(value.get(field)) is not int
        or value[field] < 0
        or value[field] > _PINNED_SIX_UNIVERSE_EXPECTED_RETURNS
        for field in count_fields
    ):
        _error("preliminary six-universe account count changed")
    if (
        value["rebalance_count"] > _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
        or value["full_target_count"]
        + value["underfilled_target_count"]
        + value["locked_over_target_count"]
        != value["rebalance_count"]
        or value["invested_return_session_count"]
        < _PINNED_SIX_UNIVERSE_MINIMUM_INVESTED_RETURNS
    ):
        _error("preliminary six-universe account count invariants changed")
    decimal_fields = (
        "cumulative_return",
        "annualized_arithmetic_return",
        "maximum_drawdown",
        "average_daily_two_sided_turnover",
        "annualized_two_sided_turnover",
        "average_cash_weight",
        "mean_holding_count",
        "mean_target_effective_holdings",
        "maximum_target_weight",
    )
    metrics = {
        field: _cell_metric(
            value.get(field), "six-universe " + role + " " + field
        )
        for field in decimal_fields
    }
    nullable = {}
    for field in ("annualized_volatility", "zero_rate_sharpe"):
        raw = value.get(field)
        nullable[field] = (
            None
            if raw is None
            else _cell_metric(raw, "six-universe " + role + " " + field)
        )
    if (
        metrics["cumulative_return"] <= -1
        or not -1 <= metrics["maximum_drawdown"] <= 0
        or metrics["average_daily_two_sided_turnover"] < 0
        or metrics["annualized_two_sided_turnover"] < 0
        or not 0 <= metrics["average_cash_weight"] <= 1
        or metrics["mean_holding_count"] < 0
        or metrics["mean_target_effective_holdings"] < 0
        or not 0 <= metrics["maximum_target_weight"] <= 1
        or (
            nullable["annualized_volatility"] is not None
            and nullable["annualized_volatility"] < 0
        )
    ):
        _error("preliminary six-universe account metric escaped bounds")
    with localcontext() as context:
        context.prec = 96
        expected_annual_turnover = +(
            metrics["average_daily_two_sided_turnover"]
            * annualization_sessions
        )
    if metrics["annualized_two_sided_turnover"] != expected_annual_turnover:
        _error("preliminary six-universe account turnover arithmetic changed")
    volatility = nullable["annualized_volatility"]
    sharpe = nullable["zero_rate_sharpe"]
    if volatility is None:
        _error("preliminary six-universe account volatility is absent")
    if volatility == 0:
        if sharpe is not None:
            _error("preliminary six-universe account Sharpe arithmetic changed")
    else:
        with localcontext() as context:
            context.prec = 96
            expected_sharpe = +(metrics["annualized_arithmetic_return"] / volatility)
        if sharpe != expected_sharpe:
            _error("preliminary six-universe account Sharpe arithmetic changed")
    _sha(value.get("equity_return_path_sha256"), "six-universe return path")
    return value


def _validate_six_universe_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile_id = plan.projection.evaluation_profile_id
    profile_bytes, profile_sha256, _result_names = (
        _six_universe_profile_binding(profile_id)
    )
    profile = _strict_object(profile_bytes, "six-universe frozen profile")
    annualization_sessions = _cell_metric(
        profile.get("annualization_sessions"),
        "six-universe profile annualization sessions",
    )
    slot_count_per_sleeve = profile.get("slot_count_per_sleeve")
    if (
        annualization_sessions != _PINNED_SIX_UNIVERSE_ANNUALIZATION_SESSIONS
        or type(slot_count_per_sleeve) is not int
        or slot_count_per_sleeve < 1
    ):
        _error("preliminary six-universe profile economics changed")
    (
        meta_name,
        signal_name,
        matched_name,
        basket_name,
        sleeves_name,
        series_name,
        runtime_name,
    ) = _PINNED_SIX_UNIVERSE_STATISTIC_NAMES
    meta = records.get(meta_name)
    signal = records.get(signal_name)
    matched = records.get(matched_name)
    basket = records.get(basket_name)
    sleeves = records.get(sleeves_name)
    series = records.get(series_name)
    runtime = records.get(runtime_name)
    if type(meta) is not dict or set(meta) != _SIX_UNIVERSE_META_FIELDS:
        _error("preliminary six-universe metadata fields changed")
    if (
        meta.get("schema") != _PINNED_SIX_UNIVERSE_SUMMARY_SCHEMA
        or meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_SIX_UNIVERSE_GATE_COMPLETED"
        or meta.get("profile_id") != profile_id
        or meta.get("profile_sha256") != profile_sha256
        or meta.get("gate_profile_id") != profile.get("gate_profile_id")
        or meta.get("gate_profile_sha256")
        != profile.get("gate_profile_sha256")
        or meta.get("package_id") != plan.package_id
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("input_manifest_id") != plan.evaluator_manifest_id
        or meta.get("input_manifest_sha256")
        != plan.evaluator_manifest_sha256
        or meta.get("decision_session_count")
        != _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
        or meta.get("analyst_source_view")
        != _PINNED_SIX_UNIVERSE_SOURCE_VIEW
        or meta.get("point_in_time_etf_membership_and_market_cap") is not True
        or meta.get("point_in_time_analyst_archive") is not False
        or meta.get("current_vintage_identity_basis") is not True
        or meta.get("aggregate_only") is not True
        or meta.get("raw_rows_in_output") is not False
        or meta.get("orders") is not False
        or meta.get("deployment") is not False
        or meta.get("trading") is not False
    ):
        _error("preliminary six-universe metadata semantics changed")
    count_fields = (
        "price_history_batch_count",
        "pit_history_call_count",
        "pit_source_row_count",
    )
    if any(
        type(meta.get(field)) is not int or meta[field] < 0
        for field in count_fields
    ) or (
        meta["price_history_batch_count"] < 1
        or meta["price_history_batch_count"]
        > plan.package.runtime_symbol_binding_count + len(_PINNED_SIX_UNIVERSE_IDS)
        or meta["pit_source_row_count"]
        > _PINNED_SIX_UNIVERSE_RUNTIME_MAX_SOURCE_ROWS
    ):
        _error("preliminary six-universe metadata count changed")
    expected_pit_calls = (
        (
            _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
            + _PINNED_SIX_UNIVERSE_RUNTIME_HISTORY_CHUNK_DECISIONS
            - 1
        )
        // _PINNED_SIX_UNIVERSE_RUNTIME_HISTORY_CHUNK_DECISIONS
    ) * (1 + len(_PINNED_SIX_UNIVERSE_IDS))
    if meta["pit_history_call_count"] != expected_pit_calls:
        _error("preliminary six-universe PIT call census changed")
    for field in (
        "symbol_resolution_sha256",
        "construction_path_sha256",
        "result_fragments_sha256",
        "summary_sha256",
    ):
        _sha(meta.get(field), "six-universe " + field)
    _safe_name(
        meta.get("symbol_resolution_id"),
        "six-universe symbol resolution id",
        512,
    )

    signal = _validate_six_universe_account_aggregate(
        signal,
        role="signal",
        annualization_sessions=annualization_sessions,
    )
    matched = _validate_six_universe_account_aggregate(
        matched,
        role="matched",
        annualization_sessions=annualization_sessions,
    )
    basket = _validate_six_universe_account_aggregate(
        basket,
        role="six_etf_basket",
        annualization_sessions=annualization_sessions,
    )
    if (
        basket["invested_return_session_count"]
        != _PINNED_SIX_UNIVERSE_EXPECTED_RETURNS - 1
        or basket["rebalance_count"]
        != _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
        or basket["full_target_count"]
        != _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
        or any(
            basket[field] != 0
            for field in (
                "underfilled_target_count",
                "locked_over_target_count",
                "entry_price_refusal_count",
                "stale_mark_session_count",
                "stale_position_deferral_count",
                "eligibility_exit_zero_recovery_count",
            )
        )
    ):
        _error("preliminary six-universe ETF basket completeness changed")

    if type(sleeves) is not dict or set(sleeves) != _SIX_UNIVERSE_SLEEVES_FIELDS:
        _error("preliminary six-universe sleeve fields changed")
    sleeve_rows = sleeves.get("universes")
    if (
        sleeves.get("schema") != _PINNED_SIX_UNIVERSE_SLEEVE_SCHEMA
        or type(sleeve_rows) is not list
        or len(sleeve_rows) != len(_PINNED_SIX_UNIVERSE_IDS)
        or tuple(
            item.get("universe_id") if type(item) is dict else None
            for item in sleeve_rows
        )
        != _PINNED_SIX_UNIVERSE_IDS
    ):
        _error("preliminary six-universe sleeve inventory changed")
    for row in sleeve_rows:
        if type(row) is not dict or set(row) != _SIX_UNIVERSE_SLEEVE_FIELDS:
            _error("preliminary six-universe sleeve row fields changed")
        integer_fields = (
            "decision_count",
            "coverage_valid_count",
            "signal_full_etf_fallback_count",
            "signal_partial_etf_fallback_count",
            "matched_full_etf_fallback_count",
        )
        if any(
            type(row.get(field)) is not int
            or row[field] < 0
            or row[field] > _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS
            for field in integer_fields
        ) or row["decision_count"] != _PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS:
            _error("preliminary six-universe sleeve count changed")
        metric_fields = (
            "mean_positive_score_count",
            "mean_signal_stock_count",
            "mean_matched_stock_count",
            "minimum_mapping_ratio",
            "minimum_cap_weight_coverage_ratio",
        )
        values = {
            field: _cell_metric(
                row.get(field), "six-universe sleeve " + field
            )
            for field in metric_fields
        }
        if (
            any(values[field] < 0 for field in metric_fields[:3])
            or values["mean_signal_stock_count"]
            > Decimal(slot_count_per_sleeve)
            or values["mean_matched_stock_count"]
            > Decimal(slot_count_per_sleeve)
            or not 0 <= values["minimum_mapping_ratio"] <= 1
            or not 0 <= values["minimum_cap_weight_coverage_ratio"] <= 1
            or row["signal_full_etf_fallback_count"]
            + row["signal_partial_etf_fallback_count"]
            > row["decision_count"]
        ):
            _error("preliminary six-universe sleeve metric escaped bounds")

    if type(series) is not dict or set(series) != _SIX_UNIVERSE_SERIES_FIELDS:
        _error("preliminary six-universe series fields changed")
    series_rows = series.get("series")
    if (
        series.get("schema") != _PINNED_SIX_UNIVERSE_SERIES_SCHEMA
        or type(series_rows) is not list
        or len(series_rows) != len(_PINNED_SIX_UNIVERSE_IDS)
        or tuple(
            item.get("universe_id") if type(item) is dict else None
            for item in series_rows
        )
        != _PINNED_SIX_UNIVERSE_IDS
    ):
        _error("preliminary six-universe series inventory changed")
    for row in series_rows:
        if (
            type(row) is not dict
            or set(row) != _SIX_UNIVERSE_SERIES_ROW_FIELDS
            or row.get("normalization_mode") != "TOTAL_RETURN"
            or row.get("observation") != "session_open"
            or row.get("expected_session_count")
            != _PINNED_SIX_UNIVERSE_EXPECTED_SESSIONS
            or row.get("observation_count")
            != _PINNED_SIX_UNIVERSE_EXPECTED_SESSIONS
        ):
            _error("preliminary six-universe series semantics changed")
        _sha(row.get("raw_observation_sha256"), "six-universe raw series")
        _sha(row.get("used_return_path_sha256"), "six-universe used series")

    if type(runtime) is not dict or set(runtime) != _SIX_UNIVERSE_RUNTIME_FIELDS:
        _error("preliminary six-universe runtime fields changed")
    if (
        runtime.get("schema") != "arv2-six-universe-qc-runtime-meta-v1"
        or runtime.get("profile_id") != profile_id
        or runtime.get("profile_sha256") != profile_sha256
        or runtime.get("package_id") != plan.package_id
        or runtime.get("package_sha256") != plan.package_sha256
        or runtime.get("symbol_resolution_id")
        != meta.get("symbol_resolution_id")
        or runtime.get("symbol_resolution_sha256")
        != meta.get("symbol_resolution_sha256")
        or runtime.get("pit_history_call_count")
        != meta.get("pit_history_call_count")
        or runtime.get("pit_source_row_count")
        != meta.get("pit_source_row_count")
        or runtime.get("price_history_call_count")
        != meta.get("price_history_batch_count")
        or runtime.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or runtime.get("host_object_store_export_required") is not False
        or runtime.get("backtest_only") is not True
        or runtime.get("orders") is not False
        or runtime.get("deployment") is not False
        or runtime.get("trading") is not False
        or type(runtime.get("runtime_slice_count")) is not int
        or not 1
        <= runtime["runtime_slice_count"]
        <= _PINNED_SIX_UNIVERSE_RUNTIME_MAX_TRAIN_SLICES
    ):
        _error("preliminary six-universe runtime semantics changed")

    fragments = {
        "signal": signal,
        "matched": matched,
        "six_etf_basket": basket,
        "sleeves": sleeves,
        "series": series,
    }
    fragment_digest = hashlib.sha256(
        _canonical(
            {
                "schema": "arv2-six-universe-result-fragments-v1",
                **fragments,
            }
        )
    ).hexdigest()
    if meta.get("result_fragments_sha256") != fragment_digest:
        _error("preliminary six-universe result fragments changed")
    summary_id = meta.get("summary_id")
    summary_sha = meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary six-universe summary identity is absent")
    summary_meta = {
        key: value
        for key, value in meta.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    digest = hashlib.sha256(
        _canonical({"profile": profile, "meta": summary_meta, **fragments})
    ).hexdigest()
    if (
        summary_sha != digest
        or summary_id != "arv2-six-universe-summary-" + digest[:24]
    ):
        _error("preliminary six-universe summary identity changed")


def _validate_aggregate_records(
    records: Mapping[str, dict[str, object]],
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> None:
    profile_id = plan.projection.evaluation_profile_id
    if (
        type(records) is not dict
        or tuple(sorted(records)) != plan.expected_custom_statistic_names
    ):
        _error("preliminary aggregate result inventory changed")
    if profile_id is None:
        _validate_legacy_aggregate_records(records, plan)
        return
    if profile_id == etf_evaluator.PROFILE_ID:
        _validate_etf_aggregate_records(records, plan)
        return
    if profile_id in _PINNED_STOCK_PORTFOLIO_PROFILE_IDS:
        _validate_stock_portfolio_aggregate_records(records, plan)
        return
    if profile_id in _PINNED_MARKET_CAP_ALL_PROFILE_IDS:
        _validate_market_cap_aggregate_records(records, plan)
        return
    if profile_id in _PINNED_LEVERAGE_PROFILE_IDS:
        _validate_leverage_aggregate_records(records, plan)
        return
    if profile_id in _PINNED_SIX_UNIVERSE_PROFILE_IDS:
        _validate_six_universe_aggregate_records(records, plan)
        return
    _validate_regime_aggregate_records(records, plan, profile_id)


def _result_receipt_path(plan):
    return plan.control_directory / (
        "aggregate-result-" + plan.plan_sha256[:24] + ".json"
    )


def _load_result_receipt_impl(
    *, plan, execution_permit, launch, terminal, result_permit,
    require_launch, require_terminal, register_result,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    _require_result_permit_bytes(result_permit, plan, launch, terminal)
    path = _result_receipt_path(plan)
    payload = _read_private(path, "aggregate result receipt")
    raw = _strict_object(payload, "aggregate result receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "result_permit_sha256", "project_id",
        "backtest_id", "custom_statistics", "custom_statistics_sha256",
        "persisted_path", "backtests_read_call_count",
        "raw_provider_rows_selected", "logs_selected", "charts_selected",
        "orders_selected", "look_accounting",
    }:
        _error("preliminary aggregate result receipt fields changed")
    raw_pairs = raw.get("custom_statistics")
    if (
        type(raw_pairs) is not list
        or type(raw.get("persisted_path")) is not str
        or any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            for item in raw_pairs
        )
    ):
        _error("preliminary persisted custom statistics changed")
    pairs = tuple((item[0], item[1]) for item in raw_pairs)
    if tuple(name for name, _value in pairs) != plan.expected_custom_statistic_names:
        _error("preliminary persisted custom-statistic inventory changed")
    records: dict[str, dict[str, object]] = {}
    for name, value in pairs:
        try:
            encoded = value.encode("ascii")
        except UnicodeError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary persisted custom statistic is not ASCII"
            ) from exc
        if not encoded or len(encoded) > 4096:
            _error("preliminary persisted custom statistic is not bounded")
        records[name] = _strict_object(encoded, f"persisted custom statistic {name}")
    _validate_aggregate_records(records, plan)
    pairs_hash = hashlib.sha256(
        _canonical([list(item) for item in pairs])
    ).hexdigest()
    value = AcceptedRiskPreliminaryAggregateResult(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["launch_sha256"],
        raw["terminal_sha256"], raw["result_permit_sha256"],
        raw["project_id"], raw["backtest_id"], pairs,
        raw["custom_statistics_sha256"], Path(raw["persisted_path"]),
        raw["backtests_read_call_count"], raw["raw_provider_rows_selected"],
        raw["logs_selected"], raw["charts_selected"], raw["orders_selected"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.result_permit_sha256 != result_permit.permit_sha256
        or raw.get("look_accounting")
        != _look_accounting(
            stage="result",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        )
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or value.custom_statistics_sha256 != pairs_hash
        or value.persisted_path != path
        or value.backtests_read_call_count != 1
        or value.raw_provider_rows_selected is not False
        or value.logs_selected is not False
        or value.charts_selected is not False
        or value.orders_selected is not False
        or payload != _identified_receipt_bytes(
            schema=RESULT_RECEIPT_SCHEMA,
            prefix="arv2-preliminary-qc-result-",
            record=_result_record(value, plan),
            receipt_id=value.receipt_id,
            receipt_sha256=value.receipt_sha256,
        )
    ):
        _error("preliminary aggregate result receipt lineage changed")
    register_result(
        value, plan, execution_permit, launch, terminal, result_permit
    )
    return value


def _read_accepted_risk_preliminary_result_once_impl(
    *, plan, owner_signature, execution_permit, launch, terminal, client,
    started_at_utc, minter, signature_verifier, transport_verifier, require_launch,
    require_terminal, register_result,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    authority = _result_authority_bound(
        plan, execution_permit, launch, terminal, require_launch, require_terminal
    )
    signature = signature_verifier(owner_signature, authority)
    if terminal.terminal_status != "Completed.":
        _error("preliminary result read requires Completed.")
    transport_verifier(client)
    result_permit = _build_result_permit(
        plan, launch, terminal, signature, started_at_utc
    )
    try:
        _write_private_once(
            result_permit.permit_path,
            result_permit.permit_bytes,
            "result-read permit",
        )
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "result_read_permit", result_permit.permit_id,
            "permit already spent or unavailable",
        ) from exc
    _require_result_permit_bytes(result_permit, plan, launch, terminal)
    capability = minter(
        transport=client,
        scope="result_read",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-result-read-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal.receipt_sha256,
            "result_permit_sha256": result_permit.permit_sha256,
            "expected_custom_statistic_names_sha256": (
                plan.expected_custom_statistic_names_sha256
            ),
        },
        call_budget={"backtests/read": 1},
    )
    try:
        response = _transport(
            client,
            capability,
            "_read_backtest_result",
            launch.project_id,
            launch.backtest_id,
        )
        pairs = _parse_custom_result(response, plan, launch)
        pairs_hash = hashlib.sha256(
            _canonical([list(item) for item in pairs])
        ).hexdigest()
        path = _result_receipt_path(plan)
        record = {
            "plan_sha256": plan.plan_sha256,
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal.receipt_sha256,
            "result_permit_sha256": result_permit.permit_sha256,
            "look_accounting": _look_accounting(
                stage="result",
                evaluation_profile_id=plan.projection.evaluation_profile_id,
            ),
            "project_id": launch.project_id,
            "backtest_id": launch.backtest_id,
            "custom_statistics": [list(item) for item in pairs],
            "custom_statistics_sha256": pairs_hash,
            "persisted_path": str(path),
            "backtests_read_call_count": 1,
            "raw_provider_rows_selected": False,
            "logs_selected": False,
            "charts_selected": False,
            "orders_selected": False,
        }
        identity, digest, payload = _identified(
            RESULT_RECEIPT_SCHEMA, "arv2-preliminary-qc-result-", record
        )
        _write_private_once(path, payload, "aggregate result receipt")
        result = AcceptedRiskPreliminaryAggregateResult(
            identity,
            digest,
            plan.plan_sha256,
            launch.receipt_sha256,
            terminal.receipt_sha256,
            result_permit.permit_sha256,
            launch.project_id,
            launch.backtest_id,
            pairs,
            pairs_hash,
            path,
            1,
            False,
            False,
            False,
            False,
        )
        register_result(
            result, plan, execution_permit, launch, terminal, result_permit
        )
        return result_permit, result
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "result_read", result_permit.permit_id, type(exc).__name__
        ) from exc


def _result_authority_bound(plan, permit, launch, terminal, require_launch, require_terminal):
    require_launch(launch, plan, permit)
    require_terminal(terminal, plan, permit, launch)
    if terminal.terminal_status != "Completed.":
        _error("preliminary result-read authority requires Completed.")
    record = {
        "schema": RESULT_AUTHORITY_SCHEMA,
        "signature_purpose": "formal_qc_result_read",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "evaluator_manifest_id": plan.evaluator_manifest_id,
        "evaluator_manifest_sha256": plan.evaluator_manifest_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": terminal.terminal_status,
        "expected_custom_statistic_names": list(
            plan.expected_custom_statistic_names
        ),
        "expected_custom_statistic_names_sha256": (
            plan.expected_custom_statistic_names_sha256
        ),
        "host_code_closure": _require_host_closure(
            plan.host_closure
        ).to_record(),
        "look_accounting": _look_accounting(
            stage="launch",
            evaluation_profile_id=plan.projection.evaluation_profile_id,
        ),
        "actions": list(RESULT_ACTIONS),
        "maximum_backtests_read_calls": 1,
        "raw_provider_price_rows_logs_charts_orders_selected": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if plan.evaluation_profile_id is not None:
        record["evaluation_profile_id"] = plan.evaluation_profile_id
        record["evaluation_profile_sha256"] = plan.evaluation_profile_sha256
    return _canonical(record)


def _make_action_guard():
    expected: tuple[tuple[str, object], ...] = ()
    authority_pid = os.getpid()
    module_globals = globals()

    def seal(names: tuple[str, ...]) -> None:
        nonlocal expected
        if expected or type(names) is not tuple or not names:
            _error("preliminary action binding seal changed")
        expected = tuple((name, module_globals[name]) for name in names)

    def require(_phase: str) -> None:
        def globals_are_current() -> bool:
            return not any(
                module_globals.get(name) is not value
                for name, value in expected
            )

        if (
            os.getpid() != authority_pid
            or not globals_are_current()
            or not module_globals[
                "_stock_portfolio_contract_bindings_are_current"
            ]()
            or not module_globals[
                "_market_cap_contract_bindings_are_current"
            ]()
            or not module_globals[
                "_six_universe_contract_bindings_are_current"
            ]()
            or not globals_are_current()
        ):
            _error("preliminary action global binding changed")

    return seal, require


_seal_action_bindings, _require_action_bindings = _make_action_guard()
del _make_action_guard


def _bind_public_actions(
    *, minter, seal_minter, execute_impl, recover_impl, inspect_impl, read_impl,
    load_launch_impl, load_terminal_impl, load_result_permit_impl,
    load_result_receipt_impl,
    execution_signature_verifier, result_signature_verifier,
    transport_verifier,
    action_guard, register_launch, require_launch, register_terminal,
    require_terminal, register_result, require_result,
):
    def execute_accepted_risk_preliminary_submission_once(
        *, plan: AcceptedRiskPreliminarySubmissionPlan,
        owner_signature: OwnerSignatureAuthority | None,
        client: FormalQcTransport,
        started_at_utc: str,
    ):
        action_guard("submission")
        return execute_impl(
            plan=plan,
            owner_signature=owner_signature,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            register_launch=register_launch,
        )

    def require_accepted_risk_preliminary_launch_receipt(value, *, plan, permit):
        action_guard("launch require")
        return require_launch(value, plan, permit)

    def load_accepted_risk_preliminary_launch_receipt(*, plan, permit):
        action_guard("launch load")
        return load_launch_impl(
            plan=plan,
            permit=permit,
            register_launch=register_launch,
        )

    def recover_accepted_risk_preliminary_launch_once(
        *, plan, owner_signature, permit, client,
    ):
        action_guard("launch recovery")
        return recover_impl(
            plan=plan,
            owner_signature=owner_signature,
            permit=permit,
            client=client,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            load_launch=load_launch_impl,
            register_launch=register_launch,
        )

    def inspect_accepted_risk_preliminary_terminal_status(
        *, plan, owner_signature, permit, launch, client,
    ):
        action_guard("status")
        return inspect_impl(
            plan=plan,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            client=client,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            require_launch=require_launch,
            register_terminal=register_terminal,
        )

    def require_accepted_risk_preliminary_terminal_status(
        value, *, plan, permit, launch,
    ):
        action_guard("terminal require")
        return require_terminal(value, plan, permit, launch)

    def load_accepted_risk_preliminary_terminal_status(
        *, plan, permit, launch,
    ):
        action_guard("terminal load")
        return load_terminal_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            require_launch=require_launch,
            register_terminal=register_terminal,
        )

    def render_accepted_risk_preliminary_result_read_authority_candidate(
        *, plan, permit, launch, terminal,
    ) -> bytes:
        action_guard("result authority")
        return _result_authority_bound(
            plan, permit, launch, terminal, require_launch, require_terminal
        )

    def load_accepted_risk_preliminary_result_read_permit(
        *, plan, execution_permit, launch, terminal,
    ):
        action_guard("result permit load")
        return load_result_permit_impl(
            plan=plan,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            require_launch=require_launch,
            require_terminal=require_terminal,
        )

    def require_accepted_risk_preliminary_result_read_permit(
        value, *, plan, execution_permit, launch, terminal,
    ):
        action_guard("result permit require")
        plan = require_accepted_risk_preliminary_submission_plan(plan)
        _require_execution_permit_bytes(execution_permit, plan)
        require_launch(launch, plan, execution_permit)
        require_terminal(terminal, plan, execution_permit, launch)
        return _require_result_permit_bytes(value, plan, launch, terminal)

    def read_accepted_risk_preliminary_result_once(
        *, plan, execution_permit, launch, terminal,
        owner_signature, client, started_at_utc,
    ):
        action_guard("result read")
        return read_impl(
            plan=plan,
            owner_signature=owner_signature,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            signature_verifier=result_signature_verifier,
            transport_verifier=transport_verifier,
            require_launch=require_launch,
            require_terminal=require_terminal,
            register_result=register_result,
        )

    def require_accepted_risk_preliminary_aggregate_result(
        value, *, plan, execution_permit, launch, terminal, result_permit,
    ):
        action_guard("result require")
        if type(value) is not AcceptedRiskPreliminaryAggregateResult:
            _error("preliminary result receipt type changed")
        if _read_private(value.persisted_path, "aggregate result receipt") != _canonical(
            {
                "schema": RESULT_RECEIPT_SCHEMA,
                "id": value.receipt_id,
                "sha256": value.receipt_sha256,
                **_result_record(value, plan),
            }
        ):
            _error("persisted preliminary aggregate result changed")
        return require_result(
            value, plan, execution_permit, launch, terminal, result_permit
        )

    def load_accepted_risk_preliminary_aggregate_result(
        *, plan, execution_permit, launch, terminal, result_permit,
    ):
        action_guard("result load")
        return load_result_receipt_impl(
            plan=plan,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            result_permit=result_permit,
            require_launch=require_launch,
            require_terminal=require_terminal,
            register_result=register_result,
        )

    seal_minter(
        (
            (
                "submission",
                ((execute_impl, execute_accepted_risk_preliminary_submission_once),),
            ),
            (
                "status",
                (
                    (inspect_impl, inspect_accepted_risk_preliminary_terminal_status),
                    (recover_impl, recover_accepted_risk_preliminary_launch_once),
                ),
            ),
            (
                "result_read",
                ((read_impl, read_accepted_risk_preliminary_result_once),),
            ),
        )
    )
    return (
        execute_accepted_risk_preliminary_submission_once,
        require_accepted_risk_preliminary_launch_receipt,
        load_accepted_risk_preliminary_launch_receipt,
        recover_accepted_risk_preliminary_launch_once,
        inspect_accepted_risk_preliminary_terminal_status,
        require_accepted_risk_preliminary_terminal_status,
        load_accepted_risk_preliminary_terminal_status,
        render_accepted_risk_preliminary_result_read_authority_candidate,
        load_accepted_risk_preliminary_result_read_permit,
        require_accepted_risk_preliminary_result_read_permit,
        read_accepted_risk_preliminary_result_once,
        require_accepted_risk_preliminary_aggregate_result,
        load_accepted_risk_preliminary_aggregate_result,
    )


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_accepted_risk_preliminary_transport_capability_minter()

(
    execute_accepted_risk_preliminary_submission_once,
    require_accepted_risk_preliminary_launch_receipt,
    load_accepted_risk_preliminary_launch_receipt,
    recover_accepted_risk_preliminary_launch_once,
    inspect_accepted_risk_preliminary_terminal_status,
    require_accepted_risk_preliminary_terminal_status,
    load_accepted_risk_preliminary_terminal_status,
    render_accepted_risk_preliminary_result_read_authority_candidate,
    load_accepted_risk_preliminary_result_read_permit,
    require_accepted_risk_preliminary_result_read_permit,
    read_accepted_risk_preliminary_result_once,
    require_accepted_risk_preliminary_aggregate_result,
    load_accepted_risk_preliminary_aggregate_result,
) = _bind_public_actions(
    minter=_transport_capability_minter,
    seal_minter=_seal_transport_capability_callers,
    execute_impl=_execute_accepted_risk_preliminary_submission_once_impl,
    recover_impl=_recover_accepted_risk_preliminary_launch_once_impl,
    inspect_impl=_inspect_accepted_risk_preliminary_terminal_status_impl,
    read_impl=_read_accepted_risk_preliminary_result_once_impl,
    load_launch_impl=_load_launch_receipt_impl,
    load_terminal_impl=_load_terminal_receipt_impl,
    load_result_permit_impl=_load_result_permit_impl,
    load_result_receipt_impl=_load_result_receipt_impl,
    execution_signature_verifier=_require_execution_signature,
    result_signature_verifier=_require_result_signature,
    transport_verifier=_PINNED_REQUIRE_TRANSPORT,
    action_guard=_require_action_bindings,
    register_launch=_register_launch,
    require_launch=_require_launch,
    register_terminal=_register_terminal,
    require_terminal=_require_terminal,
    register_result=_register_result,
    require_result=_require_result,
)

_seal_action_bindings(
    (
        "build_accepted_risk_preliminary_submission_plan",
        "require_accepted_risk_preliminary_submission_plan",
        "persist_accepted_risk_preliminary_submission_plan",
        "load_accepted_risk_preliminary_submission_plan",
        "render_accepted_risk_preliminary_execution_authority_candidate",
        "execute_accepted_risk_preliminary_submission_once",
        "load_accepted_risk_preliminary_submission_permit",
        "load_accepted_risk_preliminary_pre_create_control",
        "require_accepted_risk_preliminary_launch_receipt",
        "load_accepted_risk_preliminary_launch_receipt",
        "recover_accepted_risk_preliminary_launch_once",
        "inspect_accepted_risk_preliminary_terminal_status",
        "require_accepted_risk_preliminary_terminal_status",
        "load_accepted_risk_preliminary_terminal_status",
        "render_accepted_risk_preliminary_result_read_authority_candidate",
        "load_accepted_risk_preliminary_result_read_permit",
        "require_accepted_risk_preliminary_result_read_permit",
        "read_accepted_risk_preliminary_result_once",
        "require_accepted_risk_preliminary_aggregate_result",
        "load_accepted_risk_preliminary_aggregate_result",
        "_PINNED_REQUIRE_PACKAGE",
        "_PINNED_ITER_UPLOADS",
        "_PINNED_REQUIRE_PROJECTION",
        "_PINNED_PROJECTION_PROFILE_CALLABLE",
        "_PINNED_PROJECTION_SOURCE_PATHS_CALLABLE",
        "_PINNED_PROJECTION_STOCK_SOURCE_PATHS",
        "_PINNED_PROJECTION_STOCK_PROFILE_IDS",
        "_PINNED_PROJECTION_STOCK_UNIVERSE_PROFILE_IDS",
        "_PINNED_PROJECTION_STOCK_PROFILE_SHA256S_OBJECT",
        "_PINNED_PROJECTION_STOCK_PROFILE_SHA256_ROWS",
        "_PINNED_PROJECTION_MARKET_CAP_SOURCE_PATHS",
        "_PINNED_PROJECTION_MARKET_CAP_LEGACY_SOURCE_PATHS",
        "_PINNED_PROJECTION_MARKET_CAP_PROFILE_IDS",
        "_PINNED_PROJECTION_MARKET_CAP_V1_PROFILE_IDS",
        "_PINNED_PROJECTION_MARKET_CAP_V2_PROFILE_IDS",
        "_PINNED_PROJECTION_MARKET_CAP_V3_PROFILE_IDS",
        "_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_IDS",
        "_PINNED_PROJECTION_SUPERSEDED_UNSPENT_PROFILE_IDS",
        "_PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256S_OBJECT",
        "_PINNED_PROJECTION_MARKET_CAP_PROFILE_SHA256_ROWS",
        "_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256S_OBJECT",
        "_PINNED_PROJECTION_MARKET_CAP_ALL_PROFILE_SHA256_ROWS",
        "_PINNED_PROJECTION_LEVERAGE_SOURCE_PATHS",
        "_PINNED_PROJECTION_LEVERAGE_PROFILE_IDS",
        "_PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256S_OBJECT",
        "_PINNED_PROJECTION_LEVERAGE_PROFILE_SHA256_ROWS",
        "_PINNED_PROJECTION_SIX_UNIVERSE_SOURCE_PATHS",
        "_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_IDS",
        "_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256S_OBJECT",
        "_PINNED_PROJECTION_SIX_UNIVERSE_PROFILE_SHA256_ROWS",
        "_PINNED_EXPECTED_RESULT_NAMES",
        "_PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE",
        "_PINNED_MAX_TRAIN_SLICE_COUNT",
        "_PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_ID",
        "_PINNED_RUNTIME_STOCK_PORTFOLIO_PROFILE_IDS",
        "_PINNED_RUNTIME_STOCK_UNIVERSE_PROFILE_IDS",
        "_PINNED_RUNTIME_STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS",
        "_PINNED_RUNTIME_STOCK_MEMBERSHIP_ONLY_PROFILE_IDS",
        "_PINNED_REQUIRE_REGIME_PROFILE",
        "_PINNED_REQUIRE_STOCK_PORTFOLIO_PROFILE",
        "_PINNED_STOCK_PORTFOLIO_RESULT_NAMES_CALLABLE",
        "_PINNED_STOCK_PORTFOLIO_CONSTITUENT_TICKERS_CALLABLE",
        "_PINNED_STOCK_PORTFOLIO_SNAPSHOT_MAXIMUM_AGE_CALLABLE",
        "_PINNED_STOCK_PORTFOLIO_POSITIVE_COUNT_BOUNDS_CALLABLE",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_OBJECT",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_ID",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_IDS",
        "_PINNED_STOCK_PORTFOLIO_VARIANT_PROFILE_IDS",
        "_PINNED_STOCK_PORTFOLIO_UNIVERSE_PROFILE_IDS",
        "_PINNED_STOCK_PORTFOLIO_STATE_UNTIL_SUPERSEDED_PROFILE_IDS",
        "_PINNED_STOCK_PORTFOLIO_MEMBERSHIP_ONLY_PROFILE_IDS",
        "_PINNED_STOCK_PORTFOLIO_CANONICAL_ROWS_OBJECT",
        "_PINNED_STOCK_PORTFOLIO_CONTRACT_ID",
        "_PINNED_STOCK_PORTFOLIO_SUMMARY_SCHEMA",
        "_PINNED_STOCK_PORTFOLIO_CELL_SCHEMA",
        "_PINNED_STOCK_PORTFOLIO_EXPECTED_DECISIONS",
        "_PINNED_STOCK_PORTFOLIO_EXPECTED_RETURNS",
        "_PINNED_STOCK_PORTFOLIO_MAXIMUM_HOLDINGS",
        "_PINNED_STOCK_PORTFOLIO_MINIMUM_INVESTED_RETURNS",
        "_PINNED_STOCK_PORTFOLIO_COSTS",
        "_PINNED_STOCK_PORTFOLIO_PRIMARY_COST",
        "_PINNED_STOCK_PORTFOLIO_ANNUALIZATION_SESSIONS",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_BINDINGS",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_BYTES",
        "_PINNED_STOCK_PORTFOLIO_PROFILE_SHA256",
        "_PINNED_STOCK_PORTFOLIO_RESULT_NAMES",
        "_PINNED_REQUIRE_MARKET_CAP_PROFILE",
        "_PINNED_MARKET_CAP_RESULT_NAMES_CALLABLE",
        "_PINNED_MARKET_CAP_CONSTITUENT_TICKERS_CALLABLE",
        "_PINNED_MARKET_CAP_PROFILE_IDS",
        "_PINNED_MARKET_CAP_V1_PROFILE_IDS",
        "_PINNED_MARKET_CAP_V2_PROFILE_IDS",
        "_PINNED_MARKET_CAP_V3_PROFILE_IDS",
        "_PINNED_MARKET_CAP_TILT_PROFILE_IDS",
        "_PINNED_MARKET_CAP_ALL_PROFILE_IDS",
        "_PINNED_MARKET_CAP_QQQ_PROFILE_IDS",
        "_PINNED_MARKET_CAP_SPY_PROFILE_IDS",
        "_PINNED_MARKET_CAP_PROFILE_CANONICAL_OBJECT",
        "_PINNED_MARKET_CAP_PROFILE_CANONICAL_ROWS",
        "_PINNED_MARKET_CAP_CONTRACT_ID",
        "_PINNED_MARKET_CAP_SUMMARY_SCHEMA",
        "_PINNED_MARKET_CAP_CELL_SCHEMA",
        "_PINNED_MARKET_CAP_META_STATISTIC_NAME",
        "_PINNED_MARKET_CAP_SELECTED_AGGREGATES_STATISTIC_NAME",
        "_PINNED_MARKET_CAP_MATCHED_AGGREGATES_STATISTIC_NAME",
        "_PINNED_MARKET_CAP_TILT_AGGREGATES_STATISTIC_NAME",
        "_PINNED_MARKET_CAP_TILT_AGGREGATES_SCHEMA",
        "_PINNED_MARKET_CAP_MAXIMUM_HOLDINGS",
        "_PINNED_MARKET_CAP_TARGET_GROSS",
        "_PINNED_MARKET_CAP_PORTFOLIO_WEIGHT_QUANTUM",
        "_PINNED_MARKET_CAP_MINIMUM_TILT_RANKED_NAMES",
        "_PINNED_MARKET_CAP_MINIMUM_TILT_POSITIVE_SCORES",
        "_PINNED_MARKET_CAP_MINIMUM_TILT_NEGATIVE_SCORES",
        "_PINNED_MARKET_CAP_MAXIMUM_RELATIVE_TILT",
        "_PINNED_MARKET_CAP_MAXIMUM_ABSOLUTE_OVERWEIGHT",
        "_PINNED_MARKET_CAP_MAXIMUM_ONE_WAY_ACTIVE_SHARE",
        "_PINNED_MARKET_CAP_MAXIMUM_HHI_MULTIPLE",
        "_PINNED_MARKET_CAP_MINIMUM_INVESTED_RETURNS",
        "_PINNED_MARKET_CAP_COSTS",
        "_PINNED_MARKET_CAP_PRIMARY_COST",
        "_PINNED_MARKET_CAP_ANNUALIZATION_SESSIONS",
        "_PINNED_MARKET_CAP_RUNTIME_EXPECTED_NAMES",
        "_PINNED_MARKET_CAP_RUNTIME_PROFILE_IDS",
        "_PINNED_MARKET_CAP_RUNTIME_MAX_TRAIN_SLICES",
        "_PINNED_MARKET_CAP_RUNTIME_MAX_HISTORY_CHUNKS",
        "_PINNED_MARKET_CAP_RUNTIME_HISTORY_CHUNK_DECISIONS",
        "_PINNED_MARKET_CAP_RUNTIME_MAX_TOTAL_SOURCE_ROWS",
        "_PINNED_MARKET_CAP_PROFILE_BINDINGS",
        "_PINNED_REQUIRE_LEVERAGE_PROFILE",
        "_PINNED_LEVERAGE_RESULT_NAMES_CALLABLE",
        "_PINNED_LEVERAGE_PROFILE_IDS",
        "_PINNED_LEVERAGE_V1_PROFILE_IDS",
        "_PINNED_LEVERAGE_V2_PROFILE_IDS",
        "_PINNED_LEVERAGE_ALL_PROFILE_IDS",
        "_PINNED_LEVERAGE_PROFILE_CANONICAL_OBJECT",
        "_PINNED_LEVERAGE_PROFILE_CANONICAL_ROWS",
        "_PINNED_LEVERAGE_CONTRACT_ID",
        "_PINNED_LEVERAGE_SUMMARY_SCHEMA",
        "_PINNED_LEVERAGE_CELL_SCHEMA",
        "_PINNED_LEVERAGE_META_STATISTIC_NAME",
        "_PINNED_LEVERAGE_SELECTED_BASE_AGGREGATES_STATISTIC_NAME",
        "_PINNED_LEVERAGE_MATCHED_BASE_AGGREGATES_STATISTIC_NAME",
        "_PINNED_LEVERAGE_BASE_SOURCE_SHA256",
        "_PINNED_LEVERAGE_FACTORS",
        "_PINNED_LEVERAGE_SCENARIOS",
        "_PINNED_LEVERAGE_PRIMARY_SCENARIO_ID",
        "_PINNED_LEVERAGE_ADVERSE_SCENARIO_ID",
        "_PINNED_LEVERAGE_ANNUALIZATION_SESSIONS",
        "_PINNED_LEVERAGE_RUNTIME_EXPECTED_NAMES",
        "_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_CALLABLE",
        "_PINNED_LEVERAGE_RUNTIME_CONSTITUENT_TICKERS_CALLABLE",
        "_PINNED_LEVERAGE_RUNTIME_PROFILE_IDS",
        "_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_MAP_OBJECT",
        "_PINNED_LEVERAGE_RUNTIME_BASE_PROFILE_ROWS",
        "_PINNED_LEVERAGE_RUNTIME_SCHEMA",
        "_PINNED_LEVERAGE_RUNTIME_STATUS",
        "_PINNED_LEVERAGE_RUNTIME_MAX_TRAIN_SLICES",
        "_PINNED_LEVERAGE_PROFILE_BINDINGS",
        "_PINNED_REQUIRE_SIX_UNIVERSE_PROFILE",
        "_PINNED_SIX_UNIVERSE_RESULT_NAMES_CALLABLE",
        "_PINNED_SIX_UNIVERSE_PROFILE_IDS",
        "_PINNED_SIX_UNIVERSE_PROFILE_BINDINGS",
        "_PINNED_SIX_UNIVERSE_PROFILE_SCHEMA",
        "_PINNED_SIX_UNIVERSE_SUMMARY_SCHEMA",
        "_PINNED_SIX_UNIVERSE_ACCOUNT_SCHEMA",
        "_PINNED_SIX_UNIVERSE_SLEEVE_SCHEMA",
        "_PINNED_SIX_UNIVERSE_SERIES_SCHEMA",
        "_PINNED_SIX_UNIVERSE_STATISTIC_NAMES",
        "_PINNED_SIX_UNIVERSE_DECISION_START",
        "_PINNED_SIX_UNIVERSE_EVALUATION_END",
        "_PINNED_SIX_UNIVERSE_EXPECTED_SESSIONS",
        "_PINNED_SIX_UNIVERSE_EXPECTED_RETURNS",
        "_PINNED_SIX_UNIVERSE_EXPECTED_DECISIONS",
        "_PINNED_SIX_UNIVERSE_PRIMARY_COST",
        "_PINNED_SIX_UNIVERSE_MODELED_COST_RATE",
        "_PINNED_SIX_UNIVERSE_ANNUALIZATION_SESSIONS",
        "_PINNED_SIX_UNIVERSE_GATE_SCORE_QUANTUM",
        "_PINNED_SIX_UNIVERSE_MINIMUM_INVESTED_RETURNS",
        "_PINNED_SIX_UNIVERSE_TARGET_GROSS",
        "_PINNED_SIX_UNIVERSE_IDS",
        "_PINNED_SIX_UNIVERSE_SOURCE_VIEW",
        "_PINNED_SIX_UNIVERSE_RUNTIME_MAX_TRAIN_SLICES",
        "_PINNED_SIX_UNIVERSE_RUNTIME_WORK_UNITS",
        "_PINNED_SIX_UNIVERSE_RUNTIME_HISTORY_CHUNK_DECISIONS",
        "_PINNED_SIX_UNIVERSE_RUNTIME_MAX_SOURCE_ROWS",
        "_PINNED_JSON_DUMPS",
        "_PINNED_REQUIRE_EXECUTION_SIGNATURE",
        "_PINNED_REQUIRE_RESULT_SIGNATURE",
        "_PINNED_LOAD_INFRASTRUCTURE_LEDGER",
        "_PINNED_REQUIRE_INFRASTRUCTURE_LEDGER",
        "_PINNED_INFRASTRUCTURE_LEDGER",
        "_PINNED_REQUIRE_TRANSPORT",
        "_PINNED_TRANSPORT_CALL",
        "_PINNED_READ_PROJECTS",
        "_PINNED_PROJECT_RECORD",
        "_PINNED_CREATED_PROJECT",
        "_PINNED_READ_FILES",
        "_PINNED_SUCCESS",
        "_PINNED_OBJECT_METADATA",
        "_PINNED_COMPILE_ID",
        "_PINNED_COMPILE_STATE",
        "_PINNED_CREATED_BACKTEST",
        "_PINNED_PARSE_STATUS",
        "_PINNED_PARSE_UNIQUE_RUN",
        "_PINNED_LEXISTS",
        "_PINNED_SCANDIR",
        "_PINNED_BACKTEST_STATUS_KEYS",
        "_PINNED_DISCARDED_BACKTEST_KEYS",
        "_PINNED_COMPILE_TERMINAL_STATES",
        "_PINNED_BACKTEST_TERMINAL_STATES",
        "PLAN_SCHEMA",
        "REGIME_PLAN_SCHEMA",
        "EXECUTION_AUTHORITY_SCHEMA",
        "EXECUTION_PERMIT_SCHEMA",
        "PRECREATE_CONTROL_SCHEMA",
        "LAUNCH_RECOVERY_PERMIT_SCHEMA",
        "LAUNCH_SCHEMA",
        "TERMINAL_SCHEMA",
        "RESULT_AUTHORITY_SCHEMA",
        "RESULT_PERMIT_SCHEMA",
        "RESULT_RECEIPT_SCHEMA",
        "UPLOAD_ENTRY_SCHEMA",
        "HOST_CLOSURE_SCHEMA",
        "MAX_CONTROL_BYTES",
        "MAX_HOST_SOURCE_BYTES",
        "MAX_PROJECT_NAME_BYTES",
        "MAX_BACKTEST_NAME_BYTES",
        "MAX_COMPILE_POLLS",
        "MAX_STATUS_POLLS",
        "COMPILE_POLL_SECONDS",
        "STATUS_POLL_SECONDS",
        "QC_DEFAULT_RESEARCH_NOTEBOOK_PATH",
        "RECOVERED_LAUNCH_INITIAL_STATUS",
        "HOST_CODE_DIRECTORY_PATHS",
        "HOST_CODE_PATHS",
        "EXECUTION_ACTIONS",
        "RESULT_ACTIONS",
        "_HEX",
        "_SAFE_NAME",
        "_CELL_NAME",
        "_CELL_FIELDS",
        "_RUNTIME_META_FIELDS",
        "_PRELIMINARY_META_FIELDS",
        "_REGIME_RUNTIME_META_FIELDS",
        "_REGIME_CELL_FIELDS",
        "_REGIME_META_FIELDS",
        "_ETF_RUNTIME_META_FIELDS",
        "_ETF_META_FIELDS",
        "_ETF_IC_FIELDS",
        "_ETF_PORTFOLIO_FIELDS",
        "_STOCK_PORTFOLIO_RUNTIME_META_FIELDS",
        "_STOCK_PORTFOLIO_META_FIELDS",
        "_STOCK_PORTFOLIO_CELL_FIELDS",
        "_MARKET_CAP_RUNTIME_META_FIELDS",
        "_MARKET_CAP_META_FIELDS",
        "_MARKET_CAP_TILT_META_FIELDS",
        "_MARKET_CAP_ACCOUNT_FIELDS",
        "_MARKET_CAP_TILT_ACCOUNT_FIELDS",
        "_MARKET_CAP_TILT_FIELDS",
        "_MARKET_CAP_CELL_FIELDS",
        "_LEVERAGE_RUNTIME_META_FIELDS",
        "_LEVERAGE_META_FIELDS",
        "_LEVERAGE_PATH_PREFIXES",
        "_LEVERAGE_PATH_SUFFIXES",
        "_LEVERAGE_CELL_FIELDS",
        "_SIX_UNIVERSE_META_FIELDS",
        "_SIX_UNIVERSE_ACCOUNT_FIELDS",
        "_SIX_UNIVERSE_SLEEVES_FIELDS",
        "_SIX_UNIVERSE_SLEEVE_FIELDS",
        "_SIX_UNIVERSE_SERIES_FIELDS",
        "_SIX_UNIVERSE_SERIES_ROW_FIELDS",
        "_SIX_UNIVERSE_RUNTIME_FIELDS",
        "_CELL_COUNT_FIELDS",
        "_REGIME_MISSING_COUNT_FIELDS",
        "_CELL_METRIC_FIELDS",
        "_REGIME_PROFILE_NAME_TOKENS",
        "_EXPECTED_OUTCOME_AVAILABILITY_DISCLOSURES",
        "_DECIMAL_METRIC",
        "AcceptedRiskPreliminarySubmissionError",
        "AcceptedRiskPreliminarySubmissionLocked",
        "AcceptedRiskPreliminaryTerminalFailure",
        "AcceptedRiskPreliminaryHostSourceBinding",
        "AcceptedRiskPreliminaryHostClosureBinding",
        "AcceptedRiskPreliminaryUploadEntry",
        "AcceptedRiskPreliminarySubmissionPlan",
        "AcceptedRiskPreliminarySubmissionPermit",
        "AcceptedRiskPreliminaryPreCreateControl",
        "AcceptedRiskPreliminaryLaunchReceipt",
        "AcceptedRiskPreliminaryTerminalStatus",
        "AcceptedRiskPreliminaryResultReadPermit",
        "AcceptedRiskPreliminaryAggregateResult",
        "_EvaluationRunSpec",
        "_EVALUATION_RUN_SPECS",
        "_SUPERSEDED_UNSPENT_PROFILE_IDS",
        "_require_fresh_launch_profile",
        "_stock_portfolio_profile_binding",
        "_market_cap_profile_binding",
        "_leverage_profile_binding",
        "_six_universe_profile_binding",
        "_error",
        "_canonical",
        "_stock_portfolio_contract_bindings_are_current",
        "_market_cap_contract_bindings_are_current",
        "_leverage_contract_bindings_are_current",
        "_six_universe_contract_bindings_are_current",
        "_strict_object",
        "_sha",
        "_safe_name",
        "_utc",
        "_private_directory",
        "_read_private",
        "_write_private_once",
        "_identified",
        "_read_host_source",
        "_walk_host_python_sources",
        "_host_code_inventory_paths",
        "_build_host_closure",
        "_require_host_closure",
        "_upload_entries",
        "_plan_record",
        "_submission_plan_path",
        "_submission_plan_bytes",
        "_execution_authority",
        "_require_execution_signature",
        "_require_result_signature",
        "_execution_permit_path",
        "_build_execution_permit",
        "_spend_execution_permit",
        "_require_execution_permit_bytes",
        "_precreate_control_path",
        "_build_precreate_control",
        "_require_precreate_control",
        "_launch_recovery_permit_path",
        "_launch_recovery_permit_record",
        "_spend_launch_recovery_permit",
        "_require_launch_recovery_permit",
        "_launch_record",
        "_terminal_record",
        "_result_record",
        "_launch_receipt_path",
        "_terminal_receipt_path",
        "_identified_receipt_bytes",
        "_launch_receipt_bytes",
        "_terminal_receipt_bytes",
        "_wait",
        "_transport",
        "_new_launch",
        "_new_terminal",
        "_result_permit_path",
        "_build_result_permit",
        "_require_result_permit_bytes",
        "_parse_custom_result",
        "_authenticated_evaluator_manifest",
        "_cell_metric",
        "_outcome_availability_disclosures",
        "_validate_cell_semantics",
        "_require_runtime_meta",
        "_validate_legacy_aggregate_records",
        "_regime_axis_inventory",
        "_validate_regime_cell_semantics",
        "_validate_regime_aggregate_records",
        "_validate_etf_aggregate_records",
        "_validate_stock_portfolio_aggregate_records",
        "_validate_market_cap_account_aggregate",
        "_validate_market_cap_tilt_aggregate",
        "_validate_market_cap_aggregate_records",
        "_validate_leverage_path",
        "_validate_leverage_aggregate_records",
        "_validate_six_universe_account_aggregate",
        "_validate_six_universe_aggregate_records",
        "_validate_aggregate_records",
        "_result_receipt_path",
        "_result_authority_bound",
        "_look_accounting",
        "_run_spec",
        "_expected_result_names",
        "dataclasses",
        "hashlib",
        "json",
        "os",
        "re",
        "stat",
        "threading",
        "time",
        "weakref",
        "datetime",
        "timezone",
        "Decimal",
        "InvalidOperation",
        "localcontext",
        "Path",
        "package_builder",
        "projection_builder",
        "preregistration",
        "preliminary_runtime",
        "preliminary_evaluator",
        "regime_evaluator",
        "etf_evaluator",
        "etf_runtime",
        "stock_portfolio_evaluator",
        "market_cap_evaluator",
        "market_cap_runtime",
        "leverage_evaluator",
        "leverage_runtime",
        "six_universe_gate",
        "six_universe_evaluator",
        "six_universe_runtime",
        "formal",
        "FormalQcTransport",
        "OwnerSignatureAuthority",
        "OwnerSignatureAuthorityError",
    )
)

del _transport_capability_minter
del _seal_transport_capability_callers
del _bind_public_actions
del _execute_accepted_risk_preliminary_submission_once_impl
del _recover_accepted_risk_preliminary_launch_once_impl
del _inspect_accepted_risk_preliminary_terminal_status_impl
del _read_accepted_risk_preliminary_result_once_impl
del _load_launch_receipt_impl
del _load_terminal_receipt_impl
del _load_result_permit_impl
del _load_result_receipt_impl
del _register_launch
del _require_launch
del _register_terminal
del _require_terminal
del _register_result
del _require_result
del _seal_action_bindings
del _require_action_bindings


__all__ = (
    "AcceptedRiskPreliminaryAggregateResult",
    "AcceptedRiskPreliminaryHostClosureBinding",
    "AcceptedRiskPreliminaryHostSourceBinding",
    "AcceptedRiskPreliminaryLaunchReceipt",
    "AcceptedRiskPreliminaryPreCreateControl",
    "AcceptedRiskPreliminaryResultReadPermit",
    "AcceptedRiskPreliminarySubmissionError",
    "AcceptedRiskPreliminarySubmissionLocked",
    "AcceptedRiskPreliminarySubmissionPermit",
    "AcceptedRiskPreliminarySubmissionPlan",
    "AcceptedRiskPreliminaryTerminalFailure",
    "AcceptedRiskPreliminaryTerminalStatus",
    "AcceptedRiskPreliminaryUploadEntry",
    "build_accepted_risk_preliminary_submission_plan",
    "execute_accepted_risk_preliminary_submission_once",
    "inspect_accepted_risk_preliminary_terminal_status",
    "load_accepted_risk_preliminary_aggregate_result",
    "load_accepted_risk_preliminary_launch_receipt",
    "load_accepted_risk_preliminary_pre_create_control",
    "load_accepted_risk_preliminary_result_read_permit",
    "load_accepted_risk_preliminary_submission_permit",
    "load_accepted_risk_preliminary_submission_plan",
    "load_accepted_risk_preliminary_terminal_status",
    "persist_accepted_risk_preliminary_submission_plan",
    "recover_accepted_risk_preliminary_launch_once",
    "read_accepted_risk_preliminary_result_once",
    "render_accepted_risk_preliminary_execution_authority_candidate",
    "render_accepted_risk_preliminary_result_read_authority_candidate",
    "require_accepted_risk_preliminary_aggregate_result",
    "require_accepted_risk_preliminary_launch_receipt",
    "require_accepted_risk_preliminary_result_read_permit",
    "require_accepted_risk_preliminary_submission_permit",
    "require_accepted_risk_preliminary_submission_plan",
    "require_accepted_risk_preliminary_terminal_status",
)
