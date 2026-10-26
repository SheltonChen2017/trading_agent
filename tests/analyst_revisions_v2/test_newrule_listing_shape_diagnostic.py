"""Only synthetic in-memory listings; native artifact/network denial required."""
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

from scripts import diagnose_arv2_newrule_listing_shape as d
from scripts import arv2_newrule_storage_recovery_v2 as recovery
from scripts import diagnose_arv2_newrule_object_metadata as prior
from scripts import diagnose_arv2_newrule_upload as markers
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old

HEAD, SHA, ORG = "a"*40, "b"*64, "f"*32
REAL_DIRECTORY, REAL_CLIENT = old._Directory, old.QuantConnectClient
REAL_PREFLIGHT, REAL_RETAINED = d._preflight, d._retained


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    violations = []
    def forbidden(*_a, **_k):
        violations.append("operational_boundary")
        pytest.fail("operational boundary forbidden")
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", forbidden)
    monkeypatch.setattr(REAL_CLIENT, "__init__", forbidden)
    for owner, names in ((old, ("_Directory", "_client", "load_family", "prepare_family", "upload_inputs", "capacity_once", "begin_attempt", "_session")),
        (old.coverage, ("production_client",)), (old.october, ("load_october_order_input_package",)),
        (old.compact, ("load_accepted_risk_preliminary_package",)),
        (recovery, ("claim", "recover", "require_admission")), (prior, ("run", "_run", "_transport")),
        (markers, ("run", "_run", "_census")), (d.frozen, ("run", "_operation")),
        (urllib.request.OpenerDirector, ("open",)), (socket, ("create_connection", "getaddrinfo")),
        (socket.socket, ("connect", "connect_ex")), (old.http.client.HTTPConnection, ("request", "connect")),
        (old.http.client.HTTPSConnection, ("connect",))):
        for name in names: monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "an operational boundary guard was reached"


class Directory:
    def __init__(self): self.data, self.events, self.closed = {}, [], False
    def names(self): return tuple(self.data)
    def write(self, name, value):
        assert name.startswith("listing-shape-diagnostic-v1-")
        self.events.append(("write", name))
        if name in self.data: raise FileExistsError()
        self.data[name] = copy.deepcopy(value)
    def read(self, name):
        self.events.append(("read", name))
        return copy.deepcopy(self.data[name])
    def __exit__(self, *_): self.closed = True
    def verify(self): self.events.append(("verify",None))


def inventory():
    return [[d.PREFIX+"/PRIVATE-KEY-"+str(i), "c"*64, i+10, i == 5] for i in range(6)]


def listing():
    return {"success": True, "path": d.PREFIX, "objects": [dict(key=row[0], name="PRIVATE-KEY-"+str(i),
        size=row[2], folder=False, mime="PRIVATE-MIME", modified="PRIVATE-TIME") for i,row in enumerate(inventory())],
        "page": 0, "totalPages": 1, "objectStorageUsed": 123, "errors": []}


class Response:
    def __init__(self, url, code=200, raw=b"{}"):
        self.url, self.code, self.raw, self.closed, self.reads = url, code, raw, False, []
    def geturl(self): return self.url
    def read(self, size): self.reads.append(size); return self.raw
    def close(self): self.closed = True


def fixture(monkeypatch, value=None, code=200):
    directory, calls, events = Directory(), [], []
    response = Response(old.API_BASE+"/object/list", code, json.dumps(listing() if value is None else value).encode())
    monkeypatch.setattr(d, "_preflight", lambda *_: events.append("preflight"))
    monkeypatch.setattr(d, "_dependencies", lambda: (recovery, prior, markers, old))
    monkeypatch.setattr(old, "_Directory", lambda: directory)
    monkeypatch.setattr(d, "_retained", lambda *_: (inventory(), ORG))
    body = d.helpers.canonical_json_bytes({"organizationId": ORG, "path": d.PREFIX})
    monkeypatch.setattr(d, "PRIOR_REQUEST_SHA256", hashlib.sha256(body).hexdigest())
    def client(): events.append("credentials"); return SimpleNamespace(_credentials=object(), _clock=lambda:100)
    monkeypatch.setattr(old, "_client", client)
    monkeypatch.setattr(old, "_safe_environment", lambda: None)
    monkeypatch.setattr(old, "build_auth_headers", lambda *_: {"Authorization":"PRIVATE-CREDENTIAL"})
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return response
    monkeypatch.setattr(d, "_opener", lambda: Opener())
    return SimpleNamespace(directory=directory, response=response, calls=calls, events=events)


