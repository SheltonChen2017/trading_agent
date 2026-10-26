"""Synthetic one-role evidence only: never open the operational R297 leaf."""
from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_massive_ratings_delta as d

START = "2026-10-13T23:00:00.000000Z"
RECEIVED = "2026-10-13T23:00:01.000000Z"
END = "2026-10-13T23:00:02.000000Z"


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)


def row(**changes):
    return {
        "benzinga_id": "fixture-event-1", "date": "2026-10-01", "time": "12:00:00",
        "last_updated": "2026-10-01T12:00:00Z", "ticker": "SYNTH",
        "benzinga_firm_id": "fixture-firm-1", "firm": "Synthetic Firm",
        "rating_action": "upgrades", "rating": "Buy", "previous_rating": "Hold", **changes,
    }


def page_values(rows=None, number=1, prior=None, next_cursor=None):
    body = {"status": "OK", "results": [row()] if rows is None else rows}
    if next_cursor is not None:
        body["next_url"] = "https://api.massive.com/benzinga/v1/ratings?cursor=" + next_cursor
    raw = d.canonical_bytes(body)
    extracted, _ = d._capture._response_rows_and_next_url(raw, page_limit=d.PAGE_LIMIT)
    record = d.build_page_record(
        page_number=number, raw_response=raw, provider_rows=extracted,
        response_received_at=RECEIVED, request_cursor_sha256=prior,
    )
    return raw, extracted, record


def manifest_for(pages):
    return d.build_manifest(pages=pages, capture_started_at=START, capture_completed_at=END)


