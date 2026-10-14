"""Invented title/reference inputs, no actual source/account/financial values."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("fcntl", reason="validated POSIX custody caller scope")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
import test_insider_buying_sec_2006q1_pem_reassessment_v1 as source_fixture
import test_insider_buying_sharadar_reference_cohort as ticker_fixture
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS as OBSERVED_PRODUCER_FLAGS

from research import insider_buying_sec_title_current_reference_v1 as module


@pytest.fixture
def supplied(tmp_path, monkeypatch):return source_fixture.supplied.__wrapped__(tmp_path, monkeypatch)


def _row(value=b"Common Stock", tag=b"nonDerivativeTransaction", *, extra=b""):
    return b"<"+tag+b"><securityTitle><value>"+value+b"</value></securityTitle>"+extra+b"</"+tag+b">"


def arguments(supplied, *, table=None, tickers=None, issuer_first=False, selected=2):
    """Reusable small genuine-view fixture factory for the independent front."""
    snapshot,census,_ = supplied
    if table is None:table = b"<nonDerivativeTable>"+_row()+b"</nonDerivativeTable>"
    descriptors,bridges = [],[]
    for item in source_fixture._inputs(supplied,selected):
        inner = source_fixture._inner(item["request"]).replace(b"</ownershipDocument>", table+b"</ownershipDocument>")
        if issuer_first and item["prefix_ordinal"] == selected-1:
            start=inner.index(b"REPORTING-OWNER:\n");issuer=inner.index(b"ISSUER:\n");end=inner.index(b"</SEC-HEADER>\n")
            inner=inner[:start]+inner[issuer:end]+inner[start:issuer]+inner[end:]
        changed=source_fixture._with_raw(item,source_fixture._wrap(inner));descriptors.append(changed)
        view=module.pem.pem.build_early_pem_source_view(changed["raw_bytes"],expected_original_body_sha256=changed["body_sha256"])
        try:bridges.append(module.pem.project_genuine_pem_source_view(changed["request"],view,capture_result_sha256=changed["result_sha256"]))
        except module.pem.SecCompleteSubmissionError:pass
    assessment=module.pem.assess_2006q1_pem_source_view_identity(snapshot,census,tuple(descriptors),
        expected_capture_report_sha256=module.preceding.CAPTURE_REPORT,fixture_only=True)
    body=assessment.to_payload();inventory=module.pem.build_pem_source_view_inventory(tuple(bridges))
    source_complete={"schema":module.preceding.SCHEMA+"/complete","fixture_only":True,
        "assessment_sha256":assessment.sha256,"assessment_bytes":len(assessment.canonical_bytes()),
        "capture_id":module.preceding.original.CAPTURE_ID,"capture_report_sha256":module.preceding.CAPTURE_REPORT,
        "source_view_inventory_sha256":inventory.sha256,"source_view_profile":module.pem.pem.PROFILE,
        "counts":body["counts"],"authority":module.pem._authority(),"frozen_original_baseline":{"preparation_context":{
            "parsed_snapshot_id":snapshot.identity.snapshot_id,"parsed_lineage_sha256":snapshot.identity.lineage_hash,
            "census_quarter_sha256":module.preceding.original.hash_payload(census.to_payload()),
            **module.preceding._source_identity_inventory(body["rows"])}}}
    if tickers is None:
        tickers=[ticker_fixture.ticker(cik="123456"),ticker_fixture.ticker(cik="123456",table="fundamentals"),
            ticker_fixture.ticker(perma="unrelated",cik="999999",name="Common Stock",relatedtickers="ABC"),
            ticker_fixture.ticker(perma="",cik="",table="holdings_investor")]
    data=ticker_fixture.fixture(tickers=tickers);shara=ticker_fixture.arguments(data)
    shara_complete={"schema":"insider-sharadar-reference-cohort-observer-v2","fixture_only":True,
        "capture_manifest_sha256":shara["capture_manifest_sha256"],"tickers_projection_sha256":shara["tickers_projection_sha256"],
        "original_capture_lineage_preserved":True,"fundamentals_decoded":False,"financial_values_interpreted":False,
        "provider_dispatches":0,"credential_reads":0,"counts":{"source_ticker_rows":len(tickers),"ticker_rows_accounted":len(tickers)},
        **dict.fromkeys(OBSERVED_PRODUCER_FLAGS,False)}
    complete_raw=module._raw(source_complete);shara_raw=module._raw(shara_complete)
    return {"source_view_assessment_raw":assessment.canonical_bytes(),"expected_source_view_assessment_sha256":assessment.sha256,
        "source_view_complete_raw":complete_raw,"expected_source_view_complete_sha256":module._sha(complete_raw),
        "source_view_parent_inventory":inventory,"tickers_projection_raw":shara["tickers_projection_raw"],
        "expected_tickers_projection_sha256":shara["tickers_projection_sha256"],"capture_manifest_raw":shara["capture_manifest_raw"],
        "expected_capture_manifest_sha256":shara["capture_manifest_sha256"],"sharadar_complete_raw":shara_raw,
        "expected_sharadar_complete_sha256":module._sha(shara_raw),"fixture_only":True}


def payload(supplied, **kwargs):return module.assess_sec_title_current_reference(**arguments(supplied,**kwargs)).to_payload()


def test_full_six_form_roster_and_all_current_rows_remain_candidates_not_admission(supplied):
    body=payload(supplied)
    assert body["counts"]["source_filings"]==len(body["filing_roster"])==6
    assert body["counts"]["ticker_rows"]==len(body["ticker_row_dispositions"])==4
    assert body["counts"]["genuine_view_parents"]==body["counts"]["plain_title_occurrences"]==2
    assert body["counts"]["unique_cik_titles"]==1
    assert body["current_permaticker_groups"][0]["ticker_source_ordinals"]==[1,2]
    assert body["current_cik_group_index"][body["title_key_index"][0]["issuer_cik"]]==[0]
    assert body["company_names_used_as_join_keys"] is False
    assert all(row["historical_mapping_admitted"] is False for row in body["filing_roster"])
    assert all(value is False or type(value)is int and value==0 for value in body["authority"].values())
    assert all(row["original_capture_header_identity_bound"] is False for row in body["title_occurrences"])
    assert b"PRIVATE FIXTURE NAME" not in module._raw(body)


def test_interleaved_transaction_holding_and_unknown_children_have_real_per_tag_xml_paths(supplied):
    table=b"<nonDerivativeTable>"+_row()+b"<uninterpretedFixture/>"+_row(b"Class A",b"nonDerivativeHolding")+_row(b"Class B")+b"</nonDerivativeTable>"
    rows=payload(supplied,table=table,selected=1)["title_occurrences"]
    assert rows[0]["xml_occurrence_path"].endswith("/nonDerivativeTransaction[1]/securityTitle[1]/value")
    assert rows[1]["xml_occurrence_path"].endswith("/nonDerivativeHolding[1]/securityTitle[1]/value")
    assert rows[2]["xml_occurrence_path"].endswith("/nonDerivativeTransaction[2]/securityTitle[1]/value")
    assert all(row["xml_occurrence_path_kind"]=="exact_observed_singleton_title_value_node" for row in rows)


@pytest.mark.parametrize("fragment,kind,title_count,value_count",[
    (b"<nonDerivativeTransaction/>","attempted_refused_title_value_field_path",0,0),
    (b"<nonDerivativeTransaction><securityTitle/></nonDerivativeTransaction>","attempted_refused_title_value_field_path",1,0),
    (b"<nonDerivativeTransaction><securityTitle><value>A</value><value>B</value></securityTitle></nonDerivativeTransaction>","attempted_refused_title_value_field_path",1,2),
    (b"<nonDerivativeTransaction><securityTitle><value><nested>A</nested></value></securityTitle></nonDerivativeTransaction>","exact_observed_singleton_title_value_node",1,1)])
def test_xml_path_labels_never_represent_missing_or_ambiguous_values_as_observed_singletons(supplied,fragment,kind,title_count,value_count):
    body=payload(supplied,table=b"<nonDerivativeTable>"+fragment+b"</nonDerivativeTable>",selected=1)
    row=body["title_occurrences"][0]
    assert row["xml_occurrence_path_kind"]==kind
    assert row["security_title_child_count"]==title_count
    assert row["value_child_count"]==value_count
    assert row["xml_nonderivative_row_path"].endswith("/nonDerivativeTransaction[1]")


def test_seven_style_issuer_first_refusal_remains_accounted_without_title_extraction(supplied):
    body=payload(supplied,issuer_first=True)
    assert body["counts"]["selected_parents"]==2 and body["counts"]["genuine_view_parents"]==1
    assert body["counts"]["parser_refused_selected_parents"]==1
    assert body["parent_title_dispositions"][1]["source_parent_quarantine_code"]=="legacy_blank_separator_refused"
    assert body["parent_title_dispositions"][1]["title_occurrence_indices"]==[]
    assert len(body["filing_roster"])==6


def test_no_titles_are_an_explicit_parent_structural_observation_not_dropped_or_zero_trade(supplied):
    body=payload(supplied,table=b"")
    assert body["counts"]["genuine_view_parents"]==body["counts"]["genuine_parents_without_nonderivative_rows"]==2
    assert body["counts"]["title_occurrences"]==0 and len(body["parent_title_dispositions"])==2
    assert body["counts"]["source_filings"]==6


def test_exact_title_whitespace_case_duplicates_and_xml_escaping_are_not_class_matches(supplied):
    table=b"<nonDerivativeTable>"+_row(b"Common &amp; Stock")+_row(b" Common Stock ")+_row(b"common stock")+_row(b"Common &amp; Stock")+b"</nonDerivativeTable>"
    body=payload(supplied,table=table,selected=1)
    assert body["counts"]["title_occurrences"]==4 and body["counts"]["unique_cik_titles"]==3
    assert body["title_key_index"][0]["declared_title_decoded_text"]=="Common & Stock"
    assert body["title_key_index"][0]["title_occurrence_indices"]==[0,3]
    assert body["title_text_kind"]=="exact_decoded_XML_value_text_not_original_lexical_XML_byte_span"


@pytest.mark.parametrize("fragment,code", [(b"<nonDerivativeTransaction/>","security_title_missing"),
    (b"<nonDerivativeHolding><securityTitle/></nonDerivativeHolding>","security_title_value_missing"),
    (b"<nonDerivativeTransaction><securityTitle><value>A</value><value>B</value></securityTitle></nonDerivativeTransaction>","security_title_value_ambiguous"),
    (b"<nonDerivativeTransaction><securityTitle><value><nested>A</nested></value></securityTitle></nonDerivativeTransaction>","security_title_value_not_plain"),
    (b"<nonDerivativeTransaction><securityTitle>mixed<value>A</value></securityTitle></nonDerivativeTransaction>","security_title_mixed_content"),
    (_row(b"Common\nStock"),"security_title_text_controls")])
def test_unsupported_title_fields_are_retained_fixed_quarantines(supplied,fragment,code):
    body=payload(supplied,table=b"<nonDerivativeTable>"+fragment+b"</nonDerivativeTable>",selected=1)
    assert body["counts"]["quarantined_title_occurrences"]==1 and body["counts"]["unique_cik_titles"]==0
    assert code in body["title_occurrences"][0]["quarantine_reasons"]
    assert body["title_refusal_counts"][code]==1


def test_money_lexemes_and_derivative_titles_are_opaque_and_never_projected(supplied):
    sentinel=b"SECRET-OPAQUE-NOT-A-NUMBER"
    table=b"<nonDerivativeTable>"+_row(extra=b"<transactionAmounts><transactionShares><value>"+sentinel+b"</value></transactionShares></transactionAmounts>")+b"</nonDerivativeTable>"
    table+=b"<derivativeTable><derivativeTransaction><securityTitle><value>SECRET DERIVATIVE TITLE</value></securityTitle></derivativeTransaction></derivativeTable>"
    body=payload(supplied,table=table,selected=1);raw=module._raw(body)
    assert body["counts"]["plain_title_occurrences"]==1
    assert sentinel not in raw and b"SECRET DERIVATIVE TITLE" not in raw and b"transactionShares" not in raw


def test_all_tables_same_perma_are_one_group_and_global_competing_cik_is_retained(supplied):
    rows=[ticker_fixture.ticker(cik="123456"),ticker_fixture.ticker(cik="999999",table="fundamentals"),
        ticker_fixture.ticker(cik="123456"),ticker_fixture.ticker(cik="123456",name="different current record")]
    body=payload(supplied,tickers=rows)
    assert body["counts"]["current_permaticker_groups"]==body["counts"]["conflicted_current_permaticker_groups"]==1
    group=body["current_permaticker_groups"][0]
    assert group["current_cik_candidates"]==["0000123456","0000999999"] and group["competing_current_cik_candidates"] is True
    assert group["ticker_source_ordinals"]==[1,2,3,4]
    assert body["counts"]["duplicate_exact_ticker_rows"]==body["counts"]["conflicting_ticker_key_rows"]==1
    assert body["title_key_index"][0]["historical_share_class_admitted"] is False


def test_exact_duplicate_of_a_later_conflicting_variant_is_not_counted_as_a_new_variant(supplied):
    first=ticker_fixture.ticker(cik="123456",name="A")
    different=ticker_fixture.ticker(cik="123456",name="B")
    body=payload(supplied,tickers=[first,different,different,first])
    assert body["counts"]["ticker_rows"]==len(body["ticker_row_dispositions"])==4
    assert body["counts"]["duplicate_exact_ticker_rows"]==2
    assert body["counts"]["conflicting_ticker_key_rows"]==1
    assert "duplicate_exact_current_row" in body["ticker_row_dispositions"][2]["quarantine_reasons"]
    assert body["current_permaticker_groups"][0]["conflicting_primary_key"] is True
    assert body["count_semantics"]["conflicting_ticker_key_rows"]=="first_occurrence_of_each_additional_distinct_current_record_variant_per_exact_table_permaticker_ticker_key"


def test_nonsecurity_rows_can_reveal_global_perma_conflicts_but_cannot_create_title_links(supplied):
    rows=[ticker_fixture.ticker(cik="123456"),ticker_fixture.ticker(cik="999999",table="holdings_investor")]
    body=payload(supplied,tickers=rows)
    assert body["current_permaticker_groups"][0]["competing_current_cik_candidates"] is True
    assert body["current_permaticker_groups"][0]["ticker_source_ordinals"]==[1,2]
    assert body["current_cik_group_index"].get("0000999999",[])==[]
    assert body["current_cik_group_index"][body["title_key_index"][0]["issuer_cik"]]==[0]


def test_dense_current_relations_use_shared_cik_index_without_per_row_or_title_duplication(supplied):
    body=payload(supplied,tickers=[ticker_fixture.ticker(perma=str(i),cik="123456") for i in range(5)])
    assert body["current_cik_group_index"]["0000123456"]==[0,1,2,3,4]
    assert all("current_cik_group_indices" not in row and "current_cik_group_index_key" not in row
        for row in body["filing_roster"]+body["title_key_index"])
    assert body["current_group_semantics"]["all_table_sec_url_cik_claims_are_not_issuer_evidence"] is True
    assert body["current_group_semantics"]["historical_share_class_admitted"] is False
    assert all("historical_share_class_admitted" not in group and "same_security_alias_admitted" not in group
        for group in body["current_permaticker_groups"])


@pytest.mark.parametrize("changes,code",[({"ticker":"not a ticker"},"current_ticker_label_invalid"),
    ({"name":"Common\nStock"},"nonessential_name_control_characters"),
    ({"lastupdated":"2006-02-30"},"current_metadata_date_invalid"),
    ({"isdelisted":"unknown"},"current_delisting_flag_unknown")])
def test_current_context_quality_is_accounted_without_becoming_identity_join(supplied,changes,code):
    body=payload(supplied,tickers=[ticker_fixture.ticker(cik="123456",**changes)])
    assert body["counts"]["ticker_rows"]==body["counts"]["quarantined_ticker_rows"]==1
    assert code in body["ticker_row_dispositions"][0]["quarantine_reasons"]
    assert body["ticker_refusal_counts"][code]==1
    assert body["current_cik_group_index"][body["title_key_index"][0]["issuer_cik"]]==[0]
    assert body["title_key_index"][0]["historical_share_class_admitted"] is False


@pytest.mark.parametrize("body,code,count",[
    (b"<nonDerivativeHolding><securityTitle><value>A</value></securityTitle><securityTitle><value>A</value></securityTitle></nonDerivativeHolding>","security_title_ambiguous",2),
    (b"<nonDerivativeHolding><securityTitle extra='x'><value>A</value></securityTitle></nonDerivativeHolding>","security_title_attributes",1),
    (b"<nonDerivativeHolding><securityTitle><value extra='x'>A</value></securityTitle></nonDerivativeHolding>","security_title_value_not_plain",1),
    (b"<nonDerivativeHolding><securityTitle><unexpected/><value>A</value></securityTitle></nonDerivativeHolding>","security_title_unexpected_child",1),
    (b"<nonDerivativeHolding><securityTitle><value>A</value>outside</securityTitle></nonDerivativeHolding>","security_title_mixed_content",1),
    (_row(b"  "),"security_title_text_empty",1)])
def test_duplicate_or_attribute_mixed_title_fields_are_explicit_not_flattened(supplied,body,code,count):
    result=payload(supplied,table=b"<nonDerivativeTable>"+body+b"</nonDerivativeTable>",selected=1)
    assert result["counts"]["title_occurrences"]==result["counts"]["quarantined_title_occurrences"]==count
    assert result["title_refusal_counts"][code]==count
    assert result["counts"]["unique_cik_titles"]==0


def test_valid_footnote_reference_and_structural_whitespace_preserve_exact_plain_value(supplied):
    table=b"<nonDerivativeTable><nonDerivativeHolding><securityTitle>\n <value> Common Stock </value>\n <footnoteId id='F1'/>\n </securityTitle></nonDerivativeHolding></nonDerivativeTable>"
    result=payload(supplied,table=table,selected=1)
    assert result["counts"]["plain_title_occurrences"]==1
    assert result["title_occurrences"][0]["declared_title_decoded_text"]==" Common Stock "


def test_duplicate_nonderivative_tables_account_all_occurrences_as_ambiguous(supplied):
    table=b"<nonDerivativeTable>"+_row()+b"</nonDerivativeTable>"
    result=payload(supplied,table=table+table,selected=1)
    assert result["counts"]["nonderivative_rows_observed"]==result["counts"]["quarantined_title_occurrences"]==2
    assert result["title_refusal_counts"]["non_derivative_table_ambiguous"]==2


def test_company_name_relatedticker_label_and_case_cannot_supply_a_cik_link(supplied):
    rows=[ticker_fixture.ticker(cik="",name="Common Stock",relatedtickers="ABC",perma="same-name"),
        ticker_fixture.ticker(cik="999999",name="Common Stock",ticker="ABC",perma="same-label")]
    body=payload(supplied,tickers=rows)
    assert body["current_cik_group_index"].get(body["title_key_index"][0]["issuer_cik"],[])==[]
    assert body["counts"]["titles_without_current_cik_groups"]==1
    assert len(body["ticker_row_dispositions"])==2


def test_exact_observer_completion_flags_do_not_require_unemitted_pure_cohort_flags(supplied):
    args=arguments(supplied);body=json.loads(args["sharadar_complete_raw"])
    for flag in module.sharadar.FALSE_FLAGS:body.pop(flag,None)
    body.update(dict.fromkeys(OBSERVED_PRODUCER_FLAGS,False))
    raw=module._raw(body);args.update(sharadar_complete_raw=raw,expected_sharadar_complete_sha256=module._sha(raw))
    result=module.assess_sec_title_current_reference(**args).to_payload()
    assert result["counts"]["ticker_rows"]==4
    assert all(result["authority"][flag] is False for flag in OBSERVED_PRODUCER_FLAGS)


@pytest.mark.parametrize("change", ["assessment_hash","complete_hash","tickers_hash","manifest_hash","sharadar_hash",
    "fixture_type","actual_profile","fake_inventory","inventory_rebuilt"])
def test_external_input_pins_types_and_genuine_inventory_cannot_be_forged(supplied,change):
    args=arguments(supplied)
    keys={"assessment_hash":"expected_source_view_assessment_sha256","complete_hash":"expected_source_view_complete_sha256",
        "tickers_hash":"expected_tickers_projection_sha256","manifest_hash":"expected_capture_manifest_sha256","sharadar_hash":"expected_sharadar_complete_sha256"}
    if change in keys:args[keys[change]]="f"*64
    elif change=="fixture_type":args["fixture_only"]=1
    elif change=="actual_profile":args["fixture_only"]=False
    elif change=="fake_inventory":args["source_view_parent_inventory"]=args["source_view_parent_inventory"].to_payload()
    else:args["source_view_parent_inventory"]=replace(args["source_view_parent_inventory"])
    with pytest.raises(ValueError):module.assess_sec_title_current_reference(**args)


def test_source_roster_or_capture_context_cannot_change_under_consistent_rehashed_metadata(supplied):
    args=arguments(supplied);source=json.loads(args["source_view_assessment_raw"])
    source["rows"][0]["accession_number"]="9999999999-06-999999";source["rows_sha256"]=module._sha(module._raw(source["rows"]))
    raw=module._raw(source);complete=json.loads(args["source_view_complete_raw"])
    complete.update(assessment_sha256=module._sha(raw),assessment_bytes=len(raw))
    args.update(source_view_assessment_raw=raw,expected_source_view_assessment_sha256=module._sha(raw),
        source_view_complete_raw=module._raw(complete),expected_source_view_complete_sha256=module._sha(module._raw(complete)))
    with pytest.raises(module.SecTitleCurrentReferenceError,match="full_source_cohort_context_refused"):
        module.assess_sec_title_current_reference(**args)


@pytest.mark.parametrize("kind",["duplicate_ordinal","drop_ticker","extra_financial_field","receipt_bool_count","receipt_positive_rights"])
def test_tickers_all_row_accounting_schema_and_receipt_types_stay_bound(supplied,kind):
    args=arguments(supplied);body=json.loads(args["tickers_projection_raw"]);receipt=json.loads(args["sharadar_complete_raw"])
    if kind=="duplicate_ordinal":body["rows"][1]["source_row_ordinal"]=1
    elif kind=="drop_ticker":body["rows"].pop()
    elif kind=="extra_financial_field":body["rows"][0]["price"]=999
    elif kind=="receipt_bool_count":receipt["counts"]["source_ticker_rows"]=True
    else:receipt[OBSERVED_PRODUCER_FLAGS[0]]=True
    raw=module._raw(body);receipt["tickers_projection_sha256"]=module._sha(raw)
    args.update(tickers_projection_raw=raw,expected_tickers_projection_sha256=module._sha(raw),
        sharadar_complete_raw=module._raw(receipt),expected_sharadar_complete_sha256=module._sha(module._raw(receipt)))
    with pytest.raises(ValueError):module.assess_sec_title_current_reference(**args)


def test_result_seal_genuine_input_reparse_and_returned_dict_copy_cannot_grant_authority(supplied):
    args=arguments(supplied);result=module.assess_sec_title_current_reference(**args)
    changed=result.to_payload();changed["authority"]["backtest_ready"]=True
    assert result.to_payload()["authority"]["backtest_ready"] is False
    with pytest.raises(ValueError):replace(result).to_payload()
    projection=args["source_view_parent_inventory"].frozen_projections_for_v2()[0]
    object.__setattr__(projection,"xml_bytes",b"changed-child")
    with pytest.raises(ValueError):result.to_payload()


@pytest.mark.parametrize("cap",["MAX_TITLE_OCCURRENCES","MAX_TITLE_FIELD_BYTES","MAX_TITLE_TEXT_BYTES","MAX_RESULT_BYTES","MAX_CURRENT_GROUPS"])
def test_declared_profile_bounds_refuse_without_truncation(supplied,monkeypatch,cap):
    args=arguments(supplied);monkeypatch.setattr(module,cap,0)
    with pytest.raises(ValueError):module.assess_sec_title_current_reference(**args)


def test_pure_factory_does_not_read_files_processes_credentials_or_provider(supplied,monkeypatch):
    import os,subprocess
    args=arguments(supplied)
    def refused(*args,**kwargs):pytest.fail("pure factory attempted external interaction")
    monkeypatch.setattr(os,"open",refused);monkeypatch.setattr(subprocess,"run",refused)
    assert module.assess_sec_title_current_reference(**args).to_payload()["counts"]["source_filings"]==6


@pytest.mark.parametrize("fault",["roster_accession","header_admission","positive_authority","wrong_group_cik",
    "bool_count","coherent_count","unknown_refusal","changed_source_context","ticker_ordinal"])
def test_public_readback_validator_rederives_all_metadata_instead_of_trusting_self_hashes(supplied,fault):
    args=arguments(supplied);body=module.assess_sec_title_current_reference(**args).to_payload()
    if fault=="roster_accession":body["filing_roster"][0]["accession_number"]="9999999999-06-999999"
    elif fault=="header_admission":body["title_occurrences"][0]["original_capture_header_identity_bound"]=True
    elif fault=="positive_authority":body["authority"]["backtest_ready"]=True
    elif fault=="wrong_group_cik":body["current_permaticker_groups"][0]["current_cik_candidates"]=["0000000001"]
    elif fault=="bool_count":body["counts"]["conflicting_ticker_key_rows"]=False
    elif fault=="coherent_count":body["counts"]["plain_title_occurrences"]=1;body["counts"]["quarantined_title_occurrences"]=1
    elif fault=="unknown_refusal":body["title_refusal_counts"]["private source text"]=0
    elif fault=="changed_source_context":body["source_cohort_binding"]["ordered_source_row_identity_sha256"]="f"*64
    else:body["ticker_row_dispositions"][0]["source_row_ordinal"]=2
    body["filing_roster_sha256"]=module._sha(module._raw(body["filing_roster"]))
    with pytest.raises(module.SecTitleCurrentReferenceError,match="input_derived_title_reference_result_differs"):
        module.validate_sec_title_current_reference_payload(body,**args)


# Section 194 (Claude review): malformed completion shapes escaped as AttributeError/KeyError.
@pytest.mark.parametrize("fault", ["baseline_not_object", "capture_id_missing"])
def test_malformed_source_view_completion_is_a_typed_refusal(supplied, fault):
    args = arguments(supplied)
    complete = json.loads(args["source_view_complete_raw"])
    if fault == "baseline_not_object":complete["frozen_original_baseline"] = []
    else:del complete["capture_id"]
    raw = module._raw(complete)
    args.update(source_view_complete_raw=raw, expected_source_view_complete_sha256=module._sha(raw))
    with pytest.raises(module.SecTitleCurrentReferenceError, match="^observed_source_view_completion_binding_refused$"):
        module.assess_sec_title_current_reference(**args)


@pytest.mark.parametrize("fault", ["projection_not_object", "projection_null", "derived_view_not_object"])
def test_rehashed_malformed_projection_metadata_is_a_typed_adapter_refusal(supplied, fault):
    """Reach the inherited validator with genuine invented inputs and coherent hashes."""
    args = arguments(supplied)
    source = json.loads(args["source_view_assessment_raw"])
    parent = next(row for row in source["parent_qualification_ledger"] if row["projection_bridge"] is not None)
    if fault == "derived_view_not_object":
        parent["source_view"]["derived_sec_document_source_view"] = []
    else:
        parent["projection_bridge"]["frozen_source_view_projection"] = [] if fault == "projection_not_object" else None
    source["parent_qualification_ledger_sha256"] = module._sha(module._raw(source["parent_qualification_ledger"]))
    assessment_raw = module._raw(source)
    assessment_sha = module._sha(assessment_raw)
    complete = json.loads(args["source_view_complete_raw"])
    complete.update(assessment_sha256=assessment_sha, assessment_bytes=len(assessment_raw))
    complete_raw = module._raw(complete)
    args.update(source_view_assessment_raw=assessment_raw, expected_source_view_assessment_sha256=assessment_sha,
        source_view_complete_raw=complete_raw, expected_source_view_complete_sha256=module._sha(complete_raw))
    with pytest.raises(module.SecTitleCurrentReferenceError, match="^full_source_cohort_context_refused$"):
        module.assess_sec_title_current_reference(**args)
