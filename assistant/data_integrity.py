"""GR-4: recorded provider fetches, health alerting, and the GR-0 adapter.

data/price_source.py holds the pure contracts (protocol, fetch records,
calendar-based freshness). This module adds the stateful half:

  * ``fetch_daily_bars_recorded()`` -- every production read-path fetch
    goes through here, so success AND failure land in the append-only
    ``data_provider_fetches`` table. Repeated failure raises a
    deduplicated operational alert instead of the old silent-empty-frame
    outage mode; the data itself is returned exactly as the provider gave
    it (never synthesized, never filled).
  * ``build_data_layer_evidence()`` -- derives GR-0's three data_integrity
    checks (price_freshness, provider_health, adjustment_honesty) from
    those authenticated records. There is deliberately NO caller-settable
    boolean: a machine with no recorded fetches is blocked, not assumed
    healthy.

Boundary note: this lives under assistant/ (not data/) because it imports
AssistantStore; data/ stays importable by research code with no assistant
dependency, and nothing here imports ml.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from assistant.storage import AssistantStore
from data.price_source import (
    BAR_DATA_CLASS,
    BarFreshness,
    PriceSource,
    ProviderFetchRecord,
    YFinanceDailyBars,
    build_fetch_record,
    evaluate_bar_freshness,
)

# Consecutive failed fetches before the durable alert fires. One failure is
# a blip the caller's own degraded surface already shows; a streak means
# the provider (or network) is down and the operator should know without
# looking.
PROVIDER_ALERT_FAILURE_STREAK = 3

_PROVIDER_ALERT_CATEGORY = "data_provider"


def provider_health_fingerprint(provider_id: str, data_class: str) -> str:
    return f"provider_health:{provider_id}:{data_class}"


def _record(store: AssistantStore, record: ProviderFetchRecord) -> None:
    store.record_provider_fetch(
        provider_id=record.provider_id,
        data_class=record.data_class,
        fetched_at=record.fetched_at,
        requested_count=record.requested_count,
        returned_count=record.returned_count,
        missing_tickers=record.missing_tickers,
        ok=record.ok,
        error=record.error,
        point_in_time_lineage=record.point_in_time_lineage,
        latest_session=record.latest_session,
    )


def fetch_daily_bars_recorded(
    store: AssistantStore,
    tickers: list[str],
    lookback_days: int,
    *,
    source: PriceSource | None = None,
    now: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch daily bars with health recording and streak alerting.

    Returns exactly what the provider returned (possibly empty -- callers
    keep their own degraded rendering); the difference from calling the
    provider directly is that the outcome is durably recorded and a
    failure streak of PROVIDER_ALERT_FAILURE_STREAK raises a deduplicated
    critical operational alert. A provider exception is recorded and
    swallowed here for the same reason build_market_regime() already
    swallows it: a read-only briefing must remain available during an
    outage -- but now the outage is evidence, not silence.
    """
    active_source = source or YFinanceDailyBars()
    data: dict[str, pd.DataFrame] = {}
    caught: Exception | None = None
    try:
        data = active_source.fetch_daily_bars(tickers, lookback_days)
    except Exception as exc:  # recorded, alerted, surfaced as degraded data
        caught = exc
    record = build_fetch_record(
        active_source,
        tickers,
        data,
        data_class=BAR_DATA_CLASS,
        error=caught,
        fetched_at=now,
    )
    _record(store, record)
    if not record.ok:
        streak = store.consecutive_provider_failures(
            provider_id=record.provider_id, data_class=record.data_class
        )
        if streak >= PROVIDER_ALERT_FAILURE_STREAK:
            store.upsert_operational_alert(
                fingerprint=provider_health_fingerprint(
                    record.provider_id, record.data_class
                ),
                severity="critical",
                category=_PROVIDER_ALERT_CATEGORY,
                message=(
                    f"Data provider {record.provider_id} has failed "
                    f"{streak} consecutive {record.data_class} fetches; "
                    "market-data surfaces are degraded."
                ),
                details={
                    "provider_id": record.provider_id,
                    "data_class": record.data_class,
                    "consecutive_failures": streak,
                    "last_error": record.error,
                },
                seen_at=record.fetched_at,
            )
    return data


