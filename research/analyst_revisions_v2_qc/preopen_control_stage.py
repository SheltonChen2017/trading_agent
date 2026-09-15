"""Offline projection for a separately authorized QC pre-open control run.

This module builds exact input/output shards and two small reviewed project
files.  Its host-only authority loader performs one bounded private-file read;
building a projection performs no I/O.  The projected QC algorithm is limited
to historical observations strictly before each decision open, writes its
content-addressed terminal shards to private Object Store, and publishes only
hashes and counts through custom summary statistics.
"""
from __future__ import annotations

import ast
import dataclasses
import gzip
import hashlib
import io
import json
import os
import re
import stat
import threading
import weakref
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from research.analyst_revisions_v2.preopen_control_acquisition import (
    CONTRACT_ID,
    CONTRACT_SHA256,
    GUIDANCE_CLOCK_POLICY_ID,
    CONTROL_SESSION_COMMITMENT_SCHEMA,
    OUTPUT_MANIFEST_SCHEMA,
    OUTPUT_TERMINAL_SCHEMA,
    UNIVERSE_SESSION_COMMITMENT_SCHEMA,
)


class PreopenControlStageError(ValueError):
    """The offline projection or a content binding is invalid."""


INPUT_MANIFEST_SCHEMA = "arv2-preopen-control-input-manifest-v1"
INPUT_SHARD_SCHEMA = "arv2-preopen-control-input-shard-v1"
OUTPUT_SHARD_SCHEMA = "arv2-preopen-control-output-shard-v1"
SOURCE_FILE_SCHEMA = "arv2-preopen-control-project-source-v1"
PROJECTION_SCHEMA = "arv2-preopen-control-qc-projection-v1"
SUMMARY_SCHEMA = "arv2-preopen-control-summary-receipt-v1"
TERMINAL_PACKAGE_SCHEMA = "arv2-preopen-control-terminal-package-v1"
RUN_AUTHORITY_SCHEMA = "arv2-preopen-control-private-run-authority-v1"
CONSTRUCTION_INTERMEDIATE_SCHEMA = (
    "arv2-preopen-control-construction-intermediate-commitment-v1"
)
MARKET_SESSION_COMMITMENT_SCHEMA = (
    "arv2-preopen-control-market-session-commitment-v1"
)
PEER_AGGREGATE_SCHEMA = "arv2-preopen-control-peer-aggregate-v1"
QUALITY_MEASUREMENT_PROJECTION_SCHEMA = (
    "arv2-qdata-physical-measurement-projection-v1"
)
UNIVERSE_INPUT_SCHEMA = "arv2-preopen-control-universe-terminal-seed-v1"
SID_MAPPING_INPUT_SCHEMA = "arv2-preopen-control-reviewed-qc-sid-binding-v2"
FUNDAMENTAL_INPUT_SCHEMA = "arv2-preopen-control-fundamental-seed-v1"
EARNINGS_INPUT_SCHEMA = "arv2-preopen-control-earnings-seed-v1"
GUIDANCE_INPUT_SCHEMA = "arv2-preopen-control-guidance-seed-v1"
RATING_INPUT_SCHEMA = "arv2-preopen-control-rating-seed-v1"
INPUT_ROLE_SCHEMAS = {
    "universe": UNIVERSE_INPUT_SCHEMA,
    "sid_mapping": SID_MAPPING_INPUT_SCHEMA,
    "fundamentals": FUNDAMENTAL_INPUT_SCHEMA,
    "earnings": EARNINGS_INPUT_SCHEMA,
    "guidance": GUIDANCE_INPUT_SCHEMA,
    "ratings": RATING_INPUT_SCHEMA,
}
INPUT_ROLE_ORDER = tuple(INPUT_ROLE_SCHEMAS)
TRUTH_SOURCE_ROLE_ORDER = (
    "accepted_risk_capture", "eligible_universe", "security_master",
    "firm_ontology", "common_event", "sector_classification",
    "preopen_control", "data_quality",
)
PROJECT_NAME = "ARV2_PREOPEN_CONTROL_CONSTRUCTION_20260911"
BACKTEST_NAME = "ARV2 pre-open controls outcome-free construction"
ENTRY_PATH = "main.py"
WORKER_PATH = "preopen_control_worker.py"
QUALITY_WORKER_PATH = "preopen_quality_worker.py"
RUNTIME_PATH = "preopen_control_runtime.py"
INPUT_PREFIX = "arv2/preopen/input/"
OUTPUT_PREFIX = "arv2/preopen/output/"
SUMMARY_NAME = "ARV2_PREOPEN_CONTROL_RECEIPT"
MAX_SOURCE_CHARACTERS = 60_000
MAX_SHARD_ROWS = 100_000
MAX_UNCOMPRESSED_SHARD_BYTES = 96 * 1024 * 1024
MAX_COMPRESSED_SHARD_BYTES = 32 * 1024 * 1024
DECISION_CHUNK_SESSION_COUNT = 10
HISTORY_SYMBOL_BATCH_SIZE = 48
MAX_BUFFERED_TERMINALS = 5_000
MAX_BLOCK_COMPRESSED_INPUT_BYTES = 64 * 1024 * 1024
MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES = 192 * 1024 * 1024
MAX_BLOCK_INPUT_ROW_COUNT = 200_000
MAX_BUFFERED_MARKET_OBSERVATION_COUNT = 300_000
MAX_PROJECTED_HISTORY_CALL_COUNT = 20_000
MAX_PROJECTED_MARKET_OBSERVATION_COUNT = 100_000_000
MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
MAX_RETAINED_INPUT_COMPRESSED_BYTES = 1024 * 1024 * 1024
HISTORY_LOOKBACK_CALENDAR_DAYS = 430
MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND = 256
MARKET_SUMMARY_SERIALIZED_BYTE_BOUND = 4 * 1024
PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND = 1024
MAX_PEER_GROUP_STATE_COUNT = 300_000
TERMINAL_SERIALIZED_BYTE_BOUND = 12 * 1024
MAX_PROJECTED_SERIALIZED_WORKING_SET_BYTES = 384 * 1024 * 1024
MAX_LOGICAL_MERGE_COMPRESSED_BYTES = 128 * 1024 * 1024
MAX_RUN_AUTHORITY_BYTES = 128 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_QC_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}\Z")
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")
_SID_MAPPING_ROW_FIELDS = {
    "schema", "security_id", "qc_security_id", "cusip", "issuer_id",
    "share_class_id", "listing_id", "historical_ticker", "first_session",
    "last_session", "available_at", "source_row_sha256", "row_sha256",
    "security_master_artifact_id", "security_master_artifact_sha256",
    "mapping_status", "ticker_interval_evidence_sha256",
    "qc_discovery_terminal_sha256", "current_ticker_matches",
}


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False,
            ) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PreopenControlStageError("value is not canonical JSON") from exc


def normalize_lean_bar_end_utc_text(value: datetime) -> str:
    """Interpret naive LEAN US-equity bar ends in New York, including DST."""

    if type(value) is not datetime:
        raise PreopenControlStageError("LEAN bar end must be exact datetime")
    localized = (
        value.replace(tzinfo=ZoneInfo("America/New_York"))
        if value.tzinfo is None
        else value
    )
    return localized.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000000Z"
    )


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise PreopenControlStageError(f"{name} is not a lowercase SHA-256")
    return value


