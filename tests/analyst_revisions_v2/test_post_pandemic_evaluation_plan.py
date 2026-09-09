from __future__ import annotations

import ast
import copy
import dataclasses
import errno
import gc
import hashlib
import json
import os
import pickle
import weakref
from datetime import date
from pathlib import Path

import pytest

from data.exchange_calendar import resolve_nth_session_after, trading_sessions
import research.analyst_revisions_v2.post_pandemic_evaluation_plan as plan_module
from research.analyst_revisions_v2.import_firewall import (
    validate_transitive_import_closure,
)
from research.analyst_revisions_v2.post_pandemic_evaluation_plan import (
    PostPandemicEvaluationPlan,
    PostPandemicEvaluationPlanError,
    load_post_pandemic_evaluation_plan,
    require_loaded_post_pandemic_evaluation_plan,
)


ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "research" / "analyst_revisions_v2" / "specs"
PLAN = SPEC_DIR / "arv2_stock_post_pandemic_evaluation.structural.json"
FOLDS = SPEC_DIR / "arv2_stock_walk_forward_folds.structural.json"
STOCK = SPEC_DIR / "arv2_stock_historical.structural.json"
QC_PLAN = SPEC_DIR / "arv2_qc_first.draft.json"
ROUND0 = SPEC_DIR / "arv2_round0.draft.json"
SECTION_NAMES = (
    "naming_contract",
    "owner_partial_2026_amendment_contract",
    "inherited_evaluation_rules_contract",
    "power_and_sufficiency_reporting_contract",
    "primary_evaluation_contract",
    "post_pandemic_complete_contract",
    "partial_2026_exploratory_contract",
    "fixed_cutoff_lock_contract",
    "future_shared_holdout_contract",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _load(path: Path = PLAN):
    return load_post_pandemic_evaluation_plan(
        path,
        fold_manifest_path=FOLDS,
        stock_evaluation_path=STOCK,
        qc_first_plan_path=QC_PLAN,
    )


def _rehash(raw: dict[str, object]) -> None:
    partial = raw["partial_2026_exploratory_contract"]
    for boundary in partial["eligible_decision_bounds"]:
        boundary["boundary_sha256"] = None
        boundary["boundary_sha256"] = hashlib.sha256(
            _canonical(boundary)
        ).hexdigest()
    partial["boundary_set_sha256"] = hashlib.sha256(
        _canonical(partial["eligible_decision_bounds"])
    ).hexdigest()
    partial["partial_window_sha256"] = None
    partial["partial_window_sha256"] = hashlib.sha256(
        _canonical(partial)
    ).hexdigest()
    raw["section_hashes"] = {
        name: hashlib.sha256(_canonical(raw[name])).hexdigest()
        for name in SECTION_NAMES
    }
    raw["plan_id"] = None
    raw["plan_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["plan_hash"] = digest
    raw["plan_id"] = f"arv2-stock-post-pandemic-{digest[:16]}"


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / PLAN.name
    path.write_bytes(
        (
            json.dumps(
                raw,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    return path


def _copy_graph(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    targets = []
    for source in (PLAN, FOLDS, STOCK, QC_PLAN, ROUND0):
        target = tmp_path / source.name
        target.write_bytes(source.read_bytes())
        targets.append(target)
    return targets[0], targets[1], targets[2], targets[3]


def _is_link_capability_error(exc: OSError) -> bool:
    unsupported = {errno.EACCES, errno.EPERM, errno.ENOSYS}
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported.add(value)
    return getattr(exc, "winerror", None) in {1, 5, 50, 1314} or (
        exc.errno in unsupported
    )


def _symlink_or_skip(
    link: Path, target: Path, *, target_is_directory: bool = False
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        if _is_link_capability_error(exc):
            pytest.skip(f"host cannot create a symlink: {exc}")
        raise


def _junction_or_skip(link: Path, target: Path) -> None:
    try:
        import _winapi
    except ImportError:
        pytest.skip("directory junctions are Windows-only")
    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError as exc:
        if _is_link_capability_error(exc):
            pytest.skip(f"host cannot create a junction: {exc}")
        raise
    assert link.is_junction()


def test_repository_artifact_has_exact_content_and_parent_identity() -> None:
    plan = _load()

    assert plan.plan_id == "arv2-stock-post-pandemic-306ee0b427137cf6"
    assert plan.plan_hash == (
        "306ee0b427137cf6a2bd9a9576b472210fb46ccc77dadfda23f7fd60760fc62a"
    )
    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == (
        "caa837b1e2797095dcb4cf5f30e21b72cc9d4254ff851a4fe5fb8779678e5e14"
    )
    assert PLAN.read_text(encoding="utf-8") == plan_module._render_expected_document()
    assert plan.parent_fold_manifest == {
        "artifact_id": "arv2-stock-folds-1002155dbe8e3e87",
        "content_sha256": (
            "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
        ),
        "artifact_sha256": hashlib.sha256(FOLDS.read_bytes()).hexdigest(),
    }
    assert plan.parent_lineages["qc_first_plan"]["artifact_sha256"] == (
        hashlib.sha256(QC_PLAN.read_bytes()).hexdigest()
    )
    assert plan.parent_lineages["stock_evaluation_contract"][
        "artifact_sha256"
    ] == hashlib.sha256(STOCK.read_bytes()).hexdigest()


def test_primary_stays_2020_2025_and_complete_sensitivity_is_exact() -> None:
    plan = _load()
    primary = plan.primary_evaluation_contract
    complete = plan.post_pandemic_complete_contract

    assert primary["ordered_complete_fold_ids"] == tuple(
        f"arv2-wf-test-{year}" for year in range(2020, 2026)
    )
    assert primary["ordered_horizons_sessions"] == (1, 5, 20, 60)
    assert primary["replacement_or_reselection"] is False
    assert complete["ordered_parent_fold_ids"] == tuple(
        f"arv2-wf-test-{year}" for year in range(2021, 2026)
    )
    assert complete["ordered_h20_fold_ids"] == tuple(
        f"arv2-wf-test-{year}-h20" for year in range(2021, 2026)
    )
    assert complete["primary_sensitivity_horizon_sessions"] == 20
    assert complete["secondary_descriptive_horizons_sessions"] == (1, 5, 60)
    assert complete["parent_horizon_order_sessions"] == (1, 5, 20, 60)
    assert tuple(
        item["test_year"] for item in complete["selected_complete_h20_folds"]
    ) == tuple(range(2021, 2026))
    assert "forbidden" in complete["cross_horizon_pooling"]
    for forbidden in (
        "primary_result_rescue",
        "secondary_result_rescue",
        "threshold_model_or_universe_tuning",
    ):
        assert "forbidden" in complete[forbidden]
    aggregation = complete["complete_fold_aggregation_contract"]
    assert aggregation["ordered_parent_fold_ids"] == complete[
        "ordered_parent_fold_ids"
    ]
    assert aggregation["per_fold_and_calendar_year_reporting_required"] is True
    assert aggregation["observation_interval_rule"] == (
        "for_each_horizon_use_only_exact_authenticated_parent_boundary_"
        "test_start_through_test_end_exclusive"
    )
    assert aggregation["partial_2026_included"] is False
    assert aggregation["pooled_inferential_p_value_or_gate_permitted"] is False
    assert aggregation[
        "gate_rescue_tuning_or_threshold_selection_permitted"
    ] is False
    assert aggregation["unique_session_and_outcome_identity_required"] is True
    assert aggregation["valid_structural_no_position_return"] == (
        "follow_exact_parent_semantics"
    )
    assert aggregation["refusal_underfill_or_missing_expected_session"] == (
        "retain_every_expected_session_and_refusal_in_census_and_coverage_never_"
        "silently_drop_skip_or_zero_fill_metric_denominator_exclusion_only_under_"
        "exact_parent_named_refusal_rule"
    )
    assert aggregation["incomplete_aggregate_disposition"].endswith(
        "aggregate_is_unavailable"
    )
    assert aggregation[
        "aggregate_completeness_and_coverage_report_required"
    ] is True
    assert aggregation[
        "portfolio_return_fold_initial_and_terminal_costs_included"
    ] is True
    assert aggregation["fold_state_resets_disclosed"] is True
    assert aggregation["capital_path_interpretation"] == (
        "not_uninterrupted_live_capital"
    )
    assert complete["implementation_outcome_rows_accessed"] is False
    assert complete["selection_claimed_blind_to_market_outcomes"] is False


def test_partial_2026_is_fixed_separate_and_calendar_derived() -> None:
    plan = _load()
    naming = plan.naming_contract
    partial = plan.partial_2026_exploratory_contract
    cutoff_lock = plan.fixed_cutoff_lock_contract

    assert naming["interpretation"] == (
        "owner_shorthand_for_fixed_2021_through_2026_market_slice"
    )
    assert naming["epidemiological_regime_claim"] is False
    assert naming["dynamic_rolling_now_boundary"] is False
    assert partial["outcome_cutoff_session"] == "2026-08-28"
    assert partial["fold_id"] is None
    assert partial["result_binding_id"] is None
    assert partial["pool_with_complete_folds"] is False
    assert partial["pool_with_primary_evaluation"] is False
    assert partial["rescue_or_override_any_gate"] is False
    assert partial["tune_or_select_from_partial_results"] is False
    assert partial["blind_extension_to_later_outcomes"] is False

    assert partial["rolling_or_expanding_rule"] == "rolling"
    assert partial["nominal_train_interval"] == {
        "start_inclusive": "2019-01-02",
        "end_exclusive": "2024-01-02",
    }
    assert partial["nominal_validation_interval"] == {
        "start_inclusive": "2024-01-02",
        "end_exclusive": "2026-01-02",
    }
    assert partial["fit_contract"] == {
        "fit_scope": "training_only",
        "validation_application": "frozen_coefficients_model_and_thresholds",
        "test_application": "frozen_coefficients_model_and_thresholds",
        "validation_or_test_refit": False,
    }
    expected = (
        (1, "2024-01-03", "2026-01-05", "2026-08-27", "2026-08-28", 163),
        (5, "2024-01-09", "2026-01-09", "2026-08-21", "2026-08-24", 155),
        (20, "2024-01-31", "2026-02-02", "2026-07-31", "2026-08-03", 125),
        (60, "2024-03-28", "2026-03-31", "2026-06-03", "2026-06-04", 45),
    )
    observed = tuple(
        (
            item["horizon_sessions"],
            item["validation_start"],
            item["effective_test_start"],
            item["last_mature_decision_session"],
            item["test_end_exclusive"],
            item["eligible_decision_session_count"],
        )
        for item in partial["eligible_decision_bounds"]
    )
    assert observed == expected
    for horizon, validation_start, start, end, end_exclusive, count in expected:
        assert resolve_nth_session_after("2024-01-02", horizon) == validation_start
        assert resolve_nth_session_after("2026-01-02", horizon) == start
        assert resolve_nth_session_after(end, horizon) == "2026-08-28"
        assert resolve_nth_session_after(end, 1) == end_exclusive
        assert len(
            trading_sessions(date.fromisoformat(start), date.fromisoformat(end))
        ) == count
    assert cutoff_lock["outcome_cutoff_session"] == "2026-08-28"
    assert cutoff_lock["first_post_cutoff_session"] == "2026-08-31"
    assert cutoff_lock["blind_extension"] is False
    boundary_records = [dict(item) for item in partial["eligible_decision_bounds"]]
    for boundary in boundary_records:
        declared = boundary["boundary_sha256"]
        boundary["boundary_sha256"] = None
        assert hashlib.sha256(_canonical(boundary)).hexdigest() == declared
    assert partial["boundary_set_sha256"] == hashlib.sha256(
        _canonical([dict(item) for item in partial["eligible_decision_bounds"]])
    ).hexdigest()
    window = plan_module._thaw(partial)
    declared_window = window["partial_window_sha256"]
    window["partial_window_sha256"] = None
    assert hashlib.sha256(_canonical(window)).hexdigest() == declared_window


def test_shared_holdout_is_not_confused_with_the_fixed_cutoff_lock() -> None:
    holdout = _load().future_shared_holdout_contract

    assert holdout["legacy_validation_period_start_inclusive"] == "2026-09-01"
    assert holdout["legacy_validation_period_end_inclusive"] == "2027-08-31"
    assert holdout["legacy_validation_period_disposition"] == (
        "superseded_unspent_by_owner_qc_first_direction"
    )
    assert holdout["legacy_validation_period_revivable_by_this_supplement"] is False
    assert holdout["future_paper_period_start_inclusive"] is None
    assert holdout["future_paper_period_end_inclusive"] is None
    assert holdout["future_paper_period_authority_id"] is None
    assert holdout["shared_final_holdout_cutoff_inclusive"] == "2027-08-31"
    assert holdout["shared_final_holdout_start_inclusive"] == "2027-09-01"
    assert holdout["shared_final_holdout_end_inclusive"] == "2029-08-31"
    assert holdout["consumed_by_this_supplement"] is False
    assert holdout["consumption_by_this_lane_prohibited"] is True
    assert holdout["current_access_authorized"] is False
    assert holdout["scope"] == (
        "shared_final_holdout_across_all_four_canonical_strategy_families"
    )
    assert "2026-08-31" not in tuple(holdout.values())


def test_owner_amendment_and_inherited_evidence_limits_are_explicit() -> None:
    plan = _load()
    amendment = plan.owner_partial_2026_amendment_contract
    inherited = plan.inherited_evaluation_rules_contract

    assert amendment["owner_direction_date"] == "2026-09-08"
    assert amendment["parent_fold_clause"] == (
        "excluded_from_fixed_cutoff_evaluation_locked_no_blind_extension"
    )
    assert amendment["parent_stock_clause"] == (
        "exclude_from_test_fold_until_full_test_interval_exists"
    )
    assert amendment["parent_artifacts_remain_byte_unchanged"] is True
    assert amendment["semantic_override_of_parent_partial_exclusion"] is True
    assert amendment["rewrites_parent_fold_manifest"] is False
    assert amendment["promotes_partial_slice_to_parent_fold"] is False
    assert inherited["evidence_role"] == (
        "development_stop_go_not_prospective_confirmation"
    )
    assert inherited["contamination_disclosure"] == (
        "2019-07-16_through_2026-07-23_is_discovery_only_all_historical_"
        "inference_is_descriptive"
    )
    assert inherited["confirmatory_or_prospective_claim_permitted"] is False
    assert inherited[
        "first_selected_2021_fold_uses_pre_2021_train_and_validation_inputs"
    ] is True
    assert inherited["historical_point_in_time_inputs_remain_required"] is True
    assert inherited[
        "post_pandemic_slice_waives_historical_point_in_time_requirements"
    ] is False
    power = plan.power_and_sufficiency_reporting_contract
    assert power["power_floor_receipt_id"] is None
    assert power["required_independent_date_floor"] is None
    assert power["required_connected_component_floor"] is None
    assert power[
        "current_claim_to_meet_ARV2_4D_power_date_or_component_floors"
    ] is False
    assert power["each_report_required_fields"] == (
        "evaluation_id",
        "report_slice_id",
        "horizon_sessions",
        "independent_observation_unit",
        "observed_independent_date_count",
        "required_independent_date_count",
        "observed_connected_component_count",
        "required_connected_component_count",
        "sufficient",
        "insufficiency_reasons",
    )
    assert power["creates_new_gate_rescue_or_selection_authority"] is False


def test_every_binding_and_capability_is_closed_and_nested_state_is_immutable() -> None:
    plan = _load()

    assert len(plan.external_bindings) == 15
    assert all(value is None for value in plan.external_bindings.values())
    assert len(plan.capabilities) == 10
    assert all(value is False for value in plan.capabilities.values())
    assert plan.source_access_available is False
    assert plan.outcome_access_available is False
    assert plan.qc_action_available is False
    assert plan.result_access_available is False
    assert plan.result_disposition_available is False
    assert plan.deployment_available is False
    assert plan.orders_available is False
    with pytest.raises(TypeError):
        plan.capabilities["outcome_access"] = True
    with pytest.raises(TypeError):
        plan.post_pandemic_complete_contract["selected_complete_h20_folds"][0][
            "test_year"
        ] = 2020


def test_action_accessors_are_literal_false_returns() -> None:
    source = Path(plan_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    klass = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "PostPandemicEvaluationPlan"
    )
    expected = {
        "source_access_available",
        "outcome_access_available",
        "qc_action_available",
        "result_access_available",
        "result_disposition_available",
        "deployment_available",
        "orders_available",
    }
    methods = {
        node.name: node
        for node in klass.body
        if isinstance(node, ast.FunctionDef) and node.name in expected
    }
    assert set(methods) == expected
    for method in methods.values():
        assert len(method.body) == 1
        assert isinstance(method.body[0], ast.Return)
        assert isinstance(method.body[0].value, ast.Constant)
        assert method.body[0].value.value is False


def _drop_primary_2020(raw: dict[str, object]) -> None:
    raw["primary_evaluation_contract"]["ordered_complete_fold_ids"].pop(0)


def _reorder_complete_folds(raw: dict[str, object]) -> None:
    section = raw["post_pandemic_complete_contract"]
    section["ordered_parent_fold_ids"].reverse()
    section["ordered_h20_fold_ids"].reverse()
    section["selected_complete_h20_folds"].reverse()


def _drift_partial_train(raw: dict[str, object]) -> None:
    partial = raw["partial_2026_exploratory_contract"]
    partial["nominal_train_interval"]["start_inclusive"] = "2019-01-03"
    for boundary in partial["eligible_decision_bounds"]:
        boundary["train_start"] = "2019-01-03"


def _drift_partial_validation(raw: dict[str, object]) -> None:
    raw["partial_2026_exploratory_contract"]["nominal_validation_interval"][
        "start_inclusive"
    ] = "2024-01-03"


def _weaken_partial_gap(raw: dict[str, object]) -> None:
    boundary = raw["partial_2026_exploratory_contract"][
        "eligible_decision_bounds"
    ][2]
    boundary["purge_sessions"] = 5
    boundary["embargo_sessions"] = 5


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda raw: raw.update(status="reviewed_executable"), id="status"),
        pytest.param(lambda raw: raw.update(authority="outcome_authority"), id="authority"),
        pytest.param(
            lambda raw: raw["parent_fold_manifest"].update(content_sha256="a" * 64),
            id="parent-content",
        ),
        pytest.param(_drop_primary_2020, id="replace-primary"),
        pytest.param(_reorder_complete_folds, id="reorder-complete"),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"].update(
                primary_sensitivity_horizon_sessions=5
            ),
            id="change-primary-horizon",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"].update(
                secondary_descriptive_horizons_sessions=[1, 60]
            ),
            id="drop-secondary-horizon",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(partial_2026_included=True),
            id="aggregate-partial",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(pooled_inferential_p_value_or_gate_permitted=True),
            id="pooled-inference",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(per_fold_and_calendar_year_reporting_required=False),
            id="hide-per-fold",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(unique_session_and_outcome_identity_required=False),
            id="duplicate-outcomes",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(refusal_underfill_or_missing_expected_session="drop"),
            id="drop-refusals",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(
                portfolio_return_fold_initial_and_terminal_costs_included=False
            ),
            id="drop-fold-costs",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(fold_state_resets_disclosed=False),
            id="hide-fold-resets",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"].update(
                primary_result_rescue="allowed"
            ),
            id="rescue-primary",
        ),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"].update(
                outcome_cutoff_session="rolling_now"
            ),
            id="rolling-cutoff",
        ),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"].update(
                fold_id="arv2-wf-test-2026"
            ),
            id="promote-partial-fold",
        ),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"].update(
                pool_with_complete_folds=True
            ),
            id="pool-partial",
        ),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"][
                "eligible_decision_bounds"
            ][2].update(eligible_decision_session_count=126),
            id="partial-count",
        ),
        pytest.param(_drift_partial_train, id="partial-train-drift"),
        pytest.param(_drift_partial_validation, id="partial-validation-drift"),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"].update(
                rolling_or_expanding_rule="expanding"
            ),
            id="partial-expanding",
        ),
        pytest.param(_weaken_partial_gap, id="partial-purge-embargo"),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"][
                "fit_contract"
            ].update(validation_or_test_refit=True),
            id="partial-refit",
        ),
        pytest.param(
            lambda raw: raw["partial_2026_exploratory_contract"][
                "eligible_decision_bounds"
            ][1].update(test_end_exclusive="2026-08-25"),
            id="partial-half-open-end",
        ),
        pytest.param(
            lambda raw: raw["owner_partial_2026_amendment_contract"].update(
                semantic_override_of_parent_partial_exclusion=False
            ),
            id="remove-owner-amendment",
        ),
        pytest.param(
            lambda raw: raw["owner_partial_2026_amendment_contract"].update(
                promotes_partial_slice_to_parent_fold=True
            ),
            id="promote-partial-into-parent",
        ),
        pytest.param(
            lambda raw: raw["inherited_evaluation_rules_contract"].update(
                contamination_disclosure="clean_confirmation_period"
            ),
            id="erase-contamination",
        ),
        pytest.param(
            lambda raw: raw["inherited_evaluation_rules_contract"].update(
                confirmatory_or_prospective_claim_permitted=True
            ),
            id="claim-confirmatory",
        ),
        pytest.param(
            lambda raw: raw["inherited_evaluation_rules_contract"].update(
                post_pandemic_slice_waives_historical_point_in_time_requirements=True
            ),
            id="waive-historical-pit",
        ),
        pytest.param(
            lambda raw: raw["power_and_sufficiency_reporting_contract"].update(
                current_claim_to_meet_ARV2_4D_power_date_or_component_floors=True
            ),
            id="claim-power-floor",
        ),
        pytest.param(
            lambda raw: raw["power_and_sufficiency_reporting_contract"].update(
                creates_new_gate_rescue_or_selection_authority=True
            ),
            id="create-new-gate",
        ),
        pytest.param(
            lambda raw: raw["future_shared_holdout_contract"].update(
                legacy_validation_period_revivable_by_this_supplement=True
            ),
            id="revive-superseded-validation",
        ),
        pytest.param(
            lambda raw: raw["future_shared_holdout_contract"].update(
                future_paper_period_start_inclusive="2026-09-01"
            ),
            id="invent-future-paper-window",
        ),
        pytest.param(
            lambda raw: raw["future_shared_holdout_contract"].update(
                shared_final_holdout_start_inclusive="2027-08-31"
            ),
            id="consume-holdout-edge",
        ),
        pytest.param(
            lambda raw: raw["naming_contract"].update(
                epidemiological_regime_claim=True
            ),
            id="epidemiological-claim",
        ),
        pytest.param(
            lambda raw: raw["external_bindings"].update(outcome_dataset_id="rows"),
            id="bind-outcomes",
        ),
        pytest.param(
            lambda raw: raw["capabilities"].update(qc_launch=True),
            id="open-qc",
        ),
    ],
)
def test_correctly_rehashed_semantic_weakening_refuses(
    tmp_path: Path, mutate
) -> None:
    raw = copy.deepcopy(json.loads(PLAN.read_text(encoding="utf-8")))
    mutate(raw)
    _rehash(raw)
    with pytest.raises(PostPandemicEvaluationPlanError, match="frozen definition"):
        _load(_write(tmp_path, raw))


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        pytest.param(_drift_partial_train, "rolling geometry", id="train-geometry"),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"][
                "complete_fold_aggregation_contract"
            ].update(pooled_inferential_p_value_or_gate_permitted=True),
            "descriptive fold aggregation",
            id="pooled-inference",
        ),
        pytest.param(
            lambda raw: raw["owner_partial_2026_amendment_contract"].update(
                semantic_override_of_parent_partial_exclusion=False
            ),
            "owner amendment",
            id="owner-amendment",
        ),
        pytest.param(
            lambda raw: raw["future_shared_holdout_contract"].update(
                legacy_validation_period_revivable_by_this_supplement=True
            ),
            "superseded validation",
            id="superseded-period",
        ),
        pytest.param(
            lambda raw: raw["future_shared_holdout_contract"].update(
                consumed_by_this_supplement=True
            ),
            "superseded validation",
            id="holdout-consumption",
        ),
        pytest.param(
            lambda raw: raw["inherited_evaluation_rules_contract"].update(
                contamination_disclosure="clean_confirmation_period"
            ),
            "contamination boundary",
            id="contamination",
        ),
        pytest.param(
            lambda raw: raw["inherited_evaluation_rules_contract"].update(
                confirmatory_or_prospective_claim_permitted=True
            ),
            "contamination boundary",
            id="confirmatory-claim",
        ),
        pytest.param(
            lambda raw: raw["post_pandemic_complete_contract"].update(
                selection_claimed_blind_to_market_outcomes=True
            ),
            "descriptive fold aggregation",
            id="blind-selection-overclaim",
        ),
        pytest.param(
            lambda raw: raw["power_and_sufficiency_reporting_contract"].update(
                current_claim_to_meet_ARV2_4D_power_date_or_component_floors=True
            ),
            "power-floor",
            id="power-floor-claim",
        ),
    ],
)
def test_critical_semantic_guards_survive_exact_literal_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    match: str,
) -> None:
    raw = copy.deepcopy(json.loads(PLAN.read_text(encoding="utf-8")))
    mutate(raw)
    _rehash(raw)
    monkeypatch.setattr(plan_module, "_EXPECTED_DOCUMENT", plan_module._freeze(raw))
    with pytest.raises(PostPandemicEvaluationPlanError, match=match):
        _load(_write(tmp_path, raw))


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        (
            ('"schema":', '"schema": "forged",\n  "schema":', 1),
            "duplicate JSON key",
        ),
        (
            ('"calendar_year": 2026', '"calendar_year": 2026.0', 1),
            "binary floating-point",
        ),
        (
            ('"calendar_year": 2026', '"calendar_year": NaN', 1),
            "non-finite JSON",
        ),
    ],
)
def test_duplicate_float_and_nonfinite_json_refuse(
    tmp_path: Path, replacement: tuple[str, str, int], match: str
) -> None:
    path = tmp_path / PLAN.name
    path.write_text(
        PLAN.read_text(encoding="utf-8").replace(*replacement), encoding="utf-8"
    )
    with pytest.raises(PostPandemicEvaluationPlanError, match=match):
        _load(path)


