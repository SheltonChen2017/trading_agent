"""Guards for assistant/sleeve_report.py (M1, THREE_SLEEVE_ENGINE_PLAN).

The dangerous failure directions for a sleeve report:

* a threshold boundary that classifies 5.00% as "not yet" (or 4.99% as
  "crossed") silently moves the owner's stated rule;
* a floor comparison made on the DISPLAY-rounded percentage flips the
  verdict exactly at the boundary;
* missing lot coverage that renders as "no crossings" instead of "cannot
  review" turns absent data into a green light;
* dividend postings summed with the wrong sign, or silently dropped when
  unattributed, misstate income; and
* an action-shaped key would turn an observation payload into an
  instruction surface.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

import config
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.sleeve_report import SleeveReportError, evaluate_sleeves
from assistant.tax_lots import Fill, build_ledger

_NOW = datetime(2026, 8, 7, 15, 30, tzinfo=timezone.utc)


def _position(
    ticker: str,
    shares: float,
    current_price: float,
    entry_price: float | None = None,
) -> PortfolioPosition:
    entry = current_price if entry_price is None else entry_price
    return PortfolioPosition(
        ticker=ticker,
        shares=shares,
        entry_price=entry,
        current_price=current_price,
        market_value=shares * current_price,
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=ticker in set(config.LEVERAGED_ETF_TICKERS),
    )


def _snapshot(
    positions: list[PortfolioPosition],
    cash: float = 10_000.0,
    total_equity: float | None = None,
) -> PortfolioSnapshot:
    equity = (
        cash + sum(p.market_value for p in positions)
        if total_equity is None
        else total_equity
    )
    return PortfolioSnapshot(
        positions=positions,
        cash=cash,
        total_equity=equity,
        as_of="2026-08-07",
        source="manual",
        account_mode="manual",
    )


def _buy(ticker: str, qty: float, price: float, *, days_ago: int, fill_id: str = ""):
    return Fill(
        ticker=ticker,
        side="buy",
        qty=qty,
        price=price,
        at=_NOW - timedelta(days=days_ago),
        fill_id=fill_id or f"{ticker}-{days_ago}",
    )


_EMPTY_LEDGER = build_ledger([])


def _dividend_posting(amount: str, ticker: str | None = "JEPQ") -> dict:
    metadata = {"ticker": ticker} if ticker else {}
    return {
        "account": "INCOME:DIVIDENDS",
        "amount": amount,
        "metadata": metadata,
        "source": "corporate_action",
        "transaction_id": f"tx-{amount}-{ticker}",
    }


# ---------------------------------------------------------------------------
# Threshold boundaries (exact, per lot)
# ---------------------------------------------------------------------------


def test_gain_review_threshold_is_inclusive_at_exactly_five_percent():
    """Cost 100, price 105 -> exactly +5.00%: crossed. Price 104.99: not."""
    ledger = build_ledger([_buy("NVDA", 10, 100.0, days_ago=30)])

    at_boundary = evaluate_sleeves(
        _snapshot([_position("NVDA", 10, 105.0)]), ledger, []
    )
    lots = at_boundary["growth_sleeve"]["positions"][0]["lots"]
    assert lots[0]["crossed_gain_review_threshold"] is True
    assert at_boundary["growth_sleeve"]["lots_at_gain_review"] == 1

    below = evaluate_sleeves(
        _snapshot([_position("NVDA", 10, 104.99)]), ledger, []
    )
    assert (
        below["growth_sleeve"]["positions"][0]["lots"][0][
            "crossed_gain_review_threshold"
        ]
        is False
    )
    assert below["growth_sleeve"]["lots_at_gain_review"] == 0


def test_decline_review_threshold_is_inclusive_at_exactly_minus_ten_percent():
    ledger = build_ledger([_buy("AMD", 10, 100.0, days_ago=30)])

    at_boundary = evaluate_sleeves(
        _snapshot([_position("AMD", 10, 90.0)]), ledger, []
    )
    lot = at_boundary["growth_sleeve"]["positions"][0]["lots"][0]
    assert lot["crossed_decline_review_threshold"] is True

    above = evaluate_sleeves(_snapshot([_position("AMD", 10, 90.01)]), ledger, [])
    lot = above["growth_sleeve"]["positions"][0]["lots"][0]
    assert lot["crossed_decline_review_threshold"] is False


def test_thresholds_are_per_lot_not_average_cost():
    """Two lots, 100 and 90. Price 105: the 100-lot crossed (+5.00%), the
    90-lot is far past (+16.67%) -- and at price 96 the average-cost view
    (+1.05% on 95 avg) would show nothing while the 90-lot is +6.67%.

    Average cost is exactly the lens tax_lots.py documents as hiding real
    money; this test pins the engine to the per-lot basis the owner chose.
    """
    ledger = build_ledger(
        [
            _buy("MSFT", 10, 100.0, days_ago=60, fill_id="a"),
            _buy("MSFT", 10, 90.0, days_ago=30, fill_id="b"),
        ]
    )
    report = evaluate_sleeves(_snapshot([_position("MSFT", 20, 96.0)]), ledger, [])
    lots = report["growth_sleeve"]["positions"][0]["lots"]
    by_cost = {lot["cost_per_share"]: lot for lot in lots}
    assert by_cost[100.0]["crossed_gain_review_threshold"] is False
    assert by_cost[90.0]["crossed_gain_review_threshold"] is True
    assert report["growth_sleeve"]["lots_at_gain_review"] == 1


def test_gain_review_carries_the_tax_mechanism_fields():
    """Owner mandate (2026-08-09): every gain crossing shows term and the
    long-term countdown so the tax consequence is visible before acting."""
    ledger = build_ledger([_buy("NVDA", 10, 100.0, days_ago=340)])
    report = evaluate_sleeves(_snapshot([_position("NVDA", 10, 110.0)]), ledger, [])
    lot = report["growth_sleeve"]["positions"][0]["lots"][0]
    assert lot["crossed_gain_review_threshold"] is True
    assert lot["term_if_sold_now"] == "short"
    assert 0 < lot["days_to_long_term"] <= 30


# ---------------------------------------------------------------------------
# Dividend-sleeve floor (exact, compared unrounded)
# ---------------------------------------------------------------------------


def test_floor_status_at_exactly_the_floor_is_at_or_above():
    """10.00% against a 10% floor is AT the floor, not below it."""
    report = evaluate_sleeves(
        _snapshot([_position("JEPQ", 100, 10.0)], cash=9_000.0), _EMPTY_LEDGER, []
    )
    sleeve = report["dividend_sleeve"]
    assert sleeve["pct_of_equity"] == "10"
    assert sleeve["floor_status"] == "at_or_above_floor"


def test_floor_verdict_uses_unrounded_share_not_display_rounding():
    """9.9995% of equity DISPLAYS as 10% after quantizing, but it is below
    the floor and must say so: the verdict may not launder through the
    rounded display value."""
    report = evaluate_sleeves(
        _snapshot(
            [_position("JEPQ", 1, 9_999.5)], cash=90_000.5, total_equity=100_000.0
        ),
        _EMPTY_LEDGER,
        [],
    )
    sleeve = report["dividend_sleeve"]
    assert sleeve["pct_of_equity"] == "10"  # display rounds up...
    assert sleeve["floor_status"] == "below_floor"  # ...the verdict does not


def test_dividend_sleeve_lists_candidates_not_held():
    report = evaluate_sleeves(
        _snapshot([_position("JEPQ", 100, 50.0)]), _EMPTY_LEDGER, []
    )
    assert report["dividend_sleeve"]["candidates_not_held"] == ["JEPI", "NVDY"]


# ---------------------------------------------------------------------------
# Lot-coverage honesty
# ---------------------------------------------------------------------------


def test_position_with_no_lots_reports_none_coverage_not_zero_crossings():
    """A growth position with no recorded fills must say review is not
    possible -- silence here would read as 'no crossings'."""
    report = evaluate_sleeves(
        _snapshot([_position("NVDA", 10, 500.0)]), _EMPTY_LEDGER, []
    )
    position = report["growth_sleeve"]["positions"][0]
    assert position["lot_coverage"] == "none"
    assert "not possible" in position["coverage_reason"]
    assert position["lots"] == []


def test_partial_lot_coverage_reports_both_share_counts():
    ledger = build_ledger([_buy("NVDA", 4, 100.0, days_ago=30)])
    report = evaluate_sleeves(_snapshot([_position("NVDA", 10, 120.0)]), ledger, [])
    position = report["growth_sleeve"]["positions"][0]
    assert position["lot_coverage"] == "partial"
    assert position["snapshot_shares"] == 10
    assert position["ledger_lot_shares"] == 4
    assert "10" in position["coverage_reason"]
    assert "4" in position["coverage_reason"]
    # The covered lot is still reviewed.
    assert position["lots"][0]["crossed_gain_review_threshold"] is True


def test_full_coverage_has_no_reason_attached():
    ledger = build_ledger([_buy("TSM", 10, 200.0, days_ago=30)])
    report = evaluate_sleeves(_snapshot([_position("TSM", 10, 205.0)]), ledger, [])
    position = report["growth_sleeve"]["positions"][0]
    assert position["lot_coverage"] == "full"
    assert position["coverage_reason"] is None


def test_invalid_price_degrades_that_position_loudly_not_the_report():
    ledger = build_ledger([_buy("NVDA", 10, 100.0, days_ago=30)])
    report = evaluate_sleeves(
        _snapshot(
            [_position("NVDA", 10, 0.0), _position("AMD", 5, 100.0)],
            total_equity=50_000.0,
        ),
        ledger,
        [],
    )
    by_ticker = {p["ticker"]: p for p in report["growth_sleeve"]["positions"]}
    assert by_ticker["NVDA"]["lot_coverage"] == "unavailable"
    assert "unavailable" in by_ticker["NVDA"]["coverage_reason"]
    assert by_ticker["AMD"]["lot_coverage"] == "none"  # AMD still reported


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("equity", [0.0, -5.0, math.nan, math.inf])
def test_unusable_equity_refuses_the_report(equity):
    with pytest.raises(SleeveReportError):
        evaluate_sleeves(
            _snapshot([_position("JEPQ", 10, 50.0)], total_equity=equity),
            _EMPTY_LEDGER,
            [],
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gain_threshold_pct": 0.0},
        {"gain_threshold_pct": -5.0},
        {"decline_threshold_pct": 0.0},
        {"decline_threshold_pct": 10.0},
        {"floor_pct": -1.0},
        {"floor_pct": math.nan},
        {"gain_threshold_pct": math.inf},
    ],
)
def test_nonsense_thresholds_are_rejected(kwargs):
    with pytest.raises(SleeveReportError):
        evaluate_sleeves(_snapshot([]), _EMPTY_LEDGER, [], **kwargs)


# ---------------------------------------------------------------------------
# Dividend income from the journal
# ---------------------------------------------------------------------------


def test_income_is_negated_sum_of_income_postings():
    """A $50 dividend posts as -50 to INCOME:DIVIDENDS (double entry);
    received income is therefore the NEGATED sum."""
    report = evaluate_sleeves(
        _snapshot([]),
        _EMPTY_LEDGER,
        [_dividend_posting("-50"), _dividend_posting("-25.50", ticker="JEPI")],
    )
    income = report["dividend_income"]
    assert income["confirmed_total"] == "75.5"
    assert income["by_ticker"] == {"JEPI": "25.5", "JEPQ": "50"}
    assert income["posting_count"] == 2


def test_unattributed_income_is_bucketed_not_dropped():
    report = evaluate_sleeves(
        _snapshot([]),
        _EMPTY_LEDGER,
        [_dividend_posting("-50"), _dividend_posting("-10", ticker=None)],
    )
    income = report["dividend_income"]
    assert income["confirmed_total"] == "60"
    assert income["unattributed_total"] == "10"
    assert income["by_ticker"] == {"JEPQ": "50"}


def test_non_income_postings_are_ignored():
    report = evaluate_sleeves(
        _snapshot([]),
        _EMPTY_LEDGER,
        [
            {"account": "ASSETS:CASH", "amount": "50", "metadata": {}},
            _dividend_posting("-50"),
        ],
    )
    assert report["dividend_income"]["confirmed_total"] == "50"
    assert report["dividend_income"]["posting_count"] == 1


def test_positive_income_posting_refuses_rather_than_misstating():
    """A positive INCOME:DIVIDENDS amount is a reversal or corruption;
    counting it either way would misstate income, so the report refuses."""
    with pytest.raises(SleeveReportError):
        evaluate_sleeves(_snapshot([]), _EMPTY_LEDGER, [_dividend_posting("50")])


def test_m1_carries_no_reinvestable_budget_field():
    """Deliberate M1 scope: without M3's earmark records a budget number
    has undefined double-spend semantics. The note says so instead."""
    report = evaluate_sleeves(
        _snapshot([]), _EMPTY_LEDGER, [_dividend_posting("-50")]
    )
    assert "budget" not in str(sorted(_all_keys(report)))
    assert "M3" in report["dividend_income"]["note"]


# ---------------------------------------------------------------------------
# Single-issuer overlap disclosure
# ---------------------------------------------------------------------------


def test_nvdy_with_direct_nvda_and_nvdl_names_every_route():
    report = evaluate_sleeves(
        _snapshot(
            [
                _position("NVDY", 100, 13.0),
                _position("NVDA", 10, 220.0),
                _position("NVDL", 20, 36.0),
            ]
        ),
        _EMPTY_LEDGER,
        [],
    )
    overlaps = report["single_issuer_overlap"]
    assert len(overlaps) == 1
    assert overlaps[0]["issuer"] == "NVDA"
    routes = " ".join(overlaps[0]["routes"])
    assert "NVDY" in routes and "NVDA held directly" in routes and "NVDL" in routes


def test_nvdy_alone_discloses_nothing():
    """One route is not an overlap; the disclosure fires only when the same
    issuer is reachable twice."""
    report = evaluate_sleeves(
        _snapshot([_position("NVDY", 100, 13.0)]), _EMPTY_LEDGER, []
    )
    assert report["single_issuer_overlap"] == []


def test_diversified_income_funds_never_appear_in_overlap():
    report = evaluate_sleeves(
        _snapshot([_position("JEPI", 100, 57.0), _position("TQQQ", 10, 74.0)]),
        _EMPTY_LEDGER,
        [],
    )
    assert report["single_issuer_overlap"] == []


# ---------------------------------------------------------------------------
# Payload discipline
# ---------------------------------------------------------------------------


def _all_keys(node, path="") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(f"{path}.{key}")
            found.extend(_all_keys(value, f"{path}.{key}"))
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            found.extend(_all_keys(item, f"{path}[{index}]"))
    return found


def test_report_carries_no_action_shaped_field():
    """CLAUDE.md section 8: observation payloads must not carry instruction
    keys. Same lexical guard the idle-cash and attribution reports pin."""
    ledger = build_ledger(
        [
            _buy("NVDA", 10, 100.0, days_ago=340),
            _buy("AMD", 10, 100.0, days_ago=30),
        ]
    )
    report = evaluate_sleeves(
        _snapshot(
            [
                _position("NVDA", 10, 110.0),
                _position("AMD", 10, 85.0),
                _position("JEPQ", 100, 10.0),
                _position("NVDY", 100, 13.0),
                _position("NVDL", 20, 36.0),
            ]
        ),
        ledger,
        [_dividend_posting("-50"), _dividend_posting("-10", ticker=None)],
    )
    forbidden = ("buy", "sell", "order", "recommend", "suggest", "should", "trade")
    offending = [
        key
        for key in _all_keys(report)
        if any(word in key.rsplit(".", 1)[-1].lower() for word in forbidden)
    ]
    assert not offending, offending


def test_report_is_json_serializable_as_is():
    import json

    ledger = build_ledger([_buy("NVDA", 10, 100.0, days_ago=30)])
    report = evaluate_sleeves(
        _snapshot([_position("NVDA", 10, 110.0)]), ledger, [_dividend_posting("-50")]
    )
    json.dumps(report)  # raises on Decimal leakage


def test_engine_metadata_names_preference_not_research():
    report = evaluate_sleeves(_snapshot([]), _EMPTY_LEDGER, [])
    assert "not validated research" in report["engine"]["authority"]
    assert report["engine"]["threshold_basis"] == "per_lot_cost_per_share"


# ---------------------------------------------------------------------------
# CLI: the report command must leave the database untouched
# ---------------------------------------------------------------------------


def test_cli_sleeve_report_leaves_every_table_unchanged(tmp_path, monkeypatch, capsys):
    """Behavioral read-only proof over the WHOLE database, not a named
    subset: any table gaining or losing a row -- registry, execution,
    evidence, journal, anything -- fails this test. The CLI also opens the
    store read_only in production; this asserts the handler itself never
    needed a write even against a writable store."""
    import argparse

    import scripts.run_personal_assistant as cli
    from assistant.portfolio_ledger import record_dividend
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "sleeves.db")
    record_dividend(
        store,
        external_id="div-1",
        ticker="JEPQ",
        gross_amount="50",
        occurred_at="2026-08-01T12:00:00+00:00",
    )

    def _counts():
        with store._connect() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            return {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in tables
            }

    monkeypatch.setattr(cli, "is_configured", lambda: False)
    before = _counts()
    cli.command_sleeve_report(argparse.Namespace(json=True), store)
    after = _counts()
    assert after == before

    import json as _json

    payload = _json.loads(capsys.readouterr().out)
    assert payload["dividend_income"]["confirmed_total"] == "50"


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------


def test_reinvest_tickers_are_a_subset_of_the_leveraged_list():
    """The max_leveraged_etf_pct cap's accounting keys off
    LEVERAGED_ETF_TICKERS; a reinvest destination outside that list would be
    silently exempt from the cap. Adding one must fail here first."""
    missing = set(config.DIVIDEND_REINVEST_TICKERS) - set(
        config.LEVERAGED_ETF_TICKERS
    )
    assert not missing, (
        f"reinvest destinations outside LEVERAGED_ETF_TICKERS: {sorted(missing)}"
    )


def test_sleeve_lists_do_not_overlap_each_other():
    """One name in two sleeves would double-count its market value across
    sleeve percentages."""
    dividend = set(config.DIVIDEND_INCOME_TICKERS)
    growth = set(config.GROWTH_ROTATION_TICKERS)
    reinvest = set(config.DIVIDEND_REINVEST_TICKERS)
    assert not dividend & growth
    assert not dividend & reinvest
    assert not growth & reinvest


def test_single_stock_income_map_is_not_in_leveraged_accounting():
    """NVDY is disclosure-mapped, not leveraged-mapped: putting it in
    LEVERAGED_ETF_UNDERLYING/TICKERS would change max_leveraged_etf_pct
    enforcement, which is a policy behavior change config must not smuggle."""
    for income_etf in config.SINGLE_STOCK_INCOME_ETF_UNDERLYING:
        assert income_etf not in config.LEVERAGED_ETF_TICKERS
        assert income_etf not in config.LEVERAGED_ETF_UNDERLYING
