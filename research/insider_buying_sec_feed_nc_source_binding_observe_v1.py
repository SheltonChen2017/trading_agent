"""Read-only prefix NC/source17 observation; never admission or acquisition.

Preflight reads controls and source-file STATs only: ZIP content proof is
explicitly deferred. Analysis first rescreens the immutable old prefix and ALL
decoded bytes, then collects complete bounded NC payloads, creates genuine
private lexical routes and invokes the genuine full25 source binder once.
No private routes/rows/payloads or their value hashes leave the native worker.
No output namespace, journal, request, SDK, financial projection or file write.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_sec_feed_prefix_nc_observe_v1 as inherited
from research import insider_buying_sec_feed_nc_source_binding_v1 as binder

SCHEMA="insider-sec-feed-nc-source-binding-observe-v1"
SELF_PATH="research/insider_buying_sec_feed_nc_source_binding_observe_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_nc_source_binding_observe_v1.py"
REVIEW_TEST_PATH="tests/test_insider_buying_sec_feed_nc_source_binding_observe_v1_review.py"
AUDIT_ID="ib-sec-feed-prefix-nc-source17-offline-v1-20261025-once"
LANE_ROOT,LANE_BRANCH,EMPTY_CACHE_PREFIX=inherited.LANE_ROOT,inherited.LANE_BRANCH,inherited.EMPTY_CACHE_PREFIX
MAX_CONTROL,WORKER_SECONDS=2*1024**2,900
MAX_PAYLOAD,MAX_PAYLOADS,MAX_PAYLOAD_BYTES=1024**2,64,4*1024**2
capture,previous,custody,publication=inherited.capture,inherited.previous,inherited.custody,inherited.publication
privacy,contact_io,source_runner=inherited.privacy,inherited.contact_io,inherited.source_runner
selector,prior=source_runner.selector,source_runner.prior
shape,nc,route=inherited.pure.shape,inherited.pure,binder.route
_raw,_sha=inherited._raw,inherited._sha
FROZEN={**inherited.FROZEN,inherited.SELF_PATH:"cb66d434f0cefeb38bc85659feab8fce2f2b7431b03aef9a7d72550940d6d3df",
    inherited.TEST_PATH:"7fb1bd8ea5626595defdb2ad7ec94dd14d5008b98cafef7ce156a560028da107",
    binder.SELF_PATH:"90af57a48c5a3aaac3f77edf94bd92be795e1d957c5c4b1116afe8e97ae9698a",
    binder.TEST_PATH:"a3f724d471ccc10a7c6718a860a1bc86a73e84e1debe94ee1340e95f13ddb457",**binder.CODE_PINS}
_PHASES=frozenset({"arguments","source","native_preflight","inputs","input","privacy","collection","routes","source17","final","cleanup"})
_CODES=frozenset({"private_arguments_refused","private_contact_mode_refused","fixed_actual_front_required","source_changed",
    "metadata_refused","inputs_changed","native_boundary_refused","collection_refused","no_complete_NC_payloads_for_route_batch",
    "source17_refused","cleanup_refused"})
_BINDER_CODES=frozenset({"exact_NC_source_binding_required","exact_fixture_boolean_required","bounded_consumed_set_required",
    "bounded_genuine_route_claims_required","same_caller_consumed_set_required","route_index_refused","duplicate_route_index_refused",
    "genuine_unchanged_NC_source_binding_required","binding_route_order_refused","binding_record_refused","private_source_row_bound_refused",
    "private_source_row_identity_refused","binding_disposition_refused","binding_public_witness_refused","source_population_row_bound_refused",
    "source_quarter_order_refused","source_ordinal_gap_or_repeat_refused","source_population_byte_bound_refused","private_source_storage_bound_refused",
    "matching_source_occurrence_bound_refused","source_derivation_refused","complete_source_callback_accounting_refused",
    "route_batch_changed_during_source_scan","public_witness_byte_bound_refused"})
_REASONS=frozenset({"nonregular_or_extension_not_examined","unsupported_header_not_examined","non_NC_name_suffix_not_examined",
    "partial_physical_payload_not_examined","complete_payload_over_profile_not_examined","unsupported_header_semantics_not_examined",
    "collected_complete_observed_NC_payload"})


class NCBindingObserveError(ValueError):
    def __init__(self,code,phase="source"):
        self.phase=phase if type(phase) is str and phase in _PHASES else "source"
        super().__init__(code)


def _need(value,code,phase="source"):
    if not value:raise NCBindingObserveError(code,phase)


def _safe(error,phase):
    if type(error) is NCBindingObserveError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in _CODES \
            and type(getattr(error,"phase",None)) is str and error.phase in _PHASES:
        return {"phase":error.phase,"code":error.args[0]}
    if type(error) is binder.NCSourceBindingError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in _BINDER_CODES:
        return {"phase":"source17","code":error.args[0]}
    for kind,allowed in ((route.NCRouteError,route.SAFE_ERROR_CODES),(nc.NCStructureError,nc.SAFE_ERROR_CODES),
            (shape.PrefixShapeError,nc.SAFE_ERROR_CODES),(shape.core.PrefixFormatError,nc.SAFE_ERROR_CODES)):
        if type(error) is kind and type(getattr(error,"phase",None)) is type(getattr(error,"code",None)) is str and (error.phase,error.code) in allowed:
            return {"phase":error.phase,"code":error.code}
    return {"phase":phase if phase in _PHASES else "source","code":"source17_refused" if phase=="source17" else "metadata_refused"}


def _control(raw):
    _need(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL,"metadata_refused")
    value=capture._control(raw);_need(_raw(value)==raw,"metadata_refused");return value


def _close(holds):
    try:selector._close_all(holds,phase="NC_source17_observer_cleanup")
    except Exception:raise NCBindingObserveError("cleanup_refused","cleanup") from None


def _authority():
    return {"read_only_distinct_source17_observation":True,"new_namespace_created":False,"files_written":0,"new_requests":0,
        "SDK_calls":0,"outcome_looks":0,"whole_carrier_verified":False,"original_parent_or_XML_verified":False,
        "acceptance_identity_PIT_rights_or_canonical_verified":False,"backtesting_ready":False,
        "earlier_failed_archive_cause_established":False,"private_values_or_value_hashes_returned":False}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"original_prefix_pins":dict(inherited.inherited.ORIGINAL_PINS),
        "original_producer_head":inherited.inherited.ORIGINAL_HEAD,"historical_shape_provenance":dict(inherited.SHAPE_PROVENANCE),
        "question":"direct NC lexical routes joined to full25 source17; not the preceding NC-structure witness",
        "required_parent_source_window":"2020Q4..2025Q4","entry_pilot_window":"2021Q1..2025Q4",
        "context_source_window":"2020Q1..2026Q1","known_consumed_index_count":20044,
        "preflight_prefix_and_ZIP_body_bytes_read":0,"ZIP_body_hashes_deferred_to_analysis":True,
        "analysis_opaque_intake_ZIPs_hashed":82,"analysis_SUBMISSION_quarters_rederived":25,
        "maximum_complete_NC_payloads":MAX_PAYLOADS,"maximum_payload_bytes":MAX_PAYLOAD,
        "maximum_all_payload_bytes":MAX_PAYLOAD_BYTES,"maximum_control_or_IPC_bytes":MAX_CONTROL,
        "native_worker_seconds":WORKER_SECONDS,"memory_policy":previous._memory_policy(),
        "original_current_contact_equality_attested":False,"authority":_authority()}


def _paths():return (SELF_PATH,TEST_PATH,REVIEW_TEST_PATH,*FROZEN)


def _current(identity):
    publication._source_identity(identity,required_paths=_paths());inherited._current(identity)
    _need(custody._source_bytes(LANE_ROOT,tuple(FROZEN))==FROZEN,"source_changed")


def _identity(head):
    previous._isolated();_need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_front_required")
    value=inherited._identity(head);sources={**value["source_sha256"],**custody._source_bytes(LANE_ROOT,_paths())}
    for path,pin in sources.items():_need(_sha(custody._git(LANE_ROOT,"show",head+":"+path))==pin,"source_changed")
    value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))};_current(value);return value


class _IntakeMetadata:
    """Strict SH/FD STAT hold; not a ZIP hash/format/byte proof."""
    def __init__(self,*,fixture=False,root=None,manifest_pin=None,auxiliary_pin=None):
        self.tree=None
        try:
            _need(type(fixture) is bool,"metadata_refused","inputs")
            if fixture:
                selector._fixture_fence(root)
                _need(type(manifest_pin) is tuple and type(auxiliary_pin) is tuple,"metadata_refused","inputs")
            else:
                _need(root is manifest_pin is auxiliary_pin is None,"fixed_actual_front_required","inputs")
                root=LANE_ROOT.joinpath(*selector.INPUT_PARTS)
                manifest_pin=(selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256,selector.pure.census.RETAINED_ZIP_MANIFEST_SIZE_BYTES)
                auxiliary_pin=selector._AUX_PIN
            self.tree=selector.held_io._HeldCapture(root,private=False)
            manifest=self.tree.open(selector.pure.census._MANIFEST_NAME,manifest_pin[1]);raw=manifest.read(manifest_pin[1]+1)
            _need((len(raw),_sha(raw))==(manifest_pin[1],manifest_pin[0]),"inputs_changed","inputs")
            self.bindings=selector.pure.census._manifest_bindings(raw)
            _need(tuple(row.period for row in self.bindings)==selector.pure._periods(),"inputs_changed","inputs")
            names={selector.pure.census._MANIFEST_NAME,selector._AUX_NAME,*(row.filename for row in self.bindings)}
            _need(self.tree.names==names,"inputs_changed","inputs")
            auxiliary=self.tree.open(selector._AUX_NAME,auxiliary_pin[1])
            _need(selector.held_io._hash_stream(auxiliary,auxiliary_pin[1])==auxiliary_pin,"inputs_changed","inputs")
            for row in self.bindings:
                stream=self.tree.open(row.filename,row.size_bytes)
                _need(stream is not None and self.tree.handles[-1][2][4]==row.size_bytes
                    and stat.S_IMODE(self.tree.handles[-1][2][2]) in {0o600,0o644},"inputs_changed","inputs")
            self.manifest_raw=raw;self.manifest_sha256=manifest_pin[0];self.check()
        except BaseException:self.close();raise

    def check(self):self.tree.check()

    def match_genuine(self,held):
        _need(type(held) is selector._HeldIntake and held.manifest_raw==self.manifest_raw
            and held.context["manifest_sha256"]==self.manifest_sha256,"inputs_changed","inputs")
        self.check();held.tree.check()
        _need({name:version for name,_,version,_ in self.tree.handles}=={name:version for name,_,version,_ in held.tree.handles},
            "inputs_changed","inputs")

    def close(self):
        if self.tree:selector._close_tree(self.tree,phase="NC_source17_intake_metadata_cleanup");self.tree=None


class _SourceInputs:
    def __init__(self,root):
        self.old=self.accepted=self.intake=None
        try:
            self.old=previous._Inputs(root);self.accepted=prior._Held(root)
            accepted=prior._selector(self.accepted,prior.ACTUAL_ANCHORS)
            self.selection=self.accepted.leaf(prior.SELECTOR_PARTS,"selection.json",prior.MAX_CONTROL,prior.ACTUAL_ANCHORS.selection)
            complete=prior._json(self.accepted.leaf(prior.SELECTOR_PARTS,"complete.json",prior.MAX_CONTROL,prior.ACTUAL_ANCHORS.selector_complete))
            self.intake=_IntakeMetadata();self.consumed=frozenset(self.old.prior)
            _need(len(self.consumed)==len(self.old.prior)==20044,"inputs_changed","inputs")
            self.metadata={"schema":SCHEMA+"/source-inputs","accepted_selector":accepted,
                "selector_execution_identity":complete["current_execution_identity"],
                "intake_manifest_sha256":self.intake.manifest_sha256,"intake_leaf_count":84,"intake_ZIP_count":82,
                "retained_source_roster":self.old.plan["source_roster"],"consumed_control_pins":dict(previous.CONSUMED_PINS),
                "consumed_count":len(self.consumed),"consumed_index_sha256":previous.CONSUMED_PINS["consumed-index.json"],
                "consumed_execution_identity":self.old.complete["execution_identity"],"consumed_planner_receipt":self.old.complete["planner_receipt"],
                "raw_prefix_and_ZIP_body_bytes_read":0,"ZIP_body_hashes_verified_here":False,
                "old_original_parent_body_bytes_read":0,"unknown_prior_archive_memberships_remain_unknown":True}
            self.check()
        except BaseException:self.close();raise

    def check(self):
        self.old.check();self.accepted.recheck();self.intake.check()

    def close(self):
        _close((self.intake,self.accepted,self.old))
        self.intake=self.accepted=self.old=None


def _historical_identity(value,required):
    publication._source_identity(value,required_paths=required)
    sources=value["source_sha256"]
    _need(1<=len(sources)<=4096 and all(type(name) is str and len(name)<=512
        and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",name) and not name.startswith("/")
        and all(part not in {"",".",".."} for part in name.split("/")) for name in sources),"metadata_refused","inputs")


def _roster_metadata_valid(value):
    keys={"schema","fixture_only","context_window","pilot_window","intake_manifest_sha256","selection_sha256","schema_profile_sha256",
        "quarters","counts","context_form_counts","pilot_form_counts","source_row_jsonl_sha256","source_row_jsonl_bytes",
        "source_row_digest_framing","raw_source_cik_rewritten","financial_values_interpreted_or_projected","other_table_rows_parsed","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==binder.roster.SCHEMA and value["fixture_only"] is False
        and value["context_window"]=="2020Q1..2026Q1" and value["pilot_window"]=="2021Q1..2025Q4"
        and value["intake_manifest_sha256"]==selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
        and value["selection_sha256"]==prior.ACTUAL_ANCHORS.selection
        and value["schema_profile_sha256"]==selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256
        and value["source_row_digest_framing"]==binder.roster.FRAMING
        and value["raw_source_cik_rewritten"] is value["financial_values_interpreted_or_projected"] is value["other_table_rows_parsed"] is False
        and _raw(value["authority"])==_raw(selector.pure._authority())
        and type(value["quarters"]) is list and len(value["quarters"])==25
        and type(value["counts"]) is dict and set(value["counts"])==binder.roster.COUNT_KEYS
        and all(type(n) is int and 0<=n<=binder.MAX_SOURCE_ROWS for n in value["counts"].values()),"metadata_refused","inputs")
    _need(type(value["source_row_jsonl_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",value["source_row_jsonl_sha256"])
        and type(value["source_row_jsonl_bytes"]) is int and 0<=value["source_row_jsonl_bytes"]<=binder.MAX_SOURCE_ROW_JSONL_BYTES,"metadata_refused","inputs")
    quarterkeys={"period",*binder.roster.STAT_KEYS,"source_form_counts","zip_sha256","submission_member_sha256",
        "submission_header_line_sha256","source_row_jsonl_sha256","source_row_jsonl_bytes"}
    for period,row in zip(binder.roster.CONTEXT_PERIODS,value["quarters"],strict=True):
        _need(type(row) is dict and set(row)==quarterkeys and row["period"]==period
            and all(type(row[name]) is int and 0<=row[name]<=binder.MAX_SOURCE_ROWS for name in binder.roster.STAT_KEYS)
            and type(row["source_form_counts"]) is dict and set(row["source_form_counts"])==set(binder.roster.FORMS)
            and all(type(n) is int and n>=0 for n in row["source_form_counts"].values())
            and sum(row["source_form_counts"].values())==row["submission_rows"]
            and row["source_form_counts"]["4"]+row["source_form_counts"]["4/A"]==row["form4_or_4a_rows"]
            and all(type(row[name]) is str and re.fullmatch(r"[0-9a-f]{64}",row[name]) for name in
                ("zip_sha256","submission_member_sha256","submission_header_line_sha256","source_row_jsonl_sha256"))
            and type(row["source_row_jsonl_bytes"]) is int and 0<=row["source_row_jsonl_bytes"]<=binder.MAX_SOURCE_ROW_JSONL_BYTES,
            "metadata_refused","inputs")
    pilot=[row for row in value["quarters"] if row["period"] in binder.roster.PILOT_PERIODS]
    _need(value["counts"]=={"context_quarters":25,"pilot_quarters":20,
        "context_submission_rows":sum(row["submission_rows"] for row in value["quarters"]),
        "context_form4_or_4a_rows":sum(row["form4_or_4a_rows"] for row in value["quarters"]),
        "pilot_submission_rows":sum(row["submission_rows"] for row in pilot),"pilot_form4_or_4a_rows":sum(row["form4_or_4a_rows"] for row in pilot)}
        and value["source_row_jsonl_bytes"]==sum(row["source_row_jsonl_bytes"] for row in value["quarters"]),"metadata_refused","inputs")
    for name,rows in (("context_form_counts",value["quarters"]),("pilot_form_counts",pilot)):
        _need(type(value[name]) is dict and set(value[name])==set(binder.roster.FORMS)
            and all(type(n) is int and n>=0 for n in value[name].values())
            and value[name]=={form:sum(row["source_form_counts"][form] for row in rows) for form in binder.roster.FORMS},"metadata_refused","inputs")


def _source_metadata_valid(value):
    keys={"schema","accepted_selector","selector_execution_identity","intake_manifest_sha256","intake_leaf_count","intake_ZIP_count",
        "retained_source_roster","consumed_control_pins","consumed_count","consumed_index_sha256","consumed_execution_identity",
        "consumed_planner_receipt","raw_prefix_and_ZIP_body_bytes_read","ZIP_body_hashes_verified_here",
        "old_original_parent_body_bytes_read","unknown_prior_archive_memberships_remain_unknown"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/source-inputs"
        and value["intake_manifest_sha256"]==selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
        and type(value["intake_leaf_count"]) is type(value["intake_ZIP_count"]) is type(value["consumed_count"]) is int
        and (value["intake_leaf_count"],value["intake_ZIP_count"],value["consumed_count"])==(84,82,20044)
        and value["consumed_control_pins"]==previous.CONSUMED_PINS
        and value["consumed_index_sha256"]==previous.CONSUMED_PINS["consumed-index.json"]
        and type(value["raw_prefix_and_ZIP_body_bytes_read"]) is type(value["old_original_parent_body_bytes_read"]) is int
        and value["raw_prefix_and_ZIP_body_bytes_read"]==value["old_original_parent_body_bytes_read"]==0
        and value["ZIP_body_hashes_verified_here"] is False and value["unknown_prior_archive_memberships_remain_unknown"] is True,
        "metadata_refused","inputs")
    _historical_identity(value["selector_execution_identity"],(selector.SELF_PATH,selector.PURE_PATH))
    _historical_identity(value["consumed_execution_identity"],(previous.batch.SELF_PATH,previous.batch.TEST_PATH,
        previous.batch.campaign.SELF_PATH,previous.batch.campaign.TEST_PATH))
    summary=value["retained_source_roster"];accepted=value["accepted_selector"]
    _roster_metadata_valid(summary)
    acceptedkeys={"accepted_selection_sha256","accepted_complete_sha256","actual_success_observer_final_sha256","failed_predecessor_promoted",
        "source_capture_window","audit_quarter_window","quarters","pilot_quarter_count","pilot_counts","pilot_form_counts",
        "pilot_affected_periods","raw_zip_or_submission_rows_decoded_here","original_parent_admission_established_here"}
    _need(type(accepted) is dict and set(accepted)==acceptedkeys and accepted.get("accepted_selection_sha256")==prior.ACTUAL_ANCHORS.selection
        and accepted.get("accepted_complete_sha256")==prior.ACTUAL_ANCHORS.selector_complete
        and accepted.get("actual_success_observer_final_sha256")==prior.ACTUAL_ANCHORS.observer_final
        and accepted.get("failed_predecessor_promoted") is False
        and accepted["source_capture_window"]=="2006Q1..2026Q2" and accepted["audit_quarter_window"]=="2020Q1..2026Q1"
        and type(accepted["pilot_quarter_count"]) is int and accepted["pilot_quarter_count"]==20
        and accepted["raw_zip_or_submission_rows_decoded_here"] is accepted["original_parent_admission_established_here"] is False
        and type(accepted["quarters"]) is list and len(accepted["quarters"])==25,
        "metadata_refused","inputs")
    for left,right in zip(summary["quarters"],accepted["quarters"],strict=True):
        shared={"period",*binder.roster.STAT_KEYS,"source_form_counts","zip_sha256"}
        _need(type(right) is dict and set(right)==shared|{"selected_affected"} and type(right["selected_affected"]) is bool
            and _raw({key:left[key] for key in shared})==_raw({key:right[key] for key in shared}),"metadata_refused","inputs")
    pilot=[row for row in summary["quarters"] if row["period"] in binder.roster.PILOT_PERIODS]
    _need(_raw(accepted["pilot_counts"])==_raw({key:sum(row[key] for row in pilot) for key in binder.roster.STAT_KEYS})
        and _raw(accepted["pilot_form_counts"])==_raw(summary["pilot_form_counts"])
        and accepted["pilot_affected_periods"]==[row["period"] for row in accepted["quarters"] if row["period"] in binder.roster.PILOT_PERIODS and row["selected_affected"]],
        "metadata_refused","inputs")
    receipt=value["consumed_planner_receipt"]
    _need(type(receipt) is dict and set(receipt)=={"plan_sha256","complete_sha256","execution_identity"}
        and all(type(receipt[name]) is str and re.fullmatch(r"[0-9a-f]{64}",receipt[name]) for name in ("plan_sha256","complete_sha256")),"metadata_refused","inputs")
    _historical_identity(receipt["execution_identity"],(previous.batch.campaign.SELF_PATH,previous.batch.campaign.TEST_PATH,
        previous.batch.campaign.CAPTURE_SOURCE_PATH,previous.batch.campaign.CAPTURE_TEST_PATH))


def _plan(identity,prefix,source):
    return {"schema":SCHEMA+"/metadata-preflight","execution_identity":identity,"prefix_inputs":prefix,"source_inputs":source,
        "registration_sha256":_sha(_raw(registration())),"contact_reads":0,"raw_prefix_and_ZIP_body_bytes_read":0,
        "source_body_proofs_deferred":True,"authority":_authority()}


def _plan_valid(value,identity):
    keys={"schema","execution_identity","prefix_inputs","source_inputs","registration_sha256","contact_reads",
        "raw_prefix_and_ZIP_body_bytes_read","source_body_proofs_deferred","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/metadata-preflight"
        and _raw(value["execution_identity"])==_raw(identity) and value["registration_sha256"]==_sha(_raw(registration()))
        and type(value["contact_reads"]) is type(value["raw_prefix_and_ZIP_body_bytes_read"]) is int
        and value["contact_reads"]==value["raw_prefix_and_ZIP_body_bytes_read"]==0 and value["source_body_proofs_deferred"] is True
        and _raw(value["authority"])==_raw(_authority()),"metadata_refused","native_preflight")
    inherited._metadata_valid(value["prefix_inputs"],LANE_ROOT);_source_metadata_valid(value["source_inputs"])
    _control(_raw(value));return value


def _collect(raw,private,fixture):
    observed=shape.qualify_prefix_shape(raw,privacy_contact=private,fixture_only=fixture)
    rows=observed["physical_shape_observations"]["headers"];selected=[];dispositions={};total=0
    for row in rows:
        if row["type_class_observation"]!="regular":reason="nonregular_or_extension_not_examined"
        elif row["magic_pattern_observation"]=="unknown" or not row["header_checksum_matches"]:reason="unsupported_header_not_examined"
        elif not row["fixed_name_fields_have_nc_suffix"]:reason="non_NC_name_suffix_not_examined"
        elif not row["complete_physical_span_observed_within_prefix"]:reason="partial_physical_payload_not_examined"
        elif row["declared_payload_bytes"]>MAX_PAYLOAD:reason="complete_payload_over_profile_not_examined"
        else:selected.append(row["ordinal"]);total+=row["declared_payload_bytes"];reason="collected_complete_observed_NC_payload"
        dispositions[row["ordinal"]]=reason
    _need(len(selected)<=MAX_PAYLOADS and total<=MAX_PAYLOAD_BYTES,"collection_refused","collection")
    collector=nc._Collect(rows,set(selected));_,decoded,complete,incomplete=shape.core._decode_prefix(raw,collector)
    descriptor=observed["prefix_format_descriptor"]
    _need(collector.finished and decoded==collector.total==descriptor["decoded_prefix_bytes"]
        and complete==descriptor["completed_gzip_members_with_observed_valid_trailers"]
        and incomplete is descriptor["last_observed_gzip_member_incomplete"],"collection_refused","collection")
    payloads=[];ordinals=[]
    for row in rows:
        ordinal=row["ordinal"];header=bytes(collector.headers[ordinal]);_need(len(header)==512,"collection_refused","collection")
        if ordinal in selected:
            if not nc._plain_header_semantics(header,row["magic_pattern_observation"]):dispositions[ordinal]="unsupported_header_semantics_not_examined"
            else:
                payload=bytes(collector.payloads[ordinal]);_need(len(payload)==row["declared_payload_bytes"],"collection_refused","collection")
                payloads.append(payload);ordinals.append(ordinal)
    geometry={"prefix_bytes":len(raw),"decoded_prefix_bytes":decoded,"physical_headers_observed":len(rows),
        "completed_gzip_members_observed":complete,"last_gzip_member_incomplete":incomplete,"third_decode_counts_match":True,
        "candidate_payloads_collected":len(selected),"candidate_payload_bytes_collected":total,
        "route_payloads_examined":len(payloads),"route_payload_bytes_examined":sum(map(len,payloads)),
        "unexamined_physical_members":len(rows)-len(payloads),"examined_physical_ordinals":ordinals,
        "member_dispositions":[dispositions[row["ordinal"]] for row in rows],"all_observed_physical_headers_accounted":True,
        "whole_carrier_or_unobserved_members_accounted":False,"finite_raw_and_ALL_decoded_privacy_precedes_routes":True}
    return tuple(payloads),geometry


def _binding_valid(value,source,fixture):
    keys={"schema","fixture_only","route_grammar_profile","required_parent_source_window","entry_pilot_window","context_source_window",
        "all25_source_quarters_completed","source_population_counts","context_form_counts","pilot_form_counts","source_accounting",
        "route_batch","eligible_join_disposition_counts","eligible_join_count","route_batch_quarantined_members","private_source17_candidate_count",
        "all_input_NC_members_accounted","consumption_scope","source_values_or_value_hashes_exported","code_dependency_pins","authority"}
    _need(type(value) is dict and set(value)==keys,"source17_refused","source17")
    route.validate_nc_route_batch_witness(value["route_batch"],fixture_only=fixture)
    summary=source["retained_source_roster"];records=value["eligible_join_disposition_counts"];stats=value["source_accounting"]
    _need(value["schema"]==binder.SCHEMA and value["fixture_only"] is fixture and value["route_grammar_profile"]==route.PROFILE
        and value["required_parent_source_window"]=="2020Q4..2025Q4" and value["entry_pilot_window"]=="2021Q1..2025Q4"
        and value["context_source_window"]=="2020Q1..2026Q1" and value["all25_source_quarters_completed"] is True
        and _raw(value["source_population_counts"])==_raw(summary["counts"]) and _raw(value["context_form_counts"])==_raw(summary["context_form_counts"])
        and _raw(value["pilot_form_counts"])==_raw(summary["pilot_form_counts"]) and value["code_dependency_pins"]==binder.CODE_PINS
        and _raw(value["authority"])==_raw(binder._authority()) and type(records) is dict and set(records)<=binder.DISPOSITIONS
        and all(type(count) is int and count>0 for count in records.values())
        and type(value["eligible_join_count"]) is type(value["private_source17_candidate_count"]) is type(value["route_batch_quarantined_members"]) is int
        and value["eligible_join_count"]==sum(records.values())==value["route_batch"]["eligible_private_claims"]
        and value["private_source17_candidate_count"]==records.get("private_lexical_source17_candidate_not_admitted",0)
        and value["route_batch_quarantined_members"]==value["route_batch"]["members"]-value["eligible_join_count"]
        and value["all_input_NC_members_accounted"] is True and value["source_values_or_value_hashes_exported"] is False
        and value["consumption_scope"]=="exact caller-supplied set; no named journal attestation","source17_refused","source17")
    names={"source_rows_accounted","source_row_bytes_accounted","unique_source_accessions","cross_quarter_repeat_occurrences",
        "cross_quarter_repeated_accessions","cross_quarter_identity_conflict_occurrences","cross_quarter_identity_conflict_accessions",
        "rows_matching_eligible_route_accessions","rows_without_eligible_route_accessions","caller_consumed_accessions"}
    _need(type(stats) is dict and set(stats)==names and all(type(count) is int and count>=0 for count in stats.values())
        and stats["source_rows_accounted"]==summary["counts"]["context_submission_rows"]
        and stats["source_row_bytes_accounted"]==summary["source_row_jsonl_bytes"] and stats["caller_consumed_accessions"]==source["consumed_count"]
        and stats["unique_source_accessions"]+stats["cross_quarter_repeat_occurrences"]==stats["source_rows_accounted"]
        and stats["rows_matching_eligible_route_accessions"]+stats["rows_without_eligible_route_accessions"]==stats["source_rows_accounted"]
        and stats["cross_quarter_identity_conflict_occurrences"]<=stats["cross_quarter_repeat_occurrences"]
        and stats["cross_quarter_identity_conflict_accessions"]<=stats["cross_quarter_repeated_accessions"]<=stats["cross_quarter_repeat_occurrences"],
        "source17_refused","source17")


def _geometry_valid(value):
    keys={"prefix_bytes","decoded_prefix_bytes","physical_headers_observed","completed_gzip_members_observed","last_gzip_member_incomplete",
        "third_decode_counts_match","candidate_payloads_collected","candidate_payload_bytes_collected","route_payloads_examined",
        "route_payload_bytes_examined","unexamined_physical_members","examined_physical_ordinals","member_dispositions",
        "all_observed_physical_headers_accounted","whole_carrier_or_unobserved_members_accounted","finite_raw_and_ALL_decoded_privacy_precedes_routes"}
    _need(type(value) is dict and set(value)==keys,"collection_refused","collection")
    integerkeys={"prefix_bytes","decoded_prefix_bytes","physical_headers_observed","completed_gzip_members_observed","candidate_payloads_collected",
        "candidate_payload_bytes_collected","route_payloads_examined","route_payload_bytes_examined","unexamined_physical_members"}
    _need(all(type(value[key]) is int and value[key]>=0 for key in integerkeys)
        and value["prefix_bytes"]==65536 and value["decoded_prefix_bytes"]<=shape.core.MAX_DECODED_BYTES
        and value["physical_headers_observed"]<=256 and value["completed_gzip_members_observed"]<=shape.core.MAX_GZIP_MEMBERS
        and type(value["last_gzip_member_incomplete"]) is bool and value["third_decode_counts_match"] is True
        and value["all_observed_physical_headers_accounted"] is value["finite_raw_and_ALL_decoded_privacy_precedes_routes"] is True
        and value["whole_carrier_or_unobserved_members_accounted"] is False
        and type(value["member_dispositions"]) is list and len(value["member_dispositions"])==value["physical_headers_observed"]
        and all(type(item) is str and item in _REASONS for item in value["member_dispositions"])
        and type(value["examined_physical_ordinals"]) is list and all(type(item) is int for item in value["examined_physical_ordinals"])
        and value["examined_physical_ordinals"]==[i for i,reason in enumerate(value["member_dispositions"],1) if reason=="collected_complete_observed_NC_payload"]
        and len(value["examined_physical_ordinals"])==value["route_payloads_examined"]
        and value["route_payloads_examined"]+value["unexamined_physical_members"]==value["physical_headers_observed"]
        and value["candidate_payloads_collected"]==sum(reason in {"collected_complete_observed_NC_payload","unsupported_header_semantics_not_examined"}
            for reason in value["member_dispositions"])
        and value["route_payloads_examined"]<=value["candidate_payloads_collected"]<=min(MAX_PAYLOADS,value["physical_headers_observed"])
        and value["route_payload_bytes_examined"]<=value["candidate_payload_bytes_collected"]<=MAX_PAYLOAD_BYTES
        and value["decoded_prefix_bytes"]>=512*value["physical_headers_observed"]+value["candidate_payload_bytes_collected"],"collection_refused","collection")


def _witness_valid(value,identity,plan,fixture):
    keys={"schema","fixture_only","execution_identity","registration_sha256","input_plan_sha256","original_prefix_complete_sha256",
        "original_prefix_sha256","geometry","source17_binding","source_rederivation_matches_retained_roster",
        "current_contact_prefix_rescreened","original_current_contact_equality_attested","analysis_opaque_intake_ZIPs_hashed",
        "analysis_SUBMISSION_quarters_rederived","private_claims_rows_and_payloads_not_returned","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/witness" and value["fixture_only"] is fixture
        and _raw(value["execution_identity"])==_raw(identity) and value["registration_sha256"]==_sha(_raw(registration()))
        and value["input_plan_sha256"]==_sha(_raw(plan))
        and value["original_prefix_complete_sha256"]==plan["prefix_inputs"]["external_pins"]["complete.json"]
        and value["original_prefix_sha256"]==plan["prefix_inputs"]["external_pins"]["prefix.bin"]
        and value["source_rederivation_matches_retained_roster"] is value["current_contact_prefix_rescreened"] is value["private_claims_rows_and_payloads_not_returned"] is True
        and value["original_current_contact_equality_attested"] is False
        and type(value["analysis_opaque_intake_ZIPs_hashed"]) is type(value["analysis_SUBMISSION_quarters_rederived"]) is int
        and (value["analysis_opaque_intake_ZIPs_hashed"],value["analysis_SUBMISSION_quarters_rederived"])==(82,25)
        and _raw(value["authority"])==_raw(_authority()),"source17_refused","source17")
    _geometry_valid(value["geometry"]);_binding_valid(value["source17_binding"],plan["source_inputs"],fixture)
    _need(value["geometry"]["route_payloads_examined"]==value["source17_binding"]["route_batch"]["members"]
        and value["geometry"]["route_payload_bytes_examined"]==value["source17_binding"]["route_batch"]["payload_bytes"],"source17_refused","source17")
    _control(_raw(value));return value


def _analysis_intake():return selector._HeldIntake()


def _analyse(identity,private,prefix,source,plan,*,fixture=False):
    raw=prefix.read_body()
    replay=capture._verify_files(prefix.root,prefix.pins["complete.json"],private,fixture=fixture,current_identity=None if fixture else identity)
    payloads,geometry=_collect(raw,private,fixture)
    _need(_sha(raw)==prefix.pins["prefix.bin"] and replay["producer_execution_identity"]==prefix.metadata["original_execution_identity"]
        and replay["current_contact_prefix_rescreened"] is True,"inputs_changed","privacy")
    _need(payloads,"no_complete_NC_payloads_for_route_batch","collection")
    batch=route.assess_nc_route_batch(payloads,consumed_accessions=source.consumed,privacy_contact=private,fixture_only=fixture)
    prefix.check();source.check();intake=None
    try:
        intake=_analysis_intake();source.intake.match_genuine(intake)
        bound=binder.bind_nc_routes_to_source17(route_batch=batch,intake_manifest_raw=intake.manifest_raw,
            expected_manifest_sha256=intake.context["manifest_sha256"],selection_raw=source.selection,
            expected_selection_sha256=_sha(source.selection) if fixture else prior.ACTUAL_ANCHORS.selection,
            quarter_inputs=binder.roster.held_context_quarters(intake),
            consumed_accessions=source.consumed,fixture_only=fixture)
        _need(binder.validate_nc_source_binding(bound)._roster.to_payload()==source.metadata["retained_source_roster"],"source17_refused","source17")
        intake.recheck();source.intake.match_genuine(intake);prefix.check();source.check()
        value={"schema":SCHEMA+"/witness","fixture_only":fixture,"execution_identity":identity,"registration_sha256":_sha(_raw(registration())),
            "input_plan_sha256":_sha(_raw(plan)),"original_prefix_complete_sha256":prefix.pins["complete.json"],"original_prefix_sha256":prefix.pins["prefix.bin"],
            "geometry":geometry,"source17_binding":bound.public_witness(),"source_rederivation_matches_retained_roster":True,
            "current_contact_prefix_rescreened":True,"original_current_contact_equality_attested":False,"analysis_opaque_intake_ZIPs_hashed":82,
            "analysis_SUBMISSION_quarters_rederived":25,"private_claims_rows_and_payloads_not_returned":True,"authority":_authority()}
        return _witness_valid(value,identity,plan,fixture)
    finally:_close((intake,))


def _worker(role,identity,*,publish=False):
    _need(role in {"preflight","observe"},"metadata_refused","arguments")
    previous._isolated();source_runner._prove_isolation();memory=previous._WorkerMemoryGuard();prefix=source=None;phase="source"
    try:
        _current(identity);capture._compile_sources(identity);_current(identity);memory.check();phase="inputs"
        prefix=inherited.inherited._HeldPrefix(LANE_ROOT);source=_SourceInputs(LANE_ROOT)
        plan=_plan_valid(_plan(identity,prefix.metadata,source.metadata),identity)
        if role=="preflight":value=plan
        else:
            phase="input";line=sys.stdin.buffer.readline(MAX_CONTROL+1)
            _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"metadata_refused",phase);supplied=_control(line[:-1])
            _need(type(supplied) is dict and set(supplied)=={"contact","plan"} and _raw(supplied["plan"])==_raw(plan),"inputs_changed","inputs")
            private=privacy._contact(supplied["contact"],observed=True);phase="source17"
            value=_analyse(identity,private,prefix,source,plan)
        prefix.check();source.check();_current(identity);memory.check();result={"ok":True,"value":value}
        if not publish:return result
        encoded=_raw(result);_need(len(encoded)+1<=MAX_CONTROL,"metadata_refused","input")
        memory.check();sys.stdout.buffer.write(encoded+b"\n");sys.stdout.buffer.flush();memory.check()
    except Exception as error:
        result={"ok":False,"refusal":_safe(error,phase)}
        if not publish:return result
        sys.stdout.buffer.write(_raw(result)+b"\n");sys.stdout.buffer.flush();memory.check()
    finally:_close((source,prefix,memory))


def _command(role,identity):
    _need(role in {"preflight","observe"},"metadata_refused")
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:m._worker("+repr(role)+",identity,publish=True)\nexcept Exception:print('{\"ok\":false,\"refusal\":{\"phase\":\"source\",\"code\":\"native_boundary_refused\"}}');sys.exit(2)"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    _need(type(payload) is bytes and len(payload)<=MAX_CONTROL,"metadata_refused","input")
    try:value=inherited.inherited.old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    except Exception:raise NCBindingObserveError("native_boundary_refused","native_preflight") from None
    _control(_raw(value))
    _need(type(value) is dict and type(value.get("ok")) is bool,"native_boundary_refused")
    if value["ok"] is False:
        refusal=value.get("refusal");allowed=route.SAFE_ERROR_CODES|nc.SAFE_ERROR_CODES
        _need(set(value)=={"ok","refusal"} and type(refusal) is dict and set(refusal)=={"phase","code"}
            and type(refusal["phase"]) is type(refusal["code"]) is str
            and (refusal["phase"] in _PHASES and refusal["code"] in _CODES or (refusal["phase"],refusal["code"]) in allowed
                or refusal["phase"]=="source17" and refusal["code"] in _BINDER_CODES),"native_boundary_refused")
        if refusal["phase"]=="source17" and refusal["code"] in _BINDER_CODES:raise binder.NCSourceBindingError(refusal["code"])
        if (refusal["phase"],refusal["code"]) in route.SAFE_ERROR_CODES:raise route.NCRouteError(refusal["phase"],refusal["code"])
        if (refusal["phase"],refusal["code"]) in nc.SAFE_ERROR_CODES:raise nc.NCStructureError(refusal["phase"],refusal["code"])
        raise NCBindingObserveError(refusal["code"],refusal["phase"])
    _need(set(value)=={"ok","value"},"native_boundary_refused");return value["value"]


def _parent_proofs(plan):
    inherited.inherited._parent_proofs({"inputs":plan["prefix_inputs"]})
    source=plan["source_inputs"]
    previous._source_git(source["selector_execution_identity"]);previous._source_git(source["consumed_execution_identity"])
    previous.batch.campaign.verify_plan_producer(source["consumed_planner_receipt"])


def _preflight(expected_head):
    identity=_identity(expected_head);plan=_plan_valid(_child("preflight",identity),identity);_parent_proofs(plan)
    _need(_identity(expected_head)==identity,"source_changed","final");return identity,plan


def preflight_actual(*,expected_head):
    identity,plan=_preflight(expected_head);return {"schema":SCHEMA+"/ready","execution_identity":identity,"plan":plan}


def observe_actual(*,expected_head):
    identity,plan=_preflight(expected_head);prefix=source=None
    try:
        prefix=inherited.inherited._HeldPrefix(LANE_ROOT);source=_SourceInputs(LANE_ROOT)
        _need(_raw(_plan(identity,prefix.metadata,source.metadata))==_raw(plan),"inputs_changed","inputs")
        prefix.check();source.check();_need(_identity(expected_head)==identity,"source_changed")
        private=privacy._contact(contact_io._stdin_contact(),observed=True)
        prefix.check();source.check();_current(identity)
        value=_child("observe",identity,_raw({"contact":private,"plan":plan})+b"\n")
        _witness_valid(value,identity,plan,False);prefix.check();source.check();_current(identity);_parent_proofs(plan)
        _need(_identity(expected_head)==identity,"source_changed","final");return value
    finally:_close((source,prefix))


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise NCBindingObserveError("private_arguments_refused","arguments")


def main(argv=None):
    saved=contact_io._protect_stdin_echo()
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--contact-stdin",action="store_true")
        parser.add_argument("--preflight-only",action="store_true");args=parser.parse_args(argv)
        _need(args.preflight_only or args.contact_stdin,"private_contact_mode_refused","arguments")
        value=preflight_actual(expected_head=args.expected_head) if args.preflight_only else observe_actual(expected_head=args.expected_head)
        print(_raw(value).decode());return 0
    except Exception as error:
        print(_raw({"disposition":"NC_source17_observation_refused",**_safe(error,"source")}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