def store(path, values=None):
    values = [page_values()] if values is None else values
    path.mkdir(mode=0o700)
    for raw, extracted, record in values:
        for name, data in zip(d.page_names(record["page_number"]), (raw, extracted), strict=True):
            (path / name).write_bytes(data)
            (path / name).chmod(0o600)
    payload = d.canonical_bytes(manifest_for([value[2] for value in values]))
    (path / "manifest.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (path / "manifest.sha256").write_bytes((digest + "\n").encode("ascii"))
    (path / "manifest.json").chmod(0o600)
    (path / "manifest.sha256").chmod(0o600)
    return path, digest, len(payload)


@pytest.fixture
def stored(tmp_path):
    return store(tmp_path / "synthetic-capture")


def read(stored):
    return d._authenticate_capture(*stored)


def repin(stored, mutate):
    path = stored[0]
    manifest = d.strict_json_loads((path / "manifest.json").read_text(), "fixture")
    mutate(manifest)
    payload = d.canonical_bytes(manifest)
    digest = d._sha(payload)
    (path / "manifest.json").write_bytes(payload)
    (path / "manifest.sha256").write_bytes((digest + "\n").encode())
    return path, digest, len(payload)


def test_authenticated_single_role_snapshot_has_no_legacy_authority(stored):
    value = read(stored)
    assert type(value) is d.AuthenticatedRatingsDelta
    assert value.context.first_event_date == "2026-09-26"
    assert value.context.last_event_date == "2026-10-12"
    assert value.row_count == value.page_count == 1
    rows = tuple(d.iter_authenticated_rating_rows(value))
    assert rows[0].current_view.included and rows[0].censored_view.included
    assert rows[0].firm_label == "fixture-firm-1"
    assert rows[0].raw_row_bytes not in repr(value).encode()
    assert len(d._AUTHORITIES) >= 1


def test_terminal_empty_is_valid_acquisition_not_new_signal(tmp_path):
    value = read(store(tmp_path / "empty", [page_values([])]))
    assert value.row_count == 0 and tuple(d.iter_authenticated_rating_rows(value)) == ()


def test_terminal_two_page_chain_authenticates(tmp_path):
    first = page_values(next_cursor="second")
    second = page_values([row(benzinga_id="fixture-event-2")], 2, first[2]["next_cursor_sha256"])
    result = read(store(tmp_path / "two", [first, second]))
    assert result.page_count == result.row_count == 2


def test_duplicate_rating_ids_across_pages_refuse_before_authority(tmp_path):
    first = page_values(next_cursor="second")
    second = page_values(number=2, prior=first[2]["next_cursor_sha256"])
    stored = store(tmp_path / "duplicate", [first, second])
    before = set(d._AUTHORITIES)
    with pytest.raises(d.RatingsDeltaError, match="duplicate_rating_provider_id"):
        read(stored)
    assert set(d._AUTHORITIES) == before


def test_duplicate_rating_ids_within_page_refuse(tmp_path):
    with pytest.raises(d.RatingsDeltaError, match="duplicate_rating_provider_id"):
        read(store(tmp_path / "duplicate", [page_values([row(), row()])]))


@pytest.mark.parametrize("key,value", [
    ("schema", "legacy"), ("source_profile_sha256", "a" * 64),
    ("role", "earnings"), ("endpoint", "/benzinga/v1/guidance"),
    ("first_event_date", "2026-09-25"), ("last_event_date", "2026-10-13"),
    ("page_limit", True), ("page_limit", 999), ("page_count", True),
    ("page_count", 0), ("page_count", 17), ("attempted_request_count", 2),
    ("attempted_request_count", True), ("row_count", True), ("row_count", 16001),
    ("raw_byte_count", 32 * 1024 * 1024 + 1), ("rows_byte_count", 32 * 1024 * 1024 + 1),
    ("row_count", 2), ("raw_byte_count", 1), ("rows_byte_count", 1),
    ("point_in_time_safe", True), ("point_in_time_safe", 0),
    ("paper_or_live_ready", True), ("three_role_complete", True),
    ("capture_started_at", "2026-10-12T19:59:59.000000Z"),
    ("capture_started_at", "2026-10-14T00:00:00.000000Z"),
    ("capture_completed_at", "2026-10-12T20:00:00.000000Z"),
    ("capture_completed_at", "not-a-clock"), ("pages", None),
])
def test_manifest_fields_refuse_with_fresh_external_pin(stored, key, value):
    with pytest.raises(d.RatingsDeltaError):
        read(repin(stored, lambda m: m.__setitem__(key, value)))


@pytest.mark.parametrize("key,value", [
    ("page_number", True), ("page_number", 2), ("http_status", 201),
    ("http_status", True), ("row_count", True), ("row_count", 1001),
    ("raw_response_bytes", 4 * 1024 * 1024 + 1), ("provider_rows_bytes", -1),
    ("raw_response_sha256", "bad"), ("provider_rows_sha256", "a" * 64),
    ("request_cursor_sha256", "a" * 64), ("next_cursor_sha256", "a" * 64),
    ("terminal_page", 1), ("terminal_page", False),
    ("response_received_at", "2026-10-13T22:59:59.000000Z"),
    ("response_received_at", "2026-10-13T23:00:03.000000Z"),
])
def test_page_fields_refuse_with_fresh_external_pin(stored, key, value):
    with pytest.raises(d.RatingsDeltaError):
        read(repin(stored, lambda m: m["pages"][0].__setitem__(key, value)))


@pytest.mark.parametrize("area", ["manifest", "page"])
@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_schema_exact_inventory(stored, area, operation):
    def mutate(m):
        target = m if area == "manifest" else m["pages"][0]
        if operation == "extra":
            target["extra"] = 1
        else:
            target.pop(next(iter(target)))
    with pytest.raises(d.RatingsDeltaError):
        read(repin(stored, mutate))


@pytest.mark.parametrize("suffix", ["raw.json", "rows.jsonl"])
def test_changed_page_bytes_refuse(stored, suffix):
    path = stored[0] / ("page0001." + suffix)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(d.RatingsDeltaError):
        read(stored)


@pytest.mark.parametrize("mutation", ["extra", "missing", "mode", "hardlink", "symlink", "directory"])
def test_artifact_topology_refuses(stored, mutation):
    root = stored[0]
    leaf = root / "page0001.raw.json"
    if mutation == "extra":
        (root / "extra").write_bytes(b"fixture")
    elif mutation == "missing":
        leaf.unlink()
    elif mutation == "mode":
        leaf.chmod(0o644)
    elif mutation == "hardlink":
        os.link(leaf, root.parent / "other-link")
    elif mutation == "symlink":
        original = root.parent / "original"
        leaf.rename(original)
        leaf.symlink_to(original)
    else:
        leaf.unlink()
        leaf.mkdir()
    with pytest.raises(d.RatingsDeltaError):
        read(stored)


def test_private_directory_mode_refuses(stored):
    stored[0].chmod(0o755)
    with pytest.raises(d.RatingsDeltaError, match="private_directory"):
        read(stored)


def test_symlink_ancestor_refuses(stored):
    link = stored[0].parent / "alias"
    link.symlink_to(stored[0])
    with pytest.raises(d.RatingsDeltaError):
        read((link, *stored[1:]))


@pytest.mark.parametrize("digest,size", [("a" * 64, None), (None, 1), (True, None), (None, True)])
def test_external_manifest_bindings_are_independent(stored, digest, size):
    with pytest.raises(d.RatingsDeltaError):
        read((stored[0], stored[1] if digest is None else digest, stored[2] if size is None else size))


def test_manifest_marker_is_exact(stored):
    (stored[0] / "manifest.sha256").write_bytes(stored[1].encode() + b" ")
    with pytest.raises(d.RatingsDeltaError, match="manifest_digest_marker"):
        read(stored)


def test_noncanonical_manifest_even_repin_refuses(stored):
    path = stored[0] / "manifest.json"
    payload = path.read_bytes() + b"\n"
    path.write_bytes(payload)
    digest = d._sha(payload)
    (stored[0] / "manifest.sha256").write_bytes((digest + "\n").encode())
    with pytest.raises(d.RatingsDeltaError, match="manifest_canonical"):
        read((stored[0], digest, len(payload)))


@pytest.mark.parametrize("field,value", [("row_count", True), ("manifest_sha256", "a" * 64), ("_rows", [])])
def test_process_local_authority_rejects_mutation(stored, field, value):
    result = read(stored)
    object.__setattr__(result, field, value)
    with pytest.raises(d.RatingsDeltaError):
        tuple(d.iter_authenticated_rating_rows(result))


def test_context_and_nested_row_mutation_refuse(stored):
    result = read(stored)
    object.__setattr__(result.context, "first_event_date", "2026-01-01")
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(result)
    result = read(stored)
    object.__setattr__(result._rows[0], "raw_row_bytes", b"{}\n")
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(result)


def test_forged_dataclass_is_not_authority(stored):
    actual = read(stored)
    forged = dataclasses.replace(actual)
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(forged)


def test_operational_reader_does_not_accept_synthetic_path(stored):
    with pytest.raises(d.RatingsDeltaError, match="operational_path"):
        d.authenticate_capture(stored[0], expected_manifest_sha256=stored[1], expected_manifest_byte_count=stored[2])


@pytest.mark.parametrize("changes", [
    {}, {"benzinga_id": None}, {"date": "bad"}, {"date": "2012-12-31"},
    {"date": "2026-09-25"}, {"date": "2026-10-13"}, {"time": None}, {"time": "25:00:00"},
    {"time": 12}, {"last_updated": None}, {"last_updated": "2026-10-01T12:00:00"},
    {"last_updated": "2026-10-01T09:00:00-04:00"},
    {"last_updated": "2026-10-05T13:30:00Z"},
    {"last_updated": "2026-10-05T13:30:00.000001Z"},
    {"last_updated": "2026-10-13T23:00:02Z"},
    {"rating_action": None}, {"benzinga_firm_id": None}, {"ticker": None},
    {"date": "2026-10-12", "last_updated": "2026-10-12T10:00:00Z"},
])
def test_rating_normalization_exactly_matches_legacy_pure_semantics(changes):
    raw, extracted, record = page_values([row(**changes)])
    page = d._input.bind_capture_page(
        source_role=d.ROLE,
        redacted_query_bytes=d._input.render_redacted_capture_query_bytes(
            source_role=d.ROLE, requested_first_event_date=d.FIRST_DATE,
            requested_last_event_date=d.LAST_DATE, limit=d.PAGE_LIMIT),
        page_number=1, request_cursor_sha256=None, next_cursor_sha256=None,
        terminal_page=True, response_received_at=RECEIVED,
        raw_response_sha256=d._sha(raw), provider_rows_bytes=extracted, raw_response_bytes=raw,
    )
    context = d.RatingsDeltaContext("synthetic-context", d.FIRST_DATE, d.LAST_DATE, START, END)
    current = d.normalize_rating(page=page, row_offset=0, raw_row_bytes=extracted, context=context)
    # Test-only scalar context is never passed to legacy capture-authority APIs.
    legacy_context = SimpleNamespace(capture_id=context.capture_id,
        requested_first_event_date=d.FIRST_DATE, requested_last_event_date=d.LAST_DATE)
    old = d._input._derive_source_row(capture=legacy_context, page=page, row_offset=0,
        row=page.parsed_rows[0], raw_row_bytes=extracted, duplicate_provider_event_id=False)
    assert current == old


def test_response_extraction_and_cursor_boundaries():
    raw, extracted, _ = page_values()
    with pytest.raises(d.RatingsDeltaError, match="extraction_mismatch"):
        d.build_page_record(page_number=1, raw_response=raw, provider_rows=b"{}\n",
            response_received_at=RECEIVED, request_cursor_sha256=None)
    for bad in (
        {"status": "ERROR", "results": []},
        {"status": "OK", "results": [], "next_url": "https://evil.example/?cursor=a"},
        {"status": "OK", "results": [], "next_url": "https://api.massive.com/benzinga/v1/ratings?cursor=a&apiKey=fixture"},
    ):
        with pytest.raises(d.RatingsDeltaError, match="page_semantics"):
            d.build_page_record(page_number=1, raw_response=d.canonical_bytes(bad), provider_rows=b"",
                response_received_at=RECEIVED, request_cursor_sha256=None)


def test_final_metadata_guard_detects_same_bytes_replacement(stored, monkeypatch):
    original = d.build_page_record
    def replace(**kwargs):
        result = original(**kwargs)
        target = stored[0] / "page0001.raw.json"
        replacement = stored[0] / "new-raw"
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(target)
        return result
    monkeypatch.setattr(d, "build_page_record", replace)
    with pytest.raises(d.RatingsDeltaError, match="leaf_final_changed"):
        read(stored)


def test_canonical_manifest_uses_frozen_single_lf_oracle():
    assert d.canonical_bytes({"fixed": 1}) == b'{"fixed":1}\n'


def test_declared_page_size_refuses_before_private_leaf_read(stored, monkeypatch):
    target = stored[0] / "page0001.raw.json"
    target.write_bytes(target.read_bytes() + b" ")
    inode = target.stat().st_ino
    original = d.os.read
    reads = []
    def tracked(fd, count):
        if os.fstat(fd).st_ino == inode:
            reads.append(count)
        return original(fd, count)
    monkeypatch.setattr(d.os, "read", tracked)
    with pytest.raises(d.RatingsDeltaError):
        read(stored)
    assert reads == []


def test_authentication_parses_raw_rows_once_per_page(tmp_path):
    values = [row(benzinga_id="synthetic-" + str(i)) for i in range(1000)]
    stored = store(tmp_path / "full-page", [page_values(values)])
    prop = d._input.CapturePageBinding.raw_rows
    calls = []
    def counted(frame, event, _arg):
        if event == "call" and frame.f_code is prop.fget.__code__:
            calls.append(frame.f_locals["self"].page_number)
    previous = sys.getprofile()
    try:
        sys.setprofile(counted)
        actual = read(stored)
    finally:
        sys.setprofile(previous)
    assert actual.row_count == 1000
    assert calls == [1]


@pytest.mark.parametrize("field", [
    "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
    "st_mode", "st_uid", "st_gid", "st_nlink", "st_flags",
])
def test_every_retained_metadata_field_remains_binding(stored, monkeypatch, field):
    original_page = d.build_page_record
    original_stat = os.fstat
    armed = False
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
              "st_mode", "st_uid", "st_gid", "st_nlink", "st_flags")
    def page(**kwargs):
        nonlocal armed
        result = original_page(**kwargs)
        armed = True
        return result
    def observed(fd):
        result = original_stat(fd)
        if armed and d.stat.S_ISREG(result.st_mode):
            values = {key: getattr(result, key, 0) for key in fields}
            values[field] += 1
            return SimpleNamespace(**values)
        return result
    monkeypatch.setattr(d, "build_page_record", page)
    monkeypatch.setattr(os, "fstat", observed)
    with pytest.raises(d.RatingsDeltaError, match="leaf_final_changed"):
        read(stored)


