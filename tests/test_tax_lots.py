"""
Tax-lot ledger: per-lot basis, realized P&L, holding periods, wash-sale flags.

The motivating case (user question, 2026-07-29): buy 2 @ 100, buy 2 @ 90, price
recovers to 95. The average-cost view -- what the portfolio snapshot and the
broker both show -- reports "4 shares, average 95, unrealized 0.00%", which
looks like nothing happened. In fact two lots sit there with opposite signs, and
which one you sell determines whether you realize a harvestable loss, a taxable
gain, or nothing. These tests pin that distinction.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from assistant.storage import AssistantStore
from assistant.tax_lots import (
    FIFO,
    HIFO,
    LIFO,
    SPECIFIC,
    Fill,
    Split,
    TaxLotError,
    _decimal_sum,
    build_ledger,
    compare_sale_bases,
    is_long_term,
    select_lots,
    unrealized_by_lot,
)

DAY1 = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)
DAY2 = DAY1 + timedelta(days=1)
DAY3 = DAY1 + timedelta(days=2)


def _scenario() -> list[Fill]:
    """The user's exact case: 2 @ 100, then 2 @ 90."""
    return [
        Fill("AAPL", "buy", 2, 100.0, DAY1, fill_id="f1"),
        Fill("AAPL", "buy", 2, 90.0, DAY2, fill_id="f2"),
    ]


# --------------------------------------------------------------------------
# the motivating scenario
# --------------------------------------------------------------------------

def test_average_cost_says_flat_while_the_lots_disagree():
    ledger = build_ledger(_scenario())

    assert ledger.shares_held("AAPL") == 4
    assert ledger.average_cost("AAPL") == 95.0
    # What the snapshot shows: exactly zero.
    total_cost = sum(lot.cost_basis for lot in ledger.open_for("AAPL"))
    assert total_cost == 380.0
    assert 4 * 95.0 - total_cost == 0.0

    # What the lots actually hold, at the same price.
    by_lot = {row["lot_id"]: row for row in unrealized_by_lot(ledger, "AAPL", 95.0)}
    assert by_lot["f1"]["unrealized_pnl"] == -10.0
    assert by_lot["f2"]["unrealized_pnl"] == 10.0
    assert round(by_lot["f1"]["unrealized_pnl_pct"], 2) == -5.0
    assert round(by_lot["f2"]["unrealized_pnl_pct"], 2) == 5.56


def test_selling_two_shares_at_95_gives_three_different_answers():
    """Same trade, same price -- the realized result depends only on lot choice.
    This is what average cost structurally cannot represent."""
    ledger = build_ledger(_scenario())
    comparison = compare_sale_bases(ledger, "AAPL", qty=2, price=95.0, when=DAY3)

    assert comparison["average_cost_view"]["realized_pnl"] == 0.0
    assert comparison["methods"][FIFO]["realized_pnl"] == -10.0   # sells the 100 lot
    assert comparison["methods"][LIFO]["realized_pnl"] == 10.0    # sells the 90 lot
    assert comparison["methods"][HIFO]["realized_pnl"] == -10.0   # highest cost first
    # All short-term at 2 days held.
    assert comparison["methods"][FIFO]["short_term_pnl"] == -10.0
    assert comparison["methods"][FIFO]["long_term_pnl"] == 0.0


def test_the_realized_loss_and_gain_are_both_short_term_here():
    ledger = build_ledger(_scenario() + [Fill("AAPL", "sell", 2, 95.0, DAY3, fill_id="s1")])
    assert ledger.realized_pnl("AAPL") == -10.0
    assert ledger.realized_pnl("AAPL", long_term=True) == 0.0
    assert ledger.realized_pnl("AAPL", long_term=False) == -10.0
    assert ledger.shares_held("AAPL") == 2
    # FIFO consumed the 100 lot, leaving the 90 lot open.
    remaining = ledger.open_for("AAPL")
    assert len(remaining) == 1 and remaining[0].cost_per_share == 90.0


# --------------------------------------------------------------------------
# lot selection
# --------------------------------------------------------------------------

def test_selection_methods_pick_the_expected_lots():
    lots = list(build_ledger(_scenario()).open_for("AAPL"))
    assert [lot.lot_id for lot, _ in select_lots(lots, 2, method=FIFO)] == ["f1"]
    assert [lot.lot_id for lot, _ in select_lots(lots, 2, method=LIFO)] == ["f2"]
    assert [lot.lot_id for lot, _ in select_lots(lots, 2, method=HIFO)] == ["f1"]
    assert [lot.lot_id for lot, _ in select_lots(lots, 2, method=SPECIFIC, lot_ids=["f2"])] == ["f2"]


