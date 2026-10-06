"""Invented native QC exports: no retrieved run, authentication or price data."""
import ast
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.insider_buying import backtest_qc_export_adapter as module
from research.insider_buying import backtest_study_package as study
from test_insider_buying_backtest_study_package import _bundle_inputs


def _bytes(body):
    return study.canonical_bytes(body)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unix(value):
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400 + delta.seconds


def _stamp(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _capture(inputs, capture):
    result = dict(inputs)
    result["capture_manifest"] = _bytes(capture)
    result["trust_roots"] = module.QcExportTrustRoots(capture["trust_scope"], _sha(result["capture_manifest"]))
    return result


def _edit(inputs, role, edit, *, page=0):
    result = dict(inputs)
    capture = json.loads(result["capture_manifest"])
    if role in {"order_pages", "logs_pages"}:
        rows = list(result[role]); body = json.loads(rows[page]); edit(body)
        rows[page] = _bytes(body); result[role] = tuple(rows)
        capture[role][page]["sha256"] = _sha(rows[page])
    else:
        body = json.loads(result[role]); edit(body)
        result[role] = _bytes(body)
        key = {"native_backtest": "native_backtest_sha256", "native_order_events": "native_order_events_sha256", "project_files": "project_files_sha256", "native_compile": "native_compile_sha256"}[role]
        capture[key] = _sha(result[role])
    return _capture(result, capture)


def _edit_orders_and_events(inputs, edit):
    """Coherently rehash both fixture exports; never weaken their real checks."""
    result = dict(inputs); capture = json.loads(inputs["capture_manifest"])
    orders = [order for raw in inputs["order_pages"] for order in json.loads(raw)["orders"]]
    edit(orders)
    pages = tuple(_bytes({"orders": orders[start:start + 17], "length": len(orders[start:start + 17])}) for start in range(0, len(orders), 17))
    result["order_pages"] = pages
    result["native_order_events"] = _bytes([event for order in orders for event in order["events"]])
    capture["order_pages"] = [{"start": i * 17, "end": (i + 1) * 17, "sha256": _sha(raw)} for i, raw in enumerate(pages)]
    capture["native_order_events_sha256"] = _sha(result["native_order_events"])
    return _capture(result, capture)


def _native_inputs(bundle, package, *, failed=False):
    """Simulated external capture service, not a production provenance claim."""
    files, payload = package.files(), package.to_payload()
    manifest = json.loads(files["signals.json"])
    calendar = json.loads(bundle["evidence_artifacts"]["calendar"])
    clock = {r["session"]: r for r in calendar["sessions"]}
    orders, events = [], []
    for index, row in enumerate(manifest["signals"]):
        for side in ("entry", "exit"):
            oid = 2 * index + (1 if side == "entry" else 2)
            quantity = 10 if side == "entry" else -10
            fill_session = row[side + "_session"]
            prior = manifest["sessions"][manifest["sessions"].index(fill_session) - 1]
            submission = datetime.fromisoformat(clock[prior]["close_utc"].replace("Z", "+00:00")) + timedelta(minutes=1)
            opening = datetime.fromisoformat(clock[fill_session]["open_utc"].replace("Z", "+00:00"))
            native_events = []
            for event_id, (status, instant, filled, price) in enumerate((("submitted", submission, 0, 0), ("filled", opening, quantity, 100)), 1):
                native_events.append({"algorithmId": "invented-backtest", "symbol": row["qc_symbol_id"],
                    "symbolValue": row["ticker"], "symbolPermtick": row["ticker"], "orderId": oid,
                    "orderEventId": event_id, "id": f"order-{oid}-event-{event_id}", "status": status,
                    "orderFeeAmount": 1 if filled else 0, "orderFeeCurrency": "USD", "fillPrice": price,
                    "fillPriceCurrency": "USD", "fillQuantity": filled, "direction": "buy" if side == "entry" else "sell",
                    "message": "", "isAssignment": False, "stopPrice": 0, "limitPrice": 0, "quantity": quantity,
                    "time": _unix(instant), "isInTheMoney": False})
            events.extend(native_events)
            orders.append({"id": oid, "symbol": {"id": row["qc_symbol_id"], "value": row["ticker"], "permtick": row["ticker"]},
                "time": _stamp(submission), "createdTime": _stamp(submission), "lastFillTime": _stamp(opening),
                "quantity": quantity, "type": 4, "securityType": 1, "status": 3,
                "tag": f'IB5:{payload["registered_look_id"]}:{row["signal_id"]}:{side.upper()}',
                "direction": 0 if side == "entry" else 1, "events": native_events})
    pages = tuple(_bytes({"orders": orders[start:start + 17], "length": len(orders[start:start + 17])}) for start in range(0, len(orders), 17))
    markers = [f'IBQC_STUDY_INPUT|look={payload["registered_look_id"]}|manifest={_sha(files["signals.json"])}|gate={_sha(files["gate.json"])}|signals={len(manifest["signals"])}|canonical=false',
        f'IBQC_STUDY_ORDER_PATH_COMPLETE|look={payload["registered_look_id"]}|manifest={_sha(files["signals.json"])}|entries={len(manifest["signals"])}|exits={len(manifest["signals"])}|canonical=false']
    result = {"package": package, "native_backtest": _bytes({"success": True, "errors": [], "debugging": False,
        "backtest": {"projectId": 7, "backtestId": "invented-backtest", "completed": True,
            "status": "Runtime Error" if failed else "Completed.", "error": "invented failure" if failed else "",
            "stacktrace": "", "hasInitializeError": False, "statistics": {"Total Orders": str(len(orders))},
            "runtimeStatistics": {"Holdings": "$0.00"}, "serverStatistics": {"LEAN Version": "invented-lean-revision"}}}),
        "order_pages": pages, "native_order_events": _bytes(events),
        "project_files": _bytes({"success": True, "errors": [], "files": [{"projectId": 7, "name": "main.py", "content": files["main.py"].decode(), "isLibrary": False}]}),
        "cloud_signal_manifest": files["signals.json"], "cloud_gate": files["gate.json"],
        "calendar": bundle["evidence_artifacts"]["calendar"],
        "logs_pages": (_bytes({"success": True, "errors": [], "logs": markers, "length": 2}),)}
    capture = {"schema": "insider-qc-export-capture-v1", "profile": module.PROFILE, "trust_scope": payload["trust_scope"],
        "origin": "invented-native-QC-export" if payload["trust_scope"] == "fixture" else "authenticated-QC-export",
        "mode": "backtest", "package_sha256": package.sha256, "project_id": 7, "compile_id": "invented-compile",
        "backtest_id": "invented-backtest", "attempt_id": "attempt-1", "compiled_source_sha256": _sha(files["main.py"]),
        "project_files_sha256": _sha(result["project_files"]), "signal_manifest_sha256": _sha(files["signals.json"]),
        "gate_sha256": _sha(files["gate.json"]), "calendar_sha256": _sha(result["calendar"]),
        "native_backtest_sha256": _sha(result["native_backtest"]), "native_compile_sha256": None,
        "native_order_events_sha256": _sha(result["native_order_events"]),
        "order_pages": [{"start": i * 17, "end": (i + 1) * 17, "sha256": _sha(raw)} for i, raw in enumerate(pages)],
        "logs_pages": [{"start": 0, "end": 200, "sha256": _sha(result["logs_pages"][0])}]}
    return _capture(result, capture)


@pytest.fixture(scope="module")
def inputs():
    bundle = _bundle_inputs()
    return _native_inputs(bundle, study.build_backtest_study_package(**bundle))


def test_native_orders_events_and_source_derive_real_terminal_values_without_retrieval_claim(inputs):
    result = module.adapt_qc_export(**inputs)
    summary, terminal = result.to_payload(), json.loads(result.terminal_bytes())
    assert summary["native_order_count"] == 40 and summary["native_order_event_count"] == 80
    assert summary["complete_order_path"] is True and result.analysis()["order_path_verified"] is True
    assert terminal["fills"][0]["quantity"] == 10 and terminal["fills"][0]["price"] == "100"
    assert terminal["fills"][0]["order_id"] == "1" and terminal["final_positions"] == []
    assert summary["capture_manifest_sha256"] == inputs["trust_roots"].capture_manifest_sha256
    assert summary["statistical_gate"] == "UNADJUDICATED" and summary["ib5_pass"] is False
    assert all(summary[key] is False for key in ("engine_revision_parity_verified", "data_vintage_parity_verified",
        "brokerage_cost_model_parity_verified", "opening_price_model_parity_verified", "execution_performed_here", "broker_authority"))
    assert summary["qc_jobs_launched_here"] == summary["research_looks_spent_here"] == 0


def test_runtime_failure_is_not_completed_and_can_finish_existing_pending_attempt(inputs):
    changed = _edit(inputs, "native_backtest", lambda b: b["backtest"].update(status="Runtime Error", error="invented failure"))
    result = module.adapt_qc_export(**changed)
    assert result.analysis()["order_path_verified"] is False
    package = inputs["package"]; payload = package.to_payload()
    ledger = study.new_attempt_ledger(candidate_id=payload["candidate_id"], registered_look_id=payload["registered_look_id"], trust_scope="fixture")
    ledger = study.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="attempt-1")
    ledger = study.finish_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package,
        result_raw=result.terminal_bytes(), expected_result_sha256=result.to_payload()["terminal_sha256"])
    assert json.loads(ledger)["attempts"][0]["state"] == "runtime_failed"


