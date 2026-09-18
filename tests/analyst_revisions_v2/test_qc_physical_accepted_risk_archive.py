"""Focused offline tests for the disk-backed C1 accepted-risk archive."""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2 import accepted_risk_input_pair as c1_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    InputView,
    MAX_CAPTURE_PAGE_BYTES,
    MassiveSourceRole,
    RowDisposition,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    physical_accepted_risk_archive as physical_module,
)
from research.analyst_revisions_v2_qc.accepted_risk_pair_bridge import (
    PAIR_ARTIFACT_DOMAIN,
    render_formal_accepted_risk_pair_artifact_bytes,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchiveCapacityError,
    PhysicalAcceptedRiskArchiveError,
    _JsonArray,
    _RawJson,
    _build_physical_accepted_risk_archive_for_test,
    _iter_canonical_object,
    _load_test_fixture_physical_accepted_risk_archive,
    _write_private,
    build_physical_accepted_risk_archive,
    iter_physical_accepted_risk_rows,
    require_physical_accepted_risk_archive,
)
from scripts import capture_arv2_massive as capture_module
from scripts import build_arv2_massive_input_pair as pair_builder_module
from scripts.build_arv2_massive_input_pair import (
    _build_massive_accepted_risk_input_pair_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    FakeResponse,
    ROLE_ORDER,
    _endpoint,
    _payload,
    _rebind_manifest_physical_identity,
    _rewrite_manifest,
    _row,
    _spooled_capture,
)


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


def _stat_with(metadata, **changes):
    names = (
        "st_mode",
        "st_ino",
        "st_dev",
        "st_nlink",
        "st_uid",
        "st_gid",
        "st_size",
        "st_atime_ns",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    values = {name: getattr(metadata, name) for name in names}
    values.update(changes)
    return SimpleNamespace(**values)


_TEST_RELOAD_PINS: dict[Path, tuple[str, str]] = {}


def load_physical_accepted_risk_archive(
    *, archive_path: Path, source_artifact_path: Path
):
    pins = _TEST_RELOAD_PINS.get(archive_path)
    if pins is None:
        pins = _TEST_RELOAD_PINS.get(source_artifact_path)
    assert pins is not None
    return _load_test_fixture_physical_accepted_risk_archive(
        archive_path=archive_path,
        source_artifact_path=source_artifact_path,
        expected_archive_sha256=pins[0],
        expected_source_manifest_sha256=pins[1],
    )


def _build(tmp_path: Path):
    capture, _session = _spooled_capture(tmp_path)
    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    pins = (archive.archive_sha256, archive.source_manifest_sha256)
    _TEST_RELOAD_PINS[archive.archive_path] = pins
    _TEST_RELOAD_PINS[capture.artifact_path] = pins
    return capture, archive


def _rewrite_archive_manifest(archive, transform) -> None:
    manifest = archive.archive_path / physical_module.ARCHIVE_MANIFEST
    digest = archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    value = json.loads(manifest.read_bytes())
    transform(value)
    payload = canonical_json_bytes(value)
    manifest.write_bytes(payload)
    manifest.chmod(0o600)
    digest.write_bytes((hashlib.sha256(payload).hexdigest() + "\n").encode())
    digest.chmod(0o600)


def _visitor_pages(capture):
    pages = []
    summary = capture_module._visit_authenticated_massive_capture_pages_for_bridge(
        capture.artifact_path,
        expected_transport=capture_module.TEST_TRANSPORT,
        visit_page=pages.append,
    )
    return pages, summary


def _publication_tree(tmp_path: Path):
    (
        root,
        repository_path,
        root_name,
        repository_fd,
        root_fd,
    ) = physical_module._prepare_output_root(tmp_path / "accepted-risk")
    stage_name, stage_fd, source_fd, rows_fd = physical_module._make_stage_at(
        root_fd
    )
    return {
        "repository_path": repository_path,
        "repository_fd": repository_fd,
        "root_path": root,
        "root_name": root_name,
        "root_fd": root_fd,
        "stage_fd": stage_fd,
        "source_fd": source_fd,
        "rows_fd": rows_fd,
        "stage_name": stage_name,
    }


def _close_publication_tree(tree) -> None:
    for name in (
        "rows_fd",
        "source_fd",
        "stage_fd",
        "root_fd",
        "repository_fd",
    ):
        try:
            os.close(tree[name])
        except OSError:
            pass


def _verified_jsonl_fixture(tmp_path: Path):
    directory = tmp_path / "verified-jsonl"
    directory.mkdir(mode=0o700)
    payload = b'{"row":1}\n{"row":2}\n'
    leaf = directory / "rows.jsonl"
    leaf.write_bytes(payload)
    leaf.chmod(0o600)
    parent_fd = os.open(directory, physical_module._DIRECTORY_OPEN_FLAGS)
    return parent_fd, payload


def _verified_jsonl_fragments(parent_fd: int, payload: bytes, **overrides):
    arguments = {
        "maximum_bytes": 4096,
        "maximum_line_bytes": 1024,
        "expected_byte_count": len(payload),
        "expected_sha256": hashlib.sha256(payload).hexdigest(),
        "expected_row_count": 2,
        "name": "test JSONL shard",
    }
    arguments.update(overrides)
    return physical_module._iter_verified_jsonl_fragments_at(
        parent_fd,
        "rows.jsonl",
        **arguments,
    )


def test_verified_jsonl_terminal_refuses_streamed_byte_count_vs_opened_size(
    tmp_path, monkeypatch
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_fstat = os.fstat
    calls = 0

    def changed_opened_size(descriptor):
        nonlocal calls
        metadata = original_fstat(descriptor)
        calls += 1
        if calls == 1:
            return _stat_with(metadata, st_size=metadata.st_size + 1)
        return metadata

    monkeypatch.setattr(physical_module.os, "fstat", changed_opened_size)
    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard streamed byte count changed from opened size"
            ),
        ):
            tuple(_verified_jsonl_fragments(parent_fd, payload))
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        (
            {"expected_byte_count": 1},
            "test JSONL shard streamed byte count does not match expected byte count",
        ),
        (
            {"expected_row_count": 1},
            "test JSONL shard row count does not match expected row count",
        ),
        (
            {"expected_sha256": "0" * 64},
            "test JSONL shard content SHA-256 does not match expected SHA-256",
        ),
    ),
    ids=("expected-byte-count", "expected-row-count", "expected-sha256"),
)
def test_verified_jsonl_terminal_expected_value_refusals_are_distinctive(
    tmp_path, overrides, message
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(message),
        ):
            tuple(_verified_jsonl_fragments(parent_fd, payload, **overrides))
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize(
    ("snapshot", "mutation", "message"),
    (
        (
            "after",
            "type",
            "test JSONL shard exhausted descriptor is not a regular file",
        ),
        (
            "named",
            "type",
            "test JSONL shard named entry is not a regular file",
        ),
        (
            "after",
            "mode",
            "test JSONL shard exhausted descriptor mode is not 0600",
        ),
        (
            "named",
            "mode",
            "test JSONL shard named entry mode is not 0600",
        ),
        (
            "after",
            "links",
            "test JSONL shard exhausted descriptor link count is not one",
        ),
        (
            "named",
            "links",
            "test JSONL shard named entry link count is not one",
        ),
        (
            "named",
            "owner",
            "test JSONL shard named entry is not owner-held",
        ),
    ),
    ids=(
        "after-type",
        "named-type",
        "after-mode",
        "named-mode",
        "after-links",
        "named-links",
        "named-owner",
    ),
)
def test_verified_jsonl_terminal_metadata_refusals_are_distinctive(
    tmp_path, monkeypatch, snapshot, mutation, message
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_fstat = os.fstat
    original_stat = os.stat
    fstat_calls = 0
    stat_calls = 0

    def mutate(metadata):
        if mutation == "type":
            return _stat_with(
                metadata,
                st_mode=physical_module.stat.S_IFDIR | 0o600,
            )
        if mutation == "mode":
            return _stat_with(metadata, st_mode=metadata.st_mode | 0o040)
        if mutation == "owner":
            return _stat_with(metadata, st_uid=metadata.st_uid + 1)
        return _stat_with(metadata, st_nlink=2)

    def changed_fstat(descriptor):
        nonlocal fstat_calls
        metadata = original_fstat(descriptor)
        fstat_calls += 1
        if snapshot == "after" and fstat_calls == 2:
            return mutate(metadata)
        return metadata

    def changed_stat(path, *args, **kwargs):
        nonlocal stat_calls
        metadata = original_stat(path, *args, **kwargs)
        if path == "rows.jsonl" and kwargs.get("dir_fd") == parent_fd:
            stat_calls += 1
            if snapshot == "named" and stat_calls == 2:
                return mutate(metadata)
        return metadata

    monkeypatch.setattr(physical_module.os, "fstat", changed_fstat)
    monkeypatch.setattr(physical_module.os, "stat", changed_stat)
    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(message),
        ):
            tuple(_verified_jsonl_fragments(parent_fd, payload))
    finally:
        os.close(parent_fd)


