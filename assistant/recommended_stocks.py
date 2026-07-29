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
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from assistant.ai_advisor import suggest_similar_tickers
from assistant.similarity_evidence import compute_similarity_evidence, format_evidence_summary
from assistant.storage import AssistantStore
from assistant.ticker_verification import RECENT_IPO_ELIGIBILITY_POLICY, verify_tickers

_FINNHUB_IPO_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/ipo"
_IPO_LOOKBACK_DAYS = 30
_IPO_ACCEPTED_STATUSES = {"priced", "listed"}
_MAX_IPO_DATE_GAP_DAYS = 10  # if the first real trading bar is this far from the provider's claimed IPO date, the identity likely doesn't match (e.g. a reused/renamed ticker)


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


def fetch_recent_ipos(count: int = 10, lookback_days: int = _IPO_LOOKBACK_DAYS) -> list[dict]:
    """Finnhub /calendar/ipo, gated on FINNHUB_API_KEY. Returns [] gracefully
    if the key is unset, the request fails, or the response is malformed --
    matches the open_orders_available=False graceful-degradation pattern
    already used in assistant.context_builder.build_portfolio_snapshot_from_alpaca().
    I cannot obtain this key on your behalf -- sign up for a free Finnhub
    account yourself if you want this data source live.

    Only returns entries whose `status` is actually "priced" or "listed"
    (independent review: Finnhub's calendar also includes merely "expected"
    or "filed" IPOs that haven't traded at all yet) and whose date is not
    in the future -- an upcoming/unconfirmed IPO is not yet a real,
    tradeable security to recommend."""
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
        results = []
        for e in entries:
            symbol = e.get("symbol")
            status = str(e.get("status", "")).strip().lower()
            date_str = e.get("date", "")
            if not symbol or status not in _IPO_ACCEPTED_STATUSES:
                continue
            try:
                if date.fromisoformat(date_str) > today:
                    continue
            except ValueError:
                continue
            results.append({"ticker": symbol, "name": e.get("name", ""), "date": date_str, "status": status})
        return results[:count]
    except Exception:
        return []