@pytest.mark.parametrize("role", ["native_backtest", "native_order_events", "project_files", "calendar", "capture_manifest"])
def test_unchanged_external_root_refuses_changed_native_bytes(inputs, role):
    changed = dict(inputs); changed[role] += b" "
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**changed)


@pytest.mark.parametrize("field,value", [("project_id", True), ("compile_id", "other-compile"), ("backtest_id", "other-backtest"),
    ("package_sha256", "f" * 64), ("compiled_source_sha256", "f" * 64), ("signal_manifest_sha256", "f" * 64),
    ("gate_sha256", "f" * 64), ("calendar_sha256", "f" * 64), ("trust_scope", "production"), ("profile", "unknown"),
    ("mode", "compile_failure"), ("origin", "caller-approved"), ("extra_authority", True)])
def test_reanchored_invented_capture_still_crossbinds_every_context(inputs, field, value):
    capture = json.loads(inputs["capture_manifest"]); capture[field] = value
    # Compile identity association is authenticated externally, not in backtest/read.
    if field == "compile_id":
        result = module.adapt_qc_export(**_capture(inputs, capture))
        assert json.loads(result.terminal_bytes())["compile_id"] == value
        return
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_capture(inputs, capture))


@pytest.mark.parametrize("edit", [lambda b: b["backtest"].update(projectId=True), lambda b: b["backtest"].update(backtestId="other"),
    lambda b: b["backtest"].update(completed=1), lambda b: b["backtest"].update(hasInitializeError=0),
    lambda b: b["backtest"].update(status="Running"), lambda b: b["backtest"].update(status=[]),
    lambda b: b["backtest"]["statistics"].update({"Total Orders": "39"}), lambda b: b["backtest"]["statistics"].update({"Total Orders": 40}),
    lambda b: b.update(success=1), lambda b: b.update(errors=["native API refused"]), lambda b: b["backtest"].update(approved=True)])
