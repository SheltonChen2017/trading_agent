from __future__ import annotations

import dataclasses
import gc
import hashlib
import json
import os
from pathlib import Path

import pytest

from research.analyst_revisions_v2.stock_evaluation_contract import (
    StockEvaluationContract,
    load_stock_evaluation_contract,
)
from research.analyst_revisions_v2_qc.formal_economic_execution_definition import (
    BOOTSTRAP_RESAMPLES,
    COST_BPS_PER_SIDE,
    DEFINITION_SCHEMA,
    FORMAL_FOLD_IDS,
    FormalEconomicExecutionBinding,
    FormalEconomicExecutionDefinition,
    FormalEconomicExecutionDefinitionError,
    build_formal_economic_execution_binding,
    build_formal_economic_execution_definition,
    formal_economic_terminal_liquidation_session,
    load_formal_economic_execution_definition,
    render_formal_economic_execution_definition_bytes,
    require_formal_economic_execution_binding,
    require_formal_economic_execution_definition,
)


ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "research" / "analyst_revisions_v2" / "specs"
STOCK_SPEC = SPECS / "arv2_stock_historical.structural.json"
QC_PLAN = SPECS / "arv2_qc_first.draft.json"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _stock() -> StockEvaluationContract:
    return load_stock_evaluation_contract(STOCK_SPEC, qc_first_plan_path=QC_PLAN)


def _definition() -> FormalEconomicExecutionDefinition:
    return build_formal_economic_execution_definition(_stock())


def _binding() -> FormalEconomicExecutionBinding:
    return build_formal_economic_execution_binding(_definition())


def test_definition_binds_exact_stock_and_plan_ancestry_and_content_identity():
    value = _definition()
    record = value.to_record()
    assert record["schema"] == DEFINITION_SCHEMA
    assert record["source_definition_closure"] == {
        "strategy_pdf_sha256": "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193",
        "stock_spec_id": "arv2-stock-historical-c5ff2a6a0dcf341e",
        "stock_spec_sha256": "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b",
        "stock_economic_section_sha256": "3b98c40dd7b470658f08a8812d816aa0eeff9f765282917e478dfe378dcc95bd",
        "fold_manifest_id": "arv2-stock-folds-1002155dbe8e3e87",
        "fold_manifest_sha256": "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611",
    }
    assert record["execution_plan_ancestry"]["evaluation_id"] == (
        "arv2-eval-stock-historical-qc-001"
    )
    assert tuple(record["execution_plan_ancestry"]["formal_primary_fold_ids"]) == (
        FORMAL_FOLD_IDS
    )
    seed = dict(record)
    seed["definition_id"] = None
    seed["definition_sha256"] = None
    assert hashlib.sha256(_canonical(seed)).hexdigest() == value.definition_sha256
    assert value.definition_id == (
        "arv2-formal-economic-execution-" + value.definition_sha256[:24]
    )
    payload = render_formal_economic_execution_definition_bytes(value)
    assert hashlib.sha256(payload).hexdigest() == value.payload_sha256
    assert require_formal_economic_execution_definition(value) is value


def test_dataclass_field_surface_is_exact_and_authority_registries_cleanup():
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    assert tuple(field.name for field in dataclasses.fields(FormalEconomicExecutionDefinition)) == (
        "definition_id", "definition_sha256", "payload_sha256",
        "bootstrap_base_ancestry_sha256", "source_stock_spec_id",
        "source_stock_spec_sha256", "source_evaluation_id",
        "source_parent_plan_id", "source_parent_plan_sha256",
        "_source_stock_contract", "_canonical_document",
    )
    assert tuple(field.name for field in dataclasses.fields(FormalEconomicExecutionBinding)) == (
        "binding_id", "binding_sha256", "schema", "definition",
        "definition_id", "definition_sha256", "definition_payload_sha256",
        "definition_byte_count", "source_stock_spec_id",
        "source_stock_spec_sha256", "source_evaluation_id",
        "source_parent_plan_id", "source_parent_plan_sha256",
        "source_fold_manifest_id", "source_fold_manifest_sha256",
        "bootstrap_base_ancestry_sha256", "runtime_action_authority",
        "_canonical_document",
    )
    definition = _definition()
    binding = build_formal_economic_execution_binding(definition)
    definition_id, binding_id = id(definition), id(binding)
    del binding
    gc.collect()
    assert binding_id not in module._BINDINGS
    del definition
    gc.collect()
    assert definition_id not in module._DEFINITIONS


