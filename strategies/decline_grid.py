"""
User-specified strategy (dictated 2026-08-04, frozen before any result was
observed): buy a stock making a fresh 3-month low after a sharp recent
decline, then trade a percentage grid around the position -- trim on
rallies, average down on further drops -- until it fully exits, stops
out, or hits a max hold period.

STEP 1 -- ENTRY FILTER. A ticker qualifies on a given date when, using
only that date's own completed close and prior history:
  (a) today's close is a new `low_lookback_days`-day low (3 months ~= 63
      trading days, this project's LOOKBACK convention elsewhere uses
      21 trading days/month)
  (b) AND cumulative close-to-close return over the trailing
      `window_days` (the "given period of time" the user asked to make
      testable -- 1/2/3 weeks = 5/10/15 trading days) is worse than
      -`drop_threshold_pct` (10% default)
The user's conditions 2 ("has been dropping for a period") and 3 ("drop
rate exceeds 10%") are the SAME cumulative-return check parameterized by
one window, not two independent checks -- condition 2 supplies the
timeframe, condition 3 supplies the threshold for that timeframe.

STEP 2 -- ENTRY. $10,000 notional, executed at the NEXT trading day's
open after the close that satisfied Step 1 (this project's realistic
"next_open" convention: you cannot know a day's own final close in time
to also transact at that same close).

STEP 3 -- THE GRID (frozen decisions after clarifying with the user,
2026-08-04):
  - Reference price RESETS after every trigger (a ratchet, not a fixed
    grid from the original entry) -- explicitly the user's chosen
    reading of "Step 4: Repeat".
  - Every day, compare that day's close to the current reference price:
      close/reference - 1 >= +0.05  -> SELL `trim_pct` of CURRENT SHARES
      close/reference - 1 <= -0.05  -> BUY more, sized at `trim_pct` of
                                        CURRENT POSITION VALUE (shares *
                                        reference price) -- buy and sell
                                        sizing bases are DIFFERENT
                                        (shares vs. value) because "sell
                                        10-20%" of shares you don't have
                                        enough of is undefined, while
                                        the natural symmetric reading of
                                        "buy 10-20%" is 10-20% MORE
                                        exposure, i.e. of current value.
                                        This is a genuine, documented
                                        interpretation call the user's
                                        spec left open.
    Both execute at the FOLLOWING day's open (same next_open discipline
    as entry), and the reference price becomes that fill price.
  - `trim_pct` in {0.10, 0.20} -- BOTH tested as independently
    pre-registered primaries (the user's explicit choice over freezing
    one midpoint), not one picked after seeing which looks better.

RISK CONTROLS ADDED BY THIS PROJECT, NOT IN THE USER'S ORIGINAL
DESCRIPTION (frozen 2026-08-04, before any result was observed; the user
was told explicitly that these are additions, not literal requests):
  - position_cap_multiple = 2.0 -- total dollars ever deployed buying
    into this episode is capped at 2x the initial $10,000 ($20,000). A
    buy that would exceed the cap is sized down to whatever room is
    left; if none is left, the buy is skipped (logged, not silently
    dropped) and the ratchet does NOT reset (no trade happened).
    WITHOUT this, the strategy is unbounded averaging-down on names
    ALREADY confirmed to be sharp decliners at a fresh low -- exactly
    the failure mode strategies/trend_vol_rotation.py's module docstring
    already warns about for a near-identical trim-the-rally/buy-the-dip
    mechanic ("keeps catching a falling knife during declines").
  - stop_loss_pct = 30.0 -- if close/average_cost_basis - 1 <=
    -stop_loss_pct/100 on any day, the ENTIRE remaining position is
    liquidated at the next open. average_cost_basis is the share-
    weighted average of every buy fill so far, tracked SEPARATELY from
    the ratchet's reference price.
  - max_hold_days = 252 (~1 trading year) -- if still open after this
    many trading days from entry, the entire remaining position is
    liquidated at the next open regardless of price.
  These are circuit breakers, not alpha assumptions -- they cap how bad
  a single episode can get without changing what a "good" episode looks
  like.

WHAT THIS MODULE DOES NOT MODEL (documented limitations, not silent
gaps):
  - Trigger detection uses DAILY CLOSES only, not intraday highs/lows.
    A name that touches +7% intraday and closes +3% would NOT trigger a
    sell here, though a real resting limit order might have filled
    intraday. This likely UNDERSTATES trigger frequency on high-range
    days. Using intraday extremes instead would require fabricating an
    intraday fill assumption this project has no data to support
    (daily OHLC only) -- the same reasoning behind why
    entry_timing="next_open" is this project's default over
    "same_close" elsewhere: realism over optimism, even where it costs
    some upside.
  - Each episode is capitalized independently at its own $10,000-
    $20,000 (matching backtest/engine.py's run_backtest() row-level
    philosophy: every signal gets its own capital), NOT drawn from one
    shared account. A real account has one cash pool; if this entry
    filter fires on many tickers at once (plausible in a broad
    drawdown, since "sharp decliner at a fresh low" is exactly what a
    lot of stocks look like simultaneously in a selloff), a real trader
    could not fund every episode at full size simultaneously. This is
    the same documented gap backtest/portfolio_simulator.py's docstring
    already flags for the plain scan_fn signals; it applies here too and
    is NOT re-solved by this module.
"""
from __future__ import annotations

