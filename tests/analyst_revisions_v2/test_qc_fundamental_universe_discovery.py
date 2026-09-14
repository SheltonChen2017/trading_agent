from __future__ import annotations

import ast
import base64
import dataclasses
import hashlib
import inspect
import json
import os
import stat
import sys
import types
import weakref
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data.exchange_calendar import trading_sessions
import research.analyst_revisions_v2_qc.fundamental_universe_discovery as discovery
import research.analyst_revisions_v2_qc.fundamental_universe_discovery_submission_adapter as submission
import research.analyst_revisions_v2_qc.formal_qc_transport as transport_module
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)
from research.analyst_revisions_v2_qc.fundamental_universe_discovery import (
    ARCHIVE_MANIFEST_NAME,
    ARCHIVE_PACKAGE_NAME,
    ARCHIVE_SHARD_DIRECTORY,
    FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT,
    FORMAL_SOURCE_AXIS_FIRST_SESSION,
    FORMAL_SOURCE_AXIS_LAST_SESSION,
    MAX_DECISION_SESSIONS,
    FundamentalUniverseDiscoveryError,
    build_fundamental_universe_discovery_plan_bytes,
    build_fundamental_universe_discovery_qc_projection,
    fundamental_discovery_artifact_binding_record,
    fundamental_universe_discovery_contract_record,
    iter_reviewed_fundamental_discovery_terminal_shards,
    load_reviewed_fundamental_universe_discovery_receipt,
    require_reviewed_fundamental_universe_discovery_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "research" / "analyst_revisions_v2_qc"
WORKER_PATH = SOURCE_ROOT / "fundamental_universe_discovery_worker.py"
RUNTIME_PATH = SOURCE_ROOT / "fundamental_universe_discovery_runtime.py"
NEW_YORK = ZoneInfo("America/New_York")


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name: str, value: object):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    rebound = types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        tuple(
            _closure_cell(value) if freevar == name else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _with_global_values(function, **replacements):
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    rebound = types.FunctionType(
        function.__code__,
        namespace,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _direct_closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    return cells[name].cell_contents


def _install_offline_discovery_action_binding_guards(monkeypatch) -> None:
    """Install a test-local authority which production requires cannot see."""

    offline_guard = lambda _operation: None
    offline_pid = os.getpid()
    offline_records = {}

    def public_registry(kind):
        return (
            submission._LAUNCH_AUTHORITIES
            if kind == "launch"
            else submission._TERMINAL_AUTHORITIES
            if kind == "terminal"
            else submission._OUTPUT_AUTHORITIES
        )

    def store(kind, value, *lineage):
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda _ref, category=kind, key=identity: offline_records.pop(
                (category, key), None
            ),
        )
        entry = (reference, *lineage, offline_pid)
        offline_records[(kind, identity)] = entry
        public_registry(kind)[identity] = entry

    def current(kind, value):
        identity = id(value)
        entry = offline_records.get((kind, identity))
        if (
            os.getpid() != offline_pid
            or entry is None
            or entry[0]() is not value
            or public_registry(kind).get(identity) is not entry
        ):
            offline_records.pop((kind, identity), None)
            public_registry(kind).pop(identity, None)
            return None
        return entry

    current_launch = lambda value: current("launch", value)
    current_terminal = lambda value: current("terminal", value)
    current_output = lambda value: current("output", value)

    def register_launch(value, *, plan, permit):
        store(
            "launch",
            value,
            plan,
            permit,
            submission._canonical({
                "schema": submission.LAUNCH_SCHEMA,
                **submission._launch_record(value),
            }),
        )

    def register_terminal(value, *, plan, permit, launch):
        store(
            "terminal",
            value,
            plan,
            permit,
            launch,
            submission._canonical({
                "schema": submission.TERMINAL_STATUS_SCHEMA,
                **submission._terminal_record(value),
            }),
        )

    def register_output(value, *, plan, permit, launch, terminal):
        store(
            "output",
            value,
            plan,
            permit,
            launch,
            terminal,
            submission._canonical(submission._output_record(value)),
        )

    require_launch = _with_closure_value(
        submission.require_fundamental_discovery_launch_receipt,
        "binding_guard",
        offline_guard,
    )
    require_launch = _with_closure_value(
        require_launch,
        "current_launch",
        current_launch,
    )
    require_terminal = _with_closure_value(
        submission.require_fundamental_discovery_terminal_status_receipt,
        "binding_guard",
        offline_guard,
    )
    require_terminal = _with_closure_value(
        require_terminal,
        "require_fundamental_discovery_launch_receipt",
        require_launch,
    )
    require_terminal = _with_closure_value(
        require_terminal,
        "current_terminal",
        current_terminal,
    )
    require_output = _with_closure_value(
        submission.require_fundamental_discovery_action_output,
        "binding_guard",
        offline_guard,
    )
    require_output = _with_closure_value(
        require_output,
        "require_fundamental_discovery_terminal_status_receipt",
        require_terminal,
    )
    require_output = _with_closure_value(
        require_output,
        "current_output",
        current_output,
    )

    requirements = {
        "require_fundamental_discovery_launch_receipt": require_launch,
        "require_fundamental_discovery_terminal_status_receipt": require_terminal,
        "require_fundamental_discovery_action_output": require_output,
    }
    for name, function in requirements.items():
        monkeypatch.setattr(submission, name, function)

    specifications = (
        (
            "execute_fundamental_discovery_submission_once",
            "register_launch",
            register_launch,
            (
                (
                    "require_fundamental_discovery_launch_receipt",
                    require_launch,
                ),
            ),
        ),
        (
            "inspect_fundamental_discovery_terminal_status",
            "register_terminal",
            register_terminal,
            (
                (
                    "require_fundamental_discovery_launch_receipt",
                    require_launch,
                ),
                (
                    "require_fundamental_discovery_terminal_status_receipt",
                    require_terminal,
                ),
            ),
        ),
        (
            "download_and_review_fundamental_discovery_archive",
            "register_output",
            register_output,
            (
                (
                    "require_fundamental_discovery_terminal_status_receipt",
                    require_terminal,
                ),
                (
                    "require_fundamental_discovery_action_output",
                    require_output,
                ),
            ),
        ),
    )
    for (
        action_name,
        registrar_name,
        registrar,
        nested_requirements,
    ) in specifications:
        action = getattr(submission, action_name)
        action = _with_closure_value(action, registrar_name, registrar)
        action = _with_closure_value(action, "binding_guard", offline_guard)
        for closure_name, function in nested_requirements:
            action = _with_closure_value(action, closure_name, function)
        monkeypatch.setattr(submission, action_name, action)


@pytest.mark.parametrize(
    "name",
    (
        "_transport_capability_minter",
        "_execute_fundamental_discovery_submission_once_impl",
        "_inspect_fundamental_discovery_terminal_status_impl",
        "_download_and_review_fundamental_discovery_archive_impl",
        "_bind_transport_capability_consumers",
        "_make_discovery_return_authority",
        "_seal_discovery_return_producers",
        "_discovery_return_register_launch",
        "_discovery_return_register_terminal",
        "_discovery_return_register_output",
        "_make_discovery_action_global_binding_guard",
        "_seal_discovery_action_global_bindings",
        "_require_discovery_action_global_bindings",
    ),
)
def test_discovery_transport_authority_primitives_are_not_module_addressable(name):
    assert not hasattr(submission, name)


def test_reflected_discovery_transport_minter_cannot_self_mint():
    function = submission.execute_fundamental_discovery_submission_once
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    with pytest.raises(
        submission.formal.FormalQcSubmissionError,
        match="caller changed",
    ):
        cells["minter"].cell_contents(
            transport=object(),
            scope="result_read",
            binding_record={"schema": "forbidden"},
            call_budget={"backtests/read": 1},
        )


def _session_rows(count: int, *, first: date = date(2021, 1, 4)):
    rows = []
    cursor = first
    while len(rows) < count:
        if cursor.weekday() < 5:
            opened = datetime.combine(cursor, time(9, 30), tzinfo=NEW_YORK)
            rows.append(
                {
                    "decision_session": cursor.isoformat(),
                    "decision_session_ordinal": len(rows) + 1,
                    "decision_open_utc": opened.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                }
            )
        cursor += timedelta(days=1)
    return rows


def _formal_source_axis_rows():
    first = date.fromisoformat(FORMAL_SOURCE_AXIS_FIRST_SESSION)
    last = date.fromisoformat(FORMAL_SOURCE_AXIS_LAST_SESSION)
    sessions = trading_sessions(first, last)
    return [
        {
            "decision_session": session.isoformat(),
            "decision_session_ordinal": ordinal,
            "decision_open_utc": datetime.combine(
                session, time(9, 30), tzinfo=NEW_YORK
            ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        for ordinal, session in enumerate(sessions, start=1)
    ]


def _projection(count: int = 2, *, sessions=None):
    sessions = _session_rows(count) if sessions is None else list(sessions)
    calculation = (
        date.fromisoformat(sessions[-1]["decision_session"]) + timedelta(days=1)
    ).isoformat()
    plan = build_fundamental_universe_discovery_plan_bytes(
        decision_sessions=sessions,
        calculation_session=calculation,
    )
    projection = build_fundamental_universe_discovery_qc_projection(
        plan_bytes=plan,
        worker_source_bytes=WORKER_PATH.read_bytes(),
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
    )
    return sessions, plan, projection


class _Node:
    def __init__(self, **values):
        self.__dict__.update(values)


def _fundamental(
    index: int,
    *,
    ticker: str | None = None,
    country: str = "USA",
    cusip: str | None = None,
    qc_sid: str | None = None,
    delisting_date: date | None = date(2025, 1, 2),
):
    return _Node(
        symbol=_Node(
            id=qc_sid or f"SID-{index:05d}-USA",
            value=ticker or f"T{index:05d}",
            cusip=cusip or f"{index:08d}A",
        ),
        company_reference=_Node(
            company_id=f"MS-COMPANY-{index:05d}",
            country_id=country,
            primary_exchange_id="NAS",
            cik=f"{index + 1:010d}",
        ),
        security_reference=_Node(
            investment_id=f"MS-INVESTMENT-{index:05d}",
            security_type="ST00000001",
            is_depositary_receipt=False,
            is_primary_share=True,
            common_share_sub_type="A",
            delisting_date=delisting_date,
        ),
        asset_classification=_Node(
            morningstar_sector_code=101,
            morningstar_industry_group_code=10101,
            morningstar_industry_code=10101010,
        ),
        financial_statements=_Node(period_ending_date=date(2020, 9, 30)),
        company_profile=_Node(
            share_class_level_shares_outstanding=Decimal("1000000")
        ),
    )


def _project_source(projection, path: str) -> str:
    return next(
        source.content.decode("utf-8")
        for source in projection.source_files
        if source.project_path == path
    )


def _worker_namespace(projection) -> dict[str, object]:
    namespace: dict[str, object] = {}
    source = _project_source(projection, discovery.WORKER_PATH)
    exec(compile(source, discovery.WORKER_PATH, "exec"), namespace)
    return namespace


class _ObjectStore:
    def __init__(self, initial: dict[str, bytes]):
        self.values = dict(initial)
        self.max_size = discovery.MIN_OBJECT_STORE_CAPACITY_BYTES
        self.max_files = discovery.MIN_OBJECT_STORE_FILE_CAPACITY

    def read_bytes(self, key: str) -> bytes:
        return self.values[key]

    def save_bytes(self, key: str, payload: bytes) -> bool:
        self.values[key] = bytes(payload)
        return True


class _HistoryGateway:
    def __init__(self, marker: type, collections: list[_Node]):
        self.marker = marker
        self.collections = collections
        self.calls: list[tuple[datetime, datetime]] = []

    def __getitem__(self, item):
        if item is not self.marker:
            raise AssertionError("runtime requested a non-Fundamentals dataset")

        def request(start: datetime, end: datetime):
            self.calls.append((start, end))
            return [
                item
                for item in self.collections
                if start.date() <= item.time.date() < end.date()
            ]

        return request


class _Algorithm:
    def __init__(self, store: _ObjectStore, history: _HistoryGateway):
        self.object_store = store
        self.history = history
        self.summary: dict[str, str] = {}
        self._arv2_fundamental_discovery_completed = False

    def set_summary_statistic(self, name: str, value: str) -> None:
        self.summary[name] = value


def _runtime_fixture(
    monkeypatch,
    *,
    count: int,
    collection_hour: int = 0,
    sessions=None,
):
    sessions, plan, projection = _projection(count, sessions=sessions)
    worker_module = types.ModuleType("fundamental_universe_discovery_worker")
    exec(
        compile(
            _project_source(projection, discovery.WORKER_PATH),
            discovery.WORKER_PATH,
            "exec",
        ),
        worker_module.__dict__,
    )
    algorithm_imports = types.ModuleType("AlgorithmImports")

    class Fundamentals:
        pass

    algorithm_imports.Fundamentals = Fundamentals
    monkeypatch.setitem(
        sys.modules, "fundamental_universe_discovery_worker", worker_module
    )
    monkeypatch.setitem(sys.modules, "AlgorithmImports", algorithm_imports)
    runtime_module = types.ModuleType("fundamental_universe_discovery_runtime")
    exec(
        compile(
            _project_source(projection, discovery.RUNTIME_PATH),
            discovery.RUNTIME_PATH,
            "exec",
        ),
        runtime_module.__dict__,
    )
    collections = [
        _Node(
            time=datetime.combine(
                date.fromisoformat(geometry["decision_session"]),
                time(collection_hour),
            ),
            data=[_fundamental(index)],
        )
        for index, geometry in enumerate(sessions, start=1)
    ]
    store = _ObjectStore({projection.plan_object_store_key: plan})
    history = _HistoryGateway(Fundamentals, collections)
    algorithm = _Algorithm(store, history)
    constants = {
        "PLAN_ID": projection.plan_id,
        "PLAN_SHA256": projection.plan_artifact_sha256,
        "PLAN_BYTE_COUNT": projection.plan_byte_count,
        "PLAN_OBJECT_STORE_KEY": projection.plan_object_store_key,
        "TERMINAL_PACKAGE_KEY": projection.terminal_package_key,
        "PROJECT_SOURCE_SET_SHA256": projection.project_source_set_sha256,
        "SUMMARY_NAME": discovery.SUMMARY_NAME,
    }
    return (
        sessions,
        plan,
        projection,
        runtime_module,
        algorithm,
        constants,
    )


def _write_archive(tmp_path: Path, projection, store: _ObjectStore) -> Path:
    package = store.values[projection.terminal_package_key]
    package_record = json.loads(package)
    manifest = store.values[package_record["output_manifest_key"]]
    manifest_record = json.loads(manifest)
    root = tmp_path / "discovery-archive"
    root.mkdir(mode=0o700)
    shard_root = root / ARCHIVE_SHARD_DIRECTORY
    shard_root.mkdir(mode=0o700)
    package_path = root / ARCHIVE_PACKAGE_NAME
    manifest_path = root / ARCHIVE_MANIFEST_NAME
    package_path.write_bytes(package)
    manifest_path.write_bytes(manifest)
    package_path.chmod(0o600)
    manifest_path.chmod(0o600)
    for descriptor in manifest_record["terminal_shards"]:
        payload = store.values[descriptor["object_store_key"]]
        path = shard_root / (
            f'{descriptor["ordinal"]:04d}-'
            f'{descriptor["compressed_sha256"]}.jsonl.gz'
        )
        path.write_bytes(payload)
        path.chmod(0o600)
    return root


def _assert_no_duplicate_literal_dict_keys(source: str) -> None:
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        keys = [
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and type(key.value) is str
        ]
        assert len(keys) == len(set(keys))


def test_contract_plan_and_projection_are_scoped_bounded_and_outcome_free():
    contract = fundamental_universe_discovery_contract_record()
    assert contract["formal_source_axis"] == {
        "first_session_inclusive": "2013-01-02",
        "last_session_inclusive": "2025-12-31",
        "nyse_decision_session_count": 3_270,
        "purpose": (
            "pre-open source coverage for every training, validation, and "
            "test session needed by the fixed 2020-2025 formal folds"
        ),
        "formal_outcome_test_interval_changed": False,
    }
    assert contract["formal_source_axis"] == {
        "first_session_inclusive": "2013-01-02",
        "last_session_inclusive": "2025-12-31",
        "nyse_decision_session_count": 3_270,
        "purpose": (
            "pre-open source coverage for every training, validation, and test "
            "session needed by the fixed 2020-2025 formal folds"
        ),
        "formal_outcome_test_interval_changed": False,
    }
    assert contract["source"]["all_us_equities_including_delisted"] is True
    assert contract["source"]["current_ticker_is_not_identity"] is True
    assert contract["decision_clock"]["assigned_time_is_vendor_publication_timestamp"] is False
    assert contract["affirmative_scope"]["off_qc_security_master_established"] is False
    assert contract["affirmative_scope"]["production_preopen_input_available"] is False
    assert contract["discovery_fields"]["statement_currency_assumed"] is False
    assert contract["discovery_fields"]["book_equity_or_revenue_emitted"] is False
    assert not discovery.PROJECT_NAME.startswith("1.")
    assert discovery.PROJECT_NAME == (
        "1 ARV2_FUNDAMENTAL_UNIVERSE_DISCOVERY - 20260912"
    )

    sessions, plan, projection = _projection(2)
    assert sessions[0]["decision_open_utc"] == "2021-01-04T14:30:00.000000Z"
    summer = _session_rows(1, first=date(2021, 7, 6))[0]
    assert summer["decision_open_utc"] == "2021-07-06T13:30:00.000000Z"
    assert projection.reads_fundamentals_history is True
    assert projection.reads_prices_or_returns is False
    assert projection.reads_outcomes_or_results is False
    assert projection.places_orders_or_touches_portfolio is False
    assert len(json.loads(plan)["history_chunks"]) == 1
    assert all(source.character_count <= 60_000 for source in projection.source_files)
    source_text = "\n".join(
        source.content.decode("utf-8") for source in projection.source_files
    )
    assert source_text.count("algorithm.history[Fundamentals]") == 1
    assert "set_time_zone(\"America/New_York\")" in source_text
    for source in projection.source_files:
        _assert_no_duplicate_literal_dict_keys(source.content.decode("utf-8"))
    assert "book_equity_usd" not in source_text
    assert "revenue_ttm_usd" not in source_text

    noncontiguous = _session_rows(2)
    noncontiguous[1]["decision_session_ordinal"] = 3
    with pytest.raises(
        FundamentalUniverseDiscoveryError,
        match="ordinals must be contiguous from one",
    ):
        build_fundamental_universe_discovery_plan_bytes(
            decision_sessions=noncontiguous,
            calculation_session="2021-01-06",
        )


def test_source_axis_capacity_admits_3300_sessions_but_refuses_3301():
    sessions = _session_rows(MAX_DECISION_SESSIONS)
    last = date.fromisoformat(sessions[-1]["decision_session"])
    payload = build_fundamental_universe_discovery_plan_bytes(
        decision_sessions=sessions,
        calculation_session=(last + timedelta(days=1)).isoformat(),
    )
    plan = json.loads(payload)
    assert plan["resource_census"]["decision_session_count"] == 3_300
    assert plan["resource_census"]["history_call_count"] == 165
    with pytest.raises(FundamentalUniverseDiscoveryError, match="session cap"):
        build_fundamental_universe_discovery_plan_bytes(
            decision_sessions=_session_rows(MAX_DECISION_SESSIONS + 1),
            calculation_session=(last + timedelta(days=8)).isoformat(),
        )


def test_exact_formal_source_axis_runtime_and_receipt_commit_every_session(
    monkeypatch, tmp_path
):
    sessions = _formal_source_axis_rows()
    assert len(sessions) == FORMAL_SOURCE_AXIS_DECISION_SESSION_COUNT == 3_270
    assert sessions[0]["decision_session"] == FORMAL_SOURCE_AXIS_FIRST_SESSION
    assert sessions[-1]["decision_session"] == FORMAL_SOURCE_AXIS_LAST_SESSION
    (
        _sessions,
        plan_bytes,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(
        monkeypatch,
        count=len(sessions),
        sessions=sessions,
    )
    plan = json.loads(plan_bytes)
    runtime_source = _project_source(projection, discovery.RUNTIME_PATH)
    assert "MAX_HISTORY_CALLS = 165" in runtime_source
    assert "MAX_TOTAL_SOURCE_ROWS = 82_500_000" in runtime_source
    assert "MAX_TERMINAL_SHARDS = 3_300" in runtime_source
    assert plan["resource_census"] == {
        "decision_session_count": 3_270,
        "history_call_count": 164,
        "history_chunk_session_count": 20,
        "maximum_decision_sessions": 3_300,
        "maximum_history_calls": 165,
        "maximum_collection_rows": 25_000,
        "maximum_total_source_rows": 82_500_000,
        "maximum_shard_rows": 500_000,
        "maximum_terminal_shards": 3_300,
        "maximum_uncompressed_shard_bytes": 256 * 1024 * 1024,
        "maximum_compressed_shard_bytes": 10 * 1024 * 1024,
        "maximum_total_compressed_output_bytes": 33_000 * 1024 * 1024,
        "minimum_object_store_capacity_bytes": (
            discovery.MIN_OBJECT_STORE_CAPACITY_BYTES
        ),
        "minimum_object_store_file_capacity": (
            discovery.MIN_OBJECT_STORE_FILE_CAPACITY
        ),
    }
    assert [
        session
        for chunk in plan["history_chunks"]
        for session in chunk["decision_sessions"]
    ] == [item["decision_session"] for item in sessions]

    manifest = runtime.execute_fundamental_universe_discovery(
        algorithm, constants
    )
    assert len(algorithm.history.calls) == 164
    assert manifest["first_session"] == FORMAL_SOURCE_AXIS_FIRST_SESSION
    assert manifest["last_session"] == FORMAL_SOURCE_AXIS_LAST_SESSION
    assert manifest["census"]["decision_session_count"] == 3_270
    assert [
        item["decision_session"]
        for item in manifest["decision_session_censuses"]
    ] == [item["decision_session"] for item in sessions]

    archive = _write_archive(tmp_path, projection, algorithm.object_store)
    receipt = load_reviewed_fundamental_universe_discovery_receipt(
        plan_bytes=plan_bytes,
        projection=projection,
        archive_root=archive,
    )
    assert receipt.first_session == FORMAL_SOURCE_AXIS_FIRST_SESSION
    assert receipt.last_session == FORMAL_SOURCE_AXIS_LAST_SESSION
    assert receipt.decision_session_count == 3_270
    assert receipt.full_pit_universe_established is True
    assert receipt.full_market_peer_census_established is True
    observed_sessions = []
    for shard in iter_reviewed_fundamental_discovery_terminal_shards(receipt):
        observed_sessions.extend(
            json.loads(line)["decision_session"]
            for line in shard.canonical_json_lines.splitlines()
        )
    assert observed_sessions == [item["decision_session"] for item in sessions]


def test_worker_binds_sid_cusip_classification_and_delisted_membership():
    _sessions, _plan, projection = _projection(1)
    worker = _worker_namespace(projection)
    geometry = _session_rows(1)[0]
    rows, census = worker["build_collection_terminals"](
        fundamentals=[_fundamental(1)],
        decision_session=geometry["decision_session"],
        decision_session_ordinal=geometry["decision_session_ordinal"],
        decision_open_utc=geometry["decision_open_utc"],
    )
    row = rows[0]
    assert row["disposition"] == "accepted"
    assert row["qc_security_id"] == "SID-00001-USA"
    assert row["cusip"] == "00000001A"
    assert row["primary_exchange_mic"] == "XNAS"
    assert row["morningstar_sector_code"] == 101
    assert row["morningstar_industry_group_code"] == 10101
    assert row["morningstar_industry_code"] == 10101010
    assert row["delisting_date"] == "2025-01-02"
    assert row["available_at"] == "2021-01-04T14:29:59.999999Z"
    assert row["shares_outstanding"] == "1000000"
    assert census["qc_sid_bound_count"] == 1
    assert census["all_source_members_terminal"] is True

    renamed, _ = worker["build_collection_terminals"](
        fundamentals=[_fundamental(1, ticker="RENAMED")],
        decision_session=geometry["decision_session"],
        decision_session_ordinal=geometry["decision_session_ordinal"],
        decision_open_utc=geometry["decision_open_utc"],
    )
    assert renamed[0]["display_ticker_non_authoritative"] == "RENAMED"
    assert renamed[0]["identity_evidence_sha256"] == row["identity_evidence_sha256"]


def test_worker_terminalizes_named_refusals_and_exact_out_of_scope_reason():
    _sessions, _plan, projection = _projection(1)
    worker = _worker_namespace(projection)
    geometry = _session_rows(1)[0]
    rows, census = worker["build_collection_terminals"](
        fundamentals=[
            _fundamental(1, country="CAN"),
            _fundamental(2, cusip="NOT-A-CUSIP"),
        ],
        decision_session=geometry["decision_session"],
        decision_session_ordinal=geometry["decision_session_ordinal"],
        decision_open_utc=geometry["decision_open_utc"],
    )
    assert rows[0]["disposition"] == "out_of_scope"
    assert rows[0]["refusal_reason"] == "issuer_incorporation_country_is_not_USA"
    assert rows[1]["disposition"] == "named_refusal"
    assert rows[1]["refusal_reason"] == "missing_or_invalid_CUSIP_cross_vendor_join_key"
    assert census["terminal_count"] == census["source_member_count"] == 2
    assert census["out_of_scope_count"] == 1
    assert census["named_refusal_count"] == 1

    with pytest.raises(ValueError, match="repeats a QC SecurityIdentifier"):
        worker["build_collection_terminals"](
            fundamentals=[
                _fundamental(1, qc_sid="DUPLICATE"),
                _fundamental(2, qc_sid="DUPLICATE"),
            ],
            decision_session=geometry["decision_session"],
            decision_session_ordinal=geometry["decision_session_ordinal"],
            decision_open_utc=geometry["decision_open_utc"],
        )


def test_runtime_archive_loader_and_streaming_receipt_are_exact(monkeypatch, tmp_path):
    (
        _sessions,
        plan,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=2)
    manifest = runtime.execute_fundamental_universe_discovery(algorithm, constants)
    assert algorithm._arv2_fundamental_discovery_completed is True
    assert len(algorithm.history.calls) == 1
    assert manifest["guarantees"]["every_collection_observed_before_decision_open"] is True
    assert manifest["guarantees"]["production_preopen_input_available"] is False
    assert manifest["capabilities"]["outcome_access_performed"] is False
    assert (
        manifest["capabilities"]["object_store_capacity_preflight_performed"]
        is True
    )
    archive = _write_archive(tmp_path, projection, algorithm.object_store)
    receipt = load_reviewed_fundamental_universe_discovery_receipt(
        plan_bytes=plan,
        projection=projection,
        archive_root=archive,
    )
    assert require_reviewed_fundamental_universe_discovery_receipt(receipt) is receipt
    assert receipt.full_pit_universe_established is True
    assert receipt.full_market_peer_census_established is True
    assert receipt.qc_history_collection_preopen_authenticated is True
    assert receipt.production_preopen_input_available is False
    assert receipt.requires_cross_vendor_usd_fundamental_bridge is True
    assert receipt.qc_sid_mapping_row_count == receipt.accepted_count == 2
    assert receipt.outcome_access_performed is False
    bindings = fundamental_discovery_artifact_binding_record(receipt)
    assert bindings["eligible_universe_source"]["artifact_id"] == (
        receipt.eligible_universe_artifact_id
    )
    assert bindings["qc_sid_mapping_source"]["content_sha256"] == (
        receipt.qc_sid_mapping_artifact_sha256
    )
    shards = list(iter_reviewed_fundamental_discovery_terminal_shards(receipt))
    assert len(shards) == 1
    rows = [json.loads(line) for line in shards[0].canonical_json_lines.splitlines()]
    assert [row["decision_session"] for row in rows] == [
        "2021-01-04",
        "2021-01-05",
    ]
    assert all(row["disposition"] == "accepted" for row in rows)

    shard_path = next((archive / ARCHIVE_SHARD_DIRECTORY).iterdir())
    shard_path.chmod(0o644)
    with pytest.raises(
        FundamentalUniverseDiscoveryError,
        match="owner-only regular file|identity changed",
    ):
        require_reviewed_fundamental_universe_discovery_receipt(receipt)


def test_loader_and_iterator_support_seven_shards_without_payload_mapping(
    monkeypatch, tmp_path
):
    (
        _sessions,
        plan,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=121)
    manifest = runtime.execute_fundamental_universe_discovery(algorithm, constants)
    assert len(manifest["terminal_shards"]) == 7
    archive = _write_archive(tmp_path, projection, algorithm.object_store)
    receipt = load_reviewed_fundamental_universe_discovery_receipt(
        plan_bytes=plan,
        projection=projection,
        archive_root=archive,
    )
    parameters = inspect.signature(
        load_reviewed_fundamental_universe_discovery_receipt
    ).parameters
    assert tuple(parameters) == ("plan_bytes", "projection", "archive_root")
    receipt_fields = {field.name for field in dataclasses.fields(receipt)}
    assert not any("shard_payload" in name for name in receipt_fields)
    row_count = 0
    shard_count = 0
    for shard in iter_reviewed_fundamental_discovery_terminal_shards(receipt):
        shard_count += 1
        row_count += shard.row_count
        assert hashlib.sha256(shard.canonical_json_lines).hexdigest() == (
            shard.uncompressed_sha256
        )
    assert shard_count == receipt.terminal_shard_count == 7
    assert row_count == receipt.terminal_count == 121


def test_runtime_refuses_a_collection_not_observed_before_open(monkeypatch):
    (
        _sessions,
        _plan,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=1, collection_hour=10)
    with pytest.raises(RuntimeError, match="discovery refused"):
        runtime.execute_fundamental_universe_discovery(algorithm, constants)
    assert algorithm._arv2_fundamental_discovery_completed is False
    package = json.loads(algorithm.object_store.values[projection.terminal_package_key])
    assert package["status"] == "named_refusal"
    assert package["outcome_access_performed"] is False
    assert package["price_or_return_access_performed"] is False


@pytest.mark.parametrize("capacity_field", ["max_size", "max_files"])
def test_runtime_refuses_insufficient_object_store_capacity_before_history(
    monkeypatch, capacity_field
):
    (
        _sessions,
        _plan,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=1)
    setattr(algorithm.object_store, capacity_field, 1)
    with pytest.raises(RuntimeError, match="discovery refused"):
        runtime.execute_fundamental_universe_discovery(algorithm, constants)
    assert algorithm.history.calls == []
    package = json.loads(
        algorithm.object_store.values[projection.terminal_package_key]
    )
    assert package["status"] == "named_refusal"
    assert package["outcome_access_performed"] is False


def test_archive_leaf_symlink_and_unreviewed_receipt_are_refused(
    monkeypatch, tmp_path
):
    (
        _sessions,
        plan,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=1)
    runtime.execute_fundamental_universe_discovery(algorithm, constants)
    archive = _write_archive(tmp_path, projection, algorithm.object_store)
    alias = tmp_path / "archive-alias"
    alias.symlink_to(archive, target_is_directory=True)
    with pytest.raises(FundamentalUniverseDiscoveryError, match="root is a symlink"):
        load_reviewed_fundamental_universe_discovery_receipt(
            plan_bytes=plan,
            projection=projection,
            archive_root=alias,
        )
    forged = object.__new__(discovery.ReviewedFundamentalUniverseDiscoveryReceipt)
    with pytest.raises(FundamentalUniverseDiscoveryError, match="loader-authenticated"):
        require_reviewed_fundamental_universe_discovery_receipt(forged)


class _DiscoveryQcBackend:
    def __init__(self, *, plan, output_objects: dict[str, bytes]):
        self.plan = plan
        self.objects = dict(output_objects)
        self.files: dict[str, str] = {}
        self.created = False
        self.events: list[str] = []
        self.fail_authenticate = False
        self.terminal_status = "Completed."

    def project(self):
        return {
            "projectId": 987,
            "organizationId": self.plan.organization_id,
            "name": self.plan.project_name,
            "language": "Py",
            "owner": True,
            "codeRunning": False,
            "collaborators": [{"owner": True}],
            "libraries": [],
        }

    def request(self, path: str, payload: dict[str, object]):
        self.events.append(path)
        assert (self.plan.review_directory / submission.PERMIT_FILENAME).exists()
        if path == "authenticate":
            if self.fail_authenticate:
                raise RuntimeError("ambiguous offline authentication")
            return {"success": True}
        if path == "projects/read":
            return {
                "success": True,
                "projects": [self.project()] if self.created else [],
            }
        if path == "projects/create":
            self.created = True
            return {"success": True, "projects": [self.project()]}
        if path == "files/read":
            return {
                "success": True,
                "files": [
                    {"name": name, "content": content}
                    for name, content in sorted(self.files.items())
                ],
            }
        if path == "files/create":
            self.files[payload["name"]] = payload["content"]
            return {"success": True}
        if path == "compile/create":
            return {"success": True, "compileId": "discovery-compile"}
        if path == "compile/read":
            return {
                "success": True,
                "compileId": "discovery-compile",
                "state": "BuildSuccess",
            }
        if path == "backtests/create":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "discovery-backtest",
                    "name": payload["backtestName"],
                    "projectId": 987,
                    "status": "In Queue...",
                },
            }
        if path == "backtests/list":
            assert payload["includeStatistics"] is False
            return {
                "success": True,
                "count": 1,
                "backtests": [
                    {
                        "backtestId": "discovery-backtest",
                        "name": self.plan.backtest_name,
                        "projectId": 987,
                        "status": self.terminal_status,
                        # The status parser permits but never indexes this value.
                        "statistics": {"Sharpe Ratio": "forbidden-result"},
                    }
                ],
            }
        if path == "object/read":
            value = self.objects[payload["key"]]
            return {
                "success": True,
                "object": {
                    "key": payload["key"],
                    "objectData": base64.b64encode(value).decode("ascii"),
                },
            }
        raise AssertionError(path)


def _discovery_transport(backend: _DiscoveryQcBackend):
    def http(url, body, headers, timeout):
        del timeout
        assert "Authorization" in headers
        path = url.split("/api/v2/", 1)[1]
        if path == "object/set":
            boundary = headers["Content-Type"].split("boundary=", 1)[1]
            key = body.split(b'name="key"\r\n\r\n', 1)[1].split(
                b"\r\n--" + boundary.encode(), 1
            )[0].decode()
            marker = (
                b'name="objectData"; filename="object.bin"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            backend.objects[key] = body.split(marker, 1)[1].rsplit(
                b"\r\n--" + boundary.encode() + b"--\r\n", 1
            )[0]
            backend.events.append(path)
            result = {"success": True}
        else:
            payload = json.loads(body)
            if path == "object/properties":
                stored = backend.objects[payload["key"]]
                backend.events.append(path)
                result = {
                    "success": True,
                    "metadata": {
                        "key": payload["key"],
                        "size": len(stored),
                        "md5": hashlib.md5(
                            stored, usedforsecurity=False
                        ).hexdigest(),
                    },
                }
            else:
                result = backend.request(path, payload)
        return 200, json.dumps(result, separators=(",", ":")).encode("utf-8")

    return transport_module.FormalQcTransport(
        http_transport=http,
        clock=lambda: 1_789_000_000,
    )


def _offline_owner_signature():
    value = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(value, "authority_sha256", "a" * 64)
    return value


def _submission_fixture(monkeypatch, tmp_path):
    tmp_path.chmod(0o700)
    (
        _sessions,
        _plan_bytes,
        projection,
        runtime,
        algorithm,
        constants,
    ) = _runtime_fixture(monkeypatch, count=2)
    runtime.execute_fundamental_universe_discovery(algorithm, constants)
    plan = submission.build_fundamental_discovery_submission_plan(
        projection=projection,
        organization_id="discovery-test-organization",
        review_directory=tmp_path,
        archive_root=tmp_path / "fundamental-universe-discovery-archive",
    )
    claim_path = tmp_path / submission.REVIEW_CLAIM_FILENAME
    claim_path.write_bytes(
        submission.render_fundamental_discovery_review_claim_candidate(plan)
    )
    claim_path.chmod(0o600)
    claim = submission.load_fundamental_discovery_review_claim(plan)
    backend = _DiscoveryQcBackend(
        plan=plan,
        output_objects=algorithm.object_store.values,
    )
    client = _discovery_transport(backend)
    monkeypatch.setattr(submission, "_require_owner_signature", lambda *_args: None)
    monkeypatch.setattr(
        submission.formal,
        "_require_concrete_transport",
        lambda value: value,
    )
    _install_offline_discovery_action_binding_guards(monkeypatch)

    def offline_minter(*, transport, scope, binding_record, call_budget):
        return transport_module._mint_offline_test_capability(
            transport,
            scope=scope,
            binding_record=binding_record,
            call_budget=call_budget,
        )

    for name in (
        "execute_fundamental_discovery_submission_once",
        "inspect_fundamental_discovery_terminal_status",
        "download_and_review_fundamental_discovery_archive",
    ):
        monkeypatch.setattr(
            submission,
            name,
            _with_closure_value(getattr(submission, name), "minter", offline_minter),
        )
    monkeypatch.setattr(submission, "_wait", lambda _seconds: None)
    return plan, claim, _offline_owner_signature(), client, backend


def test_offline_submission_adapter_executes_exact_outcome_free_flow(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    authority = json.loads(
        submission.render_fundamental_discovery_execution_authority_candidate(
            plan, claim
        )
    )
    assert plan.maximum_output_object_reads == 3_302
    assert authority["review_claim_sha256"] == claim.claim_sha256
    assert authority["actions"] == list(submission.EXECUTION_ACTIONS)
    assert authority["include_statistics"] is False
    assert authority["outcome_result_statistics_log_order_access"] is False
    permit, launch = submission.execute_fundamental_discovery_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        client=client,
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )
    terminal = submission.inspect_fundamental_discovery_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        client=client,
    )
    receipt = submission.download_and_review_fundamental_discovery_archive(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        terminal=terminal,
        client=client,
    )
    assert submission.require_fundamental_discovery_launch_receipt(
        launch, plan, permit
    ) is launch
    assert submission.require_fundamental_discovery_terminal_status_receipt(
        terminal, plan, permit, launch
    ) is terminal
    assert submission.require_fundamental_discovery_action_output(
        receipt, plan, permit, launch, terminal
    ) is receipt
    assert receipt.full_pit_universe_established is True
    assert receipt.production_preopen_input_available is False
    assert receipt.outcome_access_performed is False
    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("object/read") == 3
    assert "backtests/read" not in backend.events
    assert "projects/delete" not in backend.events
    assert set(backend.files) == {item.project_path for item in plan.source_files}
    assert plan.archive_root.is_dir()


def test_offline_submission_ambiguity_consumes_permit_and_forbids_retry(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    backend.fail_authenticate = True
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    observed = list(backend.events)
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit already spent",
    ):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-12T12:01:00.000000Z",
        )
    assert backend.events == observed


