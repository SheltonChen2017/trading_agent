"""ML-5: earnings-gap risk (strategy doc section 9).

Scope discipline (doc 9.1): this estimates gap MAGNITUDE and downside-tail
risk. It does not predict whether a company will "beat", and it does not
say whether a stock should be bought. Those are different questions with
different (and much worse) evidence bases.

The event-time mapping in `map_gap_window()` is the correctness heart of
this module (doc 9.2), and it is the reason this label was deliberately
NOT built during ML-2 alongside the price-only labels:

  * released AFTER the close  -> gap = release-day close -> next session open
  * released BEFORE the open  -> gap = prior session close -> release-day open
  * intraday or unknown time  -> UNAVAILABLE, not guessed

Sessions come from the NYSE exchange calendar (pandas_market_calendars,
already pinned and already used by risk/execution_gate.py and
data/market_data.py), never from calendar-day arithmetic -- doc 9.2 is
explicit about this. "The next day" after a Friday after-close release is
Monday, and after a Thursday release before a Friday holiday it is the
following Monday; +1 day arithmetic silently gets both wrong.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from data.exchange_calendar import ExchangeCalendarError, session_close_instant

_EASTERN = ZoneInfo("America/New_York")

# Fallback for a date that is not a trading session at all. The authoritative
# boundary is the exchange calendar's own close for the release's session:
# roughly nine sessions a year close early at 13:00 ET, and a 14:30 ET release
# on one of those days is genuinely after_close rather than intraday.
from data.earnings_data import MARKET_CLOSE_HOUR

MARKET_OPEN_HOUR = 9  # 9:30 ET; a release at/after this and before close is intraday
MARKET_OPEN_MINUTE = 30

MIN_EVENTS_FOR_FIT = 30
MIN_TAIL_EVENTS_FOR_FIT = 8


class EarningsGapError(ValueError):
    """Event data cannot support a trustworthy earnings-gap estimate."""


@dataclasses.dataclass(frozen=True)
class GapWindow:
    """One resolved event-time mapping."""

    available: bool
    release_timing: str
    from_session: str | None = None
    from_price_field: str | None = None
    to_session: str | None = None
    to_price_field: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _session_close_local(local: pd.Timestamp) -> pd.Timestamp | None:
    """Actual Eastern close of the release's own session, or None if it is not one."""
    try:
        close_utc = session_close_instant(local.date().isoformat())
    except ExchangeCalendarError:
        return None
    return pd.Timestamp(close_utc).tz_convert(_EASTERN)


def classify_release_timing(announced_at: pd.Timestamp) -> str:
    """"after_close", "before_open", or "intraday" from a release timestamp."""
    announced_at = pd.Timestamp(announced_at)
    if announced_at.tzinfo is None or announced_at.utcoffset() is None:
        raise EarningsGapError(
            "release timestamp must be timezone-aware; naive event times cannot "
            "establish market availability"
        )
    local = announced_at.tz_convert(_EASTERN)
    hour, minute = local.hour, local.minute
    close_local = _session_close_local(local)
    if close_local is not None:
        if local >= close_local:
            return "after_close"
    elif hour >= MARKET_CLOSE_HOUR:
        # The release date is not a trading session, so there is no real close
        # to compare against; keep the historical fixed-hour behavior.
        return "after_close"
    if (hour, minute) < (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE):
        return "before_open"
    return "intraday"


