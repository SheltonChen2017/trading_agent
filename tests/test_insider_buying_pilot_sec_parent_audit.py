"""Invented metadata-only streaming joins; no actual source or account reads."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_sec_parent_audit as m
from research import insider_buying_pilot_sec_roster as roster
from research.insider_buying.sec_quarter_master_index import parse_sec_quarter_master_index


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("invented_parent_audit_roster_fixture",
        Path(__file__).with_name("test_insider_buying_pilot_sec_roster.py"))
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    original = helper._zip
    def unique(period, changes=None):
        changes = {form:{"ACCESSION_NUMBER":f"0000000001-{int(period[:4])%100:02d}-{int(period[-1])*100+index:06d}"}
                   for index, form in enumerate(m.FORMS, start=1)}
        return original(period, changes)
    helper._zip = unique
    supplied = helper.corpus.__wrapped__(tmp_path_factory)
    rows = []
    result = roster.derive_pilot_sec_roster(**helper._args(supplied, rows.append))
    return helper, supplied, result, rows


def _exposure(rows=()):
    return {"schema":m.EXPOSURE_SCHEMA,"records":sorted(rows,key=lambda row:row["accession_number"])}


def _exposed(row, *states):
    return {"accession_number":row["accession_number"],"accession_key_sha256":row["accession_key_sha256"],
        "evidence":[{"root_id":"invented-root","journal_sha256":str(index)*64,"state":state}
                    for index,state in enumerate(states,start=1)]}


def _candidate(row, *, verified=True, issuer=None):
    target = {key:row[key] for key in ("accession_number","period","filing_date","form_type")}
    target["issuer_cik"] = row["raw_issuer_cik"] if issuer is None else issuer
    request = {**target,"archive_path":f"edgar/data/999/{row['accession_number']}.txt"}
    request["url"] = "https://www.sec.gov/Archives/"+request["archive_path"]
    return {"root_id":"invented-root","control_name":"run/request-000-result.json","control_sha256":"a"*64,
        "request_sha256":m._sha(m._raw(request)),"request":request,"request_url":request["url"],
        "retained_target":target,"raw_object":{"relative_path":"run/objects/body.bin","sha256":"b"*64,"size_bytes":123},
        "body_currently_hash_verified":verified,"complete_parent_parsed_here":False}


def _candidates(records=()):
    return {"schema":m.CANDIDATE_SCHEMA,"fixture_only":True,
        "records":sorted(records,key=lambda row:row["accession_number"]),"masters":[],"authority":dict(m._AUTHORITY)}


def _compiler(*, exposures=None,candidates=None,**kwargs):
    raw = m._raw(exposures or _exposure());candidate_raw = m._raw(candidates or _candidates())
    return m.PilotSecParentAuditCompiler(exposure_raw=raw,expected_exposure_sha256=m._sha(raw),
        candidates_raw=candidate_raw,expected_candidates_sha256=m._sha(candidate_raw),**kwargs)


def _master(period,rows,*,alias=None,wrong=None,omit=False):
    header = b"Description: Master Index of EDGAR Dissemination Feed\n\nCIK|Company Name|Form Type|Date Filed|Filename\n--------------------------------------------------------------------------------\n"
    lines = []
    for row in rows:
        if row["period"] != period or row["form_type"] not in {"4","4/A"} or omit:continue
        form,filed = row["form_type"],row["filing_date"]
        if wrong == "form":form = "4/A" if form == "4" else "4"
        if wrong == "date":filed = filed[:-2]+"02"
        folders = ["999"] if alias is None else alias
        for folder in folders:
            lines.append(f"1|INVENTED|{form}|{filed}|edgar/data/{folder}/{row['accession_number']}.txt\n".encode())
    if not lines:
        lines.append(f"1|INVENTED|8-K|{period[:4]}-{(int(period[-1])-1)*3+1:02d}-01|edgar/data/1/0000000001-{int(period[:4])%100:02d}-999999.txt\n".encode())
    return parse_sec_quarter_master_index(header+b"".join(lines),year=int(period[:4]),quarter=int(period[-1]))


def _run(corpus,compiler):
    helper,supplied,_,_ = corpus
    generated = roster.derive_pilot_sec_roster(**helper._args(supplied,compiler.consume))
    return compiler.finish(generated)


def test_complete_roster_all_six_forms_and_full_hashes_without_fabricated_locators(corpus):
    emitted = [];value = _run(corpus,_compiler(emit_row=emitted.append,maximum_preview=2));body = value.to_payload()
    assert body["context_counts"]["source_filings"] == 150
    assert body["context_counts"]["target_filings"] == 50 and body["context_counts"]["context_filings"] == 100
    assert body["pilot_counts"]["target_filings"] == 40
    assert body["context_counts"]["fresh_locatable_candidate_requests"] == 0
    assert body["context_counts"]["no_prior_dispatch_observed_targets"] == 50
    assert body["context_counts"]["locator_quarantined_targets"] == 50
    assert len(emitted) == 150 and len(body["quarters"]) == 25
    assert body["disposition_jsonl_sha256"] == m._sha(b"".join(m._raw(row)+b"\n" for row in emitted))
    assert body["source_row_jsonl_sha256"] == corpus[2].to_payload()["source_row_jsonl_sha256"]
    assert body["fresh_request_jsonl_sha256"] == m._sha(b"") and body["fresh_request_preview"] == []
    assert all(row["request"] is None and row["pre_normalization_target"] is None for row in emitted)
    assert all(row["dispatch_authorized"] is False and row["canonical_admitted"] is False for row in emitted)
    assert body["authority"] == m._AUTHORITY and body["full_parent_bodies_opened_here"] == 0
    assert body["native_sid_required_for_accession_custody"] is False


def test_genuine_master_paths_raw_cik_pre_normalization_full_queue_and_bounded_preview(corpus):
    rows = corpus[3];emitted = [];calls = []
    def master(period):calls.append(period);return _master(period,rows)
    body = _run(corpus,_compiler(master_for_period=master,emit_row=emitted.append,maximum_preview=2)).to_payload()
    assert calls == list(m.PERIODS)
    assert body["context_counts"]["fresh_locatable_candidate_requests"] == 50 and len(body["fresh_request_preview"]) == 2
    queue = b"".join(m._raw(row["request"])+b"\n" for row in emitted if row["fresh_locatable_candidate"])
    assert body["fresh_request_jsonl_sha256"] == m._sha(queue) and body["fresh_request_jsonl_bytes"] == len(queue)
    short = next(row for row in emitted if row["source"]["period"] == "2021Q1" and row["source"]["form_type"] == "4")
    assert short["source"]["raw_issuer_cik"] == short["request"]["issuer_cik"] == short["pre_normalization_target"]["issuer_cik"] == "123"
    assert short["request"]["archive_path"].startswith("edgar/data/999/")
    assert short["request_sha256"] == m._sha(m._raw(short["request"]))
    assert short["pre_normalization_target"]["complete_submission_url"] == short["request"]["url"]


@pytest.mark.parametrize("state",sorted(m._STATES))
def test_every_consumed_state_suppresses_even_with_no_valid_body(corpus,state):
    row = next(row for row in corpus[3] if row["form_type"] == "4");emitted = []
    compiler = _compiler(exposures=_exposure([_exposed(row,state)]),master_for_period=lambda p:_master(p,corpus[3]),emit_row=emitted.append)
    body = _run(corpus,compiler).to_payload();target = next(value for value in emitted if value["source"]["accession_number"] == row["accession_number"])
    assert body["context_counts"]["prior_consumed_targets"] == 1 and body["context_counts"]["fresh_locatable_candidate_requests"] == 49
    assert target["prior_consumed"] is True and target["fresh_locatable_candidate"] is False
    assert target["disposition"] == "prior_consumed_without_matching_hash_verified_body_candidate"


def test_separate_diagnostic_body_does_not_erase_ambiguous_start_and_cross_profile_hash(corpus):
    row = next(row for row in corpus[3] if row["form_type"] == "4");candidate = _candidate(row);emitted = []
    compiler = _compiler(exposures=_exposure([_exposed(row,"ambiguous","completed")]),
        candidates=_candidates([{"accession_number":row["accession_number"],"candidates":[candidate]}]),
        master_for_period=lambda p:_master(p,corpus[3]),emit_row=emitted.append)
    body = _run(corpus,compiler).to_payload();target = next(value for value in emitted if value["source"]["accession_number"] == row["accession_number"])
    assert target["historical_ambiguous_start_preserved"] is True and target["fresh_locatable_candidate"] is False
    assert target["matching_retained_candidates"][0]["request_sha256"] == candidate["request_sha256"] != target["request_sha256"]
    assert body["context_counts"]["ambiguous_consumption_targets"] == body["context_counts"]["hash_verified_matching_body_candidate_targets"] == 1
    assert body["separate_diagnostic_does_not_resolve_original_ambiguous_start"] is True


@pytest.mark.parametrize("verified,issuer,matched",[(False,None,True),(True,"2",False)])
def test_unverified_or_conflicting_body_never_promotes_reuse_or_releases_consumption(corpus,verified,issuer,matched):
    row = next(row for row in corpus[3] if row["form_type"] == "4");emitted = [];candidate = _candidate(row,verified=verified,issuer=issuer)
    body = _run(corpus,_compiler(exposures=_exposure([_exposed(row,"refused")]),
        candidates=_candidates([{"accession_number":row["accession_number"],"candidates":[candidate]}]),
        master_for_period=lambda p:_master(p,corpus[3]),emit_row=emitted.append)).to_payload()
    target = next(value for value in emitted if value["source"]["accession_number"] == row["accession_number"])
    assert bool(target["matching_retained_candidates"]) is matched
    assert target["fresh_locatable_candidate"] is False
    assert body["context_counts"]["hash_verified_matching_body_candidate_targets"] == 0
    assert body["context_counts"]["consumed_without_matching_verified_body_candidate_targets"] == 1


@pytest.mark.parametrize("aliases,qualified",[(None,True),(["999","1"],True),(["999","998"],False)])
def test_master_aliases_require_unique_path_or_only_issuer_folder(corpus,aliases,qualified):
    row = next(row for row in corpus[3] if row["form_type"] == "4");output = []
    compiler = _compiler(master_for_period=lambda p:_master(p,corpus[3],alias=aliases),emit_row=output.append)
    _run(corpus,compiler)
    target = next(value for value in output if value["source"]["accession_number"] == row["accession_number"])
    assert target["fresh_locatable_candidate"] is qualified
    if aliases == ["999","1"]:assert target["selected_locator"]["archive_path"].startswith("edgar/data/1/")


@pytest.mark.parametrize("wrong",["form","date"])
def test_master_target_disagreement_is_quarantined_not_rewritten(corpus,wrong):
    body = _run(corpus,_compiler(master_for_period=lambda p:_master(p,corpus[3],wrong=wrong))).to_payload()
    assert body["context_counts"]["locator_quarantined_targets"] == 50
    assert body["context_counts"]["fresh_locatable_candidate_requests"] == 0


@pytest.mark.parametrize("field,value",[("source_record_ordinal",True),("source_record_ordinal",2),("form_type","8-K"),
    ("period","2019Q4"),("raw_issuer_cik","0"),("issuer_comparison_key","1"),("short_cik",1),
    ("raw_filing_date","tomorrow"),("raw_symbol_label","A\nB"),("accession_year_mismatch",True),
    ("quarterly_zip_sha256","bad"),("filing_metadata_sha256","0"*64)])
def test_source_guard_failures_poison_compiler_and_cannot_be_skipped(corpus,field,value):
    row = deepcopy(corpus[3][0]);row[field] = value
    if field != "filing_metadata_sha256":row["filing_metadata_sha256"] = m._sha(m._raw({k:v for k,v in row.items() if k != "filing_metadata_sha256"}))
    compiler = _compiler()
    with pytest.raises(m.PilotSecParentAuditError):compiler.consume(row)
    with pytest.raises(m.PilotSecParentAuditError,match="not_active"):compiler.consume(corpus[3][0])
    with pytest.raises(m.PilotSecParentAuditError,match="not_active"):compiler.finish(corpus[2])


def test_cross_quarter_occurrences_are_all_retained_and_later_target_not_queued(corpus):
    helper,supplied,_,rows = corpus
    first = next(row for row in rows if row["period"] == "2020Q1" and row["form_type"] == "4")
    changed = helper._changed(supplied,"2020Q2",lambda raw:helper._fields(raw,3,"ACCESSION_NUMBER",first["accession_number"]))
    all_rows = [];generated = roster.derive_pilot_sec_roster(**helper._args(changed,all_rows.append))
    output = [];compiler = _compiler(master_for_period=lambda p:_master(p,all_rows),emit_row=output.append)
    for row in all_rows:compiler.consume(row)
    body = compiler.finish(generated).to_payload()
    assert body["context_counts"]["source_filings"] == 150
    assert body["context_counts"]["cross_quarter_repeat_filings"] == body["context_counts"]["cross_quarter_repeat_targets"] == 1
    assert body["context_counts"]["fresh_locatable_candidate_requests"] == 49
    assert body["candidate_queue_requires_cross_quarter_repeat_reconciliation"] is True
    repeated = next(row for row in output if row["cross_quarter_accession_repeat"])
    assert repeated["source"]["period"] == "2020Q2" and repeated["prior_source_occurrence"]["period"] == "2020Q1"
    assert repeated["cross_quarter_source_identity_conflict"] is True and repeated["fresh_locatable_candidate"] is False


def test_within_quarter_duplicate_still_refuses_invalid_source_roster(corpus):
    compiler = _compiler();compiler.consume(corpus[3][0]);row = deepcopy(corpus[3][1])
    row["accession_number"] = corpus[3][0]["accession_number"];row["accession_key_sha256"] = corpus[3][0]["accession_key_sha256"]
    row["filing_metadata_sha256"] = m._sha(m._raw({k:v for k,v in row.items() if k != "filing_metadata_sha256"}))
    with pytest.raises(m.PilotSecParentAuditError,match="within_quarter_duplicate"):compiler.consume(row)


@pytest.mark.parametrize("fault",["exposure_hash","candidate_hash","request_hash","target_conflict","unsafe_path","false_authority","no_exposure","duplicate_evidence"])
def test_exact_external_inventory_bindings_and_descriptor_security(corpus,fault):
    row = next(row for row in corpus[3] if row["form_type"] == "4");candidate = _candidate(row)
    exposed = _exposure([_exposed(row,"started")]);candidates = _candidates([{"accession_number":row["accession_number"],"candidates":[candidate]}])
    if fault == "request_hash":candidate["request_sha256"] = "0"*64
    if fault == "target_conflict":candidate["request"]["issuer_cik"] = "2";candidate["request_sha256"] = m._sha(m._raw(candidate["request"]))
    if fault == "unsafe_path":candidate["raw_object"]["relative_path"] = "../body.bin"
    if fault == "false_authority":candidates["authority"]["backtest_authorized"] = True
    if fault == "no_exposure":exposed = _exposure()
    if fault == "duplicate_evidence":candidates["records"][0]["candidates"].append(deepcopy(candidate))
    raw,other = m._raw(exposed),m._raw(candidates)
    with pytest.raises(m.PilotSecParentAuditError):
        m.PilotSecParentAuditCompiler(exposure_raw=raw,expected_exposure_sha256="0"*64 if fault == "exposure_hash" else m._sha(raw),
            candidates_raw=other,expected_candidates_sha256="0"*64 if fault == "candidate_hash" else m._sha(other))


def test_callbacks_are_detached_and_callback_failure_precludes_completed_audit(corpus):
    def mutate(row):row["source"]["raw_issuer_cik"] = "999";row["dispatch_authorized"] = True
    body = _run(corpus,_compiler(master_for_period=lambda p:_master(p,corpus[3]),emit_row=mutate)).to_payload()
    assert body["context_counts"]["source_filings"] == 150 and body["authority"] == m._AUTHORITY
    def refuse(_):raise RuntimeError("invented private callback refusal")
    compiler = _compiler(emit_row=refuse)
    with pytest.raises(RuntimeError):compiler.consume(corpus[3][0])
    with pytest.raises(m.PilotSecParentAuditError,match="not_active"):compiler.finish(corpus[2])


def test_partial_stream_wrong_roster_and_finish_twice_refuse(corpus):
    compiler = _compiler();compiler.consume(corpus[3][0])
    with pytest.raises(m.PilotSecParentAuditError,match="roster_mismatch"):compiler.finish(corpus[2])
    compiler = _compiler();result = _run(corpus,compiler)
    with pytest.raises(m.PilotSecParentAuditError,match="not_active"):compiler.finish(corpus[2])
    with pytest.raises(m.PilotSecParentAuditError):m.validate_pilot_sec_parent_audit(replace(result))
    payload = result.to_payload();payload["authority"]["backtest_authorized"] = True
    assert result.to_payload()["authority"]["backtest_authorized"] is False
    with pytest.raises(m.PilotSecParentAuditError):m.validate_pilot_sec_parent_audit(type("Fake",(),{"to_payload":result.to_payload})())


def test_master_metadata_is_revalidated_at_quarter_transition(corpus):
    receipt = _master("2020Q1",corpus[3]);compiler = _compiler(master_for_period=lambda p:receipt if p == "2020Q1" else _master(p,corpus[3]))
    for row in corpus[3][:6]:compiler.consume(row)
    object.__setattr__(receipt,"source_sha256","0"*64)
    with pytest.raises(m.PilotSecParentAuditError,match="master_receipt_changed"):compiler.consume(corpus[3][6])


@pytest.mark.parametrize("field",["source_record_ordinal","quarterly_zip_sha256","submission_member_sha256",
    "submission_header_line_sha256","schema_profile_sha256","filing_metadata_sha256"])
def test_available_original_record_anchors_must_match_not_just_accession(corpus,field):
    row = next(row for row in corpus[3] if row["form_type"] == "4");candidate = _candidate(row);output = []
    candidate["request"][field] = row[field]+1 if type(row[field]) is int else "0"*64
    candidate["request_sha256"] = m._sha(m._raw(candidate["request"]))
    body = _run(corpus,_compiler(exposures=_exposure([_exposed(row,"completed")]),
        candidates=_candidates([{"accession_number":row["accession_number"],"candidates":[candidate]}]),
        master_for_period=lambda p:_master(p,corpus[3]),emit_row=output.append)).to_payload()
    target = next(item for item in output if item["source"]["accession_number"] == row["accession_number"])
    assert target["candidate_identity_conflicts"] == [candidate] and target["matching_retained_candidates"] == []
    assert not target["fresh_locatable_candidate"] and body["context_counts"]["hash_verified_matching_body_candidate_targets"] == 0


def test_conflicting_body_identities_are_retained_but_not_chosen_for_reuse(corpus):
    row = next(row for row in corpus[3] if row["form_type"] == "4");one = _candidate(row);two = deepcopy(one);output = []
    two["control_name"] = "other/request-result.json";two["control_sha256"] = "c"*64
    two["raw_object"]["sha256"] = "d"*64
    body = _run(corpus,_compiler(exposures=_exposure([_exposed(row,"completed")]),
        candidates=_candidates([{"accession_number":row["accession_number"],"candidates":[one,two]}]),
        master_for_period=lambda p:_master(p,corpus[3]),emit_row=output.append)).to_payload()
    target = next(item for item in output if item["source"]["accession_number"] == row["accession_number"])
    assert target["retained_candidate_body_identity_conflict"] is True and len(target["matching_retained_candidates"]) == 2
    assert target["fresh_locatable_candidate"] is False
    assert body["context_counts"]["candidate_body_identity_conflict_targets"] == 1
    assert body["context_counts"]["hash_verified_matching_body_candidate_targets"] == 0


def test_coherent_changed_source_row_cannot_bind_original_roster(corpus):
    compiler = _compiler()
    for index,supplied in enumerate(corpus[3]):
        row = deepcopy(supplied)
        if index == 0:
            row["raw_symbol_label"] = "DIFFERENT-INVENTED-LABEL"
            row["filing_metadata_sha256"] = m._sha(m._raw({key:value for key,value in row.items() if key != "filing_metadata_sha256"}))
        compiler.consume(row)
    with pytest.raises(m.PilotSecParentAuditError,match="source_stream_roster_mismatch"):compiler.finish(corpus[2])


@pytest.mark.parametrize("value",[1.25,"PRIVATE-NOT-A-REQUEST-FIELD"])
def test_unknown_or_financial_request_fields_fail_closed(corpus,value):
    row = next(row for row in corpus[3] if row["form_type"] == "4");candidate = _candidate(row)
    candidate["request"]["price"] = value;candidate["request_sha256"] = m._sha(m._raw(candidate["request"]))
    with pytest.raises(m.PilotSecParentAuditError):_compiler(exposures=_exposure([_exposed(row,"completed")]),
        candidates=_candidates([{"accession_number":row["accession_number"],"candidates":[candidate]}]))
