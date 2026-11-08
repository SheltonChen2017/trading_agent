"""Detached draft for an order-based pilot with declared data assumptions.

This module prepares a roster and data requirements, never signals, orders or
outcomes. It does not modify source profiles, clear their refusals, invent
receipts, qualify quotes, or provide an execution input. Proposed exceptions
belong to a separate exploratory model; they are not applied by this report.
"""
from __future__ import annotations

from collections import Counter

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import Candidate
from research.guidance_revision_drift.guidance_dataset import GuidanceDataset
from research.guidance_revision_drift.input_contracts import (
    InputError, canonical_bytes, day, digest, identifier,
)
from research.guidance_revision_drift.readiness import preflight


# An explicit, bounded exception set. Unknown issues, missing semantic fields,
# changed definitions and inconsistent supplied predecessors remain excluded.
_ASSUMABLE_ISSUES = {
    "adjustment_policy_and_scope_comparability_unverified": "reported_context_comparable",
    "non_gaap_definition_and_share_scope_equivalence_unverified": "reported_context_comparable",
    "complete_intervening_correction_withdrawal_census_unverified": "supplied_guidance_history",
    "immediate_issuer_guidance_predecessor_unverified": "supplied_guidance_history",
    "cusip_event_date_continuity_and_corporate_actions_unverified": "reconstructed_identity",
    "dated_permanent_security_mapping_unverified": "reconstructed_identity",
    "reconstructed_security_identity_not_historical_receipt": "reconstructed_identity",
    "derived_reporting_calendar_and_context_not_pit": "model_availability",
    "historical_first_delivery_and_versions_unverified": "model_availability",
    "retained_source_is_rendered_excerpt_not_complete_original": "incomplete_source_context",
}
_PROPOSALS = {
    "supplied_guidance_history": "Use supplied immediate predecessors; unknown intervening disclosures remain unknown.",
    "reported_context_comparable": "Model the retained, equal non-null definitions/share/scope as comparable; no source verification claimed.",
    "reconstructed_identity": "Use the named reconstructed identity only for this supplied cohort; continuity remains unverified.",
    "model_availability": "Use a separately labelled date-only third-session model; never fabricate historical publication or receipt instants.",
    "incomplete_source_context": "Retain excerpt limitations in the pilot; do not claim complete issuer originals.",
    "unknown_quote_condition": "Propose treating unknown original conditions as regular only in a separate exploratory model; retain original flags and numerical/clock checks.",
    "native_parity_deferred": "Defer native parity certification, preserving dated settlement, settled cash, order reconciliation and matched-SPY budgets/timing/costs.",
}
_PILOT_BASES = {
    "period": ("FY",), "currency": ("USD",),
    "revenue_units": ("USD", "USD_millions"), "eps_units": ("USD_per_share",),
    "revenue_basis": ("gaap",), "eps_basis": ("adj",),
}


