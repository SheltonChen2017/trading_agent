"""Private exact-composite source bridge, never historical/economic admission.

One current Sharadar TICKERS archive is matched against the sealed dated
Massive pilot. Native permatickers and composite/class FIGIs remain distinct;
the observed query-date relation supplies neither effective intervals nor
historical availability. No raw ticker alias or weighted share transfer exists.
"""
from __future__ import annotations

from collections import defaultdict
import dataclasses
import json
import re
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.massive_class_denominator as classes
import research.short_interest_etf.sharadar_securities_master as master


_FIGI = re.compile(r"BBG[0-9A-Z]{9}\Z")
_NATIVE = re.compile(r"[1-9][0-9]*\Z")


class SharadarClassReferenceError(ValueError):
    """Safe local codes; private source rows never appear in exceptions."""


def _refuse(reason):
    return SharadarClassReferenceError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised_only": True,
            "source_admitted": False, "point_in_time_data": False,
            "historical_identity_admitted": False, "historical_availability_verified": False,
            "same_class_denominator_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def _policy():
    return {"schema": "si-sharadar-class-reference-protocol-v1",
            "master_protocol_sha256": master.PROTOCOL_SHA256,
            "class_protocol_sha256": classes.PROTOCOL_SHA256,
            "master_table": "tickers", "STOCKS_tables": ["stocks", "SEP"],
            "join": "exact_source_composite_FIGI_to_separate_reported_class_FIGI",
            "collision_axes": ["native_permaticker", "composite_FIGI"],
            "collision_rule": "refusal_only_group_ID_trim_native_zero_strip_includes_malformed_never_positive_alias",
            "class_conflict_rule": "one_composite_to_class_and_one_class_to_native_across_all_pilot_responses",
            "count_rule": "all_identifiable_class_date_peers_present_agree_same_class_integer_no_issuer_transfer",
            "temporal_rule": "query_date_source_relation_not_effective_interval_or_public_availability",
            "retention_rule": "all_master_row_origins_and_all_thirty_class_responses_private",
            "provider_requests": 0, "credential_reads": 0,
            "publication_scope": "private_source_only_not_provider_fitness_publication",
            "authority": _authority()}


# Pin the exact fixed bridge policy, independent of a particular private file.
PROTOCOL_SHA256 = "d346c77c7267548b50c60e28c5cbe81bab08b69e22fc36929cae12014ed243c0"


def class_reference_protocol():
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_class_reference_policy_changed")
    return payload


def _figi(value):
    return value if type(value) is str and _FIGI.fullmatch(value) else None


def _collision_figi(value):
    """Refusal identity only: never use a repaired token for a positive join."""
    return _figi(value.strip()) if type(value) is str else None


def _collision_native(value):
    if type(value) is str and re.fullmatch(r"[0-9]+", value.strip()):
        return value.strip().lstrip("0") or "0"
    return None


def _identity(archive, class_bytes):
    if type(archive) is not master.CapturedSharadarMasterArchive or getattr(archive, "table", None) != "tickers":
        raise _refuse("exact_TICKERS_archive_required")
    if (type(archive.raw) is not bytes or type(archive.request_sha256) is not str
            or archive.request_sha256 != master.request_sha256("download-tickers")):
        raise _refuse("retained_TICKERS_archive_changed")
    if type(class_bytes) is not bytes:
        raise _refuse("immutable_class_report_bytes_required")
    return hash_payload({"archive_sha256": hash_bytes(archive.raw),
                         "request_sha256": archive.request_sha256,
                         "class_report_file_sha256": hash_bytes(class_bytes)})


def _source_identifiers(capture, *, refusal_only=False):
    """Malformed identifiable peers still participate in collision detection."""
    if not capture.body_observed or capture.http_status != 200 or not capture.raw:
        return None, None
    try:
        payload = classes._json(capture.raw)
    except classes.MassiveClassDenominatorError:
        return None, None
    row = payload.get("results") if type(payload) is dict else None
    if type(row) is not dict:
        return None, None
    identify = _collision_figi if refusal_only else _figi
    return identify(row.get("composite_figi")), identify(row.get("share_class_figi"))