def test_a_sale_spanning_two_lots_splits_them():
    lots = list(build_ledger(_scenario()).open_for("AAPL"))
    chosen = select_lots(lots, 3, method=FIFO)
    assert [(lot.lot_id, take) for lot, take in chosen] == [("f1", 2.0), ("f2", 1.0)]


def test_partially_consuming_a_lot_leaves_the_remainder_open():
    ledger = build_ledger(_scenario() + [Fill("AAPL", "sell", 1, 95.0, DAY3, fill_id="s1")])
    lots = {lot.lot_id: lot for lot in ledger.open_for("AAPL")}
    assert lots["f1"].qty == 1.0, "half the first lot should remain"
    assert lots["f2"].qty == 2.0
    assert ledger.realized_pnl("AAPL") == -5.0


def test_split_preserves_each_lots_total_basis_and_adjusts_future_sale():
    events = _scenario() + [
        Split("AAPL", ratio=4.0, at=DAY3, action_id="split-1"),
        Fill(
            "AAPL",
            "sell",
            4,
            30.0,
            DAY3 + timedelta(hours=1),
            fill_id="s1",
        ),
    ]
    ledger = build_ledger(events)

    # 4 pre-split shares become 16; selling 4 consumes one original share's
    # economics from the first lot (basis $100, proceeds $120).
    assert ledger.shares_held("AAPL") == 12
    assert ledger.realized_pnl("AAPL") == 20.0
    remaining = {lot.lot_id: lot for lot in ledger.open_for("AAPL")}
    assert remaining["f1"].qty == 4
    assert remaining["f1"].cost_per_share == 25.0
    assert remaining["f2"].qty == 8
    assert remaining["f2"].cost_per_share == 22.5
    assert sum(lot.cost_basis for lot in remaining.values()) == 280.0


def test_reverse_split_adjusts_quantity_and_basis():
    ledger = build_ledger(
        [
            Fill("XYZ", "buy", 100, 2.0, DAY1, fill_id="b1"),
            Split("XYZ", ratio=0.1, at=DAY2, action_id="reverse-1"),
        ]
    )
    lot = ledger.open_for("XYZ")[0]
    assert lot.qty == 10
    assert lot.cost_per_share == 20.0
    assert lot.cost_basis == 200.0


def test_overselling_is_refused_rather_than_partially_realized():
    """An over-sale means fills are missing. Realizing less than was sold would
    understate the gain -- the wrong direction, so it fails closed."""
    lots = list(build_ledger(_scenario()).open_for("AAPL"))
    with pytest.raises(TaxLotError) as exc:
        select_lots(lots, 5, method=FIFO)
    assert "only 4" in str(exc.value)
    assert "incomplete" in str(exc.value)


def test_specific_method_requires_and_validates_lot_ids():
    lots = list(build_ledger(_scenario()).open_for("AAPL"))
    with pytest.raises(TaxLotError, match="requires lot_ids"):
        select_lots(lots, 2, method=SPECIFIC)
    with pytest.raises(TaxLotError, match="unknown lot id"):
        select_lots(lots, 2, method=SPECIFIC, lot_ids=["nope"])


def test_an_unknown_selection_method_is_rejected():
    lots = list(build_ledger(_scenario()).open_for("AAPL"))
    with pytest.raises(TaxLotError, match="method must be one of"):
        select_lots(lots, 1, method="cheapest")


# --------------------------------------------------------------------------
# holding period -- the boundary is the day AFTER one year
# --------------------------------------------------------------------------

def test_one_year_exactly_is_still_short_term():
    acquired = datetime(2025, 3, 10, 15, 0, tzinfo=timezone.utc)
    assert is_long_term(acquired, datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)) is False
    assert is_long_term(acquired, datetime(2026, 3, 11, 15, 0, tzinfo=timezone.utc)) is True


def test_a_leap_day_acquisition_does_not_shift_the_boundary():
    acquired = datetime(2024, 2, 29, 15, 0, tzinfo=timezone.utc)
    assert is_long_term(acquired, datetime(2025, 3, 1, 15, 0, tzinfo=timezone.utc)) is False
    assert is_long_term(acquired, datetime(2025, 3, 2, 15, 0, tzinfo=timezone.utc)) is True


