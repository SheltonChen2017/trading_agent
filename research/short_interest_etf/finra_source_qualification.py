"""Outcome-free FINRA latest-snapshot continuity, never PIT/source admission.

This pure, file-fed diagnostic has no credential or network client.  It does
not compare distributors, identify historical securities, construct a signal,
or grant retrieval/backtest authority.  Missing and ambiguous cells remain in
the frozen denominator; actual short quantities never appear in its report.
"""
from __future__ import annotations

import dataclasses
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from data.exchange_calendar import parse_session_date
from data.hashing import canonical_json, hash_bytes, hash_payload


SCHEMA = "si-finra-source-qualification-v1"
TICKERS = ("AAPL", "MSFT", "AMZN", "NVDA", "JPM", "XOM", "GOOG", "GOOGL",
           "BRK.B", "FRC", "SIVB", "TWTR")
SETTLEMENTS = ("2026-06-30", "2026-07-15", "2026-07-31", "2026-08-14")
PUBLICATIONS = ("2026-07-10", "2026-07-24", "2026-08-11", "2026-08-25")
FIELDS = ("symbolCode", "settlementDate", "currentShortPositionQuantity",
          "previousShortPositionQuantity", "revisionFlag", "stockSplitFlag",
          "marketClassCode", "issuerServicesGroupExchangeCode", "issueName")
_MAX_PAGE_BYTES = 1024 * 1024
_MAX_QUANTITY = 10**18
_SLOT_STATUSES = ("valid", "missing", "malformed", "duplicate", "ambiguous_market_class")
_CONTINUITY_STATUSES = (
    "matched", "mismatched", "missing_previous_quantity",
    *("target_" + value for value in _SLOT_STATUSES if value != "valid"),
    *("predecessor_" + value for value in _SLOT_STATUSES if value != "valid"),
)


class FinraSourceQualificationError(ValueError):
    """A malformed or unbound capture cannot become a complete diagnostic."""


class _NumberToken(str):
    """Lexical JSON number; deliberately distinct from an ordinary JSON string."""


def _authority() -> dict[str, Any]:
    return {
        "latest_stored_snapshot_only": True,
        "point_in_time_data": False, "source_admitted": False,
        "original_vintages_verified": False, "correction_timing_verified": False,
        "stable_identity_verified": False, "historical_coverage_verified": False,
        "distributor_agreement_verified": False, "backtest_ready": False,
        "outcome_access_authorized": False, "qc_authorized": False,
        "production_authoritative": False, "trading_authority": False,
        "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0,
    }


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema": "si-finra-source-qualification-protocol-v1",
        "source": "finra_otcMarket_consolidatedShortInterest",
        "purpose": "latest_snapshot_internal_previous_period_continuity_only",
        "tickers": list(TICKERS), "settlement_dates": list(SETTLEMENTS),
        "publication_dates": dict(zip(SETTLEMENTS, PUBLICATIONS)),
        "predecessor_dates": dict(zip(SETTLEMENTS[1:], SETTLEMENTS[:-1])),
        "requested_fields": list(FIELDS), "expected_slots": 48,
        "target_slots": 36, "first_settlement_predecessor_only": True,
        "query_limit": 100, "maximum_pages_per_settlement": 2,
        "maximum_pages": 8, "maximum_rows": 800,
        "maximum_page_bytes": _MAX_PAGE_BYTES,
        "quantity_rule": "JSON_number_nonnegative_integral_at_most_10^18_no_strings_or_booleans",
        "null_previous_rule": "unknown_not_zero",
        "null_current_rule": "named_refusal",
        "matching_rule": "exact_raw_symbol_and_settlement_no_aliases",
        "duplicate_rule": "all_identifiable_raw_collisions_quarantined_before_validation",
        "market_class_rule": "multiple_classes_ambiguous_never_aggregated",
        "comparison_tolerance": 0,
        "revision_rule": "null_or_R_assertion_not_historical_availability",
        "split_rule": "null_or_S_assertion_no_quantity_adjustment",
        "publication_rule": "schedule_metadata_not_actual_availability_clock",
        "report_rule": "aggregate_counts_flags_and_hashes_no_actual_quantity_rows",
        "authority": _authority(),
    }


PROTOCOL_SHA256 = "28b85fafa01d056c3483101545bb32163f968b9f9a083b874e63f0cf1ce6e4fe"


