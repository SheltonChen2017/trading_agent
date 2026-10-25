"""Invented historical-reference metadata only; native denial is mandatory."""
from copy import deepcopy
from email.message import Message
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: lane custody is macOS/POSIX", allow_module_level=True)

from research import insider_buying_pilot_massive_reference_probe as m


HEAD="a"*40
TOKEN="invented_massive_reference_key_123+/!"


def _credential(fixture=True):return m.KeychainCredential("massive",TOKEN,fixture)


def _body():
    return {"status":"OK","request_id":"invented_request_id","count":1,"results":[{
        "ticker":"A","market":"stocks","locale":"us","active":True,"cik":"9999999",
        "name":"Invented Issuer","type":"CS","primary_exchange":"XNYS",
        "share_class_figi":"BBG000C2V3D6","composite_figi":"BBG000C2V3D6",
        "currency_name":"usd","last_updated_utc":"2020-01-02T00:00:00Z"}]}


def _identity(root):
    sources={"invented.py":"b"*64}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":HEAD,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


def _run(root,*,reader=None,transport=None,identity=None):
    return m.run_probe(HEAD,root=root,identity=identity or (lambda head,root:_identity(root)),
        credential_reader=reader or (lambda provider:_credential()),
        transport=transport or (lambda *_:m.date_probe.ProviderMetadataResponse(200,m._raw(_body()),True)),
        clock=lambda:"2026-10-24T00:00:00Z")


