"""Pure, backtest-only order-intent and fill-accounting primitives.

This module deliberately has no QuantConnect, provider, transport, object
store, broker, or network imports.  It turns an already-authorized target
portfolio into deterministic whole-share intents and reduces synthetic/cloud
backtest fill events to aggregate diagnostics.  It cannot submit an order.
"""

import dataclasses
import hashlib
import json
import re
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext


class OrderLevelBacktestError(ValueError):
    """An order-level backtest boundary or exact-arithmetic rule was refused."""


TARGET_GROSS_EXPOSURE = Decimal("0.98")
MODELED_FEE_BPS_PER_SIDE = 10
MODELED_FEE_RATE_PER_SIDE = Decimal(MODELED_FEE_BPS_PER_SIDE) / Decimal(10_000)
PLAN_SCHEMA = "arv2-order-level-rebalance-plan-v1"
SUMMARY_SCHEMA = "arv2-order-level-lifecycle-summary-v2"
SELL = "SELL"
BUY = "BUY"
PARTIALLY_FILLED = "PartiallyFilled"
FILLED = "Filled"
CANCELED = "Canceled"
INVALID = "Invalid"
TERMINAL_STATUSES = frozenset({FILLED, CANCELED, INVALID})
FILL_STATUSES = frozenset({PARTIALLY_FILLED, FILLED})
QC_NUMERIC_ORDER_STATUSES = {
    "0": "New", "1": "Submitted", "2": PARTIALLY_FILLED,
    "3": FILLED, "5": CANCELED, "6": "None", "7": INVALID,
    "8": "CancelPending", "9": "UpdateSubmitted",
}


def require_qc_order_status_enum_members(enum):
    """Bind the documented Python LEAN enum members, not their string forms."""

    try:
        members = (
            (enum.NEW, "New"), (enum.SUBMITTED, "Submitted"),
            (enum.PARTIALLY_FILLED, PARTIALLY_FILLED), (enum.FILLED, FILLED),
            (enum.CANCELED, CANCELED), (enum.NONE, "None"),
            (enum.INVALID, INVALID), (enum.CANCEL_PENDING, "CancelPending"),
            (enum.UPDATE_SUBMITTED, "UpdateSubmitted"),
        )
    except (AttributeError, TypeError) as exc:
        raise OrderLevelBacktestError(
            "QC OrderStatus enum is missing a documented member"
        ) from exc
    if any(type(member) is not type(members[0][0]) for member, _ in members):
        raise OrderLevelBacktestError("QC OrderStatus enum member type changed")
    if any(
        member == prior
        for index, (member, _) in enumerate(members)
        for prior, _ in members[:index]
    ):
        raise OrderLevelBacktestError("QC OrderStatus enum members are aliased")
    return members


def qc_order_status_enum_text(value, members):
    """Compare enum values directly; unknown or differently typed values refuse."""

    if type(value) is not type(members[0][0]):
        return None
    for member, status in members:
        if value == member:
            return status
    return None


def qc_order_status_enum_diagnostic(value):
    """Expose only a bounded type hint, never an arbitrary event value."""

    kind = type(value).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", kind):
        kind = "other"
    return " (type=" + kind + ")"


def qc_order_status_text(value, *, numeric=False):
    """Normalize only the pinned LEAN OrderStatus integer spellings."""

    text = str(value)
    if not numeric:
        return text.rsplit(".", 1)[-1]
    if value is None:
        return ""
    if text.startswith("OrderStatus."):
        text = text[len("OrderStatus."):]
    return QC_NUMERIC_ORDER_STATUSES.get(text, text)


