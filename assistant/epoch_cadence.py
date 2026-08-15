"""Is the active evidence epoch still ACCUMULATING observations?

This answers a question nothing else in the repository asks. The existing
gap check in `paper_evidence.summarize_paper_epoch()` computes its expected
window as ``_valid_sessions(observations[0], observations[-1])`` -- from the
first recorded observation to the LAST recorded one. That finds interior
holes, but it is structurally incapable of finding a trailing stall: the
window ends wherever the data ends, so whatever comes after the last
observation is never "expected". With zero observations the block is skipped
entirely.

That is not hypothetical. Epoch-002 sat at ONE observation while the ledger
drifted three cents past the reconciliation tolerance and every nightly
capture correctly refused to record evidence it could not trust. Those runs
raised a critical alert and failed nonzero, but the evidence summary itself
still had no direct answer to "is this epoch accumulating?" The count stopped
going up, and the interior-gap check reported nothing wrong because one
observation has no interior. It was diagnosed by tracing the incident by hand.

So this module anchors the window to **epoch start -> now** instead of to the
data, which is the only way a trailing stall becomes visible.

Two distinctions this module refuses to blur:

* **"not due yet" is not "healthy."** A young epoch that has produced nothing
  because nothing is due yet is fine; a month-old epoch that has produced
  nothing is not. Both have zero observations.
* **"behind" is not "stalled."** One missing session in an otherwise current
  epoch is a hiccup; a run of missing sessions at the tail with nothing since
  is a stall. Reporting them identically would train the reader to ignore the
  alarm.

Read-only by construction: every function here takes already-fetched values.
Nothing in this module opens a database, writes, submits, or touches an
epoch. See `scripts/check_epoch_cadence.py` for the read-only reader.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from assistant.paper_evidence import valid_session_dates

#: Measured trigger of the CURRENT epoch host. This is a fixed wall-clock
#: schedule, not a duration after the exchange close. On early-close sessions
#: the task still runs at 16:30 Pacific; deriving it from market close would
#: move the supposed capture three hours early and manufacture a missing row.
#: A reinstalled task may use a different local time. The CLI exposes both
#: values so the measured trigger can be supplied without a code change.
DEFAULT_CAPTURE_LOCAL_TIME = time(hour=16, minute=30)
DEFAULT_CAPTURE_TIMEZONE = ZoneInfo("America/Los_Angeles")

#: Extra slack before a session that has not appeared is called missing, so a
#: run a few minutes late is never reported as a failure.
DEFAULT_GRACE = timedelta(hours=2)

#: Consecutive missing sessions at the tail before "behind" becomes "stalled".
DEFAULT_STALL_THRESHOLD = 2

HEALTHY = "healthy"
NOT_DUE_YET = "not_due_yet"
BEHIND = "behind"
STALLED = "stalled"
NO_ACTIVE_EPOCH = "no_active_epoch"


@dataclasses.dataclass(frozen=True)
class CadenceReport:
    """What the epoch should have collected by now, and what it did."""

    evidence_epoch: str | None
    epoch_started_at: str | None
    status: str
    expected_sessions: tuple[str, ...]
    recorded_sessions: tuple[str, ...]
    missing_sessions: tuple[str, ...]
    last_recorded_session: str | None
    consecutive_missing_at_tail: int
    detail: str

    @property
    def ok(self) -> bool:
        # NO_ACTIVE_EPOCH is a distinct, truthful status, but not scheduler
        # success: when an epoch is promised to be accumulating, its absence
        # must alert rather than silently look healthy.
        return self.status in (HEALTHY, NOT_DUE_YET)


def _as_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def expected_capture_sessions(
    started_at: datetime,
    now: datetime,
    *,
    capture_local_time: time = DEFAULT_CAPTURE_LOCAL_TIME,
    capture_timezone: tzinfo = DEFAULT_CAPTURE_TIMEZONE,
    grace: timedelta = DEFAULT_GRACE,
) -> list[str]:
    """Sessions this epoch should already have captured, oldest first.

    A session belongs to the epoch only if its CAPTURE instant falls after
    the epoch opened. This is the subtle case and it is not theoretical:
    epoch-005 opened at 16:59 local on 2026-08-13, after that day's 16:30
    capture had already run and been recorded against epoch-004. Counting
    2026-08-13 as owed by epoch-005 would report a permanent phantom miss on
    day one.
    """
    started = _as_utc(started_at, "started_at")
    current = _as_utc(now, "now")
    if not isinstance(capture_local_time, time):
        raise TypeError("capture_local_time must be a datetime.time")
    if capture_local_time.tzinfo is not None:
        raise ValueError("capture_local_time must be naive; pass capture_timezone separately")
    if not isinstance(capture_timezone, tzinfo):
        raise TypeError("capture_timezone must be timezone-aware")
    if not isinstance(grace, timedelta):
        raise TypeError("grace must be a timedelta")
    if grace < timedelta(0):
        raise ValueError("grace must be non-negative")
    if current < started:
        return []

    # Widen by a day on each side: the ET session date and the UTC instant
    # can fall on different calendar days, in both directions.
    start_date = (started - timedelta(days=1)).date().isoformat()
    end_date = (current + timedelta(days=1)).date().isoformat()

    expected: list[str] = []
    for session in valid_session_dates(start_date, end_date):
        captured_at = datetime.combine(
            date.fromisoformat(session), capture_local_time, tzinfo=capture_timezone
        ).astimezone(timezone.utc)
        if captured_at <= started:
            continue  # captured before this epoch existed
        if captured_at + grace > current:
            continue  # not due yet
        expected.append(session)
    return expected


def evaluate_cadence(
    *,
    epoch: dict | None,
    recorded_sessions: object,
    now: datetime,
    capture_local_time: time = DEFAULT_CAPTURE_LOCAL_TIME,
    capture_timezone: tzinfo = DEFAULT_CAPTURE_TIMEZONE,
    grace: timedelta = DEFAULT_GRACE,
    stall_threshold: int = DEFAULT_STALL_THRESHOLD,
) -> CadenceReport:
    """Compare what should have been captured against what was."""
    if isinstance(stall_threshold, bool) or not isinstance(stall_threshold, int):
        raise TypeError("stall_threshold must be a positive whole number")
    if stall_threshold <= 0:
        raise ValueError("stall_threshold must be a positive whole number")
    if not epoch:
        return CadenceReport(
            evidence_epoch=None, epoch_started_at=None, status=NO_ACTIVE_EPOCH,
            expected_sessions=(), recorded_sessions=(), missing_sessions=(),
            last_recorded_session=None, consecutive_missing_at_tail=0,
            detail=(
                "No paper evidence epoch is active. Nothing is being "
                "accumulated, which is only correct if that is deliberate."
            ),
        )

    name = str(epoch.get("evidence_epoch"))
    started_raw = str(epoch.get("started_at"))
    started_at = datetime.fromisoformat(started_raw)

    recorded = tuple(sorted({str(s) for s in (recorded_sessions or ())}))
    expected = tuple(
        expected_capture_sessions(
            started_at, now,
            capture_local_time=capture_local_time,
            capture_timezone=capture_timezone,
            grace=grace,
        )
    )
    missing = tuple(s for s in expected if s not in set(recorded))
    last_recorded = recorded[-1] if recorded else None

    # Count the run of missing sessions at the END of the expected window.
    # A stall is defined by its tail: three misses last month followed by two
    # weeks of clean captures is a resolved incident, not a current stall.
    tail = 0
    for session in reversed(expected):
        if session in set(recorded):
            break
        tail += 1

    if not expected:
        if recorded:
            not_due_detail = (
                f"{name} opened {started_raw} and no observation is overdue yet. "
                f"{len(recorded)} observation(s) already recorded; the current "
                "grace window has not elapsed."
            )
        else:
            not_due_detail = (
                f"{name} opened {started_raw} and no observation is due yet. "
                "Zero observations is the correct state, not a stall."
            )
        return CadenceReport(
            evidence_epoch=name, epoch_started_at=started_raw,
            status=NOT_DUE_YET, expected_sessions=expected,
            recorded_sessions=recorded, missing_sessions=(),
            last_recorded_session=last_recorded,
            consecutive_missing_at_tail=0,
            detail=not_due_detail,
        )

    if not missing:
        return CadenceReport(
            evidence_epoch=name, epoch_started_at=started_raw, status=HEALTHY,
            expected_sessions=expected, recorded_sessions=recorded,
            missing_sessions=(), last_recorded_session=last_recorded,
            consecutive_missing_at_tail=0,
            detail=(
                f"{name} has all {len(expected)} expected observation(s) "
                f"through {expected[-1]}."
            ),
        )

    status = STALLED if tail >= stall_threshold else BEHIND
    if status == STALLED:
        detail = (
            f"{name} has recorded nothing for the last {tail} expected "
            f"session(s) (through {expected[-1]}). Last observation: "
            f"{last_recorded or 'none at all'}. The epoch is open but is no "
            "longer accumulating evidence -- check the scheduled task and "
            "whether ledger reconciliation is refusing to capture."
        )
    elif tail == 0:
        # Every miss is INTERIOR: the newest expected session did arrive, so
        # the epoch is still producing and these are historical holes.
        detail = (
            f"{name} is missing {len(missing)} of {len(expected)} expected "
            f"observation(s): {', '.join(missing)}. The most recent expected "
            f"session ({expected[-1]}) was captured, so the epoch is still "
            "producing; these are interior gaps rather than a stall."
        )
    else:
        # The newest expected session is missing, but not yet enough of them
        # to call it a stall. Saying "the most recent was captured" here was
        # a real defect: it is exactly the case where that is false.
        detail = (
            f"{name} is missing {len(missing)} of {len(expected)} expected "
            f"observation(s): {', '.join(missing)}. The most recent expected "
            f"session ({expected[-1]}) has NOT been captured. {tail} missing "
            f"at the tail is below the {stall_threshold}-session stall "
            "threshold, so this may still be one late or failed run -- "
            "re-check after the next session before treating it as a stall."
        )

    return CadenceReport(
        evidence_epoch=name, epoch_started_at=started_raw, status=status,
        expected_sessions=expected, recorded_sessions=recorded,
        missing_sessions=missing, last_recorded_session=last_recorded,
        consecutive_missing_at_tail=tail, detail=detail,
    )
