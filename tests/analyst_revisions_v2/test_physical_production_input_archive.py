from __future__ import annotations

import dataclasses
import os
import sqlite3
import stat
import tracemalloc
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.production_evidence_acquisition import (
    render_production_evidence_package_bytes,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    SignalArm,
    build_production_evidence_authority,
    build_production_input_batch,
    build_production_input_comparison_report,
)
from research.analyst_revisions_v2_qc import physical_production_input_archive as disk
from research.analyst_revisions_v2_qc.accepted_risk_pair_bridge import (
    build_formal_accepted_risk_pair_binding,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    require_accepted_risk_pair_binding,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    _build_physical_accepted_risk_archive_for_test,
)
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    PhysicalProductionInputArchive,
    PhysicalProductionInputArchiveError,
    PhysicalProductionInputCapacityError,
    build_test_fixture_physical_production_input_archive,
    iter_physical_normalized_evidence_rows,
    iter_physical_production_normalized_rows,
    iter_physical_production_row_evidence,
    physical_production_batch,
    require_physical_production_input_archive,
    require_reviewable_physical_production_archive,
)
from tests.analyst_revisions_v2.test_production_input_pipeline import _authority
from tests.analyst_revisions_v2.test_production_input_pipeline import _pair
from tests.analyst_revisions_v2.test_production_input_pipeline import _rating_row
from tests.analyst_revisions_v2.test_production_input_pipeline import _row_evidence
from tests.analyst_revisions_v2.test_production_input_pipeline import _sources
from tests.analyst_revisions_v2.test_qc_physical_accepted_risk_archive import (
    _build as _physical_c1,
)
from tests.analyst_revisions_v2.test_qc_accepted_risk_pair_bridge import (
    _parents_with_one_admitted_revision,
)
from scripts.build_arv2_massive_input_pair import (
    _build_massive_accepted_risk_input_pair_for_test,
)


@pytest.fixture()
def oracle(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    authority = _authority()
    archive = build_test_fixture_physical_production_input_archive(
        authority,
        output_root=tmp_path,
    )
    return authority, archive


def test_fixture_archive_is_byte_exact_to_every_legacy_c2_hash(oracle):
    authority, archive = oracle
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    comparison = build_production_input_comparison_report(authority)

    assert require_physical_production_input_archive(archive) is archive
    assert archive.evidence_authority_id == authority.authority_id
    assert archive.evidence_authority_sha256 == authority.authority_sha256
    assert archive.comparison_report_sha256 == comparison.report_sha256
    assert [item.batch_id for item in archive.batches] == [
        current.batch_id,
        censored.batch_id,
    ]
    assert [item.batch_sha256 for item in archive.batches] == [
        current.batch_sha256,
        censored.batch_sha256,
    ]
    package = archive.archive_path / archive.evidence_package.relative_path
    report = archive.archive_path / archive.comparison_report.relative_path
    assert package.read_bytes() == render_production_evidence_package_bytes(authority)
    assert report.read_bytes() == canonical_json_bytes(comparison.to_record())


def test_decimal_scale_variants_preserve_legacy_numeric_topology_and_exact_hashes(
    tmp_path,
):
    os.chmod(tmp_path, 0o700)
    pair = _pair(
        ratings=[
            _rating_row("rating-scale-one"),
            _rating_row("rating-scale-two"),
        ]
    )
    first_source, second_source = pair.rows[:2]
    first = _row_evidence(
        first_source,
        security_id="security-scale",
        historical_ticker="SCALE",
    )
    second_base = _row_evidence(
        second_source,
        security_id="security-scale",
        historical_ticker="SCALE",
    )
    assert first.security is not None
    assert first.firm is not None
    assert first.common_event is not None
    assert first.q_data is not None
    second = dataclasses.replace(
        second_base,
        security=dataclasses.replace(
            first.security,
            provider_event_id=second_source.provider_event_id,
        ),
        firm=dataclasses.replace(
            first.firm,
            provider_event_id=second_source.provider_event_id,
        ),
        common_event=dataclasses.replace(
            first.common_event,
            provider_event_id=second_source.provider_event_id,
            common_event_id="common-rating-scale-two",
        ),
        sector=first.sector,
        control=first.control,
        q_data=dataclasses.replace(first.q_data, q_data=Decimal("0.8750")),
    )
    authority = build_production_evidence_authority(
        pair,
        source_bindings=_sources(),
        row_evidence=(first, second),
    )
    archive = build_test_fixture_physical_production_input_archive(
        authority,
        output_root=tmp_path,
    )

    assert (
        archive.archive_path / archive.evidence_package.relative_path
    ).read_bytes() == render_production_evidence_package_bytes(authority)
    assert (
        archive.archive_path / archive.comparison_report.relative_path
    ).read_bytes() == canonical_json_bytes(
        build_production_input_comparison_report(authority).to_record()
    )
    for arm in SignalArm:
        legacy = build_production_input_batch(authority, signal_arm=arm)
        physical = physical_production_batch(archive, arm)
        assert physical.batch_id == legacy.batch_id
        assert physical.batch_sha256 == legacy.batch_sha256
    q_values = [
        row.q_data
        for row in iter_physical_production_normalized_rows(
            archive, SignalArm.CURRENT_VINTAGE
        )
    ]
    assert q_values == [Decimal("0.875"), Decimal("0.8750")]


def test_physical_c1_fixture_seam_consumes_rows_without_legacy_pair(tmp_path):
    os.chmod(tmp_path, 0o700)
    capture, c1 = _physical_c1(tmp_path)
    output = tmp_path / "production-c2"
    output.mkdir(mode=0o700)
    sources = _sources()

    archive = disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
        c1,
        source_bindings=sources,
        row_evidence=iter(()),
        output_root=output,
    )

    legacy = _build_massive_accepted_risk_input_pair_for_test(capture.artifact_path)
    authority = build_production_evidence_authority(
        legacy.pair,
        source_bindings=sources,
        row_evidence=(),
    )
    assert archive.fixture_only is True
    assert archive.accepted_risk_archive is c1
    assert archive.evidence_authority_sha256 == authority.authority_sha256
    for arm in SignalArm:
        legacy_batch = build_production_input_batch(authority, signal_arm=arm)
        assert physical_production_batch(archive, arm).batch_sha256 == (
            legacy_batch.batch_sha256
        )
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="legacy fixture archive cannot be submitted for production review",
    ):
        require_reviewable_physical_production_archive(archive)


