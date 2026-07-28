"""
Sanity tests for risk/execution_gate.py. Run with:
python tests/test_execution_gate.py
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from risk.execution_gate import (
    TradeIntent,
    authorize_overridden_trade_intent,
    authorize_trade_intent,
    validate_trade_intent,
)

_MARKET_HOURS_WEEKDAY = datetime(2026, 7, 27, 10, 0)  # a Monday, 10:00am


def _snapshot(positions=None, cash=10_000.0):
    return build_portfolio_snapshot(positions or [], cash=cash)


def test_clean_trade_is_approved():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=5)  # $300 = 3% of equity, under every default cap
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True
    assert result.violations == ()


def test_kill_switch_blocks_everything_else():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, kill_switch_active=True)
    assert result.approved is False
    assert result.violations == ("Kill switch is active — no trades are permitted.",)


def test_max_position_size_exceeded():
    snapshot = _snapshot(cash=10_000.0)  # total equity = 10,000
    # buying $6,000 of a single name on a 10,000 account with default 5% cap
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is False
    assert any("per-position limit" in v for v in result.violations)


def test_insufficient_cash_flagged():
    snapshot = _snapshot(cash=100.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # $600 trade, only $100 cash
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_position_pct=1.0)
    assert any("exceeds available cash" in v for v in result.violations)


def test_buying_power_constrains_cash_even_when_raw_cash_looks_sufficient():
    # Regression test (Codex review, 2026-07-27): portfolio.cash alone
    # ignores pending/open orders that the broker has already reserved
    # funds against -- portfolio.buying_power reflects that hold and must
    # be the binding constraint when it's tighter than raw cash.
    snapshot = build_portfolio_snapshot(
        [], cash=10_000.0, buying_power=1_000.0, source="alpaca", account_mode="paper",
    )
    intent = TradeIntent(ticker="KO", side="buy", shares=25)  # $1,500 > $1,000 buying power, < $10,000 cash
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_position_pct=1.0,
    )
    assert any("exceeds available cash" in v for v in result.violations)


def test_pending_buy_value_counts_toward_total_exposure():
    # Regression test (Codex review, 2026-07-27): a pending (not-yet-
    # filled) buy order doesn't show up in portfolio.positions, so the
    # total-exposure check was blind to it -- a $4,000 pending buy plus a
    # new $5,000 buy on a $10,000 account both "fit" under a 50% cap
    # (0% + 50% each), even though both fills together create 90%
    # exposure. Reproduced here and fixed via pending_buy_value_by_ticker.
    snapshot = _snapshot(cash=10_000.0)  # total equity = 10,000, no filled positions yet
    intent = TradeIntent(ticker="KO", side="buy", shares=83)  # ~$4,980 < $5,000 cap check on its own
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=0.50,
        pending_buy_value_by_ticker={"NVDA": 4_000.0},
    )
    assert any("total-exposure limit" in v for v in result.violations)


def test_pending_buy_value_on_the_same_ticker_counts_toward_position_limit():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # $600, well under 5% alone
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        pending_buy_value_by_ticker={"KO": 9_000.0},  # already 90% committed on KO via a pending order
    )
    assert any("per-position limit" in v for v in result.violations)


def test_non_finite_pending_buy_value_fails_closed_instead_of_disabling_checks():
    # Regression test (GPT review, 2026-07-27): a NaN pending value
    # propagates through every sum it touches, and `x > cap` for a NaN x
    # is always False in Python -- so a corrupted pending value used to
    # silently disable the total-exposure check entirely rather than
    # being rejected, the same failure mode already fixed elsewhere in
    # this module for reference_price/limit_price/bid/ask.
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    for bad_value in (float("nan"), float("inf"), -100.0):
        result = validate_trade_intent(
            intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
            pending_buy_value_by_ticker={"NVDA": bad_value},
        )
        assert result.approved is False, f"expected pending value {bad_value} to be rejected"
        assert any("pending_buy_value_by_ticker" in v for v in result.violations), result.violations


def test_no_pending_buy_value_leaves_exposure_checks_unaffected():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=5)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True


def test_max_total_exposure_exceeded():
    snapshot = _snapshot(
        positions=[{"ticker": "AAA", "shares": 90, "entry_price": 100.0, "current_price": 100.0}],  # $9000 already invested
        cash=1000.0,  # total equity = 10,000, already 90% invested
    )
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # +$600 -> 96% invested
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=0.90,
    )
    assert any("total-exposure limit" in v for v in result.violations)


def test_basket_concentration_exceeded():
    snapshot = _snapshot(
        positions=[{"ticker": "NVDA", "shares": 30, "entry_price": 100.0, "current_price": 100.0}],  # $3000, semiconductors
        cash=7000.0,  # total equity = 10,000
    )
    intent = TradeIntent(ticker="AMD", side="buy", shares=20)  # +$2000 (AMD price=100) -> semis = $5000 = 50%
    result = validate_trade_intent(
        intent, snapshot, reference_price=100.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=40.0,
    )
    assert any("semiconductors" in v and "basket concentration limit" in v for v in result.violations)


def test_leveraged_etf_exposure_exceeded():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="TQQQ", side="buy", shares=50)  # $2500 -> 25% leveraged, over 20% cap
    result = validate_trade_intent(
        intent, snapshot, reference_price=50.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_leveraged_etf_pct=20.0,
    )
    assert any("leveraged-ETF limit" in v for v in result.violations)


def test_sell_side_skips_exposure_checks():
    snapshot = _snapshot(
        positions=[{"ticker": "TQQQ", "shares": 100, "entry_price": 50.0, "current_price": 50.0}], cash=5000.0,
    )
    intent = TradeIntent(ticker="TQQQ", side="sell", shares=100)  # selling a big leveraged position -- should be fine
    result = validate_trade_intent(intent, snapshot, reference_price=50.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True


def test_stale_price_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0,
        price_timestamp=datetime(2026, 7, 27, 9, 0), now=datetime(2026, 7, 27, 9, 30),
        max_stale_price_minutes=15.0,
    )
    assert any("staleness limit" in v for v in result.violations)


def test_outside_trading_hours_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    weekend = datetime(2026, 8, 1, 10, 0)  # a Saturday
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=weekend)
    assert any("weekend" in v for v in result.violations)

    after_hours = datetime(2026, 7, 27, 20, 0)  # Monday 8pm
    result2 = validate_trade_intent(intent, snapshot, reference_price=60.0, now=after_hours)
    assert any("outside today's trading session" in v for v in result2.violations)


def test_market_holiday_flagged_even_on_a_weekday():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    thanksgiving_2026 = datetime(2026, 11, 26, 10, 0)  # a Thursday, but NYSE is closed
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=thanksgiving_2026)
    assert any("exchange holiday" in v for v in result.violations)


def test_early_close_flagged_after_1pm_the_day_after_thanksgiving():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    # NYSE closes at 13:00 ET the day after Thanksgiving, not the usual 16:00.
    day_after_thanksgiving_afternoon = datetime(2026, 11, 27, 14, 0)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=day_after_thanksgiving_afternoon,
    )
    assert any("outside today's trading session" in v for v in result.violations)

    day_after_thanksgiving_morning = datetime(2026, 11, 27, 10, 0)
    result_ok = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=day_after_thanksgiving_morning,
    )
    assert not any("trading session" in v or "exchange holiday" in v for v in result_ok.violations)


def test_duplicate_order_detected():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    prior = TradeIntent(ticker="KO", side="buy", shares=5)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, recent_intents=[prior])
    assert any("Duplicate order" in v for v in result.violations)


def test_max_slippage_on_limit_order():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1, order_type="limit", limit_price=70.0)  # ref=60, ~16.7% away
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_slippage_pct=1.0)
    assert any("max-slippage limit" in v for v in result.violations)


def test_one_sided_quote_fails_closed():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, bid_price=0.0, ask_price=60.5,
    )
    assert any("one-sided or invalid" in v for v in result.violations)

    result2 = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, bid_price=60.0, ask_price=0.0,
    )
    assert any("one-sided or invalid" in v for v in result2.violations)


def test_crossed_quote_fails_closed():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, bid_price=61.0, ask_price=60.0,
    )
    assert any("crossed" in v for v in result.violations)


def test_missing_bid_or_ask_does_not_run_the_spread_check():
    # Opt-in: callers that never supply a live quote (most tests, and any
    # non-execution caller of this pure gate function) must not be forced
    # into a spread violation just because bid/ask were never passed.
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True


def test_malformed_limit_price_rejected():
    snapshot = _snapshot(cash=10_000.0)
    for bad_limit_price in (None, 0, -5.0, float("nan"), float("inf")):
        intent = TradeIntent(ticker="KO", side="buy", shares=1, order_type="limit", limit_price=bad_limit_price)
        result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
        assert result.approved is False, f"expected limit_price={bad_limit_price} to be rejected"
        assert any("positive, finite limit price" in v for v in result.violations), result.violations


def test_earnings_blackout_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, earnings_days_away=1, earnings_blackout_days=2,
    )
    assert any("earnings blackout" in v for v in result.violations)

    # Outside the window -> not flagged
    result_ok = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, earnings_days_away=10, earnings_blackout_days=2,
    )
    assert not any("earnings blackout" in v for v in result_ok.violations)


def test_concentration_and_earnings_violations_are_overridable():
    # A human can knowingly accept a concentration cap or an earnings-date
    # block (the broker itself would still take the order) -- these are
    # risk-preference/business-calendar calls, not data-integrity issues.
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=100)  # over the 5% default position cap
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        earnings_days_away=1, earnings_blackout_days=2,
    )
    assert result.approved is False
    assert result.overridable is True
    assert result.blocking_violations == ()


def test_hard_safety_violations_are_never_overridable():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, kill_switch_active=True)
    assert result.overridable is False

    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        price_timestamp=datetime(2026, 7, 20, 9, 0), max_stale_price_minutes=15.0,
    )
    assert any("staleness" in v for v in result.violations)
    assert result.overridable is False

    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=datetime(2026, 7, 25, 10, 0),  # a Saturday
    )
    assert any("weekend" in v for v in result.violations)
    assert result.overridable is False


def test_mixed_overridable_and_non_overridable_violations_keeps_both_lists_distinct():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=100)  # over position cap (overridable)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, kill_switch_active=True,  # kill switch (never overridable)
    )
    # Kill switch short-circuits everything else -- only its own violation appears at all.
    assert result.violations == ("Kill switch is active — no trades are permitted.",)
    assert result.overridable is False

    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=datetime(2026, 7, 25, 10, 0),  # weekend (non-overridable)
    )
    assert any("per-position limit" in v for v in result.violations)  # overridable
    assert any("weekend" in v for v in result.violations)  # not overridable
    assert result.overridable is False
    assert any("weekend" in v for v in result.blocking_violations)
    assert not any("per-position limit" in v for v in result.blocking_violations)


def test_authorize_overridden_trade_intent_succeeds_when_every_violation_is_overridable():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        earnings_days_away=1, earnings_blackout_days=2,
    )
    assert result.approved is False
    authorization = authorize_overridden_trade_intent(intent, result)
    assert authorization.proof


def test_authorize_overridden_trade_intent_rejects_a_mixed_result():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=datetime(2026, 7, 25, 10, 0),  # weekend + over position cap
    )
    assert result.approved is False
    try:
        authorize_overridden_trade_intent(intent, result)
        assert False, "a non-overridable violation must never be authorizable via the override path"
    except ValueError as exc:
        assert "not override-eligible" in str(exc)


def test_authorize_overridden_trade_intent_rejects_an_already_approved_result():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True
    try:
        authorize_overridden_trade_intent(intent, result)
        assert False, "an approved result should go through authorize_trade_intent(), not the override path"
    except ValueError as exc:
        assert "already-approved" in str(exc)


def test_authorize_overridden_trade_intent_rejects_a_forged_result():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    real_result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        earnings_days_away=1, earnings_blackout_days=2,
    )
    import dataclasses as dc

    forged = dc.replace(real_result, violation_codes=real_result.violation_codes)
    # Same content, but constructed rather than produced by validate_trade_intent() for THIS
    # exact call -- dataclasses.replace() copies the old (still-valid-looking) proof forward,
    # so this specifically checks the proof is tied to the intent+approved outcome, not
    # merely to matching violation content.
    other_intent = TradeIntent(ticker="AMD", side="buy", shares=100)
    try:
        authorize_overridden_trade_intent(other_intent, forged)
        assert False, "a proof computed for a different intent must not verify"
    except ValueError as exc:
        assert "was not produced by validate_trade_intent" in str(exc)


def test_release_blocker_a_genuine_insufficient_cash_rejection_cannot_be_relabeled_overridable():
    # GPT review, 2026-07-28: the release blocker. A REAL hard rejection
    # (insufficient cash -- never overridable) must not become
    # authorizable by relabeling its violation_codes to something
    # override-eligible via dataclasses.replace() on the SAME intent --
    # the proof must reject this, since it now covers violation_codes.
    import dataclasses as dc

    snapshot = _snapshot(cash=100.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # $600 > $100 cash
    real_result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_position_pct=1.0,
    )
    assert real_result.approved is False
    assert real_result.overridable is False  # insufficient_cash is a hard, non-overridable violation

    forged = dc.replace(real_result, violation_codes=("max_position_pct",))
    assert forged.overridable is True  # the relabeled codes LOOK overridable...
    try:
        authorize_overridden_trade_intent(intent, forged)
        assert False, "relabeling violation_codes on a genuine hard rejection must not authorize it"
    except ValueError as exc:
        assert "was not produced by validate_trade_intent" in str(exc)


def test_release_blocker_a_genuine_stale_price_rejection_cannot_be_relabeled_overridable():
    import dataclasses as dc

    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    real_result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        price_timestamp=datetime(2026, 7, 20, 9, 0), max_stale_price_minutes=15.0,
    )
    assert real_result.approved is False
    assert real_result.overridable is False

    forged = dc.replace(real_result, violation_codes=("earnings_blackout",))
    assert forged.overridable is True
    try:
        authorize_overridden_trade_intent(intent, forged)
        assert False, "relabeling a stale-price rejection's codes must not authorize it"
    except ValueError as exc:
        assert "was not produced by validate_trade_intent" in str(exc)


def test_release_blocker_a_genuine_duplicate_order_rejection_cannot_be_relabeled_overridable():
    import dataclasses as dc

    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    prior = TradeIntent(ticker="KO", side="buy", shares=1)
    real_result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, recent_intents=[prior],
    )
    assert real_result.approved is False
    assert real_result.overridable is False

    forged = dc.replace(real_result, violation_codes=("max_basket_pct",))
    assert forged.overridable is True
    try:
        authorize_overridden_trade_intent(intent, forged)
        assert False, "relabeling a duplicate-order rejection's codes must not authorize it"
    except ValueError as exc:
        assert "was not produced by validate_trade_intent" in str(exc)


def test_validation_result_collections_are_immutable_tuples():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert isinstance(result.violations, tuple)
    assert isinstance(result.violation_codes, tuple)
    try:
        result.violations.append("injected")  # type: ignore[attr-defined]
        assert False, "tuples must not support .append()"
    except AttributeError:
        pass


def test_reordered_violation_codes_produce_the_same_proof():
    # Order of violation_codes is not semantically meaningful -- the
    # signature must be canonical (sorted) so a reordered-but-otherwise-
    # identical codes tuple still verifies.
    from risk.execution_gate import _validation_proof

    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    proof_a = _validation_proof(intent, False, ("max_basket_pct", "max_position_pct"))
    proof_b = _validation_proof(intent, False, ("max_position_pct", "max_basket_pct"))
    assert proof_a == proof_b


if __name__ == "__main__":
    test_clean_trade_is_approved()
    test_kill_switch_blocks_everything_else()
    test_max_position_size_exceeded()
    test_insufficient_cash_flagged()
    test_buying_power_constrains_cash_even_when_raw_cash_looks_sufficient()
    test_pending_buy_value_counts_toward_total_exposure()
    test_pending_buy_value_on_the_same_ticker_counts_toward_position_limit()
    test_no_pending_buy_value_leaves_exposure_checks_unaffected()
    test_non_finite_pending_buy_value_fails_closed_instead_of_disabling_checks()
    test_max_total_exposure_exceeded()
    test_basket_concentration_exceeded()
    test_leveraged_etf_exposure_exceeded()
    test_sell_side_skips_exposure_checks()
    test_stale_price_flagged()
    test_outside_trading_hours_flagged()
    test_market_holiday_flagged_even_on_a_weekday()
    test_early_close_flagged_after_1pm_the_day_after_thanksgiving()
    test_duplicate_order_detected()
    test_one_sided_quote_fails_closed()
    test_crossed_quote_fails_closed()
    test_missing_bid_or_ask_does_not_run_the_spread_check()
    test_malformed_limit_price_rejected()
    test_max_slippage_on_limit_order()
    test_earnings_blackout_flagged()
    test_concentration_and_earnings_violations_are_overridable()
    test_hard_safety_violations_are_never_overridable()
    test_mixed_overridable_and_non_overridable_violations_keeps_both_lists_distinct()
    test_authorize_overridden_trade_intent_succeeds_when_every_violation_is_overridable()
    test_authorize_overridden_trade_intent_rejects_a_mixed_result()
    test_authorize_overridden_trade_intent_rejects_an_already_approved_result()
    test_authorize_overridden_trade_intent_rejects_a_forged_result()
    test_release_blocker_a_genuine_insufficient_cash_rejection_cannot_be_relabeled_overridable()
    test_release_blocker_a_genuine_stale_price_rejection_cannot_be_relabeled_overridable()
    test_release_blocker_a_genuine_duplicate_order_rejection_cannot_be_relabeled_overridable()
    test_validation_result_collections_are_immutable_tuples()
    test_reordered_violation_codes_produce_the_same_proof()
    print("All execution gate tests passed.")
