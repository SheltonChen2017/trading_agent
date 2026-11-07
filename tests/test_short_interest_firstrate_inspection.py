"""Fabricated byte archives only; never actual USB/source, outcomes or rights."""
import io
import json
import socket
import struct
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes
from research.short_interest_etf import firstrate_short_interest_inspection as subject


HEADER = ",".join(subject.HEADER) + "\n"
BASE = "2026-01-30,12,4,3\n"


def archive(rows=BASE, *, name="FABRICATED_short_interest.csv", header=HEADER,
            compression=zipfile.ZIP_DEFLATED, members=None, attributes=0o600 << 16,
            extra=b"", comment=b"", zip_comment=b""):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for filename, content in (members if members is not None else ((name, header + rows),)):
            info = zipfile.ZipInfo(filename, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = compression
            info.external_attr = attributes
            info.extra, info.comment = extra, comment
            zipped.writestr(info, content)
        zipped.comment = zip_comment
    return output.getvalue()


def inspect(raw):
    return subject.inspect_archive(raw, expected_sha256=hash_bytes(raw))


def observed(raw):
    return inspect(raw).to_payload()["archive"]


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network is outside this fabricated pure inspector")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def test_registered_policy_freezes_actual_bytes_and_every_authority_stays_false():
    policy = subject.inspection_policy()
    assert policy["registered_pins"]["full"] == {"bytes": 34319601,
        "sha256": "08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8"}
    report = inspect(archive()).to_payload()
    flags = report["authority"]
    assert flags["inspection_only"] is True
    assert all(value is False or type(value) is int and value == 0
        for key, value in flags.items() if key != "inspection_only")
    assert report["archive"]["all_members_CRC_verified"] is True
    assert report["archive"]["complete_byte_inspection"] is True
    policy["authority"]["source_admitted"] = True
    assert subject.inspection_policy()["authority"]["source_admitted"] is False


@pytest.mark.parametrize("method", (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED))
def test_exact_supported_archives_observe_complete_rows_without_raw_exports(method):
    raw = archive(compression=method)
    report = inspect(raw)
    payload = report.to_payload()
    assert payload["archive"]["rows"] == payload["archive"]["structurally_clear_rows"] == 1
    assert payload["archive"]["quarantined_rows"] == 0
    assert payload["archive"]["earliest_settlement_date"] == "2026-01-30"
    assert report.sha256 == hash_bytes(canonical_json(payload).encode())
    assert "FABRICATED" not in canonical_json(payload)
    assert not any(hasattr(report, name) for name in ("rows", "iter_rows", "cells", "counts", "to_native"))


def test_sealed_report_detaches_payload_and_refuses_reflection_reinitialization():
    value = inspect(archive())
    changed = value.to_payload(); changed["authority"]["source_admitted"] = True
    assert value.to_payload()["authority"]["source_admitted"] is False
    with pytest.raises(subject.FirstRateInspectionRefusal, match="factory"):
        value.__init__()
    object.__setattr__(value, "_raw", b"changed")
    with pytest.raises(subject.FirstRateInspectionRefusal, match="seal_changed"):
        value.to_payload()
    empty = object.__new__(subject.FirstRateByteInspection)
    with pytest.raises(subject.FirstRateInspectionRefusal, match="seal_changed"):
        empty.to_payload()


@pytest.mark.parametrize("raw,sha", ((b"", "0" * 64), (bytearray(b"x" * 22), "0" * 64),
    (b"x" * 22, "private"), (b"x" * 22, "0" * 64)))
def test_hash_bounds_and_exact_immutable_type_precede_parsing(raw, sha):
    with pytest.raises(subject.FirstRateInspectionRefusal, match="archive_bytes_and_SHA"):
        subject.inspect_archive(raw, expected_sha256=sha)


@pytest.mark.parametrize("name", ("../SECRET_short_interest.csv", "/SECRET_short_interest.csv",
    "a_short_interest.csv", "SECRET.csv", "SECRET_short_interest.csv/", "A\\B_short_interest.csv",
    "A\x00_short_interest.csv", "A_short_interest.csv:stream"))
def test_unsafe_or_unknown_names_cannot_be_adopted(name):
    with pytest.raises(subject.FirstRateInspectionRefusal):
        inspect(archive(name=name))


def test_duplicate_archive_names_refuse_instead_of_last_member_wins():
    with pytest.warns(UserWarning, match="Duplicate"):
        raw = archive(members=(("FAB_short_interest.csv", HEADER + BASE),) * 2)
    with pytest.raises(subject.FirstRateInspectionRefusal, match="name_type_or_alias"):
        inspect(raw)


@pytest.mark.parametrize("kwargs", ({"attributes": 0o120600 << 16}, {"attributes": (0o40600 << 16) | 0x10},
    {"extra": b"\x01\x00\x00\x00"}, {"comment": b"hidden"}, {"zip_comment": b"hidden"},
    {"compression": zipfile.ZIP_BZIP2}))
def test_links_directories_extras_comments_and_unknown_compression_refuse(kwargs):
    with pytest.raises(subject.FirstRateInspectionRefusal):
        inspect(archive(**kwargs))


def test_trailing_prefixed_and_truncated_bytes_are_not_ignored():
    raw = archive()
    for changed in (raw + b"hidden", b"hidden" + raw, raw[:-1]):
        with pytest.raises(subject.FirstRateInspectionRefusal): inspect(changed)


def change_field(raw, at, width, value):
    changed = bytearray(raw); changed[at:at + width] = value.to_bytes(width, "little")
    return bytes(changed)


@pytest.mark.parametrize("offset,width,value", ((6, 2, 1), (8, 2, 99), (14, 4, 1),
    (18, 4, 1), (22, 4, 1), (26, 2, 1), (28, 2, 1)))
def test_local_central_discordance_refuses(offset, width, value):
    with pytest.raises(subject.FirstRateInspectionRefusal):
        inspect(change_field(archive(), offset, width, value))


def test_encrypted_or_descriptor_flags_rejected_even_with_matching_headers():
    raw = archive(); central = raw.index(b"PK\x01\x02")
    for flags in (1, 8, 2048):
        changed = change_field(change_field(raw, 6, 2, flags), central + 8, 2, flags)
        with pytest.raises(subject.FirstRateInspectionRefusal, match="central_format"):
            inspect(changed)


def test_CRC_corruption_is_not_structural_success():
    raw = archive(compression=zipfile.ZIP_STORED)
    changed = raw.replace(b",12,4,3", b",13,4,3")
    with pytest.raises(subject.FirstRateInspectionRefusal, match="CRC"):
        inspect(changed)


def test_deflate_unused_suffix_is_not_hidden_inside_declared_compressed_range():
    raw = archive(); central = raw.index(b"PK\x01\x02"); end = len(raw) - 22
    compressed = int.from_bytes(raw[18:22], "little")
    changed = raw[:central] + b"X" + raw[central:]
    changed = change_field(changed, 18, 4, compressed + 1)
    changed = change_field(changed, central + 1 + 20, 4, compressed + 1)
    changed = change_field(changed, end + 1 + 16, 4, central + 1)
    with pytest.raises(subject.FirstRateInspectionRefusal, match="deflate_extent"):
        inspect(changed)


@pytest.mark.parametrize("bound,value", (("MAXIMUM_ARCHIVE_BYTES", 22), ("MAXIMUM_INFLATED_BYTES", 1),
    ("MAXIMUM_MEMBER_BYTES", 1), ("MAXIMUM_MEMBERS", 0), ("MAXIMUM_ROWS", 0)))
def test_each_finite_limit_is_causal(monkeypatch, bound, value):
    raw = archive(); monkeypatch.setattr(subject, bound, value)
    with pytest.raises(subject.FirstRateInspectionRefusal): inspect(raw)


@pytest.mark.parametrize("header", ("wrong,short_interest,avg_daily_share_volume,days_to_cover\n",
    HEADER.rstrip() + ",extra\n", "\ufeff" + HEADER, HEADER.replace("settlement_date", "settlement_date ")))
def test_exact_header_cannot_be_guessed(header):
    with pytest.raises(subject.FirstRateInspectionRefusal, match="header"):
        inspect(archive(header=header))


@pytest.mark.parametrize("row,reason", (("2026-01-30,1,2\n", "row_width"),
    ("2026-01-30,1,2,3,extra\n", "row_width"), ("\n", "row_width"),
    ("20260130,1,2,3\n", "settlement_date"), ("2026-02-30,1,2,3\n", "settlement_date"),
    ("2026-01-30,1.5,2,3\n", "short_interest_nonintegral"),
    ("2026-01-30,NaN,2,3\n", "short_interest_numeric"),
    ("2026-01-30,1,Infinity,3\n", "avg_daily_share_volume_numeric"),
    ("2026-01-30,1,2,-3\n", "days_to_cover_numeric"),
    ("2026-01-30,1,2,\n", "days_to_cover_numeric"),
    ("2026-01-30,1,2, 3\n", "days_to_cover_numeric"),
    ("2026-01-30,1,2," + "1" * 129 + "\n", "field_length")))
def test_malformed_rows_are_origin_committed_and_quarantined_without_value_disclosure(row, reason):
    report = observed(archive(row))
    assert report["rows"] == report["quarantined_rows"] == report["row_reason_counts"][reason] == 1
    assert report["structurally_clear_rows"] == 0
    assert len(report["member_origin_disposition_commitment_sha256"]) == 64


@pytest.mark.parametrize("token", ("1e1000000", "1e-1000000", "0e-1000000", "1e31", "-1"))
def test_numeric_bounds_precede_fraction_expansion(monkeypatch, token):
    def forbidden(*args): pytest.fail("unbounded Fraction construction")
    monkeypatch.setattr(subject, "Fraction", forbidden)
    assert subject._number(token) is None


def test_numeric_inspection_is_independent_of_ambient_decimal_exponent_and_precision():
    from decimal import localcontext
    raw = archive("2026-01-30,100000000000000000000,0.25,77\n")
    original = observed(raw)
    with localcontext() as context:
        context.Emax, context.Emin, context.prec = 10, -10, 2
        assert observed(raw) == original


def test_coordinated_reflective_reseal_cannot_reissue_report_or_positive_authority():
    value = inspect(archive())
    payload = value.to_payload()
    payload["authority"]["source_admitted"] = True
    raw = canonical_json(payload).encode()
    anchor = raw, hash_bytes(raw)
    for key, item in (("_raw", raw), ("_sha", anchor[1]),
                      ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(value, key, item)
    with pytest.raises(subject.FirstRateInspectionRefusal, match="inspection_seal_changed"):
        value.to_payload()


def test_fractional_average_is_exact_and_independent_DTC_is_never_replaced():
    value = observed(archive("2026-01-30,12,0.25,999.123456789\n2026-02-13,9,0,77\n"))
    assert value["structurally_clear_rows"] == 2 and value["quarantined_rows"] == 0
    assert value["reported_field_observations"] == {"fractional_average_volume": 1,
        "zero_average_volume": 1, "zero_average_volume_positive_SI": 1,
        "zero_average_volume_positive_reported_DTC": 1}
    assert value["DTC_recalculated_or_substituted"] is False
    assert "999.123456789" not in canonical_json(value)


def test_all_duplicate_peers_quarantined_even_when_one_has_bad_numeric_fields():
    value = observed(archive(BASE + "2026-01-30,wrong,4,3\n"))
    assert value["rows"] == value["quarantined_rows"] == 2
    assert value["row_reason_counts"]["duplicate_settlement_all_peers"] == 2
    assert value["row_reason_counts"]["short_interest_numeric"] == 1


def test_collision_grouping_does_not_adopt_whitespace_date():
    value = observed(archive(BASE + " 2026-01-30,12,4,3\n"))
    assert value["quarantined_rows"] == 2
    assert value["row_reason_counts"]["duplicate_settlement_all_peers"] == 2
    assert value["row_reason_counts"]["settlement_date"] == 1


def test_reverse_order_is_not_reordered_or_refused_and_lexical_changes_change_origin():
    first = observed(archive("2026-02-13,12,4,3\n" + BASE))
    second = observed(archive("2026-02-13,12.0,4,3\n" + BASE))
    assert first["structurally_clear_rows"] == second["structurally_clear_rows"] == 2
    assert first["member_origin_disposition_commitment_sha256"] != second["member_origin_disposition_commitment_sha256"]


def toy_registered(monkeypatch, full, year, *, duplicate_manifest=False):
    # Explicit fixture-only byte-pin seam, never the production USB snapshot.
    readme = b"FABRICATED supplied short-interest description, no rights or availability proof"
    import hashlib
    manifest = {"fundamentals/Short_Interest/" + suffix: {"ok": True, "bytes": len(raw),
        "md5": hashlib.md5(raw).hexdigest(), "url": "private-not-output", "path": "private-not-output"}
        for suffix, raw in (("Full_Dataset", full), ("2026_data_only", year), ("Read_Me_Documentation", readme))}
    encoded = canonical_json(manifest).encode()
    if duplicate_manifest:
        encoded = b'{"duplicate":0,"duplicate":1}'
    monkeypatch.setattr(subject, "_PINS", {name: (len(raw), hash_bytes(raw)) for name, raw in
        (("full", full), ("year", year), ("manifest", encoded), ("readme", readme))})
    return full, year, encoded, readme


def test_registered_pair_exact_year_multisets_compare_without_raw_or_order_export(monkeypatch):
    full = archive("2025-12-31,10,2,5\n" + BASE + "2026-02-13,3,1,3\n")
    year = archive("2026-02-13,3,1,3\n" + BASE)
    value = subject.inspect_registered_pair(*toy_registered(monkeypatch, full, year)).to_payload()
    assert value["year_is_exact_full_2026_token_multiset_subset"] is True
    assert value["paired_member_mismatches"] == 0
    assert value["full"]["year_2026_rows"] == value["year"]["rows"] == 2
    assert not value["authority"]["source_admitted"]
    assert "private-not-output" not in canonical_json(value)


@pytest.mark.parametrize("rows", ("2026-01-30,12.0,4,3\n", BASE + BASE, "2025-12-31,12,4,3\n", ""))
def test_pair_mismatch_is_retained_and_never_becomes_admission(monkeypatch, rows):
    full, year = archive(BASE), archive(rows)
    value = subject.inspect_registered_pair(*toy_registered(monkeypatch, full, year)).to_payload()
    assert value["year_is_exact_full_2026_token_multiset_subset"] is False
    assert value["paired_member_mismatches"] == 1
    assert not value["authority"]["source_admitted"]


def test_production_pair_does_not_accept_fabricated_bytes_or_caller_hashes():
    with pytest.raises(subject.FirstRateInspectionRefusal, match="registered_original_blob_pin"):
        subject.inspect_registered_pair(archive(), archive(), b"{}", b"fabricated")


def test_duplicate_manifest_keys_are_refused_not_last_wins(monkeypatch):
    args = toy_registered(monkeypatch, archive(), archive(), duplicate_manifest=True)
    with pytest.raises(subject.FirstRateInspectionRefusal, match="manifest_duplicate_key"):
        subject.inspect_registered_pair(*args)


def test_defective_UTF8_and_unclosed_CSV_quote_refuse_safely():
    for rows in (b"\xff", '"unfinished'):
        content = HEADER.encode() + rows if type(rows) is bytes else HEADER + rows
        raw = archive(members=(("FAB_short_interest.csv", content),))
        with pytest.raises(subject.FirstRateInspectionRefusal, match="CSV_encoding_or_structure"):
            inspect(raw)
