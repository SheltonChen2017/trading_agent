"""Independent invented-only NC envelope and bounded privacy witnesses."""
from __future__ import annotations

import gzip
import hashlib
import json
import random

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_nc_structure_v1 as m


CONTACT = "invented-nc-private@unit.test"
ACCESSION = b"0123456789-20-123456"
ACCEPTANCE = b"20200102030405"


def _header(name, size, *, kind=b"0"):
    value = bytearray(512)
    value[:len(name)] = name
    value[124:136] = format(size, "011o").encode()+b"\0"
    value[148:156] = b"        "
    value[156:157] = kind
    value[257:265] = b"ustar  \0"
    value[148:156] = format(sum(value), "06o").encode()+b"\0 "
    return bytes(value)


def _pack(payloads, *, terminator=True):
    rows = []
    for ordinal, payload in enumerate(payloads):
        name = ("invented-unmapped-"+str(ordinal)+".nc").encode()
        rows.append(_header(name, len(payload))+payload+bytes((-len(payload)) % 512))
    return b"".join(rows)+(bytes(1024) if terminator else b"")


def _gzip(decoded):
    raw = gzip.compress(decoded, mtime=0)
    assert len(raw) <= 65536, "invented fixture exceeded HTTP prefix bound"
    assert len(decoded) <= len(raw)*128, "invented fixture hit upstream expansion guard"
    assert len(decoded) <= 8*1024**2
    return raw


def _nc(xml=b"<ownershipDocument/>", *, extra_header=b"", header_acceptance=True):
    header = (b"<SUBMISSION>\n<HEADER>\n<ACCESSION-NUMBER>"+ACCESSION+b"\n<TYPE>4\n"
        +(b"<ACCEPTANCE-DATETIME>"+ACCEPTANCE+b"\n" if header_acceptance else b"")
        +extra_header+b"</HEADER>\n")
    return (header+b"<DOCUMENT>\n<TYPE>4\n<SEQUENCE>1\n<FILENAME>unreturned.xml\n<TEXT>\n<XML>\n"
        +xml+b"\n</XML>\n</TEXT>\n</DOCUMENT>\n</SUBMISSION>\n")


