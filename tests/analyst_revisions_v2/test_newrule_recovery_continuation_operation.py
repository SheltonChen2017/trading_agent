"""Synthetic recovery-wrapper checks; no private artifacts or remote calls."""
import builtins
import copy
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

import scripts as scripts_package
import research.analyst_revisions_v2_qc as qc_package
from scripts import run_arv2_newrule_recovery_continuation as d
from scripts import arv2_newrule_recovery_continuation as continuation
from scripts import arv2_newrule_storage_recovery as spent_recovery
from scripts import arv2_newrule_storage_recovery_v2 as recovery
from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission

HEAD, SHA, RECEIPT = "a"*40, "b"*64, "c"*64
REAL_OPERATION = d._operation
REAL_DISPATCH = continuation.dispatch
REAL_CAPACITY = continuation.capacity_once
REAL_BEGIN = continuation.begin_attempt
REAL_DIRECTORY = submission._Directory
NEW_NAMES = {
    "scripts/arv2_newrule_storage_recovery.py",
    "scripts/run_arv2_newrule_storage_recovery.py",
    "scripts/arv2_newrule_storage_recovery_v2.py",
    "scripts/arv2_newrule_recovery_continuation.py",
    "scripts/diagnose_arv2_newrule_upload.py",
    "scripts/diagnose_arv2_newrule_object_metadata.py",
}


def args(operation="capacity", **changes):
    values = dict(operation=operation, expected_head=HEAD, caller_sha256=SHA,
        receipt_sha256=RECEIPT, candidate=None, attempt=None,
        prior_failure_sha256=None, justification_sha256=None)
    if operation in {"begin","compile","launch","status","read"}:
        values.update(candidate="R298",attempt=1)
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    violations=[]
    def forbidden(label):
        def guard(*_a,**_k):
            violations.append(label)
            pytest.fail("operational access forbidden: "+label)
        return guard
    # Python's `from package import name` can resolve the package attribute
    # instead of sys.modules. Bind BOTH to the same guarded captured module.
    # All patches are fixture-scoped and restored by monkeypatch teardown.
    for package,name,module in (
        (scripts_package,"arv2_newrule_recovery_continuation",continuation),
        (scripts_package,"arv2_newrule_storage_recovery",spent_recovery),
        (scripts_package,"arv2_newrule_storage_recovery_v2",recovery),
        (qc_package,"newrule_comparison_submission",submission)):
        monkeypatch.setattr(package,name,module)
        monkeypatch.setitem(sys.modules,package.__name__+"."+name,module)
    monkeypatch.setattr(d,"_operation",forbidden("wrapper_operation"))
    monkeypatch.setattr(d.frozen.subprocess,"run",forbidden("subprocess"))
    monkeypatch.setattr(d.frozen,"run",forbidden("frozen_run"))
    monkeypatch.setattr(d.frozen,"_operation",forbidden("frozen_operation"))
    monkeypatch.setattr(d.frozen.prepared_input.october,"load_october_order_input_package",
        forbidden("private_input_loader"))
    # Guard the real class itself as well as the module lookup. Even a stale
    # import alias must refuse before opening the production control tree.
    for name in ("__init__","verify","names","read","write"):
        monkeypatch.setattr(REAL_DIRECTORY,name,forbidden("directory_"+name))
    monkeypatch.setattr(submission,"_Directory",forbidden("directory_constructor"))
    for name in ("load_family","_session","_client","_rpc","_object","_organization",
        "prepare_family","discover_organization","upload_inputs","capacity_once","begin_attempt",
        "poll_compile_once","launch_compiled","poll_status_once","read_result_once","summarize_family"):
        monkeypatch.setattr(submission,name,forbidden("submission_"+name))
    for module,label in ((spent_recovery,"spent_recovery_"),(recovery,"recovery_v2_")):
        for name in ("claim","recover","require_admission","_retained","_payloads","_request"):
            monkeypatch.setattr(module,name,forbidden(label+name))
    for name in ("dispatch","capacity_once","begin_attempt"):
        monkeypatch.setattr(continuation,name,forbidden("continuation_"+name))
    yield
    # Product entry points catch BaseException. A swallowed pytest.fail must
    # still fail the test, rather than masquerading as the expected exit 2.
    assert violations==[], "forbidden operation attempted: "+", ".join(violations)


