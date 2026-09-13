"""Compact, content-addressed source contract for one formal ARV2 QC run.

This module is deliberately offline.  It turns already-reviewed scorer/evaluator
input rows into deterministic gzip shards and projects a no-orders LEAN entry
point.  The entry point reads those exact shards, delegates the market joins and
formal calculation to an exact separately projected cloud evaluator, writes 26
content-addressed report-family objects through a reviewed write-once protocol,
and emits only their compact root manifest through custom summary statistics.
Both channels are required parts of the one-use result-return path.

Nothing here reads a file, environment variable, credential, provider, QC
account, or market outcome.  A projection is not evidence that its source fits a
QC tier, compiles, executes, or is equivalent to the reviewed local evaluator.
Those facts are separate, owner-pinned pre-submission gates.
"""
from __future__ import annotations

import ast
import base64
import dataclasses
import gzip
import hashlib
import json
import re
import textwrap
from datetime import date, datetime, timezone
from typing import Iterable, Mapping, Sequence

from .formal_run_protocol import (
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    EVALUATION_ID,
    FORMAL_PRIMARY_FOLD_IDS,
    HORIZONS,
    PRIMARY_HORIZON,
    SOURCE_VIEW_IDS,
    TERMINAL_POLICY_ID,
    ArtifactBinding,
    FormalRunCandidate,
    require_artifact_binding,
    require_formal_run_candidate,
)


class FormalQcRuntimeProjectionError(ValueError):
    """A compact input, capacity receipt, or source projection is invalid."""


SCHEMA = "arv2-formal-qc-runtime-projection-v2"
STATUS = "offline_compact_projection_cloud_truth_and_submission_authority_pending"
AUTHORITY = (
    "pure_values_only_no_filesystem_environment_credential_provider_qc_market_"
    "result_deployment_order_or_trading_authority"
)
INPUT_MANIFEST_SCHEMA = "arv2-formal-qc-compact-input-manifest-v2"
COMPRESSED_SHARD_SCHEMA = "arv2-formal-qc-canonical-jsonl-gzip-shard-v1"
FORMAL_CONTRACT_SCHEMA = "arv2-formal-qc-formal-input-contract-v1"
CONTRIBUTION_SEED_SCHEMA = "arv2-formal-qc-contribution-seed-v1"
DECISION_JOIN_SCHEMA = "arv2-formal-qc-decision-market-join-v1"
ECONOMIC_JOIN_SCHEMA = "arv2-formal-qc-economic-market-join-v1"
DAILY_REQUIREMENT_SCHEMA = "arv2-formal-qc-daily-total-return-requirement-v1"
MINUTE_REQUIREMENT_SCHEMA = "arv2-formal-qc-prepublication-minute-requirement-v1"
TERMINAL_OBJECT_SCHEMA = "arv2-formal-qc-terminal-disposition-v2"
CLOUD_EVALUATOR_INTERFACE_SCHEMA = "arv2-formal-qc-cloud-evaluator-interface-v1"
RESOURCE_CONTRACT_SCHEMA = "arv2-formal-qc-compact-resource-census-v2"
UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA = (
    "arv2-upstream-one-fold-materialization-capacity-gate-v1"
)
CAPACITY_REVIEW_SCHEMA = "arv2-formal-qc-capacity-review-receipt-v1"
AGGREGATE_RESULT_SCHEMA = "arv2-formal-cloud-evaluation-aggregate-v1"
SUMMARY_RECEIPT_SCHEMA = "arv2-formal-qc-summary-statistic-receipt-v2"
FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA = (
    "arv2-formal-cloud-evaluation-output-envelope-v1"
)
REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA = (
    "arv2-formal-report-family-object-reference-v1"
)
MARKET_OBSERVATION_PANEL_SCHEMA = "arv2-formal-qc-market-observation-panel-v1"
DAILY_OBSERVATION_SCHEMA = "arv2-formal-qc-daily-open-observation-v1"
MINUTE_OBSERVATION_SCHEMA = "arv2-formal-qc-prepublication-minute-observation-v1"

# Compatibility aliases retained for callers that used the earlier name.  A
# "decision object" is now a compact decision-market join shard, never a
# repeated raw-outcome transport.
DECISION_OBJECT_SCHEMA = DECISION_JOIN_SCHEMA
OUTPUT_OBJECT_SCHEMA = AGGREGATE_RESULT_SCHEMA
OUTPUT_INDEX_SCHEMA = SUMMARY_RECEIPT_SCHEMA

PROJECT_NAME = "ARV2_FORMAL_STOCK_2020_2025_20260911"
BACKTEST_NAME = "ARV2 formal stock outcomes 2020-2025 plus 2021-2025 sensitivity"
ENTRY_PROJECT_PATH = "main.py"
ENTRY_CLASS_NAME = "AnalystRevisionsV2FormalOutcomeRuntime"
CLOUD_EVALUATOR_PROJECT_PATH = (
    "research/analyst_revisions_v2_qc/formal_cloud_evaluator.py"
)
FORMAL_EVALUATOR_PROJECT_PATH = (
    "research/analyst_revisions_v2_qc/formal_evaluation.py"
)
FORMAL_RESULT_PERSISTENCE_PROJECT_PATH = (
    "research/analyst_revisions_v2_qc/formal_result_persistence.py"
)
CLOUD_EVALUATOR_ENTRYPOINT = "execute_compact_formal_evaluation"
MODULE_CARRIER_BASE64_CHARACTERS = 48_000
MODULE_CARRIER_LITERAL_CHARACTERS = 120
MAX_PROJECTED_SOURCE_CHARACTERS = 60_000
SLEEVE_HOLDING_SESSIONS = 20
FORMAL_INPUT_PREFIX = "arv2/formal/input/manifests/"
FORMAL_INPUT_CONTENT_PREFIX = "arv2/formal/input/content/"
FORMAL_OUTPUT_PREFIX = "arv2/formal/output/report-families/"
REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX = FORMAL_OUTPUT_PREFIX
FORMAL_OUTPUT_INDEX_PREFIX = "summary-statistics://ARV2_RESULT_META/"
SUMMARY_META_NAME = "ARV2_RESULT_META"
SUMMARY_CHUNK_PREFIX = "ARV2_RESULT_"
SUMMARY_CHUNK_NAME_WIDTH = 3
SHARD_COMPRESSION = "gzip-mtime-zero"
SHARD_CONTENT_ENCODING = "canonical-json-lines-utf8-lf"
SHARD_ROLE_ORDER = (
    "formal_contract",
    "contribution_seeds",
    "decision_joins",
    "economic_joins",
    "daily_requirements",
    "minute_requirements",
    "terminal_dispositions",
)
SHARD_ROW_SCHEMAS = {
    "formal_contract": FORMAL_CONTRACT_SCHEMA,
    "contribution_seeds": CONTRIBUTION_SEED_SCHEMA,
    "decision_joins": DECISION_JOIN_SCHEMA,
    "economic_joins": ECONOMIC_JOIN_SCHEMA,
    "daily_requirements": DAILY_REQUIREMENT_SCHEMA,
    "minute_requirements": MINUTE_REQUIREMENT_SCHEMA,
    "terminal_dispositions": TERMINAL_OBJECT_SCHEMA,
}

# These are serialization safety bounds, not claims about a QC subscription.
# Actual plan limits are carried by a reviewed, content-authenticated capacity
# receipt and may be lower.
ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES = 48 * 1024 * 1024
ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES = 192 * 1024 * 1024
ABSOLUTE_MAX_SHARD_ROWS = 2_000_000
ABSOLUTE_MAX_SHARDS = 512
ABSOLUTE_MAX_SUMMARY_CHUNKS = 100
ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS = 4_000
ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES = 200_000
FORMAL_RESULT_FAMILY_OBJECT_COUNT = 26
MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES = 4_194_304
MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES = 4_200_000
MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES = 109_051_904
MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES = 109_200_000
MAX_JSON_DEPTH = 24
INPUT_EXPANSION_MEMORY_MULTIPLIER = 8
FORMAL_RESULT_WORKING_SET_MEMORY_BYTES = (
    MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
    + MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
    * INPUT_EXPANSION_MEMORY_MULTIPLIER
    + ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES * 4
)
OBSERVATION_MEMORY_BYTES_PER_REQUIREMENT = 512
# The cloud facade retains two SHA-256 commitments per unique minute fact so a
# later view/security activation can authenticate reuse without retaining the
# full row.  Include conservative Python mapping/key overhead, not only the 64
# raw digest bytes.
MINUTE_COMMITMENT_MEMORY_BYTES_PER_REQUIREMENT = 512
# One exact (source view, common-event component) commitment survives for the
# full evaluation stream in the frozen evaluator.  Budget conservatively for
# the evaluator dictionaries plus the runtime's independent census set.
COMPONENT_COMMITMENT_MEMORY_BYTES = 1_024
HISTORY_BATCH_MEMORY_BYTES_PER_SECURITY = 2_000_000
STREAM_EVALUATOR_BYTES_PER_ECONOMIC_JOIN = 32_768
STREAM_DECODE_WORKING_SET_MULTIPLIER = 2
MARKET_OBSERVATION_COLLECTION_PASSES = 2
DAILY_HISTORY_BLOCK_CALENDAR_DAYS = 32
MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS = 48

PHYSICAL_DEPENDENCIES = (
    "exact reviewed production compact input shards",
    "exact reviewed arv2_formal_cloud_evaluator source and local/cloud equivalence receipt",
    "QuantConnect Python LEAN AlgorithmImports and permanent Symbol-ID decoding",
    "batched US-equity TotalReturn daily History and minute History semantics",
    "reviewed terminal-payoff availability and benchmark-splice inputs; Delisting.price forbidden",
    "multipart private Object Store input upload usable by the individual account",
    "separately reviewed private Object Store output capacity for exactly 26 write-once family objects",
    "representative full-census node/object/project/history capacity receipt",
    "separate reviewed upstream truth plus one-fold scoring materialization capacity artifact",
    "non-self-mintable owner/reviewer execution and result-read trust root",
    "observed target-tier custom-summary-statistic name/value/count limits",
    "reviewed root-summary plus 26-object save/reopen/hash result transport",
    "separately authorized backtests/read result receipt parser",
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def canonical_json_bytes(value: object) -> bytes:
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
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise FormalQcRuntimeProjectionError("value is not canonical JSON") from exc


def _json_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise FormalQcRuntimeProjectionError(f"{name} must be nonempty exact bytes")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FormalQcRuntimeProjectionError(f"{name} is not UTF-8 JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise FormalQcRuntimeProjectionError(f"{name} is not one canonical JSON object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalQcRuntimeProjectionError(f"{name} is not a lowercase SHA-256")
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalQcRuntimeProjectionError(f"{name} is not a safe identifier")
    return value


def _safe_key(value: object, name: str) -> str:
    if (
        type(value) is not str
        or _SAFE_KEY.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise FormalQcRuntimeProjectionError(f"{name} is not a safe Object Store key")
    return value


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        raise FormalQcRuntimeProjectionError(f"{name} is not an exact integer >= {minimum}")
    return value


def _utc_text(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise FormalQcRuntimeProjectionError(f"{name} is not canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FormalQcRuntimeProjectionError(f"{name} is not canonical UTC text") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FormalQcRuntimeProjectionError(f"{name} is not UTC")
    return value


def _iso_date(value: object, name: str) -> str:
    if type(value) is not str:
        raise FormalQcRuntimeProjectionError(f"{name} is not an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FormalQcRuntimeProjectionError(f"{name} is not an ISO date") from exc
    if parsed.isoformat() != value:
        raise FormalQcRuntimeProjectionError(f"{name} is not a canonical ISO date")
    return value


def _exact_mapping(value: object, fields: frozenset[str], name: str) -> Mapping[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise FormalQcRuntimeProjectionError(f"{name} fields changed")
    return value


def _json_tree_exact(value: object, depth: int = 0) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if value is None or type(value) in (str, bool, int):
        return not (type(value) is int and abs(value) > 10**18)
    if type(value) is list:
        return all(_json_tree_exact(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _json_tree_exact(item, depth + 1)
            for key, item in value.items()
        )
    return False


def build_daily_market_requirement_id(
    *, security_id: str, session: str
) -> str:
    """Content-identify one TotalReturn-adjusted session-open observation."""

    _safe_id(security_id, "daily requirement security_id")
    _iso_date(session, "daily requirement session")
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": DAILY_REQUIREMENT_SCHEMA,
                "security_id": security_id,
                "session": session,
                "observation": "session_open_total_return_adjusted",
            }
        )
    ).hexdigest()
    return "arv2-daily-requirement-" + digest


def build_minute_market_requirement_id(
    *, security_id: str, publication_at_utc: str
) -> str:
    """Identify the last tradable minute strictly before one publication."""

    _safe_id(security_id, "minute requirement security_id")
    _utc_text(publication_at_utc, "publication_at_utc")
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": MINUTE_REQUIREMENT_SCHEMA,
                "security_id": security_id,
                "publication_at_utc": publication_at_utc,
                "price_selection": "last_tradable_minute_strictly_before_publication",
            }
        )
    ).hexdigest()
    return "arv2-minute-requirement-" + digest


@dataclasses.dataclass(frozen=True, slots=True)
class QcObjectPayloadBinding:
    role: str
    schema: str
    object_store_key: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def build_qc_object_payload_binding(
    *, role: str, schema: str, object_store_key: str, payload: bytes
) -> QcObjectPayloadBinding:
    _safe_id(role, "object role")
    _safe_id(schema, "object schema")
    _safe_key(object_store_key, "Object Store key")
    if type(payload) is not bytes or not payload:
        raise FormalQcRuntimeProjectionError("Object Store payload must be exact bytes")
    return QcObjectPayloadBinding(
        role=role,
        schema=schema,
        object_store_key=object_store_key,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
    )


def require_qc_object_payload_binding(value: QcObjectPayloadBinding) -> QcObjectPayloadBinding:
    if type(value) is not QcObjectPayloadBinding:
        raise FormalQcRuntimeProjectionError("Object Store binding type changed")
    _safe_id(value.role, "object role")
    _safe_id(value.schema, "object schema")
    _safe_key(value.object_store_key, "Object Store key")
    _sha(value.content_sha256, "Object Store content hash")
    _positive_int(value.byte_count, "Object Store byte count")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcCompressedShard:
    role: str
    ordinal: int
    schema: str
    object_store_key: str
    compression: str
    content_encoding: str
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    row_count: int
    payload: bytes = dataclasses.field(repr=False)

    def descriptor(self) -> dict[str, object]:
        return {
            "role": self.role,
            "ordinal": self.ordinal,
            "schema": self.schema,
            "object_store_key": self.object_store_key,
            "compression": self.compression,
            "content_encoding": self.content_encoding,
            "compressed_sha256": self.compressed_sha256,
            "compressed_byte_count": self.compressed_byte_count,
            "uncompressed_sha256": self.uncompressed_sha256,
            "uncompressed_byte_count": self.uncompressed_byte_count,
            "row_count": self.row_count,
        }


def _canonical_json_lines(rows: Sequence[Mapping[str, object]]) -> bytes:
    if type(rows) not in (tuple, list):
        raise FormalQcRuntimeProjectionError("shard rows must be an exact tuple or list")
    lines: list[bytes] = []
    for row in rows:
        if type(row) is not dict or not _json_tree_exact(row):
            raise FormalQcRuntimeProjectionError("shard row is not an exact bounded JSON object")
        lines.append(canonical_json_bytes(row))
    return b"".join(lines)


def build_formal_qc_compressed_shard(
    *, role: str, ordinal: int, rows: Sequence[Mapping[str, object]]
) -> FormalQcCompressedShard:
    if role not in SHARD_ROLE_ORDER:
        raise FormalQcRuntimeProjectionError("compact shard role changed")
    _positive_int(ordinal, "shard ordinal", allow_zero=True)
    if type(rows) not in (tuple, list):
        raise FormalQcRuntimeProjectionError("shard rows must be an exact tuple or list")
    normalized = tuple(dict(row) if type(row) is dict else row for row in rows)
    if any(
        type(row) is not dict or row.get("schema") != SHARD_ROW_SCHEMAS[role]
        for row in normalized
    ):
        raise FormalQcRuntimeProjectionError("compact shard row schema changed")
    encoded_rows = tuple(canonical_json_bytes(row) for row in normalized)
    if len(set(encoded_rows)) != len(encoded_rows):
        raise FormalQcRuntimeProjectionError("compact shard contains a duplicate row")
    raw = _canonical_json_lines(normalized)
    if len(normalized) > ABSOLUTE_MAX_SHARD_ROWS or len(raw) > ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES:
        raise FormalQcRuntimeProjectionError("compact shard exceeds an absolute safety bound")
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(payload) > ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES:
        raise FormalQcRuntimeProjectionError("compressed shard exceeds an absolute safety bound")
    digest = hashlib.sha256(payload).hexdigest()
    key = f"{FORMAL_INPUT_CONTENT_PREFIX}{role}/{ordinal:04d}-{digest}.jsonl.gz"
    return FormalQcCompressedShard(
        role=role,
        ordinal=ordinal,
        schema=COMPRESSED_SHARD_SCHEMA,
        object_store_key=key,
        compression=SHARD_COMPRESSION,
        content_encoding=SHARD_CONTENT_ENCODING,
        compressed_sha256=digest,
        compressed_byte_count=len(payload),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        uncompressed_byte_count=len(raw),
        row_count=len(normalized),
        payload=payload,
    )


def require_formal_qc_compressed_shard(value: FormalQcCompressedShard) -> FormalQcCompressedShard:
    if type(value) is not FormalQcCompressedShard:
        raise FormalQcRuntimeProjectionError("compact shard type changed")
    rows = _decode_shard_rows(value.payload) if _shard_scalars_are_plausible(value) else None
    rebuilt = (
        build_formal_qc_compressed_shard(
            role=value.role,
            ordinal=value.ordinal,
            rows=rows,
        )
        if rows is not None
        else None
    )
    if rebuilt is None or any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcCompressedShard)
    ):
        raise FormalQcRuntimeProjectionError("compact shard content identity changed")
    return value


