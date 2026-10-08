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
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from scripts import run_arv2_identity_qc as subject


@pytest.fixture(params=(subject.INPUT_SCHEMA, subject.CONTINUITY_INPUT_SCHEMA), ids=("v1", "continuity_v2"))
def package(tmp_path, monkeypatch, request):
    artifact_root = tmp_path / "private-artifacts"
    artifact_root.mkdir(mode=0o700)
    monkeypatch.setattr(subject, "ARTIFACT_ROOT", artifact_root)
    value = {"schema": request.param,
             "rows": [{"ticker": ticker, "role": subject.ROLES[ticker], "composite_figi": f"BBG{index:09d}"}
                      for index, ticker in enumerate(subject.TICKERS, 1)],
             "price_manifest_sha256": "1" * 64, "public_reference_sha256": "2" * 64,
             "sharadar_identity_manifest_sha256": "3" * 64}
    if request.param == subject.CONTINUITY_INPUT_SCHEMA:
        # Exercise a genuinely published synthetic builder package, not an
        # invented input dictionary or a patched authentication boundary.
        from . import test_identity_continuity as producer
        pins = producer.fixture(tmp_path)
        loaded = producer.build(tmp_path, pins)
        input_path = loaded.input_path
        raw = input_path.read_bytes()
        value = json.loads(raw)
    else:
        raw = subject.canonical_input(value)
        input_path = tmp_path / "public-input.json"
        input_path.write_bytes(raw)
        input_path.chmod(0o600)
    control = artifact_root / subject.CONTROL_LEAF
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
    production_api = subject._api
    # Synthetic published continuity fixtures cannot enter the real production
    # mode gate. This explicitly fake seam retains exact client-shape checks.
    def synthetic_api(candidate, prepared):
        if prepared["input_schema"] == subject.CONTINUITY_INPUT_SCHEMA:
            return subject._api_client(candidate)
        return production_api(candidate, prepared)
    monkeypatch.setattr(subject, "_api", synthetic_api)
    monkeypatch.setattr(subject.boundary, "production_client", lambda: api)
    return SimpleNamespace(fake=fake, api=api, production_api=production_api)


def completed(package, qc):
    receipt = subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    terminal = subject.status(package.control, package.pin, qc.api)
    return receipt, terminal


def assert_no_result(package):
    assert not (package.control / "result.json").exists()


def test_refused_continuity_leftover_cannot_be_prepared(tmp_path, monkeypatch):
    root = tmp_path / "qc-controls"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(subject, "ARTIFACT_ROOT", root)
    refused = tmp_path / "refused-continuity"
    refused.mkdir(mode=0o700)
    value = {"schema": subject.CONTINUITY_INPUT_SCHEMA,
             "rows": [{"ticker": ticker, "role": subject.ROLES[ticker], "composite_figi": f"BBG{index:09d}"}
                      for index, ticker in enumerate(subject.TICKERS, 1)],
             "price_manifest_sha256": "1" * 64, "public_reference_sha256": "2" * 64,
             "sharadar_identity_manifest_sha256": "3" * 64,
             "continuity_manifest_sha256": "4" * 64, "vintage_manifest_sha256": "5" * 64}
    raw = subject.canonical_input(value)
    input_path = refused / "input.json"
    input_path.write_bytes(raw)
    input_path.chmod(0o600)
    (refused / "manifest.sha256").write_bytes(b"4" * 64 + b"\n")
    (refused / "manifest.sha256").chmod(0o600)
    control = root / "R284A1-20261008"
    # Reproduce the rollback shape after the input write: no completion marker.
    assert not (refused / "manifest.json").exists()
    assert subject.validate_input(raw, subject.sha(raw)) == value
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No credentials on refusal"))
    with pytest.raises(subject.IdentityQcError):
        subject.prepare(input_path, subject.sha(raw), control)
    assert not control.exists()
    assert input_path.read_bytes() == raw and not (refused / "manifest.json").exists()


