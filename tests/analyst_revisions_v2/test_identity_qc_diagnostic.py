"""Offline R284 controls: fake QC responses and generated runtime only."""
from __future__ import annotations

import ast
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from research.quantconnect import QuantConnectClient, QuantConnectCredentials
from scripts import run_arv2_identity_qc as subject


@pytest.fixture
def package(tmp_path, monkeypatch):
    artifact_root = tmp_path / "private-artifacts"
    artifact_root.mkdir(mode=0o700)
    monkeypatch.setattr(subject, "ARTIFACT_ROOT", artifact_root)
    value = {"schema": subject.INPUT_SCHEMA,
             "rows": [{"ticker": ticker, "role": subject.ROLES[ticker], "composite_figi": f"BBG{index:09d}"}
                      for index, ticker in enumerate(subject.TICKERS, 1)],
             "price_manifest_sha256": "1" * 64, "public_reference_sha256": "2" * 64,
             "sharadar_identity_manifest_sha256": "3" * 64}
    raw = subject.canonical(value)
    input_path = tmp_path / "public-input.json"
    input_path.write_bytes(raw)
    input_path.chmod(0o600)
    control = artifact_root / "r284-a1"
    prepared = subject.prepare(input_path, subject.sha(raw), control)
    return SimpleNamespace(value=value, raw=raw, input=input_path, control=control,
                           prepared=prepared, pin=subject.sha(subject.canonical(prepared)))


class Sid:
    def __init__(self, value, market="usa"):
        self.value, self.market = value, market

    def __eq__(self, other):
        return isinstance(other, Sid) and self.value == other.value

    def __str__(self):
        raise AssertionError("No mapped SID may be rendered")


class Runtime:
    live_mode = False
    forward = {}
    reverse = {}

    def __init__(self):
        self.settings = SimpleNamespace(seed_initial_prices=True)
        self.operations, self.statistics = [], {}

    def set_time_zone(self, *args):
        self.operations.append(("timezone", args))

    def set_start_date(self, *args):
        self.operations.append(("start", args))

    def set_end_date(self, *args):
        self.operations.append(("end", args))

    def set_cash(self, *args):
        self.operations.append(("cash", args))

    def set_benchmark(self, benchmark):
        assert benchmark(None) == 1
        self.operations.append(("constant_benchmark", (1,)))

    def composite_figi(self, value):
        if type(value) is str:
            result = self.forward.get(value)
        else:
            result = self.reverse[id(value)]
        if isinstance(result, Exception):
            raise result
        return result

    def set_summary_statistic(self, name, value):
        self.statistics[name] = value


def run_runtime(package, monkeypatch, change=None):
    forwards, backwards = {}, {}
    for index, row in enumerate(package.value["rows"]):
        symbol = SimpleNamespace(id=Sid(f"PRIVATE_QC_SID_{index}"), security_type="equity")
        forwards[row["composite_figi"]] = symbol
        backwards[id(symbol)] = row["composite_figi"]
    if change:
        change(forwards, backwards)
    module = ModuleType("AlgorithmImports")
    module.QCAlgorithm = Runtime
    module.Market = SimpleNamespace(USA="usa")
    module.SecurityType = SimpleNamespace(EQUITY="equity")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", module)
    monkeypatch.setattr(Runtime, "forward", forwards)
    monkeypatch.setattr(Runtime, "reverse", backwards)
    namespace = {}
    exec(compile((package.control / "main.py").read_bytes(), "synthetic-public-runtime", "exec"), namespace)
    instance = namespace["ARV2PublicSevenIdentity"]()
    instance.initialize()
    instance.on_end_of_algorithm()
    meta = subject.validate_meta(instance.statistics[subject.META_NAME], package.prepared)
    return instance, meta


