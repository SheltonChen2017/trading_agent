"""Prospective-device, object-bound successor; historical policies stay frozen.

Section 279 accepts only device 16777231 instead of 16777232 for the fixed
assessment scope. Every other vintage metadata and opaque-attribute pin stays
unchanged. This is not historical device/security continuity or source admission.
Pins are never learned from observations; endpoint checks are not continuous
stability, hidden-attribute coverage or an interpretation of opaque grants.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import stat
from types import MappingProxyType

from scripts import audit_arv2_relocation as audit
from scripts import arv2_relocation_security as legacy

POLICY_ID = "arv2-relocated-source-security-v3"
HISTORICAL_DEVICE = 16777232
PROSPECTIVE_DEVICE = 16777231
VINTAGE_PATH = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/") / (
    "artifacts/analyst_revisions_v2/sharadar_capture/"
    "arv2-sharadar-source-20260914T003329843989Z")
VINTAGE_METADATA = MappingProxyType({
    "dev": PROSPECTIVE_DEVICE, "ino": 8124879, "mode": 16832, "uid": 501, "gid": 20,
    "nlink": 7, "size": 224, "mtime_ns": 1789346095000000000,
    "ctime_ns": 1791348969446992676, "flags": 32768,
})
XATTR_PINS = (
    (b"com.apple.fileprovider.dir#N", 1,
     "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"),
    (b"com.apple.macl", 72,
     "38b3d95534bbdeb72e84fe595e13501eaff68b0d4fcd615e51fc4e0b1194375a"),
    (b"com.apple.provenance", 11,
     "07ccfbc460d4b2eb75da90b5f2d84baf64b4dbf0059bdc6cd4c93d39d3baa4c7"),
    (b"com.apple.quarantine", 15,
     "c8aeee7d17eb7062492cdd12a92c6e3d471b00dd006fc1174a7dcee37609c18a"),
)
MAX_NAMES_BYTES = legacy.MAX_NAMES_BYTES
MAX_VALUE_BYTES = legacy.MAX_VALUE_BYTES
_FIELDS = ("dev", "ino", "mode", "uid", "gid", "nlink", "size", "mtime_ns",
           "ctime_ns", "flags")


class Refusal(legacy.Refusal):
    """Only bounded codes, never native error text or opaque values."""

    def __init__(self, code):
        if code in {
            "vintage_named_path_unavailable", "vintage_named_metadata_changed",
            "vintage_held_metadata_changed", "vintage_xattr_names_not_exact",
            "prospective_device_not_exact",
            "vintage_xattr_fingerprint_changed",
        }:
            self.code = code
            Exception.__init__(self, code)
        else:
            super().__init__(code)


def policy_record():
    """Return fresh serializable data; caller mutation cannot alter the policy."""
    return {"policy_id": POLICY_ID, "vintage_path": str(VINTAGE_PATH),
            "vintage_metadata": dict(VINTAGE_METADATA),
            "prospective_device_baseline": {
                "historical_device": HISTORICAL_DEVICE,
                "prospective_device": PROSPECTIVE_DEVICE,
                "scope": "all-held-objects-in-fixed-assessment-scope",
                "historical_device_continuity_proven": False,
                "other_metadata_waived": False},
            "xattr_pins": {name.decode("ascii"): {"size": size, "sha256": digest}
                           for name, size, digest in XATTR_PINS},
            "max_names_bytes": MAX_NAMES_BYTES, "max_value_bytes": MAX_VALUE_BYTES,
            "other_objects_policy": "unchanged-provenance-only-v1",
            "continuous_stability_proven": False}


def _metadata(fd):
    return legacy._metadata(fd)


def _pinned_metadata():
    return tuple(VINTAGE_METADATA[field] for field in _FIELDS)


def _check_named_vintage():
    # Reopen every absolute component without following links. Even fallback
    # calls bind the fixed name: replacing the vintage directory cannot turn
    # it into an ordinary provenance-only object and bypass the exact pins.
    try:
        named = audit._open_absolute_directory(VINTAGE_PATH)
    except (OSError, audit.Refusal):
        raise Refusal("vintage_named_path_unavailable") from None
    try:
        metadata = _metadata(named)
        if (type(metadata[0]) is not int or metadata[0] != PROSPECTIVE_DEVICE
                or not stat.S_ISDIR(metadata[2]) or metadata != _pinned_metadata()):
            raise Refusal("vintage_named_metadata_changed")
    finally:
        os.close(named)


def _names(native, fd):
    """Bounded names-only census; this helper grants no admission by itself."""
    buffer = ctypes.create_string_buffer(MAX_NAMES_BYTES)
    count = native.flistxattr(fd, buffer, MAX_NAMES_BYTES, legacy.XATTR_SHOWCOMPRESSION)
    if type(count) is not int or not 0 <= count <= MAX_NAMES_BYTES:
        raise Refusal("accessible xattr name census unavailable or oversized")
    if count == 0:
        return ()
    raw = buffer.raw[:count]
    if not raw.endswith(b"\0"):
        raise Refusal("accessible xattr names are malformed")
    names = raw[:-1].split(b"\0")
    if (any(not name or len(name) > 127 for name in names)
            or len(set(names)) != len(names)):
        raise Refusal("accessible xattr names are malformed")
    return tuple(sorted(names))


def snapshot(fd):
    """Require the exact prospective device, then apply object-bound security.

    Values are read once per call into bounded memory and only fingerprints
    are returned. A caller must invoke this around its fresh-buffer consumer,
    keep all ancestor/held/named checks, and compare the returned snapshots.
    No retry, pin refresh, mutation, output allocation or network operation.
    """
    if type(fd) is not int or fd < 0:
        raise Refusal("valid held descriptor required")
    before = _metadata(fd)
    if type(before[0]) is not int or before[0] != PROSPECTIVE_DEVICE:
        raise Refusal("prospective_device_not_exact")
    _check_named_vintage()
    pinned = _pinned_metadata()
    if before[:2] != pinned[:2]:
        result = legacy.snapshot(fd)
    else:
        if not stat.S_ISDIR(before[2]) or before != pinned:
            raise Refusal("vintage_held_metadata_changed")
        native = legacy._native()
        legacy._require_empty_acl(native, fd)
        names = _names(native, fd)
        if names != tuple(name for name, _size, _digest in XATTR_PINS):
            raise Refusal("vintage_xattr_names_not_exact")
        values, remaining = {}, MAX_VALUE_BYTES
        for name, expected_size, expected_digest in XATTR_PINS:
            buffer = ctypes.create_string_buffer(max(1, remaining))
            count = native.fgetxattr(fd, name, buffer, remaining, 0,
                                    legacy.XATTR_SHOWCOMPRESSION)
            if type(count) is not int or not 0 <= count <= remaining:
                raise Refusal("accessible xattr value unavailable or oversized")
            digest = hashlib.sha256(buffer.raw[:count]).hexdigest()
            if count != expected_size or digest != expected_digest:
                raise Refusal("vintage_xattr_fingerprint_changed")
            values[name.decode("ascii")] = {"size": count, "sha256": digest}
            remaining -= count
        if _names(native, fd) != names:
            raise Refusal("accessible xattr names changed during observation")
        legacy._require_empty_acl(native, fd)
        result = {"acl_empty": True, "xattrs": values, "policy_id": POLICY_ID}
    if _metadata(fd) != before:
        raise Refusal("vintage_held_metadata_changed")
    _check_named_vintage()
    return result
