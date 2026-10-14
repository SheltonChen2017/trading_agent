"""Synthetic continuation parity; no private inputs, credentials or real QC."""
import ast
import copy
import importlib.util
import inspect
import socket
import sys
from pathlib import Path
import urllib.request

import pytest

from scripts import arv2_newrule_recovery_continuation as c

old = c.old
REAL_DIRECTORY = old._Directory
REAL_DIRECTORY_INIT = REAL_DIRECTORY.__init__
REAL_CLIENT = old.QuantConnectClient
RECEIPT = "b" * 64
BASE_SPEC = importlib.util.spec_from_file_location("_newrule_continuation_fixture_only",
    Path(__file__).with_name("test_newrule_submission.py"))
base = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(base)


@pytest.fixture(autouse=True)
def operational_guards(monkeypatch, tmp_path):
    violations = []
    def forbidden(*_a, **_k):
        violations.append("operational_boundary")
        pytest.fail("operational access forbidden")
    def directory_init(self, *args, **kwargs):
        # The inherited synthetic fixture uses a real _Directory only under
        # this exact pytest-owned root. Check before its first os.open, even
        # if an imported class alias bypasses a module-level replacement.
        if not (old.ROOT == tmp_path and old.CONTROL == tmp_path / "artifacts/test-family"
                and Path.cwd() == tmp_path):
            forbidden()
        return REAL_DIRECTORY_INIT(self, *args, **kwargs)
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", directory_init)
    monkeypatch.setattr(REAL_CLIENT, "__init__", forbidden)
    monkeypatch.setattr(old.coverage, "production_client", forbidden)
    monkeypatch.setattr(old.october, "load_october_order_input_package", forbidden)
    monkeypatch.setattr(old.compact, "load_accepted_risk_preliminary_package", forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(old.http.client.HTTPConnection, "request", forbidden)
    monkeypatch.setattr(old.http.client.HTTPConnection, "connect", forbidden)
    monkeypatch.setattr(old.http.client.HTTPSConnection, "connect", forbidden)
    for obj, names in ((socket, ("create_connection", "getaddrinfo")),
                       (socket.socket, ("connect", "connect_ex"))):
        for name in names: monkeypatch.setattr(obj, name, forbidden)
    yield violations
    assert violations == [], "an operational boundary guard was reached"


@pytest.fixture
def setup(monkeypatch, tmp_path):
    value = base.setup.__wrapped__(monkeypatch, tmp_path)
    old.discover_organization(value.plan, expected_family_sha256=value.plan.family_sha256)
    value.api.calls.clear()
    value.admissions = []
    def admission(directory, plan, record, digest):
        assert plan is value.plan and record == old._parse(plan.record_bytes)
        assert digest == RECEIPT
        assert "upload-valid.json" not in directory.names()
        value.admissions.append(digest)
        return {"synthetic_only": True}
    monkeypatch.setattr(c.recovery, "require_admission", admission)
    def old_uploaded_forbidden(*_):
        pytest.fail("legacy upload receipt path forbidden")
    monkeypatch.setattr(old, "_uploaded", old_uploaded_forbidden)
    for name in ("upload_inputs", "prepare_family", "discover_organization"):
        monkeypatch.setattr(old, name, lambda *_a, **_k: pytest.fail("old preparation/upload route forbidden"))
    real_client = old._client
    def client():
        assert value.admissions, "credentials before sidecar admission"
        return real_client()
    monkeypatch.setattr(old,"_client",client)
    return value


def bindings(value):
    return dict(expected_family_sha256=value.plan.family_sha256, expected_receipt_sha256=RECEIPT)


def test_capacity_observation_wait_and_no_claim_when_occupied(setup):
    value = setup
    value.api.busy = True
    result = c.capacity_once(value.plan, **bindings(value))
    assert result["state"] == "wait" and result["available_count"] == 0
    assert value.admissions == [RECEIPT]
    assert [endpoint for endpoint,_ in value.api.calls] == ["projects/read","projects/nodes/read"]
    assert not list(old.CONTROL.glob("R*-claim.json"))
    assert not (old.CONTROL / "upload-valid.json").exists()


@pytest.mark.parametrize("candidate,size,arm",old.CELLS)
def test_begin_preserves_exact_cell_sources_claim_and_look(setup,candidate,size,arm):
    value=setup
    result=c.begin_attempt(value.plan,candidate,1,**bindings(value))
    assert result["candidate_id"]==candidate and result["attempt_id"]==candidate+"-A1"
    assert (result["shared_look"],result["development_look"],result["infrastructure_look"],result["result_cell"])==(1,1,0,0)
    record=old._parse(value.plan.record_bytes)
    cell=next(row for row in record["cells"] if row["candidate_id"]==candidate)
    assert result["projection_sha256"]==cell["projection_sha256"]
    assert result["profile_sha256"]==cell["profile_sha256"]
    assert value.api.files[result["project_id"]]=={"main.py":"# synthetic only\n"}
    assert not (old.CONTROL/"upload-valid.json").exists()
    assert (old.CONTROL/(candidate+"-A1-claim.json")).is_file()
    with pytest.raises(old.NewruleSubmissionError,match="another_attempt_active_or_ambiguous|attempt_spent"):
        c.begin_attempt(value.plan,candidate,1,**bindings(value))
    assert len([x for x in value.api.calls if x[0]=="projects/create"])==1


@pytest.mark.parametrize("operation",c.OPERATIONS)
def test_sidecar_refusal_before_any_credential_or_lifecycle_call(setup,monkeypatch,operation):
    value=setup
    def refused(*_): raise old.NewruleSubmissionError("synthetic_admission_refusal")
    monkeypatch.setattr(c.recovery,"require_admission",refused)
    monkeypatch.setattr(old,"_client",lambda:pytest.fail("credentials after refusal"))
    extra={} if operation in ("capacity","summarize") else dict(candidate_id="R298",attempt=1)
    before=tuple(sorted(x.name for x in old.CONTROL.iterdir()))
    with pytest.raises(old.NewruleSubmissionError,match="synthetic_admission_refusal"):
        c.dispatch(operation,value.plan,**extra,**bindings(value))
    assert value.api.calls==[]
    assert tuple(sorted(x.name for x in old.CONTROL.iterdir()))==before


@pytest.mark.parametrize("operation,function",[("compile","poll_compile_once"),("launch","launch_compiled"),
    ("status","poll_status_once"),("read","read_result_once"),("summarize","summarize_family")])
def test_downstream_delegation_has_only_exact_legacy_arguments(setup,monkeypatch,operation,function):
    value=setup
    received=[]
    sentinel=object()
    def selected(plan,*args,**kwargs):
        assert value.admissions==[RECEIPT]
        assert plan is value.plan
        assert args==(() if operation=="summarize" else ("R298",1))
        assert kwargs==dict(expected_family_sha256=value.plan.family_sha256)
        received.append(True)
        return sentinel
    monkeypatch.setattr(old,function,selected)
    extra={} if operation=="summarize" else dict(candidate_id="R298",attempt=1)
    assert c.dispatch(operation,value.plan,**extra,**bindings(value)) is sentinel
    assert received==[True] and value.api.calls==[]


@pytest.mark.parametrize("operation",["prepare","organization","upload","unknown",None,False,1,[]])
def test_unavailable_routes_refuse_without_admission(setup,operation):
    with pytest.raises(old.NewruleSubmissionError,match="endpoint"):
        c.dispatch(operation,setup.plan,**bindings(setup))
    assert setup.admissions==[] and setup.api.calls==[]


@pytest.mark.parametrize("operation,changes",[
    ("capacity",{"candidate_id":"R298"}), ("summarize",{"attempt":1}),
    ("compile",{"candidate_id":"R247","attempt":1}), ("begin",{"candidate_id":"R281","attempt":1}),
    ("begin",{"candidate_id":"R298","attempt":True}), ("begin",{"candidate_id":"R298","attempt":4}),
    ("launch",{"candidate_id":"R298","attempt":0}),
    ("status",{"candidate_id":"R298","attempt":1,"prior_failure_sha256":RECEIPT}),
    ("read",{"candidate_id":"R298","attempt":1,"retry_justification_sha256":RECEIPT}),
    ("capacity",{"expected_receipt_sha256":None}), ("capacity",{"expected_receipt_sha256":"bad"})])
def test_dispatch_geometry_and_receipt_shape_cannot_smuggle_actions(setup,operation,changes):
    args=bindings(setup)
    args.update(changes)
    with pytest.raises(old.NewruleSubmissionError):
        c.dispatch(operation,setup.plan,**args)
    assert setup.admissions==[] and setup.api.calls==[]


def test_busy_begin_waits_without_attempt_claim_or_mutation(setup):
    setup.api.busy=True
    with pytest.raises(old.NewruleSubmissionError,match="capacity_wait"):
        c.begin_attempt(setup.plan,"R298",1,**bindings(setup))
    assert not (old.CONTROL/"R298-A1-claim.json").exists()
    assert [endpoint for endpoint,_ in setup.api.calls]==["projects/read","projects/nodes/read"]


@pytest.mark.parametrize("failure",["projects/create","files/update","compile/create"])
def test_ambiguous_failure_spends_original_named_claim_and_cannot_retry(setup,failure):
    value=setup
    value.api.failure=failure
    with pytest.raises(old.NewruleSubmissionError,match="request_ambiguous"):
        c.begin_attempt(value.plan,"R298",1,**bindings(value))
    assert (old.CONTROL/"R298-A1-claim.json").is_file()
    before=copy.deepcopy(value.api.calls)
    with pytest.raises(old.NewruleSubmissionError,match="another_attempt_active_or_ambiguous|attempt_spent"):
        c.begin_attempt(value.plan,"R298",1,**bindings(value))
    assert value.api.calls==before
    assert not (old.CONTROL/"upload-valid.json").exists()


def test_three_failed_compile_attempts_keep_bound_prior_and_never_reset(setup):
    value=setup
    extra={}
    for attempt in (1,2,3):
        c.dispatch("begin",value.plan,"R298",attempt,**bindings(value),**extra)
        value.api.state="BuildError"
        c.dispatch("compile",value.plan,"R298",attempt,**bindings(value))
        with old._Directory() as directory:
            prior=directory.read(f"R298-A{attempt}-terminal.json")
        extra=dict(prior_failure_sha256=old._sha(old._canonical(prior)),retry_justification_sha256="c"*64)
    with pytest.raises(old.NewruleSubmissionError,match="candidate_attempt"):
        c.dispatch("begin",value.plan,"R298",4,**bindings(value),**extra)
    assert len([row for row in value.api.calls if row[0]=="projects/create"])==1
    assert len([row for row in value.api.calls if row[0]=="compile/create"])==3
    assert not (old.CONTROL/"upload-valid.json").exists()


def test_real_legacy_delegates_compile_launch_status_and_no_completed_bypass(setup):
    value=setup
    c.dispatch("begin",value.plan,"R298",1,**bindings(value))
    c.dispatch("compile",value.plan,"R298",1,**bindings(value))
    c.dispatch("launch",value.plan,"R298",1,**bindings(value))
    result=c.dispatch("status",value.plan,"R298",1,**bindings(value))
    assert result["status"]=="InProgress"
    calls=copy.deepcopy(value.api.calls)
    with pytest.raises(FileNotFoundError):
        c.dispatch("read",value.plan,"R298",1,**bindings(value))
    assert value.api.calls==calls
    result=c.dispatch("summarize",value.plan,**bindings(value))
    assert not result["family_complete"] and not result["family_comparable"]
    assert value.admissions==[RECEIPT]*6


def normalized(function, *, successor):
    tree=ast.parse(inspect.getsource(function))
    node=tree.body[0]
    if isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant):
        node.body.pop(0)
    if successor:
        index=next(i for i,arg in enumerate(node.args.kwonlyargs) if arg.arg=="expected_receipt_sha256")
        node.args.kwonlyargs.pop(index)
        node.args.kw_defaults.pop(index)
        class Normalize(ast.NodeTransformer):
            def visit_Call(self,call):
                if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=="recovery":
                    assert call.func.attr=="require_admission" and len(call.args)==4 and not call.keywords
                    return ast.Call(func=ast.Name(id="_uploaded",ctx=ast.Load()),args=call.args[:3],keywords=[])
                return self.generic_visit(call)
            def visit_Attribute(self,attr):
                if isinstance(attr.value,ast.Name) and attr.value.id=="old":
                    return ast.Name(id=attr.attr,ctx=attr.ctx)
                return self.generic_visit(attr)
        tree=Normalize().visit(tree)
    return ast.dump(tree,include_attributes=False)


