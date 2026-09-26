#!/usr/bin/env python3
"""Compose the fixed Sep25 offline successor from pinned physical archives."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import build_arv2_delta_order_input_package as _predecessor
from research.analyst_revisions_v2_qc.accepted_risk_latest_order_package import (
    build_latest_order_input_package,
    persist_latest_order_input_lineage,
)


DEFAULT_OLD_PACKAGE = (
    _predecessor.ARTIFACTS / "accepted_risk_delta_order_package_20260918_01"
    / _predecessor.EXPECTED_DELTA_PACKAGE_ID
)
DEFAULT_OUTPUT_ROOT = _predecessor.ARTIFACTS / "accepted_risk_latest_order_package_20260925_01"


def build(
    *, fresh_archive_path: Path, fresh_source_path: Path,
    expected_fresh_archive_sha256: str, expected_fresh_source_manifest_sha256: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    old_package_path: Path = DEFAULT_OLD_PACKAGE,
):
    """Reuse the exact predecessor firm/global reconstruction; no network."""
    # The physical archive contract requires exact absolute Paths and rejects
    # links itself. Do not use resolve(), which would erase a supplied symlink.
    fresh_archive_path = Path(fresh_archive_path).absolute()
    fresh_source_path = Path(fresh_source_path).absolute()
    old_package_path = Path(old_package_path).absolute()
    output_root = Path(output_root).absolute()
    parent = _predecessor.load_physical_accepted_risk_archive(
        archive_path=_predecessor.PARENT_ARCHIVE_PATH,
        source_artifact_path=_predecessor.PARENT_SOURCE_PATH,
        expected_archive_sha256=_predecessor.PARENT_ARCHIVE_SHA256,
        expected_source_manifest_sha256=_predecessor.PARENT_SOURCE_MANIFEST_SHA256,
    )
    delta = _predecessor.load_physical_accepted_risk_archive(
        archive_path=_predecessor.DELTA_ARCHIVE_PATH,
        source_artifact_path=_predecessor.DELTA_SOURCE_PATH,
        expected_archive_sha256=_predecessor.DELTA_ARCHIVE_SHA256,
        expected_source_manifest_sha256=_predecessor.DELTA_SOURCE_MANIFEST_SHA256,
    )
    fresh = _predecessor.load_physical_accepted_risk_archive(
        archive_path=fresh_archive_path, source_artifact_path=fresh_source_path,
        expected_archive_sha256=expected_fresh_archive_sha256,
        expected_source_manifest_sha256=expected_fresh_source_manifest_sha256,
    )
    packet = _predecessor.load_physical_firm_ontology_review_packet(
        archive_path=_predecessor.FIRM_PACKET_PATH,
        expected_packet_sha256=_predecessor.FIRM_PACKET_SHA256,
        accepted_risk_archive=parent, preopen_seed_archive=None,
    )
    with tempfile.TemporaryDirectory(prefix="arv2-latest-firm-reconstruction-") as scratch:
        proposal = _predecessor.build_firm_ontology_proposal(
            review_packet=packet, output_root=Path(scratch) / "proposal",
        )
        decision = _predecessor.build_firm_ontology_owner_decision(
            review_packet=packet, proposal=proposal,
        )
        firms = _predecessor.build_section72_owner_waived_firm_admission(
            decision=decision, review_packet=packet,
        )
        result = build_latest_order_input_package(
            old_delta_package_path=old_package_path, parent_archive=parent,
            prior_delta_archive=delta, fresh_archive=fresh,
            firm_admission=firms, global_contract=_predecessor._global_contract(),
            output_root=output_root,
        )
    sidecar = persist_latest_order_input_lineage(result, output_root)
    return result, sidecar


def metadata(result, sidecar):
    package = result.package
    activation = package.upload_objects[-1]
    return {
        "package_id": package.package_id, "package_sha256": package.package_sha256,
        "package_path": str(package.package_path), "lineage_sha256": result.lineage_sha256,
        "lineage_path": str(sidecar), "session_count": result.lineage["session_count"],
        "decision_cutoff_session": result.decision_cutoff_session,
        "final_execution_session": result.final_execution_session,
        "recovered_tail_contribution_count": result.recovered_tail_contribution_count,
        "fresh_contribution_count": result.fresh_contribution_count,
        "combined_contribution_count": dict(package.contribution_census)["combined_contribution_count"],
        "activation_key": activation.object_store_key,
        "activation_sha256": activation.content_sha256,
        "activation_byte_count": activation.byte_count,
        "total_upload_byte_count": package.total_upload_byte_count,
        "orders": False, "trading": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh-archive-path", type=Path, required=True)
    parser.add_argument("--fresh-source-path", type=Path, required=True)
    parser.add_argument("--fresh-archive-sha256", required=True)
    parser.add_argument("--fresh-source-manifest-sha256", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result, sidecar = build(
        fresh_archive_path=args.fresh_archive_path,
        fresh_source_path=args.fresh_source_path,
        expected_fresh_archive_sha256=args.fresh_archive_sha256,
        expected_fresh_source_manifest_sha256=args.fresh_source_manifest_sha256,
        output_root=args.output_root,
    )
    print(json.dumps(metadata(result, sidecar), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