def _closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    return cells[name].cell_contents


def test_reflected_economic_authority_register_cannot_self_mint():
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    value = object.__new__(FormalEconomicExecutionDefinition)
    with pytest.raises(
        FormalEconomicExecutionDefinitionError, match="register caller changed"
    ):
        module._economic_authority_register(
            "definition", value, (object(), b"{}\n")
        )


def test_reflected_economic_private_registries_are_immutable():
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    register = module._economic_authority_register
    private_entry = _closure_value(register, "private_entry")
    private_registry = _closure_value(private_entry, "private_registry")
    state = _closure_value(private_registry, "private_registries")
    assert type(state) is tuple
    assert not hasattr(state, "append")


def test_public_economic_authority_mirrors_cannot_reseal_private_authority():
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    definition = _definition()
    binding = build_formal_economic_execution_binding(definition)
    for registry, value, require in (
        (
            module._BINDINGS,
            binding,
            require_formal_economic_execution_binding,
        ),
        (
            module._DEFINITIONS,
            definition,
            require_formal_economic_execution_definition,
        ),
    ):
        with module._AUTHORITY_LOCK:
            entry = registry[id(value)]
            replacement = tuple(list(entry))
            assert replacement is not entry
            registry[id(value)] = replacement
        with pytest.raises(
            FormalEconomicExecutionDefinitionError,
            match="builder-authenticated",
        ):
            require(value)
        assert id(value) not in registry
        with module._AUTHORITY_LOCK:
            registry[id(value)] = entry
        with pytest.raises(
            FormalEconomicExecutionDefinitionError,
            match="builder-authenticated",
        ):
            require(value)
        assert id(value) not in registry


def test_exact_h20_axes_continue_until_actual_terminal_liquidation_sessions():
    definition = _definition()
    binding = build_formal_economic_execution_binding(definition)
    folds = definition.to_record()["sample_and_clock"]["fold_geometry"]
    assert [item["decision_session_count"] for item in folds] == [
        233, 232, 231, 230, 232, 230,
    ]
    assert sum(item["decision_session_count"] for item in folds) == 1_388
    assert [item["return_interval_count"] for item in folds] == [
        252, 251, 250, 249, 251, 249,
    ]
    assert [
        item["economic_observation_count_including_terminal_cost"] for item in folds
    ] == [253, 252, 251, 250, 252, 250]
    assert [item["terminal_liquidation_session"] for item in folds] == [
        "2021-02-01", "2022-01-31", "2023-01-31",
        "2024-01-30", "2025-01-31", "2026-01-30",
    ]
    assert formal_economic_terminal_liquidation_session(binding) == "2026-01-30"
    assert all(
        item["return_interval_count"] == item["decision_session_count"] + 19
        for item in folds
    )
    assert all(
        item["economic_observation_count_including_terminal_cost"]
        == item["decision_session_count"] + 20
        for item in folds
    )
    policy = _definition().to_record()["terminal_and_refusal_handling"]
    assert policy["prior_session_cost_backcharge"] == "forbidden"
    assert "actual_terminal_liquidation_session" in policy["terminal_liquidation_cost"]