def _load_projects_read_schema_diagnostic(plan):
    path = plan.archive_root / submission.PROJECT_SCHEMA_DIAGNOSTIC_FILENAME
    payload = path.read_bytes()
    return path, payload, json.loads(payload)


def test_projects_read_diagnostic_requires_exact_phase_and_plan_bound_permit(
    monkeypatch, tmp_path
):
    plan, _claim, _owner_signature, _client, _backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    hostile_response = object()
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="phase changed",
    ):
        submission._persist_projects_read_schema_diagnostic(
            plan=plan,
            permit=object(),
            phase="files/read",
            response=hostile_response,
        )
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="permit changed",
    ):
        submission._persist_projects_read_schema_diagnostic(
            plan=plan,
            permit=object(),
            phase="initial_inventory",
            response=hostile_response,
        )
    assert not plan.archive_root.exists()


def test_projects_read_top_level_refusal_persists_keys_only_diagnostic(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request
    forbidden_values = (
        "PRIVATE PROJECT NAME MUST NOT LEAK",
        "PRIVATE CONTENT MUST NOT LEAK",
    )

    def request(path, payload):
        if path == "projects/read":
            backend.events.append(path)
            return {
                "success": True,
                "projects": [
                    {
                        "name": forbidden_values[0],
                        "content": forbidden_values[1],
                        "newProjectField": 17,
                    }
                ],
                "newTopLevelField": forbidden_values[1],
            }
        return original_request(path, payload)

    backend.request = request
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ) as caught:
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    assert type(caught.value.__cause__) is submission.formal.FormalQcSubmissionError

    path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    assert stat.S_IMODE(plan.archive_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    assert receipt["schema"] == submission.PROJECT_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA
    assert receipt["phase"] == "initial_inventory"
    assert receipt["response_values_retained"] is False
    assert receipt["project_names_or_content_retained"] is False
    assert receipt["results_statistics_logs_orders_retained"] is False
    assert receipt["observation"]["top_level"]["fields"] == [
        {"field_name": "newTopLevelField", "json_type": "string"},
        {"field_name": "projects", "json_type": "array"},
        {"field_name": "success", "json_type": "boolean"},
    ]
    assert receipt["observation"]["project_record_shapes"] == [
        {
            "json_type": "object",
            "fields": [
                {"field_name": "content", "json_type": "string"},
                {"field_name": "name", "json_type": "string"},
                {"field_name": "newProjectField", "json_type": "number"},
            ],
        }
    ]
    assert all(value.encode("utf-8") not in payload for value in forbidden_values)
    assert backend.events == ["authenticate", "projects/read"]
    assert (plan.review_directory / submission.PERMIT_FILENAME).exists()


def test_projects_read_project_record_refusal_persists_keys_only_diagnostic(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_project = backend.project
    forbidden_value = "PRIVATE READBACK VALUE MUST NOT LEAK"

    def project():
        return {
            **original_project(),
            "newProjectField": forbidden_value,
        }

    backend.project = project
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )

    _path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    assert receipt["phase"] == "created_project_readback"
    fields = receipt["observation"]["project_record_shapes"][0]["fields"]
    assert {item["field_name"] for item in fields} == {
        "codeRunning",
        "collaborators",
        "language",
        "libraries",
        "name",
        "newProjectField",
        "organizationId",
        "owner",
        "projectId",
    }
    assert forbidden_value.encode("utf-8") not in payload
    assert plan.project_name.encode("utf-8") not in payload
    assert backend.events[:4] == [
        "authenticate",
        "projects/read",
        "projects/create",
        "projects/read",
    ]
    assert "files/read" not in backend.events
    assert "compile/create" not in backend.events
    assert "backtests/create" not in backend.events


def test_projects_read_created_readback_top_level_refusal_persists_diagnostic(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request
    forbidden_value = "PRIVATE READBACK VALUE MUST NOT LEAK"

    def request(path, payload):
        if path == "projects/read" and backend.created:
            backend.events.append(path)
            return {
                "success": True,
                "projects": [backend.project()],
                "newTopLevelField": forbidden_value,
            }
        return original_request(path, payload)

    backend.request = request
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ) as caught:
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    assert type(caught.value.__cause__) is submission.formal.FormalQcSubmissionError

    _path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    assert receipt["phase"] == "created_project_readback"
    assert receipt["observation"]["top_level"]["fields"] == [
        {"field_name": "newTopLevelField", "json_type": "string"},
        {"field_name": "projects", "json_type": "array"},
        {"field_name": "success", "json_type": "boolean"},
    ]
    assert forbidden_value.encode("utf-8") not in payload
    assert plan.project_name.encode("utf-8") not in payload
    assert backend.events == [
        "authenticate",
        "projects/read",
        "projects/create",
        "projects/read",
    ]
    assert "files/read" not in backend.events
    assert "compile/create" not in backend.events
    assert "backtests/create" not in backend.events


def test_projects_read_identity_refusal_does_not_masquerade_as_schema_diagnostic(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_project = backend.project

    def project():
        return {**original_project(), "owner": False}

    backend.project = project
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ) as caught:
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    assert type(caught.value.__cause__) is submission.formal.FormalQcSubmissionError
    assert not plan.archive_root.exists()
    assert backend.events == [
        "authenticate",
        "projects/read",
        "projects/create",
        "projects/read",
    ]
    assert (plan.review_directory / submission.PERMIT_FILENAME).exists()


@pytest.mark.parametrize(
    "hostile_kind", ("unsafe_name", "oversized_name", "oversized_inventory")
)
def test_projects_read_diagnostic_redacts_hostile_field_inventory(
    monkeypatch, tmp_path, hostile_kind
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request
    secret = "PRIVATE VALUE MUST NOT LEAK"
    unsafe_name = "../unsafe\nprivate-project-name"
    oversized_name = "x" * 129

    def request(path, payload):
        if path == "projects/read":
            backend.events.append(path)
            if hostile_kind == "unsafe_name":
                return {
                    "success": True,
                    "projects": [],
                    unsafe_name: secret,
                }
            if hostile_kind == "oversized_name":
                return {
                    "success": True,
                    "projects": [],
                    oversized_name: secret,
                }
            return {
                **{
                    f"field{index:03d}": secret
                    for index in range(
                        submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_FIELDS + 1
                    )
                },
                "success": True,
                "projects": [],
            }
        return original_request(path, payload)

    backend.request = request
    with pytest.raises(submission.FundamentalDiscoverySubmissionLocked):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    _path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    fields = receipt["observation"]["top_level"]["fields"]
    expected_marker = (
        "__unsafe_field_name_redacted__"
        if hostile_kind in {"unsafe_name", "oversized_name"}
        else "__oversized_field_inventory_refused__"
    )
    assert expected_marker in {item["field_name"] for item in fields}
    assert secret.encode("utf-8") not in payload
    assert unsafe_name.encode("utf-8") not in payload
    assert oversized_name.encode("utf-8") not in payload
    assert len(payload) <= submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES


def test_projects_read_diagnostic_bounds_unique_project_shapes(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request
    secret = "PRIVATE PROJECT VALUE MUST NOT LEAK"

    def request(path, payload):
        if path == "projects/read":
            backend.events.append(path)
            return {
                "success": True,
                "projects": [
                    {f"uniqueField{index}": secret}
                    for index in range(
                        submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES
                        + 1
                    )
                ],
                "newTopLevelField": True,
            }
        return original_request(path, payload)

    backend.request = request
    with pytest.raises(submission.FundamentalDiscoverySubmissionLocked):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    _path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    assert receipt["observation"]["project_record_shapes"] == [
        {
            "json_type": "object",
            "fields": [
                {
                    "field_name": "__unique_shape_limit_refused__",
                    "json_type": "object",
                }
            ],
        }
    ]
    assert secret.encode("utf-8") not in payload
    assert len(payload) <= submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES


def test_projects_read_diagnostic_bounds_project_record_inventory(
    monkeypatch, tmp_path
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request
    secret = "PRIVATE PROJECT VALUE MUST NOT LEAK"

    def request(path, payload):
        if path == "projects/read":
            backend.events.append(path)
            return {
                "success": True,
                "projects": [
                    {"newProjectField": secret}
                    for _index in range(
                        submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_RECORDS + 1
                    )
                ],
                "newTopLevelField": True,
            }
        return original_request(path, payload)

    backend.request = request
    with pytest.raises(submission.FundamentalDiscoverySubmissionLocked):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    _path, payload, receipt = _load_projects_read_schema_diagnostic(plan)
    assert receipt["observation"]["project_record_shapes"] == [
        {
            "json_type": "array",
            "fields": [
                {
                    "field_name": "__oversized_project_inventory_refused__",
                    "json_type": "array",
                }
            ],
        }
    ]
    assert secret.encode("utf-8") not in payload
    assert len(payload) <= submission.MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES


def test_atomic_schema_diagnostic_publication_is_owner_only_and_no_replace(
    tmp_path,
):
    tmp_path.chmod(0o700)
    path = tmp_path / submission.PROJECT_SCHEMA_DIAGNOSTIC_FILENAME
    payload = b'{"safe":"schema-only"}'
    submission._write_private_file_atomically(path, payload, "test diagnostic")
    assert path.read_bytes() == payload
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    assert not (tmp_path / ("." + path.name + ".staging")).exists()

    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="already exists",
    ):
        submission._write_private_file_atomically(
            path, b'{"different":true}', "test diagnostic"
        )
    assert path.read_bytes() == payload
    assert not (tmp_path / ("." + path.name + ".staging")).exists()


def test_atomic_schema_diagnostic_names_post_link_fsync_ambiguity(
    monkeypatch, tmp_path,
):
    tmp_path.chmod(0o700)
    path = tmp_path / submission.PROJECT_SCHEMA_DIAGNOSTIC_FILENAME
    payload = b'{"safe":"schema-only"}'
    real_fsync = submission.os.fsync
    calls = 0

    def fail_first_directory_fsync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(submission.os, "fsync", fail_first_directory_fsync)
    with pytest.raises(
        submission.FundamentalDiscoveryDiagnosticPublicationAmbiguous,
        match="linked completely.*durability is ambiguous",
    ):
        submission._write_private_file_atomically(
            path, payload, "test diagnostic"
        )
    staging = tmp_path / ("." + path.name + ".staging")
    assert path.read_bytes() == payload
    assert staging.read_bytes() == payload
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_ino == staging.stat().st_ino


def test_projects_read_diagnostic_names_archive_root_fsync_ambiguity(
    monkeypatch, tmp_path,
):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    original_request = backend.request

    def request(path, payload):
        if path == "projects/read":
            backend.events.append(path)
            return {
                "success": True,
                "projects": [],
                "newTopLevelField": True,
            }
        return original_request(path, payload)

    backend.request = request
    real_fsync = submission.os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected archive-parent fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(submission.os, "fsync", fail_directory_fsync)
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit remains consumed",
    ) as caught:
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:00:00.000000Z",
        )
    assert type(caught.value.__cause__) is (
        submission.FundamentalDiscoveryArchiveRootPublicationAmbiguous
    )
    assert type(caught.value.__cause__.__cause__) is OSError
    assert type(caught.value.__cause__.__cause__.__context__) is (
        submission.formal.FormalQcSubmissionError
    )
    assert plan.archive_root.is_dir()
    assert stat.S_IMODE(plan.archive_root.stat().st_mode) == 0o700
    assert not (
        plan.archive_root / submission.PROJECT_SCHEMA_DIAGNOSTIC_FILENAME
    ).exists()
    assert (plan.review_directory / submission.PERMIT_FILENAME).exists()
    observed_events = list(backend.events)

    with pytest.raises(
        submission.FundamentalDiscoverySubmissionLocked,
        match="permit already spent or unavailable",
    ):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-13T12:01:00.000000Z",
        )
    assert backend.events == observed_events


