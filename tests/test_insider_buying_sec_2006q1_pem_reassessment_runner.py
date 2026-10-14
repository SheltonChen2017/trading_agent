"""Invented isolated PEM front fixtures, not observed production execution."""
from __future__ import annotations

import base64
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="validated macOS/POSIX custody scope")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from research import insider_buying_sec_2006q1_pem_reassessment_runner as module
import test_insider_buying_sec_2006q1_pem_reassessment_v1 as fixtures
DIRECTORY = Path(module.__file__).parent
from test_insider_buying_sec_2006q1_parent_projection_v1 import _summary as _baseline_summary


@pytest.fixture
def supplied(tmp_path, monkeypatch):
    source, output = fixtures._fixture(tmp_path, monkeypatch);receipt = fixtures._run(source, output)
    original = module.original
    _, _, census, _, _, _ = original.preparation._prepare_inputs(source)
    raw = output / "ib1a" / receipt["raw_snapshot_id"]
    snapshot = original.load_sec_bulk_parsed_snapshot(output / "ib1b" / receipt["parsed_snapshot_id"], raw_snapshot_directory=raw)
    baseline = module.pure.v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    return snapshot, census, original._source_filings(snapshot, baseline)


def _result(supplied):
    snapshot, census, _ = supplied
    return module.pure.assess_2006q1_pem_source_view_identity(snapshot, census, fixtures._inputs(supplied),
        expected_capture_report_sha256=module.CAPTURE_REPORT, fixture_only=True)


def _preparation_context(supplied):
    snapshot,census,_ = supplied
    rows = module.pure.v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()["rows"]
    return {"parsed_snapshot_id": snapshot.identity.snapshot_id, "parsed_lineage_sha256": snapshot.identity.lineage_hash,
        "census_quarter_sha256": module.original.hash_payload(census.to_payload()), **module._source_identity_inventory(rows)}


def _capture_context():
    return {"capture_id": module.original.CAPTURE_ID, "capture_execution_head": "d" * 40,
        "capture_execution_source_inventory_sha256": "c" * 64, "bootstrap_execution_head": "e" * 40}


def _invented_baseline(supplied):
    return {"complete_sha256": "b" * 64, "preparation_context": _preparation_context(supplied),
        "capture_execution_context": _capture_context()}


def _identity():
    names = [module.SELF_PATH, module.PURE_PATH, module.VIEW_PATH, module.original.SELF_PATH,
        "research/insider_buying/sec_complete_submission.py", "research/insider_buying/sec_ib1c_identity_v2.py",
        "research/insider_buying_affected_quarter_isolation.py"]
    return {"source_sha256": {name: "a" * 64 for name in names}, "head": "a" * 40}