def _build(archive, class_report, retrieved_at):
    class_reference_protocol()
    if type(class_report) is not classes.MassiveClassDenominatorQualification:
        raise _refuse("exact_sealed_class_qualification_required")
    class_bytes = class_report.to_bytes()
    source = class_report.to_payload()
    try:
        if parse_utc_timestamp(retrieved_at, "retrieved_at") < parse_utc_timestamp(source["retrieved_at"], "class_retrieved_at"):
            raise ValueError
    except (TypeError, ValueError):
        raise _refuse("class_reference_chronology") from None
    _identity(archive, class_bytes)
    parsed = master._parsed(archive)  # exactly one TICKERS parse; no ACTIONS report
    native_axis, composite_axis = defaultdict(list), defaultdict(list)
    source_master = []
    for row in parsed["rows"]:
        raw = master._raw_row(parsed, row)
        index = row["origin"]["row_index"]
        if raw["table"].strip() in {"stocks", "SEP"}:
            native_key = _collision_native(raw.get("permaticker"))
            composite_key = _collision_figi(raw.get("figi"))
            if native_key is not None:
                native_axis[native_key].append(index)
            if composite_key is not None:
                composite_axis[composite_key].append(index)
        source_master.append({"origin": row["origin"], "raw_cells": row["raw_cells"],
                              "normalized": row["normalized"], "parser_status": row["status"],
                              "parser_refusal_reason": row["refusal_reason"]})
    composite_classes, class_natives = defaultdict(set), defaultdict(set)
    identifier_peers = []
    for capture, response in zip(class_report._captures, source["responses"]):
        composite, class_figi = _source_identifiers(capture, refusal_only=True)
        identifier_peers.append((composite, class_figi))
        if composite is not None and class_figi is not None:
            composite_classes[composite].add(class_figi)
            for index in composite_axis.get(composite, ()):
                raw = master._raw_row(parsed, parsed["rows"][index])
                class_natives[class_figi].add(_collision_native(raw.get("permaticker")))
    counts_by_class_date, blocked_count_keys = defaultdict(set), set()
    for response, (_, raw_class) in zip(source["responses"], identifier_peers):
        query_date = classes.massive_request(response["request_id"])["params"]["date"]
        if raw_class is not None and response["status"] != "present":
            blocked_count_keys.add((raw_class, query_date))
        normalized = response.get("normalized")
        if response["status"] == "present" and normalized is not None:
            count = normalized.get("share_class_shares_outstanding")
            if count is not None:
                counts_by_class_date[(normalized["share_class_figi"], normalized["query_date"])].add(count["numerator"])
    relations = []
    for response, capture, collision_ids in zip(source["responses"], class_report._captures, identifier_peers):
        raw_composite, raw_class = _source_identifiers(capture)
        normalized = response.get("normalized")
        record = {"request_id": response["request_id"], "response_status": response["status"],
                  "response_origin": {field: response[field] for field in (
                      "request_sha256", "source_file_sha256", "received_at", "http_status", "body_observed")},
                  "query_date": classes.massive_request(response["request_id"])["params"]["date"],
                  "source_composite_figi": raw_composite, "source_share_class_figi": raw_class,
                  "refusal_collision_identifiers": {"composite_figi": collision_ids[0],
                                                    "share_class_figi": collision_ids[1]},
                  "provider_security_id": None, "master_origin": None,
                  "status": "unresolved", "reason": None,
                  "denominator_source_evidence": None,
                  "historical_effective_intervals": [], "source_relation_only": True,
                  "authority": _authority()}
        reason = None
        if response["status"] not in {"present", "incomplete"} or normalized is None:
            reason = "class_response_refused_missing_or_ambiguous"
        elif raw_composite is None or raw_class is None or raw_composite == raw_class:
            reason = "separate_composite_and_class_assertions_required"
        elif len(composite_classes[raw_composite]) != 1:
            reason = "conflicting_composite_to_class_assertions"
        elif len(class_natives[raw_class]) != 1:
            reason = "class_to_native_missing_or_ambiguous"
        elif len(composite_axis.get(raw_composite, ())) != 1:
            reason = "composite_master_owner_missing_or_ambiguous"
        else:
            position = composite_axis[raw_composite][0]
            row = parsed["rows"][position]
            raw = master._raw_row(parsed, row)
            native = raw.get("permaticker")
            if row["normalized"] is None or len(native_axis.get(native, ())) != 1 or not _NATIVE.fullmatch(native):
                reason = "native_master_owner_malformed_or_ambiguous"
            elif row["normalized"]["current_common_stock_candidate"] is not True:
                reason = "not_current_common_stock_source_candidate"
            else:
                record.update(provider_security_id="sharadar:permaticker:" + native,
                              master_origin=row["origin"], status="query_date_source_relation_candidate")
                # A partial reference may support a relation but not a count.
                if response["status"] == "present":
                    count = normalized.get("share_class_shares_outstanding")
                    count_key = (raw_class, normalized["query_date"])
                    if count is not None and count_key not in blocked_count_keys and len(counts_by_class_date[count_key]) == 1:
                        record["denominator_source_evidence"] = {
                            **count, "share_class_figi": raw_class,
                            "source_request_id": response["request_id"],
                            "query_date": normalized["query_date"],
                            "evidence_only_not_denominator_admission": True}
                    else:
                        record["denominator_refusal"] = "same_class_date_count_missing_or_conflicting"
                else:
                    record["denominator_refusal"] = "incomplete_reference_not_count_qualification"
        record["reason"] = reason
        relations.append(record)
    payload = {"schema": "si-sharadar-class-reference-v1",
               "protocol_sha256": PROTOCOL_SHA256, "retrieved_at": retrieved_at,
               "master_archive_sha256": parsed["archive_sha256"],
               "master_CSV_sha256": parsed["CSV_sha256"],
               "master_headers": parsed["headers"], "master_normalized_headers": parsed["normalized_headers"],
               "master_schema_refusals": parsed["schema_refusals"],
               "master_rows": source_master, "all_master_rows_retained": True,
               "class_report_sha256": class_report.sha256,
               "class_report_file_sha256": hash_bytes(class_bytes),
               "class_responses": source["responses"], "relations": relations,
               "public_known_gaps": ["current_composite_assertion_not_historical_native_class_effective_interval",
                                     "dated_class_count_not_original_filing_or_availability",
                                     "pilot_not_full_study_population_or_terminal_coverage",
                                     "prospective_look_and_exact_QC_processing_not_qualified"],
               "authority": _authority()}
    digest = hash_payload(payload)
    payload["report_sha256"] = digest
    return canonical_json(payload).encode(), digest, class_bytes


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SharadarClassReference:
    _archive: master.CapturedSharadarMasterArchive = dataclasses.field(repr=False)
    _class_bytes: bytes = dataclasses.field(repr=False)
    _source_identity: str = dataclasses.field(repr=False)
    _report_bytes: bytes = dataclasses.field(repr=False)
    _report_sha256: str
    _seal: str = dataclasses.field(repr=False)

    def __init__(self):
        raise _refuse("class_reference_requires_bound_factory")

    def to_bytes(self):
        if type(self) is not SharadarClassReference:
            raise _refuse("exact_class_reference_required")
        class_reference_protocol()
        try:
            identity = _identity(self._archive, self._class_bytes)
            if (identity != self._source_identity or type(self._report_bytes) is not bytes
                    or hash_payload({"source_identity": identity, "report_bytes_sha256": hash_bytes(self._report_bytes),
                                     "report_sha256": self._report_sha256}) != self._seal):
                raise _refuse("sealed_class_reference_changed")
        except AttributeError:
            raise _refuse("uninitialized_class_reference") from None
        return self._report_bytes

    def to_payload(self):
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        self.to_bytes()
        return self._report_sha256


def qualify_sharadar_class_reference(tickers, class_report, *, retrieved_at):
    raw, digest, class_bytes = _build(tickers, class_report, retrieved_at)
    snapshot = master.CapturedSharadarMasterArchive(tickers.table, tickers.raw, tickers.request_sha256)
    identity = _identity(snapshot, class_bytes)
    value = object.__new__(SharadarClassReference)
    for name, item in (("_archive", snapshot), ("_class_bytes", class_bytes),
                       ("_source_identity", identity), ("_report_bytes", raw),
                       ("_report_sha256", digest), ("_seal", hash_payload({"source_identity": identity,
                           "report_bytes_sha256": hash_bytes(raw), "report_sha256": digest}))):
        object.__setattr__(value, name, item)
    value.to_bytes()
    return value
