"""CLI for briefings, deterministic proposals, and approved paper orders."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca
from assistant.execution_service import (
    PolicyOverridableBlockError,
    execute_approved_paper_proposal,
    reconcile_submission,
    recover_stale_reconciliation,
)
from assistant.policy import load_policy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.research_registry import underfilled_dataset_warning
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
)
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.storage import AssistantStore
from assistant.strategy_proposals import generate_soxx_soxl_rebalance_proposals
from execution.alpaca_broker import is_configured


def _positive_int(value: str) -> int:
    """argparse `type=` for --stale-after-seconds -- a usability guard
    only; assistant.execution_service.recover_stale_reconciliation()
    itself independently validates and is the authoritative check (GPT
    review, 2026-07-29: zero/negative values here would let a genuinely
    in-flight reconciliation be reclaimed immediately)."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {parsed}")
    return parsed


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
        # display_status (GPT review, 2026-07-30): never print a bare
        # "[confirmed]" for a finding that isn't currently production-
        # authoritative -- historical `status` is preserved, only the
        # user-facing label is qualified. This CLI briefing was the last
        # remaining consumer still reading the raw `status` value
        # directly (the Streamlit UI and the now-removed legacy
        # run_morning_briefing.py were already corrected).
        print(f"  [{finding.display_status}] {finding.label}: {finding.claim}")
        if finding.provenance is not None:
            dataset_warning = underfilled_dataset_warning(finding.provenance)
            if dataset_warning:
                print(f"    ! {dataset_warning}")


def command_briefing(args, store: AssistantStore) -> None:
    packet = _packet(include_events=not args.no_events)
    packet_id = store.save_decision_packet(packet)
    _print_briefing(packet)
    print(f"Persisted decision packet #{packet_id} to {store.path}")


def command_risk_check(args, store: AssistantStore) -> None:
    if bool(args.benchmark) != bool(args.move_pct is not None):
        # Usability guard only, not the authoritative check -- mirrors
        # _positive_int's role for --stale-after-seconds: catches an
        # obviously incomplete invocation early with a clear message.
        raise SystemExit("--benchmark and --move-pct must be given together, or not at all.")
    policy = load_policy(args.policy)
    packet = _packet(include_events=False)
    violations = check_policy_compliance(packet.portfolio, policy)
    for violation in violations:
        print(f"  POLICY VIOLATION: {violation}")
    print("Informational summary (not a policy-compliance check -- see any POLICY VIOLATION lines above):")
    print(check_concentration(packet.risk, args.basket))
    for cluster_warning in find_correlated_clusters(packet.portfolio):
        print(f"  ! {cluster_warning}")
    if args.benchmark:
        result = estimate_stress_impact(packet.portfolio, args.benchmark, args.move_pct)
        if result.get("warning"):
            print(f"  ! {result['warning']}")
        if result["total_estimated_impact"] is not None:
            print(
                f"Estimated impact of a {args.move_pct}% move in {args.benchmark}: "
                f"${result['total_estimated_impact']:,.2f}"
            )
        for impact in result["position_impacts"]:
            beta = impact["beta"] if impact["beta"] is not None else "n/a"
            estimated = f"${impact['estimated_impact']:,.2f}" if impact["estimated_impact"] is not None else "n/a"
            print(f"  {impact['ticker']}: beta={beta} estimated_impact={estimated}")


