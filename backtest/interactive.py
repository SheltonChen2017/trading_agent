"""
UI-3: the pure composition layer between the Streamlit Backtest page and
the walk-forward engine.

The Streamlit script must hold NO backtest math and NO signal knowledge of
its own -- it renders widgets from the frozen inventory below and calls
these functions, which in turn call the SAME `backtest/engine.py`
functions every CLI research script uses. That single-path property is
what makes a UI number trustworthy: there is no UI-only backtest logic to
drift from the tooling the findings registry was built with.

Scope decisions (frozen with the plan in docs/ACTION_PLAN_2026-08-02.md,
UI-3, 2026-08-04):

  - Only price/volume-only scanners are exposed. PEAD and fundamentals
    need an earnings feed; residual momentum/reversal and idio vol refuse
    to run without a precomputed residual or benchmark feed. Adding any
    of them later means extending SIGNAL_INVENTORY in a reviewed change,
    not special-casing the UI.
  - Entry timing is the executable "next_open" default, displayed but not
    selectable: "same_close" is legacy-only and look-ahead-optimistic
    (see run_backtest's docstring) and an interactive surface must not
    make choosing it casual.
  - This module performs research computation only. It must never import
    execution, proposal, risk-gate, broker, or storage code -- pinned by
    tests/test_backtest_interactive.py.

Interpretation guardrails belong to the page, but their text lives here
(EXPLORATORY_CAVEATS / SYNTHETIC_CAVEAT) so tests can pin that the UI
actually shows them rather than a paraphrase that drifts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable

import pandas as pd

from backtest.engine import run_multi_horizon_backtest
from config import ROLLING_WINDOW
from signals.breakout import scan_52_week_breakout
from signals.high52_proximity import scan_high52_proximity
from signals.momentum import scan_momentum
from signals.relative import scan_relative_dips_and_ups
from signals.scanner import scan_dips_and_ups
from signals.vol_scaled_momentum import scan_vol_scaled_momentum


@dataclass(frozen=True)
class SignalParam:
    """One tunable parameter of a scan function, with the widget bounds
    the UI must enforce. `kind` is "int" or "float"; defaults match the
    scan function's own signature defaults (asserted by test)."""

    name: str
    label: str
    kind: str
    default: float
    min_value: float
    max_value: float
    step: float
    help: str


@dataclass(frozen=True)
class InteractiveSignal:
    key: str
    label: str
    scan_fn: Callable
    params: tuple[SignalParam, ...]
    description: str
    trailing_sessions_required: Callable[[dict[str, float | int]], int]


@dataclass(frozen=True)
class BacktestDataCoverage:
    """What the data provider actually supplied for one requested run.

    Missing and short-history tickers are not silently discarded: the UI
    stores this immutable record with the results and discloses it beside
    them. A partially covered exploratory run can still be inspected, but
    it must never be presented as if the full requested universe loaded.
    """

    requested_ticker_count: int
    loaded_ticker_count: int
    complete_ticker_count: int
    missing_tickers: tuple[str, ...]
    underfilled_tickers: tuple[tuple[str, int], ...]

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_tickers or self.underfilled_tickers)


def _int_param(name, label, default, min_value, max_value, help, step=1):
    return SignalParam(
        name=name, label=label, kind="int", default=default,
        min_value=min_value, max_value=max_value, step=step, help=help,
    )


def _float_param(name, label, default, min_value, max_value, help, step=0.05):
    return SignalParam(
        name=name, label=label, kind="float", default=default,
        min_value=min_value, max_value=max_value, step=step, help=help,
    )


def _rolling_history(_params: dict[str, float | int]) -> int:
    return ROLLING_WINDOW


def _momentum_history(params: dict[str, float | int]) -> int:
    return max(
        ROLLING_WINDOW,
        int(params["lookback_days"]) + int(params["skip_days"]),
    )


def _lookback_history(params: dict[str, float | int]) -> int:
    return max(ROLLING_WINDOW, int(params["lookback_days"]))


def _vol_scaled_history(params: dict[str, float | int]) -> int:
    return max(
        ROLLING_WINDOW,
        int(params["lookback_days"]) + int(params["skip_days"]),
        int(params["vol_window"]),
    )