@pytest.mark.parametrize(
    ("transform", "match"),
    [
        (lambda value: b"\xef\xbb\xbf" + value, "BOM"),
        (lambda value: value.replace(b"\n", b"\r\n"), "canonical"),
        (lambda value: b" " + value, "canonical"),
        (lambda value: value + b" ", "canonical"),
    ],
)
def test_bom_and_noncanonical_whitespace_refuse(
    tmp_path: Path, transform, match: str
) -> None:
    path = tmp_path / PLAN.name
    path.write_bytes(transform(PLAN.read_bytes()))
    with pytest.raises(PostPandemicEvaluationPlanError, match=match):
        _load(path)


def test_noncanonical_key_order_and_lone_surrogate_refuse(tmp_path: Path) -> None:
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    schema = raw.pop("schema")
    raw["schema"] = schema
    path = tmp_path / PLAN.name
    path.write_bytes(
        (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    with pytest.raises(PostPandemicEvaluationPlanError, match="canonical"):
        _load(path)

    path.write_text(
        PLAN.read_text(encoding="utf-8").replace(
            '"label": "post_pandemic"', '"label": "\\ud800"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(PostPandemicEvaluationPlanError, match="noncanonical"):
        _load(path)


def test_loader_only_identity_copy_forgery_and_mutation_refuse() -> None:
    plan = _load()

    copied = copy.copy(plan)
    with pytest.raises(PostPandemicEvaluationPlanError, match="loader authority"):
        require_loaded_post_pandemic_evaluation_plan(copied)
    with pytest.raises((TypeError, PostPandemicEvaluationPlanError)):
        copy.deepcopy(plan)
    with pytest.raises((TypeError, pickle.PickleError)):
        pickle.dumps(plan)
    with pytest.raises(TypeError):
        dataclasses.replace(plan)

    forged = object.__new__(PostPandemicEvaluationPlan)
    with pytest.raises(PostPandemicEvaluationPlanError, match="loader-authenticated"):
        require_loaded_post_pandemic_evaluation_plan(forged)

    class Subclass(PostPandemicEvaluationPlan):
        pass

    subclass = object.__new__(Subclass)
    object.__setattr__(
        subclass, "_authority", plan_module._LOADED_POST_PANDEMIC_PLAN_AUTHORITY
    )
    with pytest.raises(PostPandemicEvaluationPlanError, match="loader-authenticated"):
        require_loaded_post_pandemic_evaluation_plan(subclass)

    object.__setattr__(plan, "plan_hash", "a" * 64)
    with pytest.raises(PostPandemicEvaluationPlanError, match="changed after"):
        require_loaded_post_pandemic_evaluation_plan(plan)


def test_authority_registry_forgets_dead_objects() -> None:
    plan = _load()
    identity = id(plan)
    reference = weakref.ref(plan)
    assert identity in plan_module._POST_PANDEMIC_PLAN_AUTHORITIES
    del plan
    gc.collect()
    assert reference() is None
    assert identity not in plan_module._POST_PANDEMIC_PLAN_AUTHORITIES


@pytest.mark.parametrize(
    ("target_index", "match"),
    [
        (0, "post-pandemic plan"),
        (1, "parent fold manifest"),
        (2, "stock-evaluation parent"),
        (3, "QC-first parent"),
    ],
)
def test_reauthentication_detects_source_or_parent_change(
    tmp_path: Path, target_index: int, match: str
) -> None:
    local_plan, local_folds, local_stock, local_qc = _copy_graph(tmp_path)
    plan = load_post_pandemic_evaluation_plan(
        local_plan,
        fold_manifest_path=local_folds,
        stock_evaluation_path=local_stock,
        qc_first_plan_path=local_qc,
    )
    target = (local_plan, local_folds, local_stock, local_qc)[target_index]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(PostPandemicEvaluationPlanError, match=match):
        require_loaded_post_pandemic_evaluation_plan(plan)


def test_initial_load_refuses_wrong_parent_bytes(tmp_path: Path) -> None:
    local_plan, local_folds, local_stock, local_qc = _copy_graph(tmp_path)
    local_folds.write_bytes(local_folds.read_bytes() + b" ")
    with pytest.raises(
        PostPandemicEvaluationPlanError,
        match="parent fold manifest artifact bytes changed",
    ):
        load_post_pandemic_evaluation_plan(
            local_plan,
            fold_manifest_path=local_folds,
            stock_evaluation_path=local_stock,
            qc_first_plan_path=local_qc,
        )


def test_nested_loader_cannot_substitute_forged_secondary_horizon_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = plan_module.load_stock_fold_manifest(
        FOLDS,
        stock_evaluation_path=STOCK,
        qc_first_plan_path=QC_PLAN,
    )
    forged = copy.copy(parent)
    walk_forward = plan_module._thaw(parent.walk_forward_contract)
    fold_2021 = next(
        item for item in walk_forward["folds"] if item["test_year"] == 2021
    )
    boundary_h1 = next(
        item
        for item in fold_2021["horizon_boundaries"]
        if item["horizon_sessions"] == 1
    )
    boundary_h1["test_start"] = "2099-01-01"
    object.__setattr__(
        forged,
        "walk_forward_contract",
        plan_module._freeze(walk_forward),
    )

    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    # This copy preserves every locally pinned top-level and H20 field.  The
    # nested parent's loader registry must therefore remain load-bearing for
    # all inherited secondary-horizon boundaries.
    plan_module._validate_parent_and_semantics(raw, forged)
    monkeypatch.setattr(plan_module, "load_stock_fold_manifest", lambda *a, **k: forged)

    with pytest.raises(
        PostPandemicEvaluationPlanError,
        match="parent fold manifest authentication failed",
    ):
        _load()


def test_bounded_artifact_facade_refuses_oversized_input(tmp_path: Path) -> None:
    path = tmp_path / PLAN.name
    path.write_bytes(b" " * (plan_module.MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(PostPandemicEvaluationPlanError, match="size limit"):
        _load(path)


@pytest.mark.parametrize("linked_role", ["plan", "folds", "stock", "qc"])
def test_each_loader_path_refuses_linked_ancestor_with_platform_link_type(
    tmp_path: Path, linked_role: str
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    _copy_graph(real)
    linked = tmp_path / "linked"
    if os.name == "nt":
        _junction_or_skip(linked, real)
    else:
        _symlink_or_skip(linked, real, target_is_directory=True)
    regular = {
        "plan": real / PLAN.name,
        "folds": real / FOLDS.name,
        "stock": real / STOCK.name,
        "qc": real / QC_PLAN.name,
    }
    selected = dict(regular)
    selected[linked_role] = linked / regular[linked_role].name
    with pytest.raises(PostPandemicEvaluationPlanError, match="link"):
        load_post_pandemic_evaluation_plan(
            selected["plan"],
            fold_manifest_path=selected["folds"],
            stock_evaluation_path=selected["stock"],
            qc_first_plan_path=selected["qc"],
        )


@pytest.mark.parametrize(
    ("target_name", "match"),
    [
        ("plan", "post-pandemic plan changed after authentication"),
        ("folds", "parent fold manifest changed after authentication"),
        ("stock", "stock-evaluation parent changed after authentication"),
        ("qc", "QC-first parent changed after authentication"),
    ],
)
def test_final_parent_revalidation_closes_nested_loader_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
    match: str,
) -> None:
    local_plan, local_folds, local_stock, local_qc = _copy_graph(tmp_path)
    real_validate = plan_module._validate_parent_and_semantics
    mutation_target = {
        "plan": local_plan,
        "folds": local_folds,
        "stock": local_stock,
        "qc": local_qc,
    }[target_name]

    def mutate_after_parent_validation(raw: object, parent: object) -> None:
        real_validate(raw, parent)
        mutation_target.write_bytes(mutation_target.read_bytes() + b" ")

    monkeypatch.setattr(
        plan_module,
        "_validate_parent_and_semantics",
        mutate_after_parent_validation,
    )
    with pytest.raises(
        PostPandemicEvaluationPlanError,
        match=match,
    ):
        load_post_pandemic_evaluation_plan(
            local_plan,
            fold_manifest_path=local_folds,
            stock_evaluation_path=local_stock,
            qc_first_plan_path=local_qc,
        )


def test_plan_is_inside_the_outcome_free_import_closure() -> None:
    reached = validate_transitive_import_closure(ROOT)
    assert "research.analyst_revisions_v2.post_pandemic_evaluation_plan" in reached
    assert "research.quantconnect" not in reached
    assert "backtest" not in reached
    assert "execution" not in reached


def test_equal_comparing_subclasses_cannot_spoof_plan_authority() -> None:
    # ARV2R23-001: the fingerprint must be exact-type, so a field replaced by an
    # equal-comparing (or always-equal) str subclass refuses reauthentication.
    class Equal(str):
        def __eq__(self, other: object) -> bool:
            return True

        __hash__ = str.__hash__

    for field_name, spoof in (
        ("plan_id", str),
        ("plan_hash", Equal),
        ("schema", Equal),
    ):
        plan = _load()
        original = getattr(plan, field_name)
        replacement = spoof(original) if spoof is str else spoof("forged")

        class Same(str):
            pass

        if spoof is str:
            replacement = Same(original)
        object.__setattr__(plan, field_name, replacement)
        with pytest.raises(
            PostPandemicEvaluationPlanError, match="changed after|noncanonical"
        ):
            require_loaded_post_pandemic_evaluation_plan(plan)
    plan = _load()
    nested = dict(plan_module._thaw(plan.capabilities))
    nested["orders"] = 0
    object.__setattr__(plan, "capabilities", plan_module._freeze(nested))
    with pytest.raises(PostPandemicEvaluationPlanError, match="changed after"):
        require_loaded_post_pandemic_evaluation_plan(plan)
