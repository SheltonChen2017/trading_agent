"""Every navigation page renders through the real Streamlit app (AUI-003).

The AUI-003 correction wrapped nineteen logical sections in bordered
containers -- a re-indentation of large page regions in a 4,700-line
script. Source tests prove the wrappers exist; THIS file proves the pages
still run: each page executes end to end in Streamlit's AppTest harness
with no exception.

Determinism: Alpaca credentials are removed (sample portfolio path),
provider bar fetches return empty (the degraded path every page promises
to survive), and earnings fetches return nothing. The store is a fresh
temporary database. No network, no broker, no operator data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"

_PAGES = (
    "Briefing",
    "Buying",
    "Selling",
    "Propose & Approve",
    "History",
    "Ticker Suggestions",
    "Backtest",
    "Reports",
    "Operations",
    "Settings & Features",
)


@pytest.fixture()
def _isolated_app_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    monkeypatch.setenv("TRADING_ASSISTANT_DB", str(tmp_path / "smoke.db"))

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(
        data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {}
    )
    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


@pytest.mark.parametrize("page", _PAGES)
def test_page_renders_without_exception(page, _isolated_app_environment):
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = page
    app.run()
    assert not app.exception, f"{page} raised: {app.exception}"
