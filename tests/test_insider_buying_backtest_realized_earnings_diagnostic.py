"""Invented complete release records only; no real rows, data or QC calls."""
import copy
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext
import hashlib
import json
from pathlib import Path
import weakref

import pytest

from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying import backtest_event_study_collection as collection
from research.insider_buying import backtest_qc_canonical_candidate as canonical
from research.insider_buying import backtest_realized_earnings_diagnostic as module
from test_insider_buying_backtest_registered_analysis import (
    dynamic_fixture, encoded, evaluate, make_panel_for_manifest_terminal, stream_fixture,
)
from test_insider_buying_backtest_event_study_manifest import make_causal_fixture, _reanchor
from test_insider_buying_backtest_event_study_collection import make_children
from test_insider_buying_backtest_qc_canonical_candidate import LEGACY, native_inputs, build


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def enc(value):
    return analysis.canonical_bytes(value)


def register_v2(registration, *, analysis_sha="a" * 64, diagnostic_sha="9" * 64):
    registration = copy.deepcopy(registration)
    registration.update(schema="insider-stock-analysis-registration-v2", policy=analysis.frozen_analysis_policy_v2(),
        implementation_sha256=analysis_sha, realized_earnings_implementation_sha256=diagnostic_sha,
        analysis_plan=analysis.analysis_plan_descriptors_v2(implementation_sha256=analysis_sha,
            realized_earnings_implementation_sha256=diagnostic_sha))
    return registration


def causal_v2(kwargs, *, analysis_sha="a" * 64, diagnostic_sha="9" * 64):
    result = dict(kwargs)
    reference = json.loads(result["entry_reference"])
    reference["schema"] = "insider-event-entry-causal-reference-v2"
    for row in reference["entries"]:
        row.pop("earnings_rows")
    result["entry_reference"] = enc(reference)
    result["registration"] = enc(register_v2(json.loads(result["registration"]),
        analysis_sha=analysis_sha, diagnostic_sha=diagnostic_sha))
    result = _reanchor(result)
    result["trust_roots"] = replace(result["trust_roots"], analysis_implementation_sha256=analysis_sha)
    return result


def fixture_v2():
    values = dynamic_fixture()
    values["registration"] = register_v2(values["registration"])
    values["manifest"]["schema"] = "insider-stock-event-study-manifest-v3"
    for event in values["manifest"]["events"]:
        event.pop("earnings_distance_sessions")
    return values


def evaluate_v2(values=None):
    raw, roots = encoded(values or fixture_v2())
    return analysis.analyze_registered_stock_study_v2(registration_raw=raw["registration"],
        manifest_raw=raw["manifest"], terminal_raw=raw["terminal"], panel_raw=raw["panel"],
        trust_roots=roots, expected_implementation_sha256="a" * 64)


def actual_source(result, *, offset=None, release_time="12:00:00", unavailable=False):
    body = result._body()
    manifest, registration = body["manifest"], body["registration"]
    sessions = manifest["sessions"]
    rows = []
    for event in manifest["events"]:
        index = next(i for i, row in enumerate(sessions) if row["session"] == event["entry_session"])
        releases = []
        if offset is not None and not unavailable:
            released = sessions[index + offset]["session"] + "T" + release_time + "Z"
            releases.append({"release_id": "release-" + event["signal_id"], "release_type": "ACTUAL_PUBLIC_EARNINGS_RELEASE",
                "lineage": [{"version_id": "release-v1", "supersedes_version_id": None,
                    "recorded_at_utc": sessions[index + 10]["close_utc"], "actual_public_release_at_utc": released,
                    "status": "ACTIVE", "source_document_sha256": "1" * 64, "source_record_sha256": "2" * 64}]})
        rows.append({**{key: event[key] for key in ("signal_id", "issuer_id", "security_id", "source_event_sha256")},
            "coverage_start_utc": sessions[index - 6]["close_utc"], "coverage_end_utc": sessions[index + 5]["close_utc"],
            "coverage_disposition": "UNAVAILABLE" if unavailable else "COMPLETE",
            "unavailable_reason": "source-window-unavailable" if unavailable else None, "releases": releases})
    return {"schema": module.SOURCE_SCHEMA, "trust_scope": "fixture",
        "registration_sha256": body["report"]["artifact_sha256s"]["registration"],
        "manifest_sha256": body["report"]["artifact_sha256s"]["manifest"],
        "event_inventory_sha256": sha(enc(manifest["events"])), "calendar_sha256": registration["calendar_sha256"],
        "source_receipt_sha256": "3" * 64, "rights_sha256": "4" * 64,
        "source_as_of_utc": sessions[-1]["close_utc"],
        "release_session_policy": registration["policy"]["earnings_release_session"], "events": rows}


