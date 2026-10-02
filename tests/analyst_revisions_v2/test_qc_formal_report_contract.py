from __future__ import annotations

import copy
import dataclasses
import gc
import hashlib
import json
import weakref

import pytest

from research.analyst_revisions_v2_qc import formal_report_contract as module


ECONOMIC_SHA256 = hashlib.sha256(b"reviewed-economic-definition").hexdigest()
OTHER_ECONOMIC_SHA256 = hashlib.sha256(b"other-economic-definition").hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )


def _contract():
    return module.build_formal_report_contract(
        economic_execution_definition_sha256=ECONOMIC_SHA256
    )


def _record() -> dict[str, object]:
    return module.formal_report_contract_record(_contract())


def _registry_seed(registry: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in registry.items()
        if key not in {"registry_id", "registry_sha256"}
    }


def test_builder_returns_one_content_addressed_outcome_free_contract():
    contract = _contract()
    assert module.require_formal_report_contract(
        contract,
        expected_economic_execution_definition_sha256=ECONOMIC_SHA256,
    ) is contract
    record = module.formal_report_contract_record(contract)
    semantic = {
        key: value
        for key, value in record.items()
        if key not in {"contract_id", "contract_sha256"}
    }
    semantic_sha256 = hashlib.sha256(_canonical(semantic)).hexdigest()
    assert contract.contract_id == "arv2-formal-report-contract-" + semantic_sha256[:24]
    assert contract.contract_sha256 == semantic_sha256
    assert contract.artifact_sha256 == hashlib.sha256(
        module.render_formal_report_contract_bytes(contract)
    ).hexdigest()
    assert contract.report_family_count == 13
    assert contract.secondary_hypothesis_count == 19
    assert contract.strategy_trial_count == 6
    assert all(
        getattr(contract, name) is False
        for name in (
            "input_read_available",
            "outcome_access_available",
            "quantconnect_available",
            "result_read_available",
            "result_disposition_available",
            "deployment_available",
            "orders_available",
            "trading_available",
        )
    )
    assert set(record["capabilities"].values()) == {False}
    assert record["contains_results"] is False
    assert record["result_sha256"] is None
    assert record["current_execution_authorized"] is False
    assert record["numeric_and_output_rules"][
        "raw_security_event_market_order_trade_or_log_rows_exported"
    ] is False


def test_complete_candidate_has_one_golden_content_identity():
    contract = _contract()
    assert contract.contract_id == (
        "arv2-formal-report-contract-bd8d06adcd73e3b985cdc421"
    )
    assert contract.contract_sha256 == (
        "bd8d06adcd73e3b985cdc421093cd1604c8b7a706cd2d248ec406fcf70ca4bc8"
    )
    assert contract.artifact_sha256 == (
        "48fb78ea34e329353b32bf05dd1c6128f01ba4285c43a5eb18546f3b1b5814f7"
    )
    assert contract.secondary_hypothesis_registry_sha256 == (
        "ac3dcfc657c566875404526d908809ff96f4831f58a6ea44a394f22e15068040"
    )
    assert contract.deflated_sharpe_trial_registry_sha256 == (
        "97fe4342a2fe0443e5acb18c12ced69f5032c618761a1d5f425e258d9e868080"
    )
    assert contract.stock_bootstrap_seed_sha256 == (
        "b0ffa30f76536cd57c19a779924a143c374b66c15c6cbaba02bfb764aadd2f3a"
    )
    assert len(module.render_formal_report_contract_bytes(contract)) == 48703