class FakeQc:
    project_id = 12345
    organization = "a" * 32
    compile_id = "compile-r284"
    backtest_id = "b" * 32

    def __init__(self, package, meta):
        self.package, self.meta = package, meta
        self.calls, self.responses = [], []
        self.files = {"main.py": "# initial default", "research.ipynb": "{}"}
        self.state, self.compile_states = "In Queue...", ["InQueue", "BuildSuccess"]
        self.change = None

    def project(self, project_id):
        return {"projectId": project_id,
                "name": subject.PROJECT_NAME if project_id == self.project_id else "reference only",
                "organizationId": self.organization, "owner": True,
                "codeRunning": False, "collaborators": [{"owner": True}]}

    def backtest(self):
        return {"projectId": self.project_id, "backtestId": self.backtest_id,
                "name": subject.BACKTEST_NAME, "status": self.state}

    def __call__(self, url, body, headers, timeout):
        assert url.startswith("https://www.quantconnect.com/api/v2/")
        assert type(timeout) is float and timeout > 0
        endpoint = url.split("/api/v2/", 1)[1]
        payload = json.loads(body)
        self.calls.append((endpoint, payload))
        response = {"success": True}
        if endpoint == "authenticate":
            assert payload == {}
        elif endpoint == "projects/read":
            assert payload["projectId"] in (subject.REFERENCE_PROJECT_ID, self.project_id)
            response["projects"] = [self.project(payload["projectId"])]
        elif endpoint == "projects/create":
            assert payload == {"name": subject.PROJECT_NAME, "language": "Py", "organizationId": self.organization}
            response["projects"] = [self.project(self.project_id)]
        elif endpoint == "files/read":
            assert payload == {"projectId": self.project_id}
            response["files"] = [{"name": name, "content": content} for name, content in self.files.items()]
        elif endpoint == "files/delete":
            assert payload == {"projectId": self.project_id, "name": "research.ipynb"}
            del self.files["research.ipynb"]
        elif endpoint == "files/update":
            assert payload["projectId"] == self.project_id and payload["name"] == "main.py"
            self.files["main.py"] = payload["content"]
        elif endpoint == "compile/create":
            assert payload == {"projectId": self.project_id}
            response.update(projectId=self.project_id, compileId=self.compile_id, state="InQueue")
        elif endpoint == "compile/read":
            assert payload == {"projectId": self.project_id, "compileId": self.compile_id}
            response.update(compileId=self.compile_id, state=self.compile_states.pop(0) if len(self.compile_states) > 1 else self.compile_states[0])
        elif endpoint == "backtests/create":
            assert payload == {"projectId": self.project_id, "compileId": self.compile_id, "backtestName": subject.BACKTEST_NAME}
            response["backtest"] = self.backtest()
        elif endpoint == "backtests/list":
            assert payload == {"projectId": self.project_id, "includeStatistics": False}
            response.update(count=1, backtests=[self.backtest()])
        elif endpoint == "backtests/read":
            assert payload == {"projectId": self.project_id, "backtestId": self.backtest_id}
            response["backtest"] = {**self.backtest(), "completed": True, "hasInitializeError": False,
                                    "statistics": {subject.META_NAME: subject.canonical(self.meta).decode("ascii"),
                                                   "Total Orders": "UNINSPECTED_ECONOMIC_SENTINEL"},
                                    "charts": {"private remote chart": "UNINSPECTED_CLOUD_IDENTIFIER"}}
        else:
            raise AssertionError("Unexpected endpoint")
        if self.change:
            self.change(endpoint, payload, response)
        self.responses.append(copy.deepcopy(response))
        return 200, json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=True).encode("ascii")


@pytest.fixture
def qc(package, monkeypatch):
    _, meta = run_runtime(package, monkeypatch)
    fake = FakeQc(package, meta)
    monkeypatch.setattr(subject.boundary, "_default_http_transport", fake)
    monkeypatch.setattr(subject.time, "sleep", lambda seconds: None)
    api = QuantConnectClient(QuantConnectCredentials("synthetic-user", "synthetic-token"),
                             transport=subject.boundary._bounded_transport, clock=lambda: 1791331200)
    return SimpleNamespace(fake=fake, api=api)


