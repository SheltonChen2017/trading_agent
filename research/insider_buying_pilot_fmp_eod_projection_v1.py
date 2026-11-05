"""Pure bounded provider metadata comparisons against retained SEC controls.

No transport, file access, row storage or financial evaluation occurs here.
Callers screen credentials and transport status before supplying response bytes.
All outputs remain diagnostic metadata with every readiness authority false.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import re
from urllib.parse import urlsplit
import weakref

SCHEMA = "insider-pilot-fmp-eod-metadata-projection-v1"
MAX_BODY = 4 * 1024 * 1024
MAX_ROWS = 1000
MAX_CASES = 32
FIRST_DAY, LAST_DAY = "2020-10-01", "2025-12-31"
_CASE_KEYS = frozenset({"case_id", "cik", "accession", "form_type", "filing_date",
    "acceptance_digits", "source_symbol", "body_sha256"})
_SEC_FIELDS = ("symbol", "cik", "filingDate", "acceptedDate", "formType", "link", "finalLink")
_INSIDER_FIELDS = ("symbol", "filingDate", "transactionDate", "reportingCik", "companyCik",
    "transactionType", "securitiesOwned", "reportingName", "typeOfOwner", "acquisitionOrDisposition",
    "directOrIndirect", "formType", "securitiesTransacted", "price", "securityName", "url")
_EOD_FIELDS = ("symbol", "cik", "isin", "cusip", "figi", "lei")
_FORMS = frozenset({"3", "3/A", "4", "4/A", "5", "5/A"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_CODES = frozenset({"response_bytes_refused", "response_status_refused", "response_json_refused",
    "response_shape_refused", "response_resource_refused", "provider_error_response",
    "control_cases_refused", "request_scope_refused", "genuine_projection_required"})


class ProjectionError(ValueError):
    """Finite own codes; upstream text and values are never error messages."""


class _Integer(str):
    """JSON integer lexeme, interpreted only for identity/pagination metadata."""


class _Float(str):
    """Opaque JSON numeric lexeme; never interpreted as a financial value."""


def _need(condition, code):
    if not condition:
        raise ProjectionError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def safe_failure(error):
    return str(error) if type(error) is ProjectionError and str(error) in _CODES else "response_json_refused"


def _authority():
    return {"source_authenticated": False, "historical_identity_verified": False,
        "historical_public_known_by_verified": False, "point_in_time_data": False,
        "rights_verified": False, "canonical_admitted": False, "full_population_complete": False,
        "backtesting_ready": False, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def _json(raw, status):
    _need(type(status) is int and status == 200, "response_status_refused")
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "response_bytes_refused")
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "response_json_refused")
            value[key] = child
        return value
    def number(value, kind):
        _need(len(value) <= 128, "response_resource_refused")
        return kind(value)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_int=lambda s: number(s, _Integer), parse_float=lambda s: number(s, _Float),
            parse_constant=lambda _: _need(False, "response_json_refused"))
        count = 0
        stack = [(value, 0)]
        while stack:
            child, depth = stack.pop(); count += 1
            _need(depth <= 12 and count <= 100000, "response_resource_refused")
            if type(child) is dict:
                _need(len(child) <= 128 and all(type(k) is str and len(k) <= 128 for k in child),
                    "response_resource_refused")
                stack.extend((v, depth + 1) for v in child.values())
            elif type(child) is list:
                _need(len(child) <= MAX_ROWS, "response_resource_refused")
                stack.extend((v, depth + 1) for v in child)
            elif isinstance(child, str):
                _need(len(child) <= 16384, "response_resource_refused")
            else:
                _need(child is None or type(child) is bool, "response_json_refused")
        return value
    except ProjectionError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ProjectionError("response_json_refused") from None


def _day(value):
    if type(value) is not str or len(value) != 10:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _sec_filing_day(value):
    """FMP's exact midnight representation is a civil date, never a zone."""
    if type(value) is str and len(value) == 19 and value[10:] == " 00:00:00":
        day = _day(value[:10])
        return day, day is not None
    return _day(value), False


def _acceptance(value):
    """Lexical naive wall-clock equality; no timezone/publication inference."""
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d%H%M%S")
    except ValueError:
        return None


def _cik(value):
    if type(value) not in {str, _Integer} or not re.fullmatch(r"[0-9]{1,10}", value) or not value.strip("0"):
        return None
    return value.zfill(10)


