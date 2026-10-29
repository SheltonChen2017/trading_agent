"""Invented genuine25-quarter source scans; no retained inputs or provider IO."""
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import re
import zipfile

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_nc_source_binding_v1 as m

CONTACT="invented-binder@unit.test"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec=importlib.util.spec_from_file_location("invented_nc_binding_roster_fixture",Path(__file__).with_name("test_insider_buying_pilot_sec_roster.py"))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);original=helper._zip
    def unique(period,changes=None):
        fields={form:{"ACCESSION_NUMBER":f"0000000001-{int(period[:4])%100:02d}-{int(period[-1])*100000+i:06d}"}
            for i,form in enumerate(m.roster.FORMS,1)}
        for form,changed in (changes or {}).items():fields.setdefault(form,{}).update(changed)
        return original(period,fields)
    helper._zip=unique;supplied=helper.corpus.__wrapped__(tmp_path_factory);rows=[]
    genuine=m.roster.derive_pilot_sec_roster(**helper._args(supplied,rows.append))
    return helper,supplied,genuine,rows


def _row(corpus,period="2021Q1",form="4"):
    return next(row for row in corpus[3] if row["period"]==period and row["form_type"]==form)


def _payload(row,*,accession=None,form=None,filed=None,extra=b""):
    form=row["form_type"] if form is None else form;filed=row["filing_date"] if filed is None else filed
    accession=row["accession_number"] if accession is None else accession
    return (f"<SUBMISSION>\n<ACCESSION-NUMBER>{accession}\n<TYPE>{form}\n<PUBLIC-DOCUMENT-COUNT>1\n<FILING-DATE>{filed.replace('-','')}\n".encode()+extra+
        b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>PRIVATE NC ISSUER NOT VALIDATED\n<CIK>999999\n</COMPANY-DATA>\n</ISSUER>\n"+
        f"<DOCUMENT>\n<TYPE>{form}\n<SEQUENCE>1\n<FILENAME>private-original.xml\n<TEXT>\n".encode()+
        b"<ownershipDocument><opaque>PRIVATE BODY NEVER PROJECTED</opaque></ownershipDocument>\n</TEXT>\n</DOCUMENT>\n</SUBMISSION>\n")


def _batch(payloads,consumed=frozenset()):
    return m.route.assess_nc_route_batch(tuple(payloads),consumed_accessions=consumed,privacy_contact=CONTACT,fixture_only=True)


def _args(corpus,batch=None,*,supplied=None,consumed=frozenset()):
    helper,original,_,_=corpus;arguments=helper._args(original if supplied is None else supplied);arguments.pop("consume_row")
    return {**arguments,"route_batch":_batch((_payload(_row(corpus)),),consumed) if batch is None else batch,"consumed_accessions":consumed}