def completed(package, qc):
    receipt = subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    terminal = subject.status(package.control, package.pin, qc.api)
    return receipt, terminal


def assert_no_result(package):
    assert not (package.control / "result.json").exists()


def test_prepare_is_offline_private_pinned(package, monkeypatch):
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No credentials or client before launch"))
    monkeypatch.setattr(subject, "_instant", lambda: pytest.fail("No clock before launch"))
    second = package.control.with_name("offline-second")
    result = subject.prepare(package.input, subject.sha(package.raw), second)
    assert {key: value for key, value in result.items() if key != "control_directory"} == {key: value for key, value in package.prepared.items() if key != "control_directory"}
    second_pin = subject.sha(subject.canonical(result))
    assert second_pin != package.pin and result["control_directory"] == str(second)
    assert set(path.name for path in second.iterdir()) == {"input.json", "main.py", "prepared.json", "prepared.sha256", "prepared-complete.json"}
    assert stat.S_IMODE(second.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in second.iterdir())
    with subject._Directory(second) as directory:
        prepared, source = subject._prepared(directory, second_pin)
    assert prepared == result and subject.sha(source) == result["source_sha256"]
    assert subject.source_template_sha256(source) == result["source_template_sha256"]


@pytest.mark.parametrize("change", [
    lambda value: value.update(schema="wrong"),
    lambda value: value.update(price_manifest_sha256="not-a-hash"),
    lambda value: value.update(raw_sharadar_rows=[]),
    lambda value: value["rows"].pop(),
    lambda value: value["rows"][0].update(role="fund"),
    lambda value: value["rows"][1].update(ticker="QCOM", role="stock"),
    lambda value: value["rows"][0].update(composite_figi="lower-case"),
    lambda value: value["rows"][1].update(composite_figi=value["rows"][0]["composite_figi"]),
    lambda value: value["rows"][0].update(closeunadj=123.45),
])
def test_input_refuses_unpinned_or_nonpublic_row_shape(package, change):
    value = copy.deepcopy(package.value)
    change(value)
    raw = subject.canonical(value)
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(raw, subject.sha(raw))


@pytest.mark.parametrize("raw", [b"{} ", b'{"schema":"x","schema":"y"}', b'{"x":NaN}', b'\xff'])
def test_noncanonical_or_ambiguous_json_refused(raw):
    with pytest.raises(subject.IdentityQcError):
        subject._json(raw)


def test_input_byte_pin_refused(package):
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(package.raw, "0" * 64)


def test_generated_source_identical_across_python_hash_seeds(package):
    code = ("import sys; from scripts import run_arv2_identity_qc as s; "
            "raw=sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(s.render_source(s.validate_input(raw,s.sha(raw)),s.sha(raw)))")
    results = []
    for seed in ("1", "98765", "random"):
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run([sys.executable, "-c", code], input=package.raw, capture_output=True,
                                check=True, env=environment, cwd=Path(subject.__file__).absolute().parents[1])
        assert result.stderr == b""
        results.append(result.stdout)
    assert results[0] == results[1] == results[2] == (package.control / "main.py").read_bytes()


def test_runtime_seven_roundtrips_no_market_or_identifier_export(package, monkeypatch):
    instance, meta = run_runtime(package, monkeypatch)
    assert meta["matched_count"] == 7 and meta["refused_count"] == 0
    assert [row["ticker"] for row in meta["rows"]] == list(subject.TICKERS)
    assert all(meta[key] is False for key in subject._FALSE_FLAGS)
    assert instance.settings.seed_initial_prices is False
    assert instance.operations == [("timezone", ("America/New_York",)), ("start", (2026, 10, 7)),
                                   ("end", (2026, 10, 7)), ("cash", (1000000,)), ("constant_benchmark", (1,))]
    encoded = subject.canonical(meta)
    for row in package.value["rows"]:
        assert row["composite_figi"].encode("ascii") not in encoded
    assert b"PRIVATE_QC_SID" not in encoded
    source = (package.control / "main.py").read_bytes()
    calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)]
    forbidden = {"add_equity", "history", "market_order", "set_holdings", "download", "log", "debug", "error", "str", "hash"}
    assert all(not isinstance(node.func, ast.Attribute) or node.func.attr not in forbidden for node in calls)
    assert all(not isinstance(node.func, ast.Name) or node.func.id not in forbidden for node in calls)


