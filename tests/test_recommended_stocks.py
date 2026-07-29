"""Tests for assistant/recommended_stocks.py. Run with:
python tests/test_recommended_stocks.py"""
import dataclasses
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant import recommended_stocks
from assistant.schemas import EvidenceStatus


def test_fetch_most_active_tickers_returns_empty_on_yf_screen_failure():
    with patch("yfinance.screen", side_effect=Exception("network error")):
        assert recommended_stocks.fetch_most_active_tickers() == []


def test_fetch_most_active_tickers_parses_real_shape():
    fake_result = {
        "quotes": [
            {"symbol": "INTC", "regularMarketVolume": 148828659, "shortName": "Intel Corporation"},
            {"symbol": "NVDA", "regularMarketVolume": 125138253, "shortName": "NVIDIA Corporation"},
        ]
    }
    with patch("yfinance.screen", return_value=fake_result):
        result = recommended_stocks.fetch_most_active_tickers(count=2)
    assert result == [
        {"ticker": "INTC", "name": "Intel Corporation", "volume": 148828659},
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "volume": 125138253},
    ]


def test_fetch_recent_ipos_returns_empty_when_finnhub_key_unset(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("requests.get") as mock_get:
        result = recommended_stocks.fetch_recent_ipos()
    assert result == []
    mock_get.assert_not_called()


def test_fetch_recent_ipos_returns_empty_on_request_failure(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    with patch("requests.get", side_effect=Exception("network error")):
        result = recommended_stocks.fetch_recent_ipos()
    assert result == []


def test_fetch_recent_ipos_returns_empty_on_malformed_response(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"unexpected": "shape"}
    mock_response.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_response):
        result = recommended_stocks.fetch_recent_ipos()
    assert result == []


def test_fetch_recent_ipos_parses_real_shape(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ipoCalendar": [{"symbol": "NEWCO", "name": "New Company Inc", "date": "2026-07-20", "status": "priced"}]
    }
    mock_response.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_response):
        result = recommended_stocks.fetch_recent_ipos()
    assert result == [{"ticker": "NEWCO", "name": "New Company Inc", "date": "2026-07-20", "status": "priced"}]


def test_is_ipo_calendar_configured(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    assert recommended_stocks.is_ipo_calendar_configured() is False
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    assert recommended_stocks.is_ipo_calendar_configured() is True


def test_build_recommended_tickers_drops_unverified_candidates(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers") as mock_active, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers") as mock_verify:
        mock_active.return_value = [{"ticker": "GOOD", "name": "Good Co", "volume": 1000}, {"ticker": "BOGUS", "name": "", "volume": None}]
        mock_verify.return_value = ([{"ticker": "GOOD", "longName": "Good Co", "sector": "", "quoteType": "EQUITY", "exchange": "NMS"}], ["BOGUS"])
        recommended, dropped = recommended_stocks.build_recommended_tickers()
    assert any(r.ticker == "GOOD" for r in recommended)
    assert not any(r.ticker == "BOGUS" for r in recommended)
    assert "BOGUS" in dropped


def test_build_recommended_tickers_labels_are_honest(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers") as mock_active, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers") as mock_verify:
        mock_active.return_value = [{"ticker": "AAPL", "name": "Apple", "volume": 5000}]
        mock_verify.return_value = ([{"ticker": "AAPL", "longName": "Apple Inc.", "sector": "", "quoteType": "EQUITY", "exchange": "NMS"}], [])
        recommended, _ = recommended_stocks.build_recommended_tickers()
    for r in recommended:
        assert "most bought" not in r.detail.lower()
        assert "buy signal" not in r.detail.lower()


def test_recommended_ticker_never_reuses_signal_evidence_status():
    field_types = {f.name: f.type for f in dataclasses.fields(recommended_stocks.RecommendedTicker)}
    assert "EvidenceStatus" not in str(field_types.values())
    assert EvidenceStatus not in field_types.values()


if __name__ == "__main__":
    test_fetch_most_active_tickers_returns_empty_on_yf_screen_failure()
    test_fetch_most_active_tickers_parses_real_shape()
    test_recommended_ticker_never_reuses_signal_evidence_status()
    print("Run via pytest for the monkeypatch-fixture tests: python -m pytest tests/test_recommended_stocks.py")
