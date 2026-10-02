#!/usr/bin/env python3
"""Build the fixed offline 2026 accepted-risk order-input successor."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from research.analyst_revisions_v2.global_benchmark_contract import (
    load_global_benchmark_contract,
)
from research.analyst_revisions_v2_qc.accepted_risk_delta_order_package import (
    EXPECTED_DELTA_LINEAGE_SHA256,
    EXPECTED_DELTA_PACKAGE_ID,
    EXPECTED_DELTA_PACKAGE_SHA256,
    build_accepted_risk_delta_order_package,
    load_accepted_risk_delta_order_package,
)
from research.analyst_revisions_v2_qc.accepted_risk_massive_delta import (
    build_parent_bound_massive_delta,
)
from research.analyst_revisions_v2_qc.accepted_risk_preliminary_package import (
    load_accepted_risk_preliminary_package,
)
from research.analyst_revisions_v2_qc.firm_ontology_owner_decision import (
    build_firm_ontology_owner_decision,
)
from research.analyst_revisions_v2_qc.firm_ontology_proposal_generator import (
    build_firm_ontology_proposal,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    load_physical_accepted_risk_archive,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    load_physical_firm_ontology_review_packet,
)
from research.analyst_revisions_v2_qc.production_evidence_composer import (
    build_section72_owner_waived_firm_admission,
)


ROOT = REPOSITORY_ROOT
ARTIFACTS = ROOT / "artifacts" / "analyst_revisions_v2"

PARENT_ARCHIVE_PATH = (
    ARTIFACTS
    / "physical_accepted_risk_20260914"
    / "arv2-physical-accepted-risk-83ef125320d6a74ce9e4ba1c"
)
PARENT_SOURCE_PATH = (
    ARTIFACTS
    / "massive_capture"
    / "arv2-massive-three-role-20260914T011337349022Z"
)
PARENT_ARCHIVE_SHA256 = (
    "83ef125320d6a74ce9e4ba1c2003f396d076a23d310bcafadf76774b7316bd11"
)
PARENT_SOURCE_MANIFEST_SHA256 = (
    "5ac9136d6ff1d21ba391ece762c128b510f478672cf5f4d2fd0f09976374625d"
)
PARENT_ARCHIVE_ID = "arv2-physical-accepted-risk-83ef125320d6a74ce9e4ba1c"

DELTA_ARCHIVE_PATH = (
    ARTIFACTS
    / "physical_accepted_risk_delta_20260916"
    / "arv2-physical-accepted-risk-1678b925bc78e8b3f4fdf291"
)
DELTA_SOURCE_PATH = (
    ARTIFACTS
    / "massive_capture"
    / "arv2-massive-three-role-20260917T051836493365Z"
)
DELTA_ARCHIVE_SHA256 = (
    "1678b925bc78e8b3f4fdf2911e3e426327fb8a1307463d1ff2bd43f279a1cc77"
)
DELTA_SOURCE_MANIFEST_SHA256 = (
    "3384e9745c3093eb203997d4a98057ae2d066180add5e0367c4c3687a50d83ea"
)
DELTA_ARCHIVE_ID = "arv2-physical-accepted-risk-1678b925bc78e8b3f4fdf291"

PRIOR_PACKAGE_PATH = (
    ARTIFACTS
    / "accepted_risk_preliminary_package_20260915_r054"
    / "arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2"
)
PRIOR_PACKAGE_SHA256 = (
    "e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9"
)
FIRM_PACKET_PATH = (
    ARTIFACTS
    / "physical_firm_ontology_review_20260914_03"
    / "arv2-firm-ontology-review-ac4d28e7126ebb066e12f289"
)
FIRM_PACKET_SHA256 = (
    "ac4d28e7126ebb066e12f28964083dab4196bf73e01618a2a638e8ad488c7aa4"
)


def _global_contract():
    specs = ROOT / "research" / "analyst_revisions_v2" / "specs"
    return load_global_benchmark_contract(
        map_path=specs / "arv2_global_rating_map.structural.json",
        matched_contract_path=(
            specs / "arv2_global_matched_comparison.structural.json"
        ),
        successor_spec_path=(
            specs / "arv2_stock_historical_successor.structural.json"
        ),
        parent_stock_spec_path=(
            specs / "arv2_stock_historical.structural.json"
        ),
        fold_manifest_path=(
            specs / "arv2_stock_walk_forward_folds.structural.json"
        ),
        qc_first_plan_path=specs / "arv2_qc_first.draft.json",
    )


def build(output_root: Path):
    output_root = Path(output_root)
    persisted = output_root / EXPECTED_DELTA_PACKAGE_ID
    if persisted.exists() or persisted.is_symlink():
        return load_accepted_risk_delta_order_package(
            persisted,
            expected_package_sha256=EXPECTED_DELTA_PACKAGE_SHA256,
            expected_lineage_sha256=EXPECTED_DELTA_LINEAGE_SHA256,
        )
    parent = load_physical_accepted_risk_archive(
        archive_path=PARENT_ARCHIVE_PATH,
        source_artifact_path=PARENT_SOURCE_PATH,
        expected_archive_sha256=PARENT_ARCHIVE_SHA256,
        expected_source_manifest_sha256=PARENT_SOURCE_MANIFEST_SHA256,
    )
    packet = load_physical_firm_ontology_review_packet(
        archive_path=FIRM_PACKET_PATH,
        expected_packet_sha256=FIRM_PACKET_SHA256,
        accepted_risk_archive=parent,
        preopen_seed_archive=None,
    )
    scratch = Path(tempfile.mkdtemp(prefix="arv2-firm-reconstruction-"))
    try:
        proposal = build_firm_ontology_proposal(
            review_packet=packet,
            output_root=scratch / "proposal",
        )
        decision = build_firm_ontology_owner_decision(
            review_packet=packet,
            proposal=proposal,
        )
        firms = build_section72_owner_waived_firm_admission(
            decision=decision,
            review_packet=packet,
        )
        delta = load_physical_accepted_risk_archive(
            archive_path=DELTA_ARCHIVE_PATH,
            source_artifact_path=DELTA_SOURCE_PATH,
            expected_archive_sha256=DELTA_ARCHIVE_SHA256,
            expected_source_manifest_sha256=DELTA_SOURCE_MANIFEST_SHA256,
        )
        composite = build_parent_bound_massive_delta(
            parent_archive=parent,
            delta_archive=delta,
            expected_parent_archive_id=PARENT_ARCHIVE_ID,
            expected_parent_archive_sha256=PARENT_ARCHIVE_SHA256,
            expected_delta_archive_id=DELTA_ARCHIVE_ID,
            expected_delta_archive_sha256=DELTA_ARCHIVE_SHA256,
        )
        prior = load_accepted_risk_preliminary_package(
            PRIOR_PACKAGE_PATH,
            expected_package_sha256=PRIOR_PACKAGE_SHA256,
        )
        result = build_accepted_risk_delta_order_package(
            composite=composite,
            prior_package=prior,
            firm_admission=firms,
            global_contract=_global_contract(),
            output_root=output_root,
        )
    finally:
        shutil.rmtree(scratch)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            ARTIFACTS / "accepted_risk_delta_order_package_20260918_01"
        ),
    )
    args = parser.parse_args()
    result = build(args.output_root.resolve())
    print(
        json.dumps(
            {
                "package_id": result.package.package_id,
                "package_sha256": result.package.package_sha256,
                "package_path": str(result.package.package_path),
                "lineage_sha256": result.lineage_sha256,
                "prior_contribution_count": result.prior_contribution_count,
                "delta_contribution_count": result.delta_contribution_count,
                "extended_membership_count": result.extended_membership_count,
                "decision_cutoff_session": result.decision_cutoff_session,
                "final_execution_session": result.final_execution_session,
                "orders": result.orders,
                "trading": result.trading,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
