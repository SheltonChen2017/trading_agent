from __future__ import annotations

from datetime import datetime, timedelta, timezone

from assistant.context_builder import build_portfolio_snapshot
from assistant.portfolio_history import (
    capture_briefing_equity_snapshot,
    portfolio_performance_report,
)
from assistant.portfolio_ledger import record_cash_transfer
from assistant.storage import AssistantStore


DAY1 = datetime(2026, 7, 27, 21, 0, tzinfo=timezone.utc)


def _portfolio(equity: float, *, account_id: str | None = None):
    return build_portfolio_snapshot(
        [],
        cash=equity,
        source="alpaca",
        account_mode="paper",
        account_id=account_id,
    )


def test_daily_history_computes_account_total_return_and_benchmark_excess(
    tmp_path,
):
    store = AssistantStore(tmp_path / "assistant.db")
    capture_briefing_equity_snapshot(
        store,
        _portfolio(100),
        captured_at=DAY1,
        account_key="paper-account",
        benchmark_levels={"SPY": 100, "QQQ": 100},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(110),
        captured_at=DAY1 + timedelta(days=1),
        account_key="paper-account",
        benchmark_levels={"SPY": 105, "QQQ": 120},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(105),
        captured_at=DAY1 + timedelta(days=2),
        account_key="paper-account",
        benchmark_levels={"SPY": 110, "QQQ": 110},
    )

    report = portfolio_performance_report(store, "paper-account")
    assert report["available"]
    assert report["total_return_pct"] == 5.0
    assert report["max_drawdown_pct"] < 0
    assert report["benchmarks"]["SPY"]["total_return_pct"] == 10.0
    assert report["benchmarks"]["SPY"]["excess_return_pct"] == -5.0


def test_external_deposit_is_not_mistaken_for_return(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    capture_briefing_equity_snapshot(
        store,
        _portfolio(100),
        captured_at=DAY1,
        account_key="paper-account",
        benchmark_levels={},
    )
    record_cash_transfer(
        store,
        external_id="deposit-1",
        amount=50,
        occurred_at=(DAY1 + timedelta(hours=1)).isoformat(),
        description="deposit",
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(150),
        captured_at=DAY1 + timedelta(days=1),
        account_key="paper-account",
        benchmark_levels={},
    )

    report = portfolio_performance_report(store, "paper-account")
    assert report["available"]
    assert report["total_return_pct"] == 0.0


def test_multiple_briefings_same_day_use_latest_equity(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    capture_briefing_equity_snapshot(
        store,
        _portfolio(100),
        captured_at=DAY1,
        account_key="paper-account",
        benchmark_levels={"SPY": 100},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(102),
        captured_at=DAY1 + timedelta(hours=1),
        account_key="paper-account",
        benchmark_levels={"SPY": 101},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(112.2),
        captured_at=DAY1 + timedelta(days=1),
        account_key="paper-account",
        benchmark_levels={"SPY": 111.1},
    )

    report = portfolio_performance_report(store, "paper-account")
    assert report["session_count"] == 2
    assert report["total_return_pct"] == 10.0
    assert report["benchmarks"]["SPY"]["total_return_pct"] == 10.0


def test_benchmark_excess_requires_same_account_period_boundaries(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    capture_briefing_equity_snapshot(
        store,
        _portfolio(100),
        captured_at=DAY1,
        account_key="paper-account",
        benchmark_levels={},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(105),
        captured_at=DAY1 + timedelta(days=1),
        account_key="paper-account",
        benchmark_levels={"SPY": 100},
    )
    capture_briefing_equity_snapshot(
        store,
        _portfolio(110),
        captured_at=DAY1 + timedelta(days=2),
        account_key="paper-account",
        benchmark_levels={"SPY": 105},
    )

    report = portfolio_performance_report(store, "paper-account")
    assert report["total_return_pct"] == 10.0
    assert not report["benchmarks"]["SPY"]["available"]
    assert "boundary" in report["benchmarks"]["SPY"]["reason"]


def test_default_history_key_is_bound_to_broker_account_id(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    first = capture_briefing_equity_snapshot(
        store,
        _portfolio(100, account_id="account-1"),
        captured_at=DAY1,
        benchmark_levels={},
    )
    second = capture_briefing_equity_snapshot(
        store,
        _portfolio(200, account_id="account-2"),
        captured_at=DAY1,
        benchmark_levels={},
    )

    assert first["account_key"] == "alpaca:paper:account-1"
    assert second["account_key"] == "alpaca:paper:account-2"
    assert len(store.list_portfolio_equity_snapshots(first["account_key"])) == 1
    assert len(store.list_portfolio_equity_snapshots(second["account_key"])) == 1


def test_history_limit_returns_the_newest_rows_in_chronological_order(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    for day, equity in enumerate((100, 101, 102)):
        capture_briefing_equity_snapshot(
            store,
            _portfolio(equity),
            captured_at=DAY1 + timedelta(days=day),
            account_key="paper-account",
            benchmark_levels={},
        )

    latest = store.list_portfolio_equity_snapshots(
        "paper-account", limit=2
    )
    assert [row["total_equity"] for row in latest] == ["101", "102"]