def test_verified_jsonl_terminal_refuses_descriptor_identity_change_at_exhaustion(
    tmp_path, monkeypatch
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_fstat = os.fstat
    calls = 0

    def changed_after_identity(descriptor):
        nonlocal calls
        metadata = original_fstat(descriptor)
        calls += 1
        if calls == 2:
            return _stat_with(
                metadata, st_mtime_ns=metadata.st_mtime_ns + 1
            )
        return metadata

    monkeypatch.setattr(physical_module.os, "fstat", changed_after_identity)
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    try:
        assert next(iterator) == b'{"row":1}'
        assert next(iterator) == b'{"row":2}'
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard opened descriptor identity changed during iteration"
            ),
        ):
            next(iterator)
    finally:
        iterator.close()
        os.close(parent_fd)


def test_verified_jsonl_terminal_refuses_named_identity_change_at_exhaustion(
    tmp_path, monkeypatch
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_stat = os.stat
    calls = 0

    def changed_named_identity(path, *args, **kwargs):
        nonlocal calls
        metadata = original_stat(path, *args, **kwargs)
        if path == "rows.jsonl" and kwargs.get("dir_fd") == parent_fd:
            calls += 1
            if calls == 2:
                return _stat_with(
                    metadata, st_mtime_ns=metadata.st_mtime_ns + 1
                )
        return metadata

    monkeypatch.setattr(physical_module.os, "stat", changed_named_identity)
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    try:
        assert next(iterator) == b'{"row":1}'
        assert next(iterator) == b'{"row":2}'
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard named entry identity changed during iteration"
            ),
        ):
            next(iterator)
    finally:
        iterator.close()
        os.close(parent_fd)


@pytest.mark.parametrize(
    ("platform", "accepted"),
    (("darwin", True), ("linux", False)),
)
def test_verified_jsonl_same_mode_fchmod_ctime_drift_is_darwin_only(
    tmp_path, monkeypatch, platform, accepted
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_fdopen = os.fdopen
    opened_descriptors = []

    def capture_descriptor(descriptor, *args, **kwargs):
        opened_descriptors.append(descriptor)
        return original_fdopen(descriptor, *args, **kwargs)

    monkeypatch.setattr(physical_module.os, "fdopen", capture_descriptor)
    monkeypatch.setattr(
        physical_module, "sys", SimpleNamespace(platform=platform)
    )
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    try:
        assert next(iterator) == b'{"row":1}'
        assert len(opened_descriptors) == 1
        descriptor = opened_descriptors[0]
        ctime_before = os.fstat(descriptor).st_ctime_ns
        os.fchmod(descriptor, 0o600)
        assert os.fstat(descriptor).st_ctime_ns != ctime_before
        if accepted:
            assert tuple(iterator) == (b'{"row":2}',)
        else:
            with pytest.raises(
                PhysicalAcceptedRiskArchiveError,
                match=_exact(
                    "test JSONL shard opened descriptor identity changed during iteration"
                ),
            ):
                tuple(iterator)
    finally:
        iterator.close()
        os.close(parent_fd)


def test_verified_jsonl_real_content_mutation_during_iteration_is_refused(
    tmp_path, monkeypatch
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    original_fdopen = os.fdopen
    opened_descriptors = []

    def capture_descriptor(descriptor, *args, **kwargs):
        opened_descriptors.append(descriptor)
        return original_fdopen(descriptor, *args, **kwargs)

    monkeypatch.setattr(physical_module.os, "fdopen", capture_descriptor)
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    writer = None
    try:
        assert next(iterator) == b'{"row":1}'
        descriptor = opened_descriptors[0]
        mtime_before = os.fstat(descriptor).st_mtime_ns
        writer = os.open(
            tmp_path / "verified-jsonl" / "rows.jsonl", os.O_WRONLY
        )
        assert os.pwrite(writer, b"9", 7) == 1
        os.close(writer)
        writer = None
        assert os.fstat(descriptor).st_mtime_ns != mtime_before
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard opened descriptor identity changed during iteration"
            ),
        ):
            tuple(iterator)
    finally:
        if writer is not None:
            os.close(writer)
        iterator.close()
        os.close(parent_fd)


def test_verified_jsonl_real_mode_mutation_during_iteration_is_refused(
    tmp_path
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    leaf = tmp_path / "verified-jsonl" / "rows.jsonl"
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    try:
        assert next(iterator) == b'{"row":1}'
        leaf.chmod(0o640)
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard exhausted descriptor mode is not 0600"
            ),
        ):
            tuple(iterator)
    finally:
        iterator.close()
        os.close(parent_fd)


def test_verified_jsonl_real_named_replacement_during_iteration_is_refused(
    tmp_path, monkeypatch
):
    parent_fd, payload = _verified_jsonl_fixture(tmp_path)
    leaf = tmp_path / "verified-jsonl" / "rows.jsonl"
    held = leaf.with_name("held-rows.jsonl")
    monkeypatch.setattr(
        physical_module, "sys", SimpleNamespace(platform="darwin")
    )
    iterator = _verified_jsonl_fragments(parent_fd, payload)
    try:
        assert next(iterator) == b'{"row":1}'
        leaf.rename(held)
        leaf.write_bytes(payload)
        leaf.chmod(0o600)
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "test JSONL shard named entry identity changed during iteration"
            ),
        ):
            tuple(iterator)
    finally:
        iterator.close()
        os.close(parent_fd)


def test_streamed_canonical_object_is_byte_exact_for_nested_fragments(tmp_path):
    report = tmp_path / "report.json"
    report.write_bytes(canonical_json_bytes({"z": [1, "two"], "a": False}))
    values = {
        "z": None,
        "rows": _JsonArray(
            lambda: iter(
                (
                    canonical_json_bytes({"b": 2})[:-1],
                    canonical_json_bytes({"a": 1})[:-1],
                )
            )
        ),
        "report": _RawJson(lambda: iter((report.read_bytes()[:-1],))),
        "a": "café",
    }

    streamed = b"".join(_iter_canonical_object(values, terminate=True))

    assert streamed == canonical_json_bytes(
        {
            "z": None,
            "rows": [{"b": 2}, {"a": 1}],
            "report": {"z": [1, "two"], "a": False},
            "a": "café",
        }
    )


def test_disk_archive_matches_the_legacy_c1_oracle_byte_for_byte(tmp_path):
    capture, archive = _build(tmp_path)
    legacy = _build_massive_accepted_risk_input_pair_for_test(
        capture.artifact_path
    )
    rows = tuple(iter_physical_accepted_risk_rows(archive))
    legacy_payload = render_formal_accepted_risk_pair_artifact_bytes(legacy)

    assert require_physical_accepted_risk_archive(archive) is archive
    assert [row.to_record() for row in rows] == [
        row.to_record() for row in legacy.pair.rows
    ]
    assert archive.pair_id == legacy.pair.pair_id
    assert archive.pair_sha256 == legacy.pair.pair_sha256
    assert archive.physical_capture_id == capture.capture_id
    assert archive.physical_capture_sha256 == capture.capture_sha256
    assert archive.capture_id == legacy.pair.capture.capture_id
    assert archive.capture_sha256 == legacy.pair.capture.capture_sha256
    assert archive.capture_id != archive.physical_capture_id
    assert archive.capture_sha256 != archive.physical_capture_sha256
    assert archive.pair_artifact.content_sha256 == hashlib.sha256(
        legacy_payload
    ).hexdigest()
    assert archive.pair_artifact.artifact_sha256 == hashlib.sha256(
        PAIR_ARTIFACT_DOMAIN + legacy_payload
    ).hexdigest()
    assert archive.pair_artifact.byte_count == len(legacy_payload)
    assert archive.current_included_count == legacy.pair.report.current_included_count
    assert archive.censored_included_count == legacy.pair.report.censored_included_count
    assert archive.disagreement_count == legacy.pair.report.disagreement_count
    assert archive.source_row_count == len(legacy.pair.rows)
    assert archive.full_capture_materialized is False
    assert archive.views_share_one_capture is True
    assert archive.pristine_point_in_time is False
    assert all(
        getattr(archive, name) is False
        for name in (
            "provider_access",
            "credential_access",
            "quantconnect_access",
            "outcome_access",
            "result_access",
            "deployment",
            "orders",
            "trading",
        )
    )


def test_disk_archive_reloads_after_process_local_authority_reset(tmp_path):
    capture, archive = _build(tmp_path)
    expected_records = tuple(
        row.to_record() for row in iter_physical_accepted_risk_rows(archive)
    )
    expected_fields = {
        field.name: getattr(archive, field.name)
        for field in dataclasses.fields(archive)
    }

    physical_module._AUTHORITIES.clear()
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive is not current builder authority"),
    ):
        require_physical_accepted_risk_archive(archive)

    reloaded = load_physical_accepted_risk_archive(
        archive_path=archive.archive_path,
        source_artifact_path=capture.artifact_path,
    )

    assert reloaded is not archive
    assert type(reloaded) is type(archive)
    assert type(reloaded.pair_artifact) is type(archive.pair_artifact)
    assert type(reloaded.role_row_counts) is tuple
    assert type(reloaded.shards) is tuple
    assert all(
        type(item) is physical_module.AcceptedRiskShardDescriptor
        for item in reloaded.shards
    )
    assert {
        field.name: getattr(reloaded, field.name)
        for field in dataclasses.fields(reloaded)
    } == expected_fields
    authority = physical_module._AUTHORITIES[id(reloaded)]
    assert authority[0]() is reloaded
    assert require_physical_accepted_risk_archive(reloaded) is reloaded
    assert tuple(
        row.to_record() for row in iter_physical_accepted_risk_rows(reloaded)
    ) == expected_records


