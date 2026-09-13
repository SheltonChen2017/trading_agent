"""Build the disk-backed QC-discovery to ARV2 pre-open input bridge.

The bridge mechanically reauthenticates two independently produced inputs:
the complete QC Fundamentals discovery receipt and the physical Massive /
Sharadar pre-open seed candidate.  It joins only exact CUSIP values to the
permanent encoded QuantConnect SecurityIdentifier.  Current tickers remain
non-authoritative display values.  Missing, reused, or ambiguous identities
become named universe terminals.

``Reviewed`` in the result type means that both source loaders and every
physical output byte were mechanically revalidated.  It does not mean a human
has reviewed the firm ontology, q-data policy, capacity, or run authority.
Those flags remain false, and the emitted input manifest remains closed.

Importing this module performs no filesystem, provider, credential,
QuantConnect, price, outcome, result, broker, order, or trading action.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import threading
import weakref
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterator, Mapping

from data.exchange_calendar import SUPPORTED_SESSION_START, trading_sessions
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.preopen_control_acquisition import (
    CONTRACT_ID,
    CONTRACT_SHA256,
    GUIDANCE_CLOCK_POLICY_ID,
    SOURCE_VIEW_ID,
)
from research.analyst_revisions_v2_qc.fundamental_universe_discovery import (
    FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT,
    FORMAL_SOURCE_AXIS_FIRST_SESSION,
    FORMAL_SOURCE_AXIS_LAST_SESSION,
    MAX_DECISION_SESSIONS,
    ReviewedFundamentalUniverseDiscoveryReceipt,
    fundamental_discovery_artifact_binding_record,
    iter_reviewed_fundamental_discovery_terminal_shards,
    require_reviewed_fundamental_universe_discovery_receipt,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    DECISION_CHUNK_SESSION_COUNT,
    EARNINGS_INPUT_SCHEMA,
    FUNDAMENTAL_INPUT_SCHEMA,
    GUIDANCE_INPUT_SCHEMA,
    HISTORY_LOOKBACK_CALENDAR_DAYS,
    HISTORY_SYMBOL_BATCH_SIZE,
    INPUT_MANIFEST_SCHEMA,
    INPUT_ROLE_ORDER,
    INPUT_ROLE_SCHEMAS,
    MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND,
    MARKET_SUMMARY_SERIALIZED_BYTE_BOUND,
    MAX_BLOCK_COMPRESSED_INPUT_BYTES,
    MAX_BLOCK_INPUT_ROW_COUNT,
    MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES,
    MAX_BUFFERED_MARKET_OBSERVATION_COUNT,
    MAX_BUFFERED_TERMINALS,
    MAX_LOGICAL_MERGE_COMPRESSED_BYTES,
    MAX_PEER_GROUP_STATE_COUNT,
    MAX_PROJECTED_HISTORY_CALL_COUNT,
    MAX_PROJECTED_MARKET_OBSERVATION_COUNT,
    MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES,
    MAX_PROJECTED_SERIALIZED_WORKING_SET_BYTES,
    MAX_RETAINED_INPUT_COMPRESSED_BYTES,
    PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND,
    RATING_INPUT_SCHEMA,
    SID_MAPPING_INPUT_SCHEMA,
    TERMINAL_SERIALIZED_BYTE_BOUND,
    TRUTH_SOURCE_ROLE_ORDER,
    UNIVERSE_INPUT_SCHEMA,
    PreopenInputShard,
    build_preopen_input_shard,
)
from scripts.build_arv2_preopen_input import (
    PhysicalPreopenInputCandidate,
    require_physical_preopen_input_candidate,
)


BRIDGE_SCHEMA = "arv2-reviewed-historical-universe-to-preopen-bridge-v1"
ARCHIVE_MANIFEST_NAME = "closed-input-manifest.json"
ARCHIVE_SHARD_DIRECTORY = "input-shards"
ARCHIVE_EVIDENCE_DIRECTORY = "bridge-evidence"
ANALYST_EVENT_BINDING_SCHEMA = "arv2-reviewed-historical-analyst-event-binding-v1"
UNIVERSE_LIFECYCLE_BINDING_SCHEMA = (
    "arv2-reviewed-historical-universe-lifecycle-binding-v1"
)
BENCHMARK_QC_SECURITY_ID = "SPY R735QTJ8XC9X"
BENCHMARK_DISPLAY_TICKER = "SPY"
SECURITY_BATCH_SIZE = 12
MAX_ARCHIVE_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_SHARD_COUNT = 20_000
MAX_BRIDGE_SECURITY_COUNT = 100_000
MAX_BRIDGE_UNIVERSE_TERMINALS = 25_000_000
MAX_ROLE_ROWS_PER_SHARD = 20_000
MAX_EVIDENCE_ROWS_PER_SHARD = 20_000
MAX_EVIDENCE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_COMPRESSED_BYTES = 32 * 1024 * 1024
MAX_SPOOL_BYTES_PER_SECURITY_BATCH = 96 * 1024 * 1024

_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")
_QC_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}\Z")
_ANALYST_EVENT_BINDING_FIELDS = {
    "schema", "locator_sha256", "raw_row_sha256", "provider_event_id",
    "common_event_id", "source_role", "current_view_disposition",
    "censored_view_disposition", "preopen_composition_disposition",
    "preopen_composition_reason", "physical_security_id", "decision_session",
    "decision_session_ordinal", "available_at", "rating_admitted",
    "rating_seed_row_sha256", "binding_disposition", "binding_reason",
    "qc_security_id", "cusip", "issuer_id", "share_class_id", "listing_id",
    "historical_ticker", "mapping_first_session", "mapping_last_session",
    "mapping_available_at", "mapping_closure_available_at", "mapping_row_sha256",
    "q_data", "q_data_evidence_sha256", "binding_sha256",
}
_UNIVERSE_LIFECYCLE_BINDING_FIELDS = {
    "schema", "decision_session", "decision_session_ordinal", "decision_open_utc",
    "source_ordinal", "discovery_disposition", "discovery_refusal_reason",
    "qc_security_id", "cusip", "display_ticker_non_authoritative",
    "logical_security_id", "issuer_id", "share_class_id", "listing_id",
    "delisting_date", "available_at", "identity_evidence_sha256",
    "source_terminal_sha256", "mapping_row_sha256", "bridge_join_disposition",
    "bridge_join_reason", "lifecycle_evidence_only", "payoff_semantics_assigned",
    "binding_sha256",
}


class HistoricalPreopenBridgeError(ValueError):
    """The reviewed discovery and source seeds cannot be bridged safely."""


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedHistoricalPreopenInputShard:
    role: str
    security_batch_ordinal: int
    ordinal: int
    object_store_key: str
    compressed_sha256: str
    compressed_byte_count: int
    payload: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedHistoricalAnalystEventBindingShard:
    ordinal: int
    row_count: int
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    canonical_json_lines: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedHistoricalUniverseLifecycleBindingShard:
    ordinal: int
    row_count: int
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    canonical_json_lines: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class _ArchiveBinding:
    role: str
    batch: int | None
    ordinal: int | None
    relative_path: str
    sha256: str
    byte_count: int
    uncompressed_sha256: str | None
    uncompressed_byte_count: int | None
    row_count: int | None
    stat_identity: tuple[int, int, int, int, int, int]


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedHistoricalUniverseToPreopenBridge:
    schema: str
    bridge_id: str
    bridge_sha256: str
    discovery_receipt_id: str
    discovery_receipt_sha256: str
    physical_candidate_id: str
    physical_candidate_sha256: str
    accepted_risk_bridge_id: str
    accepted_risk_bridge_sha256: str
    pair_id: str
    pair_sha256: str
    derived_capture_id: str
    derived_capture_sha256: str
    sharadar_capture_id: str
    sharadar_capture_sha256: str
    discovery_eligible_universe_artifact_id: str
    discovery_eligible_universe_artifact_sha256: str
    discovery_qc_sid_mapping_artifact_id: str
    discovery_qc_sid_mapping_artifact_sha256: str
    firm_review_candidate_sha256: str
    quality_policy_sha256: str
    security_master_artifact_id: str
    security_master_artifact_sha256: str
    closed_input_manifest_sha256: str
    closed_input_manifest_byte_count: int
    closed_input_manifest_bytes: bytes = dataclasses.field(repr=False)
    input_shard_inventory_sha256: str
    input_shard_count: int
    analyst_event_binding_inventory_sha256: str
    analyst_event_binding_shard_count: int
    analyst_event_binding_row_count: int
    universe_lifecycle_binding_inventory_sha256: str
    universe_lifecycle_binding_shard_count: int
    universe_lifecycle_binding_row_count: int
    first_session: str
    last_session: str
    security_count: int
    accepted_security_count: int
    named_refusal_security_count: int
    universe_terminal_count: int
    accepted_universe_terminal_count: int
    named_refusal_universe_terminal_count: int
    current_ticker_match_count: int
    current_ticker_mismatch_count: int
    excluded_control_seed_row_count: int
    six_preopen_roles_produced: bool
    exact_qc_sid_prebound: bool
    current_ticker_used_as_identity: bool
    full_pit_universe_established_within_qc_source_scope: bool
    firm_ontology_human_reviewed: bool
    data_quality_human_reviewed: bool
    target_qc_capacity_human_reviewed: bool
    production_preopen_input_available: bool
    provider_or_credential_access_performed: bool
    quantconnect_access_performed: bool
    price_or_outcome_or_result_access_performed: bool
    order_or_trading_access_performed: bool
    _archive_root: Path = dataclasses.field(repr=False)
    _archive_root_stat: tuple[int, int, int, int, int, int] = dataclasses.field(repr=False)
    _archive_shard_dir_stat: tuple[int, int, int, int, int, int] = dataclasses.field(repr=False)
    _archive_evidence_dir_stat: tuple[int, int, int, int, int, int] = dataclasses.field(repr=False)
    _archive_bindings: tuple[_ArchiveBinding, ...] = dataclasses.field(repr=False)


_AUTHORITIES: dict[int, tuple[weakref.ReferenceType[ReviewedHistoricalUniverseToPreopenBridge], tuple[object, ...]]] = {}
_AUTHORITY_LOCK = threading.RLock()


def _canonical_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise HistoricalPreopenBridgeError(f"{name} is absent")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise HistoricalPreopenBridgeError(f"{name} is not JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise HistoricalPreopenBridgeError(f"{name} is not canonical JSON")
    return value


def _terminal_rows(receipt: ReviewedFundamentalUniverseDiscoveryReceipt) -> Iterator[dict[str, object]]:
    for shard in iter_reviewed_fundamental_discovery_terminal_shards(receipt):
        for line in shard.canonical_json_lines.splitlines(keepends=True):
            try:
                row = json.loads(line)
            except (UnicodeError, ValueError, TypeError) as exc:
                raise HistoricalPreopenBridgeError("discovery terminal is invalid") from exc
            if type(row) is not dict or canonical_json_bytes(row) != line:
                raise HistoricalPreopenBridgeError("discovery terminal is not canonical")
            yield row


def _stat(path: Path, *, directory: bool) -> tuple[int, int, int, int, int, int]:
    try:
        value = path.lstat()
    except OSError as exc:
        raise HistoricalPreopenBridgeError("bridge archive entry is unavailable") from exc
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not predicate(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or value.st_uid != os.getuid()
        or value.st_mode & 0o077
        or (not directory and value.st_nlink != 1)
    ):
        raise HistoricalPreopenBridgeError("bridge archive is not owner-only regular storage")
    return (
        value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def _write_private(path: Path, payload: bytes) -> tuple[int, int, int, int, int, int]:
    try:
        with path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise HistoricalPreopenBridgeError("bridge archive entry could not be created") from exc
    return _stat(path, directory=False)


def _read_private(path: Path, maximum: int) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    before = _stat(path, directory=False)
    if before[3] > maximum:
        raise HistoricalPreopenBridgeError("bridge archive entry exceeds its bound")
    try:
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
    except OSError as exc:
        raise HistoricalPreopenBridgeError("bridge archive entry could not be read") from exc
    after = _stat(path, directory=False)
    if before != after or len(payload) != before[3] or len(payload) > maximum:
        raise HistoricalPreopenBridgeError("bridge archive entry changed while read")
    return payload, after


def _directory_names(path: Path) -> set[str]:
    before = _stat(path, directory=True)
    try:
        names = {item.name for item in path.iterdir()}
    except OSError as exc:
        raise HistoricalPreopenBridgeError("bridge archive inventory is unavailable") from exc
    if _stat(path, directory=True) != before:
        raise HistoricalPreopenBridgeError("bridge archive inventory changed while read")
    return names


def _validate_archive_inventory(value: ReviewedHistoricalUniverseToPreopenBridge) -> None:
    if _directory_names(value._archive_root) != {
        ARCHIVE_MANIFEST_NAME, ARCHIVE_SHARD_DIRECTORY, ARCHIVE_EVIDENCE_DIRECTORY,
    }:
        raise HistoricalPreopenBridgeError("historical pre-open archive root inventory changed")
    expected_input = {
        Path(item.relative_path).name
        for item in value._archive_bindings if item.role in INPUT_ROLE_ORDER
    }
    expected_evidence = {
        Path(item.relative_path).name
        for item in value._archive_bindings
        if item.role in {"analyst_event_binding", "universe_lifecycle_binding"}
    }
    if (
        _directory_names(value._archive_root / ARCHIVE_SHARD_DIRECTORY) != expected_input
        or _directory_names(value._archive_root / ARCHIVE_EVIDENCE_DIRECTORY)
        != expected_evidence
    ):
        raise HistoricalPreopenBridgeError("historical pre-open archive leaf inventory changed")


def _fingerprint(value: ReviewedHistoricalUniverseToPreopenBridge) -> tuple[object, ...]:
    result: list[object] = []
    for field in dataclasses.fields(value):
        item = getattr(value, field.name)
        if field.name == "_archive_bindings":
            result.append(tuple(dataclasses.astuple(binding) for binding in item))
        else:
            result.append(item)
    return tuple(result)


def _forget(identity: int, reference) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _join_candidates(candidate: PhysicalPreopenInputCandidate):
    universe = _canonical_object(candidate.eligible_universe_artifact_bytes, "physical universe candidate")
    rows = universe.get("candidate_security_rows")
    if type(rows) is not list:
        raise HistoricalPreopenBridgeError("physical universe candidate rows changed")
    by_cusip: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_security: dict[str, dict[str, object]] = {}
    for row in rows:
        if type(row) is not dict or type(row.get("security_id")) is not str:
            raise HistoricalPreopenBridgeError("physical universe identity row changed")
        if row["security_id"] in by_security:
            raise HistoricalPreopenBridgeError("physical universe security repeats")
        cusips = row.get("sharadar_cusip_join_candidates")
        if type(cusips) is not list or any(
            type(item) is not str or _CUSIP.fullmatch(item) is None for item in cusips
        ) or len(cusips) != len(set(cusips)):
            raise HistoricalPreopenBridgeError("Sharadar CUSIP candidate vocabulary changed")
        by_security[row["security_id"]] = row
        for cusip in cusips:
            by_cusip[cusip].append(row)
    return by_cusip, by_security


def _discovery_identities(receipt, by_cusip):
    observed: dict[str, dict[str, object]] = {}
    conflict_sids: set[str] = set()
    terminal_count = 0
    for row in _terminal_rows(receipt):
        if row.get("disposition") != "accepted":
            continue
        terminal_count += 1
        if terminal_count > MAX_BRIDGE_UNIVERSE_TERMINALS:
            raise HistoricalPreopenBridgeError("eligible discovery census exceeds bridge bound")
        sid = row.get("qc_security_id")
        cusip = row.get("cusip")
        if type(sid) is not str or _QC_SID.fullmatch(sid) is None:
            raise HistoricalPreopenBridgeError("accepted discovery QC SID changed")
        if type(cusip) is not str or _CUSIP.fullmatch(cusip) is None:
            # Defensive only: the discovery loader normally terminalled this.
            cusip = ""
        current = observed.setdefault(sid, {
            "qc_security_id": sid, "cusip": cusip,
            "first_session": row["decision_session"],
            "last_session": row["decision_session"],
            "first_available_at": row["available_at"],
            "display_tickers": set(), "terminal_hashes": [],
        })
        if current["cusip"] != cusip:
            conflict_sids.add(sid)
        current["first_session"] = min(current["first_session"], row["decision_session"])
        current["last_session"] = max(current["last_session"], row["decision_session"])
        current["first_available_at"] = min(
            current["first_available_at"], row["available_at"]
        )
        if row.get("display_ticker_non_authoritative") is not None:
            current["display_tickers"].add(row["display_ticker_non_authoritative"])
        current["terminal_hashes"].append(row["terminal_sha256"])
    if not observed:
        raise HistoricalPreopenBridgeError("discovery has no eligible terminal rows")
    cusip_sids: dict[str, set[str]] = defaultdict(set)
    candidate_sids: dict[str, set[str]] = defaultdict(set)
    for sid, info in observed.items():
        cusip_sids[info["cusip"]].add(sid)
        matches = by_cusip.get(info["cusip"], [])
        if len(matches) == 1:
            candidate_sids[matches[0]["security_id"]].add(sid)
    identities = {}
    for sid, info in observed.items():
        cusip = info["cusip"]
        matches = by_cusip.get(cusip, [])
        reason = None
        candidate = matches[0] if len(matches) == 1 else None
        if sid in conflict_sids:
            reason = "QC_SID_exposed_conflicting_CUSIPs"
        elif not cusip:
            reason = "missing_QC_CUSIP"
        elif len(cusip_sids[cusip]) != 1:
            reason = "CUSIP_reused_by_multiple_QC_SIDs"
        elif not matches:
            reason = "CUSIP_missing_from_Sharadar_identity_seeds"
        elif len(matches) != 1:
            reason = "CUSIP_ambiguous_across_Sharadar_identities"
        elif len(candidate_sids[candidate["security_id"]]) != 1:
            reason = "Sharadar_share_class_maps_to_multiple_QC_SIDs"
        logical = (
            candidate["security_id"] if reason is None else
            "qc-join-refusal-" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:24]
        )
        display = min(info["display_tickers"]) if info["display_tickers"] else "UNKNOWN"
        current_match = bool(
            candidate is not None and display == candidate["current_snapshot_ticker_display"]
        )
        identities[sid] = {
            **info, "candidate": candidate, "logical_security_id": logical,
            "reason": reason, "display_ticker": display,
            "current_ticker_matches": current_match,
            "terminal_projection_sha256": hashlib.sha256(
                canonical_json_bytes(sorted(info["terminal_hashes"]))
            ).hexdigest(),
        }
    if len(identities) > MAX_BRIDGE_SECURITY_COUNT:
        raise HistoricalPreopenBridgeError("bridge security census exceeds bound")
    return identities, terminal_count


def _quality_measurement(*, logical: str, session: str, available_at: str,
                         candidate: PhysicalPreopenInputCandidate, identity_hash: str):
    sources = (
        ("timestamp_quality", candidate.massive_bridge_id, candidate.massive_bridge_sha256, False, True),
        ("firm_label_mapping_quality", "unreviewed-firm-ontology", hashlib.sha256(candidate.firm_review_candidate_bytes).hexdigest(), True, False),
        ("security_entity_mapping_quality", "qc-cusip-sharadar-join", identity_hash, True, False),
    )
    components = []
    for kind, source_id, source_hash, pit, accepted_risk in sources:
        semantic = {
            "kind": kind, "value": "0", "source_id": source_id,
            "source_sha256": source_hash, "payload_sha256": source_hash,
            "available_at": available_at, "point_in_time": pit,
            "accepted_risk_non_pristine": accepted_risk,
        }
        components.append({**semantic, "evidence_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()})
    semantic = {
        "security_id": logical, "measured_session": session,
        "source_id": "arv2-unreviewed-zero-quality-bridge",
        "source_sha256": hashlib.sha256(candidate.quality_policy_bytes).hexdigest(),
        "components": components,
        "measurement_method_id": "arv2-qdata-conservative-min-v1",
        "q_data": "0", "available_at": available_at, "point_in_time": True,
    }
    return {**semantic, "evidence_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()}


def _mapping_row(info, security_master_id, security_master_sha):
    candidate = info["candidate"]
    accepted = info["reason"] is None
    issuer = candidate["issuer_id"] if candidate else "unresolved-issuer-" + info["logical_security_id"][-24:]
    share = candidate["source_composite_figi"] if candidate else "unresolved-share-" + info["logical_security_id"][-24:]
    listing = candidate["listing_id"] if candidate else "unresolved-listing-" + info["logical_security_id"][-24:]
    source_hash = candidate["source_row_sha256"] if candidate else info["terminal_projection_sha256"]
    join = {
        "qc_security_id": info["qc_security_id"], "cusip": info["cusip"],
        "logical_security_id": info["logical_security_id"],
        "sharadar_source_row_sha256": source_hash,
        "discovery_terminal_projection_sha256": info["terminal_projection_sha256"],
        "current_ticker_matches": info["current_ticker_matches"],
    }
    row = {
        "schema": SID_MAPPING_INPUT_SCHEMA,
        "security_id": info["logical_security_id"],
        "qc_security_id": info["qc_security_id"], "cusip": info["cusip"] or None,
        "issuer_id": issuer, "share_class_id": share, "listing_id": listing,
        "historical_ticker": info["display_ticker"],
        "first_session": info["first_session"], "last_session": info["last_session"],
        "available_at": info["first_available_at"], "source_row_sha256": source_hash,
        "security_master_artifact_id": security_master_id,
        "security_master_artifact_sha256": security_master_sha,
        "mapping_status": (
            "reviewed_qc_fundamental_discovery_exact_cusip_join" if accepted
            else "named_refusal_unresolved_cross_vendor_join"
        ),
        "ticker_interval_evidence_sha256": hashlib.sha256(canonical_json_bytes(join)).hexdigest(),
        "qc_discovery_terminal_sha256": info["terminal_projection_sha256"],
        "current_ticker_matches": info["current_ticker_matches"],
    }
    return row


def _refusal(logical: str, info, row, reason: str):
    semantic = {
        "decision_session": row["decision_session"], "security_id": logical,
        "issuer_id": info["issuer_id"], "share_class_id": info["share_class_id"],
        "listing_id": info["listing_id"], "historical_ticker": info["historical_ticker"],
        "reason": reason, "source_id": "qc-fundamental-discovery-cusip-bridge",
        "source_sha256": row["terminal_sha256"], "available_at": row["available_at"],
    }
    return {**semantic, "refusal_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()}


def _archive_shard_path(shard: PreopenInputShard) -> str:
    return (
        f"{ARCHIVE_SHARD_DIRECTORY}/{shard.security_batch_ordinal:04d}-"
        f"{shard.role}-{shard.ordinal:04d}-{shard.compressed_sha256}.jsonl.gz"
    )


def _evidence_path(role: str, ordinal: int, digest: str) -> str:
    return f"{ARCHIVE_EVIDENCE_DIRECTORY}/{role}-{ordinal:04d}-{digest}.jsonl.gz"


def _deterministic_gzip(payload: bytes) -> bytes:
    target = io.BytesIO()
    with gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as stream:
        stream.write(payload)
    return target.getvalue()


def _write_evidence_shards(*, root: Path, role: str, rows: Iterator[dict[str, object]]):
    """Write bounded canonical evidence shards without retaining the full row set."""

    bindings: list[_ArchiveBinding] = []
    chunk: list[bytes] = []
    chunk_bytes = 0

    def flush() -> None:
        nonlocal chunk, chunk_bytes
        if not chunk:
            return
        ordinal = len(bindings)
        payload = b"".join(chunk)
        if len(payload) != chunk_bytes or len(payload) > MAX_EVIDENCE_UNCOMPRESSED_BYTES:
            raise HistoricalPreopenBridgeError("bridge evidence shard exceeds byte bound")
        compressed = _deterministic_gzip(payload)
        if len(compressed) > MAX_EVIDENCE_COMPRESSED_BYTES:
            raise HistoricalPreopenBridgeError("compressed bridge evidence exceeds byte bound")
        compressed_sha = hashlib.sha256(compressed).hexdigest()
        relative = _evidence_path(role, ordinal, compressed_sha)
        bindings.append(_ArchiveBinding(
            role=role, batch=None, ordinal=ordinal, relative_path=relative,
            sha256=compressed_sha, byte_count=len(compressed),
            uncompressed_sha256=hashlib.sha256(payload).hexdigest(),
            uncompressed_byte_count=len(payload), row_count=len(chunk),
            stat_identity=_write_private(root / relative, compressed),
        ))
        chunk = []
        chunk_bytes = 0

    for row in rows:
        encoded = canonical_json_bytes(row)
        if len(encoded) > MAX_EVIDENCE_UNCOMPRESSED_BYTES:
            raise HistoricalPreopenBridgeError("one bridge evidence row exceeds byte bound")
        if chunk and (
            len(chunk) >= MAX_EVIDENCE_ROWS_PER_SHARD
            or chunk_bytes + len(encoded) > MAX_EVIDENCE_UNCOMPRESSED_BYTES
        ):
            flush()
        chunk.append(encoded)
        chunk_bytes += len(encoded)
    flush()
    return bindings


def _binding_inventory(bindings: list[_ArchiveBinding], role: str):
    selected = [item for item in bindings if item.role == role]
    records = [{
        "ordinal": item.ordinal,
        "compressed_sha256": item.sha256,
        "compressed_byte_count": item.byte_count,
        "uncompressed_sha256": item.uncompressed_sha256,
        "uncompressed_byte_count": item.uncompressed_byte_count,
        "row_count": item.row_count,
    } for item in selected]
    return (
        hashlib.sha256(canonical_json_bytes(records)).hexdigest(),
        len(records),
        sum(item["row_count"] for item in records),
    )


def _truth_bindings(candidate, discovery, security_master_id, security_master_sha):
    universe = fundamental_discovery_artifact_binding_record(discovery)["eligible_universe_source"]
    source_seed = _canonical_object(candidate.source_seed_candidate_bytes, "source seeds")
    firm = _canonical_object(candidate.firm_review_candidate_bytes, "firm review candidate")
    values = {
        "accepted_risk_capture": (candidate.massive_bridge_id, candidate.massive_bridge_sha256),
        "eligible_universe": (universe["artifact_id"], universe["artifact_sha256"]),
        "security_master": (security_master_id, security_master_sha),
        "firm_ontology": (firm["candidate_id"], hashlib.sha256(candidate.firm_review_candidate_bytes).hexdigest()),
        "common_event": (source_seed["artifact_id"], hashlib.sha256(candidate.source_seed_candidate_bytes).hexdigest()),
        "sector_classification": (universe["artifact_id"], universe["artifact_sha256"]),
        "preopen_control": (candidate.candidate_id, candidate.candidate_sha256),
        "data_quality": ("arv2-zero-quality-policy-" + hashlib.sha256(candidate.quality_policy_bytes).hexdigest()[:24], hashlib.sha256(candidate.quality_policy_bytes).hexdigest()),
    }
    return tuple({"kind": kind, "artifact_id": values[kind][0], "artifact_sha256": values[kind][1]} for kind in TRUTH_SOURCE_ROLE_ORDER)


def _role_rows(candidate, accepted_security_ids):
    source = _canonical_object(candidate.source_seed_candidate_bytes, "accepted-risk source seeds")
    fundamental = _canonical_object(candidate.fundamental_seed_inventory_bytes, "Sharadar fundamental seeds")
    roles = source.get("role_candidates")
    if type(roles) is not dict or set(roles) != {"earnings", "guidance", "ratings"}:
        raise HistoricalPreopenBridgeError("accepted-risk role seed inventory changed")
    result = {
        "fundamentals": fundamental.get("seed_rows"),
        "earnings": roles["earnings"],
        "guidance": roles["guidance"],
        "ratings": roles["ratings"],
    }
    expected = {
        "fundamentals": FUNDAMENTAL_INPUT_SCHEMA,
        "earnings": EARNINGS_INPUT_SCHEMA,
        "guidance": GUIDANCE_INPUT_SCHEMA,
        "ratings": RATING_INPUT_SCHEMA,
    }
    filtered = {}
    excluded = 0
    for role, rows in result.items():
        if type(rows) is not list:
            raise HistoricalPreopenBridgeError(f"{role} seed inventory changed")
        kept = []
        for row in rows:
            if type(row) is not dict or row.get("schema") != expected[role]:
                raise HistoricalPreopenBridgeError(f"{role} seed row changed")
            if row.get("security_id") in accepted_security_ids:
                kept.append(row)
            else:
                excluded += 1
        filtered[role] = kept
    return filtered, excluded


def _common_event_id(provider_event_id: str) -> str:
    safe = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", provider_event_id)
    if safe is not None:
        return "benzinga-event-" + provider_event_id
    digest = hashlib.sha256(canonical_json_bytes({
        "kind": "benzinga-event", "value": provider_event_id,
    })).hexdigest()
    return "benzinga-event-" + digest[:24]


def _rating_event_context(candidate, full_ordinals):
    source = _canonical_object(candidate.source_seed_candidate_bytes, "accepted-risk source seeds")
    roles = source.get("role_candidates")
    terminals = source.get("composition_terminals")
    if type(roles) is not dict or type(terminals) is not list:
        raise HistoricalPreopenBridgeError("accepted-risk analyst event inventory changed")
    ratings = roles.get("ratings")
    if type(ratings) is not list:
        raise HistoricalPreopenBridgeError("accepted-risk rating seed inventory changed")
    by_key: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    reverse_ordinals = {ordinal: session for session, ordinal in full_ordinals.items()}
    requested_quality: set[tuple[str, str]] = set()
    for row in ratings:
        if (
            type(row) is not dict or row.get("schema") != RATING_INPUT_SCHEMA
            or type(row.get("security_id")) is not str
            or type(row.get("common_event_id")) is not str
            or type(row.get("eligible_session_ordinal")) is not int
            or type(row.get("admitted")) is not bool
        ):
            raise HistoricalPreopenBridgeError("accepted-risk rating seed row changed")
        by_key[(row["security_id"], row["common_event_id"])].append(row)
        session = reverse_ordinals.get(row["eligible_session_ordinal"])
        if session is not None:
            requested_quality.add((row["security_id"], session))
    analyst_terminals = []
    expected_terminal_fields = {
        "locator_sha256", "source_role", "provider_event_id", "raw_row_sha256",
        "current_view_disposition", "censored_view_disposition",
        "preopen_composition_disposition", "reason", "security_id",
        "terminal_sha256",
    }
    for row in terminals:
        if type(row) is not dict or set(row) != expected_terminal_fields:
            raise HistoricalPreopenBridgeError("accepted-risk composition terminal changed")
        semantic = dict(row)
        declared = semantic.pop("terminal_sha256")
        if (
            type(declared) is not str
            or hashlib.sha256(canonical_json_bytes(semantic)).hexdigest() != declared
        ):
            raise HistoricalPreopenBridgeError("accepted-risk composition terminal hash changed")
        if row["source_role"] == "analyst_ratings":
            analyst_terminals.append(row)
    return by_key, analyst_terminals, reverse_ordinals, requested_quality


def _analyst_event_binding_rows(*, candidate, identities, mappings,
                                rating_by_key, terminals, reverse_ordinals,
                                quality_by_key):
    by_physical: dict[str, list[dict[str, object]]] = defaultdict(list)
    for info in identities.values():
        physical = info["candidate"]
        if physical is not None:
            by_physical[physical["security_id"]].append(info)
    for terminal in terminals:
        physical_id = terminal["security_id"]
        provider_id = terminal["provider_event_id"]
        common_id = (
            _common_event_id(provider_id) if type(provider_id) is str
            else "refused-event-" + terminal["raw_row_sha256"][:24]
        )
        rating_candidates = (
            rating_by_key.get((physical_id, common_id), [])
            if type(physical_id) is str else []
        )
        rating = rating_candidates[0] if len(rating_candidates) == 1 else None
        decision_session = (
            reverse_ordinals.get(rating["eligible_session_ordinal"])
            if rating is not None else None
        )
        joined = by_physical.get(physical_id, []) if type(physical_id) is str else []
        info = joined[0] if len(joined) == 1 else None
        mapping = mappings.get(info["qc_security_id"]) if info is not None else None
        reason = None
        if terminal["preopen_composition_disposition"] not in {
            "emitted", "coalesced_exact_control_anchor",
        }:
            reason = "analyst_event_was_not_emitted_to_the_control_seed"
        elif type(physical_id) is not str:
            reason = "analyst_event_has_no_physical_security_identity"
        elif len(joined) != 1:
            reason = "analyst_event_security_join_is_missing_or_ambiguous"
        elif info["reason"] is not None:
            reason = info["reason"]
        elif len(rating_candidates) != 1:
            reason = "analyst_event_has_no_unique_rating_seed"
        elif rating["admitted"] is not True:
            reason = "analyst_event_rating_seed_is_not_admitted"
        elif decision_session is None:
            reason = "analyst_event_session_is_outside_bridge_geometry"
        quality = quality_by_key.get((physical_id, decision_session))
        if reason is None and quality is None:
            reason = "analyst_event_has_no_same_session_universe_quality_binding"
        semantic = {
            "schema": ANALYST_EVENT_BINDING_SCHEMA,
            "locator_sha256": terminal["locator_sha256"],
            "raw_row_sha256": terminal["raw_row_sha256"],
            "provider_event_id": provider_id,
            "common_event_id": common_id,
            "source_role": terminal["source_role"],
            "current_view_disposition": terminal["current_view_disposition"],
            "censored_view_disposition": terminal["censored_view_disposition"],
            "preopen_composition_disposition": terminal["preopen_composition_disposition"],
            "preopen_composition_reason": terminal["reason"],
            "physical_security_id": physical_id,
            "decision_session": decision_session,
            "decision_session_ordinal": (
                rating["eligible_session_ordinal"] if rating is not None else None
            ),
            "available_at": rating["available_at"] if rating is not None else None,
            "rating_admitted": rating["admitted"] if rating is not None else None,
            "rating_seed_row_sha256": (
                hashlib.sha256(canonical_json_bytes(rating)).hexdigest()
                if rating is not None else None
            ),
            "binding_disposition": "accepted" if reason is None else "named_refusal",
            "binding_reason": reason,
            "qc_security_id": info["qc_security_id"] if info is not None else None,
            "cusip": info["cusip"] if info is not None else None,
            "issuer_id": mapping["issuer_id"] if mapping is not None else None,
            "share_class_id": mapping["share_class_id"] if mapping is not None else None,
            "listing_id": mapping["listing_id"] if mapping is not None else None,
            "historical_ticker": (
                mapping["historical_ticker"] if mapping is not None else None
            ),
            "mapping_first_session": (
                mapping["first_session"] if mapping is not None else None
            ),
            "mapping_last_session": (
                mapping["last_session"] if mapping is not None else None
            ),
            "mapping_available_at": (
                mapping["available_at"] if mapping is not None else None
            ),
            "mapping_closure_available_at": None,
            "mapping_row_sha256": mapping["row_sha256"] if mapping is not None else None,
            "q_data": quality[0] if reason is None else None,
            "q_data_evidence_sha256": quality[1] if reason is None else None,
        }
        yield {
            **semantic,
            "binding_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
        }


def _universe_lifecycle_binding_rows(discovery, identities, mappings):
    """Preserve every discovery terminal; delisting is evidence, never payoff."""

    for source in _terminal_rows(discovery):
        info = identities.get(source.get("qc_security_id"))
        mapping = mappings.get(source.get("qc_security_id")) if info is not None else None
        if source["disposition"] != "accepted":
            join_disposition = "not_applicable_discovery_terminal"
            join_reason = source["refusal_reason"]
        elif info is None:
            join_disposition = "named_refusal"
            join_reason = "accepted_discovery_identity_missing_from_bridge"
        elif info["reason"] is not None:
            join_disposition = "named_refusal"
            join_reason = info["reason"]
        else:
            join_disposition = "accepted"
            join_reason = None
        semantic = {
            "schema": UNIVERSE_LIFECYCLE_BINDING_SCHEMA,
            "decision_session": source["decision_session"],
            "decision_session_ordinal": source["decision_session_ordinal"],
            "decision_open_utc": source["decision_open_utc"],
            "source_ordinal": source["source_ordinal"],
            "discovery_disposition": source["disposition"],
            "discovery_refusal_reason": source["refusal_reason"],
            "qc_security_id": source["qc_security_id"],
            "cusip": source["cusip"],
            "display_ticker_non_authoritative": source["display_ticker_non_authoritative"],
            "logical_security_id": info["logical_security_id"] if info is not None else None,
            "issuer_id": mapping["issuer_id"] if mapping is not None else source["issuer_id"],
            "share_class_id": mapping["share_class_id"] if mapping is not None else source["share_class_id"],
            "listing_id": mapping["listing_id"] if mapping is not None else source["listing_id"],
            "delisting_date": source["delisting_date"],
            "available_at": source["available_at"],
            "identity_evidence_sha256": source["identity_evidence_sha256"],
            "source_terminal_sha256": source["terminal_sha256"],
            "mapping_row_sha256": mapping["row_sha256"] if mapping is not None else None,
            "bridge_join_disposition": join_disposition,
            "bridge_join_reason": join_reason,
            "lifecycle_evidence_only": True,
            "payoff_semantics_assigned": False,
        }
        yield {
            **semantic,
            "binding_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
        }


def _write_role_shards(*, root: Path, role: str, batch: int,
                       first_session: str, last_session: str, rows):
    normalized = sorted((dict(row) for row in rows), key=canonical_json_bytes)
    if len({canonical_json_bytes(row) for row in normalized}) != len(normalized):
        raise HistoricalPreopenBridgeError(f"{role} rows repeat in one security batch")
    chunks = [normalized[offset:offset + MAX_ROLE_ROWS_PER_SHARD]
              for offset in range(0, len(normalized), MAX_ROLE_ROWS_PER_SHARD)] or [[]]
    built = []
    bindings = []
    for ordinal, chunk in enumerate(chunks):
        shard = build_preopen_input_shard(
            role=role, security_batch_ordinal=batch, ordinal=ordinal,
            partition_first_session=first_session,
            partition_last_session=last_session, rows=chunk,
        )
        relative = _archive_shard_path(shard)
        path = root / relative
        binding = _ArchiveBinding(
            role=role, batch=batch, ordinal=ordinal, relative_path=relative,
            sha256=shard.compressed_sha256, byte_count=shard.compressed_byte_count,
            uncompressed_sha256=shard.uncompressed_sha256,
            uncompressed_byte_count=shard.uncompressed_byte_count,
            row_count=shard.row_count,
            stat_identity=_write_private(path, shard.payload),
        )
        built.append(shard.descriptor())
        bindings.append(binding)
    return built, bindings


def _manifest(*, descriptors, batch_metrics, batch_session_memberships,
              session_geometry, peer_keys,
              candidate, discovery, security_master_id, security_master_sha):
    descriptors = list(descriptors)
    inventory_hash = hashlib.sha256(canonical_json_bytes(descriptors)).hexdigest()
    role_bindings = []
    for role in INPUT_ROLE_ORDER:
        selected = [item for item in descriptors if item["role"] == role]
        role_bindings.append({
            "role": role,
            "descriptor_projection_sha256": hashlib.sha256(canonical_json_bytes(selected)).hexdigest(),
            "shard_count": len(selected), "row_count": sum(item["row_count"] for item in selected),
            "compressed_byte_count": sum(item["compressed_byte_count"] for item in selected),
            "uncompressed_byte_count": sum(item["uncompressed_byte_count"] for item in selected),
        })
    sid_descriptors = [item for item in descriptors if item["role"] == "sid_mapping"]
    sid_projection = canonical_json_bytes(sid_descriptors)
    sid_hash = hashlib.sha256(sid_projection).hexdigest()
    sessions = sorted(session_geometry)
    first = discovery.first_session
    last = discovery.last_session
    expected_sessions = tuple(
        item.isoformat()
        for item in trading_sessions(date.fromisoformat(first), date.fromisoformat(last))
    )
    if (
        first != FORMAL_SOURCE_AXIS_FIRST_SESSION
        or last != FORMAL_SOURCE_AXIS_LAST_SESSION
        or len(expected_sessions) != FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT
        or len(expected_sessions) > MAX_DECISION_SESSIONS
        or tuple(sessions) != expected_sessions
    ):
        raise HistoricalPreopenBridgeError("bridged universe does not span discovery endpoints")
    calendar_observations = (date.fromisoformat(last) - date.fromisoformat(first)).days + HISTORY_LOOKBACK_CALENDAR_DAYS + 1
    projected_calls = 1 + sum(4 for item in batch_metrics if item["distinct_accepted_security_count"])
    projected_observations = calendar_observations + sum(
        item["distinct_accepted_security_count"] * 4 * calendar_observations
        for item in batch_metrics
    )
    terminal_count = sum(item["universe_terminal_count"] for item in batch_metrics)
    projected_output_bytes = terminal_count * TERMINAL_SERIALIZED_BYTE_BOUND
    retained_compressed = sum(item["compressed_byte_count"] for item in descriptors)
    peer_count = len(peer_keys)
    maximum_working = max(
        item["uncompressed_input_byte_count"]
        + peer_count * PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND
        + max(
            item["maximum_buffered_market_observation_count"] * MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND,
            min(MAX_BUFFERED_TERMINALS, DECISION_CHUNK_SESSION_COUNT * item["distinct_security_count"])
            * TERMINAL_SERIALIZED_BYTE_BOUND,
        )
        for item in batch_metrics
    )
    if (
        projected_calls > MAX_PROJECTED_HISTORY_CALL_COUNT
        or projected_observations > MAX_PROJECTED_MARKET_OBSERVATION_COUNT
        or projected_output_bytes > MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES
        or retained_compressed > MAX_RETAINED_INPUT_COMPRESSED_BYTES
        or peer_count > MAX_PEER_GROUP_STATE_COUNT
        or maximum_working > MAX_PROJECTED_SERIALIZED_WORKING_SET_BYTES
    ):
        raise HistoricalPreopenBridgeError("bridged pre-open resources exceed reviewed stage bounds")
    discovery_binding = fundamental_discovery_artifact_binding_record(discovery)["eligible_universe_source"]
    decision_sessions = [session_geometry[session] for session in sessions]
    session_chunk_by_session = {
        session: index // DECISION_CHUNK_SESSION_COUNT
        for index, session in enumerate(sessions)
    }
    projected_output_shard_count = sum(
        len({session_chunk_by_session[session] for session in memberships})
        for memberships in batch_session_memberships.values()
    )
    return {
        "schema": INPUT_MANIFEST_SCHEMA, "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "benchmark_security_id": BENCHMARK_QC_SECURITY_ID,
        "benchmark_ticker": BENCHMARK_DISPLAY_TICKER,
        "first_session": first, "last_session": last,
        "calculation_session": candidate.calculation_session,
        "shards": descriptors, "input_source_inventory_sha256": inventory_hash,
        "input_role_bindings": role_bindings,
        "truth_source_bindings": list(_truth_bindings(
            candidate, discovery, security_master_id, security_master_sha
        )),
        "eligible_universe_source": {
            "artifact_id": discovery_binding["artifact_id"],
            "content_sha256": discovery_binding["artifact_sha256"],
            "artifact_sha256": discovery_binding["artifact_sha256"],
            "byte_count": discovery_binding["byte_count"],
        },
        "qc_sid_mapping_source": {
            "artifact_id": "arv2-qc-sid-mapping-" + sid_hash[:24],
            "content_sha256": sid_hash, "artifact_sha256": sid_hash,
            "byte_count": len(sid_projection),
            "row_count": sum(item["row_count"] for item in sid_descriptors),
            "mapping_semantics": (
                "canonical_content_addressed_exact_QC_SecurityIdentifier_to_"
                "Sharadar_CUSIP_permaticker_FIGI_binding;_current_ticker_is_"
                "display_only_and_the_runtime_must_use_self.symbol_encoded_SID"
            ),
        },
        "source_policy": {
            "rating_source_view": SOURCE_VIEW_ID,
            "rating_source_complete": candidate.rating_source_complete_for_frozen_query_and_accepted_risk_policy,
            "earnings_source_complete": candidate.earnings_source_complete_for_frozen_query_and_accepted_risk_policy,
            "earnings_pit_policy_id": "owner-accepted-current-row-risk-v1",
            "guidance_source_complete": candidate.guidance_source_complete_for_frozen_query_and_accepted_risk_policy,
            "guidance_clock_policy_id": GUIDANCE_CLOCK_POLICY_ID,
            "unknown_event_archive_or_clock_is_zero": False,
        },
        "construction_gate": {
            "external_private_run_authority": None,
            "external_private_run_authority_required": True,
            "outcome_access_authorized": False, "result_access_authorized": False,
            "orders_authorized": False,
        },
        "resource_census": {
            "decision_session_count": len(sessions), "decision_sessions": decision_sessions,
            "eligible_universe_terminal_count": terminal_count,
            "distinct_security_count": sum(item["distinct_security_count"] for item in batch_metrics),
            "security_batch_count": len(batch_metrics),
            "decision_chunk_session_count": DECISION_CHUNK_SESSION_COUNT,
            "history_symbol_batch_size": HISTORY_SYMBOL_BATCH_SIZE,
            "full_sample_security_history_pass_count": 2,
            "history_calls_per_nonempty_security_batch": 4,
            "deduplicated_benchmark_history_call_count": 1,
            "history_lookback_calendar_days": HISTORY_LOOKBACK_CALENDAR_DAYS,
            "maximum_symbols_in_one_security_batch": max(item["distinct_accepted_security_count"] for item in batch_metrics),
            "maximum_buffered_market_observation_count": max(item["maximum_buffered_market_observation_count"] for item in batch_metrics),
            "maximum_derived_market_summary_count": max(item["maximum_derived_market_summary_count"] for item in batch_metrics),
            "peer_group_state_count": peer_count,
            "maximum_peer_group_state_count": MAX_PEER_GROUP_STATE_COUNT,
            "peer_group_state_serialized_byte_bound": PEER_GROUP_STATE_SERIALIZED_BYTE_BOUND,
            "projected_batched_history_call_count": projected_calls,
            "projected_total_market_observation_count": projected_observations,
            "maximum_projected_market_observation_count": MAX_PROJECTED_MARKET_OBSERVATION_COUNT,
            "projected_output_uncompressed_byte_upper_bound": projected_output_bytes,
            "maximum_projected_output_uncompressed_bytes": MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES,
            "compressed_input_byte_count": retained_compressed,
            "maximum_retained_input_compressed_bytes": MAX_RETAINED_INPUT_COMPRESSED_BYTES,
            "uncompressed_input_byte_count": sum(item["uncompressed_byte_count"] for item in descriptors),
            "maximum_buffered_terminal_count": MAX_BUFFERED_TERMINALS,
            "maximum_one_security_batch_compressed_input_bytes": MAX_BLOCK_COMPRESSED_INPUT_BYTES,
            "maximum_one_security_batch_uncompressed_input_bytes": MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES,
            "maximum_one_security_batch_input_row_count": MAX_BLOCK_INPUT_ROW_COUNT,
            "maximum_one_batch_market_observation_count": MAX_BUFFERED_MARKET_OBSERVATION_COUNT,
            "maximum_projected_history_call_count": MAX_PROJECTED_HISTORY_CALL_COUNT,
            "target_qc_tier_capacity_requires_private_authority": True,
            "market_observation_serialized_byte_bound": MARKET_OBSERVATION_SERIALIZED_BYTE_BOUND,
            "market_summary_serialized_byte_bound": MARKET_SUMMARY_SERIALIZED_BYTE_BOUND,
            "terminal_serialized_byte_bound": TERMINAL_SERIALIZED_BYTE_BOUND,
            "maximum_projected_serialized_working_set_bytes": maximum_working,
            "projected_output_shard_count": projected_output_shard_count,
            "maximum_logical_merge_cursor_count": len(batch_metrics),
            "maximum_logical_merge_compressed_bytes": MAX_LOGICAL_MERGE_COMPRESSED_BYTES,
            "physical_output_partition_order": "decision_chunk_ordinal_then_security_batch_ordinal",
            "logical_output_order": "decision_session_then_security_id",
            "object_store_total_byte_quota_requires_private_authority": True,
            "full_terminal_set_retained_in_memory": False,
            "qc_runtime_full_input_set_retained_in_memory": False,
            "host_manifest_projection_retains_all_compressed_input_payloads": False,
            "physical_receipt_output_payload_iteration_is_bounded": True,
            "security_batches": batch_metrics,
        },
    }


def build_reviewed_historical_universe_to_preopen_bridge(
    discovery_receipt: ReviewedFundamentalUniverseDiscoveryReceipt,
    physical_candidate: PhysicalPreopenInputCandidate,
    archive_root: Path,
) -> ReviewedHistoricalUniverseToPreopenBridge:
    """Build one closed, disk-backed six-role bridge without external access."""

    try:
        discovery = require_reviewed_fundamental_universe_discovery_receipt(discovery_receipt)
        candidate = require_physical_preopen_input_candidate(physical_candidate)
    except Exception as exc:
        raise HistoricalPreopenBridgeError("bridge source authority revalidation failed") from exc
    if (
        discovery.first_session != candidate.first_session
        or discovery.last_session != candidate.last_session
    ):
        raise HistoricalPreopenBridgeError("discovery and physical candidate geometry differ")
    if not isinstance(archive_root, Path) or archive_root.exists() or archive_root.is_symlink():
        raise HistoricalPreopenBridgeError("bridge archive must be a new Path")
    by_cusip, _ = _join_candidates(candidate)
    identities, eligible_terminal_count = _discovery_identities(discovery, by_cusip)
    identity_projection = []
    for sid in sorted(identities):
        item = identities[sid]
        identity_projection.append({
            "qc_security_id": sid, "cusip": item["cusip"],
            "logical_security_id": item["logical_security_id"],
            "join_disposition": "accepted" if item["reason"] is None else "named_refusal",
            "reason": item["reason"],
            "terminal_projection_sha256": item["terminal_projection_sha256"],
            "current_ticker_matches": item["current_ticker_matches"],
        })
    security_master_record = {
        "schema": "arv2-qc-cusip-sharadar-security-master-projection-v1",
        "discovery_receipt_id": discovery.receipt_id,
        "discovery_receipt_sha256": discovery.receipt_sha256,
        "physical_candidate_id": candidate.candidate_id,
        "physical_candidate_sha256": candidate.candidate_sha256,
        "identity_count": len(identity_projection),
        "identity_projection_sha256": hashlib.sha256(canonical_json_bytes(identity_projection)).hexdigest(),
        "current_ticker_used_as_identity": False,
        "human_reviewed": False,
    }
    security_master_sha = hashlib.sha256(canonical_json_bytes(security_master_record)).hexdigest()
    security_master_id = "arv2-qc-cusip-security-master-" + security_master_sha[:24]
    mappings = {
        sid: _mapping_row(info, security_master_id, security_master_sha)
        for sid, info in identities.items()
    }
    for row in mappings.values():
        semantic = dict(row)
        semantic.pop("row_sha256", None)
        row["row_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()

    ordered_logical = sorted(item["logical_security_id"] for item in identities.values())
    if len(ordered_logical) != len(set(ordered_logical)):
        raise HistoricalPreopenBridgeError("bridge logical security identity collides")
    logical_to_batch = {
        logical: index // SECURITY_BATCH_SIZE for index, logical in enumerate(ordered_logical)
    }
    sid_by_logical = {item["logical_security_id"]: sid for sid, item in identities.items()}
    accepted_security_ids = {
        item["logical_security_id"] for item in identities.values() if item["reason"] is None
    }
    role_rows, excluded_seed_rows = _role_rows(candidate, accepted_security_ids)
    full_ordinals = {
        session.isoformat(): index
        for index, session in enumerate(trading_sessions(
            SUPPORTED_SESSION_START, date.fromisoformat(discovery.last_session)
        ))
    }
    rating_by_key, analyst_terminals, reverse_ordinals, requested_quality = (
        _rating_event_context(candidate, full_ordinals)
    )

    try:
        archive_root.mkdir(mode=0o700, parents=False)
        shard_dir = archive_root / ARCHIVE_SHARD_DIRECTORY
        shard_dir.mkdir(mode=0o700)
        evidence_dir = archive_root / ARCHIVE_EVIDENCE_DIRECTORY
        evidence_dir.mkdir(mode=0o700)
    except OSError as exc:
        raise HistoricalPreopenBridgeError("bridge archive directories could not be created") from exc
    _stat(archive_root, directory=True)
    _stat(shard_dir, directory=True)
    _stat(evidence_dir, directory=True)
    descriptors = []
    bindings = []
    batch_sessions: dict[int, set[str]] = defaultdict(set)
    batch_terminal_counts: Counter[int] = Counter()
    batch_accepted_counts: Counter[int] = Counter()
    batch_session_accepted: dict[int, Counter[str]] = defaultdict(Counter)
    session_geometry: dict[str, dict[str, object]] = {}
    peer_keys: set[tuple[str, str, str]] = set()
    quality_by_key: dict[tuple[str, str], tuple[str, str]] = {}

    with tempfile.TemporaryDirectory(prefix="arv2-preopen-bridge-") as spool_root_text:
        spool_root = Path(spool_root_text)
        handles = {}
        try:
            for source_row in _terminal_rows(discovery):
                if source_row.get("disposition") != "accepted":
                    continue
                info = identities[source_row["qc_security_id"]]
                logical = info["logical_security_id"]
                batch = logical_to_batch[logical]
                mapping = mappings[source_row["qc_security_id"]]
                common = {
                    "schema": UNIVERSE_INPUT_SCHEMA,
                    "decision_session": source_row["decision_session"],
                    "decision_session_ordinal": full_ordinals[source_row["decision_session"]],
                    "decision_open_utc": source_row["decision_open_utc"],
                    "security_id": logical, "qc_security_id": source_row["qc_security_id"],
                    "issuer_id": mapping["issuer_id"], "share_class_id": mapping["share_class_id"],
                    "listing_id": mapping["listing_id"], "historical_ticker": info["display_ticker"],
                    "security_master_row_sha256": mapping["ticker_interval_evidence_sha256"],
                    "qc_sid_mapping_row_sha256": mapping["row_sha256"],
                }
                if info["reason"] is None:
                    identity_hash = source_row["identity_evidence_sha256"]
                    measurement = _quality_measurement(
                        logical=logical, session=source_row["decision_session"],
                        available_at=source_row["available_at"], candidate=candidate,
                        identity_hash=identity_hash,
                    )
                    universe_row = {
                        **common, "disposition": "accepted",
                        "sector_id": "morningstar-sector-" + str(source_row["morningstar_sector_code"]),
                        "industry_id": "morningstar-industry-" + str(source_row["morningstar_industry_code"]),
                        "q_data": "0", "source_id": discovery.receipt_id,
                        "q_data_measurement": measurement,
                        "source_sha256": discovery.receipt_sha256,
                        "identity_evidence_sha256": source_row["identity_evidence_sha256"],
                        "identity_available_at": source_row["available_at"],
                        "classification_evidence_sha256": source_row["classification_evidence_sha256"],
                        "classification_available_at": source_row["available_at"],
                        "q_data_evidence_sha256": measurement["evidence_sha256"],
                        "q_data_available_at": source_row["available_at"],
                    }
                    quality_key = (logical, source_row["decision_session"])
                    if quality_key in requested_quality:
                        quality_by_key[quality_key] = (
                            universe_row["q_data"], universe_row["q_data_evidence_sha256"]
                        )
                    batch_accepted_counts[batch] += 1
                    batch_session_accepted[batch][source_row["decision_session"]] += 1
                    peer_keys.add((source_row["decision_session"], "sector", universe_row["sector_id"]))
                    peer_keys.add((source_row["decision_session"], "industry", universe_row["industry_id"]))
                else:
                    universe_row = {
                        **common, "disposition": "named_refusal",
                        "census_refusal": _refusal(logical, mapping, source_row, info["reason"]),
                    }
                path = spool_root / f"universe-{batch:04d}.jsonl"
                handle = handles.get(batch)
                if handle is None:
                    handle = path.open("ab")
                    handles[batch] = handle
                handle.write(canonical_json_bytes(universe_row))
                batch_sessions[batch].add(source_row["decision_session"])
                batch_terminal_counts[batch] += 1
                geometry = session_geometry.setdefault(source_row["decision_session"], {
                    "decision_session": source_row["decision_session"],
                    "decision_open_utc": source_row["decision_open_utc"],
                    "decision_session_ordinal": full_ordinals[source_row["decision_session"]],
                    "terminal_count": 0,
                })
                if geometry["decision_open_utc"] != source_row["decision_open_utc"]:
                    raise HistoricalPreopenBridgeError("discovery session open changed")
                geometry["terminal_count"] += 1
        finally:
            for handle in handles.values():
                handle.close()

        batch_count = max(logical_to_batch.values()) + 1
        batch_metrics = []
        for batch in range(batch_count):
            batch_logicals = ordered_logical[
                batch * SECURITY_BATCH_SIZE:(batch + 1) * SECURITY_BATCH_SIZE
            ]
            universe_path = spool_root / f"universe-{batch:04d}.jsonl"
            try:
                universe_payload = universe_path.read_bytes()
            except OSError as exc:
                raise HistoricalPreopenBridgeError("universe spool is incomplete") from exc
            if len(universe_payload) > MAX_SPOOL_BYTES_PER_SECURITY_BATCH:
                raise HistoricalPreopenBridgeError("one universe security batch exceeds spool bound")
            universe_rows = [json.loads(line) for line in universe_payload.splitlines(keepends=True)]
            keys = [(row["decision_session"], row["security_id"]) for row in universe_rows]
            if len(keys) != len(set(keys)):
                raise HistoricalPreopenBridgeError("universe security/session repeats")
            rows_by_role = {"universe": universe_rows, "sid_mapping": []}
            for logical in batch_logicals:
                rows_by_role["sid_mapping"].append(mappings[sid_by_logical[logical]])
            for role in ("fundamentals", "earnings", "guidance", "ratings"):
                rows_by_role[role] = [
                    row for row in role_rows[role] if row["security_id"] in set(batch_logicals)
                ]
            before = len(descriptors)
            for role in INPUT_ROLE_ORDER:
                built, physical = _write_role_shards(
                    root=archive_root, role=role, batch=batch,
                    first_session=discovery.first_session,
                    last_session=discovery.last_session, rows=rows_by_role[role],
                )
                descriptors.extend(built)
                bindings.extend(physical)
            selected = descriptors[before:]
            compressed = sum(item["compressed_byte_count"] for item in selected)
            uncompressed = sum(item["uncompressed_byte_count"] for item in selected)
            row_count = sum(item["row_count"] for item in selected)
            accepted_security_count = sum(
                identities[sid_by_logical[logical]]["reason"] is None
                for logical in batch_logicals
            )
            buffered = (accepted_security_count * 2 + 1) * (
                (date.fromisoformat(discovery.last_session) - date.fromisoformat(discovery.first_session)).days
                + HISTORY_LOOKBACK_CALENDAR_DAYS + 1
            )
            if (
                compressed > MAX_BLOCK_COMPRESSED_INPUT_BYTES
                or uncompressed > MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES
                or row_count > MAX_BLOCK_INPUT_ROW_COUNT
                or buffered > MAX_BUFFERED_MARKET_OBSERVATION_COUNT
            ):
                raise HistoricalPreopenBridgeError("one bridge security batch exceeds stage capacity")
            batch_metrics.append({
                "security_batch_ordinal": batch,
                "first_session": discovery.first_session, "last_session": discovery.last_session,
                "first_security_id": batch_logicals[0], "last_security_id": batch_logicals[-1],
                "decision_session_count": len(batch_sessions[batch]),
                "universe_terminal_count": batch_terminal_counts[batch],
                "distinct_security_count": len(batch_logicals),
                "distinct_accepted_security_count": accepted_security_count,
                "distinct_accepted_history_symbol_count": accepted_security_count,
                "projected_history_call_count": 4 if accepted_security_count else 0,
                "projected_total_market_observation_count": accepted_security_count * 4 * ((date.fromisoformat(discovery.last_session) - date.fromisoformat(discovery.first_session)).days + HISTORY_LOOKBACK_CALENDAR_DAYS + 1),
                "maximum_buffered_market_observation_count": buffered,
                "maximum_derived_market_summary_count": max(batch_session_accepted[batch].values(), default=0),
                "compressed_input_byte_count": compressed,
                "uncompressed_input_byte_count": uncompressed,
                "input_row_count": row_count,
            })

    bindings.extend(_write_evidence_shards(
        root=archive_root, role="analyst_event_binding",
        rows=_analyst_event_binding_rows(
            candidate=candidate, identities=identities, mappings=mappings,
            rating_by_key=rating_by_key, terminals=analyst_terminals,
            reverse_ordinals=reverse_ordinals, quality_by_key=quality_by_key,
        ),
    ))
    bindings.extend(_write_evidence_shards(
        root=archive_root, role="universe_lifecycle_binding",
        rows=_universe_lifecycle_binding_rows(discovery, identities, mappings),
    ))
    if len(bindings) > MAX_ARCHIVE_SHARD_COUNT:
        raise HistoricalPreopenBridgeError("bridge physical shard inventory exceeds bound")

    if len(descriptors) > MAX_ARCHIVE_SHARD_COUNT:
        raise HistoricalPreopenBridgeError("bridge shard inventory exceeds bound")
    try:
        require_reviewed_fundamental_universe_discovery_receipt(discovery)
        require_physical_preopen_input_candidate(candidate)
    except Exception as exc:
        raise HistoricalPreopenBridgeError("bridge source changed during construction") from exc
    manifest = _manifest(
        descriptors=descriptors, batch_metrics=batch_metrics,
        batch_session_memberships=batch_sessions,
        session_geometry=session_geometry, peer_keys=peer_keys,
        candidate=candidate, discovery=discovery,
        security_master_id=security_master_id, security_master_sha=security_master_sha,
    )
    manifest_bytes = canonical_json_bytes(manifest)
    if len(manifest_bytes) > MAX_ARCHIVE_MANIFEST_BYTES:
        raise HistoricalPreopenBridgeError("closed input manifest exceeds byte bound")
    manifest_stat = _write_private(archive_root / ARCHIVE_MANIFEST_NAME, manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    bindings.insert(0, _ArchiveBinding(
        role="closed_input_manifest", batch=None, ordinal=None,
        relative_path=ARCHIVE_MANIFEST_NAME, sha256=manifest_hash,
        byte_count=len(manifest_bytes), uncompressed_sha256=None,
        uncompressed_byte_count=None, row_count=None, stat_identity=manifest_stat,
    ))
    root_stat = _stat(archive_root, directory=True)
    shard_dir_stat = _stat(shard_dir, directory=True)
    evidence_dir_stat = _stat(evidence_dir, directory=True)
    analyst_inventory, analyst_shards, analyst_rows = _binding_inventory(
        bindings, "analyst_event_binding"
    )
    lifecycle_inventory, lifecycle_shards, lifecycle_rows = _binding_inventory(
        bindings, "universe_lifecycle_binding"
    )
    accepted_count = sum(item["reason"] is None for item in identities.values())
    mismatch_count = sum(
        item["reason"] is None and item["current_ticker_matches"] is False
        for item in identities.values()
    )
    discovery_binding = fundamental_discovery_artifact_binding_record(discovery)
    record = {
        "schema": BRIDGE_SCHEMA,
        "discovery_receipt_id": discovery.receipt_id,
        "discovery_receipt_sha256": discovery.receipt_sha256,
        "physical_candidate_id": candidate.candidate_id,
        "physical_candidate_sha256": candidate.candidate_sha256,
        "accepted_risk_bridge_id": candidate.massive_bridge_id,
        "accepted_risk_bridge_sha256": candidate.massive_bridge_sha256,
        "pair_id": candidate.pair_id,
        "pair_sha256": candidate.pair_sha256,
        "derived_capture_id": candidate.derived_capture_id,
        "derived_capture_sha256": candidate.derived_capture_sha256,
        "sharadar_capture_id": candidate.sharadar_capture_id,
        "sharadar_capture_sha256": candidate.sharadar_capture_sha256,
        "discovery_eligible_universe_artifact_id": (
            discovery_binding["eligible_universe_source"]["artifact_id"]
        ),
        "discovery_eligible_universe_artifact_sha256": (
            discovery_binding["eligible_universe_source"]["artifact_sha256"]
        ),
        "discovery_qc_sid_mapping_artifact_id": (
            discovery_binding["qc_sid_mapping_source"]["artifact_id"]
        ),
        "discovery_qc_sid_mapping_artifact_sha256": (
            discovery_binding["qc_sid_mapping_source"]["artifact_sha256"]
        ),
        "firm_review_candidate_sha256": hashlib.sha256(
            candidate.firm_review_candidate_bytes
        ).hexdigest(),
        "quality_policy_sha256": hashlib.sha256(candidate.quality_policy_bytes).hexdigest(),
        "security_master_artifact_id": security_master_id,
        "security_master_artifact_sha256": security_master_sha,
        "closed_input_manifest_sha256": manifest_hash,
        "closed_input_manifest_byte_count": len(manifest_bytes),
        "input_shard_inventory_sha256": manifest["input_source_inventory_sha256"],
        "input_shard_count": len(descriptors), "first_session": discovery.first_session,
        "analyst_event_binding_inventory_sha256": analyst_inventory,
        "analyst_event_binding_shard_count": analyst_shards,
        "analyst_event_binding_row_count": analyst_rows,
        "universe_lifecycle_binding_inventory_sha256": lifecycle_inventory,
        "universe_lifecycle_binding_shard_count": lifecycle_shards,
        "universe_lifecycle_binding_row_count": lifecycle_rows,
        "last_session": discovery.last_session, "security_count": len(identities),
        "accepted_security_count": accepted_count,
        "named_refusal_security_count": len(identities) - accepted_count,
        "universe_terminal_count": eligible_terminal_count,
        "accepted_universe_terminal_count": sum(batch_accepted_counts.values()),
        "named_refusal_universe_terminal_count": eligible_terminal_count - sum(batch_accepted_counts.values()),
        "current_ticker_match_count": accepted_count - mismatch_count,
        "current_ticker_mismatch_count": mismatch_count,
        "excluded_control_seed_row_count": excluded_seed_rows,
        "six_preopen_roles_produced": True, "exact_qc_sid_prebound": True,
        "current_ticker_used_as_identity": False,
        "full_pit_universe_established_within_qc_source_scope": True,
        "firm_ontology_human_reviewed": False, "data_quality_human_reviewed": False,
        "target_qc_capacity_human_reviewed": False,
        "production_preopen_input_available": False,
        "provider_or_credential_access_performed": False,
        "quantconnect_access_performed": False,
        "price_or_outcome_or_result_access_performed": False,
        "order_or_trading_access_performed": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(ReviewedHistoricalUniverseToPreopenBridge)
    values = {
        **record, "bridge_id": "arv2-reviewed-historical-preopen-" + digest[:24],
        "bridge_sha256": digest, "closed_input_manifest_bytes": manifest_bytes,
        "_archive_root": archive_root.absolute(), "_archive_root_stat": root_stat,
        "_archive_shard_dir_stat": shard_dir_stat,
        "_archive_evidence_dir_stat": evidence_dir_stat,
        "_archive_bindings": tuple(bindings),
    }
    if set(values) != {field.name for field in dataclasses.fields(value)}:
        raise HistoricalPreopenBridgeError("bridge field inventory changed")
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(value))
    return require_reviewed_historical_universe_to_preopen_bridge(value)


def require_reviewed_historical_universe_to_preopen_bridge(
    value: ReviewedHistoricalUniverseToPreopenBridge,
) -> ReviewedHistoricalUniverseToPreopenBridge:
    """Reauthenticate the typed bridge and immutable physical inventory."""

    if type(value) is not ReviewedHistoricalUniverseToPreopenBridge:
        raise HistoricalPreopenBridgeError("historical pre-open bridge type changed")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None or authority[0]() is not value
        or authority[1] != _fingerprint(value)
    ):
        raise HistoricalPreopenBridgeError("historical pre-open bridge lost builder authority")
    if (
        _stat(value._archive_root, directory=True) != value._archive_root_stat
        or _stat(value._archive_root / ARCHIVE_SHARD_DIRECTORY, directory=True)
        != value._archive_shard_dir_stat
        or _stat(value._archive_root / ARCHIVE_EVIDENCE_DIRECTORY, directory=True)
        != value._archive_evidence_dir_stat
    ):
        raise HistoricalPreopenBridgeError("historical pre-open archive directory changed")
    _validate_archive_inventory(value)
    for binding in value._archive_bindings:
        if type(binding) is not _ArchiveBinding:
            raise HistoricalPreopenBridgeError("historical pre-open archive binding changed")
        if _stat(value._archive_root / binding.relative_path, directory=False) != binding.stat_identity:
            raise HistoricalPreopenBridgeError("historical pre-open archive entry identity changed")
    exact_true = (
        value.six_preopen_roles_produced, value.exact_qc_sid_prebound,
        value.full_pit_universe_established_within_qc_source_scope,
    )
    exact_false = (
        value.current_ticker_used_as_identity, value.firm_ontology_human_reviewed,
        value.data_quality_human_reviewed, value.target_qc_capacity_human_reviewed,
        value.production_preopen_input_available,
        value.provider_or_credential_access_performed, value.quantconnect_access_performed,
        value.price_or_outcome_or_result_access_performed,
        value.order_or_trading_access_performed,
    )
    if (
        value.schema != BRIDGE_SCHEMA
        or any(type(item) is not bool or item is not True for item in exact_true)
        or any(type(item) is not bool or item is not False for item in exact_false)
        or value.closed_input_manifest_byte_count != len(value.closed_input_manifest_bytes)
        or value.closed_input_manifest_sha256
        != hashlib.sha256(value.closed_input_manifest_bytes).hexdigest()
        or value.input_shard_count != sum(
            item.role in INPUT_ROLE_ORDER for item in value._archive_bindings
        )
    ):
        raise HistoricalPreopenBridgeError("historical pre-open bridge boundary changed")
    analyst_inventory = _binding_inventory(
        list(value._archive_bindings), "analyst_event_binding"
    )
    lifecycle_inventory = _binding_inventory(
        list(value._archive_bindings), "universe_lifecycle_binding"
    )
    if analyst_inventory != (
        value.analyst_event_binding_inventory_sha256,
        value.analyst_event_binding_shard_count,
        value.analyst_event_binding_row_count,
    ) or lifecycle_inventory != (
        value.universe_lifecycle_binding_inventory_sha256,
        value.universe_lifecycle_binding_shard_count,
        value.universe_lifecycle_binding_row_count,
    ):
        raise HistoricalPreopenBridgeError("historical bridge evidence inventory changed")
    manifest = _canonical_object(value.closed_input_manifest_bytes, "closed input manifest")
    if (
        manifest.get("schema") != INPUT_MANIFEST_SCHEMA
        or manifest.get("input_source_inventory_sha256") != value.input_shard_inventory_sha256
        or manifest.get("construction_gate", {}).get("external_private_run_authority") is not None
        or manifest.get("construction_gate", {}).get("external_private_run_authority_required") is not True
        or tuple(item.get("role") for item in manifest.get("input_role_bindings", []))
        != INPUT_ROLE_ORDER
    ):
        raise HistoricalPreopenBridgeError("historical pre-open manifest binding changed")
    record = {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {
            "bridge_id", "bridge_sha256", "closed_input_manifest_bytes",
            "_archive_root", "_archive_root_stat", "_archive_shard_dir_stat",
            "_archive_evidence_dir_stat",
            "_archive_bindings",
        }
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        value.bridge_sha256 != digest
        or value.bridge_id != "arv2-reviewed-historical-preopen-" + digest[:24]
    ):
        raise HistoricalPreopenBridgeError("historical pre-open bridge identity changed")
    return value


def iter_reviewed_historical_preopen_input_shards(
    value: ReviewedHistoricalUniverseToPreopenBridge,
) -> Iterator[ReviewedHistoricalPreopenInputShard]:
    """Yield one hash- and stat-reauthenticated compressed shard at a time."""

    value = require_reviewed_historical_universe_to_preopen_bridge(value)
    manifest = _canonical_object(value.closed_input_manifest_bytes, "closed input manifest")
    descriptors = manifest["shards"]
    bindings = [item for item in value._archive_bindings if item.role in INPUT_ROLE_ORDER]
    if len(bindings) != len(descriptors):
        raise HistoricalPreopenBridgeError("archive shard inventory changed")
    for descriptor, binding in zip(descriptors, bindings, strict=True):
        value = require_reviewed_historical_universe_to_preopen_bridge(value)
        if (
            descriptor["role"] != binding.role
            or descriptor["security_batch_ordinal"] != binding.batch
            or descriptor["ordinal"] != binding.ordinal
            or descriptor["compressed_sha256"] != binding.sha256
            or descriptor["compressed_byte_count"] != binding.byte_count
            or descriptor["uncompressed_sha256"] != binding.uncompressed_sha256
            or descriptor["uncompressed_byte_count"] != binding.uncompressed_byte_count
            or descriptor["row_count"] != binding.row_count
        ):
            raise HistoricalPreopenBridgeError("archive shard descriptor changed")
        payload, observed = _read_private(
            value._archive_root / binding.relative_path,
            MAX_BLOCK_COMPRESSED_INPUT_BYTES,
        )
        if (
            observed != binding.stat_identity or len(payload) != binding.byte_count
            or hashlib.sha256(payload).hexdigest() != binding.sha256
        ):
            raise HistoricalPreopenBridgeError("archive shard payload changed")
        yield ReviewedHistoricalPreopenInputShard(
            role=binding.role, security_batch_ordinal=binding.batch,
            ordinal=binding.ordinal, object_store_key=descriptor["object_store_key"],
            compressed_sha256=binding.sha256,
            compressed_byte_count=binding.byte_count, payload=payload,
        )


def _read_evidence_binding(value, binding, *, schema, fields):
    payload, observed = _read_private(
        value._archive_root / binding.relative_path, MAX_EVIDENCE_COMPRESSED_BYTES
    )
    if (
        observed != binding.stat_identity or len(payload) != binding.byte_count
        or hashlib.sha256(payload).hexdigest() != binding.sha256
        or type(binding.uncompressed_byte_count) is not int
        or type(binding.uncompressed_sha256) is not str
        or type(binding.row_count) is not int
    ):
        raise HistoricalPreopenBridgeError("historical bridge evidence payload changed")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(binding.uncompressed_byte_count + 1)
            if stream.read(1):
                raise HistoricalPreopenBridgeError("historical bridge evidence has trailing data")
    except (OSError, EOFError) as exc:
        raise HistoricalPreopenBridgeError("historical bridge evidence gzip changed") from exc
    if (
        len(raw) != binding.uncompressed_byte_count
        or len(raw) > MAX_EVIDENCE_UNCOMPRESSED_BYTES
        or hashlib.sha256(raw).hexdigest() != binding.uncompressed_sha256
    ):
        raise HistoricalPreopenBridgeError("historical bridge evidence content changed")
    lines = raw.splitlines(keepends=True)
    if len(lines) != binding.row_count:
        raise HistoricalPreopenBridgeError("historical bridge evidence row census changed")
    for line in lines:
        row = _canonical_object(line, "historical bridge evidence row")
        if set(row) != fields or row.get("schema") != schema:
            raise HistoricalPreopenBridgeError("historical bridge evidence schema changed")
        semantic = dict(row)
        declared = semantic.pop("binding_sha256")
        if (
            type(declared) is not str
            or hashlib.sha256(canonical_json_bytes(semantic)).hexdigest() != declared
        ):
            raise HistoricalPreopenBridgeError("historical bridge evidence hash changed")
    return raw


def iter_reviewed_historical_analyst_event_binding_shards(
    value: ReviewedHistoricalUniverseToPreopenBridge,
) -> Iterator[ReviewedHistoricalAnalystEventBindingShard]:
    """Yield authenticated locator-to-permanent-identity analyst bindings."""

    value = require_reviewed_historical_universe_to_preopen_bridge(value)
    bindings = [
        item for item in value._archive_bindings if item.role == "analyst_event_binding"
    ]
    for expected, binding in enumerate(bindings):
        value = require_reviewed_historical_universe_to_preopen_bridge(value)
        if binding.ordinal != expected:
            raise HistoricalPreopenBridgeError("analyst event evidence ordinal changed")
        raw = _read_evidence_binding(
            value, binding, schema=ANALYST_EVENT_BINDING_SCHEMA,
            fields=_ANALYST_EVENT_BINDING_FIELDS,
        )
        yield ReviewedHistoricalAnalystEventBindingShard(
            ordinal=expected, row_count=binding.row_count,
            compressed_sha256=binding.sha256,
            compressed_byte_count=binding.byte_count,
            uncompressed_sha256=binding.uncompressed_sha256,
            uncompressed_byte_count=binding.uncompressed_byte_count,
            canonical_json_lines=raw,
        )


def iter_reviewed_historical_universe_lifecycle_binding_shards(
    value: ReviewedHistoricalUniverseToPreopenBridge,
) -> Iterator[ReviewedHistoricalUniverseLifecycleBindingShard]:
    """Yield every authenticated QC discovery terminal with lifecycle evidence."""

    value = require_reviewed_historical_universe_to_preopen_bridge(value)
    bindings = [
        item for item in value._archive_bindings
        if item.role == "universe_lifecycle_binding"
    ]
    for expected, binding in enumerate(bindings):
        value = require_reviewed_historical_universe_to_preopen_bridge(value)
        if binding.ordinal != expected:
            raise HistoricalPreopenBridgeError(
                "universe lifecycle evidence ordinal changed"
            )
        raw = _read_evidence_binding(
            value, binding, schema=UNIVERSE_LIFECYCLE_BINDING_SCHEMA,
            fields=_UNIVERSE_LIFECYCLE_BINDING_FIELDS,
        )
        yield ReviewedHistoricalUniverseLifecycleBindingShard(
            ordinal=expected, row_count=binding.row_count,
            compressed_sha256=binding.sha256,
            compressed_byte_count=binding.byte_count,
            uncompressed_sha256=binding.uncompressed_sha256,
            uncompressed_byte_count=binding.uncompressed_byte_count,
            canonical_json_lines=raw,
        )


def historical_preopen_bridge_binding_record(
    value: ReviewedHistoricalUniverseToPreopenBridge,
) -> dict[str, object]:
    value = require_reviewed_historical_universe_to_preopen_bridge(value)
    return {
        "schema": "arv2-historical-preopen-bridge-binding-v1",
        "bridge_id": value.bridge_id, "bridge_sha256": value.bridge_sha256,
        "discovery_receipt_id": value.discovery_receipt_id,
        "discovery_receipt_sha256": value.discovery_receipt_sha256,
        "physical_candidate_id": value.physical_candidate_id,
        "physical_candidate_sha256": value.physical_candidate_sha256,
        "accepted_risk_bridge_id": value.accepted_risk_bridge_id,
        "accepted_risk_bridge_sha256": value.accepted_risk_bridge_sha256,
        "pair_id": value.pair_id, "pair_sha256": value.pair_sha256,
        "derived_capture_id": value.derived_capture_id,
        "derived_capture_sha256": value.derived_capture_sha256,
        "sharadar_capture_id": value.sharadar_capture_id,
        "sharadar_capture_sha256": value.sharadar_capture_sha256,
        "security_master_artifact_id": value.security_master_artifact_id,
        "security_master_artifact_sha256": value.security_master_artifact_sha256,
        "closed_input_manifest_sha256": value.closed_input_manifest_sha256,
        "input_shard_inventory_sha256": value.input_shard_inventory_sha256,
        "input_shard_count": value.input_shard_count,
        "analyst_event_binding_inventory_sha256": (
            value.analyst_event_binding_inventory_sha256
        ),
        "analyst_event_binding_shard_count": value.analyst_event_binding_shard_count,
        "analyst_event_binding_row_count": value.analyst_event_binding_row_count,
        "universe_lifecycle_binding_inventory_sha256": (
            value.universe_lifecycle_binding_inventory_sha256
        ),
        "universe_lifecycle_binding_shard_count": (
            value.universe_lifecycle_binding_shard_count
        ),
        "universe_lifecycle_binding_row_count": value.universe_lifecycle_binding_row_count,
        "full_pit_universe_established_within_qc_source_scope": True,
        "six_preopen_roles_produced": True,
        "firm_ontology_human_reviewed": False,
        "data_quality_human_reviewed": False,
        "target_qc_capacity_human_reviewed": False,
        "production_preopen_input_available": False,
    }


__all__ = [
    "ANALYST_EVENT_BINDING_SCHEMA", "ARCHIVE_EVIDENCE_DIRECTORY",
    "ARCHIVE_MANIFEST_NAME", "ARCHIVE_SHARD_DIRECTORY",
    "BENCHMARK_DISPLAY_TICKER", "BENCHMARK_QC_SECURITY_ID", "BRIDGE_SCHEMA",
    "HistoricalPreopenBridgeError", "ReviewedHistoricalPreopenInputShard",
    "ReviewedHistoricalAnalystEventBindingShard",
    "ReviewedHistoricalUniverseLifecycleBindingShard",
    "ReviewedHistoricalUniverseToPreopenBridge",
    "UNIVERSE_LIFECYCLE_BINDING_SCHEMA",
    "build_reviewed_historical_universe_to_preopen_bridge",
    "historical_preopen_bridge_binding_record",
    "iter_reviewed_historical_analyst_event_binding_shards",
    "iter_reviewed_historical_preopen_input_shards",
    "iter_reviewed_historical_universe_lifecycle_binding_shards",
    "require_reviewed_historical_universe_to_preopen_bridge",
]
