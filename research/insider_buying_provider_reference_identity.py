"""Pure current-Sharadar metadata/SEC identity triage; never PIT promotion.

Direct public documentation: https://sharadar.com/docs/tickers,
https://sharadar.com/docs/auth and https://sharadar.com/llms.txt (2026-10-06).
The direct TICKERS bulk table is one active/delisted current snapshot, not a
series of historical vintages. Its permaticker is a provider share-class ID;
neither today's ticker nor firstpricedate/lastupdated supplies historical
validity, first listing, public knowledge, a QC SID or exact Form-4 title.

Only supplied CSV chunks and supplied SEC CIK/title evidence are consumed.
No transport, credential, artifact loader, outcome or authorization API exists.
All source rows are accounted for, including non-security and malformed rows.
An externally pinned hash proves byte consistency, not source authentication.
"""
from __future__ import annotations

import codecs
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Iterator
from urllib.parse import parse_qsl, urlsplit
import weakref

from data.hashing import canonical_json, hash_bytes, hash_payload


VERSION = "INSETF-SHARADAR-CURRENT-IDENTITY-ASSESSMENT-v1"
DIRECT_METADATA_ENDPOINT = "https://api.sharadar.com/v1.0/data/tickers"
DOCUMENTATION_URLS = ("https://sharadar.com/docs/tickers", "https://sharadar.com/docs/auth", "https://sharadar.com/llms.txt")
DOCUMENTED_COLUMNS = (
    "table", "permaticker", "ticker", "name", "exchange", "isdelisted", "category",
    "cusips", "siccode", "sicsector", "sicindustry", "figi", "famaindustry", "sector",
    "industry", "scalemarketcap", "scalerevenue", "relatedtickers", "currency", "location",
    "lastupdated", "firstadded", "firstpricedate", "lastpricedate", "firstquarter", "lastquarter",
    "secfilings", "companysite",
)
REQUIRED_COLUMNS = frozenset({"table", "permaticker", "ticker", "name", "exchange", "isdelisted", "category", "secfilings"})
MAX_METADATA_BYTES = 128 * 1024 * 1024
MAX_CHUNK_BYTES = 4 * 1024 * 1024
MAX_PHYSICAL_LINE_BYTES = 128 * 1024
MAX_RECORD_TEXT_BYTES = 128 * 1024
MAX_FIELD_TEXT_BYTES = 16 * 1024
MAX_METADATA_ROWS = 1_000_000
MAX_SEC_TITLE_ROWS = 1_000_000
MAX_REPORT_BYTES = 512 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{10}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TICKER = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-^/=]{0,63}\Z")
_SECURITY_TABLES = frozenset({"stocks", "fundamentals", "funds", "insiders", "SEP", "SF1", "SFP", "SF2"})
UNRESOLVED_GATES = (
    "historical_validity_intervals_not_established", "historical_knowledge_instants_not_established",
    "historical_closure_and_alias_lineage_not_established", "exact_sec_security_title_not_corroborated",
    "qc_symbol_id_not_bound", "first_listing_and_predecessor_history_not_established",
    "original_sec_parent_corroboration_not_performed", "ordinary_equity_eligibility_not_established",
)
_REGISTRY: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