def test_native_backtest_types_errors_counts_and_unknown_promotions_refuse(inputs, edit):
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_edit(inputs, "native_backtest", edit))


@pytest.mark.parametrize("field,value", [("id", True), ("id", 2), ("type", 0), ("type", True), ("securityType", 2),
    ("direction", 1), ("quantity", 0), ("quantity", -10), ("quantity", 10.5), ("quantity", True),
    ("status", 2), ("tag", "unattributed"), ("time", "2023-01-01T00:00:00Z"), ("lastFillTime", None)])
def test_reanchored_native_orders_cannot_change_trade_attribution_direction_type_or_time(inputs, field, value):
    with pytest.raises(module.QcExportAdapterError):
        module.adapt_qc_export(**_edit(inputs, "order_pages", lambda b: b["orders"][0].update({field: value})))


@pytest.mark.parametrize("field,value", [("algorithmId", "other-backtest"), ("symbol", "other-SID"), ("orderId", True),
    ("orderEventId", 9), ("fillQuantity", 9), ("fillPrice", 0), ("fillPrice", -1), ("fillPriceCurrency", "EUR"),
    ("orderFeeAmount", -1), ("quantity", 9), ("status", "partiallyFilled"), ("direction", "sell"),
    ("isAssignment", 0), ("isInTheMoney", True), ("time", 0)])
def test_reanchored_native_events_require_full_consistent_nonpartial_money_time_and_lineage(inputs, field, value):
    with pytest.raises(module.QcExportAdapterError):
        module.adapt_qc_export(**_edit(inputs, "order_pages", lambda b: b["orders"][0]["events"][1].update({field: value})))


@pytest.mark.parametrize("edit", [lambda b: b.pop(), lambda b: b.reverse(), lambda b: b.append(b[0]),
    lambda b: b[0].update(quantity=True), lambda b: b[0].update(approved=True)])
