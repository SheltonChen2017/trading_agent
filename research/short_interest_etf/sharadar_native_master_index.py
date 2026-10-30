"""Batched private index of source-current, rewritten Sharadar dataset keys.

Sharadar's rewritten dataset ticker keys are not historical raw-market symbols.
Resolving those keys to provider-native identifiers neither backdates the
master nor supplies a FINRA/Massive alias, share denominator, or PIT interval.
The exact captured qualification is validated once; immutable byte/cache
identity seals refuse subsequent source mutations without reparsing archives
for every lookup.  No market values, filesystem, network, or credentials enter
this module.  All row-derived outputs must remain private.
"""
from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType
from typing import Any

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.sharadar_securities_master import (
    PROTOCOL_SHA256 as MASTER_PROTOCOL_SHA256,
    CapturedSharadarMasterArchive,
    SharadarSecuritiesMasterQualification,
)

SCHEMA = "si-sharadar-native-master-index-v1"
INTERFACE_SCHEMA = "si-source-rewritten-native-provider-keys-v3"
_TABLE_GROUPS = {"stocks": "stocks", "SEP": "stocks",
                 "fundamentals": "fundamentals", "SF1": "fundamentals"}


class SharadarNativeMasterIndexError(ValueError):
    """Named refusals never interpolate source rows or private identifiers."""


def _refuse(reason: str) -> SharadarNativeMasterIndexError:
    return SharadarNativeMasterIndexError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {
        "source_only": True, "source_admitted": False, "point_in_time_data": False,
        "historical_raw_ticker_alias_admitted": False, "historical_identity_admitted": False,
        "denominator_admitted": False, "payment_or_terminal_economics_admitted": False,
        "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
        "qc_authorized": False, "production_authoritative": False,
        "trading_authority": False, "actual_outcome_looks": 0,
        "allocated_alpha": 0, "qc_attempts": 0,
    }


def _policy() -> dict[str, Any]:
    return {
        "schema": "si-sharadar-native-master-index-protocol-v1",
        "interface_schema": INTERFACE_SCHEMA,
        "master_protocol_sha256": MASTER_PROTOCOL_SHA256,
        "provider_table_groups": dict(_TABLE_GROUPS),
        "input_rule": "exact_qualification_validated_once_then_immutable_source_identity_seal",
        "key_semantic": "Sharadar_source_rewritten_current_dataset_ticker_key_not_raw_market_alias",
        "rewiring_documentation": "https://sharadar.com/docs/faqs",
        "master_reference_documentation": "https://sharadar.com/docs/tickers",
        "public_source_semantic_evidence_id": "SI-SOURCE-20261012-REWRITTEN-DATASET-KEY-01",
        "rewiring_rule": "provider_history_uses_updated_dataset_ticker_recycled_ticker_numbered_suffix_native_permaticker_unique_per_security_class",
        "collision_rule": "both_axes_all_dataset_rows_including_refused_peers_quarantine_only_canonicalization",
        "stock_rule": "unique_dataset_ticker_and_native_permaticker_no_category_based_row_drop",
        "fundamentals_rule": "unique_SF1_native_ID_matches_unique_STOCKS_explicit_primary_common_class_compatible_origin",
        "retention_rule": "all_master_row_origins_and_current_metadata_dispositions_private_no_financial_cells",
        "temporal_rule": "no_raw_alias_or_price_date_interval_or_current_classification_backdating",
        "identifier_rule": "native_sharadar_permaticker_no_FIGI_issuer_or_secondary_class_transfer",
        "denominator_rule": "dataset_key_binding_only_no_shares_or_sharefactor_interpretation",
        "publication_scope": "private_only_not_data_usability_publication",
        "authority": _authority(),
    }


PROTOCOL_SHA256 = "6400c7b682fabddcd0aab72ac436c12883189b89db12055e9ff6a019c0993a20"


def index_protocol() -> dict[str, Any]:
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_native_index_protocol_hash_mismatch")
    return payload


