"""Content-addressed TPR-0A algorithm freeze and fail-closed authority gate.

The immutable parent implemented here freezes algorithms and policy only.  It
does not invent the empirical values that require reviewed TPR-1/2 structural
evidence.  Those values must arrive in a separately content-addressed,
independently reviewed ``tpr-structural-bindings-v1`` child that binds this
parent's complete hash.  No provider or outcome reader exists in this module.
"""

# TPR-CCR5-001: tracked LF migration marker for existing Windows worktrees.
from __future__ import annotations

import dataclasses
import threading
import weakref
from decimal import Decimal
from pathlib import Path
from typing import Mapping, NoReturn

from . import (
    ALGORITHM_SPEC_SCHEMA,
    FAMILY_ID,
    PRIMARY_CELL_ID,
    PRIMARY_LOOK_ID,
    STRUCTURAL_BINDING_SCHEMA,
)
from .canonical import (
    CanonicalContractError,
    authority_value,
    canonical_json_bytes,
    deep_freeze,
    require_aware_instant,
    require_canonical_json_bytes,
    require_date,
    require_decimal_text,
    require_exact_keys,
    require_git_commit,
    require_sha256,
    require_text,
    sha256_bytes,
)
from .trust_root import (
    SIGNATURE_POLICY,
    TrustRootError,
    authority_git,
    authority_is_ancestor,
    computed_policy_repo_paths,
    verify_signed_registry_anchor,
)


class PreregistrationError(ValueError):
    """A TPR policy, review identity, or authority boundary is invalid."""


CANDIDATE_STATUS = "algorithm_policy_frozen_pending_structural_bindings_and_review"
REVIEWED_ALGORITHM_STATUS = "reviewed_algorithm_policy_frozen"
REVIEW_REGISTRY_SCHEMA = "tpr-reviewed-algorithm-registry-v2"
SOURCE_AUTHORITY_SCHEMA = "tpr-research-source-authority-v1"
PERMANENT_LOOK_AUTHORITY_SCHEMA = "tpr-permanent-look-authority-v1"
ZERO_ACCESS_SOURCE_AUTHORITY_ID = "tpr-zero-access-no-source-authority"
ZERO_ACCESS_LOOK_AUTHORITY_ID = "tpr-zero-access-no-permanent-look-authority"
CELL_SOURCE = (
    "Codex TPR-0A amendment candidate 2026-08-30 under the owner-approved "
    "target-price blueprint v2.2 fixed four-slot contract; pending Claude "
    "independent review"
)
FIXED_LANE_IDS = (
    "analyst-revisions-v2",
    "insider-buying",
    "short-interest",
    "target-price-revisions",
)
ASSIGNED_LANE_ID = "target-price-revisions"
SHARED_FAMILY_WISE_ALPHA = Decimal("0.05")
WITHIN_LANE_ALPHA_CEILING = Decimal("0.0125")
EMPTY_REVIEW_REGISTRY_BYTES = canonical_json_bytes(
    {
        "entries": [],
        "schema": REVIEW_REGISTRY_SCHEMA,
        "signature_policy": SIGNATURE_POLICY,
    }
)
CANDIDATE_REPO_PATH = (
    "research/target_price_revisions/specs/tpr_round0a.candidate.json"
)
POLICY_CODE_REPO_PATHS = (
    "research/__init__.py",
    "research/target_price_revisions/__init__.py",
    "research/target_price_revisions/canonical.py",
    "research/target_price_revisions/import_firewall.py",
    "research/target_price_revisions/preregistration.py",
    "research/target_price_revisions/trust_root.py",
    "research/target_price_revisions/windows_acl.py",
    "research/target_price_revisions/specs/.gitattributes",
)

REQUIRED_CELL_IDS = (
    "governance_contract",
    "phase_split_contract",
    "shared_holdout",
    "family_multiplicity",
    "source_contract",
    "source_authority",
    "event_taxonomy",
    "clock_contract",
    "cutoff_contract",
    "correction_contract",
    "basis_contract",
    "universe_contract",
    "primary_event_formula",
    "decay_contract",
    "independence_contract",
    "normalization_contract",
    "controls_contract",
    "estimator_contract",
    "decision_outcome_contract",
    "walk_forward_contract",
    "cost_contract",
    "empirical_binding_contract",
    "trial_and_null_contract",
    "legacy_separation_contract",
)

_TOP_KEYS = frozenset(
    {
        "schema",
        "status",
        "spec_id",
        "spec_hash",
        "producing_commit",
        "reviewed_by",
        "reviewed_at",
        "cells",
        "looks",
    }
)
_CELL_KEYS = frozenset({"cell_id", "state", "value", "source"})
_LOOK_KEYS = frozenset(
    {
        "look_id",
        "family_id",
        "primary_cell_id",
        "state",
        "validation_start",
        "validation_end",
        "dataset_id",
        "code_identity",
        "structural_binding_id",
        "structural_binding_sha256",
        "cost_cell_hash",
    }
)
_REGISTRY_KEYS = frozenset({"schema", "signature_policy", "entries"})
_REGISTRY_SIGNATURE_POLICY_KEYS = frozenset(SIGNATURE_POLICY)
_REGISTRY_ENTRY_KEYS = frozenset(
    {
        "spec_id",
        "spec_hash",
        "artifact_sha256",
        "spec_path",
        "candidate_path",
        "candidate_spec_id",
        "candidate_spec_hash",
        "candidate_artifact_sha256",
        "policy_code_sha256",
        "review_commit",
        "reviewed_by",
        "reviewed_at",
    }
)
PACKAGE_ROOT = Path(__file__).resolve().parent
ALGORITHM_CANDIDATE_PATH = PACKAGE_ROOT / "specs" / "tpr_round0a.candidate.json"
REVIEWED_SPEC_REGISTRY_PATH = PACKAGE_ROOT / "specs" / "reviewed_spec_registry.json"
RESEARCH_SOURCE_AUTHORITY_PATH = (
    PACKAGE_ROOT / "specs" / "research_source_authority.json"
)
PERMANENT_LOOK_AUTHORITY_PATH = (
    PACKAGE_ROOT / "specs" / "permanent_look_authority.json"
)

_DOCUMENTED_PROVIDER_FIELDS = (
    "adjusted_price_target",
    "analyst",
    "benzinga_analyst_id",
    "benzinga_calendar_url",
    "benzinga_firm_id",
    "benzinga_id",
    "benzinga_news_url",
    "company_name",
    "currency",
    "date",
    "firm",
    "importance",
    "last_updated",
    "notes",
    "previous_adjusted_price_target",
    "previous_price_target",
    "previous_rating",
    "price_percent_change",
    "price_target",
    "price_target_action",
    "rating",
    "rating_action",
    "ticker",
    "time",
)
DOCUMENTED_PROVIDER_FIELDS = _DOCUMENTED_PROVIDER_FIELDS