def test_second_r284_leaf_cannot_be_prepared(package, monkeypatch):
    second = package.control.with_name("R284A1-20261008-B")
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No client for another leaf"))
    with pytest.raises(subject.IdentityQcError):
        subject.prepare(package.input, subject.sha(package.raw), second)
    assert not second.exists()


@pytest.mark.parametrize("name", ["launch.json", "terminal.json", "result.json", "attempt-claim.json",
                                 "backtest-create-claim.json", "result-read-claim.json"])
def test_interrupted_control_write_never_publishes_partial_final(package, monkeypatch, name):
    original = subject.os.write
    calls = []
    def interrupted(fd, raw):
        calls.append(fd)
        if len(calls) == 1:
            return original(fd, raw[:1])
        raise OSError("synthetic interrupted control persistence")
    monkeypatch.setattr(subject.os, "write", interrupted)
    with subject._Directory(package.control) as directory:
        with pytest.raises(subject.IdentityQcError):
            directory.write(name, b'{"synthetic":"receipt"}')
        assert not (package.control / name).exists()
        assert (package.control / (name + ".pending")).read_bytes() == b"{"
        monkeypatch.setattr(subject.os, "write", original)
        with pytest.raises(subject.IdentityQcError):
            directory.write(name, b'{"synthetic":"receipt"}')
        assert not (package.control / name).exists()


def test_pending_attempt_blocks_restart_before_client_or_contact(package, qc, monkeypatch):
    pending = package.control / "attempt-claim.json.pending"
    pending.write_bytes(b"{")
    pending.chmod(0o600)
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No client after interrupted claim"))
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin)
    assert qc.fake.calls == [] and not (package.control / "attempt-claim.json").exists()
    assert pending.read_bytes() == b"{"


def test_control_publication_conflict_preserves_original_and_spends_pending(package, monkeypatch):
    original = subject.os.link
    target = package.control / "launch.json"
    def race(src, dst, **kwargs):
        target.write_bytes(b'{"synthetic":"other-complete"}')
        target.chmod(0o600)
        return original(src, dst, **kwargs)
    monkeypatch.setattr(subject.os, "link", race)
    with subject._Directory(package.control) as directory:
        with pytest.raises(subject.IdentityQcError):
            directory.write("launch.json", b'{"synthetic":"new"}')
    assert target.read_bytes() == b'{"synthetic":"other-complete"}'
    assert (package.control / "launch.json.pending").read_bytes() == b'{"synthetic":"new"}'


def test_crash_between_control_link_and_unlink_is_complete_but_refused(package, monkeypatch):
    original = subject.os.unlink
    def interrupted(name, *args, **kwargs):
        if name == "launch.json.pending":
            raise OSError("synthetic namespace interruption")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(subject.os, "unlink", interrupted)
    raw = b'{"synthetic":"complete"}'
    with subject._Directory(package.control) as directory:
        with pytest.raises(subject.IdentityQcError):
            directory.write("launch.json", raw)
        assert (package.control / "launch.json").read_bytes() == raw
        assert (package.control / "launch.json").stat().st_nlink == 2
        with pytest.raises(subject.IdentityQcError, match="private_file"):
            directory.read("launch.json")
        with pytest.raises(subject.IdentityQcError):
            directory.write("launch.json", raw)


def test_backtest_response_persistence_loss_retains_claims_and_never_retries(package, qc, monkeypatch):
    original = subject._Directory.write
    def interrupted(self, name, raw):
        if name.startswith("observation-") and json.loads(raw)["endpoint"] == "backtests/create":
            subject._fail("control_write")
        return original(self, name, raw)
    monkeypatch.setattr(subject._Directory, "write", interrupted)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert sum(endpoint == "backtests/create" for endpoint, _ in qc.fake.calls) == 1
    assert (package.control / "attempt-claim.json").exists()
    assert (package.control / "backtest-create-claim.json").exists()
    assert not (package.control / "launch.json").exists()
    before = list(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, package.pin, qc.api)
    assert qc.fake.calls == before