def _baseline(tmp_path, *, mutate=None):
    root = tmp_path / "invented-baseline";root.mkdir(mode=0o700)
    summary = _baseline_summary();counts = summary["counts"]
    counts.update(projected_complete_parents=0, grammar_quarantined_parents=64,
        corroborated_noncanonical_filings=0, quarantined_filings=83657, target_parent_corroboration_missing=71679)
    summary["projection_refusal_counts"]["sec_document_envelope_refused"] = 64
    counts.update(source_filings=6, target_filings=2, context_filings=4, selected_parents=1, retained_parent_bodies=1,
        grammar_quarantined_parents=1, quarantined_filings=6, target_parent_corroboration_missing=2,
        unsupported_context_forms=4, retained_parent_bytes=1000)
    summary["projection_refusal_counts"]["sec_document_envelope_refused"] = 1
    source_rows = [{"period": "2006Q1", "source_record_ordinal": index,
        "accession_number": f"0000123456-06-{index:06d}", "form_type": form, "raw_filing_date": "15-JAN-2006",
        "filing_date": "2006-01-15", "raw_issuer_cik": "0000123456", "issuer_comparison_key": "0000123456",
        "short_cik": False, "accession_year_mismatch": False, "submission_row_id": "a" * 64,
        "raw_archive_sha256": "b" * 64, "raw_submission_member_sha256": "c" * 64, "parsed_lineage_hash": "a" * 64}
        for index,form in enumerate(("3", "3/A", "4", "4/A", "5", "5/A"), 1)]
    assessment = module._raw({"invented_six_form_assessment": True, "rows": source_rows})
    ledger = module._raw({"counts": counts, "projection_refusal_counts": summary["projection_refusal_counts"],
        "parsed_snapshot_id": "sec-insider-parsed-2006q1-" + "a" * 16,
        "parsed_lineage_sha256": "a" * 64, "census_quarter_sha256": "b" * 64})
    reservation = module._raw({"audit_id": module.BASELINE_ID, "capture_report_sha256": module.CAPTURE_REPORT})
    complete = {"schema": module.original.SCHEMA + "/complete", "audit_id": module.BASELINE_ID, "fixture_only": True,
        "capture_id": module.original.CAPTURE_ID, "capture_report_sha256": module.CAPTURE_REPORT,
        "reservation_sha256": module._sha(reservation), "assessment_sha256": module._sha(assessment),
        "projection_ledger_sha256": module._sha(ledger), "assessment_bytes": len(assessment), "projection_ledger_bytes": len(ledger),
        "counts": counts, "projection_refusal_counts": summary["projection_refusal_counts"],
        "authority": module.original._authority(), "current_execution_identity": {"head": "a" * 40,
            "source_inventory_sha256": "b" * 64}}
    complete.update(_capture_context())
    complete.update(original_preparation_producer_commit=module.original.downstream.PRODUCER_COMMIT,
        original_preparation_completion_sha256=module.original.downstream.EXPECTED_COMPLETION_SHA256,
        original_preparation_assessment_sha256=module.original.downstream.EXPECTED_ASSESSMENT_SHA256)
    if mutate is not None:mutate(complete)
    leaves = {"assessment.json": assessment, "parent-projection.json": ledger,
        "reservation.json": reservation, "complete.json": module._raw(complete)}
    for name, raw in leaves.items():
        path = root / name;path.write_bytes(raw);path.chmod(0o600)
    pins = {name: (module._sha(raw), len(raw)) for name,raw in leaves.items()}
    return root, pins


def _summary():
    counts = {"source_filings": 83657, "target_filings": 71679, "context_filings": 11978,
        "selected_parents": 64, "original_bodies_retained": 64, "exact_pem_source_views": 64,
        "frozen_source_view_projections": 57, "pem_profile_quarantined": 0, "source_view_parser_quarantined": 7,
        "source_view_unavailable": 0, "source_view_corroborated_noncanonical": 57, "quarantined_filings": 83600,
        "original_parent_bytes": 419628, "original_body_admitted": 0}
    reasons = {key: 0 for key in module._REFUSALS};reasons["legacy_blank_separator_refused"] = 7
    return {"audit_id": "ib-2006q1-pem-view-invented", "fixture_only": False,
        **{key: "a" * 64 for key in ("complete_sha256", "assessment_sha256", "parent_ledger_sha256", "source_view_inventory_sha256")},
        "capture_report_sha256": module.CAPTURE_REPORT, "baseline_complete_sha256": module.BASELINE_COMPLETE,
        "counts": counts, "refusal_counts": reasons, "authority": module._authority()}


def _check(summary):
    return module._strict_summary(summary, audit_id=summary["audit_id"], report_sha=module.CAPTURE_REPORT,
        baseline_sha=module.BASELINE_COMPLETE)


def test_invented_baseline_four_leaf_chain_is_pinned_and_rechecked_before_use(tmp_path):
    root,pins = _baseline(tmp_path)
    held = module._PinnedBaseline(pins["complete.json"][0], fixture_only=True, root=root, leaf_pins=pins)
    try:
        held.recheck()
        assert held.metadata["original_body_quarantine_unchanged"] is True
        assert held.metadata["execution_head"] == "a" * 40
        (root / "assessment.json").write_bytes(b"{}")
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()


