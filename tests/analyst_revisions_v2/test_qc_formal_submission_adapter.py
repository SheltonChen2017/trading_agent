from __future__ import annotations

import base64
import dataclasses
import gc
import hashlib
import importlib
import json
import os
import re
import threading
import types
import weakref
from datetime import date
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import formal_submission_adapter as adapter
from research.analyst_revisions_v2_qc import formal_evaluation_bridge
from research.analyst_revisions_v2_qc import formal_qc_transport as transport_module
from research.analyst_revisions_v2.stock_evaluation_contract import (
    load_stock_evaluation_contract,
)
from research.analyst_revisions_v2_qc.formal_economic_execution_definition import (
    build_formal_economic_execution_binding,
    build_formal_economic_execution_definition,
)
from research.analyst_revisions_v2_qc.formal_cloud_evaluator import (
    FormalCloudEvaluationBindings,
)
from research.analyst_revisions_v2_qc.formal_report_contract import (
    build_formal_report_contract,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    POWER_FEASIBLE_DISPOSITION,
    SOURCE_VIEW_IDS,
    AcceptedRiskPairBinding,
    ArtifactBinding,
    FormalLookClaim,
    FormalRunProtocolError,
    FormalSubmissionPermit,
    PowerFloorBinding,
    ReviewedFormalRunAuthority,
    TerminalCensusBinding,
    build_formal_run_candidate,
)
from research.analyst_revisions_v2_qc.formal_runtime_projection import (
    CAPACITY_LIMIT_NAMES,
    CAPACITY_REVIEW_SCHEMA,
    CONTRIBUTION_SEED_SCHEMA,
    DAILY_REQUIREMENT_SCHEMA,
    DECISION_OBJECT_SCHEMA,
    DECISION_JOIN_SCHEMA,
    ECONOMIC_JOIN_SCHEMA,
    FORMAL_CONTRACT_SCHEMA,
    FORMAL_EVALUATOR_PROJECT_PATH,
    FORMAL_INPUT_PREFIX,
    INPUT_MANIFEST_SCHEMA,
    MINUTE_REQUIREMENT_SCHEMA,
    SHARD_ROLE_ORDER,
    TERMINAL_OBJECT_SCHEMA,
    build_daily_market_requirement_id,
    build_formal_qc_compressed_shard,
    build_formal_qc_input_manifest_bytes,
    build_formal_qc_runtime_projection,
    build_minute_market_requirement_id,
    build_qc_object_payload_binding,
    canonical_json_bytes,
    derive_formal_qc_runtime_resource_census,
    formal_cloud_evaluator_binding,
    formal_code_projection_binding,
    load_formal_qc_runtime_capacity_binding,
    render_formal_qc_capacity_review_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
_REAL_EXECUTION_TRUST_GATE = (
    adapter._require_non_self_mintable_execution_trust_root
)
_REAL_RESULT_READ_TRUST_GATE = (
    adapter._require_non_self_mintable_result_read_trust_root
)
_REAL_UPSTREAM_CAPACITY_GATE = adapter._require_upstream_materialization_capacity
_REAL_TERMINAL_STATUS_ENTRYPOINT = adapter.inspect_statistics_free_terminal_status


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def test_project_list_parsers_accept_documented_lean_versions_metadata():
    response = {
        "success": True,
        "projects": [],
        "versions": [
            {
                "id": 1,
                "created": "2026-09-13T00:00:00Z",
                "description": "discarded",
                "leanHash": "discarded",
                "leanCloudHash": "discarded",
                "name": "discarded",
                "ref": "discarded",
                "public": True,
            }
        ],
    }

    assert adapter._read_project_inventory(response) == []
    created = adapter._created_project(
        {
            **response,
            "projects": [
                {"projectId": 123, "name": "exact", "language": "Py"}
            ],
        },
        name="exact",
        organization_id="organization-test",
    )
    assert created["projectId"] == 123


@pytest.mark.parametrize(
    ("parser", "message"),
    (
        (
            lambda value: adapter._read_project_inventory(value),
            "projects/read versions envelope changed",
        ),
        (
            lambda value: adapter._created_project(
                {**value, "projects": [
                    {"projectId": 123, "name": "exact", "language": "Py"}
                ]},
                name="exact",
                organization_id="organization-test",
            ),
            "projects/create versions envelope changed",
        ),
    ),
)
def test_project_list_parsers_isolate_non_list_versions_refusal(parser, message):
    with pytest.raises(adapter.FormalQcSubmissionError, match=re.escape(message)):
        parser({"success": True, "projects": [], "versions": {}})


def test_project_inventory_still_refuses_undocumented_top_level_keys():
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="projects/read envelope changed",
    ):
        adapter._read_project_inventory(
            {"success": True, "projects": [], "versions": [], "unknown": None}
        )


def test_project_record_accepts_current_documented_discard_only_fields():
    record = {
        "projectId": 123,
        "organizationId": "organization-test",
        "name": "exact",
        "modified": "2026-09-13T00:00:00Z",
        "created": "2026-09-13T00:00:00Z",
        "ownerId": 1,
        "language": "Py",
        "collaborators": [{"owner": True}],
        "leanVersionId": 1,
        "leanPinnedToMaster": False,
        "owner": True,
        "description": "discarded",
        "channelId": "discarded",
        "parameters": {},
        "libraries": [],
        "grid": {},
        "liveGrid": {},
        "paperEquity": 0,
        "lastLiveDeployment": None,
        "liveForm": {},
        "encrypted": False,
        "codeRunning": False,
        "leanEnvironment": 0,
        "encryptionKey": None,
        "isPinned": False,
        "maxFileSize": 1,
        "sharingTokenBacktest": "discarded",
    }

    assert adapter._project_record(
        record,
        name="exact",
        organization_id="organization-test",
    ) is record


def test_project_record_still_refuses_undocumented_keys():
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="project envelope changed",
    ):
        adapter._project_record(
            {
                "projectId": 123,
                "organizationId": "organization-test",
                "name": "exact",
                "language": "Py",
                "collaborators": [{"owner": True}],
                "owner": True,
                "codeRunning": False,
                "unknown": None,
            },
            name="exact",
            organization_id="organization-test",
        )


def _closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    return cells[name].cell_contents


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name: str, value: object):
    """Clone a production wrapper with one explicit offline-only test cell."""

    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    closure = tuple(
        _closure_cell(value) if freevar == name else cells[freevar]
        for freevar in function.__code__.co_freevars
    )
    rebound = types.FunctionType(
        function.__code__, function.__globals__, function.__name__,
        function.__defaults__, closure,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _install_offline_action_authority(monkeypatch):
    """Install a test-local action/process authority without production minting.

    Production wrappers and their private vault remain untouched and are
    covered by the refusal tests above.  Functional tests use cloned public
    wrappers, an offline transport capability, and an independently retained
    local receipt registry so monkeypatches cannot accidentally exercise or
    populate the production authority.
    """

    private = {"launch": {}, "terminal": {}, "summary": {}}
    monkeypatch.setattr(adapter, "_local_wait", lambda _seconds: None)
    public = {
        "launch": adapter._LAUNCH_RECEIPT_AUTHORITIES,
        "terminal": adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES,
        "summary": adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES,
    }

    def register(kind, value, entry_tail):
        identity = id(value)

        def forget(_reference):
            private[kind].pop(identity, None)
            public[kind].pop(identity, None)

        reference = weakref.ref(value, forget)
        entry = (reference, *entry_tail, os.getpid())
        private[kind][identity] = entry
        public[kind][identity] = entry
        return value

    def current(kind, value):
        identity = id(value)
        entry = private[kind].get(identity)
        if (
            entry is None
            or public[kind].get(identity) is not entry
            or entry[0]() is not value
            or entry[-1] != os.getpid()
        ):
            private[kind].pop(identity, None)
            public[kind].pop(identity, None)
            return None
        return entry

    local_register_launch = lambda value, entry_tail: register(
        "launch", value, entry_tail
    )
    local_register_terminal = lambda value, entry_tail: register(
        "terminal", value, entry_tail
    )
    local_register_summary = lambda value, entry_tail: register(
        "summary", value, entry_tail
    )
    local_current_launch = lambda value: current("launch", value)
    local_current_terminal = lambda value: current("terminal", value)
    local_current_summary = lambda value: current("summary", value)

    def localize_action(name, registrar_name, process_name, process_register):
        public_action = getattr(adapter, name)
        registrar = _closure_value(public_action, registrar_name)
        registrar = _with_closure_value(
            registrar, process_name, process_register
        )
        public_action = _with_closure_value(
            public_action, "binding_guard", lambda _kind: None
        )
        public_action = _with_closure_value(
            public_action,
            "transport_capability_minter",
            transport_module._mint_offline_test_capability,
        )
        public_action = _with_closure_value(
            public_action, registrar_name, registrar
        )
        monkeypatch.setattr(adapter, name, public_action)

    localize_action(
        "execute_formal_qc_submission_once",
        "register_launch",
        "process_register_launch",
        local_register_launch,
    )
    localize_action(
        "execute_streamed_formal_qc_submission_once",
        "register_launch",
        "process_register_launch",
        local_register_launch,
    )
    localize_action(
        "inspect_statistics_free_terminal_status",
        "register_terminal",
        "process_register_terminal",
        local_register_terminal,
    )
    localize_action(
        "inspect_streamed_statistics_free_terminal_status",
        "register_terminal",
        "process_register_terminal",
        local_register_terminal,
    )

    def localize_read_action(name):
        read_action = getattr(adapter, name)
        mint_completed = _closure_value(read_action, "mint_completed")
        mint_summary = _closure_value(mint_completed, "mint_summary")
        mint_summary = _with_closure_value(
            mint_summary, "process_register_summary", local_register_summary
        )
        mint_completed = _with_closure_value(
            mint_completed, "mint_summary", mint_summary
        )
        read_action = _with_closure_value(
            read_action, "binding_guard", lambda _kind: None
        )
        read_action = _with_closure_value(
            read_action,
            "transport_capability_minter",
            transport_module._mint_offline_test_capability,
        )
        read_action = _with_closure_value(
            read_action, "mint_completed", mint_completed
        )
        monkeypatch.setattr(adapter, name, read_action)

    localize_read_action("read_formal_qc_summary_result_once")
    localize_read_action("read_streamed_formal_qc_summary_result_once")

    launch_authority = _with_closure_value(
        adapter._require_launch_receipt_authority,
        "process_current_launch",
        local_current_launch,
    )
    terminal_authority = _with_closure_value(
        adapter._require_terminal_status_receipt_authority,
        "process_current_terminal",
        local_current_terminal,
    )
    monkeypatch.setattr(
        adapter, "_require_launch_receipt_authority", launch_authority
    )
    monkeypatch.setattr(
        adapter,
        "_require_terminal_status_receipt_authority",
        terminal_authority,
    )
    summary_require = _with_closure_value(
        adapter.require_formal_qc_summary_result_read_receipt,
        "process_current_summary",
        local_current_summary,
    )
    monkeypatch.setattr(
        adapter,
        "require_formal_qc_summary_result_read_receipt",
        summary_require,
    )
    for result_control_name in (
        "_require_private_result_directory",
        "_read_private_result_control",
        "_exclusive_private_result_write",
    ):
        monkeypatch.setattr(
            adapter,
            result_control_name,
            _with_closure_value(
                getattr(adapter, result_control_name),
                "binding_guard",
                lambda _kind: None,
            ),
        )


def _raw_streamed_receipts(monkeypatch):
    """Build content-only streamed receipts without minting process authority."""

    permit = types.SimpleNamespace(permit_id="permit-test", permit_sha256="1" * 64)
    economic_execution = types.SimpleNamespace(
        binding_id="economic-execution-test",
        binding_sha256="8" * 64,
        definition_id="economic-definition-test",
        definition_sha256="9" * 64,
    )
    report_contract = types.SimpleNamespace(
        contract_id="formal-report-contract-test",
        contract_sha256="a" * 64,
        artifact_sha256="b" * 64,
        stock_bootstrap_seed_sha256="c" * 64,
    )
    plan = types.SimpleNamespace(
        plan_id="plan-test",
        plan_sha256="2" * 64,
        projection_id="projection-test",
        projection_sha256="3" * 64,
        execution_authority=types.SimpleNamespace(
            host_code_closure=types.SimpleNamespace(closure_sha256="4" * 64)
        ),
        backtest_name="backtest-test",
        upload_entry_count=1,
        source_manifest=(),
        status_poll_limit=3,
        economic_execution=economic_execution,
        report_contract=report_contract,
    )
    launch = adapter._streamed_launch_receipt(
        permit=permit,
        plan=plan,
        project_id=123,
        compile_id="compile-test",
        backtest_id="backtest-test",
        initial_status="In Queue...",
    )
    authenticated = types.SimpleNamespace(
        binding_id="power-test", binding_sha256="5" * 64
    )
    submission_bridge = types.SimpleNamespace(
        bridge_id="submission-test",
        bridge_sha256="6" * 64,
        runtime_bridge=types.SimpleNamespace(
            bridge_id="runtime-test", bridge_sha256="7" * 64
        ),
        authenticated_power_floor=authenticated,
        economic_execution=economic_execution,
        report_contract=report_contract,
        plan=plan,
    )
    monkeypatch.setattr(
        adapter,
        "require_streamed_formal_submission_adapter_bridge",
        lambda value: value,
    )
    terminal = adapter._streamed_terminal_receipt(
        submission_bridge=submission_bridge,
        launch=launch,
        permit=permit,
        terminal_status="Completed.",
        status_poll_count=1,
    )
    return permit, plan, launch, submission_bridge, terminal


def _genuine_offline_process_receipts(monkeypatch):
    """Traverse production implementations through test-local wrappers."""

    candidate, reviewed, _execution, projection, plan, claim = _fixture(monkeypatch)
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda _value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *args: args[-1])
    monkeypatch.setattr(
        adapter,
        "begin_formal_submission_once",
        lambda **_kwargs: _permit(candidate, reviewed, claim, events),
    )
    permit, launch = adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    monkeypatch.setattr(
        adapter, "require_formal_submission_permit", lambda *args: args[-1]
    )
    terminal = adapter.inspect_statistics_free_terminal_status(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        permit=permit,
        plan=plan,
        launch=launch,
        client=client,
    )
    return candidate, reviewed, claim, permit, plan, launch, terminal


@pytest.mark.parametrize(
    "name",
    (
        "_make_process_receipt_authority_vault",
        "_process_authority_register_launch",
        "_process_authority_register_terminal",
        "_process_authority_register_summary",
        "_register_launch_receipt_authority",
        "_register_terminal_status_receipt_authority",
        "_mint_summary_result_receipt_authority",
        "_mint_completed_summary_read_receipt",
        "_register_launch_receipt_authority_impl",
        "_register_terminal_status_receipt_authority_impl",
        "_mint_summary_result_receipt_authority_impl",
        "_mint_completed_summary_read_receipt_impl",
    ),
)
def test_process_receipt_authority_minters_are_not_module_addressable(name):
    assert not hasattr(adapter, name)


