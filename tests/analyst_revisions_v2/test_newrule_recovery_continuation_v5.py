"""V5 synthetic controls/fake transport only; never operational evidence."""
import ast
import copy
import importlib.util
import inspect
import json
import socket
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts import arv2_newrule_recovery_continuation_v5 as c
from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

old = c.old
REAL_DIRECTORY = old._Directory
REAL_DIRECTORY_INIT = REAL_DIRECTORY.__init__
REAL_CLIENT_INIT = old.QuantConnectClient.__init__
REAL_PRODUCTION_CLIENT = old.coverage.production_client
RECEIPT = "b" * 64
BASE_SPEC = importlib.util.spec_from_file_location("_newrule_v5_synthetic_base",
    Path(__file__).with_name("test_newrule_submission.py"))
base = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(base)


@pytest.fixture(autouse=True)
def isolation(monkeypatch, tmp_path):
    violations = []
    def forbidden(*_a, **_k):
        violations.append("operational_boundary")
        pytest.fail("operational boundary forbidden")
    def directory_init(self, *args, **kwargs):
        if not (old.ROOT == tmp_path and old.CONTROL == tmp_path / "artifacts/test-family"
                and Path.cwd() == tmp_path):
            forbidden()
        return REAL_DIRECTORY_INIT(self, *args, **kwargs)
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", directory_init)
    monkeypatch.setattr(old.QuantConnectClient, "__init__", forbidden)
    monkeypatch.setattr(old.coverage, "production_client", forbidden)
    monkeypatch.setattr(old.coverage, "_bounded_transport", forbidden)
    monkeypatch.setattr(old.october, "load_october_order_input_package", forbidden)
    monkeypatch.setattr(old.compact, "load_accepted_risk_preliminary_package", forbidden)
    for owner, names in ((socket, ("create_connection", "getaddrinfo")),
                         (socket.socket, ("connect", "connect_ex")),
                         (urllib.request.OpenerDirector, ("open",)),
                         (old.http.client.HTTPConnection, ("request", "connect")),
                         (old.http.client.HTTPSConnection, ("connect",))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "swallowed operational boundary"


@pytest.fixture
def setup(monkeypatch, tmp_path):
    value = base.setup.__wrapped__(monkeypatch, tmp_path)
    old.discover_organization(value.plan, expected_family_sha256=value.plan.family_sha256)
    value.api.calls.clear()
    value.sessions, value.active, value.admissions, value.environment_checks = [], [], [], []
    real_session = old._session
    @contextmanager
    def session(*args):
        with real_session(*args) as pair:
            value.sessions.append(pair[0])
            value.active.append(pair[0])
            try:
                yield pair
            finally:
                value.active.remove(pair[0])
    monkeypatch.setattr(old, "_session", session)
    def admission(directory, plan, record, digest):
        assert value.active == [directory] and plan is value.plan and digest == RECEIPT
        assert record == old._parse(plan.record_bytes)
        assert "upload-valid.json" not in directory.names()
        value.admissions.append(directory)
    monkeypatch.setattr(c.recovery, "require_admission", admission)
    def safe():
        value.environment_checks.append(True)
    monkeypatch.setattr(c.environment, "require_safe_environment", safe)
    class SyntheticGuarded:
        def request(self, endpoint, payload):
            assert len(value.active) == 1 and value.admissions[-1] is value.active[0]
            safe()
            return value.api.request(endpoint, payload)
    def client():
        assert len(value.active) == 1 and value.admissions[-1] is value.active[0]
        safe()
        return SyntheticGuarded()
    monkeypatch.setattr(c.environment, "guarded_client", client)
    for name in ("_client", "_uploaded", "upload_inputs", "prepare_family", "discover_organization",
                 "capacity_once", "begin_attempt", "poll_compile_once", "launch_compiled", "poll_status_once",
                 "read_result_once", "summarize_family"):
        monkeypatch.setattr(old, name, lambda *_a, **_k: pytest.fail("legacy lifecycle or credential bypass"))
    def validate(stats, *, expected_profile):
        assert set(stats) == {old.runtime.META_STATISTIC, old.runtime.MONTHLY_STATISTIC}
        assert stats == {old.runtime.META_STATISTIC: "{}", old.runtime.MONTHLY_STATISTIC: "{}"}
        return {"meta": {"common_source_path_sha256": "c" * 64,
            "package_sha256": old.PACKAGE_SHA256, "lineage_sha256": old.LINEAGE_SHA256,
            "decision_count": 300, "evaluation_session_count": 1500}, "synthetic_only": True}
    monkeypatch.setattr(old.runtime, "validate_result_statistics", validate)
    return value


def call(value, operation, candidate="R298", attempt=1, **extra):
    if operation in {"capacity", "summarize"}:
        candidate, attempt = None, None
    return c.dispatch(operation, value.plan, candidate, attempt,
        expected_family_sha256=value.plan.family_sha256, expected_receipt_sha256=RECEIPT, **extra)


def prepared(value):
    call(value, "begin")
    call(value, "compile")


def launched(value):
    prepared(value)
    call(value, "launch")


def completed(value):
    launched(value)
    value.api.status = "Completed."
    call(value, "status")


def write(name, value):
    with old._Directory() as directory:
        directory.write(name, value)


def load(name):
    with old._Directory() as directory:
        return directory.read(name)


def names():
    with old._Directory() as directory:
        return set(directory.names())


def test_isolation_identity_and_direct_constructor_tripwire(isolation):
    assert old._Directory.__init__ is not REAL_DIRECTORY_INIT
    assert old.QuantConnectClient.__init__ is not REAL_CLIENT_INIT
    assert old.coverage.production_client is not REAL_PRODUCTION_CLIENT
    with pytest.raises(pytest.fail.Exception, match="operational boundary forbidden"):
        old._Directory()
    assert isolation == ["operational_boundary"]
    isolation.clear()


def test_full_six_cell_lifecycle_same_session_and_unchanged_accounting(setup):
    value = setup
    assert call(value, "capacity")["state"] == "available"
    for candidate, size, arm in old.CELLS:
        first = call(value, "begin", candidate)
        assert first["attempt_id"] == candidate + "-A1"
        assert [first[key] for key in ("shared_look", "development_look", "infrastructure_look", "result_cell")] == [1, 1, 0, 0]
        assert call(value, "compile", candidate)["status"] == "BuildSuccess"
        call(value, "launch", candidate)
        value.api.status = "Completed."
        assert call(value, "status", candidate)["status"] == "Completed."
        result = call(value, "read", candidate)
        assert result["result_cell"] == 1 and result["family_comparable"] is False
        summary = call(value, "summarize")
        assert summary["completed_cells"][-1] == candidate
    assert summary["family_complete"] and summary["family_comparable"]
    assert summary["paper_or_live_ready"] is summary["formal_forward_ready"] is False
    assert summary["actual_action_exit_confirmation_required"] is True
    assert len(value.sessions) == 37 and len(value.admissions) == 74
    assert all(value.admissions[2 * index] is held is value.admissions[2 * index + 1]
               for index, held in enumerate(value.sessions))
    assert len([entry for entry in value.api.calls if entry[0] == "projects/create"]) == 6
    assert len([entry for entry in value.api.calls if entry[0] == "backtests/create"]) == 6
    assert "upload-valid.json" not in names()
    assert not any("A2" in name or "A3" in name for name in names())


@pytest.mark.parametrize("operation", c.OPERATIONS)
def test_admission_refusal_before_client_or_control_write(setup, monkeypatch, operation):
    def refuse(*args):
        raise old.NewruleSubmissionError("synthetic_refusal")
    monkeypatch.setattr(c.recovery, "require_admission", refuse)
    monkeypatch.setattr(c.environment, "guarded_client", lambda: pytest.fail("credential reached"))
    before = names()
    with pytest.raises(old.NewruleSubmissionError, match="synthetic_refusal"):
        call(setup, operation)
    assert names() == before and setup.api.calls == []


@pytest.mark.parametrize("operation", c.OPERATIONS)
def test_environment_refusal_precedes_session_and_sources(setup, monkeypatch, operation):
    monkeypatch.setattr(c.environment, "require_safe_environment", lambda: (_ for _ in ()).throw(c.environment.EnvironmentRefused("finite")))
    monkeypatch.setattr(old, "_session", lambda *_: pytest.fail("private session reached"))
    with pytest.raises(c.environment.EnvironmentRefused):
        call(setup, operation)


@pytest.mark.parametrize("operation,candidate,attempt", [
    ("upload", None, None), (None, None, None), (True, None, None),
    ("begin", "R298", 2), ("begin", "R298", 3), ("begin", "R298", True),
    ("begin", "R247", 1), ("capacity", "R298", 1), ("summarize", None, 1)])
def test_no_legacy_routes_retries_or_bool_aliases(setup, operation, candidate, attempt):
    with pytest.raises(old.NewruleSubmissionError):
        c.dispatch(operation, setup.plan, candidate, attempt,
            expected_family_sha256=setup.plan.family_sha256, expected_receipt_sha256=RECEIPT)
    assert not setup.sessions and not setup.api.calls


@pytest.mark.parametrize("phase", ["capacity", "begin", "launch"])
def test_busy_batches_complete_without_attempt_or_launch_and_wait_before_next(setup, phase):
    value = setup
    if phase == "launch":
        prepared(value)
    value.api.busy = True
    result = call(value, phase)
    assert result["state"] == "wait" and result["available_count"] == 0
    assert not any(name.endswith("-launch.json") for name in names())
    if phase != "launch":
        assert "R298-A1-claim.json" not in names()
    calls = copy.deepcopy(value.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="wait_before_poll"):
        call(value, phase)
    assert value.api.calls == calls
    value.clock.now += old.STATUS_INTERVAL
    value.api.busy = False
    assert call(value, phase).get("state") != "wait"


@pytest.mark.parametrize("phase,endpoint", [
    ("capacity", "projects/read"), ("capacity", "projects/nodes/read"),
    ("begin", "projects/read"), ("begin", "projects/nodes/read"),
    ("begin", "projects/create"), ("begin", "backtests/list"), ("begin", "files/read"),
    ("begin", "files/delete"), ("begin", "files/update"), ("begin", "compile/create"),
    ("compile", "compile/read"), ("launch", "projects/read"), ("launch", "files/read"),
    ("launch", "projects/nodes/read"), ("launch", "backtests/create"),
    ("status", "backtests/list"), ("read", "projects/read"), ("read", "files/read"), ("read", "backtests/read")])
def test_every_ambiguous_request_fences_all_further_network_without_repair(setup, phase, endpoint):
    value = setup
    if phase == "compile": call(value, "begin")
    if phase == "launch": prepared(value)
    if phase == "status": launched(value)
    if phase == "read": completed(value)
    value.api.failure = endpoint
    with pytest.raises(old.NewruleSubmissionError, match="request_ambiguous"):
        call(value, phase)
    evidence = names()
    calls = copy.deepcopy(value.api.calls)
    value.api.failure = None
    value.clock.now += 10000
    for operation in c.OPERATIONS:
        with pytest.raises(old.NewruleSubmissionError, match="prior_poll_ambiguous"):
            call(value, operation)
    assert value.api.calls == calls and names() == evidence


@pytest.mark.parametrize("foreign", ["capacity-001-project-intent.json", "capacity-001-valid.json",
    "R298-A1-capacity-001-reference-intent.json", "R298-A1-launch-capacity-001-files-observed.json",
    "R298-A1-backtest-create-intent.json", "R298-A1-launch.json", "R298-A2-claim.json",
    "R299-project.json", "v5-capacity-001-project-intent.json", "v5-unknown.json"])
@pytest.mark.parametrize("initialized", [False, True])
def test_unowned_legacy_or_orphan_suffix_evidence_never_reinterpreted(setup, foreign, initialized):
    if initialized: call(setup, "capacity")
    if foreign in names(): foreign = foreign.replace("001", "003")
    write(foreign, {"synthetic": True})
    setup.clock.now += old.STATUS_INTERVAL
    calls = copy.deepcopy(setup.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="mixed_lifecycle_state"):
        call(setup, "capacity")
    assert setup.api.calls == calls


@pytest.mark.parametrize("phase", ["compile", "status"])
def test_poll_interval_and_complete_contiguous_groups_only(setup, phase):
    value = setup
    if phase == "compile":
        call(value, "begin")
        value.api.state = "Building"
    else:
        launched(value)
    first = call(value, phase)
    before = copy.deepcopy(value.api.calls)
    interval = old.COMPILE_INTERVAL if phase == "compile" else old.STATUS_INTERVAL
    value.clock.now += interval - 1
    with pytest.raises(old.NewruleSubmissionError, match="wait_before_poll"):
        call(value, phase)
    assert value.api.calls == before
    value.clock.now += 1
    assert call(value, phase) == first
    group = f"v5-R298-A1-{phase}"
    assert group + "-002-batch-complete.json" in names()


def test_launch_reentry_refuses_before_client_or_remote(setup, monkeypatch):
    launched(setup)
    setup.clock.now += old.STATUS_INTERVAL
    before = copy.deepcopy(setup.api.calls)
    monkeypatch.setattr(c.environment, "guarded_client", lambda: pytest.fail("duplicate launch client"))
    with pytest.raises(old.NewruleSubmissionError, match="attempt_spent"):
        call(setup, "launch")
    assert setup.api.calls == before


def test_result_reentry_refuses_before_client_or_remote(setup, monkeypatch):
    completed(setup)
    call(setup, "read")
    before = copy.deepcopy(setup.api.calls)
    monkeypatch.setattr(c.environment, "guarded_client", lambda: pytest.fail("duplicate result client"))
    with pytest.raises(old.NewruleSubmissionError, match="attempt_spent"):
        call(setup, "read")
    assert setup.api.calls == before


@pytest.mark.parametrize("candidate", ["R299", "R300", "R301", "R302", "R303"])
def test_candidate_order_refuses_before_claim_or_client(setup, candidate):
    with pytest.raises(old.NewruleSubmissionError, match="candidate_order"):
        call(setup, "begin", candidate)
    assert not setup.api.calls and c.ROOT_RECEIPT not in names()


@pytest.mark.parametrize("failure", ["BuildError", "Runtime Error"])
def test_real_failed_terminal_does_not_allow_retry_or_next_candidate(setup, failure):
    if failure == "BuildError":
        call(setup, "begin")
        setup.api.state = failure
        result = call(setup, "compile")
    else:
        launched(setup)
        setup.api.status = failure
        result = call(setup, "status")
    assert result["status"] == failure
    before = copy.deepcopy(setup.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="candidate_order"):
        call(setup, "begin", "R299")
    with pytest.raises(old.NewruleSubmissionError, match="attempt_spent"):
        call(setup, "begin")
    with pytest.raises(old.NewruleSubmissionError, match="candidate_attempt"):
        call(setup, "begin", attempt=2)
    assert setup.api.calls == before


@pytest.mark.parametrize("value", [True, 1000.0, 1001, "1000"])
def test_compile_read_project_binding_exact_when_present(setup, value):
    call(setup, "begin")
    setup.api.mutate = lambda endpoint, response: response.update(projectId=value) if endpoint == "compile/read" else None
    with pytest.raises(old.NewruleSubmissionError, match="compile_status"):
        call(setup, "compile")
    assert "R298-A1-compile-ready.json" not in names()


@pytest.mark.parametrize("postcheck", ["admission", "source", "prepared", "environment"])
def test_failed_postcheck_after_terminal_keeps_incomplete_global_fence(setup, monkeypatch, postcheck):
    value = setup
    launched(value)
    value.api.status = "Completed."
    original = {"admission": c.recovery.require_admission, "source": old.require_family,
                "prepared": old._bound, "environment": c.environment.require_safe_environment}[postcheck]
    counter = []
    def broken(*args, **kwargs):
        # The terminal appears during the operation, after initial preflight.
        if (old.CONTROL / "R298-A1-terminal.json").exists():
            raise old.NewruleSubmissionError("synthetic_postcheck")
        counter.append(True)
        return original(*args, **kwargs)
    owner, name = {"admission": (c.recovery, "require_admission"), "source": (old, "require_family"),
                   "prepared": (old, "_bound"), "environment": (c.environment, "require_safe_environment")}[postcheck]
    monkeypatch.setattr(owner, name, broken)
    with pytest.raises(old.NewruleSubmissionError, match="synthetic_postcheck"):
        call(value, "status")
    monkeypatch.setattr(owner, name, original)
    assert "R298-A1-terminal.json" in names()
    assert "v5-R298-A1-status-001-batch-complete.json" not in names()
    before = copy.deepcopy(value.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="prior_poll_ambiguous"):
        call(value, "read")
    assert value.api.calls == before


@pytest.mark.parametrize("filename", ["v5-capacity-001-project-intent.json", "v5-capacity-001-observed.json",
    "v5-capacity-001-valid.json"])
def test_prior_completed_output_change_refuses_before_credentials(setup, filename):
    call(setup, "capacity")
    path = old.CONTROL / filename
    value = json.loads(path.read_bytes())
    value["synthetic_changed"] = True
    path.write_bytes(old._canonical(value))
    setup.clock.now += old.STATUS_INTERVAL
    before = copy.deepcopy(setup.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="batch_output_changed"):
        call(setup, "capacity")
    assert setup.api.calls == before


@pytest.mark.parametrize("missing", ["v5-capacity-001-project-observed.json", "v5-capacity-001-valid.json",
    "v5-capacity-001-batch-complete.json"])
def test_missing_evidence_cannot_release_next_poll(setup, missing):
    call(setup, "capacity")
    # Deliberately remove only a synthetic tmp_path fixture to model a loss.
    (old.CONTROL / missing).unlink()
    before = copy.deepcopy(setup.api.calls)
    setup.clock.now += old.STATUS_INTERVAL
    with pytest.raises(old.NewruleSubmissionError, match="prior_poll_ambiguous|batch_output_changed"):
        call(setup, "capacity")
    assert setup.api.calls == before


def test_schema_profile_and_single_public_dispatch_have_no_old_delegation():
    source = inspect.getsource(c)
    tree = ast.parse(source)
    public = {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")}
    assert public == {"dispatch", "finite_failure"}
    assert c.PROFILE_SHA256 == old._sha(old._canonical(c.PROFILE))
    assert c.PROFILE["attempt"] == 1 and c.PROFILE["candidate_order"] == [row[0] for row in old.CELLS]
    forbidden = {"prepare_family", "load_family", "upload_inputs", "discover_organization", "capacity_once",
        "begin_attempt", "poll_compile_once", "launch_compiled", "poll_status_once", "read_result_once", "summarize_family",
        "_client", "_next", "_uploaded"}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "old" and node.func.attr in forbidden for node in calls)
    assert len([node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "_session"]) == 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assert not any(isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)
                and item.value.id in {"old", "recovery", "environment"} for item in targets)
    assert_lane_closure_excludes_dispatch_fence()


