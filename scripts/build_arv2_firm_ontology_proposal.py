"""Reload exact physical inputs and write one inert 74-firm review proposal."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc.firm_ontology_proposal_generator import (
    FirmOntologyProposalError,
    NON_AUTHORITY_FIELDS,
    build_firm_ontology_proposal,
    require_firm_ontology_proposal,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchiveError,
    load_physical_accepted_risk_archive,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    PhysicalFirmOntologyReviewPacketError,
    load_physical_firm_ontology_review_packet,
)


SUMMARY_SCHEMA = "arv2-firm-ontology-proposal-cli-summary-v1"


class FirmOntologyProposalCliError(ValueError):
    """A CLI path or immutable pin is invalid before authority loading."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reload exact C1 and firm-review authority, then write a private "
            "non-authorizing 74-firm bulk-default proposal."
        )
    )
    parser.add_argument("--massive-source-artifact", required=True)
    parser.add_argument("--massive-source-manifest-sha256", required=True)
    parser.add_argument("--accepted-risk-archive", required=True)
    parser.add_argument("--accepted-risk-archive-sha256", required=True)
    parser.add_argument("--firm-review-packet", required=True)
    parser.add_argument("--firm-review-packet-sha256", required=True)
    parser.add_argument("--proposal-output-root", required=True)
    return parser


def _absolute(value: str, name: str) -> Path:
    if type(value) is not str or not value:
        raise FirmOntologyProposalCliError(f"{name} must be a nonempty path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise FirmOntologyProposalCliError(
            f"{name} must be a non-traversing absolute path"
        )
    return path


def _run(
    *,
    massive_source_artifact: Path,
    massive_source_manifest_sha256: str,
    accepted_risk_archive: Path,
    accepted_risk_archive_sha256: str,
    firm_review_packet: Path,
    firm_review_packet_sha256: str,
    proposal_output_root: Path,
    c1_loader: Callable = load_physical_accepted_risk_archive,
    packet_loader: Callable = load_physical_firm_ontology_review_packet,
    proposal_builder: Callable = build_firm_ontology_proposal,
) -> dict[str, object]:
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
    proposal = proposal_builder(
        review_packet=packet,
        output_root=proposal_output_root,
    )
    proposal = require_firm_ontology_proposal(proposal)
    return {
        "schema": SUMMARY_SCHEMA,
        "status": "owner_ratification_and_exception_adjudication_required",
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.proposal_sha256,
        "proposal_payload_sha256": proposal.payload_sha256,
        "proposal_path": str(proposal.path),
        "firm_count": proposal.firm_count,
        "bulk_ratification_eligible_firm_count": (
            proposal.bulk_ratification_eligible_firm_count
        ),
        "exception_firm_count": proposal.exception_firm_count,
        "unresolved_label_count": proposal.unresolved_label_count,
        **{name: False for name in NON_AUTHORITY_FIELDS},
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
            proposal_output_root=_absolute(
                arguments.proposal_output_root, "proposal output root"
            ),
        )
    except (
        FirmOntologyProposalCliError,
        PhysicalAcceptedRiskArchiveError,
        PhysicalFirmOntologyReviewPacketError,
        FirmOntologyProposalError,
    ) as exc:
        parser.exit(2, f"firm-ontology proposal refused: {exc}\n")
    sys.stdout.buffer.write(canonical_json_bytes(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
