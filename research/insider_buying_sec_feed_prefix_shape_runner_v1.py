"""One offline shape observation of an externally pinned retained Range unit.

No HTTP, SDK, source-row decode or acquisition exists here. Metadata preflight
stats but NEVER reads/hashes the old prefix. Native analysis then holds its old
SH lock/strict versions, replays the frozen current-contact prefix verifier,
and qualifies the SAME immutable bytes with the new pure shape observer.
Original contact equality and whole-carrier verification are never inferred.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_sec_feed_prefix_capture_v1 as capture
from research import insider_buying_sec_feed_prefix_shape_v1 as shape

SCHEMA="insider-sec-feed-prefix-shape-runner-v1"
SELF_PATH="research/insider_buying_sec_feed_prefix_shape_runner_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_prefix_shape_runner_v1.py"
REVIEW_TEST_PATH="tests/test_insider_buying_sec_feed_prefix_shape_runner_v1_review.py"
LANE_ROOT,LANE_BRANCH,EMPTY_CACHE_PREFIX=capture.LANE_ROOT,capture.LANE_BRANCH,capture.EMPTY_CACHE_PREFIX
ARTIFACT_PARTS=("artifacts","insider_buying","sec_feed_prefix_shape_observation_v1")
AUDIT_ID="ib-sec-feed-prefix-shape-offline-v1-20261025-once"
MAX_CONTROL=1024**2
WORKER_SECONDS=180
MIN_FREE_BYTES=64*1024**2
LOCK_BYTES=b"INSETF-retained-prefix-offline-shape-once-no-HTTP\n"
ORIGINAL_HEAD="941a6f78608b6ffb3f76c986176495cb7fae43bf"
ORIGINAL_SOURCE_INVENTORY="efb11ed9b5c728e65da22a87c2ecb3cc79c65b60b248cb7d812c788628dc7b32"
ORIGINAL_SOURCE_COUNT=138
ORIGINAL_PINS={"complete.json":"f89f5c9333383cc7a9a62b4f07ffef340451f0fca75fa91f1cd7ee55e580f2ce",
    "reservation.json":"c3a35a798eb5e8d39e5bd1d79099fc85e0a4910eb470466d631fd8b588443807",
    "request-start.json":"b1bc5191ce30172b28eab22a0f041a6ee360ad761d59caccf906a5ecae66bcd9",
    "request-result.json":"f12420338cfcb7bad3d25773d38987af16a5b382f04262b651ad76dc33ee5924",
    "inspection.json":"a403b1d30f901299662f43249b8fa05ef445387e07af2e9ae564c0cf731280ff",
    "prefix.bin":"4646b2a211ee8cc367528571ae6c212519cd4a7ff9b95820f9411c50d5763362",
    "claim":"ee8464baf15998099c94f3a2432378017cc481788cdf4a04d32b68e083918b05"}
FROZEN={**capture.FROZEN,
    capture.SELF_PATH:"153f1b35fa9aaa9d6274a43eb6c077cc5d26ac7bb83a45ac674edb4151e3e6e8",
    capture.TEST_PATH:"00f1eae23b522cc806729912210c41199bfbd6ada925e8d749a8dc2ff9de08f6",
    capture.REVIEW_TEST_PATH:"075799f50570e79b832585e944e57d07cbc06df56b4a3793b5e9ebc1b0792727",
    shape.SELF_PATH:"98f13147c86ecd58932d70f51bb7ccbf2a683a01908450371d1ed2038b27fc31",
    shape.TEST_PATH:"67b7b2923a487cd9de557038c7da4032ece254c3d8262a3518546af901fca6d4",
    shape.REVIEW_TEST_PATH:"e89588779f44038aa09eb8fa5dd957b612adfb038fdace388057de2999c5d498"}
previous,publication,custody,privacy,old,directory,source_runner=(capture.previous,capture.publication,
    capture.custody,capture.privacy,capture.old,capture.directory,capture.source_runner)
contact_io=capture.contact_io
_raw,_sha=capture._raw,capture._sha
_SHA=re.compile(r"[0-9a-f]{64}\Z")
_PHASES=frozenset({"arguments","source","native_preflight","inputs","capacity","namespace","reservation",
    "contact","start","analysis","input","privacy","gzip-prefix","replay","observer","publication","complete","readback","final","cleanup"})
_CODES=frozenset({"private_arguments_refused","private_contact_mode_refused","source_identity_refused","source_changed",
    "fixed_actual_front_required","metadata_refused","inputs_changed","original_pins_refused","original_prefix_custody_refused",
    "preflight_refused","disk_reserve_refused","fresh_namespace_already_exists","output_changed","analysis_refused",
    "native_boundary_refused","readback_refused","cleanup_refused","local_operation_refused"})
_SHAPE_CODES={"input":{"immutable_prefix_byte_bound","exact_fixture_boolean_required","exact_limits_type_required","limits_must_only_narrow"},
    "privacy":{"explicit_contact_required","contact_profile_refused","finite_prefix_screen_refused"},
    "capacity":{"gzip_member_count_bound","decoded_prefix_byte_bound","decoded_prefix_expansion_bound","descriptor_byte_bound",
        "header_metadata_bound","header_count_bound","final_metadata_bound"},
    "gzip-prefix":{"invalid_gzip_prefix_or_observed_trailer","decoder_progress_refused"},
    "replay":{"immutable_two_pass_decode_counts_differ","observer_decoded_count_differs"},
    "observer":{"feed_after_final_or_wrong_type","final_feed_required"}}


class PrefixShapeRunnerError(ValueError):
    def __init__(self,code,phase="source"):
        self.phase=phase if type(phase) is str and phase in _PHASES else "source"
        super().__init__(code)


def _need(value,code,phase="source"):
    if not value:raise PrefixShapeRunnerError(code,phase)


def _safe(error,phase):
    if type(error) is PrefixShapeRunnerError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in _CODES:
        return {"phase":error.phase,"code":error.args[0]}
    if type(error) in {shape.PrefixShapeError,capture.core.PrefixFormatError} and type(error.phase) is type(error.code) is str and error.code in _SHAPE_CODES.get(error.phase,()):
        return {"phase":error.phase,"code":error.code}
    return {"phase":phase if phase in _PHASES else "source","code":"local_operation_refused"}


def _control(raw):
    _need(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL,"metadata_refused")
    value=capture._control(raw);_need(_raw(value)==raw,"metadata_refused");return value


def _authority():
    return {"offline_prefix_shape_only":True,"source_or_identity_or_PIT_or_rights_verified":False,
        "whole_carrier_verified_or_retained":False,"original_contact_screen_replayed":False,
        "original_current_contact_equality_attested":False,"canonical_admitted":False,"backtesting_ready":False,
        "earlier_failed_archive_cause_established":False,"new_requests":0,"SDK_calls":0,"outcome_looks":0}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"original_prefix_pins":dict(ORIGINAL_PINS),
        "original_producer_head":ORIGINAL_HEAD,"original_source_inventory_sha256":ORIGINAL_SOURCE_INVENTORY,
        "original_source_count":ORIGINAL_SOURCE_COUNT,"prefix_bytes":65536,"original_root_mutated":False,
        "metadata_preflight_reads_raw_prefix":False,"full_roster_rederived":False,
        "new_HTTP_or_URL_claim_or_source_dispatch":False,"current_contact_readback_registered":True,
        "maximum_shape_bytes":shape.MAX_METADATA,"maximum_control_or_IPC_bytes":MAX_CONTROL,
        "native_worker_seconds":WORKER_SECONDS,"memory_policy":previous._memory_policy(),
        "minimum_free_reserve_bytes":MIN_FREE_BYTES,"authority":_authority()}


def _paths():return (SELF_PATH,TEST_PATH,REVIEW_TEST_PATH,*FROZEN)


def _current(identity):
    publication._source_identity(identity,required_paths=_paths())
    capture._current(identity)
    _need(custody._source_bytes(LANE_ROOT,tuple(FROZEN))==FROZEN,"source_changed")


def _identity(head):
    previous._isolated();_need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_front_required")
    value=capture._identity(head);sources={**value["source_sha256"],**custody._source_bytes(LANE_ROOT,_paths())}
    for path,pin in sources.items():_need(_sha(custody._git(LANE_ROOT,"show",head+":"+path))==pin,"source_changed")
    value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))};_current(value);return value


def _check_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}",value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and 1<=len(value["source_sha256"])<=4096 and all(type(name) is str and len(name)<=512
            and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",name) and not name.startswith("/")
            and all(part not in {"",".",".."} for part in name.split("/")) and type(pin) is str and _SHA.fullmatch(pin)
            for name,pin in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"source_identity_refused")


class _HeldPrefix:
    """Strict held old controls + prefix STAT only until read_body is called."""
    def __init__(self,root,*,fixture=False,pins=None):
        self.root,self.fixture=Path(root),fixture;self.folders=[];self.lock=None
        self.pins=dict(ORIGINAL_PINS if pins is None else pins)
        try:
            _need(type(fixture) is bool and (fixture or pins is None),"original_pins_refused","inputs")
            if fixture:publication._fixture_root(self.root);publication._native_fixture_denial()
            else:_need(self.root==LANE_ROOT,"fixed_actual_front_required","inputs")
            def opened(path):
                obj=directory._ReadbackDirectory(path);self.folders.append(obj);return obj
            self.top=opened(self.root.joinpath(*capture.ARTIFACT_PARTS));claims=opened(self.top.path/"claims")
            runs=opened(self.top.path/"runs");self.run=opened(runs.path/capture.AUDIT_ID)
            self.lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.top.fd)
            fcntl.flock(self.lock,fcntl.LOCK_SH|fcntl.LOCK_NB);self.version=privacy._file_version(os.fstat(self.lock))
            _need(self.top.read("scope.lock")==capture.LOCK_BYTES and self.top.inventory=={"scope.lock","claims","runs"}
                and claims.inventory=={capture._claim_name()} and runs.inventory=={capture.AUDIT_ID},"inputs_changed","inputs")
            names={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json",
                "complete.json","prefix.bin","response-headers.json","inspection.json"}
            _need(self.run.inventory==names,"inputs_changed","inputs")
            raws={name:self.run.read(name,cap=MAX_CONTROL) for name in sorted(names-{"prefix.bin"})}
            claim=claims.read(capture._claim_name());complete=_control(raws["complete.json"])
            identity=complete["execution_identity"];capture._check_identity(identity,self.root)
            plan=_control(raws["input-preflight.json"]);forms=capture._forms(identity,fixture,plan)
            result=_control(raws["request-result.json"]);rsha=_sha(_raw(forms["reservation.json"]))
            capture._result_valid(result,rsha,_sha(_raw(forms["claim.json"])),_sha(_raw(forms["request-start.json"])))
            capture._inspection_valid(_control(raws["inspection.json"]),fixture)
            headers=_control(raws["response-headers.json"])
            _need(type(headers) is dict and set(headers)=={"headers"},"inputs_changed","inputs")
            pairs,total=capture._range_headers(206,headers["headers"])
            _need(raws["response-headers.json"]==_raw({"headers":pairs}) and result["headers_sha256"]==_sha(_raw(pairs))
                and result["inspection_sha256"]==_sha(raws["inspection.json"]) and result["declared_carrier_total_bytes"]==total
                and result["prefix_retained"] is True and result["prefix_bytes"]==65536
                and raws["reservation.json"]==_raw(forms["reservation.json"]) and claim==_raw(forms["claim.json"])
                and raws["request-start.json"]==_raw(forms["request-start.json"])
                and raws["contact-validated.json"]==_raw({"schema":capture.SCHEMA+"/contact","reservation_sha256":rsha,
                    "contact_present":True,"contact_value_stored_or_hashed":False})
                and raws["complete.json"]==_raw(capture._complete(identity,fixture,plan,rsha,result,_sha(raws["request-result.json"]))),
                "inputs_changed","inputs")
            actual={**{n:_sha(raws[n]) for n in self.pins if n in raws},"claim":_sha(claim),"prefix.bin":result["prefix_sha256"]}
            _need(set(actual)==set(self.pins) and actual==self.pins,"original_pins_refused","inputs")
            if not fixture:_need(identity["head"]==ORIGINAL_HEAD and identity["source_inventory_sha256"]==ORIGINAL_SOURCE_INVENTORY
                and len(identity["source_sha256"])==ORIGINAL_SOURCE_COUNT,"original_pins_refused","inputs")
            value=os.stat("prefix.bin",dir_fd=self.run.fd,follow_symlinks=False)
            _need(stat.S_ISREG(value.st_mode) and value.st_uid==os.geteuid() and stat.S_IMODE(value.st_mode)==0o600
                and value.st_nlink==1 and value.st_size==65536,"original_prefix_custody_refused","inputs")
            self.metadata={"schema":SCHEMA+"/original-input","external_pins":self.pins,"original_execution_identity":identity,
                "original_input_plan":plan,"control_sha256":{n:_sha(raw) for n,raw in raws.items()},
                "prefix_bytes_statted":65536,"raw_prefix_read_by_metadata_preflight":False,
                "whole_carrier_read_or_verified":False};self.check()
        except BaseException:self.close();raise

    def check(self):
        for item in self.folders:item.check()
        _need(self.version==privacy._file_version(os.fstat(self.lock))==privacy._file_version(os.stat(
            "scope.lock",dir_fd=self.top.fd,follow_symlinks=False)),"inputs_changed","inputs")

    def read_body(self):
        self.check();self.run._versions();raw=self.run.tree.read("prefix.bin",cap=65536);self.run._versions()
        _need(type(raw) is bytes and len(raw)==65536,"original_prefix_custody_refused","inputs");return raw

    def close(self):
        active=sys.exc_info()[0] is not None;failed=False
        if self.lock is not None:
            for action in (lambda:fcntl.flock(self.lock,fcntl.LOCK_UN),lambda:os.close(self.lock)):
                try:action()
                except BaseException:failed=True
            self.lock=None
        for item in reversed(self.folders):
            try:item.close()
            except BaseException:failed=True
        self.folders=[]
        if failed and not active:raise PrefixShapeRunnerError("cleanup_refused","cleanup") from None


def _parent_proofs(plan):
    inputs=plan["inputs"];previous._source_git(inputs["original_execution_identity"])
    capture._parent_proofs(inputs["original_input_plan"])


def _plan(identity,inputs):
    return {"schema":SCHEMA+"/preflight","execution_identity":identity,"inputs":inputs,
        "new_requests":0,"contact_reads":0,"namespace_created":False}


def _forms(identity,fixture,plan):
    _check_identity(identity,Path(identity["root"]))
    _need(type(fixture) is bool and type(plan) is dict and set(plan)=={"schema","execution_identity","inputs","new_requests","contact_reads","namespace_created"}
        and plan["schema"]==SCHEMA+"/preflight" and _raw(plan["execution_identity"])==_raw(identity)
        and type(plan["inputs"]) is dict and plan["inputs"].get("schema")==SCHEMA+"/original-input"
        and type(plan["new_requests"]) is type(plan["contact_reads"]) is int and plan["new_requests"]==plan["contact_reads"]==0
        and plan["namespace_created"] is False,"preflight_refused","native_preflight")
    registered=registration();reservation={"schema":SCHEMA+"/reservation","audit_id":AUDIT_ID,"fixture_only":fixture,
        "execution_identity":identity,"registration_sha256":_sha(_raw(registered)),"preflight_sha256":_sha(_raw(plan))}
    rpin=_sha(_raw(reservation));start={"schema":SCHEMA+"/analysis-start","reservation_sha256":rpin,
        "attempt":1,"offline_only":True,"new_requests":0}
    forms={"registration.json":registered,"reservation.json":reservation,"input-preflight.json":plan,"analysis-start.json":start}
    for value in forms.values():_control(_raw(value))
    return forms


def _analyse(identity,private,held,*,fixture):
    raw=held.read_body()
    # Old replay screens before its hash. Its extra bounded read is deliberate;
    # this outer immutable raw value is compared only AFTER both privacy runs.
    replay=capture._verify_files(held.root,held.pins["complete.json"],private,fixture=fixture,current_identity=None if fixture else identity)
    observed=shape.qualify_prefix_shape(raw,privacy_contact=private,fixture_only=fixture)
    _need(observed["prefix_sha256"]==held.pins["prefix.bin"] and _sha(raw)==held.pins["prefix.bin"]
        and replay["producer_execution_identity"]==held.metadata["original_execution_identity"]
        and replay["current_contact_prefix_rescreened"] is True,"analysis_refused","analysis")
    held.check()
    return {"schema":SCHEMA+"/report","fixture_only":fixture,"execution_identity":identity,
        "original_input_sha256":_sha(_raw(held.metadata)),"original_prefix_complete_sha256":held.pins["complete.json"],
        "original_prefix_sha256":held.pins["prefix.bin"],"shape":observed,"current_contact_prefix_rescreened":True,
        "original_contact_screen_replayed":False,"original_current_contact_equality_attested":False,
        "raw_prefix_reuse_only_no_new_HTTP":True,"authority":_authority()}


def _report_valid(value,identity,inputs,fixture):
    """Strict sanitized IPC contract; native source checks are separate proof."""
    keys={"schema","fixture_only","execution_identity","original_input_sha256","original_prefix_complete_sha256",
        "original_prefix_sha256","shape","current_contact_prefix_rescreened","original_contact_screen_replayed",
        "original_current_contact_equality_attested","raw_prefix_reuse_only_no_new_HTTP","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/report" and value["fixture_only"] is fixture
        and _raw(value["execution_identity"])==_raw(identity) and value["original_input_sha256"]==_sha(_raw(inputs))
        and value["original_prefix_complete_sha256"]==inputs["external_pins"]["complete.json"]
        and value["original_prefix_sha256"]==inputs["external_pins"]["prefix.bin"]
        and value["current_contact_prefix_rescreened"] is True and value["original_contact_screen_replayed"] is False
        and value["original_current_contact_equality_attested"] is False and value["raw_prefix_reuse_only_no_new_HTTP"] is True
        and _raw(value["authority"])==_raw(_authority()),"analysis_refused","analysis")
    item=value["shape"]
    false={"dependency_pin_runtime_attested_here","member_names_routes_decoded_values_or_their_hashes_returned",
        "decoded_bytes_separately_hashed_or_retained","physical_bytes_rewritten","whole_carrier_CRC_ISIZE_EOF_or_privacy_verified",
        "whole_carrier_population_known","PDS_or_GNU_logical_name_profile_validated","XML_or_financial_or_acceptance_fields_parsed",
        "identity_or_PIT_or_rights_or_admission_verified","backtesting_ready","earlier_failed_archive_cause_established"}
    zero={"files_read_written","new_requests","SDK_calls","outcome_looks"}
    other={"schema","fixture_only","prefix_bytes","prefix_sha256","prefix_format_descriptor","physical_shape_observations",
        "prefix_core_source_path","prefix_core_source_sha256","complete_raw_and_produced_decoded_finite_privacy_precedes_shape",
        "same_immutable_prefix_two_pass_counts_compared"}
    _need(type(item) is dict and set(item)==false|zero|other and item["schema"]==shape.SCHEMA and item["fixture_only"] is fixture
        and all(item[k] is False for k in false) and all(type(item[k]) is int and item[k]==0 for k in zero)
        and type(item["prefix_bytes"]) is int and item["prefix_bytes"]==65536 and item["prefix_sha256"]==value["original_prefix_sha256"]
        and item["prefix_core_source_path"]==shape.PREFIX_CORE_PATH and item["prefix_core_source_sha256"]==shape.PREFIX_CORE_SHA256
        and item["complete_raw_and_produced_decoded_finite_privacy_precedes_shape"] is True
        and item["same_immutable_prefix_two_pass_counts_compared"] is True and len(_raw(item))<=shape.MAX_METADATA,
        "analysis_refused","analysis")
    descriptor=item["prefix_format_descriptor"]
    capture._inspection_valid({"schema":capture.SCHEMA+"/inspection","descriptor":descriptor,"headers_sha256":"a"*64,
        "declared_carrier_total_bytes":65537,"total_is_declared_not_measured":True,"prefix_unit_privacy_and_integrity_only":True,
        "whole_carrier_verified":False,"authority":capture._authority()},fixture)
    _need(descriptor["prefix_sha256"]==item["prefix_sha256"],"analysis_refused","analysis")
    physical=item["physical_shape_observations"]
    physicalkeys={"schema","status","decoded_bytes_observed","structural_frontier_bytes","following_bytes_not_interpreted",
        "observed_complete_headers","headers","stop_range","partial_header_range","two_zero_block_range","trailing_bytes_observed",
        "trailing_observed_bytes_all_zero","logical_names_validated","whole_TAR_or_member_population_verified","source_or_XML_or_PIT_or_admission_verified"}
    statuses={"observed_invalid_header_checksum","observed_unsupported_octal_size_field","unknown_magic_pattern_stop",
        "unsupported_type_or_extension_stop","directory_nonzero_payload_stop","observed_nonzero_member_padding",
        "observed_nonzero_after_two_zero_blocks","observed_nonzero_after_single_zero_block","prefix_ended_with_partial_header",
        "prefix_ended_with_partial_payload","prefix_ended_with_partial_padding","two_zero_blocks_observed_not_whole_carrier_EOF",
        "prefix_ended_with_single_zero_block","no_decoded_header_bytes","prefix_ended_at_next_header_boundary"}
    _need(type(physical) is dict and set(physical)==physicalkeys and physical["schema"]==shape.SCHEMA+"/physical-observations"
        and type(physical["status"]) is str and physical["status"] in statuses
        and all(physical[k] is False for k in ("logical_names_validated","whole_TAR_or_member_population_verified","source_or_XML_or_PIT_or_admission_verified"))
        and type(physical["trailing_observed_bytes_all_zero"]) is bool,"analysis_refused","analysis")
    for key in ("decoded_bytes_observed","structural_frontier_bytes","following_bytes_not_interpreted","observed_complete_headers","trailing_bytes_observed"):
        _need(type(physical[key]) is int and 0<=physical[key]<=capture.core.MAX_DECODED_BYTES,"analysis_refused","analysis")
    total=physical["decoded_bytes_observed"]
    _need(total==descriptor["decoded_prefix_bytes"] and physical["structural_frontier_bytes"]+physical["following_bytes_not_interpreted"]==total
        and type(physical["headers"]) is list and physical["observed_complete_headers"]==len(physical["headers"])<=shape.MAX_HEADERS,
        "analysis_refused","analysis")
    def span(raw,ceiling,nullable=False):
        _need(raw is None and nullable or type(raw) is list and len(raw)==2 and all(type(n) is int for n in raw)
            and 0<=raw[0]<=raw[1]<=ceiling,"analysis_refused","analysis")
    def markers(rows):
        _need(type(rows) is list and len(rows)<=6 and all(type(row) is dict and set(row)=={"offset","family"}
            and type(row["offset"]) is int and row["offset"] in {0,256,266} and type(row["family"]) is str
            and row["family"] in {"SUBMISSION","SEC-DOCUMENT"} for row in rows)
            and len({(r["offset"],r["family"]) for r in rows})==len(rows),"analysis_refused","analysis")
    for key in ("stop_range","partial_header_range","two_zero_block_range"):span(physical[key],total,True)
    if physical["stop_range"] is not None:
        _need(physical["stop_range"][1]==physical["structural_frontier_bytes"],"analysis_refused","analysis")
    if physical["partial_header_range"] is not None:
        _need(physical["partial_header_range"][1]==physical["structural_frontier_bytes"]
            and 0<physical["partial_header_range"][1]-physical["partial_header_range"][0]<512,"analysis_refused","analysis")
    rowkeys={"ordinal","header_range","header_checksum_matches","magic_pattern_observation","type_class_observation","declared_payload_bytes",
        "payload_range","padding_range","payload_bytes_observed","padding_bytes_observed","payload_prefix_bytes_observed","payload_opening_markers",
        "observed_physical_range","complete_physical_span_observed_within_prefix","observed_payload_padding_all_zero","observation_disposition",
        "header_or_payload_rewritten","PDS_controls_validated","admitted","fixed_name_fields_examined","fixed_name_fields_NUL_padding_zero",
        "fixed_name_fields_safe_relative_path","fixed_name_fields_have_nc_suffix","fixed_name_fields_match_accession_nc_routing_pattern","logical_name_profile_validated"}
    boolean={"header_checksum_matches","complete_physical_span_observed_within_prefix","observed_payload_padding_all_zero",
        "fixed_name_fields_examined","fixed_name_fields_NUL_padding_zero","fixed_name_fields_safe_relative_path","fixed_name_fields_have_nc_suffix",
        "fixed_name_fields_match_accession_nc_routing_pattern"}
    frontier=0
    for ordinal,row in enumerate(physical["headers"],1):
        _need(type(row) is dict and set(row)==rowkeys and type(row["ordinal"]) is int and row["ordinal"]==ordinal
            and all(type(row[k]) is bool for k in boolean)
            and all(row[k] is False for k in ("header_or_payload_rewritten","PDS_controls_validated","admitted","logical_name_profile_validated"))
            and type(row["magic_pattern_observation"]) is str and row["magic_pattern_observation"] in {"posix_ustar_NUL00","old_gnu_ustar_spaces_NUL","v7_zero_tail","unknown"}
            and type(row["type_class_observation"]) is str and row["type_class_observation"] in {"regular","directory","hardlink","symlink","pax","pax-global","gnu-longname","gnu-longlink","gnu-sparse","other"}
            and type(row["observation_disposition"]) is str and row["observation_disposition"] in {"header_only","complete_physical_span_observed_not_admitted","prefix_ended_with_partial_payload","prefix_ended_with_partial_padding"},
            "analysis_refused","analysis")
        span(row["header_range"],total);span(row["observed_physical_range"],total)
        _need(row["header_range"]==[frontier,frontier+512] and row["observed_physical_range"][0]==frontier
            and row["observed_physical_range"][1]>=frontier+512,"analysis_refused","analysis")
        frontier=row["observed_physical_range"][1];size=row["declared_payload_bytes"]
        _need(size is None or type(size) is int and 0<=size<8**12,"analysis_refused","analysis")
        span(row["payload_range"],8**12+capture.core.MAX_DECODED_BYTES,True);span(row["padding_range"],8**12+capture.core.MAX_DECODED_BYTES,True)
        if size is None:_need(row["payload_range"] is row["padding_range"] is None,"analysis_refused","analysis")
        else:_need(row["payload_range"]==[row["header_range"][1],row["header_range"][1]+size]
            and row["padding_range"]==[row["header_range"][1]+size,row["header_range"][1]+size+(-size)%512],"analysis_refused","analysis")
        for key,bound in (("payload_bytes_observed",size or 0),("padding_bytes_observed",511),("payload_prefix_bytes_observed",280)):
            _need(type(row[key]) is int and 0<=row[key]<=bound,"analysis_refused","analysis")
        _need(row["payload_prefix_bytes_observed"]==min(row["payload_bytes_observed"],280),"analysis_refused","analysis");markers(row["payload_opening_markers"])
        _need(row["observed_physical_range"][1]==row["header_range"][1]+row["payload_bytes_observed"]+row["padding_bytes_observed"],
            "analysis_refused","analysis")
        if row["complete_physical_span_observed_within_prefix"]:
            _need(size is not None and row["payload_bytes_observed"]==size and row["padding_bytes_observed"]==(-size)%512
                and row["observation_disposition"]=="complete_physical_span_observed_not_admitted","analysis_refused","analysis")
    _need(frontier<=physical["structural_frontier_bytes"],"analysis_refused","analysis")
    if physical["headers"]:
        first=physical["headers"][0];oldfirst=descriptor["first_tar_header_observation"]
        _need(first["header_checksum_matches"] is oldfirst["header_checksum_matches"],"analysis_refused","analysis")
        if oldfirst["header_checksum_matches"]:
            _need(first["type_class_observation"]==oldfirst["type_class"] and first["declared_payload_bytes"]==oldfirst["declared_payload_bytes"],
                "analysis_refused","analysis")
            # The inherited coarse observer may inspect a payload opening even
            # when the NEW shape observer deliberately stops at its unsupported
            # header. Do not force that row to claim payload interpretation.
            if first["observation_disposition"]!="header_only":
                _need(_raw(first["payload_opening_markers"])==_raw(oldfirst["payload_opening_markers"]),"analysis_refused","analysis")
    status=physical["status"]
    if status in {"observed_invalid_header_checksum","observed_unsupported_octal_size_field","unknown_magic_pattern_stop",
            "unsupported_type_or_extension_stop","directory_nonzero_payload_stop","observed_nonzero_member_padding"}:
        _need(physical["stop_range"] is not None and frontier==physical["structural_frontier_bytes"],"analysis_refused","analysis")
    if status in {"prefix_ended_at_next_header_boundary","prefix_ended_with_partial_payload","prefix_ended_with_partial_padding"}:
        _need(frontier==physical["structural_frontier_bytes"]==total,"analysis_refused","analysis")
    _control(_raw(value));return value


def _result(rsha,startsha,report=None,refusal=None):
    _need((report is None) is (refusal is not None),"analysis_refused","analysis")
    return {"schema":SCHEMA+"/result","reservation_sha256":rsha,"analysis_start_sha256":startsha,
        "report_retained":report is not None,"report_sha256":_sha(_raw(report)) if report is not None else None,
        "refusal":refusal,"contact_value_stored_or_hashed":False,"new_requests":0,"authority":_authority()}


def _complete(identity,fixture,forms,result):
    return {"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "control_sha256":{name:_sha(_raw(value)) for name,value in forms.items()},
        "result_sha256":_sha(_raw(result)),"result":result,"authority":_authority()}


def _capacity(fd):
    value=os.fstatvfs(fd);_need(value.f_bavail*value.f_frsize>=MIN_FREE_BYTES+8*MAX_CONTROL,"disk_reserve_refused","capacity")


def _preoutput_capacity(root):
    for count in range(len(ARTIFACT_PARTS)-1,-1,-1):
        held=None
        try:held=custody._Chain(root,ARTIFACT_PARTS[:count]);_capacity(held.fd);held.recheck();return
        except FileNotFoundError:continue
        finally:
            if held:held.close()
    raise PrefixShapeRunnerError("disk_reserve_refused","capacity")


def _run(*,root,identity,plan,contact,fixture,guard,held):
    if fixture:publication._fixture_root(root);publication._native_fixture_denial()
    else:_need(root==LANE_ROOT and contact is contact_io._stdin_contact and type(held) is _HeldPrefix,"fixed_actual_front_required")
    forms=_forms(identity,fixture,plan);folders=[];fresh=lock=None;locked=False;phase="capacity"
    try:
        guard();held.check();_need(held.metadata==plan["inputs"],"inputs_changed","inputs");_preoutput_capacity(root);phase="namespace"
        try:fresh=custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        except custody.ArchiveAssessmentRunnerError as error:
            if error.args==("output_cannot_resume_or_overwrite",):raise PrefixShapeRunnerError("fresh_namespace_already_exists",phase) from None
            raise
        top=old._Output(root.joinpath(*ARTIFACT_PARTS));folders.append(top);top.publish("scope.lock",LOCK_BYTES)
        lock=os.open("scope.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;version=old._version(os.fstat(lock));_capacity(top.fd)
        runs=old._Output(top.path/"runs",create=True);folders.append(runs)
        run=old._Output(runs.path/AUDIT_ID,create=True);folders.append(run);names=set();published={}
        def check():
            guard();held.check();fresh.recheck()
            for item in folders:item.check()
            _need(held.metadata==plan["inputs"] and top.tree is not None and set(os.listdir(top.fd))=={"scope.lock","runs"}
                and set(os.listdir(runs.fd))=={AUDIT_ID} and set(os.listdir(run.fd))==names
                and version==old._version(os.fstat(lock))==old._version(os.stat(
                    "scope.lock",dir_fd=top.fd,follow_symlinks=False)),"output_changed",phase)
        def publish(name,value):
            raw=_raw(value);pin=run.publish(name,raw,cap=MAX_CONTROL);names.add(name);published[name]=raw;check();return pin
        phase="reservation"
        for name in ("registration.json","reservation.json","input-preflight.json"):publish(name,forms[name])
        phase="contact";private=privacy._contact(contact(),observed=not fixture)
        contact_value={"schema":SCHEMA+"/contact","reservation_sha256":_sha(_raw(forms["reservation.json"])),
            "contact_present":True,"contact_value_stored_or_hashed":False};publish("contact-validated.json",contact_value)
        phase="start";publish("analysis-start.json",forms["analysis-start.json"]);phase="analysis";report=refusal=None
        try:
            if fixture:report=_analyse(identity,private,held,fixture=True)
            else:report=_child("analyse",identity,_raw({"contact":private,"inputs":plan["inputs"]})+b"\n")
            _report_valid(report,identity,plan["inputs"],fixture)
        except Exception as error:refusal=_safe(error,phase);report=None
        # Publication/custody failure is terminal, not a semantic analysis
        # refusal. Never mint a report_retained=False complete after a report
        # leaf has already been published and a later guard refuses it.
        if report is not None:phase="publication";publish("report.json",report)
        result=_result(_sha(_raw(forms["reservation.json"])),_sha(_raw(forms["analysis-start.json"])),report,refusal)
        phase="complete";publish("analysis-result.json",result);pin=publish("complete.json",_complete(identity,fixture,forms,result));phase="final";check()
        # Same-run exact readback while this producer retains its EX lock.
        # A separate readback worker cannot SH-lock an EX-held namespace; the
        # independently registered verifier later rederives the entire report.
        for name,raw in published.items():_need(run.read(name,cap=MAX_CONTROL)==raw,"readback_refused","readback")
        check();return {"schema":SCHEMA+"/public","complete_sha256":pin,"result":result,"authority":_authority()}
    except Exception as error:
        safe=_safe(error,phase);raise PrefixShapeRunnerError(safe["code"],safe["phase"]) from None
    finally:
        active=sys.exc_info()[0] is not None
        try:publication._close_all(folders,fresh,lock,locked)
        except Exception:
            if not active:raise PrefixShapeRunnerError("cleanup_refused","cleanup") from None


def _invented(*,root,original_root,original_complete_sha256,contact=lambda:"invented@unit.test",guard=lambda:None):
    root=Path(root);original_root=Path(original_root);publication._fixture_root(root)
    publication._fixture_root(original_root);publication._native_fixture_denial()
    _need(root!=original_root,"fixed_actual_front_required")
    oldrun=original_root.joinpath(*capture.ARTIFACT_PARTS,"runs",capture.AUDIT_ID)
    # Fixture pin assembly is explicit and never used by the actual front.
    originals={name:_sha((oldrun/name).read_bytes()) for name in ORIGINAL_PINS if name not in {"claim","prefix.bin"}}
    originals["complete.json"]=original_complete_sha256
    originals["claim"]=_sha((original_root.joinpath(*capture.ARTIFACT_PARTS,"claims",capture._claim_name())).read_bytes())
    originals["prefix.bin"]=_control((oldrun/"request-result.json").read_bytes())["prefix_sha256"]
    held=None
    try:
        held=_HeldPrefix(original_root,fixture=True,pins=originals)
        sources={SELF_PATH:"a"*64,TEST_PATH:"b"*64};identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,
            "source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
        return _run(root=root,identity=identity,plan=_plan(identity,held.metadata),contact=contact,fixture=True,guard=guard,held=held)
    finally:
        if held:held.close()


def _verify_files(root,pin,private,*,fixture,current_identity=None,original_root=None,original_pins=None):
    if fixture:publication._fixture_root(root);publication._native_fixture_denial()
    else:previous._isolated();source_runner._prove_isolation();_current(current_identity);_need(root==LANE_ROOT,"fixed_actual_front_required")
    _need(type(pin) is str and _SHA.fullmatch(pin),"readback_refused","readback")
    folders=[];held=lock=None
    try:
        held=_HeldPrefix(original_root if fixture else LANE_ROOT,fixture=fixture,pins=original_pins)
        def opened(path):
            value=directory._ReadbackDirectory(path);folders.append(value);return value
        top=opened(root.joinpath(*ARTIFACT_PARTS));runs=opened(top.path/"runs");run=opened(runs.path/AUDIT_ID)
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        version=privacy._file_version(os.fstat(lock))
        _need(top.read("scope.lock")==LOCK_BYTES and top.inventory=={"scope.lock","runs"} and runs.inventory=={AUDIT_ID},"readback_refused","readback")
        craw=run.read("complete.json",cap=MAX_CONTROL);_need(_sha(craw)==pin,"readback_refused","readback")
        complete=_control(craw);identity=complete["execution_identity"];_check_identity(identity,root)
        plan=_control(run.read("input-preflight.json",cap=MAX_CONTROL));forms=_forms(identity,fixture,plan)
        _need(_raw(plan["inputs"])==_raw(held.metadata),"inputs_changed","readback")
        result=_control(run.read("analysis-result.json",cap=MAX_CONTROL));rsha=_sha(_raw(forms["reservation.json"]))
        report=None;refusal=result.get("refusal")
        if result.get("report_retained") is True:
            report=_analyse(current_identity if not fixture else identity,private,held,fixture=fixture)
            # The recorded execution identity is the producer, not this later
            # verifier. All other derived observations must exactly replay.
            report["execution_identity"]=identity
            _report_valid(report,identity,plan["inputs"],fixture)
            _need(run.read("report.json",cap=MAX_CONTROL)==_raw(report),"readback_refused","readback")
        else:
            _need(type(refusal) is dict and set(refusal)=={"phase","code"} and type(refusal["phase"]) is type(refusal["code"]) is str
                and (refusal["code"] in _CODES and refusal["phase"] in _PHASES or refusal["code"] in _SHAPE_CODES.get(refusal["phase"],())),
                "readback_refused","readback")
        expected=_result(rsha,_sha(_raw(forms["analysis-start.json"])),report,refusal)
        names={*forms,"contact-validated.json","analysis-result.json","complete.json"}|({"report.json"} if report is not None else set())
        _need(_raw(result)==_raw(expected) and craw==_raw(_complete(identity,fixture,forms,expected)) and run.inventory==names,
            "readback_refused","readback")
        for name,value in forms.items():_need(run.read(name,cap=MAX_CONTROL)==_raw(value),"readback_refused","readback")
        _need(run.read("contact-validated.json")==_raw({"schema":SCHEMA+"/contact","reservation_sha256":rsha,
            "contact_present":True,"contact_value_stored_or_hashed":False}),"readback_refused","readback")
        for item in folders:item.check()
        held.check();_need(version==privacy._file_version(os.fstat(lock))==privacy._file_version(os.stat(
            "scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed","readback")
        if not fixture:_current(current_identity)
        return {"schema":SCHEMA+"/readback","complete_sha256":pin,"result":result,"producer_execution_identity":identity,
            "original_input_plan":plan,"current_contact_prefix_rescreened":report is not None,
            "original_contact_screen_replayed":False,"original_current_contact_equality_attested":False,"authority":_authority()}
    finally:publication._close_all([*folders,*([held] if held else [])],None,lock,lock is not None)


def _worker(role,identity,*,publish=False):
    _need(role in {"preflight","analyse","readback"},"metadata_refused","arguments")
    previous._isolated();source_runner._prove_isolation();memory=previous._WorkerMemoryGuard();held=None;phase="source"
    try:
        _current(identity);capture._compile_sources(identity);_current(identity);memory.check();phase="inputs"
        held=_HeldPrefix(LANE_ROOT)
        if role=="preflight":value=_plan(identity,held.metadata);_forms(identity,False,value)
        else:
            phase="input";line=sys.stdin.buffer.readline(MAX_CONTROL+1)
            _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"metadata_refused",phase)
            supplied=_control(line[:-1]);_need(type(supplied) is dict and "contact" in supplied,"metadata_refused",phase)
            private=privacy._contact(supplied["contact"],observed=True)
            if role=="analyse":
                _need(set(supplied)=={"contact","inputs"} and _raw(supplied["inputs"])==_raw(held.metadata),"inputs_changed","inputs")
                phase="analysis";value=_analyse(identity,private,held,fixture=False)
            else:
                _need(role=="readback" and set(supplied)=={"contact","complete_sha256"},"metadata_refused",phase)
                phase="readback";value=_verify_files(LANE_ROOT,supplied["complete_sha256"],private,fixture=False,current_identity=identity)
        held.check();_current(identity);memory.check();result={"ok":True,"value":value}
        if publish:
            encoded=_raw(result);_need(0<len(encoded)<=MAX_CONTROL,"metadata_refused","capacity")
            memory.check();sys.stdout.buffer.write(encoded+b"\n");sys.stdout.buffer.flush();memory.check();return None
        return result
    except Exception as error:
        result={"ok":False,"refusal":_safe(error,phase)}
        if publish:
            sys.stdout.buffer.write(_raw(result)+b"\n");sys.stdout.buffer.flush();memory.check();return None
        return result
    finally:source_runner.selector._close_all((held,memory),phase="prefix_shape_worker_cleanup")


def _command(role,identity):
    _need(role in {"preflight","analyse","readback"},"metadata_refused")
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_prefix_shape_runner_v1 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:m._worker("+repr(role)+",identity,publish=True)\nexcept Exception:print('{\"ok\":false,\"refusal\":{\"phase\":\"source\",\"code\":\"native_boundary_refused\"}}');sys.exit(2)"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    _need(type(payload) is bytes and len(payload)<=MAX_CONTROL,"metadata_refused","input")
    try:value=old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    except Exception:raise PrefixShapeRunnerError("native_boundary_refused","native_preflight" if role=="preflight" else "analysis") from None
    _need(type(value) is dict and type(value.get("ok")) is bool,"native_boundary_refused")
    if value["ok"] is False:
        refusal=value.get("refusal");_need(set(value)=={"ok","refusal"} and type(refusal) is dict and set(refusal)=={"phase","code"}
            and type(refusal["phase"]) is type(refusal["code"]) is str,"native_boundary_refused")
        checked=_safe(PrefixShapeRunnerError(refusal.get("code"),refusal.get("phase")),"analysis")
        if refusal.get("code") in _SHAPE_CODES.get(refusal.get("phase"),()):
            raise shape.PrefixShapeError(refusal["phase"],refusal["code"])
        _need(refusal==checked,"native_boundary_refused");raise PrefixShapeRunnerError(checked["code"],checked["phase"])
    _need(set(value)=={"ok","value"},"native_boundary_refused");return value["value"]


def _preflight(expected_head):
    identity=_identity(expected_head);plan=_child("preflight",identity);_forms(identity,False,plan);_parent_proofs(plan)
    _preoutput_capacity(LANE_ROOT);_need(not os.path.lexists(LANE_ROOT.joinpath(*ARTIFACT_PARTS)),"fresh_namespace_already_exists","namespace")
    _need(_identity(expected_head)==identity,"source_changed");return identity,plan


def run_actual(*,expected_head):
    identity,plan=_preflight(expected_head);held=None
    def guard():_need(_identity(expected_head)==identity,"source_changed")
    try:
        held=_HeldPrefix(LANE_ROOT);_need(_raw(held.metadata)==_raw(plan["inputs"]),"inputs_changed","inputs")
        return _run(root=LANE_ROOT,identity=identity,plan=plan,contact=contact_io._stdin_contact,fixture=False,guard=guard,held=held)
    finally:
        if held:held.close()


def verify_actual(*,expected_head,expected_report_sha256):
    identity=_identity(expected_head);plan=_child("preflight",identity);_forms(identity,False,plan);_parent_proofs(plan)
    private=privacy._contact(contact_io._stdin_contact(),observed=True)
    value=_child("readback",identity,_raw({"contact":private,"complete_sha256":expected_report_sha256})+b"\n")
    previous._source_git(value["producer_execution_identity"]);_parent_proofs(value["original_input_plan"])
    _need(_raw({**value["original_input_plan"],"execution_identity":identity})==_raw(plan),"inputs_changed","readback")
    _current(identity);_need(_identity(expected_head)==identity,"source_changed","final")
    return {k:v for k,v in value.items() if k!="original_input_plan"}


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise PrefixShapeRunnerError("private_arguments_refused","arguments")


def main(argv=None):
    saved=contact_io._protect_stdin_echo()
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--contact-stdin",action="store_true")
        parser.add_argument("--verify-report-sha256");args=parser.parse_args(argv)
        _need(args.contact_stdin,"private_contact_mode_refused","arguments")
        value=verify_actual(expected_head=args.expected_head,expected_report_sha256=args.verify_report_sha256) if args.verify_report_sha256 else run_actual(expected_head=args.expected_head)
        print(_raw(value).decode());return 0 if args.verify_report_sha256 or value["result"]["report_retained"] else 2
    except Exception as error:
        print(_raw({"disposition":"prefix_shape_refused",**_safe(error,"source")}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