def test_genuine_full25_conservation_private_raw17_and_warmup_not_entry_scope(corpus):
    selected=[_row(corpus,"2020Q4"),_row(corpus),_row(corpus,"2025Q4","4/A"),_row(corpus,"2020Q1"),_row(corpus,form="3")]
    raws=tuple(_payload(row) for row in selected)+(_payload(selected[0],accession="9999999999-20-999999"),)
    result=m.bind_nc_routes_to_source17(**_args(corpus,_batch(raws)));w=result.public_witness();private=result.private_bindings()
    assert m.validate_nc_source_binding(result) is result
    assert w["source_population_counts"]["context_quarters"]==25 and w["source_population_counts"]["pilot_quarters"]==20
    assert w["source_population_counts"]["context_submission_rows"]==150 and w["context_form_counts"]==dict.fromkeys(m.roster.FORMS,25)
    assert w["required_parent_source_window"]=="2020Q4..2025Q4" and w["entry_pilot_window"]=="2021Q1..2025Q4"
    assert w["private_source17_candidate_count"]==3 and w["eligible_join_count"]==6
    assert w["eligible_join_disposition_counts"]=={"private_lexical_source17_candidate_not_admitted":3,
        "outside_required_parent_source_window":1,"context_non4_form_not_parent_candidate":1,"source_accession_unmatched":1}
    assert w["all_input_NC_members_accounted"] is True and w["source_accounting"]["source_rows_accounted"]==150
    assert private[1]["source_rows"]==(selected[1],)
    assert private[1]["source_rows"][0]["raw_issuer_cik"]=="123" and private[1]["source_rows"][0]["issuer_comparison_key"]=="0000000123"
    assert private[1]["route_claim"].payload_bytes() is raws[1] and private[1]["issuer_or_owner_identity_checked"] is False
    assert all(v is False or type(v) is int and v==0 for v in w["authority"].values())
    text=m._raw(w)+repr(result).encode()
    for secret in (CONTACT,"INVENTED",selected[1]["accession_number"],selected[1]["filing_metadata_sha256"],"999999","PRIVATE BODY"):
        assert secret.encode() not in text
    private[1]["source_rows"][0]["raw_issuer_cik"]="999";w["authority"]["backtesting_ready"]=True
    assert result.private_bindings()[1]["source_rows"][0]==selected[1] and result.public_witness()["authority"]["backtesting_ready"] is False


@pytest.mark.parametrize("change",["form","date"])
def test_internal_form_date_mismatch_never_becomes_parent_or_issuer_match(corpus,change):
    row=_row(corpus);raw=_payload(row,**({"form":"4/A"} if change=="form" else {"filed":"2021-01-02"}))
    value=m.bind_nc_routes_to_source17(**_args(corpus,_batch((raw,))))
    assert value.public_witness()["eligible_join_disposition_counts"]=={"source_form_or_filing_date_mismatch":1}
    assert value.private_bindings()[0]["source_rows"]==(row,) and value.public_witness()["private_source17_candidate_count"]==0


def test_later_source_repeat_conflict_invalidates_earlier_candidate_and_preserves_both_rows(corpus):
    helper,supplied,_,_=corpus;first=_row(corpus,"2020Q4")
    changed=helper._changed(supplied,"2025Q4",lambda raw:helper._fields(raw,3,"ACCESSION_NUMBER",first["accession_number"]))
    # The old helper changes physical/source hashes, not independent selector
    # census accounting. Re-derive that entire fixture receipt from the images.
    manifest,images,_=changed;pure=m.roster.selector.pure;bindings=pure.census._manifest_bindings(manifest)
    profile=pure.build_retained_82q_schema_profile_candidate()
    census=pure._census_receipt(tuple(pure.census._census_quarter(image.raw_bytes,binding)
        for image,binding in zip(images,bindings,strict=True)),m._sha(manifest),len(manifest),True)
    headers=pure._header_receipt(tuple(pure.headers._quarter_headers(image.raw_bytes,image.period,profile)
        for image in images),census.sha256,True)
    selected=pure.select_affected_quarters(intake_manifest_raw=manifest,expected_manifest_sha256=m._sha(manifest),
        quarter_inputs=iter(images),expected_census_sha256=census.sha256,expected_header_preflight_sha256=headers.sha256,
        fixture_only=True).to_payload();selected["fixture_only"]=False
    changed=manifest,images,selected
    value=m.bind_nc_routes_to_source17(**_args(corpus,_batch((_payload(first),)),supplied=changed));w=value.public_witness()
    assert w["eligible_join_disposition_counts"]=={"source_cross_quarter_identity_conflict_quarantined":1}
    assert w["source_accounting"]["cross_quarter_repeat_occurrences"]==1
    assert w["source_accounting"]["cross_quarter_identity_conflict_accessions"]==1
    rows=value.private_bindings()[0]["source_rows"]
    assert [row["period"] for row in rows]==["2020Q4","2025Q4"] and rows[1]["accession_year_mismatch"] is True
    assert w["private_source17_candidate_count"]==0