def assess(result, source, *, scope="fixture", roots_edit=None, digest="9" * 64):
    raw = enc(source)
    roots = module.RealizedEarningsDiagnosticTrustRoots(scope,
        source["registration_sha256"], source["manifest_sha256"], result.sha256,
        sha(raw), source["source_receipt_sha256"], source["rights_sha256"], digest)
    if roots_edit:
        roots = replace(roots, **roots_edit)
    return module.assess_realized_earnings_sensitivity(primary_result=result,
        actual_earnings_raw=raw, trust_roots=roots, expected_implementation_sha256=digest)


def test_primary_economics_unchanged_and_no_raw_outcome_export_or_readiness():
    original = evaluate(dynamic_fixture())
    result = evaluate_v2()
    report = result.to_payload()
    for key in ("primary_inference", "counts", "horizon_cost_diagnostics", "split_diagnostics", "matched_control_ids",
                "software_statistical_disposition", "software_valid_stock_null_closes_family"):
        assert report[key] == original[key]
    assert report["earnings_exclusion_diagnostics"]["disposition"] == "UNAVAILABLE"
    assert report["ib5_pass"] is report["backtesting_ready"] is False
    assert "event_results" not in report and "event_results" not in enc(report).decode()
    assert report["registered_looks_consumed"] == report["qc_jobs_launched"] == 0


def test_verified_old_overconstraint_remains_v1_only_and_new_clock_has_no_earnings():
    kwargs = make_causal_fixture()
    reference = json.loads(kwargs["entry_reference"])
    reference["entries"][0]["earnings_rows"][0]["knowledge_at_utc"] = "2023-01-16T14:29:00Z"
    old = _reanchor({**kwargs, "entry_reference": enc(reference)})
    # Real old-path refusal: an irrelevant earnings timestamp delays MOO.
    with pytest.raises(canonical.CanonicalQcCandidateError, match="prerequisite reference"):
        build(old)
    corrected = causal_v2(old)
    events = causal.build_source_event_study_manifest_v2(**corrected)
    assert "earnings_distance_sessions" not in events.events()[0]
    assert "earnings_distance_sessions_by_security_id" not in events.entry_reference_facts()[0]
    plan = canonical.build_canonical_qc_batch_plan_v2(source_events=events, legacy_source=LEGACY.read_bytes(),
        security_master=corrected["security_master"], entry_reference=corrected["entry_reference"],
        registration=corrected["registration"], parent_study_id="fixture-parent")
    original = build(kwargs)
    old_signal = json.loads(original.batch_manifest_bytes(0))["signals"][0]
    new_signal = json.loads(plan.batch_manifest_bytes(0))["signals"][0]
    for key in set(old_signal) - {"signal_id", "source_event_sha256"}:
        assert old_signal[key] == new_signal[key]
    assert plan.to_payload()["kind"] == canonical.VERSION_V2
    assert plan.to_payload()["candidate_enabled"] is plan.to_payload()["dispatch_enabled"] is False
    export = canonical.adapt_canonical_qc_export(**native_inputs(plan))
    terminal = json.loads(plan.verify_native_completion_set((export,)))
    original_terminal = json.loads(original.verify_native_completion_set((canonical.adapt_canonical_qc_export(**native_inputs(original)),)))
    for left, right in zip(terminal["fills"], original_terminal["fills"], strict=True):
        assert {key: left[key] for key in ("side", "quantity", "security_id", "session", "filled_at_utc", "price")} == {
            key: right[key] for key in ("side", "quantity", "security_id", "session", "filled_at_utc", "price")}


@pytest.mark.parametrize("entry", ["old-into-new", "new-into-old", "generic-override"])
def test_explicit_source_epochs_do_not_weaken_existing_api(entry):
    old = make_causal_fixture(); new = causal_v2(old)
    with pytest.raises(ValueError):
        if entry == "old-into-new": causal.build_source_event_study_manifest_v2(**old)
        elif entry == "new-into-old": causal.build_source_event_study_manifest(**new)
        else: causal.build_source_event_study_manifest(**old, v2=True)


