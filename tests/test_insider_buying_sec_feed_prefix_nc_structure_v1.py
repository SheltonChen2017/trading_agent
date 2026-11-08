"""Invented NC/member/XML witnesses only; no actual prefix or source values."""
from dataclasses import replace
import copy
import json
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_nc_structure_v1 as m

CONTACT="invented@unit.test"
ACCESSION=b"0000000042-20-123456"


def _header(size=0,name=b"opaque_file_name.nc",kind=b"0",magic=b"ustar  \0"):
    raw=bytearray(512);raw[:len(name)]=name;raw[124:136]=format(size,"011o").encode()+b"\0"
    raw[156:157]=kind;raw[257:265]=magic;raw[148:156]=b"        "
    raw[148:156]=format(sum(raw),"06o").encode()+b"\0 ";return bytes(raw)


def _member(body,name=b"opaque_file_name.nc",**kw):
    return _header(len(body),name,**kw)+body+bytes((-len(body))%512)


def _gzip(raw,level=0):
    writer=zlib.compressobj(level=level,wbits=31);return writer.compress(raw)+writer.flush()


def _document(body=b"<ownershipDocument><documentType>4</documentType><value>123456.78</value></ownershipDocument>",
        form=b"4",filename=b"private_form4.xml"):
    return b"<DOCUMENT>\n<TYPE>"+form+b"\n<SEQUENCE>1\n<FILENAME>"+filename+b"\n<TEXT>\n<XML>\n"+body+b"\n</XML>\n</TEXT>\n</DOCUMENT>\n"


def _payload(extra=b"",documents=None,acceptance=True):
    documents=_document() if documents is None else documents
    return b"<SUBMISSION>\n<ACCESSION-NUMBER>"+ACCESSION+b"\n<TYPE>4\n<FILING-DATE>20201008\n"+(
        b"<ACCEPTANCE-DATETIME>20201008123456\n" if acceptance else b"")+extra+b"<PUBLIC-DOCUMENT-COUNT>1\n"+documents+b"</SUBMISSION>\n"


def _qualify(payload=None,*,decoded=None,raw=None,limits=None,**kw):
    decoded=_member(_payload() if payload is None else payload)+bytes(1024) if decoded is None else decoded
    return m.qualify_prefix_nc_structure(_gzip(decoded) if raw is None else raw,CONTACT,
        fixture_only=True,limits=limits,**kw)


def _nc(value):return value["members"][0]["NC_structure"]


def test_complete_NC_witness_private_values_not_returned_and_NO_admission():
    value=_qualify();nc=_nc(value);header=nc["header"]
    assert header["status"]=="complete_observed_header_lexical_only"
    assert header["accession_single_canonical_lexeme"] is header["acceptance_single_14digit_lexeme"] is True
    assert header["form_token_class"]=="4" and nc["filename_contains_single_internal_accession_lexeme"] is False
    docs=nc["documents"];assert docs["document_count"]==1 and docs["primary_ownership_syntactic_candidates"]==1
    xml=docs["documents"][0]["XML_structure"]
    assert xml["well_formed_XML_document"] is xml["ownership_document_root"] is True
    assert xml["text_values_collected_or_parsed"] is False
    assert value["authority"]["canonical_admitted"] is value["authority"]["backtesting_ready"] is False
    text=json.dumps(value)
    for private in (ACCESSION.decode(),"20201008123456","20201008","private_form4.xml","123456.78",CONTACT,"opaque_file_name"):
        assert private not in text
    assert "prefix_sha256" not in text and "physical_sha256" not in text and "routing_key_sha256" not in text
    assert set(value["dependency_source_pins"])==set(m.DEPENDENCY_PINS)


def test_internal_accession_filename_comparison_is_private_boolean_not_identity():
    value=_qualify(decoded=_member(_payload(),name=b"nested/"+ACCESSION+b"_extra.nc")+bytes(1024))
    assert _nc(value)["filename_contains_single_internal_accession_lexeme"] is True
    assert value["members"][0]["name_pattern"]["basename_pattern"]=="other_opaque_shape"
    assert value["authority"]["identity_or_original_parent_verified"] is False


