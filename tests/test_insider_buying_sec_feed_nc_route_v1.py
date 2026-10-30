"""Invented raw NC routing subset; no retained inputs, source rows or outcomes."""
from dataclasses import replace
import copy
import hashlib
import json

import pytest

from research import insider_buying_sec_feed_nc_route_v1 as m

CONTACT="invented-route-private@unit.test"
ACC=b"0123456789-20-123456"
OTHER=b"0000000042-20-000001"


def _doc(body=b"<XML>\n<ownershipDocument><privateValue>not-read</privateValue></ownershipDocument>\n</XML>",form=b"4",seq=b"1"):
    return b"<DOCUMENT>\n<TYPE>"+form+b"\n<SEQUENCE>"+seq+b"\n<FILENAME>invented-private.xml\n<TEXT>\n"+body+b"\n</TEXT>\n</DOCUMENT>\n"


def _payload(*,accession=ACC,form=b"4",extra=b"",groups=b"",docs=None,count=b"1",date=b"20201008"):
    return (b"<SUBMISSION>\n<ACCESSION-NUMBER>"+accession+b"\n<TYPE>"+form+b"\n<PUBLIC-DOCUMENT-COUNT>"+count+
        b"\n<FILING-DATE>"+date+b"\n"+extra+groups+(_doc(form=form) if docs is None else docs)+b"</SUBMISSION>\n")


def _assess(raw=None,**kwargs):
    return m.assess_nc_route(_payload() if raw is None else raw,privacy_contact=CONTACT,fixture_only=True,**kwargs)


def _batch(payloads,consumed=frozenset(),**kwargs):
    return m.assess_nc_route_batch(tuple(payloads),consumed_accessions=consumed,privacy_contact=CONTACT,fixture_only=True,**kwargs)


def test_supported_direct_front_is_private_route_NOT_source_or_clock_seal():
    raw=_payload();value=_assess(raw);claim=value.claim;w=value.public_witness()
    assert claim.accession_number==ACC.decode() and claim.form_type=="4"
    assert claim.filing_date=="2020-10-08" and claim.public_document_count==1
    assert claim.payload_bytes() is raw and m.validate_nc_front_route_claim(claim) is claim
    assert w["disposition"]=="private_direct_front_route_claim" and w["document_frames_qualified"]==1
    assert w["acceptance_evidence"]=="not_established_no_clock_substitution"
    assert all(v is False if type(v) is bool else v==0 for v in w["authority"].values())
    public=json.dumps(w)+repr(value)+repr(claim)
    for secret in (ACC.decode(),"20201008","2020-10-08",CONTACT,"invented-private.xml","not-read",hashlib.sha256(raw).hexdigest()):
        assert secret not in public
    w["authority"]["backtesting_ready"]=True
    assert value.public_witness()["authority"]["backtesting_ready"] is False


@pytest.mark.parametrize("form",[b"3",b"3/A",b"4",b"4/A",b"5",b"5/A"])
def test_all_six_form_routes_keep_amendment_token_without_financial_interpretation(form):
    assert _assess(_payload(form=form)).claim.form_type==form.decode()


def test_CRLF_input_bound_unchanged_and_no_HEADER_wrapper_needed():
    raw=_payload().replace(b"\n",b"\r\n");claim=_assess(raw).claim
    assert claim is not None and claim.payload_bytes()==raw
    assert _assess(_payload().replace(b"<SUBMISSION>\n",b"<SUBMISSION>\n<HEADER>\n")).claim is None


def test_documented_nested_issuer_owner_scopes_do_not_become_issuer_identity():
    groups=(b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented issuer\n<CIK>999\n</COMPANY-DATA>\n"
        b"<BUSINESS-ADDRESS>\n<CITY>Nowhere\n<PHONE>0000000000\n</BUSINESS-ADDRESS>\n</ISSUER>\n"
        b"<REPORTING-OWNER>\n<OWNER-DATA>\n<CONFORMED-NAME>Invented owner\n<CIK>42\n</OWNER-DATA>\n"
        b"<FILING-VALUES>\n<FORM-TYPE>4\n<ACT>34\n<FILE-NUMBER>000-00001\n<FILM-NUMBER>12345\n</FILING-VALUES>\n"
        b"<FORMER-NAME>\n<FORMER-CONFORMED-NAME>Old invented owner\n<DATE-CHANGED>20190101\n</FORMER-NAME>\n</REPORTING-OWNER>\n")
    value=_assess(_payload(groups=groups))
    assert value.claim is not None and value.public_witness()["authority"]["issuer_or_reporter_identity_verified"] is False
    assert "999" not in json.dumps(value.public_witness())