def _large_nc(size, seed, *, noise_bytes=12000):
    prefix = (b"<SUBMISSION>\n<HEADER>\n<TYPE>4\n</HEADER>\n<DOCUMENT>\n<TYPE>EX-99\n"
        b"<SEQUENCE>1\n<FILENAME>unreturned.txt\n<TEXT>\n")
    suffix = b"\n</TEXT>\n</DOCUMENT>\n</SUBMISSION>\n"
    count = size-len(prefix)-len(suffix)
    alphabet = b"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789 "
    noise = bytes(random.Random(seed).choices(alphabet, k=noise_bytes))
    lines = noise+b"\n"+b"safe-public-padding\n"*((count+19)//20)
    value = prefix+lines[:count]+suffix
    assert len(value) == size
    return value


def _qualify(payloads, **kwargs):
    return m.qualify_prefix_nc_structure(_gzip(_pack(payloads)), CONTACT, fixture_only=True, **kwargs)


def _witness(result):
    return result["members"][0]["NC_structure"]


def test_review_unclosed_SGML_leaf_fields_and_noncanonical_filename_are_observations_only():
    payload = _nc(b"<ownershipDocument><inventedValue>not-a-financial-number</inventedValue></ownershipDocument>")
    raw = _gzip(_pack([payload]))
    result = m.qualify_prefix_nc_structure(raw, CONTACT, fixture_only=True)
    witness = _witness(result)
    assert witness["header"]["status"] == "complete_observed_header_lexical_only"
    assert witness["header"]["acceptance_single_14digit_lexeme"] is True
    assert witness["header"]["accession_single_canonical_lexeme"] is True
    assert witness["documents"]["primary_ownership_syntactic_candidates"] == 1
    assert result["members"][0]["name_pattern"]["basename_pattern"] == "other_opaque_shape"
    assert result["accounting"]["complete_NC_payloads_examined"] == 1
    rendered = json.dumps(result)
    for private_value in (ACCESSION.decode(), ACCEPTANCE.decode(), "unreturned.xml", "not-a-financial-number",
            hashlib.sha256(raw).hexdigest(), hashlib.sha256(payload).hexdigest(), hashlib.sha256(ACCESSION).hexdigest()):
        assert private_value not in rendered
    assert all(value is False for key, value in result["authority"].items()
        if key not in {"new_requests", "files_read_written", "SDK_calls", "outcome_looks"})


def test_review_sequential_duplicate_HEADER_sections_cannot_join_singletons():
    payload = _nc(header_acceptance=False).replace(b"</HEADER>\n",
        b"</HEADER>\n<HEADER>\n<ACCEPTANCE-DATETIME>"+ACCEPTANCE+b"\n</HEADER>\n", 1)
    header = _witness(_qualify([payload]))["header"]
    assert header["HEADER_openings"] == 2
    assert header["status"] == "ambiguous_or_unsupported_header"
    assert header["fields"]["ACCESSION-NUMBER"]["presence"] == "ambiguous_header_or_scope"
    assert header["acceptance_single_14digit_lexeme"] is False
    assert header["accession_single_canonical_lexeme"] is False


def test_review_equal_duplicate_acceptance_is_multiple_not_deduplicated():
    header = _witness(_qualify([_nc(extra_header=b"<ACCEPTANCE-DATETIME>"+ACCEPTANCE+b"\n")]))["header"]
    assert header["fields"]["ACCEPTANCE-DATETIME"]["top_header_occurrences"] == 2
    assert header["fields"]["ACCEPTANCE-DATETIME"]["presence"] == "present_multiple"
    assert header["acceptance_single_14digit_lexeme"] is False


def test_review_document_CDATA_tag_lookalike_cannot_supply_header_acceptance():
    xml = (b"<ownershipDocument><notes><![CDATA[<ACCEPTANCE-DATETIME>"+ACCEPTANCE
        +b" <HEADER>fake</HEADER>]]></notes></ownershipDocument>")
    witness = _witness(_qualify([_nc(xml, header_acceptance=False)]))
    assert witness["header"]["fields"]["ACCEPTANCE-DATETIME"]["presence"] == "absent_in_complete_observed_header"
    assert witness["header"]["acceptance_single_14digit_lexeme"] is False
    assert witness["documents"]["primary_ownership_syntactic_candidates"] == 1


@pytest.mark.parametrize("xml,status", (
    (b"<!DOCTYPE ownershipDocument [<!ENTITY x 'invented'>]><ownershipDocument>&x;</ownershipDocument>",
        "prohibited_DTD_or_entity_declaration"),
    (b"\xef\xbb\xbf<ownershipDocument/>", "unsupported_BOM_or_encoding"),
    (b"<?xml version='1.0' encoding='ISO-8859-1'?><ownershipDocument/>", "unsupported_BOM_or_encoding"),
))
def test_review_unsupported_XML_resource_or_encoding_stops_before_parser(xml, status, monkeypatch):
    monkeypatch.setattr(m.expat, "ParserCreate", lambda *a, **k: pytest.fail("unsafe XML reached parser"))
    document = _witness(_qualify([_nc(xml)]))["documents"]["documents"][0]
    assert document["XML_structure"]["status"] == status
    assert document["primary_ownership_syntactic_candidate"] is False


@pytest.mark.parametrize("xml,limits,code", (
    (b"<ownershipDocument><a><b/></a></ownershipDocument>", m.NCStructureLimits(xml_depth=2), "XML_depth_bound"),
    (b"<ownershipDocument><a/><b/></ownershipDocument>", m.NCStructureLimits(xml_nodes=2), "XML_node_bound"),
))
def test_review_XML_resource_caps_refuse_whole_witness(xml, limits, code):
    with pytest.raises(m.NCStructureError) as caught:
        _qualify([_nc(xml)], limits=limits)
    assert (caught.value.phase, caught.value.code) == ("capacity", code)


def test_review_XML_marker_pairs_alone_never_establish_well_formed_ownership():
    witness = _witness(_qualify([_nc(b"<ownershipDocument><broken></ownershipDocument>")]))
    document = witness["documents"]["documents"][0]
    assert document["XML_structure"]["status"] == "malformed_XML"
    assert document["XML_structure"]["well_formed_XML_document"] is False
    assert document["primary_ownership_syntactic_candidate"] is False


def test_review_UTF16_NUL_payload_is_explicitly_unexamined_before_XML_parser(monkeypatch):
    monkeypatch.setattr(m.expat, "ParserCreate", lambda *a, **k: pytest.fail("NUL payload reached XML parser"))
    witness = _witness(_qualify([_nc(b"\xff\xfe"+"<ownershipDocument/>".encode("utf-16-le"))]))
    assert witness["status"] == "unsupported_NUL_or_line_endings"
    assert witness["absence_claims_permitted"] is False


def test_review_real_64_member_boundary_succeeds_without_raising_metadata_cap():
    result = _qualify([_nc() for _ in range(64)])
    assert result["accounting"]["complete_NC_payloads_examined"] == 64
    assert len(result["members"]) == 64
    assert len(m._raw(result)) <= 256*1024


def test_review_65_complete_candidates_refuse_whole_unit_before_collector_or_member_parse(monkeypatch):
    raw = _gzip(_pack([_nc() for _ in range(65)]))
    monkeypatch.setattr(m, "_Collect", lambda *a, **k: pytest.fail("count cap chose a convenient subset"))
    with pytest.raises(m.NCStructureError) as caught:
        m.qualify_prefix_nc_structure(raw, CONTACT, fixture_only=True)
    assert (caught.value.phase, caught.value.code) == ("capacity", "examined_member_count_bound")


def test_review_real_4MiB_aggregate_and_1MiB_per_payload_boundaries_succeed():
    payloads = [_large_nc(1024**2, seed) for seed in range(4)]
    result = _qualify(payloads)
    assert result["accounting"]["complete_NC_payloads_examined"] == 4
    assert result["accounting"]["payload_bytes_examined"] == 4*1024**2


def test_review_aggregate_budget_refuses_before_any_convenient_subset_parse(monkeypatch):
    raw = _gzip(_pack([_large_nc(768*1024, seed, noise_bytes=8000) for seed in range(6)]))
    monkeypatch.setattr(m, "_Collect", lambda *a, **k: pytest.fail("aggregate cap chose a convenient subset"))
    with pytest.raises(m.NCStructureError) as caught:
        m.qualify_prefix_nc_structure(raw, CONTACT, fixture_only=True)
    assert (caught.value.phase, caught.value.code) == ("capacity", "aggregate_payload_bound")


def test_review_complete_oversize_and_partial_members_are_explicitly_unexamined(monkeypatch):
    monkeypatch.setattr(m, "_member_witness", lambda *a, **k: pytest.fail("unexamined member was parsed"))
    oversize = _qualify([_large_nc(1024**2+1, 53)])
    assert oversize["accounting"]["complete_NC_payloads_examined"] == 0
    assert _witness(oversize) == {"status": "not_examined", "reason": "complete_payload_over_profile_not_examined",
        "absence_claims_permitted": False}
    raw = _gzip(_header(b"partial-unreturned.nc", 2*1024**2)+_nc())
    partial = m.qualify_prefix_nc_structure(raw, CONTACT, fixture_only=True)
    assert partial["accounting"]["complete_NC_payloads_examined"] == 0
    assert _witness(partial) == {"status": "not_examined", "reason": "partial_physical_payload_not_examined",
        "absence_claims_permitted": False}


def test_review_private_echo_in_unexamined_oversize_member_precedes_any_hash_or_collection(monkeypatch):
    payload = _large_nc(1024**2+1, 72).replace(b"</SUBMISSION>", CONTACT.encode()+b"\n</SUBMISSION>")
    raw = _gzip(_pack([payload]))
    assert CONTACT.encode() not in raw
    screen = m.shape.core.frozen.privacy_v2._TextScreen(CONTACT)
    for at in range(0, len(raw), 1024):
        screen.feed(raw[at:at+1024])
    screen.feed(b"", final=True)
    monkeypatch.setattr(m.shape.core, "_digest", lambda raw: pytest.fail("private decoded content was hashed"))
    monkeypatch.setattr(m, "_Collect", lambda *a, **k: pytest.fail("collection preceded complete privacy"))
    with pytest.raises(m.NCStructureError) as caught:
        m.qualify_prefix_nc_structure(raw, CONTACT, fixture_only=True)
    assert (caught.value.phase, caught.value.code) == ("privacy", "finite_prefix_screen_refused")


def test_review_14digit_acceptance_shape_is_not_calendar_or_PIT_validation():
    payload = _nc().replace(ACCEPTANCE, b"20201399009999")
    result = _qualify([payload])
    assert _witness(result)["header"]["acceptance_single_14digit_lexeme"] is True
    assert result["authority"]["acceptance_timestamp_or_timezone_or_PIT_verified"] is False
