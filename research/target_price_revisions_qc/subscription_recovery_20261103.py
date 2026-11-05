"""Candidate-only final-delisting resource bookkeeping for the 2026-11-03 epoch.

No opener, provider client, execution API, subscription removal or source override.
Ordinary unheld/out-of-universe names are NEVER retired: their action custody
and future warning/final observations remain necessary. Only an already-final
native security whose engine configurations are absent can release one manual
bookkeeping slot. All historical algorithms and the 4096 limit remain unchanged.
Fixtures and supplied planning rows are not native evidence or admission.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re

ACTIVE_ID_LIMIT = 4096
MAX_CENSUS_IDS = 65536
MAX_NATIVE_ORDERS = 100000
SCHEMA = "tpr-final-subscription-recovery-candidate-v1"
PROOF_FIELDS = (
    "typed_native_algorithm", "current_job_bound", "after_parent_actions",
    "native_final_in_current_slice", "exact_registered_identity",
    "native_final_security_state", "native_zero_quantity", "ledger_zero_quantity",
    "security_zero_configurations", "manager_zero_configurations",
    "no_open_orders", "known_history", "not_context", "native_clock_unchanged",
)
ROW_FIELDS = frozenset(("security_id", *PROOF_FIELDS))


class ResourceRecoveryRefusal(ValueError):
    """Body-free invalid local planning input."""


def _fail():
    raise ResourceRecoveryRefusal("bounded subscription recovery candidate refused") from None


def _sid(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        _fail()
    return value


def _ids(values, maximum):
    if type(values) not in (list, tuple, set, frozenset) or len(values) > maximum:
        _fail()
    result = tuple(_sid(value) for value in values)
    if len(set(result)) != len(result):
        _fail()
    return set(result)


def plan_reconciliation(manual_ids, observations):
    """Pure supplied-value plan. There is deliberately NO public apply function."""
    manual = _ids(manual_ids, ACTIVE_ID_LIMIT)
    if type(observations) not in (list, tuple) or len(observations) > ACTIVE_ID_LIMIT:
        _fail()
    release, refusals, seen = [], Counter(), set()
    for row in observations:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            _fail()
        sid = _sid(row["security_id"])
        if sid in seen:
            _fail()
        seen.add(sid)
        if any(type(row[key]) not in (bool, type(None)) for key in PROOF_FIELDS):
            _fail()
        if sid not in manual:
            refusals["not_manually_tracked"] += 1
            continue
        missing = [key for key in PROOF_FIELDS if row[key] is not True]
        if missing:
            for key in missing:
                refusals[key] += 1
        else:
            release.append(sid)
    return {
        "schema": SCHEMA, "candidate_release_ids": sorted(release),
        "tracked_manual_ids_before": len(manual),
        "tracked_manual_ids_after": len(manual) - len(release),
        "fixed_active_id_limit": ACTIVE_ID_LIMIT,
        "refusals": dict(sorted(refusals.items())),
        "supplied_rows_are_native_authority": False,
        "native_capacity_proven": False, "native_full_window_verified": False,
        "source_inputs_admitted": False, "economics_accepted": False,
    }


def _zero(value):
    if type(value) is bool or type(value) is float or value is None:
        return False
    if isinstance(value, Fraction):
        return value.numerator == 0
    try:
        amount = Decimal(str(value))
        return amount.is_finite() and amount == 0
    except (InvalidOperation, ValueError, TypeError, ArithmeticError):
        return False


def _native_types():
    # Fixed engine namespace only: no caller-supplied proof getter or boolean.
    # If any typed SDK member is unavailable, the adapter retains all resources.
    import AlgorithmImports as native
    names = ("QCAlgorithm", "Slice", "Symbol", "Security", "Order", "Delisting")
    if any(not isinstance(getattr(native, name, None), type) for name in names):
        raise ResourceRecoveryRefusal("native subscription recovery types unavailable")
    return native


class ResourceRecoveryMixin:
    """New-epoch mixin; importing it never activates a historical candidate."""

    def initialize(self):
        self._subscription_recovery_state = {
            "seen": set(), "census_complete": True, "peak_tracked": 0,
            "final_observations": 0, "released": 0, "unknown": 0,
        }
        return super().initialize()

    def _resource_state(self):
        state = getattr(self, "_subscription_recovery_state", None)
        if type(state) is not dict:
            state = {
                "seen": set(), "census_complete": True, "peak_tracked": 0,
                "final_observations": 0, "released": 0, "unknown": 0,
            }
            self._subscription_recovery_state = state
        return state

    def _ensure_raw_subscription(self, symbol):
        # Original RAW guards and limits execute first and are never bypassed.
        result = super()._ensure_raw_subscription(symbol)
        state = self._resource_state()
        sid = _sid(str(symbol.id))
        if sid not in state["seen"]:
            if len(state["seen"]) < MAX_CENSUS_IDS:
                state["seen"].add(sid)
            else:
                state["census_complete"] = False
        state["peak_tracked"] = max(state["peak_tracked"], len(self._manual_symbols))
        return result

    def _resource_context(self, data, native):
        if (not isinstance(self, native.QCAlgorithm) or self.live_mode is not False
                or self.is_warming_up is not False
                or not isinstance(data, native.Slice)
                or not isinstance(self.current_slice, native.Slice)
                or self.current_slice != data or self.get_locked() is not True):
            raise ResourceRecoveryRefusal("native subscription recovery context unavailable")
        config = self._config
        project, job = self.project_id, self.algorithm_id
        if (type(config) is not dict or type(project) is not int
                or config.get("project_id") != project or type(job) is not str
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job)):
            raise ResourceRecoveryRefusal("native subscription recovery context unavailable")
        self._evidence.require_binding()
        return project, job, self.utc_time, self.current_slice

    def _native_resource_row(self, event, data, native):
        context = self._resource_context(data, native)
        symbol = event.symbol
        sid = _sid(str(symbol.id))
        row = {"security_id": sid, **{key: False for key in PROOF_FIELDS}}
        row["typed_native_algorithm"] = True
        row["current_job_bound"] = True
        row["after_parent_actions"] = True
        finals = list(data.delistings.values())
        if len(finals) > ACTIVE_ID_LIMIT:
            return row, context
        matched = [item for item in finals if isinstance(item, native.Delisting)
                   and item.type == native.DelistingType.DELISTED and item.symbol == symbol]
        row["native_final_in_current_slice"] = (
            isinstance(event, native.Delisting) and event.type == native.DelistingType.DELISTED
            and len(matched) == 1 and matched[0] == event)
        row["not_context"] = symbol not in self._context_symbols
        if (not isinstance(symbol, native.Symbol) or symbol not in self.securities
                or type(self._symbols) is not dict
                or self._symbols.get(sid) != symbol
                or type(self._manual_symbols) is not set
                or sid not in self._manual_symbols
                or sid not in self._delisted_ids):
            return row, context
        security = self.securities[symbol]
        row["exact_registered_identity"] = (
            isinstance(security, native.Security) and security.symbol == symbol
            and symbol.security_type == native.SecurityType.EQUITY)
        row["native_final_security_state"] = (
            security.is_delisted is True and security.is_tradable is False)
        row["native_zero_quantity"] = _zero(self.portfolio[symbol].quantity)
        # An absent independent entry is NOT proof of zero.
        row["ledger_zero_quantity"] = (
            type(self._quantity_ledger) is dict and sid in self._quantity_ledger
            and _zero(self._quantity_ledger[sid]))
        own_configs = list(security.subscriptions)
        manager_configs = list(self.subscription_manager.subscription_data_config_service
                               .get_subscription_data_configs(symbol, True))
        row["security_zero_configurations"] = not own_configs
        row["manager_zero_configurations"] = not manager_configs
        history, opened = list(self.transactions.get_orders()), list(self.transactions.get_open_orders())
        known = (len(history) <= MAX_NATIVE_ORDERS and len(opened) <= MAX_NATIVE_ORDERS
                 and all(isinstance(order, native.Order) for order in history + opened)
                 and self._fill_history_unknown is False)
        row["known_history"] = known
        row["no_open_orders"] = known and not any(order.symbol == symbol for order in opened)
        row["native_clock_unchanged"] = self._resource_context(data, native) == context
        return row, context

    def on_data(self, data):
        # No recovery observer can swallow a parent accounting/action exception.
        result = super().on_data(data)
        state = self._resource_state()
        try:
            native = _native_types()
            self._resource_context(data, native)
            events = list(data.delistings.values())
            if len(events) > ACTIVE_ID_LIMIT:
                raise ResourceRecoveryRefusal("native subscription recovery event bound")
        except Exception:
            state["unknown"] += 1
            return result
        for event in events:
            if not isinstance(event, native.Delisting) or event.type != native.DelistingType.DELISTED:
                continue
            state["final_observations"] += 1
            try:
                first, anchor = self._native_resource_row(event, data, native)
                plan = plan_reconciliation(self._manual_symbols, [first])
                if not plan["candidate_release_ids"]:
                    state["unknown"] += 1
                    continue
                second = self._native_resource_row(event, data, native)
                if second != (first, anchor):
                    state["unknown"] += 1
                    continue
                sid = first["security_id"]
                # Job-bound buffered evidence precedes bookkeeping mutation.
                # Durability remains unproved until the parent journal is exported.
                self._log_audit("SUBSCRIPTION", {
                    "kind": "already_final_resource_bookkeeping_candidate",
                    "schema": SCHEMA, "proof": first, "plan": plan,
                    "native_capacity_proven": False, "economics_accepted": False,
                })
                # Logging itself is an observation boundary: recheck after it.
                if self._native_resource_row(event, data, native) != (first, anchor):
                    state["unknown"] += 1
                    continue
                self._manual_symbols.remove(sid)
                state["released"] += 1
            except Exception:
                # Missing/partial/native-API failures retain the resource.
                state["unknown"] += 1
        return result

    def resource_recovery_census(self):
        state = self._resource_state()
        tracked = getattr(self, "_manual_symbols", None)
        count = len(tracked) if type(tracked) is set and len(tracked) <= ACTIVE_ID_LIMIT else None
        return {
            "schema": SCHEMA, "fixed_active_id_limit": ACTIVE_ID_LIMIT,
            "tracked_manual_id_count": count,
            "cumulative_observed_id_count": len(state["seen"]) if state["census_complete"] else None,
            "cumulative_observed_id_lower_bound": len(state["seen"]),
            "census_complete": state["census_complete"], "peak_tracked_manual_ids": state["peak_tracked"],
            "typed_final_observations": state["final_observations"],
            "proved_final_bookkeeping_releases": state["released"],
            "unknown_or_refused_observations": state["unknown"],
            "actual_native_active_configuration_count": None,
            "actual_native_capacity": None, "native_capacity_proven": False,
            "native_full_window_verified": False, "source_inputs_admitted": False,
            "economics_accepted": False, "candidate_only": True,
        }

    def on_end_of_algorithm(self):
        self._log_audit("SUBSCRIPTION", {
            "kind": "resource_recovery_census", **self.resource_recovery_census()})
        return super().on_end_of_algorithm()
