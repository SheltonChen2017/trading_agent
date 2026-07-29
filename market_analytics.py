"""
Generic, backward-looking market-analytics primitives shared by
production (`assistant/`) and research (`strategies/`, `backtest/`) code.

Lives at the repo root, alongside config.py/baskets.py, deliberately --
NOT inside assistant/ (would force research code to import from the
production layer to re-export its own helper) or data/ (every existing
data/* module fetches over the network; these functions are pure
computation on already-fetched data). docs/ARCHITECTURE_DEBT.md, item 5
(2026-07-28): assistant/stock_lookup.py used to import
run_baseline_forward_returns from backtest/engine.py just to compute
holding-period ranges, which transitively pulled in
`from signals.scanner import scan_dips_and_ups` (backtest/engine.py's own
top-level import) whether or not anything needed it -- moving both
functions here removes that coupling.

classify_trend() was strategies/trend_vol_rotation.py's; both modules
re-export the moved function under their original name so existing
callers and tests need no changes.
"""
from __future__ import annotations

import pandas as pd

from config import BACKTEST_HOLD_DAYS, SLIPPAGE_PCT


def classify_trend(close: pd.Series, as_of: pd.Timestamp, lookback_days: int = 200) -> str | None:
    """"uptrend" if `close` at `as_of` is at/above its own trailing
    `lookback_days` moving average, else "downtrend". None if there isn't
    enough trailing history yet."""
    if as_of not in close.index:
        return None
    idx = close.index.get_loc(as_of)
    if idx < lookback_days - 1:
        return None
    window = close.iloc[idx - lookback_days + 1 : idx + 1]
    sma = window.mean()
    return "uptrend" if close.loc[as_of] >= sma else "downtrend"


def run_baseline_forward_returns(
    data: dict[str, pd.DataFrame],
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    The control group for backtest/engine.py's run_backtest(): for EVERY
    date (not just flagged signal dates), compute the same forward return
    over `hold_days`, minus slippage. This answers "what would holding
    this stock for the same period have returned on an arbitrary day" —
    the baseline a flagged signal's return needs to beat. Without this, an
    apparent edge over a rising test window can just be the whole universe
    drifting upward, not anything the scanner detected.

    `entry_timing` must match whatever was passed to run_backtest() for the
    signal side of the comparison, or the two aren't measuring the same
    thing: "same_close" compares close-to-close over `hold_days`; "next_open"
    shifts both legs forward one day and compares open-to-open, matching
    run_backtest()'s next-day-open execution assumption (see its docstring);
    "same_day_open_to_close" compares open-to-close on the SAME day
    (`hold_days` is ignored in this mode) -- see run_backtest()'s
    docstring for this mode's unresolved look-ahead realism gap.
    """
    if entry_timing not in ("same_close", "next_open", "same_day_open_to_close"):
        raise ValueError(
            f"entry_timing must be 'same_close', 'next_open', or 'same_day_open_to_close', got {entry_timing!r}"
        )

    frames = []
    for ticker, df in data.items():
        if entry_timing == "same_close":
            entry_price, forward_price = df["close"], df["close"].shift(-hold_days)
        elif entry_timing == "same_day_open_to_close":
            entry_price, forward_price = df["open"], df["close"]
        else:  # next_open
            entry_price, forward_price = df["open"].shift(-1), df["open"].shift(-(1 + hold_days))
        if entry_timing != "same_day_open_to_close" and len(df) <= hold_days:
            continue
        raw_return_pct = (forward_price - entry_price) / entry_price * 100
        net_return_pct = raw_return_pct - 2 * slippage_pct * 100
        frame = pd.DataFrame({"ticker": ticker, "date": df.index, "net_return_pct": net_return_pct})
        frames.append(frame.dropna(subset=["net_return_pct"]))

    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "net_return_pct"])

    return pd.concat(frames, ignore_index=True)