def test_final_directory_inventory_is_checked_after_normalization(stored, monkeypatch):
    original = d.build_page_record
    def add(**kwargs):
        result = original(**kwargs)
        (stored[0] / "late-extra").write_bytes(b"fixture")
        return result
    monkeypatch.setattr(d, "build_page_record", add)
    with pytest.raises(d.RatingsDeltaError, match="directory_final_changed"):
        read(stored)


def test_preopen_metadata_swap_refuses_before_raw_bytes(stored, monkeypatch):
    target = stored[0] / "page0001.raw.json"
    original = os.open
    original_read = os.read
    raw_fd = None
    raw_reads = []
    def opened(path, flags, *args, **kwargs):
        nonlocal raw_fd
        fd = original(path, flags, *args, **kwargs)
        if path == target.name:
            raw_fd = fd
            observed = target.stat()
            os.utime(target, ns=(observed.st_atime_ns, observed.st_mtime_ns + 1))
        return fd
    def read_bytes(fd, count):
        if fd == raw_fd:
            raw_reads.append(count)
        return original_read(fd, count)
    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "read", read_bytes)
    with pytest.raises(d.RatingsDeltaError, match="leaf_preopen_changed"):
        read(stored)
    assert raw_reads == []


@pytest.mark.parametrize("suffix", ["raw.json", "rows.jsonl"])
def test_same_size_page_digest_refuses_before_provider_parser(stored, suffix):
    target = stored[0] / ("page0001." + suffix)
    original = target.read_bytes()
    changed = original.replace(b"Synthetic Firm", b"Synthetic Xirm")
    assert changed != original and len(changed) == len(original)
    target.write_bytes(changed)
    calls = []
    parser_code = d._capture._response_rows_and_next_url.__code__
    def observed(frame, event, _arg):
        if event == "call" and frame.f_code is parser_code:
            calls.append(True)
    previous = sys.getprofile()
    try:
        sys.setprofile(observed)
        with pytest.raises(d.RatingsDeltaError):
            read(stored)
    finally:
        sys.setprofile(previous)
    assert calls == []