def weekly_decision_axis(
    axis, start_session, cutoff_session, final_session, error_type,
):
    """Select first authenticated session per ISO week and the exact cutoff."""

    if (
        type(axis) is not tuple
        or tuple(sorted(set(axis))) != axis
        or any(type(item) is not str for item in axis)
    ):
        raise error_type("order-level authenticated session axis changed")
    try:
        start = axis.index(start_session)
        cutoff = axis.index(cutoff_session)
        final = axis.index(final_session)
    except ValueError as exc:
        raise error_type(
            "order-level profile escaped the authenticated session axis"
        ) from exc
    if not start < cutoff < final or final != cutoff + 1:
        raise error_type(
            "order-level cutoff lacks its exact next execution session"
        )
    decisions = []
    prior_week = None
    for session in axis[start : cutoff + 1]:
        parsed = datetime.strptime(session, "%Y-%m-%d")
        week = (parsed.isocalendar().year, parsed.isocalendar().week)
        if week != prior_week:
            decisions.append(session)
            prior_week = week
    if decisions[-1] != cutoff_session:
        decisions.append(cutoff_session)
    if tuple(sorted(set(decisions))) != tuple(decisions):
        raise error_type("order-level decision schedule changed")
    return tuple(decisions), start, cutoff, final


def exact_decimal(value, name, error_type, *, positive=False, nonnegative=False):
    """Normalize a QC boundary number before it enters exact order arithmetic."""

    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise error_type(name + " is not decimal") from exc
    if (
        not result.is_finite()
        or (positive and result <= 0)
        or (nonnegative and result < 0)
    ):
        raise error_type(name + " is outside its finite bound")
    return result


def symbol_sid(symbol, name, error_type):
    """Read an exact QC symbol identity without trusting a repr or ticker."""

    try:
        value = str(symbol.id)
    except Exception as exc:
        raise error_type(name + " symbol identity is unreadable") from exc
    if type(value) is not str or not value:
        raise error_type(name + " symbol identity changed")
    return value


def strictly_prior_collection(inventory, cutoff, name, error_type):
    prior = tuple(item for item in inventory if item < cutoff)
    if not prior:
        raise error_type(name + " has no strictly prior collection")
    key = max(prior)
    return key, inventory[key]


def authenticated_session_age(
    positions, observed, decision_session, name, error_type,
):
    if not isinstance(observed, datetime):
        raise error_type(name + " collection time changed type")
    observed_date = observed.date().isoformat()
    try:
        decision_position = positions[decision_session]
    except (KeyError, TypeError) as exc:
        raise error_type(
            name + " collection is outside the authenticated session axis"
        ) from exc
    try:
        observed_position = positions[observed_date]
    except KeyError as exc:
        raise error_type(
            name + " collection is outside the authenticated session axis"
        ) from exc
    age = decision_position - observed_position
    if age < 0:
        raise error_type(name + " collection is after its decision session")
    return age


def aggregate_lifecycle_records(records, submitted_order_count):
    """Aggregate only authenticated lifecycle summaries; retain no order rows."""

    fee = sum((Decimal(row["modeled_fee_amount"]) for row in records), Decimal(0))
    filled_notional = sum(
        (Decimal(row["total_filled_notional"]) for row in records), Decimal(0)
    )
    actual_fee = sum(
        (Decimal(row["actual_engine_fee_amount"]) for row in records),
        Decimal(0),
    )
    target_errors = tuple(Decimal(row["target_weight_l1_error"]) for row in records)
    filled = sum(row["filled_order_count"] for row in records)
    canceled = sum(row["canceled_order_count"] for row in records)
    invalid = sum(row["invalid_order_count"] for row in records)
    mismatch = any(row["fee_mismatch"] for row in records)
    return {
        "digest": _sha256({
            "schema": "arv2-order-level-lifecycle-census-v1",
            "records": records,
        }),
        "fee": fee,
        "filled_notional": filled_notional,
        "actual_fee": actual_fee,
        "filled": filled,
        "canceled": canceled,
        "invalid": invalid,
        "orders_with_any_fill": sum(
            row["orders_with_any_fill_count"] for row in records
        ),
        "mean_target_error": (
            Decimal(0) if not target_errors
            else sum(target_errors, Decimal(0)) / Decimal(len(target_errors))
        ),
        "maximum_target_error": max(target_errors, default=Decimal(0)),
        "execution_failure": (
            canceled != 0 or invalid != 0
            or filled != submitted_order_count or mismatch
        ),
        "fee_mismatch": mismatch,
    }