def test_finite_new_refusals_do_not_render_opaque_errors():
    tree = ast.parse(inspect.getsource(c))
    literals = {node.args[-1].value for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "_require"
        and isinstance(node.args[-1], ast.Constant) and type(node.args[-1].value) is str}
    assert literals <= c.FINITE_CODES
    for literal in literals:
        assert c.finite_failure(old.NewruleSubmissionError(literal)) == literal
    class Opaque:
        def __repr__(self): pytest.fail("opaque repr")
        def __str__(self): pytest.fail("opaque str")
    assert c.finite_failure(Opaque()) == "operation_refused"
    assert c.finite_failure(ValueError("NEVER PRINT")) == "operation_refused"


def test_cooperative_lock_contention_refuses_before_admission_claim_or_credentials(setup):
    value = setup
    with old._Directory() as held, c._locked(held):
        before = names()
        with pytest.raises(old.NewruleSubmissionError, match="continuation_busy"):
            call(value, "capacity")
        assert names() == before and value.admissions == [] and value.api.calls == []
    assert call(value, "capacity")["state"] == "available"


def test_lock_releases_on_exception_without_renewing_incomplete_claim(setup):
    setup.api.failure = "projects/read"
    with pytest.raises(old.NewruleSubmissionError, match="request_ambiguous"):
        call(setup, "capacity")
    with old._Directory() as held, c._locked(held):
        assert held.fd >= 0
    with pytest.raises(old.NewruleSubmissionError, match="prior_poll_ambiguous"):
        call(setup, "capacity")


