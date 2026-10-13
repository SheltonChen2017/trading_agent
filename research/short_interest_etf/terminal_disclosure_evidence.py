"""Private, source-only inventory of a prospectively frozen disclosure pilot.

Core 8-K Items text is not an exhibit, a payment clock, a complete terminal
contract or authority to evaluate outcomes. This pure module never follows a
filing URL, extracts financial terms, or reads a provider/credential/file.
"""
from __future__ import annotations

import dataclasses
from datetime import date
import json
import re
from typing import Any

from data.hashing import hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp


WINDOWS = (("TWTR", "2022-10-01", "2022-11-30"),
           ("FRC", "2023-04-01", "2023-06-30"))
REQUEST_IDS = ("index-TWTR", "text-TWTR", "index-FRC", "text-FRC")
MAXIMUM_REQUESTS = 4
MAXIMUM_RESPONSE_BYTES = 4 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{10}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_SEC_URL = re.compile(r"(https?)://www\.sec\.gov/Archives/[A-Za-z0-9_./-]+\Z")


class TerminalDisclosureError(ValueError):
    """Fixed reasons only; no provider text or private identifiers in errors."""


def _refuse(reason: str) -> TerminalDisclosureError:
    return TerminalDisclosureError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {"source_only": True, "source_admitted": False,
            "point_in_time_data": False, "terminal_economics_admitted": False,
            "payment_cash_settlement_verified": False,
            "outcome_access_authorized": False, "ready_for_empirical_backtest": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def _fixed_policy() -> dict[str, Any]:
    # Check fixed constants before minting a new protocol, not just on reuse.
    if (WINDOWS != (("TWTR", "2022-10-01", "2022-11-30"),
                    ("FRC", "2023-04-01", "2023-06-30"))
            or REQUEST_IDS != ("index-TWTR", "text-TWTR", "index-FRC", "text-FRC")
            or type(MAXIMUM_REQUESTS) is not int or MAXIMUM_REQUESTS != 4
            or type(MAXIMUM_RESPONSE_BYTES) is not int
            or MAXIMUM_RESPONSE_BYTES != 4 * 1024 * 1024):
        raise _refuse("fixed_disclosure_policy_changed")
    return {"windows": [list(row) for row in WINDOWS], "maximum_requests": 4,
            "automatic_retries": 0, "maximum_pages_per_request": 1,
            "maximum_response_bytes": 4 * 1024 * 1024,
            "index_limit": 10000, "text_limit": 100,
            "forms": ["8-K", "8-K/A"], "sort": "filing_date.asc",
            "issuer_rule": "frozen_class_report_CIK_no_current_ticker_fallback",
            "duplicate_rule": "quarantine_all_identifiable_accession_peers_before_values",
            "text_rule": "core_Items_inventory_not_exhibits_or_payment_economics",
            "url_rule": "SEC_Archives_same_origin_no_query_userinfo_or_follow",
            "pagination_rule": "nonempty_next_url_incomplete_never_follow",
            "publication_scope": "private_only_source_evidence_inventory",
            "authority": _authority()}


def _cik(value: Any) -> str:
    if type(value) is not str or not _CIK.fullmatch(value) or int(value) == 0:
        raise _refuse("canonical_ten_digit_CIK_required")
    return value


def _sha(value: Any) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise _refuse("canonical_SHA256_required")
    return value


def _clock(value: Any):
    try:
        return parse_utc_timestamp(value, "capture_time")
    except (TypeError, ValueError):
        raise _refuse("canonical_UTC_capture_time_required") from None


def _descriptor(ciks: tuple[str, str], request_id: str) -> dict[str, Any]:
    if type(request_id) is not str or request_id not in REQUEST_IDS:
        raise _refuse("unknown_disclosure_request")
    kind, ticker = request_id.split("-", 1)
    index = 0 if ticker == "TWTR" else 1
    _, start, end = WINDOWS[index]
    path = "/stocks/filings/vX/index" if kind == "index" else "/stocks/filings/8-K/vX/text"
    return {"request_id": request_id, "method": "GET",
            "url": "https://api.massive.com" + path,
            "params": {"cik": ciks[index], "form_type.any_of": "8-K,8-K/A",
                       "filing_date.gte": start, "filing_date.lte": end,
                       "limit": "10000" if kind == "index" else "100",
                       "sort": "filing_date.asc"}}


@dataclasses.dataclass(frozen=True, slots=True)
class DisclosureProtocol:
    ciks: tuple[str, str] = dataclasses.field(repr=False)
    source_class_report_sha256: str
    _seal: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not DisclosureProtocol:
            raise _refuse("exact_disclosure_protocol_required")
        self._validate()
        object.__setattr__(self, "_seal", hash_payload(self._payload()))

    def _validate(self):
        _fixed_policy()
        if type(self.ciks) is not tuple or len(self.ciks) != 2:
            raise _refuse("two_frozen_issuer_CIKs_required")
        for value in self.ciks:
            _cik(value)
        if self.ciks[0] == self.ciks[1]:
            raise _refuse("distinct_issuer_CIKs_required")
        _sha(self.source_class_report_sha256)

    def _payload(self):
        return {"schema": "si-terminal-disclosure-protocol-v1", **_fixed_policy(),
                "source_class_report_sha256": self.source_class_report_sha256,
                "issuer_CIKs": list(self.ciks), "request_ids": list(REQUEST_IDS),
                "requests": [_descriptor(self.ciks, rid) for rid in REQUEST_IDS]}

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not DisclosureProtocol:
            raise _refuse("exact_disclosure_protocol_required")
        self._validate()
        payload = self._payload()
        if hash_payload(payload) != self._seal:
            raise _refuse("frozen_disclosure_protocol_changed")
        return {**payload, "protocol_sha256": self._seal}

    @property
    def sha256(self) -> str:
        return self.to_payload()["protocol_sha256"]

    def request(self, request_id: str) -> dict[str, Any]:
        self.to_payload()
        return _descriptor(self.ciks, request_id)

    def request_sha256(self, request_id: str) -> str:
        return hash_payload(self.request(request_id))


def freeze_disclosure_protocol(ciks: tuple[str, str], *, source_class_report_sha256: str) -> DisclosureProtocol:
    """Bind runtime-derived issuer assertions, not arbitrary source admission."""
    return DisclosureProtocol(ciks, source_class_report_sha256)


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedDisclosureResponse:
    request_id: str
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    received_at: str
    http_status: int = 200
    content_type: str = "application/json"

    def __post_init__(self):
        if type(self) is not CapturedDisclosureResponse:
            raise _refuse("exact_disclosure_capture_required")
        _fixed_policy()
        if type(self.request_id) is not str or self.request_id not in REQUEST_IDS:
            raise _refuse("unknown_disclosure_request")
        _sha(self.request_sha256)
        if type(self.raw) is not bytes or not self.raw or len(self.raw) > MAXIMUM_RESPONSE_BYTES:
            raise _refuse("immutable_bounded_disclosure_bytes_required")
        if type(self.http_status) is not int or self.http_status != 200:
            raise _refuse("disclosure_HTTP_200_required")
        if (type(self.content_type) is not str or len(self.content_type) > 256
                or any(ord(c) < 32 or ord(c) == 127 for c in self.content_type)
                or self.content_type.split(";", 1)[0].strip().lower() != "application/json"):
            raise _refuse("disclosure_JSON_media_required")
        _clock(self.received_at)

    @property
    def raw_sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.raw)