def test_owner_signature_gate_precedes_permit_credentials_and_transport(
    monkeypatch, tmp_path
):
    plan, claim, _owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    permit_path = tmp_path / submission.PERMIT_FILENAME
    monkeypatch.setattr(
        submission,
        "_require_owner_signature",
        lambda *_args: (_ for _ in ()).throw(
            submission.FundamentalDiscoverySubmissionError("signature closed")
        ),
    )
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="signature closed",
    ):
        submission.execute_fundamental_discovery_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=None,
            client=client,
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert not permit_path.exists()
    assert backend.events == []


def _registered_discovery_action_receipts(monkeypatch, tmp_path):
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    permit, launch = submission.execute_fundamental_discovery_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        client=client,
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )
    terminal = submission.inspect_fundamental_discovery_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        client=client,
    )
    output = submission.download_and_review_fundamental_discovery_archive(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        terminal=terminal,
        client=client,
    )
    return plan, permit, launch, terminal, output


def test_discovery_offline_action_receipts_remain_rejected_after_restore(
    tmp_path,
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        plan, permit, launch, terminal, output = (
            _registered_discovery_action_receipts(patch, tmp_path)
        )
    with pytest.raises(submission.FundamentalDiscoverySubmissionError):
        submission.require_fundamental_discovery_launch_receipt(
            launch, plan, permit
        )
    with pytest.raises(submission.FundamentalDiscoverySubmissionError):
        submission.require_fundamental_discovery_terminal_status_receipt(
            terminal, plan, permit, launch
        )
    with pytest.raises(submission.FundamentalDiscoverySubmissionError):
        submission.require_fundamental_discovery_action_output(
            output, plan, permit, launch, terminal
        )


def test_cloned_discovery_action_refuses_before_transport(
    monkeypatch, tmp_path,
) -> None:
    public = submission.execute_fundamental_discovery_submission_once
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    implementation = _direct_closure_value(public, "execute_impl")
    cloned_implementation = _with_global_values(
        implementation,
        _execution_preflight=lambda *_args, **_kwargs: object(),
    )
    cloned_public = _with_closure_value(
        public, "execute_impl", cloned_implementation
    )
    cloned_public = _with_closure_value(
        cloned_public, "binding_guard", lambda _operation: None
    )
    with pytest.raises(
        submission.formal.FormalQcSubmissionError,
        match="capability caller changed",
    ):
        cloned_public(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert backend.events == []


def test_discovery_return_authority_closures_have_no_mutable_vault() -> None:
    operations = (
        submission.execute_fundamental_discovery_submission_once,
        submission.inspect_fundamental_discovery_terminal_status,
        submission.download_and_review_fundamental_discovery_archive,
        submission.require_fundamental_discovery_launch_receipt,
        submission.require_fundamental_discovery_terminal_status_receipt,
        submission.require_fundamental_discovery_action_output,
    )
    mutable_cells: list[tuple[str, str, str]] = []
    observed: set[int] = set()
    pending = list(operations)
    while pending:
        function = pending.pop()
        if id(function) in observed:
            continue
        observed.add(id(function))
        if function.__closure__ is None:
            continue
        for name, cell in zip(
            function.__code__.co_freevars,
            function.__closure__,
            strict=True,
        ):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if type(value) in {dict, list, set}:
                # Exact mutable namespace objects are verification anchors,
                # never receipt or authority vaults.
                if name == "module_globals" and value is function.__globals__:
                    continue
                if name == "module_registry" and value is sys.modules:
                    continue
                mutable_cells.append(
                    (function.__name__, name, type(value).__name__)
                )
            if type(value) is types.FunctionType:
                pending.append(value)
    assert mutable_cells == []


def test_discovery_public_action_and_return_require_refuse_rebound_globals(
    monkeypatch, tmp_path,
) -> None:
    production_execute = submission.execute_fundamental_discovery_submission_once
    production_require_launch = (
        submission.require_fundamental_discovery_launch_receipt
    )
    plan, claim, owner_signature, client, _backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    permit, launch = submission.execute_fundamental_discovery_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        client=client,
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )

    # The explicit offline fixture replaced authority and transport callables.
    # Retained production wrappers must reject that namespace before either a
    # QC call or a process-return authority lookup can occur.
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action global authority changed",
    ):
        production_execute(
            plan=plan,
            review_claim=claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action global authority changed",
    ):
        production_require_launch(launch, plan, permit)


