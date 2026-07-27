"""
Expanded deterministic execution gate — the "never let the LLM bypass
these limits" layer from the assistant design (2026-07). Extends
risk/manager.py (which already does per-position sizing, stop-loss
pricing, and total-exposure capping) with the checks GPT's design review
specifically called for: sector/basket limits, leveraged-ETF limits,
stale-price checks, trading-hours checks, duplicate-order detection, max
slippage, earnings restrictions, and a kill switch.

A TradeIntent is a typed, frozen data structure — not free-form text.
validate_trade_intent() is pure validation: it never submits an order
itself (that's still execution/alpaca_broker.py's job) and never talks
to a network. Every check here is a plain deterministic calculation on
numbers already provided by the caller — no LLM involved.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from config import BASKETS, LEVERAGED_ETF_TICKERS, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from assistant.schemas import PortfolioSnapshot

_EASTERN = ZoneInfo("America/New_York")
_NYSE_CALENDAR = mcal.get_calendar("NYSE")


@dataclasses.dataclass(frozen=True)
class TradeIntent:
    ticker: str
    side: Literal["buy", "sell"]
    shares: int
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = None
    rationale: str = ""


@dataclasses.dataclass
class ValidationResult:
    approved: bool
    violations: list[str]
    # Content-hash of the exact intent this result was computed for. Lets
    # authorize_trade_intent() refuse to authorize any intent whose
    # fingerprint doesn't match -- otherwise nothing stops a caller from
    # pairing an approved ValidationResult from one (e.g. small) intent
    # with a different, never-validated intent and getting a valid
    # authorization for it (Codex review, 2026-07-27).
    validated_intent_fingerprint: str | None = None


@dataclasses.dataclass(frozen=True)
class ExecutionAuthorization:
    """Short-lived proof that a specific typed intent cleared the gate."""

    token: str
    intent_fingerprint: str
    approved_at: str
    expires_at: str


def intent_fingerprint(intent: TradeIntent) -> str:
    payload = json.dumps(
        {
            "ticker": intent.ticker.upper(),
            "side": intent.side,
            "shares": intent.shares,
            "order_type": intent.order_type,
            "limit_price": intent.limit_price,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def authorize_trade_intent(
    intent: TradeIntent,
    validation: ValidationResult,
    ttl_seconds: int = 120,
) -> ExecutionAuthorization:
    if not validation.approved:
        raise ValueError("Cannot authorize a trade intent that failed validation.")
    if validation.validated_intent_fingerprint != intent_fingerprint(intent):
        raise ValueError(
            "This ValidationResult was not produced by validating this exact trade "
            "intent -- refusing to authorize. (A validation result must come from "
            "validate_trade_intent(intent, ...) called with the SAME intent being "
            "authorized here.)"
        )
    now = datetime.now(timezone.utc)
    return ExecutionAuthorization(
        token=secrets.token_urlsafe(32),
        intent_fingerprint=intent_fingerprint(intent),
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
    )


def verify_execution_authorization(
    intent: TradeIntent,
    authorization: ExecutionAuthorization | None,
    now: datetime | None = None,
) -> None:
    if authorization is None:
        raise PermissionError("Broker submission requires a short-lived execution-gate authorization.")
    current = now or datetime.now(timezone.utc)
    expires = datetime.fromisoformat(authorization.expires_at)
    if current > expires:
        raise PermissionError("Execution-gate authorization has expired.")
    if authorization.intent_fingerprint != intent_fingerprint(intent):
        raise PermissionError("Execution-gate authorization does not match this trade intent.")


def validate_trade_intent(
    intent: TradeIntent,
    portfolio: PortfolioSnapshot,
    reference_price: float,
    *,
    price_timestamp: datetime | None = None,
    now: datetime | None = None,
    recent_intents: list[TradeIntent] | None = None,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
    bid_price: float | None = None,
    ask_price: float | None = None,
    max_position_pct: float = MAX_POSITION_PCT,
    max_total_exposure_pct: float = MAX_TOTAL_EXPOSURE_PCT,
    max_basket_pct: float = 40.0,
    max_leveraged_etf_pct: float = 20.0,
    max_stale_price_minutes: float = 15.0,
    max_slippage_pct: float = 1.0,
    max_spread_pct: float = 0.5,
    earnings_blackout_days: int = 2,
    max_order_value: float | None = None,
    min_cash_reserve_pct: float = 0.0,
) -> ValidationResult:
    """
    Validates one TradeIntent against every configured limit. Returns
    ALL violations found (not just the first), so a caller/explanation
    layer can show the complete picture rather than one check at a time.

    `now` is assumed to already be in the exchange's local time (ET) —
    no timezone conversion is performed here; convert before calling.

    Buying vs. selling: exposure/concentration checks (position size,
    total exposure, basket, leveraged-ETF) only apply to BUYS, since a
    sell reduces exposure. Stale-price, trading-hours, duplicate-order,
    spread, slippage, earnings, and the kill switch apply to both sides.

    `bid_price`/`ask_price`: when both are supplied (a market order can
    now be checked, not just a limit order against its limit price), a
    wide bid/ask spread blocks the trade under max_spread_pct -- a market
    order has no protection against a wide/fresh-but-stale-looking quote
    otherwise, since it never compares against anything.
    """
    violations: list[str] = []

    if kill_switch_active:
        return ValidationResult(
            approved=False,
            violations=["Kill switch is active — no trades are permitted."],
            validated_intent_fingerprint=intent_fingerprint(intent),
        )

    if intent.shares <= 0:
        violations.append(f"shares must be positive, got {intent.shares}.")
    if intent.side not in ("buy", "sell"):
        violations.append(f"side must be 'buy' or 'sell', got {intent.side!r}.")
    if intent.order_type not in ("market", "limit", "stop"):
        violations.append(f"Unsupported order type: {intent.order_type!r}.")

    trade_value = intent.shares * reference_price
    if not math.isfinite(reference_price) or reference_price <= 0:
        violations.append(f"reference_price must be a positive, finite number, got {reference_price}.")
    if max_order_value is not None and trade_value > max_order_value:
        violations.append(
            f"Trade value ${trade_value:,.2f} exceeds the ${max_order_value:,.2f} maximum order value."
        )

    if intent.side == "buy":
        existing_position_value = sum(
            p.market_value for p in portfolio.positions if p.ticker.upper() == intent.ticker.upper()
        )
        new_position_pct = (existing_position_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
        if new_position_pct > max_position_pct * 100:
            violations.append(
                f"Position size would be {new_position_pct:.1f}% of equity, exceeding the "
                f"{max_position_pct * 100:.1f}% per-position limit."
            )

        # portfolio.cash alone ignores pending/open orders reserving that
        # same cash (e.g. two proposals approved back-to-back, or an
        # unrelated pending buy on another ticker) -- portfolio.buying_power,
        # when the broker supplies it, already nets those holds out, so it's
        # the tighter and more honest ceiling whenever it's available
        # (Codex review, 2026-07-27: reproduced a $5,000 approval against
        # $1,000 of real buying power sitting behind a $9,000 pending buy).
        available_capital = portfolio.cash
        if portfolio.buying_power is not None:
            available_capital = min(available_capital, portfolio.buying_power)
        if trade_value > available_capital:
            violations.append(f"Trade value ${trade_value:,.2f} exceeds available cash ${available_capital:,.2f}.")
        minimum_cash = portfolio.total_equity * min_cash_reserve_pct
        if available_capital - trade_value < minimum_cash:
            violations.append(
                f"Cash after trade would be ${available_capital - trade_value:,.2f}, below the "
                f"${minimum_cash:,.2f} minimum cash reserve."
            )

        existing_invested = portfolio.total_equity - portfolio.cash
        new_invested_pct = (existing_invested + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
        if new_invested_pct > max_total_exposure_pct * 100:
            violations.append(
                f"Total invested exposure would be {new_invested_pct:.1f}% of equity, exceeding the "
                f"{max_total_exposure_pct * 100:.1f}% total-exposure limit."
            )

        for basket_name, basket_tickers in BASKETS.items():
            if intent.ticker.upper() not in basket_tickers and intent.ticker not in basket_tickers:
                continue
            existing_basket_value = sum(p.market_value for p in portfolio.positions if p.ticker in basket_tickers)
            new_basket_pct = (existing_basket_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
            if new_basket_pct > max_basket_pct:
                violations.append(
                    f"'{basket_name}' exposure would be {new_basket_pct:.1f}% of equity, exceeding the "
                    f"{max_basket_pct:.1f}% basket concentration limit."
                )

        if intent.ticker.upper() in LEVERAGED_ETF_TICKERS:
            existing_leveraged_value = sum(
                p.market_value for p in portfolio.positions if p.is_leveraged_etf
            )
            new_leveraged_pct = (existing_leveraged_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
            if new_leveraged_pct > max_leveraged_etf_pct:
                violations.append(
                    f"Leveraged ETF exposure would be {new_leveraged_pct:.1f}% of equity, exceeding the "
                    f"{max_leveraged_etf_pct:.1f}% leveraged-ETF limit."
                )
    else:
        held_shares = sum(
            p.shares for p in portfolio.positions if p.ticker.upper() == intent.ticker.upper()
        )
        if intent.shares > held_shares:
            violations.append(
                f"Sell quantity {intent.shares} exceeds the {held_shares:g} shares currently held."
            )

    if price_timestamp is not None and now is not None:
        comparable_price_timestamp = price_timestamp
        comparable_now = now
        if comparable_price_timestamp.tzinfo is None and comparable_now.tzinfo is not None:
            comparable_price_timestamp = comparable_price_timestamp.replace(tzinfo=comparable_now.tzinfo)
        elif comparable_price_timestamp.tzinfo is not None and comparable_now.tzinfo is None:
            comparable_price_timestamp = comparable_price_timestamp.replace(tzinfo=None)
        age_minutes = (comparable_now - comparable_price_timestamp).total_seconds() / 60
        if age_minutes > max_stale_price_minutes:
            violations.append(f"Reference price is {age_minutes:.1f} minutes old, exceeding the {max_stale_price_minutes:.1f}-minute staleness limit.")

    if now is not None:
        comparable_now = _as_naive_eastern(now)
        session = _trading_session_window(comparable_now)
        if session is None:
            reason = "a weekend" if comparable_now.weekday() >= 5 else "an exchange holiday"
            violations.append(f"{comparable_now.date()} is {reason} — markets are closed.")
        else:
            session_open, session_close = session
            if not (session_open <= comparable_now < session_close):
                violations.append(
                    f"{comparable_now.time()} on {comparable_now.date()} is outside today's trading "
                    f"session ({session_open.time()}-{session_close.time()} ET, accounting for "
                    "exchange holidays and early closes)."
                )

    if recent_intents:
        for prior in recent_intents:
            if prior.ticker.upper() == intent.ticker.upper() and prior.side == intent.side:
                violations.append(f"Duplicate order detected: a {intent.side} order for {intent.ticker} was already submitted.")
                break

    if intent.order_type == "limit":
        if intent.limit_price is None or not math.isfinite(intent.limit_price) or intent.limit_price <= 0:
            violations.append("Limit orders require a positive, finite limit price.")
        elif reference_price:
            slippage_pct = abs(intent.limit_price - reference_price) / reference_price * 100
            if slippage_pct > max_slippage_pct:
                violations.append(
                    f"Limit price ${intent.limit_price:.2f} is {slippage_pct:.1f}% away from the reference price "
                    f"${reference_price:.2f}, exceeding the {max_slippage_pct:.1f}% max-slippage limit."
                )

    # Bid/ask is opt-in (many callers/tests validate without a live quote
    # at all, e.g. anything upstream of a broker call) -- but once BOTH
    # sides are supplied, a bad quote must fail closed, not be silently
    # skipped. A prior version only ran this check when both sides were
    # already known to be positive, which let a one-sided quote (bid=0 or
    # ask=0, common outside market hours) or a crossed quote (ask < bid,
    # a data anomaly) pass with zero protection -- exactly the situations
    # where a market order is most likely to fill badly.
    if bid_price is not None and ask_price is not None:
        if (
            not math.isfinite(bid_price)
            or not math.isfinite(ask_price)
            or bid_price <= 0
            or ask_price <= 0
        ):
            violations.append(
                f"Bid/ask quote is one-sided or invalid (bid=${bid_price:.2f}, ask=${ask_price:.2f}) -- "
                "refusing to trade without a complete two-sided quote."
            )
        elif ask_price < bid_price:
            violations.append(
                f"Bid/ask quote is crossed (bid=${bid_price:.2f} > ask=${ask_price:.2f}) -- this indicates "
                "a stale or corrupted quote, not a tradeable market."
            )
        else:
            mid = (bid_price + ask_price) / 2
            spread_pct = (ask_price - bid_price) / mid * 100
            if spread_pct > max_spread_pct:
                violations.append(
                    f"Bid/ask spread is {spread_pct:.2f}% (bid ${bid_price:.2f} / ask ${ask_price:.2f}), "
                    f"exceeding the {max_spread_pct:.2f}% max-spread limit -- a market order here could fill "
                    "well away from the reference price."
                )

    # Symmetric window: blocks both the run-up to earnings and the days right
    # after, since a caller could someday pass a negative "days since" value.
    if (
        earnings_days_away is not None
        and abs(earnings_days_away) <= earnings_blackout_days
    ):
        violations.append(
            f"{intent.ticker} has earnings in {earnings_days_away} day(s), within the "
            f"{earnings_blackout_days}-day earnings blackout window."
        )

    return ValidationResult(
        approved=len(violations) == 0,
        violations=violations,
        validated_intent_fingerprint=intent_fingerprint(intent),
    )


def _as_naive_eastern(dt: datetime) -> datetime:
    """Per this module's long-standing contract ("`now` is assumed to
    already be in the exchange's local time (ET) -- no timezone
    conversion is performed here"), the wall-clock hour/minute/date on
    `dt` ARE the Eastern Time to use, regardless of any tzinfo attached --
    tzinfo is stripped, never converted through. (Production callers
    already pass a genuinely Eastern-zoned or naive-ET datetime; this
    preserves that contract for tz-aware values instead of silently
    reinterpreting their wall-clock time in a different zone.)"""
    return dt.replace(tzinfo=None)


def _trading_session_window(naive_eastern_dt: datetime) -> tuple[datetime, datetime] | None:
    """Real NYSE trading-session bounds (naive Eastern Time) for this
    calendar date, honoring exchange holidays and early closes (e.g. the
    day after Thanksgiving, Christmas Eve) via pandas_market_calendars --
    replaces a prior check that only knew "weekday + 9:30-16:00", which
    would incorrectly approve a trade on a market holiday. Returns None
    if the market is closed all day (weekend or full holiday)."""
    date_str = naive_eastern_dt.date().isoformat()
    schedule = _NYSE_CALENDAR.schedule(start_date=date_str, end_date=date_str)
    if schedule.empty:
        return None
    session_open = schedule.iloc[0]["market_open"].tz_convert(_EASTERN).to_pydatetime().replace(tzinfo=None)
    session_close = schedule.iloc[0]["market_close"].tz_convert(_EASTERN).to_pydatetime().replace(tzinfo=None)
    return session_open, session_close