import pandas as pd

from data.research_input_contracts import (
    require_finite_number,
    require_index_window,
    require_nonnegative_int,
    require_positive_int,
    require_positive_number,
    require_price_frame,
    require_price_frame_mapping,
    require_rate,
)

RESULT_COLUMNS = [
    "ticker", "entry_signal_date", "entry_date", "exit_date",
    "n_buys", "n_sells", "total_deployed", "total_returned",
    "net_return_pct", "buy_and_hold_baseline_pct", "edge_vs_buy_and_hold_pct",
    "hold_days", "outcome",
]

LOW_LOOKBACK_DAYS = 63          # ~3 trading months
WINDOW_DAYS = 10                # primary: ~2 trading weeks (5/15 = sensitivity)
DROP_THRESHOLD_PCT = 10.0
TRIM_PCT = 0.15                 # caller overrides with 0.10 / 0.20 for the two primaries
TRIGGER_PCT = 0.05
POSITION_CAP_MULTIPLE = 2.0
STOP_LOSS_PCT = 30.0
MAX_HOLD_DAYS = 252
INITIAL_NOTIONAL = 10_000.0


def find_entry_dates(
    df: pd.DataFrame,
    low_lookback_days: int = LOW_LOOKBACK_DAYS,
    window_days: int = WINDOW_DAYS,
    drop_threshold_pct: float = DROP_THRESHOLD_PCT,
) -> list[int]:
    """
    Row indices (into `df`) where this ticker satisfies Step 1 on that
    row's own close: a new `low_lookback_days`-day low AND a trailing
    `window_days` cumulative return worse than -drop_threshold_pct.
    Every quantity uses only data up to and including that row -- causal,
    same discipline as every other signal in this project.
    """
    require_price_frame(df, name="df", required_columns=("close",))
    low_lookback_days = require_positive_int(low_lookback_days, name="low_lookback_days")
    window_days = require_positive_int(window_days, name="window_days")
    drop_threshold_pct = require_finite_number(
        drop_threshold_pct,
        name="drop_threshold_pct",
        minimum=0.0,
        maximum=100.0,
    )
    close = df["close"]
    n = len(close)
    entries = []
    min_idx = max(low_lookback_days, window_days)
    for i in range(min_idx, n):
        prior_window = close.iloc[i - low_lookback_days + 1 : i]  # excludes today
        if not prior_window.empty and close.iloc[i] > prior_window.min():
            continue  # today is not a new low
        start_price = close.iloc[i - window_days]
        if start_price <= 0:
            continue
        cum_return_pct = (close.iloc[i] / start_price - 1) * 100
        if cum_return_pct > -drop_threshold_pct:
            continue  # decline not steep enough over this window
        entries.append(i)
    return entries


