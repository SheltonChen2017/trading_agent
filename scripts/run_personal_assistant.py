"""CLI for briefings, deterministic proposals, and approved paper orders."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca
from assistant.execution_service import execute_approved_paper_proposal
from assistant.policy import load_policy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.storage import AssistantStore
from assistant.strategy_proposals import generate_soxx_soxl_rebalance_proposals
from execution.alpaca_broker import is_configured


def _now_eastern() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _packet(include_events: bool = True):
    return build_decision_packet(
        SAMPLE_POSITIONS,
        SAMPLE_CASH,
        use_live_alpaca=is_configured(),
        include_live_events=include_events,
    )


def _print_briefing(packet) -> None:
    print(f"Decision packet {packet.schema_version} — {packet.generated_at}")
    print(
        f"Portfolio source={packet.portfolio.source} mode={packet.portfolio.account_mode} "
        f"equity=${packet.portfolio.total_equity:,.2f} cash=${packet.portfolio.cash:,.2f}"
    )
    print(
        f"Positions={packet.analytics['position_count']} "
        f"invested={packet.analytics['invested_pct']:.1f}% "
        f"unrealized P&L=${packet.analytics['unrealized_pnl']:,.2f} "
        f"open orders={packet.analytics['open_order_count']}"
    )
    print(
        f"Regime {packet.regime.benchmark_ticker}: "
        f"{packet.regime.trend or 'unavailable'} / "
        f"{packet.regime.volatility_regime or 'unavailable'}"
    )
    for warning in packet.warnings:
        print(f"  ! {warning}")
    for event in sorted(
        (item for item in packet.upcoming_events if item.event_date),
        key=lambda item: item.event_date or "",
    ):
        print(f"  {event.ticker}: {event.event_type} {event.event_date} ({event.days_away} day(s))")
    for finding in packet.signals:
        print(f"  [{finding.status.value}] {finding.label}: {finding.claim}")


def command_briefing(args, store: AssistantStore) -> None:
    packet = _packet(include_events=not args.no_events)
    packet_id = store.save_decision_packet(packet)
    _print_briefing(packet)
    print(f"Persisted decision packet #{packet_id} to {store.path}")


def command_propose(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    packet = _packet(include_events=not args.no_events)
    store.save_decision_packet(packet)
    proposals = generate_risk_reduction_proposals(packet, policy)
    if args.strategy_proposals or policy.enable_strategy_proposals:
        try:
            proposals = proposals + generate_soxx_soxl_rebalance_proposals(packet, policy)
        except Exception as exc:
            print(f"  ! SOXX/SOXL strategy proposal check failed ({exc}); showing risk-reduction proposals only.")
    if not proposals:
        print("No deterministic risk-policy breaches require a trade proposal.")
        return
    for proposal in proposals:
        store.save_proposal(proposal.to_dict())
        intent = proposal.intent
        print(
            f"{proposal.proposal_id} [{proposal.evidence_status}]: {intent.side.upper()} {intent.shares} {intent.ticker} "
            f"at reference ${proposal.reference_price:,.2f}"
        )
        for reason in proposal.reasons:
            print(f"  - {reason}")
        print(
            f"  Preview: position {proposal.expected_impact['position_weight_before_pct']:.1f}% "
            f"-> {proposal.expected_impact['position_weight_after_pct']:.1f}%"
        )
        for uncertainty in proposal.uncertainties:
            print(f"  ? {uncertainty}")
        print(f'  Approval phrase: "APPROVE {proposal.proposal_id}"')


def command_list(args, store: AssistantStore) -> None:
    proposals = store.list_proposals(status=args.status, limit=args.limit)
    if not proposals:
        print("No proposals found.")
        return
    for proposal in proposals:
        intent = proposal["intent"]
        print(
            f"{proposal['proposal_id']} [{proposal['status']}] "
            f"{intent['side'].upper()} {intent['shares']} {intent['ticker']} "
            f"expires={proposal['expires_at']}"
        )


def command_approve(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit("Alpaca paper credentials are required for approval execution.")
    policy = load_policy(args.policy)
    portfolio = build_portfolio_snapshot_from_alpaca()
    order = execute_approved_paper_proposal(
        args.proposal_id,
        args.confirm,
        portfolio,
        policy,
        store,
        now_et=_now_eastern(),
        kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
    )
    print(
        f"Submitted paper order {order['order_id']}: "
        f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal trading assistant")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parent.parent / "assistant" / "default_policy.json"),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    briefing = commands.add_parser("briefing")
    briefing.add_argument("--no-events", action="store_true")
    briefing.set_defaults(handler=command_briefing)

    propose = commands.add_parser("propose")
    propose.add_argument("--no-events", action="store_true")
    propose.add_argument(
        "--strategy-proposals",
        action="store_true",
        help=(
            "Also check the SOXX/SOXL wide-rebalance-band strategy for this run (evidence_status="
            "promising_unconfirmed_strategy, not confirmed -- see assistant/strategy_proposals.py). "
            "Only produces a proposal if you already hold both SOXX and SOXL. Set "
            "'enable_strategy_proposals': true in your policy file instead to make this durable "
            "across runs rather than passing this flag every time."
        ),
    )
    propose.set_defaults(handler=command_propose)

    list_parser = commands.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(handler=command_list)

    approve = commands.add_parser("approve")
    approve.add_argument("proposal_id")
    approve.add_argument("--confirm", required=True)
    approve.set_defaults(handler=command_approve)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = AssistantStore()
    args.handler(args, store)


if __name__ == "__main__":
    main()
