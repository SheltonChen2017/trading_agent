"""Synthetic exact-key matrix; never production artifacts/credentials/network."""
import copy
import hashlib
import io
import json
import socket
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from scripts import diagnose_arv2_newrule_properties_matrix as d
from scripts import diagnose_arv2_newrule_listing_shape as listing
from scripts import arv2_newrule_storage_recovery_v2 as recovery
from scripts import diagnose_arv2_newrule_object_metadata as prior
from scripts import diagnose_arv2_newrule_upload as markers
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old

HEAD,SHA,ORG="a"*40,"b"*64,"f"*32
REAL_DIRECTORY,REAL_CLIENT=old._Directory,old.QuantConnectClient
REAL_PREFLIGHT=d._preflight


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    violations=[]
    def forbidden(*_a,**_k): violations.append("boundary"); pytest.fail("operational access forbidden")
    monkeypatch.setattr(REAL_DIRECTORY,"__init__",forbidden)
    monkeypatch.setattr(REAL_CLIENT,"__init__",forbidden)
    for owner,names in ((old,("_Directory","_client","_input","load_family","prepare_family","upload_inputs","capacity_once","begin_attempt","_session")),
        (old.coverage,("production_client",)),(old.october,("load_october_order_input_package",)),
        (old.compact,("load_accepted_risk_preliminary_package",)),
        (recovery,("claim","recover","require_admission")),(prior,("run","_run","_transport")),
        (markers,("run","_run","_census")),(listing,("run","_run","_transport")),(d.frozen,("run","_operation")),
        (urllib.request.OpenerDirector,("open",)),(socket,("create_connection","getaddrinfo")),
        (socket.socket,("connect","connect_ex")),(old.http.client.HTTPConnection,("request","connect")),
        (old.http.client.HTTPSConnection,("connect",))):
        for name in names: monkeypatch.setattr(owner,name,forbidden)
    yield violations
    assert violations==[],"swallowed operational boundary"


class Directory:
    def __init__(self): self.data,self.events,self.closed={ },[],False
    def names(self): return tuple(self.data)
    def write(self,name,value):
        assert name.startswith("properties-matrix-diagnostic-v1-")
        self.events.append(("write",name))
        if name in self.data: raise FileExistsError()
        self.data[name]=copy.deepcopy(value)
    def read(self,name): self.events.append(("read",name)); return copy.deepcopy(self.data[name])
    def verify(self): self.events.append(("verify",None))
    def __exit__(self,*_): self.closed=True


class Response:
    def __init__(self,code,raw): self.code,self.raw,self.closed,self.reads=code,raw,False,[]
    def geturl(self): return old.API_BASE+"/object/properties"
    def read(self,size): self.reads.append(size); return self.raw
    def close(self): self.closed=True


def fixture(monkeypatch):
    directory,calls,events=Directory(),[],[]
    payloads=tuple(("PRIVATE-PAYLOAD-"+str(i)).encode() for i in range(6))
    rows=[[listing.PREFIX+"/PRIVATE-KEY-"+str(i),hashlib.sha256(raw).hexdigest(),len(raw),i==5] for i,raw in enumerate(payloads)]
    values=[dict(success=True,metadata=dict(key=row[0],size=row[2],
        md5=hashlib.md5(payloads[i],usedforsecurity=False).hexdigest(),preview="PRIVATE-PREVIEW")) for i,row in enumerate(rows)]
    responses=[Response(200,json.dumps(value).encode()) for value in values]
    monkeypatch.setattr(d,"_preflight",lambda *_:events.append("preflight"))
    monkeypatch.setattr(d,"_dependencies",lambda:(listing,(recovery,prior,markers,old)))
    monkeypatch.setattr(old,"_Directory",lambda:directory)
    monkeypatch.setattr(d,"_retained",lambda *_:(rows,ORG))
    def load(*_): events.append("input"); return object(),payloads
    monkeypatch.setattr(d,"_load_payloads",load)
    monkeypatch.setattr(d,"_package_payloads",lambda *_:payloads)
    def client(): events.append("credentials"); return SimpleNamespace(_credentials=object(),_clock=lambda:100)
    monkeypatch.setattr(old,"_client",client)
    monkeypatch.setattr(old,"_safe_environment",lambda:None)
    monkeypatch.setattr(old,"build_auth_headers",lambda *_:{"Authorization":"PRIVATE-CREDENTIAL"})
    class Opener:
        def open(self,request,timeout):
            index=len(calls); calls.append((request,timeout)); return responses[index]
    monkeypatch.setattr(d,"_opener",lambda:Opener())
    return SimpleNamespace(directory=directory,calls=calls,events=events,rows=rows,payloads=payloads,values=values,responses=responses)