def _shard_scalars_are_plausible(value: FormalQcCompressedShard) -> bool:
    return (
        value.role in SHARD_ROLE_ORDER
        and type(value.ordinal) is int
        and value.ordinal >= 0
        and value.schema == COMPRESSED_SHARD_SCHEMA
        and value.compression == SHARD_COMPRESSION
        and value.content_encoding == SHARD_CONTENT_ENCODING
        and type(value.payload) is bytes
    )


def _decode_shard_rows(payload: bytes) -> list[dict[str, object]]:
    if type(payload) is not bytes or len(payload) > ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES:
        raise FormalQcRuntimeProjectionError("compressed shard payload changed")
    try:
        raw = gzip.decompress(payload)
    except (OSError, EOFError) as exc:
        raise FormalQcRuntimeProjectionError("compressed shard is not valid gzip") from exc
    if len(raw) > ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES:
        raise FormalQcRuntimeProjectionError("uncompressed shard exceeds its absolute bound")
    rows: list[dict[str, object]] = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise FormalQcRuntimeProjectionError("JSONL shard line lacks LF terminator")
        row = _json_object(line, "JSONL shard row")
        if not _json_tree_exact(row):
            raise FormalQcRuntimeProjectionError("JSONL shard row is not an exact JSON tree")
        rows.append(row)
    if raw and not raw.endswith(b"\n"):
        raise FormalQcRuntimeProjectionError("JSONL shard lacks final LF")
    return rows


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcRuntimeResourceCensus:
    shard_count: int
    compressed_input_byte_count: int
    maximum_compressed_object_byte_count: int
    uncompressed_input_byte_count: int
    formal_contract_count: int
    contribution_seed_count: int
    decision_join_count: int
    component_commitment_count: int
    economic_join_count: int
    daily_requirement_count: int
    minute_requirement_count: int
    terminal_disposition_count: int
    distinct_security_count: int
    daily_history_batch_count: int
    minute_history_batch_count: int
    maximum_dynamic_subscription_count: int
    market_observation_collection_pass_count: int
    maximum_decoded_shard_byte_count: int
    maximum_decision_session_row_count: int
    maximum_decision_session_byte_count: int
    maximum_daily_market_day_row_count: int
    maximum_daily_market_day_byte_count: int
    maximum_minute_market_day_row_count: int
    maximum_minute_market_day_byte_count: int
    maximum_live_daily_observation_count: int
    maximum_live_active_minute_observation_count: int
    bounded_header_uncompressed_byte_count: int
    terminal_header_uncompressed_byte_count: int
    estimated_peak_node_memory_byte_count: int
    projected_summary_payload_byte_count: int
    projected_summary_chunk_count: int

    def to_record(self) -> dict[str, object]:
        return {"schema": RESOURCE_CONTRACT_SCHEMA, **dataclasses.asdict(self)}


def _streaming_resource_geometry(
    shards: tuple[FormalQcCompressedShard, ...], batch_width: int
) -> dict[str, int]:
    _positive_int(batch_width, "maximum_dynamic_subscription_count")
    daily_security_ids: set[str] = set()
    daily_by_block: dict[int, set[str]] = {}
    daily_by_session: dict[str, tuple[int, int]] = {}
    minute_security_ids: set[str] = set()
    minute_by_activation_day: dict[tuple[int, str], set[str]] = {}
    minute_day_stats: dict[str, tuple[int, int]] = {}
    decision_block_stats: dict[tuple[int, int], tuple[int, int]] = {}
    component_commitments: set[tuple[str, str]] = set()
    minute_lifetime_deltas: dict[int, int] = {}
    prior_sort_key: dict[str, tuple[object, ...]] = {}
    prior_shard_last_block: dict[str, tuple[object, ...]] = {}
    maximum_decoded_shard = 0
    header_uncompressed_bytes = 0
    terminal_header_bytes = 0

    def checked_row_geometry(
        role: str, row: dict[str, object]
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        security = row.get("security_id")
        if role == "formal_contract":
            return (0,), (role,)
        if role == "decision_joins":
            fold = _safe_id(row.get("fold_id"), "decision stream fold")
            if fold not in FORMAL_PRIMARY_FOLD_IDS:
                raise FormalQcRuntimeProjectionError("decision stream fold changed")
            position = _positive_int(
                row.get("session_position"), "decision session position",
                allow_zero=True,
            )
            view = _safe_id(row.get("source_view_id"), "decision stream view")
            if view not in SOURCE_VIEW_IDS:
                raise FormalQcRuntimeProjectionError("decision stream view changed")
            security_id = _safe_id(security, "decision stream security")
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(fold), position,
                SOURCE_VIEW_IDS.index(view), security_id,
            ), (FORMAL_PRIMARY_FOLD_IDS.index(fold), position)
        if role == "contribution_seeds":
            intervals = row.get("active_intervals")
            if (
                type(intervals) is not list or not intervals
                or any(
                    type(item) is not list or len(item) != 2
                    or type(item[0]) is not int or type(item[1]) is not int
                    or item[0] < 0 or item[1] <= item[0]
                    for item in intervals
                )
            ):
                raise FormalQcRuntimeProjectionError(
                    "contribution stream active intervals changed"
                )
            fold = _safe_id(row.get("fold_id"), "contribution stream fold")
            view = _safe_id(row.get("source_view_id"), "contribution stream view")
            if fold not in FORMAL_PRIMARY_FOLD_IDS or view not in SOURCE_VIEW_IDS:
                raise FormalQcRuntimeProjectionError("contribution stream geometry changed")
            first = min(item[0] for item in intervals)
            minute_id = row.get("minute_requirement_id")
            if minute_id is not None:
                _safe_id(minute_id, "contribution minute requirement")
            return (
                first, SOURCE_VIEW_IDS.index(view),
                FORMAL_PRIMARY_FOLD_IDS.index(fold),
                _safe_id(security, "contribution stream security"),
                _safe_id(row.get("seed_id"), "contribution stream seed"),
            ), (first,)
        if role == "daily_requirements":
            session = _iso_date(row.get("session"), "daily requirement session")
            security_id = _safe_id(security, "daily stream security")
            requirement = _safe_id(row.get("requirement_id"), "daily requirement id")
            return (session, security_id, requirement), (session,)
        if role == "economic_joins":
            fold = _safe_id(row.get("fold_id"), "economic stream fold")
            view = _safe_id(row.get("source_view_id"), "economic stream view")
            if fold not in FORMAL_PRIMARY_FOLD_IDS or view not in SOURCE_VIEW_IDS:
                raise FormalQcRuntimeProjectionError("economic stream geometry changed")
            position = _positive_int(
                row.get("session_position"), "economic session position",
                allow_zero=True,
            )
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(fold), position,
                SOURCE_VIEW_IDS.index(view),
            ), (role,)
        if role == "minute_requirements":
            publication = _utc_text(
                row.get("publication_at_utc"), "publication_at_utc"
            )
            first_active = _positive_int(
                row.get("first_active_session_position"),
                "minute first active session position", allow_zero=True,
            )
            last_active = _positive_int(
                row.get("last_active_session_position"),
                "minute last active session position", allow_zero=True,
            )
            if last_active < first_active:
                raise FormalQcRuntimeProjectionError(
                    "minute active-session interval changed"
                )
            minute_lifetime_deltas[first_active] = (
                minute_lifetime_deltas.get(first_active, 0) + 1
            )
            minute_lifetime_deltas[last_active + 1] = (
                minute_lifetime_deltas.get(last_active + 1, 0) - 1
            )
            security_id = _safe_id(security, "minute stream security")
            requirement = _safe_id(row.get("requirement_id"), "minute requirement id")
            return (
                first_active, publication, security_id, requirement,
            ), (first_active,)
        if role == "terminal_dispositions":
            kind = _safe_id(row.get("slot_kind"), "terminal slot kind")
            slot = _safe_id(row.get("slot_id"), "terminal slot id")
            horizon = row.get("horizon")
            if horizon is not None:
                horizon = _positive_int(horizon, "terminal horizon")
            return (kind, slot, -1 if horizon is None else horizon), (role,)
        encoded = canonical_json_bytes(row)
        return (encoded,), (role,)

    for shard in shards:
        maximum_decoded_shard = max(
            maximum_decoded_shard, shard.uncompressed_byte_count
        )
        if shard.role in {"formal_contract", "economic_joins", "terminal_dispositions"}:
            header_uncompressed_bytes += shard.uncompressed_byte_count
            if shard.role == "terminal_dispositions":
                terminal_header_bytes += shard.uncompressed_byte_count
        rows = _decode_shard_rows(shard.payload)
        first_block: tuple[object, ...] | None = None
        last_block: tuple[object, ...] | None = None
        for row in rows:
            sort_key, block_key = checked_row_geometry(shard.role, row)
            if prior_sort_key.get(shard.role) is not None and sort_key <= prior_sort_key[shard.role]:
                raise FormalQcRuntimeProjectionError(
                    f"{shard.role} stream rows are duplicated or reordered"
                )
            prior_sort_key[shard.role] = sort_key
            first_block = block_key if first_block is None else first_block
            last_block = block_key
            encoded_count = len(canonical_json_bytes(row))
            if shard.role == "decision_joins":
                count, byte_count = decision_block_stats.get(block_key, (0, 0))
                decision_block_stats[block_key] = (
                    count + 1, byte_count + encoded_count
                )
                disposition = row.get("disposition")
                if disposition == "scored_decision":
                    component_commitments.add((
                        _safe_id(
                            row.get("source_view_id"),
                            "component commitment source view",
                        ),
                        _safe_id(
                            row.get("common_event_component_id"),
                            "component commitment id",
                        ),
                    ))
                elif disposition != "named_preoutcome_refusal":
                    raise FormalQcRuntimeProjectionError(
                        "decision stream disposition changed"
                    )
            elif shard.role == "daily_requirements":
                session = _iso_date(
                    row.get("session"), "daily requirement session"
                )
                security_id = _safe_id(row.get("security_id"), "market security id")
                daily_security_ids.add(security_id)
                block = date.fromisoformat(session).toordinal() // (
                    DAILY_HISTORY_BLOCK_CALENDAR_DAYS
                )
                daily_by_block.setdefault(block, set()).add(security_id)
                count, byte_count = daily_by_session.get(session, (0, 0))
                daily_by_session[session] = (count + 1, byte_count + encoded_count)
            elif shard.role == "minute_requirements":
                publication = _utc_text(
                    row.get("publication_at_utc"), "publication_at_utc"
                )
                security_id = _safe_id(row.get("security_id"), "market security id")
                minute_security_ids.add(security_id)
                first_active = _positive_int(
                    row.get("first_active_session_position"),
                    "minute first active session position", allow_zero=True,
                )
                minute_by_activation_day.setdefault(
                    (first_active, publication[:10]), set()
                ).add(security_id)
                count, byte_count = minute_day_stats.get(publication[:10], (0, 0))
                minute_day_stats[publication[:10]] = (
                    count + 1, byte_count + encoded_count
                )
        if (
            first_block is not None
            and prior_shard_last_block.get(shard.role) == first_block
        ):
            raise FormalQcRuntimeProjectionError(
                f"one {shard.role} stream block was split across shards"
            )
        if last_block is not None:
            prior_shard_last_block[shard.role] = last_block
    all_security_ids = daily_security_ids | minute_security_ids
    single_pass_daily_batches = sum(
        (len(security_ids) + batch_width - 1) // batch_width
        for security_ids in daily_by_block.values()
    )
    single_pass_minute_batches = sum(
        (len(security_ids) + batch_width - 1) // batch_width
        for security_ids in minute_by_activation_day.values()
    )
    daily_counts = [daily_by_session[key][0] for key in sorted(daily_by_session)]
    maximum_live_daily = max(
        (
            sum(daily_counts[max(0, index - 60): index + 1])
            for index in range(len(daily_counts))
        ),
        default=0,
    )
    active = 0
    maximum_live_minute = 0
    for position in sorted(minute_lifetime_deltas):
        active += minute_lifetime_deltas[position]
        maximum_live_minute = max(maximum_live_minute, active)
    return {
        "distinct_security_count": len(all_security_ids),
        "daily_history_batch_count": (
            single_pass_daily_batches * MARKET_OBSERVATION_COLLECTION_PASSES
        ),
        "minute_history_batch_count": (
            single_pass_minute_batches * MARKET_OBSERVATION_COLLECTION_PASSES
        ),
        "maximum_decoded_shard_byte_count": maximum_decoded_shard,
        "maximum_decision_session_row_count": max(
            (item[0] for item in decision_block_stats.values()), default=0
        ),
        "maximum_decision_session_byte_count": max(
            (item[1] for item in decision_block_stats.values()), default=0
        ),
        "component_commitment_count": len(component_commitments),
        "maximum_daily_market_day_row_count": max(
            (item[0] for item in daily_by_session.values()), default=0
        ),
        "maximum_daily_market_day_byte_count": max(
            (item[1] for item in daily_by_session.values()), default=0
        ),
        "maximum_minute_market_day_row_count": max(
            (item[0] for item in minute_day_stats.values()), default=0
        ),
        "maximum_minute_market_day_byte_count": max(
            (item[1] for item in minute_day_stats.values()), default=0
        ),
        "maximum_live_daily_observation_count": maximum_live_daily,
        "maximum_live_active_minute_observation_count": maximum_live_minute,
        "bounded_header_uncompressed_byte_count": header_uncompressed_bytes,
        "terminal_header_uncompressed_byte_count": terminal_header_bytes,
    }


