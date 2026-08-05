"""Regression tests for the owner-dictated exploratory dip-grid script."""
from __future__ import annotations

import numpy as np
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


def test_main_keeps_episode_and_universe_baseline_paired(monkeypatch, capsys):
    """Every reported episode must carry a same-horizon universe baseline;
    truncated or empty baseline windows must not create unpaired rows."""
    periods = subject.MAX_HOLD_SESSIONS + 5
    index = pd.bdate_range("2026-01-02", periods=periods)
    # AAA declines on day 1 so it is picked; BBB stays available for baseline.
    closes = pd.DataFrame(
        {
            "AAA": np.linspace(100.0, 110.0, periods),
            "BBB": np.linspace(50.0, 55.0, periods),
        },
        index=index,
    )
    closes.iloc[1, closes.columns.get_loc("AAA")] = 80.0
    opens = closes.copy()

    monkeypatch.setattr(
        subject,
        "fetch_historical",
        lambda *_args, **_kwargs: {
            "AAA": pd.DataFrame({"close": closes["AAA"], "open": opens["AAA"]}),
            "BBB": pd.DataFrame({"close": closes["BBB"], "open": opens["BBB"]}),
        },
    )
    monkeypatch.setattr(subject, "UNIVERSE", ["AAA", "BBB"])

    subject.main()
    captured = capsys.readouterr().out
    assert "paired beat rates:" in captured
    assert "hold - universe" in captured
    assert "grid - universe" in captured
    assert "point_in_time_data=false" in captured