def execute(): return d._run(HEAD,SHA,time.monotonic()+240)


def test_six_exact_independent_properties_and_no_admission(monkeypatch):
    f=fixture(monkeypatch); result,code=execute(); report=result["report"]
    assert code==0 and report["matrix_completed"] is True and report["attempted_request_count"]==6
    assert f.events==["preflight","input","credentials","preflight"] and f.directory.closed
    assert f.directory.events[0]==("write",d.CLAIM)
    for index,((request,timeout),entry) in enumerate(zip(f.calls,report["observations"])):
        assert request.full_url==old.API_BASE+"/object/properties" and request.get_method()=="POST" and timeout<=30
        assert json.loads(request.data)=={"organizationId":ORG,"key":f.rows[index][0]}
        assert entry["index"]==index and entry["attempted"] is True and entry["http_status"]==200
        assert all(entry["observation"][name] is True for name in ("key_matches","size_matches","md5_matches"))
        stem=f"properties-matrix-diagnostic-v1-request-{index:02d}"
        assert entry["request_sha256"]==hashlib.sha256(request.data).hexdigest()==f.directory.data[stem+"-intent.json"]["request_sha256"]
        assert f.directory.data[stem+"-observed.json"]["request_sha256"]==entry["request_sha256"]
    assert len(f.directory.data)==14 and all(name.startswith("properties-matrix-diagnostic-v1-") for name in f.directory.data)
    assert all(report[name] is value for name,value in d.FLAGS.items())
    assert "PRIVATE" not in json.dumps(result) and ORG not in json.dumps(result)
    raw=d.helpers.canonical_json_bytes(report)
    assert result["report_bytes"]==len(raw) and result["report_sha256"]==hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("case",["api_false","null","missing","key_mismatch","size_mismatch","md5_mismatch","bad_md5","permission"])
def test_valid_finite_refusals_nulls_and_mismatches_continue_without_absence(monkeypatch,case):
    f=fixture(monkeypatch); value=f.values[0]
    if case=="api_false": value={"success":False,"errors":["PRIVATE-UNKNOWN"]}
    elif case=="null": value["metadata"]=None
    elif case=="missing": del value["metadata"]
    elif case=="key_mismatch": value["metadata"]["key"]="PRIVATE-OTHER"
    elif case=="size_mismatch": value["metadata"]["size"]+=1
    elif case=="md5_mismatch": value["metadata"]["md5"]="0"*32
    elif case=="bad_md5": value["metadata"]["md5"]="PRIVATE-NOT-MD5"
    elif case=="permission": value={"success":False,"errors":["permission denied"]}
    f.responses[0].raw=json.dumps(value).encode()
    result,code=execute(); report=result["report"]
    assert code==0 and len(f.calls)==6 and report["absence_established"] is False
    if case=="permission": assert report["observations"][0]["observation"]["error_category"]=="permission"
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("case",["top","success_type","extra","metadata_type","missing_field","size_bool","invalid_errors",
    "duplicate","nonfinite","exponent","encoding","trailing","transport","timeout","redirect","overflow"])