def _safe(value: object, name: str) -> str:
    if (
        type(value) is not str or _SAFE.fullmatch(value) is None
        or value.startswith("/") or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise PreopenControlStageError(f"{name} is not a safe identifier/key")
    return value


def _qc_security_identifier(value: object, name: str) -> str:
    if type(value) is not str or _QC_SID.fullmatch(value) is None:
        raise PreopenControlStageError(
            f"{name} is not a bounded encoded QuantConnect SecurityIdentifier"
        )
    return value


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise PreopenControlStageError(f"{name} is not an exact integer >= {minimum}")
    return value


def _session(value: object, name: str) -> date:
    if type(value) is not str:
        raise PreopenControlStageError(f"{name} must be an exact session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PreopenControlStageError(f"{name} must be an exact session date") from exc
    if parsed.isoformat() != value:
        raise PreopenControlStageError(f"{name} is not canonical session text")
    return parsed


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PreopenControlStageError(f"{name} must be an exact UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreopenControlStageError(f"{name} must be an exact UTC instant") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PreopenControlStageError(f"{name} is not canonical UTC microsecond text")
    return parsed


def _validated_sid_mapping_row(row: object) -> dict[str, object]:
    if (
        type(row) is not dict
        or set(row) != _SID_MAPPING_ROW_FIELDS
        or row.get("schema") != SID_MAPPING_INPUT_SCHEMA
    ):
        raise PreopenControlStageError("QC SID mapping row schema changed")
    result = dict(row)
    for name in (
        "security_id", "issuer_id", "share_class_id",
        "listing_id", "historical_ticker",
        "security_master_artifact_id",
    ):
        _safe(result[name], f"QC SID mapping {name}")
    if result["mapping_status"] not in {
        "reviewed_qc_fundamental_discovery_exact_cusip_join",
        "named_refusal_unresolved_cross_vendor_join",
    }:
        raise PreopenControlStageError(
            "QC SID mapping is not the reviewed discovery/CUSIP binding"
        )
    _qc_security_identifier(result["qc_security_id"], "QC SID mapping qc_security_id")
    if (
        result["mapping_status"]
        == "reviewed_qc_fundamental_discovery_exact_cusip_join"
        and (
            type(result["cusip"]) is not str
            or _CUSIP.fullmatch(result["cusip"]) is None
        )
    ) or (
        result["mapping_status"] == "named_refusal_unresolved_cross_vendor_join"
        and result["cusip"] is not None
        and (
            type(result["cusip"]) is not str
            or _CUSIP.fullmatch(result["cusip"]) is None
        )
    ):
        raise PreopenControlStageError("QC SID mapping CUSIP changed")
    if type(result["current_ticker_matches"]) is not bool:
        raise PreopenControlStageError("current ticker comparison type changed")
    first = _session(result["first_session"], "QC SID mapping first_session")
    last = _session(result["last_session"], "QC SID mapping last_session")
    if first > last:
        raise PreopenControlStageError("QC SID mapping effective range reversed")
    _utc(result["available_at"], "QC SID mapping available_at")
    _sha(result["source_row_sha256"], "QC SID mapping source row")
    _sha(
        result["qc_discovery_terminal_sha256"],
        "QC SID mapping discovery terminal",
    )
    _sha(
        result["ticker_interval_evidence_sha256"],
        "QC SID mapping ticker interval evidence",
    )
    _sha(
        result["security_master_artifact_sha256"],
        "QC SID mapping security master artifact",
    )
    declared = _sha(result["row_sha256"], "QC SID mapping row")
    semantic = dict(result)
    semantic.pop("row_sha256")
    if declared != hashlib.sha256(canonical_json_bytes(semantic)).hexdigest():
        raise PreopenControlStageError("QC SID mapping row hash changed")
    return result


def _bounded_gzip(payload: bytes, expected: int, name: str) -> bytes:
    if (
        type(payload) is not bytes
        or len(payload) > MAX_COMPRESSED_SHARD_BYTES
        or type(expected) is not int
        or expected < 0
        or expected > MAX_UNCOMPRESSED_SHARD_BYTES
    ):
        raise PreopenControlStageError(f"{name} payload exceeds a byte bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(expected + 1)
            if len(raw) != expected or stream.read(1):
                raise PreopenControlStageError(f"{name} uncompressed size changed")
    except (OSError, EOFError) as exc:
        raise PreopenControlStageError(f"{name} is not bounded gzip") from exc
    return raw


@dataclasses.dataclass(frozen=True, init=False)
class PreopenControlRunAuthority:
    """Owner-controlled private pin for exactly one closed input candidate."""

    pin_id: str
    pin_sha256: str
    closed_input_manifest_sha256: str
    input_source_inventory_sha256: str
    source_policy_sha256: str
    resource_census_sha256: str
    qc_sid_mapping_source_sha256: str
    target_qc_capacity_reviewed: bool
    qc_sid_mapping_reviewed: bool
    _pin_path: Path = dataclasses.field(repr=False)
    _pin_bytes: bytes = dataclasses.field(repr=False)


_RUN_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[PreopenControlRunAuthority], tuple[object, ...]]
] = {}
_RUN_AUTHORITIES_LOCK = threading.RLock()


def _strict_json(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise PreopenControlStageError(f"{name} must be exact nonempty bytes")

    def reject_pairs(pairs):
        result = {}
        for key, value in pairs:
            if type(key) is not str or key in result:
                raise PreopenControlStageError(
                    f"{name} has a duplicate or non-string object key"
                )
            result[key] = value
        return result

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                PreopenControlStageError(f"{name} contains a binary float")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                PreopenControlStageError(f"{name} contains a non-finite value")
            ),
        )
    except PreopenControlStageError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PreopenControlStageError(f"{name} is not strict JSON") from exc
    if type(parsed) is not dict or canonical_json_bytes(parsed) != payload:
        raise PreopenControlStageError(f"{name} is not one canonical JSON object")
    return parsed


def _closed_manifest(value: dict[str, object]) -> dict[str, object]:
    closed = dict(value)
    gate = dict(closed.get("construction_gate", {}))
    gate["external_private_run_authority"] = None
    closed["construction_gate"] = gate
    return closed


_RUN_PIN_FIELDS = {
    "schema", "status", "pin_id", "pin_sha256",
    "closed_input_manifest_sha256", "input_source_inventory_sha256",
    "source_policy_sha256", "resource_census_sha256",
    "qc_sid_mapping_source_sha256", "target_qc_capacity_reviewed",
    "qc_sid_mapping_reviewed", "maximum_runs",
    "outcome_result_order_access_authorized",
}


def _run_pin_binding(closed_manifest_bytes: bytes) -> dict[str, object]:
    manifest = _strict_json(closed_manifest_bytes, "closed input manifest")
    gate = manifest.get("construction_gate")
    if (
        type(gate) is not dict
        or gate.get("external_private_run_authority_required") is not True
        or gate.get("external_private_run_authority") is not None
    ):
        raise PreopenControlStageError("input manifest is not a closed run candidate")
    return {
        "schema": RUN_AUTHORITY_SCHEMA,
        "closed_input_manifest_sha256": hashlib.sha256(
            closed_manifest_bytes
        ).hexdigest(),
        "input_source_inventory_sha256": manifest[
            "input_source_inventory_sha256"
        ],
        "source_policy_sha256": hashlib.sha256(
            canonical_json_bytes(manifest["source_policy"])
        ).hexdigest(),
        "resource_census_sha256": hashlib.sha256(
            canonical_json_bytes(manifest["resource_census"])
        ).hexdigest(),
        "qc_sid_mapping_source_sha256": hashlib.sha256(
            canonical_json_bytes(manifest["qc_sid_mapping_source"])
        ).hexdigest(),
        "maximum_runs": 1,
        "outcome_result_order_access_authorized": False,
    }


def _validate_reviewed_run_pin(
    payload: bytes, closed_manifest_bytes: bytes,
) -> dict[str, object]:
    parsed = _strict_json(payload, "private run authority")
    if set(parsed) != _RUN_PIN_FIELDS:
        raise PreopenControlStageError("private run authority fields changed")
    binding = _run_pin_binding(closed_manifest_bytes)
    if any(parsed.get(name) != value for name, value in binding.items()):
        raise PreopenControlStageError("private run authority does not bind candidate")
    if (
        parsed.get("status")
        != "independently_reviewed_private_preopen_construction_authority"
        or parsed.get("target_qc_capacity_reviewed") is not True
        or parsed.get("qc_sid_mapping_reviewed") is not True
    ):
        raise PreopenControlStageError(
            "capacity and QC SID mapping require independent private review"
        )
    seed = dict(parsed)
    seed["pin_id"] = None
    seed["pin_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        parsed.get("pin_sha256") != digest
        or parsed.get("pin_id")
        != f"arv2-preopen-run-authority-{digest[:24]}"
    ):
        raise PreopenControlStageError("private run authority identity changed")
    return parsed


def render_preopen_control_run_authority_candidate(
    closed_input_manifest_bytes: bytes,
) -> bytes:
    """Render a non-authorizing review candidate with both attestations closed."""

    raw = {
        **_run_pin_binding(closed_input_manifest_bytes),
        "status": "review_required_not_authorized",
        "pin_id": None,
        "pin_sha256": None,
        "target_qc_capacity_reviewed": False,
        "qc_sid_mapping_reviewed": False,
    }
    return canonical_json_bytes(raw)


def _read_private_pin(path: Path) -> bytes:
    if type(path) is not type(Path()) or path.is_symlink():
        raise PreopenControlStageError("run authority must be a nonsymlink Path")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PreopenControlStageError("private run authority is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size <= 0
            or before.st_size > MAX_RUN_AUTHORITY_BYTES
        ):
            raise PreopenControlStageError(
                "run authority is not a bounded private regular file"
            )
        chunks: list[bytes] = []
        remaining = MAX_RUN_AUTHORITY_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > MAX_RUN_AUTHORITY_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise PreopenControlStageError("private run authority changed while read")
    finally:
        os.close(descriptor)
    return payload


def _run_authority_fingerprint(value: PreopenControlRunAuthority) -> tuple[object, ...]:
    return (
        value.pin_id, value.pin_sha256, value.closed_input_manifest_sha256,
        value.input_source_inventory_sha256, value.source_policy_sha256,
        value.resource_census_sha256, value.qc_sid_mapping_source_sha256,
        value.target_qc_capacity_reviewed, value.qc_sid_mapping_reviewed,
        value._pin_path, value._pin_bytes,
    )


def load_preopen_control_run_authority(
    closed_input_manifest_bytes: bytes, pin_path: Path,
) -> PreopenControlRunAuthority:
    """Load an exact owner-controlled private pin; canonical bytes alone do not grant it."""

    payload = _read_private_pin(pin_path)
    parsed = _validate_reviewed_run_pin(payload, closed_input_manifest_bytes)
    result = object.__new__(PreopenControlRunAuthority)
    values = {
        "pin_id": parsed["pin_id"],
        "pin_sha256": parsed["pin_sha256"],
        "closed_input_manifest_sha256": parsed["closed_input_manifest_sha256"],
        "input_source_inventory_sha256": parsed["input_source_inventory_sha256"],
        "source_policy_sha256": parsed["source_policy_sha256"],
        "resource_census_sha256": parsed["resource_census_sha256"],
        "qc_sid_mapping_source_sha256": parsed[
            "qc_sid_mapping_source_sha256"
        ],
        "target_qc_capacity_reviewed": parsed["target_qc_capacity_reviewed"],
        "qc_sid_mapping_reviewed": parsed["qc_sid_mapping_reviewed"],
        "_pin_path": pin_path,
        "_pin_bytes": payload,
    }
    for name, item in values.items():
        object.__setattr__(result, name, item)
    identity = id(result)
    reference = weakref.ref(
        result, lambda ref, key=identity: _forget_run_authority(key, ref)
    )
    with _RUN_AUTHORITIES_LOCK:
        _RUN_AUTHORITIES[identity] = (reference, _run_authority_fingerprint(result))
    return require_preopen_control_run_authority(result, closed_input_manifest_bytes)


def _forget_run_authority(identity, reference):
    with _RUN_AUTHORITIES_LOCK:
        current = _RUN_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _RUN_AUTHORITIES.pop(identity, None)


def require_preopen_control_run_authority(
    value: PreopenControlRunAuthority, closed_input_manifest_bytes: bytes,
) -> PreopenControlRunAuthority:
    if type(value) is not PreopenControlRunAuthority:
        raise PreopenControlStageError("run authority type changed")
    with _RUN_AUTHORITIES_LOCK:
        registered = _RUN_AUTHORITIES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise PreopenControlStageError("run authority is not private-file authenticated")
    payload = _read_private_pin(value._pin_path)
    if (
        payload != value._pin_bytes
        or _validate_reviewed_run_pin(payload, closed_input_manifest_bytes)
        != _strict_json(value._pin_bytes, "registered private run authority")
        or registered[1] != _run_authority_fingerprint(value)
    ):
        raise PreopenControlStageError("private run authority changed")
    return value


def activate_preopen_input_manifest_bytes(
    closed_input_manifest_bytes: bytes,
    authority: PreopenControlRunAuthority,
) -> bytes:
    authority = require_preopen_control_run_authority(
        authority, closed_input_manifest_bytes
    )
    manifest = _strict_json(closed_input_manifest_bytes, "closed input manifest")
    gate = dict(manifest["construction_gate"])
    gate["external_private_run_authority"] = {
        "schema": RUN_AUTHORITY_SCHEMA,
        "pin_id": authority.pin_id,
        "pin_sha256": authority.pin_sha256,
        "closed_input_manifest_sha256": authority.closed_input_manifest_sha256,
        "input_source_inventory_sha256": authority.input_source_inventory_sha256,
        "source_policy_sha256": authority.source_policy_sha256,
        "resource_census_sha256": authority.resource_census_sha256,
        "qc_sid_mapping_source_sha256": (
            authority.qc_sid_mapping_source_sha256
        ),
        "target_qc_capacity_reviewed": authority.target_qc_capacity_reviewed,
        "qc_sid_mapping_reviewed": authority.qc_sid_mapping_reviewed,
    }
    manifest["construction_gate"] = gate
    return canonical_json_bytes(manifest)


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenInputShard:
    role: str
    security_batch_ordinal: int
    ordinal: int
    partition_first_session: str
    partition_last_session: str
    object_store_key: str
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    row_count: int
    payload: bytes = dataclasses.field(repr=False)

    def descriptor(self) -> dict[str, object]:
        return {
            "schema": INPUT_SHARD_SCHEMA,
            "role": self.role,
            "security_batch_ordinal": self.security_batch_ordinal,
            "ordinal": self.ordinal,
            "partition_first_session": self.partition_first_session,
            "partition_last_session": self.partition_last_session,
            "object_store_key": self.object_store_key,
            "compression": "gzip-level9-mtime0",
            "encoding": "canonical-json-lines-utf8-lf",
            "row_schema": INPUT_ROLE_SCHEMAS[self.role],
            "compressed_sha256": self.compressed_sha256,
            "compressed_byte_count": self.compressed_byte_count,
            "uncompressed_sha256": self.uncompressed_sha256,
            "uncompressed_byte_count": self.uncompressed_byte_count,
            "row_count": self.row_count,
        }


def build_preopen_input_shard(
    *, role: str, security_batch_ordinal: int, ordinal: int,
    partition_first_session: str, partition_last_session: str,
    rows: Sequence[Mapping[str, object]],
) -> PreopenInputShard:
    if role not in INPUT_ROLE_SCHEMAS:
        raise PreopenControlStageError("input shard role changed")
    _count(security_batch_ordinal, "security_batch_ordinal")
    _count(ordinal, "ordinal")
    first = _session(partition_first_session, "partition_first_session")
    last = _session(partition_last_session, "partition_last_session")
    if first > last:
        raise PreopenControlStageError("input shard partition endpoints are reversed")
    if type(rows) not in (tuple, list) or len(rows) > MAX_SHARD_ROWS:
        raise PreopenControlStageError("input shard rows changed or exceed bound")
    normalized = sorted((dict(row) for row in rows), key=canonical_json_bytes)
    if any(row.get("schema") != INPUT_ROLE_SCHEMAS[role] for row in normalized):
        raise PreopenControlStageError("input row schema changed")
    encoded = [canonical_json_bytes(row) for row in normalized]
    if len(set(encoded)) != len(encoded):
        raise PreopenControlStageError("input shard repeats a row")
    raw = b"".join(encoded)
    if len(raw) > MAX_UNCOMPRESSED_SHARD_BYTES:
        raise PreopenControlStageError("input shard exceeds uncompressed bound")
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(payload) > MAX_COMPRESSED_SHARD_BYTES:
        raise PreopenControlStageError("input shard exceeds compressed bound")
    digest = hashlib.sha256(payload).hexdigest()
    key = (
        f"{INPUT_PREFIX}content/security-batch-{security_batch_ordinal:04d}/{role}/"
        f"{ordinal:04d}-{digest}-jsonl.gz"
    )
    return PreopenInputShard(
        role=role,
        security_batch_ordinal=security_batch_ordinal,
        ordinal=ordinal,
        partition_first_session=partition_first_session,
        partition_last_session=partition_last_session,
        object_store_key=key,
        compressed_sha256=digest,
        compressed_byte_count=len(payload),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        uncompressed_byte_count=len(raw),
        row_count=len(normalized),
        payload=payload,
    )


def build_preopen_input_manifest_bytes(
    *,
    shards: tuple[PreopenInputShard, ...],
    benchmark_security_id: str,
    benchmark_ticker: str,
    first_session: str,
    last_session: str,
    calculation_session: str,
    rating_source_complete: bool,
    earnings_source_complete: bool,
    guidance_source_complete: bool,
    earnings_pit_policy_id: str,
    guidance_clock_policy_id: str,
    eligible_universe_artifact_id: str,
    eligible_universe_artifact_sha256: str,
    eligible_universe_artifact_byte_count: int,
    truth_source_bindings: tuple[Mapping[str, object], ...],
) -> bytes:
    if type(shards) is not tuple or not shards:
        raise PreopenControlStageError("input shard inventory is empty")
    for shard in shards:
        if type(shard) is not PreopenInputShard:
            raise PreopenControlStageError("input shard type changed")
        if shard.role not in INPUT_ROLE_SCHEMAS:
            raise PreopenControlStageError("input shard role changed")
        _count(
            shard.security_batch_ordinal,
            "input shard security_batch_ordinal",
        )
        _count(shard.ordinal, "input shard ordinal")
        if _session(
            shard.partition_first_session, "input shard first session"
        ) > _session(shard.partition_last_session, "input shard last session"):
            raise PreopenControlStageError("input shard endpoints reversed")
        raw = _bounded_gzip(
            shard.payload, shard.uncompressed_byte_count, "input shard"
        )
        if (
            len(shard.payload) != shard.compressed_byte_count
            or hashlib.sha256(shard.payload).hexdigest()
            != shard.compressed_sha256
            or hashlib.sha256(raw).hexdigest() != shard.uncompressed_sha256
        ):
            raise PreopenControlStageError("input shard payload identity changed")
        lines = raw.splitlines(keepends=True)
        if len(lines) != shard.row_count:
            raise PreopenControlStageError("input shard row census changed")
        encoded: list[bytes] = []
        for line in lines:
            row = _strict_json(line, "input shard row")
            if row.get("schema") != INPUT_ROLE_SCHEMAS[shard.role]:
                raise PreopenControlStageError("input shard row schema changed")
            encoded.append(line)
        if encoded != sorted(set(encoded)):
            raise PreopenControlStageError(
                "input shard rows repeat or are not canonical order"
            )
        expected_key = (
            f"{INPUT_PREFIX}content/security-batch-"
            f"{shard.security_batch_ordinal:04d}/"
            f"{shard.role}/{shard.ordinal:04d}-"
            f"{shard.compressed_sha256}-jsonl.gz"
        )
        if shard.object_store_key != expected_key:
            raise PreopenControlStageError("input shard key is not content-derived")
    expected = tuple(sorted(
        shards,
        key=lambda item: (
            item.security_batch_ordinal,
            INPUT_ROLE_ORDER.index(item.role), item.ordinal,
        ),
    ))
    if shards != expected:
        raise PreopenControlStageError("input shards are not canonically ordered")
    batch_ordinals = sorted({item.security_batch_ordinal for item in shards})
    if batch_ordinals != list(range(len(batch_ordinals))):
        raise PreopenControlStageError(
            "input security-batch ordinals are not contiguous"
        )
    for batch in batch_ordinals:
        batch_shards = [
            item for item in shards if item.security_batch_ordinal == batch
        ]
        if {item.role for item in batch_shards} != set(INPUT_ROLE_ORDER):
            raise PreopenControlStageError(
                "input security-batch shard roles are incomplete"
            )
        endpoints = {
            (item.partition_first_session, item.partition_last_session)
            for item in batch_shards
        }
        if len(endpoints) != 1:
            raise PreopenControlStageError(
                "input security-batch partition endpoints differ"
            )
        for role in INPUT_ROLE_ORDER:
            ordinals = [
                item.ordinal for item in batch_shards if item.role == role
            ]
            if ordinals != list(range(len(ordinals))):
                raise PreopenControlStageError(
                    "input security-batch shard ordinals are not contiguous"
                )
    _qc_security_identifier(benchmark_security_id, "benchmark_security_id")
    for name, value in (
        ("benchmark_ticker", benchmark_ticker),
        ("earnings_pit_policy_id", earnings_pit_policy_id),
        ("guidance_clock_policy_id", guidance_clock_policy_id),
        ("eligible_universe_artifact_id", eligible_universe_artifact_id),
    ):
        _safe(value, name)
    _sha(eligible_universe_artifact_sha256, "eligible_universe_artifact_sha256")
    _count(
        eligible_universe_artifact_byte_count,
        "eligible_universe_artifact_byte_count",
        minimum=1,
    )
    if (
        type(truth_source_bindings) is not tuple
        or tuple(item.get("kind") for item in truth_source_bindings)
        != TRUTH_SOURCE_ROLE_ORDER
    ):
        raise PreopenControlStageError(
            "truth source bindings are missing, duplicated, or reordered"
        )
    normalized_truth_sources: list[dict[str, object]] = []
    for item in truth_source_bindings:
        if type(item) is not dict or set(item) != {
            "kind", "artifact_id", "artifact_sha256"
        }:
            raise PreopenControlStageError("truth source binding fields changed")
        _safe(item["artifact_id"], "truth source artifact_id")
        _sha(item["artifact_sha256"], "truth source artifact_sha256")
        normalized_truth_sources.append(dict(item))
    universe_truth = normalized_truth_sources[1]
    if (
        universe_truth["artifact_id"] != eligible_universe_artifact_id
        or universe_truth["artifact_sha256"]
        != eligible_universe_artifact_sha256
    ):
        raise PreopenControlStageError(
            "eligible universe truth source binding differs from source artifact"
        )
    security_master_truth = normalized_truth_sources[2]
    for name, value in (
        ("rating_source_complete", rating_source_complete),
        ("earnings_source_complete", earnings_source_complete),
        ("guidance_source_complete", guidance_source_complete),
    ):
        if type(value) is not bool:
            raise PreopenControlStageError(f"{name} must be exact bool")
    if guidance_source_complete and guidance_clock_policy_id != GUIDANCE_CLOCK_POLICY_ID:
        raise PreopenControlStageError(
            "complete guidance requires the exact reviewed date-only lag policy"
        )
    descriptors = [item.descriptor() for item in shards]
    inventory_hash = hashlib.sha256(canonical_json_bytes(descriptors)).hexdigest()
    input_role_bindings = []
    for role in INPUT_ROLE_ORDER:
        role_descriptors = [item for item in descriptors if item["role"] == role]
        input_role_bindings.append({
            "role": role,
            "descriptor_projection_sha256": hashlib.sha256(
                canonical_json_bytes(role_descriptors)
            ).hexdigest(),
            "shard_count": len(role_descriptors),
            "row_count": sum(int(item["row_count"]) for item in role_descriptors),
            "compressed_byte_count": sum(
                int(item["compressed_byte_count"]) for item in role_descriptors
            ),
            "uncompressed_byte_count": sum(
                int(item["uncompressed_byte_count"]) for item in role_descriptors
            ),
        })
    sid_mapping_descriptors = [
        item for item in descriptors if item["role"] == "sid_mapping"
    ]
    sid_mapping_projection = canonical_json_bytes(sid_mapping_descriptors)
    sid_mapping_projection_sha256 = hashlib.sha256(
        sid_mapping_projection
    ).hexdigest()
    sid_mapping_row_count = sum(
        int(item["row_count"]) for item in sid_mapping_descriptors
    )
    declared_first = _session(first_session, "first_session")
    declared_last = _session(last_session, "last_session")
    calculation = _session(calculation_session, "calculation_session")
    if declared_first > declared_last or calculation <= declared_last:
        raise PreopenControlStageError(
            "calculation session must be strictly after the decision sample"
        )
    session_geometry: dict[str, dict[str, object]] = {}
    all_security_ids: set[str] = set()
    qc_sid_owners: dict[str, str] = {}
    cusip_owners: dict[str, str] = {}
    peer_group_keys: set[tuple[str, str, str]] = set()
    batch_session_memberships: dict[int, set[str]] = {}
    universe_terminal_count = 0
    batch_records: list[dict[str, object]] = []
    prior_last_security: str | None = None
    for batch in batch_ordinals:
        batch_shards = [
            item for item in shards if item.security_batch_ordinal == batch
        ]
        first_text = batch_shards[0].partition_first_session
        last_text = batch_shards[0].partition_last_session
        if first_text != first_session or last_text != last_session:
            raise PreopenControlStageError(
                "security-batch input must span the declared full sample"
            )
        batch_universe: list[dict[str, object]] = []
        batch_sid_mapping: list[dict[str, object]] = []
        for shard in batch_shards:
            if shard.role not in ("universe", "sid_mapping"):
                continue
            raw = _bounded_gzip(
                shard.payload, shard.uncompressed_byte_count, "universe shard"
            )
            for line in raw.splitlines(keepends=True):
                try:
                    row = json.loads(line)
                except (UnicodeError, ValueError) as exc:
                    raise PreopenControlStageError(
                        "universe shard contains invalid JSON"
                    ) from exc
                if canonical_json_bytes(row) != line:
                    raise PreopenControlStageError(
                        "universe shard row is not canonical"
                    )
                if shard.role == "universe":
                    batch_universe.append(row)
                else:
                    batch_sid_mapping.append(_validated_sid_mapping_row(row))
        mapping_by_hash = {
            row["row_sha256"]: row for row in batch_sid_mapping
        }
        if len(mapping_by_hash) != len(batch_sid_mapping):
            raise PreopenControlStageError(
                "QC SID mapping row repeats in security batch"
            )
        mapping_identity_to_candidate: dict[tuple[object, ...], str] = {}
        for mapping in batch_sid_mapping:
            owner_checks = [
                (qc_sid_owners, mapping["qc_security_id"], "QC SecurityIdentifier")
            ]
            if mapping["mapping_status"] == (
                "reviewed_qc_fundamental_discovery_exact_cusip_join"
            ):
                owner_checks.append((cusip_owners, mapping["cusip"], "CUSIP"))
            for owners, key, label in owner_checks:
                prior_owner = owners.setdefault(key, mapping["security_id"])
                if prior_owner != mapping["security_id"]:
                    raise PreopenControlStageError(
                        f"{label} is bound to distinct logical securities"
                    )
            mapping_identity = tuple(mapping[name] for name in (
                "qc_security_id", "cusip", "issuer_id", "share_class_id",
                "listing_id", "first_session", "last_session",
            ))
            prior_candidate = mapping_identity_to_candidate.setdefault(
                mapping_identity, mapping["row_sha256"]
            )
            if prior_candidate != mapping["row_sha256"]:
                raise PreopenControlStageError(
                    "Sharadar ticker interval repeats with conflicting evidence"
                )
        referenced_mapping_hashes: set[str] = set()
        batch_sessions = sorted({
            row.get("decision_session") for row in batch_universe
        })
        if not batch_sessions:
            raise PreopenControlStageError("security batch has no universe rows")
        batch_session_memberships[batch] = set(batch_sessions)
        seen_security_sessions: set[tuple[str, str]] = set()
        accepted_ids: set[str] = set()
        batch_security_ids: set[str] = set()
        maximum_accepted_in_session = 0
        accepted_by_session: dict[str, int] = {}
        for row in batch_universe:
            if (
                type(row) is not dict
                or row.get("schema") != UNIVERSE_INPUT_SCHEMA
                or row.get("disposition") not in ("accepted", "named_refusal")
                or type(row.get("decision_session_ordinal")) is not int
            ):
                raise PreopenControlStageError("universe row schema changed")
            session = row.get("decision_session")
            _session(session, "universe decision_session")
            opened = _utc(row.get("decision_open_utc"), "universe decision_open_utc")
            if opened.astimezone(ZoneInfo("America/New_York")).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            ) != session + "T09:30:00.000000":
                raise PreopenControlStageError("universe decision open is not NYSE open")
            for field in (
                "security_id", "issuer_id", "share_class_id",
                "listing_id", "historical_ticker",
            ):
                if type(row.get(field)) is not str or not row[field]:
                    raise PreopenControlStageError(
                        f"universe {field} is not an exact identifier"
                    )
            _qc_security_identifier(
                row.get("qc_security_id"), "universe qc_security_id"
            )
            _sha(row.get("security_master_row_sha256"), "security master row")
            mapping_row_sha256 = _sha(
                row.get("qc_sid_mapping_row_sha256"),
                "QC SID mapping row",
            )
            mapping = mapping_by_hash.get(mapping_row_sha256)
            if mapping is None:
                raise PreopenControlStageError(
                    "universe identity lacks its canonical QC SID mapping row"
                )
            referenced_mapping_hashes.add(mapping_row_sha256)
            if (
                mapping["security_master_artifact_id"]
                != security_master_truth["artifact_id"]
                or mapping["security_master_artifact_sha256"]
                != security_master_truth["artifact_sha256"]
            ):
                raise PreopenControlStageError(
                    "QC SID mapping is not bound to the truth security master"
                )
            mapping_identity = tuple(mapping[name] for name in (
                "security_id", "issuer_id", "share_class_id", "listing_id",
                "historical_ticker",
            ))
            universe_identity = tuple(row[name] for name in (
                "security_id", "issuer_id", "share_class_id", "listing_id",
                "historical_ticker",
            ))
            if mapping_identity != universe_identity:
                raise PreopenControlStageError(
                    "QC SID mapping does not bind the universe identity"
                )
            if row["qc_security_id"] != mapping["qc_security_id"]:
                raise PreopenControlStageError(
                    "universe QC SecurityIdentifier differs from reviewed mapping"
                )
            if (
                row["disposition"] == "accepted"
                and mapping["mapping_status"]
                != "reviewed_qc_fundamental_discovery_exact_cusip_join"
            ):
                raise PreopenControlStageError(
                    "accepted universe row lacks a reviewed CUSIP/SID join"
                )
            if not (
                _session(mapping["first_session"], "mapping first_session")
                <= _session(session, "universe mapping session")
                <= _session(mapping["last_session"], "mapping last_session")
            ):
                raise PreopenControlStageError(
                    "QC SID mapping is not effective for decision session"
                )
            if _utc(mapping["available_at"], "mapping available_at") >= opened:
                raise PreopenControlStageError(
                    "QC SID mapping is not strictly pre-open"
                )
            key = (session, row["security_id"])
            if key in seen_security_sessions:
                raise PreopenControlStageError("universe security/session repeats")
            seen_security_sessions.add(key)
            batch_security_ids.add(row["security_id"])
            geometry = session_geometry.setdefault(session, {
                "decision_session": session,
                "decision_open_utc": row["decision_open_utc"],
                "decision_session_ordinal": row["decision_session_ordinal"],
                "terminal_count": 0,
            })
            if (
                geometry["decision_open_utc"] != row["decision_open_utc"]
                or geometry["decision_session_ordinal"]
                != row["decision_session_ordinal"]
            ):
                raise PreopenControlStageError(
                    "decision-session geometry differs between security batches"
                )
            geometry["terminal_count"] = int(geometry["terminal_count"]) + 1
            if row["disposition"] == "accepted":
                accepted_ids.add(row["security_id"])
                for field in ("sector_id", "industry_id"):
                    if type(row.get(field)) is not str or not row[field]:
                        raise PreopenControlStageError(
                            f"accepted universe {field} changed"
                        )
                peer_group_keys.add((session, "sector", row["sector_id"]))
                peer_group_keys.add((session, "industry", row["industry_id"]))
                accepted_by_session[session] = accepted_by_session.get(session, 0) + 1
                maximum_accepted_in_session = max(
                    maximum_accepted_in_session, accepted_by_session[session]
                )
        if (
            not batch_security_ids
            or len(batch_security_ids) > HISTORY_SYMBOL_BATCH_SIZE
        ):
            raise PreopenControlStageError(
                "security batch exceeds the exact 48-security bound"
            )
        first_security = min(batch_security_ids)
        last_security = max(batch_security_ids)
        if prior_last_security is not None and first_security <= prior_last_security:
            raise PreopenControlStageError(
                "security-batch identity ranges overlap or reorder"
            )
        if all_security_ids & batch_security_ids:
            raise PreopenControlStageError("security appears in more than one batch")
        prior_last_security = last_security
        if referenced_mapping_hashes != set(mapping_by_hash):
            raise PreopenControlStageError(
                "QC SID mapping batch contains an unreferenced or omitted row"
            )
        for shard in batch_shards:
            if shard.role in ("universe", "sid_mapping"):
                continue
            raw = _bounded_gzip(
                shard.payload, shard.uncompressed_byte_count,
                f"{shard.role} shard",
            )
            for line in raw.splitlines(keepends=True):
                row = _strict_json(line, f"{shard.role} row")
                if row.get("security_id") not in batch_security_ids:
                    raise PreopenControlStageError(
                        f"{shard.role} row escaped its security batch"
                    )
        accepted_symbol_count = len(accepted_ids)
        calendar_observations_per_symbol = (
            (declared_last - declared_first).days
            + HISTORY_LOOKBACK_CALENDAR_DAYS + 1
        )
        total_market_observations = (
            accepted_symbol_count * 4 * calendar_observations_per_symbol
        )
        buffered_market_observations = (
            (accepted_symbol_count * 2 + 1) * calendar_observations_per_symbol
            if accepted_symbol_count else calendar_observations_per_symbol
        )
        calls = 4 if accepted_symbol_count else 0
        compressed = sum(item.compressed_byte_count for item in batch_shards)
        uncompressed = sum(item.uncompressed_byte_count for item in batch_shards)
        row_count = sum(item.row_count for item in batch_shards)
        if (
            compressed > MAX_BLOCK_COMPRESSED_INPUT_BYTES
            or uncompressed > MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES
            or row_count > MAX_BLOCK_INPUT_ROW_COUNT
            or buffered_market_observations
            > MAX_BUFFERED_MARKET_OBSERVATION_COUNT
        ):
            raise PreopenControlStageError(
                "one security batch exceeds reviewed capacity"
            )
        batch_records.append({
            "security_batch_ordinal": batch,
            "first_session": first_text,
            "last_session": last_text,
            "first_security_id": first_security,
            "last_security_id": last_security,
            "decision_session_count": len(batch_sessions),
            "universe_terminal_count": len(batch_universe),
            "distinct_security_count": len(batch_security_ids),
            "distinct_accepted_security_count": len(accepted_ids),
            "distinct_accepted_history_symbol_count": accepted_symbol_count,
            "projected_history_call_count": calls,
            "projected_total_market_observation_count": total_market_observations,
            "maximum_buffered_market_observation_count": (
                buffered_market_observations
            ),
            "maximum_derived_market_summary_count": maximum_accepted_in_session,
            "compressed_input_byte_count": compressed,
            "uncompressed_input_byte_count": uncompressed,
            "input_row_count": row_count,
        })
        all_security_ids.update(batch_security_ids)
        universe_terminal_count += len(batch_universe)
    sessions = sorted(session_geometry)
    if sessions[0] != first_session or sessions[-1] != last_session:
        raise PreopenControlStageError(
            "declared sample endpoints do not match universe terminals"
        )
    decision_sessions = [session_geometry[item] for item in sessions]
    session_ordinals = [
        int(item["decision_session_ordinal"]) for item in decision_sessions
    ]
    if session_ordinals != sorted(set(session_ordinals)):
        raise PreopenControlStageError(
            "decision-session ordinals repeat or are not increasing"
        )
    session_chunk_by_session = {
        session: index // DECISION_CHUNK_SESSION_COUNT
        for index, session in enumerate(sessions)
    }
    projected_output_shard_count = sum(
        len({session_chunk_by_session[item] for item in memberships})
        for memberships in batch_session_memberships.values()
    )
    projected_history_calls = 1 + sum(
        int(item["projected_history_call_count"]) for item in batch_records
    )
    if projected_history_calls > MAX_PROJECTED_HISTORY_CALL_COUNT:
        raise PreopenControlStageError("projected history calls exceed reviewed bound")
    projected_market_observations = sum(
        int(item["projected_total_market_observation_count"])
        for item in batch_records
    ) + calendar_observations_per_symbol
    if projected_market_observations > MAX_PROJECTED_MARKET_OBSERVATION_COUNT:
        raise PreopenControlStageError(
            "projected total repeated-history market work exceeds offline safety bound"
        )
    projected_output_uncompressed_bytes = (
        universe_terminal_count * TERMINAL_SERIALIZED_BYTE_BOUND
    )
    if (
        projected_output_uncompressed_bytes
        > MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES
    ):
        raise PreopenControlStageError(
            "projected output storage exceeds offline safety bound"
        )
    retained_input_compressed_bytes = sum(
        item.compressed_byte_count for item in shards
    )
    if retained_input_compressed_bytes > MAX_RETAINED_INPUT_COMPRESSED_BYTES:
        raise PreopenControlStageError(
            "host-retained compressed input payloads exceed offline safety bound"
        )
    peer_group_state_count = len(peer_group_keys)
    if peer_group_state_count > MAX_PEER_GROUP_STATE_COUNT:
        raise PreopenControlStageError(
            "full-census peer aggregate state exceeds reviewed capacity"
        )
    maximum_serialized_working_set = max(
        int(item["uncompressed_input_byte_count"])
        + peer_group_state_count * PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND
        + max(
            int(item["maximum_buffered_market_observation_count"])
            * MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND,
            min(
                MAX_BUFFERED_TERMINALS,
                DECISION_CHUNK_SESSION_COUNT
                * int(item["distinct_security_count"]),
            )
            * TERMINAL_SERIALIZED_BYTE_BOUND,
        )
        for item in batch_records
    )
    if maximum_serialized_working_set > MAX_PROJECTED_SERIALIZED_WORKING_SET_BYTES:
        raise PreopenControlStageError("projected serialized working set exceeds bound")
    manifest = {
        "schema": INPUT_MANIFEST_SCHEMA,
        "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "benchmark_security_id": benchmark_security_id,
        "benchmark_ticker": benchmark_ticker,
        "first_session": first_session,
        "last_session": last_session,
        "calculation_session": calculation_session,
        "shards": descriptors,
        "input_source_inventory_sha256": inventory_hash,
        "input_role_bindings": input_role_bindings,
        "truth_source_bindings": normalized_truth_sources,
        "eligible_universe_source": {
            "artifact_id": eligible_universe_artifact_id,
            "content_sha256": eligible_universe_artifact_sha256,
            "artifact_sha256": eligible_universe_artifact_sha256,
            "byte_count": eligible_universe_artifact_byte_count,
        },
        "qc_sid_mapping_source": {
            "artifact_id": (
                f"arv2-qc-sid-mapping-{sid_mapping_projection_sha256[:24]}"
            ),
            "content_sha256": sid_mapping_projection_sha256,
            "artifact_sha256": sid_mapping_projection_sha256,
            "byte_count": len(sid_mapping_projection),
            "row_count": sid_mapping_row_count,
            "mapping_semantics": (
                "canonical_content_addressed_exact_QC_SecurityIdentifier_to_"
                "Sharadar_CUSIP_permaticker_FIGI_binding;_current_ticker_is_"
                "display_only_and_the_runtime_must_use_self.symbol_encoded_SID"
            ),
        },
        "source_policy": {
            "rating_source_view": (
                "conservative_censored_current_vintage_non_pristine_pit"
            ),
            "rating_source_complete": rating_source_complete,
            "earnings_source_complete": earnings_source_complete,
            "earnings_pit_policy_id": earnings_pit_policy_id,
            "guidance_source_complete": guidance_source_complete,
            "guidance_clock_policy_id": guidance_clock_policy_id,
            "unknown_event_archive_or_clock_is_zero": False,
        },
        "construction_gate": {
            "external_private_run_authority": None,
            "external_private_run_authority_required": True,
            "outcome_access_authorized": False,
            "result_access_authorized": False,
            "orders_authorized": False,
        },
        "resource_census": {
            "decision_session_count": len(sessions),
            "decision_sessions": decision_sessions,
            "eligible_universe_terminal_count": universe_terminal_count,
            "distinct_security_count": len(all_security_ids),
            "security_batch_count": len(batch_records),
            "decision_chunk_session_count": DECISION_CHUNK_SESSION_COUNT,
            "history_symbol_batch_size": HISTORY_SYMBOL_BATCH_SIZE,
            "full_sample_security_history_pass_count": 2,
            "history_calls_per_nonempty_security_batch": 4,
            "deduplicated_benchmark_history_call_count": 1,
            "history_lookback_calendar_days": HISTORY_LOOKBACK_CALENDAR_DAYS,
            "maximum_symbols_in_one_security_batch": max(
                int(item["distinct_accepted_history_symbol_count"])
                for item in batch_records
            ),
            "maximum_buffered_market_observation_count": max(
                int(item["maximum_buffered_market_observation_count"])
                for item in batch_records
            ),
            "maximum_derived_market_summary_count": max(
                int(item["maximum_derived_market_summary_count"])
                for item in batch_records
            ),
            "peer_group_state_count": peer_group_state_count,
            "maximum_peer_group_state_count": MAX_PEER_GROUP_STATE_COUNT,
            "peer_group_state_serialized_byte_bound": (
                PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND
            ),
            "projected_batched_history_call_count": projected_history_calls,
            "projected_total_market_observation_count": (
                projected_market_observations
            ),
            "maximum_projected_market_observation_count": (
                MAX_PROJECTED_MARKET_OBSERVATION_COUNT
            ),
            "projected_output_uncompressed_byte_upper_bound": (
                projected_output_uncompressed_bytes
            ),
            "maximum_projected_output_uncompressed_bytes": (
                MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES
            ),
            "compressed_input_byte_count": retained_input_compressed_bytes,
            "maximum_retained_input_compressed_bytes": (
                MAX_RETAINED_INPUT_COMPRESSED_BYTES
            ),
            "uncompressed_input_byte_count": sum(
                item.uncompressed_byte_count for item in shards
            ),
            "maximum_buffered_terminal_count": MAX_BUFFERED_TERMINALS,
            "maximum_one_security_batch_compressed_input_bytes": (
                MAX_BLOCK_COMPRESSED_INPUT_BYTES
            ),
            "maximum_one_security_batch_uncompressed_input_bytes": (
                MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES
            ),
            "maximum_one_security_batch_input_row_count": MAX_BLOCK_INPUT_ROW_COUNT,
            "maximum_one_batch_market_observation_count": (
                MAX_BUFFERED_MARKET_OBSERVATION_COUNT
            ),
            "maximum_projected_history_call_count": (
                MAX_PROJECTED_HISTORY_CALL_COUNT
            ),
            "target_qc_tier_capacity_requires_private_authority": True,
            "market_observation_serialized_byte_bound": (
                MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND
            ),
            "market_summary_serialized_byte_bound": (
                MARKET_SUMMARY_SERIALIZED_BYTE_BOUND
            ),
            "terminal_serialized_byte_bound": TERMINAL_SERIALIZED_BYTE_BOUND,
            "maximum_projected_serialized_working_set_bytes": (
                maximum_serialized_working_set
            ),
            "projected_output_shard_count": projected_output_shard_count,
            "maximum_logical_merge_cursor_count": len(batch_records),
            "maximum_logical_merge_compressed_bytes": (
                MAX_LOGICAL_MERGE_COMPRESSED_BYTES
            ),
            "physical_output_partition_order": (
                "decision_chunk_ordinal_then_security_batch_ordinal"
            ),
            "logical_output_order": "decision_session_then_security_id",
            "object_store_total_byte_quota_requires_private_authority": True,
            "full_terminal_set_retained_in_memory": False,
            "qc_runtime_full_input_set_retained_in_memory": False,
            "host_manifest_projection_retains_all_compressed_input_payloads": True,
            "physical_receipt_output_payload_iteration_is_bounded": True,
            "security_batches": batch_records,
        },
    }
    payload = canonical_json_bytes(manifest)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenOutputShard:
    ordinal: int
    decision_chunk_ordinal: int
    security_batch_ordinal: int
    partition_first_session: str
    partition_last_session: str
    first_security_id: str
    last_security_id: str
    object_store_key: str
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    row_count: int
    payload: bytes = dataclasses.field(repr=False)

    def descriptor(self) -> dict[str, object]:
        return {
            "schema": OUTPUT_SHARD_SCHEMA,
            "role": "control_terminals",
            "ordinal": self.ordinal,
            "decision_chunk_ordinal": self.decision_chunk_ordinal,
            "security_batch_ordinal": self.security_batch_ordinal,
            "partition_first_session": self.partition_first_session,
            "partition_last_session": self.partition_last_session,
            "first_security_id": self.first_security_id,
            "last_security_id": self.last_security_id,
            "object_store_key": self.object_store_key,
            "compression": "gzip-level9-mtime0",
            "encoding": "canonical-json-lines-utf8-lf",
            "row_schema": OUTPUT_TERMINAL_SCHEMA,
            "compressed_sha256": self.compressed_sha256,
            "compressed_byte_count": self.compressed_byte_count,
            "uncompressed_sha256": self.uncompressed_sha256,
            "uncompressed_byte_count": self.uncompressed_byte_count,
            "row_count": self.row_count,
        }


