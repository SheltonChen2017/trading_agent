"""Frozen, source-only FINRA raw-symbol and historical presence calibration.

The existing v1 strict parser is an intentional private lane dependency.  Its
fields, numeric-token types and duplicate-key rules are reused without changing
v1's protocol or admitting a new source.  These nonadjacent historical dates
are presence probes, never predecessor-continuity comparisons.  Class-share
spellings remain independent raw strings; observed presence cannot select an
alias, establish a stable identity, or prove historical/PIT coverage.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.finra_source_qualification as _v1


SCHEMA = "si-finra-source-calibration-v1"
_HISTORICAL_DATES = (
    "2022-10-14", "2022-11-15", "2023-02-28", "2023-03-15",
    "2023-04-14", "2023-05-15",
)
_HISTORICAL_SYMBOLS = ("FRC", "SIVB", "TWTR")
_FORMAT_SYMBOLS = ("BRK.B", "BRK/B", "BRK-B", "BRKB", "BRK B")
_MAX_PAGE_BYTES = 1024 * 1024
_STATUSES = ("valid", "missing", "malformed", "duplicate", "ambiguous_market_class")
_SOURCE_SEMANTIC = "latest_stored_FINRA_raw_symbol_presence_not_identity_coverage_or_PIT"


class FinraSourceCalibrationError(ValueError):
    """A changed protocol or unbound/incomplete capture is refused."""


def _refuse(reason: str) -> FinraSourceCalibrationError:
    return FinraSourceCalibrationError(f"REFUSED: {reason}")


def _authority() -> dict[str, Any]:
    return {
        "latest_stored_snapshot_only": True,
        "point_in_time_data": False, "source_admitted": False,
        "original_vintages_verified": False, "correction_timing_verified": False,
        "stable_identity_verified": False, "historical_coverage_verified": False,
        "raw_symbol_alias_selected": False, "backtest_ready": False,
        "outcome_access_authorized": False, "qc_authorized": False,
        "production_authoritative": False, "trading_authority": False,
        "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0,
    }


def _queries() -> list[dict[str, Any]]:
    return [
        {"query_id": "hist-" + settlement, "panel": "historical",
         "settlement_date": settlement, "raw_symbols": list(_HISTORICAL_SYMBOLS)}
        for settlement in _HISTORICAL_DATES
    ] + [{"query_id": "format-2026-06-30", "panel": "format",
          "settlement_date": "2026-06-30", "raw_symbols": list(_FORMAT_SYMBOLS)}]


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema": "si-finra-source-calibration-protocol-v1",
        "source": "finra_otcMarket_consolidatedShortInterest",
        "purpose": "historical_raw_symbol_presence_and_class_spelling_only",
        "queries": _queries(), "historical_cells": 18, "format_cells": 5,
        "expected_cells": 23, "requested_fields": list(_v1.FIELDS),
        "normalizer_protocol_sha256": _v1.PROTOCOL_SHA256,
        "query_limit": 100, "maximum_pages_per_query": 2,
        "maximum_source_posts": 8, "maximum_pages": 8,
        "maximum_rows": 800, "maximum_records_per_query": 200,
        "maximum_page_bytes": _MAX_PAGE_BYTES, "source_retries": 0,
        "request_rule": "settlement_equal_symbol_domain_sort_symbol_async_false",
        "pagination_rule": "query_bound_request_hash_exact_offsets_stable_total_and_headers",
        "http_response_rule": "200_strict_JSON_array_or_204_exact_empty_body_zero_total_zero_offset_required_pagination_headers_v1",
        "duplicate_rule": "all_identifiable_raw_collisions_quarantined_before_validation",
        "market_class_rule": "multiple_raw_classes_ambiguous_never_aggregated",
        "previous_null_rule": "unknown_not_zero_no_nonadjacent_continuity_test",
        "revision_split_rule": "source_flags_only_no_adjustment_or_availability_inference",
        "calendar_rule": "rule_consistent_settlement_dates_no_archived_calendar_or_availability_verification",
        "historical_date_context": {
            "SIVB": "2023-02-28_pre_halt_2023-03-15_post_halt_before_formal_suspension",
            "FRC": "2023-04-14_pre_suspension_2023-05-15_post_suspension",
            "TWTR": "2022-10-14_pre_merger_2022-11-15_post_delisting",
        },
        "format_rule": "independent_raw_spellings_no_alias_selection_or_identity_join",
        "documented_nasdaq_conventions": ["BRK.B", "BRK B"],
        "other_spellings": "diagnostic_only",
        "absence_rule": "no_matching_raw_row_in_complete_query_not_zero_or_coverage_failure",
        "report_rule": "cell_status_counts_flags_and_hashes_no_quantities_or_issue_names",
        "authority": _authority(),
    }


PROTOCOL_SHA256 = "fdf25f4fcf1b20b52f98ba3c57f9618b2548fdc356a0a1303169fcffea41486b"


def calibration_protocol() -> dict[str, Any]:
    """Detached frozen design; no caller can change scope or open authority."""
    _v1.qualification_protocol()
    payload = _protocol_payload()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen calibration protocol hash mismatch")
    return payload


def _query(query_id: Any) -> dict[str, Any]:
    if type(query_id) is not str:
        raise _refuse("unknown calibration query")
    for query in _queries():
        if query["query_id"] == query_id:
            return query
    raise _refuse("unknown calibration query")


def _integer(value: Any, name: str, minimum: int = 0, maximum: int = 200) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _refuse(f"invalid {name}")
    return value


def _sha(value: Any, name: str) -> str:
    if not _v1._valid_sha(value):
        raise _refuse(f"invalid {name}")
    return value


def calibration_request(query_id: str, offset: int) -> dict[str, Any]:
    """One exact frozen data-POST body; no network or arbitrary filters."""
    calibration_protocol()
    query = _query(query_id)
    _integer(offset, "offset", maximum=199)
    return {
        "fields": list(_v1.FIELDS),
        "compareFilters": [{"fieldName": "settlementDate", "fieldValue": query["settlement_date"], "compareType": "equal"}],
        "domainFilters": [{"fieldName": "symbolCode", "values": list(query["raw_symbols"])}],
        "sortFields": ["symbolCode"], "limit": 100, "offset": offset, "async": False,
    }


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedFinraCalibrationPage:
    """Source bytes plus query/pagination claims, rechecked by the consumer.

    This cannot authenticate HTTP transport or credentials.  The capture
    driver must retain those receipts privately and count every attempted POST.
    """

    query_id: str
    offset: int
    total: int
    limit: int
    max_limit: int
    data_version: str
    request_sha256: str
    raw: bytes
    http_status: int = 200

    def __post_init__(self) -> None:
        if type(self) is not CapturedFinraCalibrationPage:
            raise _refuse("page requires exact CapturedFinraCalibrationPage type")
        _query(self.query_id)
        _integer(self.offset, "offset", maximum=199)
        _integer(self.total, "total")
        _integer(self.limit, "limit", minimum=100, maximum=100)
        _integer(self.max_limit, "max_limit", minimum=100, maximum=10**9)
        if type(self.data_version) is not str or self.data_version != "1":
            raise _refuse("data version differs")
        _sha(self.request_sha256, "request_sha256")
        if type(self.raw) is not bytes or len(self.raw) > _MAX_PAGE_BYTES:
            raise _refuse("page requires immutable bounded raw bytes")
        if type(self.http_status) is not int or self.http_status not in (200, 204):
            raise _refuse("unsupported page HTTP status")
        if self.http_status == 204 and (self.total != 0 or self.offset != 0 or self.raw != b""):
            raise _refuse("204 requires exact empty body and zero-total zero-offset header proof")


def _parse_pages(pages: tuple[CapturedFinraCalibrationPage, ...]) -> tuple[list[dict], list[dict]]:
    if type(pages) is not tuple or not 7 <= len(pages) <= 8:
        raise _refuse("capture requires seven or eight query-bound pages")
    queries = _queries()
    indexes = {query["query_id"]: index for index, query in enumerate(queries)}
    grouped = {query["query_id"]: [] for query in queries}
    descriptors, entries = [], []
    previous_query_index = -1
    for page_index, supplied in enumerate(pages):
        if type(supplied) is not CapturedFinraCalibrationPage:
            raise _refuse("page requires exact CapturedFinraCalibrationPage type")
        # Reconstruct exact schema fields; never trust a potentially modified
        # frozen object or an instance-shadowed validation method.
        page = CapturedFinraCalibrationPage(**{
            field.name: getattr(supplied, field.name)
            for field in dataclasses.fields(CapturedFinraCalibrationPage)
        })
        query = _query(page.query_id)
        if indexes[page.query_id] < previous_query_index:
            raise _refuse("mixed or reordered query pagination")
        previous_query_index = indexes[page.query_id]
        if page.request_sha256 != hash_payload(calibration_request(page.query_id, page.offset)):
            raise _refuse("page request hash differs from frozen query")
        try:
            # Keep the actual empty bytes and their digest.  A verified 204 is
            # a zero-row response, not a fabricated JSON array or missing field.
            rows = [] if page.http_status == 204 else _v1._json(page.raw)
        except _v1.FinraSourceQualificationError as exc:
            raise _refuse(str(exc)) from exc
        if type(rows) is not list or len(rows) > 100:
            raise _refuse("page requires bounded JSON row array")
        digest = hash_bytes(page.raw)
        siblings = grouped[page.query_id]
        if len(siblings) >= 2:
            raise _refuse("query exceeds two-page bound")
        expected_offset = sum(item["row_count"] for item in siblings)
        if (page.offset != expected_offset or page.total < page.offset + len(rows)
                or (siblings and page.total != siblings[0]["total"])
                or (siblings and (page.max_limit != siblings[0]["max_limit"]
                                  or page.limit != siblings[0]["limit"]))):
            raise _refuse("incomplete stale or inconsistent pagination")
        if any(item["raw_sha256"] == digest for item in siblings):
            raise _refuse("repeated query page")
        if not rows and (page.offset < page.total or siblings):
            raise _refuse("pagination made no progress")
        descriptor = {
            "page_index": page_index, "query_id": page.query_id,
            "offset": page.offset, "total": page.total, "limit": page.limit,
            "max_limit": page.max_limit, "data_version": page.data_version,
            "http_status": page.http_status,
            "request_sha256": page.request_sha256, "raw_sha256": digest,
            "row_count": len(rows),
        }
        descriptors.append(descriptor)
        siblings.append(descriptor)
        for row_index, raw in enumerate(rows):
            origin = {"page_index": page_index, "row_index": row_index,
                      "query_id": page.query_id, "request_sha256": page.request_sha256,
                      "raw_sha256": digest, "typed_record_sha256": hash_payload(_v1._typed_tree(raw))}
            entry = {"key": None, "normalized": None, "reasons": [], "market_class": None,
                     "origin": origin, "query_id": page.query_id}
            try:
                key = _v1._key(raw)
            except (TypeError, ValueError):
                entry["reasons"].append("unidentifiable_row")
            else:
                if key[0] not in query["raw_symbols"] or key[1] != query["settlement_date"]:
                    raise _refuse("response row differs from bound query")
                entry["key"] = key
                if raw.get("marketClassCode") is not None:
                    try:
                        entry["market_class"] = _v1._text(raw["marketClassCode"])
                    except ValueError:
                        pass
            try:
                entry["normalized"] = _v1._normalize(raw)
            except (TypeError, ValueError) as exc:
                entry["reasons"].append(str(exc))
            entries.append(entry)
    for query in queries:
        members = grouped[query["query_id"]]
        if not members or sum(member["row_count"] for member in members) != members[0]["total"]:
            raise _refuse("frozen query capture incomplete")
    return descriptors, entries


def _count(keys: tuple[str, ...]) -> dict[str, int]:
    return dict.fromkeys(keys, 0)


def _build_report(descriptors: list[dict], entries: list[dict]) -> dict[str, Any]:
    groups = {}
    for entry in entries:
        if entry["key"] is not None:
            groups.setdefault(entry["key"], []).append(entry)
    statuses, valid = {}, {}
    for key, members in groups.items():
        if len(members) > 1:
            classes = {member["market_class"] for member in members}
            status = "ambiguous_market_class" if len(classes) > 1 else "duplicate"
            for member in members:
                member["reasons"].append(status)
        elif members[0]["reasons"]:
            status = "malformed"
        else:
            status = "valid"
            valid[key] = members[0]["normalized"]
        statuses[key] = status
    cells = []
    counts = {"historical": _count(_STATUSES), "format": _count(_STATUSES)}
    for query in _queries():
        for symbol in query["raw_symbols"]:
            key = symbol, query["settlement_date"]
            status = statuses.get(key, "missing")
            counts[query["panel"]][status] += 1
            cells.append({
                "query_id": query["query_id"], "panel": query["panel"],
                "raw_symbol": symbol, "settlement_date": query["settlement_date"],
                "status": status, "raw_row_count": len(groups.get(key, [])),
                "previous_field_status": ("unknown" if valid.get(key, {}).get("previous") is None
                                          else "present") if status == "valid" else "not_valid",
                "source_record_set_sha256": hash_payload([entry["origin"] for entry in groups.get(key, [])]),
            })
    refusal_counts, classes = {}, {}
    revisions, splits = {"missing": 0, "R": 0}, {"missing": 0, "S": 0}
    previous = {"unknown": 0, "present": 0}
    for entry in entries:
        for reason in sorted(set(entry["reasons"])):
            refusal_counts[reason] = refusal_counts.get(reason, 0) + 1
    for normalized in valid.values():
        market_class = normalized["market_class"] or "<missing>"
        classes[market_class] = classes.get(market_class, 0) + 1
        revisions[normalized["revision"] or "missing"] += 1
        splits[normalized["split"] or "missing"] += 1
        previous["unknown" if normalized["previous"] is None else "present"] += 1
    payload = {
        "schema": SCHEMA, "protocol_sha256": PROTOCOL_SHA256,
        "normalizer_protocol_sha256": _v1.PROTOCOL_SHA256,
        "authority": _authority(), "source_semantic": _SOURCE_SEMANTIC,
        "pages": descriptors, "cells": cells,
        "source_record_set_sha256": hash_payload([entry["origin"] for entry in entries]),
        "totals": {"expected_cells": 23, "historical_cells": 18, "format_cells": 5,
                   "raw_rows": len(entries), "valid_cells": len(valid),
                   "refused_rows": sum(bool(entry["reasons"]) for entry in entries),
                   "unidentifiable_rows": refusal_counts.get("unidentifiable_row", 0)},
        "cell_status_counts": counts, "refusal_reason_counts": refusal_counts,
        "market_class_counts": classes, "revision_flag_counts": revisions,
        "split_flag_counts": splits, "previous_field_status_counts": previous,
        "query_capture_complete": True,
        "all_cells_present_valid": len(valid) == 23 and not any(entry["reasons"] for entry in entries),
    }
    payload["report_sha256"] = hash_payload(payload)
    return payload


def _validate_report(payload: Any) -> dict:
    calibration_protocol()
    fields = {"schema", "protocol_sha256", "normalizer_protocol_sha256", "authority", "source_semantic",
              "pages", "cells", "source_record_set_sha256", "totals", "cell_status_counts",
              "refusal_reason_counts", "market_class_counts", "revision_flag_counts", "split_flag_counts",
              "previous_field_status_counts", "query_capture_complete", "all_cells_present_valid", "report_sha256"}
    if type(payload) is not dict or set(payload) != fields:
        raise _refuse("report schema differs")
    authority = payload["authority"]
    if (payload["schema"] != SCHEMA or payload["protocol_sha256"] != PROTOCOL_SHA256
            or payload["normalizer_protocol_sha256"] != _v1.PROTOCOL_SHA256
            or payload["source_semantic"] != _SOURCE_SEMANTIC or authority != _authority()
            or type(authority) is not dict
            or any(type(authority[key]) is not type(value) for key, value in _authority().items())):
        raise _refuse("report semantics or authority differs")
    expected_cells = [(query, symbol) for query in _queries() for symbol in query["raw_symbols"]]
    if type(payload["cells"]) is not list or len(payload["cells"]) != 23:
        raise _refuse("report cell denominator differs")
    counts = {"historical": _count(_STATUSES), "format": _count(_STATUSES)}
    for cell, (query, symbol) in zip(payload["cells"], expected_cells):
        if (type(cell) is not dict or set(cell) != {"query_id", "panel", "raw_symbol", "settlement_date", "status",
                                                  "raw_row_count", "previous_field_status", "source_record_set_sha256"}
                or cell["query_id"] != query["query_id"] or cell["panel"] != query["panel"]
                or cell["raw_symbol"] != symbol or cell["settlement_date"] != query["settlement_date"]
                or cell["status"] not in _STATUSES):
            raise _refuse("report cell binding differs")
        _integer(cell["raw_row_count"], "cell row count", maximum=800)
        if (cell["previous_field_status"] not in ("unknown", "present", "not_valid")
                or (cell["status"] == "valid") != (cell["previous_field_status"] != "not_valid")
                or (cell["status"] == "missing" and cell["raw_row_count"] != 0)
                or (cell["status"] in ("valid", "malformed") and cell["raw_row_count"] != 1)
                or (cell["status"] in ("duplicate", "ambiguous_market_class") and cell["raw_row_count"] < 2)):
            raise _refuse("report cell status differs")
        _sha(cell["source_record_set_sha256"], "cell source hash")
        counts[query["panel"]][cell["status"]] += 1
    supplied_counts = payload["cell_status_counts"]
    if (type(supplied_counts) is not dict or set(supplied_counts) != {"historical", "format"}
            or any(type(supplied_counts[panel]) is not dict or set(supplied_counts[panel]) != set(_STATUSES)
                   or any(type(value) is not int or value < 0 for value in supplied_counts[panel].values())
                   for panel in ("historical", "format"))
            or supplied_counts != counts):
        raise _refuse("report status counts differ")
    totals = payload["totals"]
    total_keys = {"expected_cells", "historical_cells", "format_cells", "raw_rows", "valid_cells", "refused_rows", "unidentifiable_rows"}
    if type(totals) is not dict or set(totals) != total_keys:
        raise _refuse("report totals differ")
    for value in totals.values():
        _integer(value, "report total", maximum=800)
    valid_count = counts["historical"]["valid"] + counts["format"]["valid"]
    if (totals["expected_cells"] != 23 or totals["historical_cells"] != 18 or totals["format_cells"] != 5
            or totals["valid_cells"] != valid_count or totals["raw_rows"] != valid_count + totals["refused_rows"]
            or totals["raw_rows"] != sum(cell["raw_row_count"] for cell in payload["cells"]) + totals["unidentifiable_rows"]):
        raise _refuse("report frozen denominator or accounting differs")
    for field in ("refusal_reason_counts", "market_class_counts", "revision_flag_counts", "split_flag_counts", "previous_field_status_counts"):
        values = payload[field]
        if type(values) is not dict or any(type(key) is not str or not key for key in values):
            raise _refuse("report metadata counts differ")
        for value in values.values():
            _integer(value, "metadata count", maximum=800)
        if field != "refusal_reason_counts" and sum(values.values()) != valid_count:
            raise _refuse("report flag denominator differs")
    if (set(payload["revision_flag_counts"]) != {"missing", "R"}
            or set(payload["split_flag_counts"]) != {"missing", "S"}
            or set(payload["previous_field_status_counts"]) != {"unknown", "present"}):
        raise _refuse("report flag schema differs")
    previous_counts = {"unknown": 0, "present": 0}
    for cell in payload["cells"]:
        if cell["status"] == "valid":
            previous_counts[cell["previous_field_status"]] += 1
    if payload["previous_field_status_counts"] != previous_counts:
        raise _refuse("report previous-field counts differ")
    pages = payload["pages"]
    if type(pages) is not list or not 7 <= len(pages) <= 8:
        raise _refuse("report page count differs")
    grouped = {query["query_id"]: [] for query in _queries()}
    query_indexes = {query["query_id"]: index for index, query in enumerate(_queries())}
    previous_query_index = -1
    for index, page in enumerate(pages):
        if type(page) is not dict or set(page) != {"page_index", "query_id", "offset", "total", "limit", "max_limit", "data_version", "http_status", "request_sha256", "raw_sha256", "row_count"}:
            raise _refuse("report page schema differs")
        if page["page_index"] != index or type(page["page_index"]) is not int:
            raise _refuse("report page index differs")
        _query(page["query_id"])
        query_index = query_indexes[page["query_id"]]
        if query_index < previous_query_index:
            raise _refuse("report query order differs")
        previous_query_index = query_index
        _integer(page["row_count"], "page row count", maximum=100)
        _integer(page["offset"], "page offset", maximum=199)
        _integer(page["total"], "page total")
        _integer(page["limit"], "page limit", 100, 100)
        _integer(page["max_limit"], "page maximum", 100, 10**9)
        if page["data_version"] != "1" or page["request_sha256"] != hash_payload(calibration_request(page["query_id"], page["offset"])):
            raise _refuse("report request binding differs")
        _sha(page["raw_sha256"], "raw page hash")
        if type(page["http_status"]) is not int or page["http_status"] not in (200, 204):
            raise _refuse("report HTTP status differs")
        if page["http_status"] == 200 and page["raw_sha256"] == hash_bytes(b""):
            raise _refuse("report 200 cannot bind an empty non-JSON body")
        if page["http_status"] == 204 and (
                page["row_count"] != 0 or page["total"] != 0 or page["offset"] != 0
                or page["raw_sha256"] != hash_bytes(b"")):
            raise _refuse("report 204 empty-response proof differs")
        siblings = grouped[page["query_id"]]
        if (any(item["raw_sha256"] == page["raw_sha256"] for item in siblings)
                or (page["row_count"] == 0 and (page["offset"] < page["total"] or siblings))):
            raise _refuse("report repeated page or no progress")
        if (len(siblings) >= 2 or page["offset"] != sum(item["row_count"] for item in siblings)
                or page["total"] < page["offset"] + page["row_count"]
                or (siblings and (page["total"] != siblings[0]["total"] or page["max_limit"] != siblings[0]["max_limit"]))):
            raise _refuse("report pagination differs")
        siblings.append(page)
    if (any(not siblings or sum(page["row_count"] for page in siblings) != siblings[0]["total"] for siblings in grouped.values())
            or sum(page["row_count"] for page in pages) != totals["raw_rows"]):
        raise _refuse("report query capture incomplete")
    complete = valid_count == 23 and totals["refused_rows"] == 0
    if (payload["query_capture_complete"] is not True or type(payload["all_cells_present_valid"]) is not bool
            or payload["all_cells_present_valid"] != complete):
        raise _refuse("report completeness differs")
    _sha(payload["source_record_set_sha256"], "source record set hash")
    if _sha(payload["report_sha256"], "report hash") != hash_payload({key: value for key, value in payload.items() if key != "report_sha256"}):
        raise _refuse("report digest differs")
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class FinraCalibrationReport:
    """Quantity-free canonical report, with captured identity revalidation."""

    payload_json: str
    _captured_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        payload = FinraCalibrationReport._payload(self)
        object.__setattr__(self, "_captured_sha256", payload["report_sha256"])

    def _payload(self) -> dict[str, Any]:
        if type(self) is not FinraCalibrationReport or type(self.payload_json) is not str:
            raise _refuse("report requires exact canonical FinraCalibrationReport type")
        try:
            payload = _validate_report(_v1._json(self.payload_json.encode("utf-8")))
        except FinraSourceCalibrationError:
            raise
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise _refuse("invalid calibration report") from exc
        if canonical_json(payload) != self.payload_json:
            raise _refuse("report JSON is not canonical")
        return payload

    def to_payload(self) -> dict[str, Any]:
        payload = FinraCalibrationReport._payload(self)
        if payload["report_sha256"] != self._captured_sha256:
            raise _refuse("captured report identity changed")
        return payload

    @property
    def sha256(self) -> str:
        return FinraCalibrationReport.to_payload(self)["report_sha256"]


def calibrate_finra_sources(
    pages: tuple[CapturedFinraCalibrationPage, ...], *, expected_protocol_sha256: str,
) -> FinraCalibrationReport:
    """Bind seven source queries, retain every cell, and reveal no quantities."""
    calibration_protocol()
    if type(expected_protocol_sha256) is not str or expected_protocol_sha256 != PROTOCOL_SHA256:
        raise _refuse("expected calibration protocol differs")
    try:
        descriptors, entries = _parse_pages(pages)
        payload = _build_report(descriptors, entries)
        return FinraCalibrationReport(canonical_json(payload))
    except FinraSourceCalibrationError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise _refuse("invalid calibration capture") from exc