@pytest.mark.parametrize("kind,expected,count", [("unavailable", "resolution_unavailable", 6),
                                                   ("forward_exception", "mapping_exception", 6),
                                                   ("reverse_exception", "mapping_exception", 6),
                                                   ("wrong_market", "not_usa_equity", 6),
                                                   ("wrong_type", "not_usa_equity", 6),
                                                   ("wrong_reverse", "reverse_figi_mismatch", 6),
                                                   ("collision", "sid_collision", 5)])
def test_runtime_named_refusals_and_collision_no_identifier_text(package, monkeypatch, kind, expected, count):
    first_figi, second_figi = [row["composite_figi"] for row in package.value["rows"][:2]]
    def change(forwards, backwards):
        first = forwards[first_figi]
        if kind == "unavailable":
            forwards[first_figi] = None
        elif kind == "forward_exception":
            forwards[first_figi] = ValueError("PRIVATE_QC_SID_EXCEPTION")
        elif kind == "reverse_exception":
            backwards[id(first)] = ValueError("PRIVATE_QC_FIGI_EXCEPTION")
        elif kind == "wrong_market":
            first.id.market = "eur"
        elif kind == "wrong_type":
            first.security_type = "option"
        elif kind == "wrong_reverse":
            backwards[id(first)] = "PRIVATE_WRONG_FIGI"
        else:
            forwards[second_figi].id = first.id
    _, meta = run_runtime(package, monkeypatch, change)
    assert meta["rows"][0]["reason"] == expected
    assert meta["matched_count"] == count
    if kind == "collision":
        assert meta["rows"][1]["reason"] == "sid_collision"
    assert b"PRIVATE_" not in subject.canonical(meta)


def test_runtime_live_refused(package, monkeypatch):
    monkeypatch.setattr(Runtime, "live_mode", True)
    with pytest.raises(ValueError, match="R284 live mode refused"):
        run_runtime(package, monkeypatch)


def test_launch_status_read_exact_chain_and_sanitized_observations(package, qc):
    receipt, terminal = completed(package, qc)
    result = subject.read(package.control, package.pin, qc.api)
    assert terminal["status"] == "Completed." and result["metadata"]["matched_count"] == 7
    assert receipt["source_sha256"] == package.prepared["source_sha256"]
    assert receipt["source_template_sha256"] == package.prepared["source_template_sha256"]
    assert qc.fake.files == {"main.py": (package.control / "main.py").read_text("ascii")}
    expected = ["authenticate", "projects/read", "projects/create", "projects/read", "files/read", "files/delete", "files/update", "files/read", "compile/create", "compile/read", "compile/read", "files/read", "backtests/create", "backtests/list", "backtests/read"]
    assert [endpoint for endpoint, _ in qc.fake.calls] == expected
    assert all(payload.get("projectId") == qc.fake.project_id for endpoint, payload in qc.fake.calls
               if "projectId" in payload and not (endpoint == "projects/read" and payload["projectId"] == subject.REFERENCE_PROJECT_ID))
    for index, response in enumerate(qc.fake.responses, 1):
        observation = json.loads((package.control / f"observation-{index:03d}.json").read_bytes())
        assert observation["parsed_response_sha256"] == subject.sha(subject.canonical(response))
        assert observation["server_time_authenticated"] is False and observation["operator_authenticated"] is False
        assert observation["wall_clock_ordered"] is True and observation["monotonic_elapsed_ns"] >= 0
        assert subject._utc(observation["client_end_utc"]) >= subject._utc(observation["client_start_utc"])
        assert not {"body", "response", "statistics", "headers", "source", "files", "logs"} & set(observation)
    persisted = b"".join(path.read_bytes() for path in package.control.iterdir() if path.name not in {"input.json", "main.py"})
    assert b"UNINSPECTED_ECONOMIC_SENTINEL" not in persisted and b"UNINSPECTED_CLOUD_IDENTIFIER" not in persisted
    assert b"synthetic-user" not in persisted and b"synthetic-token" not in persisted
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in package.control.iterdir())
    calls = len(qc.fake.calls)
    assert subject.status(package.control, package.pin, qc.api) == terminal
    assert len(qc.fake.calls) == calls
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    with pytest.raises(subject.IdentityQcError):
        subject.read(package.control, package.pin, qc.api)
    assert len(qc.fake.calls) == calls


