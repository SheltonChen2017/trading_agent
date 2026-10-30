"""Synthetic supplied-account observations only; no private/native effects."""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os

import pytest
import test_qc_comparison_20261028_completion as fixture
from research.target_price_revisions_qc import comparison_20261028_accounting as a

c, e, N = a.c, a.e, a.e.JsonNumber
NY = ZoneInfo("America/New_York")
SID, OTHER = "SYNTH R735QTJ8XC9X", "OTHER R735QTJ8XC9X"


@pytest.fixture(scope="module")
def original():
    return Path("research/target_price_revisions_qc/extended_calendar.json").read_bytes()


def utc(day, hour=9, minute=30):
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=NY).astimezone(timezone.utc)


def number(value):
    return a.native._decimal_token(Fraction(value))


def envelope(endpoint, request, response):
    return {"schema": "tpr-ext26-native-read-envelope-v1", "endpoint": endpoint,
        "request": request, "response": response,
        "returned_identity_checks": a.collector._returned_identity(response, request["projectId"], request["backtestId"])}


def fill(oid=1, sid=SID, day="2021-01-04", quantity=10, price=20, fee="0.1", status="Filled", cash="99799.9", held=10):
    return {"order_id": oid, "security_id": sid, "utc": utc(day).isoformat(), "status": status,
        "quantity": fixture.rat(quantity), "price": fixture.rat(price), "fee": fixture.rat(fee), "fee_currency": "USD",
        "native_final_exception": False, "cash_ledger": fixture.rat(cash), "quantity_ledger": None if held is None else fixture.rat(held)}


def native_event(row, identity):
    instant = datetime.fromisoformat(row["utc"])
    return {"algorithmId": "1" * 32, "orderId": N(str(row["order_id"])), "orderEventId": N(str(identity)),
        "id": "synthetic-event-" + str(row["order_id"]) + "-" + str(identity),
        "time": N(str(int(instant.timestamp()))), "status": row["status"][0].lower() + row["status"][1:],
        "quantity": N("10"), "fillQuantity": number(c._fraction(row["quantity"])),
        "fillPrice": number(c._fraction(row["price"])), "fillPriceCurrency": "USD",
        "orderFeeAmount": number(c._fraction(row["fee"])), "orderFeeCurrency": row["fee_currency"]}


def rebind_api(p, width=20):
    pages = []
    total, job, project = len(p["orders"]), p["binding"]["job_id"], p["binding"]["project_id"]
    for start in range(0, max(1, total), width):
        response = {"success": True, "projectId": N(str(project)), "backtestId": job,
            "length": N(str(total)), "orders": p["orders"][start:start + width]}
        pages.append(e.canonical(envelope("backtests/orders/read", {
            "projectId": project, "backtestId": job, "start": start, "end": start + width}, response)))
    chart_raw = e.canonical(p["chart"])
    p.update(order_pages=pages, chart_raw=chart_raw, api_binding={"schema": "tpr-cmp28-accounting-inputs-v1",
        "project_id": project, "job_id": job, "config_sha256": p["binding"]["config_sha256"],
        "rendered_source_closure_sha256": p["binding"]["rendered_source_closure_sha256"],
        "order_pages": [{"sha256": fixture.sha(raw), "bytes": len(raw)} for raw in pages],
        "chart": {"sha256": fixture.sha(chart_raw), "bytes": len(chart_raw)}})
    return p


