"""
Return attribution: time-weighted (the asset) vs money-weighted (you).

Motivating case (user question, 2026-07-29): buy 2 @ 100, buy 2 @ 90, price
recovers to 95. Dollar P&L is $0, which tax_lots reports correctly -- but the
ASSET fell 5% and you came out flat because you added money at the low. These
tests pin that 5-point timing contribution, and the failure modes that make
hand-rolled return math wrong: counting a deposit as a gain, and inventing an
IRR where none exists.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from assistant.performance import (
    Distribution,
    MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION,
    Observation,
    PerformanceError,
    _decimal_accumulate,
    _decimal_sum,
    money_weighted_return,
    position_performance,
    time_weighted_return,
)
from assistant.tax_lots import Fill

D1 = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)
D2 = D1 + timedelta(days=1)
D3 = D1 + timedelta(days=2)


# --------------------------------------------------------------------------
# the motivating case
# --------------------------------------------------------------------------

def test_the_dip_buy_case_separates_asset_return_from_your_return():
    result = position_performance(
        [Fill("AAPL", "buy", 2, 100.0, D1, fill_id="a"),
         Fill("AAPL", "buy", 2, 90.0, D2, fill_id="b")],
        [(D1, 100.0), (D2, 90.0), (D3, 95.0)],
    )
    # The asset fell 5%: 0.90 * 1.0555... = 0.95
    assert result["asset_return"]["total_return_pct"] == pytest.approx(-5.0, abs=1e-6)
    # You put in 380 and hold 380: flat.
    assert result["your_return"]["simple_return_pct"] == pytest.approx(0.0, abs=1e-6)
    assert result["your_return"]["total_invested"] == 380.0
    assert result["your_return"]["total_returned"] == 380.0
    # The whole point.
    assert result["timing_contribution_pct"] == pytest.approx(5.0, abs=1e-6)
    assert "timing helped by 5.00" in result["interpretation"]
    assert "not evidence of skill" in result["interpretation"]


def test_the_dip_buy_sub_periods_are_the_two_price_moves():
    result = position_performance(
        [Fill("AAPL", "buy", 2, 100.0, D1), Fill("AAPL", "buy", 2, 90.0, D2)],
        [(D1, 100.0), (D2, 90.0), (D3, 95.0)],
    )
    subs = result["asset_return"]["sub_period_returns_pct"]
    assert subs[0] == pytest.approx(-10.0, abs=1e-6)
    assert subs[1] == pytest.approx(5.5556, abs=1e-3)


def test_a_single_lump_sum_purchase_has_no_timing_contribution():
    """With one purchase there is no timing decision, so both measures agree."""
    result = position_performance(
        [Fill("AAPL", "buy", 4, 100.0, D1)],
        [(D1, 100.0), (D2, 90.0), (D3, 95.0)],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(-5.0, abs=1e-6)
    assert result["your_return"]["simple_return_pct"] == pytest.approx(-5.0, abs=1e-6)
    assert result["timing_contribution_pct"] == pytest.approx(0.0, abs=1e-6)
    assert "no measurable difference" in result["interpretation"]


def test_cash_distribution_is_included_in_asset_and_investor_total_return():
    result = position_performance(
        [Fill("KO", "buy", 2, 100.0, D1)],
        [(D1, 100.0), (D2, 100.0), (D3, 100.0)],
        distributions=[
            Distribution(
                "KO",
                ex_at=D2,
                paid_at=D3,
                amount_per_share=5.0,
                cash_amount=10.0,
                tax_classification="qualified",
            )
        ],
    )

    assert result["asset_return"]["total_return_pct"] == pytest.approx(
        5.0, abs=1e-6
    )
    assert result["your_return"]["simple_return_pct"] == pytest.approx(
        5.0, abs=1e-6
    )
    assert result["distributions"]["gross_cash"] == 10.0
    assert result["distributions"]["cash_by_tax_classification"] == {
        "qualified": 10.0
    }


def test_adjusted_price_series_does_not_double_count_distribution():
    result = position_performance(
        [Fill("KO", "buy", 1, 100.0, D1)],
        [(D1, 100.0), (D3, 105.0)],
        distributions=[
            Distribution("KO", ex_at=D2, amount_per_share=5.0)
        ],
        prices_include_distributions=True,
    )

    assert result["asset_return"]["total_return_pct"] == pytest.approx(
        5.0, abs=1e-6
    )
    assert (
        result["asset_return"]["method"]
        == "time_weighted_adjusted_price_total_return"
    )


def test_buying_high_before_a_decline_hurts_and_is_reported_as_such():
    """The mirror image -- the module must not only ever produce flattering
    numbers. Timing HURTS when money goes in ABOVE the path and the price then
    falls: 80 -> 100 (buy more) -> 90.

    Asset: 1.25 * 0.90 = +12.5%. Yours: 360 in, 4 * 90 = 360 out, so 0%.
    Timing = -12.5 points.
    """
    result = position_performance(
        [Fill("AAPL", "buy", 2, 80.0, D1), Fill("AAPL", "buy", 2, 100.0, D2)],
        [(D1, 80.0), (D2, 100.0), (D3, 90.0)],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(12.5, abs=1e-6)
    assert result["your_return"]["simple_return_pct"] == pytest.approx(0.0, abs=1e-6)
    assert result["timing_contribution_pct"] == pytest.approx(-12.5, abs=1e-6)
    assert "timing hurt by 12.50" in result["interpretation"]


def test_money_weighting_is_not_replaced_by_simple_cash_on_cash_return():
    """Cash-on-cash ROI ignores when each dollar was exposed. MWR does not.

    Here simple ROI is -15.79%, but the second contribution participates in a
    sharp one-day loss. The period-equivalent IRR is -20.33%, which is the
    like-for-like figure that must be compared with the asset's -20% TWR.
    """
    result = position_performance(
        [Fill("AAPL", "buy", 2, 100.0, D1), Fill("AAPL", "buy", 2, 90.0, D2)],
        [(D1, 100.0), (D2, 90.0), (D3, 80.0)],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(-20.0, abs=1e-6)
    assert result["your_return"]["simple_return_pct"] == pytest.approx(-15.7895, abs=1e-3)
    assert result["your_return"]["period_return_pct"] == pytest.approx(-20.3315, abs=1e-3)
    assert result["timing_contribution_pct"] == pytest.approx(-0.3315, abs=1e-3)
    assert "timing hurt" in result["interpretation"]


def test_averaging_down_before_a_recovery_beats_the_asset():
    result = position_performance(
        [Fill("KO", "buy", 1, 100.0, D1), Fill("KO", "buy", 9, 50.0, D2)],
        [(D1, 100.0), (D2, 50.0), (D3, 60.0)],
    )
    # Asset: 100 -> 50 -> 60 is a big loss; your average cost is 55.
    assert result["asset_return"]["total_return_pct"] == pytest.approx(-40.0, abs=1e-6)
    assert result["your_return"]["simple_return_pct"] > 0, "10 shares at avg 55, now 60"
    assert result["timing_contribution_pct"] > 40


# --------------------------------------------------------------------------
# TWR: a deposit is not a gain
# --------------------------------------------------------------------------

def test_a_deposit_is_never_counted_as_a_gain():
    """The classic error. Value goes 100 -> 200 purely because 100 was added;
    the true return is 0%."""
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(D2, 100.0, 100.0),
        Observation(D3, 200.0),
    ])
    assert result["total_return_pct"] == pytest.approx(0.0, abs=1e-9)


def test_a_withdrawal_is_never_counted_as_a_loss():
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(D2, 100.0, -50.0),
        Observation(D3, 50.0),
    ])
    assert result["total_return_pct"] == pytest.approx(0.0, abs=1e-9)


def test_returns_chain_multiplicatively_not_additively():
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(D2, 150.0),   # +50%
        Observation(D3, 75.0),    # -50%
    ])
    # 1.5 * 0.5 = 0.75 -> -25%, not 0%.
    assert result["total_return_pct"] == pytest.approx(-25.0, abs=1e-9)


def test_a_sub_period_starting_from_zero_is_skipped_and_reported():
    """Fully closing then re-opening a position would otherwise be an infinite
    return. Skipping silently would overstate the chain, so it is counted."""
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(D2, 120.0, -120.0),   # closed out entirely
        Observation(D3, 0.0, 100.0),      # re-opened
        Observation(D3 + timedelta(days=1), 110.0),
    ])
    assert result["sub_periods_skipped_zero_value"] == 1
    assert result["total_return_pct"] == pytest.approx(32.0, abs=1e-6)  # 1.2 * 1.1


def test_time_weighted_return_needs_two_observations():
    with pytest.raises(PerformanceError, match="at least two observations"):
        time_weighted_return([Observation(D1, 100.0)])


def test_all_zero_start_values_is_an_error_not_a_zero_return():
    with pytest.raises(PerformanceError, match="no measurable sub-period"):
        time_weighted_return([Observation(D1, 0.0), Observation(D2, 0.0)])


# --------------------------------------------------------------------------
# MWR / IRR
# --------------------------------------------------------------------------

def test_a_doubling_over_one_year_is_about_100_percent_annualized():
    flows = [(D1, -1000.0), (D1 + timedelta(days=365), 2000.0)]
    result = money_weighted_return(flows)
    assert result["irr_annualized_pct"] == pytest.approx(100.0, abs=0.5)
    assert result["simple_return_pct"] == pytest.approx(100.0, abs=1e-9)
    assert result["annualized_is_meaningful"] is True


def test_the_dip_buy_irr_is_zero_because_in_equals_out():
    flows = [(D1, -200.0), (D2, -180.0), (D3, 380.0)]
    result = money_weighted_return(flows)
    assert result["irr_annualized_pct"] == pytest.approx(0.0, abs=1e-3)
    assert result["simple_return_pct"] == pytest.approx(0.0, abs=1e-9)


def test_no_irr_exists_when_every_flow_points_the_same_way():
    """Only purchases, nothing sold and no terminal value: an IRR genuinely does
    not exist. It must report None, not a plausible fabrication."""
    result = money_weighted_return([(D1, -100.0), (D2, -100.0)])
    assert result["irr_annualized_pct"] is None
    assert "only one sign" in result["note"]
    assert result["total_invested"] == 200.0
    assert result["total_returned"] == 0.0


def test_short_window_irr_is_not_limited_to_one_thousand_percent():
    """Ten percent in two days annualizes far above the former fixed bracket."""
    result = money_weighted_return([(D1, -100.0), (D3, 110.0)])
    assert result["irr_annualized_pct"] > 1_000.0
    assert result["period_return_pct"] == pytest.approx(10.0, abs=1e-6)
    assert "note" not in result


def test_finite_period_return_survives_annualized_numeric_overflow():
    result = money_weighted_return([(D1, -100.0), (D2, 1_000.0)])
    assert result["period_return_pct"] == pytest.approx(900.0, abs=1e-6)
    assert result["irr_annualized_pct"] is None
    assert "annualized IRR exceeds" in result["note"]


def test_same_timestamp_balanced_flows_do_not_fabricate_an_irr():
    result = money_weighted_return([(D1, -100.0), (D1, 100.0)])
    assert result["irr_annualized_pct"] is None
    assert result["period_return_pct"] is None
    assert result["total_invested"] == 100.0
    assert result["total_returned"] == 100.0
    assert "positive amount of time" in result["note"]


def test_multiple_possible_irrs_fail_closed():
    """This annual series has roots near 10% and 20%; selecting one is arbitrary."""
    result = money_weighted_return([
        (D1, -100.0),
        (D1 + timedelta(days=365), 230.0),
        (D1 + timedelta(days=730), -132.0),
    ])
    assert result["irr_annualized_pct"] is None
    assert result["period_return_pct"] is None
    assert "non-unique" in result["note"]


def test_timing_uses_period_equivalent_mwr_not_simple_roi():
    """Both simple ROI and TWR are 21%, but the cash arrived after a flat year.

    The standard MWR therefore differs: 13.41% annualized, or 28.60% over the
    complete two-year comparison horizon.
    """
    result = position_performance(
        [
            Fill("AAPL", "buy", 1, 100.0, D1),
            Fill("AAPL", "buy", 1, 100.0, D1 + timedelta(days=365)),
        ],
        [
            (D1, 100.0),
            (D1 + timedelta(days=365), 100.0),
            (D1 + timedelta(days=730), 121.0),
        ],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(21.0, abs=1e-6)
    assert result["your_return"]["simple_return_pct"] == pytest.approx(21.0, abs=1e-6)
    assert result["your_return"]["irr_annualized_pct"] == pytest.approx(13.4111, abs=1e-3)
    assert result["your_return"]["period_return_pct"] == pytest.approx(28.5987, abs=1e-3)
    assert result["timing_contribution_pct"] == pytest.approx(7.5987, abs=1e-3)


def test_dividend_paid_after_terminal_valuation_is_not_a_future_cash_flow():
    final_at = D1 + timedelta(days=30)
    result = position_performance(
        [Fill("AAPL", "buy", 1, 100.0, D1)],
        [(D1, 100.0), (final_at, 99.0)],
        distributions=[
            Distribution(
                "AAPL",
                D1 + timedelta(days=15),
                2.0,
                paid_at=D1 + timedelta(days=45),
            )
        ],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(1.0)
    assert result["distributions"]["gross_cash"] == 0.0
    assert result["distributions"]["pending_cash_after_valuation"] == 2.0


def test_money_weighted_return_needs_two_flows():
    with pytest.raises(PerformanceError, match="at least two cash flows"):
        money_weighted_return([(D1, -100.0)])


def test_a_total_loss_reports_no_annualized_rate_rather_than_nonsense():
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(D1 + timedelta(days=200), 0.0),
    ])
    assert result["total_return_pct"] == pytest.approx(-100.0, abs=1e-9)
    assert result["annualized_return_pct"] is None


# --------------------------------------------------------------------------
# annualization honesty
# --------------------------------------------------------------------------

def test_a_two_day_window_flags_its_annualized_figure_as_meaningless():
    result = position_performance(
        [Fill("AAPL", "buy", 2, 100.0, D1), Fill("AAPL", "buy", 2, 90.0, D2)],
        [(D1, 100.0), (D2, 90.0), (D3, 95.0)],
    )
    assert result["asset_return"]["period_days"] == pytest.approx(2.0, abs=1e-6)
    assert result["asset_return"]["annualized_is_meaningful"] is False


def test_a_long_window_flags_its_annualized_figure_as_meaningful():
    long_end = D1 + timedelta(days=MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION + 10)
    result = time_weighted_return([
        Observation(D1, 0.0, 100.0),
        Observation(long_end, 110.0),
    ])
    assert result["annualized_is_meaningful"] is True
    assert result["annualized_return_pct"] > 10.0  # compounded past the period figure


# --------------------------------------------------------------------------
# corrupt input fails closed (this project's recurring bug class)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_value_is_refused(bad):
    with pytest.raises(PerformanceError, match="finite"):
        Observation(D1, bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_flow_is_refused(bad):
    with pytest.raises(PerformanceError, match="finite"):
        Observation(D1, 100.0, bad)


def test_a_negative_value_is_refused():
    with pytest.raises(PerformanceError, match="cannot be negative"):
        Observation(D1, -1.0)


def test_a_flow_cannot_make_the_observed_value_negative():
    with pytest.raises(PerformanceError, match="value_after_flow cannot be negative"):
        Observation(D1, 100.0, -101.0)


def test_a_boolean_value_is_refused():
    with pytest.raises(PerformanceError, match="must be a number"):
        Observation(D1, True)


def test_a_naive_timestamp_is_refused():
    with pytest.raises(PerformanceError, match="timezone-aware"):
        Observation(datetime(2026, 7, 20, 14, 30), 100.0)


def test_a_non_finite_cash_flow_is_refused():
    with pytest.raises(PerformanceError, match="finite"):
        money_weighted_return([(D1, -100.0), (D2, float("nan"))])


def test_a_non_positive_price_is_refused():
    with pytest.raises(PerformanceError, match="positive and finite"):
        position_performance([Fill("AAPL", "buy", 1, 100.0, D1)], [(D1, 100.0), (D2, 0.0)])


def test_mixing_tickers_in_one_position_is_refused():
    with pytest.raises(PerformanceError, match="per-ticker"):
        position_performance(
            [Fill("AAPL", "buy", 1, 100.0, D1), Fill("MSFT", "buy", 1, 300.0, D2)],
            [(D1, 100.0), (D2, 90.0)],
        )


def test_position_performance_needs_fills_and_prices():
    with pytest.raises(PerformanceError, match="at least one fill"):
        position_performance([], [(D1, 100.0), (D2, 90.0)])
    with pytest.raises(PerformanceError, match="at least two price points"):
        position_performance([Fill("AAPL", "buy", 1, 100.0, D1)], [(D1, 100.0)])


# --------------------------------------------------------------------------
# selling out
# --------------------------------------------------------------------------

def test_a_fully_closed_position_uses_realized_proceeds_only():
    result = position_performance(
        [Fill("AAPL", "buy", 2, 100.0, D1), Fill("AAPL", "sell", 2, 110.0, D2)],
        [(D1, 100.0), (D2, 110.0)],
    )
    assert result["shares_open"] == 0
    assert result["your_return"]["total_invested"] == 200.0
    assert result["your_return"]["total_returned"] == 220.0
    assert result["your_return"]["simple_return_pct"] == pytest.approx(10.0, abs=1e-9)


def test_asset_benchmark_includes_the_interval_while_position_is_closed():
    """Selling before a decline and re-entering afterward must not be reversed.

    The asset goes 100 -> 110 -> 90 -> 99, a continuous -1% return. The
    investor's alternating cash-flow signs make IRR potentially non-unique, so
    timing fails closed rather than claiming the skipped decline hurt.
    """
    result = position_performance(
        [
            Fill("AAPL", "buy", 1, 100.0, D1),
            Fill("AAPL", "sell", 1, 110.0, D2),
            Fill("AAPL", "buy", 1, 90.0, D3),
        ],
        [
            (D1, 100.0),
            (D2, 110.0),
            (D3, 90.0),
            (D3 + timedelta(days=1), 99.0),
        ],
    )
    assert result["asset_return"]["total_return_pct"] == pytest.approx(-1.0, abs=1e-6)
    assert result["asset_return"]["sub_period_returns_pct"] == pytest.approx(
        [10.0, -18.1818, 10.0], abs=1e-3
    )
    assert result["asset_return"]["sub_periods_skipped_zero_value"] == 0
    assert result["your_return"]["irr_annualized_pct"] is None
    assert result["timing_contribution_pct"] is None
    assert "non-unique" in result["your_return"]["note"]


def test_terminal_valuation_cannot_precede_the_latest_fill():
    with pytest.raises(PerformanceError, match="terminal valuation precedes"):
        position_performance(
            [
                Fill("AAPL", "buy", 1, 100.0, D1),
                Fill("AAPL", "buy", 1, 100.0, D3),
            ],
            [(D1, 100.0), (D2, 110.0)],
        )


def test_selling_more_than_the_position_owns_is_refused():
    with pytest.raises(PerformanceError, match="exceeds available shares"):
        position_performance(
            [
                Fill("AAPL", "buy", 1, 100.0, D1),
                Fill("AAPL", "sell", 2, 110.0, D2),
            ],
            [(D1, 100.0), (D2, 110.0)],
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_decimal_helpers_avoid_binary_float_accumulation_error():
    # Independent review, 2026-07-31 (P2 #4): money_weighted_return()'s
    # invested/returned sums and position_performance()'s cash_by_time
    # accumulation used to be plain binary float addition, which can drift
    # from the exact decimal total -- the textbook case:
    # 0.1 + 0.1 + 0.1 != 0.3 in raw binary float.
    assert 0.1 + 0.1 + 0.1 != 0.3  # the drift these helpers avoid
    assert _decimal_sum([0.1, 0.1, 0.1]) == 0.3
    running = 0.0
    for amount in (0.1, 0.1, 0.1):
        running = _decimal_accumulate(running, amount)
    assert running == 0.3
