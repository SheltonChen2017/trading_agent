"""The epoch stall detector.

The failure this exists to catch is silent by construction: the scheduled
task reports success, the app behaves exactly as designed, and the
observation count simply stops going up. Epoch-002 sat at one observation
while `summarize_paper_epoch()`'s interior-gap check reported nothing wrong,
because that check computes its window as first-observation ->
last-observation and therefore cannot see past the last row it has.

So the tests that matter here are the ones about the WINDOW and about not
crying wolf:

* a trailing stall must be visible (the thing the existing check misses);
* "not due yet" must never be reported as a problem, or the owner learns to
  ignore the tool during every quiet evening;
* a session captured before the epoch opened must not be counted as owed by
  it -- epoch-005 opened after that day's capture had already run; and
* every message must be TRUE of the state it describes.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.epoch_cadence import (
    BEHIND,
    HEALTHY,
    NOT_DUE_YET,
    NO_ACTIVE_EPOCH,
    STALLED,
    CadenceReport,
    evaluate_cadence,
    expected_capture_sessions,
)

# Thursday 2026-08-13 16:59 local / 23:59 UTC -- the real epoch-005 start,
# which is AFTER that day's 16:30 capture had already run.
EPOCH_005_START = "2026-08-13T23:59:07.901345+00:00"


def _epoch(started_at=EPOCH_005_START, name="paper-epoch-005"):
    return {"evidence_epoch": name, "started_at": started_at, "status": "active"}


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- the window ------------------------------------------------------------


def test_a_session_captured_before_the_epoch_opened_is_not_owed_by_it():
    """The real epoch-005 case. Its first day's capture ran at 16:30 and was
    recorded against epoch-004; counting it here would report a phantom miss
    on day one, forever."""
    expected = expected_capture_sessions(
        _at(EPOCH_005_START), _at("2026-08-20T23:00:00+00:00")
    )
    assert "2026-08-13" not in expected, expected
    assert "2026-08-14" in expected


def test_nothing_is_expected_before_the_first_capture_is_due():
    """A few hours into a fresh epoch, zero observations is CORRECT."""
    expected = expected_capture_sessions(
        _at(EPOCH_005_START), _at("2026-08-14T12:00:00+00:00")
    )
    assert expected == []


def test_weekends_and_holidays_are_not_expected_sessions():
    """Independence Day 2026 falls on Saturday and is observed Friday the
    3rd; neither it nor the weekend may be counted as an owed session."""
    expected = expected_capture_sessions(
        _at("2026-07-01T23:59:00+00:00"), _at("2026-07-08T23:00:00+00:00")
    )
    assert "2026-07-04" not in expected
    assert "2026-07-05" not in expected  # Sunday
    assert "2026-07-03" not in expected  # observed holiday
    assert "2026-07-02" in expected


def test_now_before_the_epoch_start_yields_nothing_rather_than_raising():
    assert expected_capture_sessions(
        _at("2026-08-20T00:00:00+00:00"), _at("2026-08-14T00:00:00+00:00")
    ) == []


def test_naive_datetimes_are_refused():
    """A naive timestamp silently interpreted as UTC would shift the whole
    window by hours and quietly change which sessions are owed."""
    with pytest.raises(ValueError):
        expected_capture_sessions(datetime(2026, 8, 13), _at("2026-08-20T00:00:00+00:00"))


# --- the classification ----------------------------------------------------


def test_a_trailing_stall_is_visible():
    """THE case. Observations stop and never resume; the existing interior-gap
    check reports nothing because its window ends at the last row."""
    report = evaluate_cadence(
        epoch=_epoch(),
        recorded_sessions=["2026-08-14", "2026-08-17"],
        now=_at("2026-08-21T23:00:00+00:00"),
    )
    assert report.status == STALLED, report.detail
    assert report.consecutive_missing_at_tail >= 2
    assert not report.ok


def test_an_epoch_that_has_produced_nothing_at_all_is_not_called_healthy():
    report = evaluate_cadence(
        epoch=_epoch(),
        recorded_sessions=[],
        now=_at("2026-08-21T23:00:00+00:00"),
    )
    assert report.status == STALLED
    assert "none at all" in report.detail


def test_not_due_yet_is_reported_as_fine():
    """Crying wolf every evening is how a detector gets ignored."""
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=[],
        now=_at("2026-08-14T12:00:00+00:00"),
    )
    assert report.status == NOT_DUE_YET
    assert report.ok
    assert "correct state" in report.detail


def test_a_fully_captured_epoch_is_healthy():
    now = _at("2026-08-19T23:00:00+00:00")
    expected = expected_capture_sessions(_at(EPOCH_005_START), now)
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=expected, now=now
    )
    assert report.status == HEALTHY
    assert report.missing_sessions == ()


def test_one_missing_tail_session_is_behind_not_stalled():
    """A single late run must not read the same as a dead epoch."""
    now = _at("2026-08-18T23:00:00+00:00")
    expected = expected_capture_sessions(_at(EPOCH_005_START), now)
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=expected[:-1], now=now
    )
    assert report.status == BEHIND
    assert report.consecutive_missing_at_tail == 1


def test_no_active_epoch_is_stated_rather_than_implied_healthy():
    report = evaluate_cadence(
        epoch=None, recorded_sessions=[], now=_at("2026-08-21T23:00:00+00:00")
    )
    assert report.status == NO_ACTIVE_EPOCH
    assert report.ok


# --- the messages must be true ---------------------------------------------


def test_the_behind_message_does_not_claim_the_tail_was_captured():
    """Regression for a defect found by replaying epoch-002's real history:
    the BEHIND message asserted "the most recent expected session was
    captured" in exactly the case where it had NOT been."""
    now = _at("2026-08-18T23:00:00+00:00")
    expected = expected_capture_sessions(_at(EPOCH_005_START), now)
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=expected[:-1], now=now
    )
    assert report.consecutive_missing_at_tail == 1
    assert "was captured, so the epoch is still producing" not in report.detail
    assert "has NOT been captured" in report.detail


