"""Offline structural assessment of the exact newly captured pilot first64.

No financial values, timezone interpretation, source promotion or transport.
Only bounded source/control metadata crosses the trusted worker boundary;
complete submissions and XML children never leave the native-denied worker.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_pilot_sec_parent_capture as capture
from research import insider_buying_pilot_sec_parent_audit_runner as base
from research import insider_buying_sec_feed_directory_stopped_controls as codec
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionError, SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)


SELF_PATH = "research/insider_buying_pilot_sec_parent_projection.py"
TEST_PATH = "tests/test_insider_buying_pilot_sec_parent_projection.py"
SCHEMA = "insider-pilot-sec-parent-structural-assessment-v1"
AUDIT_ID = "ib-pilot-sec-first64-original-parent-assessment-20261025-once"
LANE_ROOT, LANE_BRANCH = base.LANE_ROOT, base.LANE_BRANCH
EMPTY_CACHE_PREFIX = "/var/empty/insider-pilot-sec-parent-projection-no-bytecode"
CAPTURE_HEAD = "1bb03b8ee44088cad82872c12a6cd7f38e9ef961"
CAPTURE_REPORT_SHA256 = "a407d79f06e8257a9a7344a8a64398547e0e51209eae169e4acaa58b92839749"
CAPTURE_SOURCE_SHA256 = "9943d1702ab40155674a1b59be69cda94d3ba330abaa7272901baef438d8e9fe"
CAPTURE_TEST_SHA256 = "56ec1607d55e57418e6fbdc2f527c0828782f0b4542e73e01d049b49895cf229"
MAX_ROWS, ACTUAL_BODY_BYTES = 64, 650349
MAX_REPORT_BYTES, WORKER_TIMEOUT = 8 * 1024 * 1024, 90
_raw, _sha = base._raw, base._sha
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PATH = re.compile(r"[A-Za-z0-9_./-]+\.py\Z")
REGISTRATION = {
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "capture_id": capture.CAPTURE_ID, "capture_head": CAPTURE_HEAD,
    "capture_report_sha256": CAPTURE_REPORT_SHA256,
    "selected_parents": MAX_ROWS, "retained_parent_bytes": ACTUAL_BODY_BYTES,
    "scope": "original complete-parent/header/primary-XML structure only",
    "acceptance_clock": "raw fourteen-digit declaration; no UTC or PIT interpretation",
    "financial_values_interpreted": False, "amendment_lineage_inferred": False,
    "worker_invocations": 1, "new_provider_requests": 0, "credential_reads": 0,
    "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
    "native_network_fork_allwrite_securityexec_denial": True,
    "original_namespace_mutated": False, "persistent_result_published": False,
    "source_authenticated": False, "canonical_admitted": False,
    "complete_pilot_corpus": False, "backtesting_ready": False,
}


class PilotParentProjectionError(ValueError):
    """Fixed source-independent refusal codes only."""


class _ChildSpanRefusal(ValueError):
    """Row-local ambiguous child occurrence, not a custody-control failure."""


def _need(value, code):
    if not value:
        raise PilotParentProjectionError(code)


def _identity(value, *, original=False):
    capture._source_identity(value)
    names = value["source_sha256"]
    _need(1 <= len(names) <= 2048 and all(_PATH.fullmatch(name) and not name.startswith("/")
        and all(p not in {"", ".", ".."} for p in name.split("/")) for name in names),
        "projection_source_paths_refused")
    if original:
        _need(value["head"] == CAPTURE_HEAD
            and names.get(capture.SELF_PATH) == CAPTURE_SOURCE_SHA256
            and names.get(capture.TEST_PATH) == CAPTURE_TEST_SHA256
            and all(name not in names or names[name] == digest for name, digest in base.FROZEN.items()),
            "projection_original_source_pins_refused")
    else:
        _need({SELF_PATH, TEST_PATH, capture.SELF_PATH, capture.TEST_PATH} <= set(names),
            "projection_current_source_roster_refused")
    return value


def _target(request):
    request = capture._request(request)
    # The bulk ISSUERCIK comparison key is the expectation. Neither the
    # directory CIK nor a newly parsed header may supply its own expectation.
    return SecCompleteSubmissionTarget(period=request["period"],
        accession_number=request["accession_number"], form_type=request["form_type"],
        filing_date=request["filing_date"], issuer_cik=request["issuer_cik"].zfill(10),
        quarterly_index_sha256=request["master_decoded_sha256"],
        complete_submission_url=request["url"])


def assess_supplied_pilot_parents(inputs):
    """Pure structural projection; one aligned descriptor per supplied parent.

    This function makes no custody/authenticity assertion. The protected real
    loader supplies independently verified descriptors; fixtures cannot mint
    an observed operation by supplying shaped dictionaries.
    """
    _need(type(inputs) is tuple and 1 <= len(inputs) <= MAX_ROWS,
        "projection_input_count_refused")
    rows, seen, total = [], set(), 0
    for ordinal, item in enumerate(inputs):
        _need(type(item) is dict and set(item) == {"ordinal", "request", "request_sha256",
            "result_sha256", "start_sha256", "claim_sha256", "raw_bytes", "body_sha256", "body_size_bytes"}
            and type(item["ordinal"]) is int and item["ordinal"] == ordinal,
            "projection_input_order_or_schema_refused")
        target = _target(item["request"])
        _need(target.accession_number not in seen, "projection_duplicate_accession_refused")
        seen.add(target.accession_number)
        _need(item["request_sha256"] == _sha(_raw(item["request"]))
            and all(type(item[key]) is str and _SHA.fullmatch(item[key])
                for key in ("result_sha256", "start_sha256", "claim_sha256", "body_sha256")),
            "projection_input_hash_fields_refused")
        raw = item["raw_bytes"]
        _need(type(raw) is bytes and 0 < len(raw) <= capture.MAX_PARENT_BYTES
            and type(item["body_size_bytes"]) is int and item["body_size_bytes"] == len(raw)
            and item["body_sha256"] == _sha(raw), "projection_body_binding_refused")
        total += len(raw)
        _need(total <= MAX_ROWS * capture.MAX_PARENT_BYTES, "projection_total_body_bound_refused")
        row = {"ordinal": ordinal, "source_record_ordinal": item["request"]["source_record_ordinal"],
            "request_sha256": item["request_sha256"], "result_sha256": item["result_sha256"],
            "start_sha256": item["start_sha256"], "claim_sha256": item["claim_sha256"],
            "target": target.to_payload(), "raw_parent": {"sha256": item["body_sha256"], "size_bytes": len(raw)},
            "projection": None, "quarantine_code": None}
        try:
            projected = project_sec_complete_submission(target, raw)
            payload = projected.to_payload()
            _need(payload["raw_parent"]["sha256"] == item["body_sha256"], "projection_parent_digest_differs")
            header, xml = projected.header_bytes, projected.xml_bytes
            header_at, xml_at = raw.find(header), raw.find(xml)
            if not (header_at >= 0 and xml_at >= 0 and raw.count(header) == raw.count(xml) == 1):
                raise _ChildSpanRefusal("projection_child_span_ambiguous")
            row.update(disposition="original_complete_parent_projected_noncanonical", projection={
                "version": payload["version"], "payload_sha256": projected.sha256,
                "header": {"sha256": _sha(header), "size_bytes": len(header), "parent_byte_offset": header_at},
                "primary_xml": {"sha256": _sha(xml), "size_bytes": len(xml), "parent_byte_offset": xml_at,
                    "filename": projected.primary_xml_filename},
                "accepted_at_raw_uninterpreted": projected.accepted_at_raw,
                "header_owner_ciks_sha256": _sha(_raw(list(projected.header_owner_ciks))),
                "reporting_owner_count": len(projected.header_owner_ciks),
                "header_xml_owner_sets_agree": True, "issuer_cik_crosschecked_against_bulk_request": True,
                "amendment_lineage_status": "unresolved_not_inferred" if target.form_type == "4/A" else "original_as_filed",
                "financial_values_interpreted": False})
        except (SecCompleteSubmissionError, _ChildSpanRefusal):
            row.update(disposition="original_complete_parent_grammar_quarantined",
                quarantine_code="unsupported_or_conflicting_complete_submission_structure")
        rows.append(row)
    projected_count = sum(row["projection"] is not None for row in rows)
    return {"schema": SCHEMA + "/assessment", "rows": rows,
        "ordered_rows_sha256": _sha(_raw(rows)),
        "counts": {"selected": len(rows), "projected": projected_count,
            "quarantined": len(rows) - projected_count, "raw_parent_bytes": total},
        "financial_values_interpreted": False, "acceptance_timezone_interpreted": False,
        "canonical_admitted": False, "complete_pilot_corpus": False, "backtesting_ready": False}


def _original_controls(report_raw, reservation_raw, *, expected_report_sha256=CAPTURE_REPORT_SHA256):
    _need(type(report_raw) is bytes and type(reservation_raw) is bytes
        and 0 < len(report_raw) <= capture.MAX_CONTROL_BYTES
        and 0 < len(reservation_raw) <= capture.MAX_CONTROL_BYTES
        and _sha(report_raw) == expected_report_sha256, "projection_capture_report_pin_refused")
    report, reservation = capture._decode(report_raw), capture._decode(reservation_raw)
    original = _identity(report.get("capture_execution_identity"), original=True)
    _need(report.get("schema") == capture.SCHEMA + "/complete" and report.get("capture_id") == capture.CAPTURE_ID
        and report.get("fixture_only") is False and report.get("capture_completed_without_refusal") is True
        and report.get("reservation_sha256") == _sha(reservation_raw)
        and reservation.get("capture_execution_identity") == original
        and reservation.get("schema") == capture.SCHEMA + "/reservation"
        and reservation.get("capture_id") == capture.CAPTURE_ID and reservation.get("fixture_only") is False,
        "projection_original_control_links_refused")
    selection = reservation.get("selection")
    _need(type(selection) is dict and selection.get("fixture_only") is False
        and report.get("selection_sha256") == reservation.get("selection_sha256")
        == _sha(_raw(selection)) == capture.ACTUAL_SELECTION_SHA256
        and report.get("selection_execution_head") == reservation.get("selection_execution_head") == capture.ACTUAL_SELECTION_HEAD,
        "projection_original_selection_refused")
    capture.fresh.validate_selection_payload(selection)
    for key, expected in (("planned_requests", MAX_ROWS), ("started_requests", MAX_ROWS),
            ("permanent_claims_created", MAX_ROWS), ("terminal_result_records", MAX_ROWS),
            ("raw_bodies_retained", MAX_ROWS), ("header_bound_bodies", MAX_ROWS),
            ("header_quarantined_bodies", 0), ("retained_body_bytes", ACTUAL_BODY_BYTES),
            ("planned_unclaimed_unattempted", 0), ("full_xml_projection_attempts", 0)):
        _need(type(report.get(key)) is int and report[key] == expected, "projection_original_counts_refused")
    _need(type(report.get("results")) is list and len(report["results"]) == MAX_ROWS
        and report.get("authority") == reservation.get("authority") == capture.audit._AUTHORITY
        and report.get("old_roots_written") is False, "projection_original_scope_refused")
    return original, report, selection


class _HeldCapture:
    """Strict old-input metadata/hash/inventory custody and shared lock."""
    def __init__(self):
        _isolated(); base._prove_isolation()
        self.inputs, self.lock_fd, self.versions = base.custody._Inputs(LANE_ROOT), None, []
        try:
            parts = capture.ARTIFACT_PARTS
            self.base = self.inputs.directory(parts)
            self.claims = self.inputs.directory((*parts, "claims"))
            self.runs = self.inputs.directory((*parts, "runs"))
            self.run_parts = (*parts, "runs", capture.CAPTURE_ID)
            self.run = self.inputs.directory(self.run_parts)
            self.objects = self.inputs.directory((*self.run_parts, "objects"))
            for chain in (self.base, self.claims, self.runs, self.run, self.objects):
                info = os.fstat(chain.fd)
                _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                    "projection_directory_owner_or_mode_refused")
                self.versions.append((chain, codec._version(info)))
            self.lock_fd = os.open("capture.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.base.fd)
            fcntl.flock(self.lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            _need(self.read(self.base, parts, "capture.lock", 1024) == capture.LOCK_BYTES,
                "projection_capture_lock_refused")
            self.lock_version = codec._version(os.fstat(self.lock_fd))
            self.report_raw = self.read(self.run, self.run_parts, "complete.json")
            self.reservation_raw = self.read(self.run, self.run_parts, "reservation.json")
            self.original, self.report, self.selection = _original_controls(self.report_raw, self.reservation_raw)
            # Original history is proved by the trusted parent against the
            # old Git commit after the fixed-report witness returns. Current
            # executed closure is separately bound before/after; an unused
            # old dependency need not remain frozen in the later checkout.
            self.read(self.run, self.run_parts, "contact-validated.json")
            run_names = {"reservation.json", "contact-validated.json", "complete.json", "objects"}
            run_names.update(f"request-{ordinal:03d}-{kind}.json" for ordinal in range(MAX_ROWS) for kind in ("start", "result"))
            for chain, names in ((self.base, {"capture.lock", "claims", "runs"}),
                    (self.runs, {capture.CAPTURE_ID}), (self.run, run_names)):
                self.inputs.inventory(chain, names)
            self.recheck()
        except BaseException:
            base.selector._close_all((self,), phase="projection_open_cleanup"); raise

    def read(self, chain, parts, name, cap=capture.MAX_CONTROL_BYTES):
        _need(os.stat(name, dir_fd=chain.fd, follow_symlinks=False).st_uid == os.geteuid(),
            "projection_input_owner_refused")
        return self.inputs.read(chain, parts, name, limit=cap)

    def project(self):
        before = capture._verify_capture(root=LANE_ROOT, expected_report_sha256=CAPTURE_REPORT_SHA256,
            fixture_only=False, execution_identity=self.original)
        descriptors, witnesses = [], []
        for ordinal, (row, result_descriptor) in enumerate(zip(self.selection["requests"], self.report["results"], strict=True)):
            result_raw = self.read(self.run, self.run_parts, f"request-{ordinal:03d}-result.json")
            start_raw = self.read(self.run, self.run_parts, f"request-{ordinal:03d}-start.json")
            request = row["request"]
            claim_name = _sha(request["accession_number"].encode("ascii")) + ".json"
            claim_raw = self.read(self.claims, (*capture.ARTIFACT_PARTS, "claims"), claim_name)
            result, start = capture._decode(result_raw), capture._decode(start_raw)
            _need(_sha(result_raw) == result_descriptor["result_sha256"]
                and result_descriptor["result_name"] == f"request-{ordinal:03d}-result.json"
                and result["start_sha256"] == _sha(start_raw) and start["claim_sha256"] == _sha(claim_raw)
                and result["body_retained"] is result["header_identity_bound"] is True
                and result["disposition"] == "request_bound_parent_retained_header_bound",
                "projection_request_control_changed")
            raw = self.read(self.objects, (*self.run_parts, "objects"), result["body_sha256"] + ".bin", capture.MAX_PARENT_BYTES)
            descriptors.append({"ordinal": ordinal, "request": request, "request_sha256": row["request_sha256"],
                "result_sha256": _sha(result_raw), "start_sha256": _sha(start_raw), "claim_sha256": _sha(claim_raw),
                "raw_bytes": raw, "body_sha256": result["body_sha256"], "body_size_bytes": result["body_size_bytes"]})
            witnesses.append({"result": result_raw.hex(), "start": start_raw.hex(), "claim": claim_raw.hex()})
        assessment = assess_supplied_pilot_parents(tuple(descriptors))
        self.inputs.inventory(self.claims, {_sha(row["request"]["accession_number"].encode("ascii")) + ".json" for row in self.selection["requests"]})
        self.inputs.inventory(self.objects, {row["body_sha256"] + ".bin" for row in descriptors})
        _need(assessment["counts"]["selected"] == MAX_ROWS
            and assessment["counts"]["raw_parent_bytes"] == ACTUAL_BODY_BYTES, "projection_actual_body_conservation_refused")
        after = capture._verify_capture(root=LANE_ROOT, expected_report_sha256=CAPTURE_REPORT_SHA256,
            fixture_only=False, execution_identity=self.original)
        _need(before == after, "projection_capture_replay_changed")
        self.recheck()
        return assessment, {"report": self.report_raw.hex(), "reservation": self.reservation_raw.hex(), "rows": witnesses}

    def recheck(self):
        self.inputs.recheck()
        for chain, version in self.versions:
            _need(codec._version(os.fstat(chain.fd)) == version, "projection_input_directory_metadata_changed")
        if self.lock_fd is not None and hasattr(self, "lock_version"):
            _need(codec._version(os.fstat(self.lock_fd)) == self.lock_version ==
                codec._version(os.stat("capture.lock", dir_fd=self.base.fd, follow_symlinks=False)), "projection_lock_changed")

    def close(self):
        codec._HeldStopped.close(self)


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "projection_initial_isolated_flags_required")


def _current(identity):
    _identity(identity)
    required = set(base.custody._internal_source_paths(LANE_ROOT)) | {SELF_PATH, TEST_PATH, capture.SELF_PATH, capture.TEST_PATH}
    _need(required <= set(identity["source_sha256"]), "projection_current_source_closure_incomplete")
    _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
        and base.custody._source_bytes(LANE_ROOT, tuple(base.FROZEN)) == base.FROZEN
        and base.custody._source_bytes(LANE_ROOT, (capture.SELF_PATH, capture.TEST_PATH)) == {
            capture.SELF_PATH: CAPTURE_SOURCE_SHA256, capture.TEST_PATH: CAPTURE_TEST_SHA256},
        "projection_current_or_frozen_source_changed")


def _worker(identity):
    _isolated(); base._prove_isolation(); _current(identity)
    held = None
    try:
        held = _HeldCapture()
        assessment, witness = held.project()
        held.recheck(); _current(identity)
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "registration": json.loads(_raw(REGISTRATION)),
            "registration_sha256": _sha(_raw(REGISTRATION)), "execution_identity": identity,
            "capture_source_inventory_sha256": held.original["source_inventory_sha256"],
            "capture_source_count": len(held.original["source_sha256"]),
            "capture_report_sha256": CAPTURE_REPORT_SHA256, "assessment": assessment,
            "assessment_sha256": _sha(_raw(assessment)), "original_control_witness": witness,
            "native_network_fork_allwrite_securityexec_denial": True,
            "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
            "original_namespace_mutated": False, "persistent_result_published": False,
            "canonical_admitted": False, "backtesting_ready": False}
    finally:
        base.selector._close_all((held,), phase="projection_worker_cleanup")


def _unhex(value):
    _need(type(value) is str and 0 < len(value) <= 2 * capture.MAX_CONTROL_BYTES
        and len(value) % 2 == 0 and re.fullmatch(r"[0-9a-f]+", value), "projection_control_witness_encoding_refused")
    return bytes.fromhex(value)


def _decode_report(raw):
    # This is OWN canonical control IPC, not foreign-response JSON. The old
    # stopped-reader's 1 MiB/512 KiB-string caps cannot carry a full64 witness.
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_REPORT_BYTES, "projection_ipc_byte_bound_refused")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "projection_ipc_duplicate_key_refused")
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
            parse_float=lambda _: _need(False, "projection_ipc_float_refused"),
            parse_constant=lambda _: _need(False, "projection_ipc_nonfinite_refused"))
        _need(type(result) is dict and _raw(result) == raw, "projection_ipc_canonical_object_required")
        pending, nodes = [(result, 0)], 0
        while pending:
            value, depth = pending.pop(); nodes += 1
            _need(depth <= 32 and nodes <= 100000, "projection_ipc_resource_bound_refused")
            if type(value) is dict:
                _need(len(value) <= 2048 and all(type(key) is str and len(key) <= 256 for key in value), "projection_ipc_dictionary_bound_refused")
                pending.extend((item, depth + 1) for item in value.values())
            elif type(value) is list:
                _need(len(value) <= 2048, "projection_ipc_list_bound_refused")
                pending.extend((item, depth + 1) for item in value)
            elif type(value) is str:
                _need(len(value) <= 2 * capture.MAX_CONTROL_BYTES, "projection_ipc_string_bound_refused")
        return result
    except PilotParentProjectionError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PilotParentProjectionError("projection_ipc_json_refused") from None


def _validate(result, identity):
    _identity(identity)
    _need(type(result) is dict and set(result) == {"schema", "audit_id", "registration", "registration_sha256",
        "execution_identity", "capture_source_inventory_sha256", "capture_source_count", "capture_report_sha256", "assessment", "assessment_sha256", "original_control_witness",
        "native_network_fork_allwrite_securityexec_denial", "new_provider_requests", "credential_reads", "qc_accesses",
        "outcome_looks", "backtests", "original_namespace_mutated", "persistent_result_published", "canonical_admitted", "backtesting_ready"}
        and result["schema"] == SCHEMA and result["audit_id"] == AUDIT_ID
        and _raw(result["registration"]) == _raw(REGISTRATION)
        and result["registration_sha256"] == _sha(_raw(REGISTRATION))
        and result["execution_identity"] == identity and result["capture_report_sha256"] == CAPTURE_REPORT_SHA256
        and result["native_network_fork_allwrite_securityexec_denial"] is True, "projection_worker_identity_refused")
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(result[key]) is int and result[key] == 0, "projection_worker_access_refused")
    for key in ("original_namespace_mutated", "persistent_result_published", "canonical_admitted", "backtesting_ready"):
        _need(result[key] is False, "projection_worker_authority_refused")
    witness = result["original_control_witness"]
    _need(type(witness) is dict and set(witness) == {"report", "reservation", "rows"}, "projection_witness_schema_refused")
    original, report, selection = _original_controls(_unhex(witness["report"]), _unhex(witness["reservation"]))
    _need(result["capture_source_inventory_sha256"] == original["source_inventory_sha256"]
        and type(result["capture_source_count"]) is int and result["capture_source_count"] == len(original["source_sha256"]),
        "projection_original_source_metadata_refused")
    assessment = result["assessment"]
    _need(type(assessment) is dict and result["assessment_sha256"] == _sha(_raw(assessment))
        and set(assessment) == {"schema", "rows", "ordered_rows_sha256", "counts", "financial_values_interpreted",
            "acceptance_timezone_interpreted", "canonical_admitted", "complete_pilot_corpus", "backtesting_ready"}
        and assessment["schema"] == SCHEMA + "/assessment"
        and type(assessment["rows"]) is list and len(assessment["rows"]) == MAX_ROWS
        and assessment["ordered_rows_sha256"] == _sha(_raw(assessment["rows"]))
        and type(witness["rows"]) is list and len(witness["rows"]) == MAX_ROWS,
        "projection_assessment_schema_refused")
    for key in ("financial_values_interpreted", "acceptance_timezone_interpreted", "canonical_admitted", "complete_pilot_corpus", "backtesting_ready"):
        _need(assessment[key] is False, "projection_assessment_authority_refused")
    total = projected = 0
    for ordinal, (row, control, chosen, descriptor) in enumerate(zip(assessment["rows"], witness["rows"], selection["requests"], report["results"], strict=True)):
        _need(type(control) is dict and set(control) == {"result", "start", "claim"}, "projection_row_witness_refused")
        rr, sr, cr = (_unhex(control[key]) for key in ("result", "start", "claim"))
        finish, start, claim = (capture._decode(raw) for raw in (rr, sr, cr))
        _need(type(row) is dict and set(row) == {"ordinal", "source_record_ordinal", "request_sha256", "result_sha256",
            "start_sha256", "claim_sha256", "target", "raw_parent", "projection", "quarantine_code", "disposition"}
            and type(row["ordinal"]) is int and row["ordinal"] == ordinal
            and type(row["source_record_ordinal"]) is int and row["source_record_ordinal"] == chosen["request"]["source_record_ordinal"]
            and row["target"] == _target(chosen["request"]).to_payload()
            and row["request_sha256"] == chosen["request_sha256"] == finish["request_sha256"] == start["request_sha256"]
            and row["result_sha256"] == _sha(rr) == descriptor["result_sha256"]
            and descriptor["result_name"] == f"request-{ordinal:03d}-result.json"
            and row["start_sha256"] == _sha(sr) == finish["start_sha256"]
            and row["claim_sha256"] == _sha(cr) == start["claim_sha256"]
            and claim["request"] == chosen and claim["reservation_sha256"] == start["reservation_sha256"] == report["reservation_sha256"]
            and finish["body_retained"] is finish["header_identity_bound"] is True
            and row["raw_parent"] == {"sha256": finish["body_sha256"], "size_bytes": finish["body_size_bytes"]},
            "projection_row_control_crosslinks_refused")
        _need(type(finish["body_size_bytes"]) is int and 0 < finish["body_size_bytes"] <= capture.MAX_PARENT_BYTES,
            "projection_row_size_refused")
        total += finish["body_size_bytes"]
        if row["projection"] is None:
            _need(row["disposition"] == "original_complete_parent_grammar_quarantined"
                and row["quarantine_code"] == "unsupported_or_conflicting_complete_submission_structure", "projection_quarantine_refused")
        else:
            p = row["projection"]
            _need(type(p) is dict and set(p) == {"version", "payload_sha256", "header", "primary_xml",
                "accepted_at_raw_uninterpreted", "header_owner_ciks_sha256", "reporting_owner_count", "header_xml_owner_sets_agree",
                "issuer_cik_crosschecked_against_bulk_request", "amendment_lineage_status", "financial_values_interpreted"}
                and row["disposition"] == "original_complete_parent_projected_noncanonical" and row["quarantine_code"] is None
                and p["version"] == "INSETF-SEC-COMPLETE-SUBMISSION-v1"
                and all(type(p[key]) is str and _SHA.fullmatch(p[key]) for key in ("payload_sha256", "header_owner_ciks_sha256"))
                and type(p["accepted_at_raw_uninterpreted"]) is str and re.fullmatch(r"[0-9]{14}", p["accepted_at_raw_uninterpreted"])
                and type(p["reporting_owner_count"]) is int and 1 <= p["reporting_owner_count"] <= 256
                and p["header_xml_owner_sets_agree"] is p["issuer_cik_crosschecked_against_bulk_request"] is True
                and p["financial_values_interpreted"] is False
                and p["amendment_lineage_status"] == ("unresolved_not_inferred" if row["target"]["form_type"] == "4/A" else "original_as_filed"),
                "projection_projection_schema_refused")
            for key in ("header", "primary_xml"):
                child = p[key]
                _need(type(child) is dict and set(child) == ({"sha256", "size_bytes", "parent_byte_offset", "filename"} if key == "primary_xml" else {"sha256", "size_bytes", "parent_byte_offset"})
                    and type(child["sha256"]) is str and _SHA.fullmatch(child["sha256"])
                    and type(child["size_bytes"]) is int and child["size_bytes"] > 0
                    and type(child["parent_byte_offset"]) is int and child["parent_byte_offset"] >= 0
                    and child["parent_byte_offset"] + child["size_bytes"] <= finish["body_size_bytes"], "projection_child_bounds_refused")
            _need(type(p["primary_xml"]["filename"]) is str
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,250}\.xml", p["primary_xml"]["filename"])
                and ".." not in p["primary_xml"]["filename"] and not p["primary_xml"]["filename"].lower().startswith("xsl"),
                "projection_xml_filename_refused")
            projected += 1
    expected = {"selected": MAX_ROWS, "projected": projected, "quarantined": MAX_ROWS - projected, "raw_parent_bytes": total}
    _need(total == ACTUAL_BODY_BYTES and type(assessment["counts"]) is dict
        and set(assessment["counts"]) == set(expected)
        and all(type(assessment["counts"][key]) is int and assessment["counts"][key] == value for key, value in expected.items())
        and len(_raw(result)) <= MAX_REPORT_BYTES, "projection_assessment_conservation_refused")
    return original


class _Guard(base._ParentGuard):
    def _write(self, path, *, mkdir=False):
        raise PilotParentProjectionError("projection_parent_all_writes_refused")

    def _git(self, executable, command, cwd, env):
        if (executable == "/usr/bin/git" and type(command) in {list, tuple} and len(command) == 3
            and command[:2] in ([executable, "show"], (executable, "show")) and type(command[2]) is str
            and self._lane_cwd(cwd) and env == {"PATH": "/usr/bin:/bin"}):
            commit, separator, name = command[2].partition(":")
            if commit == CAPTURE_HEAD and separator and _PATH.fullmatch(name) and not name.startswith("/") and all(p not in {"", ".", ".."} for p in name.split("/")):
                return True
        return super()._git(executable, command, cwd, env)


def _committed_identity(head):
    identity = base.custody._identity(head)
    own = base.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH, capture.SELF_PATH, capture.TEST_PATH))
    for name, digest in own.items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", head + ":" + name)) == digest, "projection_uncommitted_source_refused")
    sources = {**identity["source_sha256"], **own}
    result = _identity({**identity, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))})
    _current(result)
    return result


def _command(identity):
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");import json;"
        "from research import insider_buying_pilot_sec_parent_projection as m;identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept Exception: print('{\"disposition\":\"pilot_parent_projection_worker_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX, "-c", code)


def run_actual_assessment(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "projection_fixed_source_required")
    identity = _committed_identity(expected_head)
    command = _command(identity)
    sys.addaudithook(_Guard(expected_head, command))
    child = base.launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=WORKER_TIMEOUT, cap=MAX_REPORT_BYTES)
    _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= MAX_REPORT_BYTES, "projection_worker_refused")
    result = _decode_report(child.stdout.removesuffix(b"\n"))
    original = _validate(result, identity)
    for name, digest in original["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", CAPTURE_HEAD + ":" + name)) == digest, "projection_original_git_source_mismatch")
    _need(_committed_identity(expected_head) == identity, "projection_parent_current_source_changed")
    public = dict(result)
    del public["original_control_witness"]
    public.update(original_control_witness_validated_and_omitted=True, original_source_inventory_matched_capture_commit=True,
        observed_worker_stdout_bytes=len(child.stdout), observed_worker_stdout_sha256=_sha(child.stdout))
    return public


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise PilotParentProjectionError("projection_arguments_refused")
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--expected-head", required=True)
        args = parser.parse_args(argv)
        result = run_actual_assessment(args.expected_head)
    except Exception:
        print('{"disposition":"pilot_parent_projection_refused"}')
        return 2
    print(_raw(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
