"""
Recommended-stocks candidates for the Briefing tab -- tickers NOT currently
held, surfaced for exploration only. Deliberately a separate, lightweight
dataclass from assistant.schemas.SignalEvidence/EvidenceStatus: that schema
requires backtest-style provenance (discovery fraction, bootstrap method,
hold-period return) that doesn't fit "this ticker is heavily traded today" or
"this ticker just IPO'd" -- there is no meaningful confirmation-split/
reproducibility claim to make about either fact. Presence here is NOT an
allocation authorization or a proposal -- same precedent as
config.DEFENSIVE_CARRY_TICKERS.

Every candidate ticker (most-active, IPO-calendar, or AI-suggested) goes
through the SAME assistant.ticker_verification.verify_tickers() discipline
before becoming a RecommendedTicker -- a screener glitch or a stale/incorrect
data-provider entry deserves no less scrutiny than a hallucinated ticker.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import config
from assistant.ai_advisor import suggest_similar_tickers
from assistant.ticker_verification import partition_by_universe, verify_tickers

_FINNHUB_IPO_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/ipo"


@dataclasses.dataclass(frozen=True)
class RecommendedTicker:
    ticker: str
    reason_category: Literal["most_active", "recent_ipo", "ai_suggested"]
    detail: str
    fetched_at: str


def fetch_most_active_tickers(count: int = 10) -> list[dict]:
    """Wraps yf.screen("most_actives", count=count) -- confirmed working live
    with the currently-installed yfinance, zero new dependencies. Returns []
    on any failure. Honest framing only: this is TRADING VOLUME and price
    movement, NOT buy-vs-sell order flow -- no legitimate retail-accessible
    data source provides true order imbalance. Never label this "most
    bought" anywhere in code, comments, or UI copy."""
    try:
        import yfinance as yf

        result = yf.screen("most_actives", count=count)
        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        return [
            {
                "ticker": q.get("symbol"),
                "name": q.get("shortName", ""),
                "volume": q.get("regularMarketVolume"),
            }
            for q in quotes
            if q.get("symbol")
        ]
    except Exception:
        return []


def is_ipo_calendar_configured() -> bool:
    return bool(os.environ.get("FINNHUB_API_KEY"))


def fetch_recent_ipos(count: int = 10, lookback_days: int = 30) -> list[dict]:
    """Finnhub /calendar/ipo, gated on FINNHUB_API_KEY. Returns [] gracefully
    if the key is unset, the request fails, or the response is malformed --
    matches the open_orders_available=False graceful-degradation pattern
    already used in assistant.context_builder.build_portfolio_snapshot_from_alpaca().
    I cannot obtain this key on your behalf -- sign up for a free Finnhub
    account yourself if you want this data source live."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return []

    try:
        import requests

        today = datetime.now(timezone.utc).date()
        params = {
            "from": (today - timedelta(days=lookback_days)).isoformat(),
            "to": today.isoformat(),
            "token": api_key,
        }
        response = requests.get(_FINNHUB_IPO_CALENDAR_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        entries = payload.get("ipoCalendar", []) if isinstance(payload, dict) else []
        return [
            {
                "ticker": e.get("symbol"),
                "name": e.get("name", ""),
                "date": e.get("date", ""),
                "status": e.get("status", ""),
            }
            for e in entries
            if e.get("symbol")
        ][:count]
    except Exception:
        return []


def build_recommended_tickers(cart_context: list[str] | None = None) -> tuple[list[RecommendedTicker], list[str]]:
    """Composes most-actives + IPO calendar + assistant.ai_advisor.suggest_similar_tickers()
    (unscoped if cart_context is None) through the SAME two-tier partition +
    verify_tickers() pipeline as the Watchlist's similar-stocks feature --
    most-actives and IPO-calendar results get identical scrutiny to AI
    suggestions. Returns (recommended, dropped_labels) for one combined
    "N could not be verified" caption."""
    now = datetime.now(timezone.utc).isoformat()
    recommended: list[RecommendedTicker] = []
    dropped: list[str] = []

    most_active_candidates = fetch_most_active_tickers()
    verified, batch_dropped = verify_tickers([c["ticker"] for c in most_active_candidates])
    dropped.extend(batch_dropped)
    detail_by_ticker = {c["ticker"]: c for c in most_active_candidates}
    for v in verified:
        c = detail_by_ticker.get(v["ticker"], {})
        volume = c.get("volume")
        detail = f"{v.get('longName') or c.get('name') or v['ticker']} -- trading volume today: {volume:,}" if volume else f"{v.get('longName') or v['ticker']}"
        recommended.append(RecommendedTicker(ticker=v["ticker"], reason_category="most_active", detail=detail, fetched_at=now))

    ipo_candidates = fetch_recent_ipos()
    verified, batch_dropped = verify_tickers([c["ticker"] for c in ipo_candidates])
    dropped.extend(batch_dropped)
    ipo_detail_by_ticker = {c["ticker"]: c for c in ipo_candidates}
    for v in verified:
        c = ipo_detail_by_ticker.get(v["ticker"], {})
        detail = f"{v.get('longName') or c.get('name') or v['ticker']} -- IPO date: {c.get('date', 'unknown')}"
        recommended.append(RecommendedTicker(ticker=v["ticker"], reason_category="recent_ipo", detail=detail, fetched_at=now))

    raw_suggestions = suggest_similar_tickers(cart_context or list(config.UNIVERSE[:5]))
    if raw_suggestions:
        from_universe, wildcard = partition_by_universe(raw_suggestions, universe=config.UNIVERSE)
        reason_by_ticker = {c["ticker"].upper(): c["reason"] for c in raw_suggestions}
        for c in from_universe:
            recommended.append(
                RecommendedTicker(ticker=c["ticker"].upper(), reason_category="ai_suggested", detail=c["reason"], fetched_at=now)
            )
        if wildcard:
            verified, batch_dropped = verify_tickers([c["ticker"] for c in wildcard])
            dropped.extend(batch_dropped)
            for v in verified:
                recommended.append(
                    RecommendedTicker(
                        ticker=v["ticker"], reason_category="ai_suggested",
                        detail=reason_by_ticker.get(v["ticker"], ""), fetched_at=now,
                    )
                )

    return recommended, dropped