class _NumberToken(str):
    """Retain unknown finite decimal lexical tokens without float arithmetic."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise _refuse("duplicate_disclosure_JSON_key")
        result[key] = value
    return result


def _constant(_):
    raise _refuse("nonfinite_disclosure_JSON")


def _json(raw: bytes):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=_NumberToken, parse_constant=_constant)
        # Validate lone surrogates before storing a private canonical report.
        hash_payload(value)
        return value
    except TerminalDisclosureError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise _refuse("invalid_disclosure_UTF8_JSON") from None


def _text(value: Any, *, maximum=4096) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise _refuse("invalid_disclosure_metadata_text")
    return value


def _date(value):
    try:
        text = _text(value, maximum=10)
        parsed = date.fromisoformat(text)
        if parsed.isoformat() != text:
            raise ValueError
        return text
    except (TypeError, ValueError):
        raise _refuse("canonical_disclosure_date_required") from None


def _url(value):
    text = _text(value)
    match = _SEC_URL.fullmatch(text)
    if match is None or any(part in {".", "..", ""} for part in text.split("/Archives/", 1)[1].split("/")):
        raise _refuse("safe_SEC_Archives_origin_required")
    return text, match.group(1) == "https"


def _accession(row):
    if type(row) is dict and type(row.get("accession_number")) is str:
        value = row["accession_number"]
        if _ACCESSION.fullmatch(value):
            return value
    return None


def _metadata(row, *, cik, start, end):
    if type(row) is not dict:
        raise _refuse("disclosure_row_object_required")
    accession = _accession(row)
    if accession is None:
        raise _refuse("canonical_accession_required")
    if _cik(row.get("cik")) != cik:
        raise _refuse("disclosure_issuer_mismatch")
    at = _date(row.get("filing_date"))
    if not start <= at <= end:
        raise _refuse("disclosure_window_mismatch")
    if row.get("form_type") not in ("8-K", "8-K/A") or type(row.get("form_type")) is not str:
        raise _refuse("disclosure_form_mismatch")
    url, secure = _url(row.get("filing_url"))
    result = {"accession_number": accession, "cik": cik, "filing_date": at,
              "form_type": row["form_type"], "filing_url": url,
              "SEC_URL_is_HTTPS": secure, "source_document_independently_verified": False}
    for field in ("ticker", "issuer_name"):
        result[field] = None if row.get(field) is None else _text(row[field])
    return result


def validate_disclosure_response(protocol: DisclosureProtocol, capture: CapturedDisclosureResponse) -> dict[str, Any]:
    """Retain every row; a response page is never terminal-economic proof."""
    if type(protocol) is not DisclosureProtocol or type(capture) is not CapturedDisclosureResponse:
        raise _refuse("exact_protocol_and_capture_required")
    protocol.to_payload()
    capture.__post_init__()
    if capture.request_sha256 != protocol.request_sha256(capture.request_id):
        raise _refuse("disclosure_request_binding_mismatch")
    payload = _json(capture.raw)
    allowed = {"status", "results", "count", "request_id", "next_url"}
    if type(payload) is not dict or set(payload) - allowed or payload.get("status") != "OK":
        raise _refuse("invalid_disclosure_envelope")
    absent = "results" not in payload
    if absent and (type(payload.get("count")) is not int or payload["count"] != 0):
        raise _refuse("missing_disclosure_results_without_zero_count")
    rows = [] if absent else payload["results"]
    kind, ticker = capture.request_id.split("-", 1)
    maximum = 10000 if kind == "index" else 100
    if type(rows) is not list or len(rows) > maximum:
        raise _refuse("disclosure_results_limit_or_array")
    if "count" in payload and (type(payload["count"]) is not int or payload["count"] != len(rows)):
        raise _refuse("disclosure_count_mismatch")
    if "request_id" in payload and payload["request_id"] is not None:
        _text(payload["request_id"])
    next_url = payload.get("next_url")
    if next_url is not None and type(next_url) is not str:
        raise _refuse("invalid_disclosure_next_url")
    page_complete = not next_url
    position = 0 if ticker == "TWTR" else 1
    _, start, end = WINDOWS[position]
    keys = [_accession(row) for row in rows]
    counts = {}
    for key in keys:
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    source_sha256 = capture.raw_sha256
    records = []
    for number, row in enumerate(rows):
        origin = {"source_file_sha256": source_sha256, "row_index": number,
                  "parsed_record_sha256": hash_payload(row)}
        origin["row_binding_sha256"] = hash_payload(origin)
        result = {"origin": origin, "source_record": row, "metadata": None,
                  "items_text": None, "inventory_status": "refused", "reason": None,
                  "terminal_economics_admitted": False, "payment_date": None,
                  "per_share_consideration": None, "effective_cash_available_at": None}
        if keys[number] is not None and counts[keys[number]] > 1:
            result["reason"] = "duplicate_accession_quarantined"
        else:
            try:
                result["metadata"] = _metadata(row, cik=protocol.ciks[position], start=start, end=end)
            except TerminalDisclosureError as exc:
                result["reason"] = str(exc).removeprefix("REFUSED: ")
            else:
                if not result["metadata"]["SEC_URL_is_HTTPS"]:
                    result.update(inventory_status="source_verification_needed", reason="SEC_URL_HTTP_not_authenticated")
                elif kind == "index":
                    result.update(inventory_status="metadata_inventory", reason=None)
                else:
                    text = row.get("items_text")
                    if (type(text) is not str or not text.strip() or len(text.encode("utf-8")) > MAXIMUM_RESPONSE_BYTES
                            or any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in text)):
                        result.update(inventory_status="missing_or_unusable_text", reason="core_Items_text_unavailable")
                    else:
                        result.update(items_text=text, inventory_status="core_Items_inventory", reason=None)
        records.append(result)
    return {"request_id": capture.request_id, "request_sha256": capture.request_sha256,
            "source_file_sha256": source_sha256, "received_at": capture.received_at,
            "raw_row_count": len(rows), "raw_results_absent": absent,
            "page_complete": page_complete, "pagination_refusal": None if page_complete else "next_page_unconsumed",
            "records": records, "authority": _authority()}


def _build(protocol, captures, retrieved_at):
    if type(protocol) is not DisclosureProtocol or type(captures) is not tuple or len(captures) != MAXIMUM_REQUESTS:
        raise _refuse("exact_four_disclosure_captures_required")
    protocol.to_payload()
    if tuple(row.request_id for row in captures if type(row) is CapturedDisclosureResponse) != REQUEST_IDS:
        raise _refuse("disclosure_capture_type_or_order")
    clocks = [_clock(row.received_at) for row in captures]
    if clocks != sorted(clocks) or _clock(retrieved_at) < clocks[-1]:
        raise _refuse("disclosure_capture_chronology")
    tables = [validate_disclosure_response(protocol, row) for row in captures]
    # Cross-route metadata must agree, but index + text are expected replicas,
    # not duplicate filings. Distinct amendment accessions are never collapsed.
    groups = {}
    for table in tables:
        for row in table["records"]:
            accession = _accession(row["source_record"])
            if accession is not None:
                groups.setdefault(accession, []).append((table, row))
    links = []
    for accession, peers in sorted(groups.items()):
        valid = [row["metadata"] for _, row in peers if row["metadata"] is not None]
        agreement = (len(valid) == len(peers)
                     and len({(row["cik"], row["filing_date"], row["form_type"]) for row in valid}) == 1)
        kinds = [table["request_id"].split("-", 1)[0] for table, _ in peers]
        if not agreement or len(kinds) != len(set(kinds)):
            for _, row in peers:
                row.update(inventory_status="refused", reason="cross_filing_accession_conflict")
        links.append({"accession_number": accession,
                      "request_ids": [table["request_id"] for table, _ in peers],
                      "metadata_agreement": agreement,
                      "index_and_text_present": "index" in kinds and "text" in kinds,
                      "source_document_independently_verified": False,
                      "terminal_economics_admitted": False})
    capture_identity = hash_payload([{"request_id": row.request_id,
                                     "request_sha256": row.request_sha256,
                                     "raw_sha256": row.raw_sha256, "received_at": row.received_at,
                                     "http_status": row.http_status, "content_type": row.content_type}
                                    for row in captures])
    payload = {"schema": "si-terminal-disclosure-evidence-v1",
               "protocol_sha256": protocol.sha256,
               "source_class_report_sha256": protocol.source_class_report_sha256,
               "capture_identity_sha256": capture_identity, "retrieved_at": retrieved_at,
               "all_four_pages_complete": all(table["page_complete"] for table in tables),
               "tables": tables, "accession_inventory_links": links,
               "public_known_gaps": ["core_Items_text_not_exhibits_or_exhaustive_filing_record",
                                     "CIK_issuer_relation_not_share_class_consideration_authority",
                                     "payment_and_terminal_cash_facts_not_extracted_or_admitted",
                                     "prospective_look_and_exact_QC_representation_not_registered"],
               "authority": _authority()}
    payload["report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalDisclosureEvidence:
    protocol: DisclosureProtocol = dataclasses.field(repr=False)
    captures: tuple[CapturedDisclosureResponse, ...] = dataclasses.field(repr=False)
    retrieved_at: str
    _seal: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not TerminalDisclosureEvidence:
            raise _refuse("exact_disclosure_evidence_required")
        object.__setattr__(self, "_seal", _build(self.protocol, self.captures, self.retrieved_at)["report_sha256"])

    def to_payload(self):
        if type(self) is not TerminalDisclosureEvidence:
            raise _refuse("exact_disclosure_evidence_required")
        payload = _build(self.protocol, self.captures, self.retrieved_at)
        if payload["report_sha256"] != self._seal:
            raise _refuse("retained_disclosure_evidence_changed")
        return payload

    @property
    def sha256(self):
        return self.to_payload()["report_sha256"]


def qualify_terminal_disclosure(protocol: DisclosureProtocol,
                                captures: tuple[CapturedDisclosureResponse, ...], *,
                                retrieved_at: str) -> TerminalDisclosureEvidence:
    return TerminalDisclosureEvidence(protocol, captures, retrieved_at)
