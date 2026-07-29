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

from data.market_data import fetch_historical

_SANITY_INFO_FIELDS = ("longName", "quoteType", "exchange")


def verify_tickers(candidates: list[str], max_checks: int = 10) -> tuple[list[dict], list[str]]:
    """
    Returns (verified, dropped).

    `verified` is a list of {"ticker", "longName", "sector", "quoteType",
    "exchange"} dicts for candidates that BOTH resolve via
    fetch_historical(lookback_days=10) AND pass a per-ticker
    yf.Ticker(t).info sanity check (at least one of longName/quoteType/
    exchange present and truthy).

    `dropped` is every candidate that failed either check. One bad ticker
    never aborts the batch -- each candidate is checked independently.

    Capped at `max_checks` candidates (a cost/latency bound: this runs
    synchronously inside a UI action, and .info has no batched form --
    it's one network call per ticker). Candidates beyond the cap are
    treated as dropped too, since they were never actually checked.
    """
    truncated = candidates[:max_checks]
    if not truncated:
        return [], list(candidates)

    normalized = [t.strip().upper() for t in truncated if t and t.strip()]
    verified: list[dict] = []
    dropped: list[str] = []

    try:
        history = fetch_historical(normalized, lookback_days=10)
    except Exception:
        history = {}

    for ticker in normalized:
        if ticker not in history or history[ticker].empty:
            dropped.append(ticker)
            continue
        info = _safe_ticker_info(ticker)
        if not info or not any(info.get(field) for field in _SANITY_INFO_FIELDS):
            dropped.append(ticker)
            continue
        verified.append(
            {
                "ticker": ticker,
                "longName": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "quoteType": info.get("quoteType", ""),
                "exchange": info.get("exchange", ""),
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