@pytest.mark.parametrize("kind",["consumed","duplicate","unknown"])
def test_genuine_batch_quarantines_accounted_without_releasing_consumed_or_resolving_status(corpus,kind):
    row=_row(corpus);consumed=frozenset({row["accession_number"]}) if kind=="consumed" else frozenset()
    raw=_payload(row,extra=b"<UNKNOWN>opaque\n" if kind=="unknown" else b"")
    batch=_batch((raw,raw) if kind=="duplicate" else (raw,),consumed)
    value=m.bind_nc_routes_to_source17(**_args(corpus,batch,consumed=consumed));w=value.public_witness()
    assert w["eligible_join_count"]==0 and w["route_batch_quarantined_members"]==w["route_batch"]["members"]
    assert w["all_input_NC_members_accounted"] is True and value.private_bindings()==()
    assert w["source_accounting"]["rows_without_eligible_route_accessions"]==150
    if kind=="consumed":assert w["source_accounting"]["caller_consumed_accessions"]==1


def test_different_consumed_set_refuses_before_source_materialization(corpus):
    args=_args(corpus);args["consumed_accessions"]=frozenset({_row(corpus)["accession_number"]})
    def forbidden():pytest.fail("source iterator reached before consumption-scope check");yield
    args["quarter_inputs"]=forbidden()
    with pytest.raises(m.NCSourceBindingError,match="same_caller_consumed_set_required"):m.bind_nc_routes_to_source17(**args)


def test_source_financial_member_bodies_never_open(corpus,monkeypatch):
    original=zipfile.ZipFile.open
    def guarded(self,name,*args,**kwargs):
        assert (name.filename if hasattr(name,"filename") else name)=="SUBMISSION.tsv"
        return original(self,name,*args,**kwargs)
    monkeypatch.setattr(zipfile.ZipFile,"open",guarded)
    assert m.bind_nc_routes_to_source17(**_args(corpus)).public_witness()["private_source17_candidate_count"]==1


@pytest.mark.parametrize("fault",["manifest_hash","selection_hash","list","missing","extra","reorder","fixture_alias","fixture_mismatch","fake_batch"])
def test_no_caller_asserted_complete_scope_or_untyped_route_batch(corpus,fault):
    args=_args(corpus);items=list(args["quarter_inputs"]);args["quarter_inputs"]=iter(items)
    if fault=="manifest_hash":args["expected_manifest_sha256"]="f"*64
    elif fault=="selection_hash":args["expected_selection_sha256"]="f"*64
    elif fault=="list":args["quarter_inputs"]=items
    elif fault=="missing":args["quarter_inputs"]=iter(items[:-1])
    elif fault=="extra":args["quarter_inputs"]=iter(items+[items[-1]])
    elif fault=="reorder":args["quarter_inputs"]=iter([items[1],items[0],*items[2:]])
    elif fault=="fixture_alias":args["fixture_only"]=1
    elif fault=="fixture_mismatch":args["fixture_only"]=False
    else:args["route_batch"]=args["route_batch"].public_witness()
    with pytest.raises(ValueError):m.bind_nc_routes_to_source17(**args)


@pytest.mark.parametrize("name,cap,code",[("MAX_SOURCE_ROWS",1,"source_population_row_bound_refused"),
    ("MAX_SOURCE_ROW_JSONL_BYTES",1,"source_population_byte_bound_refused"),
    ("MAX_PRIVATE_SOURCE_BYTES",1,"private_source_storage_bound_refused"),("MAX_ROUTE_CLAIMS",0,"bounded_genuine_route_claims_required")])
def test_finite_bounds_before_storage_or_completion(corpus,monkeypatch,name,cap,code):
    monkeypatch.setattr(m,name,cap)
    with pytest.raises(m.NCSourceBindingError,match=code):m.bind_nc_routes_to_source17(**_args(corpus))


