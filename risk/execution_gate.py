"""
Deterministic execution gate — the "never let the LLM bypass these
limits" layer from the assistant design (2026-07). Per-position sizing
and total-exposure capping, plus the checks GPT's design review
specifically called for: sector/basket limits, leveraged-ETF limits,
stale-price checks, trading-hours checks, duplicate-order detection, max
slippage, earnings restrictions, and a kill switch. (This module
previously described itself as "extending risk/manager.py" and as also
handling "stop-loss pricing" — that module was part of an earlier,
disconnected ML/signal-sizing research path with no import relationship
to this one and no stop-loss pricing logic ever lived in this module; the
old code was removed 2026-07-28, see docs/ARCHITECTURE_DEBT.md.)

A TradeIntent is a typed, frozen data structure — not free-form text.
validate_trade_intent() is pure validation: it never submits an order
itself (that's still execution/alpaca_broker.py's job) and never talks
to a network. Every check here is a plain deterministic calculation on
numbers already provided by the caller — no LLM involved.

This module IS the deterministic risk governor referenced in
docs/MANDATE.md (2026-07-28) -- the single place validate_trade_intent()'s
rule set (kill switch, per-position/total-exposure/basket/leveraged-ETF
concentration caps, price-staleness and overnight-gap checks, NYSE
calendar/trading-session checks, duplicate-order detection, earnings
blackout) is defined and enforced as one pure, network-free function, with
an HMAC-signed proof/anti-forgery layer wrapped around its output so a
caller can't hand-construct or mutate a passing result.

Known scatter points (architectural debt, not yet consolidated here --
see docs/ARCHITECTURE_DEBT.md for the full reasoning on why a
consolidation wasn't attempted alongside this labeling pass):
  - assistant/execution_service.py's _pending_buy_value_by_ticker() --
    pending-order exposure estimation, computed independently of this
    module's exposure checks.
  - assistant/allocation_batch.py's preflight_allocation_batch() --
    cumulative cross-leg reservation math for a multi-proposal batch,
    also computed independently and fed back in via override params.
  - assistant/proposals.py's generate_risk_reduction_proposals() -- a
    simpler, proposal-GENERATION-only concentration check (decides what
    to *suggest*), not gated through validate_trade_intent() (which
    decides what to *permit*) -- by design, but a real second source of
    concentration-limit logic worth knowing about.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import json
import math
import secrets
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from config import BASKETS, LEVERAGED_ETF_TICKERS, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from assistant.money import MoneyInput, decimal_or_none, to_decimal
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


def is_valid_share_quantity(value: object) -> bool:
    """True iff `value` is a positive whole-share quantity: a real `int`
    (not `bool` -- Python's `bool` subclasses `int`, so `True`/`False`
    would otherwise pass an `isinstance(value, int)` check and silently
    behave as 1/0 share(s)), not any `float` (whole-valued, fractional,
    NaN, or +/-infinity), and not a string or any other type.

    This project's execution workflow only ever submits whole-share
    orders, so this is deliberately strict rather than "numeric and
    positive": `intent.shares <= 0` alone does NOT reject NaN (every
    ordered comparison against NaN is False in Python), so a NaN share
    quantity used to sail through validate_trade_intent() approved, with
    trade_value = NaN silently defeating every downstream dollar-value
    comparison it touched (max-order-value, cash, position-size,
    total-exposure, basket, leveraged-ETF) rather than being rejected
    (GPT review, 2026-07-29, independently reproduced). Reused by
    validate_trade_intent() (the authorization boundary) AND
    execution/alpaca_broker.py's submit_*_order() functions (the last
    line of defense before a real broker call, independent of whether
    validate_trade_intent() ran at all) so the two checks can never
    silently drift apart."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


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
    INVALID_AVAILABLE_CAPITAL_OVERRIDE = "invalid_available_capital_override"


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