def package(original, *, zero_fee=False, zero_fee_amount="0.25", actions=(), fractional=False, multiples=False, arm="cap_off", sell=False):
    p = fixture.pack(original, arm)
    sessions = p["calendar"]["valuation_sessions"]
    if sell:
        # Buy 10 at 20 (fee 0.10), then sell 4 at 25 (fee 0.20): the sale credits
        # cash net of its fee and leaves 6 held, marked at the sale price.
        fills = [fill(), fill(oid=2, quantity=-4, price=25, fee="0.2", cash="99899.7", held=6)]
        cash, q, price, fees = Fraction("99899.7"), 6, Fraction(25), Fraction("0.3")
    elif multiples:
        fills = [fill(quantity=1, fee="0.01", status="PartiallyFilled", cash="99979.99", held=1),
            fill(quantity=1, fee="0.01", status="PartiallyFilled", cash="99959.98", held=2),
            fill(quantity=1, fee="0.01", status="Filled", cash="99939.97", held=3)]
        cash, q, price, fees = Fraction("99939.97"), 3, Fraction(20), Fraction("0.03")
    else:
        fills = [fill()]
        cash, q, price, fees = Fraction("99799.9"), 10, Fraction(20), Fraction("0.1")
    if zero_fee:
        fills.append(fill(oid=2, sid=OTHER, quantity=0, price=0, fee=zero_fee_amount, status="Submitted", cash=Fraction("99799.9") - Fraction(zero_fee_amount), held=None))
        cash, fees = Fraction("99799.9") - Fraction(zero_fee_amount), Fraction("0.1") + Fraction(zero_fee_amount)
    records = [{"kind": "FILL", "payload": row} for row in fills]
    actions = list(actions)
    for row in actions:
        if row["utc"] < fills[0]["utc"]:
            records.insert(0, {"kind": "ACTION", "payload": row})
    first_nav = cash + q * price
    max_name, name_breaches = Fraction(0), 0
    for n, day in enumerate(sessions):
        if n == 1:
            for row in actions:
                if row["utc"] >= fills[0]["utc"]:
                    records.append({"kind": "ACTION", "payload": row})
            if fractional:
                # The actual missing event-time CIL amount is deliberately not
                # in ACTION. These supplied producer snapshots include it.
                cash, q, price = Fraction("99819.9"), 3, Fraction(60)
            elif actions and any(row["action"] == "split" and row["occurred"] and row["utc"] >= fills[0]["utc"] for row in actions):
                cash, q, price = cash + 10, 20, Fraction(10)
        nav, value = cash + q * price, q * price
        exposure = value / nav
        max_name = max(max_name, exposure)
        name_breaches += exposure > Fraction(1, 10)
        records.append({"kind": "NAV", "payload": {"session": day, "nav": a._text(nav), "cash": a._text(cash),
            "gross_exposure": a._text(value / nav), "risk_within_unlevered_account": True,
            "max_name_exposure": a._text(exposure), "name_cap_is_prior_close_soft_target": True,
            "position_ledger_mismatches": 0, "cash_ledger_residual": "0", "nav_ledger_residual": "0",
            "holdings": [{"security_id": SID, "quantity": fixture.rat(q), "value": fixture.rat(value)}],
            "cash_ledger": fixture.rat(cash), "fees": fixture.rat(fees), "independent_holdings_value": fixture.rat(value),
            "holdings_value_residual": fixture.rat(0), "raw_marks": [{"security_id": SID, "price": fixture.rat(price),
                "mark_utc": utc(day, 16, 0).isoformat()}]}})
    summary = p["summary"]
    summary.update(fill_events=sum(c._fraction(row["quantity"]) != 0 for row in fills), submitted_orders=len({row["order_id"] for row in fills}),
        requested_shares=fixture.rat(sum(abs(c._fraction(row["quantity"])) for row in fills)),
        submitted_shares=fixture.rat(sum(abs(c._fraction(row["quantity"])) for row in fills)),
        filled_shares=fixture.rat(sum(abs(c._fraction(row["quantity"])) for row in fills)), fees=fixture.rat(fees),
        last_observed_nav=fixture.rat(nav), final_nav=fixture.rat(nav), max_name_exposure=fixture.rat(max_name),
        name_soft_cap_breaches=int(name_breaches))
    records.append({"kind": "SUMMARY", "payload": summary})
    for index, row in enumerate(records): row["ordinal"] = index + 1
    p["records"] = records
    fixture.rebuild(p)
    orders = []
    for oid in sorted({row["order_id"] for row in fills}):
        selected = [row for row in fills if row["order_id"] == oid]
        orders.append({"id": N(str(oid)), "status": N("3" if any(c._fraction(row["quantity"]) for row in selected) else "1"),
            "time": utc(sessions[0], 9, 20).isoformat(), "symbol": {"id": selected[0]["security_id"], "value": "PRIVATE-SYNTHETIC-ALIAS"},
            "quantity": N("999"), "price": N("999999"), "priceCurrency": "EUR",
            "events": [native_event(row, index) for index, row in enumerate(selected)]})
    values = [[N(str(int(utc(row["payload"]["session"], 16, 1).timestamp()))), number(a._smart_round(Fraction(row["payload"]["nav"])))]
        for row in records if row["kind"] == "NAV"]
    response = {"success": True, "chart": {"name": "EXT26 Account NAV", "series": {"NAV": {
        "name": "NAV", "unit": "$", "seriesType": N("0"), "values": values}}}}
    chart = envelope("backtests/chart/read", {"projectId": summary["project_id"], "backtestId": summary["job_id"],
        "name": "EXT26 Account NAV", "start": a.collector.CHART_START, "end": a.collector.CHART_END,
        "count": a.collector.CHART_COUNT}, response)
    p.update(orders=orders, chart=chart)
    return rebind_api(p)


def run(p):
    return a.audit_accounting(*p["raws"], binding=p["binding"], chunks=p["chunks"], order_pages=p["order_pages"],
        chart_raw=p["chart_raw"], api_binding=p["api_binding"])


def action(kind, *, value="0.5", day="2021-01-05", occurred=True):
    return {"action": kind, "security_id": SID, "utc": utc(day).isoformat(), "value": fixture.rat(value), "occurred": occurred}


@pytest.fixture(autouse=True)
def no_effects(monkeypatch):
    def forbidden(*_args, **_kwargs): raise AssertionError("I/O is forbidden in pure auditor")
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(a.collector, "credential", forbidden)
    monkeypatch.setattr(a.collector.http.client, "HTTPSConnection", forbidden)
    monkeypatch.setattr(a.collector.subprocess, "run", forbidden)
    monkeypatch.setattr(a.collector.Operations, "__init__", forbidden)


@pytest.mark.parametrize("arm", c.CANDIDATES)
def test_full_axis_replay_all_five_candidates_without_old_attempt_cap(original, arm):
    p = package(original, arm=arm)
    report = run(p)
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["daily_nav_observations"] == 1449
    assert report["replayed_fees"] == fixture.rat("0.1")
    assert report["native_order_census"]["orders"] == 1
    assert report["max_nav_residual"] == fixture.rat(0)
    for key in ("native_origin_authenticated", "backend_durability_proven", "historical_pit_authenticated", "data_rights_authenticated",
                "share_basis_authenticated", "full_evidence_retrieval_verified", "source_inputs_admitted", "strategy_accepted", "canonical_admission", "native_permission"):
        assert report[key] is False
    assert report["accepted_performance"] is None
    assert SID not in json.dumps(report) and "PRIVATE-SYNTHETIC-ALIAS" not in json.dumps(report)


def test_sell_fill_credits_cash_net_of_fee_reduces_holding_and_counts_absolute_shares(original):
    """TPR-CR32: the sell side of the replay arithmetic was never exercised before."""
    report = run(package(original, sell=True))
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["replayed_fees"] == fixture.rat("0.3")
    assert report["native_order_census"]["orders"] == 2
    assert report["native_order_census"]["absolute_filled_shares"] == fixture.rat(14)
    assert report["daily_nav_observations"] == 1449
    # A gross credit (fee ignored) or a debit of the sale must not reconcile.
    for wrong in ("99899.9", "99699.7"):
        p = package(original, sell=True)
        sale = next(row for row in p["records"] if row["kind"] == "FILL" and row["payload"]["order_id"] == 2)
        sale["payload"]["cash_ledger"] = fixture.rat(wrong)
        fixture.rebuild(p)
        bad = run(p)
        assert bad["cash_replay_within_cent"] is False and bad["supplied_evidence_accounting_reconciled"] is False


