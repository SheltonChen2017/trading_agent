"""Fixed-projection diagnostic fixtures; no real private body or external effects."""
from datetime import datetime, timedelta, timezone
import http.client
import os
from pathlib import Path
import subprocess

import pytest
from research.target_price_revisions_qc import extended_owner_mia_metadata_inspect as m

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError("actual private/API/credential/subprocess forbidden")
    monkeypatch.setattr(m.capture.ops, "credential", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    original = m.files._directory
    def safe(path, *, private):
        if private and path.is_relative_to(m.LANE): deny()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", safe)


def fixture(tmp_path, mutate=None):
    root = tmp_path / "synthetic-metadata"; root.mkdir(mode=0o700)
    value = {"success": True, "count": 1, "projectId": m.capture.PROJECT,
        "backtests": [{"backtestId": "synthetic-job", "created": "2026-10-13T22:00:00", "status": "Completed.",
            "progress": e.JsonNumber("1.000000000000000001"), "snapshotId": 123,
            "projectId": m.capture.PROJECT, "name_sha256": "c" * 64, "name_bytes": 12}],
        "error_count": 0, "errors_sha256": "d" * 64}
    value["backtests"][0]["progress"] = e.JsonNumber("1.000000000000000000")
    if mutate: mutate(value)
    outer = {"schema": "tpr-ext26-wire-projection-v1", "redaction_policy": "tpr-ext26-owner-discovery-contextual-metadata-v1",
        "original_wire_sha256": "e" * 64, "original_wire_bytes": 29881, "projection": value,
        "projection_sha256": m._sha(e.canonical(value)), "unexpected_outcome_or_parameter_fields_present": False,
        "raw_wire_retained": False, "outcome_parameter_source_fields_retained": False}
    raw = e.canonical(outer)
    directory = m.files._directory(root, private=True)
    try: m.capture._publish(directory, m.NAME, raw)
    finally: os.close(directory)
    plan = m._plan(git_head="a" * 40, source_hashes={name: m._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b" * 64, created_utc=(NOW - timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW + timedelta(minutes=10)).isoformat(), mode="offline-fixture",
        fixture_descriptor={"bytes": len(raw), "sha256": m._sha(raw)})
    return plan, dict(SOURCES), root


def execute(values, **kwargs):
    plan, sources, root = values
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), **kwargs))


def test_one_fixed_projection_naive_time_is_diagnostic_not_metadata_acceptance(tmp_path):
    values = fixture(tmp_path); result = execute(values)
    assert result["status"] == "COMPLETED_DIAGNOSTIC_INSPECTION"
    assert result["private_read_attempts"].fraction() == 1
    assert result["private_read_bytes"].fraction() == values[0]["descriptor"]["bytes"]
    facts = result["diagnostic"]
    assert facts["jobs"][0]["created_is_timezone_aware"] is False
    assert facts["jobs"][0]["progress"].lexeme == "1.000000000000000000"
    assert facts["discovery_metadata_accepted"] is False and facts["mia_attribution_verified"] is False
    assert facts["accepted_metrics"] is None and facts["raw_wire_independently_reopened"] is False
    assert result["api_requests"].fraction() == result["new_jobs"].fraction() == result["new_codex_attempts"].fraction() == 0
    with pytest.raises(FileExistsError): execute(values)
    assert not (values[2] / "controller.lock").exists()


@pytest.mark.parametrize("field", ["statistics", "source", "profile", "parameters"])
def test_rebound_valid_hash_still_refuses_nonmetadata_fields(tmp_path, field):
    values = fixture(tmp_path, lambda value: value["backtests"][0].update({field: "SYNTHETIC PRIVATE BODY"}))
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["diagnostic"] is None
    assert "SYNTHETIC PRIVATE BODY" not in e.canonical(result).decode()


def test_missing_count_exposes_schema_fact_not_zero_or_acceptance(tmp_path):
    result = execute(fixture(tmp_path, lambda value: value.pop("count")))
    assert result["diagnostic"]["count"] is None and result["diagnostic"]["count_field_present"] is False
    assert result["diagnostic"]["returned_rows"].fraction() == 1


@pytest.mark.parametrize("created", ["not-a-timestamp", "SYNTHETIC PRIVATE DATE", None])
def test_invalid_created_field_is_hash_type_diagnostic_not_raw_text(tmp_path, created):
    result = execute(fixture(tmp_path, lambda value: value["backtests"][0].update(created=created)))
    facts = result["diagnostic"]["jobs"][0]
    assert result["status"] == "COMPLETED_DIAGNOSTIC_INSPECTION"
    assert facts["created"] is None and facts["created_parseable"] is False and facts["created_is_timezone_aware"] is False
    if type(created) is str:
        assert facts["created_sha256"] == m._sha(created.encode())
        assert created not in e.canonical(result).decode()


