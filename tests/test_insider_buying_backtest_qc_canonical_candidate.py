"""Invented native captures and mocked LEAN only; no data, QC job or outcome access."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo

import pytest

from research.insider_buying import backtest_qc_canonical_candidate as module
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_qc_export_adapter as native
from test_insider_buying_backtest_event_study_manifest import make_causal_fixture, _edit, _reanchor, stream_reference_fixture
from test_insider_buying_qc_stock_order_study import _Algorithm, _Portfolio, study as old_study


def enc(value):
    return analysis.canonical_bytes(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


LEGACY = Path(__file__).resolve().parents[1] / "research/insider_buying_qc_stock_order_study.py"


def build(kwargs):
    return module.build_canonical_qc_batch_plan(source_events=causal.build_source_event_study_manifest(**kwargs),
        legacy_source=LEGACY.read_bytes(), security_master=kwargs["security_master"],
        entry_reference=kwargs["entry_reference"], registration=kwargs["registration"], parent_study_id="fixture-parent")


@pytest.fixture(scope="module")
def inputs():
    kwargs = make_causal_fixture()
    return kwargs, build(kwargs)


@pytest.fixture
def generated(inputs, old_study, monkeypatch):
    fake = types.ModuleType("canonical_qc_synthetic")
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    exec(compile(inputs[1].batch_files(0)["main.py"], "<invented-canonical-qc>", "exec"), fake.__dict__)
    return fake


def configured(generated, plan):
    files = plan.batch_files(0)
    generated.RESEARCH_BACKTEST_ENABLED = True  # Mock-only, no source emission/authorization.
    algorithm = generated.InsiderBuyingStockOrderStudy()
    algorithm.time_rules.before_market_open = lambda symbol, minutes: ("before", symbol, minutes)
    original = algorithm.add_equity
    mapping = {row["ticker"]: row["qc_symbol_id"] for row in json.loads(files["signals.json"])["signals"]}
    def add(ticker, resolution, **kwargs):
        result = original(ticker, resolution, **kwargs)
        result.symbol.id = mapping.get(ticker, str(result.symbol.id))
        return result
    algorithm.add_equity = add
    algorithm.object_store.content.update({generated.SIGNAL_OBJECT_STORE_KEY: files["signals.json"], generated.GATE_OBJECT_STORE_KEY: files["gate.json"]})
    algorithm.initialize()
    algorithm.portfolio = _Portfolio(100000, algorithm.holdings)
    return algorithm


def at(algorithm, instant):
    algorithm.utc_time = instant.replace(tzinfo=None)
    algorithm.time = instant.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)


def test_sealed_genuine_causal_population_partitions_without_legacy_or_authority_changes(inputs):
    kwargs, plan = inputs
    payload = plan.to_payload(); files = plan.batch_files(0)
    assert payload["event_count"] == payload["batch_count"] == 1
    assert payload["all_batches_required_before_analysis"] is True and payload["maximum_attempts_per_candidate"] == 3
    assert payload["pooled_capital_portfolio_inferred"] is False
    assert payload["candidate_enabled"] is payload["dispatch_enabled"] is payload["look_authority"] is False
    assert payload["qc_jobs"] == payload["research_looks"] == 0
    assert sha(LEGACY.read_bytes()) == module.LEGACY_SOURCE_SHA256
    assert b"RESEARCH_BACKTEST_ENABLED = False" in files["main.py"]
    assert b"before_market_open(self._clock_symbol, 2)" in files["main.py"]
    assert b"after_market_close" in files["main.py"]
    assert json.loads(files["signals.json"])["signals"][0]["entry_session"] == "2023-01-16"
    assert build(kwargs).sha256 == plan.sha256


def test_generated_default_disabled_and_live_refuse_before_object_store_or_subscription(generated):
    algorithm = generated.InsiderBuyingStockOrderStudy()
    with pytest.raises(generated.StockStudyRefusal): algorithm.initialize()
    assert algorithm.subscriptions == [] and algorithm.orders == []
    generated.RESEARCH_BACKTEST_ENABLED = True; algorithm.live_mode = True
    with pytest.raises(generated.StockStudyRefusal): algorithm.initialize()
    assert algorithm.subscriptions == []


@pytest.mark.parametrize("role", ["security_master", "entry_reference", "registration", "legacy_source", "source_events"])
def test_unanchored_or_reconstructed_prerequisites_refuse(inputs, role):
    kwargs, plan = inputs
    call = dict(source_events=causal.build_source_event_study_manifest(**kwargs), legacy_source=LEGACY.read_bytes(),
        security_master=kwargs["security_master"], entry_reference=kwargs["entry_reference"], registration=kwargs["registration"], parent_study_id="fixture-parent")
    call[role] = {} if role == "source_events" else call[role] + b" "
    with pytest.raises((module.CanonicalQcCandidateError, analysis.RegisteredAnalysisError)): module.build_canonical_qc_batch_plan(**call)


@pytest.mark.parametrize("stamp,accepted", [("20230113092800", True), ("20230113092801", False), ("20230113092959", False)])
def test_whole_plan_two_minute_cutoff_never_drops_or_forwards_event(stamp, accepted):
    kwargs = make_causal_fixture(specs=(("4", "2023-01-13", "123456", "0000123456-23-000001", stamp),))
    if accepted:
        assert build(kwargs).to_payload()["event_count"] == 1
    else:
        with pytest.raises(module.CanonicalQcCandidateError, match="whole plan"): build(kwargs)


@pytest.mark.parametrize("kind", ["entry", "earnings", "price"])
def test_reference_known_after_cutoff_refuses_whole_source_plan(kind):
    kwargs = make_causal_fixture()
    def edit(body):
        row = body["entries"][0]; instant = "2023-01-16T14:29:00Z"
        if kind == "entry": row["knowledge_at_utc"] = instant
        elif kind == "earnings": row["earnings_rows"][0]["knowledge_at_utc"] = instant
        else:
            row["stock_context"]["rows"][0]["history"][-1]["knowledge_at_utc"] = instant
            row["stock_context_sha256"] = sha(enc(row["stock_context"]))
    kwargs = _edit(kwargs, "entry_reference", edit)
    with pytest.raises(module.CanonicalQcCandidateError, match="prerequisite reference"): build(kwargs)


def test_streamed_reference_descriptors_use_sealed_compact_fact_cutoffs(inputs):
    kwargs, _ = stream_reference_fixture(inputs[0])
    assert build(kwargs).to_payload()["event_count"] == 1


@pytest.mark.parametrize("value", [True, -1, 1, "0", None])
def test_child_index_exact_type_and_range(inputs, value):
    with pytest.raises(module.CanonicalQcCandidateError): inputs[1].batch_files(value)


def test_plan_detached_copies_and_direct_resealing_refuse(inputs):
    plan = inputs[1]; body = plan.to_payload(); body["batch_ids"].clear()
    assert plan.to_payload()["batch_count"] == 1
    with pytest.raises(module.CanonicalQcCandidateError): replace(plan).to_payload()
    with pytest.raises(module.CanonicalQcCandidateError): module.CanonicalQcBatchPlan(plan._bytes, plan._token).batch_files(0)


@pytest.mark.parametrize("mode", ["missing", "duplicated", "reordered"])
def test_guarded_source_replacement_fails_closed_without_captured_anchor(mode):
    if mode == "missing": call = lambda: module._exact("safe", "old", "new")
    elif mode == "duplicated": call = lambda: module._span("start start end", "start", "end", "new")
    else: call = lambda: module._span("end start", "start", "end", "new")
    with pytest.raises(module.CanonicalQcCandidateError): call()


@pytest.mark.parametrize("edit", [
    lambda b: b.update(registered_look_id="foreign-look"),
    lambda b: b["sessions"][0].update(open_utc=b["sessions"][0]["open_utc"][:-1]),
    lambda b: b["sessions"][0].update(open_utc=b["sessions"][0]["open_utc"].replace("Z", ".000Z")),
    lambda b: b["signals"][0].update(available_at_utc="2023-01-16T14:29:00+00:00"),
    lambda b: b["signals"][0].update(decision_session="2023-01-13"),
    lambda b: b["signals"][0].update(exit_session="2023-02-14"),
    lambda b: b["signals"][0].update(issuer_id=True),
])
def test_reanchored_standalone_manifest_cannot_erase_clock_identity_guards(inputs, generated, edit):
    body = json.loads(inputs[1].batch_files(0)["signals.json"]); edit(body)
    body["calendar_sha256"] = sha(enc(body["sessions"])); raw = enc(body)
    with pytest.raises(generated.StockStudyRefusal): generated.parse_study_manifest(raw, sha(raw))


def test_real_early_close_is_supported_without_normalizing_timestamp_spelling(inputs, generated):
    body = json.loads(inputs[1].batch_files(0)["signals.json"])
    body["sessions"][0]["close_utc"] = "2021-11-29T18:00:00Z"
    body["calendar_sha256"] = sha(enc(body["sessions"])); raw = enc(body)
    assert generated.parse_study_manifest(raw, sha(raw)).closes[0].hour == 18


def test_mocked_every_calendar_preopen_afterclose_and_full_entry_exit_path(inputs, generated):
    algorithm = configured(generated, inputs[1]); manifest = algorithm._manifest
    for n, day in enumerate(manifest.sessions):
        for security in algorithm.securities.values():
            if n:
                security.last_data = types.SimpleNamespace(end_time=manifest.closes[n-1], close=100, is_fill_forward=False)
            security.price = 999  # Sizing must use previous-close bar, not this preopen quote.
        at(algorithm, manifest.opens[n] - timedelta(minutes=2)); algorithm._before_market_open()
        for oid, pending in tuple(algorithm._pending.items()):
            at(algorithm, manifest.opens[n]); quantity = pending.quantity
            algorithm.holdings[pending.symbol].quantity += quantity
            algorithm.portfolio.cash -= quantity * 100
            algorithm.on_order_event(types.SimpleNamespace(order_id=oid, symbol=pending.symbol, status="filled", fill_quantity=quantity, fill_price=100))
        for security in algorithm.securities.values():
            security.price = 100
            security.last_data = types.SimpleNamespace(end_time=manifest.closes[n], close=100, is_fill_forward=False)
        at(algorithm, manifest.closes[n] + timedelta(minutes=1)); algorithm._after_market_close()
    algorithm.on_end_of_algorithm()
    assert [row[1] for row in algorithm.orders] == [42, -42]
    assert algorithm._next_session_index == algorithm._preopen_session_index == len(manifest.sessions)
    assert "IBQC_CANONICAL_ORDER_PATH_COMPLETE" in algorithm.logs[-1]


@pytest.mark.parametrize("drift", ["timestamp", "close", "fillforward", "sid", "live", "latecallback"])
def test_preopen_previous_close_and_clock_guards_precede_first_order(inputs, generated, drift):
    algorithm = configured(generated, inputs[1]); m = algorithm._manifest; n = m.sessions.index(m.signals[0].entry_session)
    algorithm._next_session_index = algorithm._preopen_session_index = n
    symbol = algorithm._symbols[m.signals[0].ticker]; security = algorithm.securities[symbol]
    security.last_data = types.SimpleNamespace(end_time=m.closes[n-1], close=100, is_fill_forward=False)
    at(algorithm, m.opens[n]-timedelta(minutes=2))
    if drift == "timestamp": security.last_data.end_time += timedelta(minutes=1)
    elif drift == "close": security.last_data.close = 0
    elif drift == "fillforward": security.last_data.is_fill_forward = True
    elif drift == "sid": symbol.id = "foreign"
    elif drift == "live": algorithm.live_mode = True
    else: algorithm.utc_time += timedelta(seconds=1)
    with pytest.raises(generated.StockStudyRefusal): algorithm._before_market_open()
    assert algorithm.orders == []


def test_preopen_holding_drift_refuses_even_without_that_days_exit(inputs, generated):
    algorithm = configured(generated, inputs[1]); m = algorithm._manifest; row = m.signals[0]; n = m.sessions.index(row.entry_session)+1
    algorithm._next_session_index = algorithm._preopen_session_index = n
    symbol = algorithm._symbols[row.ticker]
    algorithm._active[row.qc_symbol_id] = (row, 42); algorithm.holdings[symbol].quantity = 41
    algorithm.securities[symbol].last_data = types.SimpleNamespace(end_time=m.closes[n-1], close=100, is_fill_forward=False)
    at(algorithm, m.opens[n]-timedelta(minutes=2))
    with pytest.raises(generated.StockStudyRefusal, match="held quantity drift"): algorithm._before_market_open()
    assert algorithm.orders == []


def test_partition_is_deterministic_complete_capacity_bound_and_same_sid_nonoverlap():
    dates = [f"day-{n}" for n in range(100)]
    rows = [{"signal_id": f"S{n:03d}", "qc_symbol_id": f"SID{n}", "entry_session": dates[1], "exit_session": dates[21]} for n in range(41)]
    rows += [{"signal_id": "later", "qc_symbol_id": "SID0", "entry_session": dates[21], "exit_session": dates[41]}]
    result = module._partition(rows, dates)
    assert list(map(len, result)) == [20, 20, 2] and module._partition(copy.deepcopy(rows), dates) == result
    assert [row["signal_id"] for batch in result for row in batch] == [row["signal_id"] for row in rows]
    assert result[0][0]["signal_id"] == "S000" and result[2][-1]["signal_id"] == "later"


def native_inputs(plan, index=0):
    """Explicit invented capture service; never retrieved or actually executed."""
    files = plan.batch_files(index); manifest = json.loads(files["signals.json"]); clock = {r["session"]: r for r in manifest["sessions"]}
    backtest_id = "invented-backtest" + ("-" + str(index) if index else "")
    orders, events = [], []
    for signal_index, row in enumerate(manifest["signals"]):
        for side in ("entry", "exit"):
            oid = 2*signal_index+(1 if side == "entry" else 2); quantity = 10 if side == "entry" else -10
            opening = analysis._utc(clock[row[side+"_session"]]["open_utc"]); submitted = opening-timedelta(minutes=2)
            lifecycle = []
            for eid, (status, instant, filled, price) in enumerate((("submitted", submitted, 0, 0), ("filled", opening, quantity, 100)), 1):
                lifecycle.append({"algorithmId": backtest_id, "symbol": row["qc_symbol_id"], "symbolValue": row["ticker"],
                    "symbolPermtick": row["ticker"], "orderId": oid, "orderEventId": eid, "id": f"order-{oid}-event-{eid}", "status": status,
                    "orderFeeAmount": 1 if filled else 0, "orderFeeCurrency": "USD", "fillPrice": price, "fillPriceCurrency": "USD",
                    "fillQuantity": filled, "direction": "buy" if side == "entry" else "sell", "message": "", "isAssignment": False,
                    "stopPrice": 0, "limitPrice": 0, "quantity": quantity, "time": int(instant.timestamp()), "isInTheMoney": False})
            events += lifecycle
            orders.append({"id": oid, "symbol": {"id": row["qc_symbol_id"], "value": row["ticker"], "permtick": row["ticker"]},
                "time": submitted.strftime("%Y-%m-%dT%H:%M:%SZ"), "createdTime": submitted.strftime("%Y-%m-%dT%H:%M:%SZ"), "lastFillTime": opening.strftime("%Y-%m-%dT%H:%M:%SZ"), "quantity": quantity,
                "type": 4, "securityType": 1, "status": 3, "tag": f'IB5:{manifest["registered_look_id"]}:{row["signal_id"]}:{side.upper()}',
                "direction": 0 if side == "entry" else 1, "events": lifecycle})
    markers = [f'IBQC_CANONICAL_INPUT|look={manifest["registered_look_id"]}|manifest={sha(files["signals.json"])}|gate={sha(files["gate.json"])}|signals={len(manifest["signals"])}|canonical=false',
        f'IBQC_CANONICAL_ORDER_PATH_COMPLETE|look={manifest["registered_look_id"]}|manifest={sha(files["signals.json"])}|entries={len(manifest["signals"])}|exits={len(manifest["signals"])}|canonical=false']
    call = dict(plan=plan, batch_index=index, native_backtest=enc({"success": True, "errors": [], "backtest": {
        "projectId": 7, "backtestId": backtest_id, "completed": True, "status": "Completed.", "error": "", "stacktrace": "",
        "hasInitializeError": False, "statistics": {"Total Orders": str(len(orders))}, "runtimeStatistics": {"Holdings": "$0.00"},
        "serverStatistics": {"LEAN Version": "invented-lean-revision"}}}), order_pages=(enc({"orders": orders, "length": len(orders)}),),
        native_order_events=enc(events), project_files=enc({"success": True, "errors": [], "files": [{"projectId": 7, "name": "main.py", "content": files["main.py"].decode(), "isLibrary": False}]}),
        cloud_signal_manifest=files["signals.json"], cloud_gate=files["gate.json"], logs_pages=(enc({"success": True, "errors": [], "logs": markers, "length": 2}),))
    capture = {"schema": "insider-qc-canonical-capture-v2", "profile": module.NATIVE_PROFILE, "trust_scope": "fixture", "origin": "invented-native-QC-export",
        "plan_sha256": plan.sha256, "batch_id": plan._batch_id(index), "project_id": 7, "compile_id": "invented-compile", "backtest_id": backtest_id,
        "attempt_id": "attempt-1", "compiled_source_sha256": sha(files["main.py"]), "project_files_sha256": sha(call["project_files"]),
        "signal_manifest_sha256": sha(files["signals.json"]), "gate_sha256": sha(files["gate.json"]), "native_backtest_sha256": sha(call["native_backtest"]),
        "native_order_events_sha256": sha(call["native_order_events"]), "order_pages": [{"start": 0, "end": 99, "sha256": sha(call["order_pages"][0])}],
        "logs_pages": [{"start": 0, "end": 200, "sha256": sha(call["logs_pages"][0])}]}
    return anchor(call, capture)


def anchor(call, capture):
    call["capture_manifest"] = enc(capture); call["trust_roots"] = native.QcExportTrustRoots("fixture", sha(call["capture_manifest"]))
    return call


def edit_native(call, role, edit):
    call = dict(call); capture = json.loads(call["capture_manifest"])
    pages = role in {"order_pages", "logs_pages"}
    body = json.loads(call[role][0] if pages else call[role]); edit(body)
    call[role] = (enc(body),) if pages else enc(body)
    if pages: capture[role][0]["sha256"] = sha(call[role][0])
    else: capture[role+"_sha256"] = sha(call[role])
    return anchor(call, capture)


def test_causal_manifest_generated_child_native_export_aggregate_retains_actual_registered_instants(inputs):
    plan = inputs[1]; result = module.adapt_canonical_qc_export(**native_inputs(plan))
    raw = plan.verify_native_completion_set((result,)); terminal = json.loads(raw)
    assert terminal["manifest_sha256"] == sha(causal.build_source_event_study_manifest(**inputs[0]).manifest_bytes())
    assert terminal["fills"][0]["filled_at_utc"] == "2023-01-16T14:30:00Z"
    assert terminal["fills"][0]["security_id"] == "SID00" and terminal["fills"][0]["quantity"] == 10
    assert terminal["fills"][0]["price"] == "100" and terminal["fills"][0]["order_id"] == "batch-1:1"
    assert result.to_payload()["auction_price_parity_verified"] is result.to_payload()["dispatch_enabled"] is False


@pytest.mark.parametrize("role,edit", [
    ("order_pages", lambda b: b["orders"][0].update(time="2023-01-13T21:01:00+00:00")),
    ("order_pages", lambda b: b["orders"][0].update(type=True)),
    ("order_pages", lambda b: b["orders"][0]["symbol"].update(id="foreign")),
    ("order_pages", lambda b: b["orders"][0].update(quantity=9)),
    ("order_pages", lambda b: b["orders"].pop()),
    ("native_order_events", lambda b: b[0].update(orderId=True)),
    ("native_order_events", lambda b: b.pop()),
    ("project_files", lambda b: b["files"][0].update(content=b["files"][0]["content"].replace("RESEARCH_BACKTEST_ENABLED = False", "RESEARCH_BACKTEST_ENABLED = True"))),
    ("logs_pages", lambda b: b["logs"].reverse()),
    ("logs_pages", lambda b: b["logs"].__setitem__(1, "Completed")),
    ("native_backtest", lambda b: b["backtest"].update(completed=1)),
    ("native_backtest", lambda b: b["backtest"]["statistics"].update({"Total Orders": "1"})),
    ("native_backtest", lambda b: b["backtest"]["runtimeStatistics"].update(Holdings="$10")),
])
def test_reanchored_native_v2_exports_do_not_override_substantive_controls(inputs, role, edit):
    with pytest.raises(module.CanonicalQcCandidateError): module.adapt_canonical_qc_export(**edit_native(native_inputs(inputs[1]), role, edit))


def test_opening_minute_callback_preserved_but_not_fabricated_into_exact_open_analysis(inputs):
    call = native_inputs(inputs[1]); orders = json.loads(call["order_pages"][0]); events = []
    for order in orders["orders"]:
        order["events"][-1]["time"] += 60
        order["lastFillTime"] = (native._utc(order["lastFillTime"])+timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events += order["events"]
    capture = json.loads(call["capture_manifest"]); call["order_pages"] = (enc(orders),); call["native_order_events"] = enc(events)
    capture["order_pages"][0]["sha256"] = sha(call["order_pages"][0]); capture["native_order_events_sha256"] = sha(call["native_order_events"])
    result = module.adapt_canonical_qc_export(**anchor(call, capture))
    assert result.native_fills()[0]["filled_at_utc"] == "2023-01-16T14:31:00Z"
    with pytest.raises(module.CanonicalQcCandidateError, match="exact native"): inputs[1].verify_native_completion_set((result,))


def test_fractional_native_callback_instant_is_preserved_and_strict_analysis_refuses(inputs):
    call = native_inputs(inputs[1]); orders = json.loads(call["order_pages"][0]); events = []
    for order in orders["orders"]:
        order["events"][-1]["time"] += 0.5
        order["lastFillTime"] = (native._utc(order["lastFillTime"])+timedelta(microseconds=500000)).isoformat().replace("+00:00", "Z")
        events += order["events"]
    capture = json.loads(call["capture_manifest"]); call["order_pages"] = (enc(orders),); call["native_order_events"] = enc(events)
    capture["order_pages"][0]["sha256"] = sha(call["order_pages"][0]); capture["native_order_events_sha256"] = sha(call["native_order_events"])
    result = module.adapt_canonical_qc_export(**anchor(call, capture))
    assert result.native_fills()[0]["filled_at_utc"] == "2023-01-16T14:30:00.500000Z"
    with pytest.raises(module.CanonicalQcCandidateError, match="exact native"):
        inputs[1].verify_native_completion_set((result,))


@pytest.mark.parametrize("edit", [lambda b: b["fills"][0].update(quantity=True), lambda b: b["fills"][1].update(quantity=-9),
    lambda b: b["fills"].pop(), lambda b: b.update(processed_sessions=[]), lambda b: b.update(candidate_source_sha256="a"*64),
    lambda b: b.update(errors=["failure"]), lambda b: b.update(final_positions=[{"quantity": 1}]), lambda b: b.update(registered_look_id="other")])
def test_reanchored_child_terminal_cannot_skip_full_set_or_source_fill_calendar_checks(inputs, edit):
    result = module.adapt_canonical_qc_export(**native_inputs(inputs[1])); body = json.loads(result.terminal_bytes()); edit(body); raw = enc(body)
    with pytest.raises(module.CanonicalQcCandidateError): inputs[1].verify_completion_set(terminals=(raw,), expected_terminal_sha256s=(sha(raw),))


def test_low_decimal_precision_does_not_round_above_budget_native_price_down(inputs):
    result = module.adapt_canonical_qc_export(**native_inputs(inputs[1])); body = json.loads(result.terminal_bytes())
    body["fills"][0].update(quantity=1, price="4500.000001"); body["fills"][1]["quantity"] = -1; raw = enc(body)
    with localcontext() as context:
        context.prec = 3
        with pytest.raises(module.CanonicalQcCandidateError, match="slot budget"):
            inputs[1].verify_completion_set(terminals=(raw,), expected_terminal_sha256s=(sha(raw),))


def test_all_native_children_factory_identity_required_and_returned_fills_detached(inputs):
    result = module.adapt_canonical_qc_export(**native_inputs(inputs[1]))
    result.native_fills().clear(); assert len(result.native_fills()) == 2
    with pytest.raises(module.CanonicalQcCandidateError): inputs[1].verify_native_completion_set(())
    with pytest.raises(module.CanonicalQcCandidateError): inputs[1].verify_native_completion_set((replace(result),))


@pytest.mark.parametrize("factory", ["plan", "export"])
def test_equal_mutable_byte_facades_cannot_impersonate_registered_factory_bytes(inputs, factory):
    result = build(inputs[0]) if factory == "plan" else module.adapt_canonical_qc_export(**native_inputs(inputs[1]))
    original = result._bytes
    try:
        object.__setattr__(result, "_bytes", bytearray(original))
        with pytest.raises(module.CanonicalQcCandidateError): result.to_payload()
    finally:
        object.__setattr__(result, "_bytes", original)


def many_events(count=41):
    kwargs = make_causal_fixture(specs=tuple(("4", "2023-01-15", str(123456+n), f"{123456+n:010d}-23-000001", "20230115101112") for n in range(count)),
        raw_changes={n: (lambda raw, number=n: raw.replace(b"<issuerTradingSymbol>T00</issuerTradingSymbol>", f"<issuerTradingSymbol>T{number:02d}</issuerTradingSymbol>".encode())) for n in range(count)})
    master = json.loads(kwargs["security_master"]); template = copy.deepcopy(master["mappings"][0]); master["mappings"] = []
    for n in range(count):
        row = {**template, "issuer_cik": f"{123456+n:010d}", "qc_symbol_id": f"SID{n:02d}", "ticker": f"T{n:02d}"}
        master["mappings"].append(row)
    from data.hashing import canonical_json
    kwargs["security_master"] = canonical_json(master).encode()
    ref = json.loads(kwargs["entry_reference"]); ref["security_master_sha256"] = sha(kwargs["security_master"])
    ref["eligible_control_security_ids"] = [r["qc_symbol_id"] for r in master["mappings"]]
    for entry in ref["entries"]:
        context, earnings = entry["stock_context"], entry["earnings_rows"]
        context["rows"] = [{**copy.deepcopy(context["rows"][0]), "qc_symbol_id": row["qc_symbol_id"]} for row in master["mappings"]]
        entry["stock_context_sha256"] = sha(enc(context))
        entry["earnings_rows"] = [{**copy.deepcopy(earnings[0]), "qc_symbol_id": row["qc_symbol_id"]} for row in master["mappings"]]
    kwargs["entry_reference"] = enc(ref)
    reg = json.loads(kwargs["registration"]); reg["security_master_sha256"] = sha(kwargs["security_master"]); kwargs["registration"] = enc(reg)
    return _reanchor(kwargs)


def test_genuine_41_event_population_three_children_all_native_completed_before_parent_analysis():
    plan = build(many_events()); payload = plan.to_payload()
    assert payload["event_count"] == 41 and payload["batch_count"] == 3
    assert [len(json.loads(plan.batch_manifest_bytes(i))["signals"]) for i in range(3)] == [20, 20, 1]
    results = tuple(module.adapt_canonical_qc_export(**native_inputs(plan, index)) for index in range(3))
    raw = plan.verify_native_completion_set(results); terminal = json.loads(raw)
    assert len(terminal["fills"]) == 82 and len({r["signal_id"] for r in terminal["fills"]}) == 41
    with pytest.raises(module.CanonicalQcCandidateError): plan.verify_native_completion_set(results[:-1])
    with pytest.raises(module.CanonicalQcCandidateError): plan.verify_native_completion_set(tuple(reversed(results)))
    assert all(r.native_cash_path()["capital_pooling_inferred"] is False for r in results)


def edit_lifecycle(call, edit):
    call = dict(call); capture = json.loads(call["capture_manifest"]); orders = json.loads(call["order_pages"][0]); edit(orders["orders"])
    call["order_pages"] = (enc(orders),); call["native_order_events"] = enc([e for o in orders["orders"] for e in o["events"]])
    capture["order_pages"][0]["sha256"] = sha(call["order_pages"][0]); capture["native_order_events_sha256"] = sha(call["native_order_events"])
    return anchor(call, capture)


@pytest.mark.parametrize("edit", [
    lambda orders: orders[0]["events"][-1].update(orderFeeAmount=90000),
    lambda orders: orders[0]["events"][-1].update(fillPrice=450.0000001),
    lambda orders: orders[0]["events"][0].update(orderFeeAmount=1),
    lambda orders: orders[0]["events"][-1].update(orderFeeAmount=-1),
])
def test_native_actual_full_money_and_fee_path_cannot_breach_fixed_capital(inputs, edit):
    call = edit_lifecycle(native_inputs(inputs[1]), edit)
    with localcontext() as context:
        context.prec = 3
        with pytest.raises(module.CanonicalQcCandidateError): module.adapt_canonical_qc_export(**call)


def test_extremely_small_native_fees_cannot_disappear_at_exact_twenty_slot_cash_reserve():
    plan = build(many_events(20)); call = native_inputs(plan); orders = json.loads(call["order_pages"][0])
    for order in orders["orders"]:
        order["quantity"] = 45 if order["quantity"] > 0 else -45
        for event in order["events"]:
            event["quantity"] = order["quantity"]
            if event["status"] == "filled":
                event["fillQuantity"] = order["quantity"]; event["orderFeeAmount"] = "tiny-fee-placeholder"
    capture = json.loads(call["capture_manifest"])
    call["order_pages"] = (enc(orders).replace(b'"tiny-fee-placeholder"', b'1e-100'),)
    call["native_order_events"] = enc([e for o in orders["orders"] for e in o["events"]]).replace(b'"tiny-fee-placeholder"', b'1e-100')
    capture["order_pages"][0]["sha256"] = sha(call["order_pages"][0]); capture["native_order_events_sha256"] = sha(call["native_order_events"])
    with pytest.raises(module.CanonicalQcCandidateError): module.adapt_canonical_qc_export(**anchor(call, capture))


def test_largest_supported_native_fee_scale_is_retained_exactly_under_low_context(inputs):
    call = native_inputs(inputs[1]); orders = json.loads(call["order_pages"][0]); events = []
    for order in orders["orders"]:
        order["events"][-1]["orderFeeAmount"] = "exact-fee-placeholder"; events += order["events"]
    capture = json.loads(call["capture_manifest"])
    call["order_pages"] = (enc(orders).replace(b'"exact-fee-placeholder"', b'1e-28'),)
    call["native_order_events"] = enc(events).replace(b'"exact-fee-placeholder"', b'1e-28')
    capture["order_pages"][0]["sha256"] = sha(call["order_pages"][0]); capture["native_order_events_sha256"] = sha(call["native_order_events"])
    with localcontext() as context:
        context.prec = 3
        result = module.adapt_canonical_qc_export(**anchor(call, capture))
    cash = result.native_cash_path()
    assert Decimal(cash["ending_cash_usd"]) == Decimal("99999.9999999999999999999999999998")
    assert Decimal(cash["minimum_cash_usd"]) == Decimal("98999.9999999999999999999999999999")
    assert cash["observed_fill_fees_usd"] == ["1E-28", "1E-28"]
    assert result.to_payload()["native_money_profile"] == module.NATIVE_MONEY_PROFILE


@pytest.mark.parametrize("number", [Decimal("1e-29"), Decimal("1e100"), Decimal("1000000000001"), True, "1"])
def test_explicit_native_money_profile_rejects_unsupported_precision_magnitude_or_types(number):
    with pytest.raises((module.CanonicalQcCandidateError, native.QcExportAdapterError)): module._money(number)


def failure(plan, attempt, *, status="CompileError"):
    return enc({"schema": "insider-canonical-qc-attempt-failure-v1", "trust_scope": "fixture", "parent_study_id": "fixture-parent",
        "batch_id": plan._batch_id(0), "batch_plan_sha256": plan.to_payload()["plan_sha256"], "registered_look_id": plan.to_payload()["registered_look_id"],
        "candidate_source_sha256": sha(plan.batch_files(0)["main.py"]), "attempt_id": attempt, "project_id": "7", "compile_id": "invented-compile",
        "backtest_id": None if status == "CompileError" else "invented-backtest", "status": status, "errors": ["invented diagnostic"]})


def test_child_reuses_existing_three_attempt_accounting_compile_failure_needs_no_backtest(inputs):
    from research.insider_buying import backtest_study_package as study
    plan = inputs[1]; raw = plan.new_child_attempt_ledger(0)
    for n in range(3):
        attempt = "attempt-"+str(n+1)
        raw = plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id=attempt)
        with pytest.raises(module.CanonicalQcCandidateError): plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="extra")
        diagnostic = failure(plan, attempt)
        raw = plan.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), failure_raw=diagnostic, expected_failure_sha256=sha(diagnostic))
    status = study.attempt_ledger_status(raw)
    assert status["attempt_count"] == status["unsuccessful_count"] == 3 and status["requires_mia"] is True
    with pytest.raises(module.CanonicalQcCandidateError): plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="fourth")


def test_sealed_native_completion_closes_exact_pending_child_attempt(inputs):
    from research.insider_buying import backtest_study_package as study
    plan = inputs[1]; raw = plan.new_child_attempt_ledger(0)
    raw = plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="attempt-1")
    result = module.adapt_canonical_qc_export(**native_inputs(plan))
    raw = plan.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), native_result=result)
    assert study.attempt_ledger_status(raw)["candidate_completed"] is True
    with pytest.raises(module.CanonicalQcCandidateError): plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="second")


@pytest.mark.parametrize("edit", [lambda b: b.update(backtest_id="invented"), lambda b: b.update(candidate_source_sha256="a"*64),
    lambda b: b.update(attempt_id="other"), lambda b: b.update(status="Completed"), lambda b: b.update(errors=[]), lambda b: b.update(trust_scope="production")])
def test_externally_rehashed_compile_diagnostic_cannot_promote_or_finish_other_child(inputs, edit):
    plan = inputs[1]; raw = plan.new_child_attempt_ledger(0)
    raw = plan.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="attempt-1")
    body = json.loads(failure(plan, "attempt-1")); edit(body); diagnostic = enc(body)
    with pytest.raises(module.CanonicalQcCandidateError): plan.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), failure_raw=diagnostic, expected_failure_sha256=sha(diagnostic))
