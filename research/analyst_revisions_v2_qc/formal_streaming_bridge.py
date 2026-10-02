"""Disk-backed ARV2 streamed-input to formal-runtime bridge.

This host-only module derives the exact formal runtime resource census while
reopening one authenticated physical shard at a time.  Unbounded uniqueness
and grouping state lives in a private SQLite spool, not Python containers.  It
then binds an independently reviewed runtime-capacity receipt and a second
independently reviewed streamed-bridge receipt to the exact candidate, shard
archive, resource census, manifest, and runtime projection.

The resulting bridge remains non-actionable.  It exposes a sequential upload
iterator whose final item is the content-addressed manifest, but it never calls
a transport and never grants provider, outcome, QuantConnect, result, order,
deployment, or trading authority.  A separate reviewed orchestration gate and
owner-signature authority remain mandatory.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import os
import sqlite3
import sys
import tempfile
import threading
import weakref
from collections import deque
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    acquisition_receipt_artifact_binding_record,
)

from . import formal_runtime_projection as runtime
from .formal_economic_execution_definition import (
    FormalEconomicExecutionBinding,
    FormalEconomicExecutionDefinitionError,
    formal_economic_terminal_liquidation_session,
    require_formal_economic_execution_binding,
)
from .formal_report_contract import (
    FormalReportContract,
    FormalReportContractError,
    require_formal_report_contract,
)
from .formal_run_protocol import (
    ArtifactBinding,
    FormalRunCandidate,
    build_formal_run_candidate,
    require_artifact_binding,
    require_formal_run_candidate,
)
from .formal_streaming_input import (
    FormalStreamingInputError,
    FormalStreamingRefusalReason,
    FormalStreamingRunRefusal,
    PhysicalFormalShardArchive,
    STREAMED_FORMAL_CONTRACT_VARIANT,
    StreamedFormalInputCandidate,
    _read_private_regular,
    _strict_object,
    iter_physical_formal_shard_payloads,
    require_physical_formal_shard_archive,
    require_streamed_formal_input_candidate,
    streamed_formal_contract_record,
)
from .formal_terminal_disposition_builder import (
    FormalTerminalDispositionBuild,
    FormalTerminalDispositionBuildError,
    require_formal_terminal_disposition_build,
)


class FormalStreamingBridgeError(ValueError):
    """The streamed census, review receipt, manifest, or replay is invalid."""


RESOURCE_CANDIDATE_SCHEMA = "arv2-streamed-formal-runtime-resource-candidate-v1"
BRIDGE_CAPACITY_SCHEMA = "arv2-streamed-formal-runtime-bridge-capacity-review-v1"
BRIDGE_SCHEMA = "arv2-streamed-formal-runtime-bridge-v1"
PRODUCTION_INPUT_SCHEMA = "arv2-streamed-formal-production-input-binding-v1"
UPLOAD_PROJECTION_SCHEMA = "arv2-streamed-formal-upload-projection-v1"
PARTITION_BINDING_SCHEMA = "arv2-streamed-formal-source-view-partition-binding-v1"
TERMINAL_KEY_CENSUS_DOMAIN = "arv2-formal-terminal-key-census-v2"
STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA = (
    "arv2-streamed-formal-input-manifest-lineage-v1"
)
MAX_RUNTIME_CAPACITY_RECEIPT_BYTES = 1024 * 1024
MAX_BRIDGE_CAPACITY_RECEIPT_BYTES = 1024 * 1024
MAX_DYNAMIC_SUBSCRIPTION_COUNT = 48
_RUNTIME_START = date(2020, 1, 3)
# Logical outcome interval, not the one-day LEAN engine clock.  The final
# admissible 2025 decision is 2025-12-31 and its reviewed H60 exit is exactly
# 2026-03-30 on the authenticated XNYS axis.
_RUNTIME_END = date(2026, 3, 30)


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFormalUploadDescriptor:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFormalUploadEntry:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int
    payload: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5,
            "byte_count": self.byte_count,
        }


class _BytesViewReader:
    """Sequential read-only view without duplicating a compressed shard."""

    __slots__ = ("_position", "_view")

    def __init__(self, payload: bytes) -> None:
        self._view = memoryview(payload)
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._view) - self._position
        count = min(size, len(self._view) - self._position)
        result = self._view[self._position : self._position + count].tobytes()
        self._position += count
        return result


class _DiskResourceGeometry:
    """Exact runtime geometry with whole-run sets/groups stored on disk."""

    def __init__(self, maximum_spool_bytes: int) -> None:
        self.maximum_spool_bytes = maximum_spool_bytes
        self.directory = Path(tempfile.mkdtemp(prefix="arv2-runtime-resource-"))
        os.chmod(self.directory, 0o700)
        self.path = self.directory / "resource.sqlite3"
        descriptor = os.open(
            self.path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.executescript(
            """
            CREATE TABLE security (security_id TEXT PRIMARY KEY) WITHOUT ROWID;
            CREATE TABLE daily_block (
                block_id INTEGER NOT NULL,
                security_id TEXT NOT NULL,
                PRIMARY KEY (block_id, security_id)
            ) WITHOUT ROWID;
            CREATE TABLE daily_session (
                session TEXT PRIMARY KEY,
                row_count INTEGER NOT NULL,
                byte_count INTEGER NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE minute_activation (
                first_active INTEGER NOT NULL,
                publication_day TEXT NOT NULL,
                security_id TEXT NOT NULL,
                PRIMARY KEY (first_active, publication_day, security_id)
            ) WITHOUT ROWID;
            CREATE TABLE minute_day (
                publication_day TEXT PRIMARY KEY,
                row_count INTEGER NOT NULL,
                byte_count INTEGER NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE decision_block (
                fold_index INTEGER NOT NULL,
                session_position INTEGER NOT NULL,
                row_count INTEGER NOT NULL,
                byte_count INTEGER NOT NULL,
                PRIMARY KEY (fold_index, session_position)
            ) WITHOUT ROWID;
            CREATE TABLE component (
                source_view_id TEXT NOT NULL,
                component_id TEXT NOT NULL,
                PRIMARY KEY (source_view_id, component_id)
            ) WITHOUT ROWID;
            CREATE TABLE minute_delta (
                session_position INTEGER PRIMARY KEY,
                delta INTEGER NOT NULL
            ) WITHOUT ROWID;
            """
        )
        self.peak_bytes = 0
        self.partition_counts = {
            view: {"decision": 0, "scored": 0, "refused": 0}
            for view in runtime.SOURCE_VIEW_IDS
        }
        self.partition_hashers = {}
        for view in runtime.SOURCE_VIEW_IDS:
            hasher = hashlib.sha256()
            hasher.update(TERMINAL_KEY_CENSUS_DOMAIN.encode("ascii") + b"\0")
            self.partition_hashers[view] = hasher

    def __enter__(self) -> _DiskResourceGeometry:
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        try:
            self.connection.close()
        finally:
            for name in (
                "resource.sqlite3-journal",
                "resource.sqlite3-wal",
                "resource.sqlite3-shm",
                "resource.sqlite3",
            ):
                path = self.directory / name
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            try:
                self.directory.rmdir()
            except FileNotFoundError:
                pass

    def _upsert_sum(
        self, table: str, key_name: str, key: object, count: int, byte_count: int
    ) -> None:
        self.connection.execute(
            f"INSERT INTO {table} ({key_name}, row_count, byte_count) VALUES (?, ?, ?) "
            f"ON CONFLICT({key_name}) DO UPDATE SET "
            "row_count=row_count+excluded.row_count, "
            "byte_count=byte_count+excluded.byte_count",
            (key, count, byte_count),
        )

    def _upsert_decision(self, fold: int, position: int, byte_count: int) -> None:
        self.connection.execute(
            "INSERT INTO decision_block "
            "(fold_index, session_position, row_count, byte_count) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(fold_index, session_position) DO UPDATE SET "
            "row_count=row_count+1, byte_count=byte_count+excluded.byte_count",
            (fold, position, byte_count),
        )

    def _upsert_delta(self, position: int, delta: int) -> None:
        self.connection.execute(
            "INSERT INTO minute_delta (session_position, delta) VALUES (?, ?) "
            "ON CONFLICT(session_position) DO UPDATE SET delta=delta+excluded.delta",
            (position, delta),
        )

    def observe_row(self, role: str, row: dict[str, object], byte_count: int) -> None:
        if role == "decision_joins":
            fold = runtime._safe_id(row.get("fold_id"), "decision stream fold")
            view = runtime._safe_id(row.get("source_view_id"), "decision stream view")
            position = runtime._positive_int(
                row.get("session_position"),
                "decision session position",
                allow_zero=True,
            )
            if fold not in runtime.FORMAL_PRIMARY_FOLD_IDS or view not in runtime.SOURCE_VIEW_IDS:
                raise FormalStreamingBridgeError("decision stream geometry changed")
            security = runtime._safe_id(
                row.get("security_id"), "decision stream security"
            )
            self._upsert_decision(
                runtime.FORMAL_PRIMARY_FOLD_IDS.index(fold), position, byte_count
            )
            disposition = row.get("disposition")
            if disposition == "scored_decision":
                self.partition_counts[view]["scored"] += 1
                component = runtime._safe_id(
                    row.get("common_event_component_id"), "component commitment id"
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO component VALUES (?, ?)", (view, component)
                )
            elif disposition == "named_preoutcome_refusal":
                self.partition_counts[view]["refused"] += 1
            else:
                raise FormalStreamingBridgeError("decision stream disposition changed")
            terminal = canonical_json_bytes(
                {
                    "fold_id": fold,
                    "session_position": position,
                    "security_id": security,
                }
            )
            self.partition_hashers[view].update(len(terminal).to_bytes(8, "big"))
            self.partition_hashers[view].update(terminal)
            self.partition_counts[view]["decision"] += 1
            return
        if role == "daily_requirements":
            session = runtime._iso_date(row.get("session"), "daily requirement session")
            security = runtime._safe_id(row.get("security_id"), "daily market security")
            runtime._safe_id(row.get("requirement_id"), "daily requirement id")
            block = date.fromisoformat(session).toordinal() // runtime.DAILY_HISTORY_BLOCK_CALENDAR_DAYS
            self.connection.execute("INSERT OR IGNORE INTO security VALUES (?)", (security,))
            self.connection.execute(
                "INSERT OR IGNORE INTO daily_block VALUES (?, ?)", (block, security)
            )
            self._upsert_sum("daily_session", "session", session, 1, byte_count)
            return
        if role == "minute_requirements":
            publication = runtime._utc_text(
                row.get("publication_at_utc"), "publication_at_utc"
            )
            security = runtime._safe_id(row.get("security_id"), "minute market security")
            runtime._safe_id(row.get("requirement_id"), "minute requirement id")
            first_active = runtime._positive_int(
                row.get("first_active_session_position"),
                "minute first active session position",
                allow_zero=True,
            )
            last_active = runtime._positive_int(
                row.get("last_active_session_position"),
                "minute last active session position",
                allow_zero=True,
            )
            if last_active < first_active:
                raise FormalStreamingBridgeError("minute active-session interval changed")
            day = publication[:10]
            self.connection.execute("INSERT OR IGNORE INTO security VALUES (?)", (security,))
            self.connection.execute(
                "INSERT OR IGNORE INTO minute_activation VALUES (?, ?, ?)",
                (first_active, day, security),
            )
            self._upsert_sum("minute_day", "publication_day", day, 1, byte_count)
            self._upsert_delta(first_active, 1)
            self._upsert_delta(last_active + 1, -1)

    def commit_and_bound(self) -> None:
        self.connection.commit()
        page_count = int(self.connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(self.connection.execute("PRAGMA page_size").fetchone()[0])
        current = page_count * page_size
        self.peak_bytes = max(self.peak_bytes, current)
        if current > self.maximum_spool_bytes:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.RESOURCE_CENSUS_CAPACITY_EXCEEDED,
                "disk-backed runtime resource census exceeded reviewed capacity",
            )

    def scalar(self, query: str, parameters: tuple[object, ...] = ()) -> int:
        value = self.connection.execute(query, parameters).fetchone()[0]
        return int(value or 0)

    def maximum_live_daily(self) -> int:
        window: deque[int] = deque()
        live = 0
        maximum = 0
        for (count,) in self.connection.execute(
            "SELECT row_count FROM daily_session ORDER BY session"
        ):
            value = int(count)
            window.append(value)
            live += value
            if len(window) > 61:
                live -= window.popleft()
            maximum = max(maximum, live)
        return maximum

    def maximum_live_minute(self) -> int:
        live = 0
        maximum = 0
        for (_position, delta) in self.connection.execute(
            "SELECT session_position, delta FROM minute_delta ORDER BY session_position"
        ):
            live += int(delta)
            maximum = max(maximum, live)
        if live != 0:
            raise FormalStreamingBridgeError("minute lifetime census did not close")
        return maximum

    def source_view_partition_records(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "view_id": view,
                "decision_count": self.partition_counts[view]["decision"],
                "scored_decision_count": self.partition_counts[view]["scored"],
                "named_preoutcome_refusal_count": self.partition_counts[view][
                    "refused"
                ],
                "terminal_key_sha256": self.partition_hashers[view].hexdigest(),
            }
            for view in runtime.SOURCE_VIEW_IDS
        )


def _checked_sort_and_block_key(
    role: str, row: dict[str, object]
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    security = row.get("security_id")
    if role == "formal_contract":
        return (0,), (role,)
    if role == "decision_joins":
        fold = runtime._safe_id(row.get("fold_id"), "decision stream fold")
        view = runtime._safe_id(row.get("source_view_id"), "decision stream view")
        position = runtime._positive_int(
            row.get("session_position"), "decision session position", allow_zero=True
        )
        if fold not in runtime.FORMAL_PRIMARY_FOLD_IDS or view not in runtime.SOURCE_VIEW_IDS:
            raise FormalStreamingBridgeError("decision stream geometry changed")
        security_id = runtime._safe_id(security, "decision stream security")
        return (
            runtime.FORMAL_PRIMARY_FOLD_IDS.index(fold),
            position,
            runtime.SOURCE_VIEW_IDS.index(view),
            security_id,
        ), (runtime.FORMAL_PRIMARY_FOLD_IDS.index(fold), position)
    if role == "contribution_seeds":
        intervals = row.get("active_intervals")
        if (
            type(intervals) is not list
            or not intervals
            or any(
                type(item) is not list
                or len(item) != 2
                or type(item[0]) is not int
                or type(item[1]) is not int
                or item[0] < 0
                or item[1] <= item[0]
                for item in intervals
            )
        ):
            raise FormalStreamingBridgeError("contribution active intervals changed")
        fold = runtime._safe_id(row.get("fold_id"), "contribution stream fold")
        view = runtime._safe_id(row.get("source_view_id"), "contribution stream view")
        if fold not in runtime.FORMAL_PRIMARY_FOLD_IDS or view not in runtime.SOURCE_VIEW_IDS:
            raise FormalStreamingBridgeError("contribution stream geometry changed")
        minute = row.get("minute_requirement_id")
        if minute is not None:
            runtime._safe_id(minute, "contribution minute requirement")
        first = min(item[0] for item in intervals)
        return (
            first,
            runtime.SOURCE_VIEW_IDS.index(view),
            runtime.FORMAL_PRIMARY_FOLD_IDS.index(fold),
            runtime._safe_id(security, "contribution stream security"),
            runtime._safe_id(row.get("seed_id"), "contribution stream seed"),
        ), (first,)
    if role == "economic_joins":
        fold = runtime._safe_id(row.get("fold_id"), "economic stream fold")
        view = runtime._safe_id(row.get("source_view_id"), "economic stream view")
        position = runtime._positive_int(
            row.get("session_position"), "economic session position", allow_zero=True
        )
        if fold not in runtime.FORMAL_PRIMARY_FOLD_IDS or view not in runtime.SOURCE_VIEW_IDS:
            raise FormalStreamingBridgeError("economic stream geometry changed")
        return (
            runtime.FORMAL_PRIMARY_FOLD_IDS.index(fold),
            position,
            runtime.SOURCE_VIEW_IDS.index(view),
        ), (role,)
    if role == "daily_requirements":
        session = runtime._iso_date(row.get("session"), "daily requirement session")
        security_id = runtime._safe_id(security, "daily stream security")
        requirement = runtime._safe_id(row.get("requirement_id"), "daily requirement id")
        return (session, security_id, requirement), (session,)
    if role == "minute_requirements":
        publication = runtime._utc_text(row.get("publication_at_utc"), "publication_at_utc")
        first = runtime._positive_int(
            row.get("first_active_session_position"),
            "minute first active session position",
            allow_zero=True,
        )
        last = runtime._positive_int(
            row.get("last_active_session_position"),
            "minute last active session position",
            allow_zero=True,
        )
        if last < first:
            raise FormalStreamingBridgeError("minute active-session interval changed")
        return (
            first,
            publication,
            runtime._safe_id(security, "minute stream security"),
            runtime._safe_id(row.get("requirement_id"), "minute requirement id"),
        ), (first,)
    if role == "terminal_dispositions":
        kind = runtime._safe_id(row.get("slot_kind"), "terminal slot kind")
        slot = runtime._safe_id(row.get("slot_id"), "terminal slot id")
        horizon = row.get("horizon")
        if horizon is not None:
            horizon = runtime._positive_int(horizon, "terminal horizon")
        return (kind, slot, -1 if horizon is None else horizon), (role,)
    raise FormalStreamingBridgeError("formal shard role changed")


def _derive_resource_census(
    archive: PhysicalFormalShardArchive,
    *,
    maximum_dynamic_subscription_count: int,
) -> tuple[
    runtime.FormalQcRuntimeResourceCensus,
    tuple[StreamedFormalUploadDescriptor, ...],
    int,
    tuple[dict[str, object], ...],
]:
    archive = require_physical_formal_shard_archive(archive)
    if (
        type(maximum_dynamic_subscription_count) is not int
        or not 1 <= maximum_dynamic_subscription_count <= MAX_DYNAMIC_SUBSCRIPTION_COUNT
    ):
        raise FormalStreamingBridgeError(
            "maximum dynamic subscription count escaped the reviewed 1..48 bound"
        )
    limits = dict(archive.capacity.limits)
    maximum_spool = limits["max_runtime_resource_spool_byte_count"]
    if archive.shard_count > runtime.ABSOLUTE_MAX_SHARDS:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RESOURCE_CENSUS_CAPACITY_EXCEEDED,
            "physical formal shard census exceeds the runtime absolute bound",
        )
    if any(
        descriptor.compressed_byte_count
        > runtime.ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES
        or descriptor.uncompressed_byte_count
        > runtime.ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES
        or descriptor.row_count > runtime.ABSOLUTE_MAX_SHARD_ROWS
        for descriptor in archive.descriptors
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RESOURCE_CENSUS_CAPACITY_EXCEEDED,
            "one physical formal shard exceeds a runtime absolute bound",
        )
    role_counts = {role: 0 for role in runtime.SHARD_ROLE_ORDER}
    prior_sort_key: dict[str, tuple[object, ...]] = {}
    prior_shard_last_block: dict[str, tuple[object, ...]] = {}
    upload: list[StreamedFormalUploadDescriptor] = []
    maximum_decoded_shard = 0
    bounded_header_bytes = 0
    terminal_header_bytes = 0
    with _DiskResourceGeometry(maximum_spool) as geometry:
        for physical in iter_physical_formal_shard_payloads(archive):
            descriptor = physical.descriptor
            upload.append(
                StreamedFormalUploadDescriptor(
                    role=descriptor.role,
                    object_store_key=descriptor.object_store_key,
                    content_sha256=descriptor.compressed_sha256,
                    content_md5=hashlib.md5(
                        physical.payload, usedforsecurity=False
                    ).hexdigest(),
                    byte_count=descriptor.compressed_byte_count,
                )
            )
            role_counts[descriptor.role] += descriptor.row_count
            maximum_decoded_shard = max(
                maximum_decoded_shard, descriptor.uncompressed_byte_count
            )
            if descriptor.role in {
                "formal_contract",
                "economic_joins",
                "terminal_dispositions",
            }:
                bounded_header_bytes += descriptor.uncompressed_byte_count
                if descriptor.role == "terminal_dispositions":
                    terminal_header_bytes += descriptor.uncompressed_byte_count
            raw_hasher = hashlib.sha256()
            raw_count = 0
            row_count = 0
            first_block: tuple[object, ...] | None = None
            last_block: tuple[object, ...] | None = None
            try:
                with gzip.GzipFile(
                    fileobj=_BytesViewReader(physical.payload), mode="rb"
                ) as stream:
                    while True:
                        line = stream.readline(descriptor.uncompressed_byte_count + 1)
                        if not line:
                            break
                        if not line.endswith(b"\n"):
                            raise FormalStreamingBridgeError(
                                "formal JSONL row lacks its canonical LF"
                            )
                        raw_count += len(line)
                        if raw_count > descriptor.uncompressed_byte_count:
                            raise FormalStreamingBridgeError(
                                "formal shard expanded beyond its descriptor"
                            )
                        raw_hasher.update(line)
                        row = _strict_object(line, "streamed formal JSONL row")
                        if row.get("schema") != runtime.SHARD_ROW_SCHEMAS[descriptor.role]:
                            raise FormalStreamingBridgeError(
                                "streamed formal row schema changed"
                            )
                        sort_key, block_key = _checked_sort_and_block_key(
                            descriptor.role, row
                        )
                        prior = prior_sort_key.get(descriptor.role)
                        if prior is not None and sort_key <= prior:
                            raise FormalStreamingBridgeError(
                                f"{descriptor.role} rows are duplicated or reordered"
                            )
                        prior_sort_key[descriptor.role] = sort_key
                        if first_block is None:
                            first_block = block_key
                        last_block = block_key
                        geometry.observe_row(descriptor.role, row, len(line))
                        row_count += 1
            except (OSError, EOFError) as exc:
                raise FormalStreamingBridgeError(
                    "streamed formal shard is not valid gzip"
                ) from exc
            if (
                row_count != descriptor.row_count
                or raw_count != descriptor.uncompressed_byte_count
                or raw_hasher.hexdigest() != descriptor.uncompressed_sha256
            ):
                raise FormalStreamingBridgeError(
                    "streamed formal shard row/byte/hash census changed"
                )
            if (
                first_block is not None
                and prior_shard_last_block.get(descriptor.role) == first_block
            ):
                raise FormalStreamingBridgeError(
                    f"one {descriptor.role} logical block was split across shards"
                )
            if last_block is not None:
                prior_shard_last_block[descriptor.role] = last_block
            # Drop the compressed shard before requesting the next physical
            # object, so this scanner never pins two payloads itself.
            del physical
            geometry.commit_and_bound()

        if (
            role_counts["formal_contract"] != 1
            or role_counts["contribution_seeds"] < 1
            or role_counts["decision_joins"] < 1
            or role_counts["economic_joins"] < 1
            or role_counts["daily_requirements"] < 1
        ):
            raise FormalStreamingBridgeError(
                "streamed compact input lacks a mandatory formal row class"
            )
        distinct_security_count = geometry.scalar("SELECT COUNT(*) FROM security")
        daily_batches = geometry.scalar(
            "SELECT COALESCE(SUM((security_count + ? - 1) / ?), 0) FROM "
            "(SELECT COUNT(*) AS security_count FROM daily_block GROUP BY block_id)",
            (
                maximum_dynamic_subscription_count,
                maximum_dynamic_subscription_count,
            ),
        ) * runtime.MARKET_OBSERVATION_COLLECTION_PASSES
        minute_batches = geometry.scalar(
            "SELECT COALESCE(SUM((security_count + ? - 1) / ?), 0) FROM "
            "(SELECT COUNT(*) AS security_count FROM minute_activation "
            "GROUP BY first_active, publication_day)",
            (
                maximum_dynamic_subscription_count,
                maximum_dynamic_subscription_count,
            ),
        ) * runtime.MARKET_OBSERVATION_COLLECTION_PASSES
        maximum_decision_rows = geometry.scalar(
            "SELECT COALESCE(MAX(row_count), 0) FROM decision_block"
        )
        maximum_decision_bytes = geometry.scalar(
            "SELECT COALESCE(MAX(byte_count), 0) FROM decision_block"
        )
        component_count = geometry.scalar("SELECT COUNT(*) FROM component")
        maximum_daily_rows = geometry.scalar(
            "SELECT COALESCE(MAX(row_count), 0) FROM daily_session"
        )
        maximum_daily_bytes = geometry.scalar(
            "SELECT COALESCE(MAX(byte_count), 0) FROM daily_session"
        )
        maximum_minute_rows = geometry.scalar(
            "SELECT COALESCE(MAX(row_count), 0) FROM minute_day"
        )
        maximum_minute_bytes = geometry.scalar(
            "SELECT COALESCE(MAX(byte_count), 0) FROM minute_day"
        )
        maximum_live_daily = geometry.maximum_live_daily()
        maximum_live_minute = geometry.maximum_live_minute()
        peak_spool_bytes = geometry.peak_bytes
        source_view_partitions = geometry.source_view_partition_records()

    projected_summary_payload = runtime.ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES
    projected_summary_chunks = runtime.ABSOLUTE_MAX_SUMMARY_CHUNKS
    estimated_peak_memory = (
        max(item.compressed_byte_count for item in archive.descriptors)
        + maximum_decoded_shard * runtime.STREAM_DECODE_WORKING_SET_MULTIPLIER
        + bounded_header_bytes * runtime.INPUT_EXPANSION_MEMORY_MULTIPLIER
        + maximum_decision_bytes * runtime.INPUT_EXPANSION_MEMORY_MULTIPLIER
        + (maximum_live_daily + maximum_live_minute)
        * runtime.OBSERVATION_MEMORY_BYTES_PER_REQUIREMENT
        + role_counts["minute_requirements"]
        * runtime.MINUTE_COMMITMENT_MEMORY_BYTES_PER_REQUIREMENT
        + component_count * runtime.COMPONENT_COMMITMENT_MEMORY_BYTES
        + maximum_dynamic_subscription_count
        * runtime.HISTORY_BATCH_MEMORY_BYTES_PER_SECURITY
        + role_counts["economic_joins"]
        * runtime.STREAM_EVALUATOR_BYTES_PER_ECONOMIC_JOIN
        + projected_summary_payload * 4
        + runtime.FORMAL_RESULT_WORKING_SET_MEMORY_BYTES
    )
    census = runtime.FormalQcRuntimeResourceCensus(
        shard_count=archive.shard_count,
        compressed_input_byte_count=archive.compressed_byte_count,
        maximum_compressed_object_byte_count=max(
            item.compressed_byte_count for item in archive.descriptors
        ),
        uncompressed_input_byte_count=sum(
            item.uncompressed_byte_count for item in archive.descriptors
        ),
        formal_contract_count=role_counts["formal_contract"],
        contribution_seed_count=role_counts["contribution_seeds"],
        decision_join_count=role_counts["decision_joins"],
        component_commitment_count=component_count,
        economic_join_count=role_counts["economic_joins"],
        daily_requirement_count=role_counts["daily_requirements"],
        minute_requirement_count=role_counts["minute_requirements"],
        terminal_disposition_count=role_counts["terminal_dispositions"],
        distinct_security_count=distinct_security_count,
        daily_history_batch_count=daily_batches,
        minute_history_batch_count=minute_batches,
        maximum_dynamic_subscription_count=maximum_dynamic_subscription_count,
        market_observation_collection_pass_count=(
            runtime.MARKET_OBSERVATION_COLLECTION_PASSES
        ),
        maximum_decoded_shard_byte_count=maximum_decoded_shard,
        maximum_decision_session_row_count=maximum_decision_rows,
        maximum_decision_session_byte_count=maximum_decision_bytes,
        maximum_daily_market_day_row_count=maximum_daily_rows,
        maximum_daily_market_day_byte_count=maximum_daily_bytes,
        maximum_minute_market_day_row_count=maximum_minute_rows,
        maximum_minute_market_day_byte_count=maximum_minute_bytes,
        maximum_live_daily_observation_count=maximum_live_daily,
        maximum_live_active_minute_observation_count=maximum_live_minute,
        bounded_header_uncompressed_byte_count=bounded_header_bytes,
        terminal_header_uncompressed_byte_count=terminal_header_bytes,
        estimated_peak_node_memory_byte_count=estimated_peak_memory,
        projected_summary_payload_byte_count=projected_summary_payload,
        projected_summary_chunk_count=projected_summary_chunks,
    )
    return census, tuple(upload), peak_spool_bytes, source_view_partitions


def _streamed_partition_binding(
    streamed: StreamedFormalInputCandidate,
    partition: Mapping[str, object],
) -> ArtifactBinding:
    payload = canonical_json_bytes(
        {
            "schema": PARTITION_BINDING_SCHEMA,
            "streamed_input_candidate_id": streamed.candidate_id,
            "streamed_input_candidate_sha256": streamed.candidate_sha256,
            "physical_formal_shard_archive_id": streamed.shards.archive_id,
            "physical_formal_shard_archive_sha256": streamed.shards.archive_sha256,
            "partition": dict(partition),
        }
    )
    digest = sha256_bytes(payload)
    return ArtifactBinding(
        artifact_id=f"arv2-streamed-formal-partition-{digest[:24]}",
        content_sha256=digest,
        artifact_sha256=sha256_bytes(
            (PARTITION_BINDING_SCHEMA + "\n").encode("ascii") + payload
        ),
        byte_count=len(payload),
    )


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedFormalRuntimeResourceCandidate:
    candidate_id: str
    candidate_sha256: str
    schema: str
    streamed_input: StreamedFormalInputCandidate
    resource_census: runtime.FormalQcRuntimeResourceCensus
    source_view_partitions: tuple[dict[str, object], ...]
    current_view_partition_set: ArtifactBinding
    censored_view_partition_set: ArtifactBinding
    upload_descriptors: tuple[StreamedFormalUploadDescriptor, ...]
    descriptor_projection_sha256: str
    resource_spool_peak_bytes: int
    runtime_capacity_candidate_bytes: bytes = dataclasses.field(repr=False)
    proposed_runtime_limits: tuple[tuple[str, int], ...]
    physical_shard_payloads_retained: bool
    external_action_authority: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "streamed_input_candidate_id": self.streamed_input.candidate_id,
            "streamed_input_candidate_sha256": self.streamed_input.candidate_sha256,
            "physical_formal_shard_archive_id": self.streamed_input.shards.archive_id,
            "physical_formal_shard_archive_sha256": self.streamed_input.shards.archive_sha256,
            "upstream_streaming_capacity_receipt_id": self.streamed_input.shards.capacity.receipt_id,
            "upstream_streaming_capacity_receipt_sha256": self.streamed_input.shards.capacity.receipt_sha256,
            "resource_census": self.resource_census.to_record(),
            "source_view_partitions": list(self.source_view_partitions),
            "current_view_partition_set": self.current_view_partition_set.to_record(),
            "censored_view_partition_set": self.censored_view_partition_set.to_record(),
            "upload_descriptors": [item.to_record() for item in self.upload_descriptors],
            "descriptor_projection_sha256": self.descriptor_projection_sha256,
            "resource_spool_peak_bytes": self.resource_spool_peak_bytes,
            "runtime_capacity_candidate_sha256": hashlib.sha256(
                self.runtime_capacity_candidate_bytes
            ).hexdigest(),
            "proposed_runtime_limits": dict(self.proposed_runtime_limits),
            "physical_shard_payloads_retained": self.physical_shard_payloads_retained,
            "external_action_authority": self.external_action_authority,
        }


_RESOURCE_CANDIDATES: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedFormalRuntimeResourceCandidate],
        bytes,
        tuple[object, ...],
    ],
] = {}
_RESOURCE_LOCK = threading.RLock()


def _forget_resource_candidate(identity: int, reference: object) -> None:
    with _RESOURCE_LOCK:
        current = _RESOURCE_CANDIDATES.get(identity)
        if current is not None and current[0] is reference:
            _RESOURCE_CANDIDATES.pop(identity, None)


def build_streamed_formal_runtime_resource_candidate(
    *,
    streamed_input: StreamedFormalInputCandidate,
    maximum_dynamic_subscription_count: int,
    proposed_runtime_limits: Mapping[str, int],
) -> StreamedFormalRuntimeResourceCandidate:
    streamed = require_streamed_formal_input_candidate(streamed_input)
    if type(proposed_runtime_limits) is not dict or set(proposed_runtime_limits) != set(
        runtime.CAPACITY_LIMIT_NAMES
    ):
        raise FormalStreamingBridgeError("runtime capacity limit inventory changed")
    try:
        census, upload, peak, partitions = _derive_resource_census(
            streamed.shards,
            maximum_dynamic_subscription_count=maximum_dynamic_subscription_count,
        )
        if partitions != streamed.source_view_partitions:
            raise FormalStreamingBridgeError(
                "physical decision shards disagree with the streamed source partitions"
            )
        capacity_candidate = runtime.render_formal_qc_capacity_review_candidate(
            census=census, limits=proposed_runtime_limits
        )
    except (FormalStreamingInputError, runtime.FormalQcRuntimeProjectionError) as exc:
        if isinstance(exc, FormalStreamingRunRefusal):
            raise
        raise FormalStreamingBridgeError(
            "physical formal shards could not produce an exact resource census"
        ) from exc
    current_partition = _streamed_partition_binding(streamed, partitions[0])
    censored_partition = _streamed_partition_binding(streamed, partitions[1])
    require_artifact_binding(current_partition)
    require_artifact_binding(censored_partition)
    if current_partition == censored_partition:
        raise FormalStreamingBridgeError("streamed source partitions collapsed")
    projection_sha = sha256_bytes(
        canonical_json_bytes([item.to_record() for item in upload])
    )
    record = {
        "schema": RESOURCE_CANDIDATE_SCHEMA,
        "streamed_input_candidate_id": streamed.candidate_id,
        "streamed_input_candidate_sha256": streamed.candidate_sha256,
        "physical_formal_shard_archive_id": streamed.shards.archive_id,
        "physical_formal_shard_archive_sha256": streamed.shards.archive_sha256,
        "upstream_streaming_capacity_receipt_id": streamed.shards.capacity.receipt_id,
        "upstream_streaming_capacity_receipt_sha256": streamed.shards.capacity.receipt_sha256,
        "resource_census": census.to_record(),
        "source_view_partitions": list(partitions),
        "current_view_partition_set": current_partition.to_record(),
        "censored_view_partition_set": censored_partition.to_record(),
        "upload_descriptors": [item.to_record() for item in upload],
        "descriptor_projection_sha256": projection_sha,
        "resource_spool_peak_bytes": peak,
        "runtime_capacity_candidate_sha256": hashlib.sha256(
            capacity_candidate
        ).hexdigest(),
        "proposed_runtime_limits": dict(
            (name, proposed_runtime_limits[name])
            for name in runtime.CAPACITY_LIMIT_NAMES
        ),
        "physical_shard_payloads_retained": False,
        "external_action_authority": False,
    }
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(StreamedFormalRuntimeResourceCandidate)
    fields = {
        "candidate_id": f"arv2-streamed-runtime-resource-{digest[:24]}",
        "candidate_sha256": digest,
        "schema": RESOURCE_CANDIDATE_SCHEMA,
        "streamed_input": streamed,
        "resource_census": census,
        "source_view_partitions": partitions,
        "current_view_partition_set": current_partition,
        "censored_view_partition_set": censored_partition,
        "upload_descriptors": upload,
        "descriptor_projection_sha256": projection_sha,
        "resource_spool_peak_bytes": peak,
        "runtime_capacity_candidate_bytes": capacity_candidate,
        "proposed_runtime_limits": tuple(
            (name, proposed_runtime_limits[name])
            for name in runtime.CAPACITY_LIMIT_NAMES
        ),
        "physical_shard_payloads_retained": False,
        "external_action_authority": False,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    topology = (
        id(value.streamed_input),
        id(value.resource_census),
        id(value.source_view_partitions),
        id(value.current_view_partition_set),
        id(value.censored_view_partition_set),
        id(value.upload_descriptors),
        tuple(id(item) for item in value.upload_descriptors),
        id(value.runtime_capacity_candidate_bytes),
        id(value.proposed_runtime_limits),
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_resource_candidate(key, ref)
    )
    with _RESOURCE_LOCK:
        _RESOURCE_CANDIDATES[identity] = (
            reference,
            canonical_json_bytes(record),
            topology,
        )
    return require_streamed_formal_runtime_resource_candidate(value)


def require_streamed_formal_runtime_resource_candidate(
    value: StreamedFormalRuntimeResourceCandidate,
) -> StreamedFormalRuntimeResourceCandidate:
    if type(value) is not StreamedFormalRuntimeResourceCandidate:
        raise FormalStreamingBridgeError("streamed resource candidate changed type")
    with _RESOURCE_LOCK:
        registered = _RESOURCE_CANDIDATES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalStreamingBridgeError(
            "streamed resource candidate is not builder-authenticated"
        )
    require_streamed_formal_input_candidate(value.streamed_input)
    require_artifact_binding(value.current_view_partition_set)
    require_artifact_binding(value.censored_view_partition_set)
    topology = (
        id(value.streamed_input),
        id(value.resource_census),
        id(value.source_view_partitions),
        id(value.current_view_partition_set),
        id(value.censored_view_partition_set),
        id(value.upload_descriptors),
        tuple(id(item) for item in value.upload_descriptors),
        id(value.runtime_capacity_candidate_bytes),
        id(value.proposed_runtime_limits),
    )
    record = value.to_record()
    digest = sha256_bytes(canonical_json_bytes(record))
    if (
        registered[1] != canonical_json_bytes(record)
        or registered[2] != topology
        or value.candidate_sha256 != digest
        or value.candidate_id != f"arv2-streamed-runtime-resource-{digest[:24]}"
        or value.source_view_partitions != value.streamed_input.source_view_partitions
        or value.current_view_partition_set
        != _streamed_partition_binding(value.streamed_input, value.source_view_partitions[0])
        or value.censored_view_partition_set
        != _streamed_partition_binding(value.streamed_input, value.source_view_partitions[1])
        or value.current_view_partition_set == value.censored_view_partition_set
        or tuple(item.to_record() for item in value.upload_descriptors)
        != tuple(
            StreamedFormalUploadDescriptor(
                role=descriptor.role,
                object_store_key=descriptor.object_store_key,
                content_sha256=descriptor.compressed_sha256,
                content_md5=item.content_md5,
                byte_count=descriptor.compressed_byte_count,
            ).to_record()
            for descriptor, item in zip(
                value.streamed_input.shards.descriptors,
                value.upload_descriptors,
                strict=True,
            )
        )
        or value.physical_shard_payloads_retained is not False
        or value.external_action_authority is not False
    ):
        raise FormalStreamingBridgeError(
            "streamed resource candidate changed after authentication"
        )
    return value


def _load_runtime_capacity(
    resource: StreamedFormalRuntimeResourceCandidate,
    reviewed_receipt_path: Path,
) -> runtime.FormalQcRuntimeCapacityBinding:
    payload, _fingerprint = _read_private_regular(
        reviewed_receipt_path,
        maximum_bytes=MAX_RUNTIME_CAPACITY_RECEIPT_BYTES,
        name="streamed runtime capacity review receipt",
    )
    try:
        value = runtime.load_formal_qc_runtime_capacity_binding(
            candidate_bytes=resource.runtime_capacity_candidate_bytes,
            reviewed_receipt_bytes=payload,
        )
    except runtime.FormalQcRuntimeProjectionError as exc:
        raise FormalStreamingBridgeError(
            "runtime capacity review receipt is not affirmative"
        ) from exc
    if value.candidate_sha256 != hashlib.sha256(
        resource.runtime_capacity_candidate_bytes
    ).hexdigest():
        raise FormalStreamingBridgeError(
            "runtime capacity receipt binds a different streamed resource census"
        )
    return value


def _bridge_review_candidate_record(
    resource: StreamedFormalRuntimeResourceCandidate,
    runtime_capacity: runtime.FormalQcRuntimeCapacityBinding,
) -> dict[str, object]:
    retained = dict(resource.streamed_input.scoring.observed_capacity).get(
        "retained_input_graph_bytes"
    )
    if type(retained) is not int or retained < 1:
        raise FormalStreamingBridgeError(
            "streamed scoring lacks measured whole-graph retained bytes"
        )
    return {
        "schema": BRIDGE_CAPACITY_SCHEMA,
        "status": "review_required_not_authorized",
        "receipt_id": None,
        "receipt_sha256": None,
        "streamed_resource_candidate_id": resource.candidate_id,
        "streamed_resource_candidate_sha256": resource.candidate_sha256,
        "streamed_input_candidate_id": resource.streamed_input.candidate_id,
        "streamed_input_candidate_sha256": resource.streamed_input.candidate_sha256,
        "physical_formal_shard_archive_id": resource.streamed_input.shards.archive_id,
        "physical_formal_shard_archive_sha256": resource.streamed_input.shards.archive_sha256,
        "upstream_streaming_capacity_receipt_id": resource.streamed_input.shards.capacity.receipt_id,
        "upstream_streaming_capacity_receipt_sha256": resource.streamed_input.shards.capacity.receipt_sha256,
        "retained_input_graph_bytes": retained,
        "resource_census_sha256": sha256_bytes(
            canonical_json_bytes(resource.resource_census.to_record())
        ),
        "descriptor_projection_sha256": resource.descriptor_projection_sha256,
        "runtime_capacity_candidate_sha256": runtime_capacity.candidate_sha256,
        "runtime_capacity_receipt_id": runtime_capacity.receipt_id,
        "runtime_capacity_receipt_sha256": runtime_capacity.receipt_sha256,
        "resource_spool_peak_bytes": resource.resource_spool_peak_bytes,
        "whole_graph_retained_byte_measurement_verified": False,
        "disk_backed_resource_census_verified": False,
        "sequential_reopen_rehash_upload_verified": False,
        "one_fold_streaming_projection_verified": False,
        "production_truth_materialization_avoided": False,
        "representative_full_census_verified": False,
        "runtime_capacity_reviewed": False,
        "outcome_or_qc_action_authorized": False,
    }


def render_streamed_formal_runtime_bridge_review_candidate(
    *,
    resource_candidate: StreamedFormalRuntimeResourceCandidate,
    runtime_capacity_reviewed_receipt_path: Path,
) -> bytes:
    resource = require_streamed_formal_runtime_resource_candidate(resource_candidate)
    capacity = _load_runtime_capacity(resource, runtime_capacity_reviewed_receipt_path)
    return canonical_json_bytes(_bridge_review_candidate_record(resource, capacity))


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedFormalRuntimeCapacityBinding:
    receipt_id: str
    receipt_sha256: str
    resource_candidate: StreamedFormalRuntimeResourceCandidate
    runtime_capacity: runtime.FormalQcRuntimeCapacityBinding
    review_receipt_bytes: bytes = dataclasses.field(repr=False)
    whole_graph_retained_byte_measurement_verified: bool
    disk_backed_resource_census_verified: bool
    sequential_reopen_rehash_upload_verified: bool
    one_fold_streaming_projection_verified: bool
    production_truth_materialization_avoided: bool
    representative_full_census_verified: bool
    runtime_capacity_reviewed: bool
    outcome_or_qc_action_authorized: bool

    @property
    def submission_authority(self) -> bool:
        return False

    @property
    def qc_launch_available(self) -> bool:
        return False

    def artifact_binding(self) -> ArtifactBinding:
        return ArtifactBinding(
            artifact_id=self.receipt_id,
            content_sha256=sha256_bytes(self.review_receipt_bytes),
            artifact_sha256=sha256_bytes(
                b"arv2-streamed-runtime-capacity-artifact-v1\0"
                + self.review_receipt_bytes
            ),
            byte_count=len(self.review_receipt_bytes),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
            "resource_candidate_id": self.resource_candidate.candidate_id,
            "resource_candidate_sha256": self.resource_candidate.candidate_sha256,
            "runtime_capacity": self.runtime_capacity.to_record(),
            "whole_graph_retained_byte_measurement_verified": self.whole_graph_retained_byte_measurement_verified,
            "disk_backed_resource_census_verified": self.disk_backed_resource_census_verified,
            "sequential_reopen_rehash_upload_verified": self.sequential_reopen_rehash_upload_verified,
            "one_fold_streaming_projection_verified": self.one_fold_streaming_projection_verified,
            "production_truth_materialization_avoided": self.production_truth_materialization_avoided,
            "representative_full_census_verified": self.representative_full_census_verified,
            "runtime_capacity_reviewed": self.runtime_capacity_reviewed,
            "outcome_or_qc_action_authorized": self.outcome_or_qc_action_authorized,
        }


_BRIDGE_CAPACITY_BINDINGS: dict[
    int,
    tuple[object, ...],
] = {}
_BRIDGE_CAPACITY_LOCK = threading.RLock()


def _make_bridge_capacity_authority_vault():
    """Keep loader authority outside the module-addressable inspection mirror."""

    private_bindings: tuple[tuple[int, tuple[object, ...]], ...] = ()
    register_provenance: tuple[tuple[object, ...], ...] = ()
    missing_closure_value = object()
    function_type = type(_make_bridge_capacity_authority_vault)
    authority_module = sys.modules.get(__name__)

    def private_entry(identity: int) -> tuple[object, ...] | None:
        return next(
            (entry for key, entry in private_bindings if key == identity),
            None,
        )

    def caller_is_exact() -> bool:
        if not register_provenance:
            return False
        frame = sys._getframe(2)
        for position, provenance in enumerate(register_provenance):
            (
                expected_function,
                expected_code,
                expected_name,
                expected_global_bindings,
                expected_closure,
            ) = provenance
            if (
                frame is None
                or frame.f_code is not expected_code
                or frame.f_code.co_name != expected_name
                or frame.f_globals.get("__name__") != __name__
                or authority_module is None
                or sys.modules.get(__name__) is not authority_module
                or vars(authority_module) is not frame.f_globals
                or expected_function.__code__ is not expected_code
                or expected_function.__globals__ is not frame.f_globals
                or expected_function.__name__ != expected_name
                or any(
                    expected_function.__globals__.get(
                        name, missing_closure_value
                    ) is not expected
                    or frame.f_globals.get(name, missing_closure_value)
                    is not expected
                    for name, expected in expected_global_bindings
                )
                or tuple(expected_function.__code__.co_freevars)
                != tuple(item[0] for item in expected_closure)
                or len(expected_function.__closure__ or ())
                != len(expected_closure)
                or any(
                    cell.cell_contents is not expected
                    for cell, (_name, expected) in zip(
                        expected_function.__closure__ or (),
                        expected_closure,
                        strict=True,
                    )
                )
                or any(
                    frame.f_locals.get(name, missing_closure_value)
                    is not expected
                    for name, expected in expected_closure
                )
                or (
                    position == len(register_provenance) - 1
                    and frame.f_globals.get(expected_name)
                    is not expected_function
                )
            ):
                return False
            frame = frame.f_back
        return True

    def forget(identity: int, reference: object) -> None:
        nonlocal private_bindings

        with _BRIDGE_CAPACITY_LOCK:
            current = private_entry(identity)
            if current is not None and current[0] is reference:
                private_bindings = tuple(
                    item for item in private_bindings
                    if item[0] != identity
                )
            public = _BRIDGE_CAPACITY_BINDINGS.get(identity)
            if public is current:
                _BRIDGE_CAPACITY_BINDINGS.pop(identity, None)

    def reset_after_fork() -> None:
        nonlocal private_bindings
        global _BRIDGE_CAPACITY_LOCK
        global _BRIDGE_CAPACITY_BINDINGS

        _BRIDGE_CAPACITY_LOCK = threading.RLock()
        _BRIDGE_CAPACITY_BINDINGS = {}
        private_bindings = ()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def register(
        value: StreamedFormalRuntimeCapacityBinding,
        *,
        resource_candidate: StreamedFormalRuntimeResourceCandidate,
        runtime_capacity: runtime.FormalQcRuntimeCapacityBinding,
        review_receipt_bytes: bytes,
        review_candidate_bytes: bytes,
        topology: tuple[object, ...],
    ) -> StreamedFormalRuntimeCapacityBinding:
        nonlocal private_bindings

        if os.getpid() != authority_pid or not caller_is_exact():
            raise FormalStreamingBridgeError(
                "streamed runtime capacity register caller changed"
            )
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        entry = (
            reference,
            resource_candidate,
            runtime_capacity,
            review_receipt_bytes,
            review_candidate_bytes,
            topology,
            os.getpid(),
        )
        with _BRIDGE_CAPACITY_LOCK:
            if (
                private_entry(identity) is not None
                or identity in _BRIDGE_CAPACITY_BINDINGS
            ):
                raise FormalStreamingBridgeError(
                    "streamed runtime capacity authority identity was reused"
                )
            private_bindings = (*private_bindings, (identity, entry))
            # This remains visible for cleanup/accounting tests, but it is only
            # an inspection mirror.  Authentication also requires identity
            # with the independently held lexical entry.
            _BRIDGE_CAPACITY_BINDINGS[identity] = entry
        return value

    def current(
        value: StreamedFormalRuntimeCapacityBinding,
    ) -> tuple[object, ...] | None:
        nonlocal private_bindings

        identity = id(value)
        with _BRIDGE_CAPACITY_LOCK:
            private = private_entry(identity)
            public = _BRIDGE_CAPACITY_BINDINGS.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[6] != os.getpid()
            ):
                private_bindings = tuple(
                    item for item in private_bindings
                    if item[0] != identity
                )
                _BRIDGE_CAPACITY_BINDINGS.pop(identity, None)
                return None
            return private

    def seal_register_provenance(
        value: tuple[object, ...],
    ) -> None:
        nonlocal register_provenance

        if (
            register_provenance
            or type(value) is not tuple
            or len(value) != 2
            or any(
                type(item) is not function_type
                or authority_module is None
                or item.__globals__ is not vars(authority_module)
                or item.__module__ != __name__
                for item in value
            )
        ):
            raise FormalStreamingBridgeError(
                "streamed runtime capacity register provenance changed"
            )
        try:
            register_provenance = tuple(
                (
                    item,
                    item.__code__,
                    item.__name__,
                    tuple(
                        (
                            name,
                            item.__globals__.get(
                                name, missing_closure_value
                            ),
                        )
                        for name in item.__code__.co_names
                    ),
                    tuple(
                        (name, cell.cell_contents)
                        for name, cell in zip(
                            item.__code__.co_freevars,
                            item.__closure__ or (),
                            strict=True,
                        )
                    ),
                )
                for item in value
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise FormalStreamingBridgeError(
                "streamed runtime capacity register provenance changed"
            ) from exc

    authority_pid = os.getpid()
    return register, current, seal_register_provenance


(
    _bridge_capacity_authority_register,
    _bridge_capacity_authority_current,
    _seal_bridge_capacity_authority_provenance,
) = _make_bridge_capacity_authority_vault()


def _authenticate_streamed_bridge_capacity_review(
    *,
    resource_candidate: StreamedFormalRuntimeResourceCandidate,
    runtime_capacity: runtime.FormalQcRuntimeCapacityBinding,
    review_receipt_bytes: bytes,
) -> tuple[dict[str, object], bytes]:
    """Reproduce the reviewed candidate and authenticate the exact receipt."""

    candidate = _bridge_review_candidate_record(
        resource_candidate, runtime_capacity
    )
    raw = _strict_object(
        review_receipt_bytes, "streamed formal runtime bridge review receipt"
    )
    if set(raw) != set(candidate):
        raise FormalStreamingBridgeError("streamed bridge review fields changed")
    immutable = set(candidate) - {
        "status",
        "receipt_id",
        "receipt_sha256",
        "whole_graph_retained_byte_measurement_verified",
        "disk_backed_resource_census_verified",
        "sequential_reopen_rehash_upload_verified",
        "one_fold_streaming_projection_verified",
        "production_truth_materialization_avoided",
        "representative_full_census_verified",
        "runtime_capacity_reviewed",
    }
    semantic = dict(raw)
    supplied_id = semantic["receipt_id"]
    supplied_sha = semantic["receipt_sha256"]
    semantic["receipt_id"] = None
    semantic["receipt_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    flags = (
        "whole_graph_retained_byte_measurement_verified",
        "disk_backed_resource_census_verified",
        "sequential_reopen_rehash_upload_verified",
        "one_fold_streaming_projection_verified",
        "production_truth_materialization_avoided",
        "representative_full_census_verified",
        "runtime_capacity_reviewed",
    )
    if (
        any(raw[name] != candidate[name] for name in immutable)
        or raw["status"]
        != "independently_reviewed_streamed_runtime_bridge_capacity_affirmative"
        or any(raw[name] is not True for name in flags)
        or raw["outcome_or_qc_action_authorized"] is not False
        or supplied_id != f"arv2-streamed-runtime-capacity-{digest[:24]}"
        or supplied_sha != digest
    ):
        raise FormalStreamingBridgeError(
            "streamed bridge capacity receipt is not an independent affirmative review"
        )
    return raw, canonical_json_bytes(candidate)


def _load_streamed_formal_runtime_capacity_binding_impl(
    *,
    resource_candidate: StreamedFormalRuntimeResourceCandidate,
    runtime_capacity_reviewed_receipt_path: Path,
    streamed_bridge_reviewed_receipt_path: Path,
    _authority_register: object,
) -> StreamedFormalRuntimeCapacityBinding:
    resource = require_streamed_formal_runtime_resource_candidate(resource_candidate)
    capacity = _load_runtime_capacity(resource, runtime_capacity_reviewed_receipt_path)
    payload, _fingerprint = _read_private_regular(
        streamed_bridge_reviewed_receipt_path,
        maximum_bytes=MAX_BRIDGE_CAPACITY_RECEIPT_BYTES,
        name="streamed formal runtime bridge review receipt",
    )
    raw, candidate_bytes = _authenticate_streamed_bridge_capacity_review(
        resource_candidate=resource,
        runtime_capacity=capacity,
        review_receipt_bytes=payload,
    )
    supplied_id = raw["receipt_id"]
    digest = raw["receipt_sha256"]
    flags = (
        "whole_graph_retained_byte_measurement_verified",
        "disk_backed_resource_census_verified",
        "sequential_reopen_rehash_upload_verified",
        "one_fold_streaming_projection_verified",
        "production_truth_materialization_avoided",
        "representative_full_census_verified",
        "runtime_capacity_reviewed",
    )
    value = object.__new__(StreamedFormalRuntimeCapacityBinding)
    values = {
        "receipt_id": str(supplied_id),
        "receipt_sha256": str(digest),
        "resource_candidate": resource,
        "runtime_capacity": capacity,
        "review_receipt_bytes": payload,
        **{name: True for name in flags},
        "outcome_or_qc_action_authorized": False,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    topology = (
        id(value.resource_candidate),
        id(value.runtime_capacity),
        id(value.review_receipt_bytes),
    )
    return _authority_register(
        value,
        resource_candidate=resource,
        runtime_capacity=capacity,
        review_receipt_bytes=payload,
        review_candidate_bytes=candidate_bytes,
        topology=topology,
    )


def _require_streamed_formal_runtime_capacity_binding_impl(
    value: StreamedFormalRuntimeCapacityBinding,
    *,
    _authority_current: object,
) -> StreamedFormalRuntimeCapacityBinding:
    if type(value) is not StreamedFormalRuntimeCapacityBinding:
        raise FormalStreamingBridgeError("streamed runtime capacity changed type")
    registered = _authority_current(value)
    if registered is None:
        raise FormalStreamingBridgeError(
            "streamed runtime capacity is not loader-authenticated"
        )
    resource = require_streamed_formal_runtime_resource_candidate(
        value.resource_candidate
    )
    capacity = runtime.require_formal_qc_runtime_capacity_binding(
        value.runtime_capacity
    )
    raw, candidate_bytes = _authenticate_streamed_bridge_capacity_review(
        resource_candidate=resource,
        runtime_capacity=capacity,
        review_receipt_bytes=value.review_receipt_bytes,
    )
    topology = (
        id(value.resource_candidate),
        id(value.runtime_capacity),
        id(value.review_receipt_bytes),
    )
    flags = (
        value.whole_graph_retained_byte_measurement_verified,
        value.disk_backed_resource_census_verified,
        value.sequential_reopen_rehash_upload_verified,
        value.one_fold_streaming_projection_verified,
        value.production_truth_materialization_avoided,
        value.representative_full_census_verified,
        value.runtime_capacity_reviewed,
    )
    if (
        registered[1] is not resource
        or registered[2] is not capacity
        or registered[3] != value.review_receipt_bytes
        or registered[4] != candidate_bytes
        or registered[5] != topology
        or value.receipt_id != raw.get("receipt_id")
        or value.receipt_sha256 != raw.get("receipt_sha256")
        or any(type(flag) is not bool or flag is not True for flag in flags)
        or value.outcome_or_qc_action_authorized is not False
        or value.submission_authority is not False
        or value.qc_launch_available is not False
    ):
        raise FormalStreamingBridgeError(
            "streamed runtime capacity changed after authentication"
        )
    return value


def _production_input_binding(
    candidate: StreamedFormalInputCandidate,
) -> ArtifactBinding:
    payload = canonical_json_bytes(
        {
            "schema": PRODUCTION_INPUT_SCHEMA,
            "streamed_input_candidate_id": candidate.candidate_id,
            "streamed_input_candidate_sha256": candidate.candidate_sha256,
            "streamed_scoring_id": candidate.scoring.artifact_id,
            "streamed_scoring_sha256": candidate.scoring.artifact_sha256,
            "physical_formal_shard_archive_id": candidate.shards.archive_id,
            "physical_formal_shard_archive_sha256": candidate.shards.archive_sha256,
        }
    )
    digest = sha256_bytes(payload)
    return ArtifactBinding(
        artifact_id=f"arv2-streamed-formal-production-input-{digest[:24]}",
        content_sha256=digest,
        artifact_sha256=sha256_bytes(
            b"arv2-streamed-formal-production-input-artifact-v1\0" + payload
        ),
        byte_count=len(payload),
    )


def _preopen_binding(candidate: StreamedFormalInputCandidate) -> ArtifactBinding:
    record = acquisition_receipt_artifact_binding_record(
        candidate.shards.capacity.preopen_acquisition_receipt
    )
    return ArtifactBinding(**record)


def _streamed_formal_input_lineage_record(
    *,
    candidate: StreamedFormalInputCandidate,
    production_input: ArtifactBinding,
    preopen: ArtifactBinding,
    formal_evaluator_source_sha256: str,
) -> dict[str, object]:
    contract = streamed_formal_contract_record(candidate)
    return {
        "schema": STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA,
        "contract_variant": STREAMED_FORMAL_CONTRACT_VARIANT,
        "formal_contract_sha256": sha256_bytes(canonical_json_bytes(contract)),
        "streamed_input_candidate_id": candidate.candidate_id,
        "streamed_input_candidate_sha256": candidate.candidate_sha256,
        "streamed_scoring_id": candidate.scoring.artifact_id,
        "streamed_scoring_sha256": candidate.scoring.artifact_sha256,
        "physical_formal_shard_archive_id": candidate.shards.archive_id,
        "physical_formal_shard_archive_sha256": candidate.shards.archive_sha256,
        "physical_preopen_archive_id": candidate.scoring.archive_id,
        "physical_preopen_archive_sha256": candidate.scoring.archive_sha256,
        "preopen_acquisition_id": (
            candidate.shards.capacity.preopen_acquisition_receipt.artifact_id
        ),
        "preopen_acquisition_sha256": (
            candidate.shards.capacity.preopen_acquisition_receipt.artifact_sha256
        ),
        "production_evidence_receipt_id": (
            candidate.scoring.production_evidence_receipt_id
        ),
        "production_evidence_receipt_sha256": (
            candidate.scoring.production_evidence_receipt_sha256
        ),
        "accepted_risk_sha256": sha256_bytes(
            canonical_json_bytes(candidate.accepted_risk.to_record())
        ),
        "formal_power_sha256": sha256_bytes(
            canonical_json_bytes(candidate.formal_power.to_record())
        ),
        "power_floor_sha256": sha256_bytes(
            canonical_json_bytes(candidate.power_floor.to_record())
        ),
        "economic_execution_binding_id": candidate.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            candidate.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            candidate.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            candidate.economic_execution.definition_sha256
        ),
        "economic_execution_definition_payload_sha256": (
            candidate.economic_execution.definition_payload_sha256
        ),
        "economic_execution_binding_record_sha256": sha256_bytes(
            canonical_json_bytes(contract["economic_execution_binding"])
        ),
        "economic_execution_definition_record_sha256": sha256_bytes(
            canonical_json_bytes(contract["economic_execution_definition"])
        ),
        "economic_h20_terminal_liquidation_session": (
            formal_economic_terminal_liquidation_session(
                candidate.economic_execution
            )
        ),
        "formal_report_contract_id": candidate.report_contract.contract_id,
        "formal_report_contract_sha256": candidate.report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": (
            candidate.report_contract.artifact_sha256
        ),
        "formal_report_contract_economic_execution_definition_sha256": (
            candidate.report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            candidate.report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            candidate.report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            candidate.report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": (
            candidate.report_contract.report_family_count
        ),
        "formal_report_contract_secondary_hypothesis_count": (
            candidate.report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            candidate.report_contract.strategy_trial_count
        ),
        "formal_report_contract_record_sha256": sha256_bytes(
            canonical_json_bytes(contract["formal_report_contract"])
        ),
        "scoring_result_bindings_sha256": sha256_bytes(
            canonical_json_bytes(contract["scoring_result_bindings"])
        ),
        "paired_bootstrap_authority_sha256": sha256_bytes(
            canonical_json_bytes(contract["paired_bootstrap_authority"])
        ),
        "fold_horizon_axes_sha256": sha256_bytes(
            canonical_json_bytes(contract["fold_horizon_axes"])
        ),
        "terminal_package_id": candidate.terminal_package.package_id,
        "terminal_package_sha256": candidate.terminal_package.package_sha256,
        "terminal_census_sha256": sha256_bytes(
            canonical_json_bytes(contract["terminal_census"])
        ),
        "source_view_partitions_sha256": sha256_bytes(
            canonical_json_bytes(contract["source_view_partitions"])
        ),
        "production_input_package": production_input.to_record(),
        "preopen_control_stage_output": preopen.to_record(),
        "formal_evaluator_source_sha256": formal_evaluator_source_sha256,
        "benchmark_security_id": candidate.benchmark_security_id,
        "calculation_as_of_date": candidate.calculation_as_of_date.isoformat(),
    }


def _upstream_capacity_record(
    capacity: StreamedFormalRuntimeCapacityBinding,
) -> dict[str, object]:
    return {
        "schema": runtime.UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA,
        "status": "reviewed_upstream_capacity_affirmative",
        "artifact_binding": capacity.artifact_binding().to_record(),
        "distinct_from_runtime_capacity": True,
        "one_fold_streaming_projection_verified": True,
        "production_truth_materialization_capacity_verified": True,
        "representative_full_census_verified": True,
        "launch_authorized": True,
    }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedFormalRuntimeBridge:
    bridge_id: str
    bridge_sha256: str
    schema: str
    resource_candidate: StreamedFormalRuntimeResourceCandidate
    capacity: StreamedFormalRuntimeCapacityBinding
    terminal_build: FormalTerminalDispositionBuild
    economic_execution: FormalEconomicExecutionBinding
    report_contract: FormalReportContract
    production_input_package: ArtifactBinding
    preopen_control_stage_output: ArtifactBinding
    current_view_partition_set: ArtifactBinding
    censored_view_partition_set: ArtifactBinding
    input_manifest_payload: bytes = dataclasses.field(repr=False)
    input_manifest: runtime.QcObjectPayloadBinding
    runtime_projection: runtime.FormalQcRuntimeProjection
    formal_run_candidate: FormalRunCandidate
    upload_descriptors: tuple[StreamedFormalUploadDescriptor, ...]
    upload_projection_sha256: str
    upload_entry_count: int
    upload_total_byte_count: int
    physical_shard_payloads_retained: bool
    sequential_reopen_rehash_required: bool
    legacy_tuple_upload_compatible: bool
    discovery_gate_affirmative: bool
    owner_signature_gate_affirmative: bool
    qc_launch_available: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "resource_candidate_id": self.resource_candidate.candidate_id,
            "resource_candidate_sha256": self.resource_candidate.candidate_sha256,
            "capacity_receipt_id": self.capacity.receipt_id,
            "capacity_receipt_sha256": self.capacity.receipt_sha256,
            "terminal_build_id": self.terminal_build.build_id,
            "terminal_build_sha256": self.terminal_build.build_sha256,
            "lifecycle_inventory_sha256": (
                self.terminal_build.lifecycle_inventory_sha256
            ),
            "economic_execution_binding_id": self.economic_execution.binding_id,
            "economic_execution_binding_sha256": (
                self.economic_execution.binding_sha256
            ),
            "economic_execution_definition_id": (
                self.economic_execution.definition_id
            ),
            "economic_execution_definition_sha256": (
                self.economic_execution.definition_sha256
            ),
            "economic_execution_definition_payload_sha256": (
                self.economic_execution.definition_payload_sha256
            ),
            "formal_report_contract_id": self.report_contract.contract_id,
            "formal_report_contract_sha256": self.report_contract.contract_sha256,
            "formal_report_contract_artifact_sha256": (
                self.report_contract.artifact_sha256
            ),
            "formal_report_contract_stock_bootstrap_seed_sha256": (
                self.report_contract.stock_bootstrap_seed_sha256
            ),
            "formal_report_contract_economic_execution_definition_sha256": (
                self.report_contract.economic_execution_definition_sha256
            ),
            "formal_report_contract_secondary_hypothesis_registry_sha256": (
                self.report_contract.secondary_hypothesis_registry_sha256
            ),
            "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
                self.report_contract.deflated_sharpe_trial_registry_sha256
            ),
            "formal_report_contract_report_family_count": (
                self.report_contract.report_family_count
            ),
            "formal_report_contract_secondary_hypothesis_count": (
                self.report_contract.secondary_hypothesis_count
            ),
            "formal_report_contract_strategy_trial_count": (
                self.report_contract.strategy_trial_count
            ),
            "streamed_input_candidate_id": self.resource_candidate.streamed_input.candidate_id,
            "streamed_input_candidate_sha256": self.resource_candidate.streamed_input.candidate_sha256,
            "physical_formal_shard_archive_id": self.resource_candidate.streamed_input.shards.archive_id,
            "physical_formal_shard_archive_sha256": self.resource_candidate.streamed_input.shards.archive_sha256,
            "production_input_package": self.production_input_package.to_record(),
            "preopen_control_stage_output": self.preopen_control_stage_output.to_record(),
            "current_view_partition_set": self.current_view_partition_set.to_record(),
            "censored_view_partition_set": self.censored_view_partition_set.to_record(),
            "resource_census": self.resource_candidate.resource_census.to_record(),
            "input_manifest": self.input_manifest.to_record(),
            "input_manifest_sha256": hashlib.sha256(
                self.input_manifest_payload
            ).hexdigest(),
            "runtime_projection_id": self.runtime_projection.projection_id,
            "runtime_projection_sha256": self.runtime_projection.projection_sha256,
            "formal_run_candidate_id": self.formal_run_candidate.candidate_id,
            "formal_run_candidate_sha256": self.formal_run_candidate.candidate_sha256,
            "upload_descriptors": [item.to_record() for item in self.upload_descriptors],
            "upload_projection_sha256": self.upload_projection_sha256,
            "upload_entry_count": self.upload_entry_count,
            "upload_total_byte_count": self.upload_total_byte_count,
            "physical_shard_payloads_retained": self.physical_shard_payloads_retained,
            "sequential_reopen_rehash_required": self.sequential_reopen_rehash_required,
            "legacy_tuple_upload_compatible": self.legacy_tuple_upload_compatible,
            "discovery_gate_affirmative": self.discovery_gate_affirmative,
            "owner_signature_gate_affirmative": self.owner_signature_gate_affirmative,
            "qc_launch_available": self.qc_launch_available,
        }


_BRIDGES: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedFormalRuntimeBridge],
        bytes,
        tuple[object, ...],
    ],
] = {}
_BRIDGE_LOCK = threading.RLock()


def _forget_bridge(identity: int, reference: object) -> None:
    with _BRIDGE_LOCK:
        current = _BRIDGES.get(identity)
        if current is not None and current[0] is reference:
            _BRIDGES.pop(identity, None)


def build_streamed_formal_runtime_bridge(
    *,
    resource_candidate: StreamedFormalRuntimeResourceCandidate,
    capacity: StreamedFormalRuntimeCapacityBinding,
    formal_evaluator_source: bytes,
    cloud_evaluator_source: bytes,
) -> StreamedFormalRuntimeBridge:
    resource = require_streamed_formal_runtime_resource_candidate(resource_candidate)
    reviewed = require_streamed_formal_runtime_capacity_binding(capacity)
    try:
        economic_execution = require_formal_economic_execution_binding(
            resource.streamed_input.economic_execution
        )
    except FormalEconomicExecutionDefinitionError as exc:
        raise FormalStreamingBridgeError(
            "streamed economic execution binding did not authenticate"
        ) from exc
    try:
        report_contract = require_formal_report_contract(
            resource.streamed_input.report_contract,
            expected_economic_execution_definition_sha256=(
                economic_execution.definition_sha256
            ),
        )
    except FormalReportContractError as exc:
        raise FormalStreamingBridgeError(
            "streamed formal report contract did not authenticate"
        ) from exc
    terminal_build = resource.streamed_input.terminal_build
    if terminal_build is None:
        raise FormalStreamingBridgeError(
            "streamed runtime bridge requires a lifecycle-derived terminal build"
        )
    try:
        terminal_build = require_formal_terminal_disposition_build(terminal_build)
    except FormalTerminalDispositionBuildError as exc:
        raise FormalStreamingBridgeError(
            "lifecycle-derived terminal build did not authenticate"
        ) from exc
    if (
        terminal_build.terminal_package
        is not resource.streamed_input.terminal_package
        or terminal_build.terminal_census
        is not resource.streamed_input.terminal_package.terminal_census
    ):
        raise FormalStreamingBridgeError(
            "streamed terminal package escaped its lifecycle-derived build"
        )
    if reviewed.resource_candidate is not resource:
        raise FormalStreamingBridgeError(
            "streamed runtime capacity binds a different resource candidate"
        )
    try:
        runtime._census_within_capacity(
            resource.resource_census, reviewed.runtime_capacity
        )
        evaluator = runtime.formal_cloud_evaluator_binding(
            formal_evaluator_source=formal_evaluator_source,
            cloud_evaluator_source=cloud_evaluator_source,
        )
        formal_evaluator_source_sha256 = hashlib.sha256(
            formal_evaluator_source
        ).hexdigest()
        production_input = _production_input_binding(resource.streamed_input)
        preopen = _preopen_binding(resource.streamed_input)
        manifest_payload = runtime._build_formal_qc_input_manifest_from_descriptors(
            production_input_package=production_input,
            preopen_control_stage_output=preopen,
            runtime_start=_RUNTIME_START,
            runtime_end=_RUNTIME_END,
            calculation_as_of_date=resource.streamed_input.calculation_as_of_date,
            benchmark_security_id=resource.streamed_input.benchmark_security_id,
            shard_descriptors=tuple(
                item.to_record() for item in resource.streamed_input.shards.descriptors
            ),
            resource_census=resource.resource_census,
            capacity=reviewed.runtime_capacity,
            cloud_evaluator=evaluator,
            upstream_scoring_materialization_capacity=_upstream_capacity_record(reviewed),
        )
        manifest = _strict_object(
            manifest_payload, "base streamed formal input manifest"
        )
        manifest["streamed_formal_input_lineage"] = (
            _streamed_formal_input_lineage_record(
                candidate=resource.streamed_input,
                production_input=production_input,
                preopen=preopen,
                formal_evaluator_source_sha256=formal_evaluator_source_sha256,
            )
        )
        manifest_payload = canonical_json_bytes(manifest)
        manifest_digest = hashlib.sha256(manifest_payload).hexdigest()
        input_manifest = runtime.build_qc_object_payload_binding(
            role="input_manifest",
            schema=runtime.INPUT_MANIFEST_SCHEMA,
            object_store_key=runtime.FORMAL_INPUT_PREFIX + manifest_digest + ".json",
            payload=manifest_payload,
        )
        projection = runtime.build_formal_qc_runtime_projection(
            input_manifest=input_manifest,
            formal_evaluator_source=formal_evaluator_source,
            cloud_evaluator_source=cloud_evaluator_source,
        )
        formal_candidate = build_formal_run_candidate(
            code_projection=runtime.formal_code_projection_binding(projection),
            production_input_package=production_input,
            current_view_partition_set=resource.current_view_partition_set,
            censored_view_partition_set=resource.censored_view_partition_set,
            accepted_risk=resource.streamed_input.accepted_risk,
            power_floor=resource.streamed_input.power_floor,
            terminal_census=resource.streamed_input.terminal_package.terminal_census,
        )
    except (runtime.FormalQcRuntimeProjectionError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalStreamingBridgeError):
            raise
        raise FormalStreamingBridgeError(
            "streamed formal manifest or runtime projection could not be built"
        ) from exc
    manifest_upload = StreamedFormalUploadDescriptor(
        role="input_manifest",
        object_store_key=input_manifest.object_store_key,
        content_sha256=input_manifest.content_sha256,
        content_md5=hashlib.md5(manifest_payload, usedforsecurity=False).hexdigest(),
        byte_count=len(manifest_payload),
    )
    upload_descriptors = (*resource.upload_descriptors, manifest_upload)
    upload_projection = sha256_bytes(
        canonical_json_bytes(
            {
                "schema": UPLOAD_PROJECTION_SCHEMA,
                "entries": [item.to_record() for item in upload_descriptors],
                "manifest_published_last": True,
            }
        )
    )
    record = {
        "schema": BRIDGE_SCHEMA,
        "resource_candidate_id": resource.candidate_id,
        "resource_candidate_sha256": resource.candidate_sha256,
        "capacity_receipt_id": reviewed.receipt_id,
        "capacity_receipt_sha256": reviewed.receipt_sha256,
        "terminal_build_id": terminal_build.build_id,
        "terminal_build_sha256": terminal_build.build_sha256,
        "lifecycle_inventory_sha256": terminal_build.lifecycle_inventory_sha256,
        "economic_execution_binding_id": economic_execution.binding_id,
        "economic_execution_binding_sha256": economic_execution.binding_sha256,
        "economic_execution_definition_id": economic_execution.definition_id,
        "economic_execution_definition_sha256": (
            economic_execution.definition_sha256
        ),
        "economic_execution_definition_payload_sha256": (
            economic_execution.definition_payload_sha256
        ),
        "formal_report_contract_id": report_contract.contract_id,
        "formal_report_contract_sha256": report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": report_contract.artifact_sha256,
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_economic_execution_definition_sha256": (
            report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_report_family_count": (
            report_contract.report_family_count
        ),
        "formal_report_contract_secondary_hypothesis_count": (
            report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            report_contract.strategy_trial_count
        ),
        "streamed_input_candidate_id": resource.streamed_input.candidate_id,
        "streamed_input_candidate_sha256": resource.streamed_input.candidate_sha256,
        "physical_formal_shard_archive_id": resource.streamed_input.shards.archive_id,
        "physical_formal_shard_archive_sha256": resource.streamed_input.shards.archive_sha256,
        "production_input_package": production_input.to_record(),
        "preopen_control_stage_output": preopen.to_record(),
        "current_view_partition_set": resource.current_view_partition_set.to_record(),
        "censored_view_partition_set": resource.censored_view_partition_set.to_record(),
        "resource_census": resource.resource_census.to_record(),
        "input_manifest": input_manifest.to_record(),
        "input_manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "runtime_projection_id": projection.projection_id,
        "runtime_projection_sha256": projection.projection_sha256,
        "formal_run_candidate_id": formal_candidate.candidate_id,
        "formal_run_candidate_sha256": formal_candidate.candidate_sha256,
        "upload_descriptors": [item.to_record() for item in upload_descriptors],
        "upload_projection_sha256": upload_projection,
        "upload_entry_count": len(upload_descriptors),
        "upload_total_byte_count": sum(item.byte_count for item in upload_descriptors),
        "physical_shard_payloads_retained": False,
        "sequential_reopen_rehash_required": True,
        "legacy_tuple_upload_compatible": False,
        "discovery_gate_affirmative": False,
        "owner_signature_gate_affirmative": False,
        "qc_launch_available": False,
    }
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(StreamedFormalRuntimeBridge)
    values = {
        "bridge_id": f"arv2-streamed-formal-runtime-bridge-{digest[:24]}",
        "bridge_sha256": digest,
        "schema": BRIDGE_SCHEMA,
        "resource_candidate": resource,
        "capacity": reviewed,
        "terminal_build": terminal_build,
        "economic_execution": economic_execution,
        "report_contract": report_contract,
        "production_input_package": production_input,
        "preopen_control_stage_output": preopen,
        "current_view_partition_set": resource.current_view_partition_set,
        "censored_view_partition_set": resource.censored_view_partition_set,
        "input_manifest_payload": manifest_payload,
        "input_manifest": input_manifest,
        "runtime_projection": projection,
        "formal_run_candidate": formal_candidate,
        "upload_descriptors": upload_descriptors,
        "upload_projection_sha256": upload_projection,
        "upload_entry_count": len(upload_descriptors),
        "upload_total_byte_count": sum(item.byte_count for item in upload_descriptors),
        "physical_shard_payloads_retained": False,
        "sequential_reopen_rehash_required": True,
        "legacy_tuple_upload_compatible": False,
        "discovery_gate_affirmative": False,
        "owner_signature_gate_affirmative": False,
        "qc_launch_available": False,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    topology = (
        id(value.resource_candidate),
        id(value.capacity),
        id(value.terminal_build),
        id(value.economic_execution),
        id(value.economic_execution.definition),
        id(value.report_contract),
        id(value.production_input_package),
        id(value.preopen_control_stage_output),
        id(value.current_view_partition_set),
        id(value.censored_view_partition_set),
        id(value.input_manifest_payload),
        id(value.input_manifest),
        id(value.runtime_projection),
        id(value.formal_run_candidate),
        id(value.upload_descriptors),
        tuple(id(item) for item in value.upload_descriptors),
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_bridge(key, ref))
    with _BRIDGE_LOCK:
        _BRIDGES[identity] = (
            reference,
            canonical_json_bytes(record),
            topology,
        )
    return require_streamed_formal_runtime_bridge(value)


def require_streamed_formal_runtime_bridge(
    value: StreamedFormalRuntimeBridge,
) -> StreamedFormalRuntimeBridge:
    if type(value) is not StreamedFormalRuntimeBridge:
        raise FormalStreamingBridgeError("streamed formal runtime bridge changed type")
    with _BRIDGE_LOCK:
        registered = _BRIDGES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalStreamingBridgeError(
            "streamed formal runtime bridge is not builder-authenticated"
        )
    require_streamed_formal_runtime_resource_candidate(value.resource_candidate)
    require_streamed_formal_runtime_capacity_binding(value.capacity)
    try:
        require_formal_terminal_disposition_build(value.terminal_build)
    except FormalTerminalDispositionBuildError as exc:
        raise FormalStreamingBridgeError(
            "streamed runtime lifecycle terminal build changed"
        ) from exc
    try:
        economic_execution = require_formal_economic_execution_binding(
            value.economic_execution
        )
    except FormalEconomicExecutionDefinitionError as exc:
        raise FormalStreamingBridgeError(
            "streamed economic execution binding changed"
        ) from exc
    try:
        report_contract = require_formal_report_contract(
            value.report_contract,
            expected_economic_execution_definition_sha256=(
                economic_execution.definition_sha256
            ),
        )
    except FormalReportContractError as exc:
        raise FormalStreamingBridgeError(
            "streamed formal report contract changed"
        ) from exc
    require_artifact_binding(value.production_input_package)
    require_artifact_binding(value.preopen_control_stage_output)
    require_artifact_binding(value.current_view_partition_set)
    require_artifact_binding(value.censored_view_partition_set)
    runtime.require_qc_object_payload_binding(value.input_manifest)
    runtime.require_formal_qc_runtime_projection(value.runtime_projection)
    require_formal_run_candidate(value.formal_run_candidate)
    topology = (
        id(value.resource_candidate),
        id(value.capacity),
        id(value.terminal_build),
        id(value.economic_execution),
        id(value.economic_execution.definition),
        id(value.report_contract),
        id(value.production_input_package),
        id(value.preopen_control_stage_output),
        id(value.current_view_partition_set),
        id(value.censored_view_partition_set),
        id(value.input_manifest_payload),
        id(value.input_manifest),
        id(value.runtime_projection),
        id(value.formal_run_candidate),
        id(value.upload_descriptors),
        tuple(id(item) for item in value.upload_descriptors),
    )
    record = value.to_record()
    digest = sha256_bytes(canonical_json_bytes(record))
    manifest = _strict_object(value.input_manifest_payload, "streamed input manifest")
    expected_upstream = _upstream_capacity_record(value.capacity)
    try:
        formal_source = runtime._reconstruct_projected_module_source(
            value.runtime_projection.source_files,
            runtime.FORMAL_EVALUATOR_PROJECT_PATH,
        )
        expected_lineage = _streamed_formal_input_lineage_record(
            candidate=value.resource_candidate.streamed_input,
            production_input=value.production_input_package,
            preopen=value.preopen_control_stage_output,
            formal_evaluator_source_sha256=hashlib.sha256(formal_source).hexdigest(),
        )
    except (runtime.FormalQcRuntimeProjectionError, TypeError, ValueError) as exc:
        raise FormalStreamingBridgeError(
            "streamed formal input lineage could not be reauthenticated"
        ) from exc
    if (
        registered[1] != canonical_json_bytes(record)
        or registered[2] != topology
        or value.bridge_sha256 != digest
        or value.bridge_id != f"arv2-streamed-formal-runtime-bridge-{digest[:24]}"
        or value.capacity.resource_candidate is not value.resource_candidate
        or value.resource_candidate.streamed_input.terminal_build
        is not value.terminal_build
        or value.resource_candidate.streamed_input.economic_execution
        is not economic_execution
        or value.resource_candidate.streamed_input.report_contract
        is not report_contract
        or value.terminal_build.terminal_package
        is not value.resource_candidate.streamed_input.terminal_package
        or value.terminal_build.terminal_census
        is not value.formal_run_candidate.terminal_census
        or value.current_view_partition_set
        is not value.resource_candidate.current_view_partition_set
        or value.censored_view_partition_set
        is not value.resource_candidate.censored_view_partition_set
        or value.runtime_projection.input_manifest is not value.input_manifest
        or value.formal_run_candidate.production_input_package
        is not value.production_input_package
        or value.formal_run_candidate.current_view_partition_set
        is not value.current_view_partition_set
        or value.formal_run_candidate.censored_view_partition_set
        is not value.censored_view_partition_set
        or value.formal_run_candidate.accepted_risk
        is not value.resource_candidate.streamed_input.accepted_risk
        or value.formal_run_candidate.power_floor
        is not value.resource_candidate.streamed_input.power_floor
        or value.formal_run_candidate.terminal_census
        is not value.resource_candidate.streamed_input.terminal_package.terminal_census
        or value.formal_run_candidate.code_projection
        != runtime.formal_code_projection_binding(value.runtime_projection)
        or hashlib.sha256(value.input_manifest_payload).hexdigest()
        != value.input_manifest.content_sha256
        or manifest.get("shards")
        != [
            item.to_record()
            for item in value.resource_candidate.streamed_input.shards.descriptors
        ]
        or manifest.get("resource_census")
        != value.resource_candidate.resource_census.to_record()
        or manifest.get("capacity_review") != value.capacity.runtime_capacity.to_record()
        or manifest.get("upstream_scoring_materialization_capacity") != expected_upstream
        or manifest.get("streamed_formal_input_lineage") != expected_lineage
        or value.upload_entry_count != len(value.upload_descriptors)
        or value.upload_total_byte_count
        != sum(item.byte_count for item in value.upload_descriptors)
        or value.upload_descriptors[-1].role != "input_manifest"
        or value.upload_descriptors[-1].content_sha256
        != value.input_manifest.content_sha256
        or value.physical_shard_payloads_retained is not False
        or value.sequential_reopen_rehash_required is not True
        or value.legacy_tuple_upload_compatible is not False
        or value.discovery_gate_affirmative is not False
        or value.owner_signature_gate_affirmative is not False
        or value.qc_launch_available is not False
    ):
        raise FormalStreamingBridgeError(
            "streamed formal runtime bridge changed after authentication"
        )
    return value


def iter_streamed_formal_qc_upload_entries(
    bridge: StreamedFormalRuntimeBridge,
) -> Iterator[StreamedFormalUploadEntry]:
    """Yield one reauthenticated shard at a time, then the manifest last."""

    value = require_streamed_formal_runtime_bridge(bridge)
    shard_expected = value.upload_descriptors[:-1]
    emitted = 0
    for physical, expected in zip(
        iter_physical_formal_shard_payloads(
            value.resource_candidate.streamed_input.shards
        ),
        shard_expected,
        strict=True,
    ):
        observed = StreamedFormalUploadDescriptor(
            role=physical.descriptor.role,
            object_store_key=physical.descriptor.object_store_key,
            content_sha256=hashlib.sha256(physical.payload).hexdigest(),
            content_md5=hashlib.md5(
                physical.payload, usedforsecurity=False
            ).hexdigest(),
            byte_count=len(physical.payload),
        )
        if observed != expected:
            raise FormalStreamingBridgeError(
                "physical shard changed during streamed upload replay"
            )
        emitted += 1
        entry = StreamedFormalUploadEntry(
            **observed.to_record(), payload=physical.payload
        )
        yield entry
        # Do not keep the just-emitted payload in either this generator frame
        # or the physical replay generator while the successor is opened.
        del entry, physical
    if emitted != len(shard_expected):
        raise FormalStreamingBridgeError("streamed upload omitted a physical shard")
    manifest_expected = value.upload_descriptors[-1]
    observed_manifest = StreamedFormalUploadDescriptor(
        role="input_manifest",
        object_store_key=value.input_manifest.object_store_key,
        content_sha256=hashlib.sha256(value.input_manifest_payload).hexdigest(),
        content_md5=hashlib.md5(
            value.input_manifest_payload, usedforsecurity=False
        ).hexdigest(),
        byte_count=len(value.input_manifest_payload),
    )
    if observed_manifest != manifest_expected:
        raise FormalStreamingBridgeError("streamed input manifest changed before publish")
    yield StreamedFormalUploadEntry(
        **observed_manifest.to_record(), payload=value.input_manifest_payload
    )


def _bind_streamed_runtime_capacity_authority(
    authority_register: object,
    authority_current: object,
    load_implementation: object,
    require_implementation: object,
):
    """Expose only loader/checker closures, never the authority operations."""

    def load_streamed_formal_runtime_capacity_binding(
        *,
        resource_candidate: StreamedFormalRuntimeResourceCandidate,
        runtime_capacity_reviewed_receipt_path: Path,
        streamed_bridge_reviewed_receipt_path: Path,
    ) -> StreamedFormalRuntimeCapacityBinding:
        value = load_implementation(
            resource_candidate=resource_candidate,
            runtime_capacity_reviewed_receipt_path=(
                runtime_capacity_reviewed_receipt_path
            ),
            streamed_bridge_reviewed_receipt_path=(
                streamed_bridge_reviewed_receipt_path
            ),
            _authority_register=authority_register,
        )
        return require_streamed_formal_runtime_capacity_binding(value)

    def require_streamed_formal_runtime_capacity_binding(
        value: StreamedFormalRuntimeCapacityBinding,
    ) -> StreamedFormalRuntimeCapacityBinding:
        return require_implementation(
            value, _authority_current=authority_current
        )

    return (
        load_streamed_formal_runtime_capacity_binding,
        require_streamed_formal_runtime_capacity_binding,
    )


(
    load_streamed_formal_runtime_capacity_binding,
    require_streamed_formal_runtime_capacity_binding,
) = _bind_streamed_runtime_capacity_authority(
    _bridge_capacity_authority_register,
    _bridge_capacity_authority_current,
    _load_streamed_formal_runtime_capacity_binding_impl,
    _require_streamed_formal_runtime_capacity_binding_impl,
)
_seal_bridge_capacity_authority_provenance((
    _load_streamed_formal_runtime_capacity_binding_impl,
    load_streamed_formal_runtime_capacity_binding,
))
del _bind_streamed_runtime_capacity_authority
del _bridge_capacity_authority_register
del _bridge_capacity_authority_current
del _load_streamed_formal_runtime_capacity_binding_impl
del _make_bridge_capacity_authority_vault
del _seal_bridge_capacity_authority_provenance
del _require_streamed_formal_runtime_capacity_binding_impl


__all__ = (
    "FormalStreamingBridgeError",
    "STREAMED_FORMAL_INPUT_LINEAGE_SCHEMA",
    "StreamedFormalRuntimeBridge",
    "StreamedFormalRuntimeCapacityBinding",
    "StreamedFormalRuntimeResourceCandidate",
    "StreamedFormalUploadDescriptor",
    "StreamedFormalUploadEntry",
    "build_streamed_formal_runtime_bridge",
    "build_streamed_formal_runtime_resource_candidate",
    "iter_streamed_formal_qc_upload_entries",
    "load_streamed_formal_runtime_capacity_binding",
    "render_streamed_formal_runtime_bridge_review_candidate",
    "require_streamed_formal_runtime_bridge",
    "require_streamed_formal_runtime_capacity_binding",
    "require_streamed_formal_runtime_resource_candidate",
)