def simulate_episode(
    df: pd.DataFrame,
    signal_idx: int,
    trim_pct: float = TRIM_PCT,
    trigger_pct: float = TRIGGER_PCT,
    position_cap_multiple: float = POSITION_CAP_MULTIPLE,
    stop_loss_pct: float = STOP_LOSS_PCT,
    max_hold_days: int = MAX_HOLD_DAYS,
    initial_notional: float = INITIAL_NOTIONAL,
    slippage_pct: float = 0.0015,
) -> dict | None:
    """
    Simulate one full trade episode starting from the entry signal at
    `signal_idx` (a row where find_entry_dates() fired). Returns None if
    there isn't even one more trading day to enter on (signal on the
    last available bar). Every fill is at the FOLLOWING day's open
    (see module docstring); every trigger is evaluated on daily closes.
    """
    require_price_frame(df, name="df", required_columns=("open", "close"))
    signal_idx = require_nonnegative_int(signal_idx, name="signal_idx")
    n = len(df)
    if signal_idx >= n:
        raise ValueError(f"signal_idx must be less than data length {n}, got {signal_idx}")
    trim_pct = require_finite_number(
        trim_pct,
        name="trim_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=1.0,
    )
    trigger_pct = require_finite_number(
        trigger_pct,
        name="trigger_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=1.0,
    )
    position_cap_multiple = require_finite_number(
        position_cap_multiple,
        name="position_cap_multiple",
        minimum=1.0,
    )
    stop_loss_pct = require_finite_number(
        stop_loss_pct,
        name="stop_loss_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=100.0,
    )
    max_hold_days = require_positive_int(max_hold_days, name="max_hold_days")
    initial_notional = require_positive_number(initial_notional, name="initial_notional")
    slippage_pct = require_rate(slippage_pct, name="slippage_pct")
    entry_idx = signal_idx + 1
    if entry_idx >= n:
        return None

    close = df["close"]
    open_ = df["open"]

    def _fill(raw_price: float, buying: bool) -> float:
        return raw_price * (1 + slippage_pct) if buying else raw_price * (1 - slippage_pct)

    entry_fill = _fill(float(open_.iloc[entry_idx]), buying=True)
    shares = initial_notional / entry_fill
    cash_out = initial_notional   # gross dollars spent buying, cap accounting uses this
    cash_in = 0.0                 # gross dollars received selling
    # Weighted-average cost basis of REMAINING shares. Selling a fraction
    # of the position does not change the average cost of what's left --
    # it must shrink cost_basis_dollars by that same fraction, or avg_cost
    # (= cost_basis_dollars / shares) inflates every time shares shrink
    # from a sell, spuriously tripping the stop-loss on profitable
    # episodes (caught by this project's own synthetic sanity check:
    # episodes showing +37% net return were mislabeled "stop_loss").
    cost_basis_dollars = initial_notional
    reference_price = entry_fill
    n_buys, n_sells = 1, 0
    position_cap = initial_notional * position_cap_multiple
    outcome = None
    exit_price_column = None
    exit_idx = entry_idx

    j = entry_idx
    while j < n:
        avg_cost = cost_basis_dollars / shares if shares > 0 else None
        if avg_cost is not None and close.iloc[j] / avg_cost - 1 <= -stop_loss_pct / 100:
            outcome = "stop_loss"
            has_next_session = j + 1 < n
            exit_idx = j + 1 if has_next_session else j
            exit_price_column = "open" if has_next_session else "close"
            fill_price = _fill(float(df[exit_price_column].iloc[exit_idx]), buying=False)
            cash_in += shares * fill_price
            n_sells += 1
            shares = 0.0
            break

        if j - entry_idx >= max_hold_days:
            outcome = "max_hold"
            has_next_session = j + 1 < n
            exit_idx = j + 1 if has_next_session else j
            exit_price_column = "open" if has_next_session else "close"
            fill_price = _fill(float(df[exit_price_column].iloc[exit_idx]), buying=False)
            cash_in += shares * fill_price
            n_sells += 1
            shares = 0.0
            break

        move = close.iloc[j] / reference_price - 1
        if move >= trigger_pct:
            if j + 1 >= n:
                outcome = "forced_end_no_more_data"
                exit_idx = j
                exit_price_column = "close"
                fill_price = _fill(float(close.iloc[j]), buying=False)
                cash_in += shares * fill_price
                n_sells += 1
                shares = 0.0
                break
            fill_price = _fill(float(open_.iloc[j + 1]), buying=False)
            sell_shares = shares * trim_pct
            cash_in += sell_shares * fill_price
            shares -= sell_shares
            cost_basis_dollars *= (1 - trim_pct)  # avg cost per remaining share is unchanged by a proportional sale
            reference_price = fill_price
            n_sells += 1
            # Selling a FRACTION of current shares each trigger decays
            # geometrically and mathematically never reaches exactly
            # zero -- "fully sold" is reached only once the residual
            # position's dollar value is negligible, not literally zero.
            if shares * reference_price <= 1.0:
                outcome = "fully_sold"
                exit_idx = j + 1
                exit_price_column = "open"
                shares = 0.0
                break
        elif move <= -trigger_pct:
            if j + 1 >= n:
                pass  # no room to execute the add; just keep monitoring is moot, loop will end below
            else:
                current_value = shares * reference_price
                desired_add = current_value * trim_pct
                room = max(0.0, position_cap - cash_out)
                add_value = min(desired_add, room)
                if add_value > 0:
                    fill_price = _fill(float(open_.iloc[j + 1]), buying=True)
                    add_shares = add_value / fill_price
                    shares += add_shares
                    cash_out += add_value
                    cost_basis_dollars += add_value
                    reference_price = fill_price
                    n_buys += 1
        j += 1
        exit_idx = j

    if outcome is None:
        # Ran off the end of available data still holding shares.
        outcome = "forced_end_no_more_data"
        last_idx = min(exit_idx, n - 1)
        exit_price_column = "close"
        fill_price = _fill(float(close.iloc[last_idx]), buying=False)
        cash_in += shares * fill_price
        n_sells += 1
        shares = 0.0
        exit_idx = last_idx

    net_return_pct = (cash_in - cash_out) / cash_out * 100 if cash_out > 0 else 0.0
    exit_idx = min(exit_idx, n - 1)
    entry_idx, exit_idx = require_index_window(
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        length=n,
    )

    return {
        "entry_signal_date": df.index[signal_idx],
        "entry_date": df.index[entry_idx],
        "exit_date": df.index[exit_idx],
        "n_buys": n_buys,
        "n_sells": n_sells,
        "total_deployed": round(cash_out, 2),
        "total_returned": round(cash_in, 2),
        "net_return_pct": round(net_return_pct, 3),
        "hold_days": exit_idx - entry_idx,
        "outcome": outcome,
        "exit_price_column": exit_price_column,
    }