# THE frozen inventory of interactively runnable signals. Order is display
# order. Adding, removing, or re-parameterizing an entry is a reviewed
# change (tests pin names, defaults-vs-signature agreement, and bounds).
SIGNAL_INVENTORY: tuple[InteractiveSignal, ...] = (
    InteractiveSignal(
        key="dips_and_ups",
        label="Dip / up z-score scanner",
        scan_fn=scan_dips_and_ups,
        params=(
            _float_param(
                "return_z_threshold", "Return z-score threshold", 2.0, 0.5, 4.0,
                "How unusual (in standard deviations) a day's return must be to flag.",
            ),
            _float_param(
                "volume_z_threshold", "Volume z-score threshold", 1.5, 0.0, 4.0,
                "How unusual the day's volume must be alongside the price move.",
            ),
        ),
        description=(
            "The original scanner: flags days whose return AND volume are "
            "simultaneously unusual vs. the stock's own rolling history. "
            "'dip' bets on mean reversion, 'up' on continuation."
        ),
        trailing_sessions_required=_rolling_history,
    ),
    InteractiveSignal(
        key="momentum",
        label="Cross-sectional momentum",
        scan_fn=scan_momentum,
        params=(
            _int_param(
                "lookback_days", "Momentum lookback (trading days)", 126, 21, 504,
                "Return window ranked across the universe.",
            ),
            _int_param(
                "skip_days", "Skip most recent (trading days)", 21, 0, 63,
                "Days excluded before the ranking date (avoids short-term reversal).",
            ),
            _float_param(
                "top_pct", "Top fraction flagged 'up'", 0.2, 0.05, 0.5,
                "Fraction of the universe flagged as winners.",
            ),
            _float_param(
                "bottom_pct", "Bottom fraction flagged 'dip'", 0.2, 0.05, 0.5,
                "Fraction of the universe flagged as losers.",
            ),
        ),
        description=(
            "Ranks the universe by trailing return (skipping the most "
            "recent days) and flags the top and bottom fractions."
        ),
        trailing_sessions_required=_momentum_history,
    ),
    InteractiveSignal(
        key="relative_dips_and_ups",
        label="Relative (market-adjusted) dip / up",
        scan_fn=scan_relative_dips_and_ups,
        params=(
            _float_param(
                "relative_z_threshold", "Relative return z-score threshold", 2.0, 0.5, 4.0,
                "Unusualness of the stock's return relative to the universe that day.",
            ),
            _float_param(
                "volume_z_threshold", "Volume z-score threshold", 1.5, 0.0, 4.0,
                "How unusual the day's volume must be alongside the relative move.",
            ),
        ),
        description=(
            "Like the dip/up scanner but on market-adjusted returns, so a "
            "broad selloff day does not flag the whole universe at once."
        ),
        trailing_sessions_required=_rolling_history,
    ),
    InteractiveSignal(
        key="breakout_52_week",
        label="52-week breakout",
        scan_fn=scan_52_week_breakout,
        params=(
            _int_param(
                "lookback_days", "High lookback (trading days)", 252, 63, 504,
                "Window whose high must be exceeded to flag a breakout.",
            ),
            _float_param(
                "volume_z_threshold", "Volume z-score threshold", 1.5, 0.0, 4.0,
                "Volume confirmation required with the breakout.",
            ),
        ),
        description=(
            "Flags closes above the trailing high on unusual volume -- a "
            "momentum-continuation hypothesis."
        ),
        trailing_sessions_required=_lookback_history,
    ),
    InteractiveSignal(
        key="high52_proximity",
        label="52-week-high proximity",
        scan_fn=scan_high52_proximity,
        params=(
            _int_param(
                "lookback_days", "High lookback (trading days)", 252, 63, 504,
                "Window defining the reference high.",
            ),
            _float_param(
                "top_pct", "Closest-to-high fraction flagged 'up'", 0.2, 0.05, 0.5,
                "Fraction of the universe nearest its trailing high.",
            ),
            _float_param(
                "bottom_pct", "Furthest-from-high fraction flagged 'dip'", 0.2, 0.05, 0.5,
                "Fraction of the universe furthest below its trailing high.",
            ),
        ),
        description=(
            "Ranks the universe by closeness to its own trailing high and "
            "flags both tails."
        ),
        trailing_sessions_required=_lookback_history,
    ),
    InteractiveSignal(
        key="vol_scaled_momentum",
        label="Volatility-scaled momentum",
        scan_fn=scan_vol_scaled_momentum,
        params=(
            _int_param(
                "lookback_days", "Momentum lookback (trading days)", 252, 63, 504,
                "Return window ranked across the universe.",
            ),
            _int_param(
                "skip_days", "Skip most recent (trading days)", 21, 0, 63,
                "Days excluded before the ranking date.",
            ),
            _int_param(
                "vol_window", "Volatility window (trading days)", 60, 21, 252,
                "Window for the volatility that scales the momentum score.",
            ),
            _float_param(
                "top_pct", "Top fraction flagged 'up'", 0.2, 0.05, 0.5,
                "Fraction of the universe flagged as winners.",
            ),
            _float_param(
                "bottom_pct", "Bottom fraction flagged 'dip'", 0.2, 0.05, 0.5,
                "Fraction of the universe flagged as losers.",
            ),
        ),
        description=(
            "Momentum divided by realized volatility, so a calm steady "
            "riser can outrank a violent one."
        ),
        trailing_sessions_required=_vol_scaled_history,
    ),
)


