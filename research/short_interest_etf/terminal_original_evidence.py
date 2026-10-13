"""Private deterministic source quotations, never terminal-cash admission.

Potential financial/class/payment language is retained with exact normalized
text spans and raw-byte provenance. No regex decides which holders are paid,
whether a payment happened, a cash-availability clock or a terminal payoff.
"""
from __future__ import annotations

import dataclasses
from html.parser import HTMLParser
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp

MAXIMUM_BYTES = 16 * 1024 * 1024
MAXIMUM_SPANS_PER_CATEGORY = 128
QUOTE_RADIUS = 320
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MEDIA = {"text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml"}
_CUES = (
    ("consideration_language", r"\bper\s+share\b|\beach\s+share\b|\bconsideration\b"),
    ("class_eligibility_language", r"\bcommon\s+stock\b|\bpreferred\s+stock\b|\bclass\s+[A-Z]\b"),
    ("exclusion_or_election_language", r"\bexclud(?:e[ds]?|ing)\b|\bexcept\b|\bappraisal\b|\belect(?:ion|ed|s)?\b|\btreasury\b"),
    ("payment_language", r"\bpa(?:id|yment|yable)\b|\bpaying\s+agent\b|\bsurrender\b|\bdistribut(?:ion|ed|ions)\b|\bsettlement\b"),
    ("effective_or_completion_language", r"\beffective\s+time\b|\bcompleted?\b|\bclosing\b"),
)
_MONEY = re.compile(r"(?:US\$|USD|\$)\s*[0-9][0-9,]*(?:\.[0-9]+)?", re.IGNORECASE)
_DATE = re.compile(r"\b(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+[0-9]{1,2},?\s+[0-9]{4})\b", re.IGNORECASE)
_BLOCKS = {"p", "div", "br", "tr", "td", "th", "li", "section", "table", "blockquote", "hr", "h1", "h2", "h3", "h4", "h5", "h6"}
_SUPPRESSED = {"script", "style", "template", "noscript"}


class TerminalOriginalEvidenceError(ValueError):
    """Fixed local reasons never contain private source text."""


def _require(value, reason):
    if not value:
        raise TerminalOriginalEvidenceError("REFUSED: " + reason)


def _sha(value):
    _require(type(value) is str and _SHA.fullmatch(value) is not None, "SHA256_required")


def _clock(value):
    _require(type(value) is str and value.endswith("Z"), "UTC_Z_clock_required")
    try:
        return parse_utc_timestamp(value, "source_clock")
    except (ValueError, TypeError):
        raise TerminalOriginalEvidenceError("REFUSED: UTC_Z_clock_required") from None


def _authority():
    return {"source_only": True, "semantic_admission": False, "terminal_economics_admitted": False,
            "payment_cash_settlement_verified": False, "historical_share_class_binding_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "trading_authority": False,
            "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def _policy():
    return {"schema": "si-terminal-original-evidence-policy-v1", "maximum_document_bytes": MAXIMUM_BYTES,
            "text_rule": "strict_declared_UTF8_or_default_UTF8_no_lossy_decode_HTMLParser_entities_block_spaces_suppress_scripts_styles_templates_noscript_whitespace_collapse",
            "quote_rule": "exact_normalized_character_span_and_UTF8_digest_bound_to_raw_document_hash",
            "categories": [list(item) for item in _CUES], "quote_radius_characters": QUOTE_RADIUS,
            "maximum_spans_per_category": MAXIMUM_SPANS_PER_CATEGORY,
            "truncation_rule": "retain_total_cue_count_and_explicit_unquoted_count_never_claim_complete_semantics",
            "numeric_rule": "lexical_currency_number_and_date_tokens_only_no_computation_or_unit_assignment",
            "admission_rule": "phrases_never_create_class_eligibility_payoff_payment_date_or_cash_available_clock",
            "source_rule": "protected_reader_required_for_original_custody_issuer_not_share_class_authority",
            "authority": _authority()}


PROTOCOL_SHA256 = "4b123321129531797bc90063530818f543c6e3b4bf31e5b716908b4aac1e67c6"


def evidence_protocol():
    value = _policy()
    _require(hash_payload(value) == PROTOCOL_SHA256, "frozen_evidence_policy_changed")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "duplicate_descriptor_key")
        result[key] = value
    return result


