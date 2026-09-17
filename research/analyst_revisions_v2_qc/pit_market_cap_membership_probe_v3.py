"""Pure contract and reviewed count receipt for the ARV2 PIT coverage probe.

The builder emits exactly two small QuantConnect project files.  The cloud
runtime may inspect Morningstar ``market_cap`` and the point-in-time
constituents of SPY, QQQ, and SOXX, but it may persist only bounded counts.
This module performs no network, credential, QuantConnect, market, or result
I/O.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Sequence
from data.exchange_calendar import is_trading_session, session_open_instant


class PitMarketCapMembershipProbeError(ValueError):
    """The probe plan, projection, or terminal receipt is invalid."""


CONTRACT_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-contract-v3"
PLAN_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-plan-v3"
PROJECTION_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-projection-v3"
SOURCE_FILE_SCHEMA = "arv2-qc-pit-market-cap-membership-project-source-v1"
RECEIPT_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-receipt-v3"
TERMINAL_POINTER_SCHEMA = (
    "arv2-qc-pit-market-cap-membership-coverage-terminal-v3"
)
FAILURE_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-failure-v3"
ATTESTATION_SCHEMA = (
    "arv2-qc-pit-market-cap-membership-coverage-attestation-v3"
)

PROJECT_NAME = (
    "31 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_V3 - 20260917"
)
BACKTEST_NAME = (
    "ARV2 v3 outcome-free PIT market-cap and ETF-membership summary"
)
ENTRY_PATH = "main.py"
RUNTIME_PATH = "pit_market_cap_membership_probe_runtime_v3.py"
RUNTIME_TEMPLATE_SHA256 = (
    "2ffdfa019627b50472b3d9f6eeeaad9447e147bc2b63ffb84cbe82fba62340e0"
)
RUNTIME_RENDERED_SHA256 = (
    "238c69c01009e71187162da3ff67370d23b577460164ff8820bccc02a0480b27"
)
SUMMARY_NAME = "ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE_V3"
INPUT_PREFIX = "arv2/pit-market-cap-membership-coverage-v3/input/"
OUTPUT_PREFIX = "arv2/pit-market-cap-membership-coverage-v3/output/"
ETFS = ("SPY", "QQQ", "SOXX")

MAX_PROJECT_SOURCE_CHARACTERS = 60_000
MAX_PLAN_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_TERMINAL_POINTER_BYTES = 64 * 1024
MAX_DECISION_SESSIONS = 128
MAX_HISTORY_CHUNKS = 64
HISTORY_CHUNK_SESSION_COUNT = 4
HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS = 45
MAX_COLLECTIONS_PER_CALL = 64
MAX_COLLECTION_ROWS = 25_000
MAX_TOTAL_SOURCE_ROWS = 20_000_000
EXPECTED_CANARY_SESSION_COUNT = 16
MAX_SUMMARY_CHARACTERS = 4096

_MARKER = "__ARV2_PIT_MARKET_CAP_MEMBERSHIP_V3_CONTRACT_SHA256__"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PitMarketCapMembershipProbeError(
            "value is not canonical ASCII JSON"
        ) from exc


def pit_market_cap_membership_contract_record() -> dict[str, object]:
    """Return the narrow capability and availability contract."""

    return {
        "schema": CONTRACT_SCHEMA,
        "purpose": (
            "outcome-free physical coverage evidence for a later, separately "
            "preregistered market-cap and ETF-membership stock evaluation"
        ),
        "sources": {
            "fundamentals": {
                "provider": "QuantConnect",
                "dataset": "Morningstar US Fundamentals",
                "request": "History(fundamental_universe,start,end,flatten=False)",
                "field": "market_cap",
                "identity": "exact string form of QC SecurityIdentifier",
                "point_in_time": True,
                "duplicate_exact_sid_policy": (
                    "collapse repeated rows only when every row has the same "
                    "positive, null, nonpositive, or invalid coverage class"
                ),
                "coverage_class_definitions": {
                    "positive": "finite Decimal(str(value)) greater than zero",
                    "null": "market_cap attribute absent or value is None",
                    "nonpositive": (
                        "finite Decimal(str(value)) less than or equal to zero"
                    ),
                    "invalid": (
                        "Decimal(str(value)) conversion fails or is non-finite"
                    ),
                },
                "duplicate_classification_conflict": "named refusal",
                "duplicate_market_cap_values_compared_with_each_other": False,
                "duplicate_market_cap_values_emitted": False,
                "duplicate_value_equivalence_established": False,
                "production_market_cap_value_selection_authorized": False,
            },
            "etf_membership": {
                "provider": "QuantConnect",
                "dataset": "ETF constituent universe history",
                "tickers": list(ETFS),
                "request": "History(etf_universe,start,end,flatten=False)",
                "identity": "exact string form of QC SecurityIdentifier",
                "positive_weight_only": True,
                "duplicate_exact_sid_policy": "named refusal",
                "last_update_read": False,
            },
        },
        "availability": {
            "timezone": "America/New_York",
            "decision_clock": "09:30:00 local market open",
            "fundamental_snapshot": "latest collection strictly before open",
            "constituent_snapshot": (
                "latest history Series collection timestamp strictly before "
                "decision midnight; "
                "state remains active until a later snapshot supersedes it"
            ),
            "same_day_constituent_snapshot_available": False,
        },
        "output": {
            "counts_plus_bounded_availability_timestamps_only": True,
            "raw_rows_emitted": False,
            "security_identifiers_emitted": False,
            "constituent_weights_emitted": False,
            "market_cap_values_emitted": False,
        },
        "capabilities": {
            "prices_or_returns": False,
            "outcomes_or_results": False,
            "orders_or_portfolio": False,
            "network_or_download": False,
            "external_launch_authority_embedded": False,
        },
        "scope_limit": (
            "coverage establishes provider/API geometry only; it is not a "
            "production input, security master, alpha result, or trade authority"
        ),
    }


CONTRACT_BYTES = canonical_json_bytes(pit_market_cap_membership_contract_record())
CONTRACT_SHA256 = hashlib.sha256(CONTRACT_BYTES).hexdigest()
CONTRACT_ID = "arv2-pit-market-cap-membership-contract-v3-" + CONTRACT_SHA256[:24]


def _object_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise PitMarketCapMembershipProbeError(
                "JSON contains a duplicate or non-string key"
            )
        result[key] = value
    return result


def _strict_json(payload: bytes, name: str, maximum: int) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise PitMarketCapMembershipProbeError(f"{name} violates its byte bound")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PitMarketCapMembershipProbeError(
            f"{name} is not strict ASCII JSON"
        ) from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise PitMarketCapMembershipProbeError(f"{name} is not canonical JSON")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise PitMarketCapMembershipProbeError(f"{name} is not SHA-256")
    return value


def _key(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_KEY.fullmatch(value) is None:
        raise PitMarketCapMembershipProbeError(f"{name} is unsafe")
    return value


def _session(value: object, name: str) -> date:
    if type(value) is not str:
        raise PitMarketCapMembershipProbeError(f"{name} is not a session")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PitMarketCapMembershipProbeError(f"{name} is not a session") from exc
    if parsed.isoformat() != value:
        raise PitMarketCapMembershipProbeError(f"{name} is not canonical")
    return parsed


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PitMarketCapMembershipProbeError(f"{name} is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PitMarketCapMembershipProbeError(f"{name} is not UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PitMarketCapMembershipProbeError(f"{name} is not canonical UTC")
    return parsed


def _open_utc(session: date) -> str:
    opened = session_open_instant(session.isoformat()).astimezone(timezone.utc)
    return opened.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_pit_market_cap_membership_probe_plan_bytes(
    *, decision_sessions: Sequence[str], calculation_session: str
) -> bytes:
    """Build a deterministic, bounded session and history-request plan."""

    if isinstance(decision_sessions, (str, bytes)):
        raise PitMarketCapMembershipProbeError("decision sessions are not a sequence")
    try:
        axis = tuple(decision_sessions)
    except TypeError as exc:
        raise PitMarketCapMembershipProbeError(
            "decision sessions are not iterable"
        ) from exc
    parsed = tuple(_session(value, "decision session") for value in axis)
    if (
        not 1 <= len(parsed) <= MAX_DECISION_SESSIONS
        or tuple(item.isoformat() for item in parsed) != axis
        or tuple(sorted(set(parsed))) != parsed
        or any(not is_trading_session(item.isoformat()) for item in parsed)
    ):
        raise PitMarketCapMembershipProbeError("decision-session axis changed")
    calculation = _session(calculation_session, "calculation session")
    if calculation <= parsed[-1] or not is_trading_session(calculation.isoformat()):
        raise PitMarketCapMembershipProbeError(
            "calculation session must be a later exchange session"
        )

    rows = [
        {
            "decision_session": item.isoformat(),
            "decision_session_ordinal": ordinal,
            "decision_open_utc": _open_utc(item),
        }
        for ordinal, item in enumerate(parsed, start=1)
    ]
    chunks = []
    for ordinal, offset in enumerate(range(0, len(parsed), HISTORY_CHUNK_SESSION_COUNT)):
        members = parsed[offset : offset + HISTORY_CHUNK_SESSION_COUNT]
        chunks.append(
            {
                "ordinal": ordinal,
                "first_session": members[0].isoformat(),
                "last_session": members[-1].isoformat(),
                "request_start": (
                    members[0] - timedelta(days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS)
                ).isoformat(),
                "request_end_exclusive": (members[-1] + timedelta(days=1)).isoformat(),
                "decision_sessions": [item.isoformat() for item in members],
            }
        )
    if len(chunks) > MAX_HISTORY_CHUNKS:
        raise PitMarketCapMembershipProbeError("history chunk bound changed")

    base: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "plan_id": None,
        "plan_sha256": None,
        "first_session": parsed[0].isoformat(),
        "last_session": parsed[-1].isoformat(),
        "calculation_session": calculation.isoformat(),
        "decision_sessions": rows,
        "history_chunks": chunks,
        "etfs": list(ETFS),
        "availability_policy": pit_market_cap_membership_contract_record()[
            "availability"
        ],
        "resource_census": {
            "decision_session_count": len(rows),
            "history_chunk_count": len(chunks),
            "history_call_count": len(chunks) * (1 + len(ETFS)),
            "maximum_collections_per_call": MAX_COLLECTIONS_PER_CALL,
            "maximum_collection_rows": MAX_COLLECTION_ROWS,
            "maximum_total_source_rows": MAX_TOTAL_SOURCE_ROWS,
        },
        "execution_contract": {
            "fundamental_history": True,
            "etf_constituent_history": True,
            "market_cap_field": True,
            "object_store_read_write": True,
            "price_or_return_access": False,
            "outcome_or_result_access": False,
            "orders_or_portfolio_actions": False,
            "raw_rows_ids_weights_or_values_emitted": False,
            "external_launch_authority_embedded": False,
        },
        "terminal_pointer_key": None,
    }
    seed = hashlib.sha256(canonical_json_bytes(base)).hexdigest()
    base["plan_id"] = "arv2-pit-market-cap-membership-plan-v3-" + seed[:24]
    base["terminal_pointer_key"] = OUTPUT_PREFIX + "terminals/" + seed + ".json"
    semantic = dict(base)
    semantic["plan_sha256"] = None
    base["plan_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    payload = canonical_json_bytes(base)
    if len(payload) > MAX_PLAN_BYTES:
        raise PitMarketCapMembershipProbeError("coverage plan exceeds byte bound")
    return payload


def _validate_plan(payload: bytes) -> dict[str, object]:
    value = _strict_json(payload, "coverage plan", MAX_PLAN_BYTES)
    expected = {
        "schema",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "first_session",
        "last_session",
        "calculation_session",
        "decision_sessions",
        "history_chunks",
        "etfs",
        "availability_policy",
        "resource_census",
        "execution_contract",
        "terminal_pointer_key",
    }
    if (
        set(value) != expected
        or value.get("schema") != PLAN_SCHEMA
        or value.get("contract_sha256") != CONTRACT_SHA256
        or value.get("etfs") != list(ETFS)
        or value.get("availability_policy")
        != pit_market_cap_membership_contract_record()["availability"]
    ):
        raise PitMarketCapMembershipProbeError("coverage plan contract changed")
    rebuilt = build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=[
            row["decision_session"] for row in value.get("decision_sessions", [])
        ],
        calculation_session=value.get("calculation_session"),
    )
    if rebuilt != payload:
        raise PitMarketCapMembershipProbeError("coverage plan identity changed")
    _sha(value["plan_sha256"], "plan semantic hash")
    _key(value["terminal_pointer_key"], "terminal pointer key")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PitCoverageProbeProjectSource:
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
class PitMarketCapMembershipProbeQcProjection:
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
    terminal_pointer_key: str
    source_files: tuple[PitCoverageProbeProjectSource, ...]
    project_source_set_sha256: str
    calculation_session: str
    calculation_end_date: str
    history_chunk_count: int
    runtime_source_enabled: bool
    external_launch_authority_embedded: bool
    reads_fundamentals_history: bool
    reads_etf_constituent_history: bool
    reads_prices_or_returns: bool
    reads_outcomes_or_results: bool
    places_orders_or_touches_portfolio: bool
    plan_bytes: bytes = dataclasses.field(repr=False)


def _source(path: str, payload: bytes) -> PitCoverageProbeProjectSource:
    if type(payload) is not bytes or not payload or b"\x00" in payload or b"\r" in payload:
        raise PitMarketCapMembershipProbeError("project source encoding changed")
    try:
        text = payload.decode("ascii")
    except UnicodeError as exc:
        raise PitMarketCapMembershipProbeError("project source is not ASCII") from exc
    if len(text) > MAX_PROJECT_SOURCE_CHARACTERS:
        raise PitMarketCapMembershipProbeError(
            "project source exceeds the reviewed character cap"
        )
    try:
        tree = ast.parse(text, filename=path)
        compile(text, path, "exec")
        compile(
            "QC_PRELUDE_SENTINEL = True\nfrom AlgorithmImports import *\n" + text,
            path,
            "exec",
        )
    except SyntaxError as exc:
        raise PitMarketCapMembershipProbeError(
            "project source is not prelude-safe Python"
        ) from exc
    if any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__"
        for node in tree.body
    ):
        raise PitMarketCapMembershipProbeError(
            "QC project source contains an unsupported future import"
        )
    return PitCoverageProbeProjectSource(
        project_path=path,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        character_count=len(text),
        content=payload,
    )


def _exact_history_call(node: ast.Call, first_argument: str) -> bool:
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "history"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "algorithm"
        and len(node.args) == 3
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == "start"
        and isinstance(node.args[2], ast.Name)
        and node.args[2].id == "end"
        and len(node.keywords) == 1
        and node.keywords[0].arg == "flatten"
        and isinstance(node.keywords[0].value, ast.Constant)
        and node.keywords[0].value.value is False
    ):
        return False
    if first_argument == "fundamental":
        return (
            isinstance(node.args[0], ast.Attribute)
            and isinstance(node.args[0].value, ast.Name)
            and node.args[0].value.id == "algorithm"
            and node.args[0].attr == "_arv2_fundamental_universe"
        )
    return isinstance(node.args[0], ast.Name) and node.args[0].id == "universe"


def _audit_source_capabilities(
    files: tuple[PitCoverageProbeProjectSource, ...],
) -> None:
    if tuple(item.project_path for item in files) != (ENTRY_PATH, RUNTIME_PATH):
        raise PitMarketCapMembershipProbeError("project source inventory changed")
    allowed_imports = {
        "AlgorithmImports",
        "hashlib",
        "itertools",
        "json",
        "datetime",
        "decimal",
        "zoneinfo",
        "pit_market_cap_membership_probe_runtime_v3",
    }
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
        "requests",
        "urllib",
        "subprocess",
        "socket",
        "importlib",
        "eval",
        "exec",
        "open",
        "print",
        "getattr",
        "setattr",
        "hasattr",
        "vars",
        "dir",
        "__import__",
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
        "holdings",
        "orders",
        "result",
        "results",
        "statistics",
        "runtime_statistics",
        "last_update",
        "LastUpdate",
        "log",
        "debug",
        "quit",
    }
    history_kinds: list[str] = []
    market_cap_reads = 0
    fundamental_universe_calls = 0
    constituent_universe_calls = 0
    etf_universe_calls = 0
    symbol_create_calls = 0
    empty_selector_definitions = 0
    object_reads = 0
    object_writes = 0
    for item in files:
        if (
            type(item) is not PitCoverageProbeProjectSource
            or item.content_sha256 != hashlib.sha256(item.content).hexdigest()
            or item.byte_count != len(item.content)
            or item.character_count != len(item.content.decode("ascii"))
        ):
            raise PitMarketCapMembershipProbeError(
                "project source descriptor or content changed"
            )
        tree = ast.parse(item.content.decode("ascii"), filename=item.project_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                literal_keys = [
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and type(key.value) is str
                ]
                if len(literal_keys) != len(set(literal_keys)):
                    raise PitMarketCapMembershipProbeError(
                        "project source contains a duplicate literal dictionary key"
                    )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name.split(".")[0] for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [(node.module or "").split(".")[0]]
                )
                if any(name not in allowed_imports for name in names):
                    raise PitMarketCapMembershipProbeError(
                        "project source acquired an unreviewed import"
                    )
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                raise PitMarketCapMembershipProbeError(
                    "project source acquired a forbidden capability name"
                )
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "fundamental"
            ):
                raise PitMarketCapMembershipProbeError(
                    "provider row acquired an unreviewed subscript read"
                )
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden_attributes:
                    raise PitMarketCapMembershipProbeError(
                        "project source acquired a price/order/network attribute"
                    )
                if node.attr == "market_cap":
                    market_cap_reads += 1
                    if not (
                        isinstance(node.value, ast.Name)
                        and node.value.id == "fundamental"
                    ):
                        raise PitMarketCapMembershipProbeError(
                            "market-cap access is not the reviewed field read"
                        )
                if isinstance(node.value, ast.Name) and node.value.id == "algorithm":
                    if node.attr not in {
                        "history",
                        "object_store",
                        "_arv2_fundamental_universe",
                        "_arv2_constituent_universes",
                        "_arv2_pit_coverage_summary",
                        "_arv2_pit_coverage_completed",
                    }:
                        raise PitMarketCapMembershipProbeError(
                            "runtime acquired an unreviewed algorithm capability"
                        )
                if isinstance(node.value, ast.Name) and node.value.id == "fundamental":
                    if node.attr not in {"symbol", "market_cap"}:
                        raise PitMarketCapMembershipProbeError(
                            "fundamental row acquired an unreviewed field"
                        )
                if isinstance(node.value, ast.Name) and node.value.id == "row":
                    if node.attr not in {"symbol", "weight"}:
                        raise PitMarketCapMembershipProbeError(
                            "constituent row acquired an unreviewed field"
                        )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"History", "history"}
            ):
                if _exact_history_call(node, "fundamental"):
                    history_kinds.append("fundamental")
                elif _exact_history_call(node, "constituent"):
                    history_kinds.append("constituent")
                else:
                    raise PitMarketCapMembershipProbeError(
                        "history request is not an exact reviewed unflattened call"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"read_bytes", "save_bytes"}
            ):
                exact_store = (
                    isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "object_store"
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "algorithm"
                    and not node.keywords
                )
                if node.func.attr == "read_bytes":
                    object_reads += 1
                    exact_shape = exact_store and len(node.args) == 1
                else:
                    object_writes += 1
                    exact_shape = exact_store and len(node.args) == 2
                if not exact_shape:
                    raise PitMarketCapMembershipProbeError(
                        "Object Store call is not the reviewed exact form"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "AddUniverse"
            ):
                fundamental_universe_calls += 1
                if not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                    and len(node.args) == 1
                    and not node.keywords
                    and isinstance(node.args[0], ast.Lambda)
                    and isinstance(node.args[0].body, ast.List)
                    and not node.args[0].body.elts
                ):
                    raise PitMarketCapMembershipProbeError(
                        "fundamental universe constructor changed"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "etf"
            ):
                etf_universe_calls += 1
                if not (
                    isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "self"
                    and node.func.value.attr == "universe"
                    and len(node.args) == 3
                    and not node.keywords
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "symbol"
                    and isinstance(node.args[1], ast.Attribute)
                    and isinstance(node.args[1].value, ast.Name)
                    and node.args[1].value.id == "self"
                    and node.args[1].attr == "universe_settings"
                    and isinstance(node.args[2], ast.Attribute)
                    and isinstance(node.args[2].value, ast.Name)
                    and node.args[2].value.id == "self"
                    and node.args[2].attr
                    == "_arv2_empty_constituent_selection"
                ):
                    raise PitMarketCapMembershipProbeError(
                        "reviewed ETF universe arguments changed"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_universe"
            ):
                constituent_universe_calls += 1
                if not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                    and len(node.args) == 1
                    and not node.keywords
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Attribute)
                    and node.args[0].func.attr == "etf"
                ):
                    raise PitMarketCapMembershipProbeError(
                        "reviewed ETF universe wrapper changed"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Symbol"
            ):
                symbol_create_calls += 1
                if not (
                    len(node.args) == 3
                    and not node.keywords
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "ticker"
                    and isinstance(node.args[1], ast.Attribute)
                    and isinstance(node.args[1].value, ast.Name)
                    and node.args[1].value.id == "SecurityType"
                    and node.args[1].attr == "EQUITY"
                    and isinstance(node.args[2], ast.Attribute)
                    and isinstance(node.args[2].value, ast.Name)
                    and node.args[2].value.id == "Market"
                    and node.args[2].attr == "USA"
                ):
                    raise PitMarketCapMembershipProbeError(
                        "reviewed ETF symbol constructor changed"
                    )
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_arv2_empty_constituent_selection"
            ):
                empty_selector_definitions += 1
                if not (
                    not node.decorator_list
                    and not node.args.posonlyargs
                    and not node.args.kwonlyargs
                    and node.args.vararg is None
                    and node.args.kwarg is None
                    and [argument.arg for argument in node.args.args]
                    == ["self", "_constituents"]
                    and len(node.body) == 1
                    and isinstance(node.body[0], ast.Return)
                    and isinstance(node.body[0].value, ast.List)
                    and not node.body[0].value.elts
                ):
                    raise PitMarketCapMembershipProbeError(
                        "reviewed empty ETF selector changed"
                    )
    if sorted(history_kinds) != ["constituent", "fundamental"]:
        raise PitMarketCapMembershipProbeError("reviewed history call inventory changed")
    if market_cap_reads != 1:
        raise PitMarketCapMembershipProbeError("reviewed market-cap read changed")
    if object_reads != 2 or object_writes != 1:
        raise PitMarketCapMembershipProbeError("reviewed Object Store call inventory changed")
    if fundamental_universe_calls != 1:
        raise PitMarketCapMembershipProbeError(
            "reviewed fundamental universe constructor changed"
        )
    if (
        constituent_universe_calls != 1
        or etf_universe_calls != 1
        or symbol_create_calls != 1
        or empty_selector_definitions != 1
    ):
        raise PitMarketCapMembershipProbeError(
            "reviewed ETF universe constructor changed"
        )


def _entry_source(
    *,
    plan: Mapping[str, object],
    plan_payload: bytes,
    plan_key: str,
    project_source_set_sha256: str,
) -> bytes:
    calculation = _session(plan["calculation_session"], "calculation session")
    end = calculation + timedelta(days=1)
    constants = {
        "PLAN_ID": plan["plan_id"],
        "PLAN_SHA256": plan["plan_sha256"],
        "PLAN_ARTIFACT_SHA256": hashlib.sha256(plan_payload).hexdigest(),
        "PLAN_BYTE_COUNT": len(plan_payload),
        "PLAN_OBJECT_STORE_KEY": plan_key,
        "TERMINAL_POINTER_KEY": plan["terminal_pointer_key"],
        "PROJECT_SOURCE_SET_SHA256": project_source_set_sha256,
        "SUMMARY_NAME": SUMMARY_NAME,
    }
    literal = json.dumps(constants, sort_keys=True, separators=(",", ":"))
    return f'''from AlgorithmImports import *
import json
from pit_market_cap_membership_probe_runtime_v3 import execute_pit_market_cap_membership_probe

_C = json.loads({literal!r})


class Arv2PitMarketCapMembershipCoverage(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({calculation.year}, {calculation.month}, {calculation.day})
        self.set_end_date({end.year}, {end.month}, {end.day})
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self._arv2_fundamental_universe = self.AddUniverse(lambda fundamentals: [])
        self._arv2_constituent_universes = {{}}
        for ticker in {ETFS!r}:
            symbol = Symbol.create(ticker, SecurityType.EQUITY, Market.USA)
            self._arv2_constituent_universes[ticker] = self.add_universe(
                self.universe.etf(
                    symbol,
                    self.universe_settings,
                    self._arv2_empty_constituent_selection,
                )
            )
        self._arv2_pit_coverage_completed = False
        self._arv2_pit_coverage_summary = None
        execute_pit_market_cap_membership_probe(self, _C)

    def _arv2_empty_constituent_selection(self, _constituents):
        return []

    def on_end_of_algorithm(self):
        if self._arv2_pit_coverage_completed is not True:
            raise RuntimeError("ARV2 PIT market-cap/membership coverage did not complete")
        if type(self._arv2_pit_coverage_summary) is not str:
            raise RuntimeError("ARV2 PIT market-cap/membership summary is unavailable")
        self.set_summary_statistic(_C["SUMMARY_NAME"], self._arv2_pit_coverage_summary)
'''.encode("ascii")


def _source_set_hash(files: tuple[PitCoverageProbeProjectSource, ...]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "schema": "arv2-qc-pit-market-cap-membership-source-set-v3",
                "normalization": "entry_PROJECT_SOURCE_SET_SHA256_constant_zeroed",
                "source_files": [item.to_record() for item in files],
            }
        )
    ).hexdigest()


def _projection_record(
    *,
    plan: Mapping[str, object],
    plan_payload: bytes,
    plan_key: str,
    files: tuple[PitCoverageProbeProjectSource, ...],
    source_set_sha256: str,
) -> dict[str, object]:
    calculation = _session(plan["calculation_session"], "calculation session")
    return {
        "schema": PROJECTION_SCHEMA,
        "project_name": PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_artifact_sha256": hashlib.sha256(plan_payload).hexdigest(),
        "plan_byte_count": len(plan_payload),
        "plan_object_store_key": plan_key,
        "terminal_pointer_key": plan["terminal_pointer_key"],
        "source_files": [item.to_record() for item in files],
        "project_source_set_sha256": source_set_sha256,
        "calculation_session": calculation.isoformat(),
        "calculation_end_date": (calculation + timedelta(days=1)).isoformat(),
        "history_chunk_count": len(plan["history_chunks"]),
        "runtime_source_enabled": True,
        "external_launch_authority_embedded": False,
        "reads_fundamentals_history": True,
        "reads_etf_constituent_history": True,
        "reads_prices_or_returns": False,
        "reads_outcomes_or_results": False,
        "places_orders_or_touches_portfolio": False,
    }


def build_pit_market_cap_membership_probe_qc_projection(
    *, plan_bytes: bytes, runtime_source_bytes: bytes
) -> PitMarketCapMembershipProbeQcProjection:
    """Build the exact two-file cloud source set without performing I/O."""

    plan = _validate_plan(plan_bytes)
    if type(runtime_source_bytes) is not bytes:
        raise PitMarketCapMembershipProbeError("runtime source is absent")
    if hashlib.sha256(runtime_source_bytes).hexdigest() != RUNTIME_TEMPLATE_SHA256:
        raise PitMarketCapMembershipProbeError(
            "reviewed runtime source template changed"
        )
    try:
        runtime_text = runtime_source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise PitMarketCapMembershipProbeError("runtime source is not ASCII") from exc
    if runtime_text.count(_MARKER) != 1:
        raise PitMarketCapMembershipProbeError("source contract marker changed")
    runtime = _source(
        RUNTIME_PATH,
        runtime_text.replace(_MARKER, CONTRACT_SHA256).encode("ascii"),
    )
    if runtime.content_sha256 != RUNTIME_RENDERED_SHA256:
        raise PitMarketCapMembershipProbeError(
            "reviewed rendered runtime source changed"
        )
    plan_artifact_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    plan_key = INPUT_PREFIX + "plans/" + plan_artifact_sha256 + ".json"
    provisional_entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=plan_bytes,
            plan_key=plan_key,
            project_source_set_sha256="0" * 64,
        ),
    )
    source_set_sha256 = _source_set_hash((provisional_entry, runtime))
    entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=plan_bytes,
            plan_key=plan_key,
            project_source_set_sha256=source_set_sha256,
        ),
    )
    files = (entry, runtime)
    _audit_source_capabilities(files)
    record = _projection_record(
        plan=plan,
        plan_payload=plan_bytes,
        plan_key=plan_key,
        files=files,
        source_set_sha256=source_set_sha256,
    )
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    fields = {
        **record,
        "projection_id": "arv2-pit-market-cap-membership-projection-v3-"
        + digest[:24],
        "projection_sha256": digest,
        "source_files": files,
        "plan_bytes": bytes(plan_bytes),
    }
    return require_pit_market_cap_membership_probe_qc_projection(
        PitMarketCapMembershipProbeQcProjection(**fields)
    )


def require_pit_market_cap_membership_probe_qc_projection(
    value: PitMarketCapMembershipProbeQcProjection,
) -> PitMarketCapMembershipProbeQcProjection:
    if type(value) is not PitMarketCapMembershipProbeQcProjection:
        raise PitMarketCapMembershipProbeError("coverage projection type changed")
    plan = _validate_plan(value.plan_bytes)
    provisional_entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=value.plan_bytes,
            plan_key=value.plan_object_store_key,
            project_source_set_sha256="0" * 64,
        ),
    )
    if type(value.source_files) is not tuple or len(value.source_files) != 2:
        raise PitMarketCapMembershipProbeError("project source inventory changed")
    if (
        value.source_files[1].project_path != RUNTIME_PATH
        or value.source_files[1].content_sha256 != RUNTIME_RENDERED_SHA256
        or hashlib.sha256(value.source_files[1].content).hexdigest()
        != RUNTIME_RENDERED_SHA256
    ):
        raise PitMarketCapMembershipProbeError(
            "reviewed rendered runtime source changed"
        )
    expected_source_set = _source_set_hash((provisional_entry, value.source_files[1]))
    expected_entry = _source(
        ENTRY_PATH,
        _entry_source(
            plan=plan,
            plan_payload=value.plan_bytes,
            plan_key=value.plan_object_store_key,
            project_source_set_sha256=expected_source_set,
        ),
    )
    if value.source_files[0] != expected_entry:
        raise PitMarketCapMembershipProbeError("generated entry source changed")
    _audit_source_capabilities(value.source_files)
    record = _projection_record(
        plan=plan,
        plan_payload=value.plan_bytes,
        plan_key=value.plan_object_store_key,
        files=value.source_files,
        source_set_sha256=expected_source_set,
    )
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        any(
            getattr(value, name) != expected
            for name, expected in record.items()
            if name != "source_files"
        )
        or value.source_files != tuple(value.source_files)
        or value.project_source_set_sha256 != expected_source_set
        or value.projection_sha256 != digest
        or value.projection_id
        != "arv2-pit-market-cap-membership-projection-v3-" + digest[:24]
        or value.plan_artifact_sha256 != hashlib.sha256(value.plan_bytes).hexdigest()
        or value.plan_byte_count != len(value.plan_bytes)
    ):
        raise PitMarketCapMembershipProbeError("coverage projection boundary changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedPitMarketCapMembershipCoverageReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    contract_sha256: str
    plan_id: str
    plan_sha256: str
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    first_session: str
    last_session: str
    decision_session_count: int
    history_call_count: int
    session_census_sha256: str
    receipt_object_key: str
    receipt_byte_count: int
    terminal_pointer_sha256: str
    terminal_pointer_byte_count: int
    outcome_access_performed: bool
    price_or_return_access_performed: bool
    orders_or_portfolio_actions_performed: bool
    plan_bytes: bytes = dataclasses.field(repr=False)
    terminal_pointer_bytes: bytes = dataclasses.field(repr=False)
    receipt_bytes: bytes = dataclasses.field(repr=False)
    projection: PitMarketCapMembershipProbeQcProjection = dataclasses.field(
        repr=False
    )


_SESSION_FIELDS = {
    "decision_session",
    "fundamental_collection_time_local",
    "fundamental_source_member_count",
    "fundamental_exact_sid_count",
    "fundamental_missing_or_invalid_sid_count",
    "fundamental_duplicate_exact_sid_count",
    "fundamental_duplicate_exact_sid_row_count",
    "positive_market_cap_count",
    "null_market_cap_count",
    "nonpositive_market_cap_count",
    "invalid_or_nonfinite_market_cap_count",
    "etfs",
    "union_positive_member_count",
    "union_positive_market_cap_covered_count",
    "union_market_cap_uncovered_count",
    "spy_qqq_overlap_count",
    "spy_soxx_overlap_count",
    "qqq_soxx_overlap_count",
    "triple_overlap_count",
}


def _nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise PitMarketCapMembershipProbeError(f"{name} is not a non-negative int")
    return value


def _local_timestamp(value: object, name: str) -> datetime:
    if type(value) is not str:
        raise PitMarketCapMembershipProbeError(f"{name} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PitMarketCapMembershipProbeError(f"{name} is not a timestamp") from exc
    if parsed.tzinfo is not None or parsed.isoformat(timespec="microseconds") != value:
        raise PitMarketCapMembershipProbeError(f"{name} is not canonical local time")
    return parsed


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedPitMarketCapMembershipCoverageAttestation:
    """Authenticated, outcome-free summary of a completed coverage canary."""

    schema: str
    status: str
    attestation_sha256: str
    attestation_byte_count: int
    contract_sha256: str
    plan_id: str
    plan_sha256: str
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    first_session: str
    last_session: str
    decision_session_count: int
    passed_session_count: int
    history_call_count: int
    fetched_source_row_count: int
    receipt_id: str
    receipt_sha256: str
    receipt_byte_count: int
    terminal_pointer_sha256: str
    terminal_pointer_byte_count: int
    full_receipt_remains_qc_internal: bool
    outcome_access_performed: bool
    price_or_return_access_performed: bool
    orders_or_portfolio_actions_performed: bool
    summary_bytes: bytes = dataclasses.field(repr=False)
    projection: PitMarketCapMembershipProbeQcProjection = dataclasses.field(
        repr=False
    )


@dataclasses.dataclass(frozen=True, slots=True)
class PitMarketCapMembershipCoverageNamedRefusal:
    """Authenticated safe refusal with no provider rows or result values."""

    schema: str
    status: str
    attestation_sha256: str
    attestation_byte_count: int
    contract_sha256: str
    plan_id: str
    plan_sha256: str
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    safe_reason: str
    outcome_access_performed: bool
    price_or_return_access_performed: bool
    orders_or_portfolio_actions_performed: bool
    summary_bytes: bytes = dataclasses.field(repr=False)
    projection: PitMarketCapMembershipProbeQcProjection = dataclasses.field(
        repr=False
    )


_ATTESTATION_AGGREGATE_FIELDS = {
    "fundamental_source_member_count",
    "fundamental_exact_sid_count",
    "fundamental_missing_or_invalid_sid_count",
    "fundamental_duplicate_exact_sid_count",
    "fundamental_duplicate_exact_sid_row_count",
    "positive_market_cap_count",
    "null_market_cap_count",
    "nonpositive_market_cap_count",
    "invalid_or_nonfinite_market_cap_count",
    "union_positive_member_count",
    "union_positive_market_cap_covered_count",
    "union_market_cap_uncovered_count",
}
_ATTESTATION_BOUND_FIELDS = {
    "minimum_positive_member_count",
    "maximum_positive_member_count",
    "minimum_market_cap_covered_count",
    "maximum_market_cap_covered_count",
}
_NO_EXPORT_CAPABILITIES = {
    "price_or_return_access_performed": False,
    "outcome_or_result_access_performed": False,
    "orders_or_portfolio_actions_performed": False,
    "raw_rows_emitted": False,
    "security_identifiers_emitted": False,
    "constituent_weights_emitted": False,
    "market_cap_values_emitted": False,
    "full_receipt_or_pointer_export_performed": False,
}
_COMPLETED_ATTESTATION_CAPABILITIES = {
    **_NO_EXPORT_CAPABILITIES,
    "fundamental_history_access_performed": True,
    "etf_constituent_history_access_performed": True,
    "market_cap_field_access_performed": True,
}
_SAFE_REFUSAL_REASON = re.compile(
    r"pit_coverage_refused_[A-Za-z0-9_]{1,64}_[0-9a-f]{16}\Z"
)


def _strict_attestation(payload: bytes) -> dict[str, object]:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_SUMMARY_CHARACTERS
    ):
        raise PitMarketCapMembershipProbeError(
            "coverage attestation violates its byte bound"
        )
    try:
        text = payload.decode("ascii")
        value = json.loads(text, object_pairs_hook=_object_pairs)
        canonical = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise PitMarketCapMembershipProbeError(
            "coverage attestation is not strict ASCII JSON"
        ) from exc
    if type(value) is not dict or canonical != text:
        raise PitMarketCapMembershipProbeError(
            "coverage attestation is not canonical JSON"
        )
    return value


def _positive_int(value: object, name: str, maximum: int) -> int:
    parsed = _nonnegative_int(value, name)
    if parsed == 0 or parsed > maximum:
        raise PitMarketCapMembershipProbeError(f"{name} escaped its positive bound")
    return parsed


def _validate_attestation_lineage(
    value: Mapping[str, object],
    *,
    plan: Mapping[str, object],
    projection: PitMarketCapMembershipProbeQcProjection,
) -> None:
    if (
        value.get("schema") != ATTESTATION_SCHEMA
        or value.get("contract_sha256") != CONTRACT_SHA256
        or value.get("plan_id") != plan["plan_id"]
        or value.get("plan_sha256") != plan["plan_sha256"]
        or value.get("project_source_set_sha256")
        != projection.project_source_set_sha256
    ):
        raise PitMarketCapMembershipProbeError(
            "coverage attestation lineage changed"
        )


def _capabilities_are_exact(value: object, expected: Mapping[str, bool]) -> bool:
    return (
        type(value) is dict
        and set(value) == set(expected)
        and all(value[name] is expected[name] for name in expected)
    )


def _validate_attestation_bounds(value: object, name: str, maximum: int) -> None:
    if type(value) is not dict or set(value) != _ATTESTATION_BOUND_FIELDS:
        raise PitMarketCapMembershipProbeError(f"{name} fields changed")
    minimum_members = _positive_int(
        value["minimum_positive_member_count"],
        f"{name} minimum member count",
        maximum,
    )
    maximum_members = _positive_int(
        value["maximum_positive_member_count"],
        f"{name} maximum member count",
        maximum,
    )
    minimum_covered = _positive_int(
        value["minimum_market_cap_covered_count"],
        f"{name} minimum covered count",
        maximum,
    )
    maximum_covered = _positive_int(
        value["maximum_market_cap_covered_count"],
        f"{name} maximum covered count",
        maximum,
    )
    if (
        minimum_members > maximum_members
        or minimum_covered > maximum_covered
        or minimum_covered > minimum_members
        or maximum_covered > maximum_members
    ):
        raise PitMarketCapMembershipProbeError(f"{name} bounds do not reconcile")


def _validate_attestation_availability(
    value: object, plan: Mapping[str, object]
) -> None:
    if type(value) is not dict or set(value) != {"fundamentals", "etfs"}:
        raise PitMarketCapMembershipProbeError(
            "coverage availability extrema fields changed"
        )
    first = _session(plan["first_session"], "first session")
    last = _session(plan["last_session"], "last session")
    fundamentals = value["fundamentals"]
    if type(fundamentals) is not dict or set(fundamentals) != {
        "earliest_collection_time_local",
        "latest_collection_time_local",
    }:
        raise PitMarketCapMembershipProbeError(
            "fundamental availability extrema fields changed"
        )
    fundamental_earliest = _local_timestamp(
        fundamentals["earliest_collection_time_local"],
        "earliest fundamental collection time",
    )
    fundamental_latest = _local_timestamp(
        fundamentals["latest_collection_time_local"],
        "latest fundamental collection time",
    )
    if (
        fundamental_earliest
        < datetime.combine(
            first - timedelta(days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS),
            datetime.min.time(),
        )
        or fundamental_earliest >= datetime.combine(first, datetime.min.time()).replace(
            hour=9, minute=30
        )
        or fundamental_latest
        < datetime.combine(
            last - timedelta(days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS),
            datetime.min.time(),
        )
        or fundamental_latest >= datetime.combine(last, datetime.min.time()).replace(
            hour=9, minute=30
        )
        or fundamental_earliest > fundamental_latest
    ):
        raise PitMarketCapMembershipProbeError(
            "fundamental availability escaped the reviewed PIT bounds"
        )
    etfs = value["etfs"]
    if type(etfs) is not dict or set(etfs) != set(ETFS):
        raise PitMarketCapMembershipProbeError(
            "ETF availability extrema inventory changed"
        )
    for ticker in ETFS:
        item = etfs[ticker]
        if type(item) is not dict or set(item) != {
            "earliest_collection_availability_time_local",
            "latest_collection_availability_time_local",
        }:
            raise PitMarketCapMembershipProbeError(
                "ETF availability extrema fields changed"
            )
        earliest = _local_timestamp(
            item["earliest_collection_availability_time_local"],
            f"{ticker} earliest collection availability time",
        )
        latest = _local_timestamp(
            item["latest_collection_availability_time_local"],
            f"{ticker} latest collection availability time",
        )
        if (
            earliest.time() != datetime.min.time()
            or latest.time() != datetime.min.time()
            or earliest
            < datetime.combine(
                first - timedelta(days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS),
                datetime.min.time(),
            )
            or earliest >= datetime.combine(first, datetime.min.time())
            or latest
            < datetime.combine(
                last - timedelta(days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS),
                datetime.min.time(),
            )
            or latest >= datetime.combine(last, datetime.min.time())
            or earliest > latest
        ):
            raise PitMarketCapMembershipProbeError(
                "ETF availability escaped the reviewed PIT bounds"
            )


def _load_completed_attestation(
    *,
    value: Mapping[str, object],
    summary_bytes: bytes,
    plan: Mapping[str, object],
    projection: PitMarketCapMembershipProbeQcProjection,
) -> ReviewedPitMarketCapMembershipCoverageAttestation:
    fields = {
        "schema",
        "status",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "first_session",
        "last_session",
        "decision_session_count",
        "passed_session_count",
        "history_call_count",
        "fetched_source_row_count",
        "aggregate",
        "etf_bounds",
        "union_bounds",
        "availability_extrema",
        "receipt_id",
        "receipt_sha256",
        "receipt_byte_count",
        "terminal_pointer_sha256",
        "terminal_pointer_byte_count",
        "full_receipt_remains_qc_internal",
        "capabilities",
    }
    if (
        set(value) != fields
        or value.get("status") != "completed"
        or value.get("first_session") != plan["first_session"]
        or value.get("last_session") != plan["last_session"]
        or value.get("decision_session_count") != EXPECTED_CANARY_SESSION_COUNT
        or value.get("passed_session_count") != EXPECTED_CANARY_SESSION_COUNT
        or value.get("history_call_count")
        != plan["resource_census"]["history_call_count"]
        or value.get("full_receipt_remains_qc_internal") is not True
        or not _capabilities_are_exact(
            value.get("capabilities"), _COMPLETED_ATTESTATION_CAPABILITIES
        )
    ):
        raise PitMarketCapMembershipProbeError(
            "completed coverage attestation contract changed"
        )
    fetched_source_rows = _positive_int(
        value["fetched_source_row_count"],
        "fetched source row count",
        MAX_TOTAL_SOURCE_ROWS,
    )
    aggregate = value["aggregate"]
    if type(aggregate) is not dict or set(aggregate) != _ATTESTATION_AGGREGATE_FIELDS:
        raise PitMarketCapMembershipProbeError(
            "coverage attestation aggregate fields changed"
        )
    counts = {
        name: _nonnegative_int(aggregate[name], name)
        for name in _ATTESTATION_AGGREGATE_FIELDS
    }
    if any(count > MAX_TOTAL_SOURCE_ROWS for count in counts.values()):
        raise PitMarketCapMembershipProbeError(
            "coverage attestation aggregate escaped its count bound"
        )
    if (
        counts["fundamental_exact_sid_count"]
        + counts["fundamental_missing_or_invalid_sid_count"]
        + counts["fundamental_duplicate_exact_sid_row_count"]
        != counts["fundamental_source_member_count"]
        or counts["positive_market_cap_count"]
        + counts["null_market_cap_count"]
        + counts["nonpositive_market_cap_count"]
        + counts["invalid_or_nonfinite_market_cap_count"]
        != counts["fundamental_exact_sid_count"]
        or counts["fundamental_duplicate_exact_sid_count"]
        > counts["fundamental_exact_sid_count"]
        or counts["fundamental_duplicate_exact_sid_count"]
        > counts["fundamental_duplicate_exact_sid_row_count"]
        or (counts["fundamental_duplicate_exact_sid_count"] == 0)
        != (counts["fundamental_duplicate_exact_sid_row_count"] == 0)
        or counts["union_positive_market_cap_covered_count"]
        + counts["union_market_cap_uncovered_count"]
        != counts["union_positive_member_count"]
        or counts["positive_market_cap_count"] == 0
        or counts["union_positive_member_count"] == 0
        or counts["union_positive_market_cap_covered_count"] == 0
    ):
        raise PitMarketCapMembershipProbeError(
            "coverage attestation aggregate does not reconcile"
        )
    etf_bounds = value["etf_bounds"]
    if type(etf_bounds) is not dict or set(etf_bounds) != set(ETFS):
        raise PitMarketCapMembershipProbeError(
            "coverage attestation ETF bounds inventory changed"
        )
    for ticker in ETFS:
        _validate_attestation_bounds(
            etf_bounds[ticker], f"{ticker} coverage", MAX_COLLECTION_ROWS
        )
    _validate_attestation_bounds(
        value["union_bounds"], "ETF union coverage", len(ETFS) * MAX_COLLECTION_ROWS
    )
    _validate_attestation_availability(value["availability_extrema"], plan)
    receipt_id = value["receipt_id"]
    if (
        type(receipt_id) is not str
        or re.fullmatch(
            r"arv2-pit-market-cap-membership-coverage-v3-[0-9a-f]{24}", receipt_id
        )
        is None
    ):
        raise PitMarketCapMembershipProbeError("coverage receipt identity changed")
    receipt_sha256 = _sha(value["receipt_sha256"], "coverage receipt SHA-256")
    receipt_byte_count = _positive_int(
        value["receipt_byte_count"], "coverage receipt byte count", MAX_RECEIPT_BYTES
    )
    pointer_sha256 = _sha(
        value["terminal_pointer_sha256"], "coverage pointer SHA-256"
    )
    pointer_byte_count = _positive_int(
        value["terminal_pointer_byte_count"],
        "coverage pointer byte count",
        MAX_TERMINAL_POINTER_BYTES,
    )
    return ReviewedPitMarketCapMembershipCoverageAttestation(
        schema=ATTESTATION_SCHEMA,
        status="completed",
        attestation_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        attestation_byte_count=len(summary_bytes),
        contract_sha256=CONTRACT_SHA256,
        plan_id=plan["plan_id"],
        plan_sha256=plan["plan_sha256"],
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        first_session=plan["first_session"],
        last_session=plan["last_session"],
        decision_session_count=EXPECTED_CANARY_SESSION_COUNT,
        passed_session_count=EXPECTED_CANARY_SESSION_COUNT,
        history_call_count=value["history_call_count"],
        fetched_source_row_count=fetched_source_rows,
        receipt_id=receipt_id,
        receipt_sha256=receipt_sha256,
        receipt_byte_count=receipt_byte_count,
        terminal_pointer_sha256=pointer_sha256,
        terminal_pointer_byte_count=pointer_byte_count,
        full_receipt_remains_qc_internal=True,
        outcome_access_performed=False,
        price_or_return_access_performed=False,
        orders_or_portfolio_actions_performed=False,
        summary_bytes=bytes(summary_bytes),
        projection=projection,
    )


def _load_named_refusal_attestation(
    *,
    value: Mapping[str, object],
    summary_bytes: bytes,
    plan: Mapping[str, object],
    projection: PitMarketCapMembershipProbeQcProjection,
) -> PitMarketCapMembershipCoverageNamedRefusal:
    fields = {
        "schema",
        "status",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "safe_reason",
        "capabilities",
    }
    safe_reason = value.get("safe_reason")
    if (
        set(value) != fields
        or value.get("status") != "named_refusal"
        or type(safe_reason) is not str
        or _SAFE_REFUSAL_REASON.fullmatch(safe_reason) is None
        or not _capabilities_are_exact(
            value.get("capabilities"), _NO_EXPORT_CAPABILITIES
        )
    ):
        raise PitMarketCapMembershipProbeError(
            "coverage named-refusal attestation contract changed"
        )
    return PitMarketCapMembershipCoverageNamedRefusal(
        schema=ATTESTATION_SCHEMA,
        status="named_refusal",
        attestation_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        attestation_byte_count=len(summary_bytes),
        contract_sha256=CONTRACT_SHA256,
        plan_id=plan["plan_id"],
        plan_sha256=plan["plan_sha256"],
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        safe_reason=safe_reason,
        outcome_access_performed=False,
        price_or_return_access_performed=False,
        orders_or_portfolio_actions_performed=False,
        summary_bytes=bytes(summary_bytes),
        projection=projection,
    )


def load_reviewed_pit_market_cap_membership_coverage_attestation(
    *,
    plan_bytes: bytes,
    projection: PitMarketCapMembershipProbeQcProjection,
    summary_bytes: bytes,
) -> (
    ReviewedPitMarketCapMembershipCoverageAttestation
    | PitMarketCapMembershipCoverageNamedRefusal
):
    """Validate one exact bounded QC statistic without exporting its receipt."""

    projection = require_pit_market_cap_membership_probe_qc_projection(projection)
    if plan_bytes != projection.plan_bytes:
        raise PitMarketCapMembershipProbeError(
            "attestation plan differs from projection"
        )
    plan = _validate_plan(plan_bytes)
    if len(plan["decision_sessions"]) != EXPECTED_CANARY_SESSION_COUNT:
        raise PitMarketCapMembershipProbeError(
            "coverage canary session count changed"
        )
    value = _strict_attestation(summary_bytes)
    _validate_attestation_lineage(value, plan=plan, projection=projection)
    if value.get("status") == "completed":
        return _load_completed_attestation(
            value=value,
            summary_bytes=summary_bytes,
            plan=plan,
            projection=projection,
        )
    if value.get("status") == "named_refusal":
        return _load_named_refusal_attestation(
            value=value,
            summary_bytes=summary_bytes,
            plan=plan,
            projection=projection,
        )
    raise PitMarketCapMembershipProbeError(
        "coverage attestation status changed"
    )


def require_reviewed_pit_market_cap_membership_coverage_attestation(
    value: ReviewedPitMarketCapMembershipCoverageAttestation,
) -> ReviewedPitMarketCapMembershipCoverageAttestation:
    if type(value) is not ReviewedPitMarketCapMembershipCoverageAttestation:
        raise PitMarketCapMembershipProbeError(
            "reviewed coverage attestation type changed"
        )
    rebuilt = load_reviewed_pit_market_cap_membership_coverage_attestation(
        plan_bytes=value.projection.plan_bytes,
        projection=value.projection,
        summary_bytes=value.summary_bytes,
    )
    if type(rebuilt) is not type(value) or rebuilt != value:
        raise PitMarketCapMembershipProbeError(
            "reviewed coverage attestation changed"
        )
    return value


def require_pit_market_cap_membership_coverage_named_refusal(
    value: PitMarketCapMembershipCoverageNamedRefusal,
) -> PitMarketCapMembershipCoverageNamedRefusal:
    if type(value) is not PitMarketCapMembershipCoverageNamedRefusal:
        raise PitMarketCapMembershipProbeError(
            "coverage named-refusal type changed"
        )
    rebuilt = load_reviewed_pit_market_cap_membership_coverage_attestation(
        plan_bytes=value.projection.plan_bytes,
        projection=value.projection,
        summary_bytes=value.summary_bytes,
    )
    if type(rebuilt) is not type(value) or rebuilt != value:
        raise PitMarketCapMembershipProbeError(
            "coverage named-refusal changed"
        )
    return value


def _validate_session_censuses(
    receipt: Mapping[str, object], plan: Mapping[str, object]
) -> None:
    fetched_source_row_count = _nonnegative_int(
        receipt.get("fetched_source_row_count"), "fetched source row count"
    )
    if fetched_source_row_count > MAX_TOTAL_SOURCE_ROWS:
        raise PitMarketCapMembershipProbeError(
            "fetched source-row bound changed"
        )
    rows = receipt.get("session_censuses")
    if type(rows) is not list or len(rows) != len(plan["decision_sessions"]):
        raise PitMarketCapMembershipProbeError("session census geometry changed")
    if hashlib.sha256(canonical_json_bytes(rows)).hexdigest() != receipt.get(
        "session_census_sha256"
    ):
        raise PitMarketCapMembershipProbeError("session census hash changed")
    aggregate_names = (
        "fundamental_source_member_count",
        "fundamental_exact_sid_count",
        "fundamental_missing_or_invalid_sid_count",
        "fundamental_duplicate_exact_sid_count",
        "fundamental_duplicate_exact_sid_row_count",
        "positive_market_cap_count",
        "null_market_cap_count",
        "nonpositive_market_cap_count",
        "invalid_or_nonfinite_market_cap_count",
        "union_positive_member_count",
        "union_positive_market_cap_covered_count",
        "union_market_cap_uncovered_count",
    )
    observed_aggregate = {name: 0 for name in aggregate_names}
    etf_series = {
        ticker: {"members": [], "covered": []} for ticker in ETFS
    }
    union_members: list[int] = []
    union_covered: list[int] = []
    for geometry, row in zip(plan["decision_sessions"], rows, strict=True):
        if type(row) is not dict or set(row) != _SESSION_FIELDS:
            raise PitMarketCapMembershipProbeError("session census fields changed")
        if row["decision_session"] != geometry["decision_session"]:
            raise PitMarketCapMembershipProbeError("session census axis changed")
        decision = _session(row["decision_session"], "census decision session")
        fundamental_time = _local_timestamp(
            row["fundamental_collection_time_local"], "fundamental collection time"
        )
        decision_open = datetime(
            decision.year, decision.month, decision.day, 9, 30
        )
        if fundamental_time >= decision_open:
            raise PitMarketCapMembershipProbeError(
                "fundamental collection is not strictly pre-open"
            )
        if fundamental_time.date() < decision - timedelta(
            days=HISTORY_ASOF_LOOKBACK_CALENDAR_DAYS
        ):
            raise PitMarketCapMembershipProbeError(
                "fundamental collection escaped the reviewed lookback"
            )
        for name in aggregate_names:
            observed_aggregate[name] += _nonnegative_int(row[name], name)
        if (
            row["fundamental_exact_sid_count"]
            + row["fundamental_missing_or_invalid_sid_count"]
            + row["fundamental_duplicate_exact_sid_row_count"]
            != row["fundamental_source_member_count"]
            or row["positive_market_cap_count"]
            + row["null_market_cap_count"]
            + row["nonpositive_market_cap_count"]
            + row["invalid_or_nonfinite_market_cap_count"]
            != row["fundamental_exact_sid_count"]
            or row["fundamental_duplicate_exact_sid_count"]
            > row["fundamental_exact_sid_count"]
            or row["fundamental_duplicate_exact_sid_count"]
            > row["fundamental_duplicate_exact_sid_row_count"]
            or (row["fundamental_duplicate_exact_sid_count"] == 0)
            != (row["fundamental_duplicate_exact_sid_row_count"] == 0)
        ):
            raise PitMarketCapMembershipProbeError(
                "fundamental session census does not reconcile"
            )
        etfs = row["etfs"]
        if type(etfs) is not dict or set(etfs) != set(ETFS):
            raise PitMarketCapMembershipProbeError("ETF census inventory changed")
        for ticker in ETFS:
            item = etfs[ticker]
            expected_fields = {
                "collection_availability_time_local",
                "source_row_count",
                "positive_member_count",
                "positive_market_cap_covered_count",
                "market_cap_uncovered_count",
            }
            if type(item) is not dict or set(item) != expected_fields:
                raise PitMarketCapMembershipProbeError("ETF census fields changed")
            collected = _local_timestamp(
                item["collection_availability_time_local"], "ETF collection availability time"
            )
            if collected.time() != datetime.min.time() or collected.date() >= decision:
                raise PitMarketCapMembershipProbeError(
                    "ETF collection is not strictly prior to decision midnight"
                )
            for name in expected_fields - {"collection_availability_time_local"}:
                _nonnegative_int(item[name], f"ETF {name}")
            if (
                item["positive_member_count"] > item["source_row_count"]
                or item["positive_market_cap_covered_count"]
                + item["market_cap_uncovered_count"]
                != item["positive_member_count"]
                or item["positive_market_cap_covered_count"]
                > row["positive_market_cap_count"]
                or item["source_row_count"] > MAX_COLLECTION_ROWS
            ):
                raise PitMarketCapMembershipProbeError("ETF census does not reconcile")
            etf_series[ticker]["members"].append(item["positive_member_count"])
            etf_series[ticker]["covered"].append(
                item["positive_market_cap_covered_count"]
            )
        for name in (
            "spy_qqq_overlap_count",
            "spy_soxx_overlap_count",
            "qqq_soxx_overlap_count",
            "triple_overlap_count",
        ):
            _nonnegative_int(row[name], name)
        inclusion_exclusion = (
            sum(etfs[ticker]["positive_member_count"] for ticker in ETFS)
            - row["spy_qqq_overlap_count"]
            - row["spy_soxx_overlap_count"]
            - row["qqq_soxx_overlap_count"]
            + row["triple_overlap_count"]
        )
        if (
            row["union_positive_member_count"] != inclusion_exclusion
            or row["union_positive_market_cap_covered_count"]
            + row["union_market_cap_uncovered_count"]
            != row["union_positive_member_count"]
            or row["union_positive_market_cap_covered_count"]
            > row["positive_market_cap_count"]
            or row["spy_qqq_overlap_count"]
            > min(
                etfs["SPY"]["positive_member_count"],
                etfs["QQQ"]["positive_member_count"],
            )
            or row["spy_soxx_overlap_count"]
            > min(
                etfs["SPY"]["positive_member_count"],
                etfs["SOXX"]["positive_member_count"],
            )
            or row["qqq_soxx_overlap_count"]
            > min(
                etfs["QQQ"]["positive_member_count"],
                etfs["SOXX"]["positive_member_count"],
            )
            or row["triple_overlap_count"]
            > min(
                row["spy_qqq_overlap_count"],
                row["spy_soxx_overlap_count"],
                row["qqq_soxx_overlap_count"],
            )
        ):
            raise PitMarketCapMembershipProbeError("ETF union census does not reconcile")
        union_members.append(row["union_positive_member_count"])
        union_covered.append(row["union_positive_market_cap_covered_count"])
    if receipt.get("aggregate") != observed_aggregate:
        raise PitMarketCapMembershipProbeError("aggregate census changed")
    expected_etf_bounds = {
        ticker: {
            "minimum_positive_member_count": min(etf_series[ticker]["members"]),
            "maximum_positive_member_count": max(etf_series[ticker]["members"]),
            "minimum_market_cap_covered_count": min(etf_series[ticker]["covered"]),
            "maximum_market_cap_covered_count": max(etf_series[ticker]["covered"]),
        }
        for ticker in ETFS
    }
    if receipt.get("etf_bounds") != expected_etf_bounds:
        raise PitMarketCapMembershipProbeError("ETF count bounds changed")
    if receipt.get("union_bounds") != {
        "minimum_positive_member_count": min(union_members),
        "maximum_positive_member_count": max(union_members),
        "minimum_market_cap_covered_count": min(union_covered),
        "maximum_market_cap_covered_count": max(union_covered),
    }:
        raise PitMarketCapMembershipProbeError("ETF union bounds changed")


def load_reviewed_pit_market_cap_membership_probe_receipt(
    *,
    plan_bytes: bytes,
    projection: PitMarketCapMembershipProbeQcProjection,
    terminal_pointer_bytes: bytes,
    receipt_bytes: bytes,
) -> ReviewedPitMarketCapMembershipCoverageReceipt:
    """Validate two exact Object Store objects and mint the compact receipt."""

    projection = require_pit_market_cap_membership_probe_qc_projection(projection)
    if plan_bytes != projection.plan_bytes:
        raise PitMarketCapMembershipProbeError("receipt plan differs from projection")
    plan = _validate_plan(plan_bytes)
    pointer = _strict_json(
        terminal_pointer_bytes,
        "coverage terminal pointer",
        MAX_TERMINAL_POINTER_BYTES,
    )
    pointer_fields = {
        "schema",
        "contract_sha256",
        "status",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "receipt_key",
        "receipt_sha256",
        "receipt_byte_count",
        "outcome_access_performed",
        "price_or_return_access_performed",
        "orders_or_portfolio_actions_performed",
    }
    if (
        set(pointer) != pointer_fields
        or pointer.get("schema") != TERMINAL_POINTER_SCHEMA
        or pointer.get("contract_sha256") != CONTRACT_SHA256
        or pointer.get("status") != "completed"
        or pointer.get("plan_id") != plan["plan_id"]
        or pointer.get("plan_sha256") != plan["plan_sha256"]
        or pointer.get("project_source_set_sha256")
        != projection.project_source_set_sha256
        or pointer.get("receipt_sha256") != hashlib.sha256(receipt_bytes).hexdigest()
        or pointer.get("receipt_byte_count") != len(receipt_bytes)
        or pointer.get("outcome_access_performed") is not False
        or pointer.get("price_or_return_access_performed") is not False
        or pointer.get("orders_or_portfolio_actions_performed") is not False
    ):
        raise PitMarketCapMembershipProbeError("terminal pointer binding changed")
    _sha(pointer["receipt_sha256"], "receipt object SHA-256")
    expected_receipt_key = (
        OUTPUT_PREFIX + "receipts/" + pointer["receipt_sha256"] + ".json"
    )
    if _key(pointer["receipt_key"], "receipt object key") != expected_receipt_key:
        raise PitMarketCapMembershipProbeError("receipt object key changed")
    receipt = _strict_json(receipt_bytes, "coverage receipt", MAX_RECEIPT_BYTES)
    receipt_fields = {
        "schema",
        "contract_sha256",
        "receipt_id",
        "receipt_sha256",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "first_session",
        "last_session",
        "decision_session_count",
        "history_call_count",
        "fetched_source_row_count",
        "etfs",
        "session_census_sha256",
        "session_censuses",
        "aggregate",
        "etf_bounds",
        "union_bounds",
        "capabilities",
    }
    semantic = dict(receipt)
    semantic["receipt_id"] = None
    semantic["receipt_sha256"] = None
    semantic_sha256 = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    if (
        set(receipt) != receipt_fields
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("contract_sha256") != CONTRACT_SHA256
        or receipt.get("receipt_id")
        != "arv2-pit-market-cap-membership-coverage-v3-" + semantic_sha256[:24]
        or receipt.get("receipt_sha256") != semantic_sha256
        or receipt.get("plan_id") != plan["plan_id"]
        or receipt.get("plan_sha256") != plan["plan_sha256"]
        or receipt.get("project_source_set_sha256")
        != projection.project_source_set_sha256
        or receipt.get("first_session") != plan["first_session"]
        or receipt.get("last_session") != plan["last_session"]
        or receipt.get("decision_session_count")
        != len(plan["decision_sessions"])
        or receipt.get("history_call_count")
        != plan["resource_census"]["history_call_count"]
        or receipt.get("etfs") != list(ETFS)
        or receipt.get("capabilities")
        != {
            "fundamental_history_access_performed": True,
            "etf_constituent_history_access_performed": True,
            "market_cap_field_access_performed": True,
            "price_or_return_access_performed": False,
            "outcome_or_result_access_performed": False,
            "orders_or_portfolio_actions_performed": False,
            "raw_rows_ids_weights_or_values_emitted": False,
        }
    ):
        raise PitMarketCapMembershipProbeError("coverage receipt lineage changed")
    _validate_session_censuses(receipt, plan)
    return ReviewedPitMarketCapMembershipCoverageReceipt(
        schema="arv2-reviewed-pit-market-cap-membership-coverage-receipt-v3",
        receipt_id=receipt["receipt_id"],
        receipt_sha256=receipt["receipt_sha256"],
        contract_sha256=CONTRACT_SHA256,
        plan_id=plan["plan_id"],
        plan_sha256=plan["plan_sha256"],
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        first_session=plan["first_session"],
        last_session=plan["last_session"],
        decision_session_count=receipt["decision_session_count"],
        history_call_count=receipt["history_call_count"],
        session_census_sha256=receipt["session_census_sha256"],
        receipt_object_key=pointer["receipt_key"],
        receipt_byte_count=len(receipt_bytes),
        terminal_pointer_sha256=hashlib.sha256(terminal_pointer_bytes).hexdigest(),
        terminal_pointer_byte_count=len(terminal_pointer_bytes),
        outcome_access_performed=False,
        price_or_return_access_performed=False,
        orders_or_portfolio_actions_performed=False,
        plan_bytes=bytes(plan_bytes),
        terminal_pointer_bytes=bytes(terminal_pointer_bytes),
        receipt_bytes=bytes(receipt_bytes),
        projection=projection,
    )


def require_reviewed_pit_market_cap_membership_coverage_receipt(
    value: ReviewedPitMarketCapMembershipCoverageReceipt,
) -> ReviewedPitMarketCapMembershipCoverageReceipt:
    if type(value) is not ReviewedPitMarketCapMembershipCoverageReceipt:
        raise PitMarketCapMembershipProbeError("reviewed coverage receipt type changed")
    rebuilt = load_reviewed_pit_market_cap_membership_probe_receipt(
        plan_bytes=value.plan_bytes,
        projection=value.projection,
        terminal_pointer_bytes=value.terminal_pointer_bytes,
        receipt_bytes=value.receipt_bytes,
    )
    if value != rebuilt:
        raise PitMarketCapMembershipProbeError("reviewed coverage receipt changed")
    return value


def pit_coverage_receipt_binding_record(
    value: ReviewedPitMarketCapMembershipCoverageReceipt,
) -> dict[str, object]:
    value = require_reviewed_pit_market_cap_membership_coverage_receipt(value)
    return {
        "schema": value.schema,
        "receipt_id": value.receipt_id,
        "receipt_sha256": value.receipt_sha256,
        "contract_sha256": value.contract_sha256,
        "plan_id": value.plan_id,
        "plan_sha256": value.plan_sha256,
        "projection_id": value.projection_id,
        "projection_sha256": value.projection_sha256,
        "project_source_set_sha256": value.project_source_set_sha256,
        "first_session": value.first_session,
        "last_session": value.last_session,
        "decision_session_count": value.decision_session_count,
        "history_call_count": value.history_call_count,
        "session_census_sha256": value.session_census_sha256,
        "receipt_object_key": value.receipt_object_key,
        "receipt_byte_count": value.receipt_byte_count,
        "terminal_pointer_sha256": value.terminal_pointer_sha256,
        "terminal_pointer_byte_count": value.terminal_pointer_byte_count,
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }


__all__ = [
    "ATTESTATION_SCHEMA",
    "BACKTEST_NAME",
    "CONTRACT_ID",
    "CONTRACT_SHA256",
    "ENTRY_PATH",
    "ETFS",
    "EXPECTED_CANARY_SESSION_COUNT",
    "FAILURE_SCHEMA",
    "INPUT_PREFIX",
    "OUTPUT_PREFIX",
    "MAX_SUMMARY_CHARACTERS",
    "PitCoverageProbeProjectSource",
    "PitMarketCapMembershipCoverageNamedRefusal",
    "PitMarketCapMembershipProbeError",
    "PitMarketCapMembershipProbeQcProjection",
    "PROJECT_NAME",
    "RECEIPT_SCHEMA",
    "RUNTIME_PATH",
    "ReviewedPitMarketCapMembershipCoverageAttestation",
    "ReviewedPitMarketCapMembershipCoverageReceipt",
    "SUMMARY_NAME",
    "TERMINAL_POINTER_SCHEMA",
    "build_pit_market_cap_membership_probe_plan_bytes",
    "build_pit_market_cap_membership_probe_qc_projection",
    "canonical_json_bytes",
    "load_reviewed_pit_market_cap_membership_coverage_attestation",
    "load_reviewed_pit_market_cap_membership_probe_receipt",
    "pit_coverage_receipt_binding_record",
    "pit_market_cap_membership_contract_record",
    "require_pit_market_cap_membership_probe_qc_projection",
    "require_pit_market_cap_membership_coverage_named_refusal",
    "require_reviewed_pit_market_cap_membership_coverage_attestation",
    "require_reviewed_pit_market_cap_membership_coverage_receipt",
]
