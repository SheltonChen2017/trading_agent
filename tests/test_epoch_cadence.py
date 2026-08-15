"""The epoch stall detector.

The evidence-summary failure this exists to catch is silent: a refused
scheduled capture does fail nonzero and create a critical alert, but
`summarize_paper_epoch()` still reports no trailing gap while the observation
count stops going up. Epoch-002 sat at one observation because that check
computes its window as first-observation -> last-observation and therefore
cannot see past the last row it has.

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

import sqlite3
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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


def test_an_early_close_does_not_move_the_fixed_task_trigger_earlier():
    """CODSTALL-001: the installed task runs at 16:30 Pacific even when the
    market closes early. The Friday after Thanksgiving closes at 13:00 ET;
    modelling capture as close + 3.5 hours makes it due at 16:30 ET, three
    hours before the task can run, and can manufacture a missing session.
    At 00:00Z (16:00 Pacific) neither the trigger nor its grace has elapsed.
    """
    expected = expected_capture_sessions(
        _at("2026-11-25T00:00:00+00:00"),
        _at("2026-11-28T00:00:00+00:00"),
    )
    assert "2026-11-27" not in expected, expected


def test_the_capture_timezone_actually_moves_the_due_instant():
    """The current host is 16:30 Pacific; a fresh install could be 16:30
    Eastern. The detector must model either measured trigger without a code
    edit -- and the assertion has to DISCRIMINATE, which the earlier version
    of this test did not: it asserted only that a session was absent, which
    was equally true under the default, so it passed with `capture_timezone`
    ignored entirely.

    2026-08-14 at 23:00Z is 16:00 Pacific but 19:00 Eastern. An Eastern
    trigger (16:30 ET + 2h grace = 22:30Z) is therefore already overdue while
    a Pacific one (16:30 PT + 2h = 01:30Z next day) is not.
    """
    now = _at("2026-08-14T23:00:00+00:00")
    pacific = expected_capture_sessions(_at(EPOCH_005_START), now)
    eastern = expected_capture_sessions(
        _at(EPOCH_005_START),
        now,
        capture_timezone=ZoneInfo("America/New_York"),
    )
    assert "2026-08-14" not in pacific, pacific
    assert "2026-08-14" in eastern, eastern


def test_the_capture_clock_actually_moves_the_due_instant():
    """Same discrimination requirement for the wall-clock half: holding the
    timezone fixed, an earlier trigger must make the session overdue sooner.
    """
    now = _at("2026-08-14T23:00:00+00:00")  # 16:00 Pacific
    default_1630 = expected_capture_sessions(_at(EPOCH_005_START), now)
    noon = expected_capture_sessions(
        _at(EPOCH_005_START), now, capture_local_time=time(12, 0)
    )
    assert "2026-08-14" not in default_1630, default_1630
    assert "2026-08-14" in noon, noon


def test_the_modelled_capture_instant_files_under_the_session_it_expects():
    """CLAUDE.md requires a readiness report to use the enforcing function's
    boundary conditions. This module models session D as captured on D at the
    trigger clock; `paper_session_schedule()` -- what the capture command
    actually uses -- derives the session from the EASTERN date of the capture
    instant. For the installed 16:30 Pacific trigger those must agree on
    every session, including the half day after Thanksgiving.
    """
    from assistant.paper_evidence import paper_session_schedule
    from assistant.epoch_cadence import (
        DEFAULT_CAPTURE_LOCAL_TIME,
        DEFAULT_CAPTURE_TIMEZONE,
    )

    sessions = expected_capture_sessions(
        _at("2026-11-01T00:00:00+00:00"), _at("2026-12-31T23:59:00+00:00")
    )
    assert "2026-11-27" in sessions, "the early-close session must be covered"
    for session in sessions:
        instant = datetime.combine(
            date.fromisoformat(session),
            DEFAULT_CAPTURE_LOCAL_TIME,
            tzinfo=DEFAULT_CAPTURE_TIMEZONE,
        )
        filed_under = paper_session_schedule(instant)
        assert filed_under is not None, session
        assert filed_under[0] == session, (session, filed_under[0])


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


def test_not_due_yet_does_not_claim_zero_after_an_early_capture():
    """During the grace window an on-time row can already exist even though
    the session is not overdue. Status stays NOT_DUE_YET, but its detail must
    describe the row it actually received."""
    report = evaluate_cadence(
        epoch=_epoch(),
        recorded_sessions=["2026-08-14"],
        now=_at("2026-08-15T00:00:00+00:00"),  # 17:00 Pacific, inside grace
    )
    assert report.status == NOT_DUE_YET
    assert report.recorded_sessions == ("2026-08-14",)
    assert "Zero observations" not in report.detail
    assert "1 observation" in report.detail


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
    assert not report.ok, (
        "a scheduler-compatible detector must fail when the promised active "
        "epoch no longer exists"
    )


def test_stall_threshold_must_be_a_positive_whole_number():
    """Zero makes even an interior gap satisfy ``tail >= threshold`` and
    produces the impossible message 'recorded nothing for the last 0'."""
    for invalid in (0, -1, True, 1.5):
        with pytest.raises((TypeError, ValueError)):
            evaluate_cadence(
                epoch=_epoch(), recorded_sessions=[],
                now=_at("2026-08-21T23:00:00+00:00"),
                stall_threshold=invalid,
            )


def test_negative_grace_and_aware_wall_clock_are_refused():
    with pytest.raises(ValueError, match="grace"):
        expected_capture_sessions(
            _at(EPOCH_005_START), _at("2026-08-21T23:00:00+00:00"),
            grace=timedelta(seconds=-1),
        )
    with pytest.raises(ValueError, match="naive"):
        expected_capture_sessions(
            _at(EPOCH_005_START), _at("2026-08-21T23:00:00+00:00"),
            capture_local_time=time(16, 30, tzinfo=timezone.utc),
        )


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

    # This pins the direct composition boundary. It is not, by itself, proof
    # of read-only behavior: epoch_cadence's shared calendar helper
    # transitively loads paper_evidence/storage. The behavioral test below is
    # the enforcement proof and confirms no migration-capable store is built.
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("AssistantStore" in name for name in imported), imported
    assert not any(name.startswith("assistant.storage") for name in imported), imported


def test_read_only_is_enforced_by_sqlite_and_reader_changes_no_bytes(tmp_path):
    """A source string saying ``mode=ro`` is not enough; exercise the actual
    Windows URI and prove both a write attempt and the cadence read."""
    from scripts.check_epoch_cadence import _read_only_connection, read_cadence

    database = tmp_path / "cadence.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_evidence_epochs (
                evidence_epoch TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE paper_account_observations (
                evidence_epoch TEXT NOT NULL,
                session_date TEXT NOT NULL
            );
            INSERT INTO paper_evidence_epochs VALUES (
                'paper-test', '2026-08-13T23:59:07+00:00', 'active'
            );
            """
        )
    before = database.read_bytes()

    with _read_only_connection(database) as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "UPDATE paper_evidence_epochs SET status = 'closed'"
            )

    report = read_cadence(database, _at("2026-08-14T12:00:00+00:00"))
    assert report.status == NOT_DUE_YET
    assert database.read_bytes() == before
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_cli_returns_failure_when_no_active_epoch_exists(tmp_path, capsys):
    from scripts.check_epoch_cadence import main

    database = tmp_path / "no-active.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_evidence_epochs (
                evidence_epoch TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE paper_account_observations (
                evidence_epoch TEXT NOT NULL,
                session_date TEXT NOT NULL
            );
            """
        )

    assert main(["--database", str(database), "--json"]) == 1
    assert '"status": "no_active_epoch"' in capsys.readouterr().out


def _cadence_fixture_db(tmp_path, name="flags.db"):
    """An active epoch matching the real epoch-005 start, with no rows."""
    database = tmp_path / name
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_evidence_epochs (
                evidence_epoch TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE paper_account_observations (
                evidence_epoch TEXT NOT NULL,
                session_date TEXT NOT NULL
            );
            INSERT INTO paper_evidence_epochs VALUES (
                'paper-epoch-005', '2026-08-13T23:59:07.901345+00:00', 'active'
            );
            """
        )
    connection.close()
    return database


