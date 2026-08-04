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

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from backtest.engine import run_multi_horizon_backtest
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

    scan_kwargs: dict[str, float | int] = {}
    for name, spec in declared.items():
        value = param_values[name]
        if not (spec.min_value <= value <= spec.max_value):
            raise ValueError(
                f"{name}={value!r} is outside [{spec.min_value}, "
                f"{spec.max_value}] for signal {signal_key!r}."
            )
        scan_kwargs[name] = int(value) if spec.kind == "int" else float(value)

    return run_multi_horizon_backtest(
        data,
        hold_days_options=list(hold_days_options),
        slippage_pct=slippage_pct,
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