def _authorization_proof(intent: TradeIntent, token: str, expires_at: str) -> str:
    # `expires_at` is part of the signed payload -- NOT just intent
    # identity -- so the expiry itself can't be extended after the fact.
    # ExecutionAuthorization is frozen, but dataclasses.replace() (or any
    # code building a new instance) can copy an existing, validly-signed
    # `proof` onto an object with a LATER `expires_at`; since the prior
    # version's proof didn't cover expires_at, that forged object would
    # still verify, defeating "short-lived" entirely (GPT review,
    # 2026-07-27).
    #
    # `token` is ALSO part of the signed payload (GPT review, 2026-07-31,
    # independently reproduced): the one-time-use replay check below keys
    # off `authorization.token`, but the token itself used to be entirely
    # UNSIGNED -- `dataclasses.replace(authorization, token="anything")`
    # kept the exact same valid proof (since proof never covered token at
    # all), producing an object with a fresh, never-consumed token but
    # the SAME valid intent+expiry binding, completely bypassing replay
    # detection. Binding token into the proof means swapping it invalidates
    # the proof, exactly like swapping expires_at or the intent already did.
    return _sign(f"authorized:{intent_fingerprint(intent)}:{token}:{expires_at}")


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
    token = secrets.token_urlsafe(32)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    return ExecutionAuthorization(
        token=token,
        intent_fingerprint=intent_fingerprint(intent),
        proof=_authorization_proof(intent, token, expires_at),
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
    token = secrets.token_urlsafe(32)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    return ExecutionAuthorization(
        token=token,
        intent_fingerprint=intent_fingerprint(intent),
        proof=_authorization_proof(intent, token, expires_at),
        approved_at=now.isoformat(),
        expires_at=expires_at,
    )


# token -> expires_at (ISO string), for the one-time-use check below.
# Process-local and in-memory: this is a defense-in-depth hardening for
# the ExecutionAuthorization.token field (GPT review, 2026-07-31,
# reproduced: `.token` was generated by authorize_trade_intent()/
# authorize_overridden_trade_intent() -- implying single-use, per its own
# docstring -- but this function never actually read or checked it, so
# the SAME authorization object could legitimately be replayed against
# submit_market_order()/submit_limit_order() (and, at the time this fix
# was written, the now-removed submit_stop_loss_order()) as many times as
# wanted within its TTL window). Doesn't survive a process
# restart, but neither does anything else about a short-lived (120s
# default) authorization -- this doesn't currently bypass the personal-
# assistant's single-use proposal workflow (the proposal state machine's
# atomic claiming already prevents the real code paths from attempting a
# second broker call for the same proposal), but hardens the primitive
# itself for any future caller of these lower-level execution functions.
_consumed_authorization_tokens: dict[str, str] = {}


def _prune_expired_consumed_tokens(current: datetime) -> None:
    expired = [
        token for token, expires_at in _consumed_authorization_tokens.items()
        if datetime.fromisoformat(expires_at) < current
    ]
    for token in expired:
        del _consumed_authorization_tokens[token]


def verify_execution_authorization(
    intent: TradeIntent,
    authorization: ExecutionAuthorization | None,
    now: datetime | None = None,
) -> None:
    if authorization is None:
        raise PermissionError("Broker submission requires a short-lived execution-gate authorization.")
    # Rejected explicitly, before the proof check -- an empty/malformed
    # token could otherwise reach the consumption check below with a
    # falsy dict key, and this makes the requirement unambiguous rather
    # than relying on the proof mismatch to catch it incidentally (GPT
    # review, 2026-07-31).
    if not authorization.token:
        raise PermissionError("Execution-gate authorization has an empty or missing token.")
    if not hmac.compare_digest(
        authorization.proof, _authorization_proof(intent, authorization.token, authorization.expires_at)
    ):
        raise PermissionError("Execution-gate authorization does not match this trade intent.")
    current = now or datetime.now(timezone.utc)
    expires = datetime.fromisoformat(authorization.expires_at)
    if current > expires:
        raise PermissionError("Execution-gate authorization has expired.")
    _prune_expired_consumed_tokens(current)
    if authorization.token in _consumed_authorization_tokens:
        raise PermissionError(
            "This execution-gate authorization has already been consumed -- authorizations are single-use."
        )
    _consumed_authorization_tokens[authorization.token] = authorization.expires_at


def worst_case_fill_price(intent: TradeIntent, reference_price: float) -> float:
    """
    The most expensive price `intent` could actually fill at -- what every
    dollar-denominated risk check should be priced against, rather than the
    current quote.

    A BUY limit order can fill anywhere up to its limit price, so pricing its
    risk at the quote understates every dollar cap whenever limit_price >
    reference_price. validate_trade_intent()'s max-slippage check bounds how
    far apart the two may be, but a bounded overrun is still an overrun: a
    $5,000 max-order-value cap approved a $4,990 quoted notional whose
    permitted fill was $5,039 (GPT review, 2026-07-29). This affects
    max_order_value, available cash, the cash reserve, and concentration.

    Buys only, deliberately. A SELL limit fills at its limit price or BETTER
    (higher), so the quote never understates a sell's risk -- and pricing
    sells at a worst case could newly block an exposure-REDUCING order, the
    one direction this gate must never obstruct.

    Shared by validate_trade_intent() and allocation_batch's
    preflight_allocation_batch() (which reserves cash per approved leg) so the
    two cannot drift apart -- they underestimated identically before this
    existed. Falls back to `reference_price` unchanged for market orders, for
    a missing/non-finite limit price, and whenever the limit is at or below
    the quote; a non-finite reference_price is returned as-is so the caller's
    own INVALID_REFERENCE_PRICE check still fires rather than being masked.
    """
    try:
        return float(worst_case_fill_price_decimal(intent, reference_price))
    except ValueError:
        # Preserve the helper's historical contract for corrupt reference
        # values: the caller's INVALID_REFERENCE_PRICE check owns rejection.
        return reference_price


def worst_case_fill_price_decimal(
    intent: TradeIntent, reference_price: MoneyInput
) -> Decimal:
    """Exact counterpart used by every dollar-denominated safety check."""
    reference = to_decimal(reference_price, name="reference_price")
    limit = (
        decimal_or_none(intent.limit_price)
        if intent.limit_price is not None
        else None
    )
    if (
        intent.order_type != "limit"
        or intent.side != "buy"
        or limit is None
    ):
        return reference
    return max(reference, limit)


# ---------------------------------------------------------------------------
# GR-2: the risk-check registry.
#
# Every check the gate enforces is a NAMED entry in RISK_CHECK_REGISTRY, in
# the exact order the historical hand-written sequence ran them, and
# validate_trade_intent() executes the registry rather than inline blocks.
# Adding a risk rule is one check function plus one registry entry; removing
# or reordering one fails tests/test_risk_check_registry.py's frozen
# inventory loudly. Consolidation must never REDUCE what runs: each function
# below is the verbatim logic (messages included) of the block it replaced,
# with its review-history commentary kept where the logic lives.
#
# Checks communicate through _GateContext: earlier checks both record
# violations and derive the sanitized numeric state later checks consume
# (that data-flow is exactly why the order is load-bearing and frozen).
# `applies_at` phases follow the archived plan (`proposal`, `pre_submit`,
# `post_approval`). Today every check runs at the gate's single historical
# moment -- fresh revalidation immediately before submission
# (`pre_submit`) -- so that is each entry's phase; the registry exists so a
# future proposal-time or post-approval consumer runs checks_for_phase()
# instead of growing another hand-written, driftable sequence.
# ---------------------------------------------------------------------------

PROPOSAL_PHASE = "proposal"
PRE_SUBMIT_PHASE = "pre_submit"
POST_APPROVAL_PHASE = "post_approval"
_KNOWN_PHASES = frozenset({PROPOSAL_PHASE, PRE_SUBMIT_PHASE, POST_APPROVAL_PHASE})

#: Which sides a check runs for. "non_buy" (not "sell") is deliberate: the
#: historical sequence ran the held-shares check in the buy-group's `else`
#: branch, so an invalid side like "banana" still exercised it. Renaming
#: this to "sell" would silently skip that path for invalid sides.
_SIDE_BOTH = "both"
_SIDE_BUY = "buy"
_SIDE_NON_BUY = "non_buy"


class _GateContext:
    """Mutable working state shared by the ordered checks of one validation.

    Carries the raw inputs plus every sanitized intermediate the historical
    inline sequence threaded from block to block (decimal conversions,
    per-position money, safe share count, trade value, pending-buy sums,
    available capital). A check may read anything set by an EARLIER check
    only -- the registry order is the dependency order.
    """

    def __init__(self, **inputs) -> None:
        self.__dict__.update(inputs)
        self.violations: list[str] = []
        self.violation_codes: list[str] = []
        # Derived state, populated by checks in registry order.
        self.portfolio_cash: Decimal | None = None
        self.portfolio_equity: Decimal | None = None
        self.portfolio_buying_power: Decimal | None = None
        self.position_money: list[
            tuple[Decimal | None, Decimal | None, Decimal | None]
        ] = []
        self.shares_valid: bool = False
        self.safe_shares: int = 0
        self.reference_price_decimal: Decimal | None = None
        self.trade_value: Decimal = Decimal("0")
        self.pending_by_ticker: dict[str, Decimal] = {}
        self.total_pending_buy_value: Decimal = Decimal("0")

    def violate(self, code: ViolationCode, message: str) -> None:
        self.violations.append(message)
        self.violation_codes.append(code.value)


def _check_kill_switch(ctx: _GateContext) -> None:
    if ctx.kill_switch_active:
        ctx.violate(
            ViolationCode.KILL_SWITCH,
            "Kill switch is active — no trades are permitted.",
        )


def _check_portfolio_numeric_integrity(ctx: _GateContext) -> None:
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
    portfolio = ctx.portfolio
    ctx.portfolio_cash = decimal_or_none(portfolio.cash)
    ctx.portfolio_equity = decimal_or_none(portfolio.total_equity)
    ctx.portfolio_buying_power = (
        decimal_or_none(portfolio.buying_power)
        if portfolio.buying_power is not None
        else None
    )
    if ctx.portfolio_cash is None:
        ctx.violate(
            ViolationCode.INVALID_PORTFOLIO_CASH,
            f"portfolio.cash must be finite, got {portfolio.cash}.",
        )
    elif ctx.portfolio_cash < 0:
        ctx.violate(
            ViolationCode.INVALID_PORTFOLIO_CASH,
            f"portfolio.cash must be non-negative (this project does not model margin/short cash "
            f"balances), got {portfolio.cash}.",
        )
    if ctx.portfolio_equity is None:
        ctx.violate(
            ViolationCode.INVALID_PORTFOLIO_EQUITY,
            f"portfolio.total_equity must be finite, got {portfolio.total_equity}.",
        )
    elif ctx.intent.side == "buy" and ctx.portfolio_equity <= 0:
        ctx.violate(
            ViolationCode.INVALID_PORTFOLIO_EQUITY,
            f"portfolio.total_equity must be positive to size a buy against it, got {portfolio.total_equity}.",
        )
    if portfolio.buying_power is not None and ctx.portfolio_buying_power is None:
        ctx.violate(
            ViolationCode.INVALID_BUYING_POWER,
            f"portfolio.buying_power must be finite when present, got {portfolio.buying_power}.",
        )


def _check_position_data_integrity(ctx: _GateContext) -> None:
    for position in ctx.portfolio.positions:
        entry_price = decimal_or_none(position.entry_price)
        current_price = decimal_or_none(position.current_price)
        market_value = decimal_or_none(position.market_value)
        ctx.position_money.append((entry_price, current_price, market_value))
        bad_fields = [
            (name, value)
            for name, value, converted in (
                ("shares", position.shares, decimal_or_none(position.shares)),
                ("entry_price", position.entry_price, entry_price),
                ("current_price", position.current_price, current_price),
                ("market_value", position.market_value, market_value),
            )
            if converted is None
        ]
        if bad_fields:
            detail = ", ".join(f"{name}={value}" for name, value in bad_fields)
            ctx.violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has non-finite data ({detail}) -- refusing to compute "
                "exposure with corrupted position data.",
            )
            continue
        if position.shares < 0:
            ctx.violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has negative shares ({position.shares}) -- this project "
                "does not model short positions.",
            )
        if market_value is not None and market_value < 0:
            ctx.violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has negative market_value ({position.market_value}).",
            )
        if (
            current_price is not None
            and entry_price is not None
            and (current_price <= 0 or entry_price <= 0)
        ):
            ctx.violate(
                ViolationCode.INVALID_POSITION_DATA,
                f"Position {position.ticker} has a non-positive price (entry_price="
                f"{position.entry_price}, current_price={position.current_price}).",
            )


