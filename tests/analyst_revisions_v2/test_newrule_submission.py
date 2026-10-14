"""Synthetic private controls and fake QC only; no credentials or operations."""
import copy
import dataclasses
import hashlib
import importlib.util
import json
import os
import socket
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
import urllib.request

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from research.analyst_revisions_v2_qc import newrule_comparison_submission as m

# Section 301 (ARV2R301-002): the real boundaries, captured before any test
# patches them, so the autouse tripwire below can be checked independently.
REAL_ROOT, REAL_CONTROL = m.ROOT, m.CONTROL
REAL_DIRECTORY_INIT, REAL_CLIENT_INIT = m._Directory.__init__, m.QuantConnectClient.__init__
REAL_PRODUCTION_CLIENT, REAL_BOUNDED_TRANSPORT = m.coverage.production_client, m.coverage._bounded_transport
REAL_CREATE_CONNECTION = socket.create_connection


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    """Every test is synthetic: no real control directory, client or network.

    The `setup` fixture redirects ROOT/CONTROL to tmp_path; a test that does not
    must never open the production control directory (the 298.2 incident class).
    A guard swallowed by a broad product handler still fails at teardown.
    """
    violations = []

    def forbidden(*_args, **_kwargs):
        violations.append("operational_boundary")
        pytest.fail("operational boundary forbidden")

    def directory_init(self, *args, **kwargs):
        if m.CONTROL == REAL_CONTROL or m.ROOT == REAL_ROOT:
            forbidden()
        return REAL_DIRECTORY_INIT(self, *args, **kwargs)

    monkeypatch.setattr(m._Directory, "__init__", directory_init)
    monkeypatch.setattr(m.QuantConnectClient, "__init__", forbidden)
    monkeypatch.setattr(m.coverage, "production_client", forbidden)
    monkeypatch.setattr(m.coverage, "_bounded_transport", forbidden)
    for owner, names in ((socket, ("create_connection", "getaddrinfo")),
                         (socket.socket, ("connect", "connect_ex")),
                         (urllib.request.OpenerDirector, ("open",)),
                         (m.http.client.HTTPConnection, ("connect",)),
                         (m.http.client.HTTPSConnection, ("connect",))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "swallowed operational boundary"


def test_isolation_tripwires_cover_real_directory_client_and_network(isolation):
    # Fails if the autouse tripwire above is removed or narrowed.
    assert isolation == []
    assert m._Directory.__init__ is not REAL_DIRECTORY_INIT
    assert m.QuantConnectClient.__init__ is not REAL_CLIENT_INIT
    assert m.coverage.production_client is not REAL_PRODUCTION_CLIENT
    assert m.coverage._bounded_transport is not REAL_BOUNDED_TRANSPORT
    assert socket.create_connection is not REAL_CREATE_CONNECTION
    assert m.CONTROL == REAL_CONTROL
    with pytest.raises(pytest.fail.Exception, match="operational boundary forbidden"):
        m._Directory()
    assert isolation == ["operational_boundary"]
    isolation.clear()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def axis():
    start, end = date(2013, 1, 2), date(2026, 10, 13)
    return tuple((start + timedelta(days=i)).isoformat()
        for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5)


class FakeQC:
    def __init__(self):
        self.calls, self.projects, self.files, self.runs = [], {}, {}, {}
        self.busy, self.auto, self.selected = False, True, False
        self.state, self.status = "BuildSuccess", "InProgress"
        self.failure, self.mutate, self.custom = None, None, None
        self.objects = {}
        self._credentials = NS(user_id="synthetic", api_token="synthetic-not-a-real-key")
        self._clock, self._timeout = lambda: 1, 30
        self._transport = self.http

    def project(self, project_id):
        return {"projectId": project_id, "name": self.projects.get(project_id, "Reference"),
            "organizationId": "a" * 32, "language": "Py", "owner": True,
            "public": False, "codeRunning": False, "collaborators": []}

    def request(self, endpoint, payload):
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if self.failure == endpoint:
            raise RuntimeError("NEVER-PRINT-THIS-SECRET")
        if endpoint == "authenticate":
            result = {"success": True}
        elif endpoint == "projects/read":
            result = {"success": True, "projects": [self.project(payload["projectId"])]}
        elif endpoint == "projects/nodes/read":
            result = {"success": True, "autoSelectNode": self.auto,
                "nodes": {"backtest": [{"busy": self.busy, "active": self.selected}],
                          "live": "unread", "research": "unread"}}
        elif endpoint == "projects/create":
            # The exact attempt claim MUST precede the first cloud mutation.
            candidate = payload["name"].split()[1]
            assert (m.CONTROL / f"{candidate}-A1-claim.json").is_file()
            project_id = 1000 + len(self.projects)
            self.projects[project_id] = payload["name"]
            self.files[project_id] = {"main.py": "# default\n", "research.ipynb": "{}"}
            self.runs[project_id] = []
            result = {"success": True, "projects": [self.project(project_id)]}
        elif endpoint == "files/read":
            result = {"success": True, "files": [{"name": name, "content": content,
                "projectId": payload["projectId"]} for name, content in self.files[payload["projectId"]].items()]}
        elif endpoint in {"files/create", "files/update", "files/delete"}:
            if endpoint.endswith("delete"):
                del self.files[payload["projectId"]][payload["name"]]
            else:
                self.files[payload["projectId"]][payload["name"]] = payload["content"]
            result = {"success": True}
        elif endpoint == "compile/create":
            result = {"success": True, "projectId": payload["projectId"], "compileId": "compile-" + str(len(self.calls))}
        elif endpoint == "compile/read":
            result = {"success": True, "compileId": payload["compileId"], "state": self.state}
        elif endpoint == "backtests/create":
            row = {"projectId": payload["projectId"], "backtestId": "backtest-" + str(len(self.calls)),
                   "name": payload["backtestName"], "status": "InQueue"}
            self.runs[payload["projectId"]].append(row)
            result = {"success": True, "backtest": row}
        elif endpoint == "backtests/list":
            rows = copy.deepcopy(self.runs[payload["projectId"]])
            for row in rows:
                if row["status"] != "Runtime Error":
                    row["status"] = self.status
            result = {"success": True, "backtests": rows, "count": len(rows)}
        elif endpoint == "backtests/read":
            row = copy.deepcopy(next(row for row in self.runs[payload["projectId"]]
                                     if row["backtestId"] == payload["backtestId"]))
            row.update(status="Completed.", statistics=self.custom or {
                m.runtime.META_STATISTIC: "{}", m.runtime.MONTHLY_STATISTIC: "{}",
                "Raw unapproved field": "NEVER-RETAIN"})
            result = {"success": True, "backtest": row}
        else:
            raise AssertionError(endpoint)
        if self.mutate:
            self.mutate(endpoint, result)
        return result

    def http(self, url, body, headers, timeout):
        assert headers["Authorization"] and timeout == 30
        endpoint = url[len(m.API_BASE) + 1:]
        self.calls.append((endpoint, None))
        if endpoint == "object/set":
            assert (m.CONTROL / "upload-claim.json").is_file()
            key = body.split(b'name="key"\r\n\r\n')[1].split(b"\r\n", 1)[0].decode()
            payload = body.split(b"Content-Type: application/octet-stream\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            self.objects[key] = payload
            response = {"success": True}
        else:
            assert endpoint == "object/properties"
            key = json.loads(body)["key"]
            value = self.objects[key]
            response = {"success": True, "metadata": {"key": key, "size": len(value),
                "md5": hashlib.md5(value, usedforsecurity=False).hexdigest(), "preview": "NEVER-RETAIN"}}
        if self.mutate:
            self.mutate(endpoint, response)
        return 200, json.dumps(response).encode()


@pytest.fixture
def setup(monkeypatch, tmp_path):
    assert_lane_closure_excludes_dispatch_fence()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "CONTROL", tmp_path / "artifacts/test-family")
    payloads = (b"synthetic input", b"synthetic activation")
    monkeypatch.setattr(m, "ACTIVATION_SHA256", sha(payloads[-1]))
    monkeypatch.setattr(m, "ACTIVATION_BYTES", len(payloads[-1]))
    monkeypatch.setattr(m, "UPLOAD_BYTES", sum(map(len, payloads)))
    descriptors = (NS(object_store_key="synthetic/input", content_sha256=sha(payloads[0]),
                      byte_count=len(payloads[0]), activation_manifest=False),
        NS(object_store_key=m.ACTIVATION_KEY, content_sha256=sha(payloads[1]),
           byte_count=len(payloads[1]), activation_manifest=True))
    package = NS(package_sha256=m.PACKAGE_SHA256, upload_objects=descriptors,
                 total_upload_byte_count=sum(map(len, payloads)))
    value = NS(package=package, lineage_sha256=m.LINEAGE_SHA256)
    monkeypatch.setattr(m.october, "require_october_order_input_package", lambda item: item if item is value else (_ for _ in ()).throw(ValueError("not genuine")))
    monkeypatch.setattr(m.compact, "require_accepted_risk_preliminary_package", lambda item: item)
    monkeypatch.setattr(m.compact, "iter_accepted_risk_preliminary_upload_objects", lambda _: iter(zip(descriptors, payloads)))
    monkeypatch.setattr(m, "_sources", lambda _: None)
    def project(_, *, universe_count, ar_percent, **kwargs):
        profile = m.runtime.make_profile(axis(), package_sha256=m.PACKAGE_SHA256,
            lineage_sha256=m.LINEAGE_SHA256, universe_count=universe_count, ar_percent=ar_percent,
            source_pins={"synthetic.py": "a" * 64})
        files = (m.projection.SourceFile("main.py", b"# synthetic only\n"),)
        record = {"package_sha256": m.PACKAGE_SHA256, "lineage_sha256": m.LINEAGE_SHA256,
            "activation_manifest_sha256": m.ACTIVATION_SHA256, "source_files": [f.to_record() for f in files],
            "paper_or_live_ready": False,
            "profile_sha256": profile["profile_sha256"]}
        raw = m.runtime.targets.canonical(record)
        return m.projection.Projection(raw, sha(raw), files, m.runtime.targets.canonical(profile))
    monkeypatch.setattr(m.projection, "build_projection", project)
    api = FakeQC()
    clock = NS(now=1000000)
    monkeypatch.setattr(m.time, "time", lambda: clock.now)
    def client():
        assert (m.CONTROL / "family.json").is_file()
        return api
    monkeypatch.setattr(m, "_client", client)
    plan = m.prepare_family(value, expected_new_source_pins={}, expected_host_source_pins={})
    return NS(plan=plan, value=value, api=api, clock=clock, pins={}, monkeypatch=monkeypatch)


def kwargs(s):
    return {"expected_family_sha256": s.plan.family_sha256}


def uploaded(s):
    m.discover_organization(s.plan, **kwargs(s))
    return m.upload_inputs(s.plan, **kwargs(s))


def started(s, cell="R298", attempt=1, **extra):
    result = m.begin_attempt(s.plan, cell, attempt, **kwargs(s), **extra)
    m.poll_compile_once(s.plan, cell, attempt, **kwargs(s))
    return result


def launched(s, cell="R298"):
    started(s, cell)
    return m.launch_compiled(s.plan, cell, 1, **kwargs(s))


def test_prepare_offline_exact_six_and_load(setup):
    s = setup
    assert not s.api.calls
    record = json.loads(s.plan.record_bytes)
    assert [row["candidate_id"] for row in record["cells"]] == ["R298", "R299", "R300", "R301", "R302", "R303"]
    assert "organization_id" not in record and record["organization_reference_project_id"] == 37165262
    same = m.load_family(s.value, expected_new_source_pins={}, expected_host_source_pins={}, **kwargs(s))
    assert same.family_sha256 == s.plan.family_sha256
    with pytest.raises(m.NewruleSubmissionError):
        m.prepare_family(s.value, expected_new_source_pins={}, expected_host_source_pins={})


@pytest.mark.parametrize("failure", ["pin", "forged", "mutated", "bytearray"])
def test_no_forged_or_changed_family_before_contact(setup, failure):
    s = setup
    plan, pin = s.plan, s.plan.family_sha256
    if failure == "pin": pin = "b" * 64
    elif failure == "forged": plan = dataclasses.replace(plan)
    elif failure == "mutated": object.__setattr__(plan, "record_bytes", b"{}\n")
    else: object.__setattr__(plan._projections[0].source_files[0], "source_bytes", bytearray(b"# synthetic only\n"))
    with pytest.raises(m.NewruleSubmissionError):
        m.discover_organization(plan, expected_family_sha256=pin)
    assert not s.api.calls


def test_organization_once_private_raw_identifier_not_returned(setup):
    s = setup
    value = m.discover_organization(s.plan, **kwargs(s))
    assert value["organization_sha256"] == sha(b"a" * 32)
    assert "organization_id" not in value
    assert [row[0] for row in s.api.calls] == ["authenticate", "projects/read"]
    with pytest.raises(FileExistsError): m.discover_organization(s.plan, **kwargs(s))
    assert len(s.api.calls) == 2


@pytest.mark.parametrize("field,bad", [("organizationId", "bad"), ("projectId", True), ("owner", False),
    ("public", True), ("language", "C#"), ("collaborators", [{"owner": False}])])
def test_organization_bad_identity_refuses(setup, field, bad):
    s = setup
    s.api.mutate = lambda endpoint, value: value["projects"][0].update({field: bad}) if endpoint == "projects/read" else None
    with pytest.raises(m.NewruleSubmissionError): m.discover_organization(s.plan, **kwargs(s))
    assert not (m.CONTROL / "organization.json").exists()


def test_upload_claim_activation_last_and_no_repeat(setup):
    s = setup
    uploaded(s)
    assert tuple(s.api.objects) == ("synthetic/input", m.ACTIVATION_KEY)
    raw = b"".join(path.read_bytes() for path in m.CONTROL.iterdir())
    assert b"synthetic input" not in raw and b"NEVER-RETAIN" not in raw
    calls = len(s.api.calls)
    with pytest.raises(FileExistsError): m.upload_inputs(s.plan, **kwargs(s))
    assert len(s.api.calls) == calls


@pytest.mark.parametrize("field,bad", [("size", True), ("size", 999), ("md5", "0" * 32), ("key", "wrong")])
def test_upload_metadata_failures_no_activation(setup, field, bad):
    s = setup
    m.discover_organization(s.plan, **kwargs(s))
    s.api.mutate = lambda endpoint, value: value["metadata"].update({field: bad}) if endpoint == "object/properties" else None
    with pytest.raises(m.NewruleSubmissionError): m.upload_inputs(s.plan, **kwargs(s))
    assert m.ACTIVATION_KEY not in s.api.objects
    assert not (m.CONTROL / "upload-valid.json").exists()


@pytest.mark.parametrize("busy,auto,active,available", [(True, True, True, 0), (False, False, False, 0),
    (False, False, True, 1), (False, True, False, 1)])
def test_capacity_selected_is_not_busy(setup, busy, auto, active, available):
    s = setup
    uploaded(s)
    s.api.busy, s.api.auto, s.api.selected = busy, auto, active
    result = m.capacity_once(s.plan, **kwargs(s))
    assert result["available_count"] == available
    assert result["state"] == ("available" if available else "wait")
    with pytest.raises(m.NewruleSubmissionError, match="wait_before_poll"):
        m.capacity_once(s.plan, **kwargs(s))
    s.clock.now += 60
    assert m.capacity_once(s.plan, **kwargs(s))["available_count"] == available


@pytest.mark.parametrize("auto,busy,active", [(0, False, False), (True, 0, False), (True, False, 0)])
def test_capacity_strict_boolean_types(auto, busy, active):
    with pytest.raises(m.NewruleSubmissionError):
        m._capacity({"autoSelectNode": auto, "nodes": {"backtest": [{"busy": busy, "active": active}]}})


def test_success_lifecycle_single_aggregate_and_filtered_result(setup):
    s = setup
    uploaded(s)
    receipt = launched(s)
    assert receipt["shared_look"] == receipt["development_look"] == 1
    assert receipt["infrastructure_look"] == receipt["result_cell"] == 0
    s.api.status = "Completed."
    m.poll_status_once(s.plan, "R298", 1, **kwargs(s))
    def validator(selected, *, expected_profile):
        assert set(selected) == {m.runtime.META_STATISTIC, m.runtime.MONTHLY_STATISTIC}
        return {"meta": {"package_sha256": expected_profile["package_sha256"],
            "lineage_sha256": expected_profile["lineage_sha256"], "decision_count": 302,
            "evaluation_session_count": 1510, "common_source_path_sha256": "c" * 64}, "monthly": {}}
    s.monkeypatch.setattr(m.runtime, "validate_result_statistics", validator)
    result = m.read_result_once(s.plan, "R298", 1, **kwargs(s))
    assert result["cell_completed"] and not result["family_comparable"]
    assert result["result_cell"] == 1
    with pytest.raises(FileExistsError): m.read_result_once(s.plan, "R298", 1, **kwargs(s))
    assert sum(endpoint == "backtests/read" for endpoint, _ in s.api.calls) == 1
    assert b"NEVER-RETAIN" not in b"".join(path.read_bytes() for path in m.CONTROL.iterdir())
    summary = m.summarize_family(s.plan, **kwargs(s))
    assert summary["completed_cells"] == ["R298"] and not summary["family_comparable"]
    path = m.CONTROL / "R298-A1-result.json"
    altered = json.loads(path.read_bytes())
    altered["statistics"]["meta"]["decision_count"] = 302.0
    path.write_bytes(m._canonical(altered))
    with pytest.raises(m.NewruleSubmissionError, match="result_changed"):
        m.summarize_family(s.plan, **kwargs(s))


def test_completed_without_valid_custom_statistics_stays_unaccepted(setup):
    s = setup
    uploaded(s)
    launched(s)
    s.api.status = "Completed."
    m.poll_status_once(s.plan, "R298", 1, **kwargs(s))
    with pytest.raises(ValueError): m.read_result_once(s.plan, "R298", 1, **kwargs(s))
    assert (m.CONTROL / "R298-A1-retained-statistics.json").exists()
    assert not (m.CONTROL / "R298-A1-result.json").exists()
    with pytest.raises(FileExistsError): m.read_result_once(s.plan, "R298", 1, **kwargs(s))


@pytest.mark.parametrize("failure", ["compile", "launch", "status", "read"])
def test_identity_binding_failures_spend_stage_without_retry(setup, failure):
    s = setup
    uploaded(s)
    if failure == "compile":
        m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
        s.api.mutate = lambda endpoint, value: value.update(compileId="wrong") if endpoint == "compile/read" else None
        operation = lambda: m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    elif failure == "launch":
        started(s)
        s.api.mutate = lambda endpoint, value: value["backtest"].update(name="wrong") if endpoint == "backtests/create" else None
        operation = lambda: m.launch_compiled(s.plan, "R298", 1, **kwargs(s))
    elif failure == "status":
        launched(s)
        s.api.status = "Completed"
        operation = lambda: m.poll_status_once(s.plan, "R298", 1, **kwargs(s))
    else:
        launched(s)
        s.api.status = "Completed."
        m.poll_status_once(s.plan, "R298", 1, **kwargs(s))
        s.api.mutate = lambda endpoint, value: value["backtest"].update(projectId=True) if endpoint == "backtests/read" else None
        operation = lambda: m.read_result_once(s.plan, "R298", 1, **kwargs(s))
    with pytest.raises(m.NewruleSubmissionError): operation()


def test_build_error_retry_bound_and_no_source_change(setup):
    s = setup
    uploaded(s)
    s.api.state = "BuildError"
    for attempt in (1, 2, 3):
        extra = {} if attempt == 1 else {"prior_failure_sha256": sha(m._canonical(result)), "retry_justification_sha256": "d" * 64}
        m.begin_attempt(s.plan, "R298", attempt, **kwargs(s), **extra)
        result = m.poll_compile_once(s.plan, "R298", attempt, **kwargs(s))
        assert result["status"] == "BuildError"
    assert sum(endpoint == "compile/create" for endpoint, _ in s.api.calls) == 3
    assert sum(endpoint == "projects/create" for endpoint, _ in s.api.calls) == 1
    with pytest.raises(m.NewruleSubmissionError): m.begin_attempt(s.plan, "R298", 4, **kwargs(s))


def test_transport_ambiguity_consumes_attempt_and_blocks_next_cell(setup):
    s = setup
    uploaded(s)
    s.api.failure = "compile/create"
    with pytest.raises(m.NewruleSubmissionError, match="request_ambiguous") as caught:
        m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    assert "SECRET" not in str(caught.value)
    assert (m.CONTROL / "R298-A1-claim.json").exists()
    with pytest.raises(m.NewruleSubmissionError, match="active_or_ambiguous"):
        m.begin_attempt(s.plan, "R299", 1, **kwargs(s))
    with pytest.raises((m.NewruleSubmissionError, FileNotFoundError)):
        m.begin_attempt(s.plan, "R298", 2, **kwargs(s), prior_failure_sha256="b" * 64,
                        retry_justification_sha256="c" * 64)


def test_busy_begin_does_not_claim_and_can_wait(setup):
    s = setup
    uploaded(s)
    s.api.busy = True
    with pytest.raises(m.NewruleSubmissionError, match="capacity_wait"):
        m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    assert not (m.CONTROL / "R298-A1-claim.json").exists()
    s.clock.now += 60
    s.api.busy = False
    assert m.begin_attempt(s.plan, "R298", 1, **kwargs(s))["shared_look"] == 1


@pytest.mark.parametrize("bad", [True, 0, 4, "1", 1.0])
def test_attempt_exact_bound_before_network(setup, bad):
    s = setup
    uploaded(s)
    calls = len(s.api.calls)
    with pytest.raises(m.NewruleSubmissionError): m.begin_attempt(s.plan, "R298", bad, **kwargs(s))
    assert len(s.api.calls) == calls


@pytest.mark.parametrize("failure", ["mode", "symlink", "hardlink", "json", "extra_json"])
def test_private_control_refusal(setup, failure):
    s = setup
    path = m.CONTROL / "family.json"
    if failure == "mode": path.chmod(0o644)
    elif failure == "symlink":
        saved = path.with_name("saved.json")
        path.rename(saved)
        path.symlink_to(saved)
    elif failure == "hardlink": os.link(path, path.with_name("alias.json"))
    elif failure == "json": path.write_bytes(b'{"x":1,"x":1}\n')
    else: path.write_bytes(path.read_bytes() + b"{}")
    with pytest.raises((m.NewruleSubmissionError, OSError)):
        m.discover_organization(s.plan, **kwargs(s))
    assert not s.api.calls


@pytest.mark.parametrize("unsafe", ["keylog", "debug", "https_debug"])
def test_unsafe_transport_environment_refused(monkeypatch, unsafe):
    if unsafe == "keylog": monkeypatch.setenv("SSLKEYLOGFILE", "synthetic")
    elif unsafe == "debug": monkeypatch.setattr(m.http.client.HTTPConnection, "debuglevel", 1)
    else: monkeypatch.setattr(m.http.client.HTTPSConnection, "debuglevel", 1)
    with pytest.raises(m.NewruleSubmissionError): m._safe_environment()


def test_closure_no_dispatch_fence():
    assert_lane_closure_excludes_dispatch_fence()


@pytest.mark.parametrize("mismatch", [False, True])
def test_whole_family_requires_equal_common_source_path(setup, mismatch):
    s = setup
    uploaded(s)
    def validator(_, *, expected_profile):
        return {"meta": {"package_sha256": expected_profile["package_sha256"],
            "lineage_sha256": expected_profile["lineage_sha256"], "decision_count": 302,
            "evaluation_session_count": 1510,
            "common_source_path_sha256": ("d" if mismatch and expected_profile["ar_percent"] == 200 else "c") * 64},
            "monthly": {}}
    s.monkeypatch.setattr(m.runtime, "validate_result_statistics", validator)
    for candidate, _, _ in m.CELLS:
        launched(s, candidate)
        s.api.status = "Completed."
        m.poll_status_once(s.plan, candidate, 1, **kwargs(s))
        m.read_result_once(s.plan, candidate, 1, **kwargs(s))
    summary = m.summarize_family(s.plan, **kwargs(s))
    assert summary["family_complete"] is True
    assert summary["family_comparable"] is (not mismatch)
    assert summary["comparability_mismatch"] is mismatch
    assert len(summary["completed_cells"]) == 6


def test_reader_real_runtime_validator_integration(setup):
    s = setup
    spec = importlib.util.spec_from_file_location("synthetic_runtime_fixtures", Path(__file__).with_name("test_newrule_runtime_projection.py"))
    fixtures = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixtures
    try:
        spec.loader.exec_module(fixtures)
        stats, _ = fixtures.result_fixture()
    finally:
        sys.modules.pop(spec.name, None)
    profile = m._profile(s.plan._projections[0])
    for name in (m.runtime.META_STATISTIC, m.runtime.MONTHLY_STATISTIC):
        value = json.loads(stats[name])
        for key in ("candidate_id", "profile_sha256", "package_sha256", "lineage_sha256"):
            if key in value:
                value[key] = profile[key]
        stats[name] = m.runtime.targets.canonical(value).decode("ascii")
    s.api.custom = stats
    uploaded(s)
    launched(s)
    s.api.status = "Completed."
    m.poll_status_once(s.plan, "R298", 1, **kwargs(s))
    result = m.read_result_once(s.plan, "R298", 1, **kwargs(s))
    assert result["statistics"]["meta"]["complete_geometry"] is True
    assert len(result["statistics"]["monthly"]["months"]) == 70


def test_malformed_poll_never_retried_as_normal_poll(setup):
    s = setup
    uploaded(s)
    m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    s.api.state = "unknown"
    with pytest.raises(m.NewruleSubmissionError, match="compile_status"):
        m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    s.clock.now += 100
    s.api.state = "BuildSuccess"
    calls = len(s.api.calls)
    with pytest.raises(m.NewruleSubmissionError, match="prior_poll_ambiguous"):
        m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    assert len(s.api.calls) == calls


def test_poll_limits_exact_and_no_busy_loop(setup):
    s = setup
    uploaded(s)
    m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    s.api.state = "Building"
    s.monkeypatch.setattr(m, "COMPILE_POLLS", 2)
    m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    with pytest.raises(m.NewruleSubmissionError, match="wait_before_poll"):
        m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    s.clock.now += 10
    m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))
    s.clock.now += 10
    with pytest.raises(m.NewruleSubmissionError, match="poll_budget"):
        m.poll_compile_once(s.plan, "R298", 1, **kwargs(s))