def derive_formal_qc_runtime_resource_census(
    *,
    shards: tuple[FormalQcCompressedShard, ...],
    distinct_security_count: int,
    daily_history_batch_count: int,
    minute_history_batch_count: int,
    maximum_dynamic_subscription_count: int,
    projected_summary_payload_byte_count: int,
    projected_summary_chunk_count: int,
) -> FormalQcRuntimeResourceCensus:
    _require_shard_inventory(shards)
    values = {
        "distinct_security_count": distinct_security_count,
        "daily_history_batch_count": daily_history_batch_count,
        "minute_history_batch_count": minute_history_batch_count,
        "maximum_dynamic_subscription_count": maximum_dynamic_subscription_count,
        "projected_summary_payload_byte_count": projected_summary_payload_byte_count,
        "projected_summary_chunk_count": projected_summary_chunk_count,
    }
    for name, value in values.items():
        _positive_int(value, name, allow_zero=name in {"minute_history_batch_count"})
    geometry = _streaming_resource_geometry(
        shards, maximum_dynamic_subscription_count
    )
    if (
        geometry["distinct_security_count"] != distinct_security_count
        or geometry["daily_history_batch_count"] != daily_history_batch_count
        or geometry["minute_history_batch_count"] != minute_history_batch_count
    ):
        raise FormalQcRuntimeProjectionError(
            "declared market History request geometry changed"
        )
    if projected_summary_payload_byte_count > ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES:
        raise FormalQcRuntimeProjectionError("projected aggregate result exceeds absolute bound")
    if projected_summary_chunk_count > ABSOLUTE_MAX_SUMMARY_CHUNKS:
        raise FormalQcRuntimeProjectionError("projected summary chunk count exceeds absolute bound")
    role_counts = {role: 0 for role in SHARD_ROLE_ORDER}
    for shard in shards:
        role_counts[shard.role] += shard.row_count
    if (
        role_counts["formal_contract"] != 1
        or role_counts["contribution_seeds"] < 1
        or role_counts["decision_joins"] < 1
        or role_counts["economic_joins"] < 1
        or role_counts["daily_requirements"] < 1
    ):
        raise FormalQcRuntimeProjectionError("compact input lacks a mandatory formal row class")
    uncompressed_count = sum(item.uncompressed_byte_count for item in shards)
    estimated_peak_memory = (
        max(item.compressed_byte_count for item in shards)
        + geometry["maximum_decoded_shard_byte_count"]
        * STREAM_DECODE_WORKING_SET_MULTIPLIER
        + geometry["bounded_header_uncompressed_byte_count"]
        * INPUT_EXPANSION_MEMORY_MULTIPLIER
        + geometry["maximum_decision_session_byte_count"]
        * INPUT_EXPANSION_MEMORY_MULTIPLIER
        + (
            geometry["maximum_live_daily_observation_count"]
            + geometry["maximum_live_active_minute_observation_count"]
        ) * OBSERVATION_MEMORY_BYTES_PER_REQUIREMENT
        + role_counts["minute_requirements"]
        * MINUTE_COMMITMENT_MEMORY_BYTES_PER_REQUIREMENT
        + geometry["component_commitment_count"]
        * COMPONENT_COMMITMENT_MEMORY_BYTES
        + maximum_dynamic_subscription_count
        * HISTORY_BATCH_MEMORY_BYTES_PER_SECURITY
        + role_counts["economic_joins"]
        * STREAM_EVALUATOR_BYTES_PER_ECONOMIC_JOIN
        + projected_summary_payload_byte_count * 4
        + FORMAL_RESULT_WORKING_SET_MEMORY_BYTES
    )
    return FormalQcRuntimeResourceCensus(
        shard_count=len(shards),
        compressed_input_byte_count=sum(item.compressed_byte_count for item in shards),
        maximum_compressed_object_byte_count=max(
            item.compressed_byte_count for item in shards
        ),
        uncompressed_input_byte_count=uncompressed_count,
        formal_contract_count=role_counts["formal_contract"],
        contribution_seed_count=role_counts["contribution_seeds"],
        decision_join_count=role_counts["decision_joins"],
        component_commitment_count=geometry["component_commitment_count"],
        economic_join_count=role_counts["economic_joins"],
        daily_requirement_count=role_counts["daily_requirements"],
        minute_requirement_count=role_counts["minute_requirements"],
        terminal_disposition_count=role_counts["terminal_dispositions"],
        distinct_security_count=distinct_security_count,
        daily_history_batch_count=daily_history_batch_count,
        minute_history_batch_count=minute_history_batch_count,
        maximum_dynamic_subscription_count=maximum_dynamic_subscription_count,
        market_observation_collection_pass_count=(
            MARKET_OBSERVATION_COLLECTION_PASSES
        ),
        maximum_decoded_shard_byte_count=geometry[
            "maximum_decoded_shard_byte_count"
        ],
        maximum_decision_session_row_count=geometry[
            "maximum_decision_session_row_count"
        ],
        maximum_decision_session_byte_count=geometry[
            "maximum_decision_session_byte_count"
        ],
        maximum_daily_market_day_row_count=geometry[
            "maximum_daily_market_day_row_count"
        ],
        maximum_daily_market_day_byte_count=geometry[
            "maximum_daily_market_day_byte_count"
        ],
        maximum_minute_market_day_row_count=geometry[
            "maximum_minute_market_day_row_count"
        ],
        maximum_minute_market_day_byte_count=geometry[
            "maximum_minute_market_day_byte_count"
        ],
        maximum_live_daily_observation_count=geometry[
            "maximum_live_daily_observation_count"
        ],
        maximum_live_active_minute_observation_count=geometry[
            "maximum_live_active_minute_observation_count"
        ],
        bounded_header_uncompressed_byte_count=geometry[
            "bounded_header_uncompressed_byte_count"
        ],
        terminal_header_uncompressed_byte_count=geometry[
            "terminal_header_uncompressed_byte_count"
        ],
        estimated_peak_node_memory_byte_count=estimated_peak_memory,
        projected_summary_payload_byte_count=projected_summary_payload_byte_count,
        projected_summary_chunk_count=projected_summary_chunk_count,
    )


def _require_shard_inventory(shards: tuple[FormalQcCompressedShard, ...]) -> None:
    if type(shards) is not tuple or not shards or len(shards) > ABSOLUTE_MAX_SHARDS:
        raise FormalQcRuntimeProjectionError("compact shard inventory changed")
    for shard in shards:
        require_formal_qc_compressed_shard(shard)
    expected = tuple(sorted(shards, key=lambda item: (SHARD_ROLE_ORDER.index(item.role), item.ordinal)))
    if shards != expected:
        raise FormalQcRuntimeProjectionError("compact shards are not in canonical role/ordinal order")
    seen: set[tuple[str, int]] = set()
    for shard in shards:
        key = (shard.role, shard.ordinal)
        if key in seen:
            raise FormalQcRuntimeProjectionError("duplicate compact shard ordinal")
        seen.add(key)
    for role in SHARD_ROLE_ORDER:
        ordinals = [item.ordinal for item in shards if item.role == role]
        if not ordinals:
            raise FormalQcRuntimeProjectionError("compact shard role is absent")
        if ordinals != list(range(len(ordinals))):
            raise FormalQcRuntimeProjectionError("compact shard ordinals are not contiguous")


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcRuntimeCapacityBinding:
    candidate_sha256: str
    receipt_id: str
    receipt_sha256: str
    limits: tuple[tuple[str, int], ...]
    representative_full_census_verified: bool
    target_tier_limits_observed: bool
    cloud_evaluator_equivalence_verified: bool
    object_store_input_transport_verified: bool
    object_store_output_write_once_transport_verified: bool
    summary_statistics_channel_verified: bool
    summary_root_result_channel_verified: bool
    receipt_bytes: bytes = dataclasses.field(repr=False)

    @property
    def submission_authority(self) -> bool:
        """Capacity evidence is never the external-action trust root."""

        return False

    def to_record(self) -> dict[str, object]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
            "limits": dict(self.limits),
            "representative_full_census_verified": self.representative_full_census_verified,
            "target_tier_limits_observed": self.target_tier_limits_observed,
            "cloud_evaluator_equivalence_verified": self.cloud_evaluator_equivalence_verified,
            "object_store_input_transport_verified": self.object_store_input_transport_verified,
            "object_store_output_write_once_transport_verified": self.object_store_output_write_once_transport_verified,
            "summary_statistics_channel_verified": self.summary_statistics_channel_verified,
            "summary_root_result_channel_verified": self.summary_root_result_channel_verified,
        }


_CAPACITY_LIMIT_NAMES = (
    "max_shard_count",
    "max_compressed_input_byte_count",
    "max_object_store_total_input_byte_count",
    "min_object_store_available_output_byte_count",
    "min_object_store_available_output_file_count",
    "max_single_object_byte_count",
    "max_uncompressed_input_byte_count",
    "max_formal_contract_count",
    "max_contribution_seed_count",
    "max_decision_join_count",
    "max_component_commitment_count",
    "max_economic_join_count",
    "max_daily_requirement_count",
    "max_minute_requirement_count",
    "max_terminal_disposition_count",
    "max_distinct_security_count",
    "max_daily_history_batch_count",
    "max_minute_history_batch_count",
    "max_dynamic_subscription_count",
    "max_market_observation_collection_pass_count",
    "max_decoded_shard_byte_count",
    "max_decision_session_row_count",
    "max_decision_session_byte_count",
    "max_daily_market_day_row_count",
    "max_daily_market_day_byte_count",
    "max_minute_market_day_row_count",
    "max_minute_market_day_byte_count",
    "max_live_daily_observation_count",
    "max_live_active_minute_observation_count",
    "max_bounded_header_uncompressed_byte_count",
    "max_terminal_header_uncompressed_byte_count",
    "max_summary_payload_byte_count",
    "max_summary_chunk_count",
    "max_summary_chunk_characters",
    "max_node_memory_byte_count",
    "max_project_file_count",
    "max_project_source_character_count",
)
CAPACITY_LIMIT_NAMES = _CAPACITY_LIMIT_NAMES


def render_formal_qc_capacity_review_candidate(
    *, census: FormalQcRuntimeResourceCensus, limits: Mapping[str, int]
) -> bytes:
    if type(census) is not FormalQcRuntimeResourceCensus:
        raise FormalQcRuntimeProjectionError("resource census type changed")
    if type(limits) is not dict or tuple(sorted(limits)) != tuple(sorted(_CAPACITY_LIMIT_NAMES)):
        raise FormalQcRuntimeProjectionError("capacity limit inventory changed")
    checked: dict[str, int] = {}
    for name in _CAPACITY_LIMIT_NAMES:
        checked[name] = _positive_int(limits[name], name)
    return canonical_json_bytes(
        {
            "schema": RESOURCE_CONTRACT_SCHEMA,
            "status": "requires_independent_full_census_and_target_tier_review",
            "census": census.to_record(),
            "limits": checked,
            "no_silent_truncation": True,
            "candidate_sha256": None,
        }
    )