def map_gap_window(
    announced_at: pd.Timestamp | str, *, session_index: pd.DatetimeIndex
) -> GapWindow:
    """Resolve which two prices define this event's gap (doc 9.2).

    `session_index` is the ticker's own trading-session index; the resolved
    sessions must exist in it, otherwise the event is unavailable rather
    than mapped to a session the ticker did not actually trade.
    """
    # to_datetime(errors="coerce"), NOT pd.Timestamp(): the constructor
    # RAISES DateParseError on unparseable input, so the pd.isna() guard
    # below would never be reached and one malformed announcement timestamp
    # (entirely possible in real yfinance earnings data) would crash the
    # whole batch instead of degrading that single event to "unavailable".
    timestamp = pd.to_datetime(announced_at, errors="coerce")
    if pd.isna(timestamp):
        return GapWindow(
            available=False, release_timing="unknown", reason="unparseable release timestamp"
        )
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return GapWindow(
            available=False,
            release_timing="unknown",
            reason="timezone-naive release timestamp cannot establish availability",
        )
    local_timestamp = timestamp.tz_convert(_EASTERN)
    timing = classify_release_timing(timestamp)
    if timing == "intraday":
        # Doc 9.2: "intraday or unknown release time: unavailable for the
        # primary experiment unless separately preregistered." An intraday
        # release has no clean open/close boundary -- the move is mixed into
        # a regular trading session and cannot be isolated as a gap.
        return GapWindow(
            available=False,
            release_timing="intraday",
            reason="intraday release has no isolatable open/close gap",
        )

    if not isinstance(session_index, pd.DatetimeIndex):
        return GapWindow(
            available=False,
            release_timing=timing,
            reason="session_index must be a DatetimeIndex",
        )
    if session_index.hasnans or session_index.has_duplicates:
        return GapWindow(
            available=False,
            release_timing=timing,
            reason="session_index contains NaT or duplicate sessions",
        )
    sessions = session_index
    if sessions.tz is not None:
        sessions = sessions.tz_convert(_EASTERN).tz_localize(None)
    sessions = sessions.normalize()
    if not sessions.is_monotonic_increasing:
        return GapWindow(
            available=False,
            release_timing=timing,
            reason="session_index is not sorted ascending",
        )
    release_day = local_timestamp.tz_localize(None).normalize()

    if timing == "after_close":
        # The release day itself must be a trading session (that's the close
        # the market last saw), and the gap is measured into the NEXT session.
        if release_day not in sessions:
            return GapWindow(
                available=False,
                release_timing=timing,
                reason="release day is not a trading session for this ticker",
            )
        position = sessions.get_loc(release_day)
        if position + 1 >= len(sessions):
            return GapWindow(
                available=False,
                release_timing=timing,
                reason="no subsequent session available to measure the gap into",
            )
        return GapWindow(
            available=True,
            release_timing=timing,
            from_session=str(sessions[position].date()),
            from_price_field="close",
            to_session=str(sessions[position + 1].date()),
            to_price_field="open",
        )

    # before_open: gap runs from the PRIOR session's close into this
    # session's open.
    if release_day not in sessions:
        return GapWindow(
            available=False,
            release_timing=timing,
            reason="release day is not a trading session for this ticker",
        )
    position = sessions.get_loc(release_day)
    if position == 0:
        return GapWindow(
            available=False,
            release_timing=timing,
            reason="no prior session available to measure the gap from",
        )
    return GapWindow(
        available=True,
        release_timing=timing,
        from_session=str(sessions[position - 1].date()),
        from_price_field="close",
        to_session=str(sessions[position].date()),
        to_price_field="open",
    )