def require_next_session_preopen(
    *, expected, actual_time, planned_cash, observed_cash,
    planned_quantities, observed_quantities, error_type,
    cash_increase_replan=False,
):
    """Refuse a callback that cannot execute the frozen prior-close plan."""

    if (
        actual_time.date().isoformat() != expected
        or actual_time.hour != 9
        or not 20 <= actual_time.minute <= 27
    ):
        raise error_type(
            "order-level preopen callback missed its exact next session"
        )
    if cash_increase_replan:
        if planned_quantities != observed_quantities:
            raise error_type(
                "order-level overnight holdings changed after the decision"
            )
        if (
            type(planned_cash) is not Decimal
            or not planned_cash.is_finite()
            or planned_cash < 0
            or type(observed_cash) is not Decimal
            or not observed_cash.is_finite()
            or observed_cash < planned_cash
        ):
            raise error_type(
                "order-level overnight cash decreased or is invalid"
            )
        return True if observed_cash != planned_cash else None
    if planned_cash != observed_cash or planned_quantities != observed_quantities:
        raise error_type(
            "order-level overnight account changed after the decision"
        )


def coverage_statistics(records, proxy_mode):
    """Compute the aggregate-only coverage census from frozen decision rows."""

    decimal_fields = (
        "resolved_member_count_ratio",
        "resolved_constituent_weight_ratio",
        "positive_constituent_weight_total",
    ) + (("qqq_proxy_constituent_weight_ratio",) if proxy_mode else ())
    values = {
        name: tuple(Decimal(row[name]) for row in records)
        for name in decimal_fields
    }
    return values, {
        "coverage_decision_count": len(records),
        **{
            name + "_sum": sum(row[name] for row in records)
            for name in (
                "positive_weight_member_count",
                "resolved_positive_weight_member_count",
            )
        },
        **{
            "mean_" + name: _decimal_text(
                sum(values[name], Decimal(0)) / Decimal(len(values[name]))
            )
            for name in decimal_fields
        },
        **{
            "minimum_" + name: _decimal_text(min(values[name]))
            for name in decimal_fields
        },
    }

# Distinct messages are part of the fail-closed surface and each is exercised
# directly by the focused test module.
LIVE_FLAG_TYPE_REFUSAL = "live mode flag must be an exact bool"
LIVE_MODE_REFUSAL = "analyst-revision order runtime is backtest-only"
REBALANCE_ID_REFUSAL = "rebalance id must be a nonempty exact str"
CASH_REFUSAL = "starting cash must be an exact nonnegative finite Decimal"
TARGET_MAP_REFUSAL = "target weights must be a nonempty exact dict"
TARGET_WEIGHT_REFUSAL = "target weights must be exact positive finite Decimals"
TARGET_GROSS_REFUSAL = "target weights must sum exactly to 0.98"
QUANTITY_MAP_REFUSAL = "current quantities must be an exact dict"
QUANTITY_REFUSAL = "current quantities must be exact nonnegative ints"
SECURITY_ID_REFUSAL = "security ids must be nonempty exact strs"
PRICE_MAP_REFUSAL = "reference prices must be an exact dict over the position and target census"
PRICE_REFUSAL = "reference prices must be exact positive finite Decimals"
EQUITY_REFUSAL = "marked starting equity must be strictly positive"
PLAN_TYPE_REFUSAL = "rebalance plan type changed"
PLAN_INTEGRITY_REFUSAL = "rebalance plan integrity check failed"
IDEMPOTENCY_SCOPE_REFUSAL = "registered rebalance id changed"
REBALANCE_REUSE_REFUSAL = "rebalance id was reused for a different plan"
UNREGISTERED_PLAN_REFUSAL = "rebalance plan must be registered before pre-submit"
EVENT_COLLECTION_REFUSAL = "fill events must be an exact tuple"
EVENT_TYPE_REFUSAL = "fill event type changed"
EVENT_ID_REFUSAL = "fill event id must be a nonempty exact str"
EVENT_REBALANCE_REFUSAL = "fill event rebalance id changed"
UNKNOWN_ORDER_REFUSAL = "fill event references an unknown order"
STATUS_REFUSAL = "fill event status is unsupported"
FILL_SHAPE_REFUSAL = "fill quantity and price do not match the event status"
FEE_SHAPE_REFUSAL = (
    "engine fill fee must be an exact nonnegative finite USD Decimal"
)
DUPLICATE_EVENT_REFUSAL = "fill event id was reused with different content"
TERMINAL_EVENT_REFUSAL = "fill event followed a terminal order status"
FILL_OVERRUN_REFUSAL = "cumulative fill quantity exceeds the order quantity"
PARTIAL_STATUS_REFUSAL = "PartiallyFilled cannot complete the order quantity"
FILLED_STATUS_REFUSAL = "Filled must complete the order quantity exactly"
MARGIN_REFUSAL = "filled buy would require margin"
INCOMPLETE_LIFECYCLE_REFUSAL = "every order must have a terminal status"


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _valid_id(value):
    return type(value) is str and bool(value) and value == value.strip()