def preflight_fixtures(monkeypatch, *, bad_source=None, git_failure=None):
    monkeypatch.setattr(d,"NEW_PINS",{name:"d"*64 for name in NEW_NAMES})
    observations = [str(d.ROOT),d.frozen.BRANCH,HEAD,""]
    if git_failure in ("root","branch","head","dirty"):
        observations[("root","branch","head","dirty").index(git_failure)]="mismatch"
    git_calls,source_reads=[],[]
    def git(command,**kwargs):
        git_calls.append(command)
        assert kwargs["cwd"]==d.ROOT and kwargs["timeout"]<=3
        return SimpleNamespace(stdout=(observations.pop(0)+"\n").encode("ascii"),
            stderr=b"PRIVATE-COMMAND-TEXT" if git_failure=="stderr" else b"",
            returncode=1 if git_failure=="exit" else 0)
    monkeypatch.setattr(d.frozen.subprocess,"run",git)
    def source(path):
        relative=str(path.relative_to(d.ROOT))
        source_reads.append(relative)
        if relative==bad_source:
            return "e"*64
        if path==d.SOURCE:
            return SHA
        if path==d.frozen.SOURCE:
            return d.FROZEN_CALLER_SHA256
        if relative in d.NEW_PINS:
            return d.NEW_PINS[relative]
        assert relative in d.frozen.SOURCE_PINS
        return d.frozen.SOURCE_PINS[relative]
    monkeypatch.setattr(d.helpers,"_source_digest",source)
    return source_reads,git_calls


def test_import_and_package_attribute_seams_share_guarded_real_modules():
    from scripts import arv2_newrule_storage_recovery as imported_spent_recovery
    from scripts import arv2_newrule_storage_recovery_v2 as imported_recovery
    from scripts import arv2_newrule_recovery_continuation as imported_continuation
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as imported_submission
    assert imported_spent_recovery is spent_recovery is scripts_package.arv2_newrule_storage_recovery
    assert imported_recovery is recovery is scripts_package.arv2_newrule_storage_recovery_v2
    assert imported_continuation is continuation is scripts_package.arv2_newrule_recovery_continuation
    assert imported_submission is submission is qc_package.newrule_comparison_submission
    assert sys.modules["scripts.arv2_newrule_storage_recovery"] is spent_recovery
    assert sys.modules["scripts.arv2_newrule_storage_recovery_v2"] is recovery
    assert sys.modules["scripts.arv2_newrule_recovery_continuation"] is continuation
    assert sys.modules["research.analyst_revisions_v2_qc.newrule_comparison_submission"] is submission


def test_real_alias_directory_and_all_operational_seams_are_guarded():
    assert submission._Directory.__name__ == "guard"
    for name in ("__init__","verify","names","read","write"):
        assert getattr(REAL_DIRECTORY,name).__name__ == "guard"
    for module,names in ((submission,("load_family","_session","_client","_rpc","_object",
        "prepare_family","discover_organization","upload_inputs","capacity_once","begin_attempt",
        "poll_compile_once","launch_compiled","poll_status_once","read_result_once","summarize_family")),
        (spent_recovery,("claim","recover","require_admission","_retained","_payloads","_request")),
        (recovery,("claim","recover","require_admission","_retained","_payloads","_request")),
        (continuation,("dispatch","capacity_once","begin_attempt"))):
        assert all(getattr(module,name).__name__ == "guard" for name in names)
    assert d.frozen.prepared_input.october.load_october_order_input_package.__name__ == "guard"


def test_profile_preserves_all_original_pins_plus_exact_six_additions():
    profile=d.profile_record()
    assert len(d.frozen.SOURCE_PINS)==51
    assert profile["source_pins"]==dict(d.frozen.SOURCE_PINS)
    assert set(profile["new_pins"])==NEW_NAMES
    assert not NEW_NAMES.intersection(d.frozen.SOURCE_PINS)
    assert profile["operations"]==list(d.OPERATIONS)
    assert profile["actual_recovery_exit_zero_required_externally"] is True
    assert all(profile[k] is False for k in ("original_upload_accepted","point_in_time_proven",
        "formal_forward_ready","paper_or_live_ready"))


@pytest.mark.parametrize("operation",d.OPERATIONS)
def test_exact_original_and_new_pins_checked_before_operation(monkeypatch,capsys,operation):
    reads,git=preflight_fixtures(monkeypatch)
    def operation_stub(value,deadline):
        assert value.operation==operation
        assert len(git)==4
        assert set(d.frozen.SOURCE_PINS)|NEW_NAMES|{
            str(d.SOURCE.relative_to(d.ROOT)),str(d.frozen.SOURCE.relative_to(d.ROOT))}==set(reads)
        return {"synthetic":True}
    monkeypatch.setattr(d,"_operation",operation_stub)
    assert d.run(args(operation))==0
    result=json.loads(capsys.readouterr().out)
    assert result["receipt_sha256"]==RECEIPT and result["operation_completed"] is True
    assert not result["original_upload_accepted"] and not result["formal_forward_ready"]