@dataclasses.dataclass(frozen=True)
class GapObservation:
    ticker: str
    announced_at: str
    release_timing: str
    from_session: str
    to_session: str
    from_price: float
    to_price: float
    gap_pct: float

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            raise EarningsGapError("ticker must be a non-empty string")
        timestamp = pd.to_datetime(self.announced_at, errors="coerce")
        if (
            pd.isna(timestamp)
            or pd.Timestamp(timestamp).tzinfo is None
            or pd.Timestamp(timestamp).utcoffset() is None
        ):
            raise EarningsGapError("announced_at must be a timezone-aware timestamp")
        if self.release_timing not in {"after_close", "before_open"}:
            raise EarningsGapError("release_timing must describe an overnight gap")
        for name, value in (
            ("from_session", self.from_session), ("to_session", self.to_session)
        ):
            try:
                parsed = pd.Timestamp(value)
            except (TypeError, ValueError) as exc:
                raise EarningsGapError(f"{name} must be a valid session date") from exc
            if parsed.tzinfo is not None or parsed.strftime("%Y-%m-%d") != value:
                raise EarningsGapError(f"{name} must use canonical YYYY-MM-DD format")
        if self.to_session <= self.from_session:
            raise EarningsGapError("to_session must follow from_session")
        if not (
            math.isfinite(self.from_price)
            and math.isfinite(self.to_price)
            and self.from_price > 0
            and self.to_price > 0
            and math.isfinite(self.gap_pct)
        ):
            raise EarningsGapError("gap prices and percentage must be finite and positive-priced")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def compute_gap_observations(
    ticker: str, price: pd.DataFrame, announcements: Sequence[Any]
) -> tuple[tuple[GapObservation, ...], tuple[dict[str, Any], ...]]:
    """Resolve every announcement into a realized gap, returning
    (observations, skipped) -- skipped events carry their reason, so a low
    event count is visibly explained rather than silently small."""
    for column in ("open", "close"):
        if column not in price.columns:
            raise EarningsGapError(f"price frame is missing {column!r}")
    if not isinstance(price.index, pd.DatetimeIndex):
        raise EarningsGapError("price index must be a DatetimeIndex")
    canonical_price = price.copy()
    sessions = canonical_price.index
    if sessions.tz is not None:
        sessions = sessions.tz_convert(_EASTERN).tz_localize(None)
    sessions = sessions.normalize()
    if sessions.hasnans or sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise EarningsGapError(
            "price index must contain unique, sorted, non-missing sessions"
        )
    canonical_price.index = sessions

    observations: list[GapObservation] = []
    skipped: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    for announcement in announcements:
        parsed = pd.to_datetime(announcement, errors="coerce")
        if pd.notna(parsed) and pd.Timestamp(parsed).tzinfo is not None:
            event_identity = pd.Timestamp(parsed).tz_convert("UTC").isoformat()
            if event_identity in seen_events:
                skipped.append(
                    {"announced_at": str(announcement), "reason": "duplicate earnings event"}
                )
                continue
            seen_events.add(event_identity)
        window = map_gap_window(announcement, session_index=sessions)
        if not window.available:
            skipped.append({"announced_at": str(announcement), "reason": window.reason})
            continue
        from_ts = pd.Timestamp(window.from_session)
        to_ts = pd.Timestamp(window.to_session)
        from_price = float(canonical_price.loc[from_ts, window.from_price_field])
        to_price = float(canonical_price.loc[to_ts, window.to_price_field])
        if not (
            math.isfinite(from_price)
            and math.isfinite(to_price)
            and from_price > 0
            and to_price > 0
        ):
            skipped.append(
                {"announced_at": str(announcement), "reason": "non-positive or non-finite price"}
            )
            continue
        observations.append(
            GapObservation(
                ticker=ticker,
                announced_at=event_identity,
                release_timing=window.release_timing,
                from_session=window.from_session,
                to_session=window.to_session,
                from_price=from_price,
                to_price=to_price,
                gap_pct=round((to_price / from_price - 1.0) * 100, 6),
            )
        )
    return tuple(observations), tuple(skipped)


def median_absolute_gap_baseline(
    observations: Sequence[GapObservation],
) -> float | None:
    """Doc 9.4's first model: historical median absolute gap.

    Median, not mean: earnings gaps are heavy-tailed, and a single -30%
    event would drag a mean baseline far away from the typical outcome the
    baseline is supposed to represent.
    """
    values = [
        abs(o.gap_pct) for o in observations if math.isfinite(o.gap_pct)
    ]
    if not values:
        return None
    return round(float(np.median(values)), 6)


def check_event_support(
    observations: Sequence[GapObservation], *, threshold_pct: float
) -> dict[str, Any]:
    """Doc 9.4: "Refuse model fitting when event count or class support is
    inadequate. The report must give the count of distinct earnings events,
    positive/negative tail events, and tickers represented."

    Returned rather than raised so a caller can report WHY a ticker has no
    model instead of just showing nothing.
    """
    if (
        isinstance(threshold_pct, bool)
        or not isinstance(threshold_pct, (int, float))
        or not math.isfinite(float(threshold_pct))
        or threshold_pct <= 0
    ):
        raise EarningsGapError("threshold_pct must be a positive finite number")
    distinct: dict[tuple[str, str], GapObservation] = {}
    for observation in observations:
        key = (observation.ticker, observation.announced_at)
        existing = distinct.get(key)
        if existing is not None and existing != observation:
            raise EarningsGapError(
                f"conflicting duplicate earnings event {key!r}"
            )
        distinct[key] = observation
    unique_observations = tuple(distinct.values())
    gaps = np.array([o.gap_pct for o in unique_observations], dtype=float)
    gaps = gaps[np.isfinite(gaps)]
    positive_tail = int(np.sum(gaps >= threshold_pct))
    negative_tail = int(np.sum(gaps <= -threshold_pct))
    tickers = sorted({o.ticker for o in unique_observations})
    sufficient = (
        len(gaps) >= MIN_EVENTS_FOR_FIT
        and positive_tail >= MIN_TAIL_EVENTS_FOR_FIT
        and negative_tail >= MIN_TAIL_EVENTS_FOR_FIT
    )
    reasons: list[str] = []
    if len(gaps) < MIN_EVENTS_FOR_FIT:
        reasons.append(f"only {len(gaps)} events; {MIN_EVENTS_FOR_FIT} required")
    if positive_tail < MIN_TAIL_EVENTS_FOR_FIT:
        reasons.append(
            f"only {positive_tail} upside-tail events; {MIN_TAIL_EVENTS_FOR_FIT} required"
        )
    if negative_tail < MIN_TAIL_EVENTS_FOR_FIT:
        reasons.append(
            f"only {negative_tail} downside-tail events; {MIN_TAIL_EVENTS_FOR_FIT} required"
        )
    return {
        "event_count": int(len(gaps)),
        "positive_tail_events": positive_tail,
        "negative_tail_events": negative_tail,
        "tickers_represented": tickers,
        "ticker_count": len(tickers),
        "threshold_pct": threshold_pct,
        "sufficient": sufficient,
        "insufficiency_reasons": tuple(reasons),
    }


