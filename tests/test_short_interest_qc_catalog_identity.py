"""Fabricated offline metadata only; no authenticated API or source access."""
import pytest
from data.hashing import canonical_json, hash_bytes
import scripts.short_interest_qc_catalog_identity as m


def row(identifier, created="2023-01-03 14:30:00", **changes):
    value = {"id": identifier, "created": created, "description": "not-public-description",
        "leanHash": "a" * 40, "leanCloudHash": "b" * 40,
        "name": "master", "ref": "refs/heads/master", "public": True}
    value.update(changes)
    return value


def observe(monkeypatch, rows):
    raw = canonical_json({"versions": rows, "success": True}).encode()
    monkeypatch.setattr(m, "REGISTERED_RAW_SHA256", hash_bytes(raw))
    return m.qualify_captured_identity(raw)


def test_unspecified_clock_preserved_not_invented_UTC_or_recency(monkeypatch):
    result = observe(monkeypatch, [row(2, "2020-01-01 00:00:00"), row(1, "2026-01-01T00:00:00Z")])
    assert result["selected"]["id"] == 2
    assert result["selected"]["created"] == "2020-01-01 00:00:00"
    assert result["selected_created_basis"] == "unspecified_wall_clock_not_a_timestamp"
    assert result["selection_is_latest_build_claim"] is False
    assert result["execution_admitted"] is result["source_processing_permission"] is False
    assert "not-public-description" not in canonical_json(result)


@pytest.mark.parametrize("created", [None, "0001-01-01 00:00:00", "2023-02-30 00:00:00", "2023-01-01", "2023-01-01T00:00:00-05:00", "private-contact@example.com"])
def test_missing_invalid_or_unsupported_clock_cannot_be_fabricated(monkeypatch, created):
    assert observe(monkeypatch, [row(1, created)])["selected"] is None


@pytest.mark.parametrize("changes", [{"public": False}, {"public": 1}, {"id": True}, {"leanHash": "a" * 64}, {"ref": "contact@example.com"}, {"private_unknown": "secret"}])
def test_no_other_schema_defect_is_relaxed_by_wall_clock_rule(monkeypatch, changes):
    assert observe(monkeypatch, [row(1, **changes)])["selected"] is None


def test_private_or_bad_duplicate_ID_fences_complete_public_peer(monkeypatch):
    assert observe(monkeypatch, [row(1), row(1, public=False)])["selected"] is None


def test_exact_seven_fractional_digits_preserved_without_time_order(monkeypatch):
    result = observe(monkeypatch, [row(1, "2023-01-01T00:00:00.1234567Z")])
    assert result["selected"]["created"].endswith(".1234567Z")
    assert result["selected_created_basis"] == "explicit_UTC_DateTime_literal"


def test_changed_raw_pin_refuses_before_shape_qualification(monkeypatch):
    raw = b'{"versions":[],"success":true}'
    monkeypatch.setattr(m, "REGISTERED_RAW_SHA256", "f" * 64)
    with pytest.raises(m.schema.RecoveryRefusal, match="legacy_custody_refused"):
        m.qualify_captured_identity(raw)