@dataclasses.dataclass(frozen=True)
class OrderIntent:
    rebalance_id: str
    ordinal: int
    client_order_id: str
    security_id: str
    side: str
    quantity: int
    reference_price: Decimal


@dataclasses.dataclass(frozen=True)
class RebalancePlan:
    rebalance_id: str
    starting_cash: Decimal
    starting_equity: Decimal
    starting_quantities: tuple
    reference_prices: tuple
    target_weights: tuple
    target_quantities: tuple
    intents: tuple
    plan_sha256: str


@dataclasses.dataclass(frozen=True)
class FillEvent:
    event_id: str
    rebalance_id: str
    client_order_id: str
    status: str
    fill_quantity: int
    fill_price: Decimal | None
    engine_fee_amount: Decimal | None = None
    engine_fee_currency: str | None = None


@dataclasses.dataclass(frozen=True)
class OrderLifecycleSummary:
    plan_sha256: str
    rebalance_id_sha256: str
    order_ledger_sha256: str
    intent_count: int
    sell_intent_count: int
    buy_intent_count: int
    fill_event_count: int
    filled_order_count: int
    canceled_order_count: int
    invalid_order_count: int
    orders_with_any_fill_count: int
    buy_filled_notional: Decimal
    sell_filled_notional: Decimal
    total_filled_notional: Decimal
    modeled_fee_amount: Decimal
    actual_engine_fee_amount: Decimal
    actual_engine_fee_effective_bps_per_side: Decimal
    modeled_minus_actual_fee_amount: Decimal
    fee_mismatch: bool
    two_sided_turnover: Decimal
    final_cash: Decimal
    final_gross_exposure: Decimal
    target_weight_l1_error: Decimal

    def to_record(self):
        """Return aggregate-only JSON-safe output with no security identifiers."""

        return {
            "schema": SUMMARY_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "rebalance_id_sha256": self.rebalance_id_sha256,
            "order_ledger_sha256": self.order_ledger_sha256,
            "intent_count": self.intent_count,
            "sell_intent_count": self.sell_intent_count,
            "buy_intent_count": self.buy_intent_count,
            "fill_event_count": self.fill_event_count,
            "filled_order_count": self.filled_order_count,
            "canceled_order_count": self.canceled_order_count,
            "invalid_order_count": self.invalid_order_count,
            "orders_with_any_fill_count": self.orders_with_any_fill_count,
            "fee_bps_per_side": MODELED_FEE_BPS_PER_SIDE,
            "buy_filled_notional": _decimal_text(self.buy_filled_notional),
            "sell_filled_notional": _decimal_text(self.sell_filled_notional),
            "total_filled_notional": _decimal_text(self.total_filled_notional),
            "modeled_fee_amount": _decimal_text(self.modeled_fee_amount),
            "actual_engine_fee_amount": _decimal_text(
                self.actual_engine_fee_amount
            ),
            "actual_engine_fee_effective_bps_per_side": _decimal_text(
                self.actual_engine_fee_effective_bps_per_side
            ),
            "modeled_minus_actual_fee_amount": _decimal_text(
                self.modeled_minus_actual_fee_amount
            ),
            "fee_mismatch": self.fee_mismatch,
            "two_sided_turnover": _decimal_text(self.two_sided_turnover),
            "final_cash": _decimal_text(self.final_cash),
            "final_gross_exposure": _decimal_text(self.final_gross_exposure),
            "target_weight_l1_error": _decimal_text(
                self.target_weight_l1_error
            ),
        }