def load_formal_qc_runtime_capacity_binding(
    *, candidate_bytes: bytes, reviewed_receipt_bytes: bytes
) -> FormalQcRuntimeCapacityBinding:
    candidate = _json_object(candidate_bytes, "capacity candidate")
    if candidate.get("schema") != RESOURCE_CONTRACT_SCHEMA:
        raise FormalQcRuntimeProjectionError("capacity candidate schema changed")
    candidate_without_id = dict(candidate)
    candidate_without_id["candidate_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(candidate_without_id)).hexdigest()
    if candidate.get("candidate_sha256") not in (None, digest):
        raise FormalQcRuntimeProjectionError("capacity candidate identity changed")
    receipt = _exact_mapping(
        _json_object(reviewed_receipt_bytes, "capacity review receipt"),
        frozenset(
            {
                "schema", "candidate_sha256", "receipt_id", "receipt_sha256",
                "limits", "representative_full_census_verified",
                "target_tier_limits_observed", "cloud_evaluator_equivalence_verified",
                "object_store_input_transport_verified",
                "object_store_output_write_once_transport_verified",
                "summary_statistics_channel_verified",
                "summary_root_result_channel_verified",
            }
        ),
        "capacity review receipt",
    )
    receipt_seed = dict(receipt)
    receipt_seed["receipt_id"] = None
    receipt_seed["receipt_sha256"] = None
    receipt_hash = hashlib.sha256(canonical_json_bytes(receipt_seed)).hexdigest()
    if (
        receipt["schema"] != CAPACITY_REVIEW_SCHEMA
        or receipt["candidate_sha256"] != digest
        or receipt["receipt_sha256"] != receipt_hash
        or receipt["receipt_id"] != "arv2-formal-qc-capacity-review-" + receipt_hash
        or type(receipt["limits"]) is not dict
        or tuple(sorted(receipt["limits"])) != tuple(sorted(_CAPACITY_LIMIT_NAMES))
        or any(type(receipt[name]) is not bool or receipt[name] is not True for name in (
            "representative_full_census_verified", "target_tier_limits_observed",
            "cloud_evaluator_equivalence_verified", "object_store_input_transport_verified",
            "object_store_output_write_once_transport_verified",
            "summary_statistics_channel_verified",
            "summary_root_result_channel_verified",
        ))
    ):
        raise FormalQcRuntimeProjectionError("capacity review receipt is not fully affirmative")
    limits = tuple((name, _positive_int(receipt["limits"][name], name)) for name in _CAPACITY_LIMIT_NAMES)
    value = FormalQcRuntimeCapacityBinding(
        candidate_sha256=digest,
        receipt_id=str(receipt["receipt_id"]),
        receipt_sha256=receipt_hash,
        limits=limits,
        representative_full_census_verified=receipt[
            "representative_full_census_verified"
        ],
        target_tier_limits_observed=receipt["target_tier_limits_observed"],
        cloud_evaluator_equivalence_verified=receipt[
            "cloud_evaluator_equivalence_verified"
        ],
        object_store_input_transport_verified=receipt[
            "object_store_input_transport_verified"
        ],
        object_store_output_write_once_transport_verified=receipt[
            "object_store_output_write_once_transport_verified"
        ],
        summary_statistics_channel_verified=receipt[
            "summary_statistics_channel_verified"
        ],
        summary_root_result_channel_verified=receipt[
            "summary_root_result_channel_verified"
        ],
        receipt_bytes=bytes(reviewed_receipt_bytes),
    )
    return require_formal_qc_runtime_capacity_binding(value)


def require_formal_qc_runtime_capacity_binding(
    value: FormalQcRuntimeCapacityBinding,
) -> FormalQcRuntimeCapacityBinding:
    if type(value) is not FormalQcRuntimeCapacityBinding:
        raise FormalQcRuntimeProjectionError("capacity binding type changed")
    receipt = _json_object(value.receipt_bytes, "capacity review receipt")
    if (
        value.to_record().get("receipt_id") != receipt.get("receipt_id")
        or value.to_record().get("receipt_sha256") != receipt.get("receipt_sha256")
        or value.to_record().get("candidate_sha256") != receipt.get("candidate_sha256")
        or dict(value.limits) != receipt.get("limits")
        or any(getattr(value, name) is not True for name in (
            "representative_full_census_verified", "target_tier_limits_observed",
            "cloud_evaluator_equivalence_verified", "object_store_input_transport_verified",
            "object_store_output_write_once_transport_verified",
            "summary_statistics_channel_verified",
            "summary_root_result_channel_verified",
        ))
    ):
        raise FormalQcRuntimeProjectionError("capacity binding changed")
    seed = dict(receipt)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    if hashlib.sha256(canonical_json_bytes(seed)).hexdigest() != value.receipt_sha256:
        raise FormalQcRuntimeProjectionError("capacity review receipt identity changed")
    return value


def _census_within_capacity(
    census: FormalQcRuntimeResourceCensus, capacity: FormalQcRuntimeCapacityBinding
) -> None:
    limits = dict(capacity.limits)
    comparisons = {
        "shard_count": "max_shard_count",
        "compressed_input_byte_count": "max_compressed_input_byte_count",
        "maximum_compressed_object_byte_count": "max_single_object_byte_count",
        "uncompressed_input_byte_count": "max_uncompressed_input_byte_count",
        "formal_contract_count": "max_formal_contract_count",
        "contribution_seed_count": "max_contribution_seed_count",
        "decision_join_count": "max_decision_join_count",
        "component_commitment_count": "max_component_commitment_count",
        "economic_join_count": "max_economic_join_count",
        "daily_requirement_count": "max_daily_requirement_count",
        "minute_requirement_count": "max_minute_requirement_count",
        "terminal_disposition_count": "max_terminal_disposition_count",
        "distinct_security_count": "max_distinct_security_count",
        "daily_history_batch_count": "max_daily_history_batch_count",
        "minute_history_batch_count": "max_minute_history_batch_count",
        "maximum_dynamic_subscription_count": "max_dynamic_subscription_count",
        "market_observation_collection_pass_count": (
            "max_market_observation_collection_pass_count"
        ),
        "maximum_decoded_shard_byte_count": "max_decoded_shard_byte_count",
        "maximum_decision_session_row_count": "max_decision_session_row_count",
        "maximum_decision_session_byte_count": "max_decision_session_byte_count",
        "maximum_daily_market_day_row_count": "max_daily_market_day_row_count",
        "maximum_daily_market_day_byte_count": "max_daily_market_day_byte_count",
        "maximum_minute_market_day_row_count": "max_minute_market_day_row_count",
        "maximum_minute_market_day_byte_count": "max_minute_market_day_byte_count",
        "maximum_live_daily_observation_count": "max_live_daily_observation_count",
        "maximum_live_active_minute_observation_count": (
            "max_live_active_minute_observation_count"
        ),
        "bounded_header_uncompressed_byte_count": (
            "max_bounded_header_uncompressed_byte_count"
        ),
        "terminal_header_uncompressed_byte_count": (
            "max_terminal_header_uncompressed_byte_count"
        ),
        "projected_summary_payload_byte_count": "max_summary_payload_byte_count",
        "projected_summary_chunk_count": "max_summary_chunk_count",
        "estimated_peak_node_memory_byte_count": "max_node_memory_byte_count",
    }
    for field, limit in comparisons.items():
        if getattr(census, field) > limits[limit]:
            raise FormalQcRuntimeProjectionError(f"formal QC capacity exceeded: {field}")
    if (
        census.compressed_input_byte_count
        > limits["max_object_store_total_input_byte_count"]
    ):
        raise FormalQcRuntimeProjectionError(
            "formal QC capacity exceeded: Object Store shard bytes"
        )
    if (
        limits["min_object_store_available_output_byte_count"]
        < MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
        or limits["min_object_store_available_output_file_count"]
        < FORMAL_RESULT_FAMILY_OBJECT_COUNT
    ):
        raise FormalQcRuntimeProjectionError(
            "formal QC Object Store output capacity gate is closed"
        )
    if limits["max_single_object_byte_count"] > ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES:
        raise FormalQcRuntimeProjectionError("single-object capacity limit exceeds safety bound")
    if limits["max_summary_payload_byte_count"] > ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES:
        raise FormalQcRuntimeProjectionError("summary payload limit exceeds safety bound")
    if limits["max_summary_chunk_count"] > ABSOLUTE_MAX_SUMMARY_CHUNKS:
        raise FormalQcRuntimeProjectionError("summary chunk-count limit exceeds safety bound")
    if limits["max_summary_chunk_characters"] > ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS:
        raise FormalQcRuntimeProjectionError("summary chunk-width limit exceeds safety bound")
    encoded_character_ceiling = 4 * (
        (census.projected_summary_payload_byte_count + 2) // 3
    )
    required_chunks = (
        encoded_character_ceiling
        + limits["max_summary_chunk_characters"]
        - 1
    ) // limits["max_summary_chunk_characters"]
    if required_chunks > census.projected_summary_chunk_count:
        raise FormalQcRuntimeProjectionError(
            "projected summary chunk census understates encoded payload"
        )


def _build_formal_qc_input_manifest_from_descriptors(
    *,
    production_input_package: ArtifactBinding,
    preopen_control_stage_output: ArtifactBinding,
    runtime_start: date,
    runtime_end: date,
    calculation_as_of_date: date,
    benchmark_security_id: str,
    shard_descriptors: Sequence[Mapping[str, object]],
    resource_census: FormalQcRuntimeResourceCensus,
    capacity: FormalQcRuntimeCapacityBinding,
    cloud_evaluator: ArtifactBinding,
    upstream_scoring_materialization_capacity: Mapping[str, object],
) -> bytes:
    """Render the shared manifest record after a caller authenticates inputs.

    This private renderer deliberately grants no authority.  The legacy public
    builder below always supplies its historical closed upstream gate.  The
    streamed host bridge supplies an independently loader-authenticated
    upstream receipt only after it has sequentially reauthenticated the exact
    physical descriptor census.
    """

    summary_limit = dict(capacity.limits)
    manifest = {
        "schema": INPUT_MANIFEST_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "runtime_start": runtime_start.isoformat(),
        "runtime_end": runtime_end.isoformat(),
        "calculation_as_of_date": calculation_as_of_date.isoformat(),
        "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
        "descriptive_sensitivity_fold_ids": list(DESCRIPTIVE_SENSITIVITY_FOLD_IDS),
        "descriptive_sensitivity_cannot_replace_or_rescue_primary": True,
        "source_view_ids": list(SOURCE_VIEW_IDS),
        "horizons": list(HORIZONS),
        "primary_horizon": PRIMARY_HORIZON,
        "economic_holding_sessions": SLEEVE_HOLDING_SESSIONS,
        "benchmark_security_id": benchmark_security_id,
        "production_input_package": production_input_package.to_record(),
        "preopen_control_stage_output": preopen_control_stage_output.to_record(),
        "cloud_evaluator": cloud_evaluator.to_record(),
        "cloud_evaluator_interface_schema": CLOUD_EVALUATOR_INTERFACE_SCHEMA,
        "shards": [dict(item) for item in shard_descriptors],
        "resource_census": resource_census.to_record(),
        "resource_model": {
            "market_observation_collection_passes": (
                MARKET_OBSERVATION_COLLECTION_PASSES
            ),
            "daily_history_requests": (
                "2*sum_by_32_day_block(ceil(distinct_security_ids/batch_width))"
            ),
            "minute_history_requests": (
                "2*sum_by_publication_day(ceil(distinct_security_ids/batch_width))"
            ),
            "batch_width_field": "maximum_dynamic_subscription_count",
            "history_requests_use_multi_symbol_batches": True,
            "input_rows_are_incrementally_decoded": True,
            "evaluation_uses_fold_session_blocks": True,
            "component_commitments_are_full_run_bounded": True,
            "maximum_horizon_session_lookahead": 60,
            "shared_market_panel_hash_is_verified_across_two_passes": True,
            "daily_history_block_calendar_days": DAILY_HISTORY_BLOCK_CALENDAR_DAYS,
            "maximum_daily_history_request_span_days": (
                MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS
            ),
            "estimated_peak_node_memory_formula": (
                "max_compressed_object+2*max_decoded_shard+8*bounded_headers+"
                "8*max_decision_session_bytes+512*(max_live_61_session_daily+"
                "max_live_minute_lifetime)+512*unique_minute_commitments+"
                "1024*unique_source_view_common_event_components+"
                "2000000*batch_width+32768*"
                "economic_join_count+4*projected_summary_payload_bytes+"
                "109200000_total_family_gzip+"
                "8*109051904_total_family_decoded_graph+"
                "4*200000_root_summary_encoding_overhead"
            ),
            "no_silent_truncation": True,
        },
        "capacity_review": capacity.to_record(),
        "capacity_evidence_is_submission_authority": False,
        "upstream_scoring_materialization_capacity": dict(
            upstream_scoring_materialization_capacity
        ),
        "external_owner_execution_authority_pin_required": True,
        "summary_result_contract": {
            "aggregate_result_schema": AGGREGATE_RESULT_SCHEMA,
            "summary_receipt_schema": SUMMARY_RECEIPT_SCHEMA,
            "cloud_evaluation_output_schema": (
                FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
            ),
            "report_family_object_reference_schema": (
                REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
            ),
            "meta_name": SUMMARY_META_NAME,
            "chunk_prefix": SUMMARY_CHUNK_PREFIX,
            "chunk_name_width": SUMMARY_CHUNK_NAME_WIDTH,
            "max_payload_byte_count": summary_limit["max_summary_payload_byte_count"],
            "max_chunk_count": summary_limit["max_summary_chunk_count"],
            "max_chunk_characters": summary_limit["max_summary_chunk_characters"],
            "fold_horizon_axis_count": 24,
            "source_view_fold_horizon_axis_count": 48,
            "raw_market_or_outcome_rows_in_summary_forbidden": True,
            "report_family_object_count": FORMAL_RESULT_FAMILY_OBJECT_COUNT,
            "report_family_object_key_suffix_prefix": (
                REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
            ),
            "report_family_object_full_key_derivation": (
                "str(project_id)+'/'+authenticated_object_store_key_suffix"
            ),
            "report_family_object_uncompressed_byte_ceiling": (
                MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES
            ),
            "report_family_object_compressed_byte_ceiling": (
                MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
            ),
            "report_family_object_total_uncompressed_byte_ceiling": (
                MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
            ),
            "report_family_object_total_compressed_byte_ceiling": (
                MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
            ),
            "object_store_write_once_existing_identical_bytes_only": True,
            "object_store_save_then_reopen_and_rehash_required": True,
            "root_summary_published_only_after_all_family_reopens": True,
            "family_objects_required_for_result_read": True,
        },
        "market_contract": {
            "daily_normalization": "TotalReturn",
            "daily_observation": "open_to_next_open",
            "publication_price": "last_tradable_minute_strictly_before_publication",
            "positive_firm_weighted_jump": True,
            "empty_positive_firm_weight_set_jump": "0",
            "terminal_policy_id": TERMINAL_POLICY_ID,
            "qc_delisting_price_is_terminal_payoff": False,
            "failed_arm_omission_forbidden": True,
            "shared_market_panel_across_views": True,
        },
        "orders_authorized": False,
    }
    return canonical_json_bytes(manifest)


def build_formal_qc_input_manifest_bytes(
    *,
    production_input_package: ArtifactBinding,
    preopen_control_stage_output: ArtifactBinding,
    runtime_start: date,
    runtime_end: date,
    calculation_as_of_date: date,
    benchmark_security_id: str,
    shards: tuple[FormalQcCompressedShard, ...],
    resource_census: FormalQcRuntimeResourceCensus,
    capacity: FormalQcRuntimeCapacityBinding,
    cloud_evaluator: ArtifactBinding,
) -> bytes:
    require_artifact_binding(production_input_package)
    require_artifact_binding(preopen_control_stage_output)
    require_artifact_binding(cloud_evaluator)
    if (
        type(runtime_start) is not date
        or type(runtime_end) is not date
        or type(calculation_as_of_date) is not date
        or runtime_start >= runtime_end
        or calculation_as_of_date <= runtime_end
    ):
        raise FormalQcRuntimeProjectionError("runtime dates changed")
    _safe_id(benchmark_security_id, "benchmark security id")
    _require_shard_inventory(shards)
    require_formal_qc_runtime_capacity_binding(capacity)
    expected_census = derive_formal_qc_runtime_resource_census(
        shards=shards,
        distinct_security_count=resource_census.distinct_security_count,
        daily_history_batch_count=resource_census.daily_history_batch_count,
        minute_history_batch_count=resource_census.minute_history_batch_count,
        maximum_dynamic_subscription_count=resource_census.maximum_dynamic_subscription_count,
        projected_summary_payload_byte_count=resource_census.projected_summary_payload_byte_count,
        projected_summary_chunk_count=resource_census.projected_summary_chunk_count,
    )
    if resource_census != expected_census:
        raise FormalQcRuntimeProjectionError("resource census disagrees with exact shards")
    capacity_candidate = render_formal_qc_capacity_review_candidate(
        census=resource_census, limits=dict(capacity.limits)
    )
    if hashlib.sha256(capacity_candidate).hexdigest() != capacity.candidate_sha256:
        raise FormalQcRuntimeProjectionError(
            "capacity receipt binds a different resource census"
        )
    _census_within_capacity(resource_census, capacity)
    return _build_formal_qc_input_manifest_from_descriptors(
        production_input_package=production_input_package,
        preopen_control_stage_output=preopen_control_stage_output,
        runtime_start=runtime_start,
        runtime_end=runtime_end,
        calculation_as_of_date=calculation_as_of_date,
        benchmark_security_id=benchmark_security_id,
        shard_descriptors=tuple(item.descriptor() for item in shards),
        resource_census=resource_census,
        capacity=capacity,
        cloud_evaluator=cloud_evaluator,
        upstream_scoring_materialization_capacity={
            "schema": UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA,
            "status": "required_reviewed_artifact_not_supplied",
            "artifact_binding": None,
            "distinct_from_runtime_capacity": True,
            "one_fold_streaming_projection_verified": False,
            "production_truth_materialization_capacity_verified": False,
            "representative_full_census_verified": False,
            "launch_authorized": False,
        },
    )


def validate_formal_qc_runtime_resource_candidate(
    *,
    manifest_payload: bytes,
    shards: tuple[FormalQcCompressedShard, ...],
) -> FormalQcRuntimeResourceCensus:
    manifest = _json_object(manifest_payload, "compact input manifest")
    if manifest.get("schema") != INPUT_MANIFEST_SCHEMA:
        raise FormalQcRuntimeProjectionError("compact input manifest schema changed")
    if (
        manifest.get("capacity_evidence_is_submission_authority") is not False
        or manifest.get("external_owner_execution_authority_pin_required") is not True
    ):
        raise FormalQcRuntimeProjectionError(
            "capacity evidence attempted to become submission authority"
        )
    _require_shard_inventory(shards)
    if manifest.get("shards") != [item.descriptor() for item in shards]:
        raise FormalQcRuntimeProjectionError("manifest shard inventory changed")
    capacity_record = manifest.get("capacity_review")
    if type(capacity_record) is not dict or not all(
        capacity_record.get(name) is True for name in (
            "representative_full_census_verified", "target_tier_limits_observed",
            "cloud_evaluator_equivalence_verified", "object_store_input_transport_verified",
            "object_store_output_write_once_transport_verified",
            "summary_statistics_channel_verified",
            "summary_root_result_channel_verified",
        )
    ):
        raise FormalQcRuntimeProjectionError("formal runtime capacity/equivalence gate is closed")
    raw = manifest.get("resource_census")
    if type(raw) is not dict or raw.get("schema") != RESOURCE_CONTRACT_SCHEMA:
        raise FormalQcRuntimeProjectionError("resource census schema changed")
    fields = tuple(field.name for field in dataclasses.fields(FormalQcRuntimeResourceCensus))
    if set(raw) != {"schema", *fields}:
        raise FormalQcRuntimeProjectionError("resource census fields changed")
    try:
        census = FormalQcRuntimeResourceCensus(**{name: raw[name] for name in fields})
    except TypeError as exc:
        raise FormalQcRuntimeProjectionError("resource census changed") from exc
    expected = derive_formal_qc_runtime_resource_census(
        shards=shards,
        distinct_security_count=census.distinct_security_count,
        daily_history_batch_count=census.daily_history_batch_count,
        minute_history_batch_count=census.minute_history_batch_count,
        maximum_dynamic_subscription_count=census.maximum_dynamic_subscription_count,
        projected_summary_payload_byte_count=census.projected_summary_payload_byte_count,
        projected_summary_chunk_count=census.projected_summary_chunk_count,
    )
    if census != expected:
        raise FormalQcRuntimeProjectionError("resource census disagrees with shard bytes")
    limits = capacity_record.get("limits")
    if (
        type(limits) is not dict
        or tuple(sorted(limits)) != tuple(sorted(_CAPACITY_LIMIT_NAMES))
    ):
        raise FormalQcRuntimeProjectionError("reviewed capacity limits changed")
    receipt_seed = {"schema": CAPACITY_REVIEW_SCHEMA, **capacity_record}
    receipt_seed["receipt_id"] = None
    receipt_seed["receipt_sha256"] = None
    receipt_sha256 = hashlib.sha256(
        canonical_json_bytes(receipt_seed)
    ).hexdigest()
    capacity_candidate = render_formal_qc_capacity_review_candidate(
        census=census, limits=limits
    )
    if (
        capacity_record.get("receipt_sha256") != receipt_sha256
        or capacity_record.get("receipt_id")
        != "arv2-formal-qc-capacity-review-" + receipt_sha256
        or capacity_record.get("candidate_sha256")
        != hashlib.sha256(capacity_candidate).hexdigest()
    ):
        raise FormalQcRuntimeProjectionError(
            "capacity receipt content identity changed"
        )
    reviewed_capacity = load_formal_qc_runtime_capacity_binding(
        candidate_bytes=capacity_candidate,
        reviewed_receipt_bytes=canonical_json_bytes(
            {"schema": CAPACITY_REVIEW_SCHEMA, **capacity_record}
        ),
    )
    _census_within_capacity(census, reviewed_capacity)
    for field, limit in (
        ("shard_count", "max_shard_count"),
        ("compressed_input_byte_count", "max_compressed_input_byte_count"),
        ("maximum_compressed_object_byte_count", "max_single_object_byte_count"),
        ("uncompressed_input_byte_count", "max_uncompressed_input_byte_count"),
        ("formal_contract_count", "max_formal_contract_count"),
        ("contribution_seed_count", "max_contribution_seed_count"),
        ("decision_join_count", "max_decision_join_count"),
        ("component_commitment_count", "max_component_commitment_count"),
        ("economic_join_count", "max_economic_join_count"),
        ("daily_requirement_count", "max_daily_requirement_count"),
        ("minute_requirement_count", "max_minute_requirement_count"),
        ("terminal_disposition_count", "max_terminal_disposition_count"),
        ("distinct_security_count", "max_distinct_security_count"),
        ("daily_history_batch_count", "max_daily_history_batch_count"),
        ("minute_history_batch_count", "max_minute_history_batch_count"),
        ("maximum_dynamic_subscription_count", "max_dynamic_subscription_count"),
        ("projected_summary_payload_byte_count", "max_summary_payload_byte_count"),
        ("projected_summary_chunk_count", "max_summary_chunk_count"),
        ("estimated_peak_node_memory_byte_count", "max_node_memory_byte_count"),
    ):
        if type(limits.get(limit)) is not int or getattr(census, field) > limits[limit]:
            raise FormalQcRuntimeProjectionError(f"formal QC capacity exceeded: {field}")
    if (
        census.compressed_input_byte_count
        > limits.get("max_object_store_total_input_byte_count", -1)
    ):
        raise FormalQcRuntimeProjectionError(
            "formal QC capacity exceeded: Object Store shard bytes"
        )
    return census


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcRuntimeSourceFile:
    project_path: str
    content_sha256: str
    byte_count: int
    character_count: int
    content: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcRuntimeProjection:
    projection_id: str
    projection_sha256: str
    project_name: str
    backtest_name: str
    input_manifest: QcObjectPayloadBinding
    output_index_key: str
    output_content_prefix: str
    source_files: tuple[FormalQcRuntimeSourceFile, ...]
    project_source_set_sha256: str
    evaluator_source_closure: ArtifactBinding
    evaluator_source_closure_sha256: str
    formal_primary_fold_ids: tuple[str, ...]
    descriptive_sensitivity_fold_ids: tuple[str, ...]
    source_view_ids: tuple[str, ...]
    horizons: tuple[int, ...]
    primary_horizon: int
    physical_dependencies: tuple[str, ...]
    enabled_runtime_source: bool
    places_orders: bool
    object_store_output_required_for_result_read: bool
    summary_statistics_result_channel: bool
    cloud_compile_verified: bool
    cloud_execution_verified: bool
    _canonical_document: bytes = dataclasses.field(repr=False)


def _result_persistence_source() -> bytes:
    """Render the small action-bearing helper kept outside ``main.py``.

    The split preserves the observed QC per-file ceiling without weakening it.
    This source is included in the projection's exact source-set commitment;
    it has no entry point and receives the running algorithm only from the
    already authenticated formal runtime.
    """

    constants = {
        "FORMAL_RESULT_FAMILY_OBJECT_COUNT": (
            FORMAL_RESULT_FAMILY_OBJECT_COUNT
        ),
        "MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES": (
            MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
        ),
    }
    literals = "\n".join(
        f"{key} = {json.dumps(value, separators=(',', ':'))}"
        for key, value in constants.items()
    )
    body = r'''
import hashlib

__CONSTANTS__


def persist_formal_result_families(
        algorithm, manifest, references, family_objects):
    """Write once, reopen, and rehash all 26 content-addressed objects."""

    # Reauthenticate the output-specific capacity and transport contract after
    # evaluation, immediately before the first write.  The summary root remains
    # unpublished until every family object has either been created once or
    # matched existing identical bytes and has then been reopened and rehashed.
    if (type(manifest) is not dict
            or type(references) is not list
            or type(family_objects) is not tuple
            or len(references) != FORMAL_RESULT_FAMILY_OBJECT_COUNT
            or len(family_objects) != FORMAL_RESULT_FAMILY_OBJECT_COUNT):
        raise ValueError("formal result persistence inputs changed")
    capacity = manifest.get("capacity_review")
    limits = capacity.get("limits") if type(capacity) is dict else None
    contract = manifest.get("summary_result_contract")
    if (type(limits) is not dict
            or capacity.get(
                "object_store_output_write_once_transport_verified")
                is not True
            or capacity.get("summary_root_result_channel_verified") is not True
            or type(limits.get(
                "min_object_store_available_output_byte_count")) is not int
            or limits["min_object_store_available_output_byte_count"]
                < MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
            or type(limits.get(
                "min_object_store_available_output_file_count")) is not int
            or limits["min_object_store_available_output_file_count"]
                < FORMAL_RESULT_FAMILY_OBJECT_COUNT
            or type(contract) is not dict
            or contract.get(
                "object_store_write_once_existing_identical_bytes_only")
                is not True
            or contract.get(
                "object_store_save_then_reopen_and_rehash_required") is not True
            or contract.get(
                "root_summary_published_only_after_all_family_reopens")
                is not True):
        raise ValueError("formal result persistence authority changed")
    project_id = getattr(algorithm, "project_id", None)
    store = getattr(algorithm, "object_store", None)
    if type(project_id) is not int or project_id <= 0 or store is None:
        raise ValueError("formal result Object Store project identity changed")
    contains_key = getattr(store, "contains_key", None)
    read_bytes = getattr(store, "read_bytes", None)
    save_bytes = getattr(store, "save_bytes", None)
    if not all(callable(item) for item in (
            contains_key, read_bytes, save_bytes)):
        raise ValueError("formal result Object Store bytes API changed")

    full_keys = []
    for ordinal, (reference, supplied) in enumerate(zip(
            references, family_objects, strict=True)):
        if (type(reference) is not dict
                or type(supplied) is not tuple or len(supplied) != 2
                or reference.get("ordinal") != ordinal):
            raise ValueError("formal result persistence descriptor changed")
        suffix, payload = supplied
        if (type(suffix) is not str or type(payload) is not bytes
                or reference.get("object_store_key_suffix") != suffix
                or type(reference.get("compressed_byte_count")) is not int
                or reference["compressed_byte_count"] != len(payload)
                or hashlib.sha256(payload).hexdigest()
                    != reference.get("compressed_sha256")):
            raise ValueError("formal result persistence payload changed")
        key = str(project_id) + "/" + suffix
        exists = contains_key(key)
        if type(exists) is not bool:
            raise ValueError("formal result Object Store presence changed type")
        if exists:
            existing = bytes(read_bytes(key))
            if existing != payload:
                raise ValueError(
                    "formal result Object Store key collision changed bytes")
        elif save_bytes(key, payload) is not True:
            raise ValueError("formal result Object Store save refused")
        reopened = bytes(read_bytes(key))
        if (len(reopened) != reference["compressed_byte_count"]
                or hashlib.sha256(reopened).hexdigest()
                    != reference["compressed_sha256"]
                or reopened != payload):
            raise ValueError("formal result Object Store reopen changed bytes")
        full_keys.append(key)
    if (algorithm.object_store is not store
            or type(algorithm.project_id) is not int
            or algorithm.project_id != project_id
            or len(set(full_keys)) != FORMAL_RESULT_FAMILY_OBJECT_COUNT):
        raise ValueError("formal result Object Store identity changed")
    return tuple(full_keys)
'''
    return (
        textwrap.dedent(body)
        .replace("__CONSTANTS__", literals)
        .lstrip()
        .encode("utf-8")
    )


def _entry_source(
    input_manifest: QcObjectPayloadBinding,
    evaluator_closure_hash: str,
    formal_evaluator_hash: str,
    cloud_adapter_hash: str,
) -> bytes:
    constants = {
        "INPUT_MANIFEST_KEY": input_manifest.object_store_key,
        "INPUT_MANIFEST_SHA256": input_manifest.content_sha256,
        "INPUT_MANIFEST_BYTE_COUNT": input_manifest.byte_count,
        "CLOUD_EVALUATOR_SHA256": evaluator_closure_hash,
        "FORMAL_EVALUATOR_SOURCE_SHA256": formal_evaluator_hash,
        "CLOUD_ADAPTER_SOURCE_SHA256": cloud_adapter_hash,
        "INPUT_MANIFEST_SCHEMA": INPUT_MANIFEST_SCHEMA,
        "COMPRESSED_SHARD_SCHEMA": COMPRESSED_SHARD_SCHEMA,
        "AGGREGATE_RESULT_SCHEMA": AGGREGATE_RESULT_SCHEMA,
        "FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA": (
            FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
        ),
        "REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA": (
            REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        ),
        "REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX": (
            REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
        ),
        "FORMAL_RESULT_FAMILY_OBJECT_COUNT": (
            FORMAL_RESULT_FAMILY_OBJECT_COUNT
        ),
        "MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES": (
            MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES
        ),
        "MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES": (
            MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
        ),
        "MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES": (
            MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
        ),
        "MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES": (
            MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
        ),
        "DAILY_REQUIREMENT_SCHEMA": DAILY_REQUIREMENT_SCHEMA,
        "MINUTE_REQUIREMENT_SCHEMA": MINUTE_REQUIREMENT_SCHEMA,
        "MARKET_OBSERVATION_PANEL_SCHEMA": MARKET_OBSERVATION_PANEL_SCHEMA,
        "DAILY_OBSERVATION_SCHEMA": DAILY_OBSERVATION_SCHEMA,
        "MINUTE_OBSERVATION_SCHEMA": MINUTE_OBSERVATION_SCHEMA,
        "RESOURCE_CONTRACT_SCHEMA": RESOURCE_CONTRACT_SCHEMA,
        "UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA": (
            UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA
        ),
        "SUMMARY_RECEIPT_SCHEMA": SUMMARY_RECEIPT_SCHEMA,
        "SUMMARY_META_NAME": SUMMARY_META_NAME,
        "SUMMARY_CHUNK_PREFIX": SUMMARY_CHUNK_PREFIX,
        "SUMMARY_CHUNK_NAME_WIDTH": SUMMARY_CHUNK_NAME_WIDTH,
        "FORMAL_PRIMARY_FOLD_IDS": list(FORMAL_PRIMARY_FOLD_IDS),
        "DESCRIPTIVE_SENSITIVITY_FOLD_IDS": list(DESCRIPTIVE_SENSITIVITY_FOLD_IDS),
        "SOURCE_VIEW_IDS": list(SOURCE_VIEW_IDS),
        "HORIZONS": list(HORIZONS),
        "EVALUATION_ID": EVALUATION_ID,
        "SHARD_ROLE_ORDER": list(SHARD_ROLE_ORDER),
        "SHARD_ROW_SCHEMAS": SHARD_ROW_SCHEMAS,
        "MARKET_OBSERVATION_COLLECTION_PASSES": (
            MARKET_OBSERVATION_COLLECTION_PASSES
        ),
        "MAX_JSON_DEPTH": MAX_JSON_DEPTH,
        "DAILY_HISTORY_BLOCK_CALENDAR_DAYS": DAILY_HISTORY_BLOCK_CALENDAR_DAYS,
        "MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS": MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS,
    }
    literals = "\n".join(f"{key} = {json.dumps(value, separators=(',', ':'))}" for key, value in constants.items())
    body = r'''
from AlgorithmImports import *
import base64
import gzip
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from research.analyst_revisions_v2_qc.formal_cloud_evaluator import (
    begin_compact_formal_evaluation,
    begin_formal_market_panel_digest,
    consume_compact_formal_session_block,
    consume_formal_cloud_evaluation_output,
    consume_formal_market_panel_digest_row,
    finish_compact_formal_evaluation_output,
    finish_formal_market_panel_digest,
)
from research.analyst_revisions_v2_qc.formal_result_persistence import (
    persist_formal_result_families,
)

__CONSTANTS__


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


class AnalystRevisionsV2FormalOutcomeRuntime(QCAlgorithm):
    """One enabled no-orders collector; all result data stays aggregate-only."""

    def initialize(self):
        manifest = self._read_exact_object(
            INPUT_MANIFEST_KEY, INPUT_MANIFEST_SHA256,
            INPUT_MANIFEST_BYTE_COUNT, INPUT_MANIFEST_SCHEMA)
        self._validate_manifest(manifest)
        self._preflight_result_output(manifest)
        calculation = datetime.strptime(
            manifest["calculation_as_of_date"], "%Y-%m-%d")
        runtime_end = datetime.strptime(manifest["runtime_end"], "%Y-%m-%d")
        if calculation <= runtime_end:
            raise ValueError("sealed calculation date is not after the outcome window")
        self._calculation_as_of = calculation
        # History is requested only once the whole reviewed outcome window is
        # in the past.  The algorithm clock never begins at the evaluation
        # start and therefore never asks Initialize for future bars.
        self.set_start_date(calculation.year, calculation.month, calculation.day)
        engine_end = calculation + timedelta(days=1)
        self.set_end_date(engine_end.year, engine_end.month, engine_end.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_cash(100000)
        # History is deterministically collected twice.  Pass one seals the
        # shared panel without retaining it.  Pass two rederives the same seal
        # while feeding one complete fold/session block at a time to the
        # reviewed bounded-state evaluator.  No full row or observation graph
        # is materialized.
        self._history_call_counts = {"daily": 0, "minute": 0}
        panel_hash, panel_count = self._seal_market_panel(manifest)
        aggregate = self._stream_formal_evaluation(
            manifest, panel_hash, panel_count)
        self._publish_aggregate(manifest, aggregate)

    def _read_exact_object(self, key, expected_hash, expected_count, schema):
        if not self.object_store.contains_key(key):
            raise ValueError("required Object Store input is absent")
        payload = bytes(self.object_store.read_bytes(key))
        if len(payload) != expected_count or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError("Object Store input content identity changed")
        value = json.loads(payload.decode("utf-8"))
        if type(value) is not dict or value.get("schema") != schema or _canonical_bytes(value) != payload:
            raise ValueError("Object Store input is not exact canonical JSON")
        return value

    def _validate_manifest(self, value):
        if (value.get("schema") != INPUT_MANIFEST_SCHEMA
                or value.get("evaluation_id") != EVALUATION_ID
                or value.get("formal_primary_fold_ids") != FORMAL_PRIMARY_FOLD_IDS
                or value.get("descriptive_sensitivity_fold_ids") != DESCRIPTIVE_SENSITIVITY_FOLD_IDS
                or value.get("descriptive_sensitivity_cannot_replace_or_rescue_primary") is not True
                or value.get("source_view_ids") != SOURCE_VIEW_IDS
                or value.get("horizons") != HORIZONS
                or type(value.get("calculation_as_of_date")) is not str
                or value.get("capacity_evidence_is_submission_authority") is not False
                or value.get("external_owner_execution_authority_pin_required") is not True
                or value.get("orders_authorized") is not False
                or value.get("cloud_evaluator", {}).get("content_sha256") != CLOUD_EVALUATOR_SHA256):
            raise ValueError("formal runtime manifest geometry or evaluator changed")
        upstream = value.get("upstream_scoring_materialization_capacity")
        if (type(upstream) is not dict
                or upstream.get("schema")
                    != UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA
                or upstream.get("distinct_from_runtime_capacity") is not True
                or upstream.get("one_fold_streaming_projection_verified") is not True
                or upstream.get("production_truth_materialization_capacity_verified") is not True
                or upstream.get("representative_full_census_verified") is not True
                or upstream.get("artifact_binding") is None
                or upstream.get("launch_authorized") is not True):
            raise ValueError(
                "upstream scoring materialization capacity gate is closed")
        capacity = value.get("capacity_review")
        if type(capacity) is not dict or not all(capacity.get(name) is True for name in (
                "representative_full_census_verified", "target_tier_limits_observed",
                "cloud_evaluator_equivalence_verified", "object_store_input_transport_verified",
                "object_store_output_write_once_transport_verified",
                "summary_statistics_channel_verified",
                "summary_root_result_channel_verified")):
            raise ValueError("formal runtime capacity/equivalence gate is closed")
        capacity_limits = capacity.get("limits")
        component_count = value.get("resource_census", {}).get(
            "component_commitment_count")
        if (type(capacity_limits) is not dict
                or type(component_count) is not int
                or component_count < 0
                or type(capacity_limits.get("max_component_commitment_count"))
                    is not int
                or component_count
                    > capacity_limits["max_component_commitment_count"]):
            raise ValueError("full-run component commitment capacity is closed")
        if (capacity_limits.get("min_object_store_available_output_byte_count", 0)
                    < MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
                or capacity_limits.get("min_object_store_available_output_file_count", 0)
                    < FORMAL_RESULT_FAMILY_OBJECT_COUNT):
            raise ValueError("formal result Object Store capacity gate is closed")
        model = value.get("resource_model")
        if (type(model) is not dict
                or model.get("market_observation_collection_passes")
                    != MARKET_OBSERVATION_COLLECTION_PASSES
                or model.get("history_requests_use_multi_symbol_batches") is not True
                or model.get("batch_width_field") != "maximum_dynamic_subscription_count"
                or model.get("input_rows_are_incrementally_decoded") is not True
                or model.get("evaluation_uses_fold_session_blocks") is not True
                or model.get("component_commitments_are_full_run_bounded") is not True
                or model.get("maximum_horizon_session_lookahead") != 60
                or model.get("shared_market_panel_hash_is_verified_across_two_passes") is not True
                or model.get("daily_history_block_calendar_days")
                    != DAILY_HISTORY_BLOCK_CALENDAR_DAYS
                or model.get("maximum_daily_history_request_span_days")
                    != MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS
                or model.get("no_silent_truncation") is not True):
            raise ValueError("formal runtime resource model changed")
        market = value.get("market_contract")
        if (type(market) is not dict
                or market.get("daily_normalization") != "TotalReturn"
                or market.get("publication_price") != "last_tradable_minute_strictly_before_publication"
                or market.get("empty_positive_firm_weight_set_jump") != "0"
                or market.get("qc_delisting_price_is_terminal_payoff") is not False
                or market.get("failed_arm_omission_forbidden") is not True
                or market.get("shared_market_panel_across_views") is not True):
            raise ValueError("formal runtime market contract changed")

        census = value.get("resource_census")
        if (type(census) is not dict
                or census.get("schema") != RESOURCE_CONTRACT_SCHEMA
                or census.get("market_observation_collection_pass_count")
                    != MARKET_OBSERVATION_COLLECTION_PASSES):
            raise ValueError("formal runtime resource census changed")
        descriptors = value.get("shards")
        if type(descriptors) is not list or not descriptors:
            raise ValueError("compact shard inventory changed")
        seen_roles = []
        ordinals = {}
        for item in descriptors:
            if type(item) is not dict or item.get("role") not in SHARD_ROLE_ORDER:
                raise ValueError("compact shard descriptor changed")
            role = item["role"]
            if not seen_roles or seen_roles[-1] != role:
                seen_roles.append(role)
            ordinals.setdefault(role, []).append(item.get("ordinal"))
        if (seen_roles != SHARD_ROLE_ORDER
                or any(ordinals.get(role) != list(range(len(ordinals.get(role, []))))
                       for role in SHARD_ROLE_ORDER)):
            raise ValueError("compact shard inventory is incomplete or reordered")

    def _preflight_result_output(self, manifest):
        contract = manifest.get("summary_result_contract")
        expected = {
            "aggregate_result_schema": AGGREGATE_RESULT_SCHEMA,
            "summary_receipt_schema": SUMMARY_RECEIPT_SCHEMA,
            "cloud_evaluation_output_schema": FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA,
            "report_family_object_reference_schema": REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
            "meta_name": SUMMARY_META_NAME,
            "chunk_prefix": SUMMARY_CHUNK_PREFIX,
            "chunk_name_width": SUMMARY_CHUNK_NAME_WIDTH,
            "max_payload_byte_count": 200000,
            "max_chunk_count": 100,
            "max_chunk_characters": 4000,
            "fold_horizon_axis_count": 24,
            "source_view_fold_horizon_axis_count": 48,
            "raw_market_or_outcome_rows_in_summary_forbidden": True,
            "report_family_object_count": FORMAL_RESULT_FAMILY_OBJECT_COUNT,
            "report_family_object_key_suffix_prefix": REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX,
            "report_family_object_full_key_derivation": (
                "str(project_id)+'/'+authenticated_object_store_key_suffix"),
            "report_family_object_uncompressed_byte_ceiling": (
                MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES),
            "report_family_object_compressed_byte_ceiling": (
                MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES),
            "report_family_object_total_uncompressed_byte_ceiling": (
                MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES),
            "report_family_object_total_compressed_byte_ceiling": (
                MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES),
            "object_store_write_once_existing_identical_bytes_only": True,
            "object_store_save_then_reopen_and_rehash_required": True,
            "root_summary_published_only_after_all_family_reopens": True,
            "family_objects_required_for_result_read": True,
        }
        if contract != expected:
            raise ValueError("formal result output contract changed")
        if not all(callable(getattr(self.object_store, name, None)) for name in (
                "contains_key", "read_bytes", "save_bytes")):
            raise ValueError("formal result Object Store bytes API is unavailable")
        if not callable(getattr(self, "set_summary_statistic", None)):
            raise ValueError("formal result summary-root channel is unavailable")
        for name, minimum in (
            ("max_size", MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES),
            ("max_files", FORMAL_RESULT_FAMILY_OBJECT_COUNT),
        ):
            observed = getattr(self.object_store, name, None)
            if observed is None:
                continue
            observed = observed() if callable(observed) else observed
            if type(observed) is not int or observed < minimum:
                raise ValueError("formal result Object Store observed capacity is closed")

    @staticmethod
    def _json_tree_is_bounded(value, depth=0):
        if depth > MAX_JSON_DEPTH:
            return False
        if value is None or type(value) in (str, bool, int):
            return not (type(value) is int and abs(value) > 10 ** 18)
        if type(value) is list:
            return all(AnalystRevisionsV2FormalOutcomeRuntime._json_tree_is_bounded(
                item, depth + 1) for item in value)
        if type(value) is dict:
            return all(type(key) is str and
                       AnalystRevisionsV2FormalOutcomeRuntime._json_tree_is_bounded(
                           item, depth + 1)
                       for key, item in value.items())
        return False

    @staticmethod
    def _stream_key(role, row):
        try:
            if role == "formal_contract":
                return (0,)
            if role == "contribution_seeds":
                first = min(item[0] for item in row["active_intervals"])
                return (first, SOURCE_VIEW_IDS.index(row["source_view_id"]),
                        FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                        row["security_id"], row["seed_id"])
            if role == "decision_joins":
                return (FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                        row["session_position"],
                        SOURCE_VIEW_IDS.index(row["source_view_id"]),
                        row["security_id"])
            if role == "economic_joins":
                return (FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                        row["session_position"],
                        SOURCE_VIEW_IDS.index(row["source_view_id"]))
            if role == "daily_requirements":
                return (row["session"], row["security_id"], row["requirement_id"])
            if role == "minute_requirements":
                return (row["first_active_session_position"],
                        row["publication_at_utc"], row["security_id"],
                        row["requirement_id"])
            if role == "terminal_dispositions":
                horizon = -1 if row["horizon"] is None else row["horizon"]
                return (row["slot_kind"], row["slot_id"], horizon)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("compact stream key changed") from exc
        raise ValueError("compact stream role changed")

    @staticmethod
    def _stream_block_key(role, row):
        key = AnalystRevisionsV2FormalOutcomeRuntime._stream_key(role, row)
        if role == "contribution_seeds":
            return (FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]), key[0])
        if role == "decision_joins":
            return key[:2]
        if role == "daily_requirements":
            return (row["session"],)
        if role == "minute_requirements":
            return (row["first_active_session_position"],)
        return (role,)

    def _iter_role_rows(self, manifest, role):
        prior_key = None
        prior_shard_block = None
        observed_rows = 0
        descriptors = [item for item in manifest["shards"]
                       if item.get("role") == role]
        for item in descriptors:
            expected_fields = {
                "role", "ordinal", "schema", "object_store_key",
                "compression", "content_encoding", "compressed_sha256",
                "compressed_byte_count", "uncompressed_sha256",
                "uncompressed_byte_count", "row_count",
            }
            if (type(item) is not dict or set(item) != expected_fields
                    or item["schema"] != COMPRESSED_SHARD_SCHEMA
                    or item["compression"] != "gzip-mtime-zero"
                    or item["content_encoding"]
                        != "canonical-json-lines-utf8-lf"):
                raise ValueError("compact shard descriptor changed")
            key = item["object_store_key"]
            if not self.object_store.contains_key(key):
                raise ValueError("required compact input shard is absent")
            compressed = bytes(self.object_store.read_bytes(key))
            if (len(compressed) != item["compressed_byte_count"]
                    or hashlib.sha256(compressed).hexdigest()
                        != item["compressed_sha256"]):
                raise ValueError("compact input shard compressed identity changed")
            raw_hash = hashlib.sha256()
            raw_count = 0
            row_count = 0
            first_block = None
            last_block = None
            try:
                source = gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb")
                while True:
                    line = source.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        raise ValueError("compact input JSONL line lacks LF")
                    raw_hash.update(line)
                    raw_count += len(line)
                    row_count += 1
                    row = json.loads(line.decode("utf-8"))
                    if (type(row) is not dict or _canonical_bytes(row) != line
                            or not self._json_tree_is_bounded(row)
                            or row.get("schema") != SHARD_ROW_SCHEMAS[role]):
                        raise ValueError("compact input row is not exact canonical JSON")
                    stream_key = self._stream_key(role, row)
                    if prior_key is not None and stream_key <= prior_key:
                        raise ValueError("compact stream rows are duplicated or reordered")
                    prior_key = stream_key
                    block = self._stream_block_key(role, row)
                    first_block = block if first_block is None else first_block
                    last_block = block
                    observed_rows += 1
                    yield row
            except (OSError, EOFError) as exc:
                raise ValueError("compact input shard is not valid gzip") from exc
            if (raw_count != item["uncompressed_byte_count"]
                    or raw_hash.hexdigest() != item["uncompressed_sha256"]
                    or row_count != item["row_count"]):
                raise ValueError("compact input shard uncompressed identity changed")
            if first_block is not None and first_block == prior_shard_block:
                raise ValueError("one compact stream block was split across shards")
            if last_block is not None:
                prior_shard_block = last_block
        expected = manifest["resource_census"][{
            "formal_contract": "formal_contract_count",
            "contribution_seeds": "contribution_seed_count",
            "decision_joins": "decision_join_count",
            "economic_joins": "economic_join_count",
            "daily_requirements": "daily_requirement_count",
            "minute_requirements": "minute_requirement_count",
            "terminal_dispositions": "terminal_disposition_count",
        }[role]]
        if observed_rows != expected:
            raise ValueError("compact role row census changed")

    def _load_bounded_header(self, manifest, role):
        rows = list(self._iter_role_rows(manifest, role))
        census = manifest["resource_census"]
        limit = (census["terminal_header_uncompressed_byte_count"]
                 if role == "terminal_dispositions"
                 else census["bounded_header_uncompressed_byte_count"])
        if sum(len(_canonical_bytes(row)) for row in rows) > limit:
            raise ValueError("bounded compact header exceeded its resource census")
        return rows

    @staticmethod
    def _grouped(rows, key):
        current_key = None
        current = []
        seen = set()
        for row in rows:
            row_key = key(row)
            if current and row_key != current_key:
                if row_key in seen:
                    raise ValueError("compact stream group is noncontiguous")
                seen.add(current_key)
                yield current_key, current
                current = []
            current_key = row_key
            current.append(row)
        if current:
            if current_key in seen:
                raise ValueError("compact stream group is noncontiguous")
            yield current_key, current

    @staticmethod
    def _decimal_text(value):
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("market observation is not an exact decimal") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("market observation is not finite and positive")
        return format(parsed, "f")

    @staticmethod
    def _publication_instant(value):
        if type(value) is not str or not value.endswith("Z"):
            raise ValueError("publication instant is not canonical UTC")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("publication instant is not canonical UTC") from exc
        if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("publication instant zone changed")
        return parsed

    def _exact_symbol(self, security_id):
        if type(security_id) is not str or not security_id:
            raise ValueError("permanent QC security id is absent")
        symbol = self.symbol(security_id)
        if str(symbol.id) != security_id:
            raise ValueError("permanent QC security id did not round trip")
        return symbol

    @staticmethod
    def _batches(values, width):
        if type(width) is not int or width <= 0:
            raise ValueError("history security batch width changed")
        return [values[offset:offset + width]
                for offset in range(0, len(values), width)]

    def _record_history_call(self, role):
        if not hasattr(self, "_history_call_counts"):
            self._history_call_counts = {"daily": 0, "minute": 0}
        self._history_call_counts[role] += 1

    def _collect_daily_observations(self, requirements, batch_width):
        expected = {"schema", "requirement_id", "security_id", "session"}
        ordered = list(requirements)
        if any(type(row) is not dict or set(row) != expected
               or row.get("schema") != DAILY_REQUIREMENT_SCHEMA for row in ordered):
            raise ValueError("daily market requirement schema changed")
        if ordered != sorted(ordered, key=lambda row: self._stream_key(
                "daily_requirements", row)):
            raise ValueError("daily market requirements are reordered")
        by_block = {}
        for row in ordered:
            session = datetime.strptime(row["session"], "%Y-%m-%d")
            block = session.toordinal() // DAILY_HISTORY_BLOCK_CALENDAR_DAYS
            by_block.setdefault(block, {}).setdefault(
                row["security_id"], []).append(row)
        result = []
        for _block, block_rows in sorted(by_block.items()):
            for security_batch in self._batches(sorted(block_rows), batch_width):
                symbols = [self._exact_symbol(item) for item in security_batch]
                rows = [row for item in security_batch for row in block_rows[item]]
                sessions = [datetime.strptime(row["session"], "%Y-%m-%d")
                            for row in rows]
                if max(sessions) >= self._calculation_as_of:
                    raise ValueError("daily requirement is not sealed at calculation time")
                start = min(sessions) - timedelta(days=8)
                end = min(max(sessions) + timedelta(days=8), self._calculation_as_of)
                if (end - start).days > MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS:
                    raise ValueError("daily History request span changed")
                try:
                    self._record_history_call("daily")
                    history = self.history[TradeBar](
                        symbols, start, end, Resolution.DAILY,
                        data_normalization_mode=DataNormalizationMode.TOTAL_RETURN)
                except Exception:
                    history = None
                values = None
                requested = {(row["security_id"], row["session"]) for row in rows}
                if history is not None:
                    values = {}
                    for bar in history:
                        security_id = str(bar.symbol.id)
                        if security_id not in block_rows:
                            raise ValueError("daily history returned an unrequested security")
                        session = bar.time.date().isoformat()
                        key = (security_id, session)
                        if key not in requested:
                            continue
                        if key in values:
                            raise ValueError("daily TotalReturn history duplicated a session")
                        values[key] = self._decimal_text(bar.open)
                for row in rows:
                    observed = None if values is None else values.get(
                        (row["security_id"], row["session"])
                    )
                    result.append({
                        "schema": DAILY_OBSERVATION_SCHEMA,
                        "requirement_id": row["requirement_id"],
                        "security_id": row["security_id"],
                        "session": row["session"],
                        "disposition": "observation" if observed is not None else "named_refusal",
                        "open": observed,
                        "reason": None if observed is not None else
                            "qc_total_return_daily_open_unavailable",
                    })
        return sorted(result, key=lambda row: row["requirement_id"])

    @staticmethod
    def _bar_end_utc(bar):
        ended = bar.end_time
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=ZoneInfo("America/New_York"))
        return ended.astimezone(timezone.utc)

    def _collect_minute_observations(self, requirements, batch_width):
        expected = {
            "schema", "requirement_id", "security_id", "publication_at_utc",
            "first_active_session_position", "last_active_session_position",
        }
        ordered = list(requirements)
        if any(type(row) is not dict or set(row) != expected
               or row.get("schema") != MINUTE_REQUIREMENT_SCHEMA for row in ordered):
            raise ValueError("minute market requirement schema changed")
        if ordered != sorted(ordered, key=lambda row: self._stream_key(
                "minute_requirements", row)):
            raise ValueError("minute market requirements are reordered")
        grouped = {}
        parsed = {}
        for row in ordered:
            first = row["first_active_session_position"]
            last = row["last_active_session_position"]
            if (type(first) is not int or type(last) is not int
                    or first < 0 or last < first):
                raise ValueError("minute active-session interval changed")
            instant = self._publication_instant(row["publication_at_utc"])
            if instant >= self._calculation_as_of.replace(tzinfo=timezone.utc):
                raise ValueError("minute requirement is not sealed at calculation time")
            parsed[row["requirement_id"]] = instant
            grouped.setdefault((row["security_id"], instant.date()), []).append(row)
        result = []
        by_day = {}
        for (security_id, day), rows in grouped.items():
            by_day.setdefault(day, {})[security_id] = rows
        for day, day_rows in sorted(by_day.items()):
            for security_batch in self._batches(sorted(day_rows), batch_width):
                symbols = [self._exact_symbol(item) for item in security_batch]
                rows = [row for item in security_batch for row in day_rows[item]]
                latest = max(parsed[row["requirement_id"]] for row in rows)
                local_end = latest.astimezone(
                    ZoneInfo("America/New_York")).replace(tzinfo=None)
                try:
                    self._record_history_call("minute")
                    history = self.history[TradeBar](
                        symbols, local_end - timedelta(days=8), local_end,
                        Resolution.MINUTE,
                        data_normalization_mode=DataNormalizationMode.TOTAL_RETURN)
                except Exception:
                    history = None
                bars = None
                if history is not None:
                    bars = {item: [] for item in security_batch}
                    for bar in history:
                        security_id = str(bar.symbol.id)
                        if security_id not in bars:
                            raise ValueError(
                                "minute history returned an unrequested security")
                        ended = self._bar_end_utc(bar)
                        bars[security_id].append((ended, bar))
                for row in rows:
                    instant = parsed[row["requirement_id"]]
                    eligible = () if bars is None else tuple(
                        (ended, bar) for ended, bar in bars[row["security_id"]]
                        if ended < instant
                    )
                    if eligible:
                        ended, bar = max(eligible, key=lambda item: item[0])
                        price = self._decimal_text(bar.close)
                        ended_text = ended.strftime("%Y-%m-%dT%H:%M:%SZ")
                        disposition, reason = "observation", None
                    else:
                        price, ended_text = None, None
                        disposition = "named_refusal"
                        reason = "qc_last_tradable_prepublication_minute_unavailable"
                    result.append({
                        "schema": MINUTE_OBSERVATION_SCHEMA,
                        "requirement_id": row["requirement_id"],
                        "security_id": row["security_id"],
                        "publication_at_utc": row["publication_at_utc"],
                        "disposition": disposition,
                        "last_price": price,
                        "last_bar_end_utc": ended_text,
                        "reason": reason,
                    })
        return sorted(result, key=lambda row: row["requirement_id"])

    @staticmethod
    def _observation_map(requirements, observations):
        result = {row["requirement_id"]: row for row in observations}
        if (len(result) != len(observations)
                or set(result) != {row["requirement_id"] for row in requirements}):
            raise ValueError("market observation census changed")
        return result

    def _daily_observation_session_groups(self, manifest, batch_width, digest):
        rows = self._iter_role_rows(manifest, "daily_requirements")
        blocks = self._grouped(
            rows, lambda row: datetime.strptime(
                row["session"], "%Y-%m-%d").toordinal()
                // DAILY_HISTORY_BLOCK_CALENDAR_DAYS)
        for _block, requirements in blocks:
            observations = self._collect_daily_observations(
                requirements, batch_width)
            observed = self._observation_map(requirements, observations)
            for requirement in requirements:
                consume_formal_market_panel_digest_row(
                    digest, requirement=requirement,
                    observation=observed[requirement["requirement_id"]])
            for session, session_rows in self._grouped(
                    requirements, lambda row: row["session"]):
                yield (
                    session,
                    session_rows,
                    [observed[row["requirement_id"]] for row in session_rows],
                )

    def _minute_observation_activation_groups(self, manifest, batch_width, digest):
        rows = self._iter_role_rows(manifest, "minute_requirements")
        for first, requirements in self._grouped(
                rows, lambda row: row["first_active_session_position"]):
            observations = self._collect_minute_observations(
                requirements, batch_width)
            observed = self._observation_map(requirements, observations)
            for requirement in requirements:
                consume_formal_market_panel_digest_row(
                    digest, requirement=requirement,
                    observation=observed[requirement["requirement_id"]])
            yield first, requirements, [
                observed[row["requirement_id"]] for row in requirements
            ]

    @staticmethod
    def _next_or_none(iterator):
        try:
            return next(iterator)
        except StopIteration:
            return None

    def _seal_market_panel(self, manifest):
        census = manifest["resource_census"]
        expected_count = (census["daily_requirement_count"]
                          + census["minute_requirement_count"])
        digest = begin_formal_market_panel_digest(expected_count)
        batch_width = census["maximum_dynamic_subscription_count"]
        for _ in self._daily_observation_session_groups(
                manifest, batch_width, digest):
            pass
        for _ in self._minute_observation_activation_groups(
                manifest, batch_width, digest):
            pass
        panel_hash, panel_count = finish_formal_market_panel_digest(digest)
        if (self._history_call_counts["daily"] * 2
                != census["daily_history_batch_count"]
                or self._history_call_counts["minute"] * 2
                != census["minute_history_batch_count"]):
            raise ValueError("first History pass diverged from resource census")
        return panel_hash, panel_count

    @staticmethod
    def _decision_daily_requirement_ids(rows):
        result = set()
        for row in rows:
            if row.get("disposition") != "scored_decision":
                continue
            for name in (
                    "entry_daily_requirement_id",
                    "benchmark_entry_daily_requirement_id"):
                value = row.get(name)
                if type(value) is not str:
                    raise ValueError("scored decision daily requirement changed")
                result.add(value)
            exits = row.get("horizon_exits")
            if type(exits) is not list:
                raise ValueError("scored decision horizon exits changed")
            for item in exits:
                if type(item) is not dict:
                    raise ValueError("scored decision horizon exit changed")
                for name in (
                        "stock_daily_requirement_id",
                        "benchmark_daily_requirement_id"):
                    value = item.get(name)
                    if type(value) is not str:
                        raise ValueError("scored decision exit requirement changed")
                    result.add(value)
        return result

    @staticmethod
    def _cache_rows(cache):
        pairs = [pair for session in sorted(cache)
                 for pair in cache[session]]
        requirements = [pair[0] for pair in pairs]
        observations = [pair[1] for pair in pairs]
        return requirements, observations

    def _stream_formal_evaluation(self, manifest, panel_hash, panel_count):
        census = manifest["resource_census"]
        batch_width = census["maximum_dynamic_subscription_count"]
        formal_contract = self._load_bounded_header(manifest, "formal_contract")
        economic_joins = self._load_bounded_header(manifest, "economic_joins")
        terminal_rows = self._load_bounded_header(
            manifest, "terminal_dispositions")
        expected_blocks = [
            (row["fold_id"], row["session"], row["session_position"],
             row["next_session"], row.get("economic_observation_kind"),
             row.get("h20_decision_eligible"))
            for row in economic_joins
            if row.get("source_view_id") == SOURCE_VIEW_IDS[0]
        ]
        if not expected_blocks:
            raise ValueError("formal economic stream axis is empty")
        stream = begin_compact_formal_evaluation(
            manifest=manifest,
            formal_contract_rows=formal_contract,
            economic_joins=economic_joins,
            terminal_dispositions=terminal_rows,
            shared_market_panel_sha256=panel_hash,
            shared_market_panel_observation_count=panel_count,
        )
        second_digest = begin_formal_market_panel_digest(panel_count)
        daily_groups = iter(self._daily_observation_session_groups(
            manifest, batch_width, second_digest))
        minute_groups = iter(self._minute_observation_activation_groups(
            manifest, batch_width, second_digest))
        decision_groups = iter(self._grouped(
            self._iter_role_rows(manifest, "decision_joins"),
            lambda row: (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                row["session_position"],
            )))
        seed_groups = iter(self._grouped(
            self._iter_role_rows(manifest, "contribution_seeds"),
            lambda row: (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                min(item[0] for item in row["active_intervals"]),
            )))
        next_daily = self._next_or_none(daily_groups)
        next_minute = self._next_or_none(minute_groups)
        next_decisions = self._next_or_none(decision_groups)
        next_seeds = self._next_or_none(seed_groups)
        daily_cache = {}
        daily_ids = set()
        known_minute_ids = set()
        live_minute_expiry = {}
        component_commitments = set()
        for (fold_id, session, position, next_session, observation_kind,
             h20_decision_eligible) in expected_blocks:
            if (observation_kind not in {
                    "non_economic_decision_session",
                    "h20_decision_return_interval",
                    "h20_runoff_return_interval",
                    "terminal_liquidation_cost"}
                    or type(h20_decision_eligible) is not bool
                    or h20_decision_eligible is not (
                        observation_kind == "h20_decision_return_interval")):
                raise ValueError("economic observation marker changed")
            if ((observation_kind == "terminal_liquidation_cost")
                    is not (next_session is None)):
                raise ValueError("economic terminal next-session state changed")
            block_key = (FORMAL_PRIMARY_FOLD_IDS.index(fold_id), position)
            if next_decisions is not None and next_decisions[0] < block_key:
                raise ValueError("decision stream escaped its economic axis")
            if next_decisions is not None and next_decisions[0] == block_key:
                decisions = next_decisions[1]
                next_decisions = self._next_or_none(decision_groups)
            else:
                decisions = []
            for row in decisions:
                if row.get("disposition") == "scored_decision":
                    component = row.get("common_event_component_id")
                    view = row.get("source_view_id")
                    if (type(component) is not str or not component
                            or view not in SOURCE_VIEW_IDS):
                        raise ValueError("component commitment row changed")
                    component_commitments.add((view, component))
            if len(component_commitments) > census["component_commitment_count"]:
                raise ValueError("component commitment census exceeded")
            if len(decisions) > census["maximum_decision_session_row_count"]:
                raise ValueError("decision session block exceeded resource census")
            if next_seeds is not None and next_seeds[0] < block_key:
                raise ValueError("contribution stream escaped its activation block")
            if next_seeds is not None and next_seeds[0] == block_key:
                seeds = next_seeds[1]
                next_seeds = self._next_or_none(seed_groups)
            else:
                seeds = []
            if next_minute is not None and next_minute[0] < position:
                raise ValueError("minute stream escaped its activation block")
            if next_minute is not None and next_minute[0] == position:
                minute_requirements = next_minute[1]
                minute_observations = next_minute[2]
                next_minute = self._next_or_none(minute_groups)
            else:
                minute_requirements, minute_observations = [], []
            supplied_minute_ids = {
                row["requirement_id"] for row in minute_requirements
            }
            seed_minute_ids = {
                row["minute_requirement_id"] for row in seeds
                if row.get("minute_requirement_id") is not None
            }
            if supplied_minute_ids != seed_minute_ids - known_minute_ids:
                raise ValueError("minute requirement activation does not match seeds")
            for requirement_id in tuple(live_minute_expiry):
                if live_minute_expiry[requirement_id] < position:
                    live_minute_expiry.pop(requirement_id)
            for row in minute_requirements:
                live_minute_expiry[row["requirement_id"]] = row[
                    "last_active_session_position"]
            if len(live_minute_expiry) > census[
                    "maximum_live_active_minute_observation_count"]:
                raise ValueError("live minute observation cache exceeded resource census")
            known_minute_ids.update(supplied_minute_ids)

            # Discard dates older than this session, then read just far enough
            # to contain the exact active-horizon decision exits.  Economic
            # current/next market days are required on every economic return
            # interval, including the exact 19-session runoff.  The explicit
            # liquidation-cost observation has no market read.  The frozen
            # horizon ceiling makes this at most 61 sessions;
            # the observed row ceiling is checked before evaluation.
            for old_session in tuple(daily_cache):
                if old_session < session:
                    for requirement, _observation in daily_cache.pop(old_session):
                        daily_ids.remove(requirement["requirement_id"])
            needed = self._decision_daily_requirement_ids(decisions)
            required_sessions = (
                {session, next_session}
                if observation_kind in {
                    "h20_decision_return_interval",
                    "h20_runoff_return_interval",
                }
                else set()
            )
            while (not needed.issubset(daily_ids)
                   or not required_sessions.issubset(daily_cache)):
                if next_daily is None:
                    raise ValueError("daily stream lacks an exact session requirement")
                daily_session, requirements, observations = next_daily
                next_daily = self._next_or_none(daily_groups)
                if daily_session < session:
                    continue
                if daily_session in daily_cache:
                    raise ValueError("daily observation session was replayed")
                pairs = list(zip(requirements, observations))
                daily_cache[daily_session] = pairs
                daily_ids.update(row["requirement_id"] for row in requirements)
                if len(daily_ids) > census["maximum_live_daily_observation_count"]:
                    raise ValueError("live daily observation cache exceeded resource census")
            daily_requirements, daily_observations = self._cache_rows(daily_cache)
            consume_compact_formal_session_block(
                stream,
                fold_id=fold_id,
                session=session,
                session_position=position,
                decision_joins=decisions,
                new_contribution_seeds=seeds,
                daily_requirements=daily_requirements,
                minute_requirements=minute_requirements,
                observations={
                    "schema": MARKET_OBSERVATION_PANEL_SCHEMA,
                    "daily": daily_observations,
                    "minute": minute_observations,
                },
            )
        if next_decisions is not None or next_seeds is not None:
            raise ValueError("decision or contribution stream exceeds economic axis")
        if next_minute is not None:
            raise ValueError("minute requirement stream exceeds economic axis")
        if len(known_minute_ids) != census["minute_requirement_count"]:
            raise ValueError("minute requirement census changed during streaming")
        if len(component_commitments) != census["component_commitment_count"]:
            raise ValueError("component commitment census changed during streaming")
        # Finish the second pass even when the last required evaluator block did
        # not need the final market rows.  They remain part of the authenticated
        # shared panel, but are discarded immediately after hashing.
        while next_daily is not None:
            next_daily = self._next_or_none(daily_groups)
        second_hash, second_count = finish_formal_market_panel_digest(
            second_digest)
        if second_hash != panel_hash or second_count != panel_count:
            raise ValueError("second History pass changed the shared market panel")
        if (self._history_call_counts["daily"]
                != census["daily_history_batch_count"]
                or self._history_call_counts["minute"]
                != census["minute_history_batch_count"]):
            raise ValueError("two History passes diverged from resource census")
        return finish_compact_formal_evaluation_output(stream, resamples=19999)

    def _publish_aggregate(self, manifest, output):
        contract = manifest["summary_result_contract"]
        root_manifest, family_objects = consume_formal_cloud_evaluation_output(
            output)
        try:
            document = json.loads(root_manifest.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("cloud result root is not UTF-8 JSON") from exc
        references = document.get("report_family_objects")
        if (_canonical_bytes(document) != root_manifest
                or type(document) is not dict
                or document.get("schema") != AGGREGATE_RESULT_SCHEMA
                or document.get("evaluation_id") != EVALUATION_ID
                or document.get("bindings", {}).get("input_manifest_sha256") != INPUT_MANIFEST_SHA256
                or document.get("fold_horizon_axis_count") != 24
                or document.get("source_view_fold_horizon_axis_count") != 48
                or document.get("failed_arm_omission_count") != 0
                or document.get("orders_placed") != 0
                or "raw_rows" in document or "market_rows" in document
                or type(references) is not list
                or document.get("report_family_count")
                    != FORMAL_RESULT_FAMILY_OBJECT_COUNT
                or len(references) != FORMAL_RESULT_FAMILY_OBJECT_COUNT
                or len(family_objects) != FORMAL_RESULT_FAMILY_OBJECT_COUNT):
            raise ValueError("formal result root contract changed")
        expected_reference_fields = {
            "schema", "role", "ordinal", "source_view_id", "family_id",
            "family_output_id", "family_output_sha256", "payload_schema",
            "row_count", "formal_cloud_evaluator_contract_sha256",
            "input_manifest_sha256", "formal_report_contract_sha256",
            "object_store_key_suffix", "uncompressed_byte_count",
            "uncompressed_sha256", "compressed_byte_count",
            "compressed_sha256", "encoding",
        }
        suffixes = []
        total_uncompressed = 0
        total_compressed = 0
        for ordinal, (reference, supplied) in enumerate(zip(
                references, family_objects, strict=True)):
            suffix, family_payload = supplied
            if (type(reference) is not dict
                    or set(reference) != expected_reference_fields
                    or reference.get("schema")
                        != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
                    or reference.get("role") != "formal_report_family"
                    or reference.get("ordinal") != ordinal
                    or reference.get("object_store_key_suffix") != suffix
                    or type(suffix) is not str
                    or not suffix.startswith(REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX)
                    or suffix.startswith("/") or "//" in suffix
                    or any(part in ("", ".", "..") for part in suffix.split("/"))
                    or type(family_payload) is not bytes
                    or not family_payload
                    or type(reference.get("compressed_byte_count")) is not int
                    or reference["compressed_byte_count"] != len(family_payload)
                    or len(family_payload)
                        > MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
                    or hashlib.sha256(family_payload).hexdigest()
                        != reference.get("compressed_sha256")
                    or type(reference.get("uncompressed_byte_count")) is not int
                    or not 0 < reference["uncompressed_byte_count"]
                        <= MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES):
                raise ValueError("formal result family object changed")
            suffixes.append(suffix)
            total_uncompressed += reference["uncompressed_byte_count"]
            total_compressed += len(family_payload)
        if (len(set(suffixes)) != FORMAL_RESULT_FAMILY_OBJECT_COUNT
                or document.get("report_family_object_inventory_sha256")
                    != hashlib.sha256(_canonical_bytes(references)).hexdigest()
                or document.get(
                    "report_family_object_total_uncompressed_byte_count")
                    != total_uncompressed
                or document.get(
                    "report_family_object_total_compressed_byte_count")
                    != total_compressed
                or total_uncompressed
                    > MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
                or total_compressed > MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES):
            raise ValueError("formal result family object census changed")
        full_keys = persist_formal_result_families(
            self, manifest, references, family_objects)
        if (type(full_keys) is not tuple
                or len(full_keys) != FORMAL_RESULT_FAMILY_OBJECT_COUNT
                or len(set(full_keys)) != FORMAL_RESULT_FAMILY_OBJECT_COUNT):
            raise ValueError("formal result Object Store reopen census changed")
        payload_buffer = bytearray(
            gzip.compress(root_manifest, compresslevel=9, mtime=0)
        )
        # Python/zlib versions legitimately vary the gzip OS byte.  Normalize
        # that header field so the project owns a stable cross-runtime wire
        # contract without depending on local recompression equivalence.
        payload_buffer[9] = 255
        payload = bytes(payload_buffer)
        if len(payload) > contract["max_payload_byte_count"]:
            raise ValueError("formal result root exceeds reviewed summary capacity")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii")
        width = contract["max_chunk_characters"]
        chunks = [encoded[offset:offset + width] for offset in range(0, len(encoded), width)]
        if not chunks or len(chunks) > contract["max_chunk_count"]:
            raise ValueError("formal result root chunk count exceeds reviewed capacity")
        descriptors = []
        named_chunks = []
        for ordinal, chunk in enumerate(chunks):
            name = SUMMARY_CHUNK_PREFIX + str(ordinal).zfill(SUMMARY_CHUNK_NAME_WIDTH)
            named_chunks.append((name, chunk))
            descriptors.append({
                "name": name,
                "ordinal": ordinal,
                "character_count": len(chunk),
                "sha256": hashlib.sha256(chunk.encode("ascii")).hexdigest(),
            })
        receipt = {
            "schema": SUMMARY_RECEIPT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "input_manifest_sha256": INPUT_MANIFEST_SHA256,
            "cloud_evaluator_sha256": CLOUD_EVALUATOR_SHA256,
            "root_manifest_schema": AGGREGATE_RESULT_SCHEMA,
            "root_manifest_sha256": hashlib.sha256(root_manifest).hexdigest(),
            "root_manifest_byte_count": len(root_manifest),
            "compressed_root_sha256": hashlib.sha256(payload).hexdigest(),
            "compressed_root_byte_count": len(payload),
            "encoding": (
                "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
            ),
            "chunk_count": len(chunks),
            "chunks": descriptors,
            "report_family_object_reference_schema": (
                REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA),
            "report_family_object_count": FORMAL_RESULT_FAMILY_OBJECT_COUNT,
            "report_family_object_inventory_sha256": document[
                "report_family_object_inventory_sha256"],
            "report_family_object_total_uncompressed_byte_count": (
                total_uncompressed),
            "report_family_object_total_compressed_byte_count": total_compressed,
            "report_family_object_full_key_prefix": (
                str(self.project_id) + "/"
                + REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX),
            "object_store_write_once_existing_identical_bytes_only": True,
            "object_store_save_then_reopen_and_rehash_complete": True,
            "object_store_reopened_object_count": len(full_keys),
            "raw_report_family_rows_in_summary": False,
            "fold_horizon_axis_count": 24,
            "source_view_fold_horizon_axis_count": 48,
            "failed_arm_omission_count": 0,
            "orders_placed": 0,
        }
        meta = base64.urlsafe_b64encode(_canonical_bytes(receipt)).decode("ascii")
        if len(meta) > contract["max_chunk_characters"]:
            raise ValueError("formal result root metadata exceeds reviewed summary capacity")
        for name, chunk in named_chunks:
            self.set_summary_statistic(name, chunk)
        self.set_summary_statistic(SUMMARY_META_NAME, meta)
'''
    text = textwrap.dedent(body).replace("__CONSTANTS__", literals).lstrip()
    return text.encode("utf-8")


def _source_file(path: str, content: bytes) -> FormalQcRuntimeSourceFile:
    if type(content) is not bytes:
        raise FormalQcRuntimeProjectionError("project source must be exact bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise FormalQcRuntimeProjectionError("project source is not UTF-8") from exc
    if not text.endswith("\n") or len(text) > MAX_PROJECTED_SOURCE_CHARACTERS:
        raise FormalQcRuntimeProjectionError("project source exceeds size or LF contract")
    try:
        ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise FormalQcRuntimeProjectionError("project source is not valid Python") from exc
    forbidden = ("market_order", "set_holdings", "liquidate", "submit_order")
    if any(token in text.casefold() for token in forbidden):
        raise FormalQcRuntimeProjectionError("project source contains an order-shaped call")
    return FormalQcRuntimeSourceFile(
        project_path=path,
        content_sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        character_count=len(text),
        content=bytes(content),
    )


def formal_cloud_evaluator_binding(
    *, formal_evaluator_source: bytes, cloud_evaluator_source: bytes
) -> ArtifactBinding:
    """Bind logical evaluator bytes without the dynamic entry/facade carriers."""

    logical = []
    for path, content in (
        (FORMAL_EVALUATOR_PROJECT_PATH, formal_evaluator_source),
        (CLOUD_EVALUATOR_PROJECT_PATH, cloud_evaluator_source),
    ):
        if type(content) is not bytes or not content:
            raise FormalQcRuntimeProjectionError("evaluator source must be exact bytes")
        try:
            tree = ast.parse(content.decode("utf-8"), filename=path)
        except (UnicodeError, SyntaxError) as exc:
            raise FormalQcRuntimeProjectionError("evaluator source is not valid UTF-8 Python") from exc
        forbidden_calls = {
            "market_order", "set_holdings", "liquidate", "submit_order",
            "limit_order", "stop_market_order", "stop_limit_order",
        }
        if any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name) and node.func.id.casefold() in forbidden_calls
                or isinstance(node.func, ast.Attribute)
                and node.func.attr.casefold() in forbidden_calls
            )
            for node in ast.walk(tree)
        ):
            raise FormalQcRuntimeProjectionError("evaluator source contains an order call")
        logical.append(
            {
                "logical_path": path,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "byte_count": len(content),
            }
        )
    document = canonical_json_bytes(logical)
    digest = hashlib.sha256(document).hexdigest()
    return ArtifactBinding(
        artifact_id="arv2-formal-cloud-evaluator-" + digest[:24],
        content_sha256=digest,
        artifact_sha256=hashlib.sha256(b"arv2-cloud-evaluator-closure-v1\n" + document).hexdigest(),
        byte_count=len(formal_evaluator_source) + len(cloud_evaluator_source),
    )