def build_preopen_output_shard(
    *, ordinal: int, terminal_rows: Sequence[Mapping[str, object]],
    decision_chunk_ordinal: int = 0, security_batch_ordinal: int = 0,
) -> PreopenOutputShard:
    _count(ordinal, "ordinal")
    _count(decision_chunk_ordinal, "decision_chunk_ordinal")
    _count(security_batch_ordinal, "security_batch_ordinal")
    if (
        type(terminal_rows) not in (tuple, list)
        or not terminal_rows
        or len(terminal_rows) > MAX_BUFFERED_TERMINALS
    ):
        raise PreopenControlStageError("output terminal shard is empty")
    rows = [dict(row) for row in terminal_rows]
    if any(row.get("schema") != OUTPUT_TERMINAL_SCHEMA for row in rows):
        raise PreopenControlStageError("output terminal schema changed")
    if any(
        type(row.get("decision_session")) is not str
        or type(row.get("security_id")) is not str
        for row in rows
    ):
        raise PreopenControlStageError("output terminal ordering identity changed")
    rows.sort(key=lambda row: (row["decision_session"], row["security_id"]))
    encoded = [canonical_json_bytes(row) for row in rows]
    if len(set(encoded)) != len(encoded):
        raise PreopenControlStageError("output terminal repeats")
    raw = b"".join(encoded)
    if len(raw) > 256 * 1024 * 1024:
        raise PreopenControlStageError("output terminal shard exceeds raw bound")
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(payload) > MAX_COMPRESSED_SHARD_BYTES:
        raise PreopenControlStageError("output terminal shard exceeds compressed bound")
    digest = hashlib.sha256(payload).hexdigest()
    first_session = rows[0]["decision_session"]
    last_session = rows[-1]["decision_session"]
    security_ids = sorted({row["security_id"] for row in rows})
    return PreopenOutputShard(
        ordinal=ordinal,
        decision_chunk_ordinal=decision_chunk_ordinal,
        security_batch_ordinal=security_batch_ordinal,
        partition_first_session=first_session,
        partition_last_session=last_session,
        first_security_id=security_ids[0],
        last_security_id=security_ids[-1],
        object_store_key=(
            f"{OUTPUT_PREFIX}content/control_terminals/"
            f"chunk-{decision_chunk_ordinal:04d}/"
            f"security-batch-{security_batch_ordinal:04d}/"
            f"{digest}-jsonl.gz"
        ),
        compressed_sha256=digest,
        compressed_byte_count=len(payload),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        uncompressed_byte_count=len(raw),
        row_count=len(rows),
        payload=payload,
    )


