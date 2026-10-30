"""Entirely fabricated representation tests; no source/API/QC runtime."""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction
import importlib.util
from pathlib import Path
import sys

import pytest

from research.short_interest_etf import native_qc_order_representation as qc


def proof(order, **changes):
    if type(order) is qc.ScheduledCellOrder:
        order = order.transport_order
    fields = {name: getattr(order, name) for name in (
        "cell_id", "security_id", "event_id", "order_id", "side", "fill_price",
        "fee_usd", "posted_notional_usd", "posted_cash_delta_usd")}
    fields["filled_quantity"] = order.submitted_quantity
    fields.update(changes)
    return qc.FillProof(**fields)


def order_control(book, order, at):
    if type(order) is qc.ScheduledCellOrder:
        order = order.transport_order
    after = qc.accept_fill(book.transport, order, proof(order))
    p = qc._position(book.transport, order.security_id)
    q = qc._position(after, order.security_id)
    return qc.EngineControl(book.transport.cell_id,
        qc.security_alias(book.transport.cell_id, order.security_id), at, order.event_id,
        book.transport.mirror_cash, after.mirror_cash,
        Decimal(0) if p is None else p.mirror_quantity,
        Decimal(0) if q is None else q.mirror_quantity,
        book.transport.mirror_fees_paid, after.mirror_fees_paid)


def trade(book, *, at="2023-01-03T14:30:00Z", side="buy", quantity=Fraction(1, 3),
          price=Fraction(30), security="native:fabricated-1", event="open-1", order_id="order-1"):
    order = qc.prepare_cell_order(book, at=at, security_id=security, event_id=event,
                                 order_id=order_id, side=side, economic_quantity=quantity,
                                 economic_price=price)
    return qc.accept_cell_order(book, order, proof(order), at=at,
                                control=order_control(book, order, at))


def action(book, *, event="entitlement-1", kind="dividend_entitlement",
           at="2023-01-04T14:30:00Z", security="native:fabricated-1", cash=Fraction(1),
           dividend="dividend-1", ratio=None, price=None):
    event = qc.CorporateAction(event, security, at, kind, cash, dividend, ratio, price)
    return qc.accept_corporate_action(book, event, qc.prepare_corporate_control(book, event))


def test_zero_authority_and_actual_refusal_even_with_owner_or_boolean_flags():
    policy = qc.representation_requirements()
    assert len(policy["cell_ids"]) == 48
    assert policy["native_aggregate_cash"].endswith("never_buying_power")
    assert all(flag is False for flag in policy["authority"].values())
    for flags in ({}, {"source_admitted": True, "qc_authorized": True, "look_registered": True}):
        with pytest.raises(qc.RepresentationRefusal, match="prototype_has_no"):
            qc.require_actual_execution(**flags)


@pytest.mark.parametrize("cell", qc.CELL_IDS)
def test_48_cells_preserve_fee_reserved_fractional_buy_and_exact_economic_close(cell):
    book = qc.CellBook.new(cell)
    rate = Fraction(int(cell.split("-C")[1].split("-")[0]), 10000)
    quantity = Fraction(100000) / (Fraction(13, 3) * (1 + rate))
    held = trade(book, quantity=quantity, price=Fraction(13, 3))
    assert held.transport.economic_cash == 0
    assert held.transport.mirror_cash >= 0
    assert held.transport.positions[0].economic_quantity == quantity
    closed = trade(held, at="2023-01-17T14:30:00Z", side="sell", quantity=quantity,
                   price=Fraction(14, 3), event="open-2", order_id="order-2")
    assert closed.transport.positions == ()
    assert closed.transport.economic_cash == quantity * Fraction(14, 3) * (1 - rate)
    assert closed.transport.cumulative_cash_drift_usd + closed.transport.cumulative_notional_drift_usd <= qc.MAXIMUM_COMBINED_DRIFT_USD


def test_same_native_identity_is_cell_scoped_not_shared_position_or_buying_power():
    books = qc.new_family()
    assert len({qc.security_alias(b.transport.cell_id, "native:fabricated-1") for b in books}) == 48
    exhausted = dataclasses.replace(books[0], transport=dataclasses.replace(books[0].transport,
                                      economic_cash=Fraction(0), mirror_cash=Decimal(0)))
    assert sum(b.transport.economic_cash for b in books[1:]) == 4_700_000
    with pytest.raises(ValueError, match="budget"):
        trade(exhausted, quantity=Fraction(1), price=Fraction(1))
    assert all(b.transport.economic_cash == 100000 for b in books)


