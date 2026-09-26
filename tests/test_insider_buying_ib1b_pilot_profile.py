"""Synthetic-only tests of the bounded, observed-header pilot preparation."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json

import pytest

from data.hashing import hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    SecBulkParsedSnapshotError,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
)
from research.insider_buying import sec_ib1b_pilot_profile as module


PROFILE_SHA = "54abe3073a83b4da9231aaa62b58b50907af2a6815f721890312b0f6c8a41f2e"
BINDINGS_SHA = "3ac52c110a641acf3c9420c2e32877d4a624cec73fcf041b5ba2a90047ad8f6f"
TABLES = (
    "SUBMISSION.tsv", "REPORTINGOWNER.tsv", "NONDERIV_TRANS.tsv",
    "NONDERIV_HOLDING.tsv", "DERIV_TRANS.tsv", "DERIV_HOLDING.tsv",
    "FOOTNOTES.tsv", "OWNER_SIGNATURE.tsv",
)


def _independent_sha(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def test_exact_nine_variant_profile_and_independent_hash():
    profile = module.approved_ib1b_schema_profile()
    assert len(profile.variants) == 9
    assert _independent_sha(profile.to_payload()) == PROFILE_SHA
    assert module.PILOT_SCHEMA_PROFILE_SHA256 == PROFILE_SHA
    assert module.PILOT_PERIODS == ((2022, 4), (2023, 1))
    assert tuple(dict.fromkeys(item.table_name for item in profile.variants)) == TABLES
    assert tuple(len(profile.variant_for(table, 2022, 4).headers) for table in TABLES) == (
        13, 13, 28, 14, 42, 26, 3, 3,
    )
    submission22 = profile.variant_for("SUBMISSION.tsv", 2022, 4)
    submission23 = profile.variant_for("SUBMISSION.tsv", 2023, 1)
    assert submission23.headers == submission22.headers + ("AFF10B5ONE",)
    assert submission22.headers[-1] == "REMARKS"
    assert "EXCERCISE_DATE" in profile.variant_for("DERIV_TRANS.tsv", 2022, 4).headers
    assert "EXERCISE_DATE" not in profile.variant_for("DERIV_TRANS.tsv", 2022, 4).headers
    assert "EXERCISE_DATE" in profile.variant_for("DERIV_HOLDING.tsv", 2022, 4).headers


@pytest.mark.parametrize("table", TABLES)
def test_only_transaction_keys_are_declared(table):
    expected = {
        "NONDERIV_TRANS.tsv": ("NONDERIV_TRANS_SK",),
        "DERIV_TRANS.tsv": ("DERIV_TRANS_SK",),
    }.get(table, ())
    for year, quarter in module.PILOT_PERIODS:
        assert module.approved_ib1b_schema_profile().variant_for(
            table, year, quarter
        ).source_row_key_headers == expected


@pytest.mark.parametrize("year,quarter", [(2022, 3), (2023, 2), (2026, 2)])
@pytest.mark.parametrize("table", TABLES)
def test_profile_does_not_extend_beyond_selected_window(table, year, quarter):
    with pytest.raises(SecBulkParsedSnapshotError, match="no exact quarter"):
        module.approved_ib1b_schema_profile().variant_for(table, year, quarter)


def test_factories_return_fresh_immutable_objects_and_detached_payloads():
    profile = module.approved_ib1b_schema_profile()
    other = module.approved_ib1b_schema_profile()
    assert profile == other and profile is not other
    assert profile.variants[0] is not other.variants[0]
    with pytest.raises(FrozenInstanceError):
        profile.profile_id = "wrong"
    payload = profile.to_payload()
    payload["variants"][0]["headers"].append("WRONG")
    module.verify_approved_ib1b_schema_profile(profile)
    bindings = module.approved_ib1b_archive_bindings()
    other_bindings = module.approved_ib1b_archive_bindings()
    assert bindings == other_bindings and bindings is not other_bindings
    assert bindings[0] is not other_bindings[0]
    assert bindings[0].header_receipts[0] is not other_bindings[0].header_receipts[0]
    with pytest.raises(FrozenInstanceError):
        bindings[0].archive_size_bytes = 1
    bindings[0].to_payload()["header_receipts"][0]["headers"].append("WRONG")
    module.verify_approved_ib1b_archive_bindings(bindings)


@pytest.mark.parametrize("field,value", [
    ("profile_id", "other"), ("variants", ()),
])
def test_changed_profile_fingerprint_is_refused(field, value):
    profile = module.approved_ib1b_schema_profile()
    object.__setattr__(profile, field, value)
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.verify_approved_ib1b_schema_profile(profile)


@pytest.mark.parametrize("field,value", [
    ("schema_id", "other"), ("table_name", "OWNER_SIGNATURE.tsv"),
    ("headers", ("ACCESSION_NUMBER",)), ("source_row_key_headers", ("FILING_DATE",)),
    ("valid_from_year", 2021), ("valid_from_quarter", 3),
    ("valid_through_year", 2024), ("valid_through_quarter", 2),
])
def test_changed_variant_fingerprint_is_refused(field, value):
    profile = module.approved_ib1b_schema_profile()
    object.__setattr__(profile.variants[0], field, value)
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.verify_approved_ib1b_schema_profile(profile)


@pytest.mark.parametrize("field,value", [
    ("schema_id", 1), ("table_name", b"SUBMISSION.tsv"),
    ("headers", ["ACCESSION_NUMBER"]), ("headers", (1,)),
    ("source_row_key_headers", []), ("source_row_key_headers", (1,)),
    ("valid_from_year", True), ("valid_from_quarter", 4.0),
    ("valid_through_year", "2022"), ("valid_through_quarter", None),
])
def test_variant_types_are_exact_not_json_coercible(field, value):
    profile = module.approved_ib1b_schema_profile()
    object.__setattr__(profile.variants[0], field, value)
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_schema_profile(profile)


def test_profile_and_nested_subclasses_are_refused_with_same_payload():
    class DerivedProfile(SecTsvSchemaProfile):
        pass

    class DerivedVariant(SecTsvSchemaVariant):
        pass

    profile = module.approved_ib1b_schema_profile()
    derived = DerivedProfile(profile.profile_id, profile.variants)
    assert derived.to_payload() == profile.to_payload()
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_schema_profile(derived)
    object.__setattr__(profile.variants[0], "__class__", DerivedVariant)
    assert hash_payload(profile.to_payload()) == PROFILE_SHA
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_schema_profile(profile)


@pytest.mark.parametrize("field", [
    "profile_id", "schema_id", "table_name", "headers",
    "valid_from_year", "valid_from_quarter", "valid_through_year", "valid_through_quarter",
])
def test_equal_value_scalar_subclasses_cannot_bypass_profile_exact_types(field):
    class DerivedString(str):
        pass

    class DerivedInteger(int):
        pass

    profile = module.approved_ib1b_schema_profile()
    target = profile if field == "profile_id" else profile.variants[0]
    value = getattr(target, field)
    if field == "headers":
        changed = (DerivedString(value[0]),) + value[1:]
    else:
        changed = DerivedString(value) if type(value) is str else DerivedInteger(value)
    object.__setattr__(target, field, changed)
    assert hash_payload(profile.to_payload()) == PROFILE_SHA
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_schema_profile(profile)


def test_factories_refuse_changed_internal_profile_constants(monkeypatch):
    headers = list(module._HEADERS_BY_TABLE)
    table, vector = headers[0]
    headers[0] = table, vector + ("WRONG",)
    monkeypatch.setattr(module, "_HEADERS_BY_TABLE", tuple(headers))
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.approved_ib1b_schema_profile()


def test_exact_archive_bindings_header_receipts_and_unverified_provenance():
    bindings = module.approved_ib1b_archive_bindings()
    assert module.PILOT_ARCHIVE_BINDINGS_SHA256 == BINDINGS_SHA
    assert _independent_sha([item.to_payload() for item in bindings]) == BINDINGS_SHA
    assert [(item.year, item.quarter) for item in bindings] == [(2022, 4), (2023, 1)]
    assert [item.archive_size_bytes for item in bindings] == [8400983, 13882049]
    assert [item.archive_sha256 for item in bindings] == [
        "6c6a909bd2eaaa0a24ccf5f0071b404670c115845d2939bc592bf3ce420dcdb9",
        "0b476188f52a0862e71886eb31a81f6345fc6616403b52188484aef0438cfcfb",
    ]
    assert [item.local_last_write_utc for item in bindings] == [
        "2026-09-24T22:53:37.3844487Z", "2026-09-24T22:53:38.4646512Z",
    ]
    assert [sum(row.expanded_size_bytes for row in item.header_receipts) for item in bindings] == [
        51839037, 90806476,
    ]
    for binding in bindings:
        assert binding.source_provenance_verified is False
        assert binding.timestamp_basis == "local filesystem last-write time; not SEC-attested"
        assert binding.capture_git_commit == "a4192546b168470ff1e9c421d8bd53531a1b3c05"
        assert binding.source_url.endswith("/" + binding.filename)
        assert tuple(row.table_name for row in binding.header_receipts) == TABLES
        assert "retrieved_at" not in binding.to_payload()
        for row in binding.header_receipts:
            line = ("\t".join(row.headers) + "\n").encode("ascii")
            assert len(line) == row.header_line_size_bytes
            assert hashlib.sha256(line).hexdigest() == row.header_line_sha256


@pytest.mark.parametrize("field,value", [
    ("archive_sha256", "f" * 64), ("archive_size_bytes", 1),
    ("capture_git_commit", "b" * 40),
    ("local_last_write_utc", "2026-09-25T22:53:37.3844487Z"),
])
def test_coherent_changed_archive_binding_is_refused_by_literal_fingerprint(field, value):
    bindings = module.approved_ib1b_archive_bindings()
    changed = (replace(bindings[0], **{field: value}), bindings[1])
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.verify_approved_ib1b_archive_bindings(changed)


@pytest.mark.parametrize("change", ["reordered", "missing", "extra", "list"])
def test_binding_window_order_and_container_types_are_exact(change):
    bindings = module.approved_ib1b_archive_bindings()
    changed = {
        "reordered": bindings[::-1], "missing": bindings[:1],
        "extra": bindings + bindings[:1], "list": list(bindings),
    }[change]
    with pytest.raises(module.Ib1bPilotProfileError):
        module.verify_approved_ib1b_archive_bindings(changed)


@pytest.mark.parametrize("field,value", [
    ("year", True), ("year", 2021), ("quarter", 2),
    ("archive_size_bytes", 0), ("archive_size_bytes", 1.0),
    ("filename", "../2022q4_form345.zip"), ("source_url", "https://example.com/data.zip"),
    ("archive_sha256", "F" * 64), ("capture_git_commit", "z" * 40),
    ("local_last_write_utc", "2026-09-24T22:53:37.384448Z"),
    ("timestamp_basis", "SEC authenticated retrieval"),
    ("source_provenance_verified", True), ("source_provenance_verified", 0),
    ("header_receipts", []), ("header_receipts", ()),
])
def test_malformed_or_promoted_archive_receipts_are_refused(field, value):
    binding = module.approved_ib1b_archive_bindings()[0]
    with pytest.raises(module.Ib1bPilotProfileError):
        replace(binding, **{field: value})


@pytest.mark.parametrize("field", [
    "year", "quarter", "archive_size_bytes", "filename", "archive_sha256",
    "source_url", "capture_git_commit", "local_last_write_utc", "timestamp_basis",
])
def test_equal_value_archive_scalar_subclasses_cannot_bypass_exact_types(field):
    class DerivedString(str):
        pass

    class DerivedInteger(int):
        pass

    bindings = module.approved_ib1b_archive_bindings()
    value = getattr(bindings[0], field)
    changed = DerivedString(value) if type(value) is str else DerivedInteger(value)
    object.__setattr__(bindings[0], field, changed)
    assert hash_payload([item.to_payload() for item in bindings]) == BINDINGS_SHA
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_archive_bindings(bindings)


@pytest.mark.parametrize("field,value", [
    ("table_name", "other.tsv"), ("headers", []), ("headers", ("é",)),
    ("header_line_sha256", "f" * 64), ("header_line_size_bytes", 1),
    ("header_line_size_bytes", True), ("expanded_size_bytes", 0),
])
def test_header_receipts_fail_closed(field, value):
    receipt = module.approved_ib1b_archive_bindings()[0].header_receipts[0]
    with pytest.raises(module.Ib1bPilotProfileError):
        replace(receipt, **{field: value})


def test_nested_receipt_mutation_subclass_and_reordered_table_cannot_pass():
    class DerivedReceipt(module.PilotHeaderReceipt):
        pass

    bindings = module.approved_ib1b_archive_bindings()
    object.__setattr__(bindings[0].header_receipts[0], "expanded_size_bytes", 5000000)
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.verify_approved_ib1b_archive_bindings(bindings)
    bindings = module.approved_ib1b_archive_bindings()
    object.__setattr__(bindings[0].header_receipts[0], "__class__", DerivedReceipt)
    with pytest.raises(module.Ib1bPilotProfileError, match="types are not exact"):
        module.verify_approved_ib1b_archive_bindings(bindings)
    bindings = module.approved_ib1b_archive_bindings()
    changed = (replace(bindings[0], header_receipts=bindings[0].header_receipts[::-1]), bindings[1])
    with pytest.raises(module.Ib1bPilotProfileError, match="fingerprint"):
        module.verify_approved_ib1b_archive_bindings(changed)
