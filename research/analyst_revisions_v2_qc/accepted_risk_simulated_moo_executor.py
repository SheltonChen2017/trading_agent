"""Universe-neutral, backtest-only simulated MOO execution helper.

The helper deliberately owns no strategy, universe, scoring, provider,
QuantConnect-project, or result-transport semantics.  A caller supplies one
already-authorized 98%-gross target and narrow callbacks for account reads,
security resolution, and simulated ``MarketOnOpenOrder`` submission.  The
existing pure order core remains authoritative for whole-share planning,
idempotency, fill accounting, and lifecycle aggregation.

Unknown order events never disappear silently.  A caller that needs to
compose an external event source such as the separately audited forced-
delisting ledger must supply a strict hook which returns a SHA-256 receipt.
The executor records only that receipt and bounded event identity hashes.
"""

import dataclasses
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

try:
    import accepted_risk_order_level_core as _orders
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_core as _orders,
    )


class SimulatedMooExecutorError(ValueError):
    """A callback, account boundary, order event, or lifecycle was refused."""


SUMMARY_SCHEMA = "arv2-simulated-moo-executor-summary-v1"
STATE_SCHEMA = "arv2-simulated-moo-executor-state-v1"
PLAN_PATH_SCHEMA = "arv2-simulated-moo-executor-plan-path-v1"
DRIFT_PATH_SCHEMA = "arv2-simulated-moo-executor-drift-path-v1"
EXTERNAL_EVENT_PATH_SCHEMA = (
    "arv2-simulated-moo-executor-external-event-path-v1"
)
CORPORATE_ACTION_REPLAN_PATH_SCHEMA = (
    "arv2-simulated-moo-executor-corporate-action-replan-path-v1"
)
MAX_SYNCHRONOUS_ORDER_EVENTS = 64

PREOPEN_NO_PENDING = "NO_PENDING"
PREOPEN_NOT_DUE = "NOT_DUE"
PREOPEN_SUBMITTED = "SUBMITTED"
PREOPEN_DRIFT_SKIPPED = "DRIFT_SKIPPED"

_IGNORED_ORDER_STATUSES = frozenset({
    "New",
    "Submitted",
    "None",
    "CancelPending",
    "UpdateSubmitted",
})
_EXPECTED_REFLECTED_STATUS_NUMBERS = (
    ("New", 0),
    ("Submitted", 1),
    (_orders.PARTIALLY_FILLED, 2),
    (_orders.FILLED, 3),
    (_orders.CANCELED, 5),
    ("None", 6),
    (_orders.INVALID, 7),
    ("CancelPending", 8),
    ("UpdateSubmitted", 9),
)


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SimulatedMooExecutorError(
            "simulated MOO value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _is_sha256(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _decimal_text(value):
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _decimal(value, name, *, positive=False, nonnegative=False):
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SimulatedMooExecutorError(name + " is not decimal") from exc
    if (
        not result.is_finite()
        or (positive and result <= 0)
        or (nonnegative and result < 0)
    ):
        raise SimulatedMooExecutorError(name + " is outside its finite bound")
    return result


def _nonempty_text(value, name):
    if type(value) is not str or not value or value.strip() != value:
        raise SimulatedMooExecutorError(name + " must be exact nonempty text")
    return value


def _exact_callbacks(values):
    for name, callback in values.items():
        if not callable(callback):
            raise SimulatedMooExecutorError(name + " callback is unavailable")


def _quantity(value, name, *, planning):
    """Normalize long-only plans and finite preopen census observations."""

    if type(value) is int:
        if planning and value < 0:
            raise SimulatedMooExecutorError(name + " is negative")
        return value
    if not planning and type(value) is Decimal and value.is_finite():
        integral = value.to_integral_value()
        return int(integral) if value == integral else value
    raise SimulatedMooExecutorError(
        name
        + (
            " must be an exact nonnegative int"
            if planning
            else " must be an exact finite int or Decimal"
        )
    )


def _reflected_members(order_status_enum, order_status_to_int):
    try:
        members = _orders.require_qc_order_status_enum_members(order_status_enum)
    except _orders.OrderLevelBacktestError as exc:
        raise SimulatedMooExecutorError(str(exc)) from exc
    if not callable(order_status_to_int):
        raise SimulatedMooExecutorError(
            "reflected OrderStatus numeric callback is unavailable"
        )
    observed = []
    for (member, name), (expected_name, expected_number) in zip(
        members, _EXPECTED_REFLECTED_STATUS_NUMBERS, strict=True
    ):
        try:
            number = order_status_to_int(member)
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "reflected OrderStatus numeric value is unreadable"
            ) from exc
        if name != expected_name or type(number) is not int:
            raise SimulatedMooExecutorError(
                "reflected OrderStatus map changed"
            )
        observed.append((name, number))
        if number != expected_number:
            raise SimulatedMooExecutorError(
                "reflected OrderStatus map changed"
            )
    if tuple(observed) != _EXPECTED_REFLECTED_STATUS_NUMBERS:
        raise SimulatedMooExecutorError("reflected OrderStatus map changed")
    return members


