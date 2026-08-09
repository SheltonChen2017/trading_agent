"""CLI for briefings, deterministic proposals, and approved paper orders."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.kill_switch import env_kill_switch_active
from assistant.llm import ProjectionError, project_committee_input
from assistant.llm.anthropic_provider import (
    AnthropicCommitteeProvider,
    is_anthropic_committee_configured,
    is_anthropic_committee_experiment_enabled,
)
from assistant.llm.committee_service import run_committee_review_and_record
from assistant.platform_readiness import BLOCKED, build_platform_readiness
from assistant.runtime_identity import RuntimeIdentityError, current_commit
from assistant.context_builder import (
    build_decision_packet,
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
)
from assistant.attribution import (
    DEFAULT_MINIMUM_OBSERVATIONS,
    AttributionError,
    AttributionPoint,
    evaluate_attribution,
)
from assistant.cash_reporting import CashReportError, evaluate_idle_cash
from assistant.money import decimal_text, to_decimal as _to_decimal_money
from assistant.corporate_actions import tax_ledger_with_coverage
from assistant.execution_service import (
    PolicyOverridableBlockError,
    execute_approved_paper_proposal,
    reconcile_submission,
    recover_stale_claim,
    recover_stale_reconciliation,
)
import config
from assistant.policy import (
    compute_policy_fingerprint,
    load_policy,
    resolve_policy_path,
)
from assistant.mandate import (
    compute_mandate_fingerprint,
    evaluate_live_promotion,
    load_mandate,
)
from assistant.operations import (
    append_alerts_jsonl,
    ensure_recent_database_backup,
    run_backup_restore_drill,
    run_operational_check,
)
from assistant.process_singleton import (
    ProcessSingletonError,
    acquire_process_singleton,
)
from assistant.order_reconciler import (
    cancel_all_open_orders,
    cancel_assistant_order,
    monitor_orders,
    reconcile_nonterminal_orders,
)
from assistant.portfolio_ledger import (
    bind_legacy_alpaca_account,
    bootstrap_opening_snapshot,
    ledger_balances,
    record_cash_transfer,
    record_dividend,
    record_fee,
    record_split,
    reconcile_snapshot,
    sync_app_fills,
)
from assistant.macro_context import build_descriptive_macro_context
from assistant.portfolio_history import (
    capture_briefing_equity_snapshot,
    portfolio_performance_report,
)
from assistant.paper_evidence import (
    REQUIRED_PROMOTION_DRILLS,
    build_paper_lineage,
    capture_paper_account_observation,
    paper_evidence_summary,
    paper_session_schedule,
    record_operational_drill,
    start_paper_evidence_epoch,
)
from assistant.readiness import transaction_readiness
from assistant.tax_reporting import (
    TaxReportError,
    build_annual_tax_report,
    render_tax_report_csv,
    render_tax_report_json,
)
from assistant.proposals import generate_risk_reduction_proposals
from assistant.research_registry import underfilled_dataset_warning
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
    portfolio_risk_decomposition,
)
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.storage import (
    AssistantStore,
    configured_db_path,
    verify_database_schema,
)
from assistant.strategy_proposals import CONFIGURED_LEVERAGED_PAIRS, generate_leveraged_pair_rebalance_proposals
from backtest.research_report import verify_research_report
from execution.alpaca_broker import get_account, is_configured


_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_EASTERN = ZoneInfo("America/New_York")


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


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be a positive number, got {value!r}"
        )
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"must be a positive number, got {parsed}"
        )
    return parsed


def _current_commit(*, require_clean: bool) -> str:
    """Strict runtime identity; see assistant/runtime_identity.py."""
    try:
        return current_commit(require_clean=require_clean)
    except RuntimeIdentityError as exc:
        raise SystemExit(str(exc)) from exc


def _cli_policy_path(args) -> str:
    """Resolve the governing policy path for a CLI invocation.

    ``--policy`` defaults to ``None`` so parser construction cannot raise on
    a broken ``TRADING_ASSISTANT_POLICY``. ``main()`` binds the path before
    dispatch, but tests (and any direct handler call) still see ``None``
    after ``parse_args()``. Resolving here keeps handlers usable without
    reintroducing the eager argparse default.
    """
    raw = getattr(args, "policy", None)
    if raw is None:
        return str(resolve_policy_path())
    return str(Path(raw).expanduser())


def _active_runtime_lineage(
    store: AssistantStore, args
) -> dict[str, str]:
    epoch = store.get_active_paper_evidence_epoch()
    if epoch is None:
        raise SystemExit("No active paper evidence epoch.")
    recorded = epoch["lineage"]
    mandate = load_mandate(args.mandate)
    policy = load_policy(_cli_policy_path(args))
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required to verify evidence lineage."
        )
    account = get_account()
    if not account["paper"]:
        raise SystemExit(
            "Paper evidence lineage cannot be verified against a live account."
        )
    current = build_paper_lineage(
        code_commit=_current_commit(require_clean=True),
        mandate_fingerprint=compute_mandate_fingerprint(mandate),
        policy_fingerprint=compute_policy_fingerprint(policy),
        strategy_id=recorded["strategy_id"],
        strategy_version=recorded["strategy_version"],
        model_id=recorded["model_id"],
        broker_account_id=account["account_id"],
    )
    if current != recorded:
        raise SystemExit(
            "Active evidence lineage differs from the current runtime; "
            "close this epoch and start a new one."
        )
    return current


def _benchmark_close_for_session(ticker: str, session_date: str) -> float:
    from data.market_data import fetch_historical

    normalized = ticker.upper()
    history = fetch_historical([normalized], lookback_days=10)
    if normalized not in history:
        raise SystemExit(f"Benchmark data unavailable for {normalized}.")
    frame = history[normalized]
    dates = [
        (
            index.date().isoformat()
            if callable(getattr(index, "date", None))
            else str(index)[:10]
        )
        for index in frame.index
    ]
    matching = frame.loc[[date == session_date for date in dates]]
    if matching.empty:
        raise SystemExit(
            f"No {normalized} close is available for {session_date}."
        )
    close = float(matching.iloc[-1]["close"])
    if close <= 0:
        raise SystemExit(
            f"Invalid {normalized} close for {session_date}: {close}"
        )
    return close


def _now_eastern() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _packet(include_events: bool = True, store: AssistantStore | None = None):
    return build_decision_packet(
        SAMPLE_POSITIONS,
        SAMPLE_CASH,
        use_live_alpaca=is_configured(),
        include_live_events=include_events,
        # GR-4: when a store is available, the market-data fetch is
        # recorded (success or failure) so provider health and bar
        # freshness derive from evidence rather than silence.
        store=store,
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
    # Operational warnings are durable and this command is their routed
    # delivery surface. Render them before any fallible market/account work
    # so the condition that broke the briefing cannot hide the warning too.
    _print_batched_warnings(store)
    packet = _packet(include_events=not args.no_events, store=store)
    packet_id = store.save_decision_packet(packet)
    history_note = None
    try:
        captured = capture_briefing_equity_snapshot(
            store,
            packet.portfolio,
            captured_at=packet.generated_at,
        )
        report = portfolio_performance_report(
            store, captured["account_key"]
        )
        if report.get("available"):
            history_note = (
                f"Portfolio total return {report['total_return_pct']:+.2f}% "
                f"since {report['start_session']}; "
                f"max drawdown {report['max_drawdown_pct']:.2f}%."
            )
    except Exception as exc:
        # History is observability, never a prerequisite for a briefing.
        history_note = f"Portfolio history capture unavailable: {exc}"
    _print_briefing(packet)
    macro_context = build_descriptive_macro_context()
    if macro_context.get("available"):
        print("Descriptive macro context (not predictive):")
        for indicator in macro_context["indicators"]:
            print(
                f"  {indicator['label']}: {indicator['direction']} "
                f"(20-session change {indicator['change_20_sessions']:+.4f})"
            )
    else:
        print(
            "  Macro context unavailable: "
            + str(macro_context.get("reason", "insufficient data"))
        )
    if history_note:
        print(f"  History: {history_note}")
    print(f"Persisted decision packet #{packet_id} to {store.path}")


def _print_batched_warnings(store: AssistantStore) -> None:
    """GR-5 severity routing (owner decision 2026-08-03): warnings are NOT
    delivered immediately -- the daily briefing is their delivery surface,
    so omitting them here would leave warnings surfaced nowhere at all."""
    from assistant.alert_delivery import pending_briefing_alerts

    batched_warnings = pending_briefing_alerts(store)
    if not batched_warnings:
        return
    print(
        f"Open operational warnings ({len(batched_warnings)}, batched here by policy):"
    )
    for alert in batched_warnings:
        print(
            f"  [{alert['category']}] {alert['message']} "
            f"(x{alert['occurrences']}, last {alert['last_seen_at'][:19]})"
        )


def command_risk_check(args, store: AssistantStore) -> None:
    if bool(args.benchmark) != bool(args.move_pct is not None):
        # Usability guard only, not the authoritative check -- mirrors
        # _positive_int's role for --stale-after-seconds: catches an
        # obviously incomplete invocation early with a clear message.
        raise SystemExit("--benchmark and --move-pct must be given together, or not at all.")
    policy = load_policy(_cli_policy_path(args))
    packet = _packet(include_events=False, store=store)
    violations = check_policy_compliance(packet.portfolio, policy)
    for violation in violations:
        print(f"  POLICY VIOLATION: {violation}")
    print("Informational summary (not a policy-compliance check -- see any POLICY VIOLATION lines above):")
    print(check_concentration(packet.risk, args.basket))
    for cluster_warning in find_correlated_clusters(packet.portfolio):
        print(f"  ! {cluster_warning}")
    decomposition = portfolio_risk_decomposition(packet.portfolio)
    if decomposition.get("available"):
        print(
            "Empirical portfolio risk: "
            f"beta={decomposition['portfolio_beta'] if decomposition['portfolio_beta'] is not None else 'n/a'} "
            f"annualized volatility={decomposition['annualized_volatility_pct']:.2f}%"
        )
        for cluster in decomposition["correlated_clusters"]:
            print(
                "  ! Correlated cluster "
                f"{'/'.join(cluster['tickers'])}: "
                f"{cluster['combined_weight_pct']:.2f}% of equity"
            )
    else:
        print(f"  ! Empirical risk decomposition unavailable: {decomposition.get('reason')}")
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


def command_idle_cash(args, store: AssistantStore | None = None) -> None:
    """GR-7b. Read-only: measures cash, never proposes deploying it.

    Deliberately does NOT call ``_packet(..., store=store)``: that path
    records GR-4 provider-fetch rows. A reporting command must leave the
    operator database unchanged, including evidence tables. Portfolio comes
    from a live Alpaca snapshot when configured, otherwise the sample
    portfolio — never a decision-packet rebuild that writes.
    """
    del store  # deliberately unused; this report needs no database
    policy = load_policy(_cli_policy_path(args))
    mandate = load_mandate(args.mandate)
    # A broker outage must degrade the REPORT, not dump a traceback on the
    # operator -- the same rule GR-7a's Reports page already applies to
    # coverage verification, and the same guard the UI sibling of this
    # panel carries. Without this, `idle-cash` during an Alpaca incident
    # ends in a stack trace, which in a scheduled context is
    # indistinguishable from the tool itself being broken.
    try:
        if is_configured():
            portfolio = build_portfolio_snapshot_from_alpaca()
        else:
            portfolio = build_portfolio_snapshot(
                SAMPLE_POSITIONS, SAMPLE_CASH, source="manual", account_mode="manual"
            )
    except Exception as exc:
        raise SystemExit(
            f"Cannot report idle cash: portfolio snapshot unavailable "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    try:
        report = evaluate_idle_cash(
            portfolio,
            policy,
            mandate,
            measured_annualized_volatility_pct=args.measured_volatility_pct,
        )
    except CashReportError as exc:
        raise SystemExit(f"Cannot report idle cash: {exc}") from exc

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    totals = report["totals"]
    bounds = report["policy_bounds"]
    objective = report["mandate_objective"]
    print(f"Idle-cash report ({report['as_of']}, {report['account_mode']})")
    if not report["exact_numerics"]:
        print("  ! figures derive from display-rounded values, not exact broker decimals")
    print(
        f"  equity ${totals['total_equity']} = cash ${totals['cash']} "
        f"({totals['cash_pct']}%) + invested ${totals['invested']} "
        f"({totals['invested_pct']}%)"
    )
    print(
        f"  policy: reserve floor ${bounds['reserve_floor']} "
        f"({bounds['min_cash_reserve_pct']}%), exposure ceiling "
        f"${bounds['exposure_ceiling']} ({bounds['max_total_exposure_pct']}%)"
    )
    if bounds["reserve_floor_breached"]:
        print(f"  ! cash is BELOW the reserve floor by ${bounds['cash_above_reserve'].lstrip('-')}")
    if bounds["policy_headroom"] is None:
        print(
            "  headroom unavailable -- "
            f"{bounds['policy_headroom_unavailable_reason']}"
        )
    else:
        print(
            f"  headroom ${bounds['policy_headroom']} "
            f"(limited by {bounds['binding_constraint']}) -- room the policy "
            "leaves, not a suggestion to use it"
        )
    band = (
        f"{objective['target_annualized_volatility_min_pct']}-"
        f"{objective['target_annualized_volatility_max_pct']}%"
    )
    measured = objective["measured"]
    if measured["available"]:
        verdict = "inside" if measured["within_mandate_band"] else "OUTSIDE"
        print(
            f"  mandate volatility band {band}: measured "
            f"{measured['annualized_volatility_pct']}% is {verdict} the band"
        )
    else:
        print(f"  mandate volatility band {band}: {measured['unavailable_reason']}")
    if objective["required_invested_volatility_pct"] is not None:
        print(
            f"  at {totals['invested_pct']}% invested, holdings would need "
            f"{objective['required_invested_volatility_pct']}% volatility to reach "
            f"the {objective['target_annualized_volatility_min_pct']}% floor"
        )
    else:
        print(f"  required-volatility figure unavailable: {objective['required_unavailable_reason']}")
    if objective["required_invested_volatility_at_policy_ceiling_pct"] is not None:
        print(
            "  even at the policy exposure ceiling it would need "
            f"{objective['required_invested_volatility_at_policy_ceiling_pct']}%"
        )
    print("  reporting only; no order was created, sized, or approved")


def command_attribution(args, store: AssistantStore) -> None:
    """GR-7c. Read-only: reads recorded equity snapshots, writes nothing.

    Every input comes from `portfolio_equity_snapshots`, which the
    observation path already records. This command deliberately does not
    fetch prices or rebuild a decision packet -- attribution over a period
    must use the values captured DURING that period, not today's view of
    them, and a fetch here would also write provider evidence from a
    reporting command (GR7BREV-001/002).
    """
    # One account per report, never pooled. The operator database holds both
    # the live paper account and `manual:manual` rows from sample-portfolio
    # runs; attributing across them would blend two different portfolios
    # into one return series.
    available_keys = store.list_portfolio_equity_account_keys()
    if not available_keys:
        raise SystemExit("Cannot attribute: no equity snapshots recorded yet.")
    if args.account_key:
        account_key = args.account_key
        if account_key not in available_keys:
            raise SystemExit(
                f"Cannot attribute: no snapshots for {account_key!r}. "
                f"Available: {', '.join(available_keys)}"
            )
    else:
        broker_keys = [key for key in available_keys if not key.startswith("manual:")]
        if len(broker_keys) == 1:
            account_key = broker_keys[0]
        elif len(available_keys) == 1:
            account_key = available_keys[0]
        else:
            raise SystemExit(
                "Cannot attribute: several accounts have snapshots; pass "
                f"--account-key. Available: {', '.join(available_keys)}"
            )

    rows = store.list_portfolio_equity_snapshots(account_key, limit=args.limit)
    points: list[AttributionPoint] = []
    skipped: list[str] = []
    # Skipping a snapshot that carried an external flow silently REINTRODUCES
    # the deposit-as-gain error: the chain then links across the gap and reads
    # the deposit's equity jump as return. Verified -- dropping a point whose
    # $100 deposit doubled equity reports +100%. Any such skip must refuse the
    # whole report rather than publish a return that is mostly someone's bank
    # transfer.
    dropped_flow_reasons: list[str] = []

    def _note_skip(reason: str, raw_flow: object) -> None:
        skipped.append(reason)
        try:
            flow = _to_decimal_money(raw_flow or "0", name="net_external_flow")
        except ValueError:
            # Unparseable: cannot prove it was zero, so treat as material.
            dropped_flow_reasons.append(f"{reason} (flow unreadable)")
            return
        if flow != 0:
            dropped_flow_reasons.append(f"{reason} (flow {decimal_text(flow)})")

    for row in rows:
        benchmarks = row.get("benchmarks") or {}
        close = benchmarks.get(args.benchmark)
        if close is None:
            _note_skip(
                f"{row['session_date']}: no {args.benchmark} close recorded",
                row.get("net_external_flow"),
            )
            continue
        try:
            equity = float(_to_decimal_money(row["total_equity"], name="total_equity"))
            cash = float(_to_decimal_money(row["cash"], name="cash"))
            # Do not silently clamp cash > equity to invested=0: that would
            # report "all cash" for a corrupt snapshot and hide the defect.
            invested = equity - cash
            if invested < 0:
                _note_skip(
                    f"{row['session_date']}: cash exceeds equity "
                    f"(cash={cash}, equity={equity})",
                    row.get("net_external_flow"),
                )
                continue
            points.append(
                AttributionPoint(
                    at=datetime.fromisoformat(str(row["captured_at"])),
                    session_date=str(row.get("session_date") or "") or None,
                    total_equity=equity,
                    invested_value=invested,
                    benchmark_close=float(
                        _to_decimal_money(close, name=f"{args.benchmark} close")
                    ),
                    flow=float(
                        _to_decimal_money(
                            row.get("net_external_flow") or "0",
                            name="net_external_flow",
                        )
                    ),
                )
            )
        except (ValueError, AttributionError) as exc:
            _note_skip(f"{row['session_date']}: {exc}", row.get("net_external_flow"))

    if dropped_flow_reasons:
        raise SystemExit(
            "Cannot attribute: skipped snapshot(s) carried external cash "
            "flows, and omitting them would report the deposit or withdrawal "
            "as investment return. Fix or exclude the period explicitly. "
            + "; ".join(dropped_flow_reasons[:5])
        )
    if len(points) < 2:
        raise SystemExit(
            f"Cannot attribute: {len(points)} usable valuation point(s) from "
            f"{len(rows)} snapshot(s)."
            + (f" Skipped: {'; '.join(skipped[:5])}" if skipped else "")
        )

    try:
        report = evaluate_attribution(
            points,
            benchmark_ticker=args.benchmark,
            minimum_observations=args.minimum_observations,
        )
    except AttributionError as exc:
        raise SystemExit(f"Cannot attribute: {exc}") from exc

    report["skipped_snapshots"] = skipped
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return

    period = report["period"]
    returns = report["returns"]
    decomposition = report["decomposition"]
    sufficiency = report["sample_sufficiency"]
    print(
        f"Attribution vs {report['benchmark_ticker']} "
        f"({period['start'][:10]} to {period['end'][:10]}, "
        f"{period['span_days']:.1f} days)"
    )
    if not sufficiency["sufficient"]:
        print(
            f"  ! INSUFFICIENT SAMPLE: {sufficiency['independent_count']} of "
            f"{sufficiency['required_count']} independent "
            f"{sufficiency['independent_observation_unit']}s required "
            f"({sufficiency['valuation_point_count']} raw valuation points)"
        )
        for reason in sufficiency["insufficiency_reasons"]:
            print(f"    - {reason}")
    print(
        f"  portfolio {returns['portfolio_pct']}%  vs benchmark "
        f"{returns['benchmark_pct']}%  = active {returns['active_pct']}%"
    )
    # Do not hardcode "cash drag": when average weight > 100% the payload's
    # allocation_meaning correctly refuses that label (GR7CREV-005).
    allocation_label = (
        "cash drag"
        if Decimal(decomposition["average_invested_weight_pct"]) <= Decimal("100")
        else "invested-weight effect"
    )
    print(
        f"  {allocation_label} (allocation): {decomposition['allocation_pct']}%  "
        f"at {decomposition['average_invested_weight_pct']}% average invested "
        f"({decomposition['average_invested_weight_method']})"
    )
    print(f"  residual (selection):   {decomposition['selection_pct']}%")
    print("    " + decomposition["selection_meaning"])
    if skipped:
        print(f"  skipped {len(skipped)} snapshot(s); first: {skipped[0]}")
    print("  reporting only; no order was created, sized, or approved")


def command_propose(args, store: AssistantStore) -> None:
    policy = load_policy(_cli_policy_path(args))
    packet = _packet(include_events=not args.no_events, store=store)
    store.save_decision_packet(packet)
    tax_ledger, tax_coverage = tax_ledger_with_coverage(
        store, packet.portfolio
    )
    proposals = generate_risk_reduction_proposals(
        packet,
        policy,
        tax_lot_ledger=tax_ledger,
        tax_lot_coverage=tax_coverage,
    )
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
        if not proposal.expected_impact.get("projection_complete", True):
            unknown = ", ".join(
                proposal.expected_impact.get("pending_buy_unknown_tickers", [])
            )
            print(
                "  Preview warning: pending buy value is unavailable"
                + (f" for {unknown}" if unknown else "")
                + "; actual cash may be lower and exposure may be higher."
            )
        tax_advisory = proposal.expected_impact.get("tax_lot_advisory", {})
        if tax_advisory.get("available"):
            for method, detail in tax_advisory["methods"].items():
                if "error" not in detail:
                    print(
                        f"  Tax ({method.upper()}): "
                        f"{detail['realized_pnl']:+,.2f} realized "
                        f"(short {detail['short_term_pnl']:+,.2f}, "
                        f"long {detail['long_term_pnl']:+,.2f})"
                    )
        else:
            print(
                "  Tax: advisory unavailable -- "
                + str(tax_advisory.get("reason", "unknown reason"))
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
    policy = load_policy(_cli_policy_path(args))
    portfolio = build_portfolio_snapshot_from_alpaca()
    try:
        order = execute_approved_paper_proposal(
            args.proposal_id,
            args.confirm,
            portfolio,
            policy,
            store,
            now_et=_now_eastern(),
            kill_switch_active=env_kill_switch_active(),
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


def command_recover_stale_claim(args, store: AssistantStore) -> None:
    recovered = recover_stale_claim(
        args.proposal_id, store, stale_after_seconds=args.stale_after_seconds
    )
    print(
        f"Recovered {args.proposal_id} from a stale pre-broker claim -> {recovered['status']}. "
        "No broker order existed for it, and it no longer holds that ticker/side against "
        "new proposals. Run `propose` to generate a fresh one."
    )


def command_prune_packets(args, store: AssistantStore) -> None:
    # Explicit, opt-in cleanup (GPT review, 2026-07-31) -- decision
    # packets have no retention policy otherwise; this never runs
    # automatically, only when the user deliberately invokes it.
    deleted = store.prune_decision_packets_older_than(args.older_than_days)
    print(f"Deleted {deleted} decision packet(s) older than {args.older_than_days} day(s) from {store.path}.")


def command_sync_orders(args, store: AssistantStore) -> None:
    policy = load_policy(_cli_policy_path(args))
    result = reconcile_nonterminal_orders(
        store,
        cancel_stale=args.cancel_stale,
        max_order_age_minutes=policy.max_order_age_minutes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_monitor_orders(args, store: AssistantStore) -> None:
    # IgnoreNew only covers Task Scheduler instances. An orphaned console
    # process leaves the scheduler free to start a second worker; refuse
    # here before touching the broker or the shared operator database.
    try:
        acquire_process_singleton(args.database, "order-monitor")
    except ProcessSingletonError as exc:
        raise SystemExit(f"Order monitor already running: {exc}") from exc
    policy = load_policy(_cli_policy_path(args))
    print("Running startup reconciliation, then listening for Alpaca trade updates.")
    monitor_orders(
        store,
        cancel_stale=args.cancel_stale,
        max_order_age_minutes=policy.max_order_age_minutes,
        poll_interval_seconds=args.poll_seconds,
    )


def command_cancel_order(args, store: AssistantStore) -> None:
    if str(args.confirm).strip().lower() != "cancel":
        raise SystemExit(
            'Cancellation not confirmed. Pass --confirm "cancel".'
        )
    result = cancel_assistant_order(store, args.proposal_id)
    print(json.dumps(result, indent=2, sort_keys=True))


def command_cancel_all_orders(args, store: AssistantStore) -> None:
    if str(args.confirm).strip().lower() != "cancel all open orders":
        raise SystemExit(
            "Emergency cancellation not confirmed. Pass "
            '--confirm "cancel all open orders".'
        )
    result = cancel_all_open_orders(store, reason=args.reason)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"]:
        raise SystemExit(2)


def _committee_unavailable(code: str, message: str) -> None:
    """The ADR-required CLI `review unavailable` state: one unmistakable
    line, never a traceback, never a partial review, nonzero exit."""
    print(f"Review unavailable ({code}): {message}")
    raise SystemExit(2)


def _print_cited_points(label: str, points) -> None:
    if not points:
        return
    print(f"{label}:")
    for point in points:
        print(f"  - {point.text}")
        print(f"    sources: {', '.join(point.source_ids)}")


def command_committee_review(args, store: AssistantStore) -> None:
    """Experimental investment-committee review of ONE stored sell proposal.

    Advisory only: the output can never create, approve, size, submit,
    cancel, or replace an order, and execution revalidation remains
    mandatory after any human approval. Double-gated exactly like the
    Streamlit surface (ANTHROPIC_API_KEY AND ENABLE_EXPERIMENTAL_COMMITTEE=1
    -- completing the replay corpus did not remove that gate; removal is a
    separately owner-authorized decision). Every provider result, accepted or
    not, is audit-persisted; failures before a provider call remain explicitly
    unavailable. A review that cannot be audited is unavailable.
    """
    if not is_anthropic_committee_configured():
        _committee_unavailable(
            "not_configured",
            "ANTHROPIC_API_KEY is not set; no provider call was made.",
        )
    if not is_anthropic_committee_experiment_enabled():
        _committee_unavailable(
            "experiment_disabled",
            "Set ENABLE_EXPERIMENTAL_COMMITTEE=1 to opt into supervised "
            "experimental use; this release gate stays mandatory.",
        )

    proposal = store.get_proposal(args.proposal_id)
    if proposal is None:
        _committee_unavailable(
            "unknown_proposal", f"No stored proposal {args.proposal_id!r}."
        )

    try:
        packet = _packet(include_events=not args.no_events, store=store)
    except Exception:
        # A configured account makes _packet() perform fallible broker/data
        # reads. Preserve the CLI contract and do not leak provider, broker,
        # account, or local exception details into the unavailable surface.
        _committee_unavailable(
            "input_unavailable",
            "The decision packet could not be built; no provider call was made.",
        )
    try:
        committee_input = project_committee_input(packet, proposal)
    except ProjectionError as exc:
        _committee_unavailable("projection_refused", str(exc))

    result = run_committee_review_and_record(
        committee_input,
        AnthropicCommitteeProvider(),
        store,
        timeout_seconds=args.timeout_seconds,
    )
    if not result.accepted:
        detail = result.error_message or "no further detail."
        if result.issues:
            detail += " Issues: " + "; ".join(
                f"{issue.code} at {issue.path}" for issue in result.issues
            )
        _committee_unavailable(result.error_code or "unknown", detail)

    review = result.review
    print("Committee review ACCEPTED — advisory only, not a trade instruction.")
    print(
        f"provider={result.provider_id} model={result.model_id} "
        f"prompt_version={result.prompt_version}"
    )
    print(f"verdict: {review.verdict.value}")
    print(f"confidence: {review.confidence_label.value}")
    _print_cited_points("summary", [review.summary])
    _print_cited_points("supporting points", review.supporting_points)
    _print_cited_points("counterarguments", review.counterarguments)
    _print_cited_points("hidden risks", review.hidden_risks)
    _print_cited_points("data-quality warnings", review.data_quality_warnings)
    _print_cited_points("invalidation conditions", review.invalidation_conditions)
    _print_cited_points("revision requests", review.revision_requests)
    _print_cited_points("confidence basis", [review.confidence_basis])
    print(
        "Every order still requires exact human approval and deterministic "
        "revalidation; this review changes neither."
    )


def command_dismiss_proposals(args, store: AssistantStore) -> None:
    """UI-2d: preview-first dismissal of unused, never-broker-touched
    proposals. Archive, never delete: the row, payload, and idempotency
    key all remain. Defaults to preview-only; the mutation requires BOTH
    the preview hash printed by the preview run AND the exact confirmation
    string, so a copied-and-edited command cannot dismiss a different set
    of proposals than the one previewed."""
    preview = store.proposal_dismissal_eligibility(args.proposal_ids)
    print(
        json.dumps(
            {
                "rows": [
                    {
                        "proposal_id": row.proposal_id,
                        "ticker": row.ticker,
                        "side": row.side,
                        "shares": row.shares,
                        "status": row.status,
                        "created_at": row.created_at,
                        "expires_at": row.expires_at,
                        "dismissible": row.dismissible,
                        "refusal_reasons": list(row.refusal_reasons),
                    }
                    for row in preview.rows
                ],
                "dismissible_ids": list(preview.dismissible_ids),
                "preview_hash": preview.preview_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )

    mutation_requested = (
        args.confirm_preview_hash is not None or args.confirm_dismiss is not None
    )
    if not mutation_requested:
        print(
            "[preview only] To dismiss the dismissible rows above, re-run with "
            f"--reason <text> --confirm-preview-hash {preview.preview_hash} "
            "--confirm-dismiss unused-paper-proposals"
        )
        return

    if args.confirm_dismiss != "unused-paper-proposals":
        raise SystemExit(
            "Dismissal not confirmed. Pass --confirm-dismiss "
            "unused-paper-proposals (exactly)."
        )
    if args.confirm_preview_hash is None:
        raise SystemExit(
            "Dismissal requires --confirm-preview-hash from a preview run."
        )
    if not (args.reason or "").strip():
        raise SystemExit("Dismissal requires a non-empty --reason.")

    try:
        result = store.dismiss_proposals(
            args.proposal_ids,
            dismissed_by=args.operator,
            reason=args.reason,
            expected_preview_hash=args.confirm_preview_hash,
        )
    except ValueError as exc:
        raise SystemExit(f"Dismissal refused: {exc}")
    print(
        json.dumps(
            {
                "dismissed_ids": list(result.dismissed_ids),
                "already_dismissed_ids": list(result.already_dismissed_ids),
                "dismissed_at": result.dismissed_at,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(
        "Dismissed proposals remain in the local audit history and cannot "
        "be executed."
    )


def _write_artifact_atomically(destination: Path, payload: str) -> None:
    """Write a file the reader will treat as authoritative, or write nothing.

    FCS-013. `Path.write_text` is not atomic: a crash, a full disk, or a
    killed console (this host loses console-hosted processes to 0xC000013A --
    see docs/OPERATIONAL_FACTS.md §2) leaves a TRUNCATED file. For a tax
    export that matters more than usual, because a half-written CSV is still
    a syntactically valid CSV with fewer rows, and the coverage statement the
    report relies on to disclose its own limits can itself be cut off.

    `backtest/research_report.write_research_report` was hardened for the same
    reason on 2026-07-31; this is that discipline applied to the artifact that
    actually leaves the machine. The uuid in the temp name keeps two
    concurrent writers off each other's scratch file -- the deterministic
    `.tmp` sibling was the other half of that finding.

    Overwriting IS permitted here, unlike a research report: re-running
    `tax-report` for the same year after journaling more fills is a normal
    thing to do, and the artifact is derived, not evidence.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def command_sleeve_report(args, store: AssistantStore) -> None:
    """Three-sleeve engine status (M1, THREE_SLEEVE_ENGINE_PLAN).

    Read-only measurement of the portfolio against the owner's stated
    sleeve preference: it opens the store read-only for recorded fills and
    journal postings, fetches a live snapshot when Alpaca is configured,
    and never proposes, sizes, approves, or submits anything.
    """
    from assistant.corporate_actions import fills_with_confirmed_splits
    from assistant.sleeve_report import SleeveReportError, evaluate_sleeves
    from assistant.tax_lots import TaxLotError, build_ledger

    # Same degradation rule as idle-cash: a broker outage must fail the
    # REPORT with a sentence, not dump a traceback on the operator.
    try:
        if is_configured():
            portfolio = build_portfolio_snapshot_from_alpaca()
        else:
            portfolio = build_portfolio_snapshot(
                SAMPLE_POSITIONS, SAMPLE_CASH, source="manual", account_mode="manual"
            )
    except Exception as exc:
        raise SystemExit(
            f"Cannot report sleeves: portfolio snapshot unavailable "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    try:
        ledger = build_ledger(fills_with_confirmed_splits(store))
    except (TaxLotError, ValueError, KeyError) as exc:
        # Corrupt recorded fills must refuse the whole report: per-lot
        # threshold review over a partial replay would be read as fact.
        raise SystemExit(
            f"Cannot report sleeves: recorded fills cannot be replayed into "
            f"lots ({exc})"
        ) from exc
    try:
        report = evaluate_sleeves(portfolio, ledger, store.list_journal_postings())
    except SleeveReportError as exc:
        raise SystemExit(f"Cannot report sleeves: {exc}") from exc

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    dividend = report["dividend_sleeve"]
    growth = report["growth_sleeve"]
    reinvest = report["reinvest_sleeve"]
    income = report["dividend_income"]
    print(
        f"Sleeve report ({report['as_of']}, {report['account_mode']}, "
        f"source {report['portfolio_source']})"
    )
    print(f"  equity ${report['total_equity']}")
    print(
        f"  dividend sleeve ${dividend['total_market_value']} "
        f"({dividend['pct_of_equity']}% of equity, floor "
        f"{report['engine']['floor_pct']}%): {dividend['floor_status']}"
    )
    if dividend["floor_status"] == "below_floor":
        print("  ! dividend sleeve is BELOW the owner's stated floor")
    engine = report["engine"]
    gate = " long-term" if engine["gain_review_requires_long_term"] else ""
    trim = engine["gain_review_trim_fraction"]
    print(
        f"  growth sleeve: {len(growth['positions'])} position(s); "
        f"{growth['lots_at_gain_review']} lot(s) at{gate} gain review "
        f"(>= {engine['gain_review_threshold_pct']}%, trim fraction {trim}), "
        f"{growth['lots_awaiting_long_term']} above threshold awaiting "
        f"long-term, "
        f"{growth['lots_at_decline_review']} at decline review "
        f"(<= {engine['decline_review_threshold_pct']}%)"
    )
    for position in growth["positions"]:
        if position["lot_coverage"] != "full":
            print(
                f"  ! {position['ticker']} lot coverage is "
                f"{position['lot_coverage']}: {position['coverage_reason']}"
            )
        for lot in position["lots"]:
            if lot["crossed_gain_review_threshold"]:
                print(
                    f"    {position['ticker']} lot {lot['lot_id']}: "
                    f"{lot['unrealized_pnl_pct']:+.2f}% "
                    f"(${lot['unrealized_pnl']:+,.2f}), "
                    f"{lot['term_if_sold_now']}-term if disposed now "
                    f"(first long-term date {lot['first_long_term_date']}) -- "
                    f"gain review (trim fraction {trim})"
                )
            elif lot["gain_threshold_met_awaiting_long_term"]:
                print(
                    f"    {position['ticker']} lot {lot['lot_id']}: "
                    f"{lot['unrealized_pnl_pct']:+.2f}% "
                    f"(${lot['unrealized_pnl']:+,.2f}) -- above threshold, "
                    f"long-term in {lot['days_to_long_term']} day(s); the "
                    f"first long-term date is {lot['first_long_term_date']}; "
                    f"the gate holds until then"
                )
            elif lot["crossed_decline_review_threshold"]:
                print(
                    f"    {position['ticker']} lot {lot['lot_id']}: "
                    f"{lot['unrealized_pnl_pct']:+.2f}% "
                    f"(${lot['unrealized_pnl']:+,.2f}) -- decline review"
                )
    print(
        f"  reinvest sleeve ${reinvest['total_market_value']} "
        f"({reinvest['pct_of_equity']}% of equity)"
    )
    print(
        f"  confirmed dividend income ${income['confirmed_total']} across "
        f"{income['posting_count']} posting(s) -- {income['note']}"
    )
    for overlap in report["single_issuer_overlap"]:
        print(
            f"  ! single-issuer overlap on {overlap['issuer']}: "
            + "; ".join(overlap["routes"])
        )


def command_tax_report(args, store: AssistantStore) -> None:
    """GR-7a: realized gains for one tax year, from confirmed records.

    Read-only. Exits 2 when share coverage is incomplete or unverified so a
    scripted caller notices, while STILL producing the artifact -- an
    accountant needs to see what exists plus the stated limitation, not an
    empty refusal. The limitation is written into the file itself, not just
    printed here.

    Sample/manual portfolios never verify coverage. Only a live Alpaca
    snapshot may claim a broker match.
    """
    import sys

    from assistant.context_builder import build_portfolio_snapshot_from_alpaca

    portfolio = None
    coverage_unavailable_reason = None
    if not args.no_coverage_check:
        if not is_configured():
            coverage_unavailable_reason = (
                "no live broker configured; share coverage was not verified "
                "against a broker snapshot"
            )
        else:
            try:
                portfolio = build_portfolio_snapshot_from_alpaca()
            except Exception as exc:
                coverage_unavailable_reason = (
                    "Coverage check unavailable "
                    f"({type(exc).__name__}); the report is marked unverified."
                )
                print(coverage_unavailable_reason, file=sys.stderr)
    try:
        report = build_annual_tax_report(
            store,
            args.year,
            portfolio=portfolio,
            coverage_unavailable_reason=coverage_unavailable_reason,
        )
    except TaxReportError as exc:
        raise SystemExit(f"Tax report unavailable: {exc}")

    rendered = (
        render_tax_report_csv(report)
        if args.format == "csv"
        else render_tax_report_json(report)
    )
    summary = (
        f"Tax year {report.tax_year}: {report.total.sale_count} realized "
        f"sale row(s); short-term P&L {report.short_term.realized_pnl}, "
        f"long-term P&L {report.long_term.realized_pnl}, total "
        f"{report.total.realized_pnl}. "
        f"{report.wash_sale_flagged_count} wash-sale flag(s) (advisory only)."
    )
    if args.output:
        _write_artifact_atomically(args.output, rendered)
        print(f"Wrote {args.format.upper()} tax report: {args.output}")
        print(summary)
        if not report.complete:
            print(f"COVERAGE WARNING: {report.coverage.get('reason')}")
            raise SystemExit(2)
        return

    # Keep stdout as the pure artifact for scripted/accountant consumers.
    print(rendered)
    print(summary, file=sys.stderr)
    if not report.complete:
        print(
            f"COVERAGE WARNING: {report.coverage.get('reason')}",
            file=sys.stderr,
        )
        raise SystemExit(2)


def command_readiness(args, store: AssistantStore) -> None:
    policy = load_policy(_cli_policy_path(args))
    report = transaction_readiness(store, policy, check_broker=not args.offline)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ready"]:
        raise SystemExit(2)


def command_platform_readiness(args, store: AssistantStore) -> None:
    """GR-0: five independently scored dimensions, deliberately not averaged.

    Read-only. Exits 2 when any dimension is blocked so a scheduled caller
    can react, but prints every dimension either way -- a blocked dimension
    must never suppress the others.
    """
    policy = load_policy(_cli_policy_path(args))
    mandate = load_mandate(args.mandate)
    report = build_platform_readiness(
        store, policy, mandate, check_broker=not args.offline
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if any(d.status == BLOCKED for d in report.dimensions):
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


def command_verify_db_schema(args) -> None:
    """AP-1: prove the database carries the schema current code declares.

    Read-only by default -- an operator can check a database without
    migrating it as a side effect, which is why this handler runs WITHOUT
    the store construction main() performs for every other command (that
    construction IS the migration). ``--apply`` opts into opening the
    database with current code first (idempotent CREATE IF NOT EXISTS plus
    column migrations), then verifies the result.
    """
    database = Path(args.database) if args.database is not None else configured_db_path()
    if args.apply:
        AssistantStore(database)
    result = verify_database_schema(database)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.matches:
        raise SystemExit(2)


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


def command_ledger_bind_account(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required for ledger account binding."
        )
    snapshot = build_portfolio_snapshot_from_alpaca()
    result = bind_legacy_alpaca_account(
        store,
        snapshot,
        confirmation=args.confirm,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_ledger_dividend(args, store: AssistantStore) -> None:
    inserted = record_dividend(
        store,
        external_id=args.external_id,
        ticker=args.ticker,
        gross_amount=args.gross_amount,
        occurred_at=args.occurred_at,
        ex_date=args.ex_date,
        pay_date=args.pay_date,
        amount_per_share=args.amount_per_share,
        shares_entitled=args.shares_entitled,
        tax_classification=args.tax_classification,
    )
    print(
        json.dumps(
            {
                "inserted": inserted,
                "external_id": args.external_id,
                "ticker": args.ticker.upper(),
                "action": "dividend",
            },
            indent=2,
            sort_keys=True,
        )
    )


def command_ledger_split(args, store: AssistantStore) -> None:
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required to reconcile fills before "
            "recording a split."
        )
    policy = load_policy(_cli_policy_path(args))
    order_reconciliation = reconcile_nonterminal_orders(
        store,
        max_order_age_minutes=policy.max_order_age_minutes,
    )
    if order_reconciliation.get("errors") or order_reconciliation.get(
        "skipped_too_recent", 0
    ):
        raise SystemExit(
            "Broker order reconciliation was incomplete; refusing to record "
            "the split until every possible pre-split fill is resolved."
        )
    fill_sync = sync_app_fills(store)
    inserted = record_split(
        store,
        external_id=args.external_id,
        ticker=args.ticker,
        ratio=args.ratio,
        occurred_at=args.occurred_at,
    )
    print(
        json.dumps(
            {
                "inserted": inserted,
                "external_id": args.external_id,
                "ticker": args.ticker.upper(),
                "action": "split",
                "order_reconciliation": order_reconciliation,
                "fill_sync": fill_sync,
            },
            indent=2,
            sort_keys=True,
        )
    )


def command_ledger_transfer(args, store: AssistantStore) -> None:
    inserted = record_cash_transfer(
        store,
        external_id=args.external_id,
        amount=args.amount,
        occurred_at=args.occurred_at,
        description=args.description,
    )
    print(
        json.dumps(
            {
                "inserted": inserted,
                "external_id": args.external_id,
                "amount": args.amount,
                "action": "cash_transfer",
            },
            indent=2,
            sort_keys=True,
        )
    )


def command_ledger_fee(args, store: AssistantStore) -> None:
    inserted = record_fee(
        store,
        external_id=args.external_id,
        amount=args.amount,
        occurred_at=args.occurred_at,
        description=args.description,
    )
    print(
        json.dumps(
            {
                "inserted": inserted,
                "external_id": args.external_id,
                "amount": args.amount,
                "action": "fee",
            },
            indent=2,
            sort_keys=True,
        )
    )


def command_operations_check(args, store: AssistantStore) -> None:
    policy = load_policy(_cli_policy_path(args))
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


def _alert_channel(args):
    """Resolve the delivery channel. Windows toast is the owner-chosen
    mandatory immediate channel (2026-08-03); --dry-run swaps in a
    recording channel that never notifies a human, for verification."""
    from assistant.alert_delivery import RecordingChannel, WindowsToastChannel

    if getattr(args, "dry_run", False):
        return RecordingChannel(name="dry_run")
    return WindowsToastChannel()


def command_deliver_alerts(args, store: AssistantStore) -> None:
    """GR-5: deliver open critical alerts and record every attempt."""
    from assistant.alert_delivery import deliver_pending_alerts

    report = deliver_pending_alerts(store, _alert_channel(args))
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["healthy"]:
        raise SystemExit(2)


def command_alert_self_test(args, store: AssistantStore) -> None:
    """GR-5: prove the critical channel still works, end to end.

    Records the `alert_delivery` promotion drill -- epoch-bound when an
    active paper evidence epoch exists (and only when the runtime commit
    matches that epoch's lineage exactly), otherwise verification-only.
    A FAILED self-test is recorded too; failure is evidence.
    """
    from assistant.alert_delivery import run_channel_self_test
    from assistant.paper_evidence import record_operational_drill

    if args.record_drill and not (args.operator or "").strip():
        raise SystemExit("--operator is required with --record-drill.")
    result = run_channel_self_test(store, _alert_channel(args))
    if args.record_drill:
        evidence = {
            "operator": args.operator.strip(),
            "artifact": f"alert_deliveries#{result['delivery']['delivery_id']}",
            "channel": result["channel"],
            "verified_from_storage": result["verified_from_storage"],
            "detail": result["delivery"]["detail"],
        }
        epoch = store.get_active_paper_evidence_epoch()
        if epoch is None:
            evidence["verification_only"] = True
            result["drill"] = store.record_operational_drill(
                drill_type="alert_delivery",
                performed_at=result["performed_at"],
                passed=result["passed"],
                evidence_epoch=None,
                code_commit=_runtime_commit_or_unknown(),
                evidence=evidence,
            )
        else:
            from assistant.paper_evidence import (
                PaperEvidenceError,
                verify_drill_lineage_commit,
            )

            try:
                verify_drill_lineage_commit(epoch, _runtime_commit_or_unknown())
            except PaperEvidenceError as exc:
                raise SystemExit(str(exc)) from exc
            result["drill"] = record_operational_drill(
                store,
                drill_type="alert_delivery",
                passed=result["passed"],
                evidence=evidence,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(2)


def _runtime_commit_or_unknown() -> str:
    try:
        return current_commit()
    except RuntimeIdentityError:
        return "unknown"


def command_ack_alert(args, store: AssistantStore) -> None:
    if not store.acknowledge_operational_alert(args.alert_id):
        raise SystemExit(f"Open alert not found: {args.alert_id}")
    print(f"Acknowledged alert {args.alert_id}.")


def command_recovery_drill(args, store: AssistantStore) -> None:
    if store.get_active_paper_evidence_epoch() is not None:
        _active_runtime_lineage(store, args)
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


def command_paper_epoch_start(args, store: AssistantStore) -> None:
    if not config.PAPER_TRADING:
        raise SystemExit(
            "Refusing to start paper evidence while config.PAPER_TRADING "
            "is false."
        )
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required to start paper evidence."
        )
    account = get_account()
    if not account["paper"]:
        raise SystemExit(
            "Refusing to start paper evidence against a live account."
        )
    mandate = load_mandate(args.mandate)
    policy = load_policy(_cli_policy_path(args))
    lineage = build_paper_lineage(
        code_commit=_current_commit(require_clean=True),
        mandate_fingerprint=compute_mandate_fingerprint(mandate),
        policy_fingerprint=compute_policy_fingerprint(policy),
        strategy_id=args.strategy_id,
        strategy_version=args.strategy_version,
        model_id=args.model_id,
        broker_account_id=account["account_id"],
    )
    result = start_paper_evidence_epoch(
        store, args.evidence_epoch, lineage
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_paper_epoch_close(args, store: AssistantStore) -> None:
    active = store.get_active_paper_evidence_epoch()
    if active is None:
        raise SystemExit("No active paper evidence epoch.")
    if (
        args.evidence_epoch is not None
        and args.evidence_epoch != active["evidence_epoch"]
    ):
        raise SystemExit(
            f"Active epoch is {active['evidence_epoch']!r}, not "
            f"{args.evidence_epoch!r}."
        )
    result = store.close_paper_evidence_epoch(
        active["evidence_epoch"],
        ended_at=datetime.now(timezone.utc).isoformat(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_paper_observation(args, store: AssistantStore) -> None:
    if not config.PAPER_TRADING:
        raise SystemExit(
            "Refusing paper evidence capture while config.PAPER_TRADING "
            "is false."
        )
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required for paper evidence."
        )
    cycle_started_at = datetime.now(timezone.utc)
    session = paper_session_schedule(cycle_started_at)
    if session is None:
        print(
            json.dumps(
                {
                    "captured": False,
                    "reason": "not an NYSE trading session",
                    "at": cycle_started_at.isoformat(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    session_date = session[0]
    try:
        lineage = _active_runtime_lineage(store, args)
        policy = load_policy(_cli_policy_path(args))
        order_report = reconcile_nonterminal_orders(
            store,
            cancel_stale=args.cancel_stale,
            max_order_age_minutes=policy.max_order_age_minutes,
        )
        fill_report = sync_app_fills(store)
        snapshot = build_portfolio_snapshot_from_alpaca()
        reconciliation = reconcile_snapshot(store, snapshot)
        if not reconciliation["matched"]:
            raise RuntimeError(
                "Ledger reconciliation failed; refusing to capture paper NAV."
            )
        captured_at = datetime.now(timezone.utc)
        capture_session = paper_session_schedule(captured_at)
        if capture_session is None or capture_session[0] != session_date:
            raise RuntimeError(
                "The NYSE session changed during paper observation capture."
            )
        benchmark_close = _benchmark_close_for_session(
            args.benchmark, session_date
        )
        observation = capture_paper_account_observation(
            store,
            snapshot,
            benchmark_ticker=args.benchmark,
            benchmark_close=benchmark_close,
            captured_at=captured_at,
            expected_lineage=lineage,
        )
    except (Exception, SystemExit) as exc:
        alert = store.upsert_operational_alert(
            fingerprint="scheduled-paper-observation-failure",
            severity="critical",
            category="paper_evidence",
            message=f"paper observation failed: {exc}",
            details={
                "error_type": type(exc).__name__,
                "session_date": session_date,
            },
        )
        if args.alerts_jsonl:
            append_alerts_jsonl([alert], args.alerts_jsonl)
        raise
    print(
        json.dumps(
            {
                "order_reconciliation": order_report,
                "fill_sync": fill_report,
                "ledger_reconciliation": reconciliation,
                "paper_observation": observation,
            },
            indent=2,
            sort_keys=True,
        )
    )


def command_paper_evidence_status(args, store: AssistantStore) -> None:
    summary = paper_evidence_summary(store, args.evidence_epoch)
    print(json.dumps(summary, indent=2, sort_keys=True))


def command_record_drill(args, store: AssistantStore) -> None:
    _active_runtime_lineage(store, args)
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise SystemExit("Drill evidence JSON must contain an object.")
    performed_at = (
        datetime.fromisoformat(args.performed_at.replace("Z", "+00:00"))
        if args.performed_at
        else None
    )
    result = record_operational_drill(
        store,
        drill_type=args.drill_type,
        passed=args.result == "pass",
        evidence=evidence,
        performed_at=performed_at,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def command_operations_cycle(args, store: AssistantStore) -> None:
    if not config.PAPER_TRADING:
        raise SystemExit(
            "Refusing an operational paper cycle while "
            "config.PAPER_TRADING is false."
        )
    if not is_configured():
        raise SystemExit(
            "Alpaca paper credentials are required for an operational cycle."
        )
    policy = load_policy(_cli_policy_path(args))
    try:
        order_report = reconcile_nonterminal_orders(
            store,
            cancel_stale=args.cancel_stale,
            max_order_age_minutes=policy.max_order_age_minutes,
        )
        fill_report = sync_app_fills(store)
        snapshot = build_portfolio_snapshot_from_alpaca()
        reconciliation = reconcile_snapshot(store, snapshot)
        backup = ensure_recent_database_backup(
            store,
            args.backup_directory,
            max_age_hours=args.backup_max_age_hours,
        )
        health = run_operational_check(
            store, policy, check_broker=True
        )
        if args.alerts_jsonl and health["alerts"]:
            append_alerts_jsonl(health["alerts"], args.alerts_jsonl)
    except (Exception, SystemExit) as exc:
        alert = store.upsert_operational_alert(
            fingerprint="scheduled-operations-cycle-failure",
            severity="critical",
            category="operations_cycle",
            message=f"scheduled operations cycle failed: {exc}",
            details={"error_type": type(exc).__name__},
        )
        if args.alerts_jsonl:
            append_alerts_jsonl([alert], args.alerts_jsonl)
        raise
    result = {
        "order_reconciliation": order_report,
        "fill_sync": fill_report,
        "ledger_reconciliation": reconciliation,
        "backup": backup,
        "health": health,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not reconciliation["matched"] or not health["healthy"]:
        raise SystemExit(2)


def command_promotion_status(args, store: AssistantStore) -> None:
    mandate = load_mandate(args.mandate)
    report = json.loads(args.research_report.read_text(encoding="utf-8"))
    if not verify_research_report(report):
        raise SystemExit(
            "Research report hash is missing or invalid; refusing promotion review."
        )
    paper_summary = paper_evidence_summary(store, args.evidence_epoch)
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
        metric_report=paper_summary.get("metrics") or {},
        paper_sessions=paper_summary["paper_sessions"],
        paper_orders=paper_summary["paper_orders"]["count"],
        unreconciled_items=unreconciled,
        critical_alerts=critical_alerts,
        research_reproduced=args.research_reproduced,
        point_in_time_data=bool(
            (report.get("research_protocol") or {}).get(
                "point_in_time_data"
            )
        ),
        backup_restore_drill_passed=bool(
            paper_summary["required_drills"]["backup_restore"]["passed"]
        ),
        operational_health_passed=bool(
            operations_heartbeat.get("healthy") and heartbeat_fresh
        ),
        paper_evidence_integrity_passed=bool(
            paper_summary["coverage_complete"]
            and paper_summary["lineage_consistent"]
            and paper_summary["metrics"] is not None
        ),
        operational_drills_passed=bool(
            paper_summary["all_required_drills_passed"]
        ),
    )
    result["paper_evidence"] = paper_summary
    result["research_report_sha256"] = report.get("report_sha256")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ready_for_live_canary_review"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal trading assistant")
    parser.add_argument(
        "--database",
        type=Path,
        help=(
            "SQLite database path. Defaults to TRADING_ASSISTANT_DB or "
            "data/trading_assistant.db."
        ),
    )
    parser.add_argument(
        "--policy",
        default=None,
        help=(
            "Policy file governing proposals. When omitted, resolves via "
            "TRADING_ASSISTANT_POLICY, then assistant/my_policy.json when "
            "present, otherwise assistant/default_policy.json. The path is "
            "resolved after argument parsing so a bad environment default "
            "cannot block --help or an explicit --policy."
        ),
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
    # FCS-012: _positive_int, not bare int. SQLite treats LIMIT -1 as
    # unbounded, so `list --limit -1` silently returned every row while the
    # sibling `list-alerts --limit` was already validated.
    list_parser.add_argument("--limit", type=_positive_int, default=20)
    list_parser.set_defaults(handler=command_list, read_only_store=True)

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

    recover_claim = commands.add_parser(
        "recover-stale-claim",
        help=(
            "Release a proposal stranded in 'validating'/'approved' after a process was killed "
            "before submission. Those statuses are written BEFORE any broker call, so no order can "
            "exist -- but they hold the ticker/side against new proposals (duplicate-order "
            "protection), and nothing else can clear them. Only affects a proposal untouched for "
            "--stale-after-seconds (default 900). Post-submission statuses are NOT recoverable "
            "this way -- use 'reconcile' or 'recover-stale'."
        ),
    )
    recover_claim.add_argument("proposal_id")
    recover_claim.add_argument("--stale-after-seconds", type=_positive_int, default=900)
    recover_claim.set_defaults(handler=command_recover_stale_claim)

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

    cancel_order = commands.add_parser(
        "cancel-order",
        help=(
            "Cancel the current authoritative broker order for one assistant "
            "proposal, following any replacement chain."
        ),
    )
    cancel_order.add_argument("proposal_id")
    cancel_order.add_argument(
        "--confirm",
        required=True,
        help='Must be exactly "cancel" (case-insensitive).',
    )
    cancel_order.set_defaults(handler=command_cancel_order)

    cancel_all = commands.add_parser(
        "cancel-all-orders",
        help=(
            "Engage the persistent kill switch, then request cancellation "
            "for every open broker order, including unmanaged orders."
        ),
    )
    cancel_all.add_argument(
        "--confirm",
        required=True,
        help='Must be exactly "cancel all open orders" (case-insensitive).',
    )
    cancel_all.add_argument(
        "--reason",
        required=True,
        help="Operator incident reason stored with the durable kill switch.",
    )
    cancel_all.set_defaults(handler=command_cancel_all_orders)

    readiness = commands.add_parser(
        "readiness",
        help="Check policy, SQLite integrity, reconciliation freshness, budgets, and broker state.",
    )
    platform = commands.add_parser(
        "platform-readiness",
        help=(
            "Score execution, data, operational, evidence, and strategy "
            "readiness independently. Never averaged into one number."
        ),
    )
    platform.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Skip live broker calls. Missing broker checks remain explicit "
            "execution blockers; offline never means verified."
        ),
    )
    platform.set_defaults(handler=command_platform_readiness, read_only_store=True)

    readiness.add_argument(
        "--offline",
        action="store_true",
        help="Skip the live broker-account check; all local checks still run.",
    )
    readiness.set_defaults(handler=command_readiness, read_only_store=True)

    kill_switch = commands.add_parser(
        "kill-switch",
        help="Persistently enable, disable, or inspect the execution kill switch.",
    )
    kill_switch.add_argument("state", choices=("on", "off", "status"))
    kill_switch.add_argument("--reason")
    kill_switch.set_defaults(handler=command_kill_switch)

    idle_cash = commands.add_parser(
        "idle-cash",
        help=(
            "GR-7b: report cash against the policy's reserve floor and "
            "exposure ceiling, and against the mandate's volatility target. "
            "Read-only."
        ),
    )
    idle_cash.add_argument(
        "--measured-volatility-pct",
        type=float,
        default=None,
        help=(
            "Observed annualized portfolio volatility, when one has actually "
            "been measured. Omitted means the report says so explicitly "
            "rather than assuming zero."
        ),
    )
    idle_cash.add_argument("--json", action="store_true")
    idle_cash.set_defaults(handler=command_idle_cash, needs_store=False)

    sleeve = commands.add_parser(
        "sleeve-report",
        help=(
            "Three-sleeve engine status: dividend-sleeve floor, per-lot "
            "gain/decline review thresholds with tax term, reinvest sleeve, "
            "and confirmed dividend income. Owner preference, not research. "
            "Read-only."
        ),
    )
    sleeve.add_argument("--json", action="store_true")
    sleeve.set_defaults(handler=command_sleeve_report, read_only_store=True)

    attribution = commands.add_parser(
        "attribution",
        help=(
            "GR-7c: decompose return vs the benchmark into cash drag and a "
            "labelled residual, from recorded equity snapshots. Read-only."
        ),
    )
    attribution.add_argument("--benchmark", default="SPY")
    attribution.add_argument(
        "--account-key",
        default=None,
        help="Which recorded account to attribute; required when several exist.",
    )
    attribution.add_argument(
        "--limit",
        type=_positive_int,
        default=500,
        help="Maximum recent equity snapshots to load (positive integer).",
    )
    attribution.add_argument(
        "--minimum-observations",
        type=_positive_int,
        default=DEFAULT_MINIMUM_OBSERVATIONS,
        help=(
            "Independent market sessions below which the report declares "
            "itself insufficient (not raw valuation-point count)."
        ),
    )
    attribution.add_argument("--json", action="store_true")
    attribution.set_defaults(handler=command_attribution, read_only_store=True)

    backup = commands.add_parser("backup-db", help="Create a consistent SQLite backup.")
    backup.add_argument("destination", nargs="?", type=Path)
    backup.set_defaults(handler=command_backup_db)

    verify_schema = commands.add_parser(
        "verify-db-schema",
        help=(
            "Verify the database schema matches current code. Read-only by "
            "default; --apply opens the database with current code first, "
            "which idempotently creates any missing tables, columns, "
            "indexes, and triggers."
        ),
    )
    verify_schema.add_argument(
        "--apply",
        action="store_true",
        help="Apply the current schema (open with current code) before verifying.",
    )
    verify_schema.set_defaults(handler=command_verify_db_schema, needs_store=False)

    committee = commands.add_parser(
        "committee-review",
        help=(
            "Experimental, advisory-only committee review of one stored sell "
            "proposal (real API call, real cost). Requires ANTHROPIC_API_KEY "
            "AND ENABLE_EXPERIMENTAL_COMMITTEE=1; prints an explicit 'Review "
            "unavailable (<code>)' line and exits 2 on any failure."
        ),
    )
    committee.add_argument("proposal_id")
    committee.add_argument("--no-events", action="store_true")
    committee.add_argument("--timeout-seconds", type=float, default=30.0)
    committee.set_defaults(handler=command_committee_review)

    tax_report = commands.add_parser(
        "tax-report",
        help=(
            "GR-7a: realized gains/losses for one tax year from recorded "
            "fills and journal-confirmed corporate actions. Read-only; "
            "exits 2 when share coverage is incomplete or unverified "
            "(the artifact is still produced and states the limitation). "
            "Not tax advice; wash-sale entries are advisory flags only."
        ),
    )
    # FCS-012: a tax year is a non-negative integer; assistant/tax_reporting
    # rejects anything outside 1900..2200 anyway, so catch it at the CLI
    # boundary with the validator that was written for exactly this and never
    # wired to anything.
    tax_report.add_argument("--year", type=_non_negative_int, required=True)
    tax_report.add_argument(
        "--format", choices=("csv", "json"), default="csv"
    )
    tax_report.add_argument("--output", type=Path, default=None)
    tax_report.add_argument(
        "--no-coverage-check",
        action="store_true",
        help=(
            "Skip the broker snapshot used to verify share coverage "
            "(offline use). The report is then marked COVERAGE UNVERIFIED."
        ),
    )
    tax_report.set_defaults(handler=command_tax_report, read_only_store=True)

    dismiss = commands.add_parser(
        "dismiss-proposals",
        help=(
            "UI-2d: preview (default) or dismiss unused, never-broker-touched "
            "proposals. Archive, never delete -- the row and idempotency key "
            "remain. Mutation requires --reason, --confirm-preview-hash from "
            "the preview, and --confirm-dismiss unused-paper-proposals."
        ),
    )
    dismiss.add_argument("proposal_ids", nargs="+")
    dismiss.add_argument("--reason", default=None)
    dismiss.add_argument("--operator", default="local_operator")
    dismiss.add_argument("--confirm-preview-hash", default=None)
    dismiss.add_argument("--confirm-dismiss", default=None)
    dismiss.set_defaults(handler=command_dismiss_proposals)

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

    ledger_bind = commands.add_parser(
        "ledger-bind-account",
        help=(
            "One-time migration for an Alpaca journal created before account "
            "IDs were recorded; requires an exact live reconciliation."
        ),
    )
    ledger_bind.add_argument(
        "--confirm",
        required=True,
        help='Must be exactly "bind account" (case-insensitive).',
    )
    ledger_bind.set_defaults(handler=command_ledger_bind_account)

    ledger_dividend = commands.add_parser(
        "ledger-dividend",
        help=(
            "Append a broker-confirmed cash dividend to the journal. "
            "Reference-feed discoveries are not accepted as confirmation."
        ),
    )
    ledger_dividend.add_argument("--external-id", required=True)
    ledger_dividend.add_argument("--ticker", required=True)
    ledger_dividend.add_argument("--gross-amount", required=True)
    ledger_dividend.add_argument(
        "--occurred-at",
        required=True,
        help="Timezone-aware ISO-8601 time when cash was received.",
    )
    ledger_dividend.add_argument(
        "--ex-date",
        required=True,
        help="ISO date or timezone-aware timestamp used for entitlement.",
    )
    ledger_dividend.add_argument("--pay-date")
    ledger_dividend.add_argument("--amount-per-share", required=True)
    ledger_dividend.add_argument("--shares-entitled")
    ledger_dividend.add_argument(
        "--tax-classification",
        choices=("qualified", "ordinary", "unknown"),
        default="unknown",
    )
    ledger_dividend.set_defaults(handler=command_ledger_dividend)

    ledger_split = commands.add_parser(
        "ledger-split",
        help=(
            "Append a broker-confirmed split ratio to journal share quantities "
            "without changing total cost basis."
        ),
    )
    ledger_split.add_argument("--external-id", required=True)
    ledger_split.add_argument("--ticker", required=True)
    ledger_split.add_argument(
        "--ratio",
        required=True,
        help="New shares per old share, e.g. 4 or 0.1.",
    )
    ledger_split.add_argument(
        "--occurred-at",
        required=True,
        help="Timezone-aware ISO-8601 effective timestamp.",
    )
    ledger_split.set_defaults(handler=command_ledger_split)

    ledger_transfer = commands.add_parser(
        "ledger-transfer",
        help=(
            "Append a broker-confirmed cash contribution (positive) or "
            "withdrawal (negative) to the journal."
        ),
    )
    ledger_transfer.add_argument("--external-id", required=True)
    ledger_transfer.add_argument(
        "--amount",
        required=True,
        help="Signed cash amount; positive deposits, negative withdraws.",
    )
    ledger_transfer.add_argument(
        "--occurred-at",
        required=True,
        help="Timezone-aware ISO-8601 broker posting timestamp.",
    )
    ledger_transfer.add_argument("--description", required=True)
    ledger_transfer.set_defaults(handler=command_ledger_transfer)

    ledger_fee = commands.add_parser(
        "ledger-fee",
        help="Append a broker-confirmed positive fee amount to the journal.",
    )
    ledger_fee.add_argument("--external-id", required=True)
    ledger_fee.add_argument("--amount", required=True)
    ledger_fee.add_argument(
        "--occurred-at",
        required=True,
        help="Timezone-aware ISO-8601 broker posting timestamp.",
    )
    ledger_fee.add_argument("--description", required=True)
    ledger_fee.set_defaults(handler=command_ledger_fee)

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
    list_alerts.set_defaults(handler=command_list_alerts, read_only_store=True)

    deliver_alerts = commands.add_parser(
        "deliver-alerts",
        help=(
            "Deliver open CRITICAL alerts to the Windows desktop channel and "
            "record every attempt. Warnings batch into the daily briefing "
            "instead. Exits 2 when any delivery failed."
        ),
    )
    deliver_alerts.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a recording channel that never notifies a human.",
    )
    deliver_alerts.set_defaults(handler=command_deliver_alerts)

    alert_self_test = commands.add_parser(
        "alert-self-test",
        help=(
            "Emit a synthetic critical alert, deliver it, and verify the "
            "recorded receipt. Run weekly: a channel that silently broke is "
            "worse than no channel. Exits 2 on failure."
        ),
    )
    alert_self_test.add_argument("--dry-run", action="store_true")
    alert_self_test.add_argument(
        "--record-drill",
        action="store_true",
        help="Record the alert_delivery promotion drill for this self-test.",
    )
    alert_self_test.add_argument(
        "--operator", default="", help="Operator name (required with --record-drill)."
    )
    alert_self_test.set_defaults(handler=command_alert_self_test)

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

    epoch_start = commands.add_parser(
        "paper-epoch-start",
        help="Start an immutable-lineage paper evidence collection epoch.",
    )
    epoch_start.add_argument("evidence_epoch")
    epoch_start.add_argument("--strategy-id", required=True)
    epoch_start.add_argument("--strategy-version", required=True)
    epoch_start.add_argument(
        "--model-id",
        required=True,
        help=(
            "Exact decision-model identifier, or an explicit value such as "
            "'deterministic-no-model'."
        ),
    )
    epoch_start.set_defaults(handler=command_paper_epoch_start)

    epoch_close = commands.add_parser(
        "paper-epoch-close",
        help="Close the active evidence epoch after a material runtime change.",
    )
    epoch_close.add_argument("evidence_epoch", nargs="?")
    epoch_close.set_defaults(handler=command_paper_epoch_close)

    paper_observation = commands.add_parser(
        "paper-observation",
        help=(
            "Reconcile orders and ledger, then capture one immutable "
            "post-close paper NAV observation."
        ),
    )
    paper_observation.add_argument("--benchmark", default="SPY")
    paper_observation.add_argument("--cancel-stale", action="store_true")
    paper_observation.add_argument("--alerts-jsonl", type=Path)
    paper_observation.set_defaults(handler=command_paper_observation)

    paper_status = commands.add_parser(
        "paper-evidence-status",
        help="Show derived paper sessions, orders, metrics, lineage and drills.",
    )
    paper_status.add_argument("evidence_epoch", nargs="?")
    paper_status.set_defaults(handler=command_paper_evidence_status)

    drill_record = commands.add_parser(
        "record-drill",
        help="Record timestamped operational drill evidence for the active epoch.",
    )
    drill_record.add_argument(
        "drill_type", choices=REQUIRED_PROMOTION_DRILLS
    )
    drill_record.add_argument("result", choices=("pass", "fail"))
    drill_record.add_argument(
        "evidence",
        type=Path,
        help="JSON object containing operator, artifact and drill details.",
    )
    drill_record.add_argument("--performed-at")
    drill_record.set_defaults(handler=command_record_drill)

    operations_cycle = commands.add_parser(
        "operations-cycle",
        help=(
            "Run one scheduler-friendly order, ledger, backup and health cycle."
        ),
    )
    operations_cycle.add_argument("--cancel-stale", action="store_true")
    operations_cycle.add_argument(
        "--backup-directory",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "backups",
    )
    operations_cycle.add_argument(
        "--backup-max-age-hours", type=_positive_float, default=20.0
    )
    operations_cycle.add_argument("--alerts-jsonl", type=Path)
    operations_cycle.set_defaults(handler=command_operations_cycle)

    promotion = commands.add_parser(
        "promotion-status",
        help=(
            "Evaluate evidence for a human live-canary review. This never "
            "enables live trading."
        ),
    )
    promotion.add_argument("research_report", type=Path)
    promotion.add_argument(
        "--evidence-epoch",
        help="Evidence epoch to evaluate; defaults to the active epoch.",
    )
    promotion.add_argument(
        "--research-reproduced",
        action="store_true",
        help="Attest that the report was independently reproduced.",
    )
    promotion.set_defaults(handler=command_promotion_status, read_only_store=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    # Resolve after parse so a broken TRADING_ASSISTANT_POLICY cannot brick
    # --help or an explicit --policy. Handlers also call _cli_policy_path
    # so direct test invocations with default=None stay safe.
    try:
        args.policy = _cli_policy_path(args)
    except FileNotFoundError as exc:
        raise SystemExit(f"Policy resolution failed: {exc}") from exc
    # verify-db-schema declares needs_store=False: constructing the store
    # would migrate the database before the handler runs, making read-only
    # verification of a pre-migration database impossible.
    if not getattr(args, "needs_store", True):
        args.handler(args)
        return
    store = AssistantStore(
        args.database,
        read_only=getattr(args, "read_only_store", False),
    )
    args.handler(args, store)


if __name__ == "__main__":
    main()
