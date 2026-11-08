"""Invented operational metadata only; no actual artifacts or provider I/O."""
from __future__ import annotations

from dataclasses import replace
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_coverage_audit as m


def _write(root,parts,name,value,*,raw=False):
    path = root.joinpath(*parts,name);path.parent.mkdir(parents=True,exist_ok=True)
    for directory in (path.parent,*path.parent.parents):
        if directory == root.parent:break
        directory.chmod(0o700)
    body = value if raw else m._raw(value)
    path.write_bytes(body);path.chmod(0o600)
    return m._sha(body)


def _read(root,parts,name):return json.loads(root.joinpath(*parts,name).read_bytes())


def _change(root,parts,name,change):
    value = _read(root,parts,name);change(value)
    return _write(root,parts,name,value)


def _selector_fixture(root):
    spec = importlib.util.spec_from_file_location("pilot_invented_selector_fixture",
        Path(__file__).with_name("test_insider_buying_affected_quarter_selector_v1.py"))
    fixture = importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    census = root/"invented-census-builder";census.mkdir(mode=0o700)
    arguments,_ = fixture.fixture(census)
    selected = m.selector.pure.select_affected_quarters(**arguments).to_payload();selected["fixture_only"] = False
    intake = {"manifest_sha256":selected["intake_manifest_sha256"],"manifest_bytes":selected["intake_manifest_bytes"],
        "census_sha256":selected["census_sha256"],"header_preflight_sha256":selected["header_preflight_sha256"],
        "leaf_pins":{x["period"].lower()+"_form345.zip":{"sha256":x["zip_sha256"],"bytes":x["zip_size_bytes"]} for x in selected["quarters"]},
        "quarter_observations":{x["period"]:x["local_filesystem_observation_unverified"] for x in selected["quarters"]}}
    shutil.rmtree(census)
    selected_hash = _write(root,m.SELECTOR_PARTS,"selection.json",selected)
    reservation_hash = _write(root,m.SELECTOR_PARTS,"reservation.json",{"invented":True})
    complete = dict.fromkeys(m._SELECTOR_COMPLETE_KEYS,None)
    complete.update(schema=m.selector.SCHEMA+"/complete",audit_id=m.selector.AUDIT_ID,fixture_only=False,
        current_execution_identity={"head":"a"*40},intake_context=intake,reservation_sha256=reservation_hash,
        selection_sha256=selected_hash,selection_bytes=len(m._raw(selected)),counts=selected["counts"],
        full_input_rederivations=2,effective_process_tree_network_denial=True,effective_process_fork_denial=True,
        effective_all_write_denial=True,authority=m.selector._authority())
    complete_hash = _write(root,m.SELECTOR_PARTS,"complete.json",complete)
    summary = {"audit_id":m.selector.AUDIT_ID,"authority":m.selector._authority(),"complete_sha256":complete_hash,
        "counts":selected["counts"],"fixture_only":False,"operation_registration_sha256":"b"*64,
        "predecessor_status":"FAILED_preserved_not_promoted","selection_sha256":selected_hash}
    terminal = {"schema":"insider-affected-quarter-selector-trusted-publisher-v3/semantic-terminal",
        "audit_id":m.OBSERVER_PARTS[-1],"elapsed_seconds":1.0,"exit_code":0,"stderr_bytes":0,"stderr_sha256":m._sha(b""),
        "stdout_bytes":10,"stdout_sha256":"c"*64,"success_summary":summary,"terminal_success_observed":True,"timed_out":False}
    journal = {"terminal.json":_write(root,m.OBSERVER_PARTS,"terminal.json",terminal),
        "reservation.json":_write(root,m.OBSERVER_PARTS,"reservation.json",{"invented":True}),
        "readback.json":_write(root,m.OBSERVER_PARTS,"readback.json",{"invented":True})}
    final = {"schema":"insider-affected-quarter-selector-trusted-publisher-v3/final","audit_id":m.OBSERVER_PARTS[-1],
        "authority":m.selector._authority(),"complete_sha256":complete_hash,"execution_head":"a"*40,
        "journal_leaf_sha256":journal,"old_failed_v1_promoted_or_rewritten":False,
        "parent_isolation":"trusted_unsandboxed_python_audit_guard_not_native_denial",
        "preceding_failed_observer_preserved":True,"registration_sha256":"d"*64,"selection_sha256":selected_hash,
        "semantic_exit0_observed":True,"semantic_invocations_performed":1,"strict_readback_accepted":True}
    return selected_hash,complete_hash,_write(root,m.OBSERVER_PARTS,"final.json",final)


