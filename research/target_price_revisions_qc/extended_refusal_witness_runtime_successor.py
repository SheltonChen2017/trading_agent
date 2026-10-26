"""Offline successor contract for a bounded first-refusal witness reader.

No controller, permit, CLI, executable program, notebook or QuantBook is created.
The runtime seam can read a supplied store, so it must NOT be called with a real
store without a separately frozen, authorized and reviewed effect controller.
Injected clocks/reference checks prove software semantics, not native custody.
The old standalone programs and holders remain retired. This does not renew
their scopes, authorize reads, repair the strategy or establish a valid OFF run.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import math
import re

from . import extended_refusal_witness_read_design as predecessor

PROJECT, JOB = predecessor.PROJECT, predecessor.JOB
MAX_SECONDS, MAX_RESULT_BYTES = 600, 8192
_PERMIT_KEYS = frozenset(("schema operation_id project_id job_id issued_utc expires_utc "
    "max_elapsed_seconds max_contains_calls max_read_calls max_bytes_each effects_authorized").split())
_CAPSULE_KEYS = frozenset(("schema operation_id tool_project_id job_id tool_context_sha256 "
    "project_identity_provenance").split())
_RESULT_KEYS = frozenset(("schema operation_id project_id job_id status contains_calls read_calls objects "
    "authority_granted controller_implemented ready_for_dispatch native_project_custody_proven "
    "external_capsule_authentication_proven actual_clock_proven sdk_hard_timeout_proven "
    "byte_bound_before_native_allocation_proven off_baseline_valid on_launch_authorized "
    "new_jobs new_codex_attempts new_looks").split())
_OBJECT_KEYS = frozenset(("kind present status read_attempted gzip_bytes gzip_sha256 plain_bytes plain_sha256").split())
_FALSE_KEYS = _RESULT_KEYS - frozenset(("schema operation_id project_id job_id status contains_calls read_calls objects "
    "new_jobs new_codex_attempts new_looks").split())
_OPERATION = re.compile(r"TPR-EXT26-WITNESS-RUNTIME-[A-Z0-9][A-Z0-9-]{0,63}")
_HASH = re.compile(r"[a-f0-9]{64}")


class RuntimeReadRefusal(ValueError):
    """Fixed body-free diagnostic refusal."""


def _fail():
    raise RuntimeReadRefusal("offline witness runtime contract refused")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _fail()


def _utc(value):
    if type(value) is not datetime or value.utcoffset() != timedelta(0):
        _fail()
    return value


def _clock_text(value):
    if type(value) is not str or len(value) > 40:
        _fail()
    try:
        parsed = _utc(datetime.fromisoformat(value))
    except (ValueError, OverflowError):
        _fail()
    if parsed.isoformat() != value:
        _fail()
    return parsed


def _tick(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        _fail()
    return value


def _operation(value):
    if type(value) is not str or _OPERATION.fullmatch(value) is None:
        _fail()
    return value


def validate_permit(permit):
    """Pure shape/budget validation, never an authorization or scope renewal.

    A future controller must freeze this exact prospective contract with its
    own operation, actual source and owner authority before any real effect.
    No valid production permit is supplied or registered by this module.
    """
    _closed(permit, _PERMIT_KEYS)
    if (permit["schema"] != "tpr-ext26-witness-runtime-contract-v1"
            or type(permit["project_id"]) is not int or permit["project_id"] != PROJECT
            or permit["job_id"] != JOB or permit["effects_authorized"] is not False):
        _fail()
    _operation(permit["operation_id"])
    issued, expires = (_clock_text(permit[key]) for key in ("issued_utc", "expires_utc"))
    maximum = permit["max_elapsed_seconds"]
    if (type(maximum) is not int or not 1 <= maximum <= MAX_SECONDS
            or not timedelta(0) < expires - issued <= timedelta(seconds=maximum)):
        _fail()
    for key, expected in (("max_contains_calls", 2), ("max_read_calls", 2),
                          ("max_bytes_each", predecessor.MAX_BYTES)):
        if type(permit[key]) is not int or permit[key] != expected:
            _fail()
    return _canonical(permit)


def validate_capsule(capsule, *, operation_id):
    """A bound external metadata statement, not authenticated native custody."""
    _closed(capsule, _CAPSULE_KEYS)
    if (capsule["schema"] != "tpr-ext26-witness-runtime-context-v1"
            or capsule["operation_id"] != _operation(operation_id)
            or type(capsule["tool_project_id"]) is not int or capsule["tool_project_id"] != PROJECT
            or capsule["job_id"] != JOB
            or capsule["project_identity_provenance"] != "genuine_mia_ephemeral_tool_metadata"
            or type(capsule["tool_context_sha256"]) is not str
            or _HASH.fullmatch(capsule["tool_context_sha256"]) is None):
        _fail()
    return _canonical(capsule)


def design():
    """Build-only status; no executable native program or current permit."""
    return {"schema": "tpr-ext26-witness-runtime-successor-design-v1",
        "project_id": PROJECT, "job_id": JOB, "max_contains_calls": 2, "max_read_calls": 2,
        "max_bytes_each_after_native_allocation": predecessor.MAX_BYTES,
        "intrinsic_utc_monotonic_project_store_checks": True,
        "controller_implemented": False, "program_built": False, "permit_registered": False,
        "ready_for_dispatch": False, "authority_granted": False,
        "sdk_hard_timeout_proven": False, "byte_bound_before_native_allocation_proven": False,
        "native_project_custody_proven": False, "actual_clock_proven": False,
        "off_baseline_valid": False, "on_launch_authorized": False}


def _new_result():
    return {"schema": "tpr-ext26-witness-runtime-result-v1", "operation_id": None,
        "project_id": PROJECT, "job_id": JOB, "status": "failed_or_uncertain",
        "contains_calls": 0, "read_calls": 0, "objects": [],
        **dict.fromkeys(_FALSE_KEYS, False), "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0}


def validate_result(result):
    """Closed bounded metadata only; no raw witness, native error or identifiers."""
    _closed(result, _RESULT_KEYS)
    if (result["schema"] != "tpr-ext26-witness-runtime-result-v1"
            or type(result["project_id"]) is not int or result["project_id"] != PROJECT
            or result["job_id"] != JOB
            or type(result["status"]) is not str
            or result["status"] not in {"failed_or_uncertain", "completed_diagnostic_only", "cancelled"}
            or any(result[key] is not False for key in _FALSE_KEYS)):
        _fail()
    if result["operation_id"] is not None:
        _operation(result["operation_id"])
    for key in ("new_jobs", "new_codex_attempts", "new_looks"):
        if type(result[key]) is not int or result[key] != 0:
            _fail()
    if (type(result["objects"]) is not list or len(result["objects"]) > 2
            or type(result["contains_calls"]) is not int or result["contains_calls"] != len(result["objects"])
            or type(result["read_calls"]) is not int or not 0 <= result["read_calls"] <= 2):
        _fail()
    for index, row in enumerate(result["objects"]):
        _closed(row, _OBJECT_KEYS)
        if (row["kind"] != predecessor.KINDS[index]
                or row["present"] is not None and type(row["present"]) is not bool
                or type(row["read_attempted"]) is not bool):
            _fail()
        if row["status"] == "validated_diagnostic":
            if row["present"] is not True or row["read_attempted"] is not True:
                _fail()
            for prefix in ("gzip", "plain"):
                if (type(row[prefix + "_bytes"]) is not int
                        or not 0 < row[prefix + "_bytes"] <= predecessor.MAX_BYTES
                        or type(row[prefix + "_sha256"]) is not str
                        or _HASH.fullmatch(row[prefix + "_sha256"]) is None):
                    _fail()
        else:
            if any(row[key] is not None for key in ("gzip_bytes", "gzip_sha256", "plain_bytes", "plain_sha256")):
                _fail()
            if row["status"] == "absent_uninterpreted":
                if row["present"] is not False or row["read_attempted"] is not False:
                    _fail()
            elif row["status"] != "failed_or_refused" or index != len(result["objects"]) - 1:
                _fail()
        if row["read_attempted"] and row["present"] is not True:
            _fail()
    if result["read_calls"] != sum(row["read_attempted"] for row in result["objects"]):
        _fail()
    if result["operation_id"] is None and result["contains_calls"]:
        _fail()
    if result["status"] == "completed_diagnostic_only" and (result["operation_id"] is None
            or len(result["objects"]) != 2
            or any(row["status"] not in {"absent_uninterpreted", "validated_diagnostic"} for row in result["objects"])):
        _fail()
    encoded = _canonical(result)
    if len(encoded) > MAX_RESULT_BYTES:
        _fail()
    return json.loads(encoded)


class RuntimeReadCancelled(KeyboardInterrupt):
    """Cancellation propagates with a closed body-free accounting snapshot."""
    def __init__(self, result):
        super().__init__("bounded witness runtime cancelled; no continued reads")
        self._result = validate_result(result)

    @property
    def result(self):
        return validate_result(self._result)


def read_runtime_witnesses(qb, permit, capsule, *, utc_now, monotonic_clock, reference_equals):
    """Explicit future seam; current validation uses synthetic objects ONLY.

    Checks are intrinsic, not an externally supplied no-op scope callback.
    Actual callbacks/native context still need a future reviewed controller.
    Native calls cannot be preempted here; post-call checks prevent further
    spending but cannot establish a transport timeout or pre-allocation bound.
    Only hashes/sizes leave this seam, never raw values or witness bodies.
    """
    result = _new_result()
    try:
        frozen_permit = validate_permit(permit)
        result["operation_id"] = permit["operation_id"]
        frozen_capsule = validate_capsule(capsule, operation_id=result["operation_id"])
        if not all(callable(value) for value in (utc_now, monotonic_clock, reference_equals)):
            _fail()
        issued, expires = (_clock_text(permit[key]) for key in ("issued_utc", "expires_utc"))
        maximum = permit["max_elapsed_seconds"]
        begin, first_tick = _utc(utc_now()), _tick(monotonic_clock())
        previous_now, previous_tick = begin, first_tick
        store = None

        def check():
            nonlocal previous_now, previous_tick
            now, tick = _utc(utc_now()), _tick(monotonic_clock())
            if (now < previous_now or tick < previous_tick or not issued <= now < expires
                    or not 0 <= (now - begin).total_seconds() < maximum
                    or not 0 <= (now - issued).total_seconds() < maximum
                    or not 0 <= tick - first_tick < maximum
                    or validate_permit(permit) != frozen_permit
                    or validate_capsule(capsule, operation_id=result["operation_id"]) != frozen_capsule):
                _fail()
            previous_now, previous_tick = now, tick
            if type(qb.project_id) is not int or qb.project_id != PROJECT:
                _fail()
            if store is not None and reference_equals(store, qb.object_store) is not True:
                _fail()

        check()
        store = qb.object_store
        check()
        for kind in predecessor.KINDS:
            check()
            row = {"kind": kind, "present": None, "status": "failed_or_refused", "read_attempted": False,
                "gzip_bytes": None, "gzip_sha256": None, "plain_bytes": None, "plain_sha256": None}
            result["contains_calls"] += 1
            result["objects"].append(row)
            present = store.contains_key(predecessor.witness_key(kind))
            check()
            if type(present) is not bool:
                _fail()
            row["present"] = present
            if not present:
                row["status"] = "absent_uninterpreted"
                continue
            check()
            row["read_attempted"] = True
            result["read_calls"] += 1
            returned = store.read_bytes(predecessor.witness_key(kind))
            check()
            encoded = predecessor._native_bytes(returned)
            projected = predecessor.project_witness(encoded, kind=kind)
            check()
            if (type(projected) is not dict or projected.get("kind") != kind
                    or projected.get("status") != "validated_diagnostic"
                    or projected.get("key") != predecessor.witness_key(kind)
                    or projected.get("gzip_bytes") != len(encoded)
                    or projected.get("gzip_sha256") != hashlib.sha256(encoded).hexdigest()):
                _fail()
            summary = {key: projected[key] for key in ("gzip_bytes", "gzip_sha256", "plain_bytes", "plain_sha256")}
            # Validate BEFORE mutating the durable accounting projection. Bad
            # metadata must not erase the already spent contains/read counts.
            for prefix in ("gzip", "plain"):
                if (type(summary[prefix + "_bytes"]) is not int
                        or not 0 < summary[prefix + "_bytes"] <= predecessor.MAX_BYTES
                        or type(summary[prefix + "_sha256"]) is not str
                        or _HASH.fullmatch(summary[prefix + "_sha256"]) is None):
                    _fail()
            row.update(summary)
            row["status"] = "validated_diagnostic"
        check()
        result["status"] = "completed_diagnostic_only"
        return validate_result(result)
    except KeyboardInterrupt:
        result["status"] = "cancelled"
        raise RuntimeReadCancelled(result) from None
    except Exception:
        result["status"] = "failed_or_uncertain"
        # Own fixed-size counters/rows survive every refusal. Never synthesize
        # a zero-effect result after spending a contains/read attempt.
        return validate_result(result)
