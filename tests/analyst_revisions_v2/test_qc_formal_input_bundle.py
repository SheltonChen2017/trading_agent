from __future__ import annotations

import dataclasses
import inspect
import threading
import weakref

import pytest

from research.analyst_revisions_v2_qc import formal_input_bundle as module


def test_public_scoring_admission_has_no_caller_authored_score_channel():
    legacy = inspect.signature(module.build_formal_production_scoring_census)
    begin = inspect.signature(module.begin_formal_production_scoring_projection)
    consume = inspect.signature(module.iter_formal_production_scoring_result_blocks)
    finish = inspect.signature(module.finish_formal_production_scoring_projection)

    assert tuple(legacy.parameters) == ("scoring_results",)
    assert tuple(begin.parameters) == ("production_truth", "accepted_risk")
    assert tuple(consume.parameters) == ("builder", "result")
    assert tuple(finish.parameters) == ("builder",)
    for signature in (legacy, begin, consume, finish):
        assert "current_scored_lineages" not in signature.parameters
        assert "censored_scored_lineages" not in signature.parameters


def test_projection_contract_is_explicitly_not_upstream_capacity_authority():
    fields = {
        item.name
        for item in dataclasses.fields(module.FormalProductionScoringProjection)
    }
    assert (
        "upstream_truth_and_one_fold_materialization_capacity_authenticated"
        in fields
    )
    assert "production_capacity_disposition" in fields
    source = inspect.getsource(module._ProjectionBuilderState)
    assert "truth: ProductionTruthArtifact" in source
    assert "active_result" in source
    assert "component_dates" not in source
    consume_source = inspect.getsource(
        module.iter_formal_production_scoring_result_blocks
    )
    assert "component_dates" not in consume_source


def test_projection_types_cannot_be_copied_or_caller_minted():
    forged_builder = object.__new__(
        module.FormalProductionScoringProjectionBuilder
    )
    forged_projection = object.__new__(module.FormalProductionScoringProjection)
    forged_block = object.__new__(module.FormalScoringSessionBlock)
    with pytest.raises(module.FormalInputBundleError, match="builder-authenticated"):
        module.finish_formal_production_scoring_projection(forged_builder)
    with pytest.raises(
        module.FormalInputBundleError, match="changed type|builder-authenticated"
    ):
        module.require_formal_production_scoring_projection(forged_projection)
    with pytest.raises(module.FormalInputBundleError, match="builder-authenticated"):
        module.require_formal_scoring_session_block(
            forged_block, builder=forged_builder
        )


def test_forged_scoring_census_is_rejected():
    forged = object.__new__(module.FormalProductionScoringCensus)
    with pytest.raises(module.FormalInputBundleError, match="builder-authenticated"):
        module.require_formal_production_scoring_census(forged)


def test_forged_power_binding_is_rejected_by_pure_postfreeze_gate():
    forged = object.__new__(module.FormalPowerCalibrationBinding)
    with pytest.raises(module.FormalInputBundleError, match="builder-authenticated"):
        module.require_formal_power_calibration_binding(forged)


def test_projection_schema_constants_are_unambiguous():
    assert module.SCORING_PROJECTION_SCHEMA == (
        "arv2-formal-production-scoring-projection-v1"
    )
    assert module.SCORING_SESSION_BLOCK_SCHEMA == (
        "arv2-formal-production-scoring-session-block-v1"
    )
    assert module.SCORING_FOLD_COMMITMENT_SCHEMA == (
        "arv2-formal-scoring-fold-commitment-v1"
    )