@pytest.mark.parametrize("failure",["root","branch","head","dirty","stderr","exit"])
def test_original_git_host_gate_remains_before_new_imports(monkeypatch,capsys,failure):
    reads,_=preflight_fixtures(monkeypatch,git_failure=failure)
    assert d.run(args())==2
    output=capsys.readouterr().out
    assert "PRIVATE" not in output and reads==[]
    report=json.loads(output)
    assert report["stage"]=="preflight" and report["operation_completed"] is False


@pytest.mark.parametrize("relative",[
    "scripts/diagnose_arv2_newrule_upload.py",
    "scripts/diagnose_arv2_newrule_object_metadata.py",
    "scripts/arv2_newrule_storage_recovery.py",
    "scripts/run_arv2_newrule_storage_recovery.py",
    "scripts/arv2_newrule_storage_recovery_v2.py",
    "scripts/arv2_newrule_recovery_continuation.py",
    "scripts/run_arv2_newrule_comparison.py",
    "scripts/run_arv2_newrule_recovery_continuation.py",
    "research/quantconnect.py"])
def test_bad_source_digest_prevents_helper_import_and_private_or_contact_calls(monkeypatch,capsys,relative):
    preflight_fixtures(monkeypatch,bad_source=relative)
    imports,operations=[],[]
    original=builtins.__import__
    def guard(name,globals=None,locals=None,fromlist=(),level=0):
        if (name=="scripts" and any(x.startswith("arv2_newrule") for x in fromlist)
                or name=="research.analyst_revisions_v2_qc" and "newrule_comparison_submission" in fromlist):
            imports.append((name,fromlist))
            pytest.fail("helper import after source refusal")
        return original(name,globals,locals,fromlist,level)
    monkeypatch.setattr(builtins,"__import__",guard)
    monkeypatch.setattr(d,"_operation",lambda *_: operations.append(True))
    assert d.run(args())==2
    assert imports==[] and operations==[]
    assert json.loads(capsys.readouterr().out)["stage"]=="preflight"