def test_disk_archive_builder_authority_is_process_local(tmp_path, monkeypatch):
    _capture, archive = _build(tmp_path)
    builder_pid = os.getpid()
    monkeypatch.setattr(physical_module.os, "getpid", lambda: builder_pid + 1)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive is not current builder authority"),
    ):
        require_physical_accepted_risk_archive(archive)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_disk_archive_authority_cannot_be_inherited_across_fork(tmp_path):
    _capture, archive = _build(tmp_path)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions run in the parent
        os.close(read_fd)
        try:
            require_physical_accepted_risk_archive(archive)
        except BaseException as exc:
            payload = f"{type(exc).__name__}:{exc}".encode("utf-8")
        else:
            payload = b"accepted"
        try:
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
            os._exit(0)

    os.close(write_fd)
    try:
        observed = os.read(read_fd, 4096).decode("utf-8")
    finally:
        os.close(read_fd)
    waited_pid, status = os.waitpid(child_pid, 0)

    assert waited_pid == child_pid
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert observed == (
        "PhysicalAcceptedRiskArchiveError:"
        "accepted-risk archive is not current builder authority"
    )


def test_disk_archive_reload_requires_external_archive_pin(tmp_path):
    capture, archive = _build(tmp_path)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload does not match its external trust pin"),
    ):
        _load_test_fixture_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
            expected_archive_sha256="0" * 64,
            expected_source_manifest_sha256=archive.source_manifest_sha256,
        )


def test_disk_archive_reload_cannot_self_promote_test_capture_transport(tmp_path):
    capture, archive = _build(tmp_path)
    manifest_path = archive.archive_path / physical_module.ARCHIVE_MANIFEST
    digest_path = archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    manifest = json.loads(manifest_path.read_bytes())
    manifest["capture_transport"] = capture_module.PRODUCTION_TRANSPORT
    seed = dict(manifest)
    seed.pop("archive_id")
    seed.pop("archive_sha256")
    promoted_sha256 = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    promoted_id = f"arv2-physical-accepted-risk-{promoted_sha256[:24]}"
    manifest["archive_id"] = promoted_id
    manifest["archive_sha256"] = promoted_sha256
    payload = canonical_json_bytes(manifest)
    manifest_path.write_bytes(payload)
    manifest_path.chmod(0o600)
    digest_path.write_bytes((hashlib.sha256(payload).hexdigest() + "\n").encode())
    digest_path.chmod(0o600)
    promoted_path = archive.archive_path.with_name(promoted_id)
    archive.archive_path.rename(promoted_path)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload source manifest identity is inconsistent"
        ),
    ):
        physical_module._load_physical_accepted_risk_archive(
            archive_path=promoted_path,
            source_artifact_path=capture.artifact_path,
            expected_archive_sha256=promoted_sha256,
            expected_source_manifest_sha256=archive.source_manifest_sha256,
            expected_transport=capture_module.PRODUCTION_TRANSPORT,
            require_repository_paths=False,
        )


def test_root_manifest_ctime_drift_is_accepted_only_with_exact_bytes(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original_pair = physical_module._pair_binding_from_archive_fds
    paths = (
        archive.archive_path / physical_module.ARCHIVE_MANIFEST,
        archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST,
    )
    before = {path: path.stat() for path in paths}
    after = {}

    def finish_pair(*args, **kwargs):
        value = original_pair(*args, **kwargs)
        for path in paths:
            path.chmod(0o600)
            after[path] = path.stat()
        return value

    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", finish_pair
    )

    assert require_physical_accepted_risk_archive(archive) is archive
    assert set(after) == set(paths)
    assert all(
        (
            after[path].st_dev,
            after[path].st_ino,
            after[path].st_size,
            after[path].st_mtime_ns,
        )
        == (
            before[path].st_dev,
            before[path].st_ino,
            before[path].st_size,
            before[path].st_mtime_ns,
        )
        and after[path].st_ctime_ns != before[path].st_ctime_ns
        for path in paths
    )


def test_root_manifest_content_change_is_refused_despite_restored_mtime(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original_pair = physical_module._pair_binding_from_archive_fds
    manifest_path = archive.archive_path / physical_module.ARCHIVE_MANIFEST
    digest_path = archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST

    def corrupt_after_pair(*args, **kwargs):
        value = original_pair(*args, **kwargs)
        manifest_metadata = manifest_path.stat()
        digest_metadata = digest_path.stat()
        payload = manifest_path.read_bytes()
        replacement_id = "x" + archive.archive_id[1:]
        changed = payload.replace(
            archive.archive_id.encode("ascii"),
            replacement_id.encode("ascii"),
            1,
        )
        assert changed != payload and len(changed) == len(payload)
        manifest_path.write_bytes(changed)
        digest_path.write_bytes(
            (hashlib.sha256(changed).hexdigest() + "\n").encode("ascii")
        )
        os.utime(
            manifest_path,
            ns=(manifest_metadata.st_atime_ns, manifest_metadata.st_mtime_ns),
        )
        os.utime(
            digest_path,
            ns=(digest_metadata.st_atime_ns, digest_metadata.st_mtime_ns),
        )
        return value

    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", corrupt_after_pair
    )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive manifest does not authenticate"),
    ):
        require_physical_accepted_risk_archive(archive)


@pytest.mark.parametrize("changed_field", ["st_ino", "st_mtime_ns"])
def test_root_manifest_inode_or_mtime_drift_remains_refused(
    tmp_path, monkeypatch, changed_field
):
    _capture, archive = _build(tmp_path)
    root_fd = physical_module._open_private_directory(
        archive.archive_path, "test archive"
    )
    source_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.SOURCE_DIRECTORY
    )
    rows_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.ROW_DIRECTORY
    )
    original_stat = os.stat
    try:
        identities = physical_module._pin_archive_leaf_identities(
            root_fd, source_fd, rows_fd, archive
        )

        def changed_stat(path, *args, **kwargs):
            metadata = original_stat(path, *args, **kwargs)
            if (
                path == physical_module.ARCHIVE_MANIFEST
                and kwargs.get("dir_fd") == root_fd
            ):
                return _stat_with(
                    metadata,
                    **{changed_field: getattr(metadata, changed_field) + 1},
                )
            return metadata

        monkeypatch.setattr(physical_module.os, "stat", changed_stat)
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk archive named leaf identity changed"),
        ):
            physical_module._require_archive_leaf_identities(
                root_fd, source_fd, rows_fd, identities
            )
    finally:
        os.close(rows_fd)
        os.close(source_fd)
        os.close(root_fd)


def test_data_shard_ctime_drift_remains_refused(tmp_path, monkeypatch):
    _capture, archive = _build(tmp_path)
    root_fd = physical_module._open_private_directory(
        archive.archive_path, "test archive"
    )
    source_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.SOURCE_DIRECTORY
    )
    rows_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.ROW_DIRECTORY
    )
    original_stat = os.stat
    shard_name = Path(archive.shards[0].source_relative_path).name
    try:
        identities = physical_module._pin_archive_leaf_identities(
            root_fd, source_fd, rows_fd, archive
        )

        def changed_stat(path, *args, **kwargs):
            metadata = original_stat(path, *args, **kwargs)
            if path == shard_name and kwargs.get("dir_fd") == source_fd:
                return _stat_with(metadata, st_ctime_ns=metadata.st_ctime_ns + 1)
            return metadata

        monkeypatch.setattr(physical_module.os, "stat", changed_stat)
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk archive named leaf identity changed"),
        ):
            physical_module._require_archive_leaf_identities(
                root_fd, source_fd, rows_fd, identities
            )
    finally:
        os.close(rows_fd)
        os.close(source_fd)
        os.close(root_fd)


def test_darwin_data_ctime_reconciliation_rehashes_once_then_repins(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    root_fd = physical_module._open_private_directory(
        archive.archive_path, "test archive"
    )
    source_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.SOURCE_DIRECTORY
    )
    rows_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.ROW_DIRECTORY
    )
    filename = Path(archive.shards[0].source_relative_path).name
    key = ("source", filename)
    try:
        all_pins = physical_module._pin_archive_leaf_identities(
            root_fd, source_fd, rows_fd, archive
        )
        original = all_pins[key]
        pin = dataclasses.replace(
            original,
            identity=(
                *original.identity[:4],
                original.identity[4] - 1,
                *original.identity[5:],
            ),
        )
        observed = original.identity
        original_observe = physical_module._observe_archive_leaf
        original_hash = physical_module._hash_private_regular_at
        rehashes = []

        def observe(parent_fd, leaf, **kwargs):
            if parent_fd == source_fd and leaf == filename:
                return observed
            return original_observe(parent_fd, leaf, **kwargs)

        def rehash(parent_fd, leaf, **kwargs):
            if parent_fd == source_fd and leaf == filename:
                rehashes.append(leaf)
            return original_hash(parent_fd, leaf, **kwargs)

        monkeypatch.setattr(
            physical_module, "sys", SimpleNamespace(platform="darwin")
        )
        monkeypatch.setattr(physical_module, "_observe_archive_leaf", observe)
        monkeypatch.setattr(physical_module, "_hash_private_regular_at", rehash)
        pins = {key: pin}

        physical_module._require_archive_leaf_identities(
            root_fd, source_fd, rows_fd, pins
        )
        assert pins[key].identity == observed
        assert rehashes == [filename]

        physical_module._require_archive_leaf_identities(
            root_fd, source_fd, rows_fd, pins
        )
        assert rehashes == [filename]
    finally:
        os.close(rows_fd)
        os.close(source_fd)
        os.close(root_fd)


