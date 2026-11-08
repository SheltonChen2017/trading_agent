"""Fixed owner-directed execution mask, applied AFTER frozen construction.

The digest planner accepts synthetic supplied values, never native authority.
The production adapter derives its identity digests from typed canonical native
SecurityIdentifiers inside QC. No ticker, exclusion selector, price fallback,
subscription change, input admission, or live execution authority exists here.
This module is also inlined after the immutable resource-recovery mixin.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime as _SidCashDateTime, timedelta as _SidCashDelta, timezone as _SidCashTimezone
from fractions import Fraction
import hashlib
import math
import re
import time as _sid_cash_time

STUDY_ID = "TPR-SIX-UNIVERSE-FIVE-ARM-SID-CASH-20261107-v1"
PARENT_STUDY_ID = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
EXCLUDED_SID_SHA256 = "1122fa5f1349f79e231e106127c098da27ef730836a97052d2154ecc46f1afc1"
SID_CASH_SCHEMA = "tpr-sid-cash-exclusion-v1"
SID_CASH_NATIVE_HISTORY_SCHEMA = "tpr-sid-cash-native-order-history-v1"
SID_CASH_ORDER_CHAIN_DOMAIN = b"tpr-sid-cash-native-orders-v1\n"
SID_CASH_EVENT_CHAIN_DOMAIN = b"tpr-sid-cash-native-events-v1\n"
SID_CASH_OWNER_SHA256 = "54a40d169a093baa0ee4efc8963799a0c24483631881708942a21774e751c2fa"
_SID_CASH_SLEEVES = ("SPY", "XLE", "REMX", "KIE", "XLF", "IWM")
_SID_CASH_ARMS = ("cap_off", "cap_tilt_50", "cap_tilt_100", "cap_tilt_200", "pure_tpr")
_SID_CASH_MAX_IDS = 65536
_SID_CASH_MAX_ORDERS = 100000
_SID_CASH_HISTORY_MAX_ORDERS = 50000
_SID_CASH_HISTORY_MAX_EVENTS = 250000
_SID_CASH_HISTORY_SECONDS = 600


class CashExclusionRefusal(ValueError):
    """Body-free refusal; raw native identities must stay inside QC."""


def _sid_cash_fail():
    raise CashExclusionRefusal("fixed SID cash exclusion refused") from None


def _sid_cash_id(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value.strip() != value or not value.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        _sid_cash_fail()
    return value


def _sid_cash_text_digest(value):
    return hashlib.sha256(_sid_cash_id(value).encode("ascii")).hexdigest()


def _sid_cash_weight(value):
    if type(value) is not Fraction or not 0 <= value <= 1:
        _sid_cash_fail()
    return value


def _sid_cash_weights(value):
    if type(value) is not dict or len(value) > 60:
        _sid_cash_fail()
    return {_sid_cash_id(sid): _sid_cash_weight(weight) for sid, weight in value.items()}


def plan_cash_exclusion(weights, construction, sid_sha256_by_id):
    """Pure fixed-digest plan. Caller-supplied digests prove NO native identity.

    Production calls this only after computing every digest from typed native
    symbols. The function cannot rerank, reconstruct, refill or choose another
    excluded digest. All input structures, including construction, stay intact.
    """
    original = _sid_cash_weights(weights)
    if (type(sid_sha256_by_id) is not dict or set(sid_sha256_by_id) != set(original)
            or any(type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None
                   for digest in sid_sha256_by_id.values())
            or type(construction) is not dict or construction.get("arm") not in _SID_CASH_ARMS
            or type(construction.get("per_sleeve")) is not dict
            or set(construction["per_sleeve"]) != set(_SID_CASH_SLEEVES)):
        _sid_cash_fail()
    excluded = {sid for sid, digest in sid_sha256_by_id.items() if digest == EXCLUDED_SID_SHA256}
    if len(excluded) > 1:
        _sid_cash_fail()
    aggregate, sleeves, selected, masked = {}, {}, 0, 0
    for sleeve in _SID_CASH_SLEEVES:
        row = construction["per_sleeve"][sleeve]
        if type(row) is not dict:
            _sid_cash_fail()
        before = _sid_cash_weights(row.get("target_weights"))
        slots = row.get("executable_ids")
        if (type(slots) not in (tuple, list) or len(slots) > 10
                or len(set(slots)) != len(slots) or set(slots) != set(before)
                or not set(before) <= set(original)):
            _sid_cash_fail()
        gross = sum(before.values(), Fraction(0))
        if (gross != row.get("target_weight") or row.get("cash_weight") != Fraction(1, 6) - gross):
            _sid_cash_fail()
        after = {sid: weight for sid, weight in before.items() if sid not in excluded}
        removed = sum((weight for sid, weight in before.items() if sid in excluded), Fraction(0))
        count = sum(sid in excluded for sid in slots)
        selected += len(slots)
        masked += count
        execution_gross = sum(after.values(), Fraction(0))
        sleeves[sleeve] = {
            "execution_weights": after, "frozen_selected_slot_count": len(slots),
            "masked_selected_slot_occurrences": count,
            "execution_slot_count": len(slots) - count,
            "removed_final_weight": removed, "cash_increment": removed,
            "execution_gross_weight": execution_gross,
            "execution_cash_weight": Fraction(1, 6) - execution_gross,
        }
        for sid, weight in before.items():
            aggregate[sid] = aggregate.get(sid, Fraction(0)) + weight
    gross = sum(original.values(), Fraction(0))
    if (aggregate != original or selected != construction.get("selected_slot_count")
            or gross != construction.get("target_gross_weight")
            or construction.get("cash_weight") != 1 - gross):
        _sid_cash_fail()
    after = {sid: weight for sid, weight in original.items() if sid not in excluded}
    removed = sum((original[sid] for sid in excluded), Fraction(0))
    execution_gross = sum(after.values(), Fraction(0))
    cash = 1 - execution_gross
    if (removed != sum((row["removed_final_weight"] for row in sleeves.values()), Fraction(0))
            or gross - execution_gross != removed or cash != construction["cash_weight"] + removed
            or sum((row["execution_cash_weight"] for row in sleeves.values()), Fraction(0)) != cash):
        _sid_cash_fail()
    return after, {
        "schema": SID_CASH_SCHEMA, "study_id": STUDY_ID, "parent_study_id": PARENT_STUDY_ID,
        "excluded_security_id_sha256": EXCLUDED_SID_SHA256,
        "arm": construction["arm"], "per_sleeve": sleeves,
        "frozen_selected_slot_count": selected,
        "masked_selected_slot_occurrences": masked,
        "execution_slot_count": selected - masked,
        "masked_unique_target_count": len(excluded), "removed_final_weight": removed,
        "cash_increment": removed, "frozen_construction_gross_weight": gross,
        "frozen_construction_cash_weight": construction["cash_weight"],
        "execution_gross_weight": execution_gross, "execution_cash_weight": cash,
        "all_other_exact_weights_unchanged": True, "redistribution": False,
        "refill": False, "reranking": False,
        "supplied_digests_are_native_authority": False,
        "orders_or_fills_identical_to_parent": False,
        "source_inputs_admitted": False, "strategy_accepted": False,
    }


def _sid_cash_zero(value):
    # Python.NET can expose native zero as float. Exact finite zero is safe;
    # epsilon tests and float conversion of nonzero Decimal/Fraction are not.
    if type(value) is bool or value is None:
        return False
    if type(value) is float:
        return math.isfinite(value) and value == 0.0
    if isinstance(value, Fraction):
        return value.numerator == 0
    try:
        amount = Decimal(str(value))
        return amount.is_finite() and amount == 0
    except (InvalidOperation, ValueError, TypeError, ArithmeticError):
        return False


def _sid_cash_native():
    import AlgorithmImports as native
    for name in ("QCAlgorithm", "Symbol", "SecurityIdentifier", "Order", "OrderEvent", "Slice"):
        if not isinstance(getattr(native, name, None), type):
            _sid_cash_fail()
    return native


def _sid_cash_core():
    # Exact pinned financial helpers already present in the financial closure.
    # This is never an import of caller-supplied code or an input adapter.
    import extended_core
    return extended_core


def _sid_cash_bounded(values, maximum):
    result = []
    for value in values:
        if len(result) >= maximum:
            _sid_cash_fail()
        result.append(value)
    return result


def _sid_cash_integer(value, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0) or value > 2147483647:
        _sid_cash_fail()
    return value


def _sid_cash_number(value, *, integer=False, nonnegative=False):
    if type(value) is bool or value is None:
        _sid_cash_fail()
    number = _sid_cash_core().native_fraction(value)
    if (type(number) is not Fraction or abs(number) > 10**18
            or integer and number.denominator != 1 or nonnegative and number < 0):
        _sid_cash_fail()
    return number


def _sid_cash_wire(value):
    return _sid_cash_core().exact_json(value).encode("ascii")


def _sid_cash_status(value, native):
    if not isinstance(value, native.OrderStatus):
        _sid_cash_fail()
    for attribute, label in (("NEW", "New"), ("SUBMITTED", "Submitted"),
            ("PARTIALLY_FILLED", "PartiallyFilled"), ("FILLED", "Filled"),
            ("CANCELED", "Canceled"), ("NONE", "None"), ("INVALID", "Invalid"),
            ("CANCEL_PENDING", "CancelPending"), ("UPDATE_SUBMITTED", "UpdateSubmitted")):
        if getattr(native.OrderStatus, attribute, None) == value:
            return label
    _sid_cash_fail()


def _sid_cash_order_type(value, native):
    if not isinstance(value, native.OrderType):
        _sid_cash_fail()
    for attribute, label in (("MARKET_ON_OPEN", "MarketOnOpen"), ("MARKET", "Market")):
        if getattr(native.OrderType, attribute, None) == value:
            return label
    _sid_cash_fail()


class CashExclusionMixin:
    """Fixed from-start mask; every inherited financial/action guard stays active."""

    def initialize(self):
        self._sid_cash_state = {"guard_calls": 0, "masked_decisions": 0,
            "masked_slot_occurrences": 0, "blocked_submission_attempts": 0,
            "excluded_submitted_orders": 0, "excluded_fill_events": 0,
            "initializing": True}
        try:
            result = super().initialize()
            self._sid_cash_guard("initialized", history=True)
        finally:
            self._sid_cash_state["initializing"] = False
        return result

    def _sid_cash_context(self):
        native = _sid_cash_native()
        if (not isinstance(self, native.QCAlgorithm) or self.live_mode is not False
                or type(self._config) is not dict or self._config.get("study_id") != STUDY_ID
                or self._config.get("arm") not in _SID_CASH_ARMS
                or type(getattr(self, "_sid_cash_state", None)) is not dict):
            _sid_cash_fail()
        if self._sid_cash_state.get("initializing") is True:
            # QC locks an algorithm AFTER initialize returns. The parent
            # journal observes the native project during initialization but
            # intentionally cannot require a locked job yet.
            if (type(self.project_id) is not int or self.project_id != self._config.get("project_id")
                    or type(self.get_locked()) is not bool):
                _sid_cash_fail()
        else:
            self._evidence.require_binding()
        return native

    def _sid_cash_digest_id(self, sid, native):
        sid = _sid_cash_id(sid)
        try:
            parsed = native.SecurityIdentifier.parse(sid)
        except Exception:
            _sid_cash_fail()
        if not isinstance(parsed, native.SecurityIdentifier) or str(parsed) != sid:
            _sid_cash_fail()
        return _sid_cash_text_digest(sid)

    def _sid_cash_digest_symbol(self, symbol, native):
        if (not isinstance(symbol, native.Symbol)
                or not isinstance(symbol.id, native.SecurityIdentifier)):
            _sid_cash_fail()
        sid = _sid_cash_id(str(symbol.id))
        try:
            parsed = native.SecurityIdentifier.parse(sid)
        except Exception:
            _sid_cash_fail()
        if parsed != symbol.id:
            _sid_cash_fail()
        return self._sid_cash_digest_id(sid, native)

    def _sid_cash_guard(self, stage, *, history=False):
        native = self._sid_cash_context()
        holdings = list(self.portfolio.values())
        ledger = self._quantity_ledger
        if (len(holdings) > _SID_CASH_MAX_IDS or type(ledger) is not dict
                or len(ledger) > _SID_CASH_MAX_IDS or self._fill_history_unknown is not False):
            _sid_cash_fail()
        # Scan every native holding, including unknown/unregistered names and
        # objects with invested=False but a nonzero quantity. Never zero it.
        for held in holdings:
            if self._sid_cash_digest_symbol(held.symbol, native) == EXCLUDED_SID_SHA256:
                if not _sid_cash_zero(held.quantity) or held.invested is not False:
                    _sid_cash_fail()
        for sid, quantity in ledger.items():
            if self._sid_cash_digest_id(sid, native) == EXCLUDED_SID_SHA256 and not _sid_cash_zero(quantity):
                _sid_cash_fail()
        filled = self._ever_filled_ids
        if type(filled) is not set or len(filled) > _SID_CASH_MAX_IDS:
            _sid_cash_fail()
        if any(self._sid_cash_digest_id(sid, native) == EXCLUDED_SID_SHA256 for sid in filled):
            _sid_cash_fail()
        opened = list(self.transactions.get_open_orders())
        orders = list(self.transactions.get_orders()) if history else []
        if len(opened) > _SID_CASH_MAX_ORDERS or len(orders) > _SID_CASH_MAX_ORDERS:
            _sid_cash_fail()
        for order in opened + orders:
            if not isinstance(order, native.Order):
                _sid_cash_fail()
            if self._sid_cash_digest_symbol(order.symbol, native) == EXCLUDED_SID_SHA256:
                _sid_cash_fail()
        self._sid_cash_state["guard_calls"] += 1

    def _prepare_targets(self, day):
        self._sid_cash_guard("before_construction")
        result = super()._prepare_targets(day)
        coverage = self._decision_coverage.get(day)
        if coverage is None:
            return result
        native = self._sid_cash_context()
        if (type(self._targets) is not dict or type(self._target_weights) is not dict
                or set(self._targets) != set(self._target_weights)):
            _sid_cash_fail()
        digests = {}
        for sid, symbol in self._targets.items():
            if str(symbol.id) != sid:
                _sid_cash_fail()
            digests[sid] = self._sid_cash_digest_symbol(symbol, native)
        weights, audit = plan_cash_exclusion(self._target_weights, coverage["construction"], digests)
        if coverage.get("arm") != self._config["arm"] or audit["arm"] != self._config["arm"]:
            _sid_cash_fail()
        # Both maps lose zero-weight excluded donors too: inherited mark
        # collection iterates KEYS, not positive weights. No earlier input is
        # filtered and the frozen construction/selected slots remain untouched.
        self._targets = {sid: symbol for sid, symbol in self._targets.items() if sid in weights}
        self._target_weights = weights
        coverage["coverage_semantics"] = {
            "construction_sleeves_target_gross_unallocated_target_cash": "frozen_pre_mask_construction",
            "execution_mask": "post_construction_fixed_sid_to_cash",
            "prior_mark_inputs_sha256": "remaining_execution_targets",
            "prior_mark_sleeve_sha256": "frozen_selected_slots_with_masked_mark_unavailable",
        }
        coverage["execution_mask"] = audit
        self._sid_cash_state["masked_decisions"] += int(audit["masked_unique_target_count"] > 0)
        self._sid_cash_state["masked_slot_occurrences"] += audit["masked_selected_slot_occurrences"]
        self._log_audit("COVERAGE", {"kind": "sid_cash_exclusion_execution_mask", "session": day, **audit})
        self._sid_cash_guard("after_construction")
        return result

    def _rebalance(self):
        self._sid_cash_guard("before_rebalance", history=True)
        result = super()._rebalance()
        self._sid_cash_guard("after_rebalance", history=True)
        return result

    def _daily_audit(self):
        self._sid_cash_guard("before_valuation", history=True)
        result = super()._daily_audit()
        self._sid_cash_guard("after_valuation", history=True)
        return result

    def market_on_open_order(self, symbol, quantity, *args, **kwargs):
        native = self._sid_cash_context()
        if self._sid_cash_state.get("initializing") is not False:
            _sid_cash_fail()
        if self._sid_cash_digest_symbol(symbol, native) == EXCLUDED_SID_SHA256:
            self._sid_cash_state["blocked_submission_attempts"] += 1
            _sid_cash_fail()
        self._sid_cash_guard("before_submission")
        result = super().market_on_open_order(symbol, quantity, *args, **kwargs)
        self._sid_cash_guard("after_submission")
        return result

    def on_order_event(self, event):
        native = self._sid_cash_context()
        if not isinstance(event, native.OrderEvent):
            _sid_cash_fail()
        if self._sid_cash_digest_symbol(event.symbol, native) == EXCLUDED_SID_SHA256:
            _sid_cash_fail()
        self._sid_cash_guard("before_order_event")
        result = super().on_order_event(event)
        self._sid_cash_guard("after_order_event")
        return result

    def on_data(self, data):
        native = self._sid_cash_context()
        if not isinstance(data, native.Slice):
            _sid_cash_fail()
        # Native holdings can change through fills and corporate actions. Fill
        # callbacks are guarded separately. Keep ordinary minute delivery light;
        # every action event executes both guards and the complete parent path.
        actions = bool(data.splits or data.dividends or data.delistings)
        if actions:
            self._sid_cash_guard("before_action_event")
        result = super().on_data(data)
        if actions:
            self._sid_cash_guard("after_action_event")
        return result

    def on_securities_changed(self, changes):
        self._sid_cash_guard("before_security_event")
        result = super().on_securities_changed(changes)
        self._sid_cash_guard("after_security_event")
        return result

    def on_warmup_finished(self):
        self._sid_cash_guard("before_warmup_finished")
        result = super().on_warmup_finished()
        self._sid_cash_guard("after_warmup_finished")
        return result

    def _sid_cash_history_snapshot(self):
        self._sid_cash_context()
        raw = _sid_cash_wire(self._config)
        if (self.get_locked() is not True or self._evidence._config_raw != raw
                or self._evidence._config_hash != hashlib.sha256(raw).hexdigest()):
            _sid_cash_fail()
        utc = self._native_clock(self.utc_time, "UTC")
        local = self._native_clock(self.time, "America/New_York")
        if (not isinstance(utc, _SidCashDateTime) or utc.tzinfo is None
                or utc.utcoffset() != _SidCashDelta(0) or local != utc):
            _sid_cash_fail()
        return (self._evidence.require_binding(), self.project_id, self.algorithm_id,
            utc, local,
            _sid_cash_number(self.portfolio.cash),
            _sid_cash_number(self.portfolio.total_portfolio_value),
            _sid_cash_number(self.portfolio.total_holdings_value))

    def _sid_cash_history_claim(self):
        if getattr(self, "_sid_cash_native_history_attempted", False):
            _sid_cash_fail()
        self._sid_cash_native_history_attempted = True  # Spent before any effect.
        native = self._sid_cash_context()
        for name in ("OrderTicket", "OrderStatus", "OrderType"):
            if not isinstance(getattr(native, name, None), type):
                _sid_cash_fail()
        snapshot = self._sid_cash_history_snapshot()
        prefix, project, job, capture, local, cash, nav, holdings = snapshot
        config = self._config
        config_raw = _sid_cash_wire(config)
        config_hash = hashlib.sha256(config_raw).hexdigest()
        if (self._evidence._config_raw != config_raw or self._evidence._config_hash != config_hash
                or type(project) is not int or project != config.get("project_id")
                or type(job) is not str or re.fullmatch("[0-9a-f]{32}", job) is None
                or not prefix.endswith("/" + str(project) + "/" + job + "/")):
            _sid_cash_fail()
        for key in ("policy_sha256", "calendar_sha256", "source_template_closure_sha256",
                "prior_attempts_looks_sha256"):
            if type(config.get(key)) is not str or re.fullmatch("[0-9a-f]{64}", config[key]) is None:
                _sid_cash_fail()
        created = _SidCashDateTime.now(_SidCashTimezone.utc)
        deadline = _sid_cash_time.monotonic() + _SID_CASH_HISTORY_SECONDS
        body = {
            "schema": "tpr-sid-cash-native-history-access-v1", "study_id": STUDY_ID,
            "owner_instruction_sha256": SID_CASH_OWNER_SHA256,
            "owner_scope": "implementation-record-122.3-prospective-native-census",
            "candidate_id": config["candidate_id"], "arm": config["arm"],
            "operation_id": config["operation_id"], "attempt": config["attempt"],
            "config_sha256": config_hash, "policy_sha256": config["policy_sha256"],
            "calendar_sha256": config["calendar_sha256"],
            "source_template_closure_sha256": config["source_template_closure_sha256"],
            "prior_attempts_looks_sha256": config["prior_attempts_looks_sha256"],
            "project_id": project, "job_id": job, "capture_utc": capture.isoformat(),
            "created_wall_utc": created.isoformat(),
            "expires_wall_utc": (created + _SidCashDelta(seconds=_SID_CASH_HISTORY_SECONDS)).isoformat(),
            "maximum_seconds": _SID_CASH_HISTORY_SECONDS,
            "maximum_orders": _SID_CASH_HISTORY_MAX_ORDERS,
            "maximum_events": _SID_CASH_HISTORY_MAX_EVENTS,
            "native_history_passes": 2, "maximum_get_orders_calls": 2,
            "maximum_get_order_ticket_calls": 2 * _SID_CASH_HISTORY_MAX_ORDERS,
            "maximum_ticket_order_events_reads": 2 * _SID_CASH_HISTORY_MAX_ORDERS,
            "maximum_get_open_orders_calls": 4,
            "object_store_contains_calls": 1, "object_store_save_calls": 1,
            "object_store_readback_calls": 1,
            "spent_before_native_history_read": True,
            "backend_durability_proven": False, "raw_identities_leave_qc": False,
            "order_submission_calls": 0, "source_inputs_admitted": False,
        }
        raw = _sid_cash_wire(body)
        if not 0 < len(raw) <= 4096:
            _sid_cash_fail()
        key = prefix + "native-order-history-access.json"
        descriptor = {"claim_key": key, "claim_bytes": len(raw),
            "claim_sha256": hashlib.sha256(raw).hexdigest(),
            "claim_same_node_verified": True, "backend_durability_proven": False}

        def bound():
            if (_sid_cash_time.monotonic() >= deadline
                    or _SidCashDateTime.now(_SidCashTimezone.utc) >= created + _SidCashDelta(seconds=_SID_CASH_HISTORY_SECONDS)
                    or self._sid_cash_history_snapshot() != snapshot):
                _sid_cash_fail()

        def guarded(call):
            bound()
            try:
                value = call()
            except BaseException as first:
                try:
                    bound()
                except BaseException as second:
                    if isinstance(second, KeyboardInterrupt):
                        raise second
                    if isinstance(first, KeyboardInterrupt) or not isinstance(first, Exception):
                        raise first
                    if not isinstance(second, Exception):
                        raise second
                raise
            bound()
            return value

        exists = guarded(lambda: self.object_store.contains_key(key))
        if type(exists) is not bool or exists:
            _sid_cash_fail()
        if guarded(lambda: self.object_store.save_bytes(key, raw)) is not True:
            _sid_cash_fail()
        observed = guarded(lambda: self.object_store.read_bytes(key))
        if isinstance(observed, str) or len(observed) != len(raw) or len(observed) > 4096:
            _sid_cash_fail()
        if bytes(observed) != raw:
            _sid_cash_fail()
        self._log_audit("COVERAGE", {"schema": SID_CASH_NATIVE_HISTORY_SCHEMA,
            "study_id": STUDY_ID, "kind": "sid_cash_native_history_claim",
            "capture_utc": capture.isoformat(), **descriptor})
        return native, capture, descriptor, guarded

    def _sid_cash_history_clock(self, value, capture):
        clock = self._native_clock(value, "UTC")
        if (not isinstance(clock, _SidCashDateTime) or clock.tzinfo is None
                or clock.utcoffset() != _SidCashDelta(0) or clock > capture):
            _sid_cash_fail()
        return clock

    def _sid_cash_capture_history(self, native, capture, guarded, *, emit):
        opened = guarded(lambda: _sid_cash_bounded(
            self.transactions.get_open_orders(), _SID_CASH_HISTORY_MAX_ORDERS))
        if opened:
            _sid_cash_fail()
        orders = guarded(lambda: _sid_cash_bounded(
            self.transactions.get_orders(), _SID_CASH_HISTORY_MAX_ORDERS))
        if any(not isinstance(order, native.Order) for order in orders):
            _sid_cash_fail()
        ids = [_sid_cash_integer(order.id, positive=True) for order in orders]
        if len(set(ids)) != len(ids):
            _sid_cash_fail()
        order_hash = hashlib.sha256(SID_CASH_ORDER_CHAIN_DOMAIN)
        event_hash = hashlib.sha256(SID_CASH_EVENT_CHAIN_DOMAIN)
        events_count = nonzero = 0
        filled_shares = fees = Fraction(0)
        common = {"schema": SID_CASH_NATIVE_HISTORY_SCHEMA, "study_id": STUDY_ID}
        for order in sorted(orders, key=lambda row: row.id):
            order_id = _sid_cash_integer(order.id, positive=True)
            if self._sid_cash_digest_symbol(order.symbol, native) == EXCLUDED_SID_SHA256:
                _sid_cash_fail()
            sid = _sid_cash_id(str(order.symbol.id))
            quantity = _sid_cash_number(order.quantity, integer=True)
            status = _sid_cash_status(order.status, native)
            if status not in ("Filled", "Canceled", "Invalid"):
                _sid_cash_fail()
            order_type = _sid_cash_order_type(order.type, native)
            order_time = self._sid_cash_history_clock(order.time, capture)
            if (order.price_currency != "USD" or type(order.tag) is not str
                    or len(order.tag) > 256 or not order.tag.isascii()
                    or any(ord(char) < 32 or ord(char) == 127 for char in order.tag)):
                _sid_cash_fail()
            ticket = guarded(lambda: self.transactions.get_order_ticket(order_id))
            if (not isinstance(ticket, native.OrderTicket) or ticket.order_id != order_id
                    or ticket.symbol != order.symbol):
                _sid_cash_fail()
            ticket_quantity = _sid_cash_number(ticket.quantity, integer=True)
            ticket_filled = _sid_cash_number(ticket.quantity_filled, integer=True)
            ticket_average = _sid_cash_number(ticket.average_fill_price, nonnegative=True)
            ticket_status = _sid_cash_status(ticket.status, native)
            if ticket_quantity != quantity or ticket_status != status:
                _sid_cash_fail()
            events = guarded(lambda: _sid_cash_bounded(ticket.order_events,
                _SID_CASH_HISTORY_MAX_EVENTS - events_count))
            if not events or any(not isinstance(event, native.OrderEvent) for event in events):
                _sid_cash_fail()
            event_rows, last_id, last_clock = [], -1, order_time
            observed_filled = Fraction(0)
            filled_prices = []
            for event in events:
                event_id = _sid_cash_integer(event.id)
                if (event.order_id != order_id or event_id <= last_id or event.symbol != order.symbol
                        or event.is_assignment is not False):
                    _sid_cash_fail()
                event_clock = self._sid_cash_history_clock(event.utc_time, capture)
                if event_clock < last_clock:
                    _sid_cash_fail()
                last_id, last_clock = event_id, event_clock
                fill_quantity = _sid_cash_number(event.fill_quantity, integer=True)
                fill_price = _sid_cash_number(event.fill_price, nonnegative=True)
                fee = _sid_cash_number(event.order_fee.value.amount, nonnegative=True)
                fee_currency = event.order_fee.value.currency
                null_currency = native.Currencies.NullCurrency
                event_status = _sid_cash_status(event.status, native)
                if (event.fill_price_currency not in ("USD", "", None)
                        or fill_quantity != 0 and event.fill_price_currency != "USD"
                        or fee_currency not in ("USD", "", None, null_currency)
                        or fee != 0 and fee_currency != "USD"
                        or fill_quantity != 0 and event_status not in ("PartiallyFilled", "Filled")
                        or fill_quantity and (fill_price <= 0 or fill_quantity * quantity <= 0)):
                    _sid_cash_fail()
                if fill_quantity:
                    filled_prices.append(fill_price)
                observed_filled += fill_quantity
                filled_shares += abs(fill_quantity)
                fees += fee
                nonzero += int(fill_quantity != 0)
                event_rows.append({**common, "kind": "sid_cash_native_order_event",
                    "order_id": order_id, "event_id": event_id, "security_id": sid,
                    "utc": event_clock.isoformat(), "status": event_status,
                    "fill_quantity": fill_quantity, "fill_price": fill_price,
                    "fill_currency": event.fill_price_currency, "fee": fee,
                    "fee_currency": fee_currency, "is_assignment": False})
            if (observed_filled != ticket_filled or abs(observed_filled) > abs(quantity)
                    or _sid_cash_status(events[-1].status, native) != status
                    or ticket_filled == 0 and ticket_average != 0
                    or ticket_filled != 0 and ticket_average <= 0
                    or filled_prices and not min(filled_prices) <= ticket_average <= max(filled_prices)
                    or status == "Filled" and ticket_filled != quantity):
                _sid_cash_fail()
            events_count += len(event_rows)
            row = {**common, "kind": "sid_cash_native_order", "order_id": order_id,
                "security_id": sid, "order_type": order_type, "status": status,
                "quantity": quantity, "time_utc": order_time.isoformat(),
                "price_currency": order.price_currency, "tag": order.tag,
                "ticket_quantity": ticket_quantity, "ticket_quantity_filled": ticket_filled,
                "ticket_average_fill_price": ticket_average, "ticket_status": ticket_status,
                "ticket_event_count": len(event_rows)}
            order_hash.update(_sid_cash_wire(row) + b"\n")
            if emit:
                self._log_audit("COVERAGE", row)
            for event_row in event_rows:
                event_hash.update(_sid_cash_wire(event_row) + b"\n")
                if emit:
                    self._log_audit("COVERAGE", event_row)
            guarded(lambda: None)
        return {"orders": len(orders), "events": events_count, "nonzero_fills": nonzero,
            "open_orders": 0, "absolute_filled_shares": filled_shares, "reported_fees": fees,
            "order_rows_sha256": order_hash.hexdigest(), "event_rows_sha256": event_hash.hexdigest()}

    def _sid_cash_native_history(self):
        # This durable claimed read is separate from producer intent/FILL rows.
        # A verifier child cannot recreate the parent's transaction history.
        native, capture, descriptor, guarded = self._sid_cash_history_claim()
        guarded(lambda: self._sid_cash_guard("before_native_history"))
        first = self._sid_cash_capture_history(native, capture, guarded, emit=True)
        second = self._sid_cash_capture_history(native, capture, guarded, emit=False)
        if first != second:
            _sid_cash_fail()
        guarded(lambda: self._sid_cash_guard("after_native_history"))
        self._log_audit("COVERAGE", {"schema": SID_CASH_NATIVE_HISTORY_SCHEMA,
            "study_id": STUDY_ID, "kind": "sid_cash_native_history_census", **first,
            "known_history": True, "stable_second_capture": True,
            "capture_utc": capture.isoformat(), **descriptor,
            "source_inputs_admitted": False, "strategy_accepted": False})

    def on_end_of_algorithm(self):
        self._sid_cash_native_history()
        # This price-free census is appended BEFORE the parent exports its
        # journal. No public log contains a raw identity or a price.
        self._log_audit("COVERAGE", {"kind": "sid_cash_exclusion_census",
            "schema": SID_CASH_SCHEMA, "study_id": STUDY_ID,
            "parent_study_id": PARENT_STUDY_ID,
            "excluded_security_id_sha256": EXCLUDED_SID_SHA256,
            **self._sid_cash_state, "excluded_native_quantity": 0,
            "excluded_independent_quantity": 0, "excluded_open_orders": 0,
            "checked_native_order_history": True, "source_inputs_admitted": False,
            "strategy_accepted": False})
        return super().on_end_of_algorithm()