@pytest.mark.parametrize("extra",[
    b"<UNKNOWN>\n<CIK>42\n</UNKNOWN>\n",b"<UNKNOWN>opaque\n",b"<SEC-ACT>34\n",
    b"<SOURCE>17\n",b"<ACCESSION-NUMBER>"+OTHER+b"\n",b"<TYPE>4\n",b"<FILING-DATE>20201008\n",
    b"<PUBLIC-DOCUMENT-COUNT>1\n",b"<NOTE><ACCESSION-NUMBER>"+OTHER+b"\n",
    b"<ACCEPTANCE-DATETIME>20201008123456\n",b"<!-- <ACCESSION-NUMBER>"+ACC+b" -->\n"])
def test_unknown_duplicate_inline_late_front_or_unsupported_fields_quarantine(extra):
    value=_assess(_payload(extra=extra))
    assert value.claim is None and value.public_witness()["route_claim_available"] is False


@pytest.mark.parametrize("tag",["CORRECTION","TIMESTAMP","PAPER","DELETION","PRIVATE-TO-PUBLIC","CONFIRMING-COPY",
    "PUBLIC-REL-DATE","ACTION-DATE","RECEIVED-DATE"])
def test_status_or_unqualified_availability_references_do_not_route(tag):
    line=("<"+tag+">"+("20201008123456" if tag=="TIMESTAMP" else "")+"\n").encode()
    value=_assess(_payload(extra=line));assert value.claim is None
    assert value.public_witness()["disposition"]=="unqualified_documented_status"


def test_date_change_alone_is_lexical_not_PAC_resolution_or_acceptance():
    value=_assess(_payload(extra=b"<DATE-OF-FILING-DATE-CHANGE>20201009\n"))
    assert value.claim is not None
    assert value.public_witness()["authority"]["paper_PAC_or_release_lineage_resolved"] is False


@pytest.mark.parametrize("groups",[
    b"<ISSUER>\n<CIK>42\n</ISSUER>\n",
    b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented\n<ACCESSION-NUMBER>"+ACC+b"\n<CIK>42\n</COMPANY-DATA>\n</ISSUER>\n",
    b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented\n<CIK>42\n</OWNER-DATA>\n</ISSUER>\n",
    b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented\n<CIK>42\n</COMPANY-DATA>\n<TYPE>4\n</ISSUER>\n",
    b"<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented\n<CIK>42\n</COMPANY-DATA>\n</ISSUER>\n<TYPE>4\n"])
def test_scope_shadows_never_flatten_or_complete_direct_front(groups):
    assert _assess(_payload(groups=groups)).claim is None


def test_TEXT_route_lookalikes_are_opaque_and_not_duplicate_hints():
    doc=_doc(b"<ACCESSION-NUMBER>"+OTHER+b"\n<TYPE>5\n<FILING-DATE>19000101")
    value=_assess(_payload(docs=doc));assert value.claim is not None
    assert value.public_witness()["canonical_preamble_accession_occurrences"]==1


@pytest.mark.parametrize("change",[
    lambda raw:raw[:-15],lambda raw:b"x"+raw,lambda raw:raw+b"garbage\n",
    lambda raw:raw.replace(b"</SUBMISSION>",b"</SUBMISSION>\n</SUBMISSION>"),
    lambda raw:raw.replace(b"</TEXT>",b"<DOCUMENT>\n</TEXT>"),
    lambda raw:raw.replace(b"</DOCUMENT>",b""),lambda raw:raw.replace(b"<TEXT>\n",b"<TEXT>inline\n"),
    lambda raw:raw.replace(b"<PUBLIC-DOCUMENT-COUNT>1",b"<PUBLIC-DOCUMENT-COUNT>2"),
    lambda raw:raw.replace(b"<SEQUENCE>1",b"<SEQUENCE>01"),
    lambda raw:raw.replace(b"<FILING-DATE>20201008",b"<FILING-DATE>20200230"),
    lambda raw:raw.replace(b"<TYPE>4\n<SEQUENCE>",b"<TYPE>5\n<SEQUENCE>")])
def test_complete_wrapper_document_count_frame_and_calendar_required(change):
    assert _assess(change(_payload())).claim is None


def test_batch_all_duplicate_copies_quarantined_not_first_latest():
    a=_payload();b=_payload(form=b"4/A");c=_payload(accession=OTHER)
    batch=_batch((a,b,c));assert len(batch.eligible_claims())==1 and batch.eligible_claims()[0][0]==2
    assert batch.public_witness()["member_dispositions"][:2]==["duplicate_route_all_copies_quarantined"]*2
    assert m.validate_nc_route_batch(batch) is batch