def test_acceptance_absent_only_in_complete_unambiguous_header_not_TEXT_lookalike():
    payload=_payload(acceptance=False,documents=_document(body=b"<ACCEPTANCE-DATETIME>20201008123456",filename=b"opaque.txt"))
    header=_nc(_qualify(payload))["header"]
    assert header["fields"]["ACCEPTANCE-DATETIME"]["presence"]=="absent_in_complete_observed_header"
    assert header["acceptance_single_14digit_lexeme"] is False


@pytest.mark.parametrize("extra",[b"<NOTE><ACCEPTANCE-DATETIME>20201008123456\n",b"<UNKNOWN><TYPE>4\n"])
def test_unknown_markup_bearing_header_value_is_ambiguous_not_absent(extra):
    header=_nc(_qualify(_payload(extra=extra,acceptance=False)))["header"]
    assert header["status"]=="ambiguous_or_unsupported_header"
    assert header["fields"]["ACCEPTANCE-DATETIME"]["presence"]=="ambiguous_header_or_scope"


@pytest.mark.parametrize("offset,field",[(369,b"00000000001\0"),(381,b"\x01"),(386,b"00000000001\0"),(482,b"\x01"),(483,b"00000000001\0")])
def test_oldGNU_regular_extension_semantics_are_not_examined_as_plain_NC(offset,field):
    body=_payload();header=bytearray(_header(len(body)));header[offset:offset+len(field)]=field
    header[148:156]=b"        ";header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    result=_qualify(decoded=bytes(header)+body+bytes((-len(body))%512)+bytes(1024));row=result["members"][0]
    assert row["inspection_disposition"]=="unsupported_header_semantics_not_examined"
    assert row["NC_structure"]["absence_claims_permitted"] is False


@pytest.mark.parametrize("extra",[b"<ACCESSION-NUMBER>0000000099-20-000001\n",b"<ACCEPTANCE-DATETIME>20201008000000\n"])
def test_duplicate_header_values_never_become_unique_identity_or_time(extra):
    header=_nc(_qualify(_payload(extra=extra)))["header"]
    key="ACCESSION-NUMBER" if extra.startswith(b"<ACCESSION") else "ACCEPTANCE-DATETIME"
    assert header["fields"][key]["presence"]=="present_multiple"
    assert header["accession_single_canonical_lexeme"] is False if key=="ACCESSION-NUMBER" else header["acceptance_single_14digit_lexeme"] is False


def test_HEADER_and_SEC_HEADER_scopes_are_distinct_and_conflicting_not_fallback():
    body=b"<SUBMISSION>\n<HEADER>\n<ACCESSION-NUMBER>"+ACCESSION+b"\n</HEADER>\n<SEC-HEADER>opaque\n<ACCEPTANCE-DATETIME>20201008123456\n</SEC-HEADER>\n</SUBMISSION>\n"
    header=_nc(_qualify(body))["header"]
    assert header["HEADER_openings"]==header["SEC_HEADER_openings"]==1
    assert header["status"]=="ambiguous_or_unsupported_header" and header["accession_single_canonical_lexeme"] is False


def test_nested_unknown_scope_and_HEADER_mismatch_do_not_prove_absence():
    header=_nc(_qualify(_payload(extra=b"<UNKNOWN>\n</UNKNOWN>\n",acceptance=False)))["header"]
    assert header["fields"]["ACCEPTANCE-DATETIME"]["presence"]=="ambiguous_header_or_scope"


def test_partial_member_is_unexamined_not_absent_and_no_fake_complete_payload():
    payload=_payload();decoded=_header(len(payload)+10000)+payload
    value=_qualify(decoded=decoded);member=value["members"][0]
    assert member["inspection_disposition"]=="partial_physical_payload_not_examined"
    assert member["NC_structure"]=={"status":"not_examined","reason":"partial_physical_payload_not_examined","absence_claims_permitted":False}