def _selector(value: Any) -> str:
    if (type(value) is not str or not value or len(value) > 128 or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise _refuse("canonical_bounded_provider_key_required")
    return value


def _collision_text(value: Any) -> str | None:
    # Trimming is only a *refusal* direction: malformed peers cannot make a
    # valid key unique. It never creates a positively selectable row or alias.
    if type(value) is not str:
        return None
    value = value.strip()
    if not value or len(value) > 128:
        return None
    return value


def _collision_permaticker(value: Any) -> str | None:
    value = _collision_text(value)
    if value is None or not value.isascii() or not value.isdigit():
        return None
    return value.lstrip("0") or "0"


def _source_seal(source: SharadarSecuritiesMasterQualification) -> tuple:
    if type(source) is not SharadarSecuritiesMasterQualification:
        raise _refuse("exact_master_qualification_type_required")
    try:
        captures = source.captures
        clock, identity, cached = source.retrieved_at, source._capture_identity_sha256, source._payload_json
    except AttributeError:
        raise _refuse("malformed_master_qualification") from None
    if type(captures) is not tuple or any(type(item) is not CapturedSharadarMasterArchive for item in captures):
        raise _refuse("exact_master_capture_inventory_required")
    return (source, captures, clock, identity,
            cached, tuple((item, item.raw, item.table, item.request_sha256)
                                       for item in captures))


def _check_source_seal(source: SharadarSecuritiesMasterQualification, seal: tuple) -> None:
    if (type(source) is not SharadarSecuritiesMasterQualification or source is not seal[0]
            or source.captures is not seal[1]
            or type(source.retrieved_at) is not str
            or type(source._capture_identity_sha256) is not str
            or source.retrieved_at != seal[2]
            or source._capture_identity_sha256 != seal[3] or source._payload_json is not seal[4]):
        raise _refuse("captured_master_source_changed")
    if len(source.captures) != len(seal[5]):
        raise _refuse("captured_master_source_changed")
    for current, expected in zip(source.captures, seal[5]):
        if (type(current) is not CapturedSharadarMasterArchive or current is not expected[0]
                or current.raw is not expected[1]
                or type(current.table) is not str or type(current.request_sha256) is not str
                or current.table != expected[2]
                or current.request_sha256 != expected[3]):
            raise _refuse("captured_master_source_changed")


def _rows(payload: dict[str, Any]) -> tuple[list[dict], dict, dict]:
    table = payload["tables"][0]
    rows, ticker_axes, native_axes = [], {}, {}
    for item in table["rows"]:
        raw = dict(zip(table["normalized_headers"], item["raw_cells"]))
        normalized = item["normalized"]
        table_token = _collision_text(raw.get("table"))
        group = _TABLE_GROUPS.get(table_token)
        ticker_token = _collision_text(raw.get("ticker"))
        native_token = _collision_permaticker(raw.get("permaticker"))
        row = {
            "origin": item["origin"], "provider_table_assertion": raw.get("table"),
            "dataset_group": group, "source_row_status": item["status"],
            "source_refusal_reason": item["refusal_reason"],
            "collision_ticker_token": ticker_token,
            "collision_permaticker_token": native_token,
            "provider_rewritten_key": None if normalized is None else normalized["ticker"],
            "provider_security_id": None if normalized is None else normalized["provider_security_id"],
            "native_permaticker": None if normalized is None else normalized["permaticker"],
            "isdelisted_assertion": None if normalized is None else normalized["isdelisted"],
            "current_common_stock_candidate": None if normalized is None else normalized["current_common_stock_candidate"],
            "filing_origin_assertion": None if normalized is None else normalized["filing_origin_assertion"],
            "share_class_role_assertion": None if normalized is None else normalized["share_class_role_assertion"],
            "index_disposition": "outside_dataset_groups" if group is None else
                                 "refused_master_row" if normalized is None else "source_current_candidate",
        }
        encoded = canonical_json(row)
        rows.append(row)
        if group is not None:
            if ticker_token is not None:
                ticker_axes.setdefault((group, ticker_token), []).append(encoded)
            if native_token is not None:
                native_axes.setdefault((group, native_token), []).append(encoded)
    return rows, {key: tuple(value) for key, value in ticker_axes.items()}, {
        key: tuple(value) for key, value in native_axes.items()
    }


def _unique(rows: tuple[str, ...], ticker_axes: dict, native_axes: dict,
            group: str) -> tuple[dict | None, list[dict], list[str]]:
    candidates = [json.loads(row) for row in rows]
    if not candidates:
        return None, [], ["missing_provider_dataset_key"]
    if len(candidates) != 1:
        return None, candidates, ["ambiguous_provider_dataset_key"]
    candidate = candidates[0]
    if candidate["source_row_status"] != "normalized_source_assertion":
        return None, candidates, ["refused_provider_master_row"]
    ticker = candidate["provider_rewritten_key"]
    native = candidate["native_permaticker"]
    if (len(ticker_axes.get((group, ticker), ())) != 1
            or len(native_axes.get((group, native), ())) != 1):
        peers = native_axes.get((group, native), ())
        return None, candidates + [json.loads(row) for row in peers if row != rows[0]], [
            "ambiguous_native_identifier_or_dataset_key"
        ]
    return candidate, candidates, []


@dataclasses.dataclass(frozen=True, slots=True)
class SharadarNativeMasterIndex:
    """Detached immutable indexes; no full archive parse on batched lookup."""

    qualification: SharadarSecuritiesMasterQualification = dataclasses.field(repr=False)
    _source_seal: tuple = dataclasses.field(init=False, repr=False)
    _ticker_axes: MappingProxyType = dataclasses.field(init=False, repr=False)
    _native_axes: MappingProxyType = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)
    _identity_seal: tuple = dataclasses.field(init=False, repr=False)
    _identity_seal_anchor: tuple = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not SharadarNativeMasterIndex:
            raise _refuse("exact_native_index_type_required")
        index_protocol()
        seal = _source_seal(self.qualification)
        source = SharadarSecuritiesMasterQualification.to_payload(self.qualification)
        _check_source_seal(self.qualification, seal)
        rows, ticker_axes, native_axes = _rows(source)
        payload = {
            "schema": SCHEMA, "interface_schema": INTERFACE_SCHEMA,
            "protocol_sha256": PROTOCOL_SHA256, "source_report_sha256": source["report_sha256"],
            "source_capture_identity_sha256": source["capture_identity_sha256"],
            "source_master_protocol_sha256": source["protocol_sha256"],
            "source_retrieved_at": source["retrieved_at"],
            "master_archive_sha256": source["tables"][0]["archive_sha256"],
            "master_CSV_sha256": source["tables"][0]["CSV_sha256"],
            "source_schema_refusals": source["tables"][0]["schema_refusals"],
            "lookup_semantic": "Sharadar_source_rewritten_dataset_key_only_not_historical_raw_alias",
            "population_scope": "all_captured_master_rows_no_historical_US_universe_admission",
            "publication_scope": "private_only_not_data_usability_publication",
            "rows": rows, "authority": _authority(),
        }
        payload["index_sha256"] = hash_payload(payload)
        encoded = canonical_json(payload)
        tickers, natives = MappingProxyType(ticker_axes), MappingProxyType(native_axes)
        object.__setattr__(self, "_source_seal", seal)
        object.__setattr__(self, "_ticker_axes", tickers)
        object.__setattr__(self, "_native_axes", natives)
        object.__setattr__(self, "_payload_json", encoded)
        identity_seal = (seal, tickers, natives, encoded, payload["index_sha256"])
        object.__setattr__(self, "_identity_seal", identity_seal)
        # Anchor the exact initialization seal object independently. Merely
        # comparing its first four entries would permit a forged fifth digest
        # to change sha256 and resolutions without changing the indexed bytes.
        object.__setattr__(self, "_identity_seal_anchor", identity_seal)

    def _guard(self) -> None:
        if type(self) is not SharadarNativeMasterIndex:
            raise _refuse("exact_native_index_type_required")
        index_protocol()
        try:
            seal = self._identity_seal
            anchor = self._identity_seal_anchor
        except AttributeError:
            raise _refuse("malformed_native_index") from None
        if seal is not anchor or type(seal) is not tuple or len(seal) != 5:
            raise _refuse("captured_native_index_changed")
        if (self._source_seal is not seal[0] or self._ticker_axes is not seal[1]
                or self._native_axes is not seal[2] or self._payload_json is not seal[3]):
            raise _refuse("captured_native_index_changed")
        _check_source_seal(self.qualification, self._source_seal)

    def to_payload(self) -> dict[str, Any]:
        SharadarNativeMasterIndex._guard(self)
        return json.loads(self._payload_json)

    @property
    def sha256(self) -> str:
        SharadarNativeMasterIndex._guard(self)
        return self._identity_seal[4]

    def resolve_rewritten_provider_key(self, ticker: str, table: str = "stocks") -> dict[str, Any]:
        """Resolve provider dataset keys only; raw-market callers must not use it."""
        SharadarNativeMasterIndex._guard(self)
        ticker = _selector(ticker)
        if type(table) is not str or table not in {"stocks", "fundamentals"}:
            raise _refuse("supported_provider_dataset_table_required")
        candidate, peers, reasons = _unique(
            self._ticker_axes.get((table, ticker), ()), self._ticker_axes, self._native_axes, table,
        )
        stock = candidate if table == "stocks" else None
        if candidate is not None and table == "fundamentals":
            stock, stock_peers, stock_reasons = _unique(
                self._native_axes.get(("stocks", candidate["native_permaticker"]), ()),
                self._ticker_axes, self._native_axes, "stocks",
            )
            peers.extend(stock_peers)
            reasons.extend(stock_reasons)
            if stock is not None:
                if (stock["share_class_role_assertion"] != "Primary Class"
                        or stock["current_common_stock_candidate"] is not True
                        or candidate["current_common_stock_candidate"] is not True
                        or candidate["share_class_role_assertion"] == "Secondary Class"
                        or candidate["filing_origin_assertion"] != stock["filing_origin_assertion"]):
                    reasons.append("primary_class_native_table_membership_not_established")
                    stock = None
        bound = candidate is not None and stock is not None and not reasons
        payload = {
            "schema": "si-source-rewritten-native-key-resolution-v3",
            "index_sha256": self.sha256, "source_table": table, "provider_rewritten_key": ticker,
            "lookup_semantic": "source_rewritten_provider_dataset_key_not_historical_raw_market_symbol",
            "status": "bound_provider_dataset_key" if bound else "unresolved_provider_dataset_key",
            "provider_security_id": stock["provider_security_id"] if bound else None,
            "provider_dataset_key_bound": bound,
            "source_row_origins": [row["origin"] for row in peers],
            "current_STOCKS_key_assertion": stock["provider_rewritten_key"] if bound else None,
            "current_common_stock_candidate": stock["current_common_stock_candidate"] if bound else None,
            "current_class_role_assertion": stock["share_class_role_assertion"] if bound else None,
            "current_isdelisted_assertion": stock["isdelisted_assertion"] if bound else None,
            "same_share_class_denominator": None, "historical_effective_intervals": [],
            "refusal_reasons": sorted(set(reasons)), "authority": _authority(),
        }
        payload["resolution_sha256"] = hash_payload(payload)
        return payload


def build_sharadar_native_master_index(
    qualification: SharadarSecuritiesMasterQualification,
) -> SharadarNativeMasterIndex:
    return SharadarNativeMasterIndex(qualification)


def resolve_rewritten_provider_key(index: SharadarNativeMasterIndex, ticker: str,
                                   table: str = "stocks") -> dict[str, Any]:
    if type(index) is not SharadarNativeMasterIndex:
        raise _refuse("exact_native_index_type_required")
    return SharadarNativeMasterIndex.resolve_rewritten_provider_key(index, ticker, table)
