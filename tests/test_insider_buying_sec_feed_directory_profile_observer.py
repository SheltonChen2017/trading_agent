"""Invented directory/control metadata only; never opens actual capture paths."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="macOS/POSIX private-contact producer import")
from research import insider_buying_sec_feed_directory_profile_observer as m


def _body():
    return {"directory":{"name":m.producer.DIRECTORY,"item":[{"name":"20210401.nc.tar.gz","type":"file",
        "size":"123456","last-modified":"2021-04-02 01:02:03"}]}}


def _capture(raw=None):
    raw=m._raw(_body()) if raw is None else raw
    sources={m.producer.SELF_PATH:m.PRODUCER_SOURCE_SHA256,m.producer.TEST_PATH:m.PRODUCER_TEST_SHA256,
        **{f"research/invented_{i:03}.py":"a"*64 for i in range(104)}}
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"c"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    forms=m.producer._preflight_controls(identity,False,root=m.LANE_ROOT)
    pairs=(("Content-Length",str(len(raw))),)
    result={"schema":m.producer.SCHEMA+"/result","reservation_sha256":m._sha(forms["reservation"]),
        "claim_sha256":m._sha(forms["claim"]),"start_sha256":m._sha(forms["start"]),"http_status":200,
        "transport_invocations":1,"disposition":"opaque_response_retained_inventory_unqualified","response_retained":True,
        "response_sha256":m._sha(raw),"response_bytes":len(raw),"response_headers_sha256":m._sha(m._raw(pairs)),
        "inventory_sha256":None,"inventory_qualified":False,"archive_requests":0,"accession_requests":0,
        "contact_value_stored_or_hashed":False}
    controls={"scope.lock":m.producer.LOCK_BYTES,"claim.json":forms["claim"],"reservation.json":forms["reservation"],
        "request-start.json":forms["start"],"contact-validated.json":forms["contact"],"response.bin":raw,
        "response-headers.json":m._raw({"headers":pairs}),"request-result.json":m._raw(result)}
    controls["complete.json"]=m._raw(m.producer._complete_control(identity,False,m._sha(forms["reservation"]),result,
        m._sha(controls["request-result.json"]),False))
    return controls,m.CapturePins(m._sha(controls["complete.json"]),m._sha(raw),len(raw),identity["head"],len(sources),identity["source_inventory_sha256"])


def _current_identity():
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64,m.producer.SELF_PATH:m.PRODUCER_SOURCE_SHA256,m.producer.TEST_PATH:m.PRODUCER_TEST_SHA256}
    return {"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"d"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


def _repair_links(controls):
    rsha=m._sha(controls["reservation.json"])
    for name in ("claim.json","contact-validated.json","request-start.json"):
        value=json.loads(controls[name]);value["reservation_sha256"]=rsha
        if name=="request-start.json":value["claim_sha256"]=m._sha(controls["claim.json"])
        controls[name]=m._raw(value)
    result=json.loads(controls["request-result.json"])
    result.update(reservation_sha256=rsha,claim_sha256=m._sha(controls["claim.json"]),start_sha256=m._sha(controls["request-start.json"]))
    controls["request-result.json"]=m._raw(result)
    identity=json.loads(controls["reservation.json"])["execution_identity"]
    controls["complete.json"]=m._raw(m.producer._complete_control(identity,False,rsha,result,m._sha(controls["request-result.json"]),False))


def test_structure_is_observed_without_guessing_missing_parentdir_or_inventory():
    raw=m._raw(_body());result=m.observe_directory_profile(raw)
    assert result["observed_item_count"]==1 and result["root_type"]==result["directory_type"]=="object"
    assert result["directory_known_field_types"]=={"item":"array","name":"string"}
    assert result["safe_directory_paths"]=={"name":m.producer.DIRECTORY,"parent-dir":None}
    assert result["executed_candidate_profile_refusal_code"]=="directory_profile_refused"
    assert result["new_inventory_qualified"] is result["structural_parser_financial_numbers_converted"] is False
    assert result["structural_parser_numeric_values_preserved_as_lexemes"] is True
    row=result["items"][0]
    assert row["source_ordinal"]==1 and row["listed_q2_archive_filename"]=="20210401.nc.tar.gz"
    assert row["size_text"]=="123456" and row["size_value_type"]=="string" and not row["size_unit_qualified"]
    assert result["response_sha256"]==m._sha(raw) and result["response_bytes"]==len(raw)
    assert all(value is False or type(value) is int and value==0 for value in result["authority"].values())


def test_numeric_lexemes_preserve_exact_digits_exponent_and_not_financial_values():
    raw=b'{"directory":{"item":[{"size":9007199254740993},{"size":1.234567890123456e+42},{"size":-0.25}],"profit":123.456}}'
    value=m._foreign(raw)["directory"]["item"]
    assert type(value[0]["size"]) is m._IntegerLexeme and value[0]["size"]=="9007199254740993"
    assert type(value[1]["size"]) is m._DecimalLexeme and value[1]["size"]=="1.234567890123456e+42"
    result=m.observe_directory_profile(raw)
    assert [row["size_text"] for row in result["items"]]==["9007199254740993","1.234567890123456e+42","-0.25"]
    assert b"123.456" not in m._raw(result) and b"profit" not in m._raw(result)


def test_compatible_legacy_replay_really_computes_directory_sizes_and_has_precise_labels(monkeypatch):
    body=_body();body["directory"]["parent-dir"]=m.producer.PARENT_DIRECTORY
    observed=[];original=m.producer.parse_directory_inventory
    def compatible_replay(raw):
        value=original(raw)
        assert type(value["entries"][0]["advertised_size_numeric"]) is int
        assert type(value["total_advertised_size_numeric"]) is int
        observed.append(value["total_advertised_size_numeric"])
        return value
    monkeypatch.setattr(m.producer,"parse_directory_inventory",compatible_replay)
    result=m.observe_directory_profile(m._raw(body))
    assert observed==[123456] and result["executed_candidate_profile_accepted"] is True
    assert "numeric_source_values_interpreted" not in result
    assert result["structural_parser_numeric_values_preserved_as_lexemes"] is True
    assert result["structural_parser_financial_numbers_converted"] is False
    assert result["legacy_candidate_replay_may_convert_and_sum_advertised_size_metadata"] is True


@pytest.mark.parametrize("item", ({"name":"PRIVATE filename.txt","size":"PRIVATE raw string","type":{"PRIVATE":True}},
    {"name":"../20210401.nc.tar.gz","size":[123],"type":["file"]},{"name":"20210701.nc.tar.gz","size":True},None,17))
def test_arbitrary_values_paths_and_nonobjects_never_leak_or_crash(item):
    body=_body();body["directory"]["item"]=[item];result=m.observe_directory_profile(m._raw(body))
    assert result["items"][0]["listed_q2_archive_filename"] is None
    assert result["items"][0]["size_text"] is None
    assert b"PRIVATE" not in m._raw(result)


def test_unknown_key_names_and_untrusted_paths_are_counted_not_emitted():
    body=_body();body["PRIVATE_TOP"]=True;body["directory"].update({"PRIVATE_KEY":"PRIVATE_VALUE","parent-dir":"https://PRIVATE/token"})
    result=m.observe_directory_profile(m._raw(body))
    assert result["top_unknown_field_count"]==result["directory_unknown_field_count"]==1
    assert result["safe_directory_paths"]["parent-dir"] is None
    assert b"PRIVATE" not in m._raw(result)


@pytest.mark.parametrize("raw",(b'{"directory":{},"directory":{}}',b'{"x":NaN}',b'{"x":'+b'['*30+b'0'+b']'*30+b'}',
    b'<html>PRIVATE ERROR</html>',b'{"x":"\xff"}',b'{"x":"'+b'x'*8193+b'"}'),ids=("duplicate","nonfinite","depth","html","encoding","string-bound"))
def test_malformed_or_resource_refusals_are_typed_and_snippet_free(raw):
    result=m.observe_directory_profile(raw)
    assert result["foreign_json_parse_refusal_code"] is not None
    assert result["root_type"]=="unparsed"
    assert result["new_inventory_qualified"] is False and b"PRIVATE" not in m._raw(result)


@pytest.mark.parametrize("raw",(None,b"",b"x"*(512*1024+1)))
def test_response_byte_bounds_fail_before_hash_or_decode(raw):
    with pytest.raises(m.DirectoryProfileError):m.observe_directory_profile(raw)


def test_fixed_source_error_strings_are_not_forwarded(monkeypatch):
    monkeypatch.setattr(m.producer,"parse_directory_inventory",lambda _:(_ for _ in ()).throw(m.producer.FeedDirectoryError("PRIVATE")))
    result=m.observe_directory_profile(m._raw(_body()))
    assert result["executed_candidate_profile_refusal_code"]=="candidate_profile_refused" and b"PRIVATE" not in m._raw(result)


def test_capture_authentication_binds_full_106_source_controls_and_lossless_ipc():
    controls,pins=_capture();identity=m.validate_capture(controls,pins)
    assert len(identity["source_sha256"])==106
    result=m._result(_current_identity(),controls,pins=pins)
    decoded=m.codec._decode_control(m._raw(result),ipc=True)
    assert m._validate(decoded,_current_identity(),pins=pins)==result
    assert m._witness(result)==controls and len(result["retained_control_witness"]["reservation.json"])>16384
    with pytest.raises(m.DirectoryProfileError):m._validate(result,_current_identity())


@pytest.mark.parametrize("fault",("complete_hash","response_hash","response_size","source_count_bool","head","source_inventory"))
def test_external_pin_failures_never_decode_unknown_body(fault,monkeypatch):
    controls,pins=_capture()
    if fault=="complete_hash":pins=replace(pins,complete_sha256="0"*64)
    elif fault=="response_hash":pins=replace(pins,response_sha256="0"*64)
    elif fault=="response_size":pins=replace(pins,response_bytes=pins.response_bytes+1)
    elif fault=="source_count_bool":pins=replace(pins,source_count=True)
    elif fault=="head":pins=replace(pins,execution_head="0"*40)
    else:pins=replace(pins,source_inventory_sha256="0"*64)
    monkeypatch.setattr(m,"_foreign",lambda *a:pytest.fail("pins must precede body observation"))
    with pytest.raises(m.DirectoryProfileError):m._result(_current_identity(),controls,pins=pins)


@pytest.mark.parametrize("fault",("claim_url","start_bool","contact_bool","result_bool","complete_bool","header_length","source_digest","extra_leaf"))
def test_coherently_rehashed_controls_still_require_exact_schema_and_links(fault):
    controls,pins=_capture()
    if fault=="extra_leaf":controls["inventory.json"]=b"{}"
    else:
        name={"claim_url":"claim.json","start_bool":"request-start.json","contact_bool":"contact-validated.json",
            "result_bool":"request-result.json","complete_bool":"complete.json","header_length":"response-headers.json",
            "source_digest":"reservation.json"}[fault]
        value=json.loads(controls[name])
        if fault=="claim_url":value["url"]=m.producer.foreign_json.URL
        elif fault=="start_bool":value["attempt"]=True
        elif fault=="contact_bool":value["contact_present"]=1
        elif fault=="result_bool":value["transport_invocations"]=True
        elif fault=="complete_bool":value["credential_reads"]=False
        elif fault=="header_length":value["headers"][0][1]=str(pins.response_bytes+1)
        else:value["execution_identity"]["source_inventory_sha256"]="0"*64
        controls[name]=m._raw(value)
        if fault not in {"complete_bool","header_length"}:_repair_links(controls)
    pins=replace(pins,complete_sha256=m._sha(controls["complete.json"]))
    with pytest.raises(ValueError):m.validate_capture(controls,pins)


@pytest.mark.parametrize("fault",("count_bool","authority_int","native_int","observation","observed_count_bool","witness","pin","extra"))
def test_result_rederivation_rejects_typed_or_coherent_report_forgeries(fault):
    controls,pins=_capture();identity=_current_identity();result=m._result(identity,controls,pins=pins)
    if fault=="count_bool":result["credential_reads"]=False
    elif fault=="authority_int":result["backtesting_ready"]=0
    elif fault=="native_int":result["native_network_fork_allwrite_securityexec_denial"]=1
    elif fault in {"observation","observed_count_bool"}:
        if fault=="observation":result["profile_observation"]["snippet"]="PRIVATE"
        else:result["profile_observation"]["observed_item_count"]=True
        result["profile_observation_sha256"]=m._sha(m._raw(result["profile_observation"]))
    elif fault=="witness":result["retained_control_witness"]["response.bin"]+="00"
    elif fault=="pin":result["retained_control_pins"]["complete.json"]["bytes"]=False
    else:result["extra"]=None
    with pytest.raises(ValueError):m._validate(result,identity,pins=pins)


def _seed(root):
    controls,pins=_capture();base=root.joinpath(*m.producer.ARTIFACT_PARTS);run=base/"runs"/m.producer.AUDIT_ID;claims=base/"claims"
    run.mkdir(parents=True,mode=0o700);claims.mkdir(mode=0o700)
    for path in (root/"artifacts",root/"artifacts"/"insider_buying",base,base/"runs",run,claims):path.chmod(0o700)
    paths={"scope.lock":base/"scope.lock","claim.json":claims/m.producer._claim_name(),**{name:run/name for name in m.RUN_NAMES}}
    for name,path in paths.items():path.write_bytes(controls[name]);path.chmod(0o600)
    return controls,pins,paths


def test_strict_held_nine_leaf_source_capture_is_unchanged(tmp_path):
    controls,pins,paths=_seed(tmp_path);held=m._HeldProfile(tmp_path,fixture=True)
    try:assert held.controls==controls;held.recheck();m.validate_capture(held.controls,pins)
    finally:held.close()
    assert {name:path.read_bytes() for name,path in paths.items()}==controls


@pytest.mark.parametrize("fault",("extra","missing","mode","hardlink","inode","ctime","bytes"))
def test_held_source_rejects_namespace_and_old_custody_changes(tmp_path,fault):
    controls,pins,paths=_seed(tmp_path);path=paths["response.bin"]
    if fault in {"extra","missing","mode","hardlink"}:
        if fault=="extra":other=path.parent/"inventory.json";other.write_bytes(b"{}");other.chmod(0o600)
        elif fault=="missing":path.unlink()
        elif fault=="mode":path.chmod(0o644)
        else:os.link(path,tmp_path/"extra-link")
        with pytest.raises(ValueError):m._HeldProfile(tmp_path,fixture=True)
        return
    held=m._HeldProfile(tmp_path,fixture=True)
    try:
        info=path.stat();raw=path.read_bytes()
        if fault=="ctime":path.chmod(0o640);path.chmod(0o600)
        elif fault=="inode":
            other=tmp_path/"substitute";other.write_bytes(raw);other.chmod(0o600)
            os.utime(other,ns=(info.st_atime_ns,info.st_mtime_ns));other.replace(path)
        else:path.write_bytes(raw.replace(b"123456",b"123457"));os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()


def test_fixture_boundary_and_native_flags_precede_actual_input_reader(monkeypatch):
    monkeypatch.setattr(m.base.custody,"_Inputs",lambda *a:pytest.fail("no actual namespace reader"))
    with pytest.raises(ValueError):m._HeldProfile(m.LANE_ROOT,fixture=True)
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,no_user_site=1,dont_write_bytecode=1),pycache_prefix=m.EMPTY_CACHE_PREFIX))
    with pytest.raises(m.DirectoryProfileError,match="isolated"):m._HeldProfile()


def test_worker_current_source_refusal_precedes_input_reader(monkeypatch):
    monkeypatch.setattr(m,"_isolated",lambda:None);monkeypatch.setattr(m.base,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m,"_current",lambda _:(_ for _ in ()).throw(m.DirectoryProfileError("invented_source_change")))
    monkeypatch.setattr(m,"_HeldProfile",lambda *a,**k:pytest.fail("no actual capture reader"))
    with pytest.raises(m.DirectoryProfileError,match="invented_source_change"):m._worker(_current_identity())


def test_fixed_native_command_and_original_source_git_guard_are_read_only():
    identity=_current_identity();command=m._command(identity);guard=m._Guard(identity["head"],command)
    assert all(flag in command for flag in ("-I","-S","-B","pycache_prefix="+m.EMPTY_CACHE_PREFIX))
    assert all(part in command[5] for part in ("(deny network*)","(deny process-fork)","(deny file-write*)","/usr/bin/security"))
    for target in (m.PRODUCER_HEAD+":"+m.producer.SELF_PATH,):
        assert guard._git("/usr/bin/git",("/usr/bin/git","show",target),m.LANE_ROOT,{"PATH":"/usr/bin:/bin"})
    for target in (m.codec.FAILED_HEAD+":"+m.producer.SELF_PATH,m.PRODUCER_HEAD+":../outside.py",m.PRODUCER_HEAD+":secret.txt"):
        assert not guard._git("/usr/bin/git",("/usr/bin/git","show",target),m.LANE_ROOT,{"PATH":"/usr/bin:/bin"})


def test_parent_failure_does_not_launch_or_read_capture(monkeypatch):
    monkeypatch.setattr(m,"_committed_identity",lambda _:(_ for _ in ()).throw(m.DirectoryProfileError("invented_uncommitted")))
    monkeypatch.setattr(m.base.launcher,"run_child",lambda *a,**k:pytest.fail("no child before source preflight"))
    with pytest.raises(m.DirectoryProfileError):m.run_actual_observation("d"*40)


@pytest.mark.parametrize("fault",("none","producer_git_mismatch","producer_drift"))
def test_committed_front_binds_producer_test_absent_from_real_shaped_loaded_roster(monkeypatch,fault):
    names=(m.SELF_PATH,m.TEST_PATH,m.producer.SELF_PATH,m.producer.TEST_PATH)
    raw={name:(m.LANE_ROOT/name).read_bytes() for name in names}  # Public source images only, never artifacts.
    hashes={name:m._sha(value) for name,value in raw.items()}
    # Static/loaded Python closure includes the producer module, not its test.
    loaded={name:hashes[name] for name in (m.SELF_PATH,m.producer.SELF_PATH)}
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"e"*40,"clean":True,
        "source_sha256":loaded,"source_inventory_sha256":m._sha(m._raw(loaded))}
    reads=[];git_reads=[]
    monkeypatch.setattr(m.base.custody,"_identity",lambda head:copy.deepcopy(identity))
    def source_bytes(root,requested):
        assert root==m.LANE_ROOT;requested=tuple(requested);reads.append(requested)
        if requested==tuple(m.base.FROZEN):return m.base.FROZEN
        fixed={**m.producer.REUSED_HELPER_SHA256,m.producer.SELF_PATH:m.PRODUCER_SOURCE_SHA256,
            m.producer.TEST_PATH:m.PRODUCER_TEST_SHA256}
        if requested==tuple(fixed):return fixed
        assert set(requested)<=set(hashes)
        value={name:hashes[name] for name in requested}
        if fault=="producer_drift" and len(reads)>1:value[m.producer.TEST_PATH]="0"*64
        return value
    def git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show";head,_,name=args[1].partition(":")
        assert head==identity["head"] and name in raw;git_reads.append(name)
        return raw[name]+b"# invented mismatch" if fault=="producer_git_mismatch" and name==m.producer.TEST_PATH else raw[name]
    monkeypatch.setattr(m.base.custody,"_source_bytes",source_bytes)
    monkeypatch.setattr(m.base.custody,"_git",git)
    if fault!="none":
        with pytest.raises(m.DirectoryProfileError,match="profile_uncommitted_source" if fault=="producer_git_mismatch" else "profile_current_or_frozen_source_changed"):
            m._committed_identity(identity["head"])
        return
    result=m._committed_identity(identity["head"])
    assert set(names)<=set(result["source_sha256"])
    assert {m.producer.SELF_PATH,m.producer.TEST_PATH}<=set(git_reads)
    assert any({m.producer.SELF_PATH,m.producer.TEST_PATH}<=set(row) for row in reads[1:])


def test_corrected_observation_is_fresh_v2_and_preserves_exact_preceding_failure():
    assert m.SCHEMA=="insider-sec-feed-directory-profile-observer-v2"
    assert m.AUDIT_ID=="ib-sec-feed-directory-2021q2-profile-observation-v2-20261025-once"
    assert m.REGISTRATION["preceding_observer_execution_head"]=="20e5dbfc7c3b640b9f3054273767a330ea61883f"
    assert m.REGISTRATION["preceding_observer_source_sha256"]=="807512fc7f9f13883acb26238b62e45a9ff9ec25e3afde8fb9f07e1958cb15c8"
    assert m.REGISTRATION["preceding_observer_failure_rewritten"] is False
    assert m.ACTUAL_PINS.execution_head=="6011ae9d561fb7308249c55677055e4fa62c1150"
    assert m.REGISTRATION["new_provider_requests"]==0 and m.REGISTRATION["original_namespace_mutated"] is False


def test_cli_refusal_is_fixed_and_secret_free(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual_observation",lambda _:(_ for _ in ()).throw(ValueError("PRIVATE")))
    assert m.main(["--expected-head","d"*40])==2
    assert capsys.readouterr().out=='{"disposition":"directory_profile_observation_refused"}\n'
