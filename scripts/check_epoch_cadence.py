"""Report whether the active evidence epoch is still accumulating evidence.

Deliberately a standalone script rather than a subcommand of
`run_personal_assistant.py`, for one reason: that CLI builds an
`AssistantStore`, and opening the OPERATOR database with a development
checkout's store runs that checkout's migrations against a database the
frozen runtime is pinned to. This tool exists to be safe to run from the
development folder against the live operator database while an epoch is
open, so it uses an enforced read-only SQLite connection and never constructs
the store. Its calendar helper transitively loads the storage module, but no
store instance or migration-capable connection is created.

    python scripts/check_epoch_cadence.py
    python scripts/check_epoch_cadence.py --database path/to/trading_assistant.db

Exit status: 0 when healthy or not-due-yet; 1 when the epoch is behind,
stalled, or absent, so it can be used from a scheduler if the owner later
wants that.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, time, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.epoch_cadence import (  # noqa: E402
    BEHIND,
    CadenceReport,
    DEFAULT_CAPTURE_LOCAL_TIME,
    DEFAULT_CAPTURE_TIMEZONE,
    HEALTHY,
    NOT_DUE_YET,
    NO_ACTIVE_EPOCH,
    STALLED,
    evaluate_cadence,
)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "trading_assistant.db"


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"No database at {path}")
    # mode=ro is the enforcement, not a convention: it makes a stray write
    # an error rather than a silent mutation of live evidence.
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def read_cadence(
    path: Path,
    now: datetime,
    *,
    capture_local_time: time = DEFAULT_CAPTURE_LOCAL_TIME,
    capture_timezone: tzinfo = DEFAULT_CAPTURE_TIMEZONE,
) -> CadenceReport:
    connection = _read_only_connection(path)
    try:
        connection.row_factory = sqlite3.Row
        epoch_row = connection.execute(
            "SELECT evidence_epoch, started_at, status FROM paper_evidence_epochs "
            "WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        epoch = dict(epoch_row) if epoch_row is not None else None
        recorded: list[str] = []
        if epoch is not None:
            recorded = [
                str(row["session_date"])
                for row in connection.execute(
                    "SELECT session_date FROM paper_account_observations "
                    "WHERE evidence_epoch = ?",
                    (epoch["evidence_epoch"],),
                )
            ]
    finally:
        connection.close()
    return evaluate_cadence(
        epoch=epoch,
        recorded_sessions=recorded,
        now=now,
        capture_local_time=capture_local_time,
        capture_timezone=capture_timezone,
    )


_LABEL = {
    HEALTHY: "HEALTHY",
    NOT_DUE_YET: "NOT DUE YET",
    BEHIND: "BEHIND",
    STALLED: "STALLED",
    NO_ACTIVE_EPOCH: "NO ACTIVE EPOCH",
}


def _parse_capture_time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "capture time must be HH:MM or HH:MM:SS"
        ) from exc
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError(
            "capture time must not include an offset; use --capture-timezone"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=os.environ.get("TRADING_ASSISTANT_DB", str(_DEFAULT_DB)),
        help="operator database to inspect (opened READ-ONLY)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--capture-time",
        type=_parse_capture_time,
        default=DEFAULT_CAPTURE_LOCAL_TIME,
        help=(
            "installed PaperObservation trigger clock (default: 16:30 on "
            "the current epoch host)"
        ),
    )
    parser.add_argument(
        "--capture-timezone",
        default=getattr(DEFAULT_CAPTURE_TIMEZONE, "key", "America/Los_Angeles"),
        help=(
            "IANA timezone of the installed trigger "
            "(default: America/Los_Angeles)"
        ),
    )
    arguments = parser.parse_args(argv)

    try:
        capture_timezone = ZoneInfo(arguments.capture_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        # Both are reachable and neither subsumes the other:
        # ZoneInfoNotFoundError is a KeyError subclass raised for an unknown
        # key, while an empty or non-normalized key ("", "/America/New_York")
        # raises ValueError. Catching only the first turned an operator typo
        # into a raw traceback.
        parser.error(f"unusable capture timezone: {arguments.capture_timezone!r}")
        raise AssertionError("argparse.error must exit") from exc

    report = read_cadence(
        Path(arguments.database),
        datetime.now(timezone.utc),
        capture_local_time=arguments.capture_time,
        capture_timezone=capture_timezone,
    )

    if arguments.json:
        print(json.dumps(dataclasses_asdict(report), indent=2, sort_keys=True))
    else:
        print(f"{_LABEL.get(report.status, report.status)}: {report.detail}")
        if report.expected_sessions:
            print(
                f"  expected {len(report.expected_sessions)}, "
                f"recorded {len(report.recorded_sessions)}, "
                f"missing {len(report.missing_sessions)}"
            )
        if report.last_recorded_session:
            print(f"  last observation: {report.last_recorded_session}")
    return 0 if report.ok else 1


def dataclasses_asdict(report: object) -> dict:
    import dataclasses

    return dataclasses.asdict(report)


if __name__ == "__main__":
    raise SystemExit(main())