def test_unexpected_cloud_run_blocks_status(setup):
    s = setup
    uploaded(s)
    launched(s)
    project = next(iter(s.api.runs))
    s.api.runs[project].append({"projectId": project, "backtestId": "other", "name": "other", "status": "InProgress"})
    with pytest.raises(m.NewruleSubmissionError, match="backtest_census"):
        m.poll_status_once(s.plan, "R298", 1, **kwargs(s))


def test_no_late_uploaded_source_change_before_launch(setup):
    s = setup
    uploaded(s)
    receipt = started(s)
    s.api.files[receipt["project_id"]]["main.py"] = "# changed\n"
    with pytest.raises(m.NewruleSubmissionError, match="uploaded_source_mismatch"):
        m.launch_compiled(s.plan, "R298", 1, **kwargs(s))
    assert not any(endpoint == "backtests/create" for endpoint, _ in s.api.calls)


def test_finite_failure_uses_exact_bounded_args_without_repr_or_hash():
    class Hostile(str):
        def __hash__(self): raise AssertionError("hostile hash")
        def __len__(self): raise AssertionError("hostile length")
        def __str__(self): raise AssertionError("hostile string")
    class HostileError(Exception):
        def __str__(self): raise AssertionError("hostile exception")
    for value in (Hostile("request_ambiguous"), "x" * 100000, "SECRET", None, 1):
        assert m.finite_failure(m.NewruleSubmissionError(value)) == "operation_refused"
    assert m.finite_failure(HostileError()) == "operation_refused"
    assert m.finite_failure(m.NewruleSubmissionError("request_ambiguous")) == "request_ambiguous"