def test_separate_native_event_export_cannot_drop_reorder_duplicate_or_promote(inputs, edit):
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_edit(inputs, "native_order_events", edit))


@pytest.mark.parametrize("field,value", [("orderId", True), ("orderEventId", True),
    ("fillQuantity", False), ("orderFeeAmount", False), ("isAssignment", 0)])
def test_native_event_cross_export_equality_is_typed_not_python_bool_int_equality(inputs, field, value):
    with pytest.raises(module.QcExportAdapterError):
        module.adapt_qc_export(**_edit(inputs, "native_order_events", lambda body: body[0].update({field: value})))


@pytest.mark.parametrize("change", ["gap", "overlap", "reorder", "missing", "unknown", "bool", "too_wide", "wrong_length"])
def test_pagination_completeness_is_not_native_returned_length_or_caller_flag(inputs, change):
    changed = dict(inputs); capture = json.loads(inputs["capture_manifest"])
    if change == "gap": capture["order_pages"][1]["start"] += 1
    elif change == "overlap": capture["order_pages"][1]["start"] -= 1
    elif change == "reorder": capture["order_pages"].reverse(); changed["order_pages"] = tuple(reversed(inputs["order_pages"]))
    elif change == "missing": capture["order_pages"].pop(); changed["order_pages"] = inputs["order_pages"][:-1]
    elif change == "unknown": capture["order_pages"][0]["complete"] = True
    elif change == "bool": capture["order_pages"][0]["start"] = False
    elif change == "too_wide": capture["order_pages"][0]["end"] = 100
    else:
        changed = _edit(inputs, "order_pages", lambda b: b.update(length=40))
        capture = json.loads(changed["capture_manifest"])
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_capture(changed, capture))


@pytest.mark.parametrize("role,edit", [("project_files", lambda b: b["files"][0].update(content="pass\n")),
    ("project_files", lambda b: b["files"].append(b["files"][0])), ("project_files", lambda b: b["files"][0].update(projectId=True)),
    ("project_files", lambda b: b["files"][0].update(isLibrary=0)), ("project_files", lambda b: b["files"][0].update(name="other.py"))])
def test_cloud_source_parity_checks_contents_not_source_hash_claim(inputs, role, edit):
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_edit(inputs, role, edit))


@pytest.mark.parametrize("role", ["cloud_signal_manifest", "cloud_gate"])
def test_supplied_cloud_object_bytes_must_equal_exported_package_exactly(inputs, role):
    changed = dict(inputs); changed[role] += b" "
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**changed)


@pytest.mark.parametrize("change", ["missing_end", "wrong_look", "duplicate_end", "wrong_count", "holdings", "native_error", "init_error", "not_completed"])
def test_completed_alone_does_not_prove_full_source_session_or_order_path(inputs, change):
    if change == "holdings": changed = _edit(inputs, "native_backtest", lambda b: b["backtest"]["runtimeStatistics"].update(Holdings="$1.00"))
    elif change == "native_error": changed = _edit(inputs, "native_backtest", lambda b: b["backtest"].update(error="invented error"))
    elif change == "init_error": changed = _edit(inputs, "native_backtest", lambda b: b["backtest"].update(hasInitializeError=True))
    elif change == "not_completed": changed = _edit(inputs, "native_backtest", lambda b: b["backtest"].update(completed=False))
    else:
        def edit(body):
            if change == "missing_end": body["logs"].pop(); body["length"] = 1
            elif change == "wrong_look": body["logs"][1] = body["logs"][1].replace("invented-study-1", "other-study")
            elif change == "duplicate_end": body["logs"].append(body["logs"][1]); body["length"] = 3
            else: body["logs"][1] = body["logs"][1].replace("entries=20", "entries=19")
        changed = _edit(inputs, "logs_pages", edit)
    assert module.adapt_qc_export(**changed).analysis()["order_path_verified"] is False


def test_decimal_json_numbers_and_ambient_precision_cannot_change_native_time_or_finance(inputs):
    expected = module.adapt_qc_export(**inputs).terminal_bytes()
    with localcontext() as context:
        context.prec = 3
        assert module.adapt_qc_export(**inputs).terminal_bytes() == expected


