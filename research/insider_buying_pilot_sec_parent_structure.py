"""Pure supplied-original structural evidence for the separate SEC pilot.

Only the unchanged complete-submission parser examines original header/XML
structure and identifier text. It does not convert transaction financial
fields into numbers, compute signals or admit IB-1C/canonical evidence. This
function neither reads files nor verifies named-file custody; its caller must
hold every actual input in the newly registered isolated worker. No old
operation, unresolved start, source byte or frozen parser is rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import weakref

from research import insider_buying_pilot_sec_parent_audit as audit
from research.insider_buying import sec_complete_submission as frozen


SCHEMA = "insider-pilot-sec-original-parent-structure-v1"
MAX_RECORD_BYTES = 256 * 1024
MAX_BODY_BYTES = frozen.MAX_COMPLETE_SUBMISSION_BYTES
QUARANTINE_CODE = "frozen_complete_submission_structure_or_identity_refused"
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()


class PilotSecParentStructureError(ValueError):
    """Fixed integrity refusals only; never source or exception text."""


def _need(value, code):
    if not value:
        raise PilotSecParentStructureError(code)


def _raw(value):
    return audit._raw(value)


def _sha(value):
    return audit._sha(value)


def _digest(value):
    try:
        return audit._digest(value)
    except audit.PilotSecParentAuditError:
        raise PilotSecParentStructureError("external_digest_required") from None


def _candidate(candidate, expected_candidate_sha256, prior_exposure_evidence):
    try:
        _need(type(candidate) is dict, "exact_candidate_descriptor_required")
        raw = _raw(candidate)
        _need(0 < len(raw) <= MAX_RECORD_BYTES and _sha(raw) == _digest(expected_candidate_sha256),
              "candidate_hash_or_byte_bound_refused")
        # Round-trip is a detached metadata copy, not raw market/source JSON.
        copied = json.loads(raw, parse_float=lambda _: _need(False, "floating_metadata_refused"))
        accession = copied.get("retained_target", {}).get("accession_number")
        body = {"schema": audit.CANDIDATE_SCHEMA, "fixture_only": True,
            "records": [{"accession_number": accession, "candidates": [copied]}], "masters": [],
            "authority": dict(audit._AUTHORITY)}
        validated = audit._candidate_inventory(body)
        _need(copied["retained_target"]["period"] in audit.PERIODS, "pilot_context_period_required")
        _need(copied["body_currently_hash_verified"] is True, "prior_opaque_body_verification_required")
        _need(type(prior_exposure_evidence) is list, "explicit_consumption_evidence_required")
        exposures = {"schema": audit.EXPOSURE_SCHEMA, "records": [{"accession_number": accession,
            "accession_key_sha256": _sha(accession.encode("ascii")), "evidence": prior_exposure_evidence}]}
        evidence = audit._exposures(exposures)[accession]
        _need(len(_raw(evidence)) <= MAX_RECORD_BYTES, "consumption_evidence_byte_bound_refused")
        return validated[accession][0], json.loads(_raw(evidence))
    except PilotSecParentStructureError:
        raise
    except (audit.PilotSecParentAuditError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise PilotSecParentStructureError("candidate_or_consumption_schema_refused") from None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotSecParentStructure:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is PilotSecParentStructure and self._token is _TOKEN
              and _SEALS.get(self) == self._bytes, "genuine_unchanged_structure_record_required")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def validate_pilot_sec_parent_structure(value):
    _need(type(value) is PilotSecParentStructure, "exact_structure_record_type_required")
    return value.to_payload()


def process_candidate(body_raw, candidate, *, expected_candidate_sha256, expected_body_sha256,
                      expected_master_decoded_sha256, prior_exposure_evidence):
    """Recheck one supplied original; return structural evidence or quarantine.

    Hash/schema/custody-lineage inconsistencies REFUSE the operation. A genuine
    parser rejection instead conserves the body as a fixed-code quarantine.
    Header timestamps are verbatim declarations, not official/PIT clocks.
    The original request's CIK is preserved; only the parser comparison target
    receives explicit zero-padding, as in the existing supplied-source v2.
    """
    copied, evidence = _candidate(candidate, expected_candidate_sha256, prior_exposure_evidence)
    body_sha = _digest(expected_body_sha256)
    master_sha = _digest(expected_master_decoded_sha256)
    _need(type(body_raw) is bytes and 0 < len(body_raw) <= MAX_BODY_BYTES, "bounded_exact_original_bytes_required")
    _need(_sha(body_raw) == body_sha and copied["raw_object"]["sha256"] == body_sha
          and copied["raw_object"]["size_bytes"] == len(body_raw), "original_body_hash_or_size_refused")
    request, raw_target = copied["request"], copied["retained_target"]
    for key in ("master_source_sha256", "master_decoded_sha256"):
        _need(key not in request or request[key] == master_sha, "retained_request_master_binding_refused")
    try:
        comparison_target = frozen.SecCompleteSubmissionTarget(
            period=raw_target["period"], accession_number=raw_target["accession_number"],
            form_type=raw_target["form_type"], filing_date=raw_target["filing_date"],
            issuer_cik=raw_target["issuer_cik"].zfill(10), quarterly_index_sha256=master_sha,
            complete_submission_url=copied["request_url"])
    except frozen.SecCompleteSubmissionError:
        raise PilotSecParentStructureError("frozen_comparison_target_refused") from None
    payload = None
    try:
        projection = frozen.project_sec_complete_submission(comparison_target, body_raw)
        _need(type(projection) is frozen.SecCompleteSubmissionProjection
              and projection.raw_bytes == body_raw, "exact_original_projection_required")
        payload = projection.to_payload()  # Fresh full structural reparse.
        _need(payload["target"] == comparison_target.to_payload()
              and payload["raw_parent"]["sha256"] == body_sha
              and payload["raw_parent"]["size_bytes"] == len(body_raw)
              and all(payload["children"][child]["parent_sha256"] == body_sha for child in ("header", "primary_xml")),
              "projection_original_parent_binding_refused")
    except frozen.SecCompleteSubmissionError:
        payload = None
    except PilotSecParentStructureError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise PilotSecParentStructureError("unexpected_structural_parser_refusal") from None
    success = payload is not None
    body = {"schema": SCHEMA, "scope": "supplied_source_structure_not_operational_or_canonical_attestation",
        "candidate_descriptor_sha256": expected_candidate_sha256, "request_sha256": copied["request_sha256"],
        "request": request, "retained_target": raw_target, "frozen_parser_comparison_target": comparison_target.to_payload(),
        "issuer_comparison_padding_applied": raw_target["issuer_cik"] != comparison_target.issuer_cik,
        "raw_request_target_rewritten": False, "source_body_modified": False,
        "expected_master_decoded_sha256": master_sha, "raw_parent": {"sha256": body_sha, "size_bytes": len(body_raw)},
        "retained_control": {key: copied[key] for key in ("root_id", "control_name", "control_sha256")},
        "prior_exposure_evidence": evidence,
        "historical_ambiguous_start_preserved": any(item["state"] == "ambiguous" for item in evidence),
        "original_unmatched_start_resolved": False, "consumed_accession_released_for_redispatch": False,
        "disposition": "original_complete_parent_structurally_bound_noncanonical" if success else
            "original_complete_parent_structure_quarantined_noncanonical",
        "quarantine_code": None if success else QUARANTINE_CODE,
        "full_original_structurally_bound": success, "ownership_xml_identity_structurally_checked": success,
        "frozen_parser_version": frozen.SEC_COMPLETE_SUBMISSION_VERSION,
        "frozen_projection_sha256": None if payload is None else _sha(_raw(payload)),
        "children": None if payload is None else payload["children"],
        "source_declared_fields": None if payload is None else payload["source_fields"],
        "source_declared_acceptance_is_not_official_or_pit": True,
        "xml_financial_text_may_be_structurally_decoded": True,
        "financial_numeric_fields_converted": False, "financial_values_projected": False,
        "canonical_or_ib1c_identity_admitted": False, "named_file_custody_verified_here": False,
        "authority": dict(audit._AUTHORITY)}
    raw = _raw(body)
    _need(len(raw) <= MAX_RECORD_BYTES, "structure_record_byte_bound_refused")
    result = PilotSecParentStructure(raw, _TOKEN);_SEALS[result] = raw
    return result
