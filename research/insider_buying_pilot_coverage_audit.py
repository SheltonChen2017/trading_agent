"""Read-only retained-metadata coverage for a separate 2021-2025 pilot.

This audit neither parses source financial JSON nor joins events and outcomes.
It stream-hashes retained response/metadata bytes, validates operational seals,
and summarizes the accepted selector's already-observed source counts. A
successful historical selector terminal is required; equal candidate bytes
from the failed predecessor do not suffice. No artifact writer or provider
entry point is provided. All evidence/readiness authorities remain false.
"""
from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_affected_quarter_selector_verification_v2 as selector
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS
from research.insider_buying_sharadar_reference_qualification import _outside_lane


SELF_PATH = "research/insider_buying_pilot_coverage_audit.py"
SCHEMA = "insider-retained-pilot-coverage-audit-2021-2025-v1"
LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
EARNINGS_BASE = ("artifacts", "insider_buying", "eodhd_earnings_continuation5")
EARNINGS_ID = "ib-eodhd-campaign-continuation5-202003-202607-20261014-once"
EARNINGS_PARTS = (*EARNINGS_BASE, "campaigns", EARNINGS_ID)
SELECTOR_PARTS = ("artifacts", "insider_buying", "affected_quarter_selector_verification_v2", selector.AUDIT_ID)
OBSERVER_PARTS = ("artifacts", "insider_buying", "selector_trusted_publisher_v3", "ib-selector-trusted-publisher-v3-20261021-once")
MAX_CONTROL = 1024 * 1024
MAX_METADATA = 256 * 1024 * 1024
MAX_BODY = 16 * 1024 * 1024
MAX_TOTAL_STREAM_BYTES = 8 * 1024**3
EMPTY_CACHE_PREFIX = "/var/empty/insider-pilot-coverage-no-bytecode"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_COUNTS = ("sample_rows", "metadata_accepted_rows", "quarantined_rows", "timing_unknown_rows",
           "unknown_status_rows", "reported_rows", "duplicate_fiscal_period_rows", "metadata_conflicting_fiscal_periods")
_RECEIPT_KEYS = frozenset((*FALSE_FLAGS, *_COUNTS, "all_rows_retained_in_source_order", "body_sha256", "body_size_bytes",
    "calendar_window_observed", "disposition", "duplicate_or_conflicting_rows_deduplicated", "empty_result_is_coverage_evidence",
    "financial_values_evaluated_or_projected", "http_response_observed", "http_status", "metadata_sha256",
    "nonessential_currency_projected_or_inferred", "response_body_retained", "transport_invocation_count",
    "untrusted_error_body_hashed_or_retained"))
_MANIFEST_KEYS = frozenset((*FALSE_FLAGS, "campaign_id", "credential_or_path_or_hash_retained", "disk_preflight",
    "financial_values_evaluated_or_projected", "fixture_only", "identity", "local_read_reattachment_is_provider_retry",
    "maximum_attempts_per_window", "maximum_body_bytes_per_window", "maximum_control_bytes_per_leaf",
    "maximum_local_custody_read_reattachments", "maximum_metadata_bytes_per_window", "maximum_rows_per_window",
    "minimum_start_interval_seconds", "owner_acknowledged_rotated_token", "owner_direction", "previous_campaign_anchor",
    "profile", "registered_at_utc", "retry_resume_permitted", "rotation_independently_verified", "schema",
    "timeout_seconds", "window_scope_sha256", "windows"))
_COMPLETE_KEYS = frozenset((*FALSE_FLAGS, "all_registered_windows_observed", "campaign_id", "completed_at_utc",
    "credential_or_path_or_hash_retained", "fixture_only", "identity",
    "looks_jobs_backtests", "manifest_sha256", "metadata_accepted_rows", "observed_windows", "planned_windows",
    "previous_campaign_anchor", "quarantined_rows", "refused_or_ambiguous_windows", "schema", "source_rows",
    "transport_invocation_count", "unattempted_windows", "window_results"))
_SELECTOR_COMPLETE_KEYS = frozenset(("schema", "audit_id", "fixture_only", "observed_at_utc", "observer_clock_kind",
    "current_execution_identity", "frozen_sources", "intake_context", "reservation_sha256", "selection_sha256",
    "selection_bytes", "worker_result_sha256", "source_execution", "counts", "source_only_bootstrap_sha256",
    "full_input_rederivations", "effective_process_tree_network_denial", "effective_process_fork_denial",
    "effective_all_write_denial", "authority", "operation_registration", "operation_registration_sha256"))
_TERMINAL_KEYS = frozenset(("audit_id", "elapsed_seconds", "exit_code", "schema", "stderr_bytes", "stderr_sha256",
    "stdout_bytes", "stdout_sha256", "success_summary", "terminal_success_observed", "timed_out"))


class PilotCoverageError(ValueError):
    """Fixed codes only; supplied artifact/source/exception text is private."""