def test_payload_header_lookalike_is_not_sequential_member():
    payload=_payload(documents=_document(body=b"x"*512+_header(0),filename=b"opaque.txt"))
    value=_qualify(payload)
    assert value["accounting"]["physical_headers_observed"]==1


@pytest.mark.parametrize("kind",[b"x",b"g",b"L",b"K",b"S",b"1",b"2",b"5"])
def test_nonregular_extensions_never_gain_NC_absence_or_XML_witness(kind):
    value=_qualify(decoded=_member(_payload(),kind=kind)+bytes(1024));member=value["members"][0]
    assert member["inspection_disposition"]=="nonregular_or_extension_not_examined" and member["NC_structure"]["absence_claims_permitted"] is False


@pytest.mark.parametrize("value",[{},True,replace(m.NCStructureLimits(),headers=True),replace(m.NCStructureLimits(),payload_bytes=1024**2+1)])
def test_limits_exact_and_only_narrow(value):
    with pytest.raises(m.NCStructureError):_qualify(limits=value)


def test_member_count_and_aggregate_payload_limits_refuse_entire_witness():
    decoded=_member(_payload())*2+bytes(1024)
    with pytest.raises(m.NCStructureError,match="examined_member_count_bound"):_qualify(decoded=decoded,limits=replace(m.NCStructureLimits(),examined_members=1))
    with pytest.raises(m.NCStructureError,match="aggregate_payload_bound"):_qualify(decoded=decoded,limits=replace(m.NCStructureLimits(),total_payload_bytes=len(_payload())+1))


def test_complete_oversize_payload_is_explicitly_unexamined_not_partially_inspected():
    value=_qualify(limits=replace(m.NCStructureLimits(),payload_bytes=8))
    assert value["members"][0]["inspection_disposition"]=="complete_payload_over_profile_not_examined"
    assert value["accounting"]["complete_NC_payloads_examined"]==0


@pytest.mark.parametrize("secret",[CONTACT.encode(),b"invented%40unit.test",b"".join(f"\\u{ord(c):04x}".encode() for c in CONTACT)])
def test_all_decoded_private_data_refused_before_member_interpretation(monkeypatch,secret):
    monkeypatch.setattr(m,"_member_witness",lambda *a:pytest.fail("privacy failure reached interpretation"))
    raw=_gzip(_member(_payload()+secret)+bytes(1024),level=6);assert secret not in raw
    with pytest.raises(m.NCStructureError,match="finite_prefix_screen_refused"):_qualify(raw=raw)


@pytest.mark.parametrize("xml,status",[(b'<!DOCTYPE ownershipDocument [<!ENTITY x "private">]><ownershipDocument>&x;</ownershipDocument>',"prohibited_DTD_or_entity_declaration"),
    (b'<!DOCTYPE ownershipDocument SYSTEM "https://example.invalid/secret"><ownershipDocument/>',"prohibited_DTD_or_entity_declaration"),
    (b'<?xml version="1.0" encoding="ISO-8859-1"?><ownershipDocument/>',"unsupported_BOM_or_encoding"),
    (b'\xff\xfe<ownershipDocument/>',"unsupported_BOM_or_encoding"),
    (b'<ownershipDocument>',"malformed_XML")])
def test_XML_refusals_have_finite_syntactic_status_and_never_resolve(xml,status):
    value=_qualify(_payload(documents=_document(xml)));row=_nc(value)["documents"]["documents"][0]
    assert row["XML_structure"]["status"]==status and row["primary_ownership_syntactic_candidate"] is False


def test_DTD_refuses_before_XML_parser_construction(monkeypatch):
    monkeypatch.setattr(m.expat,"ParserCreate",lambda *a,**k:pytest.fail("DTD reached XML parser"))
    value=_qualify(_payload(documents=_document(b'<!DOCTYPE ownershipDocument><ownershipDocument/>')))
    assert _nc(value)["documents"]["documents"][0]["XML_structure"]["status"]=="prohibited_DTD_or_entity_declaration"