@pytest.mark.parametrize("failed_receipt", ["observation", "terminal"])
def test_status_pending_receipt_blocks_repeat_before_any_new_contact(package, qc, monkeypatch, failed_receipt):
    subject.launch(package.control, package.pin, qc.api)
    qc.fake.state = "Completed."
    original = subject._Directory.write
    retained = []

    def interrupted(self, name, raw):
        is_target = (name == "terminal.json" if failed_receipt == "terminal" else
                     name.startswith("observation-") and json.loads(raw)["endpoint"] == "backtests/list")
        if is_target:
            pending = package.control / (name + ".pending")
            fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, b"{")
            finally:
                os.close(fd)
            retained.append(pending)
            subject._fail("control_write")
        return original(self, name, raw)

    monkeypatch.setattr(subject._Directory, "write", interrupted)
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert sum(endpoint == "backtests/list" for endpoint, _ in qc.fake.calls) == 1
    assert (package.control / "status-claim-001.json").exists()
    assert len(retained) == 1 and retained[0].read_bytes() == b"{"
    monkeypatch.setattr(subject._Directory, "write", original)
    before = list(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert qc.fake.calls == before
    assert retained[0].read_bytes() == b"{" and not (package.control / "status-claim-002.json").exists()


@pytest.mark.parametrize("action", ["launch", "status", "read"])
@pytest.mark.parametrize("pending_name", ["observation-001.json.pending", "terminal.json.pending", "unexpected-control.pending"])
def test_any_retained_pending_blocks_all_postprepare_actions_before_client(package, qc, monkeypatch, action, pending_name):
    if action in {"status", "read"}:
        completed(package, qc)
    pending = package.control / pending_name
    pending.write_bytes(b"{\"synthetic\":")
    pending.chmod(0o600)
    before = list(qc.fake.calls)
    original_names = {leaf.name for leaf in package.control.iterdir()}
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No client after any interrupted control"))
    with pytest.raises(subject.IdentityQcError, match="interrupted_control_pending"):
        getattr(subject, action)(package.control, package.pin)
    assert qc.fake.calls == before
    assert {leaf.name for leaf in package.control.iterdir()} == original_names
    assert pending.read_bytes() == b"{\"synthetic\":"


def test_pending_control_also_blocks_post_if_created_after_action_entry(package, qc, monkeypatch):
    pending = package.control / "observation-001.json.pending"
    pending.write_bytes(b"{")
    pending.chmod(0o600)
    monkeypatch.setattr(subject, "_instant", lambda: pytest.fail("No fresh observation after pending control"))
    with subject._Directory(package.control) as directory:
        with pytest.raises(subject.IdentityQcError, match="interrupted_control_pending"):
            subject._post(directory, qc.api, "backtests/list", {"projectId": 12345}, {})
    assert qc.fake.calls == [] and pending.read_bytes() == b"{"


@pytest.mark.parametrize("supplied_api", [False, True])
@pytest.mark.parametrize("package", [subject.CONTINUITY_INPUT_SCHEMA], indirect=True)
def test_real_api_refuses_synthetic_publication_before_credentials_or_supplied_client(package, qc, monkeypatch, supplied_api):
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No production credentials for test-mode package"))
    monkeypatch.setattr(subject.boundary, "_client", lambda *_args: pytest.fail("No supplied client validation before source-mode refusal"))
    with pytest.raises(subject.IdentityQcError, match="continuity_production_source_mode"):
        qc.production_api(qc.api if supplied_api else None, package.prepared)
    assert qc.fake.calls == []


@pytest.mark.parametrize("action", ["launch", "status", "read"])
@pytest.mark.parametrize("package", [subject.CONTINUITY_INPUT_SCHEMA], indirect=True)
def test_all_real_actions_apply_production_source_mode_gate(package, qc, monkeypatch, action):
    if action in {"status", "read"}:
        completed(package, qc)
        if action == "status":
            # Preserve the synthetic cached terminal while forcing a fresh
            # status path to exercise its production API boundary.
            (package.control / "terminal.json").rename(package.control / "synthetic-terminal-retained.json")
    before = list(qc.fake.calls)
    monkeypatch.setattr(subject, "_api", qc.production_api)
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No production credentials for test-mode package"))
    with pytest.raises(subject.IdentityQcError, match="continuity_production_source_mode"):
        getattr(subject, action)(package.control, package.pin)
    assert qc.fake.calls == before


@pytest.mark.parametrize("stage", ["launch", "status", "read"])
@pytest.mark.parametrize("leaf", ["manifest.json", "manifest.sha256", "input.json"])
@pytest.mark.parametrize("package", [subject.CONTINUITY_INPUT_SCHEMA], indirect=True)
def test_continuity_source_package_reauthenticated_before_every_contact(package, qc, stage, leaf):
    if stage in {"status", "read"}:
        completed(package, qc)
    source_leaf = package.input.parent / leaf
    source_leaf.write_bytes(source_leaf.read_bytes() + b" ")
    before = list(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError, match="continuity_publication"):
        getattr(subject, stage)(package.control, package.pin, qc.api)
    assert qc.fake.calls == before
    if stage == "launch":
        assert not (package.control / "attempt-claim.json").exists()
    if stage == "read":
        assert not (package.control / "result-read-claim.json").exists()


@pytest.mark.parametrize("package", [subject.CONTINUITY_INPUT_SCHEMA], indirect=True)
def test_continuity_change_during_copy_never_publishes_prepared_completion(package, monkeypatch, tmp_path):
    root = tmp_path / "separate-synthetic-candidate-root"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(subject, "ARTIFACT_ROOT", root)
    control = root / subject.CONTROL_LEAF
    original = subject._Directory.write
    def change(self, name, raw):
        result = original(self, name, raw)
        if name == "prepared.sha256":
            manifest = package.input.parent / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" ")
        return result
    monkeypatch.setattr(subject._Directory, "write", change)
    with pytest.raises(subject.IdentityQcError, match="continuity_publication"):
        subject.prepare(package.input, subject.sha(package.raw), control)
    assert (control / "input.json").read_bytes() == package.raw
    assert not (control / "prepared-complete.json").exists()
    assert not (control / "attempt-claim.json").exists()