@pytest.mark.parametrize("change", ["empty", "missing_observed", "extra", "bool_outcome", "false_wait"])
def test_malformed_completed_batch_cannot_authorize_next_action(setup, change):
    call(setup, "capacity")
    path = old.CONTROL / "v5-capacity-001-batch-complete.json"
    value = json.loads(path.read_bytes())
    if change == "empty": value["outputs"] = {}
    elif change == "missing_observed": value["outputs"].pop("v5-capacity-001-project-observed.json")
    elif change == "extra": value["outputs"]["foreign.json"] = "a" * 64
    elif change == "bool_outcome": value["outcome"] = True
    else: value["outcome"] = "BuildSuccess"
    path.write_bytes(old._canonical(value))
    before = copy.deepcopy(setup.api.calls)
    setup.clock.now += old.STATUS_INTERVAL
    with pytest.raises(old.NewruleSubmissionError, match="batch_completion"):
        call(setup, "capacity")
    assert setup.api.calls == before


@pytest.mark.parametrize("operation,outcome", [("capacity", "wait"), ("begin", "wait"), ("begin", "success"),
    ("compile", "Building"), ("compile", "BuildSuccess"), ("compile", "BuildError"),
    ("launch", "wait"), ("launch", "success"), ("status", "InProgress"),
    ("status", "Completed."), ("status", "Runtime Error"), ("read", "success")])
