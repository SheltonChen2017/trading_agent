"""Private offline ACTIONS consideration fields, never payment/economic admission.

Only retained, request-bound archives enter this pure parser. The public FAQ
defines legacy per-share cash/stock units; the captured ACTIONTYPES dictionary
must independently agree. Warehouse dates, market value and missing cash never
become shareholder payments or proceeds. No filesystem, network or credentials.
"""
from __future__ import annotations

from collections import Counter
import csv
import dataclasses
import io
import json
import re
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp, parse_utc_timestamp
import research.short_interest_etf.sharadar_securities_master as master

SCHEMA = "si-sharadar-terminal-consideration-v1"
FAQ_URL = "https://sharadar.com/docs/faqs"
FAQ_EVIDENCE_ID = "SI-SOURCE-20261013-SHARADAR-PER-SHARE-CONSIDERATION-01"
_SEAL = object()
_TERMINAL = re.compile(r"acquisition|merger|delist|liquidat|bankrupt|receivership", re.I)
_CURRENCIES = frozenset({"USD", "EUR", "GBP", "HKD", "SGD", "CAD", "CHF", "JPY", "AUD", "CNY", "SEK", "NOK"})
_LEGACY_UNITS = {
    "acquisitioncash": {"USD", "USD/share", "USD/target unit", "USD/target share"},
    "acquisitionstock": {"shares", "shares/share", "shares/target unit", "shares/target share", "ratio"},
}