@pytest.mark.parametrize("mutation", ["bad_external_hash", "extra_leaf", "hardlink", "symlink", "mode", "size", "bool_count", "positive_authority", "view_promotion"])
def test_frozen_baseline_cannot_be_forged_or_substituted(tmp_path, mutation):
    def mutate(body):
        if mutation == "bool_count":body["counts"]["source_parent_identity_conflicts"] = False
        elif mutation == "positive_authority":body["authority"]["backtesting_ready"] = True
        elif mutation == "view_promotion":body["counts"]["projected_complete_parents"] = 1
    root,pins = _baseline(tmp_path, mutate=mutate)
    expected = pins["complete.json"][0]
    if mutation == "bad_external_hash":expected = "f" * 64
    elif mutation == "extra_leaf":(root / "unexpected.json").write_bytes(b"{}");(root / "unexpected.json").chmod(0o600)
    elif mutation == "hardlink":os.link(root / "assessment.json", tmp_path / "linked.json")
    elif mutation == "symlink":(root / "assessment.json").rename(tmp_path / "original.json");(root / "assessment.json").symlink_to(tmp_path / "original.json")
    elif mutation == "mode":(root / "assessment.json").chmod(0o644)
    elif mutation == "size":pins["assessment.json"] = (pins["assessment.json"][0], pins["assessment.json"][1] + 1)
    with pytest.raises((ValueError, OSError)):
        module._PinnedBaseline(expected, fixture_only=True, root=root, leaf_pins=pins)


@pytest.mark.parametrize("root", [LANE, LANE.parent, LANE / "artifacts/insider_buying"])
def test_invented_baseline_fence_precedes_actual_root_reads(root, monkeypatch):
    monkeypatch.setattr(module.original.capture.bootstrap, "_Tree", lambda *_: pytest.fail("actual root read"))
    with pytest.raises(ValueError):
        module._PinnedBaseline("a" * 64, fixture_only=True, root=root, leaf_pins={})


@pytest.mark.parametrize("kind", ["external_sibling", "temporary_root_itself", "dotdot", "case_alias", "symlink_inside", "symlink_outside"])
def test_standalone_temporary_fixture_fence_precedes_legacy_known_root_helper_or_tree(tmp_path, monkeypatch, kind):
    trusted = Path(tempfile.gettempdir()).resolve()
    if kind == "external_sibling":root = LANE.parent / "invented-history-candidate"
    elif kind == "temporary_root_itself":root = trusted
    elif kind == "dotdot":root = tmp_path / ".." / "invented-history-candidate"
    elif kind == "case_alias":root = Path(str(tmp_path).replace("/private/tmp", "/PRIVATE/TMP"))
    else:
        target = tmp_path / "target";target.mkdir(mode=0o700)
        root = tmp_path / "alias";root.symlink_to(target if kind == "symlink_inside" else LANE.parent)
    monkeypatch.setattr(module.original.capture, "_fixture_root", lambda *_: pytest.fail("unsafe path reached old known-root helper"))
    monkeypatch.setattr(module.original.capture.bootstrap, "_Tree", lambda *_: pytest.fail("unsafe path reached a custody tree"))
    with pytest.raises(module.PemReassessmentRunnerError):
        module._PinnedBaseline("a" * 64, fixture_only=True, root=root, leaf_pins={})


def test_external_baseline_failure_occurs_before_fresh_reservation(monkeypatch):
    events = []
    monkeypatch.setattr(module, "_fixed_source_identity", lambda *_: ({}, {}))
    monkeypatch.setattr(module.original.capture, "_verify_original_committed_sources", lambda *_: events.append("capture_lineage"))
    def refuse(*_args, **_kwargs):
        events.append("baseline")
        raise module.PemReassessmentRunnerError("invented_missing_baseline")
    monkeypatch.setattr(module, "_PinnedBaseline", refuse)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: pytest.fail("reserved before baseline"))
    with pytest.raises(module.PemReassessmentRunnerError, match="invented_missing_baseline"):
        module.run_observed_reassessment("ib-2006q1-pem-view-invented", expected_head="a" * 40,
            expected_capture_report_sha256=module.CAPTURE_REPORT, expected_baseline_complete_sha256=module.BASELINE_COMPLETE)
    assert events == ["capture_lineage", "baseline"]


def test_actual_cli_has_no_fixture_or_direct_unisolated_worker_backdoor(capsys):
    with pytest.raises(SystemExit) as missing:
        module.main(["--audit-id", "ib-2006q1-pem-view-invented", "--expected-head", "a" * 40,
            "--expected-capture-report-sha256", module.CAPTURE_REPORT])
    assert missing.value.code == 2
    with pytest.raises(SystemExit):module.main(["--fixture", "--worker"])
    capsys.readouterr()


