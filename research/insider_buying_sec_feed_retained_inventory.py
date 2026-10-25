"""Qualify the fixed retained Q2 directory advertisements, never an archive.

The pinned request URL binds lookup identity; opaque directory display strings
do not. Every one of the 64 hrefs must identify its own listed name at that same
directory. Advertised KB magnitudes are lexical metadata, not archive bytes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from research import insider_buying_sec_feed_directory_profile_observer as observer


SELF_PATH = "research/insider_buying_sec_feed_retained_inventory.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_retained_inventory.py"
SCHEMA = "insider-sec-feed-retained-inventory-v1"
AUDIT_ID = "ib-sec-feed-directory-2021q2-retained-format-20261025-once"
base, producer, codec = observer.base, observer.producer, observer.codec
LANE_ROOT, LANE_BRANCH = observer.LANE_ROOT, observer.LANE_BRANCH
# The unchanged generic Q2 input hold requires this empty source-cache prefix.
# It is not an artifact namespace, observer invocation or reuse of an audit ID.
EMPTY_CACHE_PREFIX = observer.EMPTY_CACHE_PREFIX
MAX_REPORT_BYTES, CONTROL_TIMEOUT = observer.MAX_REPORT_BYTES, observer.CONTROL_TIMEOUT
OBSERVER_SOURCE_SHA256 = "72545fc8c431ba8035e31d0cc8051505a4f41cfb6da3673cc809bac05573a487"
OBSERVER_TEST_SHA256 = "dc7e237cecdd24c784cf706153317f278ddcaa6442ba079fbf146d8551ae68ac"
LOOKUP_DIRECTORY_URL = producer.URL.removesuffix("index.json")
EXPECTED_ROWS = 64
_SIZE = re.compile(r"(?P<magnitude>(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?) KB\Z")
_raw, _sha = observer._raw, observer._sha
_HeldInputs = observer._HeldProfile
_Guard = observer._Guard
REGISTRATION = {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,
    "producer_execution_head":observer.PRODUCER_HEAD,"producer_complete_sha256":observer.ACTUAL_PINS.complete_sha256,
    "response_sha256":observer.ACTUAL_PINS.response_sha256,"response_bytes":observer.ACTUAL_PINS.response_bytes,
    "producer_source_count":observer.ACTUAL_PINS.source_count,"producer_source_inventory_sha256":observer.ACTUAL_PINS.source_inventory_sha256,
    "observer_source_sha256":OBSERVER_SOURCE_SHA256,"observer_test_sha256":OBSERVER_TEST_SHA256,
    "lookup_request_url":producer.URL,"lookup_directory_url":LOOKUP_DIRECTORY_URL,"expected_complete_row_count":EXPECTED_ROWS,
    "directory_display_strings_used_for_identity":False,"advertised_KB_base_qualified":False,
    "advertised_rounding_qualified":False,"archive_payload_lengths_known":False,
    "worker_invocations":1,"new_provider_requests":0,"archive_requests":0,"credential_reads":0,
    "qc_accesses":0,"outcome_looks":0,"backtests":0,"original_namespace_mutated":False,
    "old_executed_profile_promoted":False,"native_network_fork_allwrite_securityexec_denial":True,
    "persistent_result_published":False,"raw_directory_witness":"bounded trusted IPC only; independently rederived then stripped",
    "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}


class RetainedInventoryError(ValueError):
    """Fixed local qualification codes; no opaque display text in errors."""


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self,message):
        raise RetainedInventoryError("retained_inventory_cli_arguments_refused")


def _need(value,code):
    if not value:raise RetainedInventoryError(code)


def _href(name,href):
    """Finite exact forms; no joining, percent-decoding or filename fallback."""
    _need(type(name) is str and observer._ARCHIVE.fullmatch(name),"listed_name_not_real_q2_daily_archive")
    _need(type(href) is str and 0<len(href)<=1024 and href.isascii()
        and all(33<=ord(char)<127 for char in href) and not any(char in href for char in "?#%@\\"),"listed_href_lexical_refused")
    forms={name:"relative-filename","./"+name:"dot-relative-filename",
        producer.DIRECTORY+"/"+name:"absolute-path",LOOKUP_DIRECTORY_URL+name:"absolute-https-www-sec"}
    _need(href in forms,"listed_href_not_same_trusted_q2_item")
    return LOOKUP_DIRECTORY_URL+name,forms[href]


def _href_class(value):
    if type(value) is not str:return "not-string-or-absent"
    if not value:return "empty"
    if value.startswith("https://www.sec.gov/"):return "absolute-https-www-sec"
    if value.startswith(("http://","https://")):return "absolute-other"
    if value.startswith("//"):return "protocol-relative"
    if value.startswith("/"):return "absolute-path"
    if value.startswith("./"):return "dot-relative"
    return "other-relative-or-opaque"


def _display_class(value):
    if value=="":return "empty-string-display"
    if observer._SEC_PATH.fullmatch(value):return "feed-path-display-not-identity"
    return "opaque-string-display"


def _qualify(raw):
    try:value=observer._foreign(raw)
    except observer.DirectoryProfileError:raise RetainedInventoryError("retained_foreign_json_profile_refused") from None
    _need(type(value) is dict and set(value)=={"directory"} and type(value["directory"]) is dict,"directory_envelope_refused")
    directory=value["directory"]
    _need(set(directory)=={"name","parent-dir","item"} and type(directory["name"]) is str
        and type(directory["parent-dir"]) is str and len(directory["name"])<=1024 and len(directory["parent-dir"])<=1024
        and type(directory["item"]) is list,"directory_field_profile_refused")
    _need(len(directory["item"])==EXPECTED_ROWS,"complete_64_row_count_required")
    entries,seen=[],set()
    for ordinal,item in enumerate(directory["item"],1):
        _need(type(item) is dict and set(item)=={"href","last-modified","name","size","type"}
            and all(type(value) is str for value in item.values()),"exact_five_string_fields_required")
        _need(item["type"]=="file" and len(item["last-modified"])<=128,"file_metadata_profile_refused")
        target,form=_href(item["name"],item["href"])
        _need(target not in seen,"duplicate_archive_advertisement");seen.add(target)
        match=_SIZE.fullmatch(item["size"])
        _need(match is not None and any(char in "123456789" for char in match["magnitude"]),"positive_decimal_KB_lexeme_required")
        name=item["name"]
        entries.append({"source_ordinal":ordinal,"listed_name":name,"archive_date":name[:4]+"-"+name[4:6]+"-"+name[6:8],
            "listed_href":item["href"],"href_form":form,"qualified_archive_url":target,
            "advertised_size_text":item["size"],"advertised_magnitude_text":match["magnitude"],"advertised_unit":"KB",
            "advertised_unit_base_qualified":False,"advertised_rounding_qualified":False,"actual_archive_bytes_known":False,
            "source_item_canonical_sha256":_sha(_raw({"source_ordinal":ordinal,"item":item})),"archive_followed":False})
    return {"schema":SCHEMA+"/inventory","lookup_request_url":producer.URL,"lookup_directory_url":LOOKUP_DIRECTORY_URL,
        "lookup_identity_basis":"fixed hash-bound HTTP request URL; not directory display strings",
        "directory_display_classes":{key:_display_class(directory[key]) for key in ("name","parent-dir")},
        "directory_display_strings_used_for_identity":False,"complete_advertisement_count":len(entries),"entries":entries,
        "ordered_entries_sha256":_sha(_raw(entries)),"response_sha256":_sha(raw),"response_bytes":len(raw),
        "item_hash_semantics":"canonical ordinal and exact parsed five-string-field advertisement; not raw JSON substring",
        "advertised_KB_is_not_actual_payload_bytes":True,"advertised_KB_base_qualified":False,
        "advertised_rounding_qualified":False,"old_executed_candidate_profile_remains_unqualified":True,
        "filing_population_coverage_established":False,"authority":producer._authority()}


def qualify_retained_directory(raw):
    _need(type(raw) is bytes and 0<len(raw)<=producer.MAX_RESPONSE_BYTES,"retained_directory_byte_bound")
    try:inventory=_qualify(raw);code=None
    except RetainedInventoryError as exc:inventory=None;code=str(exc)
    shape=observer.observe_directory_profile(raw)
    counts={}
    try:
        value=observer._foreign(raw);directory=value.get("directory") if type(value) is dict else None
        rows=directory.get("item") if type(directory) is dict else None
        if type(rows) is list:
            for row in rows:
                kind=_href_class(row.get("href") if type(row) is dict else None);counts[kind]=counts.get(kind,0)+1
    except observer.DirectoryProfileError:pass
    return {"schema":SCHEMA+"/qualification","status":"qualified" if inventory is not None else "refused",
        "refusal_code":code,"inventory":inventory,"safe_shape":shape,"href_shape_counts":counts,
        "response_sha256":_sha(raw),"response_bytes":len(raw),"new_archive_requests":0,
        "old_executed_profile_promoted":False,"authority":producer._authority()}


def _identity(value):
    observer._identity(value)
    _need({SELF_PATH,TEST_PATH}<=set(value["source_sha256"]),"retained_inventory_source_roster")
    return value


def _current(identity):
    observer._current(identity)
    pins={observer.SELF_PATH:OBSERVER_SOURCE_SHA256,observer.TEST_PATH:OBSERVER_TEST_SHA256}
    _need(base.custody._source_bytes(LANE_ROOT,tuple(pins))==pins,"retained_inventory_observer_source_changed")


def _result(identity,controls,*,pins=observer.ACTUAL_PINS):
    observer.validate_capture(controls,pins);qualification=qualify_retained_directory(controls["response.bin"])
    return {"schema":SCHEMA,"audit_id":AUDIT_ID,"registration":codec._decode_control(_raw(REGISTRATION)),"registration_sha256":_sha(_raw(REGISTRATION)),
        "execution_identity":identity,"retained_control_pins":{name:{"sha256":_sha(raw),"bytes":len(raw)} for name,raw in controls.items()},
        "retained_control_witness":{name:raw.hex() for name,raw in controls.items()},"directory_qualification":qualification,
        "directory_qualification_sha256":_sha(_raw(qualification)),"native_network_fork_allwrite_securityexec_denial":True,
        "new_provider_requests":0,"archive_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0,"backtests":0,
        "original_namespace_mutated":False,"old_executed_profile_promoted":False,"persistent_result_published":False,
        "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}


def _validate(result,identity,*,pins=observer.ACTUAL_PINS):
    _identity(identity);_need(type(result) is dict,"retained_inventory_result_object")
    expected=_result(identity,observer._witness(result),pins=pins)
    _need(_raw(result)==_raw(expected) and len(_raw(result))<=MAX_REPORT_BYTES,"retained_inventory_result_crosslinks")
    return result


def _worker(identity):
    observer._isolated();_identity(identity);base._prove_isolation();_current(identity)
    held=None
    try:
        held=_HeldInputs();result=_result(identity,held.controls)
        held.recheck();_current(identity);_validate(result,identity);held.recheck();_current(identity)
        return result
    finally:base.selector._close_all((held,),phase="retained_inventory_worker_cleanup")


def _committed_identity(head):
    identity=base.custody._identity(head)
    names=(SELF_PATH,TEST_PATH,observer.SELF_PATH,observer.TEST_PATH,producer.SELF_PATH,producer.TEST_PATH)
    own=base.custody._source_bytes(LANE_ROOT,names)
    for name,digest in own.items():_need(_sha(base.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"retained_inventory_uncommitted_source")
    sources={**identity["source_sha256"],**own}
    identity=_identity({**identity,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))});_current(identity)
    return identity


def _command(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;"
        "from research import insider_buying_sec_feed_retained_inventory as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept Exception: print('{\"disposition\":\"retained_inventory_worker_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def run_actual_inventory(expected_head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"retained_inventory_fixed_source")
    identity=_committed_identity(expected_head);command=_command(identity);sys.addaudithook(_Guard(expected_head,command))
    child=base.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=CONTROL_TIMEOUT,cap=MAX_REPORT_BYTES)
    _need(child.returncode==0 and child.stderr==b"" and 0<len(child.stdout)<=MAX_REPORT_BYTES,"retained_inventory_worker_refused")
    result=_validate(codec._decode_control(child.stdout.removesuffix(b"\n"),ipc=True),identity)
    original=observer.validate_capture(observer._witness(result))
    for name,digest in original["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT,"show",observer.PRODUCER_HEAD+":"+name))==digest,"retained_inventory_producer_git_mismatch")
    _need(_committed_identity(expected_head)==identity,"retained_inventory_parent_source_changed")
    public=dict(result);del public["retained_control_witness"]
    public.update({"raw_directory_control_witness_validated_and_omitted":True,"producer_source_inventory_matched_execution_commit":True,
        "observed_worker_stdout_bytes":len(child.stdout),"observed_worker_stdout_sha256":_sha(child.stdout)})
    return public


def main(argv=None):
    parser=_PrivateArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True)
    try:args=parser.parse_args(argv);result=run_actual_inventory(args.expected_head)
    except Exception:print('{"disposition":"retained_inventory_observation_refused"}');return 2
    print(_raw(result).decode());return 0 if result["directory_qualification"]["status"]=="qualified" else 2


if __name__=="__main__":raise SystemExit(main())