@pytest.mark.parametrize("number", [Decimal("1000000000001"), Decimal("-1000000000001")])
def test_native_share_profile_bound_is_exact_under_low_decimal_precision(number):
    with localcontext() as context:
        context.prec = 5
        with pytest.raises(module.QcExportAdapterError, match="unbounded native shares"):
            module._shares(number)
        assert module._shares(Decimal("1000000000000")) == 1000000000000
        assert module._shares(Decimal("-1000000000000")) == -1000000000000


def test_native_actual_decimal_price_is_ingested_and_equivalent_number_spelling_is_exact(inputs):
    changed = _edit_orders_and_events(inputs, lambda orders: orders[0]["events"][1].update(fillPrice=100.125))
    result = module.adapt_qc_export(**changed)
    assert json.loads(result.terminal_bytes())["fills"][0]["price"] == "100.125"
    capture = json.loads(changed["capture_manifest"])
    events = changed["native_order_events"].replace(b'"fillQuantity":10,', b'"fillQuantity":10.0,')
    changed = dict(changed, native_order_events=events)
    capture["native_order_events_sha256"] = _sha(events)
    assert module.adapt_qc_export(**_capture(changed, capture)).terminal_bytes() == result.terminal_bytes()


def test_full_native_lifecycle_can_represent_failure_with_pending_exits_and_residual_positions(inputs):
    def edit(orders):
        for order in orders:
            if order["direction"] == 1:
                order.update(status=1, lastFillTime=None, events=order["events"][:1])
    changed = _edit_orders_and_events(inputs, edit)
    changed = _edit(changed, "native_backtest", lambda b: b["backtest"].update(status="Runtime Error", error="invented failure"))
    result = module.adapt_qc_export(**changed)
    terminal = json.loads(result.terminal_bytes())
    assert len(terminal["fills"]) == 20 and len(terminal["final_positions"]) == 20
    assert all(row["quantity"] == 10 for row in terminal["final_positions"])
    assert "native_order_not_fully_filled" in terminal["errors"]
    assert result.analysis()["order_path_verified"] is False


def test_coherently_rehashed_exit_quantity_mismatch_is_invalid_not_success(inputs):
    def edit(orders):
        order = orders[1]; order["quantity"] = -11
        for event in order["events"]:
            event["quantity"] = -11
            if event["status"] == "filled": event["fillQuantity"] = -11
    result = module.adapt_qc_export(**_edit_orders_and_events(inputs, edit))
    assert result.analysis()["order_path_verified"] is False
    assert json.loads(result.terminal_bytes())["final_positions"]


@pytest.mark.parametrize("seconds,accepted", [(60, True), (61, False)])
def test_native_opening_minute_timestamp_profile_is_explicit_and_does_not_certify_price_model(inputs, seconds, accepted):
    def edit(orders):
        event = orders[0]["events"][1]; event["time"] += seconds
        orders[0]["lastFillTime"] = _stamp(datetime.fromisoformat(orders[0]["lastFillTime"].replace("Z", "+00:00")) + timedelta(seconds=seconds))
    changed = _edit_orders_and_events(inputs, edit)
    if accepted:
        result = module.adapt_qc_export(**changed)
        assert result.analysis()["order_path_verified"] is True
        assert result.to_payload()["opening_price_model_parity_verified"] is False
    else:
        with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**changed)


def test_production_branch_requires_configured_source_and_keeps_simulated_authority_distinct():
    # Only an invented trusted-service simulation. No retrieved/authenticated run.
    bundle = _bundle_inputs(scope="production", plan=True)
    disabled = study.build_backtest_study_package(**bundle)
    with pytest.raises(module.QcExportAdapterError, match="configured"):
        module.adapt_qc_export(**_native_inputs(bundle, disabled))
    configured = study.configure_registered_qc_candidate(disabled)
    inputs = _native_inputs(bundle, configured)
    result = module.adapt_qc_export(**inputs)
    assert result.to_payload()["capture_trust_scope"] == "production"
    assert result.to_payload()["complete_order_path"] is True
    assert result.to_payload()["provenance_boundary"] == "externally_anchored_capture_not_authenticated_here"


@pytest.mark.parametrize("role,value", [("order_pages", []), ("logs_pages", []), ("order_pages", ("bad",)),
    ("native_backtest", "bad"), ("native_order_events", b"[]"), ("project_files", None), ("calendar", b"{}")])
def test_native_input_container_and_byte_shapes_refuse_without_implicit_io(inputs, role, value):
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**dict(inputs, **{role: value}))