def _descriptor(raw):
    _require(type(raw) is str, "descriptor_canonical_JSON_required")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(TerminalOriginalEvidenceError("REFUSED: descriptor_nonfinite")))
    except (UnicodeError, ValueError):
        raise TerminalOriginalEvidenceError("REFUSED: descriptor_canonical_JSON_required") from None
    fields = {"request_id", "method", "url", "headers", "case", "issuer_CIK", "filing_date", "accession_number", "source_row_origin"}
    _require(type(value) is dict and set(value) == fields and canonical_json(value) == raw, "descriptor_shape")
    _require(type(value["case"]) is str and value["case"] in {"TWTR", "FRC"} and value["request_id"] == "original-" + value["case"]
             and value["method"] == "GET", "descriptor_case_or_method")
    url = value["url"]
    _require(type(url) is str and re.fullmatch(r"https://www\.sec\.gov/Archives/[A-Za-z0-9_./-]+", url) is not None
             and all(part not in {"", ".", ".."} for part in url.split("/Archives/", 1)[1].split("/")), "descriptor_SEC_origin")
    _require(type(value["issuer_CIK"]) is str and re.fullmatch(r"[0-9]{10}", value["issuer_CIK"]) is not None
             and int(value["issuer_CIK"]) > 0, "descriptor_issuer_CIK")
    _require(type(value["accession_number"]) is str and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", value["accession_number"]) is not None,
             "descriptor_accession")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedTerminalOriginal:
    descriptor_json: str = dataclasses.field(repr=False)
    descriptor_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    raw_sha256: str
    received_at: str
    content_type: str
    original_protocol_sha256: str
    original_report_sha256: str

    def __post_init__(self):
        _require(type(self) is CapturedTerminalOriginal, "exact_original_type_required")
        descriptor = _descriptor(self.descriptor_json)
        for digest in (self.descriptor_sha256, self.raw_sha256, self.original_protocol_sha256, self.original_report_sha256):
            _sha(digest)
        _require(hash_payload(descriptor) == self.descriptor_sha256, "descriptor_digest_mismatch")
        _require(type(self.raw) is bytes and 0 < len(self.raw) <= MAXIMUM_BYTES
                 and hash_bytes(self.raw) == self.raw_sha256, "immutable_original_bytes_mismatch")
        _clock(self.received_at)
        _require(type(self.content_type) is str and len(self.content_type) <= 256
                 and all(32 <= ord(c) <= 126 for c in self.content_type)
                 and self.content_type.split(";", 1)[0].strip().lower() in _MEDIA, "original_media_refused")


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.suppressed = [], []

    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            self.suppressed.append(tag)
        elif tag in _SUPPRESSED:
            self.suppressed.append(tag)
        elif tag in _BLOCKS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag in self.suppressed:
                self.suppressed = self.suppressed[:self.suppressed.index(tag)]
        elif tag in _BLOCKS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def _text(document):
    charset = re.search(r"(?:^|;)\s*charset\s*=\s*\"?([^;\"\s]+)", document.content_type, re.IGNORECASE)
    _require(charset is None or charset.group(1).lower() in {"utf-8", "utf8"}, "unsupported_declared_encoding")
    try:
        decoded = document.raw.decode("utf-8-sig")
    except UnicodeError:
        raise TerminalOriginalEvidenceError("REFUSED: original_not_UTF8") from None
    if document.content_type.split(";", 1)[0].strip().lower() == "text/plain":
        value = decoded
    else:
        parser = _TextParser()
        parser.feed(decoded)
        parser.close()
        value = "".join(parser.parts)
    return re.sub(r"\s+", " ", value).strip()


def _span(text, first, last):
    quote = text[first:last]
    return {"start_character": first, "end_character": last, "text": quote,
            "UTF8_sha256": hash_bytes(quote.encode("utf-8"))}


