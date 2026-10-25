"""Control-only crosslinks for the protected pilot SEC worker's IPC report.

No source, body, credential, file or process is accessed. These checks prove
the report's internal accounting, not source authenticity or parent admission.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from research import insider_buying_pilot_sec_roster as roster
from research import insider_buying_pilot_sec_parent_audit as audit
from research import insider_buying_pilot_sec_exposure as exposure


class PilotParentReadbackError(ValueError):
    """Fixed refusal codes; private metadata is never interpolated."""


def _need(value, code):
    if not value:raise PilotParentReadbackError(code)


def _raw(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def _sha(value):return hashlib.sha256(value).hexdigest()
def _digest(value):
    _need(type(value) is str and roster._SHA.fullmatch(value) is not None,"readback_digest_refused")
    return value


def _integer(value,cap=1<<63):
    _need(type(value) is int and 0 <= value < cap,"readback_typed_integer_refused")
    return value


def _exact(value,keys):
    _need(type(value) is dict and set(value) == set(keys),"readback_exact_schema_refused")


def _false_authority(value,expected):
    _exact(value,expected)
    _need(all(type(value[key]) is type(want) and value[key] == want for key,want in expected.items()),
        "readback_authority_refused")


def _forms(value):
    _exact(value,roster.FORMS)
    for count in value.values():_integer(count,2_000_001)


def _control_digest(root,name):
    """A simple JSONL event is bound to its whole journal, not a fake leaf."""
    _need(type(name) is str,"readback_control_name_refused")
    if name in root["control_sha256"]:return root["control_sha256"][name]
    match = re.fullmatch(r"attempts\.jsonl:line-([0-9]{6})",name)
    _need(root["profile"] == "simple-jsonl" and match is not None and int(match.group(1)) > 0
        and "attempts.jsonl" in root["control_sha256"],"readback_virtual_journal_control_refused")
    return root["control_sha256"]["attempts.jsonl"]


_ROSTER_KEYS = frozenset(("schema","fixture_only","context_window","pilot_window","intake_manifest_sha256",
    "selection_sha256","schema_profile_sha256","quarters","counts","context_form_counts","pilot_form_counts",
    "source_row_jsonl_sha256","source_row_jsonl_bytes","source_row_digest_framing","raw_source_cik_rewritten",
    "financial_values_interpreted_or_projected","other_table_rows_parsed","authority"))
_ROSTER_QUARTER = frozenset(("period",*roster.STAT_KEYS,"source_form_counts","zip_sha256",
    "submission_member_sha256","submission_header_line_sha256","source_row_jsonl_sha256","source_row_jsonl_bytes"))
_AUDIT_KEYS = frozenset(("schema","fixture_only","source_roster_sha256","exposure_inventory_sha256",
    "retained_candidate_inventory_sha256","quarters","context_counts","pilot_counts","source_row_jsonl_sha256",
    "source_row_jsonl_bytes","source_row_digest_framing","disposition_jsonl_sha256","disposition_jsonl_bytes",
    "disposition_digest_framing","fresh_request_jsonl_sha256","fresh_request_jsonl_bytes","fresh_request_digest_framing",
    "maximum_preview","fresh_request_preview","candidate_queue_requires_cross_quarter_repeat_reconciliation",
    "first_seen_candidates_are_provisional_if_later_accession_repeats",
    "source_accession_occurrences_are_not_globally_deduplicated","global_consumed_accessions",
    "retained_candidate_accessions","coverage_scope","retained_body_hash_verification_is_not_complete_parent_admission",
    "retained_candidate_join_policy","separate_diagnostic_does_not_resolve_original_ambiguous_start",
    "native_sid_required_for_accession_custody","raw_source_cik_rewritten","financial_values_interpreted_or_projected",
    "full_parent_bodies_opened_here","authority"))
_AUDIT_QUARTER = frozenset(("period","counts","source_form_counts","source_row_jsonl_sha256","source_row_jsonl_bytes",
    "disposition_jsonl_sha256","disposition_jsonl_bytes","fresh_request_jsonl_sha256","fresh_request_jsonl_bytes"))
_ACTUAL_COUNTS = {"context_quarters":25,"pilot_quarters":20,"context_submission_rows":1281147,
    "context_form4_or_4a_rows":1163648,"pilot_submission_rows":1008318,"pilot_form4_or_4a_rows":921570}
_SELECTOR_STATS = {"submission_rows":1008318,"form4_or_4a_rows":921570,"short_cik_rows":131,
    "short_cik_form4_or_4a_rows":118,"accession_year_mismatch_rows":0,"accession_year_mismatch_form4_or_4a_rows":0}


def _roster(value):
    _exact(value,_ROSTER_KEYS)
    _need(value["schema"] == roster.SCHEMA and value["fixture_only"] is False
        and value["context_window"] == "2020Q1..2026Q1" and value["pilot_window"] == "2021Q1..2025Q4"
        and value["intake_manifest_sha256"] == roster.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
        and value["selection_sha256"] == roster.ACTUAL_SELECTION_SHA256
        and value["schema_profile_sha256"] == roster.selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256
        and value["source_row_digest_framing"] == roster.FRAMING,"readback_roster_scope_refused")
    _false_authority(value["authority"],roster.selector.pure._authority())
    for key in ("raw_source_cik_rewritten","financial_values_interpreted_or_projected","other_table_rows_parsed"):
        _need(value[key] is False,"readback_roster_scope_refused")
    _exact(value["counts"],roster.COUNT_KEYS)
    _need(all(_integer(value["counts"][key]) == count for key,count in _ACTUAL_COUNTS.items()),
        "readback_actual_counts_refused")
    rows = value["quarters"]
    _need(type(rows) is list and len(rows) == 25,"readback_quarter_roster_refused")
    for period,row in zip(roster.CONTEXT_PERIODS,rows,strict=True):
        _exact(row,_ROSTER_QUARTER);_need(row["period"] == period,"readback_quarter_order_refused")
        for key in roster.STAT_KEYS:_integer(row[key],2_000_001)
        _forms(row["source_form_counts"]);forms = row["source_form_counts"]
        _need(sum(forms.values()) == row["submission_rows"] and forms["4"]+forms["4/A"] == row["form4_or_4a_rows"],
            "readback_form_partition_refused")
        for prefix in ("short_cik","accession_year_mismatch"):
            _need(row[prefix+"_form4_or_4a_rows"] <= row[prefix+"_rows"] <= row["submission_rows"]
                and row[prefix+"_form4_or_4a_rows"] <= row["form4_or_4a_rows"],"readback_anomaly_partition_refused")
        for key in ("zip_sha256","submission_member_sha256","submission_header_line_sha256","source_row_jsonl_sha256"):
            _digest(row[key])
        _need(_integer(row["source_row_jsonl_bytes"]) > 0,"readback_source_bytes_refused")
    pilot = [row for row in rows if row["period"] in roster.PILOT_PERIODS]
    for key,selected,field in (("context_submission_rows",rows,"submission_rows"),("pilot_submission_rows",pilot,"submission_rows"),
            ("context_form4_or_4a_rows",rows,"form4_or_4a_rows"),("pilot_form4_or_4a_rows",pilot,"form4_or_4a_rows")):
        _need(value["counts"][key] == sum(row[field] for row in selected),"readback_count_aggregate_refused")
    for key,selected in (("context_form_counts",rows),("pilot_form_counts",pilot)):
        _forms(value[key])
        _need(value[key] == {form:sum(row["source_form_counts"][form] for row in selected) for form in roster.FORMS},
            "readback_form_aggregate_refused")
    _digest(value["source_row_jsonl_sha256"])
    _need(_integer(value["source_row_jsonl_bytes"]) == sum(row["source_row_jsonl_bytes"] for row in rows),
        "readback_source_bytes_refused")
    return pilot


def _audit(value,source,result):
    _exact(value,_AUDIT_KEYS)
    _need(value["schema"] == audit.SCHEMA and value["fixture_only"] is False
        and value["source_roster_sha256"] == _sha(_raw(source))
        and value["exposure_inventory_sha256"] == result["exposure_inventory_sha256"]
        and value["retained_candidate_inventory_sha256"] == result["retained_body_inventory_sha256"],
        "readback_audit_input_crosslink_refused")
    _false_authority(value["authority"],audit._AUTHORITY)
    fixed = {"coverage_scope":"explicit_known_retained_operational_roots_not_proof_of_no_unjournaled_access",
        "retained_candidate_join_policy":"exact_accession_form_filing_date_period_cik_comparison_and_every_available_source_record_anchor",
        "retained_body_hash_verification_is_not_complete_parent_admission":True,
        "separate_diagnostic_does_not_resolve_original_ambiguous_start":True,
        "first_seen_candidates_are_provisional_if_later_accession_repeats":True,
        "source_accession_occurrences_are_not_globally_deduplicated":True,
        "native_sid_required_for_accession_custody":False,"raw_source_cik_rewritten":False,
        "financial_values_interpreted_or_projected":False,"full_parent_bodies_opened_here":0}
    _need(all(type(value[key]) is type(want) and value[key] == want for key,want in fixed.items()),
        "readback_audit_scope_refused")
    _need(value["source_row_digest_framing"] == audit.SOURCE_FRAMING == source["source_row_digest_framing"]
        and value["disposition_digest_framing"] == audit.LEDGER_FRAMING
        and value["fresh_request_digest_framing"] == audit.QUEUE_FRAMING,"readback_digest_framing_refused")
    _need(type(value["quarters"]) is list and len(value["quarters"]) == 25,"readback_quarter_roster_refused")
    for row,src in zip(value["quarters"],source["quarters"],strict=True):
        _exact(row,_AUDIT_QUARTER)
        _need(row["period"] == src["period"] and row["source_form_counts"] == src["source_form_counts"],
            "readback_audit_quarter_crosslink_refused")
        _exact(row["counts"],audit._COUNTS)
        for count in row["counts"].values():_integer(count,2_000_001)
        c = row["counts"];targets = c["target_filings"]
        _need(c["source_filings"] == src["submission_rows"] == c["context_filings"]+targets
            and targets == src["form4_or_4a_rows"] == c["prior_consumed_targets"]+c["no_prior_dispatch_observed_targets"]
            and targets == c["locator_qualified_targets"]+c["locator_quarantined_targets"],
            "readback_filing_partition_refused")
        _need(c["prior_consumed_targets"] <= c["prior_consumed_filings"] <= c["source_filings"]
            and c["ambiguous_consumption_targets"] <= c["prior_consumed_targets"]
            and c["fresh_locatable_candidate_requests"] <= min(c["no_prior_dispatch_observed_targets"],c["locator_qualified_targets"])
            and c["hash_verified_matching_body_candidate_targets"] <= min(c["retained_candidate_targets"],c["prior_consumed_targets"])
            and c["unverified_matching_body_candidate_targets"] <= c["retained_candidate_targets"] <= targets
            and c["candidate_identity_conflict_targets"] <= targets
            and c["candidate_body_identity_conflict_targets"] <= c["retained_candidate_targets"]
            and c["consumed_without_matching_verified_body_candidate_targets"]+c["hash_verified_matching_body_candidate_targets"]
                == c["prior_consumed_targets"]
            and c["cross_quarter_repeat_targets"] <= c["cross_quarter_repeat_filings"] <= c["source_filings"]
            and c["cross_quarter_repeat_targets"] <= targets
            and c["cross_quarter_identity_conflict_filings"] <= c["cross_quarter_repeat_filings"],
            "readback_disposition_bounds_refused")
        for prefix in ("source_row","disposition","fresh_request"):
            _digest(row[prefix+"_jsonl_sha256"]);_integer(row[prefix+"_jsonl_bytes"])
        _need(row["source_row_jsonl_sha256"] == src["source_row_jsonl_sha256"]
            and row["source_row_jsonl_bytes"] == src["source_row_jsonl_bytes"],
            "readback_source_stream_crosslink_refused")
    for key,selected in (("context_counts",value["quarters"]),
            ("pilot_counts",[row for row in value["quarters"] if row["period"] in roster.PILOT_PERIODS])):
        _exact(value[key],audit._COUNTS)
        _need(all(_integer(value[key][name]) == sum(row["counts"][name] for row in selected) for name in audit._COUNTS),
            "readback_disposition_aggregate_refused")
    for prefix in ("source_row","disposition","fresh_request"):
        _digest(value[prefix+"_jsonl_sha256"])
        _need(_integer(value[prefix+"_jsonl_bytes"]) == sum(row[prefix+"_jsonl_bytes"] for row in value["quarters"]),
            "readback_stream_size_aggregate_refused")
    _need(value["source_row_jsonl_sha256"] == source["source_row_jsonl_sha256"]
        and value["source_row_jsonl_bytes"] == source["source_row_jsonl_bytes"],"readback_source_stream_crosslink_refused")
    _need(type(value["candidate_queue_requires_cross_quarter_repeat_reconciliation"]) is bool
        and value["candidate_queue_requires_cross_quarter_repeat_reconciliation"]
            is (value["context_counts"]["cross_quarter_repeat_filings"] > 0),"readback_queue_provisional_scope_refused")
    _need(0 <= _integer(value["maximum_preview"]) <= 256 and type(value["fresh_request_preview"]) is list
        and len(value["fresh_request_preview"]) == min(value["maximum_preview"],value["context_counts"]["fresh_locatable_candidate_requests"]),
        "readback_preview_bound_refused")
    for item in value["fresh_request_preview"]:
        _exact(item,("request","request_sha256","pre_normalization_target"))
        _need(type(item["request"]) is dict and type(item["pre_normalization_target"]) is dict
            and item["request_sha256"] == _sha(_raw(item["request"])),"readback_preview_hash_refused")
    _integer(value["global_consumed_accessions"]);_integer(value["retained_candidate_accessions"])


def _inputs(result,source,parent):
    retained,observer,intake = (result[key] for key in ("retained_body_inventory","exposure_observer","intake_context"))
    for key in ("exposure_inventory_sha256","exposure_snapshot_sha256","retained_body_inventory_sha256"):_digest(result[key])
    _need(_sha(_raw(retained)) == result["retained_body_inventory_sha256"]
        and _sha(_raw(observer)) == result["exposure_snapshot_sha256"],"readback_inventory_hash_refused")
    try:records = audit._candidate_inventory(retained)
    except (ValueError,TypeError,KeyError):raise PilotParentReadbackError("readback_retained_inventory_refused") from None
    _need(retained["fixture_only"] is False and parent["retained_candidate_accessions"] == len(records),
        "readback_retained_inventory_scope_refused")
    masters = retained["masters"]
    _need([row["period"] for row in masters] == list(roster.CONTEXT_PERIODS)
        and all(row["body_currently_hash_verified"] is True for row in masters)
        and all(item["body_currently_hash_verified"] is True for row in retained["records"] for item in row["candidates"]),
        "readback_opaque_body_checks_required")
    _exact(observer,("schema","fixture_only","bootstrap_snapshot_sha256","bootstrap_snapshot","exposure_sha256",
        "candidates_sha256","dispatch_records","authority","body_files_opened_here","source_admission_claimed"))
    _need(observer["schema"] == exposure.SCHEMA+"/snapshot" and observer["fixture_only"] is False
        and observer["body_files_opened_here"] is False and observer["source_admission_claimed"] is False
        and observer["exposure_sha256"] == result["exposure_inventory_sha256"],"readback_observer_scope_refused")
    _false_authority(observer["authority"],exposure.authority())
    original = copy.deepcopy(retained)
    for row in original["masters"]:row["body_currently_hash_verified"] = False
    for row in original["records"]:
        for item in row["candidates"]:item["body_currently_hash_verified"] = False
    _need(observer["candidates_sha256"] == _sha(_raw(original)),"readback_pre_hash_inventory_crosslink_refused")
    bootstrap = observer["bootstrap_snapshot"]
    _exact(bootstrap,("schema","roots","exposure_inventory_sha256","global_exposed_accessions"))
    _need(bootstrap["schema"] == exposure.bootstrap.SCHEMA+"/exposure-snapshot"
        and observer["bootstrap_snapshot_sha256"] == _sha(_raw(bootstrap))
        and bootstrap["exposure_inventory_sha256"] == result["exposure_inventory_sha256"]
        and _integer(bootstrap["global_exposed_accessions"]) == parent["global_consumed_accessions"],
        "readback_bootstrap_crosslink_refused")
    _need(type(bootstrap["roots"]) is list and 1 <= len(bootstrap["roots"]) <= 32
        and type(observer["dispatch_records"]) is list and len(observer["dispatch_records"]) <= 1_000_000,
        "readback_observer_roster_refused")
    root_ids = set()
    for row in bootstrap["roots"]:
        _exact(row,("root_id","profile","control_sha256","directory_inventories","control_clocks",
            "consumed_start_records","consumed_reservation_records","reused_records","completed_item_records",
            "terminal_records","master_index_attempts_not_parent_exposure","pending_parent_accessions",
            "clock_missing_is_not_backdated","legacy_public_metadata_modes","exposure_controls","plan_requests_are_dispatch_evidence"))
        _need(type(row["root_id"]) is str and audit._ROOT.fullmatch(row["root_id"])
            and row["root_id"] not in root_ids,"readback_observer_root_refused")
        root_ids.add(row["root_id"])
        _need(row["profile"] in {"simple-jsonl","event-chain","sharded-events","diagnostic","global-claims"}
            and row["clock_missing_is_not_backdated"] is True and row["plan_requests_are_dispatch_evidence"] is False,
            "readback_bootstrap_root_scope_refused")
        for key in ("consumed_start_records","consumed_reservation_records","reused_records","completed_item_records",
                "terminal_records","master_index_attempts_not_parent_exposure"):_integer(row[key])
        for key in ("control_sha256","directory_inventories","control_clocks","legacy_public_metadata_modes"):
            _need(type(row[key]) is dict,"readback_bootstrap_metadata_refused")
        for name,digest in row["control_sha256"].items():audit._relative(name);_digest(digest)
        for name,names in row["directory_inventories"].items():
            if name:audit._relative(name)
            _need(type(names) is list and all(type(item) is str and item and "/" not in item and "\\" not in item
                and item not in {".",".."} for item in names) and len(names) == len(set(names)),
                "readback_bootstrap_inventory_refused")
        for name,clocks in row["control_clocks"].items():
            _control_digest(row,name)
            _need(type(clocks) is dict,"readback_bootstrap_clock_refused")
            for key,value in clocks.items():
                _need(type(key) is str and key.endswith(("_utc","_at_utc")),"readback_bootstrap_clock_refused")
                exposure.bootstrap._utc(value)
        for name,mode in row["legacy_public_metadata_modes"].items():
            _need(name in row["control_sha256"] and type(mode) is int and mode in {0o600,0o644},
                "readback_bootstrap_mode_refused")
        pending = row["pending_parent_accessions"]
        _need(type(pending) is list and pending == sorted(set(pending)),"readback_pending_accession_roster_refused")
        for accession in pending:audit._accession(accession)
        _need(type(row["exposure_controls"]) is list,"readback_exposure_control_roster_refused")
        for item in row["exposure_controls"]:
            _exact(item,("control_name","control_sha256","accession_number","state","clock"))
            _need(item["control_sha256"] == _control_digest(row,item["control_name"])
                and item["state"] in {"reserved","started"},"readback_exposure_control_refused")
            audit._accession(item["accession_number"])
            _need(item["clock"] is None or type(item["clock"]) is dict,"readback_exposure_control_clock_refused")
            if item["clock"] is not None:
                for value in item["clock"].values():exposure.bootstrap._utc(value)
    for row in masters:
        _need(row["root_id"] in root_ids,"readback_master_root_refused")
        receipt = row["producer_receipt"]
        _exact(receipt,("decoded_sha256","decoded_size_bytes","parser_version","master_receipt_sha256",
            "all_filing_row_count","form4_or_4a_path_rows"))
        _digest(receipt["decoded_sha256"]);_digest(receipt["master_receipt_sha256"])
        _need(0 < _integer(receipt["decoded_size_bytes"]) <= 64*1024*1024
            and _integer(receipt["form4_or_4a_path_rows"]) <= _integer(receipt["all_filing_row_count"])
            and receipt["parser_version"] == "insider-buying-sec-quarter-master-idx-v1","readback_master_receipt_refused")
    for row in retained["records"]:
        for item in row["candidates"]:_need(item["root_id"] in root_ids,"readback_candidate_root_refused")
    for row in observer["dispatch_records"]:
        _exact(row,("accession_number","root_id","control_name","control_sha256","url","state","outcome"))
        _need(row["root_id"] in root_ids and row["state"] in {"reserved","started","ambiguous","response_observed",
            "consumed_refusal","response_unsealed"} and (row["outcome"] is None or type(row["outcome"]) is str),
            "readback_dispatch_metadata_refused")
        try:audit._accession(row["accession_number"]);audit._relative(row["control_name"]);_digest(row["control_sha256"])
        except ValueError:raise PilotParentReadbackError("readback_dispatch_metadata_refused") from None
        root = next(item for item in bootstrap["roots"] if item["root_id"] == row["root_id"])
        _need(row["control_sha256"] == _control_digest(root,row["control_name"]),"readback_dispatch_control_refused")
        _need(type(row["url"]) is str and exposure.bootstrap._accession_url(row["url"]) == row["accession_number"],
            "readback_dispatch_url_refused")
    fixed = {"fixture_only":False,"manifest_sha256":source["intake_manifest_sha256"],
        "manifest_bytes":roster.selector.pure.census.RETAINED_ZIP_MANIFEST_SIZE_BYTES,
        "census_sha256":roster.selector.pure.headers.RETAINED_82Q_CENSUS_SHA256,
        "header_preflight_sha256":roster.selector.pure.RETAINED_HEADER_SHA256,
        "schema_profile_sha256":source["schema_profile_sha256"],"source_window":"2006Q1..2026Q2",
        "leaf_count":84,"retained_source_capture_commit":roster.selector.pure.census._CAPTURE_COMMIT,
        "auxiliary_control_semantics":"opaque_current_committed_gitattributes_not_source_data"}
    _exact(intake,(*fixed,"leaf_pins","leaf_names","quarter_observations"))
    _need(all(type(intake[key]) is type(want) and intake[key] == want for key,want in fixed.items()),
        "readback_intake_scope_refused")
    names = [roster.selector.pure.census._MANIFEST_NAME,".gitattributes",
        *(period.lower()+"_form345.zip" for period in roster.selector.pure._periods())]
    _need(intake["leaf_names"] == sorted(names),"readback_intake_inventory_refused")
    _exact(intake["leaf_pins"],names);_exact(intake["quarter_observations"],roster.selector.pure._periods())
    for pin in intake["leaf_pins"].values():
        _exact(pin,("sha256","bytes"));_digest(pin["sha256"]);_need(_integer(pin["bytes"]) > 0,"readback_intake_leaf_refused")
    _need(intake["leaf_pins"][roster.selector.pure.census._MANIFEST_NAME]
        == {"sha256":source["intake_manifest_sha256"],"bytes":roster.selector.pure.census.RETAINED_ZIP_MANIFEST_SIZE_BYTES}
        and intake["leaf_pins"][".gitattributes"] == {"sha256":roster.selector._AUX_PIN[0],"bytes":roster.selector._AUX_PIN[1]},
        "readback_intake_control_pins_refused")
    for stamp in intake["quarter_observations"].values():
        _need(type(stamp) is str and roster.selector.pure.census._LOCAL_STAMP.fullmatch(stamp),"readback_intake_clock_refused")
    for row in source["quarters"]:
        _need(intake["leaf_pins"][row["period"].lower()+"_form345.zip"]["sha256"] == row["zip_sha256"],
            "readback_roster_intake_crosslink_refused")


def validate_summaries(result):
    """Validate protected-worker summaries without reopening original inputs."""
    try:
        _need(type(result) is dict,"readback_report_required")
        source,parent = result["source_roster"],result["parent_audit"]
        pilot = _roster(source);_audit(parent,source,result);_inputs(result,source,parent)
        accepted = result["accepted_selector_pilot_counts"]
        _exact(accepted,roster.STAT_KEYS)
        _need(all(_integer(accepted[key]) == want == sum(row[key] for row in pilot)
            for key,want in _SELECTOR_STATS.items()),"readback_accepted_selector_counts_refused")
        return result
    except PilotParentReadbackError:raise
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):
        raise PilotParentReadbackError("readback_summary_refused") from None
