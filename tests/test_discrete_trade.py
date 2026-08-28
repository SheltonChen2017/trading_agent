"""Dollar<->share sizing for the discrete trading tabs.

A dollar amount is a BUDGET floored to whole shares (owner decision
2026-08-14), so the dangerous directions are:

* rounding UP, which spends unbudgeted money on a buy and proposes a short
  on a sell;
* losing the unspent remainder, which makes a $500 order that bought $301.51
  look like it used the whole budget; and
* float arithmetic, which on 2026-08-13 (SELREV-002) refused a valid 3-share
  order at $0.10 against a $0.30 cap because 3 * 0.10 is 0.30000000000000004.
"""
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.discrete_trade import (
    notional_for_shares,
    size_by_dollar_amount,
)


def test_a_budget_floors_to_whole_shares_and_reports_the_remainder():
    result = size_by_dollar_amount("500", "301.51")
    assert result["ok"] is True
    sizing = result["sizing"]
    assert sizing.shares == 1
    assert sizing.notional_text == "301.51"
    assert sizing.unallocated_text == "198.49"
    assert sizing.affordable is True


def test_an_exact_multiple_leaves_nothing_unallocated():
    sizing = size_by_dollar_amount("300", "100")["sizing"]
    assert sizing.shares == 3
    assert sizing.notional_text == "300"
    assert sizing.unallocated_text == "0"


def test_the_float_boundary_that_broke_the_max_order_value_check():
    """SELREV-002's exact shape: 3 * 0.10 is 0.30000000000000004 in binary
    float, so a float implementation buys 2 shares here instead of 3."""
    sizing = size_by_dollar_amount("0.30", "0.10")["sizing"]
    assert sizing.shares == 3
    # Compare VALUES, not spellings: decimal_text is canonical, so exactly
    # thirty cents is written "0.3". The UI formats money for display; this
    # module's job is to be exact, and the float version got 2 shares here.
    assert Decimal(sizing.notional_text) == Decimal("0.30")
    assert Decimal(sizing.unallocated_text) == 0


@pytest.mark.parametrize("whole_shares_only", [True, False])
def test_dollar_sizing_never_rounds_over_budget_under_low_ambient_precision(
    whole_shares_only,
):
    amount = "9.999" if whole_shares_only else "0.9999999999"
    price = "1" if whole_shares_only else "0.1"

    with localcontext() as context:
        context.prec = 2
        result = size_by_dollar_amount(
            amount,
            price,
            whole_shares_only=whole_shares_only,
        )

    assert result["ok"] is True
    sizing = result["sizing"]
    assert Decimal(sizing.notional_text) <= Decimal(amount)
    assert Decimal(sizing.notional_text) + Decimal(
        sizing.unallocated_text
    ) == Decimal(amount)
    assert sizing.shares == (9 if whole_shares_only else "9.999999999")


def test_a_budget_below_one_share_is_refused_not_rounded_up():
    result = size_by_dollar_amount("50", "301.51")
    assert result["ok"] is False
    assert "does not cover one share" in result["reason"]
    assert "sizing" not in result


@pytest.mark.parametrize("amount", ["0", "-5", "nan", "inf", "abc", None])
def test_unusable_budgets_are_refused(amount):
    assert size_by_dollar_amount(amount, "100")["ok"] is False


@pytest.mark.parametrize("price", ["0", "-1", "nan", "inf", None])
def test_unusable_prices_are_refused(price):
    result = size_by_dollar_amount("500", price)
    assert result["ok"] is False
    assert "reference price" in result["reason"]


def test_a_fractional_result_is_never_returned():
    """Whole-share only, enforced here as well as at the gate and broker."""
    sizing = size_by_dollar_amount("1000", "301.51")["sizing"]
    assert isinstance(sizing.shares, int)
    assert sizing.shares == 3  # 3.31... floored
    assert sizing.notional_text == "904.53"


def test_extreme_finite_inputs_refuse_instead_of_crashing():
    """Decimal accepts exponent values much larger than its arithmetic
    context. They are finite inputs, but converting their ratio to shares can
    overflow and must remain a user-facing refusal."""
    result = size_by_dollar_amount("1e999999999", "1e-999999999")
    assert result["ok"] is False
    assert "too large" in result["reason"]


# --- share mode ------------------------------------------------------------


def test_notional_for_shares_is_exact():
    result = notional_for_shares(3, "0.10")
    assert result["ok"] is True
    assert Decimal(result["notional_text"]) == Decimal("0.30"), (
        "float would give 0.30000000000000004"
    )


def test_share_mode_notional_is_exact_under_low_ambient_precision():
    with localcontext() as context:
        context.prec = 2
        result = notional_for_shares(999, "123.45")

    assert result["ok"] is True
    assert result["notional_text"] == "123326.55"


@pytest.mark.parametrize("shares", [0, -1, 2.0, True, "3", None])
def test_share_mode_rejects_anything_but_a_positive_int(shares):
    result = notional_for_shares(shares, "100")
    assert result["ok"] is False
    assert "whole number greater than zero" in result["reason"]


@pytest.mark.parametrize("price", ["0", "-1", "nan", None])
def test_share_mode_refuses_an_unusable_price(price):
    assert notional_for_shares(3, price)["ok"] is False


def test_the_two_modes_agree_at_the_same_quantity():
    """Sizing $904.53 at $301.51 and asking for 3 shares must cost the same."""
    from_dollars = size_by_dollar_amount("904.53", "301.51")["sizing"]
    from_shares = notional_for_shares(from_dollars.shares, "301.51")
    assert from_dollars.notional_text == from_shares["notional_text"]


def test_fractional_dollar_sizing_uses_nine_decimal_places_and_never_overspends():
    result = size_by_dollar_amount(
        "10", "3", whole_shares_only=False
    )
    assert result["ok"] is True
    sizing = result["sizing"]
    assert sizing.shares == "3.333333333"
    assert sizing.notional_text == "9.999999999"
    assert sizing.unallocated_text == "0.000000001"


def test_fractional_share_mode_accepts_exact_text_but_rejects_binary_float():
    exact = notional_for_shares(
        "0.125", "80", whole_shares_only=False
    )
    assert exact == {
        "ok": True,
        "notional_text": "10",
        "reference_price_text": "80",
    }
    assert not notional_for_shares(
        0.125, "80", whole_shares_only=False
    )["ok"]