def test_inactive_image_actual_cli_refuses_before_source_or_capture_access(monkeypatch, capsys):
    monkeypatch.setattr(module, "__file__", str(DIRECTORY / "inactive-pem-front.py"))
    monkeypatch.setattr(module.original, "_fixed_source_identity", lambda *_: pytest.fail("private draft reached actual identity"))
    status = module.main(["--audit-id", "ib-2006q1-pem-view-invented", "--expected-head", "a" * 40,
        "--expected-capture-report-sha256", module.CAPTURE_REPORT, "--expected-baseline-complete-sha256", module.BASELINE_COMPLETE])
    assert status == 2
    wire = json.loads(capsys.readouterr().out)
    assert wire["failure_class"] == "PemReassessmentRunnerError"
    assert wire["failure_phase"] == "parent_preflight"


def test_strict_actual_summary_preserves_independently_attributed57_7_partition():
    summary = _summary();assert _check(summary) is summary


@pytest.mark.parametrize("mutation", ["bool_count", "missing_count", "extra_count", "count_partition", "population", "positive_authority",
    "false_as_zero", "unknown_reason", "bool_reason", "wrong_reason_total", "bad_hash", "fixture", "baseline"])
def test_public_summary_refuses_forged_typed_counts_authority_or_scope(mutation):
    value = _summary()
    if mutation == "bool_count":value["counts"]["original_body_admitted"] = False
    elif mutation == "missing_count":del value["counts"]["source_view_unavailable"]
    elif mutation == "extra_count":value["counts"]["invented_count"] = 0
    elif mutation == "count_partition":value["counts"]["source_view_parser_quarantined"] = 6
    elif mutation == "population":value["counts"]["source_filings"] = 83658
    elif mutation == "positive_authority":value["authority"]["whole_original_parent_admitted"] = True
    elif mutation == "false_as_zero":value["authority"]["whole_original_parent_admitted"] = 0
    elif mutation == "unknown_reason":value["refusal_counts"]["private source text"] = 0
    elif mutation == "bool_reason":value["refusal_counts"]["legacy_blank_separator_refused"] = True
    elif mutation == "wrong_reason_total":value["refusal_counts"]["legacy_blank_separator_refused"] = 6
    elif mutation == "bad_hash":value["assessment_sha256"] = "not-a-hash"
    elif mutation == "fixture":value["fixture_only"] = True
    else:value["baseline_complete_sha256"] = "b" * 64
    with pytest.raises(ValueError):_check(value)


def test_fixture_publication_seals_full_six_form_assessment_ledger_inventory_and_no_raw_bytes(tmp_path, supplied):
    output_path = tmp_path / "fresh-output";output_path.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(output_path)
    identity = _identity();baseline = _invented_baseline(supplied);audit_id = "ib-2006q1-pem-view-invented"
    reservation = module._raw(module._reservation(audit_id, identity, {}, module.CAPTURE_REPORT, baseline))
    output.publish("reservation.json", reservation)
    bootstrap = {"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": "a" * 64}
    rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items() if name != bootstrap["path"]]
    try:
        summary = module._publish_assessment(output, _result(supplied), audit_id=audit_id, reservation_raw=reservation,
            identity=identity, frozen={}, baseline=baseline, capture_reservation={"execution_identity": {"source_inventory_sha256": "c" * 64}},
            capture_report={"capture_execution_head": "d" * 40, "bootstrap_execution_head": "e" * 40},
            executed_sources=rows, bootstrap_source=bootstrap, fixture_only=True)
        assert set(os.listdir(output.fd)) == module._FILES
        assert summary["fixture_only"] is True and summary["counts"]["source_filings"] == 6
        assessment = json.loads(output.read("assessment.json", cap=module.MAX_ASSESSMENT_BYTES))
        assert len(assessment["rows"]) == 6
        assert assessment["counts"]["source_view_corroborated_noncanonical"] == 1
        assert assessment["rows"][2]["corroboration"]["parent_sha256"] != assessment["rows"][2]["original_parent_custody"]["original_raw_parent"]["sha256"]
        assert b"<ownershipDocument>" not in output.read("assessment.json", cap=module.MAX_ASSESSMENT_BYTES)
        for name in module._FILES:assert (output_path / name).stat().st_mode & 0o777 == 0o600
        (output_path / "source-view-inventory.json").write_bytes(b"{}")
        with pytest.raises(ValueError):module._verify_publication(output, summary, identity=identity, frozen={}, baseline=baseline, fixture_only=True)
    finally:output.close()


