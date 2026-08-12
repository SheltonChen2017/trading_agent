"""Behavioral coverage for the Ticker Suggestions price-direction view."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.recommended_stocks import RecommendedTicker


_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline_suggestions_environment(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(
        data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {}
    )
    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def test_direction_view_renders_every_bucket_and_discloses_cached_data_time(
    _offline_suggestions_environment,
):
    fetched_at = "2026-08-11T16:00:00+00:00"
    rows = [
        RecommendedTicker("UP", "most_active", "Up detail", fetched_at, "advancing"),
        RecommendedTicker("DOWN", "most_active", "Down detail", fetched_at, "declining"),
        RecommendedTicker("FLAT", "most_active", "Flat detail", fetched_at, "unchanged"),
        RecommendedTicker("UNKNOWN", "most_active", "Unknown detail", fetched_at, None),
    ]
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Ticker Suggestions"
    app.session_state["ticker_suggestions_result"] = {
        "rows": rows,
        "dropped": [],
        "ran_at": "2026-08-11T16:14:00+00:00",
        "sources": {
            "most_active": True,
            "recent_ipo": False,
            "ai_suggested": False,
        },
    }
    app.run()

    assert not app.exception
    ticker_columns = [
        set(frame.value["Ticker"])
        for frame in app.dataframe
        if hasattr(frame.value, "columns") and "Ticker" in frame.value.columns
    ]
    assert {"UP"} in ticker_columns
    assert {"DOWN"} in ticker_columns

    captions = "\n".join(element.value for element in app.caption)
    assert "FLAT" in captions and "closed exactly flat" in captions
    assert "UNKNOWN" in captions and "reported no usable price change" in captions
    assert fetched_at in captions
    assert "cached for up to 15 minutes" in captions


def test_dropped_candidates_are_named_not_just_counted(
    _offline_suggestions_environment,
):
    """A bare count could not distinguish "we filtered out junk" from "we
    filtered out the day's second most-traded stock" -- which is exactly how
    the SPCX omission stayed invisible until the owner diffed this list
    against yfinance by hand on 2026-08-12."""
    fetched_at = "2026-08-12T16:00:00+00:00"
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Ticker Suggestions"
    app.session_state["ticker_suggestions_result"] = {
        "rows": [RecommendedTicker("UP", "most_active", "Up detail", fetched_at, "advancing")],
        "dropped": ["BOGUS", "FGN"],
        "ran_at": "2026-08-12T16:14:00+00:00",
        "sources": {"most_active": True, "recent_ipo": False, "ai_suggested": False},
    }
    app.run()

    assert not app.exception
    captions = "\n".join(element.value for element in app.caption)
    assert "BOGUS" in captions and "FGN" in captions
    # And the caption must say what screening does and does not do now.
    assert "NOT screened on size, age, price, or liquidity" in captions


def test_no_dropped_candidates_produces_no_omission_sentence(
    _offline_suggestions_environment,
):
    fetched_at = "2026-08-12T16:00:00+00:00"
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Ticker Suggestions"
    app.session_state["ticker_suggestions_result"] = {
        "rows": [RecommendedTicker("UP", "most_active", "Up detail", fetched_at, "advancing")],
        "dropped": [],
        "ran_at": "2026-08-12T16:14:00+00:00",
        "sources": {"most_active": True, "recent_ipo": False, "ai_suggested": False},
    }
    app.run()

    assert not app.exception
    captions = "\n".join(element.value for element in app.caption)
    assert "could not be identified" not in captions


def test_briefing_always_discloses_the_relaxed_suggestion_screen(
    _offline_suggestions_environment, monkeypatch
):
    """Briefing consumes the same relaxed policy and must name that fact even
    when every candidate verifies and therefore no omission caption appears.
    """
    import assistant.recommended_stocks as recommended_stocks

    monkeypatch.setattr(recommended_stocks, "fetch_most_active_tickers", lambda: [])
    monkeypatch.setattr(recommended_stocks, "fetch_recent_ipos", lambda: [])
    monkeypatch.setattr(recommended_stocks, "suggest_similar_tickers", lambda *a, **k: None)

    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Briefing"
    app.run()

    assert not app.exception
    captions = "\n".join(element.value for element in app.caption)
    assert "NOT screened on size, age, price, or liquidity" in captions
