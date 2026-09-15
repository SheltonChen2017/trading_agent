"""Physical publication tests for non-authorizing firm candidates."""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc.firm_ontology_candidate_builder import (
    build_firm_ontology_candidate_bundle,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_candidate_archive as archive_module,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as packet_module,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_candidate_archive import (
    FirmOntologyCandidatePublicationAmbiguityError,
    FirmOntologyCandidatePublicationError,
    PhysicalFirmOntologyCandidateArchive,
    _publish_firm_ontology_candidate_bundle_for_test,
    publish_firm_ontology_candidate_bundle,
    require_physical_firm_ontology_candidate_archive,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    _build_physical_firm_ontology_review_packet_for_test,
)
from tests.analyst_revisions_v2.test_firm_ontology_candidate_builder import (
    _owner_rows,
    _write_owner,
)
from tests.analyst_revisions_v2.test_physical_firm_ontology_review_packet import (
    _c1,
    _rating,
)


@pytest.fixture(scope="module")
def review_packet(tmp_path_factory):
    root = tmp_path_factory.mktemp("physical-firm-candidates")
    ratings = [
        _rating(
            f"rating-{ordinal:03d}",
            firm_id=f"firm-{ordinal:03d}",
            firm_name=f"Firm {ordinal:03d}",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        )
        for ordinal in range(74)
    ]
    return _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=_c1(root, ratings),
        output_root=root / "review",
    )


def _bundle(review_packet, tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    owner = _write_owner(tmp_path / "owner.jsonl", _owner_rows(review_packet))
    return build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=owner,
    )


def _mode(path: Path) -> int:
    return path.stat(follow_symlinks=False).st_mode & 0o777


def test_publication_is_private_immutable_complete_and_reauthenticated(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "published"
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=bundle,
        output_root=output,
    )

    assert require_physical_firm_ontology_candidate_archive(archive) is archive
    assert archive.archive_id == bundle.bundle_id
    assert archive.archive_path == output / bundle.bundle_id
    assert archive.firm_count == 74
    assert archive.ontology_entry_count == 222
    assert _mode(output) == 0o700
    assert _mode(archive.archive_path) == 0o700
    assert all(_mode(path) == 0o600 for path in archive.archive_path.iterdir())
    assert set(path.name for path in archive.archive_path.iterdir()) == {
        archive_module.MANIFEST_FILENAME,
        archive_module.MANIFEST_DIGEST_FILENAME,
        archive_module.OWNER_ADJUDICATION_FILENAME,
        archive_module.ONTOLOGY_FILENAME,
        archive_module.AVAILABILITY_FILENAME,
        archive_module.AVAILABILITY_REVIEW_FILENAME,
        archive_module.REGISTRY_CANDIDATE_FILENAME,
        archive_module.COVERAGE_FILENAME,
    }
    assert archive.independently_reviewed is False
    assert archive.production_authority is False
    assert all(
        getattr(archive, name) is False
        for name in (
            "provider_access",
            "quantconnect_access",
            "outcome_access",
            "deployment",
            "orders",
            "trading",
        )
    )


def test_existing_root_and_symlink_are_refused_without_overwrite(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o700)
    sentinel = existing / "sentinel"
    sentinel.write_bytes(b"owner data")
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="already exists; overwrite is forbidden",
    ):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=existing,
        )
    assert sentinel.read_bytes() == b"owner data"

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(FirmOntologyCandidatePublicationError):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=alias,
        )
    assert list(target.iterdir()) == []


def test_second_publication_to_same_root_refuses_and_preserves_first(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "once"
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=bundle,
        output_root=output,
    )
    before = {
        path.name: path.read_bytes() for path in archive.archive_path.iterdir()
    }
    with pytest.raises(FirmOntologyCandidatePublicationError):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=output,
        )
    assert {
        path.name: path.read_bytes() for path in archive.archive_path.iterdir()
    } == before


def test_file_tamper_inventory_change_and_forged_authority_are_refused(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=bundle,
        output_root=tmp_path / "tamper",
    )
    forged = PhysicalFirmOntologyCandidateArchive(
        **{
            field.name: getattr(archive, field.name)
            for field in dataclasses.fields(archive)
        }
    )
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="not current publisher authority",
    ):
        require_physical_firm_ontology_candidate_archive(forged)

    ontology = archive.archive_path / archive_module.ONTOLOGY_FILENAME
    ontology.write_bytes(ontology.read_bytes() + b" ")
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="identity changed|content changed|owner-only",
    ):
        require_physical_firm_ontology_candidate_archive(archive)

    other = publish_firm_ontology_candidate_bundle(
        candidate_bundle=_bundle(review_packet, tmp_path / "other-input"),
        output_root=tmp_path / "inventory",
    )
    extra = other.archive_path / "extra"
    extra.write_bytes(b"x")
    extra.chmod(0o600)
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="not current publisher authority|inventory changed",
    ):
        require_physical_firm_ontology_candidate_archive(other)


