"""
Shared ticker-verification discipline (.claude/skills/real-data-check/SKILL.md):
any AI-suggested or screener-sourced ticker that is NOT already a known,
tracked member of config.UNIVERSE must resolve via fetch_historical and
pass a yfinance .info sanity check before being shown to the user. Used
by assistant/ai_advisor.py (free-form AI ticker suggestions) and
assistant/recommended_stocks.py (market-wide screener/IPO-calendar
results) so both features share one verification contract instead of two
independently-drifting implementations.

Deliberately conservative: a hallucinated, delisted, or mistyped ticker
either won't resolve via fetch_historical at all, or will resolve but
carry no real identifying info -- either case is dropped rather than
shown, per this project's standing "never trust a new ticker without
checking it" discipline (config.DEFENSIVE_CARRY_TICKERS is the existing
precedent for holding a ticker list that isn't itself an authorization).
"""
from __future__ import annotations

import dataclasses

from data.market_data import fetch_historical

_SANITY_INFO_FIELDS = ("longName", "quoteType", "exchange")


@dataclasses.dataclass(frozen=True)
class SecurityEligibilityPolicy:
    """What counts as a legitimate, tradeable-enough candidate to show a
    user -- deliberately stricter than "the symbol resolves to something"
    (independent review: the prior verify_tickers() accepted a candidate if
    even ONE weak info field was present, which let an ETF, an OTC/foreign
    listing, a warrant/preferred share, or a barely-liquid or barely-listed
    ticker all pass under the "recommended stock" framing)."""

    allowed_quote_types: tuple[str, ...] = ("EQUITY",)
    minimum_history_sessions: int = 60  # ~3 trading months -- long enough that a handful of stale/synthetic bars can't pass
    minimum_price: float = 5.0
    minimum_median_dollar_volume: float = 1_000_000.0
    require_company_name: bool = True
    # yfinance exchange codes for the major US listing venues -- NMS/NGM/NCM
    # (Nasdaq Global Select/Global/Capital Market), NYQ (NYSE), ASE (NYSE
    # American), PCX (NYSE Arca), BATS/BTS (Cboe BZX). None = no exchange
    # restriction. Independent review: prompts and UI copy already say "US
    # tickers"/"US stocks", but nothing enforced that -- a sufficiently
    # liquid foreign or OTC listing could otherwise pass every other check.
    allowed_exchanges: tuple[str, ...] | None = ("NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BATS", "BTS")


DEFAULT_ELIGIBILITY_POLICY = SecurityEligibilityPolicy()

# A genuine IPO from the last _IPO_LOOKBACK_DAYS (see recommended_stocks.py's
# fetch_recent_ipos) calendar days has at most ~20-22 TRADING sessions --
# DEFAULT_ELIGIBILITY_POLICY's minimum_history_sessions=60 would reject
# every real recent IPO by construction, not just conservatively (independent
# review: "this does not merely make the filter conservative, it makes
# every genuine result in the lane ineligible by definition"). This lane
# gets its own, deliberately looser policy -- still real checks (equity
# type, a real company name, SOME minimum liquidity/price), just not ones
# that assume months of trading history that cannot exist yet.
RECENT_IPO_ELIGIBILITY_POLICY = SecurityEligibilityPolicy(
    allowed_quote_types=("EQUITY",),
    minimum_history_sessions=3,
    minimum_price=5.0,
    minimum_median_dollar_volume=500_000.0,
    require_company_name=True,
)

_FETCH_LOOKBACK_DAYS = 90  # a MAXIMUM request, not a requirement -- a ticker with less real
# history (e.g. a genuine recent IPO) just returns fewer rows, which the eligibility policy's
# own minimum_history_sessions then judges; safe to request uniformly regardless of lane/policy.