@pytest.mark.parametrize("extra",[b"<PAPER>\n",b"<UNKNOWN>\n<ACCESSION-NUMBER>"+ACC+b"\n</UNKNOWN>\n"])
def test_rejected_row_shadow_still_quarantines_valid_other_copy(extra):
    batch=_batch((_payload(),_payload(extra=extra)))
    assert not batch.eligible_claims()
    assert batch.public_witness()["disposition_counts"]=={"duplicate_route_all_copies_quarantined":2}


def test_consumed_roster_excludes_claim_and_keeps_exact_bound_set():
    consumed=frozenset({ACC.decode()});batch=_batch((_payload(),_payload(accession=OTHER)),consumed)
    assert batch.bound_consumed_accessions() is consumed
    assert [i for i,c in batch.eligible_claims()]==[1]
    assert batch.public_witness()["member_dispositions"][0]=="prior_consumed_route_quarantined"


@pytest.mark.parametrize("factory",[lambda:_assess(),lambda:_batch((_payload(),))])
def test_copied_factory_objects_are_not_genuine(factory):
    value=factory();copied=copy.copy(value)
    validator=m.validate_nc_route_batch if type(value) is m.NCRouteBatch else m.validate_nc_route_assessment
    with pytest.raises(m.NCRouteError,match="genuine_unchanged"):validator(copied)


def test_forged_copied_mutated_claims_and_batch_eligible_restoration_refuse():
    value=_assess();claim=value.claim
    with pytest.raises(m.NCRouteError):m.validate_nc_front_route_claim(copy.copy(claim))
    original=claim.public_document_count
    try:
        object.__setattr__(claim,"public_document_count",True)
        with pytest.raises(m.NCRouteError):value.public_witness()
    finally:object.__setattr__(claim,"public_document_count",original)
    batch=_batch((_payload(),_payload()))
    original=batch._items
    try:
        object.__setattr__(batch,"_items",(value,))
        with pytest.raises(m.NCRouteError):batch.eligible_claims()
    finally:object.__setattr__(batch,"_items",original)


@pytest.mark.parametrize("secret",[CONTACT.encode(),CONTACT.replace("@","%40").encode(),
    b"".join(("\\u%04x"%ord(c)).encode() for c in CONTACT),CONTACT.encode("utf-16-le")])
def test_full_refused_payload_privacy_precedes_parse_claim_or_hash(secret,monkeypatch):
    raw=_payload(extra=b"<UNKNOWN>"+secret+b"\n")
    monkeypatch.setattr(m,"_assessment",lambda *a:pytest.fail("private input reached parser"))
    with pytest.raises(m.NCRouteError,match="finite_payload_screen_refused"):_assess(raw)


def test_late_batch_privacy_and_budgets_prevent_partial_claim_factory(monkeypatch):
    monkeypatch.setattr(m,"_assessment",lambda *a:pytest.fail("partial batch claimed before final privacy"))
    with pytest.raises(m.NCRouteError,match="finite_payload_screen_refused"):
        _batch((_payload(),_payload(accession=OTHER,docs=_doc(CONTACT.encode()))))


@pytest.mark.parametrize("kwargs,code",[
    ({"payload_bytes":100},"payload_byte_bound"),({"lines":2},"line_count_bound"),
    ({"line_bytes":4},"line_byte_bound"),({"preamble_bytes":16},"preamble_byte_bound"),
    ({"metadata_bytes":1},"metadata_byte_bound")])
def test_exact_narrow_capacity_refuses_no_convenient_prefix(kwargs,code):
    with pytest.raises(m.NCRouteError,match=code):_assess(limits=replace(m.NCRouteLimits(),**kwargs))


@pytest.mark.parametrize("limits",[{},True,replace(m.NCRouteLimits(),members=True),replace(m.NCRouteLimits(),payload_bytes=8*1024**2+1)])
def test_wrong_limits_fail_own_finite_error(limits):
    with pytest.raises(m.NCRouteError):_assess(limits=limits)


def test_batch_capacity_consumed_and_input_types_are_exact():
    for kwargs in ({"members":1},{"batch_bytes":len(_payload())+1}):
        with pytest.raises(m.NCRouteError):_batch((_payload(),_payload(accession=OTHER)),limits=replace(m.NCRouteLimits(),**kwargs))
    for consumed in (set(),frozenset({True}),frozenset({"private-invalid"})):
        with pytest.raises(m.NCRouteError):_batch((_payload(),),consumed)
    for payload in (bytearray(_payload()),b"",None):
        with pytest.raises(m.NCRouteError):m.assess_nc_route(payload,privacy_contact=CONTACT,fixture_only=True)
    with pytest.raises(m.NCRouteError):m.assess_nc_route(_payload(),privacy_contact=None)
    assert m.assess_nc_route(_payload(),privacy_contact=None,fixture_only=True).public_witness()["finite_privacy_screened"] is False


