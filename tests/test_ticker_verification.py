"""Tests for assistant/ticker_verification.py. Run with:
python tests/test_ticker_verification.py"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from assistant import ticker_verification
from assistant.ticker_verification import SecurityEligibilityPolicy

_ELIGIBLE_INFO = {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS", "sector": "Technology"}


def _df(rows=70, close=100.0, volume=50_000_000):
    """A history shaped to pass DEFAULT_ELIGIBILITY_POLICY by default:
    70 sessions (>= 60 minimum), $100 close (>= $5 minimum), 50M share
    volume at $100 -> $5B median dollar volume (>= $1M minimum)."""
    return pd.DataFrame(
        {"close": [close] * rows, "volume": [volume] * rows},
        index=pd.bdate_range("2026-01-01", periods=rows),
    )


def test_verify_tickers_keeps_valid_ticker():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["AAPL"])
    assert dropped == []
    assert len(verified) == 1
    assert verified[0]["ticker"] == "AAPL"
    assert verified[0]["longName"] == "Apple Inc."
    assert verified[0]["history_sessions"] == 70
    assert verified[0]["last_price"] == 100.0
    assert verified[0]["median_dollar_volume"] == 100.0 * 50_000_000


def test_verify_tickers_drops_ticker_not_in_fetch_historical_result():
    # The hallucinated/delisted/typo case: fetch_historical simply omits it.
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch:
        mock_fetch.return_value = {}
        verified, dropped = ticker_verification.verify_tickers(["FAKETIX"])
    assert verified == []
    assert dropped == ["FAKETIX"]


def test_verify_tickers_drops_ticker_with_empty_info():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"ZZZZ": _df()}
        mock_info.return_value = {}
        verified, dropped = ticker_verification.verify_tickers(["ZZZZ"])
    assert verified == []
    assert dropped == ["ZZZZ"]


def test_verify_tickers_one_bad_ticker_does_not_abort_batch():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["AAPL", "BOGUS"])
    assert [v["ticker"] for v in verified] == ["AAPL"]
    assert dropped == ["BOGUS"]


def test_verify_tickers_respects_max_checks_cap():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"A": _df(), "B": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["A", "B", "C", "D"], max_checks=2)
    assert mock_fetch.call_args[0][0] == ["A", "B"]
    assert {v["ticker"] for v in verified} == {"A", "B"}
    assert set(dropped) == {"C", "D"}


# --- Eligibility policy: quote type, history length, price, liquidity

def test_verify_tickers_rejects_non_equity_quote_type():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPY": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "quoteType": "ETF"}
        verified, dropped = ticker_verification.verify_tickers(["SPY"])
    assert verified == []
    assert dropped == ["SPY"]


def test_verify_tickers_rejects_short_history():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NEWIPO": _df(rows=10)}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["NEWIPO"])
    assert verified == []
    assert dropped == ["NEWIPO"]


def test_verify_tickers_rejects_price_below_minimum():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"PENNY": _df(close=1.0)}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["PENNY"])
    assert verified == []
    assert dropped == ["PENNY"]


def test_verify_tickers_rejects_illiquid_ticker():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"THIN": _df(close=10.0, volume=100)}  # $1,000 median dollar volume
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["THIN"])
    assert verified == []
    assert dropped == ["THIN"]


def test_verify_tickers_rejects_missing_company_name():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NONAME": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "longName": ""}
        verified, dropped = ticker_verification.verify_tickers(["NONAME"])
    assert verified == []
    assert dropped == ["NONAME"]


def test_verify_tickers_rejects_non_us_exchange():
    # independent review: nothing enforced the "US tickers"/"US stocks"
    # framing already used in prompts/UI copy -- a sufficiently liquid
    # foreign or OTC listing could pass every other check.
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"FOREIGN": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "exchange": "LSE"}
        verified, dropped = ticker_verification.verify_tickers(["FOREIGN"])
    assert verified == []
    assert dropped == ["FOREIGN"]


def test_verify_tickers_allowed_exchanges_none_disables_the_check():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"FOREIGN": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "exchange": "LSE"}
        no_exchange_restriction = SecurityEligibilityPolicy(allowed_exchanges=None)
        verified, dropped = ticker_verification.verify_tickers(["FOREIGN"], policy=no_exchange_restriction)
    assert dropped == []
    assert len(verified) == 1


def test_verify_tickers_custom_policy_can_relax_defaults():
    lenient_policy = SecurityEligibilityPolicy(
        allowed_quote_types=("EQUITY", "ETF"), minimum_history_sessions=5,
        minimum_price=0.0, minimum_median_dollar_volume=0.0, require_company_name=False,
    )
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPY": _df(rows=5, close=1.0, volume=1)}
        mock_info.return_value = {"quoteType": "ETF", "exchange": "PCX", "longName": ""}
        verified, dropped = ticker_verification.verify_tickers(["SPY"], policy=lenient_policy)
    assert dropped == []
    assert len(verified) == 1


def test_partition_by_universe_splits_correctly():
    candidates = [{"ticker": "AAPL", "reason": "r1"}, {"ticker": "ZZZFAKE", "reason": "r2"}]
    from_universe, wildcard = ticker_verification.partition_by_universe(candidates, universe=["AAPL", "MSFT"])
    assert from_universe == [{"ticker": "AAPL", "reason": "r1"}]
    assert wildcard == [{"ticker": "ZZZFAKE", "reason": "r2"}]


def test_partition_by_universe_is_case_insensitive():
    candidates = [{"ticker": "aapl", "reason": "r1"}]
    from_universe, wildcard = ticker_verification.partition_by_universe(candidates, universe=["AAPL"])
    assert from_universe == [{"ticker": "aapl", "reason": "r1"}]
    assert wildcard == []


if __name__ == "__main__":
    test_verify_tickers_keeps_valid_ticker()
    test_verify_tickers_drops_ticker_not_in_fetch_historical_result()
    test_verify_tickers_drops_ticker_with_empty_info()
    test_verify_tickers_one_bad_ticker_does_not_abort_batch()
    test_verify_tickers_respects_max_checks_cap()
    test_verify_tickers_rejects_non_equity_quote_type()
    test_verify_tickers_rejects_short_history()
    test_verify_tickers_rejects_price_below_minimum()
    test_verify_tickers_rejects_illiquid_ticker()
    test_verify_tickers_rejects_missing_company_name()
    test_verify_tickers_rejects_non_us_exchange()
    test_verify_tickers_allowed_exchanges_none_disables_the_check()
    test_verify_tickers_custom_policy_can_relax_defaults()
    test_partition_by_universe_splits_correctly()
    test_partition_by_universe_is_case_insensitive()
    print("All ticker_verification tests passed.")