def _reflected_process_receipt_registers():
    register_launch = _closure_value(
        adapter.execute_formal_qc_submission_once, "register_launch"
    )
    register_terminal = _closure_value(
        adapter.inspect_statistics_free_terminal_status, "register_terminal"
    )
    mint_completed = _closure_value(
        adapter.read_formal_qc_summary_result_once, "mint_completed"
    )
    mint_summary = _closure_value(mint_completed, "mint_summary")
    return (
        _closure_value(register_launch, "process_register_launch"),
        _closure_value(register_terminal, "process_register_terminal"),
        _closure_value(mint_summary, "process_register_summary"),
    )


@pytest.mark.parametrize("register_index", range(3))
def test_reflected_process_receipt_register_cannot_self_mint(register_index):
    process_register = _reflected_process_receipt_registers()[register_index]
    value = object.__new__(adapter.FormalQcLaunchReceipt)
    with pytest.raises(adapter.FormalQcSubmissionError, match="caller changed"):
        process_register(value, ())


def test_reflected_process_receipt_private_registries_are_immutable():
    process_register = _reflected_process_receipt_registers()[0]
    register = _closure_value(process_register, "register")
    private_entry = _closure_value(register, "private_entry")
    private_registry = _closure_value(private_entry, "private_registry")
    state = _closure_value(private_registry, "private_registries")
    assert type(state) is tuple
    assert not hasattr(state, "append")


def test_formal_action_guard_seals_exact_module_name_census():
    binding_guard = _closure_value(
        adapter.execute_formal_qc_submission_once, "binding_guard"
    )
    expected_names = _closure_value(binding_guard, "expected_names")
    excluded = _closure_value(binding_guard, "excluded")
    assert expected_names == tuple(sorted(
        name for name in vars(adapter)
        if not name.startswith("__") and name not in excluded
    ))
    expected_external = _closure_value(binding_guard, "expected_external")
    observed_external = {}
    for namespace, name, _value in expected_external:
        observed_external.setdefault(namespace, []).append(name)
    os_names = [
        "close", "fstat", "fsync", "getpid", "open", "read",
        "register_at_fork", "stat", "write", "O_CREAT", "O_EXCL",
        "O_RDONLY", "O_WRONLY",
    ]
    if hasattr(adapter.os, "O_NOFOLLOW"):
        os_names.append("O_NOFOLLOW")
    path_names = [
        "__fspath__", "__init__", "__new__", "__str__", "__truediv__",
        "is_absolute", "is_symlink", "name", "parent", "read_bytes",
        "relative_to", "resolve", "stat",
    ]
    assert observed_external == {
        adapter.base64: ["b64decode", "b64encode", "urlsafe_b64encode"],
        adapter.dataclasses: ["asdict", "dataclass", "field", "fields"],
        adapter.hashlib: ["md5", "sha256"],
        adapter.json: [
            "dumps", "loads", "JSONDecoder", "JSONEncoder",
            "_default_decoder", "_default_encoder",
        ],
        adapter.json.loads: [
            "__code__", "__globals__", "__defaults__", "__kwdefaults__",
            "__closure__",
        ],
        adapter.json.dumps: [
            "__code__", "__globals__", "__defaults__", "__kwdefaults__",
            "__closure__",
        ],
        adapter.os: os_names,
        adapter.os.path: ["dirname", "join", "realpath"],
        adapter.Path: path_names,
        type(adapter.Path()): path_names,
        adapter.re: ["compile", "fullmatch"],
        adapter.stat: ["S_ISDIR", "S_ISLNK", "S_ISREG", "S_IMODE"],
        adapter.sys: ["_getframe", "modules"],
        adapter.threading: ["RLock"],
        adapter.time: ["sleep"],
        adapter.timezone: ["utc"],
        adapter.weakref: ["ref"],
        adapter.zlib: ["MAX_WBITS", "decompress", "decompressobj", "error"],
    }
    class_namespaces = _closure_value(
        binding_guard, "expected_class_namespaces"
    )
    assert tuple(item[0] for item in class_namespaces) == (
        adapter.datetime,
        adapter.json.JSONDecoder,
        adapter.json.JSONEncoder,
    )
    for class_type, names, bindings in class_namespaces:
        assert names == tuple(sorted(vars(class_type)))
        assert bindings == tuple(vars(class_type).items())


def test_formal_action_guard_survives_all_exact_downstream_claims(
    monkeypatch,
):
    claim_names = (
        "_claim_fundamental_discovery_transport_capability_minter",
        "_claim_preopen_transport_capability_minter",
        "_claim_power_calibration_transport_capability_minter",
    )
    for module_name in (
        "research.analyst_revisions_v2_qc."
        "fundamental_universe_discovery_submission_adapter",
        "research.analyst_revisions_v2_qc.preopen_control_submission_adapter",
        "research.analyst_revisions_v2_qc.power_calibration_submission_adapter",
    ):
        importlib.import_module(module_name)
    assert all(name not in vars(adapter) for name in claim_names)
    binding_guard = _closure_value(
        adapter.execute_formal_qc_submission_once, "binding_guard"
    )
    binding_guard("downstream integration")

    callbacks = []

    def hostile_read_bytes(*args, **kwargs):
        callbacks.append((args, kwargs))
        raise AssertionError("host source read occurred after dependency change")

    monkeypatch.setattr(adapter.Path, "read_bytes", hostile_read_bytes)
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="action dependency authority changed",
    ):
        adapter.execute_formal_qc_submission_once(
            candidate=object(), authority=object(), claim=object(),
            projection=object(), plan=object(), client=object(),
            submission_started_at_utc="2026-09-12T12:00:00Z",
        )
    assert callbacks == []


@pytest.mark.parametrize(
    "dependency",
    ("Path.read_bytes", "adapter._read_live_host_sources"),
)
def test_live_host_verifier_authenticates_before_source_read(
    monkeypatch, dependency,
):
    callbacks = []

    def hostile(*args, **kwargs):
        callbacks.append((args, kwargs))
        raise AssertionError("host source dependency ran before authentication")

    namespace, name = dependency.split(".", 1)
    target = adapter.Path if namespace == "Path" else adapter
    monkeypatch.setattr(target, name, hostile)
    expected = (
        "action dependency authority changed"
        if namespace == "Path"
        else "action global authority changed"
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match=expected):
        adapter.verify_formal_qc_host_closure_live(object())
    assert callbacks == []


@pytest.mark.parametrize(
    ("action_name", "signature_verifier"),
    (
        (
            "execute_formal_qc_submission_once",
            "require_formal_execution_owner_signature",
        ),
        (
            "inspect_statistics_free_terminal_status",
            "require_formal_execution_owner_signature",
        ),
        (
            "read_formal_qc_summary_result_once",
            "require_formal_result_read_owner_signature",
        ),
    ),
)
def test_formal_action_refuses_nested_verifier_and_builtin_injection_first(
    monkeypatch, tmp_path, action_name, signature_verifier,
):
    marker = tmp_path / "one-use-state-was-entered"

    def entered_implementation():
        marker.write_text("entered", encoding="ascii")
        raise AssertionError("formal implementation ran before its guard")

    hostile_calls = []

    class ExplosiveClient:
        def __getattribute__(self, name):
            hostile_calls.append(name)
            raise AssertionError("formal guard touched transport")

    public = getattr(adapter, action_name)
    expected_names = _closure_value(
        _closure_value(public, "binding_guard"), "expected_names"
    )
    monkeypatch.setattr(
        adapter, "_require_legacy_materialized_submission_retired",
        entered_implementation,
    )
    monkeypatch.setattr(adapter, signature_verifier, lambda *_args: None)
    monkeypatch.setattr(
        adapter, "tuple", lambda _values: expected_names, raising=False
    )
    monkeypatch.setattr(adapter, "any", lambda _values: False, raising=False)
    value = object()
    if action_name == "execute_formal_qc_submission_once":
        kwargs = {
            "candidate": value, "authority": value, "claim": value,
            "projection": value, "plan": value,
            "client": ExplosiveClient(),
            "submission_started_at_utc": "2026-09-12T12:00:00Z",
        }
    elif action_name == "inspect_statistics_free_terminal_status":
        kwargs = {
            "candidate": value, "authority": value, "claim": value,
            "permit": value, "plan": value, "launch": value,
            "client": ExplosiveClient(),
        }
    else:
        kwargs = {
            "result_authority": value, "result_gate": value,
            "candidate": value, "reviewed_authority": value,
            "terminal": value, "launch": value, "claim": value,
            "submission_permit": value, "plan": value,
            "client": ExplosiveClient(),
            "result_read_started_at_utc": "2026-09-12T12:00:00Z",
        }
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="action global authority changed",
    ):
        public(**kwargs)
    assert not marker.exists()
    assert hostile_calls == []


@pytest.mark.parametrize(
    "action_name",
    (
        "execute_formal_qc_submission_once",
        "read_formal_qc_summary_result_once",
    ),
)
@pytest.mark.parametrize(
    "dependency",
    (
        "os.open", "Path.read_bytes", "Path.relative_to",
        "JSONDecoder.__init__", "JSONEncoder.__init__",
    ),
)
def test_formal_action_refuses_rebound_result_io_before_state_or_transport(
    monkeypatch, tmp_path, action_name, dependency,
):
    hostile_io = []
    hostile_transport = []
    ledger = tmp_path / "result-read-spend-must-not-exist"

    def hostile_open(*args, **kwargs):
        hostile_io.append((args, kwargs))
        raise AssertionError("result-control I/O ran before its authority")

    class ExplosiveClient:
        def __getattribute__(self, name):
            hostile_transport.append(name)
            raise AssertionError("transport was touched before refusal")

    namespace, name = dependency.split(".", 1)
    target = {
        "os": adapter.os,
        "Path": adapter.Path,
        "JSONDecoder": adapter.json.JSONDecoder,
        "JSONEncoder": adapter.json.JSONEncoder,
    }[namespace]
    monkeypatch.setattr(target, name, hostile_open)
    value = object()
    if action_name == "execute_formal_qc_submission_once":
        kwargs = {
            "candidate": value,
            "authority": value,
            "claim": value,
            "projection": value,
            "plan": value,
            "client": ExplosiveClient(),
            "submission_started_at_utc": "2026-09-12T12:00:00Z",
        }
    else:
        kwargs = {
            "result_authority": value,
            "result_gate": value,
            "candidate": value,
            "reviewed_authority": value,
            "terminal": value,
            "launch": value,
            "claim": value,
            "submission_permit": value,
            "plan": value,
            "client": ExplosiveClient(),
            "result_read_started_at_utc": "2026-09-12T12:00:00Z",
        }
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="action dependency authority changed",
    ):
        getattr(adapter, action_name)(**kwargs)
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="action dependency authority changed",
    ):
        adapter._read_private_result_control(
            tmp_path / "nonexistent-pin", "audit pin"
        )
    assert hostile_io == []
    assert hostile_transport == []
    assert not ledger.exists()


