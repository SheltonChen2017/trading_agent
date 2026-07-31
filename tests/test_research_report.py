import dataclasses
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.mandate import load_mandate
from backtest.research_report import (
    ResearchReportError,
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


def test_concurrent_writes_to_the_same_destination_dont_silently_clobber(tmp_path):
    # Independent review, 2026-07-31: write_research_report() used to check
    # target.exists() and then unconditionally os.replace() -- not atomic,
    # so two concurrent writers targeting the same path could both pass the
    # existence check before either wrote, and the second os.replace()
    # would silently replace the first report's content under the same
    # "immutable" identifier with NO exception. os.link() is now the
    # actual publish step: an OS-level atomic create-exclusive that fails
    # closed instead.
    target = tmp_path / "report.json"
    report_a = {"id": "a"}
    report_b = {"id": "b"}
    successes: list[str] = []
    failures: list[str] = []
    barrier = threading.Barrier(2)

    def _write(report, tag):
        barrier.wait()
        try:
            write_research_report(report, target)
            successes.append(tag)
        except FileExistsError:
            failures.append(tag)

    t1 = threading.Thread(target=_write, args=(report_a, "a"))
    t2 = threading.Thread(target=_write, args=(report_b, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one writer wins and one is turned away with an exception --
    # never both "succeeding" (one silently clobbering the other) and
    # never both failing (the destination must end up written).
    assert len(successes) == 1
    assert len(failures) == 1
    winner_report = report_a if successes[0] == "a" else report_b
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == winner_report
    # No stray uuid-suffixed temp file left behind by either writer.
    assert list(tmp_path.glob("*.tmp")) == []


def test_confirmation_window_too_short_blocks_promotion(tmp_path):
    # Independent review, 2026-07-30: compute_portfolio_metrics() only
    # requires >=2 observations and this pipeline runs no significance
    # testing, so a short confirmation window could otherwise clear the
    # mandate's fixed thresholds by chance without anyone noticing the
    # sample was tiny. min_confirmation_sessions is a scoped floor, not
    # full statistical rigor -- it should still fire by default here.
    index = pd.date_range("2025-01-01", periods=100, freq="B")
    frame = _price_frame(index)
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
    kwargs = dict(
        strategy_name="test_strategy",
        equity_curve=equity,
        benchmark_close=frame["close"],
        data={"AAPL": frame},
        parameters={"entry_timing": "next_open"},
        mandate=broad_mandate,
        code_commit="abc123",
        requested_sessions=100,
        point_in_time_data=True,
        discovery_frac=0.6,
        hold_days=5,
        generated_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )
    default_floor = build_research_report(**kwargs)
    assert default_floor["metrics"]["sessions"] < 60
    assert "confirmation_window_too_short" in default_floor["promotion_blockers"]
    assert default_floor["research_protocol"]["min_confirmation_sessions"] == 60

    lowered_floor = build_research_report(
        **{**kwargs, "min_confirmation_sessions": default_floor["metrics"]["sessions"]}
    )
    assert "confirmation_window_too_short" not in lowered_floor["promotion_blockers"]

    with pytest.raises(ResearchReportError, match="min_confirmation_sessions"):
        build_research_report(**{**kwargs, "min_confirmation_sessions": 0})
