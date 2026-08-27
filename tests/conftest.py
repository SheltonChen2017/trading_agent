"""Session-wide guards that keep tests away from operator runtime state."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# This must run during pytest collection, before test_personal_assistant_ui.py
# imports the Streamlit script. That import executes the app in Streamlit bare
# mode and constructs AssistantStore() with no explicit path. Without this
# guard, every full-suite/reviewer run writes sample briefing rows into the
# operator's data/trading_assistant.db.
_PYTEST_STATE_DIR = Path(tempfile.mkdtemp(prefix="trading-agent-pytest-"))
os.environ["TRADING_ASSISTANT_DB"] = str(_PYTEST_STATE_DIR / "assistant.db")

# The same import, one step further: personal_assistant_ui.py calls
# _load_packet() at module scope, which reaches build_decision_packet(
# use_live_alpaca=is_configured()). On a machine with real broker
# credentials that issues a live HTTPS request to Alpaca during pytest
# COLLECTION -- and when the broker answers with an error, collection
# aborts and the entire suite runs zero tests. Observed 2026-08-02, the
# first full run after credentials were set on this machine:
#
#   ERROR collecting tests/test_personal_assistant_ui.py
#   alpaca.common.exceptions.APIError: {"message": "unauthorized."}
#
# A test suite must never depend on, or be broken by, a live brokerage
# account. No test reads these variables: tests/test_alpaca_broker.py sets
# its own fakes and tests/test_assistant_context_builder.py patches the
# broker functions directly, so clearing them here only removes the
# accidental live path.
for _credential in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
    os.environ.pop(_credential, None)


@pytest.fixture(autouse=True)
def _isolate_execution_runtime_authority(tmp_path, monkeypatch):
    """Tests may isolate only the private root, never a production env seam."""
    import assistant.dispatch_fence as dispatch_fence
    import risk.execution_gate as execution_gate

    monkeypatch.setattr(
        dispatch_fence, "_RUNTIME_FENCE_ROOT", (tmp_path / "runtime").resolve()
    )
    monkeypatch.setattr(dispatch_fence, "_RUNTIME_STOP_LOCAL_FAILURE", None)
    with dispatch_fence._DISPATCH_PERMITS_GUARD:
        dispatch_fence._DISPATCH_PERMITS.clear()
    with execution_gate._consumed_authorization_tokens_lock:
        execution_gate._consumed_authorization_tokens.clear()
    yield
    with dispatch_fence._DISPATCH_PERMITS_GUARD:
        dispatch_fence._DISPATCH_PERMITS.clear()
    with execution_gate._consumed_authorization_tokens_lock:
        execution_gate._consumed_authorization_tokens.clear()


@atexit.register
def _remove_pytest_state() -> None:
    shutil.rmtree(_PYTEST_STATE_DIR, ignore_errors=True)
