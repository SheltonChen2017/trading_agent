"""Tests for assistant/recommended_stocks.py. Run with:
python tests/test_recommended_stocks.py"""
import dataclasses
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant import recommended_stocks, similarity_evidence
from assistant.schemas import EvidenceStatus


def _verified(ticker, **overrides):
    base = {
        "ticker": ticker, "longName": f"{ticker} Inc.", "sector": "", "quoteType": "EQUITY",
        "exchange": "NMS", "history_sessions": 70, "last_price": 100.0,
        "median_dollar_volume": 5_000_000.0, "first_session_date": "2020-01-01",
    }
    base.update(overrides)
    return base


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


def test_fetch_recent_ipos_excludes_non_priced_status(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ipoCalendar": [
            {"symbol": "PRICED", "name": "Priced Co", "date": "2026-07-20", "status": "priced"},
            {"symbol": "EXPECTED", "name": "Expected Co", "date": "2026-08-01", "status": "expected"},
            {"symbol": "FILED", "name": "Filed Co", "date": "2026-08-15", "status": "filed"},
        ]
    }
    mock_response.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_response):
        result = recommended_stocks.fetch_recent_ipos()
    assert [r["ticker"] for r in result] == ["PRICED"]


def test_fetch_recent_ipos_excludes_future_dated_entries(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ipoCalendar": [
            {"symbol": "PAST", "name": "Past Co", "date": "2026-01-01", "status": "priced"},
            {"symbol": "FUTURE", "name": "Future Co", "date": "2099-01-01", "status": "priced"},
        ]
    }
    mock_response.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_response), \
         patch("assistant.recommended_stocks.datetime") as mock_datetime:
        from datetime import datetime, timezone
        mock_datetime.now.return_value = datetime(2026, 7, 28, tzinfo=timezone.utc)
        result = recommended_stocks.fetch_recent_ipos()
    assert [r["ticker"] for r in result] == ["PAST"]


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
        mock_verify.return_value = ([_verified("GOOD", longName="Good Co")], ["BOGUS"])
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
        mock_verify.return_value = ([_verified("AAPL", longName="Apple Inc.")], [])
        recommended, _ = recommended_stocks.build_recommended_tickers()
    for r in recommended:
        assert "most bought" not in r.detail.lower()
        assert "buy signal" not in r.detail.lower()


def test_build_recommended_tickers_excludes_held_tickers_from_most_active_lane(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers") as mock_active, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None) as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers") as mock_verify:
        mock_active.return_value = [{"ticker": "AAPL", "name": "Apple", "volume": 1000}, {"ticker": "MSFT", "name": "Microsoft", "volume": 2000}]
        mock_verify.return_value = ([_verified("MSFT", longName="Microsoft")], [])
        recommended, _ = recommended_stocks.build_recommended_tickers(held_tickers=["AAPL"])
    assert not any(r.ticker == "AAPL" for r in recommended)
    # AAPL must never even reach verify_tickers -- excluded before the network call.
    verified_input = mock_verify.call_args[0][0]
    assert "AAPL" not in verified_input
    mock_suggest.assert_called_once_with(["AAPL"], store=None)


