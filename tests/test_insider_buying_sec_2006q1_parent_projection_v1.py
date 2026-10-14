"""Activated observer fixtures; no retained capture or source reads."""
from __future__ import annotations

from dataclasses import replace
import base64
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody support")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_ib1c_v2_affected_quarter_runner import _fixture, _run, _payload
from test_insider_buying_sec_complete_submission import _complete, _legacy_header
from test_insider_buying_sec_2006q1_parent_capture_v1 import _run as _capture_fixture

SOURCE = LANE / "research/insider_buying_sec_2006q1_parent_projection_v1.py"
spec = importlib.util.spec_from_file_location("ib_early_projection_active_test", SOURCE)
module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module;spec.loader.exec_module(module)


@pytest.fixture
def supplied(tmp_path, monkeypatch):
    source, output = _fixture(tmp_path, monkeypatch)
    receipt = _run(source, output)
    _, _, census, _, _, _ = module.preparation._prepare_inputs(source)
    raw = output / "ib1a" / receipt["raw_snapshot_id"]
    snapshot = module.load_sec_bulk_parsed_snapshot(output / "ib1b" / receipt["parsed_snapshot_id"], raw_snapshot_directory=raw)
    baseline = module.identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    return snapshot, census, module._source_filings(snapshot, baseline)


def _request(snapshot, filing):
    accession = filing["accession_number"]
    archive = "edgar/data/987654/" + accession + ".txt"
    table = next(t for t in snapshot.identity.tables if t.table_name == "SUBMISSION.tsv")
    return {"period": "2006Q1", "accession_number": accession, "form_type": filing["form_type"],
        "filing_date": filing["filing_date"], "issuer_cik": filing["issuer_cik"], "archive_path": archive,
        "url": "https://www.sec.gov/Archives/" + archive, "source_record_ordinal": filing["source_record_ordinal"],
        "accession_key_sha256": module._sha(accession.encode()), "filing_metadata_sha256": module._sha(module._raw(filing)),
        "submission_inventory_sha256": "c" * 64, "quarterly_zip_sha256": snapshot.identity.raw_archive_sha256,
        "submission_member_sha256": table.raw_member_sha256, "master_decoded_sha256": "d" * 64,
        "master_receipt_sha256": "e" * 64}