def prepare_exploratory_backtest(
    candidate: Candidate, dataset_bytes: bytes, *, expected_dataset_sha256: str,
    producing_source_sha256: str, quote_coverage_sha256: str,
    quote_condition_overlay_sha256: str, preparation_id: str,
    owner_direction_reference: str, study_start: str, study_end: str,
) -> dict:
    """Build a metadata-only draft; references do not prove data or approval.

    Every supplied profile and missing expected ID remains accounted for.
    Pair placeholders are not qualifying signals or an accepted universe.
    No provider, environment, filesystem, clock or evaluation access occurs.
    """
    if type(candidate) is not Candidate:
        raise InputError("exact pinned base candidate required")
    checked = Candidate(candidate.canonical_bytes)
    rules = checked.to_dict()
    dataset = GuidanceDataset.from_bytes(dataset_bytes, expected_sha256=expected_dataset_sha256)
    source = dataset.to_dict()
    for value in (producing_source_sha256, quote_coverage_sha256, quote_condition_overlay_sha256):
        digest(value)
    identifier(preparation_id)
    identifier(owner_direction_reference)
    start, end = day(study_start), day(study_end)
    evidence = rules["evidence"]
    if (start > end or start < day(evidence["historical_earliest_proposed"])
            or end >= day(evidence["outcome_quarantine_from"])):
        raise InputError("ordered unprotected draft study dates required")
    if (start > day(source["scope"]["publication_start"])
            or end < day(source["scope"]["publication_end"])):
        raise InputError("draft must retain the complete declared publication scope")

    decisions = {row["profile_id"]: row for row in source["decisions"]}
    roster = []
    for profile in source["profiles"]:
        original = decisions[profile["profile_id"]]
        assumptions, exclusions = set(), []
        # Source issue strings cannot impersonate compiler-generated prefixes.
        exclusions.extend(issue for issue in profile["issues"] if issue not in _ASSUMABLE_ISSUES)
        # The source compiler permits non-null unsupported labels on baseline
        # rows; this pilot still needs FY/USD/GAAP-revenue/adjusted-EPS context.
        exclusions.extend("unsupported_pilot_" + name for name, supported in _PILOT_BASES.items()
                          if profile[name] not in supported)
        for reason in original["refusal_reasons"]:
            issue = reason.removeprefix("predecessor_issue_")
            if issue in _ASSUMABLE_ISSUES:
                assumptions.add(_ASSUMABLE_ISSUES[issue])
            else:
                exclusions.append(reason)
        if original["disposition"] == "control_event":
            exclusions.append("control_event_requires_separate_lifecycle_handling")
        if exclusions:
            role = "excluded"
        elif original["predecessor_profile_id"] is None:
            role = "baseline_placeholder"
        else:
            role = "pair_placeholder"
        roster.append({
            "profile_id": profile["profile_id"],
            "original_profile_sha256": hash_bytes(canonical_bytes(profile)),
            "original_decision": original,
            "published_date": profile["published_date"],
            "published_at": profile["published_at"],
            "actual_captured_at": profile["captured_at"],
            "preparation_role": role,
            "assumption_ids": sorted(assumptions),
            "exclusion_reasons": sorted(set(exclusions)),
            "assumptions_applied": False,
            "qualifying_signal_computed": False,
        })
    return {
        "schema": "gdr.exploratory-backtest-preparation.v1",
        "preparation_id": preparation_id,
        "owner_direction_reference": owner_direction_reference,
        "status": "draft_pilot_preparation_only",
        "base_candidate_sha256": checked.sha256,
        "producing_source_sha256": producing_source_sha256,
        "guidance_dataset_sha256": dataset.sha256,
        "original_guidance_gates": source["gates"],
        "original_readiness": preflight(checked).to_dict(),
        "economic_rules": {name: rules[name] for name in (
            "signal", "universe", "timing", "portfolio", "execution", "exits", "statistics")},
        "proposed_study": {
            "start": study_start, "end": study_end, "frozen": False,
            "scope": "supplied_event_pilot_not_full_universe_or_viability_study",
            "original_minimum_usable_history_years": evidence["history_feasibility_min_years"],
            "minimum_usable_history_verified": False,
            "partition_and_look_allocation_frozen": False,
        },
        "proposed_exceptions": [{"id": name, "description": description,
                                 "applied": False, "fact_verified": False}
                                for name, description in sorted(_PROPOSALS.items())],
        "roster": roster,
        "missing_expected_profile_ids": source["missing_profile_ids"],
        "profile_count": len(roster),
        "roles": dict(sorted(Counter(row["preparation_role"] for row in roster).items())),
        "market_inputs": {
            "quote_coverage_reference_sha256": quote_coverage_sha256,
            "condition_overlay_reference_sha256": quote_condition_overlay_sha256,
            "references_are_not_a_price_tape": True,
            "continuous_market_data_bound": False, "price_tape_sha256": None,
            "original_conditions_recovered": False, "execution_qualified": False,
            "required_data": ["continuous_raw_stock_and_SPY_quotes_and_minute_volume",
                              "listing_and_ADV_lookbacks", "dated_calendar_identity_sector_and_actions",
                              "dividend_payment_dates_and_terminal_events"],
        },
        "remaining_build_steps": ["bind_continuous_market_data_and_calendar",
                                  "implement_profile_to_model_input_adapter_without_fake_receipts",
                                  "implement_separate_exploratory_quote_condition_model",
                                  "reconcile_order_cash_settlement_and_matched_SPY_outputs",
                                  "freeze_exact_pilot_source_inputs_dates_and_look_scope_before_launch"],
        "runnable": False, "backtest_ready": False, "point_in_time_data": False,
        "qc_access_allowed": False, "outcome_calculations": 0,
        "order_based": True, "assumptions_applied": False,
    }