@pytest.mark.parametrize("identity_index", [0, 1, 2, 3, 5, 6, 7])
def test_darwin_ctime_reconciliation_preserves_every_nonctime_identity_field(
    tmp_path, monkeypatch, identity_index
):
    _capture, archive = _build(tmp_path)
    root_fd = physical_module._open_private_directory(
        archive.archive_path, "test archive"
    )
    source_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.SOURCE_DIRECTORY
    )
    rows_fd = physical_module._open_private_child_directory(
        root_fd, physical_module.ROW_DIRECTORY
    )
    filename = Path(archive.shards[0].source_relative_path).name
    key = ("source", filename)
    try:
        pin = physical_module._pin_archive_leaf_identities(
            root_fd, source_fd, rows_fd, archive
        )[key]
        changed = list(pin.identity)
        changed[identity_index] += 1
        changed[4] += 1
        monkeypatch.setattr(
            physical_module, "sys", SimpleNamespace(platform="darwin")
        )
        monkeypatch.setattr(
            physical_module,
            "_observe_archive_leaf",
            lambda *_args, **_kwargs: tuple(changed),
        )
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk archive named leaf identity changed"),
        ):
            physical_module._require_archive_leaf_identities(
                root_fd, source_fd, rows_fd, {key: pin}
            )
    finally:
        os.close(rows_fd)
        os.close(source_fd)
        os.close(root_fd)


def test_disk_archive_reload_requires_exact_absolute_path_objects(tmp_path):
    capture, archive = _build(tmp_path)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload archive path must be an exact absolute Path"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=str(archive.archive_path),
            source_artifact_path=capture.artifact_path,
        )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload source path must be an exact absolute Path"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=Path(capture.artifact_path.name),
        )


def test_disk_archive_reload_refuses_rebound_parser_contract_before_io(
    tmp_path, monkeypatch
):
    capture, archive = _build(tmp_path)
    physical_module._AUTHORITIES.clear()
    monkeypatch.setattr(
        physical_module,
        "_RELOAD_MANIFEST_KEYS",
        (*physical_module._RELOAD_MANIFEST_KEYS, "unexpected"),
    )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_unknown_manifest_key(tmp_path):
    capture, archive = _build(tmp_path)
    _rewrite_archive_manifest(
        archive, lambda value: value.__setitem__("unexpected", False)
    )
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload manifest has unknown, missing, or "
            "non-string keys"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_unknown_nested_manifest_key(tmp_path):
    capture, archive = _build(tmp_path)

    def add_unknown_key(value):
        value["shards"][0]["unexpected"] = False

    _rewrite_archive_manifest(archive, add_unknown_key)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload shard entry has unknown, missing, or "
            "non-string keys"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_boolean_in_integer_field(tmp_path):
    capture, archive = _build(tmp_path)
    _rewrite_archive_manifest(
        archive, lambda value: value.__setitem__("source_page_count", True)
    )
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload manifest count changed type"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_unknown_role_before_minting(tmp_path):
    capture, archive = _build(tmp_path)

    def change_role(value):
        value["role_row_counts"][0]["source_role"] = "unknown-role"

    _rewrite_archive_manifest(archive, change_role)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload role census has an unknown role"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_noncanonical_manifest_bytes(tmp_path):
    capture, archive = _build(tmp_path)
    manifest = archive.archive_path / physical_module.ARCHIVE_MANIFEST
    digest = archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    payload = manifest.read_bytes()[:-1] + b" \n"
    manifest.write_bytes(payload)
    manifest.chmod(0o600)
    digest.write_bytes((hashlib.sha256(payload).hexdigest() + "\n").encode())
    digest.chmod(0o600)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload manifest is not canonical JSON"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_manifest_digest_tamper(tmp_path):
    capture, archive = _build(tmp_path)
    digest = archive.archive_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    digest.write_bytes(b"0" * 64 + b"\n")
    digest.chmod(0o600)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload manifest digest changed"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_changed_immutable_flag(tmp_path):
    capture, archive = _build(tmp_path)

    def grant_provider_access(value):
        value["capabilities"]["provider_access"] = True

    _rewrite_archive_manifest(archive, grant_provider_access)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload capabilities changed type or immutable value"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_nonprivate_archive_directory(tmp_path):
    capture, archive = _build(tmp_path)
    archive.archive_path.chmod(0o750)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload archive is not an owner-private directory"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_symlinked_manifest_leaf(tmp_path):
    capture, archive = _build(tmp_path)
    manifest = archive.archive_path / physical_module.ARCHIVE_MANIFEST
    held = archive.archive_path / ".held-manifest"
    manifest.rename(held)
    manifest.symlink_to(held.name)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk reload manifest is unavailable"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_source_path_substitution(tmp_path):
    capture, archive = _build(tmp_path)
    substituted = capture.artifact_path.with_name("substituted-source")
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload source path does not bind the manifest"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=substituted,
        )


def test_disk_archive_reload_refuses_source_manifest_digest_tamper(tmp_path):
    capture, archive = _build(tmp_path)
    digest = capture.artifact_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    digest.write_bytes(b"0" * 64 + b"\n")
    digest.chmod(0o600)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload source manifest does not authenticate"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_noncanonical_source_manifest(tmp_path):
    capture, archive = _build(tmp_path)
    manifest = capture.artifact_path / physical_module.ARCHIVE_MANIFEST
    digest = capture.artifact_path / physical_module.ARCHIVE_MANIFEST_DIGEST
    payload = manifest.read_bytes()[:-1] + b" \n"
    manifest.write_bytes(payload)
    manifest.chmod(0o600)
    digest.write_bytes((hashlib.sha256(payload).hexdigest() + "\n").encode())
    digest.chmod(0o600)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("source capture manifest is not canonical JSON"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_archive_path_substitution(tmp_path):
    capture, archive = _build(tmp_path)
    substituted = archive.archive_path.with_name("substituted-archive")
    archive.archive_path.rename(substituted)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk reload archive path does not bind the manifest"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=substituted,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_refuses_semantic_shard_tamper(tmp_path):
    capture, archive = _build(tmp_path)
    shard = archive.archive_path / archive.shards[0].semantic_relative_path
    shard.write_bytes(shard.read_bytes() + b"{}\n")
    shard.chmod(0o600)
    physical_module._AUTHORITIES.clear()

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk semantic shard streamed byte count does not match "
            "expected byte count"
        ),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )


def test_disk_archive_reload_removes_authority_after_full_reauth_failure(
    tmp_path, monkeypatch
):
    capture, archive = _build(tmp_path)
    observed = []

    def fail_pair(value, **_kwargs):
        observed.append(value)
        raise PhysicalAcceptedRiskArchiveError("injected pair reauth failure")

    physical_module._AUTHORITIES.clear()
    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", fail_pair
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("injected pair reauth failure"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )

    assert len(observed) == 1
    assert id(observed[0]) not in physical_module._AUTHORITIES


def test_disk_archive_reload_refuses_path_swap_and_removes_authority(
    tmp_path, monkeypatch
):
    capture, archive = _build(tmp_path)
    original_pair = physical_module._pair_binding_from_archive_fds
    held = archive.archive_path.with_name(f"{archive.archive_id}-held")
    observed = []

    def swap_after_pair(value, **kwargs):
        result = original_pair(value, **kwargs)
        observed.append(value)
        archive.archive_path.rename(held)
        archive.archive_path.mkdir(mode=0o700)
        return result

    physical_module._AUTHORITIES.clear()
    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", swap_after_pair
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive path identity changed"),
    ):
        load_physical_accepted_risk_archive(
            archive_path=archive.archive_path,
            source_artifact_path=capture.artifact_path,
        )

    assert len(observed) == 1
    assert id(observed[0]) not in physical_module._AUTHORITIES


def test_disk_archive_authenticates_predecessor_physical_identity_and_derives_current_c1(
    tmp_path,
):
    capture, _session = _spooled_capture(tmp_path)

    def rebind(value):
        _rebind_manifest_physical_identity(
            value,
            contract_sha256=(
                capture_module.PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256
            ),
        )

    _rewrite_manifest(capture.artifact_path, rebind)
    rewritten = json.loads((capture.artifact_path / "manifest.json").read_bytes())

    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    legacy = _build_massive_accepted_risk_input_pair_for_test(
        capture.artifact_path
    )

    assert archive.physical_capture_id == rewritten["capture_id"]
    assert archive.physical_capture_sha256 == rewritten["capture_sha256"]
    assert archive.capture_id == legacy.pair.capture.capture_id
    assert archive.capture_sha256 == legacy.pair.capture.capture_sha256
    assert archive.capture_id != archive.physical_capture_id
    assert archive.pair_id == legacy.pair.pair_id
    assert [
        row.to_record() for row in iter_physical_accepted_risk_rows(archive)
    ] == [row.to_record() for row in legacy.pair.rows]


