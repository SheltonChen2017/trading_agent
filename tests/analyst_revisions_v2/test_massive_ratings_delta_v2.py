"""Synthetic retained transports only; never inspect the operational capture."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import os
from pathlib import Path
import sys

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from research.analyst_revisions_v2_qc import accepted_risk_massive_ratings_delta_v2 as m

d = m._transport


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)
    assert_lane_closure_excludes_dispatch_fence()


def row(**changes):
    return {"benzinga_id": "synthetic-event-a", "date": "2026-10-01", "time": "12:00:00",
        "last_updated": "2026-10-01T12:00:00Z", "ticker": "SYNTH",
        "benzinga_firm_id": "synthetic-firm", "firm": "Synthetic Firm",
        "rating_action": "upgrades", "rating": "Buy", "previous_rating": "Hold", **changes}


def store(tmp_path, monkeypatch, pages=None, *, unique=2, groups=1, excess=1):
    pages = [[row(), row(benzinga_id="synthetic-event-b"), row()]] if pages is None else pages
    path = tmp_path / "synthetic-retained"
    path.mkdir(mode=0o700)
    records, previous = [], None
    for index, source_rows in enumerate(pages, start=1):
        body = {"status": "OK", "results": source_rows}
        if index != len(pages):
            body["next_url"] = "https://api.massive.com/benzinga/v1/ratings?cursor=synthetic-next-" + str(index)
        raw = d.canonical_bytes(body)
        extracted, _ = d._capture._response_rows_and_next_url(raw, page_limit=d.PAGE_LIMIT)
        record = d.build_page_record(page_number=index, raw_response=raw, provider_rows=extracted,
            response_received_at="2026-10-13T23:00:01.000000Z", request_cursor_sha256=previous)
        previous = record["next_cursor_sha256"]
        records.append(record)
        for name, payload in zip(d.page_names(index), (raw, extracted), strict=True):
            (path / name).write_bytes(payload)
            (path / name).chmod(0o600)
    manifest = d.build_manifest(pages=records, capture_started_at="2026-10-13T23:00:00.000000Z",
        capture_completed_at="2026-10-13T23:00:02.000000Z")
    payload = d.canonical_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    for name, data in (("manifest.json", payload), ("manifest.sha256", (digest + "\n").encode())):
        (path / name).write_bytes(data)
        (path / name).chmod(0o600)
    monkeypatch.setattr(m, "EXPECTED_MANIFEST_SHA256", digest)
    monkeypatch.setattr(m, "EXPECTED_MANIFEST_BYTE_COUNT", len(payload))
    monkeypatch.setattr(m, "EXPECTED_SOURCE_ROW_COUNT", sum(map(len, pages)))
    monkeypatch.setattr(m, "EXPECTED_UNIQUE_ROW_COUNT", unique)
    monkeypatch.setattr(m, "EXPECTED_DUPLICATE_GROUP_COUNT", groups)
    monkeypatch.setattr(m, "EXPECTED_DUPLICATE_EXCESS_COUNT", excess)
    return path, digest, len(payload)


@pytest.fixture
def stored(tmp_path, monkeypatch):
    return store(tmp_path, monkeypatch)


def read(stored):
    return m._authenticate_retained_capture(*stored)


def repin(stored, monkeypatch, change):
    path = stored[0]
    manifest = d.strict_json_loads((path / "manifest.json").read_text(), "fixture")
    change(manifest)
    payload = d.canonical_bytes(manifest)
    digest = m._sha(payload)
    (path / "manifest.json").write_bytes(payload)
    (path / "manifest.sha256").write_bytes((digest + "\n").encode())
    monkeypatch.setattr(m, "EXPECTED_MANIFEST_SHA256", digest)
    monkeypatch.setattr(m, "EXPECTED_MANIFEST_BYTE_COUNT", len(payload))
    return path, digest, len(payload)


def test_exact_prospective_profile_not_diagnostic_or_retroactive_authority():
    profile = m.source_profile_record()
    assert m.SOURCE_PROFILE_SHA256 == m._sha(d.canonical_bytes(profile))
    assert profile["manifest_sha256"] == "2594cf2379c4a88c6ee53dc0ab3791235a01a4069f77505b7f98d560d8e9da00"
    assert profile["manifest_byte_count"] == 2628
    assert profile["source_row_count"] == 3261 and profile["unique_row_count"] == 3260
    assert profile["duplicate_group_count"] == profile["duplicate_excess_count"] == 1
    assert all(profile[name] is False for name in ("point_in_time_safe", "paper_or_live_ready", "three_role_complete", "retroactive_v1_acceptance"))


def test_all_finite_refusal_literals_are_declared():
    tree = ast.parse(Path(m.__file__).read_text())
    observed = {node.args[0].value for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_refuse"
        and node.args and isinstance(node.args[0], ast.Constant)}
    assert observed == m.FINITE_REFUSAL_CODES


def test_new_authority_collapses_once_and_preserves_every_original_locator(stored, monkeypatch):
    monkeypatch.setattr(d, "authenticate_capture", lambda *_a, **_k: pytest.fail("spent v1 invocation"))
    monkeypatch.setattr(d, "_authenticate_capture", lambda *_a, **_k: pytest.fail("spent v1 invocation"))
    value = read(stored)
    assert type(value) is m.AuthenticatedRatingsDeltaV2
    assert value.source_row_count == 3 and value.row_count == 2
    assert value.duplicate_group_count == value.duplicate_excess_count == 1
    rows = tuple(m.iter_authenticated_rating_rows(value))
    assert [item.provider_event_id for item in rows] == ["synthetic-event-a", "synthetic-event-b"]
    occurrences = tuple(m.iter_authenticated_occurrence_dispositions(value))
    assert [item.locator.row_offset for item in occurrences] == [0, 1, 2]
    assert [item.representative for item in occurrences] == [True, True, False]
    assert occurrences[2].representative_locator == rows[0].locator
    assert occurrences[2].locator.raw_row_sha256 == rows[0].locator.raw_row_sha256
    assert value.duplicate_disposition_sha256 == m._disposition_digest(occurrences)
    assert rows[0].raw_row_bytes not in repr(value).encode()
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(value)
    with pytest.raises(m.RatingsDeltaV2Error):
        m.require_authenticated_ratings_delta_v2(dataclasses.replace(value))


def test_exact_production_census_on_four_synthetic_pages(tmp_path, monkeypatch):
    rows = [row(benzinga_id=f"synthetic-event-{index}") for index in range(3260)]
    rows.insert(999, dict(rows[0]))
    source = store(tmp_path, monkeypatch, [rows[index:index + 1000] for index in range(0, len(rows), 1000)], unique=3260)
    value = read(source)
    assert value.page_count == 4 and value.source_row_count == 3261 and value.row_count == 3260
    assert value.duplicate_group_count == value.duplicate_excess_count == 1
    assert len(tuple(m.iter_authenticated_occurrence_dispositions(value))) == 3261
    assert value._occurrences[999].representative is False
    assert value._occurrences[999].representative_locator == value._occurrences[0].locator


@pytest.mark.parametrize("changes", [
    {"rating": "Strong Buy"}, {"last_updated": "2026-10-01T13:00:00Z"},
    {"ticker": "OTHER"}, {"extra": "a different canonical row"},
])
def test_any_conflicting_same_id_refuses_whole_source(tmp_path, monkeypatch, changes):
    source = store(tmp_path, monkeypatch, [[row(), row(benzinga_id="synthetic-event-b"), row(**changes)]])
    before = set(m._AUTHORITIES)
    with pytest.raises(m.RatingsDeltaV2Error, match="conflicting_provider_id"):
        read(source)
    assert set(m._AUTHORITIES) == before


def test_identical_across_page_group_is_outside_this_exact_contract(tmp_path, monkeypatch):
    source = store(tmp_path, monkeypatch, [[row(), row(benzinga_id="synthetic-event-b")], [row()]])
    with pytest.raises(m.RatingsDeltaV2Error, match="cross_page_duplicate"):
        read(source)


@pytest.mark.parametrize("invalid", [None, "", 3])
def test_invalid_ids_are_not_collapsed_or_admitted(tmp_path, monkeypatch, invalid):
    source = store(tmp_path, monkeypatch, [[row(), row(benzinga_id="synthetic-event-b"), row(benzinga_id=invalid)]])
    with pytest.raises(m.RatingsDeltaV2Error, match="invalid_provider_id"):
        read(source)


@pytest.mark.parametrize("field,value", [
    ("EXPECTED_SOURCE_ROW_COUNT", 4), ("EXPECTED_UNIQUE_ROW_COUNT", 3),
    ("EXPECTED_DUPLICATE_GROUP_COUNT", 2), ("EXPECTED_DUPLICATE_EXCESS_COUNT", 2),
])
def test_changed_census_is_not_automatically_admitted(stored, monkeypatch, field, value):
    monkeypatch.setattr(m, field, value)
    with pytest.raises(m.RatingsDeltaV2Error, match="source_count|duplicate_census"):
        read(stored)


@pytest.mark.parametrize("pin,size", [("0" * 64, 2628), (m.EXPECTED_MANIFEST_SHA256, True), (m.EXPECTED_MANIFEST_SHA256, 2629)])
def test_fixed_scope_refuses_before_open(monkeypatch, pin, size):
    def forbidden(_path):
        raise AssertionError("must refuse before read")
    monkeypatch.setitem(m._PINNED_HELPERS, "_open_chain", forbidden)
    monkeypatch.setattr(d, "_open_chain", forbidden)
    with pytest.raises(m.RatingsDeltaV2Error, match="exact_retained_manifest_scope"):
        m.authenticate_retained_capture(m.CAPTURE_PATH, expected_manifest_sha256=pin, expected_manifest_byte_count=size)


def test_public_path_is_not_redirectable(stored):
    with pytest.raises(m.RatingsDeltaV2Error, match="operational_path"):
        m.authenticate_retained_capture(stored[0], expected_manifest_sha256=stored[1], expected_manifest_byte_count=stored[2])


def test_manifest_pin_precedes_parser(stored, monkeypatch):
    path = stored[0] / "manifest.json"
    data = path.read_bytes()
    path.write_bytes(b"!" + data[1:])
    monkeypatch.setattr(d, "strict_json_loads", lambda *_a: pytest.fail("parser before external pin"))
    with pytest.raises(m.RatingsDeltaV2Error, match="manifest_external_pin"):
        read(stored)


@pytest.mark.parametrize("filename", ["page0001.raw.json", "page0001.rows.jsonl"])
def test_page_hash_precedes_any_page_parser(stored, monkeypatch, filename):
    path = stored[0] / filename
    data = path.read_bytes()
    path.write_bytes(b"!" + data[1:])
    def parser(**_kwargs):
        raise AssertionError("page parser before authenticated page hash")
    monkeypatch.setitem(m._PINNED_HELPERS, "build_page_record", parser)
    monkeypatch.setattr(d, "build_page_record", parser)
    with pytest.raises(m.RatingsDeltaV2Error, match="page_external_pin"):
        read(stored)


@pytest.mark.parametrize("filename", ["manifest.json", "manifest.sha256", "page0001.raw.json", "page0001.rows.jsonl"])
def test_declared_size_rejects_before_leaf_read(stored, monkeypatch, filename):
    path = stored[0] / filename
    path.write_bytes(path.read_bytes() + b" ")
    opened = []
    original = os.open
    def watched(name, *args, **kwargs):
        opened.append(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(os, "open", watched)
    with pytest.raises(m.RatingsDeltaV2Error):
        read(stored)
    assert filename not in opened


@pytest.mark.parametrize("change", ["extra", "missing", "symlink", "hardlink", "public"])
def test_leaf_inventory_topology_and_permissions_refuse(stored, change):
    root = stored[0]
    leaf = root / "page0001.raw.json"
    if change == "extra":
        (root / "unexpected").write_bytes(b"fixture")
    elif change == "missing":
        leaf.unlink()
    elif change == "symlink":
        leaf.rename(root / "saved-raw")
        leaf.symlink_to(root / "saved-raw")
    elif change == "hardlink":
        os.link(leaf, root.parent / "synthetic-hardlink")
    else:
        leaf.chmod(0o644)
    with pytest.raises(m.RatingsDeltaV2Error):
        read(stored)


@pytest.mark.parametrize("change", ["unknown", "nonterminal", "cursor", "count", "clock", "falseflag"])
def test_manifest_and_terminal_chain_validation_remains_binding(stored, monkeypatch, change):
    def mutate(value):
        if change == "unknown":
            value["new_field"] = 1
        elif change == "nonterminal":
            value["pages"][-1]["terminal_page"] = False
        elif change == "cursor":
            value["pages"][0]["request_cursor_sha256"] = "a" * 64
        elif change == "count":
            value["pages"][0]["row_count"] = True
        elif change == "clock":
            value["capture_started_at"] = "2026-10-12T00:00:00Z"
        else:
            value["point_in_time_safe"] = True
    source = repin(stored, monkeypatch, mutate)
    with pytest.raises(m.RatingsDeltaV2Error):
        read(source)


def test_no_collapse_before_complete_first_postguard(stored, monkeypatch):
    def refuse(*_args):
        raise m.RatingsDeltaV2Error("synthetic_final_refusal")
    monkeypatch.setattr(m, "_final_guards", refuse)
    monkeypatch.setattr(m, "_normalize_complete_occurrences", lambda *_a: pytest.fail("collapse before complete evidence"))
    before = set(m._AUTHORITIES)
    with pytest.raises(m.RatingsDeltaV2Error, match="synthetic_final_refusal"):
        read(stored)
    assert set(m._AUTHORITIES) == before


def test_file_change_during_collapse_is_caught_by_second_postguard(stored, monkeypatch):
    original = m._normalize_complete_occurrences
    def change(rows):
        result = original(rows)
        leaf = stored[0] / "page0001.raw.json"
        payload = leaf.read_bytes()
        leaf.write_bytes(payload)
        return result
    monkeypatch.setattr(m, "_normalize_complete_occurrences", change)
    with pytest.raises(m.RatingsDeltaV2Error, match="leaf_final_changed"):
        read(stored)


def test_file_change_during_fingerprint_is_caught_before_authority(stored, monkeypatch):
    original = m._fingerprint
    def change(value):
        result = original(value)
        leaf = stored[0] / "page0001.raw.json"
        leaf.write_bytes(leaf.read_bytes())
        return result
    monkeypatch.setattr(m, "_fingerprint", change)
    before = set(m._AUTHORITIES)
    with pytest.raises(m.RatingsDeltaV2Error, match="leaf_final_changed"):
        read(stored)
    assert set(m._AUTHORITIES) == before


@pytest.mark.parametrize("field,value", [
    ("source_row_count", 3.0), ("row_count", True), ("duplicate_excess_count", True),
    ("duplicate_disposition_sha256", "0" * 64), ("manifest_sha256", "0" * 64),
    ("_occurrences", []), ("_rows", []),
])
def test_mutated_authority_is_rejected(stored, field, value):
    result = read(stored)
    old = getattr(result, field)
    try:
        object.__setattr__(result, field, value)
        with pytest.raises(m.RatingsDeltaV2Error, match="authority_unavailable"):
            m.require_authenticated_ratings_delta_v2(result)
    finally:
        object.__setattr__(result, field, old)


@pytest.mark.parametrize("field,value", [("representative", 1), ("provider_event_id", "other"), ("locator", object())])
def test_occurrence_mutations_cannot_hide_behind_equal_values(stored, field, value):
    result = read(stored)
    item = result._occurrences[0]
    old = getattr(item, field)
    try:
        object.__setattr__(item, field, value)
        with pytest.raises(m.RatingsDeltaV2Error):
            m.require_authenticated_ratings_delta_v2(result)
    finally:
        object.__setattr__(item, field, old)


def test_mutable_raw_byte_alias_is_not_frozen_authority(stored):
    value = read(stored)
    row_value = value._rows[0]
    old = row_value.raw_row_bytes
    try:
        object.__setattr__(row_value, "raw_row_bytes", bytearray(old))
        with pytest.raises(m.RatingsDeltaV2Error):
            m.require_authenticated_ratings_delta_v2(value)
    finally:
        object.__setattr__(row_value, "raw_row_bytes", old)


def test_dependency_change_refuses_without_opening(stored, monkeypatch):
    monkeypatch.setattr(d, "_read_held", lambda *_a, **_k: pytest.fail("changed reader invoked"))
    with pytest.raises(m.RatingsDeltaV2Error, match="dependency_changed"):
        read(stored)


def test_retained_descriptors_are_closed_after_refusal(stored, monkeypatch):
    seen, original = [], os.close
    def close(fd):
        seen.append(fd)
        return original(fd)
    monkeypatch.setattr(os, "close", close)
    (stored[0] / "page0001.raw.json").write_bytes(b"short")
    with pytest.raises(m.RatingsDeltaV2Error):
        read(stored)
    assert len(seen) >= 3
    for fd in seen:
        with pytest.raises(OSError):
            os.fstat(fd)