def test_contract_is_deterministic_and_economic_parent_specific():
    first = _contract()
    second = _contract()
    other = module.build_formal_report_contract(
        economic_execution_definition_sha256=OTHER_ECONOMIC_SHA256
    )
    assert first is not second
    assert module.render_formal_report_contract_bytes(
        first
    ) == module.render_formal_report_contract_bytes(second)
    assert first.contract_id == second.contract_id
    assert first.contract_sha256 == second.contract_sha256
    assert first.artifact_sha256 == second.artifact_sha256
    assert module.render_formal_report_contract_bytes(
        first
    ) != module.render_formal_report_contract_bytes(other)
    assert first.contract_sha256 != other.contract_sha256
    assert first.stock_bootstrap_seed_sha256 != other.stock_bootstrap_seed_sha256
    assert first.secondary_hypothesis_registry_sha256 == other.secondary_hypothesis_registry_sha256
    assert (
        first.deflated_sharpe_trial_registry_sha256
        == other.deflated_sharpe_trial_registry_sha256
    )
    with pytest.raises(module.FormalReportContractError, match="another economic parent"):
        module.require_formal_report_contract(
            first,
            expected_economic_execution_definition_sha256=OTHER_ECONOMIC_SHA256,
        )


def test_all_thirteen_required_report_families_have_closed_bounded_schemas():
    record = _record()
    assert tuple(record["required_report_family_ids"]) == module.REPORT_FAMILY_IDS
    schemas = record["report_schemas"]
    assert [item["family_id"] for item in schemas] == list(module.REPORT_FAMILY_IDS)
    assert len(schemas) == len({item["family_id"] for item in schemas}) == 13
    for schema in schemas:
        assert schema["raw_security_event_or_market_rows_permitted"] is False
        assert type(schema["maximum_rows_per_source_view"]) is int
        assert 0 < schema["maximum_rows_per_source_view"] <= 12000
        assert schema["ordered_key_fields"][0] == "source_view_id"
        assert schema["ordered_value_fields"][0] == "status"
        assert schema["missing_rule"].endswith("never_zero_fill")
    assert [item["family_id"] for item in schemas[-6:]] == [
        "plot_data_percentile_vs_future_return",
        "plot_data_rolling_ic_and_sharpe",
        "plot_data_year_by_year_out_of_sample_alpha",
        "plot_data_signal_decay",
        "plot_data_turnover_vs_net_return",
        "plot_data_drawdown_and_time_underwater",
    ]
    output = record["numeric_and_output_rules"]
    assert output["unknown_field_or_cell"] == "refuse_complete_report"
    assert output["duplicate_key_or_cell"] == "refuse_complete_report"
    assert output["maximum_encoded_bytes_per_cell"] == 8192
    assert output["aggregate_compressed_byte_ceiling"] == 200000
    assert output["aggregate_decompressed_byte_ceiling"] == 4194304
    assert output["status_encoding"] == [
        "AVAILABLE", "UNAVAILABLE", "REFUSED", "INCONCLUSIVE", "INVALID_DATA"
    ]