def _commitment_root(records: list[dict[str, object]], domain: str) -> str:
    return hashlib.sha256(canonical_json_bytes({"domain": domain, "records": records})).hexdigest()


def build_preopen_output_manifest_bytes(
    *,
    input_manifest_bytes: bytes,
    input_manifest_id: str,
    project_source_set_sha256: str,
    output_shards: tuple[PreopenOutputShard, ...],
    universe_sessions: Sequence[Mapping[str, object]],
    control_sessions: Sequence[Mapping[str, object]],
    construction_intermediates: Mapping[str, object],
) -> bytes:
    input_hash = hashlib.sha256(input_manifest_bytes).hexdigest()
    input_value = _strict_json(input_manifest_bytes, "input manifest")
    gate = input_value.get("construction_gate")
    if (
        type(gate) is not dict
        or type(gate.get("external_private_run_authority")) is not dict
    ):
        raise PreopenControlStageError(
            "output manifest requires an activated private run authority"
        )
    _safe(input_manifest_id, "input_manifest_id")
    _sha(project_source_set_sha256, "project_source_set_sha256")
    universe = [dict(item) for item in universe_sessions]
    controls = [dict(item) for item in control_sessions]
    if any(item.get("schema") != UNIVERSE_SESSION_COMMITMENT_SCHEMA for item in universe):
        raise PreopenControlStageError("universe commitment schema changed")
    if any(item.get("schema") != CONTROL_SESSION_COMMITMENT_SCHEMA for item in controls):
        raise PreopenControlStageError("control commitment schema changed")
    for item in controls:
        _count(item.get("market_observation_count"), "market observation count")
        _sha(item.get("market_observation_sha256"), "market observation root")
    if [item["decision_session"] for item in universe] != [
        item["decision_session"] for item in controls
    ]:
        raise PreopenControlStageError("output session geometries differ")
    if (
        type(output_shards) is not tuple
        or not output_shards
        or tuple(item.ordinal for item in output_shards)
        != tuple(range(len(output_shards)))
    ):
        raise PreopenControlStageError("output shard inventory is not exact and ordered")
    descriptors = [item.descriptor() for item in output_shards]
    if [
        (item["decision_chunk_ordinal"], item["security_batch_ordinal"])
        for item in descriptors
    ] != sorted({
        (item["decision_chunk_ordinal"], item["security_batch_ordinal"])
        for item in descriptors
    }):
        raise PreopenControlStageError(
            "physical output partitions repeat or are not canonical"
        )
    intermediates = dict(construction_intermediates)
    if set(intermediates) != {
        "schema", "peer_aggregate_record_count",
        "peer_aggregate_projection_sha256",
        "market_session_commitment_count",
        "market_session_projection_sha256", "physical_terminal_shard_count",
        "logical_terminal_order", "q_data_measurement_count",
        "q_data_measurement_projection_sha256",
    } or intermediates.get("schema") != CONSTRUCTION_INTERMEDIATE_SCHEMA:
        raise PreopenControlStageError("construction intermediate binding changed")
    for name in (
        "peer_aggregate_record_count", "market_session_commitment_count",
        "physical_terminal_shard_count", "q_data_measurement_count",
    ):
        _count(intermediates.get(name), name)
    for name in (
        "peer_aggregate_projection_sha256", "market_session_projection_sha256",
        "q_data_measurement_projection_sha256",
    ):
        _sha(intermediates.get(name), name)
    if (
        intermediates["physical_terminal_shard_count"] != len(descriptors)
        or intermediates["logical_terminal_order"]
        != "decision_session_then_security_id"
    ):
        raise PreopenControlStageError("construction intermediate census changed")
    accepted = sum(item["accepted_count"] for item in controls)
    refused = sum(item["refusal_count"] for item in controls)
    universe_count = sum(item["terminal_count"] for item in universe)
    if accepted + refused != universe_count:
        raise PreopenControlStageError("output terminal census is not exhaustive")
    if sum(item.row_count for item in output_shards) != universe_count:
        raise PreopenControlStageError("output shard census differs from terminals")
    manifest = {
        "schema": OUTPUT_MANIFEST_SCHEMA,
        "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "input_manifest": {
            "artifact_id": input_manifest_id,
            "content_sha256": input_hash,
            "artifact_sha256": input_hash,
            "byte_count": len(input_manifest_bytes),
        },
        "eligible_universe_source": input_value["eligible_universe_source"],
        "qc_sid_mapping_source": input_value["qc_sid_mapping_source"],
        "source_policy": input_value["source_policy"],
        "construction_resource_census": input_value["resource_census"],
        "run_authority": gate["external_private_run_authority"],
        "input_source_inventory_sha256": input_value["input_source_inventory_sha256"],
        "input_role_bindings": input_value["input_role_bindings"],
        "truth_source_bindings": input_value["truth_source_bindings"],
        "project_source_set_sha256": project_source_set_sha256,
        "construction_intermediates": intermediates,
        "output_shards": descriptors,
        "output_shard_inventory_sha256": hashlib.sha256(canonical_json_bytes(descriptors)).hexdigest(),
        "universe_sessions": universe,
        "control_sessions": controls,
        "universe_terminal_projection_sha256": _commitment_root(
            universe, "arv2-preopen-universe-session-projection-v1"
        ),
        "control_terminal_projection_sha256": _commitment_root(
            controls, "arv2-preopen-control-session-projection-v1"
        ),
        "census": {
            "universe_terminal_count": universe_count,
            "control_accepted_count": accepted,
            "control_refusal_count": refused,
            "control_terminal_count": accepted + refused,
        },
        "capabilities": {
            "provider_access": False, "credential_access": False,
            "filesystem_access": False, "quantconnect_access": False,
            "object_store_access": False, "price_access": False,
            "outcome_access": False, "result_access": False,
            "deployment": False, "orders": False, "trading": False,
        },
    }
    return canonical_json_bytes(manifest)


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenProjectSource:
    project_path: str
    content_sha256: str
    byte_count: int
    character_count: int
    content: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": SOURCE_FILE_SCHEMA,
            "project_path": self.project_path,
            "content_sha256": self.content_sha256,
            "byte_count": self.byte_count,
            "character_count": self.character_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenControlQcProjection:
    projection_id: str
    projection_sha256: str
    project_name: str
    backtest_name: str
    input_manifest_id: str
    input_manifest_sha256: str
    input_manifest_byte_count: int
    input_manifest_key: str
    source_files: tuple[PreopenProjectSource, ...]
    project_source_set_sha256: str
    output_manifest_key_pattern: str
    terminal_package_key: str
    summary_name: str
    enabled_runtime_source: bool
    places_orders: bool
    reads_outcomes_or_results: bool
    requires_separate_reviewed_run_authority: bool
    run_authority_id: str | None
    run_authority_sha256: str | None


