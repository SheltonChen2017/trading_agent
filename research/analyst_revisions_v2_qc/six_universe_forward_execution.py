"""Declarative prospective execution freeze and source-recomputed arm matching.

This diagnostic authenticates supplied bytes and calendar/clock consistency.
It emits no targets, quantities or orders and cannot establish independent
price provenance, execution parity, fills, an evidence epoch or paper authority.
The declared sizing, cash and sell-reconciliation rules require a future
independently reviewed adapter before they can govern simulated execution.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from data.exchange_calendar import (
    ExchangeCalendarError, parse_session_date, session_close_instant,
    session_open_instant, trading_sessions,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, canonical_json_bytes, require_canonical_json_bytes,
    require_sha256, strict_json_loads,
)

from . import six_universe_forward_construction_policy as construction
from . import six_universe_forward_predecision as predecision
from . import six_universe_forward_stock_selection_policy as selection


class ForwardExecutionError(ValueError):
    """A policy, source pin, calendar or matched-arm configuration refused."""


POLICY_PATH = Path(__file__).with_suffix(".json")
FROZEN_POLICY_SHA256 = "817d7db82da6f657af4344539689b91a084494f4c9ecb1ad68d1b19c66e193a1"
CONSTRUCTION_POLICY_SHA256 = "7f1dbfe54f8179add6db9b15abdf343e55253ba50541175a5764e4c15dc644d4"
SELECTION_POLICY_SHA256 = "b691699baf506f8d7ef142439094527a936c73b37d3a2d39ed075315888bfcd0"
SCHEMA = "arv2-six-forward-matched-execution-diagnostic-v1"
CONFIGURATION_SCHEMA = "arv2-six-forward-matched-arm-configuration-v1"
CANDIDATE_IDS = ("ARV2_FORWARD_AR_OFF", "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200")
NEW_YORK = ZoneInfo("America/New_York")
_FALSE_CAPABILITIES = {
    "confirmatory_look_commitment": False, "funded_deployment": False,
    "orders": False, "outcome_access": False, "paper_deployment": False,
    "qc_compile": False, "qc_launch": False, "qc_upload": False,
}
_EXPECTED = {
    "schema": "arv2-six-universe-forward-execution-policy-v1",
    "construction_policy_sha256": CONSTRUCTION_POLICY_SHA256,
    "stock_selection_policy_sha256": SELECTION_POLICY_SHA256,
    "candidate_ids": list(CANDIDATE_IDS),
    "capabilities": _FALSE_CAPABILITIES,
    "decision_ready": False,
    "execution_adapter_implemented": False,
    "convention_disclosure": "new_prospective_convention_not_historical_after_close_next_session_MOO_replay",
    "schedule": {
        "input_and_valuation_frequency": "daily_NYSE_sessions",
        "rebalance_frequency": "first_NYSE_session_of_each_ISO_week",
        "decision_cutoff": "same_session_09:20:00_America/New_York",
        "planned_execution_session": "same_as_decision_session",
        "planned_market_order_start": "actual_NYSE_open_plus_one_minute",
        "planned_start_is_actual_fill_claim": False,
    },
    "reference_price": {
        "normalization": "RAW",
        "clock": "immediately_prior_NYSE_session_actual_close",
        "identical_source_bytes_for_all_arms": True,
        "independent_origin_proven": False,
    },
    "initial_simulated_account": {
        "currency": "USD", "nav_usd": "1000000", "cash_usd": "1000000",
        "positions": [],
    },
    "declared_economics": {
        "fee_bps_per_side": "10", "baseline_adverse_slippage_bps": "0",
        "AR_100_and_200_are_weight_transfer_fractions_not_leverage": True,
    },
    "declared_adapter_requirements": {
        "share_rounding": "whole_share_floor_NAV_times_target_weight_divided_by_RAW_reference_price",
        "target_gross_exposure": "0.98", "rounding_residue": "cash",
        "short_positions_allowed": False, "leverage_allowed": False,
        "sequence": "sells_before_buys",
        "sell_state": "actual_reconciled_sell_state_required_before_buy_budget",
        "buy_cash_gate": "actual_reconciled_cash_including_fees_required_before_buys",
        "policy_text_enforces_adapter_rules": False,
    },
    "pending_bindings": {
        "raw_reference_price_source_sha256": None,
        "matched_predecision_input_sha256": None,
        "stock_selection_target_implementation_sha256": None,
        "order_adapter_sha256": None,
        "independent_execution_parity_sha256": None,
        "actual_fill_source_sha256": None,
        "paper_epoch_sha256": None,
        "confirmatory_protocol_sha256": None,
        "qc_paper_project_mode_epoch_permit_sha256": None,
    },
}
_INPUT_KEYS = frozenset({
    "decision_session", "qc_snapshot_bytes", "qc_snapshot_sha256",
    "vendor_receipt_bytes", "vendor_receipt_sha256", "crosswalk_bytes",
    "crosswalk_sha256", "holdings_identity_bytes", "holdings_identity_sha256",
    "reference_price_bytes", "reference_price_sha256",
})
_ADDITIONAL_REFUSALS = (
    "RAW_PREVIOUS_CLOSE_PRICE_PROVENANCE_UNPROVEN",
    "AUTHENTICATED_AR_SCORE_INPUT_UNBOUND",
    "OWN_ETF_SECURITY_IDENTITY_UNPROVEN",
    "EXECUTION_ADAPTER_AND_PARITY_UNPROVEN",
    "FORWARD_EVIDENCE_EPOCH_UNBOUND",
)


def _exact(left, right):
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        return left.keys() == right.keys() and all(_exact(left[key], item) for key, item in right.items())
    if type(right) is list:
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right))
    return left == right


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def validate_policy(value):
    """Authenticate exact child fields and types, including all-false authority."""
    if not _exact(value, _EXPECTED):
        raise ForwardExecutionError("EXECUTION_POLICY_CHANGED")
    return value


def load_policy():
    """Read only the immutable child and authenticate its reviewed parent chain."""
    try:
        raw = POLICY_PATH.read_bytes()
    except OSError as exc:
        raise ForwardExecutionError("EXECUTION_POLICY_UNAVAILABLE") from exc
    if len(raw) > 16_384 or hashlib.sha256(raw).hexdigest() != FROZEN_POLICY_SHA256:
        raise ForwardExecutionError("EXECUTION_POLICY_SHA256_MISMATCH")
    try:
        value = strict_json_loads(raw.decode("ascii"), "forward execution policy")
    except (UnicodeError, CanonicalEvidenceError) as exc:
        raise ForwardExecutionError("EXECUTION_POLICY_JSON_INVALID") from exc
    validate_policy(value)
    if raw != (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii"):
        raise ForwardExecutionError("EXECUTION_POLICY_NONCANONICAL")
    if (construction.FROZEN_POLICY_SHA256 != CONSTRUCTION_POLICY_SHA256
            or selection.FROZEN_POLICY_SHA256 != SELECTION_POLICY_SHA256):
        raise ForwardExecutionError("EXECUTION_PARENT_IDENTITY_CHANGED")
    try:
        parent = selection.load_policy()
    except selection.ForwardStockSelectionPolicyError as exc:
        raise ForwardExecutionError("EXECUTION_PARENT_AUTHENTICATION_FAILED") from exc
    if (parent["parent_construction_policy_sha256"] != CONSTRUCTION_POLICY_SHA256
            or parent["capabilities"] != _FALSE_CAPABILITIES
            or parent["decision_ready"] is not False
            or parent["stock_selection_executable"] is not False):
        raise ForwardExecutionError("EXECUTION_PARENT_AUTHORITY_CHANGED")
    return _freeze(value)


@dataclass(frozen=True, slots=True)
class ArmExecutionBinding:
    candidate_id: str
    common_input_sha256: str
    execution_policy_sha256: str
    matched_configuration_sha256: str


@dataclass(frozen=True, slots=True)
class MatchedExecutionDiagnostic:
    schema: str
    decision_session: str
    common_input_sha256: str
    execution_policy_sha256: str
    stock_selection_policy_sha256: str
    construction_policy_sha256: str
    arm_configuration_sha256: str
    matched_configuration_sha256: str
    decision_cutoff_utc: str
    planned_execution_session: str
    planned_execution_time_utc: str
    reference_price_session: str
    reference_price_source_time_utc: str
    reference_price_sha256: str
    arms: tuple[ArmExecutionBinding, ArmExecutionBinding, ArmExecutionBinding]
    refusal_codes: tuple[str, ...]
    decision_ready: bool = False
    order_or_outcome_access: bool = False


def _calendar(session):
    try:
        date = parse_session_date(session, "decision_session")
        week_start = date - timedelta(days=date.weekday())
        sessions = trading_sessions(week_start, date)
        if not sessions or date != sessions[-1]:
            raise ForwardExecutionError("DECISION_NOT_NYSE_SESSION")
        if date != sessions[0]:
            raise ForwardExecutionError("DECISION_NOT_FIRST_WEEKLY_NYSE_SESSION")
        prior = trading_sessions(date - timedelta(days=31), date - timedelta(days=1))
        if not prior:
            raise ForwardExecutionError("PRIOR_NYSE_PRICE_SESSION_UNAVAILABLE")
        prior_session = prior[-1].isoformat()
        cutoff = datetime.combine(date, time(9, 20), NEW_YORK).astimezone(timezone.utc)
        execution_start = session_open_instant(session) + timedelta(minutes=1)
        return cutoff.isoformat(), execution_start.isoformat(), prior_session, session_close_instant(prior_session).isoformat()
    except ExchangeCalendarError as exc:
        raise ForwardExecutionError("DECISION_CALENDAR_INVALID") from exc


def _configuration(payload, pin):
    if type(pin) is not str:
        raise ForwardExecutionError("ARM_CONFIGURATION_SHA256_INVALID")
    try:
        require_sha256(pin, "arm configuration SHA-256")
    except CanonicalEvidenceError as exc:
        raise ForwardExecutionError("ARM_CONFIGURATION_SHA256_INVALID") from exc
    if type(payload) is not bytes or not 0 < len(payload) <= 32_768:
        raise ForwardExecutionError("ARM_CONFIGURATION_BYTES_INVALID")
    if hashlib.sha256(payload).hexdigest() != pin:
        raise ForwardExecutionError("ARM_CONFIGURATION_SHA256_MISMATCH")
    try:
        return require_canonical_json_bytes(payload, "arm configuration")
    except CanonicalEvidenceError as exc:
        raise ForwardExecutionError("ARM_CONFIGURATION_NONCANONICAL_OR_INVALID") from exc


def build_matched_execution_diagnostic(
    *, predecision_inputs, arm_configuration_bytes, arm_configuration_sha256,
):
    """Recompute common inputs from source bytes and refuse any arm/clock drift."""
    load_policy()
    if type(predecision_inputs) is not dict:
        raise ForwardExecutionError("PREDECISION_INPUT_KWARGS_INVALID")
    # All values below are exact immutable bytes/str. Retain this source
    # snapshot so caller mutation during upstream recomputation cannot rebind
    # the validated price bytes or pin in the final matched digest.
    predecision_inputs = predecision_inputs.copy()
    if set(predecision_inputs) != _INPUT_KEYS:
        raise ForwardExecutionError("PREDECISION_INPUT_KWARGS_INVALID")
    if any(type(value) is not (bytes if key.endswith("_bytes") else str)
           for key, value in predecision_inputs.items()):
        raise ForwardExecutionError("PREDECISION_INPUT_TYPES_INVALID")
    session = predecision_inputs["decision_session"]
    cutoff, start, prior_session, prior_close = _calendar(session)
    try:
        common = predecision.build_predecision_diagnostic(**predecision_inputs)
    except (predecision.ForwardPredecisionError, construction.ForwardConstructionPolicyError) as exc:
        raise ForwardExecutionError("PREDECISION_SOURCE_REFUSED: " + str(exc)) from exc
    # The upstream diagnostic has authenticated these bytes, their pin and
    # shape. Their timestamp remains a claim; matching it to a true prior
    # close does not establish RAW normalization or independent price origin.
    prices = strict_json_loads(predecision_inputs["reference_price_bytes"].decode("ascii"), "reference prices")
    price_time = datetime.fromisoformat(prices["source_time_utc"]).astimezone(timezone.utc)
    if price_time.isoformat() != prior_close:
        raise ForwardExecutionError("REFERENCE_PRICE_NOT_IMMEDIATE_PRIOR_NYSE_CLOSE")
    supplied = _configuration(arm_configuration_bytes, arm_configuration_sha256)
    expected = {
        "schema": CONFIGURATION_SCHEMA,
        "arms": [{
            "candidate_id": candidate_id,
            "decision_session": session,
            "common_input_sha256": common.common_input_sha256,
            "execution_policy_sha256": FROZEN_POLICY_SHA256,
            "decision_cutoff_utc": cutoff,
            "planned_execution_session": session,
            "planned_execution_time_utc": start,
            "starting_cash_usd": "1000000",
            "initial_positions": [],
        } for candidate_id in CANDIDATE_IDS],
    }
    if not _exact(supplied, expected):
        raise ForwardExecutionError("MATCHED_ARM_CONFIGURATION_CHANGED")
    body = {
        "schema": SCHEMA,
        "execution_policy_sha256": FROZEN_POLICY_SHA256,
        "stock_selection_policy_sha256": SELECTION_POLICY_SHA256,
        "construction_policy_sha256": CONSTRUCTION_POLICY_SHA256,
        "common_input_sha256": common.common_input_sha256,
        "decision_session": session,
        "decision_cutoff_utc": cutoff,
        "planned_execution_session": session,
        "planned_execution_time_utc": start,
        "reference_price_session": prior_session,
        "reference_price_source_time_utc": prior_close,
        "reference_price_sha256": predecision_inputs["reference_price_sha256"],
        "arm_configuration_sha256": arm_configuration_sha256,
        "candidate_ids": list(CANDIDATE_IDS),
    }
    matched = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return MatchedExecutionDiagnostic(
        **{key: value for key, value in body.items() if key != "candidate_ids"},
        matched_configuration_sha256=matched,
        arms=tuple(ArmExecutionBinding(candidate, common.common_input_sha256, FROZEN_POLICY_SHA256, matched)
                   for candidate in CANDIDATE_IDS),
        refusal_codes=common.refusal_codes + _ADDITIONAL_REFUSALS,
    )


__all__ = [
    "ArmExecutionBinding", "CANDIDATE_IDS", "CONFIGURATION_SCHEMA",
    "CONSTRUCTION_POLICY_SHA256", "FROZEN_POLICY_SHA256", "ForwardExecutionError",
    "MatchedExecutionDiagnostic", "POLICY_PATH", "SCHEMA", "SELECTION_POLICY_SHA256",
    "build_matched_execution_diagnostic", "load_policy", "validate_policy",
]