@pytest.mark.parametrize("package", [subject.CONTINUITY_INPUT_SCHEMA], indirect=True)
def test_continuity_source_path_is_private_control_metadata_only(package):
    assert package.prepared["schema"] == subject.CONTINUITY_PREPARED_SCHEMA
    assert package.prepared["continuity_input_path"] == str(package.input)
    source = (package.control / "main.py").read_bytes()
    assert str(package.input).encode() not in source
    assert "continuity_input_path" not in subject._bind(package.prepared, package.pin)
    assert "continuity_input_path" not in package.value


def test_fixed_candidate_leaf_rejects_rebound_prepared_copy_before_client(package, qc, monkeypatch):
    replay = package.control.with_name("R284A1-20261008-B")
    shutil.copytree(package.control, replay)
    value = json.loads((replay / "prepared.json").read_bytes())
    value["control_directory"] = str(replay)
    raw = subject.canonical(value)
    pin = subject.sha(raw)
    (replay / "prepared.json").write_bytes(raw)
    (replay / "prepared.sha256").write_bytes(pin.encode("ascii"))
    (replay / "prepared-complete.json").write_bytes(subject.canonical({"prepared_sha256": pin}))
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No second candidate client"))
    with pytest.raises(subject.IdentityQcError, match="candidate_control_leaf"):
        subject.launch(replay, pin)
    assert qc.fake.calls == [] and not (replay / "attempt-claim.json").exists()