class SharadarTerminalConsiderationError(ValueError):
    """Safe fixed reasons never interpolate private provider values."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise SharadarTerminalConsiderationError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {"source_only": True, "point_in_time_data": False,
            "consideration_and_payment_admitted": False, "historical_identity_admitted": False,
            "source_admitted": False, "ready_for_empirical_backtest": False,
            "outcome_access_authorized": False, "qc_authorized": False,
            "production_authoritative": False, "trading_authority": False,
            "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def _policy() -> dict[str, Any]:
    return {"schema": "si-sharadar-terminal-consideration-protocol-v1",
            "sources": ["fixed_captured_ACTIONS", "fixed_captured_DESCRIPTIONS"],
            "new_provider_requests": 0, "credential_reads": 0,
            "FAQ_URL": FAQ_URL, "FAQ_evidence_id": FAQ_EVIDENCE_ID,
            "legacy_semantics": {"acquisitioncash": "USD_per_acquired_share",
                                 "acquisitionstock": "survivor_shares_per_acquired_share"},
            "legacy_dictionary_units": {key: sorted(value) for key, value in _LEGACY_UNITS.items()},
            "currency_specific_semantics": "unique_dictionary_explicit_native_contractual_gross_cash_per_historical_target_unit",
            "currency_labels": sorted(_CURRENCIES),
            "numeric_rule": "bounded_lexical_Decimal_to_exact_Fraction_positive_no_binary_float",
            "selection": "terminal_action_code_or_actiontypes_description_including_identifiable_malformed_peers",
            "duplicate_rule": "all_identifiable_primary_key_or_dictionary_collisions_refused",
            "retention": "all_selected_rows_and_dictionary_origins_private_with_original_archive_digests",
            "aggregation": "separate_components_only_one_cash_plus_one_stock_no_election_CVR_or_ambiguous_peer",
            "date_rule": "source_calendar_action_date_never_payment_or_historical_availability",
            "no_amount_fallback": ["acquisitionby_marketcap", "market_price", "missing_cash_zero", "issuer_share_transfer"],
            "publication_scope": "private_only_no_rows_or_fitness_conclusions",
            "authority": _authority()}


PROTOCOL_SHA256 = "5ba0a5adaba3915312d604eb8479487bc610611ad4c784b5718834ac5ad7f953"


def consideration_protocol() -> dict[str, Any]:
    payload = _policy()
    _require(hash_payload(payload) == PROTOCOL_SHA256, "consideration_protocol_hash")
    return json.loads(canonical_json(payload))


def _rows(capture: master.CapturedSharadarMasterArchive):
    """Stream bounded CSV rows; do not materialize the full-master report."""
    _require(type(capture) is master.CapturedSharadarMasterArchive, "exact_archive_type")
    master.CapturedSharadarMasterArchive.__post_init__(capture)
    content = master.validate_archive(capture.table, capture.raw)
    try:
        text = content.decode("utf-8")
        _require("\x00" not in text, "CSV_NUL")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader)
        aliases = master._ALIASES.get(capture.table, {})
        normalized = [aliases.get(value, value) for value in headers]
        _require(0 < len(headers) <= 128 and all(type(value) is str and value
                 and value == value.strip() and len(value) <= 128
                 and all(ord(char) >= 32 and ord(char) != 127 for char in value)
                 for value in headers), "CSV_headers")
        _require(len(set(normalized)) == len(headers), "CSV_duplicate_headers")
        _require(master._REQUIRED[capture.table] <= set(normalized), "CSV_required_headers")
        origin_base = {"archive_sha256": hash_bytes(capture.raw), "CSV_sha256": hash_bytes(content)}
        schema = {"table": capture.table, "request_sha256": capture.request_sha256,
                  **origin_base, "headers": headers, "normalized_headers": normalized,
                  "schema_refusal": "unknown_CSV_columns" if set(normalized) - master._KNOWN[capture.table] else None}
        yield schema
        for index, cells in enumerate(reader):
            _require(len(cells) == len(headers), "CSV_row_width")
            _require(all(len(value) <= master.MAXIMUM_FIELD_CHARACTERS for value in cells), "CSV_field_limit")
            _require(index < master.MAXIMUM_ROWS[capture.table], "CSV_row_limit")
            origin = {**origin_base, "row_index": index,
                      "raw_record_sha256": hash_payload({"CSV_sha256": origin_base["CSV_sha256"], "row_index": index})}
            yield {"origin": origin, "raw_cells": cells, "raw": dict(zip(normalized, cells))}
    except (csv.Error, StopIteration, UnicodeError) as exc:
        raise SharadarTerminalConsiderationError("REFUSED: malformed_CSV") from exc


def _dictionary(capture):
    stream = _rows(capture)
    schema = next(stream)
    entries, count = [], 0
    for item in stream:
        count += 1
        raw = item["raw"]
        # Refusal-only normalization includes malformed identifiable peers.
        if raw["table"].strip().lower() != "actiontypes":
            continue
        try:
            normalized = master._normalize("descriptions", raw)
            _require(raw["table"] == "actiontypes", "dictionary_table_not_exact")
            _require(bool(raw["indicator"]) and bool(raw["description"]), "dictionary_missing_semantics")
            refusal = schema["schema_refusal"]
        except (master.SharadarSecuritiesMasterError, SharadarTerminalConsiderationError):
            normalized, refusal = None, "dictionary_malformed"
        entries.append({"origin": item["origin"], "raw_cells": item["raw_cells"],
                        "raw": raw, "normalized": normalized, "refusal_reason": refusal})
    by_code = {}
    for item in entries:
        by_code.setdefault(item["raw"]["indicator"].strip(), []).append(item)
    for peers in by_code.values():
        if len(peers) > 1:
            for item in peers:
                item["refusal_reason"] = "dictionary_duplicate_all_peers_refused"
    schema["input_row_count"] = count
    return schema, entries, by_code


def _meaning(code, entry):
    """An explicit conservative contract, not free-text inference of payments."""
    row = entry["normalized"]
    if row is None or entry["refusal_reason"]:
        return None, entry["refusal_reason"] or "dictionary_malformed"
    description = " ".join(row["description"].casefold().split())
    title = row["title"].casefold()
    if any(term in description for term in ("market cap", "market capitalization", "deal size", "enterprise value", "weighted")):
        return None, "dictionary_conflicts_with_per_target_consideration"
    if code in _LEGACY_UNITS:
        wanted = "cash" if code == "acquisitioncash" else "stock"
        if (row["unittype"] not in _LEGACY_UNITS[code] or wanted not in title
                or "acquisition" not in title or "share" not in description
                or wanted not in description):
            return None, "legacy_dictionary_FAQ_semantics_unverified"
        return {"kind": "cash" if code == "acquisitioncash" else "received_stock",
                "currency": "USD" if code == "acquisitioncash" else None,
                "unit": "acquired_share", "semantic_evidence_id": FAQ_EVIDENCE_ID}, None
    match = re.fullmatch(r"acquisitioncash([a-z]{3})", code)
    if match is not None:
        currency = match.group(1).upper()
        if (currency not in _CURRENCIES or row["unittype"] != currency + "/target unit"
                or not all(term in description for term in ("native cash consideration", "contractual gross cash", "per historical target listing unit"))
                or currency.casefold() not in description):
            return None, "currency_specific_dictionary_semantics_unverified"
        return {"kind": "cash", "currency": currency, "unit": "historical_target_listing_unit",
                "semantic_evidence_id": "captured_exact_ACTIONTYPES_dictionary"}, None
    return None, ("aggregate_market_value_not_consideration" if code == "acquisitionby"
                  else "election_alternative_not_additive" if "elect" in code or "alternative" in code or "cohort" in code
                  else "unsupported_terminal_action_semantics")


def _build(actions, descriptions, *, retrieved_at):
    consideration_protocol()
    _require(type(actions) is master.CapturedSharadarMasterArchive and actions.table == "actions"
             and type(descriptions) is master.CapturedSharadarMasterArchive and descriptions.table == "descriptions",
             "ordered_ACTIONS_DESCRIPTIONS_archives_required")
    try:
        _require(type(retrieved_at) is str and retrieved_at.endswith("Z")
                 and format_utc_timestamp(parse_utc_timestamp(retrieved_at, "consideration retrieval")) == retrieved_at,
                 "canonical_retrieval_clock")
    except (TypeError, ValueError) as exc:
        raise SharadarTerminalConsiderationError("REFUSED: canonical_retrieval_clock") from exc
    dictionary_source, dictionary, by_code = _dictionary(descriptions)
    stream = _rows(actions)
    action_source, events, total = next(stream), [], 0
    for item in stream:
        total += 1
        raw = item["raw"]
        peers = by_code.get(raw["action"].strip(), [])
        if not (_TERMINAL.search(raw["action"]) or any(_TERMINAL.search(peer["raw"]["description"]) for peer in peers)):
            continue
        reasons = []
        if action_source["schema_refusal"]:
            reasons.append(action_source["schema_refusal"])
        try:
            row = master._normalize("actions", raw)
            if row["date"] > retrieved_at[:10]:
                reasons.append("future_action_not_completed_consideration")
        except master.SharadarSecuritiesMasterError:
            row = None
            reasons.append("malformed_terminal_action_row")
        meaning = None
        if len(peers) != 1:
            reasons.append("missing_or_ambiguous_ACTIONTYPES_dictionary")
        elif row is not None:
            meaning, reason = _meaning(row["action"], peers[0])
            if reason:
                reasons.append(reason)
        numeric = None if row is None else row["value"]
        if numeric is None:
            reasons.append("missing_cash_or_ratio_not_zero")
        elif numeric["numerator"] <= 0:
            reasons.append("consideration_not_positive")
        event = {"origin": item["origin"], "raw_cells": item["raw_cells"], "raw": raw,
                 "normalized": row, "dictionary_origins": [peer["origin"] for peer in peers],
                 "consideration_source_evidence": None,
                 "field_refusal_reasons": reasons,
                 "payment_refusal_reasons": ["source_action_date_not_authenticated_holder_payment",
                                              "historical_target_and_received_share_class_binding_unqualified"],
                 "payment_date": None, "payment_timestamp": None,
                 "terminal_economics_admitted": False}
        if not reasons and meaning is not None:
            event["consideration_source_evidence"] = {**meaning, "per_target_unit": numeric,
                "source_action_date": row["date"], "received_security_source_key": row["contraticker"] or None,
                "dictionary_description_sha256": hash_bytes(peers[0]["raw"]["description"].encode("utf-8")),
                "actual_shareholder_payment_verified": False}
        events.append(event)
    action_source["input_row_count"] = total
    keys = [tuple(event["raw"][field].strip() for field in
                  ("date", "action", "ticker", "name", "contraticker", "contraname")) for event in events]
    counts = Counter(keys)
    groups = {}
    for event, key in zip(events, keys):
        if counts[key] > 1:
            event["consideration_source_evidence"] = None
            event["field_refusal_reasons"].append("duplicate_terminal_primary_key_all_peers_refused")
        groups.setdefault((event["raw"]["ticker"].strip(), event["raw"]["date"].strip()), []).append(event)
    packages = []
    for (ticker, day), group in groups.items():
        codes = [event["raw"]["action"].strip().lower() for event in group]
        components = [event for event in group if event["consideration_source_evidence"] is not None]
        cash = [event for event in components if event["consideration_source_evidence"]["kind"] == "cash"]
        stock = [event for event in components if event["consideration_source_evidence"]["kind"] == "received_stock"]
        if any("elect" in code or "alternative" in code or "cohort" in code or "cvr" in code for code in codes):
            reason = "election_cohort_or_CVR_routes_not_additive"
        elif len(cash) != 1 or len(stock) != 1:
            reason = "no_unique_cash_plus_stock_package"
        elif any(event["field_refusal_reasons"] and event["raw"]["action"].strip().lower().startswith("acquisition")
                 and event["raw"]["action"].strip().lower() != "acquisitionby" for event in group):
            reason = "ambiguous_acquisition_peer_package_unqualified"
        elif cash[0]["raw"]["contraticker"] != stock[0]["raw"]["contraticker"] or not stock[0]["raw"]["contraticker"]:
            reason = "receiving_security_relation_unverified"
        else:
            reason = None
        packages.append({"target_source_key": ticker, "source_action_date": day,
                         "event_origins": [event["origin"] for event in group],
                         "additive_cash_and_stock_field_candidates": reason is None,
                         "package_refusal_reason": reason, "payment_date": None,
                         "economic_package_admitted": False})
    source_identity = hash_payload([action_source, dictionary_source])
    payload = {"schema": SCHEMA, "protocol_sha256": PROTOCOL_SHA256,
               "retrieved_at": retrieved_at, "source_identity_sha256": source_identity,
               "sources": [action_source, dictionary_source], "dictionary_entries": dictionary,
               "terminal_events": events, "packages": packages,
               "all_selected_rows_retained": True, "authority": _authority()}
    payload["report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SharadarTerminalConsideration:
    _report_bytes: bytes = dataclasses.field(repr=False)
    _report_sha256: str = dataclasses.field(repr=False)
    _source_identity: str = dataclasses.field(repr=False)
    _seal: object = dataclasses.field(repr=False)
    _seal_anchor: object = dataclasses.field(repr=False)

    def __init__(self, *, _token=None, payload=None):
        _require(_token is _SEAL, "factory_required")
        object.__setattr__(self, "_report_bytes", canonical_json(payload).encode("utf-8"))
        object.__setattr__(self, "_report_sha256", payload["report_sha256"])
        object.__setattr__(self, "_source_identity", payload["source_identity_sha256"])
        seal = (self._report_bytes, self._report_sha256, self._source_identity)
        object.__setattr__(self, "_seal", seal)
        object.__setattr__(self, "_seal_anchor", seal)

    def to_payload(self):
        _require(type(self) is SharadarTerminalConsideration and type(self._seal) is tuple
                 and self._seal_anchor is self._seal and len(self._seal) == 3
                 and self._report_bytes is self._seal[0]
                 and self._report_sha256 is self._seal[1]
                 and self._source_identity is self._seal[2]
                 and type(self._report_bytes) is bytes and type(self._report_sha256) is str
                 and type(self._source_identity) is str, "sealed_consideration_changed")
        try:
            payload = json.loads(self._report_bytes)
            digest = payload.pop("report_sha256")
            _require(digest == self._report_sha256 and hash_payload(payload) == digest
                     and payload["source_identity_sha256"] == self._source_identity
                     and payload["protocol_sha256"] == PROTOCOL_SHA256
                     and canonical_json(payload["authority"]) == canonical_json(_authority()), "sealed_consideration_changed")
            payload["report_sha256"] = digest
            _require(canonical_json(payload).encode("utf-8") == self._report_bytes, "sealed_consideration_changed")
            return payload
        except (KeyError, TypeError, ValueError):
            raise SharadarTerminalConsiderationError("REFUSED: sealed_consideration_changed") from None

    def to_bytes(self):
        SharadarTerminalConsideration.to_payload(self)
        return self._report_bytes

    @property
    def sha256(self):
        return SharadarTerminalConsideration.to_payload(self)["report_sha256"]


def qualify_sharadar_terminal_consideration(actions, descriptions, *, retrieved_at):
    return SharadarTerminalConsideration(_token=_SEAL,
        payload=_build(actions, descriptions, retrieved_at=retrieved_at))
