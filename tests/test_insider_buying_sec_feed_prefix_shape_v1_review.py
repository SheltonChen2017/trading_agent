"""Independent invented-only sequential prefix geometry and privacy barriers."""
from __future__ import annotations

import gzip
import hashlib
import json
import random

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_prefix_shape_v1 as m


CONTACT = "invented-shape-private@unit.test"


def _header(name=b"unreturned-invented.nc", *, size=0, kind=b"0", magic="posix"):
    value = bytearray(512)
    value[:len(name)] = name
    value[124:136] = format(size, "011o").encode()+b"\0"
    value[148:156] = b"        "
    value[156:157] = kind
    if magic == "posix":
        value[257:265] = b"ustar\x0000"
    elif magic == "gnu":
        value[257:265] = b"ustar  \0"
    elif magic == "unknown":
        value[257:265] = b"unknown!"
    else:
        assert magic == "v7"
    value[148:156] = format(sum(value), "06o").encode()+b"\0 "
    return bytes(value)


def _member(body=b"", **kwargs):
    return _header(size=len(body), **kwargs)+body+bytes((-len(body)) % 512)


def _gzip(body):
    raw = gzip.compress(body, mtime=0)
    assert 0 < len(raw) <= m.core.MAX_PREFIX_BYTES
    return raw


def _qualify(body, **kwargs):
    return m.qualify_prefix_shape(_gzip(body), privacy_contact=CONTACT, fixture_only=True, **kwargs)


@pytest.mark.parametrize("magic,expected", (
    ("posix", "posix_ustar_NUL00"), ("gnu", "old_gnu_ustar_spaces_NUL"),
    ("v7", "v7_zero_tail"), ("unknown", "unknown"),
))
def test_review_magic_is_finite_observation_not_logical_schema_validation(magic, expected):
    result = _qualify(_member(name=b"unreturned-directory/", kind=b"5", magic=magic)+bytes(1024))
    shape = result["physical_shape_observations"]
    row = shape["headers"][0]
    assert row["magic_pattern_observation"] == expected
    assert row["header_checksum_matches"] is True
    assert row["logical_name_profile_validated"] is row["admitted"] is False
    assert result["PDS_or_GNU_logical_name_profile_validated"] is False
    assert result["whole_carrier_CRC_ISIZE_EOF_or_privacy_verified"] is False
    assert "unreturned-directory" not in json.dumps(result)
    assert shape["status"] == ("unknown_magic_pattern_stop" if magic == "unknown"
        else "two_zero_blocks_observed_not_whole_carrier_EOF")


def test_review_second_sequential_header_beyond_64KiB_is_observed_without_payload_scan(monkeypatch):
    payload = random.Random(381).randbytes(20000)+b"public-padding-"*5000
    first = _member(payload, name=b"first-unreturned.nc")
    body = first+_member(name=b"second-unreturned/", kind=b"5")+bytes(1024)
    assert len(first) > m.core.MAX_OBSERVATION_BYTES
    calls = []
    original = m._ShapeObserver.feed

    def feed(self, data, *, final=False):
        calls.append((len(data), final))
        return original(self, data, final=final)

    monkeypatch.setattr(m._ShapeObserver, "feed", feed)
    result = _qualify(body)
    shape = result["physical_shape_observations"]
    assert sum(length for length, _ in calls) == len(body) > 65536
    assert calls[-1] == (0, True)
    assert shape["decoded_bytes_observed"] == len(body)
    assert shape["observed_complete_headers"] == 2
    assert shape["headers"][1]["header_range"] == [len(first), len(first)+512]
    assert shape["headers"][0]["payload_bytes_observed"] == len(payload)
    assert result["prefix_format_descriptor"]["decoded_observation_bytes"] == 65536


def test_review_valid_512_aligned_header_inside_payload_never_becomes_a_member():
    misleading = _header(name=b"must-not-be-a-physical-row.nc", kind=b"5")
    payload = bytes(512)+misleading+bytes(512)
    first = _member(payload, name=b"outer-unreturned.nc")
    body = first+_member(name=b"actual-following/", kind=b"5")+bytes(1024)
    shape = _qualify(body)["physical_shape_observations"]
    assert shape["observed_complete_headers"] == 2
    assert [row["header_range"][0] for row in shape["headers"]] == [0, len(first)]
    assert shape["headers"][0]["declared_payload_bytes"] == len(payload)
    assert shape["status"] == "two_zero_blocks_observed_not_whole_carrier_EOF"