def test_claim_spent_before_client_or_any_network(package, qc, monkeypatch):
    def reject():
        assert (package.control / "attempt-claim.json").is_file()
        raise RuntimeError("SECRET_EXCEPTION_NOT_FOR_OPERATOR")
    monkeypatch.setattr(subject.boundary, "production_client", reject)
    with pytest.raises(RuntimeError):
        subject.launch(package.control, package.pin)
    assert qc.fake.calls == []
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert qc.fake.calls == []


@pytest.mark.parametrize("file", ["main.py", "input.json", "prepared.json", "prepared.sha256", "prepared-complete.json"])
def test_prepare_tamper_stops_before_claim_or_contact(package, qc, file):
    path = package.control / file
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert qc.fake.calls == [] and not (package.control / "attempt-claim.json").exists()


@pytest.mark.parametrize("defect", ["symlink", "hardlink", "permissions", "fifo"])
def test_control_file_boundaries(package, qc, defect):
    path = package.control / "main.py"
    if defect == "symlink":
        path.unlink()
        path.symlink_to(package.input)
    elif defect == "hardlink":
        os.link(path, package.control / "other.py")
    elif defect == "permissions":
        path.chmod(0o644)
    else:
        path.unlink()
        os.mkfifo(path, 0o600)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert qc.fake.calls == []


@pytest.mark.parametrize("defect", ["outside_root", "symlink", "permissions"])
def test_control_directory_boundaries(package, qc, defect):
    control = package.control
    if defect == "outside_root":
        control = package.input.parent / "elsewhere"
    elif defect == "symlink":
        control = package.control.with_name("link")
        control.symlink_to(package.control)
    else:
        package.control.chmod(0o755)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(control, package.pin, qc.api)
    assert qc.fake.calls == []


def test_directory_identity_and_permission_change_refused(package):
    with subject._Directory(package.control) as directory:
        package.control.chmod(0o755)
        with pytest.raises(subject.IdentityQcError):
            directory.names()


def test_ancestor_directory_symlink_swap_refused(package):
    original = package.control.parent
    moved = original.with_name("moved-private-artifacts")
    with subject._Directory(package.control) as directory:
        original.rename(moved)
        original.symlink_to(moved)
        with pytest.raises(subject.IdentityQcError):
            directory.names()


def test_identical_prepared_package_cannot_replay_in_new_directory(package, qc):
    replay = package.control.with_name("copied-r284-a1")
    shutil.copytree(package.control, replay)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(replay, package.pin, qc.api)
    assert qc.fake.calls == [] and not (replay / "attempt-claim.json").exists()


@pytest.mark.parametrize("defect", ["base_url", "transport", "request_override", "subclass"])
def test_client_identity_cannot_be_relaxed(package, qc, defect):
    api = qc.api
    if defect == "base_url":
        api._base_url = "https://different.example"
    elif defect == "transport":
        api._transport = qc.fake
    elif defect == "request_override":
        api.request = lambda *args: {"success": True}
    else:
        class Child(QuantConnectClient):
            pass
        api = Child(QuantConnectCredentials("synthetic", "token"), transport=subject.boundary._bounded_transport)
    with pytest.raises((subject.IdentityQcError, subject.boundary.CoverageQcSubmissionError)):
        subject.launch(package.control, package.pin, api)
    assert (package.control / "attempt-claim.json").is_file() and qc.fake.calls == []


