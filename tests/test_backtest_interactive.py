"""UI-3: the interactive-backtest composition layer.

Pins the frozen signal inventory (names, defaults-vs-signature agreement,
bounds), fail-closed input validation, chart-frame math, and the research/
execution import boundary. Run with:
python -m pytest tests/test_backtest_interactive.py
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest.interactive as interactive
from backtest.engine import RESULT_COLUMNS
from backtest.interactive import (
    SIGNAL_INVENTORY,
    cumulative_return_frame,
    run_interactive_backtest,
    signal_for_key,
)
from data.market_data import generate_synthetic

# THE frozen inventory: (key, param names in order). Changing the set of
# interactively runnable signals or their tunable surface MUST arrive with
# a reviewed edit of this literal.
FROZEN_INVENTORY = (
    ("dips_and_ups", ("return_z_threshold", "volume_z_threshold")),
    ("momentum", ("lookback_days", "skip_days", "top_pct", "bottom_pct")),
    ("relative_dips_and_ups", ("relative_z_threshold", "volume_z_threshold")),
    ("breakout_52_week", ("lookback_days", "volume_z_threshold")),
    ("high52_proximity", ("lookback_days", "top_pct", "bottom_pct")),
    (
        "vol_scaled_momentum",
        ("lookback_days", "skip_days", "vol_window", "top_pct", "bottom_pct"),
    ),
)


# --- the frozen inventory ---------------------------------------------------


def test_inventory_matches_the_frozen_literal():
    actual = tuple(
        (signal.key, tuple(param.name for param in signal.params))
        for signal in SIGNAL_INVENTORY
    )
    assert actual == FROZEN_INVENTORY


def test_keys_and_labels_are_unique():
    keys = [signal.key for signal in SIGNAL_INVENTORY]
    labels = [signal.label for signal in SIGNAL_INVENTORY]
    assert len(keys) == len(set(keys))
    assert len(labels) == len(set(labels))


def test_every_declared_param_defaults_to_the_scan_functions_own_default():
    """The UI shows inventory defaults; the engine runs scan_kwargs built
    from them. If the inventory drifted from the function signature, the
    page would silently run a different experiment than the signal's
    documented default behavior."""
    for signal in SIGNAL_INVENTORY:
        signature = inspect.signature(signal.scan_fn)
        for param in signal.params:
            assert param.name in signature.parameters, (
                f"{signal.key}: {param.name} is not a parameter of "
                f"{signal.scan_fn.__name__}"
            )
            assert signature.parameters[param.name].default == param.default, (
                f"{signal.key}.{param.name}: inventory default "
                f"{param.default!r} != signature default "
                f"{signature.parameters[param.name].default!r}"
            )


def test_defaults_lie_within_their_own_bounds_and_kinds_are_valid():
    for signal in SIGNAL_INVENTORY:
        for param in signal.params:
            assert param.kind in ("int", "float")
            assert param.min_value <= param.default <= param.max_value
            if param.kind == "int":
                assert float(param.default).is_integer()


def test_unknown_signal_key_raises():
    with pytest.raises(KeyError):
        signal_for_key("not_a_signal")


# --- fail-closed input validation ------------------------------------------


def _small_data():
    # 8 tickers x 160 days: enough history for the dip/up scanner's rolling
    # window while keeping the walk-forward loop fast.
    return generate_synthetic(
        ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"], days=160
    )


def _defaults(signal_key: str) -> dict[str, float]:
    return {
        param.name: param.default
        for param in signal_for_key(signal_key).params
    }


def test_run_produces_engine_result_frames_per_horizon():
    results = run_interactive_backtest(
        _small_data(),
        signal_key="dips_and_ups",
        param_values=_defaults("dips_and_ups"),
        hold_days_options=[1, 5],
        slippage_pct=0.0015,
    )
    assert set(results) == {1, 5}
    for frame in results.values():
        assert list(frame.columns) == RESULT_COLUMNS


def test_undeclared_parameter_fails_closed():
    values = _defaults("dips_and_ups")
    values["lookback_days"] = 100  # momentum's param, not this signal's
    with pytest.raises(ValueError, match="not declared"):
        run_interactive_backtest(
            _small_data(),
            signal_key="dips_and_ups",
            param_values=values,
            hold_days_options=[1],
            slippage_pct=0.0015,
        )


def test_missing_parameter_fails_closed():
    values = _defaults("dips_and_ups")
    values.pop("volume_z_threshold")
    with pytest.raises(ValueError, match="Missing parameters"):
        run_interactive_backtest(
            _small_data(),
            signal_key="dips_and_ups",
            param_values=values,
            hold_days_options=[1],
            slippage_pct=0.0015,
        )


def test_out_of_bounds_value_fails_closed():
    values = _defaults("dips_and_ups")
    values["return_z_threshold"] = 99.0
    with pytest.raises(ValueError, match="outside"):
        run_interactive_backtest(
            _small_data(),
            signal_key="dips_and_ups",
            param_values=values,
            hold_days_options=[1],
            slippage_pct=0.0015,
        )


def test_empty_horizon_list_fails_closed():
    with pytest.raises(ValueError, match="hold horizon"):
        run_interactive_backtest(
            _small_data(),
            signal_key="dips_and_ups",
            param_values=_defaults("dips_and_ups"),
            hold_days_options=[],
            slippage_pct=0.0015,
        )


# --- the chart frame --------------------------------------------------------


def test_cumulative_frame_accumulates_per_direction_in_date_order():
    results = pd.DataFrame(
        [
            {"date": "2026-01-05", "direction": "dip", "net_return_pct": 1.0},
            {"date": "2026-01-02", "direction": "dip", "net_return_pct": 2.0},
            {"date": "2026-01-05", "direction": "up", "net_return_pct": -1.5},
            {"date": "2026-01-06", "direction": "dip", "net_return_pct": -0.5},
        ]
    )
    frame = cumulative_return_frame(results)
    dip = frame["dip (cumulative net %)"]
    up = frame["up (cumulative net %)"]
    # Chronological: 2.0 (Jan 2), +1.0 (Jan 5), -0.5 (Jan 6).
    assert list(dip) == [2.0, 3.0, 2.5]
    # 'up' contributes nothing on Jan 2, -1.5 on Jan 5, flat after.
    assert list(up) == [0.0, -1.5, -1.5]
    assert list(frame.index) == sorted(frame.index)


def test_cumulative_frame_handles_empty_results():
    assert cumulative_return_frame(pd.DataFrame(columns=RESULT_COLUMNS)).empty


# --- research/execution boundary -------------------------------------------

_FORBIDDEN_IMPORT_ROOTS = ("assistant", "execution", "risk", "ml")


def test_interactive_module_never_imports_execution_or_ml_code():
    """A research surface must have no import path toward proposals,
    orders, the risk gate, storage, or ML. Source-level check because the
    invariant is specifically about imports."""
    tree = ast.parse(Path(interactive.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots & set(_FORBIDDEN_IMPORT_ROOTS), (
        f"backtest.interactive imports forbidden roots: "
        f"{sorted(roots & set(_FORBIDDEN_IMPORT_ROOTS))}"
    )


def test_caveat_texts_exist_for_the_ui_to_pin():
    assert "50%" in interactive.SYNTHETIC_CAVEAT
    assert "not evidence" in interactive.EXPLORATORY_CAVEATS
    assert "NOT a portfolio equity curve" in interactive.CHART_CAPTION
