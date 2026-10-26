"""Pure structural projection of the full, supplied early-2006 PEM parent.

This additive contract directly coordinates the two bounded legacy header
orders. It never rewrites a role, strips a raw parent, instantiates a frozen
projection with substitute bytes, or changes frozen parser globals. Original
body, embedded document and verbatim children have distinct byte identities.
PEM syntax and supplied-source agreement are not authenticity, PIT, rights,
canonical admission, complete-corpus or backtesting evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re

from research.insider_buying import sec_complete_submission as frozen
from research import insider_buying_sec_early_pem_source_view_v1 as pem


PROFILE = "INSETF-EARLY-ORIGINAL-PEM-COMPLETE-PARENT-v1"
MAX_ORIGINAL_PARENTS = 64
MAX_ORIGINAL_BODY_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_ORIGINAL_BYTES = 64 * 1024 * 1024
MAX_SOURCE_RECORD_ORDINAL = 250_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PATH = re.compile(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z")
_REQUEST_KEYS = frozenset({
    "period", "accession_number", "form_type", "filing_date", "issuer_cik",
    "archive_path", "url", "source_record_ordinal", "accession_key_sha256",
    "filing_metadata_sha256", "submission_inventory_sha256",
    "quarterly_zip_sha256", "submission_member_sha256",
    "master_decoded_sha256", "master_receipt_sha256",
})
_TOKEN = object()


class EarlyOriginalParentError(ValueError):
    """Fixed refusal codes only; never supplied source or exception text."""


def _need(condition, code):
    if not condition:
        raise EarlyOriginalParentError(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "external_digest_required")
    return value


def _target(request):
    # The retained capture's exact 15-field request contract, validated here
    # without importing its acquisition-capable transport/credential front.
    _need(type(request) is dict and set(request) == _REQUEST_KEYS, "request_shape_refused")
    _need(all(type(value) is str for key, value in request.items()
              if key != "source_record_ordinal")
          and type(request["source_record_ordinal"]) is int
          and 1 <= request["source_record_ordinal"] <= MAX_SOURCE_RECORD_ORDINAL,
          "request_field_types_or_ordinal_refused")
    _need(request["period"] == "2006Q1"
          and "2006-01-01" <= request["filing_date"] <= "2006-03-31",
          "early_2006q1_request_required")
    for key in _REQUEST_KEYS:
        if key.endswith("sha256"):
            _digest(request[key])
    match = _PATH.fullmatch(request["archive_path"])
    _need(match is not None and int(match.group(1)) > 0
          and match.group(2) == request["accession_number"]
          and request["url"] == "https://www.sec.gov/Archives/" + request["archive_path"],
          "request_locator_refused")
    _need(request["accession_key_sha256"] == _sha(request["accession_number"].encode()),
          "request_accession_key_refused")
    try:
        return frozen.SecCompleteSubmissionTarget(
            period=request["period"], accession_number=request["accession_number"],
            form_type=request["form_type"], filing_date=request["filing_date"],
            issuer_cik=request["issuer_cik"], quarterly_index_sha256=request["master_decoded_sha256"],
            complete_submission_url=request["url"])
    except frozen.SecCompleteSubmissionError:
        raise EarlyOriginalParentError("request_target_identity_refused") from None


def _boundary_lines(lines, *, preceding):
    """Permit short blanks only at explicit observed SGML boundaries."""
    result = []
    index = 0
    while index < len(lines):
        if lines[index] != "":
            result.append(lines[index])
            index += 1
            continue
        end = index
        while end < len(lines) and lines[end] == "":
            end += 1
        _need(end - index <= 2, "legacy_blank_separator_refused")
        previous = result[-1] if result else preceding
        following = lines[end] if end < len(lines) else None
        next_role = frozen._LEGACY_ROLE_LINE.fullmatch(following) if following is not None else None
        after_preamble = previous.startswith("DATE AS OF CHANGE:") and next_role is not None
        after_role = (frozen._LEGACY_ROLE_LINE.fullmatch(previous) is not None
                      and following is not None and frozen._LEGACY_SCOPE.fullmatch(following) is not None)
        after_leaf = (frozen._LEGACY_LEAF.fullmatch(previous) is not None
                      and (following is None or next_role is not None
                           or frozen._LEGACY_SCOPE.fullmatch(following) is not None))
        _need(after_preamble or after_role or after_leaf, "legacy_blank_separator_refused")
        index = end
    return result


def _header_identity(raw, target):
    _need(0 < len(raw) <= frozen.MAX_COMPLETE_HEADER_BYTES
          and all(byte >= 32 or byte in (9, 10) for byte in raw), "original_header_encoding_refused")
    try:
        lines = raw.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError:
        raise EarlyOriginalParentError("original_header_encoding_refused") from None
    _need(len(lines) >= 11 and lines[-1] == "</SEC-HEADER>", "original_header_envelope_refused")
    opener = re.fullmatch(
        r"<SEC-HEADER>([0-9]{10}-[0-9]{2}-[0-9]{6})\.hdr\.sgml : ([0-9]{8})", lines[0])
    _need(opener is not None and opener.group(1) == target.accession_number,
          "original_header_target_refused")
    try:
        frozen._date_digits(opener.group(2).encode(), label="header opener date")
    except frozen.SecCompleteSubmissionError:
        raise EarlyOriginalParentError("original_header_opener_date_refused") from None
    body = lines[1:-1]
    prefix = "<ACCEPTANCE-DATETIME>"
    _need(body[0].startswith(prefix), "original_acceptance_clock_refused")
    accepted = body[0][len(prefix):]
    _need(re.fullmatch(r"[0-9]{14}", accepted) is not None, "original_acceptance_clock_refused")
    try:
        datetime.strptime(accepted, "%Y%m%d%H%M%S")
    except ValueError:
        raise EarlyOriginalParentError("original_acceptance_clock_refused") from None
    preamble = {}
    for expected, line in zip(frozen._LEGACY_PREAMBLE, body[1:7], strict=True):
        match = frozen._LEGACY_FIELD.fullmatch(line)
        _need(match is not None and match.group(1) == expected
              and match.group(2) == match.group(2).strip(), "legacy_preamble_refused")
        preamble[expected] = match.group(2)
    _need(preamble["ACCESSION NUMBER"] == target.accession_number
          and preamble["CONFORMED SUBMISSION TYPE"] == target.form_type
          and preamble["FILED AS OF DATE"] == target.filing_date.replace("-", ""),
          "original_header_target_refused")
    count = preamble["PUBLIC DOCUMENT COUNT"]
    _need(re.fullmatch(r"[1-9][0-9]{0,2}", count) is not None
          and int(count) <= frozen.MAX_COMPLETE_DOCUMENTS, "legacy_document_count_refused")
    try:
        for name in ("CONFORMED PERIOD OF REPORT", "DATE AS OF CHANGE"):
            frozen._date_digits(preamble[name].encode(), label="legacy date")
    except frozen.SecCompleteSubmissionError:
        raise EarlyOriginalParentError("legacy_preamble_date_refused") from None
    roles = _boundary_lines(body[7:], preceding=body[6])
    markers = [(index, match.group(1)) for index, line in enumerate(roles)
               if (match := frozen._LEGACY_ROLE_LINE.fullmatch(line)) is not None]
    order = [name for _, name in markers]
    owner_count = len(markers) - 1
    _need(1 <= owner_count <= frozen.MAX_COMPLETE_OWNERS and markers[0][0] == 0,
          "legacy_role_topology_refused")
    if order == ["REPORTING-OWNER:"] * owner_count + ["ISSUER:"]:
        topology = "owner-first"
    elif order == ["ISSUER:"] + ["REPORTING-OWNER:"] * owner_count:
        topology = "issuer-first"
    else:
        raise EarlyOriginalParentError("legacy_role_topology_refused")
    owners = []
    issuer = None
    try:
        for index, (start, role) in enumerate(markers):
            end = markers[index + 1][0] if index + 1 < len(markers) else len(roles)
            cik = frozen._legacy_role_cik(roles[start + 1:end],
                owner=role == "REPORTING-OWNER:", target=target)
            if role == "ISSUER:":
                issuer = cik
            else:
                owners.append(cik)
    except frozen.SecCompleteSubmissionError:
        raise EarlyOriginalParentError("legacy_role_subsections_refused") from None
    _need(issuer == target.issuer_cik and len(set(owners)) == len(owners),
          "original_header_issuer_or_owner_identity_refused")
    return accepted, tuple(owners), int(count), topology


def _extract(original, target):
    _need(type(original) is bytes and 0 < len(original) <= MAX_ORIGINAL_BODY_BYTES,
          "bounded_original_body_required")
    try:
        view, prefix, suffix = pem._extract(original)
    except pem.EarlyPemSourceViewError:
        raise EarlyOriginalParentError("original_pem_envelope_refused") from None
    try:
        pieces, lines = frozen._split_lines(view)
    except frozen.SecCompleteSubmissionError:
        raise EarlyOriginalParentError("original_document_lines_refused") from None
    opener = pem._DOC.fullmatch(lines[0])
    _need(opener is not None and opener.group(1).decode() == target.accession_number,
          "original_document_target_refused")
    try:
        header_end = lines.index(b"</SEC-HEADER>", 2, len(lines) - 1)
    except ValueError:
        raise EarlyOriginalParentError("original_header_envelope_refused") from None
    header = b"".join(pieces[1:header_end + 1])
    accepted, owners, document_count, topology = _header_identity(header, target)
    position = header_end + 1
    documents = 0
    sequences = set()
    xml_documents = []
    while position < len(lines) - 1:
        _need(documents < frozen.MAX_COMPLETE_DOCUMENTS, "original_document_inventory_refused")
        try:
            end, form, filename, body = frozen._document(lines, pieces, position)
            metadata = lines[position + 1:lines.index(b"<TEXT>", position + 1, end)]
            sequence = next(line.removeprefix(b"<SEQUENCE>").decode("ascii")
                            for line in metadata if line.startswith(b"<SEQUENCE>"))
        except frozen.SecCompleteSubmissionError:
            raise EarlyOriginalParentError("original_document_inventory_refused") from None
        _need(sequence not in sequences, "original_duplicate_document_sequence_refused")
        sequences.add(sequence)
        documents += 1
        if filename.casefold().endswith(".xml"):
            _need(frozen._XML_NAME.fullmatch(filename) is not None
                  and not filename.casefold().startswith("xsl"), "original_xml_filename_refused")
            xml_documents.append((form, filename, body))
        position = end
    _need(documents == document_count and len(xml_documents) == 1,
          "original_document_inventory_refused")
    form, filename, xml = xml_documents[0]
    _need(form == target.form_type and 0 < len(xml) <= frozen.MAX_COMPLETE_XML_BYTES,
          "original_xml_type_or_bound_refused")
    try:
        fields = frozen._xml_fields(xml, target)
    except frozen.SecRawParentProjectionError:
        raise EarlyOriginalParentError("original_xml_identity_or_security_refused") from None
    _need(set(owners) == set(fields["xml_owner_ciks_normalized"]),
          "original_header_xml_owner_conflict")
    return header, xml, filename, accepted, owners, topology, documents, view, prefix, suffix


def _authority():
    return {**frozen._authority(), **pem._authority(),
        **{name: False for name in (
            "whole_original_parent_admitted", "index_membership_verified",
            "canonical_ready", "scale_promotion_authorized", "pilot_ingest_authorized",
            "signal_authorized", "qc_entitlement_verified", "backtest_authorized",
            "outcome_access_authorized")},
        "qc_jobs": 0, "sec_dispatches": 0}


def _payload(request, original, capture_sha):
    target = _target(request)
    header, xml, filename, accepted, owners, topology, count, view, prefix, suffix = _extract(original, target)
    parent_sha = _sha(original)
    return {
        "profile": PROFILE, "request": request, "request_sha256": _sha(_raw(request)),
        "target": target.to_payload(), "capture_result_sha256": _digest(capture_sha),
        "original_raw_parent": {"sha256": parent_sha, "size_bytes": len(original)},
        "embedded_sec_document": {"sha256": _sha(view), "size_bytes": len(view),
            "source_offset_bytes": len(prefix), "source_end_offset_exclusive_bytes": len(original) - len(suffix)},
        "outer_envelope": {"profile": pem.PROFILE, "prefix_sha256": _sha(prefix),
            "prefix_size_bytes": len(prefix), "suffix_sha256": _sha(suffix), "suffix_size_bytes": len(suffix),
            "public_key_base64_structure_checked_only": True, "signature_base64_structure_checked_only": True},
        "children": {
            "header": {"parent_sha256": parent_sha, "sha256": _sha(header), "size_bytes": len(header)},
            "primary_xml": {"parent_sha256": parent_sha, "filename": filename,
                "sha256": _sha(xml), "size_bytes": len(xml)}},
        "source_fields": {"accepted_at_raw": accepted, "header_owner_ciks": list(owners)},
        "header_topology": topology, "document_count": count,
        "full_original_structurally_bound": True, "original_body_unchanged": True,
        "roles_reordered": False, "sgml_or_xml_normalized": False, "source_clocks_normalized": False,
        "scope": "supplied_original_body_structural_identity_only_not_authenticity_or_canonical_admission",
        "authority": _authority(),
    }


@dataclass(frozen=True, slots=True)
class EarlyOriginalParentProjection:
    """Ordinary-mutation factory seal plus full byte reparse, not authentication."""
    _original: bytes = field(repr=False)
    _expected_original_sha256: str
    _context: bytes = field(repr=False)
    _payload_bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self):
        _need(type(self) is EarlyOriginalParentProjection
              and getattr(self, "_token", None) is _TOKEN
              and type(getattr(self, "_payload_bytes", None)) is bytes
              and self._payload_bytes == getattr(self, "_factory_bytes", None)
              and type(getattr(self, "_context", None)) is bytes
              and type(getattr(self, "_original", None)) is bytes
              and type(getattr(self, "_expected_original_sha256", None)) is str,
              "genuine_unchanged_early_original_projection_required")
        _digest(self._expected_original_sha256)
        _need(type(self._original) is bytes and _sha(self._original) == self._expected_original_sha256,
              "externally_bound_original_body_changed")
        try:
            context = json.loads(self._context)
        except (ValueError, UnicodeError):
            raise EarlyOriginalParentError("original_projection_context_refused") from None
        _need(type(context) is dict and set(context) == {"request", "capture_result_sha256"},
              "original_projection_context_refused")
        expected = _payload(context["request"], self._original, context["capture_result_sha256"])
        _need(_raw(context) == self._context, "original_projection_context_changed")
        _need(_raw(expected) == self._payload_bytes, "original_projection_metadata_changed")
        return expected

    @property
    def raw_bytes(self):
        self.to_payload()
        return self._original

    @property
    def target(self):
        return _target(self.to_payload()["request"])

    @property
    def sha256(self):
        self.to_payload()
        return _sha(self._payload_bytes)


def validate_early_original_parent(value):
    """Reject imitation/old view contracts before calling any supplied method."""
    _need(type(value) is EarlyOriginalParentProjection, "genuine_early_original_projection_required")
    return value.to_payload()


def project_early_original_parent(request: dict, original_body: bytes, *,
                                 expected_original_body_sha256: str,
                                 capture_result_sha256: str) -> EarlyOriginalParentProjection:
    """Parse one supplied full PEM body, with no I/O, acquisition or promotion."""
    _digest(expected_original_body_sha256)
    _digest(capture_result_sha256)
    _need(type(original_body) is bytes and 0 < len(original_body) <= MAX_ORIGINAL_BODY_BYTES
          and _sha(original_body) == expected_original_body_sha256, "external_original_body_hash_required")
    _target(request)
    context = _raw({"request": request, "capture_result_sha256": capture_result_sha256})
    copied = json.loads(context)
    payload = _payload(copied["request"], original_body, copied["capture_result_sha256"])
    result = EarlyOriginalParentProjection(original_body, expected_original_body_sha256, context, _raw(payload), _TOKEN)
    object.__setattr__(result, "_factory_bytes", result._payload_bytes)
    result.to_payload()
    return result