@pytest.mark.parametrize("offset,excluded2,excluded5", [(-5, False, True), (-2, True, True), (0, True, True), (2, True, True), (3, False, True), (5, False, True)])
def test_inclusive_actual_release_windows(offset, excluded2, excluded5):
    result = evaluate_v2()
    diagnostic = assess(result, actual_source(result, offset=offset))
    assert diagnostic["disposition"] == "FIXTURE_COMPLETE"
    assert diagnostic["earnings_exclusion_diagnostics"]["2"]["retained"] == int(not excluded2)
    assert diagnostic["earnings_exclusion_diagnostics"]["5"]["retained"] == int(not excluded5)
    assert diagnostic["ib5_pass"] is diagnostic["backtesting_ready"] is diagnostic["look_authority"] is False
    assert diagnostic["raw_or_per_event_returns_exported"] is False
    assert result.to_payload()["earnings_exclusion_diagnostics"]["disposition"] == "UNAVAILABLE"


@pytest.mark.parametrize("time,retained", [("14:00:00", 0), ("16:00:00", 0), ("20:59:59", 0), ("21:00:00", 1), ("22:00:00", 1)])
def test_release_exact_close_boundary_is_next_reaction_session(time, retained):
    result = evaluate_v2()
    diagnostic = assess(result, actual_source(result, offset=2, release_time=time))
    assert diagnostic["earnings_exclusion_diagnostics"]["2"]["retained"] == retained


def test_explicit_unavailable_is_not_no_earnings_or_partial_acceptance():
    result = evaluate_v2()
    diagnostic = assess(result, actual_source(result, unavailable=True))
    assert diagnostic["disposition"] == "UNAVAILABLE" and diagnostic["coverage_complete"] is False
    assert diagnostic["earnings_exclusion_diagnostics"] is None and len(diagnostic["unavailable_events"]) == 1
    complete_empty = assess(result, actual_source(result))
    assert complete_empty["earnings_exclusion_diagnostics"]["2"]["retained"] == 1


@pytest.mark.parametrize("edit", [
    lambda b: b["events"].clear(), lambda b: b["events"].append(copy.deepcopy(b["events"][0])),
    lambda b: b["events"][0].update(signal_id="another"), lambda b: b["events"][0].update(issuer_id="another"),
    lambda b: b["events"][0].update(security_id="another"), lambda b: b["events"][0].update(source_event_sha256="f"*64),
    lambda b: b.update(event_inventory_sha256="f"*64), lambda b: b.update(calendar_sha256="f"*64),
    lambda b: b["events"][0].update(coverage_start_utc="2020-01-01T21:00:00Z"),
    lambda b: b["events"][0].update(coverage_disposition=True),
    lambda b: b["events"][0].update(unavailable_reason="no-proof"),
    lambda b: b["events"][0]["releases"][0].update(release_type="PROJECTED_RELEASE"),
    lambda b: b["events"][0]["releases"][0].update(release_type="EARNINGS_CALL"),
    lambda b: b["events"][0]["releases"][0]["lineage"].clear(),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(supersedes_version_id="missing"),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(source_document_sha256="invalid"),
    lambda b: b["events"][0]["releases"].append(copy.deepcopy(b["events"][0]["releases"][0])),
    lambda b: b.update(release_session_policy="date-only-guess"), lambda b: b.update(source_as_of_utc="2020-01-01T00:00:00Z"),
])
def test_reanchored_incomplete_or_changed_release_facts_refuse(edit):
    result = evaluate_v2(); source = actual_source(result, offset=2); edit(source)
    with pytest.raises(ValueError): assess(result, source)


@pytest.mark.parametrize("role", ["registration_sha256", "manifest_sha256", "primary_report_sha256", "actual_earnings_sha256", "source_receipt_sha256", "rights_sha256", "diagnostic_implementation_sha256"])
def test_external_root_drift_refuses(role):
    result = evaluate_v2()
    with pytest.raises(ValueError): assess(result, actual_source(result), roots_edit={role: "8"*64})


def test_sealed_primary_result_cannot_be_reconstructed_or_reanchored():
    result = evaluate_v2(); source = actual_source(result)
    with pytest.raises(ValueError): assess(replace(result), source)
    body = result._body(); body["event_results"][0]["matched_net10_20s"] = "10"
    object.__setattr__(result, "_raw", enc(body))
    with pytest.raises(ValueError): result.to_payload()


