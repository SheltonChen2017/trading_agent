"""Prospective accounting policy tests; every amount/security is fabricated."""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction

import pytest

from research.short_interest_etf import native_accrual_ending as accrual

rep = accrual.rep
NATIVE = "native:fabricated-only-a"
DIVIDEND = "fabricated-dividend-a"


def dividend(**changes):
    values = dict(security_id=NATIVE, dividend_id=DIVIDEND, cash_per_share=Fraction(1),
                  scheduled_pay_date="2026-09-02", source_payload_sha256="a"*64,
                  native_class_binding_sha256="b"*64, ordinary_classification_evidence_sha256="c"*64)
    values.update(changes)
    return accrual.OrdinaryDividendAssertion(**values)


def trade(book, *, at="2026-08-17T13:30:00Z", side="buy", security=NATIVE,
          quantity=Fraction(1, 3), price=Fraction(7), event="release-1", order_id="order-1"):
    scheduled = rep.prepare_cell_order(book, at=at, security_id=security, event_id=event,
                                       order_id=order_id, side=side, economic_quantity=quantity,
                                       economic_price=price)
    order = scheduled.transport_order
    proof = rep.FillProof(**{name: getattr(order, name) for name in (
        "cell_id", "security_id", "event_id", "order_id", "side", "fill_price", "fee_usd",
        "posted_notional_usd", "posted_cash_delta_usd")}, filled_quantity=order.submitted_quantity)
    after = rep.accept_fill(book.transport, order, proof)
    p, q = rep._position(book.transport, security), rep._position(after, security)
    control = rep.EngineControl(book.transport.cell_id, rep.security_alias(book.transport.cell_id, security),
        at, event, book.transport.mirror_cash, after.mirror_cash,
        Decimal(0) if p is None else p.mirror_quantity, Decimal(0) if q is None else q.mirror_quantity,
        book.transport.mirror_fees_paid, after.mirror_fees_paid)
    return rep.accept_cell_order(book, scheduled, proof, at=at, control=control)


def action(book, kind, *, at="2026-08-20T13:30:00Z", event="entitlement-a", cash=Fraction(1)):
    value = rep.CorporateAction(event, NATIVE, at, kind, cash, DIVIDEND)
    return rep.accept_corporate_action(book, value, rep.prepare_corporate_control(book, value))


def owed_family(cash=Fraction(1)):
    books = list(rep.new_family())
    books[0] = action(trade(books[0]), "dividend_entitlement", cash=cash)
    books[0] = trade(books[0], at="2026-08-31T13:30:00Z", side="sell", event="release-2", order_id="order-2")
    return tuple(books)


def test_known_future_ordinary_dividend_is_NAV_asset_not_spendable_or_realized_cash():
    books = owed_family()
    before = books[0].sha256
    report = accrual.build_native_ending_report(books, (dividend(),)).to_payload()
    first = report["books"][0]
    assert first["receivable_face_value"] == {"numerator": 1, "denominator": 3}
    cash = books[0].transport.economic_cash
    assert first["ending_cash"] == rep._rational(cash)
    assert first["cash_realized_pnl"] == rep._rational(cash - 100000)
    assert first["provisional_nominal_accrual_NAV"] == rep._rational(cash + Fraction(1, 3))
    assert first["cash_settlement_complete"] is False
    assert first["native_reporting_computable"] is True
    row = first["ordinary_dividend_receivables"][0]
    assert row["spendable_cash"] is row["future_collection_verified"] is False
    assert row["scheduled_pay_date"] == "2026-09-02" and row["actual_bank_UTC"] is None
    assert report["all_48_native_reports_computable"] is True
    assert report["all_cash_settled"] is False
    assert report["provisional_nominal_accrual_NAV_not_realized_performance"] is True
    assert books[0].sha256 == before


def test_new_native_metric_does_not_weaken_old_cash_only_completion():
    books = owed_family()
    with pytest.raises(rep.RepresentationRefusal, match="positive_unpaid"):
        rep.finish_family(books)
    report = accrual.build_native_ending_report(books, (dividend(),)).to_payload()
    assert report["qc_backtest_completed"] is False
    assert all(value is False for value in report["authority"].values())
    assert report["actual_outcome_looks"] == report["qc_launch_attempts"] == 0
    with pytest.raises(accrual.NativeAccrualRefusal, match="not_actual_source"):
        accrual.require_actual_execution(source_admitted=True, known_receivable=True, owner_approved=True)


