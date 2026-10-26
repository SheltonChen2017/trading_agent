"""ONE unused-day 64KiB Range diagnostic; never a carrier/member admission.

Only an exact206/identity/singlepart Range unit may be read. A200 response is
left unread, with no fallback, retry, continuation or later full-URL authority.
Current sources, committed lineage, strong native controls and held metadata
precede private input. Prefix bytes AND every decoded byte receive the frozen
finite screen before any prefix/header hash or retention. Unknown response
headers are deliberately not retained; only bounded exact required fields are
screened and retained. Declared Content-Range total is NOT measured transfer.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass,field
import fcntl
import http.client
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
import weakref

from research import insider_buying_sec_feed_archive_format_v3 as previous
from research import insider_buying_sec_feed_compact_capture_v1 as compact_capture
from research import insider_buying_sec_feed_prefix_format_v1 as core

directory, old, batch = previous.directory, previous.old, previous.batch
publication, custody, privacy, source_runner = previous.publication, previous.custody, previous.privacy, previous.source_runner
contact_io = previous.contact_io
_raw, _sha = previous._raw, previous._sha
SCHEMA = "insider-sec-feed-prefix-capture-v1"
SELF_PATH = "research/insider_buying_sec_feed_prefix_capture_v1.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_prefix_capture_v1.py"
REVIEW_TEST_PATH = "tests/test_insider_buying_sec_feed_prefix_capture_v1_review.py"
LANE_ROOT, LANE_BRANCH, EMPTY_CACHE_PREFIX = previous.LANE_ROOT, previous.LANE_BRANCH, previous.EMPTY_CACHE_PREFIX
ARTIFACT_PARTS = ("artifacts","insider_buying","sec_feed_prefix_capture_v1")
AUDIT_ID = "ib-sec-feed-prefix-20201008-v1-20261025-once"
URL = "https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/20201008.nc.tar.gz"
RANGE = "bytes=0-65535"
PREFIX_BYTES, MAX_CONTROL = 65536, 64*1024**2
TRANSPORT_SECONDS, IDLE_SECONDS, WORKER_SECONDS = 45,15,180
MIN_FREE_BYTES = 8*1024**3
LOCK_BYTES = b"INSETF-unused-20201008-prefix-URL-permanently-consumed\n"
FROZEN = {**previous.FROZEN,
    core.SELF_PATH:"6778363fb6fb9b8fa71e091c749b74179d2495c49975452a92883e615e5b8c88",
    core.TEST_PATH:"371c8163f3ddfdec650ecafc7455948bbdfd68ac60d63b468f4c0bb031c54fe0",
    core.REVIEW_TEST_PATH:"bffac22873a10f2a41cbda4e827dded44bf3c7b2f29ad22d3fc80fc96af38050",
    previous.SELF_PATH:"b53808d458e270db465586b9863e2acc3efa56f9c42e7524cc6424a0aa2261e0",
    previous.TEST_PATH:"abe696390af1316d70654bbdb146880d480ddc2e199aa248f1fb409647d6ee18",
    compact_capture.SELF_PATH:"fd0fe5cc2e77b42d2845efa34a884dc4cf864bf7492bb865e970fe7ec5d1cf56",
    compact_capture.TEST_PATH:"5a057a496eda592495e4f25ee89adfa4de40becc4c326668ab97b0d92527cc36",
    compact_capture.PURE_PATH:"777006cc74567613a5d82e9c5844c1fd0f91567727d47fcb073a02ea4e161e41",
    compact_capture.PURE_TEST_PATH:"8f1619084ada77eb12165f6875643f6814902ca2ec2efc29e4213a9c06b3a1ea",
    compact_capture.PURE_REVIEW_TEST_PATH:"c9ef1c02577da1efaf50f765249b0898d329634ff706a4b126ee1c1e7ed13951",
    "tests/test_insider_buying_sec_feed_compact_capture_v1_review.py":"d35f0f20a8fc0e72c12d7f286cf85d856f7fe4868447052ec9cc5a99ead63f32"}
FAILED_SCOPES = ((old.v1,"dad7ff80e46277409aaeaf92f000b3b0ca98e81b6c622caf22f84332c61b4242"),
    (old,"8d12cf9a297899450b987c293acdcb479306a6f4512f859662ee34b8dd9e7693"),
    (previous,"df070bbb0d774cfd9b1cca5a6b8bbcf39044d7fb27c4a3735c8da9db4d9a6626"),
    (compact_capture,"c4bc18e34bb3bc0d0dd388709936bb103c208d7b33a5e1f41125d26280d9810d"))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = object()
_ACTIVATIONS, _DISPATCH = weakref.WeakKeyDictionary(), weakref.WeakKeyDictionary()
_PHASES = frozenset({"arguments","source","native_preflight","inputs","capacity","namespace","reservation",
    "contact","claim","start","transport","headers","body","privacy","gzip-prefix","input",
    "inspection","publication","complete","final","readback","cleanup"})
_HEADER_CODES = frozenset({"non206_body_unread","header_profile_refused","content_range_refused",
    "content_length_refused","transfer_encoding_refused","content_encoding_refused","multipart_refused"})
_CORE_CODES = {"input":frozenset({"immutable_prefix_byte_bound","exact_fixture_boolean_required"}),
    "privacy":frozenset({"explicit_contact_required","contact_profile_refused","finite_prefix_screen_refused"}),
    "capacity":frozenset({"gzip_member_count_bound","decoded_prefix_byte_bound","decoded_prefix_expansion_bound","descriptor_byte_bound"}),
    "gzip-prefix":frozenset({"invalid_gzip_prefix_or_observed_trailer","decoder_progress_refused"})}
_OWN_CODES = frozenset({"private_arguments_refused","private_contact_mode_refused","source_changed","source_identity_refused",
    "fixed_actual_front_required","native_boundary_refused","preflight_refused","inputs_changed","metadata_refused",
    "disk_reserve_refused","fresh_namespace_already_exists","output_changed","trusted_activation_required","dispatch_refused",
    "transport_front_refused","absolute_transport_deadline","idle_timeout","ambiguous_transport","cleanup_refused",
    "prefix_body_length_refused","header_privacy_refused","descriptor_refused","readback_refused","local_operation_refused"})


class PrefixCaptureError(ValueError):
    def __init__(self,code,phase="source"):
        self.phase = phase if type(phase) is str and phase in _PHASES else "source"
        super().__init__(code)


class _Deadline(Exception):pass


def _need(value,code,phase="source"):
    if not value:raise PrefixCaptureError(code,phase)


def _safe_error(error,phase):
    own = type(error) is PrefixCaptureError and len(error.args)==1 and type(error.args[0]) is str
    code = error.args[0] if own else None
    return {"phase":error.phase if own else phase if phase in _PHASES else "source",
        "code":code if code in _OWN_CODES|_HEADER_CODES else "local_operation_refused"}


def _control(raw):
    _need(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL,"metadata_refused")
    return previous._control(raw)


def _authority():
    return {**previous._authority(),"prefix_format_diagnostic_only":True,
        "whole_carrier_privacy_integrity_or_retention":False,"source_identity_validated":False}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"url":URL,"method":"GET","Range":RANGE,
        "maximum_GETs":1,"URL_consumed_regardless_Range":True,"source_ordinal":6,
        "listed_name":"20201008.nc.tar.gz","advertised_size_text":"523023 KB","advertisement_is_not_measured_bytes":True,
        "accepted_status":206,"required_prefix_bytes":PREFIX_BYTES,"range_total_declared_not_measured":True,
        "200_body_unread_no_fallback":True,"retries_redirects_HEAD_continuation_alias":False,
        "transport_absolute_seconds":TRANSPORT_SECONDS,"transport_idle_seconds":IDLE_SECONDS,
        "worker_seconds":WORKER_SECONDS,"memory_policy":previous._memory_policy(),"minimum_free_reserve_bytes":MIN_FREE_BYTES,
        "only_required_response_headers_retained_after_privacy":True,"full_roster_rederived":False,
        "known_failed_carrier_URLs_bound":4,"current_contact_readback_registered":True,
        "original_current_contact_equality_attested":False,"authority":_authority()}


def _own_paths():return (SELF_PATH,TEST_PATH,REVIEW_TEST_PATH,core.SELF_PATH,core.TEST_PATH,core.REVIEW_TEST_PATH,*FROZEN)


def _current(identity):
    publication._source_identity(identity,required_paths=_own_paths())
    _need(custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and custody._source_bytes(LANE_ROOT,tuple(FROZEN))==FROZEN
        and custody._source_bytes(LANE_ROOT,tuple(source_runner.FROZEN))==source_runner.FROZEN
        and set(custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"source_changed")


def _identity(head):
    previous._isolated();_need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_front_required")
    value=batch.campaign._identity(head)
    sources={**value["source_sha256"],**custody._source_bytes(LANE_ROOT,_own_paths())}
    for name,pin in sources.items():_need(_sha(custody._git(LANE_ROOT,"show",head+":"+name))==pin,"source_changed")
    identity={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    _current(identity);return identity


def _compile_sources(identity):
    """Memory-only compilation of the exact inventoried images, no cache IO."""
    for name,pin in identity["source_sha256"].items():
        parts=Path(name).parts;chain=custody._Chain(LANE_ROOT,parts[:-1])
        try:
            raw=custody._read_leaf(chain.fd,parts[-1],limit=4*1024**2,private=False)
            _need(_sha(raw)==pin,"source_changed","source")
            try:compile(raw,name,"exec")
            except (SyntaxError,ValueError):raise PrefixCaptureError("source_changed","source") from None
            chain.recheck()
        finally:chain.close()


class _Inputs:
    """Only continuously held Q4 listing + four consumed failure controls."""
    def __init__(self,root):
        self.folders=[];self.locks=[]
        try:
            top,claims,run=self.scope(root,directory)
            names={"reservation.json","contact-validated.json","request-start.json","request-result.json","complete.json",
                "response.bin","response-headers.json","inventory.json"}
            _need(set(os.listdir(run.fd))==names,"inputs_changed","inputs")
            raws={n:run.read(n,cap=directory.MAX_RESPONSE_BYTES) for n in sorted(names)}
            original=previous._directory_summary(raws,claims.read(directory._claim_name()),root,False)
            inventory=directory.parse_directory_inventory(raws["response.bin"])
            selected=[r for r in inventory["entries"] if r["qualified_archive_url"]==URL]
            _need(len(selected)==1 and selected[0]["source_ordinal"]==6 and selected[0]["listed_name"]=="20201008.nc.tar.gz"
                and selected[0]["advertised_size_text"]=="523023 KB","inputs_changed","inputs")
            failures=[]
            for module,pin in FAILED_SCOPES:
                _,c,r=self.scope(root,module)
                names={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json","complete.json"}
                _need(set(os.listdir(r.fd))==names,"inputs_changed","inputs")
                values={n:r.read(n,cap=MAX_CONTROL) for n in sorted(names)}
                claim=c.read(module._claim_name(),cap=MAX_CONTROL)
                complete=_control(values["complete.json"]);result=_control(values["request-result.json"])
                reservation=_control(values["reservation.json"]);start=_control(values["request-start.json"])
                _need(_sha(values["complete.json"])==pin and complete["result_sha256"]==_sha(values["request-result.json"])
                    and _raw(complete["result"])==_raw(result) and complete["reservation_sha256"]==_sha(values["reservation.json"])
                    and complete["input_preflight_sha256"]==_sha(values["input-preflight.json"])
                    and result["reservation_sha256"]==_sha(values["reservation.json"])
                    and result["claim_sha256"]==_sha(claim) and result["start_sha256"]==_sha(values["request-start.json"])
                    and start["claim_sha256"]==_sha(claim) and _control(claim)["url"]==module.URL
                    and complete["execution_identity"]==reservation["execution_identity"]
                    and (result.get("response_retained") is False or result.get("compact_retained") is False),"inputs_changed","inputs")
                failures.append({"url":module.URL,"complete_sha256":pin,"producer_execution_identity":complete["execution_identity"],
                    "metadata_pins":{n:_sha(v) for n,v in values.items()},"claim_sha256":_sha(claim),
                    "failed_operation_remains_failed":True,"retained_original_body_bytes_read":0})
            self.metadata={"schema":SCHEMA+"/inputs","directory":original,"selected_row":selected[0],"failed_carriers":failures,
                "original_parent_or_carrier_bodies_read":0,"source_row_tables_decoded":0,
                "prior_archive_membership_still_unknown":True}
            self.check()
        except BaseException:self.close();raise

    def opened(self,path):
        value=directory._ReadbackDirectory(path);self.folders.append(value);return value

    def scope(self,root,module):
        top=self.opened(root.joinpath(*module.ARTIFACT_PARTS));claims=self.opened(top.path/"claims")
        runs=self.opened(top.path/"runs");run=self.opened(runs.path/module.AUDIT_ID)
        expected={"scope.lock","claims","runs"}
        if module is compact_capture:
            expected.add("objects");objects=self.opened(top.path/"objects");_need(not objects.inventory,"inputs_changed","inputs")
        _need(top.inventory==expected and claims.inventory=={module._claim_name()} and runs.inventory=={module.AUDIT_ID},"inputs_changed","inputs")
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        self.locks.append((lock,top,privacy._file_version(os.fstat(lock))))
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(top.read("scope.lock")==module.LOCK_BYTES,"inputs_changed","inputs")
        return top,claims,run

    def check(self):
        for folder in self.folders:folder.check()
        for lock,top,version in self.locks:
            _need(version==privacy._file_version(os.fstat(lock))==privacy._file_version(
                os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed","inputs")

    def close(self):
        # All failures are sanitized by the outer phase boundary; preserve an
        # active primary exception when draining several independently held FDs.
        active=sys.exc_info()[0] is not None;failure=None
        for lock,_,_ in reversed(self.locks):
            for action in (lambda:fcntl.flock(lock,fcntl.LOCK_UN),lambda:os.close(lock)):
                try:action()
                except BaseException as error:failure=error
        self.locks=[]
        for folder in reversed(self.folders):
            try:folder.close()
            except BaseException as error:failure=error
        self.folders=[]
        if failure is not None and not active:raise PrefixCaptureError("cleanup_refused","cleanup") from None


def _parent_proofs(plan):
    for identity in (plan["inputs"]["directory"]["original_execution_identity"],
            *(row["producer_execution_identity"] for row in plan["inputs"]["failed_carriers"])):
        previous._source_git(identity)


def _screen(raw,private):
    try:
        value=old._TextScreen(private)
        for at in range(0,len(raw),1024):value.feed(raw[at:at+1024])
        value.feed(b"",final=True)
    except old.ArchiveSampleError:raise PrefixCaptureError("header_privacy_refused","privacy") from None


def _range_headers(status,pairs):
    _need(type(status) is int and 100<=status<=599,"header_profile_refused","headers")
    _need(status==206,"non206_body_unread","headers")
    _need(type(pairs) in {tuple,list} and len(pairs)<=64 and all(type(pair) in {tuple,list} and len(pair)==2
        and all(type(x) is str and all(32<=ord(c)<=126 for c in x) for x in pair)
        and re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+",pair[0]) for pair in pairs)
        and len(_raw(pairs))<=16384,"header_profile_refused","headers")
    grouped={name.lower():[value for n,value in pairs if n.lower()==name.lower()] for name,_ in pairs}
    _need(not grouped.get("transfer-encoding"),"transfer_encoding_refused","headers")
    _need(grouped.get("content-length")==[str(PREFIX_BYTES)],"content_length_refused","headers")
    ranges=grouped.get("content-range",[])
    _need(len(ranges)==1,"content_range_refused","headers")
    match=re.fullmatch(r"bytes 0-65535/([1-9][0-9]{0,11})",ranges[0])
    _need(match is not None and int(match.group(1))>PREFIX_BYTES,"content_range_refused","headers")
    _need(not grouped.get("content-encoding") or grouped["content-encoding"]==["identity"],"content_encoding_refused","headers")
    types=grouped.get("content-type",[])
    _need(len(types)<=1 and (not types or re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+",types[0])
        and not types[0].lower().startswith("multipart/")),"multipart_refused","headers")
    kept=tuple((name,value) for name,value in pairs if name.lower() in {"content-length","content-range","content-encoding","content-type"})
    return kept,int(match.group(1))


@dataclass(frozen=True,slots=True)
class PrefixHttpResult:
    status:int=field(repr=False)
    headers:tuple=field(repr=False)
    body:bytes=field(repr=False)
    refusal:dict|None=field(repr=False)
    declared_total:int|None=field(repr=False)
    body_read_attempted:bool=field(repr=False)


def _observe_response(response):
    status=response.status
    try:pairs,total=_range_headers(status,tuple(response.getheaders()))
    except PrefixCaptureError as error:
        return PrefixHttpResult(status,(),b"",_safe_error(error,"headers"),None,False)
    raw=response.read(PREFIX_BYTES)
    if type(raw) is not bytes or len(raw)!=PREFIX_BYTES:
        return PrefixHttpResult(status,(),b"",{"phase":"body","code":"prefix_body_length_refused"},None,True)
    return PrefixHttpResult(status,pairs,raw,None,total,True)


def _inspect(raw,pairs,private,*,fixture):
    pairs,total=_range_headers(206,pairs)
    _need(type(raw) is bytes and len(raw)==PREFIX_BYTES,"prefix_body_length_refused","body")
    for name,value in pairs:_screen(name.encode("ascii"),private);_screen(value.encode("ascii"),private)
    _screen(_raw(pairs),private)
    descriptor=core.inspect_prefix(raw,privacy_contact=private,fixture_only=fixture)
    _screen(_raw(descriptor),private)
    return {"schema":SCHEMA+"/inspection","descriptor":descriptor,"headers_sha256":_sha(_raw(pairs)),
        "declared_carrier_total_bytes":total,"total_is_declared_not_measured":True,
        "prefix_unit_privacy_and_integrity_only":True,"whole_carrier_verified":False,"authority":_authority()}


def _core_error(error):
    if type(error) is core.PrefixFormatError and type(error.phase) is str and type(error.code) is str:
        if error.code in _CORE_CODES.get(error.phase,()):return {"phase":error.phase,"code":error.code}
    return None


def _worker(role,identity,*,publish=False):
    previous._isolated();source_runner._prove_isolation();memory=previous._WorkerMemoryGuard();held=None
    try:
        _current(identity);_compile_sources(identity);_current(identity);memory.check()
        if role=="preflight":
            held=_Inputs(LANE_ROOT);value={"schema":SCHEMA+"/preflight","execution_identity":identity,"inputs":held.metadata,
                "new_requests":0,"contact_reads":0,"namespace_created":False};_forms(identity,False,value)
        else:
            line=sys.stdin.buffer.readline(MAX_CONTROL+1)
            _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"metadata_refused","input")
            supplied=_control(line[:-1]);private=privacy._contact(supplied["contact"],observed=True)
            if role=="inspect":
                _need(set(supplied)=={"contact","headers","bytes","inputs"} and supplied["bytes"]==PREFIX_BYTES
                    and type(supplied["bytes"]) is int,"metadata_refused","input")
                raw=sys.stdin.buffer.read(PREFIX_BYTES+1)
                held=_Inputs(LANE_ROOT);_need(held.metadata==supplied["inputs"],"inputs_changed","inputs")
                try:value=_inspect(raw,supplied["headers"],private,fixture=False)
                except core.PrefixFormatError as error:
                    refusal=_core_error(error);_need(refusal is not None,"descriptor_refused","inspection")
                    value={"schema":SCHEMA+"/inspection-refusal","refusal":refusal}
                except PrefixCaptureError as error:
                    value={"schema":SCHEMA+"/inspection-refusal","refusal":_safe_error(error,"inspection")}
            else:
                _need(role=="readback" and set(supplied)=={"contact","complete_sha256"},"metadata_refused","input")
                value=_verify_files(LANE_ROOT,supplied["complete_sha256"],private,fixture=False,current_identity=identity)
        if held:held.check()
        _current(identity);memory.check()
        result={"ok":True,"value":value}
        if publish:
            raw=_raw(result);_need(0<len(raw)<MAX_CONTROL,"metadata_refused")
            memory.check();sys.stdout.buffer.write(raw+b"\n");sys.stdout.buffer.flush();memory.check();return None
        return result
    finally:
        source_runner.selector._close_all((held,memory),phase="prefix_worker_cleanup")


def _command(role,identity):
    _need(role in {"preflight","inspect","readback"},"metadata_refused")
    code=("import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_prefix_capture_v1 as m;"
        "identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry:m._worker("+repr(role)+",identity,publish=True)"
        "\nexcept Exception:print('{\"ok\":false,\"code\":\"native_boundary_refused\"}');sys.exit(2)")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    try:value=old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    except Exception:raise PrefixCaptureError("native_boundary_refused","native_preflight" if role=="preflight" else "inspection") from None
    _need(type(value) is dict and set(value)=={"ok","value"} and value["ok"] is True,"native_boundary_refused")
    return value["value"]


def _capacity(fd):
    space=os.fstatvfs(fd)
    _need(space.f_bavail*space.f_frsize>=MIN_FREE_BYTES+PREFIX_BYTES+4*MAX_CONTROL,"disk_reserve_refused","capacity")


def _preoutput_capacity(root):
    for count in range(len(ARTIFACT_PARTS)-1,-1,-1):
        held=None
        try:held=custody._Chain(root,ARTIFACT_PARTS[:count]);_capacity(held.fd);held.recheck();return
        except FileNotFoundError:continue
        finally:
            if held:held.close()
    raise PrefixCaptureError("disk_reserve_refused","capacity")


def _claim_name():return _sha(b"GET\0"+URL.encode("ascii"))+".json"


def _check_identity(identity,root):
    _need(type(identity) is dict and set(identity)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and identity["root"]==str(root) and identity["branch"]==LANE_BRANCH and identity["clean"] is True
        and type(identity["head"]) is str and re.fullmatch(r"[0-9a-f]{40}",identity["head"])
        and type(identity["source_sha256"]) is dict and {SELF_PATH,TEST_PATH}<=set(identity["source_sha256"])
        and 1<=len(identity["source_sha256"])<=4096 and all(type(name) is str and len(name)<=512
            and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",name) and not name.startswith("/")
            and all(part not in {"",".",".."} for part in name.split("/"))
            and type(pin) is str and _SHA.fullmatch(pin) for name,pin in identity["source_sha256"].items())
        and identity["source_inventory_sha256"]==_sha(_raw(identity["source_sha256"])),"source_identity_refused")


def _validate_plan(identity,fixture,plan):
    _check_identity(identity,Path(identity["root"]))
    keys={"schema","execution_identity","inputs","new_requests","contact_reads","namespace_created"}
    _need(type(fixture) is bool and type(plan) is dict and set(plan)==keys and plan["schema"]==SCHEMA+"/preflight"
        and _raw(plan["execution_identity"])==_raw(identity) and type(plan["inputs"]) is dict,"preflight_refused","native_preflight")
    if fixture:_need(plan["inputs"]=={"fixture_only":True},"preflight_refused","native_preflight")
    _need(type(plan["new_requests"]) is type(plan["contact_reads"]) is int
        and plan["new_requests"]==plan["contact_reads"]==0 and plan["namespace_created"] is False,
        "preflight_refused","native_preflight")


def _forms(identity,fixture,plan):
    _validate_plan(identity,fixture,plan)
    reservation={"schema":SCHEMA+"/reservation","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration":registration(),"registration_sha256":_sha(_raw(registration())),"input_preflight_sha256":_sha(_raw(plan))}
    rsha=_sha(_raw(reservation));claim={"schema":SCHEMA+"/URL-claim","method":"GET","url":URL,
        "reservation_sha256":rsha,"URL_consumed_regardless_Range":True}
    start={"schema":SCHEMA+"/start","reservation_sha256":rsha,"claim_sha256":_sha(_raw(claim)),"attempt":1,"Range":RANGE}
    result={"reservation.json":reservation,"input-preflight.json":plan,"claim.json":claim,"request-start.json":start}
    for value in result.values():_need(_raw(_control(_raw(value)))==_raw(value),"metadata_refused","capacity")
    return result


class _Activation:
    def __init__(self,identity,guard,held):self.identity,self.guard,self.held=identity,guard,held


def _activated(value,identity):
    _need(type(value) is _Activation and _ACTIVATIONS.get(value)==(_raw(identity),id(value.guard),id(value.held))
        and _raw(value.identity)==_raw(identity) and type(value.held) is _Inputs,"trusted_activation_required")
    value.guard();value.held.check()


class _Dispatch:
    def __init__(self,token,activation,identity,guard,prove,headers):
        _need(token is _TOKEN,"dispatch_refused","transport")
        self.activation,self.identity,self.guard,self.prove,self.headers=activation,identity,guard,prove,headers
        self.attempted=False;self.status=None;self.body_read_attempted=False
        _DISPATCH[self]=(id(activation),_raw(identity),id(guard),id(prove),_raw(headers))


def _transport(context):
    _need(type(context) is _Dispatch and _DISPATCH.get(context)==(id(context.activation),_raw(context.identity),id(context.guard),id(context.prove),_raw(context.headers))
        and not context.attempted and context.headers.get("Range")==RANGE,"dispatch_refused","transport")
    _activated(context.activation,context.identity);context.guard();context.prove()
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.),"transport_front_refused","transport")
    handler=signal.getsignal(signal.SIGALRM);connection=None;begun=time.monotonic()
    def expired(*_):raise _Deadline()
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,TRANSPORT_SECONDS);context.attempted=True
        connection=http.client.HTTPSConnection("www.sec.gov",timeout=IDLE_SECONDS)
        connection.request("GET",URL.removeprefix("https://www.sec.gov"),headers=context.headers)
        response=connection.getresponse();context.status=response.status
        # Preserve truthful body-attempt telemetry even if a read raises.
        original_read=response.read
        def read(*args,**kwargs):context.body_read_attempted=True;return original_read(*args,**kwargs)
        response.read=read
        value=_observe_response(response)
        _need(time.monotonic()-begun<=TRANSPORT_SECONDS,"absolute_transport_deadline","transport")
        return value
    except _Deadline:raise PrefixCaptureError("absolute_transport_deadline","transport") from None
    finally:
        primary=sys.exc_info()[0] is not None;failed=False
        for close in (lambda:signal.setitimer(signal.ITIMER_REAL,0),lambda:signal.signal(signal.SIGALRM,handler),
                *((connection.close,) if connection else ())):
            try:close()
            except BaseException:failed=True
        if failed and not primary:raise PrefixCaptureError("cleanup_refused","cleanup")


def _inspection_valid(value,fixture):
    _need(type(value) is dict and set(value)=={"schema","descriptor","headers_sha256","declared_carrier_total_bytes",
        "total_is_declared_not_measured","prefix_unit_privacy_and_integrity_only","whole_carrier_verified","authority"}
        and value["schema"]==SCHEMA+"/inspection" and value["total_is_declared_not_measured"] is True
        and value["prefix_unit_privacy_and_integrity_only"] is True and value["whole_carrier_verified"] is False
        and _raw(value["authority"])==_raw(_authority()) and type(value["declared_carrier_total_bytes"]) is int
        and PREFIX_BYTES<value["declared_carrier_total_bytes"]<10**12 and type(value["headers_sha256"]) is str
        and _SHA.fullmatch(value["headers_sha256"]),"descriptor_refused","inspection")
    descriptor=value["descriptor"]
    false_keys={"privacy_source_runtime_attested_here","universal_privacy_claim",
        "whole_carrier_CRC_ISIZE_or_EOF_verified","whole_carrier_privacy_screened","whole_carrier_hashed_or_retained",
        "complete_member_population_known","duplicates_or_coverage_verified","decoded_bytes_separately_hashed_or_retained",
        "PDS_controls_validated","source_authenticated","acceptance_or_PIT_verified","XML_or_financial_fields_parsed",
        "rights_verified","canonical_admitted","backtesting_ready","earlier_failed_archive_cause_established","HTTP_framing_verified_here"}
    zero_keys={"filings_extracted_or_admitted","files_read_written","new_requests","SDK_calls","outcome_looks"}
    other_keys={"schema","fixture_only","prefix_bytes","prefix_sha256","finite_privacy_screened","privacy_source_path",
        "privacy_source_sha256","gzip_magic_at_prefix_start","completed_gzip_members_with_observed_valid_trailers",
        "last_observed_gzip_member_incomplete","decoded_prefix_bytes","decoded_observation_bytes","initial_decoded_opening_markers",
        "first_tar_header_observation"}
    _need(type(descriptor) is dict and descriptor.get("schema")==core.SCHEMA and descriptor.get("fixture_only") is fixture
        and set(descriptor)==false_keys|zero_keys|other_keys
        and descriptor.get("prefix_bytes")==PREFIX_BYTES and type(descriptor.get("prefix_bytes")) is int
        and descriptor.get("finite_privacy_screened") is True and type(descriptor.get("prefix_sha256")) is str
        and _SHA.fullmatch(descriptor["prefix_sha256"]) and len(_raw(descriptor))<=core.MAX_DESCRIPTOR_BYTES,
        "descriptor_refused","inspection")
    _need(all(descriptor[key] is False for key in false_keys)
        and all(type(descriptor[key]) is int and descriptor[key]==0 for key in zero_keys)
        and descriptor["privacy_source_path"]==core.PRIVACY_PATH and descriptor["privacy_source_sha256"]==core.PRIVACY_SHA256
        and descriptor["gzip_magic_at_prefix_start"] is True
        and type(descriptor["last_observed_gzip_member_incomplete"]) is bool
        and type(descriptor["completed_gzip_members_with_observed_valid_trailers"]) is int
        and 0<=descriptor["completed_gzip_members_with_observed_valid_trailers"]<=core.MAX_GZIP_MEMBERS
        and type(descriptor["decoded_prefix_bytes"]) is int and 0<=descriptor["decoded_prefix_bytes"]<=core.MAX_DECODED_BYTES
        and type(descriptor["decoded_observation_bytes"]) is int
        and descriptor["decoded_observation_bytes"]==min(descriptor["decoded_prefix_bytes"],core.MAX_OBSERVATION_BYTES),
        "descriptor_refused","inspection")
    def markers(rows):
        _need(type(rows) is list and len(rows)<=6 and all(type(row) is dict and set(row)=={"offset","family"}
            and type(row["offset"]) is int and row["offset"] in {0,256,266}
            and type(row["family"]) is str and row["family"] in {"SUBMISSION","SEC-DOCUMENT"} for row in rows)
            and len({(row["offset"],row["family"]) for row in rows})==len(rows),"descriptor_refused","inspection")
    markers(descriptor["initial_decoded_opening_markers"])
    tar=descriptor["first_tar_header_observation"]
    tar_keys={"header_bytes_available","header_checksum_matches","header_profile","first_block_all_zero","type_class",
        "declared_payload_bytes","name_has_nc_suffix","first_physical_span_within_observation_prefix","payload_opening_markers",
        "PDS_control_validated","name_or_payload_values_returned","whole_member_integrity_verified"}
    _need(type(tar) is dict and set(tar)==tar_keys and type(tar["header_bytes_available"]) is int
        and tar["header_bytes_available"]==min(descriptor["decoded_observation_bytes"],512)
        and type(tar["header_checksum_matches"]) is bool and type(tar["header_profile"]) is str
        and tar["header_profile"] in {"not_observed","first_block_not_supported_checksum_header","ustar-finite","v7-finite","unsupported_magic_or_extension"}
        and type(tar["first_block_all_zero"]) in {bool,type(None)}
        and (tar["type_class"] is None or type(tar["type_class"]) is str and tar["type_class"] in
            {"regular","directory","hardlink","symlink","pax","pax-global","gnu-longname","gnu-longlink","gnu-sparse","other"})
        and (tar["declared_payload_bytes"] is None or type(tar["declared_payload_bytes"]) is int and 0<=tar["declared_payload_bytes"]<8**12)
        and type(tar["name_has_nc_suffix"]) in {bool,type(None)} and type(tar["first_physical_span_within_observation_prefix"]) is bool
        and all(tar[key] is False for key in ("PDS_control_validated","name_or_payload_values_returned","whole_member_integrity_verified")),
        "descriptor_refused","inspection")
    markers(tar["payload_opening_markers"])
    if tar["header_bytes_available"]<512:
        _need(tar["header_profile"]=="not_observed" and tar["header_checksum_matches"] is False
            and tar["first_block_all_zero"] is tar["type_class"] is tar["declared_payload_bytes"] is tar["name_has_nc_suffix"] is None,
            "descriptor_refused","inspection")
    if tar["header_checksum_matches"]:
        size=tar["declared_payload_bytes"]
        _need(tar["header_profile"] in {"ustar-finite","v7-finite","unsupported_magic_or_extension"}
            and type(tar["first_block_all_zero"]) is bool and type(tar["name_has_nc_suffix"]) is bool and tar["type_class"] is not None
            and tar["first_physical_span_within_observation_prefix"] is (size is not None and 512+size+(-size)%512<=descriptor["decoded_observation_bytes"]),
            "descriptor_refused","inspection")
    else:_need(tar["type_class"] is tar["declared_payload_bytes"] is tar["name_has_nc_suffix"] is None
        and tar["first_physical_span_within_observation_prefix"] is False and not tar["payload_opening_markers"],"descriptor_refused","inspection")
    return value


def _refusal_valid(value):
    _need(type(value) is dict and set(value)=={"phase","code"} and type(value["phase"]) is str
        and type(value["code"]) is str and (value["code"] in _CORE_CODES.get(value["phase"],())
            or value["phase"] in _PHASES and value["code"] in _OWN_CODES|_HEADER_CODES),"descriptor_refused","inspection")
    return value


def _result_valid(value,rsha,csha,ssha):
    keys={"schema","reservation_sha256","claim_sha256","start_sha256","raw_transport_invocations","remote_request_count_measured",
        "http_status","body_read_attempted","prefix_retained","disposition","declared_carrier_total_bytes","total_is_declared_not_measured",
        "prefix_bytes","prefix_sha256","headers_sha256","inspection_sha256","refusal","contact_value_stored_or_hashed",
        "whole_carrier_retained_or_verified","individual_parent_requests","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/result"
        and (value["reservation_sha256"],value["claim_sha256"],value["start_sha256"])==(rsha,csha,ssha)
        and type(value["raw_transport_invocations"]) is int and value["raw_transport_invocations"]==1
        and value["remote_request_count_measured"] is False and type(value["body_read_attempted"]) is bool
        and type(value["prefix_retained"]) is bool and value["total_is_declared_not_measured"] is True
        and value["contact_value_stored_or_hashed"] is value["whole_carrier_retained_or_verified"] is False
        and type(value["individual_parent_requests"]) is int and value["individual_parent_requests"]==0
        and _raw(value["authority"])==_raw(_authority()),"readback_refused","readback")
    status=value["http_status"]
    _need(status is None or type(status) is int and 100<=status<=599,"readback_refused","readback")
    if value["prefix_retained"]:
        _need(status==206 and value["body_read_attempted"] is True and value["refusal"] is None
            and value["disposition"]=="prefix_format_only_noncanonical" and type(value["prefix_bytes"]) is int
            and value["prefix_bytes"]==PREFIX_BYTES and type(value["declared_carrier_total_bytes"]) is int
            and PREFIX_BYTES<value["declared_carrier_total_bytes"]<10**12,"readback_refused","readback")
        for key in ("prefix_sha256","headers_sha256","inspection_sha256"):
            _need(type(value[key]) is str and _SHA.fullmatch(value[key]),"readback_refused","readback")
    else:
        _need(value["disposition"]=="prefix_refused_no_retention_no_retry" and all(value[key] is None for key in
            ("declared_carrier_total_bytes","prefix_bytes","prefix_sha256","headers_sha256","inspection_sha256")),"readback_refused","readback")
        _refusal_valid(value["refusal"])
        if value["refusal"]["code"] in _HEADER_CODES:_need(value["body_read_attempted"] is False,"readback_refused","readback")
    return value


def _complete(identity,fixture,plan,rsha,result,rpin):
    return {"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "reservation_sha256":rsha,"input_preflight_sha256":_sha(_raw(plan)),"registration_sha256":_sha(_raw(registration())),
        "result_sha256":rpin,"result":result,"authority":_authority()}


def _run(*,root,identity,plan,contact,transport,fixture,guard,inputs=None,activation=None):
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(callable(transport) and transport is not _transport and contact not in {contact_io._stdin_contact,contact_io._getpass_contact},"fixed_actual_front_required")
    else:_need(root==LANE_ROOT and transport is _transport and contact is contact_io._stdin_contact and type(inputs) is _Inputs,"fixed_actual_front_required");_activated(activation,identity)
    forms=_forms(identity,fixture,plan);guard();phase="capacity";folders=[];fresh=lock=None;locked=False
    try:
        _preoutput_capacity(root);phase="namespace"
        try:fresh=custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        except custody.ArchiveAssessmentRunnerError as error:
            if error.args==("output_cannot_resume_or_overwrite",):raise PrefixCaptureError("fresh_namespace_already_exists",phase) from None
            raise
        top=old._Output(root.joinpath(*ARTIFACT_PARTS));folders.append(top)
        claims=old._Output(top.path/"claims",create=True);folders.append(claims)
        runs=old._Output(top.path/"runs",create=True);folders.append(runs)
        top.publish("scope.lock",LOCK_BYTES);lock=os.open("scope.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;version=old._version(os.fstat(lock));_capacity(top.fd)
        os.mkdir(AUDIT_ID,0o700,dir_fd=runs.fd);os.fsync(runs.fd);run=old._Output(runs.path/AUDIT_ID);folders.append(run)
        names=set();claimnames=set()
        def check():
            guard();fresh.recheck()
            if inputs:inputs.check();_need(inputs.metadata==plan["inputs"],"inputs_changed","inputs")
            for folder in folders:folder.check()
            _need(version==old._version(os.fstat(lock))==old._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False))
                and set(os.listdir(top.fd))=={"scope.lock","claims","runs"} and set(os.listdir(runs.fd))=={AUDIT_ID}
                and set(os.listdir(run.fd))==names and set(os.listdir(claims.fd))==claimnames,"output_changed",phase)
        def publish(name,value):
            pin=run.publish(name,_raw(value));names.add(name);check();return pin
        phase="reservation";rsha=publish("reservation.json",forms["reservation.json"]);publish("input-preflight.json",plan)
        phase="contact";private=privacy._contact(contact(),observed=not fixture)
        publish("contact-validated.json",{"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
        phase="claim";csha=claims.publish(_claim_name(),_raw(forms["claim.json"]));claimnames.add(_claim_name());check()
        phase="start";ssha=publish("request-start.json",forms["request-start.json"])
        def prove():
            check();_need(claims.read(_claim_name())==_raw(forms["claim.json"])
                and run.read("request-start.json")==_raw(forms["request-start.json"]),"dispatch_refused","transport")
        request_headers={"User-Agent":"InsiderBuyingResearch-Prefix/1.0 ("+private+")","Accept":"application/gzip",
            "Accept-Encoding":"identity","Connection":"close","Range":RANGE}
        phase="transport";response=None;context=None;status=None;attempted=False;refusal=None
        try:
            if fixture:prove();response=transport(URL,request_headers,PREFIX_BYTES)
            else:context=_Dispatch(_TOKEN,activation,identity,guard,prove,request_headers);response=_transport(context)
        except Exception as error:
            if not fixture:
                _need(context is not None and context.attempted,"transport_front_refused","transport")
                status=context.status;attempted=context.body_read_attempted
            code="absolute_transport_deadline" if type(error) is PrefixCaptureError and error.args==("absolute_transport_deadline",) else "idle_timeout" if isinstance(error,TimeoutError) else "ambiguous_transport"
            refusal={"phase":"transport","code":code}
        retained=False;prefix_pin=header_pin=inspection_pin=declared=None
        if response is not None:
            _need(type(response) is PrefixHttpResult and type(response.status) is int and 100<=response.status<=599
                and type(response.body_read_attempted) is bool,"metadata_refused","transport")
            status=response.status;attempted=response.body_read_attempted;refusal=response.refusal
            if refusal is None:
                phase="inspection"
                try:
                    pairs,total=_range_headers(status,response.headers)
                    _need(attempted is True and response.declared_total==total,"metadata_refused","headers")
                    if fixture:
                        try:inspection=_inspect(response.body,pairs,private,fixture=True)
                        except core.PrefixFormatError as error:
                            code=_core_error(error);_need(code is not None,"descriptor_refused","inspection")
                            inspection={"schema":SCHEMA+"/inspection-refusal","refusal":code}
                    else:inspection=_child("inspect",identity,_raw({"contact":private,"headers":pairs,"bytes":PREFIX_BYTES,"inputs":plan["inputs"]})+b"\n"+response.body)
                    if inspection.get("schema")==SCHEMA+"/inspection-refusal":
                        _need(set(inspection)=={"schema","refusal"},"descriptor_refused","inspection");refusal=_refusal_valid(inspection["refusal"])
                    else:
                        _inspection_valid(inspection,fixture)
                        _need(inspection["descriptor"]["prefix_sha256"]==_sha(response.body)
                            and inspection["headers_sha256"]==_sha(_raw(pairs)) and inspection["declared_carrier_total_bytes"]==total,
                            "descriptor_refused","inspection")
                        phase="publication";prefix_pin=run.publish("prefix.bin",response.body,cap=PREFIX_BYTES);names.add("prefix.bin");check()
                        header_pin=_sha(_raw(pairs));publish("response-headers.json",{"headers":pairs})
                        inspection_pin=publish("inspection.json",inspection);retained=True;declared=total
                except PrefixCaptureError as error:refusal=_safe_error(error,phase)
                except Exception:refusal={"phase":"inspection","code":"native_boundary_refused"}
        check()
        result={"schema":SCHEMA+"/result","reservation_sha256":rsha,"claim_sha256":csha,"start_sha256":ssha,
            "raw_transport_invocations":1,"remote_request_count_measured":False,"http_status":status,"body_read_attempted":attempted,
            "prefix_retained":retained,"disposition":"prefix_format_only_noncanonical" if retained else "prefix_refused_no_retention_no_retry",
            "declared_carrier_total_bytes":declared,"total_is_declared_not_measured":True,"prefix_bytes":PREFIX_BYTES if retained else None,
            "prefix_sha256":prefix_pin,"headers_sha256":header_pin,"inspection_sha256":inspection_pin,"refusal":refusal,
            "contact_value_stored_or_hashed":False,"whole_carrier_retained_or_verified":False,"individual_parent_requests":0,"authority":_authority()}
        phase="complete";_result_valid(result,rsha,csha,ssha);rpin=publish("request-result.json",result)
        report=publish("complete.json",_complete(identity,fixture,plan,rsha,result,rpin));phase="final";check()
        return {"schema":SCHEMA+"/public","complete_sha256":report,"result":result,"authority":_authority()}
    except Exception as error:
        safe=_safe_error(error,phase);raise PrefixCaptureError(safe["code"],safe["phase"]) from None
    finally:
        active=sys.exc_info()[0] is not None
        try:publication._close_all(folders,fresh,lock,locked)
        except Exception:
            if not active:raise PrefixCaptureError("cleanup_refused","cleanup") from None


def _invented(*,root,transport,contact=lambda:"invented@unit.test",guard=lambda:None):
    sources={SELF_PATH:"a"*64,TEST_PATH:"b"*64};identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    plan={"schema":SCHEMA+"/preflight","execution_identity":identity,"inputs":{"fixture_only":True},
        "new_requests":0,"contact_reads":0,"namespace_created":False}
    return _run(root=Path(root),identity=identity,plan=plan,transport=transport,contact=contact,fixture=True,guard=guard)


def _verify_files(root,pin,private,*,fixture,current_identity=None):
    if fixture:publication._fixture_root(root);publication._native_fixture_denial()
    else:previous._isolated();source_runner._prove_isolation();_current(current_identity);_need(root==LANE_ROOT,"fixed_actual_front_required")
    _need(type(pin) is str and _SHA.fullmatch(pin),"readback_refused","readback")
    folders=[];lock=None;held=None
    try:
        if not fixture:held=_Inputs(root)
        def opened(path):
            value=directory._ReadbackDirectory(path);folders.append(value);return value
        top=opened(root.joinpath(*ARTIFACT_PARTS));claims=opened(top.path/"claims");runs=opened(top.path/"runs");run=opened(runs.path/AUDIT_ID)
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);version=privacy._file_version(os.fstat(lock))
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(top.read("scope.lock")==LOCK_BYTES and top.inventory=={"scope.lock","claims","runs"}
            and runs.inventory=={AUDIT_ID} and claims.inventory=={_claim_name()},"readback_refused","readback")
        craw=run.read("complete.json",cap=MAX_CONTROL);_need(_sha(craw)==pin,"readback_refused","readback")
        complete=_control(craw);identity=complete["execution_identity"];_check_identity(identity,root)
        plan=_control(run.read("input-preflight.json",cap=MAX_CONTROL));forms=_forms(identity,fixture,plan)
        if held:_need(plan["inputs"]==held.metadata,"inputs_changed","readback")
        rsha=_sha(_raw(forms["reservation.json"]));result_raw=run.read("request-result.json",cap=MAX_CONTROL);result=_control(result_raw)
        _result_valid(result,rsha,_sha(_raw(forms["claim.json"])),_sha(_raw(forms["request-start.json"])))
        _need(plan["execution_identity"]==identity and run.read("reservation.json",cap=MAX_CONTROL)==_raw(forms["reservation.json"])
            and claims.read(_claim_name())==_raw(forms["claim.json"]) and run.read("request-start.json")==_raw(forms["request-start.json"])
            and craw==_raw(_complete(identity,fixture,plan,rsha,result,_sha(result_raw)))
            and run.read("contact-validated.json")==_raw({"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,
                "contact_value_stored_or_hashed":False}),"readback_refused","readback")
        names={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json","complete.json"}
        if result["prefix_retained"]:
            names|={"prefix.bin","response-headers.json","inspection.json"}
            run._versions();raw=run.tree.read("prefix.bin",cap=PREFIX_BYTES);hraw=run.tree.read("response-headers.json",cap=16384);run._versions()
            headers=_control(hraw);_need(type(headers) is dict and set(headers)=={"headers"},"readback_refused","readback")
            pairs,total=_range_headers(206,headers["headers"])
            _need(hraw==_raw({"headers":pairs}),"readback_refused","readback")
            observed=_inspect(raw,pairs,private,fixture=fixture)
            mraw=run.read("inspection.json",cap=core.MAX_DESCRIPTOR_BYTES+16384)
            _need(run.read("prefix.bin",cap=PREFIX_BYTES)==raw and run.read("response-headers.json",cap=16384)==hraw
                and _raw(observed)==mraw and _sha(raw)==result["prefix_sha256"] and _sha(_raw(pairs))==result["headers_sha256"]
                and _sha(mraw)==result["inspection_sha256"] and total==result["declared_carrier_total_bytes"],"readback_refused","readback")
        _need(run.inventory==names,"readback_refused","readback")
        for folder in folders:folder.check()
        if held:held.check()
        _need(version==privacy._file_version(os.fstat(lock))==privacy._file_version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed","readback")
        if not fixture:_current(current_identity)
        return {"schema":SCHEMA+"/readback","complete_sha256":pin,"result":result,"producer_execution_identity":identity,
            "original_input_plan":plan,"current_contact_prefix_rescreened":result["prefix_retained"],
            "original_contact_screen_replayed":False,"original_current_contact_equality_attested":False,
            "whole_carrier_replayed_or_verified":False,"new_requests":0,"authority":_authority()}
    finally:publication._close_all([*folders,*([held] if held else [])],None,lock,lock is not None)


def run_actual(*,expected_head):
    identity=_identity(expected_head);plan=_child("preflight",identity);_parent_proofs(plan)
    _need(plan.get("execution_identity")==identity and plan.get("schema")==SCHEMA+"/preflight","preflight_refused","native_preflight")
    _forms(identity,False,plan);held=None;activation=None
    def guard():_need(_identity(expected_head)==identity,"source_changed")
    try:
        held=_Inputs(LANE_ROOT);_need(held.metadata==plan["inputs"],"inputs_changed","inputs")
        activation=_Activation(identity,guard,held);_ACTIVATIONS[activation]=(_raw(identity),id(guard),id(held))
        return _run(root=LANE_ROOT,identity=identity,plan=plan,contact=contact_io._stdin_contact,transport=_transport,
            fixture=False,guard=guard,inputs=held,activation=activation)
    finally:
        if activation:_ACTIVATIONS.pop(activation,None)
        source_runner.selector._close_all((held,),phase="prefix_actual_cleanup")


def verify_actual(*,expected_head,expected_report_sha256):
    identity=_identity(expected_head);plan=_child("preflight",identity);_parent_proofs(plan)
    private=privacy._contact(contact_io._stdin_contact(),observed=True)
    value=_child("readback",identity,_raw({"contact":private,"complete_sha256":expected_report_sha256})+b"\n")
    previous._source_git(value["producer_execution_identity"]);_parent_proofs(value["original_input_plan"])
    _need({**value["original_input_plan"],"execution_identity":identity}==plan,"inputs_changed","readback");_current(identity)
    _need(_identity(expected_head)==identity,"source_changed","readback")
    return {k:v for k,v in value.items() if k!="original_input_plan"}


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise PrefixCaptureError("private_arguments_refused","arguments")


def main(argv=None):
    saved=contact_io._protect_stdin_echo()
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--contact-stdin",action="store_true")
        parser.add_argument("--verify-report-sha256");args=parser.parse_args(argv)
        _need(args.contact_stdin,"private_contact_mode_refused","arguments")
        value=verify_actual(expected_head=args.expected_head,expected_report_sha256=args.verify_report_sha256) if args.verify_report_sha256 else run_actual(expected_head=args.expected_head)
        print(_raw(value).decode());return 0 if args.verify_report_sha256 or value["result"]["prefix_retained"] else 2
    except Exception as error:
        print(_raw({"disposition":"prefix_capture_refused",**_safe_error(error,"source")}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
