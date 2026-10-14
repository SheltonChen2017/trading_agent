"""Pure native observation fixtures; no real private/account/outcome access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from research.target_price_revisions_qc import extended_native as n

e, N = n.e, n.e.JsonNumber
CALENDAR = Path("research/target_price_revisions_qc/extended_calendar.json").read_bytes()
SESSIONS = n.metrics._calendar(CALENDAR)
PROJECT, JOB, ATTEMPT = 123, "synthetic-job", 1
CANDIDATE = next(candidate for candidate, arm in e.CANDIDATES.items() if arm == "tpr_on")
BINDING = dict(candidate_id=CANDIDATE, project_id=PROJECT, backtest_id=JOB, attempt=ATTEMPT)
NY = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def forbidden_real_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("private filesystem, credentials, subprocess or provider/QC access forbidden")
    monkeypatch.setattr(n.collector, "credential", forbidden)
    monkeypatch.setattr(n.collector.http.client, "HTTPSConnection", forbidden)
    monkeypatch.setattr(n.collector.subprocess, "run", forbidden)
    monkeypatch.setattr(n.collector.Operations, "__init__", forbidden)
    monkeypatch.setattr(os, "open", forbidden)


def epoch(session, hour=16, minute=1):
    value = datetime.fromisoformat(session).replace(hour=hour, minute=minute, tzinfo=NY)
    return N(str(int(value.timestamp())))


def nav_fixture(style="modern"):
    values, series = [], []
    for index, session in enumerate(SESSIONS):
        nav = N("100000.0000000000000000001" if index == 0 else "100000")
        stamp = epoch(session)
        values.append([stamp, nav] if style == "modern" else {"x": stamp, "y": nav})
        series.append({"session": session, "nav": nav})
    response = {"success": True, "chart": {"name": "EXT26 Account NAV", "series": {"NAV": {
        "name": "NAV", "unit": "$", "seriesType": N("0"), "values": values}}}}
    request = {"projectId": PROJECT, "backtestId": JOB, "name": "EXT26 Account NAV",
        "start": n.collector.CHART_START, "end": n.collector.CHART_END, "count": n.collector.CHART_COUNT}
    envelope = {"schema": "tpr-ext26-native-read-envelope-v1", "endpoint": "backtests/chart/read",
        "request": request, "response": response,
        "returned_identity_checks": n.collector._returned_identity(response, PROJECT, JOB)}
    return series, envelope


def nav_run(series, envelope, **changes):
    raw, env = e.canonical(series), e.canonical(envelope)
    arguments = dict(expected_series_sha256=e.digest(raw), expected_envelope_sha256=e.digest(env), **BINDING)
    arguments.update(changes)
    return n.normalize_nav(raw, env, CALENDAR, **arguments)


def event(identity=1, *, session=SESSIONS[0], quantity="10", filled="10", price="20", fee="0.10", **changes):
    return {"algorithmId": JOB, "orderId": N("1"), "orderEventId": N(str(identity)), "id": "event-" + str(identity),
        "time": epoch(session, 9, 30), "status": "filled", "quantity": N(quantity),
        "fillQuantity": N(filled), "fillPrice": N(price), "fillPriceCurrency": "USD",
        "orderFeeAmount": N(fee), "orderFeeCurrency": "USD", **changes}


def order(identity=1, *, session=SESSIONS[0], quantity="10", status=3, events=True, **changes):
    created = datetime.fromisoformat(session).replace(hour=9, minute=20, tzinfo=NY).astimezone(timezone.utc).isoformat()
    row = {"id": N(str(identity)), "status": N(str(status)) if type(status) is int else status,
        "time": created, "createdTime": created, "quantity": N(quantity), "price": N("999999"),
        "priceCurrency": "EUR", "userId": "PRIVATE-USER-SECRET", "tag": "PRIVATE-TICKER-SECRET"}
    if events:
        row["events"] = [event(orderId=N(str(identity)), quantity=quantity, filled=quantity)]
    return {**row, **changes}


def order_fixture(rows):
    envelopes, descriptors = [], []
    for page_index in range(max(1, (len(rows) + 98) // 99)):
        start, end = page_index * 99, (page_index + 1) * 99
        response = {"success": True, "orders": rows[start:end], "length": N(str(len(rows)))}
        checks = n.collector._returned_identity(response, PROJECT, JOB)
        envelope = {"schema": "tpr-ext26-native-read-envelope-v1", "endpoint": "backtests/orders/read",
            "request": {"projectId": PROJECT, "backtestId": JOB, "start": start, "end": end},
            "response": response, "returned_identity_checks": checks}
        raw = e.canonical(envelope)
        envelopes.append(raw)
        descriptors.append({"start": start, "end": end, "response_projection_sha256": e.digest(e.canonical(response)),
            "request_response_envelope_sha256": e.digest(raw), "returned_identity_checks": checks})
    collection = {"schema": "tpr-ext26-order-collection-v1", "candidate_id": CANDIDATE, "attempt": ATTEMPT,
        "backtest_id": JOB, "order_count": len(rows), "pages": descriptors, "strategy_accepted": False, "new_looks": 0}
    return envelopes, collection


def run(rows=None, *, envelopes=None, collection=None, **changes):
    if envelopes is None: envelopes, collection = order_fixture(rows)
    raw = e.canonical(collection)
    arguments = dict(expected_collection_sha256=e.digest(raw), **BINDING)
    arguments.update(changes)
    return n.normalize_orders(envelopes, raw, CALENDAR, **arguments)


def normalized(result):
    return [row for raw in result.pages for row in e.parse_json(raw)]


@pytest.mark.parametrize("style", ["modern", "legacy"])
def test_existing_collector_chart_oracle_all_sessions_exact_lexical_nav(style):
    series, envelope = nav_fixture(style)
    raw, census = nav_run(series, envelope)
    assert raw == e.canonical(series)
    report = e.parse_json(census)
    assert report["observations"].fraction() == 1449
    assert report["normalized_series_sha256"] == e.digest(raw)
    assert e.parse_json(raw)[0]["nav"].lexeme == "100000.0000000000000000001"
    assert report["private_journal_replay_verified"] is False


def test_missing_explicit_native_success_is_not_a_completed_response():
    series, envelope = nav_fixture()
    envelope["response"].pop("success")
    with pytest.raises(ValueError): nav_run(series, envelope)


@pytest.mark.parametrize("failure", ["missing_day", "duplicate_day", "wrong_clock", "wrong_epoch", "weekend",
    "missing_y", "zero_y", "string_y", "bool_y", "foreign_project", "foreign_job", "loading", "wrong_chart",
    "default_equity", "modified_series", "wrong_request", "hash"])
def test_nav_no_interpolation_defaults_or_foreign_clock_binding(failure):
    series, envelope = nav_fixture()
    points = envelope["response"]["chart"]["series"]["NAV"]["values"]
    changes = {}
    if failure == "missing_day": points.pop()
    elif failure == "duplicate_day": points[1] = points[0]
    elif failure == "wrong_clock": points[0][0] = epoch(SESSIONS[0], 16, 0)
    elif failure == "wrong_epoch": points[0][0] = N("1600000000")
    elif failure == "weekend": points[0][0] = epoch("2021-01-02")
    elif failure == "missing_y": points[0] = {"x": points[0][0]}
    elif failure == "zero_y": points[0][1] = N("0")
    elif failure == "string_y": points[0][1] = "100000"
    elif failure == "bool_y": points[0][1] = True
    elif failure == "foreign_project": envelope["response"]["projectId"] = N("999")
    elif failure == "foreign_job": envelope["response"]["backtestId"] = "foreign-job"
    elif failure == "loading": envelope["response"]["status"] = "loading"
    elif failure == "wrong_chart": envelope["response"]["chart"]["name"] = "other"
    elif failure == "default_equity": envelope["request"]["name"] = "Strategy Equity"
    elif failure == "modified_series": series[0]["nav"] = N("1")
    elif failure == "wrong_request": envelope["request"]["end"] += 1
    elif failure == "hash": changes["expected_envelope_sha256"] = "0" * 64
    with pytest.raises(ValueError): nav_run(series, envelope, **changes)


@pytest.mark.parametrize("value,expected", [(number, name) for number, name in n.STATUS.items()] +
    [(name, name) for name in n.STATUS.values()])
def test_documented_integer_and_canonical_native_order_statuses_retained(value, expected):
    result = run([order(status=value, events=False)])
    row = normalized(result)[0]
    assert row["status"] == expected
    assert row["fill_quantity"] is row["fill_price"] is row["reported_fee"] is None
    assert e.parse_json(result.public)["status_counts"][expected].fraction() == 1


@pytest.mark.parametrize("value", [4, 10, True, None, "3", "FILLED", "filled", "Cancelled"])
def test_invalid_or_unobserved_native_order_status_not_guessed(value):
    with pytest.raises(ValueError): run([order(status=value, events=False)])


def test_actual_events_exact_fee_quantity_vwap_not_reported_native_order_price():
    row = order(quantity="3")
    row["events"] = [event(1, quantity="3", filled="1", price="20", fee="0.01", status="partiallyFilled"),
        event(2, quantity="3", filled="2", price="21", fee="0.02", time=epoch(SESSIONS[0], 9, 31))]
    result = run([row])
    observed = normalized(result)[0]
    assert observed["fill_quantity"].fraction() == 3 and observed["reported_fee"].fraction() == Fraction(3, 100)
    assert observed["fill_currency"] == "USD" and observed["fee_currency"] == "USD"
    assert observed["fill_price"] == {"schema": "tpr-ext26-derived-fill-vwap-v1", "numerator": "62", "denominator": "3"}
    private = e.parse_json(result.observations[0])[0]
    assert private["reported_order_price"].fraction() == 999999
    assert private["reported_order_price_currency"] == "EUR"
    assert len(private["events"]) == 2
    assert private["observed_event_fill_notional"] == {"numerator": "62", "denominator": "1"}
    assert b"PRIVATE-USER-SECRET" not in result.public and b"PRIVATE-TICKER-SECRET" not in result.public
    assert b"PRIVATE-USER-SECRET" not in result.observations[0]


def test_terminating_vwap_is_exact_derived_decimal_and_native_event_tokens_retained():
    row = order(quantity="2")
    row["events"] = [event(1, quantity="2", filled="1", price="20.00000000000000000001", fee="0.01", status="partiallyFilled"),
        event(2, quantity="2", filled="1", price="21.00000000000000000001", fee="0.02", time=epoch(SESSIONS[0], 9, 31))]
    result = run([row])
    assert normalized(result)[0]["fill_price"].fraction() == Fraction("20.50000000000000000001")
    assert e.parse_json(result.observations[0])[0]["events"][0]["fillPrice"].lexeme == "20.00000000000000000001"


def test_native_aggregation_and_metrics_closed_derived_vwap_contract():
    row = order(quantity="3")
    row["events"] = [event(1, quantity="3", filled="1", price="20", fee="0.01", status="partiallyFilled"),
        event(2, quantity="3", filled="2", price="21", fee="0.02", time=epoch(SESSIONS[0], 9, 31))]
    result = run([row])
    series, _envelope = nav_fixture()
    series_raw = e.canonical(series)
    observed = n.metrics.execution_metrics(list(result.pages), series_raw, CALENDAR,
        expected_orders_sha256=n.metrics.order_pages_identity(list(result.pages)),
        expected_series_sha256=e.digest(series_raw), expected_order_count=1)
    assert observed["complete_reported_fees_usd"] == {"numerator": "3", "denominator": "100"}
    assert observed["complete_reported_gross_turnover_decimal"] is not None


def test_empty_native_currency_remains_unavailable_with_original_wire_observation():
    row = order(priceCurrency="")
    row["events"][0]["orderFeeCurrency"] = ""
    row["events"][0]["fillPriceCurrency"] = ""
    result = run([row])
    observed = normalized(result)[0]
    assert observed["fee_currency"] is observed["reported_fee"] is None
    assert observed["fill_currency"] is observed["fill_quantity"] is None
    assert e.parse_json(result.observations[0])[0]["events"][0]["orderFeeCurrency"] == ""


def test_native_sell_events_preserve_sign_positive_vwap_and_observed_currency():
    result = run([order(quantity="-10")])
    observed = normalized(result)[0]
    assert observed["fill_quantity"].fraction() == -10 and observed["fill_price"].fraction() == 20
    assert observed["reported_fee"].fraction() == Fraction(1, 10)
    assert e.parse_json(result.observations[0])[0]["observed_event_fill_notional"] == {"numerator": "-200", "denominator": "1"}


@pytest.mark.parametrize("field", ["fillQuantity", "fillPrice", "fillPriceCurrency", "orderFeeAmount", "orderFeeCurrency"])
def test_missing_native_observation_is_not_fee_zero_usd_or_native_price(field):
    row = order()
    row["events"][0].pop(field)
    result = run([row])
    value = normalized(result)[0]
    if field.startswith("orderFee"):
        assert value["reported_fee"] is value["fee_currency"] is None
    else:
        assert value["fill_quantity"] is value["fill_price"] is value["fill_currency"] is None


@pytest.mark.parametrize("field", ["algorithmId", "orderId", "time", "quantity", "status"])
def test_missing_native_event_binding_or_share_basis_retained_unknown(field):
    row = order()
    row["events"][0].pop(field)
    result = run([row])
    value = normalized(result)[0]
    assert value["fill_quantity"] is value["reported_fee"] is None
    assert e.parse_json(result.observations[0])[0]["events"][0][field] is None


@pytest.mark.parametrize("failure", ["cross_session", "post_split", "missing_event_id", "incomplete_filled_history", "mixed_currency"])
def test_multi_session_post_split_or_incomplete_events_are_unknown_not_dropped(failure):
    row = order()
    if failure == "cross_session": row["events"][0]["time"] = epoch(SESSIONS[1], 9, 30)
    elif failure == "post_split": row["events"][0]["quantity"] = N("20")
    elif failure == "missing_event_id": row["events"][0].pop("id"); row["events"][0].pop("orderEventId")
    elif failure == "incomplete_filled_history": row["events"][0]["fillQuantity"] = N("5")
    else:
        row["events"] = [event(1, filled="5", status="partiallyFilled"),
            event(2, filled="5", fillPriceCurrency="EUR", time=epoch(SESSIONS[0], 9, 31))]
    result = run([row])
    value = normalized(result)[0]
    assert value["fill_quantity"] is value["reported_fee"] is None
    assert len(normalized(result)) == 1 and e.parse_json(result.public)["order_count"].fraction() == 1
    assert e.parse_json(result.observations[0])[0]["unavailable_reasons"]


@pytest.mark.parametrize("failure", ["duplicate_order", "duplicate_event", "foreign_event_order", "foreign_event_job",
    "negative_fee", "boolean_fee", "fractional_quantity", "wrong_fill_direction", "event_before_order", "event_clock_backwards",
    "nonfill_status_filled", "out_of_window", "wrong_created_time", "weekend"])
def test_conflicting_foreign_invalid_or_out_of_bound_observations_refuse(failure):
    row = order()
    rows = [row]
    if failure == "duplicate_order": rows.append(deepcopy(row))
    elif failure == "duplicate_event": row["events"].append(deepcopy(row["events"][0]))
    elif failure == "foreign_event_order": row["events"][0]["orderId"] = N("2")
    elif failure == "foreign_event_job": row["events"][0]["algorithmId"] = "foreign-job"
    elif failure == "negative_fee": row["events"][0]["orderFeeAmount"] = N("-1")
    elif failure == "boolean_fee": row["events"][0]["orderFeeAmount"] = True
    elif failure == "fractional_quantity": row["quantity"] = N("1.5")
    elif failure == "wrong_fill_direction": row["events"][0]["fillQuantity"] = N("-10")
    elif failure == "event_before_order": row["events"][0]["time"] = epoch(SESSIONS[0], 9, 19)
    elif failure == "event_clock_backwards":
        row["events"] = [event(1, filled="5", status="partiallyFilled", time=epoch(SESSIONS[0], 9, 31)),
                         event(2, filled="5")]
    elif failure == "nonfill_status_filled": row["events"][0]["status"] = "submitted"
    elif failure == "out_of_window": row["time"] = row["createdTime"] = "2020-12-31T15:00:00Z"
    elif failure == "wrong_created_time": row["createdTime"] = "2021-01-04T15:00:00Z"
    elif failure == "weekend": row["time"] = row["createdTime"] = "2021-01-02T15:00:00Z"
    with pytest.raises(ValueError): run(rows)


def test_99_order_pagination_complete_zero_census_and_explicit_no_fill_event():
    rows = [order(identity=number + 1, events=False) for number in range(105)]
    result = run(rows)
    assert [len(e.parse_json(raw)) for raw in result.pages] == [99, 6]
    assert e.parse_json(result.public)["order_count"].fraction() == 105
    assert n.metrics.order_pages_identity(list(result.pages)) == e.parse_json(result.public)["orders_sha256"]
    empty = run([])
    assert len(empty.pages) == 1 and e.parse_json(empty.pages[0]) == []
    canceled = order(status="Canceled")
    canceled["events"] = [event(filled="0", price="0", fee="0", status="canceled")]
    known = normalized(run([canceled]))[0]
    assert known["fill_quantity"].fraction() == 0 and known["reported_fee"].fraction() == 0
    assert known["fill_price"] is known["fill_currency"] is None


@pytest.mark.parametrize("failure", ["gap", "wrong_count", "missing_page", "envelope_hash", "projection_hash", "false_acceptance",
    "foreign_request", "foreign_response", "wrong_endpoint", "wrong_length", "partial_page", "checks"])
def test_explicit_collected_page_bindings_and_completeness_cannot_be_invented(failure):
    envelopes, collection = order_fixture([order(events=False)])
    if failure == "gap": collection["pages"][0]["start"] = 1
    elif failure == "wrong_count": collection["order_count"] = 2
    elif failure == "missing_page": envelopes.pop()
    elif failure == "envelope_hash": collection["pages"][0]["request_response_envelope_sha256"] = "0"*64
    elif failure == "projection_hash": collection["pages"][0]["response_projection_sha256"] = "0"*64
    elif failure == "false_acceptance": collection["strategy_accepted"] = True
    else:
        envelope = e.parse_json(envelopes[0])
        if failure == "foreign_request": envelope["request"]["backtestId"] = "foreign-job"
        elif failure == "foreign_response": envelope["response"]["projectId"] = N("999")
        elif failure == "wrong_endpoint": envelope["endpoint"] = "live/orders/read"
        elif failure == "wrong_length": envelope["response"]["length"] = N("2")
        elif failure == "partial_page": envelope["response"]["orders"].clear()
        elif failure == "checks": envelope["returned_identity_checks"]["absent_identifiers_inferred"] = True
        envelopes[0] = e.canonical(envelope)
        collection["pages"][0]["request_response_envelope_sha256"] = e.digest(envelopes[0])
        collection["pages"][0]["response_projection_sha256"] = e.digest(e.canonical(envelope["response"]))
    with pytest.raises(ValueError): run(envelopes=envelopes, collection=collection)