@dataclasses.dataclass(frozen=True, slots=True)
class _PendingPlan:
    decision_session: str
    execution_session: str
    plan: _orders.RebalancePlan


class SimulatedMooExecutor:
    """Submit and summarize one sequence of simulated MOO rebalances."""

    def __init__(
        self,
        *,
        current_live_mode,
        order_status_enum,
        order_status_to_int,
        security_for_id,
        current_quantity,
        current_holding_census,
        current_cash,
        submit_market_on_open,
        external_order_event_handler=None,
        holding_drift_replan=None,
    ):
        if not callable(current_live_mode):
            raise SimulatedMooExecutorError(
                "current live-mode callback is unavailable"
            )
        try:
            initial_live_mode = current_live_mode()
            _orders.validate_backtest_initialize(live_mode=initial_live_mode)
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "current live-mode callback failed"
            ) from exc
        _exact_callbacks({
            "security resolver": security_for_id,
            "current quantity": current_quantity,
            "complete holding census": current_holding_census,
            "current cash": current_cash,
            "MOO submission": submit_market_on_open,
        })
        if (
            external_order_event_handler is not None
            and not callable(external_order_event_handler)
        ):
            raise SimulatedMooExecutorError(
                "external order-event handler must be callable or None"
            )
        if holding_drift_replan is not None and not callable(
            holding_drift_replan
        ):
            raise SimulatedMooExecutorError(
                "holding-drift replan callback must be callable or None"
            )
        self._status_members = _reflected_members(
            order_status_enum, order_status_to_int
        )
        self._current_live_mode = current_live_mode
        self._security_for_id = security_for_id
        self._current_quantity = current_quantity
        self._current_holding_census = current_holding_census
        self._current_cash = current_cash
        self._submit_market_on_open = submit_market_on_open
        self._external_order_event_handler = external_order_event_handler
        self._holding_drift_replan = holding_drift_replan

        self._terminal = False
        self._terminal_result = None
        self._pending = None
        self._open_plan = None
        self._open_plan_events = []
        self._open_order_ids = {}
        self._pending_submission_events = None
        self._pending_submission_event_keys = None
        self._submitted_preopen_sessions = set()
        self._lifecycle_records = []
        self._plan_sha256s = []
        self._submitted_plan_sha256s = []
        self._drift_records = []
        self._external_event_records = []
        self._corporate_action_replan_records = []
        self._decision_count = 0
        self._submitted_rebalance_count = 0
        self._submitted_order_count = 0

    @property
    def pending_execution_session(self):
        return None if self._pending is None else self._pending.execution_session

    @property
    def has_open_rebalance(self):
        return self._open_plan is not None

    def _require_active(self):
        if self._terminal:
            raise SimulatedMooExecutorError(
                "simulated MOO executor is already terminal"
            )

    def _status_text(self, value):
        result = _orders.qc_order_status_enum_text(value, self._status_members)
        if result is None:
            raise SimulatedMooExecutorError(
                "simulated MOO event status is unsupported"
                + _orders.qc_order_status_enum_diagnostic(value)
            )
        return result

    def _read_cash(self):
        try:
            value = self._current_cash()
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "current cash callback failed"
            ) from exc
        return _decimal(value, "current cash", nonnegative=True)

    def _read_census(self, *, planning):
        try:
            raw = self._current_holding_census()
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "complete holding census callback failed"
            ) from exc
        if type(raw) is not dict:
            raise SimulatedMooExecutorError(
                "complete holding census must be an exact dict"
            )
        result = {}
        for security_id, raw_quantity in raw.items():
            _nonempty_text(security_id, "holding security id")
            quantity = _quantity(
                raw_quantity,
                "holding quantity",
                planning=planning,
            )
            if quantity == 0:
                raise SimulatedMooExecutorError(
                    "complete holding census contains a zero quantity"
                )
            result[security_id] = quantity
        return result

    def _read_quantity(self, security_id, *, planning):
        try:
            raw = self._current_quantity(security_id)
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "current quantity callback failed"
            ) from exc
        return _quantity(raw, "current quantity", planning=planning)

    def _consistent_quantities(self, target_ids, *, planning):
        census = self._read_census(planning=planning)
        observed = {}
        for security_id in sorted(set(census) | set(target_ids)):
            quantity = self._read_quantity(security_id, planning=planning)
            expected = census.get(security_id, 0)
            if quantity != expected:
                raise SimulatedMooExecutorError(
                    "current quantity disagrees with complete holding census"
                )
            if quantity != 0:
                observed[security_id] = quantity
        return observed

    def prepare_rebalance(
        self,
        *,
        decision_session,
        execution_session,
        target_weights,
        reference_prices,
    ):
        """Freeze one prior-close plan for its exact next-session preopen."""

        self._require_active()
        decision_session = _nonempty_text(
            decision_session, "decision session"
        )
        execution_session = _nonempty_text(
            execution_session, "execution session"
        )
        try:
            decision_date = datetime.strptime(
                decision_session, "%Y-%m-%d"
            ).date()
            execution_date = datetime.strptime(
                execution_session, "%Y-%m-%d"
            ).date()
        except ValueError as exc:
            raise SimulatedMooExecutorError(
                "decision or execution session is not an ISO date"
            ) from exc
        if execution_date <= decision_date:
            raise SimulatedMooExecutorError(
                "execution session must follow its decision session"
            )
        if self._pending is not None:
            raise SimulatedMooExecutorError(
                "simulated MOO executor already has a pending plan"
            )
        self.close_open_rebalance()
        if type(target_weights) is not dict:
            raise SimulatedMooExecutorError(
                "target weights must be an exact dict"
            )
        target_ids = tuple(target_weights)
        for security_id in target_ids:
            _nonempty_text(security_id, "target security id")
        quantities = self._consistent_quantities(target_ids, planning=True)
        try:
            plan = _orders.plan_rebalance(
                rebalance_id="arv2-simulated-moo-" + decision_session,
                starting_cash=self._read_cash(),
                current_quantities=quantities,
                reference_prices=reference_prices,
                target_weights=target_weights,
            )
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        self._pending = _PendingPlan(
            decision_session=decision_session,
            execution_session=execution_session,
            plan=plan,
        )
        self._decision_count += 1
        self._plan_sha256s.append(plan.plan_sha256)
        return plan

    def lifecycle_state(self):
        """Return bounded account-independent orchestration state."""

        result = {
            "schema": STATE_SCHEMA,
            "terminal": self._terminal,
            "decision_count": self._decision_count,
            "submitted_rebalance_count": self._submitted_rebalance_count,
            "completed_rebalance_count": len(self._lifecycle_records),
            "holding_drift_skipped_rebalance_count": len(
                self._drift_records
            ),
            "submitted_order_count": self._submitted_order_count,
            "pending_execution_session": self.pending_execution_session,
            "open_rebalance": self.has_open_rebalance,
            "external_order_event_count": len(
                self._external_event_records
            ),
        }
        return json.loads(_canonical(result).decode("ascii"))

    def _record_drift_skip(self, pending, observed):
        expected = dict(pending.plan.starting_quantities)
        changed = tuple(
            sorted(
                security_id
                for security_id in set(expected) | set(observed)
                if expected.get(security_id, 0)
                != observed.get(security_id, 0)
            )
        )
        if not changed:
            raise SimulatedMooExecutorError(
                "holding-drift skip lacks a changed security"
            )
        self._drift_records.append({
            "decision_session": pending.decision_session,
            "execution_session": pending.execution_session,
            "plan_sha256": pending.plan.plan_sha256,
            "changed_security_count": len(changed),
            "changed_security_path_sha256": _sha({
                "schema": "arv2-simulated-moo-drifted-security-path-v1",
                "security_id_sha256s": [
                    hashlib.sha256(item.encode("utf-8")).hexdigest()
                    for item in changed
                ],
            }),
        })

    def _authorized_holding_drift_replan(
        self, pending, observed_cash, observed, actual_time
    ):
        if self._holding_drift_replan is None:
            return None
        try:
            result = self._holding_drift_replan(
                pending.plan,
                observed_cash,
                dict(observed),
                actual_time,
            )
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "holding-drift replan callback failed"
            ) from exc
        if result is None:
            return None
        if type(result) is not dict or set(result) != {
            "reference_prices",
            "receipt_sha256",
        }:
            raise SimulatedMooExecutorError(
                "holding-drift replan callback returned an invalid receipt"
            )
        receipt = result["receipt_sha256"]
        prices = result["reference_prices"]
        if not _is_sha256(receipt) or type(prices) is not dict:
            raise SimulatedMooExecutorError(
                "holding-drift replan callback returned an invalid receipt"
            )
        try:
            replanned = _orders.plan_rebalance(
                rebalance_id=pending.plan.rebalance_id,
                starting_cash=observed_cash,
                current_quantities=observed,
                reference_prices=prices,
                target_weights=dict(pending.plan.target_weights),
            )
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        self._corporate_action_replan_records.append({
            "execution_session": pending.execution_session,
            "prior_plan_sha256": pending.plan.plan_sha256,
            "replanned_plan_sha256": replanned.plan_sha256,
            "authority_receipt_sha256": receipt,
        })
        return replanned

    def on_preopen(self, actual_time):
        """Validate and submit the frozen plan, or count complete-census drift."""

        self._require_active()
        if not isinstance(actual_time, datetime):
            raise SimulatedMooExecutorError(
                "preopen callback time must be a datetime"
            )
        if self._pending is None:
            return PREOPEN_NO_PENDING
        pending = self._pending
        observed_session = actual_time.date().isoformat()
        if observed_session < pending.execution_session:
            return PREOPEN_NOT_DUE
        if observed_session in self._submitted_preopen_sessions:
            raise SimulatedMooExecutorError(
                "simulated MOO preopen submission was duplicated"
            )

        observed_cash = self._read_cash()
        target_ids = set(dict(pending.plan.target_quantities))
        observed = self._consistent_quantities(target_ids, planning=False)
        expected = dict(pending.plan.starting_quantities)

        # Use the core clock guard even on the counted-drift path.  Supplying
        # the frozen account to this one call isolates clock validation from
        # the separately declared no-order drift disposition.
        try:
            _orders.require_next_session_preopen(
                expected=pending.execution_session,
                actual_time=actual_time,
                planned_cash=pending.plan.starting_cash,
                observed_cash=pending.plan.starting_cash,
                planned_quantities=expected,
                observed_quantities=expected,
                error_type=SimulatedMooExecutorError,
                cash_increase_replan=False,
            )
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc

        self._pending = None
        self._submitted_preopen_sessions.add(observed_session)
        if observed != expected:
            replanned = self._authorized_holding_drift_replan(
                pending,
                observed_cash,
                observed,
                actual_time,
            )
            if replanned is None:
                self._record_drift_skip(pending, observed)
                return PREOPEN_DRIFT_SKIPPED
            pending = _PendingPlan(
                pending.decision_session,
                pending.execution_session,
                replanned,
            )
            expected = observed

        try:
            replan = _orders.require_next_session_preopen(
                expected=pending.execution_session,
                actual_time=actual_time,
                planned_cash=pending.plan.starting_cash,
                observed_cash=observed_cash,
                planned_quantities=expected,
                observed_quantities=observed,
                error_type=SimulatedMooExecutorError,
                cash_increase_replan=True,
            )
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        plan = pending.plan
        if replan:
            try:
                plan = _orders.plan_rebalance(
                    rebalance_id=plan.rebalance_id,
                    starting_cash=observed_cash,
                    current_quantities=observed,
                    reference_prices=dict(plan.reference_prices),
                    target_weights=dict(plan.target_weights),
                )
            except _orders.OrderLevelBacktestError as exc:
                raise SimulatedMooExecutorError(str(exc)) from exc
        self._submit_plan(plan)
        self._submitted_rebalance_count += 1
        return PREOPEN_SUBMITTED

    def _submit_plan(self, plan):
        try:
            registered = _orders.register_idempotent_rebalance(plan)
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        self._open_plan = registered
        self._submitted_plan_sha256s.append(registered.plan_sha256)
        self._open_plan_events = []
        self._open_order_ids = {}
        if not registered.intents:
            self.close_open_rebalance()
            return
        for intent in registered.intents:
            try:
                live_mode = self._current_live_mode()
                _orders.validate_backtest_pre_submit(
                    live_mode=live_mode,
                    candidate_plan=plan,
                    registered_plan=registered,
                )
            except _orders.OrderLevelBacktestError as exc:
                raise SimulatedMooExecutorError(str(exc)) from exc
            except Exception as exc:
                raise SimulatedMooExecutorError(
                    "current live-mode callback failed"
                ) from exc
            try:
                symbol = self._security_for_id(intent.security_id)
            except Exception as exc:
                raise SimulatedMooExecutorError(
                    "security resolution callback failed"
                ) from exc
            if symbol is None:
                raise SimulatedMooExecutorError(
                    "simulated MOO intent lost its security resolution"
                )
            signed_quantity = (
                -intent.quantity
                if intent.side == _orders.SELL
                else intent.quantity
            )
            if self._pending_submission_events is not None:
                raise SimulatedMooExecutorError(
                    "nested simulated MOO submission is unsupported"
                )
            self._pending_submission_events = []
            self._pending_submission_event_keys = set()
            staged = ()
            try:
                ticket = self._submit_market_on_open(
                    symbol, signed_quantity, intent.client_order_id
                )
                try:
                    order_id = ticket.order_id
                except Exception as exc:
                    raise SimulatedMooExecutorError(
                        "simulated MOO ticket is unreadable"
                    ) from exc
                if (
                    type(order_id) is not int
                    or order_id < 0
                    or order_id in self._open_order_ids
                ):
                    raise SimulatedMooExecutorError(
                        "simulated MOO ticket identity changed"
                    )
                if any(
                    row[0] != order_id
                    for row in self._pending_submission_events
                ):
                    raise SimulatedMooExecutorError(
                        "synchronous event does not match returned MOO ticket"
                    )
                self._open_order_ids[order_id] = intent
                self._submitted_order_count += 1
                staged = tuple(self._pending_submission_events)
            finally:
                self._pending_submission_events = None
                self._pending_submission_event_keys = None
            for staged_order_id, staged_event_id, staged_status, event, engine_order in staged:
                if (
                    event.order_id != staged_order_id
                    or str(event.id) != staged_event_id
                    or self._status_text(event.status) != staged_status
                ):
                    raise SimulatedMooExecutorError(
                        "synchronous event changed before replay"
                    )
                self.on_order_event(event, engine_order=engine_order)

    def _external_event(self, event, engine_order, status):
        if self._external_order_event_handler is None:
            raise SimulatedMooExecutorError(
                "external order event has no strict handler"
            )
        try:
            receipt_sha256 = self._external_order_event_handler(
                event, engine_order, status
            )
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "external order-event handler failed"
            ) from exc
        if not _is_sha256(receipt_sha256):
            raise SimulatedMooExecutorError(
                "external order-event handler returned no exact SHA-256 receipt"
            )
        self._external_event_records.append({
            "order_id_sha256": _sha_text(event.order_id),
            "event_id_sha256": _sha_text(event.id),
            "status": status,
            "handler_receipt_sha256": receipt_sha256,
        })

    def on_order_event(self, event, *, engine_order=None):
        """Accept one reflected QC event or route it to the strict hook."""

        self._require_active()
        try:
            order_id = event.order_id
            event_id = event.id
            status = self._status_text(event.status)
        except SimulatedMooExecutorError:
            raise
        except Exception as exc:
            raise SimulatedMooExecutorError(
                "simulated MOO event is unreadable"
            ) from exc
        if type(order_id) is not int or order_id < 0:
            raise SimulatedMooExecutorError(
                "simulated MOO event order identity changed"
            )
        if type(event_id) not in (int, str) or str(event_id) == "":
            raise SimulatedMooExecutorError(
                "simulated MOO event identity changed"
            )
        key = (order_id, str(event_id))
        if self._pending_submission_events is not None:
            if key in self._pending_submission_event_keys:
                raise SimulatedMooExecutorError(
                    "duplicate synchronous simulated MOO event"
                )
            if (
                len(self._pending_submission_events)
                >= MAX_SYNCHRONOUS_ORDER_EVENTS
            ):
                raise SimulatedMooExecutorError(
                    "synchronous simulated MOO event buffer exceeded"
                )
            self._pending_submission_event_keys.add(key)
            self._pending_submission_events.append(
                (order_id, str(event_id), status, event, engine_order)
            )
            return

        intent = self._open_order_ids.get(order_id)
        if self._open_plan is None or intent is None:
            self._external_event(event, engine_order, status)
            return
        if status in _IGNORED_ORDER_STATUSES:
            return
        if status in _orders.FILL_STATUSES:
            signed_quantity = _decimal(
                event.fill_quantity,
                "signed fill quantity",
            )
            if (
                (intent.side == _orders.SELL and signed_quantity >= 0)
                or (intent.side == _orders.BUY and signed_quantity <= 0)
            ):
                raise SimulatedMooExecutorError(
                    "fill quantity sign disagrees with order side"
                )
            absolute = abs(signed_quantity)
            integral = absolute.to_integral_value()
            if absolute != integral or integral <= 0:
                raise SimulatedMooExecutorError(
                    "fill quantity is not a positive whole share"
                )
            fill_quantity = int(integral)
            fill_price = _decimal(
                event.fill_price, "fill price", positive=True
            )
            try:
                fee = event.order_fee.value
                fee_amount = fee.amount
                fee_currency = fee.currency
            except AttributeError as exc:
                raise SimulatedMooExecutorError(
                    "simulated MOO fill fee is unreadable"
                ) from exc
            engine_fee_amount = _decimal(
                fee_amount, "simulated MOO fill fee", nonnegative=True
            )
            if type(fee_currency) is not str or fee_currency != "USD":
                raise SimulatedMooExecutorError(
                    "simulated MOO fill fee is not exact USD"
                )
        elif status in {_orders.CANCELED, _orders.INVALID}:
            fill_quantity = 0
            fill_price = None
            engine_fee_amount = None
            fee_currency = None
        else:
            raise SimulatedMooExecutorError(
                "simulated MOO event status is unsupported"
            )
        self._open_plan_events.append(_orders.FillEvent(
            event_id="qc-event-" + str(order_id) + "-" + str(event_id),
            rebalance_id=self._open_plan.rebalance_id,
            client_order_id=intent.client_order_id,
            status=status,
            fill_quantity=fill_quantity,
            fill_price=fill_price,
            engine_fee_amount=engine_fee_amount,
            engine_fee_currency=fee_currency,
        ))

    def close_open_rebalance(self):
        """Reduce one complete event stream to its aggregate-only summary."""

        self._require_active()
        if self._open_plan is None:
            return None
        if self._pending_submission_events is not None:
            raise SimulatedMooExecutorError(
                "simulated MOO rebalance closed during submission"
            )
        try:
            summary = _orders.summarize_order_lifecycle(
                self._open_plan,
                tuple(self._open_plan_events),
                require_all_terminal=True,
            )
        except _orders.OrderLevelBacktestError as exc:
            raise SimulatedMooExecutorError(str(exc)) from exc
        record = summary.to_record()
        self._lifecycle_records.append(record)
        self._open_plan = None
        self._open_plan_events = []
        self._open_order_ids = {}
        return record

    def terminal_aggregate(self):
        """Close and freeze one deterministic aggregate with no raw rows."""

        if self._terminal:
            return json.loads(_canonical(self._terminal_result).decode("ascii"))
        if self._pending is not None:
            raise SimulatedMooExecutorError(
                "simulated MOO pending plan remained at terminal"
            )
        self.close_open_rebalance()
        if self._decision_count <= 0:
            raise SimulatedMooExecutorError(
                "simulated MOO terminal aggregate has no decisions"
            )
        try:
            lifecycle = _orders.aggregate_lifecycle_records(
                tuple(self._lifecycle_records),
                self._submitted_order_count,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SimulatedMooExecutorError(
                "simulated MOO lifecycle aggregate is unavailable"
            ) from exc
        completed = len(self._lifecycle_records)
        skipped = len(self._drift_records)
        execution_failure = lifecycle["execution_failure"]
        run_valid = (
            not execution_failure
            and completed + skipped == self._decision_count
            and skipped == 0
        )
        result = {
            "schema": SUMMARY_SCHEMA,
            "decision_count": self._decision_count,
            "submitted_rebalance_count": self._submitted_rebalance_count,
            "completed_rebalance_count": completed,
            "holding_drift_skipped_rebalance_count": skipped,
            "submitted_order_count": self._submitted_order_count,
            "filled_order_count_sum": lifecycle["filled"],
            "canceled_order_count_sum": lifecycle["canceled"],
            "invalid_order_count_sum": lifecycle["invalid"],
            "orders_with_any_fill_count_sum": lifecycle[
                "orders_with_any_fill"
            ],
            "modeled_fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
            "modeled_fee_amount": _decimal_text(lifecycle["fee"]),
            "actual_engine_fee_amount": _decimal_text(
                lifecycle["actual_fee"]
            ),
            "total_filled_notional": _decimal_text(
                lifecycle["filled_notional"]
            ),
            "mean_target_weight_l1_error": _decimal_text(
                lifecycle["mean_target_error"]
            ),
            "maximum_target_weight_l1_error": _decimal_text(
                lifecycle["maximum_target_error"]
            ),
            "target_weight_l1_error_mark_basis": (
                "prior_close_reference_prices_not_realized_open_prices"
            ),
            "fee_mismatch": lifecycle["fee_mismatch"],
            "execution_failure": execution_failure,
            "run_valid": run_valid,
            "plan_path_sha256": _sha({
                "schema": PLAN_PATH_SCHEMA,
                "plan_sha256s": self._plan_sha256s,
            }),
            "submitted_plan_path_sha256": _sha({
                "schema": (
                    "arv2-simulated-moo-executor-submitted-plan-path-v1"
                ),
                "plan_sha256s": self._submitted_plan_sha256s,
            }),
            "holding_drift_path_sha256": _sha({
                "schema": DRIFT_PATH_SCHEMA,
                "records": self._drift_records,
            }),
            "order_lifecycle_sha256": lifecycle["digest"],
            "external_order_event_count": len(
                self._external_event_records
            ),
            "external_order_event_path_sha256": _sha({
                "schema": EXTERNAL_EVENT_PATH_SCHEMA,
                "records": self._external_event_records,
            }),
            "corporate_action_replan_count": len(
                self._corporate_action_replan_records
            ),
            "corporate_action_replan_path_sha256": _sha({
                "schema": CORPORATE_ACTION_REPLAN_PATH_SCHEMA,
                "records": self._corporate_action_replan_records,
            }),
            "complete_holding_census_before_each_submission": True,
            "raw_order_rows_in_summary": False,
            "raw_security_rows_in_summary": False,
            "backtest_only": True,
            "simulated_market_on_open_orders": True,
            "live_orders": False,
            "paper_orders": False,
            "funded_orders": False,
            "deployment": False,
            "trading": False,
        }
        self._terminal = True
        self._terminal_result = json.loads(_canonical(result).decode("ascii"))
        return json.loads(_canonical(self._terminal_result).decode("ascii"))


__all__ = (
    "CORPORATE_ACTION_REPLAN_PATH_SCHEMA",
    "EXTERNAL_EVENT_PATH_SCHEMA",
    "MAX_SYNCHRONOUS_ORDER_EVENTS",
    "PREOPEN_DRIFT_SKIPPED",
    "PREOPEN_NOT_DUE",
    "PREOPEN_NO_PENDING",
    "PREOPEN_SUBMITTED",
    "SimulatedMooExecutor",
    "SimulatedMooExecutorError",
    "STATE_SCHEMA",
    "SUMMARY_SCHEMA",
)
