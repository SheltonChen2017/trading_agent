"""Invented complete controls and full all-form master images only."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_sec_locator_diagnostic as m
from research import insider_buying_pilot_sec_fresh_selection_runner as observer


HEADER = (b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Comments: metadata-only invented fixture\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("invented_locator_prior_fixture",
        Path(__file__).with_name("test_insider_buying_pilot_sec_fresh_selection.py"))
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper, helper.corpus.__wrapped__(tmp_path_factory)


def _case(corpus, monkeypatch, kind="absent", count=1):
    helper, data = corpus
    target = helper._pilot_targets(data)[0]
    target_accessions = {row["accession_number"] for row in helper._pilot_targets(data)[:count]}
    master_images = {}
    def full_master(period, source_rows, *, omit=()):
        lines = []
        for source in source_rows:
            if source["period"] != period:continue
            if source["accession_number"] in target_accessions:
                if kind == "absent":continue
                forms = (["5", "5"] if kind == "duplicate-other" else ["5"] if kind == "other-form"
                    else ["4", "4"] if kind in {"date", "aliases"} else ["4/A"])
                for index, form in enumerate(forms):
                    day = "2021-02-01" if kind == "date" else source["filing_date"]
                    folder = "998" if index and kind in {"date", "aliases"} else "999"
                    cik = "2" if index else "1"
                    company = b"OTHER \x83 METADATA" if index else b"INVENTED NAME"
                    lines.append(cik.encode() + b"|" + company + b"|" +
                        f"{form}|{day}|edgar/data/{folder}/{source['accession_number']}.txt\n".encode())
            else:
                lines.append(f"1|INVENTED|{source['form_type']}|{source['filing_date']}|edgar/data/999/{source['accession_number']}.txt\n".encode())
        raw = HEADER + b"".join(lines);master_images[period] = raw
        return m.master.parse_sec_quarter_master_index(raw, year=int(period[:4]), quarter=int(period[-1]))
    monkeypatch.setattr(helper, "_master", full_master)
    pipeline = helper._pipeline(data);chosen = helper._finish(pipeline)
    source, audit, emissions = pipeline[1:]
    quarantines = [row for row in emissions if row["relevant_parent_target"] and row["selected_locator"] is None]
    assert len(quarantines) == count
    selected = chosen.to_payload();qraw = b"".join(m._RAW(row) + b"\n" for row in quarantines)
    sources = {observer.SELF_PATH: "a" * 64}
    identity = {"root": "/invented/lane", "branch": "codex/strategy-insider-buying", "head": "a" * 40,
        "clean": True, "source_sha256": sources, "source_inventory_sha256": m._SHA(m._RAW(sources))}
    worker = {"schema": observer.SCHEMA, "audit_id": observer.AUDIT_ID, "registration": deepcopy(observer.REGISTRATION),
        "registration_sha256": m._SHA(m._RAW(observer.REGISTRATION)), "execution_identity": identity,
        "prior_audit_complete_sha256": observer.REGISTRATION["prior_audit_pins"]["complete.json"]["sha256"],
        "exposure_inventory_sha256": selected["exposure_inventory_sha256"], "exposure_snapshot_sha256": "e" * 64,
        "retained_body_inventory_sha256": selected["retained_candidate_inventory_sha256"], "selection": selected,
        "selection_sha256": chosen.sha256, "source_roster": source.to_payload(), "parent_audit": audit.to_payload(),
        "locator_quarantines": quarantines, "locator_quarantine_jsonl_sha256": m._SHA(qraw),
        "locator_quarantine_jsonl_bytes": len(qraw), "native_network_fork_allwrite_securityexec_denial": True,
        "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
        "dispatch_authorized": False, "canonical_admitted": False, "backtesting_ready": False}
    complete = {"schema": observer.SCHEMA + "/complete", "audit_id": observer.AUDIT_ID,
        "reservation_sha256": "a" * 64, "terminal_sha256": "b" * 64, "worker_result": worker}
    master_raw = master_images[target["period"]]
    receipt = m.master.parse_sec_quarter_master_index(master_raw, year=2021, quarter=1)
    return SimpleNamespace(complete=complete, row=quarantines[0], master_raw=master_raw, receipt=receipt,
        expected_complete_sha=m._SHA(m._RAW(complete)), expected_row_sha=m._SHA(m._RAW(quarantines[0])))


def _arguments(case):
    return {"master_decoded_raw": case.master_raw, "expected_master_decoded_sha256": m._SHA(case.master_raw),
        "expected_master_receipt_sha256": case.receipt.receipt_sha256,
        "selection_complete_raw": m._RAW(case.complete), "expected_selection_complete_sha256": case.expected_complete_sha,
        "quarantine_index": 0, "expected_quarantine_sha256": case.expected_row_sha}


def _run(case, **changes):
    arguments = _arguments(case);arguments.update(changes)
    return m.assess_pilot_sec_locator_quarantine(**arguments)


def _batch(case, **changes):
    arguments = {"master_inputs": ({"period": "2021Q1", "decoded_raw": case.master_raw,
        "expected_decoded_sha256": m._SHA(case.master_raw), "expected_receipt_sha256": case.receipt.receipt_sha256},),
        "selection_complete_raw": m._RAW(case.complete), "expected_selection_complete_sha256": case.expected_complete_sha,
        "expected_quarantine_sha256s": tuple(m._SHA(m._RAW(row)) for row in case.complete["worker_result"]["locator_quarantines"])}
    arguments.update(changes)
    return m.assess_pilot_sec_locator_quarantines(**arguments)


def test_batch_scans_master_once_for_all_same_quarter_quarantines(corpus, monkeypatch):
    case = _case(corpus, monkeypatch, count=8)
    parse = m.master.parse_sec_quarter_master_index;calls = []
    def counted(*args, **kwargs):
        calls.append(kwargs);return parse(*args, **kwargs)
    monkeypatch.setattr(m.master, "parse_sec_quarter_master_index", counted)
    value = _batch(case);body = value.to_payload()
    assert len(calls) == body["master_scan_count"] == 1
    assert body["quarantine_count"] == body["pilot_quarantine_count"] == len(body["reports"]) == 8
    assert [r["quarantine_index"] for r in body["reports"]] == list(range(8))
    assert m.validate_locator_diagnostic_batch_payload(body) == body
    assert all(r["classification"] == "accession_absent_from_supplied_full_quarter_master" for r in body["reports"])


@pytest.mark.parametrize("fault", ["missing_pin", "wrong_pin", "reordered_pin", "extra_master", "wrong_period", "wrong_master_pin", "list_inputs"])
def test_batch_exact_roster_membership_and_external_pins(corpus, monkeypatch, fault):
    case = _case(corpus, monkeypatch, count=2);rows = case.complete["worker_result"]["locator_quarantines"]
    pins = tuple(m._SHA(m._RAW(row)) for row in rows)
    item = {"period": "2021Q1", "decoded_raw": case.master_raw, "expected_decoded_sha256": m._SHA(case.master_raw),
        "expected_receipt_sha256": case.receipt.receipt_sha256}
    changes = {}
    if fault == "missing_pin": changes["expected_quarantine_sha256s"] = pins[:1]
    if fault == "wrong_pin": changes["expected_quarantine_sha256s"] = ("f" * 64, pins[1])
    if fault == "reordered_pin": changes["expected_quarantine_sha256s"] = pins[::-1]
    if fault == "extra_master": changes["master_inputs"] = (item, item)
    if fault == "wrong_period": item["period"] = "2021Q2";changes["master_inputs"] = (item,)
    if fault == "wrong_master_pin": item["expected_receipt_sha256"] = "f" * 64;changes["master_inputs"] = (item,)
    if fault == "list_inputs": changes["master_inputs"] = [item]
    with pytest.raises(m.PilotSecLocatorDiagnosticError): _batch(case, **changes)


@pytest.mark.parametrize("fault", ["authority", "typed_zero", "membership", "master_scan_count", "master_conflict", "physical_order", "line_hash", "classification"])
def test_serialized_batch_refuses_laundered_authority_counts_and_lossless_metadata(corpus, monkeypatch, fault):
    body = _batch(_case(corpus, monkeypatch, kind="other-form", count=2)).to_payload()
    if fault == "authority": body["backtesting_ready"] = True
    if fault == "typed_zero": body["credential_reads"] = False
    if fault == "membership": body["reports"][1]["quarantine_index"] = 0
    if fault == "master_scan_count": body["master_scan_count"] = 2
    if fault == "master_conflict": body["reports"][1]["master"]["decoded_sha256"] = "f" * 64
    if fault == "physical_order": body["reports"][0]["matching_rows"][0]["all_filing_row_ordinal"] = 0
    if fault == "line_hash": body["reports"][0]["matching_rows"][0]["raw_columns"]["Company Name"] += "CHANGED"
    if fault == "classification": body["reports"][0]["classification"] = "canonical_admitted"
    lines = b"".join(m._RAW(row) + b"\n" for row in body["reports"])
    body.update(reports_jsonl_sha256=m._SHA(lines), reports_jsonl_bytes=len(lines))
    with pytest.raises(m.PilotSecLocatorDiagnosticError): m.validate_locator_diagnostic_batch_payload(body)


@pytest.mark.parametrize("kind,classification,count", [
    ("absent", "accession_absent_from_supplied_full_quarter_master", 0),
    ("other-form", "accession_present_only_under_other_forms", 1),
    ("duplicate-other", "accession_present_only_under_other_forms", 2),
    ("date", "ownership_filing_date_disagreement", 2),
    ("form", "ownership_form_disagreement", 1),
    ("aliases", "ownership_aliases_not_uniquely_resolved", 2)])
def test_exact_full_master_classification_is_diagnostic_not_a_repaired_locator(corpus, monkeypatch, kind, classification, count):
    case = _case(corpus, monkeypatch, kind);result = _run(case);body = result.to_payload()
    assert m.validate_pilot_sec_locator_diagnostic(result) is result
    assert body["classification"] == classification and body["matching_row_count"] == len(body["matching_rows"]) == count
    assert body["master"]["decoded_sha256"] == m._SHA(case.master_raw)
    assert body["master"]["parsed_receipt_sha256"] == case.receipt.receipt_sha256
    assert body["master"]["all_filing_row_count"] == case.receipt.all_filing_row_count
    assert sum(body["master"]["all_form_counts"].values()) == case.receipt.all_filing_row_count
    assert body["source_record"] == case.row["source"] and body["quarantine_row"] == case.row
    assert body["prior_selection_complete_sha256"] == case.expected_complete_sha and body["quarantine_sha256"] == case.expected_row_sha
    assert body["authority"] == m.audit._AUTHORITY
    for key in ("original_body_requested", "original_body_admitted", "canonical_request_constructed",
            "source_quarantine_rewritten", "source_or_custody_authenticated_here", "protected_prior_execution_replayed_here",
            "official_availability_or_pit_established", "financial_numeric_values_interpreted",
            "dispatch_authorized", "canonical_admitted", "backtesting_ready"):
        assert body[key] is False
    for key in ("new_provider_requests", "credential_reads", "qc_jobs", "outcome_looks", "backtests"):
        assert type(body[key]) is int and body[key] == 0
    assert "request" not in body and body["fixture_only"] is True


def test_other_form_duplicate_rows_preserve_each_original_column_and_physical_ordinal(corpus, monkeypatch):
    body = _run(_case(corpus, monkeypatch, "duplicate-other")).to_payload()
    first, second = body["matching_rows"]
    assert first["raw_columns"]["Filename"] == second["raw_columns"]["Filename"]
    assert first["raw_columns"]["CIK"] == "1" and second["raw_columns"]["CIK"] == "2"
    assert first["raw_columns"]["Company Name"] == "INVENTED NAME" and second["raw_columns"]["Company Name"] == "OTHER ƒ METADATA"
    assert first["all_filing_row_ordinal"] < second["all_filing_row_ordinal"]
    for row in (first, second):
        fields = row["raw_columns"]
        raw = b"|".join(fields[key].encode("cp1252" if key == "Company Name" else "ascii") for key in m.COLUMNS)
        assert row["raw_five_column_line_sha256"] == m._SHA(raw)
        assert row["raw_five_column_line_bytes"] == len(raw)
    assert body["matching_form_counts"] == {"5": 2}


def test_date_conflict_preserves_source_date_and_every_master_alias_without_guess(corpus, monkeypatch):
    case = _case(corpus, monkeypatch, "date");body = _run(case).to_payload()
    assert body["source_record"]["filing_date"] == "2021-01-01"
    assert {row["raw_columns"]["Date Filed"] for row in body["matching_rows"]} == {"2021-02-01"}
    assert {row["raw_columns"]["Filename"].split("/")[2] for row in body["matching_rows"]} == {"998", "999"}
    assert body["prior_quarantine_reason"] == "master_filing_date_disagreement"
    assert body["source_record"]["raw_issuer_cik"] == "123"


@pytest.mark.parametrize("fault", ["master_pin", "receipt_pin", "complete_pin", "row_pin", "index_bool", "index_negative",
    "index_high", "master_mutable", "complete_mutable", "master_empty", "complete_empty"])
def test_external_pins_exact_types_and_membership_cannot_be_replaced(corpus, monkeypatch, fault):
    case = _case(corpus, monkeypatch);changes = {}
    if fault == "master_pin":changes["expected_master_decoded_sha256"] = "f" * 64
    if fault == "receipt_pin":changes["expected_master_receipt_sha256"] = "f" * 64
    if fault == "complete_pin":changes["expected_selection_complete_sha256"] = "f" * 64
    if fault == "row_pin":changes["expected_quarantine_sha256"] = "f" * 64
    if fault == "index_bool":changes["quarantine_index"] = False
    if fault == "index_negative":changes["quarantine_index"] = -1
    if fault == "index_high":changes["quarantine_index"] = 1
    if fault == "master_mutable":changes["master_decoded_raw"] = bytearray(case.master_raw)
    if fault == "complete_mutable":changes["selection_complete_raw"] = bytearray(m._RAW(case.complete))
    if fault == "master_empty":changes["master_decoded_raw"] = b""
    if fault == "complete_empty":changes["selection_complete_raw"] = b""
    with pytest.raises(m.PilotSecLocatorDiagnosticError):_run(case, **changes)


@pytest.mark.parametrize("change", [
    lambda c:c.update(unexpected=True),lambda c:c.update(schema="old-complete-schema"),
    lambda c:c["worker_result"].update(qc_accesses=1),lambda c:c["worker_result"].update(credential_reads=False),
    lambda c:c["worker_result"].update(backtesting_ready=True),
    lambda c:c["worker_result"].update(registration_sha256="f"*64),
    lambda c:c["worker_result"]["execution_identity"].update(clean=False),
    lambda c:c["worker_result"].update(selection_sha256="f"*64),
    lambda c:c["worker_result"].update(locator_quarantine_jsonl_sha256="f"*64),
    lambda c:c["worker_result"]["locator_quarantines"][0].update(source_record_sha256="f"*64),
    lambda c:c["worker_result"]["locator_quarantines"][0].update(prior_consumed=True),
    lambda c:c["worker_result"]["locator_quarantines"][0].update(historical_ambiguous_start_preserved=True),
    lambda c:c["worker_result"]["locator_quarantines"][0].update(dispatch_authorized=True)])
def test_bound_but_malformed_whole_control_or_source_row_is_not_factory_admission(corpus, monkeypatch, change):
    case = _case(corpus, monkeypatch);change(case.complete)
    # This adversarial fixture gives its altered outer bytes a fresh external
    # pin so schema and source checks, not just the old hash mismatch, execute.
    case.expected_complete_sha = m._SHA(m._RAW(case.complete))
    with pytest.raises(m.PilotSecLocatorDiagnosticError):_run(case)


@pytest.mark.parametrize("fault", ["bad_header", "bad_unrelated_row", "wrong_quarter", "duplicate_target", "mixed_newline"])
def test_entire_master_integrity_is_required_not_only_matching_accession(corpus, monkeypatch, fault):
    case = _case(corpus, monkeypatch, "date");raw = case.master_raw
    if fault == "bad_header":raw = raw.replace(b"Master Index", b"Other Index", 1)
    if fault == "bad_unrelated_row":raw += b"1|PRIVATE INVALID UNRELATED ROW|8-K|2021-01-01|../invalid.txt\n"
    if fault == "wrong_quarter":raw = raw.replace(b"2021-02-01", b"2021-04-01")
    if fault == "duplicate_target":
        raw += next(line+b"\n" for line in raw.splitlines() if b"edgar/data/999/"+case.row["source"]["accession_number"].encode() in line)
    if fault == "mixed_newline":raw = raw.replace(b"\n", b"\r\n", 1)
    with pytest.raises(m.PilotSecLocatorDiagnosticError):
        _run(case, master_decoded_raw=raw, expected_master_decoded_sha256=m._SHA(raw))


def test_prior_quarantine_cannot_be_silently_repaired_by_a_different_valid_master(corpus, monkeypatch):
    case = _case(corpus, monkeypatch, "absent");source = case.row["source"]
    extra = f"1|INVENTED|4|{source['filing_date']}|edgar/data/123/{source['accession_number']}.txt\n".encode()
    raw = case.master_raw+extra
    receipt = m.master.parse_sec_quarter_master_index(raw, year=2021, quarter=1)
    with pytest.raises(m.PilotSecLocatorDiagnosticError, match="prior_master_alias_or_reason_changed"):
        _run(case, master_decoded_raw=raw, expected_master_decoded_sha256=m._SHA(raw),
            expected_master_receipt_sha256=receipt.receipt_sha256)


@pytest.mark.parametrize("guard,value", [("MAX_MATCHING_ROWS",1),("MAX_FORM_TYPES",1),("MAX_RESULT_BYTES",10),("MAX_COMPLETE_BYTES",10)])
def test_finite_bounds_refuse_whole_diagnostic_without_truncating_metadata(corpus, monkeypatch, guard, value):
    case = _case(corpus, monkeypatch, "duplicate-other");monkeypatch.setattr(m, guard, value)
    with pytest.raises(m.PilotSecLocatorDiagnosticError):_run(case)


def test_fake_master_receipt_cannot_be_used_even_with_a_shape_compatible_payload(corpus, monkeypatch):
    case = _case(corpus, monkeypatch)
    fake = SimpleNamespace(source_sha256=m._SHA(case.master_raw), receipt_sha256=case.receipt.receipt_sha256,
        source_size_bytes=len(case.master_raw))
    monkeypatch.setattr(m.master, "parse_sec_quarter_master_index", lambda *_a,**_k:fake)
    with pytest.raises(m.PilotSecLocatorDiagnosticError, match="genuine_master_receipt"):_run(case)


def test_factory_registry_rejects_reconstruction_and_returned_metadata_is_detached(corpus, monkeypatch):
    value = _run(_case(corpus, monkeypatch));raw = value.canonical_bytes()
    body = value.to_payload();body["authority"]["dispatch_enabled"] = True
    assert value.canonical_bytes() == raw and value.sha256 == m._SHA(raw)
    for fake in (replace(value),m.PilotSecLocatorDiagnostic(raw,object()),SimpleNamespace(canonical_bytes=lambda:raw),body):
        with pytest.raises(m.PilotSecLocatorDiagnosticError):m.validate_pilot_sec_locator_diagnostic(fake)


def test_unexpected_parser_exception_never_leaks_supplied_source_text(corpus, monkeypatch):
    case = _case(corpus, monkeypatch)
    def refusal(*_a,**_k):raise ValueError("PRIVATE SOURCE CONTACT AND RECORD")
    monkeypatch.setattr(m.master,"parse_sec_quarter_master_index",refusal)
    with pytest.raises(m.PilotSecLocatorDiagnosticError,match="^locator_supplied_metadata_refused$"):_run(case)
