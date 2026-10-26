"""Two synthetic source artifacts; actual private/account/operator I/O denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_owner_mia_source_inspect as m

e, c = m.e, m.capture
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
FROZEN = next(row["files"] for row in e.parse_json(SOURCES[c.BUNDLE])["candidates"] if row["candidate_id"] == m.CANDIDATE)
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)
NOTEBOOK = '{"cells":[]}\n'
HELPER = '"""Synthetic safe static helper, never executed."""\n\ndef repair(value):\n    return value\n'


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError("actual credential/network/private/subprocess forbidden")
    monkeypatch.setattr(c.ops, "credential", denied)
    monkeypatch.setattr(c.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    monkeypatch.setattr(m, "NOTEBOOK_SHA256", m._sha(NOTEBOOK.encode()))
    original = m.files._directory
    def directory(path, *, private):
        if private and path.is_relative_to(m.LANE): denied()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", directory)


def publish(root, name, raw):
    directory = m.files._directory(root, private=True)
    try: c._publish(directory, name, raw)
    finally: os.close(directory)


def fixture(tmp_path, *, source_mutate=None, delta_mutate=None, archive_mutate=None):
    root = tmp_path / "synthetic-owner-source-inspection"; root.mkdir(mode=0o700)
    before = {**FROZEN, "research.ipynb": NOTEBOOK}
    current = {**before, "audit_key_recovery.py": HELPER, "weight_repair.py": HELPER,
        "clock_repair.py": HELPER, "evidence_repair.py": HELPER}
    current["main.py"] += "\n# Synthetic owner-origin source change.\n"
    if source_mutate: source_mutate(before, current)
    _, delta_raw = c._diff(before, current)
    if delta_mutate:
        delta = e.parse_json(delta_raw); delta_mutate(delta); delta_raw = e.canonical(delta)
    archive_raw = c._archive(m.CAPTURE_OPERATION, 2, current)
    if archive_mutate:
        archive = e.parse_json(archive_raw); archive_mutate(archive); archive_raw = e.canonical(archive)
    descriptors = {}
    for role, suffix, raw in (("archive", ".read2.sources.json", archive_raw), ("diff", ".diff.json", delta_raw)):
        descriptors[role] = {"bytes": len(raw), "sha256": m._sha(raw)}
        publish(root, m.CAPTURE_OPERATION + suffix, raw)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-MIA-SOURCE-INSPECT-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(raw) for name, raw in SOURCES.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(), expires_utc=(NOW + timedelta(minutes=30)).isoformat(),
        mode="offline-fixture", **descriptors)
    return plan, deepcopy(SOURCES), root


def execute(values, **kwargs):
    plan, sources, root = values
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), **kwargs))


def test_complete_all_file_delta_and_four_added_helpers_static_disclosure_only(tmp_path):
    values = fixture(tmp_path); result = execute(values)
    assert result["status"] == "COMPLETED_SOURCE_INSPECTION"
    assert result["private_read_attempts"].fraction() == 2
    assert result["private_read_bytes"].fraction() == values[0]["archive"]["bytes"] + values[0]["diff"]["bytes"]
    inspected = result["inspection"]
    assert len(inspected["all_current_file_identities"]) == 15
    assert len(inspected["all_changed_file_metadata"]) == len(inspected["disclosures"]) == 5
    assert {row["name"] for row in inspected["disclosures"]} == {"main.py", "audit_key_recovery.py", "weight_repair.py", "clock_repair.py", "evidence_repair.py"}
    assert inspected["before_matches_public_immutable_bundle"] is True and inspected["all_changes_recomputed"] is True
    assert all(row["static_python_text"] == HELPER for row in inspected["disclosures"] if row["kind"] == "added")
    assert all(row["name"] != "research.ipynb" for row in inspected["disclosures"])
    assert result["compiled_source_proven"] is False and result["network_requests"].fraction() == 0
    assert inspected["general_secret_or_covert_data_absence_proven"] is False and inspected["economics_accepted"] is False
    assert result["new_jobs_launched"].fraction() == result["new_codex_attempts"].fraction() == 0
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values)


def test_removed_module_and_changed_notebook_are_accounted_without_notebook_body(tmp_path):
    def alter(_before, current):
        current.pop("extended_config.py")
        current["research.ipynb"] = '{"cells":["SYNTHETIC NOTEBOOK PRIVATE CONTENT"]}\n'
    result = execute(fixture(tmp_path, source_mutate=alter))
    assert result["status"] == "COMPLETED_SOURCE_INSPECTION"
    rows = result["inspection"]["disclosures"]
    assert next(row for row in rows if row["name"] == "extended_config.py")["kind"] == "removed"
    assert next(row for row in rows if row["name"] == "research.ipynb")["body_disclosed"] is False
    assert "SYNTHETIC NOTEBOOK PRIVATE CONTENT" not in e.canonical(result).decode()


@pytest.mark.parametrize("fault", ["project", "operation", "request_index", "schema", "extra"])
def test_foreign_or_wrong_archive_schema_is_never_disclosed(tmp_path, fault):
    def mutate(archive):
        if fault == "project": archive["project_id"] = 999
        if fault == "operation": archive["operation_id"] = "TPR-EXT26-MIA-SOURCE-POST-FOREIGN"
        if fault == "request_index": archive["request_index"] = 1
        if fault == "schema": archive["schema"] = "foreign"
        if fault == "extra": archive["source_executed"] = True
    result = execute(fixture(tmp_path, archive_mutate=mutate))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None


@pytest.mark.parametrize("fault", ["before_hash", "after_hash", "after_text", "duplicate", "omit", "kind", "extra", "executed", "economics"])
def test_every_whole_file_before_after_identity_and_complete_delta_are_checked(tmp_path, fault):
    def mutate(delta):
        row = next(row for row in delta["changes"] if row["name"] == "main.py")
        if fault == "before_hash": row["before_identity"]["sha256"] = "f" * 64
        if fault == "after_hash": row["after_identity"]["sha256"] = "f" * 64
        if fault == "after_text": row["after"] += "# not captured"
        if fault == "duplicate": delta["changes"].append(deepcopy(next(item for item in delta["changes"] if item["kind"] == "added")))
        if fault == "omit": delta["changes"].remove(row)
        if fault == "kind": row["kind"] = "arbitrary"
        if fault == "extra": row["accepted"] = True
        if fault == "executed": delta["source_executed"] = True
        if fault == "economics": delta["economics_accepted"] = True
    result = execute(fixture(tmp_path, delta_mutate=mutate))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None


def test_consistent_changed_baseline_still_refuses_public_immutable_bundle_drift(tmp_path):
    def mutate(before, current):
        before["extended_core.py"] += "# altered baseline"
        current["extended_core.py"] = before["extended_core.py"]
    result = execute(fixture(tmp_path, source_mutate=mutate))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None


@pytest.mark.parametrize("body", [
    "API_KEY = 'SYNTHETIC_PRIVATE_SECRET'\n", "ACCOUNT_ID = 12345\n",
    "PRIVATE = '-----BEGIN PRIVATE KEY----- SYNTHETIC'\n",
    "CONTACT = 'synthetic@example.invalid'\n", "ROWS = [{'ticker':'SYNTHETIC','price':'123.45'}]\n",
    "ROWS = [('SYNTHETIC', '123.45')]\n", "HEADERS = {'Authorization':'SYNTHETIC_SECRET_VALUE'}\n",
    "HEADERS = {'api_token':'short-private-token'}\n",
    "CONST = '" + "a" * 64 + "'\n", "CONST = '" + "x " * 600 + "'\n",
    "# API_KEY=SYNTHETIC_PRIVATE_SECRET\n", "class invalid(:\n",
])
def test_explicit_secret_and_literal_market_rows_are_refused_before_any_source_disclosure(tmp_path, body):
    def mutate(_before, current): current["weight_repair.py"] = body
    result = execute(fixture(tmp_path, source_mutate=mutate))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None
    assert "SYNTHETIC_PRIVATE_SECRET" not in e.canonical(result).decode()


def test_public_config_hash_and_long_dictionary_field_key_not_arbitrary_value_are_disclosable(tmp_path):
    config = next(row["config_raw"] for row in e.parse_json(SOURCES[c.BUNDLE])["candidates"] if row["candidate_id"] == m.CANDIDATE)
    def mutate(_before, current):
        current["weight_repair.py"] = "CONFIG_HASH = '" + m._sha(config.encode()) + "'\n" + "FIELDS = {'source_current_equals_job_compiled_unknown_flag': False}\n"
    result = execute(fixture(tmp_path, source_mutate=mutate))
    assert result["status"] == "COMPLETED_SOURCE_INSPECTION"
    body = next(row["static_python_text"] for row in result["inspection"]["disclosures"] if row["name"] == "weight_repair.py")
    assert m._sha(config.encode()) in body and "source_current_equals_job_compiled_unknown_flag" in body
    with pytest.raises(ValueError): m._safe_source("", "VALUE = 'source_current_equals_job_compiled_unknown_flag'\n", set())


@pytest.mark.parametrize("fault", ["hash", "size", "symlink", "controller", "expiry", "source"])
def test_fixed_fd_custody_expiry_and_source_scope_preserve_failed_claims(tmp_path, fault):
    values = list(fixture(tmp_path)); plan, sources, root = values
    if fault == "hash": plan["archive"]["sha256"] = "f" * 64
    if fault == "size": plan["archive"]["bytes"] += 1
    if fault == "source": sources[m.MODULE] += b" "
    if fault == "symlink":
        name = m.CAPTURE_OPERATION + ".read2.sources.json"
        (root / name).rename(root / "synthetic-preserved")
        (root / name).symlink_to(root / "synthetic-preserved")
    if fault == "controller": publish(root, "controller.lock", b"preserve")
    if fault in {"expiry", "source"}:
        with pytest.raises(ValueError): execute(values, clock=(lambda: NOW + timedelta(hours=2)) if fault == "expiry" else lambda: NOW)
        assert not (root / (plan["operation_id"] + ".claim.spent.json")).exists()
    else:
        result = execute(values)
        assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None
        assert (root / (plan["operation_id"] + ".claim.spent.json")).exists()
        if fault == "controller": assert (root / "controller.lock").read_bytes() == b"preserve"


def test_exclusive_scope_access_and_each_body_claim_precede_synthetic_fd_read(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.files._read; observed = []
    def read(directory, name, **kwargs):
        operation, root = values[0]["operation_id"], values[2]
        role = "archive" if name.endswith(".read2.sources.json") else "diff"
        assert all((root / (operation + suffix)).exists() for suffix in
            (".claim.spent.json", ".access.json", "." + role + ".read.spent.json"))
        assert (root / "controller.lock").exists()
        observed.append(name)
        return original(directory, name, **kwargs)
    monkeypatch.setattr(m.files, "_read", read)
    assert execute(values)["status"] == "COMPLETED_SOURCE_INSPECTION" and len(observed) == 2


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic"])
def test_production_has_no_injected_seams_and_exact_real_descriptors(tmp_path, monkeypatch, fault):
    plan, sources, root = fixture(tmp_path)
    plan["mode"] = "production"; plan["archive"] = dict(m.ARCHIVE); plan["diff"] = dict(m.DIFF)
    plan = m._plan(**{key: plan[key] for key in m.ARGS})
    # Keep the clock valid so an injected guard cannot hide behind expiry.
    monkeypatch.setattr(m, "_now", lambda: NOW)
    kwargs = {"guard": m._guard, "clock": m._now, "monotonic": m.time.monotonic}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_: None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


@pytest.mark.parametrize("root", [m.PRIVATE_ROOT, m.LANE / "synthetic-never-created"])
def test_fixture_never_opens_actual_lane_or_private_directory(tmp_path, root):
    plan, sources, _ = fixture(tmp_path)
    with pytest.raises(ValueError): m.execute_fixture(plan, sources, root, clock=lambda: NOW)


def test_actual_cli_parsed_numbers_normalize_without_widening_scope(tmp_path, monkeypatch, capsys):
    values = fixture(tmp_path); raw = e.canonical(values[0])
    def fixture_only(plan):
        assert type(plan["archive"]["bytes"]) is e.JsonNumber and plan["mode"] == "offline-fixture"
        return m.execute_fixture(plan, values[1], values[2], clock=lambda: NOW)
    monkeypatch.setattr(m, "execute_plan", fixture_only)
    assert m.main(["--plan-json", raw.decode(), "--plan-sha256", m._sha(raw)]) == 0
    assert e.parse_json(capsys.readouterr().out.encode())["status"] == "COMPLETED_SOURCE_INSPECTION"


def test_final_check_is_reached_after_inspection_before_disclosure(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m._inspect; reached = []
    def mark(*args):
        result = original(*args); reached.append(True); return result
    monkeypatch.setattr(m, "_inspect", mark)
    def refuse(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values, guard=refuse)
    assert reached == [True] and result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None


def test_closed_boundaries_and_wrong_cli_hash_refuse_before_effect(tmp_path, monkeypatch, capsys):
    plan = fixture(tmp_path)[0]
    for key, value in (("max_private_bytes", m.MAX_PRIVATE + 1), ("source_executed", True), ("capture_operation_id", "foreign")):
        bad = deepcopy(plan); bad[key] = value
        with pytest.raises(ValueError): execute((bad, deepcopy(SOURCES), tmp_path))
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("wrong hash cannot execute"))
    assert m.main(["--plan-json", "{}", "--plan-sha256", "a" * 64]) == 1
    assert "source_text_returned" in capsys.readouterr().out


# TPR-CR29 regression: an oversized public receipt leaves a body-free failure receipt, not no receipt.


def test_oversized_public_receipt_is_refused_with_a_body_free_receipt(tmp_path, monkeypatch):
    (tmp_path / "full").mkdir(); (tmp_path / "small").mkdir()
    plan, sources, root = fixture(tmp_path / "full")
    full = m.execute_fixture(plan, sources, root, clock=lambda: NOW)
    assert e.parse_json(full)["inspection"] is not None
    monkeypatch.setattr(m, "MAX_PUBLIC", len(full) - 1)
    values = fixture(tmp_path / "small"); plan, _sources, root = values
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["inspection"] is None and result["public_size_refused"] is True
    assert result["private_read_attempts"].fraction() == 2
    assert (root / (plan["operation_id"] + ".result.json")).exists()
