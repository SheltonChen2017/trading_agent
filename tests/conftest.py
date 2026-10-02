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
_ENCODE_RUNTIME_STOP_INCIDENT = __import__("json").JSONEncoder(
    sort_keys=True, separators=(",", ":"), allow_nan=False
).encode
_RUNTIME_STOP_SESSION_FILE: Path | None = None
_RUNTIME_STOP_PREEXISTING: dict[str, tuple[str, str]] = {}
_RUNTIME_STOP_PREVIOUS_CLEAR: tuple[str, str] | None = None


def _observe_runtime_stop() -> tuple[
    Path, dict[str, tuple[str, str]], tuple[str, str] | None
]:
    """Read only; absence is empty, inability to inspect is not proof of no leak."""
    import assistant.dispatch_fence as dispatch_fence

    try:
        stop_file = (
            dispatch_fence._canonical_runtime_root()
            / dispatch_fence._STATE_DIRECTORY_NAME
            / dispatch_fence._EMERGENCY_STOP_FILE_NAME
        ).resolve()
    except Exception as exc:
        raise AssertionError("runtime-stop leak guard cannot resolve its root") from exc
    try:
        text = stop_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return stop_file, {}, None
    except (OSError, UnicodeError) as exc:
        raise AssertionError("runtime-stop leak guard cannot read its state") from exc
    try:
        state = _DECODE_RUNTIME_STOP_STATE(text)
        if not isinstance(state, dict):
            raise ValueError("state must be an object")
        generation = state.get("generation")
        raw_incidents = state.get("open_incidents")
        if type(generation) is not int or generation < 0 or not isinstance(raw_incidents, list):
            raise ValueError("invalid generation or incident inventory")
        incidents = {}
        for incident in raw_incidents:
            if not isinstance(incident, dict):
                raise ValueError("incident must be an object")
            identifier = incident.get("incident_id")
            origin = incident.get("origin_database")
            if (
                not isinstance(identifier, str) or not identifier
                or identifier in incidents
                or not isinstance(origin, str) or not origin
            ):
                raise ValueError("invalid or duplicate incident identity")
            incidents[identifier] = (
                os.path.normcase(str(Path(origin).resolve())),
                _ENCODE_RUNTIME_STOP_INCIDENT(incident),
            )
        last_clear = state.get("last_clear")
        if last_clear is not None:
            if (
                not isinstance(last_clear, dict)
                or not isinstance(last_clear.get("incident_id"), str)
                or not last_clear["incident_id"]
            ):
                raise ValueError("invalid incident clear receipt")
            last_clear = (
                last_clear["incident_id"], _ENCODE_RUNTIME_STOP_INCIDENT(last_clear)
            )
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        raise AssertionError("runtime-stop leak guard cannot decode its state") from exc
    return stop_file, incidents, last_clear


def _capture_runtime_stop_session_baseline() -> None:
    """Capture once before collection/tests, never lazily exempt a new incident."""
    global _RUNTIME_STOP_SESSION_FILE, _RUNTIME_STOP_PREEXISTING
    global _RUNTIME_STOP_PREVIOUS_CLEAR
    stop_file, incidents, last_clear = _observe_runtime_stop()
    _RUNTIME_STOP_SESSION_FILE = stop_file
    _RUNTIME_STOP_PREEXISTING = dict(incidents)
    _RUNTIME_STOP_PREVIOUS_CLEAR = last_clear


def pytest_configure(config) -> None:
    # This historic hook also runs when conftest is discovered during collection
    # (e.g. `pytest` from the repository root), before its test modules load.
    # Never rebaseline: collection itself can publish a containment incident.
    if _RUNTIME_STOP_SESSION_FILE is None:
        try:
            _capture_runtime_stop_session_baseline()
        except AssertionError as exc:
            pytest.exit(str(exc), returncode=2)


def pytest_sessionstart(session) -> None:
    pytest_configure(session.config)


def _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path) -> None:
    """Fail the test that leaked containment into the operator's runtime.

    The runtime emergency stop lives in one per-OS-user %LOCALAPPDATA% root
    shared by every database on the host.  The autouse redirect above covers
    this interpreter only; a child process a test spawns starts from the REAL
    root, and one containment write there latches a machine-global stop that
    refuses every proposal in the operator's live paper application and in
    every sibling lane's checkout (Insider lane R-09/R-18/R-22: 42 debris
    incidents were observed, all from pytest temp databases).

    Attribute new/changed incidents by exact path components, not string
    prefixes or semantic activation timestamps. Unchanged incidents captured
    before collection are exempt, including old incidents under a reused
    fixed basetemp. An exemption expires when its incident disappears/changes;
    a changed per-incident last-clear receipt also expires that incident's
    exemption. Global generation changes cannot identify whose lifecycle
    changed. A lifecycle wholly hidden between reads without a surviving
    per-incident receipt is not observable by this guard.
    Missing baseline, unreadable state, and invalid inventory fail visibly.
    The guard never mutates the file: operator runtime state is not cleanup.

    Because it runs in fixture teardown, a leak is reported by pytest as an
    ERROR at teardown of the offending test, not as a FAIL: the test's own
    assertions may still show passed.
    """
    global _RUNTIME_STOP_PREVIOUS_CLEAR
    stop_file, incidents, last_clear = _observe_runtime_stop()
    assert stop_file == _RUNTIME_STOP_SESSION_FILE, (
        "runtime-stop leak guard has no session baseline for this root"
    )
    cleared_id = (
        last_clear[0]
        if last_clear is not None and last_clear != _RUNTIME_STOP_PREVIOUS_CLEAR
        else None
    )
    for identifier, content in list(_RUNTIME_STOP_PREEXISTING.items()):
        if incidents.get(identifier) != content or identifier == cleared_id:
            del _RUNTIME_STOP_PREEXISTING[identifier]
    _RUNTIME_STOP_PREVIOUS_CLEAR = last_clear
    session_base = Path(os.path.normcase(str(tmp_path.parent.resolve())))
    leaked = [
        origin for identifier, (origin, content) in incidents.items()
        if Path(origin).is_relative_to(session_base)
        and _RUNTIME_STOP_PREEXISTING.get(identifier) != (origin, content)
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