def test_zero_fill_fee_charged_and_untouched_quantity_none_not_made_into_holding(original):
    report = run(package(original, zero_fee=True))
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["replayed_fees"] == fixture.rat("0.35")
    assert report["native_order_census"]["events"] == 2


def test_duplicate_economics_use_multiplicity_not_sets(original):
    p = package(original, multiples=True)
    assert run(p)["supplied_evidence_accounting_reconciled"] is True
    p["orders"][0]["events"].pop(0); rebind_api(p)
    report = run(p)
    assert report["native_journal_fill_fee_agreement"] is False
    assert report["unknown_reasons"]["native_journal_event_multiplicity_mismatch"] == 1


def test_same_callback_dividend_before_split_despite_opposite_journal_order(original):
    p = package(original, actions=[action("split"), action("dividend", value=1)])
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_warmup_actions_do_not_create_evaluation_cash_or_quantities(original):
    p = package(original, actions=[action("split", day="2020-12-31"), action("dividend", value=999, day="2020-12-31")])
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_split_warning_has_no_effect(original):
    p = package(original, actions=[action("split", occurred=False)])
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_fractional_held_split_cannot_be_repaired_from_later_cash(original):
    p = package(original, actions=[action("split", value=3)], fractional=True)
    report = run(p)
    assert report["quantity_replay_matches_journal"] is True
    assert report["native_journal_fill_fee_agreement"] is True
    assert report["cash_replay_within_cent"] is False
    assert report["daily_nav_replay_within_cent"] is False
    assert report["max_cash_residual"] is report["max_nav_residual"] is None
    assert report["fractional_held_splits_with_unobserved_cash_in_lieu"] == 1
    assert report["supplied_evidence_accounting_reconciled"] is False


@pytest.mark.parametrize("field", ["orderFeeAmount", "orderFeeCurrency", "fillPriceCurrency", "fillQuantity", "orderEventId", "time"])
def test_missing_native_fields_stay_unknown(original, field):
    p = package(original)
    p["orders"][0]["events"][0].pop(field)
    if field == "orderEventId": p["orders"][0]["events"][0].pop("id")
    rebind_api(p)
    report = run(p)
    assert report["supplied_evidence_accounting_reconciled"] is False
    assert report["native_journal_fill_fee_agreement"] is False
    assert report["unknown_reasons"]
    if field == "orderFeeAmount": assert report["native_order_census"]["reported_fees"] is None
    if field == "fillQuantity": assert report["native_order_census"]["absolute_filled_shares"] is None


@pytest.mark.parametrize("field,value", [("algorithmId", "2" * 32), ("orderId", N("999"))])
def test_foreign_event_identity_refused(original, field, value):
    p = package(original); p["orders"][0]["events"][0][field] = value; rebind_api(p)
    with pytest.raises(a.AccountingRefusal, match="^CMP28 supplied account replay refused$"): run(p)


@pytest.mark.parametrize("field", ["orderEventId", "id"])
def test_duplicate_native_event_identity_refused(original, field):
    p = package(original, multiples=True)
    p["orders"][0]["events"][1][field] = p["orders"][0]["events"][0][field]; rebind_api(p)
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("field,value", [("job_id", "2" * 32), ("project_id", 37650453), ("config_sha256", "f" * 64),
    ("rendered_source_closure_sha256", "e" * 64), ("schema", "old"), ("foreign", False)])
def test_api_header_binding_default_denies_drift(original, field, value):
    p = package(original); p["api_binding"][field] = value
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("which", ["order", "chart", "chunk"])
def test_actual_input_hashes_bound_before_parsing(original, which):
    p = package(original)
    if which == "order": p["order_pages"][0] += b" "
    if which == "chart": p["chart_raw"] += b" "
    if which == "chunk": p["chunks"][0] += b" "
    with pytest.raises(a.AccountingRefusal): run(p)


def test_identical_native_order_price_and_currency_are_not_fill_evidence(original):
    p = package(original)
    assert p["orders"][0]["price"].fraction() == 999999
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_changed_native_fill_price_does_not_pass_from_reported_cash_booleans(original):
    p = package(original); p["orders"][0]["events"][0]["fillPrice"] = N("21"); rebind_api(p)
    assert run(p)["supplied_evidence_accounting_reconciled"] is False


@pytest.mark.parametrize("change", ["missing_mark", "extra_mark", "duplicate_holding", "negative_quantity", "stale_mark"])
def test_held_sid_marks_quantities_and_session_not_defaulted(original, change):
    p = package(original)
    row = next(record["payload"] for record in p["records"] if record["kind"] == "NAV")
    if change == "missing_mark": row["raw_marks"].clear()
    if change == "extra_mark": row["raw_marks"].append({**row["raw_marks"][0], "security_id": OTHER})
    if change == "duplicate_holding": row["holdings"].append(deepcopy(row["holdings"][0]))
    if change == "negative_quantity": row["holdings"][0]["quantity"] = fixture.rat(-1)
    if change == "stale_mark": row["raw_marks"][0]["mark_utc"] = utc("2021-01-03", 16).isoformat()
    fixture.rebuild(p)
    with pytest.raises(a.AccountingRefusal): run(p)


def test_changed_recorded_ledger_cannot_be_oracle(original):
    p = package(original)
    p["records"][0]["payload"]["cash_ledger"] = fixture.rat(100000)
    fixture.rebuild(p)
    report = run(p)
    assert report["cash_replay_within_cent"] is False
    assert report["supplied_evidence_accounting_reconciled"] is False