def qualification_protocol() -> dict[str, Any]:
    """Return detached frozen semantics; a caller cannot grant new authority."""
    payload = _protocol_payload()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise FinraSourceQualificationError("REFUSED: frozen protocol hash mismatch")
    return payload


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise FinraSourceQualificationError("REFUSED: duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise FinraSourceQualificationError("REFUSED: nonfinite JSON constant")


def _json(blob: bytes) -> Any:
    try:
        return json.loads(blob.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=_NumberToken, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinraSourceQualificationError("REFUSED: capture is not UTF-8 JSON") from exc


def _text(value: Any) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 512:
        raise ValueError("noncanonical_text")
    return value


def _key(row: Any) -> tuple[str, str]:
    if type(row) is not dict:
        raise ValueError("not_object")
    symbol = _text(row.get("symbolCode"))
    settlement = row.get("settlementDate")
    parse_session_date(settlement, "settlementDate")
    return symbol, settlement


def _quantity(value: Any, *, nullable: bool) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is int:
        result = value
    elif type(value) is _NumberToken:
        if len(value) > 128:
            raise ValueError("invalid_quantity")
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid_quantity") from exc
        if (not decimal.is_finite() or decimal < 0 or decimal > _MAX_QUANTITY
                or decimal != decimal.to_integral_value()):
            raise ValueError("invalid_quantity")
        result = int(decimal)
    else:
        raise ValueError("missing_current_quantity" if value is None else "invalid_quantity")
    if result < 0 or result > _MAX_QUANTITY:
        raise ValueError("invalid_quantity")
    return result


def _normalize(row: Any) -> dict[str, Any]:
    if type(row) is not dict or set(row) != set(FIELDS):
        raise ValueError("missing_or_unknown_fields")
    _key(row)
    current = _quantity(row["currentShortPositionQuantity"], nullable=False)
    previous = _quantity(row["previousShortPositionQuantity"], nullable=True)
    if row["revisionFlag"] not in (None, "R") or type(row["revisionFlag"]) not in (str, type(None)):
        raise ValueError("invalid_revision_flag")
    if row["stockSplitFlag"] not in (None, "S") or type(row["stockSplitFlag"]) not in (str, type(None)):
        raise ValueError("invalid_split_flag")
    for field in ("marketClassCode", "issuerServicesGroupExchangeCode"):
        if row[field] is not None:
            _text(row[field])
    # An issue name is retained only in the raw record identity, never used to
    # resolve an alias or join a historical security.  Do not trim its spelling.
    if row["issueName"] is not None and (type(row["issueName"]) is not str or len(row["issueName"]) > 512):
        raise ValueError("invalid_issue_name")
    return {"current": current, "previous": previous,
            "revision": row["revisionFlag"], "split": row["stockSplitFlag"],
            "market_class": row["marketClassCode"]}


def _typed_tree(value: Any) -> list:
    """Type-bound parsed-record hash avoids conflating 1.0 and the string '1.0'."""
    if type(value) is _NumberToken:
        return ["number_token", str(value)]
    if type(value) is dict:
        return ["object", [[key, _typed_tree(item)] for key, item in sorted(value.items())]]
    if type(value) is list:
        return ["array", [_typed_tree(item) for item in value]]
    return [type(value).__name__, value]


def _counts(keys: tuple[str, ...]) -> dict[str, int]:
    return dict.fromkeys(keys, 0)


def _valid_sha(value: Any) -> bool:
    return (type(value) is str and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _validate_report(payload: Any) -> dict:
    fields = {"schema", "protocol_sha256", "authority", "source_semantic", "pages",
              "source_record_set_sha256", "totals", "slot_status_counts",
              "continuity_status_counts", "refusal_reason_counts", "market_class_counts",
              "revision_flag_counts", "split_flag_counts", "capture_structurally_complete",
              "continuity_comparison_complete", "continuity_consistent", "report_sha256"}
    if type(payload) is not dict or set(payload) != fields:
        raise FinraSourceQualificationError("REFUSED: report schema differs")
    qualification_protocol()
    if (payload["schema"] != SCHEMA or payload["protocol_sha256"] != PROTOCOL_SHA256
            or payload["authority"] != _authority()
            or type(payload["authority"]) is not dict
            or any(type(payload["authority"][key]) is not type(expected)
                   for key, expected in _authority().items())
            or payload["source_semantic"] != "latest_stored_FINRA_internal_continuity_not_PIT_or_distributor_agreement"):
        raise FinraSourceQualificationError("REFUSED: report semantics or authority differs")
    for field, keys, expected in (("slot_status_counts", _SLOT_STATUSES, 48),
                                 ("continuity_status_counts", _CONTINUITY_STATUSES, 36)):
        values = payload[field]
        if (type(values) is not dict or set(values) != set(keys)
                or any(type(value) is not int or value < 0 for value in values.values())
                or sum(values.values()) != expected):
            raise FinraSourceQualificationError("REFUSED: frozen denominator differs")
    totals = payload["totals"]
    total_keys = {"expected_slots", "target_slots", "raw_rows", "valid_slots",
                  "refused_rows", "out_of_sample_rows", "unidentifiable_rows"}
    if (type(totals) is not dict or set(totals) != total_keys
            or any(type(value) is not int or value < 0 for value in totals.values())
            or totals["expected_slots"] != 48 or totals["target_slots"] != 36
            or totals["valid_slots"] != payload["slot_status_counts"]["valid"]
            or totals["raw_rows"] != totals["valid_slots"] + totals["refused_rows"]
            or totals["raw_rows"] > 800):
        raise FinraSourceQualificationError("REFUSED: report totals differ")
    pages = payload["pages"]
    if type(pages) is not list or not 1 <= len(pages) <= 8:
        raise FinraSourceQualificationError("REFUSED: report pages differ")
    for index, page in enumerate(pages):
        if (type(page) is not dict or set(page) != {"page_index", "sha256", "row_count"}
                or type(page["page_index"]) is not int or page["page_index"] != index
                or not _valid_sha(page["sha256"])
                or type(page["row_count"]) is not int or not 0 <= page["row_count"] <= 100):
            raise FinraSourceQualificationError("REFUSED: report page descriptor differs")
    if sum(page["row_count"] for page in pages) != totals["raw_rows"]:
        raise FinraSourceQualificationError("REFUSED: report page totals differ")
    for field in ("refusal_reason_counts", "market_class_counts", "revision_flag_counts", "split_flag_counts"):
        values = payload[field]
        if (type(values) is not dict or any(type(key) is not str or not key for key in values)
                or any(type(value) is not int or value < 0 for value in values.values())):
            raise FinraSourceQualificationError("REFUSED: report metadata counts differ")
    for field in ("market_class_counts", "revision_flag_counts", "split_flag_counts"):
        if sum(payload[field].values()) != totals["valid_slots"]:
            raise FinraSourceQualificationError("REFUSED: report flag denominator differs")
    structural = totals["valid_slots"] == 48 and totals["refused_rows"] == 0
    comparisons = payload["continuity_status_counts"]
    complete = comparisons["matched"] + comparisons["mismatched"] == 36
    for field, expected in (("capture_structurally_complete", structural),
                            ("continuity_comparison_complete", complete),
                            ("continuity_consistent", structural and complete and comparisons["mismatched"] == 0)):
        if type(payload[field]) is not bool or payload[field] != expected:
            raise FinraSourceQualificationError("REFUSED: report completeness differs")
    if (not _valid_sha(payload["source_record_set_sha256"])
            or not _valid_sha(payload["report_sha256"])
            or payload["report_sha256"] != hash_payload({key: value for key, value in payload.items() if key != "report_sha256"})):
        raise FinraSourceQualificationError("REFUSED: report digest differs")
    return payload


@dataclasses.dataclass(frozen=True)
class FinraSourceQualification:
    """Detached, canonical and hash-revalidated aggregate report."""

    payload_json: str
    _captured_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        payload = self.to_payload()
        object.__setattr__(self, "_captured_sha256", payload["report_sha256"])

    def to_payload(self) -> dict[str, Any]:
        if type(self.payload_json) is not str:
            raise FinraSourceQualificationError("REFUSED: report requires canonical JSON")
        payload = _validate_report(_json(self.payload_json.encode("utf-8")))
        if canonical_json(payload) != self.payload_json:
            raise FinraSourceQualificationError("REFUSED: report JSON is not canonical")
        captured = getattr(self, "_captured_sha256", payload["report_sha256"])
        if captured != payload["report_sha256"]:
            raise FinraSourceQualificationError("REFUSED: report changed after construction")
        return payload

    @property
    def sha256(self) -> str:
        return self.to_payload()["report_sha256"]


def qualify_finra_snapshot(
    pages: tuple[bytes, ...], *, expected_protocol_sha256: str,
) -> FinraSourceQualification:
    """Normalize only frozen SI fields and count every sample/refusal cell.

    The caller must separately verify transport, per-settlement pagination and
    the pre-retrieval publication freeze.  These bytes alone establish neither
    licensed access nor complete provider coverage.
    """
    qualification_protocol()
    if expected_protocol_sha256 != PROTOCOL_SHA256:
        raise FinraSourceQualificationError("REFUSED: expected protocol differs from frozen protocol")
    if type(pages) is not tuple or not 1 <= len(pages) <= 8:
        raise FinraSourceQualificationError("REFUSED: requires one to eight immutable page byte strings")
    sample = {(symbol, settlement) for symbol in TICKERS for settlement in SETTLEMENTS}
    entries, groups, descriptors, origins = [], {}, [], []
    for page_index, blob in enumerate(pages):
        if type(blob) is not bytes or len(blob) > _MAX_PAGE_BYTES:
            raise FinraSourceQualificationError("REFUSED: page exceeds frozen byte bound or is mutable")
        rows = _json(blob)
        if type(rows) is not list or len(rows) > 100:
            raise FinraSourceQualificationError("REFUSED: page requires bounded JSON row array")
        digest = hash_bytes(blob)
        descriptors.append({"page_index": page_index, "sha256": digest, "row_count": len(rows)})
        for row_index, raw in enumerate(rows):
            origin = {"page_index": page_index, "row_index": row_index,
                      "source_file_sha256": digest, "typed_record_sha256": hash_payload(_typed_tree(raw))}
            origins.append(origin)
            entry = {"key": None, "normalized": None, "reasons": [], "market_class": None}
            try:
                entry["key"] = _key(raw)
            except (TypeError, ValueError):
                entry["reasons"].append("unidentifiable_row")
            else:
                # Count before schema/financial validation, across all pages.
                groups.setdefault(entry["key"], []).append(entry)
                if entry["key"] not in sample:
                    entry["reasons"].append("out_of_sample_row")
                if raw.get("marketClassCode") is not None:
                    try:
                        entry["market_class"] = _text(raw["marketClassCode"])
                    except ValueError:
                        pass  # Full normalization supplies the named refusal.
            try:
                entry["normalized"] = _normalize(raw)
            except (TypeError, ValueError) as exc:
                entry["reasons"].append(str(exc))
            entries.append(entry)
    if len(entries) > 800:
        raise FinraSourceQualificationError("REFUSED: rows exceed frozen total bound")
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
        if key in sample:
            statuses[key] = status
    slot_counts = _counts(_SLOT_STATUSES)
    for key in sorted(sample):
        slot_counts[statuses.get(key, "missing")] += 1
    continuity = _counts(_CONTINUITY_STATUSES)
    for symbol in TICKERS:
        for predecessor, settlement in zip(SETTLEMENTS[:-1], SETTLEMENTS[1:]):
            target_key, predecessor_key = (symbol, settlement), (symbol, predecessor)
            target_status = statuses.get(target_key, "missing")
            predecessor_status = statuses.get(predecessor_key, "missing")
            if target_status != "valid":
                reason = "target_" + target_status
            elif predecessor_status != "valid":
                reason = "predecessor_" + predecessor_status
            elif valid[target_key]["previous"] is None:
                reason = "missing_previous_quantity"
            else:
                reason = ("matched" if valid[target_key]["previous"] == valid[predecessor_key]["current"]
                          else "mismatched")
            continuity[reason] += 1
    refusal_counts, market_classes = {}, {}
    revision_flags, split_flags = {"missing": 0, "R": 0}, {"missing": 0, "S": 0}
    for entry in entries:
        for reason in sorted(set(entry["reasons"])):
            refusal_counts[reason] = refusal_counts.get(reason, 0) + 1
    for normalized in valid.values():
        market_class = "<missing>" if normalized["market_class"] is None else normalized["market_class"]
        market_classes[market_class] = market_classes.get(market_class, 0) + 1
        # R concerns the source's prior-period revision assertion, not a
        # correction inventory or its original/public availability timestamp.
        revision_flags[normalized["revision"] or "missing"] += 1
        split_flags[normalized["split"] or "missing"] += 1
    refused_rows = sum(bool(entry["reasons"]) for entry in entries)
    structural = slot_counts["valid"] == 48 and refused_rows == 0
    complete = continuity["matched"] + continuity["mismatched"] == 36
    payload = {
        "schema": SCHEMA, "protocol_sha256": PROTOCOL_SHA256,
        "authority": _authority(),
        "source_semantic": "latest_stored_FINRA_internal_continuity_not_PIT_or_distributor_agreement",
        "pages": descriptors, "source_record_set_sha256": hash_payload(origins),
        "totals": {"expected_slots": 48, "target_slots": 36, "raw_rows": len(entries),
                   "valid_slots": slot_counts["valid"], "refused_rows": refused_rows,
                   "out_of_sample_rows": refusal_counts.get("out_of_sample_row", 0),
                   "unidentifiable_rows": refusal_counts.get("unidentifiable_row", 0)},
        "slot_status_counts": slot_counts, "continuity_status_counts": continuity,
        "refusal_reason_counts": refusal_counts, "market_class_counts": market_classes,
        "revision_flag_counts": revision_flags, "split_flag_counts": split_flags,
        "capture_structurally_complete": structural,
        "continuity_comparison_complete": complete,
        "continuity_consistent": structural and complete and continuity["mismatched"] == 0,
    }
    payload["report_sha256"] = hash_payload(payload)
    return FinraSourceQualification(canonical_json(payload))