def test_production_entrypoint_refuses_test_transport(tmp_path):
    os.chmod(tmp_path, 0o700)
    _capture, c1 = _physical_c1(tmp_path)
    output = tmp_path / "production-c2"
    output.mkdir(mode=0o700)
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="production physical C2 requires production C1 transport",
    ):
        disk.build_physical_production_input_archive(
            c1,
            source_bindings=_sources(),
            row_evidence=iter(()),
            output_root=output,
        )


@pytest.mark.parametrize(
    "dependency_name",
    (
        "c1_archive_type",
        "c1_require",
        "c1_iterator",
        "c1_module",
        "production_transport_identity",
        "artifacts_root_identity",
    ),
)
def test_production_builder_refuses_rebound_c1_contract_before_io(
    tmp_path, monkeypatch, dependency_name
):
    output = tmp_path / "must-not-be-created"
    reached_builder = False

    def forbidden_builder(*_args, **_kwargs):
        nonlocal reached_builder
        reached_builder = True
        raise AssertionError("production builder was reached")

    if dependency_name == "c1_archive_type":
        monkeypatch.setattr(
            disk._c1_disk,
            "PhysicalAcceptedRiskArchive",
            type("ReplacementPhysicalAcceptedRiskArchive", (), {}),
        )
    elif dependency_name == "c1_require":
        monkeypatch.setattr(
            disk._c1_disk,
            "require_physical_accepted_risk_archive",
            lambda _value: _value,
        )
    elif dependency_name == "c1_iterator":
        monkeypatch.setattr(
            disk._c1_disk,
            "iter_physical_accepted_risk_rows",
            lambda _value: iter(()),
        )
    elif dependency_name == "c1_module":
        monkeypatch.setattr(
            disk._c1_disk,
            "_massive",
            SimpleNamespace(),
        )
    elif dependency_name == "production_transport_identity":
        original = disk._c1_disk._massive.PRODUCTION_TRANSPORT
        equal_replacement = bytearray(original, "ascii").decode("ascii")
        assert equal_replacement == original
        assert equal_replacement is not original
        monkeypatch.setattr(
            disk._c1_disk._massive,
            "PRODUCTION_TRANSPORT",
            equal_replacement,
        )
    else:
        original = disk._c1_disk._massive.REPOSITORY_ARTIFACTS_ROOT
        equal_replacement = Path(str(original))
        assert equal_replacement == original
        assert equal_replacement is not original
        monkeypatch.setattr(
            disk._c1_disk._massive,
            "REPOSITORY_ARTIFACTS_ROOT",
            equal_replacement,
        )
    monkeypatch.setattr(disk, "_build_from_physical_c1", forbidden_builder)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^physical C2 static contract changed$",
    ):
        disk.build_physical_production_input_archive(
            object(),
            source_bindings=(),
            row_evidence=(),
            output_root=output,
        )

    assert reached_builder is False
    assert not output.exists()


