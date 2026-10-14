"""Temporary invented intake/front checks; no actual artifact or account I/O."""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

DIR = Path(__file__).parent


def _load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    value = importlib.util.module_from_spec(spec);sys.modules[name] = value
    spec.loader.exec_module(value);return value


fixtures = _load("selector_front_pure_fixtures",DIR/"test_insider_buying_affected_quarter_selector_v1.py")
from research import insider_buying_affected_quarter_selector_runner as module


@pytest.fixture
def supplied(tmp_path):
    root = (tmp_path/"invented-intake").resolve();root.mkdir(mode=0o700)
    args,images = fixtures.fixture(root)
    auxiliary = b"INVENTED OPAQUE AUXILIARY CONTROL\n"
    (root/module._AUX_NAME).write_bytes(auxiliary)
    for path in root.iterdir():path.chmod(0o600)
    options = {"fixture_only":True,"root":root,"manifest_pin":(args["expected_manifest_sha256"],len(args["intake_manifest_raw"])),
        "census_pin":args["expected_census_sha256"],"header_pin":args["expected_header_preflight_sha256"],
        "auxiliary_pin":(module._sha(auxiliary),len(auxiliary))}
    return args,images,options


def _result(supplied,monkeypatch):
    args,images,options = supplied
    held = module._HeldIntake(**options)
    try:
        first = module.pure.select_affected_quarters(**held.source_arguments())
        repeated = module.pure.select_affected_quarters(**held.source_arguments())
        assert first.canonical_bytes() == repeated.canonical_bytes()
        selected = first.to_payload();selected["fixture_only"] = False
        encoded = module._raw(selected)
        intake = copy.deepcopy(held.context);intake["fixture_only"] = False
        context = {"identity":{"head":"a"*40,"source_sha256":{}},"frozen_sources":{},"intake_context":intake}
        execution = {"source_only_lane_imports":True,"executed_sources":[],"executed_source_inventory_sha256":"b"*64,
            "executed_source_count":0,"full_historical_environment_reconstructed":False}
        monkeypatch.setattr(module.pure,"EXPECTED_ACTUAL_COUNTS",selected["counts"])
        monkeypatch.setattr(module.pure,"EXPECTED_ACTUAL_FORM_COUNTS",copy.deepcopy(selected["source_form_counts"]))
        expected_execution = copy.deepcopy(execution)
        monkeypatch.setattr(module,"_source_context",lambda *_:copy.deepcopy(expected_execution))
        body = {"schema":module.SCHEMA+"/worker-result","audit_id":"ib-affected-quarter-selector-invented",
            "fixture_only":False,"selection_b64":base64.b64encode(encoded).decode(),"selection_sha256":module._sha(encoded),
            "selection_bytes":len(encoded),"counts":selected["counts"],"intake_context":intake,"source_execution":execution,
            "authority":module._authority(),"effective_process_tree_network_denial":True,"effective_process_fork_denial":True,
            "effective_all_write_denial":True,"full_input_rederivations":2}
        return context,body,encoded
    finally:held.close()


def test_full_84_leaf_custody_and_two_genuine_metadata_rederivations(supplied):
    args,images,options = supplied
    held = module._HeldIntake(**options)
    try:
        assert len(held.tree.handles) == held.context["leaf_count"] == 84
        first = module.pure.select_affected_quarters(**held.source_arguments())
        second = module.pure.select_affected_quarters(**held.source_arguments())
        assert first.canonical_bytes() == second.canonical_bytes()
        assert first.to_payload()["affected_periods"] == ["2006Q1","2020Q4"]
        held.recheck()
        assert b"INVENTED PRIVATE ISSUER" not in first.canonical_bytes()
    finally:held.close()


@pytest.mark.parametrize("kind",["extra","changed_zip","changed_auxiliary","renamed_root","permissive_leaf","hardlink"])
def test_named_namespace_leaf_versions_and_auxiliary_are_held(supplied,kind):
    _,_,options = supplied;root = options["root"]
    held = module._HeldIntake(**options)
    try:
        leaf = root/"2006q1_form345.zip"
        if kind == "extra":(root/"unbound.json").write_bytes(b"{}")
        elif kind == "changed_zip":leaf.write_bytes(leaf.read_bytes()+b"changed")
        elif kind == "changed_auxiliary":(root/module._AUX_NAME).write_bytes(b"changed")
        elif kind == "renamed_root":root.rename(root.with_name("renamed-original"));root.mkdir(mode=0o700)
        elif kind == "permissive_leaf":leaf.chmod(0o666)
        else:os.link(leaf,root/"hardlink.zip")
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()


