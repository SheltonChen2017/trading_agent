"""Invented public-directory metadata; no actual retained namespace is opened."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, timedelta
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="private-contact helper import")
from research import insider_buying_sec_feed_retained_inventory as m


def _body():
    rows=[]
    for index in range(64):
        name=(date(2021,4,1)+timedelta(days=index)).strftime("%Y%m%d")+".nc.tar.gz"
        rows.append({"href":name,"last-modified":"PRIVATE opaque modified display","name":name,
            "size":"291592 KB","type":"file"})
    return {"directory":{"name":"PRIVATE opaque directory display","parent-dir":"PRIVATE opaque parent display","item":rows}}


def _identity():
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64,
        m.observer.SELF_PATH:m.OBSERVER_SOURCE_SHA256,m.observer.TEST_PATH:m.OBSERVER_TEST_SHA256,
        m.producer.SELF_PATH:m.observer.PRODUCER_SOURCE_SHA256,m.producer.TEST_PATH:m.observer.PRODUCER_TEST_SHA256,
        **{f"research/current_fixture_{i:03}.py":"c"*64 for i in range(104)}}
    return {"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"d"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


def _capture(raw=None):
    raw=m._raw(_body()) if raw is None else raw
    sources={m.producer.SELF_PATH:m.observer.PRODUCER_SOURCE_SHA256,m.producer.TEST_PATH:m.observer.PRODUCER_TEST_SHA256,
        **{f"research/invented_{i:03}.py":m._sha(("invented-source-"+str(i)).encode()) for i in range(104)}}
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
    return controls,m.observer.CapturePins(m._sha(controls["complete.json"]),m._sha(raw),len(raw),identity["head"],
        len(sources),identity["source_inventory_sha256"])


def test_complete_all64_metadata_is_qualified_without_display_identity_or_byte_claim():
    raw=m._raw(_body());result=m.qualify_retained_directory(raw);inventory=result["inventory"]
    assert result["status"]=="qualified" and result["refusal_code"] is None
    assert inventory["complete_advertisement_count"]==len(inventory["entries"])==64
    assert [row["source_ordinal"] for row in inventory["entries"]]==list(range(1,65))
    assert inventory["directory_display_classes"]=={"name":"opaque-string-display","parent-dir":"opaque-string-display"}
    assert result["href_shape_counts"]=={"other-relative-or-opaque":64}
    assert inventory["entries"][0]["qualified_archive_url"]==m.LOOKUP_DIRECTORY_URL+"20210401.nc.tar.gz"
    assert inventory["entries"][0]["advertised_magnitude_text"]=="291592"
    assert inventory["ordered_entries_sha256"]==m._sha(m._raw(inventory["entries"]))
    assert inventory["response_sha256"]==m._sha(raw) and inventory["response_bytes"]==len(raw)
    assert b"PRIVATE" not in m._raw(result)
    assert inventory["advertised_KB_is_not_actual_payload_bytes"] is True
    for flag in ("advertised_KB_base_qualified","advertised_rounding_qualified","filing_population_coverage_established"):
        assert inventory[flag] is False
    assert result["old_executed_profile_promoted"] is False
    assert all(value is False or type(value) is int and value==0 for value in result["authority"].values())


@pytest.mark.parametrize("prefix,form",(("","relative-filename"),("./","dot-relative-filename"),
    (m.producer.DIRECTORY+"/","absolute-path"),(m.LOOKUP_DIRECTORY_URL,"absolute-https-www-sec")))
def test_only_explicit_same_directory_href_forms_are_accepted(prefix,form):
    body=_body()
    for row in body["directory"]["item"]:row["href"]=prefix+row["name"]
    result=m.qualify_retained_directory(m._raw(body))
    assert result["status"]=="qualified" and {row["href_form"] for row in result["inventory"]["entries"]}=={form}


@pytest.mark.parametrize("href",("https://evil.example/20210401.nc.tar.gz","http://www.sec.gov/Archives/edgar/Feed/2021/QTR2/20210401.nc.tar.gz",
    "//www.sec.gov/Archives/edgar/Feed/2021/QTR2/20210401.nc.tar.gz","/Archives/edgar/Feed/2021/QTR1/20210401.nc.tar.gz",
    "../QTR2/20210401.nc.tar.gz","./../20210401.nc.tar.gz","20210402.nc.tar.gz","20210401.nc.tar.gz?x=PRIVATE",
    "20210401.nc.tar.gz#PRIVATE","%32%30%32%31%30%34%30%31.nc.tar.gz","https://PRIVATE@www.sec.gov/20210401.nc.tar.gz",
    "20210401.nc.tar.gz\\PRIVATE"," PRIVATE",""))
def test_href_qualification_never_falls_back_to_valid_filename(href):
    body=_body();body["directory"]["item"][0]["href"]=href
    result=m.qualify_retained_directory(m._raw(body))
    assert result["status"]=="refused" and result["inventory"] is None
    assert result["refusal_code"] in {"listed_href_lexical_refused","listed_href_not_same_trusted_q2_item"}
    assert b"PRIVATE" not in m._raw(result)


@pytest.mark.parametrize("size",("0 KB","0.000000 KB","01 KB","-1 KB","1e3 KB","1 MB","1KB","1 KB ","1.1234567 KB",1,True,None))
def test_size_is_positive_bounded_decimal_KB_text_not_numeric_or_inferred_unit(size):
    body=_body();body["directory"]["item"][0]["size"]=size
    assert m.qualify_retained_directory(m._raw(body))["status"]=="refused"


@pytest.mark.parametrize("size",("0.000001 KB","1 KB","123456789012345678.123456 KB"))
def test_KB_magnitude_is_preserved_lexically_without_arithmetic(size):
    body=_body();body["directory"]["item"][0]["size"]=size
    row=m.qualify_retained_directory(m._raw(body))["inventory"]["entries"][0]
    assert row["advertised_size_text"]==size and row["advertised_magnitude_text"]==size[:-3]
    assert row["advertised_unit_base_qualified"] is row["actual_archive_bytes_known"] is False


@pytest.mark.parametrize("fault",("count63","count65","duplicate","invalid_date","outside_quarter","extra_top","extra_directory",
    "extra_item","missing_href","bool_type","opaque_type","modified_bound"))
def test_every_row_and_exact_envelope_are_required_not_just_minimal_candidate(fault):
    body=_body();rows=body["directory"]["item"]
    if fault=="count63":rows.pop()
    elif fault=="count65":rows.append(copy.deepcopy(rows[-1]))
    elif fault=="duplicate":rows[-1]=copy.deepcopy(rows[0])
    elif fault in {"invalid_date","outside_quarter"}:
        rows[-1]["name"]=rows[-1]["href"]="20210431.nc.tar.gz" if fault=="invalid_date" else "20210701.nc.tar.gz"
    elif fault=="extra_top":body["PRIVATE"]=None
    elif fault=="extra_directory":body["directory"]["PRIVATE"]=None
    elif fault=="extra_item":rows[-1]["PRIVATE"]=None
    elif fault=="missing_href":del rows[-1]["href"]
    elif fault=="bool_type":rows[-1]["type"]=True
    elif fault=="opaque_type":rows[-1]["type"]="PRIVATE"
    else:rows[-1]["last-modified"]="PRIVATE"*100
    result=m.qualify_retained_directory(m._raw(body))
    assert result["status"]=="refused" and result["inventory"] is None
    assert b"PRIVATE" not in m._raw(result)


def test_order_and_exact_parsed_row_metadata_have_distinct_bound_hashes():
    body=_body();original=m.qualify_retained_directory(m._raw(body))["inventory"]
    body["directory"]["item"][0]["last-modified"]="changed opaque metadata"
    changed=m.qualify_retained_directory(m._raw(body))["inventory"]
    assert original["entries"][0]["source_item_canonical_sha256"]!=changed["entries"][0]["source_item_canonical_sha256"]
    body["directory"]["item"].reverse();reverse=m.qualify_retained_directory(m._raw(body))["inventory"]
    assert changed["ordered_entries_sha256"]!=reverse["ordered_entries_sha256"]
    assert reverse["entries"][0]["source_ordinal"]==1 and reverse["entries"][0]["listed_name"]==body["directory"]["item"][0]["name"]


@pytest.mark.parametrize("raw",(b'{"directory":{},"directory":{}}',b'{"x":NaN}',b'<html>PRIVATE</html>',b'{"x":"\xff"}'))
def test_unqualified_foreign_formats_are_safe_typed_observations_not_leaked_text(raw):
    result=m.qualify_retained_directory(raw)
    assert result["status"]=="refused" and result["refusal_code"]=="retained_foreign_json_profile_refused"
    assert result["safe_shape"]["root_type"]=="unparsed" and b"PRIVATE" not in m._raw(result)


@pytest.mark.parametrize("raw",(None,b"",b"x"*(512*1024+1)))
def test_invalid_body_bounds_refuse_before_observation(raw,monkeypatch):
    monkeypatch.setattr(m.observer,"observe_directory_profile",lambda _:pytest.fail("no decode before bound"))
    with pytest.raises(m.RetainedInventoryError,match="byte_bound"):m.qualify_retained_directory(raw)


def test_pinned_106_source_capture_and_lossless_trusted_witness_are_rederived():
    controls,pins=_capture();identity=_identity();result=m._result(identity,controls,pins=pins)
    assert m._validate(m.codec._decode_control(m._raw(result),ipc=True),identity,pins=pins)==result
    assert result["directory_qualification"]["status"]=="qualified"
    assert m.observer._witness(result)==controls and len(result["retained_control_pins"])==9
    with pytest.raises(ValueError):m._validate(result,identity)


def test_result_registration_is_independent_of_module_canonical_registration():
    controls,pins=_capture();before=copy.deepcopy(m.REGISTRATION)
    result=m._result(_identity(),controls,pins=pins)
    try:
        result["registration"]["archive_requests"]=1
        assert m.REGISTRATION==before
    finally:
        m.REGISTRATION.clear();m.REGISTRATION.update(before)


@pytest.mark.parametrize("fault",("complete","response","size","source_count_bool","head","source_inventory"))
def test_old_external_control_pins_precede_any_new_body_qualification(fault,monkeypatch):
    controls,pins=_capture()
    changes={"complete":{"complete_sha256":"0"*64},"response":{"response_sha256":"0"*64},
        "size":{"response_bytes":pins.response_bytes+1},"source_count_bool":{"source_count":True},
        "head":{"execution_head":"0"*40},"source_inventory":{"source_inventory_sha256":"0"*64}}
    monkeypatch.setattr(m,"qualify_retained_directory",lambda _:pytest.fail("no qualification before pins"))
    with pytest.raises(ValueError):m._result(_identity(),controls,pins=replace(pins,**changes[fault]))


@pytest.mark.parametrize("fault",("zero_bool","false_int","native_int","qualification","qualified_count_bool","witness","pin","extra"))
def test_exact_canonical_result_rederivation_rejects_coherent_typed_forgeries(fault):
    controls,pins=_capture();identity=_identity();result=m._result(identity,controls,pins=pins)
    if fault=="zero_bool":result["credential_reads"]=False
    elif fault=="false_int":result["backtesting_ready"]=0
    elif fault=="native_int":result["native_network_fork_allwrite_securityexec_denial"]=1
    elif fault in {"qualification","qualified_count_bool"}:
        if fault=="qualification":result["directory_qualification"]["inventory"]["entries"][0]["qualified_archive_url"]="https://evil.example/"
        else:result["directory_qualification"]["inventory"]["complete_advertisement_count"]=True
        result["directory_qualification_sha256"]=m._sha(m._raw(result["directory_qualification"]))
    elif fault=="witness":result["retained_control_witness"]["response.bin"]+="00"
    elif fault=="pin":result["retained_control_pins"]["complete.json"]["bytes"]=False
    else:result["extra"]=None
    with pytest.raises(ValueError):m._validate(result,identity,pins=pins)


@pytest.mark.parametrize("fault",("none","missing_test","git_mismatch","later_drift"))
def test_genuine_current_front_adds_all_three_test_images_to_real_shaped_loaded_roster(monkeypatch,fault):
    names=(m.SELF_PATH,m.TEST_PATH,m.observer.SELF_PATH,m.observer.TEST_PATH,m.producer.SELF_PATH,m.producer.TEST_PATH)
    raw={name:(m.LANE_ROOT/name).read_bytes() for name in names}  # Public code only.
    hashes={name:m._sha(value) for name,value in raw.items()}
    loaded={name:hashes[name] for name in (m.SELF_PATH,m.observer.SELF_PATH,m.producer.SELF_PATH)}
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"e"*40,"clean":True,
        "source_sha256":loaded,"source_inventory_sha256":m._sha(m._raw(loaded))}
    reads=[];git_reads=[]
    monkeypatch.setattr(m.base.custody,"_identity",lambda head:copy.deepcopy(identity))
    def source_bytes(root,requested):
        assert root==m.LANE_ROOT;requested=tuple(requested);reads.append(requested)
        if requested==tuple(m.base.FROZEN):return m.base.FROZEN
        old={**m.producer.REUSED_HELPER_SHA256,m.producer.SELF_PATH:m.observer.PRODUCER_SOURCE_SHA256,
            m.producer.TEST_PATH:m.observer.PRODUCER_TEST_SHA256}
        if requested==tuple(old):return old
        assert set(requested)<=set(hashes)
        answer={name:hashes[name] for name in requested}
        if fault=="missing_test":answer.pop(m.producer.TEST_PATH,None)
        if fault=="later_drift" and len(reads)>1 and m.observer.TEST_PATH in answer:answer[m.observer.TEST_PATH]="0"*64
        return answer
    def git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show";head,_,name=args[1].partition(":")
        assert head==identity["head"] and name in raw;git_reads.append(name)
        return raw[name]+b"# mismatch" if fault=="git_mismatch" and name==m.producer.TEST_PATH else raw[name]
    monkeypatch.setattr(m.base.custody,"_source_bytes",source_bytes);monkeypatch.setattr(m.base.custody,"_git",git)
    if fault!="none":
        with pytest.raises(ValueError):m._committed_identity(identity["head"])
        return
    result=m._committed_identity(identity["head"])
    assert set(names)<=set(result["source_sha256"]) and set(git_reads)==set(names)
    assert any(set(names)<=set(read) for read in reads[1:])


def test_worker_initial_native_and_source_guards_precede_old_input_hold(monkeypatch):
    monkeypatch.setattr(m,"_HeldInputs",lambda:pytest.fail("no retained input before guards"))
    monkeypatch.setattr(m.observer,"_isolated",lambda:(_ for _ in ()).throw(ValueError("isolated")))
    with pytest.raises(ValueError,match="isolated"):m._worker(_identity())
    monkeypatch.setattr(m.observer,"_isolated",lambda:None)
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:(_ for _ in ()).throw(ValueError("native")))
    with pytest.raises(ValueError,match="native"):m._worker(_identity())
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m,"_current",lambda _:(_ for _ in ()).throw(ValueError("source")))
    with pytest.raises(ValueError,match="source"):m._worker(_identity())


def test_fixed_command_uses_old_generic_hold_prefix_without_mutating_old_audit():
    command=m._command(_identity())
    assert m.EMPTY_CACHE_PREFIX==m.observer.EMPTY_CACHE_PREFIX
    assert all(flag in command for flag in ("-I","-S","-B","pycache_prefix="+m.EMPTY_CACHE_PREFIX))
    assert all(part in command[5] for part in ("(deny network*)","(deny process-fork)","(deny file-write*)","/usr/bin/security"))
    assert m.AUDIT_ID!=m.observer.AUDIT_ID and m.AUDIT_ID!=m.producer.AUDIT_ID
    assert m.REGISTRATION["archive_requests"]==m.REGISTRATION["new_provider_requests"]==0
    assert m.REGISTRATION["old_executed_profile_promoted"] is False


def test_parent_source_refusal_cannot_launch_input_worker(monkeypatch):
    monkeypatch.setattr(m,"_committed_identity",lambda _:(_ for _ in ()).throw(ValueError("uncommitted")))
    monkeypatch.setattr(m.base.launcher,"run_child",lambda *a,**k:pytest.fail("no launch before source preflight"))
    with pytest.raises(ValueError):m.run_actual_inventory("a"*40)


@pytest.mark.parametrize("git_mismatch",(False,True))
def test_parent_independent_replay_strips_lossless_witness_and_checks_old_git(monkeypatch,git_mismatch):
    controls,pins=_capture();identity=_identity();result=m._result(identity,controls,pins=pins)
    result_raw=m._raw(result)+b"\n";old_identity=json.loads(controls["reservation.json"])["execution_identity"]
    monkeypatch.setattr(m,"_committed_identity",lambda _:identity);monkeypatch.setattr(m.sys,"addaudithook",lambda _:None)
    monkeypatch.setattr(m.base.launcher,"run_child",lambda *a,**k:SimpleNamespace(returncode=0,stderr=b"",stdout=result_raw))
    real_validate=m._validate;real_capture=m.observer.validate_capture
    monkeypatch.setattr(m,"_validate",lambda result,identity:real_validate(result,identity,pins=pins))
    monkeypatch.setattr(m.observer,"validate_capture",lambda controls,pins=pins:real_capture(controls,pins))
    observed=[]
    def git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show"
        head,_,name=args[1].partition(":");assert head==m.observer.PRODUCER_HEAD;observed.append(name)
        if git_mismatch:return b"invented wrong source"
        if name in {m.producer.SELF_PATH,m.producer.TEST_PATH}:return (m.LANE_ROOT/name).read_bytes()  # Public code only.
        return ("invented-source-"+str(int(name.removeprefix("research/invented_").removesuffix(".py")))).encode()
    monkeypatch.setattr(m.base.custody,"_git",git)
    if git_mismatch:
        with pytest.raises(ValueError,match="producer_git_mismatch"):m.run_actual_inventory(identity["head"])
        return
    public=m.run_actual_inventory(identity["head"])
    assert set(observed)==set(old_identity["source_sha256"])
    assert "retained_control_witness" not in public and public["raw_directory_control_witness_validated_and_omitted"] is True
    assert public["directory_qualification"]["status"]=="qualified"
    assert public["observed_worker_stdout_sha256"]==m._sha(result_raw)


@pytest.mark.parametrize("status,exitcode",(("qualified",0),("refused",2)))
def test_cli_status_and_fixed_error_do_not_claim_new_acquisition(status,exitcode,monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual_inventory",lambda _:{"directory_qualification":{"status":status}})
    assert m.main(["--expected-head","d"*40])==exitcode
    assert status in capsys.readouterr().out
    monkeypatch.setattr(m,"run_actual_inventory",lambda _:(_ for _ in ()).throw(ValueError("PRIVATE")))
    assert m.main(["--expected-head","d"*40])==2
    assert capsys.readouterr().out=='{"disposition":"retained_inventory_observation_refused"}\n'


def test_cli_unknown_argv_never_echoes_accidentally_supplied_secret(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual_inventory",lambda _:pytest.fail("no operation for unsupported argv"))
    assert m.main(["--expected-head","d"*40,"--api-token","PRIVATE-INVENTED-SECRET"])==2
    output=capsys.readouterr()
    assert output.out=='{"disposition":"retained_inventory_observation_refused"}\n' and output.err==""