def test_formal_binder_refuses_rebound_c1_contract_before_io(monkeypatch):
    reached_binder = False

    def replacement_require(_value):
        raise AssertionError("rebound C1 require was called")

    def forbidden_binder(*_args, **_kwargs):
        nonlocal reached_binder
        reached_binder = True
        raise AssertionError("formal binder was reached")

    monkeypatch.setattr(
        disk._c1_disk,
        "require_physical_accepted_risk_archive",
        replacement_require,
    )
    monkeypatch.setattr(
        disk,
        "_build_physical_formal_accepted_risk_pair_binding",
        forbidden_binder,
    )

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^physical C2 static contract changed$",
    ):
        disk.build_physical_formal_accepted_risk_pair_binding(
            object(), object()
        )

    assert reached_binder is False


def test_publication_syncs_leaves_and_stage_before_rename_then_root(
    tmp_path, monkeypatch
):
    output = tmp_path / "durable-c2"
    output.mkdir(mode=0o700)
    output_identity = (
        os.stat(output, follow_symlinks=False).st_dev,
        os.stat(output, follow_symlinks=False).st_ino,
    )
    events: list[object] = []
    real_fsync = os.fsync
    real_rename = disk._rename_at

    def recording_fsync(descriptor):
        metadata = os.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        if stat.S_ISREG(metadata.st_mode):
            events.append("leaf-sync")
        elif identity == output_identity:
            events.append("root-sync")
        else:
            events.append("stage-sync")
        return real_fsync(descriptor)

    def recording_rename(parent_fd, source, destination):
        events.append(("rename", source, destination))
        return real_rename(parent_fd, source, destination)

    monkeypatch.setattr(disk.os, "fsync", recording_fsync)
    monkeypatch.setattr(disk, "_rename_at", recording_rename)

    archive = build_test_fixture_physical_production_input_archive(
        _authority(), output_root=output
    )

    rename_index = next(
        index
        for index, event in enumerate(events)
        if type(event) is tuple
        and len(event) == 3
        and event[0] == "rename"
        and event[2] == archive.archive_id
    )
    assert "leaf-sync" in events[:rename_index]
    assert "stage-sync" in events[:rename_index]
    assert "root-sync" in events[rename_index + 1 :]
    assert require_physical_production_input_archive(archive) is archive


def test_exact_evidence_generator_is_drained_through_terminal_code(tmp_path):
    os.chmod(tmp_path, 0o700)
    authority = _authority()
    exhausted = False

    def evidence_rows():
        nonlocal exhausted
        yield from authority.row_evidence
        exhausted = True

    archive = disk._build_physical_archive(
        accepted_risk_archive=None,
        parent_archive_id=authority.pair_id,
        parent_archive_sha256=authority.pair_sha256,
        fixture_only=True,
        pair_id=authority.pair_id,
        pair_sha256=authority.pair_sha256,
        expected_source_row_count=len(authority.pair.rows),
        expected_current_included_count=sum(
            row.current_view.included for row in authority.pair.rows
        ),
        expected_censored_included_count=sum(
            row.censored_view.included for row in authority.pair.rows
        ),
        source_rows=lambda: iter(authority.pair.rows),
        source_bindings=authority.source_bindings,
        row_evidence=evidence_rows(),
        archive_root=tmp_path,
    )

    assert exhausted is True
    assert archive.evidence_row_count == len(authority.row_evidence)


def test_surplus_evidence_member_is_consumed_and_refused(tmp_path):
    os.chmod(tmp_path, 0o700)
    authority = _authority()

    def evidence_rows():
        yield from authority.row_evidence
        yield authority.row_evidence[-1]

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^row evidence is not unique canonical source order$",
    ):
        disk._build_physical_archive(
            accepted_risk_archive=None,
            parent_archive_id=authority.pair_id,
            parent_archive_sha256=authority.pair_sha256,
            fixture_only=True,
            pair_id=authority.pair_id,
            pair_sha256=authority.pair_sha256,
            expected_source_row_count=len(authority.pair.rows),
            expected_current_included_count=None,
            expected_censored_included_count=None,
            source_rows=lambda: iter(authority.pair.rows),
            source_bindings=authority.source_bindings,
            row_evidence=evidence_rows(),
            archive_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("input_attribute", "descendant"),
    (
        ("source_artifact_path", False),
        ("source_artifact_path", True),
        ("archive_path", False),
        ("archive_path", True),
    ),
)
def test_physical_c2_output_cannot_equal_or_descend_from_physical_c1_input(
    tmp_path, monkeypatch, input_attribute, descendant
):
    os.chmod(tmp_path, 0o700)
    _capture, c1 = _physical_c1(tmp_path)
    immutable_input = getattr(c1, input_attribute)
    output = (
        immutable_input / "forbidden-c2-output"
        if descendant
        else immutable_input
    )
    opened = False

    def unexpected_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("overlapping output reached filesystem open")

    monkeypatch.setattr(disk, "_open_directory_path", unexpected_open)
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^physical C2 output overlaps an immutable C1 input$",
    ):
        disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
            c1,
            source_bindings=_sources(),
            row_evidence=iter(()),
            output_root=output,
        )

    assert opened is False