def _need(value, code):
    if not value:raise PilotCoverageError(code)


def _raw(value):return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "external_hash_required")
    return value


def _json(raw):
    def pairs(items):
        result = {}
        for key,value in items:
            _need(key not in result, "duplicate_control_key_refused");result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _need(False, "nonfinite_control_refused"))
        _need(type(value) is dict and _raw(value) == raw, "canonical_control_required")
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError):
        raise PilotCoverageError("control_json_refused") from None


def _zero_authority(value):
    _need(type(value) is dict and value and all(item is False or type(item) is int and item == 0 for item in value.values()),
          "source_authority_not_false")


def _false_flags(value):
    _need(all(value.get(name) is False for name in FALSE_FLAGS), "source_readiness_not_false")


def _windows():
    return tuple((date(y,m,1).isoformat(), date(y,m,calendar.monthrange(y,m)[1]).isoformat())
                 for y in range(2020,2027) for m in range(1,13) if (2020,3) <= (y,m) <= (2026,7))


@dataclass(frozen=True, slots=True)
class Anchors:
    earnings_manifest: str
    earnings_complete: str
    selection: str
    selector_complete: str
    observer_final: str


ACTUAL_ANCHORS = Anchors(
    "6443c8caaac2b826e6759c4e1a9db6b209e927b9bc13e2f82ed15bdac968ddec",
    "953e0071edf449b594a6e2cd20b7588a6b8dc38fb97bc9fbcb5f1f0aae2c0e24",
    "d1dd4e093d5505fac6373562bb24198c7ad6fc61ef7745912a40bff84528aaef",
    "da3780102a1b57157d4df4021630ded31cb78730d1765826111b960485a95b42",
    "c1b2cd8c1833ef11763ceefee15b83c5ac7af47d26ad7a1296ed5af8e04e2441")