# Every policy value is repeated here deliberately.  A valid content hash
# proves identity, not acceptability; a correctly re-hashed policy weakening
# must still fail these semantic pins.
_EXPECTED_VALUES = deep_freeze(
    {
        "governance_contract": {
            "authority_ceiling": "research_contract_only_zero_provider_zero_outcome",
            "blueprint_path": (
                "docs/Strategy Description/"
                "TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf"
            ),
            "blueprint_sha256": (
                "f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b"
            ),
            "blueprint_version": "2.2",
            "blueprint_role": "sole_governing_target_price_strategy_authority",
            "submitted_source_pin_disposition": (
                "historical_malformed_unavailable_not_authority"
            ),
            "live_trading_authorized": False,
            "paper_trading_authorized": False,
            "qc_job_authorized": False,
            "outcome_access_authorized": False,
        },
        "phase_split_contract": {
            "parent_phase": "TPR-0A_algorithm_and_policy_freeze",
            "parent_immutable_after_review": True,
            "child_schema": STRUCTURAL_BINDING_SCHEMA,
            "child_phase": "post_TPR-1_TPR-2_zero_outcome_structural_binding",
            "child_must_bind_parent_spec_hash": True,
            "child_must_be_independently_reviewed": True,
            "child_may_change_parent_algorithm": False,
            "child_required_before": [
                "TPR-3_canonical_score_publication",
                "any_target_aligned_outcome_access",
                "any_permanent_look_spend",
            ],
            "child_inputs_must_exclude": [
                "future_returns_joined_to_target_events",
                "ranked_candidate_formula_results",
                "shared_final_holdout",
            ],
        },
        "shared_holdout": {
            "shared_family_count": 4,
            "validation_start": "2026-09-01",
            "cutoff_session": "2027-08-31",
            "validation_end": "2027-08-31",
            "reserved_start": "2027-09-01",
            "reserved_end": "2029-08-31",
            "lane_access_prohibited": True,
        },
        "family_multiplicity": {
            "family_id": FAMILY_ID,
            "fixed_lane_ids": list(FIXED_LANE_IDS),
            "assigned_lane_id": ASSIGNED_LANE_ID,
            "shared_family_count": 4,
            "shared_family_wise_alpha": "0.05",
            "allocation": "fixed_equal_bonferroni_across_four_lane_slots",
            "assigned_family_alpha": "0.0125",
            "within_lane_confirmatory_alpha_ceiling": "0.0125",
            "slot_reallocation": {
                "transferable": False,
                "unused": "EXPIRES",
                "withdrawn": "EXPIRES",
                "redistribution": "PROHIBITED",
            },
            "confirmatory_alpha_allocations": [
                {
                    "look_id": PRIMARY_LOOK_ID,
                    "primary_cell_id": PRIMARY_CELL_ID,
                    "two_sided_alpha": "0.0125",
                }
            ],
            "permanent_primary_cell_ids": [PRIMARY_CELL_ID],
            "permanent_look_ids": [PRIMARY_LOOK_ID],
            "look_budget": 1,
            "external_append_only_authority_required": True,
        },
        "source_contract": {
            "provider_contract_id": "massive-benzinga-target-revisions-v1",
            "provider": "Massive/Benzinga Analyst Ratings",
            "http_method": "GET",
            "endpoint": "/benzinga/v1/ratings",
            "schema_version": "v1",
            "documentation_urls": [
                "https://massive.com/docs/rest/partners/benzinga/analyst-ratings",
                "https://www.benzinga.com/apis/cloud-product/analyst-ratings-api/",
            ],
            "documented_provider_fields": list(_DOCUMENTED_PROVIDER_FIELDS),
            "retrieval_contract": {
                "scope": "all_history_unfiltered_through_frozen_high_water",
                "provider_earliest_history_claim": "2011-12-08",
                "earliest_history_claim_disposition": (
                    "audit_claim_only_never_accepted_coverage_without_reviewed_capture"
                ),
                "first_request_limit": 50000,
                "first_request_sort": "last_updated_ascending",
                "high_water": (
                    "exact_aware_UTC_last_updated_upper_bound_bound_in_reviewed_"
                    "source_history_schema_audit"
                ),
                "prohibited_caller_filters": [
                    "ticker",
                    "firm",
                    "analyst",
                    "rating_action",
                    "price_target_action",
                ],
                "first_request_cursor": None,
                "pagination": (
                    "follow_each_same_endpoint_next_url_in_order_until_absent_or_null"
                ),
                "next_url_validation": (
                    "exact_HTTPS_provider_host_and_endpoint_with_frozen_limit_sort_"
                    "high_water_and_only_provider_cursor_variation"
                ),
                "cursor_cycle_duplicate_or_page_replay": "REFUSED",
                "high_water_violation_or_nonascending_last_updated": "REFUSED",
            },
            "raw_page_contract": {
                "hash_every_request_method_url_credential_redacted_nonsecret_"
                "canonical_query_and_headers_status_fetch_clock_and_raw_response_"
                "bytes": True,
                "full_ordered_page_inventory_required": True,
                "page_count_and_row_count_required": True,
                "immutable_raw_page_sha256_required": True,
                "stable_row_locator": (
                    "page_sha256_plus_zero_based_row_index_plus_provider_id_if_present"
                ),
                "byte_identical_duplicate_row": (
                    "retain_raw_then_deduplicate_normalized_identity_with_audit_count"
                ),
                "conflicting_duplicate_provider_id_or_cursor": "REFUSED",
            },
            "secret_handling_contract": {
                "excluded_from_persisted_request_metadata_and_hashes": [
                    "authorization_values",
                    "cookie_values",
                    "api_key_values",
                    "secret_query_values",
                    "derived_secret_hashes",
                ],
                "persisted_nonsecret_identity": (
                    "reviewed_credential_authority_id_plus_redacted_header_and_"
                    "query_parameter_names_only"
                ),
                "unclassified_secret_bearing_metadata": "REFUSED",
                "raw_response_secret_scan_required_before_persistence": True,
            },
            "schema_handling_contract": {
                "numeric_fields": [
                    "adjusted_price_target",
                    "importance",
                    "previous_adjusted_price_target",
                    "previous_price_target",
                    "price_percent_change",
                    "price_target",
                ],
                "numeric_token_parser": (
                    "original_JSON_number_or_decimal_string_to_exact_finite_Decimal_"
                    "without_binary_float_or_locale_coercion"
                ),
                "optional_absent_or_null": "named_MISSING_never_zero_or_empty_string",
                "required_absent_or_null": "REFUSED",
                "boolean_as_integer_or_decimal": "REFUSED",
                "scalar_type_mismatch": "REFUSED",
                "action_handling": (
                    "exact_trimmed_case_sensitive_value_through_reviewed_versioned_"
                    "action_map_unknown_or_conflicting_action_REFUSED_no_fuzzy_mapping"
                ),
                "unknown_field_policy": "REFUSED_until_schema_version_is_reviewed",
                "exact_optional_null_type_action_matrix_child_binding_required": True,
            },
            "unknown_field_policy": "refuse_row",
            "missing_optional_field_policy": "retain_named_missing_or_refusal",
            "capture_contract": (
                "immutable_raw_bytes_request_response_metadata_fetch_clock_"
                "page_inventory_sha256_manifest"
            ),
            "provider_reader_implemented": False,
        },
        "source_authority": {
            "authority_mode": "zero_access",
            "entitlement_state": "UNESTABLISHED",
            "earliest_public_time_semantics_state": "UNESTABLISHED",
            "correction_completeness_state": "UNESTABLISHED",
            "target_horizon_consistency_state": "UNESTABLISHED",
            "raw_retention_rights_state": "UNESTABLISHED",
            "derived_processing_rights_state": "UNESTABLISHED",
            "qc_transfer_rights_state": "UNESTABLISHED",
            "entitlement_verified": False,
            "earliest_public_time_semantics_established": False,
            "correction_completeness_established": False,
            "target_horizon_consistency_established": False,
            "credential_access_authorized": False,
            "source_requests_authorized": False,
            "structural_sample_access_authorized": False,
            "local_raw_storage_right_verified": False,
            "normalized_processing_right_verified": False,
            "qc_transfer_right_verified": False,
            "provider_sample_accessed": False,
        },
        "event_taxonomy": {
            "valid_states": [
                "VALID_ZERO",
                "VALID_NONZERO",
                "MISSING",
                "REFUSED",
                "INELIGIBLE",
            ],
            "eligible_revision": (
                "finite_positive_prior_and_new_target_with_computable_signed_change"
            ),
            "raise_direction": "positive",
            "cut_direction": "negative",
            "same_reconciled_target": "VALID_ZERO",
            "initiation_set_announce_without_positive_prior": (
                "target_level_diagnostic_never_revision"
            ),
            "withdrawal_suspension_no_target": (
                "MISSING_and_active_roster_change_never_numeric_zero"
            ),
            "zero_negative_nonfinite_contradictory_or_currency_ambiguous": "REFUSED",
            "unknown_action": "REFUSED",
            "exactly_one_disposition_per_raw_locator": True,
        },
        "clock_contract": {
            "effective_at": "descriptive_only_never_tradability_authority",
            "available_at": "earliest_independently_verified_public_availability",
            "ingested_at": "capture_and_latency_only_cannot_move_availability_earlier",
            "version_available_at": "correction_usability_clock",
            "information_time": "verified_available_at_else_conservative_date_only",
            "precise_clock_without_publication_evidence": "date_only",
            "ambiguous_timezone": "REFUSED",
            "date_only_rule": "no_earlier_than_second_exchange_open_after_event_date",
            "eligible_open_rule": (
                "first_exchange_open_strictly_after_max_information_time_and_research_cutoff"
            ),
            "same_day_premarket_canonical": False,
        },
        "cutoff_contract": {
            "timezone": "America/New_York",
            "prior_session_local_time": "18:00:00",
            "cutoff_basis": "prior_exchange_session",
            "decision_frequency": "weekly",
            "decision_session": "first_eligible_exchange_session_of_week",
            "holiday_rule": "roll_to_next_exchange_session",
            "later_same_day_version_policy": "future_decisions_only",
        },
        "correction_contract": {
            "raw_versions_immutable": True,
            "stable_event_lineage_required": True,
            "selection_at_cutoff": (
                "latest_version_whose_version_available_at_is_not_after_cutoff"
            ),
            "final_state_backfill_prohibited": True,
            "missing_from_later_snapshot_is_withdrawal": False,
            "duplicate_provider_id_or_collision": "REFUSED",
            "deletion_requires_explicit_provider_evidence": True,
        },
        "basis_contract": {
            "preserve_raw_and_provider_adjusted_targets": True,
            "common_share_basis_required": True,
            "split_double_adjustment": "REFUSED",
            "split_policy": "point_in_time_effective_session_evidence",
            "currency_policy": "point_in_time_fx_available_before_cutoff",
            "missing_stale_or_ambiguous_fx": "REFUSED",
            "adr_policy": "point_in_time_depositary_ratio_and_underlying_identity",
            "missing_or_ambiguous_adr_ratio": "REFUSED",
            "target_horizon_policy": "explicit_and_comparable_prior_to_new",
            "missing_or_incomparable_target_horizon": "REFUSED",
            "target_pair_selection": (
                "select_exactly_one_unmixed_pair_after_the_reviewed_vendor_adjustment_"
                "and_restatement_audit;use_adjusted_new_and_adjusted_prior_only_when_"
                "the_audit_proves_both_cutoff_valid_values_share_one_currency_common_"
                "share_basis_target_horizon_and_split_lineage;otherwise_use_raw_new_"
                "with_the_last_cutoff_valid_prior_active_target_reconstructed_from_"
                "the_same_stable_institution_security_currency_share_basis_and_"
                "horizon_lineage;any_unproved_equivalence_mixed_pair_or_gap_is_REFUSED"
            ),
            "provider_previous_target_policy": (
                "provider_previous_price_target_and_previous_adjusted_price_target_"
                "are_audit_comparators_only_and_never_replace_the_reconstructed_prior_"
                "active_lineage_state"
            ),
            "restatement_policy": (
                "later_provider_restatement_cannot_rewrite_an_earlier_cutoff_state;"
                "each_value_uses_its_own_version_available_at"
            ),
            "pre_event_price_policy": (
                "for_a_precisely_timed_event_use_the_finite_positive_official_"
                "unadjusted_primary_listing_close_of_the_immediately_preceding_"
                "completed_exchange_session_whose_close_is_strictly_before_"
                "information_time;for_a_date_only_event_use_the_official_close_of_"
                "the_exchange_session_immediately_before_the_event_calendar_date;"
                "transform_only_to_the_event_common_share_basis_with_split_evidence_"
                "effective_and_available_before_information_time;intraday_current_"
                "ticker_and_vendor_adjusted_history_fallbacks_are_prohibited;missing_"
                "stale_nonpositive_or_ambiguous_price_or_split_lineage_is_REFUSED"
            ),
            "permanent_security_identity_required": True,
            "current_ticker_join_prohibited": True,
            "structural_source_bindings": {
                "security_master_id": None,
                "security_master_sha256": None,
                "corporate_action_source_id": None,
                "corporate_action_source_sha256": None,
                "fx_source_id": None,
                "fx_source_sha256": None,
                "adr_source_id": None,
                "adr_source_sha256": None,
                "target_horizon_evidence_id": None,
                "target_horizon_evidence_sha256": None,
                "price_adv_source_id": None,
                "price_adv_source_sha256": None,
            },
        },
        "universe_contract": {
            "point_in_time": True,
            "primary_listing_required": True,
            "listing_venues": ["XASE", "XNAS", "XNYS"],
            "eligible_instrument_types": ["common_stock", "adr"],
            "adr_requires_complete_basis_contract": True,
            "excluded_instrument_types": [
                "bdc",
                "closed_end_fund",
                "etf",
                "foreign_ordinary_without_adr_contract",
                "limited_partnership",
                "preferred_stock",
                "reit",
                "right",
                "trust",
                "unit",
                "warrant",
            ],
            "include_delisted": True,
            "current_ticker_joins": False,
            "unknown_identity": "REFUSED",
            "classification": "point_in_time_industry_and_sector",
            "normalization_hierarchy": ["industry", "sector", "REFUSED"],
            "market_fallback": False,
            "price_liquidity_capacity_screen_values": None,
        },
        "primary_event_formula": {
            "primary_cell_id": PRIMARY_CELL_ID,
            "delta": "(new_target-prior_target)/pre_event_split_consistent_stock_price",
            "direction": "signed_raise_positive_cut_negative",
            "finite_positive_prior_new_and_price_required": True,
            "event_clip_absolute": None,
            "event_clip_symbol": "CLIP_TPR0",
            "clip_is_source_repair": False,
            "log_target_change": "robustness_diagnostic_never_rescue",
        },
        "decay_contract": {
            "age_unit": "exchange_sessions_from_eligible_open_to_decision_session",
            "same_session_age": 0,
            "formula": "2**(-age_sessions/20)",
            "half_life_exchange_sessions": 20,
            "truncate_after_exchange_sessions": 80,
            "age_80_included": True,
            "age_above_80": "expired_zero_weight_preserve_event_disposition",
            "expiry_changes_raw_event_disposition": False,
        },
        "independence_contract": {
            "maximum_unit": "one_institution_security_session_catalyst_contribution",
            "stable_institution_identity": {
                "canonical_key": (
                    "benzinga_firm_id_mapped_through_the_reviewed_point_in_time_"
                    "institution_identity_alias_audit"
                ),
                "required_child_bindings": [
                    "institution_identity_alias_audit",
                    "institution_master_id",
                    "institution_master_sha256",
                ],
                "availability": (
                    "identity_alias_merger_and_successor_evidence_must_be_effective_"
                    "and_available_no_later_than_the_decision_cutoff"
                ),
                "raw_firm_label_role": "audit_only_never_identity_or_join_key",
                "current_name_join": "PROHIBITED",
                "missing_provider_firm_id": "REFUSED",
                "missing_or_ambiguous_alias_lineage": "REFUSED",
                "provider_id_collision_or_concurrent_many_to_one": "REFUSED",
                "successor_mapping": (
                    "only_when_the_reviewed_audit_proves_the_legal_successor_"
                    "relationship_and_its_cutoff_valid_effective_time_else_keep_"
                    "historical_institutions_distinct"
                ),
            },
            "within_unit_reconciliation": (
                "latest_cutoff_valid_versions_then_median_of_distinct_lineages"
            ),
            "institution_strength": (
                "stock_strength=median_across_the_one_reconciled_cutoff_valid_"
                "clipped_and_decayed_contribution_per_stable_institution"
            ),
            "effective_n_formula": (
                "square(sum(abs(values)))/sum(square(values))"
            ),
            "effective_n_zero_denominator": (
                "all_zero_contributions_yield_named_effective_count_zero_"
                "never_NaN_and_never_epsilon"
            ),
            "institution_effective_n": "N_eff_institution_contributions",
            "catalyst_contribution": "sum_institution_contributions_within_catalyst",
            "catalyst_effective_n": "N_eff_catalyst_contributions",
            "independent_breadth": "min_institution_effective_n_and_catalyst_effective_n",
            "unknown_catalyst_policy": (
                "one_conservative_cluster_per_security_and_eligible_session"
            ),
            "raw_event_analyst_and_burst_counts": "diagnostic_not_independent_breadth",
            "reliability_is_confidence": False,
            "reliability_applied_to_primary_rank": False,
        },
        "normalization_contract": {
            "population": "complete_eligible_point_in_time_decision_cross_section",
            "group_hierarchy": ["industry", "sector", "REFUSED"],
            "center": "median",
            "dispersion": "1.4826_times_median_absolute_deviation",
            "epsilon_denominator": False,
            "structural_valid_zero_included": True,
            "minimum_total_group_names": None,
            "minimum_active_group_names": None,
            "sparse_group": "REFUSED",
            "zero_or_nonfinite_mad": "REFUSED",
            "fallback_eligibility_outcome_free": True,
        },
        "controls_contract": {
            "information_cutoff": (
                "18:00:00_America/New_York_on_the_prior_exchange_session"
            ),
            "missing_control_policy": (
                "refuse_security_before_cross_section_except_the_explicit_"
                "NO_ACCEPTED_RATING_EVENT_state_after_complete_rating_inventory_proof"
            ),
            "continuous_controls": [
                "prior_total_return_5_sessions",
                "prior_total_return_20_sessions",
                "prior_total_return_60_sessions",
                "log_point_in_time_market_cap",
                "log_point_in_time_adv_20_sessions",
                "realized_volatility_20_sessions",
            ],
            "categorical_controls": [
                "hierarchical_normalization_group",
                "rating_action_20_session_state",
                "earnings_or_guidance_common_catalyst",
            ],
            "as_of_endpoints": {
                "prior_total_return_5_sessions": (
                    "split_and_dividend_consistent_total_return_index_at_close_S[-1]_"
                    "divided_by_index_at_close_S[-6]_minus_one"
                ),
                "prior_total_return_20_sessions": (
                    "split_and_dividend_consistent_total_return_index_at_close_S[-1]_"
                    "divided_by_index_at_close_S[-21]_minus_one"
                ),
                "prior_total_return_60_sessions": (
                    "split_and_dividend_consistent_total_return_index_at_close_S[-1]_"
                    "divided_by_index_at_close_S[-61]_minus_one"
                ),
                "log_point_in_time_market_cap": (
                    "natural_log_of_finite_positive_unadjusted_close_S[-1]_times_"
                    "latest_point_in_time_shares_outstanding_effective_no_later_than_"
                    "S[-1]_and_available_no_later_than_cutoff"
                ),
                "log_point_in_time_adv_20_sessions": (
                    "natural_log_of_arithmetic_mean_split_consistent_close_times_"
                    "volume_for_complete_sessions_S[-20]_through_S[-1]"
                ),
                "realized_volatility_20_sessions": (
                    "sample_standard_deviation_of_the_20_finite_close_to_close_log_"
                    "total_returns_from_S[-21]_through_S[-1]_without_annualization"
                ),
                "hierarchical_normalization_group": (
                    "the_same_cutoff_valid_PIT_industry_used_for_normalization_when_"
                    "its_bound_group_rules_pass_else_the_cutoff_valid_PIT_sector_"
                    "fallback_when_its_rules_pass_else_REFUSED;classification_"
                    "effective_on_decision_session_and_available_by_cutoff"
                ),
                "rating_action_20_session_state": (
                    "exact_state_of_the_latest_cutoff_valid_accepted_rating_event_"
                    "whose_eligible_open_is_in_S[-20]_through_S[-1]_ordered_by_"
                    "eligible_open_then_version_available_at_then_stable_event_id;"
                    "if_a_complete_admitted_rating_inventory_proves_none_use_"
                    "NO_ACCEPTED_RATING_EVENT_otherwise_REFUSED"
                ),
                "earnings_or_guidance_common_catalyst": (
                    "COMMON_CATALYST_PRESENT_or_NO_COMMON_CATALYST_from_the_reviewed_"
                    "stable_catalyst_inventory_effective_for_the_target_event_and_"
                    "available_by_cutoff;unknown_or_incomplete_inventory_REFUSED"
                ),
            },
            "rating_no_event_state": "NO_ACCEPTED_RATING_EVENT",
            "rating_no_event_is_generic_missing": False,
            "target_primary_sample_filtered_by_rating_availability": False,
            "eligible_open_gap_is_a_pre_rank_control": False,
            "simultaneous_nested_industry_sector_dummies": False,
            "classification_control_count": 1,
            "continuous_scaling": (
                "separately_for_each_decision_session_and_continuous_control_"
                "z=(x-median(x))/(Decimal_1.4826*median(abs(x-median(x))))_over_"
                "the_identical_complete_eligible_rows"
            ),
            "continuous_zero_or_nonfinite_mad": "decision_session_REFUSED",
            "categorical_encoding": (
                "deterministic_one_hot_per_categorical_control_drop_each_"
                "lexicographically_first_UTF8_level_with_no_interactions"
            ),
        },
        "estimator_contract": {
            "pre_rank_residualization": (
                "within_decision_session_ols_of_normalized_target_score_on_exact_controls"
            ),
            "solver": (
                "deterministic_column_order_intercept_then_continuous_then_"
                "categorical_UTF8_levels;convert_each_finite_canonical_Decimal_"
                "design_and_response_value_to_its_exact_rational;solve_X_transpose_"
                "X_beta_equals_X_transpose_y_by_fraction_free_Gaussian_elimination_"
                "with_the_first_nonzero_pivot_in_column_order;exact_zero_pivot_or_"
                "singular_design_REFUSED_without_tolerance_or_regularization"
            ),
            "numeric_and_rank_arithmetic": (
                "OLS_coefficients_residuals_and_tie_comparisons_are_exact_rationals;"
                "average_tie_ranks_and_fractional_percentiles_are_exact_rationals;"
                "binary_float_approximate_ties_epsilon_ridge_and_pseudoinverse_are_"
                "PROHIBITED"
            ),
            "classification_design": (
                "one_hierarchical_normalization_group_dummy_set_never_simultaneous_"
                "nested_industry_and_sector_dummies"
            ),
            "rank_input": "control_residual",
            "rank_population": "identical_complete_eligible_observations",
            "rank_method": "deterministic_fractional_rank_average_ties",
            "primary_estimand": (
                "mean_weekly_equal_weight_top_quintile_minus_bottom_quintile_"
                "net_20_session_open_to_open_return"
            ),
            "quintiles": 5,
            "security_positions_overlap_within_leg": False,
            "temporal_inference": (
                "moving_block_bootstrap_over_decision_sessions_block_four_weeks"
            ),
            "bootstrap_resamples": 10000,
            "bootstrap_seed": (
                "sha256(parent_spec_hash+colon+structural_binding_sha256+colon+"
                "tpr-look-stock-primary-001+colon+studentized-mbb-v1)"
            ),
            "panel_dependence_check": (
                "two_way_cluster_by_decision_session_and_permanent_security_id"
            ),
            "positive_direction_required": True,
        },
        "decision_outcome_contract": {
            "decision_frequency": "weekly_first_eligible_exchange_session",
            "outcome_horizon_exchange_sessions": 20,
            "entry": "next_eligible_open",
            "exit": "open_after_20_exchange_sessions",
            "terminal_outcomes_required": True,
            "missing_terminal_return": "REFUSED_never_drop",
            "gross_and_net_cost_outputs_required": True,
            "primary_comparison": "top_minus_bottom_score_quintile",
        },
        "walk_forward_contract": {
            "development_start": None,
            "development_start_binding_algorithm": (
                "earliest_exchange_session_for_which_reviewed_TPR1_TPR2_manifests_"
                "prove_complete_admitted_point_in_time_coverage_for_source_identity_"
                "basis_controls_and_cost_inputs_without_target_aligned_outcomes"
            ),
            "development_end": "2026-08-31",
            "prospective_validation_start": "2026-09-01",
            "prospective_validation_end": "2027-08-31",
            "shared_holdout_start": "2027-09-01",
            "shared_holdout_end": "2029-08-31",
            "fold_policy": (
                "expanding_training_window_with_chronological_nonoverlapping_test_"
                "folds_whose_boundaries_are_bound_from_complete_structural_coverage"
            ),
            "training_choice_policy": (
                "all_choices_fixed_before_target_aligned_outcomes_and_each_fit_uses_"
                "only_sessions_strictly_before_its_test_fold"
            ),
            "purge_groups": [
                "decision_session",
                "permanent_security_id",
                "common_catalyst_id",
            ],
            "embargo_exchange_sessions": 20,
            "one_shot_prospective_validation": True,
            "shared_holdout_access": "PROHIBITED",
        },
        "cost_contract": {
            "units": "dollars_then_divide_once_by_nav",
            "position_change_basis": "net_change_in_shares_and_notional",
            "formula_components": [
                "commission",
                "half_spread",
                "square_root_impact_using_point_in_time_adv",
                "opening_auction_gap_and_slippage",
                "rejection_and_unfilled_behavior",
            ],
            "formula": (
                "abs_delta_shares*commission_per_share+"
                "abs_delta_notional*half_spread_fraction+"
                "abs_delta_notional*impact_coefficient*"
                "sqrt(abs_delta_notional/adv_dollars)+"
                "auction_gap_slippage_dollars+rejection_unfilled_penalty_dollars"
            ),
            "missing_adv_new_or_increasing_exposure": "REFUSED",
            "risk_reducing_exit_policy": "conservative_cost_fallback_must_not_block_exit",
            "diagnostic_bps_per_side": ["0", "5", "10", "20"],
            "canonical_commission_per_share": None,
            "canonical_half_spread_fraction": None,
            "canonical_impact_coefficient": None,
            "canonical_participation_cap": None,
            "canonical_auction_gap_rule": None,
        },
        "empirical_binding_contract": {
            "state": "required_unbound_zero_outcome",
            "child_schema": STRUCTURAL_BINDING_SCHEMA,
            "bind_after_reviewed_milestones": ["TPR-1", "TPR-2"],
            "bind_before": [
                "TPR-3_canonical_score_publication",
                "any_target_aligned_outcome_access",
            ],
            "required_parent_fields_immutable": True,
            "required_bindings": {
                "structural_input_manifest_sha256": None,
                "source_history_schema_audit": None,
                "vendor_adjustment_restatement_audit": None,
                "institution_identity_alias_audit": None,
                "institution_master_id": None,
                "institution_master_sha256": None,
                "event_clip_absolute": None,
                "event_clip_resolution_and_stability_rule": None,
                "minimum_total_group_names": None,
                "minimum_active_group_names": None,
                "price_liquidity_capacity_screen_values": None,
                "group_and_universe_binding_rule": None,
                "frozen_research_capacity_notional": None,
                "canonical_commission_per_share": None,
                "canonical_half_spread_fraction": None,
                "canonical_impact_coefficient": None,
                "canonical_participation_cap": None,
                "canonical_auction_gap_rule": None,
                "cost_coverage_and_stability_rule": None,
                "earliest_complete_pit_development_session": None,
                "reliability_thresholds": None,
                "reliability_threshold_rule": None,
                "unconditional_return_sigma": None,
                "planning_weekly_decision_session_count": None,
                "planning_event_frequency_lower_bound": None,
                "planning_event_frequency_rule": None,
                "planning_eligible_decision_sessions": None,
                "planning_design_effect": None,
                "planning_effective_n": None,
                "planning_mde_net_return": None,
                "round_trip_cost_p95_at_frozen_capacity": None,
                "practical_effect_threshold_net_return": None,
                "required_effective_decision_sessions": None,
                "required_calendar_decision_sessions": None,
                "actual_structurally_eligible_decision_sessions": None,
                "actual_structurally_eligible_effective_n": None,
                "chronological_fold_boundaries": None,
                "chronological_fold_stability_rule": None,
                "power_structural_coverage_rule": None,
            },
            "structural_common_contract": {
                "input": "complete_content_addressed_reviewed_TPR1_TPR2_rows_only",
                "window_start": "earliest_complete_pit_development_session_binding",
                "window_end": "2026-08-31",
                "canonical_sort": (
                    "decision_session_permanent_security_id_stable_event_lineage_id_"
                    "version_available_at_raw_locator_UTF8_then_numeric_ascending"
                ),
                "arithmetic": "exact_finite_Decimal_no_binary_float_no_epsilon",
                "quantile": (
                    "Hyndman_Fan_type_7_on_sorted_finite_Decimals_with_exact_linear_"
                    "interpolation"
                ),
                "chronological_halves": (
                    "split_at_the_session_midpoint_earlier_half_gets_the_extra_session"
                ),
                "deterministic_seed": (
                    "sha256(parent_spec_hash+colon+structural_input_manifest_sha256+"
                    "colon+binding_name);counter_draw_k_is_sha256(seed+colon+k)"
                ),
                "prohibited_inputs": [
                    "target_aligned_returns",
                    "candidate_formula_ranks",
                    "performance_selection",
                    "reserved_holdout",
                ],
                "refusal": (
                    "any_incomplete_manifest_nonfinite_required_value_coverage_failure_"
                    "or_failed_frozen_stability_gate_REFUSED_never_relax_or_impute"
                ),
            },
            "event_clip_algorithm": {
                "sample": (
                    "all_admitted_signed_price_scaled_revisions_after_only_reviewed_"
                    "documented_structural_source_error_exclusions"
                ),
                "formula": (
                    "max(abs(type7_q0.005_signed),abs(type7_q0.995_signed))"
                ),
                "required_result": "finite_positive_Decimal",
                "stability": (
                    "apply_the_exact_independently_reviewed_child_binding_"
                    "event_clip_resolution_and_stability_rule_to_full_and_"
                    "chronological_half_samples;rule_must_bind_tail_resolution_"
                    "coverage_and_instability_refusal_without_outcomes"
                ),
                "source_repair": False,
            },
            "group_and_universe_algorithm": {
                "binding_rule": (
                    "exact_independently_reviewed_group_and_universe_binding_rule_"
                    "from_the_structural_child"
                ),
                "candidate_evidence": (
                    "complete_PIT_price_ADV20_spread_auction_capacity_classification_"
                    "and_control_design_coverage_curves_over_the_common_window"
                ),
                "screen_values": (
                    "bind_price_liquidity_and_capacity_thresholds_only_after_the_"
                    "child_rule_pins_exact_order_statistics_coverage_requirements_"
                    "tie_handling_and_instability_refusal"
                ),
                "capacity": (
                    "bind_the_largest_research_notional_supported_under_the_child_"
                    "screen_rule_and_bound_participation_cap_on_every_required_"
                    "structural_coverage_cohort"
                ),
                "minimum_total_group_names": (
                    "bind_from_the_child_rule_using_full_rank_control_design_dimension_"
                    "and_complete_PIT_group_coverage"
                ),
                "minimum_active_group_names": (
                    "bind_from_the_same_child_rule_and_complete_nonzero_signal_"
                    "availability_without_target_aligned_returns"
                ),
                "hierarchy": (
                    "industry_if_both_minima_and_finite_positive_MAD_pass_else_sector_"
                    "if_the_same_rules_pass_else_REFUSED_never_market_or_epsilon"
                ),
                "stability": (
                    "child_rule_must_pin_deterministic_full_versus_chronological_half_"
                    "coverage_and_threshold_instability_refusal"
                ),
            },
            "cost_parameter_algorithm": {
                "window": "structural_common_window_never_target_event_aligned",
                "commission": (
                    "maximum_applicable_documented_per_share_commission_and_fee_"
                    "schedule_over_the_frozen_research_capacity"
                ),
                "half_spread": (
                    "bind_a_conservative_finite_nonnegative_measure_under_the_exact_"
                    "reviewed_child_cost_coverage_and_stability_rule"
                ),
                "impact": (
                    "bind_a_conservative_finite_nonnegative_square_root_impact_"
                    "coefficient_under_the_exact_reviewed_child_rule"
                ),
                "participation_cap": (
                    "bind_a_conservative_cap_from_reviewed_ADV_and_opening_auction_"
                    "capacity_evidence_under_the_exact_reviewed_child_rule"
                ),
                "auction_and_rejection_rule": (
                    "bind_open_gap_slippage_rejection_and_unfilled_behavior_under_"
                    "the_exact_reviewed_child_rule_with_risk_exit_fallback"
                ),
                "coverage_and_stability": (
                    "the_child_cost_coverage_and_stability_rule_must_pin_each_"
                    "component_window_estimator_resolution_coverage_half_sample_"
                    "instability_threshold_and_refusal"
                ),
                "round_trip_cost_p95": (
                    "type7_q0.95_of_the_complete_frozen_cost_formula_evaluated_at_"
                    "frozen_capacity_without_target_events_or_returns"
                ),
            },
            "reliability_binding_algorithm": {
                "components": [
                    "source_precision",
                    "independent_breadth",
                    "concentration",
                    "latency",
                    "observed_feature_weight",
                ],
                "thresholds": (
                    "bind_only_from_the_exact_independently_reviewed_child_"
                    "reliability_threshold_rule_which_pins_component_estimators_"
                    "knots_coverage_ties_and_instability_refusal"
                ),
                "benefit_components": [
                    "source_precision",
                    "independent_breadth",
                    "observed_feature_weight",
                ],
                "harm_components": ["concentration", "latency"],
                "component_quality": (
                    "the_bound_child_rule_must_be_bounded_and_monotone_"
                    "nondecreasing_in_each_benefit_component_and_nonincreasing_in_"
                    "each_harm_component"
                ),
                "combined_quality": (
                    "exact_bounded_monotone_combiner_bound_by_the_reviewed_child_rule"
                ),
                "bounds": "closed_interval_zero_to_one",
                "stability": (
                    "child_rule_must_pin_deterministic_full_versus_chronological_"
                    "half_coverage_and_distribution_instability_refusal"
                ),
                "hard_invalidity_override": False,
                "name_confidence_prohibited": True,
                "primary_rank_effect": False,
            },
            "power_and_effect_algorithm": {
                "prospective_calendar": (
                    "all_first_eligible_exchange_sessions_of_each_exchange_week_from_"
                    "2026-09-01_through_2027-08-31_from_the_reviewed_calendar"
                ),
                "planning_event_frequency": (
                    "apply_the_exact_independently_reviewed_child_planning_event_"
                    "frequency_rule_to_complete_development_weeks_with_or_without_"
                    "a_structurally_admitted_target_revision"
                ),
                "planning_eligible_dates": (
                    "floor(planning_calendar_dates_times_planning_event_frequency_"
                    "lower_bound)_independent_of_actual_prospective_eligible_count"
                ),
                "overlap_factor": (
                    "mean_concurrent_20_exchange_session_windows_on_the_complete_"
                    "planning_calendar_never_target_aligned_returns"
                ),
                "security_factor": (
                    "sum(square(security_cluster_sizes))/sum(security_cluster_sizes)_"
                    "where_sizes_count_complete_zero_outcome_structurally_admitted_"
                    "incidences_sharing_permanent_security_id"
                ),
                "catalyst_factor": (
                    "sum(square(catalyst_cluster_sizes))/sum(catalyst_cluster_sizes)_"
                    "where_sizes_count_complete_zero_outcome_structurally_admitted_"
                    "incidences_sharing_common_catalyst_id"
                ),
                "block_factor": "Decimal_4_for_frozen_four_week_inference_block",
                "design_effect": (
                    "max(1,overlap_factor,block_factor)*max(1,security_factor)*max(1,"
                    "catalyst_factor)_as_the_conservative_joint_temporal_security_"
                    "and_catalyst_full_dependence_upper_bound"
                ),
                "planning_effective_n": (
                    "floor(planning_eligible_dates_divided_by_design_effect)"
                ),
                "sigma": (
                    "sample_standard_deviation_of_complete_unconditional_security_"
                    "20_session_open_to_open_returns_not_joined_to_target_events"
                ),
                "planning_mde": (
                    "(normal_quantile_0.99375+normal_quantile_0.80)*sigma_divided_by_"
                    "sqrt(planning_effective_n)"
                ),
                "cost_p95": (
                    "type7_q0.95_measured_round_trip_cost_at_frozen_capacity"
                ),
                "practical_effect": "max(2_times_cost_p95,planning_mde)",
                "required_effective_n": (
                    "ceiling(((normal_quantile_0.99375+normal_quantile_0.80)*sigma_"
                    "divided_by_practical_effect)**2)"
                ),
                "required_calendar_n": (
                    "ceiling(required_effective_n_times_design_effect)"
                ),
                "separate_actual_sufficiency": (
                    "count_actual_structurally_eligible_prospective_weekly_dates_only_"
                    "after_all_nonoutcome_contracts_are_fixed_then_require_both_"
                    "actual_calendar_n_at_least_required_calendar_n_and_floor(actual_"
                    "calendar_n_divided_by_design_effect)_at_least_required_effective_n"
                ),
                "coverage_and_stability": (
                    "the_child_power_structural_coverage_rule_must_pin_unconditional_"
                    "return_and_cluster_coverage_resolution_stability_and_refusal"
                ),
                "child_recomputation": (
                    "the_TPR0B_loader_must_recompute_and_exactly_match_each_calendar_"
                    "frequency_design_effect_effective_n_sigma_MDE_cost_practical_"
                    "effect_required_n_and_actual_sufficiency_field_else_REFUSED"
                ),
            },
            "power": "0.80",
            "assigned_alpha": "0.0125",
            "outcome_join_prohibited": True,
            "independent_review_required": True,
        },
        "trial_and_null_contract": {
            "primary_cell_id": PRIMARY_CELL_ID,
            "primary_look_id": PRIMARY_LOOK_ID,
            "primary_acceptance_contract": {
                "null_hypothesis": (
                    "mean_weekly_net_top_minus_bottom_20_session_return_equals_zero"
                ),
                "alternative_hypothesis": (
                    "mean_weekly_net_top_minus_bottom_20_session_return_not_equal_zero"
                ),
                "two_sided_alpha": "0.0125",
                "positive_direction_required": True,
                "leg_membership": {
                    "rank": (
                        "average_one_based_rank_for_exact_ties_then_fractional_"
                        "percentile=(average_rank-Decimal_0.5)/eligible_name_count"
                    ),
                    "bottom": "fractional_percentile_less_than_Decimal_0.20",
                    "top": "fractional_percentile_at_least_Decimal_0.80",
                    "boundary_ties": (
                        "one_shared_average_rank_places_the_entire_tie_group_by_the_"
                        "same_strict_bottom_or_inclusive_top_rule_never_split"
                    ),
                    "weights": (
                        "equal_weight_1_over_leg_name_count_separately_within_each_leg"
                    ),
                    "weekly_spread": (
                        "mean_top_net_return_minus_mean_bottom_net_return"
                    ),
                    "empty_leg": "INSUFFICIENT",
                },
                "primary_bootstrap": {
                    "method": (
                        "studentized_null_centered_circular_moving_block_bootstrap_"
                        "over_chronological_weekly_spreads"
                    ),
                    "block_length_weeks": 4,
                    "resamples": 10000,
                    "observed_statistics": (
                        "for_chronological_weekly_spreads_x_0_through_x_n_minus_1_"
                        "with_n_at_least_2_observed_mean=sum(x_d)/n;observed_"
                        "studentizer=sample_standard_deviation_denominator_n_minus_"
                        "1_divided_by_sqrt(n);observed_t=observed_mean_divided_by_"
                        "observed_studentizer"
                    ),
                    "null_centering": (
                        "centered_x_d=x_d_minus_observed_mean_exactly_before_any_"
                        "resampling"
                    ),
                    "seed": (
                        "lowercase_hex_sha256_of_UTF8(parent_spec_hash+colon+"
                        "structural_binding_sha256+colon+tpr-look-stock-primary-001+"
                        "colon+studentized-mbb-v1)"
                    ),
                    "block_start_draw": (
                        "for_zero_based_resample_r_0_through_9999_and_zero_based_"
                        "block_b_0_through_ceiling(n/4)_minus_1_hash_UTF8(seed_"
                        "lowercase_hex+colon+ASCII_decimal_r_no_leading_zeros+colon+"
                        "ASCII_decimal_b_no_leading_zeros);start=unsigned_big_endian_"
                        "integer_of_the_first_16_raw_digest_bytes_modulo_n;append_"
                        "centered_x_at_(start+j)_mod_n_for_j_0_through_3_and_truncate_"
                        "the_concatenation_to_the_first_n_values"
                    ),
                    "replicate_studentizer": (
                        "sample_standard_deviation_of_the_n_resampled_centered_values_"
                        "with_denominator_n_minus_1_divided_by_sqrt(n)"
                    ),
                    "replicate_t": (
                        "mean_of_resampled_null_centered_spreads_divided_by_its_"
                        "studentizer"
                    ),
                    "p_value": (
                        "(1+count(abs(replicate_t)>=abs(observed_t)))/(10000+1)"
                    ),
                    "pass": (
                        "p_value_less_than_or_equal_to_Decimal_0.0125_and_observed_"
                        "mean_strictly_positive"
                    ),
                    "confidence_interval": (
                        "two_sided_98.75_percent_studentized_bootstrap_t_interval_"
                        "from_the_same_10000_ordered_extended_real_replicate_t_values:"
                        "qlo=type7_q0.00625_and_qhi=type7_q0.99375_then_interval_"
                        "[observed_mean-qhi*observed_studentizer,observed_mean-qlo*"
                        "observed_studentizer];a_type7_bracket_touching_one_signed_"
                        "infinity_produces_the_corresponding_unbounded_endpoint_and_"
                        "a_bracket_spanning_both_infinities_is_reported_CI_UNAVAILABLE;"
                        "report_both_bounds_or_unavailability_with_the_primary_result_"
                        "but_never_use_the_interval_as_an_additional_gate"
                    ),
                    "zero_edge": (
                        "all_observed_spreads_exact_zero_gives_p_1_interval_[0,0]_"
                        "and_VALID_NULL_only_after_all_earlier_disposition_gates;"
                        "constant_nonzero_observed_spreads_or_n_less_"
                        "than_2_are_INSUFFICIENT;replicate_zero_studentizer_and_zero_"
                        "mean_gives_t_0;replicate_zero_studentizer_and_nonzero_mean_"
                        "gives_signed_infinity_which_remains_in_the_p_value_and_CI_"
                        "replicate_inventory"
                    ),
                },
                "two_way_cluster_cross_check": {
                    "support": (
                        "only_one_complete_admitted_top_or_bottom_leg_row_per_"
                        "decision_session_and_permanent_security_id;middle_rows_"
                        "are_excluded;duplicates_missing_"
                        "terminal_returns_or_nonfinite_values_are_INVALID_DATA"
                    ),
                    "counts": (
                        "D=number_of_unique_decision_sessions;S=number_of_unique_"
                        "permanent_security_ids;N=number_of_unique_date_security_"
                        "rows;n_d=number_of_rows_on_date_d"
                    ),
                    "row_contribution": (
                        "z_di=net_return_di/top_leg_count_d_for_top_rows_and_minus_"
                        "net_return_di/bottom_leg_count_d_for_bottom_rows;weekly_"
                        "spread_x_d=sum_i(z_di);full_mean=m=sum_d(x_d)/D"
                    ),
                    "row_influence": (
                        "g_di=(z_di-m/n_d)/D_so_sum_over_all_rows_is_exactly_zero"
                    ),
                    "clusters": ["decision_session", "permanent_security_id"],
                    "variance": (
                        "V=max(0,D/(D-1)*sum_d(square(sum_i(g_di)))+S/(S-1)*sum_s("
                        "square(sum_rows_for_s(g_di)))-N/(N-1)*sum_di(square(g_di)))"
                    ),
                    "degrees_of_freedom": "min(D-1,S-1)",
                    "p_value": (
                        "2*(1-Student_t_CDF(abs(m/sqrt(V)),degrees_of_freedom))"
                    ),
                    "minimum_dimensions": (
                        "D_at_least_2_and_S_at_least_2_and_N_at_least_2_else_"
                        "INSUFFICIENT"
                    ),
                    "zero_edge": (
                        "zero_mean_and_zero_variance_gives_p_1;positive_or_negative_"
                        "nonzero_mean_with_zero_variance_is_INSUFFICIENT"
                    ),
                    "pass": "two_sided_p_not_greater_than_0.0125_and_mean_positive",
                },
                "chronological_fold_stability": {
                    "rule_binding": (
                        "exact_independently_reviewed_chronological_fold_stability_"
                        "rule_from_the_structural_child"
                    ),
                    "assignment": (
                        "sort_structurally_admitted_decision_sessions_ascending_then_"
                        "apply_the_bound_child_rule_and_bind_exact_nonoverlapping_"
                        "session_boundaries_before_outcomes"
                    ),
                    "sufficiency": (
                        "apply_the_bound_child_minimum_fold_and_per_fold_session_rule_"
                        "else_INSUFFICIENT"
                    ),
                    "pass": (
                        "mean_weekly_net_spread_strictly_positive_in_every_bound_fold"
                    ),
                    "nonpass": "VALID_NULL",
                },
                "economic_gate": (
                    "full_sample_mean_net_spread_at_least_practical_effect_threshold_"
                    "net_return"
                ),
                "disposition_precedence": [
                    "UNAUTHORIZED_if_any_required_authority_is_absent",
                    "INVALID_IMPLEMENTATION_if_identity_parity_or_algorithm_fails",
                    "INVALID_DATA_if_admitted_data_basis_or_terminal_integrity_fails",
                    "INSUFFICIENT_if_structural_power_empty_leg_fold_minimum_cluster_"
                    "dimension_n_less_than_2_or_nonzero_degenerate_inference_"
                    "sufficiency_fails",
                    "VALID_PASS_only_if_positive_bootstrap_cluster_economic_and_all_"
                    "fold_gates_pass",
                    "VALID_NULL_for_every_other_valid_statistical_economic_sign_or_"
                    "stability_nonpass_and_close_family",
                ],
            },
            "secondary_experiment_ids": [
                "tpr-diagnostic-log-target-change",
                "tpr-diagnostic-static-target-upside",
                "tpr-secondary-paired-consensus-change",
                "tpr-secondary-consensus-novelty",
                "tpr-secondary-unexpected-revision-residual",
                "tpr-deferred-rating-interaction",
            ],
            "secondary_outcome_access": "UNAUTHORIZED",
            "secondary_or_etf_rescue": False,
            "valid_null_closes_family": True,
            "invalid_data_or_implementation": (
                "repair_exact_defect_under_review_without_unregistered_new_hypothesis"
            ),
            "insufficient": "wait_for_legitimate_data_never_loosen_after_looking",
            "unauthorized": "do_not_run",
            "dispositions": [
                "VALID_PASS",
                "VALID_NULL",
                "INVALID_DATA",
                "INVALID_IMPLEMENTATION",
                "INSUFFICIENT",
                "UNAUTHORIZED",
            ],
        },
        "legacy_separation_contract": {
            "rating_family_is_target_ground_truth": False,
            "rating_events_relabelled_as_target_events": False,
            "legacy_price_target_data_is_authority": False,
            "legacy_or_analyst_evidence_epoch_reuse": False,
            "cross_strategy_imports": "PROHIBITED",
            "provider_outcome_backtest_qc_broker_imports": "PROHIBITED",
        },
    }
)