def test_completion_inventory_rejects_missing_required_rpc_pairs(setup, operation, outcome):
    item = setup.plan._projections[0]
    marker = c._stem(operation, None if operation == "capacity" else "R298") + "-001"
    allowed = c._allowed(operation, marker, "R298", item)
    assert not c._outputs_match(operation, marker, "R298", allowed, set(), outcome)
    assert not c._outputs_match(operation, marker, "R298", allowed, {"unexpected.json"}, outcome)


def test_begin_optional_notebook_delete_requires_both_request_markers(setup):
    marker = "v5-R298-A1-begin-001"
    allowed = c._allowed("begin", marker, "R298", setup.plan._projections[0])
    pair = c._rpc_names(marker + "-delete-default-notebook")
    assert c._outputs_match("begin", marker, "R298", allowed, allowed, "success")
    assert c._outputs_match("begin", marker, "R298", allowed, allowed - pair, "success")
    assert not c._outputs_match("begin", marker, "R298", allowed,
        allowed - {marker + "-delete-default-notebook-observed.json"}, "success")


def test_missing_native_lock_refuses_before_private_session(setup, monkeypatch):
    monkeypatch.setattr(c, "fcntl", None)
    monkeypatch.setattr(old, "_session", lambda *_: pytest.fail("private session reached"))
    with pytest.raises(old.NewruleSubmissionError, match="native_lock_unavailable"):
        call(setup, "capacity")