def _check_share_quantity(ctx: _GateContext) -> None:
    # Strict, not just "positive": rejects NaN, +/-infinity, fractional
    # floats, bool, strings, and any other non-int type -- `shares <= 0`
    # alone does not reject NaN (every ordered comparison against NaN is
    # False in Python), so a NaN quantity used to pass this check, make
    # trade_value NaN, and silently defeat every downstream dollar-value
    # comparison in this function too (GPT review, 2026-07-29).
    ctx.shares_valid = is_valid_share_quantity(ctx.intent.shares)
    if not ctx.shares_valid:
        ctx.violate(
            ViolationCode.INVALID_SHARES,
            f"shares must be a positive whole number (int), got {ctx.intent.shares!r} "
            f"({type(ctx.intent.shares).__name__}) -- NaN, infinity, fractional, boolean, "
            "and non-numeric values are never valid share quantities.",
        )
    # A rejected/invalid shares value must not be allowed to poison every
    # dollar-value comparison below (NaN propagates through arithmetic,
    # and a non-numeric type like a string would raise instead) -- `0` is
    # substituted ONLY for this function's own arithmetic; `approved` is
    # already guaranteed False from the violation just recorded above, so
    # this substitution can never mask the rejection, only keep the rest
    # of the checks running instead of crashing.
    ctx.safe_shares = ctx.intent.shares if ctx.shares_valid else 0