def test_public_receipt_constructors_cannot_mint_process_authority(monkeypatch):
    permit, plan, _launch, submission_bridge, _terminal = (
        _raw_streamed_receipts(monkeypatch)
    )
    direct_launch = adapter._streamed_launch_receipt(
        permit=permit,
        plan=plan,
        project_id=123,
        compile_id="compile-direct",
        backtest_id="backtest-direct",
        initial_status="In Queue...",
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_launch_self_identity(direct_launch)

    direct_terminal = adapter._streamed_terminal_receipt(
        submission_bridge=submission_bridge,
        launch=direct_launch,
        permit=permit,
        terminal_status="Completed.",
        status_poll_count=1,
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_terminal_self_identity(direct_terminal)


def test_public_process_receipt_mirrors_cannot_reseal_authority(monkeypatch):
    _candidate, _reviewed, _claim, _permit, _plan, launch, terminal = (
        _genuine_offline_process_receipts(monkeypatch)
    )
    with adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK:
        terminal_entry = adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES[
            id(terminal)
        ]
        replacement = tuple(list(terminal_entry))
        assert replacement is not terminal_entry
        adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES[id(terminal)] = replacement
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_terminal_self_identity(terminal)
    assert id(terminal) not in adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES
    with adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK:
        adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES[id(terminal)] = terminal_entry
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_terminal_self_identity(terminal)
    assert id(terminal) not in adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES

    with adapter._LAUNCH_RECEIPT_AUTHORITIES_LOCK:
        launch_entry = adapter._LAUNCH_RECEIPT_AUTHORITIES[id(launch)]
        replacement = tuple(list(launch_entry))
        assert replacement is not launch_entry
        adapter._LAUNCH_RECEIPT_AUTHORITIES[id(launch)] = replacement
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_launch_self_identity(launch)
    assert id(launch) not in adapter._LAUNCH_RECEIPT_AUTHORITIES
    with adapter._LAUNCH_RECEIPT_AUTHORITIES_LOCK:
        adapter._LAUNCH_RECEIPT_AUTHORITIES[id(launch)] = launch_entry
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_launch_self_identity(launch)
    assert id(launch) not in adapter._LAUNCH_RECEIPT_AUTHORITIES


def test_action_receipts_require_process_return_authority_and_cleanup(monkeypatch):
    _candidate, _reviewed, _claim, _permit, _plan, launch, terminal = (
        _genuine_offline_process_receipts(monkeypatch)
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_launch_self_identity(dataclasses.replace(launch))
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter._require_terminal_self_identity(dataclasses.replace(terminal))

    launch_id, terminal_id = id(launch), id(terminal)
    launch_ref, terminal_ref = weakref.ref(launch), weakref.ref(terminal)
    del terminal
    gc.collect()
    assert terminal_ref() is None
    assert terminal_id not in adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES
    del launch
    gc.collect()
    assert launch_ref() is None
    assert launch_id not in adapter._LAUNCH_RECEIPT_AUTHORITIES


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_process_receipt_authorities_do_not_cross_fork(monkeypatch):
    _candidate, _reviewed, _claim, _permit, _plan, launch, _terminal = (
        _genuine_offline_process_receipts(monkeypatch)
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - assertions are reported through the pipe
        os.close(read_descriptor)
        try:
            adapter._require_launch_self_identity(launch)
        except adapter.FormalQcSubmissionError:
            empty = not (
                adapter._LAUNCH_RECEIPT_AUTHORITIES
                or adapter._TERMINAL_STATUS_RECEIPT_AUTHORITIES
                or adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES
            )
            os.write(write_descriptor, b"refused" if empty else b"not-cleared")
        else:
            os.write(write_descriptor, b"accepted")
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 64)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"refused"


def test_terminal_poll_count_requires_exact_bounded_int(monkeypatch):
    permit, plan, launch, submission_bridge, _terminal = (
        _raw_streamed_receipts(monkeypatch)
    )
    for count in (False, 0, plan.status_poll_limit + 1):
        with pytest.raises(adapter.FormalQcSubmissionError, match="terminal"):
            adapter._streamed_terminal_receipt(
                submission_bridge=submission_bridge,
                launch=launch,
                permit=permit,
                terminal_status="Completed.",
                status_poll_count=count,
            )


def test_streamed_receipts_and_postlaunch_capability_bind_economic_definition(monkeypatch):
    _permit, plan, launch, submission_bridge, terminal = (
        _raw_streamed_receipts(monkeypatch)
    )
    economic = submission_bridge.economic_execution
    for value in (launch, terminal):
        assert value.economic_execution_binding_id == economic.binding_id
        assert value.economic_execution_binding_sha256 == economic.binding_sha256
        assert value.economic_execution_definition_id == economic.definition_id
        assert value.economic_execution_definition_sha256 == economic.definition_sha256
    capability = adapter.streamed_formal_post_launch_capability_record(
        submission_bridge
    )
    assert capability["economic_execution_binding_id"] == economic.binding_id
    assert capability["economic_execution_binding_sha256"] == economic.binding_sha256
    assert capability["economic_execution_definition_id"] == economic.definition_id
    assert capability["economic_execution_definition_sha256"] == (
        economic.definition_sha256
    )
    assert plan.economic_execution is economic
    report = submission_bridge.report_contract
    assert capability["formal_report_contract_id"] == report.contract_id
    assert capability["formal_report_contract_sha256"] == report.contract_sha256
    assert capability["formal_report_contract_artifact_sha256"] == (
        report.artifact_sha256
    )


def test_streamed_report_authority_requires_exact_economic_child_identity(monkeypatch):
    stock = load_stock_evaluation_contract(
        ROOT / "research/analyst_revisions_v2/specs/arv2_stock_historical.structural.json",
        qc_first_plan_path=(
            ROOT / "research/analyst_revisions_v2/specs/arv2_qc_first.draft.json"
        ),
    )
    economic = build_formal_economic_execution_binding(
        build_formal_economic_execution_definition(stock)
    )
    report = build_formal_report_contract(
        economic_execution_definition_sha256=economic.definition_sha256
    )
    same_valued_substitute = build_formal_report_contract(
        economic_execution_definition_sha256=economic.definition_sha256
    )
    streamed_input = types.SimpleNamespace(
        economic_execution=economic,
        report_contract=report,
    )
    bridge = types.SimpleNamespace(
        economic_execution=economic,
        report_contract=report,
        resource_candidate=types.SimpleNamespace(streamed_input=streamed_input),
    )
    monkeypatch.setattr(adapter, "_require_streamed_runtime_bridge", lambda value: value)
    assert adapter._require_streamed_report_contract(report, bridge) is report
    with pytest.raises(adapter.FormalQcSubmissionError, match="escaped"):
        adapter._require_streamed_report_contract(same_valued_substitute, bridge)


def test_legacy_action_entrypoints_retire_before_any_transport_access():
    class ExplosiveTransport:
        def __getattribute__(self, _name):
            raise AssertionError("retired entrypoint touched transport")

    value = object()
    client = ExplosiveTransport()
    actions = (
        lambda: adapter.execute_formal_qc_submission_once(
            candidate=value, authority=value, claim=value, projection=value,
            plan=value, client=client,
            submission_started_at_utc="2026-09-12T12:00:00Z",
        ),
        lambda: adapter.inspect_statistics_free_terminal_status(
            candidate=value, authority=value, claim=value, permit=value,
            plan=value, launch=value, client=client,
        ),
        lambda: adapter.read_formal_qc_summary_result_once(
            result_authority=value, result_gate=value, candidate=value,
            reviewed_authority=value, terminal=value, launch=value,
            claim=value, submission_permit=value, plan=value, client=client,
            result_read_started_at_utc="2026-09-12T12:00:00Z",
        ),
    )
    for action in actions:
        with pytest.raises(adapter.FormalQcSubmissionError, match="retired"):
            action()


def test_summary_contract_is_exact_and_joined_payload_is_bounded():
    contract = {
        "aggregate_result_schema": adapter.AGGREGATE_RESULT_SCHEMA,
        "summary_receipt_schema": adapter.SUMMARY_RECEIPT_SCHEMA,
        "cloud_evaluation_output_schema": (
            adapter.FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
        ),
        "report_family_object_reference_schema": (
            adapter.REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        ),
        "meta_name": adapter.SUMMARY_META_NAME,
        "chunk_prefix": adapter.SUMMARY_CHUNK_PREFIX,
        "chunk_name_width": adapter.SUMMARY_CHUNK_NAME_WIDTH,
        "max_payload_byte_count": 8,
        "max_chunk_count": 2,
        "max_chunk_characters": 8,
        "fold_horizon_axis_count": 24,
        "source_view_fold_horizon_axis_count": 48,
        "raw_market_or_outcome_rows_in_summary_forbidden": True,
        "report_family_object_count": adapter.FORMAL_RESULT_FAMILY_OBJECT_COUNT,
        "report_family_object_key_suffix_prefix": (
            adapter.REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
        ),
        "report_family_object_full_key_derivation": (
            "str(project_id)+'/'+authenticated_object_store_key_suffix"
        ),
        "report_family_object_uncompressed_byte_ceiling": (
            adapter.MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES
        ),
        "report_family_object_compressed_byte_ceiling": (
            adapter.MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
        ),
        "report_family_object_total_uncompressed_byte_ceiling": (
            adapter.MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
        ),
        "report_family_object_total_compressed_byte_ceiling": (
            adapter.MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
        ),
        "object_store_write_once_existing_identical_bytes_only": True,
        "object_store_save_then_reopen_and_rehash_required": True,
        "root_summary_published_only_after_all_family_reopens": True,
        "family_objects_required_for_result_read": True,
    }
    assert adapter._require_summary_result_contract(contract) == {
        "chunk_name_width": 3,
        "max_payload_byte_count": 8,
        "max_chunk_count": 2,
        "max_chunk_characters": 8,
    }
    changed = dict(contract)
    changed.pop("aggregate_result_schema")
    with pytest.raises(adapter.FormalQcSubmissionError, match="fields"):
        adapter._require_summary_result_contract(changed)
    variable_capacity_fields = {
        "max_payload_byte_count",
        "max_chunk_count",
        "max_chunk_characters",
    }
    for name in sorted(set(contract) - variable_capacity_fields):
        changed = dict(contract)
        current = changed[name]
        if type(current) is bool:
            changed[name] = not current
        elif type(current) is int:
            changed[name] = current + 1
        else:
            changed[name] = str(current) + "-changed"
        with pytest.raises(adapter.FormalQcSubmissionError, match="changed"):
            adapter._require_summary_result_contract(changed)

    encoded = "MTIzNDU2Nzg5"  # nine decoded bytes across two legal chunks
    launch = types.SimpleNamespace(
        project_id=123, backtest_id="backtest-test", backtest_name="expected"
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="capacity"):
        adapter._extract_arv2_summary_pairs(
            {
                "success": True,
                "backtest": {
                    "projectId": 123,
                    "backtestId": "backtest-test",
                    "name": "expected",
                    "status": "Completed.",
                    "statistics": {
                        adapter.SUMMARY_CHUNK_PREFIX + "000": encoded[:6],
                        adapter.SUMMARY_CHUNK_PREFIX + "001": encoded[6:],
                        adapter.SUMMARY_META_NAME: "bWV0YQ==",
                    },
                },
            },
            launch=launch,
            maximum_chunk_count=2,
            maximum_chunk_characters=8,
            chunk_name_width=3,
            maximum_payload_byte_count=8,
        )
    with pytest.raises(adapter.FormalQcSubmissionError, match="base64"):
        adapter._extract_arv2_summary_pairs(
            {
                "success": True,
                "backtest": {
                    "projectId": 123,
                    "backtestId": "backtest-test",
                    "name": "expected",
                    "status": "Completed.",
                    "statistics": {
                        adapter.SUMMARY_CHUNK_PREFIX + "000": "YQ====",
                        adapter.SUMMARY_META_NAME: "bWV0YQ==",
                    },
                },
            },
            launch=launch,
            maximum_chunk_count=2,
            maximum_chunk_characters=8,
            chunk_name_width=3,
            maximum_payload_byte_count=8,
        )


def _artifact(name: str) -> ArtifactBinding:
    payload = name.encode()
    return ArtifactBinding(
        artifact_id="arv2-" + name,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        artifact_sha256=hashlib.sha256(payload + b"artifact").hexdigest(),
        byte_count=len(payload),
    )


def _accepted() -> AcceptedRiskPairBinding:
    return AcceptedRiskPairBinding(
        pair=_artifact("accepted-risk"),
        capture_id="arv2-capture-test",
        capture_sha256="1" * 64,
        current_source_included_count=10,
        censored_source_included_count=8,
        current_admitted_decision_count=9,
        current_named_preoutcome_refusal_count=1,
        censored_admitted_decision_count=7,
        censored_named_preoutcome_refusal_count=1,
        guidance_admitted_count=0,
        pre_2013_admitted_count=0,
        pristine_point_in_time=False,
        views_share_one_capture=True,
    )


def _power() -> PowerFloorBinding:
    return PowerFloorBinding(
        numeric_receipt=_artifact("power"),
        stock_successor=_artifact("stock-power"),
        disposition=POWER_FEASIBLE_DISPOSITION,
        required_valid_dates=1,
        observed_preoutcome_valid_dates=2,
        required_connected_components=1,
        observed_preoutcome_connected_components=2,
        h20_test_session_capacity=1388,
        preoutcome_candidate_date_count=2,
        valid_h20_test_session_count=2,
        refused_h20_test_session_count=0,
        missing_h20_test_session_count=1386,
        connected_component_instance_count=2,
    )


def _terminal() -> TerminalCensusBinding:
    return TerminalCensusBinding(
        census=_artifact("terminal"),
        terminal_policy_id="arv2-terminal-payoff-benchmark-splice-v1",
        security_count=2,
        lifecycle_coverage_count=2,
        terminal_requirement_count=1,
        terminal_payoff_count=1,
        benchmark_splice_continuation_count=0,
        named_terminal_refusal_count=0,
        silently_omitted_count=0,
    )


def _decision_payload() -> bytes:
    sessions = [
        {
            "view_id": view_id,
            "fold_id": f"arv2-wf-test-{year}",
            "session": f"{year}-01-02",
            "session_position": 0,
            "next_session": f"{year}-01-03",
        }
        for view_id in SOURCE_VIEW_IDS
        for year in range(2020, 2026)
    ]
    rows = []
    requirements = []
    for number, view_id in enumerate(SOURCE_VIEW_IDS, start=1):
        security_id = f"TEST{number} R735QTJ8XC{number}"
        rows.append(
            {
                "decision_id": f"decision-{number}",
                "security_id": security_id,
                "view_id": view_id,
                "fold_id": "arv2-wf-test-2020",
                "decision_session": "2020-01-02",
                "structural_zero": False,
                "session_position": 0,
                "entry_session": "2020-01-03",
                "decision_lineage_sha256": str(number) * 64,
                "publication_contributions": [
                    {
                        "contribution_lineage_sha256": str(number + 2) * 64,
                        "publication_at_utc": "2020-01-02T15:00:00Z",
                        "absolute_decayed_firm_specific_weight": "1",
                    }
                ],
                "exit_sessions": {
                    "1": "2020-01-06",
                    "5": "2020-01-10",
                    "20": "2020-02-03",
                    "60": "2020-04-01",
                },
            }
        )
        requirements.append(
            {
                "requirement_id": f"requirement-{number}",
                "view_id": view_id,
                "fold_id": "arv2-wf-test-2020",
                "session": "2020-01-02",
                "session_position": 0,
                "next_session": "2020-01-03",
                "security_id": security_id,
            }
        )
    return _canonical(
        {
            "schema": DECISION_OBJECT_SCHEMA,
            "row_count": len(rows),
            "rows": rows,
            "economic_session_count": len(sessions),
            "economic_sessions": sessions,
            "economic_return_requirement_count": len(requirements),
            "economic_return_requirements": requirements,
        }
    )


def _terminal_payload() -> bytes:
    return _canonical(
        {
            "schema": TERMINAL_OBJECT_SCHEMA,
            "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
            "row_count": 0,
            "rows": [],
        }
    )


def _capacity(census, **overrides):
    limits = {name: 10_000_000 for name in CAPACITY_LIMIT_NAMES}
    limits.update(
        max_project_file_count=100,
        max_project_source_character_count=2_000_000,
        max_summary_chunk_characters=4_000,
        max_summary_payload_byte_count=200_000,
        max_summary_chunk_count=100,
        max_single_object_byte_count=48 * 1024 * 1024,
        max_object_store_total_input_byte_count=50 * 1024 * 1024,
        min_object_store_available_output_byte_count=128 * 1024 * 1024,
        min_object_store_available_output_file_count=100,
        max_node_memory_byte_count=2 * 1024 * 1024 * 1024,
    )
    limits.update(overrides)
    candidate_bytes = render_formal_qc_capacity_review_candidate(
        census=census, limits=limits
    )
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    receipt = {
        "schema": CAPACITY_REVIEW_SCHEMA,
        "candidate_sha256": candidate_sha256,
        "receipt_id": None,
        "receipt_sha256": None,
        "limits": limits,
        "representative_full_census_verified": True,
        "target_tier_limits_observed": True,
        "cloud_evaluator_equivalence_verified": True,
        "object_store_input_transport_verified": True,
        "object_store_output_write_once_transport_verified": True,
        "summary_statistics_channel_verified": True,
        "summary_root_result_channel_verified": True,
    }
    receipt_sha256 = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    receipt["receipt_id"] = "arv2-formal-qc-capacity-review-" + receipt_sha256
    receipt["receipt_sha256"] = receipt_sha256
    return load_formal_qc_runtime_capacity_binding(
        candidate_bytes=candidate_bytes,
        reviewed_receipt_bytes=canonical_json_bytes(receipt),
    )


def _fixture(monkeypatch: pytest.MonkeyPatch, capacity_overrides=None):
    # Exercise the pure adapter/transport mechanics under an explicit offline
    # test seam.  Production entry points retain immutable hard gates until a
    # non-self-mintable owner/reviewer verifier and reviewed upstream-capacity
    # artifact are implemented.
    monkeypatch.setattr(
        adapter, "_require_non_self_mintable_execution_trust_root",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        adapter, "_require_legacy_materialized_submission_retired", lambda: None
    )
    monkeypatch.setattr(
        adapter, "_require_non_self_mintable_result_read_trust_root",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        adapter, "_require_upstream_materialization_capacity", lambda _manifest: None
    )
    monkeypatch.setattr(
        adapter,
        "verify_formal_qc_host_closure_live",
        _with_closure_value(
            adapter.verify_formal_qc_host_closure_live,
            "binding_guard",
            lambda _kind: None,
        ),
    )
    package = _artifact("production-package")
    security_id = "AAPL R735QTJ8XC9X"
    publication = "2021-01-04T13:00:00Z"
    rows = {
        "formal_contract": [{"schema": FORMAL_CONTRACT_SCHEMA}],
        "contribution_seeds": [{
            "schema": CONTRIBUTION_SEED_SCHEMA,
            "seed_id": "arv2-seed-test",
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "security_id": security_id,
            "minute_requirement_id": build_minute_market_requirement_id(
                security_id=security_id, publication_at_utc=publication
            ),
            "active_intervals": [[100, 101]],
        }],
        "decision_joins": [{
            "schema": DECISION_JOIN_SCHEMA,
            "decision_id": "arv2-decision-test",
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "session_position": 100,
            "security_id": security_id,
            "disposition": "named_preoutcome_refusal",
        }],
        "economic_joins": [{
            "schema": ECONOMIC_JOIN_SCHEMA,
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "session": "2021-01-04",
            "session_position": 100,
            "next_session": "2021-01-05",
        }],
        "daily_requirements": [{
            "schema": DAILY_REQUIREMENT_SCHEMA,
            "requirement_id": build_daily_market_requirement_id(
                security_id=security_id, session="2021-01-04"
            ),
            "security_id": security_id,
            "session": "2021-01-04",
        }],
        "minute_requirements": [{
            "schema": MINUTE_REQUIREMENT_SCHEMA,
            "requirement_id": build_minute_market_requirement_id(
                security_id=security_id, publication_at_utc=publication
            ),
            "security_id": security_id,
            "publication_at_utc": publication,
            "first_active_session_position": 100,
            "last_active_session_position": 100,
        }],
        "terminal_dispositions": [],
    }
    shards = tuple(
        build_formal_qc_compressed_shard(
            role=role, ordinal=0, rows=rows[role]
        )
        for role in SHARD_ROLE_ORDER
    )
    census = derive_formal_qc_runtime_resource_census(
        shards=shards,
        distinct_security_count=1,
        daily_history_batch_count=2,
        minute_history_batch_count=2,
        maximum_dynamic_subscription_count=1,
        projected_summary_payload_byte_count=100_000,
        projected_summary_chunk_count=34,
    )
    evaluator_source = (ROOT / FORMAL_EVALUATOR_PROJECT_PATH).read_bytes()
    cloud_source = (
        ROOT / "research/analyst_revisions_v2_qc/formal_cloud_evaluator.py"
    ).read_bytes()
    evaluator = formal_cloud_evaluator_binding(
        formal_evaluator_source=evaluator_source,
        cloud_evaluator_source=cloud_source,
    )
    manifest_payload = build_formal_qc_input_manifest_bytes(
        production_input_package=package,
        preopen_control_stage_output=_artifact("preopen-control"),
        runtime_start=date(2020, 1, 1),
        runtime_end=date(2025, 12, 31),
        calculation_as_of_date=date(2026, 1, 2),
        benchmark_security_id="SPY R735QTJ8XC9X",
        shards=shards,
        resource_census=census,
        capacity=_capacity(census, **(capacity_overrides or {})),
        cloud_evaluator=evaluator,
    )
    manifest_hash = hashlib.sha256(manifest_payload).hexdigest()
    manifest = build_qc_object_payload_binding(
        role="input_manifest",
        schema=INPUT_MANIFEST_SCHEMA,
        object_store_key=FORMAL_INPUT_PREFIX + manifest_hash + ".json",
        payload=manifest_payload,
    )
    projection = build_formal_qc_runtime_projection(
        input_manifest=manifest,
        formal_evaluator_source=evaluator_source,
        cloud_evaluator_source=cloud_source,
    )
    candidate = build_formal_run_candidate(
        code_projection=formal_code_projection_binding(projection),
        production_input_package=package,
        current_view_partition_set=_artifact("current-partitions"),
        censored_view_partition_set=_artifact("censored-partitions"),
        accepted_risk=_accepted(),
        power_floor=_power(),
        terminal_census=_terminal(),
    )
    upload_bundle = adapter.build_formal_qc_upload_bundle(
        input_manifest=manifest,
        manifest_payload=manifest_payload,
        shards=shards,
    )
    fake_b5d = types.SimpleNamespace(
        projection_id="arv2-b5d-source-set",
        projection_sha256="6" * 64,
        projection_artifact_sha256="7" * 64,
        project_file_count=11,
        total_projected_source_byte_count=1000,
    )
    monkeypatch.setattr(
        adapter, "require_synthetic_qc_runtime_shard_projection", lambda value: value
    )
    host_closure = adapter.build_formal_qc_host_closure_binding(
        worktree_root=ROOT,
        b5d_project_source_set=fake_b5d,
    )
    transport = adapter.build_formal_qc_transport_binding(
        host_code_closure=host_closure
    )
    organization_id = "test-organization-001"
    monkeypatch.setattr(adapter, "require_reviewed_formal_run_authority", lambda *a: a[-1])
    provisional = ReviewedFormalRunAuthority(
        authority_id="arv2-reviewed-test",
        authority_sha256="2" * 64,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        claude_review_commit="a" * 40,
        codex_counterreview_commit="b" * 40,
        owner_decision_id="arv2-owner-test",
        owner_outcome_authority_receipt_id="placeholder",
        review_receipt_artifact_sha256="3" * 64,
        claim_directory=Path("/private/tmp/arv2-test-no-access"),
        maximum_submissions=1,
        result_read_requires_separate_terminal_gate=True,
        _receipt_bytes=b"never-read",
        _external_pin=None,  # type: ignore[arg-type]
    )
    authority_bytes = adapter.render_formal_qc_execution_authority_candidate(
        candidate=candidate,
        projection=projection,
        upload_bundle=upload_bundle,
        host_code_closure=host_closure,
        transport=transport,
        organization_id=organization_id,
    )
    authority_id = json.loads(authority_bytes)["authority_id"]
    reviewed = dataclasses.replace(
        provisional, owner_outcome_authority_receipt_id=authority_id
    )
    execution_authority = adapter.load_formal_qc_execution_authority(
        candidate=candidate,
        reviewed_authority=reviewed,
        projection=projection,
        upload_bundle=upload_bundle,
        host_code_closure=host_closure,
        transport=transport,
        organization_id=organization_id,
        receipt_bytes=authority_bytes,
    )
    plan = adapter.build_formal_qc_submission_plan(
        candidate=candidate,
        authority=reviewed,
        execution_authority=execution_authority,
        projection=projection,
        upload_bundle=upload_bundle,
        organization_id=organization_id,
    )
    claim = FormalLookClaim(
        claim_id="arv2-claim-test",
        claim_sha256="4" * 64,
        authority_id=reviewed.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        claimed_at_utc="2026-09-11T12:00:00.000000Z",
        maximum_submissions=1,
        submission_count_reserved=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        claim_path=Path("/private/tmp/arv2-test-no-access/claim.json"),
        _claim_bytes=b"never-read",
    )
    monkeypatch.setenv("QC_USER_ID", "12345")
    monkeypatch.setenv("QC_API_TOKEN", "offline-test-token")
    _install_offline_action_authority(monkeypatch)
    return candidate, reviewed, execution_authority, projection, plan, claim


class _FakeBackend:
    def __init__(
        self,
        events: list[str],
        *,
        compile_pending_reads: int = 0,
        status_pending_reads: int = 1,
    ) -> None:
        self.events = events
        self.objects: dict[str, bytes] = {}
        self.files: dict[str, str] = {}
        self.compile_reads = 0
        self.compile_pending_reads = compile_pending_reads
        self.status_reads = 0
        self.status_pending_reads = status_pending_reads
        self.created = False
        self.result_statistics = {
            adapter.SUMMARY_META_NAME: "bWV0YQ==",
            adapter.SUMMARY_CHUNK_PREFIX + "000": "Y2h1bms=",
            "Sharpe Ratio": "must-not-be-returned",
        }

    def request(self, path: str, payload: dict[str, object]):
        self.events.append("request:" + path)
        if path == "authenticate":
            return {"success": True}
        if path == "projects/read":
            return {
                "success": True,
                "projects": [self._project()] if self.created else [],
            }
        if path == "projects/create":
            self.created = True
            return {
                "success": True,
                "projects": [self._project()],
            }
        if path == "files/read":
            return {
                "success": True,
                "files": [
                    {"name": name, "content": content}
                    for name, content in sorted(self.files.items())
                ],
            }
        if path in {"files/create", "files/update"}:
            self.files[str(payload["name"])] = str(payload["content"])
            return {"success": True}
        if path == "compile/create":
            return {"success": True, "compileId": "compile-test"}
        if path == "compile/read":
            self.compile_reads += 1
            return {
                "success": True,
                "compileId": "compile-test",
                "state": (
                    "InQueue"
                    if self.compile_reads <= self.compile_pending_reads
                    else "BuildSuccess"
                ),
            }
        if path == "backtests/create":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "backtest-test",
                    "name": payload["backtestName"],
                    "projectId": 123,
                    "status": "In Queue...",
                },
            }
        if path == "backtests/list":
            self.status_reads += 1
            status = (
                "In Progress..."
                if self.status_reads <= self.status_pending_reads
                else "Completed."
            )
            return {
                "success": True,
                "count": 1,
                "backtests": [
                    {
                        "backtestId": "backtest-test",
                        "name": "ARV2 formal stock outcomes 2020-2025 plus 2021-2025 sensitivity",
                        "projectId": 123,
                        "status": status,
                    }
                ],
            }
        if path == "backtests/read":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "backtest-test",
                    "name": (
                        "ARV2 formal stock outcomes 2020-2025 plus "
                        "2021-2025 sensitivity"
                    ),
                    "projectId": 123,
                    "status": "Completed.",
                    "statistics": dict(self.result_statistics),
                },
            }
        raise AssertionError(path)

    @staticmethod
    def _project():
        return {
            "projectId": 123,
            "organizationId": "test-organization-001",
            "name": "ARV2_FORMAL_STOCK_2020_2025_20260911",
            "language": "Py",
            "owner": True,
            "codeRunning": False,
            "collaborators": [{"owner": True}],
            "libraries": [],
        }

    def set_object_multipart(
        self, organization_id: str, key: str, payload: bytes
    ):
        self.events.append("set_object:" + key)
        assert organization_id == "test-organization-001"
        self.objects[key] = payload
        return {"success": True}

    def read_object_bytes_via_metadata(self, organization_id: str, key: str):
        self.events.append("get_object:" + key)
        assert organization_id == "test-organization-001"
        return self.objects[key]


