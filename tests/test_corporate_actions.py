from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from assistant.corporate_actions import confirmed_distributions, confirmed_splits
from assistant.portfolio_ledger import (
    ACCOUNT_DIVIDEND_INCOME,
    SECURITY_ACCOUNT_PREFIX,
)
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


class _PostingStore:
    """Minimal store exposing only what these readers consume.

    Deliberately NOT built through record_dividend()/record_split(): those
    writers emit canonical decimal text, so they cannot produce the input
    this test is about. The malformed row stands in for a hand-edited
    journal, a future importer, or storage corruption -- exactly the cases
    the module's docstring promises to report rather than crash on.
    """

    def __init__(self, postings):
        self._postings = postings

    def list_journal_postings(self):
        return self._postings


def _dividend_posting(*, amount_per_share="0.25", amount="-5.00"):
    return {
        "transaction_id": "txn-div",
        "source": "corporate_action",
        "account": ACCOUNT_DIVIDEND_INCOME,
        "external_id": "dividend:aapl-1",
        "amount": amount,
        "occurred_at": "2026-08-01T14:00:00+00:00",
        "metadata": {
            "ticker": "AAPL",
            "ex_date": "2026-07-10",
            "amount_per_share": amount_per_share,
        },
    }


def _split_posting(metadata):
    return {
        "transaction_id": "txn-split",
        "source": "corporate_action",
        "account": f"{SECURITY_ACCOUNT_PREFIX}AAPL",
        "external_id": "split:aapl-1",
        "occurred_at": "2026-08-01T14:00:00+00:00",
        "metadata": metadata,
    }


@pytest.mark.parametrize(
    "posting",
    [
        _dividend_posting(amount_per_share="N/A"),
        _dividend_posting(amount="not-a-number"),
        # NaN and Infinity are LEGAL Decimal literals, so they survive the
        # conversion; to_decimal rejects them for non-finiteness instead.
        _dividend_posting(amount_per_share="NaN"),
        _dividend_posting(amount_per_share="Infinity"),
    ],
    ids=["bad_per_share", "bad_gross_amount", "nan_per_share", "inf_per_share"],
)
def test_malformed_dividend_decimals_are_reported_unavailable_not_raised(posting):
    """`Decimal(str(x))` raises decimal.InvalidOperation on malformed text.

    InvalidOperation is an ArithmeticError, NOT a ValueError, so it slipped
    straight through this function's `except (ValueError, KeyError)` and
    surfaced as an uncaught traceback in the Streamlit and CLI callers of
    tax_ledger_with_coverage(). assistant.money.to_decimal exists to
    normalize exactly that.
    """
    distributions, unavailable = confirmed_distributions(_PostingStore([posting]))

    assert distributions == []
    assert len(unavailable) == 1
    assert unavailable[0]["ticker"] == "AAPL"
    assert "invalid confirmed dividend metadata" in unavailable[0]["reason"]


def test_empty_amount_per_share_is_caught_by_the_missing_field_guard():
    """Not the same path: an empty string is falsy, so it never reaches the
    decimal conversion. Pinned so the two reasons stay distinguishable."""
    distributions, unavailable = confirmed_distributions(
        _PostingStore([_dividend_posting(amount_per_share="")])
    )
    assert distributions == []
    assert "lacks ex_date or amount_per_share" in unavailable[0]["reason"]


def test_valid_dividend_posting_still_converts():
    """Guards against 'fixing' the above by rejecting everything."""
    distributions, unavailable = confirmed_distributions(
        _PostingStore([_dividend_posting()])
    )
    assert unavailable == []
    assert [d.amount_per_share for d in distributions] == [0.25]


@pytest.mark.parametrize(
    "metadata",
    [
        {"corporate_action": "split", "ratio": "four-for-one"},
        {"corporate_action": "split"},
    ],
    ids=["malformed_ratio", "missing_ratio"],
)
def test_unreadable_split_ratio_fails_closed_as_valueerror(metadata):
    """A split whose ratio cannot be read must NOT be silently skipped --
    dropping it would leave every later share count and cost basis wrong.

    Raising is the fail-closed direction: tax_ledger_with_coverage()
    catches ValueError and reports the ledger incomplete. The bug was that
    a malformed (as opposed to missing) ratio raised InvalidOperation,
    which that caller does not catch.
    """
    with pytest.raises(ValueError):
        confirmed_splits(_PostingStore([_split_posting(metadata)]))


