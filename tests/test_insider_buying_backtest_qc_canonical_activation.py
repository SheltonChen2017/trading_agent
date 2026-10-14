"""Invented external application records only; never actual activation facts."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json

import pytest

from research.insider_buying import backtest_qc_canonical_activation as module
from research.insider_buying import backtest_qc_canonical_candidate as canonical
from research.insider_buying import backtest_qc_export_adapter as native
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_study_package as study
from research.insider_buying.backtest_source_stream import build_stream_source_evidence
from test_insider_buying_backtest_event_study_manifest import make_v3_causal_fixture
from test_insider_buying_backtest_source_stream import make_stream_fixture
from test_insider_buying_backtest_realized_earnings_diagnostic import causal_v2
from test_insider_buying_backtest_qc_canonical_candidate import LEGACY, native_inputs
from test_insider_buying_provider_rights_evidence import records, admit, project, NOW


def enc(value): return analysis.canonical_bytes(value)
def sha(raw): return hashlib.sha256(raw).hexdigest()


def production_shape(value):
    """Test-only external trust service; no product/authentication assertion."""
    if type(value) is dict:
        return {key: "production" if key == "trust_scope" else production_shape(item) for key, item in value.items()}
    if type(value) is list: return [production_shape(item) for item in value]
    return value


@pytest.fixture(scope="module")
def inputs():
    stream, _ = make_stream_fixture()
    population = json.loads(stream["population_manifest"])
    population.update(trust_scope="production", origin="sec-original-complete-submission")
    stream.update(population_manifest=enc(population), population_sha256=sha(enc(population)), trust_scope="production")
    evidence = build_stream_source_evidence(**stream)
    kwargs = causal_v2(make_v3_causal_fixture())
    for role in ("security_master", "calendar", "common_equity_exceptions", "entry_reference", "registration"):
        kwargs[role] = enc(production_shape(json.loads(kwargs[role])))
    reference = json.loads(kwargs["entry_reference"])
    reference.update(calendar_sha256=sha(kwargs["calendar"]), security_master_sha256=sha(kwargs["security_master"]))
    for entry in reference["entries"]:
        context = entry["stock_context"]; context["calendar_sha256"] = sha(kwargs["calendar"])
        for row in context["rows"]:
            # Deliberately invented external production-shaped declaration,
            # not an observed official exchange record or authenticated source.
            row["first_listing_evidence"]["source_authority"] = "official-exchange-first-listing-record"
            row["first_listing_evidence_sha256"] = sha(enc(row["first_listing_evidence"]))
        entry["stock_context_sha256"] = sha(enc(context))
    kwargs["entry_reference"] = enc(reference)
    state = records(); state = production_shape(state)
    state["subject"].update(source_manifest_sha256=stream["population_sha256"],
        first_session="2021-01-01", last_session="2024-12-31")
    right = admit(state); mapping = project(right, state)
    registration = json.loads(kwargs["registration"])
    registration.update(source_manifest_sha256=stream["population_sha256"], security_master_sha256=sha(kwargs["security_master"]),
        calendar_sha256=sha(enc(json.loads(kwargs["calendar"])["sessions"])), rights_sha256=mapping["rights_artifact_sha256"],
        registered_at_utc="2026-10-05T12:00:00Z", first_outcome_access_utc="2026-10-07T12:00:00Z")
    kwargs["registration"] = enc(registration); kwargs["source_evidence"] = evidence
    kwargs["trust_roots"] = causal.EventStudyManifestTrustRoots("production", stream["population_sha256"],
        *(sha(kwargs[name]) for name in ("security_master", "calendar", "common_equity_exceptions", "entry_reference", "registration")), "a" * 64)
    source = causal.build_source_event_study_manifest_v2(**kwargs)
    plan = canonical.build_canonical_qc_batch_plan_v2(source_events=source, legacy_source=LEGACY.read_bytes(),
        security_master=kwargs["security_master"], entry_reference=kwargs["entry_reference"],
        registration=kwargs["registration"], parent_study_id="invented-external-parent")
    body = plan._body(); subject = right.to_payload()["subject"]
    entitlement = {"schema": "insider-canonical-qc-account-entitlement-v1", "trust_scope": "production",
        "origin": "externally-anchored-account-product-evidence", "organization_id": "invented-org", "processing_scope": study.SCOPE,
        "observed_at_utc": "2026-10-06T11:00:00Z", "rights_evidence_sha256": right.sha256,
        **{key: subject[key] for key in ("account_pseudonym", "product_id", "dataset_id", "vintage_id", "outcome_vintage_sha256",
           "market_data_profile", "clock_data_entitlements", "first_session", "last_session")}}
    permanent = {"schema": "insider-canonical-qc-permanent-registration-v1", "trust_scope": "production",
        "origin": "externally-registered-permanent-stock-study", "parent_gate_sha256": study.PARENT_GATE_SHA256,
        "parent_study_id": body["parent_study_id"], "candidate_id": body["candidate_id"], "registered_look_id": body["registered_look_id"],
        "plan_sha256": plan.sha256, "source_event_study_sha256": body["source_event_study_sha256"],
        "source_event_manifest_sha256": body["source_event_manifest_sha256"], "analysis_registration_sha256": body["registration_sha256"],
        **body["manifest_roots"], "rights_evidence_sha256": right.sha256, "account_entitlement_sha256": sha(enc(entitlement)),
        "maximum_attempts_per_candidate": 3, "all_batches_required": True, "children": module._children(plan),
        "registered_at_utc": NOW, "first_outcome_access_utc": registration["first_outcome_access_utc"]}
    return dict(plan=plan, rights_evidence=right, account_entitlement_raw=enc(entitlement), registration_raw=enc(permanent),
        analysis_registration_raw=kwargs["registration"], trust_roots=module.CanonicalActivationTrustRoots(right.sha256, sha(enc(entitlement)), sha(enc(permanent))))


def configure(inputs): return module.configure_canonical_qc_plan(**inputs)


def edited(inputs, role, edit):
    result = dict(inputs); body = json.loads(result[role]); edit(body); result[role] = enc(body)
    field = "account_entitlement_sha256" if role == "account_entitlement_raw" else "registration_sha256"
    result["trust_roots"] = replace(result["trust_roots"], **{field: sha(result[role])})
    return result


def supplied(configured):
    call = native_inputs(configured)
    capture = json.loads(call["capture_manifest"])
    capture.pop("plan_sha256")
    capture.update(schema=module.CAPTURE_SCHEMA, profile=module.PROFILE, trust_scope="production",
        origin="externally-rooted-supplied-native-QC-export", configured_plan_sha256=configured.sha256)
    operation = {"schema": "insider-canonical-qc-external-operation-v1", "origin": "externally-rooted-supplied-operation-record",
        "configured_plan_sha256": configured.sha256, "permanent_registration_sha256": configured.to_payload()["roots"]["registration_sha256"],
        **{key: capture[key] for key in ("project_id", "compile_id", "backtest_id", "attempt_id", "compiled_source_sha256")},
        "launch_started_at_utc": "2026-10-07T12:00:00Z", "capture_completed_at_utc": "2026-10-07T12:01:00Z"}
    call["operational_receipt_raw"] = enc(operation)
    capture["operational_receipt_sha256"] = sha(call["operational_receipt_raw"])
    call["capture_manifest"] = enc(capture)
    call["trust_roots"] = native.QcExportTrustRoots("production", sha(call["capture_manifest"]))
    return call


def native_edit(call, role, edit):
    result = dict(call); capture = json.loads(result["capture_manifest"])
    pages = role in {"order_pages", "logs_pages"}
    body = json.loads(result[role][0] if pages else result[role]); edit(body)
    result[role] = (enc(body),) if pages else enc(body)
    if pages: capture[role][0]["sha256"] = sha(result[role][0])
    else: capture[role + "_sha256"] = sha(result[role])
    result["capture_manifest"] = enc(capture)
    result["trust_roots"] = native.QcExportTrustRoots("production", sha(result["capture_manifest"]))
    return result


def test_exact_genuine_factories_configure_only_one_source_switch_not_real_facts(inputs):
    configured = configure(inputs)
    original = inputs["plan"].batch_files(0); files = configured.batch_files(0)
    assert files["main.py"] == original["main.py"].replace(b"RESEARCH_BACKTEST_ENABLED = False\n", b"RESEARCH_BACKTEST_ENABLED = True\n", 1)
    assert files["signals.json"] == original["signals.json"] and files["gate.json"] == original["gate.json"]
    assert configured.to_payload()["children"][0]["files"] == {name: sha(raw) for name, raw in files.items()}
    assert configured.to_payload()["dispatch_enabled"] is configured.to_payload()["authentication_performed_here"] is False
    assert configured.to_payload()["qc_jobs"] == configured.to_payload()["research_looks"] == 0
    assert inputs["plan"].to_payload()["candidate_enabled"] is False


@pytest.mark.parametrize("edit", [lambda b: b.update(children=[]), lambda b: b["children"][0]["files"].update(**{"main.py": "b"*64}),
    lambda b: b.update(maximum_attempts_per_candidate=True), lambda b: b.update(all_batches_required=1),
    lambda b: b.update(first_outcome_access_utc="2027-01-01T00:00:00Z"), lambda b: b.update(registered_at_utc="2026-10-07T12:00:00Z"),
    lambda b: b.update(registered_look_id="unregistered"), lambda b: b.update(trust_scope="fixture"), lambda b: b.update(extra=True)])
def test_reanchored_permanent_registration_cannot_promote_or_drop(inputs, edit):
    with pytest.raises(ValueError): configure(edited(inputs, "registration_raw", edit))


@pytest.mark.parametrize("edit", [lambda b: b.update(account_pseudonym="foreign"), lambda b: b.update(last_session="2022-01-01"),
    lambda b: b["market_data_profile"].update(stock_fill_forward=0), lambda b: b.update(rights_evidence_sha256="a"*64),
    lambda b: b.update(origin="counts-only-probe"), lambda b: b.update(observed_at_utc="2026-10-07T00:00:00Z")])
def test_reanchored_account_receipt_does_not_replace_subject_or_coverage(inputs, edit):
    with pytest.raises(ValueError): configure(edited(inputs, "account_entitlement_raw", edit))


@pytest.mark.parametrize("role", ["plan", "rights_evidence", "analysis_registration_raw", "trust_roots"])
def test_fixture_or_unsealed_or_unanchored_sources_cannot_configure(inputs, role):
    call = dict(inputs)
    call[role] = inputs[role] + b" " if role == "analysis_registration_raw" else {}
    with pytest.raises(ValueError): configure(call)


def test_configured_and_native_payloads_cannot_reseal_or_mutate(inputs):
    configured = configure(inputs)
    with pytest.raises(ValueError): replace(configured).batch_files(0)
    object.__setattr__(configured, "_bytes", bytearray(configured._bytes))
    with pytest.raises(ValueError): configured.to_payload()
    configured = configure(inputs); result = module.adapt_configured_canonical_qc_export(**supplied(configured))
    with pytest.raises(ValueError): replace(result).to_payload()
    object.__setattr__(result, "_bytes", bytearray(result._bytes))
    with pytest.raises(ValueError): result.to_payload()


def test_supplied_full_native_child_to_production_terminal_does_not_open_analysis(inputs):
    configured = configure(inputs); result = module.adapt_configured_canonical_qc_export(**supplied(configured))
    terminal = configured.verify_native_completion_set((result,))
    assert json.loads(terminal)["trust_scope"] == "production" and len(json.loads(terminal)["fills"]) == 2
    assert result.to_payload()["authentication_performed_here"] is False
    assert result.to_payload()["engine_data_auction_cost_parity_verified"] is False
    assert result.to_payload()["statistical_gate"] == "UNADJUDICATED"
    with pytest.raises(ValueError): configured.verify_native_completion_set(())


@pytest.mark.parametrize("role,edit", [("native_backtest", lambda b: b["backtest"].update(completed=False)),
    ("native_backtest", lambda b: b["backtest"]["statistics"].update(**{"Total Orders": "3"})),
    ("project_files", lambda b: b["files"][0].update(content="foreign source")),
    ("order_pages", lambda b: b["orders"].pop()), ("native_order_events", lambda b: b.pop()),
    ("logs_pages", lambda b: b["logs"].pop()),
    ("order_pages", lambda b: b["orders"][0].update(tag="foreign")),
    ("order_pages", lambda b: b["orders"][0]["symbol"].update(id="foreign")),
    ("native_backtest", lambda b: b["backtest"]["runtimeStatistics"].update(Holdings="$1.00"))])
def test_reanchored_native_completed_is_not_sufficient(inputs, role, edit):
    configured = configure(inputs)
    with pytest.raises(ValueError): module.adapt_configured_canonical_qc_export(**native_edit(supplied(configured), role, edit))


def failure(configured, attempt, **changes):
    body = {"schema": "insider-configured-canonical-qc-failure-v1", "configured_plan_sha256": configured.sha256,
        "batch_index": 0, "attempt_id": attempt, "candidate_source_sha256": sha(configured.batch_files(0)["main.py"]),
        "project_id": 7, "compile_id": "invented-compile", "backtest_id": None, "status": "CompileError", "errors": ["invented"]}
    body.update(changes); return enc(body)


def test_three_failures_pending_ambiguity_and_compile_id_rules(inputs):
    configured = configure(inputs); raw = configured.new_child_attempt_ledger(0)
    for n in range(3):
        attempt = f"attempt-{n+1}"
        raw = configured.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id=attempt)
        with pytest.raises(ValueError): configured.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="extra")
        bad = failure(configured, attempt, backtest_id="invented")
        with pytest.raises(ValueError): configured.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), failure_raw=bad, expected_failure_sha256=sha(bad))
        diagnostic = failure(configured, attempt)
        raw = configured.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), failure_raw=diagnostic, expected_failure_sha256=sha(diagnostic))
    assert study.attempt_ledger_status(raw)["requires_mia"] is True
    with pytest.raises(ValueError): configured.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="fourth")


def test_native_exact_completion_finishes_only_bound_pending_attempt(inputs):
    configured = configure(inputs); raw = configured.new_child_attempt_ledger(0)
    raw = configured.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="attempt-1")
    result = module.adapt_configured_canonical_qc_export(**supplied(configured))
    raw = configured.finish_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), native_result=result)
    assert study.attempt_ledger_status(raw)["candidate_completed"] is True
    with pytest.raises(ValueError): configured.begin_child_attempt(index=0, ledger_raw=raw, expected_ledger_sha256=sha(raw), attempt_id="extra")


def test_fractional_native_callback_is_preserved_never_relabelled(inputs):
    configured = configure(inputs); call = supplied(configured)
    orders = json.loads(call["order_pages"][0]); events = json.loads(call["native_order_events"])
    for order in orders["orders"]:
        order["lastFillTime"] = order["lastFillTime"].replace("Z", ".500000Z")
        order["events"][-1]["time"] += .5
    for event in events:
        if event["status"] == "filled": event["time"] += .5
    call = native_edit(call, "order_pages", lambda b: b.update(orders))
    call = native_edit(call, "native_order_events", lambda b: b.__setitem__(slice(None), events))
    result = module.adapt_configured_canonical_qc_export(**call)
    assert all(".500000Z" in row["filled_at_utc"] for row in result.native_fills())
    assert result.to_payload()["exact_open_bridge_verified"] is False
    with pytest.raises(ValueError): configured.verify_native_completion_set((result,))


@pytest.mark.parametrize("edit", [lambda b: b.update(launch_started_at_utc="2026-10-06T11:00:00Z"),
    lambda b: b.update(capture_completed_at_utc="2026-10-07T11:00:00Z"), lambda b: b.update(permanent_registration_sha256="b"*64),
    lambda b: b.update(compile_id="foreign"), lambda b: b.update(project_id=True), lambda b: b.update(origin="historical-fill-clock")])
def test_external_operational_chronology_not_inferred_from_historical_fills(inputs, edit):
    call = supplied(configure(inputs)); operation = json.loads(call["operational_receipt_raw"]); edit(operation)
    call["operational_receipt_raw"] = enc(operation); capture = json.loads(call["capture_manifest"])
    capture["operational_receipt_sha256"] = sha(call["operational_receipt_raw"])
    call["capture_manifest"] = enc(capture); call["trust_roots"] = native.QcExportTrustRoots("production", sha(call["capture_manifest"]))
    with pytest.raises(ValueError): module.adapt_configured_canonical_qc_export(**call)


@pytest.mark.parametrize("edit", [lambda b: b.update(trust_scope="fixture"), lambda b: b.update(origin="authenticated-by-this-parser"),
    lambda b: b.update(configured_plan_sha256="b"*64), lambda b: b.update(batch_id="foreign"),
    lambda b: b.update(project_id=True), lambda b: b.update(compiled_source_sha256="a"*64),
    lambda b: b.update(signal_manifest_sha256="a"*64), lambda b: b.update(gate_sha256="a"*64),
    lambda b: b.update(extra=True), lambda b: b.update(profile=canonical.NATIVE_PROFILE)])
def test_external_capture_reanchor_cannot_replace_configured_source_or_provenance_profile(inputs, edit):
    call = supplied(configure(inputs)); capture = json.loads(call["capture_manifest"]); edit(capture)
    call["capture_manifest"] = enc(capture); call["trust_roots"] = native.QcExportTrustRoots("production", sha(call["capture_manifest"]))
    with pytest.raises(ValueError): module.adapt_configured_canonical_qc_export(**call)


def test_missing_contract_cannot_be_replaced_by_a_genuine_probe_only_factory(inputs):
    state = production_shape(records(contract=False))
    state["subject"].update(source_manifest_sha256=inputs["plan"]._body()["manifest_roots"]["source_manifest_sha256"],
        first_session="2021-01-01", last_session="2024-12-31")
    evidence = admit(state); call = dict(inputs, rights_evidence=evidence)
    call["trust_roots"] = replace(call["trust_roots"], rights_evidence_sha256=evidence.sha256)
    with pytest.raises(ValueError, match="contract-not-current"): configure(call)


def test_detached_outputs_and_exact_index_profiles(inputs):
    configured = configure(inputs); returned = configured.to_payload(); returned["children"].clear()
    assert len(configured.to_payload()["children"]) == 1
    for index in (True, -1, 1, None, "0"):
        with pytest.raises(ValueError): configured.batch_files(index)
    result = module.adapt_configured_canonical_qc_export(**supplied(configured))
    fills = result.native_fills(); fills.clear()
    assert len(result.native_fills()) == 2


def test_pure_import_surface_contains_no_io_provider_or_execution_entrypoint():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(module))
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.startswith(("urllib", "requests", "http", "socket", "os", "pathlib", "subprocess", "assistant", "execution")) for name in imports)


def test_per_event_full_quantities_cannot_cancel_across_repeated_sid_events(inputs):
    # Typed native parser-kernel control, NOT a sealed production-result proof.
    # Unchanged legacy completion already checks each pair; this successor
    # must do so before sealing its own native result/finishing an attempt.
    from types import SimpleNamespace
    configured = configure(inputs); files = configured.batch_files(0)
    manifest = json.loads(files["signals.json"]); second = deepcopy(manifest["signals"][0])
    dates = [row["session"] for row in manifest["sessions"]]
    index = dates.index(second["exit_session"]) + 1
    second.update(signal_id="second-event", entry_session=dates[index], exit_session=dates[index + 20])
    manifest["signals"].append(second); files["signals.json"] = enc(manifest)
    toy = SimpleNamespace(batch_files=lambda index: files, _batch_id=configured._batch_id, sha256=configured.sha256)
    call = native_inputs(toy); orders = json.loads(call["order_pages"][0])["orders"]
    for order, quantity in zip(orders, (10, -5, 5, -10), strict=True):
        order["quantity"] = quantity
        for event in order["events"]:
            event["quantity"] = quantity
            if event["status"] == "filled": event["fillQuantity"] = quantity
    events = [event for order in orders for event in order["events"]]
    clock = {row["session"]: (analysis._utc(row["open_utc"]), analysis._utc(row["close_utc"])) for row in manifest["sessions"]}
    fills, _ = canonical._canonical_order_fills(orders, events, json.loads(call["capture_manifest"]), manifest, clock)
    assert len(fills) == 4 and sum(row["quantity"] for row in fills) == 0
    with pytest.raises(ValueError, match="per-event"): module._paired_full_quantities(fills)


@pytest.mark.parametrize("expires", ["2026-10-06T12:01:00Z", "2026-10-07T12:01:00Z"])
def test_expired_contract_at_actual_operation_cannot_use_registration_current_rights(inputs, expires):
    state = production_shape(records())
    state["subject"] = inputs["rights_evidence"].to_payload()["subject"]
    state["index"]["expires_at_utc"] = expires
    evidence = admit(state)
    call = dict(inputs, rights_evidence=evidence)
    entitlement = json.loads(call["account_entitlement_raw"])
    entitlement["rights_evidence_sha256"] = evidence.sha256
    call["account_entitlement_raw"] = enc(entitlement)
    permanent = json.loads(call["registration_raw"])
    permanent.update(rights_evidence_sha256=evidence.sha256, account_entitlement_sha256=sha(call["account_entitlement_raw"]))
    call["registration_raw"] = enc(permanent)
    call["trust_roots"] = module.CanonicalActivationTrustRoots(evidence.sha256, sha(call["account_entitlement_raw"]), sha(call["registration_raw"]))
    configured = configure(call)
    with pytest.raises(ValueError, match="contract"): module.adapt_configured_canonical_qc_export(**supplied(configured))
