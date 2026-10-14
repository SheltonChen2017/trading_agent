"""Pure early-PEM source-view corroboration, not whole-body admission.

This separately versioned epoch composes the genuine original/view extraction,
unchanged frozen projection of the exact inner bytes, and unchanged IB-1C v2
assessor. Its full-quarter ledger says source_view_corroborated_noncanonical,
never that v2 alone admitted an original PEM whole body. Original acquisition
header quarantines and unsupported issuer-first parsing remain unchanged.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import re

from data.hashing import hash_payload
from research import insider_buying_sec_early_pem_source_view_v1 as pem
from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research.insider_buying import sec_ib1c_identity_v2 as v2
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionProjection, SecCompleteSubmissionTarget,
    SecCompleteSubmissionError, project_sec_complete_submission,
)


SCHEMA = "insider-2006q1-supplied-pem-source-view-corroboration-v1"
EVIDENCE_EPOCH = "INSETF-IB1C-2006Q1-PEM-SOURCE-VIEW-IDENTITY-v1-candidate"
MAX_SELECTED_PARENTS = 64
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = object()
_DESCRIPTOR_KEYS = frozenset({"prefix_ordinal", "request_sha256", "request", "result_sha256", "terminal_disposition",
    "body_sha256", "body_size_bytes", "raw_bytes", "header_identity_bound"})


class PemSourceViewEvidenceError(ValueError):
    """Fixed refusal codes only; source/private exception text is excluded."""


def _need(value, code):
    if not value:raise PemSourceViewEvidenceError(code)


def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "external_digest_required")
    return value


def _authority():
    return {**v2._authority(), **pem._authority(), "whole_original_parent_admitted": False,
        "source_view_contract_is_original_parent_contract": False, "signal_eligibility_evaluated": False}


def _target(request):
    original.capture._request(request)
    return SecCompleteSubmissionTarget(period=request["period"], accession_number=request["accession_number"],
        form_type=request["form_type"], filing_date=request["filing_date"], issuer_cik=request["issuer_cik"],
        quarterly_index_sha256=request["master_decoded_sha256"], complete_submission_url=request["url"])


@dataclass(frozen=True, slots=True)
class ProjectedPemParent:
    _view: pem.EarlyPemSourceView = field(repr=False)
    _projection: SecCompleteSubmissionProjection = field(repr=False)
    _context_bytes: bytes = field(repr=False)
    _payload_bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def _validated(self):
        _need(type(self) is ProjectedPemParent and self._token is _TOKEN
              and self._factory_bytes == self._payload_bytes and type(self._context_bytes) is bytes
              and type(self._view) is pem.EarlyPemSourceView
              and type(self._projection) is SecCompleteSubmissionProjection,
              "genuine_unchanged_pem_projection_bridge_required")
        view = self._view.to_payload()  # Full original/view byte reparse.
        projected = self._projection.to_payload()  # Full frozen header/XML reparse.
        context = json.loads(self._context_bytes)
        _need(context.get("original_capture_header_identity_bound") is False
              and projected["target"] == _target(context["request"]).to_payload()
              and self._projection.raw_bytes == self._view.source_view_bytes
              and projected["raw_parent"]["sha256"] == view["derived_sec_document_source_view"]["sha256"],
              "original_view_frozen_projection_relation_changed")
        expected = _bridge_payload(context, view, projected, self._projection.sha256)
        _need(_raw(expected) == self._payload_bytes, "pem_projection_bridge_metadata_changed")
        return expected

    def to_payload(self):return self._validated()
    @property
    def sha256(self):self._validated();return _sha(self._payload_bytes)
    @property
    def frozen_source_view_projection(self):
        self._validated();return self._projection


def _bridge_payload(context, view, projected, projection_sha):
    return {"schema": SCHEMA + "/original-view-projection-bridge", "evidence_epoch": EVIDENCE_EPOCH,
        "request": context["request"], "request_sha256": _sha(_raw(context["request"])),
        "capture_result_sha256": context["capture_result_sha256"],
        "original_capture_header_identity_bound": False,
        "original_capture_header_quarantine_preserved": True,
        "original_raw_parent": view["original_raw_parent"],
        "derived_sec_document_source_view": view["derived_sec_document_source_view"],
        "source_view_receipt_sha256": _sha(_raw(view)), "pem_profile": view["profile"],
        "frozen_source_view_projection": {"version": projected["version"], "sha256": projection_sha,
            "raw_parent_identity_kind": "derived_contiguous_sec_document_view_not_original_whole_body",
            "source_view_parent_sha256": projected["raw_parent"]["sha256"],
            "header_sha256": projected["children"]["header"]["sha256"],
            "xml_sha256": projected["children"]["primary_xml"]["sha256"],
            "source_acceptance_raw": projected["source_fields"]["accepted_at_raw"],
            "source_acceptance_timezone_inferred": False},
        "disposition": "source_view_projected_noncanonical", "authority": _authority()}


def project_genuine_pem_source_view(request, view_receipt, *, capture_result_sha256,
                                    original_capture_header_identity_bound=False):
    """Project exact immutable extracted bytes; no wrapper or role rewriting."""
    _need(type(view_receipt) is pem.EarlyPemSourceView and original_capture_header_identity_bound is False,
          "genuine_pem_view_and_original_header_quarantine_required")
    _digest(capture_result_sha256)
    target = _target(request)
    view = view_receipt.to_payload()
    _need(view["profile"] == pem.PROFILE and view["sgml_or_xml_normalized"] is False
          and view["roles_reordered"] is False and view["authority"] == pem._authority(),
          "exact_unmodified_pem_profile_required")
    projection = project_sec_complete_submission(target, view_receipt.source_view_bytes)
    context = {"request": json.loads(_raw(request)), "capture_result_sha256": capture_result_sha256,
        "original_capture_header_identity_bound": False}
    payload = _bridge_payload(context, view, projection.to_payload(), projection.sha256)
    result = ProjectedPemParent(view_receipt, projection, _raw(context), _raw(payload), _TOKEN)
    object.__setattr__(result, "_factory_bytes", result._payload_bytes)
    result.to_payload()
    return result


@dataclass(frozen=True, slots=True)
class PemSourceViewInventory:
    _parents: tuple[ProjectedPemParent, ...] = field(repr=False)
    _payload_bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self):
        _need(type(self) is PemSourceViewInventory and self._token is _TOKEN
              and type(self._parents) is tuple and self._factory_bytes == self._payload_bytes,
              "genuine_unchanged_pem_inventory_required")
        observed = _inventory_payload(self._parents)
        _need(_raw(observed) == self._payload_bytes, "pem_inventory_changed")
        return observed

    @property
    def sha256(self):self.to_payload();return _sha(self._payload_bytes)

    def frozen_projections_for_v2(self):
        self.to_payload()
        return tuple(parent.frozen_source_view_projection for parent in self._parents)


def _inventory_payload(parents):
    _need(type(parents) is tuple and len(parents) <= MAX_SELECTED_PARENTS
          and all(type(parent) is ProjectedPemParent for parent in parents), "bounded_genuine_pem_bridge_tuple_required")
    rows = [parent.to_payload() for parent in parents]
    accessions = [row["request"]["accession_number"] for row in rows]
    _need(len(set(accessions)) == len(rows), "duplicate_pem_corroborating_accession_refused")
    order = [(row["request"]["filing_date"], row["request"]["accession_number"], row["request"]["source_record_ordinal"])
             for row in rows]
    _need(all(before < after for before, after in zip(order, order[1:])), "pem_inventory_source_order_refused")
    original_bytes = sum(row["original_raw_parent"]["size_bytes"] for row in rows)
    view_bytes = sum(row["derived_sec_document_source_view"]["size_bytes"] for row in rows)
    _need(original_bytes <= v2.MAX_CORROBORATING_BYTES and view_bytes <= v2.MAX_CORROBORATING_BYTES,
          "existing_v2_aggregate_corroboration_byte_bound_refused")
    return {"schema": SCHEMA + "/source-view-inventory", "evidence_epoch": EVIDENCE_EPOCH,
        "rows": rows, "parent_count": len(rows), "original_parent_bytes": original_bytes,
        "derived_source_view_bytes": view_bytes, "ordered_bridges_sha256": _sha(_raw(rows)),
        "v2_input_identity_kind": "genuine_frozen_projection_of_derived_view_not_original_whole_body",
        "whole_original_parent_admission": False, "authority": _authority()}


def build_pem_source_view_inventory(parents):
    payload = _inventory_payload(parents)
    result = PemSourceViewInventory(parents, _raw(payload), _TOKEN)
    object.__setattr__(result, "_factory_bytes", result._payload_bytes)
    result.to_payload()
    return result


@dataclass(frozen=True, slots=True)
class PemQuarterReassessment:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self):
        _need(type(self) is PemQuarterReassessment and self._token is _TOKEN
              and type(self._bytes) is bytes and self._factory_bytes == self._bytes,
              "genuine_unchanged_pem_quarter_assessment_required")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


def _source_descriptor(snapshot, census, filing, item):
    request = original.capture._request(item["request"])
    _need(filing is not None and filing["relevant_form4_or_amendment"] is True
          and request["period"] == census.period
          and all(request[key] == filing[key] for key in ("accession_number", "form_type", "filing_date", "issuer_cik", "source_record_ordinal"))
          and request["filing_metadata_sha256"] == _sha(_raw(filing))
          and request["quarterly_zip_sha256"] == snapshot.identity.raw_archive_sha256
          and request["submission_member_sha256"] == next(table.raw_member_sha256 for table in snapshot.identity.tables
              if table.table_name == "SUBMISSION.tsv"), "original_filing_descriptor_binding_refused")
    return request


def assess_2006q1_pem_source_view_identity(snapshot, census, descriptors, *,
        expected_capture_report_sha256, fixture_only):
    """Full population accounting in a new, explicitly source-view-only epoch."""
    _digest(expected_capture_report_sha256)
    _need(type(fixture_only) is bool and type(descriptors) is tuple
          and len(descriptors) <= MAX_SELECTED_PARENTS, "bounded_parent_descriptor_tuple_required")
    _need(census.period == "2006Q1" and snapshot.identity.year == 2006 and snapshot.identity.quarter == 1,
          "fixed_2006q1_source_context_required")
    baseline = v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    filings = original._source_filings(snapshot, baseline)
    forms = {form: sum(row["form_type"] == form for row in baseline["rows"]) for form in original.capture.bootstrap.locators.FORMS}
    if not fixture_only:
        _need(len(descriptors) == 64 and baseline["submission_count"] == 83_657
              and forms == {"3": 5694, "3/A": 534, "4": 68520, "4/A": 3159, "5": 5539, "5/A": 211}
              and snapshot.identity.raw_archive_sha256 == original.preparation.EXPECTED_ZIP_SHA256,
              "exact_actual_six_form_population_required")
    bridges, ledger, seen, previous, total_bytes = [], [], set(), None, 0
    for ordinal, item in enumerate(descriptors):
        _need(type(item) is dict and set(item) == _DESCRIPTOR_KEYS and type(item["prefix_ordinal"]) is int
              and item["prefix_ordinal"] == ordinal and type(item["request"]) is dict,
              "selected_parent_descriptor_shape_or_order_refused")
        request = _source_descriptor(snapshot, census, filings.get(item["request"].get("accession_number")), item)
        _need(item["request_sha256"] == _sha(_raw(request)) and request["accession_number"] not in seen,
              "request_hash_or_duplicate_accession_refused")
        seen.add(request["accession_number"])
        order = (request["filing_date"], request["accession_number"], request["source_record_ordinal"])
        _need(previous is None or previous < order, "selected_prefix_order_refused");previous = order
        _need(item["header_identity_bound"] is False, "original_header_quarantine_must_stay_false")
        if not fixture_only:
            _need(request["submission_inventory_sha256"] == original.capture.bootstrap.custody.INVENTORY_SHA256
                  and request["master_decoded_sha256"] == original.capture.bootstrap.locators.RETAINED_MASTER_SHA256
                  and request["master_receipt_sha256"] == original.capture.bootstrap.MASTER_RECEIPT_SHA256,
                  "actual_original_capture_source_anchors_refused")
        row = {"prefix_ordinal": ordinal, "source_record_ordinal": request["source_record_ordinal"],
            "accession_number": request["accession_number"], "request_sha256": item["request_sha256"],
            "original_capture_result_sha256": item["result_sha256"],
            "original_capture_terminal_disposition": item["terminal_disposition"],
            "original_capture_header_identity_bound": False, "original_capture_header_quarantine_preserved": True,
            "original_raw_parent": None, "source_view": None, "projection_bridge": None, "quarantine_code": None}
        raw = item["raw_bytes"]
        if raw is None:
            _need(item["body_sha256"] is None and item["body_size_bytes"] is None
                  and item["terminal_disposition"] in {"planned_unattempted", "http_refused_no_retry",
                      "ambiguous_transport_failure_no_retry", "response_privacy_framing_or_custody_refused_no_retry"}
                  and (item["result_sha256"] is None) is (item["terminal_disposition"] == "planned_unattempted"),
                  "unavailable_parent_descriptor_refused")
            if item["result_sha256"] is not None:_digest(item["result_sha256"])
            row.update(disposition="source_view_unavailable", quarantine_code=item["terminal_disposition"])
        else:
            _need(type(raw) is bytes and type(item["body_size_bytes"]) is int and item["body_size_bytes"] == len(raw)
                  and 0 < len(raw) <= pem.MAX_ORIGINAL_BODY_BYTES and item["body_sha256"] == _sha(raw)
                  and item["terminal_disposition"] == "complete_raw_response_retained_header_quarantined",
                  "original_body_custody_or_terminal_binding_refused")
            _digest(item["result_sha256"])
            total_bytes += len(raw)
            _need(total_bytes <= v2.MAX_CORROBORATING_BYTES, "existing_v2_aggregate_parent_byte_bound_refused")
            row["original_raw_parent"] = {"sha256": item["body_sha256"], "size_bytes": len(raw)}
            try:view = pem.build_early_pem_source_view(raw, expected_original_body_sha256=item["body_sha256"])
            except pem.EarlyPemSourceViewError:
                row.update(disposition="original_pem_profile_quarantined", quarantine_code="exact_pem_outer_envelope_profile_refused")
            else:
                row["source_view"] = view.to_payload()
                try:bridge = project_genuine_pem_source_view(request, view, capture_result_sha256=item["result_sha256"])
                except SecCompleteSubmissionError as error:
                    code = ("legacy_blank_separator_refused" if str(error) == "REFUSED: legacy header blank line is not a section separator"
                        else original._parser_refusal_code(error))
                    row.update(disposition="source_view_frozen_parser_quarantined", quarantine_code=code)
                else:
                    bridges.append(bridge)
                    row.update(disposition="source_view_projected_noncanonical", projection_bridge=bridge.to_payload())
        ledger.append(row)
    inventory = build_pem_source_view_inventory(tuple(bridges))
    inside = v2.assess_ib1c_v2_quarter_identity(snapshot, census, inventory.frozen_projections_for_v2()).to_payload()
    _need(type(inside["rows"]) is list and len(inside["rows"]) == len(baseline["rows"])
          and inside["submission_count"] == baseline["submission_count"]
          and all(type(inside[key]) is int and inside[key] >= 0 for key in ("submission_count", "corroborated_count", "quarantined_count"))
          and _raw(inside["authority"]) == _raw(v2._authority())
          and inside["accounting_sha256"] == hash_payload(inside["rows"]), "full_source_view_v2_accounting_refused")
    _need(all(type(row) is dict and row.get("disposition") in
              {"quarantined", "corroborated_noncanonical"} for row in inside["rows"]),
          "full_source_view_v2_row_disposition_refused")
    disposition_counts = Counter(row["disposition"] for row in inside["rows"])
    _need(inside["corroborated_count"] == disposition_counts["corroborated_noncanonical"]
          and inside["quarantined_count"] == disposition_counts["quarantined"]
          and inside["submission_count"] == sum(disposition_counts.values()),
          "full_source_view_v2_row_count_mismatch_refused")
    lookup = {row["accession_number"]: row for row in ledger}
    rows = []
    for prior, current in zip(baseline["rows"], inside["rows"], strict=True):
        _need((prior["accession_number"], prior["source_record_ordinal"]) ==
              (current["accession_number"], current["source_record_ordinal"]), "full_source_row_identity_changed")
        row = json.loads(_raw(current));selected = lookup.get(row["accession_number"])
        row["v2_inner_assessment_disposition"] = row["disposition"]
        row["original_parent_custody"] = None if selected is None else {
            "original_raw_parent": selected["original_raw_parent"],
            "original_capture_result_sha256": selected["original_capture_result_sha256"],
            "original_capture_header_identity_bound": False, "original_capture_header_quarantine_preserved": True}
        row["source_view_qualification"] = None if selected is None else {
            "disposition": selected["disposition"], "quarantine_code": selected["quarantine_code"],
            "source_view": selected["source_view"], "projection_bridge": selected["projection_bridge"]}
        row["whole_original_parent_admitted"] = False
        if row["disposition"] == "corroborated_noncanonical":
            _need(selected is not None and selected["projection_bridge"] is not None
                  and row["corroboration"]["parent_sha256"] == selected["projection_bridge"]
                    ["derived_sec_document_source_view"]["sha256"], "derived_v2_parent_identity_bridge_missing")
            row["disposition"] = "source_view_corroborated_noncanonical"
            row["corroboration_identity_kind"] = "derived_view_not_original_complete_parent"
        else:row["corroboration_identity_kind"] = None
        rows.append(row)
    counts = {"source_filings": len(rows), "target_filings": forms["4"] + forms["4/A"],
        "context_filings": sum(forms[form] for form in ("3", "3/A", "5", "5/A")),
        "selected_parents": len(ledger), "original_bodies_retained": sum(row["original_raw_parent"] is not None for row in ledger),
        "exact_pem_source_views": sum(row["source_view"] is not None for row in ledger),
        "frozen_source_view_projections": len(bridges),
        "pem_profile_quarantined": sum(row["disposition"] == "original_pem_profile_quarantined" for row in ledger),
        "source_view_parser_quarantined": sum(row["disposition"] == "source_view_frozen_parser_quarantined" for row in ledger),
        "source_view_unavailable": sum(row["disposition"] == "source_view_unavailable" for row in ledger),
        "source_view_corroborated_noncanonical": inside["corroborated_count"],
        "quarantined_filings": inside["quarantined_count"], "original_parent_bytes": total_bytes,
        "original_body_admitted": 0}
    _need(counts["original_bodies_retained"] + counts["source_view_unavailable"] == counts["selected_parents"]
          and counts["frozen_source_view_projections"] + counts["source_view_parser_quarantined"] == counts["exact_pem_source_views"]
          and counts["exact_pem_source_views"] + counts["pem_profile_quarantined"] == counts["original_bodies_retained"]
          and counts["source_view_corroborated_noncanonical"] + counts["quarantined_filings"] == counts["source_filings"],
          "complete_source_view_population_partition_refused")
    body = {"schema": SCHEMA, "evidence_epoch": EVIDENCE_EPOCH, "fixture_only": fixture_only,
        "period": "2006Q1", "source_identity_kind": "original_raw_body_to_exact_view_to_frozen_projection_bridge",
        "capture_report_sha256": expected_capture_report_sha256,
        "parsed_snapshot_id": snapshot.identity.snapshot_id, "parsed_lineage_sha256": snapshot.identity.lineage_hash,
        "census_quarter_sha256": hash_payload(census.to_payload()), "form_counts": forms,
        "source_view_profile": pem.PROFILE, "parent_qualification_ledger": ledger,
        "parent_qualification_ledger_sha256": _sha(_raw(ledger)), "source_view_inventory": inventory.to_payload(),
        "source_view_inventory_sha256": inventory.sha256, "v2_source_view_assessment_sha256": hash_payload(inside),
        "v2_source_view_assessment_kind": inside["kind"], "v2_source_view_row_accounting_sha256": inside["accounting_sha256"],
        "rows": rows, "rows_sha256": _sha(_raw(rows)), "counts": counts,
        "whole_original_parent_identity_sha256": None, "whole_quarter_identity_sha256": None,
        "v2_contract_alone_admits_original_whole_bodies": False,
        "original_capture_header_quarantines_unchanged": True, "authority": _authority()}
    encoded = _raw(body)
    _need(len(encoded) <= MAX_OUTPUT_BYTES, "full_source_view_assessment_output_bound_refused")
    result = PemQuarterReassessment(encoded, _TOKEN)
    object.__setattr__(result, "_factory_bytes", encoded)
    result.to_payload()
    return result
