"""Additive full-original structural admission, never frozen IB-1C ingestion.

All six forms and raw SUBMISSION CIK/date/year evidence remain accounted for.
The immutable original capture/header dispositions and frozen empty-parent
assessment are retained separately from this new, noncanonical parser result.
No frozen complete-submission projection is manufactured or impersonated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import weakref

from data.hashing import hash_payload
from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research import insider_buying_sec_early_original_parent_v1 as parser


SCHEMA = "insider-2006q1-full-original-structural-admission-v1"
MAX_PARENT_COUNT = 64
MAX_ASSESSMENT_BYTES = 128 * 1024 * 1024
FORM_COUNTS = {"3": 5694, "3/A": 534, "4": 68520, "4/A": 3159, "5": 5539, "5/A": 211}
_SEAL = object()
_REGISTRY = {}


class OriginalAdmissionError(ValueError):
    """Fixed local codes; no raw body, private identity or parser text."""


def _need(value, code):
    if not value:
        raise OriginalAdmissionError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return original._sha(raw)


def authority():
    return {**original._authority(), "original_body_structural_admission_is_canonical": False,
            "historical_identity_or_availability_verified": False}


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class OriginalAdmissionAssessment:
    _bytes: bytes = field(repr=False)
    _seal: object = field(repr=False)

    def canonical_bytes(self):
        record = _REGISTRY.get(id(self))
        _need(type(self) is OriginalAdmissionAssessment and self._seal is _SEAL
              and record is not None and record[0]() is self and type(self._bytes) is bytes
              and self._bytes == record[1], "genuine_unchanged_original_admission_required")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def _factory(body):
    raw = _raw(body)
    _need(len(raw) <= MAX_ASSESSMENT_BYTES, "admission_output_bound_refused")
    result = OriginalAdmissionAssessment(raw, _SEAL)
    key = id(result)
    _REGISTRY[key] = (weakref.ref(result, lambda ref: _REGISTRY.pop(key, None)), raw)
    return result


def assess_original_admission(snapshot, census, parent_inputs, *, expected_capture_report_sha256, fixture_only):
    """Validate every supplied descriptor and preserve the complete quarter.

    The caller owns input custody/native isolation. Fixture mode cannot assert
    the observed 83,657-row/64-parent production profile. Missing/refused bodies
    remain in both selected-parent and complete-quarter accounting.
    """
    try:
        original._digest(expected_capture_report_sha256)
        _need(type(fixture_only) is bool and type(parent_inputs) is tuple
              and len(parent_inputs) <= MAX_PARENT_COUNT, "bounded_original_descriptor_tuple_required")
        _need(census.period == "2006Q1" and snapshot.identity.year == 2006 and snapshot.identity.quarter == 1,
              "fixed_original_quarter_required")
        baseline = original.identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
        filings = original._source_filings(snapshot, baseline)
        forms = {form: sum(row["form_type"] == form for row in baseline["rows"]) for form in FORM_COUNTS}
        if not fixture_only:
            _need(len(baseline["rows"]) == 83_657 and forms == FORM_COUNTS and len(parent_inputs) == MAX_PARENT_COUNT
                  and snapshot.identity.raw_archive_sha256 == original.preparation.EXPECTED_ZIP_SHA256,
                  "actual_full_quarter_and64_profile_required")
        descriptors = {"prefix_ordinal", "request_sha256", "request", "result_sha256", "terminal_disposition",
                       "body_sha256", "body_size_bytes", "raw_bytes", "header_identity_bound"}
        ledger, projections, seen, previous, total = [], {}, set(), None, 0
        for ordinal, item in enumerate(parent_inputs):
            _need(type(item) is dict and set(item) == descriptors and type(item["prefix_ordinal"]) is int
                  and item["prefix_ordinal"] == ordinal, "original_descriptor_shape_or_order_refused")
            request = original.capture._request(item["request"])
            accession = request["accession_number"]
            _need(accession not in seen and item["request_sha256"] == _sha(_raw(request)),
                  "original_request_duplicate_or_hash_refused")
            seen.add(accession)
            order = (request["filing_date"], accession, request["source_record_ordinal"])
            _need(previous is None or previous < order, "original_prefix_order_refused"); previous = order
            filing = filings.get(accession)
            _need(filing is not None and filing["relevant_form4_or_amendment"] is True
                  and request["period"] == census.period
                  and all(request[key] == filing[key] for key in ("form_type", "filing_date", "issuer_cik", "source_record_ordinal"))
                  and request["filing_metadata_sha256"] == _sha(_raw(filing))
                  and request["quarterly_zip_sha256"] == snapshot.identity.raw_archive_sha256
                  and request["submission_member_sha256"] == next(table.raw_member_sha256 for table in snapshot.identity.tables
                      if table.table_name == "SUBMISSION.tsv"), "original_request_source_binding_refused")
            if not fixture_only:
                _need(request["submission_inventory_sha256"] == original.capture.bootstrap.custody.INVENTORY_SHA256
                      and request["master_decoded_sha256"] == original.capture.bootstrap.locators.RETAINED_MASTER_SHA256
                      and request["master_receipt_sha256"] == original.capture.bootstrap.MASTER_RECEIPT_SHA256,
                      "original_retained_source_anchor_refused")
            terminal, raw = item["terminal_disposition"], item["raw_bytes"]
            _need(type(terminal) is str and type(item["header_identity_bound"]) is bool, "original_capture_flags_refused")
            row = {key: item[key] for key in ("prefix_ordinal", "request_sha256", "result_sha256", "terminal_disposition",
                "body_sha256", "body_size_bytes", "header_identity_bound")}
            row.update(source_record_ordinal=request["source_record_ordinal"], accession_number=accession,
                       original_projection=None, original_projection_refusal=None)
            if raw is None:
                _need(item["body_sha256"] is None and item["body_size_bytes"] is None
                      and item["header_identity_bound"] is False and terminal in {"planned_unattempted",
                      "ambiguous_transport_failure_no_retry", "http_refused_no_retry", "response_privacy_framing_or_custody_refused_no_retry"}
                      and (item["result_sha256"] is None) is (terminal == "planned_unattempted"), "unavailable_original_descriptor_refused")
                if item["result_sha256"] is not None: original._digest(item["result_sha256"])
                row["disposition"] = "original_complete_parent_unavailable"
            else:
                _need(type(raw) is bytes and 0 < len(raw) <= original.capture.MAX_PARENT_BYTES
                      and type(item["body_size_bytes"]) is int and item["body_size_bytes"] == len(raw)
                      and item["body_sha256"] == _sha(raw) and terminal in {
                          "complete_raw_response_retained_header_bound", "complete_raw_response_retained_header_quarantined"}
                      and item["header_identity_bound"] is terminal.endswith("_bound"), "retained_original_descriptor_refused")
                original._digest(item["result_sha256"])
                total += len(raw)
                _need(total <= original.identity_v2.MAX_CORROBORATING_BYTES, "original_aggregate_byte_bound_refused")
                try:
                    projected = parser.project_early_original_parent(request, raw,
                        expected_original_body_sha256=item["body_sha256"], capture_result_sha256=item["result_sha256"])
                    _need(type(projected) is parser.EarlyOriginalParentProjection, "genuine_original_projection_required")
                    payload = parser.validate_early_original_parent(projected)
                except parser.EarlyOriginalParentError:
                    row.update(disposition="original_parent_structure_quarantined", original_projection_refusal="early_original_parser_refused")
                else:
                    _need(type(projected) is parser.EarlyOriginalParentProjection
                          and payload["original_raw_parent"] == {"sha256": item["body_sha256"], "size_bytes": len(raw)}
                          and payload["capture_result_sha256"] == item["result_sha256"]
                          and payload["full_original_structurally_bound"] is True,
                          "genuine_original_projection_binding_refused")
                    _need(all(payload["target"][key] == request[key] for key in
                              ("period", "accession_number", "form_type", "filing_date", "issuer_cik")),
                          "original_projection_target_refused")
                    evidence = {"projection_sha256": projected.sha256,
                        "original_parent_sha256": item["body_sha256"], "capture_result_sha256": item["result_sha256"],
                        "header_sha256": payload["children"]["header"]["sha256"],
                        "xml_sha256": payload["children"]["primary_xml"]["sha256"],
                        "header_topology": payload["header_topology"], "accepted_clock_verified": False,
                        "capture_header_identity_bound": item["header_identity_bound"]}
                    row.update(disposition="original_structurally_bound_noncanonical", original_projection=evidence)
                    projections[accession] = evidence
            ledger.append(row)
        rows = []
        for source in baseline["rows"]:
            evidence = projections.get(source["accession_number"])
            target = source["form_type"] in {"4", "4/A"}
            _need(evidence is None or target, "context_original_projection_refused")
            rows.append({**source, "frozen_baseline_disposition": source["disposition"],
                "frozen_baseline_quarantine_reasons": list(source["quarantine_reasons"]),
                "disposition": "original_structurally_bound_noncanonical" if evidence is not None else "quarantined",
                "quarantine_reasons": [] if evidence is not None else list(source["quarantine_reasons"]),
                "original_parent_evidence": evidence})
        bound = len(projections)
        counts = {"source_filings": len(rows), "target_filings": forms["4"] + forms["4/A"],
            "context_filings": sum(forms[form] for form in ("3", "3/A", "5", "5/A")),
            "selected_parents": len(ledger), "retained_parent_bodies": sum(row["body_sha256"] is not None for row in ledger),
            "structurally_bound_original_parents": bound,
            "parser_quarantined_parents": sum(row["disposition"] == "original_parent_structure_quarantined" for row in ledger),
            "unavailable_selected_parents": sum(row["disposition"] == "original_complete_parent_unavailable" for row in ledger),
            "structurally_bound_noncanonical_filings": bound, "quarantined_filings": len(rows) - bound,
            "target_original_binding_missing": forms["4"] + forms["4/A"] - bound,
            "retained_parent_bytes": total, "preserved_capture_header_quarantines": sum(
                row["terminal_disposition"] == "complete_raw_response_retained_header_quarantined" for row in ledger)}
        _need(counts["structurally_bound_original_parents"] + counts["parser_quarantined_parents"] == counts["retained_parent_bodies"]
              and counts["retained_parent_bodies"] + counts["unavailable_selected_parents"] == counts["selected_parents"]
              and counts["structurally_bound_noncanonical_filings"] + counts["quarantined_filings"] == counts["source_filings"]
              and counts["target_original_binding_missing"] + bound == counts["target_filings"]
              and [(row["source_record_ordinal"], row["accession_number"]) for row in rows] ==
                  [(row["source_record_ordinal"], row["accession_number"]) for row in baseline["rows"]],
              "whole_original_quarter_partition_refused")
        return _factory({"schema": SCHEMA, "fixture_only": fixture_only, "period": "2006Q1",
            "capture_report_sha256": expected_capture_report_sha256, "form_counts": forms,
            "parsed_snapshot_id": snapshot.identity.snapshot_id, "parsed_lineage_hash": snapshot.identity.lineage_hash,
            "census_quarter_sha256": hash_payload(census.to_payload()), "frozen_baseline_assessment_sha256": hash_payload(baseline),
            "frozen_baseline_accounting_sha256": baseline["accounting_sha256"],
            "parser_profile": parser.PROFILE, "parent_ledger": ledger, "parent_ledger_sha256": _sha(_raw(ledger)),
            "rows": rows, "accounting_sha256": hash_payload(rows), "counts": counts,
            "whole_quarter_identity_sha256": None, "authority": authority()})
    except OriginalAdmissionError:
        raise
    except Exception:
        raise OriginalAdmissionError("original_admission_inputs_refused") from None