def _carrier_source(encoded: str) -> bytes:
    literals = "\n    ".join(
        repr(encoded[offset : offset + MODULE_CARRIER_LITERAL_CHARACTERS])
        for offset in range(0, len(encoded), MODULE_CARRIER_LITERAL_CHARACTERS)
    )
    return ("DATA = (\n    " + literals + "\n)\n").encode("ascii")


def _project_canonical_module(
    *, canonical_path: str, canonical_source: bytes
) -> tuple[FormalQcRuntimeSourceFile, ...]:
    """Project one >60k logical module as an exact hash-checking facade."""

    encoded = base64.b64encode(canonical_source).decode("ascii")
    chunks = tuple(
        encoded[offset : offset + MODULE_CARRIER_BASE64_CHARACTERS]
        for offset in range(0, len(encoded), MODULE_CARRIER_BASE64_CHARACTERS)
    )
    stem = canonical_path[:-3]
    module_prefix = stem.rsplit("/", 1)[1]
    imports = []
    aliases = []
    files: list[FormalQcRuntimeSourceFile] = []
    for ordinal, chunk in enumerate(chunks):
        module_name = f"_{module_prefix}_carrier_{ordinal:03d}"
        path = stem.rsplit("/", 1)[0] + "/" + module_name + ".py"
        alias = f"_c{ordinal:03d}"
        imports.append(f"from .{module_name} import DATA as {alias}")
        aliases.append(alias)
        files.append(_source_file(path, _carrier_source(chunk)))
    digest = hashlib.sha256(canonical_source).hexdigest()
    facade = (
        "import base64 as _base64\n"
        "import hashlib as _hashlib\n"
        + "\n".join(imports)
        + "\n_DATA = _base64.b64decode(("
        + ",".join(aliases)
        + ").encode('ascii'), validate=True)\n"
        + f"if _hashlib.sha256(_DATA).hexdigest() != {digest!r}:\n"
        + "    raise RuntimeError('canonical evaluator source reconstruction changed')\n"
        + f"exec(compile(_DATA.decode('utf-8'), {canonical_path!r}, 'exec'), globals(), globals())\n"
        + "del _DATA\n"
    ).encode("utf-8")
    return (_source_file(canonical_path, facade), *files)


