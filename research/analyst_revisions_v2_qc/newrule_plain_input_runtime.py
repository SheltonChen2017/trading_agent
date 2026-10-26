"""Authenticate plain JSON/JSONL research data from QC Object Store.

This separately versioned loader reads no encoded executable source. Its
inputs are genuinely uncompressed canonical data, not renamed compressed
objects. The new transport has its own content-derived identity and an
explicit parent proof; it never reports the old transport as the bytes read.
Only the package loader and bounded collection helper used by the new-rule
driver are included. No order, network, write or dynamic-import capability
is introduced. A pinned activation descriptor is required from the caller.
"""

import dataclasses
import hashlib
import itertools
import json
import re

try:
    import accepted_risk_preliminary_rating_evaluator as evaluator
except ImportError:
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_rating_evaluator as evaluator


class AcceptedRiskOrderLevelInputRuntimeError(ValueError):
    """The plain transport or its authenticated input changed shape."""


TRANSPORT_MANIFEST_SCHEMA = "arv2-newrule-plain-transport-v1"
UPLOAD_OBJECT_SCHEMA = "arv2-newrule-plain-upload-object-v1"
PARENT_PROOF_SCHEMA = "arv2-newrule-plain-parent-proof-v1"
BENCHMARK_SECURITY_ID = "arv2-benchmark-SPY"
BENCHMARK_TICKER = "SPY"
MAX_UPLOAD_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 44 * 1024 * 1024
MAX_PLAIN_SHARD_BYTES = 16 * 1024 * 1024
MAX_TRANSPORT_OBJECT_COUNT = 95
MAX_COLLECTION_ROWS = 25_000
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 2_000_000
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,1023}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_/-]*/[A-Za-z0-9_-]+\.[A-Za-z0-9]+\Z")
_ROLE_ORDER = ("evaluator_manifest", "session_axis", "memberships", "contributions", "runtime_symbol_bindings")
_OBJECT_FIELDS = {"schema", "role", "ordinal", "object_store_key", "relative_path",
    "byte_count", "content_sha256", "record_count", "compression", "activation_manifest"}
_TRANSPORT_FIELDS = {"schema", "package_id", "package_sha256", "evaluator_manifest_id",
    "evaluator_manifest_sha256", "benchmark", "source_disposition_sha256",
    "runtime_symbol_binding_count", "runtime_symbol_bindings_sha256", "contribution_census",
    "objects", "runtime", "claims", "parent_proof", "parent_proof_sha256"}
_PARENT_FIELDS = {"schema", "source_package_sha256", "source_lineage_sha256",
    "source_activation_sha256", "source_activation_byte_count", "source_inventory_sha256", "streams"}
_STREAM_FIELDS = {"role", "ordinal", "record_count", "byte_count", "content_sha256"}
_EXPECTED_RUNTIME = {
    "input_loading": "QC_ObjectStore_cloud_to_cloud_no_host_export",
    "security_resolution": "composite_figi_exact_roundtrip_ticker_diagnostic_only",
    "history": "bounded_total_return_adjusted_open_batches",
    "progress": "one_bounded_work_unit_per_callback_or_train",
    "result_transport": "aggregate_only_custom_summary_statistics",
}
_EXPECTED_CLAIMS = {
    "preliminary": True, "current_snapshot_security_and_sector": True, "uniform_q_data": True,
    "point_in_time": False, "formal": False, "control_residualized": False,
    "terminal_payoff_complete": False, "economic_portfolio": False, "etf_or_leverage": False,
    "deployment": False, "orders": False, "trading": False,
}


def _error(message):
    raise AcceptedRiskOrderLevelInputRuntimeError(message)