def _FakeClient(
    events, *, monkeypatch, compile_pending_reads=0, status_pending_reads=1
):
    backend = _FakeBackend(
        events,
        compile_pending_reads=compile_pending_reads,
        status_pending_reads=status_pending_reads,
    )

    def http(url, body, headers, timeout):
        del timeout
        path = url.split("/api/v2/", 1)[1]
        if path == "object/set":
            content_type = headers["Content-Type"]
            boundary = content_type.split("boundary=", 1)[1]
            key = body.split(b'name="key"\r\n\r\n', 1)[1].split(
                b"\r\n--" + boundary.encode("ascii"), 1
            )[0].decode("utf-8")
            marker = (
                b'name="objectData"; filename="object.bin"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            payload = body.split(marker, 1)[1].rsplit(
                b"\r\n--" + boundary.encode("ascii") + b"--\r\n", 1
            )[0]
            result = backend.set_object_multipart(
                "test-organization-001", key, payload
            )
        else:
            payload = json.loads(body.decode("utf-8"))
            if path == "object/properties":
                events.append("request:" + path)
                stored = backend.objects[str(payload["key"])]
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

    # Functional tests use the explicit credential-isolated offline seam.
    # Production wrapper/capability provenance is exercised only by refusal
    # tests, so these fixtures cannot populate a production authority vault.
    client = transport_module.FormalQcTransport(
        http_transport=http,
        clock=lambda: 1_789_000_000,
    )
    client._test_backend = backend
    return client


def _permit(candidate, reviewed, claim, events):
    events.append("permit")
    return FormalSubmissionPermit(
        permit_id="arv2-permit-test",
        permit_sha256="5" * 64,
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        authority_id=reviewed.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
        maximum_submissions=1,
        submission_attempt_count=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        permit_path=Path("/private/tmp/arv2-test-no-access/permit.json"),
        _permit_bytes=b"never-read",
    )


def test_exact_execution_authority_is_required_not_an_arbitrary_receipt_id(monkeypatch):
    candidate, reviewed, execution, projection, plan, _ = _fixture(monkeypatch)
    assert execution.authority_id == reviewed.owner_outcome_authority_receipt_id
    assert execution.authority_id.endswith(execution.authority_sha256)
    assert execution.maximum_backtest_submissions == 1
    assert execution.compile_poll_limit == adapter.MAX_COMPILE_POLLS
    assert execution.compile_poll_interval_seconds == 2
    assert execution.status_poll_limit == adapter.MAX_STATUS_POLLS
    assert execution.status_poll_interval_seconds == 30
    assert execution.qc_outcome_execution_authorized is True
    assert execution.result_read_authorized is False
    assert execution.log_access_authorized is False
    assert execution.status_only_access_authorized is True
    assert execution.deployment_orders_trading_authorized is False
    assert tuple(
        source.path for source in execution.host_code_closure.sources
    ) == adapter.REQUIRED_HOST_CODE_PATHS
    assert execution.transport.request_surface == adapter.TRANSPORT_REQUEST_SURFACE
    assert execution.transport.concrete_type == "FormalQcTransport"
    changed_review = dataclasses.replace(
        reviewed, owner_outcome_authority_receipt_id="arv2-arbitrary-safe-id"
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="exact execution"):
        adapter.load_formal_qc_execution_authority(
            candidate=candidate,
            reviewed_authority=changed_review,
            projection=projection,
            upload_bundle=plan.upload_bundle,
            host_code_closure=execution.host_code_closure,
            transport=execution.transport,
            organization_id=plan.organization_id,
            receipt_bytes=execution._receipt_bytes,
        )
    forged_transport = dataclasses.replace(
        execution.transport, implementation_sha256="0" * 64
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="transport binding"):
        adapter.require_formal_qc_transport_binding(
            forged_transport, execution.host_code_closure
        )
    for index, source in enumerate(execution.host_code_closure.sources):
        changed_source = dataclasses.replace(source, content_sha256="0" * 64)
        forged_sources = (
            execution.host_code_closure.sources[:index]
            + (changed_source,)
            + execution.host_code_closure.sources[index + 1:]
        )
        forged_closure = dataclasses.replace(
            execution.host_code_closure, sources=forged_sources,
        )
        with pytest.raises(adapter.FormalQcSubmissionError, match="changed"):
            adapter.require_formal_qc_host_closure_binding(forged_closure)


