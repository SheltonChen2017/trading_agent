"""Synthetic only: no retained captures, native QC, credentials or network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_owner_repair_terminal_capture as m

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
TOKEN = "synthetic-credential-never-native"
DISCOVERY_NAME = "TPR-EXT26-OWNER-MIA-DISCOVERY-SUCCESSOR-SYNTHETIC-001.result.json"


@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def denied(*_a, **_k): raise AssertionError("actual private/native/credential/network/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    original = m.files._directory
    def directory(path, *, private):
        if private and (path == m.PRIVATE_ROOT or path.is_relative_to(m.LANE)): denied()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", directory)


def response(job, snapshot, status="RuntimeError"):
    return {"success": True, "projectId": m.PROJECT, "backtest": {
        "projectId": m.PROJECT, "backtestId": job, "snapshotId": snapshot,
        "compileId": None, "status": status, "completed": True, "progress": m.e.JsonNumber("1.0000000"),
        "created": "2026-10-20 14:45:00", "startDate": "2021-01-04T00:00:00",
        "endDate": "2026-10-09T23:59:59Z", "error": None if status == "Completed." else
            'ValueError SYNTHETIC PRIVATE MESSAGE\nFile "/private/main.py", line 1028\nFile "/private/secret_module.py", line 4',
        "statistics": {"Sharpe Ratio": "SYNTHETIC PRIVATE OUTCOME", "private-key": "SYNTHETIC PRIVATE VALUE"},
        "parameters": {"private": "SYNTHETIC PRIVATE PARAMETER"}, "source": "SYNTHETIC PRIVATE SOURCE"}}


def fixture(tmp_path):
    root = tmp_path / "synthetic-owner-repair"; root.mkdir(mode=0o700)
    discovery = {"schema": "tpr-ext26-owner-mia-discovery-successor-receipt-v1", "status": "COMPLETED_METADATA",
        "operation_id": DISCOVERY_NAME[:-len(".result.json")], "project_id": m.PROJECT,
        "jobs": [{"backtest_id": job, "snapshot_id_observed": snapshot} for job, snapshot, _ in m.JOBS]}
    raw = m.e.canonical(discovery)
    fd = os.open(root / DISCOVERY_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try: os.write(fd, raw)
    finally: os.close(fd)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-REPAIR-TERMINAL-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(value) for name, value in SOURCES.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(), expires_utc=(NOW + timedelta(minutes=10)).isoformat(),
        discovery_reference={"name": DISCOVERY_NAME, "bytes": len(raw), "sha256": m._sha(raw)}, mode="offline-fixture")
    return plan, deepcopy(SOURCES), root


def transport(fault=None):
    calls = []
    def read(plan, payload, seconds, claim):
        index = len(calls); calls.append((payload, seconds, claim))
        job, snapshot, _ = m.JOBS[index]
        value = response(job, snapshot, "Completed." if index == 2 else "RuntimeError")
        if fault: return fault(index, value)
        return m.e.canonical(value), 200, TOKEN
    return read, calls


def execute(values, reading=None, **kwargs):
    plan, sources, root = values
    return m.e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW),
        transport=transport()[0] if reading is None else reading, **kwargs))


def number(value): return int(value.fraction())


def test_all_three_actual_jobs_retained_with_nullable_compile_and_no_acceptance(tmp_path):
    values = fixture(tmp_path); reading, calls = transport(); result = execute(values, reading)
    assert result["schema"] == "tpr-ext26-owner-repair-terminal-receipt-v1"
    assert result["status"] == "COMPLETED_TERMINAL_METADATA" and len(calls) == 3
    assert [row["backtest_id"] for row in result["observations"]] == [row[0] for row in m.JOBS]
    assert [number(row["retrospective_look_ordinal"]) for row in result["observations"]] == [31, 32, 33]
    assert all(row["native_compile_id"] is None and row["native_dates_timezone_assumption"] is None for row in result["observations"])
    assert result["observations"][0]["progress"].lexeme == "1.0000000"
    assert result["observations"][0]["public_file_frames"] == [{"file": "main.py", "line": m.e.JsonNumber("1028")}]
    assert result["observations"][0]["error_type_enums"] == ["ValueError"]
    assert result["observations"][2]["error_is_null"] is True
    assert result["observations"][0]["statistics_key_names"]["statistics"][0] == "Sharpe Ratio"
    for key in ("compiled_source_proven", "economics_accepted", "strategy_accepted", "canonical_admission",
        "full_window_accounting_verified", "current_project_source_proves_compiled_job_source", "uncertain_prior_dispatch_attributed",
        "retrospective_registration_is_preregistration", "owner_reported_mia_attribution_authenticated", "automatic_retry", "object_export", "trading"):
        assert result[key] is False
    assert result["accepted_metrics"] is None and number(result["new_codex_attempts"]) == number(result["new_looks"]) == 0
    assert number(result["codex_off_attempts_consumed"]) == 3 and number(result["observed_looks_after"]) == 33
    for path in values[2].iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        assert b"SYNTHETIC PRIVATE" not in path.read_bytes()
        assert TOKEN.encode() not in path.read_bytes()
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values, reading)
    assert len(calls) == 3


@pytest.mark.parametrize("fault", ["job", "root_project", "row_project", "snapshot", "compile", "bool_progress", "progress",
    "completed", "missing_error", "completed_error", "bad_date", "composite_date", "composite_project"])
def test_bad_native_bindings_are_private_retained_before_refusal_not_accepted(tmp_path, fault):
    values = fixture(tmp_path)
    def alter(index, value):
        row = value["backtest"]
        if index == 0:
            if fault == "job": row["backtestId"] = "f" * 32
            if fault == "root_project": value["projectId"] = 999
            if fault == "row_project": row["projectId"] = 999
            if fault == "snapshot": row["snapshotId"] = 1
            if fault == "compile": row["compileId"] = ""
            if fault == "bool_progress": row["progress"] = True
            if fault == "progress": row["progress"] = m.e.JsonNumber("1.1")
            if fault == "completed": row["completed"] = "true"
            if fault == "missing_error": row.pop("error")
            if fault == "completed_error": row["status"] = "Completed."
            if fault == "bad_date": row["endDate"] = "SYNTHETIC PRIVATE BAD DATE"
            if fault == "composite_date": row["endDate"] = []
            if fault == "composite_project": row["projectId"] = {}
        return m.e.canonical(value), 200, TOKEN
    reading, calls = transport(alter); result = execute(values, reading)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 3
    assert len(result["observations"]) == 2 and result["requests"][0]["projection"] is not None
    assert (values[2] / (values[0]["operation_id"] + ".result.json")).exists()


@pytest.mark.parametrize("credential", ["", None, 1, "a b", "a\n", "x" * 257])
def test_unusable_credential_rejected_before_any_projection(credential):
    with pytest.raises(ValueError): m._credential(credential)
    with pytest.raises(ValueError): m.project_terminal(b'{"success":true,"backtest":{}}', credential=credential)


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_echo_in_ignored_source_or_stats_is_never_retained(tmp_path, escaped):
    values = fixture(tmp_path)
    def alter(index, value):
        value["backtest"]["source"] = TOKEN
        raw = m.e.canonical(value)
        if escaped: raw = raw.replace(TOKEN.encode(), ("\\u0073" + TOKEN[1:]).encode())
        return raw, 200, TOKEN
    reading, calls = transport(alter); result = execute(values, reading)
    assert result["observations"] == [] and len(calls) == 3
    assert all(row["wire"] is not None and row["projection"] is None for row in result["requests"])
    assert all(TOKEN.encode() not in path.read_bytes() for path in values[2].iterdir())


@pytest.mark.parametrize("at", [0, 1, 2])
def test_keyboard_interrupt_stops_scope_before_any_later_request(tmp_path, at):
    values = fixture(tmp_path)
    def interrupt(index, value):
        if index == at: raise KeyboardInterrupt("SYNTHETIC PRIVATE CANCEL")
        return m.e.canonical(value), 200, TOKEN
    reading, calls = transport(interrupt); result = execute(values, reading)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["cancelled"] is True
    assert len(calls) == at + 1 and len(result["observations"]) == at
    assert not (values[2] / "controller.lock").exists()


@pytest.mark.parametrize("fault", ["http", "malformed", "duplicate", "oversize", "timeout", "node_bound"])
def test_failed_responses_keep_body_free_receipt_and_spent_requests(tmp_path, fault):
    values = fixture(tmp_path)
    def alter(index, value):
        if fault == "timeout": raise TimeoutError("SYNTHETIC PRIVATE TIMEOUT")
        if fault == "oversize": return b"x" * (m.MAX_RESPONSE + 1), 200, TOKEN
        if fault == "malformed": return b"SYNTHETIC PRIVATE MALFORMED", 200, TOKEN
        if fault == "duplicate": return b'{"success":true,"success":false,"backtest":{}}', 200, TOKEN
        if fault == "node_bound": value["ignored"] = [0] * 400001
        return m.e.canonical(value) if fault != "node_bound" else json.dumps(value, default=lambda v: int(v.fraction())).encode(), 503 if fault == "http" else 200, TOKEN
    reading, calls = transport(alter); result = execute(values, reading)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["observations"] == []
    assert 1 <= len(calls) <= 3 and result["accepted_metrics"] is None
    assert (values[2] / (values[0]["operation_id"] + ".result.json")).exists()
    assert not (values[2] / "controller.lock").exists()


def test_public_receipt_overflow_gets_body_free_failure_after_reads(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.observation
    def oversized(*args): return {**original(*args), "synthetic_padding": "x" * (m.MAX_RECEIPT + 1)}
    monkeypatch.setattr(m, "observation", oversized)
    reading, calls = transport(); result = execute(values, reading)
    assert len(calls) == 3 and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["public_receipt_overflow"] is True and result["observations"] is None and result["requests"] is None
    assert (values[2] / (values[0]["operation_id"] + ".result.json")).stat().st_size < m.MAX_RECEIPT


def test_discovery_identity_failure_stops_before_transport(tmp_path):
    values = fixture(tmp_path); values[0]["discovery_reference"]["sha256"] = "c" * 64
    reading, calls = transport(); result = execute(values, reading)
    assert calls == [] and result["status"] == "FAILED_OR_UNCERTAIN"


@pytest.mark.parametrize("kind", ["root", "native", "mode"])
def test_fixture_cannot_route_into_native_root_transport_or_production(tmp_path, kind):
    plan, sources, root = fixture(tmp_path); reading = transport()[0]
    if kind == "root": root = m.PRIVATE_ROOT
    if kind == "native": reading = m._native_request
    if kind == "mode": plan["mode"] = "production"
    with pytest.raises(ValueError): m.execute_fixture(plan, sources, root, clock=lambda: NOW, transport=reading)


@pytest.mark.parametrize("field", ["guard", "clock", "monotonic", "transport", "root"])
def test_production_identity_seams_refuse_before_private_effect(tmp_path, monkeypatch, field):
    monkeypatch.setattr(m, "_now", lambda: NOW)
    plan, sources, _ = fixture(tmp_path); plan["mode"] = "production"
    arguments = {"root": m.PRIVATE_ROOT, "guard": m._guard, "clock": m._now,
        "monotonic": m.time.monotonic, "transport": m._native_request}
    arguments[field] = tmp_path if field == "root" else (lambda *_a: NOW) if field == "clock" else lambda *_a: 0
    with pytest.raises(ValueError): m._execute(plan, sources, **arguments)


def test_plan_is_fixed_three_jobs_current_source_bound_and_dynamic_scope(tmp_path):
    plan, _, _ = fixture(tmp_path)
    assert len(m.SOURCE_PATHS) == len(set(m.SOURCE_PATHS)) and m._sha(SOURCES[m.parser_source.MODULE]) == m.PARSER_SHA256
    assert [row["snapshot_id"] for row in plan["jobs"]] == [37830348, 37832726, 37834838]
    assert plan["max_requests"] == 3 and plan["max_response_bytes"] == 4 * 1024 * 1024
    assert plan["max_received_bytes"] == 12 * 1024 * 1024 + 3 and plan["max_seconds"] == 120
    assert plan["oversize_refusal_bytes_reserved"] == 3 and plan["max_projection_parse_seconds"] == 10
    for mutation in ({"expires_utc": (NOW + timedelta(hours=1)).isoformat()}, {"mode": "native"},
        {"source_hashes": {}}, {"operation_id": "wrong"}):
        with pytest.raises(ValueError): m._plan(**{**{key: plan[key] for key in m.ARGS}, **mutation})
    with pytest.raises(ValueError): m._request(plan, {"projectId": m.PROJECT + 1, "backtestId": m.JOBS[0][0]})
    with pytest.raises(ValueError): m._request(plan, {"projectId": m.PROJECT, "backtestId": "f" * 32})


def test_all_three_oversize_refusal_bytes_are_prospectively_reserved(tmp_path):
    values = fixture(tmp_path)
    def oversized(index, value): return b"x" * (m.MAX_RESPONSE + 1), 200, TOKEN
    reading, calls = transport(oversized); result = execute(values, reading)
    assert len(calls) == 3 and number(result["received_bytes"]) == m.MAX_TOTAL == 12 * 1024 * 1024 + 3
    assert all(number(row["wire"]["bytes"]) > 0 and row["projection"] is None for row in result["requests"])


def test_request_reservation_requires_its_refusal_byte_before_transport(tmp_path, monkeypatch):
    # Synthetic smaller cap isolates pre-effect reservation from the later
    # accounting check; production's prospectively fixed bound is unchanged.
    monkeypatch.setattr(m, "MAX_TOTAL", m.MAX_TOTAL - 1)
    values = fixture(tmp_path)
    def oversized(index, value): return b"x" * (m.MAX_RESPONSE + 1), 200, TOKEN
    reading, calls = transport(oversized); result = execute(values, reading)
    assert len(calls) == 2 and number(result["request_attempts"]) == 2


def test_four_mib_parser_does_not_inherit_predecessors_two_mib_transport_bound():
    value = response(*m.JOBS[0][:2]); value["ignored"] = "x" * (2 * 1024 * 1024 + 16)
    projection = m.project_terminal(m.e.canonical(value), credential=TOKEN)
    assert m.observation(projection, *m.JOBS[0][:2])["native_status"] == "RuntimeError"


def test_projection_has_hard_ten_second_deadline_before_parser_execution(monkeypatch):
    from contextlib import contextmanager
    calls = []
    @contextmanager
    def deadline(seconds):
        calls.append(seconds)
        raise TimeoutError("synthetic projection timeout")
        yield
    monkeypatch.setattr(m.ops, "wall_deadline", deadline)
    with pytest.raises(TimeoutError): m.project_terminal(m.e.canonical(response(*m.JOBS[0][:2])), credential=TOKEN)
    assert calls == [10]


def test_shared_controller_lock_is_never_deleted_or_bypassed(tmp_path):
    values = fixture(tmp_path); path = values[2] / "controller.lock"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        reading, calls = transport(); result = execute(values, reading)
        assert calls == [] and result["status"] == "FAILED_OR_UNCERTAIN" and path.exists()
    finally: os.close(descriptor)


def test_native_request_rejects_forged_claim_before_any_credentials_or_private_read(tmp_path):
    plan, _, _ = fixture(tmp_path); plan["mode"] = "production"
    with pytest.raises(ValueError): m._native_request(plan, {"projectId": m.PROJECT, "backtestId": m.JOBS[0][0]}, 30,
        {"bytes": 1, "sha256": "a" * 64})


def test_scope_expiration_after_response_prevents_subsequent_reads(tmp_path):
    values = fixture(tmp_path); current = [NOW]
    def expired(index, value):
        current[0] = NOW + timedelta(hours=1)
        return m.e.canonical(value), 200, TOKEN
    reading, calls = transport(expired); result = execute(values, reading, clock=lambda: current[0])
    assert len(calls) == 1 and result["status"] == "FAILED_OR_UNCERTAIN" and result["observations"] == []


def test_nondict_statistics_value_is_not_misrepresented_as_a_statistic_key():
    value = response(*m.JOBS[0][:2]); value["backtest"]["statistics"] = "SYNTHETIC PRIVATE STATISTIC VALUE"
    projection = m.project_terminal(m.e.canonical(value), credential=TOKEN)
    assert projection["statistics_key_names"]["statistics"] == []
    assert projection["statistics_container_shapes"]["statistics"] is False