def build_formal_qc_runtime_projection(
    *,
    input_manifest: QcObjectPayloadBinding,
    formal_evaluator_source: bytes,
    cloud_evaluator_source: bytes,
) -> FormalQcRuntimeProjection:
    require_qc_object_payload_binding(input_manifest)
    if (
        input_manifest.role != "input_manifest"
        or input_manifest.schema != INPUT_MANIFEST_SCHEMA
        or input_manifest.object_store_key != FORMAL_INPUT_PREFIX + input_manifest.content_sha256 + ".json"
    ):
        raise FormalQcRuntimeProjectionError("input manifest binding is not exact/content-addressed")
    evaluator_closure = formal_cloud_evaluator_binding(
        formal_evaluator_source=formal_evaluator_source,
        cloud_evaluator_source=cloud_evaluator_source,
    )
    if input_manifest.schema != INPUT_MANIFEST_SCHEMA:
        raise FormalQcRuntimeProjectionError("input manifest schema changed")
    formal_files = _project_canonical_module(
        canonical_path=FORMAL_EVALUATOR_PROJECT_PATH,
        canonical_source=formal_evaluator_source,
    )
    cloud_files = _project_canonical_module(
        canonical_path=CLOUD_EVALUATOR_PROJECT_PATH,
        canonical_source=cloud_evaluator_source,
    )
    entry_file = _source_file(
        ENTRY_PROJECT_PATH,
        _entry_source(
            input_manifest,
            evaluator_closure.content_sha256,
            hashlib.sha256(formal_evaluator_source).hexdigest(),
            hashlib.sha256(cloud_evaluator_source).hexdigest(),
        ),
    )
    files = (
        entry_file,
        _source_file("research/__init__.py", b"# ARV2 projected package\n"),
        _source_file(
            "research/analyst_revisions_v2_qc/__init__.py",
            b"# ARV2 formal QC projected package\n",
        ),
        _source_file(
            FORMAL_RESULT_PERSISTENCE_PROJECT_PATH,
            _result_persistence_source(),
        ),
        *formal_files,
        *cloud_files,
    )
    source_manifest = [
        {
            "project_path": item.project_path,
            "content_sha256": item.content_sha256,
            "byte_count": item.byte_count,
            "character_count": item.character_count,
        }
        for item in files
    ]
    source_set_hash = hashlib.sha256(canonical_json_bytes(source_manifest)).hexdigest()
    seed: dict[str, object] = {
        "schema": SCHEMA,
        "projection_id": None,
        "projection_sha256": None,
        "status": STATUS,
        "authority": AUTHORITY,
        "project_name": PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "input_manifest": input_manifest.to_record(),
        "source_files": source_manifest,
        "project_source_set_sha256": source_set_hash,
        "evaluator_source_closure": evaluator_closure.to_record(),
        "evaluator_source_closure_sha256": evaluator_closure.content_sha256,
        "execution_geometry": {
            "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
            "descriptive_sensitivity_fold_ids": list(DESCRIPTIVE_SENSITIVITY_FOLD_IDS),
            "descriptive_sensitivity_cannot_replace_or_rescue_primary": True,
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "horizons": list(HORIZONS),
            "primary_horizon": PRIMARY_HORIZON,
        },
        "result_channel": {
            "object_store_output_required_for_result_read": True,
            "summary_statistics_result_channel": True,
            "summary_statistics_carries_root_only": True,
            "report_family_object_count": FORMAL_RESULT_FAMILY_OBJECT_COUNT,
            "report_family_object_reference_schema": (
                REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
            ),
            "report_family_object_key_suffix_prefix": (
                REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
            ),
            "meta_name": SUMMARY_META_NAME,
            "chunk_prefix": SUMMARY_CHUNK_PREFIX,
        },
        "physical_dependencies": list(PHYSICAL_DEPENDENCIES),
        "truth_state": {"cloud_compile_verified": False, "cloud_execution_verified": False},
        "places_orders": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    seed["projection_sha256"] = digest
    seed["projection_id"] = "arv2-formal-qc-runtime-" + digest[:24]
    payload = canonical_json_bytes(seed)
    value = FormalQcRuntimeProjection(
        projection_id=str(seed["projection_id"]),
        projection_sha256=digest,
        project_name=PROJECT_NAME,
        backtest_name=BACKTEST_NAME,
        input_manifest=input_manifest,
        output_index_key=FORMAL_OUTPUT_INDEX_PREFIX + input_manifest.content_sha256,
        output_content_prefix=FORMAL_OUTPUT_PREFIX,
        source_files=files,
        project_source_set_sha256=source_set_hash,
        evaluator_source_closure=evaluator_closure,
        evaluator_source_closure_sha256=evaluator_closure.content_sha256,
        formal_primary_fold_ids=FORMAL_PRIMARY_FOLD_IDS,
        descriptive_sensitivity_fold_ids=DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        source_view_ids=SOURCE_VIEW_IDS,
        horizons=HORIZONS,
        primary_horizon=PRIMARY_HORIZON,
        physical_dependencies=PHYSICAL_DEPENDENCIES,
        enabled_runtime_source=True,
        places_orders=False,
        object_store_output_required_for_result_read=True,
        summary_statistics_result_channel=True,
        cloud_compile_verified=False,
        cloud_execution_verified=False,
        _canonical_document=payload,
    )
    return value


def require_formal_qc_runtime_projection(
    value: FormalQcRuntimeProjection,
) -> FormalQcRuntimeProjection:
    if type(value) is not FormalQcRuntimeProjection:
        raise FormalQcRuntimeProjectionError("runtime projection type changed")
    rebuilt = build_formal_qc_runtime_projection(
        input_manifest=value.input_manifest,
        formal_evaluator_source=_reconstruct_projected_module_source(
            value.source_files, FORMAL_EVALUATOR_PROJECT_PATH
        ),
        cloud_evaluator_source=_reconstruct_projected_module_source(
            value.source_files, CLOUD_EVALUATOR_PROJECT_PATH
        ),
    ) if type(value.source_files) is tuple and len(value.source_files) >= 6 else None
    if rebuilt is None or any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcRuntimeProjection)
    ):
        raise FormalQcRuntimeProjectionError("runtime projection changed")
    return value