def test_valid_split_posting_still_converts():
    splits = confirmed_splits(
        _PostingStore([_split_posting({"corporate_action": "split", "ratio": "4"})])
    )
    assert [s.ratio for s in splits] == [4.0]


def test_malformed_broker_shares_degrade_coverage_instead_of_traceback(monkeypatch):
    """Residual FPS-001 class: coverage share math used raw Decimal(str(...)).

    InvalidOperation is not a ValueError, so a corrupt portfolio.shares value
    escaped tax_ledger_with_coverage and would traceback in Reports/CLI.
    """
    from assistant import corporate_actions as ca

    class _Ledger:
        open_lots = [SimpleNamespace(ticker="AAPL")]

        def shares_held(self, ticker: str) -> float:
            return 10.0

    monkeypatch.setattr(ca, "fills_with_confirmed_splits", lambda store: [])
    monkeypatch.setattr(ca, "build_ledger", lambda fills: _Ledger())
    portfolio = SimpleNamespace(
        positions=[SimpleNamespace(ticker="AAPL", shares="not-a-number")]
    )

    ledger, coverage = ca.tax_ledger_with_coverage(object(), portfolio)

    assert ledger is None
    assert coverage["complete"] is False
    assert "broker shares" in coverage["reason"]


def test_share_mismatch_detection_rejects_non_finite_and_malformed_input():
    """CFPS-001. Raw `Decimal(str(x))` accepts the literals "NaN" and
    "Infinity", and -- unlike float -- ORDERING COMPARISONS ON A DECIMAL NaN
    RAISE InvalidOperation rather than returning False. So the `recorded <= 0`
    guard inside this helper is not the safe check it appears to be, and an
    ArithmeticError is not catchable as ValueError by callers.

    The one live caller (execution validation) passes validated Decimals
    inside a try/except, so this is defense in depth -- but the signature
    accepts `str`, and the helper is re-exported for presentation, which is
    exactly the surface where the same class was a real traceback (GFPS-001).
    """
    from decimal import Decimal, InvalidOperation

    import pytest

    from assistant.share_reconciliation import detect_split_like_share_mismatch

    # The trap this guards, stated as an executable fact.
    with pytest.raises(InvalidOperation):
        _ = Decimal("NaN") <= 0
    assert (float("nan") <= 0) is False

    for bad in ("not-a-number", float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            detect_split_like_share_mismatch(bad, 100)
        with pytest.raises(ValueError):
            detect_split_like_share_mismatch(100, bad)


def test_share_mismatch_detection_still_classifies_a_real_split():
    """Guards against 'fixing' the above by rejecting everything."""
    from assistant.share_reconciliation import detect_split_like_share_mismatch

    assert detect_split_like_share_mismatch(100, 400) == {
        "ratio": "4:1",
        "direction": "forward",
        "recorded_shares": "100",
        "broker_shares": "400",
    }
    assert detect_split_like_share_mismatch(100, 101) is None


def test_share_match_tolerance_has_a_single_definition():
    """CFPS-002. The same broker-vs-ledger share tolerance was written three
    times: SHARE_TOLERANCE in portfolio_ledger (which PUBLISHES it into the
    durable reconciliation record as "tolerances.shares"), plus bare literals
    in corporate_actions and tax_reporting. Tuning the constant -- e.g. for
    fractional shares -- would have moved ledger reconciliation while leaving
    both tax surfaces on the old value.

    Source-level because the invariant is "there is exactly one definition",
    which no runtime call can observe.
    """
    import re
    from pathlib import Path

    from assistant.portfolio_ledger import SHARE_TOLERANCE

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for module in ("assistant/corporate_actions.py", "assistant/tax_reporting.py"):
        source = (root / module).read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            if re.search(r'Decimal\(\s*["\']0\.0{5,}1["\']\s*\)', line):
                offenders.append(f"{module}:{number}: {line.strip()}")

    assert not offenders, (
        "share tolerance must come from portfolio_ledger.SHARE_TOLERANCE, not "
        f"a local literal: {offenders}"
    )
    assert str(SHARE_TOLERANCE) == "1E-8"