def _runtime_entry_source(
    *, manifest_key: str, manifest_hash: str, manifest_count: int,
    manifest_id: str, source_set_hash: str, terminal_package_key: str,
) -> bytes:
    """Render the thin QC entry point; all construction lives in bounded runtime."""

    constants = {
        "INPUT_MANIFEST_KEY": manifest_key,
        "INPUT_MANIFEST_SHA256": manifest_hash,
        "INPUT_MANIFEST_BYTE_COUNT": manifest_count,
        "INPUT_MANIFEST_ID": manifest_id,
        "PROJECT_SOURCE_SET_SHA256": source_set_hash,
        "INPUT_MANIFEST_SCHEMA": INPUT_MANIFEST_SCHEMA,
        "OUTPUT_MANIFEST_SCHEMA": OUTPUT_MANIFEST_SCHEMA,
        "SUMMARY_SCHEMA": SUMMARY_SCHEMA,
        "SUMMARY_NAME": SUMMARY_NAME,
        "OUTPUT_PREFIX": OUTPUT_PREFIX,
        "TERMINAL_PACKAGE_KEY": terminal_package_key,
        "TERMINAL_PACKAGE_SCHEMA": TERMINAL_PACKAGE_SCHEMA,
    }
    literal = json.dumps(constants, sort_keys=True)
    source = f'''from AlgorithmImports import *
import hashlib
import json
from preopen_control_runtime import (
    finalize_preopen_control_construction,
    initialize_runtime_state,
    run_preopen_control_construction,
)

_C = {literal}

def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\\n").encode("utf-8")

class AnalystRevisionsV2PreopenControlConstruction(QCAlgorithm):
    def initialize(self):
        self.set_time_zone(TimeZones.NEW_YORK)
        payload = bytes(self.object_store.read_bytes(_C["INPUT_MANIFEST_KEY"]))
        if (len(payload) != _C["INPUT_MANIFEST_BYTE_COUNT"] or
                hashlib.sha256(payload).hexdigest() != _C["INPUT_MANIFEST_SHA256"]):
            raise ValueError("pre-open input manifest identity changed")
        self._manifest = json.loads(payload.decode("utf-8"))
        if _canonical(self._manifest) != payload:
            raise ValueError("pre-open input manifest is not canonical")
        gate = self._manifest.get("construction_gate", {{}})
        authority = gate.get("external_private_run_authority")
        closed_manifest = dict(self._manifest)
        closed_gate = dict(gate)
        closed_gate["external_private_run_authority"] = None
        closed_manifest["construction_gate"] = closed_gate
        if (self._manifest.get("schema") != _C["INPUT_MANIFEST_SCHEMA"] or
                self._manifest.get("contract_sha256") != "{CONTRACT_SHA256}" or
                gate.get("external_private_run_authority_required") is not True or
                type(authority) is not dict or
                authority.get("target_qc_capacity_reviewed") is not True or
                authority.get("qc_sid_mapping_reviewed") is not True or
                authority.get("closed_input_manifest_sha256") !=
                    hashlib.sha256(_canonical(closed_manifest)).hexdigest() or
                authority.get("input_source_inventory_sha256") !=
                    self._manifest.get("input_source_inventory_sha256") or
                authority.get("source_policy_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("source_policy"))).hexdigest() or
                authority.get("resource_census_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("resource_census"))).hexdigest() or
                authority.get("qc_sid_mapping_source_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("qc_sid_mapping_source"))).hexdigest() or
                any(gate.get(name) is not False for name in
                    ("outcome_access_authorized", "result_access_authorized",
                     "orders_authorized"))):
            raise ValueError("pre-open construction authority is closed")
        calculation = tuple(map(int, self._manifest["calculation_session"].split("-")))
        self.set_start_date(*calculation)
        self.set_end_date(*calculation)
        self.set_cash(100000)
        initialize_runtime_state(self)
        self.schedule.on(self.date_rules.on(*calculation),
            self.time_rules.at(12, 0), self._construct)

    def _construct(self):
        run_preopen_control_construction(self)

    def on_end_of_algorithm(self):
        finalize_preopen_control_construction(
            self, _C, "{CONTRACT_ID}", "{CONTRACT_SHA256}")
'''
    return source.encode("utf-8")