def _reconstruct_projected_module_source(
    files: tuple[FormalQcRuntimeSourceFile, ...], canonical_path: str
) -> bytes:
    stem = canonical_path[:-3]
    prefix = stem.rsplit("/", 1)[0] + "/_" + stem.rsplit("/", 1)[1] + "_carrier_"
    carriers = tuple(sorted(
        (item for item in files if item.project_path.startswith(prefix)),
        key=lambda item: item.project_path,
    ))
    if not carriers:
        raise FormalQcRuntimeProjectionError("projected evaluator carriers are absent")
    encoded = ""
    for item in carriers:
        tree = ast.parse(item.content.decode("ascii"), filename=item.project_path)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
            raise FormalQcRuntimeProjectionError("projected evaluator carrier shape changed")
        value = ast.literal_eval(tree.body[0].value)
        if type(value) is not str:
            raise FormalQcRuntimeProjectionError("projected evaluator carrier data changed")
        encoded += value
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as exc:
        raise FormalQcRuntimeProjectionError("projected evaluator carrier encoding changed") from exc


def render_formal_qc_runtime_projection_bytes(value: FormalQcRuntimeProjection) -> bytes:
    require_formal_qc_runtime_projection(value)
    return bytes(value._canonical_document)


def formal_code_projection_binding(value: FormalQcRuntimeProjection) -> ArtifactBinding:
    require_formal_qc_runtime_projection(value)
    return ArtifactBinding(
        artifact_id=value.projection_id,
        content_sha256=value.project_source_set_sha256,
        artifact_sha256=hashlib.sha256(value._canonical_document).hexdigest(),
        byte_count=sum(item.byte_count for item in value.source_files),
    )


