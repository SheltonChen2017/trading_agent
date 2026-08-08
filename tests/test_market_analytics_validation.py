"""CCX-003: the two validation candidates Codex deferred without naming them.

`docs/REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md` §5 marks the root Python
modules "Complete" while recording "two low-risk validation candidates
deferred pending caller/test cross-check". The candidates were never
described, so nobody could pick them up, and "Complete" overstated closure.

The cross-check was done and both are real. Neither is reachable from the
execution path -- production callers pass the frozen `trend_lookback_days`
of 200, and the baseline runner is research-only -- so P3 stands. But the
second one inverts the control group a signal's edge is judged against,
which is the same failure mode as the decline-grid comparator (CXL-013),
rated P2.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_analytics import classify_trend, run_baseline_forward_returns


def _series(n: int = 50) -> pd.Series:
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.Series(np.linspace(100.0, 200.0, n), index=idx)


def _frame(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close.values,
            "high": close.values,
            "low": close.values,
            "close": close.values,
            "volume": np.full(len(close), 1e6),
        },
        index=close.index,
    )


@pytest.mark.parametrize("lookback", [0, -1, -200])
def test_a_non_positive_trend_lookback_is_refused(lookback):
    """It used to answer "downtrend" from an EMPTY window.

    `idx < lookback - 1` is False for a non-positive lookback, the slice comes
    back empty, its mean is NaN, and `close >= NaN` is False -- so the caller
    received a confident trend label computed from no data. A trend label
    feeds strategy sizing; fabricating one is worse than refusing.
    """
    close = _series()
    with pytest.raises(ValueError):
        classify_trend(close, close.index[-1], lookback_days=lookback)


@pytest.mark.parametrize("lookback", [True, 1.5, "200", None])
def test_a_non_integer_trend_lookback_is_refused(lookback):
    close = _series()
    with pytest.raises(ValueError):
        classify_trend(close, close.index[-1], lookback_days=lookback)


def test_a_valid_trend_lookback_still_works():
    close = _series()
    assert classify_trend(close, close.index[-1], lookback_days=20) == "uptrend"
    # Insufficient history still returns None rather than raising.
    assert classify_trend(close, close.index[-1], lookback_days=200) is None


@pytest.mark.parametrize("hold_days", [0, -1, -5])
def test_a_non_positive_hold_is_refused_by_the_baseline_runner(hold_days):
    """A negative hold silently inverted the baseline.

    `shift(-hold_days)` with a negative value shifts BACKWARD, so the
    "forward" price is a past price: on a monotonically rising fixture the
    baseline reported -7.08% where the true forward return was +6.93%. This
    is the control group a signal's edge is measured against.
    """
    close = _series()
    with pytest.raises(ValueError):
        run_baseline_forward_returns({"X": _frame(close)}, hold_days=hold_days)


@pytest.mark.parametrize("slippage", [-0.01, float("nan"), float("inf"), True])
def test_an_unusable_slippage_is_refused(slippage):
    close = _series()
    with pytest.raises(ValueError):
        run_baseline_forward_returns(
            {"X": _frame(close)}, hold_days=5, slippage_pct=slippage
        )


def test_a_valid_baseline_run_is_unchanged_and_forward_looking():
    close = _series()
    result = run_baseline_forward_returns({"X": _frame(close)}, hold_days=5)
    assert not result.empty
    # A rising series must produce a positive forward baseline.
    assert result["net_return_pct"].mean() > 0