def execute(): return d._run(HEAD, SHA, time.monotonic()+90)


def test_full_observation_one_readonly_call_and_published_finite_report(monkeypatch):
    f = fixture(monkeypatch)
    envelope, code = execute()
    assert code == 0 and f.directory.closed and len(f.calls) == 1
    request, timeout = f.calls[0]
    assert request.get_method() == "POST" and request.full_url == old.API_BASE+"/object/list"
    assert json.loads(request.data) == {"organizationId":ORG,"path":d.PREFIX} and timeout <= 30
    assert f.events == ["preflight", "credentials", "preflight"]
    report = envelope["report"]
    assert report["attempted_request_count"] == 1 and report["http_status"] == 200
    assert report["terminal"] == "listing_shape_observed" and report["failure_code"] is None
    raw = d.helpers.canonical_json_bytes(report)
    assert envelope["report_bytes"] == len(raw) and envelope["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert f.directory.events[0] == ("write",d.CLAIM)
    assert {d.CLAIM,d.START,d.REPORT} == set(f.directory.data)
    assert all(report[name] is value for name,value in d.FLAGS.items())
    assert "PRIVATE" not in json.dumps(envelope) and ORG not in json.dumps(envelope)
    assert report["observation"]["schema_observation"]["original_initial_shape_conjunction"] is True
    assert f.response.reads == [d.MAX_RESPONSE_BYTES+1] and f.response.closed


@pytest.mark.parametrize("prefix", ["exact","leading","trailing","both","other"])
def test_prefix_boolean_variants_never_output_path(prefix):
    value = listing(); value["path"] = {"exact":d.PREFIX,"leading":"/"+d.PREFIX,
        "trailing":d.PREFIX+"/","both":"/"+d.PREFIX+"/","other":"PRIVATE-OTHER"}[prefix]
    observed = d._observation(json.dumps(value).encode(), inventory())["schema_observation"]
    expected = {"exact":"path_exact","leading":"path_leading_slash","trailing":"path_trailing_slash","both":"path_both_slashes"}
    assert sum(observed["predicates"][key] for key in expected.values()) == int(prefix != "other")
    if prefix != "other": assert observed["predicates"][expected[prefix]] is True
    assert "PRIVATE" not in json.dumps(observed) and d.PREFIX not in json.dumps(observed)


@pytest.mark.parametrize("field,value,kind,bounded", [("page",None,"null",None),("page",False,"bool",None),
    ("page",1.0,"float",None),("page",-1,"int",None),("page",2**31,"int",None),
    ("page",1,"int",1),("totalPages",0,"int",0),("totalPages",2,"int",2),
    ("totalPages","PRIVATE","str",None)])
def test_page_types_and_bounded_values(field,value,kind,bounded):
    raw = listing(); raw[field]=value
    observed = d._observation(json.dumps(raw).encode(),inventory())["schema_observation"]
    assert observed["field_types"][field] == kind
    assert observed["page_value" if field=="page" else "total_pages_value"] == bounded


def test_missing_extra_null_variant_and_census_facts_do_not_reveal_names():
    value=listing(); del value["page"]; del value["totalPages"]; value["PRIVATE-EXTRA"]="PRIVATE-VALUE"
    value["objectStorageUsed"] = 123.0
    objects=value["objects"]
    objects[0]["isFolder"] = objects[0].pop("folder"); objects[0]["size"]=10.0
    objects[1]["modified"]=None; objects[1]["mime"]=None; objects[1]["name"]=None
    objects.extend([copy.deepcopy(objects[2]), {"key":"PRIVATE-UNKNOWN","folder":True}, None, {"key":False}])
    observed=d._observation(json.dumps(value).encode(),inventory())["schema_observation"]
    assert observed["missing_required_count"]==2 and observed["unknown_top_field_count"]==1
    assert observed["field_types"]["page"] == observed["field_types"]["totalPages"] == "missing"
    assert observed["object_count"]==10 and observed["census_complete"] is True
    c=observed["object_counters"]
    assert (c["known_key"],c["duplicate_known_key"],c["unknown_key"],c["invalid_key_type"],c["non_dict"])==(7,1,1,1,1)
    assert c["alternate_is_folder_schema"]==1 and c["size_integral_float"]==1 and c["folder_true"]==1
    assert observed["object_field_types"]["modified"]["null"]==1
    assert "PRIVATE" not in json.dumps(observed)


@pytest.mark.parametrize("value", [None,False,123,1.2,"PRIVATE",[],{}])
def test_non_object_or_missing_response_shape_is_observed_not_publication_acceptance(value):
    result=d._observation(json.dumps(value).encode(), inventory())["schema_observation"]
    assert result["original_initial_shape_conjunction"] is False and result["object_count"] is None


def test_census_is_bounded_and_explicitly_incomplete():
    value=listing(); value["objects"]=[None]*(d.MAX_CENSUS+1)
    observed=d._observation(json.dumps(value).encode(),inventory())["schema_observation"]
    assert observed["object_count"]==d.MAX_CENSUS+1 and observed["census_complete"] is False
    assert observed["object_counters"]["scanned"]==d.MAX_CENSUS


@pytest.mark.parametrize("raw", [b'{"success":true,"success":false}',b'{"x":NaN}',b'{"x":Infinity}',
    b'{"x":-Infinity}',b'{"x":1e400}',b'{"x":[{"y":1,"y":2}]}',b'{}{}',b'notjson',b'\xff'])
def test_strict_json_rejects_duplicates_nonfinite_trailing_and_encoding(raw):
    with pytest.raises((d.DiagnosticRefusal,ValueError,UnicodeError)): d._observation(raw,inventory())


@pytest.mark.parametrize("code", [301,401,403,429,500])
def test_non2xx_status_is_bounded_observation_without_body_or_retry(monkeypatch,code):
    f=fixture(monkeypatch,code=code)
    result,status=execute()
    assert status==0 and result["report"]["http_status"]==code
    assert result["report"]["observation"]=={"http_body_parsed":False,"schema_observation":None}
    assert f.response.reads==[] and f.response.closed and len(f.calls)==1


def test_http_error_numeric_status_preserved_without_failed_body(monkeypatch):
    f=fixture(monkeypatch)
    class Body(io.BytesIO):
        def read(self,*_): pytest.fail("failed body must not be read")
    body=Body(b"PRIVATE")
    error=urllib.error.HTTPError(old.API_BASE+"/object/list",403,"PRIVATE",{},body)
    def open_once(request,timeout): f.calls.append((request,timeout)); raise error
    monkeypatch.setattr(d,"_opener",lambda:SimpleNamespace(open=open_once))
    envelope,code=execute()
    assert code==0 and envelope["report"]["http_status"]==403 and len(f.calls)==1 and body.closed


@pytest.mark.parametrize("mutation", ["url","status_bool","overflow","timeout","malformed","expired"])
def test_transport_ambiguity_refuses_without_retry(monkeypatch,mutation):
    f=fixture(monkeypatch)
    if mutation=="url": f.response.url+="/wrong"
    elif mutation=="status_bool": f.response.code=True
    elif mutation=="overflow": f.response.raw=b"x"*(d.MAX_RESPONSE_BYTES+1)
    elif mutation=="malformed": f.response.raw=b"bad"
    elif mutation=="timeout":
        def timeout(request,timeout): f.calls.append((request,timeout)); raise TimeoutError("PRIVATE")
        monkeypatch.setattr(d,"_opener",lambda:SimpleNamespace(open=timeout))
    elif mutation=="expired":
        original=f.response.read
        def read(size):
            raw=original(size)
            monkeypatch.setattr(d.helpers,"_remaining",lambda *_: (_ for _ in ()).throw(d.helpers.Deadline()))
            return raw
        f.response.read=read
    if mutation=="expired":
        with pytest.raises(d.helpers.Deadline): execute()
    else:
        envelope,code=execute()
        assert code==2 and envelope["report"]["observation"] is None and envelope["report"]["attempted_request_count"]==1
        assert "PRIVATE" not in json.dumps(envelope)
    assert len(f.calls)==1


def test_no_redirect_empty_proxy_configuration(monkeypatch):
    seen=[]
    monkeypatch.setattr(urllib.request,"build_opener",lambda *args:seen.extend(args))
    d._opener()
    assert isinstance(seen[0],urllib.request.ProxyHandler) and seen[0].proxies=={}
    assert isinstance(seen[1],d._NoRedirect)
    assert seen[1].redirect_request(None,None,302,"PRIVATE",{},"https://unused.invalid") is None


@pytest.mark.parametrize("boundary",["directory_alias","client_alias","socket","old_run"])
def test_captured_independent_guards_cannot_be_swallowed(isolation,boundary):
    calls={"directory_alias":lambda:REAL_DIRECTORY(),"client_alias":lambda:REAL_CLIENT(),
        "socket":lambda:socket.create_connection(("unused.invalid",443)),"old_run":lambda:recovery.claim(HEAD,SHA)}
    with pytest.raises(pytest.fail.Exception): calls[boundary]()
    assert isolation==["operational_boundary"]; isolation.clear()


def test_direct_run_in_actual_pytest_context_refuses_before_directory():
    result,status=execute()
    assert status==2 and not result["report_published"]
    assert result["report"]["failure_code"]=="operational_test_context" and result["report"]["attempted_request_count"]==0


def test_preflight_failure_does_not_import_dependencies_or_construct_directory(monkeypatch):
    def reject(*_): raise d.DiagnosticRefusal("source_binding")
    monkeypatch.setattr(d,"_preflight",reject)
    monkeypatch.setattr(d,"_dependencies",lambda:pytest.fail("no imports after source refusal"))
    result,status=execute()
    assert status==2 and result["report"]["failure_code"]=="source_binding" and not result["report_published"]


@pytest.mark.parametrize("where",["claim","retained","credentials","close"])
def test_consumption_refusal_and_late_close_preserve_no_acceptance(monkeypatch,where,capsys):
    f=fixture(monkeypatch)
    if where=="claim": f.directory.data[d.CLAIM]={}
    elif where=="retained": monkeypatch.setattr(d,"_retained",lambda *_: (_ for _ in ()).throw(d.DiagnosticRefusal("prior_report_pin")))
    elif where=="credentials": monkeypatch.setattr(old,"_client",lambda: (_ for _ in ()).throw(PermissionError("PRIVATE")))
    elif where=="close": f.directory.__exit__=lambda *_: (_ for _ in ()).throw(d.DiagnosticRefusal("publication_ambiguous"))
    assert d.run(SimpleNamespace(expected_head=HEAD,caller_sha256=SHA))==2
    result=json.loads(capsys.readouterr().out)
    assert "PRIVATE" not in json.dumps(result)
    if where=="close": assert result["terminal"]=="diagnostic_publication_ambiguous" and "report_sha256" not in result
    else: assert len(f.calls)==0 and result["report"]["observation"] is None


def prior_fixture():
    directory=Directory()
    binding={"schema":"arv2-newrule-storage-recovery-v2","profile_sha256":d.PRIOR_PROFILE_SHA256,
        "family_sha256":d.FAMILY_SHA256,"expected_head":d.PRIOR_HEAD,"caller_sha256":d.PRIOR_CALLER_SHA256}
    directory.data[recovery.CLAIM]=dict(binding,attempt_consumed=True)
    directory.data[recovery.START]=dict(binding)
    request={"ordinal":0,"endpoint":"object/list","index":None,"request_sha256":d.PRIOR_REQUEST_SHA256,
        "attempted":True,"http_status":200,"response_schema_valid":True,"api_success":True,"error_category":"unknown"}
    directory.data[recovery.REPORT]=dict(binding,organization_sha256=d.ORGANIZATION_SHA256,
        inventory_sha256=d.INVENTORY_SHA256,prior_v1_refusal_sha256=recovery.V1_REFUSAL_SHA256,
        stage="list",complete=False,attempt_consumed=True,failure_code="listing_incomplete_or_shape",
        attempted_request_count=1,requests=[request],existing_indices=[],published_indices=[],validated_indices=[],
        legacy_upload_accepted=False,atomic_absent_only_put=False,actual_exit_is_external=True,
        formal_forward_ready=False,point_in_time_proven=False,paper_or_live_ready=False)
    return directory


def test_exact_publicly_reconstructed_prior_report_matches_external_pin_no_private_read():
    directory=prior_fixture()
    raw=d.helpers.canonical_json_bytes(directory.data[recovery.REPORT])
    assert len(raw)==1258==d.PRIOR_REPORT_BYTES and hashlib.sha256(raw).hexdigest()==d.PRIOR_REPORT_SHA256
    d._prior_binding(directory,recovery)
    assert directory.events==[("read",name) for name in (recovery.CLAIM,recovery.START,recovery.REPORT)]


@pytest.mark.parametrize("mutation",["claim","start","pin","length","complete","head","caller","count_bool","request_digest","extra"])
def test_prior_report_pin_exact_schema_and_bindings_refuse_drift(monkeypatch,mutation):
    directory=prior_fixture(); report=directory.data[recovery.REPORT]
    if mutation in {"claim","start"}: directory.data[recovery.CLAIM if mutation=="claim" else recovery.START]["expected_head"]=HEAD
    elif mutation=="pin": monkeypatch.setattr(d,"PRIOR_REPORT_SHA256","c"*64)
    elif mutation=="length": monkeypatch.setattr(d,"PRIOR_REPORT_BYTES",1259)
    else:
        if mutation=="request_digest": report["requests"][0]["request_sha256"]="c"*64
        else:
            key,value={"complete":("complete",True),"head":("expected_head",HEAD),"caller":("caller_sha256",SHA),
                "count_bool":("attempted_request_count",True),"extra":("PRIVATE",True)}[mutation]
            report[key]=value
        raw=d.helpers.canonical_json_bytes(report)
        monkeypatch.setattr(d,"PRIOR_REPORT_BYTES",len(raw)); monkeypatch.setattr(d,"PRIOR_REPORT_SHA256",hashlib.sha256(raw).hexdigest())
    with pytest.raises(d.DiagnosticRefusal): d._prior_binding(directory,recovery)


def test_retained_reads_only_exact_metadata_and_org_not_package(monkeypatch):
    directory=Directory(); events=[]; rows=inventory()
    monkeypatch.setattr(d,"_prior_binding",lambda *_:events.append("prior"))
    monkeypatch.setattr(markers,"_family_binding",lambda *_:{"upload_inventory":rows})
    monkeypatch.setattr(d,"INVENTORY_SHA256",hashlib.sha256(d.helpers.canonical_json_bytes(rows)).hexdigest())
    monkeypatch.setattr(prior,"_organization",lambda *_:ORG)
    assert REAL_RETAINED(directory,(recovery,prior,markers,old),time.monotonic()+30)==(rows,ORG)
    assert events==["prior"] and directory.events==[]
    directory.data[recovery.ADMISSION]={}
    with pytest.raises(d.DiagnosticRefusal,match="admission_present"):
        REAL_RETAINED(directory,(recovery,prior,markers,old),time.monotonic()+30)


def preflight_fixture(monkeypatch):
    raw=b"synthetic committed diagnostic\n"; caller=hashlib.sha256(raw).hexdigest(); seen=[]
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


def test_preflight_uses_frozen_original_caller_and_own_exact_commit_blob(monkeypatch):
    f=preflight_fixture(monkeypatch)
    REAL_PREFLIGHT(HEAD,f.caller,time.monotonic()+90)
    assert len(f.seen)==1 and f.seen[0].caller_sha256==d.FROZEN_CALLER_SHA256
    assert f.seen[0].operation=="summarize" and f.seen[0].family_sha256==d.FAMILY_SHA256


@pytest.mark.parametrize("mutation",["self","dependency","blob","size","head","dirty","source_path","deadline"])
def test_preflight_refuses_source_commit_or_scope_mismatch(monkeypatch,mutation):
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
    with pytest.raises(d.DiagnosticRefusal): REAL_PREFLIGHT(HEAD,f.caller,time.monotonic()+(91 if mutation=="deadline" else 90))


@pytest.mark.parametrize("mutation",["verify","source_postcheck","readback"])
def test_final_finite_checks_refuse_without_normal_success_envelope(monkeypatch,mutation,capsys):
    f=fixture(monkeypatch)
    if mutation=="verify": f.directory.verify=lambda: (_ for _ in ()).throw(d.DiagnosticRefusal("publication_ambiguous"))
    elif mutation=="source_postcheck":
        def check(*_):
            f.events.append("preflight")
            if f.events.count("preflight")==2: raise d.DiagnosticRefusal("source_binding")
        monkeypatch.setattr(d,"_preflight",check)
    else:
        original=f.directory.read
        def read(name):
            value=original(name)
            if name==d.REPORT: value["attempted_request_count"]=False
            return value
        f.directory.read=read
    assert d.run(SimpleNamespace(expected_head=HEAD,caller_sha256=SHA))==2
    output=json.loads(capsys.readouterr().out)
    assert f.directory.closed and len(f.calls)==1
    if mutation=="source_postcheck": assert output["report"]["observation"] is None
    else: assert "report_sha256" not in output


@pytest.mark.parametrize("errors",[None,[],["PRIVATE-ERROR"]])
def test_error_presence_facts_do_not_expose_strings(errors):
    value=listing()
    if errors is None: del value["errors"]
    else: value["errors"]=errors
    result=d._observation(json.dumps(value).encode(),inventory())["schema_observation"]
    assert result["errors_missing_or_empty_list"] is (not errors)
    assert result["errors_nonempty_list"] is bool(errors)
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("mutation",["unchanged","missing_page","page_null","page_bool","pages_bool","pages_two",
    "storage_bool","storage_limit","objects_seven","unknown_top","path","success_false",
    "human_later","object_later","zero_pages_later"])
def test_initial_shape_boolean_matches_only_frozen_first_guard(mutation):
    value=listing()
    if mutation=="missing_page": del value["page"]
    elif mutation=="page_null": value["page"]=None
    elif mutation=="page_bool": value["page"]=False
    elif mutation=="pages_bool": value["totalPages"]=True
    elif mutation=="pages_two": value["totalPages"]=2
    elif mutation=="storage_bool": value["objectStorageUsed"]=True
    elif mutation=="storage_limit": value["objectStorageUsed"]=2**63
    elif mutation=="objects_seven": value["objects"].append(copy.deepcopy(value["objects"][0]))
    elif mutation=="unknown_top": value["PRIVATE"]=True
    elif mutation=="path": value["path"]+="/"
    elif mutation=="success_false": value["success"]=False
    elif mutation=="human_later": value["objectStorageUsedHuman"]=False
    elif mutation=="object_later": value["objects"][0]["PRIVATE"]=True
    elif mutation=="zero_pages_later": value["totalPages"]=0
    try:
        recovery._listing(value,inventory())  # pure schema predicate only; no old operation
        first_passed=True
    except recovery.StorageRecoveryError as error:
        first_passed=error.args[0]!="listing_incomplete_or_shape"
    observed=d._observation(json.dumps(value).encode(),inventory())["schema_observation"]
    assert observed["original_initial_shape_conjunction"] is first_passed


def test_finite_failure_never_renders_or_hashes_unknown_exception():
    class HostileMeta(type):
        def __hash__(cls): raise AssertionError("no class hashing")
        def __eq__(cls,other): raise AssertionError("no class equality")
    class Hostile(Exception,metaclass=HostileMeta):
        def __str__(self): raise AssertionError("no stringify")
        def __repr__(self): raise AssertionError("no repr")
    class HostileString(str):
        def __hash__(self): raise AssertionError("no string subclass lookup")
    assert d._failure(Hostile("PRIVATE"))=="unknown_exception"
    assert d._failure(d.DiagnosticRefusal(HostileString("source_binding")))=="unknown_exception"
    assert d._failure(d.DiagnosticRefusal("PRIVATE"*100))=="unknown_exception"