def test_public_render_load_round_trip_cannot_grant_execution_or_network(monkeypatch):
    candidate, reviewed, execution, projection, plan, claim = _fixture(monkeypatch)
    monkeypatch.setattr(
        adapter,
        "_require_non_self_mintable_execution_trust_root",
        _REAL_EXECUTION_TRUST_GATE,
    )
    match = "non-self-mintable owner/reviewer execution trust root"
    with pytest.raises(adapter.FormalQcSubmissionError, match=match):
        adapter.load_formal_qc_execution_authority(
            candidate=candidate,
            reviewed_authority=reviewed,
            projection=projection,
            upload_bundle=plan.upload_bundle,
            host_code_closure=execution.host_code_closure,
            transport=execution.transport,
            organization_id=plan.organization_id,
            receipt_bytes=execution._receipt_bytes,
        )
    with pytest.raises(adapter.FormalQcSubmissionError, match=match):
        adapter.build_formal_qc_submission_plan(
            candidate=candidate,
            authority=reviewed,
            execution_authority=execution,
            projection=projection,
            upload_bundle=plan.upload_bundle,
            organization_id=plan.organization_id,
        )
    events: list[str] = []
    permit_called = False

    def begin(**_kwargs):
        nonlocal permit_called
        permit_called = True
        raise AssertionError("the hard trust gate must precede permit creation")

    monkeypatch.setattr(adapter, "begin_formal_submission_once", begin)
    with pytest.raises(adapter.FormalQcSubmissionError, match=match):
        adapter.execute_formal_qc_submission_once(
            candidate=candidate,
            authority=reviewed,
            claim=claim,
            projection=projection,
            plan=plan,
            client=_FakeClient(events, monkeypatch=monkeypatch),
            submission_started_at_utc="2026-09-11T12:01:00.000000Z",
        )
    assert permit_called is False
    assert events == []


def test_legacy_runtime_capacity_cannot_replace_upstream_capacity(monkeypatch):
    candidate, _reviewed, execution, projection, plan, _claim = _fixture(monkeypatch)
    manifest_entry = next(
        item for item in plan.upload_bundle.entries if item.role == "input_manifest"
    )
    manifest = json.loads(manifest_entry.payload)
    upstream = manifest["upstream_scoring_materialization_capacity"]
    assert upstream == {
        "schema": "arv2-upstream-one-fold-materialization-capacity-gate-v1",
        "status": "required_reviewed_artifact_not_supplied",
        "artifact_binding": None,
        "distinct_from_runtime_capacity": True,
        "one_fold_streaming_projection_verified": False,
        "production_truth_materialization_capacity_verified": False,
        "representative_full_census_verified": False,
        "launch_authorized": False,
    }
    assert manifest["capacity_evidence_is_submission_authority"] is False
    monkeypatch.setattr(
        adapter,
        "_require_upstream_materialization_capacity",
        _REAL_UPSTREAM_CAPACITY_GATE,
    )
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match="separate reviewed upstream scoring materialization capacity is absent",
    ):
        adapter.render_formal_qc_execution_authority_candidate(
            candidate=candidate,
            projection=projection,
            upload_bundle=plan.upload_bundle,
            host_code_closure=execution.host_code_closure,
            transport=execution.transport,
            organization_id=plan.organization_id,
        )


def test_missing_reviewed_transport_surface_refuses_before_permit(monkeypatch):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    permit_called = False

    def begin(**kwargs):
        nonlocal permit_called
        permit_called = True
        raise AssertionError("permit must not be created")

    monkeypatch.setattr(adapter, "begin_formal_submission_once", begin)
    with pytest.raises(adapter.FormalQcSubmissionError, match="surface is required"):
        adapter.execute_formal_qc_submission_once(
            candidate=candidate,
            authority=reviewed,
            claim=claim,
            projection=projection,
            plan=plan,
            client=object(),
            submission_started_at_utc="2026-09-11T12:01:00.000000Z",
        )
    assert permit_called is False


def test_permit_is_created_immediately_before_first_network_method(monkeypatch):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    monkeypatch.setattr(
        adapter,
        "begin_formal_submission_once",
        lambda **kwargs: _permit(candidate, reviewed, claim, events),
    )
    permit, launch = adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    assert events[:2] == ["permit", "request:authenticate"]
    assert sum(event == "request:backtests/create" for event in events) == 1
    assert launch.backtest_submission_count == 1
    assert launch.include_statistics is False
    assert launch.result_read_authorized is False
    assert launch.orders_authorized is False
    assert permit.permit_id == "arv2-permit-test"


def test_compile_wait_occurs_only_between_pending_poll_requests(monkeypatch):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    events: list[str] = []
    client = _FakeClient(
        events, monkeypatch=monkeypatch, compile_pending_reads=2
    )
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    monkeypatch.setattr(
        adapter,
        "begin_formal_submission_once",
        lambda **kwargs: _permit(candidate, reviewed, claim, events),
    )
    monkeypatch.setattr(
        adapter, "_local_wait",
        lambda seconds: events.append(f"wait:{seconds}"),
    )
    adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    assert events[:2] == ["permit", "request:authenticate"]
    compile_segment = [
        event for event in events
        if event in {"request:compile/read", "wait:2"}
    ]
    assert compile_segment == [
        "request:compile/read",
        "wait:2",
        "request:compile/read",
        "wait:2",
        "request:compile/read",
    ]


def test_replay_refuses_before_a_second_network_method(monkeypatch):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    calls = 0

    def begin(**kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise FormalRunProtocolError("formal look is already spent")
        return _permit(candidate, reviewed, claim, events)

    monkeypatch.setattr(adapter, "begin_formal_submission_once", begin)
    adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    network_count = len(events)
    with pytest.raises(FormalRunProtocolError, match="already spent"):
        adapter.execute_formal_qc_submission_once(
            candidate=candidate,
            authority=reviewed,
            claim=claim,
            projection=projection,
            plan=plan,
            client=client,
            submission_started_at_utc="2026-09-11T12:02:00.000000Z",
        )
    assert len(events) == network_count


def test_status_parser_discards_documented_result_fields_without_interpreting_payload():
    class Explosive:
        def __repr__(self):
            raise AssertionError("forbidden payload was accessed")

        def __eq__(self, _other):
            raise AssertionError("forbidden payload was compared")

    raw = {
        "success": True,
        "count": 1,
        "backtests": [
            {
                "backtestId": "backtest-test",
                "name": "expected",
                # The official list schema does not promise projectId.  The
                # request itself scopes the project, so absence is valid.
                "status": "Completed.",
                "statistics": Explosive(),
                "charts": Explosive(),
                "sharpeRatio": Explosive(),
                "parameterSet": Explosive(),
            }
        ],
    }
    status = adapter.parse_statistics_free_backtest_list(
        raw,
        expected_project_id=123,
        expected_backtest_id="backtest-test",
        expected_backtest_name="expected",
    )
    assert status.status == "Completed."
    assert status.project_id == 123


def test_status_parser_rejects_unknown_or_nested_status_metadata():
    class Explosive:
        def __repr__(self):
            raise AssertionError("forbidden payload was accessed")

    nested = {
        "success": True,
        "count": 1,
        "backtests": [
            {
                "backtestId": "backtest-test",
                "name": "expected",
                "projectId": 123,
                "status": "Completed.",
                "note": {"statistics": Explosive()},
            }
        ],
    }
    with pytest.raises(adapter.FormalQcSubmissionError, match="ignored field shape"):
        adapter.parse_statistics_free_backtest_list(
            nested,
            expected_project_id=123,
            expected_backtest_id="backtest-test",
            expected_backtest_name="expected",
        )

    bounded = {
        "success": True,
        "count": 1,
        "backtests": [
            {
                "backtestId": "backtest-test",
                "name": "expected",
                "projectId": 123,
                "status": "Completed.",
                "undocumentedEnvelope": Explosive(),
            }
        ],
    }
    with pytest.raises(adapter.FormalQcSubmissionError, match="unknown key"):
        adapter.parse_statistics_free_backtest_list(
            bounded,
            expected_project_id=123,
            expected_backtest_id="backtest-test",
            expected_backtest_name="expected",
        )


@pytest.mark.parametrize(
    "field",
    (
        "backtestId", "name", "status", "projectId",
        "created", "completed", "note", "progress",
    ),
)
def test_status_parser_type_preflights_every_consumed_value(field):
    class Explosive:
        def __repr__(self):
            raise AssertionError("hostile status value was represented")

        def __eq__(self, _other):
            raise AssertionError("hostile status value was compared")

        def __hash__(self):
            raise AssertionError("hostile status value was hashed")

    row = {
        "backtestId": "backtest-test",
        "name": "expected",
        "projectId": 123,
        "status": "Completed.",
    }
    row[field] = Explosive()
    with pytest.raises(adapter.FormalQcSubmissionError, match="shape changed"):
        adapter.parse_statistics_free_backtest_list(
            {"success": True, "count": 1, "backtests": [row]},
            expected_project_id=123,
            expected_backtest_id="backtest-test",
            expected_backtest_name="expected",
        )


def test_terminal_status_is_statistics_free_and_result_gate_stays_disabled(monkeypatch):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    monkeypatch.setattr(
        adapter,
        "begin_formal_submission_once",
        lambda **kwargs: _permit(candidate, reviewed, claim, events),
    )
    permit, launch = adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    monkeypatch.setattr(adapter, "require_formal_submission_permit", lambda *a: a[-1])
    terminal = adapter.inspect_statistics_free_terminal_status(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        permit=permit,
        plan=plan,
        launch=launch,
        client=client,
    )
    status_calls = [event for event in events if event == "request:backtests/list"]
    assert len(status_calls) == 2
    assert terminal.terminal_status == "Completed."
    assert terminal.statistics_requested is False
    assert terminal.full_status_envelope_received_and_json_parsed is True
    assert terminal.statistics_or_result_values_selected_or_inspected is False
    assert terminal.discarded_values_retained_in_receipt_or_exported is False
    gate = adapter.build_formal_qc_result_gate_candidate(
        terminal=terminal,
        launch=launch,
        plan=plan,
        permit=permit,
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
    )
    adapter.require_formal_qc_result_gate_candidate(
        value=gate,
        terminal=terminal,
        launch=launch,
        plan=plan,
        permit=permit,
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
    )
    assert gate.terminal_status == "Completed."
    assert gate.result_read_authorized is False
    assert gate.owner_terminal_result_authority_receipt_id is None
    with pytest.raises(TypeError):
        adapter.require_formal_qc_terminal_status_receipt(
            terminal=terminal,
            launch=launch,
            plan=plan,
            permit=permit,
        )
    forged_terminal = dataclasses.replace(terminal, receipt_sha256="0" * 64)
    with pytest.raises(adapter.FormalQcSubmissionError, match="changed"):
        adapter.require_formal_qc_terminal_status_receipt(
            terminal=forged_terminal,
            launch=launch,
            plan=plan,
            permit=permit,
            candidate=candidate,
            authority=reviewed,
            claim=claim,
        )
    forged_gate = dataclasses.replace(gate, result_read_authorized=True)
    with pytest.raises(adapter.FormalQcSubmissionError, match="changed"):
        adapter.require_formal_qc_result_gate_candidate(
            value=forged_gate,
            terminal=terminal,
            launch=launch,
            plan=plan,
            permit=permit,
            candidate=candidate,
            authority=reviewed,
            claim=claim,
            projection=projection,
        )
    forged_identity = dataclasses.replace(gate, gate_sha256="0" * 64)
    with pytest.raises(adapter.FormalQcSubmissionError, match="content identity"):
        adapter.render_formal_qc_result_read_authority_candidate(
            forged_identity,
            launch,
            terminal,
            candidate=candidate,
            reviewed_authority=reviewed,
        )
    assert adapter.formal_qc_submission_adapter_record()[
        "separate_result_read_gate_present"
    ] is True


def _completed_result_context(monkeypatch, tmp_path):
    candidate, reviewed, _, projection, plan, claim = _fixture(monkeypatch)
    ledger_directory = tmp_path / "result-read-ledger"
    ledger_directory.mkdir(mode=0o700)
    os.chmod(ledger_directory, 0o700)
    reviewed = dataclasses.replace(reviewed, claim_directory=ledger_directory)
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda value: None
    )
    monkeypatch.setattr(adapter, "require_formal_look_claim", lambda *a: a[-1])
    monkeypatch.setattr(
        adapter,
        "begin_formal_submission_once",
        lambda **kwargs: _permit(candidate, reviewed, claim, events),
    )
    permit, launch = adapter.execute_formal_qc_submission_once(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
        plan=plan,
        client=client,
        submission_started_at_utc="2026-09-11T12:01:00.000000Z",
    )
    monkeypatch.setattr(adapter, "require_formal_submission_permit", lambda *a: a[-1])
    terminal = adapter.inspect_statistics_free_terminal_status(
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        permit=permit,
        plan=plan,
        launch=launch,
        client=client,
    )
    gate = adapter.build_formal_qc_result_gate_candidate(
        terminal=terminal,
        launch=launch,
        plan=plan,
        permit=permit,
        candidate=candidate,
        authority=reviewed,
        claim=claim,
        projection=projection,
    )
    authority_bytes = adapter.render_formal_qc_result_read_authority_candidate(
        gate,
        launch,
        terminal,
        candidate=candidate,
        reviewed_authority=reviewed,
    )
    pin_bytes = adapter.render_formal_qc_result_read_external_pin_candidate(
        candidate=candidate,
        reviewed_authority=reviewed,
        gate=gate,
        launch=launch,
        terminal=terminal,
        result_authority_receipt_bytes=authority_bytes,
    )
    pin_path = ledger_directory / adapter.RESULT_READ_EXTERNAL_PIN_FILENAME
    pin_path.write_bytes(pin_bytes)
    os.chmod(pin_path, 0o600)
    result_authority = adapter.load_formal_qc_result_read_authority(
        gate=gate,
        launch=launch,
        terminal=terminal,
        candidate=candidate,
        reviewed_authority=reviewed,
        receipt_bytes=authority_bytes,
    )
    monkeypatch.setattr(
        adapter, "verify_formal_qc_host_closure_live", lambda value: value
    )
    return (
        candidate,
        reviewed,
        plan,
        permit,
        claim,
        launch,
        terminal,
        gate,
        result_authority,
        client,
        events,
        pin_path,
    )