@pytest.mark.parametrize("kind", ["bytearray", "memoryview", "bytes_subclass", "text_subclass",
    "view_impostor", "locator_impostor", "view_enum_impostor", "digest_subclass"])
def test_authority_rejects_equal_value_alternate_field_types(stored, kind):
    value = read(stored)
    source = value._rows[0]
    calls = []
    class Text(str):
        pass
    class Bytes(bytes):
        pass
    def replacement_record(original):
        def record():
            calls.append(True)
            return original
        return SimpleNamespace(to_record=record)
    if kind in {"bytearray", "memoryview", "bytes_subclass"}:
        constructor = {"bytearray": bytearray, "memoryview": memoryview, "bytes_subclass": Bytes}[kind]
        object.__setattr__(source, "raw_row_bytes", constructor(source.raw_row_bytes))
    elif kind == "text_subclass":
        object.__setattr__(source, "action_label", Text(source.action_label))
    elif kind == "view_impostor":
        object.__setattr__(source, "current_view", replacement_record(source.current_view.to_record()))
    elif kind == "locator_impostor":
        object.__setattr__(source, "locator", replacement_record(source.locator.to_record()))
    elif kind == "view_enum_impostor":
        object.__setattr__(source.current_view, "view", SimpleNamespace(value=source.current_view.view.value))
    else:
        object.__setattr__(value, "manifest_sha256", Text(value.manifest_sha256))
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(value)
    assert calls == []


def test_mutated_context_is_type_checked_before_copy_hooks(stored):
    value = read(stored)
    calls = []
    original = value.context.capture_id
    class CopyHook:
        def __deepcopy__(self, memo):
            calls.append(True)
            return original
    object.__setattr__(value.context, "capture_id", CopyHook())
    with pytest.raises(d.RatingsDeltaError):
        d.require_authenticated_ratings_delta(value)
    assert calls == []