def test_lineage_scan_uses_primary_order_without_temporary_sort(tmp_path):
    output = tmp_path / "lineage-plan-c2"
    output.mkdir(mode=0o700)
    root_path, root_fd = disk._open_directory_path(
        output, name="physical C2 archive root"
    )
    stage_name, stage_fd = disk._create_private_stage_at(root_fd)
    connection = None
    try:
        connection = disk._open_spool(
            output / stage_name / "spool.sqlite3",
            root_path=root_path,
            root_fd=root_fd,
            stage_name=stage_name,
            stage_fd=stage_fd,
            created_files={},
        )
        plan = connection.execute(
            "EXPLAIN QUERY PLAN " + disk._LINEAGE_SCAN_SQL
        ).fetchall()
        assert not any("TEMP B-TREE" in str(row[3]).upper() for row in plan)
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 1
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        maximum_pages = connection.execute(
            "PRAGMA max_page_count"
        ).fetchone()[0]
        assert maximum_pages == disk.MAX_SQLITE_BYTES // page_size
    finally:
        if connection is not None:
            connection.close()
        os.close(stage_fd)
        os.close(root_fd)


def test_lineage_validation_retains_constant_state_across_many_overlaps():
    class StreamingConnection:
        def execute(self, statement):
            assert statement == disk._LINEAGE_SCAN_SQL

            def rows():
                for index in range(100_000):
                    yield (
                        "security historical_ticker lineage",
                        "SAME",
                        f"{index:08d}",
                        "",
                        b'["one-identity"]',
                    )

            return rows()

    tracemalloc.start()
    try:
        disk._validate_lineage(StreamingConnection())
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 1_500_000


def test_lineage_validation_refuses_overlapping_different_identities():
    rows = iter(
        (
            ("provider-firm identity lineage", "firm-1", "2020-01-01", "", b"a"),
            (
                "provider-firm identity lineage",
                "firm-1",
                "2020-01-02",
                "2020-01-03",
                b"b",
            ),
        )
    )
    connection = SimpleNamespace(execute=lambda statement: rows)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^contradictory overlapping provider-firm identity lineage evidence$",
    ):
        disk._validate_lineage(connection)


def test_sqlite_hard_page_ceiling_uses_declared_capacity_error(
    tmp_path, monkeypatch
):
    os.chmod(tmp_path, 0o700)
    probe = sqlite3.connect(":memory:")
    try:
        page_size = int(probe.execute("PRAGMA page_size").fetchone()[0])
    finally:
        probe.close()
    monkeypatch.setattr(disk, "MAX_SQLITE_BYTES", page_size * 5)

    with pytest.raises(
        PhysicalProductionInputCapacityError,
        match=r"^C2 SQLite spool reached its fixed hard page bound$",
    ) as captured:
        build_test_fixture_physical_production_input_archive(
            _authority(), output_root=tmp_path
        )

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert (
        captured.value.__cause__.sqlite_errorcode & 0xFF
    ) == sqlite3.SQLITE_FULL
    assert list(tmp_path.iterdir()) == []


def test_root_sync_failure_rolls_back_durably_before_cleanup(
    tmp_path, monkeypatch
):
    output = tmp_path / "rollback-c2"
    output.mkdir(mode=0o700)
    calls: list[str] = []
    real_fsync_fd = disk._fsync_fd

    def fail_publication_sync(descriptor, name):
        calls.append(name)
        if name == "physical C2 root publication":
            raise PhysicalProductionInputArchiveError(
                "physical C2 root publication directory sync failed"
            )
        return real_fsync_fd(descriptor, name)

    monkeypatch.setattr(disk, "_fsync_fd", fail_publication_sync)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^physical C2 root publication directory sync failed$",
    ):
        build_test_fixture_physical_production_input_archive(
            _authority(), output_root=output
        )

    assert "physical C2 root rollback" in calls
    assert "physical C2 root cleanup" in calls
    assert list(output.iterdir()) == []