def test_prepare_is_offline_private_pinned(package, monkeypatch, tmp_path):
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No credentials or client before launch"))
    monkeypatch.setattr(subject, "_instant", lambda: pytest.fail("No clock before launch"))
    # A separate synthetic fixture root preserves the fresh-prepare offline
    # assertion without creating a second leaf in one production candidate.
    root = tmp_path / "fresh-offline-fixture-root"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(subject, "ARTIFACT_ROOT", root)
    control = root / subject.CONTROL_LEAF
    result = subject.prepare(package.input, subject.sha(package.raw), control)
    pin = subject.sha(subject.canonical(result))
    assert result["control_directory"] == str(control)
    assert {key: value for key, value in result.items() if key != "control_directory"} == {
        key: value for key, value in package.prepared.items() if key != "control_directory"}
    assert set(path.name for path in control.iterdir()) == {"input.json", "main.py", "prepared.json", "prepared.sha256", "prepared-complete.json"}
    assert stat.S_IMODE(control.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in control.iterdir())
    with subject._Directory(control) as directory:
        prepared, source = subject._prepared(directory, pin)
    assert prepared == result and subject.sha(source) == prepared["source_sha256"]
    assert subject.source_template_sha256(source) == prepared["source_template_sha256"]
    with pytest.raises(subject.IdentityQcError, match="prepare_directory_not_empty"):
        subject.prepare(package.input, subject.sha(package.raw), control)


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
    raw = subject.canonical_input(value)
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(raw, subject.sha(raw))


@pytest.mark.parametrize("raw", [b"{} ", b'{"schema":"x","schema":"y"}', b'{"x":NaN}', b'\xff'])
def test_noncanonical_or_ambiguous_json_refused(raw):
    with pytest.raises(subject.IdentityQcError):
        subject._json(raw)


def test_input_byte_pin_refused(package):
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(package.raw, "0" * 64)


def test_input_matches_research_canonical_bytes_without_normalizing_or_repinning(package):
    research_raw = canonical_json_bytes(package.value)
    assert package.raw == subject.canonical_input(package.value) == research_raw
    assert package.raw.endswith(b"\n") and not package.raw.endswith(b"\n\n")
    assert subject.validate_input(research_raw, subject.sha(research_raw)) == package.value
    assert (package.control / "input.json").read_bytes() == research_raw
    assert package.prepared["input_sha256"] == subject.sha(research_raw)
    no_linefeed_pin = subject.sha(subject.canonical(package.value))
    assert no_linefeed_pin != package.prepared["input_sha256"]
    with pytest.raises(subject.IdentityQcError, match="input_bytes"):
        subject.validate_input(research_raw, no_linefeed_pin)
    with pytest.raises(subject.IdentityQcError, match="input_bytes"):
        subject.render_source(package.value, no_linefeed_pin)


@pytest.mark.parametrize("kind", ["missing_lf", "multiple_lf", "crlf", "trailing_space",
                                 "space_before_lf", "leading_lf", "pretty_json", "unsorted_keys"])