def test_selling_before_buying_is_never_long_term():
    assert is_long_term(DAY3, DAY1) is False


def test_days_to_long_term_counts_down():
    acquired = datetime.now(timezone.utc) - timedelta(days=300)
    ledger = build_ledger([Fill("KO", "buy", 1, 50.0, acquired, fill_id="k1")])
    row = unrealized_by_lot(ledger, "KO", 55.0)[0]
    assert row["term_if_sold_now"] == "short"
    assert 60 <= row["days_to_long_term"] <= 67, row["days_to_long_term"]


def test_a_long_held_lot_reports_long_term_and_zero_countdown():
    acquired = datetime.now(timezone.utc) - timedelta(days=400)
    ledger = build_ledger([Fill("KO", "buy", 1, 50.0, acquired, fill_id="k1")])
    row = unrealized_by_lot(ledger, "KO", 55.0)[0]
    assert row["term_if_sold_now"] == "long"
    assert row["days_to_long_term"] == 0


def test_realized_components_are_split_by_term():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    now = datetime.now(timezone.utc)
    ledger = build_ledger([
        Fill("KO", "buy", 1, 40.0, old, fill_id="old"),
        Fill("KO", "buy", 1, 60.0, recent, fill_id="new"),
        Fill("KO", "sell", 2, 50.0, now, fill_id="s"),
    ])
    assert ledger.realized_pnl("KO", long_term=True) == 10.0   # 50 - 40
    assert ledger.realized_pnl("KO", long_term=False) == -10.0  # 50 - 60
    assert ledger.realized_pnl("KO") == 0.0


# --------------------------------------------------------------------------
# wash-sale FLAGGING (never adjustment)
# --------------------------------------------------------------------------

def test_a_loss_with_a_repurchase_inside_30_days_is_flagged():
    ledger = build_ledger([
        Fill("AAPL", "buy", 1, 100.0, DAY1, fill_id="b1"),
        Fill("AAPL", "sell", 1, 90.0, DAY2, fill_id="s1"),
        Fill("AAPL", "buy", 1, 92.0, DAY2 + timedelta(days=5), fill_id="b2"),
    ])
    loss = next(r for r in ledger.realized if r.realized_pnl < 0)
    assert loss.wash_sale_suspected is True


def test_a_loss_with_no_nearby_repurchase_is_not_flagged():
    ledger = build_ledger([
        Fill("AAPL", "buy", 1, 100.0, DAY1, fill_id="b1"),
        Fill("AAPL", "sell", 1, 90.0, DAY2, fill_id="s1"),
        Fill("AAPL", "buy", 1, 92.0, DAY2 + timedelta(days=45), fill_id="b2"),
    ])
    loss = next(r for r in ledger.realized if r.realized_pnl < 0)
    assert loss.wash_sale_suspected is False


def test_a_gain_is_never_flagged_as_a_wash_sale():
    ledger = build_ledger([
        Fill("AAPL", "buy", 1, 90.0, DAY1, fill_id="b1"),
        Fill("AAPL", "sell", 1, 100.0, DAY2, fill_id="s1"),
        Fill("AAPL", "buy", 1, 99.0, DAY2 + timedelta(days=1), fill_id="b2"),
    ])
    gain = next(r for r in ledger.realized if r.realized_pnl > 0)
    assert gain.wash_sale_suspected is False


def test_the_flag_does_not_change_the_realized_amount():
    """Flagging is advisory; basis is never adjusted (see module docstring)."""
    ledger = build_ledger([
        Fill("AAPL", "buy", 1, 100.0, DAY1, fill_id="b1"),
        Fill("AAPL", "sell", 1, 90.0, DAY2, fill_id="s1"),
        Fill("AAPL", "buy", 1, 92.0, DAY2 + timedelta(days=5), fill_id="b2"),
    ])
    assert ledger.realized_pnl("AAPL") == -10.0


# --------------------------------------------------------------------------
# corrupt input fails closed (this project's recurring bug class)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, -1])
def test_a_non_finite_or_non_positive_quantity_is_refused(bad):
    with pytest.raises(TaxLotError):
        Fill("AAPL", "buy", bad, 100.0, DAY1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, -5.0])
def test_a_non_finite_or_non_positive_price_is_refused(bad):
    with pytest.raises(TaxLotError):
        Fill("AAPL", "buy", 1, bad, DAY1)


def test_a_boolean_quantity_is_refused():
    """bool is an int subclass; `qty > 0` alone would accept True as 1 share."""
    with pytest.raises(TaxLotError):
        Fill("AAPL", "buy", True, 100.0, DAY1)


