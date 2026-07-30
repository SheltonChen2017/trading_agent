from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd

from assistant.corporate_actions import confirmed_distributions
from assistant.portfolio_ledger import record_dividend
from assistant.storage import AssistantStore
from data.corporate_actions import (
    fetch_recent_splits,
    fetch_upcoming_ex_dividends,
)
from data.event_data import upcoming_quad_witching_dates


class _FakeTicker:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.calendar = {
            "Ex-Dividend Date": pd.Timestamp("2026-08-15")
        }
        self.splits = pd.Series(
            [4.0, 2.0],
            index=[
                pd.Timestamp("2025-01-10"),
                pd.Timestamp("2026-07-15"),
            ],
        )


def test_reference_dividend_and_split_discovery_never_claims_confirmation():
    original = sys.modules.get("yfinance")
    sys.modules["yfinance"] = SimpleNamespace(Ticker=_FakeTicker)
    try:
        dividends = fetch_upcoming_ex_dividends(
            ["aapl"], as_of=date(2026, 7, 30)
        )
        splits = fetch_recent_splits(
            ["aapl"],
            since=date(2026, 1, 1),
            as_of=date(2026, 7, 30),
        )
    finally:
        if original is None:
            sys.modules.pop("yfinance", None)
        else:
            sys.modules["yfinance"] = original

    assert dividends["AAPL"]["event_date"] == "2026-08-15"
    assert not dividends["AAPL"]["account_confirmed"]
    assert splits["AAPL"] == [
        {
            "ticker": "AAPL",
            "event_type": "split",
            "event_date": "2026-07-15",
            "ratio": 2.0,
            "source": "yfinance.splits",
            "fetched_at": splits["AAPL"][0]["fetched_at"],
            "account_confirmed": False,
        }
    ]


def test_quad_witching_is_deterministic_calendar_context_not_prediction():
    events = upcoming_quad_witching_dates(
        date(2026, 1, 1), horizon_days=100
    )
    assert len(events) == 1
    assert events[0]["event_date"] == "2026-03-20"
    assert events[0]["predictive"] is False


def test_confirmed_dividends_convert_to_performance_distributions(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    record_dividend(
        store,
        external_id="aapl-div-1",
        ticker="AAPL",
        gross_amount="5",
        occurred_at="2026-08-01T14:00:00+00:00",
        ex_date="2026-07-10",
        amount_per_share="0.25",
        shares_entitled="20",
        tax_classification="qualified",
    )
    record_dividend(
        store,
        external_id="legacy-div",
        ticker="KO",
        gross_amount="2",
        occurred_at="2026-08-01T14:00:00+00:00",
    )

    distributions, unavailable = confirmed_distributions(store)

    assert len(distributions) == 1
    assert distributions[0].ticker == "AAPL"
    assert distributions[0].amount_per_share == 0.25
    assert distributions[0].cash_amount == 5.0
    assert distributions[0].tax_classification == "qualified"
    assert distributions[0].ex_at.tzinfo is not None
    assert unavailable[0]["ticker"] == "KO"
    assert "lacks" in unavailable[0]["reason"]
