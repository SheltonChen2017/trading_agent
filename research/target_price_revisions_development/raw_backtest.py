"""Pure order-based diagnostic for a separately admitted raw-target proxy.

This function admits no source, opens no file and confers no authority. Its
controller must authenticate all source/outcome and look permissions first.
Quantity sizing uses decision marks available by the cutoff, not the later
execution open. Capacity uses only pre-cutoff lagged volume. Session outcomes
may be delivered later than their market clock; delivery is never represented
as decision-known information. Orders are day-only: unfilled quantities remain
in the report and are never implicitly carried, liquidated or written off.

The fixed 10 bps per side, $0.01/share and 1% lagged-volume assumptions are
diagnostic and uncalibrated, not market facts, MOO modeling or QC parity.
An execution-time 10% name check only limits each buy fill, never rewrites
its decision quantity or forces an unrequested intra-session rebalance.
Later fills/costs and price changes can change held weights; this is not a
continuous holding-period name-cap guarantee.
Finite Decimal inputs become exact rationals so caller Decimal context cannot
round hypothetical money. This separate pure path does not import the
synthetic-only contract or execution-capable money/assistant packages.
Corporate-action economics are externally admitted outcomes, never source
announcement facts. Dividends are gross, non-spendable ex-date receivables;
no payment date, tax or reinvestment is invented. Splits preserve original
fill economics and convert raw-share units, with explicit refusal of fractional
held/order entitlements and simultaneous split/dividend basis ambiguity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import re

MODE = "raw-target-change-proxy-development"
AUTHORITY = (("canonical_admission", False), ("confirmatory_alpha", False),
             ("market_edge", False), ("qc", False), ("live_trading", False))
SLIPPAGE = Fraction(1, 1000)
COMMISSION_PER_SHARE = Fraction(1, 100)
MAX_NAME_WEIGHT = Fraction(1, 10)
MAX_SECURITIES = 4096
MAX_SESSIONS = 10000
MAX_BAR_ROWS = 1000000
MAX_ACTIONS = 100000
MAX_QUANTITY = 1000000000
MAX_FIRST_CUTOFF_AGE = timedelta(days=7)


class RawBacktestError(ValueError):
    """Invalid inputs refuse the hypothetical computation before publication."""


@dataclass(frozen=True)
class RawPosition:
    security_id: str
    quantity: int


@dataclass(frozen=True)
class RawOrder:
    order_id: str
    session_id: str
    security_id: str
    side: str
    requested_quantity: int
    filled_quantity: int
    pending_quantity: int
    status: str
    reason: str


@dataclass(frozen=True)
class RawFill:
    order_id: str
    session_id: str
    security_id: str
    side: str
    quantity: int
    raw_open_price: str
    execution_price: str
    notional: str
    commission: str
    slippage_cost: str


@dataclass(frozen=True)
class RawExclusion:
    session_id: str
    security_id: str
    reason: str


@dataclass(frozen=True)
class RawCorporateAction:
    action_id: str
    session_id: str
    security_id: str
    kind: str
    input_value: str | None
    prior_quantity: int
    resulting_quantity: int | None
    cash_receivable: str | None
    status: str


@dataclass(frozen=True)
class RawSessionResult:
    session_id: str
    cutoff_utc: str | None
    decision_equity: str | None
    open_equity: str | None
    close_equity: str | None
    cash: str
    positions: tuple[RawPosition, ...]
    unpriced_security_ids: tuple[str, ...]
    dividend_receivable: str = "0"


@dataclass(frozen=True)
class RawBacktestResult:
    initial_cash: str
    initial_positions: tuple[RawPosition, ...]
    final_cash: str
    final_positions: tuple[RawPosition, ...]
    sessions: tuple[RawSessionResult, ...]
    orders: tuple[RawOrder, ...]
    fills: tuple[RawFill, ...]
    exclusions: tuple[RawExclusion, ...]
    total_commission: str
    total_slippage: str
    complete: bool
    mode: str = MODE
    costs_calibrated: bool = False
    point_in_time_data: bool = False
    source_and_look_admission_required: bool = True
    authority: tuple[tuple[str, bool], ...] = AUTHORITY
    sizing_policy: str = "decision-mark-whole-share-cost-reserve"
    liquidity_policy: str = "one-percent-pre-cutoff-lagged-volume-day-only"
    slippage_bps_per_side: str = "10"
    commission_per_share: str = "0.01"
    maximum_name_weight: str = "0.1"
    execution_name_cap_policy: str = "point-of-buy-fill-open-nav-including-own-friction"
    corporate_actions: tuple[RawCorporateAction, ...] = ()
    final_dividend_receivable: str = "0"
    dividend_cash_policy: str = "exdate-receivable-never-spendable-no-assumed-payment-date"
    corporate_action_accounting_complete: bool = True
    unresolved_action_security_ids: tuple[str, ...] = ()
    unresolved_quantity_basis: str = "last-accounted-pre-event-quantity-not-confirmed-entitlement"
    split_cost_basis_policy: str = "original-fill-notional-and-cost-preserved-no-lot-tax-basis-claim"


def _fail(reason):
    raise RawBacktestError(reason)


def _schema(value, keys):
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != keys):
        _fail("invalid closed raw backtest schema")


def _rows(value, maximum, name, *, nonempty=False):
    if type(value) is not tuple or len(value) > maximum or (nonempty and not value):
        _fail(f"invalid bounded {name}")
    return value


def _id(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", value) is None:
        _fail("invalid source-native identity")
    return value


def _utc(value):
    if type(value) is not str or len(value) > 64:
        _fail("invalid aware UTC clock")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid aware UTC clock")


def _optional_clock(value):
    return None if value is None else _utc(value)


def _number(value, *, positive=False, maximum=Fraction(10**18)):
    if type(value) is not str or len(value) > 64 or re.fullmatch(r"[0-9]{1,32}(?:\.[0-9]{1,24})?", value) is None:
        _fail("invalid finite nonnegative decimal")
    number = Fraction(Decimal(value))
    if number > maximum or (positive and number == 0):
        _fail("invalid bounded decimal")
    return number


def _quantity(value):
    if type(value) is not int or not 0 <= value <= MAX_QUANTITY:
        _fail("invalid bounded whole-share quantity")
    return value


def _text(value):
    if value < 0:
        _fail("negative hypothetical accounting")
    numerator, denominator = value.numerator, value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail("nonterminating hypothetical amount")
    places = max(twos, fives)
    digits = str(numerator * 2 ** (places - twos) * 5 ** (places - fives))
    if not places:
        return digits
    digits = digits.zfill(places + 1)
    result = digits[:-places] + "." + digits[-places:]
    return result.rstrip("0").rstrip(".")


def _positions(holdings):
    return tuple(RawPosition(sid, qty) for sid, qty in sorted(holdings.items()) if qty)


def _marked(cash, holdings, prices):
    unpriced = tuple(sid for sid, qty in sorted(holdings.items()) if qty and prices.get(sid) is None)
    if unpriced:
        return None, unpriced
    return cash + sum((qty * prices[sid] for sid, qty in holdings.items() if qty), Fraction()), ()


def _validate(security_inventory, sessions, targets, initial_cash, initial_positions, corporate_actions):
    inventory = set()
    for row in _rows(security_inventory, MAX_SECURITIES, "stock inventory", nonempty=True):
        _schema(row, {"security_id", "asset_type"})
        sid = _id(row["security_id"])
        if type(row["asset_type"]) is not str or row["asset_type"] != "common-stock" or sid in inventory:
            _fail("invalid unique common-stock inventory")
        inventory.add(sid)
    cash = _number(initial_cash)
    holdings = {}
    for row in _rows(initial_positions, MAX_SECURITIES, "initial positions"):
        _schema(row, {"security_id", "quantity"})
        sid, qty = _id(row["security_id"]), _quantity(row["quantity"])
        if sid not in inventory or sid in holdings:
            _fail("invalid initial position identity")
        holdings[sid] = qty
    session_map, parsed_sessions, last_close, total_rows = {}, [], None, 0
    for row in _rows(sessions, MAX_SESSIONS, "sessions", nonempty=True):
        _schema(row, {"session_id", "open_utc", "close_utc", "bars"})
        session_id = _id(row["session_id"])
        opened, closed = _utc(row["open_utc"]), _utc(row["close_utc"])
        if session_id in session_map or closed <= opened or (last_close is not None and opened <= last_close):
            _fail("sessions must be unique and strictly chronological")
        bars = {}
        for bar in _rows(row["bars"], MAX_SECURITIES, "session bars"):
            total_rows += 1
            if total_rows > MAX_BAR_ROWS:
                _fail("bar row resource bound")
            _schema(bar, {"security_id", "open", "close", "lagged_volume", "volume_available_at_utc",
                          "open_available_at_utc", "close_available_at_utc", "tradable"})
            sid = _id(bar["security_id"])
            if sid not in inventory or sid in bars or type(bar["tradable"]) is not bool:
                _fail("invalid unique bar identity or tradability")
            open_price = None if bar["open"] is None else _number(bar["open"], positive=True, maximum=Fraction(10**12))
            close_price = None if bar["close"] is None else _number(bar["close"], positive=True, maximum=Fraction(10**12))
            volume = None if bar["lagged_volume"] is None else _quantity(bar["lagged_volume"])
            open_available = _optional_clock(bar["open_available_at_utc"])
            close_available = _optional_clock(bar["close_available_at_utc"])
            if (open_available is not None and open_available < opened) or (close_available is not None and close_available < closed):
                _fail("outcome availability cannot predate market event")
            bars[sid] = (open_price if open_available is not None else None,
                         close_price if close_available is not None else None,
                         volume, _optional_clock(bar["volume_available_at_utc"]), bar["tradable"])
        session_map[session_id] = (opened, closed, last_close)
        parsed_sessions.append((session_id, opened, closed, bars))
        last_close = closed
    frames = {}
    for row in _rows(targets, MAX_SESSIONS, "target frames", nonempty=True):
        _schema(row, {"session_id", "cutoff_utc", "weights", "decision_marks"})
        session_id = _id(row["session_id"])
        if session_id not in session_map or session_id in frames:
            _fail("invalid target session identity")
        cutoff = _utc(row["cutoff_utc"])
        opened, _, prior_close = session_map[session_id]
        if cutoff >= opened or (prior_close is not None and cutoff < prior_close) or (prior_close is None and opened - cutoff > MAX_FIRST_CUTOFF_AGE):
            _fail("target cutoff is stale or not before execution open")
        weights, total = {}, Fraction()
        for weight in _rows(row["weights"], MAX_SECURITIES, "weights", nonempty=True):
            _schema(weight, {"security_id", "weight"})
            sid = _id(weight["security_id"])
            number = _number(weight["weight"], maximum=MAX_NAME_WEIGHT)
            if sid not in inventory or sid in weights:
                _fail("invalid unique target identity")
            weights[sid], total = number, total + number
        if total > 1:
            _fail("total stock target weight exceeds one")
        marks = {}
        for mark in _rows(row["decision_marks"], MAX_SECURITIES, "decision marks"):
            _schema(mark, {"security_id", "price", "available_at_utc"})
            sid = _id(mark["security_id"])
            if sid not in inventory or sid in marks:
                _fail("invalid unique decision mark identity")
            price = None if mark["price"] is None else _number(mark["price"], positive=True, maximum=Fraction(10**12))
            marks[sid] = (price, _optional_clock(mark["available_at_utc"]))
        frames[session_id] = (cutoff, row["cutoff_utc"], weights, marks)
    actions, action_ids = {}, set()
    for row in _rows(corporate_actions, MAX_ACTIONS, "corporate actions"):
        _schema(row, {"action_id", "session_id", "security_id", "kind", "value"})
        action_id, session_id, sid = _id(row["action_id"]), _id(row["session_id"]), _id(row["security_id"])
        kind = row["kind"]
        if (action_id in action_ids or session_id not in session_map or sid not in inventory
                or type(kind) is not str or kind not in ("cash_dividend", "stock_split", "unresolved")):
            _fail("invalid unique corporate action identity or kind")
        action_ids.add(action_id)
        if kind == "unresolved":
            if row["value"] is not None:
                _fail("unresolved action cannot assert an economic value")
            value = None
        else:
            value = _number(row["value"], positive=True, maximum=Fraction(MAX_QUANTITY))
            if kind == "stock_split" and value < Fraction(1, MAX_QUANTITY):
                _fail("split ratio outside bounded share units")
        actions.setdefault(session_id, []).append((action_id, sid, kind, row["value"], value))
    return cash, holdings, parsed_sessions, frames, actions


def _split_quantity(quantity, ratio):
    converted = quantity * ratio
    if converted.denominator != 1:
        _fail("fractional stock split entitlement or order requires admitted cash-in-lieu accounting")
    return _quantity(converted.numerator)


def run_raw_revision_backtest(*, security_inventory, sessions, targets,
                              initial_cash="100000", initial_positions=(), corporate_actions=()):
    """Compute hypothetical day orders on detached, strictly closed primitives.

    Missing valuation means equity is unknown, not zero. An explicit zero target
    can still reduce a priced holding, while quantity-dependent targets refuse
    if the decision portfolio lacks complete pre-cutoff marks. Liquidity missing
    at cutoff leaves even zero exits pending; no liquidation is invented.
    """
    cash, holdings, parsed_sessions, frames, actions = _validate(
        security_inventory, sessions, targets, initial_cash, initial_positions, corporate_actions)
    start_cash, start_positions = _text(cash), _positions(holdings)
    orders, fills, exclusions, results = [], [], [], []
    total_commission = total_slippage = Fraction()
    receivable = Fraction()
    action_results, unresolved = [], set()
    accounting_complete = True
    complete = True
    for session_id, opened, closed, bars in parsed_sessions:
        frame = frames.get(session_id)
        decision_equity = None
        cutoff_text = None
        desired_quantities = {}
        if frame is not None:
            cutoff, cutoff_text, weights, marks = frame
            if any(qty and sid not in weights for sid, qty in holdings.items()):
                _fail("missing explicit prior target")
            decision_prices = {}
            for sid in sorted(set(weights) | {sid for sid, qty in holdings.items() if qty}):
                price, available = marks.get(sid, (None, None))
                if available is not None and available > cutoff:
                    exclusions.append(RawExclusion(session_id, sid, "decision_mark_after_cutoff"))
                    price = None
                elif price is None or available is None:
                    exclusions.append(RawExclusion(session_id, sid, "decision_mark_missing"))
                    price = None
                decision_prices[sid] = price
            for sid in unresolved:
                decision_prices[sid] = None
            # This is the PRIOR-CUTOFF accounting state. Current-open action
            # values cannot fund or alter the frozen decision quantity.
            decision_equity, _ = _marked(cash + receivable, holdings, decision_prices)
            if decision_equity is None:
                complete = False
            for sid, weight in sorted(weights.items()):
                if weight == 0:
                    desired = 0
                elif sid in unresolved:
                    exclusions.append(RawExclusion(session_id, sid, "corporate_action_unresolved"))
                    complete = False
                    continue
                elif decision_equity is None or decision_prices[sid] is None:
                    exclusions.append(RawExclusion(session_id, sid, "incomplete_decision_marks"))
                    complete = False
                    continue
                else:
                    reserve = decision_prices[sid] * (1 + SLIPPAGE) + COMMISSION_PER_SHARE
                    desired = int(weight * decision_equity // reserve)
                    if desired > MAX_QUANTITY:
                        _fail("target quantity exceeds resource bound")
                desired_quantities[sid] = desired
        grouped_actions = {}
        for event in actions.get(session_id, ()):
            grouped_actions.setdefault(event[1], []).append(event)
        split_units = {}
        for sid, events in sorted(grouped_actions.items()):
            kinds = [event[2] for event in events]
            quantity = holdings.get(sid, 0)
            if ("stock_split" in kinds and "cash_dividend" in kinds
                    and (quantity or desired_quantities.get(sid, 0))):
                _fail("simultaneous split/dividend entitlement basis requires ordered source evidence")
            if kinds.count("stock_split") > 1 and (quantity or desired_quantities.get(sid, 0)):
                _fail("simultaneous split entitlement ordering requires source evidence")
            if "unresolved" in kinds:
                unresolved.add(sid)
            for action_id, _, kind, original_value, value in sorted(events, key=lambda item: (item[2], item[0])):
                quantity = holdings.get(sid, 0)
                if sid in unresolved:
                    if quantity:
                        complete, accounting_complete = False, False
                        exclusions.append(RawExclusion(session_id, sid, "corporate_action_unresolved"))
                    action_results.append(RawCorporateAction(action_id, session_id, sid, kind, original_value,
                        quantity, None if quantity else 0, None,
                        "unresolved-held-entitlement" if quantity else "unheld-new-entry-blocked"))
                elif kind == "cash_dividend":
                    entitlement = quantity * value
                    receivable += entitlement
                    action_results.append(RawCorporateAction(action_id, session_id, sid, kind, original_value,
                        quantity, quantity, _text(entitlement), "gross-exdate-receivable-not-cash"))
                else:
                    converted = _split_quantity(quantity, value)
                    if sid in desired_quantities:
                        desired_quantities[sid] = _split_quantity(desired_quantities[sid], value)
                    holdings[sid] = converted
                    split_units[sid] = split_units.get(sid, Fraction(1)) * value
                    action_results.append(RawCorporateAction(action_id, session_id, sid, kind, original_value,
                        quantity, converted, "0", "exact-whole-share-unit-conversion-no-cash-flow"))
        open_prices = {sid: None if sid in unresolved else values[0] for sid, values in bars.items()}
        open_equity, open_unpriced = _marked(cash + receivable, holdings, open_prices)
        if open_unpriced:
            complete = False
            exclusions.extend(RawExclusion(session_id, sid, "held_open_mark_missing") for sid in open_unpriced)
        if frame is not None:
            intended = []
            for sid, desired in sorted(desired_quantities.items()):
                delta = desired - holdings.get(sid, 0)
                if delta:
                    intended.append(("buy" if delta > 0 else "sell", sid, abs(delta)))
            # Sales precede purchases; stable source-ID ordering allocates scarce cash.
            for side, sid, requested in sorted(intended, key=lambda item: (item[0] != "sell", item[1])):
                # Source IDs may contain separators. NUL is excluded by _id,
                # so this three-component content identity cannot be ambiguous.
                order_id = hashlib.sha256((session_id + "\0" + sid + "\0" + side).encode("ascii")).hexdigest()
                open_price, _, volume, volume_at, tradable = bars.get(sid, (None, None, None, None, False))
                reason, filled = "filled", 0
                if sid in unresolved:
                    reason = "corporate_action_unresolved"
                elif open_price is None:
                    reason = "execution_open_missing"
                elif not tradable:
                    reason = "nontradable"
                elif side == "buy" and open_equity is None:
                    reason = "incomplete_open_valuation"
                elif volume is None or volume_at is None:
                    reason = "lagged_capacity_missing"
                elif volume_at > cutoff:
                    reason = "lagged_capacity_after_cutoff"
                else:
                    # The observed lagged bar was in prior-session share units.
                    # A current split converts units mechanically, not liquidity
                    # information or a feature available before the cutoff.
                    capacity = int(volume * split_units.get(sid, Fraction(1)) // 100)
                    unit = open_price * (1 + SLIPPAGE if side == "buy" else 1 - SLIPPAGE)
                    limits = {"lagged_volume_capacity": capacity}
                    if side == "buy":
                        affordable = int(cash // (unit + COMMISSION_PER_SHARE))
                        # Open prices restrict actual risk only; frozen decision
                        # quantities above are never re-sized from future prices.
                        risk_nav, _ = _marked(cash + receivable, holdings, open_prices)
                        if risk_nav is None:
                            _fail("buy risk valuation became unavailable")
                        numerator = MAX_NAME_WEIGHT * risk_nav - holdings.get(sid, 0) * open_price
                        denominator = open_price + MAX_NAME_WEIGHT * (open_price * SLIPPAGE + COMMISSION_PER_SHARE)
                        name_capacity = max(0, int(numerator // denominator))
                        limits["insufficient_cash"] = affordable
                        limits["execution_name_cap"] = name_capacity
                    elif unit < COMMISSION_PER_SHARE:
                        # A legitimate exit can pay its shortfall from existing
                        # cash, but must never create debt or erase the holding.
                        affordable = int(cash // (COMMISSION_PER_SHARE - unit))
                        limits["insufficient_cash_for_commission"] = affordable
                    filled = min(requested, *limits.values())
                    if filled < requested:
                        reason = next(name for name, limit in limits.items() if limit == filled)
                    if filled:
                        notional, fee, slip = filled * unit, filled * COMMISSION_PER_SHARE, filled * open_price * SLIPPAGE
                        if side == "sell":
                            holdings[sid] -= filled
                            cash += notional - fee
                        else:
                            holdings[sid] = holdings.get(sid, 0) + filled
                            cash -= notional + fee
                        total_commission += fee
                        total_slippage += slip
                        fills.append(RawFill(order_id, session_id, sid, side, filled,
                                             _text(open_price), _text(unit), _text(notional), _text(fee), _text(slip)))
                pending = requested - filled
                orders.append(RawOrder(order_id, session_id, sid, side, requested, filled, pending,
                                       "filled" if not pending else "pending-day-only-not-carried", reason))
                if pending:
                    complete = False
                    exclusions.append(RawExclusion(session_id, sid, reason))
        close_prices = {sid: None if sid in unresolved else values[1] for sid, values in bars.items()}
        close_equity, unpriced = _marked(cash + receivable, holdings, close_prices)
        if unpriced:
            complete = False
            exclusions.extend(RawExclusion(session_id, sid, "held_close_mark_missing") for sid in unpriced)
        results.append(RawSessionResult(session_id, cutoff_text,
                                       None if decision_equity is None else _text(decision_equity),
                                       None if open_equity is None else _text(open_equity),
                                       None if close_equity is None else _text(close_equity),
                                       _text(cash), _positions(holdings), unpriced, _text(receivable)))
    return RawBacktestResult(start_cash, start_positions, _text(cash), _positions(holdings),
                             tuple(results), tuple(orders), tuple(fills), tuple(exclusions),
                             _text(total_commission), _text(total_slippage), complete,
                             corporate_actions=tuple(action_results), final_dividend_receivable=_text(receivable),
                             corporate_action_accounting_complete=accounting_complete,
                             unresolved_action_security_ids=tuple(sorted(unresolved)))
