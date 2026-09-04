"""The conftest leak guard must detect a containment write into the real root.

The guard is what turns a silent machine-global emergency stop into a failing
test.  Prove it fires on a crafted incident whose origin database sits under
this session's pytest base temp, and stays quiet for incidents from elsewhere,
so concurrent suites on the same host cannot trip it.  The real runtime file
is never touched: the root is redirected to a temporary directory first.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import assistant.dispatch_fence as dispatch_fence
from tests.conftest import _assert_test_left_no_incident_in_the_real_runtime_stop


def _write_stop(root: Path, origin_database: str) -> None:
    state_dir = root / dispatch_fence._STATE_DIRECTORY_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / dispatch_fence._EMERGENCY_STOP_FILE_NAME).write_text(
        json.dumps(
            {
                "version": dispatch_fence._RUNTIME_STOP_STATE_VERSION,
                "active": True,
                "scope": "execution_runtime",
                "generation": 1,
                "reason": "test",
                "changed_at": "2026-09-04T00:00:00+00:00",
                "open_incidents": [
                    {
                        "incident_id": "crafted",
                        "origin_database": origin_database,
                        "reason": "test",
                        "changed_at": "2026-09-04T00:00:00+00:00",
                    }
                ],
                "last_clear": None,
            }
        ),
        encoding="utf-8",
    )


def test_guard_fails_when_this_session_leaked_into_the_real_root(
    tmp_path, monkeypatch
):
    fake_real_root = tmp_path / "fake-localappdata"
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: fake_real_root
    )
    # An origin under this session's base temp is attributed to this session.
    leaked_db = tmp_path.parent / "some_other_test0" / "assistant.db"
    _write_stop(fake_real_root, str(leaked_db))

    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)

    # The autouse conftest guard re-runs at teardown while the root is still
    # redirected here; it would (correctly) fail on this crafted leak, so the
    # crafted state is removed once the assertion above has been proven.
    (
        fake_real_root
        / dispatch_fence._STATE_DIRECTORY_NAME
        / dispatch_fence._EMERGENCY_STOP_FILE_NAME
    ).unlink()


def test_guard_ignores_incidents_from_other_sessions(tmp_path, monkeypatch):
    fake_real_root = tmp_path / "fake-localappdata"
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: fake_real_root
    )
    _write_stop(fake_real_root, r"C:\somewhere\else\pytest-9\assistant.db")

    _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_is_quiet_when_no_real_stop_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: tmp_path / "empty"
    )
    _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
