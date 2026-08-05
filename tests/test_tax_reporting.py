"""GR-7a: annual realized-gain reporting.

Pins the archived plan's §12 item 4 contract plus this project's honesty
rules: the report reproduces `tax_lots.py`'s verdicts rather than
re-deriving them, rows sum to the stated totals exactly (Decimal, not
float drift), tax-year bucketing happens in market-local time, wash-sale
entries stay advisory flags, and an incomplete or unverified share
coverage is stated IN the artifact rather than silently exported as
though it were complete.

Run with: python -m pytest tests/test_tax_reporting.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from assistant.corporate_actions import tax_ledger_with_coverage
from assistant.storage import AssistantStore
from assistant.tax_reporting import (
    LONG_TERM,
    SHORT_TERM,
    TAX_YEAR_TIMEZONE,
    AnnualTaxReport,
    TaxReportError,
    build_annual_tax_report,
    render_tax_report_csv,
    render_tax_report_json,
    tax_year_of,
)

UTC = timezone.utc


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "tax.db")


def _fill(store, fill_id, ticker, side, qty, price, at):
    """Seed one fill through the REAL path.

    Fills are derived from the append-only `broker_order_events` journal
    (see `AssistantStore.list_fills`), not a separate table, so the tests
    exercise the same replay the production report uses rather than a
    convenient fiction.
    """
    from assistant.order_lifecycle import journal_broker_order_update

    proposal_id = f"p-{fill_id}"
    store.save_proposal(
        {
            "proposal_id": proposal_id,
            "created_at": at.isoformat(),
            "expires_at": (at + timedelta(hours=4)).isoformat(),
            "status": "filled",
            "idempotency_key": f"idem-{proposal_id}",
            "intent": {
                "ticker": ticker,
                "side": side,
                "shares": qty,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )
    order = {
        "order_id": f"o-{fill_id}",
        "client_order_id": f"idem-{proposal_id}",
        "ticker": ticker,
        "shares": float(qty),
        "side": side,
        "type": "market",
        "limit_price": None,
        "time_in_force": "day",
        "status": "filled",
        "filled_qty": float(qty),
        "filled_avg_price": float(price),
        "submitted_at": at.isoformat(),
        "updated_at": None,
    }
    journal_broker_order_update(
        store,
        proposal_id,
        order,
        event_type="fill",
        event_at=at.isoformat(),
        fill_qty=float(qty),
        fill_price=float(price),
    )


def _round_trip(store, *, buy_at, sell_at, buy_price=100.0, sell_price=150.0, qty=10):
    """One clean buy->sell round trip, the simplest realized event."""
    _fill(store, "b1", "AAPL", "buy", qty, buy_price, buy_at)
    _fill(store, "s1", "AAPL", "sell", qty, sell_price, sell_at)


# --- tax-year bucketing (market-local, not UTC) ----------------------------


def test_tax_year_uses_market_local_time_not_utc():
    """A sale at 02:00 UTC on 1 January happened the previous evening in
    New York and belongs to the PREVIOUS tax year. Bucketing on the raw
    UTC date would silently move late-December sales a year forward."""
    new_year_utc = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    assert new_year_utc.year == 2026
    assert tax_year_of(new_year_utc) == 2025

    midyear = datetime(2026, 6, 15, 18, 0, tzinfo=UTC)
    assert tax_year_of(midyear) == 2026


def test_report_buckets_the_new_year_boundary_sale_into_the_prior_year(store):
    buy = datetime(2025, 6, 1, 14, 0, tzinfo=UTC)
    sell = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)  # 2025-12-31 21:00 ET
    _round_trip(store, buy_at=buy, sell_at=sell)

    assert build_annual_tax_report(store, 2025).total.sale_count == 1
    assert build_annual_tax_report(store, 2026).total.sale_count == 0


# --- the numbers themselves ------------------------------------------------


def test_realized_row_matches_the_lot_ledger_exactly(store):
    buy = datetime(2025, 3, 3, 14, 30, tzinfo=UTC)
    sell = datetime(2026, 4, 6, 14, 30, tzinfo=UTC)  # > 1 year: long term
    _round_trip(store, buy_at=buy, sell_at=sell, buy_price=100.0, sell_price=150.0, qty=10)

    report = build_annual_tax_report(store, 2026)
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.ticker == "AAPL"
    assert row.quantity == Decimal("10")
    assert row.cost_basis == Decimal("1000")
    assert row.proceeds == Decimal("1500")
    assert row.realized_pnl == Decimal("500")
    assert row.holding_period == LONG_TERM
    assert row.wash_sale_suspected is False


def test_short_and_long_term_are_split_and_totals_sum_exactly(store):
    # Short-term: bought and sold inside a year, at a loss.
    _fill(store, "b-short", "MSFT", "buy", 5, 200.0, datetime(2026, 2, 2, 15, tzinfo=UTC))
    _fill(store, "s-short", "MSFT", "sell", 5, 180.0, datetime(2026, 5, 5, 15, tzinfo=UTC))
    # Long-term: held over a year, at a gain.
    _fill(store, "b-long", "AAPL", "buy", 10, 100.0, datetime(2025, 1, 6, 15, tzinfo=UTC))
    _fill(store, "s-long", "AAPL", "sell", 10, 150.0, datetime(2026, 6, 8, 15, tzinfo=UTC))

    report = build_annual_tax_report(store, 2026)
    assert report.short_term.sale_count == 1
    assert report.long_term.sale_count == 1
    assert report.short_term.realized_pnl == Decimal("-100")
    assert report.long_term.realized_pnl == Decimal("500")

    # Exact Decimal identities: the exported rows must sum to the exported
    # totals with no float drift, and the two buckets must partition it.
    assert report.total.realized_pnl == Decimal("400")
    assert sum((r.realized_pnl for r in report.rows), Decimal("0")) == report.total.realized_pnl
    assert sum((r.proceeds for r in report.rows), Decimal("0")) == report.total.proceeds
    assert sum((r.cost_basis for r in report.rows), Decimal("0")) == report.total.cost_basis
    assert (
        report.short_term.realized_pnl + report.long_term.realized_pnl
        == report.total.realized_pnl
    )
    assert report.short_term.sale_count + report.long_term.sale_count == len(report.rows)


def test_fractional_quantities_do_not_drift(store):
    """Float arithmetic on 0.1-style quantities is exactly where a naive
    implementation loses cents; the report must stay decimal-exact."""
    at_buy = datetime(2026, 2, 2, 15, tzinfo=UTC)
    at_sell = datetime(2026, 3, 3, 15, tzinfo=UTC)
    _fill(store, "b-frac", "NVDA", "buy", 0.1, 10.10, at_buy)
    _fill(store, "s-frac", "NVDA", "sell", 0.1, 20.20, at_sell)

    report = build_annual_tax_report(store, 2026)
    row = report.rows[0]
    assert row.cost_basis == Decimal("1.010")
    assert row.proceeds == Decimal("2.020")
    assert row.realized_pnl == Decimal("1.010")
    assert report.total.realized_pnl == row.realized_pnl


def test_open_positions_are_never_reported_as_realized(store):
    _fill(store, "b-open", "AMZN", "buy", 3, 100.0, datetime(2026, 4, 4, 15, tzinfo=UTC))
    report = build_annual_tax_report(store, 2026)
    assert report.rows == ()
    assert report.total.realized_pnl == Decimal("0")
    assert report.total.sale_count == 0


# --- wash sales stay advisory ----------------------------------------------


def test_wash_sale_is_flagged_but_never_adjusts_basis(store):
    """A loss sale with a repurchase inside the window is FLAGGED; the
    reported basis and P&L are unchanged, because the real rule spans
    accounts this app cannot see."""
    _fill(store, "b1", "MSFT", "buy", 10, 200.0, datetime(2026, 3, 2, 15, tzinfo=UTC))
    _fill(store, "s1", "MSFT", "sell", 10, 180.0, datetime(2026, 4, 1, 15, tzinfo=UTC))
    _fill(store, "b2", "MSFT", "buy", 10, 185.0, datetime(2026, 4, 10, 15, tzinfo=UTC))

    report = build_annual_tax_report(store, 2026)
    flagged = [row for row in report.rows if row.wash_sale_suspected]
    assert len(flagged) == 1
    assert report.wash_sale_flagged_count == 1
    # Unadjusted: the loss is still the full -200.
    assert flagged[0].realized_pnl == Decimal("-200")
    assert report.total.realized_pnl == Decimal("-200")


def test_a_gain_is_never_wash_sale_flagged(store):
    _round_trip(
        store,
        buy_at=datetime(2026, 3, 2, 15, tzinfo=UTC),
        sell_at=datetime(2026, 4, 1, 15, tzinfo=UTC),
        buy_price=100.0,
        sell_price=150.0,
    )
    _fill(store, "b2", "AAPL", "buy", 10, 149.0, datetime(2026, 4, 5, 15, tzinfo=UTC))
    report = build_annual_tax_report(store, 2026)
    assert report.wash_sale_flagged_count == 0


# --- coverage honesty ------------------------------------------------------


def _positions(shares: float, ticker: str = "AAPL"):
    return [
        {
            "ticker": ticker,
            "shares": shares,
            "entry_price": 100.0,
            "current_price": 120.0,
        }
    ]


def test_coverage_unverified_when_no_portfolio_is_supplied(store):
    _round_trip(
        store,
        buy_at=datetime(2026, 1, 5, 15, tzinfo=UTC),
        sell_at=datetime(2026, 2, 5, 15, tzinfo=UTC),
    )
    report = build_annual_tax_report(store, 2026)
    assert report.coverage["complete"] is None
    assert report.coverage["verified"] is False
    # Unverified is NOT complete -- the conservative direction.
    assert report.complete is False


def test_coverage_complete_when_ledger_matches_the_broker(store):
    buy_at = datetime(2026, 1, 5, 15, tzinfo=UTC)
    _fill(store, "b1", "AAPL", "buy", 10, 100.0, buy_at)
    _fill(store, "s1", "AAPL", "sell", 4, 150.0, datetime(2026, 2, 5, 15, tzinfo=UTC))

    snapshot = build_portfolio_snapshot(_positions(6), 1_000.0)
    report = build_annual_tax_report(store, 2026, portfolio=snapshot)
    assert report.coverage["complete"] is True
    assert report.complete is True
    assert report.coverage["tickers"]["AAPL"]["matched"] is True


def test_missing_fill_history_makes_the_report_incomplete(store):
    """The dangerous case: the broker holds more shares than the app can
    account for, so realized history is missing sales."""
    _fill(store, "b1", "AAPL", "buy", 10, 100.0, datetime(2026, 1, 5, 15, tzinfo=UTC))
    snapshot = build_portfolio_snapshot(_positions(25), 1_000.0)  # 15 unexplained

    report = build_annual_tax_report(store, 2026, portfolio=snapshot)
    assert report.complete is False
    assert report.coverage["verified"] is True
    assert "INCOMPLETE" in report.coverage["reason"]
    assert report.coverage["tickers"]["AAPL"]["matched"] is False


def test_coverage_verdict_agrees_with_the_proposal_path(store):
    """The report must not invent a second coverage rule: its verdict has
    to match `tax_ledger_with_coverage()`, which proposals already use."""
    _fill(store, "b1", "AAPL", "buy", 10, 100.0, datetime(2026, 1, 5, 15, tzinfo=UTC))
    for broker_shares, expected in ((10, True), (25, False)):
        snapshot = build_portfolio_snapshot(_positions(broker_shares), 1_000.0)
        _, coverage = tax_ledger_with_coverage(store, snapshot)
        report = build_annual_tax_report(store, 2026, portfolio=snapshot)
        assert coverage["complete"] is expected
        assert report.coverage["complete"] is expected


def test_unbuildable_ledger_refuses_instead_of_reporting_zero(store):
    """A sale with no matching lot must not silently produce an empty,
    confident-looking report."""
    _fill(store, "s-orphan", "AAPL", "sell", 5, 150.0, datetime(2026, 2, 5, 15, tzinfo=UTC))
    with pytest.raises(TaxReportError, match="ledger could not be built"):
        build_annual_tax_report(store, 2026)


@pytest.mark.parametrize("year", ["2026", 2026.0, True, 1800, 3000, None])
def test_invalid_tax_years_are_refused(store, year):
    with pytest.raises(TaxReportError):
        build_annual_tax_report(store, year)


# --- the exported artifact -------------------------------------------------


def _csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_csv_states_completeness_on_the_first_lines(store):
    _fill(store, "b1", "AAPL", "buy", 10, 100.0, datetime(2026, 1, 5, 15, tzinfo=UTC))
    snapshot = build_portfolio_snapshot(_positions(25), 1_000.0)
    incomplete = render_tax_report_csv(
        build_annual_tax_report(store, 2026, portfolio=snapshot)
    )
    rows = _csv_rows(incomplete)
    assert "tax year 2026" in rows[0][0]
    # The limitation must be visible immediately, not buried below a table
    # an accountant might read in isolation.
    assert "INCOMPLETE" in rows[1][0]

    unverified = render_tax_report_csv(build_annual_tax_report(store, 2026))
    assert "COVERAGE UNVERIFIED" in _csv_rows(unverified)[1][0]


def test_csv_contains_rows_totals_and_the_wash_sale_disclaimer(store):
    _fill(store, "b1", "MSFT", "buy", 10, 200.0, datetime(2026, 3, 2, 15, tzinfo=UTC))
    _fill(store, "s1", "MSFT", "sell", 10, 180.0, datetime(2026, 4, 1, 15, tzinfo=UTC))
    _fill(store, "b2", "MSFT", "buy", 10, 185.0, datetime(2026, 4, 10, 15, tzinfo=UTC))

    text = render_tax_report_csv(build_annual_tax_report(store, 2026))
    assert "wash-sale" in text.lower()
    assert "NOT tax advice" in text
    assert "Cost basis is never adjusted" in text

    rows = _csv_rows(text)
    header_index = next(i for i, r in enumerate(rows) if r and r[0] == "ticker")
    data = rows[header_index + 1]
    assert data[0] == "MSFT"
    assert data[5] == SHORT_TERM
    assert data[9] == "yes"  # wash-sale flag column
    assert any(r and r[0] == "SHORT-TERM TOTAL" for r in rows)
    assert any(r and r[0] == "TOTAL" for r in rows)


def test_json_round_trips_and_carries_coverage_and_disclaimers(store):
    _round_trip(
        store,
        buy_at=datetime(2026, 1, 5, 15, tzinfo=UTC),
        sell_at=datetime(2026, 2, 5, 15, tzinfo=UTC),
    )
    snapshot = build_portfolio_snapshot(_positions(0), 1_000.0)
    payload = json.loads(
        render_tax_report_json(
            build_annual_tax_report(store, 2026, portfolio=snapshot)
        )
    )
    assert payload["tax_year"] == 2026
    assert payload["complete"] is True
    assert payload["coverage"]["verified"] is True
    assert payload["disclaimers"]
    assert payload["rows"][0]["holding_period"] == SHORT_TERM
    # Money is exported as exact text, never as a float.
    assert isinstance(payload["total"]["realized_pnl"], str)


def test_report_is_read_only(store):
    """A report must never mutate proposal, journal, or fill state."""
    _round_trip(
        store,
        buy_at=datetime(2026, 1, 5, 15, tzinfo=UTC),
        sell_at=datetime(2026, 2, 5, 15, tzinfo=UTC),
    )
    with store._connect() as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "broker_order_events",
                "journal_transactions",
                "trade_proposals",
            )
        }
    build_annual_tax_report(store, 2026)
    render_tax_report_csv(build_annual_tax_report(store, 2026))
    with store._connect() as connection:
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "broker_order_events",
                "journal_transactions",
                "trade_proposals",
            )
        }
    assert before == after


# --- CLI -------------------------------------------------------------------


def _args(tmp_path, **overrides):
    defaults = dict(
        year=2026,
        format="csv",
        output=None,
        no_coverage_check=True,
    )
    defaults.update(overrides)
    return type("Args", (), defaults)()


def test_cli_writes_the_artifact_and_exits_2_when_unverified(store, tmp_path, capsys):
    import scripts.run_personal_assistant as cli

    _round_trip(
        store,
        buy_at=datetime(2026, 1, 5, 15, tzinfo=UTC),
        sell_at=datetime(2026, 2, 5, 15, tzinfo=UTC),
    )
    output = tmp_path / "reports" / "2026.csv"
    with pytest.raises(SystemExit) as excinfo:
        cli.command_tax_report(_args(tmp_path, output=output), store)
    assert excinfo.value.code == 2

    # Exiting nonzero must NOT mean refusing to produce the artifact: the
    # owner still needs to see what exists, with the limitation stated.
    assert output.exists()
    assert "COVERAGE UNVERIFIED" in output.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "COVERAGE WARNING" in out
    assert "wash-sale flag(s) (advisory only)" in out


def test_cli_exits_zero_only_when_coverage_is_verified_complete(
    store, tmp_path, monkeypatch, capsys
):
    import scripts.run_personal_assistant as cli

    _fill(store, "b1", "AAPL", "buy", 10, 100.0, datetime(2026, 1, 5, 15, tzinfo=UTC))
    _fill(store, "s1", "AAPL", "sell", 4, 150.0, datetime(2026, 2, 5, 15, tzinfo=UTC))

    class _Packet:
        portfolio = build_portfolio_snapshot(_positions(6), 1_000.0)

    monkeypatch.setattr(
        cli, "_packet", lambda include_events=False, store=None: _Packet()
    )
    cli.command_tax_report(
        _args(tmp_path, no_coverage_check=False, format="json"), store
    )
    out = capsys.readouterr().out
    assert "COVERAGE WARNING" not in out
    assert '"complete": true' in out


def test_cli_survives_a_broker_outage_and_marks_the_report_unverified(
    store, tmp_path, monkeypatch, capsys
):
    """A data outage must degrade the coverage claim, not crash the export
    or silently assert completeness."""
    import scripts.run_personal_assistant as cli

    def _explode(include_events=False, store=None):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(cli, "_packet", _explode)
    with pytest.raises(SystemExit) as excinfo:
        cli.command_tax_report(_args(tmp_path, no_coverage_check=False), store)
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "Coverage check unavailable" in out
    assert "COVERAGE UNVERIFIED" in out
