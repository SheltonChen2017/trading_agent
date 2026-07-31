"""
The significance test's own false-positive rate, measured rather than assumed.

Every verdict in this project rests on one function, so the function's
error rate is worth pinning like any other behaviour. These tests feed it
PURE NOISE -- data whose true mean edge is exactly zero -- and assert it
says "not significant" about as often as its threshold promises.

Background (2026-07-30): a candidate-signal run surfaced two defects here.

1. `block_length >= n_dates` made every circular resample a ROTATION of the
   whole date set, so the CI collapsed to zero width and p was exactly 0.0
   for any nonzero mean. The old guard `n_dates < max(5, block_length)` is
   strict, so exact equality passed straight through it. This fired on real
   project data: a VIX-spike cell with block_length=15 and n_dates=15
   reported a +0.013% mean edge as significant at p=0.0.

2. Even away from that corner the test was anti-conservative at small
   `n_dates` -- 18.5% false positives at alpha=0.05 on i.i.d. noise with
   31 dates and block 10, against a nominal 5%.

Both now return a `refusal_reason` instead of a number. Note the direction
of the original error: it made significance EASIER, so it never produced a
false REJECTION -- previously-recorded rejections are unaffected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import (
    MIN_BLOCK_BOOTSTRAP_DATES,
    bootstrap_daily_edge_significance_by_block,
    bootstrap_edge_significance_by_block,
)

BOTH_VARIANTS = (
    bootstrap_edge_significance_by_block,
    bootstrap_daily_edge_significance_by_block,
)


def _dates(n_dates: int, per_date: int) -> pd.Series:
    days = pd.to_datetime("2020-01-01") + pd.to_timedelta(np.arange(n_dates), unit="D")
    return pd.Series(np.repeat(days, per_date))


@pytest.mark.parametrize("fn", BOTH_VARIANTS)
def test_a_block_as_long_as_the_sample_is_refused(fn):
    """THE regression: this exact shape reported a ~0% edge as p=0.0.

    Reproduced with a deliberately tiny constant drift -- an edge nobody
    would call real -- so a returned p-value cannot be explained away as a
    genuinely strong effect.
    """
    n_dates = 12
    edges = pd.Series(np.full(n_dates * 4, 0.013))
    stats = fn(edges, _dates(n_dates, 4), block_length=n_dates)

    assert stats["p_value"] is None, (
        "block_length == n_dates yields a zero-width CI and p=0 for any nonzero "
        "mean; it must be refused, not reported"
    )
    assert stats["refusal_reason"], "a refusal must say why"
    assert "independent blocks" in stats["refusal_reason"]


@pytest.mark.parametrize("fn", BOTH_VARIANTS)
def test_fewer_than_two_blocks_is_refused(fn):
    """One block short of degenerate is still degenerate enough."""
    stats = fn(pd.Series(np.full(80, 0.5)), _dates(20, 4), block_length=11)
    assert stats["p_value"] is None
    assert "independent blocks" in stats["refusal_reason"]


@pytest.mark.parametrize("fn", BOTH_VARIANTS)
def test_too_few_dates_is_refused_at_every_block_length(fn):
    """At n_dates=31 the measured false-positive rate was 3.5-6.5x nominal
    for every block length tried, so no choice of block rescues it."""
    rng = np.random.default_rng(0)
    edges = pd.Series(rng.normal(0, 3.0, size=31 * 10))
    for block_length in (2, 5, 10, 15):
        stats = fn(edges, _dates(31, 10), block_length=block_length)
        assert stats["p_value"] is None, f"block_length={block_length} should be refused"
        assert stats["refusal_reason"]


@pytest.mark.parametrize("fn", BOTH_VARIANTS)
def test_enough_dates_still_produces_a_p_value(fn):
    """The guard must not swallow the cases the toolkit exists to serve.

    At 400 dates the method measured essentially exact (5.00% observed at a
    nominal 5%), so this is the regime it should keep answering in.
    """
    rng = np.random.default_rng(1)
    edges = pd.Series(rng.normal(0, 3.0, size=400 * 3))
    stats = fn(edges, _dates(400, 3), block_length=10)

    assert stats["refusal_reason"] is None
    assert stats["p_value"] is not None
    assert stats["ci_low"] < stats["ci_high"], "a real CI must have width"


@pytest.mark.parametrize("fn", BOTH_VARIANTS)
def test_false_positive_rate_on_pure_noise_is_near_nominal(fn):
    """The test that keeps the rest honest.

    60 independent pure-noise trials at a shape the guard permits. A
    calibrated test rejects ~5% of the time at alpha=0.05; the old code at
    small n_dates hit 18-27%. The bound is deliberately loose (<=20%)
    because 60 trials is a coarse estimate -- it is set to catch a
    calibration COLLAPSE, not to police a few percentage points.
    """
    rng = np.random.default_rng(7)
    date_col = _dates(120, 5)
    false_positives = 0
    trials = 60
    for _ in range(trials):
        edges = pd.Series(rng.normal(0, 3.0, size=120 * 5))
        stats = fn(edges, date_col, block_length=10, n_bootstrap=400)
        if stats["p_value"] is not None and stats["p_value"] < 0.05:
            false_positives += 1

    rate = false_positives / trials
    assert rate <= 0.20, (
        f"false-positive rate on pure noise is {rate:.0%} against a nominal 5% -- "
        "the block bootstrap has lost calibration"
    )


def test_min_dates_constant_is_not_quietly_lowered():
    """The threshold is a measured value, not a tunable.

    Lowering it re-opens the regime where the measured error rate was
    3.5-6.5x nominal, so it should require editing this assertion and the
    measurements in _block_bootstrap_refusal's docstring together.
    """
    assert MIN_BLOCK_BOOTSTRAP_DATES == 50


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
