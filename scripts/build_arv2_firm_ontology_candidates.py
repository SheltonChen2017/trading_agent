"""Reload reviewed physical inputs and publish ARV2 ontology candidates.

The command reauthenticates persisted C1 and firm-review bytes under explicit
owner/reviewer SHA-256 pins.  It therefore survives the manual adjudication
interval without rebuilding either authority.  It performs no network,
credential, QuantConnect, outcome, registry, deployment, order, or trading
operation.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc.firm_ontology_candidate_builder import (
    FirmOntologyCandidateError,
    build_firm_ontology_candidate_bundle,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchiveError,
    load_physical_accepted_risk_archive,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_candidate_archive import (
    FirmOntologyCandidatePublicationError,
    publish_firm_ontology_candidate_bundle,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    PhysicalFirmOntologyReviewPacketError,
    load_physical_firm_ontology_review_packet,
)


SUMMARY_SCHEMA = "arv2-firm-ontology-candidate-cli-summary-v1"


class FirmOntologyCandidateCliError(ValueError):
    """An explicit CLI path or separation precondition was refused."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reload exact C1 and firm-review authority, validate all 74 explicit "
            "owner adjudications, and publish non-authorizing private candidates."
        ),
        epilog=(
            "All archive inputs and the owner file must be absolute existing "
            "paths. The candidate output root must be a fresh absolute path."
        ),
    )
    parser.add_argument("--massive-source-artifact", required=True)
    parser.add_argument("--massive-source-manifest-sha256", required=True)
    parser.add_argument("--accepted-risk-archive", required=True)
    parser.add_argument("--accepted-risk-archive-sha256", required=True)
    parser.add_argument("--firm-review-packet", required=True)
    parser.add_argument("--firm-review-packet-sha256", required=True)
    parser.add_argument("--owner-adjudication-file", required=True)
    parser.add_argument("--candidate-output-root", required=True)
    return parser


def _absolute(value: str, name: str) -> Path:
    if type(value) is not str or not value:
        raise FirmOntologyCandidateCliError(
            f"{name} must be a nonempty absolute path"
        )
    candidate = Path(value)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise FirmOntologyCandidateCliError(
            f"{name} must be a non-traversing absolute path"
        )
    return candidate


def _overlap(left: Path, right: Path) -> bool:
    try:
        common = Path(os.path.commonpath((str(left), str(right))))
    except ValueError:
        return False
    return common == left or common == right


def _preflight_paths(
    *,
    massive_source_artifact: Path,
    accepted_risk_archive: Path,
    firm_review_packet: Path,
    owner_adjudication_file: Path,
    candidate_output_root: Path,
) -> None:
    directory_inputs = (
        massive_source_artifact,
        accepted_risk_archive,
        firm_review_packet,
    )
    inputs = (*directory_inputs, owner_adjudication_file)
    for path in directory_inputs:
        if path.is_symlink() or not path.is_dir():
            raise FirmOntologyCandidateCliError(
                "CLI archive inputs must be existing nonsymlink directories"
            )
    if owner_adjudication_file.is_symlink() or not owner_adjudication_file.is_file():
        raise FirmOntologyCandidateCliError(
            "owner adjudication must be an existing nonsymlink file"
        )
    if candidate_output_root.exists() or candidate_output_root.is_symlink():
        raise FirmOntologyCandidateCliError(
            "candidate output root must be fresh and absent"
        )
    if (
        not candidate_output_root.parent.is_dir()
        or candidate_output_root.parent.is_symlink()
    ):
        raise FirmOntologyCandidateCliError(
            "candidate output parent must be an existing nonsymlink directory"
        )
    all_paths = (*inputs, candidate_output_root)
    for index, left in enumerate(all_paths):
        for right in all_paths[index + 1 :]:
            if _overlap(left, right):
                raise FirmOntologyCandidateCliError(
                    "CLI input and output paths must not overlap"
                )


def _run(
    *,
    massive_source_artifact: Path,
    massive_source_manifest_sha256: str,
    accepted_risk_archive: Path,
    accepted_risk_archive_sha256: str,
    firm_review_packet: Path,
    firm_review_packet_sha256: str,
    owner_adjudication_file: Path,
    candidate_output_root: Path,
    c1_loader: Callable = load_physical_accepted_risk_archive,
    packet_loader: Callable = load_physical_firm_ontology_review_packet,
    candidate_builder: Callable = build_firm_ontology_candidate_bundle,
    publisher: Callable = publish_firm_ontology_candidate_bundle,
) -> dict[str, object]:
    """Execute the one-process reload chain; injection is test-only."""

    _preflight_paths(
        massive_source_artifact=massive_source_artifact,
        accepted_risk_archive=accepted_risk_archive,
        firm_review_packet=firm_review_packet,
        owner_adjudication_file=owner_adjudication_file,
        candidate_output_root=candidate_output_root,
    )
    c1 = c1_loader(
        archive_path=accepted_risk_archive,
        source_artifact_path=massive_source_artifact,
        expected_archive_sha256=accepted_risk_archive_sha256,
        expected_source_manifest_sha256=massive_source_manifest_sha256,
    )
    packet = packet_loader(
        archive_path=firm_review_packet,
        expected_packet_sha256=firm_review_packet_sha256,
        accepted_risk_archive=c1,
    )
    candidate = candidate_builder(
        review_packet=packet,
        owner_adjudication_path=owner_adjudication_file,
    )
    archive = publisher(
        candidate_bundle=candidate,
        output_root=candidate_output_root,
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "status": "candidate_archive_published_not_authorized",
        "accepted_risk_archive_id": c1.archive_id,
        "accepted_risk_archive_sha256": c1.archive_sha256,
        "firm_review_packet_id": packet.packet_id,
        "firm_review_packet_sha256": packet.packet_sha256,
        "candidate_bundle_id": candidate.bundle_id,
        "candidate_bundle_sha256": candidate.bundle_sha256,
        "candidate_archive_path": str(archive.archive_path),
        "firm_count": candidate.firm_count,
        "ontology_entry_count": candidate.ontology_entry_count,
        "full_massive_capture_rebuilt_once": False,
        "firm_review_source_rows_retraversed_once": False,
        "trusted_physical_packet_disk_reload_used": True,
        "independently_reviewed": False,
        "production_authority": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        summary = _run(
            massive_source_artifact=_absolute(
                arguments.massive_source_artifact, "Massive source artifact"
            ),
            massive_source_manifest_sha256=(
                arguments.massive_source_manifest_sha256
            ),
            accepted_risk_archive=_absolute(
                arguments.accepted_risk_archive, "accepted-risk archive"
            ),
            accepted_risk_archive_sha256=arguments.accepted_risk_archive_sha256,
            firm_review_packet=_absolute(
                arguments.firm_review_packet, "firm-review packet"
            ),
            firm_review_packet_sha256=arguments.firm_review_packet_sha256,
            owner_adjudication_file=_absolute(
                arguments.owner_adjudication_file, "owner adjudication file"
            ),
            candidate_output_root=_absolute(
                arguments.candidate_output_root, "candidate output root"
            ),
        )
    except (
        FirmOntologyCandidateCliError,
        PhysicalAcceptedRiskArchiveError,
        PhysicalFirmOntologyReviewPacketError,
        FirmOntologyCandidateError,
        FirmOntologyCandidatePublicationError,
    ) as exc:
        parser.exit(2, f"firm-ontology candidate build refused: {exc}\n")
    sys.stdout.buffer.write(canonical_json_bytes(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
