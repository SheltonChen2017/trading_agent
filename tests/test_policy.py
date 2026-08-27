"""Tests for assistant/policy.py's TradingPolicy.validate() -- GPT review
flagged that several fields (max_slippage_pct, max_spread_pct,
earnings_blackout_days, allowed_sides, allowed_order_types, boolean
fields) were accepted without any sanity checking, which could let a
hand-edited policy file silently misbehave rather than fail loudly at
load time.
"""
import dataclasses
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.policy import (
    TradingPolicy,
    compute_policy_fingerprint,
    load_policy,
    policy_with_updated_flags,
)
from assistant.temporal_integrity import MAX_ORDER_AGE_MINUTES


def _valid_policy(**overrides) -> TradingPolicy:
    base = TradingPolicy(version="test", name="test", execution_mode="paper")
    return dataclasses.replace(base, **overrides)


_REAL_POLICY_FIELDS = (
    "max_order_value",
    "max_daily_submitted_notional",
    "max_order_age_minutes",
    "max_stale_price_minutes",
    "max_slippage_pct",
    "max_spread_pct",
    "max_position_pct",
    "max_total_exposure_pct",
    "max_basket_pct",
    "max_leveraged_etf_pct",
    "min_cash_reserve_pct",
)


def test_default_policy_is_valid():
    _valid_policy().validate()  # must not raise


def test_order_age_policy_uses_the_reconciler_maximum():
    _valid_policy(max_order_age_minutes=MAX_ORDER_AGE_MINUTES).validate()
    with pytest.raises(ValueError, match="max_order_age_minutes"):
        _valid_policy(
            max_order_age_minutes=MAX_ORDER_AGE_MINUTES + 0.001
        ).validate()


def test_policy_fingerprint_same_content_same_fingerprint():
    a = _valid_policy()
    b = _valid_policy()
    assert compute_policy_fingerprint(a) == compute_policy_fingerprint(b)


def test_policy_fingerprint_changes_with_any_risk_limit():
    # Regression test (GPT review, 2026-07-28): approval previously only
    # compared `version` strings -- two policies with the SAME version
    # but different limits were interchangeable. The fingerprint must
    # change even though `version` doesn't.
    base = _valid_policy(version="1.0.0")
    edited = dataclasses.replace(base, max_position_pct=base.max_position_pct / 2)
    assert base.version == edited.version
    assert compute_policy_fingerprint(base) != compute_policy_fingerprint(edited)


def test_policy_fingerprint_changes_with_allow_new_positions():
    base = _valid_policy(version="1.0.0", allow_new_positions=False)
    edited = dataclasses.replace(base, allow_new_positions=True)
    assert base.version == edited.version
    assert compute_policy_fingerprint(base) != compute_policy_fingerprint(edited)


def test_policy_fingerprint_ignores_notes_only_changes():
    # `notes` is free-text/explanatory, not behavior-affecting -- changing
    # ONLY it should not invalidate an otherwise-identical policy.
    base = _valid_policy(notes="original notes")
    edited = dataclasses.replace(base, notes="completely different notes")
    assert compute_policy_fingerprint(base) == compute_policy_fingerprint(edited)


def test_default_and_personal_starter_policies_have_distinct_identity():
    # GPT review, 2026-07-28: give the personal starter policy an identity
    # distinct from the default so the two are never accidentally
    # interchangeable, even though they start with identical limits.
    from assistant.policy import DEFAULT_POLICY_PATH, load_policy

    default_policy = load_policy(DEFAULT_POLICY_PATH)
    personal_policy = load_policy(DEFAULT_POLICY_PATH.parent / "my_policy.example.json")
    assert default_policy.name != personal_policy.name
    assert default_policy.version != personal_policy.version
    assert compute_policy_fingerprint(default_policy) != compute_policy_fingerprint(personal_policy)


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