def test_a_naive_timestamp_is_refused():
    with pytest.raises(TaxLotError, match="timezone-aware"):
        Fill("AAPL", "buy", 1, 100.0, datetime(2026, 7, 20, 14, 30))


def test_an_invalid_side_is_refused():
    with pytest.raises(TaxLotError, match="side must be"):
        Fill("AAPL", "short", 1, 100.0, DAY1)


def test_unrealized_by_lot_refuses_a_corrupt_price():
    ledger = build_ledger(_scenario())
    with pytest.raises(TaxLotError):
        unrealized_by_lot(ledger, "AAPL", float("nan"))


# --------------------------------------------------------------------------
# determinism / replay
# --------------------------------------------------------------------------

def test_the_ledger_is_order_independent_and_replayable():
    """Lots are DERIVED from the append-only event journal, so replaying the
    same fills in any input order must give the same ledger -- that is what
    makes having no separate lots table safe."""
    forward = build_ledger(_scenario())
    reversed_input = build_ledger(list(reversed(_scenario())))
    assert [(l.lot_id, l.qty, l.cost_per_share) for l in forward.open_lots] == \
           [(l.lot_id, l.qty, l.cost_per_share) for l in reversed_input.open_lots]


def test_tickers_are_isolated_from_each_other():
    ledger = build_ledger([
        Fill("AAPL", "buy", 2, 100.0, DAY1, fill_id="a1"),
        Fill("MSFT", "buy", 2, 300.0, DAY1, fill_id="m1"),
        Fill("AAPL", "sell", 2, 110.0, DAY2, fill_id="a2"),
    ])
    assert ledger.realized_pnl("AAPL") == 20.0
    assert ledger.realized_pnl("MSFT") == 0.0
    assert ledger.shares_held("MSFT") == 2
    assert ledger.shares_held("AAPL") == 0


def test_lowercase_tickers_are_normalized():
    ledger = build_ledger([
        Fill("aapl", "buy", 1, 100.0, DAY1, fill_id="b"),
        Fill("AAPL", "sell", 1, 110.0, DAY2, fill_id="s"),
    ])
    assert ledger.realized_pnl("aapl") == 10.0
    assert ledger.shares_held("AAPL") == 0


# --------------------------------------------------------------------------
# the storage adapter
# --------------------------------------------------------------------------

def _proposal(pid: str, ticker: str, side: str, shares: int) -> dict:
    return {
        "proposal_id": pid, "created_at": DAY1.isoformat(), "expires_at": DAY3.isoformat(),
        "status": "filled", "idempotency_key": f"idem-{pid}",
        "intent": {"ticker": ticker, "side": side, "shares": shares,
                   "order_type": "market", "limit_price": None},
    }


def test_list_fills_prefers_incremental_stream_fills():
    from assistant.order_lifecycle import journal_broker_order_update

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        store.save_proposal(_proposal("p1", "AAPL", "buy", 2))
        order = {
            "order_id": "o1", "client_order_id": "idem-p1", "ticker": "AAPL", "shares": 2.0,
            "side": "buy", "type": "market", "limit_price": None, "time_in_force": "day",
            "status": "filled", "filled_qty": 2.0, "filled_avg_price": 100.0,
            "submitted_at": DAY1.isoformat(), "updated_at": None,
        }
        journal_broker_order_update(
            store, "p1", order, event_type="fill",
            event_at=DAY1.isoformat(), fill_qty=2.0, fill_price=100.0,
        )
        fills = store.list_fills()
        assert len(fills) == 1
        assert fills[0]["ticker"] == "AAPL"
        assert fills[0]["side"] == "buy"
        assert fills[0]["qty"] == 2.0
        assert fills[0]["price"] == 100.0


def test_list_fills_falls_back_to_the_cumulative_snapshot_when_polling_only():
    """Poll reconciliation never reports incremental fills, only the broker's
    cumulative filled_qty/filled_avg_price."""
    from assistant.order_lifecycle import journal_broker_order_update

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        store.save_proposal(_proposal("p1", "AAPL", "buy", 2))
        order = {
            "order_id": "o1", "client_order_id": "idem-p1", "ticker": "AAPL", "shares": 2.0,
            "side": "buy", "type": "market", "limit_price": None, "time_in_force": "day",
            "status": "filled", "filled_qty": 2.0, "filled_avg_price": 100.0,
            "submitted_at": DAY1.isoformat(), "updated_at": None,
        }
        journal_broker_order_update(
            store, "p1", order, event_type="poll_reconciliation", event_at=DAY1.isoformat(),
        )
        fills = store.list_fills()
        assert len(fills) == 1, f"expected one derived fill, got {fills}"
        assert fills[0]["qty"] == 2.0
        assert fills[0]["price"] == 100.0