@pytest.mark.parametrize("field,value", [("scheduled_pay_date", None), ("scheduled_pay_date", "2026-9-02"),
    ("cash_per_share", None), ("cash_per_share", 1.0),
    ("source_payload_sha256", None), ("native_class_binding_sha256", ""),
    ("ordinary_classification_evidence_sha256", ""), ("currency", "CAD"),
    ("distribution", "special"), ("distribution", "due_bill"), ("distribution", "stock"),
    ("distribution", "contingent"), ("distribution", "unknown")])
def test_missing_amount_date_evidence_and_nonordinary_cash_never_become_zero_or_admitted(field, value):
    with pytest.raises(ValueError):
        dividend(**{field: value})


@pytest.mark.parametrize("pay_date", ["2026-08-28", "2026-08-30"])
def test_model_already_available_unpaid_receivable_is_not_disguised_as_future_known_asset(pay_date):
    with pytest.raises(accrual.NativeAccrualRefusal, match="separate_settlement"):
        accrual.build_native_ending_report(owed_family(), (dividend(scheduled_pay_date=pay_date),))


def test_cutoff_day_provider_payment_is_future_receivable_under_explicit_next_open_model():
    report = accrual.build_native_ending_report(owed_family(), (dividend(scheduled_pay_date="2026-08-31"),)).to_payload()
    row = report["books"][0]["ordinary_dividend_receivables"][0]
    assert row["modeled_payment_clock"]["modeled_cash_available_at"] == "2026-09-01T13:30:00Z"
    assert report["all_cash_settled"] is False
    assert report["books"][0]["receivable_face_value"] == {"numerator": 1, "denominator": 3}


def test_missing_ambiguous_amount_or_wrong_native_class_fails_without_partial_report():
    books = owed_family()
    for values, reason in (((), "without_ordinary"), ((dividend(), dividend()), "ambiguous"),
        ((dividend(cash_per_share=Fraction(2)),), "amount_or_native"),
        ((dividend(security_id="native:other-class"),), "without_ordinary")):
        with pytest.raises(accrual.NativeAccrualRefusal, match=reason):
            accrual.build_native_ending_report(books, values)


def test_open_position_or_positive_unresolved_terminal_is_not_cured_by_NAV_accrual():
    books = list(rep.new_family()); books[0] = trade(books[0])
    with pytest.raises(accrual.NativeAccrualRefusal, match="open_positions"):
        accrual.build_native_ending_report(tuple(books), (dividend(),))
    with pytest.raises(ValueError):
        rep.CorporateAction("unknown", NATIVE, "2026-08-20T13:30:00Z", "terminal", None)


def test_zero_entitlement_adds_no_positive_NAV_or_source_requirement():
    books = owed_family(Fraction(0))
    report = accrual.build_native_ending_report(books).to_payload()
    assert report["all_cash_settled"] is True
    assert report["books"][0]["receivable_face_value"] == {"numerator": 0, "denominator": 1}
    assert report["books"][0]["provisional_nominal_accrual_NAV"] == report["books"][0]["ending_cash"]


def test_zero_known_ordinary_assertion_adds_zero_and_matches_entitlement_metadata():
    books = owed_family(Fraction(0))
    report = accrual.build_native_ending_report(books, (dividend(cash_per_share=Fraction(0)),)).to_payload()
    assert report["all_cash_settled"] is True
    assert report["books"][0]["receivable_face_value"] == {"numerator": 0, "denominator": 1}
    with pytest.raises(accrual.NativeAccrualRefusal, match="amount_or_native"):
        accrual.build_native_ending_report(books, (dividend(cash_per_share=Fraction(1)),))


def test_48_reports_required_and_external_boolean_or_unsealed_dict_cannot_admit():
    for books in (rep.new_family()[:-1], rep.new_family()[::-1]):
        with pytest.raises(ValueError):
            accrual.build_native_ending_report(books)
    with pytest.raises(accrual.NativeAccrualRefusal, match="immutable_exact"):
        accrual.build_native_ending_report(owed_family(), ({"source_admitted": True, "cash_per_share": 1},))


def test_source_assertion_and_report_are_rebuilt_and_original_anchor_cannot_be_replaced():
    fact = dividend(); report = accrual.build_native_ending_report(owed_family(), (fact,))
    detached = report.to_payload(); detached["authority"]["source_independently_authenticated"] = True
    assert report.to_payload()["authority"]["source_independently_authenticated"] is False
    object.__setattr__(fact, "scheduled_pay_date", "2026-09-03")
    for read in (fact.to_payload, fact.__post_init__, report.to_payload):
        with pytest.raises(accrual.NativeAccrualRefusal, match="identity_changed"):
            read()