def test_input_requires_exactly_one_lf_and_no_other_canonical_relaxation(package, kind, monkeypatch):
    raw = package.raw
    if kind == "missing_lf":
        raw = raw[:-1]
    elif kind == "multiple_lf":
        raw += b"\n"
    elif kind == "crlf":
        raw = raw[:-1] + b"\r\n"
    elif kind == "trailing_space":
        raw += b" "
    elif kind == "space_before_lf":
        raw = raw[:-1] + b" \n"
    elif kind == "leading_lf":
        raw = b"\n" + raw
    elif kind == "pretty_json":
        raw = json.dumps(package.value, sort_keys=True, indent=2).encode("ascii") + b"\n"
    else:
        reversed_value = dict(reversed(sorted(package.value.items())))
        raw = json.dumps(reversed_value, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
    assert raw != package.raw
    source_path = package.input.with_name("malformed-input.json")
    source_path.write_bytes(raw)
    source_path.chmod(0o600)
    control = package.control.with_name("invalid-input")
    monkeypatch.setattr(subject.boundary, "production_client", lambda: pytest.fail("No API on refused input"))
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(raw, subject.sha(raw))
    with pytest.raises(subject.IdentityQcError):
        subject.prepare(source_path, subject.sha(raw), control)
    assert not control.exists()


def test_input_lf_does_not_relax_internal_control_or_metadata_json(package, qc):
    for raw in (subject.canonical(package.prepared), subject.canonical(qc.fake.meta)):
        assert subject._json(raw) == json.loads(raw)
        with pytest.raises(subject.IdentityQcError, match="noncanonical_json"):
            subject._json(raw + b"\n")
    with pytest.raises(subject.IdentityQcError):
        subject.validate_meta(subject.canonical(qc.fake.meta).decode("ascii") + "\n", package.prepared)


def test_original_v1_profile_and_key_contract_remain_unchanged():
    assert subject.PROFILE_SHA256 == "8a96514a71799763673e31a180f970692a512c51cb7a53dfa3230e362de98811"
    assert subject._input_keys(subject.INPUT_SCHEMA) == {"schema", "rows", "price_manifest_sha256", "public_reference_sha256", "sharadar_identity_manifest_sha256"}
    assert subject._profile(subject.INPUT_SCHEMA) == (subject.PROFILE, subject.PROFILE_SHA256)
    assert subject._profile(subject.CONTINUITY_INPUT_SCHEMA) == (subject.CONTINUITY_PROFILE, subject.CONTINUITY_PROFILE_SHA256)
    assert subject.PROFILE_SHA256 != subject.CONTINUITY_PROFILE_SHA256


def test_every_mode_binds_selected_profile_and_never_claims_complete_identity(package, monkeypatch):
    _, meta = run_runtime(package, monkeypatch)
    profile, profile_sha256 = subject._profile(package.value["schema"])
    assert package.prepared["input_schema"] == package.value["schema"]
    assert package.prepared["profile"] == profile
    assert package.prepared["profile_sha256"] == profile_sha256
    assert meta["input_schema"] == package.value["schema"]
    assert meta["profile_sha256"] == profile_sha256
    assert meta["source_binding_mode"] == profile["mode"]
    assert all(package.prepared[key] is False and meta[key] is False for key in subject._RUNTIME_FALSE_FLAGS)
    if package.value["schema"] == subject.CONTINUITY_INPUT_SCHEMA:
        assert profile["source_qualifications_retained_private_host_only"] is True
        assert profile["current_vendor_figi_missing_refusal_preserved"] is True
        assert "qualified_vintage_current_continuity" in profile["mode"]
        assert meta["continuity_manifest_sha256"] == package.value["continuity_manifest_sha256"]
        assert meta["vintage_manifest_sha256"] == package.value["vintage_manifest_sha256"]
    else:
        assert "continuity_manifest_sha256" not in meta and "vintage_manifest_sha256" not in meta


@pytest.mark.parametrize("kind", ["unknown_schema", "mixed_keys", "missing_pin", "invalid_pin", "host_qualifications"])
def test_variant_schema_keys_and_pins_exact_no_mixed_admission(package, kind):
    value = copy.deepcopy(package.value)
    if kind == "unknown_schema":
        value["schema"] = "arv2-seven-public-figi-continuity-input-v999"
    elif kind == "mixed_keys":
        value["schema"] = subject.INPUT_SCHEMA if value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else subject.CONTINUITY_INPUT_SCHEMA
    elif kind == "missing_pin":
        value.pop("vintage_manifest_sha256" if value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else "public_reference_sha256")
    elif kind == "invalid_pin":
        value["continuity_manifest_sha256" if value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else "public_reference_sha256"] = True
    else:
        value["rows"][0]["source_refusal_codes"] = ["FIGI_INVALID_OR_MISSING"]
    raw = subject.canonical_input(value)
    with pytest.raises(subject.IdentityQcError):
        subject.validate_input(raw, subject.sha(raw))


@pytest.mark.parametrize("kind", ["input_schema", "profile", "profile_sha256", "extra_pin", "qualification_flag"])
def test_prepared_selected_schema_profile_and_flags_cannot_mix_before_contact(package, qc, kind):
    path = package.control / "prepared.json"
    value = json.loads(path.read_bytes())
    other = subject.INPUT_SCHEMA if package.value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else subject.CONTINUITY_INPUT_SCHEMA
    if kind == "input_schema":
        value["input_schema"] = other
    elif kind == "profile":
        value["profile"] = subject._profile(other)[0]
    elif kind == "profile_sha256":
        value["profile_sha256"] = subject._profile(other)[1]
    elif kind == "qualification_flag":
        value["complete_price_identity_binding"] = True
    elif package.value["schema"] == subject.INPUT_SCHEMA:
        value["continuity_manifest_sha256"] = "4" * 64
    else:
        value.pop("continuity_manifest_sha256")
    raw = subject.canonical(value)
    new_pin = subject.sha(raw)
    path.write_bytes(raw)
    (package.control / "prepared.sha256").write_bytes(new_pin.encode("ascii"))
    (package.control / "prepared-complete.json").write_bytes(subject.canonical({"prepared_sha256": new_pin}))
    with pytest.raises(subject.IdentityQcError):
        subject.launch(package.control, new_pin, qc.api)
    assert qc.fake.calls == [] and not (package.control / "attempt-claim.json").exists()


@pytest.mark.parametrize("kind", ["input_schema", "profile_hash", "binding_mode", "continuity_pin", "vintage_pin", "qualified_flag"])
def test_metadata_selected_variant_and_continuity_binding_exact(package, qc, kind):
    value = copy.deepcopy(qc.fake.meta)
    other = subject.INPUT_SCHEMA if package.value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else subject.CONTINUITY_INPUT_SCHEMA
    if kind == "input_schema":
        value["input_schema"] = other
    elif kind == "profile_hash":
        value["profile_sha256"] = subject._profile(other)[1]
    elif kind == "binding_mode":
        value["source_binding_mode"] = subject._profile(other)[0]["mode"]
    elif kind == "qualified_flag":
        value["complete_price_identity_binding"] = True
    else:
        value["continuity_manifest_sha256" if kind == "continuity_pin" else "vintage_manifest_sha256"] = "6" * 64
    with pytest.raises(subject.IdentityQcError):
        subject.validate_meta(subject.canonical(value).decode("ascii"), package.prepared)


@pytest.mark.parametrize("kind", ["binding_schema", "profile_hash", "continuity_pin", "vintage_pin", "qualified_flag"])
def test_launch_and_terminal_refuse_mixed_variant_receipt_before_status_contact(package, qc, kind):
    subject.launch(package.control, package.pin, qc.api)
    path = package.control / "launch.json"
    value = json.loads(path.read_bytes())
    if kind == "binding_schema":
        value["input_schema"] = subject.INPUT_SCHEMA if package.value["schema"] == subject.CONTINUITY_INPUT_SCHEMA else subject.CONTINUITY_INPUT_SCHEMA
    elif kind == "profile_hash":
        value["profile_sha256"] = "6" * 64
    elif kind == "qualified_flag":
        value["historical_identity_authenticated"] = True
    else:
        value["continuity_manifest_sha256" if kind == "continuity_pin" else "vintage_manifest_sha256"] = "6" * 64
    path.write_bytes(subject.canonical(value))
    before = len(qc.fake.calls)
    with pytest.raises(subject.IdentityQcError):
        subject.status(package.control, package.pin, qc.api)
    assert len(qc.fake.calls) == before


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
    assert all(meta[key] is False for key in subject._RUNTIME_FALSE_FLAGS)
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
        assert subject._bound(observation, subject._bind(package.prepared, package.pin))
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