def _entry_source(
    *, manifest_key: str, manifest_hash: str, manifest_count: int,
    manifest_id: str, worker_hash: str, source_set_hash: str,
) -> bytes:
    constants = {
        "INPUT_MANIFEST_KEY": manifest_key,
        "INPUT_MANIFEST_SHA256": manifest_hash,
        "INPUT_MANIFEST_BYTE_COUNT": manifest_count,
        "INPUT_MANIFEST_ID": manifest_id,
        "WORKER_SOURCE_SHA256": worker_hash,
        "PROJECT_SOURCE_SET_SHA256": source_set_hash,
        "INPUT_MANIFEST_SCHEMA": INPUT_MANIFEST_SCHEMA,
        "OUTPUT_MANIFEST_SCHEMA": OUTPUT_MANIFEST_SCHEMA,
        "OUTPUT_TERMINAL_SCHEMA": OUTPUT_TERMINAL_SCHEMA,
        "SUMMARY_SCHEMA": SUMMARY_SCHEMA,
        "SUMMARY_NAME": SUMMARY_NAME,
        "OUTPUT_PREFIX": OUTPUT_PREFIX,
        "MAX_OUTPUT_SHARD_COMPRESSED_BYTES": MAX_COMPRESSED_SHARD_BYTES,
        "MAX_OUTPUT_SHARD_UNCOMPRESSED_BYTES": 256 * 1024 * 1024,
        "INPUT_SHARD_SCHEMA": INPUT_SHARD_SCHEMA,
        "OUTPUT_SHARD_SCHEMA": OUTPUT_SHARD_SCHEMA,
        "UNIVERSE_SESSION_COMMITMENT_SCHEMA": UNIVERSE_SESSION_COMMITMENT_SCHEMA,
        "CONTROL_SESSION_COMMITMENT_SCHEMA": CONTROL_SESSION_COMMITMENT_SCHEMA,
    }
    literal = json.dumps(constants, sort_keys=True)
    source = f'''from AlgorithmImports import *
import gzip
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from preopen_control_worker import (
    build_market_control_summaries, build_session_terminals,
)

_C = {literal}

def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\\n").encode("utf-8")

def _merkle(records):
    if not records:
        return hashlib.sha256(_canonical({{"domain": "arv2-empty-terminal-set-v1"}})).hexdigest()
    level = [hashlib.sha256(_canonical(
        {{"domain": "arv2-terminal-leaf-v1", "record": row}})).hexdigest()
        for row in records]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(_canonical({{"domain": "arv2-terminal-node-v1",
            "left": level[index], "right": level[index + 1]}})).hexdigest()
            for index in range(0, len(level), 2)]
    return level[0]

class AnalystRevisionsV2PreopenControlConstruction(QCAlgorithm):
    def initialize(self):
        self.set_time_zone(TimeZones.NEW_YORK)
        payload = bytes(self.object_store.read_bytes(_C["INPUT_MANIFEST_KEY"]))
        if (len(payload) != _C["INPUT_MANIFEST_BYTE_COUNT"] or
                hashlib.sha256(payload).hexdigest() != _C["INPUT_MANIFEST_SHA256"]):
            raise ValueError("pre-open input manifest identity changed")
        self._manifest = json.loads(payload.decode("utf-8"))
        gate = self._manifest.get("construction_gate", {{}})
        authority = gate.get("external_private_run_authority")
        closed_manifest = dict(self._manifest)
        closed_gate = dict(gate)
        closed_gate["external_private_run_authority"] = None
        closed_manifest["construction_gate"] = closed_gate
        if (self._manifest.get("schema") != _C["INPUT_MANIFEST_SCHEMA"] or
                self._manifest.get("contract_sha256") != "{CONTRACT_SHA256}" or
                gate.get("external_private_run_authority_required") is not True or
                type(authority) is not dict or
                authority.get("target_qc_capacity_reviewed") is not True or
                authority.get("qc_sid_mapping_reviewed") is not True or
                authority.get("closed_input_manifest_sha256") !=
                    hashlib.sha256(_canonical(closed_manifest)).hexdigest() or
                authority.get("input_source_inventory_sha256") !=
                    self._manifest.get("input_source_inventory_sha256") or
                authority.get("source_policy_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("source_policy"))).hexdigest() or
                authority.get("resource_census_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("resource_census"))).hexdigest() or
                authority.get("qc_sid_mapping_source_sha256") != hashlib.sha256(
                    _canonical(self._manifest.get("qc_sid_mapping_source"))).hexdigest() or
                any(gate.get(name) is not False for name in
                    ("outcome_access_authorized", "result_access_authorized", "orders_authorized"))):
            raise ValueError("pre-open construction authority is closed")
        calculation = tuple(map(int, self._manifest["calculation_session"].split("-")))
        self.set_start_date(*calculation)
        self.set_end_date(*calculation)
        self.set_cash(100000)
        self._terminal_buffer = []
        self._output_shards = []
        self._universe_sessions = []
        self._control_sessions = []
        self._processed = set()
        benchmark = self.symbol(self._manifest["benchmark_security_id"])
        if str(benchmark.id) != self._manifest["benchmark_security_id"]:
            raise ValueError("benchmark permanent security identity changed")
        self.schedule.on(self.date_rules.on(*calculation),
            self.time_rules.at(12, 0), self._construct_all_sessions)

    def _read_block(self, block):
        result = {{role: [] for role in ("universe", "sid_mapping", "fundamentals",
            "earnings", "guidance", "ratings")}}
        descriptors = [item for item in self._manifest["shards"]
            if item["block_ordinal"] == block["block_ordinal"]]
        if (sum(item["compressed_byte_count"] for item in descriptors) !=
                block["compressed_input_byte_count"] or
                sum(item["uncompressed_byte_count"] for item in descriptors) !=
                block["uncompressed_input_byte_count"] or
                sum(item["row_count"] for item in descriptors) !=
                block["input_row_count"]):
            raise ValueError("input block resource census changed")
        seen = set()
        for item in descriptors:
            payload = bytes(self.object_store.read_bytes(item["object_store_key"]))
            if (len(payload) != item["compressed_byte_count"] or
                    len(payload) > self._manifest["resource_census"][
                        "maximum_one_block_compressed_input_bytes"] or
                    hashlib.sha256(payload).hexdigest() != item["compressed_sha256"]):
                raise ValueError("pre-open input shard identity changed")
            maximum = item["uncompressed_byte_count"]
            with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
                raw = stream.read(maximum + 1)
                extra = stream.read(1)
            if (len(raw) != maximum or extra or
                    len(raw) > self._manifest["resource_census"][
                        "maximum_one_block_uncompressed_input_bytes"] or
                    hashlib.sha256(raw).hexdigest() != item["uncompressed_sha256"]):
                raise ValueError("pre-open input shard raw identity changed")
            rows = []
            for line in raw.splitlines(keepends=True):
                row = json.loads(line)
                if (_canonical(row) != line or
                        row.get("schema") != item["row_schema"]):
                    raise ValueError("pre-open input row is not exact canonical schema")
                identity = hashlib.sha256(line).hexdigest()
                if identity in seen:
                    raise ValueError("pre-open input block repeats a row")
                seen.add(identity)
                rows.append(row)
            if len(rows) != item["row_count"]:
                raise ValueError("pre-open input shard census changed")
            result[item["role"]].extend(rows)
        if set(result) != {{"universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings"}}:
            raise ValueError("pre-open input block roles changed")
        return result

    def _history_rows(self, symbols, start, last, kind, mode):
        output = []
        history = self.history[TradeBar](symbols, start, last, Resolution.DAILY,
            data_normalization_mode=mode)
        for bar in history:
            security_id = str(bar.symbol.id)
            ended = bar.end_time
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=ZoneInfo("America/New_York"))
            available = ended.astimezone(timezone.utc)
            if available >= last:
                raise ValueError("future bar escaped block history bound")
            output.append({{"security_id": security_id,
                "schema": "arv2-preopen-control-market-observation-v1",
                "kind": kind,
                "session_ordinal": available.date().toordinal(),
                "available_at": available.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
                "close": str(bar.close),
                "volume": str(bar.volume) if kind == "raw" else None}})
        return sorted(output, key=_canonical)

    def _market_summaries(self, block_rows, block_record):
        security_ids = sorted({{row["qc_security_id"] for row in block_rows
            if row["disposition"] == "accepted"}})
        if not security_ids:
            return [], []
        first = min(datetime.fromisoformat(
            row["decision_open_utc"].replace("Z", "+00:00")) for row in block_rows)
        last = max(datetime.fromisoformat(
            row["decision_open_utc"].replace("Z", "+00:00")) for row in block_rows)
        start = first - timedelta(days=430)
        benchmark_id = self._manifest["benchmark_security_id"]
        benchmark_symbol = self.symbol(benchmark_id)
        if str(benchmark_symbol.id) != benchmark_id:
            raise ValueError("benchmark permanent security identity changed")
        benchmark_rows = self._history_rows(
            [benchmark_symbol], start, last, "benchmark_total_return",
            DataNormalizationMode.TOTAL_RETURN)
        batch_size = self._manifest["resource_census"]["history_symbol_batch_size"]
        summaries = []
        lineage_by_key = {{}}
        maximum_rows = block_record["maximum_buffered_market_observation_count"]
        for offset in range(0, len(security_ids), batch_size):
            batch_ids = security_ids[offset:offset + batch_size]
            batch_id_set = set(batch_ids)
            symbols = []
            for security_id in batch_ids:
                symbol = self.symbol(security_id)
                if str(symbol.id) != security_id:
                    raise ValueError("permanent QC security identity changed")
                symbols.append(symbol)
            market_rows = self._history_rows(
                symbols, start, last, "total_return",
                DataNormalizationMode.TOTAL_RETURN)
            market_rows.extend(self._history_rows(
                symbols, start, last, "raw", DataNormalizationMode.RAW))
            if len(market_rows) + len(benchmark_rows) > maximum_rows:
                raise ValueError("one market batch exceeded reviewed capacity")
            batch_seeds = [row for row in block_rows
                if row["qc_security_id"] in batch_id_set]
            built, lineages = build_market_control_summaries(
                universe_rows=batch_seeds, stock_market_rows=market_rows,
                benchmark_market_rows=benchmark_rows,
                benchmark_security_id=benchmark_id)
            summaries.extend(built)
            for row in lineages:
                key = (row["decision_session"], row["security_id"], row["role"])
                if key in lineage_by_key and lineage_by_key[key] != row:
                    raise ValueError("market lineage changed between symbol batches")
                lineage_by_key[key] = row
            del market_rows
        lineages = sorted(lineage_by_key.values(), key=_canonical)
        if len(summaries) > block_record["maximum_derived_market_summary_count"]:
            raise ValueError("derived market summary capacity exceeded")
        return sorted(summaries,
            key=lambda row: (row["decision_session"], row["security_id"])), lineages

    def _construct_one_session(self, session, rows, summaries, lineages, inputs):
        if session in self._processed:
            raise ValueError("decision session was processed twice")
        opened = datetime.fromisoformat(rows[0]["decision_open_utc"].replace("Z", "+00:00"))
        observed = opened - timedelta(microseconds=1)
        session_summaries = [row for row in summaries
            if row["decision_session"] == session]
        session_lineages = sorted([row for row in lineages
            if row["decision_session"] == session], key=_canonical)
        roots = {{role: hashlib.sha256(_canonical(inputs[role])).hexdigest()
            for role in ("universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings")}}
        roots["market_observations"] = hashlib.sha256(
            _canonical(session_lineages)).hexdigest()
        policy = self._manifest["source_policy"]
        built = build_session_terminals(
            universe_rows=rows, market_control_summaries=session_summaries,
            market_lineages=session_lineages,
            benchmark_security_id=self._manifest["benchmark_security_id"],
            fundamental_rows=inputs["fundamentals"],
            earnings_rows=inputs["earnings"],
            guidance_rows=inputs["guidance"],
            rating_rows=inputs["ratings"],
            observed_at_utc=observed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            rating_source_complete=policy["rating_source_complete"],
            earnings_source_complete=policy["earnings_source_complete"],
            guidance_source_complete=policy["guidance_source_complete"],
            input_roots=roots)
        if len(built) != len(rows):
            raise ValueError("control worker omitted a universe terminal")
        accepted = sum(row["disposition"] == "accepted" for row in built)
        refused = len(built) - accepted
        universe_records = [{{"terminal": "accepted",
            "value": row["eligible_security_session"]}} if
            row["disposition"] == "accepted" else {{"terminal": "refused",
            "value": row["census_refusal"]}} for row in built]
        universe_records.sort(key=lambda item: item["value"]["security_id"])
        self._universe_sessions.append({{
            "schema": _C["UNIVERSE_SESSION_COMMITMENT_SCHEMA"],
            "decision_session": session, "accepted_count": accepted,
            "refusal_count": refused, "terminal_count": len(built),
            "terminal_merkle_root": _merkle(universe_records)}})
        self._control_sessions.append({{
            "schema": _C["CONTROL_SESSION_COMMITMENT_SCHEMA"],
            "decision_session": session, "accepted_count": accepted,
            "refusal_count": refused, "terminal_count": len(built),
            "terminal_merkle_root": _merkle(built),
            "market_observation_count": sum(
                row["observation_count"] for row in session_lineages),
            "market_observation_sha256": roots["market_observations"]}})
        self._terminal_buffer.extend(built)
        maximum = self._manifest["resource_census"][
            "maximum_buffered_terminal_count"]
        while len(self._terminal_buffer) >= maximum:
            self._flush_terminal_buffer(maximum)
        self._processed.add(session)

    def _construct_all_sessions(self):
        for block_record in self._manifest["resource_census"]["blocks"]:
            inputs = self._read_block(block_record)
            sessions = sorted({{row["decision_session"] for row in inputs["universe"]}})
            if (len(sessions) != block_record["decision_session_count"] or
                    sessions[0] != block_record["first_session"] or
                    sessions[-1] != block_record["last_session"]):
                raise ValueError("input block decision-session census changed")
            block_rows = inputs["universe"]
            summaries, lineages = self._market_summaries(block_rows, block_record)
            for session in sessions:
                rows = sorted([row for row in block_rows
                    if row["decision_session"] == session],
                    key=lambda row: row["security_id"])
                self._construct_one_session(
                    session, rows, summaries, lineages, inputs)
            del summaries
            del lineages
            del inputs
        self._flush_terminal_buffer()

    def _flush_terminal_buffer(self, row_limit=None):
        if not self._terminal_buffer:
            return
        count = len(self._terminal_buffer) if row_limit is None else row_limit
        rows = sorted(self._terminal_buffer[:count],
            key=lambda row: (row["decision_session"], row["security_id"]))
        raw = b"".join(_canonical(row) for row in rows)
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        if (len(rows) > self._manifest["resource_census"][
                "maximum_buffered_terminal_count"] or
                len(raw) > _C["MAX_OUTPUT_SHARD_UNCOMPRESSED_BYTES"] or
                len(compressed) > _C["MAX_OUTPUT_SHARD_COMPRESSED_BYTES"]):
            raise ValueError("pre-open terminal shard capacity exceeded")
        digest = hashlib.sha256(compressed).hexdigest()
        ordinal = len(self._output_shards)
        key = (_C["OUTPUT_PREFIX"] + "content/control_terminals/" +
            str(ordinal).zfill(4) + "-" + digest + "-jsonl.gz")
        if not self.object_store.save_bytes(key, compressed):
            raise ValueError("pre-open terminal shard persistence failed")
        self._output_shards.append({{"schema": _C["OUTPUT_SHARD_SCHEMA"],
            "role": "control_terminals", "ordinal": ordinal,
            "object_store_key": key, "compression": "gzip-level9-mtime0",
            "encoding": "canonical-json-lines-utf8-lf",
            "row_schema": _C["OUTPUT_TERMINAL_SCHEMA"],
            "compressed_sha256": digest,
            "compressed_byte_count": len(compressed),
            "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            "uncompressed_byte_count": len(raw), "row_count": len(rows)}})
        self._terminal_buffer = self._terminal_buffer[count:]

    def on_end_of_algorithm(self):
        if not self._output_shards or not self._processed:
            raise ValueError("pre-open construction produced no terminal shards")
        universe_sessions = sorted(
            self._universe_sessions, key=lambda row: row["decision_session"])
        control_sessions = sorted(
            self._control_sessions, key=lambda row: row["decision_session"])
        accepted_count = sum(row["accepted_count"] for row in control_sessions)
        refusal_count = sum(row["refusal_count"] for row in control_sessions)
        terminal_count = accepted_count + refusal_count
        descriptors = self._output_shards
        manifest = {{"schema": _C["OUTPUT_MANIFEST_SCHEMA"],
            "contract_id": "{CONTRACT_ID}",
            "contract_sha256": "{CONTRACT_SHA256}",
            "input_manifest": {{"artifact_id": _C["INPUT_MANIFEST_ID"],
                "content_sha256": _C["INPUT_MANIFEST_SHA256"],
                "artifact_sha256": _C["INPUT_MANIFEST_SHA256"],
                "byte_count": _C["INPUT_MANIFEST_BYTE_COUNT"]}},
            "eligible_universe_source": self._manifest["eligible_universe_source"],
            "qc_sid_mapping_source": self._manifest["qc_sid_mapping_source"],
            "source_policy": self._manifest["source_policy"],
            "construction_resource_census": self._manifest["resource_census"],
            "run_authority": self._manifest["construction_gate"][
                "external_private_run_authority"],
            "input_source_inventory_sha256":
                self._manifest["input_source_inventory_sha256"],
            "input_role_bindings": self._manifest["input_role_bindings"],
            "truth_source_bindings": self._manifest["truth_source_bindings"],
            "project_source_set_sha256": _C["PROJECT_SOURCE_SET_SHA256"],
            "output_shards": descriptors,
            "output_shard_inventory_sha256":
                hashlib.sha256(_canonical(descriptors)).hexdigest(),
            "universe_sessions": universe_sessions,
            "control_sessions": control_sessions,
            "universe_terminal_projection_sha256": hashlib.sha256(_canonical({{
                "domain": "arv2-preopen-universe-session-projection-v1",
                "records": universe_sessions}})).hexdigest(),
            "control_terminal_projection_sha256": hashlib.sha256(_canonical({{
                "domain": "arv2-preopen-control-session-projection-v1",
                "records": control_sessions}})).hexdigest(),
            "census": {{"universe_terminal_count": terminal_count,
                "control_accepted_count": accepted_count,
                "control_refusal_count": refusal_count,
                "control_terminal_count": terminal_count}},
            "capabilities": {{"provider_access": False, "credential_access": False,
                "filesystem_access": False, "quantconnect_access": False,
                "object_store_access": False, "price_access": False,
                "outcome_access": False, "result_access": False,
                "deployment": False, "orders": False, "trading": False}}}}
        manifest_bytes = _canonical(manifest)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_key = _C["OUTPUT_PREFIX"] + "manifests/" + manifest_hash + ".json"
        if not self.object_store.save_bytes(manifest_key, manifest_bytes):
            raise ValueError("pre-open output manifest persistence failed")
        receipt = {{"schema": _C["SUMMARY_SCHEMA"],
            "manifest_sha256": manifest_hash, "manifest_byte_count": len(manifest_bytes),
            "source_set_sha256": _C["PROJECT_SOURCE_SET_SHA256"],
            "terminal_count": terminal_count,
            "accepted_count": accepted_count,
            "refusal_count": refusal_count,
            "shard_count": len(descriptors)}}
        self.set_summary_statistic(_C["SUMMARY_NAME"],
            _canonical(receipt).decode("utf-8").strip())
'''
    return source.encode("utf-8")


