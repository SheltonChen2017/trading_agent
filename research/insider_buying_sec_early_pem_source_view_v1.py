"""Pure lane-local contract for one observed early SEC PEM source-view profile.

The full original HTTP body remains the raw parent. The source view is only
its exact contiguous SEC-DOCUMENT byte span, without rewriting any SGML/XML,
line ending, role order or source clock. PEM/MIC syntax is not signature,
SEC-origin, official publication, PIT, rights or identity verification.
Frozen parsers, acquisition state and IB-1C v2 behavior are not changed.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import re

from research.insider_buying import sec_complete_submission as frozen


PROFILE = "INSETF-EARLY-PEM-EXACT-CONTIGUOUS-SOURCE-VIEW-v1"
MAX_ORIGINAL_BODY_BYTES = 8 * 1024 * 1024
MAX_ORIGINAL_LINES = 100_000
PREFIX_BYTES = 373
SUFFIX_BYTES = 39
PREFIX_LINES = 10
KEY_DECODED_BYTES = 90
SIGNATURE_DECODED_BYTES = 64
BEGIN = b"-----BEGIN PRIVACY-ENHANCED MESSAGE-----"
END = b"-----END PRIVACY-ENHANCED MESSAGE-----"
STANDARD_HEADER_LINES = (
    BEGIN,
    b"Proc-Type: 2001,MIC-CLEAR",
    b"Originator-Name: webmaster@www.sec.gov",
    b"Originator-Key-Asymmetric:",
)
MIC_INFO = b"MIC-Info: RSA-MD5,RSA,"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DOC = re.compile(rb"<SEC-DOCUMENT>([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt : ([0-9]{8})\Z")
_HEADER = re.compile(rb"<SEC-HEADER>([0-9]{10}-[0-9]{2}-[0-9]{6})\.hdr\.sgml : ([0-9]{8})\Z")
_TOKEN = object()


class EarlyPemSourceViewError(ValueError):
    """Fixed codes only, never supplied bytes, names, signature or key data."""


def _need(condition, code):
    if not condition:raise EarlyPemSourceViewError(code)


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _authority():
    return {name: False for name in (
        "signature_verified", "sec_origin_authenticated", "official_acceptance_verified",
        "publication_time_verified", "point_in_time_verified", "rights_verified",
        "historical_identity_verified", "canonical_evidence", "complete_corpus",
        "direct_ib1c_ingest_authorized", "qc_authorized", "backtesting_ready", "execution_authorized",
    )}


def _base64_structure(lines, indices, lengths, decoded_bytes):
    encoded = b""
    for index, length in zip(indices, lengths, strict=True):
        line = lines[index]
        _need(len(line) == length and re.fullmatch(rb" [A-Za-z0-9+/=]+", line),
              "pem_base64_continuation_shape_refused")
        encoded += line[1:]
    try:decoded = base64.b64decode(encoded, validate=True)
    except ValueError:raise EarlyPemSourceViewError("pem_base64_encoding_refused") from None
    _need(len(decoded) == decoded_bytes and base64.b64encode(decoded) == encoded,
          "pem_base64_size_or_canonical_encoding_refused")
    # Decoding here validates framing only. No key format, signature, digest
    # algorithm, issuer, trust anchor or actual cryptographic verification.


def _extract(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_ORIGINAL_BODY_BYTES,
          "bounded_original_body_required")
    _need(raw.endswith(b"\n") and b"\r" not in raw and b"\0" not in raw,
          "observed_lf_only_original_body_required")
    try:pieces, lines = frozen._split_lines(raw)
    except frozen.SecCompleteSubmissionError:raise EarlyPemSourceViewError("original_body_line_profile_refused") from None
    _need(len(lines) <= MAX_ORIGINAL_LINES and len(lines) >= 17,
          "pem_line_count_profile_refused")
    _need(tuple(lines[:4]) == STANDARD_HEADER_LINES and lines[6] == MIC_INFO and lines[9] == b"",
          "exact_standard_pem_header_required")
    _base64_structure(lines, (4, 5), (65, 57), KEY_DECODED_BYTES)
    _base64_structure(lines, (7, 8), (65, 25), SIGNATURE_DECODED_BYTES)
    _need(lines[-1] == END and pieces[-1] == END + b"\n" and lines[-2] == b"</SEC-DOCUMENT>",
          "exact_pem_suffix_required")
    markers = {
        BEGIN: 1, END: 1, b"<SEC-DOCUMENT>": 1, b"</SEC-DOCUMENT>": 1,
        b"<SEC-HEADER>": 1, b"</SEC-HEADER>": 1,
    }
    _need(all(raw.count(marker) == count for marker, count in markers.items()),
          "duplicate_or_ambiguous_pem_sec_marker_refused")
    opener, header = _DOC.fullmatch(lines[PREFIX_LINES]), _HEADER.fullmatch(lines[PREFIX_LINES + 1])
    _need(opener is not None and header is not None and opener.group(1) == header.group(1),
          "inner_document_header_opener_profile_refused")
    for value in (opener.group(2), header.group(2)):
        try:frozen._date_digits(value, label="source-view opener date")
        except frozen.SecCompleteSubmissionError:raise EarlyPemSourceViewError("inner_source_opener_date_shape_refused") from None
    prefix = b"".join(pieces[:PREFIX_LINES])
    view = b"".join(pieces[PREFIX_LINES:-1])
    suffix = pieces[-1]
    _need(len(prefix) == PREFIX_BYTES and len(suffix) == SUFFIX_BYTES
          and prefix + view + suffix == raw and view == raw[PREFIX_BYTES:len(raw)-SUFFIX_BYTES],
          "exact_contiguous_source_view_relation_refused")
    return view, prefix, suffix


@dataclass(frozen=True, slots=True)
class EarlyPemSourceView:
    """Weak factory seal with full byte reparse, not adversarial authentication."""
    _original: bytes = field(repr=False)
    _expected_original_sha256: str
    _view: bytes = field(repr=False)
    _payload: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_payload: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def _validated(self):
        _need(type(self) is EarlyPemSourceView and self._token is _TOKEN
              and type(self._payload) is bytes and self._payload == self._factory_payload,
              "genuine_unchanged_pem_source_view_required")
        _need(type(self._expected_original_sha256) is str and _SHA.fullmatch(self._expected_original_sha256)
              and _sha(self._original) == self._expected_original_sha256,
              "externally_bound_original_body_changed")
        view, prefix, suffix = _extract(self._original)
        expected = _payload(self._original, view, prefix, suffix)
        _need(type(self._view) is bytes and self._view == view and self._payload == _raw(expected),
              "pem_view_or_derived_metadata_changed")
        return expected

    def to_payload(self):return self._validated()

    @property
    def original_bytes(self):
        self._validated();return self._original

    @property
    def source_view_bytes(self):
        self._validated();return self._view

    @property
    def sha256(self):
        self._validated();return _sha(self._payload)


def _payload(original, view, prefix, suffix):
    return {"profile": PROFILE,
        "scope": "one_observed_early_pem_outer_envelope_not_general_pem_or_all_sec_history",
        "support": "exact_contiguous_wrapper_extraction_only; no_signature_authenticity_publication_PIT_or_rights_verification",
        "original_raw_parent": {"sha256": _sha(original), "size_bytes": len(original)},
        "derived_sec_document_source_view": {"sha256": _sha(view), "size_bytes": len(view),
            "source_offset_bytes": PREFIX_BYTES, "source_end_offset_exclusive_bytes": len(original)-SUFFIX_BYTES,
            "byte_relation": "exact_contiguous_original_span"},
        "outer_envelope": {"prefix_sha256": _sha(prefix), "prefix_size_bytes": len(prefix),
            "suffix_sha256": _sha(suffix), "suffix_size_bytes": len(suffix),
            "public_key_base64_structure_checked_only": True,
            "signature_base64_structure_checked_only": True},
        "original_body_unchanged": True, "sgml_or_xml_normalized": False, "roles_reordered": False,
        "source_clocks_normalized": False, "full_xml_or_header_identity_assessed": False,
        "authority": _authority()}


def build_early_pem_source_view(original_body, *, expected_original_body_sha256):
    _need(type(original_body) is bytes and type(expected_original_body_sha256) is str
          and _SHA.fullmatch(expected_original_body_sha256) is not None
          and _sha(original_body) == expected_original_body_sha256, "external_original_body_hash_required")
    view, prefix, suffix = _extract(original_body)
    result = EarlyPemSourceView(original_body, expected_original_body_sha256, view,
        _raw(_payload(original_body, view, prefix, suffix)), _TOKEN)
    object.__setattr__(result, "_factory_payload", result._payload)
    result.to_payload()
    return result
