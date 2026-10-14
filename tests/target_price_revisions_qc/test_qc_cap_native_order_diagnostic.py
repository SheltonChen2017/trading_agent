"""Synthetic original-wire native fee/unit unknowns; no empirical inputs."""
from copy import deepcopy
from datetime import datetime
import json

import pytest
from research.target_price_revisions_qc import cap_native_order_diagnostic as d


def fixture():
    job = "synthetic-job"
    strategy_clock = datetime(2025, 1, 2, 9, 20, tzinfo=d.accounting.NY)
    strategy_fill = strategy_clock.replace(minute=30)
    final_clock = datetime(2025, 3, 7, 16, tzinfo=d.accounting.NY)
    strategy = {"id": 1, "status": 3, "type": 4, "priceAdjustmentMode": 0, "priceCurrency": "USD",
        "quantity": 10, "tag": "TPRM:" + "a" * 20, "createdTime": strategy_clock.isoformat(),
        "symbol": {"value": "SYNTHETIC_PRIVATE_NAME"}, "events": [
            {"orderId": 1, "orderEventId": 1, "id": job + "-1-1", "algorithmId": job,
             "status": "filled", "fillQuantity": 10, "fillPrice": "100", "fillPriceCurrency": "USD",
             "orderFeeAmount": "0.10", "orderFeeCurrency": "USD", "time": int(strategy_fill.timestamp())}]}
    engine = {"id": 2, "status": 3, "type": 0, "priceAdjustmentMode": 0, "priceCurrency": "",
        "quantity": -10, "tag": "Liquidate from delisting", "createdTime": final_clock.isoformat(),
        "events": [{"orderId": 2, "orderEventId": 1, "id": job + "-2-1", "algorithmId": job,
            "status": "filled", "fillQuantity": -10, "fillPrice": "100", "fillPriceCurrency": "",
            "isAssignment": False, "time": int(final_clock.timestamp())}]}
    pages = [{"success": True, "loading": False, "start": 0, "end": 99, "length": 2,
              "projectId": 7, "backtestId": job, "orders": [strategy, engine]}]
    summary = {"submitted_orders": 1, "submitted_shares": 10, "fill_events": 2, "filled_shares": 20,
               "fees": "0.10", "native_final_delisting_compatibility_exceptions": 1}
    return [pages, {"project_id": 7, "backtest_id": job}, summary,
            {"Total Orders": "2", "Total Fees": "$0.10"}, {"arm": "tpr_on", "cost": "baseline"}, []]


def test_absent_native_fee_and_empty_units_stay_unknown_with_observed_subtotals():
    args = fixture()
    before = deepcopy(args[:-1])
    result = d.orders(*args)
    assert args[:-1] == before
    orders, partition, provenance = (result[key] for key in ("orders", "native_order_partition", "fee_provenance"))
    assert orders["orders"] == orders["filled_orders"] == orders["fill_events"] == 2
    assert orders["filled_shares"] == "20" and orders["order_failures"] == 0
    assert orders["observed_fees"] == "0.1" and orders["fees"] is None
    assert orders["api_unreported_fee_events"] == orders["native_fee_fields_missing_fill_events"] == 1
    assert orders["native_fee_complete"] is False
    assert orders["observed_usd_fill_notional"] == "1000" and orders["fill_notional"] is None
    assert orders["native_fill_currency_unknown_fill_events"] == 1 and orders["native_usd_notional_complete"] is False
    engine = partition["engine_tagged_delisting_market"]
    assert engine["orders"] == engine["fill_events"] == engine["api_unreported_fee_events"] == 1
    assert engine["observed_fees"] == "0" and engine["fees"] is None
    assert engine["zero_fee_qcc_fill_events"] == engine["zero_fee_usd_fill_events"] == 0
    assert engine["fill_notional"] is None and engine["observed_usd_fill_notional"] == "0"
    assert partition["engine_tag_is_not_independent_custody_proof"] is True
    assert provenance["api_reported_fee_totals_by_currency"] == {"USD": "0.1"}
    assert provenance["all_native_fee_total"] is None and provenance["all_native_fee_total_known"] is False
    assert provenance["summary_matches_reported_strategy_fees"] is True
    assert provenance["statistic_matches_reported_strategy_fees"] is True
    assert provenance["unreported_fee_zero_attested"] is False and provenance["unreported_fee_currency_attested"] is False
    assert {"non_moo_raw_usd_order", "native_order_currency_empty_or_missing", "native_fill_currency_empty_or_missing",
            "non_usd_native_fill", "api_unreported_native_fee", "native_fee_schedule_unverifiable",
            "order_clock_outside_frozen_schedule", "fill_clock_outside_frozen_schedule"} <= set(args[-1])
    assert "SYNTHETIC_PRIVATE_NAME" not in json.dumps(result)
    assert "synthetic-job" not in json.dumps(result)