def test_publication_independently_recounts_rows_instead_of_trusting_consistent_upstream_counts(tmp_path, supplied):
    # Fault injection in an upstream produced object, not a source or authority
    # claim. The two mutated integers still satisfy the full sum partition.
    result = _result(supplied);payload = result.to_payload()
    payload["counts"]["source_view_corroborated_noncanonical"] = 0
    payload["counts"]["quarantined_filings"] = 6
    encoded = module._raw(payload)
    object.__setattr__(result, "_bytes", encoded);object.__setattr__(result, "_factory_bytes", encoded)
    output_path = tmp_path / "mutant-output";output_path.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(output_path)
    identity = _identity();baseline = _invented_baseline(supplied);audit_id = "ib-2006q1-pem-view-invented"
    reservation = module._raw(module._reservation(audit_id, identity, {}, module.CAPTURE_REPORT, baseline))
    output.publish("reservation.json", reservation)
    bootstrap = {"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": "a" * 64}
    rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items() if name != bootstrap["path"]]
    try:
        with pytest.raises(module.PemReassessmentRunnerError, match="measured_pem_rows_or_ledger_counts_differ"):
            module._publish_assessment(output, result, audit_id=audit_id, reservation_raw=reservation,
                identity=identity, frozen={}, baseline=baseline, capture_reservation={"execution_identity": {"source_inventory_sha256": "c" * 64}},
                capture_report={"capture_execution_head": "d" * 40, "bootstrap_execution_head": "e" * 40},
                executed_sources=rows, bootstrap_source=bootstrap, fixture_only=True)
        assert set(os.listdir(output.fd)) == {"reservation.json"}
    finally:output.close()


@pytest.mark.parametrize("mutation", ["row_header_bound", "row_positive_authority", "parsed_snapshot",
    "wrong_period", "whole_original_identity_kind", "wrong_v2_kind", "unselected_accession"])
def test_peer_verified_rehashed_row_or_preparation_faults_are_refused_before_publication(tmp_path, supplied, mutation):
    result = _result(supplied);payload = result.to_payload()
    if mutation == "row_header_bound":payload["rows"][2]["original_parent_custody"]["original_capture_header_identity_bound"] = True
    elif mutation == "row_positive_authority":payload["rows"][2]["source_view_qualification"]["projection_bridge"]["authority"]["backtesting_ready"] = True
    elif mutation == "parsed_snapshot":payload["parsed_snapshot_id"] = "sec-insider-parsed-2006q1-" + "f" * 16
    elif mutation == "wrong_period":payload["period"] = "2022Q4"
    elif mutation == "whole_original_identity_kind":payload["source_identity_kind"] = "whole_original_parent_admitted"
    elif mutation == "wrong_v2_kind":payload["v2_source_view_assessment_kind"] = "invented_kind"
    else:payload["rows"][0]["accession_number"] = "9999999999-06-999999"
    payload["rows_sha256"] = module._sha(module._raw(payload["rows"]))
    encoded = module._raw(payload);object.__setattr__(result, "_bytes", encoded);object.__setattr__(result, "_factory_bytes", encoded)
    output_path = tmp_path / "mutant-copy-output";output_path.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(output_path)
    identity = _identity();baseline = _invented_baseline(supplied)
    audit_id = "ib-2006q1-pem-view-invented"
    reservation = module._raw(module._reservation(audit_id, identity, {}, module.CAPTURE_REPORT, baseline));output.publish("reservation.json", reservation)
    bootstrap = {"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": "a" * 64}
    rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items() if name != bootstrap["path"]]
    try:
        with pytest.raises(module.PemReassessmentRunnerError, match="row_original_custody_or_source_view_copy_differs|observed_preparation_identity_differs|strict_pem_assessment_context_required|observed_full_source_row_identity_differs"):
            module._publish_assessment(output, result, audit_id=audit_id, reservation_raw=reservation,
                identity=identity, frozen={}, baseline=baseline, capture_reservation={"execution_identity": {"source_inventory_sha256": "c" * 64}},
                capture_report={"capture_execution_head": "d" * 40, "bootstrap_execution_head": "e" * 40},
                executed_sources=rows, bootstrap_source=bootstrap, fixture_only=True)
        assert set(os.listdir(output.fd)) == {"reservation.json"}
    finally:output.close()


