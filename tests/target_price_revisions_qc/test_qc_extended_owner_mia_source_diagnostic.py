"""Bounded synthetic static classifications; no cloud source execution/disclosure."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_owner_mia_source_diagnostic as m
from tests.target_price_revisions_qc import test_qc_extended_owner_mia_source_inspect as previous

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError("actual private/API/credential/subprocess forbidden")
    monkeypatch.setattr(m.capture.ops, "credential", deny)
    monkeypatch.setattr(m.capture.http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(m.subprocess, "run", deny)
    monkeypatch.setattr(m.predecessor, "NOTEBOOK_SHA256", m._sha(previous.NOTEBOOK.encode()))
    original = m.files._directory
    def safe(path, *, private):
        if private and path.is_relative_to(m.LANE): deny()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", safe)


def fixture(tmp_path, *, body=None, **kwargs):
    if body is not None:
        kwargs["source_mutate"] = lambda _before, current: current.update({"weight_repair.py": body})
    old_plan, _old_sources, root = previous.fixture(tmp_path, **kwargs)
    plan = m._plan(git_head="a" * 40, source_hashes={name: m._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b" * 64, created_utc=(NOW - timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW + timedelta(minutes=10)).isoformat(), archive=old_plan["archive"], diff=old_plan["diff"], mode="offline-fixture")
    return plan, dict(SOURCES), root


def execute(values, **kwargs):
    plan, sources, root = values
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), **kwargs))


def test_verified_delta_and_policy_passes_never_disclose_source(tmp_path):
    values = fixture(tmp_path); result = execute(values)
    assert result["status"] == "COMPLETED_POLICY_DIAGNOSTIC" and result["stage"] == "diagnosis_complete"
    assert result["private_read_attempts"].fraction() == 2
    assert result["private_read_bytes"].fraction() == values[0]["archive"]["bytes"] + values[0]["diff"]["bytes"]
    assert result["all_changes_recomputed"] is True and result["before_matches_public_immutable_bundle"] is True
    assert all(row["classification"] == "POLICY_PASSED_NO_DISCLOSURE" for row in result["policy_diagnostics"])
    text = e.canonical(result).decode()
    assert previous.HELPER not in text and "static_python_text" not in text
    assert result["source_disclosed"] is False and result["source_executed"] is False
    assert result["compiled_source_proven"] is False and result["accepted_metrics"] is None
    with pytest.raises(FileExistsError): execute(values)


@pytest.mark.parametrize("body,reason", [
    ("VALUE = '" + "a" * 40 + "'\n", "NEW_OPAQUE_STRING_LITERAL"),
    ("API_KEY = 'SYNTHETIC_PRIVATE_SECRET'\n", "SECRET_NAMED_LITERAL_ASSIGNMENT"),
    ("ACCOUNT_ID = 12345\n", "SECRET_NAMED_LITERAL_ASSIGNMENT"),
    ("ROWS = [{'ticker':'SYNTHETIC_PRIVATE_TICKER','price':'123.45'}]\n", "NEW_LITERAL_NESTED_ROW_CONTAINER"),
    ("HEADERS = {'Authorization':'SYNTHETIC_PRIVATE_SECRET'}\n", "NEW_LITERAL_MARKET_OR_CREDENTIAL_DICT"),
    ("ROWS = [('SYNTHETIC_PRIVATE_TICKER','123.45')]\n", "NEW_LITERAL_NESTED_ROW_CONTAINER"),
    ("VALUE = '-----BEGIN PRIVATE KEY----- SYNTHETIC_PRIVATE_SECRET'\n", "NEW_PRIVATE_KEY_MARKER"),
    ("VALUE = 'synthetic@example.invalid'\n", "NEW_EMAIL_PATTERN"),
    ("VALUE = '" + "x " * 600 + "'\n", "NEW_STRING_BYTE_BOUND"),
    ("# API_KEY=SYNTHETIC_PRIVATE_SECRET\n", "CHANGED_LINE_CREDENTIAL_PATTERN"),
    ("class invalid(:\n", "AFTER_SYNTAX_OR_RECURSION"),
])
def test_exact_policy_classification_is_metadata_not_a_secret_fact_or_disclosure(tmp_path, body, reason):
    result = execute(fixture(tmp_path, body=body))
    assert result["status"] == "COMPLETED_POLICY_DIAGNOSTIC"
    row = next(row for row in result["policy_diagnostics"] if row["name"] == "weight_repair.py")
    assert row["classification"] == "POLICY_REFUSED" and row["policy_refused"] is True
    assert row["event"]["reason"] == reason
    assert row["event"]["literal_sha256"] is None and row["event"]["literal_digest_withheld"] is True
    text = e.canonical(result).decode()
    assert body not in text and "SYNTHETIC_PRIVATE_SECRET" not in text and "SYNTHETIC_PRIVATE_TICKER" not in text


def test_opaque_literal_length_and_context_withhold_digest_without_waiving_screen(tmp_path):
    value = "schema_identifier_that_is_thirty_two_plus_characters"
    result = execute(fixture(tmp_path, body="VALUE = '" + value + "'\n"))
    row = next(row for row in result["policy_diagnostics"] if row["name"] == "weight_repair.py")
    assert row["event"]["literal_sha256"] is None and row["event"]["literal_digest_withheld"] is True
    assert row["event"]["literal_bytes"].fraction() == len(value.encode())
    assert row["event"]["length_representation"] == "string_literal_utf8"
    assert row["event"]["line"].fraction() == 1 and value not in e.canonical(result).decode()
    assert m._sha(value.encode()) not in e.canonical(result).decode()
    assert row["policy_refused"] is True


def test_long_dictionary_field_exemption_remains_not_an_arbitrary_value_exemption(tmp_path):
    result = execute(fixture(tmp_path, body="FIELDS = {'source_current_equals_job_compiled_unknown_flag': False}\n"))
    row = next(row for row in result["policy_diagnostics"] if row["name"] == "weight_repair.py")
    assert row["classification"] == "POLICY_PASSED_NO_DISCLOSURE" and row["event"] is None


@pytest.mark.parametrize("fault", ["foreign_project", "extra_archive", "omit_delta", "baseline"])
def test_proof_refusal_precedes_policy_classification(tmp_path, fault):
    kwargs = {}
    if fault == "foreign_project": kwargs["archive_mutate"] = lambda archive: archive.update(project_id=999)
    if fault == "extra_archive": kwargs["archive_mutate"] = lambda archive: archive.update(extra=True)
    if fault == "omit_delta": kwargs["delta_mutate"] = lambda delta: delta["changes"].pop()
    if fault == "baseline":
        def alter(before, current):
            before["extended_core.py"] += "# synthetic baseline drift"
            current["extended_core.py"] = before["extended_core.py"]
        kwargs["source_mutate"] = alter
    result = execute(fixture(tmp_path, **kwargs))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["policy_diagnostics"] is None
    assert result["before_matches_public_immutable_bundle"] is False
    assert result["stage"] in {"archive_schema", "delta_recomputation", "immutable_before_tree"}


def test_access_and_two_per_body_claims_are_durable_before_reads(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.files._read; observed = []
    def read(directory, name, **kwargs):
        role = "archive" if name.endswith(".read2.sources.json") else "diff"
        assert all((values[2] / (m.OPERATION + suffix)).exists() for suffix in
            (".claim.spent.json", ".access.json", "." + role + ".read.spent.json"))
        observed.append(name); return original(directory, name, **kwargs)
    monkeypatch.setattr(m.files, "_read", read)
    assert execute(values)["status"] == "COMPLETED_POLICY_DIAGNOSTIC" and len(observed) == 2


@pytest.mark.parametrize("fault", ["expired", "source", "predecessor", "extra", "scope"])
def test_closed_source_scope_time_and_predecessor_refuse_before_claim(tmp_path, fault):
    values = fixture(tmp_path); clock = lambda: NOW
    if fault == "expired": clock = lambda: NOW + timedelta(hours=1)
    if fault in {"source", "predecessor"}: values[1][m.MODULE if fault == "source" else m.predecessor.MODULE] += b" "
    if fault == "extra": values[0]["disclose_source"] = True
    if fault == "scope": values[0]["expires_utc"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError): execute(values, clock=clock)
    assert not (values[2] / (m.OPERATION + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic"])
def test_production_no_injected_seams_and_fixed_real_descriptors(tmp_path, fault):
    old, sources, root = fixture(tmp_path)
    args = {name: old[name] for name in m.ARGS}; args.update(mode="production", archive=None, diff=None)
    plan = m._plan(**args)
    assert plan["archive"] == m.predecessor.ARCHIVE and plan["diff"] == m.predecessor.DIFF
    kwargs = {"guard": m._guard, "clock": m._now, "monotonic": m.time.monotonic}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_: None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


@pytest.mark.parametrize("root", [m.PRIVATE_ROOT, m.LANE / "synthetic-never-created"])
def test_fixture_cannot_read_actual_private_or_lane_root(tmp_path, root):
    plan, sources, _ = fixture(tmp_path)
    with pytest.raises(ValueError): m.execute_fixture(plan, sources, root, clock=lambda: NOW)


def test_final_check_is_after_diagnosis_before_completed_status(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m._diagnose; reached = []
    def diagnosed(*args):
        original(*args); reached.append(True)
    monkeypatch.setattr(m, "_diagnose", diagnosed)
    def refuse(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values, guard=refuse)
    assert reached and result["status"] == "FAILED_OR_UNCERTAIN" and result["policy_diagnostics"] is not None


def test_wrong_cli_hash_never_executes(monkeypatch, capsys):
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("bad hash cannot execute"))
    assert m.main(["--plan-json", "{}", "--plan-sha256", "a" * 64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["source_text_returned"] is False