@pytest.mark.parametrize("mutation",[
    lambda w:w.update(unknown="private"),lambda w:w["authority"].update(backtesting_ready=True),
    lambda w:w["authority"].update(new_requests=True),lambda w:w.update(payload_bytes=True),
    lambda w:w.update(route_claim_available=1),lambda w:w.update(privacy_source_sha256="f"*64),
    lambda w:w.update(canonical_preamble_accession_occurrences=2),lambda w:w.update(document_frames_qualified=0),
    lambda w:w.update(disposition="private actual source"),lambda w:w.update(authority=object()),
    lambda w:w.update(authority={"x":float("nan")})])
def test_closed_witness_rejects_authority_type_aliases_foreign_objects(mutation):
    w=_assess().public_witness();mutation(w)
    with pytest.raises(m.NCRouteError):m.validate_nc_route_witness(w,fixture_only=True)


def test_cycle_and_batch_witness_inconsistent_partition_refuse_finitely():
    w=_assess().public_witness();w["authority"]=w
    with pytest.raises(m.NCRouteError):m.validate_nc_route_witness(w,fixture_only=True)
    w=_batch((_payload(),)).public_witness();w["eligible_private_claims"]=True
    with pytest.raises(m.NCRouteError):m.validate_nc_route_batch_witness(w,fixture_only=True)
    w=_batch((_payload(),)).public_witness();w["member_dispositions"]=["prior_consumed_route_quarantined"]
    with pytest.raises(m.NCRouteError):m.validate_nc_route_batch_witness(w,fixture_only=True)


# Claude review section 330 (IBNCROUTE-CR33001): the value parser strips
# leading spaces/tabs, so the shadow hint must too, or a whitespace-led copy
# of a route hides from duplicate quarantine. Claims keep the canonical form.
@pytest.mark.parametrize("pad",[b"\t",b" ",b" \t "])
def test_whitespace_led_shadow_copy_still_quarantines_every_copy(pad):
    shadow=_payload(accession=pad+ACC)
    assert _assess(shadow).claim is None
    batch=_batch((_payload(),shadow))
    assert not batch.eligible_claims()
    assert batch.public_witness()["disposition_counts"]=={"duplicate_route_all_copies_quarantined":2}
    assert _batch((_payload(accession=pad+ACC),),frozenset({ACC.decode()})).public_witness()["member_dispositions"]==["prior_consumed_route_quarantined"]


@pytest.mark.parametrize("before_submission",[False,True])
def test_stray_DOCUMENT_does_not_hide_a_shadow_before_a_qualified_TEXT_barrier(before_submission):
    valid=_payload()
    malformed=(b"<DOCUMENT>\n"+valid if before_submission else
        valid.replace(b"<SUBMISSION>\n",b"<SUBMISSION>\n<DOCUMENT>\n",1))
    assessed=_assess(malformed)
    assert assessed.claim is None and assessed.public_witness()["canonical_preamble_accession_occurrences"]==0
    batch=_batch((valid,malformed))
    assert batch.eligible_claims()==()
    assert batch.public_witness()["member_dispositions"]==["duplicate_route_all_copies_quarantined"]*2


@pytest.mark.parametrize("raw",[
    b"<SUBMISSION>\n<TEXT>\n<ACCESSION-NUMBER>"+ACC+b"\n</TEXT>\n</SUBMISSION>\n",
    b"<DOCUMENT>\n<TEXT>\n<ACCESSION-NUMBER>"+ACC+b"\n</TEXT>\n",
    _payload().replace(b"<TEXT>\n",b"<TEXT>inline\n"),
    b"<SUBMISSION>\n<ACCESSION-NUMBER>"+ACC+b"\n</SUBMISSION>\n",
])
def test_unqualified_or_missing_TEXT_barrier_refuses_entire_batch_not_other_claims(raw):
    assert _assess(raw).claim is None
    with pytest.raises(m.NCRouteError) as caught:_batch((_payload(accession=OTHER),raw))
    assert (caught.value.phase,caught.value.code)==("structure","shadow_front_unqualified")


def test_genuine_opaque_TEXT_accession_mentions_do_not_quarantine_distinct_routes():
    second=_payload(accession=OTHER,docs=_doc(b"<ACCESSION-NUMBER>"+ACC+b"\n<ACCESSION-NUMBER>\t"+ACC))
    batch=_batch((_payload(),second))
    assert [index for index,_ in batch.eligible_claims()]==[0,1]
    assert batch.public_witness()["disposition_counts"]=={"private_direct_front_route_claim":2}