def _earnings_fixture(root):
    manifest = dict.fromkeys(m._MANIFEST_KEYS,False)
    manifest.update(schema="insider-eodhd-date-window-earnings-continuation-v5",campaign_id=m.EARNINGS_ID,
        profile="eodhd-calendar-unattempted-only-20200301-20260731-v5",registered_at_utc="2026-10-14T00:00:00Z",
        fixture_only=True,identity={"head":"a"*40},windows=[list(x) for x in m._windows()],
        previous_campaign_anchor={"invented":"e"*64},owner_direction="Invented temporary fixture only",
        owner_acknowledged_rotated_token=True,maximum_attempts_per_window=1,maximum_local_custody_read_reattachments=3,
        maximum_body_bytes_per_window=m.MAX_BODY,maximum_rows_per_window=200000,maximum_metadata_bytes_per_window=m.MAX_METADATA,
        maximum_control_bytes_per_leaf=m.MAX_CONTROL,timeout_seconds=15,minimum_start_interval_seconds=1.0,
        window_scope_sha256=[m._sha(m._raw(m.custody._scope(w))) for w in m._windows()],disk_preflight={"invented":True})
    manifest_hash = _write(root,m.EARNINGS_PARTS,"manifest.json",manifest);results = []
    for index,window in enumerate(m._windows()):
        prefix = f"window-{index:04d}"
        # Deliberately NOT JSON: an unintended financial/body decode fails.
        body = b"INVENTED OPAQUE FINANCIAL BODY NOT JSON"+str(index).encode()
        metadata = b"INVENTED OPAQUE ROW METADATA HASH ONLY"+str(index).encode()
        body_hash = _write(root,m.EARNINGS_PARTS,prefix+"-response.json",body,raw=True)
        metadata_hash = _write(root,m.EARNINGS_PARTS,prefix+"-metadata.json",metadata,raw=True)
        receipt = dict.fromkeys(m._RECEIPT_KEYS,False)
        receipt.update(sample_rows=3,metadata_accepted_rows=2,quarantined_rows=1,timing_unknown_rows=1,unknown_status_rows=0,
            reported_rows=3,duplicate_fiscal_period_rows=0,metadata_conflicting_fiscal_periods=0,
            all_rows_retained_in_source_order=True,body_sha256=body_hash,body_size_bytes=len(body),
            calendar_window_observed=True,disposition="calendar_window_observed",http_response_observed=True,http_status=200,
            metadata_sha256=metadata_hash,response_body_retained=True,transport_invocation_count=1)
        scope = m.custody._scope(window)
        scope_hash = _write(root,(*m.EARNINGS_BASE,"scopes"),m._sha(m._raw(scope))+".json",
            {"schema":manifest["schema"],"scope":scope,"campaign_id":m.EARNINGS_ID,"reserved_at_utc":"2026-10-14T00:00:00Z","maximum_attempts":1})
        started_hash = _write(root,m.EARNINGS_PARTS,prefix+"-started.json",{"schema":manifest["schema"],"window":list(window),
            "index":index,"started_at_utc":"2026-10-14T00:00:00Z","manifest_sha256":manifest_hash,
            "scope_reservation_sha256":scope_hash,"maximum_attempts":1})
        child_hash = _write(root,m.EARNINGS_PARTS,prefix+"-complete.json",{"schema":manifest["schema"],"window":list(window),
            "index":index,"completed_at_utc":"2026-10-14T00:00:00Z","manifest_sha256":manifest_hash,
            "started_sha256":started_hash,"scope_reservation_sha256":scope_hash,"receipt":receipt})
        results.append({"index":index,"window":list(window),"receipt":receipt,"complete_sha256":child_hash})
    # Independently transcribed producer summary schema (continuation5 source).
    # Do not let an incorrect consumer constant manufacture a matching fixture.
    producer_keys = {*m.FALSE_FLAGS,"schema","campaign_id","completed_at_utc","manifest_sha256","identity","fixture_only",
        "previous_campaign_anchor","planned_windows","transport_invocation_count","observed_windows",
        "refused_or_ambiguous_windows","unattempted_windows","all_registered_windows_observed","window_results",
        "credential_or_path_or_hash_retained","source_rows","metadata_accepted_rows","quarantined_rows","looks_jobs_backtests"}
    complete = dict.fromkeys(producer_keys,False)
    complete.update(schema=manifest["schema"],campaign_id=m.EARNINGS_ID,completed_at_utc="2026-10-14T00:00:00Z",
        fixture_only=True,identity=manifest["identity"],looks_jobs_backtests=[0,0,0],manifest_sha256=manifest_hash,
        metadata_accepted_rows=154,quarantined_rows=77,source_rows=231,observed_windows=77,planned_windows=77,
        previous_campaign_anchor=manifest["previous_campaign_anchor"],refused_or_ambiguous_windows=0,
        unattempted_windows=[],transport_invocation_count=77,window_results=results,all_registered_windows_observed=True)
    complete_hash = _write(root,m.EARNINGS_PARTS,"complete.json",complete)
    _write(root,m.EARNINGS_BASE,"campaign.lock",b"",raw=True)
    return manifest_hash,complete_hash


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    root = tmp_path_factory.mktemp("invented-pilot-metadata").resolve();root.chmod(0o700)
    return root,m.Anchors(*_earnings_fixture(root),*_selector_fixture(root))