@pytest.mark.parametrize("root",[module.original.capture.bootstrap.custody.LANE_ROOT,
    module.original.capture.bootstrap.custody.LANE_ROOT.parent,Path("/")])
def test_fixture_fence_precedes_every_real_reader(root,monkeypatch):
    monkeypatch.setattr(module.held_io,"_HeldCapture",lambda *_args,**_kwargs:pytest.fail("reader reached"))
    with pytest.raises(ValueError):module._HeldIntake(fixture_only=True,root=root)
    with pytest.raises(ValueError):module._HeldPublication(root,{name:"a"*64 for name in module._FILES},fixture_only=True)


def test_resolved_fixture_alias_cannot_touch_actual_root(tmp_path,monkeypatch):
    alias = tmp_path/"redirect";alias.symlink_to(module.original.capture.bootstrap.custody.LANE_ROOT,target_is_directory=True)
    monkeypatch.setattr(module.held_io,"_HeldCapture",lambda *_args,**_kwargs:pytest.fail("reader reached"))
    with pytest.raises(ValueError):module._HeldIntake(fixture_only=True,root=alias)


def test_private_actual_cli_refuses_before_git_intake_or_output(monkeypatch,capsys,tmp_path):
    monkeypatch.setattr(module,"__file__",str(tmp_path/"explicitly-inactive-selector-front.py"))
    for target,name in ((module.original,"_fixed_source_identity"),(module,"_HeldIntake"),(module,"_output_directory")):
        monkeypatch.setattr(target,name,lambda *_args,**_kwargs:pytest.fail("actual callback reached"))
    assert module.main(["--audit-id","ib-affected-quarter-selector-invented","--expected-head","a"*40]) == 2
    body = json.loads(capsys.readouterr().out)
    assert body == {"disposition":module._DISPOSITION,"failure_phase":"parent_preflight",
        "failure_class":"AffectedQuarterSelectorRunnerError","os_errno":None}


def test_control_validator_accepts_only_known_metadata(supplied,monkeypatch):
    context,body,encoded = _result(supplied,monkeypatch)
    assert module._validate_worker_result(body,audit_id=body["audit_id"],context=context) == encoded
    child = SimpleNamespace(returncode=0,stderr=b"",stdout=module._raw(body)+b"\n")
    assert module._child_result(child,context=context) == body


@pytest.mark.parametrize("kind",["extra","deny_false","replays_one","replays_bool","wrong_manifest","wrong_source_context",
    "bad_base64","wrong_bytes","bool_bytes","extra_selection","extra_quarter","changed_quarter_order",
    "coherent_population","positive_authority","wrong_pin"])
def test_coherent_metadata_result_cannot_escape_scope(supplied,monkeypatch,kind):
    context,body,encoded = _result(supplied,monkeypatch)
    if kind == "extra":body["financial_unknown"] = {"count":42}
    elif kind == "deny_false":body["effective_all_write_denial"] = False
    elif kind == "replays_one":body["full_input_rederivations"] = 1
    elif kind == "replays_bool":body["full_input_rederivations"] = True
    elif kind == "wrong_manifest":body["intake_context"]["manifest_sha256"] = "f"*64
    elif kind == "wrong_source_context":body["source_execution"]["executed_source_count"] = 1
    elif kind == "bad_base64":body["selection_b64"] += "\n"
    elif kind == "wrong_bytes":body["selection_bytes"] += 1
    elif kind == "bool_bytes":body["selection_bytes"] = True
    else:
        selected = json.loads(encoded)
        if kind == "extra_selection":selected["financial_unknown"] = {"count":42}
        elif kind == "extra_quarter":selected["quarters"][0]["financial_unknown"] = {"count":42}
        elif kind == "changed_quarter_order":selected["quarters"][0],selected["quarters"][1] = selected["quarters"][1],selected["quarters"][0]
        elif kind == "coherent_population":selected["counts"]["submission_rows"] += 1;body["counts"] = selected["counts"]
        elif kind == "positive_authority":selected["authority"]["backtesting_ready"] = True
        else:selected["quarters"][0]["zip_sha256"] = "f"*64
        selected["quarters_sha256"] = module._sha(module._raw(selected["quarters"]))
        changed = module._raw(selected);body.update(selection_b64=base64.b64encode(changed).decode(),
            selection_sha256=module._sha(changed),selection_bytes=len(changed))
    with pytest.raises(ValueError):module._validate_worker_result(body,audit_id=body["audit_id"],context=context)