def test_old_strict_helper_is_unchanged_and_refuses_absent_fee_shape():
    args = fixture()
    with pytest.raises(d.AuditError):
        d.accounting._orders(*deepcopy(args))
    assert d.orders(*args)["orders"]["fees"] is None


@pytest.mark.parametrize("mode", ["amount_only", "currency_only", "amount_null", "currency_null", "currency_empty",
    "fee_alias", "fee_nested", "type_string", "type_bool", "raw_string", "raw_bool", "tag_substring",
    "positive", "partial_fill", "partial_status", "partial_order", "assignment", "assignment_unknown", "status_bool"])
def test_joint_absence_exception_is_closed_and_ambiguity_refuses(mode):
    args = fixture()
    order = args[0][0]["orders"][1]
    event = order["events"][0]
    if mode == "amount_only": event["orderFeeAmount"] = "0"
    elif mode == "currency_only": event["orderFeeCurrency"] = "QCC"
    elif mode == "amount_null": event.update(orderFeeAmount=None, orderFeeCurrency="QCC")
    elif mode == "currency_null": event.update(orderFeeAmount="0", orderFeeCurrency=None)
    elif mode == "currency_empty": event.update(orderFeeAmount="0", orderFeeCurrency="")
    elif mode == "fee_alias": event["order-fee-amount"] = "0"
    elif mode == "fee_nested": event["orderFee"] = {"amount": "0", "currency": "QCC"}
    elif mode == "type_string": order["type"] = "0"
    elif mode == "type_bool": order["type"] = False
    elif mode == "raw_string": order["priceAdjustmentMode"] = "0"
    elif mode == "raw_bool": order["priceAdjustmentMode"] = False
    elif mode == "tag_substring": order["tag"] = "prefix Liquidate from delisting"
    elif mode == "positive": order["quantity"], event["fillQuantity"] = 10, 10
    elif mode == "partial_fill": event["fillQuantity"] = -9
    elif mode == "partial_status": event["status"] = "partiallyFilled"
    elif mode == "partial_order": order["status"] = 2
    elif mode == "assignment": event["isAssignment"] = True
    elif mode == "assignment_unknown": event.pop("isAssignment")
    else: event["status"] = True
    with pytest.raises(d.AuditError):
        d.orders(*args)


@pytest.mark.parametrize("key", ["priceCurrency", "fillPriceCurrency"])
def test_missing_native_final_currency_is_reported_not_invented(key):
    args = fixture()
    row = args[0][0]["orders"][1] if key == "priceCurrency" else args[0][0]["orders"][1]["events"][0]
    row.pop(key)
    result = d.orders(*args)
    assert result["orders"]["fees"] is None and result["orders"]["fill_notional"] is None
    assert "native_" + ("order" if key == "priceCurrency" else "fill") + "_currency_empty_or_missing" in args[-1]


@pytest.mark.parametrize("field", ["priceCurrency", "fillPriceCurrency"])
@pytest.mark.parametrize("value", [None, 0, False, [], "usd", "USDX"])
def test_malformed_currency_is_not_an_unknown_metadata_exception(field, value):
    args = fixture()
    row = args[0][0]["orders"][1] if field == "priceCurrency" else args[0][0]["orders"][1]["events"][0]
    row[field] = value
    with pytest.raises(d.AuditError):
        d.orders(*args)


@pytest.mark.parametrize("field", ["priceCurrency", "fillPriceCurrency"])
def test_missing_ordinary_currency_does_not_use_final_exception(field):
    args = fixture()
    row = args[0][0]["orders"][0] if field == "priceCurrency" else args[0][0]["orders"][0]["events"][0]
    row.pop(field)
    with pytest.raises(d.AuditError):
        d.orders(*args)


def test_ordinary_usd_fill_cannot_omit_native_fee_pair():
    args = fixture()
    event = args[0][0]["orders"][0]["events"][0]
    event.pop("orderFeeAmount")
    event.pop("orderFeeCurrency")
    with pytest.raises(d.AuditError, match="unreported fee outside"):
        d.orders(*args)


