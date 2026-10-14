"""Synthetic AST views only; no cloud/private/operator/API effects."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_owner_mia_source_view as m
from tests.target_price_revisions_qc import test_qc_extended_owner_mia_source_diagnostic as previous

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
    monkeypatch.setattr(m.predecessor, "NOTEBOOK_SHA256", m.diagnostic._sha(previous.previous.NOTEBOOK.encode()))
    original = m.files._directory
    def safe(path, *, private):
        if private and path.is_relative_to(m.LANE): deny()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", safe)


def fixture(tmp_path, **kwargs):
    old, _sources, root = previous.fixture(tmp_path, **kwargs)
    plan = m._plan(git_head="a" * 40, source_hashes={name: m.diagnostic._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b" * 64, created_utc=(NOW - timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW + timedelta(minutes=10)).isoformat(), archive=old["archive"], diff=old["diff"], mode="offline-fixture")
    return plan, dict(SOURCES), root


def execute(values, **kwargs):
    plan, sources, root = values
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), **kwargs))


def notebook(code, *, markdown="SYNTHETIC PRIVATE MARKDOWN", output="SYNTHETIC PRIVATE OUTPUT"):
    return e.canonical({"cells": [
        {"cell_type": "markdown", "metadata": {}, "source": [markdown]},
        {"cell_type": "code", "metadata": {"private": "SYNTHETIC PRIVATE METADATA"}, "source": code,
            "outputs": [{"private": output}], "execution_count": 1}],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 2}).decode()


def test_same_fixed_proof_exposes_views_not_an_executable_port(tmp_path):
    values = fixture(tmp_path); result = execute(values)
    assert result["status"] == "COMPLETED_STATIC_SOURCE_VIEW" and result["private_read_attempts"].fraction() == 2
    assert result["private_read_bytes"].fraction() == values[0]["archive"]["bytes"] + values[0]["diff"]["bytes"]
    assert result["before_matches_public_immutable_bundle"] is True and result["all_changes_recomputed"] is True
    assert result["all_changed_files_accounted"] is True and len(result["views"]) == 5
    main = next(row["view"] for row in result["views"] if row["name"] == "main.py")
    assert main["view_format"] == "normalized_ast_unified_diff"
    assert "@@" not in main["static_python_view"]  # comment-only owner change is withheld, not fabricated as logic
    assert result["source_not_an_executable_port"] is True and result["compiled_source_proven"] is False
    assert result["accepted_metrics"] is None and result["api_requests"].fraction() == 0
    with pytest.raises(FileExistsError): execute(values)


def test_module_class_and_function_docstrings_and_all_comments_are_withheld(tmp_path):
    long_doc = "SYNTHETIC PRIVATE DOC " + "x" * 1995
    body = '"""' + long_doc + '"""\n# API_KEY=SYNTHETIC_PRIVATE_SECRET\nclass Repair:\n    """SYNTHETIC PRIVATE CLASS DOC"""\n    def work(self, value):\n        """SYNTHETIC PRIVATE FUNCTION DOC"""\n        return value\n'
    result = execute(fixture(tmp_path, body=body))
    viewed = next(row["view"] for row in result["views"] if row["name"] == "weight_repair.py")
    assert viewed["view_status"] == "STATIC_POLICY_PASSED"
    assert {row["scope"] for row in viewed["after_docstrings_withheld"]} == {"Module", "ClassDef", "FunctionDef"}
    assert "return value" in viewed["static_python_view"] and "class Repair" in viewed["static_python_view"]
    text = e.canonical(result).decode()
    for private in (long_doc, "SYNTHETIC PRIVATE CLASS DOC", "SYNTHETIC PRIVATE FUNCTION DOC", "SYNTHETIC_PRIVATE_SECRET"):
        assert private not in text and m.diagnostic._sha(private.encode()) not in text
    assert viewed["comments_withheld"] is True and viewed["byte_equivalence_or_docstring_inertness_proven"] is False


@pytest.mark.parametrize("body", [
    "API_KEY = 'SYNTHETIC_PRIVATE_SECRET'\n", "ROWS = [{'ticker':'SYNTHETIC_PRIVATE_TICKER','price':'123.45'}]\n",
    "ROWS = [('SYNTHETIC_PRIVATE_TICKER','123.45')]\n", "VALUE = '" + "a" * 40 + "'\n",
    "VALUE = 'synthetic@example.invalid'\n", "VALUE = '-----BEGIN PRIVATE KEY----- SYNTHETIC'\n",
])
def test_non_docstring_unknown_literal_secret_and_market_row_policy_is_not_weakened(tmp_path, body):
    result = execute(fixture(tmp_path, body=body))
    viewed = next(row["view"] for row in result["views"] if row["name"] == "weight_repair.py")
    assert viewed["view_status"] == "POLICY_REFUSED" and "static_python_view" not in viewed
    assert viewed["refusal_event"]["literal_sha256"] is None
    assert "SYNTHETIC_PRIVATE_SECRET" not in e.canonical(result).decode() and "SYNTHETIC_PRIVATE_TICKER" not in e.canonical(result).decode()


def test_runtime_docstring_reference_is_visible_not_assumed_inert(tmp_path):
    body = '"""SYNTHETIC PRIVATE DOC"""\ndef work(value):\n    return value.__doc__\n'
    result = execute(fixture(tmp_path, body=body))
    viewed = next(row["view"] for row in result["views"] if row["name"] == "weight_repair.py")
    assert viewed["docstring_reference_detected"] is True and viewed["byte_equivalence_or_docstring_inertness_proven"] is False
    assert "__doc__" in viewed["static_python_view"]


def test_added_notebook_shows_code_only_and_accounts_whole_file(tmp_path):
    def alter(_before, current): current["mia.ipynb"] = notebook(['"""SYNTHETIC PRIVATE NB DOC"""\n', 'def work(value):\n    return value\n'])
    result = execute(fixture(tmp_path, source_mutate=alter))
    row = next(row for row in result["views"] if row["name"] == "mia.ipynb")
    assert row["after_identity"]["sha256"] == result["all_current_file_identities"]["mia.ipynb"]["sha256"]
    viewed = row["view"]
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_PASSED" and len(viewed["cells"]) == 2
    assert viewed["cells"][0]["source_withheld"] is True and viewed["cells"][1]["source_withheld"] is False
    assert "return value" in viewed["cells"][1]["code_view"]["static_python_view"]
    text = e.canonical(result).decode()
    for marker in ("SYNTHETIC PRIVATE NB DOC", "SYNTHETIC PRIVATE MARKDOWN", "SYNTHETIC PRIVATE OUTPUT", "SYNTHETIC PRIVATE METADATA"):
        assert marker not in text


def test_one_refused_notebook_code_cell_suppresses_all_code(tmp_path):
    def alter(_before, current):
        value = e.parse_json(notebook("def safe(value):\n    return value\n").encode())
        value["cells"].append({"cell_type": "code", "metadata": {}, "source": "API_KEY='SYNTHETIC_PRIVATE_SECRET'\n", "outputs": []})
        current["mia.ipynb"] = e.canonical(value).decode()
    result = execute(fixture(tmp_path, source_mutate=alter))
    viewed = next(row["view"] for row in result["views"] if row["name"] == "mia.ipynb")
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_REFUSED"
    assert all("static_python_view" not in row.get("code_view", {}) for row in viewed["cells"])
    assert "SYNTHETIC_PRIVATE_SECRET" not in e.canonical(result).decode()


@pytest.mark.parametrize("fault", ["before", "delta", "archive"])
def test_all_source_before_and_delta_proof_precede_views(tmp_path, fault):
    kwargs = {}
    if fault == "before":
        def alter(before, current):
            before["extended_core.py"] += "# synthetic before drift"
            current["extended_core.py"] = before["extended_core.py"]
        kwargs["source_mutate"] = alter
    if fault == "delta": kwargs["delta_mutate"] = lambda delta: delta["changes"].pop()
    if fault == "archive": kwargs["archive_mutate"] = lambda archive: archive.update(project_id=999)
    result = execute(fixture(tmp_path, **kwargs))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["views"] is None


@pytest.mark.parametrize("fault", ["source", "diagnostic", "expired", "extra", "scope"])
def test_frozen_source_and_time_scope_refuse_before_claim(tmp_path, fault):
    values = fixture(tmp_path); clock = lambda: NOW
    if fault in {"source", "diagnostic"}: values[1][m.MODULE if fault == "source" else m.diagnostic.MODULE] += b" "
    if fault == "expired": clock = lambda: NOW + timedelta(hours=1)
    if fault == "extra": values[0]["source_executed"] = True
    if fault == "scope": values[0]["expires_utc"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError): execute(values, clock=clock)
    assert not (values[2] / (m.OPERATION + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic"])
def test_production_no_injected_seams(tmp_path, monkeypatch, fault):
    old, sources, root = fixture(tmp_path)
    args = {name: old[name] for name in m.ARGS}; args.update(mode="production", archive=None, diff=None)
    plan = m._plan(**args)
    assert plan["archive"] == m.predecessor.ARCHIVE and plan["diff"] == m.predecessor.DIFF
    # Keep the clock valid so an injected guard cannot hide behind expiry.
    monkeypatch.setattr(m, "_now", lambda: NOW)
    kwargs = {"guard": m._guard, "clock": m._now, "monotonic": m.time.monotonic}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_: None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


def test_two_body_claims_and_access_precede_every_read(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.files._read; observed = []
    def read(directory, name, **kwargs):
        role = "archive" if name.endswith(".read2.sources.json") else "diff"
        assert all((values[2] / (m.OPERATION + suffix)).exists() for suffix in
            (".claim.spent.json", ".access.json", "." + role + ".read.spent.json"))
        observed.append(name); return original(directory, name, **kwargs)
    monkeypatch.setattr(m.files, "_read", read)
    assert execute(values)["status"] == "COMPLETED_STATIC_SOURCE_VIEW" and len(observed) == 2


def test_final_check_after_completed_views_is_load_bearing(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m._view; reached = []
    def viewed(*args):
        original(*args); reached.append(True)
    monkeypatch.setattr(m, "_view", viewed)
    def refuse(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values, guard=refuse)
    assert reached and result["status"] == "FAILED_OR_UNCERTAIN" and result["views"] is not None


def test_wrong_cli_hash_never_executes(monkeypatch, capsys):
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("bad hash cannot execute"))
    assert m.main(["--plan-json", "{}", "--plan-sha256", "a" * 64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["source_text_returned"] is False