@pytest.mark.parametrize("target", ["assertion", "report"])
def test_equality_spoofed_retained_anchor_cannot_repair_source_identity(target):
    class Spoof(str):
        def __eq__(self, other): return True
        def __ne__(self, other): return False
    value = dividend() if target == "assertion" else accrual.build_native_ending_report(owed_family(), (dividend(),))
    object.__setattr__(value, "_anchor", Spoof("not-the-original-anchor"))
    with pytest.raises(accrual.NativeAccrualRefusal, match="identity_changed"):
        value.to_payload()


def test_even_unused_known_metadata_is_bound_to_the_source_report_identity():
    report = accrual.build_native_ending_report(rep.new_family(), (dividend(),))
    object.__setattr__(report, "dividends", (dividend(scheduled_pay_date="2026-09-03"),))
    with pytest.raises(accrual.NativeAccrualRefusal, match="identity_changed"):
        report.to_payload()


@pytest.mark.parametrize("pay_date,expected", [("2026-09-02", "2026-09-03T13:30:00Z"),
    ("2026-09-05", "2026-09-08T13:30:00Z"), ("2026-11-06", "2026-11-09T14:30:00Z")])
def test_date_only_modeled_clock_after_pay_day_is_not_observed_bank_UTC(pay_date, expected):
    clock = accrual.modeled_payment_clock(pay_date)
    assert clock["modeled_cash_available_at"] == expected
    assert clock["actual_bank_UTC"] is None
    assert clock["actual_bank_cash_settlement_verified"] is False
    assert clock["model_clock_not_observed_payment_fact"] is True


@pytest.mark.parametrize("lookback", rep.LOOKBACKS)
@pytest.mark.parametrize("cost", rep.COSTS_BPS)
@pytest.mark.parametrize("role", rep.ALLOCATION_ROLES)
def test_fully_paid_cutoff_metrics_equal_published_fraction_kernel(lookback, cost, role):
    from research.short_interest_etf.latest_revised_orders import _book
    other = "native:fabricated-only-b"
    dates = ("2026-08-17", "2026-08-31")
    records = [{"settlement_date": day, "entry_session": day, "entry_at": day+"T13:30:00Z",
        "exit_session": None if i else dates[1], "exit_at": None if i else dates[1]+"T13:30:00Z",
        "status": "final_no_successor" if i else "ready", "common_security_ids": [NATIVE, other],
        "high_tail_security_ids": [other], "low_tail_security_ids": [NATIVE], "refusal_reasons": []}
        for i, day in enumerate(dates)]
    bars = {(security, day): {"open": str(price)} for day in dates for security, price in ((NATIVE, 7), (other, 11))}
    events = [{"event_id": "entitle-a", "security_id": NATIVE, "kind": "dividend_entitlement", "at": "2026-08-20T13:30:00Z", "cash_per_share": "1", "dividend_id": DIVIDEND},
        {"event_id": "pay-a", "security_id": NATIVE, "kind": "dividend_payment", "at": "2026-08-28T20:00:00Z", "cash_per_share": "1", "dividend_id": DIVIDEND}]
    expected = _book(records, bars, events, lookback, cost, role)
    assert expected["complete"]
    cell = f"si-qc-L{lookback}-C{cost}-{role}"
    book = rep.CellBook.new(cell); event_index = 0
    for i, row in enumerate(expected["orders"]):
        while event_index < len(events) and rep._stamp(events[event_index]["at"]) <= rep._stamp(row["at"]):
            value = events[event_index]; event_index += 1
            if rep._position(book.transport, NATIVE) is not None or book.receivables:
                book = action(book, value["kind"], at=value["at"], event=value["event_id"])
        book = trade(book, at=row["at"], side=row["side"], security=row["security_id"],
            quantity=Fraction(row["quantity"]["numerator"], row["quantity"]["denominator"]),
            price=Fraction(row["raw_open_usd"]), event="release-"+row["settlement_date"], order_id=f"order-{i:04d}")
    books = list(rep.new_family()); books[rep.CELL_IDS.index(cell)] = book
    report = accrual.build_native_ending_report(tuple(books)).to_payload()["books"][rep.CELL_IDS.index(cell)]
    financial = expected["financial_result"]
    assert report["ending_cash"] == financial["ending_cash"]
    assert report["cash_realized_pnl"] == financial["realized_pnl"]
    assert report["provisional_nominal_accrual_NAV"] == financial["total_equity"]
    assert report["provisional_nominal_NAV_return"] == financial["net_return"]
    assert report["total_fees"] == financial["total_fees"]
    assert report["cash_settlement_complete"] is True