_EMPIRICAL_CELL_IDS = frozenset({"empirical_binding_contract"})
_REQUIRED_EMPIRICAL_BINDING_KEYS = tuple(
    _EXPECTED_VALUES["empirical_binding_contract"]["required_bindings"]
)
_EMPIRICAL_PENDING_BINDINGS = tuple(
    f"empirical.{key}" for key in _REQUIRED_EMPIRICAL_BINDING_KEYS
)
_PENDING_BINDINGS = (
    "independent_review_anchor",
    "tpr_structural_bindings_v1_child",
    "reviewed_TPR1_source_snapshot_and_rights",
    "reviewed_TPR2_identity_basis_controls_and_cost_inputs",
    *_EMPIRICAL_PENDING_BINDINGS,
    f"looks.{PRIMARY_LOOK_ID}.dataset_id",
    f"looks.{PRIMARY_LOOK_ID}.code_identity",
    f"looks.{PRIMARY_LOOK_ID}.structural_binding_id",
    f"looks.{PRIMARY_LOOK_ID}.structural_binding_sha256",
    "external_append_only_permanent_look_authority",
)
if (
    len(_EMPIRICAL_PENDING_BINDINGS) != len(set(_EMPIRICAL_PENDING_BINDINGS))
    or {
        value.removeprefix("empirical.") for value in _EMPIRICAL_PENDING_BINDINGS
    }
    != set(_REQUIRED_EMPIRICAL_BINDING_KEYS)
):
    raise RuntimeError("TPR pending bindings do not exactly cover required child keys")