def _parent(request):
    raw = _complete(header=_legacy_header()).replace(b"0000999999-22-000001", request["accession_number"].encode())
    raw = raw.replace(b"20221107", b"20060115")
    if request["form_type"] == "4/A":
        raw = (raw.replace(b"CONFORMED SUBMISSION TYPE:\t4\n", b"CONFORMED SUBMISSION TYPE:\t4/A\n")
            .replace(b"FORM TYPE:\t4\n", b"FORM TYPE:\t4/A\n")
            .replace(b"<TYPE>4\n", b"<TYPE>4/A\n")
            .replace(b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"))
    return raw


def _inputs(supplied, *, selected=1):
    snapshot, _, filings = supplied
    candidates = sorted((f for f in filings.values() if f["relevant_form4_or_amendment"]),
        key=lambda f: (f["filing_date"], f["accession_number"], f["source_record_ordinal"]))
    result = []
    for ordinal, filing in enumerate(candidates[:selected]):
        request = _request(snapshot, filing);raw = _parent(request)
        result.append({"prefix_ordinal": ordinal, "request_sha256": module._sha(module._raw(request)),
            "request": request, "result_sha256": "a" * 64,
            "terminal_disposition": "complete_raw_response_retained_header_bound",
            "body_sha256": module._sha(raw), "body_size_bytes": len(raw), "raw_bytes": raw, "header_identity_bound": True})
    return tuple(result)


def _assess(supplied, inputs=None, **kwargs):
    snapshot, census, _ = supplied
    return module.assess_supplied_early_parents(snapshot, census, _inputs(supplied) if inputs is None else inputs,
        expected_capture_report_sha256="f" * 64, fixture_only=True, **kwargs)


def _changed(item, raw):
    return {**item, "raw_bytes": raw, "body_sha256": module._sha(raw), "body_size_bytes": len(raw)}


def test_original_parent_reassesses_complete_six_form_quarter_without_admission(supplied):
    result = _assess(supplied);payload = result.to_payload()
    assert payload["counts"]["source_filings"] == 6
    assert payload["counts"]["context_filings"] == payload["counts"]["unsupported_context_forms"] == 4
    assert payload["counts"]["corroborated_noncanonical_filings"] == 1
    assert payload["counts"]["target_parent_corroboration_missing"] == 1
    assert payload["counts"]["quarantined_filings"] == 5
    assert len(payload["assessment"]["rows"]) == 6
    assert payload["assessment"]["rows"][2]["accession_year_mismatch"] is True
    assert payload["assessment"]["whole_quarter_identity_sha256"] is None
    assert payload["authority"] == module._authority()
    assert payload["parent_projection_ledger"][0]["projection"]["accepted_clock_verified"] is False
    assert b"<ownershipDocument>" not in result.canonical_bytes()
    assert b"Invented one-quarter issuer" not in result.canonical_bytes()


def test_both_target_forms_can_be_corroborated_context_stays_quarantined(supplied):
    payload = _assess(supplied, _inputs(supplied, selected=2)).to_payload()
    assert payload["counts"]["projected_complete_parents"] == 2
    assert payload["counts"]["corroborated_noncanonical_filings"] == 2
    assert payload["counts"]["quarantined_filings"] == 4
    assert payload["whole_quarter_identity_sha256"] is None


@pytest.mark.parametrize("kind", ["dtd", "entity", "namespace", "bom", "bad_owner", "bad_issuer", "malformed", "nested_owner"])
def test_unsupported_or_conflicting_xml_retains_parent_quarantine_and_full_denominator(supplied, kind):
    item = _inputs(supplied)[0];raw = item["raw_bytes"]
    if kind == "dtd":raw = raw.replace(b"<ownershipDocument>", b"<!DOCTYPE ownershipDocument><ownershipDocument>")
    elif kind == "entity":raw = raw.replace(b"<ownershipDocument>", b"<!ENTITY thing 'foo'><ownershipDocument>")
    elif kind == "namespace":raw = raw.replace(b"<ownershipDocument>", b"<ownershipDocument xmlns='urn:invented'>")
    elif kind == "bom":raw = raw.replace(b"<ownershipDocument>", b"\xef\xbb\xbf<ownershipDocument>")
    elif kind == "bad_owner":raw = raw.replace(b"<rptOwnerCik>0000999999", b"<rptOwnerCik>0000003333")
    elif kind == "bad_issuer":raw = raw.replace(b"<issuerCik>0000123456", b"<issuerCik>0000123457")
    elif kind == "nested_owner":raw = raw.replace(b"</ownershipDocument>", b"<wrapper><reportingOwner/></wrapper></ownershipDocument>")
    else:raw = raw.replace(b"</ownershipDocument>", b"<not-closed>")
    payload = _assess(supplied, (_changed(item, raw),)).to_payload()
    assert payload["counts"]["source_filings"] == payload["counts"]["quarantined_filings"] == 6
    assert payload["counts"]["grammar_quarantined_parents"] == 1
    assert payload["counts"]["target_parent_corroboration_missing"] == 2
    assert payload["parent_projection_ledger"][0]["projection"] is None


@pytest.mark.parametrize("terminal", ["planned_unattempted", "http_refused_no_retry", "ambiguous_transport_failure_no_retry",
    "response_privacy_framing_or_custody_refused_no_retry"])
def test_missing_refused_and_ambiguous_selected_parent_are_not_replaced_by_zero_or_dropped(supplied, terminal):
    item = _inputs(supplied)[0]
    missing = {**item, "raw_bytes": None, "body_sha256": None, "body_size_bytes": None,
        "header_identity_bound": False, "terminal_disposition": terminal,
        "result_sha256": None if terminal == "planned_unattempted" else "a" * 64}
    payload = _assess(supplied, (missing,)).to_payload()
    assert payload["counts"]["unavailable_selected_parents"] == 1
    assert payload["counts"]["target_parent_corroboration_missing"] == 2
    assert payload["counts"]["quarantined_filings"] == 6


@pytest.mark.parametrize("key,value", [("body_size_bytes", True), ("body_sha256", "a" * 64), ("prefix_ordinal", True),
    ("result_sha256", None), ("header_identity_bound", 1), ("terminal_disposition", "planned_unattempted")])
def test_rehashed_descriptor_type_or_lineage_forgeries_refused(supplied, key, value):
    item = {**_inputs(supplied)[0], key: value}
    with pytest.raises(module.EarlyParentProjectionError):_assess(supplied, (item,))


@pytest.mark.parametrize("key", ["source_record_ordinal", "filing_metadata_sha256", "quarterly_zip_sha256", "submission_member_sha256"])
def test_request_cannot_be_rebound_to_an_unrelated_source_row(supplied, key):
    item = _inputs(supplied)[0];request = dict(item["request"])
    request[key] = 4 if key == "source_record_ordinal" else "a" * 64
    altered = {**item, "request": request, "request_sha256": module._sha(module._raw(request))}
    with pytest.raises(module.EarlyParentProjectionError, match="parent_source_filing_binding_refused"):
        _assess(supplied, (altered,))


def test_caller_mutation_cannot_change_factory_bytes_or_grant_authority(supplied):
    result = _assess(supplied);payload = result.to_payload()
    payload["authority"]["backtesting_ready"] = True
    assert result.to_payload()["authority"]["backtesting_ready"] is False
    for changed in (replace(result), module.EarlyParentReassessment(result.canonical_bytes(), object())):
        with pytest.raises(module.EarlyParentProjectionError, match="genuine_unchanged_reassessment"):
            changed.to_payload()


def test_actual_profile_cannot_be_asserted_from_small_invented_corpus(supplied):
    snapshot, census, _ = supplied
    with pytest.raises(module.EarlyParentProjectionError, match="real_complete_quarter_population_required"):
        module.assess_supplied_early_parents(snapshot, census, _inputs(supplied),
            expected_capture_report_sha256="f" * 64, fixture_only=False)


def test_existing_v2_aggregate_body_bound_is_not_expanded_for_new_capture(supplied, monkeypatch):
    monkeypatch.setattr(module.identity_v2, "MAX_CORROBORATING_BYTES", 1)
    with pytest.raises(module.EarlyParentProjectionError, match="existing_v2_aggregate_parent_byte_bound"):_assess(supplied)


def test_zero_supplied_parent_still_replays_every_submission(supplied):
    payload = _assess(supplied, ()).to_payload()
    assert payload["counts"]["source_filings"] == payload["counts"]["quarantined_filings"] == 6
    assert payload["counts"]["selected_parents"] == 0
    assert payload["whole_quarter_identity_sha256"] is None


def test_parent_descriptor_count_and_duplicate_bounds_are_explicit(supplied):
    first = _inputs(supplied)[0]
    with pytest.raises(module.EarlyParentProjectionError, match="bounded_parent_descriptor_tuple"):_assess(supplied, (first,) * 65)
    with pytest.raises(module.EarlyParentProjectionError):_assess(supplied, (first, {**first, "prefix_ordinal": 1}))


def test_inactive_source_entry_refuses_before_any_real_identity_input_or_output_access(monkeypatch, capsys):
    monkeypatch.setattr(module, "__file__", str(LANE / "artifacts/insider_buying/development_drafts/inactive-projection.py"))
    monkeypatch.setattr(module.capture.bootstrap.custody, "_identity", lambda *_: pytest.fail("must not inspect real lane identity"))
    monkeypatch.setattr(module.capture, "_verify_original_committed_sources", lambda *_: pytest.fail("must not read actual capture"))
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: pytest.fail("must not create production output"))
    assert module.main(["--audit-id", "ib-2006q1-parent-projection-invented", "--expected-head", "a" * 40,
        "--expected-capture-report-sha256", "b" * 64]) == 2
    assert capsys.readouterr().out == '{"disposition":"offline_parent_projection_refused_outputs_preserved"}\n'


def test_declared_xml_profile_does_not_assert_source_timezone_or_financial_values():
    assert module.XML_PROFILE["clock_timezone_inferred"] is False
    assert module.XML_PROFILE["financial_values_interpreted"] is False
    assert module.XML_PROFILE["namespaces"] == "unsupported-quarantine"
    assert module.XML_PROFILE["source_acceptance_clock"].startswith("original-14-digit-source-declaration")


@pytest.mark.parametrize("key,value", [("issuer_cik", "0000123457"), ("form_type", "4/A"), ("filing_date", "2006-01-16")])
def test_rehashed_request_identity_drift_is_refused_before_xml_not_laundered_as_grammar_quarantine(supplied, key, value):
    item = _inputs(supplied)[0];request = {**item["request"], key: value}
    altered = {**item, "request": request, "request_sha256": module._sha(module._raw(request))}
    with pytest.raises(module.EarlyParentProjectionError, match="parent_source_filing_binding_refused"):
        _assess(supplied, (altered,))


def test_direct_filing_map_cannot_overwrite_duplicate_source_accession(supplied):
    snapshot, census, _ = supplied
    baseline = module.identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    duplicate = replace(snapshot, rows=(snapshot.rows[0], *snapshot.rows))
    with pytest.raises(module.EarlyParentProjectionError, match="duplicate_source_accession"):
        module._source_filings(duplicate, baseline)


def test_projection_worker_isolation_probes_require_fork_and_outside_write_denial(tmp_path, monkeypatch):
    output = tmp_path / "output";output.mkdir(mode=0o700)
    observed = []
    monkeypatch.setattr(module.capture.bootstrap.custody, "_effective_denial", lambda **kwargs: observed.append(kwargs))
    def denied(path, flags, mode):
        observed.append((path, flags, mode))
        raise PermissionError(errno.EPERM, "invented boundary denial")
    monkeypatch.setattr(module.os, "open", denied)
    module._prove_worker_isolation(output)
    assert observed[0] == {"require_fork": True}
    assert observed[1][0] == tmp_path / "output.outside-probe"
    assert observed[1][1] & (os.O_NOFOLLOW | os.O_EXCL | os.O_CREAT) == os.O_NOFOLLOW | os.O_EXCL | os.O_CREAT
    assert not (tmp_path / "output.outside-probe").exists()


def _summary():
    return {"audit_id": "ib-2006q1-parent-projection-invented", "fixture_only": False,
        **{key: "a" * 64 for key in ("complete_sha256", "assessment_sha256", "projection_ledger_sha256", "capture_report_sha256")},
        "counts": {"source_filings": 83657, "target_filings": 71679, "context_filings": 11978,
            "selected_parents": 64, "retained_parent_bodies": 64, "projected_complete_parents": 64,
            "grammar_quarantined_parents": 0, "unavailable_selected_parents": 0,
            "corroborated_noncanonical_filings": 64, "quarantined_filings": 83593,
            "target_parent_corroboration_missing": 71615, "source_parent_identity_conflicts": 0,
            "unsupported_context_forms": 11978, "retained_parent_bytes": 64000},
        "projection_refusal_counts": {code: 0 for code in module.PARSER_REFUSAL_CODES}, "authority": module._authority()}


@pytest.mark.parametrize("mutation", ["missing_counts", "extra_count"])
def test_public_worker_summary_requires_exact_count_vocabulary(mutation):
    value = _summary()
    if mutation == "missing_counts":value["counts"] = {}
    else:value["counts"]["made_up_count"] = 1
    with pytest.raises(module.EarlyParentProjectionError, match="worker_reassessment_summary_refused"):
        module._strict_summary(value, audit_id=value["audit_id"], report_sha=value["capture_report_sha256"])


@pytest.mark.parametrize("mutation", ["bool_count", "int_false_authority", "missing_authority", "bad_hash", "fixture_true"])
def test_public_worker_summary_refuses_typed_or_positive_authority(mutation):
    value = _summary()
    if mutation == "bool_count":value["counts"]["source_parent_identity_conflicts"] = False
    elif mutation == "int_false_authority":value["authority"]["backtesting_ready"] = 0
    elif mutation == "missing_authority":del value["authority"]["backtesting_ready"]
    elif mutation == "bad_hash":value["complete_sha256"] = "not-a-hash"
    else:value["fixture_only"] = True
    with pytest.raises(module.EarlyParentProjectionError):
        module._strict_summary(value, audit_id=value["audit_id"], report_sha=value["capture_report_sha256"])


def test_pure_composition_has_no_filesystem_or_provider_calls(supplied, monkeypatch):
    def refused(*args, **kwargs):pytest.fail("pure composition attempted filesystem/provider interaction")
    # Parsing and composition need supplied immutable metadata/body bytes only.
    monkeypatch.setattr(module.os, "open", refused)
    monkeypatch.setattr(module.subprocess, "run", refused)
    monkeypatch.setattr(module.capture, "_selected_sec_transport", refused)
    assert _assess(supplied).to_payload()["counts"]["source_filings"] == 6


@pytest.mark.parametrize("message,code", [
    ("REFUSED: XML declares a DTD or entity", "xml_security_profile_refused"),
    ("REFUSED: header and XML reporting-owner identities disagree", "header_xml_owner_identity_conflict"),
    ("REFUSED: XML form or issuer disagrees with target", "xml_target_identity_conflict"),
    ("REFUSED: XML namespace-qualified nodes are unsupported", "xml_dialect_refused"),
    ("REFUSED: XML is malformed", "xml_grammar_refused"),
    ("REFUSED: legacy acceptance time is invalid", "source_acceptance_clock_refused"),
    ("REFUSED: header issuer CIK disagrees with target", "header_target_identity_conflict"),
    ("REFUSED: SEC-DOCUMENT envelope disagrees with target or is incomplete", "sec_document_envelope_refused"),
    ("REFUSED: legacy header role indentation or leaf is malformed", "original_header_grammar_refused"),
    ("REFUSED: exactly one ownership XML document is required", "complete_document_inventory_refused"),
    ("REFUSED: complete submission has unsupported NUL or line endings", "source_body_encoding_or_bound_refused"),
    ("INVENTED PRIVATE SOURCE TEXT /no/such/source", "unsupported_original_complete_parent_grammar"),
])
def test_fixed_refusal_categories_do_not_serialize_exception_or_source_text(message, code):
    observed = module._parser_refusal_code(module.SecCompleteSubmissionError(message))
    assert observed == code and observed in module.PARSER_REFUSAL_CODES
    assert message not in observed


@pytest.mark.parametrize("mutate", ["unknown_code", "bool_value", "wrong_total"])
def test_worker_refusal_summary_has_fixed_codes_strict_counts_and_exact_partition(mutate):
    summary = _summary()
    if mutate == "unknown_code":summary["projection_refusal_counts"]["SOURCE TEXT"] = 0
    elif mutate == "bool_value":summary["projection_refusal_counts"]["xml_grammar_refused"] = False
    else:summary["projection_refusal_counts"]["xml_grammar_refused"] = 1
    with pytest.raises(module.EarlyParentProjectionError, match="worker_projection_refusal_summary_refused"):
        module._strict_summary(summary, audit_id=summary["audit_id"], report_sha=summary["capture_report_sha256"])


@pytest.mark.parametrize("http_status", [None, 403])
def test_sealed_capture_fixture_loader_replays_raw_or_refused_with_all_prefix_rows(tmp_path, http_status):
    response = None if http_status is None else module.capture.SecHttpResult(http_status, (), b"")
    result = _capture_fixture(tmp_path, response=response, capture_id=module.CAPTURE_ID)
    tree, rows, reservation, report = module._load_sealed_capture(result["report_sha256"], fixture_only=True, root=tmp_path)
    try:
        assert len(rows) == 64
        assert report["capture_execution_head"] == reservation["selection"]["repository_head"]
        assert [row["prefix_ordinal"] for row in rows] == list(range(64))
        if http_status is None:
            assert all(type(row["raw_bytes"]) is bytes for row in rows)
            assert all(row["body_sha256"] == module._sha(row["raw_bytes"]) for row in rows)
        else:
            assert rows[0]["terminal_disposition"] == "http_refused_no_retry"
            assert all(row["terminal_disposition"] == "planned_unattempted" and row["raw_bytes"] is None for row in rows[1:])
        tree.recheck()
    finally:tree.close()


def test_unsealed_fixture_capture_cannot_be_loaded_or_manufacture_report(tmp_path):
    namespace = tmp_path.joinpath(*module.capture.ARTIFACT_PARTS)
    run = namespace / "runs" / module.CAPTURE_ID
    for path in (namespace, namespace / "claims", namespace / "runs", run, run / "objects"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700);path.chmod(0o700)
    (namespace / "capture.lock").write_bytes(module.capture.LOCK_BYTES);(namespace / "capture.lock").chmod(0o600)
    (run / "reservation.json").write_bytes(b"{}");(run / "reservation.json").chmod(0o600)
    before = sorted(str(p.relative_to(namespace)) for p in namespace.rglob("*"))
    with pytest.raises((ValueError, OSError)):
        module._load_sealed_capture("a" * 64, fixture_only=True, root=tmp_path)
    assert sorted(str(p.relative_to(namespace)) for p in namespace.rglob("*")) == before
    assert not (run / "complete.json").exists()


@pytest.mark.parametrize("root", [LANE, LANE.parent, LANE / "artifacts/insider_buying/sec_2006q1_parent_capture_v1"])
def test_fixture_capture_reader_fence_precedes_real_capture_checks(root, monkeypatch):
    monkeypatch.setattr(module.capture, "_verify_capture", lambda *_args, **_kwargs: pytest.fail("must not inspect actual capture"))
    with pytest.raises(module.capture.EarlyParentCaptureError, match="fixture_root_transport_required"):
        module._load_sealed_capture("a" * 64, fixture_only=True, root=root)


def test_complete_quarter_baseline_rejects_duplicate_accessions_before_filing_map(supplied, monkeypatch):
    snapshot, census, _ = supplied
    from research.insider_buying.sec_bulk_parsed_snapshot import _source_row_id
    rows = list(snapshot.rows);source = rows[1];values = list(source.values)
    positions = {name: index for index, name in enumerate(snapshot.identity.tables[0].headers)}
    values[positions["ACCESSION_NUMBER"]] = rows[0].accession_number
    table = snapshot.identity.tables[0]
    duplicate = replace(source, accession_number=rows[0].accession_number, values=tuple(values), row_id=_source_row_id(
        raw_snapshot_id=snapshot.identity.raw_snapshot_id, raw_lineage_hash=snapshot.identity.raw_lineage_hash,
        raw_archive_sha256=snapshot.identity.raw_archive_sha256, table_name="SUBMISSION.tsv", raw_member_sha256=table.raw_member_sha256,
        source_record_ordinal=source.source_record_ordinal, values=tuple(values), source_row_key=()))
    rows[1] = duplicate
    updated = replace(table, row_ids_hash=module.hash_payload([row.row_id for row in rows if row.table_name == "SUBMISSION.tsv"]))
    identity = replace(snapshot.identity, tables=(updated, *snapshot.identity.tables[1:]), lineage_hash="", snapshot_id="")
    lineage = module.hash_payload(identity.lineage_payload())
    identity = replace(identity, lineage_hash=lineage, snapshot_id="sec-insider-parsed-2006q1-" + lineage[:16])
    altered = replace(snapshot, identity=identity, rows=tuple(rows))
    reached = []
    monkeypatch.setattr(module, "_source_filings", lambda *_: reached.append("map reached"))
    with pytest.raises(module.identity_v2.Ib1cIdentityV2Error) as error:
        module.assess_supplied_early_parents(altered, census, (), expected_capture_report_sha256="a" * 64, fixture_only=True)
    assert "repeats a SUBMISSION accession" in str(error.value.__cause__)
    assert reached == []


@pytest.mark.parametrize("key,value", [("source_filings", 83658), ("retained_parent_bodies", 63),
    ("corroborated_noncanonical_filings", 65), ("unsupported_context_forms", 0)])
def test_public_summary_cannot_change_population_or_complete_partition(key, value):
    summary = _summary();summary["counts"][key] = value
    with pytest.raises(module.EarlyParentProjectionError, match="worker_reassessment_count_partition_refused"):
        module._strict_summary(summary, audit_id=summary["audit_id"], report_sha=summary["capture_report_sha256"])


def test_source_only_bootstrap_executes_captured_fixture_bytes_without_filesystem_fallback():
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    fixture_code = b'''import json
def _worker(audit_id, **kwargs):
    return {"fixture_only": True, "audit_id": audit_id, "executed_sources": kwargs["executed_sources"]()}
def _raw(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
'''
    sources = {helper_path: module.isolation._read_source(helper_path),
        "research/__init__.py": b"", module.SELF_PATH: fixture_code}
    envelope = {"sources": [{"path": name, "sha256": module._sha(raw), "source_b64": base64.b64encode(raw).decode()}
        for name, raw in sorted(sources.items())], "parent_context": {"identity": {
            "source_sha256": {name: module._sha(raw) for name, raw in sources.items()}}, "frozen_sources": {}},
        "audit_id": "invented-source-only-probe", "expected_head": "a" * 40, "report_sha256": "b" * 64}
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP],
        cwd=LANE, input=module._raw(envelope), capture_output=True, check=False, timeout=30)
    assert child.returncode == 0, child.stderr.decode()
    output = json.loads(child.stdout)
    assert output["fixture_only"] is True and output["audit_id"] == "invented-source-only-probe"
    rows = output["executed_sources"]
    assert rows[0] == {"path": helper_path, "sha256": module._sha(sources[helper_path])}
    assert rows[-1] == {"path": module.SELF_PATH, "sha256": module._sha(fixture_code)}
    assert len(rows) == 3