@pytest.mark.parametrize("scope", [True, 0, None, "unknown"])
def test_external_root_scope_cannot_be_promoted_or_coerced(inputs, scope):
    root = module.QcExportTrustRoots(scope, inputs["trust_roots"].capture_manifest_sha256)
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**dict(inputs, trust_roots=root))


@pytest.mark.parametrize("edit", [lambda b: b.update(length=1), lambda b: b.update(length=True),
    lambda b: b.update(success=1), lambda b: b.update(errors=["API failure"]), lambda b: b.update(complete=True)])
def test_native_log_completeness_and_response_types_are_enforced(inputs, edit):
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_edit(inputs, "logs_pages", edit))


def test_native_log_marker_must_be_unique_correctly_ordered_and_source_bound(inputs):
    wrong_input = _edit(inputs, "logs_pages", lambda b: b["logs"].__setitem__(0, b["logs"][0].replace("signals=20", "signals=19")))
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**wrong_input)
    reversed_logs = _edit(inputs, "logs_pages", lambda b: b["logs"].reverse())
    assert module.adapt_qc_export(**reversed_logs).analysis()["order_path_verified"] is False


def test_duplicate_and_nonfinite_native_json_never_survive_external_rehash(inputs):
    for raw in (b'{"success":true,"success":true}', b'{"success":NaN}'):
        changed = dict(inputs, native_backtest=raw)
        capture = json.loads(inputs["capture_manifest"]); capture["native_backtest_sha256"] = _sha(raw)
        with pytest.raises(module.QcExportAdapterError): module.adapt_qc_export(**_capture(changed, capture))


def test_result_detaches_and_reconstruction_replacement_or_mutation_refuses(inputs):
    result = module.adapt_qc_export(**inputs)
    detached = result.to_payload(); detached["ib5_pass"] = True
    assert result.to_payload()["ib5_pass"] is False
    forged = replace(result)
    with pytest.raises(module.QcExportAdapterError): forged.to_payload()
    object.__setattr__(result, "_bytes", result._bytes + b" ")
    with pytest.raises(module.QcExportAdapterError): result.to_payload()


def _compile_inputs(inputs, *, attempt="attempt-1"):
    result = {key: inputs[key] for key in ("package", "project_files", "cloud_signal_manifest", "cloud_gate")}
    result["native_compile"] = _bytes({"success": True, "errors": [], "compileId": "invented-compile", "state": "BuildError", "logs": ["invented compile failure"]})
    capture = json.loads(inputs["capture_manifest"])
    capture.update(mode="compile_failure", backtest_id=None, attempt_id=attempt, native_compile_sha256=_sha(result["native_compile"]),
        native_backtest_sha256=None, native_order_events_sha256=None, calendar_sha256=None, order_pages=[], logs_pages=[])
    return _capture(result, capture)


def test_native_compile_failure_without_backtest_reuses_three_attempt_accounting(inputs):
    package = inputs["package"]; payload = package.to_payload()
    ledger = study.new_attempt_ledger(candidate_id=payload["candidate_id"], registered_look_id=payload["registered_look_id"], trust_scope="fixture")
    for number in range(1, 4):
        attempt = f"attempt-{number}"
        result = module.adapt_qc_compile_failure(**_compile_inputs(inputs, attempt=attempt))
        terminal = json.loads(result.terminal_bytes())
        assert terminal["backtest_id"] is None and terminal["status"] == "CompileError"
        assert terminal["fills"] == [] and terminal["submitted_order_count"] == 0
        ledger = study.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id=attempt)
        ledger = study.finish_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package,
            result_raw=result.terminal_bytes(), expected_result_sha256=result.to_payload()["terminal_sha256"])
    assert study.attempt_ledger_status(ledger)["requires_mia"] is True
    with pytest.raises(study.StudyPackageError):
        study.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="attempt-4")


@pytest.mark.parametrize("field,value", [("compileId", "other"), ("state", "InQueue"), ("state", "BuildSuccess"), ("logs", []), ("success", 1), ("approved", True)])
def test_native_compile_profile_refuses_nonterminal_success_or_foreign_identity(inputs, field, value):
    changed = _compile_inputs(inputs)
    changed = _edit(changed, "native_compile", lambda body: body.update({field: value}))
    with pytest.raises(module.QcExportAdapterError): module.adapt_qc_compile_failure(**changed)