if any(
    value is not None
    for value in _EXPECTED_VALUES["empirical_binding_contract"][
        "required_bindings"
    ].values()
):
    raise RuntimeError("TPR-0A empirical child values must remain exactly null")


@dataclasses.dataclass(frozen=True)
class PreregistrationCell:
    cell_id: str
    state: str
    value: object
    source: str


@dataclasses.dataclass(frozen=True)
class RegisteredLook:
    look_id: str
    family_id: str
    primary_cell_id: str
    state: str
    validation_start: str
    validation_end: str
    dataset_id: str | None
    code_identity: str | None
    structural_binding_id: str | None
    structural_binding_sha256: str | None
    cost_cell_hash: str


@dataclasses.dataclass(frozen=True)
class AlgorithmCandidate:
    status: str
    spec_id: str
    spec_hash: str
    cells: tuple[PreregistrationCell, ...]
    looks: tuple[RegisteredLook, ...]
    unresolved_owner_decisions: tuple[str, ...]
    pending_bindings: tuple[str, ...]

    def cell(self, cell_id: str) -> object:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                return cell.value
        raise PreregistrationError(f"required TPR-0A cell is absent: {cell_id}")


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedAlgorithmSpec:
    status: str
    spec_id: str
    spec_hash: str
    producing_commit: str
    reviewed_by: str
    reviewed_at: str
    cells: tuple[PreregistrationCell, ...]
    looks: tuple[RegisteredLook, ...]
    source_path: str
    artifact_sha256: str
    review_commit: str
    registry_anchor_commit: str
    signing_key_fingerprint: str
    _authority: object = dataclasses.field(repr=False, compare=False)

    def cell(self, cell_id: str) -> object:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                return cell.value
        raise PreregistrationError(f"required TPR-0A cell is absent: {cell_id}")