def test_selection_sleeves_cash_and_leverage_are_exact():
    record = _definition().to_record()
    selection = record["eligible_ranking_and_sleeves"]
    assert selection["quintile_count"] == (
        "ceil(strictly_positive_scored_row_count_divided_by_5)"
    )
    assert selection["minimum_sleeve_size"] == 5
    assert selection["sleeve_capital_fraction"] == {"numerator": 1, "denominator": 20}
    assert selection["holding_return_intervals"] == 20
    assert selection["under_minimum"] == (
        "entire_new_one_twentieth_sleeve_remains_cash"
    )
    costs = record["turnover_cost_and_wealth_state"]
    assert costs["cost_bps_per_side_grid"] == list(COST_BPS_PER_SIDE)
    assert costs["primary_cost_bps_per_side"] == 10
    assert costs["half_turnover_convention"] is False
    assert costs["leverage"] is False
    assert costs["short_positions"] is False
    assert costs["borrowed_cash"] is False


def test_liquidity_impact_is_explicitly_unbound_and_diagnostic_only():
    scope = _definition().to_record()["liquidity_impact_scope"]
    assert scope == {
        "liquidity_impact_binding_sha256": None,
        "binding_status": "absent",
        "role": "capacity_diagnostic_only_never_promotion_gate",
        "missing_binding_blocks_primary_execution_definition": False,
        "may_replace_rescue_or_modify_the_primary_cost_gate": False,
        "liquidity_or_market_impact_execution_authority": False,
        "provider_outcome_qc_result_or_trading_authority": False,
    }


def test_daily_total_return_names_do_not_conflate_geometric_relative_return():
    arithmetic = _definition().to_record()["daily_arithmetic_and_naming"]
    assert arithmetic["net_excess_daily_total_return"] == (
        "net_portfolio_daily_total_return_minus_benchmark_daily_total_return"
    )
    assert arithmetic["primary_statistic_exact_name"] == (
        "mean_net_excess_daily_total_return"
    )
    assert arithmetic["cumulative_net_portfolio_total_return"].startswith(
        "product_over_valid_complete_path"
    )
    assert arithmetic["geometric_relative_total_return"] == (
        "one_plus_cumulative_net_portfolio_total_return_divided_by_one_plus_"
        "cumulative_benchmark_total_return_minus_one"
    )
    assert arithmetic["forbidden_ambiguous_name"] == (
        "cumulative_net_excess_total_return"
    )
    assert arithmetic["forbidden_relative_formula"].startswith("product_of_one_plus")


def test_turnover_terminal_benchmark_and_refusal_semantics_are_closed():
    record = _definition().to_record()
    turnover = record["turnover_cost_and_wealth_state"]
    assert turnover["daily_turnover_exact_name"] == (
        "gross_traded_notional_fraction_of_pretrade_NAV"
    )
    assert turnover["zero_target_changes_retained"] is True
    assert turnover["initial_entry_cost_included"] is True
    terminal = record["terminal_and_refusal_handling"]
    assert terminal["terminal_disposition_precedes_ordinary_daily_bar"] is True
    assert terminal["qc_delisting_price_is_terminal_payoff"] is False
    assert terminal["restart_after_state_loss"] == "forbidden"
    assert terminal["cross_fold_wealth_or_sleeve_carry"] == "forbidden"
    assert terminal["post_terminal_active_sleeve_treatment"] == (
        "remove_only_the_named_terminal_security_at_its_actual_terminal_session_"
        "and_hold_its_remaining_active_sleeve_weight_as_cash_through_scheduled_"
        "exit_without_redistribution"
    )
    assert "not_zero_filled" in terminal["missing_benchmark_return"]
    assert "excludes_the_entire_independent_fold" in (
        terminal["unresolved_terminal_or_missing_held_security_return"]
    )


