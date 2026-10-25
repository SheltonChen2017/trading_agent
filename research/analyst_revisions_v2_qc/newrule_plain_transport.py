"""Additive, identity-encoded JSONL DATA transport for the frozen October input.

This host converter authenticates an existing compact package and preserves its
ordered canonical records. It neither acquires data nor writes files, uploads,
changes an old package, or authorizes QC contact. Compression is actually removed
from the new data objects, not renamed or concealed. Service acceptance remains
unproven. New transport identities never masquerade as the predecessor's hash.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import threading
import weakref
import zlib

from . import accepted_risk_preliminary_package as compact


SCHEMA = "arv2-newrule-plain-transport-v1"
OBJECT_SCHEMA = "arv2-newrule-plain-upload-object-v1"
PROOF_SCHEMA = "arv2-newrule-plain-parent-proof-v1"
KEY_PREFIX = "arv2/newrule-plain-v1"
ROLES = ("evaluator_manifest", "session_axis", "memberships", "contributions",
         "runtime_symbol_bindings")
MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 44 * 1024 * 1024
MAX_ROW_SHARD_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 96  # Includes the activation manifest, always last.
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRE_SOURCE = compact.require_accepted_risk_preliminary_package
_ITER_SOURCE = compact.iter_accepted_risk_preliminary_upload_objects
_LOAD_ROWS = compact._load_canonical_gzip_records
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITIES = {}


class PlainTransportError(ValueError):
    """Finite local category; never contains data rows or provider text."""


def _require(condition, code):
    if not condition:
        raise PlainTransportError(code)


def canonical(value):
    """Canonical ASCII JSON without LF, matching the existing data contract."""
    try:
        pending = [(value, 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            _require(depth <= 128 and nodes <= 2_000_000, "json_bound")
            kind = type(item)
            if kind is dict:
                _require(all(type(key) is str for key in item), "json_type")
                _require(nodes + len(pending) + len(item) <= 2_000_000, "json_bound")
                pending.extend((child, depth + 1) for child in item.values())
            elif kind is list:
                _require(nodes + len(pending) + len(item) <= 2_000_000, "json_bound")
                pending.extend((child, depth + 1) for child in item)
            else:
                _require(kind in (type(None), bool, int, float, str), "json_type")
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        if type(error) is PlainTransportError:
            raise
        raise PlainTransportError("json_type") from None


def sha(payload):
    _require(type(payload) is bytes, "payload_type")
    return hashlib.sha256(payload).hexdigest()


def _hash(value):
    _require(type(value) is str and _HEX.fullmatch(value), "hash")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        _require(type(key) is str and key not in result, "json_duplicate")
        result[key] = value
    return result


def _json(payload):
    _require(type(payload) is bytes and 0 < len(payload) <= MAX_OBJECT_BYTES, "payload_bound")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        if type(error) is PlainTransportError:
            raise
        raise PlainTransportError("json") from None
    _require(type(value) is dict and canonical(value) + b"\n" == payload, "canonical")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PlainUploadObject:
    schema: str
    role: str
    ordinal: int
    object_store_key: str
    relative_path: str
    byte_count: int
    content_sha256: str
    record_count: int
    compression: str
    activation_manifest: bool
    payload: bytes = dataclasses.field(repr=False)

    def to_record(self):
        return {field.name: getattr(self, field.name) for field in dataclasses.fields(self)
                if field.name != "payload"}


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PlainTransport:
    package_id: str
    package_sha256: str
    source_package_sha256: str
    source_lineage_sha256: str
    parent_proof_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    upload_objects: tuple[PlainUploadObject, ...] = dataclasses.field(repr=False)
    total_upload_byte_count: int

    @property
    def activation_manifest_key(self):
        return self.upload_objects[-1].object_store_key

    @property
    def activation_manifest_sha256(self):
        return self.upload_objects[-1].content_sha256

    @property
    def activation_manifest_byte_count(self):
        return self.upload_objects[-1].byte_count

    def to_record(self):
        require_plain_transport(self)
        return _json(self.record_bytes)


def _fingerprint(value):
    _require(type(value) is PlainTransport and type(value.upload_objects) is tuple
             and 6 <= len(value.upload_objects) <= MAX_OBJECTS
             and all(type(item) is PlainUploadObject and type(item.payload) is bytes
                     for item in value.upload_objects)
             and type(value.record_bytes) is bytes
             and type(value.total_upload_byte_count) is int
             and all(type(item) is str for item in (value.package_id, value.package_sha256,
                 value.source_package_sha256, value.source_lineage_sha256, value.parent_proof_sha256)),
             "authority")
    return (value.package_id, value.package_sha256, value.source_package_sha256,
            value.source_lineage_sha256, value.parent_proof_sha256, value.record_bytes,
            value.total_upload_byte_count,
            tuple((canonical(item.to_record()), item.payload) for item in value.upload_objects))


def _forget(identity, reference):
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            del _AUTHORITIES[identity]


def _mint(value):
    identity = id(value)
    reference = weakref.ref(value, lambda ref: _forget(identity, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(value), os.getpid())
    return value


def require_plain_transport(value):
    fingerprint = _fingerprint(value)
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    _require(authority is not None and authority[0]() is value
             and authority[1] == fingerprint and authority[2] == os.getpid(), "authority")
    return value


def _convert_payloads(package, pairs):
    """Pure supplied-byte conversion seam. Its result has NO process authority.

    Only build_plain_transport may authenticate the source, exhaust its checked
    iterator and mint the returned capability. This seam performs no I/O.
    """
    _require(type(pairs) is tuple and 6 <= len(pairs) <= MAX_OBJECTS, "inventory")
    _require(all(type(pair) is tuple and len(pair) == 2
                 and type(pair[0]) is compact.PreliminaryUploadObject
                 and type(pair[1]) is bytes for pair in pairs), "inventory")
    descriptors = tuple(pair[0] for pair in pairs)
    _require(descriptors == package.upload_objects, "source_inventory")
    _require(sum(len(raw) for _, raw in pairs) == package.total_upload_byte_count
             and package.total_upload_byte_count <= MAX_TOTAL_BYTES, "source_total")
    for item, raw in pairs:
        compact._require_upload_object(item)
        _require(len(raw) == item.byte_count and sha(raw) == item.content_sha256, "source_payload")
    _require(descriptors[-1].activation_manifest is True
             and not any(item.activation_manifest for item in descriptors[:-1]), "activation_order")
    transport = _json(pairs[-1][1])
    _require(transport.get("schema") == compact.TRANSPORT_MANIFEST_SCHEMA
             and transport.get("package_sha256") == package.package_sha256
             and transport.get("package_id") == package.package_id
             and transport.get("source_disposition_sha256") == package.source_disposition_sha256
             and canonical(transport.get("objects")) == canonical(
                 [item.to_record() for item in descriptors[:-1]]), "source_manifest")
    old_seed = dict(transport, package_id=None, package_sha256=None)
    _require(sha(canonical(old_seed)) == package.package_sha256
             and package.package_id == "arv2-preliminary-qc-package-" + package.package_sha256[:24],
             "source_identity")
    _hash(package.package_sha256)
    _hash(package.source_disposition_sha256)
    binding_count = transport.get("runtime_symbol_binding_count")
    _require(type(binding_count) is int and 0 < binding_count <= 100_000,
             "source_binding_count")
    _hash(transport.get("runtime_symbol_bindings_sha256"))
    _hash(transport.get("evaluator_manifest_sha256"))
    census = transport.get("contribution_census")
    _require(type(census) is dict and all(type(key) is str
             and type(count) is int and count >= 0 for key, count in census.items()),
             "source_census")
    expected_seed = compact._transport_seed(
        package_id=None, package_sha256=None,
        evaluator_manifest={"manifest_id": transport.get("evaluator_manifest_id"),
                            "manifest_sha256": transport.get("evaluator_manifest_sha256")},
        objects=descriptors[:-1], source_disposition_sha256=package.source_disposition_sha256,
        runtime_symbol_binding_count=binding_count,
        runtime_symbol_bindings_sha256=transport["runtime_symbol_bindings_sha256"],
        contribution_census=census)
    _require(canonical(old_seed) == canonical(expected_seed), "source_contract")
    plain = []
    streams = []
    positions = {role: [] for role in ROLES}
    accumulated = 0
    binding_digest = hashlib.sha256()
    observed_binding_count = 0
    for item, raw in pairs[:-1]:
        _require(item.role in ROLES, "role")
        positions[item.role].append(item.ordinal)
        if item.role == "evaluator_manifest":
            manifest = _json(raw)
            _require(item.ordinal == 0 and item.record_count == 1
                     and manifest.get("manifest_id") == transport.get("evaluator_manifest_id")
                     and manifest.get("manifest_sha256") == transport.get("evaluator_manifest_sha256"),
                     "evaluator_manifest")
            payload = raw
            name = "evaluator-manifest.json"
        else:
            try:
                rows, byte_count = _LOAD_ROWS(raw, item)
            except (compact.AcceptedRiskPreliminaryPackageError, zlib.error):
                raise PlainTransportError("source_rows") from None
            payload = b"".join(canonical(row) + b"\n" for row in rows)
            _require(type(byte_count) is int and byte_count == len(payload)
                     and 0 < len(payload) <= MAX_ROW_SHARD_BYTES
                     and len(rows) == item.record_count, "plain_rows")
            name = f"{item.role}-{item.ordinal:04d}.jsonl"
            if item.role == "runtime_symbol_bindings":
                binding_digest.update(payload)
                observed_binding_count += item.record_count
        _require(0 < len(payload) <= MAX_OBJECT_BYTES, "object_bound")
        accumulated += len(payload)
        _require(accumulated <= MAX_TOTAL_BYTES, "total_bound")
        plain.append((item.role, item.ordinal, item.record_count, name, payload))
        streams.append({"role": item.role, "ordinal": item.ordinal,
                        "record_count": item.record_count, "byte_count": len(payload),
                        "content_sha256": sha(payload)})
    _require(positions["evaluator_manifest"] == [0]
             and all(values and values == list(range(len(values))) for values in positions.values())
             and [item.role for item in descriptors[:-1]] ==
             [role for role, values in positions.items() for _ in values], "role_order")
    _require(len({item.object_store_key for item in descriptors}) == len(descriptors)
             and len({item.relative_path for item in descriptors}) == len(descriptors), "source_duplicate")
    _require(observed_binding_count == binding_count
             and binding_digest.hexdigest() == transport["runtime_symbol_bindings_sha256"],
             "source_binding_stream")
    proof = {"schema": PROOF_SCHEMA, "source_package_sha256": package.package_sha256,
             "source_lineage_sha256": package.source_disposition_sha256,
             "source_activation_sha256": descriptors[-1].content_sha256,
             "source_activation_byte_count": descriptors[-1].byte_count,
             "source_inventory_sha256": sha(canonical([item.to_record() for item in descriptors])),
             "streams": streams}
    proof_sha = sha(canonical(proof))
    prefix = KEY_PREFIX + "/" + proof_sha[:24]
    objects = [PlainUploadObject(OBJECT_SCHEMA, role, ordinal, prefix + "/" + name,
        name, len(payload), sha(payload), count, "identity", False, payload)
        for role, ordinal, count, name, payload in plain]
    record = dict(transport, schema=SCHEMA, package_id=None, package_sha256=None,
                  objects=[item.to_record() for item in objects],
                  parent_proof=proof, parent_proof_sha256=proof_sha)
    package_sha = sha(canonical(record))
    package_id = "arv2-newrule-plain-package-" + package_sha[:24]
    record.update(package_id=package_id, package_sha256=package_sha)
    encoded = canonical(record) + b"\n"
    _require(len(encoded) <= MAX_OBJECT_BYTES, "activation_bound")
    objects.append(PlainUploadObject(OBJECT_SCHEMA, "activation_manifest", 0,
        prefix + "/transport-manifest.json", "transport-manifest.json", len(encoded),
        sha(encoded), 1, "identity", True, encoded))
    total = sum(item.byte_count for item in objects)
    _require(total <= MAX_TOTAL_BYTES and len(objects) <= MAX_OBJECTS, "total_bound")
    return PlainTransport(package_id, package_sha, package.package_sha256,
        package.source_disposition_sha256, proof_sha, encoded, tuple(objects), total)


def build_plain_transport(package, *, expected_package_sha256, expected_lineage_sha256):
    """Authenticate the unchanged source package, then convert in memory only.

    Requires a separately authorized private-input read scope before invocation.
    There is no filesystem output, provider call, QC contact or admission mint.
    """
    _hash(expected_package_sha256)
    _hash(expected_lineage_sha256)
    package = _REQUIRE_SOURCE(package)
    _require(package.package_sha256 == expected_package_sha256
             and package.source_disposition_sha256 == expected_lineage_sha256, "parent_pin")
    # Exhaustion also executes the source iterator's final held/named recheck.
    pairs = []
    for pair in _ITER_SOURCE(package):
        _require(len(pairs) < MAX_OBJECTS, "inventory")
        pairs.append(pair)
    pairs = tuple(pairs)
    value = _convert_payloads(package, pairs)
    _REQUIRE_SOURCE(package)
    return require_plain_transport(_mint(value))


def iter_plain_upload_objects(value):
    """Yield retained immutable payloads, activation last; never upload them."""
    value = require_plain_transport(value)
    for item in value.upload_objects:
        require_plain_transport(value)
        yield item, item.payload
    require_plain_transport(value)