@pytest.fixture
def supplied(tmp_path,original):
    template,anchors = original;root = (tmp_path/"invented-copy").resolve();shutil.copytree(template,root)
    return root,anchors


def test_exact_buffers_and_counts_without_financial_decode(supplied,monkeypatch):
    old = m._json
    def controls_only(raw):
        assert b"INVENTED OPAQUE" not in raw
        return old(raw)
    monkeypatch.setattr(m,"_json",controls_only)
    result = m.audit_fixture(*supplied);earnings,sec = result["earnings"],result["sec"]
    assert result["fixture_only"] is True
    assert len(earnings["buffered_months"]) == 67 and earnings["pilot_month_count"] == 60
    assert earnings["buffered_months"][0]["window"] == ["2020-10-01","2020-10-31"]
    assert earnings["buffered_months"][-1]["window"] == ["2026-04-01","2026-04-30"]
    assert earnings["pilot_counts"]["sample_rows"] == 180 and earnings["pilot_counts"]["metadata_accepted_rows"] == 120
    assert earnings["pilot_counts"]["quarantined_rows"] == 60 and earnings["producer_receipt_counts_not_recomputed_row_semantics"] is True
    assert earnings["metadata_rows_decoded_here"] is earnings["source_financial_bodies_decoded"] is False
    assert len(sec["quarters"]) == 25 and sec["pilot_quarter_count"] == 20
    assert sec["pilot_counts"]["submission_rows"] == 120 and sec["pilot_counts"]["form4_or_4a_rows"] == 40
    assert sec["pilot_form_counts"] == dict.fromkeys(m.selector.pure.FORMS,20)
    assert sec["failed_predecessor_promoted"] is sec["original_parent_admission_established_here"] is False
    assert result["calendar_session_buffer_sufficiency_verified"] is False
    assert result["raw_price_or_return_values_read"] is result["signals_joined_to_outcomes"] is False
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert all(result[name] == 0 for name in ("new_provider_requests","credential_reads","qc_jobs","backtests","research_looks"))
    assert len(result["held_input_leaf_sha256"]) == 2+77*3+67*2+3+4
    assert b"INVENTED OPAQUE" not in m._raw(result)


@pytest.mark.parametrize("kind",["body","metadata","manifest_hash","complete_hash","selection_hash","selector_complete_hash","observer_hash",
    "extra_campaign_leaf","extra_scope_leaf","missing_month","public_leaf","symlink","hardlink"])