def test_dimensions_cohorts_exclusions_and_non_rescue_rules_are_exact():
    record = _record()
    dimensions = record["dimensions"]
    assert tuple(dimensions["source_view_ids"]) == module.SOURCE_VIEW_IDS
    assert dimensions["primary_source_view_id"] == module.SOURCE_VIEW_IDS[0]
    assert dimensions["sensitivity_source_view_id"] == module.SOURCE_VIEW_IDS[1]
    assert dimensions["sensitivity_source_view_can_replace_or_rescue_primary"] is False
    assert tuple(dimensions["horizons_sessions"]) == (1, 5, 20, 60)
    assert dimensions["primary_horizon_sessions"] == 20
    assert dimensions["minimum_valid_test_dates"] == 50
    assert dimensions["hac_lag_sessions_by_horizon"] == {
        "1": 1, "5": 5, "20": 20, "60": 60
    }
    assert dimensions["hac_session_axis"].startswith("actual_XNYS_session_distance")
    assert dimensions["hac_kernel"] == "Bartlett"
    assert tuple(dimensions["rating_actions"]) == ("upgrades", "downgrades")
    assert tuple(item["cohort_id"] for item in dimensions["cohorts"]) == module.COHORT_IDS
    assert dimensions["cohort_assignment"].startswith("all_plus_exactly_one_nonall_cohort")
    exclusions = dimensions["earnings_exclusions"]
    assert [item["exclusion_id"] for item in exclusions] == list(module.EARNINGS_EXCLUSION_IDS)
    assert exclusions[0]["inclusive_session_distances"] == [-2, -1, 0, 1, 2]
    assert exclusions[1]["inclusive_session_distances"] == list(range(-5, 6))
    slices = dimensions["slices"]
    assert slices[0] == {
        "slice_id": "formal_2020_2025_primary",
        "fold_ids": list(module.FORMAL_FOLD_IDS),
        "report_fold_scope_ids": list(module.FORMAL_FOLD_IDS) + ["POOLED"],
        "classification": "PRIMARY_development",
        "may_be_rescued_by_other_slice": False,
    }
    assert slices[1] == {
        "slice_id": "owner_2021_2025_descriptive_sensitivity",
        "fold_ids": list(module.DESCRIPTIVE_FOLD_IDS),
        "report_fold_scope_ids": list(module.DESCRIPTIVE_FOLD_IDS) + ["POOLED"],
        "classification": "DESCRIPTIVE_sensitivity",
        "may_replace_or_rescue_primary": False,
    }
    assert dimensions["score_arm_ids"] == ["firm_specific", "global_map"]
    assert dimensions["fama_macbeth_coefficient_ids"] == ["bullish", "bearish"]
    assert dimensions["report_fold_scope_token"] == "POOLED"
    assert dimensions["earnings_cohort_anchor"].startswith(
        "among_point_in_time_known_earnings_sessions_choose_minimum_absolute"
    )
    assert tuple(dimensions["portfolio_variant_ids"]) == module.PORTFOLIO_VARIANT_IDS
    assert dimensions["portfolio_leverage"] is False
    assert set(dimensions["portfolio_variant_definitions"]) == set(
        module.PORTFOLIO_VARIANT_IDS
    )
    assert "one_divided_by" in dimensions["portfolio_variant_definitions"][
        "direct_stock_inverse_volatility"
    ]
    assert "strictly_positive" in dimensions["portfolio_variant_definitions"][
        "direct_stock_score_weight"
    ]
    assert tuple(dimensions["cost_bps_per_side"]) == (0, 5, 10, 20)
    assert dimensions["event_time_sessions"] == [0, 1, 5, 20, 60]
    assert dimensions["percentile_bins"] == list(range(1, 11))
    assert dimensions["rolling_window_sessions"] == 60
    assert dimensions["rolling_minimum_valid_observations"] == 50
    assert dimensions["rolling_series_ids"] == [
        "firm_specific_H20_daily_IC",
        "global_map_H20_daily_IC",
        "direct_stock_equal_weight_cost10_daily_net_excess_return",
    ]
    assert dimensions["rolling_plot_fold_scope"] == "POOLED_only"
    accounting = dimensions["f6_accounting_axis"]
    assert [item["accounting_kind"] for item in accounting] == [
        "preoutcome_decision_terminal",
        "horizon_outcome_terminal",
        "economic_trial_terminal",
        "lifecycle_terminal_disposition",
        "global_comparator_coverage_ledger",
        "report_family_terminal",
        "power_floor",
    ]
    assert accounting[0]["reason_or_component_ids"] == ["all"]
    assert accounting[1]["reason_or_component_ids"] == ["h1", "h5", "h20", "h60"]
    assert accounting[2]["reason_or_component_ids"] == (
        "exact_six_strategy_trial_registry_ids"
    )
    assert accounting[4]["reason_or_component_ids"] == list(
        module.COMPARATOR_LEDGER_IDS
    )
    assert accounting[5]["reason_or_component_ids"] == list(
        module.REPORT_FAMILY_IDS
    )
    assert accounting[6]["reason_or_component_ids"] == [
        "valid_h20_fm_dates",
        "connected_h20_components",
    ]
    assert dimensions["f6_accounting_equality"].startswith(
        "expected_count_equals_terminal_count"
    )
    assert "before_constructing_any_F6_row" in dimensions["f6_self_accounting"]
    assert record["classification"]["secondary_can_replace_or_rescue_primary"] is False
    assert record["classification"]["exploratory_can_replace_or_rescue_primary"] is False
    primary = record["primary_gate_composition"]
    assert primary["scope"].startswith("formal_2020_2025_primary_POOLED")
    assert primary["sensitivity_scope"].endswith(
        "replace_or_rescue_the_primary_source_view"
    )
    assert primary["combination"] == "all_primary_and_power_gates_conjunctive_no_rescue"
    assert primary["output_fields"] == [
        "gate_id", "status", "observed_metric", "threshold", "reasons"
    ]


