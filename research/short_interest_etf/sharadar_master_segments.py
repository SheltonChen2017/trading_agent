"""Pure byte-preserving segments for a private reconstructed master report.

This codec verifies storage integrity and the closed report envelope, not the
provider assertions or source fitness. A reconstruction clock is explicitly
not a recovered original report clock. No filesystem, network or admission
operation exists here, and no caller can supply an authority Boolean.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp, parse_utc_timestamp
from research.short_interest_etf.sharadar_securities_master import (
    INTERFACE_SCHEMA, MAXIMUM_REQUESTS, MAXIMUM_ROWS, PROTOCOL_SHA256 as MASTER_PROTOCOL_SHA256,
    SCHEMA as MASTER_SCHEMA, TABLES, qualification_protocol, request_sha256,
)

MAXIMUM_PART_BYTES = 32 * 1024 * 1024
MAXIMUM_REPORT_BYTES = 2 * 1024 * 1024 * 1024
MAXIMUM_PARTS = MAXIMUM_REPORT_BYTES // MAXIMUM_PART_BYTES
MAXIMUM_INDEX_BYTES = 1024 * 1024
INDEX_SCHEMA = "si-sharadar-master-segments-index-v1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = frozenset({
    "schema", "interface_schema", "protocol_sha256", "capture_identity_sha256", "retrieved_at",
    "publication_scope", "population_scope", "tables", "STOCKS_master_row_indices",
    "current_common_stock_candidate_indices", "excluded_or_refused_STOCKS_rows",
    "temporal_event_candidates", "historical_ticker_intervals", "authority", "report_sha256",
})
_TABLE_FIELDS = frozenset({"table", "request_sha256", "archive_sha256", "CSV_sha256", "headers",
    "normalized_headers", "schema_refusals", "input_row_count", "rows", "all_input_rows_retained"})
_ROW_FIELDS = frozenset({"origin", "raw_cells", "status", "normalized", "refusal_reason"})
_ORIGIN_FIELDS = frozenset({"archive_sha256", "CSV_sha256", "row_index", "raw_record_sha256"})


class SharadarMasterSegmentsError(ValueError):
    """Fixed refusal codes never expose report rows or caller values."""


def _refuse(reason: str) -> SharadarMasterSegmentsError:
    return SharadarMasterSegmentsError("REFUSED: " + reason)


def _sha(value: Any) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise _refuse("invalid_digest")
    return value


def _clock(value: Any) -> str:
    try:
        if (type(value) is not str or not value.endswith("Z")
                or format_utc_timestamp(parse_utc_timestamp(value, "reconstruction anchor")) != value):
            raise _refuse("canonical_reconstruction_clock_required")
    except (TypeError, ValueError):
        raise _refuse("canonical_reconstruction_clock_required") from None
    return value


def _authority() -> dict[str, Any]:
    return {"byte_integrity_only": True, "source_semantics_requalified": False,
            "source_admitted": False, "historical_identity_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "trading_authority": False, "new_provider_requests": 0}


def _policy() -> dict[str, Any]:
    return {"schema": "si-sharadar-master-segments-protocol-v1", "index_schema": INDEX_SCHEMA,
            "report_schema": MASTER_SCHEMA, "master_protocol_sha256": MASTER_PROTOCOL_SHA256,
            "maximum_part_bytes": MAXIMUM_PART_BYTES, "maximum_report_bytes": MAXIMUM_REPORT_BYTES,
            "maximum_parts": MAXIMUM_PARTS, "maximum_index_bytes": MAXIMUM_INDEX_BYTES,
            "layout": "ordered_contiguous_nonempty_32MiB_parts_except_final",
            "JSON": "exact_canonical_UTF8_no_duplicate_keys_floats_constants_or_byte_normalization",
            "bindings": "index_seal_part_positions_lengths_hashes_complete_bytes_report_payload_capture_identity",
            "origin_status": "refused", "origin_refusal": "private_report_size_limit",
            "origin_requests_consumed": MAXIMUM_REQUESTS,
            "clock_semantic": "observed_source_refusal_reconstruction_anchor_not_original_report_clock",
            "authority": _authority()}


PROTOCOL_SHA256 = "a5f158170fcf3803664a93f1f7bdb74b3895729d4e0ed4a3a32b14ba869a3abd"


def segment_protocol() -> dict[str, Any]:
    value = _policy()
    if hash_payload(value) != PROTOCOL_SHA256:
        raise _refuse("segment_protocol_hash_mismatch")
    qualification_protocol()
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise _refuse("duplicate_JSON_key")
        value[key] = item
    return value


def _no_float(_: str) -> Any:
    raise _refuse("floating_or_nonfinite_JSON_number")


def _integer(token: str) -> int:
    if len(token) > 512:
        raise _refuse("JSON_integer_bound")
    return int(token)


def _load_canonical(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise _refuse("invalid_bytes_or_size")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_float=_no_float, parse_constant=_no_float, parse_int=_integer)
        if type(value) is not dict or canonical_json(value).encode("utf-8") != raw:
            raise _refuse("noncanonical_JSON_bytes")
    except SharadarMasterSegmentsError:
        raise
    except (UnicodeError, TypeError, ValueError, RecursionError, OverflowError):
        raise _refuse("invalid_canonical_JSON") from None
    return value


def _closed_nested(value: Any) -> None:
    """Preserve the master's explicit non-admission semantics, never infer facts."""
    if type(value) is dict:
        for key, item in value.items():
            if key in {"historical_mapping_admitted", "terminal_economics_admitted", "point_in_time_data"} and item is not False:
                raise _refuse("master_authority_changed")
            if key in {"effective_at", "payment_timestamp", "historical_alias", "same_share_class_denominator", "share_class_figi"} and item is not None:
                raise _refuse("master_authority_changed")
            if key in {"historical_ticker_intervals", "historical_effective_intervals"} and item != []:
                raise _refuse("master_authority_changed")
            _closed_nested(item)
    elif type(value) is list:
        for item in value:
            _closed_nested(item)