@pytest.mark.parametrize("field", ["capture_id", "capture_execution_head", "capture_execution_source_inventory_sha256",
    "bootstrap_execution_head", "original_preparation_producer_commit", "original_preparation_completion_sha256",
    "original_preparation_assessment_sha256"])
def test_peer_verified_complete_lineage_fields_cannot_be_coherently_rehashed_into_new_context(tmp_path, supplied, monkeypatch, field):
    output_path = tmp_path / "lineage-output";output_path.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(output_path)
    identity = _identity();baseline = _invented_baseline(supplied);audit_id = "ib-2006q1-pem-view-invented"
    reservation = module._raw(module._reservation(audit_id, identity, {}, module.CAPTURE_REPORT, baseline));output.publish("reservation.json", reservation)
    bootstrap = {"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": "a" * 64}
    rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items() if name != bootstrap["path"]]
    try:
        summary = module._publish_assessment(output, _result(supplied), audit_id=audit_id, reservation_raw=reservation,
            identity=identity, frozen={}, baseline=baseline, capture_reservation={"execution_identity": {"source_inventory_sha256": "c" * 64}},
            capture_report={"capture_execution_head": "d" * 40, "bootstrap_execution_head": "e" * 40},
            executed_sources=rows, bootstrap_source=bootstrap, fixture_only=True)
        real_read = output.read;complete = json.loads(real_read("complete.json", cap=module.MAX_CONTROL_BYTES))
        complete[field] = "invented-wrong-observed-context";raw = module._raw(complete)
        monkeypatch.setattr(output, "read", lambda name, **kwargs: raw if name == "complete.json" else real_read(name, **kwargs))
        changed = {**summary, "complete_sha256": module._sha(raw)}
        with pytest.raises(module.PemReassessmentRunnerError, match="observed_capture_or_original_preparation_lineage_differs"):
            module._verify_publication(output, changed, identity=identity, frozen={}, baseline=baseline, fixture_only=True)
    finally:output.close()


@pytest.mark.parametrize("mutation", ["measured_parent_bytes", "drop_row", "form_count_bool", "unknown_row_state",
    "context_promoted", "original_hash_in_view_slot", "view_offset_bool", "inventory_parent_bool", "inventory_extra_bridge",
    "ledger_header_bound", "projection_presence", "altered_epoch", "row_whole_parent_admitted"])
def test_independent_final_assessment_guard_refuses_row_ledger_inventory_faults(supplied, mutation):
    payload = _result(supplied).to_payload()
    if mutation == "measured_parent_bytes":payload["counts"]["original_parent_bytes"] += 1
    elif mutation == "drop_row":payload["rows"].pop()
    elif mutation == "form_count_bool":payload["form_counts"]["3"] = True
    elif mutation == "unknown_row_state":payload["rows"][0]["disposition"] = "unknown"
    elif mutation == "context_promoted":payload["rows"][0]["disposition"] = "source_view_corroborated_noncanonical"
    elif mutation == "original_hash_in_view_slot":
        parent = payload["parent_qualification_ledger"][0]
        parent["source_view"]["derived_sec_document_source_view"]["sha256"] = parent["original_raw_parent"]["sha256"]
    elif mutation == "view_offset_bool":payload["parent_qualification_ledger"][0]["source_view"]["derived_sec_document_source_view"]["source_offset_bytes"] = True
    elif mutation == "inventory_parent_bool":payload["source_view_inventory"]["parent_count"] = True
    elif mutation == "inventory_extra_bridge":payload["source_view_inventory"]["rows"].append(payload["source_view_inventory"]["rows"][0])
    elif mutation == "ledger_header_bound":payload["parent_qualification_ledger"][0]["original_capture_header_identity_bound"] = True
    elif mutation == "projection_presence":payload["parent_qualification_ledger"][0]["projection_bridge"] = None
    elif mutation == "altered_epoch":payload["evidence_epoch"] = "INVENTED wrong source epoch"
    else:payload["rows"][0]["whole_original_parent_admitted"] = True
    # Rehash metadata to exercise semantics, not merely a digest mismatch.
    payload["rows_sha256"] = module._sha(module._raw(payload["rows"]))
    payload["parent_qualification_ledger_sha256"] = module._sha(module._raw(payload["parent_qualification_ledger"]))
    payload["source_view_inventory_sha256"] = module._sha(module._raw(payload["source_view_inventory"]))
    with pytest.raises((ValueError, TypeError)):
        module._validate_assessment(payload, fixture_only=True, preparation_context=_preparation_context(supplied))


