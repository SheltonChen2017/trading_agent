"""User-dictated strategy (2026-08-05), spec FROZEN before any result was
observed: each day, scan for the stock with the SHARPEST one-day decline,
buy that dip, and for any +5% rise sell 5% of the position.

The user's description says an LLM (GPT/Grok/Claude) performs the daily
scan. Historical LLM picks are unreplayable, and "the stock with the
sharpest decline" is a deterministic ranking -- argmin of the one-day
close-to-close return over the universe -- which is what any LLM doing
that job faithfully converges to. This backtest therefore tests the
STRATEGY with the deterministic ranking; it cannot measure whatever
additional discretion a live LLM might inject, and no result here says
anything about LLM stock-picking ability.

FROZEN INTERPRETATION (decided before running, mirroring the decline-grid
conventions the user previously confirmed):

  1. UNIVERSE + DATA: config.UNIVERSE via fetch_historical, 1764 sessions
     (~7 years). Survivorship caveat applies as everywhere in this
     project (delisted failures absent from the universe).
  2. PICK: each session t, the eligible ticker with the most negative
     close[t]/close[t-1] - 1. Ties broken alphabetically. One NEW $10,000
     episode opens every session (episodes overlap; see honesty notes).
  3. ENTRY: $10,000 notional at session t+1's OPEN (the project's
     executable next_open convention -- you cannot know day t's final
     ranking in time to trade day t's close).
  4. GRID (the user's "for any 5% increase, I sell 5%"):
     reference price = the entry fill. Each subsequent session, if
     close/reference - 1 >= +0.05, sell 5% of CURRENT shares at the NEXT
     session's open, and the reference RESETS to that fill (the ratchet
     reading the user chose for the decline-grid strategy). Declines:
     hold -- the user specified no averaging down and none is added.
  5. TERMINATION (project-added, NOT in the user's dictation, required to
     make an open-ended hold backtestable): the remainder liquidates at
     the open 63 sessions (~3 months) after entry. Flagged as an
     addition, exactly like the decline-grid risk controls were.
  6. COSTS: config.SLIPPAGE_PCT (0.15%) deducted per leg on every entry,
     trim, and liquidation.
  7. BASELINES (both frozen; raw returns are never read in isolation):
     (a) same ticker, same entry, buy-and-hold to the same 63-session
         horizon with the same entry/exit slippage -- isolates what the
         GRID adds versus just buying the dip;
     (b) the universe equal-weight mean 63-session next-open-to-open
         return over the same entry dates -- does picking the sharpest
         decliner beat an average stock at all?

HONESTY NOTES (standing project rules): episodes overlap heavily (up to
~63 concurrent), so per-episode observations are NOT independent -- no
significance is claimed and none should be inferred; this is a single
frozen spec (no parameter sweep), but it is still one more look at the
same universe, whose measured detectable-effect floor exceeds any
plausible real edge; results are exploratory, not evidence, and change
nothing about live or paper authority.

Run with: python scripts/run_sharpest_decline_dip_2026_08_05.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config import LOOKBACK_DAYS, SLIPPAGE_PCT, UNIVERSE
from data.market_data import fetch_historical

ENTRY_NOTIONAL = 10_000.0
TRIM_TRIGGER = 0.05
TRIM_FRACTION = 0.05
MAX_HOLD_SESSIONS = 63
SLIP = SLIPPAGE_PCT  # one-way, per leg


def _aligned_frames(data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes = pd.DataFrame({t: df["close"] for t, df in data.items()}).sort_index()
    opens = pd.DataFrame({t: df["open"] for t, df in data.items()}).sort_index()
    return closes, opens


def _simulate_episode(
    closes: pd.Series, opens: pd.Series, entry_index: int
) -> dict | None:
    """One $10k episode from entry open to trim-ratcheted liquidation."""
    # The frozen comparison is a 63-session horizon. Near the right edge,
    # silently shortening that horizon pools one- and two-session episodes
    # into statistics labeled "63-session" and gives them incomparable
    # opportunity to hit the trim grid. Refuse underfilled outcomes.
    if (
        entry_index < 0
        or entry_index + MAX_HOLD_SESSIONS >= len(opens)
        or entry_index + MAX_HOLD_SESSIONS >= len(closes)
    ):
        return None
    entry_price = opens.iloc[entry_index] * (1 + SLIP)
    if not np.isfinite(entry_price) or entry_price <= 0:
        return None
    shares = ENTRY_NOTIONAL / entry_price
    reference = entry_price
    proceeds = 0.0
    trims = 0
    last_index = entry_index + MAX_HOLD_SESSIONS
    day = entry_index
    while day < last_index:
        close = closes.iloc[day]
        if np.isfinite(close) and close / reference - 1 >= TRIM_TRIGGER:
            fill = opens.iloc[day + 1] * (1 - SLIP)
            if np.isfinite(fill) and fill > 0:
                sold = shares * TRIM_FRACTION
                proceeds += sold * fill
                shares -= sold
                reference = fill
                trims += 1
        day += 1
    exit_price = opens.iloc[last_index] * (1 - SLIP)
    if not np.isfinite(exit_price) or exit_price <= 0:
        return None
    proceeds += shares * exit_price
    net_return_pct = (proceeds / ENTRY_NOTIONAL - 1) * 100

    # Baseline (a): same entry, no grid, same horizon and slippage.
    hold_return_pct = (
        (opens.iloc[last_index] * (1 - SLIP)) / entry_price - 1
    ) * 100
    return {
        "net_return_pct": net_return_pct,
        "hold_return_pct": hold_return_pct,
        "trims": trims,
        "sessions_held": last_index - entry_index,
    }


def main() -> None:
    print(
        f"Fetching {len(UNIVERSE)} tickers x {LOOKBACK_DAYS} sessions "
        "(real data; several minutes)..."
    )
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"{len(data)} tickers returned data.")
    closes, opens = _aligned_frames(data)
    daily_returns = closes.pct_change()

    episodes: list[dict] = []
    dates = closes.index
    for t in range(1, len(dates) - 2):
        row = daily_returns.iloc[t].dropna()
        if row.empty:
            continue
        # Frozen pick: sharpest one-day decline, alphabetical tie-break.
        worst = row.sort_index().idxmin()
        if not np.isfinite(row[worst]) or row[worst] >= 0:
            continue  # no decliner that day -- nothing matches the spec
        entry_index = t + 1
        # Same full-horizon gate as the episode: refuse truncated windows
        # and refuse episodes whose universe baseline cannot be formed on
        # the identical observation set.
        if entry_index + MAX_HOLD_SESSIONS >= len(dates):
            continue
        last_index = entry_index + MAX_HOLD_SESSIONS
        entry_opens = opens.iloc[entry_index] * (1 + SLIP)
        exit_opens = opens.iloc[last_index] * (1 - SLIP)
        window = (exit_opens / entry_opens - 1) * 100
        window = window.replace([np.inf, -np.inf], np.nan).dropna()
        if window.empty:
            continue
        ticker = str(worst)
        episode = _simulate_episode(closes[ticker], opens[ticker], entry_index)
        if episode is None:
            continue
        episode["ticker"] = ticker
        episode["entry_date"] = dates[entry_index].date().isoformat()
        episode["picked_decline_pct"] = round(row[worst] * 100, 2)
        episode["universe_return_pct"] = float(window.mean())
        episode["universe_ticker_count"] = int(len(window))
        episodes.append(episode)

    frame = pd.DataFrame(episodes)
    print(f"\nEpisodes simulated: {len(frame)}")
    if frame.empty:
        print("Nothing to report.")
        return

    def _describe(label: str, series: pd.Series) -> None:
        print(
            f"{label}: mean {series.mean():+.2f}%  median {series.median():+.2f}%  "
            f"positive rate {(series > 0).mean() * 100:.1f}%  "
            f"p5 {series.quantile(0.05):+.2f}%  p95 {series.quantile(0.95):+.2f}%"
        )

    print("\n=== Strategy (dip + 5%-trim ratchet, 63-session cap) ===")
    _describe("grid episodes", frame["net_return_pct"])
    print(f"mean trims per episode: {frame['trims'].mean():.2f}")
    print(
        "sum of overlapping $10k episode P&L (NOT a capital-constrained "
        f"portfolio; up to ~{MAX_HOLD_SESSIONS} concurrent): "
        f"${(frame['net_return_pct'] / 100 * ENTRY_NOTIONAL).sum():,.0f}"
    )

    print("\n=== Baseline (a): same picks, buy-and-hold, no grid ===")
    _describe("hold episodes", frame["hold_return_pct"])

    print("\n=== Baseline (b): universe average over the same windows ===")
    _describe("universe windows", frame["universe_return_pct"])
    print(
        "universe coverage tickers/episode: "
        f"min {frame['universe_ticker_count'].min()}  "
        f"median {frame['universe_ticker_count'].median():.0f}  "
        f"max {frame['universe_ticker_count'].max()} "
        f"(of {len(UNIVERSE)} requested)"
    )

    print("\n=== Paired diffs on identical episodes ===")
    _describe("grid - hold", frame["net_return_pct"] - frame["hold_return_pct"])
    _describe(
        "hold - universe",
        frame["hold_return_pct"] - frame["universe_return_pct"],
    )
    _describe(
        "grid - universe",
        frame["net_return_pct"] - frame["universe_return_pct"],
    )
    print(
        "paired beat rates: "
        f"P(hold>universe)="
        f"{(frame['hold_return_pct'] > frame['universe_return_pct']).mean() * 100:.1f}%  "
        f"P(grid>universe)="
        f"{(frame['net_return_pct'] > frame['universe_return_pct']).mean() * 100:.1f}%"
    )

    print(
        "\nHONESTY: episodes overlap heavily and are not independent; no "
        "significance is claimed. Single frozen spec, still one more look "
        "at a universe whose detectable-effect floor exceeds plausible "
        "edges. Survivorship-biased universe. Adjusted yfinance history is "
        "exploratory (point_in_time_data=false). Positive-rate rows above "
        "are same-series fractions and are not a paired beat rate; use the "
        "paired section for pick-vs-universe comparisons. Exploratory "
        "only -- not evidence, not a trading authorization."
    )


if __name__ == "__main__":
    main()