def _registered_inputs(monkeypatch, *, compatible=True):
    """Genuine parent→pipeline→package→native-export fixture, not a run claim."""
    import test_insider_buying_backtest_study_package as package_fixtures
    from test_insider_buying_backtest_evidence_pipeline import _edit as edit_pipeline
    from research.insider_buying import backtest_registered_analysis as registered
    original_fixture = package_fixtures.make_pipeline_fixture
    def fixture():
        options = {"filed": {i: "2023-02-24" for i in range(40)},
                   "acceptance": {i: "20230224120000" for i in range(40)}} if compatible else None
        kwargs = original_fixture(options)
        rows, current, eastern = [], date(2022, 1, 3), ZoneInfo("America/New_York")
        while len(rows) < 600:
            if current.weekday() < 5:
                rows.append({"session": current.isoformat(),
                    "open_utc": _stamp(datetime(current.year, current.month, current.day, 9, 30, tzinfo=eastern).astimezone(timezone.utc)),
                    "close_utc": _stamp(datetime(current.year, current.month, current.day, 16, 0, tzinfo=eastern).astimezone(timezone.utc))})
            current += timedelta(days=1)
        return edit_pipeline(kwargs, "calendar", lambda body: body.update(sessions=rows), crossbind=True)
    # Invented helper seam only; no production factory, pin or guard is changed.
    with monkeypatch.context() as context:
        context.setattr(package_fixtures, "make_pipeline_fixture", fixture)
        bundle = package_fixtures._bundle_inputs()
    package = study.build_backtest_study_package(**bundle)
    native = _native_inputs(bundle, package)
    payload, qc = package.to_payload(), json.loads(package.files()["signals.json"])
    sessions = json.loads(bundle["evidence_artifacts"]["calendar"])["sessions"]
    implementation = "a" * 64
    registration = {"schema": "insider-stock-analysis-registration-v1", "trust_scope": "fixture",
        "registered_look_id": payload["registered_look_id"], "candidate_id": payload["candidate_id"],
        "policy": registered.frozen_analysis_policy(),
        "analysis_plan": registered.analysis_plan_descriptors(implementation_sha256=implementation),
        "registered_at_utc": "2022-01-01T00:00:00Z", "first_outcome_access_utc": "2023-03-01T00:00:00Z",
        "implementation_sha256": implementation, "source_manifest_sha256": qc["source_manifest_sha256"],
        "security_master_sha256": qc["security_master_sha256"], "calendar_sha256": _sha(_bytes(sessions)),
        "outcome_vintage_sha256": qc["outcome_vintage_sha256"], "rights_sha256": payload["artifact_sha256s"]["rights"],
        "prior_variance_calibration_sha256": "e" * 64}
    scored = {r["qc_symbol_id"]: r for r in bundle["pipeline_result"].scored_rows()}
    admitted = bundle["pipeline_result"].admitted_events()
    events = [{"signal_id": signal["signal_id"], "issuer_id": scored[signal["qc_symbol_id"]]["issuer_cik"],
        "security_id": signal["qc_symbol_id"], "available_at_utc": signal["available_at_utc"].replace("+00:00", "Z"),
        "entry_session": signal["entry_session"], "exit_session": signal["exit_session"],
        "source_event_sha256": signal["source_event_sha256"],
        "buyer_ids": sorted({r["owner_cik"] for r in admitted if r["qc_symbol_id"] == signal["qc_symbol_id"]}),
        "score": scored[signal["qc_symbol_id"]]["raw_stock_score"], "earnings_distance_sessions": 10, "regime": "bull"}
        for signal in qc["signals"]]
    manifest = {"schema": "insider-stock-event-study-manifest-v1", "trust_scope": "fixture",
        "registration_sha256": _sha(_bytes(registration)), "source_manifest_sha256": qc["source_manifest_sha256"],
        "security_master_sha256": qc["security_master_sha256"], "calendar_sha256": registration["calendar_sha256"],
        "outcome_vintage_sha256": qc["outcome_vintage_sha256"], "sessions": sessions,
        "eligible_control_security_ids": ["CONTROL-1", "CONTROL-2", "CONTROL-3"], "events": events}
    return native, registration, manifest, implementation


def _bridge_kwargs(registration, manifest, implementation):
    registration_raw, manifest_raw = _bytes(registration), _bytes(manifest)
    return {"registration_raw": registration_raw, "manifest_raw": manifest_raw,
        "expected_registration_sha256": _sha(registration_raw), "expected_manifest_sha256": _sha(manifest_raw),
        "expected_implementation_sha256": implementation}


