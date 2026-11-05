"""Ignored source-only FMP company context; never historical class admission.

The safe CIK lookup authenticates the present request-target company, not a
historical class, sector, denomination or availability clock. Historical cap
is a company-size series, never a share-class count. Its dated issuer and USD
bindings must be independently verified from a same-date source report.
"""
from __future__ import annotations

import dataclasses
import json
import re
from urllib.parse import urlencode

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.native_dated_identity as daily
import research.short_interest_etf.fmp_cap_source as cap

ENDPOINT = "https://financialmodelingprep.com/stable/search-cik"
MAXIMUM_LOOKUP_BYTES = 1024 * 1024
MAXIMUM_LOOKUP_ROWS = 50
SCHEMA = "si-fmp-company-context-draft-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"symbol", "companyName", "cik", "exchangeFullName", "exchange", "currency"}


class FmpContextError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise FmpContextError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised_only": True,
            "source_admitted": False, "historical_identity_admitted": False,
            "historical_currency_admitted": False, "market_cap_admitted": False,
            "same_class_denominator_admitted": False, "point_in_time_data": False,
            "actual_execution_authorized": False, "qc_authorized": False,
            "ready_for_empirical_backtest": False, "outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0, "trading_authority": False}


def policy():
    return {"schema": SCHEMA + "-policy", "lookup_endpoint": ENDPOINT,
            "lookup_documentation": "https://site.financialmodelingprep.com/developer/docs/stable/search-cik",
            "cap_documentation": "https://site.financialmodelingprep.com/developer/docs/stable/historical-market-cap",
            "authorization_documentation": "https://site.financialmodelingprep.com/developer/docs",
            "lookup_parameters": {"cik": "independently_source_selected_positive_CIK", "limit": 50},
            "lookup_fields": sorted(_FIELDS), "maximum_lookup_bytes": MAXIMUM_LOOKUP_BYTES,
            "maximum_lookup_rows": MAXIMUM_LOOKUP_ROWS,
            "lookup_semantics": "current_request_target_company_context_not_historical_class_currency_sector_or_availability",
            "lookup_selection": "exact_prospectively_selected_symbol_and_CIK_no_name_or_first_row_fallback",
            "CIK_format": "positive_1_to_10_decimal_digits_zero_padding_only_not_entity_inference",
            "cap_endpoint": cap.ENDPOINT, "cap_from": cap.FROM, "cap_to": cap.TO, "cap_limit": cap.LIMIT,
            "maximum_cap_bytes": cap.MAXIMUM_RESPONSE_BYTES,
            "requests": "lookup_then_at_most_one_cap_GET_per_exact_source_selected_ticket_no_paging_retries",
            "negative_lookup": "cap_skipped_receipt_unused_budget_cannot_be_repurposed",
            "reservation": "whole_page_byte_and_row_reservation_before_each_START",
            "authentication": "documented_apikey_header_memory_only_never_secret_query",
            "cap_identity": "company_series_request_context_then_same_date_exact_daily_CIK_match",
            "cap_currency": "as_trading_independent_same_date_request_target_USD_evidence_not_current_lookup_currency",
            "count": "company_market_cap_never_class_shares_or_cap_divided_by_price",
            "collision": "all_identifiable_selected_symbol_duplicate_or_malformed_peers_refused",
            "pre_hash_scope": "lookup_only_documented_nonfinancial_fields_cap_all_dates_in_frozen_range",
            "authority": _authority()}


def _cik(value):
    _require(type(value) is str and re.fullmatch(r"[0-9]{1,10}", value)
             and int(value) > 0, "positive_CIK_string_required")
    return value.zfill(10)


def _symbol(value):
    _require(type(value) is str and 1 <= len(value) <= 128
             and all(33 <= ord(char) <= 126 for char in value) and "," not in value,
             "exact_single_symbol_required")
    return value


def _utc(value):
    try:
        return parse_utc_timestamp(value, "receipt_clock")
    except (TypeError, ValueError):
        raise FmpContextError("REFUSED: UTC_receipt_clock_required") from None


def _decode(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            _require(name not in result, "duplicate_source_JSON_key")
            result[name] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(FmpContextError("REFUSED: nonfinite_source_JSON")))
        def safe_unicode(item):
            if type(item) is str:
                item.encode("utf-8")
            elif type(item) is dict:
                for key, child in item.items():
                    safe_unicode(key); safe_unicode(child)
            elif type(item) is list:
                for child in item:
                    safe_unicode(child)
        safe_unicode(value)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise FmpContextError("REFUSED: bounded_UTF8_JSON_required") from None


