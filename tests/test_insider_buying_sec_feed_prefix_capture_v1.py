"""Invented Range/front fixtures only; no retained inputs or live transport."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from types import SimpleNamespace
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_capture_v1 as m

CONTACT="invented@unit.test"


def _prefix(body=None):
    body=b"x"*70000 if body is None else body
    decoder=zlib.compressobj(level=0,wbits=31)
    return (decoder.compress(body)+decoder.flush())[:65536]


def _headers(**overrides):
    values={"Content-Length":"65536","Content-Range":"bytes 0-65535/1000000","Content-Encoding":"identity",
        "Content-Type":"application/gzip","Date":"unretained server value"}
    values.update(overrides)
    return tuple(values.items())


class _Response:
    def __init__(self,status=206,headers=None,raw=None):
        self.status=status;self.headers=_headers() if headers is None else headers
        self.raw=_prefix() if raw is None else raw;self.reads=[]
    def getheaders(self):return self.headers
    def read(self,count):self.reads.append(count);return self.raw


def _base(root):return root.joinpath(*m.ARTIFACT_PARTS)
def _path(root):return _base(root)/"runs"/m.AUDIT_ID


def _run(root,*,response=None,calls=None,contact=lambda:CONTACT,guard=lambda:None):
    response=_Response() if response is None else response
    def transport(url,headers,cap):
        assert (url,headers["Range"],cap)==(m.URL,m.RANGE,65536)
        assert CONTACT in headers["User-Agent"]
        assert (_path(root)/"reservation.json").is_file() and (_path(root)/"request-start.json").is_file()
        assert (_base(root)/"claims"/m._claim_name()).is_file()
        if calls is not None:calls.append(1)
        return m._observe_response(response)
    return m._invented(root=root,transport=transport,contact=contact,guard=guard)


def test_registration_is_small_different_unused_URL_no_carrier_authority():
    value=m.registration()
    assert value["url"].endswith("/20201008.nc.tar.gz") and value["source_ordinal"]==6
    assert value["advertised_size_text"]=="523023 KB" and value["required_prefix_bytes"]==65536
    assert value["Range"]=="bytes=0-65535" and value["URL_consumed_regardless_Range"] is True
    assert value["maximum_GETs"]==1 and value["full_roster_rederived"] is False
    assert m.URL not in {x.URL for x,_ in m.FAILED_SCOPES}
    value["authority"]["backtesting_ready"]=True
    assert m.registration()["authority"]["backtesting_ready"] is False
    assert m._claim_name()==hashlib.sha256(b"GET\0"+m.URL.encode()).hexdigest()+".json"


def test_exact_206_prefix_only_retention_and_independent_current_contact_readback(tmp_path):
    response=_Response();calls=[];result=_run(tmp_path,response=response,calls=calls)
    assert calls==[1] and response.reads==[65536]
    value=result["result"]
    assert value["prefix_retained"] is True and value["prefix_bytes"]==65536
    assert value["http_status"]==206 and value["declared_carrier_total_bytes"]==1000000
    assert value["total_is_declared_not_measured"] is True and value["whole_carrier_retained_or_verified"] is False
    assert (_path(tmp_path)/"prefix.bin").read_bytes()==response.raw
    headers=json.loads((_path(tmp_path)/"response-headers.json").read_bytes())
    assert "Date" not in dict(headers["headers"])
    replay=m._verify_files(tmp_path,result["complete_sha256"],"different@unit.test",fixture=True)
    assert replay["current_contact_prefix_rescreened"] is True
    assert replay["original_contact_screen_replayed"] is replay["original_current_contact_equality_attested"] is False
    assert replay["whole_carrier_replayed_or_verified"] is False and replay["result"]==value
    for path in _base(tmp_path).rglob("*"):
        if path.is_file():assert CONTACT.encode() not in path.read_bytes()


@pytest.mark.parametrize("status",[200,301,302,403,416,429,500])
def test_non206_is_never_read_and_never_falls_back(tmp_path,status):
    response=_Response(status=status,raw=CONTACT.encode());calls=[]
    result=_run(tmp_path,response=response,calls=calls)
    assert response.reads==[] and calls==[1]
    value=result["result"]
    assert value["http_status"]==status and value["body_read_attempted"] is False
    assert value["refusal"]=={"phase":"headers","code":"non206_body_unread"}
    assert value["prefix_bytes"] is value["prefix_sha256"] is value["inspection_sha256"] is None
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==value
    with pytest.raises(m.PrefixCaptureError,match="fresh_namespace_already_exists"):
        _run(tmp_path,response=response,calls=calls)
    assert calls==[1]


@pytest.mark.parametrize("headers,code",[
    ((("Content-Length","65536"),("Content-Range","bytes 1-65536/1000000")),"content_range_refused"),
    ((("Content-Length","65536"),("Content-Range","bytes 0-65535/*")),"content_range_refused"),
    ((("Content-Length","65536"),("Content-Range","bytes 0-65535/65536")),"content_range_refused"),
    ((("Content-Length","65536"),("Content-Range","bytes 0-65535/0")),"content_range_refused"),
    (_headers(**{"Content-Length":"65535"}),"content_length_refused"),
    (_headers(**{"Content-Length":"065536"}),"content_length_refused"),
    ((*_headers(),("content-length","65536")),"content_length_refused"),
    ((*_headers(),("content-range","bytes 0-65535/1000000")),"content_range_refused"),
    ((*_headers(),("Transfer-Encoding","chunked")),"transfer_encoding_refused"),
    (_headers(**{"Content-Encoding":"gzip"}),"content_encoding_refused"),
    (_headers(**{"Content-Type":"multipart/byteranges"}),"multipart_refused"),
    (_headers(**{"Content-Type":"multipart/byteranges; boundary=private"}),"multipart_refused"),
    ((*_headers(),("X-Injected","bad\r\nvalue")),"header_profile_refused"),
])
def test_malformed_or_multipart_206_refuses_before_body(headers,code):
    response=_Response(headers=headers);result=m._observe_response(response)
    assert response.reads==[] and result.body_read_attempted is False and result.body==b""
    assert result.refusal=={"phase":"headers","code":code}


@pytest.mark.parametrize("size",[0,1,65535,65537])
def test_exact_unit_size_not_a_lucky_short_or_oversized_prefix(tmp_path,size):
    response=_Response(raw=b"x"*size);result=_run(tmp_path,response=response)
    assert response.reads==[65536] and result["result"]["body_read_attempted"] is True
    assert result["result"]["refusal"]=={"phase":"body","code":"prefix_body_length_refused"}
    assert not (_path(tmp_path)/"prefix.bin").exists()


def test_core_phase_and_code_are_durable_without_hashing_refused_prefix(tmp_path,monkeypatch):
    raw=b"not a gzip"+bytes(65526);response=_Response(raw=raw)
    real=m._sha
    def no_refused_hash(value):
        assert value!=raw
        return real(value)
    monkeypatch.setattr(m,"_sha",no_refused_hash)
    result=_run(tmp_path,response=response)
    assert result["result"]["refusal"]=={"phase":"gzip-prefix","code":"invalid_gzip_prefix_or_observed_trailer"}
    assert result["result"]["prefix_retained"] is False
    assert not (_path(tmp_path)/"prefix.bin").exists()
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


@pytest.mark.parametrize("private",[CONTACT.encode(),b"invented%40unit.test",b"".join(f"\\u{ord(c):04x}".encode() for c in CONTACT)])
def test_private_raw_or_decoded_prefix_refusal_preserves_precise_code(tmp_path,private):
    result=_run(tmp_path,response=_Response(raw=_prefix(private+b"x"*70000)))
    assert result["result"]["refusal"]=={"phase":"privacy","code":"finite_prefix_screen_refused"}
    assert result["result"]["prefix_sha256"] is None and not (_path(tmp_path)/"prefix.bin").exists()


def test_response_header_privacy_before_hash_or_retention(tmp_path,monkeypatch):
    # A strictly required header cannot normally contain an address under its
    # exact grammar. Screening is nonetheless an independent retention guard.
    original=m._range_headers
    def supplied(status,pairs):
        safe,total=original(status,pairs)
        return (*safe,("X-Invented",CONTACT)),total
    monkeypatch.setattr(m,"_range_headers",supplied)
    result=_run(tmp_path)
    assert result["result"]["refusal"]=={"phase":"privacy","code":"header_privacy_refused"}
    assert not (_path(tmp_path)/"response-headers.json").exists()


@pytest.mark.parametrize("name",["complete.json","reservation.json","request-result.json","request-start.json","inspection.json","response-headers.json","prefix.bin"])
def test_strict_readback_exact_pins_ctime_and_inventory(tmp_path,name):
    result=_run(tmp_path);path=_path(tmp_path)/name;path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


def test_readback_refuses_extra_header_control_even_unchanged_complete(tmp_path):
    result=_run(tmp_path);path=_path(tmp_path)/"response-headers.json"
    value=json.loads(path.read_bytes());value["extra"]=True;path.write_bytes(m._raw(value))
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


def test_readback_new_current_contact_echo_cannot_be_hashed_or_accepted(tmp_path,monkeypatch):
    response=_Response(raw=_prefix(b"other@unit.test"+b"x"*70000));result=_run(tmp_path,response=response)
    assert result["result"]["prefix_retained"] is True
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],"other@unit.test",fixture=True)


def test_low_disk_refuses_before_namespace_or_private_contact(tmp_path,monkeypatch):
    monkeypatch.setattr(m.os,"fstatvfs",lambda fd:SimpleNamespace(f_bavail=1,f_frsize=1));calls=[]
    with pytest.raises(m.PrefixCaptureError,match="disk_reserve_refused"):
        _run(tmp_path,contact=lambda:calls.append(1))
    assert not calls and not _base(tmp_path).exists()


def test_stale_even_empty_root_is_not_reclaimed(tmp_path):
    _base(tmp_path).mkdir(parents=True);calls=[]
    with pytest.raises(m.PrefixCaptureError,match="fresh_namespace_already_exists"):
        _run(tmp_path,contact=lambda:calls.append(1))
    assert not calls


def test_guard_start_mismatch_stops_before_any_callback(tmp_path):
    calls=[]
    def guard():
        if (_path(tmp_path)/"request-start.json").exists():raise RuntimeError(CONTACT)
    with pytest.raises(m.PrefixCaptureError):_run(tmp_path,calls=calls,guard=guard)
    assert calls==[] and (_path(tmp_path)/"request-start.json").is_file()


def test_transport_errors_finite_consumed_no_retry(tmp_path):
    calls=[]
    def transport(*args):calls.append(1);raise TimeoutError(CONTACT)
    value=m._invented(root=tmp_path,transport=transport)
    assert calls==[1] and value["result"]["refusal"]=={"phase":"transport","code":"idle_timeout"}
    assert CONTACT not in json.dumps(value)
    assert m._verify_files(tmp_path,value["complete_sha256"],CONTACT,fixture=True)["result"]==value["result"]


def test_result_guard_keeps_types_and_false_authority():
    # Obtain a genuine failed result separately in file-backed tests; direct
    # parsing guard must reject arbitrary refusal phase/type assertions.
    for value in ({"phase":[],"code":"idle_timeout"},{"phase":"transport","code":CONTACT},
            {"phase":"transport","code":"idle_timeout","extra":False}):
        with pytest.raises(m.PrefixCaptureError):m._refusal_valid(value)


def test_native_command_retains_memory_publish_scope_and_all_initial_denials():
    joined=" ".join(m._command("inspect",{"source_only":True}))
    for value in ("-I","-S","-B",m.EMPTY_CACHE_PREFIX,"deny network*","deny process-fork","deny file-write*","/usr/bin/security","publish=True"):
        assert value in joined
    assert CONTACT not in joined


def test_false_or_mutated_dispatch_cannot_open_socket(monkeypatch):
    calls=[];context=m._Dispatch(m._TOKEN,None,{"invented":True},lambda:None,lambda:None,{"Range":m.RANGE})
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**kw:calls.append(1))
    with pytest.raises(m.PrefixCaptureError,match="trusted_activation_required"):m._transport(context)
    assert not calls and context.attempted is False


def test_unknown_CLI_tokens_do_not_echo_private_text(capsys):
    assert m.main(["--unknown-"+CONTACT])==2
    out=capsys.readouterr();assert CONTACT not in out.out+out.err and not out.err
    assert json.loads(out.out)["code"]=="private_arguments_refused"


@pytest.mark.parametrize("body,valid",[(b"pass\n",True),(b"break\n",False)])
def test_native_source_memory_compile_rechecks_exact_bytes_without_bytecode(monkeypatch,body,valid):
    calls=[]
    class Chain:
        fd=123
        def __init__(self,*args):calls.append("open")
        def recheck(self):calls.append("recheck")
        def close(self):calls.append("closed")
    monkeypatch.setattr(m.custody,"_Chain",Chain)
    monkeypatch.setattr(m.custody,"_read_leaf",lambda *a,**kw:body)
    identity={"source_sha256":{"research/invented.py":m._sha(body)}}
    if valid:m._compile_sources(identity);assert calls==["open","recheck","closed"]
    else:
        with pytest.raises(m.PrefixCaptureError,match="source_changed"):m._compile_sources(identity)
        assert calls==["open","closed"]


def test_input_cleanup_closes_FD_even_if_unlock_itself_fails(monkeypatch):
    held=m._Inputs.__new__(m._Inputs);held.locks=[(123,None,None)];held.folders=[];closed=[]
    def unlock(*args):raise OSError("invented unlock failure")
    monkeypatch.setattr(m.fcntl,"flock",unlock);monkeypatch.setattr(m.os,"close",closed.append)
    with pytest.raises(m.PrefixCaptureError,match="cleanup_refused"):held.close()
    assert closed==[123] and held.locks==[]