def _check_intent_side(ctx: _GateContext) -> None:
    if ctx.intent.side not in ("buy", "sell"):
        ctx.violate(
            ViolationCode.INVALID_SIDE,
            f"side must be 'buy' or 'sell', got {ctx.intent.side!r}.",
        )


def _check_order_type(ctx: _GateContext) -> None:
    if ctx.intent.order_type not in ("market", "limit", "stop"):
        ctx.violate(
            ViolationCode.INVALID_ORDER_TYPE,
            f"Unsupported order type: {ctx.intent.order_type!r}.",
        )


def _check_reference_price_and_order_value(ctx: _GateContext) -> None:
    ctx.reference_price_decimal = decimal_or_none(ctx.reference_price)
    if ctx.reference_price_decimal is None or ctx.reference_price_decimal <= 0:
        ctx.violate(
            ViolationCode.INVALID_REFERENCE_PRICE,
            f"reference_price must be a positive, finite number, got {ctx.reference_price}.",
        )
    # Keep evaluating after invalid input so callers receive all violations;
    # the recorded hard violation guarantees this fallback can never approve.
    arithmetic_reference_price = ctx.reference_price_decimal or Decimal("0")
    try:
        fill_price = worst_case_fill_price_decimal(ctx.intent, arithmetic_reference_price)
    except ValueError:
        fill_price = arithmetic_reference_price
    ctx.trade_value = Decimal(ctx.safe_shares) * fill_price
    max_order_value_decimal = (
        decimal_or_none(ctx.max_order_value)
        if ctx.max_order_value is not None
        else None
    )
    if ctx.max_order_value is not None and max_order_value_decimal is None:
        # Policy validation normally makes this unreachable; fail closed for
        # direct callers of the pure gate too.
        ctx.violate(
            ViolationCode.MAX_ORDER_VALUE,
            f"max_order_value must be positive and finite, got {ctx.max_order_value}.",
        )
    elif max_order_value_decimal is not None and ctx.trade_value > max_order_value_decimal:
        ctx.violate(
            ViolationCode.MAX_ORDER_VALUE,
            f"Trade value ${ctx.trade_value:,.2f} exceeds the ${ctx.max_order_value:,.2f} maximum order value.",
        )


def _check_pending_buy_values(ctx: _GateContext) -> None:
    # A NaN/negative pending value must fail closed, not silently
    # corrupt the arithmetic below: NaN propagates through every sum
    # it touches, and `x > cap` for a NaN `x` is always False in
    # Python -- exactly the "silently disables the check" failure
    # mode already fixed elsewhere in this module for reference_price/
    # limit_price/bid/ask, but missed here when
    # pending_buy_value_by_ticker was added (GPT review, 2026-07-27).
    for raw_ticker, raw_value in (ctx.pending_buy_value_by_ticker or {}).items():
        pending_value = decimal_or_none(raw_value)
        if pending_value is None or pending_value < 0:
            ctx.violate(
                ViolationCode.INVALID_PENDING_VALUE,
                f"pending_buy_value_by_ticker[{raw_ticker!r}] must be a non-negative, finite "
                f"number, got {raw_value} -- refusing to compute exposure with a corrupted "
                "pending-order value.",
            )
            continue
        key = raw_ticker.upper()
        ctx.pending_by_ticker[key] = (
            ctx.pending_by_ticker.get(key, Decimal("0")) + pending_value
        )
    ctx.total_pending_buy_value = sum(ctx.pending_by_ticker.values(), Decimal("0"))


def _check_max_position_pct(ctx: _GateContext) -> None:
    existing_position_value = sum(
        (
            market_value
            for p, (_, _, market_value) in zip(ctx.portfolio.positions, ctx.position_money)
            if p.ticker.upper() == ctx.intent.ticker.upper() and market_value is not None
        ),
        Decimal("0"),
    ) + ctx.pending_by_ticker.get(ctx.intent.ticker.upper(), Decimal("0"))
    new_position_pct = (
        (existing_position_value + ctx.trade_value)
        / ctx.portfolio_equity
        * Decimal("100")
        if ctx.portfolio_equity is not None and ctx.portfolio_equity
        else Decimal("0")
    )
    max_position_percent = to_decimal(ctx.max_position_pct) * Decimal("100")
    if new_position_pct > max_position_percent:
        ctx.violate(
            ViolationCode.MAX_POSITION_PCT,
            f"Position size would be {new_position_pct:.1f}% of equity, exceeding the "
            f"{ctx.max_position_pct * 100:.1f}% per-position limit.",
        )


