"""Pure contract for a new present-storage observation, not historical repair.

The native caller must authenticate every fixed input before this factory is
called and qualify the current held filesystem independently. A device-only
difference permits this separate descriptive contract; it never makes the old
physical binding pass or establishes continuous historical custody.
"""
from __future__ import annotations

import hashlib
import json
import re
import weakref

SCHEMA = "insider-pilot-current-storage-transition-v1"
STORAGE_SCHEMA = "insider-pilot-stable-private-custody-v2/storage-identity"
_FIELDS = frozenset({"schema", "root_kind", "device", "inode", "mode", "owner", "group"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE = re.compile(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_][A-Za-z0-9_.-]*\.py\Z")
_PINS = (
    ("provider_complete", 70190, "f52646ad80a2a7497f9eb56d471987d8041ac744600b194e5e9ea99c6684a552"),
    ("proof_complete", 23187, "e801524572f54c9c7415798386b5c579f66b35fcc46eb7a9b9e57aa977ad81b3"),
    ("reference_complete", 7985, "07dd203d82c3d90f90e1af239b8ef2255ecba47400595d6f415a65989ee29f97"),
    ("tickers_projection", 29841795, "da2bf31da6436127dd405154b339d1a31ad6c14a788d0017ce620ad5217aea60"),
    ("actions_projection", 116139300, "27387a32fffe710e7733b8f8b225250fc92ad3d829d720efc77df77a015c5246"),
    ("provider_controls", 18297, "c48c892c83ac241246663cbeb2e5c68199342e4063899a22c50cbe2b9f69b658"),
    ("provider_storage", 1145, "2335d59e1cfa5961139d37950633951e9c3921f344a2a005355599edec908f5d"),
)
_RESULTS = weakref.WeakKeyDictionary()


class StorageTransitionError(ValueError):
    """Finite own refusal only; never expose supplied records or values."""


def _need(ok, code):
    if not ok:
        raise StorageTransitionError(code)


def _raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise StorageTransitionError("input_refused") from None


def expected_input_pins():
    """A detached copy; caller mutation cannot alter the fixed input contract."""
    return {name: {"bytes": size, "sha256": digest} for name, size, digest in _PINS}


def authority():
    return {"source_authenticated": False, "historical_public_known_by_verified": False,
            "historical_identity_verified": False, "point_in_time_data": False,
            "rights_verified": False, "canonical_admitted": False,
            "full_population_complete": False, "backtesting_ready": False,
            "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def _storage(value):
    _need(type(value) is dict and set(value) == _FIELDS, "storage_shape_refused")
    _need(value["schema"] == STORAGE_SCHEMA and type(value["schema"]) is str
          and value["root_kind"] == "fixed_user_application_support"
          and type(value["root_kind"]) is str, "storage_shape_refused")
    _need(all(type(value[key]) is int and value[key] >= 0
              for key in ("device", "inode", "mode", "owner", "group"))
          and value["inode"] > 0 and value["mode"] == 0o700, "storage_shape_refused")
    return dict(value)


def _pins(value):
    expected = expected_input_pins()
    _need(type(value) is dict and set(value) == set(expected), "input_pins_refused")
    for name, pin in value.items():
        _need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
              and type(pin["bytes"]) is int and type(pin["sha256"]) is str
              and pin == expected[name], "input_pins_refused")
    return expected


def _execution(value):
    _need(type(value) is dict and set(value) == {"head", "sources", "source_inventory_sha256"},
          "execution_identity_refused")
    _need(type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["head"])
          and type(value["sources"]) is dict and 0 < len(value["sources"]) <= 1024,
          "execution_identity_refused")
    sources = value["sources"]
    for name, digest in sources.items():
        _need(type(name) is str and len(name) <= 512 and _SOURCE.fullmatch(name)
              and name.split("/", 1)[0] != "artifacts" and type(digest) is str
              and _SHA.fullmatch(digest), "execution_identity_refused")
    encoded = _raw(sources)
    _need(len(encoded) <= 256 * 1024
          and type(value["source_inventory_sha256"]) is str
          and value["source_inventory_sha256"] == hashlib.sha256(encoded).hexdigest(),
          "execution_identity_refused")
    return {"head": value["head"], "sources": dict(sources),
            "source_inventory_sha256": value["source_inventory_sha256"]}


class TransitionReceipt:
    """Factory-only immutable bytes; each payload is a detached mutable copy."""
    __slots__ = ("_body", "__weakref__")

    def __new__(cls, *_args, **_kwargs):
        raise StorageTransitionError("genuine_transition_required")

    def __setattr__(self, _name, _value):
        raise AttributeError("immutable transition receipt")

    @property
    def raw(self):
        body = _RESULTS.get(self)
        _need(type(body) is bytes and getattr(self, "_body", None) == body,
              "genuine_transition_required")
        return body

    @property
    def sha256(self):
        return hashlib.sha256(self.raw).hexdigest()

    def to_payload(self):
        return json.loads(self.raw)


def build_transition(physical, proof, qualification, input_pins, execution_identity, *, fixture_only=True):
    """Validate a narrow successor observation, never authenticate bytes itself.

    Full historical receipts may contain unrelated externally authenticated
    fields. Only their finite identity/actual-pass/receipt-link snapshots enter
    this new receipt. Native filesystem and byte checks remain the caller's job.
    """
    _need(type(fixture_only) is bool, "fixture_flag_refused")
    current = _storage(physical)
    _need(type(proof) is dict and type(qualification) is dict, "historical_proof_refused")
    _need(proof.get("passed") is qualification.get("passed") is True
          and proof.get("fixture_only") is qualification.get("fixture_only") is False,
          "historical_proof_refused")
    previous = _storage(proof.get("storage_identity"))
    qualified = _storage(qualification.get("storage_identity"))
    _need(previous == qualified, "historical_proof_conflict")
    pins = _pins(input_pins)
    _need(type(qualification.get("receipt_sha256")) is str
          and qualification["receipt_sha256"] == pins["proof_complete"]["sha256"],
          "historical_proof_link_refused")
    _need([key for key in sorted(_FIELDS) if current[key] != previous[key]] == ["device"],
          "device_only_difference_required")
    value = {"schema": SCHEMA, "fixture_only": fixture_only, "contract_validated": True,
             "current_byte_equivalence_only": True, "input_bytes_authenticated_by_factory": False,
             "historical_physical_continuity_established": False, "historical_binding_passed": False,
             "current_storage_identity": current, "historical_storage_identity": previous,
             "historical_changed_fields": ["device"], "input_pins": pins,
             "execution_identity": _execution(execution_identity), "authority": authority()}
    body = _raw(value)
    _need(len(body) <= 512 * 1024, "output_refused")
    result = object.__new__(TransitionReceipt)
    object.__setattr__(result, "_body", body)
    _RESULTS[result] = body
    return result


def validate_payload(value, *, execution_identity=None):
    """Validate a detached IPC/readback contract; this is not byte authentication.

    Rebuilding preserves the in-process factory seal rather than treating a
    deserialized dict as a genuine receipt object. The external caller still
    authenticates persisted bytes and the live held filesystem independently.
    """
    keys = {"schema", "fixture_only", "contract_validated", "current_byte_equivalence_only",
            "input_bytes_authenticated_by_factory", "historical_physical_continuity_established",
            "historical_binding_passed", "current_storage_identity", "historical_storage_identity",
            "historical_changed_fields", "input_pins", "execution_identity", "authority"}
    _need(type(value) is dict and set(value) == keys, "payload_refused")
    _need(type(value["schema"]) is str and value["schema"] == SCHEMA,
          "payload_refused")
    _need(type(value["historical_changed_fields"]) is list
          and value["historical_changed_fields"] == ["device"], "payload_refused")
    for name, expected in (("contract_validated", True), ("current_byte_equivalence_only", True),
            ("input_bytes_authenticated_by_factory", False),
            ("historical_physical_continuity_established", False), ("historical_binding_passed", False)):
        _need(value[name] is expected, "payload_refused")
    expected_authority = authority()
    _need(type(value["authority"]) is dict and set(value["authority"]) == set(expected_authority)
          and all(type(value["authority"][name]) is type(expected)
                  and value["authority"][name] == expected for name, expected in expected_authority.items()),
          "payload_refused")
    proof = {"passed": True, "fixture_only": False,
             "storage_identity": value["historical_storage_identity"]}
    qualification = {**proof, "receipt_sha256": expected_input_pins()["proof_complete"]["sha256"]}
    rebuilt = build_transition(value["current_storage_identity"], proof, qualification,
        value["input_pins"], value["execution_identity"], fixture_only=value["fixture_only"])
    _need(_raw(value) == rebuilt.raw, "payload_refused")
    if execution_identity is not None:
        _need(_raw(_execution(execution_identity)) == _raw(value["execution_identity"]),
              "execution_identity_refused")
    return rebuilt.to_payload()
