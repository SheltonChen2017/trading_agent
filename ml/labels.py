"""Point-in-time forward labels (strategy doc section 6.4).

Labels are computed independently of ml/features.py and joined only by
`(as_of_session, ticker)` at evaluation time -- never merged into the
feature frame here, so a labeling bug can never silently leak into a
feature. Every label row records the entry/exit sessions and prices it
used, and tail `as_of_session`s without a complete forward horizon are
dropped and counted (returned separately, not silently discarded) rather
than padded with a fabricated value.

Entry convention: "next tradable open" means the label enters at the OPEN
of the first session strictly after `as_of_session` -- consistent with the
rest of this project's `entry_timing="next_open"` convention
(backtest/research_report.py, assistant/context_builder.py). Exit
convention: the CLOSE of the session `horizon_sessions` sessions after
entry (a hold-to-close realized outcome, not the exit session's open).
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping

import pandas as pd


class LabelError(ValueError):
    """A price series cannot support point-in-time label construction."""


@dataclasses.dataclass(frozen=True)
class LabelRow:
    ticker: str
    as_of_session: str
    label_version: str
    entry_session: str
    entry_price: float
    exit_session: str
    exit_price: float
    value: float
    components: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "as_of_session": self.as_of_session,
            "label_version": self.label_version,
            "entry_session": self.entry_session,
            "entry_price": self.entry_price,
            "exit_session": self.exit_session,
            "exit_price": self.exit_price,
            "value": self.value,
            "components": dict(self.components),
        }


def _validate_price_index(close: pd.Series, name: str) -> None:
    if close.empty:
        raise LabelError(f"{name} is empty")
    if not close.index.is_monotonic_increasing:
        raise LabelError(f"{name} index is not sorted ascending")
    if close.index.has_duplicates:
        raise LabelError(f"{name} index has duplicate sessions")


def _next_open_exit_pairs(
    index: pd.Index, *, horizon_sessions: int
) -> tuple[list[int], list[int], int]:
    """For every possible `as_of` position, the (entry_idx, exit_idx) pair
    under the next-open-entry / horizon-sessions-later-close-exit
    convention, and how many tail rows were dropped for an incomplete
    horizon. `as_of` at position i enters at i+1 and exits at i+1+horizon;
    both must exist in `index`."""
    n = len(index)
    as_of_positions: list[int] = []
    entry_positions: list[int] = []
    exit_positions: list[int] = []
    dropped = 0
    for i in range(n):
        entry_idx = i + 1
        exit_idx = i + 1 + horizon_sessions
        if exit_idx >= n:
            dropped += 1
            continue
        as_of_positions.append(i)
        entry_positions.append(entry_idx)
        exit_positions.append(exit_idx)
    return as_of_positions, entry_positions, exit_positions, dropped


def compute_forward_excess_return_labels(
    ticker: str,
    close: pd.Series,
    open_: pd.Series,
    benchmark_close: pd.Series,
    *,
    horizon_sessions: int = 20,
    round_trip_cost_bps: float = 0.0,
    label_version: str = "forward_excess_return_20d_next_open_v1",
) -> tuple[tuple[LabelRow, ...], int]:
    """Strategy doc 6.4: "return from the next tradable open through the
    configured 20-session exit, less the aligned QQQ or SOXX return and
    round-trip cost." Returns (label_rows, dropped_tail_row_count)."""
    _validate_price_index(close, "close")
    _validate_price_index(open_, "open")
    _validate_price_index(benchmark_close, "benchmark_close")
    if horizon_sessions < 1:
        raise LabelError("horizon_sessions must be a positive integer")
    if round_trip_cost_bps < 0 or not math.isfinite(round_trip_cost_bps):
        raise LabelError("round_trip_cost_bps must be a non-negative finite number")
    if not close.index.equals(open_.index):
        raise LabelError("close and open must share the same session index")

    aligned_benchmark = benchmark_close.reindex(close.index)
    as_of_pos, entry_pos, exit_pos, dropped = _next_open_exit_pairs(
        close.index, horizon_sessions=horizon_sessions
    )
    cost_pct = round_trip_cost_bps / 10_000.0 * 100
    rows: list[LabelRow] = []
    for as_of_i, entry_i, exit_i in zip(as_of_pos, entry_pos, exit_pos):
        entry_price = float(open_.iloc[entry_i])
        exit_price = float(close.iloc[exit_i])
        benchmark_entry = aligned_benchmark.iloc[entry_i]
        benchmark_exit = aligned_benchmark.iloc[exit_i]
        if (
            entry_price <= 0
            or not math.isfinite(entry_price)
            or exit_price <= 0
            or not math.isfinite(exit_price)
            or pd.isna(benchmark_entry)
            or pd.isna(benchmark_exit)
            or benchmark_entry <= 0
        ):
            dropped += 1
            continue
        raw_return_pct = (exit_price / entry_price - 1.0) * 100
        benchmark_return_pct = (float(benchmark_exit) / float(benchmark_entry) - 1.0) * 100
        value = raw_return_pct - benchmark_return_pct - cost_pct
        rows.append(
            LabelRow(
                ticker=ticker,
                as_of_session=str(close.index[as_of_i].date()),
                label_version=label_version,
                entry_session=str(close.index[entry_i].date()),
                entry_price=entry_price,
                exit_session=str(close.index[exit_i].date()),
                exit_price=exit_price,
                value=round(value, 6),
                components={
                    "raw_return_pct": round(raw_return_pct, 6),
                    "benchmark_return_pct": round(benchmark_return_pct, 6),
                    "round_trip_cost_pct": round(cost_pct, 6),
                },
            )
        )
    return tuple(rows), dropped