@pytest.mark.parametrize("currency", ["USD", "QCC", "EUR"])
def test_explicit_zero_fee_is_observed_without_relabeling_currency(currency):
    args = fixture()
    event = args[0][0]["orders"][1]["events"][0]
    event.update(orderFeeAmount="0", orderFeeCurrency=currency, fillPriceCurrency="USD")
    result = d.orders(*args)
    orders = result["orders"]
    assert orders["fees"] == "0.1" and orders["native_fee_complete"] is True
    assert orders["api_unreported_fee_events"] == 0 and orders["fill_notional"] == "2000"
    assert result["fee_provenance"]["api_reported_fee_totals_by_currency"][currency] == ("0.1" if currency == "USD" else "0")
    assert "native_fee_schedule_mismatch" in args[-1]
    assert "native_order_currency_empty_or_missing" in args[-1]


def test_non_usd_fee_is_kept_in_own_currency_not_added_to_usd_fee_total():
    args = fixture()
    args[0][0]["orders"][1]["events"][0].update(orderFeeAmount="0.20", orderFeeCurrency="EUR")
    result = d.orders(*args)
    assert result["orders"]["fees"] is None and result["orders"]["observed_fees"] == "0.1"
    assert result["fee_provenance"]["api_reported_fee_totals_by_currency"] == {"EUR": "0.2", "USD": "0.1"}
    assert "non_usd_native_fill" in args[-1]


@pytest.mark.parametrize("field,value", [("quantity", "NaN"), ("quantity", "1.5"), ("quantity", 0),
    ("fillQuantity", None), ("fillQuantity", "NaN"), ("fillQuantity", "-1.5"), ("fillQuantity", 0),
    ("fillPrice", "NaN"), ("fillPrice", "Infinity"), ("fillPrice", 0),
    ("time", None), ("time", "NaN"), ("time", "1.5"), ("time", "1e100"),
    ("orderFeeAmount", "-1"), ("orderFeeAmount", "NaN")])
def test_malformed_fill_numbers_hard_refuse(field, value):
    args = fixture()
    order = args[0][0]["orders"][1]
    event = order["events"][0]
    if field == "quantity": order[field] = value
    else:
        if field == "orderFeeAmount": event["orderFeeCurrency"] = "USD"
        event[field] = value
    with pytest.raises(d.AuditError):
        d.orders(*args)


@pytest.mark.parametrize("mode", ["duplicate_order", "duplicate_fill", "foreign_fill", "bool_orderid", "float_eventid",
    "alias_different", "alias_bool", "composite_different", "composite_missing_algorithm", "algorithm_foreign",
    "algorithm_null", "legacy_alias", "page_foreign", "page_foreign_type"])
def test_native_id_domain_and_job_binding_are_exact(mode):
    args = fixture()
    page, engine = args[0][0], args[0][0]["orders"][1]
    event = engine["events"][0]
    if mode == "duplicate_order": engine["id"] = 1
    elif mode == "duplicate_fill": engine["events"].append(deepcopy(event))
    elif mode == "foreign_fill": event["orderId"] = 9
    elif mode == "bool_orderid": event["orderId"] = True
    elif mode == "float_eventid": event["orderEventId"] = 1.0
    elif mode == "alias_different": event["id"] = 2
    elif mode == "alias_bool": event["id"] = True
    elif mode == "composite_different": event["id"] += "0"
    elif mode == "composite_missing_algorithm": event.pop("algorithmId")
    elif mode == "algorithm_foreign":
        event["algorithmId"] = "foreign"
        event["id"] = "foreign-2-1"
    elif mode == "algorithm_null": event["algorithmId"] = None
    elif mode == "legacy_alias": event["order-event-id"] = 1
    elif mode == "page_foreign": page["backtestId"] = "foreign"
    else: page["projectId"] = 7.0
    with pytest.raises(d.AuditError):
        d.orders(*args)


def test_exact_integer_alias_seam_and_no_alias_keep_event_id_domain():
    args = fixture()
    for order in args[0][0]["orders"]:
        event = order["events"][0]
        event["id"] = event["orderEventId"]
    assert d.orders(*args)["orders"]["fill_events"] == 2
    for order in args[0][0]["orders"]:
        order["events"][0].pop("id")
    assert d.orders(*args)["orders"]["fill_events"] == 2


@pytest.mark.parametrize("fault", ["overlap", "width", "width_bool", "changing_length", "length_overflow",
    "rows_overflow", "pages_overflow", "events_overflow", "event_nondict", "orders_nontyped", "page_nondict", "page_after_length"])