def _coverage_for_fold(fold_id: str, source_view_id: str):
    binding = module.ScoringResultBinding(
        fold_id=fold_id,
        result_id=f"result-{fold_id}",
        result_sha256="1" * 64,
        precontrol_batch_id=f"batch-{fold_id}",
        precontrol_batch_sha256="2" * 64,
        model_sha256s=("3" * 64, "4" * 64),
    )
    geometry = module._h20_geometry_for_fold(fold_id)
    ledgers = tuple(
        module._coverage_ledger(ledger_id, 19, 20)
        for ledger_id in module._GLOBAL_COVERAGE_LEDGER_IDS
    )
    return module._build_global_coverage_value(
        schema=module.GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
        scope_id=fold_id,
        source_view_id=source_view_id,
        fold_ids=(fold_id,),
        result_bindings=(binding,),
        h20_test_intervals=((fold_id, geometry[6], geometry[7]),),
        ledgers=ledgers,
        endpoint_status_counts=(
            ("mapped", 40), ("measured_refusal", 0),
            ("unknown", 0), ("invalid", 0),
        ),
        endpoint_pair_status_counts=(
            ("mapped", 20), ("measured_refusal", 0),
            ("unknown", 0), ("invalid", 0),
        ),
        direction_status_counts=(
            ("expected_sign", 18), ("opposite_sign", 1),
            ("zero_delta", 1),
        ),
        raw_canonical_label_counts=(("5" * 64, "6" * 64, "mapped", 40),),
        date_diagnostic_counts=(
            ("firm_totalized_zero_dates", 0),
            ("global_totalized_zero_dates", 0),
            ("both_arms_constant_dates", 1),
            ("score_refused_candidate_dates", 0),
            ("preoutcome_candidate_dates", 20),
        ),
        diagnostic_ratios=(
            module._coverage_ratio("global_tier_collapse_zero_share", 1, 20),
            module._coverage_ratio("global_direction_conflict_share", 1, 20),
            module._coverage_ratio("firm_totalized_zero_date_share", 0, 20),
            module._coverage_ratio("global_totalized_zero_date_share", 0, 20),
            module._coverage_ratio("both_arms_constant_date_share", 1, 20),
        ),
    )


def test_global_comparator_coverage_pools_integer_counts_without_ratio_averaging():
    folds = tuple(
        _coverage_for_fold(fold_id, module.CURRENT_VIEW_LABEL)
        for fold_id in module.FORMAL_PRIMARY_FOLD_IDS
    )
    pooled = module.pool_formal_global_comparator_coverages(folds)

    assert module.require_formal_global_comparator_coverage(pooled) is pooled
    assert pooled.fold_ids == module.FORMAL_PRIMARY_FOLD_IDS
    assert pooled.schema == module.GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA
    assert all(
        (item.numerator, item.denominator, item.passes) == (114, 120, True)
        for item in pooled.ledgers
    )
    assert dict(pooled.endpoint_pair_status_counts) == {
        "mapped": 120,
        "measured_refusal": 0,
        "unknown": 0,
        "invalid": 0,
    }
    assert pooled.diagnostic_ratios[0].numerator == 6
    assert pooled.diagnostic_ratios[0].denominator == 120


def test_global_comparator_coverage_zero_denominator_and_tamper_fail_closed():
    zero = module._coverage_ledger("endpoint_pair_mapping", 0, 0)
    assert zero.disposition == "INVALID_DATA"
    assert zero.reasons == ("zero_denominator",)

    value = _coverage_for_fold(
        module.FORMAL_PRIMARY_FOLD_IDS[0], module.CENSORED_VIEW_LABEL
    )
    object.__setattr__(
        value,
        "endpoint_pair_status_counts",
        (("mapped", 19), ("measured_refusal", 0), ("unknown", 0), ("invalid", 0)),
    )
    with pytest.raises(
        module.FormalInputBundleError,
        match="diagnostic reconciliation|identity",
    ):
        module.require_formal_global_comparator_coverage(value)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("result_id", "bad id with spaces", "result_id"),
        ("precontrol_batch_id", "", "precontrol_batch_id"),
        ("model_sha256s", ("3" * 64,), "model census"),
    ),
)
def test_global_comparator_coverage_rejects_malformed_result_binding(
    field, replacement, message
):
    fold_id = module.FORMAL_PRIMARY_FOLD_IDS[0]
    value = _coverage_for_fold(fold_id, module.CURRENT_VIEW_LABEL)
    forged = dataclasses.replace(
        value.result_bindings[0],
        **{field: replacement},
    )
    object.__setattr__(value, "result_bindings", (forged,))

    with pytest.raises(module.FormalInputBundleError, match=message):
        module.require_formal_global_comparator_coverage(value)


def test_streaming_coverage_api_accepts_sessions_not_caller_counts():
    begin = inspect.signature(
        module.begin_formal_global_comparator_fold_coverage
    )
    record = inspect.signature(
        module.record_formal_global_comparator_coverage_session
    )
    finish = inspect.signature(
        module.finish_formal_global_comparator_fold_coverage
    )
    assert tuple(begin.parameters) == (
        "fold_id", "signal_arm", "batch", "global_contract", "endpoint_labels"
    )
    assert tuple(record.parameters) == (
        "accumulator", "decision_session", "census_rows", "final_rows",
        "final_refusals", "maximum_retained_bytes",
    )
    assert tuple(finish.parameters) == ("accumulator", "result_binding")
    forbidden = {"numerator", "denominator", "passes", "ready", "counts"}
    assert forbidden.isdisjoint(begin.parameters)
    assert forbidden.isdisjoint(record.parameters)
    assert forbidden.isdisjoint(finish.parameters)

    forged = object.__new__(module.FormalGlobalComparatorCoverageAccumulator)
    with pytest.raises(module.FormalInputBundleError, match="builder-authenticated"):
        module.finish_formal_global_comparator_fold_coverage(
            forged,
            result_binding=module.ScoringResultBinding(
                "arv2-wf-test-2020", "result", "1" * 64,
                "batch", "2" * 64, ("3" * 64, "4" * 64),
            ),
        )