def command_propose(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    packet = _packet(include_events=not args.no_events)
    store.save_decision_packet(packet)
    proposals = generate_risk_reduction_proposals(packet, policy)
    if args.strategy_proposals or policy.enable_strategy_proposals:
        try:
            proposals = proposals + generate_soxx_soxl_rebalance_proposals(packet, policy, store=store)
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
        print(f'  Approve with: approve {proposal.proposal_id} --confirm approve')


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
    try:
        order = execute_approved_paper_proposal(
            args.proposal_id,
            args.confirm,
            portfolio,
            policy,
            store,
            now_et=_now_eastern(),
            kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
            override_policy_violations=args.override,
        )
    except PolicyOverridableBlockError as exc:
        if exc.conditions_changed:
            # GPT review, 2026-07-30: the caller already passed
            # --override, but the freshly revalidated violations no
            # longer match what was reviewed the last time this proposal
            # was blocked -- never silently authorize against a
            # different set than what was actually reviewed.
            raise SystemExit(
                f"{exc}\n\nThe override conditions changed since your previous review. No order was "
                "submitted. Review the updated violations above and rerun with --override again if you "
                "still accept them."
            )
        raise SystemExit(
            f"{exc}\n\nEvery violation above is override-eligible (a risk-preference or "
            f"earnings-calendar call, not unreliable data). Re-run with --override to proceed anyway."
        )
    print(
        f"Submitted paper order {order['order_id']}: "
        f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
    )


def command_reconcile(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit("Alpaca paper credentials are required for reconciliation.")
    order = reconcile_submission(args.proposal_id, store)
    print(
        f"Reconciled {args.proposal_id}: found broker order {order['order_id']} "
        f"[{order.get('status', 'unknown')}] and marked executed."
    )


def command_recover_stale(args, store: AssistantStore) -> None:
    recovered = recover_stale_reconciliation(args.proposal_id, store, stale_after_seconds=args.stale_after_seconds)
    print(
        f"Recovered {args.proposal_id} from a stale 'reconciling' status -> "
        f"{recovered['status']}. Run `reconcile {args.proposal_id}` to resolve it."
    )


def command_prune_packets(args, store: AssistantStore) -> None:
    # Explicit, opt-in cleanup (GPT review, 2026-07-31) -- decision
    # packets have no retention policy otherwise; this never runs
    # automatically, only when the user deliberately invokes it.
    deleted = store.prune_decision_packets_older_than(args.older_than_days)
    print(f"Deleted {deleted} decision packet(s) older than {args.older_than_days} day(s) from {store.path}.")


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

    risk_check = commands.add_parser(
        "risk-check",
        help=(
            "Deterministic concentration/duplication/stress-test answers (assistant/risk_copilot.py) "
            "against the current portfolio -- e.g. 'am I overexposed to tech' or 'what happens if SPY "
            "falls 10%'. --benchmark and --move-pct must be given together to run the stress test."
        ),
    )
    risk_check.add_argument("--basket", default=None, help="Basket name to check concentration for.")
    risk_check.add_argument("--benchmark", default=None, help="Benchmark ticker for the stress test, e.g. SPY.")
    risk_check.add_argument("--move-pct", type=float, default=None, help="Hypothetical benchmark move, e.g. -10.")
    risk_check.set_defaults(handler=command_risk_check)

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
    approve.add_argument("--confirm", required=True, help='Must be exactly "approve" (case-insensitive).')
    approve.add_argument(
        "--override",
        action="store_true",
        help=(
            "Proceed even if the execution gate blocked this on an override-eligible violation "
            "(a concentration cap or the earnings blackout window). Has no effect if any other "
            "violation (stale price, closed market, a bad quote, a duplicate order, the kill "
            "switch, insufficient cash) is also present -- those can never be overridden."
        ),
    )
    approve.set_defaults(handler=command_approve)

    reconcile = commands.add_parser(
        "reconcile",
        help=(
            "Resolve a proposal stuck in 'submitting' or 'submission_unknown' (e.g. after a network "
            "timeout during approval) by re-querying the broker for the same idempotency key. "
            "Re-running 'approve' cannot do this -- the proposal is no longer 'proposed'."
        ),
    )
    reconcile.add_argument("proposal_id")
    reconcile.set_defaults(handler=command_reconcile)

    recover_stale = commands.add_parser(
        "recover-stale",
        help=(
            "Resolve a proposal stranded in 'reconciling' after a process crash left no in-process "
            "handler to run -- only affects a proposal that hasn't been touched in --stale-after-seconds "
            "(default 300); a recent claim is presumed genuinely in-flight and left alone. Recovers to "
            "'submission_unknown', then re-run 'reconcile' to resolve it."
        ),
    )
    recover_stale.add_argument("proposal_id")
    recover_stale.add_argument("--stale-after-seconds", type=_positive_int, default=300)
    recover_stale.set_defaults(handler=command_recover_stale)

    prune_packets = commands.add_parser(
        "prune-packets",
        help=(
            "Explicit, opt-in cleanup for the decision_packets table -- deletes packets older than "
            "--older-than-days. Never runs automatically; decision packets otherwise have no retention "
            "policy and the table grows with every distinct briefing/UI refresh."
        ),
    )
    prune_packets.add_argument("--older-than-days", type=_positive_int, required=True)
    prune_packets.set_defaults(handler=command_prune_packets)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = AssistantStore()
    args.handler(args, store)


if __name__ == "__main__":
    main()