def test_ambiguity_stops_matrix_retaining_finite_partial_evidence(monkeypatch,case):
    f=fixture(monkeypatch); value=f.values[1]
    if case=="top": value=[]
    elif case=="success_type": value["success"]=1
    elif case=="extra": value["PRIVATE"]=True
    elif case=="metadata_type": value["metadata"]=[]
    elif case=="missing_field": del value["metadata"]["key"]
    elif case=="size_bool": value["metadata"]["size"]=False
    elif case=="invalid_errors": value["errors"]=[{}]
    f.responses[1].raw=json.dumps(value).encode()
    if case=="duplicate": f.responses[1].raw=b'{"success":true,"success":false}'
    elif case=="nonfinite": f.responses[1].raw=b'{"success":true,"metadata":NaN}'
    elif case=="exponent": f.responses[1].raw=b'{"success":true,"metadata":1e400}'
    elif case=="encoding": f.responses[1].raw=b'\xff'
    elif case=="trailing": f.responses[1].raw=b'{}{}'
    elif case=="overflow": f.responses[1].raw=b'x'*(d.MAX_RESPONSE_BYTES+1)
    elif case=="redirect": f.responses[1].geturl=lambda:old.API_BASE+"/object/set"
    elif case in {"transport","timeout"}:
        def opener(request,timeout):
            index=len(f.calls); f.calls.append((request,timeout))
            if index==1: raise (TimeoutError("PRIVATE") if case=="timeout" else urllib.error.URLError("PRIVATE"))
            return f.responses[index]
        monkeypatch.setattr(d,"_opener",lambda:SimpleNamespace(open=opener))
    result,code=execute(); report=result["report"]
    assert code==2 and len(f.calls)==2 and report["attempted_request_count"]==2 and report["matrix_completed"] is False
    assert len(report["observations"])==2 and "PRIVATE" not in json.dumps(result)
    if case in {"duplicate","trailing"}: assert report["failure_code"]=="response_json"
    if case in {"nonfinite","exponent"}: assert report["failure_code"]=="response_nonfinite"
    if case=="encoding": assert report["failure_code"]=="response_encoding"
    if case=="invalid_errors": assert report["failure_code"]=="response_schema"


def test_http_error_body_never_read_or_followed(monkeypatch):
    f=fixture(monkeypatch)
    class Body(io.BytesIO):
        def read(self,*_): pytest.fail("non2xx body forbidden")
    body=Body(b"PRIVATE")
    error=urllib.error.HTTPError(old.API_BASE+"/object/properties",404,"PRIVATE",{},body)
    def opener(request,timeout):
        index=len(f.calls); f.calls.append((request,timeout))
        if index==0: raise error
        return f.responses[index]
    monkeypatch.setattr(d,"_opener",lambda:SimpleNamespace(open=opener))
    result,code=execute()
    assert code==2 and len(f.calls)==1 and body.closed and result["report"]["observations"][0]["http_status"]==404
    assert result["report"]["failure_code"]=="http_status_stop"
    assert result["report"]["absence_established"] is False


@pytest.mark.parametrize("status",[301,401,403,404,429,500,503])
def test_all_non2xx_stop_before_later_intent_without_reading_body(monkeypatch,status):
    f=fixture(monkeypatch); f.responses[1].code=status
    result,code=execute(); report=result["report"]
    assert code==2 and report["failure_code"]=="http_status_stop" and len(f.calls)==2
    assert report["observations"][1]["http_status"]==status and f.responses[1].reads==[]
    assert not any("request-02" in name for name in f.directory.data)


def test_success_with_errors_stops_as_contradictory_response(monkeypatch):
    f=fixture(monkeypatch); value=f.values[1]; value["errors"]=["quota exceeded"]
    f.responses[1].raw=json.dumps(value).encode()
    result,code=execute(); report=result["report"]
    assert code==2 and report["failure_code"]=="response_contradiction" and len(f.calls)==2
    assert report["observations"][1]["observation"]["success_with_nonempty_errors"] is True
    assert not any("request-02" in name for name in f.directory.data)


def test_proxy_empty_redirect_refused(monkeypatch):
    captured=[]
    monkeypatch.setattr(urllib.request,"build_opener",lambda *args:captured.extend(args))
    d._opener()
    assert captured[0].proxies=={} and captured[1].redirect_request(None,None,302,"x",{},"https://unused.invalid") is None