class ProviderReferenceIdentityError(ValueError):
    """Supplied snapshot or inventory cannot be accounted for safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProviderReferenceIdentityError("REFUSED: " + message)


def _sha(value: object, label: str) -> None:
    _require(type(value) is str and _SHA.fullmatch(value) is not None, label + " digest is invalid")


def metadata_schema_sha256(columns: tuple[str, ...]) -> str:
    _require(type(columns) is tuple and all(type(column) is str for column in columns)
             and REQUIRED_COLUMNS <= set(columns)
             and len(columns) == len(set(columns)) and set(columns) <= set(DOCUMENTED_COLUMNS),
             "metadata schema is not a documented unique reference-only projection")
    return hash_payload({"provider": "direct-sharadar", "table": "tickers", "ordered_columns": list(columns)})


@dataclass(frozen=True, slots=True)
class SharadarCurrentMetadataSnapshot:
    metadata_sha256: str
    schema_sha256: str
    provider_vintage_id: str
    observed_at_utc: str
    columns: tuple[str, ...] = DOCUMENTED_COLUMNS

    def __post_init__(self) -> None:
        _sha(self.metadata_sha256, "metadata")
        _sha(self.schema_sha256, "schema")
        _require(self.schema_sha256 == metadata_schema_sha256(self.columns), "metadata schema anchor differs")
        _require(type(self.provider_vintage_id) is str and _ID.fullmatch(self.provider_vintage_id) is not None,
                 "snapshot vintage ID is invalid")
        _require(type(self.observed_at_utc) is str and self.observed_at_utc.endswith("Z"), "observation must be canonical UTC")
        try:
            instant = datetime.fromisoformat(self.observed_at_utc[:-1] + "+00:00")
        except ValueError:
            raise ProviderReferenceIdentityError("REFUSED: observation instant is invalid") from None
        _require(instant.tzinfo == timezone.utc and instant.isoformat().replace("+00:00", "Z") == self.observed_at_utc,
                 "observation instant is noncanonical")


@dataclass(frozen=True, slots=True)
class SecIssuerTitle:
    issuer_cik: str
    security_title_raw: str

    def __post_init__(self) -> None:
        _require(type(self.issuer_cik) is str and _CIK.fullmatch(self.issuer_cik) is not None
                 and int(self.issuer_cik) > 0, "SEC issuer CIK must be positive canonical ten digits")
        _require(type(self.security_title_raw) is str and self.security_title_raw
                 and len(self.security_title_raw.encode("utf-8")) <= 4096
                 and not any(ord(char) < 32 for char in self.security_title_raw), "SEC exact title is invalid")

    def to_payload(self) -> dict:
        return {"issuer_cik": self.issuer_cik, "security_title_raw": self.security_title_raw}


def sec_issuer_title_inventory_sha256(records: tuple[SecIssuerTitle, ...]) -> str:
    """Fixture/supplied-inventory helper; independent external anchoring remains required."""
    _require(type(records) is tuple and 0 < len(records) <= MAX_SEC_TITLE_ROWS, "SEC title inventory count differs")
    digest = hashlib.sha256()
    prior = None
    for item in records:
        _require(type(item) is SecIssuerTitle, "exact SEC title record required")
        item.__post_init__()
        key = (item.issuer_cik, item.security_title_raw.encode("utf-8"))
        _require(prior is None or prior < key, "SEC title inventory is duplicated or reordered")
        digest.update((canonical_json(item.to_payload()) + "\n").encode("utf-8"))
        prior = key
    return digest.hexdigest()


def _iterator(value: object, label: str) -> Iterator:
    try:
        iterator = iter(value)
    except TypeError:
        raise ProviderReferenceIdentityError("REFUSED: " + label + " must be an exact one-pass iterator") from None
    _require(iterator is value, label + " must be an exact one-pass iterator")
    return iterator


def _lines(chunks: Iterator[bytes], digest, accounting: dict) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending = ""
    for chunk in chunks:
        _require(type(chunk) is bytes and 0 < len(chunk) <= MAX_CHUNK_BYTES, "CSV chunk is empty, mutable or oversized")
        accounting["metadata_bytes"] += len(chunk)
        _require(accounting["metadata_bytes"] <= MAX_METADATA_BYTES, "CSV snapshot exceeds bounded byte profile")
        digest.update(chunk)
        try:
            pending += decoder.decode(chunk)
        except UnicodeError:
            raise ProviderReferenceIdentityError("REFUSED: CSV is not exact UTF-8") from None
        start = 0
        while (end := pending.find("\n", start)) != -1:
            line = pending[start:end]
            _require(len(line.encode("utf-8")) <= MAX_PHYSICAL_LINE_BYTES, "CSV physical line is oversized")
            yield line + "\n"
            start = end + 1
        pending = pending[start:]
        _require(len(pending.encode("utf-8")) <= MAX_PHYSICAL_LINE_BYTES, "CSV unterminated physical line is oversized")
    try:
        pending += decoder.decode(b"", final=True)
    except UnicodeError:
        raise ProviderReferenceIdentityError("REFUSED: CSV has incomplete UTF-8") from None
    if pending:
        _require(len(pending.encode("utf-8")) <= MAX_PHYSICAL_LINE_BYTES, "CSV terminal line is oversized")
        yield pending


def _sec_cik_url(raw: str) -> tuple[str | None, str]:
    if not raw:
        return None, "sec_filings_url_missing"
    if any(char.isspace() for char in raw) or any(char in raw for char in "\\%"):
        return None, "sec_filings_url_not_canonical"
    try:
        url = urlsplit(raw)
        if (url.scheme != "https" or url.netloc != "www.sec.gov" or url.fragment
                or url.path not in {"/cgi-bin/browse-edgar", "/edgar/browse/"}):
            return None, "sec_filings_url_not_canonical"
        query = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None, "sec_filings_url_not_canonical"
    keys = [key for key, _ in query]
    allowed = {"CIK", "action", "type", "dateb", "owner", "count"} if url.path == "/cgi-bin/browse-edgar" else {"CIK", "owner"}
    if len(keys) != len(set(keys)) or not set(keys) <= allowed:
        return None, "sec_filings_url_not_canonical"
    values = dict(query)
    if url.path == "/cgi-bin/browse-edgar" and values.get("action") != "getcompany":
        return None, "sec_filings_url_not_canonical"
    cik = values.get("CIK")
    if cik is None or re.fullmatch(r"[0-9]{1,10}", cik) is None or int(cik) == 0:
        return None, "sec_filings_url_cik_missing_or_invalid"
    return cik.zfill(10), "current_provider_sec_url_cik_candidate"


@dataclass(frozen=True, slots=True, weakref_slot=True)
class SharadarCurrentIdentityAssessment:
    _bytes: bytes

    def _validate(self) -> bytes:
        registered = _REGISTRY.get(id(self))
        _require(type(self) is SharadarCurrentIdentityAssessment and type(self._bytes) is bytes
                 and registered is not None and registered[0]() is self and registered[1] == self._bytes,
                 "assessment is not an unchanged genuine factory result")
        return self._bytes

    def to_payload(self) -> dict:
        return json.loads(self._validate())

    @property
    def sha256(self) -> str:
        return hash_bytes(self._validate())


def assess_sharadar_current_identity(*, metadata_chunks: Iterator[bytes], snapshot: SharadarCurrentMetadataSnapshot,
                                    sec_issuer_titles: Iterator[SecIssuerTitle], expected_sec_inventory_sha256: str) -> SharadarCurrentIdentityAssessment:
    """Account for a supplied complete current snapshot without releasing eligibility.

    No completeness claim is inferred from provider documentation or row count.
    The supplied exact byte/schema hashes and separately supplied SEC inventory
    are checked in full. SEC titles are retained verbatim, never matched by name,
    generic category, relatedtickers, CUSIP or FIGI.
    """
    _require(type(snapshot) is SharadarCurrentMetadataSnapshot, "exact snapshot descriptor required")
    snapshot.__post_init__()
    _sha(expected_sec_inventory_sha256, "SEC inventory")
    chunks = _iterator(metadata_chunks, "metadata chunks")
    sec_records = _iterator(sec_issuer_titles, "SEC title records")
    sec_digest, sec_rows, prior = hashlib.sha256(), [], None
    report_budget = 0
    for item in sec_records:
        _require(type(item) is SecIssuerTitle, "exact SEC title record required")
        item.__post_init__()
        key = (item.issuer_cik, item.security_title_raw.encode("utf-8"))
        _require(prior is None or prior < key, "SEC title inventory is duplicated or reordered")
        _require(len(sec_rows) < MAX_SEC_TITLE_ROWS, "SEC title inventory exceeds bound")
        payload = item.to_payload()
        # Reserve each compact SEC disposition before retaining its input.
        report_budget += len(canonical_json(payload).encode("utf-8")) + 1024
        _require(report_budget <= MAX_REPORT_BYTES, "SEC identity report exceeds bounded output profile")
        sec_digest.update((canonical_json(payload) + "\n").encode("utf-8"))
        sec_rows.append(payload)
        prior = key
        del item
    _require(sec_rows and sec_digest.hexdigest() == expected_sec_inventory_sha256, "SEC title inventory anchor differs or empty")
    accounting = {"metadata_bytes": 0, "metadata_rows": 0, "active_rows": 0, "delisted_rows": 0,
                  "unknown_delisting_rows": 0, "nonsecurity_rows": 0, "cik_candidate_rows": 0,
                  "no_cik_rows": 0, "duplicate_primary_key_rows": 0, "conflicting_primary_key_rows": 0}
    digest = hashlib.sha256()
    reader = csv.reader(_lines(chunks, digest, accounting), strict=True)
    rows, groups, primary_keys = [], {}, {}
    try:
        header = next(reader)
        _require(tuple(header) == snapshot.columns, "captured CSV header differs from exact schema anchor")
        for ordinal, values in enumerate(reader):
            _require(ordinal < MAX_METADATA_ROWS, "CSV metadata row count exceeds bounded profile")
            _require(len(values) == len(header), "CSV row width differs from header")
            _require(sum(len(value.encode("utf-8")) for value in values) <= MAX_RECORD_TEXT_BYTES
                     and all(len(value.encode("utf-8")) <= MAX_FIELD_TEXT_BYTES for value in values), "CSV record/field exceeds bound")
            _require(all("\x00" not in value for value in values), "CSV contains NUL metadata")
            record = dict(zip(header, values, strict=True))
            record_sha = hash_payload(record)
            reasons = []
            table, permanent, ticker = record["table"], record["permaticker"], record["ticker"]
            security_table = table in _SECURITY_TABLES
            if not security_table:
                accounting["nonsecurity_rows"] += 1
                reasons.append("not_a_documented_security_table_row")
            if not _ID.fullmatch(permanent):
                reasons.append("provider_permanent_share_class_id_missing_or_invalid")
            if not _TICKER.fullmatch(ticker):
                reasons.append("current_ticker_missing_or_invalid")
            flag = record["isdelisted"]
            accounting["active_rows" if flag == "N" else "delisted_rows" if flag == "Y" else "unknown_delisting_rows"] += 1
            if flag not in {"Y", "N"}:
                reasons.append("current_delisting_flag_unknown")
            cik, url_disposition = _sec_cik_url(record["secfilings"])
            accounting["cik_candidate_rows" if cik else "no_cik_rows"] += 1
            if cik is None:
                reasons.append(url_disposition)
            primary_key = (table, permanent, ticker)
            old = primary_keys.get(primary_key)
            if old is not None:
                duplicate = old == record_sha
                accounting["duplicate_primary_key_rows" if duplicate else "conflicting_primary_key_rows"] += 1
                reasons.append("duplicate_exact_primary_key_row" if duplicate else "conflicting_current_primary_key_row")
            else:
                primary_keys[primary_key] = record_sha
            row = {"ordinal": ordinal, "source_row_sha256": record_sha, "table": table,
                   "provider_permaticker": permanent, "current_ticker": ticker, "current_name": record["name"],
                   "current_exchange": record["exchange"], "current_category": record["category"],
                   "current_isdelisted": flag, "issuer_cik_candidate": cik, "sec_url_disposition": url_disposition,
                   "sec_filings_url_sha256": hash_bytes(record["secfilings"].encode("utf-8")),
                   "observed_dates": {key: record.get(key) for key in ("lastupdated", "firstadded", "firstpricedate", "lastpricedate")},
                   "untrusted_identifier_fields": {key: {"present": bool(record.get(key)),
                        "sha256": hash_bytes(record.get(key, "").encode("utf-8"))} for key in ("cusips", "figi", "relatedtickers")},
                   "diagnostic_reasons": reasons, "canonical_eligibility_released": False}
            report_budget += len(canonical_json(row).encode("utf-8")) + 1024
            _require(report_budget <= MAX_REPORT_BYTES, "metadata identity report exceeds bounded output profile")
            rows.append(row)
            if security_table and _ID.fullmatch(permanent):
                group = groups.setdefault(permanent, {"row_ordinals": [], "ciks": set(), "tickers": set(),
                                                       "tables": set(), "conflicted": False})
                group["row_ordinals"].append(ordinal)
                if cik:
                    group["ciks"].add(cik)
                if ticker:
                    group["tickers"].add(ticker)
                group["tables"].add(table)
                group["conflicted"] |= old is not None and old != record_sha
            accounting["metadata_rows"] += 1
            del values, record, row
    except (csv.Error, StopIteration):
        raise ProviderReferenceIdentityError("REFUSED: CSV is empty, malformed or exceeds parser field bounds") from None
    _require(accounting["metadata_rows"] > 0 and digest.hexdigest() == snapshot.metadata_sha256,
             "metadata byte anchor differs or snapshot has no rows")
    candidates, by_cik = [], {}
    for permanent, group in sorted(groups.items()):
        ciks = sorted(group["ciks"])
        conflict = group["conflicted"] or len(ciks) > 1
        candidate = {"provider_permaticker": permanent, "source_row_ordinals": group["row_ordinals"],
                     "issuer_cik_candidates": ciks, "current_ticker_alias_observations": sorted(group["tickers"]),
                     "observed_tables": sorted(group["tables"]), "current_provider_identity_conflicted": conflict,
                     "candidate_scope": "current-provider-share-class-only-not-pit", "unresolved_gates": list(UNRESOLVED_GATES)}
        candidates.append(candidate)
        if not conflict and len(ciks) == 1:
            by_cik.setdefault(ciks[0], []).append(permanent)
    for item in sec_rows:
        permanent_ids = sorted(by_cik.get(item["issuer_cik"], []))
        # Many classes/titles must not create an unbounded Cartesian payload.
        report_budget += sum(len(permanent.encode("utf-8")) + 3 for permanent in permanent_ids)
        _require(report_budget <= MAX_REPORT_BYTES, "SEC candidate expansion exceeds bounded output profile")
        item["provider_permaticker_candidates"] = permanent_ids
        item["identity_coverage_disposition"] = ("no_current_cik_candidate" if not permanent_ids else
            "multiple_current_share_class_candidates" if len(permanent_ids) > 1 else "one_current_share_class_candidate_not_corroborated")
        item["exact_title_matching_performed"] = False
        item["unresolved_gates"] = list(UNRESOLVED_GATES)
    body = {"kind": VERSION, "provider": "direct-sharadar", "table": "tickers", "endpoint_identity": DIRECT_METADATA_ENDPOINT,
            "snapshot": {"metadata_sha256": snapshot.metadata_sha256, "schema_sha256": snapshot.schema_sha256,
                "provider_vintage_id": snapshot.provider_vintage_id, "observed_at_utc": snapshot.observed_at_utc,
                "ordered_columns": list(snapshot.columns), "profile": "current-supplied-snapshot-not-historical-vintage"},
            "sec_issuer_title_inventory_sha256": expected_sec_inventory_sha256, "accounting": accounting,
            "metadata_rows": rows, "current_share_class_candidates": candidates, "sec_identity_coverage": sec_rows,
            "source_authenticated_here": False, "rights_authenticated_here": False, "point_in_time_verified": False,
            "first_listing_verified": False, "canonical_eligibility_released": False, "qc_authorized": False,
            "authorized_outcome_looks": 0, "consumed_outcome_looks": 0, "qc_jobs": 0,
            "unresolved_gates": list(UNRESOLVED_GATES)}
    raw = canonical_json(body).encode("utf-8")
    _require(len(raw) <= MAX_REPORT_BYTES, "identity report exceeds bounded output profile")
    result = SharadarCurrentIdentityAssessment(raw)
    identity = id(result)
    _REGISTRY[identity] = (weakref.ref(result, lambda _: _REGISTRY.pop(identity, None)), raw)
    return result


__all__ = ["VERSION", "DOCUMENTED_COLUMNS", "SharadarCurrentMetadataSnapshot", "SecIssuerTitle",
           "SharadarCurrentIdentityAssessment", "ProviderReferenceIdentityError", "metadata_schema_sha256",
           "sec_issuer_title_inventory_sha256", "assess_sharadar_current_identity"]