def test_XML_depth_and_node_capacity_are_fatal_not_a_prefix_result():
    xml=b"<ownershipDocument><a><b/></a></ownershipDocument>"
    with pytest.raises(m.NCStructureError,match="XML_depth_bound"):_qualify(_payload(documents=_document(xml)),limits=replace(m.NCStructureLimits(),xml_depth=2))
    with pytest.raises(m.NCStructureError,match="XML_node_bound"):_qualify(_payload(documents=_document(xml)),limits=replace(m.NCStructureLimits(),xml_nodes=2))


def test_zero_document_and_PAC_literal_do_not_infer_paper_or_source17_status():
    body=b"<SUBMISSION>\n<TYPE>PAC\n<PUBLIC-DOCUMENT-COUNT>0\n</SUBMISSION>\n"
    value=_qualify(body);nc=_nc(value)
    assert nc["header"]["form_token_class"]=="PAC_literal_only" and nc["documents"]["document_count"]==0
    assert nc["paper_or_PAC_status_inferred_from_zero_documents"] is False
    assert value["authority"]["source17_join_attempted"] is False


@pytest.mark.parametrize("mutation",[
    lambda v:v.update(extra="private"),lambda v:v["authority"].update(backtesting_ready=True),
    lambda v:v.update(decoded_prefix_bytes=True),lambda v:v["members"][0]["name_pattern"].update(basename_pattern="private-name"),
    lambda v:v["members"][0]["NC_structure"]["header"].update(form_token_class="private-form"),
    lambda v:v["accounting"].update(unexamined_members=1)])
def test_public_validator_rejects_values_unknown_fields_aliases_and_crosslinks(mutation):
    value=_qualify();mutation(value)
    with pytest.raises(m.NCStructureError):m.validate_prefix_nc_observation(value,fixture_only=True)


def test_validator_returns_detached_copy():
    value=_qualify();accepted=m.validate_prefix_nc_observation(value,fixture_only=True)
    value["members"][0]["name_pattern"]["basename_pattern"]="mutated"
    assert accepted["members"][0]["name_pattern"]["basename_pattern"]!="mutated"


def test_64_real_complete_NC_rows_fit_metadata_and_65_refuse_whole_result():
    body=_payload(documents=b"")
    value=_qualify(raw=_gzip(_member(body)*64+bytes(1024),level=6))
    assert value["accounting"]["complete_NC_payloads_examined"]==64 and len(m._raw(value))<=256*1024
    with pytest.raises(m.NCStructureError,match="examined_member_count_bound"):
        _qualify(raw=_gzip(_member(body)*65+bytes(1024),level=6))


def test_nonzero_GNU_times_are_not_POSIX_prefix_or_acceptance_values():
    body=_payload(acceptance=False);header=bytearray(_header(len(body)))
    header[345:357]=b"12345670123\0";header[357:369]=b"12345670124\0"
    header[148:156]=b"        ";header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    value=_qualify(decoded=bytes(header)+body+bytes((-len(body))%512)+bytes(1024))
    assert value["accounting"]["complete_NC_payloads_examined"]==1
    assert _nc(value)["header"]["acceptance_single_14digit_lexeme"] is False
    assert b"12345670123" not in m._raw(value)


def test_SOURCE_is_count_only_and_17_semantics_never_interpreted():
    value=_qualify(_payload(extra=b"<SOURCE>17\n"));header=_nc(value)["header"]
    assert header["fields"]["SOURCE"]["presence"]=="present_once"
    assert value["authority"]["source17_join_attempted"] is False and b'"17"' not in m._raw(value)


def test_all_public_refusal_pairs_are_finite_exported_controls():
    assert type(m.SAFE_ERROR_CODES) is frozenset
    for call in (lambda:_qualify(limits={}),lambda:_qualify(raw=b"bad"),lambda:_qualify(limits=replace(m.NCStructureLimits(),metadata_bytes=1))):
        with pytest.raises(m.NCStructureError) as caught:call()
        assert (caught.value.phase,caught.value.code) in m.SAFE_ERROR_CODES
