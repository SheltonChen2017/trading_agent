"""Invented directory metadata only; external native network/Keychain denial."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody")
pytest.importorskip("termios", reason="macOS/POSIX private contact")
from research import insider_buying_sec_feed_directory_q4_v2 as m


CONTACT = "invented@unit.test"


def _body():
    return {"directory":{"name":"opaque observed display","parent-dir":"opaque parent","item":[
        {"name":"20201002.nc.tar.gz","href":"20201002.nc.tar.gz","type":"file","size":"12.345 KB","last-modified":"2020-10-02 22:01:02"},
        {"name":"20201001.nc.tar.gz","href":"./20201001.nc.tar.gz","type":"file","size":"1 KB","last-modified":"2020-10-03 01:02:03"}]}}


def _response(raw=None, headers=None, status=200):
    raw = m._raw(_body()) if raw is None else raw
    return m.SecHttpResult(status, (("Content-Length", str(len(raw))),) if headers is None else headers, raw)


def _base(root): return root.joinpath(*m.ARTIFACT_PARTS)
def _runpath(root): return _base(root)/"runs"/m.AUDIT_ID
def _json(path): return json.loads(path.read_bytes())


def _run(root, *, response=None, calls=None, on_call=None, **kwargs):
    def wire(url, headers, cap):
        if calls is not None: calls.append((url, headers, cap))
        if on_call is not None: on_call()
        assert url == m.URL and cap == 512*1024 and CONTACT in headers["User-Agent"]
        return _response() if response is None else response
    return m._run_invented_probe(root=root, transport=wire, **kwargs)


def test_known_five_string_profile_preserves_order_lexemes_and_false_authority():
    result=m.parse_directory_inventory(m._raw(_body()))
    assert [r["listed_name"] for r in result["entries"]]==["20201002.nc.tar.gz","20201001.nc.tar.gz"]
    assert result["entries"][0]["advertised_magnitude_text"]=="12.345"
    assert result["entries"][0]["advertised_unit"]=="KB"
    assert result["directory_display_strings_used_for_identity"] is False
    assert result["archive_selected"] is False
    assert result["missing_directory_dates_do_not_establish_absent_filings"] is True
    assert all(v is False or type(v)is int and v==0 for v in result["authority"].values())


@pytest.mark.parametrize("fault",("root","extra","empty","unknown_item","duplicate","wrong_quarter","bad_date","bad_name","directory","negative_size","float_size","bool_size","unknown_unit","no_href","foreign_href","query","percent","zero_size"))
def test_unqualified_shapes_refuse_without_partial_inventory(fault):
    body=_body();directory=body["directory"];item=directory["item"][0]
    if fault=="root":body=[]
    elif fault=="extra":body["extra"]=1
    elif fault=="empty":directory["item"]=[]
    elif fault=="unknown_item":item["unknown"]=True
    elif fault=="duplicate":directory["item"].append(dict(item))
    elif fault=="wrong_quarter":item["name"]="20210101.nc.tar.gz"
    elif fault=="bad_date":item["name"]="20201131.nc.tar.gz"
    elif fault=="bad_name":item["name"]="../20201002.nc.tar.gz"
    elif fault=="directory":item["type"]="dir"
    elif fault=="negative_size":item["size"]="-1 KB"
    elif fault=="float_size":item["size"]=1.5
    elif fault=="bool_size":item["size"]=True
    elif fault=="unknown_unit":item["size"]="12 MB"
    elif fault=="no_href":del item["href"]
    elif fault=="foreign_href":item["href"]="https://evil.test/"+item["name"]
    elif fault=="query":item["href"]+="?x=1"
    elif fault=="percent":item["href"]="%32"+item["href"][1:]
    else:item["size"]="0.000 KB"
    with pytest.raises(m.FeedDirectoryError):m.parse_directory_inventory(m._raw(body))


@pytest.mark.parametrize("prefix",("", "./",m.DIRECTORY+"/",m.URL.removesuffix("index.json")))
def test_four_exact_same_item_href_forms(prefix):
    body=_body();body["directory"]["item"][0]["href"]=prefix+"20201002.nc.tar.gz"
    assert m.parse_directory_inventory(m._raw(body))["entry_count"]==2


@pytest.mark.parametrize("raw",(b'{"directory":{},"directory":{}}', b'{"x":NaN}', b'not JSON',
    b'{"x":'+b'['*30+b'0'+b']'*30+b'}'))
def test_malformed_duplicate_nonfinite_or_deep_json_refuses(raw):
    with pytest.raises(m.FeedDirectoryError): m.parse_directory_inventory(raw)


def test_single_request_private_scope_start_before_callback_and_observed_readback(tmp_path):
    calls = []
    def check():
        run = _runpath(tmp_path)
        assert (run/"reservation.json").is_file() and (run/"request-start.json").is_file()
        assert (_base(tmp_path)/"claims"/m._claim_name()).is_file()
    result = _run(tmp_path, calls=calls, on_call=check)
    assert len(calls) == result["transport_invocations"] == 1 and result["directory_inventory_completed"] is True
    assert result["archive_requests"] == result["accession_requests"] == 0
    verified = m.verify_invented_probe(tmp_path, result["report_sha256"])
    assert verified["response_sha256"] == result["response_sha256"] and verified["directory_inventory_completed"]
    assert verified["candidate_inventory"]==result["candidate_inventory"]
    assert m._sha(m._raw(verified["candidate_inventory"]))==result["inventory_sha256"]
    for path in _base(tmp_path).rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
        if path.is_file(): assert CONTACT.encode() not in path.read_bytes()
    with pytest.raises(ValueError): _run(tmp_path)
    assert len(calls) == 1


def test_contact_is_read_only_after_durable_reservation_before_claim(tmp_path):
    observed = []
    def contact():
        observed.append(1)
        assert (_runpath(tmp_path)/"reservation.json").is_file()
        assert list((_base(tmp_path)/"claims").iterdir()) == []
        return CONTACT
    _run(tmp_path, contact=contact)
    assert observed == [1]


@pytest.mark.parametrize("status",(301,403,404,429,500))
def test_non200_stops_once_without_body_pin_or_retention(tmp_path,status):
    calls=[]; result=_run(tmp_path,calls=calls,response=_response(b"DO NOT HASH OR RETAIN",headers=(),status=status))
    assert len(calls)==1 and not result["response_retained"] and result["response_sha256"] is None
    assert not (_runpath(tmp_path)/"response.bin").exists()
    assert result["candidate_inventory"] is None
    assert m.verify_invented_probe(tmp_path,result["report_sha256"])["disposition"]=="http_refused_no_body_no_retry"


@pytest.mark.parametrize("raw",(b'{"unexpected":"profile"}', b'{not JSON}', b'{"unexpected":"\xff"}'))
def test_complete_safe_unknown_format_retained_before_profile_parse_and_never_retried(tmp_path,raw,monkeypatch):
    original=m.parse_directory_inventory; observed=[]
    def parse(body):
        assert (_runpath(tmp_path)/"response.bin").read_bytes()==raw
        observed.append(body); return original(body)
    monkeypatch.setattr(m,"parse_directory_inventory",parse)
    result=_run(tmp_path,response=_response(raw))
    assert observed==[raw] and result["response_retained"] is True and not result["directory_inventory_completed"]
    assert result["disposition"]=="opaque_response_retained_inventory_unqualified"
    assert result["candidate_inventory"] is None
    assert result["response_sha256"]==m._sha(raw) and result["response_bytes"]==len(raw)
    assert not (_runpath(tmp_path)/"inventory.json").exists()
    assert not m.verify_invented_probe(tmp_path,result["report_sha256"])["directory_inventory_completed"]
    with pytest.raises(ValueError): _run(tmp_path)


@pytest.mark.parametrize("encode",(lambda s:s,lambda s:quote(s,safe=""),lambda s:quote(quote(s,safe=""),safe=""),
    lambda s:"".join("\\u%04x"%ord(c) for c in s),lambda s:s.replace("@","&#64;")))
@pytest.mark.parametrize("where",("headers","body"))
def test_contact_echo_screen_precedes_any_response_hash_or_retention(tmp_path,encode,where):
    raw=m._raw(_body()); headers=(("Content-Length",str(len(raw))),)
    if where=="headers": headers=(*headers,("X-Echo",encode(CONTACT)))
    else: raw+=encode(CONTACT).encode(); headers=(("Content-Length",str(len(raw))),)
    result=_run(tmp_path,response=_response(raw,headers=headers))
    assert result["response_sha256"] is result["response_bytes"] is None
    assert _json(_runpath(tmp_path)/"request-result.json")["response_headers_sha256"] is None
    assert not result["response_retained"] and not (_runpath(tmp_path)/"response.bin").exists()


@pytest.mark.parametrize("encoding",("utf-16-le","utf-16-be","utf-32-le","utf-32-be"))
def test_coherent_multibyte_contact_echo_refuses_before_body_or_header_hash(tmp_path,monkeypatch,encoding):
    raw=('{"echo":"'+CONTACT+'"}').encode(encoding)
    headers=(("Content-Length",str(len(raw))),)
    original=m._sha; prohibited=(raw,m._raw(headers)); remote_hashes=[]
    def digest(value):
        if value in prohibited: remote_hashes.append(value)
        return original(value)
    monkeypatch.setattr(m,"_sha",digest)
    result=_run(tmp_path,response=_response(raw,headers=headers))
    assert not result["response_retained"]
    retained=_json(_runpath(tmp_path)/"request-result.json")
    assert retained["response_sha256"] is retained["response_bytes"] is retained["response_headers_sha256"] is None
    assert not (_runpath(tmp_path)/"response.bin").exists()
    assert not (_runpath(tmp_path)/"response-headers.json").exists()
    assert remote_hashes==[], "remote body/header hashing must follow privacy screening"


def _transport_context(monkeypatch):
    events=[]
    monkeypatch.setattr(m,"_RAW_TRANSPORT",lambda *a:pytest.fail("no real opener in transport-control fixtures"))
    monkeypatch.setattr(m,"signal",SimpleNamespace(ITIMER_REAL=1,SIGALRM=2,
        getitimer=lambda _: (0.0,0.0),getsignal=lambda _:"prior",
        signal=lambda *args:events.append(("handler",*args)),
        setitimer=lambda *args:events.append(("timer",*args))))
    context=m._Context(m._TOKEN,m.LANE_ROOT,{},lambda:None,None,None,"a"*64,"b"*64,{})
    return context,events


def test_production_transport_custody_refusal_precedes_alarm_and_raw_invocation(monkeypatch):
    context,events=_transport_context(monkeypatch)
    def refuse(_): raise m.FeedDirectoryError("invented_local_custody_refusal")
    monkeypatch.setattr(m._Context,"check",refuse)
    with pytest.raises(m.FeedDirectoryError,match="invented_local_custody_refusal"):
        m._production_transport(context)
    assert not context.attempted and not context.raw_transport_invoked and events==[]


def test_production_transport_absolute_deadline_is_fixed_no_retry_and_restores_alarm(monkeypatch):
    context,events=_transport_context(monkeypatch); calls=[]
    monkeypatch.setattr(m._Context,"check",lambda _:None)
    def deadline(*args): calls.append(args);raise m._DeadlineExceeded()
    monkeypatch.setattr(m,"_RAW_TRANSPORT",deadline)
    with pytest.raises(m.FeedDirectoryError,match="^transport_deadline_refused$"):
        m._production_transport(context)
    assert len(calls)==1 and calls[0]==(m.URL,{},m.MAX_RESPONSE_BYTES)
    assert context.attempted and context.raw_transport_invoked
    assert [event for event in events if event[0]=="timer"]==[("timer",1,30),("timer",1,0)]
    assert events[-1]==("handler",2,"prior")


@pytest.mark.parametrize("size",(m.MAX_RESPONSE_BYTES,m.MAX_RESPONSE_BYTES+1))
def test_response_bound_inclusive_and_oversized_source_not_retained(tmp_path,size):
    raw=m._raw(_body());raw+=b" "*(size-len(raw))
    result=_run(tmp_path,response=_response(raw))
    assert result["response_retained"] is (size==m.MAX_RESPONSE_BYTES)
    assert result["directory_inventory_completed"] is (size==m.MAX_RESPONSE_BYTES)


@pytest.mark.parametrize("headers",((("Content-Length","1"),("Content-Length","1")),
    (("Transfer-Encoding","chunked "),),(("Content-Encoding","gzip"),),()))
def test_ambiguous_or_encoded_framing_never_retained(tmp_path,headers):
    assert not _run(tmp_path,response=_response(headers=headers))["response_retained"]


def test_transport_failure_consumes_only_one_url_and_never_echoes_exception(tmp_path):
    calls=[]
    def fail(*args): calls.append(1);raise OSError("PRIVATE remote exception")
    result=m._run_invented_probe(root=tmp_path,transport=fail)
    assert calls==[1] and result["http_status"] is None and not result["response_retained"]
    assert b"PRIVATE" not in (_runpath(tmp_path)/"complete.json").read_bytes()
    assert m.verify_invented_probe(tmp_path,result["report_sha256"])["transport_invocations"]==1


@pytest.mark.parametrize("fixture",(True,False))
def test_internal_runner_cannot_bypass_actual_fixture_root_and_callback_fronts(tmp_path,monkeypatch,fixture):
    root=m.LANE_ROOT if fixture else tmp_path
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64}
    identity={"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    monkeypatch.setattr(m.publication,"_NewDirectory",lambda *a,**k:pytest.fail("bypass must precede namespace creation"))
    with pytest.raises(ValueError):m._run(root=root,identity=identity,guard=lambda:None,
        contact=lambda:CONTACT,transport=lambda *a:pytest.fail("must not dispatch"),fixture=fixture)


@pytest.mark.parametrize("which",("raw","wrapper"))
def test_fixture_real_transport_objects_refuse_before_callback(tmp_path,monkeypatch,which):
    monkeypatch.setattr(m,"_RAW_TRANSPORT",lambda *a:pytest.fail("real transport never allowed in fixture"))
    callback=m._RAW_TRANSPORT if which=="raw" else m._production_transport
    with pytest.raises(ValueError):m._run_invented_probe(root=tmp_path,transport=callback)


@pytest.mark.parametrize("fault",("credential_bool","fixture_integer","authority_integer","body","inventory","claim","start","count"))
def test_readback_rejects_rehashed_but_inconsistent_or_untyped_controls(tmp_path,fault):
    result=_run(tmp_path);run=_runpath(tmp_path);complete=_json(run/"complete.json")
    if fault=="credential_bool":complete["credential_reads"]=False
    elif fault=="fixture_integer":complete["fixture_only"]=1
    elif fault=="authority_integer":complete["authority"]["archive_download_authorized"]=0
    elif fault=="body":
        path=run/"response.bin";path.write_bytes(path.read_bytes().replace(b"12.345",b"12.346"))
    elif fault=="inventory":
        path=run/"inventory.json";value=_json(path);value["advertised_KB_base_qualified"]=True;path.write_bytes(m._raw(value))
    elif fault=="claim":
        path=_base(tmp_path)/"claims"/m._claim_name();value=_json(path);value["url"]=m.URL+"extra";path.write_bytes(m._raw(value))
    elif fault=="start":
        path=run/"request-start.json";value=_json(path);value["attempt"]=True;path.write_bytes(m._raw(value))
    else: complete["archive_requests"]=False
    raw=m._raw(complete);(run/"complete.json").write_bytes(raw)
    with pytest.raises(ValueError):m.verify_invented_probe(tmp_path,m._sha(raw))


def test_source_change_during_callback_prevents_completion_and_preserves_claim(tmp_path):
    changed=False
    def guard():
        if changed:raise ValueError("invented_source_changed")
    def wire(*args):
        nonlocal changed
        changed=True;return _response()
    with pytest.raises(ValueError):m._run_invented_probe(root=tmp_path,transport=wire,guard=guard)
    assert (_runpath(tmp_path)/"request-start.json").is_file()
    assert (_base(tmp_path)/"claims"/m._claim_name()).is_file()
    assert not (_runpath(tmp_path)/"complete.json").exists()


def test_native_actual_verifier_front_refuses_before_source_or_artifact_reads(monkeypatch):
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,no_user_site=1,dont_write_bytecode=1),
        pycache_prefix=m.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:pytest.fail("flags must precede all probes"))
    monkeypatch.setattr(m,"_verify",lambda *a:pytest.fail("no actual artifacts"))
    with pytest.raises(m.FeedDirectoryError,match="isolated"):
        m.verify_actual_probe(expected_report_sha256="a"*64,execution_identity={})


def test_cli_refusal_is_fixed_and_exit2(monkeypatch,capsys):
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:None)
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda value:None)
    monkeypatch.setattr(m,"run_actual_probe",lambda *a,**k:(_ for _ in ()).throw(ValueError("PRIVATE")))
    assert m.main(["--expected-head","a"*40])==2
    output=capsys.readouterr();assert "PRIVATE" not in output.err+output.out and output.err.startswith("REFUSED:")


def _identity_for(root, count=104):
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64,
        **{f"research/invented_source_{index:04}.py":"c"*64 for index in range(count-2)}}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


def test_new_q4_scope_is_not_consumed_q1_q2_alias():
    assert m.URL=="https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/index.json"
    assert m.AUDIT_ID=="ib-sec-feed-directory-2020q4-20261025-once"
    assert m.ARTIFACT_PARTS==("artifacts","insider_buying","sec_feed_directory_q4_v2")
    assert m.URL!=m.foreign_json.URL
    assert m._scope()["archive_selection_authorized"] is False
    assert m.parse_directory_inventory(m._raw(_body()))["period"]=="2020Q4"


@pytest.mark.parametrize("count",(104,256,1024))
def test_full_production_sized_control_preflight_roundtrips_without_old_foreign_limit(tmp_path,count):
    identity=_identity_for(tmp_path,count)
    forms=m._preflight_controls(identity,False,root=tmp_path)
    assert set(forms)=={"identity","reservation","claim","start","contact","capacity_result","capacity_complete"}
    for raw in forms.values(): assert m._raw(m._decode(raw,canonical=True))==raw
    assert len(m._decode(forms["reservation"],canonical=True)["execution_identity"]["source_sha256"])==count
    complete=m._decode(forms["capacity_complete"],canonical=True)
    assert len(complete["execution_identity"]["source_sha256"])==count
    assert complete==m._complete_control(identity,False,m._sha(forms["reservation"]),
        m._decode(forms["capacity_result"],canonical=True),m._sha(forms["capacity_result"]),True)
    assert len(forms["capacity_complete"])<=m.MAX_CONTROL_BYTES
    with pytest.raises(m.foreign_json.FeedDirectoryError,match="json_resource_bound_refused"):
        m.foreign_json._decode(forms["reservation"],canonical=True)


def test_direct_private_context_and_fabricated_actual_runner_cannot_open(monkeypatch):
    calls=[];monkeypatch.setattr(m,"_RAW_TRANSPORT",lambda *a:calls.append(1))
    identity=_identity_for(m.LANE_ROOT)
    context=m._Context(m._TOKEN,m.LANE_ROOT,identity,lambda:None,None,None,"a"*64,"b"*64,{})
    with pytest.raises(m.FeedDirectoryError,match="genuine_context"):
        m._production_transport(context)
    monkeypatch.setattr(m.publication,"_NewDirectory",lambda *a,**k:pytest.fail("no namespace"))
    with pytest.raises(m.FeedDirectoryError,match="trusted_actual_activation"):
        m._run(root=m.LANE_ROOT,identity=identity,guard=lambda:None,contact=m.contact_io._stdin_contact,transport=m._production_transport,fixture=False)
    assert calls==[]


def test_default_invented_run_and_readback_have_104_source_reservation(tmp_path):
    result=_run(tmp_path)
    reservation=_json(_runpath(tmp_path)/"reservation.json")
    assert len(reservation["execution_identity"]["source_sha256"])==104
    assert m.verify_invented_probe(tmp_path,result["report_sha256"])["directory_inventory_completed"] is True


@pytest.mark.parametrize("fault",("refuse","nonidentical","complete_capacity"))
def test_preflight_failure_precedes_namespace_contact_claim_and_transport(tmp_path,monkeypatch,fault):
    old=m._decode;seen=[]
    def decode(raw,*,canonical=False):
        if canonical:
            if fault=="refuse": raise m.FeedDirectoryError("invented_codec_refusal")
            value=old(raw,canonical=True)
            seen.append(value.get("schema"))
            if fault=="nonidentical" and "source_sha256" in value: value["clean"]=False
            if fault=="complete_capacity" and value.get("schema")==m.SCHEMA+"/complete":
                raise m.FeedDirectoryError("invented_future_complete_codec_refusal")
            return value
        return old(raw)
    monkeypatch.setattr(m,"_decode",decode)
    monkeypatch.setattr(m.publication,"_NewDirectory",lambda *a,**k:pytest.fail("preflight must precede namespace"))
    with pytest.raises(m.FeedDirectoryError):
        m._run_invented_probe(root=tmp_path,contact=lambda:pytest.fail("preflight must precede contact"),
            transport=lambda *a:pytest.fail("preflight must precede transport"))
    assert not _base(tmp_path).exists()
    if fault=="complete_capacity": assert m.SCHEMA+"/complete" in seen


def test_preflight_never_routes_own_controls_through_foreign_decoder(tmp_path,monkeypatch):
    monkeypatch.setattr(m.foreign_json,"_decode",lambda *a,**k:pytest.fail("foreign codec must not decode own controls"))
    forms=m._preflight_controls(_identity_for(tmp_path),False,root=tmp_path)
    assert len(forms)==7




@pytest.mark.parametrize("fault",("source_item_hash","source_ordinal_bool"))
def test_candidate_metadata_rehashed_forgery_cannot_replace_independent_source_replay(tmp_path,fault):
    _run(tmp_path);run=_runpath(tmp_path)
    inventory=_json(run/"inventory.json");result=_json(run/"request-result.json");complete=_json(run/"complete.json")
    entry=inventory["entries"][0]
    if fault=="source_item_hash": entry["source_item_canonical_sha256"]="0"*64
    else: entry["source_ordinal"]=True
    inventory["ordered_entries_sha256"]=m._sha(m._raw(inventory["entries"]))
    raw=m._raw(inventory);(run/"inventory.json").write_bytes(raw)
    result["inventory_sha256"]=m._sha(raw);raw=m._raw(result);(run/"request-result.json").write_bytes(raw)
    complete["result"]=result;complete["result_sha256"]=m._sha(raw)
    raw=m._raw(complete);(run/"complete.json").write_bytes(raw)
    with pytest.raises(ValueError): m.verify_invented_probe(tmp_path,m._sha(raw))


@pytest.mark.parametrize("name",("data/__init__.py","data/hashing.py","ml/immutable_io.py","research/insider_buying/sec_complete_submission.py"))
def test_real_shaped_internal_roots_are_preserved_in_control_identity(tmp_path,name):
    identity=_identity_for(tmp_path);identity["source_sha256"][name]="d"*64
    identity["source_inventory_sha256"]=m._sha(m._raw(identity["source_sha256"]))
    assert m._source_identity(identity,root=tmp_path) is identity
    assert m._decode(m._preflight_controls(identity,False,root=tmp_path)["reservation"],canonical=True)["execution_identity"]==identity


@pytest.mark.parametrize("name",("../secret.py","/absolute.py","research//bad.py","research/./bad.py","research/source.txt","research/bad-name.py","research/evil\\x.py"))
def test_source_inventory_noncanonical_paths_refuse(tmp_path,name):
    identity=_identity_for(tmp_path);identity["source_sha256"][name]="d"*64
    identity["source_inventory_sha256"]=m._sha(m._raw(identity["source_sha256"]))
    with pytest.raises(m.FeedDirectoryError,match="source_identity"):
        m._source_identity(identity,root=tmp_path)


def test_native_preflight_failure_precedes_actual_activation_namespace_and_contact(monkeypatch):
    identity=_identity_for(m.LANE_ROOT);events=[]
    monkeypatch.setattr(m,"_identity",lambda head:identity)
    def preflight(value):events.append("preflight");raise m.FeedDirectoryError("native_source_preflight_refused")
    monkeypatch.setattr(m,"_native_preflight",preflight)
    monkeypatch.setattr(m,"_run",lambda **k:pytest.fail("no namespace/contact or activated run"))
    before=len(m._ACTIVATIONS)
    with pytest.raises(m.FeedDirectoryError,match="native_source_preflight"):
        m.run_actual_probe("a"*40)
    assert events==["preflight"] and len(m._ACTIVATIONS)==before


def test_actual_activation_is_only_live_during_trusted_run(monkeypatch):
    identity=_identity_for(m.LANE_ROOT);events=[];seen=[]
    monkeypatch.setattr(m,"_identity",lambda head:identity)
    monkeypatch.setattr(m,"_native_preflight",lambda value:events.append("native"))
    def run(**kwargs):
        events.append("run");seen.append(kwargs["activation"])
        assert kwargs["contact"] is m.contact_io._stdin_contact
        m._activated(kwargs["activation"],identity)
        return {"invented":True}
    monkeypatch.setattr(m,"_run",run)
    assert m.run_actual_probe("a"*40)=={"invented":True} and events==["native","run"]
    with pytest.raises(m.FeedDirectoryError,match="trusted_actual_activation"):
        m._activated(seen[0],identity)


def test_native_preflight_worker_proves_denial_before_any_source_read(monkeypatch):
    events=[];identity=_identity_for(m.LANE_ROOT)
    monkeypatch.setattr(m,"_isolated",lambda:events.append("flags"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:events.append("denial"))
    monkeypatch.setattr(m,"_current",lambda value:events.append("sources"))
    value=m._preflight_worker(identity)
    assert events==["flags","denial","sources","sources"]
    assert value["native_network_fork_allwrite_securityexec_denial"] is True
    assert value["provider_requests"]==value["contact_reads"]==0


@pytest.mark.parametrize("fault",("exit","stderr","echo","bool"))
def test_native_launcher_requires_exact_own_metadata_result(monkeypatch,fault):
    identity=_identity_for(m.LANE_ROOT)
    monkeypatch.setattr(m,"_current",lambda value:None)
    expected={"schema":m.SCHEMA+"/source-preflight","source_inventory_sha256":identity["source_inventory_sha256"],
        "control_sizes":{name:len(raw) for name,raw in m._preflight_controls(identity,False,root=m.LANE_ROOT).items()},
        "native_network_fork_allwrite_securityexec_denial":True,"provider_requests":0,"contact_reads":0}
    if fault=="bool":expected["provider_requests"]=False
    child=SimpleNamespace(returncode=2 if fault=="exit" else 0,stderr=b"PRIVATE" if fault=="stderr" else b"",
        stdout=m._raw(expected)+(b"PRIVATE" if fault=="echo" else b"\n"))
    monkeypatch.setattr(m.source_runner.launcher,"run_child",lambda *a,**k:child)
    with pytest.raises(m.FeedDirectoryError,match="native_source_preflight"):
        m._native_preflight(identity)


def test_readback_holds_shared_scope_lock_and_restores_it(tmp_path,monkeypatch):
    result=_run(tmp_path);events=[];original=m.fcntl.flock
    def flock(fd,op):events.append(op);return original(fd,op)
    monkeypatch.setattr(m.fcntl,"flock",flock)
    m.verify_invented_probe(tmp_path,result["report_sha256"])
    assert events[0]==m.fcntl.LOCK_SH|m.fcntl.LOCK_NB and events[-1]==m.fcntl.LOCK_UN


def test_old_readback_strict_ctime_change_before_first_read_refuses(tmp_path):
    result=_run(tmp_path);held=m._ReadbackDirectory(_runpath(tmp_path))
    try:
        path=_runpath(tmp_path)/"complete.json";before=path.stat();os.chmod(path,0o400);os.chmod(path,0o600)
        assert path.stat().st_mtime_ns==before.st_mtime_ns
        with pytest.raises(m.FeedDirectoryError,match="old_readback_inventory_or_version"):
            held.read("complete.json")
    finally:held.close()


@pytest.mark.parametrize("fault",("mode","hardlink","extra","symlink"))
def test_readback_custody_and_inventory_refuse(tmp_path,fault):
    result=_run(tmp_path);run=_runpath(tmp_path)
    if fault=="mode":os.chmod(run/"complete.json",0o644)
    elif fault=="hardlink":os.link(run/"complete.json",tmp_path/"alias.json")
    elif fault=="extra":(run/"unexpected").write_bytes(b"x")
    else:
        raw=(run/"complete.json").read_bytes();(run/"complete.json").unlink()
        target=tmp_path/"target.json";target.write_bytes(raw);(run/"complete.json").symlink_to(target)
    with pytest.raises(ValueError):m.verify_invented_probe(tmp_path,result["report_sha256"])


def test_cli_unknown_arguments_never_echo_secret_and_echo_protection_is_first(monkeypatch,capsys):
    events=[]
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:events.append("protect"))
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda value:events.append("restore"))
    monkeypatch.setattr(m,"run_actual_probe",lambda *a,**k:pytest.fail("must not activate"))
    assert m.main(["--expected-head","a"*40,"--PRIVATE-SECRET"])==2
    output=capsys.readouterr();assert "PRIVATE-SECRET" not in output.err+output.out
    assert events==["protect","restore"]


def test_readback_constructor_failure_closes_open_directory_preserving_primary(tmp_path,monkeypatch):
    _run(tmp_path);path=_runpath(tmp_path);held=[];original=m.privacy._Directory
    def directory(*args,**kwargs):
        value=original(*args,**kwargs);held.append(value);return value
    real_stat=m.os.stat
    def fail_stat(name,*args,**kwargs):
        if name=="complete.json" and kwargs.get("dir_fd")==held[0].fd:
            raise OSError("invented_primary_stat_refusal")
        return real_stat(name,*args,**kwargs)
    monkeypatch.setattr(m.privacy,"_Directory",directory);monkeypatch.setattr(m.os,"stat",fail_stat)
    with pytest.raises(OSError,match="invented_primary_stat_refusal"):
        m._ReadbackDirectory(path)
    with pytest.raises(OSError):m.os.fstat(held[0].fd)


@pytest.mark.parametrize("phase",("source_identity","native_source_preflight"))
def test_actual_front_refusal_reports_only_finite_known_phase(monkeypatch,phase):
    identity=_identity_for(m.LANE_ROOT)
    def refuse(*a):raise OSError("PRIVATE-CONTACT-remote-exception")
    monkeypatch.setattr(m,"_identity",refuse if phase=="source_identity" else lambda head:identity)
    monkeypatch.setattr(m,"_native_preflight",refuse)
    with pytest.raises(m.FeedDirectoryError) as caught:m.run_actual_probe("a"*40)
    assert caught.value.stage==phase and caught.value.args==("local_operation_refused",)


def test_late_publication_refusal_preserves_stage_without_foreign_message(tmp_path,monkeypatch):
    old=m.publication._NewDirectory.publish
    def fail(self,name,raw,**kwargs):
        if name=="complete.json":raise OSError("PRIVATE-CONTACT-do-not-export")
        return old(self,name,raw,**kwargs)
    monkeypatch.setattr(m.publication._NewDirectory,"publish",fail)
    with pytest.raises(m.FeedDirectoryError) as caught:_run(tmp_path)
    assert caught.value.stage=="complete_publication" and caught.value.args==("local_operation_refused",)
    assert (_runpath(tmp_path)/"request-start.json").exists() and not (_runpath(tmp_path)/"complete.json").exists()


def test_cleanup_refusal_is_distinct_from_success_and_omits_foreign_message(tmp_path,monkeypatch):
    old=m.publication._close_all
    def fail(*a):old(*a);raise OSError("PRIVATE-CONTACT-cleanup")
    monkeypatch.setattr(m.publication,"_close_all",fail)
    with pytest.raises(m.FeedDirectoryError) as caught:_run(tmp_path)
    assert caught.value.stage=="cleanup" and caught.value.args==("local_operation_refused",)
    assert (_runpath(tmp_path)/"complete.json").exists()


@pytest.mark.parametrize("exception",(OSError("PRIVATE"),m.FeedDirectoryError("PRIVATE"),m.FeedDirectoryError("source_identity_refused")))
def test_cli_error_codes_are_allowlisted_never_exception_strings(monkeypatch,capsys,exception):
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:None)
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda _:None)
    def fail(*a,**k):raise exception
    monkeypatch.setattr(m,"run_actual_probe",fail)
    assert m.main(["--expected-head","a"*40])==2
    output=capsys.readouterr()
    assert "PRIVATE" not in output.err+output.out and "stage=arguments code=" in output.err
    expected="source_identity_refused" if type(exception)is m.FeedDirectoryError and exception.args==( "source_identity_refused",) else "local_operation_refused"
    assert "code="+expected in output.err


def test_own_exception_class_does_not_make_unlisted_message_safe():
    exception=m.FeedDirectoryError("PRIVATE-CONTACT-unlisted-own-code")
    exception.stage="PRIVATE-stage"
    result=m._classified("source_identity",exception)
    assert result.args==("local_operation_refused",) and result.stage=="source_identity"


@pytest.mark.parametrize("children",(False,True))
def test_stale_empty_namespace_is_permanently_refused_before_contact_or_claim(tmp_path,children):
    base=_base(tmp_path);base.mkdir(parents=True,mode=0o700)
    if children:
        (base/"claims").mkdir(mode=0o700);(base/"runs").mkdir(mode=0o700)
    before=set(base.iterdir())
    with pytest.raises(m.FeedDirectoryError,match="fresh_namespace_already_exists"):
        m._run_invented_probe(root=tmp_path,contact=lambda:pytest.fail("stale root must precede contact"),
            transport=lambda *a:pytest.fail("stale root must precede raw transport"))
    assert set(base.iterdir())==before and not (base/"scope.lock").exists()

