"""Synthetic metadata discovery only; no actual account/API/private/operator root."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_owner_mia_discovery as m

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 22, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError("actual credential/network/private/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    original = m.files._directory
    def directory(path, *, private):
        if private and path.is_relative_to(m.LANE): denied()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", directory)


def fixture(tmp_path):
    root = tmp_path / "synthetic-owner-mia-discovery"; root.mkdir(mode=0o700)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-MIA-DISCOVERY-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(raw) for name, raw in SOURCES.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(), expires_utc=(NOW + timedelta(minutes=30)).isoformat(), mode="offline-fixture")
    return plan, deepcopy(SOURCES), root


def row(identity="synthetic-new-job", created="2026-10-13T21:00:00Z", status="Completed."):
    return {"backtestId": identity, "created": created, "status": status, "progress": 1,
        "snapshotId": 123, "name": "SYNTHETIC PRIVATE JOB NAME", "projectId": m.PROJECT}


def transport(rows=None, *, fault=None, status=200):
    calls = []
    def read(plan, seconds, claim):
        assert plan["endpoint"] == "backtests/list" and plan["payload"] == {"projectId": 37650980, "includeStatistics": False}
        assert 0 < seconds <= 30
        calls.append(deepcopy(plan["payload"]))
        jobs = deepcopy([row()] if rows is None else rows)
        body = {"success": True, "projectId": m.PROJECT, "count": len(jobs), "backtests": jobs, "errors": []}
        if fault: fault(body)
        return e.canonical(body), status, "SYNTHETIC-TOKEN"
    return read, calls


def execute(values, reading=None, **kwargs):
    plan, sources, root = values
    if reading is None: reading = transport()[0]
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW),
        transport=reading, **kwargs))


def test_single_documented_list_request_keeps_failed_unknown_and_known_jobs_chronologically(tmp_path):
    known = "e3324aef9bd2af2caf16a32468eeb101"
    jobs = [row("synthetic-new-success", "2026-10-13T21:20:00Z"),
        row(known, "2026-10-12T06:55:00Z", "Runtime Error"),
        row("synthetic-new-failure", "2026-10-13T21:10:00Z", "Runtime Error")]
    values = fixture(tmp_path); read, calls = transport(jobs); result = execute(values, read)
    assert result["status"] == "COMPLETED_METADATA" and len(calls) == 1
    assert [item["backtest_id"] for item in result["jobs"]] == [known, "synthetic-new-failure", "synthetic-new-success"]
    assert result["unknown_job_ids"] == ["synthetic-new-failure", "synthetic-new-success"]
    assert result["jobs"][0]["known_historical_job"] is True
    assert result["winner_selected"] is False and result["compiled_source_proven"] is False
    assert all(item["owner_reported_mia_attribution_verified"] is False for item in result["jobs"])
    assert result["previously_recorded_looks"].fraction() == 20
    assert result["look_registry_updates_performed"].fraction() == result["new_jobs_launched"].fraction() == 0
    assert result["codex_off_attempts_consumed"].fraction() == 3 and result["accepted_metrics"] is None
    assert "SYNTHETIC PRIVATE JOB NAME" not in e.canonical(result).decode()
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values, read)
    assert len(calls) == 1


def test_exact_numeric_tokens_survive_without_statistics_parameters_or_profile_contents(tmp_path):
    def fault(body):
        body["backtests"][0].update(progress=e.JsonNumber("1.000000000000000000000"),
            userId=12345, ownerId="SYNTHETIC OWNER", profileImage="SYNTHETIC IMAGE",
            statistics={"Return": "SYNTHETIC OUTCOME"}, parameterSet={"private": "SYNTHETIC PARAMETER"},
            source="SYNTHETIC SOURCE BODY", account={"id": "SYNTHETIC ACCOUNT", "email": "synthetic@example.invalid"})
    values = fixture(tmp_path); result = execute(values, transport(fault=fault)[0])
    assert result["status"] == "COMPLETED_METADATA"
    assert result["jobs"][0]["progress"].lexeme == "1.000000000000000000000"
    raw = (values[2] / (values[0]["operation_id"] + ".read001.projection.json")).read_bytes()
    assert all(marker not in raw for marker in (b"12345", b"SYNTHETIC OWNER", b"SYNTHETIC IMAGE", b"SYNTHETIC OUTCOME",
        b"SYNTHETIC PARAMETER", b"SYNTHETIC SOURCE BODY", b"SYNTHETIC ACCOUNT", b"synthetic@example.invalid"))
    projected = e.parse_json(raw)
    assert projected["projection"]["backtests"][0]["progress"].lexeme == "1.000000000000000000000"
    assert projected["outcome_parameter_source_fields_retained"] is False and projected["raw_wire_retained"] is False
    assert result["unexpected_outcome_or_parameter_fields_present"] is True


def test_contextual_profile_scrub_never_replaces_digits_or_job_order_identity():
    value = {"backtests": [{"backtestId": "12345-job", "progress": e.JsonNumber("0.12345"), "userId": 12345}],
        "account": {"id": 12345, "name": "SYNTHETIC PERSON"}, "orders": [{"id": 12345, "quantity": e.JsonNumber("12345")}]}
    scrubbed = m._contextual_redact(value)
    assert scrubbed["backtests"][0]["userId"] == "[redacted]" and scrubbed["account"]["id"] == "[redacted]"
    assert scrubbed["backtests"][0]["backtestId"] == "12345-job"
    assert scrubbed["backtests"][0]["progress"].lexeme == "0.12345"
    assert scrubbed["orders"][0]["id"] == 12345 and scrubbed["orders"][0]["quantity"].lexeme == "12345"
    assert value["account"]["id"] == 12345


@pytest.mark.parametrize("count", [0, 128])
def test_closed_row_boundary_accepts_all_rows_without_outcome_selection(tmp_path, count):
    jobs = [row("synthetic-job-" + str(number)) for number in range(count)]
    result = execute(fixture(tmp_path), transport(jobs)[0])
    assert result["status"] == "COMPLETED_METADATA" and len(result["jobs"]) == count


@pytest.mark.parametrize("fault", ["129_rows", "count_mismatch", "duplicate", "foreign_project", "foreign_row_project",
    "missing_id", "missing_created", "naive_created", "bad_created", "bool_progress", "bad_progress", "bool_snapshot",
    "negative_snapshot", "bad_status", "false_success", "not_list", "not_row", "long_name"])
def test_bad_or_unbounded_metadata_retains_failure_without_a_second_request(tmp_path, fault):
    def alter(body):
        item = body["backtests"][0]
        if fault == "129_rows": body.update(count=129, backtests=[row("synthetic-" + str(number)) for number in range(129)])
        elif fault == "count_mismatch": body["count"] = 2
        elif fault == "duplicate": body.update(count=2, backtests=[item, deepcopy(item)])
        elif fault == "foreign_project": body["projectId"] = 999
        elif fault == "foreign_row_project": item["projectId"] = 999
        elif fault == "missing_id": item.pop("backtestId")
        elif fault == "missing_created": item.pop("created")
        elif fault == "naive_created": item["created"] = "2026-10-13T21:00:00"
        elif fault == "bad_created": item["created"] = "invalid"
        elif fault == "bool_progress": item["progress"] = True
        elif fault == "bad_progress": item["progress"] = e.JsonNumber("1.0001")
        elif fault == "bool_snapshot": item["snapshotId"] = True
        elif fault == "negative_snapshot": item["snapshotId"] = -1
        elif fault == "bad_status": item["status"] = "x" * 81
        elif fault == "false_success": body["success"] = False
        elif fault == "not_list": body["backtests"] = None
        elif fault == "not_row": body["backtests"] = ["not a row"]
        elif fault == "long_name": item["name"] = "x" * 1025
    values = fixture(tmp_path); read, calls = transport(fault=alter); result = execute(values, read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1 and result["jobs"] is None
    assert result["accepted_metrics"] is None and (values[2] / (values[0]["operation_id"] + ".result.json")).exists()


def test_unknown_status_is_hashed_private_and_publicly_diagnostic_not_completed(tmp_path):
    result = execute(fixture(tmp_path), transport([row(status="SYNTHETIC UNRECOGNIZED STATUS")])[0])
    assert result["status"] == "COMPLETED_METADATA" and result["jobs"][0]["status"] == "unrecognized_status"
    assert "SYNTHETIC UNRECOGNIZED STATUS" not in e.canonical(result).decode()


def test_offset_chronology_and_identity_tiebreak_do_not_select_a_winner(tmp_path):
    jobs = [row("synthetic-b", "2026-10-13T22:00:00+01:00", "Runtime Error"), row("synthetic-a", "2026-10-13T21:00:00Z")]
    result = execute(fixture(tmp_path), transport(jobs)[0])
    assert [item["backtest_id"] for item in result["jobs"]] == ["synthetic-a", "synthetic-b"]
    assert result["jobs"][1]["created"] == "2026-10-13T22:00:00+01:00"


def test_absent_returned_project_fields_remain_request_scope_not_provider_identity(tmp_path):
    def omit(body):
        body.pop("projectId")
        for item in body["backtests"]: item.pop("projectId")
    result = execute(fixture(tmp_path), transport(fault=omit)[0])
    assert result["status"] == "COMPLETED_METADATA" and result["observed_returned_project_fields"].fraction() == 0
    assert result["request_bound_to_fixed_project"] is True and result["provider_authenticity_attested"] is False


def test_unrequested_top_level_outcome_fields_are_flagged_before_discarding_values(tmp_path):
    def extra(body): body["statistics"] = {"private": "SYNTHETIC UNREQUESTED OUTCOME"}
    values = fixture(tmp_path); result = execute(values, transport(fault=extra)[0])
    assert result["unexpected_outcome_or_parameter_fields_present"] is True
    raw = (values[2] / (values[0]["operation_id"] + ".read001.projection.json")).read_bytes()
    assert b"SYNTHETIC UNREQUESTED OUTCOME" not in raw


def test_refused_final_check_after_metadata_does_not_claim_completed_scope(tmp_path, monkeypatch):
    (tmp_path / "first").mkdir(); (tmp_path / "second").mkdir()
    happy = execute(fixture(tmp_path / "first"))
    assert happy["status"] == "COMPLETED_METADATA"
    reached = []
    original = m._metadata
    def metadata_then_mark(*args):
        result = original(*args)
        reached.append(True)
        return result
    monkeypatch.setattr(m, "_metadata", metadata_then_mark)
    def refuse_at_last(_):
        if reached: raise ValueError("SYNTHETIC FINAL REFUSAL")
    values = fixture(tmp_path / "second"); read, calls = transport(); result = execute(values, read, guard=refuse_at_last)
    assert len(calls) == 1 and reached == [True]
    assert result["jobs"] is not None and result["unknown_job_ids"] == ["synthetic-new-job"]
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["request"]["status"] == "failed_or_unknown"
    assert (values[2] / (values[0]["operation_id"] + ".result.json")).exists()


@pytest.mark.parametrize("fault", ["timeout", "http", "oversize", "malformed", "echo", "escaped_echo", "expired_after_read"])
def test_failed_response_scope_remains_spent_with_safe_uncertainty(tmp_path, fault):
    values = fixture(tmp_path); read, calls = transport(status=503 if fault == "http" else 200); elapsed = [0.0]
    def reading(*args):
        if fault == "timeout": calls.append(True); raise TimeoutError("SYNTHETIC PRIVATE FAILURE")
        raw, status, token = read(*args)
        if fault == "oversize": raw = b"x" * (m.MAX_RESPONSE + 1)
        if fault == "malformed": raw = b"{"
        if fault == "echo": raw = raw.replace(b'"errors":[]', b'"errors":["SYNTHETIC-TOKEN"]')
        if fault == "escaped_echo": raw = raw.replace(b'"errors":[]', b'"errors":["SYNTHETIC-\\u0054OKEN"]')
        if fault == "expired_after_read": elapsed[0] = 30
        return raw, status, token
    result = execute(values, reading, monotonic=lambda: elapsed[0])
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["failed_response_bytes_unknown"] is (fault == "timeout")
    if fault in {"echo", "escaped_echo", "malformed", "oversize"}: assert result["request"]["wire_sha256"] is None
    assert "SYNTHETIC-TOKEN" not in e.canonical(result).decode() and "SYNTHETIC PRIVATE FAILURE" not in e.canonical(result).decode()
    with pytest.raises(FileExistsError): execute(values, reading)
    assert len(calls) == 1


def test_claim_access_request_and_shared_lock_are_durable_before_transport(tmp_path):
    values = fixture(tmp_path); read, calls = transport()
    def reading(*args):
        root, operation = values[2], values[0]["operation_id"]
        for suffix in (".claim.spent.json", ".access.json", ".read001.request.spent.json"):
            raw = (root / (operation + suffix)).read_bytes()
            assert raw and (root / (operation + suffix)).stat().st_mode & 0o777 == 0o600
        assert (root / "controller.lock").exists()
        return read(*args)
    assert execute(values, reading)["status"] == "COMPLETED_METADATA" and len(calls) == 1


def test_existing_controller_is_preserved_and_scope_spent_without_network(tmp_path):
    values = fixture(tmp_path); root = values[2]
    fd = os.open(root / "controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try: os.write(fd, b"synthetic other owner")
    finally: os.close(fd)
    read, calls = transport(); result = execute(values, read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and not calls
    assert (root / "controller.lock").read_bytes() == b"synthetic other owner"
    assert (root / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["expired", "naive", "offset", "source", "freeze", "calendar", "look", "extra_field", "payload", "row_bound"])
def test_scope_and_frozen_identity_refusals_precede_claims_or_transport(tmp_path, fault):
    values = list(fixture(tmp_path)); read, calls = transport(); clock = lambda: NOW
    if fault == "expired": clock = lambda: NOW + timedelta(hours=2)
    if fault == "naive": clock = lambda: NOW.replace(tzinfo=None)
    if fault == "offset": clock = lambda: NOW.astimezone(timezone(timedelta(hours=5)))
    if fault in {"source", "freeze", "calendar", "look"}:
        target = {"source": m.MODULE, "freeze": m.capture.PREFIX + "extended_study_freeze.json",
            "calendar": m.capture.PREFIX + "extended_calendar.json", "look": m.LOOK}[fault]
        values[1][target] += b" "
    if fault == "extra_field": values[0]["launch_authorized"] = True
    if fault == "payload": values[0]["payload"]["includeStatistics"] = True
    if fault == "row_bound": values[0]["max_rows"] = 129
    with pytest.raises((ValueError, KeyError)): execute(values, read, clock=clock)
    assert not calls and not (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic", "transport"])
def test_production_rejects_injected_seams_before_private_open(tmp_path, monkeypatch, fault):
    plan, sources, root = fixture(tmp_path); plan["mode"] = "production"
    # Keep the clock valid so an injected guard cannot hide behind expiry.
    monkeypatch.setattr(m, "_production_clock", lambda: NOW)
    kwargs = {"guard": m._guard, "clock": m._production_clock, "monotonic": m.time.monotonic, "transport": m._native_request}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_: None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


@pytest.mark.parametrize("root", [m.PRIVATE_ROOT, m.LANE / "synthetic-never-created"])
def test_fixture_never_opens_lane_or_actual_private_root(tmp_path, root):
    plan, sources, _ = fixture(tmp_path); read, calls = transport()
    with pytest.raises(ValueError): m.execute_fixture(plan, sources, root, clock=lambda: NOW, transport=read)
    assert not calls


def test_native_signer_refuses_missing_exact_request_claim_before_credentials(tmp_path):
    plan = fixture(tmp_path)[0]; plan["mode"] = "production"
    with pytest.raises(ValueError): m._native_request(plan, 30, None)


def test_cli_exact_parsed_plan_keeps_body_free_stdout_and_no_production_seam(tmp_path, monkeypatch, capsys):
    values = fixture(tmp_path); raw = e.canonical(values[0]); read, calls = transport()
    def fixture_only(plan):
        assert plan["mode"] == "offline-fixture"
        return m.execute_fixture(plan, values[1], values[2], clock=lambda: NOW, transport=read)
    monkeypatch.setattr(m, "execute_plan", fixture_only)
    assert m.main(["--plan-json", raw.decode(), "--plan-sha256", m._sha(raw)]) == 0
    output = capsys.readouterr().out
    assert e.parse_json(output.encode())["status"] == "COMPLETED_METADATA" and len(calls) == 1
    assert all(marker not in output for marker in ("SYNTHETIC PRIVATE JOB NAME", "permitted_repair_source", '"statistics":', "parameterSet", "profileImage"))


def test_cli_hash_refusal_is_sanitized_before_any_execution(monkeypatch, capsys):
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("no execution on wrong hash"))
    assert m.main(["--plan-json", "{}", "--plan-sha256", "a" * 64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["status"] == "REFUSED_OR_UNCERTAIN"


def test_expiry_duration_operation_and_closure_never_grant_other_routes(tmp_path):
    plan = fixture(tmp_path)[0]
    for key, bad in (("operation_id", "TPR-EXT26-MIA-RECOVERY-SYNTHETIC-001"), ("expires_utc", (NOW + timedelta(hours=2)).isoformat())):
        args = {name: plan[name] for name in m.ARGS}; args[key] = bad
        with pytest.raises(ValueError): m._plan(**args)
    assert m.ENDPOINT == "backtests/list" and m.PAYLOAD == {"projectId": 37650980, "includeStatistics": False}
    assert m._frozen(SOURCES) == m.PRIOR_JOBS | {"e3324aef9bd2af2caf16a32468eeb101"}