def test_unfrozen_placeholder_prevents_any_operation(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    d.NEW_PINS["scripts/arv2_newrule_storage_recovery_v2.py"]="0"*64
    operations=[]
    monkeypatch.setattr(d,"_operation",lambda *_:operations.append(True))
    assert d.run(args())==2 and operations==[]
    assert json.loads(capsys.readouterr().out)["operation_completed"] is False


@pytest.mark.parametrize("operation,changes",[
    ("upload",{}),("prepare",{}),("organization",{}),("unknown",{}),
    ("capacity",{"candidate":"R298"}),("summarize",{"attempt":1}),
    ("begin",{"candidate":"R247"}),("launch",{"candidate":"R281"}),
    ("begin",{"attempt":True}),("begin",{"attempt":0}),("read",{"attempt":4}),
    ("begin",{"attempt":2}),("begin",{"attempt":3}),
    ("begin",{"attempt":1,"prior_failure_sha256":RECEIPT,"justification_sha256":RECEIPT}),
    ("status",{"prior_failure_sha256":RECEIPT,"justification_sha256":RECEIPT}),
    ("begin",{"attempt":2,"prior_failure_sha256":RECEIPT}),
    ("begin",{"attempt":2,"justification_sha256":RECEIPT}),
    ("capacity",{"receipt_sha256":None}),("capacity",{"receipt_sha256":"x"}),
    ("capacity",{"caller_sha256":"x"}),("capacity",{"expected_head":"x"})])
def test_strict_geometry_and_receipt_refusal(monkeypatch,capsys,operation,changes):
    preflight_fixtures(monkeypatch)
    operations=[]
    monkeypatch.setattr(d,"_operation",lambda *_:operations.append(True))
    assert d.run(args(operation,**changes))==2 and operations==[]
    report=json.loads(capsys.readouterr().out)
    assert report["stage"]=="preflight" and report["operation_completed"] is False


@pytest.mark.parametrize("attempt",[2,3])
def test_bound_retry_arguments_preserve_original_rules(monkeypatch,attempt):
    preflight_fixtures(monkeypatch)
    d._preflight(args("begin",attempt=attempt,prior_failure_sha256="e"*64,
        justification_sha256="f"*64),time.monotonic()+10)


@pytest.mark.parametrize("operation",d.OPERATIONS)
def test_exact_input_family_then_receipt_bound_dispatch(monkeypatch,operation):
    observed=[]
    value,plan=object(),object()
    selected=args(operation)
    def load(path,**kwargs):
        assert path==d.frozen.PACKAGE
        assert kwargs==dict(expected_package_sha256=d.frozen.PACKAGE_SHA256,
            lineage_path=d.frozen.LINEAGE,expected_lineage_sha256=d.frozen.LINEAGE_SHA256)
        observed.append("input")
        return value
    def family(actual,**kwargs):
        assert actual is value and observed==["input"]
        assert kwargs==dict(expected_family_sha256=d.FAMILY_SHA256,
            expected_new_source_pins=dict(d.frozen.NEW_SOURCE_PINS),
            expected_host_source_pins={n:d.frozen.SOURCE_PINS[n] for n in submission.HOST_SOURCE_NAMES})
        observed.append("family")
        return plan
    returned={"safe_synthetic":True}
    if operation=="read":
        returned={key:"synthetic" for key in ("family_sha256","candidate_id","attempt_id",
            "project_id","backtest_id","status","cell_completed","family_comparable","result_cell")}
        returned["statistics"]={"meta":{"account_aggregates":{"terminal_nav":"1000000"},
            "common_source_path_sha256":RECEIPT,"decision_count":302,"evaluation_session_count":1451,
            "order_count":2,"fill_count":2,"coverage_fallback_counts":{}},
            "monthly":{"do_not_print":"PRIVATE-MONTHLY"},"extra":"PRIVATE-UNAPPROVED"}
        returned["raw_error"]="PRIVATE-ERROR"
    saved=copy.deepcopy(returned)
    def dispatch(which,actual,candidate,attempt,**kwargs):
        assert observed==["input","family"] and which==operation and actual is plan
        assert (candidate,attempt)==(selected.candidate,selected.attempt)
        assert kwargs==dict(expected_family_sha256=d.FAMILY_SHA256,expected_receipt_sha256=RECEIPT,
            prior_failure_sha256=None,retry_justification_sha256=None)
        observed.append("dispatch")
        return returned
    monkeypatch.setattr(d.frozen.prepared_input.october,"load_october_order_input_package",load)
    monkeypatch.setattr(submission,"load_family",family)
    monkeypatch.setattr(continuation,"dispatch",dispatch)
    result=REAL_OPERATION(selected,time.monotonic()+10)
    assert observed==["input","family","dispatch"] and returned==saved
    if operation=="read":
        assert "PRIVATE" not in json.dumps(result)
        assert result["statistics_sha256"]==hashlib.sha256(d.helpers.canonical_json_bytes(returned["statistics"])).hexdigest()
        assert result["account_aggregates"]==returned["statistics"]["meta"]["account_aggregates"]
        assert "statistics" not in result and "raw_error" not in result
    else:
        assert result==returned


@pytest.mark.parametrize("stage",["input","family","dispatch"])
def test_opaque_lifecycle_failure_never_exposes_message(monkeypatch,capsys,stage):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d,"_operation",REAL_OPERATION)
    observed=[]
    def selected(name):
        def call(*_a,**_k):
            observed.append(name)
            if name==stage: raise RuntimeError("PRIVATE-ERROR-TEXT")
            return object()
        return call
    monkeypatch.setattr(d.frozen.prepared_input.october,"load_october_order_input_package",selected("input"))
    monkeypatch.setattr(submission,"load_family",selected("family"))
    monkeypatch.setattr(continuation,"dispatch",selected("dispatch"))
    assert d.run(args())==2
    output=capsys.readouterr().out
    assert "PRIVATE" not in output
    report=json.loads(output)
    assert report["failure_code"]=="unknown_exception" and report["operation_completed"] is False
    assert observed==["input","family","dispatch"][:["input","family","dispatch"].index(stage)+1]


