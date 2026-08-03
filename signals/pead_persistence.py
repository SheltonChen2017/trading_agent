"""
Consecutive-earnings-surprise persistence (a PEAD variant).

Classic single-surprise PEAD (signals/pead.py) fires on any one earnings
beat or miss above a threshold. The hypothesis here is narrower: a
SINGLE beat is largely priced by now in big liquid names, but a RUN of
same-direction surprises may still carry information, because it is
evidence that the market's model of the company is persistently wrong in
one direction rather than noisily wrong in both.

Construction (frozen 2026-08-03, before any result was observed):

  streak         — count consecutive same-sign surprises ending at the
                   current announcement, looking back at most
                   `max_streak_quarters` (8) events.
  gate           — fire only when streak >= `min_streak_quarters` (4)
                   AND the current |surprise| >= threshold. Both
                   conditions are on the CURRENT event, so the signal
                   fires on the announcement's effective date only.
  direction      — the sign of the streak ("up" for a run of beats).
  hold           — 40 trading days, the middle of the specified 20-60
                   day PEAD window.

LOOK-AHEAD DISCIPLINE. The streak is computed from events at or before
the current announcement only. The earnings frame handed in covers a
ticker's whole history including events in the future relative to the
backtest's as-of date, so slicing it correctly is the entire ballgame —
test_streak_never_counts_future_earnings asserts this directly by
appending later events and checking no earlier signal changes.

SAMPLE SIZE. This is event-driven: ~4 events per ticker per year, and
the streak gate rejects most of those, so it fires far less often than
any daily signal in this project. Expect a small sample and treat the
significance results with correspondingly more caution — a handful of
signals is not evidence in either direction.

NOT POINT-IN-TIME. yfinance's surprise figures are as-recorded-now, not
as-published-then: restatements and shifting consensus estimates are
baked in, and only currently-listed tickers are present at all. This
signal therefore cannot support a point-in-time claim
(`point_in_time_data=false`), and a positive result here is exploratory
evidence about a hypothesis, not a tradeable backtest.

Same output column contract as scan_dips_and_ups(); bind `earnings_data`
with functools.partial before passing as scan_fn, exactly like
signals/pead.py.
"""
from __future__ import annotations

import pandas as pd

from config import PEAD_SURPRISE_THRESHOLD_PCT
from data.earnings_data import match_effective_date

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

MIN_STREAK_QUARTERS = 4
MAX_STREAK_QUARTERS = 8


def compute_surprise_streak(
    surprises: pd.DataFrame,
    as_of_event: pd.Timestamp,
    max_streak_quarters: int = MAX_STREAK_QUARTERS,
) -> tuple[int, float]:
    """
    Length and sign of the run of same-sign surprises ending at
    `as_of_event`.

    Returns (streak_length, current_surprise_pct). A streak of 1 means
    the previous quarter broke the run (or there is no previous
    quarter). Events AFTER `as_of_event` are excluded — that exclusion is
    what keeps this causal, since the caller hands in a ticker's full
    earnings history.

    Zero surprises are treated as breaking a streak rather than
    continuing it: a company exactly matching consensus is evidence the
    market's model is right, which is the opposite of what this signal
    is looking for.
    """
    if max_streak_quarters < 1:
        raise ValueError(f"max_streak_quarters must be positive, got {max_streak_quarters!r}.")
    if as_of_event not in surprises.index:
        return 0, float("nan")

    # Sort BEFORE slicing. On a newest-first frame (which is how
    # yfinance hands earnings back) ".loc[:event]" means "from the newest
    # row down to this one" — i.e. the future — and sorting the slice
    # afterwards cannot undo that. Checking the slice's own monotonicity
    # is not a guard either: a one-row slice is trivially monotonic, so
    # the check silently passes on exactly the input that breaks it.
    series = surprises["surprise_pct"]
    if not series.index.is_monotonic_increasing:
        series = series.sort_index()

    # Strictly causal: everything up to and including this event.
    history = series.loc[:as_of_event].iloc[-max_streak_quarters:]
    if history.empty:
        return 0, float("nan")

    current = float(history.iloc[-1])
    if pd.isna(current) or current == 0:
        return 0, current

    current_sign = 1 if current > 0 else -1
    streak = 0
    for value in reversed(history.tolist()):
        if pd.isna(value) or value == 0:
            break
        if (1 if value > 0 else -1) != current_sign:
            break
        streak += 1

    return streak, current


def scan_pead_persistence(
    data: dict[str, pd.DataFrame],
    earnings_data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    surprise_threshold_pct: float = PEAD_SURPRISE_THRESHOLD_PCT,
    min_streak_quarters: int = MIN_STREAK_QUARTERS,
    max_streak_quarters: int = MAX_STREAK_QUARTERS,
) -> pd.DataFrame:
    """
    Flag a stock on its earnings reaction day when the current surprise
    both exceeds `surprise_threshold_pct` and completes a run of at
    least `min_streak_quarters` consecutive same-sign surprises.

    `return_zscore` carries the streak length (the signal's strength
    measure), and `volume_zscore` carries the current surprise percent —
    both repurposed to keep the shared column contract, matching how
    signals/pead.py repurposes `return_zscore` for the surprise.
    """
    if as_of is None:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    if min_streak_quarters < 1:
        raise ValueError(f"min_streak_quarters must be positive, got {min_streak_quarters!r}.")
    if min_streak_quarters > max_streak_quarters:
        raise ValueError(
            f"min_streak_quarters ({min_streak_quarters}) cannot exceed "
            f"max_streak_quarters ({max_streak_quarters})."
        )

    rows = []
    for ticker, price_df in data.items():
        if ticker not in earnings_data or as_of not in price_df.index:
            continue

        surprises = earnings_data[ticker]
        if surprises is None or surprises.empty:
            continue

        matched = match_effective_date(as_of, surprises.index, price_df.index)
        if matched is None:
            continue  # not this ticker's earnings reaction day

        streak, surprise_pct = compute_surprise_streak(surprises, matched, max_streak_quarters)
        if streak < min_streak_quarters:
            continue
        if pd.isna(surprise_pct) or abs(surprise_pct) < surprise_threshold_pct:
            continue

        close = float(price_df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": float(streak),
                "volume_zscore": round(float(surprise_pct), 2),
                "direction": "up" if surprise_pct > 0 else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
