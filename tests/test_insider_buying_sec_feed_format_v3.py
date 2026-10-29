"""Invented byte fixtures only; no retained archive, IO, acquisition or SDK."""
from dataclasses import replace
import gzip
import hashlib
import io
import json
import struct
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_format_v3 as m


CONTACT="invented@unit.test"


def _header(name=b"a.nc",body=b"opaque",kind=b"0",*,ustar=True,prefix=b""):
    value=bytearray(512);value[:len(name)]=name
    for at,size,text in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
        (124,12,format(len(body),"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        value[at:at+size]=text
    value[156:157]=kind
    if ustar:value[257:265]=b"ustar\0"+b"00";value[345:345+len(prefix)]=prefix
    return _checksum(value)


def _checksum(value):
    value=bytearray(value);value[148:156]=b"        ";value[148:156]=format(sum(value),"06o").encode()+b"\0 "
    return bytes(value)


def _tar(rows=None,*,tail=1024):
    rows=[(b"a.nc",b"<SUBMISSION>opaque</SUBMISSION>",b"0")] if rows is None else rows
    return b"".join(_header(name,body,kind)+body+bytes((-len(body))%512) for name,body,kind in rows)+bytes(tail)


def _gzip(raw,*,extra=None,name=None,comment=None,header_crc=False,text=False):
    flags=(4 if extra is not None else 0)|(8 if name is not None else 0)|(16 if comment is not None else 0)|(2 if header_crc else 0)|(1 if text else 0)
    header=b"\x1f\x8b\x08"+bytes([flags])+bytes(4)+b"\0\xff"
    if extra is not None:header+=struct.pack("<H",len(extra))+extra
    if name is not None:header+=name+b"\0"
    if comment is not None:header+=comment+b"\0"
    if header_crc:header+=struct.pack("<H",zlib.crc32(header)&0xffff)
    compressor=zlib.compressobj(wbits=-15);compressed=compressor.compress(raw)+compressor.flush()
    return header+compressed+struct.pack("<II",zlib.crc32(raw),len(raw)%(1<<32))


def _inspect(raw,**kwargs):return m.inspect_gzip_tar_format(raw,privacy_contact=CONTACT,fixture_only=True,**kwargs)


@pytest.mark.parametrize("chunksize",(1,7,511,512,513,65536))
def test_exact_physical_byte_ranges_hashes_and_shape_are_not_filing_admission(chunksize):
    payload=b"<SUBMISSION>opaque financial text is not parsed</SUBMISSION>\r\n"
    tar=_tar([(b"private-name.nc",payload,b"0")],tail=2048);raw=_gzip(tar)
    result=_inspect(raw,chunksize=chunksize);row=result["tar"]["members"][0]
    assert result["gzip_members"][0]["compressed_range"]==[0,len(raw)]
    assert result["decoded_stream_sha256"]==hashlib.sha256(tar).hexdigest()
    assert row["header_range"]==[0,512] and row["payload_range"]==[512,512+len(payload)]
    assert row["observed_payload_sha256"]==hashlib.sha256(payload).hexdigest()
    assert result["tar"]["terminator_range"]==[1024,2048] and result["tar"]["trailing_range"]==[2048,3072]
    observation=row["framing_observation"]["opening_token_observations"]
    assert observation[0]["offset"]==0 and observation[0]["exact_terminal_token_before_ASCII_whitespace"] is True
    assert result["complete_submission_projection_created"] is result["PDS_controls_validated"] is result["canonical_admitted"] is False
    assert result["actual_June_failure_cause_established"] is result["backtesting_ready"] is False
    encoded=json.dumps(result);assert "private-name.nc" not in encoded and "opaque financial text" not in encoded


@pytest.mark.parametrize("cut",(1,20,255,511,512,513,900,1024,1537))
def test_concatenated_gzip_segments_form_one_tar_even_inside_header_or_payload(cut):
    tar=_tar([(b"a.nc",b"x"*800,b"0")]);raw=_gzip(tar[:cut])+_gzip(tar[cut:])
    result=_inspect(raw,chunksize=7)
    assert len(result["gzip_members"])==2 and result["gzip_members"][0]["decoded_range"]==[0,cut]
    assert result["gzip_members"][1]["decoded_range"]==[cut,len(tar)]
    assert result["tar"]["status"]=="physical-framing-complete" and len(result["tar"]["members"])==1
    assert result["tar"]["members"][0]["observed_payload_sha256"]==hashlib.sha256(b"x"*800).hexdigest()


def test_empty_gzip_members_are_counted_and_independent_tar_concatenation_is_refused():
    tar=_tar();result=_inspect(_gzip(b"")+_gzip(tar)+_gzip(b""),chunksize=1)
    assert [row["decoded_bytes"] for row in result["gzip_members"]]==[0,len(tar),0]
    result=_inspect(_gzip(tar)+_gzip(tar),chunksize=13)
    assert result["tar"]["opaque_code"]=="nonzero_after_terminator" and len(result["tar"]["members"])==1
    assert result["tar"]["trailing_bytes"]==len(tar)
    assert result["tar"]["opaque_remainder_range"]==[len(tar),2*len(tar)]
    assert result["tar"]["opaque_remainder_sha256"]==hashlib.sha256(tar).hexdigest()


@pytest.mark.parametrize("extra,name,comment,hcrc,text",[(None,None,None,False,False),(b"AB\x02\0xy",b"name",b"comment",True,True),(b"",b"",b"",True,False)])
def test_bounded_optional_headers_and_header_CRC_are_supported(extra,name,comment,hcrc,text):
    raw=_gzip(_tar(),extra=extra,name=name,comment=comment,header_crc=hcrc,text=text)
    result=_inspect(raw,chunksize=1)
    assert result["gzip_members"][0]["header_crc_present_and_verified"] is hcrc


@pytest.mark.parametrize("fault,phase,code",[("magic","gzip-header","invalid_magic"),("method","gzip-header","unsupported_compression_method"),
    ("reserved","gzip-header","reserved_flags_set"),("header_crc","gzip-header","header_crc_mismatch"),
    ("crc","gzip-trailer","crc32_mismatch"),("isize","gzip-trailer","isize_mod32_mismatch"),
    ("trailer","gzip-trailer","truncated_trailer"),("junk","gzip-header","trailing_nonmember_bytes")])
def test_gzip_failures_keep_precise_static_phase_before_any_identity_hash(fault,phase,code,monkeypatch):
    raw=bytearray(_gzip(_tar(),header_crc=fault=="header_crc"))
    if fault=="magic":raw[0]=0
    elif fault=="method":raw[2]=7
    elif fault=="reserved":raw[3]|=32
    elif fault=="header_crc":raw[10]^=1
    elif fault=="crc":raw[-8]^=1
    elif fault=="isize":raw[-4]^=1
    elif fault=="trailer":del raw[-3:]
    else:raw.extend(b"not another gzip member")
    monkeypatch.setattr(m.hashlib,"sha256",lambda *a:pytest.fail("identity hash before complete screening/integrity"))
    with pytest.raises(m.FeedFormatError) as caught:_inspect(bytes(raw))
    assert (caught.value.phase,caught.value.code)==(phase,code)


@pytest.mark.parametrize("raw",[b"",b"\x1f\x8b",b"\x1f\x8b\x08\x04"+bytes(6)+b"\xff\xff",b"\x1f\x8b\x08\x08"+bytes(6)+b"no-terminator"])
def test_empty_or_truncated_optional_header_is_finitely_refused(raw):
    with pytest.raises(m.FeedFormatError):_inspect(raw)


@pytest.mark.parametrize("change",[{"decoded_bytes":100},{"expansion_ratio":1},{"gzip_members":1},{"gzip_header_bytes":10},
    {"gzip_text_field_bytes":2},{"tar_members":1},{"metadata_bytes":100}])
def test_limits_only_narrow_finite_resource_profiles(change):
    tar=_tar([(b"a",b"abc",b"0"),(b"b",b"def",b"0")]);raw=_gzip(tar,name=b"long-name")
    if "gzip_members" in change:raw=_gzip(tar[:512])+_gzip(tar[512:])
    with pytest.raises(m.FeedFormatError):_inspect(raw,limits=replace(m.FeedFormatLimits(),**change))


def test_wrong_limits_type_has_finite_input_classification():
    with pytest.raises(m.FeedFormatError,match="input:exact_limits_type_required"):_inspect(_gzip(_tar()),limits={})
    for limits in (replace(m.FeedFormatLimits(),decoded_bytes=True),replace(m.FeedFormatLimits(),decoded_bytes=8*1024**3+1)):
        with pytest.raises(m.FeedFormatError,match="limits_must_only_narrow"):_inspect(_gzip(_tar()),limits=limits)


def test_ISIZE_is_modulo_2pow32_not_an_asserted_exact_length():
    m._trailer(struct.pack("<II",123,5),0,123,(1<<32)+5)
    with pytest.raises(m.FeedFormatError,match="isize_mod32"):
        m._trailer(struct.pack("<II",123,6),0,123,(1<<32)+5)


@pytest.mark.parametrize("encoded",[CONTACT.encode(),CONTACT.upper().encode(),CONTACT.encode("utf-16-le"),
    b"invented&#64;unit.test",b"invented%40unit.test",b"invented\\u0040unit.test"])
def test_late_decoded_contact_across_gzip_members_precedes_all_hashes(encoded,monkeypatch):
    tar=_tar([(b"safe",b"prefix"+encoded+b"suffix",b"0")]);cut=520
    raw=_gzip(tar[:cut])+_gzip(tar[cut:])
    monkeypatch.setattr(m.hashlib,"sha256",lambda *a:pytest.fail("hash created before complete finite privacy pass"))
    with pytest.raises(m.FeedFormatError,match="privacy:finite_screen_refused"):_inspect(raw,chunksize=1)


def test_optional_gzip_header_contact_precedes_all_hashes(monkeypatch):
    raw=_gzip(_tar(),name=CONTACT.encode())
    monkeypatch.setattr(m.hashlib,"sha256",lambda *a:pytest.fail("hash before compressed privacy"))
    with pytest.raises(m.FeedFormatError,match="privacy"):_inspect(raw,chunksize=1)


def test_no_contact_is_explicitly_fixture_only_not_false_privacy_or_authentication():
    raw=_gzip(_tar())
    with pytest.raises(m.FeedFormatError,match="explicit_contact_required"):m.inspect_gzip_tar_format(raw,privacy_contact=None)
    value=m.inspect_gzip_tar_format(raw,privacy_contact=None,fixture_only=True)
    assert value["finite_privacy_screened"] is value["privacy_pin_runtime_attested_here"] is False


@pytest.mark.parametrize("name,kind,code",[(b"../escape",b"0","unsafe_member_path"),(b"/absolute",b"0","unsafe_member_path"),
    (b"a//b",b"0","unsafe_member_path"),(b"a/./b",b"0","unsafe_member_path"),(b"./a",b"0","unsafe_member_path"),
    (b"a/",b"0","regular_path_has_directory_suffix"),(b"link",b"2","unsupported_type_or_extension"),
    (b"hard",b"1","unsupported_type_or_extension"),(b"pax",b"x","unsupported_type_or_extension"),
    (b"global",b"g","unsupported_type_or_extension"),(b"gnu",b"L","unsupported_type_or_extension"),
    (b"sparse",b"S","unsupported_type_or_extension"),(b"directory/",b"5","directory_payload_refused")])
def test_unsafe_names_types_extensions_are_conserved_and_never_extracted(name,kind,code):
    value=_inspect(_gzip(_tar([(name,b"opaque",kind)])))
    row=value["tar"]["members"][0]
    assert code in row["refusal_codes"] and row["complete_physical_member"] is True and row["admitted"] is row["extracted"] is False
    assert value["tar"]["member_payloads_extracted"]==value["tar"]["filings_admitted"]==0
    assert value["tar"]["all_member_profiles_supported"] is value["tar"]["retention_extraction_or_admission_authorized"] is False


def test_duplicate_and_directory_alias_paths_are_counted_without_deduplication():
    value=_inspect(_gzip(_tar([(b"dir/",b"",b"5"),(b"dir",b"",b"5"),(b"a",b"one",b"0"),(b"a",b"two",b"0")])))
    assert len(value["tar"]["members"])==4 and value["tar"]["refusal_counts"]["duplicate_member_path"]==2


def test_V7_and_finite_ustar_prefix_are_distinct_supported_profiles():
    body=b"plain";v7=_header(b"a",body,ustar=False)+body+bytes((-len(body))%512)+bytes(1024)
    assert _inspect(_gzip(v7))["tar"]["members"][0]["header_profile"]=="v7-finite"
    header=_header(b"a",body,prefix=b"dir");value=_inspect(_gzip(header+body+bytes((-len(body))%512)+bytes(1024)))
    assert value["tar"]["members"][0]["name_sha256"]==hashlib.sha256(b"dir/a").hexdigest()


def test_bad_checksum_stops_unknown_stride_but_valid_gzip_still_has_complete_opaque_range():
    tar=_tar();broken=bytearray(tar);broken[10]^=1
    value=_inspect(_gzip(bytes(broken)),chunksize=3)
    assert value["tar"]["opaque_code"]=="checksum_mismatch" and value["tar"]["members"]==[]
    assert value["tar"]["opaque_remainder_range"]==[0,len(tar)]
    assert value["tar"]["opaque_remainder_sha256"]==hashlib.sha256(broken).hexdigest()


def test_nonzero_payload_padding_is_not_a_new_header_and_remains_refused():
    tar=bytearray(_tar([(b"a",b"x",b"0"),(b"b",b"y",b"0")]));tar[513]=1
    value=_inspect(_gzip(bytes(tar)),chunksize=1)
    assert len(value["tar"]["members"])==2 and value["tar"]["refusal_counts"]["nonzero_member_padding"]==1
    assert value["tar"]["status"]=="refused-physical-profile"


def test_one_zero_block_missing_terminator_preserves_its_actual_byte_range():
    tar=_tar(tail=512);value=_inspect(_gzip(tar),chunksize=1)
    assert value["tar"]["opaque_code"]=="missing_two_zero_block_terminator"
    assert value["tar"]["opaque_remainder_range"]==[len(tar)-512,len(tar)]
    assert value["tar"]["opaque_remainder_sha256"]==hashlib.sha256(bytes(512)).hexdigest()


@pytest.mark.parametrize("end",(515,1023,1200,1535))
def test_incomplete_member_descriptor_does_not_claim_full_declared_payload_or_lose_identity(end):
    tar=_tar([(b"a",b"x"*600,b"0")])[:end];value=_inspect(_gzip(tar),chunksize=3);row=value["tar"]["members"][0]
    assert row["complete_physical_member"] is False and row["payload_bytes_observed"]==min(end-512,600)
    assert value["tar"]["opaque_remainder_range"]==[0,end]
    assert value["tar"]["opaque_remainder_sha256"]==hashlib.sha256(tar).hexdigest()


@pytest.mark.parametrize("offset",(0,256,266))
def test_exact_envelope_offsets_are_observed_without_blindstrip_or_validated_control(offset):
    body=b"Q"*offset+b"<SUBMISSION>no field parsed</SUBMISSION>"+b" \r\n"*100
    value=_inspect(_gzip(_tar([(b"a.nc",body,b"0")])));row=value["tar"]["members"][0]
    observations=row["framing_observation"]["opening_token_observations"]
    assert [item["offset"] for item in observations]==([offset] if offset in {0,256} else [])
    if offset==256:assert observations[0]["prefix_sha256"]==hashlib.sha256(b"Q"*256).hexdigest()
    assert row["observed_payload_sha256"]==hashlib.sha256(body).hexdigest()
    assert row["framing_observation"]["validated_PDS_control"] is row["framing_observation"]["XML_or_SGML_structure_validated"] is False


def test_internal_or_split_closing_tokens_never_become_terminal_shape():
    body=b"<SEC-DOCUMENT>opaque</SEC-DOCU \tMENT>"
    row=_inspect(_gzip(_tar([(b"a",body,b"0")])),chunksize=1)["tar"]["members"][0]
    assert row["framing_observation"]["opening_token_observations"][0]["exact_terminal_token_before_ASCII_whitespace"] is False


def test_member_ratio_can_refuse_even_when_the_aggregate_ratio_is_within_profile():
    import random
    raw=_gzip(b"x"*10000)+_gzip(random.Random(9127).randbytes(10000))
    assert 20000<len(raw)*m.FeedFormatLimits().expansion_ratio
    with pytest.raises(m.FeedFormatError,match="gzip-trailer:member_expansion_ratio_bound"):_inspect(raw)


def test_physical_empty_directory_and_size_refusals_do_not_authorize_members():
    tar=_tar([(b"empty",b"",b"0"),(b"directory/",b"",b"5")])
    value=_inspect(_gzip(tar))
    assert value["tar"]["status"]=="physical-framing-complete" and value["tar"]["all_member_profiles_supported"] is True
    assert value["tar"]["retention_extraction_or_admission_authorized"] is False
    limited=_inspect(_gzip(_tar([(b"a",b"long",b"0")])),limits=replace(m.FeedFormatLimits(),tar_member_bytes=3))
    assert limited["tar"]["status"]=="physical-framing-complete" and limited["tar"]["all_member_profiles_supported"] is False
    assert limited["tar"]["members"][0]["refusal_codes"]==["member_size_profile_bound"]


def test_repeated_trailing_separator_is_not_a_canonical_safe_directory():
    value=_inspect(_gzip(_tar([(b"a//",b"",b"5")])))
    row=value["tar"]["members"][0]
    assert row["safe_relative_path"] is False and "unsafe_member_path" in row["refusal_codes"]
    assert value["tar"]["all_member_profiles_supported"] is False
    assert row["name_sha256"]==hashlib.sha256(b"a//").hexdigest()


def test_pure_API_never_calls_old_runtime_identity_inputs_or_transport(monkeypatch):
    raw=_gzip(_tar())
    def forbidden(*args,**kwargs):pytest.fail("pure format API reached executed collector front")
    for name in ("_identity","_current","_preflight_worker","_run_child","run_actual_sample","verify_actual_sample","_production_transport","_read_failed_v1"):
        monkeypatch.setattr(m.privacy_v2,name,forbidden)
    assert _inspect(raw)["tar"]["status"]=="physical-framing-complete"


def test_noncanonical_header_magic_link_and_string_padding_are_only_quarantined_profiles():
    for start,value,code in ((257,b"ustar ","unsupported_tar_header_profile"),(157,b"target","unexpected_link_target"),(5,b"\0hidden","nonzero_string_field_padding")):
        header=bytearray(_header(b"a",b"x"));header[start:start+len(value)]=value
        tar=_checksum(header)+b"x"+bytes(511)+bytes(1024);result=_inspect(_gzip(tar))
        assert code in result["tar"]["members"][0]["refusal_codes"] and result["tar"]["all_member_profiles_supported"] is False


def test_body_size_and_padding_boundaries_have_exact_nonoverlapping_extent_conservation():
    rows=[(f"leaf{i}".encode(),b"x"*count,b"0") for i,count in enumerate((0,1,511,512,513,1024))]
    tar=_tar(rows);result=_inspect(_gzip(tar),chunksize=17);offset=0
    for row,(_,body,_) in zip(result["tar"]["members"],rows):
        end=offset+512+len(body)+(-len(body))%512
        assert row["header_range"]==[offset,offset+512] and row["padding_range"][-1]==end
        assert row["observed_physical_member_sha256"]==hashlib.sha256(tar[offset:end]).hexdigest();offset=end
    assert result["tar"]["terminator_range"]==[offset,offset+1024] and offset+1024==len(tar)


def test_single_zero_before_partial_header_is_preserved_in_opaque_extent():
    initial=_tar(tail=512);tar=initial+b"partial"*14+b"xx"
    value=_inspect(_gzip(tar),chunksize=7)
    assert value["tar"]["opaque_code"]=="partial_header_at_EOF"
    assert value["tar"]["opaque_remainder_range"]==[len(initial)-512,len(tar)]
    assert value["tar"]["opaque_remainder_sha256"]==hashlib.sha256(tar[len(initial)-512:]).hexdigest()


def test_single_nonterminal_zero_has_explicit_range_and_identity_without_becoming_valid_tar():
    initial=_tar([(b"a",b"one",b"0")],tail=512);tar=initial+_tar([(b"b",b"two",b"0")])
    value=_inspect(_gzip(tar),chunksize=7)
    assert value["tar"]["status"]=="refused-physical-profile" and len(value["tar"]["members"])==2
    assert value["tar"]["nonterminal_zero_blocks"]==[{"range":[len(initial)-512,len(initial)],"sha256":hashlib.sha256(bytes(512)).hexdigest()}]


def test_invalid_deflate_and_short_trailing_bytes_keep_distinct_phases():
    invalid=b"\x1f\x8b\x08\x00"+bytes(6)+b"\x07"+bytes(8)
    with pytest.raises(m.FeedFormatError,match="gzip-deflate:invalid_deflate_stream"):_inspect(invalid)
    with pytest.raises(m.FeedFormatError,match="gzip-header:truncated_fixed_header"):_inspect(_gzip(_tar())+b"x")