def test_finite_failure_length_refusal_precedes_inventory_lookup(monkeypatch):
    class Tripwire:
        def __contains__(self, value): pytest.fail("oversized inventory lookup")
    monkeypatch.setattr(c, "FINITE_CODES", Tripwire())
    assert c.finite_failure(old.NewruleSubmissionError("x" * 65)) == "operation_refused"


def test_prior_completed_evidence_changed_during_action_refuses_completion(setup):
    call(setup, "capacity")
    setup.clock.now += old.STATUS_INTERVAL
    def mutate(endpoint, response):
        if endpoint == "projects/nodes/read":
            path = old.CONTROL / "v5-capacity-001-valid.json"
            value = json.loads(path.read_bytes())
            value["synthetic_changed"] = True
            path.write_bytes(old._canonical(value))
    setup.api.mutate = mutate
    with pytest.raises(old.NewruleSubmissionError, match="batch_output_changed"):
        call(setup, "capacity")
    assert "v5-capacity-002-batch-claim.json" in names()
    assert "v5-capacity-002-batch-complete.json" not in names()


@pytest.mark.parametrize("operation", ["capacity", "compile", "status"])
def test_original_bounded_poll_budget_is_not_reset(setup, monkeypatch, operation):
    if operation == "compile":
        call(setup, "begin")
        setup.api.state = "Building"
    elif operation == "status":
        launched(setup)
    monkeypatch.setattr(old, "COMPILE_POLLS" if operation == "compile" else "STATUS_POLLS", 2)
    for _ in range(2):
        call(setup, operation)
        setup.clock.now += old.STATUS_INTERVAL
    before = copy.deepcopy(setup.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="poll_budget"):
        call(setup, operation)
    assert setup.api.calls == before


def test_gap_in_complete_group_ordinals_refuses_even_when_claim_hash_matches(setup):
    call(setup, "capacity")
    original = "v5-capacity-001"
    replacement = "v5-capacity-003"
    for path in sorted(old.CONTROL.glob(original + "*.json")):
        path.rename(path.with_name(path.name.replace(original, replacement)))
    claim_path = old.CONTROL / (replacement + "-batch-claim.json")
    claim = json.loads(claim_path.read_bytes())
    claim["ordinal"] = 3
    claim["allowed_outputs"] = [name.replace(original, replacement) for name in claim["allowed_outputs"]]
    claim_path.write_bytes(old._canonical(claim))
    completion_path = old.CONTROL / (replacement + "-batch-complete.json")
    completion = json.loads(completion_path.read_bytes())
    completion["claim_sha256"] = old._sha(old._canonical(claim))
    completion["outputs"] = {name.replace(original, replacement): digest for name, digest in completion["outputs"].items()}
    completion_path.write_bytes(old._canonical(completion))
    before = copy.deepcopy(setup.api.calls)
    with pytest.raises(old.NewruleSubmissionError, match="poll_budget"):
        call(setup, "capacity")
    assert setup.api.calls == before