def _canonical(value):
    try:
        pending = [(value, 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
                _error("plain JSON structure exceeded its bound")
            kind = type(item)
            if kind is dict:
                if any(type(key) is not str for key in item):
                    _error("plain JSON object key is not exact text")
                pending.extend((child, depth + 1) for child in item.values())
            elif kind is list:
                pending.extend((child, depth + 1) for child in item)
            elif kind not in (type(None), bool, int, float, str):
                _error("plain JSON value has an unsupported type")
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError("plain data is not canonical ASCII JSON") from exc


def _sha(value, name):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(name + " is not lowercase SHA-256")
    return value


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _error("plain JSON has a duplicate or non-string key")
        result[key] = value
    return result


def _constant(_value):
    _error("plain JSON has a non-finite constant")


def _json(payload, name):
    if type(payload) is not bytes:
        _error(name + " is not exact bytes")
    try:
        return json.loads(payload.decode("ascii"), object_pairs_hook=_object_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " is not strict ASCII JSON") from exc


def _stream_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _read_object(store, key, expected_sha256, byte_count):
    if type(key) is not str or _KEY.fullmatch(key) is None or key.rsplit("/", 1)[-1].count(".") != 1:
        _error("plain Object Store key violates portable grammar")
    _sha(expected_sha256, "plain Object Store object")
    if type(byte_count) is not int or not 0 < byte_count <= MAX_UPLOAD_OBJECT_BYTES:
        _error("plain Object Store object bound changed")
    try:
        present = store.contains_key(key)
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError("plain Object Store existence check failed") from exc
    if type(present) is not bool or not present:
        _error("plain Object Store object is unavailable")
    try:
        payload = bytes(store.read_bytes(key))
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError("plain Object Store object read failed") from exc
    if len(payload) != byte_count or hashlib.sha256(payload).hexdigest() != expected_sha256:
        _error("plain Object Store object identity changed")
    return payload


def _descriptor(value):
    if type(value) is not dict or set(value) != _OBJECT_FIELDS or value["schema"] != UPLOAD_OBJECT_SCHEMA:
        _error("plain upload descriptor schema changed")
    role, ordinal = value["role"], value["ordinal"]
    if type(role) is not str or role not in _ROLE_ORDER or type(ordinal) is not int or ordinal < 0:
        _error("plain upload descriptor role or ordinal changed")
    size, count = value["byte_count"], value["record_count"]
    limit = MAX_UPLOAD_OBJECT_BYTES if role == "evaluator_manifest" else MAX_PLAIN_SHARD_BYTES
    if type(size) is not int or not 0 < size <= limit or type(count) is not int or count < 1:
        _error("plain upload descriptor count or bound changed")
    name = "evaluator-manifest.json" if role == "evaluator_manifest" else f"{role}-{ordinal:04d}.jsonl"
    key = value["object_store_key"]
    if (type(key) is not str or _KEY.fullmatch(key) is None or value["relative_path"] != name
            or key.rsplit("/", 1)[-1] != name or (role == "evaluator_manifest" and (ordinal != 0 or count != 1))):
        _error("plain upload descriptor path changed")
    if value["compression"] != "identity" or value["activation_manifest"] is not False:
        _error("plain upload descriptor is not identity data")
    _sha(value["content_sha256"], "plain upload descriptor content")
    return dict(value)


def _validate_transport(value, activation_key, activation_bytes):
    if (type(value) is not dict or set(value) != _TRANSPORT_FIELDS
            or value["schema"] != TRANSPORT_MANIFEST_SCHEMA):
        _error("plain transport schema changed")
    for key in ("package_sha256", "evaluator_manifest_sha256", "source_disposition_sha256",
            "runtime_symbol_bindings_sha256", "parent_proof_sha256"):
        _sha(value[key], "plain " + key)
    manifest_id = value["evaluator_manifest_id"]
    if type(manifest_id) is not str or _SAFE.fullmatch(manifest_id) is None:
        _error("plain evaluator manifest identifier changed")
    if (type(value["runtime_symbol_binding_count"]) is not int
            or not 0 < value["runtime_symbol_binding_count"] <= 100_000):
        _error("plain runtime symbol binding count changed")
    if (_canonical(value["runtime"]) != _canonical(_EXPECTED_RUNTIME)
            or _canonical(value["claims"]) != _canonical(_EXPECTED_CLAIMS)):
        _error("plain runtime or claims changed")
    if value["benchmark"] != {"security_id": BENCHMARK_SECURITY_ID, "ticker": BENCHMARK_TICKER,
            "binding": "QC_US_equity_symbol_resolved_in_process"}:
        _error("plain benchmark binding changed")
    census = value["contribution_census"]
    if type(census) is not dict or any(type(key) is not str or _SAFE.fullmatch(key) is None
            or type(count) is not int or count < 0 for key, count in census.items()):
        _error("plain contribution census changed")
    objects = value["objects"]
    if type(objects) is not list or not 0 < len(objects) <= MAX_TRANSPORT_OBJECT_COUNT:
        _error("plain transport object inventory changed")
    descriptors = tuple(_descriptor(item) for item in objects)
    if (type(activation_bytes) is not int or not 0 < activation_bytes <= MAX_UPLOAD_OBJECT_BYTES
            or activation_bytes + sum(item["byte_count"] for item in descriptors) > MAX_TOTAL_UPLOAD_BYTES):
        _error("plain transport total byte budget changed")
    positions = {role: [] for role in _ROLE_ORDER}
    for item in descriptors:
        positions[item["role"]].append(item["ordinal"])
    if (any(items != list(range(len(items))) for items in positions.values())
            or len(positions["evaluator_manifest"]) != 1 or any(not positions[role] for role in _ROLE_ORDER[1:])):
        _error("plain role ordinal inventory changed")
    if [item["role"] for item in descriptors] != [role for role, items in positions.items() for _ in items]:
        _error("plain role group order changed")
    if len({item["object_store_key"] for item in descriptors}) != len(descriptors):
        _error("plain transport repeats an Object Store key")
    parent = value["parent_proof"]
    if type(parent) is not dict or set(parent) != _PARENT_FIELDS or parent["schema"] != PARENT_PROOF_SCHEMA:
        _error("plain parent proof schema changed")
    for key in ("source_package_sha256", "source_lineage_sha256", "source_activation_sha256", "source_inventory_sha256"):
        _sha(parent[key], "plain parent " + key)
    if (type(parent["source_activation_byte_count"]) is not int
            or not 0 < parent["source_activation_byte_count"] <= MAX_UPLOAD_OBJECT_BYTES
            or parent["source_lineage_sha256"] != value["source_disposition_sha256"]):
        _error("plain parent source binding changed")
    streams = parent["streams"]
    if type(streams) is not list or len(streams) != len(descriptors):
        _error("plain parent stream inventory changed")
    for stream, item in zip(streams, descriptors):
        if (type(stream) is not dict or set(stream) != _STREAM_FIELDS
                or _canonical(stream) != _canonical({key: item[key] for key in _STREAM_FIELDS})):
            _error("plain parent stream identity changed")
    parent_sha = hashlib.sha256(_canonical(parent)).hexdigest()
    prefix = "arv2/newrule-plain-v1/" + parent_sha[:24] + "/"
    if (parent_sha != value["parent_proof_sha256"]
            or activation_key != prefix + "transport-manifest.json"
            or any(item["object_store_key"] != prefix + item["relative_path"] for item in descriptors)):
        _error("plain parent digest or exact key prefix changed")
    seed = dict(value)
    seed["package_id"] = None
    seed["package_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (value["package_sha256"] != digest
            or value["package_id"] != "arv2-newrule-plain-package-" + digest[:24]):
        _error("plain package identity is not content-derived")
    return dict(value), descriptors


def _plain_rows(payload, expected_count, role):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_PLAIN_SHARD_BYTES:
        _error("plain row shard byte bound changed")
    if type(expected_count) is not int or expected_count < 1 or role not in _ROLE_ORDER[1:]:
        _error("plain row shard role or count changed")
    lines = payload.splitlines(keepends=True)
    if len(lines) != expected_count or any(not line.endswith(b"\n") for line in lines):
        _error("plain row shard census changed")
    rows = []
    for line in lines:
        value = _json(line, "plain " + role + " row")
        if type(value) is not dict or _canonical(value) + b"\n" != line:
            _error("plain row is not exact canonical JSON")
        rows.append(value)
    return tuple(rows)


@dataclasses.dataclass(frozen=True)
class LoadedAcceptedRiskPreliminaryPackage:
    package_id: str
    package_sha256: str
    activation_manifest_sha256: str
    evaluator_input: object
    runtime_symbol_bindings: tuple


def load_accepted_risk_preliminary_package(algorithm, *, activation_manifest_key,
        activation_manifest_sha256, activation_manifest_byte_count):
    if algorithm is None:
        _error("plain QC algorithm is unavailable")
    payload = _read_object(algorithm.object_store, activation_manifest_key,
        activation_manifest_sha256, activation_manifest_byte_count)
    transport = _json(payload, "plain activation manifest")
    if _canonical(transport) + b"\n" != payload:
        _error("plain activation manifest is not exact canonical JSON")
    transport, descriptors = _validate_transport(transport, activation_manifest_key, len(payload))
    by_role = {role: [] for role in _ROLE_ORDER}
    for item in descriptors:
        raw = _read_object(algorithm.object_store, item["object_store_key"], item["content_sha256"], item["byte_count"])
        if item["role"] == "evaluator_manifest":
            value = _json(raw, "plain evaluator manifest")
            if type(value) is not dict or _canonical(value) + b"\n" != raw:
                _error("plain evaluator manifest is not exact canonical JSON")
            by_role[item["role"]].append(value)
        else:
            by_role[item["role"]].extend(_plain_rows(raw, item["record_count"], item["role"]))
    manifest = by_role["evaluator_manifest"][0]
    if (manifest.get("manifest_id") != transport["evaluator_manifest_id"]
            or manifest.get("manifest_sha256") != transport["evaluator_manifest_sha256"]):
        _error("plain evaluator manifest identity diverged from transport")
    try:
        loaded = evaluator.load_preliminary_rating_input(manifest, tuple(by_role["session_axis"]),
            tuple(by_role["memberships"]), tuple(by_role["contributions"]))
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError("plain evaluator input did not authenticate") from exc
    bindings = tuple(by_role["runtime_symbol_bindings"])
    if (len(bindings) != transport["runtime_symbol_binding_count"]
            or _stream_hash(bindings) != transport["runtime_symbol_bindings_sha256"]):
        _error("plain runtime symbol binding stream identity changed")
    return LoadedAcceptedRiskPreliminaryPackage(transport["package_id"], transport["package_sha256"],
        activation_manifest_sha256, loaded, bindings)


def collection_rows(rows, name):
    try:
        result = tuple(itertools.islice(iter(rows), MAX_COLLECTION_ROWS + 1))
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " collection is unreadable") from exc
    if len(result) > MAX_COLLECTION_ROWS:
        _error(name + " collection row bound changed")
    return result


__all__ = ("AcceptedRiskOrderLevelInputRuntimeError", "LoadedAcceptedRiskPreliminaryPackage",
    "load_accepted_risk_preliminary_package", "collection_rows")