@pytest.mark.parametrize("kind", ["split", "dividend"])
def test_duplicate_action_sid_session_refused(original, kind):
    p = package(original, actions=[action(kind, value=1), action(kind, value=1)])
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("value,expected", [("1000", "1000"), ("1000.0000499", "1000"), ("1000.00005", "1000"),
    ("1000.00015", "1000.0002"), ("999.123456789", "999.1235"), ("0.00123456789", "0.001234568"),
    ("0.00000012345675", "0.0000001234568")])
def test_public_smart_rounding_contract_exact_ties_and_threshold(value, expected):
    assert a._smart_round(Fraction(value)) == Fraction(expected)


def test_chart_census_complete_but_value_mismatch_cannot_pass(original):
    p = package(original)
    p["chart"]["response"]["chart"]["series"]["NAV"]["values"][0][1] = N("100000")
    rebind_api(p)
    assert run(p)["native_chart_rounding_agreement"] is False


@pytest.mark.parametrize("change", ["wrong_clock", "missing_day", "loading", "foreign_project"])
def test_chart_oracle_preserves_unavailable_and_foreign_identity(original, change):
    p = package(original)
    if change == "wrong_clock": p["chart"]["response"]["chart"]["series"]["NAV"]["values"][0][0] = N(str(int(utc("2021-01-04", 16, 0).timestamp())))
    if change == "missing_day": p["chart"]["response"]["chart"]["series"]["NAV"]["values"].pop()
    if change == "loading": p["chart"]["response"]["status"] = "loading"
    if change == "foreign_project": p["chart"]["response"]["projectId"] = N("1")
    if change == "foreign_project":
        # Recompute structural returned-ID claims cannot bless a foreign field.
        p["chart"]["returned_identity_checks"] = {"observed_project_id_fields": 1, "observed_backtest_id_fields": 0,
            "absent_identifiers_inferred": False, "provider_authenticity_independently_verified": False}
    rebind_api(p)
    if change == "foreign_project":
        with pytest.raises(a.AccountingRefusal): run(p)
    else:
        report = run(p)
        assert report["native_chart_rounding_agreement"] is False
        assert report["unknown_reasons"]["native_daily_nav_chart_unavailable"] == 1


def test_hundred_order_window_refused_per_official_schema(original):
    p = package(original); rebind_api(p, width=100)
    with pytest.raises(a.AccountingRefusal): run(p)


def test_explicit_zero_empty_fee_currency_preserved_without_usd_inference_or_cash_blocker(original):
    p = package(original, zero_fee=True, zero_fee_amount="0")
    p["records"][1]["payload"]["fee_currency"] = ""
    p["orders"][1]["events"][0]["orderFeeCurrency"] = ""
    fixture.rebuild(p); rebind_api(p)
    report = run(p)
    assert report["native_order_census"]["currency_fields_complete"] is False
    assert report["native_order_census"]["currency_inference_performed"] is False
    assert report["unknown_reasons"]["native_zero_fee_currency_unobserved"] == 1
    assert report["native_journal_fill_fee_agreement"] is True
    assert report["cash_replay_within_cent"] is True
    assert report["supplied_evidence_accounting_reconciled"] is True


@pytest.mark.parametrize("currency", ["", "EUR"])
def test_missing_or_other_currency_on_nonzero_fee_stays_unavailable(original, currency):
    p = package(original); p["orders"][0]["events"][0]["orderFeeCurrency"] = currency; rebind_api(p)
    report = run(p)
    assert report["native_order_census"]["currency_fields_complete"] is False
    assert report["native_journal_fill_fee_agreement"] is False
    assert report["supplied_evidence_accounting_reconciled"] is False


def test_distinct_order_ids_allow_same_per_order_native_event_id_and_twenty_row_windows(original):
    p = package(original)
    for oid in range(2, 22):
        row = fill(oid=oid, sid=OTHER, quantity=0, price=0, fee=0, status="Submitted", cash="99799.9", held=None)
        p["orders"].append({"id": N(str(oid)), "status": N("1"), "time": utc("2021-01-04", 9, 20).isoformat(),
            "symbol": {"id": OTHER}, "events": [native_event(row, 0)]})
    rebind_api(p, width=20)
    report = run(p)
    assert len(p["order_pages"]) == 2 and report["native_order_census"]["orders"] == 21
    assert report["native_journal_fill_fee_agreement"] is False  # Extra native events never silently dropped.


def test_extra_empty_census_page_is_not_a_fresh_order_census(original):
    p = package(original); p["orders"] = []; rebind_api(p)
    p["order_pages"].append(p["order_pages"][0])
    p["api_binding"]["order_pages"].append(deepcopy(p["api_binding"]["order_pages"][0]))
    with pytest.raises(a.AccountingRefusal): run(p)


def test_actual_attempt_seven_accepted_by_cmp_binding_without_legacy_three_cap(original):
    p = package(original)
    p["config"]["attempt"] = p["summary"]["attempt"] = 7
    config_hash = fixture.sha(fixture.wire(p["config"]))
    p["summary"]["config_sha256"] = config_hash
    p["prefix"] = f"tpr-cmp28/evidence/{c.STUDY}/{p['config']['operation_id']}/{config_hash}/attempt-7/37650980/{'1' * 32}/"
    fixture.rebuild(p); rebind_api(p)
    report = run(p)
    assert report["attempt"] == 7 and report["supplied_evidence_accounting_reconciled"] is True


def test_same_instant_aware_action_spellings_do_not_change_dividend_split_order(original):
    split, dividend = action("split"), action("dividend", value=1)
    dividend["utc"] = dividend["utc"].replace("+00:00", "Z")
    p = package(original, actions=[split, dividend])
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_daily_position_mismatch_claim_is_checked_not_trusted(original):
    p = package(original)
    row = next(record["payload"] for record in p["records"] if record["kind"] == "NAV")
    row["position_ledger_mismatches"] = 1
    fixture.rebuild(p)
    assert run(p)["quantity_replay_matches_journal"] is False


