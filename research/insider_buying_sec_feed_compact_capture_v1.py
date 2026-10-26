"""ONE fresh Dec3 carrier, retained compact NC candidates only, never admission.

The carrier is immutable RAM input to initially native-denied workers. It is
NEVER hashed or persisted. All gzip/TAR integrity precedes any selected-object
hash/publication. Only whole physical header/payload/padding spans that pass
the unchanged finite privacy screen enter private CAS. Filename routing is not
identity. Later readback replays retained objects, NOT the discarded carrier.
No provider, private contact or artifact is accessed merely by importing this
module. Actual fronts require a qualified clean source image and fresh scope.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
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
from research import insider_buying_sec_feed_compact_members_v1 as compact
from research import insider_buying_pilot_sec_roster as roster

directory, old, batch = previous.directory, previous.old, previous.batch
publication, custody, privacy, source_runner = previous.publication, previous.custody, previous.privacy, previous.source_runner
contact_io = previous.contact_io
_raw, _sha, _control = previous._raw, previous._sha, previous._control
SCHEMA = "insider-sec-feed-compact-capture-v1"
SELF_PATH = "research/insider_buying_sec_feed_compact_capture_v1.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_compact_capture_v1.py"
REVIEW_TEST_PATH = "tests/test_insider_buying_sec_feed_compact_capture_v1_review.py"
PURE_PATH = "research/insider_buying_sec_feed_compact_members_v1.py"
PURE_TEST_PATH = "tests/test_insider_buying_sec_feed_compact_members_v1.py"
PURE_REVIEW_TEST_PATH = "tests/test_insider_buying_sec_feed_compact_members_v1_review.py"
LANE_ROOT, LANE_BRANCH, EMPTY_CACHE_PREFIX = previous.LANE_ROOT, previous.LANE_BRANCH, previous.EMPTY_CACHE_PREFIX
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sec_feed_compact_capture_v1")
AUDIT_ID = "ib-sec-feed-archive-20201203-compact-v1-20261025-once"
URL = "https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/20201203.nc.tar.gz"
LOCK_BYTES = b"INSETF-one-unused-20201203-compact-members-v1\n"
MAX_COMPRESSED, MAX_CONTROL = 512*1024**2, 64*1024**2
MAX_PHYSICAL, MAX_METADATA, CHUNK = 24*1024**2, 8*1024**2, 65536
TRANSPORT_SECONDS, IDLE_SECONDS, WORKER_SECONDS = 1200, 15, 3600
MIN_FREE_BYTES = 8*1024**3
FROZEN = {**previous.FROZEN, previous.SELF_PATH:"b53808d458e270db465586b9863e2acc3efa56f9c42e7524cc6424a0aa2261e0",
    previous.TEST_PATH:"abe696390af1316d70654bbdb146880d480ddc2e199aa248f1fb409647d6ee18",
    "research/insider_buying_pilot_sec_roster.py":"e14c0e23d22604ee583cbb4958ab371ec56b619741a5a2e5da7211db73c7eaf4",
    "tests/test_insider_buying_pilot_sec_roster.py":"914fb29161d87c5553be4b3bc1546356e57908afff3dd31e089589e68c2f83aa"}
_TOKEN = object()
_ACTIVATIONS, _DISPATCH = weakref.WeakKeyDictionary(), weakref.WeakKeyDictionary()
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PHASES = frozenset({"arguments","source","native_preflight","inputs","capacity","namespace","reservation",
    "contact","claim","start","transport","inspection","publication","complete","final","readback","cleanup"})


class CompactCaptureError(ValueError):
    """Finite own phase/code, never foreign exception or contact text."""


class _Deadline(Exception): pass


def _need(value, code):
    if not value: raise CompactCaptureError(code)


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "digest_refused")
    return value


def _authority():
    return {**previous._authority(), "full_raw_retention_scope_only":False,
        "retained_compact_member_candidate_only":True, "whole_carrier_hashed":False,
        "whole_carrier_retained":False, "source_identity_validated":False}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"method":"GET","url":URL,
        "source_ordinal":43,"listed_name":"20201203.nc.tar.gz","advertised_size_text":"493450 KB",
        "advertised_KB_base_or_rounding_qualified":False,"advertisement_is_not_actual_bytes":True,
        "directory_report_sha256":previous.DIRECTORY_REPORT,"directory_body_sha256":previous.DIRECTORY_BODY,
        "directory_inventory_sha256":previous.DIRECTORY_INVENTORY,"maximum_GETs":1,
        "maximum_compressed_bytes":MAX_COMPRESSED,"transport_absolute_seconds":TRANSPORT_SECONDS,
        "transport_idle_seconds":IDLE_SECONDS,"native_worker_wall_seconds":WORKER_SECONDS,
        "native_worker_memory_policy":previous._memory_policy(),"minimum_free_reserve_bytes":MIN_FREE_BYTES,
        "maximum_selected_physical_bytes":MAX_PHYSICAL,"maximum_selected_payload_bytes":8*1024**2,
        "maximum_selected_candidates":4096,"maximum_nonhex_IPC_metadata_bytes":MAX_METADATA,
        "maximum_IPC_bytes":MAX_CONTROL,"maximum_binary_chunk_bytes":CHUNK,
        "all_25_six_form_source_quarters_rederived":True,"selected_forms":["4","4/A"],
        "late_cross_quarter_repeats_quarantined":True,"known_consumed_dispatch_index_count":20044,
        "redirects":False,"proxies":False,"retries":False,"HEAD_Range_alias_requests":False,
        "whole_carrier_hash_retention_or_privacy_claim":False,"individual_parent_dispatches":0,
        "member_XML_financial_interpretation":False,"current_contact_readback_rescreen_registered":True,
        "original_current_contact_equality_attested":False,"discarded_carrier_replay_possible":False,
        "earlier_June_or_October_URLs_retried":False,"authority":_authority()}


def _classified(phase, error):
    allowed = {"private_arguments_refused","private_contact_mode_refused","fixed_actual_front_required",
        "source_changed","native_worker_refused","native_preflight_refused","inputs_changed",
        "fresh_namespace_already_exists","disk_reserve_refused","trusted_activation_required",
        "dispatch_context_refused","transport_front_refused","absolute_transport_deadline",
        "transport_cleanup_refused","output_inventory_changed","output_lock_changed","readback_pin_refused",
        "readback_crosslinks_refused","compact_result_refused","metadata_capacity_refused","local_operation_refused"}
    code = error.args[0] if type(error) is CompactCaptureError and len(error.args)==1 else None
    result = CompactCaptureError(code if code in allowed else "local_operation_refused")
    result.phase = phase if phase in _PHASES else "source"
    return result


def _current(identity):
    previous._check_identity(identity, LANE_ROOT)
    publication._source_identity(identity, required_paths=(SELF_PATH,TEST_PATH,REVIEW_TEST_PATH,PURE_PATH,PURE_TEST_PATH,PURE_REVIEW_TEST_PATH,*FROZEN))
    _need(custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"])) == identity["source_sha256"]
        and custody._source_bytes(LANE_ROOT,tuple(FROZEN)) == FROZEN
        and custody._source_bytes(LANE_ROOT,tuple(source_runner.FROZEN)) == source_runner.FROZEN,
        "source_changed")
    _need(set(custody._internal_source_paths(LANE_ROOT)) <= set(identity["source_sha256"]), "source_changed")


def _identity(head):
    previous._isolated()
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH, "fixed_actual_front_required")
    value = batch.campaign._identity(head)
    own = custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH,REVIEW_TEST_PATH,PURE_PATH,PURE_TEST_PATH,PURE_REVIEW_TEST_PATH,*FROZEN))
    for name,digest in own.items():
        _need(_sha(custody._git(LANE_ROOT,"show",head+":"+name)) == digest, "source_changed")
    sources = {**value["source_sha256"],**own}
    value = {**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    _current(value)
    return value


class _RosterRoutes:
    """Lightweight all-occurrence accounting, never old body/compiler replay."""
    def __init__(self):
        self.seen, self.repeated, self.conflicted, self.q4 = {}, set(), set(), {}
        self.occurrences = self.repeat_occurrences = self.conflict_occurrences = 0

    def consume(self,row):
        # Rows come from the exact source parser; independently verify its seal
        # hash/shape before retaining metadata. Never change a raw CIK field.
        _need(type(row) is dict and set(row)==roster.ROW_KEYS
            and row["filing_metadata_sha256"] == _sha(_raw({k:v for k,v in row.items() if k!="filing_metadata_sha256"})),
            "source_row_refused")
        accession = row["accession_number"]
        identity = _sha(_raw({k:row[k] for k in ("accession_number","form_type","filing_date","issuer_comparison_key")}))
        previous_identity = self.seen.get(accession)
        if previous_identity is None: self.seen[accession] = identity
        else:
            self.repeated.add(accession);self.repeat_occurrences += 1
            if previous_identity != identity:
                self.conflicted.add(accession);self.conflict_occurrences += 1
        if row["period"]=="2020Q4":
            _need(accession not in self.q4, "within_quarter_source_duplicate_refused")
            self.q4[accession] = copy.deepcopy(row)
        self.occurrences += 1

    def finish(self,summary,prior):
        _need(summary["counts"]["context_submission_rows"]==self.occurrences, "source_occurrence_count_refused")
        q = next(row for row in summary["quarters"] if row["period"]=="2020Q4")
        forms = dict(Counter(row["form_type"] for row in self.q4.values()))
        _need(len(self.q4)==q["submission_rows"] and {form:forms.get(form,0) for form in roster.FORMS}==q["source_form_counts"],
            "source_quarter_counts_refused")
        ordered = sorted(self.q4.values(),key=lambda row:row["source_record_ordinal"])
        framing = b"".join(_raw(row)+b"\n" for row in ordered)
        _need(_sha(framing)==q["source_row_jsonl_sha256"] and len(framing)==q["source_row_jsonl_bytes"], "source_quarter_digest_refused")
        eligible = {a for a,row in self.q4.items() if row["form_type"] in {"4","4/A"} and a not in self.repeated and a not in self.conflicted}
        receipt = {"schema":SCHEMA+"/source-roster","source_roster":summary,"source_roster_sha256":_sha(_raw(summary)),
            "q4_receipt":q,"q4_all_six_rows":len(self.q4),"q4_four_or_four_a_rows":q["form4_or_4a_rows"],
            "q4_other_context_rows":len(self.q4)-q["form4_or_4a_rows"],"q4_eligible_after_repeat_quarantine":len(eligible),
            "full_25_source_occurrences":self.occurrences,"cross_quarter_repeat_occurrences":self.repeat_occurrences,
            "cross_quarter_conflict_occurrences":self.conflict_occurrences,
            "cross_quarter_repeat_accessions":len(self.repeated),"cross_quarter_conflict_accessions":len(self.conflicted),
            "q4_repeated_accessions":len(set(self.q4)&self.repeated),"q4_conflicted_accessions":len(set(self.q4)&self.conflicted),
            "q4_known_consumed_routing_accessions":len(set(self.q4)&set(prior)),
            "source_rows_globally_deduplicated":False,"raw_source_fields_rewritten":False,
            "prior_consumption_is_not_admission":True,"XML_or_financial_fields_parsed":False}
        receipt["routing_scope"]=compact._scope_binding((frozenset(self.q4),frozenset(eligible),frozenset(prior)))
        return receipt, frozenset(self.q4), frozenset(eligible)


class _Inputs:
    """Strict old inputs, no old parent bodies; holds remain open through use."""
    def __init__(self,root,*,source_receipt=None):
        self.old = self.accepted = self.intake = None
        try:
            self.old = previous._Inputs(root)  # OLD Oct7 selection stays labelled OLD.
            listing_path=root.joinpath(*directory.ARTIFACT_PARTS,"runs",directory.AUDIT_ID)
            listing=[folder for folder in self.old.folders if folder is not None and folder.path==listing_path]
            _need(len(listing)==1,"old_listing_hold_refused")
            inventory = directory.parse_directory_inventory(listing[0].read("response.bin",cap=directory.MAX_RESPONSE_BYTES))
            rows = [r for r in inventory["entries"] if r["qualified_archive_url"]==URL]
            _need(len(rows)==1 and rows[0]["source_ordinal"]==43 and rows[0]["listed_name"]=="20201203.nc.tar.gz"
                and rows[0]["advertised_size_text"]=="493450 KB", "new_directory_selection_refused")
            self.accepted = source_runner.prior._Held(root)
            source_runner.prior._selector(self.accepted,source_runner.prior.ACTUAL_ANCHORS)
            selected = self.accepted.leaf(source_runner.prior.SELECTOR_PARTS,"selection.json",source_runner.prior.MAX_CONTROL,
                source_runner.prior.ACTUAL_ANCHORS.selection)
            self.intake = source_runner.selector._HeldIntake()
            self.prior = tuple(self.old.metadata["prior_accessions"])
            if source_receipt is None:
                # Source-row interpretation is confined to the initially
                # native-denied worker. The trusted parent only holds/hashes
                # old inputs and validates this worker's compact controls.
                previous._isolated();source_runner._prove_isolation()
                routes = _RosterRoutes()
                genuine = roster.derive_pilot_sec_roster(intake_manifest_raw=self.intake.manifest_raw,
                    expected_manifest_sha256=self.intake.context["manifest_sha256"],selection_raw=selected,
                    expected_selection_sha256=source_runner.prior.ACTUAL_ANCHORS.selection,
                    quarter_inputs=roster.held_context_quarters(self.intake),consume_row=routes.consume,fixture_only=False)
                _need(genuine.to_payload()==self.old.plan["source_roster"],"original_source_roster_changed")
                source, self.roster_set, self.eligible = routes.finish(genuine.to_payload(),self.prior)
                self.rows = routes.q4
            else:
                source=_control(_raw(source_receipt));summary=source["source_roster"]
                _need(source["source_roster_sha256"]==_sha(_raw(summary))
                    and summary==self.old.plan["source_roster"]
                    and summary["intake_manifest_sha256"]==self.intake.context["manifest_sha256"]
                    and summary["selection_sha256"]==source_runner.prior.ACTUAL_ANCHORS.selection
                    and summary["schema_profile_sha256"]==self.intake.context["schema_profile_sha256"],"inputs_changed")
                self.rows=self.roster_set=self.eligible=None
            self.metadata = {"schema":SCHEMA+"/inputs","old_listing_and_consumption":self.old.metadata,
                "new_selected_row":rows[0],"source_receipt":source,"source_receipt_sha256":_sha(_raw(source)),
                "old_original_parent_body_bytes_read":0,"full_source_tables_decoded":["SUBMISSION.tsv"],
                "original_source_cik_rewritten":False,"unknown_prior_archive_memberships_remain_unknown":True}
            _need(source["cross_quarter_repeat_occurrences"]==self.old.plan["parent_audit"]["context_counts"]["cross_quarter_repeat_filings"]
                and source["cross_quarter_conflict_occurrences"]==self.old.plan["parent_audit"]["context_counts"]["cross_quarter_identity_conflict_filings"],
                "original_source_repeat_accounting_changed")
            self.check(full=True)
        except BaseException:
            self.close();raise

    def check(self,*,full=False):
        self.old.check();self.accepted.recheck();self.intake.tree.check()
        if full:self.intake.recheck()

    def close(self):
        source_runner.selector._close_all((self.intake,self.accepted,self.old),phase="compact_input_cleanup")
        self.old = self.accepted = self.intake = None


def _source_binding(row):
    return {key:row[key] for key in ("source_record_ordinal","filing_metadata_sha256","form_type",
        "quarterly_zip_sha256","submission_member_sha256","submission_header_line_sha256","schema_profile_sha256")}


def _screen(raw,contact):
    _need(type(raw) is bytes, "privacy_input_refused")
    screen = old._TextScreen(contact)
    for at in range(0,len(raw),CHUNK):screen.feed(raw[at:at+CHUNK])
    screen.feed(b"",final=True)


def _headers(value):
    pairs = previous._headers(value)
    return pairs


def _header_screen(pairs,private):
    for name,value in pairs:
        _screen(name.encode("latin-1"),private);_screen(value.encode("latin-1"),private)
    _screen(_raw(pairs),private)


def _wire(result,rows,receipt_sha,pairs,private):
    _need(type(result) is compact.CompactResult, "compact_result_refused")
    manifest = result.manifest();entries=[];binaries=[]
    for candidate in result.candidates:
        _need(type(candidate) is compact.CompactCandidate and candidate.routing_accession in rows, "compact_result_refused")
        descriptor=candidate.descriptor();raw=candidate.physical_bytes
        row=rows[candidate.routing_accession]
        _need(row["form_type"] in {"4","4/A"},"compact_result_refused")
        entries.append({"physical_sha256":descriptor["physical_sha256"],"source_binding":_source_binding(row)})
        binaries.append({"physical_sha256":descriptor["physical_sha256"],
            "chunks_hex":[raw[i:i+CHUNK].hex() for i in range(0,len(raw),CHUNK)]})
    value={"schema":SCHEMA+"/inspection","compact":manifest,"source_receipt_sha256":receipt_sha,
        "headers_sha256":_sha(_raw(pairs)),"selected":entries,"binary_objects":binaries,
        "carrier_hashed_or_retained":False,"authority":_authority()}
    _validate_wire(value,fixture=manifest["fixture_only"])
    # Metadata is only fixed own labels, pins and finite integer controls; still
    # screen the complete retained control before returning/hash/publication.
    _screen(_raw({**value,"binary_objects":[{**b,"chunks_hex":[]} for b in binaries]}),private)
    return value


def _decode_objects(value):
    _need(type(value) is list and len(value)<=4096,"compact_result_refused")
    objects={};total=0
    for item in value:
        _need(type(item) is dict and set(item)=={"physical_sha256","chunks_hex"},"compact_result_refused")
        pin=_digest(item["physical_sha256"]);chunks=item["chunks_hex"]
        _need(pin not in objects and type(chunks) is list and 1<=len(chunks)<=129,"compact_result_refused")
        parts=[]
        for index,part in enumerate(chunks):
            _need(type(part) is str and 0<len(part)<=2*CHUNK and len(part)%2==0
                and re.fullmatch(r"[0-9a-f]+",part) and (index==len(chunks)-1 or len(part)==2*CHUNK),"compact_result_refused")
            parts.append(bytes.fromhex(part))
        raw=b"".join(parts);total+=len(raw)
        _need(total<=MAX_PHYSICAL and len(raw)<=8*1024**2+1023 and _sha(raw)==pin,"compact_result_refused")
        objects[pin]=raw
    return objects


_MANIFEST_FALSE = ("caller_roster_form_or_source_evidence_verified_here","whole_carrier_hashed","whole_carrier_privacy_screened",
    "discarded_member_bytes_hashed_or_returned","discarded_carrier_replay_possible_from_result","dependency_pins_runtime_attested_here",
    "HTTP_framing_verified_here","original_source_authenticated","filing_population_completeness_established","universal_privacy_claim",
    "XML_or_financial_fields_parsed","acceptance_or_PIT_verified","rights_verified","canonical_admitted","backtesting_ready",
    "original_failed_archive_cause_established")
_MANIFEST_COUNT = ("gzip_members_observed","physical_members_observed","decoded_bytes_observed","compressed_bytes_observed",
    "candidate_pool_count","candidate_pool_physical_bytes","retained_candidates","retained_physical_bytes")
_MANIFEST_OTHER = ("schema","fixture_only","routing_scope","name_profile","unsafe_basename_shadow_hints_only_for_duplicate_quarantine",
    "original_carrier_gzip_integrity_observed","original_carrier_physical_integrity_observed","immutable_no_hash_passes",
    "all_compressed_bytes_accounted","disposition_counts","candidates","format_source_sha256","privacy_source_sha256","SDK_calls","outcome_looks")


def _validate_wire(value,*,fixture,with_binary=True):
    keys={"schema","compact","source_receipt_sha256","headers_sha256","selected","carrier_hashed_or_retained","authority"}
    _need(type(value) is dict and set(value)==keys|({"binary_objects"} if with_binary else set())
        and value["schema"]==SCHEMA+"/inspection" and value["carrier_hashed_or_retained"] is False
        and _raw(value["authority"])==_raw(_authority()),"compact_result_refused")
    for key in ("source_receipt_sha256","headers_sha256"):_digest(value[key])
    form=value["compact"]
    _need(type(form) is dict and set(form)==set(_MANIFEST_FALSE)|set(_MANIFEST_COUNT)|set(_MANIFEST_OTHER)
        and form["schema"]==compact.SCHEMA and form["fixture_only"] is fixture
        and all(form[k] is False for k in _MANIFEST_FALSE)
        and all(form[k] is True for k in ("unsafe_basename_shadow_hints_only_for_duplicate_quarantine",
            "original_carrier_gzip_integrity_observed","original_carrier_physical_integrity_observed","all_compressed_bytes_accounted"))
        and type(form["immutable_no_hash_passes"]) is int and form["immutable_no_hash_passes"]==2
        and all(type(form[k]) is int and 0<=form[k] for k in (*_MANIFEST_COUNT,"SDK_calls","outcome_looks"))
        and form["SDK_calls"]==form["outcome_looks"]==0
        and form["format_source_sha256"]==compact.FORMAT_SOURCE_SHA256
        and form["privacy_source_sha256"]==compact.engine.PRIVACY_SOURCE_SHA256,"compact_result_refused")
    _need(all(_raw(form[key])==_raw(expected) for key,expected in compact._STATIC_MANIFEST.items()),"compact_result_refused")
    _need(form["gzip_members_observed"]<=100000 and form["physical_members_observed"]<=100000
        and form["decoded_bytes_observed"]<=8*1024**3 and 0<form["compressed_bytes_observed"]<=MAX_COMPRESSED
        and form["candidate_pool_count"]<=4096 and form["candidate_pool_physical_bytes"]<=MAX_PHYSICAL
        and form["retained_candidates"]<=form["candidate_pool_count"] and form["retained_physical_bytes"]<=form["candidate_pool_physical_bytes"],
        "compact_result_refused")
    counts=form["disposition_counts"]
    allowed=set(compact._DISPOSITIONS)
    _need(type(counts) is dict and set(counts)<=allowed and all(type(n) is int and 0<n<=100000 for n in counts.values())
        and sum(counts.values())==form["physical_members_observed"]
        and counts.get("retained_identity_unvalidated_candidate",0)==form["retained_candidates"],"compact_result_refused")
    private_count=counts.get("finite_member_privacy_refused_unhashed_unretained",0)
    private_bytes=form["candidate_pool_physical_bytes"]-form["retained_physical_bytes"]
    _need(1<=form["gzip_members_observed"] and 0<form["decoded_bytes_observed"]
        and form["decoded_bytes_observed"]%512==0 and form["decoded_bytes_observed"]<=form["compressed_bytes_observed"]*128
        and form["physical_members_observed"]*512+1024<=form["decoded_bytes_observed"]
        and form["candidate_pool_count"]==form["retained_candidates"]+private_count<=form["physical_members_observed"]
        and form["candidate_pool_physical_bytes"]%512==0
        and form["candidate_pool_physical_bytes"]<=form["decoded_bytes_observed"]-1024
        and 512*private_count<=private_bytes<=(8*1024**2+512)*private_count
        and (form["candidate_pool_count"]!=0 or form["candidate_pool_physical_bytes"]==0),"compact_result_refused")
    _need(type(form["routing_scope"]) is dict and set(form["routing_scope"])=={"roster","eligible","consumed"},"compact_result_refused")
    for binding in form["routing_scope"].values():
        _need(type(binding) is dict and set(binding)=={"count","sorted_newline_sha256"}
            and type(binding["count"]) is int and 0<=binding["count"]<=1500000,"compact_result_refused")
        _digest(binding["sorted_newline_sha256"])
    selected=value["selected"]
    _need(type(selected) is list and len(selected)==form["retained_candidates"] and len(form["candidates"])==len(selected),"compact_result_refused")
    seen=set();total=0;last=0;last_end=0
    for item,descriptor in zip(selected,form["candidates"],strict=True):
        descriptor_keys={"schema","source_ordinal","header_range","payload_range","padding_range","physical_bytes","payload_bytes",
            "routing_key_sha256","physical_sha256","header_sha256","payload_sha256","padding_sha256","header_profile","type_class",
            "safe_relative_path","finite_member_privacy_screened","identity_validated","quarantined","XML_or_financial_fields_parsed",
            "complete_submission_projection_created","admitted"}
        _need(type(item) is dict and set(item)=={"physical_sha256","source_binding"}
            and type(descriptor) is dict and set(descriptor)==descriptor_keys and item["physical_sha256"]==descriptor["physical_sha256"]
            and descriptor["schema"]==compact.SCHEMA+"/candidate" and type(descriptor["source_ordinal"]) is int
            and last<descriptor["source_ordinal"]<=form["physical_members_observed"]
            and descriptor["header_profile"] in {"v7-finite","ustar-finite"} and descriptor["type_class"]=="regular"
            and all(descriptor[k] is True for k in ("safe_relative_path","finite_member_privacy_screened","quarantined"))
            and all(descriptor[k] is False for k in ("identity_validated","XML_or_financial_fields_parsed","complete_submission_projection_created","admitted")),
            "compact_result_refused")
        last=descriptor["source_ordinal"];pin=_digest(descriptor["physical_sha256"])
        for key in ("routing_key_sha256","header_sha256","payload_sha256","padding_sha256"):_digest(descriptor[key])
        for key in ("header_range","payload_range","padding_range"):
            _need(type(descriptor[key]) is list and len(descriptor[key])==2
                and all(type(n) is int and 0<=n<=8*1024**3 for n in descriptor[key]),"compact_result_refused")
        origin=descriptor["header_range"][0];payload=descriptor["payload_bytes"]
        _need(pin not in seen and type(payload) is int and 0<=payload<=8*1024**2
            and type(descriptor["physical_bytes"]) is int and 512<=descriptor["physical_bytes"]<=8*1024**2+512
            and origin%512==0 and origin>=last_end
            and descriptor["header_range"]==[origin,origin+512]
            and descriptor["payload_range"]==[origin+512,origin+512+payload]
            and descriptor["padding_range"]==[origin+512+payload,origin+descriptor["physical_bytes"]]
            and descriptor["physical_bytes"]==512+payload+(-payload)%512
            and descriptor["padding_range"][1]<=form["decoded_bytes_observed"]-1024,"compact_result_refused")
        last_end=descriptor["padding_range"][1]
        seen.add(pin);total+=descriptor["physical_bytes"]
        source=item["source_binding"]
        _need(type(source) is dict and set(source)=={"source_record_ordinal","filing_metadata_sha256","form_type",
            "quarterly_zip_sha256","submission_member_sha256","submission_header_line_sha256","schema_profile_sha256"}
            and type(source["source_record_ordinal"]) is int and 1<=source["source_record_ordinal"]<=1500000
            and source["form_type"] in {"4","4/A"},"compact_result_refused")
        for key in source:
            if key.endswith("sha256"):_digest(source[key])
    _need(total==form["retained_physical_bytes"]<=MAX_PHYSICAL,"compact_result_refused")
    if with_binary:
        objects=_decode_objects(value["binary_objects"])
        _need(set(objects)==seen and all(len(objects[desc["physical_sha256"]])==desc["physical_bytes"] for desc in form["candidates"]),"compact_result_refused")
        for desc in form["candidates"]:
            span=objects[desc["physical_sha256"]];size=desc["payload_bytes"]
            _need(_sha(span[:512])==desc["header_sha256"] and _sha(span[512:512+size])==desc["payload_sha256"]
                and _sha(span[512+size:])==desc["padding_sha256"] and not any(span[512+size:]),"compact_result_refused")
        wire_size=len(_raw(value))
        hexadecimal_size=sum(len(chunk) for item in value["binary_objects"] for chunk in item["chunks_hex"])
        # Include every quote/comma/bracket in the NONHEX ceiling, not merely
        # the empty-list skeleton used for retained-control privacy screening.
        _need(wire_size-hexadecimal_size<=MAX_METADATA and wire_size<=MAX_CONTROL,"metadata_capacity_refused")
    else:_need(len(_raw(value))<=MAX_METADATA,"metadata_capacity_refused")
    _control(_raw(value))
    return value


def _inspect(raw,pairs,private,inputs,*,fixture):
    private=privacy._contact(private,observed=not fixture);_header_screen(pairs,private)
    result=compact.compact_members(raw,roster_accessions=inputs.roster_set,eligible_accessions=inputs.eligible,
        consumed_accessions=frozenset(inputs.prior),privacy_contact=private,fixture_only=fixture)
    return _wire(result,inputs.rows,inputs.metadata["source_receipt_sha256"],pairs,private)


def _validate_inspection_plan(value,plan,*,fixture):
    _validate_wire(value,fixture=fixture,with_binary="binary_objects" in value)
    _need(value["source_receipt_sha256"]==plan["inputs"]["source_receipt_sha256"],"compact_result_refused")
    if fixture:
        scope=plan["inputs"]["invented_scope"]
        expected=compact._scope_binding(tuple(frozenset(scope[k]) for k in ("roster","eligible","prior")))
    else:expected=plan["inputs"]["source_receipt"]["routing_scope"]
    _need(_raw(value["compact"]["routing_scope"])==_raw(expected),"compact_result_refused")
    if not fixture:
        source=plan["inputs"]["source_receipt"];q=source["q4_receipt"];profile=source["source_roster"]["schema_profile_sha256"]
        anchors={"quarterly_zip_sha256":q["zip_sha256"],"submission_member_sha256":q["submission_member_sha256"],
            "submission_header_line_sha256":q["submission_header_line_sha256"],"schema_profile_sha256":profile}
        for selected in value["selected"]:
            binding=selected["source_binding"]
            _need(binding["source_record_ordinal"]<=q["submission_rows"]
                and all(binding[key]==pin for key,pin in anchors.items()),"compact_result_refused")


def _validate_plan(plan,identity,*,fixture):
    keys={"schema","execution_identity","inputs","fixture_only"} if fixture else {
        "schema","execution_identity","inputs","consumption_proof","new_provider_requests","contact_reads","output_namespace_created","authority"}
    _need(type(plan) is dict and set(plan)==keys and plan["schema"]==SCHEMA+"/input-preflight"
        and _raw(plan["execution_identity"])==_raw(identity),"inputs_changed")
    if fixture:
        _need(plan["fixture_only"] is True,"inputs_changed");return plan
    _need(type(plan["new_provider_requests"]) is type(plan["contact_reads"]) is int
        and plan["new_provider_requests"]==plan["contact_reads"]==0 and plan["output_namespace_created"] is False
        and _raw(plan["authority"])==_raw(_authority()),"inputs_changed")
    inputs=plan["inputs"]
    _need(type(inputs) is dict and set(inputs)=={"schema","old_listing_and_consumption","new_selected_row","source_receipt",
        "source_receipt_sha256","old_original_parent_body_bytes_read","full_source_tables_decoded","original_source_cik_rewritten",
        "unknown_prior_archive_memberships_remain_unknown"} and inputs["schema"]==SCHEMA+"/inputs"
        and inputs["old_original_parent_body_bytes_read"]==0 and type(inputs["old_original_parent_body_bytes_read"]) is int
        and inputs["full_source_tables_decoded"]==["SUBMISSION.tsv"] and inputs["original_source_cik_rewritten"] is False
        and inputs["unknown_prior_archive_memberships_remain_unknown"] is True
        and inputs["source_receipt_sha256"]==_sha(_raw(inputs["source_receipt"])),"inputs_changed")
    selected=inputs["new_selected_row"]
    _need(selected["source_ordinal"]==43 and type(selected["source_ordinal"]) is int and selected["listed_name"]=="20201203.nc.tar.gz"
        and selected["qualified_archive_url"]==URL and selected["advertised_size_text"]=="493450 KB","inputs_changed")
    prior=inputs["old_listing_and_consumption"]
    previous._prior(prior["prior_accessions"])
    _need(len(prior["prior_accessions"])==20044
        and prior["consumed_pins"]==previous.CONSUMED_PINS,"inputs_changed")
    source=inputs["source_receipt"];summary=source["source_roster"]
    _need(source["schema"]==SCHEMA+"/source-roster" and source["source_roster_sha256"]==_sha(_raw(summary))
        and summary["schema"]==roster.SCHEMA and summary["fixture_only"] is False
        and [r["period"] for r in summary["quarters"]]==list(roster.CONTEXT_PERIODS)
        and summary["counts"]=={"context_quarters":25,"pilot_quarters":20,"context_submission_rows":1281147,
            "context_form4_or_4a_rows":1163648,"pilot_submission_rows":1008318,"pilot_form4_or_4a_rows":921570}
        and summary["selection_sha256"]==source_runner.prior.ACTUAL_ANCHORS.selection
        and summary["intake_manifest_sha256"]==source_runner.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
        and summary["schema_profile_sha256"]==source_runner.selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256
        and source["q4_receipt"]==next(q for q in summary["quarters"] if q["period"]=="2020Q4")
        and source["full_25_source_occurrences"]==1281147,"inputs_changed")
    proof=plan["consumption_proof"]
    _need(proof["batch_number"]==1 and proof["complete_sha256"]==previous.CONSUMED_PINS["complete.json"]
        and proof["plan_sha256"]==previous.CONSUMED_PINS["plan.json"]
        and proof["index_sha256"]==previous.CONSUMED_PINS["consumed-index.json"]
        and proof["capture_execution_identity"]==prior["capture_execution_identity"],"inputs_changed")
    return plan


def _preflight_worker(identity):
    held=None
    try:
        _current(identity);held=_Inputs(LANE_ROOT)
        proof,prior=batch.read_actual_predecessor(1,execution_identity=identity,**{
            "expected_complete_sha256":previous.CONSUMED_PINS["complete.json"],
            "expected_plan_sha256":previous.CONSUMED_PINS["plan.json"],
            "expected_index_sha256":previous.CONSUMED_PINS["consumed-index.json"]})
        _need(tuple(prior)==held.prior and len(prior)==20044,"inputs_changed")
        value={"schema":SCHEMA+"/input-preflight","execution_identity":identity,"inputs":held.metadata,
            "consumption_proof":proof,"new_provider_requests":0,"contact_reads":0,"output_namespace_created":False,
            "authority":_authority()}
        held.check(full=True);_current(identity);_forms(identity,False,value)
        return value
    finally:
        source_runner.selector._close_all((held,),phase="compact_preflight_cleanup")


def _worker(role,identity,*,publish=False):
    previous._isolated();source_runner._prove_isolation()
    memory=previous._WorkerMemoryGuard()
    try:
        _current(identity);memory.check()
        if role=="preflight":value=_preflight_worker(identity)
        else:
            line=sys.stdin.buffer.readline(MAX_CONTROL+1)
            _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"private_stdin_bound")
            body=_control(line[:-1]);private=privacy._contact(body["contact"],observed=True)
            if role=="readback":
                _need(set(body)=={"contact","report_sha256"},"private_stdin_schema")
                value=_verify_files(LANE_ROOT,body["report_sha256"],private,fixture=False,current_identity=identity)
            else:
                _need(role=="inspect" and set(body)=={"contact","headers","bytes","plan"}
                    and type(body["bytes"]) is int and 0<body["bytes"]<=MAX_COMPRESSED,"private_stdin_schema")
                raw=sys.stdin.buffer.read(body["bytes"]+1)
                _need(len(raw)==body["bytes"],"private_stdin_bound")
                held=None
                try:
                    held=_Inputs(LANE_ROOT)
                    _need(held.metadata==body["plan"]["inputs"],"inputs_changed")
                    value=_inspect(raw,_headers(body["headers"]),private,held,fixture=False)
                    held.check(full=True);_current(identity)
                finally:source_runner.selector._close_all((held,),phase="compact_inspect_cleanup")
        _current(identity);memory.check()
        if publish:
            raw=_raw({"ok":True,"value":value});_need(0<len(raw)<=MAX_CONTROL,"native_stdout_bound")
            memory.check();sys.stdout.buffer.write(raw+b"\n");sys.stdout.buffer.flush();memory.check();return None
        return {"ok":True,"value":value}
    finally:source_runner.selector._close_all((memory,),phase="compact_worker_memory_cleanup")


def _command(role,identity):
    _need(role in {"preflight","inspect","readback"},"worker_role_refused")
    code=("import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_compact_capture_v1 as m;"
        "identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry:m._worker("+repr(role)+",identity,publish=True)"
        "\nexcept Exception:print('{\"ok\":false,\"code\":\"native_worker_refused\"}');sys.exit(2)")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    value=old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    _need(type(value) is dict and set(value)=={"ok","value"} and value["ok"] is True,"native_worker_refused")
    return value["value"]


def _capacity(fd):
    space=os.fstatvfs(fd)
    _need(space.f_bavail*space.f_frsize>=MIN_FREE_BYTES+MAX_PHYSICAL+4*MAX_CONTROL,"disk_reserve_refused")


def _preoutput_capacity(root):
    for count in range(len(ARTIFACT_PARTS)-1,-1,-1):
        held=None
        try:
            held=custody._Chain(root,ARTIFACT_PARTS[:count]);_capacity(held.fd);held.recheck();return
        except FileNotFoundError:continue
        finally:
            if held:held.close()
    raise CompactCaptureError("disk_reserve_refused")


def _claim_name():return _sha(b"GET\0"+URL.encode("ascii"))+".json"


def _forms(identity,fixture,plan):
    previous._check_identity(identity,Path(identity["root"]))
    _validate_plan(plan,identity,fixture=fixture)
    reservation={"schema":SCHEMA+"/reservation","audit_id":AUDIT_ID,"fixture_only":fixture,"registration":registration(),
        "registration_sha256":_sha(_raw(registration())),"execution_identity":identity,"input_preflight_sha256":_sha(_raw(plan))}
    rsha=_sha(_raw(reservation));claim={"schema":SCHEMA+"/URL-claim","method":"GET","url":URL,"reservation_sha256":rsha}
    start={"schema":SCHEMA+"/start","attempt":1,"reservation_sha256":rsha,"claim_sha256":_sha(_raw(claim))}
    values={"reservation.json":reservation,"input-preflight.json":plan,"claim.json":claim,"request-start.json":start}
    for value in values.values():_need(_control(_raw(value))==value,"metadata_capacity_refused")
    _need(sum(len(_raw(value)) for value in values.values())<MAX_METADATA,"metadata_capacity_refused")
    return values


class _Activation:
    def __init__(self,identity,guard,held):self.identity,self.guard,self.held=identity,guard,held


def _activated(value,identity):
    _need(type(value) is _Activation and _ACTIVATIONS.get(value)==(_raw(identity),id(value.guard),id(value.held))
        and _raw(value.identity)==_raw(identity) and type(value.held) is _Inputs,"trusted_activation_required")
    value.guard();value.held.check()


class _Dispatch:
    def __init__(self,token,activation,identity,guard,prove,headers):
        _need(token is _TOKEN,"dispatch_context_refused")
        self.activation,self.identity,self.guard,self.prove,self.headers=activation,identity,guard,prove,headers
        self.attempted=False
        _DISPATCH[self]=(id(activation),_raw(identity),id(guard),id(prove),_raw(headers))


def _transport(context):
    _need(type(context) is _Dispatch and _DISPATCH.get(context)==(id(context.activation),_raw(context.identity),id(context.guard),id(context.prove),_raw(context.headers))
        and not context.attempted,"dispatch_context_refused")
    _activated(context.activation,context.identity);context.guard();context.prove()
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.),"transport_front_refused")
    previous_handler=signal.getsignal(signal.SIGALRM);connection=None;begun=time.monotonic()
    def expired(*_):raise _Deadline()
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,TRANSPORT_SECONDS);context.attempted=True
        connection=http.client.HTTPSConnection("www.sec.gov",timeout=IDLE_SECONDS)
        connection.request("GET",URL.removeprefix("https://www.sec.gov"),headers=context.headers)
        response=connection.getresponse();pairs=tuple(response.getheaders())
        _need(type(response.status) is int,"http_status_refused")
        if response.status!=200:return directory.SecHttpResult(response.status,pairs,b"")
        mode,size=old._framing(pairs,MAX_COMPRESSED)
        _need(mode!="chunked" or response.chunked is True,"http_chunk_decoder_refused")
        raw=response.read(size if mode=="length" else MAX_COMPRESSED+1)
        _need(mode!="chunked" or response.read(1)==b"" and response.isclosed(),"http_chunk_terminal_refused")
        result=directory.SecHttpResult(200,pairs,raw);old._strict_response(result)
        _need(time.monotonic()-begun<=TRANSPORT_SECONDS,"absolute_transport_deadline")
        return result
    except _Deadline:raise CompactCaptureError("absolute_transport_deadline") from None
    finally:
        active=sys.exc_info()[0] is not None;failed=False
        for cleanup in (lambda:signal.setitimer(signal.ITIMER_REAL,0),lambda:signal.signal(signal.SIGALRM,previous_handler),
                *((connection.close,) if connection else ())):
            try:cleanup()
            except BaseException:failed=True
        if failed and not active:raise CompactCaptureError("transport_cleanup_refused")


def _complete(identity,fixture,plan,rsha,result,rpin):
    return {"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(_raw(registration())),"input_preflight_sha256":_sha(_raw(plan)),
        "reservation_sha256":rsha,"result_sha256":rpin,"result":result,"authority":_authority()}


def _validate_result(value,rsha,csha,ssha):
    keys={"schema","reservation_sha256","claim_sha256","start_sha256","raw_transport_invocations","remote_request_count_measured",
        "http_status","disposition","compact_retained","headers_sha256","inspection_sha256","selected_objects","selected_physical_bytes",
        "inspection_refusal","transport_refusal","carrier_hashed_or_retained","individual_parent_requests","contact_value_stored_or_hashed","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/result"
        and (value["reservation_sha256"],value["claim_sha256"],value["start_sha256"])==(rsha,csha,ssha)
        and type(value["raw_transport_invocations"]) is int and value["raw_transport_invocations"]==1
        and value["remote_request_count_measured"] is False and value["carrier_hashed_or_retained"] is False
        and value["contact_value_stored_or_hashed"] is False and type(value["individual_parent_requests"]) is int
        and value["individual_parent_requests"]==0 and type(value["compact_retained"]) is bool
        and _raw(value["authority"])==_raw(_authority()),"readback_crosslinks_refused")
    status=value["http_status"]
    _need(status is None or type(status) is int and 100<=status<=599,"readback_crosslinks_refused")
    if value["compact_retained"]:
        _need(status==200 and value["disposition"]=="compact_identity_unvalidated_candidates_only"
            and value["inspection_refusal"] is value["transport_refusal"] is None
            and type(value["selected_objects"]) is int and 0<=value["selected_objects"]<=4096
            and type(value["selected_physical_bytes"]) is int and 0<=value["selected_physical_bytes"]<=MAX_PHYSICAL,"readback_crosslinks_refused")
        for k in ("headers_sha256","inspection_sha256"):_digest(value[k])
    else:
        _need(all(value[k] is None for k in ("headers_sha256","inspection_sha256","selected_objects","selected_physical_bytes")),"readback_crosslinks_refused")
        if status is None:
            _need(value["disposition"]=="ambiguous_transport_failure_no_retry" and value["inspection_refusal"] is None
                and value["transport_refusal"] in ({"phase":"transport","code":code} for code in
                    ("absolute_transport_deadline","idle_timeout","ambiguous_transport")),"readback_crosslinks_refused")
        elif status!=200:
            _need(value["disposition"]=="non200_body_unread_no_retry" and value["inspection_refusal"] is value["transport_refusal"] is None,"readback_crosslinks_refused")
        else:
            _need(value["disposition"]=="compact_privacy_integrity_or_resource_refused_no_retry"
                and value["transport_refusal"] is None and type(value["inspection_refusal"]) is dict
                and value["inspection_refusal"]=={"phase":"inspection","code":"finite_compact_inspection_refused"},"readback_crosslinks_refused")
    return value


def _run(*,root,identity,plan,contact,transport,fixture,guard,inputs,activation=None,inspector=None):
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(callable(transport) and transport is not _transport and contact not in {contact_io._stdin_contact,contact_io._getpass_contact},"invented_callbacks_required")
    else:
        _need(root==LANE_ROOT and transport is _transport and contact is contact_io._stdin_contact
            and inspector is None and type(inputs) is _Inputs,"fixed_actual_front_required")
        _activated(activation,identity)
    forms=_forms(identity,fixture,plan);guard()
    if not fixture:inputs.check(full=True);_need(inputs.metadata==plan["inputs"],"inputs_changed")
    phase="capacity";folders=[];lock=None;locked=False;fresh=None
    try:
        _preoutput_capacity(root);phase="namespace"
        try:fresh=custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        except custody.ArchiveAssessmentRunnerError as error:
            if error.args==("output_cannot_resume_or_overwrite",):raise CompactCaptureError("fresh_namespace_already_exists") from None
            raise
        top=old._Output(root.joinpath(*ARTIFACT_PARTS));folders.append(top)
        claims=old._Output(top.path/"claims",create=True);folders.append(claims)
        runs=old._Output(top.path/"runs",create=True);folders.append(runs)
        objects=old._Output(top.path/"objects",create=True);folders.append(objects)
        top.publish("scope.lock",LOCK_BYTES);lock=os.open("scope.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;version=old._version(os.fstat(lock));_capacity(top.fd)
        os.mkdir(AUDIT_ID,0o700,dir_fd=runs.fd);os.fsync(runs.fd);run=old._Output(runs.path/AUDIT_ID);folders.append(run)
        names=set();claimnames=set();objectnames=set()
        def check():
            guard();fresh.recheck()
            if not fixture:inputs.check();_need(inputs.metadata==plan["inputs"],"inputs_changed")
            for folder in folders:folder.check()
            _need(version==old._version(os.fstat(lock))==old._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"output_lock_changed")
            _need(set(os.listdir(top.fd))=={"scope.lock","claims","runs","objects"} and set(os.listdir(runs.fd))=={AUDIT_ID}
                and set(os.listdir(run.fd))==names and set(os.listdir(claims.fd))==claimnames
                and set(os.listdir(objects.fd))==objectnames,"output_inventory_changed")
        def publish(name,value):
            pin=run.publish(name,_raw(value));names.add(name);check();return pin
        phase="reservation";rsha=publish("reservation.json",forms["reservation.json"]);publish("input-preflight.json",plan)
        phase="contact";private=privacy._contact(contact(),observed=not fixture);old._contact_needles(private)
        publish("contact-validated.json",{"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
        phase="claim";csha=claims.publish(_claim_name(),_raw(forms["claim.json"]));claimnames.add(_claim_name());check()
        phase="start";ssha=publish("request-start.json",forms["request-start.json"])
        def prove():
            check();_need(claims.read(_claim_name())==_raw(forms["claim.json"])
                and run.read("request-start.json")==_raw(forms["request-start.json"]),"dispatch_context_refused")
        headers={"User-Agent":"InsiderBuyingResearch-CompactNC/1.0 ("+private+")","Accept":"application/gzip","Accept-Encoding":"identity","Connection":"close"}
        phase="transport";response=None;context=None;transport_refusal=None
        try:
            if fixture:prove();response=transport(URL,headers,MAX_COMPRESSED)
            else:context=_Dispatch(_TOKEN,activation,identity,guard,prove,headers);response=_transport(context)
        except Exception as error:
            if not fixture:_need(context is not None and context.attempted,"transport_front_refused")
            code="absolute_transport_deadline" if type(error) is CompactCaptureError and error.args==("absolute_transport_deadline",) else "idle_timeout" if isinstance(error,TimeoutError) else "ambiguous_transport"
            transport_refusal={"phase":"transport","code":code}
        check();status=None;inspection=None;retained=False;refusal=None;hsha=isha=count=size=None
        disposition="ambiguous_transport_failure_no_retry"
        if response is not None:
            _need(type(response) is directory.SecHttpResult and type(response.status) is int and 100<=response.status<=599,"response_metadata_refused")
            status=response.status;disposition="non200_body_unread_no_retry"
            if status==200:
                phase="inspection"
                try:
                    raw=old._strict_response(response);pairs=_headers(response.headers)
                    if fixture:inspection=(inspector or _inspect)(raw,pairs,private,inputs,fixture=True)
                    else:inspection=_child("inspect",identity,_raw({"contact":private,"headers":pairs,"bytes":len(raw),"plan":plan})+b"\n"+raw)
                    _validate_inspection_plan(inspection,plan,fixture=fixture)
                    _need(inspection["source_receipt_sha256"]==plan["inputs"]["source_receipt_sha256"]
                        and inspection["headers_sha256"]==_sha(_raw(pairs)),"compact_result_refused")
                except Exception:
                    refusal={"phase":"inspection","code":"finite_compact_inspection_refused"}
                    disposition="compact_privacy_integrity_or_resource_refused_no_retry"
                else:
                    phase="publication";binary=_decode_objects(inspection["binary_objects"])
                    for pin,span in binary.items():
                        name=pin+".bin";_need(objects.publish(name,span,cap=8*1024**2+1023)==pin,"compact_result_refused")
                        objectnames.add(name);check()
                    manifest={k:v for k,v in inspection.items() if k!="binary_objects"}
                    _validate_wire(manifest,fixture=fixture,with_binary=False)
                    hsha=_sha(_raw(pairs));publish("response-headers.json",{"headers":pairs})
                    isha=publish("inspection.json",manifest);retained=True
                    count=len(binary);size=sum(len(v) for v in binary.values())
                    disposition="compact_identity_unvalidated_candidates_only"
        result={"schema":SCHEMA+"/result","reservation_sha256":rsha,"claim_sha256":csha,"start_sha256":ssha,
            "raw_transport_invocations":1,"remote_request_count_measured":False,"http_status":status,"disposition":disposition,
            "compact_retained":retained,"headers_sha256":hsha,"inspection_sha256":isha,"selected_objects":count,"selected_physical_bytes":size,
            "inspection_refusal":refusal,"transport_refusal":transport_refusal,"carrier_hashed_or_retained":False,
            "individual_parent_requests":0,"contact_value_stored_or_hashed":False,"authority":_authority()}
        phase="complete";_validate_result(result,rsha,csha,ssha);rpin=publish("request-result.json",result)
        report=publish("complete.json",_complete(identity,fixture,plan,rsha,result,rpin));phase="final";check()
        if not fixture:inputs.check(full=True)
        return {"schema":SCHEMA+"/public","audit_id":AUDIT_ID,"complete_sha256":report,"result":result,"authority":_authority()}
    except Exception as error:raise _classified(phase,error) from None
    finally:
        primary=sys.exc_info()[0] is not None
        try:publication._close_all(folders,fresh,lock,locked)
        except Exception as error:
            if not primary:raise _classified("cleanup",error) from None


def _invented(*,root,transport,inputs,contact=lambda:"invented@unit.test",guard=lambda:None,inspector=None):
    sources={SELF_PATH:"a"*64,TEST_PATH:"b"*64,previous.SELF_PATH:"c"*64,previous.TEST_PATH:"d"*64};identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    plan={"schema":SCHEMA+"/input-preflight","execution_identity":identity,"inputs":inputs.metadata,"fixture_only":True}
    return _run(root=Path(root),identity=identity,plan=plan,contact=contact,transport=transport,fixture=True,guard=guard,inputs=inputs,inspector=inspector)


def _verify_files(root,pin,private,*,fixture,current_identity=None):
    if fixture:publication._fixture_root(root);publication._native_fixture_denial()
    else:previous._isolated();source_runner._prove_isolation();_current(current_identity);_need(root==LANE_ROOT,"fixed_actual_front_required")
    _digest(pin);folders=[];lock=None;inputs=None
    try:
        if not fixture:inputs=_Inputs(root)
        def opened(path):
            value=directory._ReadbackDirectory(path);folders.append(value);return value
        top=opened(root.joinpath(*ARTIFACT_PARTS));claims=opened(top.path/"claims");runs=opened(top.path/"runs")
        objects=opened(top.path/"objects");run=opened(runs.path/AUDIT_ID)
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);version=privacy._file_version(os.fstat(lock))
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(top.read("scope.lock")==LOCK_BYTES and set(os.listdir(top.fd))=={"scope.lock","claims","runs","objects"}
            and set(os.listdir(runs.fd))=={AUDIT_ID} and set(os.listdir(claims.fd))=={_claim_name()},"readback_crosslinks_refused")
        craw=run.read("complete.json",cap=MAX_CONTROL);_need(_sha(craw)==pin,"readback_pin_refused")
        complete=_control(craw);identity=complete["execution_identity"];plan=_control(run.read("input-preflight.json",cap=MAX_CONTROL))
        previous._check_identity(identity,root)
        if inputs:_need(inputs.metadata==plan["inputs"],"inputs_changed")
        forms=_forms(identity,fixture,plan);rsha=_sha(_raw(forms["reservation.json"]))
        result_raw=run.read("request-result.json",cap=MAX_CONTROL);result=_control(result_raw)
        _validate_result(result,rsha,_sha(_raw(forms["claim.json"])),_sha(_raw(forms["request-start.json"])))
        _need(plan["execution_identity"]==identity and run.read("reservation.json",cap=MAX_CONTROL)==_raw(forms["reservation.json"])
            and claims.read(_claim_name())==_raw(forms["claim.json"]) and run.read("request-start.json")==_raw(forms["request-start.json"])
            and run.read("contact-validated.json")==_raw({"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
            and craw==_raw(_complete(identity,fixture,plan,rsha,result,_sha(result_raw))),"readback_crosslinks_refused")
        expected={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json","complete.json"}
        objectnames=set()
        if result["compact_retained"]:
            expected|={"inspection.json","response-headers.json"}
            # These strict OLD reads deliberately avoid hashes until fresh
            # current-contact screening; source hold still binds all versions.
            run._versions();hraw=run.tree.read("response-headers.json",cap=MAX_CONTROL);run._versions()
            headers=_control(hraw);_need(set(headers)=={"headers"},"readback_crosslinks_refused")
            pairs=_headers(headers["headers"]);_header_screen(pairs,private)
            _need(run.read("response-headers.json",cap=MAX_CONTROL)==hraw and _sha(_raw(pairs))==result["headers_sha256"],"readback_crosslinks_refused")
            mraw=run.read("inspection.json",cap=MAX_METADATA);manifest=_control(mraw)
            _validate_inspection_plan(manifest,plan,fixture=fixture)
            _need(_sha(mraw)==result["inspection_sha256"] and manifest["source_receipt_sha256"]==plan["inputs"]["source_receipt_sha256"]
                and manifest["headers_sha256"]==result["headers_sha256"],"readback_crosslinks_refused")
            candidates=[]
            for item,descriptor in zip(manifest["selected"],manifest["compact"]["candidates"],strict=True):
                name=descriptor["physical_sha256"]+".bin";objectnames.add(name)
                objects._versions();span=objects.tree.read(name,cap=8*1024**2+1023);objects._versions();_screen(span,private)
                route=compact._hint(span[:512]);_need(route is not None,"readback_crosslinks_refused")
                candidates.append(compact.CompactCandidate(route,span,_raw(descriptor)))
                _need(objects.read(name,cap=8*1024**2+1023)==span,"readback_crosslinks_refused")
                if inputs:_need(route in inputs.rows and item["source_binding"]==_source_binding(inputs.rows[route]),"readback_crosslinks_refused")
            if fixture:
                source=plan["inputs"]["invented_scope"]
                roster_set,eligible,prior=map(frozenset,(source["roster"],source["eligible"],source["prior"]))
            else:roster_set,eligible,prior=inputs.roster_set,inputs.eligible,frozenset(inputs.prior)
            verified=compact.verify_retained_candidates(tuple(candidates),expected_manifest=manifest["compact"],roster_accessions=roster_set,
                eligible_accessions=eligible,consumed_accessions=prior,privacy_contact=private,fixture_only=fixture)
            _need(len(candidates)==result["selected_objects"] and sum(len(c.physical_bytes) for c in candidates)==result["selected_physical_bytes"],"readback_crosslinks_refused")
        else:verified=None
        _need(set(os.listdir(run.fd))==expected and set(os.listdir(objects.fd))==objectnames,"readback_crosslinks_refused")
        for folder in folders:folder.check()
        if inputs:inputs.check(full=True);_current(current_identity)
        _need(version==privacy._file_version(os.fstat(lock))==privacy._file_version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed")
        return {"schema":SCHEMA+"/readback","complete_sha256":pin,"result":result,"producer_execution_identity":identity,
            "original_input_plan":plan,"retained_subset_replay":verified,"discarded_carrier_replayed":False,
            "original_current_contact_equality_attested":False,"original_contact_screen_replayed":False,"new_provider_requests":0,"authority":_authority()}
    finally:publication._close_all([*folders,*([inputs] if inputs else [])],None,lock,lock is not None)


def _parent_plan_proofs(plan):
    previous._parent_plan_proofs({"inputs":plan["inputs"]["old_listing_and_consumption"],"consumption_proof":plan["consumption_proof"]})


def run_actual(*,expected_head):
    identity=_identity(expected_head);plan=_child("preflight",identity);_parent_plan_proofs(plan)
    _need(plan.get("execution_identity")==identity and plan.get("schema")==SCHEMA+"/input-preflight","native_preflight_refused")
    _forms(identity,False,plan)
    held=None;activation=None
    def guard():_need(_identity(expected_head)==identity,"source_changed")
    try:
        held=_Inputs(LANE_ROOT,source_receipt=plan["inputs"]["source_receipt"]);_need(held.metadata==plan["inputs"],"inputs_changed")
        activation=_Activation(identity,guard,held);_ACTIVATIONS[activation]=(_raw(identity),id(guard),id(held))
        return _run(root=LANE_ROOT,identity=identity,plan=plan,contact=contact_io._stdin_contact,transport=_transport,fixture=False,
            guard=guard,inputs=held,activation=activation)
    finally:
        if activation:_ACTIVATIONS.pop(activation,None)
        source_runner.selector._close_all((held,),phase="compact_actual_cleanup")


def verify_actual(*,expected_head,expected_report_sha256):
    identity=_identity(expected_head);plan=_child("preflight",identity);_parent_plan_proofs(plan)
    private=privacy._contact(contact_io._stdin_contact(),observed=True)
    value=_child("readback",identity,_raw({"contact":private,"report_sha256":_digest(expected_report_sha256)})+b"\n")
    previous._source_git(value["producer_execution_identity"]);_parent_plan_proofs(value["original_input_plan"])
    normalized={**value["original_input_plan"],"execution_identity":identity}
    _need(normalized==plan,"inputs_changed")
    _need(_identity(expected_head)==identity,"source_changed")
    return {k:v for k,v in value.items() if k!="original_input_plan"}


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise CompactCaptureError("private_arguments_refused")


def main(argv=None):
    saved=contact_io._protect_stdin_echo();phase="arguments"
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--contact-stdin",action="store_true")
        parser.add_argument("--verify-report-sha256");args=parser.parse_args(argv)
        _need(args.contact_stdin,"private_contact_mode_refused");phase="source"
        value=verify_actual(expected_head=args.expected_head,expected_report_sha256=args.verify_report_sha256) if args.verify_report_sha256 else run_actual(expected_head=args.expected_head)
        print(_raw(value).decode())
        return 0 if args.verify_report_sha256 or value["result"]["compact_retained"] else 2
    except Exception as error:
        value=_classified(getattr(error,"phase",phase),error)
        print(_raw({"disposition":"compact_capture_refused","phase":value.phase,"code":value.args[0]}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