def _document(document):
    document.__post_init__()
    text = _text(document)
    assertions, inventory = [], []
    text_sha256 = hash_bytes(text.encode("utf-8"))
    for category, pattern in _CUES:
        total = 0
        for match in re.finditer(pattern, text, re.IGNORECASE):
            total += 1
            if total > MAXIMUM_SPANS_PER_CATEGORY:
                continue
            first, last = max(0, match.start() - QUOTE_RADIUS), min(len(text), match.end() + QUOTE_RADIUS)
            lexical = []
            for kind, token_pattern in (("currency_number_unclassified", _MONEY), ("date_unclassified", _DATE)):
                for token in token_pattern.finditer(text, first, last):
                    lexical.append({"kind": kind, "span": _span(text, token.start(), token.end()),
                                    "financial_or_payment_meaning_admitted": False})
            assertion_id = hash_payload({"policy_sha256": PROTOCOL_SHA256,
                                         "raw_document_sha256": document.raw_sha256,
                                         "normalized_text_UTF8_sha256": text_sha256,
                                         "category": category, "cue_start": match.start(), "cue_end": match.end()})
            assertions.append({"assertion_id": assertion_id, "category": category, "quote": _span(text, first, last),
                               "cue": _span(text, match.start(), match.end()), "lexical_candidates": lexical,
                               "semantic_status": "unreviewed_source_language_not_economic_assertion",
                               "consideration_cash_per_share": None, "eligible_share_class": None,
                               "payment_date": None, "effective_cash_available_at": None,
                               "authority": _authority()})
        inventory.append({"category": category, "total_cues": total,
                          "quoted_cues": min(total, MAXIMUM_SPANS_PER_CATEGORY),
                          "unquoted_cues": max(0, total - MAXIMUM_SPANS_PER_CATEGORY)})
    return {"descriptor": _descriptor(document.descriptor_json), "descriptor_sha256": document.descriptor_sha256,
            "raw_document_sha256": document.raw_sha256, "received_at": document.received_at,
            "content_type": document.content_type, "original_protocol_sha256": document.original_protocol_sha256,
            "original_report_sha256": document.original_report_sha256,
            "normalized_text": text, "normalized_text_UTF8_sha256": text_sha256,
            "cue_inventory": inventory, "assertions": assertions,
            "normalization_is_not_browser_layout_or_filing_semantic_validation": True,
            "authority": _authority()}


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalOriginalEvidence:
    documents: tuple[CapturedTerminalOriginal, ...] = dataclasses.field(repr=False)
    retrieved_at: str
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        _require(type(self) is TerminalOriginalEvidence, "exact_evidence_type_required")
        evidence_protocol()
        _require(type(self.documents) is tuple and 0 < len(self.documents) <= 2
                 and all(type(item) is CapturedTerminalOriginal for item in self.documents), "one_or_two_exact_originals_required")
        end = _clock(self.retrieved_at)
        descriptors, hashes = [], []
        for document in self.documents:
            document.__post_init__()
            _require(_clock(document.received_at) <= end, "evidence_clock_precedes_capture")
            descriptors.append(document.descriptor_sha256)
            hashes.append(document.raw_sha256)
        _require(len(set(descriptors)) == len(descriptors) and len(set(hashes)) == len(hashes), "duplicate_original_evidence")
        payload = {"schema": "si-terminal-original-private-evidence-v1", "protocol_sha256": PROTOCOL_SHA256,
                   "retrieved_at": self.retrieved_at, "documents": [_document(item) for item in self.documents],
                   "source_custody": "requires_separately_verified_protected_original_reader",
                   "scope": "bounded_source_language_not_full_terminal_coverage_or_cashflow_admission", "authority": _authority()}
        payload["report_sha256"] = hash_payload(payload)
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    def to_payload(self):
        _require(type(self) is TerminalOriginalEvidence, "exact_evidence_type_required")
        _require(type(self._payload_json) is str, "exact_sealed_JSON_text_required")
        rebuilt = TerminalOriginalEvidence(self.documents, self.retrieved_at)
        _require(rebuilt._payload_json == self._payload_json, "sealed_evidence_changed")
        return json.loads(self._payload_json)

    @property
    def sha256(self):
        return self.to_payload()["report_sha256"]


def qualify_terminal_original_evidence(documents, *, retrieved_at):
    return TerminalOriginalEvidence(documents, retrieved_at)
