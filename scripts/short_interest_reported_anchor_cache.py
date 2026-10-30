"""Protected owned-cache adapter; no source retrieval, secrets, or QC API.

No operational CLI is provided until Main freezes a clean runtime code/head,
an exact protected cache path and the independently verified closure-byte pin.
Four physical part files avoid one Git/FD operation per split event. Logical
event bytes/digests remain individually bound by the registered closure.
"""
from dataclasses import dataclass, field
import re
import struct

from data.hashing import canonical_json, hash_bytes
from research.short_interest_etf.contracts import parse_utc_timestamp
import scripts.continue_short_interest_native_identity as capture
import research.short_interest_etf.native_reported_anchor_cache as contract
from scripts import load_short_interest_native_identity_continuation as protected

MAGIC = b"si-exact-anchor-events-v1\0"
PHYSICAL_NAMES = ("header.private.json", "anchors.private.bin", "cells.private.bin", "events.private.bin")
MAXIMUM_EVENT_BYTES = 65536
MAXIMUM_EVENT_COUNT = 500000


def pack_events(events):
    contract.require(type(events) is tuple and len(events) <= MAXIMUM_EVENT_COUNT
            and all(type(raw) is bytes and len(raw) <= MAXIMUM_EVENT_BYTES for raw in events), "bounded_exact_event_bytes")
    contract.require(len(MAGIC) + 8 + sum(8 + len(raw) for raw in events) <= 512 * 1024 * 1024,
            "finite_packed_event_storage_limit")
    return MAGIC + struct.pack("<Q", len(events)) + b"".join(struct.pack("<Q", len(raw)) + raw for raw in events)


def unpack_events(raw):
    contract.require(type(raw) is bytes and raw.startswith(MAGIC) and len(raw) >= len(MAGIC) + 8,
            "exact_packed_event_magic")
    count, = struct.unpack_from("<Q", raw, len(MAGIC))
    contract.require(count <= MAXIMUM_EVENT_COUNT, "packed_event_count_bound")
    offset, result = len(MAGIC) + 8, []
    for _ in range(count):
        contract.require(offset + 8 <= len(raw), "packed_event_length_missing")
        length, = struct.unpack_from("<Q", raw, offset)
        offset += 8
        contract.require(length <= MAXIMUM_EVENT_BYTES and offset + length <= len(raw), "packed_event_length_bound")
        result.append(raw[offset:offset + length])
        offset += length
    contract.require(offset == len(raw), "unbound_extra_event_bytes")
    return tuple(result)


@dataclass(frozen=True, slots=True, init=False)
class CacheCandidate:
    _plan: object = field(repr=False)
    _files: tuple = field(repr=False)
    _closure: bytes = field(repr=False)
    _known: str = field(repr=False)
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise contract.AnchorCacheRefusal("cache_candidate_factory_required")

    def guard(self):
        contract.require(type(self) is CacheCandidate and self._anchor is self._identity
                and all(current is bound for current, bound in zip((self._plan, self._files, self._closure, self._known), self._anchor)),
                "cache_candidate_changed")
        self._plan._guard()
        contract.require(canonical_json(contract.KNOWN) == self._known and self._plan.sha256 == contract.KNOWN["plan_sha256"],
                "observed_plan_anchor_changed")

    @property
    def closure_sha256(self):
        self.guard()
        return hash_bytes(self._closure)

    def iter_files(self):
        self.guard()
        for name, raw in self._files:
            self.guard()
            yield name, raw
        self.guard()
        yield "closure.private.json", self._closure