def test_list_fills_does_not_double_count_an_order_seen_both_ways():
    """An order with incremental stream fills AND later cumulative poll events
    must contribute its fills exactly once."""
    from assistant.order_lifecycle import journal_broker_order_update

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        store.save_proposal(_proposal("p1", "AAPL", "buy", 2))
        base = {
            "order_id": "o1", "client_order_id": "idem-p1", "ticker": "AAPL", "shares": 2.0,
            "side": "buy", "type": "market", "limit_price": None, "time_in_force": "day",
            "status": "filled", "filled_qty": 2.0, "filled_avg_price": 100.0,
            "submitted_at": DAY1.isoformat(), "updated_at": None,
        }
        journal_broker_order_update(
            store, "p1", base, event_type="fill",
            event_at=DAY1.isoformat(), fill_qty=2.0, fill_price=100.0,
        )
        journal_broker_order_update(
            store, "p1", base, event_type="poll_reconciliation",
            event_at=DAY2.isoformat(),
        )
        fills = store.list_fills()
        assert len(fills) == 1, f"the same order must not be counted twice: {fills}"
        assert sum(f["qty"] for f in fills) == 2.0


def test_list_fills_is_empty_on_a_fresh_database():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        assert store.list_fills() == []
        assert build_ledger([]).open_lots == ()


def test_a_ledger_built_from_journaled_fills_matches_the_direct_ledger():
    """End to end: journal the user's scenario through the real fill path, then
    confirm the derived ledger is the same one the pure functions produce."""
    from assistant.order_lifecycle import journal_broker_order_update

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        for index, (price, at) in enumerate(((100.0, DAY1), (90.0, DAY2)), start=1):
            pid = f"p{index}"
            store.save_proposal(_proposal(pid, "AAPL", "buy", 2))
            journal_broker_order_update(
                store, pid,
                {"order_id": f"o{index}", "client_order_id": f"idem-{pid}", "ticker": "AAPL",
                 "shares": 2.0, "side": "buy", "type": "market", "limit_price": None,
                 "time_in_force": "day", "status": "filled", "filled_qty": 2.0,
                 "filled_avg_price": price, "submitted_at": at.isoformat(), "updated_at": None},
                event_type="fill", event_at=at.isoformat(), fill_qty=2.0, fill_price=price,
            )

        fills = [
            Fill(f["ticker"], f["side"], f["qty"], f["price"],
                 datetime.fromisoformat(f["at"]), fill_id=f["fill_id"])
            for f in store.list_fills()
        ]
        ledger = build_ledger(fills)
        assert ledger.shares_held("AAPL") == 4
        assert ledger.average_cost("AAPL") == 95.0
        pnls = sorted(row["unrealized_pnl"] for row in unrealized_by_lot(ledger, "AAPL", 95.0))
        assert pnls == [-10.0, 10.0], "the two lots must survive the round trip through storage"



def test_buying_more_then_selling_the_old_lot_at_a_loss_is_still_flagged():
    """The genuine wash-sale shape: a replacement position acquired inside the
    window that is NOT disposed of by the loss sale. Excluding the sold shares
    must not break real detection."""
    ledger = build_ledger([
        Fill("AAPL", "buy", 1, 100.0, DAY1, fill_id="old"),
        Fill("AAPL", "buy", 1, 92.0, DAY2, fill_id="replacement"),
        Fill("AAPL", "sell", 1, 90.0, DAY3, fill_id="s1", ),
    ])
    loss = next(r for r in ledger.realized if r.realized_pnl < 0)
    assert loss.lot_id == "old", "FIFO should dispose of the older, higher-cost lot"
    assert loss.wash_sale_suspected is True
    assert ledger.shares_held("AAPL") == 1, "the replacement position is still held"


