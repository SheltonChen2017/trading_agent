"""Synthetic custody/receipt/transport tests; no real credentials or QC access.

These exercise a cooperative scoped controller, not canonical antirollback or
protected-parent custody. Every file and cloud response below is a fixture.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import operations as ops


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
REAL_GUARD = ops.guard


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def forbid_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unexpected real process, credentials, or network access")
    monkeypatch.delenv("QC_USER_ID", raising=False)
    monkeypatch.delenv("QC_API_TOKEN", raising=False)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(ops.subprocess, "run", forbidden)
    monkeypatch.setattr(ops.http.client, "HTTPSConnection", forbidden)
    monkeypatch.setattr(ops, "datetime", FrozenDateTime)


@pytest.fixture
def scope(tmp_path, monkeypatch):
    lane = tmp_path / "synthetic-lane"
    lane.mkdir(mode=0o700)
    artifacts = lane / "artifacts"
    artifacts.mkdir(mode=0o700)
    package = lane / "package"
    package.mkdir(mode=0o700)
    private = artifacts / "qc" / "run"
    source_dir = artifacts / "synthetic-source"
    source_dir.mkdir(mode=0o700)
    source = source_dir / "structure.json"
    raw = b'{"identities":[],"ratings":[],"synthetic":true}\n'
    source.write_bytes(raw)
    source.chmod(0o600)
    freeze = {"review_baseline": ops.BASELINE,
        "operations": {"fresh_operation_id": "SYNTHETIC-ACCESS"},
        "universes": [{"case": f"case{i}", "id": f"SYNTHETIC-CANDIDATE-{i}"} for i in range(6)]}
    (package / "six_universe_freeze.json").write_bytes(ops.canonical(freeze))
    for name, value in {"LANE": lane, "PACKAGE": package, "PRIVATE": private,
                        "SOURCE": source, "SOURCE_HASH": ops.digest(raw),
                        "FREEZE_HASH": ops.digest(ops.canonical(freeze))}.items():
        monkeypatch.setattr(ops, name, value)
    monkeypatch.setattr(ops, "guard", lambda: {"head": ops.BASELINE, "status": "synthetic changes"})
    return SimpleNamespace(lane=lane, package=package, private=private,
                           source=source, raw=raw, freeze=freeze)


def body(path):
    return json.loads(path.read_bytes())


def alter_access(scope, **changes):
    path = scope.private / "access.json"
    value = body(path)
    value.update(changes)
    path.write_bytes(ops.canonical(value))


def register(case="case0", project=41):
    ops.exclusive(case + ".project.json", {"project_id": project, "owner": True,
                                          "organization_id": "synthetic-organization"})


def fake_transport(monkeypatch, raw=None, status=200, fail=None):
    """Install one non-network connection and record every bounded operation."""
    calls = []
    value = ops.canonical({"success": True}) if raw is None else raw
    class Response:
        def read(self, count):
            calls.append(("read", count))
            return value[:count]
    response = Response()
    response.status = status
    class Connection:
        def request(self, *args, **kwargs):
            calls.append(("request", args, kwargs))
            if fail is not None:
                raise fail
        def getresponse(self):
            calls.append(("response",))
            return response
        def close(self):
            calls.append(("close",))
    def connect(*args, **kwargs):
        calls.append(("connect", args, kwargs))
        return Connection()
    monkeypatch.setenv("QC_USER_ID", "synthetic-user")
    monkeypatch.setenv("QC_API_TOKEN", "synthetic-token-not-real")
    monkeypatch.setattr(ops.ssl, "create_default_context", lambda: "synthetic-tls")
    monkeypatch.setattr(ops.http.client, "HTTPSConnection", connect)
    monkeypatch.setattr(ops.time, "time", lambda: 123456)
    return calls


def test_guard_checks_physical_git_root_branch_head_and_status(scope, monkeypatch):
    calls = []
    answers = {("rev-parse", "--show-toplevel"): str(scope.lane),
        ("branch", "--show-current"): ops.BRANCH,
        ("rev-parse", "HEAD"): ops.BASELINE, ("status", "--short"): " M synthetic.py"}
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs == {"cwd": scope.lane, "check": True, "capture_output": True, "text": True}
        return SimpleNamespace(stdout=answers[tuple(command[1:])])
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: scope.lane))
    monkeypatch.setattr(ops.subprocess, "run", run)
    assert REAL_GUARD() == {"head": ops.BASELINE, "status": "M synthetic.py"}
    assert calls[-1] == ["git", "status", "--short"]


@pytest.mark.parametrize("wrong", ["physical", "alias", "gitroot", "branch", "head"])
def test_guard_refuses_wrong_lane_without_any_operational_io(scope, monkeypatch, wrong):
    location = scope.lane
    if wrong == "physical":
        location = scope.lane.parent
    elif wrong == "alias":
        location = scope.lane.parent / "alias"
        location.symlink_to(scope.lane, target_is_directory=True)
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: location))
    answers = {("rev-parse", "--show-toplevel"): "other" if wrong == "gitroot" else str(scope.lane),
        ("branch", "--show-current"): "main" if wrong == "branch" else ops.BRANCH,
        ("rev-parse", "HEAD"): "0" * 40 if wrong == "head" else ops.BASELINE}
    monkeypatch.setattr(ops.subprocess, "run", lambda cmd, **kw: SimpleNamespace(stdout=answers[tuple(cmd[1:])]))
    with pytest.raises(ops.Refusal):
        REAL_GUARD()
    assert not scope.private.exists()


def test_private_root_and_exclusive_receipts_keep_custody_and_no_overwrite(scope):
    expected = ops.exclusive("synthetic.json", {"synthetic": True})
    assert expected == ops.digest(ops.read_private("synthetic.json"))
    for path, mode in [(scope.private.parent, 0o700), (scope.private, 0o700),
                       (scope.private / "synthetic.json", 0o600)]:
        assert path.stat().st_mode & 0o777 == mode
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.exclusive("synthetic.json", {"overwritten": True})
    assert body(scope.private / "synthetic.json") == {"synthetic": True}


@pytest.mark.parametrize("name", ["../escape", "/absolute", "sub/file", "x" * 151, ""])
def test_invalid_private_names_refuse(scope, name):
    with pytest.raises(ops.Refusal):
        ops.exclusive(name, {})
    with pytest.raises(ops.Refusal):
        ops.read_private(name)


@pytest.mark.parametrize("kind", ["mode", "symlink", "hardlink", "directory"])
def test_private_read_refuses_unsafe_file_custody(scope, kind):
    ops.exclusive("fixture.json", b"fixture")
    path = scope.private / "fixture.json"
    if kind == "mode":
        path.chmod(0o644)
    elif kind == "hardlink":
        os.link(path, scope.private / "alias.json")
    else:
        path.unlink()
        if kind == "symlink":
            path.symlink_to(scope.source)
        else:
            path.mkdir(mode=0o700)
    with pytest.raises(ops.Refusal, match="custody"):
        ops.read_private("fixture.json")


def test_existing_root_mode_is_refused_not_repaired(scope):
    scope.private.parent.mkdir(mode=0o755)
    with pytest.raises(ops.Refusal, match="custody"):
        ops.exclusive("fixture.json", {})
    assert scope.private.parent.stat().st_mode & 0o777 == 0o755


def test_private_read_bound(scope):
    ops.exclusive("fixture.json", b"12345")
    assert ops.read_private("fixture.json", maximum=5) == b"12345"
    with pytest.raises(ops.Refusal, match="exceeds bound"):
        ops.read_private("fixture.json", maximum=4)


def test_access_records_bounded_fresh_scope_without_credentials_or_source_read(scope):
    ops.prepare_access()
    receipt = ops.access()
    assert receipt["operation_id"] == "SYNTHETIC-ACCESS"
    assert receipt["source_sha256"] == ops.digest(scope.raw)
    assert receipt["source_reads"] == 1 and receipt["source_refreshes"] == 0
    assert receipt["old_outcome_reads"] == receipt["d0_reads"] == 0
    assert receipt["max_attempts_each"] == 3 and receipt["max_projects"] == 6
    assert receipt["max_requests"] == 1000 and receipt["max_response_bytes"] == 16 * 1024 * 1024
    assert receipt["canonical_admission"] is False and receipt["trading"] is False
    assert not (scope.private / "source-read.spent.json").exists()
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.prepare_access()


@pytest.mark.parametrize("age,allowed", [(0, True), (172800, True), (172801, False), (-1, False)])
def test_access_48_hour_window_includes_boundary_not_future(scope, age, allowed):
    ops.prepare_access()
    alter_access(scope, created_utc=(NOW - timedelta(seconds=age)).isoformat())
    if allowed:
        assert ops.access()["schema"] == "tpr-qc6-access-v1"
    else:
        with pytest.raises(ops.Refusal, match="expired"):
            ops.access()


def test_freeze_change_refuses_existing_access(scope):
    ops.prepare_access()
    scope.freeze["operations"]["fresh_operation_id"] = "DIFFERENT"
    (scope.package / "six_universe_freeze.json").write_bytes(ops.canonical(scope.freeze))
    with pytest.raises(ops.Refusal, match="freeze changed"):
        ops.access()


@pytest.mark.parametrize("field", ["case_count", "baseline"])
def test_bad_freeze_refuses_access_reservation(scope, field):
    if field == "case_count":
        scope.freeze["universes"].pop()
    else:
        scope.freeze["review_baseline"] = "0" * 40
    (scope.package / "six_universe_freeze.json").write_bytes(ops.canonical(scope.freeze))
    with pytest.raises(ops.Refusal, match="six-case freeze"):
        ops.prepare_access()
    assert not scope.private.exists()


def test_structure_read_is_spent_first_hash_verified_and_once(scope, monkeypatch):
    ops.prepare_access()
    original_open = os.open
    opens = []
    def watched_open(path, *args, **kwargs):
        if path == scope.source.name and "dir_fd" in kwargs:
            assert (scope.private / "source-read.spent.json").exists()
            assert args[0] & os.O_NOFOLLOW
            opens.append(path)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", watched_open)
    assert ops.read_structure() == scope.raw
    assert body(scope.private / "source-read.completed.json")["sha256"] == ops.digest(scope.raw)
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.read_structure()
    assert opens == [scope.source.name]


@pytest.mark.parametrize("failure", ["hash", "mode"])
def test_source_failure_still_spends_read_and_never_claims_completion(scope, failure):
    ops.prepare_access()
    if failure == "hash":
        scope.source.write_bytes(b"different fixture")
    else:
        scope.source.chmod(0o644)
    with pytest.raises(ops.Refusal):
        ops.read_structure()
    assert (scope.private / "source-read.spent.json").exists()
    assert not (scope.private / "source-read.completed.json").exists()
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.read_structure()


@pytest.mark.parametrize("endpoint", ["live/create", "live/read", "data/read", "optimizations/create",
                                     "projects/share", "files/delete", "../authenticate"])
def test_out_of_scope_endpoints_refuse_before_request_reservation(scope, endpoint):
    ops.prepare_access()
    with pytest.raises(ops.Refusal, match="outside scoped"):
        ops.post(endpoint, {"projectId": 41})
    assert list(scope.private.glob("request.*")) == []


@pytest.mark.parametrize("project", [None, 99, "41", True])
def test_unregistered_or_wrong_type_project_refuses_before_request(scope, project):
    ops.prepare_access()
    register()
    with pytest.raises(ops.Refusal, match="unregistered"):
        ops.post("files/read", {"projectId": project})
    assert list(scope.private.glob("request.*")) == []


def test_missing_credentials_are_receipted_without_network(scope):
    ops.prepare_access()
    with pytest.raises(ops.Refusal, match="unavailable"):
        ops.authenticate()
    reservation = body(scope.private / "request.0001.json")
    terminal = body(scope.private / "request.0001.terminal.json")
    assert reservation["endpoint"] == "authenticate"
    assert terminal["status"] == "credentials_missing"
    assert "payload" not in reservation


def test_request_budget_counts_failures_and_terminal_slots_once(scope):
    ops.prepare_access()
    alter_access(scope, max_requests=2)
    for _ in range(2):
        with pytest.raises(ops.Refusal, match="unavailable"):
            ops.authenticate()
    with pytest.raises(ops.Refusal, match="budget exhausted"):
        ops.authenticate()
    assert (scope.private / "request.0002.terminal.json").exists()
    assert not (scope.private / "request.0003.json").exists()


@pytest.mark.parametrize("project_key", ["projectId", "id"])
def test_registered_project_transport_is_pinned_bounded_and_credential_safe(scope, monkeypatch, project_key):
    ops.prepare_access()
    register()
    calls = fake_transport(monkeypatch)
    assert ops.post("files/read", {project_key: 41}) == {"success": True}
    assert calls[0] == ("connect", ("www.quantconnect.com",), {"timeout": 30, "context": "synthetic-tls"})
    request = next(row for row in calls if row[0] == "request")
    assert request[1] == ("POST", "/api/v2/files/read")
    assert request[2]["body"] == ops.canonical({project_key: 41})
    assert request[2]["headers"]["Timestamp"] == "123456"
    assert request[2]["headers"]["Authorization"].startswith("Basic ")
    assert ("read", 16 * 1024 * 1024 + 1) in calls and calls[-1] == ("close",)
    assert body(scope.private / "request.0001.terminal.json")["status"] == "succeeded"
    receipt_bytes = b"".join(path.read_bytes() for path in scope.private.glob("request.*.json"))
    assert b"synthetic-token-not-real" not in receipt_bytes and b"synthetic-user" not in receipt_bytes


@pytest.mark.parametrize("status,raw,expected", [
    (302, b'{"success":true}', "failed"),
    (200, b'{"success":false,"errors":["synthetic error"]}', "failed"),
    (200, b'{"success":1}', "failed"),
    (200, b'[]', "failed"),
    (200, b'invalid-json', "transport_or_decode_failure"),
    (200, b'{"success":true,"echo":"synthetic-token-not-real"}', "response_refused"),
])
def test_unsuccessful_response_has_one_terminal_no_retry_or_redirect(scope, monkeypatch, status, raw, expected):
    ops.prepare_access()
    calls = fake_transport(monkeypatch, raw=raw, status=status)
    with pytest.raises(ops.Refusal):
        ops.authenticate()
    assert body(scope.private / "request.0001.terminal.json")["status"] == expected
    assert sum(row[0] == "request" for row in calls) == 1
    assert calls[-1] == ("close",)


def test_oversize_response_is_bounded_receipted_and_not_retained(scope, monkeypatch):
    ops.prepare_access()
    calls = fake_transport(monkeypatch, raw=b"x" * (16 * 1024 * 1024 + 1))
    with pytest.raises(ops.Refusal, match="exceeds bound"):
        ops.authenticate()
    assert ("read", 16 * 1024 * 1024 + 1) in calls
    assert body(scope.private / "request.0001.terminal.json")["status"] == "response_refused"
    assert sum(path.stat().st_size for path in scope.private.iterdir()) < 10000


def test_transport_failure_is_sanitized_receipted_and_not_retried(scope, monkeypatch):
    ops.prepare_access()
    calls = fake_transport(monkeypatch, fail=OSError("synthetic-token-not-real"))
    with pytest.raises(ops.Refusal, match="no automatic retry") as caught:
        ops.authenticate()
    assert "synthetic-token-not-real" not in str(caught.value)
    assert body(scope.private / "request.0001.terminal.json")["status"] == "transport_or_decode_failure"
    assert sum(row[0] == "request" for row in calls) == 1 and calls[-1] == ("close",)


def test_connection_constructor_failure_gets_sanitized_terminal(scope, monkeypatch):
    ops.prepare_access()
    fake_transport(monkeypatch)
    def failed_constructor(*args, **kwargs):
        raise OSError("synthetic-token-not-real")
    monkeypatch.setattr(ops.http.client, "HTTPSConnection", failed_constructor)
    with pytest.raises(ops.Refusal, match="no automatic retry"):
        ops.authenticate()
    assert body(scope.private / "request.0001.terminal.json")["status"] == "transport_or_decode_failure"


def project_response(**changes):
    project = {"name": "SYNTHETIC-CANDIDATE-0-private", "projectId": 41,
               "owner": True, "isPublic": False, "collaborators": [], "maxFileSize": 32000}
    project.update(changes)
    return {"success": True, "projects": [project]}


def test_fresh_owned_private_project_is_spent_before_api_and_registered_once(scope, monkeypatch):
    ops.prepare_access()
    requests = []
    def create(endpoint, payload, **context):
        assert (scope.private / "case0.project-create.spent.json").exists()
        assert context == {"_project_context": "case0"}
        requests.append((endpoint, payload))
        return project_response()
    monkeypatch.setattr(ops, "post", create)
    record = ops.create_project("case0")
    assert record["project_id"] == ops.registered_project("case0") == 41
    assert record["owner"] is True and record["shared_by_this_operation"] is False
    assert requests == [("projects/create", {"name": "SYNTHETIC-CANDIDATE-0-private", "language": "Py"})]
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.create_project("case0")
    assert len(requests) == 1


@pytest.mark.parametrize("change", [{"owner": False}, {"owner": None}, {"isPublic": True},
    {"collaborators": [{"owner": False}]}, {"name": "unrelated"}, {"projectId": True}])
def test_ambiguous_or_nonprivate_project_refuses_registration_but_remains_spent(scope, monkeypatch, change):
    ops.prepare_access()
    monkeypatch.setattr(ops, "post", lambda *_args, **_kwargs: project_response(**change))
    with pytest.raises(ops.Refusal):
        ops.create_project("case0")
    assert (scope.private / "case0.project-create.spent.json").exists()
    assert not (scope.private / "case0.project.json").exists()
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.create_project("case0")


def test_unknown_candidate_never_creates_or_reserves(scope):
    ops.prepare_access()
    with pytest.raises(ops.Refusal, match="unknown frozen universe"):
        ops.create_project("not-a-case")
    with pytest.raises(ops.Refusal, match="unknown frozen universe"):
        ops.reserve_attempt("not-a-case", {"main.py": "a" * 64}, "b" * 64)
    assert list(scope.private.glob("*.attempt.*")) == []


def test_three_attempt_cap_persists_across_source_packet_fixes_and_failed_terminals(scope):
    ops.prepare_access()
    register()
    for number in range(1, 4):
        receipt = ops.reserve_attempt("case0", {"main.py": str(number) * 64}, str(number + 3) * 64)
        assert receipt["attempt"] == number
        assert receipt["candidate_id"] == "SYNTHETIC-CANDIDATE-0"
        assert receipt["compile_counts_as_attempt"] is True
        assert receipt["look_reserved_before_backtest"] is True
        ops.exclusive(f"case0.attempt.{number}.terminal.json", {"status": "compile_failure"})
    with pytest.raises(ops.Refusal, match="three attempts consumed"):
        ops.reserve_attempt("case0", {"main.py": "e" * 64}, "f" * 64)
    assert len(list(scope.private.glob("case0.attempt.*.reserved.json"))) == 3
    assert not (scope.private / "case0.attempt.4.reserved.json").exists()


def test_reservation_without_terminal_still_consumes_attempt(scope):
    ops.prepare_access()
    register()
    first = ops.reserve_attempt("case0", {"main.py": "a" * 64}, "b" * 64)
    second = ops.reserve_attempt("case0", {"main.py": "a" * 64}, "b" * 64)
    assert (first["attempt"], second["attempt"]) == (1, 2)


def test_six_genuine_cases_have_separate_frozen_attempt_counters(scope):
    ops.prepare_access()
    for number in range(6):
        register(f"case{number}", 41 + number)
        receipt = ops.reserve_attempt(f"case{number}", {"main.py": "a" * 64}, "b" * 64)
        assert receipt["attempt"] == 1 and receipt["project_id"] == 41 + number
    assert len(list(scope.private.glob("*.attempt.*.reserved.json"))) == 6


def test_changed_operations_source_refuses_spent_access(scope, monkeypatch):
    ops.prepare_access()
    other_code = scope.lane / "different-operations.py"
    other_code.write_bytes(b"# synthetic changed implementation\n")
    monkeypatch.setattr(ops, "__file__", str(other_code))
    with pytest.raises(ops.Refusal, match="operations source changed"):
        ops.access()


def test_directory_symlink_cannot_substitute_private_root(scope):
    ops.exclusive("fixture.json", {})
    alias = scope.lane / "symlink-root"
    alias.symlink_to(scope.private, target_is_directory=True)
    with pytest.raises(ops.Refusal, match="custody"):
        ops._read_custodied(alias, "fixture.json", 100)


def test_file_swap_to_symlink_at_open_is_not_followed(scope, monkeypatch):
    ops.exclusive("fixture.json", {})
    original_open = os.open
    def raced_open(path, flags, *args, **kwargs):
        if path == "fixture.json" and "dir_fd" in kwargs:
            destination = scope.private / "fixture.json"
            destination.unlink()
            destination.symlink_to(scope.source)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", raced_open)
    with pytest.raises(ops.Refusal, match="custody"):
        ops.read_private("fixture.json")


@pytest.mark.parametrize("endpoint", ["compile/create", "backtests/create", "object/set", "projects/create"])
def test_generic_post_cannot_bypass_typed_launch_or_upload(scope, endpoint):
    ops.prepare_access()
    register()
    with pytest.raises(ops.Refusal):
        ops.post(endpoint, {"projectId": 41})
    assert list(scope.private.glob("request.*")) == []


def reserved(scope):
    ops.prepare_access()
    register()
    sources = {"main.py": "a" * 64}
    receipt = ops.reserve_attempt("case0", sources, "b" * 64)
    return sources, receipt


def test_typed_compile_launch_binds_source_and_only_launches_once(scope, monkeypatch):
    sources, _ = reserved(scope)
    calls = fake_transport(monkeypatch, raw=ops.canonical({"success": True, "compileId": "compile-1", "state": "InQueue"}))
    result = ops.compile_candidate("case0", 1, sources)
    assert result["compileId"] == "compile-1"
    prefix = "case0.attempt.1.compile"
    assert (scope.private / (prefix + ".spent.json")).exists()
    assert (scope.private / (prefix + ".transport-spent.json")).exists()
    assert body(scope.private / (prefix + ".terminal.json"))["status"] == "launched"
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.compile_candidate("case0", 1, sources)
    assert sum(row[0] == "request" for row in calls) == 1


def test_compile_source_mismatch_refuses_before_stage_spend(scope):
    reserved(scope)
    with pytest.raises(ops.Refusal, match="binding mismatch"):
        ops.compile_candidate("case0", 1, {"main.py": "c" * 64})
    assert not (scope.private / "case0.attempt.1.compile.spent.json").exists()


def test_uncertain_compile_keeps_attempt_and_stage_spent_without_retry(scope):
    sources, _ = reserved(scope)
    with pytest.raises(ops.Refusal, match="attempt remains consumed"):
        ops.compile_candidate("case0", 1, sources)
    assert body(scope.private / "case0.attempt.1.compile.terminal.json")["status"] == "failed_or_uncertain"
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.compile_candidate("case0", 1, sources)
    assert ops.reserve_attempt("case0", sources, "b" * 64)["attempt"] == 2


def prepare_compile(scope, monkeypatch):
    sources, _ = reserved(scope)
    fake_transport(monkeypatch, raw=ops.canonical({"success": True, "compileId": "compile-1", "state": "BuildSuccess"}))
    ops.compile_candidate("case0", 1, sources)
    return sources


def test_typed_backtest_binds_compile_and_only_launches_once_without_completion_claim(scope, monkeypatch):
    sources = prepare_compile(scope, monkeypatch)
    calls = fake_transport(monkeypatch, raw=ops.canonical({"success": True, "backtest": {"backtestId": "backtest-1"}}))
    result = ops.launch_backtest("case0", 1, "compile-1", "synthetic-run", sources)
    assert result["backtest"]["backtestId"] == "backtest-1"
    spent = body(scope.private / "case0.attempt.1.backtest.spent.json")
    assert spent["development_look_consumed"] is True
    terminal = body(scope.private / "case0.attempt.1.backtest.terminal.json")
    assert terminal["backtest_id"] == "backtest-1" and terminal["completed"] is False
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.launch_backtest("case0", 1, "compile-1", "synthetic-run", sources)
    assert sum(row[0] == "request" for row in calls) == 1


def test_backtest_rejects_different_compile_before_stage_spend(scope, monkeypatch):
    sources = prepare_compile(scope, monkeypatch)
    with pytest.raises(ops.Refusal, match="compile/name binding mismatch"):
        ops.launch_backtest("case0", 1, "unrelated-compile", "synthetic-run", sources)
    assert not (scope.private / "case0.attempt.1.backtest.spent.json").exists()


def test_backtest_failure_preserves_attempt_look_and_terminal(scope, monkeypatch):
    sources = prepare_compile(scope, monkeypatch)
    fake_transport(monkeypatch, raw=ops.canonical({"success": False, "errors": ["synthetic runtime refusal"]}))
    with pytest.raises(ops.Refusal, match="attempt and look remain consumed"):
        ops.launch_backtest("case0", 1, "compile-1", "synthetic-run", sources)
    assert body(scope.private / "case0.attempt.1.backtest.terminal.json")["status"] == "failed_or_uncertain"
    assert body(scope.private / "case0.attempt.1.backtest.spent.json")["development_look_consumed"] is True


def test_launch_context_cannot_replay_a_previously_consumed_transport(scope, monkeypatch):
    sources = prepare_compile(scope, monkeypatch)
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.post("compile/create", {"projectId": 41}, _stage_context=("case0", 1, "compile"))
    assert len(list(scope.private.glob("request.*.terminal.json"))) == 1


def plaintext_packet(scope, monkeypatch):
    from research.target_price_revisions_qc import packet
    monkeypatch.setattr(packet, "FREEZE_SHA256", ops.FREEZE_HASH)
    monkeypatch.setattr(packet, "FROZEN_STRUCTURE_SHA256", ops.SOURCE_HASH)
    identity = {"security_id": "SHARADAR:1000", "ticker": "SYN", "eligible": True, "reason": "eligible"}
    value = {"schema": "tpr-qc-six-signals-v1", "candidate_id": packet.FAMILY_ID,
        "freeze_sha256": ops.FREEZE_HASH,
        "source_hashes": dict(packet.FROZEN_SOURCE_HASHES, **{"structure.json": ops.SOURCE_HASH}),
        "identities": [identity], "frames": [{"session": session, "cutoff_utc": cutoff,
            "states": [{"security_id": "SHARADAR:1000", "state": "unknown_input", "score": None,
                        "reasons": ["no_source_rating_rows"]}]} for session, cutoff in zip(packet.SESSIONS, packet.CUTOFFS)]}
    packet.validate_packet(value)
    return ops.canonical(value)


def test_plaintext_upload_has_fixed_org_key_multipart_and_single_family_reservation(scope, monkeypatch):
    ops.prepare_access()
    register()
    raw = plaintext_packet(scope, monkeypatch)
    calls = fake_transport(monkeypatch)
    result = ops.upload_packet("case0", raw)
    expected_key = "tpr-qc6/TPR-QC6-20261008-v1/" + ops.digest(raw) + ".json"
    assert result["key"] == expected_key and result["status"] == "uploaded"
    request = next(row for row in calls if row[0] == "request")
    assert request[1] == ("POST", "/api/v2/object/set")
    wire = request[2]["body"]
    assert b'name="organizationId"' in wire and b"synthetic-organization" in wire
    assert b'name="key"' in wire and expected_key.encode() in wire
    assert b'name="objectData"' in wire and raw in wire
    assert request[2]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.upload_packet("case0", raw)
    assert sum(row[0] == "request" for row in calls) == 1


@pytest.mark.parametrize("mutation", ["bad_org", "not_owner", "wrong_source", "wrong_freeze", "arbitrary_json", "oversize"])
def test_plaintext_upload_refuses_unbound_input_before_spend(scope, monkeypatch, mutation):
    ops.prepare_access()
    register()
    raw = plaintext_packet(scope, monkeypatch)
    if mutation in {"bad_org", "not_owner"}:
        project = body(scope.private / "case0.project.json")
        project["organization_id" if mutation == "bad_org" else "owner"] = None
        (scope.private / "case0.project.json").write_bytes(ops.canonical(project))
    elif mutation in {"wrong_source", "wrong_freeze"}:
        value = json.loads(raw)
        if mutation == "wrong_source":
            value["source_hashes"]["structure.json"] = "f" * 64
        else:
            value["freeze_sha256"] = "f" * 64
        raw = ops.canonical(value)
    elif mutation == "arbitrary_json":
        raw = b'{"not":"a packet"}\n'
    else:
        raw = b"x" * (16 * 1024 * 1024 + 1)
    with pytest.raises(ops.Refusal):
        ops.upload_packet("case0", raw)
    assert not (scope.private / "packet-upload.spent.json").exists()


def test_upload_failure_has_terminal_and_no_repeated_upload(scope, monkeypatch):
    ops.prepare_access()
    register()
    raw = plaintext_packet(scope, monkeypatch)
    with pytest.raises(ops.Refusal, match="no implicit retry"):
        ops.upload_packet("case0", raw)
    assert body(scope.private / "packet-upload.terminal.json")["status"] == "failed_or_uncertain"
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.upload_packet("case0", raw)


def test_project_typed_transport_is_single_use_and_cannot_create_arbitrary_name(scope, monkeypatch):
    ops.prepare_access()
    calls = fake_transport(monkeypatch, raw=ops.canonical(project_response()))
    assert ops.create_project("case0")["project_id"] == 41
    assert (scope.private / "case0.project-create.transport-spent.json").exists()
    with pytest.raises(ops.Refusal, match="binding mismatch"):
        ops.post("projects/create", {"name": "arbitrary", "language": "Py"}, _project_context="case0")
    with pytest.raises(ops.Refusal, match="already reserved"):
        ops.post("projects/create", {"name": "SYNTHETIC-CANDIDATE-0-private", "language": "Py"}, _project_context="case0")
    assert sum(row[0] == "request" for row in calls) == 1


def test_private_transport_refuses_unknown_endpoint_even_with_valid_scope(scope):
    ops.prepare_access()
    with pytest.raises(ops.Refusal, match="outside scoped"):
        ops._request("live/create", b"{}", "application/json")
    assert list(scope.private.glob("request.*")) == []
