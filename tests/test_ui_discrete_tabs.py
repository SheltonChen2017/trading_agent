"""Discrete Buying and Discrete Selling (owner request 2026-08-14).

Four pages now exist where two did: budget-driven buying, policy-driven
selling, and these two owner-directed single-name pages. The risks the tests
pin:

* the renamed pages must still be reachable and must not have swapped
  meanings -- "Policy Based Selling" must no longer host the owner-directed
  sell, which moved here;
* a dollar amount is a BUDGET floored to whole shares, and the leftover must
  be stated rather than silently absorbed; and
* neither page may propose more shares than the owner can sell, or a
  proposal that does not match the currently displayed inputs (the AP-9 /
  SELL-1 stale-card rule).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.recommended_stocks import RecommendedTicker

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline(monkeypatch):
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


def _page(name: str) -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = name
    app.run()
    return app


# --- the renames -----------------------------------------------------------


def test_all_four_trading_pages_exist_under_their_new_names(_offline):
    app = _page("Briefing")
    assert not app.exception
    labels = app.radio(key="nav_page").options
    for name in (
        "Budgeted Buying",
        "Discrete Buying",
        "Policy Based Selling",
        "Discrete Selling",
    ):
        assert name in labels, labels
    assert "Buying" not in labels and "Selling" not in labels


@pytest.mark.parametrize(
    ("legacy_name", "new_name"),
    (("Buying", "Budgeted Buying"), ("Selling", "Policy Based Selling")),
)
def test_an_open_session_on_a_renamed_page_is_migrated(
    _offline, legacy_name, new_name
):
    """A deploy must not strand an already-open browser session on a value
    that is no longer one of the radio options."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = legacy_name
    app.run()

    assert not app.exception
    assert app.radio(key="nav_page").value == new_name


def test_policy_based_selling_no_longer_hosts_the_owner_directed_sell(_offline):
    """It moved to Discrete Selling. Two paths to one action is where the
    stale-state bugs live, so exactly one must exist."""
    app = _page("Policy Based Selling")
    assert not app.exception
    subheaders = [s.value for s in app.subheader]
    assert "Sell a specific holding (your own decision)" not in subheaders
    assert "Recommended sells (policy-breach based)" in subheaders


# --- discrete buying -------------------------------------------------------


def test_discrete_buying_asks_for_a_ticker_and_disclaims_recommendation(_offline):
    app = _page("Discrete Buying")
    assert not app.exception
    captions = "\n".join(c.value for c in app.caption)
    assert "NOT recommending" in captions
    assert "zero signals as real edge" in captions
    assert any(
        i.label.startswith("Ticker to buy") for i in app.text_input
    ), [i.label for i in app.text_input]
    # The suggestion picker is present but must not have run any network call.
    assert any("pick from ticker suggestions" in e.label for e in app.expander)


def test_clicking_a_discrete_suggestion_safely_fills_the_ticker(
    _offline, monkeypatch
):
    """Streamlit forbids changing a widget key after that widget has been
    instantiated in the same run. The picker must update through a callback,
    before the rerun builds the ticker input."""
    import assistant.recommended_stocks as recommended_stocks

    row = RecommendedTicker(
        "NVDA",
        "most_active",
        "NVIDIA -- trading volume today: 1,000,000",
        "2026-08-14T16:00:00+00:00",
        "advancing",
    )
    calls = {"count": 0}

    def _fake_build(*_args, **_kwargs):
        calls["count"] += 1
        return [row], ["BOGUS"]

    monkeypatch.setattr(
        recommended_stocks,
        "build_recommended_tickers",
        _fake_build,
    )
    app = _page("Discrete Buying")
    assert calls["count"] == 0
    app.button(key="discrete_buy_suggestions_run").click().run()
    assert calls["count"] == 1
    captions = "\n".join(c.value for c in app.caption)
    assert "Source data fetched at 2026-08-14T16:00:00+00:00" in captions
    assert "cached for up to 15 minutes" in captions
    assert "BOGUS" in captions and "could not be verified" in captions
    app.button(key="discrete_buy_pick_NVDA").click().run()

    assert not app.exception
    assert app.text_input(key="discrete_buy_ticker").value == "NVDA"


def test_discrete_buying_prices_the_ticker_and_offers_both_sizing_modes(
    _offline, monkeypatch
):
    from decimal import Decimal

    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _s, **_k: (lambda _t: {"NVDA": Decimal("100")}),
    )
    app = _page("Discrete Buying")
    app.text_input(key="discrete_buy_ticker").set_value("NVDA").run()

    assert not app.exception
    modes = [
        r
        for r in app.segmented_control
        if r.label.startswith("Size this trade by")
    ]
    assert modes, [r.label for r in app.segmented_control]
    assert set(modes[0].options) == {"Share count", "Dollar amount"}


def test_a_dollar_budget_states_the_unspent_remainder(_offline, monkeypatch):
    """$250 at $100 buys 2 shares and leaves $50. Hiding that would make a
    budget look fully spent."""
    from decimal import Decimal

    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _s, **_k: (lambda _t: {"NVDA": Decimal("100")}),
    )
    app = _page("Discrete Buying")
    app.text_input(key="discrete_buy_ticker").set_value("NVDA").run()
    app.segmented_control(key="discrete_buy_mode").set_value("Dollar amount").run()
    app.number_input(key="discrete_buy_dollars").set_value(250.0).run()

    assert not app.exception
    markdown = " ".join(m.value for m in app.markdown)
    assert "2 whole share(s)" in markdown
    assert "$50.00 is left over" in markdown
    assert "budget, not a" in markdown