def test_rollback_sync_ambiguity_preserves_hidden_staging(
    tmp_path, monkeypatch
):
    output = tmp_path / "ambiguous-c2"
    output.mkdir(mode=0o700)
    real_fsync_fd = disk._fsync_fd

    def fail_root_syncs(descriptor, name):
        if name in {
            "physical C2 root publication",
            "physical C2 root rollback",
        }:
            raise PhysicalProductionInputArchiveError(
                f"{name} directory sync failed"
            )
        return real_fsync_fd(descriptor, name)

    monkeypatch.setattr(disk, "_fsync_fd", fail_root_syncs)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=(
            r"^physical C2 publication state is ambiguous after "
            r"rollback sync failure$"
        ),
    ):
        build_test_fixture_physical_production_input_archive(
            _authority(), output_root=output
        )

    residue = list(output.iterdir())
    assert len(residue) == 1
    assert residue[0].name.startswith(".arv2-c2-")
    assert any(residue[0].iterdir())


def test_build_root_swap_preserves_original_stage_and_replacement(
    tmp_path
):
    os.chmod(tmp_path, 0o700)
    _capture, c1 = _physical_c1(tmp_path)
    output = tmp_path / "root-swap-c2"
    output.mkdir(mode=0o700)
    moved = tmp_path / "root-swap-c2-original"

    def hostile_evidence():
        os.rename(output, moved)
        output.mkdir(mode=0o700)
        (output / "do-not-delete").write_bytes(b"replacement")
        raise RuntimeError("hostile evidence stopped")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="hostile evidence stopped"):
        disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
            c1,
            source_bindings=_sources(),
            row_evidence=hostile_evidence(),
            output_root=output,
        )

    assert (output / "do-not-delete").read_bytes() == b"replacement"
    assert any(item.name.startswith(".arv2-c2-") for item in moved.iterdir())


def test_cleanup_refuses_substituted_staging_directory(tmp_path):
    os.chmod(tmp_path, 0o700)
    _capture, c1 = _physical_c1(tmp_path)
    output = tmp_path / "stage-swap-c2"
    output.mkdir(mode=0o700)
    displaced: Path | None = None
    replacement: Path | None = None

    def hostile_evidence():
        nonlocal displaced, replacement
        stages = [
            item for item in output.iterdir() if item.name.startswith(".arv2-c2-")
        ]
        assert len(stages) == 1
        replacement = stages[0]
        displaced = output / f"{replacement.name}.displaced"
        os.rename(replacement, displaced)
        replacement.mkdir(mode=0o700)
        (replacement / "do-not-delete").write_bytes(b"replacement")
        raise RuntimeError("hostile evidence stopped")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="hostile evidence stopped"):
        disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
            c1,
            source_bindings=_sources(),
            row_evidence=hostile_evidence(),
            output_root=output,
        )

    assert replacement is not None
    assert displaced is not None
    assert (replacement / "do-not-delete").read_bytes() == b"replacement"
    assert any(displaced.iterdir())


def test_cleanup_quarantines_and_preserves_every_leaf_on_substitution(
    tmp_path, monkeypatch
):
    root = tmp_path / "quarantine-cleanup-c2"
    root.mkdir(mode=0o700)
    root_path, root_fd = disk._open_directory_path(
        root, name="physical C2 archive root"
    )
    stage_name, stage_fd = disk._create_private_stage_at(root_fd)
    created_files: dict[str, tuple[int, int]] = {}
    descriptor = os.open(
        "leaf",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=stage_fd,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, b"original")
        metadata = os.fstat(descriptor)
        created_files["leaf"] = (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(descriptor)

    real_rename_at = disk._rename_at
    swapped = False

    def swap_before_quarantine(parent_fd, source, destination):
        nonlocal swapped
        if (
            not swapped
            and source == "leaf"
            and destination.startswith(".arv2-delete-")
            and parent_fd == stage_fd
        ):
            swapped = True
            os.rename(
                "leaf",
                "held-original",
                src_dir_fd=stage_fd,
                dst_dir_fd=stage_fd,
            )
            replacement = os.open(
                "leaf",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=stage_fd,
            )
            try:
                os.fchmod(replacement, 0o600)
                os.write(replacement, b"substitute")
            finally:
                os.close(replacement)
        return real_rename_at(parent_fd, source, destination)

    try:
        monkeypatch.setattr(disk, "_rename_at", swap_before_quarantine)
        assert disk._safe_cleanup_stage_at(
            root_path=root_path,
            root_fd=root_fd,
            stage_name=stage_name,
            stage_fd=stage_fd,
            created_files=created_files,
        ) is False
        assert swapped is True
        stage = root / stage_name
        assert stage.is_dir()
        assert sorted(item.read_bytes() for item in stage.iterdir()) == [
            b"original",
            b"substitute",
        ]
    finally:
        os.close(stage_fd)
        os.close(root_fd)


def test_spool_substitution_before_quarantine_preserves_hidden_stage(
    tmp_path, monkeypatch
):
    output = tmp_path / "spool-swap-c2"
    output.mkdir(mode=0o700)
    real_rename_at = disk._rename_at
    swapped = False

    def swap_spool_before_quarantine(stage_fd, source, destination):
        nonlocal swapped
        if (
            not swapped
            and source == "spool.sqlite3"
            and destination.startswith(".arv2-delete-")
            and type(stage_fd) is int
        ):
            swapped = True
            os.rename(
                source,
                "held-spool.sqlite3",
                src_dir_fd=stage_fd,
                dst_dir_fd=stage_fd,
            )
            replacement = os.open(
                source,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=stage_fd,
            )
            try:
                os.fchmod(replacement, 0o600)
                os.write(replacement, b"substitute spool")
            finally:
                os.close(replacement)
        return real_rename_at(stage_fd, source, destination)

    monkeypatch.setattr(disk, "_rename_at", swap_spool_before_quarantine)
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^physical C2 SQLite spool quarantine is ambiguous$",
    ):
        build_test_fixture_physical_production_input_archive(
            _authority(), output_root=output
        )

    assert swapped is True
    residue = list(output.iterdir())
    assert len(residue) == 1
    assert residue[0].name.startswith(".arv2-c2-")
    assert (residue[0] / "held-spool.sqlite3").exists()
    assert any(
        item.name.startswith(".arv2-delete-")
        and item.read_bytes() == b"substitute spool"
        for item in residue[0].iterdir()
    )


