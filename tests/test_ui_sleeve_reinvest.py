"""The Buying page's three-sleeve M3 dividend-reinvestment section.

Renders unconditionally (no checkbox gating), so a single-run AppTest is
sufficient -- unlike the AI-review sections, there is no session-state
clearing rerun trap here. The deep behavioral coverage (pool math, routing,
earmark lifecycle) lives in tests/test_sleeve_reinvest.py; this pins that
the surface actually exists on the page, renders read-only against an empty
pool, and does not crash the tab.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline_buying_environment(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})

    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def test_buying_page_renders_the_reinvest_section_read_only(
    _offline_buying_environment,
):
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Budgeted Buying"
    app.run()

    assert not app.exception
    labels = [e.label for e in app.expander]
    assert any("Dividend reinvestment" in label for label in labels), labels
    captions = "\n".join(element.value for element in app.caption)
    # The section must state its stance: preference not research, and
    # approve-gated -- never presenting itself as an autonomous purchase.
    assert "Owner preference, not research" in captions
    assert "Nothing is bought until you approve" in captions
