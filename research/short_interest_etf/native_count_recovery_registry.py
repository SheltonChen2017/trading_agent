"""Offline provenance union for one manual latest-reported count recovery.

The original refused claim never becomes complete. A later observation of its
pre-wire negative is a new source observation, with its own actual clock. This
pure module accepts protected read/custody seams, not paths, HTTP or credentials.
Its distinct sealed type is not an old registry or an actual-input admission.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_class_reference as references
import research.short_interest_etf.native_parallel_count_contract as parallel
import research.short_interest_etf.native_reported_anchor_plan as reported
from research.short_interest_etf.latest_revised_protocol import EPOCH_ID

ORIGINAL_COUNT = 81_875
PARENT_STARTED = 48
FAILED_POSITION = 47
PARENT_HTTP = 47
PARENT_CHARGED_BYTES = 2_159_332
MAXIMUM_CUMULATIVE_BYTES = 4 * 1024 ** 3
ANCHOR_PLAN_SHA256 = "d58b2b3d006319899e6af9cd06a2fef17128c391513ea0ee99c987c483d2af3b"
PARENT_PLAN_SHA256 = "d1c9d08b939022bf5eafa2cdde47f9555fe1bbd04c28e7650fb6bdb4d5a5ee56"
PARENT_MANIFEST_SHA256 = "f6f5baf16c0fac2ffa26f994cf82122bcef9dfa842526530797531bc5c8f55c6"
MAPPING_SHA256 = "f36b28e9e4d0ebc76d2e5d8806e413604b5c52c8e443ff828b69f910ac9f2e9d"
RECOVERY_PROTOCOL_SHA256 = "5876de333c792b63253390bae32d3dfe58e8f760b215859ffb324afed969219b"
SOURCE_EPOCH = "latest-reported-count-recovery-20261024-v1"


class CountRecoveryRegistryRefusal(ValueError):
    """Fixed codes never include source rows, credentials or private paths."""


def require(value, code):
    if not value:
        raise CountRecoveryRegistryRefusal("REFUSED: " + code)


def authority():
    return {"source_only": True, "latest_revised_only": True,
            "source_admitted": False, "denominator_admitted": False,
            "historical_PIT_admitted": False, "actual_input_execution_admitted": False,
            "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "trading_authority": False}


def _driver_authority():
    return {"source_only": True, "original_round_halted": True,
            "original_pre_wire_negative_preserved": True, "source_admitted": False,
            "same_class_denominator_admitted": False, "historical_PIT_admitted": False,
            "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "trading_authority": False}


def _decoded(raw, digest, maximum=65536):
    require(type(raw) is bytes and 0 < len(raw) <= maximum
            and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)
            and hash_bytes(raw) == digest, "closed_control_original_bytes_required")
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, "duplicate_control_key")
            result[name] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                parse_constant=lambda unused: require(False, "nonfinite_control"))
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise CountRecoveryRegistryRefusal("REFUSED: closed_control_JSON_refused") from None


def _control(raw, digest):
    value = _decoded(raw, digest)
    require(type(value) is dict, "control_object_required")
    return value


def _manifest(raw, digest, expected_names):
    # The external manifest is outside the closed capture directory, avoiding
    # self-reference. It is a canonical name/bytes/hash list, not source rows.
    entries = _decoded(raw, digest, 64 * 1024 * 1024)
    require(type(entries) is list and len(entries) == len(expected_names),
            "exact_closed_manifest_size_required")
    result, previous = {}, ""
    for entry in entries:
        require(type(entry) is dict and set(entry) == {"name", "sha256", "bytes"}
                and type(entry["name"]) is str and entry["name"] in expected_names
                and previous < entry["name"]
                and type(entry["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                and type(entry["bytes"]) is int and 0 <= entry["bytes"] <= 64 * 1024 * 1024,
                "closed_manifest_membership_or_entry_refused")
        previous = entry["name"]
        result[entry["name"]] = entry
    require(set(result) == expected_names, "closed_manifest_exact_membership_required")
    return result


def _names(parent, child):
    old = {"protocol.private.json", "started.json", "run.refused.json"}
    new = {"protocol.private.json", "started.json", "child.inventory.private.json",
           "diagnostics.inventory.private.json", "child.completed.json", "round.closed.qualified.json"}
    for inventory, names in ((parent, old), (child, new)):
        for receipt in inventory.iter_receipts():
            prefix = f'query-{receipt["query_ordinal"]:08d}'
            names.update((prefix + ".started.json", prefix + ".received.json"))
            if receipt["body_observed"]:
                names.add(prefix + ".raw")
            elif inventory is child:
                require(receipt["code"] == "HTTP_404_body_unobserved", "only_closed_404_child_negative")
                names.add(prefix + ".diagnostic.private.json")
    return old, new


def _bound_reader(read, manifest, custody):
    def bound(name, maximum):
        custody()
        require(name in manifest and manifest[name]["bytes"] <= maximum, "registered_file_name_or_bound_required")
        raw = read(name, maximum)
        custody()
        require(type(raw) is bytes and len(raw) == manifest[name]["bytes"]
                and hash_bytes(raw) == manifest[name]["sha256"], "original_manifest_file_changed")
        return raw
    return bound


def _same(actual, expected):
    return canonical_json(actual) == canonical_json(expected)


def _plans(source, parent, child, mapping):
    require(type(source) is reported.NativeReportedAnchorPlan
            and type(parent) is parallel.ParallelCountInventory
            and type(child) is parallel.ParallelCountInventory,
            "exact_source_and_typed_inventory_required")
    source._guard(); parent.guard(); child.guard()
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    positions = (FAILED_POSITION, *range(PARENT_STARTED + 1, ORIGINAL_COUNT + 1))
    expected = tuple((position, selected[position - 1]) for position in positions) if (
        type(selected) is list and len(selected) == ORIGINAL_COUNT) else None
    require(source.sha256 == ANCHOR_PLAN_SHA256 and expected is not None
            and type(mapping) is tuple and all(type(row) is tuple and len(row) == 2
                and all(type(number) is int for number in row) for row in mapping)
            and mapping == expected and hash_payload(mapping) == MAPPING_SHA256,
            "fixed_original_position_mapping_required")
    require(parent._plan._queries is source.query_plan
            and parent._plan.sha256 == PARENT_PLAN_SHA256
            and child._plan._queries._matrix is source._matrix,
            "exact_original_and_child_plan_lineage_required")
    spec = child._plan._queries.to_payload()
    require(spec["mode"] == "explicit_anchors" and spec["anchor_dates"] is None
            and spec["selected_query_ordinals"] == [row[1] for row in mapping]
            and spec["source_matrix_sha256"] == source._matrix.sha256
            and spec["format_policy_sha256"] == hash_payload(references.reference_policy()),
            "child_selected_source_plan_changed")
    p, c = parent.to_payload(), child.to_payload()
    require(p["attempts_started"] == PARENT_STARTED and p["http_invocations"] == PARENT_HTTP
            and p["charged_response_bytes"] == PARENT_CHARGED_BYTES and p["halted"] is True
            and p["complete_frozen_request_sequence"] is False
            and parent._plan.to_payload()["maximum_total_response_bytes"] == MAXIMUM_CUMULATIVE_BYTES,
            "original_refused_prefix_or_budget_changed")
    require(c["attempts_started"] == len(mapping) and c["unstarted_tickets"] == 0
            and c["halted"] is False and c["complete_frozen_request_sequence"] is True
            and child._plan.to_payload()["maximum_attempts"] == len(mapping)
            and child._plan.to_payload()["maximum_total_response_bytes"]
                == MAXIMUM_CUMULATIVE_BYTES - PARENT_CHARGED_BYTES
            and p["charged_response_bytes"] + c["charged_response_bytes"] <= MAXIMUM_CUMULATIVE_BYTES
            and parallel.clock(p["completed_at"]) <= parallel.clock(c["started_at"]),
            "child_incomplete_or_cumulative_budget_changed")
    negative = parent.receipt_for_ordinal(FAILED_POSITION)
    require(negative["http_attempted"] is False and negative["http_status"] is None
            and negative["body_observed"] is False
            and negative["code"] == "material_request_refused"
            and all(negative[name] is None for name in
                ("raw_path", "raw_sha256", "raw_bytes", "content_type")),
            "original_pre_wire_negative_must_survive")
    return p, c, negative


def _closure(parent, child, marker, closure):
    c = child.to_payload()
    require(_same(marker, {"schema": "si-manual-count-recovery-child-completed-v1",
            "completed_at": c["completed_at"], "child_inventory_sha256": child.sha256,
            "child_starts": c["attempts_started"],
            "cumulative_starts": PARENT_STARTED + c["attempts_started"],
            "parent_inventory_sha256": parent.sha256,
            "original_position_47_negative_retained": True,
            "child_complete_source_only": True, "original_round_complete": False,
            "provisional_until_postpublication_remote_check": True,
            "authority": _driver_authority()}), "exact_child_marker_required")
    require(_same(closure, {"schema": "si-manual-count-recovery-observed-closure-v1",
            "protocol_sha256": RECOVERY_PROTOCOL_SHA256,
            "audit_started_at": closure.get("audit_started_at"),
            "audit_ended_at": closure.get("audit_ended_at"),
            "matching_remote_observed_equal": True, "child_marker_sha256": hash_payload(marker),
            "child_inventory_sha256": child.sha256, "original_round_complete": False,
            "source_admitted": False, "ready_for_backtest": False,
            "authority": _driver_authority()}), "exact_postpublication_child_closure_required")
    require(parallel.clock(c["completed_at"]) <= parallel.clock(closure["audit_started_at"])
            <= parallel.clock(closure["audit_ended_at"]), "child_closure_chronology_required")


@dataclass(frozen=True, slots=True, init=False)
class CountRecoveryRegistry:
    _source: object = field(repr=False)
    _parent: object = field(repr=False)
    _child: object = field(repr=False)
    _mapping: tuple = field(repr=False)
    _records: tuple = field(repr=False)
    _header: str = field(repr=False)
    _digest: str
    _custody: object = field(repr=False)
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise CountRecoveryRegistryRefusal("REFUSED: recovery_registry_factory_required")

    def _guard(self):
        values = (self._source, self._parent, self._child, self._mapping, self._records,
                  self._header, self._digest, self._custody)
        require(type(self) is CountRecoveryRegistry and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == len(values)
                and all(current is original for current, original in zip(values, self._anchor)),
                "sealed_recovery_registry_changed")
        self._source._guard(); self._parent.guard(); self._child.guard(); self._custody()

    def to_payload(self):
        self._guard()
        return json.loads(self._header)

    @property
    def sha256(self):
        self._guard()
        return self._digest

    @property
    def _plan(self):
        self._guard()
        return self._source

    def iter_records(self):
        self._guard()
        for raw in self._records:
            self._guard()
            yield json.loads(raw)

    def iter_cells(self):
        self._guard()
        for cell in self._source.iter_cells():
            self._guard()
            index = cell["anchor_index"]
            record = None if index < 0 else json.loads(self._records[index])
            reasons = list(cell["refusal_reasons"])
            if not reasons and (record is None or record["refusal_reasons"]):
                reasons.append("planned_anchor_count_missing_or_refused_no_old_count_fallback")
            cell.update(refusal_reasons=reasons,
                same_class_count=None if reasons else record["same_class_count"],
                query_asof_date=None if record is None else record["query_asof_date"],
                actual_receipt_UTC=None if record is None else record["actual_receipt_UTC"],
                historical_available_date=None, effective_intervals=[], authority=authority(),
                recovery_registry_sha256=self._digest, source_epoch=SOURCE_EPOCH)
            yield cell


def qualify_count_recovery(source, parent_inventory, child_inventory, *, original_to_matrix_mapping,
        parent_read, child_read, custody, child_marker_raw, expected_child_marker_sha256,
        child_closure_raw, expected_child_closure_sha256, parent_manifest_raw,
        child_manifest_raw, expected_child_manifest_sha256, child_names):
    """Fully close controls and raw totals before returning any count/cell iterator.

    Reads are fixed local receipt names with a byte ceiling. The operational
    caller must hold original parent/child manifests and protected directory/file
    custody for both seams, including the unchanged closed directory membership
    stamp. child_names observes actual held-directory names before/after complete
    replay; no caller absence boolean is accepted. These proofs grant no admission.
    """
    require(callable(parent_read) and callable(child_read) and callable(custody) and callable(child_names),
            "protected_read_and_custody_seams_required")
    custody()
    p, c, negative = _plans(source, parent_inventory, child_inventory, original_to_matrix_mapping)
    marker = _control(child_marker_raw, expected_child_marker_sha256)
    closure = _control(child_closure_raw, expected_child_closure_sha256)
    _closure(parent_inventory, child_inventory, marker, closure)
    parent_names, expected_child_names = _names(parent_inventory, child_inventory)
    old_manifest = _manifest(parent_manifest_raw, PARENT_MANIFEST_SHA256, parent_names)
    new_manifest = _manifest(child_manifest_raw, expected_child_manifest_sha256, expected_child_names)
    def membership():
        custody()
        observed = child_names()
        require(type(observed) is tuple and observed == tuple(sorted(expected_child_names)),
                "closed_child_directory_membership_changed_or_refused")
        custody()
    membership()
    parent_read = _bound_reader(parent_read, old_manifest, custody)
    child_read = _bound_reader(child_read, new_manifest, custody)
    require(child_read("child.completed.json", 65536) == child_marker_raw
            and child_read("round.closed.qualified.json", 65536) == child_closure_raw,
            "actual_closed_marker_bytes_required")
    protocol_raw = child_read("protocol.private.json", 65536)
    require(hash_bytes(protocol_raw) == RECOVERY_PROTOCOL_SHA256, "frozen_child_protocol_bytes_required")
    inventory_raw = child_read("child.inventory.private.json", 65536)
    require(_same(_control(inventory_raw, new_manifest["child.inventory.private.json"]["sha256"]), c),
            "closed_child_inventory_file_changed")
    start_raw = child_read("started.json", 65536)
    start = _control(start_raw, new_manifest["started.json"]["sha256"])
    require(type(start.get("code_head")) is str and re.fullmatch(r"[0-9a-f]{40}", start["code_head"])
            and type(start.get("code_identity_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", start["code_identity_sha256"])
            and _same(start, {"schema": "si-manual-count-recovery-start-v1",
                "started_at": c["started_at"], "parent_inventory_sha256": parent_inventory.sha256,
                "child_plan_sha256": child_inventory._plan.sha256, "code_head": start.get("code_head"),
                "code_identity_sha256": start.get("code_identity_sha256"),
                "protocol_sha256": RECOVERY_PROTOCOL_SHA256, "authority": _driver_authority()}),
            "closed_child_start_code_and_plan_required")
    diagnostics = []
    child_queries = iter(child_inventory._plan._queries.iter_queries())
    child_ordinal, observed_bytes, records = 0, {"parent": 0, "child": 0}, []
    classes, counts, negatives = defaultdict(set), defaultdict(set), set()
    anchors = iter(source.iter_anchors())
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    for position, original_query in enumerate(source.query_plan.iter_queries(), 1):
        custody()
        anchor = next(anchors, None)
        ticket = original_query.to_payload()
        require(anchor is not None and anchor["anchor_index"] == position - 1
                and position <= ORIGINAL_COUNT, "complete_original_anchor_order_required")
        matrix_ordinal = selected[position - 1]
        require(anchor["original_query_ordinal"] == matrix_ordinal, "anchor_matrix_mapping_changed")
        if position <= PARENT_STARTED and position != FAILED_POSITION:
            segment, local, query, inventory, read = "parent", position, original_query, parent_inventory, parent_read
        else:
            child_ordinal += 1
            query = next(child_queries, None)
            require(query is not None and original_to_matrix_mapping[child_ordinal - 1] == (position, matrix_ordinal),
                    "complete_unique_child_mapping_required")
            segment, local, inventory, read = "child", child_ordinal, child_inventory, child_read
        query_ticket = query.to_payload()
        require(query_ticket["query_ordinal"] == local
                and query_ticket["request_sha256"] == ticket["request_sha256"],
                "child_or_parent_descriptor_reuse_refused")
        receipt = inventory.receipt_for_ordinal(local)
        if segment == "child":
            prefix = f"query-{local:08d}"
            began_raw = child_read(prefix + ".started.json", 65536)
            began = _control(began_raw, new_manifest[prefix + ".started.json"]["sha256"])
            require(_same(began, {"schema": "si-manual-count-recovery-request-start-v1",
                "query_ordinal": local, "original_count_position": position,
                "request": query_ticket["request"], "request_sha256": query_ticket["request_sha256"],
                "started_at": receipt["started_at"], "child_plan_sha256": child_inventory._plan.sha256,
                "code_head": start["code_head"], "whole_page_bytes_reserved": parallel.MAXIMUM_RESPONSE_BYTES}),
                "original_child_START_mapping_changed")
            received_raw = child_read(prefix + ".received.json", 65536)
            require(_same(_control(received_raw, new_manifest[prefix + ".received.json"]["sha256"]), receipt),
                    "original_child_receipt_changed")
            if not receipt["body_observed"]:
                diagnostic_raw = child_read(prefix + ".diagnostic.private.json", 65536)
                diagnostic = _control(diagnostic_raw, new_manifest[prefix + ".diagnostic.private.json"]["sha256"])
                require(_same(diagnostic, {"query_ordinal": local, "failure_stage": "transport",
                    "http_attempted": True, "http_status": 404,
                    "observed_receipt_at": receipt["received_at"], "protocol_sha256": RECOVERY_PROTOCOL_SHA256}),
                    "original_404_diagnostic_changed")
                diagnostics.append(diagnostic)
        raw = b""
        if receipt["body_observed"]:
            raw = read(receipt["raw_path"], parallel.MAXIMUM_RESPONSE_BYTES)
            custody()
            require(type(raw) is bytes and len(raw) == receipt["raw_bytes"]
                    and hash_bytes(raw) == receipt["raw_sha256"], "bound_original_response_bytes_required")
            observed_bytes[segment] += len(raw)
        require(type(receipt["http_status"]) is int, "unobserved_transport_slot_cannot_cover_source")
        capture = references.capture_native_dated_class_response(query, raw=raw, raw_sha256=hash_bytes(raw),
            request_sha256=query_ticket["request_sha256"], received_at=receipt["received_at"],
            http_status=receipt["http_status"], content_type=receipt["content_type"] or "",
            body_observed=receipt["body_observed"])
        parallel.verify_capture_receipt(inventory, capture)
        result = references._response(capture)
        normalized = result["normalized"]
        reasons = [] if result["reason"] is None else [result["reason"]]
        at = result["query_asof_date"]
        require(at == anchor["query_asof_date"], "original_anchor_asof_changed")
        for composite in result["source_composites"]:
            classes[(composite, at)].update(result["source_classes"])
        for class_id in result["source_classes"]:
            if normalized is None:
                negatives.add((class_id, at))
        if normalized is not None:
            if normalized["share_class_figi"] != anchor["share_class_figi"]:
                reasons.append("count_class_does_not_match_dated_identity")
            if normalized["composite_figi"] != anchor["composite_figi"]:
                reasons.append("count_composite_does_not_match_dated_identity")
            counts[(normalized["share_class_figi"], at)].add(normalized["same_class_count"]["numerator"])
        records.append({"original_count_position": position, "original_query_ordinal": matrix_ordinal,
            "anchor_index": position - 1, "query_asof_date": at, "source_segment": segment,
            "segment_query_ordinal": local, "actual_receipt_UTC": receipt["received_at"],
            "parallel_request_started_at": receipt["started_at"], "source_origin": result["origin"],
            "source_inventory_sha256": inventory.sha256,
            "same_class_count": None if normalized is None else normalized["same_class_count"],
            "observed_ids": None if normalized is None else
                [normalized["composite_figi"], normalized["share_class_figi"]], "refusal_reasons": reasons})
        del raw, capture, result, normalized
    # All global controls finish here, not after the last outward record yield.
    require(len(records) == ORIGINAL_COUNT and next(anchors, None) is None
            and child_ordinal == len(original_to_matrix_mapping) and next(child_queries, None) is None,
            "complete_original_and_child_sequences_required")
    require(observed_bytes == {"parent": p["retained_raw_bytes"], "child": c["retained_raw_bytes"]},
            "complete_parent_child_raw_byte_totals_required")
    diagnostic_raw = child_read("diagnostics.inventory.private.json", 64 * 1024 * 1024)
    require(_same(_decoded(diagnostic_raw, new_manifest["diagnostics.inventory.private.json"]["sha256"],
                          64 * 1024 * 1024), diagnostics), "complete_diagnostics_inventory_required")
    encoded = []
    for record in records:
        ids, at = record.pop("observed_ids"), record["query_asof_date"]
        if ids is not None:
            composite, class_id = ids
            if (class_id, at) in negatives or len(counts[(class_id, at)]) != 1:
                record["refusal_reasons"].append("same_class_same_asof_count_conflict_or_malformed_peer")
            if len(classes[(composite, at)]) != 1:
                record["refusal_reasons"].append("same_date_composite_class_conflict")
        record["refusal_reasons"] = sorted(set(record["refusal_reasons"]))
        record.update(authority=authority(), source_epoch=SOURCE_EPOCH)
        encoded.append(canonical_json(record))
    custody(); _plans(source, parent_inventory, child_inventory, original_to_matrix_mapping)
    _closure(parent_inventory, child_inventory, marker, closure)
    membership()
    header = {"schema": "si-native-count-recovery-registry-v1", "economic_evidence_epoch": EPOCH_ID,
        "source_epoch": SOURCE_EPOCH, "anchor_plan_sha256": source.sha256,
        "parent_inventory_sha256": parent_inventory.sha256, "child_inventory_sha256": child_inventory.sha256,
        "mapping_sha256": MAPPING_SHA256, "child_marker_sha256": expected_child_marker_sha256,
        "child_closure_sha256": expected_child_closure_sha256,
        "parent_file_manifest_sha256": PARENT_MANIFEST_SHA256,
        "child_file_manifest_sha256": expected_child_manifest_sha256,
        "planned_anchor_count": ORIGINAL_COUNT, "captured_anchor_count": len(records),
        "complete_composite_source_sequence": True, "original_round_complete": False,
        "original_negative_receipt": negative, "parent_budget": p, "child_budget": c,
        "cumulative_starts": p["attempts_started"] + c["attempts_started"],
        "cumulative_http_invocations": p["http_invocations"] + c["http_invocations"],
        "cumulative_charged_response_bytes": p["charged_response_bytes"] + c["charged_response_bytes"],
        "full_provider_coverage_admitted": False, "authority": authority()}
    header_raw, encoded = canonical_json(header), tuple(encoded)
    digest = hashlib.sha256((header_raw + "\n").encode())
    for raw in encoded:
        digest.update(raw.encode() + b"\n")
    value = object.__new__(CountRecoveryRegistry)
    parts = (source, parent_inventory, child_inventory, original_to_matrix_mapping, encoded,
             header_raw, digest.hexdigest(), custody)
    for name, item in zip(("_source", "_parent", "_child", "_mapping", "_records", "_header",
                          "_digest", "_custody"), parts):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", parts); object.__setattr__(value, "_identity", parts)
    value._guard()
    return value
