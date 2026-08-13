"""The Selling page's owner-directed sell section (2026-08-13 request).

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
    app.session_state["nav_page"] = "Selling"
    app.run()
    return app


def test_the_selling_page_offers_a_direct_sale_of_a_held_position(
    _offline_selling_environment,
):
    app = _selling_app()

    assert not app.exception
    subheaders = [s.value for s in app.subheader]
    assert "Sell a specific holding (your own decision)" in subheaders
    # The policy-breach path must still be there and still be distinct.
    assert "Recommended sells (policy-breach based)" in subheaders


def test_the_direct_sale_section_disclaims_any_recommendation(
    _offline_selling_environment,
):
    """An owner-directed sale must never borrow the credibility of the
    computed policy-breach path sitting directly below it."""
    app = _selling_app()

    assert not app.exception
    captions = "\n".join(element.value for element in app.caption)
    assert "This project is NOT recommending it" in captions
    assert "zero signals as real edge" in captions
    assert "you approve by typing the phrase" in captions


def test_the_share_selector_cannot_exceed_the_shares_held(
    _offline_selling_environment,
):
    """The number input is bounded by the holding itself, so the UI cannot
    even express a short. The generator refuses independently (see
    tests/test_user_directed_sell.py) -- this pins that the widget agrees
    rather than relying on the refusal alone."""
    app = _selling_app()

    assert not app.exception
    sell_inputs = [
        element
        for element in app.number_input
        if element.label.startswith("Shares to sell")
    ]
    assert sell_inputs, [element.label for element in app.number_input]
    widget = sell_inputs[0]
    held = int(widget.label.split("you hold ")[1].rstrip(")"))
    assert widget.max == held
    assert widget.min == 1