def test_genuine_roster_receipt_without_this_call_callbacks_is_not_complete_proof(corpus,monkeypatch):
    monkeypatch.setattr(m.roster,"derive_pilot_sec_roster",lambda **kwargs:corpus[2])
    with pytest.raises(m.NCSourceBindingError,match="complete_source_callback_accounting_refused"):
        m.bind_nc_routes_to_source17(**_args(corpus))


def test_unchanged_roster_callback_last_row_cannot_silently_disappear(corpus,monkeypatch):
    original=m.roster.derive_pilot_sec_roster
    def missing(**kwargs):
        consume=kwargs["consume_row"]
        kwargs["consume_row"]=lambda row:None if row["period"]=="2026Q1" and row["source_record_ordinal"]==6 else consume(row)
        return original(**kwargs)
    monkeypatch.setattr(m.roster,"derive_pilot_sec_roster",missing)
    with pytest.raises(m.NCSourceBindingError,match="complete_source_callback_accounting_refused"):
        m.bind_nc_routes_to_source17(**_args(corpus))


@pytest.mark.parametrize("field",["_stats","_public","_records","_token"])
def test_private_seal_and_exact_types_cannot_be_reconstructed_or_mutated(corpus,field):
    value=m.bind_nc_routes_to_source17(**_args(corpus));original=getattr(value,field)
    forged=replace(value)
    with pytest.raises(m.NCSourceBindingError):m.validate_nc_source_binding(forged)
    changed=bytearray(original) if field in {"_stats","_public"} else () if field=="_records" else object()
    try:
        object.__setattr__(value,field,changed)
        with pytest.raises(m.NCSourceBindingError):value.public_witness()
    finally:object.__setattr__(value,field,original)
    assert m.validate_nc_source_binding(value) is value


def test_mutated_child_route_is_not_reused_after_source_scan(corpus,monkeypatch):
    args=_args(corpus);claim=args["route_batch"].eligible_claims()[0][1];original=claim.form_type
    real=m.roster.derive_pilot_sec_roster
    def changed(**kwargs):
        result=real(**kwargs);object.__setattr__(claim,"form_type","4/A");return result
    monkeypatch.setattr(m.roster,"derive_pilot_sec_roster",changed)
    try:
        with pytest.raises(ValueError):m.bind_nc_routes_to_source17(**args)
    finally:object.__setattr__(claim,"form_type",original)


def test_code_pins_are_exact_sha256_declarations_not_malformed_metadata():
    assert all(re.fullmatch(r"[0-9a-f]{64}",digest) for digest in m.CODE_PINS.values())
    assert m.CODE_PINS[m.route.REVIEW_TEST_PATH]=="b76815992a26b3f5c4816213a70c8ee21590ad09296692e7d3fc137402e070c0"


def test_private_record_index_bool_alias_cannot_pass_immutable_snapshot(corpus):
    batch=_batch((_payload(_row(corpus)),_payload(_row(corpus,"2021Q2"))))
    value=m.bind_nc_routes_to_source17(**_args(corpus,batch));original=value._records
    assert original[1][0]==1
    try:
        object.__setattr__(value,"_records",(original[0],(True,*original[1][1:])))
        with pytest.raises(m.NCSourceBindingError):m.validate_nc_source_binding(value)
    finally:object.__setattr__(value,"_records",original)
    assert m.validate_nc_source_binding(value) is value


@pytest.mark.parametrize("error_type",[RuntimeError,OSError])
def test_foreign_source_iterator_detail_cannot_escape_finite_derivation_boundary(corpus,error_type):
    args=_args(corpus)
    def foreign():
        raise error_type("PRIVATE SOURCE ITERATOR DETAIL MUST NOT ESCAPE")
        yield
    args["quarter_inputs"]=foreign()
    with pytest.raises(m.NCSourceBindingError,match=r"^source_derivation_refused$") as caught:
        m.bind_nc_routes_to_source17(**args)
    assert "PRIVATE" not in str(caught.value)