@pytest.mark.parametrize("progress", [e.JsonNumber("1.000000000000000001"), e.JsonNumber("-0.1"), True])
def test_invalid_progress_shape_or_bounds_stays_exact_diagnostic_not_signal(tmp_path, progress):
    result = execute(fixture(tmp_path, lambda value: value["backtests"][0].update(progress=progress)))
    facts = result["diagnostic"]["jobs"][0]
    assert result["status"] == "COMPLETED_DIAGNOSTIC_INSPECTION" and facts["progress_within_unit_bounds"] is False
    if type(progress) is e.JsonNumber: assert facts["progress"].lexeme == progress.lexeme
    else: assert facts["progress"] is None and facts["progress_field_type"] == "boolean"


@pytest.mark.parametrize("fault", ["hash", "size", "symlink", "foreign_project", "foreign_row_project"])
def test_exact_fd_custody_and_project_refusals_preserve_spent_failure(tmp_path, fault):
    def changed(value):
        if fault == "foreign_project": value["projectId"] = 999
        if fault == "foreign_row_project": value["backtests"][0]["projectId"] = 999
    values = fixture(tmp_path, changed)
    if fault == "hash": values[0]["descriptor"]["sha256"] = "f" * 64; values[0]["fixture_descriptor"]["sha256"] = "f" * 64
    if fault == "size": values[0]["descriptor"]["bytes"] += 1; values[0]["fixture_descriptor"]["bytes"] += 1
    if fault == "symlink":
        (values[2] / m.NAME).rename(values[2] / "preserved")
        (values[2] / m.NAME).symlink_to(values[2] / "preserved")
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["diagnostic"] is None
    assert (values[2] / (m.OPERATION + ".claim.spent.json")).exists()


def test_claim_access_are_durable_before_the_only_private_read(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.files._read; calls = []
    def read(directory, name, **kwargs):
        assert name == m.NAME
        assert all((values[2] / (m.OPERATION + suffix)).exists() for suffix in (".claim.spent.json", ".access.json"))
        calls.append(name); return original(directory, name, **kwargs)
    monkeypatch.setattr(m.files, "_read", read)
    assert execute(values)["status"] == "COMPLETED_DIAGNOSTIC_INSPECTION" and calls == [m.NAME]


@pytest.mark.parametrize("fault", ["expired", "naive", "offset", "source", "extra", "long_scope"])
def test_plan_identity_clock_and_scope_refuse_before_claim(tmp_path, fault):
    values = fixture(tmp_path); clock = lambda: NOW
    if fault == "expired": clock = lambda: NOW + timedelta(hours=1)
    if fault == "naive": clock = lambda: NOW.replace(tzinfo=None)
    if fault == "offset": clock = lambda: NOW.astimezone(timezone(timedelta(hours=5)))
    if fault == "source": values[1][m.MODULE] += b" "
    if fault == "extra": values[0]["new_authority"] = True
    if fault == "long_scope": values[0]["expires_utc"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError): execute(values, clock=clock)
    assert not (values[2] / (m.OPERATION + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic", "descriptor"])
def test_production_has_no_fixture_path_clock_or_descriptor_seam(tmp_path, monkeypatch, fault):
    fixture_plan, sources, root = fixture(tmp_path)
    args = {name: fixture_plan[name] for name in m.ARGS}; args.update(mode="production", fixture_descriptor=None)
    if fault == "descriptor":
        args["fixture_descriptor"] = fixture_plan["fixture_descriptor"]
        with pytest.raises(ValueError): m._plan(**args)
        return
    plan = m._plan(**args)
    assert plan["name"] == m.NAME and plan["descriptor"] == {"bytes": 4138, "sha256": m.SHA256}
    # Keep the clock valid so an injected guard cannot hide behind expiry.
    monkeypatch.setattr(m, "_now", lambda: NOW)
    kwargs = {"guard": m._guard, "clock": m._now, "monotonic": m.time.monotonic}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_: None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


@pytest.mark.parametrize("root", [m.PRIVATE_ROOT, m.LANE / "synthetic-never-created"])
def test_fixture_cannot_open_actual_lane_or_private_root(tmp_path, root):
    plan, sources, _ = fixture(tmp_path)
    with pytest.raises(ValueError): m.execute_fixture(plan, sources, root, clock=lambda: NOW)


def test_final_check_refusal_is_anchored_after_completed_diagnostic(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m._inspect; reached = []
    def inspected(raw):
        result = original(raw); reached.append(True); return result
    monkeypatch.setattr(m, "_inspect", inspected)
    def guard(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values, guard=guard)
    assert reached and result["diagnostic"] is not None
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["private_read_attempts"].fraction() == 1


def test_cli_hash_refusal_has_no_execution_or_body_output(monkeypatch, capsys):
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("wrong hash cannot execute"))
    assert m.main(["--plan-json", "{}", "--plan-sha256", "a" * 64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["status"] == "REFUSED_OR_UNCERTAIN"