def test_secondary_registry_is_ordered_complete_hashed_and_non_rescuing():
    record = _record()
    registry = record["secondary_hypothesis_registry"]
    hypotheses = registry["ordered_hypotheses"]
    expected_ids = [
        "secondary_fm_bullish_h1",
        "secondary_fm_bullish_h5",
        "secondary_fm_bullish_h60",
        "secondary_fm_bearish_h1",
        "secondary_fm_bearish_h5",
        "secondary_fm_bearish_h20",
        "secondary_fm_bearish_h60",
        "secondary_fm_bullish_h20_cohort_exact_earnings_day",
        "secondary_fm_bullish_h20_cohort_one_to_two_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_three_to_five_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_over_five_days_after_earnings",
        "secondary_fm_bullish_h20_cohort_pre_earnings",
        "secondary_fm_bullish_h20_earnings_exclusion_pm2",
        "secondary_fm_bullish_h20_earnings_exclusion_pm5",
        "secondary_economic_direct_stock_inverse_volatility_cost10",
        "secondary_economic_direct_stock_score_weight_cost10",
        "secondary_economic_direct_stock_equal_weight_cost0",
        "secondary_economic_direct_stock_equal_weight_cost5",
        "secondary_economic_direct_stock_equal_weight_cost20",
    ]
    assert [item["hypothesis_id"] for item in hypotheses] == expected_ids
    assert [item["registry_ordinal"] for item in hypotheses] == list(range(19))
    assert {item["score_arm_id"] for item in hypotheses} == {"firm_specific"}
    assert all(item["classification"] == "SECONDARY_non_rescuing" for item in hypotheses)
    assert registry["required_cohort_baseline"] == {
        "cohort_id": "all",
        "duplicates_primary_population": True,
        "included_in_bh_family": False,
    }
    bh = registry["benjamini_hochberg"]
    assert bh["family_size"] == 19
    assert bh["scope"].startswith("one_independent_19_slot_family_per_source_view")
    assert bh["missing_or_refused_p_value"] == "retain_slot_and_use_exact_one_for_adjustment"
    assert bh["rank_order"] == "ascending_exact_p_value_then_registry_ordinal"
    assert bh["raw_adjustment"] == "min(1,family_size_times_p_value_divided_by_rank)"
    assert bh["monotonicity"] == "reverse_cumulative_minimum_in_rank_order"
    assert bh["rejection_threshold"] == {"numerator": 1, "denominator": 20}
    assert bh["maximum_output_rows_per_source_view"] == 19
    assert bh["output_fields"][-2:] == ["rejected_at_q_lte_0_05", "reasons"]
    assert bh["role"].startswith("reporting_only_never_replaces_or_rescues")
    bindings = registry["required_reporting_bindings"]
    assert (
        bindings["stock_event_returns_by_rating_action"]["report_family_id"]
        == module.REPORT_FAMILY_IDS[0]
    )
    assert (
        bindings["event_time_cumulative_abnormal_return_by_rating_action"][
            "report_family_id"
        ]
        == module.REPORT_FAMILY_IDS[1]
    )
    digest = hashlib.sha256(_canonical(_registry_seed(registry))).hexdigest()
    assert registry["registry_sha256"] == digest
    assert registry["registry_id"] == "arv2-secondary-hypothesis-registry-" + digest[:24]