def _source(path: str, content: bytes) -> PreopenProjectSource:
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise PreopenControlStageError("project source is not UTF-8") from exc
    if len(text) > MAX_SOURCE_CHARACTERS:
        raise PreopenControlStageError("project source exceeds 60,000 characters")
    try:
        ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise PreopenControlStageError("project source is not valid Python") from exc
    return PreopenProjectSource(
        project_path=path,
        content_sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        character_count=len(text),
        content=content,
    )


def build_preopen_control_qc_projection(
    *, input_manifest_bytes: bytes, worker_source_bytes: bytes,
    quality_worker_source_bytes: bytes, runtime_source_bytes: bytes,
    run_authority: PreopenControlRunAuthority | None = None,
) -> PreopenControlQcProjection:
    manifest = _strict_json(input_manifest_bytes, "input manifest")
    if (
        manifest.get("schema") != INPUT_MANIFEST_SCHEMA
        or manifest.get("contract_id") != CONTRACT_ID
        or manifest.get("contract_sha256") != CONTRACT_SHA256
    ):
        raise PreopenControlStageError("input manifest contract changed")
    gate = manifest.get("construction_gate")
    if type(gate) is not dict:
        raise PreopenControlStageError("construction gate changed")
    external = gate.get("external_private_run_authority")
    if run_authority is None:
        if external is not None:
            raise PreopenControlStageError(
                "activated manifest requires its private run authority"
            )
        enabled = False
    else:
        closed_bytes = canonical_json_bytes(_closed_manifest(manifest))
        run_authority = require_preopen_control_run_authority(
            run_authority, closed_bytes
        )
        expected_external = {
            "schema": RUN_AUTHORITY_SCHEMA,
            "pin_id": run_authority.pin_id,
            "pin_sha256": run_authority.pin_sha256,
            "closed_input_manifest_sha256": (
                run_authority.closed_input_manifest_sha256
            ),
            "input_source_inventory_sha256": (
                run_authority.input_source_inventory_sha256
            ),
                "source_policy_sha256": run_authority.source_policy_sha256,
                "resource_census_sha256": run_authority.resource_census_sha256,
                "qc_sid_mapping_source_sha256": (
                    run_authority.qc_sid_mapping_source_sha256
                ),
                "target_qc_capacity_reviewed": (
                    run_authority.target_qc_capacity_reviewed
                ),
                "qc_sid_mapping_reviewed": run_authority.qc_sid_mapping_reviewed,
            }
        if external != expected_external:
            raise PreopenControlStageError(
                "activated manifest does not bind private run authority"
            )
        enabled = True
    worker_text = worker_source_bytes.decode("utf-8")
    marker = "__ARV2_PREOPEN_CONTROL_CONTRACT_SHA256__"
    if worker_text.count(marker) != 1:
        raise PreopenControlStageError("worker contract marker changed")
    worker_bytes = worker_text.replace(marker, CONTRACT_SHA256).encode("utf-8")
    worker = _source(WORKER_PATH, worker_bytes)
    quality_worker = _source(QUALITY_WORKER_PATH, quality_worker_source_bytes)
    runtime = _source(RUNTIME_PATH, runtime_source_bytes)
    manifest_hash = hashlib.sha256(input_manifest_bytes).hexdigest()
    manifest_id = f"arv2-preopen-control-input-{manifest_hash[:24]}"
    manifest_key = f"{INPUT_PREFIX}manifests/{manifest_hash}.json"
    terminal_package_key = (
        f"{OUTPUT_PREFIX}packages/{manifest_hash}.json"
    )
    provisional_entry = _runtime_entry_source(
        manifest_id=manifest_id, manifest_key=manifest_key,
        manifest_hash=manifest_hash,
        manifest_count=len(input_manifest_bytes), source_set_hash="0" * 64,
        terminal_package_key=terminal_package_key,
    )
    provisional = _source(ENTRY_PATH, provisional_entry)
    source_set_hash = hashlib.sha256(canonical_json_bytes({
        "schema": "arv2-preopen-control-normalized-source-set-v1",
        "normalization": "entry_PROJECT_SOURCE_SET_SHA256_constant_zeroed",
        "source_files": [
            provisional.to_record(), worker.to_record(), quality_worker.to_record(),
            runtime.to_record(),
        ],
    })).hexdigest()
    entry = _source(ENTRY_PATH, _runtime_entry_source(
        manifest_id=manifest_id, manifest_key=manifest_key,
        manifest_hash=manifest_hash,
        manifest_count=len(input_manifest_bytes), source_set_hash=source_set_hash,
        terminal_package_key=terminal_package_key,
    ))
    files = (entry, worker, quality_worker, runtime)
    record = {
        "schema": PROJECTION_SCHEMA,
        "project_name": PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "input_manifest_id": manifest_id,
        "input_manifest_sha256": manifest_hash,
        "input_manifest_byte_count": len(input_manifest_bytes),
        "input_manifest_key": manifest_key,
        "source_files": [item.to_record() for item in files],
        "project_source_set_sha256": source_set_hash,
        "output_manifest_key_pattern": OUTPUT_PREFIX + "manifests/{sha256}.json",
        "terminal_package_key": terminal_package_key,
        "summary_name": SUMMARY_NAME,
        "enabled_runtime_source": enabled,
        "places_orders": False,
        "reads_outcomes_or_results": False,
        "requires_separate_reviewed_run_authority": True,
        "run_authority_id": (
            run_authority.pin_id if run_authority is not None else None
        ),
        "run_authority_sha256": (
            run_authority.pin_sha256 if run_authority is not None else None
        ),
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return PreopenControlQcProjection(
        projection_id=f"arv2-preopen-qc-projection-{digest[:24]}",
        projection_sha256=digest,
        project_name=PROJECT_NAME,
        backtest_name=BACKTEST_NAME,
        input_manifest_id=manifest_id,
        input_manifest_sha256=manifest_hash,
        input_manifest_byte_count=len(input_manifest_bytes),
        input_manifest_key=manifest_key,
        source_files=files,
        project_source_set_sha256=source_set_hash,
        output_manifest_key_pattern=OUTPUT_PREFIX + "manifests/{sha256}.json",
        terminal_package_key=terminal_package_key,
        summary_name=SUMMARY_NAME,
        enabled_runtime_source=enabled,
        places_orders=False,
        reads_outcomes_or_results=False,
        requires_separate_reviewed_run_authority=True,
        run_authority_id=(
            run_authority.pin_id if run_authority is not None else None
        ),
        run_authority_sha256=(
            run_authority.pin_sha256 if run_authority is not None else None
        ),
    )


__all__ = [
    "BACKTEST_NAME", "EARNINGS_INPUT_SCHEMA", "ENTRY_PATH",
    "FUNDAMENTAL_INPUT_SCHEMA", "GUIDANCE_INPUT_SCHEMA",
    "INPUT_MANIFEST_SCHEMA", "INPUT_ROLE_SCHEMAS", "PreopenControlQcProjection",
    "PreopenControlRunAuthority",
    "PreopenControlStageError", "PreopenInputShard", "PreopenOutputShard",
    "PreopenProjectSource", "PROJECT_NAME", "QUALITY_WORKER_PATH",
    "RATING_INPUT_SCHEMA", "RUNTIME_PATH", "TERMINAL_PACKAGE_SCHEMA",
    "RUN_AUTHORITY_SCHEMA", "SID_MAPPING_INPUT_SCHEMA", "SUMMARY_NAME",
    "UNIVERSE_INPUT_SCHEMA", "WORKER_PATH", "activate_preopen_input_manifest_bytes",
    "build_preopen_control_qc_projection",
    "build_preopen_input_manifest_bytes", "build_preopen_input_shard",
    "build_preopen_output_manifest_bytes", "build_preopen_output_shard",
    "canonical_json_bytes", "load_preopen_control_run_authority",
    "normalize_lean_bar_end_utc_text",
    "render_preopen_control_run_authority_candidate",
    "require_preopen_control_run_authority",
]
