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

Two policies, and the difference is deliberate. DEFAULT_ELIGIBILITY_POLICY
screens on identity AND size/age/price. SUGGESTION_DISCLOSURE_POLICY screens
on identity only, for surfaces whose job is to show the reader what the market
did rather than to hand them a vouched-for shortlist. Neither policy is an
authorization to trade anything: passing one only means the symbol survived
the checks that policy declares.
"""
from __future__ import annotations

import dataclasses
import math

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

# Compatibility only. AP-8 no longer uses this policy in the recent-IPO lane,
# but it was a public module-level contract before AP-8 and removing the name
# needlessly breaks imports in downstream tools. Keep its reviewed values
# frozen; build_recommended_tickers() uses SUGGESTION_DISCLOSURE_POLICY for all
# three lanes.
RECENT_IPO_ELIGIBILITY_POLICY = SecurityEligibilityPolicy(
    allowed_quote_types=("EQUITY",),
    minimum_history_sessions=3,
    minimum_price=5.0,
    minimum_median_dollar_volume=500_000.0,
    require_company_name=True,
)

# Owner decision, 2026-08-12. The ticker-suggestion surfaces are DISCLOSURE,
# not endorsement: they describe what the market did and hold no execution
# authority whatsoever. The owner asked to see the rows and judge them
# personally after DEFAULT_ELIGIBILITY_POLICY silently removed three of the
# day's ten most-active names -- SPCX (41 sessions < 60, though $1.9T market
# cap and ~$10.7B median daily dollar volume), PLUG ($2.27 < $5.00), and NBIS
# (the longName gap fixed above).
#
# What this policy REMOVES is the size/age/price screen: those were judgments
# about whether a real security is worth showing, and that judgment now
# belongs to the reader. Every removed gate is re-emitted as a visible fact on
# the row (assistant.recommended_stocks._eligibility_disclosure), so the
# information is disclosed rather than discarded -- a row that clears nothing
# must not be indistinguishable from a blue chip.
#
# What this policy KEEPS is identity: the symbol must still resolve to real
# market data, be an EQUITY, and be listed on a US venue. Those are not size
# opinions, they are what stops a hallucinated or mistyped symbol from being
# rendered as a suggestion, and the ai_suggested lane is LLM-authored. Do not
# relax them without a separate explicit owner decision.
#
# Scope is deliberately narrow: build_recommended_tickers() only. The
# Watchlist similar-stocks surface still uses DEFAULT_ELIGIBILITY_POLICY.
SUGGESTION_DISCLOSURE_POLICY = SecurityEligibilityPolicy(
    allowed_quote_types=("EQUITY",),
    minimum_history_sessions=0,
    minimum_price=0.0,
    minimum_median_dollar_volume=0.0,
    # Company identity was never one of the owner-removed size/age/price
    # judgments. The three-field fallback below fixes NBIS without weakening
    # the identity floor for LLM-authored symbols.
    require_company_name=True,
    allowed_exchanges=DEFAULT_ELIGIBILITY_POLICY.allowed_exchanges,
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
    the last close is finite, positive, and at least `policy.minimum_price`;
    when the policy declares a positive liquidity floor, trailing median
    dollar volume (close * volume, a liquidity proxy) must be available and at
    least that floor. A zero liquidity floor means "disclose, do not screen,"
    so an unavailable measurement is preserved as `None`. If
    `policy.require_company_name`, a non-empty text name must be present.

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
        # Counter-review AP8CR-002: review restored the batch-isolation
        # contract for a malformed close, but the first-session date was
        # still derived unguarded further down, so one frame with an
        # unexpected index aborted the whole batch and took every good
        # ticker with it. Same function, same contract, same fix.
        #
        # Drop rather than substitute "": _is_ipo_identity_mismatch() treats a
        # missing first-session date as "no mismatch", so an empty string
        # would silently disarm the reused/renamed-symbol guard that exists to
        # catch exactly this kind of malformed identity.
        try:
            first_session_date = str(hist.index[0].date())
        except (AttributeError, IndexError, TypeError, ValueError):
            dropped.append(ticker)
            continue

        try:
            last_price = float(hist["close"].iloc[-1])
        except (KeyError, IndexError, OverflowError, TypeError, ValueError):
            dropped.append(ticker)
            continue
        # A zero or non-finite close is malformed market data, not a low-price
        # security. AP-8 removed the owner's $5 display screen; it did not turn
        # unusable data into verified identity.
        if not math.isfinite(last_price) or last_price <= 0:
            dropped.append(ticker)
            continue

        median_dollar_volume: float | None = None
        if "volume" in hist.columns:
            try:
                measured_volume = float((hist["close"] * hist["volume"]).median())
            except (OverflowError, TypeError, ValueError):
                measured_volume = float("nan")
            if math.isfinite(measured_volume) and measured_volume >= 0:
                median_dollar_volume = measured_volume
        quote_type = info.get("quoteType", "")
        # yfinance does not populate longName for every real listing -- NBIS
        # (Nebius Group N.V., Nasdaq NMS, ~$3.6B median daily dollar volume)
        # returns longName=None while carrying shortName='Nebius Group N.V.'
        # and displayName='Nebius', persistently across repeated fetches.
        # require_company_name exists to reject a symbol with NO identity, so
        # reading only one of the three name fields turned a provider metadata
        # gap into a claim about the security. Checked 2026-08-12 against live
        # yfinance after the owner noticed real most-active names missing.
        company_name = next(
            (
                value.strip()
                for value in (
                    info.get("longName"),
                    info.get("shortName"),
                    info.get("displayName"),
                )
                if isinstance(value, str) and value.strip()
            ),
            "",
        )

        exchange = info.get("exchange", "")
        eligible = (
            quote_type in policy.allowed_quote_types
            and history_sessions >= policy.minimum_history_sessions
            and last_price >= policy.minimum_price
            and (
                policy.minimum_median_dollar_volume <= 0
                or (
                    median_dollar_volume is not None
                    and median_dollar_volume >= policy.minimum_median_dollar_volume
                )
            )
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
                "first_session_date": first_session_date,
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
