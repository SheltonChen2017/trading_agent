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
capture correctly refused to record evidence it could not trust. The
machinery behaved exactly as designed; the count simply stopped going up,
and the interior-gap check reported nothing wrong because one observation
has no interior. It was found by tracing it by hand, days later.

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
from datetime import datetime, timedelta, timezone

from assistant.paper_evidence import session_market_closes, valid_session_dates

#: How long after the exchange close the observation is actually captured.
#: This is a property of the INSTALLED SCHEDULE, not of the market: the
#: `TradingAgent-Paper-PaperObservation` task fires at 16:30 local time, which
#: is 19:30 ET, i.e. 3h30m after a normal 16:00 ET close. It matters for
#: correctness rather than cosmetics -- it decides which epoch a session's
#: capture belongs to when an epoch is rolled mid-day. Re-derive it if the
#: installed trigger changes; do not assume this default still matches.
DEFAULT_CAPTURE_AFTER_CLOSE = timedelta(hours=3, minutes=30)

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
        return self.status in (HEALTHY, NOT_DUE_YET, NO_ACTIVE_EPOCH)


def _as_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def expected_capture_sessions(
    started_at: datetime,
    now: datetime,
    *,
    capture_after_close: timedelta = DEFAULT_CAPTURE_AFTER_CLOSE,
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
    if current < started:
        return []

    # Widen by a day on each side: the ET session date and the UTC instant
    # can fall on different calendar days, in both directions.
    start_date = (started - timedelta(days=1)).date().isoformat()
    end_date = (current + timedelta(days=1)).date().isoformat()

    closes = session_market_closes(start_date, end_date)
    expected: list[str] = []
    for session in valid_session_dates(start_date, end_date):
        close = closes.get(session)
        if close is None:
            continue
        captured_at = _as_utc(close, "market_close") + capture_after_close
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
    capture_after_close: timedelta = DEFAULT_CAPTURE_AFTER_CLOSE,
    grace: timedelta = DEFAULT_GRACE,
    stall_threshold: int = DEFAULT_STALL_THRESHOLD,
) -> CadenceReport:
    """Compare what should have been captured against what was."""
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
            capture_after_close=capture_after_close, grace=grace,
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
        return CadenceReport(
            evidence_epoch=name, epoch_started_at=started_raw,
            status=NOT_DUE_YET, expected_sessions=expected,
            recorded_sessions=recorded, missing_sessions=(),
            last_recorded_session=last_recorded,
            consecutive_missing_at_tail=0,
            detail=(
                f"{name} opened {started_raw} and no observation is due yet. "
                "Zero observations is the correct state, not a stall."
            ),
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