@pytest.mark.parametrize("key", ["parsed_snapshot_id", "parsed_lineage_sha256", "census_quarter_sha256"])
def test_known_preparation_context_is_external_and_cannot_follow_rehashed_assessment_mutation(supplied, key):
    payload = _result(supplied).to_payload()
    payload[key] = "sec-insider-parsed-2006q1-" + "f" * 16 if key == "parsed_snapshot_id" else "f" * 64
    with pytest.raises(module.PemReassessmentRunnerError, match="observed_preparation_identity_differs"):
        module._validate_assessment(payload, fixture_only=True, preparation_context=_preparation_context(supplied))


def test_even_fixture_validation_cannot_invent_expected_context_from_its_own_payload(supplied):
    payload = _result(supplied).to_payload()
    with pytest.raises(TypeError):module._validate_assessment(payload, fixture_only=True)
    with pytest.raises(ValueError):module._validate_assessment(payload, fixture_only=True, preparation_context=None)


def test_fresh_output_is_private_exclusive_and_has_disk_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(module.original.capture.bootstrap.custody, "LANE_ROOT", tmp_path)
    held = module._output_directory("ib-2006q1-pem-view-invented", create=True)
    try:
        assert held.path.stat().st_mode & 0o777 == 0o700
        assert set(os.listdir(held.fd)) == set()
        with pytest.raises(module.PemReassessmentRunnerError, match="fresh_pem_output_required"):
            module._output_directory("ib-2006q1-pem-view-invented", create=True)
    finally:held.close()
    monkeypatch.setattr(module.os, "fstatvfs", lambda *_: SimpleNamespace(f_bavail=0, f_frsize=1))
    with pytest.raises(module.PemReassessmentRunnerError, match="pem_disk_reserve_refused"):
        module._output_directory("ib-2006q1-pem-view-second-invented", create=True)
    assert not tmp_path.joinpath(*module.OUTPUT_PARTS, "ib-2006q1-pem-view-second-invented").exists()


@pytest.mark.parametrize("mutation", ["unknown_source", "duplicate_source", "wrong_digest", "missing_pure", "missing_view", "missing_front"])
def test_executed_inventory_requires_all_genuine_captured_source_paths(mutation):
    identity = _identity();rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items()]
    if mutation == "unknown_source":rows.append({"path": "research/UNKNOWN.py", "sha256": "a" * 64})
    elif mutation == "duplicate_source":rows.append(rows[0])
    elif mutation == "wrong_digest":rows[0]["sha256"] = "b" * 64
    else:rows = [row for row in rows if row["path"] != {"missing_pure": module.PURE_PATH, "missing_view": module.VIEW_PATH, "missing_front": module.SELF_PATH}[mutation]]
    with pytest.raises(ValueError):module._source_execution_context(rows, identity)


def _captured_probe(code, *, mutate=None):
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    sources = {helper_path: module.original.isolation._read_source(helper_path), "research/__init__.py": b"", module.SELF_PATH: code}
    envelope = {"sources": [{"path": name, "sha256": module._sha(raw), "source_b64": base64.b64encode(raw).decode("ascii")}
        for name,raw in sorted(sources.items())], "parent_context": {"identity": {"source_sha256": {name: module._sha(raw) for name,raw in sources.items()}}},
        "audit_id": "ib-2006q1-pem-view-captured-fixture", "expected_head": "a" * 40, "report_sha256": module.CAPTURE_REPORT,
        "baseline_sha256": module.BASELINE_COMPLETE}
    if mutate is not None:mutate(envelope)
    return subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP], cwd=LANE,
        input=module._raw(envelope), capture_output=True, check=False, timeout=30)