def _check_cash_and_reserve(ctx: _GateContext) -> None:
    # Overrides must be finite or they're ignored (falling back to the
    # real portfolio figures) -- a non-finite override still records a
    # hard, non-overridable violation below, so this fallback never
    # papers over the bad input; it just keeps the arithmetic sane
    # while `approved` is already guaranteed False.
    available_cash_decimal = (
        decimal_or_none(ctx.available_cash_override)
        if ctx.available_cash_override is not None
        else None
    )
    if ctx.available_cash_override is not None and available_cash_decimal is None:
        ctx.violate(
            ViolationCode.INVALID_AVAILABLE_CAPITAL_OVERRIDE,
            f"available_cash_override must be finite, got {ctx.available_cash_override}.",
        )
    available_buying_power_decimal = (
        decimal_or_none(ctx.available_buying_power_override)
        if ctx.available_buying_power_override is not None
        else None
    )
    if (
        ctx.available_buying_power_override is not None
        and available_buying_power_decimal is None
    ):
        ctx.violate(
            ViolationCode.INVALID_AVAILABLE_CAPITAL_OVERRIDE,
            f"available_buying_power_override must be finite, got {ctx.available_buying_power_override}.",
        )

    # portfolio.cash alone ignores pending/open orders reserving that
    # same cash (e.g. two proposals approved back-to-back, or an
    # unrelated pending buy on another ticker) -- portfolio.buying_power,
    # when the broker supplies it, already nets those holds out, so it's
    # the tighter and more honest ceiling whenever it's available
    # (Codex review, 2026-07-27: reproduced a $5,000 approval against
    # $1,000 of real buying power sitting behind a $9,000 pending buy).
    # `available_cash_override`/`available_buying_power_override` (see
    # validate_trade_intent's docstring) let a caller simulating earlier
    # reserved batch legs tighten these WITHOUT touching
    # portfolio.cash/buying_power themselves, since those two also feed
    # `existing_invested` below and must stay at their real, unreserved
    # values there.
    available_capital = (
        available_cash_decimal
        if available_cash_decimal is not None
        else (ctx.portfolio_cash or Decimal("0"))
    )
    effective_buying_power = (
        available_buying_power_decimal
        if available_buying_power_decimal is not None
        else ctx.portfolio_buying_power
    )
    if effective_buying_power is not None:
        available_capital = min(available_capital, effective_buying_power)
    if ctx.trade_value > available_capital:
        ctx.violate(
            ViolationCode.INSUFFICIENT_CASH,
            f"Trade value ${ctx.trade_value:,.2f} exceeds available cash ${available_capital:,.2f}.",
        )
    minimum_cash = (
        (ctx.portfolio_equity or Decimal("0"))
        * to_decimal(ctx.min_cash_reserve_pct)
    )
    if available_capital - ctx.trade_value < minimum_cash:
        ctx.violate(
            ViolationCode.MIN_CASH_RESERVE,
            f"Cash after trade would be ${available_capital - ctx.trade_value:,.2f}, below the "
            f"${minimum_cash:,.2f} minimum cash reserve.",
        )


def _check_max_total_exposure(ctx: _GateContext) -> None:
    # Deliberately portfolio.cash (the REAL, unreserved figure), never
    # the cash check's available_capital -- existing_invested must derive
    # from the account's actual state, with pending/simulated buys entering
    # ONLY via total_pending_buy_value, or an earlier reserved leg
    # would be counted twice: once here (via a shrunk cash figure)
    # and again via total_pending_buy_value (see validate_trade_intent's
    # docstring).
    existing_invested = (
        (ctx.portfolio_equity or Decimal("0"))
        - (ctx.portfolio_cash or Decimal("0"))
        + ctx.total_pending_buy_value
    )
    new_invested_pct = (
        (existing_invested + ctx.trade_value)
        / ctx.portfolio_equity
        * Decimal("100")
        if ctx.portfolio_equity is not None and ctx.portfolio_equity
        else Decimal("0")
    )
    max_total_exposure_percent = (
        to_decimal(ctx.max_total_exposure_pct) * Decimal("100")
    )
    if new_invested_pct > max_total_exposure_percent:
        ctx.violate(
            ViolationCode.MAX_TOTAL_EXPOSURE_PCT,
            f"Total invested exposure would be {new_invested_pct:.1f}% of equity, exceeding the "
            f"{ctx.max_total_exposure_pct * 100:.1f}% total-exposure limit.",
        )


def _check_basket_concentration(ctx: _GateContext) -> None:
    for basket_name, basket_tickers in BASKETS.items():
        if (
            ctx.intent.ticker.upper() not in basket_tickers
            and ctx.intent.ticker not in basket_tickers
        ):
            continue
        existing_basket_value = sum(
            (
                market_value
                for p, (_, _, market_value) in zip(ctx.portfolio.positions, ctx.position_money)
                if p.ticker.upper() in basket_tickers and market_value is not None
            ),
            Decimal("0"),
        ) + sum(
            (v for t, v in ctx.pending_by_ticker.items() if t in basket_tickers),
            Decimal("0"),
        )
        new_basket_pct = (
            (existing_basket_value + ctx.trade_value)
            / ctx.portfolio_equity
            * Decimal("100")
            if ctx.portfolio_equity is not None and ctx.portfolio_equity
            else Decimal("0")
        )
        if new_basket_pct > to_decimal(ctx.max_basket_pct):
            ctx.violate(
                ViolationCode.MAX_BASKET_PCT,
                f"'{basket_name}' exposure would be {new_basket_pct:.1f}% of equity, exceeding the "
                f"{ctx.max_basket_pct:.1f}% basket concentration limit.",
            )


