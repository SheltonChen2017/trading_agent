"""Paired synthetic callback protocol; never an SDK or market acceptance test."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from unittest.mock import patch

import pytest

from data.hashing import canonical_json
from research.guidance_revision_drift.corporate_actions import CorporateAction
from research.guidance_revision_drift.fixtures import fixture_instant
from research.guidance_revision_drift.paired_bridge import (
    PairedBridgeError, PairedSyntheticBridge, SYMBOLS, action_callback_bytes,
)
from research.guidance_revision_drift.simulation import Minute, Quote


D = Decimal


def at(day="2025-04-04", hour=10, minute=0):
    return fixture_instant(date.fromisoformat(day), hour, minute)


def ack_all(bridge):
    """Invented native-style receipts; no authenticated runtime involved."""
    while bridge.pending_receipts():
        expected = bridge.pending_receipts()[0]
        protocol = bridge.snapshot()["protocol"]
        key = (expected["sleeve"], expected["order_id"])
        binding = next((b for b in protocol["bindings"] if (b["sleeve"], b["order_id"]) == key), None)
        if binding is None:
            bridge.bind(*key, 100 + len(protocol["bindings"]), SYMBOLS[key[0]])
            binding = bridge.snapshot()["protocol"]["bindings"][-1]
        native_id = binding["native_id"]
        event_id = bridge._event_ids.get((key[0], native_id), -1) + 1
        bridge.acknowledge(key[0], native_id, event_id, symbol=expected["symbol"],
            status=expected["status"], at=datetime.fromisoformat(expected["at"]),
            quantity=expected["quantity"], price=D(expected["price"]), fee=D(expected["fee"]))


def source_minute(bridge, instant, volume=10000, price="50", settlement="2025-04-07"):
    return bridge.minute("strategy", Minute("SYN-ISSUER-A", instant, D(price), D(price),
        volume, D("25000000"), date.fromisoformat(settlement)),
        comparator_quote=Quote(instant, D("100"), D("100")))


def spy_minute(bridge, instant, volume=100000, price="100", settlement="2025-04-07"):
    return bridge.minute("comparator", Minute("SYN-SPY", instant, D(price), D(price),
        volume, D("1000000000"), date.fromisoformat(settlement)))


def entered(*, source_volume=10000, comparator_volume=100000):
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    ack_all(bridge)
    source_minute(bridge, at(minute=1), source_volume)
    ack_all(bridge)
    spy_minute(bridge, at(minute=2), comparator_volume)
    ack_all(bridge)
    return bridge


def observe(bridge, instant):
    bridge.observe_accounts(instant, bridge.account_observation("strategy", instant),
                            bridge.account_observation("comparator", instant))


def action(bridge, *, issuer="SYN-ISSUER-A", kind="split", **changes):
    body = {"schema": "gdr.synthetic.corporate-action.v1", "source_id": "SYN-CALLBACK-SOURCE",
        "action_id": "SYN-CALLBACK-ACTION", "issuer_id": issuer,
        "calendar_sha256": bridge._corpus.schedule.sha256, "kind": kind,
        "effective_at": at("2025-04-07", 9, 30).isoformat().replace("+00:00", "Z"),
        "received_at": at("2025-04-04", 16).isoformat().replace("+00:00", "Z"),
        "validated_at": at("2025-04-04", 16).isoformat().replace("+00:00", "Z"),
        "ratio": "2" if kind == "split" else None,
        "amount": "1" if kind == "dividend" else None,
        "pay_session": "2025-04-08" if kind == "dividend" else None}
    body.update(changes)
    return CorporateAction.from_dict(body)


def raw_change(raw, **changes):
    body = json.loads(raw)
    body.update(changes)
    return canonical_json(body).encode()


def assert_atomic(bridge, operation, match=None):
    before = bridge.snapshot()
    with pytest.raises(ValueError, match=match):
        operation()
    assert bridge.snapshot() == before


def test_source_fill_acknowledgement_binds_comparator_budget_and_native_domains():
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    assert_atomic(bridge, lambda: bridge.bind("strategy", bridge.pending_receipts()[0]["order_id"],
                                            1, "SYN-SPY"), "binding")
    ack_all(bridge)
    source_minute(bridge, at(minute=1))
    assert not bridge.snapshot()["comparator"]["tranches"]
    assert_atomic(bridge, lambda: spy_minute(bridge, at(minute=2)), "acknowledgement missing")
    ack_all(bridge)
    state = bridge.snapshot()
    fill = state["strategy"]["fills"][0]
    tranche = state["comparator"]["tranches"][0]
    assert D(tranche["source_budget"]) == D(fill["price"]) * fill["quantity"] + D(fill["fee"])
    assert state["protocol"]["source_fill_count"] == 1
    assert {b["sleeve"] for b in state["protocol"]["bindings"]} == {"strategy", "comparator"}
    ids = [b["native_id"] for b in state["protocol"]["bindings"]]
    assert len(set(ids)) == len(ids)
    spy_minute(bridge, at(minute=2))
    ack_all(bridge)
    assert bridge.snapshot()["comparator"]["tranches"][0]["quantity"] > 0


def test_partial_fills_and_cancel_hold_reservation_until_exact_terminal_ack():
    bridge = entered(source_volume=100)
    assert bridge.snapshot()["strategy"]["positions"][0]["quantity"] == 1
    bridge.cancel(at(minute=5))
    before = bridge.snapshot()
    expected = bridge.pending_receipts()[0]
    binding = bridge.snapshot()["protocol"]["bindings"][0]
    native_id = binding["native_id"]
    event_id = bridge._event_ids[("strategy", native_id)] + 1
    bridge.acknowledge("strategy", native_id, event_id, symbol="SYN-GDR", status="cancel_pending",
        at=at(minute=5), quantity=0, price=D(0), fee=D(0))
    assert bridge.snapshot()["strategy"]["reserved_cash"] == before["strategy"]["reserved_cash"]
    assert_atomic(bridge, lambda: bridge.decision(at("2025-04-07")), "acknowledgement missing")
    ack_all(bridge)
    assert D(bridge.snapshot()["strategy"]["reserved_cash"]) == 0
    assert bridge.snapshot()["strategy"]["positions"][0]["quantity"] == 1
    assert expected["status"] == "cancel_pending"


def test_duplicate_conflicting_reordered_and_crossed_receipts_are_atomic():
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    expected = bridge.pending_receipts()[0]
    bridge.bind("strategy", expected["order_id"], 10, "SYN-GDR")
    arguments = dict(symbol="SYN-GDR", status="submitted", at=at(), quantity=0, price=D(0), fee=D(0))
    bridge.acknowledge("strategy", 10, 1, **arguments)
    before = bridge.snapshot()
    bridge.acknowledge("strategy", 10, 1, **arguments)
    assert bridge.snapshot() == before
    for updates in ({"quantity": 1}, {"fee": D(1)}, {"symbol": "SYN-SPY"},
                    {"quantity": True}, {"price": D("NaN")}, {"status": "filled"}):
        bad = {**arguments, **updates}
        assert_atomic(bridge, lambda: bridge.acknowledge("strategy", 10, 1, **bad))
    assert_atomic(bridge, lambda: bridge.acknowledge("strategy", 10, 0, **arguments), "reordered")
    assert_atomic(bridge, lambda: bridge.acknowledge("comparator", 10, 2,
                                                   **{**arguments, "symbol": "SYN-SPY"}), "unknown")


def test_all_93_sessions_complete_paired_orders_but_do_not_promote_parity():
    bridge = PairedSyntheticBridge()
    for index, session in enumerate(bridge._sessions):
        day = session.day
        settlement = bridge._sessions[min(index + 1, len(bridge._sessions) - 1)].day.isoformat()
        decision = fixture_instant(day, 10)
        bridge.decision(decision, Quote(decision, D("50"), D("50")))
        ack_all(bridge)
        source_minute(bridge, decision + timedelta(minutes=1), settlement=settlement)
        ack_all(bridge)
        spy_minute(bridge, decision + timedelta(minutes=2), settlement=settlement)
        ack_all(bridge)
        observe(bridge, decision + timedelta(minutes=2))
        bridge.cancel(decision + timedelta(minutes=5))
        ack_all(bridge)
        bridge.close(day, D("50"), D("100"))
    state = bridge.snapshot()
    assert len(state["strategy"]["navs"]) == len(state["comparator"]["navs"]) == 93
    assert not state["strategy"]["positions"]
    assert not any(t["quantity"] for t in state["comparator"]["tranches"])
    assert not state["strategy"]["receivables"] and not state["comparator"]["receivables"]
    assert not state["protocol"]["pending"]
    assert len(state["strategy"]["fills"]) == len(state["comparator"]["fills"]) == 2
    assert not state["comparator"]["synthetic_schedule_parity_blocked"]
    assert not any(state[n] for n in ("native_runtime_verified", "settlement_parity_verified", "cloud_completed", "empirical_evidence"))


def test_partial_comparator_execution_retains_permanent_blocker_after_later_fill():
    bridge = entered(comparator_volume=100)
    assert bridge.snapshot()["comparator"]["tranches"][0]["quantity"] == 1
    spy_minute(bridge, at(minute=3))
    ack_all(bridge)
    reasons = [b["reason"] for b in bridge.snapshot()["comparator"]["permanent_parity_blockers"]]
    assert "partial_or_unmatched_execution" in reasons
    assert bridge.snapshot()["comparator"]["synthetic_schedule_parity_blocked"]


def test_source_exit_cancels_unmatched_comparator_entry_through_control_receipts():
    bridge = entered(comparator_volume=100)
    bridge.close(date(2025, 5, 2), D("50"), D("100"))
    bridge.decision(at("2025-05-05"))
    ack_all(bridge)
    source_minute(bridge, at("2025-05-05", minute=1), settlement="2025-05-06")
    # A source fill creates comparator cancellation and sell expectations only
    # after its exact acknowledgement; no native rejection is hidden.
    source = bridge.pending_receipts()[0]
    # Bindings include a distinct source exit order.
    native_id = next(b["native_id"] for b in bridge.snapshot()["protocol"]["bindings"]
                     if b["sleeve"] == "strategy" and b["order_id"] == source["order_id"])
    event_id = bridge._event_ids[("strategy", native_id)] + 1
    bridge.acknowledge("strategy", native_id, event_id, symbol="SYN-GDR",
        status=source["status"], at=datetime.fromisoformat(source["at"]),
        quantity=source["quantity"], price=D(source["price"]), fee=D(source["fee"]))
    controls = [r["status"] for r in bridge.pending_receipts() if r["sleeve"] == "comparator"]
    assert "cancel_pending" in controls and "canceled" in controls and "submitted" in controls
    assert_atomic(bridge, lambda: spy_minute(bridge, at("2025-05-05", minute=2),
                                           settlement="2025-05-06"), "acknowledgement missing")
    ack_all(bridge)
    spy_minute(bridge, at("2025-05-05", minute=2), settlement="2025-05-06")
    ack_all(bridge)
    comp = bridge.snapshot()["comparator"]
    assert not any(t["quantity"] for t in comp["tranches"])
    assert "entry_unmatched_at_strategy_exit" in [b["reason"] for b in comp["permanent_parity_blockers"]]


def test_source_partial_exit_closes_corresponding_fraction_of_each_tranche():
    bridge = entered()
    bridge.close(date(2025, 5, 2), D("50"), D("100"))
    bridge.decision(at("2025-05-05"))
    ack_all(bridge)
    before = bridge.snapshot()["comparator"]["tranches"][0]["quantity"]
    source_quantity = bridge.snapshot()["strategy"]["positions"][0]["quantity"]
    source_minute(bridge, at("2025-05-05", minute=1), volume=5000, settlement="2025-05-06")
    ack_all(bridge)
    comp = bridge.snapshot()["comparator"]
    assert comp["strategy_remaining"]["SYN-ISSUER-A"] == bridge.snapshot()["strategy"]["positions"][0]["quantity"]
    executed = bridge.snapshot()["strategy"]["fills"][-1]["quantity"]
    sells = [o for o in comp["orders"] if o["side"] == "sell"]
    assert 0 < executed < source_quantity
    assert sum(o["quantity"] for o in sells) == before * executed // source_quantity > 0


def test_whole_share_actions_exact_redelivery_and_unsupported_rollback():
    bridge = entered()
    previous = bridge.snapshot()
    supplied = action(bridge)
    receipt = action_callback_bytes(supplied)
    assert bridge.action_callback(supplied, receipt) == supplied.sha256
    state = bridge.snapshot()
    assert state["strategy"]["positions"][0]["quantity"] == previous["strategy"]["positions"][0]["quantity"] * 2
    assert state["comparator"]["strategy_remaining"]["SYN-ISSUER-A"] == state["strategy"]["positions"][0]["quantity"]
    assert state["strategy"]["fills"] == previous["strategy"]["fills"]
    bridge.action_callback(supplied, receipt)
    assert bridge.snapshot() == state
    conflicting = action(bridge, ratio="3")
    assert_atomic(bridge, lambda: bridge.action_callback(conflicting, action_callback_bytes(conflicting)), "conflicting")
    for changes in ({"ratio": "0.3"}, {"issuer": "SYN-UNKNOWN"},
                    {"effective_at": at("2025-04-08", 10).isoformat().replace("+00:00", "Z")}):
        other = entered()
        supplied = action(other, **changes)
        assert_atomic(other, lambda: other.action_callback(supplied, action_callback_bytes(supplied)))
    with pytest.raises(ValueError):
        action(entered(), kind="noncash_merger")


def test_callback_input_mismatch_and_pending_action_hazard_cannot_partially_mutate():
    bridge = entered()
    supplied = action(bridge)
    receipt = action_callback_bytes(supplied)
    for raw in (raw_change(receipt, action_sha256="0" * 64), receipt + b" ",
                raw_change(receipt, extra="unknown"), b'{"schema":1,"schema":1}'):
        assert_atomic(bridge, lambda: bridge.action_callback(supplied, raw))
    pending = entered(comparator_volume=100)
    supplied = action(pending)
    assert_atomic(pending, lambda: pending.action_callback(supplied, action_callback_bytes(supplied)), "terminal paired orders")


def test_fresh_receipt_with_wrong_economics_or_status_refuses_against_expectation():
    # The duplicate-identity cases above reuse an event ID, so they are refused
    # as conflicting redeliveries. A new event ID carrying wrong economics or a
    # wrong status must be refused by the deterministic expectation itself.
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    ack_all(bridge)
    source_minute(bridge, at(minute=1))
    expected = bridge.pending_receipts()[0]
    assert expected["status"] == "filled"
    binding = next(b for b in bridge.snapshot()["protocol"]["bindings"] if b["order_id"] == expected["order_id"])
    native_id = binding["native_id"]
    event_id = bridge._event_ids[("strategy", native_id)] + 1
    exact = dict(symbol="SYN-GDR", status=expected["status"], at=datetime.fromisoformat(expected["at"]),
                 quantity=expected["quantity"], price=D(expected["price"]), fee=D(expected["fee"]))
    for updates in ({"fee": D(expected["fee"]) + 1}, {"price": D(expected["price"]) + 1},
                    {"quantity": expected["quantity"] - 1}, {"status": "partially_filled"}):
        assert_atomic(bridge, lambda: bridge.acknowledge("strategy", native_id, event_id, **{**exact, **updates}),
                      "deterministic expectation")
    bridge.acknowledge("strategy", native_id, event_id, **exact)
    assert bridge.snapshot()["protocol"]["source_fill_count"] == 1


def test_cash_action_refuses_while_a_carried_strategy_exit_is_pending():
    # The existing pending-action case leaves a comparator order open. Here the
    # comparator is fully reconciled and only a partially filled strategy exit
    # carries into the next open; the engines accept a dividend on a holding
    # with an open sell, so only the strategy half of the guard refuses it.
    bridge = entered()
    bridge.close(date(2025, 4, 4), D("40"), D("100"))
    bridge.decision(at("2025-04-07"))
    ack_all(bridge)
    source_minute(bridge, at("2025-04-07", minute=1), volume=1000, price="40", settlement="2025-04-08")
    ack_all(bridge)
    spy_minute(bridge, at("2025-04-07", minute=2), settlement="2025-04-08")
    ack_all(bridge)
    bridge.close(date(2025, 4, 7), D("40"), D("100"))
    state = bridge.snapshot()
    assert any(o["side"] == "sell" and o["status"] == "open" for o in state["strategy"]["orders"])
    assert not any(o["status"] == "open" for o in state["comparator"]["orders"])
    dividend = action(bridge, kind="dividend", action_id="SYN-CARRIED-EXIT-DIVIDEND",
                      effective_at=at("2025-04-08", 9, 30).isoformat().replace("+00:00", "Z"),
                      pay_session="2025-04-09")
    assert_atomic(bridge, lambda: bridge.action_callback(dividend, action_callback_bytes(dividend)),
                  "terminal paired orders")


def test_comparator_split_and_dividends_keep_distinct_entitlements_and_payment_dates():
    bridge = entered()
    spy = bridge.snapshot()["comparator"]["tranches"][0]["quantity"]
    supplied = action(bridge, issuer="SYN-SPY")
    bridge.action_callback(supplied, action_callback_bytes(supplied))
    assert bridge.snapshot()["comparator"]["tranches"][0]["quantity"] == spy * 2
    for issuer, identity, amount in (("SYN-ISSUER-A", "SYN-DIV-SOURCE", "1"),
                                    ("SYN-SPY", "SYN-DIV-SPY", "2")):
        supplied = action(bridge, kind="dividend", issuer=issuer, action_id=identity, amount=amount)
        bridge.action_callback(supplied, action_callback_bytes(supplied))
    state = bridge.snapshot()
    assert D(state["strategy"]["receivables"][0]["amount"]) == state["strategy"]["positions"][0]["quantity"]
    assert D(state["comparator"]["receivables"][0]["amount"]) == spy * 4
    assert state["strategy"]["receivables"][0]["pay_session"] == "2025-04-08"


@pytest.mark.parametrize("amount,pay", [("4000", "2025-04-08"), (None, None)])
def test_terminal_source_never_fabricates_comparator_exit(amount, pay):
    bridge = entered()
    before = bridge.snapshot()["comparator"]
    supplied = action(bridge, kind="terminal", amount=amount, pay_session=pay)
    bridge.action_callback(supplied, action_callback_bytes(supplied))
    comp = bridge.snapshot()["comparator"]
    assert comp["orders"] == before["orders"] and comp["tranches"] == before["tranches"]
    assert comp["study_completion_blocked"]
    assert "source_terminal_comparator_schedule_unsupported" in [b["reason"] for b in comp["permanent_parity_blockers"]]


def test_component_account_observations_reject_aliases_and_hidden_receivables():
    bridge = entered(source_volume=100)
    instant = at(minute=2)
    strategy = bridge.account_observation("strategy", instant)
    comp = bridge.account_observation("comparator", instant)
    for changes in ({"settled_cash": "100000"}, {"reserved_cash": "0"},
                    {"available_cash": "100000"}, {"quantity": True},
                    {"immediate_cash": "NaN"}, {"extra": 1}, {"settlement_parity_verified": True}):
        assert_atomic(bridge, lambda: bridge.observe_accounts(instant, raw_change(strategy, **changes), comp), "mismatch")
    bridge.observe_accounts(instant, strategy, comp)
    before = bridge.snapshot()
    bridge.observe_accounts(instant, strategy, comp)
    assert bridge.snapshot() == before
    assert_atomic(bridge, lambda: bridge.observe_accounts(instant, raw_change(strategy, quantity=999), comp), "conflicting")
    assert_atomic(bridge, lambda: bridge.observe_accounts(instant + timedelta(minutes=1),
        bridge.account_observation("strategy", instant + timedelta(minutes=1)),
        bridge.account_observation("comparator", instant + timedelta(minutes=1))), "current callback clock")


def test_explicit_dividend_settlement_early_wrong_and_duplicate_observations_are_atomic():
    bridge = entered()
    supplied = action(bridge, kind="dividend")
    bridge.action_callback(supplied, action_callback_bytes(supplied))
    early = at("2025-04-07", 9, 30)
    expected = deepcopy(bridge)
    # An invented observer wrongly claims future proceeds as settled at ex-open.
    raw = json.loads(expected.account_observation("strategy", early))
    cash = D(raw["settled_cash"])
    proceeds = sum(D(r["amount"]) for r in raw["receivables"])
    early_wrong = raw_change(expected.account_observation("strategy", early),
                             settled_cash=str(cash + proceeds), receivables=[])
    assert_atomic(bridge, lambda: bridge.observe_accounts(early, early_wrong,
        expected.account_observation("comparator", early), settle=True), "mismatch")
    observe(bridge, early)
    pay = at("2025-04-08", 9, 30)
    observer = deepcopy(bridge)
    observer._strategy.advance(pay)
    observer._comparator.advance(pay)
    strategy = observer.account_observation("strategy", pay)
    comparator = observer.account_observation("comparator", pay)
    assert_atomic(bridge, lambda: bridge.observe_accounts(pay,
        raw_change(strategy, receivables=raw["receivables"]), comparator, settle=True), "mismatch")
    bridge.observe_accounts(pay, strategy, comparator, settle=True)
    state = bridge.snapshot()
    assert D(state["strategy"]["settled_cash"]) == cash + proceeds
    assert state["strategy"]["receivables"] == []
    bridge.observe_accounts(pay, strategy, comparator, settle=True)
    assert bridge.snapshot() == state
    assert_atomic(bridge, lambda: bridge.observe_accounts(pay, early_wrong, comparator, settle=True), "conflicting")


def test_trace_capacity_refusal_rolls_back_both_engines_and_protocol():
    bridge = entered()
    with patch("research.guidance_revision_drift.paired_bridge.MAX_PROTOCOL_RECORDS", bridge.snapshot()["protocol"]["trace_count"]):
        assert_atomic(bridge, lambda: bridge.decision(at("2025-04-07")), "capacity")


def test_better_comparator_fill_keeps_budget_mismatch_beyond_rounding():
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    ack_all(bridge)
    source_minute(bridge, at(minute=1))
    ack_all(bridge)
    spy_minute(bridge, at(minute=2), price="99")
    ack_all(bridge)
    comp = bridge.snapshot()["comparator"]
    assert "budget_mismatch_beyond_rounding" in [b["reason"] for b in comp["permanent_parity_blockers"]]
    assert comp["synthetic_schedule_parity_blocked"]


def test_failure_after_first_action_sleeve_rolls_back_the_paired_transition():
    bridge = entered()
    supplied = action(bridge)
    with patch("research.guidance_revision_drift.comparison.MatchedComparator.apply_source_split",
               side_effect=ValueError("invented second-sleeve callback failure")):
        assert_atomic(bridge, lambda: bridge.action_callback(supplied, action_callback_bytes(supplied)), "second-sleeve")


def test_friday_sale_proceeds_remain_unspendable_until_explicit_monday_open():
    bridge = entered()
    bridge.close(date(2025, 4, 10), D("40"), D("100"))
    bridge.decision(at("2025-04-11"))
    ack_all(bridge)
    source_minute(bridge, at("2025-04-11", minute=1), settlement="2025-04-14")
    ack_all(bridge)
    spy_minute(bridge, at("2025-04-11", minute=2), settlement="2025-04-14")
    ack_all(bridge)
    instant = at("2025-04-11", minute=2)
    strategy = bridge.account_observation("strategy", instant)
    comparator = bridge.account_observation("comparator", instant)
    body = json.loads(strategy)
    assert body["receivables"][0]["pay_session"] == "2025-04-14"
    assert D(body["available_cash"]) < D(body["immediate_cash"])
    for changes in ({"receivables": []}, {"settled_cash": body["immediate_cash"]},
                    {"available_cash": body["immediate_cash"]}):
        assert_atomic(bridge, lambda: bridge.observe_accounts(instant,
            raw_change(strategy, **changes), comparator), "mismatch")
    observe(bridge, instant)
    pay = at("2025-04-14", 9, 30)
    observer = deepcopy(bridge)
    observer._strategy.advance(pay)
    observer._comparator.advance(pay)
    strategy = observer.account_observation("strategy", pay)
    comparator = observer.account_observation("comparator", pay)
    bridge.observe_accounts(pay, strategy, comparator, settle=True)
    assert not bridge.snapshot()["strategy"]["receivables"]
    assert not bridge.snapshot()["comparator"]["receivables"]
    assert not bridge.snapshot()["settlement_parity_verified"]


def test_real_identities_wrong_symbol_and_same_bar_execution_refuse():
    bridge = PairedSyntheticBridge()
    bridge.decision(at(), Quote(at(), D("50"), D("50")))
    ack_all(bridge)
    with pytest.raises(ValueError, match="SYN-"):
        Minute("AAPL", at(minute=1), D("50"), D("50"), 10000, D("25000000"), date(2025, 4, 7))
    for issuer, sleeve in (("SYN-OTHER", "strategy"), ("SYN-SPY", "strategy"), ("SYN-ISSUER-A", "comparator")):
        minute = Minute(issuer, at(minute=1), D("50"), D("50"), 10000,
                        D("25000000"), date(2025, 4, 7))
        assert_atomic(bridge, lambda: bridge.minute(sleeve, minute,
                    comparator_quote=Quote(at(minute=1), D("100"), D("100"))), "issuer")
    source_minute(bridge, at())
    assert bridge.snapshot()["strategy"]["fills"] == []
