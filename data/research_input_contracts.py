"""Strict input contracts shared by research strategies and backtests.

The functions in this module validate inputs without sorting, coercing, or
silently intersecting them.  A backtest result is evidence only when its time
direction, costs, capital, weights, and price observations are all explicit
and economically possible at the public boundary that creates the result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from numbers import Integral, Real
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype


WEIGHT_SUM_TOLERANCE = 1e-9


def _is_bool(value: Any) -> bool:
    return isinstance(value, (bool, np.bool_))


def require_positive_int(value: Any, *, name: str) -> int:
    """Return a strictly positive integer, explicitly excluding bool."""
    if _is_bool(value) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return normalized


def require_nonnegative_int(value: Any, *, name: str) -> int:
    """Return a non-negative integer, explicitly excluding bool."""
    if _is_bool(value) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return normalized


def require_horizon(
    value: Any,
    *,
    name: str = "hold_days",
    allow_same_session_zero: bool = False,
) -> int:
    """Validate a forward horizon.

    Zero is accepted only when the caller explicitly identifies a genuine
    same-session entry/exit mode.  Negative values, bool, and integral-looking
    floats are always refused.
    """
    if _is_bool(value) or not isinstance(value, Integral):
        qualifier = (
            "a non-negative integer"
            if allow_same_session_zero
            else "a positive integer"
        )
        raise ValueError(f"{name} must be {qualifier}, got {value!r}")
    normalized = int(value)
    minimum = 0 if allow_same_session_zero else 1
    if normalized < minimum:
        qualifier = (
            "a non-negative integer for same-session execution"
            if allow_same_session_zero
            else "a positive integer"
        )
        raise ValueError(f"{name} must be {qualifier}, got {value!r}")
    return normalized


def require_finite_number(
    value: Any,
    *,
    name: str,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
    maximum_inclusive: bool = True,
) -> float:
    """Return a finite real number inside the requested closed/open bounds."""
    if _is_bool(value) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number, got {value!r}")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number, got {value!r}")
    if minimum is not None:
        below = normalized < minimum if minimum_inclusive else normalized <= minimum
        if below:
            operator = ">=" if minimum_inclusive else ">"
            raise ValueError(f"{name} must be {operator} {minimum}, got {value!r}")
    if maximum is not None:
        above = normalized > maximum if maximum_inclusive else normalized >= maximum
        if above:
            operator = "<=" if maximum_inclusive else "<"
            raise ValueError(f"{name} must be {operator} {maximum}, got {value!r}")
    return normalized


def require_positive_number(value: Any, *, name: str) -> float:
    return require_finite_number(value, name=name, minimum=0.0, minimum_inclusive=False)


def require_rate(
    value: Any,
    *,
    name: str,
    allow_one: bool = False,
) -> float:
    """Validate a fractional cost/tax/slippage rate.

    Transaction costs and slippage must be below 100% so proceeds and fill
    prices cannot turn negative.  A tax rate may explicitly allow 100%.
    """
    return require_finite_number(
        value,
        name=name,
        minimum=0.0,
        maximum=1.0,
        maximum_inclusive=allow_one,
    )


def require_combined_rates_at_most_one(
    first: float,
    second: float,
    *,
    first_name: str,
    second_name: str,
) -> None:
    """Prevent combined deductions from manufacturing negative proceeds."""
    if first + second > 1.0:
        raise ValueError(
            f"{first_name} + {second_name} must be <= 1.0, got {first!r} + {second!r}"
        )


def require_long_only_weights(
    weights: Sequence[Any],
    *,
    name: str,
    expected_size: int | None = None,
    tolerance: float = WEIGHT_SUM_TOLERANCE,
) -> tuple[float, ...]:
    """Validate a fully-invested, unlevered, long-only weight vector."""
    tolerance = require_positive_number(tolerance, name="tolerance")
    if isinstance(weights, (str, bytes)) or not isinstance(weights, Sequence):
        raise ValueError(f"{name} must be a sequence of long-only weights")
    normalized = tuple(
        require_finite_number(value, name=f"{name}[{idx}]", minimum=0.0, maximum=1.0)
        for idx, value in enumerate(weights)
    )
    if not normalized:
        raise ValueError(f"{name} must contain at least one weight")
    if expected_size is not None and len(normalized) != expected_size:
        raise ValueError(
            f"{name} must contain exactly {expected_size} weights, got {len(normalized)}"
        )
    total = math.fsum(normalized)
    if abs(total - 1.0) > tolerance:
        raise ValueError(
            f"{name} must sum to 1.0 within tolerance {tolerance}, got {total!r}"
        )
    return normalized


def require_long_only_weight_mapping(
    weights_by_state: Mapping[str, Sequence[Any]],
    *,
    name: str,
    expected_size: int | None = None,
) -> dict[str, tuple[float, ...]]:
    if not isinstance(weights_by_state, Mapping) or not weights_by_state:
        raise ValueError(f"{name} must be a non-empty mapping of weight vectors")
    return {
        state: require_long_only_weights(
            weights,
            name=f"{name}[{state!r}]",
            expected_size=expected_size,
        )
        for state, weights in weights_by_state.items()
    }


def require_session_index(index: pd.Index, *, name: str) -> None:
    """Require an unambiguous ascending sequence of research sessions."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{name} must be a pandas DatetimeIndex of sessions")
    if not index.is_unique:
        raise ValueError(f"{name} must contain unique sessions")
    if not index.is_monotonic_increasing:
        raise ValueError(f"{name} must be monotonically increasing")
    if bool(index.hasnans):
        raise ValueError(f"{name} must not contain missing sessions")


