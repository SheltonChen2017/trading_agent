"""Operational readiness checks for the paper-trading execution service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from assistant.policy import TradingPolicy
from assistant.proposal_status import (
    BROKER_ACCEPTED,
    CANCEL_PENDING,
    EXECUTED,
    PARTIALLY_FILLED,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
)
from assistant.storage import AssistantStore

CRITICAL_UNRESOLVED_STATUSES = (
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    EXECUTED,
)
ACTIVE_ORDER_STATUSES = (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING)


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
    environment_kill_switch = os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"
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
            "active_order_budget",
            len(active) <= policy.max_open_orders,
            f"{len(active)} active assistant order(s); cap={policy.max_open_orders}.",
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
    checks.append(
        _check(
            "daily_submission_budget",
            usage["submitted_order_count"] <= policy.max_daily_order_count
            and usage["submitted_notional"] <= policy.max_daily_submitted_notional,
            (
                f"{usage['submitted_order_count']}/{policy.max_daily_order_count} orders, "
                f"${usage['submitted_notional']:,.2f}/"
                f"${policy.max_daily_submitted_notional:,.2f} submitted notional."
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
                    "broker_open_order_budget",
                    len(open_orders) <= policy.max_open_orders,
                    f"{len(open_orders)} broker open order(s); cap={policy.max_open_orders}.",
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