@pytest.mark.parametrize("name",["capacity_once","begin_attempt"])
def test_exact_frozen_function_body_parity_except_admission_and_namespace(name):
    assert normalized(getattr(c,name),successor=True)==normalized(getattr(old,name),successor=False)


def test_module_has_no_global_patch_legacy_receipt_write_or_dynamic_code():
    source=inspect.getsource(c)
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            assert node.func.id not in {"setattr","exec","eval","compile","globals"}
        if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            assert not any(isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name)
                           and t.value.id in {"old","recovery"} for t in targets)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in {"_uploaded","upload_inputs","prepare_family","discover_organization"}
            if node.func.attr=="write" and node.args and isinstance(node.args[0],ast.Constant):
                assert node.args[0].value!="upload-valid.json"
    assert "assistant.dispatch_fence" not in sys.modules


@pytest.mark.parametrize("boundary", ["directory_alias", "client_alias", "opener", "socket", "input_loader"])
def test_independent_guards_block_production_stale_aliases(operational_guards, boundary):
    calls = {
        "directory_alias": lambda: REAL_DIRECTORY(),
        "client_alias": lambda: REAL_CLIENT(),
        "opener": lambda: urllib.request.OpenerDirector().open("https://unused.invalid"),
        "socket": lambda: socket.create_connection(("unused.invalid", 443)),
        "input_loader": lambda: old.october.load_october_order_input_package("unused"),
    }
    with pytest.raises(pytest.fail.Exception, match="operational access forbidden"):
        calls[boundary]()
    assert operational_guards == ["operational_boundary"]
    operational_guards.clear()
