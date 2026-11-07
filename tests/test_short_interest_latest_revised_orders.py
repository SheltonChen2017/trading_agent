"""Invented external-file scenarios prove accounting, never market edge."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import localcontext
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf import latest_revised_orders as orders_module
from research.short_interest_etf.latest_revised_orders import (
    LatestRevisedOrderError, LatestRevisedOrderReplay, replay_latest_revised_orders,
)
from research.short_interest_etf.latest_revised_protocol import ALLOCATION_ROLES, COSTS_BPS, LOOKBACKS
from research.short_interest_etf.latest_revised_rankings import rank_latest_revised_bundle
from research.short_interest_etf.latest_revised_source import LatestRevisedBundle, load_latest_revised_bundle
from test_short_interest_latest_revised_source import fixture_documents, write_fixture


LOW = "figi:BBG000000000"
MIDDLE = "figi:BBG000000010"
ENTRY = "2024-02-13T14:30:00Z"
EXIT = "2024-02-27T14:30:00Z"


def _amount(value):
    assert set(value) == {"numerator", "denominator"}
    assert type(value["numerator"]) is int and type(value["denominator"]) is int
    result = Fraction(value["numerator"], value["denominator"])
    assert result.numerator == value["numerator"] and result.denominator == value["denominator"]
    return result


@pytest.fixture(scope="module")
def invented_documents():
    return fixture_documents()


@pytest.fixture(scope="module")
def ordinary(tmp_path_factory, invented_documents):
    bundle = load_latest_revised_bundle(write_fixture(tmp_path_factory.mktemp("latest-orders"), invented_documents))
    rankings = rank_latest_revised_bundle(bundle)
    result = replay_latest_revised_orders(bundle, rankings)
    return bundle, rankings, result, result.to_payload()


def _run(tmp_path, invented_documents, mutate):
    documents = deepcopy(invented_documents)
    mutate(documents)
    bundle = load_latest_revised_bundle(write_fixture(tmp_path, documents))
    return replay_latest_revised_orders(bundle, rank_latest_revised_bundle(bundle)).to_payload()


def _book(payload, *, cost=0, role="long_low_pressure", lookback=20):
    return next(book for book in payload["books"] if (
        book["cost_bps_per_side"], book["allocation_role"], book["lookback_sessions"]
    ) == (cost, role, lookback))


def _event(kind, at, *, security=LOW, event_id=None, **extras):
    return {"event_id": event_id or kind, "security_id": security, "kind": kind, "at": at, **extras}


def _remove_bar(documents, security, session):
    rows = documents["bars.json"]["rows"]
    rows[:] = [row for row in rows if (row["security_id"], row["session"]) != (security, session)]


def _assert_atomic_incomplete(payload, reason):
    assert payload["complete"] is False
    for book in payload["books"]:
        assert book["complete"] is False
        assert any(reason in item for item in book["refusal_reasons"])
        assert book["financial_result"] is None
        assert "orders" not in book and "cashflows" not in book
        assert all("cash_after_rebalance" not in row for row in book["release_records"])


def test_all_48_books_keep_frozen_cost_roles_and_zero_authority(ordinary):
    _, _, _, payload = ordinary
    assert payload["complete"] is True
    assert len(payload["books"]) == 48
    assert {(book["lookback_sessions"], book["cost_bps_per_side"], book["allocation_role"])
            for book in payload["books"]} == {(lookback, cost, role)
            for lookback in LOOKBACKS for cost in COSTS_BPS for role in ALLOCATION_ROLES}
    assert all(book["cost_role"] == ("primary" if book["cost_bps_per_side"] == 10 else "sensitivity")
               for book in payload["books"])
    assert payload["selected_lookback"] is None
    assert payload["authority"]["latest_revised"] is True
    assert payload["authority"]["point_in_time_data"] is False
    assert payload["authority"]["source_admitted"] is False
    assert payload["authority"]["confirmatory_eligible"] is False
    assert payload["authority"]["qc_backtest_authorized"] is False
    assert payload["authority"]["trading_authority"] is False
    assert payload["actual_outcome_access_authority"] is False
    assert payload["look_accounting"] == "runner_managed"
    assert "synthetic_only" not in payload and "empirical_looks_consumed" not in payload
    assert _amount(payload["allocated_alpha"]) == 0
    assert payload["order_replay_sha256"] == hash_payload({key: value for key, value in payload.items()
                                                         if key != "order_replay_sha256"})


@pytest.mark.parametrize("cost", COSTS_BPS)
def test_raw_open_profit_reserves_entry_fee_before_fractional_sizing(ordinary, cost):
    book = _book(ordinary[3], cost=cost)
    rate = Fraction(cost, 10000)
    quantity = Fraction(50000, 100) / (1 + rate)
    expected = quantity * 2 * 110 * (1 - rate)
    financial = book["financial_result"]
    assert _amount(financial["ending_cash"]) == expected
    assert _amount(financial["realized_pnl"]) == expected - 100000
    assert _amount(financial["net_return"]) == expected / 100000 - 1
    assert _amount(financial["total_fees"]) == quantity * 2 * (100 + 110) * rate
    buys = [row for row in book["orders"] if row["side"] == "buy"]
    assert len(buys) == 2
    assert {_amount(row["quantity"]) for row in buys} == {quantity}
    assert sum((_amount(row["notional"]) + _amount(row["fee"]) for row in buys), Fraction(0)) == 100000
    assert all(_amount(row["cash_after"]) >= 0 for row in book["orders"])
    assert financial["final_positions"] == []


def test_original_high_tail_is_avoided_and_common_baseline_retains_middle(ordinary):
    payload = ordinary[3]
    baseline = _book(payload, role="equal_weight_common")
    avoidance = _book(payload, role="avoid_high_pressure")
    low = _book(payload)
    record = baseline["release_records"][1]
    high = set(record["high_tail_security_ids"])
    low_ids = set(record["low_tail_security_ids"])
    assert len(record["common_security_ids"]) == 20
    assert len(high) == len(low_ids) == 2
    assert MIDDLE in record["common_security_ids"] and MIDDLE not in high | low_ids
    assert {row["security_id"] for row in baseline["orders"]} == set(record["common_security_ids"])
    assert {row["security_id"] for row in avoidance["orders"]} == set(record["common_security_ids"]) - high
    assert {row["security_id"] for row in low["orders"]} == low_ids
    assert all(row["side"] in ("buy", "sell") for book in payload["books"] for row in book["orders"])


@pytest.mark.parametrize("missing_indices, reason", [
    ((18, 19), "missing_common_high_pressure_tail"),
    ((0, 1), "missing_common_low_pressure_tail"),
    (tuple(range(4, 15)), "underfilled_common_intersection"),
])
def test_uncomparable_common_release_opens_no_orders_in_any_book(
    tmp_path, invented_documents, missing_indices, reason,
):
    def mutate(documents):
        past = sorted(row["session"] for row in documents["bars.json"]["rows"]
                      if row["security_id"] == LOW and row["session"] < "2024-02-13")
        for index in missing_indices:
            _remove_bar(documents, f"figi:BBG{index:09d}", past[-30])
    payload = _run(tmp_path, invented_documents, mutate)
    for book in payload["books"]:
        record = book["release_records"][1]
        assert record["status"] == "refused"
        assert reason in record["refusal_reasons"]
        assert record["execution_status"] == "retained_refusal_cash_only"
        assert record["allocation_security_ids"] == []
        assert book["orders"] == []
        assert _amount(book["financial_result"]["ending_cash"]) == 100000


def test_partial_tail_loss_keeps_surviving_original_tail_without_replacement(
    tmp_path, invented_documents,
):
    def mutate(documents):
        past = sorted(row["session"] for row in documents["bars.json"]["rows"]
                      if row["security_id"] == LOW and row["session"] < "2024-02-13")
        _remove_bar(documents, "figi:BBG000000019", past[-30])
    payload = _run(tmp_path, invented_documents, mutate)
    baseline = _book(payload, role="equal_weight_common")
    avoidance = _book(payload, role="avoid_high_pressure")
    record = baseline["release_records"][1]
    assert record["status"] == "ready"
    assert record["execution_status"] == "rebalanced"
    assert record["original_high_tail_security_ids"] == ["figi:BBG000000018", "figi:BBG000000019"]
    assert record["high_tail_security_ids"] == ["figi:BBG000000018"]
    assert len(record["common_security_ids"]) == 19
    assert {row["security_id"] for row in avoidance["orders"] if row["side"] == "buy"} == (
        set(record["common_security_ids"]) - {"figi:BBG000000018"}
    )
    assert payload["complete"] is True


def test_successor_rebalance_carries_earned_cash_instead_of_reset(tmp_path, invented_documents):
    def mutate(documents):
        documents["calendar.json"]["rows"].append({"settlement_date": "2024-02-29", "publication_date": "2024-03-11"})
        observations = documents["si-page-1.json"]["results"]
        for index in range(20):
            observations.append({"ticker": f"TOY{index:02d}", "settlement_date": "2024-02-29",
                                 "short_interest": 100000 + index * 100 + 3 * (index + 1) * 1000,
                                 "avg_daily_volume": 100000, "days_to_cover": "1"})
            for session in trading_sessions(date(2024, 2, 28), date(2024, 3, 12)):
                documents["bars.json"]["rows"].append({"security_id": f"figi:BBG{index:09d}",
                    "session": session.isoformat(), "open": "121" if session.isoformat() == "2024-03-12" else "110",
                    "close": "100", "volume": 100000, "prices_adjusted": False})
    payload = _run(tmp_path, invented_documents, mutate)
    for cost in COSTS_BPS:
        book = _book(payload, cost=cost)
        rate = Fraction(cost, 10000)
        assert _amount(book["financial_result"]["ending_cash"]) == 121000 * ((1-rate)/(1+rate)) ** 2
        middle = book["release_records"][2]
        assert _amount(middle["cash_after_exit"]) == 110000 * (1-rate)/(1+rate)
        assert _amount(middle["cash_after_rebalance"]) == 0
        at_middle = [row["side"] for row in book["orders"] if row["at"] == EXIT]
        assert at_middle == ["sell", "sell", "buy", "buy"]
        assert book["release_records"][-1]["execution_status"] == "final_exit_only"


def test_split_changes_quantity_without_double_counting_price_adjustment(tmp_path, invented_documents):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event("split", "2024-02-20T14:00:00Z", split_numerator=2, split_denominator=1)]
        for row in documents["bars.json"]["rows"]:
            if (row["security_id"], row["session"]) == (LOW, "2024-02-27"):
                row["open"] = "55"
    book = _book(_run(tmp_path, invented_documents, mutate))
    low_orders = [row for row in book["orders"] if row["security_id"] == LOW]
    assert [_amount(row["quantity"]) for row in low_orders] == [500, 1000]
    assert _amount(book["financial_result"]["ending_cash"]) == 110000
    assert _amount(book["splits"][0]["ratio"]) == 2


@pytest.mark.parametrize("ex_at,expected", [(ENTRY, 110000), ("2024-02-21T14:30:00Z", 110500), (EXIT, 110500)])
def test_dividend_entitlement_precedes_open_and_survives_exit_until_payment(tmp_path, invented_documents, ex_at, expected):
    def mutate(documents):
        documents["events.json"]["rows"] = [
            _event("dividend_entitlement", ex_at, dividend_id="d1", cash_per_share="1"),
            _event("dividend_payment", "2024-03-01T14:30:00Z", dividend_id="d1", cash_per_share="1")]
    book = _book(_run(tmp_path, invented_documents, mutate))
    assert book["complete"] is True
    assert _amount(book["financial_result"]["ending_cash"]) == expected
    assert _amount(book["financial_result"]["dividends_paid"]) == expected - 110000
    assert _amount(book["financial_result"]["outstanding_dividend_receivables"]) == 0


def test_same_clock_split_then_entitlement_locks_post_split_quantity(tmp_path, invented_documents):
    def mutate(documents):
        documents["events.json"]["rows"] = [
            _event("dividend_entitlement", "2024-02-20T14:00:00Z", dividend_id="d1", cash_per_share="1"),
            _event("split", "2024-02-20T14:00:00Z", split_numerator=2, split_denominator=1),
            _event("dividend_payment", "2024-03-01T14:30:00Z", dividend_id="d1", cash_per_share="1")]
        for row in documents["bars.json"]["rows"]:
            if (row["security_id"], row["session"]) == (LOW, "2024-02-27"):
                row["open"] = "55"
    book = _book(_run(tmp_path, invented_documents, mutate))
    entitlement = next(row for row in book["cashflows"] if row["kind"] == "dividend_entitlement")
    assert _amount(entitlement["shares_entitled"]) == 1000
    assert _amount(book["financial_result"]["ending_cash"]) == 111000


def test_dividend_locked_before_later_split_is_not_paid_on_exit_quantity(tmp_path, invented_documents):
    def mutate(documents):
        documents["events.json"]["rows"] = [
            _event("dividend_entitlement", "2024-02-20T14:00:00Z", dividend_id="d1", cash_per_share="1"),
            _event("split", "2024-02-21T14:00:00Z", split_numerator=2, split_denominator=1),
            _event("dividend_payment", "2024-03-01T14:30:00Z", dividend_id="d1", cash_per_share="1")]
        for row in documents["bars.json"]["rows"]:
            if (row["security_id"], row["session"]) == (LOW, "2024-02-27"):
                row["open"] = "55"
    book = _book(_run(tmp_path, invented_documents, mutate))
    assert _amount(book["financial_result"]["dividends_paid"]) == 500
    assert _amount(book["financial_result"]["ending_cash"]) == 110500


@pytest.mark.parametrize("payment_at,payment_amount,reason", [
    ("2024-02-20T14:00:00Z", "1", "dividend_payment_precedes_entitlement"),
    ("2024-03-01T14:00:00Z", "2", "dividend_payment_amount_mismatch"),
])
def test_dividend_payment_clock_and_economics_are_validated_before_ledger(tmp_path, invented_documents, payment_at, payment_amount, reason):
    def mutate(documents):
        documents["events.json"]["rows"] = [
            _event("dividend_entitlement", "2024-02-21T14:00:00Z", dividend_id="d1", cash_per_share="1"),
            _event("dividend_payment", payment_at, dividend_id="d1", cash_per_share=payment_amount)]
    _assert_atomic_incomplete(_run(tmp_path, invented_documents, mutate), reason)


@pytest.mark.parametrize("payment_at", [None, "2026-09-01T14:00:00Z"])
def test_positive_dividend_unpaid_by_evaluation_end_is_incomplete(tmp_path, invented_documents, payment_at):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event("dividend_entitlement", "2024-02-21T14:00:00Z", dividend_id="d1", cash_per_share="1")]
        if payment_at:
            documents["events.json"]["rows"].append(_event("dividend_payment", payment_at, dividend_id="d1", cash_per_share="1"))
    _assert_atomic_incomplete(_run(tmp_path, invented_documents, mutate), "unsettled_dividend_receivable")


def test_zero_unpaid_dividend_is_not_an_invented_positive_receivable(tmp_path, invented_documents):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event("dividend_entitlement", "2024-02-21T14:00:00Z", dividend_id="zero", cash_per_share="0")]
    book = _book(_run(tmp_path, invented_documents, mutate))
    assert book["complete"] is True and _amount(book["financial_result"]["ending_cash"]) == 110000


@pytest.mark.parametrize("cash_per_share,expected", [("0", 55000), ("10", 60000)])
def test_explicit_terminal_cash_including_zero_can_replace_missing_exit_open(tmp_path, invented_documents, cash_per_share, expected):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event("terminal", "2024-02-23T14:00:00Z", cash_per_share=cash_per_share)]
        _remove_bar(documents, LOW, "2024-02-27")
    book = _book(_run(tmp_path, invented_documents, mutate))
    assert book["complete"] is True and _amount(book["financial_result"]["ending_cash"]) == expected
    assert [(row["side"], row["security_id"]) for row in book["orders"]].count(("sell", LOW)) == 0
    terminal = next(row for row in book["cashflows"] if row["kind"] == "terminal")
    assert _amount(terminal["amount"]) == Fraction(cash_per_share) * 500


@pytest.mark.parametrize("kind", ["suspension", "unknown_terminal"])
def test_unresolved_middle_identity_action_blocks_entire_original_cohort(tmp_path, invented_documents, kind):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event(kind, "2024-02-23T14:00:00Z", security=MIDDLE)]
        _remove_bar(documents, MIDDLE, "2024-02-27")
    _assert_atomic_incomplete(_run(tmp_path, invented_documents, mutate), kind)


def test_suspension_at_entry_open_blocks_buy_even_with_supplied_price(tmp_path, invented_documents):
    def mutate(documents):
        documents["events.json"]["rows"] = [_event("suspension", ENTRY, security=MIDDLE)]
    _assert_atomic_incomplete(_run(tmp_path, invented_documents, mutate), "entry_after_suspension")


@pytest.mark.parametrize("session,label", [("2024-02-13", "missing_entry_raw_open"), ("2024-02-27", "missing_exit_raw_open")])
def test_missing_middle_price_never_reranks_or_drops_only_the_missing_name(tmp_path, invented_documents, session, label):
    payload = _run(tmp_path, invented_documents, lambda documents: _remove_bar(documents, MIDDLE, session))
    _assert_atomic_incomplete(payload, label)
    for book in payload["books"]:
        record = book["release_records"][1]
        assert MIDDLE in record["common_security_ids"]
        assert MIDDLE not in record["low_tail_security_ids"] + record["high_tail_security_ids"]
        assert record["status"] == "incomplete_common_cohort"


@pytest.mark.parametrize("role", ALLOCATION_ROLES)
def test_successor_after_evaluation_end_refuses_even_if_every_holding_terminates(role):
    securities = [f"figi:BBG{index:09d}" for index in range(10)]
    records = [{
        "settlement_date": "2026-07-31", "entry_session": "2026-08-14",
        "entry_at": "2026-08-14T13:30:00Z", "exit_session": "2026-09-02",
        "exit_at": "2026-09-02T13:30:00Z", "status": "ready",
        "common_security_ids": securities, "high_tail_security_ids": securities[-2:],
        "low_tail_security_ids": securities[:2], "refusal_reasons": [],
    }]
    bars = {(security, "2026-08-14"): {"open": "10"} for security in securities}
    events = [{
        "event_id": f"fabricated-terminal-{index}", "security_id": security,
        "kind": "terminal", "at": "2026-08-20T13:00:00Z", "cash_per_share": "10",
    } for index, security in enumerate(securities)]
    book = orders_module._book(records, bars, events, 20, 0, role)
    assert book["complete"] is False
    assert book["refusal_reasons"] == ["successor_exit_after_evaluation_end"]
    assert book["financial_result"] is None
    assert "orders" not in book and "cashflows" not in book


def test_warmup_and_final_no_successor_records_are_retained(ordinary):
    records = _book(ordinary[3])["release_records"]
    assert [row["status"] for row in records] == ["warmup", "ready", "final_no_successor"]
    assert records[0]["execution_status"] == "retained_refusal_cash_only"
    assert records[-1]["execution_status"] == "final_exit_only"
    assert "no_successor_release" in records[-1]["refusal_reasons"]
    assert records[-1]["allocation_security_ids"] == []


def test_empty_calendar_release_opens_no_new_positions(tmp_path, invented_documents):
    def mutate(documents):
        documents["si-page-1.json"]["results"][:] = [row for row in documents["si-page-1.json"]["results"]
                                                     if row["settlement_date"] != "2024-01-31"]
    payload = _run(tmp_path, invented_documents, mutate)
    assert _book(payload)["release_records"][1]["status"] == "empty"
    assert all(book["orders"] == [] and _amount(book["financial_result"]["ending_cash"]) == 100000 for book in payload["books"])


def test_single_calendar_release_retains_no_successor_without_new_entry(tmp_path, invented_documents):
    def mutate(documents):
        documents["calendar.json"]["rows"][:] = documents["calendar.json"]["rows"][:1]
        documents["si-page-1.json"]["results"][:] = [row for row in documents["si-page-1.json"]["results"]
                                                     if row["settlement_date"] == "2024-01-12"]
    payload = _run(tmp_path, invented_documents, mutate)
    for book in payload["books"]:
        assert book["orders"] == []
        assert _amount(book["financial_result"]["ending_cash"]) == 100000
        assert len(book["release_records"]) == 1
        assert book["release_records"][0]["status"] == "final_no_successor"
        assert "no_successor_release" in book["release_records"][0]["refusal_reasons"]


def test_immutable_replay_authenticates_inputs_output_and_exact_types(ordinary):
    bundle, rankings, result, _ = ordinary
    detached = result.to_payload()
    detached["books"].clear()
    assert len(result.to_payload()["books"]) == 48
    with pytest.raises(FrozenInstanceError):
        result._payload_json = "{}"
    other = replay_latest_revised_orders(bundle, rankings)
    object.__setattr__(other, "_payload_json", "{}")
    with pytest.raises(LatestRevisedOrderError, match="deterministic source-bound"):
        other.to_payload()
    with pytest.raises(LatestRevisedOrderError, match="exact LatestRevisedBundle"):
        replay_latest_revised_orders(object(), rankings)
    with pytest.raises(LatestRevisedOrderError, match="exact LatestRevisedRankings"):
        replay_latest_revised_orders(bundle, object())
    class Child(LatestRevisedOrderReplay):
        pass
    with pytest.raises(LatestRevisedOrderError, match="exact LatestRevisedOrderReplay"):
        Child(bundle, rankings)


def test_bundle_ranking_binding_and_protocol_grid_cannot_be_replaced(ordinary, monkeypatch):
    bundle, rankings, _, _ = ordinary
    payload = bundle.to_payload()
    payload["provenance"]["retrieved_at"] = "2026-10-07T12:00:01Z"
    payload["bundle_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"})
    modified = LatestRevisedBundle(canonical_json(payload))
    with pytest.raises(LatestRevisedOrderError, match="different source bundle"):
        replay_latest_revised_orders(modified, rankings)
    monkeypatch.setattr(orders_module, "COSTS_BPS", (0,))
    with pytest.raises(LatestRevisedOrderError, match="frozen exploratory protocol"):
        replay_latest_revised_orders(bundle, rankings)


def test_accounting_is_independent_of_ambient_decimal_precision(ordinary):
    bundle, rankings, result, _ = ordinary
    with localcontext() as context:
        context.prec = 2
        assert replay_latest_revised_orders(bundle, rankings).sha256 == result.sha256
