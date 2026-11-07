"""Pure 48-book QC representation prototype: no engine or empirical permit.

One future QC run may carry 48 cell-scoped Base-security aliases, but the
aggregate native USD account is only a reconciled control. Each exact book
alone determines its fee-reserved orders. This module imports no QC runtime,
provider, credential, network or broker code; every result retains zero access.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache

from data.exchange_calendar import resolve_nth_session_after, session_open_instant
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.latest_revised_protocol import (
    ALLOCATION_ROLES, COSTS_BPS, EVALUATION_START, EVALUATION_END, INITIAL_CASH_USD, LOOKBACKS,
    PROTOCOL_SHA256 as ECONOMIC_SHA256,
)
from research.short_interest_etf.qc_fractional_transport import (
    CELL_IDS, CellTransportState, FillProof, PendingTransportOrder,
    TransportPosition, QUANTUM, MAXIMUM_COMBINED_DRIFT_USD,
    PROTOCOL_SHA256 as TRANSPORT_SHA256, _decimal, _fraction, _identifier,
    _lattice, _proof_decimal, _rational, _text, accept_fill, prepare_order,
)


class RepresentationRefusal(ValueError):
    pass


def _refuse(reason):
    return RepresentationRefusal("REFUSED: " + reason)


def _authority():
    return {"actual_input_admitted": False, "outcome_access_authorized": False,
            "processing_qualified": False, "look_registered": False,
            "qc_execution_authorized": False, "trading_authority": False}


def representation_requirements():
    """A software design, not caller-selectable admission or a cloud permit."""
    payload = {
        "schema": "si-qc-joint-book-representation-prototype-v1",
        "economic_protocol_sha256": ECONOMIC_SHA256,
        "transport_protocol_sha256": TRANSPORT_SHA256,
        "cell_ids": list(CELL_IDS), "selected_lookback": None,
        "topology": "one_joint_candidate_48_independent_cell_books",
        "cash_per_book_usd": INITIAL_CASH_USD,
        "native_aggregate_cash": "sum_mirror_cash_control_only_never_buying_power",
        "alias": "cell_scoped_Base_identifier_no_native_equity_history_or_actions",
        "lot_size": _rational(QUANTUM), "tick_size": _rational(QUANTUM),
        "contract_multiplier": 1, "quote_currency": "USD",
        "fee_reservation": "exact_per_cell_cash_quantity_price_and_fixed_side_bps",
        "price_clock": "qualified_raw_open_at_registered_next_XNYS_open",
        "action_order": ["split", "dividend_entitlement", "dividend_payment", "terminal", "sell", "buy"],
        "dividend": "entitled_pre_ex_open_quantity_receivable_cash_only_at_payment",
        "terminal": "verified_consideration_and_payment_explicit_cash_and_close_no_fake_trade",
        "authority": _authority(),
        "actual_blockers": ["independent_actual_native_source_qualification",
                            "exact_source_processing_route",
                            "prospective_evaluation_and_permanent_look_registration",
                            "qualified_engine_custom_models_and_event_feed",
                            "engine_version_and_joint_candidate_lineage",
                            "authenticated_capacity_and_launch_recheck"],
        "completion": "all_48_books_all_fills_actions_and_native_controls_reconciled_no_open_positions_or_positive_receivables",
        "drift": "absolute_cumulative_per_cell_cash_plus_notional_at_most_1e-6_USD",
        "native_statistics": "diagnostic_not_authoritative_exact_fraction_financial_results",
    }
    payload["representation_sha256"] = hash_payload(payload)
    return payload


def require_actual_execution(*_args, **_kwargs):
    """Prototype has no positive permit route, even with supplied booleans."""
    raise _refuse("prototype_has_no_source_processing_look_or_engine_permit")


def security_alias(cell_id: str, native_id: str) -> str:
    if type(cell_id) is not str or cell_id not in CELL_IDS:
        raise _refuse("unknown_cell")
    _identifier(native_id)
    return "si-base-" + hash_payload({"cell": cell_id, "native": native_id})


@lru_cache(maxsize=512)
def _open_instant(session):
    return session_open_instant(session)


def nominal_release_open(publication_date: str):
    """Hypothetical date schedule only; not actual dissemination evidence."""
    session = resolve_nth_session_after(publication_date, 1)
    at = _open_instant(session).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"publication_date": publication_date, "entry_session": session, "entry_at": at,
            "timing": "hypothetical_calendar_date_next_XNYS_open",
            "actual_availability_verified": False,
            "inside_evaluation": EVALUATION_START <= session <= EVALUATION_END,
            "authority": _authority()}


def _stamp(at: str):
    if type(at) is not str or not at.endswith("Z"):
        raise _refuse("canonical_UTC_clock_required")
    parsed = parse_utc_timestamp(at, "representation.at")
    # Equivalent alternate fractions/time representations cannot split a key.
    canonical = parsed.strftime("%Y-%m-%dT%H:%M:%S")
    if parsed.microsecond:
        canonical += "." + f"{parsed.microsecond:06d}".rstrip("0")
    if at != canonical + "Z":
        raise _refuse("canonical_UTC_clock_required")
    return parsed


_PRIORITY = {"split": 0, "dividend_entitlement": 1, "dividend_payment": 2,
             "terminal": 3, "sell": 4, "buy": 5}


@dataclasses.dataclass(frozen=True, slots=True)
class Receivable:
    security_id: str
    dividend_id: str
    entitlement_at: str
    cash_per_share: Fraction
    economic_amount: Fraction
    mirror_amount: Decimal

    def payload(self):
        if type(self) is not Receivable:
            raise _refuse("exact_receivable_required")
        _identifier(self.security_id); _identifier(self.dividend_id)
        _stamp(self.entitlement_at); _fraction(self.cash_per_share); _fraction(self.economic_amount)
        _proof_decimal(self.mirror_amount, nonnegative=True)
        return {"security_id": self.security_id, "dividend_id": self.dividend_id,
                "entitlement_at": self.entitlement_at,
                "cash_per_share": _rational(self.cash_per_share),
                "economic_amount": _rational(self.economic_amount),
                "mirror_amount": _text(self.mirror_amount)}


@dataclasses.dataclass(frozen=True, slots=True)
class CellBook:
    transport: CellTransportState
    receivables: tuple[Receivable, ...] = ()
    action_ids: tuple[str, ...] = ()
    last_key: tuple[str, int, str, str] | None = None
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        payload = canonical_json(self._payload())
        if hasattr(self, "_anchor") and self._anchor != payload:
            raise _refuse("book_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    @classmethod
    def new(cls, cell_id):
        return cls(CellTransportState.new(cell_id))

    def _payload(self):
        if type(self) is not CellBook or type(self.transport) is not CellTransportState:
            raise _refuse("exact_book_transport_required")
        source = self.transport.to_payload()
        if type(self.receivables) is not tuple or any(type(r) is not Receivable for r in self.receivables):
            raise _refuse("immutable_receivables_required")
        rows = [r.payload() for r in self.receivables]
        keys = [(r.security_id, r.dividend_id) for r in self.receivables]
        if keys != sorted(set(keys)):
            raise _refuse("duplicate_or_unordered_receivables")
        if type(self.action_ids) is not tuple:
            raise _refuse("immutable_actions_required")
        for action in self.action_ids:
            _identifier(action)
        if len(set(self.action_ids)) != len(self.action_ids):
            raise _refuse("duplicate_action")
        if self.last_key is not None:
            if (type(self.last_key) is not tuple or len(self.last_key) != 4
                    or type(self.last_key[1]) is not int or self.last_key[1] not in _PRIORITY.values()):
                raise _refuse("invalid_event_key")
            _stamp(self.last_key[0]); _identifier(self.last_key[2]); _identifier(self.last_key[3])
        return {"schema": "si-qc-independent-cell-book-prototype-v1",
                "transport": source, "receivables": rows,
                "action_ids": list(self.action_ids),
                "last_key": None if self.last_key is None else list(self.last_key),
                "authority": _authority()}

    def to_payload(self):
        payload = self._payload()
        if canonical_json(payload) != self._anchor:
            raise _refuse("book_identity_changed")
        payload["book_sha256"] = hash_payload(payload)
        return payload

    @property
    def sha256(self):
        return self.to_payload()["book_sha256"]


def _key(book, *, at, kind, security_id, event_id):
    if type(book) is not CellBook:
        raise _refuse("exact_book_required")
    book.to_payload(); _stamp(at); _identifier(security_id); _identifier(event_id)
    if type(kind) is not str or kind not in _PRIORITY:
        raise _refuse("unsupported_or_unresolved_event")
    if not EVALUATION_START <= at[:10] <= EVALUATION_END:
        raise _refuse("event_outside_frozen_evaluation")
    if kind in ("buy", "sell") and _stamp(at) != _open_instant(at[:10]):
        raise _refuse("order_not_at_XNYS_raw_open")
    key = at, _PRIORITY[kind], security_id, event_id
    if book.last_key is not None:
        old = (_stamp(book.last_key[0]), *book.last_key[1:])
        new = (_stamp(at), *key[1:])
        if new <= old:
            raise _refuse("event_out_of_order_or_duplicate")
    return key


@dataclasses.dataclass(frozen=True, slots=True)
class EngineControl:
    cell_id: str
    security_alias: str
    at: str
    event_id: str
    cash_before: Decimal
    cash_after: Decimal
    quantity_before: Decimal
    quantity_after: Decimal
    fee_before: Decimal
    fee_after: Decimal

    def __post_init__(self):
        if (type(self) is not EngineControl or type(self.cell_id) is not str
                or self.cell_id not in CELL_IDS):
            raise _refuse("exact_engine_control_required")
        _identifier(self.security_alias); _identifier(self.event_id); _stamp(self.at)
        for name in ("cash_before", "cash_after", "quantity_before", "quantity_after", "fee_before", "fee_after"):
            _proof_decimal(getattr(self, name), nonnegative=True)


def _position(transport, security):
    return next((p for p in transport.positions if p.security_id == security), None)


def _verify_control(before, after, *, security_id, at, event_id, control):
    if type(control) is not EngineControl:
        raise _refuse("exact_engine_control_required")
    EngineControl.__post_init__(control)
    p, q = _position(before.transport, security_id), _position(after.transport, security_id)
    expected = EngineControl(before.transport.cell_id, security_alias(before.transport.cell_id, security_id),
                             at, event_id, before.transport.mirror_cash, after.transport.mirror_cash,
                             Decimal(0) if p is None else p.mirror_quantity,
                             Decimal(0) if q is None else q.mirror_quantity,
                             before.transport.mirror_fees_paid, after.transport.mirror_fees_paid)
    if control != expected:
        raise _refuse("engine_cash_holdings_fee_or_alias_mismatch")


@dataclasses.dataclass(frozen=True, slots=True)
class ScheduledCellOrder:
    transport_order: PendingTransportOrder
    at: str
    source_book_sha256: str
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        payload = canonical_json(self._payload())
        if hasattr(self, "_anchor") and self._anchor != payload:
            raise _refuse("scheduled_order_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    def _payload(self):
        if type(self) is not ScheduledCellOrder or type(self.transport_order) is not PendingTransportOrder:
            raise _refuse("exact_scheduled_order_required")
        _stamp(self.at)
        if (type(self.source_book_sha256) is not str or len(self.source_book_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_book_sha256)):
            raise _refuse("invalid_source_book_digest")
        return {"schema": "si-qc-scheduled-cell-order-prototype-v1", "at": self.at,
                "source_book_sha256": self.source_book_sha256,
                "transport_order": self.transport_order.to_payload()}

    def to_payload(self):
        payload = self._payload()
        if canonical_json(payload) != self._anchor:
            raise _refuse("scheduled_order_identity_changed")
        return payload


def prepare_cell_order(book: CellBook, *, at: str, security_id: str, event_id: str,
                       order_id: str, side: str, economic_quantity: Fraction,
                       economic_price: Fraction) -> ScheduledCellOrder:
    _key(book, at=at, kind=side, security_id=security_id, event_id=event_id)
    order = prepare_order(book.transport, security_id=security_id, event_id=event_id,
                         order_id=order_id, side=side, economic_quantity=economic_quantity,
                         economic_price=economic_price)
    return ScheduledCellOrder(order, at, book.sha256)


def accept_cell_order(book: CellBook, scheduled: ScheduledCellOrder, proof: FillProof,
                      *, at: str, control: EngineControl) -> CellBook:
    if type(scheduled) is not ScheduledCellOrder:
        raise _refuse("exact_scheduled_order_required")
    scheduled.to_payload()
    if scheduled.at != at or scheduled.source_book_sha256 != book.sha256:
        raise _refuse("scheduled_order_clock_or_book_mismatch")
    order = scheduled.transport_order
    key = _key(book, at=at, kind=order.side, security_id=order.security_id, event_id=order.event_id)
    after = dataclasses.replace(book, transport=accept_fill(book.transport, order, proof), last_key=key)
    _verify_control(book, after, security_id=order.security_id, at=at, event_id=order.event_id, control=control)
    return after


@dataclasses.dataclass(frozen=True, slots=True)
class CorporateAction:
    event_id: str
    security_id: str
    at: str
    kind: str
    cash_per_share: Fraction | None = None
    dividend_id: str | None = None
    split_ratio: Fraction | None = None
    valuation_price: Fraction | None = None

    def __post_init__(self):
        if type(self) is not CorporateAction:
            raise _refuse("exact_corporate_action_required")
        _identifier(self.event_id); _identifier(self.security_id); _stamp(self.at)
        if type(self.kind) is not str or self.kind not in _PRIORITY or self.kind in ("buy", "sell"):
            raise _refuse("unresolved_or_unsupported_corporate_action")
        if self.kind == "split":
            _fraction(self.split_ratio, positive=True); _fraction(self.valuation_price, positive=True)
            if self.cash_per_share is not None or self.dividend_id is not None:
                raise _refuse("split_has_unrelated_cash_fields")
        else:
            _fraction(self.cash_per_share)
            if self.split_ratio is not None or self.valuation_price is not None:
                raise _refuse("cash_event_has_split_fields")
            if self.kind != "terminal":
                _identifier(self.dividend_id)
            elif self.dividend_id is not None:
                raise _refuse("terminal_has_dividend_fields")


def _action_after(book: CellBook, action: CorporateAction) -> CellBook:
    if type(action) is not CorporateAction:
        raise _refuse("exact_corporate_action_required")
    CorporateAction.__post_init__(action)
    key = _key(book, at=action.at, kind=action.kind, security_id=action.security_id, event_id=action.event_id)
    if action.event_id in book.action_ids:
        raise _refuse("duplicate_action")
    source = book.transport
    held = _position(source, action.security_id)
    receivables = list(book.receivables)
    cash, mirror = source.economic_cash, Fraction(source.mirror_cash)
    cash_drift, notional_drift = source.cumulative_cash_drift_usd, source.cumulative_notional_drift_usd
    positions = list(source.positions)
    if action.kind == "dividend_payment":
        owed = next((r for r in receivables if (r.security_id, r.dividend_id) == (action.security_id, action.dividend_id)), None)
        if owed is None:
            raise _refuse("payment_without_entitlement")
        if _stamp(action.at) < _stamp(owed.entitlement_at):
            raise _refuse("payment_precedes_entitlement")
        # Amount matching requires the original declared per-share amount,
        # not the current position (which may have exited or split meanwhile).
        if owed.cash_per_share != action.cash_per_share:
            raise _refuse("payment_amount_mismatch")
        cash += owed.economic_amount; mirror += Fraction(owed.mirror_amount)
        cash_drift += abs(owed.economic_amount - Fraction(owed.mirror_amount))
        receivables.remove(owed)
    elif held is None:
        raise _refuse("action_requires_held_identity_or_frozen_receivable")
    elif action.kind == "split":
        exact = held.economic_quantity * action.split_ratio
        unrounded = Fraction(held.mirror_quantity) * action.split_ratio
        posted = _lattice(unrounded, "floor")
        if posted <= 0:
            raise _refuse("split_mirror_quantity_below_lattice")
        positions.remove(held)
        positions.append(TransportPosition(action.security_id, exact, _decimal(posted)))
        notional_drift += abs(unrounded - posted) * action.valuation_price
    elif action.kind == "dividend_entitlement":
        if any((r.security_id, r.dividend_id) == (action.security_id, action.dividend_id) for r in receivables):
            raise _refuse("duplicate_dividend_entitlement")
        exact = held.economic_quantity * action.cash_per_share
        posted = _lattice(Fraction(held.mirror_quantity) * action.cash_per_share, "nearest_even")
        receivables.append(Receivable(action.security_id, action.dividend_id, action.at,
                                      action.cash_per_share, exact, _decimal(posted)))
    elif action.kind == "terminal":
        exact = held.economic_quantity * action.cash_per_share
        posted = _lattice(Fraction(held.mirror_quantity) * action.cash_per_share, "nearest_even")
        cash += exact; mirror += posted; cash_drift += abs(exact - posted)
        positions.remove(held)
    if cash_drift + notional_drift > MAXIMUM_COMBINED_DRIFT_USD:
        raise _refuse("corporate_action_cumulative_drift_budget")
    after_transport = dataclasses.replace(source, economic_cash=cash, mirror_cash=_decimal(mirror),
                    positions=tuple(sorted(positions, key=lambda p: p.security_id)),
                    cumulative_cash_drift_usd=cash_drift, cumulative_notional_drift_usd=notional_drift)
    return dataclasses.replace(book, transport=after_transport,
                               receivables=tuple(sorted(receivables, key=lambda r: (r.security_id, r.dividend_id))),
                               action_ids=book.action_ids + (action.event_id,), last_key=key)


def prepare_corporate_control(book, action):
    """Expected explicit posting for a custom engine adapter, never a permit."""
    after = _action_after(book, action)
    p, q = _position(book.transport, action.security_id), _position(after.transport, action.security_id)
    return EngineControl(book.transport.cell_id, security_alias(book.transport.cell_id, action.security_id),
                         action.at, action.event_id, book.transport.mirror_cash, after.transport.mirror_cash,
                         Decimal(0) if p is None else p.mirror_quantity,
                         Decimal(0) if q is None else q.mirror_quantity,
                         book.transport.mirror_fees_paid, after.transport.mirror_fees_paid)


def accept_corporate_action(book, action, control):
    after = _action_after(book, action)
    _verify_control(book, after, security_id=action.security_id, at=action.at, event_id=action.event_id, control=control)
    return after


def _family(books):
    if type(books) is not tuple or len(books) != 48 or any(type(b) is not CellBook for b in books):
        raise _refuse("all_48_exact_independent_books_required")
    if tuple(b.transport.cell_id for b in books) != CELL_IDS:
        raise _refuse("missing_duplicate_or_reordered_cell")
    for book in books:
        book.to_payload()
    return books


def new_family():
    return tuple(CellBook.new(cell) for cell in CELL_IDS)


def reconcile_native_aggregate(books, *, native_cash: Decimal, native_fees: Decimal,
                               native_holdings: tuple[tuple[str, Decimal], ...]):
    """Native aggregate is diagnostic control, never per-cell buying power."""
    _family(books)
    _proof_decimal(native_cash, nonnegative=True); _proof_decimal(native_fees, nonnegative=True)
    cash = sum((Fraction(b.transport.mirror_cash) for b in books), Fraction())
    fees = sum((Fraction(b.transport.mirror_fees_paid) for b in books), Fraction())
    expected = tuple(sorted((security_alias(b.transport.cell_id, p.security_id), p.mirror_quantity)
                     for b in books for p in b.transport.positions))
    if type(native_holdings) is not tuple:
        raise _refuse("immutable_native_holdings_required")
    for holding in native_holdings:
        if type(holding) is not tuple or len(holding) != 2:
            raise _refuse("exact_native_holding_required")
        _identifier(holding[0]); _proof_decimal(holding[1], positive=True)
    if native_holdings != expected:
        raise _refuse("native_cell_alias_holdings_mismatch")
    if Fraction(native_cash) != cash or Fraction(native_fees) != fees:
        raise _refuse("native_pooled_control_cash_or_fee_mismatch")
    return {"native_control_reconciled": True, "cash": _text(_decimal(cash)),
            "fees": _text(_decimal(fees)), "held_aliases": len(expected),
            "authority": _authority()}


def finish_family(books):
    _family(books)
    if any(b.transport.positions for b in books):
        raise _refuse("open_positions_at_evaluation_end")
    if any(r.economic_amount > 0 for b in books for r in b.receivables):
        raise _refuse("positive_unpaid_dividend_receivable")
    payload = {"schema": "si-qc-48-book-prototype-completion-v1",
               "software_accounting_complete": True, "qc_backtest_completed": False,
               "representation_sha256": representation_requirements()["representation_sha256"],
               "books": [b.to_payload() for b in books], "authority": _authority(),
               "actual_outcome_looks": 0, "qc_launch_attempts": 0,
               "selected_lookback": None}
    payload["completion_sha256"] = hash_payload(payload)
    return payload