def test_coverage_accumulator_is_bound_to_its_builder_thread():
    value = object.__new__(module.FormalGlobalComparatorCoverageAccumulator)
    for name, item in {
        "accumulator_id": "arv2-test-coverage-accumulator",
        "schema": module.GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA,
        "fold_id": module.FORMAL_PRIMARY_FOLD_IDS[0],
        "source_view_id": module.CURRENT_VIEW_LABEL,
    }.items():
        object.__setattr__(value, name, item)
    state = object.__new__(module._GlobalCoverageAccumulatorState)
    source = object.__new__(module.FormalGlobalComparatorCoverageSource)
    for name, item in {
        "source_id": "arv2-test-coverage-source",
        "schema": module.GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA,
        "source_view_id": module.CURRENT_VIEW_LABEL,
    }.items():
        object.__setattr__(source, name, item)
    object.__setattr__(state, "source", source)
    object.__setattr__(state, "pid", module.os.getpid())
    object.__setattr__(state, "owner_thread_id", threading.get_ident())
    static = module._post_canonical_bytes({
        "accumulator_id": value.accumulator_id,
        "schema": value.schema,
        "fold_id": value.fold_id,
        "source_view_id": value.source_view_id,
        "source_id": source.source_id,
    })
    with module._GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
        module._GLOBAL_COVERAGE_ACCUMULATORS[id(value)] = (
            weakref.ref(value), static, state,
        )
    errors = []

    def cross_thread_read():
        try:
            module._require_global_coverage_accumulator(value)
        except Exception as exc:  # exact type asserted below
            errors.append(exc)

    thread = threading.Thread(target=cross_thread_read)
    thread.start()
    thread.join()
    with module._GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
        module._GLOBAL_COVERAGE_ACCUMULATORS.pop(id(value), None)

    assert len(errors) == 1
    assert type(errors[0]) is module.FormalInputBundleError
    assert "changed" in str(errors[0])


def test_component_coverage_requires_exact_event_topology_not_member_overlap():
    firm = module._component_topologies(
        ("security-a", "security-b"),
        (("security-a", "event-x"), ("security-b", "event-x")),
    )
    same = module._component_topologies(
        ("security-a", "security-b"),
        (("security-a", "event-x"), ("security-b", "event-x")),
    )
    changed_event = module._component_topologies(
        ("security-a", "security-b"),
        (("security-a", "event-y"), ("security-b", "event-y")),
    )
    split = module._component_topologies(
        ("security-a", "security-b"), (),
    )
    redundant_firm = module._component_topologies(
        ("security-a", "security-b"),
        (
            ("security-a", "event-x"),
            ("security-b", "event-x"),
            ("security-a", "event-y"),
        ),
    )
    same_nodes_missing_edge = module._component_topologies(
        ("security-a", "security-b"),
        (
            ("security-a", "event-y"),
            ("security-b", "event-x"),
        ),
    )
    assert same == firm
    assert changed_event != firm
    assert split != firm
    assert redundant_firm != same_nodes_missing_edge


def test_component_coverage_never_pads_with_inactive_census_singletons():
    firm = tuple(
        module._FirmBaselineContribution(
            security_id=f"security-{index}",
            common_event_id="event-active",
            eligible_session="2020-01-02",
            linked_c2_row_sha256s=(f"{index + 1:064x}",),
        )
        for index in range(5)
    )

    firm_components, paired_components = module._active_component_topologies(
        firm,
        (),
    )

    assert firm_components == ((
        tuple(f"security-{index}" for index in range(5)),
        ("event-active",),
        tuple(
            (f"security-{index}", "event-active")
            for index in range(5)
        ),
    ),)
    assert paired_components == ()


