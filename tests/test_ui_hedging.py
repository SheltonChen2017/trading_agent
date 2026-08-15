"""The Hedging page (HEDGE-1, owner request 2026-08-14).

What the page must never do is more interesting than what it shows. The
risks pinned here:

* it must not render a hedge percentage or a purchase while any selected
  instrument's value is unreadable -- an understated current weight is
  exactly the reading that oversizes a purchase;
* it must never offer a SELL. A hedge page that can rebalance downward is a
  hedge page that can be talked into liquidating a defensive position, and
  that belongs on the deliberate Discrete Selling path;
* it must carry the unmeasured-protection disclosure on every render, because
  the word "hedge" implies protection this project has not measured; and
* it must not ship a submit-all button. A partly-filled multi-leg hedge is a
  different position from the one that was sized.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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


def _hedging(**session) -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Hedging"
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    return app


def _text(app) -> str:
    parts = []
    for collection in (
        app.caption, app.warning, app.error, app.info, app.success,
        app.markdown, app.subheader,
    ):
        for element in collection:
            parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


# --- the page exists and says what it is -----------------------------------


def test_the_hedging_page_is_reachable(_offline):
    app = _hedging()
    assert not app.exception, app.exception
    assert "Hedging" in app.radio(key="nav_page").options


def test_every_render_carries_the_unmeasured_protection_disclosure(_offline):
    app = _hedging()
    assert "NOT confirmed that this basket reduces drawdown" in _text(app)


def test_a_zero_target_reports_but_does_not_offer_a_purchase(_offline):
    app = _hedging()
    assert not app.exception
    assert "Set a hedge target above 0%" in _text(app)
    assert not [b for b in app.button if b.key == "hedge_create"]


def test_the_daily_reset_instrument_is_disclosed_on_the_page(_offline):
    app = _hedging()
    assert "SINGLE day" in _text(app), _text(app)


# --- the boundaries --------------------------------------------------------


def test_the_page_never_offers_a_sell(_offline):
    """A hedge page that can rebalance downward can be talked into
    liquidating a defensive position. Selling stays on the deliberate path."""
    app = _hedging(hedge_target_pct=10.0)
    assert not app.exception
    labels = [str(b.label).lower() for b in app.button]
    assert not any("sell" in label for label in labels), labels


def test_there_is_no_submit_all_control(_offline):
    """A partly-filled multi-leg hedge is a different position from the one
    that was sized, so each leg is approved on its own."""
    app = _hedging(hedge_target_pct=10.0)
    labels = [str(b.label).lower() for b in app.button]
    assert not any("submit all" in label for label in labels), labels


def test_the_source_never_generates_a_hedge_sell_or_submits_directly():
    source = _APP_PATH.read_text(encoding="utf-8")
    page = source.split('if page == "Hedging":', 1)[1].split(
        'if page == "Propose & Approve":', 1
    )[0]
    for forbidden in ("generate_user_directed_sell_proposal", "execute_allocation_batch"):
        assert forbidden not in page, forbidden


def test_an_unreadable_holding_blocks_both_the_percentage_and_the_purchase(
    _offline, monkeypatch
):
    """The page must refuse rather than show an understated hedge weight."""
    import assistant.context_builder as context_builder

    real_builder = context_builder.build_portfolio_snapshot

    def _with_unreadable_tlt(positions, cash, **kwargs):
        snapshot = real_builder(
            list(positions) + [
                {
                    "ticker": "TLT", "shares": 10,
                    "entry_price": 100.0, "current_price": 100.0,
                }
            ],
            cash=cash, **kwargs
        )
        broken = [
            dataclasses.replace(
                p, market_value=float("nan"), market_value_exact=None
            ) if p.ticker == "TLT" else p
            for p in snapshot.positions
        ]
        return dataclasses.replace(snapshot, positions=broken)

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _with_unreadable_tlt
    )
    app = _hedging(hedge_target_pct=10.0)
    assert not app.exception, app.exception
    rendered = _text(app)
    assert "TLT" in rendered
    assert "oversize the purchase" in rendered
    assert not [b for b in app.button if b.key == "hedge_create"]