def _output(root):return root.joinpath(*m.OUTPUT_PARTS,m.AUDIT_ID)
def _snapshot(root):return {str(path.relative_to(root)):path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_fixed_one_call_private_custody_metadata_only_and_no_secret(tmp_path):
    calls=[]
    def reader(provider):
        assert provider=="massive" and (_output(tmp_path)/"credential-read-started.json").is_file()
        calls.append("credential");return _credential()
    def transport(url,credential):
        assert url==m.URL and TOKEN not in url and credential==_credential()
        assert (_output(tmp_path)/"01-reference-started.json").is_file()
        calls.append("GET");return m.date_probe.ProviderMetadataResponse(200,m._raw(_body()),True)
    result=_run(tmp_path,reader=reader,transport=transport)
    assert calls==["credential","GET"] and result["transport_invocation_count"]==1
    assert result["status"]=="completed-reference-metadata-probe" and result["fixture_only"] is True
    assert result["metadata"]["requested_asof_date"]=="2020-01-02"
    assert result["metadata"]["numeric_financial_fields_interpreted"] is False
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"]==result["qc_jobs"]==result["backtests"]==0
    assert _output(tmp_path).stat().st_mode&0o777==0o700
    for name,digest in result["published_leaf_sha256"].items():
        leaf=_output(tmp_path)/name
        assert m._sha(leaf.read_bytes())==digest and leaf.stat().st_mode&0o777==0o600 and leaf.stat().st_nlink==1
    assert json.loads((_output(tmp_path)/"complete.json").read_bytes())==result
    assert TOKEN.encode() not in b"".join(_snapshot(tmp_path).values())


@pytest.mark.parametrize("mutation",["unknown-financial","unknown-financial-string","numeric-cik","float-count","string-count","bool-count","zero-count",
    "two-results","next-page","status-error","missing-class","other-ticker","inactive","wrong-asof-fields","bad-time","unknown-top"])
def test_source_financial_or_nonfixed_reference_refuses_without_body_hash_or_retention(tmp_path,mutation):
    body=_body();row=body["results"][0]
    if mutation=="unknown-financial":row["market_cap"]=1.23456789e200
    elif mutation=="unknown-financial-string":row["market_cap"]="123.456"
    elif mutation=="numeric-cik":row["cik"]=1090872
    elif mutation=="float-count":body["count"]=1.0
    elif mutation=="string-count":body["count"]="1"
    elif mutation=="bool-count":body["count"]=True
    elif mutation=="zero-count":body["count"]=0;body["results"]=[]
    elif mutation=="two-results":body["results"].append(deepcopy(row))
    elif mutation=="next-page":body["next_url"]="https://api.massive.com/v3/reference/tickers?cursor=private"
    elif mutation=="status-error":body["status"]="NOT_AUTHORIZED"
    elif mutation=="missing-class":row.pop("share_class_figi")
    elif mutation=="other-ticker":row["ticker"]="AA"
    elif mutation=="inactive":row["active"]=False
    elif mutation=="wrong-asof-fields":row["type"]="ADRC"
    elif mutation=="bad-time":row["last_updated_utc"]="2020-01-02"
    else:body["financial_result"]=55
    result=_run(tmp_path,transport=lambda *_:m.date_probe.ProviderMetadataResponse(200,m._raw(body),True))
    assert result["metadata"] is None and result["status"]=="stopped-reference-metadata-probe"
    assert not (_output(tmp_path)/"01-reference-response.json").exists()
    completed=json.loads((_output(tmp_path)/"01-reference-completed.json").read_bytes())
    assert completed["body_sha256"] is completed["body_size_bytes"] is None
    assert completed["untrusted_error_body_hashed_or_retained"] is False


def test_numeric_lexemes_are_never_financial_numbers():
    observed=m._json(b'{"count":1,"opaque":1.23456789e99999}')
    assert type(observed["count"]) is m._IntegerLexeme and observed["count"]=="1"
    assert type(observed["opaque"]) is m._FloatLexeme and observed["opaque"]=="1.23456789e99999"


@pytest.mark.parametrize("kind",["literal","percent","double-percent","json-unicode"])
def test_decoded_or_encoded_credential_echo_precedes_source_hash(kind,monkeypatch):
    body=_body();body["results"][0]["name"]=TOKEN if kind=="literal" else quote(TOKEN,safe="")
    if kind=="double-percent":body["results"][0]["name"]=quote(body["results"][0]["name"],safe="")
    raw=m._raw(body)
    if kind=="json-unicode":
        escaped='"'+''.join("\\u%04x"%ord(char) for char in TOKEN)+'"'
        raw=raw.replace(json.dumps(body["results"][0]["name"]).encode(),escaped.encode())
    monkeypatch.setattr(m,"_sha",lambda *_:pytest.fail("credential echo must not be hashed"))
    with pytest.raises(m.MassiveReferenceProbeError,match="credential_echo_refused"):m._projection(raw,_credential())


@pytest.mark.parametrize("raw",[b'{"count":1,"count":1}',b'{"count":NaN}',b"\xff",b"["*25+b"0"+b"]"*25,b"x"*262145])
def test_malformed_duplicate_deep_or_oversized_source_is_fixed_refusal(raw):
    with pytest.raises(m.MassiveReferenceProbeError):m._projection(raw,_credential())


@pytest.mark.parametrize("status",[None,302,401,403,429,500])
def test_non200_body_never_interpreted_or_retained(tmp_path,monkeypatch,status):
    monkeypatch.setattr(m,"_projection",lambda *_:pytest.fail("no source decode"))
    result=_run(tmp_path,transport=lambda *_:m.date_probe.ProviderMetadataResponse(status,TOKEN.encode(),False))
    assert result["http_status"]==status and result["metadata"] is None and result["transport_invocation_count"]==1
    assert TOKEN.encode() not in b"".join(_snapshot(tmp_path).values())


def test_consumed_namespace_never_repeats_credential_or_transport(tmp_path):
    _run(tmp_path);before=_snapshot(tmp_path)
    with pytest.raises(m.MassiveReferenceProbeError):
        _run(tmp_path,reader=lambda *_:pytest.fail("duplicate credential"),transport=lambda *_:pytest.fail("duplicate GET"))
    assert _snapshot(tmp_path)==before


@pytest.mark.parametrize("credential",[None,m.KeychainCredential("eodhd",TOKEN,True),
    m.KeychainCredential("massive",TOKEN,False),m.KeychainCredential("massive","demo",True),
    m.KeychainCredential("massive","bad\nheader",True)])
def test_bad_credential_consumes_scope_without_dispatch(tmp_path,credential):
    result=_run(tmp_path,reader=lambda *_:credential,transport=lambda *_:pytest.fail("credential refused"))
    assert result["transport_invocation_count"]==0 and result["credential_read_observed"] is False


@pytest.mark.parametrize("root",[m.LANE_ROOT,m.LANE_ROOT.parent,m.LANE_ROOT/"fixture",Path("/")])
def test_fixture_scope_never_reaches_real_lane_or_ancestor(root):
    with pytest.raises(m.MassiveReferenceProbeError,match="invented_outside_lane_callbacks_required"):_run(root)


def test_fixture_cannot_choose_real_callback(monkeypatch,tmp_path):
    monkeypatch.setattr(m.request,"build_opener",lambda *_:pytest.fail("must not open"))
    for kwargs in ({"credential_reader":m.read_keychain_credential,"transport":lambda *_:None},
        {"credential_reader":lambda *_:None,"transport":m._default_transport}):
        with pytest.raises(m.MassiveReferenceProbeError,match="invented_outside_lane_callbacks_required"):
            m.run_probe(HEAD,root=tmp_path,identity=lambda head,root:_identity(root),**kwargs)


@pytest.mark.parametrize("mutation",["content","mode","extra","restored-mtime"])
def test_changed_custody_refuses_before_response_projection(tmp_path,monkeypatch,mutation):
    def transport(*_):
        leaf=_output(tmp_path)/"reservation.json";before=leaf.stat()
        if mutation=="content":leaf.write_bytes(b"{}")
        elif mutation=="mode":leaf.chmod(0o644)
        elif mutation=="extra":(_output(tmp_path)/"foreign").write_bytes(b"unsafe")
        else:
            raw=leaf.read_bytes();leaf.write_bytes(raw.replace(b'"maximum_attempts":1',b'"maximum_attempts":2'))
            os.utime(leaf,ns=(before.st_atime_ns,before.st_mtime_ns))
        return m.date_probe.ProviderMetadataResponse(200,m._raw(_body()),True)
    monkeypatch.setattr(m,"_projection",lambda *_:pytest.fail("changed custody source decode"))
    with pytest.raises(m.MassiveReferenceProbeError):_run(tmp_path,transport=transport)


def _default_context(monkeypatch):
    context=object.__new__(m._Context);context.root=m.LANE_ROOT;context.fixture=False
    context.baseline=_identity(m.LANE_ROOT);context.directory=SimpleNamespace(fd=42);context.check=lambda:None
    context.published={name:"e"*64 for name in ("reservation.json","credential-read-started.json",
        "credential-read-completed.json","01-reference-started.json")}
    leaves={"reservation.json":m._reservation(context.baseline,False),
        "credential-read-started.json":{"schema":m.SCHEMA,"maximum_credential_reads":1,"reservation_sha256":"e"*64},
        "credential-read-completed.json":{"schema":m.SCHEMA,"fixture_only":False,"started_sha256":"e"*64,
            "credential_read_observed":True,"disposition":"configured-keychain-credential-read"},
        "01-reference-started.json":m._started("e"*64)}
    monkeypatch.setattr(m.publication,"_leaf",lambda directory,name,cap:(m._raw(leaves[name]),()))
    return context,leaves


class _Stream:
    def __init__(self,status=200,body=None,headers=(),url=None):
        self.status=status;self.body=io.BytesIO(m._raw(_body()) if body is None else body)
        self.headers=Message();self.reads=0;self.closed=False;self.url=m.URL if url is None else url
        for key,value in headers:self.headers[key]=value
    def getcode(self):return self.status
    def geturl(self):return self.url
    def read(self,count):self.reads+=1;return self.body.read(count)
    def close(self):self.closed=True


@pytest.mark.parametrize("status",[200,302,401,403])
def test_real_transport_fixed_bearer_header_no_query_secret_and_non200_no_read(monkeypatch,status):
    context,_=_default_context(monkeypatch);stream=_Stream(status);calls=[];handlers=[]
    class Opener:
        def open(self,item,timeout):calls.append((item,timeout));return stream
    monkeypatch.setattr(m.request,"build_opener",lambda *args:(handlers.extend(args),Opener())[1])
    result=m._default_transport(m.URL,_credential(False),context=context)
    assert len(calls)==1 and calls[0][1]==15 and stream.closed
    item=calls[0][0]
    assert item.full_url==m.URL and TOKEN not in item.full_url
    assert item.get_header("Authorization")=="Bearer "+TOKEN and item.get_method()=="GET"
    assert type(handlers[0]) is m.request.ProxyHandler and handlers[0].proxies=={}
    assert type(handlers[1]) is m.date_probe._DenyRedirect and type(handlers[2]) is m.request.HTTPSHandler
    assert (stream.reads>0) is (status==200)
    if status!=200:assert result.body==b""


@pytest.mark.parametrize("failure",["context","fixture","url","reservation","read-start","missing-start","last-check"])
def test_real_transport_bad_context_or_seals_refuse_before_open(monkeypatch,failure):
    context,leaves=_default_context(monkeypatch);checks=[]
    monkeypatch.setattr(m.request,"build_opener",lambda *_:SimpleNamespace(open=lambda *_a,**_k:pytest.fail("must not open")))
    url=m.URL
    if failure=="context":context.check=lambda:m._need(False,"context_refused")
    elif failure=="fixture":context.fixture=True
    elif failure=="url":url+="&ticker=AA"
    elif failure=="reservation":leaves["reservation.json"]["request"]["date"]="2021-01-01"
    elif failure=="read-start":leaves["credential-read-started.json"]["maximum_credential_reads"]=2
    elif failure=="missing-start":context.published.pop("01-reference-started.json")
    else:
        def changed():
            checks.append(1)
            if len(checks)==3:raise m.MassiveReferenceProbeError("last_context_refused")
        context.check=changed
    with pytest.raises(m.MassiveReferenceProbeError):
        m._default_transport(url,_credential(False),context=context)


@pytest.mark.parametrize("headers,code",[
    ([("Content-Length","1"),("Content-Length","1")],"invalid-content-length"),
    ([("Content-Length","262145")],"oversized-response"),([("Content-Encoding","gzip")],"unsupported-content-encoding"),
    ([("Transfer-Encoding","chunked"),("Content-Length","1")],"partial-read"),
    ([("Content-Length","999999")],"oversized-response"),([("Content-Length","999")],"truncated-response")])
def test_http_framing_refusals_discard_body(headers,code):
    observed=m._read_bounded(_Stream(headers=headers),200)
    assert observed.disposition==code and observed.body==b"" and observed.body_complete is False


def test_invalid_response_origin_refuses_without_read(monkeypatch):
    context,_=_default_context(monkeypatch);stream=_Stream(url=m.URL+"&foreign=1")
    monkeypatch.setattr(m.request,"build_opener",lambda *_:SimpleNamespace(open=lambda *_a,**_k:stream))
    result=m._default_transport(m.URL,_credential(False),context=context)
    assert result.disposition=="response-origin-mismatch" and stream.reads==0


def test_deadline_during_last_context_check_is_typed_timeout_without_dispatch(monkeypatch):
    context,_=_default_context(monkeypatch);checks=[]
    monkeypatch.setattr(m.request,"build_opener",lambda *_:SimpleNamespace(open=lambda *_a,**_k:pytest.fail("no HTTP dispatch")))
    def checking():
        checks.append(1)
        if len(checks)==3:raise m.date_probe.PriceDateProbeError("transport-timeout")
    context.check=checking
    observed=m._default_transport(m.URL,_credential(False),context=context)
    assert observed.status is None and observed.body==b"" and observed.body_complete is False
    assert observed.disposition=="transport-timeout" and len(checks)==3


def test_clean_identity_changes_before_dispatch_refuse(tmp_path):
    def identity(head,root):
        value=_identity(root)
        if (_output(root)/"01-reference-started.json").exists():value["head"]="b"*40
        return value
    with pytest.raises(m.MassiveReferenceProbeError):
        _run(tmp_path,identity=identity,transport=lambda *_:pytest.fail("changed identity dispatch"))


def test_isolated_interpreter_guard_precedes_source_identity(monkeypatch):
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_user_site=1,no_site=0,dont_write_bytecode=1),
        pycache_prefix=m.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.custody,"_identity",lambda *_:pytest.fail("unsafe interpreter Git access"))
    with pytest.raises(m.MassiveReferenceProbeError,match="isolated_source_interpreter_required"):m._identity(HEAD)


def test_cleanup_drains_all_and_preserves_primary():
    context=object.__new__(m._Context);calls=[]
    class Bad:
        def close(self):calls.append("closed");raise OSError("PRIVATE")
    context.directory=context.parent=Bad()
    with pytest.raises(m.MassiveReferenceProbeError,match="primary_refused"):
        try:raise m.MassiveReferenceProbeError("primary_refused")
        finally:context.close()
    assert calls==["closed","closed"]
    context.close()


def test_stopped_cli_is_exit2_and_prints_no_provider_body(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_probe",lambda *_:{"status":"stopped-reference-metadata-probe","http_status":403,
        "disposition":"http_refused","transport_invocation_count":1,"research_looks":0,"qc_jobs":0,"backtests":0,
        "metadata":{"private":TOKEN}})
    assert m.main(["--expected-head",HEAD])==2
    assert TOKEN not in capsys.readouterr().out
