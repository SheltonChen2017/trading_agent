"""Pure OFF recovery preparation and prospective native-return validation.

Both entrypoints consume supplied public bytes/metadata only. They do not read
files, inspect Git, register a permit/claim, build an active native program,
contact a tool, create a notebook or launch a job. Repository observations and
return bindings are statements to validate, never authenticated custody.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import extended_refusal_witness_program_successor as program
from . import extended_refusal_witness_runtime_successor as runtime

ROOT = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions"
BRANCH = "codex/strategy-target-price-revisions"
PREFIX = "research/target_price_revisions_qc/"
SOURCE_SHA256 = {
    PREFIX + "extended_refusal_witness_controller_successor.py": "d96f57179568a841d872ac8eb243cdf1c8a2834cb2b68a33912cdebbf376194b",
    PREFIX + "extended_refusal_witness_runtime_successor.py": "cf8cd1a2c58af31643f14061cc170e99e020172f22ca7619588d801c4dae9d4f",
    PREFIX + "extended_refusal_witness_read_design.py": "6ee5593ed2fe5e504fcef867219e5ba4a0c5883d0294a6544c3636440a8b1d22",
    PREFIX + "extended_refusal_witness_context_successor.py": "1b057f254fba91eee98862bbb63b2141cea63962905c458459d7a47531215a0f",
    PREFIX + "extended_refusal_witness_program_successor.py": "4d4ec88689d0c22742f981d13e1288122684b4e300e26286ddb468cbdad47110",
}
MAX_SOURCE_BYTES = 65536
MAX_OWNER_BYTES = 8192
MAX_ENVELOPE_BYTES = 16384
_HASH = re.compile(r"[a-f0-9]{64}")
_HEAD = re.compile(r"[a-f0-9]{40}")
_INVOCATION = re.compile(r"[a-f0-9]{32}")
_OBSERVATION_KEYS = frozenset(("physical_root git_toplevel branch git_head status_short").split())
_BINDING_KEYS = frozenset(("operation_id invocation_id git_head plan_sha256 program_sha256 "
    "capsule_sha256 source_closure_sha256").split())
_ENVELOPE_KEYS = frozenset(("schema bindings delivery_status native_result").split())


class OffRecoveryRefusal(ValueError):
    """Fixed body-free refusal: never include source or native payload text."""


def _fail():
    raise OffRecoveryRefusal("offline OFF recovery preparation refused") from None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _fail()


def _match(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail()


def source_closure_sha256():
    """Digest of the independent known-public five-file identity map, no I/O."""
    return _sha(_canonical(SOURCE_SHA256))


def prepare_off_recovery(public_sources, *, repository_observation, owner_instruction):
    """Return a deterministic inert manifest, not a current operation permit.

    ``public_sources`` must contain exactly the independently pinned five
    public files as bytes. The clean repository observation must be obtained
    separately in the designated worktree. Owner text is hashed, not retained
    or interpreted as new authority. No dates, invocation or native capsule are
    minted here; fill none of those fields without fresh actual native work.
    """
    try:
        _closed(public_sources, frozenset(SOURCE_SHA256))
        _closed(repository_observation, _OBSERVATION_KEYS)
        observed = repository_observation
        if (any(type(value) is not str for value in observed.values())
                or observed["physical_root"] != ROOT or observed["git_toplevel"] != ROOT
                or observed["branch"] != BRANCH or observed["status_short"] != ""):
            _fail()
        _match(observed["git_head"], _HEAD)
        if (type(owner_instruction) is not bytes or not 0 < len(owner_instruction) <= MAX_OWNER_BYTES
                or not owner_instruction.strip()):
            _fail()
        for path, digest in SOURCE_SHA256.items():
            raw = public_sources[path]
            if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES or _sha(raw) != digest:
                _fail()
        program.validate_sources(
            builder_raw=public_sources[PREFIX + "extended_refusal_witness_program_successor.py"],
            expected_builder_sha256=SOURCE_SHA256[PREFIX + "extended_refusal_witness_program_successor.py"],
            runtime_raw=public_sources[PREFIX + "extended_refusal_witness_runtime_successor.py"],
            reader_raw=public_sources[PREFIX + "extended_refusal_witness_read_design.py"],
            witness_raw=public_sources[PREFIX + "extended_refusal_witness_context_successor.py"],
        )
        reader = runtime.predecessor
        body = {
            "schema": "tpr-ext26-off-recovery-preparation-v1",
            "mode": "offline_prepared_native_setup_pending",
            "repository_observation": dict(observed),
            "repository_observation_authenticated": False,
            "owner_instruction_sha256": _sha(owner_instruction),
            "owner_instruction_authenticated": False,
            "source_hashes": dict(SOURCE_SHA256),
            "source_closure_sha256": source_closure_sha256(),
            "resource_release": {"qc_safari_available": False, "availability_observed": False,
                "monitor_rearm_authorized": False, "analyst_push_is_automatic_release": False,
                "next_boundary": "fresh_owner_release_then_native_setup"},
            "study": {"study_id": "TPR-CAP-TILT-EXT26-20261010-v1", "arm": "OFF",
                "start": "2021-01-04", "end": "2026-10-09", "warmup": "2020-09-01",
                "valuations": 1449, "decisions": 301, "sleeves": ["SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX"],
                "selection": "cap_only_top10_fixed60_stock_slots", "tpr_tilt": "0", "ar_enabled": False},
            "retained_witness_contract": {"project_id": reader.PROJECT, "job_id": reader.JOB,
                "keys": [reader.witness_key(kind) for kind in reader.KINDS],
                "config_sha256": reader.witness.CONFIG_SHA256, "freeze_sha256": reader.witness.FREEZE_SHA256,
                "calendar_sha256": reader.witness.CALENDAR_SHA256,
                "max_contains_calls": 2, "max_read_calls": 2, "max_bytes_each_after_native_allocation": reader.MAX_BYTES,
                "frozen_input_hashes": dict(reader.INPUT_HASHES),
                "retained_key_identity_is_fresh_access_authority": False},
            "pending_native": dict.fromkeys(("operation_id", "invocation_id", "issued_utc", "expires_utc",
                "permit", "capsule", "tool_context", "program_sha256", "claim_receipt"), None),
            "pending_native_checklist": [
                "Observe owner-released QC/Safari availability without disturbing the other lane.",
                "Reverify actual worktree, HEAD, clean status, source closure and matching remote before effect.",
                "Discover a genuine own-project native capability; never fabricate an ephemeral Mia interface.",
                "If a new notebook is needed, freeze a fresh collision-free identity and actual tool metadata; do not reuse October 22 scopes.",
                "Reserve fresh bounded access/operation/attempt/look identities before each applicable effect; preserve historical counts.",
                "Verify an identified source-bound genuine adapter, intrinsic clocks, wall/byte limits and invocation/program return bindings.",
                "Validate only the two exact witness keys; no enumeration, History, source edits or launch in that read scope.",
                "Separate validated witness hashes from diagnosis sufficiency; units, source date and historical compiled custody may remain unknown.",
                "Make only evidence-bound lane corrections with frozen economics; reserve and verify full-window OFF before ON.",
            ],
            "authority_granted": False, "ready_for_dispatch": False, "native_binding_proven": False,
            "source_units_accepted": False, "diagnosis_sufficient": False, "off_baseline_valid": False,
            "on_launch_authorized": False, "old_scope_reuse_permitted": False,
            "sdk_hard_timeout_proven": False, "byte_bound_before_native_allocation_proven": False,
            "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0,
        }
        return {**json.loads(_canonical(body)), "preparation_sha256": _sha(_canonical(body))}
    except OffRecoveryRefusal:
        raise
    except Exception:
        _fail()


def _validate_bindings(value):
    _closed(value, _BINDING_KEYS)
    runtime._operation(value["operation_id"])
    _match(value["invocation_id"], _INVOCATION)
    _match(value["git_head"], _HEAD)
    for key in ("plan_sha256", "program_sha256", "capsule_sha256", "source_closure_sha256"):
        _match(value[key], _HASH)
    if value["source_closure_sha256"] != source_closure_sha256():
        _fail()
    return json.loads(_canonical(value))


def _decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ENVELOPE_BYTES:
        _fail()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail()
            result[key] = value
        return result
    def nonfinite(_text):
        _fail()
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    pending, count = [(result, 0)], 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if count > 256 or depth > 12:
            _fail()
        if type(value) is dict:
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            pending.extend((item, depth + 1) for item in value)
        elif type(value) is str and len(value) > 1024:
            _fail()
        elif type(value) is float:
            # Native contract contains integer counts only, including failure paths.
            _fail()
    return result


def validate_native_envelope(raw, *, expected_bindings):
    """Strict pure parser for a FUTURE body-free return, not authentication.

    Exact expected bindings must be frozen by the future genuine controller.
    Unreturned/uncertain transport retains null counts; cancellation may carry
    a validated partial result, never a fabricated zero-effect observation.
    A bound synthetic packet remains synthetic: all custody/acceptance flags
    returned here are false, regardless of a completed diagnostic status.
    """
    try:
        expected = _validate_bindings(expected_bindings)
        envelope = _decode(raw)
        _closed(envelope, _ENVELOPE_KEYS)
        if (envelope["schema"] != "tpr-ext26-off-native-envelope-v1"
                or _validate_bindings(envelope["bindings"]) != expected
                or type(envelope["delivery_status"]) is not str
                or envelope["delivery_status"] not in {"returned", "failed_or_uncertain", "cancelled"}):
            _fail()
        delivery, result = envelope["delivery_status"], envelope["native_result"]
        if result is None:
            if delivery == "returned":
                _fail()
            contains = reads = None
            status = delivery
        else:
            if delivery == "failed_or_uncertain":
                _fail()
            result = runtime.validate_result(result)
            if (result["operation_id"] != expected["operation_id"]
                    or delivery == "cancelled" and result["status"] != "cancelled"):
                _fail()
            contains, reads = result["contains_calls"], result["read_calls"]
            status = "cancelled" if delivery == "cancelled" else result["status"]
        return {"schema": "tpr-ext26-off-native-envelope-validation-v1", "bindings": expected,
            "status": status, "delivery_status": delivery, "native_result": result,
            "contains_calls": contains, "read_calls": reads, "binding_shape_validated": True,
            "envelope_sha256": _sha(raw), "native_tool_authenticated": False,
            "native_binding_proven": False, "authority_granted": False, "ready_for_dispatch": False,
            "diagnosis_sufficient": False, "source_units_accepted": False, "off_baseline_valid": False,
            "on_launch_authorized": False, "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0}
    except OffRecoveryRefusal:
        raise
    except Exception:
        _fail()