def require_projection_bound_to_candidate(
    candidate: FormalRunCandidate, projection: FormalQcRuntimeProjection
) -> FormalQcRuntimeProjection:
    require_formal_run_candidate(candidate)
    require_formal_qc_runtime_projection(projection)
    if candidate.code_projection != formal_code_projection_binding(projection):
        raise FormalQcRuntimeProjectionError("formal run candidate binds different projected code")
    return projection


__all__ = (
    "ABSOLUTE_MAX_SUMMARY_CHUNKS", "AGGREGATE_RESULT_SCHEMA", "AUTHORITY",
    "BACKTEST_NAME", "CAPACITY_LIMIT_NAMES", "CAPACITY_REVIEW_SCHEMA",
    "CLOUD_EVALUATOR_ENTRYPOINT",
    "CLOUD_EVALUATOR_INTERFACE_SCHEMA", "CLOUD_EVALUATOR_PROJECT_PATH",
    "COMPRESSED_SHARD_SCHEMA", "CONTRIBUTION_SEED_SCHEMA",
    "DAILY_OBSERVATION_SCHEMA", "DAILY_REQUIREMENT_SCHEMA", "DECISION_JOIN_SCHEMA",
    "DECISION_OBJECT_SCHEMA", "ECONOMIC_JOIN_SCHEMA", "ENTRY_CLASS_NAME",
    "ENTRY_PROJECT_PATH", "FORMAL_CONTRACT_SCHEMA", "FORMAL_EVALUATOR_PROJECT_PATH",
    "FORMAL_INPUT_CONTENT_PREFIX", "FORMAL_INPUT_PREFIX",
    "FORMAL_RESULT_FAMILY_OBJECT_COUNT",
    "FORMAL_RESULT_PERSISTENCE_PROJECT_PATH",
    "FORMAL_RESULT_WORKING_SET_MEMORY_BYTES",
    "FORMAL_OUTPUT_INDEX_PREFIX", "FORMAL_OUTPUT_PREFIX",
    "FormalQcCompressedShard", "FormalQcRuntimeCapacityBinding",
    "FormalQcRuntimeProjection", "FormalQcRuntimeProjectionError",
    "FormalQcRuntimeResourceCensus", "FormalQcRuntimeSourceFile", "HORIZONS",
    "INPUT_MANIFEST_SCHEMA", "MAX_PROJECTED_SOURCE_CHARACTERS",
    "MARKET_OBSERVATION_PANEL_SCHEMA", "MINUTE_OBSERVATION_SCHEMA",
    "MINUTE_REQUIREMENT_SCHEMA", "OUTPUT_INDEX_SCHEMA", "OUTPUT_OBJECT_SCHEMA",
    "PHYSICAL_DEPENDENCIES", "PROJECT_NAME", "QcObjectPayloadBinding",
    "RESOURCE_CONTRACT_SCHEMA", "SCHEMA", "SHARD_ROLE_ORDER",
    "SLEEVE_HOLDING_SESSIONS", "STATUS", "SUMMARY_CHUNK_PREFIX",
    "SUMMARY_META_NAME", "SUMMARY_RECEIPT_SCHEMA", "TERMINAL_OBJECT_SCHEMA",
    "UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA",
    "build_daily_market_requirement_id", "build_formal_qc_compressed_shard",
    "build_formal_qc_input_manifest_bytes", "build_formal_qc_runtime_projection",
    "build_minute_market_requirement_id", "build_qc_object_payload_binding",
    "canonical_json_bytes", "derive_formal_qc_runtime_resource_census",
    "formal_cloud_evaluator_binding", "formal_code_projection_binding",
    "load_formal_qc_runtime_capacity_binding",
    "render_formal_qc_capacity_review_candidate",
    "render_formal_qc_runtime_projection_bytes", "require_formal_qc_compressed_shard",
    "require_formal_qc_runtime_capacity_binding", "require_formal_qc_runtime_projection",
    "require_projection_bound_to_candidate", "validate_formal_qc_runtime_resource_candidate",
    "require_qc_object_payload_binding",
)
