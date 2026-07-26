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
from datetime import datetime
from typing import Literal

from config import BASKETS, LEVERAGED_ETF_TICKERS, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from assistant.schemas import PortfolioSnapshot


@dataclasses.dataclass(frozen=True)
class TradeIntent:
    ticker: str
    side: Literal["buy", "sell"]
    shares: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    rationale: str = ""


@dataclasses.dataclass
class ValidationResult:
    approved: bool
    violations: list[str]


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
    max_position_pct: float = MAX_POSITION_PCT,
    max_total_exposure_pct: float = MAX_TOTAL_EXPOSURE_PCT,
    max_basket_pct: float = 40.0,
    max_leveraged_etf_pct: float = 20.0,
    max_stale_price_minutes: float = 15.0,
    max_slippage_pct: float = 1.0,
    earnings_blackout_days: int = 2,
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
    slippage, earnings, and the kill switch apply to both sides.
    """
    violations: list[str] = []

    if kill_switch_active:
        return ValidationResult(approved=False, violations=["Kill switch is active — no trades are permitted."])

    if intent.shares <= 0:
        violations.append(f"shares must be positive, got {intent.shares}.")

    trade_value = intent.shares * reference_price

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

        if trade_value > portfolio.cash:
            violations.append(f"Trade value ${trade_value:,.2f} exceeds available cash ${portfolio.cash:,.2f}.")

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

    if price_timestamp is not None and now is not None:
        age_minutes = (now - price_timestamp).total_seconds() / 60
        if age_minutes > max_stale_price_minutes:
            violations.append(f"Reference price is {age_minutes:.1f} minutes old, exceeding the {max_stale_price_minutes:.1f}-minute staleness limit.")

    if now is not None:
        if now.weekday() >= 5:
            violations.append(f"{now.date()} is a weekend — markets are closed.")
        elif not (_time_ge(now, 9, 30) and _time_lt(now, 16, 0)):
            violations.append(f"{now.time()} is outside standard market hours (9:30-16:00 ET).")

    if recent_intents:
        for prior in recent_intents:
            if prior.ticker.upper() == intent.ticker.upper() and prior.side == intent.side:
                violations.append(f"Duplicate order detected: a {intent.side} order for {intent.ticker} was already submitted.")
                break

    if intent.order_type == "limit" and intent.limit_price is not None and reference_price:
        slippage_pct = abs(intent.limit_price - reference_price) / reference_price * 100
        if slippage_pct > max_slippage_pct:
            violations.append(
                f"Limit price ${intent.limit_price:.2f} is {slippage_pct:.1f}% away from the reference price "
                f"${reference_price:.2f}, exceeding the {max_slippage_pct:.1f}% max-slippage limit."
            )

    if earnings_days_away is not None and earnings_days_away <= earnings_blackout_days:
        violations.append(
            f"{intent.ticker} has earnings in {earnings_days_away} day(s), within the "
            f"{earnings_blackout_days}-day earnings blackout window."
        )

    return ValidationResult(approved=len(violations) == 0, violations=violations)


def _time_ge(dt: datetime, hour: int, minute: int) -> bool:
    return (dt.hour, dt.minute) >= (hour, minute)


def _time_lt(dt: datetime, hour: int, minute: int) -> bool:
    return (dt.hour, dt.minute) < (hour, minute)
