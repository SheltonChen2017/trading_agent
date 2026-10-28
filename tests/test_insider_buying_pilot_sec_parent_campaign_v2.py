"""Invented full25-quarter metadata only; production inputs/transport forbidden."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
from research import insider_buying_pilot_sec_parent_campaign_v2 as m


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec=importlib.util.spec_from_file_location("invented_campaign_source_fixture",Path(__file__).with_name("test_insider_buying_pilot_sec_fresh_selection.py"))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper,helper.corpus.__wrapped__(tmp_path_factory)


def _proof():
    return {"old_exposure_inventory_sha256":"a"*64,"old_exposure_snapshot_sha256":"b"*64,"latest64_report_sha256":"c"*64,
        "latest64_capture_head":"d"*40,"latest64_source_inventory_sha256":"e"*64,"old_count":0,"new64_count":0}


def _pipeline(corpus,*,consumed=(),number=1,limit=None,mutate=None):
    helper,fixture=corpus
    _unused,generated,completed,emitted=helper._pipeline(fixture)
    builder=m.CampaignBatchBuilder(consumed=sorted(consumed),batch_number=number,predecessor=None if number==1 else {"invented_predecessor":True},limit=limit)
    for row in emitted:
        item=deepcopy(row)
        if mutate:mutate(item)
        builder.consume(item)
    return builder,generated,completed,emitted


def _finish(pipeline):
    builder,generated,completed,_=pipeline
    return builder.finish(source_roster=generated,parent_audit=completed,base_consumption=_proof())


def test_full25_quarter_genuine_stream_selects_first64_context_targets_not_old_pilot_prefix(corpus):
    pipeline=_pipeline(corpus);sealed=_finish(pipeline);body=sealed.to_payload()
    eligible=[row for row in pipeline[3] if row["fresh_locatable_candidate"]]
    assert body["selected_count"]==64 and len(body["parent_audit"]["quarters"])==25
    assert [row["request"] for row in body["requests"]]==[row["request"] for row in eligible[:64]]
    assert body["requests"][0]["request"]["period"]=="2020Q1"
    assert body["source_roster_sha256"]==pipeline[1].sha256 and body["parent_audit_sha256"]==pipeline[2].sha256
    assert m.validate_batch_plan(body)==body and sealed.sha256==m._sha(sealed.canonical_bytes())
    assert all(v is False if type(v) is bool else v==0 for v in body["authority"].values())
    assert b"PRIVATE FINANCIAL SENTINEL" not in sealed.canonical_bytes()


def test_new64_old_consumed_and_ambiguous_keys_are_all_excluded_without_reclassifying_archive_members(corpus):
    targets=[row["accession_number"] for row in corpus[1][3] if row["form_type"] in {"4","4/A"}][:12]
    body=_finish(_pipeline(corpus,consumed=targets)).to_payload()
    assert not set(targets)&{row["request"]["accession_number"] for row in body["requests"]}
    assert body["consumed_accessions"]==sorted(targets) and body["archive_exposures"]==list(m.ARCHIVE_EXPOSURES)
    assert body["archive_membership_known"] is False
    assert body["policy"]["archive_membership_unknown_is_not_zero_exposure_or_an_accession_claim"] is True


def test_requests_preserve_source_rawCIK_master_folder_ordinals_and_all_hashes(corpus):
    body=_finish(_pipeline(corpus)).to_payload()
    for ordinal,row in enumerate(body["requests"],1):
        assert row["selection_ordinal"]==ordinal and row["request"]["issuer_cik"]==row["source"]["raw_issuer_cik"]
        assert row["request"]["source_record_ordinal"]==row["source"]["source_record_ordinal"]
        assert row["request"]["archive_path"].startswith("edgar/data/999/")
        assert row["request_sha256"]==m._sha(m._raw(row["request"]))


@pytest.mark.parametrize("number,limit",((True,None),(0,None),(20001,None),(1,1024),(2,1025),(2,True)))
def test_strict_batch_and_expansion_bounds(number,limit):
    with pytest.raises(ValueError):m.CampaignBatchBuilder(consumed=[],batch_number=number,predecessor=None if number==1 else {},limit=limit)


def test_subsequent_plan_can_be_bounded1024_but_never_proves_capture_by_itself(corpus):
    body=_finish(_pipeline(corpus,number=2)).to_payload()
    assert body["limit"]==1024 and body["selected_count"]<1024 and body["fixture_only"] is True
    assert body["predecessor"]=={"invented_predecessor":True}
    with pytest.raises(ValueError):m.CampaignBatchBuilder(consumed=[],batch_number=2,predecessor=None)


def test_missing_full_stream_or_forged_factory_cannot_seal(corpus):
    pipeline=_pipeline(corpus);builder,generated,completed,_=pipeline
    with pytest.raises(ValueError):builder.finish(source_roster=SimpleNamespace(to_payload=generated.to_payload),parent_audit=completed,base_consumption=_proof())
    with pytest.raises(ValueError):builder.finish(source_roster=generated,parent_audit=completed,base_consumption=_proof())
    forged=replace(_finish(_pipeline(corpus)),_bytes=b"{}")
    with pytest.raises(ValueError):forged.to_payload()


@pytest.mark.parametrize("fault",("source_hash","source_order","bool","authority","locator","late_repeat"))
def test_source_dispositions_fail_closed_without_deduplicating_or_filling_gaps(corpus,fault):
    pipeline=_pipeline(corpus);emitted=pipeline[3];builder=m.CampaignBatchBuilder(consumed=[],batch_number=1,predecessor=None)
    selected=next(row for row in emitted if row["fresh_locatable_candidate"])
    def mutate(row):
        if row["source"]!=selected["source"]:return
        if fault=="source_hash":row["source_record_sha256"]="0"*64
        elif fault=="source_order":row["source"]["source_record_ordinal"]=99
        elif fault=="bool":row["cross_quarter_accession_repeat"]=0
        elif fault=="authority":row["canonical_admitted"]=True
        elif fault=="locator":row["selected_locator"]["archive_path"]="edgar/data/999/0000000001-20-999999.txt"
        else:row["cross_quarter_accession_repeat"]=True
    if fault=="late_repeat":
        for row in emitted:item=deepcopy(row);mutate(item);builder.consume(item)
        with pytest.raises(ValueError):builder.finish(source_roster=pipeline[1],parent_audit=pipeline[2],base_consumption=_proof())
    else:
        with pytest.raises(ValueError):
            for row in emitted:item=deepcopy(row);mutate(item);builder.consume(item)
        with pytest.raises(ValueError):builder.consume(deepcopy(emitted[0]))


@pytest.mark.parametrize("fault",("request_count","request_bool","url","rawcik","digest","consumed","source_total","authority","archive","policy","base_bool"))
def test_detached_control_mutations_are_not_accepted_as_genuine_plans(corpus,fault):
    value=_finish(_pipeline(corpus)).to_payload()
    if fault=="request_count":value["selected_count"]+=1
    elif fault=="request_bool":value["requests"][0]["request"]["source_record_ordinal"]=True
    elif fault=="url":value["requests"][0]["request"]["url"]=m.ARCHIVE_EXPOSURES[0]["url"]
    elif fault=="rawcik":value["requests"][0]["request"]["issuer_cik"]="0000000999"
    elif fault=="digest":value["requests"][0]["request_sha256"]="f"*64
    elif fault=="consumed":
        value["consumed_accessions"]=[value["requests"][0]["request"]["accession_number"]]
        value["consumed_index_sha256"]=m._sha(m._raw(value["consumed_accessions"]))
    elif fault=="source_total":value["source_roster"]["counts"]["context_form4_or_4a_rows"]+=1
    elif fault=="authority":value["authority"]["sec_dispatches"]=True
    elif fault=="archive":value["archive_membership_known"]=True
    elif fault=="policy":value["policy"]["maximum_attempts_per_accession"]=2
    else:value["base_consumption"]["old_count"]=True
    with pytest.raises(ValueError):m.validate_batch_plan(value)


def test_factory_returns_detached_deep_copies(corpus):
    sealed=_finish(_pipeline(corpus));value=sealed.to_payload();value["policy"]["maximum_attempts_per_accession"]=99
    assert sealed.to_payload()["policy"]==m.POLICY


def _controls(plan,root):
    identity={"root":str(root.resolve()),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":{m.SELF_PATH:"b"*64,m.TEST_PATH:"c"*64}}
    identity["source_inventory_sha256"]=m._sha(m._raw(identity["source_sha256"]))
    reservation={"schema":m.SCHEMA+"/reservation","batch_number":plan["batch_number"],"execution_identity":identity,
        "policy":m.POLICY,"authority":m.AUTHORITY,"predecessor_pins":None,"stopped_launch_lineage":m._launch_lineage()}
    raw=m._raw(reservation);plan_raw=m._raw(plan)
    complete={"schema":m.SCHEMA+"/complete","batch_number":plan["batch_number"],"execution_identity":identity,
        "reservation_sha256":m._sha(raw),"plan_sha256":m._sha(plan_raw),"stopped_launch_lineage":m._launch_lineage(),"native_network_fork_allwrite_securityexec_denial":True,"authority":m.AUTHORITY}
    return {"reservation.json":raw,"plan.json":plan_raw,"complete.json":m._raw(complete)}


def test_coherent_plan_reservation_complete_rewrite_is_not_external_authentication(corpus,tmp_path):
    original=_controls(_finish(_pipeline(corpus)).to_payload(),tmp_path)
    pins={"expected_plan_sha256":m._sha(original["plan.json"]),"expected_complete_sha256":m._sha(original["complete.json"]),"expected_producer_head":"a"*40}
    assert m._validate_plan_controls(original,1,fixture=True,**pins)[0]["batch_number"]==1
    changed=json.loads(original["plan.json"]);changed["consumed_accessions"]=["0000000009-21-999999"]
    changed["consumed_index_sha256"]=m._sha(m._raw(changed["consumed_accessions"]))
    coherent=_controls(changed,tmp_path)
    with pytest.raises(ValueError,match="external"):m._validate_plan_controls(coherent,1,fixture=True,**pins)


def test_one_controller_lock_no_old_scope_resume_or_batch_gap(tmp_path):
    root=tmp_path.resolve();first=m.Controller(root,create=True,fixture=True)
    try:
        with pytest.raises(BlockingIOError):m.Controller(root,fixture=True)
        run=first.fresh(1);run.publish("reservation.json",b'{"invented":true}')
        with pytest.raises(ValueError):first.fresh(1)
        with pytest.raises(ValueError):first.fresh(3)
    finally:first.close()


def test_controller_refuses_uncooperative_new_batch_during_native_worker(tmp_path):
    controller=m.Controller(tmp_path.resolve(),create=True,fixture=True)
    try:
        controller.fresh(1)
        os.mkdir(controller.batches.path/"batch-000002",0o700)
        with pytest.raises(ValueError,match="unexpected_batch"):controller.check()
    finally:controller.close()


def _held_plan(corpus,tmp_path):
    plan=_finish(_pipeline(corpus)).to_payload();raws=_controls(plan,tmp_path)
    controller=m.Controller(tmp_path.resolve(),create=True,fixture=True)
    try:
        run=controller.fresh(1)
        for name,raw in raws.items():run.publish(name,raw,cap=m.MAX_CONTROL)
    finally:controller.close()
    pins={"expected_plan_sha256":m._sha(raws["plan.json"]),"expected_complete_sha256":m._sha(raws["complete.json"]),"expected_producer_head":"a"*40}
    return m.HeldBatchPlan(tmp_path.resolve(),1,fixture=True,**pins),pins


def test_pinned_plan_keeps_open_custody_and_detects_samebyte_initial_or_later_ctime_change(corpus,tmp_path):
    held,pins=_held_plan(corpus,tmp_path)
    try:
        assert held.plan["selected_count"]==64 and held.receipt["plan_sha256"]==pins["expected_plan_sha256"]
        held.recheck();path=held.tree.path/"plan.json";os.chmod(path,0o640);os.chmod(path,0o600)
        with pytest.raises(ValueError,match="old_plan_changed"):held.recheck()
    finally:held.close()
    with pytest.raises(ValueError,match="hold_closed"):held.recheck()


def test_pinned_plan_first_read_ctime_mutation_is_not_new_output_settlement(corpus,tmp_path,monkeypatch):
    held,pins=_held_plan(corpus,tmp_path);path=held.tree.path/"plan.json";held.close()
    before=path.stat();original=m.os.read;changed=[]
    def read(fd,count):
        info=m.os.fstat(fd)
        if not changed and (info.st_dev,info.st_ino)==(before.st_dev,before.st_ino):
            changed.append(True);os.chmod(path,0o640);os.chmod(path,0o600)
        return original(fd,count)
    monkeypatch.setattr(m.os,"read",read)
    with pytest.raises(ValueError,match="old_plan_changed"):m.HeldBatchPlan(tmp_path.resolve(),1,fixture=True,**pins)
    assert changed


@pytest.mark.parametrize("phase",sorted(m.PHASES))
def test_worker_failure_stages_are_finite_and_never_exception_or_contact_text(phase):
    error=ValueError("invented-private-contact@unit.test");error._campaign_phase=phase
    value=m._safe_failure(error)
    assert value=={"schema":m.SCHEMA+"/worker-refusal","phase":phase,"code":"native_or_control_refused"}
    assert "private" not in repr(value)


def test_native_refusal_CLI_reports_only_typed_stage_and_fixed_code(monkeypatch,capsys):
    def refuse(*a,**k):raise m.NativeWorkerRefused("source_rederivation","source_population_changed")
    monkeypatch.setattr(m,"prepare_actual_batch",refuse)
    assert m.main(["--expected-head","a"*40])==2
    assert json.loads(capsys.readouterr().out)=={"disposition":"campaign_plan_refused","failure_stage":"source_rederivation","failure_code":"source_population_changed"}


@pytest.mark.parametrize("fault",("consumed_extra","consumed_missing","capture_identity","finish_clock","complete_pin","first64_pin"))
def test_coherently_reanchored_local_indexes_still_need_exact_predecessor_semantics(fault):
    from research import insider_buying_pilot_sec_parent_batch_capture_v2 as capture
    previous={"batch_number":1,"complete_sha256":"a"*64,"plan_sha256":"b"*64,"index_sha256":"c"*64,
        "complete":{"execution_identity":{"invented":True},"last_finished_utc":"2026-10-26T00:00:00+00:00","capture_completed_without_refusal":True},
        "index":{"accessions":["0000000001-21-000001"]}}
    proof={"batch_number":1,"complete_sha256":"a"*64,"plan_sha256":"b"*64,"index_sha256":"c"*64,
        "capture_execution_identity":{"invented":True},"first64_success_sha256":"a"*64,
        "last_finished_utc":"2026-10-26T00:00:00+00:00","capture_completed_without_refusal":True}
    following={"batch_number":2,"plan":{"batch_number":2,"consumed_accessions":["0000000001-21-000001"],"predecessor":proof},"index":{"predecessor_index_sha256":"c"*64}}
    capture._validate_predecessor_link(following,previous)
    if fault=="consumed_extra":following["plan"]["consumed_accessions"].append("0000000001-21-000002")
    elif fault=="consumed_missing":following["plan"]["consumed_accessions"]=[]
    elif fault=="capture_identity":proof["capture_execution_identity"]={"invented_changed":True}
    elif fault=="finish_clock":proof["last_finished_utc"]="2026-10-26T01:00:00+00:00"
    elif fault=="complete_pin":proof["complete_sha256"]="d"*64
    else:proof["first64_success_sha256"]="e"*64
    with pytest.raises(ValueError,match="predecessor"):capture._validate_predecessor_link(following,previous)


@pytest.mark.parametrize("status,stage,code",((None,"complete","none"),(403,"body_privacy","finite_privacy_refused"),(200,"header_identity","header_identity_unbound")))
def test_unretained_terminal_cannot_claim_complete_or_wrong_HTTP_failure_stage(status,stage,code):
    from research import insider_buying_pilot_sec_parent_batch_capture_v2 as capture
    row={"request_sha256":"a"*64}
    value={"schema":capture.SCHEMA+"/result","ordinal":0,"attempt":1,"request_sha256":"a"*64,"start_sha256":"b"*64,
        "raw_transport_invocations":0 if status is None else 1,"remote_request_count_measured":False,"http_status":status,
        "failure_stage":stage,"failure_code":code,"body_retained":False,"body_sha256":None,"body_bytes":None,"headers_sha256":None,
        "header_bound":False,"finished_utc":"2026-10-26T00:00:00+00:00","finished_monotonic_ns":1}
    with pytest.raises(ValueError,match="stage"):capture._validate_terminal(value,row,0,"b"*64)


def test_controller_never_accepts_production_fixture_alias_before_any_creation(monkeypatch):
    monkeypatch.setattr(m.archive,"_Output",lambda *a,**k:pytest.fail("no namespace creation"))
    with pytest.raises(ValueError):m.Controller(m.LANE_ROOT,create=True,fixture=True)


def test_actual_front_rejects_source_before_namespace_or_child(monkeypatch):
    monkeypatch.setattr(m,"_identity",lambda _:(_ for _ in ()).throw(ValueError("fixed refusal")))
    monkeypatch.setattr(m,"Controller",lambda *a,**k:pytest.fail("no namespace before source"))
    monkeypatch.setattr(m,"_run_child",lambda *a,**k:pytest.fail("no worker before source"))
    with pytest.raises(ValueError):m.prepare_actual_batch("a"*40)


def test_native_initial_flags_and_denial_precede_inputs(monkeypatch):
    monkeypatch.setattr(m,"_isolated",lambda:(_ for _ in ()).throw(ValueError("initial native")))
    monkeypatch.setattr(m.source.retained,"_PriorHold",lambda:pytest.fail("no actual input"))
    with pytest.raises(ValueError,match="initial native"):m._plan_worker({},1)


def test_command_fixed_native_policy_and_no_contact_or_source_rows_in_argv():
    command=m._command({"invented_source_metadata":True},1)
    assert all(flag in command for flag in ("-I","-S","-B","pycache_prefix="+m.EMPTY_CACHE_PREFIX))
    assert all(rule in command[5] for rule in ("deny network*","deny process-fork","deny file-write*","/usr/bin/security"))
    assert "invented@unit.test" not in repr(command)


@pytest.mark.parametrize("raw",(b'{"x":1,"x":2}',b'{"x":1.2}',b'{"x":NaN}',b' {"x":1}',b'[]'))
def test_own_control_codec_refuses_untrusted_noncanonical_or_noninteger_shapes(raw):
    with pytest.raises(ValueError):m._decode(raw)


def test_production_size_own_codec_not_old100001_list_or32_source_key_limit():
    value={"source_sha256":{f"research/source_{n:04d}.py":"a"*64 for n in range(140)},
        "consumed_accessions":[f"0000000001-21-{n:06d}" for n in range(120000)]}
    assert m._decode(m._raw(value))==value


def test_private_CLI_never_echoes_unknown_secret_argv(monkeypatch,capsys):
    monkeypatch.setattr(m,"prepare_actual_batch",lambda *a,**k:pytest.fail("no plan on invalid argv"))
    assert m.main(["--expected-head","a"*40,"--api-token","PRIVATE"])==2
    captured=capsys.readouterr();assert captured.err=="" and captured.out=='{"disposition":"campaign_plan_refused"}\n'


def test_local_launch2_has_distinct_namespace_but_never_changes_capture_namespace():
    assert m.ARTIFACT_PARTS==("artifacts","insider_buying","pilot_sec_parent_campaign_v2_launch2")
    assert m.CAPTURE_PARTS==("artifacts","insider_buying","pilot_sec_parent_batch_capture_v2")


def test_source_only_launcher_health_refusal_precedes_any_new_namespace(monkeypatch):
    identity={"invented_source_identity":True}
    monkeypatch.setattr(m,"_identity",lambda _:identity)
    def refuse(value):
        assert value is identity
        raise m.NativeWorkerRefused("launcher_health","native_or_control_refused")
    monkeypatch.setattr(m,"_launcher_health",refuse,raising=False)
    monkeypatch.setattr(m,"_stopped_launch_lineage",lambda *a:pytest.fail("old input reached before health"))
    monkeypatch.setattr(m,"Controller",lambda *a,**k:pytest.fail("namespace reached before health"))
    with pytest.raises(m.NativeWorkerRefused,match="native_worker_refused"):
        m.prepare_actual_batch("a"*40)


def _failed_launch(root):
    sources={name:"b"*64 for name in (m.SELF_PATH,m.TEST_PATH,m.CAPTURE_SOURCE_PATH,m.CAPTURE_TEST_PATH)}
    sources.update({f"research/invented_{n:03d}.py":"c"*64 for n in range(112)})
    identity={"root":str(root.resolve()),"branch":m.LANE_BRANCH,"head":"d"*40,"clean":True,"source_sha256":sources,
        "source_inventory_sha256":m._sha(m._raw(sources))}
    raw=m._raw({"schema":m.FAILED_SCHEMA+"/reservation","batch_number":1,"execution_identity":identity,
        "policy":m.POLICY,"authority":m.AUTHORITY,"predecessor_pins":None})
    path=root.joinpath(*m.FAILED_PARTS,"batches","batch-000001");path.mkdir(parents=True,mode=0o700)
    for parent in (root/"artifacts",root/"artifacts"/"insider_buying",path.parent.parent,path.parent,path):os.chmod(parent,0o700)
    lock=path.parent.parent/"controller.lock";lock.write_bytes(m.FAILED_LOCK_BYTES);os.chmod(lock,0o600)
    reservation=path/"reservation.json";reservation.write_bytes(raw);os.chmod(reservation,0o600)
    pin={"sha256":m._sha(raw),"bytes":len(raw),"head":identity["head"],"source_inventory_sha256":identity["source_inventory_sha256"]}
    return reservation,pin,raw


def test_native_old_failed_reservation_is_only_failure_lineage_not_completed_predecessor(tmp_path):
    path,pin,raw=_failed_launch(tmp_path.resolve())
    held=m._FailedLaunchHold(tmp_path.resolve(),fixture=True,pin=pin)
    try:
        assert held.reservation_raw==raw and len(held.identity["source_sha256"])==116
        assert held.summary["batch_inventory"]==["reservation.json"]
        assert held.summary["completed_predecessor"] is held.summary["historical_dispatch_count_measured"] is False
        held.recheck()
    finally:held.close()
    assert path.read_bytes()==raw


def test_failed_reservation_first_read_ctime_mutation_refuses(tmp_path,monkeypatch):
    path,pin,_raw=_failed_launch(tmp_path.resolve());before=path.stat();original=m.os.read;changed=[]
    def read(fd,count):
        result=original(fd,count)
        if not changed and m.os.fstat(fd).st_ino==before.st_ino:
            changed.append(True);os.chmod(path,0o640);os.chmod(path,0o600)
        return result
    monkeypatch.setattr(m.os,"read",read)
    with pytest.raises(ValueError,match="failed_old_control_changed"):
        m._FailedLaunchHold(tmp_path.resolve(),fixture=True,pin=pin)
    assert changed and path.stat().st_mtime_ns==before.st_mtime_ns


@pytest.mark.parametrize("fault",("pin","complete","head","inventory","old_lock"))
def test_failed_launch_exact_old_inventory_pin_and_shared_lock(tmp_path,fault):
    path,pin,raw=_failed_launch(tmp_path.resolve());lock=None
    if fault=="pin":pin["sha256"]="e"*64
    elif fault=="complete":extra=path.parent/"complete.json";extra.write_bytes(b"{}");os.chmod(extra,0o600)
    elif fault=="head":pin["head"]="f"*40
    elif fault=="inventory":pin["source_inventory_sha256"]="0"*64
    else:
        lock=os.open(path.parent.parent.parent/"controller.lock",os.O_RDONLY)
        m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
    try:
        with pytest.raises((ValueError,BlockingIOError)):m._FailedLaunchHold(tmp_path.resolve(),fixture=True,pin=pin)
    finally:
        if lock is not None:os.close(lock)


def test_source_health_worker_proves_initial_denial_before_any_source_or_input(monkeypatch):
    monkeypatch.setattr(m,"_isolated",lambda:(_ for _ in ()).throw(ValueError("initial denial")))
    monkeypatch.setattr(m,"_current",lambda _:pytest.fail("source before denial"))
    monkeypatch.setattr(m,"_FailedLaunchHold",lambda *a,**k:pytest.fail("health must never read old artifacts"))
    with pytest.raises(ValueError,match="initial denial"):m._launcher_health_worker({})


@pytest.mark.parametrize("fault",("stderr","bool_counter","identity","extra"))
def test_launcher_health_exact_tiny_witness_refuses_before_namespace(monkeypatch,fault):
    identity={"invented_source_identity":True}
    value={"schema":m.SCHEMA+"/launcher-health","execution_identity":identity,"native_network_fork_allwrite_securityexec_denial":True,
        "artifact_reads":0,"provider_requests":0,"credential_reads":0,"qc_accesses":0}
    if fault=="bool_counter":value["artifact_reads"]=False
    elif fault=="identity":value["execution_identity"]={}
    elif fault=="extra":value["unsafe_extra"]="invented-private"
    def child(*a,**k):
        if fault=="stderr":raise ValueError("invented-private stderr never emitted")
        return value
    monkeypatch.setattr(m,"_run_child",child)
    with pytest.raises(m.NativeWorkerRefused) as error:m._launcher_health(identity)
    assert (error.value.phase,error.value.code)==("launcher_health","native_or_control_refused")


def test_exact_fixed_health_command_matches_worker_launch_prefix_and_never_inputs():
    identity={"source_metadata_only":True};normal=m._command(identity,1);health=m._command(identity,1,role="health")
    assert normal[:-1]==health[:-1] and "_launcher_health_worker(identity)" in health[-1]
    assert "_plan_worker(identity," not in health[-1] and "_failed_launch_worker(identity)" not in health[-1]
    with pytest.raises(ValueError,match="fixed_worker_role"):m._command(identity,1,role="arbitrary_source_code")


@pytest.mark.skipif(m.sys.platform!="darwin",reason="faithful macOS nested Seatbelt launch refusal")
def test_genuine_nested_native_launcher_refuses_before_old_or_new_artifacts(monkeypatch):
    # This test already runs inside initial native network/security denial.
    # The exact fixed health command cannot sandbox_apply a second profile.
    monkeypatch.setattr(m,"_identity",lambda _:{"invented_source_metadata":True})
    monkeypatch.setattr(m,"_stopped_launch_lineage",lambda *a:pytest.fail("no old input before healthy launcher"))
    monkeypatch.setattr(m,"Controller",lambda *a,**k:pytest.fail("no new root before healthy launcher"))
    with pytest.raises(m.NativeWorkerRefused) as error:m.prepare_actual_batch("a"*40)
    assert error.value.phase=="launcher_health"


# Claude review section 342 (IBREQ21-CR34202): the required21 capture consumed
# eight accessions this planner does not chain, so planning must stop while
# such a later capture namespace exists, before any planner scope or child.
def test_later_capture_namespace_blocks_planning(tmp_path):
    root=tmp_path.resolve()
    assert m._no_unchained_later_capture(root) is None
    root.joinpath(*m.UNCHAINED_LATER_CAPTURE_PARTS[0]).mkdir(parents=True)
    with pytest.raises(m.CampaignError,match="^campaign_unchained_later_capture_consumption$"):
        m._no_unchained_later_capture(root)


def test_actual_planning_checks_later_captures_before_any_planner_scope(monkeypatch):
    identity={"invented_source_identity":True}
    monkeypatch.setattr(m,"_identity",lambda _:identity)
    monkeypatch.setattr(m,"_launcher_health",lambda value:None)
    monkeypatch.setattr(m,"_stopped_launch_lineage",lambda value:m._launch_lineage())
    monkeypatch.setattr(m,"Controller",lambda *a,**k:pytest.fail("planner scope created"))
    monkeypatch.setattr(m,"_run_child",lambda *a,**k:pytest.fail("planner child launched"))
    with pytest.raises(m.CampaignError,match="^campaign_unchained_later_capture_consumption$"):
        m.prepare_actual_batch("a"*40)


def test_planner_worker_checks_later_captures_before_any_input(monkeypatch):
    monkeypatch.setattr(m,"_isolated",lambda:None)
    monkeypatch.setattr(m,"_current",lambda identity:None)
    monkeypatch.setattr(m,"_FailedLaunchHold",lambda *a:pytest.fail("old input reached"))
    with pytest.raises(m.CampaignError,match="^campaign_unchained_later_capture_consumption$"):
        m._plan_worker({},1)
