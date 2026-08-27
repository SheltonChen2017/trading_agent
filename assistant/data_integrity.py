"""GR-4: recorded provider fetches, health alerting, and the GR-0 adapter.

data/price_source.py holds the pure contracts (protocol, fetch records,
calendar-based freshness). This module adds the stateful half:

  * ``fetch_daily_bars_recorded()`` -- every production read-path fetch
    goes through here, so success AND failure land in the append-only
    ``data_provider_fetches`` table. Repeated failure raises a
    deduplicated operational alert instead of the old silent-empty-frame
    outage mode. Per-ticker validation omits malformed frames while preserving
    clean siblings; observations are never synthesized, filled, or repaired.
  * ``build_data_layer_evidence()`` -- derives GR-0's three data_integrity
    checks (price_freshness, provider_health, adjustment_honesty) from
    those authenticated records. There is deliberately NO caller-settable
    boolean: a machine with no recorded fetches is blocked, not assumed
    healthy.

Boundary note: this lives under assistant/ (not data/) because it consumes the
assistant-owned operational-store contract; data/ stays importable by research
code with no assistant dependency, and nothing here imports ml.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from assistant.storage_contracts import StrategyOperationalStore
from data.price_source import (
    BAR_DATA_CLASS,
    BarFreshness,
    PriceSource,
    ProviderFetchRecord,
    YFinanceDailyBars,
    build_validated_fetch,
    canonical_requested_tickers,
    evaluate_bar_freshness,
)

# Consecutive failed fetches before the durable alert fires. One failure is
# a blip the caller's own degraded surface already shows; a streak means
# the provider, transport, or response usability is persistently unhealthy
# and the operator should know without looking.
PROVIDER_ALERT_FAILURE_STREAK = 3

_PROVIDER_ALERT_CATEGORY = "data_provider"
_PROVIDER_DATA_QUALITY_PREFIX = "provider_data_quality"


def provider_health_fingerprint(provider_id: str, data_class: str) -> str:
    return f"provider_health:{provider_id}:{data_class}"


def provider_data_quality_fingerprint(provider_id: str, data_class: str) -> str:
    return f"{_PROVIDER_DATA_QUALITY_PREFIX}:{provider_id}:{data_class}"


def _record(store: StrategyOperationalStore, record: ProviderFetchRecord) -> None:
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


def _alert_degraded_batch(
    store: StrategyOperationalStore,
    record: ProviderFetchRecord,
) -> None:
    """Persist the dimensions the provider-fetch row cannot encode as a map."""

    if not record.transport_ok:
        # Transport failures use the existing consecutive-failure alert path.
        return
    at = datetime.fromisoformat(record.fetched_at)
    session_by_ticker = dict(record.ticker_latest_sessions)
    error_by_ticker = dict(record.ticker_errors)
    freshness_by_ticker: dict[str, dict[str, Any]] = {}
    for ticker in record.usable_tickers:
        freshness = evaluate_bar_freshness(session_by_ticker[ticker], now=at)
        freshness_by_ticker[ticker] = {
            "fresh": freshness.fresh,
            "latest_session": freshness.latest_session,
            "expected_session": freshness.expected_session,
            "detail": freshness.detail,
        }
    missing_freshness = (
        evaluate_bar_freshness(None, now=at)
        if record.missing_tickers
        else None
    )
    for ticker in record.missing_tickers:
        freshness_by_ticker[ticker] = {
            "fresh": False,
            "latest_session": None,
            "expected_session": (
                missing_freshness.expected_session
                if missing_freshness is not None
                else None
            ),
            "detail": error_by_ticker.get(ticker, "ticker data is unavailable"),
        }

    stale_tickers = sorted(
        ticker
        for ticker, evidence in freshness_by_ticker.items()
        if not evidence["fresh"]
    )
    if record.universe_complete and not stale_tickers:
        return

    store.upsert_operational_alert(
        fingerprint=provider_data_quality_fingerprint(
            record.provider_id, record.data_class
        ),
        severity="warning",
        category=_PROVIDER_ALERT_CATEGORY,
        message=(
            f"Data provider {record.provider_id} returned a degraded "
            f"{record.data_class} batch; affected requested tickers: "
            + ", ".join(stale_tickers)
        ),
        details={
            "provider_id": record.provider_id,
            "data_class": record.data_class,
            "transport_ok": record.transport_ok,
            "requested_count": record.requested_count,
            "usable_tickers": list(record.usable_tickers),
            "missing_tickers": list(record.missing_tickers),
            "universe_complete": record.universe_complete,
            "worst_required_session": record.latest_session,
            "ticker_freshness": freshness_by_ticker,
            "ticker_errors": error_by_ticker,
        },
        seen_at=record.fetched_at,
    )


def fetch_daily_bars_recorded(
    store: StrategyOperationalStore,
    tickers: list[str],
    lookback_days: int,
    *,
    source: PriceSource | None = None,
    now: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch daily bars with health recording and streak alerting.

    Returns each usable requested frame without modifying its observations;
    malformed/missing ticker frames are omitted while clean siblings survive.
    The outcome is durably recorded and a
    failure streak of PROVIDER_ALERT_FAILURE_STREAK raises a deduplicated
    critical operational alert. A provider exception is recorded and
    swallowed here for the same reason build_market_regime() already
    swallows it: a read-only briefing must remain available during an
    outage -- but now the outage is evidence, not silence.
    """
    active_source = source or YFinanceDailyBars()
    requested = list(canonical_requested_tickers(tickers))
    raw_data: dict[str, pd.DataFrame] = {}
    caught: Exception | None = None
    try:
        raw_data = active_source.fetch_daily_bars(requested, lookback_days)
    except Exception as exc:  # recorded, alerted, surfaced as degraded data
        caught = exc
    data, record = build_validated_fetch(
        active_source,
        requested,
        raw_data,
        data_class=BAR_DATA_CLASS,
        error=caught,
        fetched_at=now,
    )
    _record(store, record)
    _alert_degraded_batch(store, record)
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
    store: StrategyOperationalStore, *, now: datetime | None = None
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

    # Freshness/completeness describe the latest attempted read, not the last
    # convenient success. Otherwise one malformed/empty current response can
    # be hidden behind an older healthy fetch until the failure-streak alert
    # happens to trip.
    latest_fetch = max(
        fetches,
        key=lambda record: datetime.fromisoformat(
            record["fetched_at"]
        ).astimezone(timezone.utc),
    )
    if (
        latest_fetch["returned_count"] == 0
        or latest_fetch["latest_session"] is None
    ):
        price_freshness: dict[str, Any] = {
            "ok": False,
            "detail": "latest provider fetch returned no usable requested bars",
            "evidence": {
                "recorded_fetches": len(fetches),
                "fetched_at": latest_fetch["fetched_at"],
                "provider_id": latest_fetch["provider_id"],
                "requested_count": latest_fetch["requested_count"],
                "returned_count": latest_fetch["returned_count"],
                "missing_tickers": list(latest_fetch["missing_tickers"]),
                "universe_complete": False,
            },
        }
    else:
        freshness: BarFreshness = evaluate_bar_freshness(
            latest_fetch["latest_session"], now=at
        )
        universe_complete = (
            latest_fetch["returned_count"] == latest_fetch["requested_count"]
        )
        missing_tickers = list(latest_fetch["missing_tickers"])
        freshness_ok = freshness.fresh and universe_complete
        detail = freshness.detail
        if not universe_complete:
            detail = (
                "requested universe incomplete; missing/unusable tickers: "
                f"{missing_tickers}; worst usable-symbol freshness: {detail}"
            )
        price_freshness = {
            "ok": freshness_ok,
            "detail": detail,
            "evidence": {
                "latest_session": freshness.latest_session,
                "expected_session": freshness.expected_session,
                "fetched_at": latest_fetch["fetched_at"],
                "provider_id": latest_fetch["provider_id"],
                "requested_count": latest_fetch["requested_count"],
                "returned_count": latest_fetch["returned_count"],
                "missing_tickers": missing_tickers,
                "universe_complete": universe_complete,
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