def test_public_render_pin_load_round_trip_cannot_grant_result_read(
    monkeypatch, tmp_path
):
    context = _completed_result_context(monkeypatch, tmp_path)
    (
        candidate,
        reviewed,
        plan,
        permit,
        claim,
        launch,
        terminal,
        gate,
        result_authority,
        client,
        events,
        _pin_path,
    ) = context
    monkeypatch.setattr(
        adapter,
        "_require_non_self_mintable_result_read_trust_root",
        _REAL_RESULT_READ_TRUST_GATE,
    )
    match = "non-self-mintable owner/reviewer result-read trust root"
    with pytest.raises(adapter.FormalQcSubmissionError, match=match):
        adapter.load_formal_qc_result_read_authority(
            gate=gate,
            launch=launch,
            terminal=terminal,
            candidate=candidate,
            reviewed_authority=reviewed,
            receipt_bytes=result_authority._receipt_bytes,
        )
    before_reads = events.count("request:backtests/read")
    ledger = result_authority.result_read_ledger_path
    assert not ledger.exists()
    with pytest.raises(adapter.FormalQcSubmissionError, match=match):
        adapter.read_formal_qc_summary_result_once(
            result_authority=result_authority,
            result_gate=gate,
            candidate=candidate,
            reviewed_authority=reviewed,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=permit,
            plan=plan,
            client=client,
            result_read_started_at_utc="2026-09-11T13:00:00Z",
        )
    assert events.count("request:backtests/read") == before_reads
    assert not ledger.exists()


def test_result_read_requires_external_pin_and_durable_exclusive_spend(
    monkeypatch, tmp_path
):
    context = _completed_result_context(monkeypatch, tmp_path)
    (
        candidate,
        reviewed,
        plan,
        permit,
        claim,
        launch,
        terminal,
        gate,
        result_authority,
        client,
        events,
        pin_path,
    ) = context
    pin_mode = pin_path.stat().st_mode & 0o777
    assert pin_mode == 0o600
    before_reads = events.count("request:backtests/read")
    receipt = adapter.read_formal_qc_summary_result_once(
        result_authority=result_authority,
        result_gate=gate,
        candidate=candidate,
        reviewed_authority=reviewed,
        terminal=terminal,
        launch=launch,
        claim=claim,
        submission_permit=permit,
        plan=plan,
        client=client,
        result_read_started_at_utc="2026-09-11T13:00:00Z",
    )
    assert events.count("request:backtests/read") == before_reads + 1
    assert receipt.summary_pairs == (
        (adapter.SUMMARY_CHUNK_PREFIX + "000", "Y2h1bms="),
        (adapter.SUMMARY_META_NAME, "bWV0YQ=="),
    )
    assert receipt.result_read_count == 1
    assert receipt.full_result_envelope_received_and_json_parsed is True
    assert receipt.standard_statistic_values_selected_or_inspected is False
    assert (
        receipt.logs_charts_orders_trades_values_selected_or_inspected is False
    )
    assert receipt.unrelated_values_retained_in_receipt_or_exported is False
    assert receipt.result_read_ledger_path.stat().st_mode & 0o777 == 0o600
    adapter.require_formal_qc_summary_result_read_receipt(
        receipt,
        result_authority=result_authority,
        terminal=terminal,
        launch=launch,
    )
    if hasattr(os, "fork"):
        read_descriptor, write_descriptor = os.pipe()
        child = os.fork()
        if child == 0:  # pragma: no cover - result is reported through the pipe
            os.close(read_descriptor)
            try:
                adapter.require_formal_qc_summary_result_read_receipt(
                    receipt,
                    result_authority=result_authority,
                    terminal=terminal,
                    launch=launch,
                )
            except adapter.FormalQcSubmissionError:
                result = b"refused"
            else:
                result = b"accepted"
            os.write(write_descriptor, result)
            os.close(write_descriptor)
            os._exit(0)
        os.close(write_descriptor)
        outcome = os.read(read_descriptor, 32)
        os.close(read_descriptor)
        _, child_status = os.waitpid(child, 0)
        assert os.WIFEXITED(child_status) and os.WEXITSTATUS(child_status) == 0
        assert outcome == b"refused"
        assert adapter.require_formal_qc_summary_result_read_receipt(
            receipt,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
        ) is receipt
    forged_pairs = (
        (adapter.SUMMARY_CHUNK_PREFIX + "000", "Zm9yZ2Vk"),
        (adapter.SUMMARY_META_NAME, "bWV0YQ=="),
    )
    forged = dataclasses.replace(
        receipt,
        summary_pairs=forged_pairs,
        summary_pairs_sha256=hashlib.sha256(
            adapter._canonical([list(item) for item in forged_pairs])
        ).hexdigest(),
    )
    forged_record = {
        field.name: getattr(forged, field.name)
        for field in dataclasses.fields(forged)
        if field.name not in {"receipt_id", "receipt_sha256"}
        and not field.name.startswith("_")
    }
    forged_record["summary_pairs"] = [list(item) for item in forged_pairs]
    forged_record["result_read_ledger_path"] = str(
        forged.result_read_ledger_path
    )
    forged_id, forged_sha256 = adapter._identified_receipt(
        "arv2-formal-qc-result-read-",
        adapter.RESULT_READ_RECEIPT_SCHEMA,
        forged_record,
    )
    forged = dataclasses.replace(
        forged, receipt_id=forged_id, receipt_sha256=forged_sha256
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter.require_formal_qc_summary_result_read_receipt(
            forged,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
        )
    bindings = FormalCloudEvaluationBindings(
        input_manifest_sha256="1" * 64,
        production_scoring_census_sha256="2" * 64,
        evaluation_input_bundle_id="evaluation-input-test",
        evaluation_input_bundle_sha256="3" * 64,
        terminal_disposition_package_sha256="4" * 64,
        shared_market_panel_sha256="5" * 64,
        shared_market_panel_observation_count=1,
        formal_evaluator_source_sha256="6" * 64,
        evaluator_source_closure_sha256="7" * 64,
        execution_plan_sha256="8" * 64,
        capacity_plan_sha256="9" * 64,
    )
    with pytest.raises(
        formal_evaluation_bridge.FormalEvaluationBridgeError,
        match="streamed submission bridge",
    ):
        formal_evaluation_bridge.build_formal_aggregate_evaluation_receipt(
            result_read_receipt=forged,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
            submission_bridge=None,  # type: ignore[arg-type]
            expected_bindings=bindings,
        )
    with pytest.raises(adapter.FormalQcSubmissionLocked, match="already spent"):
        adapter.read_formal_qc_summary_result_once(
            result_authority=result_authority,
            result_gate=gate,
            candidate=candidate,
            reviewed_authority=reviewed,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=permit,
            plan=plan,
            client=client,
            result_read_started_at_utc="2026-09-11T13:01:00Z",
        )
    assert events.count("request:backtests/read") == before_reads + 1
    receipt_id = id(receipt)
    receipt_ref = weakref.ref(receipt)
    del receipt
    gc.collect()
    assert receipt_ref() is None
    assert receipt_id not in adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES


def test_public_summary_receipt_mirror_cannot_reseal_authority(
    monkeypatch, tmp_path
):
    (
        candidate,
        reviewed,
        plan,
        submission_permit,
        claim,
        launch,
        terminal,
        gate,
        result_authority,
        client,
        _events,
        _pin_path,
    ) = _completed_result_context(monkeypatch, tmp_path)
    receipt = adapter.read_formal_qc_summary_result_once(
        result_authority=result_authority,
        result_gate=gate,
        candidate=candidate,
        reviewed_authority=reviewed,
        terminal=terminal,
        launch=launch,
        claim=claim,
        submission_permit=submission_permit,
        plan=plan,
        client=client,
        result_read_started_at_utc="2026-09-11T13:00:00Z",
    )
    with adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES_LOCK:
        entry = adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES[id(receipt)]
        replacement = tuple(list(entry))
        assert replacement is not entry
        adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES[id(receipt)] = replacement
    with pytest.raises(adapter.FormalQcSubmissionError, match="process-return"):
        adapter.require_formal_qc_summary_result_read_receipt(
            receipt,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
        )
    assert id(receipt) not in adapter._SUMMARY_RESULT_RECEIPT_AUTHORITIES


def test_result_read_missing_or_changed_external_pin_never_becomes_authority(
    monkeypatch, tmp_path
):
    context = _completed_result_context(monkeypatch, tmp_path)
    (
        candidate,
        reviewed,
        _plan,
        _permit,
        _claim,
        launch,
        terminal,
        gate,
        result_authority,
        _client,
        _events,
        pin_path,
    ) = context
    authority_bytes = result_authority._receipt_bytes
    pin_path.unlink()
    with pytest.raises(adapter.FormalQcSubmissionError, match="unavailable"):
        adapter.load_formal_qc_result_read_authority(
            gate=gate,
            launch=launch,
            terminal=terminal,
            candidate=candidate,
            reviewed_authority=reviewed,
            receipt_bytes=authority_bytes,
        )
    pin_path.write_bytes(b"{}\n")
    os.chmod(pin_path, 0o600)
    with pytest.raises(adapter.FormalQcSubmissionError, match="external pin changed"):
        adapter.load_formal_qc_result_read_authority(
            gate=gate,
            launch=launch,
            terminal=terminal,
            candidate=candidate,
            reviewed_authority=reviewed,
            receipt_bytes=authority_bytes,
        )


def test_ambiguous_result_read_consumes_authority_before_network_retry(
    monkeypatch, tmp_path
):
    context = _completed_result_context(monkeypatch, tmp_path)
    (
        candidate,
        reviewed,
        plan,
        permit,
        claim,
        launch,
        terminal,
        gate,
        result_authority,
        client,
        events,
        _pin_path,
    ) = context
    original_http = client._http

    def fail_one_result_read(url, body, headers, timeout):
        if url.endswith("/backtests/read"):
            events.append("request:backtests/read")
            raise RuntimeError("ambiguous transport failure")
        return original_http(url, body, headers, timeout)

    client._http = fail_one_result_read
    with pytest.raises(adapter.FormalQcSubmissionLocked, match="formal look remains consumed"):
        adapter.read_formal_qc_summary_result_once(
            result_authority=result_authority,
            result_gate=gate,
            candidate=candidate,
            reviewed_authority=reviewed,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=permit,
            plan=plan,
            client=client,
            result_read_started_at_utc="2026-09-11T13:00:00Z",
        )
    first_read_count = events.count("request:backtests/read")
    with pytest.raises(adapter.FormalQcSubmissionLocked, match="already spent"):
        adapter.read_formal_qc_summary_result_once(
            result_authority=result_authority,
            result_gate=gate,
            candidate=candidate,
            reviewed_authority=reviewed,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=permit,
            plan=plan,
            client=client,
            result_read_started_at_utc="2026-09-11T13:01:00Z",
        )
    assert events.count("request:backtests/read") == first_read_count


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        pytest.param(
            transport_module.FormalQcTransportError(
                "QuantConnect network request failed"
            ),
            "network_ambiguous",
            id="network-ambiguity",
        ),
        pytest.param(
            transport_module.FormalQcTransportError(
                "QuantConnect backtests/create request was refused"
            ),
            "refused",
            id="definite-provider-refusal",
        ),
        pytest.param(
            transport_module.FormalQcTransportError(
                "QuantConnect response is not UTF-8 JSON"
            ),
            "envelope",
            id="invalid-provider-envelope",
        ),
        pytest.param(
            adapter.FormalQcSubmissionError("compile response changed"),
            "envelope",
            id="validated-response-envelope",
        ),
        pytest.param(RuntimeError("fixture detail"), "network_ambiguous", id="unknown"),
    ],
)
def test_spent_action_failure_class_is_coarse_and_value_free(failure, expected):
    assert adapter._failure_outcome_class(failure) == expected
    locked = adapter.FormalQcSubmissionLocked(
        "submission",
        "permit-fixture",
        type(failure).__name__,
        outcome_class=expected,
    )
    assert locked.outcome_class == expected
    assert "fixture detail" not in str(locked)


def test_submission_plan_mutation_is_refused(monkeypatch):
    candidate, reviewed, _, projection, plan, _ = _fixture(monkeypatch)
    changed = dataclasses.replace(plan, include_statistics=True)
    with pytest.raises(adapter.FormalQcSubmissionError, match="changed"):
        adapter.require_formal_qc_submission_plan(
            value=changed,
            candidate=candidate,
            authority=reviewed,
            projection=projection,
        )


def test_transport_rejects_hostile_base_and_direct_or_cross_scope_calls(monkeypatch):
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        return 200, b'{"success":true}'

    with pytest.raises(
        transport_module.FormalQcTransportError, match="base URL"
    ):
        transport_module.FormalQcTransport(
            base_url="https://example.invalid/api/v2",
            http_transport=http,
            clock=lambda: 1_789_000_000,
        )
    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    assert not hasattr(transport_module, "_new_transport_capability")
    with pytest.raises(TypeError):
        client._post(
            path="authenticate", body=b"{}", content_type="application/json"
        )
    submission = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1},
    )
    production = transport_module.FormalQcTransport()
    with pytest.raises(
        transport_module.FormalQcTransportError, match="capability"
    ):
        production._request_json(submission, "authenticate", {})
    with pytest.raises(
        transport_module.FormalQcTransportError, match="capability"
    ):
        client._post(
            submission,
            path="backtests/list",
            body=b"{}",
            content_type="application/json",
        )
    with pytest.raises(
        transport_module.FormalQcTransportError, match="allowlisted"
    ):
        client._post(
            submission,
            path="data/read",
            body=b"{}",
            content_type="application/json",
        )
    client._base_url = "https://example.invalid/api/v2"
    with pytest.raises(
        transport_module.FormalQcTransportError, match="state changed"
    ):
        client._post(
            submission,
            path="authenticate",
            body=b"{}",
            content_type="application/json",
        )
    assert calls == []


def test_injected_transport_never_receives_environment_credentials(monkeypatch):
    monkeypatch.setenv("QC_USER_ID", "live-user-must-not-leak")
    monkeypatch.setenv("QC_API_TOKEN", "live-token-must-not-leak")
    headers_seen = []

    def http(url, body, headers, timeout):
        del url, body, timeout
        headers_seen.append(dict(headers))
        return 200, b'{"success":true}'

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1},
    )
    client._request_json(capability, "authenticate", {})
    assert len(headers_seen) == 1
    assert "live-user-must-not-leak" not in repr(headers_seen)
    with pytest.raises(
        transport_module.FormalQcTransportError, match="budget exhausted"
    ):
        client._request_json(capability, "authenticate", {})
    assert len(headers_seen) == 1
    with pytest.raises(
        adapter.FormalQcSubmissionError, match="production-only"
    ):
        adapter._require_concrete_transport(client)