def test_score_capability_denominator_retains_exact_refused_terminal():
    census = tuple(f"security-{index:02d}" for index in range(20))

    assert module._is_preoutcome_candidate_date(census, census, ()) is True
    assert module._is_preoutcome_candidate_date(
        census,
        census[:-1],
        (census[-1],),
    ) is True
    assert module._is_preoutcome_candidate_date(
        census,
        census[:-1],
        (),
    ) is False
    assert module._is_preoutcome_candidate_date(
        census[:-1],
        census[:-1],
        (),
    ) is False

    baseline = _coverage_for_fold(
        module.FORMAL_PRIMARY_FOLD_IDS[0], module.CURRENT_VIEW_LABEL
    )
    charged = module._build_global_coverage_value(
        schema=baseline.schema,
        scope_id=baseline.scope_id,
        source_view_id=baseline.source_view_id,
        fold_ids=baseline.fold_ids,
        result_bindings=baseline.result_bindings,
        h20_test_intervals=baseline.h20_test_intervals,
        ledgers=baseline.ledgers,
        endpoint_status_counts=baseline.endpoint_status_counts,
        endpoint_pair_status_counts=baseline.endpoint_pair_status_counts,
        direction_status_counts=baseline.direction_status_counts,
        raw_canonical_label_counts=baseline.raw_canonical_label_counts,
        date_diagnostic_counts=(
            ("firm_totalized_zero_dates", 0),
            ("global_totalized_zero_dates", 0),
            ("both_arms_constant_dates", 0),
            ("score_refused_candidate_dates", 1),
            ("preoutcome_candidate_dates", 20),
        ),
        diagnostic_ratios=tuple(
            dataclasses.replace(item, numerator=0)
            if item.ratio_id.endswith("constant_date_share")
            else item
            for item in baseline.diagnostic_ratios
        ),
    )
    assert module.require_formal_global_comparator_coverage(charged) is charged
    assert dict(charged.date_diagnostic_counts)[
        "score_refused_candidate_dates"
    ] == 1


def test_fold_coverage_discards_post_test_contributions_before_axis_check():
    source = inspect.getsource(
        module.begin_formal_global_comparator_fold_coverage_from_source
    )
    assert "item.eligible_session < test_end" in source
    assert "source_state.contributions" in source


def test_global_label_diagnostics_preserve_hashed_raw_form_collisions():
    canonical = "a" * 64
    values = (
        ("1" * 64, canonical, "mapped", 2),
        ("2" * 64, canonical, "mapped", 1),
    )

    normalized, raw, canonical_counts, collisions = (
        module._global_label_diagnostics(values)
    )

    assert normalized == values
    assert raw == (
        ("1" * 64, "mapped", 2),
        ("2" * 64, "mapped", 1),
    )
    assert canonical_counts == ((canonical, "mapped", 3),)
    assert dict(collisions) == {
        "canonical_keys_with_multiple_raw_forms": 1,
        "canonical_keys_with_any_raw_form": 1,
        "endpoint_instances_in_colliding_canonical_keys": 3,
        "canonicalizable_endpoint_instances": 3,
    }


@pytest.mark.parametrize(
    "values",
    (
        (
            ("1" * 64, "2" * 64, "mapped", 1),
            ("1" * 64, "3" * 64, "mapped", 1),
        ),
        (
            ("1" * 64, "2" * 64, "mapped", 1),
            ("3" * 64, "2" * 64, "unknown", 1),
        ),
        (("1" * 64, "0" * 64, "mapped", 1),),
        (("1" * 64, "2" * 64, "invalid", 1),),
    ),
)
def test_global_label_diagnostics_reject_impossible_resolver_maps(values):
    with pytest.raises(module.FormalInputBundleError):
        module._global_label_diagnostics(values)


def test_global_label_diagnostics_reconcile_exact_endpoint_statuses():
    baseline = _coverage_for_fold(
        module.FORMAL_PRIMARY_FOLD_IDS[0], module.CURRENT_VIEW_LABEL
    )
    with pytest.raises(
        module.FormalInputBundleError,
        match="diagnostic reconciliation",
    ):
        module._build_global_coverage_value(
            schema=baseline.schema,
            scope_id=baseline.scope_id,
            source_view_id=baseline.source_view_id,
            fold_ids=baseline.fold_ids,
            result_bindings=baseline.result_bindings,
            h20_test_intervals=baseline.h20_test_intervals,
            ledgers=baseline.ledgers,
            endpoint_status_counts=baseline.endpoint_status_counts,
            endpoint_pair_status_counts=baseline.endpoint_pair_status_counts,
            direction_status_counts=baseline.direction_status_counts,
            raw_canonical_label_counts=(
                ("5" * 64, "6" * 64, "unknown", 40),
            ),
            date_diagnostic_counts=baseline.date_diagnostic_counts,
            diagnostic_ratios=baseline.diagnostic_ratios,
        )