def test_cli_capture_flags_actually_reach_the_calculation(tmp_path):
    """The flags exist so a remeasured trigger can be supplied without a code
    edit; if they did not reach `expected_capture_sessions` nothing else here
    would notice. Same discriminating instant as the classifier tests: at
    23:00Z an Eastern trigger is overdue and a Pacific one is not.
    """
    from scripts.check_epoch_cadence import read_cadence

    database = _cadence_fixture_db(tmp_path)
    now = _at("2026-08-14T23:00:00+00:00")

    default_report = read_cadence(database, now)
    eastern_report = read_cadence(
        database, now, capture_timezone=ZoneInfo("America/New_York")
    )
    noon_report = read_cadence(database, now, capture_local_time=time(12, 0))

    assert default_report.status == NOT_DUE_YET
    assert default_report.expected_sessions == ()
    assert eastern_report.expected_sessions == ("2026-08-14",)
    assert noon_report.expected_sessions == ("2026-08-14",)


def test_cli_argument_parsing_passes_the_flags_through(tmp_path, monkeypatch):
    """`read_cadence` honouring its keywords does not prove argparse wires
    them. Capture the call instead of asserting on a status: `main` reads the
    real clock, so any status assertion here would be a date-dependent test
    that passes or fails depending on the hour it is run."""
    import scripts.check_epoch_cadence as cli

    database = _cadence_fixture_db(tmp_path, "argv.db")
    seen: dict = {}

    def _capture(path, now, *, capture_local_time, capture_timezone):
        seen.update(
            path=path, capture_local_time=capture_local_time,
            capture_timezone=capture_timezone,
        )
        return evaluate_cadence(
            epoch=None, recorded_sessions=[], now=now
        )

    monkeypatch.setattr(cli, "read_cadence", _capture)
    cli.main(
        [
            "--database", str(database),
            "--capture-time", "12:00",
            "--capture-timezone", "America/New_York",
        ]
    )
    assert seen["capture_local_time"] == time(12, 0)
    assert getattr(seen["capture_timezone"], "key", None) == "America/New_York"
    assert Path(seen["path"]) == database


@pytest.mark.parametrize("value", ["", "/America/New_York", "../etc/passwd"])
def test_cli_rejects_an_unusable_capture_timezone_without_a_traceback(
    tmp_path, value
):
    """An unknown key raises ZoneInfoNotFoundError (a KeyError subclass) but
    an empty or non-normalized key raises ValueError. Catching only the first
    turned an operator typo into a raw traceback instead of a usage error."""
    from scripts.check_epoch_cadence import main

    database = _cadence_fixture_db(tmp_path, "tz.db")
    with pytest.raises(SystemExit) as caught:
        main(["--database", str(database), "--capture-timezone", value])
    assert caught.value.code == 2


def test_the_report_is_immutable():
    report = evaluate_cadence(
        epoch=_epoch(), recorded_sessions=[], now=_at("2026-08-14T12:00:00+00:00")
    )
    assert isinstance(report, CadenceReport)
    with pytest.raises(Exception):
        report.status = "healthy"  # type: ignore[misc]