def test_selling_the_entire_position_at_a_loss_is_not_a_wash_sale():
    """Nothing is held afterwards, so there is no replacement position."""
    ledger = build_ledger([
        Fill("AAPL", "buy", 2, 100.0, DAY1, fill_id="b1"),
        Fill("AAPL", "sell", 2, 90.0, DAY2, fill_id="s1"),
    ])
    loss = next(r for r in ledger.realized if r.realized_pnl < 0)
    assert loss.wash_sale_suspected is False
    assert ledger.shares_held("AAPL") == 0

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# --- an uncovered ticker must not fabricate a cost basis (2026-07-30) ---
#
# ledger.average_cost() returns 0.0 when no lots are known, so the
# average-cost view reported basis=0 and therefore the WHOLE proceeds as gain:
# a "$2,000 realized gain" on a position whose basis is simply unknown. And
# because compare_sale_bases() left `available` for the caller to stamp True
# unconditionally, both the CLI and the UI rendered an empty result instead of
# the "advisory unavailable" branch -- so missing lot history looked exactly
# like "no tax implications". For a tax figure that is the worst direction to
# be wrong in: it overstates the bill and can talk a user out of a
# risk-reducing sell.

def _uncovered_ledger():
    return build_ledger([
        Fill(ticker="AAPL", qty=10, price=50.0,
             at=datetime(2025, 1, 1, tzinfo=timezone.utc), fill_id="f1", side="buy"),
    ])


def test_an_uncovered_ticker_reports_unavailable_rather_than_a_zero_basis():
    result = compare_sale_bases(_uncovered_ledger(), "NVDA", qty=20, price=100.0)

    assert result["available"] is False
    assert result["reason"]
    view = result["average_cost_view"]
    assert view["available"] is False
    assert "unknown -- not zero" in view["reason"]
    assert "cost_per_share" not in view, "must not publish a fabricated basis"
    assert "realized_pnl" not in view, "must not publish a fabricated gain"


def test_a_covered_ticker_still_reports_real_figures():
    """The guard must not suppress genuine advice."""
    ledger = build_ledger([
        Fill(ticker="NVDA", qty=50, price=40.0,
             at=datetime(2025, 1, 1, tzinfo=timezone.utc), fill_id="f2", side="buy"),
    ])
    result = compare_sale_bases(ledger, "NVDA", qty=20, price=100.0)

    assert result["available"] is True
    assert "reason" not in result
    assert result["average_cost_view"]["available"] is True
    assert result["average_cost_view"]["cost_per_share"] == 40.0
    # (100 - 40) * 20
    assert result["methods"]["fifo"]["realized_pnl"] == 1200.0


def test_partial_coverage_does_not_extrapolate_basis_to_uncovered_shares():
    """A partial average cannot be applied to the whole proposed sale."""
    ledger = build_ledger([
        Fill(ticker="NVDA", qty=5, price=40.0,
             at=datetime(2025, 1, 1, tzinfo=timezone.utc), fill_id="f3", side="buy"),
    ])
    result = compare_sale_bases(ledger, "NVDA", qty=20, price=100.0)

    view = result["average_cost_view"]
    assert view["available"] is False
    assert view["covers_only_shares"] == 5
    assert "partial average basis" in view["reason"]
    assert "cost_per_share" not in view
    assert "realized_pnl" not in view
    assert result["available"] is False


@pytest.mark.parametrize(
    ("field", "qty", "price"),
    [
        ("qty", float("nan"), 100.0),
        ("qty", float("inf"), 100.0),
        ("qty", 0.0, 100.0),
        ("qty", True, 100.0),
        ("price", 1.0, float("nan")),
        ("price", 1.0, float("inf")),
        ("price", 1.0, 0.0),
        ("price", 1.0, True),
    ],
)
def test_sale_basis_comparison_rejects_invalid_boundaries(
    field, qty, price
):
    with pytest.raises(TaxLotError, match=field):
        compare_sale_bases(
            _uncovered_ledger(), "NVDA", qty=qty, price=price
        )


def test_sale_basis_comparison_requires_timezone_aware_sale_time():
    with pytest.raises(TaxLotError, match="timezone-aware"):
        compare_sale_bases(
            _uncovered_ledger(),
            "NVDA",
            qty=1,
            price=100,
            when=datetime(2026, 7, 30),
        )


def test_decimal_sum_avoids_binary_float_accumulation_error():
    # Independent review, 2026-07-31 (P2 #4): realized_pnl()/average_cost()
    # used to sum many lots' dollar figures as plain binary floats, which
    # can drift from the exact decimal total -- the textbook case:
    # 0.1 + 0.1 + 0.1 != 0.3 in raw binary float.
    assert 0.1 + 0.1 + 0.1 != 0.3  # the drift this helper avoids
    assert _decimal_sum([0.1, 0.1, 0.1]) == 0.3