def test_unknown_financial_nested_count_is_never_numerically_interpreted(supplied,monkeypatch):
    context,body,_ = _result(supplied,monkeypatch)
    body["financial_unknown"] = {"count":42.123}
    lexical = module._opaque_json(module._raw(body))
    assert type(lexical["financial_unknown"]["count"]) is module._Number
    monkeypatch.setattr(module,"_interpret_metadata_int",lambda *_:pytest.fail("unknown financial token converted"))
    with pytest.raises(ValueError):module._validate_worker_result(lexical,audit_id=body["audit_id"],context=context)


@pytest.mark.parametrize("suffix",[b"",b"\n\n",b" \n",b"\r\n"])
def test_exact_single_lf_not_arbitrary_whitespace(supplied,monkeypatch,suffix):
    context,body,_ = _result(supplied,monkeypatch)
    child = SimpleNamespace(returncode=0,stderr=b"",stdout=module._raw(body)+suffix)
    with pytest.raises(ValueError):module._child_result(child,context=context)


def test_stored_failure_fields_are_revalidated_without_secret_text():
    body = {"disposition":module._DISPOSITION,"failure_phase":"worker_selection","failure_class":"ValueError","os_errno":None}
    error = module.ReportedSelectorWorkerError(body)
    assert module._failure_diagnostic(error) == body
    error.diagnostic["private_text"] = "PRIVATE SENTINEL"
    assert "PRIVATE" not in module._raw(module._failure_diagnostic(error)).decode()
    assert module._failure_diagnostic(error)["failure_phase"] == "parent_worker_result"


def test_cleanup_attempts_all_and_never_changes_aliased_primary_phase():
    events = [];primary = ValueError("PRIVATE SENTINEL");primary._selector_failure_phase = "parent_final_inputs"
    def failed():events.append("first");raise primary
    try:
        raise primary
    except ValueError:
        module._close_all((SimpleNamespace(close=failed),SimpleNamespace(close=lambda:events.append("second"))),phase="parent_cleanup")
    assert events == ["first","second"] and primary._selector_failure_phase == "parent_final_inputs"


def test_cleanup_alone_has_its_precise_phase():
    def failed():raise ValueError("PRIVATE SENTINEL")
    with pytest.raises(ValueError) as caught:module._close_all((SimpleNamespace(close=failed),),phase="worker_cleanup")
    assert module._failure_diagnostic(caught.value)["failure_phase"] == "worker_cleanup"


@pytest.mark.parametrize("kind",["intake","publication"])
def test_constructor_cleanup_cannot_replace_the_actual_primary_refusal(tmp_path,monkeypatch,kind):
    primary = ValueError("PRIVATE PRIMARY TEXT");secondary = PermissionError("PRIVATE CLEANUP TEXT")
    def refuse_open(*_):raise primary
    def refuse_close():raise secondary
    fake = SimpleNamespace(names=module._FILES,open=refuse_open,close=refuse_close,
        handles=[("leaf",SimpleNamespace(close=refuse_close),(),1)],chain=SimpleNamespace(fds=[]))
    monkeypatch.setattr(module.held_io,"_HeldCapture",lambda *_args,**_kwargs:fake)
    root = tmp_path.resolve()
    with pytest.raises(ValueError) as caught:
        if kind == "intake":module._HeldIntake(fixture_only=True,root=root,manifest_pin=("a"*64,3),
            census_pin="b"*64,header_pin="c"*64,auxiliary_pin=("d"*64,3))
        else:module._HeldPublication(root,dict.fromkeys(module._FILES,"a"*64),fixture_only=True)
    assert caught.value is primary


def test_nested_cleanup_attempts_all_stream_and_directory_handles(tmp_path,monkeypatch):
    events = [];stream_failure = ValueError("PRIVATE STREAM TEXT")
    def first():events.append("first");raise stream_failure
    def second():events.append("second")
    def close_fd(fd):
        events.append(fd)
        if fd == 732:raise OSError("PRIVATE DIRECTORY TEXT")
    monkeypatch.setattr(module.os,"close",close_fd)
    chain = SimpleNamespace(fds=[731,732],close=lambda:events.append("chain"))
    tree = SimpleNamespace(handles=[("second",SimpleNamespace(close=second),(),1),
        ("first",SimpleNamespace(close=first),(),1)],chain=chain)
    tree.close = lambda:module.held_io._HeldCapture.close(tree)
    held = object.__new__(module._HeldIntake);held.tree = tree
    with pytest.raises(ValueError) as caught:held.close()
    assert caught.value is stream_failure
    assert events == ["first","second",732,731]
    assert tree.handles == [] and chain.fds == []