def test_postpublication_authority_failure_rolls_back_and_allows_retry(
    tmp_path, monkeypatch
):
    output = tmp_path / "postpublication-c2"
    output.mkdir(mode=0o700)
    captured: list[object] = []

    def refuse(value):
        captured.append(value)
        raise PhysicalProductionInputArchiveError("forced authority refusal")

    monkeypatch.setattr(
        disk, "require_physical_production_input_archive", refuse
    )
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=r"^forced authority refusal$",
    ):
        build_test_fixture_physical_production_input_archive(
            _authority(), output_root=output
        )

    assert len(captured) == 1
    assert id(captured[0]) not in disk._AUTHORITIES
    assert list(output.iterdir()) == []


def test_verifier_refuses_replaced_archive_path_identity(oracle):
    _authority_value, archive = oracle
    original = archive.archive_path
    displaced = original.parent / f"{original.name}.displaced"
    os.rename(original, displaced)
    original.mkdir(mode=0o700)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=(
            r"^physical C2 archive path no longer names builder authority$"
        ),
    ):
        require_physical_production_input_archive(archive)


def test_verifier_refuses_leaf_swap_during_authenticated_read(
    oracle, monkeypatch
):
    _authority_value, archive = oracle
    target = archive.evidence_rows.relative_path
    target_path = archive.archive_path / target
    replacement_bytes = target_path.read_bytes()
    displaced = archive.archive_path / f"{target}.displaced"
    original_iterator = disk._iter_private_file_at
    swapped = False

    def swapping_iterator(parent_fd, filename, **kwargs):
        nonlocal swapped
        for chunk in original_iterator(parent_fd, filename, **kwargs):
            if filename == target and not swapped:
                swapped = True
                os.rename(target_path, displaced)
                target_path.write_bytes(replacement_bytes)
                os.chmod(target_path, 0o600)
            yield chunk

    monkeypatch.setattr(disk, "_iter_private_file_at", swapping_iterator)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match=rf"^{target} identity changed after traversal$",
    ):
        require_physical_production_input_archive(archive)
    assert swapped is True


@pytest.mark.parametrize("swap_kind", ("leaf", "archive"))
def test_iterator_refuses_named_identity_swap_between_rows(oracle, swap_kind):
    _authority_value, archive = oracle
    batch = physical_production_batch(archive, SignalArm.CURRENT_VINTAGE)
    target = archive.archive_path / batch.normalized_rows.relative_path
    payload = target.read_bytes()
    iterator = iter_physical_production_normalized_rows(
        archive, SignalArm.CURRENT_VINTAGE
    )
    first = next(iterator)
    assert first.signal_arm is SignalArm.CURRENT_VINTAGE

    if swap_kind == "leaf":
        displaced = archive.archive_path / f"{target.name}.displaced"
        os.rename(target, displaced)
        target.write_bytes(payload)
        os.chmod(target, 0o600)
        expected = rf"^{target.name} identity changed after traversal$"
    else:
        original = archive.archive_path
        displaced = original.parent / f"{original.name}.displaced"
        os.rename(original, displaced)
        original.mkdir(mode=0o700)
        expected = r"^physical C2 archive path identity changed$"

    with pytest.raises(PhysicalProductionInputArchiveError, match=expected):
        next(iterator)