def test_disk_archive_matches_oracle_across_censoring_and_refusal_rows(tmp_path):
    revised = _row("revised", role=ROLE_ORDER[0])
    revised["last_updated"] = "2022-01-01T00:00:00Z"
    revised["firm"] = "Crédit Test"
    invalid_date = _row("invalid-date", role=ROLE_ORDER[0])
    invalid_date["date"] = "not-a-date"
    missing_id = _row("unused", role=ROLE_ORDER[1])
    del missing_id["benzinga_id"]
    responses = [
        FakeResponse(
            _payload([revised, invalid_date]), _endpoint(ROLE_ORDER[0])
        ),
        FakeResponse(_payload([missing_id]), _endpoint(ROLE_ORDER[1])),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)
    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    legacy = _build_massive_accepted_risk_input_pair_for_test(
        capture.artifact_path
    )

    assert [row.to_record() for row in iter_physical_accepted_risk_rows(archive)] == [
        row.to_record() for row in legacy.pair.rows
    ]
    assert archive.pair_id == legacy.pair.pair_id
    assert archive.pair_sha256 == legacy.pair.pair_sha256
    assert archive.pair_artifact.byte_count == len(
        render_formal_accepted_risk_pair_artifact_bytes(legacy)
    )
    assert archive.current_included_count == legacy.pair.report.current_included_count
    assert archive.censored_included_count == legacy.pair.report.censored_included_count
    assert archive.disagreement_count == legacy.pair.report.disagreement_count == 1


def test_disk_archive_does_not_use_the_aggregate_capture_loader(
    tmp_path, monkeypatch
):
    capture, _session = _spooled_capture(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("aggregate loader was reached")

    monkeypatch.setattr(
        capture_module, "_load_massive_capture_artifact_bounded", forbidden
    )
    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )

    assert archive.source_row_count == 4


def test_disk_archive_visitor_does_not_retain_prior_page_objects(
    tmp_path,
):
    import gc
    import weakref

    capture, _session = _spooled_capture(tmp_path)
    original = capture_module._visit_authenticated_massive_capture_pages_for_bridge
    prior: weakref.ReferenceType[object] | None = None
    callbacks = 0

    def visitor(*, artifact_path, expected_transport, visit_page):
        def observe(page):
            nonlocal prior, callbacks
            gc.collect()
            if prior is not None:
                assert prior() is None
            visit_page(page)
            prior = weakref.ref(page)
            callbacks += 1

        return original(
            artifact_path,
            expected_transport=expected_transport,
            visit_page=observe,
        )

    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
        visitor=visitor,
    )

    assert callbacks == archive.source_page_count
    assert archive.maximum_source_page_byte_count <= MAX_CAPTURE_PAGE_BYTES


