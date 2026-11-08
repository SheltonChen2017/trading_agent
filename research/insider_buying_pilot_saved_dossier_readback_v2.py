"""Strict detached validation of the existing five-leaf dossier receipt.

This pure module performs no file, Git, network, credential or operation IO.
The native caller authenticates held filesystem bytes. Final acceptance also
requires its separate source-only Git verification of both source maps.
The known complete anchor authenticates the saved receipt; validation does
not rerun original inputs, reauthenticate the historical storage proof, or
reconstruct the historical Python environment. Current reader identity is
separate from the original execution identity, so a later HEAD is supported.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re

from research import insider_buying_pilot_storage_dossier_runner_v1 as prior

SCHEMA = "insider-pilot-saved-dossier-readback-v2"
ORIGINAL_HEAD = "cbd2897ce4fe4e22362587eb68f6f546e919c341"
ORIGINAL_INVENTORY = "226cf2c05005b659faa3b0c4130c39c53dddd49fd5b0dc0db9822f35a556ee25"
ORIGINAL_SOURCE_COUNT = 177
COMPLETE_SHA256 = "e55a9aaaf6f56c1f12b248fe3b6befdf04d00fcbffa90f27d64733f880a5039e"
TRANSITION_SHA256 = "bc3d0577a7ea5a240c497d26930dac2b0f1b8ca6a8a398569b684bd3753b3be1"
DOSSIER_SHA256 = "9d42dedbdca0f8f0c8012ad183c250198ec68c9bd762f371bcb2ec830a9df472"
REFERENCE_AUDIT_SHA256 = "485cc1057bb7d23c4c44052cd53206d7711c0b135787b9b396bf57dc8fcff8b0"
OUTPUT_NAMES = tuple(prior.OUTPUT_NAMES)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_SOURCE = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py\Z")
_COUNT_KEYS = frozenset({"controls", "originals_reparsed", "issuer_ciks",
    "reporting_owner_occurrences", "distinct_reporting_owners", "security_title_occurrences",
    "observed_security_titles", "quarantined_security_titles", "unplaced_security_titles",
    "entries_missing_security_title"})
ACTUAL_COUNTS = {"controls": 12, "originals_reparsed": 12, "issuer_ciks": 11,
    "reporting_owner_occurrences": 13, "distinct_reporting_owners": 13,
    "security_title_occurrences": 37, "observed_security_titles": 37,
    "quarantined_security_titles": 0, "unplaced_security_titles": 0,
    "entries_missing_security_title": 0}


class SavedReadbackError(ValueError):
    """Only fixed refusal codes; never private saved values or exception text."""


def need(ok, code="saved_readback_refused"):
    if not ok:
        raise SavedReadbackError(code)


def _raw(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        need(0 < len(data) <= prior.stable.MAX_EPOCH_BYTES, "saved_payload_refused")
        return data
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise SavedReadbackError("saved_payload_refused") from None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _copy(value):
    return json.loads(_raw(value))


def _shape(value, keys, code="saved_payload_refused"):
    need(type(value) is dict and set(value) == set(keys), code)


def _same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _json_types(value):
    """The saved contract has no float fields; reject aliases before old checks."""
    if type(value) is dict:
        need(all(type(key) is str for key in value), "saved_payload_refused")
        for key, child in value.items():
            if key == "authority":
                need(_same(child, prior.transition.authority()), "saved_authority_refused")
            _json_types(child)
    elif type(value) is list:
        for child in value:
            _json_types(child)
    else:
        need(value is None or type(value) in {str, bool, int}, "saved_payload_refused")


def source_identity(value):
    """Strict source-map contract only; the caller must verify each Git byte."""
    _shape(value, {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"},
           "saved_identity_refused")
    need(type(value["root"]) is str and value["root"] == str(prior.ROOT)
         and type(value["branch"]) is str and value["branch"] == prior.BRANCH
         and value["clean"] is True and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
         and type(value["source_sha256"]) is dict and 0 < len(value["source_sha256"]) <= 1024,
         "saved_identity_refused")
    for name, digest in value["source_sha256"].items():
        need(type(name) is str and len(name) <= 512 and _SOURCE.fullmatch(name)
             and not PurePosixPath(name).is_absolute() and PurePosixPath(name).as_posix() == name
             and all(part not in {".", ".."} for part in name.split("/"))
             and name.split("/", 1)[0] != "artifacts"
             and type(digest) is str and _SHA.fullmatch(digest), "saved_identity_refused")
    need(type(value["source_inventory_sha256"]) is str and _SHA.fullmatch(value["source_inventory_sha256"])
         and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "saved_identity_refused")
    return _copy(value)


def _identities(original, reader, *, fixture):
    original, reader = source_identity(original), source_identity(reader)
    need(all(reader["source_sha256"].get(name) == digest
             for name, digest in original["source_sha256"].items()), "saved_source_overlap_refused")
    if not fixture:
        need(original["head"] == ORIGINAL_HEAD
             and original["source_inventory_sha256"] == ORIGINAL_INVENTORY
             and len(original["source_sha256"]) == ORIGINAL_SOURCE_COUNT, "saved_original_anchor_refused")
    return original, reader


def extract_original_identity(value):
    """Extract only after the external complete->reservation pin is checked.

    This is not final saved-result acceptance or a Git/source-byte check.
    The caller must still run validate_saved and its separate Git verifier.
    """
    try:
        _shape(value, {"schema", "audit_id", "controls", "pins", "storage_identity"})
        need(value["schema"] == prior.stable.SCHEMA + "/readback"
             and value["audit_id"] == prior.AUDIT_ID, "saved_payload_refused")
        _shape(value["controls"], OUTPUT_NAMES)
        _shape(value["pins"], OUTPUT_NAMES)
        complete = value["controls"]["complete.json"]
        complete_pin = value["pins"]["complete.json"]
        _pin(complete_pin)
        complete_bytes = _raw(complete)
        need(complete_pin == {"bytes": len(complete_bytes), "sha256": _sha(complete_bytes)}
             and complete_pin["sha256"] == COMPLETE_SHA256, "saved_complete_anchor_refused")
        _shape(complete["published_leaf_pins"], set(OUTPUT_NAMES) - {"complete.json"})
        reservation = value["controls"]["reservation.json"]
        pin = complete["published_leaf_pins"]["reservation.json"]
        _pin(pin)
        reservation_bytes = _raw(reservation)
        need(_same(pin, value["pins"]["reservation.json"])
             and pin == {"bytes": len(reservation_bytes), "sha256": _sha(reservation_bytes)},
             "saved_pin_refused")
        _shape(reservation, {"schema", "code_identity", "registration", "fixture_only", "storage"})
        original = source_identity(reservation["code_identity"])
        need(original["head"] == ORIGINAL_HEAD
             and original["source_inventory_sha256"] == ORIGINAL_INVENTORY
             and len(original["source_sha256"]) == ORIGINAL_SOURCE_COUNT,
             "saved_original_anchor_refused")
        return original
    except SavedReadbackError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        raise SavedReadbackError("saved_readback_refused") from None


def _pin(value):
    _shape(value, {"bytes", "sha256"})
    need(type(value["bytes"]) is int and 0 < value["bytes"] <= prior.stable.MAX_BYTES
         and type(value["sha256"]) is str and _SHA.fullmatch(value["sha256"]), "saved_pin_refused")


def _storage(value):
    _shape(value, {"schema", "root_kind", "device", "inode", "mode", "owner", "group"})
    need(value["schema"] == prior.stable.SCHEMA + "/storage-identity"
         and value["root_kind"] == "fixed_user_application_support", "saved_storage_refused")
    need(all(type(value[key]) is int and 0 <= value[key] < 2**63
             for key in ("device", "inode", "mode", "owner", "group"))
         and value["inode"] > 0 and value["mode"] == 0o700, "saved_storage_refused")


def _summary(value, original, reader, complete_sha256, *, fixture):
    complete = value["controls"]["complete.json"]
    dossier_counts = complete["dossier_summary"]["counts"]
    return {"schema": SCHEMA + "/summary", "completed": True,
        "fixture_only": fixture, "saved_receipt_contract_validated": True,
        "original_execution_head": original["head"], "original_source_inventory_sha256": original["source_inventory_sha256"],
        "reader_execution_head": reader["head"], "reader_source_inventory_sha256": reader["source_inventory_sha256"],
        "complete_sha256": complete_sha256,
        "transition_sha256": value["pins"]["transition.json"]["sha256"],
        "dossier_sha256": value["pins"]["dossier.json"]["sha256"],
        "reference_audit_sha256": complete["audit_summary"]["result_sha256"],
        "leaf_count": 5, "original_input_leaves_replayed": 0,
        "historical_evidence_gates_closed": 0,
        "historical_storage_identity_reauthenticated": False,
        "full_historical_environment_replayed": False,
        "counts": {key: dossier_counts[key] for key in _COUNT_KEYS},
        "authority": prior.transition.authority()}


def _validate(value, *, original_identity, reader_identity, complete_sha256, fixture):
    need(type(fixture) is bool and type(complete_sha256) is str and _SHA.fullmatch(complete_sha256),
         "saved_arguments_refused")
    original, reader = _identities(original_identity, reader_identity, fixture=fixture)
    _shape(value, {"schema", "audit_id", "controls", "pins", "storage_identity"})
    need(value["schema"] == prior.stable.SCHEMA + "/readback" and value["audit_id"] == prior.AUDIT_ID,
         "saved_payload_refused")
    _shape(value["controls"], OUTPUT_NAMES)
    _shape(value["pins"], OUTPUT_NAMES)
    for name in OUTPUT_NAMES:
        _pin(value["pins"][name])
        encoded = _raw(value["controls"][name])
        need(value["pins"][name] == {"bytes": len(encoded), "sha256": _sha(encoded)}, "saved_pin_refused")
    need(sum(pin["bytes"] for pin in value["pins"].values()) <= prior.stable.MAX_EPOCH_BYTES, "saved_pin_refused")
    need(value["pins"]["complete.json"]["sha256"] == complete_sha256, "saved_complete_anchor_refused")
    # Only after the external complete anchor is checked do saved semantics
    # enter the legacy validator. Its raw cross-links remain binding.
    _json_types(value)
    _storage(value["storage_identity"])
    complete = value["controls"]["complete.json"]
    _storage(complete["storage_identity"])
    need(_same(value["storage_identity"], complete["storage_identity"]), "saved_storage_refused")
    _shape(complete["published_leaf_pins"], set(OUTPUT_NAMES) - {"complete.json"})
    for name, pin in complete["published_leaf_pins"].items():
        _pin(pin)
        need(_same(pin, value["pins"][name]), "saved_pin_refused")
    reservation = value["controls"]["reservation.json"]
    need(_same(reservation["code_identity"], original), "saved_original_anchor_refused")
    prior.validate_readback(value, original, complete_sha256)
    if not fixture:
        need(value["pins"]["transition.json"]["sha256"] == TRANSITION_SHA256
             and value["pins"]["dossier.json"]["sha256"] == DOSSIER_SHA256
             and complete["audit_summary"]["result_sha256"] == REFERENCE_AUDIT_SHA256,
             "saved_complete_anchor_refused")
    result = _summary(value, original, reader, complete_sha256, fixture=fixture)
    return validate_summary(result, original_identity=original, reader_identity=reader,
                            fixture_only=fixture, complete_sha256=complete_sha256)


def validate_saved(value, *, original_identity, reader_identity):
    """Validate ONLY the externally pinned actual five-leaf saved operation."""
    try:
        return _validate(value, original_identity=original_identity, reader_identity=reader_identity,
                         complete_sha256=COMPLETE_SHA256, fixture=False)
    except SavedReadbackError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        raise SavedReadbackError("saved_readback_refused") from None


def validate_invented(value, *, original_identity, reader_identity, complete_sha256):
    """Toy contract validation only; never emits an actual/false-fixture result."""
    try:
        return _validate(value, original_identity=original_identity, reader_identity=reader_identity,
                         complete_sha256=complete_sha256, fixture=True)
    except SavedReadbackError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        raise SavedReadbackError("saved_readback_refused") from None


def validate_summary(value, *, original_identity, reader_identity, fixture_only=False,
                     complete_sha256=COMPLETE_SHA256):
    """Strict detached IPC result check; native caller authenticates its worker."""
    need(type(fixture_only) is bool and type(complete_sha256) is str and _SHA.fullmatch(complete_sha256),
         "saved_arguments_refused")
    original, reader = _identities(original_identity, reader_identity, fixture=fixture_only)
    keys = {"schema", "completed", "fixture_only", "saved_receipt_contract_validated",
        "original_execution_head", "original_source_inventory_sha256", "reader_execution_head",
        "reader_source_inventory_sha256", "complete_sha256", "transition_sha256", "dossier_sha256",
        "reference_audit_sha256", "leaf_count", "original_input_leaves_replayed", "historical_evidence_gates_closed",
        "historical_storage_identity_reauthenticated", "full_historical_environment_replayed", "counts", "authority"}
    _shape(value, keys, "saved_summary_refused")
    need(value["schema"] == SCHEMA + "/summary" and value["completed"] is True
         and value["fixture_only"] is fixture_only and value["saved_receipt_contract_validated"] is True,
         "saved_summary_refused")
    need(value["original_execution_head"] == original["head"]
         and value["original_source_inventory_sha256"] == original["source_inventory_sha256"]
         and value["reader_execution_head"] == reader["head"]
         and value["reader_source_inventory_sha256"] == reader["source_inventory_sha256"], "saved_summary_refused")
    for key in ("complete_sha256", "transition_sha256", "dossier_sha256", "reference_audit_sha256"):
        need(type(value[key]) is str and _SHA.fullmatch(value[key]), "saved_summary_refused")
    need(value["complete_sha256"] == complete_sha256, "saved_summary_refused")
    for key, expected in (("leaf_count", 5), ("original_input_leaves_replayed", 0), ("historical_evidence_gates_closed", 0)):
        need(type(value[key]) is int and value[key] == expected, "saved_summary_refused")
    need(value["historical_storage_identity_reauthenticated"] is False
         and value["full_historical_environment_replayed"] is False
         and _same(value["authority"], prior.transition.authority()), "saved_summary_refused")
    _shape(value["counts"], _COUNT_KEYS, "saved_summary_refused")
    need(all(type(n) is int and 0 <= n <= 1_000_000 for n in value["counts"].values()), "saved_summary_refused")
    need(value["counts"]["controls"] == value["counts"]["originals_reparsed"] == 12, "saved_summary_refused")
    if not fixture_only:
        need(complete_sha256 == COMPLETE_SHA256 and value["transition_sha256"] == TRANSITION_SHA256
             and value["dossier_sha256"] == DOSSIER_SHA256
             and value["reference_audit_sha256"] == REFERENCE_AUDIT_SHA256
             and _same(value["counts"], ACTUAL_COUNTS), "saved_summary_refused")
    return _copy(value)