def test_finite_frozen_refusal_preserved(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    def refuse(*_): raise submission.NewruleSubmissionError("capacity_wait")
    monkeypatch.setattr(d,"_operation",refuse)
    assert d.run(args())==2
    assert json.loads(capsys.readouterr().out)["failure_code"]=="capacity_wait"


@pytest.mark.parametrize("operation",d.OPERATIONS)
@pytest.mark.parametrize("reason,expected",[
    ("admission_pin","admission_pin"),
    ("PRIVATE-UNAPPROVED-ADMISSION-DETAIL","unknown_exception"),
])
def test_v2_admission_refusal_is_finite_before_any_downstream_operation(
        monkeypatch,capsys,operation,reason,expected):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d,"_operation",REAL_OPERATION)
    monkeypatch.setattr(continuation,"dispatch",REAL_DISPATCH)
    monkeypatch.setattr(continuation,"capacity_once",REAL_CAPACITY)
    monkeypatch.setattr(continuation,"begin_attempt",REAL_BEGIN)
    value,plan,directory,record=object(),object(),object(),object()
    observed=[]
    def load(*_a,**_k):
        observed.append("input")
        return value
    def family(actual,**_k):
        assert actual is value
        observed.append("family")
        return plan
    @contextmanager
    def session(actual,pin):
        assert actual is plan and pin==d.FAMILY_SHA256
        observed.append("session")
        yield directory,record
    def refuse(actual_directory,actual_plan,actual_record,pin):
        assert (actual_directory,actual_plan,actual_record)==(directory,plan,record)
        assert pin==RECEIPT
        observed.append("admission")
        raise recovery.StorageRecoveryError(reason)
    monkeypatch.setattr(d.frozen.prepared_input.october,"load_october_order_input_package",load)
    monkeypatch.setattr(submission,"load_family",family)
    monkeypatch.setattr(submission,"_session",session)
    monkeypatch.setattr(recovery,"require_admission",refuse)
    # The autouse guards remain active on all clients, delegates, and real
    # directories: even a caught attempted operation fails fixture teardown.
    assert d.run(args(operation))==2
    output=capsys.readouterr().out
    assert "PRIVATE" not in output
    report=json.loads(output)
    assert report["failure_code"]==expected
    assert report["stage"]==operation and report["operation_completed"] is False
    assert "result" not in report
    assert observed==["input","family","session","admission"]


def test_deadline_after_dispatch_cannot_emit_success(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    clock=time.monotonic
    def late(*_):
        monkeypatch.setattr(time,"monotonic",lambda:clock()+10000)
        return {"accepted":True}
    monkeypatch.setattr(d,"_operation",late)
    assert d.run(args())==2
    report=json.loads(capsys.readouterr().out)
    assert report["failure_code"]=="deadline" and report["operation_completed"] is False
    assert "result" not in report


def test_late_exception_after_synthetic_persistence_still_nonzero(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    evidence=[]
    def late(*_):
        evidence.append({"retained_terminal":"synthetic-success-not-accepted"})
        raise OSError("PRIVATE-LATE-ERROR")
    monkeypatch.setattr(d,"_operation",late)
    assert d.run(args())==2 and len(evidence)==1
    output=capsys.readouterr().out
    assert "PRIVATE" not in output
    report=json.loads(output)
    assert report["operation_completed"] is False and "result" not in report


def test_maximum_output_refuses_before_console_publication(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d,"_operation",lambda *_:{"PRIVATE":"x"*d.MAX_OUTPUT_BYTES})
    assert d.run(args())==2
    assert "PRIVATE" not in capsys.readouterr().out


def test_malformed_read_result_does_not_emit_partial_success(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d,"_operation",REAL_OPERATION)
    monkeypatch.setattr(d.frozen.prepared_input.october,"load_october_order_input_package",lambda *_a,**_k:object())
    monkeypatch.setattr(submission,"load_family",lambda *_a,**_k:object())
    monkeypatch.setattr(continuation,"dispatch",lambda *_a,**_k:{"statistics":{"meta":{"private":"NO-PRINT"}}})
    assert d.run(args("read"))==2
    output=capsys.readouterr().out
    assert "NO-PRINT" not in output and "statistics" not in output
    assert json.loads(output)["operation_completed"] is False


def test_actual_wrapper_exit_zero_never_claims_original_or_formal_acceptance(monkeypatch,capsys):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d,"_operation",lambda *_:{"state":"wait"})
    assert d.run(args())==0
    value=json.loads(capsys.readouterr().out)
    assert value["operation_completed"] and value["result"]=={"state":"wait"}
    assert all(value[k] is False for k in ("original_upload_accepted","formal_forward_ready",
        "point_in_time_proven","paper_or_live_ready"))
    assert_lane_closure_excludes_dispatch_fence()