def fit_gap_threshold_classifier(
    x_train: np.ndarray, y_train: np.ndarray, *, random_seed: int = 0
):
    """Logistic regression for "absolute gap exceeds threshold" (doc 9.4).

    Refuses a single-class target: a classifier fit on all-zeros will
    happily report perfect accuracy while having learned nothing, and its
    predicted probabilities would be meaningless.
    """
    from sklearn.linear_model import LogisticRegression

    x_train = np.asarray(x_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if x_train.ndim != 2 or y_train.ndim != 1 or x_train.shape[0] != y_train.shape[0]:
        raise EarningsGapError("x_train and y_train must have aligned 2D/1D rows")
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all():
        raise EarningsGapError("training data must be finite")
    if np.any((y_train != 0) & (y_train != 1)):
        raise EarningsGapError("threshold classifier target must contain only 0 or 1")
    unique = np.unique(y_train)
    if unique.size < 2:
        raise EarningsGapError(
            "threshold classifier requires both classes present in training data"
        )
    if x_train.shape[0] < MIN_EVENTS_FOR_FIT:
        raise EarningsGapError(
            f"need at least {MIN_EVENTS_FOR_FIT} training events, got {x_train.shape[0]}"
        )
    model = LogisticRegression(max_iter=1000, random_state=random_seed)
    model.fit(x_train, y_train)
    return model


def fit_gap_magnitude_quantiles(
    x_train: np.ndarray,
    y_train: np.ndarray,
    *,
    quantiles: Sequence[float] = (0.1, 0.5, 0.9),
    random_seed: int = 0,
) -> dict[float, Any]:
    """Quantile regression for gap magnitude intervals (doc 9.4).

    One model per quantile (sklearn's GradientBoostingRegressor with
    loss="quantile"), returned as a dict so a caller emits an interval
    rather than a single misleading point estimate.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    x_train = np.asarray(x_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if x_train.ndim != 2 or y_train.ndim != 1 or x_train.shape[0] != y_train.shape[0]:
        raise EarningsGapError("x_train and y_train must have aligned 2D/1D rows")
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all():
        raise EarningsGapError("training data must be finite")
    if np.any(y_train < 0):
        raise EarningsGapError("gap magnitude targets must be non-negative")
    if x_train.shape[0] < MIN_EVENTS_FOR_FIT:
        raise EarningsGapError(
            f"need at least {MIN_EVENTS_FOR_FIT} training events, got {x_train.shape[0]}"
        )
    quantile_values = tuple(quantiles)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in quantile_values
    ):
        raise EarningsGapError("quantiles must be finite numeric values")
    if len(quantile_values) != len(set(quantile_values)):
        raise EarningsGapError("quantiles must be unique")
    models: dict[float, Any] = {}
    for quantile in quantile_values:
        if not 0 < quantile < 1:
            raise EarningsGapError("quantiles must be in (0, 1)")
        model = GradientBoostingRegressor(
            loss="quantile", alpha=quantile, random_state=random_seed
        )
        model.fit(x_train, y_train)
        models[quantile] = model
    return models