def test_native_to_registered_terminal_bridge_preserves_real_instants_prices_ids_and_exact_first_open(monkeypatch):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    result = module.adapt_qc_export(**inputs)
    raw = result.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))
    terminal = json.loads(raw)
    assert terminal["schema"] == "insider-stock-event-study-terminal-v1" and len(terminal["fills"]) == 40
    native = result.native_fills()[0]; exported = terminal["fills"][0]
    assert exported["filled_at_utc"] == native["filled_at_utc"] == "2023-02-27T14:30:00Z"
    assert exported["security_id"] == native["qc_symbol_id"] and exported["quantity"] == native["quantity"]
    assert exported["price"] == native["price"] and exported["order_id"] == native["order_id"]
    assert "issuer_id" not in exported  # Never reverse-engineer an issuer from a SID.
    copy = result.native_fills(); copy[0]["filled_at_utc"] = "2000-01-01T00:00:00Z"
    assert result.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation)) == raw
    assert result.to_payload()["ib5_pass"] is False


def test_daily_close_delayed_parent_availability_is_not_coerced_into_first_open_analysis(monkeypatch):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch, compatible=False)
    result = module.adapt_qc_export(**inputs)
    assert result.analysis()["order_path_verified"] is True  # Valid only for its own distinct clock.
    with pytest.raises(module.QcExportAdapterError, match="event-clock"):
        result.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


def test_native_minute_end_timestamp_cannot_be_replaced_by_invented_exact_open_for_analysis(monkeypatch):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    def edit(orders):
        orders[0]["events"][1]["time"] += 60
        orders[0]["lastFillTime"] = "2023-02-27T14:31:00Z"
    result = module.adapt_qc_export(**_edit_orders_and_events(inputs, edit))
    assert result.analysis()["order_path_verified"] is True
    with pytest.raises(module.QcExportAdapterError, match="exact registered"):
        result.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


@pytest.mark.parametrize("field", ["candidate_id", "registered_look_id", "rights_sha256", "source_manifest_sha256", "outcome_vintage_sha256"])
def test_registered_bridge_reanchored_epoch_or_lineage_must_still_match_native_package(monkeypatch, field):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    registration[field] = "other" if field.endswith("id") else "f" * 64
    manifest["registration_sha256"] = _sha(_bytes(registration))
    if field in manifest: manifest[field] = registration[field]
    with pytest.raises(module.QcExportAdapterError):
        module.adapt_qc_export(**inputs).registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


@pytest.mark.parametrize("field,value", [("security_id", "other-SID"), ("source_event_sha256", "f" * 64),
    ("available_at_utc", "2023-02-24T18:00:00Z")])
def test_registered_bridge_reanchored_event_cannot_replace_actual_native_source_security_or_time(monkeypatch, field, value):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    manifest["events"][0][field] = value
    with pytest.raises(module.QcExportAdapterError):
        module.adapt_qc_export(**inputs).registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


def test_registered_bridge_full_calendar_instants_not_only_session_dates_must_match_native_capture(monkeypatch):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    manifest["sessions"][0]["open_utc"] = manifest["sessions"][0]["open_utc"].replace("14:30", "14:31")
    registration["calendar_sha256"] = manifest["calendar_sha256"] = _sha(_bytes(manifest["sessions"]))
    manifest["registration_sha256"] = _sha(_bytes(registration))
    with pytest.raises(module.QcExportAdapterError, match="calendar instants"):
        module.adapt_qc_export(**inputs).registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


def test_registered_bridge_requires_clean_factory_native_result_and_external_implementation_identity(monkeypatch):
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    kwargs = _bridge_kwargs(registration, manifest, implementation)
    result = module.adapt_qc_export(**inputs)
    with pytest.raises(module.QcExportAdapterError):
        replace(result).registered_terminal_bytes(**kwargs)
    kwargs["expected_implementation_sha256"] = "f" * 64
    with pytest.raises(module.QcExportAdapterError): result.registered_terminal_bytes(**kwargs)
    failed = module.adapt_qc_export(**_edit(inputs, "native_backtest", lambda b: b["backtest"].update(error="invented error")))
    with pytest.raises(module.QcExportAdapterError, match="clean"):
        failed.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))


def test_adapter_imports_no_client_cloud_entry_or_external_access_interfaces():
    source = (Path(__file__).resolve().parents[1] / "research/insider_buying/backtest_qc_export_adapter.py").read_bytes()
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"__future__", "dataclasses", "datetime", "decimal", "research.insider_buying"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "exec", "eval"} for node in ast.walk(tree))
