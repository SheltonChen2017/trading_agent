"""Read-only, initially native-isolated observation of one held old prefix.

No output namespace, claim, HTTP, SDK, credentials or source rows are read here.
Metadata preflight never reads/hashes prefix.bin. Only analysis reads that
already-retained unit, rescreens it with the current anonymous-stdin contact,
and returns the new pure observer's closed, value-free witness. Historical
shape execution is provenance, not this execution or an additional replay.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from research import insider_buying_sec_feed_prefix_shape_runner_v1 as inherited
from research import insider_buying_sec_feed_prefix_nc_structure_v1 as pure

SCHEMA="insider-sec-feed-prefix-nc-observe-v1"
SELF_PATH="research/insider_buying_sec_feed_prefix_nc_observe_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_prefix_nc_observe_v1.py"
AUDIT_ID="ib-sec-feed-prefix-nc-structure-offline-v1-20261025-once"
LANE_ROOT,LANE_BRANCH=inherited.LANE_ROOT,inherited.LANE_BRANCH
EMPTY_CACHE_PREFIX,MAX_CONTROL=inherited.EMPTY_CACHE_PREFIX,inherited.MAX_CONTROL
WORKER_SECONDS=180
FROZEN={**inherited.FROZEN,
    inherited.SELF_PATH:"f959d2c6375353e510b0183032cab39bccaf15546cc3433937d6898960e8cee6",
    inherited.TEST_PATH:"db1591265cc04351e8bc966f3eab29f24cb18c004321989f8665d9f87ea7f609",
    inherited.REVIEW_TEST_PATH:"6b496f5edaf28803aecb879f28a121be938863d897f8451f2db1c4b88437e82f"}
SHAPE_PROVENANCE={"observed_head":"85f0857325b612d8941ced620c4e8c9dbdad49e7",
    "observed_source_count":144,"observed_source_inventory_sha256":"72f9ea8ac9bc0d8a5ab2bff455f63cbb08f4971d59da5475225f9dc3d8f29552",
    "historical_observed_provenance_not_new_execution":True,"old_shape_output_replayed_here":False}
capture,previous,custody,publication=(inherited.capture,inherited.previous,inherited.custody,inherited.publication)
contact_io,privacy,source_runner=inherited.contact_io,inherited.privacy,inherited.source_runner
_raw,_sha,_control=inherited._raw,inherited._sha,inherited._control
_PHASES=frozenset({"arguments","source","native_preflight","inputs","input","analysis","contact","final","cleanup"})
_CODES=frozenset({"private_arguments_refused","private_contact_mode_refused","fixed_actual_front_required",
    "source_changed","metadata_refused","inputs_changed","analysis_refused","native_boundary_refused","cleanup_refused"})


class PrefixNcObserveError(ValueError):
    def __init__(self,code,phase="source"):
        self.phase=phase if type(phase) is str and phase in _PHASES else "source"
        super().__init__(code)


def _need(value,code,phase="source"):
    if not value:raise PrefixNcObserveError(code,phase)


def _safe(error,phase):
    if type(error) is PrefixNcObserveError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in _CODES and type(getattr(error,"phase",None)) is str and error.phase in _PHASES:
        return {"phase":error.phase,"code":error.args[0]}
    if type(error) is pure.NCStructureError and type(getattr(error,"phase",None)) is type(getattr(error,"code",None)) is str:
        if (error.phase,error.code) in pure.SAFE_ERROR_CODES:return {"phase":error.phase,"code":error.code}
    return {"phase":phase if phase in _PHASES else "source","code":"analysis_refused" if phase=="analysis" else "metadata_refused"}


def _authority():
    return {"read_only_prefix_observation":True,"new_namespace_created":False,"files_written":0,
        "new_requests":0,"SDK_calls":0,"outcome_looks":0,"whole_carrier_verified":False,
        "source_or_PDS_or_XML_or_PIT_or_rights_verified":False,"canonical_admitted":False,"backtesting_ready":False,
        "earlier_failed_archive_cause_established":False}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"original_prefix_pins":dict(inherited.ORIGINAL_PINS),
        "original_producer_head":inherited.ORIGINAL_HEAD,"original_source_inventory_sha256":inherited.ORIGINAL_SOURCE_INVENTORY,
        "original_source_count":inherited.ORIGINAL_SOURCE_COUNT,"historical_shape_provenance":dict(SHAPE_PROVENANCE),
        "metadata_preflight_reads_or_hashes_raw_prefix":False,"current_contact_reloaded_once_for_analysis":True,
        "original_current_contact_equality_attested":False,"maximum_control_or_IPC_bytes":MAX_CONTROL,
        "native_worker_seconds":WORKER_SECONDS,"memory_policy":previous._memory_policy(),"authority":_authority()}


def _paths():return (SELF_PATH,TEST_PATH,pure.SELF_PATH,pure.TEST_PATH,pure.REVIEW_TEST_PATH,*FROZEN)


def _current(identity):
    publication._source_identity(identity,required_paths=_paths());inherited._current(identity)
    _need(custody._source_bytes(LANE_ROOT,tuple(FROZEN))==FROZEN,"source_changed")


def _identity(head):
    previous._isolated();_need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_front_required")
    value=inherited._identity(head);sources={**value["source_sha256"],**custody._source_bytes(LANE_ROOT,_paths())}
    for path,pin in sources.items():_need(_sha(custody._git(LANE_ROOT,"show",head+":"+path))==pin,"source_changed")
    value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))};_current(value);return value


def _plan(identity,inputs):
    return {"schema":SCHEMA+"/metadata-preflight","execution_identity":identity,"inputs":inputs,
        "registration_sha256":_sha(_raw(registration())),"raw_prefix_read_or_hashed":False,"contact_reads":0,"authority":_authority()}


def _metadata_valid(inputs,root):
    keys={"schema","external_pins","original_execution_identity","original_input_plan","control_sha256",
        "prefix_bytes_statted","raw_prefix_read_by_metadata_preflight","whole_carrier_read_or_verified"}
    controls={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json",
        "complete.json","response-headers.json","inspection.json"}
    _need(type(inputs) is dict and set(inputs)==keys and inputs["schema"]==inherited.SCHEMA+"/original-input"
        and type(inputs["external_pins"]) is dict and set(inputs["external_pins"])==set(inherited.ORIGINAL_PINS)
        and type(inputs["control_sha256"]) is dict and set(inputs["control_sha256"])==controls
        and all(type(pin) is str and inherited._SHA.fullmatch(pin) for pin in (*inputs["external_pins"].values(),*inputs["control_sha256"].values()))
        and all(inputs["external_pins"][name]==inputs["control_sha256"][name] for name in set(inherited.ORIGINAL_PINS)&controls)
        and type(inputs["prefix_bytes_statted"]) is int and inputs["prefix_bytes_statted"]==65536
        and inputs["raw_prefix_read_by_metadata_preflight"] is inputs["whole_carrier_read_or_verified"] is False,
        "metadata_refused","inputs")
    original=inputs["original_execution_identity"];capture._check_identity(original,root)
    fixture=root!=LANE_ROOT;forms=capture._forms(original,fixture,inputs["original_input_plan"])
    _need(all(inputs["control_sha256"][name]==_sha(_raw(value)) for name,value in forms.items() if name in controls)
        and inputs["external_pins"]["claim"]==_sha(_raw(forms["claim.json"])),"metadata_refused","inputs")
    if not fixture:_need(inputs["external_pins"]==inherited.ORIGINAL_PINS and original["head"]==inherited.ORIGINAL_HEAD
        and original["source_inventory_sha256"]==inherited.ORIGINAL_SOURCE_INVENTORY
        and len(original["source_sha256"])==inherited.ORIGINAL_SOURCE_COUNT,"metadata_refused","inputs")


def _plan_valid(plan,identity):
    inherited._check_identity(identity,Path(identity["root"]))
    _need(type(plan) is dict and set(plan)=={"schema","execution_identity","inputs","registration_sha256",
        "raw_prefix_read_or_hashed","contact_reads","authority"} and plan["schema"]==SCHEMA+"/metadata-preflight"
        and _raw(plan["execution_identity"])==_raw(identity) and type(plan["inputs"]) is dict
        and plan["inputs"].get("schema")==inherited.SCHEMA+"/original-input"
        and plan["registration_sha256"]==_sha(_raw(registration())) and plan["raw_prefix_read_or_hashed"] is False
        and type(plan["contact_reads"]) is int and plan["contact_reads"]==0
        and _raw(plan["authority"])==_raw(_authority()),"metadata_refused","native_preflight")
    _metadata_valid(plan["inputs"],Path(identity["root"]))
    _control(_raw(plan));return plan


def _witness_valid(value,identity,inputs,fixture):
    keys={"schema","fixture_only","execution_identity","registration_sha256","input_metadata_sha256",
        "original_complete_sha256","original_prefix_sha256","observation","current_contact_prefix_rescreened",
        "original_contact_screen_replayed","original_current_contact_equality_attested","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/witness" and value["fixture_only"] is fixture
        and _raw(value["execution_identity"])==_raw(identity) and value["registration_sha256"]==_sha(_raw(registration()))
        and value["input_metadata_sha256"]==_sha(_raw(inputs))
        and value["original_complete_sha256"]==inputs["external_pins"]["complete.json"]
        and value["original_prefix_sha256"]==inputs["external_pins"]["prefix.bin"]
        and value["current_contact_prefix_rescreened"] is True and value["original_contact_screen_replayed"] is False
        and value["original_current_contact_equality_attested"] is False
        and _raw(value["authority"])==_raw(_authority()),"analysis_refused","analysis")
    pure.validate_prefix_nc_observation(value["observation"],fixture_only=fixture)
    _need(value["observation"]["prefix_bytes"]==inputs["prefix_bytes_statted"]==65536,"analysis_refused","analysis")
    _control(_raw(value));return value


def _analyse(identity,private,held,*,fixture):
    raw=held.read_body()
    replay=capture._verify_files(held.root,held.pins["complete.json"],private,fixture=fixture,current_identity=None if fixture else identity)
    observed=pure.qualify_prefix_nc_structure(raw,privacy_contact=private,fixture_only=fixture)
    # No prefix hash of this local image is made until BOTH finite rescreens.
    _need(_sha(raw)==held.pins["prefix.bin"] and replay["producer_execution_identity"]==held.metadata["original_execution_identity"]
        and replay["current_contact_prefix_rescreened"] is True,"analysis_refused","analysis")
    held.check()
    value={"schema":SCHEMA+"/witness","fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(_raw(registration())),"input_metadata_sha256":_sha(_raw(held.metadata)),
        "original_complete_sha256":held.pins["complete.json"],"original_prefix_sha256":held.pins["prefix.bin"],
        "observation":observed,"current_contact_prefix_rescreened":True,"original_contact_screen_replayed":False,
        "original_current_contact_equality_attested":False,"authority":_authority()}
    return _witness_valid(value,identity,held.metadata,fixture)


def _worker(role,identity,*,publish=False):
    _need(role in {"preflight","observe"},"metadata_refused","arguments")
    previous._isolated();source_runner._prove_isolation();memory=previous._WorkerMemoryGuard();held=None;phase="source"
    try:
        _current(identity);capture._compile_sources(identity);_current(identity);memory.check();phase="inputs"
        held=inherited._HeldPrefix(LANE_ROOT)
        if role=="preflight":value=_plan_valid(_plan(identity,held.metadata),identity)
        else:
            phase="input";line=sys.stdin.buffer.readline(MAX_CONTROL+1)
            _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"metadata_refused",phase);supplied=_control(line[:-1])
            _need(type(supplied) is dict and set(supplied)=={"contact","inputs"}
                and _raw(supplied["inputs"])==_raw(held.metadata),"inputs_changed","inputs")
            private=privacy._contact(supplied["contact"],observed=True);phase="analysis"
            value=_analyse(identity,private,held,fixture=False)
        held.check();_current(identity);memory.check();result={"ok":True,"value":value}
        if not publish:return result
        encoded=_raw(result);_need(0<len(encoded)<=MAX_CONTROL,"metadata_refused","input")
        memory.check();sys.stdout.buffer.write(encoded+b"\n");sys.stdout.buffer.flush();memory.check()
    except Exception as error:
        result={"ok":False,"refusal":_safe(error,phase)}
        if not publish:return result
        sys.stdout.buffer.write(_raw(result)+b"\n");sys.stdout.buffer.flush();memory.check()
    finally:source_runner.selector._close_all((held,memory),phase="prefix_nc_observer_cleanup")


def _command(role,identity):
    _need(role in {"preflight","observe"},"metadata_refused")
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_prefix_nc_observe_v1 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:m._worker("+repr(role)+",identity,publish=True)\nexcept Exception:print('{\"ok\":false,\"refusal\":{\"phase\":\"source\",\"code\":\"native_boundary_refused\"}}');sys.exit(2)"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    _need(type(payload) is bytes and len(payload)<=MAX_CONTROL,"metadata_refused","input")
    try:value=inherited.old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    except Exception:raise PrefixNcObserveError("native_boundary_refused","native_preflight") from None
    _need(type(value) is dict and type(value.get("ok")) is bool,"native_boundary_refused")
    if value["ok"] is False:
        refusal=value.get("refusal");_need(set(value)=={"ok","refusal"} and type(refusal) is dict
            and set(refusal)=={"phase","code"} and type(refusal["phase"]) is type(refusal["code"]) is str
            and (refusal["phase"] in _PHASES and refusal["code"] in _CODES
                or (refusal["phase"],refusal["code"]) in pure.SAFE_ERROR_CODES),"native_boundary_refused")
        if (refusal["phase"],refusal["code"]) in pure.SAFE_ERROR_CODES:raise pure.NCStructureError(refusal["phase"],refusal["code"])
        raise PrefixNcObserveError(refusal["code"],refusal["phase"])
    _need(set(value)=={"ok","value"},"native_boundary_refused");return value["value"]


def _preflight(expected_head):
    identity=_identity(expected_head);plan=_plan_valid(_child("preflight",identity),identity)
    inherited._parent_proofs({"inputs":plan["inputs"]})
    _need(_identity(expected_head)==identity,"source_changed","final");return identity,plan


def preflight_actual(*,expected_head):
    """Metadata-only readiness; no private input, prefix bytes or output path."""
    identity,plan=_preflight(expected_head);return {"schema":SCHEMA+"/ready","execution_identity":identity,"plan":plan}


def observe_actual(*,expected_head):
    identity,plan=_preflight(expected_head);held=None
    try:
        held=inherited._HeldPrefix(LANE_ROOT);_need(_raw(held.metadata)==_raw(plan["inputs"]),"inputs_changed","inputs")
        _need(_identity(expected_head)==identity,"source_changed");held.check()
        private=privacy._contact(contact_io._stdin_contact(),observed=True)
        held.check();_current(identity)
        value=_child("observe",identity,_raw({"contact":private,"inputs":plan["inputs"]})+b"\n")
        _witness_valid(value,identity,plan["inputs"],False);held.check();_current(identity)
        _need(_identity(expected_head)==identity,"source_changed","final");return value
    finally:
        if held:held.close()


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise PrefixNcObserveError("private_arguments_refused","arguments")


def main(argv=None):
    saved=contact_io._protect_stdin_echo()
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--contact-stdin",action="store_true")
        parser.add_argument("--preflight-only",action="store_true");args=parser.parse_args(argv)
        _need(args.preflight_only or args.contact_stdin,"private_contact_mode_refused","arguments")
        value=preflight_actual(expected_head=args.expected_head) if args.preflight_only else observe_actual(expected_head=args.expected_head)
        print(_raw(value).decode());return 0
    except Exception as error:
        print(_raw({"disposition":"prefix_nc_observation_refused",**_safe(error,"source")}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