def simulate_buy_and_hold(
    df: pd.DataFrame,
    entry_idx: int,
    exit_idx: int,
    initial_notional: float = INITIAL_NOTIONAL,
    slippage_pct: float = 0.0015,
    *,
    exit_price_column: str,
) -> float:
    """
    Net return (%) of simply buying at entry_idx's open and selling at
    the explicitly supplied exit price column, matching the episode's own
    forced/triggered exit -- no rebalancing at all. This is
    the baseline the grid strategy's edge is measured against: does the
    active buy-the-dip/sell-the-rally ladder actually add value over
    just holding the SAME entry through the SAME window, or is any
    apparent profit just this ticker's own reversal/bounce doing the
    work regardless of how it's traded?
    """
    if exit_price_column not in {"open", "close"}:
        raise ValueError("exit_price_column must be 'open' or 'close'")
    require_price_frame(
        df,
        name="df",
        required_columns=("open", exit_price_column),
    )
    entry_idx, exit_idx = require_index_window(
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        length=len(df),
    )
    initial_notional = require_positive_number(initial_notional, name="initial_notional")
    slippage_pct = require_rate(slippage_pct, name="slippage_pct")
    entry_fill = float(df["open"].iloc[entry_idx]) * (1 + slippage_pct)
    exit_fill = float(df[exit_price_column].iloc[exit_idx]) * (1 - slippage_pct)
    return (exit_fill - entry_fill) / entry_fill * 100