def prepare_cache(plan, *, runtime_head, cache_code_identity_sha256, completed_at):
    contract.require(type(plan) is contract.reported.NativeReportedAnchorPlan
            and type(runtime_head) is str and re.fullmatch(r"[0-9a-f]{40}", runtime_head)
            and contract.digest(cache_code_identity_sha256), "exact_observed_plan_and_runtime_code_required")
    plan._guard()
    parse_utc_timestamp(completed_at, "cache_preparation_clock")
    header = plan.header()
    contract.require(plan.sha256 == contract.KNOWN["plan_sha256"]
            and header["exact_request_budget"] == contract.KNOWN["request_budget"]
            and header["source_matrix_sha256"] == contract.KNOWN["matrix_sha256"]
            and len(header["identity_source_pins"]) == contract.KNOWN["date_count"], "Main_observed_plan_not_arbitrary_flag")
    logical = tuple(plan.iter_parts())
    names = list(PHYSICAL_NAMES[:3]) + [f"event-{index:06d}.private.json" for index in range(1, len(logical) - 2)]
    physical = tuple(zip(PHYSICAL_NAMES, (*logical[:3], pack_events(tuple(logical[3:])))))
    closure = {"schema": "si-exact-reported-anchor-cache-closure-v1", "observed_source": dict(contract.KNOWN),
            "parts": [{"name": name, "sha256": hash_bytes(raw), "bytes": len(raw)} for name, raw in zip(names, logical)],
            "physical_files": [{"name": name, "sha256": hash_bytes(raw), "bytes": len(raw)} for name, raw in physical],
            "cache_runtime_head": runtime_head, "cache_code_identity_sha256": cache_code_identity_sha256,
            "cache_prepared_at": completed_at, "source_only": True, "source_admitted": False,
            "ready_for_empirical_backtest": False, "provider_requests": 0, "credential_reads": 0,
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    value = object.__new__(CacheCandidate)
    parts = plan, physical, canonical_json(closure).encode(), canonical_json(contract.KNOWN)
    for name, item in zip(("_plan", "_files", "_closure", "_known"), parts):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", parts)
    object.__setattr__(value, "_identity", parts)
    value.guard()
    return value


def publish_owned_cache(candidate, owned, *, boundary):
    """Only a newly create-exclusive protected run receives these fixed names."""
    contract.require(type(candidate) is CacheCandidate and type(owned) is capture._OwnedOutput,
            "exact_candidate_owned_directory_FDs_required")
    boundary()
    owned.check()
    contract.require(not protected.os.listdir(owned._anchor[2]), "only_empty_new_owned_cache_run_can_publish")
    for name, raw in candidate.iter_files():
        boundary()
        owned.check()
        candidate.guard()
        try:
            owned.publish(name, raw)  # O_EXCL0600/no-link/inode checks; never overwrite a prefix.
        finally:
            boundary()
            owned.check()


def reload_owned_cache(owned, matrix, actions, dictionary, *, boundary,
        expected_runtime_head, expected_cache_code_identity_sha256):
    """Five exact files + registered closure pin; no source-history recapture."""
    contract.require(type(owned) is capture._OwnedOutput and type(expected_runtime_head) is str
            and re.fullmatch(r"[0-9a-f]{40}", expected_runtime_head)
            and contract.digest(expected_cache_code_identity_sha256), "protected_cache_runtime_descriptor")
    def read(name, maximum):
        boundary()
        try:
            return protected.read_owned_source(owned, name, maximum)
        finally:
            boundary()
    boundary()
    names = tuple(sorted(protected.os.listdir(owned._anchor[2])))
    contract.require(names == tuple(sorted((*PHYSICAL_NAMES, "closure.private.json"))), "exact_five_file_cache_inventory")
    proof = contract.verify_closure(read("closure.private.json", 128 * 1024 * 1024))
    closure = proof.payload()
    contract.require(closure.get("cache_runtime_head") == expected_runtime_head
            and closure.get("cache_code_identity_sha256") == expected_cache_code_identity_sha256
            and type(closure.get("physical_files")) is list
            and [part.get("name") for part in closure["physical_files"] if type(part) is dict] == list(PHYSICAL_NAMES),
            "registered_cache_code_and_four_physical_files")
    raws = []
    for pin in closure["physical_files"]:
        contract.require(set(pin) == {"name", "sha256", "bytes"} and contract.digest(pin["sha256"])
                and type(pin["bytes"]) is int and 0 <= pin["bytes"] <= 512 * 1024 * 1024, "bounded_cache_file_pin")
        raw = read(pin["name"], max(1, pin["bytes"]))
        contract.require(hash_bytes(raw) == pin["sha256"] and len(raw) == pin["bytes"], "registered_physical_cache_bytes")
        raws.append(raw)
    events = unpack_events(raws[3])
    rebuilt = contract.rebuild_anchor_plan(matrix, *raws[:3], events, actions, dictionary, closure=proof)
    boundary()
    owned.check()
    contract.require(tuple(sorted(protected.os.listdir(owned._anchor[2]))) == names, "cache_inventory_changed_during_reload")
    return rebuilt
