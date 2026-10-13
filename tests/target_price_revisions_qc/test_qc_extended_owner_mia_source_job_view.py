"""Synthetic exact public identities only; no actual cloud/private/operator I/O."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_owner_mia_source_job_view as m
from tests.target_price_revisions_qc import test_qc_extended_owner_mia_source_view as previous
from tests.target_price_revisions_qc import test_qc_extended_owner_mia_source_inspect as source_fixture

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)
PUBLIC = "7dacf829bda2cf1bbe6d75cac5ab5ca3"


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError("actual private/API/credential/subprocess forbidden")
    monkeypatch.setattr(m.capture.ops, "credential", deny)
    monkeypatch.setattr(m.capture.http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(m.subprocess, "run", deny)
    monkeypatch.setattr(m.predecessor, "NOTEBOOK_SHA256", m.diagnostic._sha(source_fixture.NOTEBOOK.encode()))
    original = m.files._directory
    def safe(path, *, private):
        if private and (path == m.PRIVATE_ROOT or path.is_relative_to(m.LANE)): deny()
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


def notebook_fixture(tmp_path, code):
    def alter(_before, current): current["mia.ipynb"] = previous.notebook(code)
    return fixture(tmp_path, source_mutate=alter)


def notebook_view(result):
    return next(row["view"] for row in result["views"] if row["name"] == "mia.ipynb")


def test_exact_pinned_public_ledger_and_prior_job_set_not_caller_supplied():
    identities = m._public_ids(SOURCES)
    ledger = e.parse_json(SOURCES[m.LEDGER])
    assert len(identities) == 14
    assert identities == frozenset(row["backtest_id"] for row in ledger["jobs"]) | frozenset(ledger["known_historical_jobs"])
    assert PUBLIC in identities and len(PUBLIC) == 32
    assert m.diagnostic._sha(SOURCES[m.LEDGER]) == m.LEDGER_SHA256
    assert len(m.SOURCE_PATHS) == len(set(m.SOURCE_PATHS))


def test_exact_public_job_literal_is_narrow_notebook_exception_not_compiled_proof(tmp_path):
    code = "job = '" + PUBLIC + "'\ndef inspect(value):\n    return value\n"
    assert m.view._notebook(previous.notebook(code), set())["view_status"] == "NOTEBOOK_CODE_POLICY_REFUSED"
    values = notebook_fixture(tmp_path, code); result = execute(values); viewed = notebook_view(result)
    assert result["status"] == "COMPLETED_PUBLIC_JOB_STATIC_VIEW"
    assert result["private_read_attempts"].fraction() == 2
    assert result["private_read_bytes"].fraction() == values[0]["archive"]["bytes"] + values[0]["diff"]["bytes"]
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_PASSED"
    assert viewed["matched_already_public_job_literals"] == [PUBLIC]
    assert PUBLIC in viewed["cells"][1]["code_view"]["static_python_view"]
    assert result["public_identity_count"].fraction() == 14 and result["public_identity_exception_notebook_code_only"] is True
    assert result["generic_opaque_or_hex_exception"] is False and result["compiled_source_proven"] is False
    assert viewed["matching_job_literal_proves_compiled_source"] is False
    assert result["accepted_metrics"] is None and result["new_codex_attempts"].fraction() == 0 and result["attempt_reset"] is False
    assert result["source_not_executed"] is True and result["source_not_an_executable_port"] is True
    assert result["before_matches_public_immutable_bundle"] is True and result["all_changes_recomputed"] is True
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values)


@pytest.mark.parametrize("value", ["z" * 32, PUBLIC + "0", "0" + PUBLIC, "Z" + PUBLIC[1:], PUBLIC.upper()])
def test_unknown_or_substring_opaque_literal_does_not_become_public(tmp_path, value):
    result = execute(notebook_fixture(tmp_path, "job = '" + value + "'\n")); viewed = notebook_view(result)
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_REFUSED"
    assert viewed["matched_already_public_job_literals"] == []
    assert all("static_python_view" not in row.get("code_view", {}) for row in viewed["cells"])
    assert value not in e.canonical(result).decode()


@pytest.mark.parametrize("code", [
    "API_KEY = '" + PUBLIC + "'\n", "ROWS = [{'ticker':'" + PUBLIC + "','price':'123.45'}]\n",
    "ROWS = [('" + PUBLIC + "','123.45')]\n", "HEADERS = {'Authorization':'" + PUBLIC + "'}\n",
])
def test_exact_public_id_does_not_exempt_secret_or_market_row_policy(tmp_path, code):
    viewed = notebook_view(execute(notebook_fixture(tmp_path, code)))
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_REFUSED" and viewed["matched_already_public_job_literals"] == []
    assert all("static_python_view" not in row.get("code_view", {}) for row in viewed["cells"])


def test_public_job_id_exception_does_not_expand_python_helper_policy(tmp_path):
    result = execute(fixture(tmp_path, body="job = '" + PUBLIC + "'\n"))
    viewed = next(row["view"] for row in result["views"] if row["name"] == "weight_repair.py")
    assert viewed["view_status"] == "POLICY_REFUSED" and "static_python_view" not in viewed
    assert viewed["refusal_event"]["reason"] == "NEW_OPAQUE_STRING_LITERAL"
    assert viewed["refusal_event"]["literal_sha256"] is None


def test_public_ids_inside_docs_comments_outputs_or_metadata_are_not_disclosed_or_matched(tmp_path):
    marker = "SYNTHETIC PRIVATE CONTENT"
    def alter(_before, current):
        current["mia.ipynb"] = previous.notebook('"""' + PUBLIC + ' ' + marker + '"""\n# ' + PUBLIC + ' ' + marker + '\ndef safe(value):\n    return value\n',
            markdown=PUBLIC + marker, output=PUBLIC + marker)
    result = execute(fixture(tmp_path, source_mutate=alter)); viewed = notebook_view(result)
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_PASSED" and viewed["matched_already_public_job_literals"] == []
    assert PUBLIC not in e.canonical(result).decode() and marker not in e.canonical(result).decode()
    assert result["all_docstrings_comments_notebook_outputs_markdown_metadata_withheld"] is True


def test_any_unknown_notebook_cell_suppresses_all_public_id_code(tmp_path):
    def alter(_before, current):
        value = e.parse_json(previous.notebook("job = '" + PUBLIC + "'\n").encode())
        value["cells"].append({"cell_type":"code", "metadata":{}, "source":"unknown = '" + "x" * 32 + "'\n", "outputs":[]})
        current["mia.ipynb"] = e.canonical(value).decode()
    viewed = notebook_view(execute(fixture(tmp_path, source_mutate=alter)))
    assert viewed["view_status"] == "NOTEBOOK_CODE_POLICY_REFUSED" and viewed["matched_already_public_job_literals"] == []
    assert all("static_python_view" not in row.get("code_view", {}) for row in viewed["cells"])


@pytest.mark.parametrize("fault", ["ledger", "discovery", "view", "look", "module", "extra", "expiry", "duration"])
def test_pinned_source_closed_plan_and_time_refuse_before_claim(tmp_path, fault):
    values = fixture(tmp_path); clock = lambda: NOW
    names = {"ledger":m.LEDGER, "discovery":m.discovery.MODULE, "view":m.view.MODULE, "look":m.discovery.LOOK, "module":m.MODULE}
    if fault in names: values[1][names[fault]] += b" "
    if fault == "extra": values[0]["caller_public_ids"] = ["a" * 32]
    if fault == "expiry": clock = lambda: NOW + timedelta(hours=1)
    if fault == "duration": values[0]["expires_utc"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError): execute(values, clock=clock)
    assert not (values[2] / (m.OPERATION + ".claim.spent.json")).exists()


@pytest.mark.parametrize("fault", ["project", "duplicate", "ordinal", "historical", "economics", "compiled", "reset", "metrics"])
def test_semantic_public_ledger_proof_is_independent_of_its_digest(monkeypatch, fault):
    sources = dict(SOURCES); value = e.parse_json(sources[m.LEDGER])
    if fault == "project": value["project_id"] = 999
    if fault == "duplicate": value["jobs"][1]["backtest_id"] = value["jobs"][0]["backtest_id"]
    if fault == "ordinal": value["jobs"][0]["look_ordinal"] = 22
    if fault == "historical": value["known_historical_jobs"].pop()
    if fault == "economics": value["jobs"][0]["economics_accepted"] = True
    if fault == "compiled": value["jobs"][0]["compiled_source_proven"] = True
    if fault == "reset": value["attempt_reset"] = True
    if fault == "metrics": value["jobs"][0]["accepted_metrics"] = {"return":123}
    sources[m.LEDGER] = e.canonical(value)
    monkeypatch.setattr(m, "LEDGER_SHA256", m.diagnostic._sha(sources[m.LEDGER]))
    with pytest.raises(ValueError): m._public_ids(sources)


@pytest.mark.parametrize("fault", ["before", "delta", "archive"])
def test_all_immutable_before_delta_and_project_proof_precede_views(tmp_path, fault):
    kwargs = {}
    if fault == "before":
        def alter(before, current):
            before["extended_core.py"] += "# synthetic drift"
            current["extended_core.py"] = before["extended_core.py"]
        kwargs["source_mutate"] = alter
    if fault == "delta": kwargs["delta_mutate"] = lambda delta: delta["changes"].pop()
    if fault == "archive": kwargs["archive_mutate"] = lambda archive: archive.update(project_id=999)
    result = execute(fixture(tmp_path, **kwargs))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["views"] is None


@pytest.mark.parametrize("fault", ["root", "guard", "clock", "monotonic"])
def test_production_has_no_injected_seams(tmp_path, fault):
    old, sources, root = fixture(tmp_path)
    args = {name:old[name] for name in m.ARGS}; args.update(mode="production", archive=None, diff=None)
    plan = m._plan(**args)
    assert plan["archive"] == m.predecessor.ARCHIVE and plan["diff"] == m.predecessor.DIFF
    kwargs = {"guard":m._guard, "clock":m._now, "monotonic":m.time.monotonic}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_:None
    with pytest.raises(ValueError): m._execute(plan, sources, root, **kwargs)


def test_two_exclusive_body_claims_and_access_exist_before_reads(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m.files._read; seen = []
    def read(directory, name, **kwargs):
        role = "archive" if name.endswith(".read2.sources.json") else "diff"
        assert all((values[2] / (m.OPERATION + suffix)).exists() for suffix in
            (".claim.spent.json", ".access.json", "." + role + ".read.spent.json"))
        seen.append(name); return original(directory, name, **kwargs)
    monkeypatch.setattr(m.files, "_read", read)
    assert execute(values)["status"] == "COMPLETED_PUBLIC_JOB_STATIC_VIEW" and len(seen) == 2


def test_final_check_after_static_view_is_load_bearing(tmp_path, monkeypatch):
    values = fixture(tmp_path); original = m._view; reached = []
    def viewed(*args): original(*args); reached.append(True)
    monkeypatch.setattr(m, "_view", viewed)
    def refuse(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values, guard=refuse)
    assert reached and result["status"] == "FAILED_OR_UNCERTAIN" and result["views"] is not None


def test_wrong_cli_hash_never_executes(monkeypatch, capsys):
    monkeypatch.setattr(m, "execute_plan", lambda *_: pytest.fail("bad hash cannot execute"))
    assert m.main(["--plan-json","{}","--plan-sha256","a"*64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["source_text_returned"] is False