def signal_for_key(key: str) -> InteractiveSignal:
    for signal in SIGNAL_INVENTORY:
        if signal.key == key:
            return signal
    raise KeyError(
        f"Unknown interactive signal {key!r}. Valid keys: "
        f"{[s.key for s in SIGNAL_INVENTORY]}"
    )


def inspect_data_coverage(
    data: dict[str, pd.DataFrame],
    *,
    requested_tickers: tuple[str, ...],
    requested_sessions: int,
) -> BacktestDataCoverage:
    """Validate and summarize provider coverage without changing the data.

    A completely empty response fails closed because "provider returned no
    usable rows" and "the signal found nothing" are different outcomes.
    Partial coverage is returned explicitly so the exploratory UI can warn
    while retaining the useful subset.
    """
    if (
        isinstance(requested_sessions, bool)
        or not isinstance(requested_sessions, int)
        or requested_sessions < 1
    ):
        raise ValueError("requested_sessions must be a positive integer.")
    if not requested_tickers:
        raise ValueError("At least one requested ticker is required.")
    if any(not isinstance(ticker, str) or not ticker for ticker in requested_tickers):
        raise ValueError("Requested tickers must be non-empty strings.")
    if len(set(requested_tickers)) != len(requested_tickers):
        raise ValueError("Requested tickers must be unique.")

    unexpected = sorted(set(data) - set(requested_tickers))
    if unexpected:
        raise ValueError(
            f"Provider returned tickers outside the requested scope: {unexpected}."
        )

    loaded: list[str] = []
    missing: list[str] = []
    underfilled: list[tuple[str, int]] = []
    for ticker in requested_tickers:
        frame = data.get(ticker)
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            missing.append(ticker)
            continue
        loaded.append(ticker)
        if len(frame) < requested_sessions:
            underfilled.append((ticker, len(frame)))

    if not loaded:
        raise ValueError(
            "The data provider returned no usable market data for the "
            "requested universe; no backtest was run."
        )

    return BacktestDataCoverage(
        requested_ticker_count=len(requested_tickers),
        loaded_ticker_count=len(loaded),
        complete_ticker_count=len(loaded) - len(underfilled),
        missing_tickers=tuple(missing),
        underfilled_tickers=tuple(underfilled),
    )


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number, got {value!r}.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite number, got {value!r}.")
    return numeric


