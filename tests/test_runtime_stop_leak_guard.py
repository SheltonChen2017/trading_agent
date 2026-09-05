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


def _write_stop(
    root: Path,
    origin_database: str,
    *,
    activated_at: object = "2999-01-01T00:00:00+00:00",
) -> None:
    """Write a crafted stop whose one incident uses the runtime's own schema.

    ``activated_at`` defaults to the far future so the crafted incident can
    never predate the session that reads it.
    """
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
                        "activated_at": activated_at,
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


def test_guard_ignores_a_stale_incident_from_an_earlier_run_under_the_same_basetemp(
    tmp_path, monkeypatch
):
    """A fixed ``--basetemp`` is reused across runs.  An incident an EARLIER
    run left under it must not error every test of this run: only incidents
    stamped at or after this session's start are attributed here."""
    fake_real_root = tmp_path / "fake-localappdata"
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: fake_real_root
    )
    stale_db = tmp_path.parent / "earlier_run_test0" / "assistant.db"
    _write_stop(
        fake_real_root, str(stale_db), activated_at="2000-01-01T00:00:00+00:00"
    )

    _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


@pytest.mark.parametrize(
    "activated_at",
    ["not-a-timestamp", "2000-01-01T00:00:00", None],
    ids=["unparseable", "naive", "missing"],
)
def test_guard_attributes_by_path_when_the_incident_stamp_is_unusable(
    tmp_path, monkeypatch, activated_at
):
    """An unreadable or naive stamp must not hide a leak under this base temp."""
    fake_real_root = tmp_path / "fake-localappdata"
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: fake_real_root
    )
    leaked_db = tmp_path.parent / "some_other_test0" / "assistant.db"
    _write_stop(fake_real_root, str(leaked_db), activated_at=activated_at)

    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    (
        fake_real_root
        / dispatch_fence._STATE_DIRECTORY_NAME
        / dispatch_fence._EMERGENCY_STOP_FILE_NAME
    ).unlink()


def test_guard_is_quiet_when_no_real_stop_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dispatch_fence, "_canonical_runtime_root", lambda: tmp_path / "empty"
    )
    _assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