def test_pins_rosters_and_private_topology(supplied,kind):
    root,anchors = supplied;path = root.joinpath(*m.EARNINGS_PARTS,"window-0007-response.json")
    if kind in {"body","metadata"}:
        if kind == "metadata":path = path.with_name("window-0007-metadata.json")
        path.write_bytes(path.read_bytes()+b"changed")
    elif kind.endswith("_hash"):
        key = {"manifest_hash":"earnings_manifest","complete_hash":"earnings_complete","selection_hash":"selection",
            "selector_complete_hash":"selector_complete","observer_hash":"observer_final"}[kind]
        anchors = replace(anchors,**{key:"f"*64})
    elif kind == "extra_campaign_leaf":_write(root,m.EARNINGS_PARTS,"unexpected.json",{})
    elif kind == "extra_scope_leaf":_write(root,(*m.EARNINGS_BASE,"scopes"),"unexpected.json",{})
    elif kind == "missing_month":path.unlink()
    elif kind == "public_leaf":path.chmod(0o644)
    elif kind == "symlink":
        target = root/"invented-target";target.write_bytes(path.read_bytes());target.chmod(0o600);path.unlink();path.symlink_to(target)
    elif kind == "hardlink":os.link(path,root/"invented-alias")
    with pytest.raises(m.PilotCoverageError):m.audit_fixture(root,anchors)


@pytest.mark.parametrize("field,value",[("sample_rows",True),("http_status",True),("transport_invocation_count",True),
    ("body_size_bytes",True),("metadata_accepted_rows",4),("timing_unknown_rows",2),
    ("financial_values_evaluated_or_projected",True),("canonical_ready",True),("unknown_status_rows",True),
    ("empty_result_is_coverage_evidence",True)])
def test_receipt_typed_counts_partitions_and_false_authorities(original,field,value):
    root,_ = original;receipt = copy.deepcopy(_read(root,m.EARNINGS_PARTS,"complete.json")["window_results"][0]["receipt"])
    receipt[field] = value
    with pytest.raises(m.PilotCoverageError):m._receipt(receipt)


@pytest.mark.parametrize("change",[lambda v:v.update(schema="unrecognized"),lambda v:v.update(planned_windows=True),
    lambda v:v.update(credential_or_path_or_hash_retained=True),lambda v:v.update(looks_jobs_backtests=[False,0,0]),
    lambda v:v["window_results"].reverse(),lambda v:v.update(source_rows=230)])
def test_campaign_schema_order_and_aggregates_with_fresh_fixture_pin(supplied,change):
    root,anchors = supplied;digest = _change(root,m.EARNINGS_PARTS,"complete.json",change)
    with pytest.raises(m.PilotCoverageError):m.audit_fixture(root,replace(anchors,earnings_complete=digest))


@pytest.mark.parametrize("field,value",[("maximum_attempts_per_window",True),("maximum_local_custody_read_reattachments",4),
    ("retry_resume_permitted",True),("window_scope_sha256",[]),("owner_acknowledged_rotated_token",False),
    ("minimum_start_interval_seconds",True),("rotation_independently_verified",True)])
def test_registered_scope_and_limits_before_child_controls(supplied,field,value):
    root,anchors = supplied;digest = _change(root,m.EARNINGS_PARTS,"manifest.json",lambda v:v.update({field:value}))
    complete = _read(root,m.EARNINGS_PARTS,"complete.json");complete["manifest_sha256"] = digest
    complete_hash = _write(root,m.EARNINGS_PARTS,"complete.json",complete)
    with pytest.raises(m.PilotCoverageError,match="operational_controls"):
        m.audit_fixture(root,replace(anchors,earnings_manifest=digest,earnings_complete=complete_hash))


@pytest.mark.parametrize("field,value",[("semantic_exit0_observed",False),("strict_readback_accepted",False),
    ("old_failed_v1_promoted_or_rewritten",True),("semantic_invocations_performed",True),("complete_sha256","f"*64)])
def test_identical_failed_candidate_bytes_do_not_substitute_for_success(supplied,field,value):
    root,anchors = supplied;digest = _change(root,m.OBSERVER_PARTS,"final.json",lambda v:v.update({field:value}))
    with pytest.raises(m.PilotCoverageError):m.audit_fixture(root,replace(anchors,observer_final=digest))


@pytest.mark.parametrize("change",[lambda v:v.update(exit_code=2),lambda v:v.update(exit_code=False),
    lambda v:v.update(terminal_success_observed=False),lambda v:v.update(timed_out=True),lambda v:v.update(stderr_bytes=1),
    lambda v:v.update(extra_authority=True)])
def test_actual_successful_terminal_required_beyond_final_assertions(supplied,change):
    root,anchors = supplied;digest = _change(root,m.OBSERVER_PARTS,"terminal.json",change)
    final = _read(root,m.OBSERVER_PARTS,"final.json");final["journal_leaf_sha256"]["terminal.json"] = digest
    digest = _write(root,m.OBSERVER_PARTS,"final.json",final)
    with pytest.raises(m.PilotCoverageError):m.audit_fixture(root,replace(anchors,observer_final=digest))