def _check_leveraged_etf_concentration(ctx: _GateContext) -> None:
    if ctx.intent.ticker.upper() not in LEVERAGED_ETF_TICKERS:
        return
    existing_leveraged_value = sum(
        (
            market_value
            for p, (_, _, market_value) in zip(ctx.portfolio.positions, ctx.position_money)
            if p.is_leveraged_etf and market_value is not None
        ),
        Decimal("0"),
    ) + sum(
        (
            v
            for t, v in ctx.pending_by_ticker.items()
            if t in LEVERAGED_ETF_TICKERS
        ),
        Decimal("0"),
    )
    new_leveraged_pct = (
        (existing_leveraged_value + ctx.trade_value)
        / ctx.portfolio_equity
        * Decimal("100")
        if ctx.portfolio_equity is not None and ctx.portfolio_equity
        else Decimal("0")
    )
    if new_leveraged_pct > to_decimal(ctx.max_leveraged_etf_pct):
        ctx.violate(
            ViolationCode.MAX_LEVERAGED_ETF_PCT,
            f"Leveraged ETF exposure would be {new_leveraged_pct:.1f}% of equity, exceeding the "
            f"{ctx.max_leveraged_etf_pct:.1f}% leveraged-ETF limit.",
        )


def _check_sell_exceeds_held(ctx: _GateContext) -> None:
    held_shares = sum(
        p.shares
        for p in ctx.portfolio.positions
        if p.ticker.upper() == ctx.intent.ticker.upper()
    )
    if ctx.safe_shares > held_shares:
        ctx.violate(
            ViolationCode.SELL_EXCEEDS_HELD,
            f"Sell quantity {ctx.intent.shares!r} exceeds the {held_shares:g} shares currently held.",
        )


def _check_price_freshness(ctx: _GateContext) -> None:
    if ctx.price_timestamp is None or ctx.now is None:
        return
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
    price_timestamp, now = ctx.price_timestamp, ctx.now
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
    if age_minutes > ctx.max_stale_price_minutes:
        ctx.violate(
            ViolationCode.STALE_PRICE,
            f"Reference price is {age_minutes:.1f} minutes old, exceeding the {ctx.max_stale_price_minutes:.1f}-minute staleness limit.",
        )
    elif age_minutes < -_FUTURE_TIMESTAMP_TOLERANCE_MINUTES:
        # A negative age (price_timestamp AFTER now) beyond a small
        # clock-skew tolerance means the timestamp is impossible, not
        # merely "very fresh" -- only the staleness check existed
        # before, so a quote timestamp minutes or hours in the future
        # passed with zero protection (GPT review, 2026-07-29).
        ctx.violate(
            ViolationCode.FUTURE_PRICE_TIMESTAMP,
            f"Reference price timestamp is {abs(age_minutes):.1f} minutes in the FUTURE, exceeding the "
            f"{_FUTURE_TIMESTAMP_TOLERANCE_MINUTES:.1f}-minute clock-skew tolerance -- refusing to trust "
            "an impossible timestamp.",
        )


def _check_trading_session(ctx: _GateContext) -> None:
    if ctx.now is None:
        return
    comparable_now = _as_naive_eastern(ctx.now)
    session = _trading_session_window(comparable_now)
    if session is None:
        reason = "a weekend" if comparable_now.weekday() >= 5 else "an exchange holiday"
        ctx.violate(
            ViolationCode.MARKET_CLOSED,
            f"{comparable_now.date()} is {reason} — markets are closed.",
        )
    else:
        session_open, session_close = session
        if not (session_open <= comparable_now < session_close):
            ctx.violate(
                ViolationCode.OUTSIDE_TRADING_SESSION,
                f"{comparable_now.time()} on {comparable_now.date()} is outside today's trading "
                f"session ({session_open.time()}-{session_close.time()} ET, accounting for "
                "exchange holidays and early closes).",
            )


def _check_duplicate_order(ctx: _GateContext) -> None:
    if not ctx.recent_intents:
        return
    for prior in ctx.recent_intents:
        if (
            prior.ticker.upper() == ctx.intent.ticker.upper()
            and prior.side == ctx.intent.side
        ):
            ctx.violate(
                ViolationCode.DUPLICATE_ORDER,
                f"Duplicate order detected: a {ctx.intent.side} order for {ctx.intent.ticker} was already submitted.",
            )
            break


def _check_limit_price_and_slippage(ctx: _GateContext) -> None:
    if ctx.intent.order_type != "limit":
        return
    limit_price_decimal = (
        decimal_or_none(ctx.intent.limit_price)
        if ctx.intent.limit_price is not None
        else None
    )
    if limit_price_decimal is None or limit_price_decimal <= 0:
        ctx.violate(
            ViolationCode.INVALID_LIMIT_PRICE,
            "Limit orders require a positive, finite limit price.",
        )
    elif ctx.reference_price_decimal is not None and ctx.reference_price_decimal > 0:
        slippage_pct = (
            abs(limit_price_decimal - ctx.reference_price_decimal)
            / ctx.reference_price_decimal
            * Decimal("100")
        )
        if slippage_pct > to_decimal(ctx.max_slippage_pct):
            ctx.violate(
                ViolationCode.MAX_SLIPPAGE,
                f"Limit price ${limit_price_decimal:.2f} is {slippage_pct:.1f}% away from the reference price "
                f"${ctx.reference_price_decimal:.2f}, exceeding the {ctx.max_slippage_pct:.1f}% max-slippage limit.",
            )


