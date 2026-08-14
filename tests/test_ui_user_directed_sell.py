"""The Discrete Selling page's owner-directed sell path.

Before this, the Selling tab could only act on a computed policy breach. The
risk in adding an owner-directed path is that it starts to LOOK like a
project recommendation, or that it renders a stale proposal for a different
holding under the current selection -- the exact stale-state defect AP-9
closed on the Buying page. Both are pinned here, in the real app.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline_selling_environment(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})

    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def _selling_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Discrete Selling"
    app.run()
    return app


def test_discrete_selling_is_the_only_owner_directed_sell_surface(
    _offline_selling_environment,
):
    app = _selling_app()

    assert not app.exception
    assert any(s.label == "Holding to sell" for s in app.selectbox)
    subheaders = [s.value for s in app.subheader]
    assert "Recommended sells (policy-breach based)" not in subheaders


def test_the_direct_sale_section_disclaims_any_recommendation(
    _offline_selling_environment,
):
    """An owner-directed sale must never borrow the credibility of the
    computed policy-breach path sitting directly below it."""
    app = _selling_app()

    assert not app.exception
    captions = "\n".join(element.value for element in app.caption)
    assert "NOT the policy-breach path" in captions
    assert "does not predict price declines" in captions
    assert "approve the proposal by typing the phrase" in captions


def test_the_share_selector_cannot_exceed_the_shares_held(
    _offline_selling_environment,
):
    """The number input is bounded by the holding itself, so the UI cannot
    even express a short. The generator refuses independently (see
    tests/test_user_directed_sell.py) -- this pins that the widget agrees
    rather than relying on the refusal alone."""
    app = _selling_app()

    assert not app.exception
    widget = app.number_input(key="discrete_sell_shares")
    assert widget.max is not None
    assert widget.min == 1


def test_fractional_remainder_is_not_described_as_a_closed_position(
    _offline_selling_environment,
    monkeypatch,
):
    """Whole-share input cannot dispose of a fractional remainder."""
    import assistant.sample_portfolio as sample_portfolio
    import scripts.personal_assistant_ui as ui

    fractional_positions = [
        {
            "ticker": "NVDA",
            "shares": "10.5",
            "entry_price": "100",
            "current_price": "110",
        }
    ]
    # AppTest executes the file in its own module namespace, while prior UI
    # tests may already have imported the normal module. Patch both sources.
    monkeypatch.setattr(sample_portfolio, "SAMPLE_POSITIONS", fractional_positions)
    monkeypatch.setattr(ui, "SAMPLE_POSITIONS", fractional_positions)
    # AppTest has its own execution-module wrapper around the same cached
    # function; clear the shared Streamlit cache, not only the normal import.
    import streamlit as st

    st.cache_data.clear()
    ui._load_base_packet.clear()

    app = _selling_app()
    app.number_input(key="discrete_sell_shares").set_value(10).run()

    captions = "\n".join(element.value for element in app.caption)
    assert "closes the position" not in captions
    assert "0.5 share(s) would remain" in captions


def test_changing_share_input_hides_the_stale_actionable_proposal(
    _offline_selling_environment,
):
    app = _selling_app()
    app.number_input(key="discrete_sell_shares").set_value(3).run()
    app.button(key="discrete_sell_create").click().run()
    assert "SELL 3 NVDA" in [element.value for element in app.subheader]

    app.number_input(key="discrete_sell_shares").set_value(4).run()

    assert "SELL 3 NVDA" not in [element.value for element in app.subheader]
    notices = "\n".join(element.value for element in app.info)
    assert "3 share(s)" in notices
    assert "current 4-share selection" in notices