def test_an_interior_gap_says_so_and_is_true():
    """The other side: when the newest session DID arrive, the message may
    say so -- and the state must actually be that."""
    now = _at("2026-08-19T23:00:00+00:00")
    expected = expected_capture_sessions(_at(EPOCH_005_START), now)
    assert len(expected) >= 3
    recorded = [s for s in expected if s != expected[1]]  # drop an interior one
    report = evaluate_cadence(epoch=_epoch(), recorded_sessions=recorded, now=now)
    assert report.status == BEHIND
    assert report.consecutive_missing_at_tail == 0
    assert "interior gaps" in report.detail
    assert expected[-1] in report.recorded_sessions


# --- the historical incident -----------------------------------------------


def test_epoch_002_history_is_classified_and_described_correctly():
    """Replay of the real stall: opened 2026-08-06 17:55Z, one observation on
    08-06, closed 08-10 19:25Z. Two sessions were owed (Thu/Fri); the Friday
    never arrived. That is one missing tail session, so BEHIND is the honest
    answer -- and the message must not claim the tail was captured."""
    report = evaluate_cadence(
        epoch=_epoch("2026-08-06T17:55:00+00:00", "paper-epoch-002"),
        recorded_sessions=["2026-08-06"],
        now=_at("2026-08-10T19:25:00+00:00"),
    )
    assert report.status == BEHIND
    assert report.missing_sessions == ("2026-08-07",)
    assert "has NOT been captured" in report.detail


def test_the_same_incident_becomes_a_stall_once_it_persists():
    """Had epoch-002 been left open two more sessions, the detector must
    escalate rather than keep saying 'may still be one late run'."""
    report = evaluate_cadence(
        epoch=_epoch("2026-08-06T17:55:00+00:00", "paper-epoch-002"),
        recorded_sessions=["2026-08-06"],
        now=_at("2026-08-12T23:00:00+00:00"),
    )
    assert report.status == STALLED
    assert report.consecutive_missing_at_tail >= 2


# --- the read-only contract ------------------------------------------------


def test_the_reader_opens_the_database_read_only():
    """The whole point of the standalone script: it must be safe to run from
    a development checkout against the live operator database."""
    import ast

    path = Path(__file__).resolve().parent.parent / "scripts" / "check_epoch_cadence.py"
    source = path.read_text(encoding="utf-8")
    assert "mode=ro" in source

    # The invariant is what the module IMPORTS, not what its prose mentions:
    # the docstring deliberately names AssistantStore to explain the choice,
    # and a substring test would forbid the explanation rather than the
    # dependency.
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("AssistantStore" in name for name in imported), imported
    assert not any(name.startswith("assistant.storage") for name in imported), imported


def test_the_report_is_immutable():
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=[], now=_at("2026-08-14T12:00:00+00:00")
    )
    assert isinstance(report, CadenceReport)
    with pytest.raises(Exception):
        report.status = "healthy"  # type: ignore[misc]
