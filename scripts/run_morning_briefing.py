"""
Phase 1 read-only assistant: builds today's decision packet from the
sample/manual portfolio, logs it to the trading journal, and prints a
human-readable briefing.

This script has NO trading capability at all — it only reads market data
and this project's own research findings, and prints a summary. No order
submission (see assistant/context_builder.py and assistant/schemas.py for
the architecture this follows).

Uses your live Alpaca account (paper or live, per config.PAPER_TRADING)
automatically once APCA_API_KEY_ID / APCA_API_SECRET_KEY are set as
environment variables; falls back to assistant/sample_portfolio.py's
EXAMPLE positions otherwise, with a clear warning printed either way.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.audit_log import append_decision_packet
from assistant.context_builder import build_decision_packet
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.schemas import EvidenceStatus
from execution.alpaca_broker import is_configured


def _print_section(title: str):
    print(f"\n=== {title} ===")


def main():
    live = is_configured()
    packet = build_decision_packet(SAMPLE_POSITIONS, SAMPLE_CASH, use_live_alpaca=live)
    append_decision_packet(packet)

    print(f"Morning briefing — generated {packet.generated_at}")
    if live:
        print("(Using your live Alpaca account.)")
    else:
        print("(Alpaca not configured — using assistant/sample_portfolio.py's EXAMPLE positions, not real holdings.)")

    _print_section("Market regime")
    r = packet.regime
    print(f"{r.benchmark_ticker}: trend={r.trend or 'unavailable'}, "
          f"volatility_regime={r.volatility_regime or 'unavailable'} "
          f"(trailing {r.trailing_volatility_pct}% daily std as of {r.as_of})")

    _print_section("Portfolio")
    p = packet.portfolio
    print(f"Total equity: ${p.total_equity:,.2f} (cash: ${p.cash:,.2f}, {packet.risk.cash_pct}%)")
    for pos in p.positions:
        print(f"  {pos.ticker:6s} {pos.shares:>8.1f} sh  ${pos.market_value:>10,.2f}  "
              f"({pos.unrealized_pnl_pct:+.1f}% unrealized){'  [leveraged]' if pos.is_leveraged_etf else ''}")

    _print_section("Risk exposure")
    risk = packet.risk
    print(f"Largest single position: {risk.largest_single_position_pct}% of equity")
    print(f"Leveraged ETF exposure: {risk.leveraged_etf_exposure_pct}%")
    if risk.basket_exposure_pct:
        print("Basket exposure (overlapping):")
        for basket, pct in sorted(risk.basket_exposure_pct.items(), key=lambda kv: -kv[1]):
            print(f"  {basket:25s} {pct}%")
    if risk.concentration_warnings:
        print("Concentration warnings:")
        for w in risk.concentration_warnings:
            print(f"  ! {w}")

    _print_section("Relevant research evidence")
    for s in packet.signals:
        marker = {
            EvidenceStatus.CONFIRMED: "[CONFIRMED]",
            EvidenceStatus.PROMISING_UNCONFIRMED: "[PROMISING/UNCONFIRMED]",
            EvidenceStatus.EXPLORATORY: "[EXPLORATORY]",
            EvidenceStatus.REJECTED: "[REJECTED]",
            EvidenceStatus.UNAVAILABLE: "[UNAVAILABLE]",
        }[s.status]
        print(f"{marker} {s.label}")
        print(f"    Claim: {s.claim}")
        print(f"    {s.detail}")

    _print_section("Upcoming events")
    if all(e.status == EvidenceStatus.UNAVAILABLE for e in packet.upcoming_events):
        print("No live earnings/macro-event calendar wired up yet — status UNAVAILABLE for all held tickers.")
    else:
        for e in packet.upcoming_events:
            print(f"  {e.ticker}: {e.event_type} in {e.days_away} days [{e.status.value}]")

    if packet.warnings:
        _print_section("Warnings")
        for w in packet.warnings:
            print(f"  ! {w}")

    print("\nLogged to assistant/decision_log.jsonl")


if __name__ == "__main__":
    main()
