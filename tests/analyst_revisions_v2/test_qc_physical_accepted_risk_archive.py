"""Focused offline tests for the disk-backed C1 accepted-risk archive."""
from __future__ import annotations

import dataclasses
import hashlib
import os
import re
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import accepted_risk_input_pair as c1_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    MAX_CAPTURE_PAGE_BYTES,
    MassiveSourceRole,
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
    _row,
    _spooled_capture,
)


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


def _build(tmp_path: Path):
    capture, _session = _spooled_capture(tmp_path)
    archive = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    return capture, archive


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
        match=_exact("capture visitor physical identity did not reconstruct"),
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
            "accepted-risk semantic shard row count, byte count, hash, or identity changed"
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
