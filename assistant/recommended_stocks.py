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
through the SAME assistant.ticker_verification.verify_tickers() identity
discipline before becoming a RecommendedTicker -- a screener glitch or a
stale/incorrect data-provider entry deserves no less scrutiny than a
hallucinated ticker.

All three lanes run under SUGGESTION_DISCLOSURE_POLICY (owner decision,
2026-08-12), not DEFAULT_ELIGIBILITY_POLICY: identity is still enforced
(resolves to real market data, EQUITY, US venue) but size/age/price screening
is not, because this surface is disclosure the reader judges rather than a
shortlist this project vouches for. The thresholds that are no longer enforced
are re-emitted per row by _eligibility_disclosure(). The Watchlist
similar-stocks surface is deliberately NOT included and still screens on
DEFAULT_ELIGIBILITY_POLICY.
"""
from __future__ import annotations

import dataclasses
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from assistant.ai_advisor import suggest_similar_tickers
from assistant.similarity_evidence import compute_similarity_evidence, format_evidence_summary
from assistant.storage import AssistantStore
from assistant.ticker_verification import (
    DEFAULT_ELIGIBILITY_POLICY,
    SUGGESTION_DISCLOSURE_POLICY,
    verify_tickers,
)

_FINNHUB_IPO_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/ipo"
_IPO_LOOKBACK_DAYS = 30
_IPO_ACCEPTED_STATUSES = {"priced", "listed"}
_MAX_IPO_DATE_GAP_DAYS = 10  # if the first real trading bar is this far from the provider's claimed IPO date, the identity likely doesn't match (e.g. a reused/renamed ticker)


PriceDirection = Literal["advancing", "declining", "unchanged"]


def classify_price_direction(change_percent: object) -> PriceDirection | None:
    """Today's price direction, or None when the provider did not give one.

    Deliberately NOT a buy/sell classification. Volume is symmetric -- every
    share traded was bought by someone and sold by someone else -- so a
    "most bought" column cannot be derived from this screener's volume field
    (see fetch_most_active_tickers). Direction of the price move is a separate,
    provider-reported fact; it lets the UI distinguish heavily traded names
    whose prices rose from heavily traded names whose prices fell.

    NaN is rejected explicitly: every ordered comparison against NaN is
    False, so an unguarded `> 0 ... < 0 ... else unchanged` chain would
    silently report a corrupt value as "unchanged" -- inventing a fact the
    provider never supplied.
    """
    if change_percent is None or isinstance(change_percent, bool):
        return None
    try:
        value = float(change_percent)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if value > 0:
        return "advancing"
    if value < 0:
        return "declining"
    return "unchanged"


def _eligibility_disclosure(verified: dict, *, include_history: bool = True) -> list[str]:
    """Restate, as plain visible facts, every screen SUGGESTION_DISCLOSURE_POLICY
    stopped enforcing (owner decision, 2026-08-12).

    Removing a filter and saying nothing would be a downgrade, not a
    disclosure: a 41-session listing and a decade-old blue chip would render
    identically, and the reader could no longer tell which rows the project's
    own thresholds would have excluded. So each removed gate becomes a note
    measured from the SAME verified record the gate used to read, compared
    against DEFAULT_ELIGIBILITY_POLICY's still-declared thresholds. A row that
    clears every threshold gets no notes at all.

    These are descriptions of thinness, not predictions and not advice.
    Nothing here proposes, sizes, approves, or authorizes any order.
    """
    notes: list[str] = []
    policy = DEFAULT_ELIGIBILITY_POLICY

    sessions = verified.get("history_sessions")
    if include_history and isinstance(sessions, int) and sessions < policy.minimum_history_sessions:
        notes.append(
            f"only {sessions} completed trading session(s) -- below this "
            f"project's usual {policy.minimum_history_sessions}-session floor, "
            "so volatility and trend estimates are not yet reliable"
        )

    last_price = verified.get("last_price")
    if isinstance(last_price, (int, float)) and math.isfinite(float(last_price)) and float(last_price) < policy.minimum_price:
        notes.append(
            f"last close ${float(last_price):,.2f} -- below the usual "
            f"${policy.minimum_price:,.2f} price floor"
        )

    dollar_volume = verified.get("median_dollar_volume")
    if (
        not isinstance(dollar_volume, (int, float))
        or isinstance(dollar_volume, bool)
        or not math.isfinite(float(dollar_volume))
    ):
        notes.append(
            "median daily dollar volume unavailable -- cannot compare this row "
            f"with the usual ${policy.minimum_median_dollar_volume:,.0f} "
            "liquidity floor"
        )
    elif float(dollar_volume) < policy.minimum_median_dollar_volume:
        notes.append(
            f"median daily dollar volume ${float(dollar_volume):,.0f} -- below "
            f"the usual ${policy.minimum_median_dollar_volume:,.0f} liquidity "
            "floor, so it may be hard to trade at a fair price"
        )

    return notes


@dataclasses.dataclass(frozen=True)
class RecommendedTicker:
    ticker: str
    reason_category: Literal["most_active", "recent_ipo", "ai_suggested"]
    detail: str
    fetched_at: str
    # Populated for the most_active lane only; None everywhere else and
    # whenever the provider omitted or corrupted the change value. Consumers
    # must treat None as "unknown", never as a direction. Defaulted so the
    # other two lanes construct unchanged.
    price_direction: PriceDirection | None = None


def fetch_most_active_tickers(count: int = 10) -> list[dict]:
    """Wraps yf.screen("most_actives", count=count) -- confirmed working live
    with the currently-installed yfinance, zero new dependencies. Returns []
    on any failure. Honest framing only: this is TRADING VOLUME and price
    movement, NOT buy-vs-sell order flow -- this yfinance screen does not
    provide classified order flow. Never label this "most bought" anywhere
    in code, comments, or UI copy.

    And this is not a swap-the-screener fix (counter-review MADCR-002, kept
    narrow deliberately): classifying a trade as buyer- or seller-initiated
    needs trade prints matched against the prevailing quote (Lee-Ready and
    similar), i.e. consolidated trade-and-quote data. The market feed this
    project actually has is Alpaca's free IEX tier -- a small share of
    consolidated volume, measured on 2026-08-10 quoting a large-cap at a
    ~6% spread while the consolidated market was penny-wide. Estimating
    direction from that would produce confident-looking noise, which is
    worse than declining to report it."""
    try:
        import yfinance as yf

        result = yf.screen("most_actives", count=count)
        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        return [
            {
                "ticker": q.get("symbol"),
                "name": q.get("shortName", ""),
                "volume": q.get("regularMarketVolume"),
                # Today's price move, used ONLY to split the same volume list
                # into advancing/declining. Still not order flow.
                "change_percent": q.get("regularMarketChangePercent"),
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
    held_tickers: list[str] | None = None,
    store: AssistantStore | None = None,
    *,
    include_most_active: bool = True,
    include_recent_ipos: bool = True,
    include_ai_suggestions: bool = True,
) -> tuple[list[RecommendedTicker], list[str]]:
    """Composes most-actives + IPO calendar + assistant.ai_advisor.suggest_similar_tickers()
    through one verify_tickers() pipeline -- most-actives and IPO-calendar
    results get identical scrutiny to AI suggestions. Returns (recommended,
    dropped_labels) for one combined "could not be verified" caption; a drop
    now means the symbol failed IDENTITY (did not resolve to real market data,
    is not an equity, or is not on a US venue), never that it was judged too
    small, too young, or too cheap -- see SUGGESTION_DISCLOSURE_POLICY.

    `held_tickers` -- the account's ACTUAL current positions -- is used two
    ways: (1) every lane excludes them, so "not held" in the UI is an
    enforced property, not just a label; (2) it's the basis for the
    "ai_suggested" lane ("similar to what you actually hold"). If
    `held_tickers` is empty/None, the ai_suggested lane is skipped entirely
    rather than falling back to an arbitrary fixed basket (independent
    review, 2026-07-28: a prior version silently substituted
    config.UNIVERSE[:5] here, which could make the Briefing appear
    personalized to a user's holdings when it was actually just always
    suggesting tickers similar to a fixed mega-cap-tech basket).

    Each `include_*` flag prevents its provider call entirely, rather than
    fetching candidates and hiding the corresponding rows afterward. This is
    load-bearing for the dedicated UI's explicit source controls. In
    particular, `include_ai_suggestions=False` prevents the paid Claude call
    while leaving whichever deterministic lanes were selected untouched
    (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md sections 3.2 and 4.2)."""
    now = datetime.now(timezone.utc).isoformat()
    held_set = {t.upper() for t in (held_tickers or [])}
    recommended: list[RecommendedTicker] = []
    dropped: list[str] = []

    if include_most_active:
        most_active_candidates = [
            c
            for c in fetch_most_active_tickers()
            if c["ticker"].upper() not in held_set
        ]
        verified, batch_dropped = verify_tickers(
            [c["ticker"] for c in most_active_candidates],
            policy=SUGGESTION_DISCLOSURE_POLICY,
        )
        dropped.extend(batch_dropped)
        # verify_tickers() strips and uppercases every symbol. Join provider
        # metadata on the same canonical key or a harmless case difference
        # makes a valid price change and volume look unreported.
        detail_by_ticker = {
            str(c["ticker"]).strip().upper(): c for c in most_active_candidates
        }
        for v in verified:
            c = detail_by_ticker.get(str(v["ticker"]).strip().upper(), {})
            volume = c.get("volume")
            direction = classify_price_direction(c.get("change_percent"))
            name = v.get("longName") or c.get("name") or v["ticker"]
            parts = [str(name)]
            if volume:
                parts.append(f"trading volume today: {volume:,}")
            if direction is None:
                # Say so rather than implying a flat move; the reader must be
                # able to tell "no direction reported" from "did not move".
                parts.append("price change today: not reported")
            else:
                parts.append(
                    f"price change today: {float(c['change_percent']):+.2f}%"
                )
            parts.extend(_eligibility_disclosure(v))
            recommended.append(
                RecommendedTicker(
                    ticker=v["ticker"],
                    reason_category="most_active",
                    detail=" -- ".join(parts),
                    fetched_at=now,
                    price_direction=direction,
                )
            )

    if include_recent_ipos:
        ipo_candidates = [
            c for c in fetch_recent_ipos() if c["ticker"].upper() not in held_set
        ]
        verified, batch_dropped = verify_tickers(
            [c["ticker"] for c in ipo_candidates],
            policy=SUGGESTION_DISCLOSURE_POLICY,
        )
        dropped.extend(batch_dropped)
        # Same normalization the most-active lane needs (MAD-001), and here
        # the consequence is worse than a cosmetic "not reported": a failed
        # join makes claimed_date empty, and _is_ipo_identity_mismatch()
        # returns False for missing data -- so the reused/renamed-symbol
        # guard below would silently pass a candidate it exists to catch.
        # Note the held-set filter above already upper()s the provider
        # symbol; this join must agree with it.
        ipo_detail_by_ticker = {
            str(c["ticker"]).strip().upper(): c for c in ipo_candidates
        }
        for v in verified:
            c = ipo_detail_by_ticker.get(str(v["ticker"]).strip().upper(), {})
            claimed_date = c.get("date", "")
            if _is_ipo_identity_mismatch(v.get("first_session_date"), claimed_date):
                dropped.append(v["ticker"])
                continue
            name = v.get("longName") or c.get("name") or v["ticker"]
            detail = (
                f"{name} -- IPO date: {claimed_date or 'unknown'} "
                f"({v['history_sessions']} completed trading session(s) -- "
                "volatility/trend estimates are not yet reliable this early)"
            )
            # include_history=False: this lane's own detail string already
            # states the session count and the same unreliability caveat, and
            # a second copy would read as two separate problems.
            notes = _eligibility_disclosure(v, include_history=False)
            if notes:
                detail = " -- ".join([detail, *notes])
            recommended.append(
                RecommendedTicker(
                    ticker=v["ticker"],
                    reason_category="recent_ipo",
                    detail=detail,
                    fetched_at=now,
                )
            )

    if held_set and include_ai_suggestions:
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
            verified, batch_dropped = verify_tickers(
                candidate_tickers, policy=SUGGESTION_DISCLOSURE_POLICY
            )
            dropped.extend(batch_dropped)
            for v in verified:
                recommended.append(
                    RecommendedTicker(
                        ticker=v["ticker"], reason_category="ai_suggested",
                        detail=" -- ".join(
                            [
                                _similarity_detail(
                                    held_list, v["ticker"], reason_by_ticker.get(v["ticker"], "")
                                ),
                                *_eligibility_disclosure(v),
                            ]
                        ),
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
