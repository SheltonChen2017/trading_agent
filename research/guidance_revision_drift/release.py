"""Reproducible pre-QC review manifest; all external launch gates stay closed.

Generation runs bounded built-in invented integration examples. Verification
reconstructs their hashes from current local source; an asserted success field
or newly self-computed outer hash is never sufficient evidence.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import platform

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import (
    _decode, load_candidate, verify_source_documents,
)
from research.guidance_revision_drift.fixtures import example_corpus, fixture_projection
from research.guidance_revision_drift.lean_bridge import fixture_stream
from research.guidance_revision_drift.reporting import source_manifest
from research.guidance_revision_drift.scenario import run_fixture_report
from research.guidance_revision_drift.specification import ExecutableSpecification


def launch_preflight() -> dict:
    """There is deliberately no approval argument, credential read or launch."""
    specification = ExecutableSpecification(load_candidate()).to_dict()
    return {"status": "blocked", "qc_upload_allowed": False, "qc_launch_allowed": False,
            "provider_access_allowed": False, "paper_live_allowed": False,
            "qc_attempts": 0, "empirical_looks": 0,
            "required_before_external_evaluation": [
                "independent_Claude_review_of_exact_pushed_source",
                "owner_freeze_and_separate_exact_source_outcome_and_QC_authority",
                "audited_identifier_calendar_and_PIT_contracts",
                "installed_pinned_LEAN_engine_and_binding_validation",
                "native_fill_scheduling_and_cash_settlement_validation",
                "candidate_specific_maximum_three_unsuccessful_QC_attempts_then_Mia_or_owner",
            ], "original_candidate_blockers": specification["readiness"]["blockers"]}


def build_release() -> dict:
    candidate = load_candidate()
    verify_source_documents(candidate, Path(__file__).resolve().parents[2])
    sources_before = source_manifest()
    corpus = example_corpus()
    specification = ExecutableSpecification(candidate)
    report = run_fixture_report()
    # Import only the local invented-data composition, never an SDK entrypoint.
    from research.guidance_revision_drift.integration import run_integration_report
    integration = run_integration_report()
    sources_after = source_manifest()
    if sources_before != sources_after:
        raise ValueError("source changed while building review release")
    result = {
        "schema": "gdr.synthetic.review-release.v1",
        "status": "unreviewed_offline_engineering_candidate",
        "candidate_sha256": candidate.sha256,
        "proposed_specification_sha256": specification.sha256,
        "planning_sources": candidate.to_dict()["source_documents"],
        "source_manifest": sources_after,
        "code_sha256": hash_payload(sources_after),
        "data_contracts": {
            "guidance": "gdr.synthetic.vendor-context.v1 + Massive single-record public field shape",
            "lineage": "gdr.synthetic.provider-lineage.v1",
            "market": "gdr.synthetic.market-input.v1",
            "actions": "gdr.synthetic.corporate-action.v1",
            "recovery": "gdr.synthetic.recovery-genesis.v1",
            "limits": "invented SYN identities/2024-2025 observations; no rights/PIT certification",
        },
        "calendar": {"sha256": corpus.schedule.sha256, "audited_exchange_calendar": False,
                     "session_count": len(corpus.schedule.sessions),
                     "projection_sha256": hash_payload(fixture_projection([asdict(s) for s in corpus.schedule.sessions]))},
        "engine": {"python_implementation": platform.python_implementation(),
                   "python_version": platform.python_version(), "native_entrypoint": "research/guidance_revision_drift/lean/main.py",
                   "LEAN_version": None, "SDK_binding_verified": False, "QC_completed": False,
                   "native_settlement": "immediate_cash_envelope_not_equity_cash_account_parity",
                   "spending_authority": "shadow_explicit_fixture_settlement_only",
                   "native_fill_scheduling": "unverified_requires_exact_engine_run",
                   "synthetic_sidecar_sha256": hash_bytes(fixture_stream()),
                   "synthetic_sidecar_bytes": len(fixture_stream())},
        "reports": {"original_base_stress_sha256": hash_payload(report),
                    "integration_sha256": hash_payload(integration), "integration": integration},
        "preflight": launch_preflight(),
        "market_evidence": False, "point_in_time_evidence": False,
        "independent_review_complete": False,
    }
    # Reuse the strict bounded decoder for canonical JSON/number constraints.
    _decode(canonical_json(result).encode("utf-8"))
    return result


def verify_release(raw: bytes, *, expected_sha256: str) -> dict:
    if type(expected_sha256) is not str or hash_bytes(raw) != expected_sha256:
        raise ValueError("release differs from caller-retained content anchor")
    body = _decode(raw)
    if raw != canonical_json(body).encode("utf-8"):
        raise ValueError("canonical release bytes required")
    reconstructed = build_release()
    if raw != canonical_json(reconstructed).encode("utf-8"):
        raise ValueError("release does not reproduce from current local source and fixtures")
    return {"status": "verified_offline_content_only", "sha256": expected_sha256,
            "qc_launch_allowed": False, "market_evidence": False}
