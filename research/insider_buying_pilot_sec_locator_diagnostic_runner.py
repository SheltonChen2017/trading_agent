"""Protected read-only all-form diagnosis of the exact pilot locator quarantines.

Only retained master metadata and the observed selector controls are read.
Trusted parent Git checks are outside the initially native-denied worker.
Raw-free stdout is the sole new result; no namespace, transport or authority.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys

from research import insider_buying_pilot_sec_parent_audit_runner as base
from research import insider_buying_pilot_sec_fresh_selection_runner as selected
from research import insider_buying_pilot_sec_locator_diagnostic as pure

SELF_PATH = "research/insider_buying_pilot_sec_locator_diagnostic_runner.py"
PURE_PATH = "research/insider_buying_pilot_sec_locator_diagnostic.py"
SCHEMA = "insider-pilot-sec-locator-allforms-observer-v1"
AUDIT_ID = "ib-pilot-sec-locator-allforms-20261025-once"
LANE_ROOT = base.LANE_ROOT
SELECTION_PARTS = ("artifacts","insider_buying","pilot_sec_fresh_selection_v1",selected.AUDIT_ID)
SELECTION_PINS = {
    "reservation.json": ("1f07c7b2a7c0b6f633ca8a901be1a0d44010a4392c2e89d2e4078649b94fe8c7",13866),
    "terminal.json": ("260c3330c96de06a41f243cd5541d1ab58d58aa9a42321dac9290a0804c7d287",403),
    "complete.json": ("3dc2a3b85fa2c56ea9ddbe02263bcf7f4fa0945b316e0383c9c15d675ebd22b1",385209)}
SELECTION_HEAD = "b3aea4f10b7512eee2e1629a8417df0784cd4dbc"
SELECTION_SHA256 = "6b9db2ccaf59c19a202759cf2f5334cc0862ca8bb01eeba9121aa385b9828f56"
MAX_REPORT = 16*1024*1024
MAX_COMPRESSED = 8*1024*1024
MAX_DECODED_TOTAL = 512*1024*1024
CONTROL_TIMEOUT = 240
REGISTRATION = {
    "schema":SCHEMA+"/registration","audit_id":AUDIT_ID,
    "selection_audit_id":selected.AUDIT_ID,"selection_execution_head":SELECTION_HEAD,
    "selection_control_pins":{name:{"sha256":sha,"bytes":size} for name,(sha,size) in SELECTION_PINS.items()},
    "selection_sha256":SELECTION_SHA256,"context_periods":list(base.roster.CONTEXT_PERIODS),
    "quarantine_count":12,"pilot_quarantine_count":11,
    "master_commit_sha256":base.bootstrap.MASTER_COMMIT_SHA256,
    "master_report_sha256":base.bootstrap.MASTER_REPORT_SHA256,
    "master_scan_policy":"one full all-form physical-row diagnostic scan per affected quarter after genuine master integrity parse",
    "unaffected_master_policy":"gzip bytes hash-held; decoded/receipt descriptors bound to fixed producer report, not reparsed",
    "worker_invocations":1,"new_provider_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0,"backtests":0,
    "native_worker_network_fork_allwrite_securityexec_denial":True,"persistent_result_published":False,
    "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}
_raw,_sha = base._raw,base._sha


class LocatorRunnerError(ValueError):
    """Source-independent fixed refusal codes."""


def _need(value,code):
    if not value:raise LocatorRunnerError(code)


def _identity(value):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(LANE_ROOT) and value["branch"]==base.LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}",value["head"])
        and type(value["source_sha256"]) is dict and value["source_sha256"]
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"locator_execution_identity")
    _need({SELF_PATH,PURE_PATH}<=set(value["source_sha256"]),"locator_execution_source_roster")
    for name,digest in value["source_sha256"].items():
        _need(type(name) is str and 0<len(name)<=512 and not name.startswith("/")
            and all(p not in {"",".",".."} for p in name.split("/")),"locator_execution_source_path")
        pure._digest(digest)
    return value


def _selection_controls(controls):
    """Externally pinned control validation, not a fabricated factory."""
    _need(type(controls) is dict and set(controls)==set(SELECTION_PINS),"locator_selection_inventory")
    decoded={}
    for name,(digest,size) in SELECTION_PINS.items():
        raw=controls[name]
        _need(type(raw) is bytes and len(raw)==size and _sha(raw)==digest,"locator_selection_pin")
        decoded[name]=base._decode(raw)
    complete,reservation,terminal=(decoded[n] for n in ("complete.json","reservation.json","terminal.json"))
    _need(set(complete)=={"schema","audit_id","reservation_sha256","terminal_sha256","worker_result"}
        and complete["schema"]==selected.SCHEMA+"/complete" and complete["audit_id"]==selected.AUDIT_ID
        and complete["reservation_sha256"]==_sha(controls["reservation.json"])
        and complete["terminal_sha256"]==_sha(controls["terminal.json"]),"locator_selection_control_links")
    worker=complete["worker_result"]
    _need(type(worker) is dict and type(worker.get("locator_quarantines")) is list
        and len(worker["locator_quarantines"])==12,"locator_exact_quarantine_count")
    pins=tuple(_sha(_raw(row)) for row in worker["locator_quarantines"])
    pure._completed_row(controls["complete.json"],SELECTION_PINS["complete.json"][0],0,pins[0])
    _need(set(reservation)=={"schema","registration","execution_identity"}
        and reservation["schema"]==selected.SCHEMA+"/reservation"
        and reservation["registration"]==selected.REGISTRATION
        and reservation["execution_identity"]==worker["execution_identity"]
        and worker["execution_identity"]["head"]==SELECTION_HEAD
        and worker["selection_sha256"]==SELECTION_SHA256
        and worker["selection"]["fixture_only"] is False,"locator_selection_production_lineage")
    _need(set(terminal)=={"schema","reservation_sha256","elapsed_seconds","exit_code","stdout_bytes","stdout_sha256","stderr_bytes","stderr_sha256"}
        and terminal["schema"]==selected.SCHEMA+"/terminal" and terminal["reservation_sha256"]==complete["reservation_sha256"]
        and type(terminal["exit_code"]) is int and terminal["exit_code"]==0
        and type(terminal["elapsed_seconds"]) in {int,float} and math.isfinite(terminal["elapsed_seconds"]) and terminal["elapsed_seconds"]>=0
        and type(terminal["stdout_bytes"]) is int and terminal["stdout_bytes"]==len(_raw(worker))+1
        and terminal["stdout_sha256"]==_sha(_raw(worker)+b"\n")
        and type(terminal["stderr_bytes"]) is int and terminal["stderr_bytes"]==0 and terminal["stderr_sha256"]==_sha(b""),
        "locator_selection_success_control")
    _need(sum(row["source"]["period"] in base.roster.PILOT_PERIODS for row in worker["locator_quarantines"])==11,
        "locator_exact_pilot_quarantine_count")
    return complete,worker,pins


class _SelectionHold:
    def __init__(self):
        self.tree=base.selector.held_io._HeldCapture(LANE_ROOT.joinpath(*SELECTION_PARTS),private=True,settle_ctime=True)
        try:
            _need(self.tree.names==set(SELECTION_PINS),"locator_selection_inventory")
            self.controls={}
            for name,(digest,size) in SELECTION_PINS.items():
                stream=self.tree.open(name,size);raw=stream.read(size+1)
                _need(len(raw)==size and _sha(raw)==digest,"locator_selection_pin")
                self.controls[name]=raw
            self.complete,self.worker,self.row_pins=_selection_controls(self.controls)
            self.recheck()
        except BaseException:
            self.close();raise
    def recheck(self):
        self.tree.check()
        for name,(digest,size) in SELECTION_PINS.items():
            stream=self.tree.open(name,size)
            _need(base.selector.held_io._hash_stream(stream,size)==(digest,size),"locator_selection_changed")
    def close(self):
        primary,failed=sys.exc_info()[0] is not None,False
        for _,stream,_,_ in reversed(self.tree.handles):
            try:stream.close()
            except BaseException:failed=True
        try:self.tree.chain.close()
        except BaseException:failed=True
        if failed and not primary:raise LocatorRunnerError("locator_selection_cleanup_refused")


def _descriptors_from_controls(commit_raw,raw):
    _need(type(commit_raw) is bytes and 0<len(commit_raw)<=base.bootstrap.MAX_CONTROL_BYTES
        and _sha(commit_raw)==base.bootstrap.MASTER_COMMIT_SHA256
        and type(raw) is bytes and 0<len(raw)<=base.bootstrap.MAX_CONTROL_BYTES
        and _sha(raw)==base.bootstrap.MASTER_REPORT_SHA256,"locator_master_control_pins")
    commit=base.bootstrap._json(commit_raw)
    name=commit.get("report_name")
    _need(type(name) is str and "/" not in name and name not in {"",".",".."},"locator_master_report_name")
    _need(commit.get("kind")=="sec-master82-commit" and commit.get("report_sha256")==_sha(raw),"locator_master_control_binding")
    report=base.bootstrap._json(raw);rows=report.get("master_indexes")
    all_periods=tuple(f"{year}Q{quarter}" for year in range(2006,2027) for quarter in range(1,5) if (year,quarter)<=(2026,2))
    _need(report.get("kind")=="INSETF-SEC-MASTER82-RESUMABLE-v1" and report.get("complete_82_master_indexes_acquired") is True
        and report.get("halted_reason") is None and type(rows) is list and len(rows)==82
        and [row.get("period") for row in rows]==list(all_periods)
        and all(row.get("status")=="acquired_noncanonical" for row in rows),"locator_master_complete_inventory")
    result=[]
    for item in rows:
        if item["period"] not in base.roster.CONTEXT_PERIODS:continue
        period=item["period"];obj,receipt=item.get("raw_object"),item.get("receipt")
        _need(item.get("source_url")==f"https://www.sec.gov/Archives/edgar/full-index/{period[:4]}/QTR{period[-1]}/master.gz"
            and type(obj) is dict and set(obj)=={"sha256","relative_path","size_bytes"} and type(receipt) is dict
            and set(receipt)=={"decoded_sha256","decoded_size_bytes","parser_version","master_receipt_sha256","all_filing_row_count","form4_or_4a_path_rows"},
            "locator_master_descriptor")
        pure._digest(obj["sha256"]);pure._digest(receipt["decoded_sha256"]);pure._digest(receipt["master_receipt_sha256"])
        _need(obj["relative_path"]=="objects/"+obj["sha256"]+".bin" and type(obj["size_bytes"]) is int
            and 0<obj["size_bytes"]<=MAX_COMPRESSED and type(receipt["decoded_size_bytes"]) is int
            and 0<receipt["decoded_size_bytes"]<=pure.master.MAX_MASTER_INDEX_BYTES
            and receipt["parser_version"]==pure.master.MASTER_INDEX_PARSER_VERSION
            and type(receipt["all_filing_row_count"]) is int and type(receipt["form4_or_4a_path_rows"]) is int
            and 0<=receipt["form4_or_4a_path_rows"]<=receipt["all_filing_row_count"]<=pure.master.MAX_MASTER_INDEX_ROWS,
            "locator_master_descriptor_bounds")
        result.append({"period":period,"source_url":item["source_url"],"raw_object":obj,"producer_receipt":receipt})
    _need([r["period"] for r in result]==list(base.roster.CONTEXT_PERIODS),"locator_master_context_inventory")
    return result


def _master_descriptors(tree):
    commit_raw=tree.read((),"commit.json",expected=base.bootstrap.MASTER_COMMIT_SHA256)
    commit=base.bootstrap._json(commit_raw);name=commit.get("report_name")
    _need(type(name) is str and "/" not in name and name not in {"",".",".."},"locator_master_report_name")
    raw=tree.read((),name,expected=base.bootstrap.MASTER_REPORT_SHA256)
    result=_descriptors_from_controls(commit_raw,raw)
    return result,{"commit_hex":commit_raw.hex(),"report_hex":raw.hex()}


def _master_witness(witness):
    _need(type(witness) is dict and set(witness)=={"commit_hex","report_hex"},"locator_master_control_witness")
    decoded=[]
    for key in ("commit_hex","report_hex"):
        value=witness[key]
        _need(type(value) is str and 0<len(value)<=2*base.bootstrap.MAX_CONTROL_BYTES and len(value)%2==0
            and re.fullmatch(r"[0-9a-f]+",value),"locator_master_control_witness")
        decoded.append(bytes.fromhex(value))
    return _descriptors_from_controls(*decoded)


def _derive(held,tree):
    rows=held.worker["locator_quarantines"]
    periods=sorted({row["source"]["period"] for row in rows},key=base.roster.CONTEXT_PERIODS.index)
    descriptors,witness=_master_descriptors(tree);inputs=[];total=0
    for item in descriptors:
        obj=item["raw_object"];receipt=item["producer_receipt"]
        raw=tree.read(("objects",),obj["sha256"]+".bin",cap=MAX_COMPRESSED,expected=obj["sha256"])
        _need(len(raw)==obj["size_bytes"],"locator_master_compressed_size")
        if item["period"] in periods:
            decoded=base.bootstrap._decompress_master(raw);total+=len(decoded)
            _need(total<=MAX_DECODED_TOTAL and len(decoded)==receipt["decoded_size_bytes"]
                and _sha(decoded)==receipt["decoded_sha256"],"locator_master_decoded_binding")
            inputs.append({"period":item["period"],"decoded_raw":decoded,"expected_decoded_sha256":receipt["decoded_sha256"],
                "expected_receipt_sha256":receipt["master_receipt_sha256"]})
    value=pure.assess_pilot_sec_locator_quarantines(master_inputs=tuple(inputs),
        selection_complete_raw=held.controls["complete.json"],expected_selection_complete_sha256=SELECTION_PINS["complete.json"][0],
        expected_quarantine_sha256s=held.row_pins)
    pure.validate_pilot_sec_locator_diagnostic(value)
    body=value.to_payload()
    _need(body["fixture_only"] is False and body["quarantine_count"]==12 and body["pilot_quarantine_count"]==11,
        "locator_actual_batch_scope")
    for report in body["reports"]:
        descriptor=next(d for d in descriptors if d["period"]==report["source_record"]["period"])
        summary,receipt=report["master"],descriptor["producer_receipt"]
        _need(summary["decoded_sha256"]==receipt["decoded_sha256"] and summary["decoded_size_bytes"]==receipt["decoded_size_bytes"]
            and summary["parsed_receipt_sha256"]==receipt["master_receipt_sha256"]
            and summary["all_filing_row_count"]==receipt["all_filing_row_count"]
            and summary["form4_or_4a_path_rows"]==receipt["form4_or_4a_path_rows"],"locator_master_report_reparse_binding")
    return body,descriptors,witness


def _validate(result,identity):
    _identity(identity)
    keys={"schema","audit_id","registration","registration_sha256","execution_identity","selection_control_pins","selection_controls",
        "master_descriptors","master_descriptors_sha256","master_control_witness","diagnostic","diagnostic_sha256",
        "native_network_fork_allwrite_securityexec_denial","all25_compressed_master_objects_hash_rechecked",
        "unaffected_master_decoded_or_reparsed","actual_source_body_decoded","new_provider_requests","credential_reads",
        "qc_accesses","outcome_looks","backtests","source_authenticated_here","canonical_admitted","backtesting_ready"}
    _need(type(result) is dict and set(result)==keys and result["schema"]==SCHEMA and result["audit_id"]==AUDIT_ID
        and result["registration"]==REGISTRATION and result["registration_sha256"]==_sha(_raw(REGISTRATION))
        and result["execution_identity"]==identity and result["selection_control_pins"]==REGISTRATION["selection_control_pins"],
        "locator_result_schema")
    for key in ("new_provider_requests","credential_reads","qc_accesses","outcome_looks","backtests"):
        _need(type(result[key]) is int and result[key]==0,"locator_result_access")
    for key in ("unaffected_master_decoded_or_reparsed","actual_source_body_decoded","source_authenticated_here","canonical_admitted","backtesting_ready"):
        _need(result[key] is False,"locator_result_authority")
    _need(result["native_network_fork_allwrite_securityexec_denial"] is True
        and result["all25_compressed_master_objects_hash_rechecked"] is True,"locator_result_denial")
    witness=result["selection_controls"]
    _need(type(witness) is dict and set(witness)==set(SELECTION_PINS)
        and all(type(value) is dict for value in witness.values()),"locator_result_selection_witness")
    _,original,row_pins=_selection_controls({name:_raw(value) for name,value in witness.items()})
    descriptors=result["master_descriptors"]
    _need(type(descriptors) is list and [r["period"] for r in descriptors]==list(base.roster.CONTEXT_PERIODS)
        and _sha(_raw(descriptors))==result["master_descriptors_sha256"]
        and descriptors==_master_witness(result["master_control_witness"]),"locator_result_master_inventory")
    for row in descriptors:
        _need(type(row) is dict and set(row)=={"period","source_url","raw_object","producer_receipt"},"locator_result_master_schema")
        obj,receipt=row["raw_object"],row["producer_receipt"]
        _need(type(obj) is dict and set(obj)=={"sha256","relative_path","size_bytes"} and type(obj["size_bytes"]) is int
            and 0<obj["size_bytes"]<=MAX_COMPRESSED and obj["relative_path"]=="objects/"+pure._digest(obj["sha256"])+".bin",
            "locator_result_master_object")
        _need(type(receipt) is dict and set(receipt)=={"decoded_sha256","decoded_size_bytes","parser_version","master_receipt_sha256",
            "all_filing_row_count","form4_or_4a_path_rows"},"locator_result_master_receipt")
        pure._digest(receipt["decoded_sha256"]);pure._digest(receipt["master_receipt_sha256"])
        _need(row["source_url"]==f"https://www.sec.gov/Archives/edgar/full-index/{row['period'][:4]}/QTR{row['period'][-1]}/master.gz"
            and receipt["parser_version"]==pure.master.MASTER_INDEX_PARSER_VERSION
            and type(receipt["decoded_size_bytes"]) is int and 0<receipt["decoded_size_bytes"]<=pure.master.MAX_MASTER_INDEX_BYTES
            and type(receipt["all_filing_row_count"]) is int and type(receipt["form4_or_4a_path_rows"]) is int
            and 0<=receipt["form4_or_4a_path_rows"]<=receipt["all_filing_row_count"]<=pure.master.MAX_MASTER_INDEX_ROWS,
            "locator_result_master_values")
    body=pure.validate_locator_diagnostic_batch_payload(result["diagnostic"])
    _need(body["fixture_only"] is False and body["quarantine_count"]==12 and body["pilot_quarantine_count"]==11
        and body["prior_selection_complete_sha256"]==SELECTION_PINS["complete.json"][0]
        and body["prior_selection_sha256"]==SELECTION_SHA256 and _sha(_raw(body))==result["diagnostic_sha256"],
        "locator_result_diagnostic_link")
    _need(body["prior_quarantine_jsonl_sha256"]==original["locator_quarantine_jsonl_sha256"]
        and [row["quarantine_row"] for row in body["reports"]]==original["locator_quarantines"]
        and tuple(row["quarantine_sha256"] for row in body["reports"])==row_pins,"locator_result_exact_quarantine_membership")
    for report in body["reports"]:
        receipt=next(r for r in descriptors if r["period"]==report["source_record"]["period"])["producer_receipt"]
        _need(all(report["master"][a]==receipt[b] for a,b in (("decoded_sha256","decoded_sha256"),
            ("decoded_size_bytes","decoded_size_bytes"),("parsed_receipt_sha256","master_receipt_sha256"),
            ("all_filing_row_count","all_filing_row_count"),("form4_or_4a_path_rows","form4_or_4a_path_rows"))),
            "locator_result_master_crosslinks")
    _need(len(_raw(result))<=MAX_REPORT,"locator_result_bound")
    return result


def _worker(identity):
    _need(sys.flags.isolated==1 and sys.flags.no_site==1 and sys.flags.no_user_site==1 and sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==base.EMPTY_CACHE_PREFIX,"locator_worker_flags")
    _identity(identity);base._prove_isolation()
    _need(base.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and base.custody._source_bytes(LANE_ROOT,tuple(base.FROZEN))==base.FROZEN,"locator_worker_sources")
    held,tree=None,None
    try:
        held=_SelectionHold()
        spec=next(spec for spec in base.bootstrap.actual_roots() if spec.root_id=="masters-v3")
        tree=base.bootstrap._Tree(spec)
        body,descriptors,witness=_derive(held,tree)
        held.recheck();tree.recheck()
        _need(base.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
            and base.custody._source_bytes(LANE_ROOT,tuple(base.FROZEN))==base.FROZEN,"locator_worker_sources")
        result={"schema":SCHEMA,"audit_id":AUDIT_ID,"registration":REGISTRATION,"registration_sha256":_sha(_raw(REGISTRATION)),
            "execution_identity":identity,"selection_control_pins":REGISTRATION["selection_control_pins"],
            "selection_controls":{name:base._decode(raw) for name,raw in held.controls.items()},
            "master_descriptors":descriptors,"master_descriptors_sha256":_sha(_raw(descriptors)),
            "master_control_witness":witness,
            "diagnostic":body,"diagnostic_sha256":_sha(_raw(body)),
            "native_network_fork_allwrite_securityexec_denial":True,"all25_compressed_master_objects_hash_rechecked":True,
            "unaffected_master_decoded_or_reparsed":False,"actual_source_body_decoded":False,
            "new_provider_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0,"backtests":0,
            "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}
        return _validate(result,identity)
    finally:
        # Existing tree.close stops at its first failed close; the wrapper drains
        # locks/ancestry and preserves an active primary without changing it.
        wrapped=base.exposure.ExposureHold(tree) if tree is not None else None
        base.selector._close_all((held,wrapped),phase="locator_worker_cleanup")


class _Guard(base._ParentGuard):
    def _write(self,path,*,mkdir=False):
        raise LocatorRunnerError("locator_parent_all_writes_refused")


def _command(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;"
        "from research import insider_buying_pilot_sec_locator_diagnostic_runner as m;"
        "identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept Exception: print('{\"disposition\":\"locator_worker_refused\"}');sys.exit(2)\n"
        "print(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+base.EMPTY_CACHE_PREFIX,"-c",code)


def run_actual(expected_head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"locator_fixed_source")
    identity=_identity(base.custody._identity(expected_head))
    command=_command(identity);guard=_Guard(expected_head,command);sys.addaudithook(guard)
    child=base.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=CONTROL_TIMEOUT,cap=MAX_REPORT)
    _need(child.returncode==0 and child.stderr==b"" and 0<len(child.stdout)<=MAX_REPORT,"locator_worker_refused")
    result=_validate(base._decode(child.stdout.removesuffix(b"\n")),identity)
    _need(base.custody._identity(expected_head)==identity,"locator_parent_source_changed")
    public=dict(result)
    del public["selection_controls"]
    del public["master_control_witness"]
    public["selection_control_witness_validated_and_omitted"]=True
    public["master_control_witness_validated_and_omitted"]=True
    public["observed_worker_stdout_bytes"]=len(child.stdout)
    public["observed_worker_stdout_sha256"]=_sha(child.stdout)
    return public


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True)
    args=parser.parse_args(argv)
    try:result=run_actual(args.expected_head)
    except Exception:
        print('{"disposition":"pilot_locator_diagnostic_refused"}');return 2
    print(_raw(result).decode());return 0


if __name__=="__main__":raise SystemExit(main())
