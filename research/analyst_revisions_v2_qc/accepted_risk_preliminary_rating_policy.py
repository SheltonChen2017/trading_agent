"""Static disclosures for the accepted-risk preliminary rating evaluator."""

CONTRACT_ID = "arv2-accepted-risk-preliminary-rating-evaluator-v1"
MANIFEST_SCHEMA = "arv2-accepted-risk-preliminary-rating-manifest-v1"
SESSION_SCHEMA = "arv2-preliminary-rating-session-v1"
MEMBERSHIP_SCHEMA = "arv2-preliminary-rating-membership-v1"
CONTRIBUTION_SCHEMA = "arv2-preliminary-rating-contribution-v1"
SUMMARY_SCHEMA = "arv2-accepted-risk-preliminary-rating-summary-v1"
CELL_SCHEMA = "arv2-accepted-risk-preliminary-rating-summary-cell-v1"
HISTORY_REQUEST_SCHEMA = "arv2-preliminary-total-return-history-request-v1"
HISTORY_OBSERVATION_SCHEMA = "arv2-preliminary-total-return-open-observation-v1"
SOURCE_LINEAGE_FIELDS = (
    "accepted_risk_input_pair_sha256",
    "security_master_admission_sha256",
    "firm_ontology_admission_sha256",
    "global_rating_map_sha256",
    "pre_normalized_contribution_source_sha256",
)
SESSION_FIELDS = ("schema", "session_index", "session")
MEMBERSHIP_FIELDS = (
    "schema",
    "security_id",
    "first_session_index",
    "last_session_index_exclusive",
    "sector_id",
    "q_data",
    "row_sha256",
)
CONTRIBUTION_FIELDS = (
    "schema",
    "source_view_id",
    "contribution_id",
    "security_id",
    "eligible_session_index",
    "institution_id",
    "common_event_id",
    "rating_action",
    "firm_delta_numerator",
    "firm_delta_denominator",
    "global_delta_numerator",
    "global_delta_denominator",
    "source_row_sha256",
    "row_sha256",
)
MANIFEST_FIELDS = (
    "schema",
    "contract_id",
    "manifest_id",
    "source_view_ids",
    "horizons",
    "primary_window",
    "descriptive_window",
    "rating_history_start_session",
    "history_observation",
    "benchmark_security_id",
    "session_axis_count",
    "session_axis_sha256",
    "membership_row_count",
    "membership_rows_sha256",
    "contribution_row_count",
    "contribution_rows_sha256",
    "source_lineage_sha256s",
    "history_batch_security_count",
    "scoring_sessions_per_callback",
    "signal_seed_contributions_per_callback",
    "q_data_policy_id",
    "maximum_backtest_runtime_hours",
    "accepted_risk_disclosures",
    "manifest_sha256",
)
HISTORY_OBSERVATION = (
    "session_open_total_return_adjusted_open_to_open_excess_vs_SPY"
)
Q_DATA_POLICY_ID = "owner_waived_uniform_full_weight_not_formal_qdata_measurement"
RATING_HISTORY_START_SESSION = "2013-01-02"
SOURCE_VIEW_IDS = (
    "current_row_current_vintage_non_pristine_pit",
    "conservative_censored_current_vintage_non_pristine_pit",
)
HORIZONS = (1, 5, 20, 60)
PRIMARY_WINDOW_ITEMS = (
    ("window_id", "formal_2020_2025_primary"),
    ("start_session", "2020-01-02"),
    ("end_session", "2025-12-31"),
    ("role", "primary_preliminary_stock_ic_window"),
)
DESCRIPTIVE_WINDOW_ITEMS = (
    ("window_id", "owner_2021_2025_descriptive_sensitivity"),
    ("start_session", "2021-01-04"),
    ("end_session", "2025-12-31"),
    ("role", "owner_requested_descriptive_sensitivity_only"),
)

ACCEPTED_RISK_DISCLOSURE_ITEMS = (
    ("current_and_conservatively_censored_source_views", True),
    ("pre_normalized_firm_and_global_rating_deltas", True),
    ("institution_stock_session_deduplicated_upstream", True),
    ("rating_half_life_sessions", 20),
    ("byte_identical_formal_per_event_decay_replay", False),
    ("complete_cross_section_required_for_each_date_ic", True),
    ("owner_waived_uniform_q_data", True),
    ("historical_point_in_time_security_master", False),
    ("historical_point_in_time_sector_classification", False),
    ("pristine_point_in_time_input", False),
    ("control_residualization", False),
    ("formal_walk_forward_control_fit", False),
    ("frozen_26_family_formal_result", False),
    ("terminal_payoff_or_successor_authority", False),
    ("economic_portfolio_evaluation", False),
    ("etf_portfolio_construction", False),
    ("actual_or_synthetic_leverage", False),
    ("deployment", False),
    ("orders", False),
    ("trading", False),
)


def primary_window_record():
    return dict(PRIMARY_WINDOW_ITEMS)


def descriptive_window_record():
    return dict(DESCRIPTIVE_WINDOW_ITEMS)


def accepted_risk_disclosures_record():
    return dict(ACCEPTED_RISK_DISCLOSURE_ITEMS)

OMITTED_FORMAL_COMPONENTS = (
    "point_in_time_security_and_listing_master",
    "point_in_time_sector_history",
    "measured_session_specific_q_data",
    "preopen_control_residualization",
    "walk_forward_train_only_control_fit",
    "terminal_cash_delisting_and_successor_returns",
    "matched_formal_26_report_family_output",
    "multiplicity_gate_and_accept_reject_inference",
    "dependence_aware_HAC_ICIR_and_block_bootstrap",
    "common_event_component_grouping_and_rating_action_cohorts",
    "byte_identical_formal_per_event_decay_replay",
    "direct_stock_or_etf_economic_portfolio",
    "transaction_cost_turnover_and_overlap_evaluation",
    "actual_or_synthetic_leveraged_etf_evaluation",
)