def test_actual_pytest_context_refuses_before_any_directory_or_dependency_import(monkeypatch):
    monkeypatch.setattr(d,"_dependencies",lambda:pytest.fail("dependency imports forbidden"))
    result,code=execute()
    assert code==2 and not result["report_published"] and result["report"]["failure_code"]=="operational_test_context"


@pytest.mark.parametrize("stage",["preflight","claim","retained","input","credentials","verify","close","readback"])
def test_claim_before_private_reads_and_no_normal_output_on_late_failure(monkeypatch,stage,capsys):
    f=fixture(monkeypatch)
    if stage=="preflight": monkeypatch.setattr(d,"_preflight",lambda *_:(_ for _ in ()).throw(d.DiagnosticRefusal("source_binding")))
    elif stage=="claim": f.directory.data[d.CLAIM]={}
    elif stage=="retained": monkeypatch.setattr(d,"_retained",lambda *_:(_ for _ in ()).throw(d.DiagnosticRefusal("listing_report_pin")))
    elif stage=="input": monkeypatch.setattr(d,"_load_payloads",lambda *_:(_ for _ in ()).throw(d.DiagnosticRefusal("inventory_binding")))
    elif stage=="credentials": monkeypatch.setattr(old,"_client",lambda:(_ for _ in ()).throw(PermissionError("PRIVATE")))
    elif stage in {"verify","close"}: setattr(f.directory,"verify" if stage=="verify" else "__exit__",lambda *_:(_ for _ in ()).throw(d.DiagnosticRefusal("publication_ambiguous")))
    else:
        original=f.directory.read
        def read(name):
            result=original(name)
            if name==d.REPORT: result["matrix_completed"]=False
            return result
        f.directory.read=read
    assert d.run(SimpleNamespace(expected_head=HEAD,caller_sha256=SHA))==2
    result=json.loads(capsys.readouterr().out)
    assert "PRIVATE" not in json.dumps(result)
    if stage in {"verify","close","readback"}: assert "report_sha256" not in result
    else: assert not f.calls
    if stage in {"preflight","claim","retained"}: assert "input" not in f.events
    if stage in {"preflight","claim","retained","input"}: assert "credentials" not in f.events


@pytest.mark.parametrize("which",["directory","client","socket","old_operation"])
def test_independent_captured_guards_survive_aliases(isolation,which):
    callbacks={"directory":lambda:REAL_DIRECTORY(),"client":lambda:REAL_CLIENT(),
        "socket":lambda:socket.create_connection(("unused.invalid",443)),"old_operation":lambda:recovery.claim(HEAD,SHA)}
    with pytest.raises(pytest.fail.Exception): callbacks[which]()
    assert isolation==["boundary"]; isolation.clear()


def test_package_iterator_authentication_and_byte_binding_without_familyplan(monkeypatch):
    f=fixture(monkeypatch)
    descriptors=[SimpleNamespace(object_store_key=row[0],content_sha256=row[1],byte_count=row[2],activation_manifest=row[3]) for row in f.rows]
    monkeypatch.setattr(old,"_input",lambda _:object())
    monkeypatch.setattr(old.compact,"iter_accepted_risk_preliminary_upload_objects",lambda _:iter(zip(descriptors,f.payloads)))
    # fixture bypass is replaced by the real pure function captured from source module below.
    assert REAL_PACKAGE(object(),old,f.rows)==f.payloads
    descriptors[0].content_sha256="0"*64
    with pytest.raises(d.DiagnosticRefusal,match="inventory_binding"): REAL_PACKAGE(object(),old,f.rows)


REAL_PACKAGE=d._package_payloads
REAL_LOAD=d._load_payloads