def preflight_lookup_scope(raw):
    """Before body hashing/storage, refuse financial/unknown source fields.

Strict duplicate-key/nonfinite refusal is receipt-only: unobserved raw paths
must not be fabricated for bodies which were deliberately not retained.
"""
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_LOOKUP_BYTES, "bounded_lookup_bytes_required")
    rows = _decode(raw)
    _require(type(rows) is list and len(rows) <= MAXIMUM_LOOKUP_ROWS, "bounded_lookup_array_required")
    for row in rows:
        _require(type(row) is dict and set(row) <= _FIELDS, "nonfinancial_lookup_field_contract")
        _require(all(value is None or type(value) is str for value in row.values()),
                 "lookup_field_type_contract")
    return rows


class _Sealed:
    __slots__ = ("_bytes", "_refs", "_anchor", "_identity")

    def __init__(self):
        raise FmpContextError("REFUSED: source_factory_required")

    def to_bytes(self):
        _require(type(self._anchor) is tuple and len(self._anchor) == 2
                 and self._anchor is self._identity and self._bytes is self._anchor[0]
                 and self._refs is self._anchor[1], "sealed_context_changed")
        for item in self._refs:
            item.to_bytes()
        return self._bytes

    def to_payload(self):
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        return hash_bytes(self.to_bytes())

    def require_actual_execution(self):
        self.to_bytes()
        raise FmpContextError("REFUSED: independent_actual_execution_gates_not_supplied")


class CompanyTargetTicket(_Sealed):
    __slots__ = ()


class ContextPlan(_Sealed):
    __slots__ = ()

    def tickets(self):
        self.to_bytes()
        return self._refs


class CompanyContextQualification(_Sealed):
    __slots__ = ()


class CompanyCapQualification(_Sealed):
    __slots__ = ()


class DatedIssuerCapBinding(_Sealed):
    __slots__ = ()


def _seal(cls, payload, refs=()):
    result = object.__new__(cls)
    raw = canonical_json(payload).encode()
    anchor = (raw, refs)
    for name, value in (("_bytes", raw), ("_refs", refs), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, value)
    return result


def seal_target_ticket(source_bytes, *, expected_sha256):
    """Seal source selection evidence, not provider identity admission."""
    _require(type(source_bytes) is bytes and len(source_bytes) <= 256 * 1024
             and type(expected_sha256) is str and _HASH.fullmatch(expected_sha256)
             and hash_bytes(source_bytes) == expected_sha256, "source_selection_bytes_changed")
    value = _decode(source_bytes)
    _require(type(value) is dict and set(value) == {"schema", "symbol", "cik", "source_origins"}
             and value["schema"] == SCHEMA + "-target-proposal", "source_selection_schema")
    _symbol(value["symbol"])
    canonical_cik = _cik(value["cik"])
    origins = value["source_origins"]
    _require(type(origins) is list and 1 <= len(origins) <= 256 and all(type(origin) is dict
        and set(origin) == {"artifact_sha256", "locator"}
        and type(origin["artifact_sha256"]) is str and _HASH.fullmatch(origin["artifact_sha256"])
        and type(origin["locator"]) is str and 1 <= len(origin["locator"]) <= 512
        and all(32 <= ord(char) <= 126 for char in origin["locator"]) for origin in origins),
        "source_selection_origins_required")
    return _seal(CompanyTargetTicket, {**value, "canonical_cik": canonical_cik,
        "selection_bytes_sha256": expected_sha256, "source_selection_only": True, "authority": _authority()})


def request_descriptor(ticket, stage):
    _require(type(ticket) is CompanyTargetTicket and stage in {"lookup", "cap"}, "exact_target_and_stage_required")
    target = ticket.to_payload()
    params = ({"cik": target["canonical_cik"], "limit": MAXIMUM_LOOKUP_ROWS} if stage == "lookup" else
              {"symbol": target["symbol"], "from": cap.FROM, "to": cap.TO, "limit": cap.LIMIT})
    return {"method": "GET", "url": ENDPOINT if stage == "lookup" else cap.ENDPOINT,
            "params": params, "authentication": "apikey_header_not_recorded",
            "source_target_ticket_sha256": ticket.sha256, "stage": stage}


def clean_url(ticket, stage):
    value = request_descriptor(ticket, stage)
    return value["url"] + "?" + urlencode(value["params"])