def test_daily_risk_breach_cannot_disappear_into_summary_zero(original):
    p = package(original)
    row = next(record["payload"] for record in p["records"] if record["kind"] == "NAV")
    row["cash"] = "-1"; row["risk_within_unlevered_account"] = False
    fixture.rebuild(p)
    report = run(p)
    assert report["replayed_risk_breaches"] == 1
    assert report["summary_replayed_aggregates_agree"] is False
    assert report["supplied_evidence_accounting_reconciled"] is False


def test_final_day_late_fee_cannot_be_hidden_after_last_frozen_nav(original):
    p = package(original)
    row = fill(oid=2, sid=OTHER, day="2026-10-09", quantity=0, price=0, fee=1, status="Submitted", cash="99798.9", held=None)
    row["utc"] = utc("2026-10-09", 16, 2).isoformat()
    p["records"].insert(-1, {"kind": "FILL", "payload": row})
    for index, record in enumerate(p["records"]): record["ordinal"] = index + 1
    fixture.rebuild(p)
    with pytest.raises(a.AccountingRefusal): run(p)


def test_nonfinite_native_numeric_token_refused_body_free(original):
    p = package(original)
    raw = p["order_pages"][0].replace(b'"orderFeeAmount":0.1', b'"orderFeeAmount":NaN')
    assert raw != p["order_pages"][0]
    p["order_pages"][0] = raw
    p["api_binding"]["order_pages"][0] = {"sha256": fixture.sha(raw), "bytes": len(raw)}
    with pytest.raises(a.AccountingRefusal, match="^CMP28 supplied account replay refused$"): run(p)


def test_offsetting_native_holding_value_errors_do_not_cancel_in_nav_sum(original):
    p = package(original)
    second = fill(oid=2, sid=OTHER, cash="99599.8")
    p["records"].insert(1, {"kind": "FILL", "payload": second})
    nav, cash, value = Fraction("99999.8"), Fraction("99599.8"), Fraction(400)
    for record in p["records"]:
        if record["kind"] != "NAV": continue
        row = record["payload"]
        row.update(nav=a._text(nav), cash=a._text(cash), cash_ledger=fixture.rat(cash), fees=fixture.rat("0.2"),
            gross_exposure=a._text(value / nav), max_name_exposure=a._text(Fraction(201) / nav),
            independent_holdings_value=fixture.rat(value))
        row["holdings"][0]["value"] = fixture.rat(201)
        row["holdings"].append({"security_id": OTHER, "quantity": fixture.rat(10), "value": fixture.rat(199)})
        row["raw_marks"].append({**row["raw_marks"][0], "security_id": OTHER})
    p["summary"].update(fill_events=2, submitted_orders=2, requested_shares=fixture.rat(20),
        submitted_shares=fixture.rat(20), filled_shares=fixture.rat(20), fees=fixture.rat("0.2"),
        last_observed_nav=fixture.rat(nav), final_nav=fixture.rat(nav), max_name_exposure=fixture.rat(Fraction(201) / nav))
    for index, record in enumerate(p["records"]): record["ordinal"] = index + 1
    fixture.rebuild(p)
    p["orders"].append({"id": N("2"), "status": N("3"), "time": utc("2021-01-04", 9, 20).isoformat(),
        "symbol": {"id": OTHER}, "events": [native_event(second, 0)]})
    for point in p["chart"]["response"]["chart"]["series"]["NAV"]["values"]: point[1] = number(a._smart_round(nav))
    rebind_api(p)
    report = run(p)
    assert report["native_journal_fill_fee_agreement"] is True
    assert report["quantity_replay_matches_journal"] is True
    assert report["cash_replay_within_cent"] is True
    assert report["daily_nav_replay_within_cent"] is False
    assert report["supplied_evidence_accounting_reconciled"] is False


def test_page_count_bound_is_checked_before_native_body_processing(original):
    p = package(original)
    p["order_pages"] = [b""] * (a.MAX_PAGES + 1)
    with pytest.raises(a.AccountingRefusal): run(p)


PIN = "a" * 64


def compact(p, pin=PIN):
    return a.normalize_api_observations(p["order_pages"], p["chart_raw"], p["api_binding"],
        binding=p["binding"], source_calendar_raw=p["original"], normalizer_source_sha256=pin)


def run_compact(p, raw, *, expected_hash=None, pin=PIN):
    return a.audit_compact(*p["raws"], binding=p["binding"], chunks=p["chunks"], compact_raw=raw,
        expected_compact_sha256=fixture.sha(raw) if expected_hash is None else expected_hash,
        expected_normalizer_source_sha256=pin)


def alter_compact(raw, path, value):
    body = e.parse_json(raw)
    cursor = body
    for key in path[:-1]: cursor = cursor[key]
    cursor[path[-1]] = value
    return e.canonical(body)


def actual_submitted_shape(original):
    p = package(original)
    submitted = fill(quantity=0, price=0, fee=0, status="Submitted", cash=100000, held=None)
    submitted["utc"] = utc("2021-01-04", 9, 20).isoformat()
    p["records"].insert(0, {"kind": "FILL", "payload": submitted})
    for index, record in enumerate(p["records"]): record["ordinal"] = index + 1
    fixture.rebuild(p)
    paid = p["orders"][0]["events"][0]
    paid["orderEventId"] = N("1"); paid["id"] = "synthetic-event-1-1"
    event = native_event(submitted, 0)
    for key in ("orderFeeAmount", "orderFeeCurrency", "fillPriceCurrency"): event.pop(key)
    p["orders"][0]["events"] = [event, paid]
    return rebind_api(p)


def test_compact_and_raw_wrapper_share_one_replay_and_report(original):
    p = package(original)
    raw = compact(p, pin=None)
    assert run_compact(p, raw, pin=None) == run(p)
    assert run_compact(p, compact(p))["supplied_evidence_accounting_reconciled"] is True