def test_discovery_global_seal_pins_public_authority_mirror_root(
    monkeypatch,
) -> None:
    production_require = (
        submission.require_fundamental_discovery_launch_receipt
    )
    monkeypatch.setattr(submission, "_LAUNCH_AUTHORITIES", {})
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action global authority changed",
    ):
        production_require(object(), object(), object())


@pytest.mark.parametrize(
    "name",
    (
        "_require_owner_signature",
        "FundamentalDiscoveryLaunchReceipt",
        "_canonical",
        "globals",
        "type",
        "_unexpected_discovery_action_global",
    ),
)
def test_discovery_submission_refuses_rebound_helper_or_constructor_before_mint(
    monkeypatch, name: str,
) -> None:
    production_execute = submission.execute_fundamental_discovery_submission_once
    prior = tuple(submission._LAUNCH_AUTHORITIES.items())
    monkeypatch.setattr(submission, name, object(), raising=False)
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action global authority changed",
    ):
        production_execute(
            plan=object(),
            review_claim=object(),
            owner_signature=object(),
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert tuple(submission._LAUNCH_AUTHORITIES.items()) == prior


@pytest.mark.parametrize("name", ("_created_project", "_PROJECT_RECORD_KEYS"))
def test_discovery_submission_refuses_rebound_transport_dependency_before_mint(
    monkeypatch, name,
) -> None:
    production_execute = submission.execute_fundamental_discovery_submission_once
    prior = tuple(submission._LAUNCH_AUTHORITIES.items())
    monkeypatch.setattr(submission.formal, name, object())
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action dependency authority changed",
    ):
        production_execute(
            plan=object(),
            review_claim=object(),
            owner_signature=object(),
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert tuple(submission._LAUNCH_AUTHORITIES.items()) == prior


@pytest.mark.parametrize(
    ("namespace", "name", "replacement"),
    (
        (submission.Path, "open", None),
        (submission.os, "O_EXCL", 0),
        (submission.os, "O_RDONLY", object()),
        (submission.os, "link", None),
        (submission.os, "unlink", None),
        (submission.json.JSONDecoder, "decode", None),
    ),
)
def test_discovery_path_and_create_dependencies_refuse_before_action(
    monkeypatch, namespace, name, replacement,
) -> None:
    production_execute = submission.execute_fundamental_discovery_submission_once
    prior = tuple(submission._LAUNCH_AUTHORITIES.items())
    callbacks = []

    def hostile(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile discovery path collaborator executed")

    monkeypatch.setattr(
        namespace,
        name,
        hostile if replacement is None else replacement,
    )
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action dependency authority changed",
    ):
        production_execute(
            plan=object(),
            review_claim=object(),
            owner_signature=object(),
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert callbacks == []
    assert tuple(submission._LAUNCH_AUTHORITIES.items()) == prior


@pytest.mark.parametrize(
    ("namespace", "name"),
    (
        (discovery, "_strict_json"),
        (discovery, "_read_private_file"),
        (discovery.Path, "absolute"),
    ),
)
def test_discovery_output_refuses_rebound_loader_dependency_before_authority(
    monkeypatch, tmp_path, namespace, name,
) -> None:
    production_download = (
        submission.download_and_review_fundamental_discovery_archive
    )
    prior = tuple(submission._OUTPUT_AUTHORITIES.items())
    archive_root = tmp_path / "archive"
    callbacks = []

    def hostile(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile discovery loader dependency executed")

    monkeypatch.setattr(namespace, name, hostile)
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="action dependency authority changed",
    ):
        production_download(
            plan=types.SimpleNamespace(archive_root=archive_root),
            review_claim=object(),
            owner_signature=object(),
            permit=object(),
            launch=object(),
            terminal=object(),
            client=object(),
        )
    assert callbacks == []
    assert tuple(submission._OUTPUT_AUTHORITIES.items()) == prior
    assert not archive_root.exists()


def test_extracted_discovery_return_registrars_cannot_self_mint() -> None:
    attempts = (
        (
            submission.execute_fundamental_discovery_submission_once,
            "register_launch",
            object.__new__(submission.FundamentalDiscoveryLaunchReceipt),
            {"plan": object(), "permit": object()},
        ),
        (
            submission.inspect_fundamental_discovery_terminal_status,
            "register_terminal",
            object.__new__(submission.FundamentalDiscoveryTerminalStatusReceipt),
            {"plan": object(), "permit": object(), "launch": object()},
        ),
        (
            submission.download_and_review_fundamental_discovery_archive,
            "register_output",
            object.__new__(submission.FundamentalDiscoveryNamedRefusalReceipt),
            {
                "plan": object(),
                "permit": object(),
                "launch": object(),
                "terminal": object(),
            },
        ),
    )
    for operation, name, value, keywords in attempts:
        registrar = _direct_closure_value(operation, name)
        with pytest.raises(
            submission.FundamentalDiscoverySubmissionError,
            match="producer changed",
        ):
            registrar(value, **keywords)


def test_discovery_return_mirror_copy_revokes_without_resealing(
    monkeypatch, tmp_path,
) -> None:
    plan, permit, launch, terminal, output = _registered_discovery_action_receipts(
        monkeypatch, tmp_path
    )
    cases = (
        (
            "_OUTPUT_AUTHORITIES",
            output,
            lambda: submission.require_fundamental_discovery_action_output(
                output, plan, permit, launch, terminal
            ),
        ),
        (
            "_TERMINAL_AUTHORITIES",
            terminal,
            lambda: submission.require_fundamental_discovery_terminal_status_receipt(
                terminal, plan, permit, launch
            ),
        ),
        (
            "_LAUNCH_AUTHORITIES",
            launch,
            lambda: submission.require_fundamental_discovery_launch_receipt(
                launch, plan, permit
            ),
        ),
    )
    for registry_name, value, require in cases:
        registry = getattr(submission, registry_name)
        original = registry[id(value)]
        registry[id(value)] = tuple(item for item in original)
        assert registry[id(value)] is not original
        with pytest.raises(
            submission.FundamentalDiscoverySubmissionError,
            match="process-return authority",
        ):
            require()
        assert id(value) not in registry


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_discovery_action_returns_refuse_in_child_and_survive_in_parent(
    monkeypatch, tmp_path,
) -> None:
    plan, permit, launch, terminal, output = _registered_discovery_action_receipts(
        monkeypatch, tmp_path
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - assertions report through the pipe
        os.close(read_descriptor)
        operations = (
            lambda: submission.require_fundamental_discovery_launch_receipt(
                launch, plan, permit
            ),
            lambda: submission.require_fundamental_discovery_terminal_status_receipt(
                terminal, plan, permit, launch
            ),
            lambda: submission.require_fundamental_discovery_action_output(
                output, plan, permit, launch, terminal
            ),
        )
        refused = 0
        for operation in operations:
            try:
                operation()
            except (submission.FundamentalDiscoverySubmissionError, ValueError):
                refused += 1
        mirrors_empty = all(
            not getattr(submission, name)
            for name in (
                "_LAUNCH_AUTHORITIES",
                "_TERMINAL_AUTHORITIES",
                "_OUTPUT_AUTHORITIES",
            )
        )
        os.write(
            write_descriptor,
            f"{refused},{mirrors_empty}".encode("ascii"),
        )
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 32)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"3,True"
    assert submission.require_fundamental_discovery_launch_receipt(
        launch, plan, permit
    ) is launch
    assert submission.require_fundamental_discovery_terminal_status_receipt(
        terminal, plan, permit, launch
    ) is terminal
    assert submission.require_fundamental_discovery_action_output(
        output, plan, permit, launch, terminal
    ) is output


def test_named_refusal_is_typed_and_process_authenticated(
    monkeypatch, tmp_path,
) -> None:
    plan, claim, owner_signature, client, backend = _submission_fixture(
        monkeypatch, tmp_path
    )
    failure_key = discovery.OUTPUT_PREFIX + "failures/offline-test.json"
    failure = {
        "schema": "arv2-qc-fundamental-discovery-failure-v1",
        "contract_sha256": discovery.CONTRACT_SHA256,
        "status": "named_refusal",
        "plan_id": plan.discovery_plan_id,
        "plan_sha256": plan.discovery_plan_artifact_sha256,
        "safe_reason": "qc_fundamentals_unavailable",
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    failure_payload = discovery.canonical_json_bytes(failure)
    package = {
        "schema": discovery.TERMINAL_PACKAGE_SCHEMA,
        "contract_sha256": discovery.CONTRACT_SHA256,
        "status": "named_refusal",
        "failure_key": failure_key,
        "failure_sha256": hashlib.sha256(failure_payload).hexdigest(),
        "failure_byte_count": len(failure_payload),
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    backend.objects[failure_key] = failure_payload
    backend.objects[plan.terminal_package_key] = discovery.canonical_json_bytes(
        package
    )
    backend.terminal_status = "Runtime Error"

    permit, launch = submission.execute_fundamental_discovery_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        client=client,
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )
    terminal = submission.inspect_fundamental_discovery_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        client=client,
    )
    refusal = submission.download_and_review_fundamental_discovery_archive(
        plan=plan,
        review_claim=claim,
        owner_signature=owner_signature,
        permit=permit,
        launch=launch,
        terminal=terminal,
        client=client,
    )
    assert type(refusal) is submission.FundamentalDiscoveryNamedRefusalReceipt
    assert submission.require_fundamental_discovery_action_output(
        refusal, plan, permit, launch, terminal
    ) is refusal
    assert refusal.safe_reason == "qc_fundamentals_unavailable"
    (plan.archive_root / submission.REFUSAL_FILENAME).write_bytes(b"{}\n")
    with pytest.raises(
        submission.FundamentalDiscoverySubmissionError,
        match="named refusal receipt changed",
    ):
        submission.require_fundamental_discovery_action_output(
            refusal, plan, permit, launch, terminal
        )