def compute_forward_realized_vol_labels(
    ticker: str,
    close: pd.Series,
    *,
    horizon_sessions: int = 20,
    label_version: str = "forward_realized_vol_20d_v1",
) -> tuple[tuple[LabelRow, ...], int]:
    """Realized volatility (daily-return std, in percent -- same
    non-annualized convention as signals/regime.py's
    compute_trailing_market_volatility(), not reinvented here) over the
    `horizon_sessions` sessions following `as_of_session`."""
    _validate_price_index(close, "close")
    if horizon_sessions < 2:
        raise LabelError("horizon_sessions must be at least 2 to compute a volatility")

    n = len(close)
    dropped = 0
    rows: list[LabelRow] = []
    for i in range(n):
        window_start = i + 1
        window_end = i + 1 + horizon_sessions  # exclusive
        if window_end > n:
            dropped += 1
            continue
        window = close.iloc[window_start - 1 : window_end]  # include i's close as the base for pct_change
        daily_returns = window.pct_change().dropna()
        if len(daily_returns) < 2:
            dropped += 1
            continue
        vol_pct = float(daily_returns.std() * 100)
        if not math.isfinite(vol_pct):
            dropped += 1
            continue
        rows.append(
            LabelRow(
                ticker=ticker,
                as_of_session=str(close.index[i].date()),
                label_version=label_version,
                entry_session=str(close.index[window_start].date()),
                entry_price=float(close.iloc[window_start]),
                exit_session=str(close.index[window_end - 1].date()),
                exit_price=float(close.iloc[window_end - 1]),
                value=round(vol_pct, 6),
                components={"realized_vol_pct": round(vol_pct, 6)},
            )
        )
    return tuple(rows), dropped


def compute_forward_downside_threshold_labels(
    ticker: str,
    close: pd.Series,
    open_: pd.Series,
    benchmark_close: pd.Series,
    *,
    horizon_sessions: int = 20,
    round_trip_cost_bps: float = 0.0,
    downside_threshold_pct: float = 5.0,
    label_version: str = "forward_downside_threshold_v1",
) -> tuple[tuple[LabelRow, ...], int]:
    """Whether the forward excess return crosses a preregistered downside
    threshold. Built on top of compute_forward_excess_return_labels() --
    `downside_threshold_pct` must be fixed BEFORE looking at results
    (strategy doc 14: "research question and preregistered primary
    outcome"); the 5.0 default here is a placeholder, not a preregistered
    value, and callers doing real research must pass their own."""
    if downside_threshold_pct <= 0 or not math.isfinite(downside_threshold_pct):
        raise LabelError("downside_threshold_pct must be a positive finite number")
    excess_rows, dropped = compute_forward_excess_return_labels(
        ticker,
        close,
        open_,
        benchmark_close,
        horizon_sessions=horizon_sessions,
        round_trip_cost_bps=round_trip_cost_bps,
        label_version=label_version,
    )
    rows = tuple(
        dataclasses.replace(
            row,
            label_version=label_version,
            value=1.0 if row.value <= -downside_threshold_pct else 0.0,
            components={
                **row.components,
                "excess_return_pct": row.value,
                "downside_threshold_pct": downside_threshold_pct,
            },
        )
        for row in excess_rows
    )
    return rows, dropped
