"""Run the shared-capital scanner simulation and write an immutable report."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from assistant.mandate import load_mandate
from backtest.portfolio_simulator import simulate_portfolio
from backtest.research_report import build_research_report, write_research_report
from data.market_data import fetch_historical


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a reproducible mandate-scored portfolio report."
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=config.UNIVERSE,
        help="Ticker universe; defaults to config.UNIVERSE.",
    )
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--lookback-sessions", type=int, default=config.LOOKBACK_DAYS)
    parser.add_argument("--hold-days", type=int, default=config.BACKTEST_HOLD_DAYS)
    parser.add_argument("--discovery-frac", type=float, default=0.6)
    parser.add_argument(
        "--mandate",
        default=str(
            Path(__file__).resolve().parent.parent
            / "assistant"
            / "default_mandate.json"
        ),
    )
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tickers = sorted({ticker.upper() for ticker in args.tickers})
    data = fetch_historical(tickers, lookback_days=args.lookback_sessions)
    benchmark_data = fetch_historical(
        [args.benchmark.upper()], lookback_days=args.lookback_sessions
    )
    if args.benchmark.upper() not in benchmark_data:
        raise SystemExit(f"benchmark data unavailable: {args.benchmark}")
    missing = sorted(set(tickers) - set(data))
    if missing:
        raise SystemExit(f"price data unavailable for: {missing}")

    parameters = {
        "tickers": tickers,
        "benchmark": args.benchmark.upper(),
        "lookback_sessions": args.lookback_sessions,
        "hold_days": args.hold_days,
        "discovery_frac": args.discovery_frac,
        "entry_timing": "next_open",
        "slippage_pct": config.SLIPPAGE_PCT,
    }
    simulation = simulate_portfolio(
        data,
        hold_days=args.hold_days,
        entry_timing="next_open",
        slippage_pct=config.SLIPPAGE_PCT,
    )
    report = build_research_report(
        strategy_name="shared_capital_dip_up_scanner",
        equity_curve=simulation["equity_curve"],
        benchmark_close=benchmark_data[args.benchmark.upper()]["close"],
        data={**data, args.benchmark.upper(): benchmark_data[args.benchmark.upper()]},
        parameters=parameters,
        mandate=load_mandate(args.mandate),
        code_commit=_current_commit(),
        requested_sessions=args.lookback_sessions,
        point_in_time_data=False,
        discovery_frac=args.discovery_frac,
        hold_days=args.hold_days,
    )
    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.output = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "research_reports"
            / f"portfolio-report-{stamp}.json"
        )
    target = write_research_report(report, args.output)
    print(target)
    print(
        "Mandate passed="
        f"{report['mandate_evaluation']['passed']}; "
        f"promotion blockers={report['promotion_blockers']}"
    )


if __name__ == "__main__":
    main()
