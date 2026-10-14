"""Pure exact-plan cache reconstruction; no source/credential/provider I/O.

The actual plan digest/budget were independently observed by Main. A future
protected closure-byte pin is registered only after exclusive cache publication
and verification. No caller completion flag manufactures an anchor plan.
"""
from dataclasses import dataclass, field
from datetime import date
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrices
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.native_dated_class_reference as references
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.native_reported_anchor_plan as reported

REGISTERED_CLOSURE_SHA256 = "PENDING"
KNOWN = {"plan_sha256": "d58b2b3d006319899e6af9cd06a2fef17128c391513ea0ee99c987c483d2af3b",
    "request_budget": 81875, "date_count": 112, "source_attempts": 1340,
    "parent_attempts": 491, "child_attempts": 849,
    "identity_capture_head": "64f372ea8bfbcc542e87356a5e3e58fe07da1c27",
    "identity_capture_code_sha256": "00fd3e26b30ee6227eb734ee8afe66ceb8dd93f1b027c90bc7c4f1dd78ab55ca",
    "matrix_sha256": "e570c5b658668f0f9ab087dabbd968d4460294287eba1406ae203882144bc49e",
    "parent_inventory_sha256": "c3c4b6dfe08193ab0e943aea1f36ec057279139fe17af73cd79f8504908c24f8",
    "parent_budget_sha256": "33df02ba5722b3e80aea8daef5a6a432018a56d387272d48f8b3023c69e9c2e5",
    "child_inventory_sha256": "92f3eccbfb8985256a35364c4bf6739483e8fbbe41d563d5df2a0ed0954dd5b8",
    "child_budget_sha256": "f58314801ad84ddbd0f0de203efecf18a693ebc44dc089d4bcc15751c72a064e"}


class AnchorCacheRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise AnchorCacheRefusal(reason)


def exact(left, right):
    return canonical_json(left) == canonical_json(right)


def digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def parsed(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_cache_key")
            result[key] = value
        return result
    def nonfinite(_):
        raise AnchorCacheRefusal("nonfinite_cache_JSON")
    require(type(raw) is bytes, "cache_original_bytes_required")
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise AnchorCacheRefusal("cache_JSON_refused") from None
    require(type(value) is dict and canonical_json(value).encode() == raw, "canonical_cache_JSON_required")
    return value


@dataclass(frozen=True, slots=True, init=False)
class VerifiedCacheClosure:
    _raw: bytes = field(repr=False)
    _known: str = field(repr=False)
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise AnchorCacheRefusal("registered_cache_closure_factory_required")

    def payload(self):
        require(type(self) is VerifiedCacheClosure and self._anchor is self._identity
                and self._raw is self._anchor[0] and self._known is self._anchor[1], "cache_closure_changed")
        require(canonical_json(KNOWN) == self._known and hash_bytes(self._raw) == REGISTERED_CLOSURE_SHA256,
                "registered_cache_anchor_changed")
        return parsed(self._raw)


def verify_closure(raw):
    require(digest(REGISTERED_CLOSURE_SHA256) and type(raw) is bytes
            and hash_bytes(raw) == REGISTERED_CLOSURE_SHA256, "cache_closure_unregistered_or_changed")
    value = parsed(raw)
    require(exact(value.get("observed_source"), KNOWN)
            and value.get("schema") == "si-exact-reported-anchor-cache-closure-v1"
            and value.get("source_only") is True and value.get("source_admitted") is False
            and value.get("ready_for_empirical_backtest") is False
            and all(type(value.get(key)) is int and value[key] == 0
                for key in ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
            and value.get("backtest_result_exists") is False, "registered_source_only_cache_closure")
    require(type(value.get("parts")) is list and len(value["parts"]) >= 3
            and all(type(part) is dict and set(part) == {"name", "sha256", "bytes"}
                and digest(part["sha256"]) and type(part["bytes"]) is int and part["bytes"] >= 0
                for part in value["parts"]), "exact_registered_part_descriptors")
    expected_names = ["header.private.json", "anchors.private.bin", "cells.private.bin"] + [
            f"event-{index:06d}.private.json" for index in range(1, len(value["parts"]) - 2)]
    require([part["name"] for part in value["parts"]] == expected_names, "exact_cache_part_names_and_order")
    result = object.__new__(VerifiedCacheClosure)
    anchor = raw, canonical_json(KNOWN)
    for name, item in (("_raw", raw), ("_known", anchor[1]), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    result.payload()
    return result


def rebuild_anchor_plan(matrix, header_raw, anchor_raw, cells_raw, event_raws, actions, dictionary, *, closure):
    require(type(closure) is VerifiedCacheClosure and type(matrix) is matrices.NativePopulationClassMatrix
            and type(event_raws) is tuple and all(type(raw) is bytes for raw in (header_raw, anchor_raw, cells_raw, *event_raws)),
            "exact_matrix_registered_closure_and_private_parts_required")
    proof = closure.payload()
    parts = (header_raw, anchor_raw, cells_raw, *event_raws)
    require(len(parts) == len(proof["parts"]) and all(hash_bytes(raw) == pin["sha256"] and len(raw) == pin["bytes"]
            for raw, pin in zip(parts, proof["parts"])), "registered_cache_part_bytes_changed")
    require(reported._packed_digest(header_raw, anchor_raw, cells_raw, event_raws) == KNOWN["plan_sha256"],
            "observed_exact_plan_digest_required")
    source, header = matrix.header(), parsed(header_raw)
    keys = {"schema", "policy_sha256", "source_matrix_sha256", "source_matrix_refusal_count", "identity_source_pins",
            "action_source_pins", "exact_request_budget", "cell_count", "class_label_count", "split_fence_count",
            "class_labels", "composites", "packed_cell_bytes", "packed_anchor_bytes", "underlying_query_plan_sha256", "authority"}
    require(set(header) == keys and header["schema"] == reported.SCHEMA
            and header["policy_sha256"] == hash_payload(reported.anchor_policy())
            and matrix.sha256 == KNOWN["matrix_sha256"] == header["source_matrix_sha256"]
            and header["source_matrix_refusal_count"] == source["refusal_count"]
            and exact(header["authority"], reported._authority()), "exact_cache_source_schema_policy_and_matrix")
    for field in ("exact_request_budget", "cell_count", "class_label_count", "split_fence_count", "packed_cell_bytes", "packed_anchor_bytes"):
        require(type(header[field]) is int and header[field] >= 0, "exact_integer_cache_counts")
    count, budget = source["query_count"], header["exact_request_budget"]
    require(0 < budget == KNOWN["request_budget"] <= count and header["cell_count"] == count
            and header["packed_cell_bytes"] == len(cells_raw) == count * reported._CELL.size
            and header["packed_anchor_bytes"] == len(anchor_raw) == budget * reported._ANCHOR.size
            and header["split_fence_count"] == len(event_raws), "bounded_exact_packed_plan_counts")
    labels, composites = header["class_labels"], header["composites"]
    require(type(labels) is list and len(labels) == header["class_label_count"] and labels
            and all(type(label) is list and len(label) == 2 and type(label[0]) is str
                and re.fullmatch(r"sharadar:permaticker:[1-9][0-9]{0,29}", label[0])
                and identity._figi(label[1]) == label[1] for label in labels)
            and len(set(tuple(label) for label in labels)) == len(labels)
            and type(composites) is list and composites and all(identity._figi(value) == value for value in composites)
            and len(set(composites)) == len(composites), "exact_native_class_and_composite_namespaces")
    pins = header["identity_source_pins"]
    require(type(pins) is list and len(pins) == KNOWN["date_count"]
            and [pin.get("query_date") for pin in pins if type(pin) is dict] == source["settlements"]
            and all(set(pin) == {"query_date", "source_sha256", "master_archive_sha256", "master_CSV_sha256"}
                and all(digest(pin[key]) for key in ("source_sha256", "master_archive_sha256", "master_CSV_sha256")) for pin in pins)
            and len({(pin["master_archive_sha256"], pin["master_CSV_sha256"]) for pin in pins}) == 1,
            "all_original_identity_dates_and_source_pins_retained")
    baseline, archive_pins = reported._split_fences(actions, dictionary)
    require(exact(header["action_source_pins"], list(archive_pins)) and len(baseline) == len(event_raws),
            "original_actions_dictionary_and_fence_inventory")
    for raw, original in zip(event_raws, baseline):
        event = parsed(raw)
        require(set(event) == set(original), "exact_fence_event_fields")
        found = event["same_date_native_class"]
        require(found is None or (type(found) is list and len(found) == 2 and type(found[0]) is str
                and re.fullmatch(r"sharadar:permaticker:[1-9][0-9]{0,29}", found[0]) and identity._figi(found[1]) == found[1]),
                "bound_fence_native_class_namespace")
        expected = {**original, "same_date_native_class": found,
                "refusal_reasons": sorted(set(original["refusal_reasons"] +
                    (["split_native_class_not_authenticated_on_action_date"] if found is None else [])))}
        require(exact(event, expected), "original_fence_origin_dates_and_refusals_preserved")
    anchor_values = tuple(reported._ANCHOR.iter_unpack(anchor_raw))
    selected, seen, previous_day = [], set(), -1
    query_bytes = matrix.parts()[1]
    for index, (ordinal, day, label, composite, flags, page, row) in enumerate(anchor_values):
        require(1 <= ordinal <= count and ordinal not in seen and previous_day <= day < len(source["settlements"])
                and label < len(labels) and composite < len(composites) and 1 <= flags <= 31
                and 1 <= page <= 2 * identity.MAXIMUM_PAGES_PER_PANEL and row < identity.MAXIMUM_PAGE_ROWS,
                "bounded_unique_chronological_anchor_record")
        require(matrices._QUERY.unpack_from(query_bytes, (ordinal - 1) * matrices._QUERY.size)[1] == day
                and reported._CELL.unpack_from(cells_raw, (ordinal - 1) * reported._CELL.size) == (index, label, 0),
                "anchor_original_source_ordinal_date_and_cell_binding")
        seen.add(ordinal)
        selected.append(ordinal)
        previous_day = day
    for index, (anchor, label, flags) in enumerate(reported._CELL.iter_unpack(cells_raw)):
        require(0 <= flags <= 15, "known_cell_refusal_bits_only")
        if flags & reported._MISSING_IDENTITY:
            require(anchor == label == -1 and not flags & reported._STALE, "negative_identity_cells_not_fabricated_positive")
        else:
            require(0 <= anchor < budget and 0 <= label < len(labels) and not flags & (reported._UNQUALIFIED_VENUE | reported._INACTIVE_LISTING),
                    "positive_cell_anchor_class_and_listing_refusal_consistency")
            old = anchor_values[anchor]
            day = matrices._QUERY.unpack_from(query_bytes, index * matrices._QUERY.size)[1]
            require(old[2] == label and old[1] <= day, "same_class_no_future_anchor_transfer")
            age_ok = reported.reported_anchor_age_ok(source["settlements"][old[1]], source["settlements"][day])
            require(bool(flags & reported._STALE) is (not age_ok), "exact_95_day_refusal_rule_preserved")
    queries = references.freeze_native_class_query_plan(matrix, mode="explicit_anchors", selected_query_ordinals=tuple(sorted(selected)))
    require(queries.sha256 == header["underlying_query_plan_sha256"] and queries.to_payload()["query_count"] == budget,
            "exact_selected_source_query_plan_reconstructed")
    result = object.__new__(reported.NativeReportedAnchorPlan)
    archives = tuple((archive, archive.raw, archive.table, archive.request_sha256) for archive in (actions, dictionary))
    bound = matrix, queries, header_raw, anchor_raw, cells_raw, event_raws, archives, KNOWN["plan_sha256"]
    for name, value in zip(("_matrix", "_query_plan", "_header", "_anchors", "_cells", "_events", "_archives", "_digest"), bound):
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_anchor", bound)
    object.__setattr__(result, "_identity", bound)
    result._guard()
    return result
