"""
Overnight-gap reversal signal.

Deliberately DIFFERENT information than this project's already-rejected
z-score/momentum/breakout/PEAD family (see memory: project_signal_findings.md):
overnight_gap_pct = today's open / yesterday's close - 1. Academic
evidence (overnight-return / daytime-reversal literature, e.g. published
in the Journal of Financial and Quantitative Analysis) documents that
overnight returns are often followed by a partial DAYTIME REVERSAL --
an unusually negative overnight gap tends to bounce back (at least
partially) between the open and close. Motivation, not a guarantee this
survives this project's universe/costs/rigor bar.

This is the ONLY signal in the current ChatGPT-recommended family that
needs a genuinely new execution mode: the signal is known AT THE OPEN
(not after that day's close, like every other signal here), and the
trade is a SAME-DAY round trip -- enter at today's open, exit at today's
close. See backtest/engine.py's "same_day_open_to_close" entry_timing
(added specifically for this signal) -- `hold_days` is not meaningful
under that mode and should be passed as OVERNIGHT_GAP_HOLD_DAYS (0), a
documented placeholder.

Earnings days behave differently around announcements (much larger,
information-driven gaps rather than the liquidity/order-flow-driven gaps
this signal is about) -- `scan_overnight_gap_reversal()` accepts an
optional `earnings_dates` map (ticker -> set of known earnings effective
dates, e.g. from data/earnings_data.fetch_earnings_history()) and
excludes any gap within OVERNIGHT_GAP_EARNINGS_EXCLUSION_DAYS trading
days of a known earnings date, rather than mixing the two regimes
together.

Opening spreads can be wide enough to consume the entire apparent
edge -- this signal's backtest should always be checked with a realistic
(not zero) slippage_pct, and cost sensitivity is essential before trusting
any positive result here more than for other signals.

PRE-REGISTERED before running against real data (do not re-tune after
seeing a result -- see config.py):
  - rolling window: 20 trading days (OVERNIGHT_GAP_ROLLING_WINDOW),
    matching this project's ROLLING_WINDOW convention for the original
    scanner
  - z-threshold: 2.0 (OVERNIGHT_GAP_Z_THRESHOLD), matching
    RETURN_Z_THRESHOLD's convention
  - direction: a NEGATIVE gap (opened lower than yesterday's close) is
    "dip" (the well-evidenced, expected-reversal-upward leg); a POSITIVE
    gap is "up" (included for symmetry, not the primary hypothesis --
    the practical long-only application is the "dip" leg only)
  - earnings exclusion: +/-1 trading day (OVERNIGHT_GAP_EARNINGS_EXCLUSION_DAYS)

Same output column contract as every other signal, so it plugs into
backtest/engine.py's full toolkit unchanged (pass entry_timing=
"same_day_open_to_close"). `return_pct` holds the actual overnight gap
percentage (not the same-day intraday return that gets measured
separately by run_backtest()'s open-to-close scoring).
"""
from __future__ import annotations

import pandas as pd

from config import OVERNIGHT_GAP_EARNINGS_EXCLUSION_DAYS, OVERNIGHT_GAP_ROLLING_WINDOW, OVERNIGHT_GAP_Z_THRESHOLD

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def compute_gap_features(df: pd.DataFrame, window: int = OVERNIGHT_GAP_ROLLING_WINDOW) -> pd.DataFrame:
    """
    Adds `gap_pct` (today's open vs yesterday's close) and its rolling
    z-score to a copy of `df`. The rolling mean/std are shifted by 1 so
    today's own gap is excluded from its own baseline (same
    self-contamination fix already applied to signals/scanner.py).
    """
    out = df.copy()
    out["gap_pct"] = out["open"] / out["close"].shift(1) - 1

    rolling_mean = out["gap_pct"].shift(1).rolling(window).mean()
    rolling_std = out["gap_pct"].shift(1).rolling(window).std()
    out["gap_zscore"] = (out["gap_pct"] - rolling_mean) / rolling_std
    return out


def _is_earnings_adjacent(
    ticker: str, as_of: pd.Timestamp, date_index: pd.DatetimeIndex, earnings_dates: dict[str, set] | None,
    exclusion_days: int,
) -> bool:
    if not earnings_dates or ticker not in earnings_dates:
        return False
    ticker_earnings = earnings_dates[ticker]
    if not ticker_earnings:
        return False
    idx = date_index.get_loc(as_of)
    window_start = max(0, idx - exclusion_days)
    window_end = min(len(date_index) - 1, idx + exclusion_days)
    nearby_dates = set(date_index[window_start : window_end + 1])
    return bool(nearby_dates & ticker_earnings)


def scan_overnight_gap_reversal(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    window: int = OVERNIGHT_GAP_ROLLING_WINDOW,
    z_threshold: float = OVERNIGHT_GAP_Z_THRESHOLD,
    earnings_dates: dict[str, set] | None = None,
    earnings_exclusion_days: int = OVERNIGHT_GAP_EARNINGS_EXCLUSION_DAYS,
) -> pd.DataFrame:
    """
    Flags every ticker in `data` whose overnight gap (today's open vs
    yesterday's close) has an extreme trailing z-score on `as_of`: "dip"
    for a gap-down (expected daytime reversal upward, the well-evidenced
    leg), "up" for a gap-up (included for symmetry). A ticker within
    `earnings_exclusion_days` trading days of a known earnings date (per
    `earnings_dates`, if supplied) is skipped for that date.
    """
    rows = []
    for ticker, df in data.items():
        if len(df) < window + 2:
            continue
        if as_of is not None and as_of not in df.index:
            continue
        effective_as_of = as_of if as_of is not None else df.index[-1]
        if _is_earnings_adjacent(ticker, effective_as_of, df.index, earnings_dates, earnings_exclusion_days):
            continue

        features = compute_gap_features(df, window=window)
        row = features.loc[effective_as_of] if as_of is not None else features.iloc[-1]

        if pd.isna(row["gap_zscore"]):
            continue
        if abs(row["gap_zscore"]) < z_threshold:
            continue

        rows.append(
            {
                "ticker": ticker,
                "date": row.name,
                "close": round(row["close"], 2),
                "return_pct": round(row["gap_pct"] * 100, 2),
                "return_zscore": round(row["gap_zscore"], 2),
                "volume_zscore": float("nan"),
                "direction": "dip" if row["gap_zscore"] < 0 else "up",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
