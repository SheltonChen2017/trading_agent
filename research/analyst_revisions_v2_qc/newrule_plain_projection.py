"""Pure R298 bridge to genuinely plain-data transport and readable source.

The predecessor family and D15 receipt are historical references, never
admission of these new objects. A separately frozen caller must authenticate
and publish the new inventory before any readiness recovery. This builder
does no filesystem, credentials, network, publication or operational work.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import re
import threading
from types import SimpleNamespace
import weakref

from scripts import arv2_r298_recovery_evidence as parent
from . import newrule_comparison_projection as frozen
from . import newrule_plain_transport as transport


SCHEMA = "arv2-r298-plain-projection-v1"
BRIDGE_SCHEMA = "arv2-r298-plain-source-bridge-v1"
NEW_SOURCE_NAMES = ("newrule_plain_transport.py", "newrule_plain_input_runtime.py",
                    "newrule_plain_projection.py")
TEMPLATE_NAME = "accepted_risk_six_universe_order_qc_projection.py"
SOURCE_NAMES = frozenset((*NEW_SOURCE_NAMES, TEMPLATE_NAME))
INPUT_NAME = "accepted_risk_order_level_input_runtime.py"
LOADER_NAME = "newrule_plain_input_runtime.py"
PROFILE_DELTA = frozenset(("package_sha256", "source_pins", "profile_sha256"))
MAIN_KEYWORDS = frozenset(("profile", "activation_manifest_key",
                           "activation_manifest_sha256", "activation_manifest_byte_count"))
FALSE_FLAGS = {"new_storage_admitted": False, "historical_d15_admits_new_objects": False,
    "qc_source_policy_acceptance_proven": False, "backtest_created": False,
    "point_in_time_proven": False, "formal_identity_admitted": False,
    "formal_forward_ready": False, "paper_or_live_ready": False}
_AUTHORITIES = {}
_LOCK = threading.RLock()


class PlainProjectionError(ValueError):
    """Finite projection refusal, never private input or source text."""


def require(condition, code):
    if not condition:
        raise PlainProjectionError(code)


def canonical(value):
    return transport.canonical(value)


def sha(raw):
    require(type(raw) is bytes, "bytes")
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None, "hash")
    return value


def _economic_profile(value):
    require(type(value) is dict and PROFILE_DELTA <= set(value), "profile")
    return {key: item for key, item in value.items() if key not in PROFILE_DELTA}


def _source_binding(sources, expected):
    require(type(sources) is dict and set(sources) == SOURCE_NAMES
        and type(expected) is dict and set(expected) == set(NEW_SOURCE_NAMES), "source_inventory")
    pins = {**expected, TEMPLATE_NAME: parent.SOURCE_PINS[TEMPLATE_NAME]}
    for name, digest in pins.items():
        _hash(digest)
        raw = sources[name]
        require(type(raw) is bytes and 0 < len(raw) <= 100000
            and raw.isascii() and sha(raw) == digest, "source_pin")
    return dict(sorted(expected.items()))


def _loader_shape(raw):
    tree = ast.parse(raw.decode("ascii"))
    forbidden = {"gzip", "zlib", "base64", "marshal", "pickle", "io"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(not {item.name.split(".")[0] for item in node.names} & forbidden, "plain_loader")
        elif isinstance(node, ast.ImportFrom):
            require((node.module or "").split(".")[0] not in forbidden, "plain_loader")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            require(node.func.id not in {"exec", "eval", "compile", "__import__"}, "plain_loader")


def _plain_binding(value):
    value = transport.require_plain_transport(value)
    require(value.source_package_sha256 == parent.PACKAGE
        and value.source_lineage_sha256 == parent.LINEAGE, "parent_input")
    record = value.to_record()
    require(type(record) is dict and canonical(record) + b"\n" == value.record_bytes,
        "transport_canonical")
    proof = record.get("parent_proof")
    require(type(proof) is dict and proof.get("schema") == transport.PROOF_SCHEMA
        and proof.get("source_package_sha256") == parent.PACKAGE
        and proof.get("source_lineage_sha256") == parent.LINEAGE
        and proof.get("source_activation_sha256") == parent.ACTIVATION[1]
        and type(proof.get("source_activation_byte_count")) is int
        and proof["source_activation_byte_count"] == parent.ACTIVATION[2]
        and sha(canonical(proof)) == value.parent_proof_sha256
        == record.get("parent_proof_sha256"), "parent_proof")
    seed = dict(record, package_id=None, package_sha256=None)
    require(record.get("schema") == transport.SCHEMA
        and record.get("source_disposition_sha256") == parent.LINEAGE
        and sha(canonical(seed)) == value.package_sha256 == record.get("package_sha256")
        and value.package_sha256 != parent.PACKAGE
        and value.package_id == record.get("package_id")
        == "arv2-newrule-plain-package-" + value.package_sha256[:24], "transport_identity")
    objects = value.upload_objects
    require(6 <= len(objects) <= transport.MAX_OBJECTS
        and all(item.compression == "identity" for item in objects)
        and canonical(record.get("objects")) == canonical([item.to_record() for item in objects[:-1]])
        and all(item.activation_manifest is False for item in objects[:-1])
        and objects[-1].activation_manifest is True
        and objects[-1].role == "activation_manifest"
        and objects[-1].payload == value.record_bytes, "transport_inventory")
    inventory = []
    for item in objects:
        require(type(item.byte_count) is int and 0 < item.byte_count <= transport.MAX_OBJECT_BYTES
            and type(item.payload) is bytes and item.byte_count == len(item.payload)
            and item.content_sha256 == sha(item.payload)
            and item.object_store_key.startswith(transport.KEY_PREFIX + "/" + value.parent_proof_sha256[:24] + "/")
            and item.object_store_key != parent.ACTIVATION[0], "transport_object")
        inventory.append(item.to_record())
    require(sum(item.byte_count for item in objects) == value.total_upload_byte_count
        and 0 < value.total_upload_byte_count <= transport.MAX_TOTAL_BYTES
        and len({item.object_store_key for item in objects}) == len(objects), "transport_total")
    require(objects[-1].content_sha256 != parent.ACTIVATION[1], "transport_activation")
    return record, inventory


def _main_shape(raw):
    """Mask exactly the four bound literals, never arbitrary source changes."""
    tree = ast.parse(raw.decode("ascii"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "NewruleComparisonDriver"]
    require(len(calls) == 1, "main_call")
    keywords = {item.arg: item for item in calls[0].keywords}
    require(len(keywords) == len(calls[0].keywords) and MAIN_KEYWORDS <= set(keywords), "main_keywords")
    for name in MAIN_KEYWORDS:
        try:
            ast.literal_eval(keywords[name].value)
        except (ValueError, TypeError, SyntaxError):
            raise PlainProjectionError("main_literals") from None
        keywords[name].value = ast.Constant(value="BOUND_" + name)
    return ast.dump(tree, include_attributes=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PlainProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_files: tuple = dataclasses.field(repr=False)
    _transport: object = dataclasses.field(repr=False)

    def to_record(self):
        return require_plain_projection(self)


def _fingerprint(value):
    require(type(value) is PlainProjection and type(value.projection_sha256) is str
        and type(value.record_bytes) is bytes
        and type(value.profile_bytes) is bytes and type(value.source_files) is tuple
        and all(type(item) is frozen.SourceFile and type(item.project_path) is str
                and type(item.source_bytes) is bytes for item in value.source_files), "projection_type")
    return (value.projection_sha256, value.record_bytes, value.profile_bytes, id(value._transport),
            tuple((item.project_path, item.source_bytes) for item in value.source_files))


def _forget(identity, reference):
    with _LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            del _AUTHORITIES[identity]


def require_plain_projection(value, expected_projection_sha256=None):
    fingerprint = _fingerprint(value)
    with _LOCK:
        authority = _AUTHORITIES.get(id(value))
    require(authority is not None and authority[0]() is value
        and authority[1] == fingerprint and authority[2] == os.getpid(), "projection_authority")
    transport.require_plain_transport(value._transport)
    require(value.projection_sha256 == sha(value.record_bytes), "projection_hash")
    if expected_projection_sha256 is not None:
        require(_hash(expected_projection_sha256) == value.projection_sha256, "projection_pin")
    return json.loads(value.record_bytes)


def build_plain_projection(parent_projection, plain_transport, *, sources, expected_new_source_pins):
    """Construct only the existing R298 economic arm with a new transport binding.

    Supplied public source bytes require separately selected external pins.
    There is no auto-refresh, old admission reuse, contact or attempt reset.
    Mapping the new loader to the existing imported filename is explicit in the
    record; its genuinely plain data protocol is not compressed data in disguise.
    """
    parent_record = parent.require_projection(parent_projection)
    new_pins = _source_binding(sources, expected_new_source_pins)
    plain_record, inventory = _plain_binding(plain_transport)
    old_profile = json.loads(parent_projection.profile_bytes)
    require(old_profile["package_sha256"] == parent.PACKAGE
        and old_profile["lineage_sha256"] == parent.LINEAGE
        and old_profile["source_pins"] == parent.SOURCE_PINS
        and old_profile["universe_count"] == 6 and old_profile["ar_percent"] == 0, "parent_profile")
    axis = frozen.october._sessions()
    # The original template uses dict repr: restore its original insertion
    # order with the unchanged builder, not canonical JSON's sorted order.
    rendered_old_profile = frozen.runtime.make_profile(axis,
        package_sha256=parent.PACKAGE, lineage_sha256=parent.LINEAGE,
        universe_count=6, ar_percent=0, source_pins=dict(parent.SOURCE_PINS))
    require(rendered_old_profile == old_profile, "parent_profile")
    pins = {**parent.SOURCE_PINS, **new_pins}
    profile = frozen.runtime.make_profile(axis,
        package_sha256=plain_transport.package_sha256, lineage_sha256=parent.LINEAGE,
        universe_count=6, ar_percent=0, source_pins=pins)
    require(_economic_profile(profile) == _economic_profile(old_profile), "economic_profile_changed")
    old_files = {item.project_path: item.source_bytes for item in parent_projection.source_files}
    old_activation = SimpleNamespace(object_store_key=parent.ACTIVATION[0],
        content_sha256=parent.ACTIVATION[1], byte_count=parent.ACTIVATION[2])
    original_main = frozen.normalize(frozen.main_source(rendered_old_profile, old_activation,
        sources[TEMPLATE_NAME]), "main.py")
    require(original_main == old_files["main.py"], "parent_main_template")
    activation = plain_transport.upload_objects[-1]
    next_main = frozen.normalize(frozen.main_source(profile, activation,
        sources[TEMPLATE_NAME]), "main.py")
    require(_main_shape(original_main) == _main_shape(next_main), "main_semantics_changed")
    loader = frozen.normalize(sources[LOADER_NAME], INPUT_NAME)
    _loader_shape(loader)
    for name, raw in ((INPUT_NAME, loader), ("main.py", next_main)):
        frozen.audit(name, raw)
    files = tuple(frozen.SourceFile(name, loader if name == INPUT_NAME else
        next_main if name == "main.py" else old_files[name]) for name in parent.FILE_NAMES)
    unchanged = tuple(name for name in parent.FILE_NAMES if name not in (INPUT_NAME, "main.py"))
    require(len(unchanged) == 9 and all(item.source_bytes == old_files[item.project_path]
        for item in files if item.project_path in unchanged), "unchanged_sources")
    require(sum(item.byte_count for item in files) <= 448 * 1024, "source_total")
    bridge = {"schema": BRIDGE_SCHEMA, "parent_family_sha256": parent.FAMILY,
        "parent_projection_sha256": parent.PROJECTION, "parent_profile_sha256": parent.PROFILE,
        "historical_d15_admission_sha256": parent.ADMISSION,
        "parent_package_sha256": parent.PACKAGE, "lineage_sha256": parent.LINEAGE,
        "parent_activation_sha256": parent.ACTIVATION[1],
        "plain_transport_sha256": plain_transport.package_sha256,
        "parent_proof_sha256": plain_transport.parent_proof_sha256,
        "economic_profile_sha256": sha(canonical(_economic_profile(profile))),
        "source_mapping": {INPUT_NAME: LOADER_NAME}, "new_source_pins": new_pins,
        "unchanged_cloud_files": list(unchanged),
        "allowed_profile_fields": sorted(PROFILE_DELTA),
        "allowed_main_literal_keywords": sorted(MAIN_KEYWORDS), **FALSE_FLAGS}
    record = {"schema": SCHEMA, "candidate_id": "R298", "economic_candidate_id": profile["candidate_id"],
        "profile_sha256": profile["profile_sha256"], "package_sha256": plain_transport.package_sha256,
        "lineage_sha256": parent.LINEAGE, "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256, "activation_manifest_byte_count": activation.byte_count,
        "upload_inventory": inventory, "upload_inventory_sha256": sha(canonical(inventory)),
        "total_upload_byte_count": plain_transport.total_upload_byte_count,
        "source_files": [item.to_record() for item in files],
        "bridge": bridge, "bridge_sha256": sha(canonical(bridge)), **FALSE_FLAGS}
    raw = canonical(record)
    require(len(raw) <= 512 * 1024, "record_bound")
    value = PlainProjection(sha(raw), raw, canonical(profile), files, plain_transport)
    identity = id(value)
    reference = weakref.ref(value, lambda ref: _forget(identity, ref))
    with _LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(value), os.getpid())
    require_plain_projection(value)
    return value
