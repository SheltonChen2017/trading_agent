"""Entirely invented IPC metadata; registered count constants are not data."""
from __future__ import annotations

import copy

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_sec_parent_readback as m


def invented_report():
    """Build coherent synthetic summaries, never an executed market receipt."""
    r = m.roster;source_rows = []
    for index,period in enumerate(r.CONTEXT_PERIODS):
        pilot = period in r.PILOT_PERIODS
        group = r.PILOT_PERIODS if pilot else tuple(p for p in r.CONTEXT_PERIODS if p not in r.PILOT_PERIODS)
        position = group.index(period)
        totals = (1008318,921570) if pilot else (272829,242078)
        source,target = (total//len(group)+(position < total%len(group)) for total in totals)
        forms = dict.fromkeys(r.FORMS,0);forms.update({"3":source-target,"4":target})
        short,short_target = ((131,118) if period == "2021Q1" else (15,14) if period == "2020Q4" else (0,0))
        source_rows.append({"period":period,"submission_rows":source,"form4_or_4a_rows":target,
            "short_cik_rows":short,"short_cik_form4_or_4a_rows":short_target,
            "accession_year_mismatch_rows":0,"accession_year_mismatch_form4_or_4a_rows":0,"source_form_counts":forms,
            "zip_sha256":m._sha(("zip"+period).encode()),"submission_member_sha256":m._sha(("member"+period).encode()),
            "submission_header_line_sha256":m._sha(("header"+period).encode()),
            "source_row_jsonl_sha256":m._sha(("source"+period).encode()),"source_row_jsonl_bytes":source*100})
    pilot_rows = [row for row in source_rows if row["period"] in r.PILOT_PERIODS]
    source = {"schema":r.SCHEMA,"fixture_only":False,"context_window":"2020Q1..2026Q1","pilot_window":"2021Q1..2025Q4",
        "intake_manifest_sha256":r.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256,
        "selection_sha256":r.ACTUAL_SELECTION_SHA256,"schema_profile_sha256":r.selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "quarters":source_rows,"counts":dict(m._ACTUAL_COUNTS),"source_row_jsonl_sha256":"a"*64,
        "source_row_jsonl_bytes":sum(row["source_row_jsonl_bytes"] for row in source_rows),
        "source_row_digest_framing":r.FRAMING,"raw_source_cik_rewritten":False,
        "financial_values_interpreted_or_projected":False,"other_table_rows_parsed":False,"authority":r.selector.pure._authority()}
    for key,rows in (("context_form_counts",source_rows),("pilot_form_counts",pilot_rows)):
        source[key] = {form:sum(row["source_form_counts"][form] for row in rows) for form in r.FORMS}
    masters = []
    for row in source_rows:
        period = row["period"]
        masters.append({"root_id":"masters-v3","control_name":"report.json","control_sha256":"b"*64,
            "period":period,"source_url":f"https://www.sec.gov/Archives/edgar/full-index/{period[:4]}/QTR{period[-1]}/master.gz",
            "raw_object":{"relative_path":"objects/"+("c"*64)+".bin","sha256":"c"*64,"size_bytes":100},
            "producer_receipt":{"decoded_sha256":"d"*64,"decoded_size_bytes":100,"parser_version":"insider-buying-sec-quarter-master-idx-v1",
                "master_receipt_sha256":"e"*64,"all_filing_row_count":1,"form4_or_4a_path_rows":1},
            "body_currently_hash_verified":True,"master_decoded_here":False})
    retained = {"schema":m.audit.CANDIDATE_SCHEMA,"fixture_only":False,"records":[],"masters":masters,"authority":m.exposure.authority()}
    original = copy.deepcopy(retained)
    for row in original["masters"]:row["body_currently_hash_verified"] = False
    exposure_sha = "f"*64
    root = {"root_id":"masters-v3","profile":"event-chain","control_sha256":{"report.json":"b"*64},
        "directory_inventories":{"":["report.json"]},"control_clocks":{},"consumed_start_records":0,"consumed_reservation_records":0,
        "reused_records":0,"completed_item_records":0,"terminal_records":0,"master_index_attempts_not_parent_exposure":0,
        "pending_parent_accessions":[],"clock_missing_is_not_backdated":True,"legacy_public_metadata_modes":{},
        "exposure_controls":[],"plan_requests_are_dispatch_evidence":False}
    bootstrap = {"schema":m.exposure.bootstrap.SCHEMA+"/exposure-snapshot","roots":[root],
        "exposure_inventory_sha256":exposure_sha,"global_exposed_accessions":0}
    observer = {"schema":m.exposure.SCHEMA+"/snapshot","fixture_only":False,
        "bootstrap_snapshot_sha256":m._sha(m._raw(bootstrap)),"bootstrap_snapshot":bootstrap,
        "exposure_sha256":exposure_sha,"candidates_sha256":m._sha(m._raw(original)),"dispatch_records":[],
        "authority":m.exposure.authority(),"body_files_opened_here":False,"source_admission_claimed":False}
    audit_rows = []
    for row in source_rows:
        counts = dict.fromkeys(m.audit._COUNTS,0)
        counts.update(source_filings=row["submission_rows"],target_filings=row["form4_or_4a_rows"],
            context_filings=row["submission_rows"]-row["form4_or_4a_rows"],
            no_prior_dispatch_observed_targets=row["form4_or_4a_rows"],locator_qualified_targets=row["form4_or_4a_rows"],
            fresh_locatable_candidate_requests=row["form4_or_4a_rows"])
        audit_rows.append({"period":row["period"],"counts":counts,"source_form_counts":row["source_form_counts"],
            "source_row_jsonl_sha256":row["source_row_jsonl_sha256"],"source_row_jsonl_bytes":row["source_row_jsonl_bytes"],
            "disposition_jsonl_sha256":"1"*64,"disposition_jsonl_bytes":row["submission_rows"]*200,
            "fresh_request_jsonl_sha256":"2"*64,"fresh_request_jsonl_bytes":row["form4_or_4a_rows"]*100})
    parent = {"schema":m.audit.SCHEMA,"fixture_only":False,"source_roster_sha256":m._sha(m._raw(source)),
        "exposure_inventory_sha256":exposure_sha,"retained_candidate_inventory_sha256":m._sha(m._raw(retained)),
        "quarters":audit_rows,"source_row_jsonl_sha256":source["source_row_jsonl_sha256"],
        "source_row_jsonl_bytes":source["source_row_jsonl_bytes"],"source_row_digest_framing":m.audit.SOURCE_FRAMING,
        "disposition_jsonl_sha256":"3"*64,"disposition_jsonl_bytes":sum(row["disposition_jsonl_bytes"] for row in audit_rows),
        "disposition_digest_framing":m.audit.LEDGER_FRAMING,"fresh_request_jsonl_sha256":"4"*64,
        "fresh_request_jsonl_bytes":sum(row["fresh_request_jsonl_bytes"] for row in audit_rows),"fresh_request_digest_framing":m.audit.QUEUE_FRAMING,
        "maximum_preview":0,"fresh_request_preview":[],"candidate_queue_requires_cross_quarter_repeat_reconciliation":False,
        "first_seen_candidates_are_provisional_if_later_accession_repeats":True,
        "source_accession_occurrences_are_not_globally_deduplicated":True,"global_consumed_accessions":0,"retained_candidate_accessions":0,
        "coverage_scope":"explicit_known_retained_operational_roots_not_proof_of_no_unjournaled_access",
        "retained_body_hash_verification_is_not_complete_parent_admission":True,
        "retained_candidate_join_policy":"exact_accession_form_filing_date_period_cik_comparison_and_every_available_source_record_anchor",
        "separate_diagnostic_does_not_resolve_original_ambiguous_start":True,"native_sid_required_for_accession_custody":False,
        "raw_source_cik_rewritten":False,"financial_values_interpreted_or_projected":False,"full_parent_bodies_opened_here":0,
        "authority":dict(m.audit._AUTHORITY)}
    for key,rows in (("context_counts",audit_rows),("pilot_counts",[row for row in audit_rows if row["period"] in r.PILOT_PERIODS])):
        parent[key] = {name:sum(row["counts"][name] for row in rows) for name in m.audit._COUNTS}
    periods = r.selector.pure._periods();names = [r.selector.pure.census._MANIFEST_NAME,".gitattributes",
        *(period.lower()+"_form345.zip" for period in periods)]
    pins = {name:{"sha256":"5"*64,"bytes":100} for name in names}
    pins[r.selector.pure.census._MANIFEST_NAME] = {"sha256":source["intake_manifest_sha256"],"bytes":34381}
    pins[".gitattributes"] = {"sha256":r.selector._AUX_PIN[0],"bytes":r.selector._AUX_PIN[1]}
    for row in source_rows:pins[row["period"].lower()+"_form345.zip"]["sha256"] = row["zip_sha256"]
    intake = {"fixture_only":False,"manifest_sha256":source["intake_manifest_sha256"],"manifest_bytes":34381,
        "census_sha256":r.selector.pure.headers.RETAINED_82Q_CENSUS_SHA256,"header_preflight_sha256":r.selector.pure.RETAINED_HEADER_SHA256,
        "schema_profile_sha256":source["schema_profile_sha256"],"source_window":"2006Q1..2026Q2",
        "leaf_count":84,"leaf_pins":pins,"leaf_names":sorted(names),"retained_source_capture_commit":r.selector.pure.census._CAPTURE_COMMIT,
        "auxiliary_control_semantics":"opaque_current_committed_gitattributes_not_source_data",
        "quarter_observations":dict.fromkeys(periods,"2026-09-24T22:52:19.7647157Z")}
    return {"source_roster":source,"parent_audit":parent,"retained_body_inventory":retained,
        "retained_body_inventory_sha256":m._sha(m._raw(retained)),"exposure_observer":observer,
        "exposure_snapshot_sha256":m._sha(m._raw(observer)),"exposure_inventory_sha256":exposure_sha,
        "accepted_selector_pilot_counts":dict(m._SELECTOR_STATS),"intake_context":intake}


def reseal(value):
    value["parent_audit"]["source_roster_sha256"] = m._sha(m._raw(value["source_roster"]))
    value["retained_body_inventory_sha256"] = m._sha(m._raw(value["retained_body_inventory"]))
    value["parent_audit"]["retained_candidate_inventory_sha256"] = value["retained_body_inventory_sha256"]
    observer = value["exposure_observer"]
    observer["bootstrap_snapshot_sha256"] = m._sha(m._raw(observer["bootstrap_snapshot"]))
    value["exposure_snapshot_sha256"] = m._sha(m._raw(observer))


def test_realistic_invented_counts_crosslinks_and_false_authorities():
    value = invented_report()
    assert m.validate_summaries(value) is value


@pytest.mark.parametrize("fault",("roster_hash","source_hash","source_bytes","quarter_source_hash","exposure_hash",
    "candidate_hash","selector_count","selector_bool","roster_bool","unknown_roster","unknown_audit","positive_authority",
    "nested_fixture","financial","quarter_order","form_partition","count_partition","disposition_aggregate",
    "pending_queue","candidate_unverified","intake_hash","intake_pin","bootstrap_hash","bootstrap_count","old_inventory_hash"))
def test_internal_metadata_laundering_is_refused_even_with_resealed_outer_hashes(fault):
    value = invented_report();parent = value["parent_audit"];source = value["source_roster"]
    if fault == "roster_hash":parent["source_roster_sha256"] = "9"*64
    elif fault == "source_hash":parent["source_row_jsonl_sha256"] = "9"*64
    elif fault == "source_bytes":parent["source_row_jsonl_bytes"] += 1
    elif fault == "quarter_source_hash":parent["quarters"][0]["source_row_jsonl_sha256"] = "9"*64
    elif fault == "exposure_hash":parent["exposure_inventory_sha256"] = "9"*64
    elif fault == "candidate_hash":parent["retained_candidate_inventory_sha256"] = "9"*64
    elif fault == "selector_count":value["accepted_selector_pilot_counts"]["submission_rows"] += 1
    elif fault == "selector_bool":value["accepted_selector_pilot_counts"]["accession_year_mismatch_rows"] = False
    elif fault == "roster_bool":source["counts"]["context_quarters"] = True;reseal(value)
    elif fault == "unknown_roster":source["unexpected"] = True;reseal(value)
    elif fault == "unknown_audit":parent["unexpected"] = True
    elif fault == "positive_authority":source["authority"]["backtesting_ready"] = True;reseal(value)
    elif fault == "nested_fixture":parent["fixture_only"] = True
    elif fault == "financial":parent["financial_values_interpreted_or_projected"] = True
    elif fault == "quarter_order":source["quarters"][0],source["quarters"][1] = source["quarters"][1],source["quarters"][0];reseal(value)
    elif fault == "form_partition":source["quarters"][0]["source_form_counts"]["3"] += 1;reseal(value)
    elif fault == "count_partition":parent["quarters"][0]["counts"]["target_filings"] -= 1
    elif fault == "disposition_aggregate":parent["context_counts"]["prior_consumed_targets"] += 1
    elif fault == "pending_queue":parent["candidate_queue_requires_cross_quarter_repeat_reconciliation"] = True
    elif fault == "candidate_unverified":value["retained_body_inventory"]["masters"][0]["body_currently_hash_verified"] = False;reseal(value)
    elif fault == "intake_hash":value["intake_context"]["leaf_pins"]["2020q1_form345.zip"]["sha256"] = "9"*64
    elif fault == "intake_pin":value["intake_context"]["leaf_pins"][".gitattributes"]["bytes"] += 1
    elif fault == "bootstrap_hash":value["exposure_observer"]["bootstrap_snapshot_sha256"] = "9"*64;value["exposure_snapshot_sha256"] = m._sha(m._raw(value["exposure_observer"]))
    elif fault == "bootstrap_count":value["exposure_observer"]["bootstrap_snapshot"]["global_exposed_accessions"] = 1;reseal(value)
    else:value["exposure_observer"]["candidates_sha256"] = "9"*64;reseal(value)
    with pytest.raises(m.PilotParentReadbackError):m.validate_summaries(value)


def _virtual_control(value):
    root = value["exposure_observer"]["bootstrap_snapshot"]["roots"][0]
    root["profile"] = "simple-jsonl";root["control_sha256"]["attempts.jsonl"] = "6"*64
    name = "attempts.jsonl:line-000001";clocks = {"started_utc":"2026-09-29T01:00:00+00:00"}
    root["control_clocks"][name] = clocks
    root["exposure_controls"] = [{"control_name":name,"control_sha256":"6"*64,
        "accession_number":"0000000001-21-000001","state":"started","clock":clocks}]
    value["exposure_observer"]["dispatch_records"] = [{"accession_number":"0000000001-21-000001",
        "root_id":root["root_id"],"control_name":name,"control_sha256":"6"*64,
        "url":"https://www.sec.gov/Archives/edgar/data/1/0000000001-21-000001.txt","state":"started","outcome":None}]
    reseal(value)
    return root


def test_simple_jsonl_virtual_event_binds_whole_journal_not_nonexistent_leaf():
    value = invented_report();_virtual_control(value)
    assert m.validate_summaries(value) is value


@pytest.mark.parametrize("fault",("zero","wrong_profile","other_name","missing_journal","wrong_hash"))
def test_virtual_event_cannot_escape_its_exact_profile_journal_and_digest(fault):
    value = invented_report();root = _virtual_control(value)
    if fault == "zero":root["control_clocks"] = {"attempts.jsonl:line-000000":{}}
    elif fault == "wrong_profile":root["profile"] = "event-chain"
    elif fault == "other_name":root["control_clocks"] = {"other.jsonl:line-000001":{}}
    elif fault == "missing_journal":del root["control_sha256"]["attempts.jsonl"]
    else:root["exposure_controls"][0]["control_sha256"] = "9"*64
    reseal(value)
    with pytest.raises(m.PilotParentReadbackError):m.validate_summaries(value)