def _check_bid_ask_quote_and_spread(ctx: _GateContext) -> None:
    # Bid/ask is opt-in (many callers/tests validate without a live quote
    # at all, e.g. anything upstream of a broker call) -- but once BOTH
    # sides are supplied, a bad quote must fail closed, not be silently
    # skipped. A prior version only ran this check when both sides were
    # already known to be positive, which let a one-sided quote (bid=0 or
    # ask=0, common outside market hours) or a crossed quote (ask < bid,
    # a data anomaly) pass with zero protection -- exactly the situations
    # where a market order is most likely to fill badly.
    if ctx.bid_price is None or ctx.ask_price is None:
        return
    bid_price_decimal = decimal_or_none(ctx.bid_price)
    ask_price_decimal = decimal_or_none(ctx.ask_price)
    if (
        bid_price_decimal is None
        or ask_price_decimal is None
        or bid_price_decimal <= 0
        or ask_price_decimal <= 0
    ):
        ctx.violate(
            ViolationCode.INVALID_QUOTE,
            f"Bid/ask quote is one-sided or invalid (bid={ctx.bid_price!r}, ask={ctx.ask_price!r}) -- "
            "refusing to trade without a complete two-sided quote.",
        )
    elif ask_price_decimal < bid_price_decimal:
        ctx.violate(
            ViolationCode.INVALID_QUOTE,
            f"Bid/ask quote is crossed (bid=${bid_price_decimal:.2f} > ask=${ask_price_decimal:.2f}) -- this indicates "
            "a stale or corrupted quote, not a tradeable market.",
        )
    else:
        mid = (bid_price_decimal + ask_price_decimal) / Decimal("2")
        spread_pct = (
            (ask_price_decimal - bid_price_decimal)
            / mid
            * Decimal("100")
        )
        if spread_pct > to_decimal(ctx.max_spread_pct):
            ctx.violate(
                ViolationCode.MAX_SPREAD,
                f"Bid/ask spread is {spread_pct:.2f}% (bid ${bid_price_decimal:.2f} / ask ${ask_price_decimal:.2f}), "
                f"exceeding the {ctx.max_spread_pct:.2f}% max-spread limit -- a market order here could fill "
                "well away from the reference price.",
            )


def _check_earnings_blackout(ctx: _GateContext) -> None:
    # Symmetric window: blocks both the run-up to earnings and the days right
    # after, since a caller could someday pass a negative "days since" value.
    if (
        ctx.earnings_days_away is not None
        and abs(ctx.earnings_days_away) <= ctx.earnings_blackout_days
    ):
        ctx.violate(
            ViolationCode.EARNINGS_BLACKOUT,
            f"{ctx.intent.ticker} has earnings in {ctx.earnings_days_away} day(s), within the "
            f"{ctx.earnings_blackout_days}-day earnings blackout window.",
        )


@dataclasses.dataclass(frozen=True)
class RiskCheck:
    """One named, ordered entry of the risk-check registry.

    ``applies_to_side`` selects which intents exercise the check ("both",
    "buy", or "non_buy" -- see the _SIDE_* constants for why "non_buy" is
    not spelled "sell"). ``terminal`` means a violation from this check
    stops evaluation immediately (only the kill switch historically
    short-circuited; everything else accumulates so callers see the full
    picture). ``applies_at`` is the set of lifecycle phases the check is
    valid for; the gate's own invocation is the ``pre_submit`` phase.
    """

    name: str
    applies_to_side: str
    terminal: bool
    applies_at: frozenset
    run: object  # Callable[[_GateContext], None]; kept loose for dataclass frozenness


def _entry(
    name: str,
    run,
    *,
    applies_to_side: str = _SIDE_BOTH,
    terminal: bool = False,
    applies_at: frozenset = frozenset({PRE_SUBMIT_PHASE}),
) -> RiskCheck:
    if applies_to_side not in (_SIDE_BOTH, _SIDE_BUY, _SIDE_NON_BUY):
        raise ValueError(f"unknown applies_to_side {applies_to_side!r}")
    if not applies_at or not applies_at <= _KNOWN_PHASES:
        raise ValueError(f"applies_at must be a non-empty subset of {sorted(_KNOWN_PHASES)}")
    return RiskCheck(
        name=name,
        applies_to_side=applies_to_side,
        terminal=terminal,
        applies_at=applies_at,
        run=run,
    )


