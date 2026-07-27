"""Tests for assistant/policy.py's TradingPolicy.validate() -- GPT review
flagged that several fields (max_slippage_pct, max_spread_pct,
earnings_blackout_days, allowed_sides, allowed_order_types, boolean
fields) were accepted without any sanity checking, which could let a
hand-edited policy file silently misbehave rather than fail loudly at
load time.
"""
import dataclasses
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.policy import TradingPolicy


def _valid_policy(**overrides) -> TradingPolicy:
    base = TradingPolicy(version="test", name="test", execution_mode="paper")
    return dataclasses.replace(base, **overrides)


def test_default_policy_is_valid():
    _valid_policy().validate()  # must not raise


def test_negative_max_slippage_pct_rejected():
    try:
        _valid_policy(max_slippage_pct=-1.0).validate()
        assert False, "expected a negative max_slippage_pct to be rejected"
    except ValueError as exc:
        assert "max_slippage_pct" in str(exc)


def test_negative_max_spread_pct_rejected():
    try:
        _valid_policy(max_spread_pct=-0.1).validate()
        assert False, "expected a negative max_spread_pct to be rejected"
    except ValueError as exc:
        assert "max_spread_pct" in str(exc)


def test_negative_earnings_blackout_days_rejected():
    try:
        _valid_policy(earnings_blackout_days=-2).validate()
        assert False, "expected a negative earnings_blackout_days to be rejected"
    except ValueError as exc:
        assert "earnings_blackout_days" in str(exc)


def test_empty_allowed_sides_rejected():
    try:
        _valid_policy(allowed_sides=()).validate()
        assert False, "expected empty allowed_sides to be rejected"
    except ValueError as exc:
        assert "allowed_sides" in str(exc)


def test_unsupported_allowed_side_rejected():
    try:
        _valid_policy(allowed_sides=("buy", "short")).validate()
        assert False, "expected an unsupported side to be rejected"
    except ValueError as exc:
        assert "allowed_sides" in str(exc)


def test_empty_allowed_order_types_rejected():
    try:
        _valid_policy(allowed_order_types=()).validate()
        assert False, "expected empty allowed_order_types to be rejected"
    except ValueError as exc:
        assert "allowed_order_types" in str(exc)


def test_unsupported_allowed_order_type_rejected():
    try:
        _valid_policy(allowed_order_types=("market", "trailing_stop")).validate()
        assert False, "expected an unsupported/unimplemented order type to be rejected"
    except ValueError as exc:
        assert "allowed_order_types" in str(exc)


def test_non_finite_numeric_fields_rejected():
    # Regression test (Codex review, 2026-07-27): a naive `<= 0` / `< 0`
    # check silently PASSES a NaN (NaN <= 0 is False in Python), which
    # would then make every downstream `>`/`<` comparison in
    # risk/execution_gate.py evaluate False no matter what -- silently
    # disabling that cap instead of rejecting the policy. json.loads()
    # accepts a literal NaN/Infinity by default, so this is reachable from
    # a malformed policy file, not just a caller bug.
    numeric_fields = (
        "max_order_value",
        "max_stale_price_minutes",
        "max_slippage_pct",
        "max_spread_pct",
        "max_position_pct",
        "max_total_exposure_pct",
        "max_basket_pct",
        "max_leveraged_etf_pct",
        "min_cash_reserve_pct",
    )
    for field_name in numeric_fields:
        for bad_value in (float("nan"), float("inf")):
            try:
                _valid_policy(**{field_name: bad_value}).validate()
                assert False, f"expected {field_name}={bad_value} to be rejected"
            except ValueError as exc:
                assert field_name in str(exc), (field_name, bad_value, str(exc))


def test_non_boolean_flag_fields_rejected():
    for field_name in ("require_earnings_data", "allow_new_positions", "enable_strategy_proposals"):
        try:
            _valid_policy(**{field_name: "true"}).validate()
            assert False, f"expected a non-boolean {field_name} to be rejected"
        except ValueError as exc:
            assert field_name in str(exc)


if __name__ == "__main__":
    test_default_policy_is_valid()
    test_negative_max_slippage_pct_rejected()
    test_negative_max_spread_pct_rejected()
    test_negative_earnings_blackout_days_rejected()
    test_empty_allowed_sides_rejected()
    test_unsupported_allowed_side_rejected()
    test_empty_allowed_order_types_rejected()
    test_unsupported_allowed_order_type_rejected()
    test_non_finite_numeric_fields_rejected()
    test_non_boolean_flag_fields_rejected()
    print("All policy validation tests passed.")