def test_production_diagnostic_refuses_before_source_bytes_are_decoded():
    result = evaluate_v2(); source = actual_source(result)
    roots = module.RealizedEarningsDiagnosticTrustRoots("production", source["registration_sha256"],
        source["manifest_sha256"], result.sha256, "1"*64, source["source_receipt_sha256"], source["rights_sha256"], "9"*64)
    with pytest.raises(module.RealizedEarningsDiagnosticError, match="zero-look"):
        module.assess_realized_earnings_sensitivity(primary_result=None, actual_earnings_raw=object(),
            trust_roots=roots, expected_implementation_sha256="9"*64)


def test_diagnostic_code_identity_is_fixed_in_preoutcome_registration():
    result = evaluate_v2()
    with pytest.raises(ValueError, match="executable identity"):
        assess(result, actual_source(result), digest="8"*64)


def test_new_registration_preserves_primary_policy_and_refuses_earnings_policy_drift():
    old, new = analysis.frozen_analysis_policy(), analysis.frozen_analysis_policy_v2()
    assert {k: v for k, v in new.items() if k in old and k != "version"} == {k: v for k, v in old.items() if k != "version"}
    values = fixture_v2(); values["registration"]["policy"]["earnings_used_for_primary_event_selection"] = True
    with pytest.raises(ValueError, match="policy drift"): evaluate_v2(values)


def test_homogeneous_successor_collection_no_mixed_epoch_or_causal_earnings():
    original, kwargs = make_children()
    records = tuple(collection.CausalStudyChildRecord(causal.build_source_event_study_manifest_v2(**causal_v2(item)),
        item["source_evidence"], causal_v2(item)["registration"]) for item in kwargs)
    descriptors = [collection.describe_causal_child_v2(record) for record in records]
    inventory = enc({"schema": collection.INVENTORY_SCHEMA_V2, "trust_scope": "fixture", "origin": "invented-sealed-causal-window-collection",
        "event_first_session": descriptors[0]["event_first_session"], "event_last_session": descriptors[-1]["event_last_session"], "children": descriptors})
    parent = json.loads(records[0].registration_raw)
    parent.update(source_manifest_sha256=sha(inventory), registered_at_utc="2021-12-01T00:00:00Z")
    parent_raw = enc(parent)
    inputs = dict(child_records=iter(records), collection_inventory=inventory, parent_registration=parent_raw,
        trust_roots=collection.EventStudyCollectionTrustRoots("fixture", sha(inventory), sha(parent_raw), "a"*64))
    result = collection.build_source_event_study_collection_v2(**inputs)
    assert result.to_payload()["kind"] == collection.VERSION_V2 and len(result.events()) == 4
    assert all("earnings_distance_sessions" not in row for row in result.events())
    with pytest.raises(ValueError): collection.build_source_event_study_collection(**{**inputs, "child_records": iter(records)})
    with pytest.raises(ValueError): collection.build_source_event_study_collection_v2(**{**inputs, "child_records": iter((original[0], records[1]))})