def test_source_only_captured_worker_proves_os_denial_before_installing_python_audit_hook():
    # The child inherits this test process's effective OS network denial.
    # Do not nest a new Seatbelt profile inside an already denied test process.
    module.capture.bootstrap.custody._effective_denial(require_fork=False)
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    fixture_code = b'''import errno, json, socket, sys
from research import insider_buying_affected_quarter_isolation as helper
def _worker(audit_id, **kwargs):
    handle = None
    try:
        handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        handle.settimeout(0.2)
        handle.connect(("127.0.0.1", 9))
    except OSError as exc:
        assert exc.errno in {errno.EPERM, errno.EACCES}
    else:
        raise AssertionError("effective inherited OS denial not observed")
    finally:
        if handle is not None: handle.close()
    sys.addaudithook(helper._audit_event)
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except helper.AffectedQuarterIsolationError:
        audit_blocked = True
    else:
        raise AssertionError("late audit hook not effective")
    return {"fixture_only": True, "os_network_denial_observed": True,
            "late_audit_hook_observed": audit_blocked}
def _raw(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
'''
    sources = {helper_path: module.isolation._read_source(helper_path),
        "research/__init__.py": b"", module.SELF_PATH: fixture_code}
    envelope = {"sources": [{"path": name, "sha256": module._sha(raw), "source_b64": base64.b64encode(raw).decode()}
        for name, raw in sorted(sources.items())], "parent_context": {"identity": {
            "source_sha256": {name: module._sha(raw) for name, raw in sources.items()}}, "frozen_sources": {}},
        "audit_id": "invented-source-only-ordering-probe", "expected_head": "a" * 40, "report_sha256": "b" * 64}
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP],
        cwd=LANE, input=module._raw(envelope), capture_output=True, check=False, timeout=30)
    assert child.returncode == 0, child.stderr.decode()
    assert not child.stderr
    assert json.loads(child.stdout) == {"fixture_only": True, "os_network_denial_observed": True,
        "late_audit_hook_observed": True}