def test_non_integer_earnings_blackout_days_rejected():
    # Regression test (Codex review, 2026-07-27): `< 0` alone silently
    # passes NaN (NaN < 0 is False) and doesn't reject infinity or a
    # fractional value either -- all three should be rejected outright
    # since this field is meant to be a whole number of days.
    for bad_value in (float("nan"), float("inf"), 1.5):
        try:
            _valid_policy(earnings_blackout_days=bad_value).validate()
            assert False, f"expected earnings_blackout_days={bad_value} to be rejected"
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
    for field_name in _REAL_POLICY_FIELDS:
        for bad_value in (float("nan"), float("inf")):
            try:
                _valid_policy(**{field_name: bad_value}).validate()
                assert False, f"expected {field_name}={bad_value} to be rejected"
            except ValueError as exc:
                assert field_name in str(exc), (field_name, bad_value, str(exc))


@pytest.mark.parametrize(
    "field_name",
    _REAL_POLICY_FIELDS,
)
@pytest.mark.parametrize("bad_value", (False, True))
def test_boolean_numeric_policy_fields_are_rejected(field_name, bad_value):
    """JSON booleans must never become authoritative 0/1 policy values."""
    with pytest.raises(ValueError, match=field_name):
        _valid_policy(**{field_name: bad_value}).validate()


@pytest.mark.parametrize("bad_value", (False, True))
def test_boolean_cash_reserve_update_is_rejected_before_float_coercion(bad_value):
    with pytest.raises(ValueError, match="min_cash_reserve_pct"):
        policy_with_updated_flags(
            _valid_policy(min_cash_reserve_pct=0.10),
            min_cash_reserve_pct=bad_value,
        )


@pytest.mark.parametrize("field_name", _REAL_POLICY_FIELDS)
@pytest.mark.parametrize("bad_value", (False, True))
def test_boolean_numeric_value_loaded_from_json_is_rejected(
    tmp_path, field_name, bad_value
):
    raw = _valid_policy().to_dict()
    raw[field_name] = bad_value
    path = tmp_path / "boolean-policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=field_name):
        load_policy(path)


def test_cash_reserve_update_accepts_valid_zero():
    updated = policy_with_updated_flags(
        _valid_policy(min_cash_reserve_pct=0.10),
        min_cash_reserve_pct=0.0,
    )
    assert updated.min_cash_reserve_pct == 0.0
    updated.validate()


def test_nonstandard_json_nan_is_rejected_at_parse_boundary(tmp_path):
    path = tmp_path / "nan-policy.json"
    path.write_text(
        json.dumps(_valid_policy().to_dict()).replace(
            '"max_basket_pct": 0.4',
            '"max_basket_pct": NaN',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-finite JSON constant"):
        load_policy(path)


def test_daily_order_and_open_order_caps_require_positive_integers():
    for field_name in ("max_daily_order_count", "max_open_orders"):
        for bad_value in (0, -1, 1.5, True):
            try:
                _valid_policy(**{field_name: bad_value}).validate()
                assert False, f"expected {field_name}={bad_value!r} to be rejected"
            except ValueError as exc:
                assert field_name in str(exc)


def test_non_boolean_flag_fields_rejected():
    for field_name in (
        "require_earnings_data",
        "allow_new_positions",
        "enable_strategy_proposals",
        "whole_shares_only",
    ):
        try:
            _valid_policy(**{field_name: "true"}).validate()
            assert False, f"expected a non-boolean {field_name} to be rejected"
        except ValueError as exc:
            assert field_name in str(exc)


if __name__ == "__main__":
    test_default_policy_is_valid()
    test_policy_fingerprint_same_content_same_fingerprint()
    test_policy_fingerprint_changes_with_any_risk_limit()
    test_policy_fingerprint_changes_with_allow_new_positions()
    test_policy_fingerprint_ignores_notes_only_changes()
    test_default_and_personal_starter_policies_have_distinct_identity()
    test_negative_max_slippage_pct_rejected()
    test_negative_max_spread_pct_rejected()
    test_negative_earnings_blackout_days_rejected()
    test_non_integer_earnings_blackout_days_rejected()
    test_empty_allowed_sides_rejected()
    test_unsupported_allowed_side_rejected()
    test_empty_allowed_order_types_rejected()
    test_unsupported_allowed_order_type_rejected()
    test_non_finite_numeric_fields_rejected()
    test_non_boolean_flag_fields_rejected()
    print("All policy validation tests passed.")
