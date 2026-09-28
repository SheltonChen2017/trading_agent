"""Offline, value-free between-capture drift counts are not PIT evidence."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import stat
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from scripts import measure_arv2_vendor_drift as subject
from tests.analyst_revisions_v2 import test_massive_capture_adapter as offline


def _row(identity="PRIVATE-RECORD-ALPHA", **fields):
    return {"benzinga_id": identity, "date": subject.FIRST,
            "last_updated": "2026-09-16T03:00:00Z", **fields}


def _compare(before, after):
    old, old_count = subject._index(before)
    new, new_count = subject._index(after)
    return subject.compare_role(old, new, old_count, new_count)


def test_ambiguous_ids_repeats_and_typed_id_additions_are_disclosed_not_selected():
    before = [_row("unchanged"), _row("unchanged"), _row("timestamp"),
              _row("payload", price_target=987654321), _row("missing"),
              _row("old-only"), _row("old-ambiguous", rating="A"),
              _row("old-ambiguous", rating="B"), _row("new-ambiguous"), _row(7)]
    after = [_row("unchanged"), _row("timestamp", last_updated="2026-09-17T04:00:00Z"),
             _row("payload", price_target=987654322), _row("missing", optional=None),
             _row("new-only"), _row("old-ambiguous", rating="A"),
             _row("new-ambiguous", rating="A"), _row("new-ambiguous", rating="B"), _row("7")]
    result = _compare(before, after)
    assert result == {
        "old_rows_in_window": 10, "new_rows_in_window": 9,
        "old_distinct_ids": 8, "new_distinct_ids": 8, "common_ids": 6,
        "comparable_single_variant_common_ids": 4, "ambiguous_common_ids_excluded": 2,
        "old_ambiguous_ids": 1, "new_ambiguous_ids": 1,
        "old_repeated_identical_rows": 1, "new_repeated_identical_rows": 0,
        "old_only_ids": 2, "new_only_ids": 2, "unchanged_common_ids": 1,
        "any_changed_common_ids": 3, "semantic_changed_common_ids": 2,
        "last_updated_only_changed_common_ids": 1, "rating_or_target_changed_common_ids": 1,
        "clock_or_identity_changed_common_ids": 0,
        "semantic_change_percent_of_comparable_ids": "50.000000",
        "changed_field_counts": {"last_updated": 1, "optional": 1, "price_target": 1},
    }
    text = canonical_json_bytes(result).decode("ascii")
    assert not any(canonical_json_bytes(private).decode("ascii") in text for private in (
        "unchanged", "old-ambiguous", "new-ambiguous", "old-only", "new-only", 987654321, 987654322))


@pytest.mark.parametrize("direction", ("missing_to_null", "null_to_missing"))
def test_missing_and_null_are_distinct_even_though_get_would_return_none(direction):
    missing, null = _row(), _row(optional=None)
    before, after = (missing, null) if direction == "missing_to_null" else (null, missing)
    result = _compare([before], [after])
    assert result["semantic_changed_common_ids"] == 1
    assert result["changed_field_counts"] == {"optional": 1}


def test_payload_and_last_updated_categories_partition_changes_and_clock_overlap():
    result = _compare([_row(ticker="PRIVATE-OLD-SYMBOL", rating="PRIVATE-OLD-RATING")],
                      [_row(ticker="PRIVATE-NEW-SYMBOL", rating="PRIVATE-NEW-RATING",
                            last_updated="2026-09-18T00:00:00Z")])
    assert result["any_changed_common_ids"] == result["semantic_changed_common_ids"] == 1
    assert result["last_updated_only_changed_common_ids"] == 0
    assert result["clock_or_identity_changed_common_ids"] == result["rating_or_target_changed_common_ids"] == 1
    assert result["changed_field_counts"] == {"last_updated": 1, "rating": 1, "ticker": 1}
    assert "PRIVATE-" not in canonical_json_bytes(result).decode("ascii")


def test_canonical_object_key_order_does_not_create_a_change():
    before = _row(nested={"x": 1, "y": 2})
    after = dict(reversed(list(_row(nested={"y": 2, "x": 1}).items())))
    result = _compare([before], [after])
    assert result["unchanged_common_ids"] == 1 and result["changed_field_counts"] == {}


@pytest.mark.parametrize("before,after", (
    (Decimal("12345678901234567890.12345678901234567890"),
     Decimal("12345678901234567890.12345678901234567891")),
    (Decimal("1.00"), Decimal("1.0")),
    (Decimal("1"), 1),
))
def test_decimal_payload_and_representation_differences_are_not_float_collapsed(before, after):
    result = _compare([_row(price_target=before)], [_row(price_target=after)])
    assert result["semantic_changed_common_ids"] == result["rating_or_target_changed_common_ids"] == 1
    assert result["changed_field_counts"] == {"price_target": 1}
    assert result["semantic_change_percent_of_comparable_ids"] == "100.000000"


@pytest.mark.parametrize("value", (Decimal("NaN"), Decimal("Infinity"), float("nan")))
def test_nonfinite_or_unsupported_numeric_payload_is_not_silently_counted(value):
    with pytest.raises(subject.capture.MassiveCaptureError):
        subject._index([_row(price_target=value)])


def test_integer_and_text_ids_remain_separate():
    index, count = subject._index([_row(7), _row("7")])
    assert count == 2 and set(index) == {b"7", b'"7"'}


def test_empty_or_only_ambiguous_comparison_has_no_invented_percentage():
    result = _compare([], [])
    assert result["comparable_single_variant_common_ids"] == 0
    assert result["semantic_change_percent_of_comparable_ids"] is None
    result = _compare([_row(rating="A"), _row(rating="B")], [_row(rating="A")])
    assert result["ambiguous_common_ids_excluded"] == 1
    assert result["any_changed_common_ids"] == 0
    assert result["semantic_change_percent_of_comparable_ids"] is None


def test_date_window_is_inclusive_and_rows_outside_do_not_require_an_id():
    rows = [_row("FIRST", date=subject.FIRST), _row("LAST", date=subject.LAST),
            {"date": "2026-07-31"}, {"date": "2026-09-17"}]
    index, count = subject._index(rows)
    assert count == len(index) == 2
    with pytest.raises(ValueError, match="reversed"):
        subject._index([], subject.LAST, subject.FIRST)


@pytest.mark.parametrize("new_date", ("2026-08-02", "2026-09-17"))
def test_date_move_is_a_clock_change_or_window_disappearance_not_an_invented_deletion(new_date):
    result = _compare([_row()], [_row(date=new_date)])
    if new_date == "2026-08-02":
        assert result["clock_or_identity_changed_common_ids"] == result["semantic_changed_common_ids"] == 1
        assert result["old_only_ids"] == 0
    else:
        assert result["old_only_ids"] == 1 and result["comparable_single_variant_common_ids"] == 0
        assert result["semantic_changed_common_ids"] == 0
        assert result["semantic_change_percent_of_comparable_ids"] is None


@pytest.mark.parametrize("identity", (None, True, False, 1.0, "", [], {}))
def test_unavailable_or_invalid_identity_is_refused(identity):
    with pytest.raises(ValueError, match="ID is unavailable or malformed"):
        subject._index([_row(identity)])


@pytest.mark.parametrize("row", ([], None, {"benzinga_id": "x"}, _row(date="2026-02-30")))
def test_nonobject_or_invalid_event_dates_are_refused(row):
    with pytest.raises(ValueError):
        subject._index([row])


def _capture(tmp_path, *, phase="old", first=None, last=None):
    responses = []
    for role in subject.capture.ROLE_ORDER:
        row = offline._row("PRIVATE-CAPTURE-ROW-ID-" + role.value, role=role)
        row["date"] = subject.FIRST
        row["ticker"] = "PRIVATE-CAPTURE-TICKER"
        if role is subject.capture.ROLE_ORDER[0]:
            row["price_target"] = Decimal("987654321.1234567890123456789") if phase == "new" else Decimal("125.000")
        payload = subject.capture._canonical_json_value({"results": [row], "status": "OK"}).encode("utf-8")
        responses.append(offline.FakeResponse(payload, offline._endpoint(role)))
    return subject.capture._capture_massive_history_spooled_for_test(
        requested_first_event_date=subject.FIRST if first is None else first,
        requested_last_event_date=subject.LAST if last is None else last,
        artifact_root=tmp_path / phase, session=offline.FakeSession(responses),
        clock=lambda: datetime(2026, 9, 17, tzinfo=timezone.utc) + timedelta(days=phase == "new"),
        api_key=offline.KEY)


def test_real_authenticated_offline_capture_loader_and_value_free_report(tmp_path):
    old, new = _capture(tmp_path), _capture(tmp_path, phase="new")
    report = subject.compare_captures(old.artifact_path, old.manifest_sha256,
        new.artifact_path, new.manifest_sha256, expected_transport=subject.capture.TEST_TRANSPORT)
    assert report["minimum_between_capture_interval"] == "1 day, 0:00:00"
    assert report["point_in_time_proven"] is report["performance_effect_measured"] is False
    assert report["qc_calls"] == report["return_looks"] == 0
    assert report["old_manifest_sha256"] == old.manifest_sha256
    assert report["new_manifest_sha256"] == new.manifest_sha256
    ratings = report["roles"][subject.capture.ROLE_ORDER[0].value]
    assert ratings["semantic_changed_common_ids"] == 1
    assert ratings["rating_or_target_changed_common_ids"] == 1
    assert ratings["changed_field_counts"] == {"price_target": 1}
    assert all(role["comparable_single_variant_common_ids"] == 1 for role in report["roles"].values())
    text = canonical_json_bytes(report).decode("ascii")
    assert "PRIVATE-CAPTURE" not in text and "987654321" not in text


@pytest.mark.parametrize("target", ("raw_response_file", "provider_rows_file"))
def test_capture_byte_tampering_is_refused_before_returning_counts(tmp_path, target):
    old = _capture(tmp_path)
    manifest = json.loads((old.artifact_path / "manifest.json").read_bytes())
    page = old.artifact_path / manifest["pages"][0][target]
    page.write_bytes(page.read_bytes().replace(b"PRIVATE-CAPTURE-TICKER", b"PRIVATE-CAPTURE-ALTERD", 1))
    with pytest.raises(subject.capture.MassiveCaptureError, match="byte count or hash changed"):
        subject.read_capture(old.artifact_path, old.manifest_sha256,
                             expected_transport=subject.capture.TEST_TRANSPORT)


def test_external_manifest_pin_and_declared_query_window_are_required(tmp_path):
    old = _capture(tmp_path)
    with pytest.raises(ValueError, match="external pin"):
        subject.read_capture(old.artifact_path, "0" * 64, expected_transport=subject.capture.TEST_TRANSPORT)
    narrowed = _capture(tmp_path, phase="narrowed", first="2026-08-02")
    with pytest.raises(ValueError, match="complete drift window"):
        subject.read_capture(narrowed.artifact_path, narrowed.manifest_sha256,
                             expected_transport=subject.capture.TEST_TRANSPORT)


@pytest.mark.parametrize("kind", ("same_digest", "overlap", "touch", "reverse"))
def test_capture_order_requires_distinct_nonoverlapping_chronological_vintages(monkeypatch, kind):
    old = SimpleNamespace(capture_id="old-private-capture", manifest_sha256="a" * 64,
        capture_completed_at="2026-09-17T12:00:00.000000Z")
    new = SimpleNamespace(capture_id="new-private-capture", manifest_sha256="b" * 64,
        capture_started_at="2026-09-18T12:00:00.000000Z")
    if kind == "same_digest":
        new.manifest_sha256 = old.manifest_sha256
    elif kind in ("overlap", "reverse"):
        new.capture_started_at = "2026-09-17T11:59:59.000000Z"
    else:
        new.capture_started_at = old.capture_completed_at
    empty = {role.value: {} for role in subject.capture.ROLE_ORDER}
    monkeypatch.setattr(subject, "read_capture", lambda path, *_args, **_kwargs:
                        (old if path == "old" else new, empty, Counter()))
    with pytest.raises(ValueError, match="distinct, chronological nonoverlapping"):
        subject.compare_captures("old", old.manifest_sha256, "new", new.manifest_sha256)


def test_published_report_is_private_digest_named_and_immutable(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(subject.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    report = {"schema": "arv2-test-counts", "rows": 2, "qc_calls": 0}
    path, digest = subject.publish_report(report, allowed / "reports")
    payload = canonical_json_bytes(report)
    assert path.read_bytes() == payload
    assert path.name == "drift-counts-" + digest + ".json"
    assert digest == subject.sha256_bytes(payload)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with pytest.raises(subject.capture.MassiveCaptureError, match="overwrite refused"):
        subject.publish_report(report, allowed / "reports")
    assert path.read_bytes() == payload


def test_publication_failure_closes_opened_directory_descriptor(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(subject.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    descriptors = []
    real_open = subject.capture._open_directory_path
    def record_open(*args, **kwargs):
        path, descriptor = real_open(*args, **kwargs)
        descriptors.append(descriptor)
        return path, descriptor
    def fail_write(*_args, **_kwargs):
        raise RuntimeError("synthetic report write failure")
    monkeypatch.setattr(subject.capture, "_open_directory_path", record_open)
    monkeypatch.setattr(subject.capture, "_exclusive_private_write_at", fail_write)
    with pytest.raises(RuntimeError, match="synthetic report write failure"):
        subject.publish_report({"rows": 2}, allowed / "reports")
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


def test_invalid_report_is_refused_before_opening_or_creating_output_root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(subject.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    def unexpected_open(*_args, **_kwargs):
        raise AssertionError("invalid report opened output root")
    monkeypatch.setattr(subject.capture, "_open_directory_path", unexpected_open)
    with pytest.raises(ValueError):
        subject.publish_report({"noncanonical": float("nan")}, allowed / "reports")
    assert not allowed.exists()
