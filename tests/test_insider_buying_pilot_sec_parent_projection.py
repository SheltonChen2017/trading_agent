"""Invented inputs only, under external native network/Keychain denial."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX custody")
pytest.importorskip("termios", reason="private-contact producer import")
from research import insider_buying_pilot_sec_parent_projection as m

sys.path.insert(0, str(Path(__file__).parent))
from test_insider_buying_pilot_sec_parent_capture import _request, _body, _run as _capture_run, _selection as _capture_selection
from test_insider_buying_sec_complete_submission import _complete, _header, _xml


def _input(index=1, raw=None):
    request = _request(index)
    raw = _body(request) if raw is None else raw
    return {"ordinal": index - 1, "request": request, "request_sha256": m._sha(m._raw(request)),
        "result_sha256": "b" * 64, "start_sha256": "c" * 64, "claim_sha256": "d" * 64,
        "raw_bytes": raw, "body_sha256": m._sha(raw), "body_size_bytes": len(raw)}


def _rebody(item, raw):
    item = deepcopy(item)
    item.update(raw_bytes=raw, body_sha256=m._sha(raw), body_size_bytes=len(raw))
    return item


def _identity(*, original=False):
    sources = {m.capture.SELF_PATH: m.CAPTURE_SOURCE_SHA256, m.capture.TEST_PATH: m.CAPTURE_TEST_SHA256,
        **m.base.FROZEN}
    if not original:
        sources.update({m.SELF_PATH: "e" * 64, m.TEST_PATH: "f" * 64})
    return {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH,
        "head": m.CAPTURE_HEAD if original else "d" * 40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}


def _controls(monkeypatch):
    """Real-sized controls with invented requests; no production factory seal."""
    identity = _identity(original=True)
    rows = [{"request": _request(i), "request_sha256": m._sha(m._raw(_request(i)))} for i in range(1, 65)]
    selection = {"fixture_only": False, "requests": rows, "invented_fixture_only": True}
    monkeypatch.setattr(m.capture, "ACTUAL_SELECTION_SHA256", m._sha(m._raw(selection)))
    checked = []
    monkeypatch.setattr(m.capture.fresh, "validate_selection_payload", lambda value: checked.append(deepcopy(value)))
    reservation = {"capture_execution_identity": identity, "schema": m.capture.SCHEMA + "/reservation",
        "capture_id": m.capture.CAPTURE_ID, "fixture_only": False, "selection": selection,
        "selection_sha256": m._sha(m._raw(selection)), "selection_execution_head": m.capture.ACTUAL_SELECTION_HEAD,
        "authority": dict(m.capture.audit._AUTHORITY)}
    report = {"capture_execution_identity": identity, "schema": m.capture.SCHEMA + "/complete",
        "capture_id": m.capture.CAPTURE_ID, "fixture_only": False, "capture_completed_without_refusal": True,
        "reservation_sha256": m._sha(m._raw(reservation)), "selection_sha256": m._sha(m._raw(selection)),
        "selection_execution_head": m.capture.ACTUAL_SELECTION_HEAD,
        "planned_requests": 64, "started_requests": 64, "permanent_claims_created": 64,
        "terminal_result_records": 64, "raw_bodies_retained": 64, "header_bound_bodies": 64,
        "header_quarantined_bodies": 0, "retained_body_bytes": m.ACTUAL_BODY_BYTES,
        "planned_unclaimed_unattempted": 0, "full_xml_projection_attempts": 0,
        "authority": dict(m.capture.audit._AUTHORITY), "old_roots_written": False, "results": [{} for _ in rows]}
    return report, reservation, checked


def _worker_result(monkeypatch):
    report, reservation, _ = _controls(monkeypatch)
    inputs, witnesses = [], []
    for ordinal, selected in enumerate(reservation["selection"]["requests"]):
        item = _input(ordinal + 1)
        claim = {"request": selected, "reservation_sha256": report["reservation_sha256"]}
        cr = m._raw(claim)
        start = {"claim_sha256": m._sha(cr), "request_sha256": item["request_sha256"],
            "reservation_sha256": report["reservation_sha256"]}
        sr = m._raw(start)
        finish = {"request_sha256": item["request_sha256"], "start_sha256": m._sha(sr),
            "body_retained": True, "header_identity_bound": True,
            "body_sha256": item["body_sha256"], "body_size_bytes": item["body_size_bytes"]}
        rr = m._raw(finish)
        report["results"][ordinal] = {"result_name": f"request-{ordinal:03d}-result.json", "result_sha256": m._sha(rr)}
        item.update(claim_sha256=m._sha(cr), start_sha256=m._sha(sr), result_sha256=m._sha(rr))
        inputs.append(item)
        witnesses.append({"result": rr.hex(), "start": sr.hex(), "claim": cr.hex()})
    total = sum(item["body_size_bytes"] for item in inputs)
    report["retained_body_bytes"] = total
    monkeypatch.setattr(m, "ACTUAL_BODY_BYTES", total)
    report_raw = m._raw(report)
    monkeypatch.setattr(m, "CAPTURE_REPORT_SHA256", m._sha(report_raw))
    # Default arguments stay literal in production. This pure helper routes
    # only invented controls to the explicit test hash, never real paths.
    original_check = m._original_controls
    monkeypatch.setattr(m, "_original_controls", lambda rr, sr: original_check(rr, sr, expected_report_sha256=m._sha(report_raw)))
    assessment = m.assess_supplied_pilot_parents(tuple(inputs))
    original = reservation["capture_execution_identity"]
    return {"schema": m.SCHEMA, "audit_id": m.AUDIT_ID, "registration": deepcopy(m.REGISTRATION),
        "registration_sha256": m._sha(m._raw(m.REGISTRATION)), "execution_identity": _identity(),
        "capture_source_inventory_sha256": original["source_inventory_sha256"], "capture_source_count": len(original["source_sha256"]),
        "capture_report_sha256": m.CAPTURE_REPORT_SHA256, "assessment": assessment,
        "assessment_sha256": m._sha(m._raw(assessment)), "original_control_witness": {
            "report": report_raw.hex(), "reservation": m._raw(reservation).hex(), "rows": witnesses},
        "native_network_fork_allwrite_securityexec_denial": True, "new_provider_requests": 0,
        "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
        "original_namespace_mutated": False, "persistent_result_published": False,
        "canonical_admitted": False, "backtesting_ready": False}


def _rehash_assessment(result):
    assessment = result["assessment"]
    assessment["ordered_rows_sha256"] = m._sha(m._raw(assessment["rows"]))
    result["assessment_sha256"] = m._sha(m._raw(assessment))


def test_exact_original_children_are_bound_and_raw_acceptance_not_promoted():
    item = _input()
    result = m.assess_supplied_pilot_parents((item,))
    row = result["rows"][0]
    assert result["counts"] == {"selected": 1, "projected": 1, "quarantined": 0, "raw_parent_bytes": len(item["raw_bytes"])}
    assert row["target"]["issuer_cik"] == "0000123456"
    assert "/987654/" in row["target"]["complete_submission_url"]
    p = row["projection"]
    assert p["accepted_at_raw_uninterpreted"] == "20210104101112"
    assert p["reporting_owner_count"] == 1 and p["header_xml_owner_sets_agree"] is True
    assert p["amendment_lineage_status"] == "original_as_filed"
    for child in (p["header"], p["primary_xml"]):
        raw = item["raw_bytes"][child["parent_byte_offset"]:child["parent_byte_offset"] + child["size_bytes"]]
        assert m._sha(raw) == child["sha256"]
    assert result["ordered_rows_sha256"] == m._sha(m._raw(result["rows"]))
    assert not result["acceptance_timezone_interpreted"] and not result["financial_values_interpreted"]
    assert b"Invented Owner" not in m._raw(result) and b"<ownershipDocument>" not in m._raw(result)
    assert not result["complete_pilot_corpus"] and not result["backtesting_ready"]


def test_crlf_and_decimal_lexemes_are_untouched_not_financially_parsed():
    item = _input()
    raw = item["raw_bytes"].replace(b"</ownershipDocument>", b"<nonDerivativeTable><nonDerivativeTransaction>"
        b"<transactionAmounts><transactionShares><value>9007199254740993.00000000000000001</value>"
        b"</transactionShares><transactionPricePerShare><value>NaN</value></transactionPricePerShare>"
        b"</transactionAmounts></nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>")
    raw = raw.replace(b"\n", b"\r\n")
    result = m.assess_supplied_pilot_parents((_rebody(item, raw),))
    assert result["counts"]["projected"] == 1
    p = result["rows"][0]["projection"]
    child = p["primary_xml"]
    xml = raw[child["parent_byte_offset"]:child["parent_byte_offset"] + child["size_bytes"]]
    assert b"9007199254740993.00000000000000001" in xml and b"NaN" in xml
    assert m._sha(xml) == child["sha256"]
    assert b"9007199254740993" not in m._raw(result) and p["financial_values_interpreted"] is False


def test_multi_owner_header_xml_identity_is_retained_not_replicated_as_buyers():
    request = _request(1)
    raw = _complete(owners=("0000999999", "0000888888")).replace(b"0000999999-22-000001", request["accession_number"].encode()).replace(b"20221107", b"20210104")
    row = m.assess_supplied_pilot_parents((_input(raw=raw),))["rows"][0]
    assert row["projection"]["reporting_owner_count"] == 2
    assert row["projection"]["header_owner_ciks_sha256"] == m._sha(m._raw(["0000999999", "0000888888"]))


def test_amendment_is_structurally_retained_without_guessing_original_accession():
    item = _input()
    item["request"]["form_type"] = "4/A"
    item["request_sha256"] = m._sha(m._raw(item["request"]))
    raw = item["raw_bytes"].replace(b"FORM TYPE:\t4\n", b"FORM TYPE:\t4/A\n").replace(
        b"CONFORMED SUBMISSION TYPE:\t4\n", b"CONFORMED SUBMISSION TYPE:\t4/A\n").replace(
        b"<TYPE>4\n", b"<TYPE>4/A\n").replace(b"<documentType>4</documentType>", b"<documentType>4/A</documentType>")
    row = m.assess_supplied_pilot_parents((_rebody(item, raw),))["rows"][0]
    assert row["projection"]["amendment_lineage_status"] == "unresolved_not_inferred"
    assert "amends_accession" not in row["projection"]


@pytest.mark.parametrize("old,new", ((b"<issuerCik>0000123456</issuerCik>", b"<issuerCik>0000987654</issuerCik>"),
    (b"<rptOwnerCik>0000999999</rptOwnerCik>", b"<rptOwnerCik>0000888888</rptOwnerCik>"),
    (b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"),
    (b"FILED AS OF DATE:\t20210104", b"FILED AS OF DATE:\t20210105"),
    (b"<SEC-DOCUMENT>0000000123-21-000001.txt", b"<SEC-DOCUMENT>0000000123-21-000002.txt"),
    (b"<ownershipDocument>", b"<otherDocument>"),
    (b"<ownershipDocument>", b"<!DOCTYPE ownershipDocument><ownershipDocument>"),
    (b"<ownershipDocument>", b"<ownershipDocument xmlns='urn:invented'>"),
    (b"</ownershipDocument>", b""),
    (b"<ACCEPTANCE-DATETIME>20210104101112", b"<ACCEPTANCE-DATETIME>20210230101112")))
def test_structural_and_source_identity_conflicts_quarantine_without_raw_error(old, new):
    item = _input()
    assert old in item["raw_bytes"]
    result = m.assess_supplied_pilot_parents((_rebody(item, item["raw_bytes"].replace(old, new)),))
    assert result["counts"]["quarantined"] == 1 and result["counts"]["projected"] == 0
    assert result["rows"][0]["projection"] is None
    assert result["rows"][0]["quarantine_code"] == "unsupported_or_conflicting_complete_submission_structure"


def test_exact_expected_issuer_is_bulk_request_not_derived_header_or_directory():
    item = _input()
    item["request"]["issuer_cik"] = "987654"
    item["request_sha256"] = m._sha(m._raw(item["request"]))
    result = m.assess_supplied_pilot_parents((item,))
    assert result["counts"]["quarantined"] == 1
    assert result["rows"][0]["target"]["issuer_cik"] == "0000987654"


def test_second_primary_xml_and_duplicate_document_sequence_are_quarantined():
    item = _input()
    document = item["raw_bytes"].split(b"<DOCUMENT>", 1)[1].split(b"</DOCUMENT>", 1)[0]
    raw = item["raw_bytes"].replace(b"</SEC-DOCUMENT>", b"<DOCUMENT>" + document + b"</DOCUMENT>\n</SEC-DOCUMENT>")
    result = m.assess_supplied_pilot_parents((_rebody(item, raw),))
    assert result["counts"]["quarantined"] == 1


def test_valid_parent_with_xml_echo_in_nonxml_attachment_quarantines_only_that_row():
    item = _input()
    accepted = m.project_sec_complete_submission(m._target(item["request"]), item["raw_bytes"])
    extra = (b"<DOCUMENT>\n<TYPE>EX-99\n<SEQUENCE>2\n<FILENAME>attachment.txt\n<TEXT>\n"
        + accepted.xml_bytes + b"</TEXT>\n</DOCUMENT>\n")
    raw = item["raw_bytes"].replace(b"PUBLIC DOCUMENT COUNT:\t1\n", b"PUBLIC DOCUMENT COUNT:\t2\n").replace(
        b"</SEC-DOCUMENT>\n", extra + b"</SEC-DOCUMENT>\n")
    assert m.project_sec_complete_submission(m._target(item["request"]), raw).xml_bytes == accepted.xml_bytes
    assert raw.count(accepted.xml_bytes) == 2
    result = m.assess_supplied_pilot_parents((_rebody(item, raw), _input(2)))
    assert result["counts"] == {"selected": 2, "projected": 1, "quarantined": 1,
        "raw_parent_bytes": len(raw) + len(_input(2)["raw_bytes"])}
    assert result["rows"][0]["projection"] is None and result["rows"][1]["projection"] is not None


def test_all64_rows_remain_in_order_with_complete_byte_refusal_conservation():
    items = tuple(_input(i) for i in range(1, 65))
    items = tuple(_rebody(item, item["raw_bytes"].replace(b"</ownershipDocument>", b"")) if i % 2 else item for i, item in enumerate(items))
    result = m.assess_supplied_pilot_parents(items)
    assert result["counts"] == {"selected": 64, "projected": 32, "quarantined": 32,
        "raw_parent_bytes": sum(len(item["raw_bytes"]) for item in items)}
    assert [row["ordinal"] for row in result["rows"]] == list(range(64))


def _held_fixture(tmp_path, monkeypatch):
    # Exercise actual held-I/O/64-body composition only on a newly generated
    # invented capture. Its original pure-control contract is tested above;
    # production pins/factory are never rebound to permit this test root.
    _capture_run(tmp_path, selection=_capture_selection(64))
    run = tmp_path.joinpath(*m.capture.ARTIFACT_PARTS, "runs", m.capture.CAPTURE_ID)
    report, reservation = (m.capture._decode((run / name).read_bytes()) for name in ("complete.json", "reservation.json"))
    verify = m.capture._verify_capture
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m, "ACTUAL_BODY_BYTES", report["retained_body_bytes"])
    monkeypatch.setattr(m, "_original_controls", lambda rr, sr: (_identity(original=True), report, reservation["selection"]))
    monkeypatch.setattr(m.capture, "_verify_capture", lambda **kw: verify(root=tmp_path,
        expected_report_sha256=m._sha((run / "complete.json").read_bytes()), fixture_only=True))
    return m._HeldCapture(), run


def test_held_original_namespace_and_all64_actual_code_paths_use_invented_files_only(tmp_path, monkeypatch):
    held, run = _held_fixture(tmp_path, monkeypatch)
    try:
        before = {str(path.relative_to(tmp_path)): m._sha(path.read_bytes()) for path in tmp_path.rglob("*") if path.is_file()}
        assessment, witness = held.project()
        assert assessment["counts"]["selected"] == assessment["counts"]["projected"] == 64
        assert assessment["counts"]["raw_parent_bytes"] == m.ACTUAL_BODY_BYTES
        assert len(witness["rows"]) == 64 and witness["report"] == (run / "complete.json").read_bytes().hex()
        held.recheck()
        after = {str(path.relative_to(tmp_path)): m._sha(path.read_bytes()) for path in tmp_path.rglob("*") if path.is_file()}
        assert before == after
    finally:
        held.close()


@pytest.mark.parametrize("fault", ("body_mutation", "extra_leaf", "lock_mode"))
def test_held_original_input_mutations_refuse_without_namespace_repair(tmp_path, monkeypatch, fault):
    held, run = _held_fixture(tmp_path, monkeypatch)
    try:
        held.project()
        if fault == "body_mutation":
            path = next((run / "objects").iterdir()); raw = path.read_bytes()
            path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        elif fault == "extra_leaf": (run / "unexpected.json").write_bytes(b"{}")
        else: tmp_path.joinpath(*m.capture.ARTIFACT_PARTS, "capture.lock").chmod(0o640)
        with pytest.raises(ValueError): held.recheck()
    finally:
        held.close()


@pytest.mark.parametrize("fault", ("missing_ordinal", "bool_ordinal", "wrong_request_sha", "body_sha", "body_size_bool",
    "body_size", "unknown_field", "nonbytes", "zero_body", "bad_result_sha", "duplicate", "reorder", "too_many"))
def test_malformed_or_misaligned_descriptor_refuses_without_silently_dropping(fault):
    item = _input()
    values = (item,)
    if fault == "missing_ordinal": del item["ordinal"]
    elif fault == "bool_ordinal": item["ordinal"] = False
    elif fault == "wrong_request_sha": item["request_sha256"] = "0" * 64
    elif fault == "body_sha": item["body_sha256"] = "0" * 64
    elif fault == "body_size_bool": item["body_size_bytes"] = True
    elif fault == "body_size": item["body_size_bytes"] += 1
    elif fault == "unknown_field": item["private"] = "PRIVATE"
    elif fault == "nonbytes": item["raw_bytes"] = bytearray(item["raw_bytes"])
    elif fault == "zero_body": item.update(raw_bytes=b"", body_size_bytes=0, body_sha256=m._sha(b""))
    elif fault == "bad_result_sha": item["result_sha256"] = "PRIVATE"
    elif fault == "duplicate": other = deepcopy(item); other["ordinal"] = 1; values = (item, other)
    elif fault == "reorder": values = (_input(2), item)
    else: values = tuple(_input(i) for i in range(1, 66))
    with pytest.raises(ValueError): m.assess_supplied_pilot_parents(values)


@pytest.mark.parametrize("inputs", ((), [], None, b"PRIVATE"))
def test_no_empty_or_nonexact_input_container(inputs):
    with pytest.raises(m.PilotParentProjectionError): m.assess_supplied_pilot_parents(inputs)


def test_capture_controls_separate_old_identity_from_current_consumer(monkeypatch):
    report, reservation, checked = _controls(monkeypatch)
    rr, sr = m._raw(report), m._raw(reservation)
    old, actual_report, selection = m._original_controls(rr, sr, expected_report_sha256=m._sha(rr))
    assert old["head"] == m.CAPTURE_HEAD and old != _identity()
    assert actual_report == report and selection == reservation["selection"] and checked == [selection]
    with pytest.raises(ValueError): m._original_controls(rr, sr)
    report["capture_execution_identity"] = _identity()
    rr = m._raw(report)
    with pytest.raises(m.PilotParentProjectionError): m._original_controls(rr, sr, expected_report_sha256=m._sha(rr))


def test_full64_parent_validation_rederives_control_links_and_preserves_source_tiers(monkeypatch):
    result = _worker_result(monkeypatch)
    assert m._validate(result, _identity()) == _identity(original=True)
    assert m._decode_report(m._raw(result)) == result
    assert result["assessment"]["counts"]["projected"] == 64
    assert result["execution_identity"]["head"] != m._validate(result, _identity())["head"]


@pytest.mark.parametrize("fault", ("bool_count", "body_total", "row_order", "source_ordinal_bool", "source_issuer",
    "child_offset", "child_size_bool", "child_hash", "amendment_claim", "financial_flag", "row_extra",
    "lost_row", "more_row", "result_witness", "original_source_count_bool", "access_bool", "registration"))
def test_full64_ipc_mutation_cannot_rehash_into_acceptance(fault, monkeypatch):
    result = _worker_result(monkeypatch)
    assessment, row = result["assessment"], result["assessment"]["rows"][0]
    if fault == "bool_count": assessment["counts"]["quarantined"] = False
    elif fault == "body_total": assessment["counts"]["raw_parent_bytes"] += 1
    elif fault == "row_order": assessment["rows"][0], assessment["rows"][1] = assessment["rows"][1], assessment["rows"][0]
    elif fault == "source_ordinal_bool": row["source_record_ordinal"] = True
    elif fault == "source_issuer": row["target"]["issuer_cik"] = "0000987654"
    elif fault == "child_offset": row["projection"]["primary_xml"]["parent_byte_offset"] = row["raw_parent"]["size_bytes"]
    elif fault == "child_size_bool": row["projection"]["header"]["size_bytes"] = True
    elif fault == "child_hash": row["projection"]["header"]["sha256"] = "PRIVATE"
    elif fault == "amendment_claim": row["projection"]["amendment_lineage_status"] = "resolved"
    elif fault == "financial_flag": row["projection"]["financial_values_interpreted"] = True
    elif fault == "row_extra": row["private_value"] = "PRIVATE"
    elif fault == "lost_row": assessment["rows"].pop()
    elif fault == "more_row": assessment["rows"].append(deepcopy(row))
    elif fault == "result_witness": result["original_control_witness"]["rows"][0]["result"] = m._raw({"private": "PRIVATE"}).hex()
    elif fault == "original_source_count_bool": result["capture_source_count"] = True
    elif fault == "access_bool": result["new_provider_requests"] = False
    else: result["registration"]["selected_parents"] = 0
    _rehash_assessment(result)
    with pytest.raises((ValueError, KeyError)): m._validate(result, _identity())


@pytest.mark.parametrize("fault", ("source_hash", "source_test", "head", "branch", "clean", "inventory", "source_traversal", "bool_count", "reservation_hash", "selection_hash", "extra_projection", "bytes"))
def test_original_identity_control_pins_and_exact_counts_cannot_be_relabelled(fault, monkeypatch):
    report, reservation, _ = _controls(monkeypatch)
    ident = report["capture_execution_identity"]
    if fault == "source_hash": ident["source_sha256"][m.capture.SELF_PATH] = "a" * 64
    elif fault == "source_test": del ident["source_sha256"][m.capture.TEST_PATH]
    elif fault == "head": ident["head"] = "b" * 40
    elif fault == "branch": ident["branch"] = "codex/not-this-lane"
    elif fault == "clean": ident["clean"] = False
    elif fault == "inventory": ident["source_inventory_sha256"] = "0" * 64
    elif fault == "source_traversal": ident["source_sha256"]["research/../private.py"] = "a" * 64
    elif fault == "bool_count": report["planned_unclaimed_unattempted"] = False
    elif fault == "reservation_hash": report["reservation_sha256"] = "0" * 64
    elif fault == "selection_hash": report["selection_sha256"] = "0" * 64
    elif fault == "extra_projection": report["full_xml_projection_attempts"] = 1
    else: report["retained_body_bytes"] += 1
    if fault in {"source_hash", "source_test", "source_traversal"}:
        ident["source_inventory_sha256"] = m._sha(m._raw(ident["source_sha256"]))
    # Coherently relink the reservation so these negatives exercise the
    # independent literal old-source anchors, not an incidental stale hash.
    if fault in {"source_hash", "source_test", "source_traversal", "head"}:
        report["reservation_sha256"] = m._sha(m._raw(reservation))
    rr, sr = m._raw(report), m._raw(reservation)
    with pytest.raises(ValueError): m._original_controls(rr, sr, expected_report_sha256=m._sha(rr))


def test_current_front_binds_explicit_capture_test_even_if_loaded_closure_omits_it(monkeypatch):
    current = _identity()
    own = {key: current["source_sha256"][key] for key in (m.SELF_PATH, m.TEST_PATH, m.capture.SELF_PATH, m.capture.TEST_PATH)}
    base_identity = deepcopy(current)
    del base_identity["source_sha256"][m.capture.TEST_PATH]
    base_identity["source_inventory_sha256"] = m._sha(m._raw(base_identity["source_sha256"]))
    monkeypatch.setattr(m.base.custody, "_identity", lambda head: deepcopy(base_identity))
    monkeypatch.setattr(m.base.custody, "_source_bytes", lambda root, names: {key: own[key] for key in names})
    bodies = {key: key.encode() for key in own}
    own.update({key: m._sha(raw) for key, raw in bodies.items()})
    matched = []
    monkeypatch.setattr(m.base.custody, "_git", lambda root, *args: matched.append(args[-1]) or bodies[args[-1].split(":", 1)[1]])
    checked = []
    monkeypatch.setattr(m, "_current", lambda value: checked.append(deepcopy(value)))
    result = m._committed_identity(current["head"])
    assert set(own) <= set(result["source_sha256"]) and result["source_sha256"][m.capture.TEST_PATH] == own[m.capture.TEST_PATH]
    assert len(matched) == 4 and checked == [result]


def test_current_front_rejects_uncommitted_source_before_input(monkeypatch):
    current = _identity()
    monkeypatch.setattr(m.base.custody, "_identity", lambda head: current)
    monkeypatch.setattr(m.base.custody, "_source_bytes", lambda root, names: {name: "a" * 64 for name in names})
    monkeypatch.setattr(m.base.custody, "_git", lambda *args: b"different committed bytes")
    with pytest.raises(m.PilotParentProjectionError, match="uncommitted"): m._committed_identity(current["head"])


def test_worker_effective_native_denial_precedes_actual_input_open(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_isolated", lambda: calls.append("flags"))
    def deny():
        calls.append("native"); raise m.PilotParentProjectionError("invented_native_denial_not_established")
    monkeypatch.setattr(m.base, "_prove_isolation", deny)
    monkeypatch.setattr(m, "_current", lambda *_: calls.append("source"))
    monkeypatch.setattr(m, "_HeldCapture", lambda: pytest.fail("actual artifact tripwire reached"))
    with pytest.raises(m.PilotParentProjectionError): m._worker(_identity())
    assert calls == ["flags", "native"]


def test_worker_registration_is_detached_from_mutable_global(monkeypatch):
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m, "_current", lambda value: None)
    class InventedHeld:
        original = _identity(original=True)
        def project(self): return {}, {}
        def recheck(self): pass
        def close(self): pass
    monkeypatch.setattr(m, "_HeldCapture", InventedHeld)
    previous = deepcopy(m.REGISTRATION)
    try:
        result = m._worker(_identity())
        result["registration"]["selected_parents"] = 0
        assert m.REGISTRATION == previous
    finally:
        m.REGISTRATION.clear(); m.REGISTRATION.update(previous)


def test_missing_dependency_closure_refuses_before_artifact_tripwire(monkeypatch):
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.base.custody, "_internal_source_paths", lambda root: (m.SELF_PATH, m.TEST_PATH, "research/missing_dependency.py"))
    monkeypatch.setattr(m, "_HeldCapture", lambda: pytest.fail("artifact read before complete source proof"))
    with pytest.raises(m.PilotParentProjectionError, match="closure_incomplete"): m._worker(_identity())


def test_current_or_frozen_mutation_refuses_before_artifact_tripwire(monkeypatch):
    current = _identity()
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.base.custody, "_internal_source_paths", lambda root: tuple(current["source_sha256"]))
    monkeypatch.setattr(m.base.custody, "_source_bytes", lambda root, names: {name: "0" * 64 for name in names})
    monkeypatch.setattr(m, "_HeldCapture", lambda: pytest.fail("artifact read after source mutation"))
    with pytest.raises(m.PilotParentProjectionError, match="source_changed"): m._worker(current)


def test_command_requires_secret_free_initial_native_denial_and_no_stale_bytecode():
    command = m._command(_identity())
    assert command[:3] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin")
    for part in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", '(deny process-exec (literal "/usr/bin/security"))'):
        assert part in command[5]
    for flag in ("-I", "-S", "-B", "pycache_prefix=" + m.EMPTY_CACHE_PREFIX): assert flag in command
    assert b"raw_bytes" not in command[-1].encode()


def test_parser_does_not_echo_unknown_private_arguments(capsys):
    assert m.main(["--api-token", "PRIVATE ARGUMENT"]) == 2
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err


@pytest.mark.parametrize("bad", (None, "", "0", "PRIVATE", "a" * (2 * m.capture.MAX_CONTROL_BYTES + 2)))
def test_control_witness_is_bounded_strict_hex(bad):
    with pytest.raises(m.PilotParentProjectionError): m._unhex(bad)


def test_ipc_codec_accepts_own_large_control_witness_not_the_old_one_megabyte_limit():
    # An original reservation, 64 claims and journals plus row metadata can
    # exceed the old reader's limits without approaching the new IPC cap.
    value = {"original_control_witness": {"reservation": "a" * 800000,
        "rows": [{"claim": "b" * 10000, "start": "c" * 2000, "result": "d" * 2000} for _ in range(64)]}}
    raw = m._raw(value)
    assert 1024 * 1024 < len(raw) < m.MAX_REPORT_BYTES
    assert m._decode_report(raw) == value


@pytest.mark.parametrize("raw", (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.0}', b'{"x":1}\n',
    b'{"x":' + b'[' * 34 + b'0' + b']' * 34 + b'}', b'{"x":"' + b'a' * (2 * m.capture.MAX_CONTROL_BYTES + 1) + b'"}',
    b'{"x":[' + b'0,' * 2048 + b'0]}', b'[]'))
def test_own_ipc_stays_strict_canonical_finite_bounded_and_not_foreign(raw):
    with pytest.raises(m.PilotParentProjectionError): m._decode_report(raw)


def test_guard_only_allows_exact_original_git_sources_not_traversal_or_other_heads():
    guard = m._Guard("d" * 40, ("/usr/bin/false",))
    call = lambda target: guard._git("/usr/bin/git", ["/usr/bin/git", "show", target], m.LANE_ROOT, {"PATH": "/usr/bin:/bin"})
    assert call(m.CAPTURE_HEAD + ":research/insider_buying_pilot_sec_parent_capture.py") is True
    assert not call(m.CAPTURE_HEAD + ":research/../private.py")
    assert not call("c" * 40 + ":research/insider_buying_pilot_sec_parent_capture.py")
    with pytest.raises(m.PilotParentProjectionError): guard._write(m.LANE_ROOT / "invented")
