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
    _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


# Bound once at import: this guard runs in EVERY test's teardown, including
# tests that legitimately monkeypatch ``json.loads`` with a must-not-run
# sentinel (the insider SEC nesting-cap tests).  A bound JSONDecoder.decode
# never consults ``json.loads``, so the guard cannot trip those sentinels.
_DECODE_RUNTIME_STOP_STATE = __import__("json").JSONDecoder().decode

# Session start, for attributing runtime-stop incidents to THIS run.  Bound at
# import so every teardown compares against the same instant.
_SESSION_STARTED_AT = __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc
)


def _incident_predates_this_session(activated_at: object) -> bool:
    """True only for an incident stamped strictly before this session began.

    Anything unparseable or naive returns False so the incident stays
    attributed by path: an unreadable timestamp must not hide a leak.
    """
    from datetime import datetime

    if not isinstance(activated_at, str):
        return False
    try:
        stamped = datetime.fromisoformat(activated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if stamped.tzinfo is None or stamped.utcoffset() is None:
        return False
    return stamped < _SESSION_STARTED_AT


def _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path) -> None:
    """Fail the test that leaked containment into the operator's runtime.

    The runtime emergency stop lives in one per-OS-user %LOCALAPPDATA% root
    shared by every database on the host.  The autouse redirect above covers
    this interpreter only; a child process a test spawns starts from the REAL
    root, and one containment write there latches a machine-global stop that
    refuses every proposal in the operator's live paper application and in
    every sibling lane's checkout (Insider lane R-09/R-18/R-22: 42 debris
    incidents were observed, all from pytest temp databases).

    Only incidents whose origin database sits under THIS session's pytest
    base temp AND whose ``activated_at`` is not before this session started
    are attributed here.  The path test keeps concurrent suites from other
    sessions on the same host from tripping the guard; the time test keeps a
    stale incident left under a reused fixed ``--basetemp`` by an earlier run
    from erroring every test of the next run.  An incident without a
    parseable ``activated_at`` is attributed by path alone (fail closed).
    The guard reads the real file and never mutates it: operator runtime
    state is not test cleanup.

    Because it runs in fixture teardown, a leak is reported by pytest as an
    ERROR at teardown of the offending test, not as a FAIL: the test's own
    assertions may still show passed.
    """
    import os

    import assistant.dispatch_fence as dispatch_fence

    try:
        real_root = dispatch_fence._canonical_runtime_root()
    except Exception:  # platform without a resolvable root: nothing to guard
        return
    stop_file = (
        real_root
        / dispatch_fence._STATE_DIRECTORY_NAME
        / dispatch_fence._EMERGENCY_STOP_FILE_NAME
    )
    if not stop_file.exists():
        return
    try:
        state = _DECODE_RUNTIME_STOP_STATE(stop_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # unreadable real state is the runtime's own fail-closed concern
    session_base = os.path.normcase(str(tmp_path.parent.resolve()))
    leaked = [
        incident.get("origin_database")
        for incident in state.get("open_incidents", []) or []
        if isinstance(incident, dict)
        and os.path.normcase(str(incident.get("origin_database", ""))).startswith(
            session_base
        )
        and not _incident_predates_this_session(incident.get("activated_at"))
    ]
    assert not leaked, (
        "this test (or a child process it spawned) wrote a containment incident "
        f"into the REAL runtime emergency stop at {stop_file}; redirect "
        "assistant.dispatch_fence._RUNTIME_FENCE_ROOT in every process the test "
        f"starts. Leaked origin databases: {leaked}"
    )


@atexit.register
def _remove_pytest_state() -> None:
    shutil.rmtree(_PYTEST_STATE_DIR, ignore_errors=True)
