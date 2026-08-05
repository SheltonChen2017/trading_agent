"""Regression tests for the owner-dictated exploratory dip-grid script."""
from __future__ import annotations

import pandas as pd

from scripts import run_sharpest_decline_dip_2026_08_05 as subject


def _prices(periods: int) -> tuple[pd.Series, pd.Series]:
    index = pd.bdate_range("2026-01-02", periods=periods)
    values = pd.Series(
        [100.0 + index for index in range(periods)],
        index=index,
    )
    return values, values.copy()


def test_episode_requires_the_frozen_full_horizon():
    closes, opens = _prices(subject.MAX_HOLD_SESSIONS)
    assert subject._simulate_episode(closes, opens, 1) is None


def test_episode_reports_exactly_the_frozen_full_horizon():
    closes, opens = _prices(subject.MAX_HOLD_SESSIONS + 1)
    result = subject._simulate_episode(closes, opens, 0)
    assert result is not None
    assert result["sessions_held"] == subject.MAX_HOLD_SESSIONS