@pytest.mark.parametrize("payload,code,category", [
    ({"error": "NewruleError: missing_clock_bar"}, "missing_clock_bar", None),
    ({"errorMessage": "Runtime Error: NewruleError: source_census"}, "source_census", None),
    ({"errors": ["SyntaxError: NEVER-PRINT"]}, None, "SyntaxError"),
    ({"error": "NEVER-PRINT-SECRET"}, None, None),
    ({"errors": ["source_census", "missing_clock_bar"]}, None, None),
    ({"error": "source_census" + "x" * 10000}, None, None),
])
def test_finite_known_error_evidence_only(payload, code, category):
    result = m._failure_evidence(payload, "runtime_error")
    assert result["known_runtime_code"] == code and result["python_error_category"] == category
    assert result["raw_error_retained"] is result["cause_authenticated"] is False
    assert b"NEVER-PRINT" not in m._canonical(result)


def test_selected_sources_require_exact_inventory_and_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "HOST_SOURCE_NAMES", ("one.py",))
    (tmp_path / "one.py").write_bytes(b"# synthetic source\n")
    m._sources({"one.py": sha(b"# synthetic source\n")})
    for pins in ({}, {"extra.py": "a" * 64}, {"one.py": "a" * 64}):
        with pytest.raises(m.NewruleSubmissionError): m._sources(pins)