def _version(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


class _Held:
    def __init__(self,root):
        self.root,self.chains,self.pins,self.locks,self.inventories = root,{}, {},[],{}
        self.streamed = 0

    def directory(self,parts,names=None):
        if parts not in self.chains:self.chains[parts] = custody._Chain(self.root,parts)
        chain = self.chains[parts];chain.recheck()
        _need(os.fstat(chain.fd).st_uid == os.geteuid(), "input_directory_owner_refused")
        if names is not None:
            _need(set(os.listdir(chain.fd)) == set(names), "input_inventory_refused")
            self.inventories[parts] = set(names)
        return chain

    def leaf(self,parts,name,cap,expected=None,*,collect=True):
        chain = self.directory(parts);before = os.stat(name,dir_fd=chain.fd,follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid()
              and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= cap,"input_leaf_custody_refused")
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        try:
            _need(_version(os.fstat(fd)) == _version(before),"input_leaf_substituted")
            digest,count,chunks = hashlib.sha256(),0,[]
            while chunk := os.read(fd,65536):
                count += len(chunk);self.streamed += len(chunk)
                _need(count <= before.st_size and self.streamed <= MAX_TOTAL_STREAM_BYTES,"input_stream_bound_refused")
                digest.update(chunk)
                if collect:chunks.append(chunk)
            _need(count == before.st_size and _version(os.fstat(fd)) == _version(before)
                  == _version(os.stat(name,dir_fd=chain.fd,follow_symlinks=False)),"input_leaf_changed")
        finally:os.close(fd)
        observed = digest.hexdigest()
        _need(expected is None or observed == _digest(expected),"input_hash_refused")
        key = (parts,name);pin = (_version(before),observed,cap)
        _need(key not in self.pins or self.pins[key] == pin,"held_input_changed")
        self.pins[key] = pin
        return b"".join(chunks) if collect else observed

    def lock(self,parts):
        chain = self.directory(parts);name = "campaign.lock"
        before = os.stat(name,dir_fd=chain.fd,follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_size == 0 and before.st_uid == os.geteuid()
              and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600,"campaign_lock_refused")
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        try:
            _need(_version(os.fstat(fd)) == _version(before),"campaign_lock_refused")
            fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BaseException:os.close(fd);raise
        self.locks.append((chain,fd,_version(before)))

    def recheck(self):
        for parts,names in self.inventories.items():self.directory(parts,names)
        for (parts,name),(version,digest,cap) in tuple(self.pins.items()):
            _need(_version(os.stat(name,dir_fd=self.directory(parts).fd,follow_symlinks=False)) == version,"held_input_version_changed")
            self.leaf(parts,name,cap,digest,collect=False)
        for chain,fd,version in self.locks:
            _need(_version(os.fstat(fd)) == version == _version(os.stat("campaign.lock",dir_fd=chain.fd,follow_symlinks=False)),"campaign_lock_changed")

    def close(self):
        primary,failed = sys.exc_info()[0] is not None,False
        for _,fd,_ in self.locks:
            try:os.close(fd)
            except BaseException:failed = True
        self.locks = []
        for chain in reversed(tuple(self.chains.values())):
            try:chain.close()
            except BaseException:failed = True
        self.chains = {}
        if failed and not primary:raise PilotCoverageError("input_cleanup_refused") from None


def _receipt(value):
    _need(type(value) is dict and set(value) == _RECEIPT_KEYS,"receipt_schema_refused")
    _false_flags(value)
    for key in _COUNTS:_need(type(value[key]) is int and 0 <= value[key] <= 200000,"typed_receipt_count_refused")
    count = value["sample_rows"]
    _need(value["metadata_accepted_rows"]+value["quarantined_rows"] == count
          and all(value[key] <= count for key in _COUNTS) and value["timing_unknown_rows"] <= value["quarantined_rows"],"receipt_partition_refused")
    _need(type(value["http_status"]) is int and value["http_status"] == 200
          and type(value["transport_invocation_count"]) is int and value["transport_invocation_count"] == 1
          and type(value["body_size_bytes"]) is int and 0 < value["body_size_bytes"] <= MAX_BODY
          and value["disposition"] == "calendar_window_observed","receipt_observation_refused")
    for key in ("calendar_window_observed","response_body_retained","http_response_observed","all_rows_retained_in_source_order"):
        _need(value[key] is True,"receipt_observation_refused")
    for key in ("duplicate_or_conflicting_rows_deduplicated","empty_result_is_coverage_evidence",
                "financial_values_evaluated_or_projected","nonessential_currency_projected_or_inferred","untrusted_error_body_hashed_or_retained"):
        _need(value[key] is False,"receipt_exclusion_refused")
    _digest(value["body_sha256"]);_digest(value["metadata_sha256"])
    return {key:value[key] for key in _COUNTS}


def _earnings(held,anchors,fixture):
    held.directory(EARNINGS_BASE,{"campaigns","scopes","campaign.lock"});held.lock(EARNINGS_BASE)
    held.directory((*EARNINGS_BASE,"campaigns"),{EARNINGS_ID})
    manifest_raw = held.leaf(EARNINGS_PARTS,"manifest.json",MAX_CONTROL,anchors.earnings_manifest)
    complete_raw = held.leaf(EARNINGS_PARTS,"complete.json",MAX_CONTROL,anchors.earnings_complete)
    manifest,complete = _json(manifest_raw),_json(complete_raw)
    _need(set(manifest) == _MANIFEST_KEYS and set(complete) == _COMPLETE_KEYS,"campaign_schema_refused")
    _false_flags(manifest);_false_flags(complete)
    _need(manifest["schema"] == complete["schema"] == "insider-eodhd-date-window-earnings-continuation-v5"
          and manifest["campaign_id"] == complete["campaign_id"] == EARNINGS_ID
          and manifest["fixture_only"] is fixture and complete["fixture_only"] is fixture
          and manifest["identity"] == complete["identity"]
          and complete["manifest_sha256"] == anchors.earnings_manifest
          and manifest["profile"] == "eodhd-calendar-unattempted-only-20200301-20260731-v5"
          and manifest["windows"] == [list(x) for x in _windows()],"campaign_profile_refused")
    integer_controls = {"maximum_attempts_per_window":1,"maximum_local_custody_read_reattachments":3,
        "maximum_body_bytes_per_window":MAX_BODY,"maximum_rows_per_window":200000,
        "maximum_metadata_bytes_per_window":MAX_METADATA,"maximum_control_bytes_per_leaf":MAX_CONTROL,"timeout_seconds":15}
    _need(all(type(manifest[key]) is int and manifest[key] == expected for key,expected in integer_controls.items())
          and type(manifest["minimum_start_interval_seconds"]) in {int,float} and manifest["minimum_start_interval_seconds"] == 1.0
          and manifest["owner_acknowledged_rotated_token"] is True
          and all(manifest[key] is False for key in ("retry_resume_permitted","local_read_reattachment_is_provider_retry",
              "financial_values_evaluated_or_projected","credential_or_path_or_hash_retained","rotation_independently_verified"))
          and complete["credential_or_path_or_hash_retained"] is False
          and complete["previous_campaign_anchor"] == manifest["previous_campaign_anchor"]
          and manifest["window_scope_sha256"] == [_sha(_raw(custody._scope(x))) for x in _windows()],"campaign_operational_controls_refused")
    _need(type(complete["planned_windows"]) is int and complete["planned_windows"] == 77
          and type(complete["observed_windows"]) is int and complete["observed_windows"] == 77
          and type(complete["transport_invocation_count"]) is int and complete["transport_invocation_count"] == 77
          and complete["all_registered_windows_observed"] is True and complete["unattempted_windows"] == []
          and type(complete["refused_or_ambiguous_windows"]) is int and complete["refused_or_ambiguous_windows"] == 0
          and complete["looks_jobs_backtests"] == [0,0,0]
          and all(type(x) is int for x in complete["looks_jobs_backtests"]),"campaign_completion_refused")
    results = complete["window_results"]
    _need(type(results) is list and len(results) == 77,"complete_window_roster_required")
    scopes,names,selected,all_counts = set(),{"manifest.json","complete.json"},[],dict.fromkeys(_COUNTS,0)
    for index,(window,result) in enumerate(zip(_windows(),results,strict=True)):
        _need(type(result) is dict and set(result) == {"index","window","receipt","complete_sha256"}
              and type(result["index"]) is int and result["index"] == index and result["window"] == list(window),"ordered_window_refused")
        prefix = f"window-{index:04d}";counts = _receipt(result["receipt"])
        child_raw = held.leaf(EARNINGS_PARTS,prefix+"-complete.json",MAX_CONTROL,result["complete_sha256"]);child = _json(child_raw)
        _need(set(child) == {"schema","window","index","completed_at_utc","manifest_sha256","started_sha256","scope_reservation_sha256","receipt"}
              and child["schema"] == manifest["schema"] and child["window"] == list(window)
              and type(child["index"]) is int and child["index"] == index
              and child["manifest_sha256"] == anchors.earnings_manifest and child["receipt"] == result["receipt"],"child_completion_binding_refused")
        start = _json(held.leaf(EARNINGS_PARTS,prefix+"-started.json",MAX_CONTROL,child["started_sha256"]))
        _need(start == {"schema":manifest["schema"],"window":list(window),"index":index,
            "started_at_utc":start.get("started_at_utc"),"manifest_sha256":anchors.earnings_manifest,
            "scope_reservation_sha256":child["scope_reservation_sha256"],"maximum_attempts":1}
            and type(start["maximum_attempts"]) is int,"started_journal_refused")
        scope_value = custody._scope(window);scope_name = _sha(_raw(scope_value))+".json";scopes.add(scope_name)
        scope = _json(held.leaf((*EARNINGS_BASE,"scopes"),scope_name,MAX_CONTROL,child["scope_reservation_sha256"]))
        _need(scope == {"schema":manifest["schema"],"scope":scope_value,"campaign_id":EARNINGS_ID,
            "reserved_at_utc":scope.get("reserved_at_utc"),"maximum_attempts":1} and type(scope["maximum_attempts"]) is int,"scope_journal_refused")
        utc = custody.assessment._utc
        _need(utc(manifest["registered_at_utc"]) <= utc(scope["reserved_at_utc"]) <= utc(start["started_at_utc"])
              <= utc(child["completed_at_utc"]) <= utc(complete["completed_at_utc"]),"source_clock_order_refused")
        names.update(prefix+suffix for suffix in ("-started.json","-complete.json","-response.json","-metadata.json"))
        for key in _COUNTS:all_counts[key] += counts[key]
        if "2020-10-01" <= window[0] <= "2026-04-01":
            body = result["receipt"]
            held.leaf(EARNINGS_PARTS,prefix+"-response.json",MAX_BODY,body["body_sha256"],collect=False)
            pin = held.pins[(EARNINGS_PARTS,prefix+"-response.json")]
            _need(pin[0][5] == body["body_size_bytes"],"response_byte_count_refused")
            held.leaf(EARNINGS_PARTS,prefix+"-metadata.json",MAX_METADATA,body["metadata_sha256"],collect=False)
            selected.append({"window":list(window),"source_window_ordinal":index,"http_status":200,"counts":counts,
                "body_sha256":body["body_sha256"],"metadata_sha256":body["metadata_sha256"],"completion_sha256":result["complete_sha256"]})
    held.directory(EARNINGS_PARTS,names);held.directory((*EARNINGS_BASE,"scopes"),scopes)
    _need(type(complete["source_rows"]) is int and complete["source_rows"] == all_counts["sample_rows"]
          and type(complete["metadata_accepted_rows"]) is int and complete["metadata_accepted_rows"] == all_counts["metadata_accepted_rows"]
          and type(complete["quarantined_rows"]) is int and complete["quarantined_rows"] == all_counts["quarantined_rows"],"campaign_aggregate_refused")
    _need(len(selected) == 67,"exact_67_buffered_windows_required")
    pilot = [x for x in selected if "2021-01-01" <= x["window"][0] <= "2025-12-01"]
    return {"source_campaign_id":EARNINGS_ID,"source_campaign_manifest_sha256":anchors.earnings_manifest,
        "source_campaign_complete_sha256":anchors.earnings_complete,"source_control_months_verified":77,
        "buffered_months":selected,"pilot_month_count":len(pilot),
        "pilot_counts":{key:sum(x["counts"][key] for x in pilot) for key in _COUNTS},
        "metadata_rows_decoded_here":False,"source_financial_bodies_decoded":False,
        "body_and_metadata_bytes_hash_streamed":True,"producer_receipt_counts_not_recomputed_row_semantics":True}


def _selector(held,anchors):
    held.directory(SELECTOR_PARTS,{"reservation.json","selection.json","complete.json"})
    raw = held.leaf(SELECTOR_PARTS,"selection.json",MAX_CONTROL,anchors.selection)
    complete = _json(held.leaf(SELECTOR_PARTS,"complete.json",MAX_CONTROL,anchors.selector_complete))
    _need(set(complete) == _SELECTOR_COMPLETE_KEYS,"selector_complete_schema_refused")
    held.leaf(SELECTOR_PARTS,"reservation.json",MAX_CONTROL,complete["reservation_sha256"])
    final = _json(held.leaf(OBSERVER_PARTS,"final.json",MAX_CONTROL,anchors.observer_final))
    _need(set(final) == {"schema","audit_id","authority","complete_sha256","execution_head","journal_leaf_sha256",
        "old_failed_v1_promoted_or_rewritten","parent_isolation","preceding_failed_observer_preserved","registration_sha256",
        "selection_sha256","semantic_exit0_observed","semantic_invocations_performed","strict_readback_accepted"},"observer_final_schema_refused")
    _zero_authority(final["authority"]);_zero_authority(complete["authority"])
    _need(final["schema"] == "insider-affected-quarter-selector-trusted-publisher-v3/final"
          and final["audit_id"] == OBSERVER_PARTS[-1] and final["complete_sha256"] == anchors.selector_complete
          and final["selection_sha256"] == anchors.selection and final["semantic_exit0_observed"] is True
          and final["strict_readback_accepted"] is True and final["old_failed_v1_promoted_or_rewritten"] is False
          and final["preceding_failed_observer_preserved"] is True and type(final["semantic_invocations_performed"]) is int
          and final["semantic_invocations_performed"] == 1,"accepted_selector_observer_required")
    journal = final["journal_leaf_sha256"]
    _need(type(journal) is dict and set(journal) == {"reservation.json","readback.json","terminal.json"},"observer_journal_roster_refused")
    held.directory(OBSERVER_PARTS,{*journal,"final.json"})
    leaves = {name:_json(held.leaf(OBSERVER_PARTS,name,MAX_CONTROL,digest)) for name,digest in journal.items()}
    terminal = leaves["terminal.json"]
    _need(set(terminal) == _TERMINAL_KEYS and terminal.get("schema") == "insider-affected-quarter-selector-trusted-publisher-v3/semantic-terminal"
          and terminal.get("audit_id") == OBSERVER_PARTS[-1] and type(terminal.get("exit_code")) is int
          and terminal["exit_code"] == 0 and terminal.get("terminal_success_observed") is True
          and terminal.get("timed_out") is False,"actual_selector_exit0_required")
    _need(type(terminal["elapsed_seconds"]) in {int,float} and 0 <= terminal["elapsed_seconds"] <= 240
          and type(terminal["stderr_bytes"]) is int and terminal["stderr_bytes"] == 0
          and terminal["stderr_sha256"] == _sha(b"") and type(terminal["stdout_bytes"]) is int
          and 0 < terminal["stdout_bytes"] <= MAX_CONTROL,"selector_terminal_resource_refused")
    _digest(terminal["stdout_sha256"])
    summary = terminal.get("success_summary")
    _need(type(summary) is dict and summary.get("complete_sha256") == anchors.selector_complete
          and summary.get("selection_sha256") == anchors.selection,"selector_terminal_binding_refused")
    _need(set(summary) == {"audit_id","authority","complete_sha256","counts","fixture_only","operation_registration_sha256",
              "predecessor_status","selection_sha256"} and summary["audit_id"] == selector.AUDIT_ID
          and summary["fixture_only"] is False and summary["predecessor_status"] == "FAILED_preserved_not_promoted",
          "selector_terminal_summary_refused")
    _zero_authority(summary["authority"])
    _need(complete.get("schema") == selector.SCHEMA+"/complete" and complete.get("audit_id") == selector.AUDIT_ID
          and complete.get("fixture_only") is False and complete.get("selection_sha256") == anchors.selection
          and type(complete.get("selection_bytes")) is int and complete["selection_bytes"] == len(raw)
          and complete.get("full_input_rederivations") == 2 and type(complete["full_input_rederivations"]) is int
          and all(complete.get(key) is True for key in ("effective_process_tree_network_denial","effective_process_fork_denial","effective_all_write_denial")),
          "accepted_selector_completion_required")
    selected = selector._selection_metadata(raw,context={"intake_context":complete["intake_context"]})
    _need(complete["counts"] == selected["counts"] == summary["counts"]
          and final["execution_head"] == complete["current_execution_identity"]["head"],"selector_count_or_execution_binding_refused")
    quarters = [x for x in selected["quarters"] if "2020Q1" <= x["period"] <= "2026Q1"]
    pilot = [x for x in quarters if "2021Q1" <= x["period"] <= "2025Q4"]
    _need(len(quarters) == 25 and len(pilot) == 20,"pilot_quarter_roster_refused")
    keys = ("submission_rows","form4_or_4a_rows","short_cik_rows","short_cik_form4_or_4a_rows",
            "accession_year_mismatch_rows","accession_year_mismatch_form4_or_4a_rows")
    return {"accepted_selection_sha256":anchors.selection,"accepted_complete_sha256":anchors.selector_complete,
        "actual_success_observer_final_sha256":anchors.observer_final,"failed_predecessor_promoted":False,
        "source_capture_window":"2006Q1..2026Q2","audit_quarter_window":"2020Q1..2026Q1",
        "quarters":[{key:x[key] for key in ("period",*keys,"source_form_counts","selected_affected","zip_sha256")} for x in quarters],
        "pilot_quarter_count":20,"pilot_counts":{key:sum(x[key] for x in pilot) for key in keys},
        "pilot_form_counts":{key:sum(x["source_form_counts"][key] for x in pilot) for key in selector.pure.FORMS},
        "pilot_affected_periods":[x["period"] for x in pilot if x["selected_affected"]],
        "raw_zip_or_submission_rows_decoded_here":False,"original_parent_admission_established_here":False}


def _audit(root,anchors,fixture):
    _need(type(anchors) is Anchors,"typed_anchors_required")
    for field in anchors.__dataclass_fields__:_digest(getattr(anchors,field))
    held = _Held(root)
    try:
        earnings = _earnings(held,anchors,fixture);sec = _selector(held,anchors)
        held.recheck()
        return {"schema":SCHEMA,"fixture_only":fixture,"pilot_window":"2021-01-01..2025-12-31",
            "source_warmup_envelope":"2020-01-01..2020-12-31","source_tail_envelope":"2026-01-01..2026-03-31",
            "earnings_envelope":"2020-10-01..2026-04-30","earnings":earnings,"sec":sec,
            "held_input_leaf_sha256":{"/".join((*parts,name)):pin[1] for (parts,name),pin in sorted(held.pins.items())},
            "raw_price_or_return_values_read":False,"signals_joined_to_outcomes":False,"new_provider_requests":0,
            "credential_reads":0,"qc_jobs":0,"backtests":0,"research_looks":0,
            "source_coverage_is_not_identity_or_actual_release_completeness":True,
            "calendar_session_buffer_sufficiency_verified":False,**{key:False for key in FALSE_FLAGS}}
    except PilotCoverageError:raise
    except Exception:raise PilotCoverageError("retained_metadata_audit_refused") from None
    finally:held.close()


def audit_fixture(root,anchors):
    _need(isinstance(root,Path) and root.is_absolute() and root.resolve() == root and _outside_lane(root),"invented_outside_lane_root_required")
    custody._effective_denial(require_fork=False)
    return _audit(root,anchors,True)


def _worker(identity):
    _need(sys.flags.isolated == 1 and sys.flags.no_user_site == 1 and sys.flags.no_site == 1
          and sys.flags.dont_write_bytecode == 1 and sys.pycache_prefix == EMPTY_CACHE_PREFIX,"isolated_worker_required")
    _need(type(identity) is dict and set(identity) == {"root","branch","head","clean","source_sha256","source_inventory_sha256"}
          and identity.get("root") == str(LANE_ROOT) and identity.get("branch") == LANE_BRANCH
          and identity.get("clean") is True and type(identity.get("head")) is str and _HEAD.fullmatch(identity["head"]),"parent_identity_required")
    sources = identity["source_sha256"]
    _need(type(sources) is dict and SELF_PATH in sources and 1 <= len(sources) <= 512
          and all(type(name) is str and name and not Path(name).is_absolute() and ".." not in Path(name).parts
              and type(digest) is str and _SHA.fullmatch(digest) for name,digest in sources.items())
          and identity["source_inventory_sha256"] == _sha(_raw(sources)),"parent_source_inventory_required")
    custody._effective_denial(require_fork=True)
    try:os.execve("/usr/bin/security",["security","help"],{"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"})
    except OSError as exc:_need(exc.errno in {errno.EPERM,errno.EACCES},"effective_credential_exec_denial_required")
    else:raise PilotCoverageError("effective_credential_exec_denial_required")
    # tempfile.gettempdir() probes writability and is inappropriate after an
    # initial all-write denial. The fixed existing temporary directory is used
    # only for an exclusive non-data write which MUST be denied.
    probe = Path("/private/tmp")/("insider-pilot-readonly-denial-"+uuid.uuid4().hex)
    try:fd = os.open(probe,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except OSError as exc:_need(exc.errno in {errno.EPERM,errno.EACCES},"effective_all_write_denial_required")
    else:os.close(fd);raise PilotCoverageError("effective_all_write_denial_required")
    _need(custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"])) == identity["source_sha256"],"worker_source_changed")
    result = _audit(LANE_ROOT,ACTUAL_ANCHORS,False)
    _need(custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"])) == identity["source_sha256"],"worker_source_changed")
    return {**result,"execution_identity":identity,"effective_native_network_fork_allwrite_denial":True,
        "effective_native_credential_exec_denial":True}


def _validate_result(result,identity):
    """Strict raw-free readback; does not manufacture independent source facts."""
    fixed = {"schema":SCHEMA,"fixture_only":False,"pilot_window":"2021-01-01..2025-12-31",
        "source_warmup_envelope":"2020-01-01..2020-12-31","source_tail_envelope":"2026-01-01..2026-03-31",
        "earnings_envelope":"2020-10-01..2026-04-30","raw_price_or_return_values_read":False,
        "signals_joined_to_outcomes":False,"source_coverage_is_not_identity_or_actual_release_completeness":True,
        "calendar_session_buffer_sufficiency_verified":False,"effective_native_network_fork_allwrite_denial":True,
        "effective_native_credential_exec_denial":True,**{name:False for name in FALSE_FLAGS}}
    zeros = {"new_provider_requests","credential_reads","qc_jobs","backtests","research_looks"}
    _need(type(result) is dict and set(result) == set(fixed)|zeros|{"execution_identity","earnings","sec","held_input_leaf_sha256"},
          "strict_worker_result_schema_required")
    _need(all(type(result[key]) is type(value) and result[key] == value for key,value in fixed.items())
          and all(type(result[key]) is int and result[key] == 0 for key in zeros)
          and result["execution_identity"] == identity,"worker_result_authority_or_identity_refused")
    earnings = result["earnings"]
    efixed = {"source_campaign_id":EARNINGS_ID,"source_campaign_manifest_sha256":ACTUAL_ANCHORS.earnings_manifest,
        "source_campaign_complete_sha256":ACTUAL_ANCHORS.earnings_complete,"source_control_months_verified":77,
        "pilot_month_count":60,"metadata_rows_decoded_here":False,"source_financial_bodies_decoded":False,
        "body_and_metadata_bytes_hash_streamed":True,"producer_receipt_counts_not_recomputed_row_semantics":True}
    _need(type(earnings) is dict and set(earnings) == set(efixed)|{"buffered_months","pilot_counts"}
          and all(type(earnings[key]) is type(value) and earnings[key] == value for key,value in efixed.items()),
          "strict_earnings_result_required")
    months = earnings["buffered_months"]
    expected = [(index,window) for index,window in enumerate(_windows()) if "2020-10-01" <= window[0] <= "2026-04-01"]
    _need(type(months) is list and len(months) == len(expected),"strict_buffered_month_roster_required")
    for row,(index,window) in zip(months,expected,strict=True):
        _need(type(row) is dict and set(row) == {"window","source_window_ordinal","http_status","counts","body_sha256","metadata_sha256","completion_sha256"}
              and row["window"] == list(window) and type(row["source_window_ordinal"]) is int and row["source_window_ordinal"] == index
              and type(row["http_status"]) is int and row["http_status"] == 200,"strict_buffered_month_required")
        counts = row["counts"]
        _need(type(counts) is dict and set(counts) == set(_COUNTS)
              and all(type(value) is int and 0 <= value <= 200000 for value in counts.values())
              and counts["metadata_accepted_rows"]+counts["quarantined_rows"] == counts["sample_rows"]
              and all(value <= counts["sample_rows"] for value in counts.values())
              and counts["timing_unknown_rows"] <= counts["quarantined_rows"],"strict_buffered_counts_required")
        for key in ("body_sha256","metadata_sha256","completion_sha256"):_digest(row[key])
    pilot = [row for row in months if "2021-01-01" <= row["window"][0] <= "2025-12-01"]
    _need(earnings["pilot_counts"] == {key:sum(row["counts"][key] for row in pilot) for key in _COUNTS}
          and all(type(v) is int for v in earnings["pilot_counts"].values()),"strict_pilot_earnings_counts_required")
    sec = result["sec"]
    sfixed = {"accepted_selection_sha256":ACTUAL_ANCHORS.selection,"accepted_complete_sha256":ACTUAL_ANCHORS.selector_complete,
        "actual_success_observer_final_sha256":ACTUAL_ANCHORS.observer_final,"failed_predecessor_promoted":False,
        "source_capture_window":"2006Q1..2026Q2","audit_quarter_window":"2020Q1..2026Q1","pilot_quarter_count":20,
        "raw_zip_or_submission_rows_decoded_here":False,"original_parent_admission_established_here":False}
    _need(type(sec) is dict and set(sec) == set(sfixed)|{"quarters","pilot_counts","pilot_form_counts","pilot_affected_periods"}
          and all(type(sec[key]) is type(value) and sec[key] == value for key,value in sfixed.items()),"strict_sec_result_required")
    keys = ("submission_rows","form4_or_4a_rows","short_cik_rows","short_cik_form4_or_4a_rows",
            "accession_year_mismatch_rows","accession_year_mismatch_form4_or_4a_rows")
    quarters = sec["quarters"];periods = [period for period in selector.pure._periods() if "2020Q1" <= period <= "2026Q1"]
    _need(type(quarters) is list and len(quarters) == len(periods),"strict_quarter_roster_required")
    for row,period in zip(quarters,periods,strict=True):
        _need(type(row) is dict and set(row) == {"period",*keys,"source_form_counts","selected_affected","zip_sha256"}
              and row["period"] == period and all(type(row[key]) is int and 0 <= row[key] <= selector.pure.MAX_ROWS_PER_TABLE for key in keys),
              "strict_quarter_counts_required")
        forms = row["source_form_counts"]
        _need(type(forms) is dict and set(forms) == set(selector.pure.FORMS)
              and all(type(value) is int and 0 <= value <= row["submission_rows"] for value in forms.values())
              and sum(forms.values()) == row["submission_rows"] and forms["4"]+forms["4/A"] == row["form4_or_4a_rows"]
              and type(row["selected_affected"]) is bool
              and row["selected_affected"] == (row["short_cik_rows"]>0 or row["accession_year_mismatch_rows"]>0),"strict_quarter_partition_required")
        _digest(row["zip_sha256"])
    pilot = [row for row in quarters if "2021Q1" <= row["period"] <= "2025Q4"]
    _need(sec["pilot_counts"] == {key:sum(row[key] for row in pilot) for key in keys}
          and all(type(value) is int for value in sec["pilot_counts"].values())
          and sec["pilot_form_counts"] == {key:sum(row["source_form_counts"][key] for row in pilot) for key in selector.pure.FORMS}
          and all(type(value) is int for value in sec["pilot_form_counts"].values())
          and sec["pilot_affected_periods"] == [row["period"] for row in pilot if row["selected_affected"]],"strict_pilot_sec_counts_required")
    leaves = result["held_input_leaf_sha256"]
    expected_names = {"/".join((*EARNINGS_PARTS,name)) for name in ("manifest.json","complete.json")}
    for index,window in enumerate(_windows()):
        expected_names.update("/".join((*EARNINGS_PARTS,f"window-{index:04d}"+suffix)) for suffix in ("-started.json","-complete.json"))
        expected_names.add("/".join((*EARNINGS_BASE,"scopes",_sha(_raw(custody._scope(window)))+".json")))
        if "2020-10-01" <= window[0] <= "2026-04-01":
            expected_names.update("/".join((*EARNINGS_PARTS,f"window-{index:04d}"+suffix)) for suffix in ("-response.json","-metadata.json"))
    expected_names.update("/".join((*SELECTOR_PARTS,name)) for name in ("reservation.json","selection.json","complete.json"))
    expected_names.update("/".join((*OBSERVER_PARTS,name)) for name in ("reservation.json","readback.json","terminal.json","final.json"))
    _need(type(leaves) is dict and set(leaves) == expected_names,"strict_held_input_roster_required")
    for digest in leaves.values():_digest(digest)
    crosslinks = {"/".join((*EARNINGS_PARTS,"manifest.json")):ACTUAL_ANCHORS.earnings_manifest,
        "/".join((*EARNINGS_PARTS,"complete.json")):ACTUAL_ANCHORS.earnings_complete,
        "/".join((*SELECTOR_PARTS,"selection.json")):ACTUAL_ANCHORS.selection,
        "/".join((*SELECTOR_PARTS,"complete.json")):ACTUAL_ANCHORS.selector_complete,
        "/".join((*OBSERVER_PARTS,"final.json")):ACTUAL_ANCHORS.observer_final}
    for row in months:
        prefix = f"window-{row['source_window_ordinal']:04d}"
        for suffix,key in (("-response.json","body_sha256"),("-metadata.json","metadata_sha256"),("-complete.json","completion_sha256")):
            crosslinks["/".join((*EARNINGS_PARTS,prefix+suffix))] = row[key]
    _need(all(leaves[name] == digest for name,digest in crosslinks.items()),"strict_report_hash_crosslinks_required")
    return result


def run_actual(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH,"fixed_production_source_required")
    identity = custody._identity(expected_head)
    _need(SELF_PATH in identity["source_sha256"],"committed_audit_source_required")
    code = ("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;"
            "from research import insider_buying_pilot_coverage_audit as m;"
            "print(m._raw(m._worker(json.loads(sys.stdin.buffer.read(1048577)))).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    child = subprocess.run(("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code),
        input=_raw(identity),capture_output=True,timeout=240,cwd=LANE_ROOT,check=False)
    _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= MAX_CONTROL,"isolated_audit_worker_refused")
    result = _json(child.stdout.removesuffix(b"\n"))
    _validate_result(result,identity)
    _need(custody._identity(expected_head) == identity,"parent_source_changed")
    return result


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__);cli.add_argument("--expected-head",required=True)
    args = cli.parse_args(argv)
    try:result = run_actual(args.expected_head)
    except Exception:
        print('{"disposition":"retained_pilot_metadata_audit_refused"}');return 2
    print(_raw(result).decode());return 0


if __name__ == "__main__":raise SystemExit(main())