def _report(raw: bytes) -> dict[str, Any]:
    segment_protocol()
    value = _load_canonical(raw, MAXIMUM_REPORT_BYTES)
    if set(value) != _REPORT_FIELDS or (value["schema"], value["interface_schema"], value["protocol_sha256"]) != (
            MASTER_SCHEMA, INTERFACE_SCHEMA, MASTER_PROTOCOL_SHA256):
        raise _refuse("master_envelope_or_protocol")
    if (value["publication_scope"] != "private_only_not_data_usability_publication"
            or value["population_scope"] != "all_captured_STOCKS_master_rows_including_delisted_no_US_market_completeness_claim"
            or canonical_json(value["authority"]) != canonical_json(qualification_protocol()["authority"])):
        raise _refuse("master_authority_changed")
    _clock(value["retrieved_at"]); _sha(value["capture_identity_sha256"]); _sha(value["report_sha256"])
    if hash_payload({key: item for key, item in value.items() if key != "report_sha256"}) != value["report_sha256"]:
        raise _refuse("master_payload_digest_mismatch")
    tables = value["tables"]
    if type(tables) is not list or len(tables) != len(TABLES):
        raise _refuse("master_table_inventory")
    identities = []
    for expected, table in zip(TABLES, tables):
        if type(table) is not dict or set(table) != _TABLE_FIELDS or table["table"] != expected:
            raise _refuse("master_table_inventory")
        if table["request_sha256"] != request_sha256("download-" + expected):
            raise _refuse("master_table_request_binding")
        _sha(table["archive_sha256"]); _sha(table["CSV_sha256"])
        if (type(table["rows"]) is not list or type(table["input_row_count"]) is not int
                or table["input_row_count"] != len(table["rows"])
                or not 0 <= len(table["rows"]) <= MAXIMUM_ROWS[expected]
                or table["all_input_rows_retained"] is not True):
            raise _refuse("master_row_inventory")
        for field in ("headers", "normalized_headers"):
            headers = table[field]
            if (type(headers) is not list or not headers or any(type(item) is not str for item in headers)
                    or len(headers) != len(set(headers))):
                raise _refuse("master_header_inventory")
        if len(table["headers"]) != len(table["normalized_headers"]) or type(table["schema_refusals"]) is not list:
            raise _refuse("master_header_inventory")
        for index, row in enumerate(table["rows"]):
            if type(row) is not dict or set(row) != _ROW_FIELDS:
                raise _refuse("master_row_shape")
            origin = row["origin"]
            if (type(origin) is not dict or set(origin) != _ORIGIN_FIELDS
                    or type(origin["row_index"]) is not int or origin["row_index"] != index
                    or origin["archive_sha256"] != table["archive_sha256"]
                    or origin["CSV_sha256"] != table["CSV_sha256"]
                    or origin["raw_record_sha256"] != hash_payload({"CSV_sha256": table["CSV_sha256"], "row_index": index})):
                raise _refuse("master_row_provenance")
            if (type(row["raw_cells"]) is not list or len(row["raw_cells"]) != len(table["headers"])
                    or any(type(item) is not str for item in row["raw_cells"])):
                raise _refuse("master_raw_cell_shape")
            if row["status"] == "normalized_source_assertion":
                if type(row["normalized"]) is not dict or row["refusal_reason"] is not None:
                    raise _refuse("master_disposition_shape")
            elif row["status"] == "refused":
                if row["normalized"] is not None or type(row["refusal_reason"]) is not str or not row["refusal_reason"]:
                    raise _refuse("master_disposition_shape")
            else:
                raise _refuse("master_disposition_shape")
        identities.append({"table": expected, "request_sha256": table["request_sha256"],
                           "archive_sha256": table["archive_sha256"]})
    if hash_payload(identities) != value["capture_identity_sha256"]:
        raise _refuse("master_capture_identity_mismatch")
    for field in ("STOCKS_master_row_indices", "current_common_stock_candidate_indices",
                  "excluded_or_refused_STOCKS_rows", "temporal_event_candidates"):
        if type(value[field]) is not list:
            raise _refuse("master_derived_inventory_shape")
    _closed_nested(value)
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class MasterReportProvenance:
    source_capture_receipt_sha256: str
    source_code_identity_sha256: str
    finalizer_code_identity_sha256: str
    reconstruction_anchor_utc: str

    def __post_init__(self):
        if type(self) is not MasterReportProvenance:
            raise _refuse("exact_provenance_type_required")
        for value in (self.source_capture_receipt_sha256, self.source_code_identity_sha256,
                      self.finalizer_code_identity_sha256):
            _sha(value)
        _clock(self.reconstruction_anchor_utc)

    def to_payload(self):
        MasterReportProvenance.__post_init__(self)
        return {**dataclasses.asdict(self), "origin_capture_status": "refused",
                "origin_capture_refusal": "private_report_size_limit",
                "origin_provider_requests_consumed": MAXIMUM_REQUESTS,
                "clock_semantic": _policy()["clock_semantic"]}