def test_compact_contains_only_small_aggregate_commitments_not_individual_observations(original):
    p = package(original)
    raw = compact(p)
    body = e.parse_json(raw)
    assert len(raw) < 6144 and len(raw) <= a.MAX_COMPACT_BYTES
    for forbidden in (SID, OTHER, "PRIVATE-SYNTHETIC-ALIAS", "security_id", '"order_id"', '"price"', '"rounded_nav"', "99999.9"):
        assert forbidden not in raw.decode()
    assert body["completion_binding_sha256"] == fixture.sha(e.canonical(p["binding"]))
    assert body["normalizer_source_sha256"] == PIN
    assert body["normalizer_source_custody_verified"] is False
    assert body["raw_api_pages_revalidated_in_child"] is False
    assert body["exact_journal_to_event_id_mapping_proven"] is False


def test_compact_wrong_hash_stops_before_private_journal_processing(original, monkeypatch):
    p = package(original); raw = compact(p)
    def forbidden(*_args, **_kwargs): pytest.fail("private journal replay occurred before compact integrity check")
    monkeypatch.setattr(c, "replay_chunks", forbidden)
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw + b" ", expected_hash=fixture.sha(raw))


@pytest.mark.parametrize("path,value", [
    (("identity", "job_id"), "2" * 32), (("identity", "project_id"), 37650453),
    (("identity", "candidate_id"), "foreign"), (("identity", "attempt"), 8),
    (("completion_binding_sha256",), "b" * 64), (("source_calendar_sha256",), "c" * 64),
    (("normalizer_source_sha256",), "b" * 64), (("schema",), "forged"),
    (("foreign",), "not-an-authority"), (("native_permission",), True),
    (("normalizer_source_custody_verified",), True), (("raw_api_pages_revalidated_in_child",), True),
    (("exact_journal_to_event_id_mapping_proven",), True), (("native_execution_timing_verified",), True),
    (("api_order_page_count",), -1), (("api_total_envelope_bytes",), 0),
    (("known_event_count",), -1), (("known_event_count",), 2),
    (("known_nonzero_fill_count",), 2), (("known_zero_fill_skeleton_count",), 2),
    (("native_order_census", "orders"), 0), (("native_order_census", "events"), -1),
    (("native_order_census", "nonzero_fills"), 2), (("native_order_census", "reported_fees"), fixture.rat(-1)),
    (("native_order_census", "currency_inference_performed"), True),
    (("native_chart", "axis_complete"), "yes"), (("native_chart", "observations"), 1448),
    (("unknown_reasons", "invented_source_authority"), 1),
])
def test_resealed_compact_foreign_bindings_authority_and_invalid_census_refused(original, path, value):
    p = package(original); raw = alter_compact(compact(p), path, value)
    with pytest.raises(a.AccountingRefusal, match="^CMP28 supplied account replay refused$"): run_compact(p, raw)


def test_external_normalizer_pin_must_be_explicitly_matched_not_ignored(original):
    p = package(original); raw = compact(p)
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw, pin=None)
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw, pin="b" * 64)
    assert run_compact(p, raw)["normalizer_source_custody_verified"] is False


def test_changed_full_parent_summary_envelope_hash_is_not_same_compact_scope(original):
    p = package(original); raw = compact(p)
    p["binding"]["envelopes"]["summary"]["sha256"] = "b" * 64
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw)


def test_compact_counter_commitments_preserve_multiplicity(original):
    p = package(original, multiples=True)
    first = compact(p)
    p["orders"][0]["events"].pop(0); rebind_api(p)
    second = compact(p)
    assert e.parse_json(first)["event_multiset_sha256"] != e.parse_json(second)["event_multiset_sha256"]
    assert e.parse_json(first)["nonzero_fill_multiset_sha256"] != e.parse_json(second)["nonzero_fill_multiset_sha256"]
    assert run_compact(p, first)["native_nonzero_fill_fee_agreement"] is True
    assert run_compact(p, second)["native_nonzero_fill_fee_agreement"] is False


def test_compact_nav_fingerprint_catches_modified_native_point_without_child_values(original):
    p = package(original); first = compact(p)
    p["chart"]["response"]["chart"]["series"]["NAV"]["values"][0][1] = N("100000")
    rebind_api(p); second = compact(p)
    assert e.parse_json(first)["native_chart"]["axis_vector_sha256"] != e.parse_json(second)["native_chart"]["axis_vector_sha256"]
    assert run_compact(p, first)["native_chart_rounding_agreement"] is True
    assert run_compact(p, second)["native_chart_rounding_agreement"] is False


def test_actual_missing_submitted_fee_shape_preserves_partial_checks_and_unknown_full_fees(original):
    p = actual_submitted_shape(original)
    raw = compact(p); body = e.parse_json(raw); report = run_compact(p, raw)
    assert body["native_order_census"]["events"].fraction() == 2
    assert body["known_event_count"].fraction() == 1
    assert body["known_zero_fill_skeleton_count"].fraction() == 1
    assert body["native_order_census"]["reported_fees"] is None
    assert report["native_nonzero_fill_fee_agreement"] is True
    assert report["native_observed_nonzero_fees"] == fixture.rat("0.1")
    assert report["native_zero_fill_event_observation_agreement"] is True
    assert report["native_zero_fill_fee_observation_complete"] is False
    assert report["native_journal_fill_fee_agreement"] is False
    assert report["unknown_reasons"]["unobserved_zero_fill_fee"] == 1
    assert report["cash_replay_within_cent"] is True
    assert report["supplied_evidence_accounting_reconciled"] is False
    assert report["exact_journal_to_event_id_mapping_proven"] is False


