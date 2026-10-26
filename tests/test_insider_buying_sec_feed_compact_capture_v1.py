"""Invented source/HTTP/CAS controls only; initial native network denial."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody stack")
pytest.importorskip("termios", reason="private stdin custody")
from research import insider_buying_sec_feed_compact_capture_v1 as m

CONTACT="invented@unit.test"
A="0000000001-20-000001"
B="0000000002-20-000002"
C="0000000003-20-000003"


def _row(accession=A,*,ordinal=1,form="4",period="2020Q4",filed="2020-12-03",issuer="0000000001"):
    row={"period":period,"source_record_ordinal":ordinal,"accession_number":accession,"form_type":form,
        "raw_filing_date":filed,"filing_date":filed,"raw_issuer_cik":issuer,"issuer_comparison_key":issuer.zfill(10),
        "short_cik":len(issuer)<10,"accession_year_mismatch":int(accession[11:13])!=int(filed[:4])%100,
        "raw_symbol_label":"INVENTED","accession_key_sha256":m._sha(accession.encode()),
        "quarterly_zip_sha256":"1"*64,"submission_member_sha256":"2"*64,
        "submission_header_line_sha256":"3"*64,"schema_profile_sha256":"4"*64}
    row["filing_metadata_sha256"]=m._sha(m._raw(row))
    return row


def _inputs(*,rows=None,prior=(),eligible=None):
    rows={A:_row()} if rows is None else rows
    eligible=frozenset(a for a,r in rows.items() if r["form_type"] in {"4","4/A"}) if eligible is None else frozenset(eligible)
    source={"roster":sorted(rows),"eligible":sorted(eligible),"prior":sorted(prior)}
    return SimpleNamespace(rows=rows,roster_set=frozenset(rows),eligible=eligible,prior=tuple(sorted(prior)),
        metadata={"source_receipt_sha256":m._sha(m._raw(source)),"invented_scope":source})


def _member(body=b"opaque NC candidate",*,name=None,kind=b"0"):
    name=(A+".nc").encode() if name is None else name
    header=bytearray(512);header[:len(name)]=name
    for at,width,value in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
        (124,12,format(len(body),"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        header[at:at+width]=value
    header[148:156]=b"        ";header[156:157]=kind;header[257:265]=b"ustar\0"+b"00"
    header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    return bytes(header)+body+bytes((-len(body))%512)


def _response(*,members=None,raw=None,headers=None,status=200):
    raw=gzip.compress(b"".join(members or [_member()])+bytes(1024),mtime=0) if raw is None else raw
    return m.directory.SecHttpResult(status,(("Content-Length",str(len(raw))),) if headers is None else headers,raw)


def _run(root,*,response=None,calls=None,hook=None,inputs=None,**kwargs):
    inputs=_inputs() if inputs is None else inputs
    def transport(url,headers,cap):
        assert url==m.URL and cap==m.MAX_COMPRESSED and CONTACT in headers["User-Agent"]
        if calls is not None:calls.append(1)
        if hook:hook()
        return _response() if response is None else response
    return m._invented(root=root,inputs=inputs,transport=transport,**kwargs)


def _base(root):return root.joinpath(*m.ARTIFACT_PARTS)
def _runpath(root):return _base(root)/"runs"/m.AUDIT_ID
def _read(path):return json.loads(path.read_bytes())


def test_registration_is_distinct_unused_day_and_bounded_compact_scope():
    value=m.registration()
    assert (value["source_ordinal"],value["listed_name"],value["advertised_size_text"])==(43,"20201203.nc.tar.gz","493450 KB")
    assert m.URL not in {m.previous.URL,m.old.URL,m.old.v1.URL}
    assert value["maximum_GETs"]==1 and value["transport_absolute_seconds"]==1200 and value["transport_idle_seconds"]==15
    assert value["native_worker_wall_seconds"]==3600 and value["maximum_compressed_bytes"]==512*1024**2
    assert value["maximum_selected_physical_bytes"]==24*1024**2 and value["maximum_nonhex_IPC_metadata_bytes"]==8*1024**2
    assert value["whole_carrier_hash_retention_or_privacy_claim"] is False
    assert value["advertised_KB_base_or_rounding_qualified"] is False
    assert value["all_25_six_form_source_quarters_rederived"] is True
    assert value["selected_forms"]==["4","4/A"]
    value["authority"]["backtesting_ready"]=True
    assert m.registration()["authority"]["backtesting_ready"] is False


def test_whole_physical_candidate_is_retained_in_CAS_not_carrier_or_path_extraction(tmp_path):
    calls=[]
    def hook():
        assert (_runpath(tmp_path)/"reservation.json").is_file()
        assert (_runpath(tmp_path)/"request-start.json").is_file()
        assert (_base(tmp_path)/"claims"/m._claim_name()).is_file()
    result=_run(tmp_path,calls=calls,hook=hook)
    assert calls==[1] and result["result"]["compact_retained"] is True
    assert result["result"]["selected_objects"]==1 and result["result"]["selected_physical_bytes"]==1024
    manifest=_read(_runpath(tmp_path)/"inspection.json")
    descriptor=manifest["compact"]["candidates"][0]
    obj=_base(tmp_path)/"objects"/(descriptor["physical_sha256"]+".bin")
    assert obj.read_bytes()==_member() and hashlib.sha256(obj.read_bytes()).hexdigest()==descriptor["physical_sha256"]
    assert manifest["selected"][0]["source_binding"]==m._source_binding(_row())
    assert "binary_objects" not in manifest and "raw_symbol_label" not in json.dumps(manifest)
    assert not any(path.suffix==".gz" or path.name==A+".nc" for path in _base(tmp_path).rglob("*"))
    verified=m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)
    assert verified["retained_subset_replay"]["retained_objects_verified"]==1
    assert verified["discarded_carrier_replayed"] is False and verified["original_contact_screen_replayed"] is False
    assert verified["result"]==result["result"]
    for path in _base(tmp_path).rglob("*"):
        if path.is_file():assert CONTACT.encode() not in path.read_bytes()


def test_discarded_unroutable_private_bytes_are_not_privacy_or_hash_scope(tmp_path,monkeypatch):
    response=_response(members=[_member(),_member(CONTACT.encode(),name=b"other.dat")])
    real=m._sha
    def no_carrier_hash(raw):
        assert raw!=response.body
        return real(raw)
    monkeypatch.setattr(m,"_sha",no_carrier_hash)
    result=_run(tmp_path,response=response)
    form=_read(_runpath(tmp_path)/"inspection.json")["compact"]
    assert result["result"]["selected_objects"]==1
    assert form["disposition_counts"]["unroutable_name"]==1 and form["whole_carrier_privacy_screened"] is False


@pytest.mark.parametrize("case",("consumed","other_form","duplicate","unsafe_duplicate","private_selected","ineligible_repeat"))
def test_unadmitted_dispositions_conserve_all_members_without_prefix_promotion(tmp_path,case):
    inputs=_inputs();members=[_member()]
    if case=="consumed":inputs=_inputs(prior=[A])
    elif case=="other_form":inputs=_inputs(rows={A:_row(form="3")})
    elif case=="duplicate":members.append(_member())
    elif case=="unsafe_duplicate":members.append(_member(name=("../"+A+".nc").encode()))
    elif case=="private_selected":members=[_member(CONTACT.encode())]
    else:inputs=_inputs(eligible=[])
    result=_run(tmp_path,inputs=inputs,response=_response(members=members))
    assert result["result"]["compact_retained"] is True and result["result"]["selected_objects"]==0
    form=_read(_runpath(tmp_path)/"inspection.json")["compact"]
    assert sum(form["disposition_counts"].values())==len(members)
    if case in {"other_form","ineligible_repeat"}:
        assert form["disposition_counts"]=={"known_roster_route_not_eligible":1}
    assert list((_base(tmp_path)/"objects").iterdir())==[]
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


@pytest.mark.parametrize("fault",("late_crc","late_tail","header_contact","header_unicode","header_percent","length","opaque","unsupported_pax"))
def test_integrity_privacy_and_unsupported_profile_refusals_keep_no_raw_or_measurement(tmp_path,fault):
    response=_response();raw=response.body;headers=response.headers
    if fault=="late_crc":raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
    elif fault=="late_tail":raw+=b"unaccounted"
    elif fault=="header_contact":headers=(*headers,("X-Diagnostic",CONTACT))
    elif fault=="header_unicode":headers=(*headers,("X-Diagnostic","".join("\\u%04x"%ord(c) for c in CONTACT)))
    elif fault=="header_percent":headers=(*headers,("X-Diagnostic","invented%40unit.test"))
    elif fault=="length":headers=(("Content-Length",str(len(raw)+1)),)
    elif fault=="opaque":raw=gzip.compress(b"not a TAR",mtime=0)
    else:raw=_response(members=[_member(kind=b"x")]).body
    if fault in {"late_crc","late_tail","opaque","unsupported_pax"}:headers=(("Content-Length",str(len(raw))),)
    result=_run(tmp_path,response=_response(raw=raw,headers=headers))
    assert result["result"]["compact_retained"] is False
    assert result["result"]["inspection_refusal"]=={"phase":"inspection","code":"finite_compact_inspection_refused"}
    assert all(result["result"][k] is None for k in ("headers_sha256","inspection_sha256","selected_objects","selected_physical_bytes"))
    assert list((_base(tmp_path)/"objects").iterdir())==[]
    assert not (_runpath(tmp_path)/"inspection.json").exists() and not (_runpath(tmp_path)/"response-headers.json").exists()
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


@pytest.mark.parametrize("status",(301,403,429,500))
def test_non200_and_transport_refusals_are_permanently_consumed(tmp_path,status):
    calls=[];first=_run(tmp_path,response=_response(raw=CONTACT.encode(),status=status),calls=calls)
    assert first["result"]["disposition"]=="non200_body_unread_no_retry" and calls==[1]
    assert list((_base(tmp_path)/"objects").iterdir())==[]
    with pytest.raises(m.CompactCaptureError,match="fresh_namespace_already_exists"):_run(tmp_path,calls=calls)
    assert calls==[1]


@pytest.mark.parametrize("failure",(TimeoutError,RuntimeError))
def test_ambiguous_transport_has_no_retry_or_exception_disclosure(tmp_path,failure):
    calls=[]
    def broken(*args):calls.append(1);raise failure(CONTACT)
    result=m._invented(root=tmp_path,inputs=_inputs(),transport=broken)
    assert calls==[1] and result["result"]["disposition"]=="ambiguous_transport_failure_no_retry"
    assert CONTACT not in json.dumps(result)
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


@pytest.mark.parametrize("suffix",((),("claims","runs","objects")))
def test_stale_even_empty_namespace_refuses_before_contact_or_dispatch(tmp_path,suffix):
    base=_base(tmp_path);base.mkdir(parents=True);base.chmod(0o700)
    for name in suffix:(base/name).mkdir(mode=0o700)
    calls=[];before={str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
    with pytest.raises(m.CompactCaptureError,match="fresh_namespace_already_exists"):
        _run(tmp_path,calls=calls,contact=lambda:calls.append("contact"))
    assert calls==[] and before=={str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}


def test_capacity_before_namespace_contact_and_claim(tmp_path,monkeypatch):
    calls=[];monkeypatch.setattr(m.os,"fstatvfs",lambda fd:SimpleNamespace(f_bavail=1,f_frsize=1))
    with pytest.raises(m.CompactCaptureError,match="disk_reserve_refused"):
        _run(tmp_path,calls=calls,contact=lambda:calls.append(1))
    assert calls==[] and not _base(tmp_path).exists()


def test_current_guard_and_durable_start_tamper_precede_dispatch(tmp_path):
    calls=[]
    def guard():
        if (_runpath(tmp_path)/"request-start.json").exists():raise RuntimeError(CONTACT)
    with pytest.raises(m.CompactCaptureError):_run(tmp_path,calls=calls,guard=guard)
    assert calls==[] and (_runpath(tmp_path)/"request-start.json").is_file()


def test_private_noop_constructor_cannot_authorize_actual_dispatch_or_private_run(tmp_path,monkeypatch):
    calls=[];identity={"invented":True};held=m._Inputs.__new__(m._Inputs)
    activation=m._Activation(identity,lambda:None,held)
    context=m._Dispatch(m._TOKEN,activation,identity,lambda:None,lambda:None,{"User-Agent":CONTACT})
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:calls.append(1))
    with pytest.raises(m.CompactCaptureError,match="trusted_activation_required"):m._transport(context)
    assert calls==[] and context.attempted is False
    with pytest.raises(m.CompactCaptureError):
        m._run(root=tmp_path,identity=identity,plan={},inputs=held,contact=lambda:CONTACT,transport=m._transport,
            fixture=False,guard=lambda:None,activation=activation)
    assert calls==[] and not _base(tmp_path).exists()


@pytest.mark.parametrize("leaf",("complete.json","reservation.json","request-start.json","request-result.json","inspection.json","response-headers.json","CAS"))
def test_independent_strict_readback_rejects_changed_raw_or_control(tmp_path,leaf):
    result=_run(tmp_path)
    path=next((_base(tmp_path)/"objects").iterdir()) if leaf=="CAS" else _runpath(tmp_path)/leaf
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


def test_old_input_ctime_is_strict_even_unchanged_bytes_and_mtime(tmp_path):
    result=_run(tmp_path);path=next((_base(tmp_path)/"objects").iterdir());held=m.directory._ReadbackDirectory(path.parent)
    try:
        before=os.stat(path);os.chmod(path,0o400);os.chmod(path,0o600)
        assert os.stat(path).st_mtime_ns==before.st_mtime_ns
        with pytest.raises(ValueError):held.check()
    finally:held.close()
    # A fresh readback has no historical ctime claim before its own first hold.
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


def test_no_unlisted_output_or_object_allowed(tmp_path):
    result=_run(tmp_path);extra=_base(tmp_path)/"objects"/("a"*64+".bin");extra.write_bytes(b"invented");extra.chmod(0o600)
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


def test_header_extra_key_and_manifest_claim_laundering_refuse(tmp_path):
    result=_run(tmp_path);manifest=_read(_runpath(tmp_path)/"inspection.json")
    bad=copy.deepcopy(manifest);bad["extra"]=False
    with pytest.raises(m.CompactCaptureError):m._validate_wire(bad,fixture=True,with_binary=False)
    for key in m._MANIFEST_FALSE:
        bad=copy.deepcopy(manifest);bad["compact"][key]=True
        with pytest.raises(m.CompactCaptureError):m._validate_wire(bad,fixture=True,with_binary=False)
    bad=copy.deepcopy(manifest);bad["compact"]["retained_candidates"]=True
    with pytest.raises(m.CompactCaptureError):m._validate_wire(bad,fixture=True,with_binary=False)


@pytest.mark.parametrize("retained,verify,expected",((True,False,0),(False,False,2),(False,True,0)))
def test_CLI_capture_failure_not_green_but_independent_failed_control_readback_is_success(monkeypatch,capsys,retained,verify,expected):
    seen=[]
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:(seen.append("protect"),"saved")[1])
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda saved:seen.append(("restore",saved)))
    value={"result":{"compact_retained":retained}}
    monkeypatch.setattr(m,"run_actual",lambda **kw:value)
    monkeypatch.setattr(m,"verify_actual",lambda **kw:value)
    argv=["--expected-head","a"*40,"--contact-stdin"]+(["--verify-report-sha256","b"*64] if verify else [])
    assert m.main(argv)==expected
    assert seen==["protect",("restore","saved")]
    assert json.loads(capsys.readouterr().out)==value


def test_worker_memory_monitor_real_protocol_is_close_not_contextmanager(monkeypatch,capsys):
    assert not hasattr(m.previous._WorkerMemoryGuard,"__enter__")
    seen=[]
    class Guard:
        def check(self):seen.append("sample")
        def close(self):seen.append("close")
    monkeypatch.setattr(m.previous,"_isolated",lambda:seen.append("flags"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:seen.append("native"))
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Guard)
    monkeypatch.setattr(m,"_current",lambda identity:seen.append("current"))
    monkeypatch.setattr(m,"_preflight_worker",lambda identity:{"source_only_fixture":True})
    m._worker("preflight",{},publish=True)
    assert seen[-1]=="close" and seen.index("native")<seen.index("sample")
    assert seen.count("current")>=2 and json.loads(capsys.readouterr().out)=={"ok":True,"value":{"source_only_fixture":True}}


@pytest.mark.parametrize("status",(200,403))
def test_transport_component_one_attempt_directHTTPS_and_non200_body_unread(monkeypatch,status):
    # Unit-component simulation only: the ordinary private constructors never
    # authorize a production run. Explicit test registry installation is not
    # actual-front/held-input evidence and no real opener is reachable.
    seen=[];identity={"fixture_component_only":True}
    held=m._Inputs.__new__(m._Inputs);held.check=lambda **kw:seen.append("held")
    guard=lambda:seen.append("guard")
    activation=m._Activation(identity,guard,held)
    monkeypatch.setitem(m._ACTIVATIONS,activation,(m._raw(identity),id(guard),id(held)))
    body=_response().body
    class Response:
        chunked=False
        def __init__(self):self.status=status
        def getheaders(self):return (("Content-Length",str(len(body))),)
        def read(self,count):seen.append(("read",count));assert status==200;return body
    class Connection:
        def __init__(self,host,timeout):seen.append((host,timeout))
        def request(self,method,path,headers):seen.append((method,path));assert CONTACT in headers["User-Agent"]
        def getresponse(self):return Response()
        def close(self):seen.append("closed")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    context=m._Dispatch(m._TOKEN,activation,identity,guard,lambda:seen.append("start"),{"User-Agent":CONTACT})
    response=m._transport(context)
    assert response.status==status and context.attempted is True
    assert ("www.sec.gov",15) in seen and ("GET",m.URL.removeprefix("https://www.sec.gov")) in seen
    assert seen.index("start")<seen.index(("www.sec.gov",15)) and seen[-1]=="closed"
    assert any(type(x) is tuple and x[0]=="read" for x in seen)==(status==200)
    with pytest.raises(m.CompactCaptureError):m._transport(context)


def test_transport_headers_mutation_refuses_before_even_dummy_opener(monkeypatch):
    seen=[];identity={"fixture_component_only":True};held=m._Inputs.__new__(m._Inputs);held.check=lambda **kw:None
    guard=lambda:None;activation=m._Activation(identity,guard,held)
    monkeypatch.setitem(m._ACTIVATIONS,activation,(m._raw(identity),id(guard),id(held)))
    headers={"User-Agent":CONTACT};context=m._Dispatch(m._TOKEN,activation,identity,guard,lambda:None,headers)
    headers["User-Agent"]="changed"
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:seen.append(1))
    with pytest.raises(m.CompactCaptureError):m._transport(context)
    assert seen==[] and context.attempted is False


@pytest.mark.parametrize("fault",("odd","upper","overlong","duplicate","wrong_hash","extra_key","short_nonfinal"))
def test_binary_chunk_wire_is_finite_exact_and_not_a_single_24MiB_string(fault):
    raw=b"x"*1024;item={"physical_sha256":m._sha(raw),"chunks_hex":[raw.hex()]}
    value=[item]
    if fault=="odd":item["chunks_hex"][0]+="a"
    elif fault=="upper":item["chunks_hex"][0]="AA"*1024
    elif fault=="overlong":item["chunks_hex"][0]="00"*(m.CHUNK+1)
    elif fault=="duplicate":value.append(copy.deepcopy(item))
    elif fault=="wrong_hash":item["physical_sha256"]="0"*64
    elif fault=="extra_key":item["extra"]=0
    else:item["chunks_hex"]=[raw.hex(),raw.hex()]
    with pytest.raises(m.CompactCaptureError):m._decode_objects(value)


def test_wire_chunk_boundary_positive_and_total_capacity(monkeypatch):
    raw=b"x"*(m.CHUNK+512);item={"physical_sha256":m._sha(raw),"chunks_hex":[raw[:m.CHUNK].hex(),raw[m.CHUNK:].hex()]}
    assert m._decode_objects([item])=={item["physical_sha256"]:raw}
    monkeypatch.setattr(m,"MAX_PHYSICAL",len(raw)-1)
    with pytest.raises(m.CompactCaptureError):m._decode_objects([item])


def _summary(rows):
    forms={f:sum(row["form_type"]==f for row in rows) for f in m.roster.FORMS}
    q={"period":"2020Q4","submission_rows":len(rows),"form4_or_4a_rows":forms["4"]+forms["4/A"],"source_form_counts":forms,
        "source_row_jsonl_sha256":m._sha(b"".join(m._raw(r)+b"\n" for r in rows)),"source_row_jsonl_bytes":sum(len(m._raw(r))+1 for r in rows)}
    return {"quarters":[q],"counts":{"context_submission_rows":len(rows)}}


def test_lightweight_roster_keeps_all_forms_and_source_ordinals():
    rows=[_row(form=form,accession=f"000000000{i}-20-00000{i}",ordinal=i) for i,form in enumerate(m.roster.FORMS,1)]
    routes=m._RosterRoutes()
    for row in rows:assert routes.consume(row) is None
    receipt,all_six,eligible=routes.finish(_summary(rows),[rows[0]["accession_number"]])
    assert len(all_six)==6 and len(eligible)==2 and receipt["q4_other_context_rows"]==4
    assert receipt["q4_known_consumed_routing_accessions"]==1
    assert receipt["source_rows_globally_deduplicated"] is False
    assert routes.q4[rows[0]["accession_number"]]==rows[0]


@pytest.mark.parametrize("where",("earlier","later","later_conflict"))
def test_cross_quarter_repeat_quarantines_Q4_even_when_later_and_different_form(where):
    q4=_row();outside=_row(period="2021Q1" if where!="earlier" else "2020Q1",filed="2021-01-04" if where!="earlier" else "2020-01-02")
    if where=="later_conflict":outside=_row(period="2021Q1",filed="2021-01-04",form="5")
    stream=[outside,q4] if where=="earlier" else [q4,outside]
    routes=m._RosterRoutes()
    for row in stream:routes.consume(row)
    summary=_summary([q4]);summary["counts"]["context_submission_rows"]=2
    receipt,all_six,eligible=routes.finish(summary,[])
    assert all_six=={A} and eligible==set() and receipt["full_25_source_occurrences"]==2
    assert receipt["q4_repeated_accessions"]==1 and receipt["cross_quarter_repeat_occurrences"]==1


def test_within_quarter_duplicate_and_source_hash_mutation_refuse():
    routes=m._RosterRoutes();routes.consume(_row())
    with pytest.raises(m.CompactCaptureError):routes.consume(_row(ordinal=2))
    bad=_row();bad["form_type"]="5"
    with pytest.raises(m.CompactCaptureError):m._RosterRoutes().consume(bad)


def test_native_command_preserves_memory_monitor_and_initial_denials_without_private_argv():
    command=m._command("inspect",{"invented_source_only":True});joined=" ".join(command)
    for text in ("-I","-S","-B","deny network*","deny process-fork","deny file-write*","/usr/bin/security",m.EMPTY_CACHE_PREFIX):assert text in joined
    assert CONTACT not in joined and m.URL not in joined and "publish=True" in joined
    assert m.EMPTY_CACHE_PREFIX==m.previous.EMPTY_CACHE_PREFIX==m.batch.campaign.EMPTY_CACHE_PREFIX


def test_child_uses_existing_decoded_result_not_wrong_double_JSON_decode(monkeypatch):
    expected={"invented":True};monkeypatch.setattr(m.old,"_run_child",lambda *a,**k:{"ok":True,"value":expected})
    assert m._child("preflight",{"invented":True}) is expected


def test_unknown_arguments_cannot_echo_secret(capsys):
    assert m.main(["--unknown-"+CONTACT])==2
    output=capsys.readouterr();assert CONTACT not in output.out+output.err and output.err==""
    assert json.loads(output.out)["code"]=="private_arguments_refused"


def test_actual_front_binds_identity_preflight_original_Git_before_any_inputs(monkeypatch):
    seen=[];identity={"source_only":True}
    monkeypatch.setattr(m,"_identity",lambda head:(seen.append("identity"),identity)[1])
    monkeypatch.setattr(m,"_child",lambda role,ident:(seen.append("native"),{"execution_identity":identity,"schema":m.SCHEMA+"/input-preflight"})[1])
    def stopped(plan):seen.append("original-Git");raise RuntimeError("invented stop")
    monkeypatch.setattr(m,"_parent_plan_proofs",stopped)
    monkeypatch.setattr(m,"_Inputs",lambda *a,**k:pytest.fail("inputs opened before original proof"))
    with pytest.raises(RuntimeError):m.run_actual(expected_head="a"*40)
    assert seen==["identity","native","original-Git"]


def test_genuine_old_input_shape_reads_continuously_held_listing_not_nonexistent_raw(tmp_path,monkeypatch):
    class ReachedListing(Exception):pass
    seen=[]
    path=tmp_path.joinpath(*m.directory.ARTIFACT_PARTS,"runs",m.directory.AUDIT_ID)
    folder=SimpleNamespace(path=path,read=lambda name,**kw:(seen.append(name),b"invented held listing")[1])
    held=SimpleNamespace(folders=[None,None,None,folder],metadata={},close=lambda:seen.append("closed"))
    assert not hasattr(held,"raw")
    monkeypatch.setattr(m.previous,"_Inputs",lambda root:held)
    def parse(raw):
        assert raw==b"invented held listing"
        raise ReachedListing()
    monkeypatch.setattr(m.directory,"parse_directory_inventory",parse)
    with pytest.raises(ReachedListing):m._Inputs(tmp_path)
    assert seen==["response.bin","closed"]


@pytest.mark.parametrize("fault",("identity","admitted","unknown_member_key","boolean_ordinal","source_count","name_policy"))
def test_parent_IPC_descriptor_claims_have_closed_exact_schema(tmp_path,fault):
    _run(tmp_path);bad=_read(_runpath(tmp_path)/"inspection.json")
    descriptor=bad["compact"]["candidates"][0]
    if fault=="identity":descriptor["identity_validated"]=True
    elif fault=="admitted":descriptor["admitted"]=True
    elif fault=="unknown_member_key":descriptor["unexpected"]=False
    elif fault=="boolean_ordinal":descriptor["source_ordinal"]=True
    elif fault=="source_count":descriptor["payload_bytes"]=-1
    else:bad["compact"]["name_profile"]="invented broader policy"
    with pytest.raises(m.CompactCaptureError):m._validate_wire(bad,fixture=True,with_binary=False)