def _missing(value):
    return value is None or type(value) is str and value == ""


def _provider_error(value):
    return type(value) is dict and (any(value.get(k) for k in ("error", "Error Message", "error_message", "errors"))
        or value.get("success") is False
        or type(value.get("status")) is str and value["status"].lower() in {"error", "failed", "failure"})


def _cases(cases):
    _need(type(cases) in {list, tuple} and 0 < len(cases) <= MAX_CASES, "control_cases_refused")
    result, ids, sources = [], set(), set()
    for case in cases:
        _need(type(case) is dict and frozenset(case) in {_CASE_KEYS, _CASE_KEYS - {"source_symbol"}}, "control_cases_refused")
        _need(type(case["case_id"]) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", case["case_id"])
            and case["case_id"] not in ids, "control_cases_refused")
        _need(type(case["cik"]) is str and len(case["cik"]) == 10 and _cik(case["cik"]) == case["cik"]
            and type(case["accession"]) is str and re.fullmatch(r"[0-9]{18}", case["accession"])
            and type(case["form_type"]) is str and case["form_type"] in _FORMS and _day(case["filing_date"]) is not None
            and FIRST_DAY <= case["filing_date"] <= LAST_DAY and type(case["acceptance_digits"]) is str
            and re.fullmatch(r"[0-9]{14}", case["acceptance_digits"])
            and type(case["body_sha256"]) is str and _SHA.fullmatch(case["body_sha256"]), "control_cases_refused")
        try:
            datetime.strptime(case["acceptance_digits"], "%Y%m%d%H%M%S")
        except ValueError:
            raise ProjectionError("control_cases_refused") from None
        symbol = case.get("source_symbol")
        _need(symbol is None or type(symbol) is str and 0 < len(symbol) <= 64 and symbol.isascii(), "control_cases_refused")
        source = (case["cik"], case["accession"])
        _need(source not in sources, "control_cases_refused")
        ids.add(case["case_id"]); sources.add(source); result.append(dict(case))
    return result


def _paging(page, limit):
    _need(type(page) is int and 0 <= page <= 1000 and type(limit) is int and 1 <= limit <= MAX_ROWS,
        "request_scope_refused")


def _accessions(value):
    if value is None or value == "":
        return set(), "absent"
    if type(value) is not str or len(value) > 4096:
        return set(), "invalid"
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.netloc.lower() not in {"sec.gov", "www.sec.gov"}:
            return set(), "foreign_or_unusable"
        path = url.path
        if url.query or url.fragment or not path.startswith("/Archives/edgar/data/") or not path.isascii() \
                or "\\" in path or "%" in path or "//" in path or any(p in {".", ".."} for p in path.split("/")):
            return set(), "foreign_or_unusable"
        parts = path[len("/Archives/edgar/data/"):].split("/")
        direct_submission = len(parts) == 2 and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\.txt", parts[1])
        if (len(parts) < 3 and not direct_submission) or _cik(parts[0]) is None:
            return set(), "foreign_or_unusable"
        found = {p for p in parts[1:] if re.fullmatch(r"[0-9]{18}", p)}
        found.update(m.replace("-", "") for m in re.findall(r"(?<![0-9])[0-9]{10}-[0-9]{2}-[0-9]{6}(?![0-9])", "/".join(parts[1:])))
        return found, "accession_present" if found else "accession_absent"
    except ValueError:
        return set(), "foreign_or_unusable"


def _checks(cases):
    return {c["case_id"]: {**{k: 0 for k in ("candidate_rows", "exact_accession_rows", "cik_equal_rows",
        "joint_cik_accession_rows", "filing_date_equal_rows", "form_type_equal_rows", "source_symbol_present_rows",
        "source_symbol_equal_rows", "naive_acceptance_comparable_rows", "naive_acceptance_lexical_equal_rows",
        "filing_filter_equal_rows", "transaction_filter_equal_rows")}, "acceptance_timezone_verified": False,
        "public_known_by_verified": False, "source_body_equivalence_verified": False} for c in cases}


