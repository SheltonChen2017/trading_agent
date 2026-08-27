"""Outcome-free statistical dispatch contracts for Analyst Revisions V2.

This module does not import prices, labels, outcome builders, ML evaluation,
or the backtest engine. It accepts a bootstrap implementation explicitly and
enforces the overlap-aware V2 contract *before* that implementation can run.
The outcome-gated orchestration layer may later supply the repository's
reviewed bootstrap primitive after satisfying the separate preregistration
and look-spend controls.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar


_Result = TypeVar("_Result")


class AnalystStatisticsContractError(ValueError):
    """A statistical request violates an Analyst Revisions V2 invariant."""


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise AnalystStatisticsContractError(
            f"{name} must be an exact positive integer"
        )
    return value


def run_horizon_aware_block_bootstrap(
    delegate: Callable[..., _Result],
    /,
    *args: Any,
    horizon_sessions: int,
    block_length: int,
    **kwargs: Any,
) -> _Result:
    """Validate overlap protection, then call a supplied bootstrap primitive.

    ``horizon_sessions`` is intentionally consumed by this wrapper and is not
    forwarded: the generic repository bootstrap accepts ``block_length`` but
    cannot infer the label horizon from an already-computed statistic series.
    V2 therefore makes the horizon mandatory at this boundary and refuses a
    block shorter than the overlapping forward-outcome window.
    """
    horizon_sessions = _positive_integer(horizon_sessions, "horizon_sessions")
    block_length = _positive_integer(block_length, "block_length")
    if block_length < horizon_sessions:
        raise AnalystStatisticsContractError(
            "block_length must be at least horizon_sessions for overlapping outcomes"
        )
    if not callable(delegate):
        raise AnalystStatisticsContractError("delegate must be callable")
    return delegate(*args, block_length=block_length, **kwargs)
