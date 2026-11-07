"""Pinned demonstration policy; not an admitted empirical cashflow protocol."""
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    require_si5_offline_protocol,
)

SI5_SYNTHETIC_POLICY_SHA256 = "ab4a0e5c080324100143417469d845144c3417273e95bf5abf410db3c51e07eb"


def _policy_payload() -> dict[str, Any]:
    return {
        "schema": "si5-fixed-fixture-demonstration-policy-v1",
        "owner_decision_source": {
            "path": "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md",
            "commit": "e19f0873ea13c01cb24469a23053abc8125d2b9e",
            "sha256": "820bab37ce299e74351e2fba47b4d65c81fc2589b0384c975ed4b1ee9b8a8e35",
            "section": 92,
            "authorization_ids": ["SI-AUTH-20261006-03", "SI-AUTH-20261006-04"],
            "decision_ids": [f"SI-DEC-20261006-0{index}" for index in range(3, 7)],
        },
        "offline_protocol_sha256": require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL),
        "input_mode": "fixed_builtin_fixture_ids_only",
        "order_basis": "unlevered_long_avoidance_exact_fractional_shares",
        "entry_cash": "reserve_full_fill_and_fee_before_allocation",
        "corporate_actions": "split_quantity_pre_ex_open_entitlement_later_payment",
        "terminal_basis": "explicit_fixture_cash_only_zero_allowed_no_assumed_payout",
        "missing_execution": "named_refusal_no_partial_fill_or_last_quote_fallback",
        "primary_order_cost_bps_per_side": 10,
        "sensitivity_cost_bps_per_side": [0, 5, 20],
        "diagnostic_basis": "gross_split_adjusted_dividend_excluded_R20",
        "diagnostic_cost_bps_per_side": 0,
        "candidate_lookbacks": [20, 60, 120, 252],
        "selected_lookback": None,
        "synthetic_only": True,
        "source_admitted": False,
        "real_backtesting_ready": False,
        "authorized_real_outcome_looks": 0,
        "consumed_real_outcome_looks": 0,
    }


def synthetic_policy_payload() -> dict[str, Any]:
    """Fresh canonical policy tied to the committed owner decisions."""
    payload = _policy_payload()
    if hash_payload(payload) != SI5_SYNTHETIC_POLICY_SHA256:
        raise ValueError("REFUSED: fixed synthetic demonstration policy changed")
    return payload