def test_archive_creator_pid_guard_is_an_isolated_refusal(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=_bundle(review_packet, tmp_path),
        output_root=tmp_path / "pid",
    )
    monkeypatch.setattr(archive_module, "_AUTHORITY_PID", os.getpid() + 1)

    with pytest.raises(
        FirmOntologyCandidatePublicationError, match="another process"
    ):
        require_physical_firm_ontology_candidate_archive(archive)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_archive_registry_and_lock_reset_after_fork(
    review_packet, tmp_path: Path
) -> None:
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=_bundle(review_packet, tmp_path),
        output_root=tmp_path / "fork",
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        reset = (
            archive_module._AUTHORITY_PID == os.getpid()
            and archive_module._AUTHORITIES == {}
        )
        try:
            require_physical_firm_ontology_candidate_archive(archive)
        except FirmOntologyCandidatePublicationError:
            refused = True
        else:
            refused = False
        os.write(write_descriptor, b"ok" if reset and refused else b"bad")
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    try:
        result = os.read(read_descriptor, 3)
    finally:
        os.close(read_descriptor)
    waited, status = os.waitpid(child, 0)
    assert waited == child and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert result == b"ok"
    assert require_physical_firm_ontology_candidate_archive(archive) is archive


def test_ordinary_publication_failure_removes_stage_but_keeps_fresh_root(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "ordinary-failure"

    def refuse(_stage, _final):
        raise packet_module.PhysicalFirmOntologyReviewPacketError("sentinel")

    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="failed without replacement",
    ):
        _publish_firm_ontology_candidate_bundle_for_test(
            candidate_bundle=bundle,
            output_root=output,
            publish_stage=refuse,
        )
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_stage_directory_sync_failure_never_publishes_partial_candidate(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "stage-sync-failure"

    def fail_sync(_path):
        raise FirmOntologyCandidatePublicationError("stage sync sentinel")

    monkeypatch.setattr(archive_module, "_fsync_directory", fail_sync)
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="stage sync sentinel",
    ):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=output,
        )
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_total_capacity_includes_manifest_and_digest_without_partial_publish(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    payload_bytes = sum(
        len(payload) for _role, _name, payload in archive_module._file_payloads(bundle)
    )
    monkeypatch.setattr(archive_module, "MAX_ARCHIVE_BYTES", payload_bytes)
    output = tmp_path / "capacity"
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="exceeds its total byte bound",
    ):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=output,
        )
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_ambiguous_publication_preserves_exact_private_stage(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "ambiguous"

    def ambiguous(_stage, _final):
        raise packet_module.PhysicalFirmOntologyReviewPacketPublicationAmbiguityError(
            "sentinel"
        )

    with pytest.raises(
        FirmOntologyCandidatePublicationAmbiguityError,
        match="private residue preserved",
    ):
        _publish_firm_ontology_candidate_bundle_for_test(
            candidate_bundle=bundle,
            output_root=output,
            publish_stage=ambiguous,
        )
    residue = list(output.iterdir())
    assert len(residue) == 1
    assert residue[0].name.startswith(".firm-candidate-stage-")
    assert _mode(residue[0]) == 0o700
    assert all(_mode(path) == 0o600 for path in residue[0].iterdir())


def test_post_publish_failure_rolls_back_without_visible_candidate(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    output = tmp_path / "late-failure"

    def fail_mint(**_kwargs):
        raise RuntimeError("mint sentinel")

    monkeypatch.setattr(archive_module, "_mint", fail_mint)
    with pytest.raises(RuntimeError, match="mint sentinel"):
        _publish_firm_ontology_candidate_bundle_for_test(
            candidate_bundle=bundle,
            output_root=output,
        )
    assert output.is_dir()
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    ("target_name", "attribute"),
    [
        ("builder", "require_firm_ontology_candidate_bundle"),
        ("publication", "_publish_stage"),
        ("publication", "_rollback_published_stage"),
    ],
)
def test_each_publisher_dependency_guard_is_mutation_sensitive(
    review_packet,
    tmp_path: Path,
    monkeypatch,
    target_name: str,
    attribute: str,
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    target = (
        archive_module._builder
        if target_name == "builder"
        else archive_module._publication
    )
    monkeypatch.setattr(target, attribute, object())
    with pytest.raises(
        FirmOntologyCandidatePublicationError,
        match="dependency binding changed",
    ):
        publish_firm_ontology_candidate_bundle(
            candidate_bundle=bundle,
            output_root=tmp_path / f"dependency-{attribute}",
        )


def test_candidate_archive_contains_no_world_writable_object(
    review_packet, tmp_path: Path
) -> None:
    bundle = _bundle(review_packet, tmp_path)
    archive = publish_firm_ontology_candidate_bundle(
        candidate_bundle=bundle,
        output_root=tmp_path / "modes",
    )
    for root, directories, files in os.walk(archive.archive_path.parent):
        root_path = Path(root)
        assert _mode(root_path) == 0o700
        assert all(_mode(root_path / name) == 0o700 for name in directories)
        assert all(_mode(root_path / name) == 0o600 for name in files)