def test_family_profiles_must_have_identical_full_geometry(setup):
    s = setup
    original = m.projection.build_projection
    def altered(*args, **kwargs):
        item = original(*args, **kwargs)
        if kwargs["universe_count"] == 8:
            profile = json.loads(item.profile_bytes)
            profile["clock"] = "different_geometry"
            profile.pop("profile_sha256")
            profile["profile_sha256"] = m.runtime.targets.digest(profile)
            record = item.to_record()
            record["profile_sha256"] = profile["profile_sha256"]
            raw = m.runtime.targets.canonical(record)
            item = m.projection.Projection(raw, sha(raw), item.source_files, m.runtime.targets.canonical(profile))
        return item
    s.monkeypatch.setattr(m.projection, "build_projection", altered)
    with pytest.raises(m.NewruleSubmissionError, match="family_geometry"):
        m._build(s.value, {}, {})
    assert not s.api.calls


def test_failure_inventory_is_static_and_covers_own_refusals():
    import ast
    tree = ast.parse(Path(m.__file__).read_bytes())
    literals = {node.args[-1].value for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id in {"_require", "NewruleSubmissionError"}
        and node.args and isinstance(node.args[-1], ast.Constant) and type(node.args[-1].value) is str}
    assert literals <= m.FINITE_REFUSAL_CODES