def test_unknown_zero_fill_fee_is_not_defaulted_even_when_journal_reports_nonzero_fee(original):
    p = package(original, zero_fee=True, zero_fee_amount="0.25")
    for key in ("orderFeeAmount", "orderFeeCurrency"): p["orders"][1]["events"][0].pop(key)
    rebind_api(p)
    report = run_compact(p, compact(p))
    assert report["native_nonzero_fill_fee_agreement"] is True
    assert report["native_zero_fill_event_observation_agreement"] is True
    assert report["native_zero_fill_fee_observation_complete"] is False
    assert report["replayed_fees"] == fixture.rat("0.35")
    assert report["native_order_census"]["reported_fees"] is None
    assert report["supplied_evidence_accounting_reconciled"] is False


def test_partial_nonzero_and_zero_observation_checks_fail_independently(original):
    p = actual_submitted_shape(original)
    p["orders"][0]["events"][1]["fillPrice"] = N("21"); rebind_api(p)
    report = run_compact(p, compact(p))
    assert report["native_nonzero_fill_fee_agreement"] is False
    assert report["native_zero_fill_event_observation_agreement"] is True
    p = actual_submitted_shape(original)
    p["orders"][0]["events"][0]["status"] = "canceled"; rebind_api(p)
    report = run_compact(p, compact(p))
    assert report["native_nonzero_fill_fee_agreement"] is True
    assert report["native_zero_fill_event_observation_agreement"] is False


def test_compact_zero_empty_fee_currency_has_same_conditional_math_result(original):
    p = package(original, zero_fee=True, zero_fee_amount="0")
    p["records"][1]["payload"]["fee_currency"] = ""
    p["orders"][1]["events"][0]["orderFeeCurrency"] = ""
    fixture.rebuild(p); rebind_api(p)
    report = run_compact(p, compact(p))
    assert report["native_order_census"]["currency_fields_complete"] is False
    assert report["native_nonzero_fill_fee_agreement"] is True
    assert report["native_zero_fill_event_observation_agreement"] is True
    assert report["native_journal_fill_fee_agreement"] is True
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["native_origin_authenticated"] is False


def test_caller_can_reseal_opaque_provenance_hash_so_hash_is_not_authentication(original):
    p = package(original)
    raw = alter_compact(compact(p), ("ordered_api_envelopes_sha256",), "b" * 64)
    report = run_compact(p, raw)
    # The raw API producer/custody must be verified outside this pure consumer.
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["raw_api_pages_revalidated_in_child"] is False
    assert report["normalizer_source_custody_verified"] is False
    assert report["native_origin_authenticated"] is False


def test_nav_commitment_uses_actual_validated_epoch_axis_utc_and_rounding(original):
    import hashlib
    p = package(original); body = e.parse_json(compact(p))
    digest = hashlib.sha256(b"tpr-cmp28-rounded-nav-vector-v1\n")
    points = p["chart"]["response"]["chart"]["series"]["NAV"]["values"]
    for day, (stamp, nav) in zip(p["calendar"]["valuation_sessions"], points):
        instant = datetime.fromtimestamp(int(stamp.fraction()), timezone.utc)
        digest.update(e.canonical({"session": day, "audit_utc": instant.isoformat(), "rounded_nav": fixture.rat(nav.fraction())}))
    assert body["native_chart"]["axis_vector_sha256"] == digest.hexdigest()
    assert utc("2021-01-04", 16, 1).hour != utc("2021-07-01", 16, 1).hour  # NY DST preserved.


def test_fractional_second_event_utc_is_preserved_in_commitments_without_disclosure(original):
    p = package(original)
    p["records"][0]["payload"]["utc"] = utc("2021-01-04").replace(microsecond=1).isoformat()
    p["orders"][0]["events"][0]["time"] = N(str(int(utc("2021-01-04").timestamp())) + ".000001")
    fixture.rebuild(p); rebind_api(p)
    first = compact(p)
    assert run_compact(p, first)["native_nonzero_fill_fee_agreement"] is True
    assert ".000001" not in first.decode()
    p["orders"][0]["events"][0]["time"] = N(str(int(utc("2021-01-04").timestamp())) + ".000002")
    rebind_api(p); second = compact(p)
    assert e.parse_json(first)["nonzero_fill_multiset_sha256"] != e.parse_json(second)["nonzero_fill_multiset_sha256"]
    assert run_compact(p, second)["native_nonzero_fill_fee_agreement"] is False


def test_zero_skeleton_commitment_preserves_duplicate_economic_observations(original):
    p = actual_submitted_shape(original)
    zero_record = deepcopy(p["records"][0])
    p["records"].insert(1, zero_record)
    for index, record in enumerate(p["records"]): record["ordinal"] = index + 1
    fixture.rebuild(p)
    zero_event = deepcopy(p["orders"][0]["events"][0])
    zero_event["orderEventId"] = N("2"); zero_event["id"] = "synthetic-extra-zero-event"
    p["orders"][0]["events"].insert(1, zero_event)
    rebind_api(p); first = compact(p)
    assert run_compact(p, first)["native_zero_fill_event_observation_agreement"] is True
    p["orders"][0]["events"].pop(0); rebind_api(p); second = compact(p)
    assert e.parse_json(first)["zero_fill_skeleton_sha256"] != e.parse_json(second)["zero_fill_skeleton_sha256"]
    assert run_compact(p, second)["native_zero_fill_event_observation_agreement"] is False


@pytest.mark.parametrize("path,value", [
    (("known_event_count",), True), (("native_order_census", "events"), N("1.0")),
    (("observed_nonzero_fees",), fixture.rat(-1)), (("observed_nonzero_fees",), None),
    (("native_order_census", "absolute_filled_shares"), fixture.rat(0)),
    (("zero_fill_skeleton_sha256",), "0" * 64), (("native_chart", "axis_vector_sha256"), "0" * 64),
    (("unknown_reasons", "missing_native_event_identity"), -1),
])
def test_compact_numeric_hash_and_unknown_fact_bounds_refuse_resealed_bad_shapes(original, path, value):
    p = package(original); raw = alter_compact(compact(p), path, value)
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw)