def freeze_context_plan(tickets):
    _require(type(tickets) is tuple and bool(tickets) and len(tickets) <= 100_000
             and all(type(ticket) is CompanyTargetTicket for ticket in tickets), "finite_exact_target_tickets_required")
    keys = [(ticket.to_payload()["canonical_cik"], ticket.to_payload()["symbol"]) for ticket in tickets]
    _require(keys == sorted(set(keys)), "ordered_unique_exact_target_tickets_required")
    return _seal(ContextPlan, {"schema": SCHEMA + "-plan", "policy_sha256": hash_payload(policy()),
        "target_sha256s": [ticket.sha256 for ticket in tickets], "maximum_requests": 2 * len(tickets),
        "maximum_total_bytes": len(tickets) * (MAXIMUM_LOOKUP_BYTES + cap.MAXIMUM_RESPONSE_BYTES),
        "maximum_rows": len(tickets) * (MAXIMUM_LOOKUP_ROWS + cap.LIMIT), "authority": _authority()}, tickets)


def _response_binding(ticket, stage, raw, raw_sha256, request_sha256, started_at, received_at, http_status, content_type):
    _require(type(ticket) is CompanyTargetTicket and type(raw) is bytes
             and hash_bytes(raw) == raw_sha256
             and hash_payload(request_descriptor(ticket, stage)) == request_sha256, "request_or_raw_binding_changed")
    _require(type(http_status) is int and http_status == 200 and type(content_type) is str
             and content_type.split(";", 1)[0].strip().lower() == "application/json", "successful_JSON_response_required")
    _require(_utc(started_at) <= _utc(received_at), "response_clock_chronology")
    return {"request_sha256": request_sha256, "raw_sha256": raw_sha256, "started_at": started_at,
            "received_at": received_at, "http_status": http_status, "content_type": content_type}


def qualify_context(ticket, *, raw, raw_sha256, request_sha256, started_at, received_at,
                    http_status=200, content_type="application/json"):
    rows = preflight_lookup_scope(raw)
    receipt = _response_binding(ticket, "lookup", raw, raw_sha256, request_sha256, started_at, received_at, http_status, content_type)
    target, evidence, peers = ticket.to_payload(), [], []
    for ordinal, row in enumerate(rows):
        entry = {"row_index": ordinal, "raw_origin": {"raw_sha256": raw_sha256, "locator": f"/[{ordinal}]"},
                 "source_fields": row, "status": "refused", "reason": None}
        # Identifiable malformed copies still quarantine the selected symbol.
        if type(row.get("symbol")) is str and row["symbol"].strip() == target["symbol"]:
            peers.append(ordinal)
        try:
            _require(_symbol(row.get("symbol")) == target["symbol"], "not_selected_request_target")
            _require(_cik(row.get("cik")) == target["canonical_cik"], "request_target_CIK_mismatch")
            entry.update(status="current_company_context_candidate")
        except FmpContextError as exc:
            entry["reason"] = str(exc).removeprefix("REFUSED: ")
        evidence.append(entry)
    if len(peers) > 1:
        for ordinal in peers:
            evidence[ordinal].update(status="refused", reason="ambiguous_selected_symbol_peer")
    candidates = [row["row_index"] for row in evidence if row["status"] == "current_company_context_candidate"]
    return _seal(CompanyContextQualification, {"schema": SCHEMA + "-qualification", **receipt,
        "ticket_sha256": ticket.sha256, "policy_sha256": hash_payload(policy()),
        "symbol": target["symbol"], "canonical_cik": target["canonical_cik"], "rows": evidence,
        "selected_row_index": candidates[0] if len(candidates) == 1 else None,
        "historical_currency_from_lookup": None, "historical_class_from_lookup": None,
        "historical_sector_from_lookup": None, "authority": _authority()}, (ticket,))


