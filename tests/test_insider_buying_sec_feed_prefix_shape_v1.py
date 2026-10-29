"""Invented prefix shapes only, never retained bytes or supplier calls."""
from dataclasses import replace
import hashlib
import json
import random
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_shape_v1 as m

CONTACT="invented@unit.test"


def _checksum(value):
    value=bytearray(value);value[148:156]=b"        "
    value[148:156]=format(sum(value),"06o").encode()+b"\0 "
    return bytes(value)


def _header(name=b"invented.nc",size=0,kind=b"0",magic="posix",prefix=b""):
    value=bytearray(512);value[:len(name)]=name
    for at,width,text in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
        (124,12,format(size,"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        value[at:at+width]=text
    value[156:157]=kind
    if magic=="posix":value[257:265]=b"ustar\x0000";value[345:345+len(prefix)]=prefix
    elif magic=="gnu":value[257:265]=b"ustar  \0"
    elif magic=="unknown":value[257:265]=b"UNKNOWN!"
    return _checksum(value)


def _member(body=b"opaque",**kw):
    return _header(size=len(body),**kw)+body+bytes((-len(body))%512)


def _gzip(raw,level=0):
    c=zlib.compressobj(level=level,wbits=31)
    return c.compress(raw)+c.flush()


def _qualify(decoded=None,raw=None,**kw):
    raw=_gzip(decoded) if raw is None else raw
    return m.qualify_prefix_shape(raw,privacy_contact=kw.pop("privacy_contact",CONTACT),
        fixture_only=kw.pop("fixture_only",True),**kw)


@pytest.mark.parametrize("magic,expected",[("posix","posix_ustar_NUL00"),("gnu","old_gnu_ustar_spaces_NUL"),("v7","v7_zero_tail")])
def test_exact_magic_enum_directory_then_unchanged_sequential_regular_ranges(magic,expected):
    body=b"<SUBMISSION>opaque no admission</SUBMISSION>"
    decoded=_header(name=b"dir/",kind=b"5",magic=magic)+_member(body,name=b"0000000001-20-000001.nc",magic=magic)+bytes(1024)
    result=_qualify(decoded);shape=result["physical_shape_observations"];rows=shape["headers"]
    assert len(rows)==2 and rows[0]["type_class_observation"]=="directory"
    assert [r["magic_pattern_observation"] for r in rows]==[expected,expected]
    assert rows[0]["header_range"]==[0,512] and rows[0]["payload_range"]==rows[0]["padding_range"]==[512,512]
    assert rows[1]["header_range"]==[512,1024] and rows[1]["payload_range"]==[1024,1024+len(body)]
    assert rows[1]["observed_physical_range"]==[512,1536]
    assert rows[1]["payload_opening_markers"]==[{"offset":0,"family":"SUBMISSION"}]
    assert rows[1]["fixed_name_fields_match_accession_nc_routing_pattern"] is True
    assert shape["two_zero_block_range"]==[1536,2560]
    assert shape["status"]=="two_zero_blocks_observed_not_whole_carrier_EOF"
    assert rows[1]["complete_physical_span_observed_within_prefix"] is True
    assert result["PDS_or_GNU_logical_name_profile_validated"] is result["backtesting_ready"] is False
    text=json.dumps(result)
    assert "0000000001-20-000001" not in text and "opaque no admission" not in text and CONTACT not in text
    assert "dir/" not in text and ".nc\"" not in text


def test_second_header_beyond_frozen64KiB_window_is_observed_by_streaming():
    body=random.Random(541).randbytes(22000)+b"x"*80000
    decoded=_member(body,name=b"first.nc",magic="gnu")+_member(b"<SEC-DOCUMENT>opaque",name=b"second.nc",magic="gnu")+bytes(1024)
    raw=_gzip(decoded,level=6);assert len(raw)<65536 and len(decoded)>65536
    result=_qualify(raw=raw);rows=result["physical_shape_observations"]["headers"]
    assert len(rows)==2 and rows[1]["header_range"][0]>65536
    assert rows[1]["payload_opening_markers"]==[{"offset":0,"family":"SEC-DOCUMENT"}]
    assert result["prefix_format_descriptor"]["decoded_observation_bytes"]==65536
    assert result["physical_shape_observations"]["decoded_bytes_observed"]==len(decoded)


def test_plausible_header_inside_payload_is_never_scanned_as_a_member():
    fake=_header(name=b"forged.nc",size=0)
    decoded=_member(b"x"*512+fake+b"x"*512,name=b"real.nc")+_member(b"actual",name=b"last.nc")+bytes(1024)
    result=_qualify(decoded);rows=result["physical_shape_observations"]["headers"]
    assert [r["header_range"][0] for r in rows]==[0,2048]
    assert "forged" not in json.dumps(result)


@pytest.mark.parametrize("offset",[0,256,266])
def test_payload_marker_offsets_are_observations_not_prefix_stripping(offset):
    body=b"x"*offset+b"<SUBMISSION>opaque"
    result=_qualify(_member(body)+bytes(1024));row=result["physical_shape_observations"]["headers"][0]
    assert row["payload_opening_markers"]==[{"offset":offset,"family":"SUBMISSION"}]
    assert row["payload_range"]==[512,512+len(body)]
    assert row["header_or_payload_rewritten"] is row["PDS_controls_validated"] is row["admitted"] is False


@pytest.mark.parametrize("kind",[b"x",b"g",b"L",b"K",b"S",b"1",b"2",b"9"])
def test_extensions_and_links_stop_without_interpreting_following_names(kind):
    decoded=_member(b"opaque",kind=kind,magic="gnu")+_member(b"not reached",name=b"later.nc")+bytes(1024)
    result=_qualify(decoded);shape=result["physical_shape_observations"]
    assert shape["status"]=="unsupported_type_or_extension_stop" and len(shape["headers"])==1
    assert shape["structural_frontier_bytes"]==512 and shape["following_bytes_not_interpreted"]==len(decoded)-512
    assert shape["headers"][0]["payload_bytes_observed"]==0


def test_unknown_magic_is_observed_then_stops_without_guessing_body_geometry():
    decoded=_member(b"opaque",magic="unknown")+_member(b"later")
    shape=_qualify(decoded)["physical_shape_observations"]
    assert shape["status"]=="unknown_magic_pattern_stop" and shape["headers"][0]["magic_pattern_observation"]=="unknown"
    assert shape["headers"][0]["fixed_name_fields_examined"] is False


def test_invalid_observed_checksum_is_not_prefix_truncation():
    decoded=bytearray(_member());decoded[101]^=1
    shape=_qualify(bytes(decoded))["physical_shape_observations"]
    assert shape["status"]=="observed_invalid_header_checksum"
    assert shape["headers"][0]["header_checksum_matches"] is False and shape["partial_header_range"] is None


def test_non_octal_size_stops_distinctly_after_valid_checksum():
    header=bytearray(_header());header[124:136]=b"not-octal!!!\0";header=_checksum(header)
    shape=_qualify(header+b"opaque")["physical_shape_observations"]
    assert shape["status"]=="observed_unsupported_octal_size_field"
    assert shape["headers"][0]["declared_payload_bytes"] is None


@pytest.mark.parametrize("cut,status",[(1,"prefix_ended_with_partial_header"),(511,"prefix_ended_with_partial_header"),
    (512,"prefix_ended_with_partial_payload"),(515,"prefix_ended_with_partial_payload"),
    (520,"prefix_ended_with_partial_padding"),(1023,"prefix_ended_with_partial_padding"),
    (1024,"prefix_ended_at_next_header_boundary"),(1536,"prefix_ended_with_single_zero_block"),
    (2048,"two_zero_blocks_observed_not_whole_carrier_EOF")])
def test_prefix_boundary_states_do_not_become_invalid_checksum_or_full_EOF(cut,status):
    decoded=_member(b"12345678")+bytes(1024)
    shape=_qualify(decoded[:cut])["physical_shape_observations"]
    assert shape["status"]==status
    assert shape["whole_TAR_or_member_population_verified"] is False
    if cut<512:assert shape["partial_header_range"]==[0,cut]
    elif cut<1024:assert shape["headers"][0]["observed_physical_range"]==[0,cut]


@pytest.mark.parametrize("case,status",[("nonzero_pad","observed_nonzero_member_padding"),
    ("one_zero","observed_nonzero_after_single_zero_block"),("two_zero","observed_nonzero_after_two_zero_blocks"),
    ("directory_payload","directory_nonzero_payload_stop")])
def test_observed_invalid_or_unsupported_geometry_is_explicit(case,status):
    if case=="nonzero_pad":decoded=_member(b"x")[:-1]+b"X"+_member(b"later")
    elif case=="one_zero":decoded=bytes(512)+_member()
    elif case=="two_zero":decoded=bytes(1024)+_member()
    else:decoded=_member(b"x",kind=b"5")+_member()
    shape=_qualify(decoded)["physical_shape_observations"]
    assert shape["status"]==status


@pytest.mark.parametrize("name",[b"/0000000001-20-000001.nc",b"../0000000001-20-000001.nc",b"dir//0000000001-20-000001.nc",b"./0000000001-20-000001.nc"])
def test_name_flags_never_normalize_unsafe_paths_or_return_name(name):
    result=_qualify(_member(name=name));row=result["physical_shape_observations"]["headers"][0]
    assert row["fixed_name_fields_safe_relative_path"] is row["fixed_name_fields_match_accession_nc_routing_pattern"] is False
    assert name.decode() not in json.dumps(result)


def test_old_GNU_bytes345_are_not_misread_as_POSIX_prefix():
    header=bytearray(_header(name=b"0000000001-20-000001.nc",magic="gnu"));header[345:350]=b"../X/"
    result=_qualify(_checksum(header));row=result["physical_shape_observations"]["headers"][0]
    assert row["magic_pattern_observation"]=="old_gnu_ustar_spaces_NUL"
    assert row["fixed_name_fields_safe_relative_path"] is True
    assert row["logical_name_profile_validated"] is False


def test_header_count_exhaustion_refuses_whole_descriptor_not_a_convenient_prefix():
    decoded=b"".join(_header(name=f"dir{i}/".encode(),kind=b"5") for i in range(3))
    with pytest.raises(m.PrefixShapeError,match="header_count_bound"):
        _qualify(decoded,limits=replace(m.ShapeLimits(),header_count=2))


def test_256_count_cap_and_metadata_cap_are_both_finite():
    decoded=b"".join(_header(name=f"dir{i}/".encode(),kind=b"5") for i in range(257))
    raw=_gzip(decoded,level=1)
    assert len(raw)<65536
    with pytest.raises(m.PrefixShapeError):_qualify(raw=raw)
    with pytest.raises(m.PrefixShapeError,match="metadata_bound"):
        _qualify(_member(),limits=replace(m.ShapeLimits(),metadata_bytes=100))


def test_real_256_header_metadata_boundary_positive_not_an_unproved_count():
    decoded=b"".join(_header(name=f"dir{i}/".encode(),kind=b"5",magic="gnu") for i in range(256))
    result=_qualify(raw=_gzip(decoded,level=1))
    assert result["physical_shape_observations"]["observed_complete_headers"]==256
    assert len(m._raw(result))<=262144


@pytest.mark.parametrize("limits",[{},m.ShapeLimits(header_count=257),m.ShapeLimits(metadata_bytes=262145),m.ShapeLimits(header_count=True)])
def test_only_narrow_exact_limits(limits):
    with pytest.raises(m.PrefixShapeError):_qualify(_member(),limits=limits)


def test_all_raw_and_decoded_privacy_finishes_before_shape_and_prefix_hash(monkeypatch):
    raw=_gzip(_member(CONTACT.encode()))
    monkeypatch.setattr(m.core,"_digest",lambda value:pytest.fail("hash before complete privacy"))
    monkeypatch.setattr(m,"_ShapeObserver",lambda *a:pytest.fail("shape before complete privacy"))
    with pytest.raises(m.PrefixShapeError,match="finite_prefix_screen_refused"):_qualify(raw=raw)


def test_missing_contact_is_not_a_fixture_privacy_assertion():
    with pytest.raises(m.PrefixShapeError,match="explicit_contact_required"):_qualify(_member(),privacy_contact=None)


def test_second_decode_counts_must_match_frozen_first_pass(monkeypatch):
    original=m.core._decode_prefix;calls=[]
    def decode(*args):
        result=original(*args);calls.append(True)
        return result if len(calls)==1 else (result[0],result[1]+1,result[2],result[3])
    monkeypatch.setattr(m.core,"_decode_prefix",decode)
    with pytest.raises(m.PrefixShapeError,match="immutable_two_pass_decode_counts_differ"):_qualify(_member())


def test_observer_forced_wrong_decoded_total_refuses(monkeypatch):
    original=m._ShapeObserver.finish
    def finish(self):
        value=original(self);value["decoded_bytes_observed"]+=1;return value
    monkeypatch.setattr(m._ShapeObserver,"finish",finish)
    with pytest.raises(m.PrefixShapeError,match="observer_decoded_count_differs"):_qualify(_member())


def test_gzip_corruption_is_not_interpreted_as_a_TAR_profile(monkeypatch):
    raw=bytearray(_gzip(_member()));raw[-8]^=1
    monkeypatch.setattr(m,"_ShapeObserver",lambda *a:pytest.fail("observing corrupt prefix"))
    with pytest.raises(m.PrefixShapeError,match="invalid_gzip_prefix_or_observed_trailer"):_qualify(raw=bytes(raw))


def test_raw_prefix_hash_is_only_upstream_raw_hash_no_name_or_decoded_hash():
    raw=_gzip(_member());result=_qualify(raw=raw)
    assert result["prefix_sha256"]==hashlib.sha256(raw).hexdigest()
    encoded=json.dumps(result)
    assert "name_sha256" not in encoded and "decoded_sha256" not in encoded
    assert result["decoded_bytes_separately_hashed_or_retained"] is False
    assert result["whole_carrier_CRC_ISIZE_EOF_or_privacy_verified"] is False