def test_hac_bootstrap_seed_and_complete_session_sampler_are_exact():
    inference = _definition().to_record()["inference"]
    assert inference["hac"] == {
        "role": "descriptive_only_not_a_separate_gate",
        "lag_sessions": 20,
        "axis": "actual_NYSE_session_positions_never_compress_named_gaps",
        "kernel": "Bartlett",
        "lag_weight": "(20_plus_1_minus_lag)_divided_by_(20_plus_1)",
        "autocovariance_denominator": "total_valid_session_count_not_lag_pair_count",
        "observed_pair_count_by_lag_required": True,
    }
    bootstrap = inference["centered_complete_session_moving_block_bootstrap"]
    assert bootstrap["block_length_sessions"] == 20
    assert bootstrap["resamples"] == BOOTSTRAP_RESAMPLES
    assert "all_20_consecutive_expected_NYSE_sessions" in (
        bootstrap["eligible_block_start"]
    )
    assert bootstrap["fold_boundaries_never_crossed"] is True
    assert bootstrap["retry_or_seed_change_after_outcome"] == "forbidden"
    assert bootstrap["base_seed_ancestry_is_operative"] is False
    assert hashlib.sha256(
        _canonical(bootstrap["base_seed_ancestry_record"])
    ).hexdigest() == (
        bootstrap["base_seed_ancestry_sha256"]
    )
    operative = bootstrap["sole_operative_seed_and_draw_authority"]
    assert operative["schema"] == "arv2-formal-report-execution-contract-v1"
    assert operative["seed_record_path"] == (
        "bootstrap.stock_FM_and_economic_seed_record"
    )
    assert operative["seed_domain"] == "arv2-stock-formal-bootstrap-seed-v1"
    assert operative["draw_domain"] == (
        "arv2-stock-formal-noncircular-mbb-hash-counter-v1"
    )
    assert operative[
        "economic_definition_sha256_must_equal_this_authenticated_definition"
    ] is True


def test_every_coverage_turnover_and_overlap_denominator_is_named():
    denominators = _definition().to_record()["exact_denominators"]
    assert set(denominators) == {
        "eligible_ranking_coverage", "scored_ranking_coverage",
        "positive_score_share", "selected_name_share", "sleeve_disposition",
        "daily_return_coverage", "mean_daily_turnover", "overlap_membership",
        "overlap_duplicate_numerator", "overlap_zero_denominator",
        "source_views_and_folds_reported_separately",
        "silent_drop_skip_imputation_or_zero_fill",
    }
    assert denominators["source_views_and_folds_reported_separately"] is True
    assert denominators["overlap_zero_denominator"] == (
        "report_named_unavailable_not_zero"
    )
    assert denominators["sleeve_disposition"] == (
        "every_expected_H20_decision_session_exactly_selected_or_cash_underfill_"
        "with_row_refusals_accounted_separately"
    )
    assert denominators["silent_drop_skip_imputation_or_zero_fill"] == "forbidden"


def test_all_external_action_capabilities_are_literal_false():
    capabilities = _definition().to_record()["capabilities"]
    assert capabilities
    assert all(type(value) is bool and value is False for value in capabilities.values())
    assert _binding().runtime_action_authority is False


def test_module_closure_mutation_refuses_before_artifact_construction(monkeypatch):
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    monkeypatch.setattr(module, "MINIMUM_SLEEVE_SIZE", 4)
    with pytest.raises(
        FormalEconomicExecutionDefinitionError,
        match="module closure changed",
    ):
        build_formal_economic_execution_definition(_stock())


def test_module_closure_refuses_replaced_calendar_dependency_without_calling_it(
    monkeypatch,
):
    import research.analyst_revisions_v2_qc.formal_economic_execution_definition as module

    hostile_calls = 0

    def hostile(*_args, **_kwargs):
        nonlocal hostile_calls
        hostile_calls += 1
        return ()

    monkeypatch.setattr(module, "trading_sessions", hostile)
    with pytest.raises(
        FormalEconomicExecutionDefinitionError,
        match="container closure changed",
    ):
        build_formal_economic_execution_definition(_stock())
    assert hostile_calls == 0


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("eligible_ranking_and_sleeves", "minimum_sleeve_size"), 4),
        (("turnover_cost_and_wealth_state", "primary_cost_bps_per_side"), 5),
        (("turnover_cost_and_wealth_state", "leverage"), True),
        (("terminal_and_refusal_handling", "prior_session_cost_backcharge"), "allowed"),
        (("inference", "hac", "lag_sessions"), 19),
        (("inference", "centered_complete_session_moving_block_bootstrap", "resamples"), 20_000),
    ],
)
def test_semantic_tampering_refuses_even_with_recomputed_public_identity(path, replacement):
    stock = _stock()
    payload = json.loads(
        render_formal_economic_execution_definition_bytes(
            build_formal_economic_execution_definition(stock)
        )
    )
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    payload["definition_id"] = None
    payload["definition_sha256"] = None
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    payload["definition_id"] = "arv2-formal-economic-execution-" + digest[:24]
    payload["definition_sha256"] = digest
    with pytest.raises(
        FormalEconomicExecutionDefinitionError,
        match="changed from the canonical candidate",
    ):
        load_formal_economic_execution_definition(
            source_stock_contract=stock, payload=_canonical(payload)
        )