def test_physical_formal_pair_binding_is_exact_legacy_oracle(
    tmp_path, monkeypatch
):
    os.chmod(tmp_path, 0o700)
    massive, current, censored = _parents_with_one_admitted_revision(
        tmp_path, monkeypatch
    )
    c1 = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=massive.artifact_path,
        output_root=tmp_path / "accepted-risk-physical",
    )
    output = tmp_path / "production-c2-physical"
    output.mkdir(mode=0o700)
    c2 = disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
        c1,
        source_bindings=current.evidence_authority.source_bindings,
        row_evidence=iter(current.evidence_authority.row_evidence),
        output_root=output,
    )

    physical_binding = (
        disk._build_test_fixture_physical_formal_accepted_risk_pair_binding(
            c1, c2
        )
    )
    legacy_binding = build_formal_accepted_risk_pair_binding(
        bridge=massive,
        current_batch=current,
        censored_batch=censored,
    )

    assert require_accepted_risk_pair_binding(physical_binding) is physical_binding
    assert physical_binding.to_record() == legacy_binding.to_record()
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="fixture physical C2 cannot produce a production formal pair binding",
    ):
        disk.build_physical_formal_accepted_risk_pair_binding(c1, c2)


def test_physical_formal_pair_binding_requires_exact_c1_parent_identity(
    tmp_path, monkeypatch
):
    os.chmod(tmp_path, 0o700)
    massive, current, _censored = _parents_with_one_admitted_revision(
        tmp_path, monkeypatch
    )
    c1 = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=massive.artifact_path,
        output_root=tmp_path / "accepted-risk-one",
    )
    equal_c1 = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=massive.artifact_path,
        output_root=tmp_path / "accepted-risk-two",
    )
    output = tmp_path / "production-c2"
    output.mkdir(mode=0o700)
    c2 = disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
        c1,
        source_bindings=current.evidence_authority.source_bindings,
        row_evidence=iter(current.evidence_authority.row_evidence),
        output_root=output,
    )
    assert equal_c1.archive_sha256 == c1.archive_sha256
    assert equal_c1 is not c1

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="physical C1 and C2 do not share exact parent identity",
    ):
        disk._build_test_fixture_physical_formal_accepted_risk_pair_binding(
            equal_c1, c2
        )


@pytest.mark.parametrize(
    ("source_role", "event_date"),
    (
        (disk.MassiveSourceRole.CORPORATE_GUIDANCE, "2021-01-04"),
        (disk.MassiveSourceRole.ANALYST_RATINGS, "2012-12-31"),
    ),
)
def test_physical_formal_pair_binding_exhaustively_refuses_forbidden_admission(
    tmp_path, monkeypatch, source_role, event_date
):
    os.chmod(tmp_path, 0o700)
    massive, current, _censored = _parents_with_one_admitted_revision(
        tmp_path, monkeypatch
    )
    c1 = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=massive.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    output = tmp_path / "production-c2"
    output.mkdir(mode=0o700)
    c2 = disk._build_test_fixture_physical_production_input_archive_from_physical_c1(
        c1,
        source_bindings=current.evidence_authority.source_bindings,
        row_evidence=iter(current.evidence_authority.row_evidence),
        output_root=output,
    )

    monkeypatch.setattr(
        disk,
        "_iter_normalized_rows",
        lambda _archive, _batch: iter(
            (SimpleNamespace(source_role=source_role, event_date=event_date),)
        ),
    )
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="formal accepted-risk binding refused physical C1/C2 state",
    ):
        disk._build_test_fixture_physical_formal_accepted_risk_pair_binding(
            c1, c2
        )


def test_normalized_iterator_refuses_reordered_authenticated_records(oracle):
    _authority_value, archive = oracle
    batch = physical_production_batch(archive, SignalArm.CURRENT_VINTAGE)
    path = archive.archive_path / batch.normalized_rows.relative_path
    lines = path.read_bytes().splitlines(keepends=True)
    assert len(lines) == 2
    path.write_bytes(b"".join(reversed(lines)))
    payload = path.read_bytes()
    reordered = dataclasses.replace(
        batch.normalized_rows,
        sha256=sha256_bytes(payload),
    )
    reordered_batch = dataclasses.replace(batch, normalized_rows=reordered)

    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="physical normalized row order changed",
    ):
        tuple(disk._iter_normalized_rows(archive, reordered_batch))


