"""Offline contract and disk-backed reviewed receipt for QC discovery.

This module performs no network, provider, credential, QuantConnect, market,
or outcome I/O.  Its builders are pure.  The receipt loader reads a bounded,
owner-only local archive one shard at a time; only exhaustive physical
validation can mint :class:`ReviewedFundamentalUniverseDiscoveryReceipt`.

The affirmative receipt is deliberately scoped.  It establishes the full
point-in-time member census exposed by QuantConnect's US Fundamentals history
for the requested sessions, including delisted members under that dataset's
documented contract.  It does not establish an off-QC security master,
Morningstar revision/tombstone history, or an original publication timestamp.
The assigned availability instant is a conservative decision-clock value one
microsecond before the reviewed market open, never a claimed vendor timestamp.
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
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo


class FundamentalUniverseDiscoveryError(ValueError):
    """The offline projection or physical discovery evidence is invalid."""


PLAN_SCHEMA = "arv2-qc-fundamental-universe-discovery-plan-v1"
PROJECTION_SCHEMA = "arv2-qc-fundamental-universe-discovery-projection-v1"
SOURCE_FILE_SCHEMA = "arv2-qc-fundamental-universe-project-source-v1"
OUTPUT_MANIFEST_SCHEMA = "arv2-qc-fundamental-universe-output-manifest-v1"
OUTPUT_SHARD_SCHEMA = "arv2-qc-fundamental-universe-terminal-shard-v1"
TERMINAL_SCHEMA = "arv2-qc-fundamental-universe-terminal-v1"
CENSUS_SCHEMA = "arv2-qc-fundamental-universe-session-census-v1"
TERMINAL_PACKAGE_SCHEMA = "arv2-qc-fundamental-universe-terminal-package-v1"
RECEIPT_SCHEMA = "arv2-reviewed-qc-fundamental-universe-discovery-receipt-v1"
ELIGIBLE_UNIVERSE_ARTIFACT_SCHEMA = (
    "arv2-qc-fundamental-eligible-universe-artifact-v1"
)
SID_MAPPING_ARTIFACT_SCHEMA = "arv2-qc-fundamental-sid-mapping-artifact-v1"
FUNDAMENTAL_ARTIFACT_SCHEMA = "arv2-qc-preopen-fundamental-artifact-v1"
AVAILABILITY_POLICY_ID = (
    "qc-morningstar-pit-session-snapshot-conservative-preopen-v1"
)
SOURCE_SCOPE_ID = "quantconnect-us-fundamentals-history-all-including-delisted-v1"

PROJECT_NAME = "1 ARV2_FUNDAMENTAL_UNIVERSE_DISCOVERY - 20260912"
BACKTEST_NAME = "ARV2 outcome-free QC Fundamentals universe discovery"
ENTRY_PATH = "main.py"
WORKER_PATH = "fundamental_universe_discovery_worker.py"
RUNTIME_PATH = "fundamental_universe_discovery_runtime.py"
INPUT_PREFIX = "arv2/fundamental-universe-discovery/input/"
OUTPUT_PREFIX = "arv2/fundamental-universe-discovery/output/"
SUMMARY_NAME = "ARV2_FUNDAMENTAL_UNIVERSE_DISCOVERY_RECEIPT"
ARCHIVE_MANIFEST_NAME = "output-manifest.json"
ARCHIVE_PACKAGE_NAME = "terminal-package.json"
ARCHIVE_SHARD_DIRECTORY = "terminal-shards"

# The formal test interval remains 2020-2025, but its first fold needs
# pre-open source rows back to 2013-01-02.  The exact NYSE source axis contains
# 3,270 sessions; 3,300 is a small explicit ceiling, not an unbounded range.
FORMAL_SOURCE_AXIS_FIRST_SESSION = "2013-01-02"
FORMAL_SOURCE_AXIS_LAST_SESSION = "2025-12-31"
FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT = 3_270
MAX_DECISION_SESSIONS = 3_300
HISTORY_CHUNK_SESSION_COUNT = 20
MAX_HISTORY_CALLS = 165
MAX_COLLECTION_ROWS = 25_000
MAX_TOTAL_SOURCE_ROWS = MAX_DECISION_SESSIONS * MAX_COLLECTION_ROWS
MAX_SHARD_ROWS = 500_000
MAX_TERMINAL_SHARDS = MAX_DECISION_SESSIONS
MAX_PLAN_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_TERMINAL_PACKAGE_BYTES = 64 * 1024
MAX_PROJECT_SOURCE_CHARACTERS = 60_000
MAX_UNCOMPRESSED_SHARD_BYTES = 256 * 1024 * 1024
# FormalQcTransport bounds an entire JSON response at 16 MiB.  Keep the
# base64-encoded object plus its envelope below that pre-existing boundary.
MAX_COMPRESSED_SHARD_BYTES = 10 * 1024 * 1024
MAX_TOTAL_COMPRESSED_OUTPUT_BYTES = (
    MAX_TERMINAL_SHARDS * MAX_COMPRESSED_SHARD_BYTES
)
MIN_OBJECT_STORE_CAPACITY_BYTES = (
    MAX_TOTAL_COMPRESSED_OUTPUT_BYTES
    + MAX_OUTPUT_MANIFEST_BYTES
    + MAX_TERMINAL_PACKAGE_BYTES
    + MAX_PLAN_BYTES
)
MIN_OBJECT_STORE_FILE_CAPACITY = MAX_TERMINAL_SHARDS + 3
MAX_JSON_DEPTH = 20

_MARKER = "__ARV2_FUNDAMENTAL_DISCOVERY_CONTRACT_SHA256__"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,511}\Z")
_NEW_YORK = ZoneInfo("America/New_York")


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
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise FundamentalUniverseDiscoveryError(
            "value is not canonical JSON"
        ) from exc


def fundamental_universe_discovery_contract_record() -> dict[str, object]:
    """Return the exact narrow source, clock, and capability contract."""

    return {
        "schema": "arv2-qc-fundamental-universe-discovery-contract-v1",
        "source_scope_id": SOURCE_SCOPE_ID,
        "formal_source_axis": {
            "first_session_inclusive": FORMAL_SOURCE_AXIS_FIRST_SESSION,
            "last_session_inclusive": FORMAL_SOURCE_AXIS_LAST_SESSION,
            "nyse_decision_session_count": (
                FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT
            ),
            "purpose": (
                "pre-open source coverage for every training, validation, and "
                "test session needed by the fixed 2020-2025 formal folds"
            ),
            "formal_outcome_test_interval_changed": False,
        },
        "source": {
            "provider": "QuantConnect",
            "dataset": "Morningstar US Fundamentals",
            "request": "History[Fundamentals]",
            "all_us_equities_including_delisted": True,
            "documented_point_in_time_snapshots": True,
            "current_ticker_is_not_identity": True,
            "permanent_identity": "exact string form of QC SecurityIdentifier",
            "cross_vendor_join_key": (
                "exact QC symbol.cusip; missing or invalid CUSIP is a named refusal"
            ),
        },
        "decision_clock": {
            "timezone": "America/New_York",
            "qc_algorithm_time_zone": "America/New_York",
            "market_open_local": "09:30:00",
            "availability_policy_id": AVAILABILITY_POLICY_ID,
            "assigned_available_at": "decision_open_UTC_minus_one_microsecond",
            "assigned_time_is_vendor_publication_timestamp": False,
            "reason": (
                "a conservative pre-open ceiling used only after the QC history "
                "collection is physically observed before that session's market "
                "open; it is not source-publication evidence"
            ),
        },
        "eligible_lane_projection": {
            "issuer_incorporation_country": "USA",
            "morningstar_security_type": "ST00000001",
            "depositary_receipt": False,
            "primary_exchange_map": {
                "ASE": "XASE",
                "NAS": "XNAS",
                "NYS": "XNYS",
            },
            "display_ticker_authoritative": False,
            "delisting_date_filters_membership": False,
        },
        "discovery_fields": {
            "classification": [
                "morningstar_sector_code",
                "morningstar_industry_group_code",
                "morningstar_industry_code",
            ],
            "non_currency_share_observation": [
                "financial_statements.period_ending_date",
                "company_profile.share_class_level_shares_outstanding",
            ],
            "statement_currency_assumed": False,
            "book_equity_or_revenue_emitted": False,
        },
        "required_cross_vendor_bridge": (
            "A later reviewed composer must join exact QC CUSIP/SID census to "
            "Sharadar PIT identity plus equityusd/revenueusd and actual comparable "
            "prior-fiscal-year rows, then combine Massive control roles and q-data. "
            "This discovery receipt alone is not a production pre-open input."
        ),
        "object_store_capacity_preflight": {
            "maximum_size_attribute": "object_store.max_size",
            "maximum_files_attribute": "object_store.max_files",
            "minimum_capacity_bytes": MIN_OBJECT_STORE_CAPACITY_BYTES,
            "minimum_file_capacity": MIN_OBJECT_STORE_FILE_CAPACITY,
            "remaining_capacity_established": False,
            "write_failures_remain_terminal": True,
        },
        "terminal_rule": (
            "one accepted, out_of_scope, or named_refusal terminal for every "
            "source collection member; missing collection refuses the run"
        ),
        "affirmative_scope": {
            "full_pit_universe_established": (
                "only within the exact QC US Fundamentals History source scope"
            ),
            "full_market_peer_census_established": (
                "all source members terminalled; named refusals remain explicit"
            ),
            "off_qc_security_master_established": False,
            "vendor_revision_or_tombstone_history_established": False,
            "morningstar_publication_timestamp_established": False,
            "production_preopen_input_available": False,
        },
        "forbidden": {
            "price_or_return_access": True,
            "outcome_or_result_access": True,
            "current_ticker_identity": True,
            "provider_credentials": True,
            "orders_or_portfolio_actions": True,
            "deployment_or_trading": True,
            "row_or_value_logging": True,
        },
    }


CONTRACT_BYTES = canonical_json_bytes(fundamental_universe_discovery_contract_record())
CONTRACT_SHA256 = hashlib.sha256(CONTRACT_BYTES).hexdigest()
CONTRACT_ID = f"arv2-qc-fundamental-universe-contract-{CONTRACT_SHA256[:16]}"


def render_fundamental_universe_discovery_contract_bytes() -> bytes:
    return bytes(CONTRACT_BYTES)


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise FundamentalUniverseDiscoveryError("JSON depth exceeds reviewed bound")
    if value is None or type(value) in (str, bool, int):
        if type(value) is int and abs(value) > 10**18:
            raise FundamentalUniverseDiscoveryError("JSON integer exceeds bound")
        return
    if type(value) is list:
        for item in value:
            _check_depth(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise FundamentalUniverseDiscoveryError("JSON key is not text")
            _check_depth(item, depth + 1)
        return
    raise FundamentalUniverseDiscoveryError("JSON scalar type is forbidden")


def _strict_json(payload: bytes, name: str, *, maximum: int) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise FundamentalUniverseDiscoveryError(f"{name} exceeds its byte bound")

    def pairs(items):
        result = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise FundamentalUniverseDiscoveryError(
                    f"{name} has a duplicate or non-string key"
                )
            result[key] = value
        return result

    def forbidden_number(_value):
        raise FundamentalUniverseDiscoveryError(
            f"{name} contains a binary float or non-finite value"
        )

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=forbidden_number,
            parse_constant=forbidden_number,
        )
    except FundamentalUniverseDiscoveryError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is not strict JSON") from exc
    if type(value) is not dict:
        raise FundamentalUniverseDiscoveryError(f"{name} is not one JSON object")
    _check_depth(value)
    if canonical_json_bytes(value) != payload:
        raise FundamentalUniverseDiscoveryError(f"{name} is not canonical")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise FundamentalUniverseDiscoveryError(f"{name} is not lowercase SHA-256")
    return value


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FundamentalUniverseDiscoveryError(
            f"{name} is not an exact integer >= {minimum}"
        )
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FundamentalUniverseDiscoveryError(f"{name} is not a safe identifier")
    return value


def _safe_key(value: object, name: str) -> str:
    if (
        type(value) is not str
        or _SAFE_KEY.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise FundamentalUniverseDiscoveryError(f"{name} is not a safe key")
    return value


def _date(value: object, name: str) -> date:
    if type(value) is not str:
        raise FundamentalUniverseDiscoveryError(f"{name} is not a session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is not a session date") from exc
    if parsed.isoformat() != value:
        raise FundamentalUniverseDiscoveryError(f"{name} is not canonical")
    return parsed


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise FundamentalUniverseDiscoveryError(f"{name} is not a UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is not a UTC instant") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise FundamentalUniverseDiscoveryError(f"{name} is not canonical UTC text")
    return parsed


def _expected_open(session: date) -> str:
    local = datetime.combine(session, time(9, 30), tzinfo=_NEW_YORK)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _history_collection_time(
    value: object, *, session: date, name: str
) -> datetime:
    if type(value) is not str or not value:
        raise FundamentalUniverseDiscoveryError(f"{name} is not an exact datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FundamentalUniverseDiscoveryError(
            f"{name} is not an exact datetime"
        ) from exc
    if parsed.isoformat(timespec="microseconds") != value:
        raise FundamentalUniverseDiscoveryError(f"{name} is not canonical")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        local = parsed.replace(tzinfo=_NEW_YORK)
    else:
        local = parsed.astimezone(_NEW_YORK)
    if local.date() != session or local.timetz().replace(tzinfo=None) >= time(9, 30):
        raise FundamentalUniverseDiscoveryError(
            f"{name} was not observed before the decision-session market open"
        )
    return parsed


_SESSION_FIELDS = {
    "decision_session",
    "decision_session_ordinal",
    "decision_open_utc",
}


def _validated_session_geometry(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != _SESSION_FIELDS:
        raise FundamentalUniverseDiscoveryError("decision-session fields changed")
    session = _date(value["decision_session"], "decision session")
    ordinal = _count(
        value["decision_session_ordinal"], "decision session ordinal", minimum=1
    )
    opened = _utc(value["decision_open_utc"], "decision open")
    if value["decision_open_utc"] != _expected_open(session):
        raise FundamentalUniverseDiscoveryError(
            "decision open is not 09:30 America/New_York"
        )
    return {
        "decision_session": session.isoformat(),
        "decision_session_ordinal": ordinal,
        "decision_open_utc": opened.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def build_fundamental_universe_discovery_plan_bytes(
    *, decision_sessions: Sequence[Mapping[str, object]], calculation_session: str
) -> bytes:
    """Build an exact bounded plan; this pure operation grants no QC authority."""

    if type(decision_sessions) not in (list, tuple) or not decision_sessions:
        raise FundamentalUniverseDiscoveryError("decision sessions are absent")
    if len(decision_sessions) > MAX_DECISION_SESSIONS:
        raise FundamentalUniverseDiscoveryError("decision session cap exceeded")
    sessions = [_validated_session_geometry(dict(item)) for item in decision_sessions]
    identities = [item["decision_session"] for item in sessions]
    ordinals = [item["decision_session_ordinal"] for item in sessions]
    if identities != sorted(set(identities)):
        raise FundamentalUniverseDiscoveryError(
            "decision sessions repeat or are not increasing"
        )
    if ordinals != list(range(1, len(sessions) + 1)):
        raise FundamentalUniverseDiscoveryError(
            "decision session ordinals must be contiguous from one"
        )
    calculation = _date(calculation_session, "calculation session")
    if calculation <= _date(identities[-1], "last decision session"):
        raise FundamentalUniverseDiscoveryError(
            "calculation session must follow every decision session"
        )
    chunks = []
    for ordinal, offset in enumerate(
        range(0, len(sessions), HISTORY_CHUNK_SESSION_COUNT)
    ):
        group = sessions[offset : offset + HISTORY_CHUNK_SESSION_COUNT]
        first = _date(group[0]["decision_session"], "chunk first session")
        last = _date(group[-1]["decision_session"], "chunk last session")
        chunks.append(
            {
                "ordinal": ordinal,
                "first_session": first.isoformat(),
                "last_session": last.isoformat(),
                "request_start": first.isoformat() + "T00:00:00",
                "request_end_exclusive": (last + timedelta(days=1)).isoformat()
                + "T00:00:00",
                "decision_sessions": [item["decision_session"] for item in group],
            }
        )
    if len(chunks) > MAX_HISTORY_CALLS:
        raise FundamentalUniverseDiscoveryError("history call cap exceeded")
    plan_without_identity = {
        "schema": PLAN_SCHEMA,
        "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "plan_id": None,
        "plan_sha256": None,
        "first_session": identities[0],
        "last_session": identities[-1],
        "calculation_session": calculation.isoformat(),
        "decision_sessions": sessions,
        "history_chunks": chunks,
        "source_contract": fundamental_universe_discovery_contract_record(),
        "availability_policy": {
            "policy_id": AVAILABILITY_POLICY_ID,
            "assigned_available_at": "decision_open_UTC_minus_one_microsecond",
            "source_publication_timestamp_claimed": False,
            "point_in_time_scope": SOURCE_SCOPE_ID,
        },
        "resource_census": {
            "decision_session_count": len(sessions),
            "history_call_count": len(chunks),
            "history_chunk_session_count": HISTORY_CHUNK_SESSION_COUNT,
            "maximum_decision_sessions": MAX_DECISION_SESSIONS,
            "maximum_history_calls": MAX_HISTORY_CALLS,
            "maximum_collection_rows": MAX_COLLECTION_ROWS,
            "maximum_total_source_rows": MAX_TOTAL_SOURCE_ROWS,
            "maximum_shard_rows": MAX_SHARD_ROWS,
            "maximum_terminal_shards": MAX_TERMINAL_SHARDS,
            "maximum_uncompressed_shard_bytes": MAX_UNCOMPRESSED_SHARD_BYTES,
            "maximum_compressed_shard_bytes": MAX_COMPRESSED_SHARD_BYTES,
            "maximum_total_compressed_output_bytes": (
                MAX_TOTAL_COMPRESSED_OUTPUT_BYTES
            ),
            "minimum_object_store_capacity_bytes": (
                MIN_OBJECT_STORE_CAPACITY_BYTES
            ),
            "minimum_object_store_file_capacity": (
                MIN_OBJECT_STORE_FILE_CAPACITY
            ),
        },
        "execution_contract": {
            "history_dataset": "Fundamentals",
            "algorithm_time_zone": "America/New_York",
            "all_us_equities_including_delisted": True,
            "object_store_read_write": True,
            "custom_terminal_summary": True,
            "price_or_return_access": False,
            "outcome_or_result_access": False,
            "orders_or_portfolio_actions": False,
            "external_launch_authority_embedded": False,
        },
        "terminal_package_key": None,
    }
    semantic = dict(plan_without_identity)
    seed = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    plan_id = f"arv2-qc-fundamental-universe-plan-{seed[:24]}"
    package_key = OUTPUT_PREFIX + "packages/" + seed + ".json"
    plan_without_identity["plan_id"] = plan_id
    plan_without_identity["terminal_package_key"] = package_key
    normalized = dict(plan_without_identity)
    normalized["plan_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    plan_without_identity["plan_sha256"] = digest
    payload = canonical_json_bytes(plan_without_identity)
    if len(payload) > MAX_PLAN_BYTES:
        raise FundamentalUniverseDiscoveryError("discovery plan exceeds byte bound")
    return payload


def _validate_plan(payload: bytes) -> dict[str, object]:
    value = _strict_json(payload, "discovery plan", maximum=MAX_PLAN_BYTES)
    expected_fields = {
        "schema",
        "contract_id",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "first_session",
        "last_session",
        "calculation_session",
        "decision_sessions",
        "history_chunks",
        "source_contract",
        "availability_policy",
        "resource_census",
        "execution_contract",
        "terminal_package_key",
    }
    if (
        set(value) != expected_fields
        or value.get("schema") != PLAN_SCHEMA
        or value.get("contract_id") != CONTRACT_ID
        or value.get("contract_sha256") != CONTRACT_SHA256
    ):
        raise FundamentalUniverseDiscoveryError("discovery plan schema changed")
    rebuilt = build_fundamental_universe_discovery_plan_bytes(
        decision_sessions=value["decision_sessions"],
        calculation_session=value["calculation_session"],
    )
    if rebuilt != payload:
        raise FundamentalUniverseDiscoveryError("discovery plan identity changed")
    _safe_id(value["plan_id"], "plan id")
    _sha(value["plan_sha256"], "plan semantic hash")
    _safe_key(value["terminal_package_key"], "terminal package key")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoveryProjectSource:
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


@dataclasses.dataclass(frozen=True, init=False)
class FundamentalUniverseDiscoveryQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    project_name: str
    backtest_name: str
    plan_id: str
    plan_sha256: str
    plan_artifact_sha256: str
    plan_byte_count: int
    plan_object_store_key: str
    plan_bytes: bytes = dataclasses.field(repr=False)
    terminal_package_key: str
    source_files: tuple[FundamentalDiscoveryProjectSource, ...]
    project_source_set_sha256: str
    calculation_session: str
    calculation_end_date: str
    history_call_count: int
    maximum_total_source_rows: int
    runtime_source_enabled: bool
    external_launch_authority_embedded: bool
    reads_fundamentals_history: bool
    reads_prices_or_returns: bool
    reads_outcomes_or_results: bool
    places_orders_or_touches_portfolio: bool


_PROJECTIONS: dict[
    int,
    tuple[
        weakref.ReferenceType[FundamentalUniverseDiscoveryQcProjection],
        tuple[object, ...],
    ],
] = {}
_PROJECTION_LOCK = threading.RLock()


def _projection_fingerprint(
    value: FundamentalUniverseDiscoveryQcProjection,
) -> tuple[object, ...]:
    result = []
    for field in dataclasses.fields(value):
        item = getattr(value, field.name)
        if field.name == "source_files":
            if type(item) is not tuple or any(
                type(source) is not FundamentalDiscoveryProjectSource
                for source in item
            ):
                return ("invalid-project-source-topology",)
            result.append(
                tuple(
                    (
                        source.project_path,
                        source.content_sha256,
                        source.byte_count,
                        source.character_count,
                        source.content,
                    )
                    for source in item
                )
            )
        else:
            result.append(item)
    return tuple(result)


def _forget_projection(
    identity: int,
    reference: weakref.ReferenceType[FundamentalUniverseDiscoveryQcProjection],
) -> None:
    with _PROJECTION_LOCK:
        current = _PROJECTIONS.get(identity)
        if current is not None and current[0] is reference:
            _PROJECTIONS.pop(identity, None)


def _source(path: str, payload: bytes) -> FundamentalDiscoveryProjectSource:
    if type(payload) is not bytes or not payload:
        raise FundamentalUniverseDiscoveryError("project source is absent")
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise FundamentalUniverseDiscoveryError("project source is not UTF-8") from exc
    if len(text) > MAX_PROJECT_SOURCE_CHARACTERS:
        raise FundamentalUniverseDiscoveryError(
            "project source exceeds the reviewed character cap"
        )
    try:
        ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise FundamentalUniverseDiscoveryError("project source is invalid Python") from exc
    return FundamentalDiscoveryProjectSource(
        project_path=path,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        character_count=len(text),
        content=payload,
    )


def _audit_source_capabilities(files: tuple[FundamentalDiscoveryProjectSource, ...]) -> None:
    if tuple(item.project_path for item in files) != (
        ENTRY_PATH,
        WORKER_PATH,
        RUNTIME_PATH,
    ):
        raise FundamentalUniverseDiscoveryError("project source inventory changed")
    forbidden_names = {
        "TradeBar",
        "QuoteBar",
        "HistoryRequest",
        "add_equity",
        "add_security",
        "set_holdings",
        "market_order",
        "limit_order",
        "stop_market_order",
        "liquidate",
        "download",
    }
    forbidden_attributes = {
        "portfolio",
        "securities",
        "transactions",
        "price",
        "close",
        "open",
        "high",
        "low",
        "volume",
        "market_cap",
        "holdings",
    }
    history_subscripts = 0
    for item in files:
        if (
            type(item) is not FundamentalDiscoveryProjectSource
            or type(item.project_path) is not str
            or type(item.content) is not bytes
            or type(item.content_sha256) is not str
            or item.content_sha256 != hashlib.sha256(item.content).hexdigest()
            or item.byte_count != len(item.content)
            or item.character_count != len(item.content.decode("utf-8"))
        ):
            raise FundamentalUniverseDiscoveryError(
                "project source descriptor or content changed"
            )
        tree = ast.parse(item.content.decode("utf-8"), filename=item.project_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                literal_keys = [
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and type(key.value) is str
                ]
                if len(literal_keys) != len(set(literal_keys)):
                    raise FundamentalUniverseDiscoveryError(
                        "project source contains a duplicate literal dictionary key"
                    )
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                raise FundamentalUniverseDiscoveryError(
                    "project source acquired a forbidden capability name"
                )
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
                raise FundamentalUniverseDiscoveryError(
                    "project source acquired a price/order/portfolio attribute"
                )
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "history"
            ):
                history_subscripts += 1
                if not isinstance(node.slice, ast.Name) or node.slice.id != "Fundamentals":
                    raise FundamentalUniverseDiscoveryError(
                        "history request is not exactly History[Fundamentals]"
                    )
    if history_subscripts != 1:
        raise FundamentalUniverseDiscoveryError(
            "project must contain exactly one Fundamentals history request"
        )


def _entry_source(
    *,
    plan: Mapping[str, object],
    plan_payload: bytes,
    plan_key: str,
    project_source_set_sha256: str,
) -> bytes:
    calculation = _date(plan["calculation_session"], "calculation session")
    calculation_end = calculation + timedelta(days=1)
    constants = {
        "PLAN_ID": plan["plan_id"],
        "PLAN_SHA256": hashlib.sha256(plan_payload).hexdigest(),
        "PLAN_BYTE_COUNT": len(plan_payload),
        "PLAN_OBJECT_STORE_KEY": plan_key,
        "TERMINAL_PACKAGE_KEY": plan["terminal_package_key"],
        "PROJECT_SOURCE_SET_SHA256": project_source_set_sha256,
        "SUMMARY_NAME": SUMMARY_NAME,
    }
    literal = json.dumps(constants, sort_keys=True, separators=(",", ":"))
    return f'''from AlgorithmImports import *
import json
from fundamental_universe_discovery_runtime import execute_fundamental_universe_discovery

_C = json.loads({literal!r})


class Arv2FundamentalUniverseDiscovery(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.set_start_date({calculation.year}, {calculation.month}, {calculation.day})
        self.set_end_date({calculation_end.year}, {calculation_end.month}, {calculation_end.day})
        self._arv2_fundamental_discovery_completed = False
        execute_fundamental_universe_discovery(self, _C)

    def on_end_of_algorithm(self):
        if self._arv2_fundamental_discovery_completed is not True:
            raise RuntimeError("ARV2 fundamental-universe discovery did not complete")
'''.encode("utf-8")


def _projection_record(
    *,
    plan: Mapping[str, object],
    plan_payload: bytes,
    plan_key: str,
    files: tuple[FundamentalDiscoveryProjectSource, ...],
    source_set_sha256: str,
) -> dict[str, object]:
    calculation = _date(plan["calculation_session"], "calculation session")
    return {
        "schema": PROJECTION_SCHEMA,
        "project_name": PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_artifact_sha256": hashlib.sha256(plan_payload).hexdigest(),
        "plan_byte_count": len(plan_payload),
        "plan_object_store_key": plan_key,
        "terminal_package_key": plan["terminal_package_key"],
        "source_files": [item.to_record() for item in files],
        "project_source_set_sha256": source_set_sha256,
        "calculation_session": calculation.isoformat(),
        "calculation_end_date": (calculation + timedelta(days=1)).isoformat(),
        "history_call_count": plan["resource_census"]["history_call_count"],
        "maximum_total_source_rows": MAX_TOTAL_SOURCE_ROWS,
        "runtime_source_enabled": True,
        "external_launch_authority_embedded": False,
        "reads_fundamentals_history": True,
        "reads_prices_or_returns": False,
        "reads_outcomes_or_results": False,
        "places_orders_or_touches_portfolio": False,
    }


def build_fundamental_universe_discovery_qc_projection(
    *, plan_bytes: bytes, worker_source_bytes: bytes, runtime_source_bytes: bytes
) -> FundamentalUniverseDiscoveryQcProjection:
    """Build the reviewed three-file QC source set without performing I/O."""

    plan = _validate_plan(plan_bytes)
    worker_text = worker_source_bytes.decode("utf-8")
    runtime_text = runtime_source_bytes.decode("utf-8")
    if worker_text.count(_MARKER) != 1 or runtime_text.count(_MARKER) != 1:
        raise FundamentalUniverseDiscoveryError("source contract marker changed")
    worker = _source(
        WORKER_PATH, worker_text.replace(_MARKER, CONTRACT_SHA256).encode("utf-8")
    )
    runtime = _source(
        RUNTIME_PATH, runtime_text.replace(_MARKER, CONTRACT_SHA256).encode("utf-8")
    )
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    plan_key = INPUT_PREFIX + "plans/" + plan_hash + ".json"
    provisional_entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=plan_bytes,
            plan_key=plan_key,
            project_source_set_sha256="0" * 64,
        ),
    )
    source_set_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "schema": "arv2-qc-fundamental-normalized-source-set-v1",
                "normalization": "entry_PROJECT_SOURCE_SET_SHA256_constant_zeroed",
                "source_files": [
                    provisional_entry.to_record(),
                    worker.to_record(),
                    runtime.to_record(),
                ],
            }
        )
    ).hexdigest()
    entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=plan_bytes,
            plan_key=plan_key,
            project_source_set_sha256=source_set_sha256,
        ),
    )
    files = (entry, worker, runtime)
    _audit_source_capabilities(files)
    record = _projection_record(
        plan=plan,
        plan_payload=plan_bytes,
        plan_key=plan_key,
        files=files,
        source_set_sha256=source_set_sha256,
    )
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(FundamentalUniverseDiscoveryQcProjection)
    fields = {
        **record,
        "projection_id": f"arv2-qc-fundamental-projection-{digest[:24]}",
        "projection_sha256": digest,
        "plan_bytes": bytes(plan_bytes),
        "source_files": files,
    }
    expected = {field.name for field in dataclasses.fields(value)}
    if set(fields) != expected:
        raise FundamentalUniverseDiscoveryError("projection field inventory changed")
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    fingerprint = _projection_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(value, lambda ref: _forget_projection(identity, ref))
    with _PROJECTION_LOCK:
        _PROJECTIONS[identity] = (reference, fingerprint)
    return require_fundamental_universe_discovery_qc_projection(value)


def require_fundamental_universe_discovery_qc_projection(
    value: FundamentalUniverseDiscoveryQcProjection,
) -> FundamentalUniverseDiscoveryQcProjection:
    if type(value) is not FundamentalUniverseDiscoveryQcProjection:
        raise FundamentalUniverseDiscoveryError("discovery projection type changed")
    with _PROJECTION_LOCK:
        state = _PROJECTIONS.get(id(value))
    if (
        state is None
        or state[0]() is not value
        or state[1] != _projection_fingerprint(value)
    ):
        raise FundamentalUniverseDiscoveryError(
            "discovery projection is not builder-authenticated"
        )
    plan = _validate_plan(value.plan_bytes)
    if (
        value.schema != PROJECTION_SCHEMA
        or value.plan_id != plan["plan_id"]
        or value.plan_sha256 != plan["plan_sha256"]
        or value.plan_artifact_sha256
        != hashlib.sha256(value.plan_bytes).hexdigest()
        or value.plan_byte_count != len(value.plan_bytes)
        or value.terminal_package_key != plan["terminal_package_key"]
        or value.runtime_source_enabled is not True
        or value.external_launch_authority_embedded is not False
        or value.reads_fundamentals_history is not True
        or value.reads_prices_or_returns is not False
        or value.reads_outcomes_or_results is not False
        or value.places_orders_or_touches_portfolio is not False
    ):
        raise FundamentalUniverseDiscoveryError("discovery projection boundary changed")
    record = _projection_record(
        plan=plan,
        plan_payload=value.plan_bytes,
        plan_key=value.plan_object_store_key,
        files=value.source_files,
        source_set_sha256=value.project_source_set_sha256,
    )
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        value.projection_sha256 != digest
        or value.projection_id != f"arv2-qc-fundamental-projection-{digest[:24]}"
    ):
        raise FundamentalUniverseDiscoveryError("projection identity changed")
    _audit_source_capabilities(value.source_files)
    return value


_TERMINAL_FIELDS = {
    "schema",
    "contract_sha256",
    "source_scope_id",
    "availability_policy_id",
    "disposition",
    "refusal_reason",
    "decision_session",
    "decision_session_ordinal",
    "decision_open_utc",
    "source_ordinal",
    "qc_security_id",
    "cusip",
    "display_ticker_non_authoritative",
    "security_id",
    "issuer_id",
    "share_class_id",
    "listing_id",
    "morningstar_company_id",
    "morningstar_investment_id",
    "cik",
    "incorporation_country",
    "security_type_code",
    "primary_exchange_id",
    "primary_exchange_mic",
    "is_depositary_receipt",
    "is_primary_share",
    "common_share_sub_type",
    "delisting_date",
    "morningstar_sector_code",
    "morningstar_industry_group_code",
    "morningstar_industry_code",
    "period_end",
    "available_at",
    "shares_outstanding",
    "identity_evidence_sha256",
    "classification_evidence_sha256",
    "share_evidence_sha256",
    "terminal_sha256",
}
_REFUSAL_REASONS = {
    "missing_or_invalid_exact_qc_security_identifier",
    "missing_or_invalid_CUSIP_cross_vendor_join_key",
    "missing_or_invalid_identity_or_listing_field",
    "issuer_incorporation_country_is_not_USA",
    "security_type_is_not_Morningstar_common_stock",
    "security_is_a_depositary_receipt",
    "primary_exchange_outside_XASE_XNAS_XNYS",
    "missing_stable_Morningstar_company_id_and_CIK",
    "missing_or_invalid_Morningstar_classification",
    "missing_or_invalid_preopen_share_observation",
}
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")


def _optional_text(value: object, name: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise FundamentalUniverseDiscoveryError(f"{name} is not bounded text")
    return value


def _decimal_text(value: object, name: str, *, positive: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise FundamentalUniverseDiscoveryError(f"{name} is not decimal text")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is not decimal text") from exc
    if (
        not parsed.is_finite()
        or (positive and parsed <= 0)
        or ("0" if parsed == 0 else format(parsed, "f")) != value
    ):
        raise FundamentalUniverseDiscoveryError(f"{name} is not canonical Decimal")
    return value


def _validate_terminal(
    row: dict[str, object], geometry: Mapping[str, object]
) -> dict[str, object]:
    if (
        set(row) != _TERMINAL_FIELDS
        or row.get("schema") != TERMINAL_SCHEMA
        or row.get("contract_sha256") != CONTRACT_SHA256
        or row.get("source_scope_id") != SOURCE_SCOPE_ID
        or row.get("availability_policy_id") != AVAILABILITY_POLICY_ID
        or row.get("decision_session") != geometry["decision_session"]
        or row.get("decision_session_ordinal")
        != geometry["decision_session_ordinal"]
        or row.get("decision_open_utc") != geometry["decision_open_utc"]
        or type(row.get("source_ordinal")) is not int
        or row["source_ordinal"] < 0
    ):
        raise FundamentalUniverseDiscoveryError("terminal schema or geometry changed")
    semantic = dict(row)
    declared = _sha(semantic.pop("terminal_sha256"), "terminal hash")
    semantic["terminal_sha256"] = None
    if declared != hashlib.sha256(canonical_json_bytes(semantic)).hexdigest():
        raise FundamentalUniverseDiscoveryError("terminal semantic hash changed")
    disposition = row.get("disposition")
    if disposition not in ("accepted", "out_of_scope", "named_refusal"):
        raise FundamentalUniverseDiscoveryError("terminal disposition changed")
    if disposition == "accepted":
        if row.get("refusal_reason") is not None:
            raise FundamentalUniverseDiscoveryError("accepted terminal has a refusal")
    elif row.get("refusal_reason") not in _REFUSAL_REASONS:
        raise FundamentalUniverseDiscoveryError("terminal refusal reason changed")

    for name in (
        "qc_security_id",
        "cusip",
        "display_ticker_non_authoritative",
        "security_id",
        "issuer_id",
        "share_class_id",
        "listing_id",
        "morningstar_company_id",
        "morningstar_investment_id",
        "cik",
        "incorporation_country",
        "security_type_code",
        "primary_exchange_id",
        "primary_exchange_mic",
        "common_share_sub_type",
        "delisting_date",
        "period_end",
        "available_at",
        "shares_outstanding",
    ):
        _optional_text(row.get(name), name)
    for name in ("is_depositary_receipt", "is_primary_share"):
        if row.get(name) is not None and type(row[name]) is not bool:
            raise FundamentalUniverseDiscoveryError(f"{name} type changed")
    for name in (
        "morningstar_sector_code",
        "morningstar_industry_group_code",
        "morningstar_industry_code",
    ):
        if row.get(name) is not None and (
            type(row[name]) is not int or row[name] < 1
        ):
            raise FundamentalUniverseDiscoveryError(f"{name} type changed")
    for name in (
        "identity_evidence_sha256",
        "classification_evidence_sha256",
        "share_evidence_sha256",
    ):
        if row.get(name) is not None:
            _sha(row[name], name)

    if disposition == "accepted":
        for name in (
            "qc_security_id",
            "cusip",
            "security_id",
            "issuer_id",
            "share_class_id",
            "listing_id",
            "morningstar_investment_id",
            "incorporation_country",
            "security_type_code",
            "primary_exchange_id",
            "primary_exchange_mic",
            "period_end",
            "available_at",
            "shares_outstanding",
            "identity_evidence_sha256",
            "classification_evidence_sha256",
            "share_evidence_sha256",
        ):
            if row.get(name) is None:
                raise FundamentalUniverseDiscoveryError(
                    f"accepted terminal lacks {name}"
                )
        if _CUSIP.fullmatch(row["cusip"]) is None:
            raise FundamentalUniverseDiscoveryError("accepted CUSIP changed")
        if (
            row["incorporation_country"] != "USA"
            or row["security_type_code"] != "ST00000001"
            or row["primary_exchange_id"]
            not in {"ASE", "NAS", "NYS"}
            or row["primary_exchange_mic"]
            != {"ASE": "XASE", "NAS": "XNAS", "NYS": "XNYS"}[
                row["primary_exchange_id"]
            ]
            or row["is_depositary_receipt"] is not False
        ):
            raise FundamentalUniverseDiscoveryError(
                "accepted terminal is outside lane eligibility projection"
            )
        _date(row["period_end"], "fundamental period end")
        if row["delisting_date"] is not None:
            _date(row["delisting_date"], "delisting date")
        _decimal_text(row["shares_outstanding"], "shares outstanding", positive=True)
        expected_available = (
            _utc(geometry["decision_open_utc"], "decision open")
            - timedelta(microseconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if row["available_at"] != expected_available:
            raise FundamentalUniverseDiscoveryError(
                "conservative pre-open availability assignment changed"
            )
        identity = {
            key: row[key]
            for key in (
                "qc_security_id",
                "cusip",
                "security_id",
                "issuer_id",
                "share_class_id",
                "listing_id",
                "morningstar_company_id",
                "morningstar_investment_id",
                "cik",
                "incorporation_country",
                "security_type_code",
                "primary_exchange_id",
                "primary_exchange_mic",
                "is_depositary_receipt",
                "is_primary_share",
                "common_share_sub_type",
                "delisting_date",
            )
        }
        if row["identity_evidence_sha256"] != hashlib.sha256(
            canonical_json_bytes(identity)
        ).hexdigest():
            raise FundamentalUniverseDiscoveryError("identity evidence changed")
        classification = {
            "morningstar_sector_code": row["morningstar_sector_code"],
            "morningstar_industry_group_code": row[
                "morningstar_industry_group_code"
            ],
            "morningstar_industry_code": row["morningstar_industry_code"],
            "decision_session": row["decision_session"],
        }
        if row["classification_evidence_sha256"] != hashlib.sha256(
            canonical_json_bytes(classification)
        ).hexdigest():
            raise FundamentalUniverseDiscoveryError(
                "classification evidence changed"
            )
        shares = {
            "qc_security_id": row["qc_security_id"],
            "decision_session": row["decision_session"],
            "period_end": row["period_end"],
            "available_at": row["available_at"],
            "shares_outstanding": row["shares_outstanding"],
        }
        if row["share_evidence_sha256"] != hashlib.sha256(
            canonical_json_bytes(shares)
        ).hexdigest():
            raise FundamentalUniverseDiscoveryError("share evidence changed")
    return row


def _bounded_gzip(payload: bytes, expected_size: int, name: str) -> bytes:
    if (
        type(payload) is not bytes
        or len(payload) > MAX_COMPRESSED_SHARD_BYTES
        or type(expected_size) is not int
        or expected_size < 1
        or expected_size > MAX_UNCOMPRESSED_SHARD_BYTES
    ):
        raise FundamentalUniverseDiscoveryError(f"{name} exceeds a byte bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(expected_size + 1)
            extra = stream.read(1)
    except (OSError, EOFError) as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is not bounded gzip") from exc
    if len(raw) != expected_size or extra:
        raise FundamentalUniverseDiscoveryError(f"{name} raw size changed")
    if gzip.compress(raw, compresslevel=9, mtime=0) != payload:
        raise FundamentalUniverseDiscoveryError(
            f"{name} is not deterministic gzip-level9-mtime0"
        )
    return raw


@dataclasses.dataclass(frozen=True, slots=True)
class _ArchiveFileBinding:
    role: str
    ordinal: int | None
    object_store_key: str | None
    relative_path: str
    sha256: str
    byte_count: int
    stat_identity: tuple[int, int, int, int, int]


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedFundamentalDiscoveryTerminalShard:
    ordinal: int
    object_store_key: str
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    row_count: int
    canonical_json_lines: bytes = dataclasses.field(repr=False)


def _private_stat(path: Path, name: str, *, directory: bool) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} is unavailable") from exc
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_kind(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_mode & 0o077
    ):
        raise FundamentalUniverseDiscoveryError(
            f"{name} is not an owner-only regular {'directory' if directory else 'file'}"
        )
    return observed


def _stat_identity(observed: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        observed.st_dev,
        observed.st_ino,
        stat.S_IFMT(observed.st_mode),
        observed.st_size,
        observed.st_mtime_ns,
    )


def _read_private_file(path: Path, name: str, maximum: int) -> tuple[bytes, tuple[int, int, int, int, int]]:
    before = _private_stat(path, name, directory=False)
    if before.st_size < 1 or before.st_size > maximum:
        raise FundamentalUniverseDiscoveryError(f"{name} exceeds its byte bound")
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            payload = stream.read(maximum + 1)
            after_open = os.fstat(stream.fileno())
    except OSError as exc:
        raise FundamentalUniverseDiscoveryError(f"{name} could not be read") from exc
    after = _private_stat(path, name, directory=False)
    identity = _stat_identity(before)
    if (
        len(payload) != before.st_size
        or len(payload) > maximum
        or _stat_identity(opened) != identity
        or _stat_identity(after_open) != identity
        or _stat_identity(after) != identity
    ):
        raise FundamentalUniverseDiscoveryError(f"{name} changed while read")
    return payload, identity


def _shard_relative_path(ordinal: int, digest: str) -> str:
    _count(ordinal, "archive shard ordinal")
    _sha(digest, "archive shard hash")
    return f"{ARCHIVE_SHARD_DIRECTORY}/{ordinal:04d}-{digest}.jsonl.gz"


_DESCRIPTOR_FIELDS = {
    "schema",
    "ordinal",
    "first_session",
    "last_session",
    "object_store_key",
    "compression",
    "encoding",
    "compressed_sha256",
    "compressed_byte_count",
    "uncompressed_sha256",
    "uncompressed_byte_count",
    "row_count",
}
_CENSUS_FIELDS = {
    "schema",
    "contract_sha256",
    "decision_session",
    "decision_session_ordinal",
    "decision_open_utc",
    "qc_history_collection_time",
    "qc_history_collection_time_zone",
    "collection_observed_before_decision_open",
    "source_member_count",
    "terminal_count",
    "qc_sid_bound_count",
    "accepted_count",
    "out_of_scope_count",
    "named_refusal_count",
    "terminal_projection_sha256",
    "all_source_members_terminal",
    "outcome_access_performed",
    "price_or_return_access_performed",
}


def _artifact_projections(
    descriptor_hash: str, counts: Mapping[str, int]
) -> dict[str, dict[str, object]]:
    values = {
        "eligible_universe": (
            ELIGIBLE_UNIVERSE_ARTIFACT_SCHEMA,
            "accepted_terminal_rows_projected_to_identity_and_membership",
            counts["accepted_count"],
            "arv2-qc-fundamental-eligible-universe-",
        ),
        "qc_sid_mapping": (
            SID_MAPPING_ARTIFACT_SCHEMA,
            "all_non_null_qc_security_ids_with_terminal_disposition",
            counts["qc_sid_bound_count"],
            "arv2-qc-fundamental-sid-mapping-",
        ),
    }
    result = {}
    for role, (schema, selection, row_count, prefix) in values.items():
        projection = {
            "schema": schema,
            "selection": selection,
            "terminal_shard_inventory_sha256": descriptor_hash,
            "row_count": row_count,
        }
        payload = canonical_json_bytes(projection)
        digest = hashlib.sha256(payload).hexdigest()
        result[role] = {
            "artifact_id": prefix + digest[:24],
            "artifact_sha256": digest,
            "byte_count": len(payload),
            "row_count": row_count,
            "projection": projection,
        }
    return result


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedFundamentalUniverseDiscoveryReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    plan_id: str
    plan_sha256: str
    plan_artifact_sha256: str
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    output_manifest_id: str
    output_manifest_sha256: str
    output_manifest_byte_count: int
    output_manifest_bytes: bytes = dataclasses.field(repr=False)
    terminal_package_sha256: str
    terminal_package_byte_count: int
    terminal_shard_inventory_sha256: str
    terminal_shard_count: int
    first_session: str
    last_session: str
    decision_session_count: int
    source_member_count: int
    terminal_count: int
    qc_sid_mapping_row_count: int
    accepted_count: int
    out_of_scope_count: int
    named_refusal_count: int
    eligible_universe_artifact_id: str
    eligible_universe_artifact_sha256: str
    eligible_universe_artifact_byte_count: int
    eligible_universe_artifact_bytes: bytes = dataclasses.field(repr=False)
    qc_sid_mapping_artifact_id: str
    qc_sid_mapping_artifact_sha256: str
    qc_sid_mapping_artifact_byte_count: int
    qc_sid_mapping_artifact_bytes: bytes = dataclasses.field(repr=False)
    source_scope_id: str
    availability_policy_id: str
    full_pit_universe_established: bool
    full_market_peer_census_established: bool
    every_source_member_terminal_once: bool
    delisted_members_not_filtered: bool
    qc_history_collection_preopen_authenticated: bool
    current_ticker_used_as_identity: bool
    production_preopen_input_available: bool
    requires_cross_vendor_usd_fundamental_bridge: bool
    quantconnect_fundamentals_history_access_performed: bool
    private_object_store_read_write_performed: bool
    object_store_capacity_preflight_performed: bool
    provider_credentials_accessed: bool
    price_or_return_access_performed: bool
    outcome_access_performed: bool
    result_access_performed: bool
    orders_or_portfolio_actions_performed: bool
    deployment_or_trading_performed: bool
    _archive_root: Path = dataclasses.field(repr=False)
    _archive_root_stat: tuple[int, int, int, int, int] = dataclasses.field(repr=False)
    _archive_shard_directory_stat: tuple[int, int, int, int, int] = dataclasses.field(
        repr=False
    )
    _archive_files: tuple[_ArchiveFileBinding, ...] = dataclasses.field(repr=False)


_RECEIPTS: dict[
    int,
    tuple[
        weakref.ReferenceType[ReviewedFundamentalUniverseDiscoveryReceipt],
        tuple[object, ...],
    ],
] = {}
_RECEIPT_LOCK = threading.RLock()


def _receipt_fingerprint(
    value: ReviewedFundamentalUniverseDiscoveryReceipt,
) -> tuple[object, ...]:
    result = []
    for field in dataclasses.fields(value):
        item = getattr(value, field.name)
        if field.name == "_archive_files":
            if type(item) is not tuple or any(
                type(binding) is not _ArchiveFileBinding for binding in item
            ):
                return ("invalid-archive-file-topology",)
            result.append(
                tuple(
                    (
                        binding.role,
                        binding.ordinal,
                        binding.object_store_key,
                        binding.relative_path,
                        binding.sha256,
                        binding.byte_count,
                        binding.stat_identity,
                    )
                    for binding in item
                )
            )
        else:
            result.append(item)
    return tuple(result)


def _forget_receipt(
    identity: int,
    reference: weakref.ReferenceType[ReviewedFundamentalUniverseDiscoveryReceipt],
) -> None:
    with _RECEIPT_LOCK:
        current = _RECEIPTS.get(identity)
        if current is not None and current[0] is reference:
            _RECEIPTS.pop(identity, None)


def _validate_terminal_package(
    payload: bytes,
    *,
    manifest_payload: bytes,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    package = _strict_json(
        payload, "terminal package", maximum=MAX_TERMINAL_PACKAGE_BYTES
    )
    expected_fields = {
        "schema",
        "contract_sha256",
        "status",
        "output_manifest_key",
        "output_manifest_sha256",
        "output_manifest_byte_count",
        "decision_session_count",
        "source_member_count",
        "terminal_count",
        "accepted_count",
        "out_of_scope_count",
        "named_refusal_count",
        "outcome_access_performed",
        "price_or_return_access_performed",
        "orders_or_portfolio_actions_performed",
    }
    census = manifest["census"]
    manifest_hash = hashlib.sha256(manifest_payload).hexdigest()
    if (
        set(package) != expected_fields
        or package.get("schema") != TERMINAL_PACKAGE_SCHEMA
        or package.get("contract_sha256") != CONTRACT_SHA256
        or package.get("status") != "completed"
        or package.get("output_manifest_key")
        != OUTPUT_PREFIX + "manifests/" + manifest_hash + ".json"
        or package.get("output_manifest_sha256") != manifest_hash
        or package.get("output_manifest_byte_count") != len(manifest_payload)
        or package.get("decision_session_count")
        != census["decision_session_count"]
        or package.get("source_member_count") != census["source_member_count"]
        or package.get("terminal_count") != census["terminal_count"]
        or package.get("accepted_count") != census["accepted_count"]
        or package.get("out_of_scope_count") != census["out_of_scope_count"]
        or package.get("named_refusal_count") != census["named_refusal_count"]
        or package.get("outcome_access_performed") is not False
        or package.get("price_or_return_access_performed") is not False
        or package.get("orders_or_portfolio_actions_performed") is not False
    ):
        raise FundamentalUniverseDiscoveryError("terminal package binding changed")
    return package


def load_reviewed_fundamental_universe_discovery_receipt(
    *,
    plan_bytes: bytes,
    projection: FundamentalUniverseDiscoveryQcProjection,
    archive_root: Path,
) -> ReviewedFundamentalUniverseDiscoveryReceipt:
    """Stream one private archive shard at a time and mint the compact receipt."""

    projection = require_fundamental_universe_discovery_qc_projection(projection)
    if plan_bytes != projection.plan_bytes:
        raise FundamentalUniverseDiscoveryError("receipt plan differs from projection")
    plan = _validate_plan(plan_bytes)
    if not isinstance(archive_root, Path):
        raise FundamentalUniverseDiscoveryError("archive root must be a Path")
    try:
        requested_root = archive_root.absolute()
        requested_root_stat = requested_root.lstat()
        root = requested_root.resolve(strict=True)
    except OSError as exc:
        raise FundamentalUniverseDiscoveryError("archive root is unavailable") from exc
    # Reject a symlink supplied as the archive leaf without rejecting ordinary
    # platform aliases in an ancestor (for example macOS /var -> /private/var).
    if stat.S_ISLNK(requested_root_stat.st_mode):
        raise FundamentalUniverseDiscoveryError("archive root is a symlink")
    root_stat = _private_stat(root, "discovery archive root", directory=True)
    shard_directory = root / ARCHIVE_SHARD_DIRECTORY
    shard_directory_stat = _private_stat(
        shard_directory, "discovery shard directory", directory=True
    )
    output_manifest_bytes, manifest_stat = _read_private_file(
        root / ARCHIVE_MANIFEST_NAME,
        "discovery output manifest",
        MAX_OUTPUT_MANIFEST_BYTES,
    )
    terminal_package_bytes, package_stat = _read_private_file(
        root / ARCHIVE_PACKAGE_NAME,
        "discovery terminal package",
        MAX_TERMINAL_PACKAGE_BYTES,
    )
    archive_files = [
        _ArchiveFileBinding(
            role="output_manifest",
            ordinal=None,
            object_store_key=None,
            relative_path=ARCHIVE_MANIFEST_NAME,
            sha256=hashlib.sha256(output_manifest_bytes).hexdigest(),
            byte_count=len(output_manifest_bytes),
            stat_identity=manifest_stat,
        ),
        _ArchiveFileBinding(
            role="terminal_package",
            ordinal=None,
            object_store_key=projection.terminal_package_key,
            relative_path=ARCHIVE_PACKAGE_NAME,
            sha256=hashlib.sha256(terminal_package_bytes).hexdigest(),
            byte_count=len(terminal_package_bytes),
            stat_identity=package_stat,
        ),
    ]
    manifest = _strict_json(
        output_manifest_bytes,
        "output manifest",
        maximum=MAX_OUTPUT_MANIFEST_BYTES,
    )
    expected_manifest_fields = {
        "schema",
        "contract_sha256",
        "status",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "source_scope",
        "availability_policy",
        "first_session",
        "last_session",
        "decision_session_censuses",
        "terminal_shards",
        "terminal_shard_inventory_sha256",
        "artifact_projections",
        "census",
        "guarantees",
        "capabilities",
    }
    if (
        set(manifest) != expected_manifest_fields
        or manifest.get("schema") != OUTPUT_MANIFEST_SCHEMA
        or manifest.get("contract_sha256") != CONTRACT_SHA256
        or manifest.get("status") != "completed"
        or manifest.get("plan_id") != plan["plan_id"]
        or manifest.get("plan_sha256") != hashlib.sha256(plan_bytes).hexdigest()
        or manifest.get("project_source_set_sha256")
        != projection.project_source_set_sha256
        or manifest.get("source_scope")
        != fundamental_universe_discovery_contract_record()
        or manifest.get("availability_policy") != plan["availability_policy"]
        or manifest.get("first_session") != plan["first_session"]
        or manifest.get("last_session") != plan["last_session"]
    ):
        raise FundamentalUniverseDiscoveryError("output manifest lineage changed")

    descriptors = manifest["terminal_shards"]
    if (
        type(descriptors) is not list
        or not len(plan["history_chunks"]) <= len(descriptors) <= len(
            plan["decision_sessions"]
        )
        or len(descriptors) > MAX_TERMINAL_SHARDS
    ):
        raise FundamentalUniverseDiscoveryError("terminal shard inventory changed")
    descriptor_hash = hashlib.sha256(canonical_json_bytes(descriptors)).hexdigest()
    if manifest.get("terminal_shard_inventory_sha256") != descriptor_hash:
        raise FundamentalUniverseDiscoveryError("terminal shard inventory hash changed")

    geometries = {
        item["decision_session"]: item for item in plan["decision_sessions"]
    }
    declared_censuses = manifest["decision_session_censuses"]
    if type(declared_censuses) is not list or len(declared_censuses) != len(geometries):
        raise FundamentalUniverseDiscoveryError("session census inventory changed")
    census_by_session = {}
    for census in declared_censuses:
        if (
            type(census) is not dict
            or set(census) != _CENSUS_FIELDS
            or census.get("schema") != CENSUS_SCHEMA
            or census.get("contract_sha256") != CONTRACT_SHA256
            or census.get("decision_session") not in geometries
            or census.get("decision_session") in census_by_session
            or census.get("decision_session_ordinal")
            != geometries[census["decision_session"]]["decision_session_ordinal"]
            or census.get("decision_open_utc")
            != geometries[census["decision_session"]]["decision_open_utc"]
            or census.get("qc_history_collection_time_zone")
            != "America/New_York"
            or census.get("collection_observed_before_decision_open") is not True
            or census.get("all_source_members_terminal") is not True
            or census.get("outcome_access_performed") is not False
            or census.get("price_or_return_access_performed") is not False
        ):
            raise FundamentalUniverseDiscoveryError("session census schema changed")
        _history_collection_time(
            census.get("qc_history_collection_time"),
            session=_date(census["decision_session"], "census decision session"),
            name="QC history collection time",
        )
        for name in (
            "source_member_count",
            "terminal_count",
            "qc_sid_bound_count",
            "accepted_count",
            "out_of_scope_count",
            "named_refusal_count",
        ):
            _count(
                census.get(name),
                "session " + name,
                minimum=1 if name in {"source_member_count", "terminal_count"} else 0,
            )
        _sha(census.get("terminal_projection_sha256"), "terminal projection")
        census_by_session[census["decision_session"]] = census
    if list(census_by_session) != sorted(geometries):
        raise FundamentalUniverseDiscoveryError(
            "session censuses repeat or are not canonically ordered"
        )

    aggregate = {
        name: 0
        for name in (
            "source_member_count",
            "terminal_count",
            "qc_sid_bound_count",
            "accepted_count",
            "out_of_scope_count",
            "named_refusal_count",
        )
    }
    total_compressed = 0
    session_order = list(geometries)
    session_index = {session: index for index, session in enumerate(session_order)}
    chunk_ordinal_by_session = {
        session: chunk["ordinal"]
        for chunk in plan["history_chunks"]
        for session in chunk["decision_sessions"]
    }
    terminalled_sessions: set[str] = set()
    next_session_index = 0
    for expected_ordinal, descriptor in enumerate(descriptors):
        if (
            type(descriptor) is not dict
            or set(descriptor) != _DESCRIPTOR_FIELDS
            or descriptor.get("schema") != OUTPUT_SHARD_SCHEMA
            or descriptor.get("ordinal") != expected_ordinal
            or descriptor.get("first_session") not in geometries
            or descriptor.get("last_session") not in geometries
            or descriptor.get("compression") != "gzip-level9-mtime0"
            or descriptor.get("encoding") != "canonical-json-lines-utf8-lf"
        ):
            raise FundamentalUniverseDiscoveryError("terminal shard descriptor changed")
        first_index = session_index[descriptor["first_session"]]
        last_index = session_index[descriptor["last_session"]]
        if (
            first_index != next_session_index
            or first_index > last_index
            or chunk_ordinal_by_session[descriptor["first_session"]]
            != chunk_ordinal_by_session[descriptor["last_session"]]
        ):
            raise FundamentalUniverseDiscoveryError(
                "terminal shard session interval changed"
            )
        descriptor_sessions = session_order[first_index : last_index + 1]
        if terminalled_sessions.intersection(descriptor_sessions):
            raise FundamentalUniverseDiscoveryError(
                "a decision session appears in more than one terminal shard"
            )
        key = _safe_key(descriptor["object_store_key"], "terminal shard key")
        relative_path = _shard_relative_path(
            expected_ordinal, descriptor["compressed_sha256"]
        )
        payload, shard_stat = _read_private_file(
            root / relative_path,
            "terminal shard",
            MAX_COMPRESSED_SHARD_BYTES,
        )
        archive_files.append(
            _ArchiveFileBinding(
                role="terminal_shard",
                ordinal=expected_ordinal,
                object_store_key=key,
                relative_path=relative_path,
                sha256=descriptor["compressed_sha256"],
                byte_count=descriptor["compressed_byte_count"],
                stat_identity=shard_stat,
            )
        )
        compressed_size = _count(
            descriptor["compressed_byte_count"], "compressed bytes", minimum=1
        )
        raw_size = _count(
            descriptor["uncompressed_byte_count"], "uncompressed bytes", minimum=1
        )
        row_count = _count(descriptor["row_count"], "shard rows", minimum=1)
        if row_count > MAX_SHARD_ROWS:
            raise FundamentalUniverseDiscoveryError("terminal shard row cap exceeded")
        if (
            compressed_size != len(payload)
            or compressed_size > MAX_COMPRESSED_SHARD_BYTES
            or descriptor["compressed_sha256"]
            != hashlib.sha256(payload).hexdigest()
            or key
            != OUTPUT_PREFIX
            + "terminal-shards/"
            + hashlib.sha256(plan_bytes).hexdigest()
            + "/"
            + descriptor["compressed_sha256"]
            + ".jsonl.gz"
        ):
            raise FundamentalUniverseDiscoveryError("terminal shard identity changed")
        raw = _bounded_gzip(payload, raw_size, "terminal shard")
        if descriptor["uncompressed_sha256"] != hashlib.sha256(raw).hexdigest():
            raise FundamentalUniverseDiscoveryError("terminal shard raw hash changed")
        total_compressed += len(payload)
        if total_compressed > MAX_TOTAL_COMPRESSED_OUTPUT_BYTES:
            raise FundamentalUniverseDiscoveryError("total output byte cap exceeded")

        shard_sessions = set(descriptor_sessions)
        rows_by_session: dict[str, list[dict[str, object]]] = {
            session: [] for session in descriptor_sessions
        }
        lines = raw.splitlines(keepends=True)
        if len(lines) != row_count:
            raise FundamentalUniverseDiscoveryError("terminal shard row count changed")
        previous_key = None
        for line in lines:
            row = _strict_json(line, "terminal row", maximum=16 * 1024)
            session = row.get("decision_session")
            if session not in shard_sessions:
                raise FundamentalUniverseDiscoveryError(
                    "terminal escaped its declared shard interval"
                )
            row = _validate_terminal(row, geometries[session])
            order_key = (session, row["source_ordinal"])
            if previous_key is not None and order_key <= previous_key:
                raise FundamentalUniverseDiscoveryError(
                    "terminal shard rows repeat or are not ordered"
                )
            previous_key = order_key
            rows_by_session[session].append(row)

        for session in descriptor_sessions:
            rows = rows_by_session[session]
            census = census_by_session[session]
            ordinals = [row["source_ordinal"] for row in rows]
            if ordinals != list(range(len(rows))):
                raise FundamentalUniverseDiscoveryError(
                    "source-member terminal ordinals are not exhaustive"
                )
            sids = [
                row["qc_security_id"]
                for row in rows
                if row["qc_security_id"] is not None
            ]
            if len(sids) != len(set(sids)):
                raise FundamentalUniverseDiscoveryError(
                    "session repeats a QC SecurityIdentifier"
                )
            actual = {
                "source_member_count": len(rows),
                "terminal_count": len(rows),
                "qc_sid_bound_count": len(sids),
                "accepted_count": sum(
                    row["disposition"] == "accepted" for row in rows
                ),
                "out_of_scope_count": sum(
                    row["disposition"] == "out_of_scope" for row in rows
                ),
                "named_refusal_count": sum(
                    row["disposition"] == "named_refusal" for row in rows
                ),
            }
            projection_hash = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "domain": "arv2-qc-fundamental-session-terminals-v1",
                        "terminal_sha256s_in_source_order": [
                            row["terminal_sha256"] for row in rows
                        ],
                    }
                )
            ).hexdigest()
            if any(census[name] != count for name, count in actual.items()) or (
                census["terminal_projection_sha256"] != projection_hash
            ):
                raise FundamentalUniverseDiscoveryError(
                    "session terminal census differs from physical shard"
                )
            for name, count in actual.items():
                aggregate[name] += count
        terminalled_sessions.update(descriptor_sessions)
        next_session_index = last_index + 1

    if terminalled_sessions != set(geometries):
        raise FundamentalUniverseDiscoveryError(
            "terminal shards do not cover every requested decision session"
        )

    expected_shard_names = {
        Path(binding.relative_path).name
        for binding in archive_files
        if binding.role == "terminal_shard"
    }
    try:
        root_names = {item.name for item in root.iterdir()}
        shard_names = {item.name for item in shard_directory.iterdir()}
    except OSError as exc:
        raise FundamentalUniverseDiscoveryError(
            "discovery archive inventory could not be read"
        ) from exc
    if root_names != {
        ARCHIVE_MANIFEST_NAME,
        ARCHIVE_PACKAGE_NAME,
        ARCHIVE_SHARD_DIRECTORY,
    } or shard_names != expected_shard_names:
        raise FundamentalUniverseDiscoveryError(
            "discovery archive has an extra, missing, or renamed file"
        )

    census = manifest["census"]
    expected_census_fields = {
        "decision_session_count",
        "history_call_count",
        "terminal_shard_count",
        *aggregate,
    }
    if type(census) is not dict or set(census) != expected_census_fields:
        raise FundamentalUniverseDiscoveryError("aggregate census fields changed")
    if (
        census.get("decision_session_count") != len(geometries)
        or census.get("history_call_count") != len(plan["history_chunks"])
        or census.get("terminal_shard_count") != len(descriptors)
        or any(census.get(name) != count for name, count in aggregate.items())
        or aggregate["source_member_count"] != aggregate["terminal_count"]
        or aggregate["terminal_count"]
        != aggregate["accepted_count"]
        + aggregate["out_of_scope_count"]
        + aggregate["named_refusal_count"]
        or aggregate["source_member_count"] > MAX_TOTAL_SOURCE_ROWS
    ):
        raise FundamentalUniverseDiscoveryError("aggregate terminal census changed")

    expected_projections = _artifact_projections(descriptor_hash, aggregate)
    if manifest.get("artifact_projections") != expected_projections:
        raise FundamentalUniverseDiscoveryError("artifact projections changed")
    expected_guarantees = {
        "every_requested_session_observed_once": True,
        "every_source_member_terminal_once": True,
        "every_collection_observed_before_decision_open": True,
        "exact_qc_sid_bound_when_source_exposes_sid": True,
        "delisted_members_not_filtered": True,
        "current_ticker_used_as_identity": False,
        "full_pit_universe_established_within_qc_source_scope": True,
        "full_market_peer_census_established_with_terminal_refusals": True,
        "morningstar_publication_timestamp_established": False,
        "vendor_revision_or_tombstone_history_established": False,
        "off_qc_security_master_established": False,
        "production_preopen_input_available": False,
        "USD_statement_facts_established": False,
        "actual_prior_fiscal_year_revenue_established": False,
    }
    expected_capabilities = {
        "quantconnect_fundamentals_history_access_performed": True,
        "private_object_store_read_write_performed": True,
        "object_store_capacity_preflight_performed": True,
        "provider_credentials_accessed": False,
        "price_or_return_access_performed": False,
        "outcome_access_performed": False,
        "result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "deployment_or_trading_performed": False,
    }
    if (
        manifest.get("guarantees") != expected_guarantees
        or manifest.get("capabilities") != expected_capabilities
    ):
        raise FundamentalUniverseDiscoveryError(
            "discovery guarantees or capability receipt changed"
        )
    _validate_terminal_package(
        terminal_package_bytes,
        manifest_payload=output_manifest_bytes,
        manifest=manifest,
    )

    universe = expected_projections["eligible_universe"]
    sid_mapping = expected_projections["qc_sid_mapping"]
    universe_bytes = canonical_json_bytes(universe["projection"])
    sid_bytes = canonical_json_bytes(sid_mapping["projection"])
    output_hash = hashlib.sha256(output_manifest_bytes).hexdigest()
    record = {
        "schema": RECEIPT_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_artifact_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "output_manifest_id": "arv2-qc-fundamental-output-" + output_hash[:24],
        "output_manifest_sha256": output_hash,
        "output_manifest_byte_count": len(output_manifest_bytes),
        "terminal_package_sha256": hashlib.sha256(
            terminal_package_bytes
        ).hexdigest(),
        "terminal_package_byte_count": len(terminal_package_bytes),
        "terminal_shard_inventory_sha256": descriptor_hash,
        "terminal_shard_count": len(descriptors),
        "first_session": plan["first_session"],
        "last_session": plan["last_session"],
        "decision_session_count": census["decision_session_count"],
        "source_member_count": census["source_member_count"],
        "terminal_count": census["terminal_count"],
        "qc_sid_mapping_row_count": census["qc_sid_bound_count"],
        "accepted_count": census["accepted_count"],
        "out_of_scope_count": census["out_of_scope_count"],
        "named_refusal_count": census["named_refusal_count"],
        "eligible_universe_artifact_id": universe["artifact_id"],
        "eligible_universe_artifact_sha256": universe["artifact_sha256"],
        "eligible_universe_artifact_byte_count": universe["byte_count"],
        "qc_sid_mapping_artifact_id": sid_mapping["artifact_id"],
        "qc_sid_mapping_artifact_sha256": sid_mapping["artifact_sha256"],
        "qc_sid_mapping_artifact_byte_count": sid_mapping["byte_count"],
        "source_scope_id": SOURCE_SCOPE_ID,
        "availability_policy_id": AVAILABILITY_POLICY_ID,
        "full_pit_universe_established": True,
        "full_market_peer_census_established": True,
        "every_source_member_terminal_once": True,
        "delisted_members_not_filtered": True,
        "qc_history_collection_preopen_authenticated": True,
        "current_ticker_used_as_identity": False,
        "production_preopen_input_available": False,
        "requires_cross_vendor_usd_fundamental_bridge": True,
        **expected_capabilities,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(ReviewedFundamentalUniverseDiscoveryReceipt)
    fields = {
        **record,
        "receipt_id": "arv2-reviewed-qc-fundamental-discovery-" + digest[:24],
        "receipt_sha256": digest,
        "output_manifest_bytes": bytes(output_manifest_bytes),
        "eligible_universe_artifact_bytes": universe_bytes,
        "qc_sid_mapping_artifact_bytes": sid_bytes,
        "_archive_root": root,
        "_archive_root_stat": _stat_identity(root_stat),
        "_archive_shard_directory_stat": _stat_identity(shard_directory_stat),
        "_archive_files": tuple(archive_files),
    }
    expected = {field.name for field in dataclasses.fields(value)}
    if set(fields) != expected:
        raise FundamentalUniverseDiscoveryError("receipt field inventory changed")
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    fingerprint = _receipt_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(value, lambda ref: _forget_receipt(identity, ref))
    with _RECEIPT_LOCK:
        _RECEIPTS[identity] = (reference, fingerprint)
    return require_reviewed_fundamental_universe_discovery_receipt(value)


def _receipt_record(
    value: ReviewedFundamentalUniverseDiscoveryReceipt,
) -> dict[str, object]:
    excluded = {
        "receipt_id",
        "receipt_sha256",
        "output_manifest_bytes",
        "eligible_universe_artifact_bytes",
        "qc_sid_mapping_artifact_bytes",
        "_archive_root",
        "_archive_root_stat",
        "_archive_shard_directory_stat",
        "_archive_files",
    }
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in excluded
    }


def require_reviewed_fundamental_universe_discovery_receipt(
    value: ReviewedFundamentalUniverseDiscoveryReceipt,
) -> ReviewedFundamentalUniverseDiscoveryReceipt:
    """Reauthenticate the typed affirmative boundary without performing I/O."""

    if type(value) is not ReviewedFundamentalUniverseDiscoveryReceipt:
        raise FundamentalUniverseDiscoveryError("discovery receipt type changed")
    with _RECEIPT_LOCK:
        state = _RECEIPTS.get(id(value))
    if (
        state is None
        or state[0]() is not value
        or state[1] != _receipt_fingerprint(value)
    ):
        raise FundamentalUniverseDiscoveryError(
            "discovery receipt is not loader-authenticated"
        )
    if not isinstance(value._archive_root, Path):
        raise FundamentalUniverseDiscoveryError("receipt archive root changed")
    if (
        _stat_identity(
            _private_stat(
                value._archive_root, "discovery archive root", directory=True
            )
        )
        != value._archive_root_stat
        or _stat_identity(
            _private_stat(
                value._archive_root / ARCHIVE_SHARD_DIRECTORY,
                "discovery shard directory",
                directory=True,
            )
        )
        != value._archive_shard_directory_stat
    ):
        raise FundamentalUniverseDiscoveryError(
            "discovery archive directory identity changed"
        )
    for binding in value._archive_files:
        if type(binding) is not _ArchiveFileBinding:
            raise FundamentalUniverseDiscoveryError("archive binding type changed")
        path = value._archive_root / binding.relative_path
        if _stat_identity(_private_stat(path, binding.role, directory=False)) != (
            binding.stat_identity
        ):
            raise FundamentalUniverseDiscoveryError(
                "discovery archive file identity changed"
            )
    for name in (
        "full_pit_universe_established",
        "full_market_peer_census_established",
        "every_source_member_terminal_once",
        "delisted_members_not_filtered",
        "qc_history_collection_preopen_authenticated",
        "current_ticker_used_as_identity",
        "production_preopen_input_available",
        "requires_cross_vendor_usd_fundamental_bridge",
        "quantconnect_fundamentals_history_access_performed",
        "private_object_store_read_write_performed",
        "object_store_capacity_preflight_performed",
        "provider_credentials_accessed",
        "price_or_return_access_performed",
        "outcome_access_performed",
        "result_access_performed",
        "orders_or_portfolio_actions_performed",
        "deployment_or_trading_performed",
    ):
        if type(getattr(value, name)) is not bool:
            raise FundamentalUniverseDiscoveryError(f"receipt {name} type changed")
    if (
        value.schema != RECEIPT_SCHEMA
        or value.source_scope_id != SOURCE_SCOPE_ID
        or value.availability_policy_id != AVAILABILITY_POLICY_ID
        or value.full_pit_universe_established is not True
        or value.full_market_peer_census_established is not True
        or value.every_source_member_terminal_once is not True
        or value.delisted_members_not_filtered is not True
        or value.qc_history_collection_preopen_authenticated is not True
        or value.current_ticker_used_as_identity is not False
        or value.production_preopen_input_available is not False
        or value.requires_cross_vendor_usd_fundamental_bridge is not True
        or value.quantconnect_fundamentals_history_access_performed is not True
        or value.private_object_store_read_write_performed is not True
        or value.object_store_capacity_preflight_performed is not True
        or value.provider_credentials_accessed is not False
        or value.price_or_return_access_performed is not False
        or value.outcome_access_performed is not False
        or value.result_access_performed is not False
        or value.orders_or_portfolio_actions_performed is not False
        or value.deployment_or_trading_performed is not False
    ):
        raise FundamentalUniverseDiscoveryError("receipt authority boundary changed")
    for name in (
        "output_manifest_byte_count",
        "terminal_package_byte_count",
        "terminal_shard_count",
        "decision_session_count",
        "source_member_count",
        "terminal_count",
        "qc_sid_mapping_row_count",
        "accepted_count",
        "out_of_scope_count",
        "named_refusal_count",
        "eligible_universe_artifact_byte_count",
        "qc_sid_mapping_artifact_byte_count",
    ):
        _count(getattr(value, name), name)
    if (
        value.output_manifest_byte_count != len(value.output_manifest_bytes)
        or value.output_manifest_sha256
        != hashlib.sha256(value.output_manifest_bytes).hexdigest()
        or value.eligible_universe_artifact_byte_count
        != len(value.eligible_universe_artifact_bytes)
        or value.eligible_universe_artifact_sha256
        != hashlib.sha256(value.eligible_universe_artifact_bytes).hexdigest()
        or value.qc_sid_mapping_artifact_byte_count
        != len(value.qc_sid_mapping_artifact_bytes)
        or value.qc_sid_mapping_artifact_sha256
        != hashlib.sha256(value.qc_sid_mapping_artifact_bytes).hexdigest()
        or value.source_member_count != value.terminal_count
        or value.terminal_count
        != value.accepted_count
        + value.out_of_scope_count
        + value.named_refusal_count
    ):
        raise FundamentalUniverseDiscoveryError("receipt content census changed")
    universe = _strict_json(
        value.eligible_universe_artifact_bytes,
        "eligible-universe projection",
        maximum=MAX_TERMINAL_PACKAGE_BYTES,
    )
    sid_mapping = _strict_json(
        value.qc_sid_mapping_artifact_bytes,
        "QC SID projection",
        maximum=MAX_TERMINAL_PACKAGE_BYTES,
    )
    if (
        universe.get("schema") != ELIGIBLE_UNIVERSE_ARTIFACT_SCHEMA
        or universe.get("row_count") != value.accepted_count
        or universe.get("terminal_shard_inventory_sha256")
        != value.terminal_shard_inventory_sha256
        or value.eligible_universe_artifact_id
        != "arv2-qc-fundamental-eligible-universe-"
        + value.eligible_universe_artifact_sha256[:24]
        or sid_mapping.get("schema") != SID_MAPPING_ARTIFACT_SCHEMA
        or sid_mapping.get("row_count") != value.qc_sid_mapping_row_count
        or sid_mapping.get("terminal_shard_inventory_sha256")
        != value.terminal_shard_inventory_sha256
        or value.qc_sid_mapping_artifact_id
        != "arv2-qc-fundamental-sid-mapping-"
        + value.qc_sid_mapping_artifact_sha256[:24]
    ):
        raise FundamentalUniverseDiscoveryError("receipt artifact binding changed")
    record = _receipt_record(value)
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        value.receipt_sha256 != digest
        or value.receipt_id
        != "arv2-reviewed-qc-fundamental-discovery-" + digest[:24]
    ):
        raise FundamentalUniverseDiscoveryError("receipt identity changed")
    return value


def iter_reviewed_fundamental_discovery_terminal_shards(
    value: ReviewedFundamentalUniverseDiscoveryReceipt,
):
    """Yield one reauthenticated uncompressed terminal shard at a time.

    The iterator itself never retains more than one compressed payload and one
    corresponding bounded uncompressed payload.  A caller can stream its JSON
    lines into a later CUSIP/SID-to-Sharadar bridge without materializing the
    full multi-year census.
    """

    value = require_reviewed_fundamental_universe_discovery_receipt(value)
    manifest = _strict_json(
        value.output_manifest_bytes,
        "receipt output manifest",
        maximum=MAX_OUTPUT_MANIFEST_BYTES,
    )
    descriptors = manifest["terminal_shards"]
    bindings = {
        binding.ordinal: binding
        for binding in value._archive_files
        if binding.role == "terminal_shard"
    }
    if set(bindings) != set(range(len(descriptors))):
        raise FundamentalUniverseDiscoveryError(
            "receipt shard archive binding inventory changed"
        )
    for ordinal, descriptor in enumerate(descriptors):
        value = require_reviewed_fundamental_universe_discovery_receipt(value)
        binding = bindings[ordinal]
        if (
            binding.object_store_key != descriptor["object_store_key"]
            or binding.sha256 != descriptor["compressed_sha256"]
            or binding.byte_count != descriptor["compressed_byte_count"]
            or binding.relative_path
            != _shard_relative_path(ordinal, descriptor["compressed_sha256"])
        ):
            raise FundamentalUniverseDiscoveryError(
                "receipt shard archive binding changed"
            )
        payload, observed_stat = _read_private_file(
            value._archive_root / binding.relative_path,
            "receipt terminal shard",
            MAX_COMPRESSED_SHARD_BYTES,
        )
        if (
            observed_stat != binding.stat_identity
            or len(payload) != binding.byte_count
            or hashlib.sha256(payload).hexdigest() != binding.sha256
        ):
            raise FundamentalUniverseDiscoveryError(
                "receipt terminal shard content changed"
            )
        raw = _bounded_gzip(
            payload,
            descriptor["uncompressed_byte_count"],
            "receipt terminal shard",
        )
        if (
            hashlib.sha256(raw).hexdigest()
            != descriptor["uncompressed_sha256"]
            or len(raw.splitlines(keepends=True)) != descriptor["row_count"]
        ):
            raise FundamentalUniverseDiscoveryError(
                "receipt terminal shard raw content changed"
            )
        yield ReviewedFundamentalDiscoveryTerminalShard(
            ordinal=ordinal,
            object_store_key=binding.object_store_key,
            compressed_sha256=binding.sha256,
            compressed_byte_count=binding.byte_count,
            uncompressed_sha256=descriptor["uncompressed_sha256"],
            uncompressed_byte_count=descriptor["uncompressed_byte_count"],
            row_count=descriptor["row_count"],
            canonical_json_lines=raw,
        )


def fundamental_discovery_artifact_binding_record(
    value: ReviewedFundamentalUniverseDiscoveryReceipt,
) -> dict[str, object]:
    """Return compact bindings for the later cross-vendor physical composer."""

    value = require_reviewed_fundamental_universe_discovery_receipt(value)
    return {
        "schema": "arv2-qc-fundamental-discovery-artifact-bindings-v1",
        "receipt_id": value.receipt_id,
        "receipt_sha256": value.receipt_sha256,
        "source_scope_id": value.source_scope_id,
        "terminal_shard_inventory_sha256": value.terminal_shard_inventory_sha256,
        "eligible_universe_source": {
            "artifact_id": value.eligible_universe_artifact_id,
            "content_sha256": value.eligible_universe_artifact_sha256,
            "artifact_sha256": value.eligible_universe_artifact_sha256,
            "byte_count": value.eligible_universe_artifact_byte_count,
            "row_count": value.accepted_count,
            "content_is_projection_manifest": True,
        },
        "qc_sid_mapping_source": {
            "artifact_id": value.qc_sid_mapping_artifact_id,
            "content_sha256": value.qc_sid_mapping_artifact_sha256,
            "artifact_sha256": value.qc_sid_mapping_artifact_sha256,
            "byte_count": value.qc_sid_mapping_artifact_byte_count,
            "row_count": value.qc_sid_mapping_row_count,
            "content_is_projection_manifest": True,
        },
        "full_pit_universe_established": True,
        "full_market_peer_census_established": True,
        "qc_history_collection_preopen_authenticated": True,
        "production_preopen_input_available": False,
        "requires_cross_vendor_usd_fundamental_bridge": True,
        "outcome_access_performed": False,
    }


__all__ = [
    "ARCHIVE_MANIFEST_NAME",
    "ARCHIVE_PACKAGE_NAME",
    "ARCHIVE_SHARD_DIRECTORY",
    "AVAILABILITY_POLICY_ID",
    "BACKTEST_NAME",
    "CONTRACT_ID",
    "CONTRACT_SHA256",
    "ENTRY_PATH",
    "FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT",
    "FORMAL_SOURCE_AXIS_FIRST_SESSION",
    "FORMAL_SOURCE_AXIS_LAST_SESSION",
    "FundamentalDiscoveryProjectSource",
    "FundamentalUniverseDiscoveryError",
    "FundamentalUniverseDiscoveryQcProjection",
    "HISTORY_CHUNK_SESSION_COUNT",
    "MAX_COLLECTION_ROWS",
    "MAX_DECISION_SESSIONS",
    "MAX_HISTORY_CALLS",
    "MAX_TOTAL_SOURCE_ROWS",
    "PLAN_SCHEMA",
    "PROJECT_NAME",
    "RECEIPT_SCHEMA",
    "RUNTIME_PATH",
    "ReviewedFundamentalDiscoveryTerminalShard",
    "ReviewedFundamentalUniverseDiscoveryReceipt",
    "SOURCE_SCOPE_ID",
    "SUMMARY_NAME",
    "TERMINAL_SCHEMA",
    "WORKER_PATH",
    "build_fundamental_universe_discovery_plan_bytes",
    "build_fundamental_universe_discovery_qc_projection",
    "canonical_json_bytes",
    "fundamental_discovery_artifact_binding_record",
    "fundamental_universe_discovery_contract_record",
    "iter_reviewed_fundamental_discovery_terminal_shards",
    "load_reviewed_fundamental_universe_discovery_receipt",
    "render_fundamental_universe_discovery_contract_bytes",
    "require_fundamental_universe_discovery_qc_projection",
    "require_reviewed_fundamental_universe_discovery_receipt",
]