def test_native_inventory_resource_and_pagination_guards(fault):
    args = fixture()
    page = args[0][0]
    if fault == "overlap": page["start"] = 1
    elif fault == "width": page["end"] = 100
    elif fault == "width_bool": page["end"] = True
    elif fault == "changing_length": args[0].append({**deepcopy(page), "start": 99, "end": 198, "length": 3})
    elif fault == "length_overflow": page["length"] = 5001
    elif fault == "rows_overflow": page["orders"] *= 50
    elif fault == "pages_overflow": args[0] *= 101
    elif fault == "events_overflow": page["orders"][0]["events"] *= 101
    elif fault == "event_nondict": page["orders"][0]["events"] = [None]
    elif fault == "orders_nontyped": page["orders"] = [None]
    elif fault == "page_after_length":
        next_page = {**deepcopy(page), "start": 99, "end": 198, "orders": [deepcopy(page["orders"][1])]}
        page["orders"] = page["orders"][:1]
        args[0].append(next_page)
    else: args[0] = [None]
    with pytest.raises(d.AuditError):
        d.orders(*args)


@pytest.mark.parametrize("fault,reason", [("loading", "order_inventory_loading_or_failed"),
    ("failed", "order_inventory_loading_or_failed"), ("boundary", "order_page_boundary_missing"),
    ("incomplete", "order_inventory_incomplete"), ("empty", "order_inventory_missing")])
def test_incomplete_inventory_cannot_claim_all_native_totals(fault, reason):
    args = fixture()
    page = args[0][0]
    if fault == "loading": page["loading"] = True
    elif fault == "failed": page["success"] = False
    elif fault == "boundary": page.pop("end")
    elif fault == "incomplete": page["length"] = 3
    else: args[0] = []
    result = d.orders(*args)
    assert result["orders"]["order_inventory_complete"] is False
    assert result["orders"]["fees"] is result["orders"]["fill_notional"] is None
    assert reason in args[-1]


@pytest.mark.parametrize("field,value,reason", [("submitted_orders", 2, "strategy_tagged_moo_summary_mismatch"),
    ("submitted_shares", 11, "strategy_tagged_moo_summary_mismatch"), ("filled_shares", 21, "all_native_fill_summary_mismatch"),
    ("fill_events", 3, "all_native_fill_summary_mismatch"), ("native_final_delisting_compatibility_exceptions", 0, "native_final_compatibility_count_mismatch"),
    ("fees", "0.20", "known_strategy_fees_and_summary_mismatch_or_unknown")])
def test_original_summary_differences_are_visible_not_repaired(field, value, reason):
    args = fixture()
    args[2][field] = value
    assert d.orders(*args)["orders"]["fees"] is None
    assert reason in args[-1]
    assert args[2][field] == value


def test_original_stats_fee_is_crosscheck_not_proof_of_unreported_zero():
    args = fixture()
    args[3]["Total Fees"] = "$0.20"
    result = d.orders(*args)
    assert result["fee_provenance"]["original_qc_statistic_fee_claim"] == "0.2"
    assert result["fee_provenance"]["statistic_matches_reported_strategy_fees"] is False
    assert result["orders"]["fees"] is None
    assert "known_strategy_fees_and_statistic_mismatch_or_unknown" in args[-1]


def test_nonfilled_history_omits_fees_without_fabricating_fill():
    args = fixture()
    args[0][0]["orders"][0]["events"].insert(0, {"status": "submitted"})
    assert d.orders(*args)["orders"]["fill_events"] == 2


def test_non_usd_explicit_fill_notional_is_not_added_to_observed_usd():
    args = fixture()
    args[0][0]["orders"][1]["events"][0]["fillPriceCurrency"] = "EUR"
    result = d.orders(*args)
    assert result["orders"]["fill_notional"] is None
    assert result["orders"]["observed_usd_fill_notional"] == "1000"
    assert "non_usd_native_fill" in args[-1]


def test_native_clock_and_failure_discrepancies_are_not_removed():
    args = fixture()
    strategy = args[0][0]["orders"][0]
    strategy["events"][0]["time"] += 300
    result = d.orders(*args)
    assert "fill_clock_outside_frozen_schedule" in args[-1]
    assert result["orders"]["fill_events"] == 2
    strategy["status"] = 5
    result = d.orders(*args)
    assert result["orders"]["order_failures"] == 1
    assert "unfilled_or_failed_native_orders" in args[-1]


def test_fill_before_order_and_whole_overfill_hard_refuse():
    args = fixture()
    strategy = args[0][0]["orders"][0]
    strategy["events"][0]["time"] -= 3600
    with pytest.raises(d.AuditError): d.orders(*args)
    args = fixture()
    strategy = args[0][0]["orders"][0]
    strategy["events"][0]["fillQuantity"] = 11
    with pytest.raises(d.AuditError): d.orders(*args)