@dataclasses.dataclass(frozen=True)
class OutcomeAccessRequest:
    family_id: str
    look_id: str
    algorithm_spec_id: str
    algorithm_spec_hash: str
    structural_binding_id: str
    structural_binding_sha256: str
    dataset_id: str
    code_identity: str
    requested_start: str
    requested_end: str
    horizon_exchange_sessions: int
    assigned_alpha: str


@dataclasses.dataclass(frozen=True, init=False)
class OutcomeAccessPermit:
    """Uninstantiable public shape reserved for a future external authority."""

    permit_id: str
    authority_id: str
    request_sha256: str
    _authority: object = dataclasses.field(repr=False, compare=False)


_REVIEWED_AUTHORITY = object()
_REVIEWED_AUTHORITIES: dict[
    int,
    tuple[weakref.ReferenceType[ReviewedAlgorithmSpec], Path, tuple[object, ...]],
] = {}
_REVIEWED_AUTHORITIES_LOCK = threading.RLock()


def _translate(exc: Exception) -> PreregistrationError:
    return PreregistrationError(str(exc))


def _parse_root(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        payload = path.read_bytes()
        raw = require_canonical_json_bytes(payload, "TPR-0A preregistration")
        require_exact_keys(raw, _TOP_KEYS, "TPR-0A preregistration")
    except (OSError, CanonicalContractError) as exc:
        raise _translate(exc) from exc
    if raw["schema"] != ALGORITHM_SPEC_SCHEMA:
        raise PreregistrationError("TPR-0A preregistration schema is unsupported")
    return raw, payload


def _canonical_payload(raw: Mapping[str, object]) -> bytes:
    payload = dict(raw)
    payload["spec_id"] = None
    payload["spec_hash"] = None
    try:
        return canonical_json_bytes(payload)
    except CanonicalContractError as exc:
        raise _translate(exc) from exc


def derive_spec_hash(raw: Mapping[str, object]) -> str:
    """Derive the complete semantic hash with identity fields blanked."""
    return sha256_bytes(_canonical_payload(raw))


def _cell_hash(value: object) -> str:
    try:
        return sha256_bytes(canonical_json_bytes(value))
    except CanonicalContractError as exc:
        raise _translate(exc) from exc


def build_algorithm_candidate_bytes() -> bytes:
    """Reproduce the exact non-authoritative TPR-0A candidate artifact.

    Frozen mappings are materialized by ``canonical_json_bytes`` as JSON
    objects.  Keeping artifact construction beside the semantic pins prevents
    tuple-based comparison representations from leaking into persisted JSON.
    """
    raw: dict[str, object] = {
        "schema": ALGORITHM_SPEC_SCHEMA,
        "status": CANDIDATE_STATUS,
        "spec_id": None,
        "spec_hash": None,
        "producing_commit": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "cells": [
            {
                "cell_id": cell_id,
                "state": (
                    "frozen_algorithm_empirical_binding_required"
                    if cell_id in _EMPIRICAL_CELL_IDS
                    else "frozen"
                ),
                "value": _EXPECTED_VALUES[cell_id],
                "source": CELL_SOURCE,
            }
            for cell_id in REQUIRED_CELL_IDS
        ],
        "looks": [
            {
                "look_id": PRIMARY_LOOK_ID,
                "family_id": FAMILY_ID,
                "primary_cell_id": PRIMARY_CELL_ID,
                "state": "planned_unbound",
                "validation_start": "2026-09-01",
                "validation_end": "2027-08-31",
                "dataset_id": None,
                "code_identity": None,
                "structural_binding_id": None,
                "structural_binding_sha256": None,
                "cost_cell_hash": _cell_hash(_EXPECTED_VALUES["cost_contract"]),
            }
        ],
    }
    spec_hash = derive_spec_hash(raw)
    raw["spec_hash"] = spec_hash
    raw["spec_id"] = f"tpr-round0a-candidate-{spec_hash[:16]}"
    return canonical_json_bytes(raw, trailing_lf=True)


def _validate_cells(raw_cells: object) -> tuple[PreregistrationCell, ...]:
    if not isinstance(raw_cells, list) or len(raw_cells) != len(REQUIRED_CELL_IDS):
        raise PreregistrationError("TPR-0A must contain every required cell exactly once")
    cells: list[PreregistrationCell] = []
    for expected_id, item in zip(REQUIRED_CELL_IDS, raw_cells, strict=True):
        try:
            require_exact_keys(item, _CELL_KEYS, f"cell {expected_id}")
        except CanonicalContractError as exc:
            raise _translate(exc) from exc
        if item["cell_id"] != expected_id:
            raise PreregistrationError("TPR-0A cells must use canonical inventory order")
        expected_state = (
            "frozen_algorithm_empirical_binding_required"
            if expected_id in _EMPIRICAL_CELL_IDS
            else "frozen"
        )
        if item["state"] != expected_state:
            raise PreregistrationError(f"{expected_id} has an invalid freeze state")
        try:
            source = require_text(item["source"], f"{expected_id} source")
        except CanonicalContractError as exc:
            raise _translate(exc) from exc
        if source != CELL_SOURCE:
            raise PreregistrationError(
                f"{expected_id} source does not match the frozen owner/blueprint authority"
            )
        expected_value = _EXPECTED_VALUES[expected_id]
        try:
            values_match = canonical_json_bytes(item["value"]) == canonical_json_bytes(
                expected_value
            )
        except CanonicalContractError as exc:
            raise _translate(exc) from exc
        if not values_match:
            raise PreregistrationError(f"{expected_id} changed the frozen TPR-0A policy")
        cells.append(
            PreregistrationCell(
                cell_id=expected_id,
                state=expected_state,
                value=deep_freeze(item["value"]),
                source=source,
            )
        )
    return tuple(cells)


def _validate_looks(raw_looks: object) -> tuple[RegisteredLook, ...]:
    if not isinstance(raw_looks, list) or len(raw_looks) != 1:
        raise PreregistrationError("TPR-0A must register exactly one planned primary look")
    item = raw_looks[0]
    try:
        require_exact_keys(item, _LOOK_KEYS, "planned primary look")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        item["look_id"] != PRIMARY_LOOK_ID
        or item["family_id"] != FAMILY_ID
        or item["primary_cell_id"] != PRIMARY_CELL_ID
        or item["state"] != "planned_unbound"
        or item["validation_start"] != "2026-09-01"
        or item["validation_end"] != "2027-08-31"
    ):
        raise PreregistrationError("planned look changed the frozen family, cell, or period")
    for name in (
        "dataset_id",
        "code_identity",
        "structural_binding_id",
        "structural_binding_sha256",
    ):
        if item[name] is not None:
            raise PreregistrationError(
                "TPR-0A look must remain planned, structurally unbound, and non-executable"
            )
    try:
        cost_hash = require_sha256(item["cost_cell_hash"], "cost_cell_hash")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if cost_hash != _cell_hash(_EXPECTED_VALUES["cost_contract"]):
        raise PreregistrationError("planned look does not bind the frozen cost algorithm")
    return (
        RegisteredLook(
            look_id=PRIMARY_LOOK_ID,
            family_id=FAMILY_ID,
            primary_cell_id=PRIMARY_CELL_ID,
            state="planned_unbound",
            validation_start="2026-09-01",
            validation_end="2027-08-31",
            dataset_id=None,
            code_identity=None,
            structural_binding_id=None,
            structural_binding_sha256=None,
            cost_cell_hash=cost_hash,
        ),
    )


