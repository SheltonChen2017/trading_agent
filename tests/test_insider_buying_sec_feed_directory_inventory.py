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
from research import insider_buying_sec_feed_directory_inventory as m


CONTACT = "invented@unit.test"


def _body():
    return {"directory": {"name": m.DIRECTORY, "parent-dir": m.PARENT_DIRECTORY, "item": [
        {"name": "20210105.nc.tar.gz", "type": "file", "size": "123456",
            "last-modified": "2021-01-05 22:01:02"},
        {"name": "20210104.nc.tar.gz", "type": "file", "size": "0",
            "last-modified": "2021-01-06 01:02:03"}]}}


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


def test_candidate_profile_preserves_order_zero_size_unknown_units_and_false_authority():
    result = m.parse_directory_inventory(m._raw(_body()))
    assert [row["filename"] for row in result["entries"]] == ["20210105.nc.tar.gz", "20210104.nc.tar.gz"]
    assert result["total_advertised_size_numeric"] == 123456 and result["advertised_size_unit"] == "unknown"
    assert not result["advertised_archive_bytes_measured"]
    assert result["entries"][1]["advertised_size_numeric"] == 0
    assert result["entries"][0]["last_modified_timezone"] == "unknown"
    assert result["missing_directory_dates_do_not_establish_absent_filings"] is True
    assert all(value is False or type(value) is int and value == 0 for value in result["authority"].values())
    numeric = m._raw(_body()).replace(b'"size":"123456"', b'"size":123456')
    assert m.parse_directory_inventory(numeric)["entries"][0]["advertised_size_representation"] == "json-integer"


@pytest.mark.parametrize("fault",("root", "extra", "location", "parent", "empty", "unknown_item", "duplicate",
    "wrong_quarter", "bad_date", "bad_name", "directory", "negative_size", "float_size", "bool_size", "unknown_unit"))
def test_unqualified_shapes_refuse_without_partial_inventory(fault):
    body = _body(); directory = body["directory"]; item = directory["item"][0]
    if fault == "root": body = []
    elif fault == "extra": body["extra"] = 1
    elif fault == "location": directory["name"] += "/other"
    elif fault == "parent": directory["parent-dir"] = "/other"
    elif fault == "empty": directory["item"] = []
    elif fault == "unknown_item": item["unknown"] = True
    elif fault == "duplicate": directory["item"].append(dict(item))
    elif fault == "wrong_quarter": item["name"] = "20210401.nc.tar.gz"
    elif fault == "bad_date": item["name"] = "20210230.nc.tar.gz"
    elif fault == "bad_name": item["name"] = "../20210105.nc.tar.gz"
    elif fault == "directory": item["type"] = "dir"
    elif fault == "negative_size": item["size"] = "-1"
    elif fault == "float_size": item["size"] = 1.5
    elif fault == "bool_size": item["size"] = True
    else: item["size"] = "123 KB"
    with pytest.raises(m.FeedDirectoryError): m.parse_directory_inventory(m._raw(body))


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
        path=run/"response.bin";path.write_bytes(path.read_bytes().replace(b"123456",b"123457"))
    elif fault=="inventory":
        path=run/"inventory.json";value=_json(path);value["advertised_size_unit"]="bytes";path.write_bytes(m._raw(value))
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
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,dont_write_bytecode=1),
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
