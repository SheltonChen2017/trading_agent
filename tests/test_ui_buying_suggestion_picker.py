"""Buying page: pick a most-active suggestion straight into the cart.

Owner request 2026-08-13 — a third cart source alongside "pick from common
tickers" and "type any other ticker".

This moves a DISCLOSURE surface into a buying flow, so the tests pin the
properties that keep that honest:

* no network call on page load (the screen runs only on an explicit click);
* each row's AP-8 eligibility disclosure travels with its own Add button and
  is named again in the cart, because once a ticker is a bare symbol in a
  list it is indistinguishable from one the owner picked deliberately;
* cached source time stays distinct from the time the result was displayed;
* changing the cart hides analysis and proposal controls computed for the
  previous cart.

Plus the mechanical one that a draft got wrong: the Buying page has no
module-level `packet` (that name belongs to the Briefing block), so the
handler must load its own.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.recommended_stocks import RecommendedTicker

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
_FETCHED_AT = "2026-08-13T16:00:00+00:00"


def _rows():
    return [
        RecommendedTicker(
            "UPUP", "most_active",
            "Up Co -- trading volume today: 1,000,000 -- price change today: +3.00% "
            "-- only 41 completed trading session(s) -- below this project's usual "
            "60-session floor, so volatility and trend estimates are not yet reliable",
            _FETCHED_AT, "advancing",
        ),
        RecommendedTicker(
            "DNDN", "most_active",
            "Down Co -- trading volume today: 900,000 -- price change today: -2.00%",
            _FETCHED_AT, "declining",
        ),
        RecommendedTicker(
            "FLAT", "most_active",
            "Flat Co -- trading volume today: 10 -- price change today: +0.00%",
            _FETCHED_AT, "unchanged",
        ),
        RecommendedTicker(
            "UNKNOWN", "most_active",
            "Unknown Co -- trading volume today: 20 -- price change today: not reported",
            _FETCHED_AT, None,
        ),
    ]


@pytest.fixture()
def _offline(monkeypatch):
    # The suggestions loader is @st.cache_data-wrapped and that cache lives in
    # the PROCESS, not the AppTest. Without clearing it, the first test's
    # successful result is served to every later test and the provider patch
    # below is never reached -- which silently turned the provider-failure
    # test into an assertion about cached success. Clear before each test so
    # each one exercises the seam it claims to.
    import streamlit as st

    st.cache_data.clear()

    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})

    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )

    # The provider seam. Counting calls is the point: it must stay at zero
    # until the button is clicked.
    calls = {"n": 0}
    import assistant.recommended_stocks as recommended_stocks

    def _fake_build(*_a, **_k):
        calls["n"] += 1
        return _rows(), ["BOGUS"]

    monkeypatch.setattr(recommended_stocks, "build_recommended_tickers", _fake_build)
    return calls


def _buying_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Buying"
    app.run()
    return app


def _button(app, startswith):
    return next(b for b in app.button if b.label.startswith(startswith))


def _checked_result_row() -> dict:
    return {
        "own_trend": "flat",
        "own_vol": 2.0,
        "current_price": 100.0,
        "price_as_of": "2026-08-13",
        "price_history": None,
        "explanation": {
            "currently_held": None,
            "triggered_today": False,
            "historical_evidence": [],
            "note": "",
        },
        "price_targets": [],
        "hold_range": None,
        "news": [],
        "news_summary": None,
        "news_summary_reason": None,
        "earnings": {"available": False},
    }


def test_the_picker_exists_and_runs_no_network_call_on_page_load(_offline):
    app = _buying_app()

    assert not app.exception
    labels = [e.label for e in app.expander]
    assert any("pick from ticker suggestions" in label for label in labels), labels
    assert _offline["n"] == 0, (
        "the market screen must not run on page load -- only on an explicit click"
    )


def test_clicking_show_loads_rows_and_splits_them_by_direction(_offline):
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()

    assert not app.exception
    assert _offline["n"] == 1, "exactly one provider call, on the click"
    markdown = " ".join(m.value for m in app.markdown)
    assert "Most active — price up today" in markdown
    assert "Most active — price down today" in markdown
    # A flat mover belongs to neither column and must be named, not dropped.
    captions = "\n".join(c.value for c in app.caption)
    assert "FLAT" in captions
    # Unverifiable candidates are named rather than silently omitted.
    assert "BOGUS" in captions


def test_every_verified_row_is_clickable_including_flat_candidates(_offline):
    """BUY-1 promises one Add control per verified most-active row.

    A flat price move is still a verified most-active candidate.  Direction
    only decides where it is displayed; it must not silently decide whether
    the owner may put the ticker in the research cart.
    """
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()

    flat_add = _button(app, "Add FLAT")
    _button(app, "Add UNKNOWN")
    captions = "\n".join(c.value for c in app.caption)
    assert "Flat Co -- trading volume today: 10" in captions
    assert "Unknown Co -- trading volume today: 20" in captions

    flat_add.click()
    app.run()

    assert not app.exception
    assert app.session_state["watchlist_from_suggestions"] == ["FLAT"]
    assert any("**Cart:** FLAT" in m.value for m in app.markdown)


def test_picker_distinguishes_source_fetch_time_from_display_time(_offline):
    """The cached loader's row time, not the button click, is data freshness."""
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()

    captions = "\n".join(c.value for c in app.caption)
    assert f"Source data fetched at {_FETCHED_AT}" in captions
    assert "Displayed at" in captions
    assert "cached for up to 15 minutes" in captions