@pytest.mark.parametrize("filename,key,bad", [("family.json", "formal_forward_ready", 0),
    ("R298-profile.json", "whole_shares", 1), ("R298-projection.json", "paper_or_live_ready", 0)])
def test_prepared_external_bindings_reject_boolean_integer_aliases(setup, filename, key, bad):
    s = setup
    path = m.CONTROL / filename
    value = json.loads(path.read_bytes())
    value[key] = bad
    path.write_bytes(m._canonical(value))
    with pytest.raises(m.NewruleSubmissionError, match="prepared_"):
        m.discover_organization(s.plan, **kwargs(s))
    assert not s.api.calls


@pytest.mark.parametrize("phase", ["files", "compile"])
def test_cloud_project_float_aliases_refuse(setup, phase):
    s = setup
    uploaded(s)
    def mutate(endpoint, value):
        if phase == "files" and endpoint == "files/read":
            for row in value["files"]: row["projectId"] = float(row["projectId"])
        elif phase == "compile" and endpoint == "compile/create":
            value["projectId"] = float(value["projectId"])
    s.api.mutate = mutate
    with pytest.raises(m.NewruleSubmissionError): m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    assert (m.CONTROL / "R298-A1-claim.json").exists()


def test_second_launch_never_creates_a_second_backtest(setup):
    # Section 301 (ARV2R301-009): the exclusive backtest-create intent is the
    # only guard against a second create for the same cell attempt.
    s = setup
    uploaded(s)
    launched(s)
    assert sum(endpoint == "backtests/create" for endpoint, _ in s.api.calls) == 1
    s.clock.now += 60
    with pytest.raises((m.NewruleSubmissionError, FileExistsError)):
        m.launch_compiled(s.plan, "R298", 1, **kwargs(s))
    assert sum(endpoint == "backtests/create" for endpoint, _ in s.api.calls) == 1
    assert len(s.api.runs[next(iter(s.api.runs))]) == 1