def validate_backtest_initialize(*, live_mode):
    """Refuse anything except an explicit exact ``False`` live-mode flag."""

    if type(live_mode) is not bool:
        raise OrderLevelBacktestError(LIVE_FLAG_TYPE_REFUSAL)
    if live_mode:
        raise OrderLevelBacktestError(LIVE_MODE_REFUSAL)
    return True


def _validate_security_ids(*mappings):
    if any(
        not _valid_id(security_id)
        for mapping in mappings
        for security_id in mapping
    ):
        raise OrderLevelBacktestError(SECURITY_ID_REFUSAL)


def _intent_record(intent):
    return {
        "rebalance_id": intent.rebalance_id,
        "ordinal": intent.ordinal,
        "client_order_id": intent.client_order_id,
        "security_id": intent.security_id,
        "side": intent.side,
        "quantity": intent.quantity,
        "reference_price": _decimal_text(intent.reference_price),
    }


def _plan_seed(plan):
    return {
        "schema": PLAN_SCHEMA,
        "rebalance_id": plan.rebalance_id,
        "starting_cash": _decimal_text(plan.starting_cash),
        "starting_equity": _decimal_text(plan.starting_equity),
        "starting_quantities": [list(item) for item in plan.starting_quantities],
        "reference_prices": [
            [security_id, _decimal_text(price)]
            for security_id, price in plan.reference_prices
        ],
        "target_weights": [
            [security_id, _decimal_text(weight)]
            for security_id, weight in plan.target_weights
        ],
        "target_quantities": [list(item) for item in plan.target_quantities],
        "intents": [_intent_record(intent) for intent in plan.intents],
    }