def test_new_causal_native_primary_and_actual_release_path_is_one_sealed_fixture_epoch():
    root = Path(__file__).resolve().parents[1]
    analysis_sha = sha((root / "research/insider_buying/backtest_registered_analysis.py").read_bytes())
    diagnostic_sha = sha((root / "research/insider_buying/backtest_realized_earnings_diagnostic.py").read_bytes())
    kwargs = causal_v2(make_causal_fixture(), analysis_sha=analysis_sha, diagnostic_sha=diagnostic_sha)
    source = causal.build_source_event_study_manifest_v2(**kwargs)
    plan = canonical.build_canonical_qc_batch_plan_v2(source_events=source, legacy_source=LEGACY.read_bytes(),
        security_master=kwargs["security_master"], entry_reference=kwargs["entry_reference"],
        registration=kwargs["registration"], parent_study_id="fixture-parent")
    native = canonical.adapt_canonical_qc_export(**native_inputs(plan))
    terminal_raw = plan.verify_native_completion_set((native,))
    registration, manifest, terminal = json.loads(kwargs["registration"]), json.loads(source.manifest_bytes()), json.loads(terminal_raw)
    issuers = {row["qc_symbol_id"]: row["issuer_cik"] for row in json.loads(kwargs["security_master"])["mappings"]}
    panel = make_panel_for_manifest_terminal(registration, manifest, terminal, issuers)
    raws = {"registration": kwargs["registration"], "manifest": source.manifest_bytes(), "terminal": terminal_raw, "panel": enc(panel)}
    result = analysis.analyze_registered_stock_study_v2(registration_raw=raws["registration"], manifest_raw=raws["manifest"],
        terminal_raw=raws["terminal"], panel_raw=raws["panel"], expected_implementation_sha256=analysis_sha,
        trust_roots=analysis.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(raws[role])) for role in analysis.ROLES)))
    diagnostic = assess(result, actual_source(result, offset=3), digest=diagnostic_sha)
    assert diagnostic["event_count"] == result.to_payload()["counts"]["events"] == 1
    assert diagnostic["earnings_exclusion_diagnostics"]["2"]["retained"] == 1
    assert diagnostic["earnings_exclusion_diagnostics"]["5"]["retained"] == 0
    assert result.to_payload()["registered_implementation_sha256"] == analysis_sha
    assert diagnostic["diagnostic_implementation_sha256"] == diagnostic_sha
    assert diagnostic["implementation_execution_identity_verified_here"] is False
    assert result.to_payload()["ib5_pass"] is diagnostic["ib5_pass"] is False


def successor_stream_inputs():
    raw, old_record = stream_fixture(count=3)
    registration = register_v2(json.loads(raw["registration"]))
    register_sha = sha(enc(registration))
    manifest = json.loads(raw["manifest"])
    manifest.update(schema="insider-stock-event-study-manifest-v3", registration_sha256=register_sha)
    for row in manifest["events"]: row.pop("earnings_distance_sessions")
    manifest_sha = sha(enc(manifest))
    terminal = json.loads(raw["terminal"])
    terminal.update(registration_sha256=register_sha, manifest_sha256=manifest_sha)
    descriptor = json.loads(raw["panel"])
    descriptor.update(registration_sha256=register_sha, manifest_sha256=manifest_sha)
    def record(index):
        body = json.loads(old_record(index))
        body.update(registration_sha256=register_sha, manifest_sha256=manifest_sha)
        return enc(body)
    for index, item in enumerate(descriptor["records"]):
        payload = record(index)
        item.update(sha256=sha(payload), byte_length=len(payload))
    raws = {"registration": enc(registration), "manifest": enc(manifest), "terminal": enc(terminal), "panel": enc(descriptor)}
    return raws, record


def test_successor_onepass_stream_releases_raw_records_and_diagnostic_uses_all_events():
    raws, record = successor_stream_inputs()
    references = []
    def records():
        for index in range(3):
            assert all(ref() is None for ref in references)
            holder = analysis.SuppliedPanelRecord(record(index)); references.append(weakref.ref(holder))
            yield holder
            del holder
    result = analysis.analyze_registered_stock_study_stream_v2(registration_raw=raws["registration"], manifest_raw=raws["manifest"],
        terminal_raw=raws["terminal"], panel_descriptor_raw=raws["panel"], panel_records=records(),
        trust_roots=analysis.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(raws[role])) for role in analysis.ROLES)),
        expected_implementation_sha256="a"*64)
    assert all(ref() is None for ref in references)
    assert result.to_payload()["panel_stream"]["records"] == 3
    assert assess(result, actual_source(result))["earnings_exclusion_diagnostics"]["2"]["retained"] == 3
    source = actual_source(result, offset=3)
    source["events"][1].update(coverage_disposition="UNAVAILABLE", unavailable_reason="missing-history", releases=[])
    diagnostic = assess(result, source)
    assert diagnostic["disposition"] == "UNAVAILABLE" and diagnostic["earnings_exclusion_diagnostics"] is None


def test_production_successor_stream_refuses_before_iterator_or_outcomes():
    raws, _ = successor_stream_inputs()
    class Never:
        def __iter__(self): raise AssertionError("production touched iterator")
    roots = analysis.RegisteredAnalysisTrustRoots("production", tuple((role, sha(raws[role])) for role in analysis.ROLES))
    # Match production registration only, then gate precedes all manifest/panel work.
    registration = json.loads(raws["registration"]); registration["trust_scope"] = "production"
    registration_raw = enc(registration)
    roots = analysis.RegisteredAnalysisTrustRoots("production", tuple((role, sha(registration_raw) if role == "registration" else sha(raws[role])) for role in analysis.ROLES))
    with pytest.raises(ValueError, match="zero-look"):
        analysis.analyze_registered_stock_study_stream_v2(registration_raw=registration_raw, manifest_raw=object(),
            terminal_raw=object(), panel_descriptor_raw=object(), panel_records=Never(), trust_roots=roots,
            expected_implementation_sha256="a"*64)