def test_dividend_is_receivable_until_payment_and_survives_exit():
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    entitled = action(held)
    assert entitled.transport.economic_cash == held.transport.economic_cash
    assert entitled.receivables[0].economic_amount == Fraction(1, 3)
    exited = trade(entitled, at="2023-01-05T14:30:00Z", side="sell", event="open-2", order_id="order-2")
    paid = action(exited, event="payment-1", kind="dividend_payment", at="2023-01-06T00:00:00Z")
    assert paid.transport.economic_cash == exited.transport.economic_cash + Fraction(1, 3)
    assert paid.receivables == ()


def test_payment_amount_cannot_change_original_entitlement_after_exit():
    entitled = action(trade(qc.CellBook.new(qc.CELL_IDS[0])))
    with pytest.raises(qc.RepresentationRefusal, match="amount_mismatch"):
        action(entitled, event="payment-1", kind="dividend_payment", cash=Fraction(2), at="2023-01-06T00:00:00Z")


def test_split_entitlement_payment_then_terminal_same_time_is_frozen_priority():
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    split = action(held, event="split-1", kind="split", cash=None, dividend=None,
                   ratio=Fraction(3, 2), price=Fraction(20))
    assert split.transport.positions[0].economic_quantity == Fraction(1, 2)
    entitlement = action(split)
    assert entitlement.receivables[0].economic_amount == Fraction(1, 2)
    payment = action(entitlement, event="payment-1", kind="dividend_payment")
    terminal = action(payment, event="terminal-1", kind="terminal", dividend=None, cash=Fraction(8))
    assert terminal.transport.positions == ()
    assert terminal.transport.economic_cash == held.transport.economic_cash + Fraction(1, 2) + 4
    assert terminal.transport.economic_fees_paid == held.transport.economic_fees_paid
    assert len(terminal.transport.consumed_order_ids) == 1
    with pytest.raises(qc.RepresentationRefusal, match="out_of_order"):
        action(terminal, event="late-split", kind="split", cash=None, dividend=None, ratio=Fraction(2), price=Fraction(4))


def test_reverse_split_never_whole_share_rounds_or_creates_cash_in_lieu():
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    split = action(held, event="split-1", kind="split", cash=None, dividend=None,
                   ratio=Fraction(1, 7), price=Fraction(210))
    assert split.transport.positions[0].economic_quantity == Fraction(1, 21)
    assert 0 < split.transport.positions[0].mirror_quantity < 1
    assert split.transport.economic_cash == held.transport.economic_cash


@pytest.mark.parametrize("kind,cash", [("terminal", None), ("unknown_terminal", Fraction(0)),
                                         ("suspension", Fraction(0))])
def test_unknown_terminal_cash_and_suspension_do_not_turn_into_zero_or_price_trade(kind, cash):
    with pytest.raises(ValueError):
        action(trade(qc.CellBook.new(qc.CELL_IDS[0])), kind=kind, cash=cash, dividend=None)


def test_evidenced_zero_terminal_is_explicit_cash_posting_not_zero_price_order():
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    ended = action(held, event="zero-known", kind="terminal", cash=Fraction(0), dividend=None)
    assert ended.transport.economic_cash == held.transport.economic_cash
    assert ended.transport.positions == ()
    assert ended.transport.consumed_order_ids == held.transport.consumed_order_ids


@pytest.mark.parametrize("field,value", [("cash_after", Decimal(0)), ("quantity_after", Decimal(1)),
    ("fee_after", Decimal(1)), ("security_alias", "wrong-alias"), ("at", "2023-01-04T14:31:00Z")])
def test_every_engine_corporate_control_is_checked_before_transition(field, value):
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    event = qc.CorporateAction("terminal-1", "native:fabricated-1", "2023-01-04T14:30:00Z", "terminal", Fraction(8))
    expected = qc.prepare_corporate_control(held, event)
    before = held.sha256
    with pytest.raises(qc.RepresentationRefusal, match="mismatch"):
        qc.accept_corporate_action(held, event, dataclasses.replace(expected, **{field: value}))
    assert held.sha256 == before


