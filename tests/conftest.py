"""Session-wide guards that keep tests away from operator runtime state."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path


# This must run during pytest collection, before test_personal_assistant_ui.py
# imports the Streamlit script. That import executes the app in Streamlit bare
# mode and constructs AssistantStore() with no explicit path. Without this
# guard, every full-suite/reviewer run writes sample briefing rows into the
# operator's data/trading_assistant.db.
_PYTEST_STATE_DIR = Path(tempfile.mkdtemp(prefix="trading-agent-pytest-"))
os.environ["TRADING_ASSISTANT_DB"] = str(_PYTEST_STATE_DIR / "assistant.db")


@atexit.register
def _remove_pytest_state() -> None:
    shutil.rmtree(_PYTEST_STATE_DIR, ignore_errors=True)