@pytest.mark.parametrize("shape,code", [("unexpected_name", "fresh_project_files"),
                                        ("too_many", "fresh_project_files"),
                                        ("duplicate", "duplicate_cloud_file")])
def test_unexpected_or_duplicate_fresh_files_refuse_before_any_delete(setup, shape, code):
    # Section 301 (ARV2R301-009): files/delete may remove only research.ipynb from
    # a fresh project holding at most main.py and research.ipynb, each once.
    s = setup
    uploaded(s)

    def mutate(endpoint, result):
        if endpoint != "files/read" or not result.get("files"):
            return
        rows = {row["name"]: row for row in result["files"]}
        notebook = dict(rows["research.ipynb"])
        if shape == "unexpected_name":
            result["files"] = [dict(notebook, name="other.py"), notebook]
        elif shape == "too_many":
            result["files"] = [*result["files"], dict(notebook, name="other.py")]
        else:
            result["files"] = [notebook, dict(notebook)]

    s.api.mutate = mutate
    with pytest.raises(m.NewruleSubmissionError, match=code):
        m.begin_attempt(s.plan, "R298", 1, **kwargs(s))
    assert not any(endpoint == "files/delete" for endpoint, _ in s.api.calls)
    assert not any(endpoint in {"files/create", "files/update", "compile/create"} for endpoint, _ in s.api.calls)