def test_review_checksum_corruption_is_not_mislabeled_as_expected_prefix_truncation():
    bad = bytearray(_header())
    bad[0] ^= 1
    corrupt = _qualify(bytes(bad)+_member())
    shape = corrupt["physical_shape_observations"]
    assert shape["status"] == "observed_invalid_header_checksum"
    assert shape["observed_complete_headers"] == 1
    assert shape["following_bytes_not_interpreted"] == 512
    partial = _qualify(_header(size=200)+b"a"*73)["physical_shape_observations"]
    assert partial["status"] == "prefix_ended_with_partial_payload"
    assert partial["headers"][0]["payload_bytes_observed"] == 73
    assert partial["headers"][0]["complete_physical_span_observed_within_prefix"] is False


@pytest.mark.parametrize("kind", (b"x", b"g", b"L", b"K", b"S", b"1", b"2"))
def test_review_extensions_and_links_stop_without_interpreting_following_names(kind):
    body = _member(kind=kind)+_member(name=b"must-not-follow.nc")
    shape = _qualify(body)["physical_shape_observations"]
    assert shape["status"] == "unsupported_type_or_extension_stop"
    assert shape["observed_complete_headers"] == 1
    assert shape["following_bytes_not_interpreted"] == 512
    assert shape["headers"][0]["admitted"] is False


def test_review_late_decoded_private_echo_precedes_shape_construction_and_any_prefix_hash(monkeypatch):
    body = _member(random.Random(9).randbytes(20000)+b"public-padding-"*5000+CONTACT.encode())
    raw = _gzip(body)
    assert CONTACT.encode() not in raw
    raw_screen = m.core.frozen.privacy_v2._TextScreen(CONTACT)
    for at in range(0, len(raw), 1024):
        raw_screen.feed(raw[at:at+1024])
    raw_screen.feed(b"", final=True)
    monkeypatch.setattr(m.core, "_digest", lambda raw: pytest.fail("private prefix was hashed"))
    monkeypatch.setattr(m, "_ShapeObserver", lambda *a, **k: pytest.fail("shape preceded complete privacy"))
    with pytest.raises(m.PrefixShapeError) as caught:
        m.qualify_prefix_shape(raw, privacy_contact=CONTACT, fixture_only=True)
    assert (caught.value.phase, caught.value.code) == ("privacy", "finite_prefix_screen_refused")


@pytest.mark.parametrize("limits,expected", (
    (m.ShapeLimits(header_count=1), "header_count_bound"),
    (m.ShapeLimits(metadata_bytes=200), "header_metadata_bound"),
))
def test_review_capacity_failure_never_returns_a_partial_shape(limits, expected):
    with pytest.raises(m.PrefixShapeError) as caught:
        _qualify(_member()+_member(name=b"second.nc"), limits=limits)
    assert (caught.value.phase, caught.value.code) == ("capacity", expected)


@pytest.mark.parametrize("limits", ({}, m.ShapeLimits(header_count=True), m.ShapeLimits(metadata_bytes=False)))
def test_review_limits_never_accept_boolean_aliases_or_arbitrary_types(limits):
    with pytest.raises(m.PrefixShapeError) as caught:
        _qualify(_member(), limits=limits)
    assert caught.value.phase == "input"


def test_review_public_rows_never_return_raw_names_or_name_header_hashes():
    name = b"0123456789-21-123456.nc"
    header = _header(name=name)
    result = _qualify(header+bytes(1024))
    row = result["physical_shape_observations"]["headers"][0]
    assert row["fixed_name_fields_match_accession_nc_routing_pattern"] is True
    rendered = json.dumps(result)
    for forbidden in (name.decode(), hashlib.sha256(name).hexdigest(), hashlib.sha256(header).hexdigest()):
        assert forbidden not in rendered
    for key in ("dependency_pin_runtime_attested_here", "member_names_routes_decoded_values_or_their_hashes_returned",
            "whole_carrier_population_known", "identity_or_PIT_or_rights_or_admission_verified",
            "earlier_failed_archive_cause_established", "backtesting_ready"):
        assert result[key] is False
    for key in ("files_read_written", "new_requests", "SDK_calls", "outcome_looks"):
        assert type(result[key]) is int and result[key] == 0