def test_build_recommended_tickers_skips_ai_suggested_lane_when_no_holdings(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest:
        recommended, _ = recommended_stocks.build_recommended_tickers(held_tickers=None)
    mock_suggest.assert_not_called()
    assert not any(r.reason_category == "ai_suggested" for r in recommended)


def test_include_ai_suggestions_false_prevents_the_paid_call_entirely(monkeypatch):
    """The UI's optional-AI master preference must be able to stop the LLM
    call from FIRING, not merely hide its output -- and it must not disturb
    the deterministic lanes or the held-ticker exclusion while doing so
    (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md section 3.2)."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers") as mock_active, \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers") as mock_verify:
        mock_active.return_value = [
            {"ticker": "AAPL", "name": "Apple", "volume": 1000},
            {"ticker": "MSFT", "name": "Microsoft", "volume": 2000},
        ]
        mock_verify.return_value = ([_verified("MSFT", longName="Microsoft")], [])
        recommended, _ = recommended_stocks.build_recommended_tickers(
            held_tickers=["AAPL"], include_ai_suggestions=False
        )
    # The dangerous direction: despite holdings existing (which normally
    # triggers the suggestion call), the LLM helper is never invoked.
    mock_suggest.assert_not_called()
    assert not any(r.reason_category == "ai_suggested" for r in recommended)
    # Deterministic lanes are unaffected: most-active still runs, and the
    # held-ticker exclusion still holds.
    assert any(r.ticker == "MSFT" for r in recommended)
    assert not any(r.ticker == "AAPL" for r in recommended)


def test_disabled_market_sources_do_not_make_network_calls():
    """A source toggle is an execution control for that source, not merely
    a display filter: disabled lanes must not call their providers or add
    failures to the combined dropped count."""
    with patch(
        "assistant.recommended_stocks.fetch_most_active_tickers"
    ) as mock_active, patch(
        "assistant.recommended_stocks.fetch_recent_ipos"
    ) as mock_ipos, patch(
        "assistant.recommended_stocks.verify_tickers"
    ) as mock_verify, patch(
        "assistant.recommended_stocks.suggest_similar_tickers"
    ) as mock_suggest:
        recommended, dropped = recommended_stocks.build_recommended_tickers(
            held_tickers=["AAPL"],
            include_most_active=False,
            include_recent_ipos=False,
            include_ai_suggestions=False,
        )

    mock_active.assert_not_called()
    mock_ipos.assert_not_called()
    mock_suggest.assert_not_called()
    mock_verify.assert_not_called()
    assert recommended == []
    assert dropped == []


_NO_EVIDENCE = similarity_evidence.SimilarityEvidence(
    source_tickers=(), candidate_ticker="", shared_sectors=(), shared_industries=(),
    return_correlation_pct=None, lookback_days=126, data_start=None, data_end=None,
)


def test_build_recommended_tickers_uses_held_tickers_as_similarity_basis(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers", return_value=([_verified("JPM")], [])), \
         patch("assistant.recommended_stocks.compute_similarity_evidence", return_value=_NO_EVIDENCE):
        mock_suggest.return_value = [{"ticker": "JPM", "reason": "Similar bank exposure"}]
        recommended, _ = recommended_stocks.build_recommended_tickers(held_tickers=["BAC", "WFC"])
    mock_suggest.assert_called_once_with(["BAC", "WFC"], store=None)
    assert any(r.ticker == "JPM" and r.reason_category == "ai_suggested" for r in recommended)


def test_build_recommended_tickers_excludes_held_from_ai_suggestions(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers", return_value=([_verified("JPM")], [])), \
         patch("assistant.recommended_stocks.compute_similarity_evidence", return_value=_NO_EVIDENCE):
        mock_suggest.return_value = [{"ticker": "BAC", "reason": "You already hold this"}, {"ticker": "JPM", "reason": "Similar"}]
        recommended, _ = recommended_stocks.build_recommended_tickers(held_tickers=["BAC"])
    assert not any(r.ticker == "BAC" for r in recommended)


def test_build_recommended_tickers_applies_eligibility_to_known_universe_suggestions(monkeypatch):
    # independent review: a suggestion already in config.UNIVERSE used to be appended
    # directly, bypassing verify_tickers() entirely -- universe membership answered
    # "where did this come from," not "is this eligible today." AAPL is a real
    # config.UNIVERSE member; this confirms it still goes through verify_tickers()
    # and is dropped if that check fails.
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["AAPL"]:
            return ([], ["AAPL"])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect) as mock_verify:
        mock_suggest.return_value = [{"ticker": "AAPL", "reason": "Known mega-cap"}]
        recommended, dropped = recommended_stocks.build_recommended_tickers(held_tickers=["NVDA"])
    ai_suggested_call = next(c for c in mock_verify.call_args_list if c.args and c.args[0] == ["AAPL"])
    assert ai_suggested_call is not None
    assert not any(r.ticker == "AAPL" for r in recommended)
    assert "AAPL" in dropped


def test_similarity_detail_pairs_llm_reason_with_measured_evidence(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    evidence = dataclasses.replace(_NO_EVIDENCE, return_correlation_pct=90.0, shared_industries=("NVDA",))

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["AMD"]:
            return ([_verified("AMD")], [])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.suggest_similar_tickers") as mock_suggest, \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect), \
         patch("assistant.recommended_stocks.compute_similarity_evidence", return_value=evidence):
        mock_suggest.return_value = [{"ticker": "AMD", "reason": "A close semiconductor peer"}]
        recommended, _ = recommended_stocks.build_recommended_tickers(held_tickers=["NVDA"])
    amd = next(r for r in recommended if r.ticker == "AMD")
    assert "A close semiconductor peer" in amd.detail
    assert "measured" in amd.detail
    assert "90%" in amd.detail


# --- Lane-specific IPO eligibility (independent review: a genuine IPO from
# the last 30 calendar days has at most ~20 trading sessions, but the
# DEFAULT_ELIGIBILITY_POLICY used everywhere else requires 60 -- every real
# recent IPO was rejected by construction, not just conservatively.)

def test_build_recommended_tickers_ipo_lane_uses_the_lenient_ipo_policy(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    verified_newco = _verified("NEWCO", history_sessions=7, first_session_date="2026-07-21")

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["NEWCO"]:
            return ([verified_newco], [])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.fetch_recent_ipos") as mock_ipos, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect) as mock_verify:
        mock_ipos.return_value = [{"ticker": "NEWCO", "name": "New Co", "date": "2026-07-20", "status": "priced"}]
        recommended, _ = recommended_stocks.build_recommended_tickers()
    # verify_tickers must be called with the lenient IPO policy for this lane, not the default.
    ipo_call = next(c for c in mock_verify.call_args_list if c.args and c.args[0] == ["NEWCO"])
    assert ipo_call.kwargs["policy"] is recommended_stocks.RECENT_IPO_ELIGIBILITY_POLICY
    assert any(r.ticker == "NEWCO" and r.reason_category == "recent_ipo" for r in recommended)


def test_build_recommended_tickers_ipo_detail_discloses_limited_history(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    verified_newco = _verified("NEWCO", history_sessions=7, first_session_date="2026-07-21")

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["NEWCO"]:
            return ([verified_newco], [])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.fetch_recent_ipos") as mock_ipos, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect):
        mock_ipos.return_value = [{"ticker": "NEWCO", "name": "New Co", "date": "2026-07-20", "status": "priced"}]
        recommended, _ = recommended_stocks.build_recommended_tickers()
    newco = next(r for r in recommended if r.ticker == "NEWCO")
    assert "7 completed trading session" in newco.detail
    assert "not yet reliable" in newco.detail


def test_build_recommended_tickers_rejects_ipo_identity_mismatch(monkeypatch):
    # A "recent IPO" whose real first trading bar is nowhere near the
    # claimed IPO date is likely a reused/renamed ticker, not a fresh
    # listing -- independent review's exact scenario.
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    verified_reused = _verified("REUSED", history_sessions=500, first_session_date="2020-01-01")

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["REUSED"]:
            return ([verified_reused], [])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.fetch_recent_ipos") as mock_ipos, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect):
        mock_ipos.return_value = [{"ticker": "REUSED", "name": "Reused Co", "date": "2026-07-20", "status": "priced"}]
        recommended, dropped = recommended_stocks.build_recommended_tickers()
    assert not any(r.ticker == "REUSED" for r in recommended)
    assert "REUSED" in dropped


def test_build_recommended_tickers_accepts_ipo_with_close_date_match(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    # First real trading bar 2 days after the claimed IPO date -- within tolerance.
    verified_newco = _verified("NEWCO", history_sessions=5, first_session_date="2026-07-22")

    def _side_effect(tickers, *args, **kwargs):
        if tickers == ["NEWCO"]:
            return ([verified_newco], [])
        return ([], [])

    with patch("assistant.recommended_stocks.fetch_most_active_tickers", return_value=[]), \
         patch("assistant.recommended_stocks.fetch_recent_ipos") as mock_ipos, \
         patch("assistant.recommended_stocks.suggest_similar_tickers", return_value=None), \
         patch("assistant.recommended_stocks.verify_tickers", side_effect=_side_effect):
        mock_ipos.return_value = [{"ticker": "NEWCO", "name": "New Co", "date": "2026-07-20", "status": "priced"}]
        recommended, dropped = recommended_stocks.build_recommended_tickers()
    assert any(r.ticker == "NEWCO" for r in recommended)
    assert "NEWCO" not in dropped


def test_is_ipo_identity_mismatch_true_for_large_gap():
    assert recommended_stocks._is_ipo_identity_mismatch("2020-01-01", "2026-07-20") is True


def test_is_ipo_identity_mismatch_false_for_close_dates():
    assert recommended_stocks._is_ipo_identity_mismatch("2026-07-22", "2026-07-20") is False


def test_is_ipo_identity_mismatch_false_when_data_missing():
    assert recommended_stocks._is_ipo_identity_mismatch(None, "2026-07-20") is False
    assert recommended_stocks._is_ipo_identity_mismatch("2026-07-20", "") is False


def test_recommended_ticker_never_reuses_signal_evidence_status():
    field_types = {f.name: f.type for f in dataclasses.fields(recommended_stocks.RecommendedTicker)}
    assert "EvidenceStatus" not in str(field_types.values())
    assert EvidenceStatus not in field_types.values()


if __name__ == "__main__":
    test_fetch_most_active_tickers_returns_empty_on_yf_screen_failure()
    test_fetch_most_active_tickers_parses_real_shape()
    test_is_ipo_identity_mismatch_true_for_large_gap()
    test_is_ipo_identity_mismatch_false_for_close_dates()
    test_is_ipo_identity_mismatch_false_when_data_missing()
    test_recommended_ticker_never_reuses_signal_evidence_status()
    print("Run via pytest for the monkeypatch-fixture tests: python -m pytest tests/test_recommended_stocks.py")