def test_an_unpriceable_ticker_refuses_instead_of_guessing(_offline, monkeypatch):
    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        sleeve_notifications, "_recorded_close_fetcher", lambda _s, **_k: (lambda _t: {})
    )
    app = _page("Discrete Buying")
    app.text_input(key="discrete_buy_ticker").set_value("ZZZZ").run()

    assert not app.exception
    errors = "\n".join(e.value for e in app.error)
    assert "No fresh recorded close" in errors
    assert "Nothing was proposed" in errors


def test_a_zero_dollar_input_hides_a_stored_buy_card(_offline, monkeypatch):
    """A stored proposal cannot remain actionable when the current controls
    no longer express any valid trade size."""
    from decimal import Decimal

    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _s, **_k: (lambda _t: {"NVDA": Decimal("100")}),
    )
    app = _page("Discrete Buying")
    app.text_input(key="discrete_buy_ticker").set_value("NVDA").run()
    app.button(key="discrete_buy_create").click().run()
    assert "BUY 1 NVDA" in [s.value for s in app.subheader]

    app.segmented_control(key="discrete_buy_mode").set_value("Dollar amount").run()

    assert "BUY 1 NVDA" not in [s.value for s in app.subheader]
    notices = "\n".join(i.value for i in app.info)
    assert "does not match the current selection" in notices


# --- discrete selling ------------------------------------------------------


def test_discrete_selling_lists_holdings_and_offers_both_modes(_offline):
    app = _page("Discrete Selling")
    assert not app.exception
    # Either there are holdings (a selectbox) or an explicit empty statement.
    if app.selectbox:
        assert any(s.label.startswith("Holding to sell") for s in app.selectbox)
        modes = [
            r
            for r in app.segmented_control
            if r.label.startswith("Size this trade by")
        ]
        assert modes and set(modes[0].options) == {"Share count", "Dollar amount"}
    else:
        infos = "\n".join(i.value for i in app.info)
        assert "nothing to sell" in infos or "whole share available" in infos


def test_the_share_selector_cannot_exceed_the_holding(_offline):
    """The UI must not be able to express a short; the generator refuses
    independently, and this pins that the widget agrees."""
    app = _page("Discrete Selling")
    if not app.selectbox:
        pytest.skip("no holdings in this environment")
    widget = next(n for n in app.number_input if n.label == "Shares")
    caption = "\n".join(c.value for c in app.caption)
    assert widget.min == 1
    assert widget.max is not None and widget.max >= 1
    assert "whole share(s) of" in caption


def test_a_dollar_amount_above_the_holding_refuses_rather_than_capping(_offline):
    """Silently capping would change the number the owner typed -- the same
    action-shaped edit SELL-1 refuses on the share side."""
    app = _page("Discrete Selling")
    if not app.selectbox:
        pytest.skip("no holdings in this environment")
    app.segmented_control(key="discrete_sell_mode").set_value("Dollar amount").run()
    app.number_input(key="discrete_sell_dollars").set_value(10_000_000.0).run()

    assert not app.exception
    warnings = "\n".join(w.value for w in app.warning)
    assert "more than you hold" in warnings
    assert "nothing is proposed" in warnings


def test_a_zero_dollar_input_hides_a_stored_sell_card(_offline):
    app = _page("Discrete Selling")
    if not app.selectbox:
        pytest.skip("no holdings in this environment")
    ticker = app.selectbox(key="discrete_sell_ticker").value
    app.button(key="discrete_sell_create").click().run()
    assert f"SELL 1 {ticker}" in [s.value for s in app.subheader]

    app.segmented_control(key="discrete_sell_mode").set_value("Dollar amount").run()

    assert f"SELL 1 {ticker}" not in [s.value for s in app.subheader]
    notices = "\n".join(i.value for i in app.info)
    assert "controls do not describe a valid trade" in notices


def test_discrete_sell_dollar_sizing_uses_the_exact_recorded_price(
    _offline, monkeypatch
):
    """At an exact price just over $100, a $100 budget cannot buy one share.
    The rounded display float must not change that boundary."""
    import streamlit as st
    import assistant.sample_portfolio as sample_portfolio
    import scripts.personal_assistant_ui as ui

    positions = [
        {
            "ticker": "NVDA",
            "shares": "10",
            "entry_price": "90",
            "current_price": "100.000000000000000001",
        }
    ]
    monkeypatch.setattr(sample_portfolio, "SAMPLE_POSITIONS", positions)
    monkeypatch.setattr(ui, "SAMPLE_POSITIONS", positions)
    st.cache_data.clear()
    ui._load_base_packet.clear()

    app = _page("Discrete Selling")
    app.segmented_control(key="discrete_sell_mode").set_value("Dollar amount").run()
    app.number_input(key="discrete_sell_dollars").set_value(100.0).run()

    warnings = "\n".join(w.value for w in app.warning)
    assert "does not cover one share" in warnings
