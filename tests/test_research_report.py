import dataclasses
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.mandate import load_mandate
from backtest.research_report import (
    build_data_manifest,
    build_research_report,
    embargoed_split_dates,
    verify_research_report,
    write_research_report,
)


def _price_frame(index):
    close = np.linspace(100, 130, len(index))
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 1_000_000),
        },
        index=index,
    )


def test_data_manifest_hashes_data_and_surfaces_underfill():
    index = pd.date_range("2026-01-01", periods=10, freq="B")
    manifest = build_data_manifest(
        {"AAPL": _price_frame(index)},
        requested_sessions=20,
        point_in_time=False,
    )
    assert len(manifest["manifest_sha256"]) == 64
    assert manifest["quality_passed"] is False
    assert manifest["issues"] == [
        {"ticker": "AAPL", "issue": "under_90pct_requested_history"}
    ]


def test_embargoed_split_excludes_hold_period_on_both_sides():
    dates = pd.date_range("2026-01-01", periods=100, freq="B")
    split = embargoed_split_dates(
        dates, discovery_frac=0.6, embargo_sessions=5
    )
    assert split["embargo_sessions_each_side"] == 5
    assert split["excluded_session_count"] == 10
    assert pd.Timestamp(split["discovery_end"]) < pd.Timestamp(
        split["confirmation_start"]
    )


def test_research_report_is_immutable_and_blocks_non_point_in_time_data(
    tmp_path,
):
    index = pd.date_range("2025-01-01", periods=100, freq="B")
    frame = _price_frame(index)
    alternating = np.resize(np.array([1.01, 0.995]), len(index))
    frame["close"] = 100 * pd.Series(alternating, index=index).cumprod()
    frame["open"] = frame["close"]
    frame["high"] = frame["close"] + 0.5
    frame["low"] = frame["close"] - 0.5
    equity = pd.Series(
        100_000 * (frame["close"] / frame["close"].iloc[0]), index=index
    )
    broad_mandate = dataclasses.replace(
        load_mandate(),
        target_annualized_volatility_min_pct=0,
        target_annualized_volatility_max_pct=100,
        max_drawdown_pct=100,
        max_time_under_water_sessions=1000,
        max_downside_capture_pct=200,
        min_upside_capture_pct=0,
    )
    report = build_research_report(
        strategy_name="test_strategy",
        equity_curve=equity,
        benchmark_close=frame["close"],
        data={"AAPL": frame},
        parameters={"entry_timing": "next_open"},
        mandate=broad_mandate,
        code_commit="abc123",
        requested_sessions=100,
        point_in_time_data=False,
        discovery_frac=0.6,
        hold_days=5,
        generated_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )
    assert report["mandate_evaluation"]["passed"] is True
    assert "not_point_in_time_data" in report["promotion_blockers"]
    assert len(report["report_sha256"]) == 64
    assert verify_research_report(report) is True
    assert pd.Timestamp(report["metrics"]["start"]) >= pd.Timestamp(
        report["research_protocol"]["split"]["confirmation_start"]
    )
    tampered = dict(report)
    tampered["strategy_name"] = "tampered"
    assert verify_research_report(tampered) is False

    target = tmp_path / "report.json"
    assert write_research_report(report, target) == target
    with pytest.raises(FileExistsError, match="immutable"):
        write_research_report(report, target)