def _validate_dates_and_alpha(cells: tuple[PreregistrationCell, ...]) -> None:
    by_id = {cell.cell_id: cell.value for cell in cells}
    holdout = by_id["shared_holdout"]
    try:
        validation_start = require_date(holdout["validation_start"], "validation start")
        cutoff = require_date(holdout["cutoff_session"], "shared cutoff")
        validation_end = require_date(holdout["validation_end"], "validation end")
        reserved_start = require_date(holdout["reserved_start"], "holdout start")
        reserved_end = require_date(holdout["reserved_end"], "holdout end")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if not validation_start <= validation_end == cutoff < reserved_start <= reserved_end:
        raise PreregistrationError("validation and shared-holdout schedule is inconsistent")

    family = by_id["family_multiplicity"]
    fixed_lane_ids = tuple(family["fixed_lane_ids"])
    if (
        fixed_lane_ids != FIXED_LANE_IDS
        or len(set(fixed_lane_ids)) != len(FIXED_LANE_IDS)
        or family["assigned_lane_id"] != ASSIGNED_LANE_ID
        or family["shared_family_count"] != len(FIXED_LANE_IDS)
        or holdout["shared_family_count"] != len(FIXED_LANE_IDS)
    ):
        raise PreregistrationError(
            "selection-family membership must retain the four permanent lane slots"
        )

    try:
        shared_alpha = require_decimal_text(
            family["shared_family_wise_alpha"],
            "shared family-wise alpha",
            minimum=Decimal("0"),
        )
        assigned_alpha = require_decimal_text(
            family["assigned_family_alpha"],
            "assigned family alpha",
            minimum=Decimal("0"),
        )
        within_lane_ceiling = require_decimal_text(
            family["within_lane_confirmatory_alpha_ceiling"],
            "within-lane confirmatory alpha ceiling",
            minimum=Decimal("0"),
        )
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        shared_alpha != SHARED_FAMILY_WISE_ALPHA
        or assigned_alpha != WITHIN_LANE_ALPHA_CEILING
        or within_lane_ceiling != WITHIN_LANE_ALPHA_CEILING
        or assigned_alpha * len(FIXED_LANE_IDS) != shared_alpha
    ):
        raise PreregistrationError(
            "the fixed four-slot family must retain 1/80 per lane within total 1/20"
        )

    reallocation = family["slot_reallocation"]
    try:
        require_exact_keys(
            reallocation,
            frozenset({"transferable", "unused", "withdrawn", "redistribution"}),
            "slot reallocation policy",
        )
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        reallocation["transferable"] is not False
        or reallocation["unused"] != "EXPIRES"
        or reallocation["withdrawn"] != "EXPIRES"
        or reallocation["redistribution"] != "PROHIBITED"
    ):
        raise PreregistrationError(
            "unused or withdrawn lane alpha must expire without redistribution"
        )

    allocations = family["confirmatory_alpha_allocations"]
    if not isinstance(allocations, tuple) or not allocations:
        raise PreregistrationError(
            "every confirmatory TPR cell/look must have an explicit alpha allocation"
        )
    allocation_pairs: set[tuple[str, str]] = set()
    allocated_alpha = Decimal("0")
    for index, allocation in enumerate(allocations):
        try:
            require_exact_keys(
                allocation,
                frozenset({"look_id", "primary_cell_id", "two_sided_alpha"}),
                f"confirmatory alpha allocation {index}",
            )
            look_id = require_text(
                allocation["look_id"], f"confirmatory alpha allocation {index} look_id"
            )
            cell_id = require_text(
                allocation["primary_cell_id"],
                f"confirmatory alpha allocation {index} primary_cell_id",
            )
            alpha = require_decimal_text(
                allocation["two_sided_alpha"],
                f"confirmatory alpha allocation {index}",
                minimum=Decimal("0"),
                maximum=within_lane_ceiling,
            )
        except CanonicalContractError as exc:
            raise _translate(exc) from exc
        pair = (look_id, cell_id)
        if pair in allocation_pairs or alpha <= 0:
            raise PreregistrationError(
                "confirmatory alpha allocations must be unique and strictly positive"
            )
        allocation_pairs.add(pair)
        allocated_alpha += alpha

    permanent_look_ids = tuple(family["permanent_look_ids"])
    permanent_cell_ids = tuple(family["permanent_primary_cell_ids"])
    if len(permanent_look_ids) != len(permanent_cell_ids):
        raise PreregistrationError(
            "permanent look and primary-cell inventories must pair exactly"
        )
    permanent_pairs = set(zip(permanent_look_ids, permanent_cell_ids, strict=True))
    if (
        allocation_pairs != permanent_pairs
        or family["look_budget"] != len(allocations)
        or allocated_alpha > within_lane_ceiling
    ):
        raise PreregistrationError(
            "confirmatory allocations must cover the permanent inventory within 1/80"
        )

    empirical_alpha = by_id["empirical_binding_contract"]["assigned_alpha"]
    acceptance_alpha = by_id["trial_and_null_contract"][
        "primary_acceptance_contract"
    ]["two_sided_alpha"]
    try:
        empirical_alpha_value = require_decimal_text(
            empirical_alpha, "empirical binding assigned alpha"
        )
        acceptance_alpha_value = require_decimal_text(
            acceptance_alpha, "primary acceptance alpha"
        )
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        empirical_alpha_value != allocated_alpha
        or acceptance_alpha_value != allocated_alpha
    ):
        raise PreregistrationError(
            "structural-binding and acceptance alpha must equal the allocated "
            "confirmatory alpha within the permanent family ceiling"
        )