def test_partial_missing_nonzero_fee_is_none_not_zero_observed_fee_aggregate(original):
    p = package(original); p["orders"][0]["events"][0].pop("orderFeeAmount"); rebind_api(p)
    raw = compact(p); body = e.parse_json(raw); report = run_compact(p, raw)
    assert body["observed_nonzero_fees"] is None
    assert report["native_observed_nonzero_fees"] is None
    assert report["native_nonzero_fill_fee_agreement"] is False


def test_resealed_known_zero_fee_count_cannot_contradict_retained_missing_zero_fee(original):
    p = actual_submitted_shape(original)
    raw = alter_compact(compact(p), ("known_event_count",), 2)
    with pytest.raises(a.AccountingRefusal): run_compact(p, raw)


def test_full_replay_rejects_journal_fill_submicrosecond_precision_instead_of_truncating(original):
    p = package(original)
    p["records"][0]["payload"]["utc"] = "2021-01-04T14:30:00.0000001+00:00"
    fixture.rebuild(p)
    with pytest.raises(a.AccountingRefusal): run(p)


def test_action_grouping_rejects_submicrosecond_precision_instead_of_merging_clocks(original):
    p = package(original, actions=[action("split"), action("dividend", value=1)])
    row = next(record["payload"] for record in p["records"] if record["kind"] == "ACTION" and record["payload"]["action"] == "split")
    row["utc"] = "2021-01-05T14:30:00.0000001+00:00"
    fixture.rebuild(p)
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("field", ["time", "createdTime"])
def test_api_order_rejects_submicrosecond_precision_before_lossy_legacy_parse(original, field):
    p = package(original)
    p["orders"][0][field] = "2021-01-04T14:20:00.0000001+00:00"
    rebind_api(p)
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("location", ["journal", "api"])
def test_fractional_offset_submicrosecond_precision_is_not_silently_zeroed(original, location):
    p = package(original)
    if location == "journal":
        p["records"][0]["payload"]["utc"] = "2021-01-04T14:30:00+00:00:00.0000001"
        fixture.rebuild(p)
    else:
        p["orders"][0]["time"] = "2021-01-04T14:20:00+00:00:00.0000001"
        rebind_api(p)
    with pytest.raises(a.AccountingRefusal): run(p)


@pytest.mark.parametrize("text,microsecond", [
    ("2021-01-04T14:30:00Z", 0), ("2021-01-04 09:30:00-05:00", 0),
    ("2021-01-04t15:30:00+01:00", 0), ("2021-01-04T14:30:00.000000000Z", 0),
    ("2021-01-04T14:30:00.000001000000+00:00", 1),
    ("2021-01-04T14:30:00,123456000+00:00", 123456),
    ("2021-01-04T14:30:00.000001+00:00:00.000001", 0),
    ("2021-01-04T14:30:00.000000000-00:00:00.000001000", 1),
    ("2021-01-04T14:30:01.000001+00:00:01.000001", 0),
    ("2021-01-04T15:30:00.123456000+01:00:00.123456000", 0),
    ("2021-01-04T09:29:59.9999990-05:00:00.0000010", 0),
])
def test_exact_iso_parser_preserves_microseconds_trailing_zeros_and_signed_offset_seconds(text, microsecond):
    assert a._clock(text) == utc("2021-01-04").replace(microsecond=microsecond)


@pytest.mark.parametrize("text", [
    "2021-01-04T14:30:00", "2021-01-04T14:30Z", "2021-01-04X14:30:00Z",
    "2021-01-04T14:30:00+00:60", "2021-01-04T14:30:00+24:00", "2021-01-04T14:30:00+00:00:60",
    "2021-01-04T14:60:00Z", "2021-01-04T14:30:60Z", "2021-02-30T14:30:00Z",
    "2021-01-04T14:30:00.+00:00", "2021-01-04T14:30:00+00:00.000001",
    "2021-01-04T14:30:00.1234561Z", "2021-01-04T14:30:00+00:00:01.1234561",
])
def test_exact_iso_parser_refuses_unknown_grammar_overflow_or_lossy_precision_body_free(text):
    with pytest.raises(a.AccountingRefusal, match="^CMP28 supplied account replay refused$"): a._clock(text)


@pytest.mark.parametrize("spelling", [
    "2021-01-04T14:30:00.000000000Z", "2021-01-04 09:30:00-05:00",
    "2021-01-04T15:30:00.0000000+01:00:00.00000000",
    "2021-01-04T14:30:00.0000010+00:00:00.000001000",
])
def test_full_replay_accepts_exact_equivalent_aware_fill_spellings(original, spelling):
    p = package(original); p["records"][0]["payload"]["utc"] = spelling; fixture.rebuild(p)
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


@pytest.mark.parametrize("field", ["time", "createdTime"])
def test_api_order_exact_equivalent_offset_and_trailing_zero_spelling_retained(original, field):
    p = package(original)
    p["orders"][0][field] = "2021-01-04T09:20:00.000000000-05:00:00.000000000"
    rebind_api(p)
    assert run(p)["supplied_evidence_accounting_reconciled"] is True


def test_action_grouping_preserves_equivalent_exact_offset_fraction_spellings(original):
    p = package(original, actions=[action("split"), action("dividend", value=1)])
    for record in p["records"]:
        if record["kind"] == "ACTION":
            record["payload"]["utc"] = ("2021-01-05T09:30:00.000000000-05:00" if record["payload"]["action"] == "split"
                else "2021-01-05T15:30:00.000000000+01:00:00.000000000")
    fixture.rebuild(p)
    assert run(p)["supplied_evidence_accounting_reconciled"] is True