def run_interactive_backtest(
    data: dict[str, pd.DataFrame],
    *,
    signal_key: str,
    param_values: dict[str, float],
    hold_days_options: list[int],
    slippage_pct: float,
) -> dict[int, pd.DataFrame]:
    """Run the shared multi-horizon walk-forward engine for one inventory
    signal. Fails closed on anything off-contract: unknown signal key,
    a parameter name the inventory does not declare, an out-of-bounds
    value, or an empty horizon list -- an interactive surface must never
    silently drop or coerce a user's input into a different experiment
    than the one displayed.
    """
    signal = signal_for_key(signal_key)
    if not any(
        isinstance(frame, pd.DataFrame) and not frame.empty
        for frame in data.values()
    ):
        raise ValueError(
            "The data provider returned no usable market data; no backtest was run."
        )
    declared = {param.name: param for param in signal.params}
    unknown = sorted(set(param_values) - set(declared))
    if unknown:
        raise ValueError(
            f"Parameters {unknown} are not declared for signal "
            f"{signal_key!r}; declared: {sorted(declared)}"
        )
    missing = sorted(set(declared) - set(param_values))
    if missing:
        raise ValueError(
            f"Missing parameters {missing} for signal {signal_key!r}."
        )
    if not hold_days_options:
        raise ValueError("At least one hold horizon is required.")

    validated_horizons: list[int] = []
    for value in hold_days_options:
        numeric = _finite_real(value, name="hold horizon")
        if not numeric.is_integer() or numeric <= 0:
            raise ValueError(
                f"Each hold horizon must be a positive whole number, got {value!r}."
            )
        validated_horizons.append(int(numeric))
    if len(set(validated_horizons)) != len(validated_horizons):
        raise ValueError("Each hold horizon must be unique.")

    validated_slippage = _finite_real(slippage_pct, name="slippage_pct")
    if validated_slippage < 0:
        raise ValueError("slippage_pct must be non-negative.")

    scan_kwargs: dict[str, float | int] = {}
    for name, spec in declared.items():
        value = param_values[name]
        numeric = _finite_real(value, name=name)
        if spec.kind == "int" and not numeric.is_integer():
            raise ValueError(
                f"{name} must be a whole number for signal {signal_key!r}, "
                f"got {value!r}."
            )
        if not (spec.min_value <= numeric <= spec.max_value):
            raise ValueError(
                f"{name}={value!r} is outside [{spec.min_value}, "
                f"{spec.max_value}] for signal {signal_key!r}."
            )
        scan_kwargs[name] = int(numeric) if spec.kind == "int" else numeric

    # The signal needs enough trailing rows to become defined, then one row
    # for next-open entry and ``max(horizon)`` more rows to reach the exit.
    # Without this guard an impossible configuration looks exactly like a
    # legitimate zero-signal result in the engine's empty result frame.
    minimum_sessions = (
        signal.trailing_sessions_required(scan_kwargs)
        + max(validated_horizons)
        + 2
    )
    longest_history = max(
        len(frame)
        for frame in data.values()
        if isinstance(frame, pd.DataFrame) and not frame.empty
    )
    if longest_history < minimum_sessions:
        raise ValueError(
            f"Selected signal parameters and hold horizons require at least "
            f"{minimum_sessions} sessions, but the longest loaded ticker has "
            f"{longest_history}; insufficient history to run this experiment."
        )

    return run_multi_horizon_backtest(
        data,
        hold_days_options=validated_horizons,
        slippage_pct=validated_slippage,
        scan_fn=signal.scan_fn,
        scan_kwargs=scan_kwargs,
        entry_timing="next_open",
    )


def cumulative_return_frame(results: pd.DataFrame) -> pd.DataFrame:
    """Chart-ready frame: for each signal direction, the running sum of
    per-signal net returns (%) in chronological signal order.

    This is an equal-weight, one-unit-per-signal accumulation -- a shape
    for eyeballing when a signal's contributions came and whether one
    period dominates, NOT a portfolio equity curve (no compounding, no
    position sizing, no capital constraint, overlapping holds allowed).
    The caption the UI must show next to it comes from CHART_CAPTION.
    """
    if results.empty:
        return pd.DataFrame()
    frame = results[["date", "direction", "net_return_pct"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["date"], kind="stable")
    pivot = (
        frame.groupby(["date", "direction"])["net_return_pct"]
        .sum()
        .unstack("direction")
        .fillna(0.0)
        .cumsum()
    )
    pivot.columns = [f"{direction} (cumulative net %)" for direction in pivot.columns]
    return pivot


CHART_CAPTION = (
    "Running sum of per-signal net returns (%), equal weight, one unit per "
    "signal, slippage deducted -- NOT a portfolio equity curve: no "
    "compounding, sizing, or capital constraint, and holds may overlap."
)

SYNTHETIC_CAVEAT = (
    "Synthetic random-walk data: a ~50% win rate here is the EXPECTED, "
    "correct result. This run checks the pipeline's plumbing and says "
    "nothing about real-market edge."
)

EXPLORATORY_CAVEATS = (
    "Exploratory result -- not evidence of edge. This page applies no "
    "multiple-comparison correction and every parameter tweak is another "
    "uncounted look; small samples (well under ~30 signals) are "
    "luck-indistinguishable; yfinance history is not point-in-time. "
    "Confirmatory significance runs only in the frozen CLI pipeline "
    "(run_significance_check.py / run_out_of_sample_check.py), and this "
    "project's record there is 11 signals tested, 0 confirmed."
)