@pytest.mark.parametrize("mutation", ["unknown_source", "duplicate_source", "wrong_digest"])
def test_execution_inventory_cannot_assert_uncaptured_or_duplicate_code(mutation):
    names = [module.SELF_PATH, "research/insider_buying/sec_complete_submission.py", "research/insider_buying/sec_ib1c_identity_v2.py"]
    identity = {"source_sha256": {name: "a" * 64 for name in names}}
    rows = [{"path": name, "sha256": "a" * 64} for name in names]
    if mutation == "unknown_source":rows.append({"path": "research/NOT_CAPTURED.py", "sha256": "a" * 64})
    elif mutation == "duplicate_source":rows.append(rows[0])
    else:rows[0] = {**rows[0], "sha256": "b" * 64}
    with pytest.raises(module.EarlyParentProjectionError):module._source_execution_context(rows, identity)


@pytest.mark.parametrize("extra_newlines", [2, 3])
def test_isolated_parent_stdout_refuses_extra_newlines_before_summary_validation(
        tmp_path, monkeypatch, extra_newlines):
    identity = {"source_sha256": {}}
    seen = []
    output = SimpleNamespace(path=tmp_path, close=lambda: None,
        publish=lambda *_args, **_kwargs: "a" * 64)
    monkeypatch.setattr(module, "_fixed_source_identity", lambda *_: (identity, {}))
    monkeypatch.setattr(module.capture, "_verify_original_committed_sources", lambda *_: None)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: output)
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs:
        SimpleNamespace(returncode=0, stderr=b"", stdout=b"{}" + b"\n" * extra_newlines))
    def refused_summary(*args, **kwargs):
        seen.append(True)
        raise AssertionError("noncanonical worker wire reached summary validation")
    monkeypatch.setattr(module, "_strict_summary", refused_summary)
    with pytest.raises(module.capture.bootstrap.ParentBootstrapError, match="control_json_refused"):
        module.run_observed_reassessment("ib-2006q1-parent-projection-invented",
            expected_head="a" * 40, expected_capture_report_sha256="b" * 64)
    assert seen == []

