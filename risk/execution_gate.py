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
import enum
import hashlib
import hmac
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

# A quote timestamp further in the future than this is treated as
# impossible/corrupted data, not merely "very fresh" -- small enough to
# tolerate ordinary clock skew between this process and the broker/data
# provider, not so large that a genuinely bad timestamp (e.g. a bug that
# adds hours instead of subtracting) would slip through as "fresh."
_FUTURE_TIMESTAMP_TOLERANCE_MINUTES = 1.0

# Process-local secret, generated once at import time. intent_fingerprint()
# below is a PLAIN hash of public TradeIntent fields -- any code that can
# import TradeIntent can compute the same hash, so it was never actually a
# proof that validate_trade_intent()/authorize_trade_intent() ran (Codex
# review, 2026-07-27: hand-constructing a ValidationResult or
# ExecutionAuthorization with a correctly-computed fingerprint passed
# verification). _sign() below mixes in this secret via HMAC, so a proof can
# only be produced by code that already holds _GATE_SECRET -- i.e. this
# module itself -- not by anything that merely knows the intent's fields.
_GATE_SECRET = secrets.token_bytes(32)


def _sign(payload: str) -> str:
    return hmac.new(_GATE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclasses.dataclass(frozen=True)
class TradeIntent:
    ticker: str
    side: Literal["buy", "sell"]
    shares: int
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = None
    rationale: str = ""


class ViolationCode(str, enum.Enum):
    """Stable, machine-checkable identity for each violation type -- the
    security-relevant data authorize_overridden_trade_intent() below
    actually trusts. Human-readable message TEXT (ValidationResult.
    violations) is display-only and never used to decide override
    eligibility (2026-07-28, GPT review: a prior version derived
    eligibility from a separately-stored, unsigned `overridable_violations`
    list of plain message strings -- dataclasses.replace() could swap a
    hard rejection's content for override-eligible-looking text while
    keeping a validly-signed proof, since the proof never covered that
    field at all)."""

    KILL_SWITCH = "kill_switch"
    INVALID_SHARES = "invalid_shares"
    INVALID_SIDE = "invalid_side"
    INVALID_ORDER_TYPE = "invalid_order_type"
    INVALID_REFERENCE_PRICE = "invalid_reference_price"
    MAX_ORDER_VALUE = "max_order_value"
    INVALID_PENDING_VALUE = "invalid_pending_value"
    MAX_POSITION_PCT = "max_position_pct"
    INSUFFICIENT_CASH = "insufficient_cash"
    MIN_CASH_RESERVE = "min_cash_reserve"
    MAX_TOTAL_EXPOSURE_PCT = "max_total_exposure_pct"
    MAX_BASKET_PCT = "max_basket_pct"
    MAX_LEVERAGED_ETF_PCT = "max_leveraged_etf_pct"
    SELL_EXCEEDS_HELD = "sell_exceeds_held"
    STALE_PRICE = "stale_price"
    MARKET_CLOSED = "market_closed"
    OUTSIDE_TRADING_SESSION = "outside_trading_session"
    DUPLICATE_ORDER = "duplicate_order"
    INVALID_LIMIT_PRICE = "invalid_limit_price"
    MAX_SLIPPAGE = "max_slippage"
    INVALID_QUOTE = "invalid_quote"
    MAX_SPREAD = "max_spread"
    EARNINGS_BLACKOUT = "earnings_blackout"
    INVALID_PORTFOLIO_CASH = "invalid_portfolio_cash"
    INVALID_PORTFOLIO_EQUITY = "invalid_portfolio_equity"
    INVALID_BUYING_POWER = "invalid_buying_power"
    INVALID_POSITION_DATA = "invalid_position_data"
    FUTURE_PRICE_TIMESTAMP = "future_price_timestamp"


# The ONLY violation codes authorize_overridden_trade_intent() will ever
# let a human knowingly proceed past: deliberate risk-preference or
# business-calendar calls, not data-integrity/safety issues. This is a
# fixed module-level constant, not per-result instance data -- there is
# nothing here for a caller to mutate or replace (2026-07-28, GPT review).
OVERRIDABLE_VIOLATION_CODES: frozenset[ViolationCode] = frozenset(
    {
        ViolationCode.MAX_POSITION_PCT,
        ViolationCode.MAX_TOTAL_EXPOSURE_PCT,
        ViolationCode.MAX_BASKET_PCT,
        ViolationCode.MAX_LEVERAGED_ETF_PCT,
        ViolationCode.EARNINGS_BLACKOUT,
    }
)


@dataclasses.dataclass(frozen=True)
class ValidationResult:
    approved: bool
    # Human-readable messages -- display only. Same order and length as
    # `violation_codes` below; NOT itself security-relevant (see
    # ViolationCode's docstring).
    violations: tuple[str, ...]
    # Stable codes, one per entry in `violations`, in the same order --
    # THIS is what validation_proof signs and what override eligibility is
    # computed from. Tuple (immutable), unlike the prior list-based
    # design.
    violation_codes: tuple[str, ...] = ()
    # HMAC (keyed by this module's process-local secret) over the exact
    # intent this result was computed for, the approved/rejected outcome,
    # AND the full (canonically ordered) violation_codes. Only
    # validate_trade_intent() can produce a proof that verifies -- unlike
    # a plain content hash, this can't be recomputed by code that merely
    # knows the intent's public fields, so a hand-constructed
    # ValidationResult (with an arbitrary or even correctly-hashed
    # fingerprint) is rejected by authorize_trade_intent() below (Codex
    # review, 2026-07-27). Signing `approved` too (not just intent
    # identity) matters because this dataclass would otherwise be mutable:
    # a REJECTED result still got a validly-signed proof for its intent,
    # so flipping `.approved` to True and reusing that proof would have
    # passed authorize_trade_intent() -- frozen=True blocks the plain
    # in-place mutation, and signing the outcome blocks reusing the proof
    # on any *other* ValidationResult (e.g. via dataclasses.replace()) too
    # (GPT review, 2026-07-27). Signing violation_codes too (2026-07-28,
    # GPT review) closes the remaining hole: without it, a genuine hard
    # rejection's violation content could be swapped for override-eligible
    # -looking codes via dataclasses.replace() while the proof (which
    # never covered that field) kept verifying.
    validation_proof: str | None = None

    @property
    def overridable(self) -> bool:
        """True iff there's at least one violation and EVERY one of them
        is override-eligible. Always computed fresh from violation_codes
        (which validation_proof cryptographically binds) against the
        fixed OVERRIDABLE_VIOLATION_CODES constant -- never stored as
        separate, independently mutable instance data, so there is
        nothing here to forge."""
        return bool(self.violation_codes) and all(
            code in OVERRIDABLE_VIOLATION_CODES for code in self.violation_codes
        )

    @property
    def blocking_violations(self) -> tuple[str, ...]:
        """Human-readable messages for violations that are NOT
        override-eligible. Non-empty here means an override can never
        apply, regardless of what else is present alongside them."""
        return tuple(
            message
            for message, code in zip(self.violations, self.violation_codes)
            if code not in OVERRIDABLE_VIOLATION_CODES
        )


@dataclasses.dataclass(frozen=True)
class ExecutionAuthorization:
    """Short-lived proof that a specific typed intent cleared the gate."""

    token: str
    intent_fingerprint: str  # informational/for logging -- NOT the security check, see `proof`
    proof: str  # HMAC-signed; only authorize_trade_intent() can produce a valid one
    approved_at: str
    expires_at: str


def intent_fingerprint(intent: TradeIntent) -> str:
    """Plain content hash -- useful for logging/display/dedup, but NOT a
    secret (any code with a TradeIntent can compute this itself). Do not
    use this alone as a security check; see _sign()/_validation_proof()/
    _authorization_proof()."""
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


def _validation_proof(
    intent: TradeIntent, approved: bool, violation_codes: tuple[str, ...] = ()
) -> str:
    # `approved` is part of the signed payload -- NOT just intent identity
    # -- so a REJECTED validation's proof can never be reused as if it were
    # an approval. ValidationResult is a plain (mutable) dataclass;
    # signing intent identity alone meant a caller could take a rejected
    # result (which still got a validly-signed proof for its intent),
    # flip `.approved = True`, and authorize_trade_intent() would accept
    # it -- the proof didn't actually encode the outcome (GPT review,
    # 2026-07-27).
    #
    # `violation_codes` is ALSO part of the signed payload (2026-07-28,
    # GPT review): without this, a genuine rejected result's violation
    # content could be swapped via dataclasses.replace() for
    # override-eligible-looking codes while keeping the same (still
    # "valid") proof, since the proof never covered that field at all --
    # authorize_overridden_trade_intent() would then wrongly authorize a
    # hard rejection (insufficient cash, stale price, a duplicate order,
    # ...) as if every violation were a deliberate risk-preference call.
    # Sorted before joining so that two otherwise-identical code sets in a
    # different order (not semantically meaningful) still produce the
    # same signature.
    canonical_codes = ":".join(sorted(violation_codes))
    return _sign(f"validated:{approved}:{intent_fingerprint(intent)}:{canonical_codes}")


def _authorization_proof(intent: TradeIntent, expires_at: str) -> str:
    # `expires_at` is part of the signed payload -- NOT just intent
    # identity -- so the expiry itself can't be extended after the fact.
    # ExecutionAuthorization is frozen, but dataclasses.replace() (or any
    # code building a new instance) can copy an existing, validly-signed
    # `proof` onto an object with a LATER `expires_at`; since the prior
    # version's proof didn't cover expires_at, that forged object would
    # still verify, defeating "short-lived" entirely (GPT review,
    # 2026-07-27).
    return _sign(f"authorized:{intent_fingerprint(intent)}:{expires_at}")


def authorize_trade_intent(
    intent: TradeIntent,
    validation: ValidationResult,
    ttl_seconds: int = 120,
) -> ExecutionAuthorization:
    if not validation.approved:
        raise ValueError("Cannot authorize a trade intent that failed validation.")
    if validation.validation_proof is None or not hmac.compare_digest(
        validation.validation_proof, _validation_proof(intent, True, validation.violation_codes)
    ):
        raise ValueError(
            "This ValidationResult was not produced by validate_trade_intent(intent, ...) "
            "called with this exact trade intent -- refusing to authorize. A hand-constructed "
            "or mismatched ValidationResult cannot be signed correctly."
        )
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    return ExecutionAuthorization(
        token=secrets.token_urlsafe(32),
        intent_fingerprint=intent_fingerprint(intent),
        proof=_authorization_proof(intent, expires_at),
        approved_at=now.isoformat(),
        expires_at=expires_at,
    )


def authorize_overridden_trade_intent(
    intent: TradeIntent,
    validation: ValidationResult,
    ttl_seconds: int = 120,
) -> ExecutionAuthorization:
    """
    A second, narrowly-scoped path to a real ExecutionAuthorization for a
    trade validate_trade_intent() REJECTED, used only when every single
    violation is a deliberate risk-preference/business-calendar call
    (currently: per-position/total-exposure/basket/leveraged-ETF
    concentration caps, and the earnings blackout window) that a human
    can knowingly accept -- never for a violation reflecting unreliable
    data or a hard safety invariant (stale price, closed market, a bad
    bid/ask quote, a duplicate order, the kill switch, insufficient cash,
    an invalid intent). Those always require authorize_trade_intent()'s
    ordinary approved=True path, and can NEVER be overridden here even if
    they co-occur with an overridable violation (2026-07 feature,
    requested to let a user consciously accept e.g. a known earnings-date
    block when the broker itself would still take the order).

    Independently re-verifies eligibility inside this module rather than
    trusting the caller's claim: the same HMAC-signed validation_proof
    mechanism authorize_trade_intent() uses to prove a ValidationResult
    wasn't hand-constructed is checked here too (against approved=False
    AND this exact violation_codes tuple, since that's what a genuine
    rejection looks like -- see _validation_proof()'s docstring on why
    violation_codes had to become part of the signed payload, 2026-07-28
    GPT review), and `.overridable` (computed fresh from those
    proof-bound codes against the fixed OVERRIDABLE_VIOLATION_CODES
    constant) must be True -- if even one violation code isn't
    override-eligible, this raises exactly like a normal rejection would.
    """
    if validation.approved:
        raise ValueError("Use authorize_trade_intent() for an already-approved validation.")
    if validation.validation_proof is None or not hmac.compare_digest(
        validation.validation_proof, _validation_proof(intent, False, validation.violation_codes)
    ):
        raise ValueError(
            "This ValidationResult was not produced by validate_trade_intent(intent, ...) called with "
            "this exact trade intent and violation set -- refusing to authorize an override."
        )
    if not validation.overridable:
        raise ValueError(
            "At least one violation is not override-eligible (only concentration-cap and "
            "earnings-blackout violations can be overridden) -- refusing to authorize."
        )
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    return ExecutionAuthorization(
        token=secrets.token_urlsafe(32),
        intent_fingerprint=intent_fingerprint(intent),
        proof=_authorization_proof(intent, expires_at),
        approved_at=now.isoformat(),
        expires_at=expires_at,
    )


def verify_execution_authorization(
    intent: TradeIntent,
    authorization: ExecutionAuthorization | None,
    now: datetime | None = None,
) -> None:
    if authorization is None:
        raise PermissionError("Broker submission requires a short-lived execution-gate authorization.")
    if not hmac.compare_digest(authorization.proof, _authorization_proof(intent, authorization.expires_at)):
        raise PermissionError("Execution-gate authorization does not match this trade intent.")
    current = now or datetime.now(timezone.utc)
    expires = datetime.fromisoformat(authorization.expires_at)
    if current > expires:
        raise PermissionError("Execution-gate authorization has expired.")


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
    pending_buy_value_by_ticker: dict[str, float] | None = None,
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

    `pending_buy_value_by_ticker`: estimated dollar value of currently
    pending (not-yet-filled) BUY orders, keyed by ticker. portfolio.cash/
    buying_power already covers whether there's enough MONEY for this
    trade, but the per-position, total-exposure, basket, and leveraged-ETF
    checks below only look at `portfolio.positions` -- a pending buy that
    hasn't filled yet doesn't show up there either, so without this a
    pending buy on this (or a same-basket/leveraged) ticker is invisible
    to every exposure/concentration cap, not just the cash check (Codex
    review, 2026-07-27: reproduced a $4,000 pending buy + a new $5,000 buy
    both passing a 50% exposure cap on a $10,000 account, even though both
    fills together create 90% exposure).
    """
    violations: list[str] = []
    violation_codes: list[str] = []

    def _violate(code: ViolationCode, message: str) -> None:
        violations.append(message)
        violation_codes.append(code.value)

    if kill_switch_active:
        codes = (ViolationCode.KILL_SWITCH.value,)
        return ValidationResult(
            approved=False,
            violations=("Kill switch is active — no trades are permitted.",),
            violation_codes=codes,
            validation_proof=_validation_proof(intent, False, codes),
        )

    # Portfolio numeric integrity -- checked BEFORE any of the
    # exposure/cash arithmetic below touches these fields (GPT review,
    # 2026-07-29). Policy values and reference_price were already
    # validated for finiteness elsewhere, but a corrupted broker/manual
    # PortfolioSnapshot (NaN or infinity in cash, equity, buying power, or
    # any position's numbers) was NOT -- and NaN silently defeats every
    # comparison it touches (`NaN > limit` is always False in Python), so
    # a cash check, an exposure cap, or a basket/leveraged-ETF sum could
    # all silently fail OPEN instead of blocking. These are always hard,
    # non-overridable violations -- never a risk-preference call.
    if not math.isfinite(portfolio.cash):
        _violate(ViolationCode.INVALID_PORTFOLIO_CASH, f"portfolio.cash must be finite, got {portfolio.cash}.")
    elif portfolio.cash < 0:
        _violate(
            ViolationCode.INVALID_PORTFOLIO_CASH,
            f"portfolio.cash must be non-negative (this project does not model margin/short cash "
            f"balances), got {portfolio.cash}.",
        )
    if not math.isfinite(portfolio.total_equity):
        _violate(
            ViolationCode.INVALID_PORTFOLIO_EQUITY,
            f"portfolio.total_equity must be finite, got {portfolio.total_equity}.",
        )
    elif intent.side == "buy" and portfolio.total_equity <= 0:
        _violate(
            ViolationCode.INVALID_PORTFOLIO_EQUITY,
            f"portfolio.total_equity must be positive to size a buy against it, got {portfolio.total_equity}.",
        )
    if portfolio.buying_power is not None and not math.isfinite(portfolio.buying_power):
        _violate(
            ViolationCode.INVALID_BUYING_POWER,
            f"portfolio.buying_power must be finite when present, got {portfolio.buying_power}.",
        )
    for position in portfolio.positions:
        bad_fields = [
            (name, value)
            for name, value in (
                ("shares", position.shares),
                ("entry_price", position.entry_price),
                ("current_price", position.current_price),
                ("market_value", position.market_value),
            )
            if not math.isfinite(value)
        ]
        if bad_fields:
            detail = ", ".join(f"{name}={value}" for name, value in bad_fields)
            _violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has non-finite data ({detail}) -- refusing to compute "
                "exposure with corrupted position data.",
            )
            continue
        if position.shares < 0:
            _violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has negative shares ({position.shares}) -- this project "
                "does not model short positions.",
            )
        if position.market_value < 0:
            _violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has negative market_value ({position.market_value}).",
            )
        if position.current_price <= 0 or position.entry_price <= 0:
            _violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has a non-positive price (entry_price="
                f"{position.entry_price}, current_price={position.current_price}).",
            )

    if intent.shares <= 0:
        _violate(ViolationCode.INVALID_SHARES, f"shares must be positive, got {intent.shares}.")
    if intent.side not in ("buy", "sell"):
        _violate(ViolationCode.INVALID_SIDE, f"side must be 'buy' or 'sell', got {intent.side!r}.")
    if intent.order_type not in ("market", "limit", "stop"):
        _violate(ViolationCode.INVALID_ORDER_TYPE, f"Unsupported order type: {intent.order_type!r}.")

    trade_value = intent.shares * reference_price
    if not math.isfinite(reference_price) or reference_price <= 0:
        _violate(
            ViolationCode.INVALID_REFERENCE_PRICE,
            f"reference_price must be a positive, finite number, got {reference_price}.",
        )
    if max_order_value is not None and trade_value > max_order_value:
        _violate(
            ViolationCode.MAX_ORDER_VALUE,
            f"Trade value ${trade_value:,.2f} exceeds the ${max_order_value:,.2f} maximum order value.",
        )

    if intent.side == "buy":
        # A NaN/negative pending value must fail closed, not silently
        # corrupt the arithmetic below: NaN propagates through every sum
        # it touches, and `x > cap` for a NaN `x` is always False in
        # Python -- exactly the "silently disables the check" failure
        # mode already fixed elsewhere in this module for reference_price/
        # limit_price/bid/ask, but missed here when
        # pending_buy_value_by_ticker was added (GPT review, 2026-07-27).
        pending_by_ticker: dict[str, float] = {}
        for raw_ticker, raw_value in (pending_buy_value_by_ticker or {}).items():
            if not math.isfinite(raw_value) or raw_value < 0:
                _violate(
                    ViolationCode.INVALID_PENDING_VALUE,
                    f"pending_buy_value_by_ticker[{raw_ticker!r}] must be a non-negative, finite "
                    f"number, got {raw_value} -- refusing to compute exposure with a corrupted "
                    "pending-order value.",
                )
                continue
            key = raw_ticker.upper()
            pending_by_ticker[key] = pending_by_ticker.get(key, 0.0) + raw_value
        total_pending_buy_value = sum(pending_by_ticker.values())

        existing_position_value = sum(
            p.market_value for p in portfolio.positions if p.ticker.upper() == intent.ticker.upper()
        ) + pending_by_ticker.get(intent.ticker.upper(), 0.0)
        new_position_pct = (existing_position_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
        if new_position_pct > max_position_pct * 100:
            _violate(
                ViolationCode.MAX_POSITION_PCT,
                f"Position size would be {new_position_pct:.1f}% of equity, exceeding the "
                f"{max_position_pct * 100:.1f}% per-position limit.",
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
            _violate(
                ViolationCode.INSUFFICIENT_CASH,
                f"Trade value ${trade_value:,.2f} exceeds available cash ${available_capital:,.2f}.",
            )
        minimum_cash = portfolio.total_equity * min_cash_reserve_pct
        if available_capital - trade_value < minimum_cash:
            _violate(
                ViolationCode.MIN_CASH_RESERVE,
                f"Cash after trade would be ${available_capital - trade_value:,.2f}, below the "
                f"${minimum_cash:,.2f} minimum cash reserve.",
            )

        existing_invested = portfolio.total_equity - portfolio.cash + total_pending_buy_value
        new_invested_pct = (existing_invested + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
        if new_invested_pct > max_total_exposure_pct * 100:
            _violate(
                ViolationCode.MAX_TOTAL_EXPOSURE_PCT,
                f"Total invested exposure would be {new_invested_pct:.1f}% of equity, exceeding the "
                f"{max_total_exposure_pct * 100:.1f}% total-exposure limit.",
            )

        for basket_name, basket_tickers in BASKETS.items():
            if intent.ticker.upper() not in basket_tickers and intent.ticker not in basket_tickers:
                continue
            existing_basket_value = sum(
                p.market_value for p in portfolio.positions if p.ticker in basket_tickers
            ) + sum(v for t, v in pending_by_ticker.items() if t in basket_tickers)
            new_basket_pct = (existing_basket_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
            if new_basket_pct > max_basket_pct:
                _violate(
                    ViolationCode.MAX_BASKET_PCT,
                    f"'{basket_name}' exposure would be {new_basket_pct:.1f}% of equity, exceeding the "
                    f"{max_basket_pct:.1f}% basket concentration limit.",
                )

        if intent.ticker.upper() in LEVERAGED_ETF_TICKERS:
            existing_leveraged_value = sum(
                p.market_value for p in portfolio.positions if p.is_leveraged_etf
            ) + sum(v for t, v in pending_by_ticker.items() if t in LEVERAGED_ETF_TICKERS)
            new_leveraged_pct = (existing_leveraged_value + trade_value) / portfolio.total_equity * 100 if portfolio.total_equity else 0.0
            if new_leveraged_pct > max_leveraged_etf_pct:
                _violate(
                    ViolationCode.MAX_LEVERAGED_ETF_PCT,
                    f"Leveraged ETF exposure would be {new_leveraged_pct:.1f}% of equity, exceeding the "
                    f"{max_leveraged_etf_pct:.1f}% leveraged-ETF limit.",
                )
    else:
        held_shares = sum(
            p.shares for p in portfolio.positions if p.ticker.upper() == intent.ticker.upper()
        )
        if intent.shares > held_shares:
            _violate(
                ViolationCode.SELL_EXCEEDS_HELD,
                f"Sell quantity {intent.shares} exceeds the {held_shares:g} shares currently held.",
            )

    if price_timestamp is not None and now is not None:
        # Both aware: subtraction across aware datetimes is correct
        # regardless of which zones they're each in -- no conversion
        # needed. Both naive: per this module's established contract
        # (_as_naive_eastern()'s docstring), a naive datetime is assumed
        # to already be Eastern Time, so nothing to convert either.
        # Mixed: the naive one is assumed ET (the same contract) and the
        # AWARE one is genuinely CONVERTED into Eastern via astimezone()
        # -- not just relabeled. A prior version used .replace(tzinfo=...)
        # on whichever side needed it, which silently REINTERPRETS a
        # timestamp's existing wall-clock numbers as if they were already
        # in the other zone (e.g. a genuinely UTC quote timestamp treated
        # as if it were already ET) instead of converting the instant it
        # actually represents -- a ~4-5 hour error whenever the two
        # differ (GPT review, 2026-07-29).
        if price_timestamp.tzinfo is not None and now.tzinfo is None:
            comparable_price_timestamp = price_timestamp.astimezone(_EASTERN).replace(tzinfo=None)
            comparable_now = now
        elif price_timestamp.tzinfo is None and now.tzinfo is not None:
            comparable_price_timestamp = price_timestamp.replace(tzinfo=_EASTERN)
            comparable_now = now
        else:
            comparable_price_timestamp = price_timestamp
            comparable_now = now
        age_minutes = (comparable_now - comparable_price_timestamp).total_seconds() / 60
        if age_minutes > max_stale_price_minutes:
            _violate(
                ViolationCode.STALE_PRICE,
                f"Reference price is {age_minutes:.1f} minutes old, exceeding the {max_stale_price_minutes:.1f}-minute staleness limit.",
            )
        elif age_minutes < -_FUTURE_TIMESTAMP_TOLERANCE_MINUTES:
            # A negative age (price_timestamp AFTER now) beyond a small
            # clock-skew tolerance means the timestamp is impossible, not
            # merely "very fresh" -- only the staleness check existed
            # before, so a quote timestamp minutes or hours in the future
            # passed with zero protection (GPT review, 2026-07-29).
            _violate(
                ViolationCode.FUTURE_PRICE_TIMESTAMP,
                f"Reference price timestamp is {abs(age_minutes):.1f} minutes in the FUTURE, exceeding the "
                f"{_FUTURE_TIMESTAMP_TOLERANCE_MINUTES:.1f}-minute clock-skew tolerance -- refusing to trust "
                "an impossible timestamp.",
            )

    if now is not None:
        comparable_now = _as_naive_eastern(now)
        session = _trading_session_window(comparable_now)
        if session is None:
            reason = "a weekend" if comparable_now.weekday() >= 5 else "an exchange holiday"
            _violate(ViolationCode.MARKET_CLOSED, f"{comparable_now.date()} is {reason} — markets are closed.")
        else:
            session_open, session_close = session
            if not (session_open <= comparable_now < session_close):
                _violate(
                    ViolationCode.OUTSIDE_TRADING_SESSION,
                    f"{comparable_now.time()} on {comparable_now.date()} is outside today's trading "
                    f"session ({session_open.time()}-{session_close.time()} ET, accounting for "
                    "exchange holidays and early closes).",
                )

    if recent_intents:
        for prior in recent_intents:
            if prior.ticker.upper() == intent.ticker.upper() and prior.side == intent.side:
                _violate(
                    ViolationCode.DUPLICATE_ORDER,
                    f"Duplicate order detected: a {intent.side} order for {intent.ticker} was already submitted.",
                )
                break

    if intent.order_type == "limit":
        if intent.limit_price is None or not math.isfinite(intent.limit_price) or intent.limit_price <= 0:
            _violate(ViolationCode.INVALID_LIMIT_PRICE, "Limit orders require a positive, finite limit price.")
        elif reference_price:
            slippage_pct = abs(intent.limit_price - reference_price) / reference_price * 100
            if slippage_pct > max_slippage_pct:
                _violate(
                    ViolationCode.MAX_SLIPPAGE,
                    f"Limit price ${intent.limit_price:.2f} is {slippage_pct:.1f}% away from the reference price "
                    f"${reference_price:.2f}, exceeding the {max_slippage_pct:.1f}% max-slippage limit.",
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
            _violate(
                ViolationCode.INVALID_QUOTE,
                f"Bid/ask quote is one-sided or invalid (bid=${bid_price:.2f}, ask=${ask_price:.2f}) -- "
                "refusing to trade without a complete two-sided quote.",
            )
        elif ask_price < bid_price:
            _violate(
                ViolationCode.INVALID_QUOTE,
                f"Bid/ask quote is crossed (bid=${bid_price:.2f} > ask=${ask_price:.2f}) -- this indicates "
                "a stale or corrupted quote, not a tradeable market.",
            )
        else:
            mid = (bid_price + ask_price) / 2
            spread_pct = (ask_price - bid_price) / mid * 100
            if spread_pct > max_spread_pct:
                _violate(
                    ViolationCode.MAX_SPREAD,
                    f"Bid/ask spread is {spread_pct:.2f}% (bid ${bid_price:.2f} / ask ${ask_price:.2f}), "
                    f"exceeding the {max_spread_pct:.2f}% max-spread limit -- a market order here could fill "
                    "well away from the reference price.",
                )

    # Symmetric window: blocks both the run-up to earnings and the days right
    # after, since a caller could someday pass a negative "days since" value.
    if (
        earnings_days_away is not None
        and abs(earnings_days_away) <= earnings_blackout_days
    ):
        _violate(
            ViolationCode.EARNINGS_BLACKOUT,
            f"{intent.ticker} has earnings in {earnings_days_away} day(s), within the "
            f"{earnings_blackout_days}-day earnings blackout window.",
        )

    approved = len(violations) == 0
    violations_t = tuple(violations)
    codes_t = tuple(violation_codes)
    return ValidationResult(
        approved=approved,
        violations=violations_t,
        violation_codes=codes_t,
        validation_proof=_validation_proof(intent, approved, codes_t),
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