def _finish(raw, family, stats, checks, *, scoped, clean, dates, pagination):
    payload = {"schema": SCHEMA, "family": family, "scoped": scoped, "metadata_clean": clean,
        "response_rows_retained": False, "response_body_retained": False,
        "metadata_evidence_can_independently_reparse_response": False,
        "credential_screening_is_external_required_control": True,
        "body_pin": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} if scoped and clean else None,
        "counts": dict(stats), "case_checks": checks if scoped else {},
        "filing_date_bounds": [min(dates), max(dates)] if scoped and dates else None,
        "pagination": pagination, "all_six_form_coverage_verified": False,
        "current_label_agreement_is_historical_identity": False,
        "naive_acceptance_is_publication_or_timezone_evidence": False,
        "latest_date_filter_semantics_verified": False,
        "financial_values_interpreted": False, "authority": _authority()}
    result = ProjectionResult(_raw(payload), _TOKEN)
    _SEALS[result] = result._bytes
    return result


def _fmp(raw, cases, *, family, cik=None, from_date=None, to_date=None, requested_date=None, page, limit, status):
    controls = _cases(cases); _paging(page, limit)
    if family == "fmp_sec_search":
        _need(type(cik) is str and len(cik) == 10 and _cik(cik) == cik and cik in {c["cik"] for c in controls}
            and _day(from_date) is not None and _day(to_date) is not None
            and FIRST_DAY <= from_date <= to_date <= LAST_DAY, "request_scope_refused")
    else:
        _need(_day(requested_date) is not None and FIRST_DAY <= requested_date <= LAST_DAY, "request_scope_refused")
    rows = _json(raw, status)
    if type(rows) is dict:
        raise ProjectionError("provider_error_response")
    _need(type(rows) is list and len(rows) <= limit and all(type(r) is dict for r in rows), "response_shape_refused")
    _need(not any(_provider_error(row) for row in rows), "provider_error_response")
    fields = _SEC_FIELDS if family == "fmp_sec_search" else _INSIDER_FIELDS
    stats = Counter(response_rows=len(rows), metadata_valid_rows=0, metadata_quarantined_rows=0,
        filing_date_missing_rows=0, filing_date_invalid_rows=0, filing_date_outside_window_rows=0,
        filing_midnight_normalized_rows=0, requested_date_disagreement_rows=0,
        requested_interval_outside_rows=0, cik_missing_rows=0, cik_invalid_rows=0,
        queried_cik_disagreement_rows=0, transaction_date_missing_rows=0, transaction_date_invalid_rows=0,
        transaction_date_outside_window_rows=0, requested_date_filing_matches=0, requested_date_transaction_matches=0,
        accession_absent_rows=0, accession_conflict_rows=0, ambiguous_control_candidate_rows=0,
        matched_control_rows=0, unmatched_control_rows=0)
    presence, urls, dates, checks = Counter(), Counter(), [], _checks(controls)
    scoped, clean = True, True
    for row in rows:
        presence.update(k for k in fields if row.get(k) is not None)
        # Financial/name fields are opaque and never copied into output.
        metadata = ("symbol", "filingDate", "acceptedDate", "formType", "link", "finalLink") if family == "fmp_sec_search" else ("symbol", "filingDate", "transactionDate", "formType", "url")
        invalid = any(row.get(k) is not None and (type(row[k]) is not str or len(row[k]) > (4096 if k in {"link", "finalLink", "url"} else 128)) for k in metadata)
        company = _cik(row.get("cik" if family == "fmp_sec_search" else "companyCik"))
        if company is None:
            stats["cik_missing_rows" if _missing(row.get("cik" if family == "fmp_sec_search" else "companyCik")) else "cik_invalid_rows"] += 1
            invalid = True; scoped = False
        if cik is not None and company is not None and company != cik:
            stats["queried_cik_disagreement_rows"] += 1; scoped = False
        if family == "fmp_sec_search":
            filing, midnight_normalized = _sec_filing_day(row.get("filingDate"))
            stats["filing_midnight_normalized_rows"] += int(midnight_normalized)
        else:
            filing = _day(row.get("filingDate"))
        if filing is None:
            stats["filing_date_missing_rows" if _missing(row.get("filingDate")) else "filing_date_invalid_rows"] += 1
            scoped = False
        elif not FIRST_DAY <= filing <= LAST_DAY:
            stats["filing_date_outside_window_rows"] += 1; scoped = False
        else:
            dates.append(filing)
            if from_date is not None and not from_date <= filing <= to_date:
                stats["requested_interval_outside_rows"] += 1; scoped = False
        transaction = _day(row.get("transactionDate")) if family == "fmp_insider_latest" else None
        if family == "fmp_insider_latest":
            if transaction is None:
                stats["transaction_date_missing_rows" if _missing(row.get("transactionDate")) else "transaction_date_invalid_rows"] += 1
            elif not FIRST_DAY <= transaction <= LAST_DAY:
                stats["transaction_date_outside_window_rows"] += 1  # Legitimate older trade on an in-scope filing.
            stats["requested_date_filing_matches"] += int(filing == requested_date)
            stats["requested_date_transaction_matches"] += int(transaction == requested_date)
            # The documented date parameter's field meaning is unknown. A
            # row matching neither possible field cannot satisfy this query.
            if filing != requested_date and transaction != requested_date:
                stats["requested_date_disagreement_rows"] += 1; scoped = False
        accessions = set()
        for key in (("link", "finalLink") if family == "fmp_sec_search" else ("url",)):
            found, code = _accessions(row.get(key)); accessions.update(found); urls[code] += 1
        if len(accessions) > 1:
            stats["accession_conflict_rows"] += 1; invalid = True
        if not accessions:
            stats["accession_absent_rows"] += 1
        if invalid:
            stats["metadata_quarantined_rows"] += 1; clean = False; continue
        stats["metadata_valid_rows"] += 1
        candidates = [c for c in controls if c["accession"] in accessions or c["cik"] == company and c["filing_date"] == filing]
        exact = [c for c in candidates if c["accession"] in accessions and c["cik"] == company]
        stats["ambiguous_control_candidate_rows"] += int(len(candidates) > 1 and len(exact) != 1)
        stats["matched_control_rows" if len(exact) == 1 else "unmatched_control_rows"] += 1
        accepted = _acceptance(row.get("acceptedDate"))
        for case in candidates:
            item = checks[case["case_id"]]
            values = {"candidate_rows": True, "exact_accession_rows": case["accession"] in accessions,
                "cik_equal_rows": case["cik"] == company,
                "joint_cik_accession_rows": case["accession"] in accessions and case["cik"] == company,
                "filing_date_equal_rows": filing == case["filing_date"], "form_type_equal_rows": row.get("formType") == case["form_type"],
                "source_symbol_present_rows": bool(row.get("symbol")),
                "source_symbol_equal_rows": case.get("source_symbol") is not None and row.get("symbol") == case.get("source_symbol"),
                "naive_acceptance_comparable_rows": accepted is not None,
                "naive_acceptance_lexical_equal_rows": accepted is not None and accepted == case["acceptance_digits"],
                "filing_filter_equal_rows": requested_date is not None and filing == requested_date,
                "transaction_filter_equal_rows": requested_date is not None and transaction == requested_date}
            for key, value in values.items(): item[key] += int(value)
    stats["metadata_field_presence"] = dict(presence); stats["url_presence_codes"] = dict(urls)
    return _finish(raw, family, stats, checks, scoped=scoped, clean=clean, dates=dates,
        pagination={"requested_page": page, "requested_limit": limit, "limit_reached": len(rows) == limit,
            "additional_pages_unknown": True, "all_pages_read": False})