#: THE ordered risk-check inventory. Order is load-bearing twice over:
#: earlier checks derive the sanitized state later checks consume, and the
#: violation list's order is caller-visible behavior frozen by the existing
#: suites. tests/test_risk_check_registry.py pins names, order, sides,
#: terminality, and phases; changing any of it is a reviewed decision, not
#: an accident.
RISK_CHECK_REGISTRY: tuple[RiskCheck, ...] = (
    _entry("kill_switch", _check_kill_switch, terminal=True),
    _entry("portfolio_numeric_integrity", _check_portfolio_numeric_integrity),
    _entry("position_data_integrity", _check_position_data_integrity),
    _entry("share_quantity", _check_share_quantity),
    _entry("intent_side", _check_intent_side),
    _entry("order_type", _check_order_type),
    _entry("reference_price_and_order_value", _check_reference_price_and_order_value),
    _entry("pending_buy_values", _check_pending_buy_values, applies_to_side=_SIDE_BUY),
    _entry("max_position_pct", _check_max_position_pct, applies_to_side=_SIDE_BUY),
    _entry("cash_and_reserve", _check_cash_and_reserve, applies_to_side=_SIDE_BUY),
    _entry("max_total_exposure", _check_max_total_exposure, applies_to_side=_SIDE_BUY),
    _entry("basket_concentration", _check_basket_concentration, applies_to_side=_SIDE_BUY),
    _entry(
        "leveraged_etf_concentration",
        _check_leveraged_etf_concentration,
        applies_to_side=_SIDE_BUY,
    ),
    _entry("sell_exceeds_held", _check_sell_exceeds_held, applies_to_side=_SIDE_NON_BUY),
    _entry("price_freshness", _check_price_freshness),
    _entry("trading_session", _check_trading_session),
    _entry("duplicate_order", _check_duplicate_order),
    _entry("limit_price_and_slippage", _check_limit_price_and_slippage),
    _entry("bid_ask_quote_and_spread", _check_bid_ask_quote_and_spread),
    _entry("earnings_blackout", _check_earnings_blackout),
)


def checks_for_phase(phase: str) -> tuple[RiskCheck, ...]:
    """The ordered checks valid at a lifecycle phase.

    Today every registered check is ``pre_submit`` (the gate's single
    historical moment). A future proposal-time or post-approval consumer
    should call this instead of growing a second hand-written sequence --
    that scatter is exactly what ARCHITECTURE_DEBT item 2 documents.
    """
    if phase not in _KNOWN_PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {sorted(_KNOWN_PHASES)}")
    return tuple(check for check in RISK_CHECK_REGISTRY if phase in check.applies_at)


def _check_applies(check: RiskCheck, side: str) -> bool:
    if check.applies_to_side == _SIDE_BOTH:
        return True
    if check.applies_to_side == _SIDE_BUY:
        return side == "buy"
    return side != "buy"


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
    available_cash_override: float | None = None,
    available_buying_power_override: float | None = None,
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

    `available_cash_override`/`available_buying_power_override` (GPT
    review, 2026-07-29): let a caller simulating a SEQUENCE of proposals
    (assistant.allocation_batch's cumulative preflight) tell the CASH
    checks (INSUFFICIENT_CASH, MIN_CASH_RESERVE) that less capital is
    really available than `portfolio.cash`/`portfolio.buying_power` show,
    without touching what the EXPOSURE checks (position/total/basket/
    leveraged-ETF) compute existing invested value from. A prior version
    had the caller pass a `dataclasses.replace()`'d portfolio with cash
    already reduced by earlier legs' reserved notional -- but
    `existing_invested` below is derived from `portfolio.total_equity -
    portfolio.cash`, so that same reservation got counted there TOO (via
    the shrunk cash figure) in addition to `pending_buy_value_by_ticker`
    (via `extra_pending_buy_value_by_ticker`), double-counting every
    earlier leg and inflating projected exposure past what the batch
    would actually produce -- a fail-closed bug (rejected some genuinely
    safe batches), but wrong all the same.

    Accounting invariant this function now preserves: each existing
    position, real pending order, and simulated earlier batch leg
    contributes exactly once to projected exposure. `portfolio.cash`/
    `portfolio.total_equity` are ALWAYS the real, unreserved account
    figures for the exposure-side arithmetic (`existing_invested`);
    `pending_buy_value_by_ticker` (real open orders plus any caller-
    supplied `extra_pending_buy_value_by_ticker`) is the ONLY place a
    not-yet-filled dollar amount enters exposure math. The overrides here
    affect ONLY the cash/buying-power availability checks, never
    exposure -- so a reservation that reduces available cash for the
    next leg does not also inflate that leg's total/position/basket/
    leveraged-ETF exposure a second time. None (the default) for both
    overrides reproduces the exact single-proposal-execution behavior
    from before this parameter existed.
    """
    context = _GateContext(
        intent=intent,
        portfolio=portfolio,
        reference_price=reference_price,
        price_timestamp=price_timestamp,
        now=now,
        recent_intents=recent_intents,
        kill_switch_active=kill_switch_active,
        earnings_days_away=earnings_days_away,
        bid_price=bid_price,
        ask_price=ask_price,
        max_position_pct=max_position_pct,
        max_total_exposure_pct=max_total_exposure_pct,
        max_basket_pct=max_basket_pct,
        max_leveraged_etf_pct=max_leveraged_etf_pct,
        max_stale_price_minutes=max_stale_price_minutes,
        max_slippage_pct=max_slippage_pct,
        max_spread_pct=max_spread_pct,
        earnings_blackout_days=earnings_blackout_days,
        max_order_value=max_order_value,
        min_cash_reserve_pct=min_cash_reserve_pct,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        available_cash_override=available_cash_override,
        available_buying_power_override=available_buying_power_override,
    )
    # GR-2: the gate RUNS THE REGISTRY -- there is no hand-written check
    # sequence left to drift from the inventory. A terminal check (only the
    # kill switch) stops evaluation on violation, reproducing the historical
    # early return byte-for-byte; every other check accumulates so callers
    # still receive the complete picture.
    for check in checks_for_phase(PRE_SUBMIT_PHASE):
        if not _check_applies(check, intent.side):
            continue
        check.run(context)
        if check.terminal and context.violations:
            break

    approved = len(context.violations) == 0
    violations_t = tuple(context.violations)
    codes_t = tuple(context.violation_codes)
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