def build_data_layer_evidence(
    store: AssistantStore, *, now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """GR-0's three data_integrity checks, derived from recorded fetches.

    Shapes are {name: {ok, detail, evidence}}. Fail-closed: with zero
    recorded fetches every check is not-ok with an explicit "no recorded
    provider fetches" reason -- absence of evidence is a blocker, never a
    pass. ``adjustment_honesty`` passes when every recorded fetch carries
    an explicit lineage declaration and non-point-in-time data is honestly
    declared as such; it does NOT claim the data is point-in-time (the
    promotion gates own that question, unchanged).
    """
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fetches = store.list_provider_fetches(data_class=BAR_DATA_CLASS, limit=100)
    if not fetches:
        missing = {
            "ok": False,
            "detail": (
                "no recorded provider fetches yet; the data layer has not "
                "produced evidence to derive this check from"
            ),
            "evidence": {"recorded_fetches": 0},
        }
        return {
            "price_freshness": dict(missing),
            "provider_health": dict(missing),
            "adjustment_honesty": dict(missing),
        }

    provider_ids = sorted({record["provider_id"] for record in fetches})
    streaks = {
        provider_id: store.consecutive_provider_failures(
            provider_id=provider_id, data_class=BAR_DATA_CLASS
        )
        for provider_id in provider_ids
    }
    worst_streak = max(streaks.values())
    provider_health = {
        "ok": worst_streak < PROVIDER_ALERT_FAILURE_STREAK,
        "detail": (
            "no provider failure streak"
            if worst_streak == 0
            else f"consecutive failures by provider: {streaks}"
        ),
        "evidence": {
            "consecutive_failures": streaks,
            "alert_threshold": PROVIDER_ALERT_FAILURE_STREAK,
        },
    }

    latest_ok = None
    for provider_id in provider_ids:
        candidate = store.latest_successful_provider_fetch(
            provider_id=provider_id, data_class=BAR_DATA_CLASS
        )
        if candidate and (
            latest_ok is None or candidate["fetched_at"] > latest_ok["fetched_at"]
        ):
            latest_ok = candidate
    if latest_ok is None:
        price_freshness: dict[str, Any] = {
            "ok": False,
            "detail": "no successful provider fetch on record",
            "evidence": {"recorded_fetches": len(fetches)},
        }
    else:
        freshness: BarFreshness = evaluate_bar_freshness(
            latest_ok["latest_session"], now=at
        )
        price_freshness = {
            "ok": freshness.fresh,
            "detail": freshness.detail,
            "evidence": {
                "latest_session": freshness.latest_session,
                "expected_session": freshness.expected_session,
                "fetched_at": latest_ok["fetched_at"],
                "provider_id": latest_ok["provider_id"],
            },
        }

    non_pit = sorted(
        {
            record["provider_id"]
            for record in fetches
            if not record["point_in_time_lineage"]
        }
    )
    adjustment_honesty = {
        # Every fetch record carries an explicit declaration by
        # construction (the column is NOT NULL); the check therefore
        # passes as HONESTY, with the non-point-in-time reality stated
        # rather than laundered.
        "ok": True,
        "detail": (
            "all recorded fetches declare lineage explicitly"
            + (
                f"; non-point-in-time (exploratory) providers: {non_pit}"
                if non_pit
                else "; all providers declare point-in-time lineage"
            )
        ),
        "evidence": {
            "non_point_in_time_providers": non_pit,
            "recorded_fetches": len(fetches),
        },
    }

    return {
        "price_freshness": price_freshness,
        "provider_health": provider_health,
        "adjustment_honesty": adjustment_honesty,
    }