def project_sec_search(raw, cases, *, queried_cik, from_date, to_date, page=0, limit=1000, status=200):
    return _fmp(raw, cases, family="fmp_sec_search", cik=queried_cik, from_date=from_date,
        to_date=to_date, page=page, limit=limit, status=status)


def project_insider_latest(raw, cases, *, requested_date, page=0, limit=1000, status=200):
    return _fmp(raw, cases, family="fmp_insider_latest", requested_date=requested_date, page=page, limit=limit, status=status)


def _uint(value):
    return int(value) if type(value) is _Integer and re.fullmatch(r"[0-9]{1,10}", value) else None


def project_eod_mapping(raw, cases, *, requested_ciks, offset=0, limit=1000, status=200):
    controls = _cases(cases); _paging(offset, limit)
    _need(type(requested_ciks) in {list, tuple} and 0 < len(requested_ciks) <= MAX_CASES
        and all(type(c) is str and len(c) == 10 and _cik(c) == c and c in {x["cik"] for x in controls} for c in requested_ciks)
        and len(set(requested_ciks)) == len(requested_ciks), "request_scope_refused")
    response = _json(raw, status)
    _need(type(response) is dict, "response_shape_refused")
    if "data" not in response or _provider_error(response):
        raise ProjectionError("provider_error_response")
    rows, meta, links = response["data"], response.get("meta"), response.get("links")
    _need(type(rows) is list and len(rows) <= limit and all(type(r) is dict for r in rows)
        and type(meta) is dict and type(links) is dict, "response_shape_refused")
    _need(not any(_provider_error(row) for row in rows), "provider_error_response")
    total, actual_limit, actual_offset = (_uint(meta.get(k)) for k in ("total", "limit", "offset"))
    _need(total is not None and total >= len(rows) and actual_limit is not None and 1 <= actual_limit <= MAX_ROWS
        and actual_offset is not None and (links.get("next") is None or type(links["next"]) is str and len(links["next"]) <= 4096), "response_shape_refused")
    scoped, clean = actual_offset == offset and actual_limit == limit, True
    stats = Counter(response_rows=len(rows), metadata_valid_rows=0, metadata_quarantined_rows=0,
        cik_missing_rows=0, cik_invalid_rows=0, requested_cik_disagreement_rows=0,
        matched_control_rows=0, unmatched_control_rows=0, current_symbol_conflicting_ciks=0,
        issuer_ciks_with_multiple_symbols=0)
    presence, checks, seen, symbol_ciks = Counter(), {}, {}, {}
    for c in controls:
        checks[c["case_id"]] = {"cik_rows": 0, "current_symbol_present_rows": 0, "current_symbol_equal_rows": 0,
            "current_symbol_us_namespace_equal_rows": 0,
            "identifier_presence_counts": {k: 0 for k in _EOD_FIELDS[2:]}, "historical_identity_verified": False}
    for row in rows:
        presence.update(k for k in _EOD_FIELDS if row.get(k) is not None)
        company = _cik(row.get("cik"))
        invalid = any(row.get(k) is not None and (type(row[k]) is not str or len(row[k]) > 128) for k in _EOD_FIELDS if k != "cik")
        if company is None:
            stats["cik_missing_rows" if _missing(row.get("cik")) else "cik_invalid_rows"] += 1
            scoped = False; invalid = True
        elif company not in requested_ciks:
            stats["requested_cik_disagreement_rows"] += 1; scoped = False
        if invalid:
            stats["metadata_quarantined_rows"] += 1; clean = False; continue
        stats["metadata_valid_rows"] += 1
        symbol = row.get("symbol")
        if symbol:
            seen.setdefault(company, set()).add(symbol)
            symbol_ciks.setdefault(symbol, set()).add(company)
        matched = [c for c in controls if c["cik"] == company]
        stats["matched_control_rows" if matched else "unmatched_control_rows"] += 1
        for case in matched:
            item = checks[case["case_id"]]; item["cik_rows"] += 1
            item["current_symbol_present_rows"] += int(bool(symbol))
            item["current_symbol_equal_rows"] += int(case.get("source_symbol") is not None and symbol == case.get("source_symbol"))
            source_symbol = case.get("source_symbol")
            item["current_symbol_us_namespace_equal_rows"] += int(source_symbol is not None
                and not source_symbol.endswith(".US") and symbol == source_symbol + ".US")
            for key in _EOD_FIELDS[2:]: item["identifier_presence_counts"][key] += int(bool(row.get(key)))
    stats["current_symbol_conflicting_ciks"] = sum(len(v) > 1 for v in symbol_ciks.values())
    stats["issuer_ciks_with_multiple_symbols"] = sum(len(v) > 1 for v in seen.values())
    stats["metadata_field_presence"] = dict(presence)
    return _finish(raw, "eod_current_mapping", stats, checks, scoped=scoped, clean=clean, dates=[],
        pagination={"requested_offset": offset, "requested_limit": limit, "response_total": total,
            "response_limit": actual_limit, "response_offset": actual_offset, "limit_reached": len(rows) == limit,
            "next_present": bool(links.get("next")), "more_rows_indicated": bool(links.get("next")) or offset + len(rows) < total,
            "all_pages_read": False})


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ProjectionResult:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is ProjectionResult and self._token is _TOKEN and _SEALS.get(self) == self._bytes,
            "genuine_projection_required")
        return self._bytes

    @property
    def sha256(self):
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def public_payload(result):
    _need(type(result) is ProjectionResult, "genuine_projection_required")
    return json.loads(result.canonical_bytes())
