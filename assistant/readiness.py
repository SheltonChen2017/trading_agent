"""Operational readiness checks for the paper-trading execution service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from assistant.kill_switch import env_kill_switch_active
from assistant.dispatch_fence import get_runtime_emergency_stop
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
from assistant.temporal_integrity import (
    MAX_READINESS_WINDOW_SECONDS as _MAX_READINESS_WINDOW_SECONDS,
    bounded_timing_number,
    timestamp_disposition,
)

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
# Tests and production fault-injection may replace the module's ``datetime``
# clock with a subclass.  Keep the real type separately so an ordinary aware
# datetime supplied by the caller remains valid under that injected clock.
_DATETIME_TYPE = datetime


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, _DATETIME_TYPE):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _bounded_readiness_number(name: str, value: Any, *, maximum: float) -> float:
    return bounded_timing_number(
        name,
        value,
        minimum=0.0,
        maximum=maximum,
        minimum_inclusive=False,
    )


def _aware_readiness_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if (
        not isinstance(value, _DATETIME_TYPE)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("now must be a timezone-aware datetime or None")
    return value.astimezone(timezone.utc)


def _claim_timestamp_disposition(value: Any, *, now: datetime) -> dict[str, Any]:
    return timestamp_disposition(value, now=now, field="updated_at")


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
    explicit_now = now is not None
    now = _aware_readiness_now(now)
    max_reconciliation_age_minutes = _bounded_readiness_number(
        "max_reconciliation_age_minutes",
        max_reconciliation_age_minutes,
        maximum=_MAX_READINESS_WINDOW_SECONDS / 60.0,
    )
    stale_claim_seconds = _bounded_readiness_number(
        "stale_claim_seconds",
        stale_claim_seconds,
        maximum=_MAX_READINESS_WINDOW_SECONDS,
    )
    if type(check_broker) is not bool:
        raise ValueError("check_broker must be an actual bool")
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
    try:
        runtime_stop = get_runtime_emergency_stop(store.path)
    except Exception as exc:
        checks.append(
            _check(
                "runtime_emergency_stop",
                False,
                f"state could not be read; treating the runtime stop as active: {exc}",
            )
        )
    else:
        checks.append(
            _check(
                "runtime_emergency_stop",
                runtime_stop.get("active") is False,
                str(runtime_stop.get("reason") or "inactive"),
            )
        )

    try:
        kill_switch = store.get_kill_switch()
    except Exception as exc:
        checks.append(
            _check(
                "persistent_kill_switch",
                False,
                f"state is unreadable; treating the emergency stop as active: {exc}",
            )
        )
    else:
        checks.append(
            _check(
                "persistent_kill_switch",
                not kill_switch["active"],
                str(kill_switch["reason"] or "inactive"),
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
    unreadable_claim_ages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    future_claim_ages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    claim_proposals = store.list_proposals_by_statuses(STRANDED_CLAIM_STATUSES)
    claim_checked_at = now if explicit_now else datetime.now(timezone.utc)
    for proposal in claim_proposals:
        disposition = _claim_timestamp_disposition(
            proposal.get("updated_at"), now=claim_checked_at
        )
        if disposition["kind"] == "material_future":
            future_claim_ages.append((proposal, disposition))
        elif not disposition["integrity_ok"]:
            unreadable_claim_ages.append((proposal, disposition))
        elif float(disposition["signed_age_seconds"] or 0.0) > stale_claim_seconds:
            stranded.append(proposal)
    claim_age_issues = bool(stranded or unreadable_claim_ages or future_claim_ages)
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
                f"{p['proposal_id']}:{p['status']}={p.get('updated_at')!r} "
                f"({d['kind']})"
                for p, d in unreadable_claim_ages
            )
        )
    if future_claim_ages:
        detail_parts.append(
            "materially future updated_at: " + ", ".join(
                f"{p['proposal_id']}:{p['status']}={p.get('updated_at')!r}, "
                f"signed_age_seconds={d['signed_age_seconds']:.6f}"
                for p, d in future_claim_ages
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
    if future_claim_ages:
        detail_parts.append(
            "do not auto-reclaim from future clock evidence; reconcile the clock "
            "and claim metadata manually"
        )
    checks.append(
        _check(
            "stranded_pre_broker_claims",
            not claim_age_issues,
            "none" if not claim_age_issues else "; ".join(detail_parts) + ".",
        )
    )

    last_reconciliation = store.get_system_state("last_order_reconciliation")
    reconciliation_state = (
        last_reconciliation if isinstance(last_reconciliation, dict) else {}
    )
    # AP-7 (second instance, found by counter-review): compare against a clock
    # captured AFTER reading the row, exactly as assistant/operations.py does.
    # `monitor-orders` rewrites this key every poll (30s in the deployed task)
    # while this function's entry clock is already minutes old -- the window
    # here contains a full SQLite integrity_check and several proposal
    # queries, so it is WIDER than the operations.py window. Reusing the entry
    # clock made a valid concurrent write look future-dated, failing the
    # `timedelta(0) <=` guard and turning a healthy reconciliation into a
    # readiness failure. An explicitly supplied clock stays frozen, so
    # deterministic/as-of evaluation and genuine future-date refusal are
    # unchanged.
    reconciliation_checked_at = now if explicit_now else datetime.now(timezone.utc)
    reconciled_at = _parse_timestamp(
        reconciliation_state.get("at")
    )
    reconciliation_age = (
        None if reconciled_at is None else reconciliation_checked_at - reconciled_at
    )
    reconciliation_error_count = int(reconciliation_state.get("error_count", 0))
    timestamp_integrity_error_count = int(
        reconciliation_state.get("timestamp_integrity_error_count", 0)
    )
    reconciliation_fresh = (
        reconciled_at is not None
        # FCS-017: a future-dated reconciliation must not read as fresh.
        and timedelta(0)
        <= reconciliation_age
        <= timedelta(minutes=max_reconciliation_age_minutes)
        and reconciliation_error_count == 0
        and timestamp_integrity_error_count == 0
    )
    checks.append(
        _check(
            "reconciliation_freshness",
            reconciliation_fresh,
            (
                "never completed"
                if reconciled_at is None
                else f"last completed at {reconciled_at.isoformat()}, "
                f"age_seconds={reconciliation_age.total_seconds():.6f}, "
                f"errors={reconciliation_error_count}, "
                f"timestamp_integrity_errors={timestamp_integrity_error_count}"
            ),
        )
    )

    trading_day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    usage = store.get_execution_budget_usage(trading_day)
    fill_evidence_status = usage.get("evidence_status")
    fill_integrity_errors = usage.get("integrity_errors")
    fill_ledger_ok = (
        fill_evidence_status
        in {"provider_exact", "legacy_rounded_unrecoverable"}
        and isinstance(fill_integrity_errors, list)
        and not fill_integrity_errors
    )
    checks.append(
        _check(
            "fill_ledger_integrity",
            fill_ledger_ok,
            (
                f"evidence_status={fill_evidence_status!r}; no integrity errors"
                if fill_ledger_ok
                else (
                    f"evidence_status={fill_evidence_status!r}; "
                    f"integrity_errors={fill_integrity_errors!r}"
                )
            ),
        )
    )
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