def test_strategy_trial_registry_and_deflated_sharpe_units_are_exact():
    registry = _record()["strategy_trial_registry"]
    trials = registry["ordered_trials"]
    assert [item["registry_ordinal"] for item in trials] == list(range(6))
    assert [item["trial_id"] for item in trials] == [
        "direct_stock_equal_weight_cost0",
        "direct_stock_equal_weight_cost5",
        "direct_stock_equal_weight_cost10",
        "direct_stock_equal_weight_cost20",
        "direct_stock_inverse_volatility_cost10",
        "direct_stock_score_weight_cost10",
    ]
    assert registry["annualization_sessions"] == 252
    assert registry["common_session_rule"].endswith("without_shrinking_N")
    assert registry["sharpe"]["daily"] == "mean_divided_by_standard_deviation"
    assert registry["sharpe"]["annualized"] == "daily_sharpe_times_sqrt_Decimal_252"
    deflated = registry["deflated_sharpe"]
    assert deflated["trial_count_N"] == 6
    assert deflated["unit"].startswith("daily_Sharpe_for_threshold_and_z")
    assert deflated["expected_maximum_multiplier"] == "1.300140787845584"
    assert deflated["normal_cdf"]["decimal_precision"] == 80
    assert deflated["input_fields"][-1] == "daily_net_excess_total_return"
    assert deflated["output_fields"][-2:] == ["status", "reasons"]
    assert deflated["maximum_output_rows_per_source_view"] == 6
    assert deflated["winner_selection"] == "none_report_all_six_registry_trials"
    assert deflated["role"].startswith("reporting_only_never_replaces_or_rescues")
    digest = hashlib.sha256(_canonical(_registry_seed(registry))).hexdigest()
    assert registry["registry_sha256"] == digest
    assert registry["registry_id"] == "arv2-strategy-trial-registry-" + digest[:24]


def test_five_global_comparator_coverage_ledgers_are_exact_preoutcome_gates():
    coverage = _record()["global_comparator_coverage"]
    assert tuple(coverage["ordered_ledger_ids"]) == module.COMPARATOR_LEDGER_IDS
    assert set(coverage["definitions"]) == set(module.COMPARATOR_LEDGER_IDS)
    assert coverage["source_view_scope"] == "each_source_view_is_gated_separately"
    assert coverage["fold_scope"].startswith("each_exact_H20_test_fold_then_pooled")
    assert coverage["event_fold_attribution"].startswith(
        "one_C2_hash_occurrence_per_source_view_fold"
    )
    assert "firm_only_institution_security_session_daily_dedupe" in (
        coverage["event_fold_attribution"]
    )
    assert "score_refused_candidate_dates" in coverage["diagnostic_censuses"]
    assert (
        "exact_hashed_raw_and_canonical_label_disposition_counts"
        in coverage["diagnostic_censuses"]
    )
    assert coverage["threshold"] == {"numerator": 19, "denominator": 20}
    assert coverage["comparison"] == "numerator_times_20_greater_than_or_equal_denominator_times_19"
    assert coverage["zero_denominator"] == "INVALID_DATA_not_ready"
    assert coverage["gate"].startswith("all_five_ledgers_each_fold_and_pooled_must_pass")
    assert coverage["outcome_inputs_permitted"] is False