def load_algorithm_candidate(path: Path) -> AlgorithmCandidate:
    """Authenticate the immutable TPR-0A parent without granting authority."""
    raw, _ = _parse_root(path)
    if raw["status"] != CANDIDATE_STATUS:
        raise PreregistrationError("artifact is not the TPR-0A algorithm candidate")
    for field in ("producing_commit", "reviewed_by", "reviewed_at"):
        if raw[field] is not None:
            raise PreregistrationError(
                "unreviewed TPR-0A candidate cannot claim production or review identity"
            )
    try:
        spec_hash = require_sha256(raw["spec_hash"], "spec_hash")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if spec_hash != derive_spec_hash(raw):
        raise PreregistrationError("TPR-0A candidate content hash mismatch")
    if raw["spec_id"] != f"tpr-round0a-candidate-{spec_hash[:16]}":
        raise PreregistrationError("TPR-0A candidate spec_id is not content-derived")
    cells = _validate_cells(raw["cells"])
    _validate_dates_and_alpha(cells)
    looks = _validate_looks(raw["looks"])
    return AlgorithmCandidate(
        status=CANDIDATE_STATUS,
        spec_id=str(raw["spec_id"]),
        spec_hash=spec_hash,
        cells=cells,
        looks=looks,
        unresolved_owner_decisions=(),
        pending_bindings=_PENDING_BINDINGS,
    )


def _repository_root(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=True)
    raise PreregistrationError("review anchor is not inside a Git repository")


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        return authority_git(root, *arguments, binary=binary)
    except TrustRootError as exc:
        raise PreregistrationError("review anchor Git verification failed") from exc


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        return authority_is_ancestor(root, ancestor, descendant)
    except TrustRootError as exc:
        raise PreregistrationError("review ancestry verification failed") from exc


def _committed_candidate(
    root: Path,
    producing_commit: str,
    candidate_relative: str,
) -> tuple[Mapping[str, object], bytes]:
    """Authenticate the exact canonical candidate blob in its producing commit."""
    payload = bytes(
        _git(root, "show", f"{producing_commit}:{candidate_relative}", binary=True)
    )
    try:
        raw = require_canonical_json_bytes(payload, "producing candidate")
        require_exact_keys(raw, _TOP_KEYS, "producing candidate")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if raw["schema"] != ALGORITHM_SPEC_SCHEMA or raw["status"] != CANDIDATE_STATUS:
        raise PreregistrationError("producing blob is not the exact TPR-0A candidate")
    if any(raw[field] is not None for field in ("producing_commit", "reviewed_by", "reviewed_at")):
        raise PreregistrationError("producing candidate makes an unauthorized review claim")
    try:
        spec_hash = require_sha256(raw["spec_hash"], "candidate spec_hash")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        spec_hash != derive_spec_hash(raw)
        or raw["spec_id"] != f"tpr-round0a-candidate-{spec_hash[:16]}"
    ):
        raise PreregistrationError("producing candidate identity is not content-derived")
    cells = _validate_cells(raw["cells"])
    _validate_dates_and_alpha(cells)
    _validate_looks(raw["looks"])
    return raw, payload


def _review_anchor(
    spec_path: Path,
    raw: Mapping[str, object],
    spec_payload: bytes,
) -> tuple[str, str, str, str, str]:
    """Bind reviewed algorithm bytes to an independent committed Git snapshot."""
    original_registry = REVIEWED_SPEC_REGISTRY_PATH.absolute()
    original_spec = spec_path.absolute()
    _reject_redirected_path_or_ancestor(original_registry, "review registry")
    _reject_redirected_path_or_ancestor(original_spec, "reviewed spec")
    try:
        registry_path = original_registry.resolve(strict=True)
        resolved_spec = original_spec.resolve(strict=True)
    except OSError as exc:
        raise PreregistrationError("reviewed spec or review registry is absent") from exc
    if registry_path != original_registry or resolved_spec != original_spec:
        raise PreregistrationError(
            "reviewed spec and registry paths must be canonical and unredirected"
        )
    spec_root = _repository_root(resolved_spec)
    registry_root = _repository_root(registry_path)
    if spec_root != registry_root:
        raise PreregistrationError("reviewed spec and registry must share one repository")
    try:
        spec_relative = resolved_spec.relative_to(spec_root).as_posix()
        registry_relative = registry_path.relative_to(spec_root).as_posix()
    except ValueError as exc:
        raise PreregistrationError("review anchor escaped its repository") from exc
    candidate_relative = CANDIDATE_REPO_PATH
    if spec_relative == candidate_relative:
        raise PreregistrationError("reviewed artifact cannot overwrite its candidate")
    try:
        registry_payload = registry_path.read_bytes()
    except OSError as exc:
        raise PreregistrationError("review registry is unavailable") from exc
    committed_registry = bytes(
        _git(spec_root, "show", f"HEAD:{registry_relative}", binary=True)
    )
    if registry_payload != committed_registry:
        raise PreregistrationError("working review registry differs from committed bytes")
    if registry_payload == EMPTY_REVIEW_REGISTRY_BYTES:
        raise PreregistrationError("reviewed algorithm has no unique external review anchor")
    try:
        trusted_registry = verify_signed_registry_anchor(spec_root, registry_payload)
        computed_policy_paths = computed_policy_repo_paths(spec_root)
    except TrustRootError as exc:
        raise PreregistrationError("signed review-registry trust root is invalid") from exc
    if trusted_registry.registry_payload != registry_payload:
        raise PreregistrationError("signed registry bytes differ from the parsed registry")
    try:
        registry = require_canonical_json_bytes(registry_payload, "review registry")
        require_exact_keys(registry, _REGISTRY_KEYS, "review registry")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if registry["schema"] != REVIEW_REGISTRY_SCHEMA or not isinstance(
        registry["entries"], list
    ):
        raise PreregistrationError("review registry schema or entries are invalid")
    try:
        require_exact_keys(
            registry["signature_policy"],
            _REGISTRY_SIGNATURE_POLICY_KEYS,
            "review registry signature_policy",
        )
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if dict(registry["signature_policy"]) != SIGNATURE_POLICY:
        raise PreregistrationError("review registry signature policy is not frozen")
    if not registry["entries"]:
        raise PreregistrationError("reviewed algorithm has no unique external review anchor")
    if frozenset(computed_policy_paths) != frozenset(POLICY_CODE_REPO_PATHS):
        raise PreregistrationError(
            "signed policy inventory differs from the verifier import closure"
        )
    matches: list[Mapping[str, object]] = []
    seen_ids: set[str] = set()
    for entry in registry["entries"]:
        try:
            require_exact_keys(entry, _REGISTRY_ENTRY_KEYS, "review registry entry")
            entry_spec_id = require_text(entry["spec_id"], "registry spec_id")
            require_sha256(entry["spec_hash"], "registry spec_hash")
            require_sha256(entry["artifact_sha256"], "registry artifact_sha256")
            require_text(entry["spec_path"], "registry spec_path")
            require_text(entry["candidate_path"], "registry candidate_path")
            require_text(entry["candidate_spec_id"], "registry candidate_spec_id")
            require_sha256(
                entry["candidate_spec_hash"], "registry candidate_spec_hash"
            )
            require_sha256(
                entry["candidate_artifact_sha256"],
                "registry candidate_artifact_sha256",
            )
            require_exact_keys(
                entry["policy_code_sha256"],
                frozenset(POLICY_CODE_REPO_PATHS),
                "registry policy_code_sha256",
            )
            for policy_path in POLICY_CODE_REPO_PATHS:
                require_sha256(
                    entry["policy_code_sha256"][policy_path],
                    f"registry policy code hash {policy_path}",
                )
            require_git_commit(entry["review_commit"], "registry review_commit")
            require_text(entry["reviewed_by"], "registry reviewed_by")
            require_aware_instant(entry["reviewed_at"], "registry reviewed_at")
        except CanonicalContractError as exc:
            raise _translate(exc) from exc
        if entry_spec_id in seen_ids:
            raise PreregistrationError("review registry contains duplicate spec_id")
        seen_ids.add(entry_spec_id)
        if entry_spec_id == raw["spec_id"]:
            matches.append(entry)
    if len(matches) != 1:
        raise PreregistrationError("reviewed algorithm has no unique external review anchor")
    anchor = matches[0]
    try:
        anchored_hash = require_sha256(anchor["spec_hash"], "anchored spec_hash")
        artifact_hash = require_sha256(
            anchor["artifact_sha256"], "anchored artifact_sha256"
        )
        candidate_hash = require_sha256(
            anchor["candidate_spec_hash"], "anchored candidate spec_hash"
        )
        candidate_artifact_hash = require_sha256(
            anchor["candidate_artifact_sha256"],
            "anchored candidate artifact_sha256",
        )
        candidate_spec_id = require_text(
            anchor["candidate_spec_id"], "anchored candidate spec_id"
        )
        review_commit = require_git_commit(anchor["review_commit"], "review_commit")
        reviewed_by = require_text(anchor["reviewed_by"], "anchored reviewed_by")
        reviewed_at = require_aware_instant(anchor["reviewed_at"], "anchored reviewed_at")
        producing_commit = require_git_commit(raw["producing_commit"], "producing_commit")
        policy_code_hashes = {
            policy_path: require_sha256(
                anchor["policy_code_sha256"][policy_path],
                f"anchored policy code hash {policy_path}",
            )
            for policy_path in POLICY_CODE_REPO_PATHS
        }
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if (
        anchor["spec_path"] != spec_relative
        or anchor["candidate_path"] != candidate_relative
        or anchored_hash != raw["spec_hash"]
        or reviewed_by != raw["reviewed_by"]
        or reviewed_at != raw["reviewed_at"]
        or artifact_hash != sha256_bytes(spec_payload)
    ):
        raise PreregistrationError("review anchor does not bind the complete algorithm spec")
    registry_anchor_commit = trusted_registry.anchor_commit
    head_commit = trusted_registry.head_commit
    if (
        review_commit == registry_anchor_commit
        or not _git_is_ancestor(spec_root, review_commit, registry_anchor_commit)
    ):
        raise PreregistrationError(
            "signed registry anchor must be a strict descendant of review_commit"
        )
    for policy_path, expected_hash in policy_code_hashes.items():
        reviewed_policy_blob = bytes(
            _git(spec_root, "show", f"{review_commit}:{policy_path}", binary=True)
        )
        anchored_policy_blob = bytes(
            _git(
                spec_root,
                "show",
                f"{registry_anchor_commit}:{policy_path}",
                binary=True,
            )
        )
        head_policy_blob = bytes(
            _git(spec_root, "show", f"{head_commit}:{policy_path}", binary=True)
        )
        working_policy_path = (spec_root / Path(policy_path)).absolute()
        _reject_redirected_path_or_ancestor(
            working_policy_path, f"policy code {policy_path}"
        )
        try:
            resolved_policy_path = working_policy_path.resolve(strict=True)
            working_policy_blob = resolved_policy_path.read_bytes()
        except OSError as exc:
            raise PreregistrationError("reviewed policy code is unavailable") from exc
        if (
            resolved_policy_path != working_policy_path
            or sha256_bytes(anchored_policy_blob) != expected_hash
            or reviewed_policy_blob != anchored_policy_blob
            or head_policy_blob != anchored_policy_blob
            or working_policy_blob != anchored_policy_blob
        ):
            raise PreregistrationError(
                "policy code differs among review, signed anchor, HEAD, and working tree"
            )
    _git(spec_root, "cat-file", "-e", f"{producing_commit}^{{commit}}")
    if (
        producing_commit == review_commit
        or not _git_is_ancestor(spec_root, producing_commit, review_commit)
    ):
        raise PreregistrationError(
            "review commit must be a strict descendant of the exact producing commit"
        )
    candidate_raw, candidate_payload = _committed_candidate(
        spec_root, producing_commit, candidate_relative
    )
    if (
        candidate_raw["spec_id"] != candidate_spec_id
        or candidate_raw["spec_hash"] != candidate_hash
        or sha256_bytes(candidate_payload) != candidate_artifact_hash
    ):
        raise PreregistrationError(
            "review anchor does not bind the exact producing candidate identity"
        )
    transition_fields = {
        "status",
        "spec_id",
        "spec_hash",
        "producing_commit",
        "reviewed_by",
        "reviewed_at",
    }
    if any(
        raw[key] != candidate_raw[key] for key in _TOP_KEYS - transition_fields
    ):
        raise PreregistrationError(
            "reviewed artifact is not an authorized same-policy candidate transition"
        )
    reviewed_blob = bytes(
        _git(spec_root, "show", f"{review_commit}:{spec_relative}", binary=True)
    )
    anchored_blob = bytes(
        _git(
            spec_root,
            "show",
            f"{registry_anchor_commit}:{spec_relative}",
            binary=True,
        )
    )
    head_blob = bytes(
        _git(spec_root, "show", f"{head_commit}:{spec_relative}", binary=True)
    )
    if (
        reviewed_blob != anchored_blob
        or anchored_blob != head_blob
        or head_blob != spec_payload
    ):
        raise PreregistrationError(
            "algorithm spec differs among review, signed anchor, HEAD, and working tree"
        )
    if str(
        _git(
            spec_root,
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        )
    ) != f"{head_commit}\n":
        raise PreregistrationError("HEAD changed during reviewed-algorithm verification")
    try:
        if registry_path.read_bytes() != trusted_registry.registry_payload:
            raise PreregistrationError(
                "review registry changed during reviewed-algorithm verification"
            )
        if resolved_spec.read_bytes() != spec_payload:
            raise PreregistrationError(
                "algorithm spec changed during reviewed-algorithm verification"
            )
        for policy_path, expected_hash in policy_code_hashes.items():
            if sha256_bytes((spec_root / policy_path).read_bytes()) != expected_hash:
                raise PreregistrationError(
                    "policy code changed during reviewed-algorithm verification"
                )
    except OSError as exc:
        raise PreregistrationError(
            "reviewed authority bytes became unavailable during verification"
        ) from exc
    try:
        terminal_policy_paths = computed_policy_repo_paths(spec_root)
    except TrustRootError as exc:
        raise PreregistrationError(
            "signed policy import closure changed during verification"
        ) from exc
    if frozenset(terminal_policy_paths) != frozenset(POLICY_CODE_REPO_PATHS):
        raise PreregistrationError(
            "signed policy import closure changed during verification"
        )
    return (
        str(resolved_spec),
        artifact_hash,
        review_commit,
        registry_anchor_commit,
        trusted_registry.signing_key_fingerprint,
    )


