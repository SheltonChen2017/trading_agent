from __future__ import annotations

import pandas as pd
import pytest

from strategies import decline_grid


def _frame(opens, closes):
    index = pd.bdate_range("2026-01-02", periods=len(opens))
    return pd.DataFrame(
        {
            "open": opens,
            "high": [max(a, b) for a, b in zip(opens, closes)],
            "low": [min(a, b) for a, b in zip(opens, closes)],
            "close": closes,
            "volume": 1_000_000.0,
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("kwargs", "expected_outcome", "expected_column"),
    [
        ({"stop_loss_pct": 10.0}, "stop_loss", "open"),
        ({"max_hold_days": 0}, "max_hold", "open"),
        ({"trigger_pct": 0.05, "trim_pct": 1.0}, "fully_sold", "open"),
    ],
)
def test_next_session_episode_exits_record_open_price_source(
    kwargs, expected_outcome, expected_column
):
    closes = [100.0, 60.0, 60.0] if expected_outcome == "stop_loss" else [100.0, 110.0, 110.0]
    episode = decline_grid.simulate_episode(
        _frame([100.0, 100.0, 80.0], closes),
        0,
        slippage_pct=0.0,
        **kwargs,
    )

    assert episode["outcome"] == expected_outcome
    assert episode["exit_price_column"] == expected_column


@pytest.mark.parametrize(
    ("kwargs", "expected_outcome"),
    [
        ({"stop_loss_pct": 10.0}, "stop_loss"),
        ({"max_hold_days": 0}, "max_hold"),
        ({"trigger_pct": 0.05}, "forced_end_no_more_data"),
    ],
)
def test_final_session_episode_exits_record_close_price_source(
    kwargs, expected_outcome
):
    final_close = 60.0 if expected_outcome == "stop_loss" else 110.0
    episode = decline_grid.simulate_episode(
        _frame([100.0, 100.0], [100.0, final_close]),
        0,
        slippage_pct=0.0,
        **kwargs,
    )

    assert episode["outcome"] == expected_outcome
    assert episode["exit_price_column"] == "close"


def test_quiet_forced_end_records_close_price_source():
    episode = decline_grid.simulate_episode(
        _frame([100.0, 100.0], [100.0, 100.0]),
        0,
        trigger_pct=0.5,
        slippage_pct=0.0,
    )

    assert episode["outcome"] == "forced_end_no_more_data"
    assert episode["exit_price_column"] == "close"


def test_backtest_baseline_uses_same_terminal_close_as_episode(monkeypatch):
    frame = _frame([100.0, 50.0], [100.0, 200.0])
    monkeypatch.setattr(decline_grid, "find_entry_dates", lambda *_args, **_kwargs: [0])

    result = decline_grid.run_decline_grid_backtest(
        {"TEST": frame},
        trigger_pct=0.05,
        slippage_pct=0.0,
    )

    assert result.iloc[0]["outcome"] == "forced_end_no_more_data"
    assert result.iloc[0]["net_return_pct"] == 300.0
    assert result.iloc[0]["buy_and_hold_baseline_pct"] == 300.0
    assert result.iloc[0]["edge_vs_buy_and_hold_pct"] == 0.0