def test_stock_bootstrap_seed_and_draw_encoding_bind_every_required_parent():
    record = _record()
    bootstrap = record["bootstrap"]
    seed = bootstrap["stock_FM_and_economic_seed_record"]
    assert seed == {
        "domain": "arv2-stock-formal-bootstrap-seed-v1",
        "qc_first_plan_sha256": module.QC_FIRST_PLAN_SHA256,
        "fold_manifest_sha256": module.FOLD_MANIFEST_SHA256,
        "evaluation_id": module.EVALUATION_ID,
        "economic_execution_definition_sha256": ECONOMIC_SHA256,
        "secondary_hypothesis_registry_sha256": record[
            "secondary_hypothesis_registry"
        ]["registry_sha256"],
        "deflated_sharpe_trial_registry_sha256": record[
            "strategy_trial_registry"
        ]["registry_sha256"],
        "sampler_version": "v1",
    }
    assert bootstrap["stock_FM_and_economic_seed_sha256"] == hashlib.sha256(
        _canonical(seed)
    ).hexdigest()
    assert bootstrap["operative_seed_precedence"].startswith(
        "this_authenticated_child_seed_and_draw_contract_is_the_sole_operative"
    )
    assert len(bootstrap["metric_ids"]) == 21
    assert bootstrap["metric_ids"][:2] == [
        "primary_fm_bullish_h20",
        "primary_economic_equal_weight_cost10",
    ]
    assert len(bootstrap["metric_ids"]) == len(set(bootstrap["metric_ids"]))
    assert "source_view_length_uint16BE" in bootstrap["draw_preimage"]
    assert "slice_length_uint16BE" in bootstrap["draw_preimage"]
    assert "metric_length_uint16BE" in bootstrap["draw_preimage"]
    assert "rejection_uint64BE" in bootstrap["draw_preimage"]
    assert "pooled_formal_ordinal_6" in bootstrap["fold_ordinal"]
    assert "pooled_descriptive_ordinal_7" in bootstrap["fold_ordinal"]
    assert bootstrap["noncircular_complete_axis"] is True
    assert bootstrap["resamples"] == 19999
    assert bootstrap["resample_ordinal"] == "zero_based_0_through_19998"
    assert bootstrap["empty_replicate"] == "INCONCLUSIVE_locked_no_redraw"
    assert bootstrap["two_sided_p_value"].endswith("as_reduced_Fraction")


def test_render_and_load_are_byte_exact_and_return_new_authenticated_identity():
    contract = _contract()
    payload = module.render_formal_report_contract_bytes(contract)
    assert payload.endswith(b"\n")
    assert payload == _canonical(json.loads(payload))
    loaded = module.load_formal_report_contract_bytes(
        payload,
        expected_economic_execution_definition_sha256=ECONOMIC_SHA256,
    )
    assert loaded is not contract
    assert module.require_formal_report_contract(loaded) is loaded
    assert module.render_formal_report_contract_bytes(loaded) == payload


@pytest.mark.parametrize(
    "bad",
    [
        None,
        b"1" * 64,
        "A" * 64,
        "1" * 63,
        "0" * 64,
        True,
    ],
)
def test_builder_rejects_unresolved_or_inexact_economic_parent(bad):
    with pytest.raises(module.FormalReportContractError, match="SHA-256|unresolved"):
        module.build_formal_report_contract(
            economic_execution_definition_sha256=bad  # type: ignore[arg-type]
        )


def test_builder_rejects_string_subclass_parent():
    class StringSubclass(str):
        pass

    with pytest.raises(module.FormalReportContractError, match="exact lowercase"):
        module.build_formal_report_contract(
            economic_execution_definition_sha256=StringSubclass(ECONOMIC_SHA256)
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.__setitem__("unknown", False),
        lambda value: value["required_report_family_ids"].pop(),
        lambda value: value["capabilities"].__setitem__("result_read", True),
        lambda value: value["parents"].__setitem__(
            "economic_execution_definition_sha256", OTHER_ECONOMIC_SHA256
        ),
        lambda value: value["secondary_hypothesis_registry"].__setitem__(
            "registry_sha256", "1" * 64
        ),
        lambda value: value["report_schemas"][0].__setitem__(
            "raw_security_event_or_market_rows_permitted", True
        ),
    ],
)
def test_loader_rejects_canonical_unknown_incomplete_or_tampered_documents(mutator):
    value = copy.deepcopy(_record())
    mutator(value)
    with pytest.raises(module.FormalReportContractError, match="unknown, incomplete, or binds"):
        module.load_formal_report_contract_bytes(
            _canonical(value),
            expected_economic_execution_definition_sha256=ECONOMIC_SHA256,
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{ "x":1}\n',
        b'{"x":1}\r\n',
        b"\xef\xbb\xbf{}\n",
        b'{"x":"a\\u0000b"}\x00\n',
        b'{"x":1,"x":1}\n',
        b'{"x":1.0}\n',
        b'{"x":NaN}\n',
        b"\xff\n",
    ],
)
def test_loader_rejects_noncanonical_duplicate_float_nonfinite_or_bad_framing(payload):
    with pytest.raises(module.FormalReportContractError):
        module.load_formal_report_contract_bytes(
            payload,
            expected_economic_execution_definition_sha256=ECONOMIC_SHA256,
        )