def run_decline_grid_backtest(
    data: dict[str, pd.DataFrame],
    trim_pct: float = TRIM_PCT,
    window_days: int = WINDOW_DAYS,
    low_lookback_days: int = LOW_LOOKBACK_DAYS,
    drop_threshold_pct: float = DROP_THRESHOLD_PCT,
    trigger_pct: float = TRIGGER_PCT,
    position_cap_multiple: float = POSITION_CAP_MULTIPLE,
    stop_loss_pct: float = STOP_LOSS_PCT,
    max_hold_days: int = MAX_HOLD_DAYS,
    initial_notional: float = INITIAL_NOTIONAL,
    slippage_pct: float = 0.0015,
) -> pd.DataFrame:
    """
    Walk every ticker's own history once: find every Step-1 entry date,
    simulate the full grid episode from each one (skipping new entries
    while a prior episode on the SAME ticker is still open -- one open
    episode per ticker at a time, matching backtest/portfolio_simulator.py's
    existing convention), and return one row per completed episode.
    """
    require_price_frame_mapping(
        data,
        name="data",
        required_columns=("open", "close"),
    )
    trim_pct = require_finite_number(
        trim_pct,
        name="trim_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=1.0,
    )
    window_days = require_positive_int(window_days, name="window_days")
    low_lookback_days = require_positive_int(low_lookback_days, name="low_lookback_days")
    drop_threshold_pct = require_finite_number(
        drop_threshold_pct,
        name="drop_threshold_pct",
        minimum=0.0,
        maximum=100.0,
    )
    trigger_pct = require_finite_number(
        trigger_pct,
        name="trigger_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=1.0,
    )
    position_cap_multiple = require_finite_number(
        position_cap_multiple,
        name="position_cap_multiple",
        minimum=1.0,
    )
    stop_loss_pct = require_finite_number(
        stop_loss_pct,
        name="stop_loss_pct",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=100.0,
    )
    max_hold_days = require_positive_int(max_hold_days, name="max_hold_days")
    initial_notional = require_positive_number(initial_notional, name="initial_notional")
    slippage_pct = require_rate(slippage_pct, name="slippage_pct")
    rows = []
    for ticker, df in data.items():
        entry_indices = find_entry_dates(df, low_lookback_days, window_days, drop_threshold_pct)
        next_available_idx = 0
        for idx in entry_indices:
            if idx < next_available_idx:
                continue  # a prior episode on this ticker is still open through this date
            episode = simulate_episode(
                df, idx,
                trim_pct=trim_pct, trigger_pct=trigger_pct,
                position_cap_multiple=position_cap_multiple, stop_loss_pct=stop_loss_pct,
                max_hold_days=max_hold_days, initial_notional=initial_notional,
                slippage_pct=slippage_pct,
            )
            if episode is None:
                continue
            entry_idx_actual = idx + 1
            exit_idx_actual = df.index.get_loc(episode["exit_date"])
            baseline_pct = simulate_buy_and_hold(
                df, entry_idx_actual, exit_idx_actual,
                initial_notional=initial_notional, slippage_pct=slippage_pct,
                exit_price_column=episode["exit_price_column"],
            )
            episode["ticker"] = ticker
            episode["buy_and_hold_baseline_pct"] = round(baseline_pct, 3)
            episode["edge_vs_buy_and_hold_pct"] = round(episode["net_return_pct"] - baseline_pct, 3)
            rows.append(episode)
            exit_date = episode["exit_date"]
            next_available_idx = df.index.get_loc(exit_date) + 1

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return pd.DataFrame(rows)[RESULT_COLUMNS].sort_values("entry_signal_date").reset_index(drop=True)