def test_disk_archive_refuses_cross_page_duplicate_provider_id(tmp_path):
    cursor = _endpoint(MassiveSourceRole.ANALYST_RATINGS) + "?cursor=two"
    responses = [
        FakeResponse(
            _payload([_row("duplicate", role=ROLE_ORDER[0])], cursor),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(
            _payload([_row("duplicate", role=ROLE_ORDER[0])]), cursor
        ),
        FakeResponse(
            _payload([_row("earnings", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("duplicate or conflicting benzinga_id invalidates the capture"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


def test_disk_archive_refuses_duplicate_earnings_provider_id(tmp_path):
    responses = [
        FakeResponse(
            _payload([_row("rating", role=ROLE_ORDER[0])]),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(
            _payload(
                [
                    _row("duplicate", role=ROLE_ORDER[1]),
                    _row("duplicate", role=ROLE_ORDER[1]),
                ]
            ),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("duplicate or conflicting benzinga_id invalidates the capture"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


def test_provider_id_census_refuses_wrong_role_types_and_incomplete_lookup(
    tmp_path,
):
    connection = physical_module._open_spool(tmp_path / "census.sqlite3")
    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("provider-ID census source role changed type"),
        ):
            physical_module._insert_provider_id(
                connection,
                _row("guidance", role=ROLE_ORDER[2]),
                "corporate_guidance",  # type: ignore[arg-type]
            )
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("provider-ID lookup source role changed type"),
        ):
            physical_module._is_duplicate_guidance_provider_id(
                connection,
                _row("guidance", role=ROLE_ORDER[2]),
                "corporate_guidance",  # type: ignore[arg-type]
            )
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("guidance duplicate-ID census is incomplete"),
        ):
            physical_module._is_duplicate_guidance_provider_id(
                connection,
                _row("guidance", role=ROLE_ORDER[2]),
                MassiveSourceRole.CORPORATE_GUIDANCE,
            )
    finally:
        connection.close()


def test_disk_archive_refuses_cross_role_duplicate_provider_id(tmp_path):
    responses = [
        FakeResponse(
            _payload([_row("duplicate", role=ROLE_ORDER[0])]),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(
            _payload([_row("duplicate", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("duplicate or conflicting benzinga_id invalidates the capture"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


@pytest.mark.parametrize("conflicting_payload", [False, True])
def test_disk_archive_matches_legacy_when_guidance_duplicate_is_quarantined(
    tmp_path, conflicting_payload
):
    duplicate_first = _row("guidance-duplicate", role=ROLE_ORDER[2])
    duplicate_second = dict(duplicate_first)
    if conflicting_payload:
        duplicate_second.update(
            {
                "date": "2021-02-04",
                "last_updated": "2021-02-04 09:30:00",
                "min_revenue_guidance": 1,
            }
        )
    unique = _row("guidance-unique", role=ROLE_ORDER[2])
    responses = [
        FakeResponse(
            _payload([_row("rating", role=ROLE_ORDER[0])]),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(
            _payload([_row("earnings", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([duplicate_first, duplicate_second, unique]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    legacy = _build_massive_accepted_risk_input_pair_for_test(
        capture.artifact_path
    )
    rows = tuple(iter_physical_accepted_risk_rows(archive))
    guidance = tuple(
        row
        for row in rows
        if row.locator.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
    )
    duplicated = tuple(
        row for row in guidance if row.provider_event_id == "guidance-duplicate"
    )
    retained_unique = next(
        row for row in guidance if row.provider_event_id == "guidance-unique"
    )

    assert len(rows) == archive.source_row_count == 5
    assert len(duplicated) == 2
    assert tuple(row.locator.row_offset for row in duplicated) == (0, 1)
    assert tuple(row.raw_row_bytes for row in duplicated) == (
        canonical_json_bytes(duplicate_first),
        canonical_json_bytes(duplicate_second),
    )
    assert all(
        row.current_view.disposition
        is RowDisposition.DUPLICATE_PROVIDER_EVENT_ID
        and row.censored_view.disposition
        is RowDisposition.DUPLICATE_PROVIDER_EVENT_ID
        and not row.current_view.included
        and not row.censored_view.included
        for row in duplicated
    )
    assert retained_unique.current_view.included is True
    assert retained_unique.censored_view.included is True
    assert [row.to_record() for row in rows] == [
        row.to_record() for row in legacy.pair.rows
    ]
    assert archive.pair_id == legacy.pair.pair_id
    assert archive.pair_sha256 == legacy.pair.pair_sha256
    assert archive.current_included_count == 3
    assert archive.censored_included_count == 3
    report = legacy.pair.report
    counts = {
        (item.view, item.disposition): item.count
        for item in report.disposition_counts
    }
    assert counts[
        (InputView.CURRENT_ROW, RowDisposition.DUPLICATE_PROVIDER_EVENT_ID)
    ] == 2
    assert counts[
        (
            InputView.CONSERVATIVE_CENSORED,
            RowDisposition.DUPLICATE_PROVIDER_EVENT_ID,
        )
    ] == 2


def test_disk_archive_refuses_unreviewed_rating_action(tmp_path):
    rating = _row("rating", role=ROLE_ORDER[0])
    rating["rating_action"] = "surprise_action"
    responses = [
        FakeResponse(_payload([rating]), _endpoint(ROLE_ORDER[0])),
        FakeResponse(
            _payload([_row("earnings", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("rating_action is not a reviewed provider action"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


@pytest.mark.parametrize(
    ("rating_action", "remove_field"),
    [
        (None, True),
        (None, False),
        ("", False),
    ],
)
def test_disk_archive_preserves_missing_or_exact_empty_action_for_c2_disposition(
    tmp_path, rating_action, remove_field
):
    rating = _row("rating-missing-action", role=ROLE_ORDER[0])
    if remove_field:
        rating.pop("rating_action")
    else:
        rating["rating_action"] = rating_action
    responses = [
        FakeResponse(_payload([rating]), _endpoint(ROLE_ORDER[0])),
        FakeResponse(
            _payload([_row("earnings", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    legacy = _build_massive_accepted_risk_input_pair_for_test(
        capture.artifact_path
    )
    rows = tuple(iter_physical_accepted_risk_rows(archive))
    source = rows[0]

    assert len(rows) == archive.source_row_count == 3
    assert source.raw_row_bytes == canonical_json_bytes(rating)
    assert source.action_label == "__missing_rating_or_target_action__"
    assert source.current_view.included is True
    assert source.censored_view.included is True
    assert [row.to_record() for row in rows] == [
        row.to_record() for row in legacy.pair.rows
    ]
    assert archive.pair_id == legacy.pair.pair_id
    assert archive.pair_sha256 == legacy.pair.pair_sha256


def test_disk_archive_refuses_whitespace_rating_action(tmp_path):
    rating = _row("rating-whitespace-action", role=ROLE_ORDER[0])
    rating["rating_action"] = "   "
    responses = [
        FakeResponse(_payload([rating]), _endpoint(ROLE_ORDER[0])),
        FakeResponse(
            _payload([_row("earnings", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    capture, _session = _spooled_capture(tmp_path, responses=responses)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("rating_action is not a reviewed provider action"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


def test_disk_archive_refuses_an_empty_capture(tmp_path):
    capture, _session = _spooled_capture(tmp_path, responses=[
        FakeResponse(_payload([]), _endpoint(role)) for role in ROLE_ORDER
    ])

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk input pair cannot be empty"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
        )


def test_disk_archive_refuses_non_authoritative_page_type(tmp_path):
    def visitor(*, artifact_path, expected_transport, visit_page):
        del artifact_path, expected_transport
        visit_page(object())

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("capture visitor yielded a non-authoritative page type"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=tmp_path / "capture",
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_disk_archive_refuses_visitor_summary_that_disagrees_with_pages(tmp_path):
    capture, _session = _spooled_capture(tmp_path)
    original = capture_module._visit_authenticated_massive_capture_pages_for_bridge

    def visitor(*, artifact_path, expected_transport, visit_page):
        summary = original(
            artifact_path,
            expected_transport=expected_transport,
            visit_page=visit_page,
        )
        return dataclasses.replace(
            summary, total_row_count=summary.total_row_count + 1
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "capture visitor summary does not match its exhaustive page traversal"
        ),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_disk_archive_refuses_physical_capture_identity_substitution(tmp_path):
    capture, _session = _spooled_capture(tmp_path)
    original = capture_module._visit_authenticated_massive_capture_pages_for_bridge

    def visitor(*, artifact_path, expected_transport, visit_page):
        summary = original(
            artifact_path,
            expected_transport=expected_transport,
            visit_page=visit_page,
        )
        return dataclasses.replace(
            summary,
            capture_id="arv2-capture-000000000000000000000000",
            capture_sha256="0" * 64,
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "physical capture identity does not match an admitted contract"
        ),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_disk_archive_refuses_an_unregistered_equal_copy(tmp_path):
    _capture, archive = _build(tmp_path)
    clone = object.__new__(type(archive))
    for field in dataclasses.fields(archive):
        object.__setattr__(clone, field.name, getattr(archive, field.name))

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive is not current builder authority"),
    ):
        require_physical_accepted_risk_archive(clone)


def test_disk_archive_refuses_equal_but_replaced_shard_container(tmp_path):
    _capture, archive = _build(tmp_path)
    object.__setattr__(archive, "shards", tuple(list(archive.shards)))

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive is not current builder authority"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_disk_archive_refuses_changed_semantic_shard(tmp_path):
    _capture, archive = _build(tmp_path)
    shard = archive.archive_path / archive.shards[0].semantic_relative_path
    with shard.open("ab") as handle:
        handle.write(b"{}\n")

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk semantic shard streamed byte count does not match "
            "expected byte count"
        ),
    ):
        require_physical_accepted_risk_archive(archive)


def test_disk_archive_refuses_changed_source_shard(tmp_path):
    _capture, archive = _build(tmp_path)
    shard = archive.archive_path / archive.shards[0].source_relative_path
    payload = shard.read_bytes()
    shard.write_bytes(payload + b"{}\n")
    os.chmod(shard, 0o600)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk source shard byte count, hash, or identity changed"
        ),
    ):
        require_physical_accepted_risk_archive(archive)


def test_disk_archive_refuses_nonprivate_source_shard(tmp_path):
    _capture, archive = _build(tmp_path)
    shard = archive.archive_path / archive.shards[0].source_relative_path
    shard.chmod(0o640)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk source shard is not a bounded owner-held private regular file"
        ),
    ):
        require_physical_accepted_risk_archive(archive)


def test_disk_archive_refuses_manifest_or_inventory_tamper(tmp_path):
    _capture, archive = _build(tmp_path)
    extra = archive.archive_path / "unexpected"
    extra.write_bytes(b"x")
    extra.chmod(0o600)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive inventory changed"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_disk_archive_refuses_manifest_content_tamper(tmp_path):
    _capture, archive = _build(tmp_path)
    manifest = archive.archive_path / "manifest.json"
    payload = manifest.read_bytes()
    manifest.write_bytes(payload[:-2] + b" \n")
    manifest.chmod(0o600)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive manifest does not authenticate"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_archive_writer_refuses_before_crossing_fixed_byte_bound(tmp_path):
    destination = tmp_path / "bounded"

    with pytest.raises(
        PhysicalAcceptedRiskArchiveCapacityError,
        match=_exact("archive writer exceeded its fixed byte bound"),
    ):
        _write_private(destination, (b"1234", b"5"), maximum_bytes=4)

    assert destination.exists() is False


def test_production_builder_refuses_non_repository_paths(tmp_path):
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "production C1 source and output must remain in separate artifacts paths"
        ),
    ):
        build_physical_accepted_risk_archive(
            source_artifact_path=tmp_path / "capture",
            output_root=tmp_path / "accepted-risk",
        )


def test_production_builder_refuses_rebound_capture_visitor_before_io(
    tmp_path, monkeypatch
):
    reached = False

    def visitor(*_args, **_kwargs):
        nonlocal reached
        reached = True

    monkeypatch.setattr(
        capture_module,
        "_visit_authenticated_massive_capture_pages_for_bridge",
        visitor,
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        build_physical_accepted_risk_archive(
            source_artifact_path=tmp_path / "capture",
            output_root=tmp_path / "accepted-risk",
        )
    assert reached is False


def test_builder_refuses_rebound_c1_derivation_helper_before_io(
    tmp_path, monkeypatch
):
    reached = False

    def replacement(*_args, **_kwargs):
        nonlocal reached
        reached = True

    monkeypatch.setattr(c1_module, "_derive_source_row", replacement)
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=tmp_path / "capture",
            output_root=tmp_path / "accepted-risk",
            visitor=replacement,
        )
    assert reached is False


def test_publication_syncs_source_rows_stage_then_root(tmp_path):
    tree = _publication_tree(tmp_path)
    identities = {
        physical_module._directory_identity(os.fstat(tree[name])): label
        for name, label in (
            ("source_fd", "source"),
            ("rows_fd", "rows"),
            ("stage_fd", "stage"),
            ("root_fd", "root"),
        )
    }
    calls = []

    def fsync(descriptor):
        calls.append(
            identities[physical_module._directory_identity(os.fstat(descriptor))]
        )
        os.fsync(descriptor)

    try:
        physical_module._publish_stage_at(
            **tree, final_name="final", fsync=fsync
        )
        assert calls == ["source", "rows", "stage", "root"]
        assert set(os.listdir(tree["root_fd"])) == {"final"}
        physical_module._require_pinned_child_identity(
            tree["root_fd"],
            "final",
            tree["stage_fd"],
            "published accepted-risk archive",
        )
    finally:
        _close_publication_tree(tree)


def test_publication_root_sync_failure_rolls_back_and_syncs_root(tmp_path):
    tree = _publication_tree(tmp_path)
    identities = {
        physical_module._directory_identity(os.fstat(tree[name])): label
        for name, label in (
            ("source_fd", "source"),
            ("rows_fd", "rows"),
            ("stage_fd", "stage"),
            ("root_fd", "root"),
        )
    }
    calls = []
    root_attempts = 0

    def fsync(descriptor):
        nonlocal root_attempts
        label = identities[
            physical_module._directory_identity(os.fstat(descriptor))
        ]
        calls.append(label)
        if label == "root":
            root_attempts += 1
            if root_attempts == 1:
                raise OSError("injected initial root sync failure")
        os.fsync(descriptor)

    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "accepted-risk archive publication could not be synchronized"
            ),
        ):
            physical_module._publish_stage_at(
                **tree, final_name="final", fsync=fsync
            )
        assert calls == ["source", "rows", "stage", "root", "root"]
        assert set(os.listdir(tree["root_fd"])) == {tree["stage_name"]}
        physical_module._require_pinned_child_identity(
            tree["root_fd"],
            tree["stage_name"],
            tree["stage_fd"],
            "accepted-risk staging directory",
        )
    finally:
        _close_publication_tree(tree)


def test_builder_preserves_hidden_stage_when_rollback_sync_is_ambiguous(
    tmp_path, monkeypatch
):
    capture, _session = _spooled_capture(tmp_path)
    original = physical_module._publish_stage_at

    def fail_root_sync(**kwargs):
        def fsync(descriptor):
            if descriptor == kwargs["root_fd"]:
                raise OSError("injected persistent root sync failure")
            os.fsync(descriptor)

        return original(**kwargs, fsync=fsync)

    monkeypatch.setattr(physical_module, "_publish_stage_at", fail_root_sync)
    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "accepted-risk archive publication rollback is ambiguous; "
            "hidden staging preserved"
        ),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=output_root,
        )

    residue = tuple(output_root.iterdir())
    assert len(residue) == 1
    assert residue[0].name.startswith(".arv2-c1-")
    assert (residue[0] / "manifest.json").is_file()


def test_cleanup_refuses_a_substituted_stage_entry_without_touching_it(tmp_path):
    tree = _publication_tree(tmp_path)
    replacement_fd = None
    moved_name = f"{tree['stage_name']}-held"
    try:
        os.rename(
            tree["stage_name"],
            moved_name,
            src_dir_fd=tree["root_fd"],
            dst_dir_fd=tree["root_fd"],
        )
        os.mkdir(tree["stage_name"], 0o700, dir_fd=tree["root_fd"])
        replacement_fd = os.open(
            tree["stage_name"],
            physical_module._DIRECTORY_OPEN_FLAGS,
            dir_fd=tree["root_fd"],
        )
        sentinel = os.open(
            "sentinel",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=replacement_fd,
        )
        os.write(sentinel, b"do not remove")
        os.close(sentinel)

        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk staging directory identity changed"),
        ):
            physical_module._cleanup_stage_at(**tree)
        assert os.listdir(replacement_fd) == ["sentinel"]
        assert moved_name in os.listdir(tree["root_fd"])
    finally:
        if replacement_fd is not None:
            os.close(replacement_fd)
        _close_publication_tree(tree)


def test_writer_failure_preserves_a_substituted_named_leaf(tmp_path):
    parent = tmp_path / "writer"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, physical_module._DIRECTORY_OPEN_FLAGS)

    def chunks():
        yield b"original"
        os.rename(
            "leaf", "held", src_dir_fd=parent_fd, dst_dir_fd=parent_fd
        )
        replacement = os.open(
            "leaf",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(replacement, 0o600)
            os.write(replacement, b"substitute")
        finally:
            os.close(replacement)
        raise RuntimeError("injected writer failure")

    try:
        with pytest.raises(RuntimeError, match=_exact("injected writer failure")):
            physical_module._write_private_at(
                parent_fd, "leaf", chunks(), maximum_bytes=100
            )
        assert (parent / "leaf").read_bytes() == b"substitute"
        assert (parent / "held").read_bytes() == b"original"
    finally:
        os.close(parent_fd)


def test_bulk_cleanup_rechecks_leaf_identity_immediately_before_unlink(
    tmp_path, monkeypatch
):
    parent = tmp_path / "bulk-cleanup"
    parent.mkdir(mode=0o700)
    leaf = parent / "leaf"
    leaf.write_bytes(b"original")
    leaf.chmod(0o600)
    parent_fd = os.open(parent, physical_module._DIRECTORY_OPEN_FLAGS)
    original_stat = os.stat
    matching_calls = 0

    def swap_after_first_stat(path, *args, **kwargs):
        nonlocal matching_calls
        metadata = original_stat(path, *args, **kwargs)
        if (
            path == "leaf"
            and kwargs.get("dir_fd") == parent_fd
            and kwargs.get("follow_symlinks") is False
        ):
            matching_calls += 1
            if matching_calls == 1:
                os.rename(
                    "leaf",
                    "held",
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                replacement = os.open(
                    "leaf",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    os.fchmod(replacement, 0o600)
                    os.write(replacement, b"substitute")
                finally:
                    os.close(replacement)
        return metadata

    try:
        with monkeypatch.context() as patch:
            patch.setattr(physical_module.os, "stat", swap_after_first_stat)
            with pytest.raises(
                PhysicalAcceptedRiskArchiveError,
                match=_exact("test cleanup is ambiguous"),
            ):
                physical_module._unlink_private_files_at(parent_fd, "test")
        assert matching_calls >= 1
        assert (parent / "leaf").read_bytes() == b"substitute"
        assert (parent / "held").read_bytes() == b"original"
    finally:
        os.close(parent_fd)


def test_publication_refuses_a_swapped_output_root(tmp_path):
    tree = _publication_tree(tmp_path)
    moved_name = f"{tree['root_name']}-held"
    replacement_fd = None
    try:
        os.rename(
            tree["root_name"],
            moved_name,
            src_dir_fd=tree["repository_fd"],
            dst_dir_fd=tree["repository_fd"],
        )
        os.mkdir(tree["root_name"], 0o700, dir_fd=tree["repository_fd"])
        replacement_fd = os.open(
            tree["root_name"],
            physical_module._DIRECTORY_OPEN_FLAGS,
            dir_fd=tree["repository_fd"],
        )
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk archive root identity changed"),
        ):
            physical_module._publish_stage_at(**tree, final_name="final")
        assert os.listdir(replacement_fd) == []
        assert tree["stage_name"] in os.listdir(tree["root_fd"])
    finally:
        if replacement_fd is not None:
            os.close(replacement_fd)
        _close_publication_tree(tree)


def test_streaming_visitor_refuses_a_page_after_terminal_before_summary(
    tmp_path,
):
    capture, _session = _spooled_capture(tmp_path)
    pages, summary = _visitor_pages(capture)
    first = dataclasses.replace(
        pages[0], next_cursor_sha256=None, terminal_page=True
    )
    source = pages[1]
    following = dataclasses.replace(
        source,
        source_role=first.source_role,
        endpoint_identifier=first.endpoint_identifier,
        redacted_query_bytes=first.redacted_query_bytes,
        redacted_query_sha256=first.redacted_query_sha256,
        page_number=2,
        request_cursor_sha256=None,
    )

    def visitor(*, artifact_path, expected_transport, visit_page):
        del artifact_path, expected_transport
        visit_page(first)
        visit_page(following)
        return dataclasses.replace(
            summary,
            total_page_count=2,
            total_row_count=first.row_count + following.row_count,
            role_row_counts=tuple(
                (
                    role,
                    sum(
                        page.row_count
                        for page in (first, following)
                        if page.source_role is role
                    ),
                )
                for role in ROLE_ORDER
            ),
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("capture visitor emitted a page after terminal"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_streaming_visitor_refuses_a_repeated_cursor_before_summary(tmp_path):
    capture, _session = _spooled_capture(tmp_path)
    pages, summary = _visitor_pages(capture)
    base = pages[0]
    cursors = ("a" * 64, "b" * 64)
    forged = (
        dataclasses.replace(
            pages[0], next_cursor_sha256=cursors[0], terminal_page=False
        ),
        dataclasses.replace(
            pages[1],
            source_role=base.source_role,
            endpoint_identifier=base.endpoint_identifier,
            redacted_query_bytes=base.redacted_query_bytes,
            redacted_query_sha256=base.redacted_query_sha256,
            page_number=2,
            request_cursor_sha256=cursors[0],
            next_cursor_sha256=cursors[1],
            terminal_page=False,
        ),
        dataclasses.replace(
            pages[2],
            source_role=base.source_role,
            endpoint_identifier=base.endpoint_identifier,
            redacted_query_bytes=base.redacted_query_bytes,
            redacted_query_sha256=base.redacted_query_sha256,
            page_number=3,
            request_cursor_sha256=cursors[1],
            next_cursor_sha256=cursors[0],
            terminal_page=False,
        ),
    )

    def visitor(*, artifact_path, expected_transport, visit_page):
        del artifact_path, expected_transport
        for page in forged:
            visit_page(page)
        return dataclasses.replace(
            summary,
            total_page_count=len(forged),
            total_row_count=sum(page.row_count for page in forged),
            role_row_counts=tuple(
                (
                    role,
                    sum(
                        page.row_count
                        for page in forged
                        if page.source_role is role
                    ),
                )
                for role in ROLE_ORDER
            ),
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("capture visitor cursor chain repeats or cycles"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_streaming_visitor_refuses_a_replayed_response_before_rows(tmp_path):
    capture, _session = _spooled_capture(tmp_path)
    pages, summary = _visitor_pages(capture)
    cursor = "a" * 64
    first = dataclasses.replace(
        pages[0], next_cursor_sha256=cursor, terminal_page=False
    )
    replay = dataclasses.replace(
        pages[0],
        page_number=2,
        request_cursor_sha256=cursor,
        next_cursor_sha256=None,
        terminal_page=True,
    )

    def visitor(*, artifact_path, expected_transport, visit_page):
        del artifact_path, expected_transport
        visit_page(first)
        visit_page(replay)
        return dataclasses.replace(
            summary,
            total_page_count=2,
            total_row_count=first.row_count + replay.row_count,
            role_row_counts=tuple(
                (
                    role,
                    sum(
                        page.row_count
                        for page in (first, replay)
                        if page.source_role is role
                    ),
                )
                for role in ROLE_ORDER
            ),
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("capture visitor repeats a raw response page"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=tmp_path / "accepted-risk",
            visitor=visitor,
        )


def test_archive_preflight_independently_refuses_page_after_terminal(tmp_path):
    _capture, archive = _build(tmp_path)
    first, second, *remaining = archive.shards
    assert first.source_role is second.source_role
    object.__setattr__(
        archive,
        "shards",
        (
            dataclasses.replace(
                first, next_cursor_sha256=None, terminal_page=True
            ),
            dataclasses.replace(second, request_cursor_sha256=None),
            *remaining,
        ),
    )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk shard follows a terminal page"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_archive_preflight_independently_refuses_cursor_cycle(tmp_path):
    _capture, archive = _build(tmp_path)
    first, second, *remaining = archive.shards
    assert first.next_cursor_sha256 is not None
    object.__setattr__(
        archive,
        "shards",
        (
            first,
            dataclasses.replace(
                second,
                next_cursor_sha256=first.next_cursor_sha256,
                terminal_page=False,
            ),
            *remaining,
        ),
    )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk shard cursor chain repeats or cycles"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_archive_preflight_independently_refuses_response_replay(tmp_path):
    _capture, archive = _build(tmp_path)
    first, second, *remaining = archive.shards
    object.__setattr__(
        archive,
        "shards",
        (
            first,
            dataclasses.replace(
                second, raw_response_sha256=first.raw_response_sha256
            ),
            *remaining,
        ),
    )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk shard pagination replays a response"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_builder_refuses_rebound_rating_action_whitelist_before_io(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        pair_builder_module,
        "_KNOWN_RATING_ACTIONS",
        frozenset(tuple(pair_builder_module._KNOWN_RATING_ACTIONS)),
    )
    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=tmp_path / "capture",
            output_root=output_root,
        )
    assert not output_root.exists()


def test_builder_refuses_rebound_missing_rating_action_classifier_before_io(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        physical_module,
        "_rating_action_is_missing",
        lambda _value: True,
    )
    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=tmp_path / "capture",
            output_root=output_root,
        )
    assert not output_root.exists()


def test_builder_invokes_pinned_c1_static_contract_before_io(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(c1_module, "_GUIDANCE_LAST_UPDATED_RE", re.compile("x"))
    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=tmp_path / "capture",
            output_root=output_root,
        )
    assert not output_root.exists()


def test_mid_visitor_dependency_rebind_refuses_before_publication(
    tmp_path, monkeypatch
):
    capture, _session = _spooled_capture(tmp_path)
    original = capture_module._visit_authenticated_massive_capture_pages_for_bridge

    def visitor(*, artifact_path, expected_transport, visit_page):
        summary = original(
            artifact_path,
            expected_transport=expected_transport,
            visit_page=visit_page,
        )
        monkeypatch.setattr(
            pair_builder_module,
            "_KNOWN_RATING_ACTIONS",
            frozenset(tuple(pair_builder_module._KNOWN_RATING_ACTIONS)),
        )
        return summary

    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("physical accepted-risk dependency binding changed"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=output_root,
            visitor=visitor,
        )
    assert list(output_root.iterdir()) == []


def test_post_publication_authentication_failure_rolls_back_cleanly(
    tmp_path, monkeypatch
):
    capture, _session = _spooled_capture(tmp_path)

    def refuse(_value):
        raise PhysicalAcceptedRiskArchiveError(
            "injected post-publication authentication failure"
        )

    monkeypatch.setattr(
        physical_module, "require_physical_accepted_risk_archive", refuse
    )
    output_root = tmp_path / "accepted-risk"
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("injected post-publication authentication failure"),
    ):
        _build_physical_accepted_risk_archive_for_test(
            source_artifact_path=capture.artifact_path,
            output_root=output_root,
        )
    assert list(output_root.iterdir()) == []


def test_iterator_does_not_mask_its_own_integrity_error_as_zip_mismatch(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original_require = physical_module.require_physical_accepted_risk_archive
    original_fragments = physical_module._iter_verified_jsonl_fragments_at

    monkeypatch.setattr(
        physical_module,
        "require_physical_accepted_risk_archive",
        lambda value: value,
    )

    def wrong_semantic(*args, **kwargs):
        fragments = original_fragments(*args, **kwargs)
        first = next(fragments)
        yield first[:-1] + (b"0" if first[-1:] != b"0" else b"1")
        yield from fragments

    monkeypatch.setattr(
        physical_module, "_iter_verified_jsonl_fragments_at", wrong_semantic
    )
    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact("accepted-risk semantic row changed"),
        ):
            next(iter_physical_accepted_risk_rows(archive))
    finally:
        monkeypatch.setattr(
            physical_module,
            "require_physical_accepted_risk_archive",
            original_require,
        )


def test_require_refuses_byte_equal_leaf_replacement_after_hash_callback(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original = physical_module._hash_private_regular_at
    replaced = False

    def replace_after_hash(*args, **kwargs):
        nonlocal replaced
        result = original(*args, **kwargs)
        if not replaced:
            replaced = True
            shard = (
                archive.archive_path
                / archive.shards[0].source_relative_path
            )
            payload = shard.read_bytes()
            replacement = shard.with_name(f".{shard.name}.replacement")
            replacement.write_bytes(payload)
            replacement.chmod(0o600)
            os.replace(replacement, shard)
        return result

    monkeypatch.setattr(
        physical_module, "_hash_private_regular_at", replace_after_hash
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive named leaf identity changed"),
    ):
        require_physical_accepted_risk_archive(archive)
    assert replaced is True


def test_require_refuses_source_directory_replacement_after_pair_callback(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original = physical_module._pair_binding_from_archive_fds
    held = tmp_path / "held-source"

    def replace_after_pair(*args, **kwargs):
        result = original(*args, **kwargs)
        source = archive.archive_path / physical_module.SOURCE_DIRECTORY
        source.rename(held)
        source.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", replace_after_pair
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk source directory identity changed"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_require_refuses_archive_path_replacement_after_pair_callback(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    original = physical_module._pair_binding_from_archive_fds
    held = archive.archive_path.with_name(f"{archive.archive_id}-held")

    def replace_after_pair(*args, **kwargs):
        result = original(*args, **kwargs)
        archive.archive_path.rename(held)
        archive.archive_path.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(
        physical_module, "_pair_binding_from_archive_fds", replace_after_pair
    )
    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive path identity changed"),
    ):
        require_physical_accepted_risk_archive(archive)


def test_iterator_refuses_leaf_replacement_between_yields(tmp_path):
    _capture, archive = _build(tmp_path)
    rows = iter_physical_accepted_risk_rows(archive)
    first = next(rows)
    assert first is not None
    shard = archive.archive_path / archive.shards[0].semantic_relative_path
    payload = shard.read_bytes()
    replacement = shard.with_name(f".{shard.name}.replacement")
    replacement.write_bytes(payload)
    replacement.chmod(0o600)
    os.replace(replacement, shard)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact("accepted-risk archive named leaf identity changed"),
    ):
        next(rows)


def test_authenticated_semantic_fold_reconstructs_every_exact_row(tmp_path):
    _capture, archive = _build(tmp_path)
    expected = tuple(iter_physical_accepted_risk_rows(archive))
    observed = []

    def visit(item):
        assert type(item) is physical_module._AuthenticatedAcceptedRiskSemanticRow
        assert type(item.row) is c1_module.AcceptedRiskSourceRow
        assert item.canonical_record_bytes == canonical_json_bytes(
            item.row.to_record()
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            item.canonical_record_bytes = b"changed\n"
        observed.append(item)

    result = physical_module._fold_authenticated_physical_accepted_risk_rows(
        archive, visit
    )

    assert result is None
    assert [item.row.to_record() for item in observed] == [
        row.to_record() for row in expected
    ]
    assert len(observed) == archive.source_row_count


def test_authenticated_semantic_fold_refuses_non_none_visitor_result(tmp_path):
    _capture, archive = _build(tmp_path)

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "authenticated semantic fold visitor must return None"
        ),
    ):
        physical_module._fold_authenticated_physical_accepted_risk_rows(
            archive, lambda _item: False
        )


def test_authenticated_semantic_fold_seals_row_methods_between_callbacks(
    tmp_path, monkeypatch
):
    _capture, archive = _build(tmp_path)
    callbacks = 0

    def visit(_item):
        nonlocal callbacks
        callbacks += 1
        monkeypatch.setattr(
            c1_module.AcceptedRiskSourceRow,
            "to_record",
            lambda _row: {},
        )

    with pytest.raises(
        PhysicalAcceptedRiskArchiveError,
        match=_exact(
            "authenticated semantic fold dependency binding changed"
        ),
    ):
        physical_module._fold_authenticated_physical_accepted_risk_rows(
            archive, visit
        )
    assert callbacks == 1


def test_authenticated_semantic_fold_terminally_refuses_archive_mutation(
    tmp_path,
):
    _capture, archive = _build(tmp_path)
    original = archive.result_access
    callbacks = 0

    def visit(_item):
        nonlocal callbacks
        callbacks += 1
        if callbacks == archive.source_row_count:
            object.__setattr__(archive, "result_access", True)

    try:
        with pytest.raises(
            PhysicalAcceptedRiskArchiveError,
            match=_exact(
                "accepted-risk archive capability or risk classification changed"
            ),
        ):
            physical_module._fold_authenticated_physical_accepted_risk_rows(
                archive, visit
            )
    finally:
        object.__setattr__(archive, "result_access", original)
    assert callbacks == archive.source_row_count


def test_authenticated_semantic_fold_never_rederives_provider_semantics():
    source = inspect.getsource(
        physical_module._make_authenticated_physical_accepted_risk_fold
    )
    assert "_PINNED_DERIVE_SOURCE_ROW" not in source
    assert "_derive_source_row" not in source