def test_adding_a_suggestion_hides_results_checked_for_the_old_cart(_offline):
    """A newly added ticker must not sit above analysis/proposals for an old cart."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Buying"
    app.session_state["watchlist_typed"] = "NVDA"
    app.session_state["watchlist_results"] = {"NVDA": _checked_result_row()}
    app.session_state["watchlist_results_cart"] = ["NVDA"]
    app.run()
    assert "NVDA" in [s.value for s in app.subheader]

    _button(app, "Show most-active suggestions").click()
    app.run()
    _button(app, "Add UPUP").click()
    app.run()

    assert not app.exception
    warnings = "\n".join(w.value for w in app.warning)
    assert "cart changed since you checked it" in warnings
    assert app.session_state["watchlist_results"] == {}
    assert "NVDA" not in [s.value for s in app.subheader]
    assert "Create purchase proposals using this split" not in [
        s.value for s in app.subheader
    ]


def test_adding_a_suggestion_puts_it_in_the_cart(_offline):
    """The whole point of the feature: click a ticker, it joins the cart the
    same way a typed or multiselected one does."""
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()
    _button(app, "Add UPUP").click()
    app.run()

    assert not app.exception
    assert app.session_state["watchlist_from_suggestions"] == ["UPUP"]
    assert any("**Cart:** UPUP" in m.value for m in app.markdown), (
        [m.value for m in app.markdown]
    )


def test_the_cart_names_where_a_suggestion_came_from_and_its_missing_screens(
    _offline,
):
    """AP-8's disclosures exist because these names are NOT screened on size,
    age, price, or liquidity. A bare symbol in a cart hides that."""
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()
    _button(app, "Add UPUP").click()
    app.run()

    captions = "\n".join(c.value for c in app.caption)
    assert "From the most-active screen: UPUP" in captions
    assert "not filtered on size, age, price, or liquidity" in captions
    # And the row's own disclosure must have been rendered beside its button.
    assert "below this project's usual" in captions


def test_a_ticker_already_in_the_cart_cannot_be_added_twice(_offline):
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()
    _button(app, "Add UPUP").click()
    app.run()

    assert not app.exception
    already = _button(app, "UPUP in cart")
    assert already.disabled
    assert app.session_state["watchlist_from_suggestions"] == ["UPUP"]


def test_clearing_removes_only_the_suggestion_picks(_offline):
    app = _buying_app()
    app.session_state["watchlist_typed"] = "MSFT"
    _button(app, "Show most-active suggestions").click()
    app.run()
    _button(app, "Add DNDN").click()
    app.run()
    assert any("DNDN" in m.value for m in app.markdown if "Cart:" in m.value)

    _button(app, "Clear suggestion picks").click()
    app.run()

    assert not app.exception
    assert app.session_state["watchlist_from_suggestions"] == []
    cart_line = next(m.value for m in app.markdown if "**Cart:**" in m.value)
    assert "DNDN" not in cart_line
    assert "MSFT" in cart_line, "clearing suggestions must not clear typed tickers"


def test_a_provider_failure_states_itself_and_adds_nothing(_offline, monkeypatch):
    """A screen outage must not look like an empty market."""
    import assistant.recommended_stocks as recommended_stocks

    def _boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(recommended_stocks, "build_recommended_tickers", _boom)
    app = _buying_app()
    _button(app, "Show most-active suggestions").click()
    app.run()

    assert not app.exception, "the page must survive a provider failure"
    errors = "\n".join(e.value for e in app.error)
    assert "Could not load suggestions" in errors
    assert "Nothing was added to your cart" in errors
    # AppTest's session_state routes attribute access to key lookup, so it has
    # no .get(); read it the way the other tests do.
    try:
        picks = app.session_state["watchlist_from_suggestions"]
    except KeyError:
        picks = []
    assert not picks