def test_loader_binds_only_frozen_package_lineage_and_no_familyplan(monkeypatch):
    calls=[]; value=object(); payloads=(b"synthetic",)
    def load(path,**kwargs): calls.append((path,kwargs)); return value
    monkeypatch.setattr(old.october,"load_october_order_input_package",load)
    monkeypatch.setattr(d,"_package_payloads",lambda passed,submission,rows:payloads if passed is value and submission is old else None)
    assert REAL_LOAD(old,[])==(value,payloads)
    assert calls==[(d.frozen.PACKAGE,dict(expected_package_sha256=d.frozen.PACKAGE_SHA256,
        lineage_path=d.frozen.LINEAGE,expected_lineage_sha256=d.frozen.LINEAGE_SHA256))]


def listing_fixture(monkeypatch):
    directory=Directory()
    binding={"schema":listing.SCHEMA,"profile_sha256":d.LISTING_PROFILE_SHA256,
        "family_sha256":d.FAMILY_SHA256,"expected_head":d.LISTING_HEAD,"caller_sha256":d.LISTING_SHA256,
        "attempt_consumed":True}
    directory.data[listing.CLAIM]=dict(binding)
    directory.data[listing.START]={"schema":listing.SCHEMA,"profile_sha256":d.LISTING_PROFILE_SHA256,
        "family_sha256":d.FAMILY_SHA256,"endpoint":"object/list","request_sha256":listing.PRIOR_REQUEST_SHA256}
    observation=listing._observation(json.dumps(dict(success=True,path=listing.PREFIX,objects=None,
        page=None,totalPages=None,objectStorageUsed=10)).encode(),[])
    directory.data[listing.REPORT]=dict(binding,prior_report_sha256=listing.PRIOR_REPORT_SHA256,
        started_at="2026-10-14T02:15:47+00:00",finished_at="2026-10-14T02:15:48+00:00",
        stage="diagnostic_completed",terminal="listing_shape_observed",failure_code=None,
        attempted_request_count=1,http_status=200,observation=observation,**listing.FLAGS)
    raw=d.helpers.canonical_json_bytes(directory.data[listing.REPORT])
    monkeypatch.setattr(d,"LISTING_REPORT_BYTES",len(raw))
    monkeypatch.setattr(d,"LISTING_REPORT_SHA256",hashlib.sha256(raw).hexdigest())
    return directory


def test_listing_external_pin_and_known_null_observation_are_not_absence(monkeypatch):
    directory=listing_fixture(monkeypatch)
    d._listing_binding(directory,listing)
    assert directory.events==[("read",name) for name in (listing.CLAIM,listing.START,listing.REPORT)]


@pytest.mark.parametrize("mutation",["claim","intent","pin","length","head","caller","profile","terminal","count_bool",
    "api_false","objects_list","path_false","types_bad","extra"])
def test_listing_retained_evidence_drift_refuses_before_package_or_contact(monkeypatch,mutation):
    directory=listing_fixture(monkeypatch); report=directory.data[listing.REPORT]
    if mutation=="claim": directory.data[listing.CLAIM]["expected_head"]=HEAD
    elif mutation=="intent": directory.data[listing.START]["endpoint"]="object/properties"
    elif mutation=="pin": monkeypatch.setattr(d,"LISTING_REPORT_SHA256","c"*64)
    elif mutation=="length": monkeypatch.setattr(d,"LISTING_REPORT_BYTES",d.LISTING_REPORT_BYTES+1)
    else:
        shape=report["observation"]["schema_observation"]
        if mutation=="api_false": shape["api_success"]=False
        elif mutation=="objects_list": shape["field_types"]["objects"]="list"
        elif mutation=="path_false": shape["predicates"]["path_exact"]=False
        elif mutation=="types_bad": shape["field_types"]=[]
        else:
            key,value={"head":("expected_head",HEAD),"caller":("caller_sha256",SHA),"profile":("profile_sha256",SHA),
                "terminal":("terminal","other"),"count_bool":("attempted_request_count",True),"extra":("PRIVATE",True)}[mutation]
            report[key]=value
        raw=d.helpers.canonical_json_bytes(report)
        monkeypatch.setattr(d,"LISTING_REPORT_BYTES",len(raw)); monkeypatch.setattr(d,"LISTING_REPORT_SHA256",hashlib.sha256(raw).hexdigest())
    with pytest.raises(d.DiagnosticRefusal): d._listing_binding(directory,listing)