@pytest.mark.parametrize("nested", [False, True])
def test_unknown_fields_refuse_at_every_level(nested):
    stock = _stock()
    payload = json.loads(
        render_formal_economic_execution_definition_bytes(
            build_formal_economic_execution_definition(stock)
        )
    )
    target = payload["daily_arithmetic_and_naming"] if nested else payload
    target["unexpected"] = False
    payload["definition_id"] = None
    payload["definition_sha256"] = None
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    payload["definition_id"] = "arv2-formal-economic-execution-" + digest[:24]
    payload["definition_sha256"] = digest
    with pytest.raises(FormalEconomicExecutionDefinitionError):
        load_formal_economic_execution_definition(
            source_stock_contract=stock, payload=_canonical(payload)
        )


def test_duplicate_keys_binary_floats_and_nonfinite_json_refuse():
    stock = _stock()
    valid = render_formal_economic_execution_definition_bytes(
        build_formal_economic_execution_definition(stock)
    )
    duplicate = valid.replace(
        b'{"authority":', b'{"authority":"duplicate","authority":', 1
    )
    for payload in (duplicate, b'{"value":1.5}\n', b'{"value":NaN}\n'):
        with pytest.raises(FormalEconomicExecutionDefinitionError):
            load_formal_economic_execution_definition(
                source_stock_contract=stock, payload=payload
            )


def test_public_clone_and_post_build_mutation_cannot_mint_authority():
    value = _definition()
    clone = object.__new__(FormalEconomicExecutionDefinition)
    for field in value.__dataclass_fields__:
        object.__setattr__(clone, field, getattr(value, field))
    with pytest.raises(FormalEconomicExecutionDefinitionError, match="builder-authenticated"):
        require_formal_economic_execution_definition(clone)

    binding = build_formal_economic_execution_binding(value)
    object.__setattr__(binding, "definition_sha256", "0" * 64)
    with pytest.raises(FormalEconomicExecutionDefinitionError, match="binding changed"):
        require_formal_economic_execution_binding(binding)


def test_binding_strongly_retains_and_reauthenticates_definition_parents():
    stock = _stock()
    definition = build_formal_economic_execution_definition(stock)
    binding = build_formal_economic_execution_binding(definition)
    definition_id = definition.definition_id
    del stock, definition
    gc.collect()
    assert binding.definition.definition_id == definition_id
    assert require_formal_economic_execution_binding(binding) is binding
    record = binding.to_record()
    seed = dict(record)
    seed["binding_id"] = None
    seed["binding_sha256"] = None
    assert hashlib.sha256(_canonical(seed)).hexdigest() == binding.binding_sha256


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork boundary")
def test_process_authorities_reject_in_fork_child_and_remain_valid_in_parent():
    definition = _definition()
    binding = build_formal_economic_execution_binding(definition)
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        results = []
        for callback, value in (
            (require_formal_economic_execution_definition, definition),
            (require_formal_economic_execution_binding, binding),
        ):
            try:
                callback(value)
            except FormalEconomicExecutionDefinitionError:
                results.append("refused")
            else:
                results.append("accepted")
        os.write(write_fd, ",".join(results).encode("ascii"))
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    outcome = os.read(read_fd, 1024)
    os.close(read_fd)
    _, status = os.waitpid(pid, 0)
    assert status == 0
    assert outcome == b"refused,refused"
    assert require_formal_economic_execution_definition(definition) is definition
    assert require_formal_economic_execution_binding(binding) is binding
