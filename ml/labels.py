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

The BENCHMARK leg must use that identical timing -- benchmark OPEN at
entry, benchmark CLOSE at exit -- which is why
compute_forward_excess_return_labels() requires `benchmark_open` and does
not merely reuse `benchmark_close` at both ends. This is not a stylistic
preference. The first version of this module used the benchmark's close on
the entry session, so the ticker's return was measured open-to-close while
the benchmark's was measured close-to-close. That timing mismatch
contaminates the target with the benchmark's overnight move and can change
both the magnitude and sign of an excess-return label. It is target
misalignment, not feature/look-ahead leakage. Any empirical estimate of its
impact belongs in a reproducible research artifact that records the symbol,
date range, retrieval time, provider, and adjustment settings rather than in
this module-level contract.
"""
from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType
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

    def __post_init__(self) -> None:
        for name in ("ticker", "label_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LabelError(f"{name} must be a non-empty string")
        dates = {
            name: _parse_session(getattr(self, name), name)
            for name in ("as_of_session", "entry_session", "exit_session")
        }
        if dates["entry_session"] < dates["as_of_session"]:
            raise LabelError("entry_session must not precede as_of_session")
        if dates["exit_session"] < dates["entry_session"]:
            raise LabelError("exit_session must not precede entry_session")
        for name in ("entry_price", "exit_price"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LabelError(f"{name} must be a positive finite number")
            if value <= 0 or not math.isfinite(float(value)):
                raise LabelError(f"{name} must be a positive finite number")
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not math.isfinite(float(self.value))
        ):
            raise LabelError("value must be a finite number")
        if not isinstance(self.components, Mapping):
            raise LabelError("components must be a mapping")
        frozen_components: dict[str, float] = {}
        for key, value in self.components.items():
            if not isinstance(key, str) or not key.strip():
                raise LabelError("component names must be non-empty strings")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise LabelError(f"component {key!r} must be a finite number")
            frozen_components[key] = float(value)
        object.__setattr__(self, "components", MappingProxyType(frozen_components))

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


def _parse_session(value: str, name: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise LabelError(f"{name} must use canonical YYYY-MM-DD format")
    parsed = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != value:
        raise LabelError(f"{name} must use canonical YYYY-MM-DD format")
    return parsed


def _validate_price_index(series: pd.Series, name: str) -> None:
    if series.empty:
        raise LabelError(f"{name} is empty")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise LabelError(f"{name} index must be a DatetimeIndex of trading sessions")
    if series.index.hasnans:
        raise LabelError(f"{name} index contains NaT")
    if not series.index.is_monotonic_increasing:
        raise LabelError(f"{name} index is not sorted ascending")
    if series.index.has_duplicates:
        raise LabelError(f"{name} index has duplicate sessions")
    normalized = series.index.normalize()
    if not series.index.equals(normalized):
        raise LabelError(f"{name} index must contain normalized trading sessions")


def _require_positive_int(value: Any, name: str, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else f"at least {minimum}"
        raise LabelError(f"{name} must be {qualifier}")


def _is_positive_finite(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return numeric > 0 and math.isfinite(numeric)


def _require_nonempty_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise LabelError(f"{name} must be a non-empty string")


def _next_open_exit_pairs(
    index: pd.Index, *, horizon_sessions: int
) -> tuple[list[int], list[int], list[int], int]:
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
    benchmark_open: pd.Series,
    horizon_sessions: int = 20,
    round_trip_cost_bps: float = 0.0,
    label_version: str | None = None,
) -> tuple[tuple[LabelRow, ...], int]:
    """Strategy doc 6.4: "return from the next tradable open through the
    configured 20-session exit, less the aligned QQQ or SOXX return and
    round-trip cost." Returns (label_rows, dropped_tail_row_count)."""
    _require_nonempty_string(ticker, "ticker")
    _validate_price_index(close, "close")
    _validate_price_index(open_, "open")
    _validate_price_index(benchmark_close, "benchmark_close")
    _validate_price_index(benchmark_open, "benchmark_open")
    _require_positive_int(horizon_sessions, "horizon_sessions", minimum=1)
    if (
        isinstance(round_trip_cost_bps, bool)
        or not isinstance(round_trip_cost_bps, (int, float))
        or round_trip_cost_bps < 0
        or not math.isfinite(float(round_trip_cost_bps))
    ):
        raise LabelError("round_trip_cost_bps must be a non-negative finite number")
    if not close.index.equals(open_.index):
        raise LabelError("close and open must share the same session index")
    if label_version is None:
        label_version = f"forward_excess_return_{horizon_sessions}d_next_open_v1"
    if not isinstance(label_version, str) or not label_version.strip():
        raise LabelError("label_version must be a non-empty string")

    aligned_benchmark_close = benchmark_close.reindex(close.index)
    aligned_benchmark_open = benchmark_open.reindex(close.index)
    as_of_pos, entry_pos, exit_pos, dropped = _next_open_exit_pairs(
        close.index, horizon_sessions=horizon_sessions
    )
    cost_pct = round_trip_cost_bps / 10_000.0 * 100
    rows: list[LabelRow] = []
    for as_of_i, entry_i, exit_i in zip(as_of_pos, entry_pos, exit_pos):
        raw_entry_price = open_.iloc[entry_i]
        raw_exit_price = close.iloc[exit_i]
        benchmark_entry = aligned_benchmark_open.iloc[entry_i]
        benchmark_exit = aligned_benchmark_close.iloc[exit_i]
        if (
            not _is_positive_finite(raw_entry_price)
            or not _is_positive_finite(raw_exit_price)
            or not _is_positive_finite(benchmark_entry)
            or not _is_positive_finite(benchmark_exit)
        ):
            dropped += 1
            continue
        entry_price = float(raw_entry_price)
        exit_price = float(raw_exit_price)
        raw_return_pct = (exit_price / entry_price - 1.0) * 100
        benchmark_return_pct = (float(benchmark_exit) / float(benchmark_entry) - 1.0) * 100
        value = raw_return_pct - benchmark_return_pct - cost_pct
        if not all(math.isfinite(item) for item in (raw_return_pct, benchmark_return_pct, value)):
            dropped += 1
            continue
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
                    "benchmark_entry_price": round(float(benchmark_entry), 6),
                    "benchmark_exit_price": round(float(benchmark_exit), 6),
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
    label_version: str | None = None,
) -> tuple[tuple[LabelRow, ...], int]:
    """Realized volatility (daily-return std, in percent -- same
    non-annualized convention as signals/regime.py's
    compute_trailing_market_volatility(), not reinvented here) over the
    `horizon_sessions` sessions following `as_of_session`."""
    _require_nonempty_string(ticker, "ticker")
    _validate_price_index(close, "close")
    _require_positive_int(horizon_sessions, "horizon_sessions", minimum=2)
    if label_version is None:
        label_version = f"forward_realized_vol_{horizon_sessions}d_v1"
    if not isinstance(label_version, str) or not label_version.strip():
        raise LabelError("label_version must be a non-empty string")

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
        numeric_window = pd.to_numeric(window, errors="coerce")
        if not numeric_window.map(_is_positive_finite).all():
            dropped += 1
            continue
        daily_returns = numeric_window.pct_change(fill_method=None).dropna()
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
    benchmark_open: pd.Series,
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
    _require_nonempty_string(ticker, "ticker")
    if (
        isinstance(downside_threshold_pct, bool)
        or not isinstance(downside_threshold_pct, (int, float))
        or downside_threshold_pct <= 0
        or not math.isfinite(float(downside_threshold_pct))
    ):
        raise LabelError("downside_threshold_pct must be a positive finite number")
    excess_rows, dropped = compute_forward_excess_return_labels(
        ticker,
        close,
        open_,
        benchmark_close,
        benchmark_open=benchmark_open,
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