def preflight_fixture(monkeypatch):
    raw=b"synthetic committed matrix\n"; caller=hashlib.sha256(raw).hexdigest(); seen=[]
    pins={d.ROOT/name:digest for name,digest in d.PINS.items()}; pins[d.SOURCE]=caller
    monkeypatch.setattr(d,"_under_test",lambda:False)
    monkeypatch.setattr(d.frozen,"_preflight",lambda args,deadline:seen.append(args))
    monkeypatch.setattr(d.helpers,"_source_digest",lambda path:pins[path])
    def git(args,deadline,limit=65536):
        if args[:2]==["cat-file","-s"]: return (str(len(raw))+"\n").encode()
        if args[:2]==["cat-file","blob"]: assert limit==len(raw); return raw
        if args==["rev-parse","HEAD"]: return (HEAD+"\n").encode()
        assert args==["status","--porcelain"]; return b""
    monkeypatch.setattr(d,"_git",git)
    return SimpleNamespace(caller=caller,pins=pins,seen=seen,git=git)


def test_preflight_original_caller_exact_own_blob_and_no_operational_import(monkeypatch):
    f=preflight_fixture(monkeypatch)
    REAL_PREFLIGHT(HEAD,f.caller,time.monotonic()+240)
    assert len(f.seen)==1 and f.seen[0].caller_sha256==d.FROZEN_CALLER_SHA256
    assert f.seen[0].operation=="summarize" and f.seen[0].family_sha256==d.FAMILY_SHA256


@pytest.mark.parametrize("mutation",["self","dependency","blob","size","head","dirty","source_path","deadline"])
def test_source_runtime_binding_refuses_each_new_gate(monkeypatch,mutation):
    f=preflight_fixture(monkeypatch)
    if mutation=="self": f.pins[d.SOURCE]="c"*64
    elif mutation=="dependency": f.pins[d.ROOT/next(iter(d.PINS))]="c"*64
    elif mutation=="source_path": monkeypatch.setattr(d,"SOURCE",d.SOURCE.with_name("wrong.py"))
    elif mutation!="deadline":
        def changed(args,deadline,limit=65536):
            value=f.git(args,deadline,limit)
            if mutation=="blob" and args[:2]==["cat-file","blob"]: return b"x"*len(value)
            if mutation=="size" and args[:2]==["cat-file","-s"]: return b"0\n"
            if mutation=="head" and args==["rev-parse","HEAD"]: return b"c"*40+b"\n"
            if mutation=="dirty" and args==["status","--porcelain"]: return b" M file\n"
            return value
        monkeypatch.setattr(d,"_git",changed)
    with pytest.raises(d.DiagnosticRefusal): REAL_PREFLIGHT(HEAD,f.caller,time.monotonic()+(241 if mutation=="deadline" else 240))


def test_post_source_or_payload_change_keeps_matrix_unaccepted(monkeypatch):
    f=fixture(monkeypatch)
    monkeypatch.setattr(d,"_package_payloads",lambda *_:(b"CHANGED",))
    result,code=execute()
    assert code==2 and len(f.calls)==6 and result["report"]["failure_code"]=="source_postcheck"
    assert result["report"]["matrix_completed"] is False


def test_finite_exception_labels_do_not_render_or_hash_hostile_types():
    class HostileMeta(type):
        def __hash__(cls): raise AssertionError("no hash")
        def __eq__(cls,other): raise AssertionError("no equality")
    class Hostile(Exception,metaclass=HostileMeta):
        def __str__(self): raise AssertionError("no text")
        def __repr__(self): raise AssertionError("no repr")
    assert d._failure(Hostile("PRIVATE"),listing,prior,old)=="unknown_exception"
    assert d._failure(listing.DiagnosticRefusal("response_nonfinite"),listing,prior,old)=="response_nonfinite"
    assert d._failure(prior.DiagnosticRefusal("PRIVATE"),listing,prior,old)=="dependency_validation_refused"
