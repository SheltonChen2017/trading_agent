"""Invented prefix units only; never actual artifacts, network or credentials."""
import hashlib
import json
import struct
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_format_v1 as m

CONTACT = "invented@unit.test"


def _gzip(raw, *, level=0):
    c = zlib.compressobj(level=level, wbits=-15)
    return b"\x1f\x8b\x08\0" + bytes(6) + c.compress(raw) + c.flush() + struct.pack("<II", zlib.crc32(raw), len(raw))


def _tar(body=b"<SUBMISSION>not admitted</SUBMISSION>", *, kind=b"0", name=b"invented.nc", opaque=0):
    h = bytearray(512)
    h[:len(name)] = name
    for at, width, value in ((100, 8, b"0000600\0"), (108, 8, b"0000000\0"),
        (116, 8, b"0000000\0"), (124, 12, format(len(body) + opaque, "011o").encode() + b"\0"),
        (136, 12, b"00000000000\0")):
        h[at:at+width] = value
    h[156:157] = kind
    h[257:265] = b"ustar\x0000"
    h[148:156] = b"        "
    h[148:156] = format(sum(h), "06o").encode() + b"\0 "
    payload = bytes(opaque) + body
    return bytes(h) + payload + bytes((-len(payload)) % 512) + bytes(1024)


def _inspect(raw, **kw):
    return m.inspect_prefix(raw, privacy_contact=kw.pop("privacy_contact", CONTACT),
        fixture_only=kw.pop("fixture_only", True), **kw)