def test_streamed_result_transaction_reads_root_then_exact_26_bound_objects(
    monkeypatch,
):
    """One logical result look is exactly one root read plus 26 ordered reads."""

    from research.analyst_revisions_v2_qc import formal_cloud_evaluator as cloud

    events: list[str] = []
    project_id = 123
    organization_id = "test-organization-001"
    input_manifest_sha256 = "1" * 64
    evaluator_sha256 = "2" * 64
    root_manifest = b'{"root":"authenticated-before-family-reads"}\n'
    payloads = tuple(f"family-{ordinal:02d}".encode("ascii") for ordinal in range(26))

    descriptors = []
    for ordinal, payload in enumerate(payloads):
        compressed_sha256 = hashlib.sha256(payload).hexdigest()
        suffix = (
            "arv2/formal/output/report-families/"
            f"{input_manifest_sha256}/{ordinal:02d}-{compressed_sha256}.json.gz"
        )
        record = {
            "ordinal": ordinal,
            "object_store_key_suffix": suffix,
            "compressed_sha256": compressed_sha256,
            "compressed_byte_count": len(payload),
            "uncompressed_byte_count": len(payload) + 1,
        }
        descriptors.append(
            types.SimpleNamespace(
                **record,
                to_record=(lambda value=record: dict(value)),
            )
        )
    descriptors = tuple(descriptors)
    descriptor_root = hashlib.sha256(
        adapter._canonical([item.to_record() for item in descriptors])
    ).hexdigest()
    bindings = types.SimpleNamespace(
        input_manifest_sha256=input_manifest_sha256,
        evaluator_source_closure_sha256=evaluator_sha256,
    )
    root_metadata = {
        "input_manifest_sha256": input_manifest_sha256,
        "cloud_evaluator_sha256": evaluator_sha256,
        "root_manifest_sha256": hashlib.sha256(root_manifest).hexdigest(),
        "root_manifest_byte_count": len(root_manifest),
        "report_family_object_reference_schema": (
            cloud.REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        ),
        "report_family_object_count": 26,
        "report_family_object_inventory_sha256": descriptor_root,
        "report_family_object_total_uncompressed_byte_count": sum(
            item.uncompressed_byte_count for item in descriptors
        ),
        "report_family_object_total_compressed_byte_count": sum(
            item.compressed_byte_count for item in descriptors
        ),
        "report_family_object_full_key_prefix": (
            f"{project_id}/{cloud.REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX}"
        ),
        "object_store_write_once_existing_identical_bytes_only": True,
        "object_store_save_then_reopen_and_rehash_complete": True,
        "object_store_reopened_object_count": 26,
        "raw_report_family_rows_in_summary": False,
    }
    payload_by_key = {
        f"{project_id}/{item.object_store_key_suffix}": payload
        for item, payload in zip(descriptors, payloads, strict=True)
    }

    def http(url, body, headers, timeout):
        del headers, timeout
        path = url.split("/api/v2/", 1)[1]
        events.append("network:" + path)
        if path == "backtests/read":
            response = {"success": True, "backtest": {}}
        elif path == "object/read":
            request = json.loads(body)
            key = request["key"]
            payload = payload_by_key[key]
            response = {
                "success": True,
                "object": {
                    "key": key,
                    "objectData": base64.b64encode(payload).decode("ascii"),
                },
            }
        else:  # pragma: no cover - exact path inventory is asserted below
            raise AssertionError(path)
        return 200, json.dumps(response, separators=(",", ":")).encode("ascii")

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    monkeypatch.setattr(
        adapter, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda _value: None
    )
    minted_capabilities = []

    def offline_minter(*, transport, scope, binding_record, call_budget):
        minted_capabilities.append(
            (scope, dict(binding_record), dict(call_budget))
        )
        return transport_module._mint_offline_test_capability(
            transport,
            scope=scope,
            call_budget=call_budget,
            binding_record=binding_record,
        )

    candidate = types.SimpleNamespace(candidate_id="candidate", candidate_sha256="3" * 64)
    reviewed = types.SimpleNamespace(authority_id="reviewed", authority_sha256="4" * 64)
    launch = types.SimpleNamespace(
        receipt_id="launch", receipt_sha256="5" * 64,
        project_id=project_id, backtest_id="backtest", backtest_name="formal",
    )
    terminal = types.SimpleNamespace(receipt_id="terminal", terminal_status="Completed.")
    power = types.SimpleNamespace(binding_id="power", binding_sha256="6" * 64)
    economic = types.SimpleNamespace(
        binding_id="economic", binding_sha256="7" * 64,
        definition_id="definition", definition_sha256="8" * 64,
    )
    report = types.SimpleNamespace(
        contract_sha256="9" * 64, artifact_sha256="a" * 64,
        stock_bootstrap_seed_sha256="b" * 64,
    )
    runtime_bridge = types.SimpleNamespace(
        bridge_id="runtime", bridge_sha256="c" * 64,
        input_manifest_payload=b"{}\n",
    )
    submitted = types.SimpleNamespace(
        formal_run_candidate=candidate,
        reviewed_authority=reviewed,
        plan=types.SimpleNamespace(
            candidate_id=candidate.candidate_id,
            reviewed_authority_id=reviewed.authority_id,
            organization_id=organization_id,
        ),
        runtime_bridge=runtime_bridge,
        bridge_id="submission", bridge_sha256="d" * 64,
        authenticated_power_floor=power,
        economic_execution=economic,
        report_contract=report,
        execution_authority=types.SimpleNamespace(host_code_closure=object()),
    )
    result_authority = types.SimpleNamespace(
        backtest_id=launch.backtest_id,
        terminal_receipt_id=terminal.receipt_id,
        candidate_id=candidate.candidate_id,
        reviewed_authority_id=reviewed.authority_id,
        authority_sha256="e" * 64,
        _owner_signature=object(), _receipt_bytes=b"signed",
    )
    result_gate = types.SimpleNamespace(
        runtime_bridge_id=runtime_bridge.bridge_id,
        runtime_bridge_sha256=runtime_bridge.bridge_sha256,
        submission_adapter_bridge_id=submitted.bridge_id,
        submission_adapter_bridge_sha256=submitted.bridge_sha256,
        authenticated_power_floor_id=power.binding_id,
        authenticated_power_floor_sha256=power.binding_sha256,
        economic_execution_binding_id=economic.binding_id,
        economic_execution_binding_sha256=economic.binding_sha256,
        economic_execution_definition_id=economic.definition_id,
        economic_execution_definition_sha256=economic.definition_sha256,
    )
    permit = types.SimpleNamespace(permit_id="permit", permit_sha256="f" * 64)

    monkeypatch.setattr(
        adapter, "require_streamed_formal_submission_adapter_bridge",
        lambda _value: submitted,
    )
    for name in (
        "_require_non_self_mintable_result_read_trust_root",
        "require_streamed_formal_qc_result_gate_candidate",
        "require_formal_qc_result_read_authority",
        "require_streamed_formal_qc_launch_receipt",
        "require_streamed_formal_qc_terminal_status_receipt",
        "verify_formal_qc_host_closure_live",
        "_require_streamed_authenticated_power_floor",
        "_require_streamed_economic_execution",
        "_require_streamed_report_contract",
    ):
        monkeypatch.setattr(adapter, name, lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        adapter,
        "_streamed_summary_result_contract",
        lambda _value: {
            "chunk_name_width": 3,
            "max_payload_byte_count": 200_000,
            "max_chunk_count": 100,
            "max_chunk_characters": 4_000,
        },
    )
    monkeypatch.setattr(
        adapter, "_begin_formal_qc_result_read_once", lambda **_kwargs: permit
    )

    def extract_root(_raw, **_kwargs):
        assert events == ["network:backtests/read"]
        events.append("validate:root-envelope")
        return ((adapter.SUMMARY_META_NAME, "root"),)

    def reconstruct_root(_pairs, **_kwargs):
        events.append("validate:root-content")
        return root_manifest, root_metadata

    monkeypatch.setattr(adapter, "_extract_arv2_summary_pairs", extract_root)
    monkeypatch.setattr(adapter, "_reconstruct_formal_result_root", reconstruct_root)
    monkeypatch.setattr(
        cloud,
        "derive_streamed_formal_evaluation_preknown_bindings_record",
        lambda _manifest: {"preknown": True},
    )

    def derive_read_plan(_root, *, expected_preknown_bindings):
        assert expected_preknown_bindings == {"preknown": True}
        assert not any(item == "network:object/read" for item in events)
        events.append("validate:root-read-plan")
        return bindings, descriptors

    monkeypatch.setattr(
        cloud,
        "derive_formal_cloud_evaluation_family_object_read_plan",
        derive_read_plan,
    )
    validated_ordinals: list[int] = []

    def validate_family(_root, *, expected_bindings, descriptor, payload):
        assert expected_bindings is bindings
        assert payload == payloads[descriptor.ordinal]
        validated_ordinals.append(descriptor.ordinal)
        events.append(f"validate:family:{descriptor.ordinal:02d}")

    monkeypatch.setattr(
        cloud,
        "require_formal_cloud_evaluation_family_object_payload",
        validate_family,
    )

    def validate_aggregate(_root, *, expected_bindings, report_family_object_payloads):
        assert expected_bindings is bindings
        assert tuple(report_family_object_payloads.values()) == payloads
        assert events.count("network:object/read") == 26
        events.append("validate:aggregate")

    monkeypatch.setattr(
        cloud,
        "require_formal_cloud_evaluation_aggregate_bytes",
        validate_aggregate,
    )

    implementation = _closure_value(
        adapter.read_streamed_formal_qc_summary_result_once,
        "streamed_read_implementation",
    )
    captured = implementation(
        result_authority=result_authority,
        result_gate=result_gate,
        submission_bridge=submitted,
        terminal=terminal,
        launch=launch,
        claim=object(),
        submission_permit=object(),
        client=client,
        result_read_started_at_utc="2026-09-12T12:00:00Z",
        _authority_mint_completed=lambda **values: values,
        _transport_capability_minter=offline_minter,
    )

    assert events[:4] == [
        "network:backtests/read",
        "validate:root-envelope",
        "validate:root-content",
        "validate:root-read-plan",
    ]
    assert events.count("network:backtests/read") == 1
    assert events.count("network:object/read") == 26
    assert sum(item.startswith("network:") for item in events) == 27
    assert validated_ordinals == list(range(26))
    assert events == [
        "network:backtests/read",
        "validate:root-envelope",
        "validate:root-content",
        "validate:root-read-plan",
        *(
            item
            for ordinal in range(26)
            for item in (
                "network:object/read",
                f"validate:family:{ordinal:02d}",
            )
        ),
        "validate:aggregate",
    ]
    assert [item[0] for item in minted_capabilities] == [
        "result_read",
        "result_family_read",
    ]
    assert minted_capabilities[0][2] == {"backtests/read": 1}
    family_scope, family_binding, family_budget = minted_capabilities[1]
    assert family_scope == "result_family_read"
    assert family_budget == {"object/read": 26}
    assert family_binding == {
        "schema": adapter.RESULT_FAMILY_READ_CAPABILITY_SCHEMA,
        "project_id": project_id,
        "organization_id": organization_id,
        "descriptor_root_sha256": descriptor_root,
        "object_store_keys": list(payload_by_key),
        "root_manifest_sha256": hashlib.sha256(root_manifest).hexdigest(),
        "result_read_receipt_pending": True,
        "result_disposition_authority": False,
        "deployment_authority": False,
        "orders_authority": False,
        "trading_authority": False,
    }
    assert events[-1] == "validate:aggregate"
    assert captured["root_manifest"] == root_manifest
    assert captured["family_payloads"] == tuple(
        (descriptor.object_store_key_suffix, payload)
        for descriptor, payload in zip(descriptors, payloads, strict=True)
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_transport_capabilities_and_production_minter_do_not_cross_fork():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, headers, timeout))
        return 200, b'{"success":true}'

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    scoped = (
        ("submission", "authenticate"),
        ("status", "backtests/list"),
        ("result_read", "backtests/read"),
        ("preopen_output_read", "object/read"),
        ("power_calibration_output_read", "object/read"),
    )
    capabilities = tuple(
        transport_module._mint_offline_test_capability(
            client, scope=scope, call_budget={path: 1}
        )
        for scope, path in scoped
    )
    production_minter = _closure_value(
        adapter.inspect_statistics_free_terminal_status,
        "transport_capability_minter",
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - result is reported through the pipe
        os.close(read_descriptor)
        outcomes = []
        for capability, (_scope, path) in zip(capabilities, scoped, strict=True):
            try:
                client._post(
                    capability,
                    path=path,
                    body=b"{}",
                    content_type="application/json",
                )
            except transport_module.FormalQcTransportError:
                outcomes.append("refused")
            else:
                outcomes.append("accepted")
        try:
            production_minter(
                transport=transport_module.FormalQcTransport(),
                scope="status",
                binding_record={"schema": "fork-test"},
                call_budget={"backtests/list": 1},
            )
        except transport_module.FormalQcTransportError:
            outcomes.append("minter-refused")
        else:
            outcomes.append("minter-accepted")
        os.write(write_descriptor, ",".join(outcomes).encode("ascii"))
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 256)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"refused,refused,refused,refused,refused,minter-refused"
    assert calls == []
    for capability, (_scope, path) in zip(capabilities, scoped, strict=True):
        client._post(
            capability,
            path=path,
            body=b"{}",
            content_type="application/json",
        )
    assert len(calls) == len(scoped)


def test_transport_one_call_budget_is_atomic_across_threads():
    calls = []
    calls_lock = threading.Lock()
    start = threading.Barrier(3)

    def http(url, body, headers, timeout):
        with calls_lock:
            calls.append((url, body, headers, timeout))
        return 200, b'{"success":true}'

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    outcomes = []

    def invoke() -> None:
        start.wait()
        try:
            client._request_json(capability, "authenticate", {})
        except transport_module.FormalQcTransportError:
            result = "refused"
        else:
            result = "accepted"
        with calls_lock:
            outcomes.append(result)

    workers = tuple(threading.Thread(target=invoke) for _ in range(2))
    for worker in workers:
        worker.start()
    start.wait()
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert sorted(outcomes) == ["accepted", "refused"]
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ("http", "timeout", "clock"))
def test_production_transport_reauthenticates_configuration_before_credentials(
    mutation,
):
    hostile_calls = []

    def hostile_http(*args):
        hostile_calls.append(args)
        return 200, b'{"success":true}'

    client = transport_module.FormalQcTransport()
    if mutation == "http":
        client._http = hostile_http
    elif mutation == "timeout":
        client._timeout = 1.0
    else:
        client._clock = lambda: 1_789_000_000
    with pytest.raises(
        transport_module.FormalQcTransportError,
        match="injected/offline transport",
    ):
        client._require_production_configuration()
    assert hostile_calls == []


