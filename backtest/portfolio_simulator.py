"""
Event-driven, capital-constrained portfolio simulator for backtest/engine.py's
row-level signal scanner.

Context (see memory: project_execution_realism_gaps, gap #2): run_backtest()
scores every flagged signal as an independent bet at its own fixed notional,
which ignores that a real account has ONE shared cash pool and that signals
cluster on the same dates (momentum alone flags ~19-20 tickers/day in this
project's universe) -- thousands of "overlapping trades" can't each get
their own capital in reality. simulate_portfolio() answers "what would
actually happen running ONE account, sized against real cash and a max
concurrent-position cap, against this scanner" -- an equity/drawdown curve,
not a bag of independent row returns.

Reuses scan_fn the same way run_backtest() does (same contract: a DataFrame
with ticker/date/direction/etc.), so any signal already written for this
project's scanner works here unchanged, with no separate simulator-only
signal logic to drift out of sync.

SCOPE of this first version (deliberately not the full wishlist from
project_execution_realism_gaps):
  - Cash and position-slot capacity are reserved AT SIGNAL TIME (the date
    the scanner fires), not at actual entry time (which may be the next
    trading day's open, under entry_timing="next_open"). This is a
    conservative simplification -- it can only UNDER-count how much
    cash/capacity is actually available on the real entry day, never
    over-count and accidentally overspend.
  - One open position per ticker at a time; a repeat signal on an already-
    held ticker is skipped, not pyramided.
  - Equal-weight sizing (position_size_pct of CURRENT equity at signal
    time) capped by whatever cash is actually left -- no volatility-based
    or Kelly-style sizing.
  - Exit is purely hold_days-based, exactly like run_backtest() -- there is
    NO intraday stop-loss execution modeled here yet. A position that's
    still open at the very end of the data is force-closed at the last
    available price so the equity curve and trade log are always fully
    realized.
  - Slippage is applied as a price haircut on both legs (buy slightly
    above, sell slightly below the quoted price), the dollar-accounting
    equivalent of run_backtest()'s "round-trip slippage" convention.

Has NOT yet been used to re-run any of this project's existing REJECTED
findings -- everything in research_findings.json still reflects the
row-level, unconstrained scoring in backtest/engine.py. This module exists
so a FUTURE signal test can be portfolio-realistic from day one, not to
silently revisit a past verdict.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from config import BACKTEST_HOLD_DAYS, RETURN_Z_THRESHOLD, ROLLING_WINDOW, SLIPPAGE_PCT, VOLUME_Z_THRESHOLD
from signals.scanner import scan_dips_and_ups
from backtest.engine import _resolve_scan_kwargs

TRADE_LOG_COLUMNS = [
    "ticker", "direction", "signal_date", "entry_date", "entry_price",
    "exit_date", "exit_price", "shares", "position_value", "net_return_pct", "forced_close",
]


def _cagr_pct(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2 or equity_curve.iloc[0] <= 0:
        return 0.0
    n_years = len(equity_curve) / 252
    if n_years <= 0:
        return 0.0
    return (float(equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / n_years) - 1) * 100


def _max_drawdown_pct(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min()) * 100


def simulate_portfolio(
    data: dict[str, pd.DataFrame],
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    hold_days: int = BACKTEST_HOLD_DAYS,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    entry_timing: str = "next_open",
    slippage_pct: float = SLIPPAGE_PCT,
    initial_cash: float = 100_000.0,
    max_concurrent_positions: int = 20,
    position_size_pct: float = 0.05,
    direction_filter: tuple[str, ...] | None = None,
) -> dict:
    """
    Walk every date in the universe in order, running `scan_fn` exactly as
    run_backtest() does. Each accepted signal becomes ONE position sized at
    `position_size_pct` of current equity (capped by available cash),
    subject to `max_concurrent_positions` open at once. Returns:

      - equity_curve: pd.Series (date-indexed total account value)
      - trade_log: pd.DataFrame (TRADE_LOG_COLUMNS)
      - cagr_pct, max_drawdown_pct: computed from equity_curve
      - n_trades, n_signals_seen, n_signals_skipped_capacity, n_signals_skipped_cash
      - final_cash, final_equity

    `entry_timing` follows run_backtest()'s convention: "same_close" enters
    and exits at the signal date's own close; "next_open" enters at the
    next trading day's open and exits `hold_days` opens later. See this
    module's docstring for what "at signal time" reservation means for cash
    accounting under next_open.
    """
    if entry_timing not in ("same_close", "next_open"):
        raise ValueError(f"entry_timing must be 'same_close' or 'next_open', got {entry_timing!r}")
    if not data:
        return _empty_result(initial_cash)

    kwargs = _resolve_scan_kwargs(scan_fn, scan_kwargs, return_z_threshold, volume_z_threshold)
    all_dates = sorted(set().union(*(df.index for df in data.values())))
    tail_buffer = hold_days + 1 if entry_timing == "next_open" else hold_days
    usable_dates = all_dates[ROLLING_WINDOW : len(all_dates) - tail_buffer] if tail_buffer > 0 else all_dates[ROLLING_WINDOW:]
    if not usable_dates:
        return _empty_result(initial_cash)

    cash = initial_cash
    open_positions: dict[str, dict] = {}  # ticker -> position dict
    trade_log: list[dict] = []
    equity_dates: list = []
    equity_values: list[float] = []
    n_signals_seen = 0
    n_skipped_capacity = 0
    n_skipped_cash = 0

    def _mark_to_market(as_of) -> float:
        value = cash
        for ticker, pos in open_positions.items():
            df = data[ticker]
            if as_of in df.index:
                price = float(df["close"].loc[as_of])
            else:
                price = pos["last_known_price"]
            pos["last_known_price"] = price
            value += pos["shares"] * price
        return value

    def _close_position(ticker: str, pos: dict, exit_date, exit_price: float, forced: bool) -> None:
        nonlocal cash
        net_exit_price = exit_price * (1 - slippage_pct / 100)
        proceeds = pos["shares"] * net_exit_price
        cash += proceeds
        net_return_pct = (net_exit_price - pos["net_entry_price"]) / pos["net_entry_price"] * 100
        trade_log.append(
            {
                "ticker": ticker,
                "direction": pos["direction"],
                "signal_date": pos["signal_date"],
                "entry_date": pos["entry_date"],
                "entry_price": round(pos["net_entry_price"], 2),
                "exit_date": exit_date,
                "exit_price": round(net_exit_price, 2),
                "shares": pos["shares"],
                "position_value": round(pos["position_value"], 2),
                "net_return_pct": round(net_return_pct, 3),
                "forced_close": forced,
            }
        )

    for as_of in usable_dates:
        # 1. Close any positions whose exit date has arrived.
        for ticker in [t for t, pos in open_positions.items() if pos["exit_date"] <= as_of]:
            pos = open_positions.pop(ticker)
            df = data[ticker]
            exit_price = pos["planned_exit_price"] if pos["exit_date"] in df.index else pos["last_known_price"]
            _close_position(ticker, pos, pos["exit_date"], exit_price, forced=False)

        # 2. Evaluate new signals.
        signals = scan_fn(data, as_of=as_of, **kwargs)
        if not signals.empty:
            if direction_filter is not None:
                signals = signals[signals["direction"].isin(direction_filter)]
            for _, sig in signals.iterrows():
                n_signals_seen += 1
                ticker = sig["ticker"]
                if ticker in open_positions:
                    continue
                df = data[ticker]
                if as_of not in df.index:
                    continue
                idx = df.index.get_loc(as_of)
                if entry_timing == "same_close":
                    entry_idx, exit_idx, entry_col, exit_col = idx, idx + hold_days, "close", "close"
                else:
                    entry_idx, exit_idx, entry_col, exit_col = idx + 1, idx + 1 + hold_days, "open", "open"
                if exit_idx >= len(df):
                    continue  # not enough forward history to ever close this one

                if len(open_positions) >= max_concurrent_positions:
                    n_skipped_capacity += 1
                    continue

                current_equity = _mark_to_market(as_of)
                position_value = min(current_equity * position_size_pct, cash)
                if position_value <= 0:
                    n_skipped_cash += 1
                    continue

                raw_entry_price = float(df[entry_col].iloc[entry_idx])
                net_entry_price = raw_entry_price * (1 + slippage_pct / 100)
                shares = position_value / net_entry_price
                if shares <= 0:
                    continue

                cash -= shares * net_entry_price
                open_positions[ticker] = {
                    "direction": sig["direction"],
                    "signal_date": as_of,
                    "entry_date": df.index[entry_idx],
                    "net_entry_price": net_entry_price,
                    "shares": shares,
                    "position_value": position_value,
                    "exit_date": df.index[exit_idx],
                    "planned_exit_price": float(df[exit_col].iloc[exit_idx]),
                    "last_known_price": raw_entry_price,
                }

        equity_dates.append(as_of)
        equity_values.append(_mark_to_market(as_of))

    # Force-close anything still open at the end so the curve/log are fully realized.
    last_date = usable_dates[-1]
    for ticker, pos in list(open_positions.items()):
        _close_position(ticker, pos, last_date, pos["last_known_price"], forced=True)
    open_positions.clear()
    if equity_values:
        equity_values[-1] = cash

    equity_curve = pd.Series(equity_values, index=pd.Index(equity_dates, name="date"))
    trade_df = pd.DataFrame(trade_log, columns=TRADE_LOG_COLUMNS) if trade_log else pd.DataFrame(columns=TRADE_LOG_COLUMNS)

    return {
        "equity_curve": equity_curve,
        "trade_log": trade_df,
        "cagr_pct": round(_cagr_pct(equity_curve), 2),
        "max_drawdown_pct": round(_max_drawdown_pct(equity_curve), 1),
        "n_trades": len(trade_log),
        "n_signals_seen": n_signals_seen,
        "n_signals_skipped_capacity": n_skipped_capacity,
        "n_signals_skipped_cash": n_skipped_cash,
        "final_cash": round(cash, 2),
        "final_equity": round(float(equity_curve.iloc[-1]), 2) if not equity_curve.empty else round(cash, 2),
    }


def _empty_result(initial_cash: float) -> dict:
    return {
        "equity_curve": pd.Series(dtype=float),
        "trade_log": pd.DataFrame(columns=TRADE_LOG_COLUMNS),
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "n_trades": 0,
        "n_signals_seen": 0,
        "n_signals_skipped_capacity": 0,
        "n_signals_skipped_cash": 0,
        "final_cash": round(initial_cash, 2),
        "final_equity": round(initial_cash, 2),
    }