def test_engine_control_rejects_equality_spoofed_cell_identifier():
    class Spoof(str):
        def __eq__(self, other):
            return True
    with pytest.raises(qc.RepresentationRefusal, match="exact_engine_control"):
        qc.EngineControl(Spoof("not-a-cell"), "alias", "2023-01-03T14:30:00Z", "event",
                          Decimal(1), Decimal(1), Decimal(0), Decimal(0), Decimal(0), Decimal(0))


def test_fill_partial_whole_share_exdate_cash_and_cross_cell_proof_refuse():
    book = qc.CellBook.new(qc.CELL_IDS[0])
    at = "2023-01-03T14:30:00Z"
    order = qc.prepare_cell_order(book, at=at, security_id="native:fabricated-1", event_id="open-1",
                order_id="order-1", side="buy", economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    control = order_control(book, order, at)
    with pytest.raises(ValueError, match="partial_fill"):
        qc.accept_cell_order(book, order, proof(order, filled_quantity=Decimal(1)), at=at, control=control)
    held = qc.accept_cell_order(book, order, proof(order), at=at, control=control)
    event = qc.CorporateAction("entitlement-1", "native:fabricated-1", "2023-01-04T14:30:00Z", "dividend_entitlement", Fraction(1), "dividend-1")
    expected = qc.prepare_corporate_control(held, event)
    with pytest.raises(qc.RepresentationRefusal, match="mismatch"):
        qc.accept_corporate_action(held, event, dataclasses.replace(expected, cash_after=Decimal("99990.333333333333333333")))
    with pytest.raises(qc.RepresentationRefusal, match="mismatch"):
        qc.accept_corporate_action(held, event, dataclasses.replace(expected, cell_id=qc.CELL_IDS[1]))


def test_prepared_order_clock_cannot_be_reassigned_after_sizing():
    book = qc.CellBook.new(qc.CELL_IDS[0])
    original_at = "2023-01-03T14:30:00Z"
    changed_at = "2023-01-03T14:31:00Z"
    order = qc.prepare_cell_order(book, at=original_at, security_id="native:fabricated-1", event_id="open-1",
                order_id="order-1", side="buy", economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    with pytest.raises(qc.RepresentationRefusal, match="clock_or_book"):
        qc.accept_cell_order(book, order, proof(order), at=changed_at,
                             control=order_control(book, order, changed_at))


@pytest.mark.parametrize("at", ["2023-01-03T14:31:00Z", "2023-01-07T14:30:00Z", "2026-09-01T13:30:00Z"])
def test_orders_refuse_nonopen_non_session_or_protected_period_clock(at):
    with pytest.raises(ValueError):
        qc.prepare_cell_order(qc.CellBook.new(qc.CELL_IDS[0]), at=at, security_id="native:fabricated-1", event_id="open-1",
                order_id="order-1", side="buy", economic_quantity=Fraction(1, 3), economic_price=Fraction(30))


@pytest.mark.parametrize("publication,expected", [("2024-03-07", "2024-03-08T14:30:00Z"),
    ("2024-03-08", "2024-03-11T13:30:00Z"), ("2024-03-28", "2024-04-01T13:30:00Z")])
def test_nominal_next_XNYS_open_respects_DST_holiday_weekend_without_availability_claim(publication, expected):
    schedule = qc.nominal_release_open(publication)
    assert schedule["entry_at"] == expected
    assert schedule["actual_availability_verified"] is False
    assert all(flag is False for flag in schedule["authority"].values())


def test_final_nominal_metadata_never_grants_a_protected_september_entry():
    schedule = qc.nominal_release_open("2026-09-10")
    assert schedule["inside_evaluation"] is False
    with pytest.raises(qc.RepresentationRefusal, match="outside_frozen"):
        trade(qc.CellBook.new(qc.CELL_IDS[0]), at=schedule["entry_at"])


def test_native_pooled_controls_reconcile_exactly_all_book_postings_and_aliases():
    books = list(qc.new_family())
    books[0] = trade(books[0])
    books[1] = trade(books[1])
    books = tuple(books)
    cash = qc._decimal(sum((Fraction(b.transport.mirror_cash) for b in books), Fraction()))
    fees = qc._decimal(sum((Fraction(b.transport.mirror_fees_paid) for b in books), Fraction()))
    holdings = tuple(sorted((qc.security_alias(b.transport.cell_id, p.security_id), p.mirror_quantity) for b in books for p in b.transport.positions))
    assert qc.reconcile_native_aggregate(books, native_cash=cash, native_fees=fees, native_holdings=holdings)["held_aliases"] == 2
    with pytest.raises(qc.RepresentationRefusal, match="pooled_control"):
        qc.reconcile_native_aggregate(books, native_cash=Decimal("4800000"), native_fees=fees, native_holdings=holdings)
    with pytest.raises(qc.RepresentationRefusal, match="alias_holdings"):
        qc.reconcile_native_aggregate(books, native_cash=cash, native_fees=fees, native_holdings=((holdings[0][0], holdings[0][1] + holdings[1][1]),))


def test_native_holdings_must_be_exact_decimal_not_numerically_equal_float():
    books = list(qc.new_family())
    books[0] = trade(books[0], quantity=Fraction(1), price=Fraction(30))
    books = tuple(books)
    cash = qc._decimal(sum((Fraction(b.transport.mirror_cash) for b in books), Fraction()))
    holdings = ((qc.security_alias(books[0].transport.cell_id, "native:fabricated-1"), 1.0),)
    with pytest.raises(ValueError):
        qc.reconcile_native_aggregate(books, native_cash=cash, native_fees=Decimal(0), native_holdings=holdings)


def test_drift_overflow_does_not_cancel_across_corporate_actions():
    held = trade(qc.CellBook.new(qc.CELL_IDS[0]))
    held = dataclasses.replace(held, transport=dataclasses.replace(held.transport,
             cumulative_cash_drift_usd=qc.MAXIMUM_COMBINED_DRIFT_USD - held.transport.cumulative_notional_drift_usd))
    with pytest.raises(ValueError, match="drift"):
        action(held, kind="terminal", dividend=None, cash=Fraction(1))


def test_unpaid_positive_receivable_or_open_position_withholds_family_completion():
    family = list(qc.new_family())
    family[0] = trade(family[0])
    with pytest.raises(qc.RepresentationRefusal, match="open_positions"):
        qc.finish_family(tuple(family))
    family[0] = action(family[0])
    family[0] = trade(family[0], at="2023-01-05T14:30:00Z", side="sell", event="open-2", order_id="order-2")
    with pytest.raises(qc.RepresentationRefusal, match="positive_unpaid"):
        qc.finish_family(tuple(family))
    family[0] = action(family[0], kind="dividend_payment", event="payment-1", at="2023-01-06T00:00:00Z")
    result = qc.finish_family(tuple(family))
    assert result["software_accounting_complete"] and result["qc_backtest_completed"] is False
    assert result["actual_outcome_looks"] == result["qc_launch_attempts"] == 0


def test_family_cannot_omit_reorder_or_duplicate_a_cell():
    books = qc.new_family()
    for broken in (books[:-1], books[::-1], (books[0],) * 48):
        with pytest.raises(qc.RepresentationRefusal):
            qc.finish_family(broken)


def test_detached_outputs_reflected_state_and_receivable_mutation_refuse():
    book = action(trade(qc.CellBook.new(qc.CELL_IDS[0])))
    detached = book.to_payload(); detached["authority"]["qc_execution_authorized"] = True
    assert book.to_payload()["authority"]["qc_execution_authorized"] is False
    object.__setattr__(book.receivables[0], "economic_amount", Fraction(99))
    with pytest.raises(qc.RepresentationRefusal, match="identity_changed"):
        book.to_payload()


def test_book_postinit_cannot_reanchor_replaced_receivable():
    book = action(trade(qc.CellBook.new(qc.CELL_IDS[0])))
    object.__setattr__(book.receivables[0], "economic_amount", Fraction(99))
    with pytest.raises(qc.RepresentationRefusal, match="identity_changed"):
        book.__post_init__()


def test_scheduled_postinit_cannot_reanchor_a_changed_clock():
    book = qc.CellBook.new(qc.CELL_IDS[0])
    order = qc.prepare_cell_order(book, at="2023-01-03T14:30:00Z", security_id="native:fabricated-1", event_id="open-1",
                order_id="order-1", side="buy", economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    object.__setattr__(order, "at", "2023-01-17T14:30:00Z")
    with pytest.raises(qc.RepresentationRefusal, match="identity_changed"):
        order.__post_init__()


@pytest.mark.parametrize("lookback", qc.LOOKBACKS)
@pytest.mark.parametrize("cost", qc.COSTS_BPS)
@pytest.mark.parametrize("role", qc.ALLOCATION_ROLES)
def test_three_release_action_and_order_path_equals_existing_fraction_book(lookback, cost, role):
    # Reuse the existing financial kernel only as a fabricated test oracle;
    # no strategy outcome file or real source is loaded or reconstructed.
    from research.short_interest_etf.latest_revised_orders import _book
    ids = ("native:fixture-a", "native:fixture-b", "native:fixture-c")
    a, b, c = ids
    records = []
    dates = ("2023-01-03", "2023-01-17", "2023-02-01")
    for i, session in enumerate(dates):
        final = i == 2
        common = list(ids if i == 0 else ids[:2])
        records.append({"settlement_date": session, "entry_session": session,
            "entry_at": session + "T14:30:00Z", "exit_session": None if final else dates[i+1],
            "exit_at": None if final else dates[i+1] + "T14:30:00Z",
            "status": "final_no_successor" if final else "ready", "common_security_ids": common,
            "high_tail_security_ids": [common[-1]], "low_tail_security_ids": [a], "refusal_reasons": []})
    bars = {(security, session): {"open": str(price)} for session, prices in (
        (dates[0], (7, 11, 13)), (dates[1], (5, 15, 8)), (dates[2], (8, 19, 8)))
        for security, price in zip(ids, prices)}
    events = [
        {"event_id": "split-a", "security_id": a, "kind": "split", "at": "2023-01-10T14:30:00Z", "split_numerator": 3, "split_denominator": 2},
        {"event_id": "entitle-a", "security_id": a, "kind": "dividend_entitlement", "at": "2023-01-11T14:30:00Z", "cash_per_share": "1", "dividend_id": "dividend-a"},
        {"event_id": "terminal-c", "security_id": c, "kind": "terminal", "at": "2023-01-13T00:00:00Z", "cash_per_share": "8"},
        {"event_id": "payment-a", "security_id": a, "kind": "dividend_payment", "at": "2023-01-20T00:00:00Z", "cash_per_share": "1", "dividend_id": "dividend-a"},
    ]
    oracle = _book(records, bars, events, lookback, cost, role)
    assert oracle["complete"]
    book = qc.CellBook.new(f"si-qc-L{lookback}-C{cost}-{role}")
    event_index = 0
    for index, row in enumerate(oracle["orders"]):
        while event_index < len(events) and qc._stamp(events[event_index]["at"]) <= qc._stamp(row["at"]):
            source = events[event_index]; event_index += 1
            held = qc._position(book.transport, source["security_id"])
            owed = any(r.security_id == source["security_id"] and r.dividend_id == source.get("dividend_id") for r in book.receivables)
            if held is None and not owed:
                continue
            changes = {"event": source["event_id"], "security": source["security_id"],
                "kind": source["kind"], "at": source["at"], "dividend": source.get("dividend_id"),
                "cash": None if source["kind"] == "split" else Fraction(source["cash_per_share"])}
            if source["kind"] == "split":
                changes.update(ratio=Fraction(source["split_numerator"], source["split_denominator"]), price=Fraction(5))
            book = action(book, **changes)
        quantity = Fraction(row["quantity"]["numerator"], row["quantity"]["denominator"])
        book = trade(book, at=row["at"], side=row["side"], security=row["security_id"],
                     event="release-" + row["settlement_date"], order_id=f"order-{index:04d}",
                     quantity=quantity, price=Fraction(row["raw_open_usd"]))
        assert book.transport.economic_cash == Fraction(row["cash_after"]["numerator"], row["cash_after"]["denominator"])
    assert book.transport.positions == () and book.receivables == ()
    financial = oracle["financial_result"]
    assert book.transport.economic_cash == Fraction(financial["ending_cash"]["numerator"], financial["ending_cash"]["denominator"])
    assert book.transport.economic_fees_paid == Fraction(financial["total_fees"]["numerator"], financial["total_fees"]["denominator"])
    assert len(book.transport.consumed_order_ids) == len(oracle["orders"])
