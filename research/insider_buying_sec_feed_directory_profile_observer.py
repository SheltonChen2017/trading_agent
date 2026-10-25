"""Offline structural observation of the exact retained Q2 directory response.

No transport/contact API or archive is opened. Only whitelisted directory
metadata reaches the public result. The lossless fixed-response/control witness
is bounded trusted IPC, independently checked, then omitted by the parent.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_sec_feed_directory_inventory_v2 as producer
from research import insider_buying_sec_feed_directory_stopped_controls as codec
from research import insider_buying_pilot_sec_parent_audit_runner as base


SELF_PATH = "research/insider_buying_sec_feed_directory_profile_observer.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_directory_profile_observer.py"
SCHEMA = "insider-sec-feed-directory-profile-observer-v2"
AUDIT_ID = "ib-sec-feed-directory-2021q2-profile-observation-v2-20261025-once"
LANE_ROOT, LANE_BRANCH = base.LANE_ROOT, base.LANE_BRANCH
EMPTY_CACHE_PREFIX = "/var/empty/insider-sec-feed-directory-profile-v2-no-bytecode"
PRECEDING_OBSERVER_HEAD = "20e5dbfc7c3b640b9f3054273767a330ea61883f"
PRECEDING_OBSERVER_SOURCE_SHA256 = "807512fc7f9f13883acb26238b62e45a9ff9ec25e3afde8fb9f07e1958cb15c8"
PRODUCER_HEAD = "6011ae9d561fb7308249c55677055e4fa62c1150"
PRODUCER_SOURCE_SHA256 = "c04c226f77e7dde3a94d31b83c23abea25e736997bf624caf49801da166e66a4"
PRODUCER_TEST_SHA256 = "8bfa62da7376162a823cdb03e99b135b84c9ef57bcf92ee7c5849643cbb976b2"
MAX_CONTROL_BYTES, MAX_REPORT_BYTES = codec.MAX_CONTROL_BYTES, codec.MAX_REPORT_BYTES
CONTROL_TIMEOUT = 60
RUN_NAMES = frozenset({"reservation.json", "contact-validated.json", "request-start.json", "response.bin",
    "response-headers.json", "request-result.json", "complete.json"})
CONTROL_NAMES = frozenset({"scope.lock", "claim.json", *RUN_NAMES})
KNOWN_KEYS = frozenset({"directory", "name", "parent-dir", "item", "type", "size", "last-modified", "href",
    "path", "parent", "items", "count", "modified", "last_modified", "encoding", "content-type"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SEC_PATH = re.compile(r"/?Archives/edgar/Feed(?:/[0-9]{4}(?:/QTR[1-4])?)?/?\Z")
_ARCHIVE = re.compile(r"2021(?:04(?:0[1-9]|[12][0-9]|30)|05(?:0[1-9]|[12][0-9]|3[01])|06(?:0[1-9]|[12][0-9]|30))\.nc\.tar\.gz\Z")
_SIZE = re.compile(r"[+-]?[0-9]{1,32}(?:\.[0-9]{1,16})?(?:[eE][+-]?[0-9]{1,4})?(?: ?(?:B|KB|MB|GB|TB|bytes))?\Z", re.I)
_raw, _sha = base._raw, base._sha


class DirectoryProfileError(ValueError):
    """Fixed local diagnostic codes, never foreign snippets or exception text."""


def _need(value, code):
    if not value: raise DirectoryProfileError(code)


@dataclass(frozen=True, slots=True)
class CapturePins:
    complete_sha256: str
    response_sha256: str
    response_bytes: int
    execution_head: str
    source_count: int
    source_inventory_sha256: str


ACTUAL_PINS = CapturePins("1590c2723a1f0745247791116dddada391708819cd50c713bb3a68fe2a441361",
    "fa08fe5fefb4f4514a71e2c0192614dd649b05285e9050d1986e134fa602775c", 8695,
    PRODUCER_HEAD, 106, "eaa86f0d7384a3103cac3c0c2e7203e9d351f074b10bc40091b8988213cebb54")
REGISTRATION = {"schema": SCHEMA+"/registration", "audit_id": AUDIT_ID,
    "preceding_observer_execution_head":PRECEDING_OBSERVER_HEAD,
    "preceding_observer_source_sha256":PRECEDING_OBSERVER_SOURCE_SHA256,
    "preceding_observer_disposition":"parent-observed source_identity_refused before launcher/audit hook/retained inputs; no observation payload",
    "preceding_observer_failure_rewritten":False,
    "producer_audit_id": producer.AUDIT_ID, "producer_execution_head": PRODUCER_HEAD,
    "producer_source_sha256": PRODUCER_SOURCE_SHA256, "producer_test_sha256": PRODUCER_TEST_SHA256,
    "complete_sha256": ACTUAL_PINS.complete_sha256, "response_sha256": ACTUAL_PINS.response_sha256,
    "response_bytes": ACTUAL_PINS.response_bytes, "producer_source_count": ACTUAL_PINS.source_count,
    "producer_source_inventory_sha256": ACTUAL_PINS.source_inventory_sha256,
    "exact_retained_leaf_count": 9, "worker_invocations": 1, "new_provider_requests": 0,
    "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
    "native_network_fork_allwrite_securityexec_denial": True, "original_namespace_mutated": False,
    "persistent_result_published": False, "original_profile_widened": False,
    "raw_directory_witness": "fixed retained response and controls in bounded trusted IPC only; omitted after independent parent validation",
    "source_authenticated_here": False, "canonical_admitted": False, "backtesting_ready": False}


class _IntegerLexeme(str): pass
class _DecimalLexeme(str): pass


def _foreign(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= producer.MAX_RESPONSE_BYTES, "foreign_byte_bound")
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "foreign_duplicate_key"); value[key] = child
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_int=_IntegerLexeme, parse_float=_DecimalLexeme,
            parse_constant=lambda _: _need(False, "foreign_nonfinite_refused"))
        pending, nodes = [(value, 0)], 0
        while pending:
            item, depth = pending.pop(); nodes += 1
            _need(nodes <= 4096 and depth <= 24, "foreign_resource_bound")
            if type(item) is dict:
                _need(len(item) <= 128 and all(type(k) is str and len(k) <= 128 for k in item), "foreign_object_bound")
                pending.extend((child, depth+1) for child in item.values())
            elif type(item) is list:
                _need(len(item) <= 256, "foreign_array_bound"); pending.extend((child, depth+1) for child in item)
            elif isinstance(item, str): _need(len(item) <= 8192, "foreign_string_bound")
        return value
    except DirectoryProfileError: raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise DirectoryProfileError("foreign_json_or_encoding_refused") from None


def _kind(value):
    if type(value) is _IntegerLexeme: return "integer-lexeme"
    if type(value) is _DecimalLexeme: return "decimal-lexeme"
    return {dict:"object", list:"array", str:"string", bool:"boolean", type(None):"null"}.get(type(value), "other")


def _fields(value):
    if type(value) is not dict: return {}, 0
    return {key:_kind(value[key]) for key in sorted(set(value)&KNOWN_KEYS)}, len(set(value)-KNOWN_KEYS)


def observe_directory_profile(raw):
    """Public shape only; numbers remain uninterpreted lexical strings."""
    _need(type(raw) is bytes and 0<len(raw)<=producer.MAX_RESPONSE_BYTES,"profile_response_byte_bound")
    try: value = _foreign(raw); parse_code = None
    except DirectoryProfileError as exc: value = None; parse_code = str(exc)
    try: producer.parse_directory_inventory(raw); profile_code = None
    except producer.FeedDirectoryError as exc:
        code = str(exc)
        profile_code = code if code in {"foreign_json_refused", "directory_envelope_refused", "directory_profile_refused",
            "directory_item_refused", "directory_filename_refused", "directory_date_refused", "directory_advertisement_refused"} else "candidate_profile_refused"
    top_fields, top_unknown = _fields(value)
    directory = value.get("directory") if type(value) is dict else None
    directory_fields, directory_unknown = _fields(directory)
    items = directory.get("item") if type(directory) is dict else None
    safe_paths = {}
    for key in ("name", "parent-dir"):
        item = directory.get(key) if type(directory) is dict else None
        safe_paths[key] = item if type(item) is str and _SEC_PATH.fullmatch(item) else None
    rows, signatures, types = [], {}, {}
    if type(items) is list:
        for ordinal, item in enumerate(items, 1):
            fields, unknown = _fields(item)
            signature = _raw({"known_keys":sorted(fields), "unknown_field_count":unknown}).decode()
            signatures[signature] = signatures.get(signature, 0)+1
            for key, kind in fields.items(): types[(key,kind)] = types.get((key,kind), 0)+1
            name = item.get("name") if type(item) is dict else None
            size = item.get("size") if type(item) is dict else None
            size_text = str(size) if type(size) in {str,_IntegerLexeme,_DecimalLexeme} and (size=="" or _SIZE.fullmatch(size)) else None
            source_type = item.get("type") if type(item) is dict else None
            rows.append({"source_ordinal":ordinal, "item_type":_kind(item), "known_field_types":fields,
                "unknown_field_count":unknown, "listed_q2_archive_filename": name if type(name) is str and _ARCHIVE.fullmatch(name) else None,
                "source_type_class":source_type if type(source_type) is str and source_type in {"file","dir"} else "other-or-absent",
                "size_text":size_text, "size_value_type":_kind(size), "size_unit_qualified":False})
    return {"schema":SCHEMA+"/observation", "response_sha256":_sha(raw), "response_bytes":len(raw),
        "foreign_json_parse_refusal_code":parse_code, "root_type":"unparsed" if parse_code else _kind(value), "top_known_field_types":top_fields,
        "top_unknown_field_count":top_unknown, "directory_type":_kind(directory), "directory_known_field_types":directory_fields,
        "directory_unknown_field_count":directory_unknown, "safe_directory_paths":safe_paths,
        "items_type":_kind(items), "observed_item_count":len(items) if type(items) is list else None,
        "item_keyset_counts":[{**json.loads(key),"count":count} for key,count in sorted(signatures.items())],
        "item_value_type_counts":[{"field":key,"type":kind,"count":count} for (key,kind),count in sorted(types.items())],
        "items":rows, "executed_candidate_profile_refusal_code":profile_code,
        "executed_candidate_profile_accepted":profile_code is None, "new_inventory_qualified":False,
        "structural_parser_numeric_values_preserved_as_lexemes":True,
        "structural_parser_financial_numbers_converted":False,
        "legacy_candidate_replay_may_convert_and_sum_advertised_size_metadata":True,
        "arbitrary_text_snippets_emitted":False,
        "advertised_size_unit":"unqualified", "authority":producer._authority()}


def validate_capture(controls, pins=ACTUAL_PINS):
    _need(type(pins) is CapturePins and type(controls) is dict and set(controls)==CONTROL_NAMES
        and all(type(raw) is bytes and 0<len(raw)<= (producer.MAX_RESPONSE_BYTES if name=="response.bin" else MAX_CONTROL_BYTES)
            for name,raw in controls.items()), "capture_control_inventory")
    for digest in (pins.complete_sha256,pins.response_sha256,pins.source_inventory_sha256):
        _need(type(digest) is str and _SHA.fullmatch(digest), "capture_pin_digest")
    _need(type(pins.response_bytes) is int and 0<pins.response_bytes<=producer.MAX_RESPONSE_BYTES
        and type(pins.source_count) is int and 1<=pins.source_count<=2048
        and type(pins.execution_head) is str and re.fullmatch(r"[0-9a-f]{40}",pins.execution_head), "capture_pin_counts")
    _need(_sha(controls["complete.json"])==pins.complete_sha256 and _sha(controls["response.bin"])==pins.response_sha256
        and len(controls["response.bin"])==pins.response_bytes and controls["scope.lock"]==producer.LOCK_BYTES, "capture_pinned_bytes")
    decoded={name:codec._decode_control(raw) for name,raw in controls.items() if name not in {"scope.lock","response.bin"}}
    reservation=decoded["reservation.json"]; identity=reservation.get("execution_identity")
    producer._source_identity(identity,root=LANE_ROOT)
    _need(identity["head"]==pins.execution_head and len(identity["source_sha256"])==pins.source_count
        and identity["source_inventory_sha256"]==pins.source_inventory_sha256
        and identity["source_sha256"][producer.SELF_PATH]==PRODUCER_SOURCE_SHA256
        and identity["source_sha256"][producer.TEST_PATH]==PRODUCER_TEST_SHA256, "capture_producer_identity")
    _need(controls["reservation.json"]==_raw(producer._reservation(identity,False)), "capture_reservation_schema")
    forms=producer._preflight_controls(identity,False,root=LANE_ROOT)
    _need(controls["claim.json"]==forms["claim"] and controls["request-start.json"]==forms["start"]
        and controls["contact-validated.json"]==forms["contact"], "capture_claim_start_contact_links")
    headers=decoded["response-headers.json"]
    _need(set(headers)=={"headers"} and type(headers["headers"]) is list and len(headers["headers"])<=64
        and all(type(p) is list and len(p)==2 and all(type(v) is str for v in p) for p in headers["headers"]), "capture_header_schema")
    pairs=tuple(tuple(p) for p in headers["headers"])
    producer._strict_selected_response(producer.SecHttpResult(200,pairs,controls["response.bin"]),max_bytes=producer.MAX_RESPONSE_BYTES)
    result={"schema":producer.SCHEMA+"/result", "reservation_sha256":_sha(controls["reservation.json"]),
        "claim_sha256":_sha(controls["claim.json"]), "start_sha256":_sha(controls["request-start.json"]),
        "http_status":200, "transport_invocations":1, "disposition":"opaque_response_retained_inventory_unqualified",
        "response_retained":True, "response_sha256":pins.response_sha256, "response_bytes":pins.response_bytes,
        "response_headers_sha256":_sha(_raw(pairs)), "inventory_sha256":None, "inventory_qualified":False,
        "archive_requests":0, "accession_requests":0, "contact_value_stored_or_hashed":False}
    _need(controls["request-result.json"]==_raw(result) and controls["complete.json"]==_raw(producer._complete_control(
        identity,False,_sha(controls["reservation.json"]),result,_sha(controls["request-result.json"]),False)), "capture_result_complete_links")
    return identity


def _version(info): return codec._version(info)


class _HeldProfile:
    def __init__(self,root=LANE_ROOT,*,fixture=False):
        _need(type(fixture) is bool,"profile_fixture_mode_required")
        if fixture: producer.publication._fixture_root(root);producer.publication._native_fixture_denial()
        else: _need(root==LANE_ROOT,"fixed_profile_root");_isolated();base._prove_isolation()
        self.inputs,self.versions,self.lock_fd=base.custody._Inputs(root),[],None
        try:
            parts=producer.ARTIFACT_PARTS
            self.base=self.inputs.directory(parts);claims=self.inputs.directory((*parts,"claims"))
            runs=self.inputs.directory((*parts,"runs"));run=self.inputs.directory((*parts,"runs",producer.AUDIT_ID))
            for chain,names in ((self.base,{"scope.lock","claims","runs"}),(claims,{producer._claim_name()}),(runs,{producer.AUDIT_ID}),(run,RUN_NAMES)):
                info=os.fstat(chain.fd)
                _need(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,"profile_directory_owner_or_mode")
                self.versions.append((chain,None,_version(info)));self.inputs.inventory(chain,names)
            self.lock_fd=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.base.fd)
            fcntl.flock(self.lock_fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            self.controls={}
            for key,chain,path,name in (("scope.lock",self.base,parts,"scope.lock"),("claim.json",claims,(*parts,"claims"),producer._claim_name()),
                    *((name,run,(*parts,"runs",producer.AUDIT_ID),name) for name in sorted(RUN_NAMES))):
                _need(os.stat(name,dir_fd=chain.fd,follow_symlinks=False).st_uid==os.geteuid(),"profile_leaf_owner")
                cap=producer.MAX_RESPONSE_BYTES if key=="response.bin" else MAX_CONTROL_BYTES
                self.controls[key]=self.inputs.read(chain,path,name,limit=cap)
                self.versions.append((chain,name,_version(os.stat(name,dir_fd=chain.fd,follow_symlinks=False))))
            self.lock_version=_version(os.fstat(self.lock_fd));self.recheck()
        except BaseException:base.selector._close_all((self,),phase="profile_open_cleanup");raise

    def recheck(self):
        self.inputs.recheck()
        for chain,name,version in self.versions:
            info=os.fstat(chain.fd) if name is None else os.stat(name,dir_fd=chain.fd,follow_symlinks=False)
            _need(_version(info)==version,"profile_input_metadata_changed")
        _need(_version(os.fstat(self.lock_fd))==self.lock_version==_version(os.stat("scope.lock",dir_fd=self.base.fd,follow_symlinks=False)),"profile_lock_changed")

    def close(self): codec._HeldStopped.close(self)


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"profile_initial_isolated_flags_required")


def _identity(value):
    producer._source_identity(value,root=LANE_ROOT)
    _need({SELF_PATH,TEST_PATH}<=set(value["source_sha256"]),"profile_source_roster")
    return value


def _current(identity):
    fixed={**producer.REUSED_HELPER_SHA256,producer.SELF_PATH:PRODUCER_SOURCE_SHA256,producer.TEST_PATH:PRODUCER_TEST_SHA256}
    _need(base.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and base.custody._source_bytes(LANE_ROOT,tuple(base.FROZEN))==base.FROZEN
        and base.custody._source_bytes(LANE_ROOT,tuple(fixed))==fixed,"profile_current_or_frozen_source_changed")


def _result(identity,controls,*,pins=ACTUAL_PINS):
    validate_capture(controls,pins);observation=observe_directory_profile(controls["response.bin"])
    return {"schema":SCHEMA,"audit_id":AUDIT_ID,"registration":REGISTRATION,"registration_sha256":_sha(_raw(REGISTRATION)),
        "execution_identity":identity,"retained_control_pins":{name:{"sha256":_sha(raw),"bytes":len(raw)} for name,raw in controls.items()},
        "retained_control_witness":{name:raw.hex() for name,raw in controls.items()},"profile_observation":observation,
        "profile_observation_sha256":_sha(_raw(observation)),"native_network_fork_allwrite_securityexec_denial":True,
        "new_provider_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0,"backtests":0,
        "original_namespace_mutated":False,"original_profile_widened":False,"persistent_result_published":False,
        "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}


def _witness(result):
    witness=result.get("retained_control_witness")
    _need(type(witness) is dict and set(witness)==CONTROL_NAMES,"profile_witness_inventory")
    controls={}
    for name,value in witness.items():
        cap=producer.MAX_RESPONSE_BYTES if name=="response.bin" else MAX_CONTROL_BYTES
        _need(type(value) is str and 0<len(value)<=2*cap and len(value)%2==0 and re.fullmatch(r"[0-9a-f]+",value),"profile_witness_encoding")
        controls[name]=bytes.fromhex(value)
    return controls


def _validate(result,identity,*,pins=ACTUAL_PINS):
    _identity(identity)
    _need(type(result) is dict,"profile_result_object")
    expected=_result(identity,_witness(result),pins=pins)
    _need(_raw(result)==_raw(expected) and len(_raw(result))<=MAX_REPORT_BYTES,"profile_result_schema_or_crosslinks")
    return result


def _worker(identity):
    _isolated();_identity(identity);base._prove_isolation();_current(identity)
    held=None
    try:
        held=_HeldProfile();result=_result(identity,held.controls)
        held.recheck();_current(identity);_validate(result,identity);held.recheck();_current(identity)
        return result
    finally:base.selector._close_all((held,),phase="profile_worker_cleanup")


class _Guard(base._ParentGuard):
    def _write(self,path,*,mkdir=False):raise DirectoryProfileError("profile_parent_all_writes_refused")

    def _git(self,executable,command,cwd,env):
        if (executable=="/usr/bin/git" and type(command) in {list,tuple} and len(command)==3
                and command[:2] in ([executable,"show"],(executable,"show")) and type(command[2]) is str
                and self._lane_cwd(cwd) and type(env) is dict and env=={"PATH":"/usr/bin:/bin"}):
            commit,separator,name=command[2].partition(":")
            if (commit==PRODUCER_HEAD and separator and codec._PATH.fullmatch(name) and name.endswith(".py")
                    and not name.startswith("/") and all(p not in {"",".",".."} for p in name.split("/"))):return True
        return super()._git(executable,command,cwd,env)


def _committed_identity(head):
    identity=base.custody._identity(head)
    # Loaded/static Python closure binds modules, not their TEST_PATH literals.
    # Bind both producer images explicitly before its unchanged validator runs.
    own=base.custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH,producer.SELF_PATH,producer.TEST_PATH))
    for name,digest in own.items():_need(_sha(base.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"profile_uncommitted_source")
    sources={**identity["source_sha256"],**own}
    identity=_identity({**identity,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))});_current(identity)
    return identity


def _command(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;"
        "from research import insider_buying_sec_feed_directory_profile_observer as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept Exception: print('{\"disposition\":\"directory_profile_worker_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def run_actual_observation(expected_head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"profile_fixed_source")
    identity=_committed_identity(expected_head);command=_command(identity);sys.addaudithook(_Guard(expected_head,command))
    child=base.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=CONTROL_TIMEOUT,cap=MAX_REPORT_BYTES)
    _need(child.returncode==0 and child.stderr==b"" and 0<len(child.stdout)<=MAX_REPORT_BYTES,"profile_worker_refused")
    result=_validate(codec._decode_control(child.stdout.removesuffix(b"\n"),ipc=True),identity)
    original_identity=validate_capture(_witness(result))
    for name,digest in original_identity["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT,"show",PRODUCER_HEAD+":"+name))==digest,"profile_original_source_commit_mismatch")
    _need(_committed_identity(expected_head)==identity,"profile_parent_source_changed")
    public=dict(result);del public["retained_control_witness"]
    public.update({"raw_directory_control_witness_validated_and_omitted":True,"producer_source_inventory_matched_execution_commit":True,
        "observed_worker_stdout_bytes":len(child.stdout),"observed_worker_stdout_sha256":_sha(child.stdout)})
    return public


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=run_actual_observation(args.expected_head)
    except Exception:print('{"disposition":"directory_profile_observation_refused"}');return 2
    print(_raw(result).decode());return 0


if __name__=="__main__":raise SystemExit(main())