def test_description_document_header_is_a_supported_opaque_TEXT_barrier():
    second=_payload(accession=OTHER,docs=_doc(b"<ACCESSION-NUMBER>"+ACC).replace(
        b"<TEXT>\n",b"<DESCRIPTION>invented description\n<TEXT>\n",1))
    assert [index for index,_ in _batch((_payload(),second)).eligible_claims()]==[0,1]


@pytest.mark.parametrize("old,new",[
    (b"<TYPE>4\n<SEQUENCE>",b"<TYPE>\n<SEQUENCE>"),
    (b"<SEQUENCE>1",b"<SEQUENCE>01"),
    (b"<FILENAME>invented-private.xml",b"<FILENAME>"),
    (b"<TEXT>\n",b"<DESCRIPTION>bad<inline>\n<TEXT>\n"),
])
def test_malformed_document_header_cannot_establish_an_opaque_shadow_barrier(old,new):
    raw=_payload().replace(old,new,1)
    assert _assess(raw).claim is None
    with pytest.raises(m.NCRouteError) as caught:_batch((_payload(accession=OTHER),raw))
    assert (caught.value.phase,caught.value.code)==("structure","shadow_front_unqualified")


def test_shadow_front_budget_includes_stray_DOCUMENT_prelude_and_qualified_header():
    raw=_payload().replace(b"<SUBMISSION>\n",b"<SUBMISSION>\n"+b"<DOCUMENT>\n"*8,1)
    with pytest.raises(m.NCRouteError) as caught:_assess(raw,limits=replace(m.NCRouteLimits(),preamble_bytes=80))
    assert (caught.value.phase,caught.value.code)==("capacity","preamble_byte_bound")


def test_exact_shadow_front_byte_boundary_includes_header_but_not_opaque_TEXT():
    raw=_payload();front_bytes=raw.index(b"<TEXT>\n")+len(b"<TEXT>\n")
    limits=replace(m.NCRouteLimits(),preamble_bytes=front_bytes)
    assert _assess(raw,limits=limits).claim is not None
    with pytest.raises(m.NCRouteError) as caught:_assess(raw,limits=replace(limits,preamble_bytes=front_bytes-1))
    assert (caught.value.phase,caught.value.code)==("capacity","preamble_byte_bound")
    larger=_payload(docs=_doc(b"opaque"*8192))
    assert larger.index(b"<TEXT>\n")+len(b"<TEXT>\n")==front_bytes
    assert _assess(larger,limits=limits).claim is not None


def test_stray_DOCUMENT_front_budget_counts_cumulative_prelude_not_header_alone():
    raw=b"<DOCUMENT>\n"+_payload()
    front_bytes=raw.index(b"<TEXT>\n")+len(b"<TEXT>\n")
    document_header_bytes=front_bytes-raw.rindex(b"<DOCUMENT>\n",0,front_bytes)
    assert document_header_bytes<front_bytes-1
    assert _assess(raw,limits=replace(m.NCRouteLimits(),preamble_bytes=front_bytes)).claim is None
    with pytest.raises(m.NCRouteError) as caught:
        _assess(raw,limits=replace(m.NCRouteLimits(),preamble_bytes=front_bytes-1))
    assert (caught.value.phase,caught.value.code)==("capacity","preamble_byte_bound")


@pytest.mark.parametrize("complete",[True,False])
def test_shadow_completeness_is_exact_typed_factory_snapshot_not_caller_assertion(complete):
    raw=_payload() if complete else b"<SUBMISSION>\n<TEXT>\n</SUBMISSION>\n"
    value=_assess(raw)
    assert value._shadow_complete is complete
    try:
        object.__setattr__(value,"_shadow_complete",1 if complete else True)
        with pytest.raises(m.NCRouteError,match="genuine_unchanged_assessment_required"):value.public_witness()
    finally:object.__setattr__(value,"_shadow_complete",complete)


def test_contact_screen_precedes_even_an_ambiguous_shadow_barrier(monkeypatch):
    raw=b"<SUBMISSION>\n<TEXT>\n"+CONTACT.encode()+b"\n</SUBMISSION>\n"
    monkeypatch.setattr(m,"_shadow_front",lambda *a:pytest.fail("shadow interpretation preceded whole privacy"))
    with pytest.raises(m.NCRouteError) as caught:_assess(raw)
    assert (caught.value.phase,caught.value.code)==("privacy","finite_payload_screen_refused")
