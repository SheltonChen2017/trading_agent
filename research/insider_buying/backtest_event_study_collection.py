"""Pure pre-outcome composition of genuinely sealed adjacent causal windows.

This successor removes the single source-window study-size restriction. It
does not acquire history, publish an 82-quarter corpus, authenticate a source,
register/spend a look, or grant outcome/QC access. The immutable application
inventory binds every supplied child, source receipt and preregistration.
Repeated complete-quarter source populations must agree byte-for-byte and are
counted once; economic lots and original members cannot be traded twice.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import json

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying.backtest_source_stream import StreamSourceEvidence, validate_stream_source_evidence


VERSION = "insider-source-causal-firstopen-collection-v1"
INVENTORY_SCHEMA = "insider-causal-study-collection-inventory-v1"
VERSION_V2 = "insider-source-causal-firstopen-collection-v2"
INVENTORY_SCHEMA_V2 = "insider-causal-study-collection-inventory-v2"
MAX_CHILDREN = 1_250
MAX_INVENTORY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_CHILD_BYTES = 128 * 1024 * 1024 * 1024
MAX_COLLECTION_BYTES = 256 * 1024 * 1024
MAX_UNIQUE_SOURCE_ROWS = 5_000_000


class EventStudyCollectionError(ValueError):
    """An immutable child collection, continuity or common epoch refused."""


def _need(ok, reason):
    if not ok:
        raise EventStudyCollectionError("REFUSED: " + reason)


@dataclass(frozen=True, slots=True)
class EventStudyCollectionTrustRoots:
    trust_scope: str
    collection_inventory_sha256: str
    parent_registration_sha256: str
    analysis_implementation_sha256: str

    def __post_init__(self):
        _need(type(self) is EventStudyCollectionTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "exact collection trust roots required")
        for value in (self.collection_inventory_sha256, self.parent_registration_sha256,
                      self.analysis_implementation_sha256):
            analysis._digest(value)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CausalStudyChildRecord:
    event_manifest: causal.SourceEventStudyManifest
    source_evidence: StreamSourceEvidence
    registration_raw: bytes = field(repr=False)

    def __post_init__(self):
        _need(type(self) is CausalStudyChildRecord
              and type(self.event_manifest) is causal.SourceEventStudyManifest
              and type(self.source_evidence) is StreamSourceEvidence
              and type(self.registration_raw) is bytes
              and 0 < len(self.registration_raw) <= analysis.MAX_BYTES,
              "exact sealed causal/source child and bounded registration required")


def _child(record, *, v2=False):
    _need(type(record) is CausalStudyChildRecord, "non-child record in immutable collection")
    record.__post_init__()
    metadata = causal.validate_source_event_study_manifest(record.event_manifest)
    source = validate_stream_source_evidence(record.source_evidence)
    kinds = {causal.VERSION_V2, causal.ZERO_WINDOW_VERSION_V2} if v2 else {causal.VERSION, causal.ZERO_WINDOW_VERSION}
    _need(metadata["kind"] in kinds
          and metadata["source_stream_sha256"] == record.source_evidence.sha256
          and metadata["source_population_sha256"] == source["population_manifest_sha256"]
          and metadata["trust_scope"] == source["trust_scope"]
          and source["relevant_form4_identity_complete"], "child source receipt/epoch differs or is incomplete")
    manifest_raw = record.event_manifest.manifest_bytes()
    registration = analysis._decode(record.registration_raw, metadata["registration_sha256"])
    manifest = json.loads(manifest_raw)
    if metadata["event_count"]:
        validator = analysis.verify_registered_analysis_manifest_v2 if v2 else analysis.verify_registered_analysis_manifest
        checked = validator(registration_raw=record.registration_raw,
            manifest_raw=manifest_raw, expected_registration_sha256=metadata["registration_sha256"],
            expected_manifest_sha256=metadata["manifest_sha256"],
            expected_implementation_sha256=metadata["analysis_implementation_sha256"])
        registration, manifest = checked["registration"], checked["manifest"]
    else:
        _need(metadata["kind"] == (causal.ZERO_WINDOW_VERSION_V2 if v2 else causal.ZERO_WINDOW_VERSION) and metadata["zero_event_window_complete"]
              and manifest["events"] == [] and metadata["standalone_analysis_population_nonempty"] is False,
              "zero-event window is not genuine complete source/reference coverage")
    quarters = record.source_evidence.quarter_receipts()
    descriptor = {"event_study_sha256": record.event_manifest.sha256,
        "event_manifest_sha256": metadata["manifest_sha256"], "source_stream_sha256": record.source_evidence.sha256,
        "source_population_sha256": metadata["source_population_sha256"],
        "registration_sha256": metadata["registration_sha256"], "entry_reference_sha256": metadata["entry_reference_sha256"],
        "security_master_sha256": metadata["security_master_sha256"], "calendar_sha256": metadata["calendar_sha256"],
        "common_equity_exceptions_sha256": metadata["common_equity_exceptions_sha256"],
        "analysis_implementation_sha256": metadata["analysis_implementation_sha256"],
        "event_population_policy": metadata["event_population_policy"], "source_evidence_epoch": source["evidence_epoch"],
        "source_profile": source["kind"], "causal_profile": metadata["kind"],
        "event_first_session": metadata["event_first_session"], "event_last_session": metadata["event_last_session"],
        "event_count": metadata["event_count"], "quarter_receipts_sha256": hash_payload(quarters)}
    return descriptor, metadata, source, quarters, registration, manifest


def describe_causal_child(record: CausalStudyChildRecord) -> dict:
    """Derive inventory facts, not authenticate or establish an external root."""
    return _child(record)[0]


def describe_causal_child_v2(record: CausalStudyChildRecord) -> dict:
    """New homogeneous no-earnings causal epoch; old children refuse."""
    return _child(record, v2=True)[0]


def collection_provenance(value: causal.SourceEventStudyManifest) -> dict:
    """Detached original child receipts and deduplicated quarter accounting."""
    metadata = causal.validate_source_event_study_manifest(value)
    _need(metadata["kind"] == VERSION, "exact composed causal collection required")
    body = value._body()
    return {"child_receipts": body["child_receipts"],
            "unique_source_quarter_receipts": body["unique_source_quarter_receipts"]}


def collection_provenance_v2(value: causal.SourceEventStudyManifest) -> dict:
    metadata = causal.validate_source_event_study_manifest(value)
    _need(metadata["kind"] == VERSION_V2, "exact composed causal collection-v2 required")
    body = value._body()
    return {"child_receipts": body["child_receipts"],
            "unique_source_quarter_receipts": body["unique_source_quarter_receipts"]}


def _epoch(registration):
    # Source inventory and registration timestamps deliberately differ across
    # windows. Every other study/look/method/vintage/rights field is immutable.
    return {key: value for key, value in registration.items()
            if key not in {"source_manifest_sha256", "registered_at_utc"}}


def _build_source_event_study_collection(*, child_records: Iterator[CausalStudyChildRecord],
        collection_inventory: bytes, parent_registration: bytes,
        trust_roots: EventStudyCollectionTrustRoots, v2=False) -> causal.SourceEventStudyManifest:
    """Compose exactly one complete, nonempty parent without touching outcomes."""
    _need(type(trust_roots) is EventStudyCollectionTrustRoots, "exact external collection roots required")
    trust_roots.__post_init__()
    _need(type(collection_inventory) is bytes and 0 < len(collection_inventory) <= MAX_INVENTORY_BYTES,
          "immutable collection inventory absent or exceeds its bound")
    inventory = analysis._decode(collection_inventory, trust_roots.collection_inventory_sha256)
    analysis._fields(inventory, {"schema", "trust_scope", "origin", "event_first_session", "event_last_session", "children"},
                     "causal child collection inventory")
    _need(inventory["schema"] == (INVENTORY_SCHEMA_V2 if v2 else INVENTORY_SCHEMA) and inventory["trust_scope"] == trust_roots.trust_scope
          and inventory["origin"] == {"fixture": "invented-sealed-causal-window-collection",
              "production": "externally-anchored-sealed-causal-window-collection"}[trust_roots.trust_scope],
          "collection source/reference profile or scope differs")
    descriptors = inventory["children"]
    _need(type(descriptors) is list and 2 <= len(descriptors) <= MAX_CHILDREN
          and isinstance(child_records, Iterator) and iter(child_records) is child_records,
          "bounded complete child inventory and one-pass iterator required")
    parent = analysis._decode(parent_registration, trust_roots.parent_registration_sha256)
    analysis._fields(parent, {"schema", "trust_scope", "registered_look_id", "candidate_id", "policy", "analysis_plan",
        "registered_at_utc", "first_outcome_access_utc", "implementation_sha256", "source_manifest_sha256",
        "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256", "rights_sha256",
        "prior_variance_calibration_sha256"} | ({"realized_earnings_implementation_sha256"} if v2 else set()), "parent preregistration")
    _need(parent["source_manifest_sha256"] == trust_roots.collection_inventory_sha256
          and parent["trust_scope"] == trust_roots.trust_scope
          and parent["implementation_sha256"] == trust_roots.analysis_implementation_sha256
          and analysis._utc(parent["registered_at_utc"]) < analysis._utc(parent["first_outcome_access_utc"]),
          "parent inventory, implementation, trust scope or pre-outcome epoch differs")
    common, calendar, date_index, previous_last = None, None, None, None
    receipts, quarter_hashes, quarter_accessions, child_receipts = {}, {}, set(), []
    events, lineages, reference_facts, per_date_controls = [], [], {}, {}
    event_ids, issuer_days, economic_lots, member_ids = set(), set(), set(), set()
    total_bytes = duplicate_quarters = zero_windows = 0
    source_window_start = source_window_end = None
    counts = {"source_submission_count": 0, "stream_corroborated_form4_count": 0,
              "preceding_corroborated_count": 0, "preceding_quarantined_count": 0}
    form_counts, quarantine_counts = {}, {}
    for number, supplied_descriptor in enumerate(descriptors, 1):
        try:
            record = next(child_records)
        except StopIteration as exc:
            raise EventStudyCollectionError("REFUSED: declared causal child is missing") from exc
        descriptor, metadata, source, quarters, registration, manifest = _child(record, v2=v2)
        _need(supplied_descriptor == descriptor and type(supplied_descriptor) is dict
              and canonical_json(supplied_descriptor) == canonical_json(descriptor),
              "immutable child inventory is reordered, altered or incomplete")
        total_bytes += len(record.event_manifest._bytes) + len(record.source_evidence._bytes) + len(record.registration_raw)
        _need(total_bytes <= MAX_TOTAL_CHILD_BYTES, "aggregate supplied child evidence exceeds its finite bound")
        _need(metadata["trust_scope"] == trust_roots.trust_scope
              and metadata["analysis_implementation_sha256"] == trust_roots.analysis_implementation_sha256
              and analysis.canonical_bytes(_epoch(registration)) == analysis.canonical_bytes(_epoch(parent))
              and analysis._utc(registration["registered_at_utc"]) <= analysis._utc(parent["registered_at_utc"]),
              "child changed fixed parent look/epoch or was registered after parent collection")
        common_fields = {key: metadata[key] for key in ("trust_scope", "security_master_sha256", "calendar_sha256",
            "common_equity_exceptions_sha256", "analysis_implementation_sha256", "event_population_policy")}
        common_fields.update(child_source_evidence_epoch=source["evidence_epoch"], child_source_profile=source["kind"])
        _need(metadata["event_population_policy"] == causal.EVENT_POPULATION_POLICY, "causal population policy differs")
        if common is None:
            common = common_fields
            calendar = manifest["sessions"]
            date_index = {row["session"]: index for index, row in enumerate(calendar)}
        _need(common_fields == common and manifest["sessions"] == calendar, "common calendar/master/classification/method roots differ")
        first, last = metadata["event_first_session"], metadata["event_last_session"]
        _need(first in date_index and last in date_index and date_index[first] <= date_index[last], "child event window absent/reversed")
        _need((number == 1 and first == inventory["event_first_session"])
              or (previous_last is not None and date_index[first] == date_index[previous_last] + 1),
              "child windows have a gap, overlap, duplicate or reordered session")
        previous_last = last
        source_window_start = min(source_window_start or metadata["source_window_start"], metadata["source_window_start"])
        source_window_end = max(source_window_end or metadata["source_window_end"], metadata["source_window_end"])
        _need(number != len(descriptors) or last == inventory["event_last_session"], "final child does not cover declared last session")
        for receipt in quarters:
            period = receipt["period"]
            digest = hash_payload(receipt)
            if period in receipts:
                _need(quarter_hashes[period] == digest, "repeated quarter source/coverage/raw inventory conflicts")
                duplicate_quarters += 1
                continue
            accessions = receipt["accession_numbers"]
            _need(type(accessions) is list and len(accessions) == receipt["source_submission_count"]
                  and hash_payload(accessions) == receipt["accession_numbers_sha256"]
                  and len(set(accessions)) == len(accessions) and not (set(accessions) & quarter_accessions),
                  "cross-quarter source accession is duplicate or accounting differs")
            quarter_accessions.update(accessions)
            _need(len(quarter_accessions) <= MAX_UNIQUE_SOURCE_ROWS, "unique source census exceeds finite bound")
            compact = {key: value for key, value in receipt.items() if key != "accession_numbers"}
            receipts[period], quarter_hashes[period] = compact, digest
            for key in counts:
                counts[key] += receipt["observed_parent_count"] if key == "stream_corroborated_form4_count" else receipt[key]
            for key, value in receipt["source_form_counts"].items():
                form_counts[key] = form_counts.get(key, 0) + value
            for key, value in receipt["preceding_quarantine_reason_counts"].items():
                quarantine_counts[key] = quarantine_counts.get(key, 0) + value
        child_events = manifest["events"]
        _need(len(child_events) == metadata["event_count"], "child observed event count differs")
        child_lineages = record.event_manifest.event_lineage()
        _need(len(child_lineages) == len(child_events), "child source event lineage incomplete")
        for event, lineage in zip(child_events, child_lineages, strict=True):
            key = event["issuer_id"], event["entry_session"]
            _need(first <= event["entry_session"] <= last and event["signal_id"] not in event_ids
                  and key not in issuer_days and lineage["signal_id"] == event["signal_id"]
                  and lineage["source_event_sha256"] == event["source_event_sha256"],
                  "event outside window or duplicate event/issuer-day/lineage")
            for lot in lineage["payload"]["lots"]:
                lot_key = lot["owner_cik"], lot["qc_symbol_id"], lot["transaction_date"]
                _need(lot_key not in economic_lots and not (set(lot["member_event_ids"]) & member_ids),
                      "economic lot or original member would be counted/traded twice")
                economic_lots.add(lot_key)
                member_ids.update(lot["member_event_ids"])
            event_ids.add(event["signal_id"]); issuer_days.add(key)
            events.append(event); lineages.append({**lineage, "child_ordinal": number,
                "child_event_study_sha256": descriptor["event_study_sha256"]})
        _need(len(events) <= analysis.MAX_EVENTS, "composed event population exceeds finite bound")
        for fact in record.event_manifest.entry_reference_facts():
            day = fact["entry_session"]
            _need(first <= day <= last and day not in reference_facts, "entry prerequisite belongs to wrong/duplicate window")
            reference_facts[day] = fact
        for day, ids in manifest["eligible_control_security_ids_by_entry_session"].items():
            _need(day not in per_date_controls, "PIT control date repeated across child windows")
            per_date_controls[day] = ids
        zero_windows += metadata["event_count"] == 0
        child_receipts.append({"ordinal": number, **descriptor, "registration_epoch_sha256": hash_payload(_epoch(registration)),
            "source_submission_count": metadata["source_submission_count"],
            "child_excluded_reason_counts": metadata["excluded_reason_counts"],
            "zero_event_window_complete": metadata["zero_event_window_complete"],
            "original_causal_receipt": metadata,
            "original_source_receipt_sha256": hash_payload(source),
            "original_source_receipt_counts": {key: value for key, value in source.items()
                if key.endswith("count") or key.endswith("counts")},
            "original_receipt_counts_are_per_child_not_unique_population": True})
        del record, metadata, source, quarters, registration, manifest, child_events, child_lineages
    try:
        next(child_records)
    except StopIteration:
        pass
    else:
        raise EventStudyCollectionError("REFUSED: undeclared extra child in source collection")
    _need(events, "complete collection has no nonempty analysis population")
    events.sort(key=lambda row: (row["entry_session"], row["issuer_id"], row["signal_id"]))
    lineage_by_id = {row["signal_id"]: row for row in lineages}
    lineages = [lineage_by_id[event["signal_id"]] for event in events]
    controls_union = sorted(set().union(*(set(ids) for ids in per_date_controls.values())))
    parent_manifest = {"schema": "insider-stock-event-study-manifest-v3" if v2 else "insider-stock-event-study-manifest-v2", "trust_scope": trust_roots.trust_scope,
        "registration_sha256": trust_roots.parent_registration_sha256,
        "source_manifest_sha256": trust_roots.collection_inventory_sha256,
        "security_master_sha256": parent["security_master_sha256"], "calendar_sha256": parent["calendar_sha256"],
        "outcome_vintage_sha256": parent["outcome_vintage_sha256"], "sessions": calendar,
        "eligible_control_security_ids": controls_union,
        "eligible_control_security_ids_by_entry_session": dict(sorted(per_date_controls.items())), "events": events}
    parent_raw = analysis.canonical_bytes(parent_manifest)
    validator = analysis.verify_registered_analysis_manifest_v2 if v2 else analysis.verify_registered_analysis_manifest
    validator(registration_raw=parent_registration, manifest_raw=parent_raw,
        expected_registration_sha256=trust_roots.parent_registration_sha256, expected_manifest_sha256=hash_bytes(parent_raw),
        expected_implementation_sha256=trust_roots.analysis_implementation_sha256)
    summary = {"kind": VERSION_V2 if v2 else VERSION, **common, "source_population_sha256": trust_roots.collection_inventory_sha256,
        "collection_inventory_sha256": trust_roots.collection_inventory_sha256,
        "entry_reference_sha256": trust_roots.collection_inventory_sha256,
        "entry_reference_profile": "immutable-causal-child-source-and-reference-collection-inventory-v1",
        "registration_sha256": trust_roots.parent_registration_sha256,
        "source_profile": "composed-sealed-adjacent-causal-source-windows-not-new-acquisition-v1",
        "manifest_sha256": hash_bytes(parent_raw), "child_count": len(descriptors), "zero_event_window_count": zero_windows,
        "event_first_session": inventory["event_first_session"], "event_last_session": inventory["event_last_session"],
        "source_window_start": source_window_start, "source_window_end": source_window_end,
        "event_count": len(events), "event_date_count": len(per_date_controls), "economic_lot_count": len(economic_lots),
        "original_member_count": len(member_ids), "unique_source_quarter_count": len(receipts),
        "repeated_source_quarter_receipts_not_recounted": duplicate_quarters,
        **counts, "source_form_counts": dict(sorted(form_counts.items())),
        "preceding_quarantine_reason_counts": dict(sorted(quarantine_counts.items())),
        "raw_child_objects_retained": 0, "raw_parent_images_retained": 0, "aggregate_child_evidence_bytes": total_bytes,
        "literal_first_open_after_acceptance": True, "daily_close_candidate_backdated": False,
        "source_authentication_performed": False, "rights_authenticated_here": False,
        "look_authority": False, "backtesting_ready": False, "qc_jobs": 0, "research_looks": 0,
        "outcome_rows_read": 0, "execution_performed": False, "historical_publication_promoted": False}
    return causal._seal_validated_manifest({"summary": summary, "manifest": parent_manifest, "lineage": lineages,
        "entry_references": [reference_facts[day] for day in sorted(reference_facts)],
        "child_receipts": child_receipts, "unique_source_quarter_receipts": [receipts[p] for p in sorted(receipts)]},
        max_bytes=MAX_COLLECTION_BYTES)


def build_source_event_study_collection(**kwargs) -> causal.SourceEventStudyManifest:
    """Unchanged homogeneous v1 collection epoch; successor children refuse."""
    _need("v2" not in kwargs, "public collection profile override forbidden")
    return _build_source_event_study_collection(**kwargs)


def build_source_event_study_collection_v2(**kwargs) -> causal.SourceEventStudyManifest:
    """Complete adjacent no-earnings causal windows under one fixed look."""
    _need("v2" not in kwargs, "public collection profile override forbidden")
    return _build_source_event_study_collection(**kwargs, v2=True)


__all__ = ["EventStudyCollectionError", "EventStudyCollectionTrustRoots", "CausalStudyChildRecord",
           "describe_causal_child", "describe_causal_child_v2", "collection_provenance", "collection_provenance_v2",
           "build_source_event_study_collection", "build_source_event_study_collection_v2"]