def _reviewed_fingerprint(spec: ReviewedAlgorithmSpec) -> tuple[object, ...]:
    return (
        spec.status,
        spec.spec_id,
        spec.spec_hash,
        spec.producing_commit,
        spec.reviewed_by,
        spec.reviewed_at,
        tuple(
            (cell.cell_id, cell.state, authority_value(cell.value), cell.source)
            for cell in spec.cells
        ),
        tuple(dataclasses.astuple(look) for look in spec.looks),
        spec.source_path,
        spec.artifact_sha256,
        spec.review_commit,
        spec.registry_anchor_commit,
        spec.signing_key_fingerprint,
    )


def _forget_reviewed_authority(
    identity: int,
    reference: weakref.ReferenceType[ReviewedAlgorithmSpec],
) -> None:
    with _REVIEWED_AUTHORITIES_LOCK:
        current = _REVIEWED_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _REVIEWED_AUTHORITIES.pop(identity, None)


def _mint_reviewed_algorithm(
    *,
    raw: Mapping[str, object],
    cells: tuple[PreregistrationCell, ...],
    looks: tuple[RegisteredLook, ...],
    source_path: str,
    artifact_sha256: str,
    review_commit: str,
    registry_anchor_commit: str,
    signing_key_fingerprint: str,
) -> ReviewedAlgorithmSpec:
    value = object.__new__(ReviewedAlgorithmSpec)
    for name, item in {
        "status": REVIEWED_ALGORITHM_STATUS,
        "spec_id": raw["spec_id"],
        "spec_hash": raw["spec_hash"],
        "producing_commit": raw["producing_commit"],
        "reviewed_by": raw["reviewed_by"],
        "reviewed_at": raw["reviewed_at"],
        "cells": cells,
        "looks": looks,
        "source_path": source_path,
        "artifact_sha256": artifact_sha256,
        "review_commit": review_commit,
        "registry_anchor_commit": registry_anchor_commit,
        "signing_key_fingerprint": signing_key_fingerprint,
        "_authority": _REVIEWED_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _reviewed_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_reviewed_authority(key, ref)
    )
    with _REVIEWED_AUTHORITIES_LOCK:
        _REVIEWED_AUTHORITIES[identity] = (reference, Path(source_path), fingerprint)
    return value


def load_reviewed_algorithm_spec(path: Path) -> ReviewedAlgorithmSpec:
    """Load only a Git-anchored algorithm parent; still no outcome authority."""
    raw, payload = _parse_root(path)
    if raw["status"] != REVIEWED_ALGORITHM_STATUS:
        raise PreregistrationError(
            "outcome access requires an independently reviewed algorithm parent"
        )
    try:
        spec_hash = require_sha256(raw["spec_hash"], "spec_hash")
        producing_commit = require_git_commit(raw["producing_commit"], "producing_commit")
        reviewed_by = require_text(raw["reviewed_by"], "reviewed_by")
        reviewed_at = require_aware_instant(raw["reviewed_at"], "reviewed_at")
    except CanonicalContractError as exc:
        raise _translate(exc) from exc
    if spec_hash != derive_spec_hash(raw):
        raise PreregistrationError("reviewed algorithm content hash mismatch")
    if raw["spec_id"] != f"tpr-round0a-{spec_hash[:16]}":
        raise PreregistrationError("reviewed algorithm spec_id is not content-derived")
    cells = _validate_cells(raw["cells"])
    _validate_dates_and_alpha(cells)
    looks = _validate_looks(raw["looks"])
    (
        source_path,
        artifact_hash,
        review_commit,
        registry_anchor_commit,
        signing_key_fingerprint,
    ) = _review_anchor(path, raw, payload)
    # Assign validated scalar spellings back into the raw mapping used by the
    # private factory.  The canonical parser already detached it from callers.
    raw = dict(raw)
    raw.update(
        producing_commit=producing_commit,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )
    return _mint_reviewed_algorithm(
        raw=raw,
        cells=cells,
        looks=looks,
        source_path=source_path,
        artifact_sha256=artifact_hash,
        review_commit=review_commit,
        registry_anchor_commit=registry_anchor_commit,
        signing_key_fingerprint=signing_key_fingerprint,
    )


def require_reviewed_algorithm_spec(value: object) -> ReviewedAlgorithmSpec:
    if type(value) is not ReviewedAlgorithmSpec:
        raise PreregistrationError("algorithm review authority must be loader-authenticated")
    try:
        authority_token = value._authority
    except AttributeError as exc:
        raise PreregistrationError(
            "algorithm review authority must be loader-authenticated"
        ) from exc
    if authority_token is not _REVIEWED_AUTHORITY:
        raise PreregistrationError("algorithm review authority must be loader-authenticated")
    with _REVIEWED_AUTHORITIES_LOCK:
        authority = _REVIEWED_AUTHORITIES.get(id(value))
    if authority is None or authority[0]() is not value:
        raise PreregistrationError("algorithm review authority is forged or unregistered")
    _, original_path, expected_fingerprint = authority
    if _reviewed_fingerprint(value) != expected_fingerprint:
        raise PreregistrationError("reviewed algorithm authority changed after verification")
    reloaded = load_reviewed_algorithm_spec(original_path)
    if _reviewed_fingerprint(reloaded) != expected_fingerprint:
        raise PreregistrationError("reviewed algorithm bytes or Git anchor changed")
    return value


def _reject_redirected_path_or_ancestor(path: Path, name: str) -> None:
    original = path.absolute()
    for candidate in (original, *original.parents):
        try:
            is_link = candidate.is_symlink()
            try:
                is_junction = candidate.is_junction()
            except AttributeError:  # pragma: no cover - Python < 3.12
                is_junction = False
        except OSError as exc:
            raise PreregistrationError(f"{name} path-redirection audit failed") from exc
        if is_link or is_junction:
            raise PreregistrationError(
                f"{name} original path and ancestors must not contain a symlink "
                "or junction"
            )


def _require_zero_access_authority(
    path: Path,
    *,
    schema: str,
    authority_id: str,
    name: str,
) -> str:
    try:
        _reject_redirected_path_or_ancestor(path, name)
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise PreregistrationError(f"{name} must be a regular canonical artifact")
        raw = require_canonical_json_bytes(resolved.read_bytes(), name)
        require_exact_keys(
            raw,
            frozenset({"schema", "authority_mode", "authority_id", "entries"}),
            name,
        )
    except (OSError, CanonicalContractError) as exc:
        raise _translate(exc) from exc
    if (
        raw["schema"] != schema
        or raw["authority_mode"] != "zero_access"
        or raw["authority_id"] != authority_id
        or raw["entries"] != []
    ):
        raise PreregistrationError(f"{name} is not the frozen zero-access declaration")
    return authority_id


def require_zero_access_source_authority() -> str:
    return _require_zero_access_authority(
        RESEARCH_SOURCE_AUTHORITY_PATH,
        schema=SOURCE_AUTHORITY_SCHEMA,
        authority_id=ZERO_ACCESS_SOURCE_AUTHORITY_ID,
        name="TPR research-source authority",
    )


def require_zero_access_permanent_look_authority() -> str:
    return _require_zero_access_authority(
        PERMANENT_LOOK_AUTHORITY_PATH,
        schema=PERMANENT_LOOK_AUTHORITY_SCHEMA,
        authority_id=ZERO_ACCESS_LOOK_AUTHORITY_ID,
        name="TPR permanent-look authority",
    )


def authorize_outcome_access(
    algorithm: ReviewedAlgorithmSpec | AlgorithmCandidate,
    request: OutcomeAccessRequest,
) -> NoReturn:
    """Fail closed until reviewed parent, child, source, and look authorities exist."""
    if type(algorithm) is AlgorithmCandidate:
        raise PreregistrationError(
            "TPR-0A candidate is not independently reviewed and grants zero outcome access"
        )
    require_reviewed_algorithm_spec(algorithm)
    if type(request) is not OutcomeAccessRequest:
        raise PreregistrationError("outcome request must use the exact frozen request type")
    # Authenticate both negative declarations.  A missing or substituted file
    # is not equivalent to a truthful zero-access authority.
    require_zero_access_source_authority()
    require_zero_access_permanent_look_authority()
    raise PreregistrationError(
        "no reviewed structural child, admitted source, or external append-only "
        "permanent-look authority exists; TPR outcome access is zero-access"
    )


def assert_outcome_access_permit(permit: object) -> NoReturn:
    """No TPR-0A code path can mint or authenticate an outcome permit."""
    raise PreregistrationError(
        "TPR outcome permits are unavailable until a future reviewed external authority"
    )