def test_native_denial_precedes_any_input_and_python_hook(monkeypatch):
    monkeypatch.setattr(module,"__file__",str(module.original.capture.bootstrap.custody.LANE_ROOT/module.SELF_PATH))
    events = []
    def deny(_):events.append("native");raise ValueError("invented missing OS denial")
    monkeypatch.setattr(module,"_prove_allwrite_denial",deny)
    monkeypatch.setattr(module,"_HeldIntake",lambda:pytest.fail("actual input reader reached"))
    monkeypatch.setattr(module.sys,"addaudithook",lambda *_:pytest.fail("Python hook installed before native proof"))
    with pytest.raises(ValueError) as caught:module._worker("ib-affected-quarter-selector-invented",expected_head="a"*40,
        context={},executed_sources=[],bootstrap_source={})
    assert events == ["native"] and module._failure_diagnostic(caught.value)["failure_phase"] == "worker_native_denial"


@pytest.mark.parametrize("fault,expected",[(None,None),("hold","parent_final_output_hold"),
    ("inputs","parent_final_inputs"),("source","parent_final_sources"),("output","parent_final_output_check")])
def test_real_temporary_parent_publication_flow_and_precise_late_refusals(tmp_path,supplied,monkeypatch,fault,expected):
    # Only the native transport and source/input identities are invented.
    # Directory publication and all final output holds are real temporary I/O.
    context,body,encoded = _result(supplied,monkeypatch)
    _,_,options = supplied
    held = module._HeldIntake(**options);held.context = context["intake_context"]
    calls = {"identity":0,"inputs":0};original_recheck = held.recheck
    def recheck():
        calls["inputs"] += 1
        if fault == "inputs" and calls["inputs"] == 3:raise ValueError("PRIVATE INPUT TEXT")
        original_recheck()
    held.recheck = recheck
    root = (tmp_path/"invented-parent").resolve();root.mkdir(mode=0o700)
    audit = body["audit_id"];head = "a"*40
    output_path = root.joinpath(*module.OUTPUT_PARTS,audit);output_path.mkdir(parents=True,mode=0o700)
    monkeypatch.setattr(module.original.capture.bootstrap.custody,"LANE_ROOT",root)
    def identity(_):
        calls["identity"] += 1
        if fault == "source" and calls["identity"] == 4:return {"changed":True},{}
        return context["identity"],context["frozen_sources"]
    monkeypatch.setattr(module,"_fixed_source_identity",identity)
    monkeypatch.setattr(module,"_HeldIntake",lambda:held)
    monkeypatch.setattr(module,"_output_directory",lambda _:module.original.capture.custody._Directory(output_path))
    actual_publication = module._HeldPublication
    def publication(*args,**kwargs):
        if fault == "hold":raise ValueError("PRIVATE HOLD TEXT")
        value = actual_publication(*args,**kwargs)
        if fault == "output":
            def refused():raise ValueError("PRIVATE OUTPUT TEXT")
            value.recheck = refused
        return value
    monkeypatch.setattr(module,"_HeldPublication",publication)
    def launch(command,**kwargs):
        policy = command[command.index("-p")+1]
        assert "(deny file-write*)" in policy and "(allow file-write*" not in policy
        assert "(deny network*)" in policy and "(deny process-fork)" in policy
        assert set(json.loads(kwargs["input"])) == {"sources","context","audit_id","expected_head"}
        return SimpleNamespace(returncode=0,stderr=b"",stdout=module._raw(body)+b"\n")
    monkeypatch.setattr(module.subprocess,"run",launch)
    if fault is None:
        result = module.run_observed_selection(audit,expected_head=head)
        assert result["selection_sha256"] == module._sha(encoded)
        assert calls == {"identity":4,"inputs":3}
    else:
        with pytest.raises(ValueError) as caught:module.run_observed_selection(audit,expected_head=head)
        diagnostic = module._failure_diagnostic(caught.value)
        assert diagnostic["failure_phase"] == expected
        assert "PRIVATE" not in module._raw(diagnostic).decode()
    assert set(os.listdir(output_path)) == module._FILES
    assert (output_path/"selection.json").read_bytes() == encoded


def test_known_raw_source_clock_is_bound_not_a_self_reported_date(supplied,monkeypatch):
    context,body,encoded = _result(supplied,monkeypatch)
    selected = json.loads(encoded)
    selected["quarters"][0]["local_filesystem_observation_unverified"] = "2026-10-14T01:00:00.0000000Z"
    selected["quarters_sha256"] = module._sha(module._raw(selected["quarters"]))
    changed = module._raw(selected)
    body.update(selection_b64=base64.b64encode(changed).decode(),selection_sha256=module._sha(changed),selection_bytes=len(changed))
    with pytest.raises(ValueError):module._validate_worker_result(body,audit_id=body["audit_id"],context=context)