def test_production_transport_reauthenticates_after_clock_before_credentials(
):
    safe_calls = []
    hostile_calls = []
    state = {}

    def safe_http(*args):
        safe_calls.append(args)
        return 200, b'{"success":true}'

    def mutate_during_clock():
        state["capability"].production_transport = True
        state["client"]._http = lambda *args: hostile_calls.append(args)
        return 1_789_000_000

    client = transport_module.FormalQcTransport(
        http_transport=safe_http,
        clock=mutate_during_clock,
    )
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    state.update(client=client, capability=capability)
    with pytest.raises(
        transport_module.FormalQcTransportError,
        match="configuration changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert safe_calls == []
    assert hostile_calls == []


@pytest.mark.parametrize(
    "response",
    (
        b'{"success":true,"success":true}',
        b'{"success":true,"backtest":{"id":1,"id":2}}',
        (
            b'{"success":true,"backtest":{"statistics":'
            b'{"ARV2_SUMMARY_000":"a","ARV2_SUMMARY_000":"b"}}}'
        ),
        b'{"success":true,"ignored":NaN}',
        b'{"success":true,"ignored":Infinity}',
    ),
)
def test_transport_rejects_duplicate_keys_and_nonstandard_constants(response):
    def http(_url, _body, _headers, _timeout):
        return 200, response

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    with pytest.raises(
        transport_module.FormalQcTransportError, match="UTF-8 JSON"
    ):
        client._request_json(capability, "authenticate", {})


def test_transport_preserves_forward_compatible_finite_ignored_floats():
    def http(_url, _body, _headers, _timeout):
        return 200, b'{"success":true,"futureProgress":0.25}'

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    assert client._request_json(capability, "authenticate", {}) == {
        "success": True,
        "futureProgress": 0.25,
    }


def test_multipart_boundary_collision_refuses_before_http(monkeypatch):
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, headers, timeout))
        return 200, b'{"success":true}'

    client = transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )
    boundary = "ARV2" + "c" * 64
    capability = transport_module._mint_offline_test_capability(
        client, scope="submission", call_budget={"object/set": 1},
    )
    monkeypatch.setattr(
        transport_module, "_multipart_boundary", lambda exact_bytes: boundary
    )
    offline_method = _with_closure_value(
        transport_module.FormalQcTransport._set_object_multipart,
        "binding_guard",
        lambda _capability: None,
    )
    payload = b"licensed-bytes\r\n--" + boundary.encode("ascii") + b"\r\n"
    with pytest.raises(
        transport_module.FormalQcTransportError, match="collides"
    ):
        types.MethodType(offline_method, client)(
            capability, "test-org", "arv2/formal/input/test.bin", payload
        )
    assert calls == []


def test_project_capacity_is_checked_against_exact_projection(monkeypatch):
    _, _, _, projection, plan, _ = _fixture(monkeypatch)
    file_count = len(projection.source_files)
    character_count = sum(item.character_count for item in projection.source_files)
    adapter._require_upload_projection_capacity(plan.upload_bundle, projection)
    _fixture(
        monkeypatch,
        {
            "max_project_file_count": file_count,
            "max_project_source_character_count": character_count,
        },
    )
    with pytest.raises(
        adapter.FormalQcSubmissionError, match="project/Object Store capacity"
    ):
        _fixture(monkeypatch, {"max_project_file_count": file_count - 1})
    with pytest.raises(
        adapter.FormalQcSubmissionError, match="project/Object Store capacity"
    ):
        _fixture(
            monkeypatch,
            {"max_project_source_character_count": character_count - 1},
        )


@pytest.mark.parametrize(
    ("binding", "message"),
    (
        (
            "power",
            "streamed launch lacks an authenticated power-floor binding",
        ),
        (
            "economic",
            "streamed economic execution binding did not authenticate",
        ),
        (
            "report",
            "streamed formal report contract did not authenticate",
        ),
    ),
)
def test_streamed_launch_binding_authentication_refusals_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
    binding: str,
    message: str,
):
    if binding == "power":
        from research.analyst_revisions_v2_qc import power_calibration_bridge

        def refuse_power(_value):
            raise power_calibration_bridge.AcceptedRiskPowerCalibrationError(
                "offline invalid binding"
            )

        monkeypatch.setattr(
            power_calibration_bridge,
            "require_authenticated_power_floor_binding",
            refuse_power,
        )
        action = lambda: adapter._require_streamed_authenticated_power_floor(
            object(), object()
        )
    elif binding == "economic":
        def refuse_economic(_value):
            raise adapter.FormalEconomicExecutionDefinitionError(
                "offline invalid binding"
            )

        monkeypatch.setattr(
            adapter,
            "require_formal_economic_execution_binding",
            refuse_economic,
        )
        action = lambda: adapter._require_streamed_economic_execution(
            object(), object()
        )
    else:
        economic = types.SimpleNamespace(definition_sha256="1" * 64)
        bridge = types.SimpleNamespace(economic_execution=economic)
        monkeypatch.setattr(
            adapter,
            "_require_streamed_runtime_bridge",
            lambda _value: bridge,
        )
        monkeypatch.setattr(
            adapter,
            "_require_streamed_economic_execution",
            lambda *_args: economic,
        )

        def refuse_report(*_args, **_kwargs):
            raise adapter.FormalReportContractError("offline invalid binding")

        monkeypatch.setattr(adapter, "require_formal_report_contract", refuse_report)
        action = lambda: adapter._require_streamed_report_contract(
            object(), bridge
        )

    with pytest.raises(adapter.FormalQcSubmissionError, match=re.escape(message)):
        action()


def _fresh_host_closure(monkeypatch: pytest.MonkeyPatch):
    fake_b5d = types.SimpleNamespace(
        projection_id="arv2-b5d-test-source-set",
        projection_sha256="1" * 64,
        projection_artifact_sha256="2" * 64,
        project_file_count=11,
        total_projected_source_byte_count=1000,
    )
    monkeypatch.setattr(
        adapter,
        "require_synthetic_qc_runtime_shard_projection",
        lambda value: value,
    )
    return adapter.build_formal_qc_host_closure_binding(
        worktree_root=ROOT,
        b5d_project_source_set=fake_b5d,
    )


def test_host_source_manifest_closure_identity_and_live_change_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
):
    closure = _fresh_host_closure(monkeypatch)
    cases = (
        (
            dataclasses.replace(closure, sources=closure.sources[:-1]),
            "host closure source manifest changed",
        ),
        (
            dataclasses.replace(closure, _canonical_document=b"{}\n"),
            "host closure changed",
        ),
    )
    for changed, message in cases:
        with pytest.raises(
            adapter.FormalQcSubmissionError,
            match=re.escape(message),
        ):
            adapter.require_formal_qc_host_closure_binding(changed)

    raw = json.loads(closure._canonical_document)
    raw["closure_sha256"] = "0" * 64
    wrong_identity = dataclasses.replace(
        closure,
        closure_sha256="0" * 64,
        _canonical_document=_canonical(raw),
    )
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match=re.escape("host closure identity changed"),
    ):
        adapter.require_formal_qc_host_closure_binding(wrong_identity)

    live_verifier = _closure_value(
        adapter.verify_formal_qc_host_closure_live,
        "implementation",
    )
    monkeypatch.setattr(
        adapter,
        "require_formal_qc_host_closure_binding",
        lambda value: value,
    )
    monkeypatch.setattr(adapter, "_read_live_host_sources", lambda _root: ())
    with pytest.raises(
        adapter.FormalQcSubmissionError,
        match=re.escape("live host code closure changed"),
    ):
        live_verifier(closure)


def test_streamed_execution_owner_pin_binding_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
):
    candidate = object()
    bridge = types.SimpleNamespace(formal_run_candidate=candidate)
    reviewed = types.SimpleNamespace(
        owner_outcome_authority_receipt_id="different-authority"
    )
    receipt = _canonical({"authority_id": "expected-authority"})
    monkeypatch.setattr(
        adapter,
        "_require_streamed_runtime_bridge",
        lambda value: value,
    )
    monkeypatch.setattr(
        adapter,
        "require_reviewed_formal_run_authority",
        lambda *_args: reviewed,
    )
    monkeypatch.setattr(
        adapter,
        "render_streamed_formal_qc_execution_authority_candidate",
        lambda **_kwargs: receipt,
    )
    monkeypatch.setattr(
        adapter,
        "_require_non_self_mintable_execution_trust_root",
        lambda *_args: None,
    )
    message = "owner review pin does not bind this exact streamed execution authority"
    with pytest.raises(adapter.FormalQcSubmissionError, match=re.escape(message)):
        adapter.load_streamed_formal_qc_execution_authority(
            runtime_bridge=bridge,  # type: ignore[arg-type]
            reviewed_authority=reviewed,  # type: ignore[arg-type]
            host_code_closure=object(),  # type: ignore[arg-type]
            transport=object(),  # type: ignore[arg-type]
            organization_id="test-organization",
            receipt_bytes=receipt,
        )


def _isolated_streamed_launch_context(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
):
    entry = adapter.FormalQcUploadEntry(
        role="input_shard",
        object_store_key="arv2/formal/input/test.json.gz",
        content_sha256=hashlib.sha256(b"x").hexdigest(),
        content_md5=hashlib.md5(b"x", usedforsecurity=False).hexdigest(),
        byte_count=1,
        payload=b"x",
    )
    upload_entries = (entry,) if failure == "object-metadata" else ()
    projection = types.SimpleNamespace(source_files=())
    plan = types.SimpleNamespace(
        plan_id="streamed-plan",
        plan_sha256="1" * 64,
        organization_id="test-organization-001",
        project_name="ARV2_FORMAL_STOCK_2020_2025_20260911",
        backtest_name="ARV2 formal stock outcomes",
        upload_entry_count=len(upload_entries),
        compile_poll_limit=2,
        compile_poll_interval_seconds=0,
    )
    candidate = types.SimpleNamespace(candidate_sha256="2" * 64)
    authority = types.SimpleNamespace(authority_sha256="3" * 64)
    economic = types.SimpleNamespace(
        binding_sha256="4" * 64,
        definition_sha256="5" * 64,
    )
    report = types.SimpleNamespace(
        contract_sha256="6" * 64,
        artifact_sha256="7" * 64,
        stock_bootstrap_seed_sha256="8" * 64,
    )
    runtime_bridge = types.SimpleNamespace(
        bridge_sha256="9" * 64,
        runtime_projection=projection,
    )
    execution = types.SimpleNamespace(
        _owner_signature=None,
        _receipt_bytes=b"receipt",
        host_code_closure=object(),
    )
    permit = types.SimpleNamespace(
        permit_id="permit-test",
        permit_sha256="a" * 64,
    )
    submitted = types.SimpleNamespace(
        bridge_sha256="b" * 64,
        formal_run_candidate=candidate,
        reviewed_authority=authority,
        plan=plan,
        runtime_bridge=runtime_bridge,
        execution_authority=execution,
        authenticated_power_floor=types.SimpleNamespace(binding_sha256="c" * 64),
        economic_execution=economic,
        report_contract=report,
    )
    project = {
        "projectId": 123,
        "organizationId": plan.organization_id,
        "name": plan.project_name,
        "language": "Py",
        "owner": True,
        "codeRunning": False,
        "collaborators": [],
        "libraries": [],
    }
    project_reads = 0
    file_reads = 0

    def transport_call(_client, _capability, method, *args, **_kwargs):
        nonlocal project_reads, file_reads
        if method == "_set_object_multipart":
            return {"success": True}
        if method == "_read_object_properties":
            return {
                "success": True,
                "metadata": {
                    "key": entry.object_store_key,
                    "size": entry.byte_count,
                    "md5": "0" * 32,
                },
            }
        assert method == "_request_json"
        endpoint = args[0]
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            project_reads += 1
            if project_reads == 1:
                return {
                    "success": True,
                    "projects": [project] if failure == "pre-existing" else [],
                }
            return {"success": True, "projects": [project]}
        if endpoint == "projects/create":
            return {"success": True, "projects": [project]}
        if endpoint == "files/read":
            file_reads += 1
            files = (
                [{"name": "unexpected.py", "content": "pass\n"}]
                if failure == "extra-file" and file_reads == 1
                else []
            )
            return {"success": True, "files": files}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-test"}
        if endpoint == "compile/read":
            return {
                "success": True,
                "compileId": "compile-test",
                "state": "BuildError",
            }
        raise AssertionError(endpoint)

    for name, replacement in (
        ("require_streamed_formal_submission_adapter_bridge", lambda value: value),
        ("_require_non_self_mintable_execution_trust_root", lambda *_args: None),
        ("require_streamed_formal_qc_submission_plan", lambda **_kwargs: plan),
        ("require_formal_look_claim", lambda *_args: object()),
        ("_require_concrete_transport", lambda value: value),
        ("verify_formal_qc_host_closure_live", lambda _value: None),
        ("_preflight_streamed_upload", lambda _value: None),
        ("_require_streamed_authenticated_power_floor", lambda *_args: object()),
        ("_require_streamed_economic_execution", lambda *_args: object()),
        ("_require_streamed_report_contract", lambda *_args: object()),
        ("begin_formal_submission_once", lambda **_kwargs: permit),
        ("_iter_streamed_upload_entries", lambda _value: iter(upload_entries)),
        ("_external", lambda _closure, action: action()),
        ("_transport_call", transport_call),
    ):
        monkeypatch.setattr(adapter, name, replacement)
    implementation = _closure_value(
        adapter.execute_streamed_formal_qc_submission_once,
        "streamed_execute_implementation",
    )
    return implementation, submitted


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("pre-existing", "exact formal project already exists"),
        ("extra-file", "new project contains an unexpected source file"),
        (
            "object-metadata",
            "Object Store metadata does not authenticate uploaded bytes",
        ),
        ("compile", "formal source did not compile successfully"),
    ),
)
def test_streamed_remote_launch_refusals_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    message: str,
):
    implementation, submitted = _isolated_streamed_launch_context(
        monkeypatch,
        failure,
    )
    with pytest.raises(adapter.FormalQcSubmissionLocked) as raised:
        implementation(
            submission_bridge=submitted,
            claim=object(),
            client=object(),
            submission_started_at_utc="2026-09-12T12:01:00.000000Z",
            _authority_register_launch=lambda *_args, **_kwargs: pytest.fail(
                "launch receipt must not be created"
            ),
            _transport_capability_minter=lambda **_kwargs: object(),
        )
    assert type(raised.value.__cause__) is adapter.FormalQcSubmissionError
    assert str(raised.value.__cause__) == message


def test_result_read_ledger_refuses_non_private_file_mode(tmp_path: Path):
    ledger = (tmp_path / "result-read-ledger.json").absolute()
    ledger.write_bytes(b"{}\n")
    ledger.chmod(0o644)
    message = (
        "result-read ledger entry is not a bounded private mode-0600 regular file"
    )
    with pytest.raises(adapter.FormalQcSubmissionError, match=re.escape(message)):
        adapter._read_private_result_control(ledger, "result-read ledger entry")