def test_captured_front_uses_fixed_consumer_and_proves_os_denial_before_python_hook():
    code = b'''import errno, json, socket, sys
from research import insider_buying_affected_quarter_isolation as helper
def _worker(audit_id, **kwargs):
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(.2);sock.connect(("127.0.0.1", 9))
    except OSError as exc:
        assert exc.errno in {errno.EPERM, errno.EACCES}
    else:raise AssertionError("inherited OS denial absent")
    finally:
        if sock is not None:sock.close()
    sys.addaudithook(helper._audit_event)
    try:socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except helper.AffectedQuarterIsolationError:blocked = True
    else:raise AssertionError("late audit hook absent")
    return {"fixture_only": True, "os_network_denial_observed": True, "late_hook_observed": blocked,
        "source_inventory_is_list_not_callback": type(kwargs["executed_sources"]) is list,
        "baseline_sha256": kwargs["expected_baseline_complete_sha256"]}
def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
'''
    child = _captured_probe(code)
    assert child.returncode == 0 and not child.stderr
    assert child.stdout.endswith(b"\n") and not child.stdout.endswith(b"\n\n")
    assert json.loads(child.stdout) == {"fixture_only": True, "os_network_denial_observed": True,
        "late_hook_observed": True, "source_inventory_is_list_not_callback": True, "baseline_sha256": module.BASELINE_COMPLETE}


@pytest.mark.parametrize("mutation", ["hash", "missing_consumer", "duplicate_helper"])
def test_captured_bootstrap_refuses_bad_inventory_without_repository_import_fallback(mutation):
    code = b'def _worker(*args, **kwargs):raise AssertionError("must not execute bad source context")\n'
    def alter(body):
        if mutation == "hash":body["parent_context"]["identity"]["source_sha256"][module.SELF_PATH] = "f" * 64
        elif mutation == "missing_consumer":body["sources"] = [row for row in body["sources"] if row["path"] != module.SELF_PATH]
        else:body["sources"].append(next(row for row in body["sources"] if row["path"].endswith("affected_quarter_isolation.py")))
    child = _captured_probe(code, mutate=alter)
    assert child.returncode == 2 and not child.stderr
    body = json.loads(child.stdout)
    assert body["disposition"] == "offline_pem_source_view_refused_outputs_preserved"
    assert body["failure_phase"] in {"worker_bootstrap_context", "worker_bootstrap_source_decode"}


@pytest.mark.parametrize("suffix", [b"", b"\n\n", b" \n", b"\n\n\n"])
def test_parent_wire_refuses_missing_or_extra_framing_lf_before_summary(tmp_path, monkeypatch, suffix):
    identity = {"source_sha256": {}};held = SimpleNamespace(metadata={"complete_sha256": module.BASELINE_COMPLETE}, recheck=lambda: None, close=lambda: None)
    output = SimpleNamespace(path=tmp_path, publish=lambda *_args, **_kwargs: None, close=lambda: None)
    monkeypatch.setattr(module, "_fixed_source_identity", lambda *_: (identity, {}))
    monkeypatch.setattr(module.original.capture, "_verify_original_committed_sources", lambda *_: None)
    monkeypatch.setattr(module, "_PinnedBaseline", lambda *_: held)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: output)
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=b"{}" + suffix, stderr=b"", returncode=0))
    monkeypatch.setattr(module, "_strict_summary", lambda *_args, **_kwargs: pytest.fail("bad wire reached summary"))
    with pytest.raises(ValueError):module.run_observed_reassessment("ib-2006q1-pem-view-invented", expected_head="a" * 40,
        expected_capture_report_sha256=module.CAPTURE_REPORT, expected_baseline_complete_sha256=module.BASELINE_COMPLETE)


def test_failure_diagnostic_never_emits_private_exception_text_or_path():
    message = "PRIVATE source body or contact must not appear"
    body = module._failure_diagnostic(PermissionError(errno.EACCES, message), "worker_capture")
    assert message not in module._raw(body).decode()
    assert body["failure_phase"] == "worker_capture" and body["os_errno"] == errno.EACCES


def test_worker_uses_effective_fork_and_write_denial_before_opening_any_inputs(monkeypatch):
    # Static source order is paired with the captured subprocess's actual OS
    # network/hook order test above. No actual custody reader is executed here.
    source = (DIRECTORY / "insider_buying_sec_2006q1_pem_reassessment_runner.py").read_text()
    start = source.index("def _worker(");end = source.index("def run_observed_reassessment(", start)
    worker = source[start:end]
    assert worker.index("original._prove_worker_isolation") < worker.index("sys.addaudithook") < worker.index('"worker_baseline", _PinnedBaseline')
    assert worker.index("sys.addaudithook") < worker.index("original._load_original_preparation") < worker.index("original._load_sealed_capture")
    assert "executed_sources()" not in worker and "monkeypatch" not in worker