@pytest.mark.parametrize("kind",["body_same_size_mtime_restored","metadata","extra","lock"])
def test_final_recheck_detects_post_semantic_changes(supplied,monkeypatch,kind):
    root,anchors = supplied;old = m._selector
    def changed(held,pins):
        result = old(held,pins);path = root.joinpath(*m.EARNINGS_PARTS,"window-0007-response.json")
        if kind == "body_same_size_mtime_restored":
            stamp = path.stat();raw = path.read_bytes();path.write_bytes(b"X"+raw[1:]);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        elif kind == "metadata":
            path = path.with_name("window-0007-metadata.json");path.write_bytes(path.read_bytes()+b"X")
        elif kind == "extra":_write(root,m.EARNINGS_PARTS,"late-extra.json",{})
        elif kind == "lock":root.joinpath(*m.EARNINGS_BASE,"campaign.lock").write_bytes(b"X")
        return result
    monkeypatch.setattr(m,"_selector",changed)
    with pytest.raises(m.PilotCoverageError):m.audit_fixture(root,anchors)


@pytest.mark.parametrize("root",[m.LANE_ROOT,m.LANE_ROOT.parent,m.LANE_ROOT/"invented",Path("relative"),
    Path("/System/Volumes/Data")/str(m.LANE_ROOT).lstrip("/")])
def test_fixture_denies_lane_ancestors_descendants_and_firmlink_alias(root):
    with pytest.raises(m.PilotCoverageError,match="outside_lane"):m.audit_fixture(root,m.ACTUAL_ANCHORS)


def test_fixture_native_network_denial_precedes_inputs(monkeypatch,supplied):
    def refused(**kwargs):raise m.PilotCoverageError("network_denial_not_effective")
    monkeypatch.setattr(m.custody,"_effective_denial",refused)
    monkeypatch.setattr(m,"_audit",lambda *_:pytest.fail("metadata must not be opened"))
    with pytest.raises(m.PilotCoverageError,match="network_denial"):m.audit_fixture(*supplied)


def test_worker_flags_checked_before_input(monkeypatch):
    monkeypatch.setattr(m,"_audit",lambda *_:pytest.fail("metadata must not be opened"))
    with pytest.raises(m.PilotCoverageError,match="isolated_worker"):m._worker({})


