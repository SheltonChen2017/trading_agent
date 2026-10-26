"""Independent invented-only bounded-prefix observations and crypto barriers."""
from __future__ import annotations

import gzip
import json
import random

import pytest

from research import insider_buying_sec_feed_prefix_format_v1 as m


CONTACT = "invented-prefix@unit.test"


def _inspect(raw):
    return m.inspect_prefix(raw, privacy_contact=CONTACT, fixture_only=True)


def _tar(body, name=b"unreturned-public-name.nc"):
    header = bytearray(512)
    header[:len(name)] = name
    header[124:136] = format(len(body), "011o").encode()+b"\0"
    header[148:156] = b"        "
    header[156:157] = b"0"
    header[257:265] = b"ustar\0"+b"00"
    header[148:156] = format(sum(header), "06o").encode()+b"\0 "
    return bytes(header)+body+bytes((-len(body)) % 512)+bytes(1024)


@pytest.mark.parametrize("cut", (1, 4, 9, 10, -8, -4, -1))
def test_review_truncated_gzip_unit_is_not_a_verified_whole_carrier(cut):
    full = gzip.compress(b"public invented observation", mtime=0)
    result = _inspect(full[:cut])
    assert result["last_observed_gzip_member_incomplete"] is True
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 0
    assert result["whole_carrier_CRC_ISIZE_or_EOF_verified"] is False
    assert result["whole_carrier_privacy_screened"] is False
    assert result["whole_carrier_hashed_or_retained"] is False
    assert result["complete_member_population_known"] is False


def test_review_complete_then_partial_member_counts_only_observed_valid_trailer():
    raw = gzip.compress(b"first public member", mtime=0)+gzip.compress(b"second public member", mtime=0)[:-4]
    result = _inspect(raw)
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 1
    assert result["last_observed_gzip_member_incomplete"] is True
    assert result["whole_carrier_CRC_ISIZE_or_EOF_verified"] is False


@pytest.mark.parametrize("offset", (0, 256, 266))
def test_review_marker_offsets_are_only_observations_not_fixed_PDS_or_identity(offset):
    body = b"p"*offset+b"<SUBMISSION>opaque invented</SUBMISSION>"
    result = _inspect(gzip.compress(_tar(body), mtime=0))
    observed = result["first_tar_header_observation"]
    assert observed["header_checksum_matches"] is True
    assert observed["payload_opening_markers"] == [{"offset": offset, "family": "SUBMISSION"}]
    assert observed["PDS_control_validated"] is False
    assert observed["whole_member_integrity_verified"] is False
    assert result["completed_gzip_members_with_observed_valid_trailers"] == 1
    assert result["whole_carrier_CRC_ISIZE_or_EOF_verified"] is False
    assert result["PDS_controls_validated"] is result["acceptance_or_PIT_verified"] is False
    assert "unreturned-public-name.nc" not in json.dumps(result)


def test_review_late_decoded_echo_beyond_observation_window_refuses_before_hash(monkeypatch):
    # Keep compression ratio comfortably below128 while decoded bytes extend
    # beyond the transient64KiB observation buffer.
    noise = random.Random(42).randbytes(16384)
    safe_body = noise+b"public-padding-"*5000+b"safe final text"
    safe = gzip.compress(safe_body, mtime=0)
    assert len(safe) < m.MAX_PREFIX_BYTES
    assert _inspect(safe)["decoded_prefix_bytes"] > m.MAX_OBSERVATION_BYTES
    private = gzip.compress(noise+b"public-padding-"*5000+CONTACT.encode(), mtime=0)
    assert CONTACT.encode() not in private
    raw_screen = m.frozen.privacy_v2._TextScreen(CONTACT)
    for at in range(0, len(private), 1024):
        raw_screen.feed(private[at:at+1024])
    raw_screen.feed(b"", final=True)
    monkeypatch.setattr(m, "_digest", lambda raw: pytest.fail("prefix hash preceded complete decoded privacy"))
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(private)
    assert (caught.value.phase, caught.value.code) == ("privacy", "finite_prefix_screen_refused")


def test_review_raw_optional_gzip_name_echo_refuses_before_decode_hash(monkeypatch):
    plain = gzip.compress(b"public body", mtime=0)
    # Insert a legal gzip FNAME containing only an invented private value.
    raw = plain[:3]+bytes((plain[3] | 8,))+plain[4:10]+CONTACT.encode()+b"\0"+plain[10:]
    monkeypatch.setattr(m, "_digest", lambda raw: pytest.fail("prefix hash preceded raw privacy"))
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(raw)
    assert caught.value.phase == "privacy"


def test_review_observed_corrupt_trailer_refuses_before_hash(monkeypatch):
    raw = bytearray(gzip.compress(b"public body", mtime=0))
    raw[-8] ^= 1
    monkeypatch.setattr(m, "_digest", lambda raw: pytest.fail("prefix hash preceded observed trailer validation"))
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(bytes(raw))
    assert caught.value.phase == "gzip-prefix"


def test_review_decoded_quota_exhaustion_is_not_a_retained_truncated_success(monkeypatch):
    raw = gzip.compress(bytes(range(256))*2, mtime=0)
    monkeypatch.setattr(m, "MAX_DECODED_BYTES", 100)
    monkeypatch.setattr(m, "_digest", lambda raw: pytest.fail("prefix hash preceded decoded quota"))
    with pytest.raises(m.PrefixFormatError) as caught:
        _inspect(raw)
    assert (caught.value.phase, caught.value.code) == ("capacity", "decoded_prefix_byte_bound")