def build_recommended_tickers(
    held_tickers: list[str] | None = None, store: AssistantStore | None = None
) -> tuple[list[RecommendedTicker], list[str]]:
    """Composes most-actives + IPO calendar + assistant.ai_advisor.suggest_similar_tickers()
    through the SAME two-tier partition + verify_tickers() pipeline as the
    Watchlist's similar-stocks feature -- most-actives and IPO-calendar
    results get identical scrutiny to AI suggestions. Returns (recommended,
    dropped_labels) for one combined "N could not be verified" caption.

    `held_tickers` -- the account's ACTUAL current positions -- is used two
    ways: (1) every lane excludes them, so "not held" in the UI is an
    enforced property, not just a label; (2) it's the basis for the
    "ai_suggested" lane ("similar to what you actually hold"). If
    `held_tickers` is empty/None, the ai_suggested lane is skipped entirely
    rather than falling back to an arbitrary fixed basket (independent
    review, 2026-07-28: a prior version silently substituted
    config.UNIVERSE[:5] here, which could make the Briefing appear
    personalized to a user's holdings when it was actually just always
    suggesting tickers similar to a fixed mega-cap-tech basket)."""
    now = datetime.now(timezone.utc).isoformat()
    held_set = {t.upper() for t in (held_tickers or [])}
    recommended: list[RecommendedTicker] = []
    dropped: list[str] = []

    most_active_candidates = [c for c in fetch_most_active_tickers() if c["ticker"].upper() not in held_set]
    verified, batch_dropped = verify_tickers([c["ticker"] for c in most_active_candidates])
    dropped.extend(batch_dropped)
    detail_by_ticker = {c["ticker"]: c for c in most_active_candidates}
    for v in verified:
        c = detail_by_ticker.get(v["ticker"], {})
        volume = c.get("volume")
        detail = f"{v.get('longName') or c.get('name') or v['ticker']} -- trading volume today: {volume:,}" if volume else f"{v.get('longName') or v['ticker']}"
        recommended.append(RecommendedTicker(ticker=v["ticker"], reason_category="most_active", detail=detail, fetched_at=now))

    ipo_candidates = [c for c in fetch_recent_ipos() if c["ticker"].upper() not in held_set]
    verified, batch_dropped = verify_tickers(
        [c["ticker"] for c in ipo_candidates], policy=RECENT_IPO_ELIGIBILITY_POLICY
    )
    dropped.extend(batch_dropped)
    ipo_detail_by_ticker = {c["ticker"]: c for c in ipo_candidates}
    for v in verified:
        c = ipo_detail_by_ticker.get(v["ticker"], {})
        claimed_date = c.get("date", "")
        if _is_ipo_identity_mismatch(v.get("first_session_date"), claimed_date):
            dropped.append(v["ticker"])
            continue
        name = v.get("longName") or c.get("name") or v["ticker"]
        detail = (
            f"{name} -- IPO date: {claimed_date or 'unknown'} ({v['history_sessions']} completed trading "
            "session(s) -- volatility/trend estimates are not yet reliable this early)"
        )
        recommended.append(RecommendedTicker(ticker=v["ticker"], reason_category="recent_ipo", detail=detail, fetched_at=now))

    if held_set:
        held_list = sorted(held_set)
        raw_suggestions = suggest_similar_tickers(held_list, store=store)
        if raw_suggestions:
            raw_suggestions = [c for c in raw_suggestions if c.get("ticker", "").upper() not in held_set]
            reason_by_ticker = {c["ticker"].upper(): c["reason"] for c in raw_suggestions}
            # Every AI suggestion goes through the SAME eligibility check,
            # regardless of whether it happens to be a known config.UNIVERSE
            # member or a wildcard pick (independent review: UNIVERSE was
            # built for research-scan coverage, not recommendation
            # eligibility -- a member can be illiquid, non-equity, or have
            # gone stale since being added; universe membership answers
            # "where did this come from," never "is this eligible today").
            candidate_tickers = list(dict.fromkeys(c["ticker"].upper() for c in raw_suggestions))
            verified, batch_dropped = verify_tickers(candidate_tickers)
            dropped.extend(batch_dropped)
            for v in verified:
                recommended.append(
                    RecommendedTicker(
                        ticker=v["ticker"], reason_category="ai_suggested",
                        detail=_similarity_detail(held_list, v["ticker"], reason_by_ticker.get(v["ticker"], "")),
                        fetched_at=now,
                    )
                )

    return recommended, dropped


def _is_ipo_identity_mismatch(first_session_date: str | None, claimed_ipo_date: str) -> bool:
    """Reject a ticker whose real first trading bar doesn't line up with the
    IPO date the provider claimed for it -- catches a reused/renamed ticker
    symbol masquerading as a fresh listing (independent review: "a ticker
    that passes may actually be suspicious -- e.g. a reused symbol with
    older history")."""
    if not first_session_date or not claimed_ipo_date:
        return False
    try:
        gap_days = abs((date.fromisoformat(first_session_date) - date.fromisoformat(claimed_ipo_date)).days)
    except ValueError:
        return False
    return gap_days > _MAX_IPO_DATE_GAP_DAYS


def _similarity_detail(held_tickers: list[str], candidate: str, llm_reason: str) -> str:
    """Pairs the LLM's stated reason with REAL, measured similarity evidence
    (correlation + sector/industry overlap) so a false claim -- a real,
    resolvable ticker with a wrong "why it's similar" story, e.g. CAT
    mislabeled as a semiconductor peer of NVDA -- is visibly checkable
    rather than silently trusted (independent review: ticker-existence
    verification alone cannot catch this)."""
    evidence = compute_similarity_evidence(held_tickers, candidate)
    return f"{llm_reason} [measured: {format_evidence_summary(evidence)}]"