def qualify_company_cap(context, *, raw, raw_sha256, request_sha256, started_at, received_at,
                        http_status=200, content_type="application/json"):
    _require(type(context) is CompanyContextQualification, "exact_company_context_required")
    company, ticket = context.to_payload(), context._refs[0]
    _require(company["selected_row_index"] is not None, "unresolved_company_context_no_cap_fallback")
    _require(_utc(company["received_at"]) <= _utc(started_at), "context_must_precede_cap_request")
    rows = cap.preflight_scope(raw)
    receipt = _response_binding(ticket, "cap", raw, raw_sha256, request_sha256, started_at, received_at, http_status, content_type)
    evidence, dates = [], {}
    for ordinal, row in enumerate(rows):
        date_candidates = list(dict.fromkeys(row.values("date")))
        for at in date_candidates:
            dates.setdefault(at, []).append(ordinal)
        entry = {"row_index": ordinal, "date_candidates": date_candidates,
                 "raw_origin": {"raw_sha256": raw_sha256, "locator": f"/[{ordinal}]"}, "status": "refused", "reason": None}
        try:
            names = [name for name, _ in row]
            _require(len(names) == len(set(names)) and set(names) == {"symbol", "date", "marketCap"}, "cap_row_field_contract")
            value = dict(row)
            _require(value["symbol"] == company["symbol"], "cap_request_target_symbol_mismatch")
            entry.update(status="issuer_size_series_candidate", date=cap._date(value["date"]),
                         market_cap=cap._cap(value["marketCap"]), issuer_cik=company["canonical_cik"])
            entry["market_cap"]["unit"] = "trading_currency_amount_independent_dated_binding_required"
        except (FmpContextError, cap.FmpCapError) as exc:
            entry["reason"] = str(exc).removeprefix("REFUSED: ")
        evidence.append(entry)
    for peers in dates.values():
        if len(peers) > 1:
            for ordinal in peers:
                evidence[ordinal].update(status="refused", reason="duplicate_or_malformed_identifiable_cap_date_peer")
    return _seal(CompanyCapQualification, {"schema": SCHEMA + "-cap-qualification", **receipt,
        "company_context_sha256": context.sha256, "policy_sha256": hash_payload(policy()),
        "symbol": company["symbol"], "issuer_cik": company["canonical_cik"], "rows": evidence,
        "currency_from_current_context": None, "same_class_shares": None, "authority": _authority()}, (context,))


def bind_dated_issuer_cap(cap_report, dated_identity):
    """Exact-date source candidates only; no settlement-to-daily projection.

CIK matches alone identify the issuer. USD-cap evidence additionally requires
a same-date row for the FMP request target itself, with the same CIK and USD.
An unrelated class's currency or a current lookup's currency is insufficient.
"""
    _require(type(cap_report) is CompanyCapQualification and type(dated_identity) is daily.DatedIdentityQualification,
             "exact_typed_cap_and_same_date_identity_required")
    series, identity = cap_report.to_payload(), dated_identity.to_payload()
    at = identity["query_date"]
    caps = [row for row in series["rows"] if row.get("date") == at and row["status"] == "issuer_size_series_candidate"]
    records = [dict(zip(daily.ROW_FIELDS, row, strict=True)) for row in identity["rows"]]
    valid = [row for row in records if not row["refusal_reasons"] and row["provider_security_id"] is not None
             and row["active"] is True and row["locale"] == "us" and row["market"] == "stocks" and row["type"] == "CS"]
    target = [row for row in valid if row["ticker"] == series["symbol"] and row["cik"] == series["issuer_cik"]
              and row["currency_name"] == "usd"]
    usd = len(target) == 1
    valid_origins = {(row["page_ordinal"], row["row_index"]) for row in valid}
    bindings = []
    for row in records:
        if row["cik"] != series["issuer_cik"] and row["ticker"] != series["symbol"]:
            continue
        reasons = list(row["refusal_reasons"])
        if (row["page_ordinal"], row["row_index"]) not in valid_origins:
            reasons.append("daily_native_candidate_unresolved")
        if row["cik"] != series["issuer_cik"]:
            reasons.append("daily_issuer_CIK_missing_or_mismatched")
        if len(caps) != 1:
            reasons.append("same_date_cap_missing_or_ambiguous")
        if not usd:
            reasons.append("same_date_request_target_USD_not_independently_observed")
        bindings.append({"identity_row_origin": [row["page_ordinal"], row["row_index"]],
            "provider_security_id": row["provider_security_id"], "share_class_figi": row["share_class_figi"],
            "status": "dated_issuer_USD_cap_source_candidate" if not reasons else "refused",
            "refusal_reasons": reasons, "cap_row_index": caps[0]["row_index"] if len(caps) == 1 else None,
            "same_class_shares": None})
    return _seal(DatedIssuerCapBinding, {"schema": SCHEMA + "-dated-binding", "date": at,
        "cap_report_sha256": cap_report.sha256, "daily_identity_sha256": hash_bytes(dated_identity.to_bytes()),
        "issuer_CIK": series["issuer_cik"], "bindings": bindings,
        "complete_daily_identity_source_row_count": len(records),
        "currency_source": "same_date_request_target_row" if usd else None,
        "current_metadata_backdated": False, "authority": _authority()}, (cap_report, dated_identity))