def test_sole_prefix_digest_and_no_whole_source_promotion():
    raw = _gzip(_tar())
    result = _inspect(raw)
    assert result["prefix_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["prefix_bytes"] == len(raw)
    assert result["finite_privacy_screened"] is True
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 1
    assert result["last_observed_gzip_member_incomplete"] is False
    assert result["first_tar_header_observation"]["header_checksum_matches"] is True
    assert result["first_tar_header_observation"]["header_profile"] == "ustar-finite"
    assert result["first_tar_header_observation"]["payload_opening_markers"] == [{"offset": 0, "family": "SUBMISSION"}]
    for key in ("whole_carrier_CRC_ISIZE_or_EOF_verified", "whole_carrier_privacy_screened",
        "whole_carrier_hashed_or_retained", "complete_member_population_known", "canonical_admitted",
        "acceptance_or_PIT_verified", "PDS_controls_validated", "backtesting_ready",
        "earlier_failed_archive_cause_established", "HTTP_framing_verified_here"):
        assert result[key] is False
    assert result["filings_extracted_or_admitted"] == result["new_requests"] == result["SDK_calls"] == 0
    encoded = json.dumps(result)
    assert "invented.nc" not in encoded and "not admitted" not in encoded and CONTACT not in encoded


@pytest.mark.parametrize("cut", [1, 2, 3, 4, 5, 9, 10, 11, 12, 100, 510, 511, 512, 513, 1000, -8, -7, -1])
def test_truncated_header_deflate_and_trailer_are_prefix_not_whole_integrity(cut):
    raw = _gzip(_tar())
    result = _inspect(raw[:cut])
    assert result["last_observed_gzip_member_incomplete"] is True
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 0
    assert result["whole_carrier_CRC_ISIZE_or_EOF_verified"] is False
    assert result["prefix_sha256"] == hashlib.sha256(raw[:cut]).hexdigest()


@pytest.mark.parametrize("split", [1, 255, 511, 512, 513, 1100])
def test_gzip_member_split_is_continuous_decoded_prefix(split):
    tar = _tar()
    raw = _gzip(tar[:split]) + _gzip(tar[split:])
    result = _inspect(raw)
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 2
    assert result["decoded_prefix_bytes"] == len(tar)
    assert result["first_tar_header_observation"]["header_checksum_matches"] is True
    assert result["complete_member_population_known"] is False


def test_complete_member_and_truncated_next_header_are_distinct():
    raw = _gzip(b"opaque") + b"\x1f\x8b\x08"
    r = _inspect(raw)
    assert r["completed_gzip_members_with_observed_valid_trailers"] == 1
    assert r["last_observed_gzip_member_incomplete"] is True
    assert r["first_tar_header_observation"]["header_profile"] == "not_observed"


@pytest.mark.parametrize("offset", [0, 256, 266])
@pytest.mark.parametrize("family", [b"<SUBMISSION>", b"<SEC-DOCUMENT>"])
def test_opaque_offsets_are_observations_never_a_pds_strip(offset, family):
    body = bytes(offset) + family + b"opaque"
    result = _inspect(_gzip(_tar(body)))
    assert result["first_tar_header_observation"]["payload_opening_markers"] == [{"offset": offset, "family": family[1:-1].decode()}]
    assert result["first_tar_header_observation"]["PDS_control_validated"] is False
    assert result["PDS_controls_validated"] is False
    assert result["XML_or_financial_fields_parsed"] is False


@pytest.mark.parametrize("kind,label", [(b"x", "pax"), (b"g", "pax-global"), (b"L", "gnu-longname"),
    (b"2", "symlink"), (b"5", "directory"), (b"Q", "other")])
def test_first_header_extensions_observed_without_extracting_or_accepting(kind, label):
    r = _inspect(_gzip(_tar(kind=kind)))
    assert r["first_tar_header_observation"]["type_class"] == label
    assert r["filings_extracted_or_admitted"] == 0


def test_non_tar_decoded_stream_is_retained_unit_not_parser_success():
    r = _inspect(_gzip(b"<SUBMISSION>" + b"opaque"*200))
    assert r["initial_decoded_opening_markers"] == [{"offset": 0, "family": "SUBMISSION"}]
    assert r["first_tar_header_observation"]["header_checksum_matches"] is False
    assert r["first_tar_header_observation"]["header_profile"] == "first_block_not_supported_checksum_header"
    assert r["source_authenticated"] is False


@pytest.mark.parametrize("where", ["compressed-header", "decoded-tail", "encoded-decoded-tail"])
def test_privacy_finishes_before_any_prefix_hash(where, monkeypatch):
    body = b"opaque"*200
    if where != "compressed-header":
        suffix = CONTACT.encode() if where == "decoded-tail" else b"%69%6e%76%65%6e%74%65%64%40unit.test"
        raw = _gzip(body + suffix, level=1)
        raw = raw[:3] + b"\x08" + raw[4:10] + b"n"*128 + b"\0" + raw[10:]
        assert suffix not in raw and CONTACT.encode() not in raw
    else:
        raw = b"\x1f\x8b\x08\x08" + bytes(6) + CONTACT.encode() + b"\0" + _gzip(body)[10:]
    calls = []
    monkeypatch.setattr(m, "_digest", lambda _: calls.append(True) or "a"*64)
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(raw)
    assert caught.value.phase == "privacy" and caught.value.code == "finite_prefix_screen_refused"
    assert calls == [] and CONTACT not in str(caught.value)


def test_private_value_after_observation_window_still_screened(monkeypatch):
    # Input is capped64KiB, so use a modest compressible but sub-ratio payload.
    raw = _gzip(b"x"*65540 + CONTACT.encode(), level=1)
    monkeypatch.setattr(m, "MAX_DECODED_BYTES", 1024*1024)
    # Raise only the ratio by padding legal gzip optional header, keeping the
    # actual decoder payload untouched and every compressed byte screened.
    raw = raw[:3] + b"\x08" + raw[4:10] + b"n"*1024 + b"\0" + raw[10:]
    calls = []
    monkeypatch.setattr(m, "_digest", lambda _: calls.append(True) or "a"*64)
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(raw)
    assert caught.value.phase == "privacy" and calls == []


@pytest.mark.parametrize("mutation", ["CRC", "ISIZE", "DEFLATE", "header-reserved", "trailing-nonmember"])
def test_observed_corruption_is_not_truncation_and_never_hashed(mutation, monkeypatch):
    raw = bytearray(_gzip(_tar()))
    if mutation == "CRC": raw[-8] ^= 1
    elif mutation == "ISIZE": raw[-4] ^= 1
    elif mutation == "DEFLATE": raw[10] = 0xff
    elif mutation == "header-reserved": raw[3] = 0x80
    else: raw.extend(b"not-a-gzip-member")
    calls = []
    monkeypatch.setattr(m, "_digest", lambda _: calls.append(True) or "a"*64)
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(bytes(raw))
    assert caught.value.phase == "gzip-prefix"
    assert caught.value.code == "invalid_gzip_prefix_or_observed_trailer" and not calls


@pytest.mark.parametrize("raw", [None, b"", bytearray(b"x"), memoryview(b"x"), b"x"*65537])
def test_input_is_exact_immutable_bounded_unit(raw):
    with pytest.raises(m.PrefixFormatError, match="immutable_prefix_byte_bound"):
        _inspect(raw)


@pytest.mark.parametrize("fixture", [1, 0, "yes", None])
def test_boolean_aliases_not_fixture_authority(fixture):
    with pytest.raises(m.PrefixFormatError, match="exact_fixture_boolean_required"):
        _inspect(_gzip(b"opaque"), fixture_only=fixture)


def test_actual_requires_contact_and_unscreened_fixture_explicit():
    with pytest.raises(m.PrefixFormatError, match="explicit_contact_required"):
        m.inspect_prefix(_gzip(b"opaque"), privacy_contact=None)
    r = m.inspect_prefix(_gzip(b"opaque"), privacy_contact=None, fixture_only=True)
    assert r["finite_privacy_screened"] is False and r["fixture_only"] is True


def test_decoded_quota_refuses_before_hash(monkeypatch):
    raw = _gzip(b"x"*4096)
    monkeypatch.setattr(m, "MAX_DECODED_BYTES", 4095)
    calls = []
    monkeypatch.setattr(m, "_digest", lambda _: calls.append(True) or "a"*64)
    with pytest.raises(m.PrefixFormatError, match="decoded_prefix_byte_bound"):
        _inspect(raw)
    assert not calls


def test_member_quota_refuses_before_hash(monkeypatch):
    raw = _gzip(b"one") + _gzip(b"two")
    monkeypatch.setattr(m, "MAX_GZIP_MEMBERS", 1)
    calls = []
    monkeypatch.setattr(m, "_digest", lambda _: calls.append(True) or "a"*64)
    with pytest.raises(m.PrefixFormatError, match="gzip_member_count_bound"):
        _inspect(raw)
    assert not calls


def test_actual_prefix_cap_invented_unit_is_incomplete_and_finitely_replayable():
    body = bytes(range(256))*400
    raw = _gzip(_tar(body))[:65536]
    assert len(raw) == 65536
    a = _inspect(raw)
    b = _inspect(raw)
    assert a == b and a["last_observed_gzip_member_incomplete"] is True
    assert a["first_tar_header_observation"]["first_physical_span_within_observation_prefix"] is False
    assert a["decoded_observation_bytes"] <= 65536
    assert len(m._raw(a)) < m.MAX_DESCRIPTOR_BYTES