def test_coherent_form3_to_form5_reassignment_cannot_replace_known_full_form_totals(supplied,monkeypatch):
    context,body,encoded = _result(supplied,monkeypatch)
    selected = json.loads(encoded)
    original_counts = copy.deepcopy(selected["counts"])
    original_pins = copy.deepcopy(context["intake_context"])
    quarter = next(row for row in selected["quarters"] if row["period"] == "2006Q2")
    assert quarter["source_form_counts"]["3"] > 0
    quarter["source_form_counts"]["3"] -= 1
    quarter["source_form_counts"]["5"] += 1
    selected["source_form_counts"]["3"] -= 1
    selected["source_form_counts"]["5"] += 1
    selected["quarters_sha256"] = module._sha(module._raw(selected["quarters"]))
    changed = module._raw(selected)
    body.update(selection_b64=base64.b64encode(changed).decode(),selection_sha256=module._sha(changed),selection_bytes=len(changed))
    assert selected["counts"] == body["counts"] == original_counts
    assert context["intake_context"] == original_pins
    assert selected["source_form_counts"] != module.pure.EXPECTED_ACTUAL_FORM_COUNTS
    with pytest.raises(ValueError):module._validate_worker_result(body,audit_id=body["audit_id"],context=context)


def test_second_genuine_rederivation_cannot_be_replaced_by_an_equal_count_claim(supplied,monkeypatch):
    _,_,options = supplied;held = module._HeldIntake(**options)
    factory = module.pure.select_affected_quarters;calls = []
    def changed(**kwargs):
        calls.append(1)
        first = factory(**kwargs)
        return first if len(calls) == 1 else SimpleNamespace(canonical_bytes=lambda:b"coherent but different metadata")
    monkeypatch.setattr(module.pure,"select_affected_quarters",changed)
    try:
        with pytest.raises(ValueError):module._derive_twice(held)
        assert len(calls) == 2
    finally:held.close()


def test_extra_intake_leaf_is_refused_before_factory_or_output(supplied):
    _,_,options = supplied
    (options["root"]/"unexpected.control").write_bytes(b"PRIVATE SENTINEL")
    with pytest.raises(ValueError):module._HeldIntake(**options)


def test_output_caps_and_envelope_refuse_without_a_truncated_publication(supplied,monkeypatch):
    context,body,_ = _result(supplied,monkeypatch)
    monkeypatch.setattr(module,"MAX_SELECTION_BYTES",1)
    with pytest.raises(ValueError):module._validate_worker_result(body,audit_id=body["audit_id"],context=context)
    monkeypatch.setattr(module,"MAX_CONTEXT_BYTES",1)
    with pytest.raises(ValueError) as caught:module._at_phase("parent_source_capture",module._captured_envelope,[],context,body["audit_id"],"a"*40)
    assert module._failure_diagnostic(caught.value)["failure_phase"] == "parent_source_capture"


def test_captured_bootstrap_runs_with_inherited_os_network_denial_without_any_input(tmp_path):
    root = tmp_path.resolve()
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    helper = module.original.isolation._read_source(helper_path)
    consumer = ("import os,socket,errno\n"
        "def _raw(body):\n import json\n return json.dumps(body,sort_keys=True,separators=(',',':')).encode()\n"
        "def _worker(*args,**kwargs):\n"
        " h=socket.socket()\n"
        " try:h.connect(('127.0.0.1',9))\n"
        " except OSError as e:assert e.errno in {errno.EPERM,errno.EACCES}\n"
        " else:raise AssertionError('native network denial absent')\n"
        " finally:h.close()\n"
        " return {'fixture_only':True,'synthetic_captured_bootstrap_only':True,'native_network_denials':1}\n").encode()
    sources = sorted([(helper_path,helper),(module.SELF_PATH,consumer)])
    identity = {name:module._sha(raw) for name,raw in sources}
    envelope = {"sources":[{"path":name,"sha256":identity[name],"source_b64":base64.b64encode(raw).decode()} for name,raw in sources],
        "context":{"identity":{"source_sha256":identity}},"audit_id":"ib-affected-quarter-selector-invented","expected_head":"a"*40}
    child = subprocess.run([sys.executable,"-I","-S","-B","-c",module.SOURCE_ONLY_BOOTSTRAP],
        input=module._raw(envelope),capture_output=True,check=False,timeout=60,cwd=Path.cwd())
    assert child.returncode == 0 and child.stderr == b"",child.stdout
    assert json.loads(child.stdout) == {"fixture_only":True,"synthetic_captured_bootstrap_only":True,"native_network_denials":1}
    assert list(root.iterdir()) == []
