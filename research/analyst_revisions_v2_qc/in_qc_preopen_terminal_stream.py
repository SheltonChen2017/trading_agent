"""Stream pre-open terminals cloud-locally without a host Object Store export.

QuantConnect permits a running algorithm to read its organization/project
Object Store even when the account cannot export those objects through the
host API.  This module authenticates the content-addressed pre-open terminal
shards and delivers the exact logical ``(session, security)`` stream to one
in-process consumer.  It neither writes a host archive nor asserts that the
downstream physical scorer or frozen formal evaluator has run.

The input symbol resolution must be the explicitly owner-accepted, non-PIT
runtime result.  A security whose ticker failed runtime resolution may appear
only as a named-refusal pre-open terminal.  An accepted terminal for such a
security is a hard error.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import heapq
import io
import json
import os
import re
import threading
import weakref
from collections.abc import Callable
from datetime import date
from itertools import groupby

try:  # QuantConnect projects are projected as a flat source directory.
    from accepted_risk_qc_symbol_resolution import (
        AcceptedRiskQcSymbolResolution,
        require_accepted_risk_qc_symbol_resolution,
    )
    from preopen_terminal_semantics import validate_preopen_terminal_semantics
except ImportError:  # Host tests import through the repository package.
    from research.analyst_revisions_v2_qc.accepted_risk_qc_symbol_resolution import (
        AcceptedRiskQcSymbolResolution,
        require_accepted_risk_qc_symbol_resolution,
    )
    from research.analyst_revisions_v2_qc.preopen_terminal_semantics import (
        validate_preopen_terminal_semantics,
    )


class InQcPreopenTerminalStreamError(ValueError):
    """The cloud-local pre-open stream cannot be authenticated."""


RECEIPT_SCHEMA = "arv2-owner-accepted-risk-in-qc-preopen-terminal-stream-v1"
MANIFEST_BINDING_SCHEMA = (
    "arv2-owner-accepted-risk-in-qc-preopen-output-manifest-binding-v1"
)
OUTPUT_MANIFEST_SCHEMA = "arv2-preopen-control-output-manifest-v1"
OUTPUT_SHARD_SCHEMA = "arv2-preopen-control-output-shard-v1"
OUTPUT_ROW_SCHEMA = "arv2-preopen-control-terminal-v1"
UNIVERSE_SESSION_SCHEMA = "arv2-preopen-control-universe-session-commitment-v1"
CONTROL_SESSION_SCHEMA = "arv2-preopen-control-session-commitment-v1"
MAX_SHARD_COUNT = 20_000
MAX_OUTPUT_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ONE_COMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ONE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ONE_TERMINAL_BYTES = 64 * 1024
MAX_LOGICAL_MERGE_COMPRESSED_BYTES = 128 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_#\-$= ]*\.[A-Za-z0-9]+\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_DESCRIPTOR_FIELDS = {
    "schema",
    "role",
    "ordinal",
    "decision_chunk_ordinal",
    "security_batch_ordinal",
    "partition_first_session",
    "partition_last_session",
    "first_security_id",
    "last_security_id",
    "object_store_key",
    "compression",
    "encoding",
    "row_schema",
    "compressed_sha256",
    "compressed_byte_count",
    "uncompressed_sha256",
    "uncompressed_byte_count",
    "row_count",
}
_TERMINAL_FIELDS = {
    "schema",
    "decision_session",
    "security_id",
    "qc_security_id",
    "issuer_id",
    "share_class_id",
    "listing_id",
    "security_master_row_sha256",
    "disposition",
    "detail_reason",
    "eligible_security_session",
    "q_data_measurement",
    "census_refusal",
    "input_roots",
    "terminal_sha256",
}
_MANIFEST_FIELDS = {
    "schema", "contract_id", "contract_sha256", "input_manifest",
    "eligible_universe_source", "qc_sid_mapping_source", "source_policy",
    "construction_resource_census", "run_authority", "input_role_bindings",
    "truth_source_bindings", "input_source_inventory_sha256",
    "project_source_set_sha256", "construction_intermediates", "output_shards",
    "output_shard_inventory_sha256", "universe_sessions", "control_sessions",
    "universe_terminal_projection_sha256", "control_terminal_projection_sha256",
    "census", "capabilities",
}
_CENSUS_FIELDS = {
    "universe_terminal_count", "control_accepted_count", "control_refusal_count",
    "control_terminal_count",
}
_INTERMEDIATE_FIELDS = {
    "schema", "peer_aggregate_record_count", "peer_aggregate_projection_sha256",
    "market_session_commitment_count", "market_session_projection_sha256",
    "physical_terminal_shard_count", "logical_terminal_order",
    "q_data_measurement_count", "q_data_measurement_projection_sha256",
}
_CAPABILITY_FIELDS = {
    "provider_access", "credential_access", "filesystem_access",
    "quantconnect_access", "object_store_access", "price_access",
    "outcome_access", "result_access", "deployment", "orders", "trading",
}
_UNIVERSE_SESSION_FIELDS = {
    "schema", "decision_session", "accepted_count", "refusal_count",
    "terminal_count", "terminal_merkle_root",
}
_CONTROL_SESSION_FIELDS = {
    *_UNIVERSE_SESSION_FIELDS,
    "market_observation_count", "market_observation_sha256",
}


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open value is not canonical JSON"
        ) from exc


def _strict_row(line: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[object, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open row has duplicate or non-string keys"
                )
            result[key] = value
        return result

    try:
        row = json.loads(
            line.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                InQcPreopenTerminalStreamError(
                    "cloud-local pre-open row contains a binary float"
                )
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                InQcPreopenTerminalStreamError(
                    "cloud-local pre-open row contains a non-finite value"
                )
            ),
        )
    except InQcPreopenTerminalStreamError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open row is not strict JSON"
        ) from exc
    if (
        type(row) is not dict
        or set(row) != _TERMINAL_FIELDS
        or row.get("schema") != OUTPUT_ROW_SCHEMA
        or _canonical(row) != line
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open row is not exact canonical terminal schema"
        )
    semantic = dict(row)
    declared = semantic.pop("terminal_sha256")
    if (
        type(declared) is not str
        or _HEX.fullmatch(declared) is None
        or hashlib.sha256(_canonical(semantic)).hexdigest() != declared
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open terminal content hash changed"
        )
    return row


def _strict_object(payload: object, name: str) -> dict[str, object]:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_OUTPUT_MANIFEST_BYTES
    ):
        raise InQcPreopenTerminalStreamError(
            f"cloud-local pre-open {name} bytes changed or exceed capacity"
        )

    def pairs(items: list[tuple[object, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise InQcPreopenTerminalStreamError(
                    f"cloud-local pre-open {name} has duplicate or non-string keys"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                InQcPreopenTerminalStreamError(
                    f"cloud-local pre-open {name} contains a binary float"
                )
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                InQcPreopenTerminalStreamError(
                    f"cloud-local pre-open {name} contains a non-finite value"
                )
            ),
        )
    except InQcPreopenTerminalStreamError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise InQcPreopenTerminalStreamError(
            f"cloud-local pre-open {name} is not strict JSON"
        ) from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise InQcPreopenTerminalStreamError(
            f"cloud-local pre-open {name} is not canonical JSON"
        )
    return value


def _session(value: object, name: str) -> str:
    if type(value) is not str:
        raise InQcPreopenTerminalStreamError(f"{name} is not a session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InQcPreopenTerminalStreamError(
            f"{name} is not a session date"
        ) from exc
    if parsed.isoformat() != value:
        raise InQcPreopenTerminalStreamError(
            f"{name} is not canonical session text"
        )
    return value


def _identifier(value: object, name: str) -> str:
    if (
        type(value) is not str
        or _IDENTIFIER.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise InQcPreopenTerminalStreamError(f"{name} is not a safe identifier")
    return value


def _validated_descriptor(value: object) -> dict[str, object]:
    if (
        type(value) is not dict
        or set(value) != _DESCRIPTOR_FIELDS
        or value.get("schema") != OUTPUT_SHARD_SCHEMA
        or value.get("role") != "control_terminals"
        or value.get("compression") != "gzip-level9-mtime0"
        or value.get("encoding") != "canonical-json-lines-utf8-lf"
        or value.get("row_schema") != OUTPUT_ROW_SCHEMA
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor schema changed"
        )
    descriptor = dict(value)
    for field in (
        "ordinal",
        "decision_chunk_ordinal",
        "security_batch_ordinal",
        "compressed_byte_count",
        "uncompressed_byte_count",
        "row_count",
    ):
        if type(descriptor[field]) is not int or descriptor[field] < 0:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open descriptor count changed"
            )
    if (
        descriptor["row_count"] < 1
        or not 0 < descriptor["compressed_byte_count"] <= MAX_ONE_COMPRESSED_BYTES
        or not 0 < descriptor["uncompressed_byte_count"] <= MAX_ONE_UNCOMPRESSED_BYTES
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor exceeds a hard capacity"
        )
    for field in ("compressed_sha256", "uncompressed_sha256"):
        if type(descriptor[field]) is not str or _HEX.fullmatch(descriptor[field]) is None:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open descriptor SHA-256 changed"
            )
    key = descriptor["object_store_key"]
    digest = descriptor["compressed_sha256"]
    if (
        type(key) is not str
        or _KEY.fullmatch(key) is None
        or not key.endswith("/" + digest + "-jsonl.gz")
        or ".jsonl.gz" in key
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open Object Store key is not QC-legal and content-derived"
        )
    _session(
        descriptor["partition_first_session"],
        "cloud-local pre-open descriptor first session",
    )
    _session(
        descriptor["partition_last_session"],
        "cloud-local pre-open descriptor last session",
    )
    _identifier(
        descriptor["first_security_id"],
        "cloud-local pre-open descriptor first security",
    )
    _identifier(
        descriptor["last_security_id"],
        "cloud-local pre-open descriptor last security",
    )
    if (
        descriptor["partition_first_session"] > descriptor["partition_last_session"]
        or descriptor["first_security_id"] > descriptor["last_security_id"]
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor boundary is reversed"
        )
    return descriptor


class _Cursor:
    def __init__(self, descriptor: dict[str, object], payload: bytes) -> None:
        if (
            type(payload) is not bytes
            or len(payload) != descriptor["compressed_byte_count"]
            or hashlib.sha256(payload).hexdigest()
            != descriptor["compressed_sha256"]
        ):
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open compressed shard identity changed"
            )
        self.descriptor = descriptor
        self.stream = gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb")
        self.raw_hash = hashlib.sha256()
        self.raw_count = 0
        self.row_count = 0
        self.last_key: tuple[str, str] | None = None
        self.first_session: str | None = None
        self.last_session: str | None = None
        self.first_security: str | None = None
        self.last_security: str | None = None

    def next(self) -> dict[str, object] | None:
        try:
            line = self.stream.readline(MAX_ONE_TERMINAL_BYTES + 1)
        except (EOFError, OSError) as exc:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open shard is not valid gzip"
            ) from exc
        if not line:
            self.stream.close()
            if (
                self.raw_count != self.descriptor["uncompressed_byte_count"]
                or self.raw_hash.hexdigest()
                != self.descriptor["uncompressed_sha256"]
                or self.row_count != self.descriptor["row_count"]
                or self.first_session
                != self.descriptor["partition_first_session"]
                or self.last_session != self.descriptor["partition_last_session"]
                or self.first_security != self.descriptor["first_security_id"]
                or self.last_security != self.descriptor["last_security_id"]
            ):
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open shard terminal census changed"
                )
            return None
        self.raw_count += len(line)
        if self.raw_count > self.descriptor["uncompressed_byte_count"]:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open shard exceeded its uncompressed bound"
            )
        if len(line) > MAX_ONE_TERMINAL_BYTES or not line.endswith(b"\n"):
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open terminal line exceeds its bound or lacks LF"
            )
        self.raw_hash.update(line)
        self.row_count += 1
        row = _strict_row(line)
        session = row.get("decision_session")
        security_id = row.get("security_id")
        _session(session, "cloud-local pre-open terminal decision session")
        _identifier(security_id, "cloud-local pre-open terminal security_id")
        key = (session, security_id)
        if self.last_key is not None and key <= self.last_key:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open shard terminals repeat or reorder"
            )
        self.last_key = key
        self.first_session = self.first_session or session
        self.last_session = session
        self.first_security = (
            security_id if self.first_security is None else min(self.first_security, security_id)
        )
        self.last_security = (
            security_id if self.last_security is None else max(self.last_security, security_id)
        )
        return row


def _commitment_root(records: list[dict[str, object]], domain: str) -> str:
    return hashlib.sha256(
        _canonical({"domain": domain, "records": records})
    ).hexdigest()


def _validated_session_commitments(
    value: object,
    *,
    control: bool,
) -> tuple[dict[str, object], ...]:
    fields = _CONTROL_SESSION_FIELDS if control else _UNIVERSE_SESSION_FIELDS
    schema = CONTROL_SESSION_SCHEMA if control else UNIVERSE_SESSION_SCHEMA
    if type(value) is not list or not value or any(type(item) is not dict for item in value):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest session commitments changed"
        )
    result: list[dict[str, object]] = []
    for item in value:
        row = dict(item)
        if set(row) != fields or row["schema"] != schema:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open output-manifest session commitment schema changed"
            )
        _session(row["decision_session"], "output-manifest decision session")
        for name in ("accepted_count", "refusal_count", "terminal_count"):
            if type(row[name]) is not int or row[name] < 0:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open output-manifest session census changed"
                )
        if row["terminal_count"] != row["accepted_count"] + row["refusal_count"]:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open output-manifest session census changed"
            )
        if type(row["terminal_merkle_root"]) is not str or _HEX.fullmatch(
            row["terminal_merkle_root"]
        ) is None:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open output-manifest session root changed"
            )
        if control:
            if type(row["market_observation_count"]) is not int or row[
                "market_observation_count"
            ] < 0:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open output-manifest market census changed"
                )
            if type(row["market_observation_sha256"]) is not str or _HEX.fullmatch(
                row["market_observation_sha256"]
            ) is None:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open output-manifest market root changed"
                )
        result.append(row)
    if tuple(item["decision_session"] for item in result) != tuple(
        sorted({item["decision_session"] for item in result})
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest session axis repeats or reorders"
        )
    return tuple(result)


def _manifest_projection(
    payload: bytes,
) -> tuple[
    tuple[dict[str, object], ...],
    int,
    int,
    int,
    str,
]:
    manifest = _strict_object(payload, "output manifest")
    if set(manifest) != _MANIFEST_FIELDS or manifest.get("schema") != OUTPUT_MANIFEST_SCHEMA:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest schema changed"
        )
    raw_descriptors = manifest["output_shards"]
    if (
        type(raw_descriptors) is not list
        or not raw_descriptors
        or len(raw_descriptors) > MAX_SHARD_COUNT
        or any(type(item) is not dict for item in raw_descriptors)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest shard inventory changed"
        )
    descriptors = tuple(_validated_descriptor(item) for item in raw_descriptors)
    descriptor_hash = hashlib.sha256(_canonical(list(descriptors))).hexdigest()
    if (
        type(manifest["output_shard_inventory_sha256"]) is not str
        or manifest["output_shard_inventory_sha256"] != descriptor_hash
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest shard inventory hash changed"
        )
    census = manifest["census"]
    if type(census) is not dict or set(census) != _CENSUS_FIELDS:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest census schema changed"
        )
    for name in _CENSUS_FIELDS:
        if type(census[name]) is not int or census[name] < 0:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open output-manifest census changed"
            )
    if (
        census["control_terminal_count"] < 1
        or census["control_terminal_count"]
        != census["control_accepted_count"] + census["control_refusal_count"]
        or census["universe_terminal_count"] != census["control_terminal_count"]
        or census["control_terminal_count"]
        != sum(int(item["row_count"]) for item in descriptors)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest census does not reconcile"
        )
    universe = _validated_session_commitments(
        manifest["universe_sessions"], control=False
    )
    controls = _validated_session_commitments(
        manifest["control_sessions"], control=True
    )
    if (
        tuple(item["decision_session"] for item in universe)
        != tuple(item["decision_session"] for item in controls)
        or sum(int(item["terminal_count"]) for item in universe)
        != census["universe_terminal_count"]
        or sum(int(item["accepted_count"]) for item in controls)
        != census["control_accepted_count"]
        or sum(int(item["refusal_count"]) for item in controls)
        != census["control_refusal_count"]
        or sum(int(item["terminal_count"]) for item in controls)
        != census["control_terminal_count"]
        or manifest["universe_terminal_projection_sha256"]
        != _commitment_root(
            list(universe), "arv2-preopen-universe-session-projection-v1"
        )
        or manifest["control_terminal_projection_sha256"]
        != _commitment_root(
            list(controls), "arv2-preopen-control-session-projection-v1"
        )
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest session commitments do not reconcile"
        )
    intermediates = manifest["construction_intermediates"]
    if (
        type(intermediates) is not dict
        or set(intermediates) != _INTERMEDIATE_FIELDS
        or intermediates.get("schema")
        != "arv2-preopen-control-construction-intermediate-commitment-v1"
        or intermediates.get("logical_terminal_order")
        != "decision_session_then_security_id"
        or type(intermediates.get("physical_terminal_shard_count")) is not int
        or intermediates["physical_terminal_shard_count"] != len(descriptors)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest construction binding changed"
        )
    capabilities = manifest["capabilities"]
    if (
        type(capabilities) is not dict
        or set(capabilities) != _CAPABILITY_FIELDS
        or any(type(item) is not bool for item in capabilities.values())
        or any(capabilities.values())
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest acquired a capability"
        )
    return (
        descriptors,
        int(census["control_terminal_count"]),
        int(census["control_accepted_count"]),
        int(census["control_refusal_count"]),
        descriptor_hash,
    )


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class BoundInQcPreopenOutputManifest:
    """Process-local binding to transport-critical facts in exact manifest bytes."""

    schema: str
    binding_id: str
    binding_sha256: str
    source_output_manifest_sha256: str
    descriptor_inventory_sha256: str
    shard_count: int
    terminal_count: int
    accepted_terminal_count: int
    named_refusal_terminal_count: int
    transport_projection_only: bool
    formal_output_authority: bool
    _manifest_bytes: bytes = dataclasses.field(repr=False)
    _descriptor_bytes: tuple[bytes, ...] = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(type(self))
            if not field.name.startswith("_")
        }


_MANIFEST_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[BoundInQcPreopenOutputManifest], bytes, int]
] = {}
_MANIFEST_AUTHORITY_LOCK = threading.RLock()
_MANIFEST_AUTHORITY_PID = os.getpid()


def _manifest_authority_fingerprint(value: BoundInQcPreopenOutputManifest) -> bytes:
    return _canonical(
        {
            "record": value.to_record(),
            "manifest_sha256": hashlib.sha256(value._manifest_bytes).hexdigest(),
            "descriptor_payload_sha256": hashlib.sha256(
                b"".join(value._descriptor_bytes)
            ).hexdigest(),
            "descriptor_object_ids": [id(item) for item in value._descriptor_bytes],
        }
    )


def _forget_manifest_authority(
    identity: int,
    reference: weakref.ReferenceType[BoundInQcPreopenOutputManifest],
) -> None:
    with _MANIFEST_AUTHORITY_LOCK:
        current = _MANIFEST_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _MANIFEST_AUTHORITIES.pop(identity, None)


def bind_preopen_output_manifest_for_cloud_stream(
    output_manifest_bytes: bytes,
) -> BoundInQcPreopenOutputManifest:
    """Bind exact QC-produced manifest bytes without asserting formal truth."""

    descriptors, terminal_count, accepted, refused, descriptor_hash = (
        _manifest_projection(output_manifest_bytes)
    )
    manifest_hash = hashlib.sha256(output_manifest_bytes).hexdigest()
    seed = {
        "schema": MANIFEST_BINDING_SCHEMA,
        "binding_id": None,
        "binding_sha256": None,
        "source_output_manifest_sha256": manifest_hash,
        "descriptor_inventory_sha256": descriptor_hash,
        "shard_count": len(descriptors),
        "terminal_count": terminal_count,
        "accepted_terminal_count": accepted,
        "named_refusal_terminal_count": refused,
        "transport_projection_only": True,
        "formal_output_authority": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["binding_id"] = "arv2-in-qc-preopen-manifest-" + digest[:24]
    seed["binding_sha256"] = digest
    value = BoundInQcPreopenOutputManifest(
        **seed,
        _manifest_bytes=bytes(output_manifest_bytes),
        _descriptor_bytes=tuple(_canonical(item) for item in descriptors),
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_manifest_authority(key, ref)
    )
    with _MANIFEST_AUTHORITY_LOCK:
        _MANIFEST_AUTHORITIES[identity] = (
            reference,
            _manifest_authority_fingerprint(value),
            os.getpid(),
        )
    return require_bound_preopen_output_manifest(value)


def require_bound_preopen_output_manifest(
    value: BoundInQcPreopenOutputManifest,
) -> BoundInQcPreopenOutputManifest:
    if type(value) is not BoundInQcPreopenOutputManifest:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest binding type changed"
        )
    with _MANIFEST_AUTHORITY_LOCK:
        registered = _MANIFEST_AUTHORITIES.get(id(value))
    if (
        os.getpid() != _MANIFEST_AUTHORITY_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output manifest lacks process-local binding authority"
        )
    if (
        any(
            type(getattr(value, field)) is not str
            for field in (
                "schema", "binding_id", "binding_sha256",
                "source_output_manifest_sha256", "descriptor_inventory_sha256",
            )
        )
        or _HEX.fullmatch(value.binding_sha256) is None
        or _HEX.fullmatch(value.source_output_manifest_sha256) is None
        or _HEX.fullmatch(value.descriptor_inventory_sha256) is None
        or type(value._manifest_bytes) is not bytes
        or type(value._descriptor_bytes) is not tuple
        or any(type(item) is not bytes for item in value._descriptor_bytes)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest binding scalar or container type changed"
        )
    descriptors, terminal_count, accepted, refused, descriptor_hash = (
        _manifest_projection(value._manifest_bytes)
    )
    seed = value.to_record()
    declared_id = seed["binding_id"]
    declared_sha = seed["binding_sha256"]
    seed["binding_id"] = None
    seed["binding_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.schema != MANIFEST_BINDING_SCHEMA
        or type(value.shard_count) is not int
        or type(value.terminal_count) is not int
        or type(value.accepted_terminal_count) is not int
        or type(value.named_refusal_terminal_count) is not int
        or value.transport_projection_only is not True
        or value.formal_output_authority is not False
        or value.source_output_manifest_sha256
        != hashlib.sha256(value._manifest_bytes).hexdigest()
        or value.descriptor_inventory_sha256 != descriptor_hash
        or value.shard_count != len(descriptors)
        or value.terminal_count != terminal_count
        or value.accepted_terminal_count != accepted
        or value.named_refusal_terminal_count != refused
        or value._descriptor_bytes != tuple(_canonical(item) for item in descriptors)
        or declared_sha != digest
        or declared_id != "arv2-in-qc-preopen-manifest-" + digest[:24]
        or registered[1] != _manifest_authority_fingerprint(value)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output-manifest binding changed"
        )
    return value


def _bound_manifest_descriptors(
    value: BoundInQcPreopenOutputManifest,
) -> tuple[dict[str, object], ...]:
    authority = require_bound_preopen_output_manifest(value)
    return tuple(_strict_object(item, "bound output descriptor") for item in authority._descriptor_bytes)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class InQcPreopenTerminalStreamReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    source_output_manifest_sha256: str
    symbol_resolution_sha256: str
    descriptor_inventory_sha256: str
    shard_count: int
    terminal_count: int
    accepted_terminal_count: int
    named_refusal_terminal_count: int
    logical_terminal_chain_sha256: str
    cloud_local_object_store_reads: int
    host_object_store_export_performed: bool
    transport_only: bool
    consumer_effects_attested: bool
    eligible_as_formal_evidence: bool

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


_RECEIPT_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[InQcPreopenTerminalStreamReceipt], bytes, int]
] = {}
_RECEIPT_AUTHORITY_LOCK = threading.RLock()
_RECEIPT_AUTHORITY_PID = os.getpid()


def _receipt_fingerprint(value: InQcPreopenTerminalStreamReceipt) -> bytes:
    return _canonical(value.to_record())


def _forget_receipt(
    identity: int,
    reference: weakref.ReferenceType[InQcPreopenTerminalStreamReceipt],
) -> None:
    with _RECEIPT_AUTHORITY_LOCK:
        current = _RECEIPT_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _RECEIPT_AUTHORITIES.pop(identity, None)


def _register_receipt(
    value: InQcPreopenTerminalStreamReceipt,
) -> InQcPreopenTerminalStreamReceipt:
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_receipt(key, ref)
    )
    with _RECEIPT_AUTHORITY_LOCK:
        _RECEIPT_AUTHORITIES[identity] = (
            reference,
            _receipt_fingerprint(value),
            os.getpid(),
        )
    return value


def _receipt_seed(
    *,
    source_output_manifest_sha256: str,
    resolution_sha256: str,
    descriptor_inventory_sha256: str,
    shard_count: int,
    terminal_count: int,
    accepted_count: int,
    refusal_count: int,
    chain_sha256: str,
) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": None,
        "receipt_sha256": None,
        "source_output_manifest_sha256": source_output_manifest_sha256,
        "symbol_resolution_sha256": resolution_sha256,
        "descriptor_inventory_sha256": descriptor_inventory_sha256,
        "shard_count": shard_count,
        "terminal_count": terminal_count,
        "accepted_terminal_count": accepted_count,
        "named_refusal_terminal_count": refusal_count,
        "logical_terminal_chain_sha256": chain_sha256,
        "cloud_local_object_store_reads": shard_count,
        "host_object_store_export_performed": False,
        "transport_only": True,
        "consumer_effects_attested": False,
        "eligible_as_formal_evidence": False,
    }


def stream_preopen_terminals_cloud_locally(
    *,
    algorithm: object,
    output_manifest: BoundInQcPreopenOutputManifest,
    symbol_resolution: AcceptedRiskQcSymbolResolution,
    consumer: Callable[[dict[str, object]], None],
) -> InQcPreopenTerminalStreamReceipt:
    """Authenticate and consume the logical pre-open stream inside QC.

    The exact inventory and census come only from a process-local binding to
    canonical output-manifest bytes.  Rows delivered to ``consumer`` remain
    provisional until this function returns its authenticated receipt.
    """

    try:
        resolution = require_accepted_risk_qc_symbol_resolution(symbol_resolution)
    except Exception as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open symbol resolution is not authenticated"
        ) from exc
    if (
        resolution.formal_security_master_authority is not False
        or resolution.preliminary_evaluation_eligible is not True
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open accepted-risk boundary changed"
        )
    try:
        manifest = require_bound_preopen_output_manifest(output_manifest)
    except Exception as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output manifest is not authenticated"
        ) from exc
    descriptors = _bound_manifest_descriptors(manifest)
    source_output_manifest_sha256 = manifest.source_output_manifest_sha256
    expected_descriptor_inventory_sha256 = manifest.descriptor_inventory_sha256
    expected_terminal_count = manifest.terminal_count
    expected_accepted_terminal_count = manifest.accepted_terminal_count
    expected_named_refusal_terminal_count = manifest.named_refusal_terminal_count
    if not callable(consumer):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open terminal consumer is not callable"
        )
    try:
        store = getattr(algorithm, "object_store", None)
        read_bytes = getattr(store, "read_bytes", None)
    except Exception as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open Object Store bytes API is unreadable"
        ) from exc
    if not callable(read_bytes):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open Object Store bytes API is unavailable"
        )
    normalized = tuple(_validated_descriptor(item) for item in descriptors)
    descriptor_hash = hashlib.sha256(_canonical(list(normalized))).hexdigest()
    if descriptor_hash != expected_descriptor_inventory_sha256:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor inventory escaped its output manifest"
        )
    expected_order = tuple(
        sorted(
            normalized,
            key=lambda item: (
                item["decision_chunk_ordinal"],
                item["security_batch_ordinal"],
            ),
        )
    )
    if normalized != expected_order or tuple(item["ordinal"] for item in normalized) != tuple(
        range(len(normalized))
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor inventory repeats or reorders"
        )
    partition_keys = [
        (item["decision_chunk_ordinal"], item["security_batch_ordinal"])
        for item in normalized
    ]
    if len(set(partition_keys)) != len(partition_keys):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open descriptor partition repeats"
        )

    resolved_ids = {str(item["security_id"]) for item in resolution.resolved}
    resolution_refusal_ids = {
        str(item["security_id"]) for item in resolution.named_refusals
    }
    resolved_qc_sids = {
        str(item["security_id"]): str(item["qc_security_id"])
        for item in resolution.resolved
    }
    all_input_ids = resolved_ids | resolution_refusal_ids
    seen_ids: set[str] = set()
    accepted = 0
    refused = 0
    count = 0
    previous_global: tuple[str, str] | None = None
    chain = hashlib.sha256(
        _canonical({"domain": "arv2-in-qc-preopen-terminal-chain-v1"})
    ).hexdigest()

    for _chunk, grouped in groupby(
        normalized, key=lambda item: item["decision_chunk_ordinal"]
    ):
        group = tuple(grouped)
        if (
            sum(int(item["compressed_byte_count"]) for item in group)
            > MAX_LOGICAL_MERGE_COMPRESSED_BYTES
        ):
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open logical merge working set exceeds capacity"
            )
        cursors: list[_Cursor] = []
        actual_group_bytes = 0
        for descriptor in group:
            try:
                payload = bytes(read_bytes(descriptor["object_store_key"]))
            except Exception as exc:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open Object Store shard read failed"
                ) from exc
            # Authenticate each payload before retaining the next one.  A
            # dishonest store cannot turn small declared descriptors into a
            # many-object memory spike before the first identity check.
            cursor = _Cursor(descriptor, payload)
            actual_group_bytes += len(payload)
            if actual_group_bytes > MAX_LOGICAL_MERGE_COMPRESSED_BYTES:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open logical merge actual working set exceeds capacity"
                )
            cursors.append(cursor)
        heap: list[tuple[str, str, int, dict[str, object]]] = []
        for index, cursor in enumerate(cursors):
            row = cursor.next()
            if row is not None:
                heapq.heappush(
                    heap,
                    (str(row["decision_session"]), str(row["security_id"]), index, row),
                )
        while heap:
            session, security_id, index, row = heapq.heappop(heap)
            key = (session, security_id)
            if previous_global is not None and key <= previous_global:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local logical pre-open terminals repeat or reorder"
                )
            if security_id not in all_input_ids:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open terminal escaped symbol-resolution authority"
                )
            disposition = row.get("disposition")
            observed_qc_sid = row.get("qc_security_id")
            if (
                security_id in resolved_ids
                and observed_qc_sid != resolved_qc_sids[security_id]
            ):
                raise InQcPreopenTerminalStreamError(
                    "pre-open terminal differs from its runtime QC SecurityIdentifier"
                )
            if disposition == "accepted":
                if security_id not in resolved_ids:
                    raise InQcPreopenTerminalStreamError(
                        "runtime-unresolved security appeared as an accepted pre-open terminal"
                    )
                accepted += 1
            elif disposition == "named_refusal":
                if (
                    security_id in resolution_refusal_ids
                    and observed_qc_sid is not None
                ):
                    raise InQcPreopenTerminalStreamError(
                        "runtime-unresolved pre-open terminal unexpectedly carries a QC SecurityIdentifier"
                    )
                refused += 1
            else:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open terminal disposition changed"
                )
            try:
                validate_preopen_terminal_semantics(row)
            except Exception as exc:
                raise InQcPreopenTerminalStreamError(
                    "cloud-local pre-open terminal semantic schema did not authenticate"
                ) from exc
            record_sha256 = hashlib.sha256(_canonical(row)).hexdigest()
            chain = hashlib.sha256(
                _canonical(
                    {
                        "domain": "arv2-in-qc-preopen-terminal-chain-node-v1",
                        "previous_sha256": chain,
                        "record_sha256": record_sha256,
                    }
                )
            ).hexdigest()
            consumer(_strict_row(_canonical(row)))
            count += 1
            seen_ids.add(security_id)
            previous_global = key
            following = cursors[index].next()
            if following is not None:
                heapq.heappush(
                    heap,
                    (
                        str(following["decision_session"]),
                        str(following["security_id"]),
                        index,
                        following,
                    ),
                )
        # Each cursor is advanced once beyond its final row by the heap loop;
        # that exact transition validates its raw hash and declared census.
    if seen_ids != all_input_ids:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open stream omitted a symbol-resolution terminal"
        )
    if (
        count != expected_terminal_count
        or accepted != expected_accepted_terminal_count
        or refused != expected_named_refusal_terminal_count
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open terminal census escaped its output manifest"
        )
    try:
        require_accepted_risk_qc_symbol_resolution(resolution)
    except Exception as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open symbol resolution changed during consumption"
        ) from exc
    try:
        require_bound_preopen_output_manifest(manifest)
    except Exception as exc:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open output manifest changed during consumption"
        ) from exc
    seed = _receipt_seed(
        source_output_manifest_sha256=source_output_manifest_sha256,
        resolution_sha256=resolution.resolution_sha256,
        descriptor_inventory_sha256=descriptor_hash,
        shard_count=len(normalized),
        terminal_count=count,
        accepted_count=accepted,
        refusal_count=refused,
        chain_sha256=chain,
    )
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["receipt_id"] = "arv2-in-qc-preopen-stream-" + digest[:24]
    seed["receipt_sha256"] = digest
    value = _register_receipt(InQcPreopenTerminalStreamReceipt(**seed))
    return require_in_qc_preopen_terminal_stream_receipt(value)


def require_in_qc_preopen_terminal_stream_receipt(
    value: InQcPreopenTerminalStreamReceipt,
) -> InQcPreopenTerminalStreamReceipt:
    if type(value) is not InQcPreopenTerminalStreamReceipt:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open stream receipt type changed"
        )
    with _RECEIPT_AUTHORITY_LOCK:
        registered = _RECEIPT_AUTHORITIES.get(id(value))
    if (
        os.getpid() != _RECEIPT_AUTHORITY_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open stream receipt lacks process-local stream authority"
        )
    for field in ("schema", "receipt_id", "receipt_sha256"):
        if type(getattr(value, field)) is not str:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open stream receipt identity type changed"
            )
    if _HEX.fullmatch(value.receipt_sha256) is None:
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open stream receipt identity type changed"
        )
    for field in (
        "shard_count",
        "terminal_count",
        "accepted_terminal_count",
        "named_refusal_terminal_count",
        "cloud_local_object_store_reads",
    ):
        observed = getattr(value, field)
        if type(observed) is not int or observed < 0:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open stream receipt count changed"
            )
    for field in (
        "host_object_store_export_performed",
        "transport_only",
        "consumer_effects_attested",
        "eligible_as_formal_evidence",
    ):
        if type(getattr(value, field)) is not bool:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open stream receipt gate type changed"
            )
    for field in (
        "source_output_manifest_sha256",
        "symbol_resolution_sha256",
        "descriptor_inventory_sha256",
        "logical_terminal_chain_sha256",
    ):
        observed = getattr(value, field)
        if type(observed) is not str or _HEX.fullmatch(observed) is None:
            raise InQcPreopenTerminalStreamError(
                "cloud-local pre-open stream receipt SHA-256 changed"
            )
    seed = value.to_record()
    declared_id = seed.pop("receipt_id", None)
    declared_sha = seed.pop("receipt_sha256", None)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.schema != RECEIPT_SCHEMA
        or declared_sha != digest
        or declared_id != "arv2-in-qc-preopen-stream-" + digest[:24]
        or value.terminal_count
        != value.accepted_terminal_count + value.named_refusal_terminal_count
        or value.shard_count < 1
        or value.terminal_count < 1
        or value.cloud_local_object_store_reads != value.shard_count
        or value.host_object_store_export_performed is not False
        or value.transport_only is not True
        or value.consumer_effects_attested is not False
        or value.eligible_as_formal_evidence is not False
        or registered[1] != _receipt_fingerprint(value)
    ):
        raise InQcPreopenTerminalStreamError(
            "cloud-local pre-open stream receipt identity or gates changed"
        )
    return value


__all__ = (
    "BoundInQcPreopenOutputManifest",
    "InQcPreopenTerminalStreamError",
    "InQcPreopenTerminalStreamReceipt",
    "MANIFEST_BINDING_SCHEMA",
    "MAX_LOGICAL_MERGE_COMPRESSED_BYTES",
    "MAX_ONE_COMPRESSED_BYTES",
    "MAX_ONE_TERMINAL_BYTES",
    "MAX_ONE_UNCOMPRESSED_BYTES",
    "MAX_SHARD_COUNT",
    "OUTPUT_ROW_SCHEMA",
    "OUTPUT_SHARD_SCHEMA",
    "RECEIPT_SCHEMA",
    "bind_preopen_output_manifest_for_cloud_stream",
    "require_bound_preopen_output_manifest",
    "require_in_qc_preopen_terminal_stream_receipt",
    "stream_preopen_terminals_cloud_locally",
)
