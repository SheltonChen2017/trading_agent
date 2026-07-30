"""CLI for briefings, deterministic proposals, and approved paper orders."""
from __future__ import annotations

import argparse
import json
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
from assistant.mandate import (
    compute_mandate_fingerprint,
    evaluate_live_promotion,
    load_mandate,
)
from assistant.operations import (
    append_alerts_jsonl,
    run_backup_restore_drill,
    run_operational_check,
)
from assistant.order_reconciler import monitor_orders, reconcile_nonterminal_orders
from assistant.portfolio_ledger import (
    bootstrap_opening_snapshot,
    ledger_balances,
    reconcile_snapshot,
    sync_app_fills,
)
from assistant.readiness import transaction_readiness
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
from assistant.strategy_proposals import CONFIGURED_LEVERAGED_PAIRS, generate_leveraged_pair_rebalance_proposals
from backtest.research_report import verify_research_report
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


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be a non-negative integer, got {value!r}"
        )
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"must be a non-negative integer, got {parsed}"
        )
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
        for pair_config in CONFIGURED_LEVERAGED_PAIRS:
            try:
                proposals = proposals + generate_leveraged_pair_rebalance_proposals(
                    packet, policy, pair_config, store=store
                )
            except Exception as exc:
                print(
                    f"  ! {pair_config.stable_ticker}/{pair_config.leveraged_ticker} strategy proposal "
                    f"check failed ({exc}); skipping this pair."
                )
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
    proposal = store.get_proposal(args.proposal_id)
    print(
        f"Reconciled {args.proposal_id}: found broker order {order['order_id']} "
        f"[{order.get('status', 'unknown')}]; proposal is now {proposal['status']}."
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


def command_sync_orders(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    result = reconcile_nonterminal_orders(
        store,
        cancel_stale=args.cancel_stale,
        max_order_age_minutes=policy.max_order_age_minutes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_monitor_orders(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    print("Running startup reconciliation, then listening for Alpaca trade updates.")
    monitor_orders(
        store,
        cancel_stale=args.cancel_stale,
        max_order_age_minutes=policy.max_order_age_minutes,
        poll_interval_seconds=args.poll_seconds,
    )


def command_readiness(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    report = transaction_readiness(store, policy, check_broker=not args.offline)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ready"]:
        raise SystemExit(2)


def command_kill_switch(args, store: AssistantStore) -> None:
    if args.state == "status":
        print(json.dumps(store.get_kill_switch(), indent=2, sort_keys=True))
        return
    active = args.state == "on"
    reason = args.reason or ("Manually activated from CLI." if active else "Manually cleared from CLI.")
    store.set_kill_switch(active, reason=reason)
    print(json.dumps(store.get_kill_switch(), indent=2, sort_keys=True))


def command_backup_db(args, store: AssistantStore) -> None:
    destination = args.destination
    if destination is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = store.path.parent / "backups" / f"trading_assistant-{timestamp}.db"
    target = store.backup_to(destination)
    print(f"Database backup created: {target}")


def command_mandate_status(args, store: AssistantStore) -> None:
    mandate = load_mandate(args.mandate)
    payload = mandate.to_dict()
    payload["computed_fingerprint"] = compute_mandate_fingerprint(mandate)
    payload["live_trading_enabled"] = False
    print(json.dumps(payload, indent=2, sort_keys=True))


def command_ledger_bootstrap(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required for ledger bootstrap."
        )
    snapshot = build_portfolio_snapshot_from_alpaca()
    result = bootstrap_opening_snapshot(
        store, snapshot, confirmation=args.confirm
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_ledger_sync(args, store: AssistantStore) -> None:
    result = sync_app_fills(store)
    balances = ledger_balances(store)
    result["cash"] = str(balances["cash"])
    result["shares"] = {
        ticker: str(qty)
        for ticker, qty in sorted(balances["shares"].items())
    }
    print(json.dumps(result, indent=2, sort_keys=True))


def command_ledger_reconcile(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required for ledger reconciliation."
        )
    if not args.no_sync:
        sync_app_fills(store)
    snapshot = build_portfolio_snapshot_from_alpaca()
    report = reconcile_snapshot(store, snapshot)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["matched"]:
        raise SystemExit(2)


def command_operations_check(args, store: AssistantStore) -> None:
    policy = load_policy(args.policy)
    report = run_operational_check(
        store, policy, check_broker=not args.offline
    )
    if args.alerts_jsonl and report["alerts"]:
        append_alerts_jsonl(report["alerts"], args.alerts_jsonl)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["healthy"]:
        raise SystemExit(2)


def command_list_alerts(args, store: AssistantStore) -> None:
    status = None if args.all else "open"
    print(
        json.dumps(
            store.list_operational_alerts(status=status, limit=args.limit),
            indent=2,
            sort_keys=True,
        )
    )


def command_ack_alert(args, store: AssistantStore) -> None:
    if not store.acknowledge_operational_alert(args.alert_id):
        raise SystemExit(f"Open alert not found: {args.alert_id}")
    print(f"Acknowledged alert {args.alert_id}.")


def command_recovery_drill(args, store: AssistantStore) -> None:
    destination = args.destination
    if destination is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = (
            store.path.parent
            / "backups"
            / f"recovery-drill-{timestamp}.db"
        )
    report = run_backup_restore_drill(store, destination)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(2)


def command_promotion_status(args, store: AssistantStore) -> None:
    mandate = load_mandate(args.mandate)
    report = json.loads(args.research_report.read_text(encoding="utf-8"))
    if not verify_research_report(report):
        raise SystemExit(
            "Research report hash is missing or invalid; refusing promotion review."
        )
    latest_reconciliation = store.get_latest_ledger_reconciliation()
    unreconciled = (
        int(latest_reconciliation.get("mismatch_count", 0))
        if latest_reconciliation is not None
        else 1
    )
    critical_alerts = sum(
        alert["severity"] == "critical"
        for alert in store.list_operational_alerts(status="open", limit=1000)
    )
    fills = store.list_fills()
    paper_orders = len({fill["order_id"] for fill in fills})
    restore_drill = store.get_system_state(
        "last_backup_restore_drill", default={}
    )
    operations_heartbeat = store.get_system_state(
        "operations_heartbeat", default={}
    )
    heartbeat_at = None
    try:
        heartbeat_at = datetime.fromisoformat(
            str(operations_heartbeat.get("at", "")).replace("Z", "+00:00")
        )
        if heartbeat_at.tzinfo is None:
            heartbeat_at = None
    except ValueError:
        heartbeat_at = None
    heartbeat_fresh = (
        heartbeat_at is not None
        and datetime.now(timezone.utc) - heartbeat_at <= timedelta(minutes=5)
    )
    result = evaluate_live_promotion(
        mandate,
        metric_report=report.get("metrics") or {},
        paper_sessions=args.paper_sessions,
        paper_orders=paper_orders,
        unreconciled_items=unreconciled,
        critical_alerts=critical_alerts,
        research_reproduced=args.research_reproduced,
        point_in_time_data=bool(
            (report.get("research_protocol") or {}).get(
                "point_in_time_data"
            )
        ),
        backup_restore_drill_passed=bool(restore_drill.get("passed")),
        operational_health_passed=bool(
            operations_heartbeat.get("healthy") and heartbeat_fresh
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ready_for_live_canary_review"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal trading assistant")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parent.parent / "assistant" / "default_policy.json"),
    )
    parser.add_argument(
        "--mandate",
        default=str(
            Path(__file__).resolve().parent.parent
            / "assistant"
            / "default_mandate.json"
        ),
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
            "falls 10%%'. --benchmark and --move-pct must be given together to run the stress test."
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
            "Also check the configured leveraged-pair rebalance strategies for this run "
            "(see assistant.strategy_proposals.CONFIGURED_LEVERAGED_PAIRS; none carry a "
            "'confirmed' evidence_status -- see assistant/strategy_proposals.py). Only produces a "
            "proposal for a pair if you already hold both of its tickers. Set "
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

    sync_orders = commands.add_parser(
        "sync-orders",
        help="Poll Alpaca once and reconcile every nonterminal assistant order.",
    )
    sync_orders.add_argument(
        "--cancel-stale",
        action="store_true",
        help="Request cancellation for accepted/partially-filled orders older than the policy cap.",
    )
    sync_orders.set_defaults(handler=command_sync_orders)

    monitor = commands.add_parser(
        "monitor-orders",
        help="Run startup reconciliation, then continuously consume Alpaca trade updates.",
    )
    monitor.add_argument(
        "--cancel-stale",
        action="store_true",
        help="Request stale-order cancellation during startup reconciliation.",
    )
    monitor.add_argument(
        "--poll-seconds",
        type=_positive_int,
        default=30,
        help="Polling fallback interval while the trade-update stream runs (default: 30).",
    )
    monitor.set_defaults(handler=command_monitor_orders)

    readiness = commands.add_parser(
        "readiness",
        help="Check policy, SQLite integrity, reconciliation freshness, budgets, and broker state.",
    )
    readiness.add_argument(
        "--offline",
        action="store_true",
        help="Skip the live broker-account check; all local checks still run.",
    )
    readiness.set_defaults(handler=command_readiness)

    kill_switch = commands.add_parser(
        "kill-switch",
        help="Persistently enable, disable, or inspect the execution kill switch.",
    )
    kill_switch.add_argument("state", choices=("on", "off", "status"))
    kill_switch.add_argument("--reason")
    kill_switch.set_defaults(handler=command_kill_switch)

    backup = commands.add_parser("backup-db", help="Create a consistent SQLite backup.")
    backup.add_argument("destination", nargs="?", type=Path)
    backup.set_defaults(handler=command_backup_db)

    mandate_status = commands.add_parser(
        "mandate-status",
        help="Validate and display the machine-readable portfolio mandate.",
    )
    mandate_status.set_defaults(handler=command_mandate_status)

    ledger_bootstrap = commands.add_parser(
        "ledger-bootstrap",
        help="Record the current Alpaca snapshot as the journal opening balance.",
    )
    ledger_bootstrap.add_argument(
        "--confirm",
        required=True,
        help='Must be exactly "bootstrap" (case-insensitive).',
    )
    ledger_bootstrap.set_defaults(handler=command_ledger_bootstrap)

    ledger_sync = commands.add_parser(
        "ledger-sync",
        help="Idempotently append post-bootstrap app fills to the journal.",
    )
    ledger_sync.set_defaults(handler=command_ledger_sync)

    ledger_reconcile = commands.add_parser(
        "ledger-reconcile",
        help="Compare journal cash/positions with the current Alpaca snapshot.",
    )
    ledger_reconcile.add_argument(
        "--no-sync",
        action="store_true",
        help="Do not sync app fills before comparing the snapshot.",
    )
    ledger_reconcile.set_defaults(handler=command_ledger_reconcile)

    operations_check = commands.add_parser(
        "operations-check",
        help="Run readiness, accounting, backup and recovery health checks.",
    )
    operations_check.add_argument("--offline", action="store_true")
    operations_check.add_argument("--alerts-jsonl", type=Path)
    operations_check.set_defaults(handler=command_operations_check)

    list_alerts = commands.add_parser(
        "alerts", help="List durable operational alerts."
    )
    list_alerts.add_argument("--all", action="store_true")
    list_alerts.add_argument("--limit", type=_positive_int, default=100)
    list_alerts.set_defaults(handler=command_list_alerts)

    acknowledge = commands.add_parser(
        "ack-alert", help="Acknowledge one open operational alert."
    )
    acknowledge.add_argument("alert_id", type=_positive_int)
    acknowledge.set_defaults(handler=command_ack_alert)

    recovery_drill = commands.add_parser(
        "recovery-drill",
        help="Create, restore and verify a database backup.",
    )
    recovery_drill.add_argument("destination", nargs="?", type=Path)
    recovery_drill.set_defaults(handler=command_recovery_drill)

    promotion = commands.add_parser(
        "promotion-status",
        help=(
            "Evaluate evidence for a human live-canary review. This never "
            "enables live trading."
        ),
    )
    promotion.add_argument("research_report", type=Path)
    promotion.add_argument(
        "--paper-sessions", type=_non_negative_int, required=True
    )
    promotion.add_argument(
        "--research-reproduced",
        action="store_true",
        help="Attest that the report was independently reproduced.",
    )
    promotion.set_defaults(handler=command_promotion_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = AssistantStore()
    args.handler(args, store)


if __name__ == "__main__":
    main()