def verify_tickers(
    candidates: list[str], max_checks: int = 10, policy: SecurityEligibilityPolicy = DEFAULT_ELIGIBILITY_POLICY
) -> tuple[list[dict], list[str]]:
    """
    Returns (verified, dropped).

    `verified` is a list of {"ticker", "longName", "sector", "quoteType",
    "exchange", "history_sessions", "last_price", "median_dollar_volume",
    "first_session_date"} dicts for candidates that resolve via fetch_historical AND pass EVERY
    check in `policy`: quote type is in `policy.allowed_quote_types` (an ETF,
    warrant, preferred share, or fund is REJECTED under the default policy,
    which only allows "EQUITY" -- this is a "recommended STOCKS" feature),
    at least `policy.minimum_history_sessions` real trading sessions exist,
    the last close is at least `policy.minimum_price`, the trailing median
    dollar volume (close * volume, a liquidity proxy) is at least
    `policy.minimum_median_dollar_volume`, and (if `policy.require_company_name`)
    a real company name is present.

    `dropped` is every candidate that failed fetch_historical, failed any
    eligibility check above, or was beyond `max_checks`. One bad ticker
    never aborts the batch -- each candidate is checked independently.

    Capped at `max_checks` candidates (a cost/latency bound: this runs
    synchronously inside a UI action, and .info has no batched form --
    it's one network call per ticker).
    """
    truncated = candidates[:max_checks]
    if not truncated:
        return [], list(candidates)

    normalized = [t.strip().upper() for t in truncated if t and t.strip()]
    verified: list[dict] = []
    dropped: list[str] = []

    try:
        history = fetch_historical(normalized, lookback_days=_FETCH_LOOKBACK_DAYS)
    except Exception:
        history = {}

    for ticker in normalized:
        hist = history.get(ticker)
        if hist is None or hist.empty:
            dropped.append(ticker)
            continue

        info = _safe_ticker_info(ticker)
        if not info or not any(info.get(field) for field in _SANITY_INFO_FIELDS):
            dropped.append(ticker)
            continue

        history_sessions = len(hist)
        last_price = float(hist["close"].iloc[-1])
        median_dollar_volume = (
            float((hist["close"] * hist["volume"]).median()) if "volume" in hist.columns else 0.0
        )
        quote_type = info.get("quoteType", "")
        company_name = info.get("longName", "")

        exchange = info.get("exchange", "")
        eligible = (
            quote_type in policy.allowed_quote_types
            and history_sessions >= policy.minimum_history_sessions
            and last_price >= policy.minimum_price
            and median_dollar_volume >= policy.minimum_median_dollar_volume
            and (not policy.require_company_name or bool(company_name))
            and (policy.allowed_exchanges is None or exchange in policy.allowed_exchanges)
        )
        if not eligible:
            dropped.append(ticker)
            continue

        verified.append(
            {
                "ticker": ticker,
                "longName": company_name,
                "sector": info.get("sector", ""),
                "quoteType": quote_type,
                "exchange": exchange,
                "history_sessions": history_sessions,
                "last_price": last_price,
                "median_dollar_volume": median_dollar_volume,
                "first_session_date": str(hist.index[0].date()),
            }
        )

    dropped.extend(t.strip().upper() for t in candidates[max_checks:] if t and t.strip())
    return verified, dropped


def _safe_ticker_info(ticker: str) -> dict:
    try:
        import yfinance as yf  # imported lazily, matching data/market_data.py's pattern

        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def partition_by_universe(candidates: list[dict], universe: list[str]) -> tuple[list[dict], list[dict]]:
    """
    Deterministic (non-LLM-judged) split of `candidates` (each a
    {"ticker", "reason"}-shaped dict) into (from_universe, wildcard) by a
    plain set-membership check against `universe`. Never trusts an LLM's
    own claim about universe membership -- the "AI never computes/
    classifies, only narrates" rule applies here too.
    """
    universe_set = {t.upper() for t in universe}
    from_universe = [c for c in candidates if c.get("ticker", "").upper() in universe_set]
    wildcard = [c for c in candidates if c.get("ticker", "").upper() not in universe_set]
    return from_universe, wildcard