def test_actual_release_correction_and_retraction_lineage_is_replayed_not_latest_literal():
    result = evaluate_v2(); source = actual_source(result, offset=0)
    lineage = source["events"][0]["releases"][0]["lineage"]
    original = lineage[0]
    index = next(i for i, item in enumerate(result._body()["manifest"]["sessions"]) if item["session"] == result._body()["manifest"]["events"][0]["entry_session"])
    corrected = {**original, "version_id": "release-v2", "supersedes_version_id": "release-v1",
        "actual_public_release_at_utc": result._body()["manifest"]["sessions"][index+3]["session"] + "T12:00:00Z",
        "recorded_at_utc": result._body()["manifest"]["sessions"][index+11]["close_utc"]}
    lineage.append(corrected)
    assert assess(result, source)["earnings_exclusion_diagnostics"]["2"]["retained"] == 1
    corrected["status"] = "RETRACTED"
    assert assess(result, source)["earnings_exclusion_diagnostics"]["5"]["retained"] == 1
    corrected["supersedes_version_id"] = "foreign-version"
    with pytest.raises(ValueError): assess(result, source)


def test_weekend_release_uses_next_regular_close_without_midnight_guess():
    result = evaluate_v2(); source = actual_source(result, offset=2)
    sessions = result._body()["manifest"]["sessions"]
    entry = next(i for i, row in enumerate(sessions) if row["session"] == result._body()["manifest"]["events"][0]["entry_session"])
    friday = next(i for i in range(entry-4, entry+4) if analysis._date(sessions[i]["session"]).weekday() == 4)
    saturday = analysis._date(sessions[friday]["session"]) + timedelta(days=1)
    source["events"][0]["releases"][0]["lineage"][0]["actual_public_release_at_utc"] = saturday.isoformat() + "T12:00:00Z"
    expected = abs(friday+1-entry) > 2
    assert assess(result, source)["earnings_exclusion_diagnostics"]["2"]["retained"] == int(expected)


def stream_result_v2(raws, record):
    return analysis.analyze_registered_stock_study_stream_v2(registration_raw=raws["registration"], manifest_raw=raws["manifest"],
        terminal_raw=raws["terminal"], panel_descriptor_raw=raws["panel"], panel_records=(record(i) for i in range(3)),
        trust_roots=analysis.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(raws[role])) for role in analysis.ROLES)),
        expected_implementation_sha256="a"*64)


def test_stream_diagnostic_derived_arithmetic_is_not_ambient_precision_dependent():
    raws, record = successor_stream_inputs()
    precise = stream_result_v2(raws, record)
    expected = assess(precise, actual_source(precise))["earnings_exclusion_diagnostics"]
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        actual = stream_result_v2(raws, record)
        assert actual.to_payload() == precise.to_payload()
        assert assess(actual, actual_source(actual))["earnings_exclusion_diagnostics"] == expected


def test_valid_reordered_flat_manifest_joins_diagnostics_by_exact_source_identity():
    raws, record = successor_stream_inputs()
    records = [json.loads(record(i)) for i in range(3)]
    registration, manifest, terminal = (json.loads(raws[role]) for role in ("registration", "manifest", "terminal"))
    manifest["events"].reverse()
    panel = {key: records[0][key] for key in ("trust_scope", "registration_sha256", "manifest_sha256", "outcome_vintage_sha256", "matched_control_coverage_sha256")}
    panel.update(schema="insider-stock-event-study-panel-v2", events=[row for item in records for row in item["events"]],
        control_pools={item["entry_session"]: item["control_pool"] for item in records},
        selected_control_outcomes={item["entry_session"]: item["selected_control_outcomes"] for item in records})
    result = evaluate_v2({"registration": registration, "manifest": manifest, "terminal": terminal, "panel": panel})
    assert assess(result, actual_source(result))["earnings_exclusion_diagnostics"]["2"]["retained"] == 3
