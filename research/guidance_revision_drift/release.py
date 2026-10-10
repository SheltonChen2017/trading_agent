"""Reproducible pre-QC review manifest; all external launch gates stay closed.

Generation runs bounded built-in invented integration examples. Verification
reconstructs their hashes from current local source; an asserted success field
or newly self-computed outer hash is never sufficient evidence.
"""
from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
import platform
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import (
    _decode, load_candidate, verify_source_documents,
)
from research.guidance_revision_drift.fixtures import example_corpus, fixture_projection
from research.guidance_revision_drift.lean_bridge import fixture_stream
from research.guidance_revision_drift.reporting import source_manifest
from research.guidance_revision_drift.scenario import run_fixture_report
from research.guidance_revision_drift.specification import ExecutableSpecification


def _environment(body: dict) -> dict:
    """Only interpreter labels are portable; engine/settings stay content-bound."""
    try:
        environment = {key: body["engine"][key]
                       for key in ("python_implementation", "python_version")}
    except (KeyError, TypeError) as exc:
        raise ValueError("release interpreter labels missing") from exc
    for value in environment.values():
        if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.+\-]{1,64}", value):
            raise ValueError("invalid release interpreter label")
    return environment


def content_projection(body: dict) -> dict:
    """Drop exactly two descriptive environment labels, never runtime evidence.

    Caller-supplied objects cannot certify themselves: the verifier compares
    this canonical projection to a fresh reconstruction from current source.
    """
    result = deepcopy(body)
    for key in _environment(body):
        del result["engine"][key]
    result.pop("identities", None)
    return result


def _identities(body: dict) -> dict:
    return {"portable_content_sha256": hash_payload(content_projection(body)),
            "environment_sha256": hash_payload(_environment(body))}


def launch_preflight() -> dict:
    """There is deliberately no approval argument, credential read or launch."""
    specification = ExecutableSpecification(load_candidate()).to_dict()
    return {"status": "blocked", "qc_upload_allowed": False, "qc_launch_allowed": False,
            "provider_access_allowed": False, "paper_live_allowed": False,
            "qc_attempts": 0, "empirical_looks": 0,
            "readiness": {
                "offline_source_package": "unreviewed_preparation_candidate",
                "native_engine_execution": "unverified",
                "empirical_order_based_backtest": "blocked",
                "native_missing_evidence": ["pinned_engine_and_binding_run",
                    "native_callback_scheduling", "native_comparator_and_corporate_actions",
                    "equity_cash_settlement_parity"],
                "scope": "fixed_base_SYN_GDR_receipt_replay_not_an_empirical_data_adapter",
            },
            "required_before_external_evaluation": [
                "independent_Claude_review_of_exact_pushed_source",
                "accepted_Codex_counter_review_of_every_Claude_commit",
                "external_human_authorization_for_exact_synthetic_candidate",
                "reviewed_root_entrypoint_and_exact_372_frame_transport",
                "existing_authenticated_QC_access_without_install_purchase_or_account_change",
                "existing_project_file_and_remaining_log_quotas_cover_complete_native_evidence",
                "retained_owner_cycle_and_latest_head_preserve_attempt_budget_across_corrections",
                "record_project_compile_run_engine_and_binding_identities",
                "candidate_specific_maximum_three_unsuccessful_QC_attempts_then_Mia_or_owner",
            ],
            "external_evaluation_scope": "synthetic_only_order_based_integration_not_empirical",
            "required_before_empirical_evaluation": [
                "independent_Claude_review_of_exact_pushed_source",
                "owner_freeze_and_separate_exact_source_outcome_and_QC_authority",
                "audited_identifier_calendar_and_PIT_contracts",
                "pinned_native_engine_and_binding_validation",
                "native_fill_scheduling_and_cash_settlement_validation",
                "native_matched_comparator_and_corporate_action_parity",
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
    from research.guidance_revision_drift.bundle import build_bundle, verify_bundle
    bundle = build_bundle()
    bundle_receipt = verify_bundle(bundle, expected_sha256=hash_bytes(bundle))
    sources_after = source_manifest()
    if sources_before != sources_after:
        raise ValueError("source changed while building review release")
    result = {
        "schema": "gdr.synthetic.review-release.v2",
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
        "source_bundle": {"sha256": hash_bytes(bundle), "bytes": len(bundle),
                          "verification": bundle_receipt},
        "preflight": launch_preflight(),
        "market_evidence": False, "point_in_time_evidence": False,
        "independent_review_complete": False,
    }
    result["identities"] = _identities(result)
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


def verify_release_content(raw: bytes, *, expected_sha256: str,
                           expected_content_sha256: str) -> dict:
    """Verify portable content AND the supplied exact artifact's retained anchor.

    Does not relax verify_release's environment-bound byte equality. An
    environment difference remains explicit and is not a runtime-parity claim.
    """
    if type(expected_sha256) is not str or hash_bytes(raw) != expected_sha256:
        raise ValueError("release differs from caller-retained content anchor")
    body = _decode(raw)
    if raw != canonical_json(body).encode("utf-8"):
        raise ValueError("canonical release bytes required")
    identities = _identities(body)
    if (canonical_json(body.get("identities")) != canonical_json(identities)
            or type(expected_content_sha256) is not str
            or identities["portable_content_sha256"] != expected_content_sha256):
        raise ValueError("release identity or retained portable anchor mismatch")
    current = build_release()
    if canonical_json(content_projection(body)) != canonical_json(content_projection(current)):
        raise ValueError("release content does not reproduce from current source and fixtures")
    return {"status": "verified_portable_offline_content_only", "sha256": expected_sha256,
            "portable_content_sha256": expected_content_sha256,
            "artifact_environment": _environment(body), "current_environment": _environment(current),
            "environment_matches": _environment(body) == _environment(current),
            "runtime_parity_verified": False, "qc_launch_allowed": False, "market_evidence": False}
