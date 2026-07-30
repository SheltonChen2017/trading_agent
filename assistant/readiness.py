"""Operational readiness checks for the paper-trading execution service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from assistant.kill_switch import env_kill_switch_active
from assistant.money import to_decimal
from assistant.policy import TradingPolicy
from assistant.proposal_status import (
    APPROVED,
    BROKER_ACCEPTED,
    CANCEL_PENDING,
    EXECUTED,
    PARTIALLY_FILLED,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    VALIDATING,
)
from assistant.storage import AssistantStore

CRITICAL_UNRESOLVED_STATUSES = (
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    EXECUTED,
)
ACTIVE_ORDER_STATUSES = (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING)

# Pre-broker statuses that hold a ticker/side slot against new proposals (see
# proposal_status.IN_FLIGHT_INTENT_STATUSES). Readiness must surface a STALE one
# because it silently blocks that ticker while looking like nothing is wrong:
# neither CRITICAL_UNRESOLVED_STATUSES nor ACTIVE_ORDER_STATUSES covers them, so
# readiness used to report ready=True while proposals for that ticker could not
# be claimed at all (found 2026-07-30 reviewing the duplicate-guard change that
# introduced the blocking).
STRANDED_CLAIM_STATUSES = (VALIDATING, APPROVED)


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def transaction_readiness(
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    broker_module=None,
    now: datetime | None = None,
    max_reconciliation_age_minutes: float = 5.0,
    stale_claim_seconds: float = 900.0,
    check_broker: bool = True,
) -> dict[str, Any]:
    """Return a machine-readable, fail-closed readiness report."""
    now = now or datetime.now(timezone.utc)
    checks: list[dict[str, Any]] = []

    try:
        policy.validate()
        checks.append(_check("policy", True, f"{policy.name} ({policy.version}) is valid."))
    except Exception as exc:
        checks.append(_check("policy", False, str(exc)))
    checks.append(
        _check(
            "policy_execution_mode",
            policy.execution_mode == "paper",
            f"execution_mode={policy.execution_mode!r}",
        )
    )

    integrity = store.database_integrity_check()
    checks.append(
        _check(
            "database_integrity",
            integrity == ["ok"],
            ", ".join(integrity),
        )
    )
    environment_kill_switch = env_kill_switch_active()
    checks.append(
        _check(
            "environment_kill_switch",
            not environment_kill_switch,
            "active" if environment_kill_switch else "inactive",
        )
    )

    kill_switch = store.get_kill_switch()
    checks.append(
        _check(
            "persistent_kill_switch",
            not bool(kill_switch.get("active")),
            str(kill_switch.get("reason") or "inactive"),
        )
    )

    critical = store.list_proposals_by_statuses(CRITICAL_UNRESOLVED_STATUSES)
    checks.append(
        _check(
            "ambiguous_broker_outcomes",
            not critical,
            (
                "none"
                if not critical
                else ", ".join(f"{p['proposal_id']}:{p['status']}" for p in critical)
            ),
        )
    )

    active = store.list_proposals_by_statuses(ACTIVE_ORDER_STATUSES)
    checks.append(
        _check(
            # `<`, not `<=`: readiness answers "can ANOTHER order be
            # submitted right now", and execution_service refuses at
            # `len(open_orders) >= policy.max_open_orders`. With `<=` this
            # reported ready=True at a full budget (1 active, cap 1) while
            # execution would correctly refuse -- readiness must not promise
            # what the gate will deny (GPT review, 2026-07-29).
            "active_order_budget",
            len(active) < policy.max_open_orders,
            f"{len(active)} active assistant order(s); cap={policy.max_open_orders} "
            f"(room for {max(0, policy.max_open_orders - len(active))} more).",
        )
    )

    # A claim only counts as stranded once it is older than the recovery
    # threshold -- a proposal being validated RIGHT NOW is in flight, not stuck,
    # and must not fail readiness for everyone else. An unreadable timestamp is
    # different: its age cannot be proved, so fail closed and surface the row
    # instead of silently omitting a ticker/side block from the report.
    stranded: list[dict[str, Any]] = []
    unreadable_claim_ages: list[dict[str, Any]] = []
    for proposal in store.list_proposals_by_statuses(STRANDED_CLAIM_STATUSES):
        parsed = _parse_timestamp(proposal.get("updated_at"))
        if parsed is None:
            unreadable_claim_ages.append(proposal)
        elif now - parsed > timedelta(seconds=stale_claim_seconds):
            stranded.append(proposal)
    claim_age_issues = bool(stranded or unreadable_claim_ages)
    detail_parts: list[str] = []
    if stranded:
        detail_parts.append(
            "stale: " + ", ".join(
                f"{p['proposal_id']}:{p['status']}" for p in stranded
            )
        )
    if unreadable_claim_ages:
        detail_parts.append(
            "unreadable updated_at: " + ", ".join(
                f"{p['proposal_id']}:{p['status']}={p.get('updated_at')!r}"
                for p in unreadable_claim_ages
            )
        )
    if stranded:
        detail_parts.append(
            "stale entries hold their ticker/side against new proposals; "
            "clear with `recover-stale-claim <proposal_id>`"
        )
    if unreadable_claim_ages:
        detail_parts.append(
            "repair unreadable timestamp metadata before trading"
        )
    checks.append(
        _check(
            "stranded_pre_broker_claims",
            not claim_age_issues,
            "none" if not claim_age_issues else "; ".join(detail_parts) + ".",
        )
    )

    last_reconciliation = store.get_system_state("last_order_reconciliation")
    reconciled_at = _parse_timestamp(
        last_reconciliation.get("at") if isinstance(last_reconciliation, dict) else None
    )
    reconciliation_fresh = (
        reconciled_at is not None
        and now - reconciled_at <= timedelta(minutes=max_reconciliation_age_minutes)
        and int(last_reconciliation.get("error_count", 0)) == 0
    )
    checks.append(
        _check(
            "reconciliation_freshness",
            reconciliation_fresh,
            (
                "never completed"
                if reconciled_at is None
                else f"last completed at {reconciled_at.isoformat()}, "
                f"errors={last_reconciliation.get('error_count', 0)}"
            ),
        )
    )

    trading_day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    usage = store.get_execution_budget_usage(trading_day)
    submitted_notional = to_decimal(
        usage.get("submitted_notional_decimal", usage["submitted_notional"]),
        name="submitted_notional",
    )
    submitted_notional_cap = to_decimal(
        policy.max_daily_submitted_notional,
        name="max_daily_submitted_notional",
    )
    remaining_notional = max(
        submitted_notional_cap - submitted_notional,
        to_decimal(0),
    )
    checks.append(
        _check(
            # `<` on BOTH axes, derived from what
            # storage.reserve_execution_budget() actually enforces: it refuses
            # when `count + 1 > max_daily_orders` and when
            # `existing_notional + notional > max_daily_notional`. So another
            # order fits only if the count is strictly below its cap -- and,
            # because that same function rejects `notional <= 0`, the smallest
            # possible next order still has positive notional, which means
            # exact notional equality also leaves no room. `<=` reported
            # ready=True at 1/1 orders and a fully-consumed notional budget
            # while submission would have been refused (GPT review,
            # 2026-07-29).
            "daily_submission_budget",
            usage["submitted_order_count"] < policy.max_daily_order_count
            and submitted_notional < submitted_notional_cap,
            (
                f"{usage['submitted_order_count']}/{policy.max_daily_order_count} orders "
                f"(room for {max(0, policy.max_daily_order_count - usage['submitted_order_count'])} more), "
                f"${submitted_notional:,.2f}/"
                f"${policy.max_daily_submitted_notional:,.2f} submitted notional "
                f"(${remaining_notional:,.2f} remaining)."
            ),
        )
    )

    if check_broker:
        if broker_module is None:
            import execution.alpaca_broker as broker_module
        try:
            account = broker_module.get_account()
            account_ok = (
                bool(account.get("paper"))
                and str(account.get("status")).upper() == "ACTIVE"
                and not account.get("trading_blocked")
                and not account.get("account_blocked")
                and not account.get("trade_suspended_by_user")
            )
            checks.append(
                _check(
                    "broker_account",
                    account_ok,
                    (
                        f"paper={account.get('paper')}, status={account.get('status')}, "
                        f"trading_blocked={account.get('trading_blocked')}"
                    ),
                )
            )
        except Exception as exc:
            checks.append(_check("broker_account", False, str(exc)))
        try:
            open_orders = broker_module.get_open_orders()
            checks.append(
                _check(
                    # Same off-by-one as active_order_budget above -- this
                    # second site was not in the review but has the identical
                    # defect, and execution_service counts BROKER open orders
                    # (not assistant rows) for its own >= refusal, so this is
                    # the check that actually mirrors the gate.
                    "broker_open_order_budget",
                    len(open_orders) < policy.max_open_orders,
                    f"{len(open_orders)} broker open order(s); cap={policy.max_open_orders} "
                    f"(room for {max(0, policy.max_open_orders - len(open_orders))} more).",
                )
            )
        except Exception as exc:
            checks.append(_check("broker_open_order_budget", False, str(exc)))

    return {
        "ready": all(check["ok"] for check in checks),
        "checked_at": now.isoformat(),
        "database": str(Path(store.path)),
        "checks": checks,
        "active_orders": len(active),
        "daily_budget": usage,
    }