def _require_positive_price_values(values: pd.Series, *, name: str) -> None:
    if (
        is_bool_dtype(values.dtype)
        or is_complex_dtype(values.dtype)
        or not is_numeric_dtype(values.dtype)
    ):
        raise ValueError(f"{name} must contain numeric prices")
    try:
        numeric = values.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric prices") from exc
    if not np.isfinite(numeric).all():
        raise ValueError(f"{name} must contain only finite prices")
    if (numeric <= 0).any():
        raise ValueError(f"{name} must contain only positive prices")


def require_price_frame(
    frame: pd.DataFrame,
    *,
    name: str,
    required_columns: Sequence[str],
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"{name} must be a pandas DataFrame")
    if not frame.columns.is_unique:
        raise ValueError(f"{name} must have unique columns")
    require_session_index(frame.index, name=f"{name}.index")
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required price columns: {missing!r}")
    price_columns = tuple(
        dict.fromkeys(
            (
                *required_columns,
                *(
                    column
                    for column in ("open", "high", "low", "close")
                    if column in frame.columns
                ),
            )
        )
    )
    for column in price_columns:
        _require_positive_price_values(frame[column], name=f"{name}.{column}")


def require_price_frame_mapping(
    data: Mapping[str, pd.DataFrame],
    *,
    name: str,
    required_columns: Sequence[str],
) -> None:
    if not isinstance(data, Mapping):
        raise ValueError(f"{name} must be a mapping of ticker to price DataFrame")
    for ticker, frame in data.items():
        require_price_frame(frame, name=f"{name}[{ticker!r}]", required_columns=required_columns)


def require_aligned_price_series(
    series_by_name: Mapping[str, pd.Series],
    *,
    allow_empty: bool = False,
) -> None:
    """Require positive series on one exact, unique, ascending index."""
    if not isinstance(series_by_name, Mapping) or not series_by_name:
        raise ValueError("price series must be a non-empty mapping")
    reference_name: str | None = None
    reference_index: pd.Index | None = None
    for name, series in series_by_name.items():
        if not isinstance(series, pd.Series):
            raise ValueError(f"{name} must be a pandas Series")
        require_session_index(series.index, name=f"{name}.index")
        if series.empty:
            if not allow_empty:
                raise ValueError(f"{name} must contain at least one price")
        else:
            _require_positive_price_values(series, name=name)
        if reference_index is None:
            reference_name = name
            reference_index = series.index
        elif not series.index.equals(reference_index):
            raise ValueError(f"{name}.index must exactly align with {reference_name}.index")


def require_index_window(
    *,
    entry_idx: Any,
    exit_idx: Any,
    length: int,
    entry_name: str = "entry_idx",
    exit_name: str = "exit_idx",
) -> tuple[int, int]:
    """Validate an in-bounds window whose exit cannot precede entry."""
    entry = require_nonnegative_int(entry_idx, name=entry_name)
    exit_ = require_nonnegative_int(exit_idx, name=exit_name)
    if entry >= length:
        raise ValueError(f"{entry_name} must be less than data length {length}, got {entry}")
    if exit_ >= length:
        raise ValueError(f"{exit_name} must be less than data length {length}, got {exit_}")
    if exit_ < entry:
        raise ValueError(f"{exit_name} must not precede {entry_name}, got {exit_} < {entry}")
    return entry, exit_
