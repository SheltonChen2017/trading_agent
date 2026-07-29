"""Tests for assistant/ticker_verification.py. Run with:
python tests/test_ticker_verification.py"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from assistant import ticker_verification


def _df(rows=5):
    return pd.DataFrame({"close": [1.0] * rows}, index=pd.bdate_range("2026-01-01", periods=rows))


def test_verify_tickers_keeps_valid_ticker():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS"}
        verified, dropped = ticker_verification.verify_tickers(["AAPL"])
    assert dropped == []
    assert len(verified) == 1
    assert verified[0]["ticker"] == "AAPL"
    assert verified[0]["longName"] == "Apple Inc."


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
        mock_info.return_value = {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS"}
        verified, dropped = ticker_verification.verify_tickers(["AAPL", "BOGUS"])
    assert [v["ticker"] for v in verified] == ["AAPL"]
    assert dropped == ["BOGUS"]


def test_verify_tickers_respects_max_checks_cap():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"A": _df(), "B": _df()}
        mock_info.return_value = {"longName": "X", "quoteType": "EQUITY", "exchange": "NMS"}
        verified, dropped = ticker_verification.verify_tickers(["A", "B", "C", "D"], max_checks=2)
    assert mock_fetch.call_args[0][0] == ["A", "B"]
    assert {v["ticker"] for v in verified} == {"A", "B"}
    assert set(dropped) == {"C", "D"}


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
    test_partition_by_universe_splits_correctly()
    test_partition_by_universe_is_case_insensitive()
    print("All ticker_verification tests passed.")
