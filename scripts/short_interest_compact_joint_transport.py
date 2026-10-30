"""Unadmitted V2 runtime draft: bounded transitions, mandatory cohort audits.

Economic formulas are the unchanged original Fraction/decimal transport and
corporate-action kernel, applied to an affected-security projection. Full
positions, claims, duplicate IDs and append-only history stay here; projection
history is NOT a reset of the real ledger or any source/request budget.
No credentials, actual inputs, QC job or positive permit is included.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_lean_joint_transport as old
from research.short_interest_etf import native_accrual_ending as ending
from research.short_interest_etf import native_qc_order_representation as rep


def _refuse(reason):
    return old._refuse(reason)


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise _refuse("exact_digest_required")
    return value


def compact_policy():
    result = {"schema": "si-compact-joint-runtime-draft-v2",
        "economic_sha256": rep.ECONOMIC_SHA256, "decimal_transport_sha256": rep.TRANSPORT_SHA256,
        "cell_ids": list(rep.CELL_IDS), "economic_kernel": "unchanged_affected_projection_of_original_math",
        "projection_scope": "at_most_one_held_security_one_matching_receivable_no_history",
        "real_ledger": "all_positions_claims_ids_and_append_only_journal_retained_not_reset",
        "transition_namespace": "trade_security_event_side_and_separate_cell_global_action_event",
        "per_fill": "affected_alias_quantity_fee_and_aggregate_cash_delta_only",
        "boundary": "registered_cohort_end_full_all48_all_registered_aliases_and_incremental_journal_audit",
        "report": "no_open_cohort_or_pending_order_full_all48_all_aliases_full_journal_audit_first",
        "UTC_Unspecified": "only_QCAlgorithm.UtcTime_Order.Time_OrderEvent.UtcTime_documented_UTC",
        "native_statistics": "diagnostic_not_authoritative",
        "authority": rep._authority(), "actual_looks": 0, "qc_attempts": 0}
    result["policy_sha256"] = hash_payload(result)
    return result


def require_actual_execution(*_args, **_kwargs):
    raise _refuse("compact_prototype_has_no_actual_source_processing_look_or_QC_permit")


_UTC_PATHS = ("QCAlgorithm.UtcTime", "Order.Time", "OrderEvent.UtcTime")


def documented_utc_text(value, *, kind, semantic_path):
    """Software clock normalization, not provider publication evidence.

    Public UTC properties can carry DateTimeKind.Unspecified; do not apply host
    local-zone conversion. A caller-supplied arbitrary timestamp is not covered.
    """
    if type(semantic_path) is not str or semantic_path not in _UTC_PATHS:
        raise _refuse("not_a_documented_LEAN_UTC_property")
    if type(value) is not str or type(kind) is not str or kind not in ("Utc", "Unspecified"):
        raise _refuse("LEAN_UTC_kind_or_clock_refused")
    if kind == "Utc":
        if not value.endswith("Z"):
            raise _refuse("UTC_kind_string_mismatch")
        stem = value[:-1]
    else:
        if value.endswith("Z") or "+" in value[10:] or "-" in value[10:]:
            raise _refuse("Unspecified_kind_string_mismatch")
        stem = value
    if "." in stem:
        whole, fraction = stem.split(".", 1)
        if not fraction.isdigit() or (len(fraction) > 6 and any(c != "0" for c in fraction[6:])):
            raise _refuse("unsupported_submicrosecond_clock")
        fraction = fraction[:6].rstrip("0")
        stem = whole + ("." + fraction if fraction else "")
    rep._stamp(stem + "Z")
    return stem + "Z"


class CompactLeanRuntime(old.LeanRuntime):
    def utc(self, obj, *path):
        choices = ((self.qc.QCAlgorithm, ("UtcTime",), "QCAlgorithm.UtcTime"),
                   (self.qc.Order, ("Time",), "Order.Time"),
                   (self.qc.OrderEvent, ("UtcTime",), "OrderEvent.UtcTime"))
        label = next((label for cls, allowed, label in choices
            if tuple(path) == allowed and self.clr.GetClrType(cls).IsAssignableFrom(obj.GetType())), None)
        if label is None:
            raise _refuse("not_a_documented_LEAN_UTC_property")
        value = self._string_getter(obj, tuple(path), "o", "System.DateTime")
        key = obj.GetType().AssemblyQualifiedName, tuple(path), "DateTime.Kind"
        if key not in self.getters:
            E = self.Expression
            p = E.Parameter(self.clr.GetClrType(self.Object), "instance")
            node = E.Convert(p, obj.GetType())
            for name in path:
                node = E.PropertyOrField(node, name)
            kind = E.Property(node, "Kind")
            method = kind.Type.GetMethod("ToString", self.Array[self.Type]([]))
            call = E.Call(kind, method)
            self.getters[key] = E.Lambda[self.Func[self.Object, self.String]](
                call, self.Array[self.ParameterExpression]([p])).Compile()
        return documented_utc_text(value, kind=self.getters[key].Invoke(obj), semantic_path=label)


@dataclasses.dataclass(frozen=True, slots=True)
class Instruction:
    cell_id: str
    at: str
    security_id: str
    event_id: str
    kind: str
    order_id: str | None = None
    quantity: Fraction | None = None
    price: Fraction | None = None
    action: rep.CorporateAction | None = None
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        payload = canonical_json(self.payload())
        if hasattr(self, "_anchor") and (type(self._anchor) is not str or self._anchor != payload):
            raise _refuse("instruction_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    def payload(self):
        if type(self) is not Instruction or type(self.cell_id) is not str or self.cell_id not in rep.CELL_IDS:
            raise _refuse("exact_instruction_and_cell_required")
        rep._stamp(self.at); rep._identifier(self.security_id); rep._identifier(self.event_id)
        if self.kind in ("buy", "sell"):
            rep._identifier(self.order_id); rep._fraction(self.quantity, positive=True); rep._fraction(self.price, positive=True)
            if self.action is not None:
                raise _refuse("trade_has_action_fields")
            detail = {"order_id": self.order_id, "quantity": rep._rational(self.quantity), "price": rep._rational(self.price)}
        else:
            if type(self.action) is not rep.CorporateAction or any(x is not None for x in (self.order_id, self.quantity, self.price)):
                raise _refuse("exact_action_instruction_required")
            rep.CorporateAction.__post_init__(self.action)
            if (self.action.at, self.action.security_id, self.action.event_id, self.action.kind) != (self.at, self.security_id, self.event_id, self.kind):
                raise _refuse("action_instruction_identity_mismatch")
            detail = {name: (rep._rational(v) if type(v) is Fraction else v)
                      for name, v in dataclasses.asdict(self.action).items()}
        return {"cell": self.cell_id, "at": self.at, "security": self.security_id,
                "event": self.event_id, "kind": self.kind, "detail": detail}

    @property
    def sha256(self):
        payload = self.payload()
        if type(self._anchor) is not str or canonical_json(payload) != self._anchor:
            raise _refuse("instruction_identity_changed")
        return hash_payload(payload)


def trade_instruction(cell, *, at, security_id, event_id, order_id, side, quantity, price):
    return Instruction(cell, at, security_id, event_id, side, order_id, quantity, price)


def action_instruction(cell, action):
    return Instruction(cell, action.at, action.security_id, action.event_id, action.kind, action=action)


def transition_key(instruction):
    # Match the original kernel's trade tuple and separate global action IDs.
    # A shared release event may legitimately drive several securities/legs.
    instruction.sha256
    if instruction.order_id is not None:
        return ("trade", instruction.security_id, instruction.event_id, instruction.kind)
    return ("action", instruction.event_id)


def _root(rows):
    result = 0
    for row in rows:
        result ^= int(hash_payload(row), 16)
    return f"{result:064x}"


class RuntimeCell:
    def __init__(self, cell):
        initial = rep.CellTransportState.new(cell)
        self.cell_id, self.economic_cash, self.mirror_cash = cell, initial.economic_cash, initial.mirror_cash
        self.economic_fees_paid, self.mirror_fees_paid = Fraction(), Decimal(0)
        self.cumulative_cash_drift_usd, self.cumulative_notional_drift_usd = Fraction(), Fraction()
        self.positions, self.receivables = {}, {}
        self.position_root = self.receivable_root = "0" * 64
        self.order_ids, self.event_keys, self.action_ids = [], [], []  # Append-only, no per-fill copies.
        self.used_orders, self.used_transitions = set(), set()
        self.last_key, self.revision = None, 0
        self.sha256 = hash_payload({"cell": cell, "initial_cash": rep.INITIAL_CASH_USD,
                                    "policy": compact_policy()["policy_sha256"]})
        self._scalar_anchor = canonical_json(self.scalars())

    @property
    def transport(self):
        return self  # Generic buying-power callback accesses only mirror_cash.

    def scalars(self):
        return {"cell": self.cell_id, "cash": rep._rational(self.economic_cash), "mirror_cash": rep._text(self.mirror_cash),
            "fees": rep._rational(self.economic_fees_paid), "mirror_fees": rep._text(self.mirror_fees_paid),
            "cash_drift": rep._rational(self.cumulative_cash_drift_usd), "notional_drift": rep._rational(self.cumulative_notional_drift_usd),
            "position_root": self.position_root, "position_count": len(self.positions),
            "receivable_root": self.receivable_root, "receivable_count": len(self.receivables),
            "orders": len(self.order_ids), "events": len(self.event_keys), "actions": len(self.action_ids),
            "transition_count": len(self.used_transitions), "last_key": self.last_key,
            "revision": self.revision, "state_sha256": self.sha256}

    def verify_scalar(self):
        _sha(self.sha256)
        if type(self._scalar_anchor) is not str or canonical_json(self.scalars()) != self._scalar_anchor:
            raise _refuse("runtime_scalar_identity_changed")

    def projection(self, security, dividend=None):
        self.verify_scalar()
        held = self.positions.get(security)
        owed = self.receivables.get((security, dividend))
        state = rep.CellTransportState(self.cell_id, self.economic_cash, self.mirror_cash,
            () if held is None else (held,), (), (), self.economic_fees_paid, self.mirror_fees_paid,
            self.cumulative_cash_drift_usd, self.cumulative_notional_drift_usd)
        return rep.CellBook(state, () if owed is None else (owed,), (), self.last_key)

    def snapshot(self):
        self.verify_full()
        state = rep.CellTransportState(self.cell_id, self.economic_cash, self.mirror_cash,
            tuple(self.positions[k] for k in sorted(self.positions)), tuple(self.order_ids), tuple(self.event_keys),
            self.economic_fees_paid, self.mirror_fees_paid, self.cumulative_cash_drift_usd, self.cumulative_notional_drift_usd)
        return rep.CellBook(state, tuple(self.receivables[k] for k in sorted(self.receivables)), tuple(self.action_ids), self.last_key)

    def verify_full(self, *, full_history=False):
        self.verify_scalar()
        if _root([p.payload() for p in self.positions.values()]) != self.position_root:
            raise _refuse("runtime_position_map_changed")
        if _root([r.payload() for r in self.receivables.values()]) != self.receivable_root:
            raise _refuse("runtime_receivable_map_changed")
        if (len(self.used_orders) != len(self.order_ids)
                or len(self.event_keys) != len(self.order_ids)
                or len(self.used_transitions) != len(self.order_ids) + len(self.action_ids)):
            raise _refuse("runtime_history_or_duplicate_registry_changed")
        if full_history and (set(self.order_ids) != self.used_orders
                or self.used_transitions != ({("trade", *key) for key in self.event_keys}
                                             | {("action", event) for event in self.action_ids})):
            raise _refuse("runtime_history_or_duplicate_registry_changed")

    def apply(self, instruction, after, command_hash):
        self.verify_scalar()
        key = transition_key(instruction)
        if key in self.used_transitions or (instruction.order_id is not None and instruction.order_id in self.used_orders):
            raise _refuse("duplicate_runtime_transition_or_order")
        previous = self.sha256
        sid = instruction.security_id
        old_position = self.positions.get(sid)
        new_position = rep._position(after.transport, sid)
        xor = int(self.position_root, 16)
        for p in (old_position, new_position):
            if p is not None:
                xor ^= int(hash_payload(p.payload()), 16)
        self.position_root = f"{xor:064x}"
        if new_position is None:
            self.positions.pop(sid, None)
        else:
            self.positions[sid] = new_position
        if instruction.action is not None and instruction.action.dividend_id is not None:
            claim_key = sid, instruction.action.dividend_id
            old_claim = self.receivables.get(claim_key)
            new_claim = next(iter(after.receivables), None)
            xor = int(self.receivable_root, 16)
            for claim in (old_claim, new_claim):
                if claim is not None:
                    xor ^= int(hash_payload(claim.payload()), 16)
            self.receivable_root = f"{xor:064x}"
            if new_claim is None:
                self.receivables.pop(claim_key, None)
            else:
                self.receivables[claim_key] = new_claim
        for name in ("economic_cash", "mirror_cash", "economic_fees_paid", "mirror_fees_paid",
                     "cumulative_cash_drift_usd", "cumulative_notional_drift_usd"):
            setattr(self, name, getattr(after.transport, name))
        if instruction.order_id is not None:
            self.order_ids.append(instruction.order_id); self.used_orders.add(instruction.order_id)
            self.event_keys.append((sid, instruction.event_id, instruction.kind))
        else:
            self.action_ids.append(instruction.event_id)
        self.used_transitions.add(key)
        self.last_key, self.revision = after.last_key, self.revision + 1
        # Roots/counts are constant-size commitments; canonical map snapshots
        # and complete history validation occur at mandatory boundaries.
        self.sha256 = hash_payload({"previous": previous, "instruction": command_hash,
                                    "after": {k: v for k, v in self.scalars().items() if k != "state_sha256"}})
        self._scalar_anchor = canonical_json(self.scalars())
        return previous, self.sha256


@dataclasses.dataclass(frozen=True, slots=True)
class Scheduled:
    instruction: Instruction
    bounded: rep.ScheduledCellOrder
    source_revision: str
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        payload = canonical_json(self._payload())
        if hasattr(self, "_anchor") and (type(self._anchor) is not str or self._anchor != payload):
            raise _refuse("compact_schedule_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    @property
    def transport_order(self):
        return self.bounded.transport_order

    @property
    def at(self):
        return self.instruction.at

    @property
    def source_book_sha256(self):
        return self.source_revision

    def _payload(self):
        if type(self) is not Scheduled or type(self.instruction) is not Instruction or type(self.bounded) is not rep.ScheduledCellOrder:
            raise _refuse("exact_compact_schedule_required")
        return {"instruction_sha256": self.instruction.sha256, "bounded": self.bounded.to_payload(),
                "runtime_revision": _sha(self.source_revision)}

    def to_payload(self):
        payload = self._payload()
        if type(self._anchor) is not str or canonical_json(payload) != self._anchor:
            raise _refuse("compact_schedule_identity_changed")
        return payload


class CompactJointTransport(old.JointTransport):
    def __init__(self, runtime):
        self.runtime = runtime
        self.cells = {cell: RuntimeCell(cell) for cell in rep.CELL_IDS}
        self.securities, self.identities, self.opens, self.alias_fees = {}, {}, {}, {}
        self.pending, self.poisoned, self.sequence = None, False, 0
        self.expected_cash = old._sum(c.mirror_cash for c in self.cells.values())
        self.journal, self.journal_head = [], "0" * 64
        self.initial_heads = {cell: self.cells[cell].sha256 for cell in rep.CELL_IDS}
        self.verified_index, self.verified_head, self.verified_cells = 0, self.journal_head, dict(self.initial_heads)
        self.cohort, self.cohort_ids, self.expected, self.consumed = None, set(), {}, set()

    def book(self, cell):
        if type(cell) is not str or cell not in self.cells:
            raise _refuse("unknown_cell")
        self.cells[cell].verify_scalar()
        return self.cells[cell]

    def begin_cohort(self, cohort_id, *, at, instructions):
        self._live(); rep._identifier(cohort_id); rep._stamp(at)
        if self.cohort is not None or self.pending is not None or cohort_id in self.cohort_ids or self.runtime.now() != at:
            raise _refuse("invalid_or_duplicate_cohort_start")
        if type(instructions) is not tuple or tuple(row[0] for row in instructions) != rep.CELL_IDS:
            raise _refuse("registered_all48_cohort_agenda_required")
        expected = {}
        for cell, rows in instructions:
            if type(rows) is not tuple:
                raise _refuse("immutable_cohort_commands_required")
            for instruction in rows:
                if type(instruction) is not Instruction or instruction.cell_id != cell or instruction.at != at:
                    raise _refuse("cohort_command_identity_or_clock_mismatch")
                key = cell, transition_key(instruction)
                if key in expected or key[1] in self.cells[cell].used_transitions:
                    raise _refuse("duplicate_cohort_transition")
                expected[key] = instruction.sha256
        self.full_audit()
        self.cohort_ids.add(cohort_id)
        self.cohort = cohort_id, at, hash_payload({"cohort": cohort_id, "at": at,
            "commands": [[cell, [[i.event_id, i.sha256] for i in rows]] for cell, rows in instructions]})
        self.expected, self.consumed = expected, set()

    def _slot(self, instruction):
        self._live()
        key = instruction.cell_id, transition_key(instruction)
        if (self.cohort is None or instruction.at != self.cohort[1] or self.runtime.now() != instruction.at
                or self.expected.get(key) != instruction.sha256 or key in self.consumed):
            raise _refuse("transition_not_in_active_frozen_cohort")
        return key

    def prepare(self, instruction):
        self._slot(instruction)
        if instruction.kind not in ("buy", "sell"):
            raise _refuse("action_not_trade")
        cell = self.book(instruction.cell_id)
        if instruction.order_id in cell.used_orders:
            raise _refuse("duplicate_runtime_order")
        bounded = rep.prepare_cell_order(cell.projection(instruction.security_id), at=instruction.at,
            security_id=instruction.security_id, event_id=instruction.event_id, order_id=instruction.order_id,
            side=instruction.kind, economic_quantity=instruction.quantity, economic_price=instruction.price)
        return Scheduled(instruction, bounded, cell.sha256)

    def offer_raw_open(self, alias, *, at, raw_open):
        if self.cohort is None or at != self.cohort[1]:
            raise _refuse("open_outside_registered_cohort")
        return super().offer_raw_open(alias, at=at, raw_open=raw_open)

    def arm(self, scheduled):
        self._live()
        if self.pending is not None or type(scheduled) is not Scheduled:
            raise _refuse("one_exact_compact_pending_order_required")
        scheduled.to_payload(); self._slot(scheduled.instruction)
        o, rt = scheduled.transport_order, self.runtime
        cell, alias = self.book(o.cell_id), rep.security_alias(o.cell_id, o.security_id)
        if (cell.sha256 != scheduled.source_revision or alias not in self.securities
                or self.opens.get(alias) != (scheduled.at, o.economic_price)
                or self.prepare(scheduled.instruction).to_payload() != scheduled.to_payload()):
            raise _refuse("stale_unregistered_or_unproven_compact_order")
        security = self.securities[alias]
        held = cell.positions.get(o.security_id)
        quantity = Decimal(0) if held is None else held.mirror_quantity
        if (rt.cash() != self.expected_cash or rt.decimal(security, "Holdings", "Quantity") != quantity
                or rt.decimal(security, "Holdings", "TotalFees") != self.alias_fees[alias]):
            self._stop("affected_alias_or_cash_mismatch_before_order")
        self.sequence += 1
        self.pending = old._Pending(scheduled, alias, f"si-joint-{self.sequence:012d}", self.expected_cash, self.alias_fees[alias])
        return self.pending.tag

    def _match(self, security, order):
        p = super()._match(security, order)
        self._slot(p.scheduled.instruction)
        return p

    def settle(self, parameters):
        self._live()
        p, rt = self.pending, self.runtime
        if p is None or p.settlement_calls != 0 or p.fill_calls != 1:
            self._stop("missing_or_duplicate_native_settlement")
        self._validate_fill(parameters.Fill)
        o, security = p.scheduled.transport_order, parameters.Security
        cell = self.book(o.cell_id)
        held = cell.positions.get(o.security_id)
        before_quantity = Decimal(0) if held is None else held.mirror_quantity
        if (rt.symbol(security) != p.alias or parameters.CashAmount.Currency != "USD"
                or rt.cash() != old._sum((p.aggregate_cash_before, -o.fee_usd))
                or rt.decimal(security, "Holdings", "TotalFees") != old._sum((p.alias_fee_before, o.fee_usd))
                or rt.decimal(security, "Holdings", "Quantity") != before_quantity):
            self._stop("affected_fee_cash_or_holdings_before_settlement_mismatch")
        rt.post_cash(old._sum((o.posted_cash_delta_usd, o.fee_usd)))
        p.settlement_calls += 1

    def _commit(self, instruction, after):
        cell = self.book(instruction.cell_id)
        before_cash = cell.mirror_cash
        previous, new = cell.apply(instruction, after, instruction.sha256)
        row = {"index": len(self.journal), "cohort": self.cohort[2], "cell": instruction.cell_id,
               "event": instruction.event_id, "instruction": instruction.sha256,
               "cell_previous": previous, "cell_next": new, "global_previous": self.journal_head}
        next_hash = hash_payload(row)
        self.journal.append((canonical_json(row), next_hash, instruction))
        self.journal_head = next_hash
        self.expected_cash = rep._decimal(Fraction(self.expected_cash) + Fraction(cell.mirror_cash) - Fraction(before_cash))
        self.consumed.add((instruction.cell_id, transition_key(instruction)))

    def on_order_event(self, event):
        self._live()
        p, rt = self.pending, self.runtime
        if p is not None and rt.is_nonterminal_notice(event):
            if (type(event.OrderId) is not int or event.OrderId <= 0 or p.engine_order_id not in (None, event.OrderId)
                    or rt.symbol(event) != p.alias or rt.utc(event, "UtcTime") != p.scheduled.at):
                self._stop("unregistered_native_order_notice")
            p.engine_order_id = event.OrderId
            return
        self._validate_fill(event)
        if p.fill_calls != 1 or p.settlement_calls != 1:
            self._stop("native_fill_did_not_post_exactly_once")
        instruction, o, cell = p.scheduled.instruction, p.scheduled.transport_order, self.book(p.scheduled.instruction.cell_id)
        bounded = cell.projection(o.security_id)
        security = self.securities[p.alias]
        cash_delta = rep._decimal(Fraction(rt.cash()) - Fraction(p.aggregate_cash_before))
        fee_delta = rep._decimal(Fraction(rt.decimal(security, "Holdings", "TotalFees")) - Fraction(p.alias_fee_before))
        held = cell.positions.get(o.security_id)
        control = rep.EngineControl(o.cell_id, p.alias, instruction.at, o.event_id,
            cell.mirror_cash, old._sum((cell.mirror_cash, cash_delta)), Decimal(0) if held is None else held.mirror_quantity,
            rt.decimal(security, "Holdings", "Quantity"), cell.mirror_fees_paid, old._sum((cell.mirror_fees_paid, fee_delta)))
        signed_notional = old._sum((cash_delta, fee_delta))
        proof = rep.FillProof(o.cell_id, o.security_id, o.event_id, o.order_id, o.side,
            rt.decimal(event, "FillQuantity"), rt.decimal(event, "FillPrice"), fee_delta,
            rep._decimal(abs(Fraction(signed_notional))), cash_delta)
        try:
            self._slot(instruction)
            if cell.sha256 != p.scheduled.source_revision:
                raise _refuse("runtime_revision_changed_before_fill")
            after = rep.accept_cell_order(bounded, p.scheduled.bounded, proof, at=instruction.at, control=control)
            self._commit(instruction, after)
            self.alias_fees[p.alias] = old._sum((p.alias_fee_before, o.fee_usd))
            if rt.cash() != self.expected_cash:
                raise _refuse("aggregate_cash_delta_mismatch_after_fill")
        except Exception:
            self.poisoned = True
            raise
        self.pending = None

    def corporate_instruction(self, instruction):
        self._slot(instruction)
        if self.pending is not None or instruction.action is None:
            raise _refuse("invalid_corporate_transition")
        cell, action, rt = self.book(instruction.cell_id), instruction.action, self.runtime
        bounded = cell.projection(instruction.security_id, action.dividend_id)
        control = rep.prepare_corporate_control(bounded, action)
        alias = control.security_alias
        if alias not in self.securities:
            raise _refuse("corporate_alias_not_registered")
        security = self.securities[alias]
        if (rt.cash() != self.expected_cash or rt.decimal(security, "Holdings", "Quantity") != control.quantity_before
                or rt.decimal(security, "Holdings", "TotalFees") != self.alias_fees[alias]):
            self._stop("affected_alias_or_cash_mismatch_before_action")
        before_cash = rt.cash()
        try:
            if action.kind in ("split", "terminal"):
                old_average = rt.decimal(security, "Holdings", "AveragePrice")
                average = (rep._decimal(rep._lattice(Fraction(old_average) / action.split_ratio, "nearest_even"))
                           if action.kind == "split" else Decimal(0))
                rt.set_holdings(security, average_price=average, quantity=control.quantity_after)
            delta = rep._decimal(Fraction(control.cash_after) - Fraction(control.cash_before))
            if delta:
                rt.post_cash(delta)
            native = dataclasses.replace(control, cash_after=old._sum((cell.mirror_cash,
                rep._decimal(Fraction(rt.cash()) - Fraction(before_cash)))),
                quantity_after=rt.decimal(security, "Holdings", "Quantity"))
            if rt.decimal(security, "Holdings", "TotalFees") != self.alias_fees[alias]:
                raise _refuse("unexpected_fee_on_corporate_action")
            after = rep.accept_corporate_action(bounded, action, native)
            self._commit(instruction, after)
            if rt.cash() != self.expected_cash:
                raise _refuse("aggregate_cash_delta_mismatch_after_action")
        except Exception:
            self.poisoned = True
            raise

    def _audit_journal(self, full):
        import json
        start, head, cells = ((0, "0" * 64, dict(self.initial_heads)) if full
                              else (self.verified_index, self.verified_head, dict(self.verified_cells)))
        histories = {cell: ([], [], []) for cell in rep.CELL_IDS} if full else None
        for index in range(start, len(self.journal)):
            text, claimed, instruction = self.journal[index]
            if type(text) is not str or type(claimed) is not str:
                raise _refuse("invalid_journal_row")
            row = json.loads(text)
            if (canonical_json(row) != text or hash_payload(row) != claimed or row["index"] != index
                    or row["global_previous"] != head or cells[row["cell"]] != row["cell_previous"]
                    or type(instruction) is not Instruction or instruction.sha256 != row["instruction"]
                    or (instruction.cell_id, instruction.event_id) != (row["cell"], row["event"])):
                raise _refuse("event_journal_chain_mismatch")
            if histories is not None:
                orders, events, actions = histories[instruction.cell_id]
                if instruction.order_id is not None:
                    orders.append(instruction.order_id)
                    events.append((instruction.security_id, instruction.event_id, instruction.kind))
                else:
                    actions.append(instruction.event_id)
            head, cells[row["cell"]] = claimed, row["cell_next"]
        if head != self.journal_head or any(cells[c] != self.cells[c].sha256 for c in rep.CELL_IDS):
            raise _refuse("journal_or_state_revision_mismatch")
        if histories is not None:
            for cell, (orders, events, actions) in histories.items():
                actual = self.cells[cell]
                if (actual.order_ids, actual.event_keys, actual.action_ids) != (orders, events, actions):
                    raise _refuse("runtime_history_does_not_match_event_journal")
        self.verified_index, self.verified_head, self.verified_cells = len(self.journal), head, cells

    def full_audit(self, *, full_journal=False):
        self._live()
        if self.pending is not None:
            raise _refuse("audit_during_pending_order")
        try:
            for cell in rep.CELL_IDS:
                self.cells[cell].verify_full(full_history=full_journal)
            self._audit_journal(full_journal)
            cash, fees, holdings = super()._snapshot()
            expected_cash = old._sum(c.mirror_cash for c in self.cells.values())
            expected_fees = old._sum(c.mirror_fees_paid for c in self.cells.values())
            expected_holdings = tuple(sorted((rep.security_alias(c.cell_id, native), p.mirror_quantity)
                for c in self.cells.values() for native, p in c.positions.items()))
            if cash != self.expected_cash or cash != expected_cash or fees != expected_fees or holdings != expected_holdings:
                raise _refuse("full_all48_native_cash_fee_quantity_mismatch")
        except Exception:
            self.poisoned = True
            raise
        return {"full_all48_and_all_registered_aliases_reconciled": True,
                "journal_sha256": self.journal_head, "authority": rep._authority()}

    def end_cohort(self):
        self._live()
        if self.cohort is None or self.pending is not None or self.consumed != set(self.expected):
            raise _refuse("cohort_commands_unfinished")
        result = self.full_audit()
        self.cohort, self.expected, self.consumed = None, {}, set()
        return result

    def reconcile(self):
        return self.full_audit()

    def snapshot_family(self):
        self._live()
        if self.cohort is not None or self.pending is not None:
            raise _refuse("report_before_audited_cohort_close")
        self.full_audit(full_journal=True)
        return tuple(self.cells[cell].snapshot() for cell in rep.CELL_IDS)

    def finish_v1(self):
        return rep.finish_family(self.snapshot_family())

    def ending_v2(self, *, dividends=()):
        return ending.build_native_ending_report(self.snapshot_family(), dividends=dividends)