@pytest.mark.parametrize("kind,endpoint", [("reference_wrong_id", "projects/read"),
                                         ("reference_not_owner", "projects/read"),
                                         ("fresh_collaborator", "projects/read"),
                                         ("fresh_running", "projects/read"),
                                         ("fresh_wrong_org", "projects/read"),
                                         ("unexpected_file", "files/read"),
                                         ("source_changed", "files/read"),
                                         ("compile_wrong_id", "compile/read"),
                                         ("compile_wrong_project", "compile/create"),
                                         ("compile_error", "compile/read"),
                                         ("create_wrong_run_name", "backtests/create")])
def test_remote_identity_source_and_compile_guards(package, qc, kind, endpoint):
    def change(actual, payload, response):
        if actual != endpoint:
            return
        if kind.startswith("reference") and payload.get("projectId") == subject.REFERENCE_PROJECT_ID:
            response["projects"][0]["projectId" if kind == "reference_wrong_id" else "owner"] = 98765 if kind == "reference_wrong_id" else False
        elif kind.startswith("fresh") and payload.get("projectId") == qc.fake.project_id:
            row = response["projects"][0]
            if kind == "fresh_collaborator":
                row["collaborators"].append({"owner": False})
            elif kind == "fresh_running":
                row["codeRunning"] = True
            else:
                row["organizationId"] = "c" * 32
        elif kind == "unexpected_file":
            response["files"].append({"name": "foreign.py", "content": ""})
        elif kind == "source_changed" and "research.ipynb" not in qc.fake.files:
            response["files"][0]["content"] += "# foreign edit"
        elif kind == "compile_wrong_id":
            response["compileId"] = "other-compile"
        elif kind == "compile_wrong_project":
            response["projectId"] = 98765
        elif kind == "compile_error":
            response["state"] = "BuildError"
        elif kind == "create_wrong_run_name":
            response["backtest"]["name"] = "other-run"
    qc.fake.change = change
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert (package.control / "attempt-claim.json").exists()
    calls = len(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert len(qc.fake.calls) == calls
    assert not (package.control / "launch.json").exists()


def test_compile_poll_budget_never_creates_backtest(package, qc, monkeypatch):
    monkeypatch.setattr(subject, "MAX_COMPILE_POLLS", 2)
    qc.fake.compile_states = ["InQueue"]
    with pytest.raises(subject.IdentityQcError, match="compile_poll_budget"):
        subject.launch(package.control, package.pin, qc.api)
    assert sum(endpoint == "compile/read" for endpoint, _ in qc.fake.calls) == 2
    assert not any(endpoint == "backtests/create" for endpoint, _ in qc.fake.calls)


def test_project_create_must_not_reuse_old_reference_identity(package, qc):
    def change(endpoint, payload, response):
        if endpoint == "projects/create":
            response["projects"][0]["projectId"] = subject.REFERENCE_PROJECT_ID
    qc.fake.change = change
    with pytest.raises(subject.IdentityQcError, match="new_project_reused_reference_id"):
        subject.launch(package.control, package.pin, qc.api)
    assert [endpoint for endpoint, _ in qc.fake.calls] == ["authenticate", "projects/read", "projects/create"]
    assert (package.control / "attempt-claim.json").exists()
    assert not (package.control / "project-created.json").exists()
    assert not any(endpoint in {"files/delete", "files/update", "compile/create", "backtests/create"} for endpoint, _ in qc.fake.calls)


def test_concurrent_cloud_source_change_after_compile_refused_before_run(package, qc):
    def change(endpoint, payload, response):
        if endpoint == "compile/read" and response["state"] == "BuildSuccess":
            qc.fake.files["main.py"] += "# concurrent cloud owner edit"
    qc.fake.change = change
    with pytest.raises(subject.IdentityQcError, match="cloud_source_changed_after_compile"):
        subject.launch(package.control, package.pin, qc.api)
    assert not any(endpoint == "backtests/create" for endpoint, _ in qc.fake.calls)
    assert not (package.control / "backtest-create-claim.json").exists()


@pytest.mark.parametrize("field,wrong", [("attempt", True), ("project_id", "12345"), ("source_sha256", "4" * 64)])
def test_local_launch_receipt_binding_type_sensitive(package, qc, field, wrong):
    subject.launch(package.control, package.pin, qc.api)
    path = package.control / "launch.json"
    value = json.loads(path.read_bytes())
    value[field] = wrong
    path.write_bytes(subject.canonical(value))
    calls = len(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert len(qc.fake.calls) == calls


def test_status_poll_budget_and_no_completed_result_before_terminal(package, qc, monkeypatch):
    subject.launch(package.control, package.pin, qc.api)
    with pytest.raises(subject.IdentityQcError):
        subject.read(package.control, package.pin, qc.api)
    assert not (package.control / "result-read-claim.json").exists()
    monkeypatch.setattr(subject, "MAX_STATUS_POLLS", 1)
    subject.status(package.control, package.pin, qc.api)
    with pytest.raises(subject.IdentityQcError, match="status_poll_budget"):
        subject.status(package.control, package.pin, qc.api)
    assert sum(endpoint == "backtests/list" for endpoint, _ in qc.fake.calls) == 1


@pytest.mark.parametrize("kind", ["run_id", "run_name", "project_id", "duplicate", "foreign_run", "count", "state"])
def test_status_exact_fresh_project_inventory(package, qc, kind):
    subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    def change(endpoint, payload, response):
        if endpoint != "backtests/list":
            return
        rows = response["backtests"]
        if kind == "run_id":
            rows[0]["backtestId"] = "other-run"
        elif kind == "run_name":
            rows[0]["name"] = "other-name"
        elif kind == "project_id":
            rows[0]["projectId"] = 98765
        elif kind in ("duplicate", "foreign_run"):
            rows.append({**rows[0], "backtestId": "other-run" if kind == "foreign_run" else rows[0]["backtestId"]})
            response["count"] = 2
        elif kind == "count":
            response["count"] = True
        else:
            rows[0]["status"] = "unknown"
    qc.fake.change = change
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert not (package.control / "terminal.json").exists()


@pytest.mark.parametrize("field,wrong", [("attempt", True), ("source_template_sha256", "4" * 64),
                                       ("price_manifest_sha256", "4" * 64), ("decision_ready", 0),
                                       ("orders_authorized", True), ("input_count", True),
                                       ("matched_count", 6), ("rows", [])])
def test_metadata_binding_counts_and_false_flags_strict(package, qc, field, wrong):
    value = copy.deepcopy(qc.fake.meta)
    value[field] = wrong
    with pytest.raises(subject.IdentityQcError):
        subject.validate_meta(subject.canonical(value).decode("ascii"), package.prepared)


@pytest.mark.parametrize("field,wrong", [("ticker", "QCOM_ALIAS"), ("role", "fund"), ("matched", 1),
                                       ("reason", "invented"), ("reason", []), ("matched", False)])
def test_metadata_exact_named_row_schema(package, qc, field, wrong):
    value = copy.deepcopy(qc.fake.meta)
    value["rows"][0][field] = wrong
    with pytest.raises(subject.IdentityQcError):
        subject.validate_meta(subject.canonical(value).decode("ascii"), package.prepared)


@pytest.mark.parametrize("kind", ["metadata_missing", "metadata_bad", "metadata_remote_identifiers", "wrong_run", "runtime_error", "initialize_error", "completed_false", "backtest_error", "nonfinite_platform_field", "transport_failure"])
def test_result_read_spent_after_every_failure_no_fresh_result(package, qc, kind):
    completed(package, qc)
    def change(endpoint, payload, response):
        if endpoint != "backtests/read":
            return
        row = response["backtest"]
        if kind == "metadata_missing":
            row["statistics"].pop(subject.META_NAME)
        elif kind == "metadata_bad":
            row["statistics"][subject.META_NAME] = "not-json"
        elif kind == "metadata_remote_identifiers":
            value = copy.deepcopy(qc.fake.meta)
            value["rows"][0]["sid"] = "PRIVATE_REMOTE_SID"
            row["statistics"][subject.META_NAME] = subject.canonical(value).decode("ascii")
        elif kind == "wrong_run":
            row["backtestId"] = "other-run"
        elif kind == "runtime_error":
            row["status"] = "Runtime Error"
        elif kind == "initialize_error":
            row["hasInitializeError"] = True
        elif kind == "completed_false":
            row["completed"] = False
        elif kind == "backtest_error":
            row["error"] = "private remote exception"
        elif kind == "nonfinite_platform_field":
            row["charts"]["nan"] = float("nan")
        else:
            raise RuntimeError("PRIVATE_TRANSPORT_ERROR")
    qc.fake.change = change
    with pytest.raises((subject.IdentityQcError, subject.boundary.CoverageQcSubmissionError)):
        subject.read(package.control, package.pin, qc.api)
    assert_no_result(package)
    assert (package.control / "result-read-claim.json").is_file()
    calls = len(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.read(package.control, package.pin, qc.api)
    assert len(qc.fake.calls) == calls


@pytest.mark.parametrize("kind", ["backward_wall", "naive_start", "nonutc_start", "backward_monotonic"])
def test_observation_clock_failure_no_fresh_terminal(package, qc, monkeypatch, kind):
    subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    values = {"backward_wall": ["2026-10-07T10:00:01+00:00", "2026-10-07T10:00:00+00:00"],
              "naive_start": ["2026-10-07T10:00:00", "2026-10-07T10:00:01+00:00"],
              "nonutc_start": ["2026-10-07T10:00:00-07:00", "2026-10-07T10:00:01+00:00"],
              "backward_monotonic": ["2026-10-07T10:00:00+00:00", "2026-10-07T10:00:01+00:00"]}[kind]
    stamps = iter(values)
    monkeypatch.setattr(subject, "_instant", lambda: next(stamps))
    if kind == "backward_monotonic":
        ticks = iter((2, 1))
        monkeypatch.setattr(subject.time, "monotonic_ns", lambda: next(ticks))
    before = len(list(package.control.glob("observation-*.json")))
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert not (package.control / "terminal.json").exists()
    assert len(list(package.control.glob("observation-*.json"))) == before
    assert (package.control / "status-claim-001.json").exists()


def test_observation_persistence_failure_blocks_fresh_terminal(package, qc, monkeypatch):
    subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    original = subject._Directory.write
    def deny(self, name, raw):
        if name.startswith("observation-"):
            subject._fail("control_write")
        return original(self, name, raw)
    monkeypatch.setattr(subject._Directory, "write", deny)
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert not (package.control / "terminal.json").exists()
    assert (package.control / "status-claim-001.json").exists()


def test_cli_refusal_code_and_foreign_exception_redaction(package, monkeypatch, capsys):
    args = ["launch", "--control-directory", str(package.control), "--prepared-sha256", package.pin]
    monkeypatch.setattr(subject, "launch", lambda *args: subject._fail("compile_failed"))
    assert subject.main(args) == 2
    assert capsys.readouterr().out == "R284 refused: compile_failed; existing one-use claims remain spent\n"
    def foreign(*args):
        raise RuntimeError("SECRET_REMOTE_DETAIL")
    monkeypatch.setattr(subject, "launch", foreign)
    assert subject.main(args) == 2
    assert capsys.readouterr().out == "R284 operation refused; existing one-use claims remain spent\n"