def test_native_initial_worker_denial_proofs_without_artifact_reads():
    code = ("import sys;sys.path.insert(0,"+repr(str(m.LANE_ROOT))+");from research import insider_buying_pilot_coverage_audit as m;"
        "sources={m.SELF_PATH:'a'*64};identity={'root':str(m.LANE_ROOT),'branch':m.LANE_BRANCH,'head':'b'*40,'clean':True,"
        "'source_sha256':sources,'source_inventory_sha256':m._sha(m._raw(sources))};"
        "m.custody._source_bytes=lambda *args:sources;m._audit=lambda *args:{'invented':True};calls=[];original=m.os.execve;"
        "exec(\"def observed_exec(*args):\\n calls.append(args[0]);return original(*args)\");m.os.execve=observed_exec;"
        "value=m._worker(identity);assert value['effective_native_network_fork_allwrite_denial'] is True;"
        "assert value['effective_native_credential_exec_denial'] is True;assert calls==['/usr/bin/security'];print('invented-native-denial-ok')")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    child = subprocess.run(("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+m.EMPTY_CACHE_PREFIX,"-c",code),
        capture_output=True,timeout=30,cwd=m.LANE_ROOT)
    if child.returncode == 71 and child.stderr == b"sandbox-exec: sandbox_apply: Operation not permitted\n":
        pytest.skip("macOS denies nested sandbox application; run the same invented proof as an initial native sandbox")
    assert child.returncode == 0,child.stderr.decode()
    assert child.stdout == b"invented-native-denial-ok\n" and child.stderr == b""


def test_actual_parent_git_checks_outside_initial_fork_denied_child(monkeypatch,supplied):
    value = m.audit_fixture(*supplied);value["fixture_only"] = False
    monkeypatch.setattr(m,"ACTUAL_ANCHORS",supplied[1])
    sources = {m.SELF_PATH:"a"*64};identity = {"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"b"*40,
        "clean":True,"source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))};calls = []
    def parent(head):calls.append(("identity",head));return copy.deepcopy(identity)
    def worker(command,**kwargs):
        calls.append(("child",command))
        assert command[:3] == ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin")
        assert all(flag in command for flag in ("-I","-S","-B"))
        assert "deny process-fork" in command[5] and "deny file-write*" in command[5]
        assert kwargs["input"] == m._raw(identity) and kwargs["timeout"] == 240
        value.update(execution_identity=identity,effective_native_network_fork_allwrite_denial=True,effective_native_credential_exec_denial=True)
        return SimpleNamespace(returncode=0,stderr=b"",stdout=m._raw(value)+b"\n")
    monkeypatch.setattr(m.custody,"_identity",parent);monkeypatch.setattr(m.subprocess,"run",worker)
    assert m.run_actual("b"*40)["execution_identity"] == identity
    assert [x[0] for x in calls] == ["identity","child","identity"]


@pytest.mark.parametrize("change",[lambda v:v.update(backtesting_ready=True),lambda v:v.update(qc_jobs=99),
    lambda v:v.update(credential_reads=False),lambda v:v.update(unexpected=True),lambda v:v["earnings"]["buffered_months"].pop(),
    lambda v:v["earnings"]["buffered_months"][0]["counts"].update(sample_rows=True),
    lambda v:v["earnings"]["pilot_counts"].update(sample_rows=0),lambda v:v["sec"]["quarters"].pop(),
    lambda v:v["sec"]["pilot_counts"].update(submission_rows=0),lambda v:v.update(held_input_leaf_sha256={}),
    lambda v:v["held_input_leaf_sha256"].update({"/".join((*m.EARNINGS_PARTS,"manifest.json")):"f"*64}),
    lambda v:v["held_input_leaf_sha256"].update({"/".join((*m.EARNINGS_PARTS,"window-0007-metadata.json")):"f"*64})])
def test_parent_strict_result_guard_rejects_authority_and_count_laundering(supplied,monkeypatch,change):
    value = m.audit_fixture(*supplied);identity = {"invented":True}
    value.update(fixture_only=False,execution_identity=identity,effective_native_network_fork_allwrite_denial=True,
        effective_native_credential_exec_denial=True)
    monkeypatch.setattr(m,"ACTUAL_ANCHORS",supplied[1])
    assert m._validate_result(copy.deepcopy(value),identity) == value
    change(value)
    with pytest.raises(m.PilotCoverageError):m._validate_result(value,identity)


def test_parent_worker_refusal_not_accepted(monkeypatch):
    identity = {"source_sha256":{m.SELF_PATH:"a"*64}}
    monkeypatch.setattr(m.custody,"_identity",lambda _:identity)
    monkeypatch.setattr(m.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0,stderr=b"private",stdout=b"{}"))
    with pytest.raises(m.PilotCoverageError,match="worker_refused"):m.run_actual("b"*40)


def test_cli_fixed_refusal_exit_two_no_private_exception(monkeypatch,capsys):
    def refused(_):raise ValueError("PRIVATE INPUT OR TOKEN MUST NOT ESCAPE")
    monkeypatch.setattr(m,"run_actual",refused)
    assert m.main(["--expected-head","b"*40]) == 2
    assert capsys.readouterr().out == '{"disposition":"retained_pilot_metadata_audit_refused"}\n'


def test_close_drains_all_handles_and_preserves_primary(tmp_path):
    closed = []
    def broken(label):
        def close():closed.append(label);raise OSError("private cleanup failure")
        return close
    held = m._Held(tmp_path);held.chains = {("first",):SimpleNamespace(close=broken("first")),("second",):SimpleNamespace(close=broken("second"))}
    with pytest.raises(m.PilotCoverageError,match="cleanup"):held.close()
    assert closed == ["second","first"]
    held.chains = {("third",):SimpleNamespace(close=broken("third"))}
    with pytest.raises(ValueError,match="primary"):
        try:raise ValueError("primary")
        finally:held.close()
    assert closed[-1] == "third"


def test_control_duplicate_nonfinite_noncanonical_and_wrong_root_refused():
    for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{ "x":1}',b'[]'):
        with pytest.raises(m.PilotCoverageError):m._json(raw)