def test_streaming_iterators_round_trip_exact_rows_without_retained_tuples(oracle):
    authority, archive = oracle
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )

    evidence = tuple(iter_physical_production_row_evidence(archive))
    assert [item.to_record() for item in evidence] == [
        item.to_record() for item in authority.row_evidence
    ]
    assert [item.to_record() for item in iter_physical_production_normalized_rows(
        archive, SignalArm.CURRENT_VINTAGE
    )] == [item.to_record() for item in current.normalized_rows]
    assert [item.to_record() for item in iter_physical_production_normalized_rows(
        archive, SignalArm.CONSERVATIVE_CENSORED
    )] == [item.to_record() for item in censored.normalized_rows]
    joined = tuple(
        iter_physical_normalized_evidence_rows(
            archive, SignalArm.CURRENT_VINTAGE
        )
    )
    assert [item.normalized_row.source_locator for item in joined] == [
        item.evidence.locator for item in joined
    ]
    assert physical_production_batch(
        archive, SignalArm.CURRENT_VINTAGE
    ).normalized_row_count == len(joined)
    assert archive.accepted_risk_archive is None
    assert archive.full_pair_materialized is False
    assert archive.full_evidence_materialized is False
    assert archive.full_admission_census_materialized is False


def test_normalized_evidence_join_drains_unmatched_evidence_to_terminal(
    oracle, monkeypatch
):
    _authority_value, archive = oracle
    batch = physical_production_batch(
        archive, SignalArm.CONSERVATIVE_CENSORED
    )
    assert batch.normalized_row_count < archive.evidence_row_count
    original_iterator = disk._iter_evidence_rows
    terminal_reached = False

    def tracked_evidence_rows(value):
        nonlocal terminal_reached
        yield from original_iterator(value)
        terminal_reached = True

    monkeypatch.setattr(disk, "_iter_evidence_rows", tracked_evidence_rows)

    joined = tuple(
        iter_physical_normalized_evidence_rows(
            archive, SignalArm.CONSERVATIVE_CENSORED
        )
    )

    assert len(joined) == batch.normalized_row_count
    assert terminal_reached is True


def test_fixture_archive_is_explicitly_refused_at_formal_adapter(oracle):
    _authority_value, archive = oracle
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="legacy fixture archive cannot be submitted for production review",
    ):
        require_reviewable_physical_production_archive(archive)


def test_unregistered_copy_and_container_identity_change_are_refused(oracle):
    _authority_value, archive = oracle
    forged = object.__new__(PhysicalProductionInputArchive)
    for field in dataclasses.fields(archive):
        object.__setattr__(forged, field.name, getattr(archive, field.name))
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="not current builder authority",
    ):
        require_physical_production_input_archive(forged)

    original = archive.batches
    object.__setattr__(archive, "batches", tuple(reversed(original)))
    try:
        with pytest.raises(
            PhysicalProductionInputArchiveError,
            match="batch order changed",
        ):
            require_physical_production_input_archive(archive)
    finally:
        object.__setattr__(archive, "batches", original)
    assert require_physical_production_input_archive(archive) is archive

    original_sources = archive.source_bindings
    equal_replacement = tuple(dataclasses.replace(item) for item in original_sources)
    assert equal_replacement == original_sources
    object.__setattr__(archive, "source_bindings", equal_replacement)
    try:
        with pytest.raises(
            PhysicalProductionInputArchiveError,
            match="not current builder authority",
        ):
            require_physical_production_input_archive(archive)
    finally:
        object.__setattr__(archive, "source_bindings", original_sources)
    assert require_physical_production_input_archive(archive) is archive


def test_persisted_tamper_and_surplus_inventory_are_refused(oracle):
    _authority_value, archive = oracle
    normalized = archive.batches[0].normalized_rows
    path = archive.archive_path / normalized.relative_path
    with path.open("ab") as handle:
        handle.write(b"{}\n")
    with pytest.raises(
        PhysicalProductionInputArchiveError,
        match="expected private regular file|changed during bounded traversal",
    ):
        require_physical_production_input_archive(archive)


def test_jsonl_traversal_enforces_record_bound_before_decode(oracle):
    _authority_value, archive = oracle
    descriptor = archive.evidence_rows
    constrained = dataclasses.replace(descriptor, maximum_record_byte_count=1)
    with pytest.raises(
        PhysicalProductionInputCapacityError,
        match="exceeds its recorded bound",
    ):
        _archive_path, archive_fd = disk._open_bound_archive_directory(archive)
        try:
            tuple(
                disk._iter_jsonl_fragments_at(
                    archive_fd,
                    descriptor.relative_path,
                    constrained,
                )
            )
        finally:
            os.close(archive_fd)


def test_manifest_and_semantic_files_are_content_addressed(oracle):
    _authority_value, archive = oracle
    manifest = (archive.archive_path / disk.ARCHIVE_MANIFEST).read_bytes()
    digest = (archive.archive_path / disk.ARCHIVE_MANIFEST_DIGEST).read_bytes()
    assert digest == (sha256_bytes(manifest) + "\n").encode("ascii")
    assert archive.archive_path.name == archive.archive_id
    assert archive.archive_id.endswith(archive.archive_sha256[:24])