def _validate_plan(plan):
    if type(plan) is not RebalancePlan:
        raise OrderLevelBacktestError(PLAN_TYPE_REFUSAL)
    try:
        valid = (
            _valid_id(plan.rebalance_id)
            and type(plan.starting_cash) is Decimal
            and plan.starting_cash.is_finite()
            and type(plan.starting_equity) is Decimal
            and plan.starting_equity.is_finite()
            and plan.starting_equity > 0
            and type(plan.starting_quantities) is tuple
            and type(plan.reference_prices) is tuple
            and type(plan.target_weights) is tuple
            and type(plan.target_quantities) is tuple
            and type(plan.intents) is tuple
            and type(plan.plan_sha256) is str
            and len(plan.plan_sha256) == 64
            and _sha256(_plan_seed(plan)) == plan.plan_sha256
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise OrderLevelBacktestError(PLAN_INTEGRITY_REFUSAL)
    return plan


def plan_rebalance(
    *, rebalance_id, starting_cash, current_quantities, reference_prices,
    target_weights,
):
    """Build sell-first whole-share intents for an exact 98%-gross target."""

    if not _valid_id(rebalance_id):
        raise OrderLevelBacktestError(REBALANCE_ID_REFUSAL)
    if (
        type(starting_cash) is not Decimal
        or not starting_cash.is_finite()
        or starting_cash < 0
    ):
        raise OrderLevelBacktestError(CASH_REFUSAL)
    if type(target_weights) is not dict or not target_weights:
        raise OrderLevelBacktestError(TARGET_MAP_REFUSAL)
    if type(current_quantities) is not dict:
        raise OrderLevelBacktestError(QUANTITY_MAP_REFUSAL)
    if type(reference_prices) is not dict:
        raise OrderLevelBacktestError(PRICE_MAP_REFUSAL)
    _validate_security_ids(
        target_weights, current_quantities, reference_prices
    )
    if any(
        type(weight) is not Decimal
        or not weight.is_finite()
        or weight <= 0
        for weight in target_weights.values()
    ):
        raise OrderLevelBacktestError(TARGET_WEIGHT_REFUSAL)
    if any(
        type(quantity) is not int or quantity < 0
        for quantity in current_quantities.values()
    ):
        raise OrderLevelBacktestError(QUANTITY_REFUSAL)
    census = set(target_weights) | set(current_quantities)
    if set(reference_prices) != census:
        raise OrderLevelBacktestError(PRICE_MAP_REFUSAL)
    if any(
        type(price) is not Decimal
        or not price.is_finite()
        or price <= 0
        for price in reference_prices.values()
    ):
        raise OrderLevelBacktestError(PRICE_REFUSAL)

    with localcontext() as context:
        context.prec = 80
        target_total = sum(target_weights.values(), Decimal(0))
        if target_total != TARGET_GROSS_EXPOSURE:
            raise OrderLevelBacktestError(TARGET_GROSS_REFUSAL)
        equity = starting_cash + sum(
            Decimal(current_quantities.get(security_id, 0)) * price
            for security_id, price in reference_prices.items()
        )
        if equity <= 0:
            raise OrderLevelBacktestError(EQUITY_REFUSAL)
        target_quantities = {
            security_id: int(
                (equity * target_weights.get(security_id, Decimal(0)) / price)
                .to_integral_value(rounding=ROUND_FLOOR)
            )
            for security_id, price in reference_prices.items()
        }

    deltas = {
        security_id: target_quantities[security_id]
        - current_quantities.get(security_id, 0)
        for security_id in sorted(census)
    }
    intent_rows = [
        (security_id, SELL, -deltas[security_id])
        for security_id in sorted(census)
        if deltas[security_id] < 0
    ] + [
        (security_id, BUY, deltas[security_id])
        for security_id in sorted(census)
        if deltas[security_id] > 0
    ]
    intents = []
    for ordinal, (security_id, side, quantity) in enumerate(intent_rows, 1):
        client_order_id = _sha256(
            {
                "schema": "arv2-order-level-client-order-id-v1",
                "rebalance_id": rebalance_id,
                "ordinal": ordinal,
                "security_id": security_id,
                "side": side,
                "quantity": quantity,
            }
        )
        intents.append(
            OrderIntent(
                rebalance_id=rebalance_id,
                ordinal=ordinal,
                client_order_id=client_order_id,
                security_id=security_id,
                side=side,
                quantity=quantity,
                reference_price=reference_prices[security_id],
            )
        )
    seed = RebalancePlan(
        rebalance_id=rebalance_id,
        starting_cash=starting_cash,
        starting_equity=equity,
        starting_quantities=tuple(sorted(current_quantities.items())),
        reference_prices=tuple(sorted(reference_prices.items())),
        target_weights=tuple(sorted(target_weights.items())),
        target_quantities=tuple(sorted(target_quantities.items())),
        intents=tuple(intents),
        plan_sha256="",
    )
    plan = dataclasses.replace(seed, plan_sha256=_sha256(_plan_seed(seed)))
    return _validate_plan(plan)


def register_idempotent_rebalance(candidate, *, existing_plan=None):
    """Register once, or return the byte-equivalent plan on an exact retry."""

    candidate = _validate_plan(candidate)
    if existing_plan is None:
        return candidate
    existing_plan = _validate_plan(existing_plan)
    if candidate.rebalance_id != existing_plan.rebalance_id:
        raise OrderLevelBacktestError(IDEMPOTENCY_SCOPE_REFUSAL)
    if candidate != existing_plan or candidate.plan_sha256 != existing_plan.plan_sha256:
        raise OrderLevelBacktestError(REBALANCE_REUSE_REFUSAL)
    return existing_plan


def validate_backtest_pre_submit(
    *, live_mode, candidate_plan, registered_plan,
):
    """Recheck backtest-only mode and exact idempotent plan before submission."""

    validate_backtest_initialize(live_mode=live_mode)
    if registered_plan is None:
        raise OrderLevelBacktestError(UNREGISTERED_PLAN_REFUSAL)
    return register_idempotent_rebalance(
        candidate_plan, existing_plan=registered_plan
    )


def _validate_event(event):
    if type(event) is not FillEvent:
        raise OrderLevelBacktestError(EVENT_TYPE_REFUSAL)
    if not _valid_id(event.event_id):
        raise OrderLevelBacktestError(EVENT_ID_REFUSAL)
    if not _valid_id(event.rebalance_id):
        raise OrderLevelBacktestError(EVENT_REBALANCE_REFUSAL)
    if not _valid_id(event.client_order_id):
        raise OrderLevelBacktestError(UNKNOWN_ORDER_REFUSAL)
    if (
        type(event.status) is not str
        or event.status not in FILL_STATUSES | TERMINAL_STATUSES
    ):
        raise OrderLevelBacktestError(STATUS_REFUSAL)
    fill_shape_ok = (
        event.status in FILL_STATUSES
        and type(event.fill_quantity) is int
        and event.fill_quantity > 0
        and type(event.fill_price) is Decimal
        and event.fill_price.is_finite()
        and event.fill_price > 0
    ) or (
        event.status in {CANCELED, INVALID}
        and type(event.fill_quantity) is int
        and event.fill_quantity == 0
        and event.fill_price is None
    )
    if not fill_shape_ok:
        raise OrderLevelBacktestError(FILL_SHAPE_REFUSAL)
    fee_shape_ok = (
        event.status in FILL_STATUSES
        and type(event.engine_fee_amount) is Decimal
        and event.engine_fee_amount.is_finite()
        and event.engine_fee_amount >= 0
        and type(event.engine_fee_currency) is str
        and event.engine_fee_currency == "USD"
    ) or (
        event.status in {CANCELED, INVALID}
        and event.engine_fee_amount is None
        and event.engine_fee_currency is None
    )
    if not fee_shape_ok:
        raise OrderLevelBacktestError(FEE_SHAPE_REFUSAL)
    return event


def summarize_order_lifecycle(plan, events, *, require_all_terminal=True):
    """Aggregate an idempotent fill stream without exposing security ids."""

    plan = _validate_plan(plan)
    if type(events) is not tuple:
        raise OrderLevelBacktestError(EVENT_COLLECTION_REFUSAL)
    if type(require_all_terminal) is not bool:
        raise OrderLevelBacktestError(INCOMPLETE_LIFECYCLE_REFUSAL)
    intents = {intent.client_order_id: intent for intent in plan.intents}
    state = {
        client_order_id: {"filled": 0, "status": None}
        for client_order_id in intents
    }
    quantities = dict(plan.starting_quantities)
    prices = dict(plan.reference_prices)
    target_weights = dict(plan.target_weights)
    cash = plan.starting_cash
    buy_notional = Decimal(0)
    sell_notional = Decimal(0)
    modeled_fee_total = Decimal(0)
    actual_fee_total = Decimal(0)
    fee_mismatch_seen = False
    seen_events = {}
    accepted_events = []

    with localcontext() as context:
        context.prec = 80
        for raw_event in events:
            event = _validate_event(raw_event)
            prior = seen_events.get(event.event_id)
            if prior is not None:
                if prior != event:
                    raise OrderLevelBacktestError(DUPLICATE_EVENT_REFUSAL)
                continue
            seen_events[event.event_id] = event
            if event.rebalance_id != plan.rebalance_id:
                raise OrderLevelBacktestError(EVENT_REBALANCE_REFUSAL)
            intent = intents.get(event.client_order_id)
            if intent is None:
                raise OrderLevelBacktestError(UNKNOWN_ORDER_REFUSAL)
            order_state = state[event.client_order_id]
            if order_state["status"] in TERMINAL_STATUSES:
                raise OrderLevelBacktestError(TERMINAL_EVENT_REFUSAL)
            cumulative = order_state["filled"] + event.fill_quantity
            if cumulative > intent.quantity:
                raise OrderLevelBacktestError(FILL_OVERRUN_REFUSAL)
            if event.status == PARTIALLY_FILLED and cumulative >= intent.quantity:
                raise OrderLevelBacktestError(PARTIAL_STATUS_REFUSAL)
            if event.status == FILLED and cumulative != intent.quantity:
                raise OrderLevelBacktestError(FILLED_STATUS_REFUSAL)

            if event.fill_quantity:
                notional = Decimal(event.fill_quantity) * event.fill_price
                modeled_fee = notional * MODELED_FEE_RATE_PER_SIDE
                actual_fee = event.engine_fee_amount
                fee_mismatch_seen = (
                    fee_mismatch_seen or actual_fee != modeled_fee
                )
                if intent.side == SELL:
                    quantities[intent.security_id] -= event.fill_quantity
                    cash += notional - actual_fee
                    sell_notional += notional
                else:
                    proposed_cash = cash - notional - actual_fee
                    if proposed_cash < 0:
                        raise OrderLevelBacktestError(MARGIN_REFUSAL)
                    quantities[intent.security_id] = (
                        quantities.get(intent.security_id, 0)
                        + event.fill_quantity
                    )
                    cash = proposed_cash
                    buy_notional += notional
                modeled_fee_total += modeled_fee
                actual_fee_total += actual_fee
            order_state["filled"] = cumulative
            order_state["status"] = event.status
            accepted_events.append(event)

        if require_all_terminal and any(
            order_state["status"] not in TERMINAL_STATUSES
            for order_state in state.values()
        ):
            raise OrderLevelBacktestError(INCOMPLETE_LIFECYCLE_REFUSAL)

        final_equity = cash + sum(
            Decimal(quantities.get(security_id, 0)) * price
            for security_id, price in prices.items()
        )
        actual_weights = {
            security_id: (
                Decimal(quantities.get(security_id, 0)) * price / final_equity
            )
            for security_id, price in prices.items()
        }
        target_error = sum(
            abs(actual_weights.get(security_id, Decimal(0)) - weight)
            for security_id, weight in target_weights.items()
        ) + sum(
            abs(actual_weights[security_id])
            for security_id in actual_weights
            if security_id not in target_weights
        )
        target_error += abs(
            cash / final_equity - (Decimal(1) - TARGET_GROSS_EXPOSURE)
        )
        final_gross = sum(actual_weights.values(), Decimal(0))
        total_notional = buy_notional + sell_notional
        actual_fee_effective_bps = (
            Decimal(0)
            if total_notional == 0
            else actual_fee_total / total_notional * Decimal(10_000)
        )

    terminal_counts = {
        status: sum(item["status"] == status for item in state.values())
        for status in TERMINAL_STATUSES
    }
    event_records = [
        {
            "event_id": event.event_id,
            "client_order_id": event.client_order_id,
            "status": event.status,
            "fill_quantity": event.fill_quantity,
            "fill_price": (
                None
                if event.fill_price is None
                else _decimal_text(event.fill_price)
            ),
            "engine_fee_amount": (
                None
                if event.engine_fee_amount is None
                else _decimal_text(event.engine_fee_amount)
            ),
            "engine_fee_currency": event.engine_fee_currency,
        }
        for event in accepted_events
    ]
    ledger_sha256 = _sha256(
        {
            "schema": "arv2-order-level-ledger-v1",
            "plan_sha256": plan.plan_sha256,
            "events": event_records,
        }
    )
    return OrderLifecycleSummary(
        plan_sha256=plan.plan_sha256,
        rebalance_id_sha256=hashlib.sha256(
            plan.rebalance_id.encode("utf-8")
        ).hexdigest(),
        order_ledger_sha256=ledger_sha256,
        intent_count=len(plan.intents),
        sell_intent_count=sum(intent.side == SELL for intent in plan.intents),
        buy_intent_count=sum(intent.side == BUY for intent in plan.intents),
        fill_event_count=len(accepted_events),
        filled_order_count=terminal_counts[FILLED],
        canceled_order_count=terminal_counts[CANCELED],
        invalid_order_count=terminal_counts[INVALID],
        orders_with_any_fill_count=sum(item["filled"] > 0 for item in state.values()),
        buy_filled_notional=buy_notional,
        sell_filled_notional=sell_notional,
        total_filled_notional=total_notional,
        modeled_fee_amount=modeled_fee_total,
        actual_engine_fee_amount=actual_fee_total,
        actual_engine_fee_effective_bps_per_side=(
            actual_fee_effective_bps
        ),
        modeled_minus_actual_fee_amount=(
            modeled_fee_total - actual_fee_total
        ),
        fee_mismatch=fee_mismatch_seen,
        two_sided_turnover=total_notional / plan.starting_equity,
        final_cash=cash,
        final_gross_exposure=final_gross,
        target_weight_l1_error=target_error,
    )
