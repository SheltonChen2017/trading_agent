"""General daily portfolio equity history and benchmark-relative reporting.

This is separate from ``paper_evidence``: evidence epochs intentionally demand
post-close paper observations plus fresh ledger reconciliation, while a normal
briefing may be manual/live and intraday. Every briefing valuation is appended;
reporting collapses multiple captures on one date to the latest equity while
summing that day's external flows.

Account equity naturally includes cash dividends received by the broker.
External cash transfers are removed from performance, but dividends are not,
so the account side is total return. Benchmark levels come from
``fetch_historical(auto_adjust=True)`` and are therefore compared on the same
distribution-adjusted basis.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np

from assistant.money import decimal_text, to_decimal
from assistant.portfolio_ledger import ACCOUNT_CASH
from assistant.storage import AssistantStore
from config import MARKET_BENCHMARK_TICKERS
from data.market_data import fetch_historical

_EASTERN = ZoneInfo("America/New_York")


def _parse_at(value: object) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("portfolio snapshot timestamp must be timezone-aware")
    return parsed


def latest_adjusted_benchmark_levels(
    tickers: list[str] | tuple[str, ...] = tuple(MARKET_BENCHMARK_TICKERS),
    *,
    fetcher: Callable[..., dict] = fetch_historical,
) -> tuple[dict[str, str], list[str]]:
    levels: dict[str, str] = {}
    unavailable: list[str] = []
    normalized = list(dict.fromkeys(str(ticker).upper() for ticker in tickers))
    try:
        data = fetcher(normalized, lookback_days=10)
    except Exception:
        return {}, normalized
    for ticker in normalized:
        frame = data.get(ticker)
        if frame is None or frame.empty or "close" not in frame:
            unavailable.append(ticker)
            continue
        try:
            close = to_decimal(frame["close"].iloc[-1], name=f"{ticker} close")
        except ValueError:
            unavailable.append(ticker)
            continue
        if close <= 0:
            unavailable.append(ticker)
            continue
        levels[ticker] = decimal_text(close)
    return levels, unavailable


def _external_flow_since(
    store: AssistantStore,
    *,
    after: datetime | None,
    through: datetime,
) -> Decimal:
    if after is None:
        return Decimal("0")
    result = Decimal("0")
    for posting in store.list_journal_postings():
        if (
            posting.get("source") != "cash_transfer"
            or posting.get("account") != ACCOUNT_CASH
        ):
            continue
        occurred = _parse_at(posting["occurred_at"])
        if after < occurred <= through:
            result += to_decimal(posting["amount"], name="cash transfer")
    return result


def capture_briefing_equity_snapshot(
    store: AssistantStore,
    portfolio: Any,
    *,
    captured_at: datetime | str | None = None,
    account_key: str | None = None,
    benchmark_levels: dict[str, Any] | None = None,
    benchmark_fetcher: Callable[..., dict] = fetch_historical,
) -> dict[str, Any]:
    """Persist an immutable briefing valuation without making briefing fail."""
    when = _parse_at(captured_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    key = (
        str(account_key).strip()
        if account_key is not None
        else (
            f"{portfolio.source}:{portfolio.account_mode}:{portfolio.account_id}"
            if portfolio.account_id
            else f"{portfolio.source}:{portfolio.account_mode}"
        )
    )
    if not key:
        raise ValueError("account_key must be non-empty")

    prior = store.list_portfolio_equity_snapshots(key)
    previous_at = _parse_at(prior[-1]["captured_at"]) if prior else None
    if previous_at is not None and when < previous_at:
        raise ValueError("portfolio equity snapshots must advance in time")
    net_external_flow = _external_flow_since(
        store, after=previous_at, through=when
    )

    unavailable: list[str] = []
    if benchmark_levels is None:
        exact_benchmarks, unavailable = latest_adjusted_benchmark_levels(
            fetcher=benchmark_fetcher
        )
    else:
        exact_benchmarks = {}
        for ticker, value in benchmark_levels.items():
            try:
                amount = to_decimal(value, name=f"{ticker} benchmark")
            except ValueError:
                unavailable.append(str(ticker).upper())
                continue
            if amount <= 0:
                unavailable.append(str(ticker).upper())
                continue
            exact_benchmarks[str(ticker).upper()] = decimal_text(amount)

    record = {
        "schema_version": "1.0",
        "account_key": key,
        "session_date": when.astimezone(_EASTERN).date().isoformat(),
        "captured_at": when.isoformat(),
        "source": portfolio.source,
        "account_mode": portfolio.account_mode,
        "account_id": portfolio.account_id,
        "total_equity": decimal_text(portfolio.total_equity_decimal),
        "cash": decimal_text(portfolio.cash_decimal),
        "net_external_flow": decimal_text(net_external_flow),
        "benchmarks": exact_benchmarks,
        "benchmark_basis": "yfinance_auto_adjust_total_return",
        "benchmark_unavailable": sorted(set(unavailable)),
    }
    return store.append_portfolio_equity_snapshot(record)


def portfolio_performance_report(
    store: AssistantStore, account_key: str
) -> dict[str, Any]:
    """Compute flow-adjusted account return, volatility, drawdown, and excess."""
    snapshots = store.list_portfolio_equity_snapshots(account_key)
    if not snapshots:
        return {
            "account_key": account_key,
            "available": False,
            "reason": "no portfolio equity snapshots",
        }

    grouped: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        session_date = snapshot["session_date"]
        if session_date not in grouped:
            grouped[session_date] = {
                "snapshot": snapshot,
                "net_external_flow": Decimal("0"),
            }
        grouped[session_date]["snapshot"] = snapshot
        grouped[session_date]["net_external_flow"] += to_decimal(
            snapshot["net_external_flow"]
        )
    daily = [grouped[key] for key in sorted(grouped)]
    if len(daily) < 2:
        return {
            "account_key": account_key,
            "available": False,
            "reason": "at least two daily snapshots are required",
            "session_count": len(daily),
        }

    returns: list[float] = []
    wealth = 1.0
    wealth_path = [wealth]
    for previous, current in zip(daily, daily[1:]):
        previous_equity = to_decimal(
            previous["snapshot"]["total_equity"]
        )
        current_equity = to_decimal(current["snapshot"]["total_equity"])
        flow = current["net_external_flow"]
        if previous_equity <= 0:
            continue
        period_return = float(
            (current_equity - flow) / previous_equity - Decimal("1")
        )
        if not math.isfinite(period_return):
            continue
        returns.append(period_return)
        wealth *= 1.0 + period_return
        wealth_path.append(wealth)
    if not returns:
        return {
            "account_key": account_key,
            "available": False,
            "reason": "no finite return intervals",
            "session_count": len(daily),
        }

    peaks = np.maximum.accumulate(np.asarray(wealth_path, dtype=float))
    drawdowns = np.asarray(wealth_path, dtype=float) / peaks - 1.0
    realized_volatility = (
        float(np.std(returns, ddof=1) * np.sqrt(252) * 100)
        if len(returns) >= 2
        else None
    )
    account_return_pct = (wealth - 1.0) * 100.0

    benchmark_tickers = sorted(
        {
            ticker
            for row in daily
            for ticker in row["snapshot"].get("benchmarks", {})
        }
    )
    benchmark_reports: dict[str, dict[str, Any]] = {}
    for ticker in benchmark_tickers:
        first_snapshot = daily[0]["snapshot"]
        last_snapshot = daily[-1]["snapshot"]
        first_value = first_snapshot.get("benchmarks", {}).get(ticker)
        last_value = last_snapshot.get("benchmarks", {}).get(ticker)
        if first_value is None or last_value is None:
            benchmark_reports[ticker] = {
                "available": False,
                "reason": (
                    "adjusted close is missing at an account-period boundary"
                ),
            }
            continue
        start_level = to_decimal(first_value)
        end_level = to_decimal(last_value)
        if start_level <= 0 or end_level <= 0:
            benchmark_reports[ticker] = {
                "available": False,
                "reason": "account-boundary adjusted close is not positive",
            }
            continue
        start_date = first_snapshot["session_date"]
        end_date = last_snapshot["session_date"]
        benchmark_return_pct = float(
            (end_level / start_level - Decimal("1")) * Decimal("100")
        )
        benchmark_reports[ticker] = {
            "available": True,
            "start_session": start_date,
            "end_session": end_date,
            "total_return_pct": round(benchmark_return_pct, 4),
            "excess_return_pct": round(
                account_return_pct - benchmark_return_pct, 4
            ),
            "basis": "distribution-adjusted close",
        }

    return {
        "account_key": account_key,
        "available": True,
        "start_session": daily[0]["snapshot"]["session_date"],
        "end_session": daily[-1]["snapshot"]["session_date"],
        "session_count": len(daily),
        "return_interval_count": len(returns),
        "total_return_pct": round(account_return_pct, 4),
        "annualized_realized_volatility_pct": (
            round(realized_volatility, 4)
            if realized_volatility is not None
            else None
        ),
        "max_drawdown_pct": round(float(drawdowns.min()) * 100.0, 4),
        "benchmarks": benchmark_reports,
        "method": "daily_time_weighted_return_net_of_external_cash_flows",
    }