def test_loader_refuses_before_parsing_a_document_over_the_byte_ceiling():
    with pytest.raises(module.FormalReportContractError, match="byte ceiling"):
        module.load_formal_report_contract_bytes(
            b"{" + b" " * module.MAX_CONTRACT_BYTES + b"}\n",
            expected_economic_execution_definition_sha256=ECONOMIC_SHA256,
        )


def test_caller_cannot_mint_or_mutate_an_authenticated_contract():
    forged = object.__new__(module.FormalReportContract)
    with pytest.raises(module.FormalReportContractError, match="builder-authenticated"):
        module.require_formal_report_contract(forged)
    contract = _contract()
    object.__setattr__(contract, "status", "authorized")
    with pytest.raises(module.FormalReportContractError, match="changed after authentication"):
        module.require_formal_report_contract(contract)


def test_copied_identity_is_not_authority_and_dead_contract_is_forgotten():
    contract = _contract()
    identity = id(contract)
    cloned = copy.copy(contract)
    with pytest.raises(module.FormalReportContractError, match="builder-authenticated"):
        module.require_formal_report_contract(cloned)
    reference = weakref.ref(contract)
    del contract
    gc.collect()
    assert reference() is None
    assert identity not in module._CONTRACTS


def test_detached_record_mutation_does_not_change_authenticated_contract():
    contract = _contract()
    detached = module.formal_report_contract_record(contract)
    detached["capabilities"]["outcome_access"] = True
    detached["report_schemas"].clear()
    assert module.require_formal_report_contract(contract) is contract
    fresh = module.formal_report_contract_record(contract)
    assert fresh["capabilities"]["outcome_access"] is False
    assert len(fresh["report_schemas"]) == 13


def test_sealed_template_is_not_rewritten_by_public_global_rebinding(monkeypatch):
    expected = module.render_formal_report_contract_bytes(_contract())
    monkeypatch.setattr(module, "_STATIC_TEMPLATE_BYTES", b"{}\n")
    monkeypatch.setattr(module, "REPORT_FAMILY_IDS", ("hostile",))
    monkeypatch.setattr(module, "SCHEMA", "hostile")
    observed = module.build_formal_report_contract(
        economic_execution_definition_sha256=ECONOMIC_SHA256
    )
    assert module.render_formal_report_contract_bytes(observed) == expected
    assert observed.report_family_count == 13
    assert observed.schema == "arv2-formal-report-execution-contract-v1"


def test_contract_object_shape_and_export_surface_are_closed():
    assert {item.name for item in dataclasses.fields(module.FormalReportContract)} == {
        "contract_id",
        "contract_sha256",
        "artifact_sha256",
        "schema",
        "status",
        "authority",
        "evaluation_id",
        "economic_execution_definition_sha256",
        "secondary_hypothesis_registry_sha256",
        "deflated_sharpe_trial_registry_sha256",
        "stock_bootstrap_seed_sha256",
        "report_family_count",
        "secondary_hypothesis_count",
        "strategy_trial_count",
        "_canonical_document",
    }
    assert "open" not in module.__all__
    assert "submit" not in module.__all__
    assert "evaluate" not in module.__all__
    assert "authorize" not in module.__all__
    assert {
        "build_formal_report_contract",
        "require_formal_report_contract",
        "render_formal_report_contract_bytes",
        "load_formal_report_contract_bytes",
        "formal_report_contract_record",
    }.issubset(module.__all__)