@dataclasses.dataclass(frozen=True, slots=True)
class MasterReportPart:
    position: int
    byte_length: int
    bytes_sha256: str

    def __post_init__(self):
        if (type(self) is not MasterReportPart or type(self.position) is not int
                or not 0 <= self.position < MAXIMUM_PARTS or type(self.byte_length) is not int
                or not 1 <= self.byte_length <= MAXIMUM_PART_BYTES):
            raise _refuse("invalid_exact_part_record")
        _sha(self.bytes_sha256)

    def to_payload(self):
        MasterReportPart.__post_init__(self)
        return dataclasses.asdict(self)


def _total(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= MAXIMUM_REPORT_BYTES:
        raise _refuse("total_report_size_limit")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class MasterReportIndex:
    provenance: MasterReportProvenance
    report_byte_length: int
    report_bytes_sha256: str
    report_payload_sha256: str
    capture_identity_sha256: str
    parts: tuple[MasterReportPart, ...]
    _sealed: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not MasterReportIndex:
            raise _refuse("exact_index_type_required")
        object.__setattr__(self, "_sealed", canonical_json(self._payload()))

    def _payload(self):
        segment_protocol()
        if type(self.provenance) is not MasterReportProvenance:
            raise _refuse("exact_provenance_type_required")
        _total(self.report_byte_length)
        for value in (self.report_bytes_sha256, self.report_payload_sha256, self.capture_identity_sha256):
            _sha(value)
        if (type(self.parts) is not tuple or not 1 <= len(self.parts) <= MAXIMUM_PARTS
                or any(type(part) is not MasterReportPart for part in self.parts)):
            raise _refuse("immutable_exact_part_inventory_required")
        parts = [part.to_payload() for part in self.parts]
        if (any(part.position != index for index, part in enumerate(self.parts))
                or any(part.byte_length != MAXIMUM_PART_BYTES for part in self.parts[:-1])
                or sum(part.byte_length for part in self.parts) != self.report_byte_length):
            raise _refuse("ordered_contiguous_part_layout")
        return {"schema": INDEX_SCHEMA, "segment_protocol_sha256": PROTOCOL_SHA256,
                "master_protocol_sha256": MASTER_PROTOCOL_SHA256, "report_schema": MASTER_SCHEMA,
                "provenance": self.provenance.to_payload(), "report_byte_length": self.report_byte_length,
                "report_bytes_sha256": self.report_bytes_sha256, "report_payload_sha256": self.report_payload_sha256,
                "capture_identity_sha256": self.capture_identity_sha256, "parts": parts, "authority": _authority()}

    def to_payload(self):
        value = self._payload()
        if canonical_json(value) != self._sealed:
            raise _refuse("index_identity_changed")
        value["index_sha256"] = hash_payload(value)
        return value

    def to_bytes(self) -> bytes:
        raw = canonical_json(self.to_payload()).encode("utf-8")
        if len(raw) > MAXIMUM_INDEX_BYTES:
            raise _refuse("index_size_limit")
        return raw

    @classmethod
    def from_bytes(cls, raw: bytes):
        value = _load_canonical(raw, MAXIMUM_INDEX_BYTES)
        try:
            provenance_raw = value["provenance"]
            provenance = MasterReportProvenance(**{field.name: provenance_raw[field.name]
                                                  for field in dataclasses.fields(MasterReportProvenance)})
            parts = tuple(MasterReportPart(**part) for part in value["parts"])
            result = cls(provenance, value["report_byte_length"], value["report_bytes_sha256"],
                         value["report_payload_sha256"], value["capture_identity_sha256"], parts)
        except SharadarMasterSegmentsError:
            raise
        except (TypeError, ValueError, KeyError):
            raise _refuse("invalid_index_shape") from None
        if canonical_json(result.to_payload()) != canonical_json(value):
            raise _refuse("index_envelope_or_digest_mismatch")
        return result


@dataclasses.dataclass(frozen=True, slots=True)
class SegmentedMasterReport:
    index: MasterReportIndex
    parts: tuple[bytes, ...] = dataclasses.field(repr=False)

    def __post_init__(self):
        if type(self) is not SegmentedMasterReport or type(self.index) is not MasterReportIndex:
            raise _refuse("exact_segmented_report_type_required")
        self.index.to_payload()
        if (type(self.parts) is not tuple or len(self.parts) != len(self.index.parts)
                or any(type(part) is not bytes for part in self.parts)
                or any(len(part) != expected.byte_length or hash_bytes(part) != expected.bytes_sha256
                       for part, expected in zip(self.parts, self.index.parts))):
            raise _refuse("segmented_report_part_binding")


def _parts(parts: Any) -> bytes:
    if (type(parts) is not tuple or not 1 <= len(parts) <= MAXIMUM_PARTS
            or any(type(part) is not bytes or not 1 <= len(part) <= MAXIMUM_PART_BYTES for part in parts)
            or any(len(part) != MAXIMUM_PART_BYTES for part in parts[:-1])):
        raise _refuse("immutable_bounded_ordered_byte_parts_required")
    _total(sum(len(part) for part in parts))
    return b"".join(parts)


def build_index_for_parts(parts: tuple[bytes, ...], *, provenance: MasterReportProvenance) -> MasterReportIndex:
    if type(provenance) is not MasterReportProvenance:
        raise _refuse("exact_provenance_type_required")
    provenance.to_payload()
    raw = _parts(parts)
    report = _report(raw)
    if report["retrieved_at"] != provenance.reconstruction_anchor_utc:
        raise _refuse("reconstruction_anchor_mismatch")
    return MasterReportIndex(provenance, len(raw), hash_bytes(raw), report["report_sha256"],
                             report["capture_identity_sha256"], tuple(MasterReportPart(index, len(part), hash_bytes(part))
                                                                     for index, part in enumerate(parts)))


def encode_report(raw: bytes, *, provenance: MasterReportProvenance) -> SegmentedMasterReport:
    if type(raw) is not bytes:
        raise _refuse("exact_report_bytes_required")
    _total(len(raw))
    parts = tuple(raw[index:index + MAXIMUM_PART_BYTES] for index in range(0, len(raw), MAXIMUM_PART_BYTES))
    return SegmentedMasterReport(build_index_for_parts(parts, provenance=provenance), parts)


def decode_report(index: MasterReportIndex, parts: tuple[bytes, ...]) -> bytes:
    if type(index) is not MasterReportIndex:
        raise _refuse("exact_index_type_required")
    index.to_payload()
    if type(parts) is not tuple or len(parts) != len(index.parts):
        raise _refuse("part_inventory_mismatch")
    raw = _parts(parts)
    for part, expected in zip(parts, index.parts):
        if len(part) != expected.byte_length or hash_bytes(part) != expected.bytes_sha256:
            raise _refuse("part_length_or_digest_mismatch")
    if len(raw) != index.report_byte_length or hash_bytes(raw) != index.report_bytes_sha256:
        raise _refuse("complete_bytes_digest_mismatch")
    report = _report(raw)
    if (report["report_sha256"] != index.report_payload_sha256
            or report["capture_identity_sha256"] != index.capture_identity_sha256
            or report["retrieved_at"] != index.provenance.reconstruction_anchor_utc):
        raise _refuse("report_index_binding_mismatch")
    return raw
