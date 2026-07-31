"""Tests for ml/experiment_contracts.py (ML-LR-0).

Covers the live-readiness plan's own section 6.3 test list: round trip and
stable hash; behavior-relevant changes alter the hash; nested caller
mutation cannot change a constructed spec; confirmation without a parent is
refused; duplicate variants refused; naive timestamps and non-finite nested
values refused; forbidden execution-shaped fields cannot enter serialized
output; and pure report construction creates no SQLite or execution state.
"""
from __future__ import annotations

import math

import pytest

from ml.experiment_contracts import (
    ConfirmationSpec,
    ExperimentContractError,
    ExperimentIdentity,
    ExperimentRunRecord,
    ExperimentSpec,
    ResearchGateSpec,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _gate(**overrides) -> ResearchGateSpec:
    kwargs = dict(
        minimum_folds_won=2,
        minimum_coverage_fraction=0.8,
        maximum_alpha=0.05,
        block_lengths=(20, 40),
        required_calibration_bins=10,
        failure_slices=("year", "volatility_regime"),
    )
    kwargs.update(overrides)
    return ResearchGateSpec(**kwargs)


def _spec(**overrides) -> ExperimentSpec:
    kwargs = dict(
        experiment_id="volatility-discovery-v1",
        task="volatility_forecast",
        mode="discovery",
        created_at="2026-07-31T00:00:00+00:00",
        primary_outcome="QLIKE vs EWMA baseline",
        candidate_models=("ridge_log_vol", "hist_gradient_boosting"),
        frozen_baselines=("trailing_realized", "ewma"),
        feature_set_version="fs-v1",
        label_version="forward_realized_vol_20d_v1",
        benchmark="QQQ",
        horizon_sessions=20,
        universe_definition="fixed:tech-v1",
        research_look_dimensions={
            "models": ["ridge_log_vol", "hist_gradient_boosting"],
            "horizons": ["20"],
            "benchmarks": ["QQQ"],
        },
        split_configuration={"n_splits": 3, "embargo_sessions": 20},
        cost_tax_liquidity_assumptions={"transaction_cost_bps": 5.0},
        research_gate=_gate(),
        random_seed=0,
    )
    kwargs.update(overrides)
    return ExperimentSpec(**kwargs)


def _confirmation_spec(**overrides) -> ExperimentSpec:
    kwargs = dict(
        experiment_id="volatility-confirmation-v1",
        mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="volatility-discovery-v1",
            parent_spec_hash=_HASH_A,
            parent_report_hash=_HASH_B,
        ),
    )
    kwargs.update(overrides)
    return _spec(**kwargs)


# --- round trip and hashing -------------------------------------------------


def test_spec_round_trips_and_hash_is_stable():
    first, second = _spec(), _spec()
    assert first.to_dict() == second.to_dict()
    assert first.spec_hash == second.spec_hash
    assert len(first.spec_hash) == 64


def test_spec_is_json_serializable():
    import json

    json.dumps(_spec().to_dict())


@pytest.mark.parametrize(
    "overrides",
    [
        {"horizon_sessions": 60},
        {"benchmark": "SOXX"},
        {"random_seed": 1},
        {"label_version": "other_v2"},
        {"universe_definition": "fixed:tech-v2"},
        {"split_configuration": {"n_splits": 5, "embargo_sessions": 20}},
        {"cost_tax_liquidity_assumptions": {"transaction_cost_bps": 10.0}},
    ],
)
def test_behavior_relevant_changes_alter_the_hash(overrides):
    assert _spec().spec_hash != _spec(**overrides).spec_hash


def test_changing_a_research_gate_threshold_alters_the_hash():
    """The gate is part of the hashed identity on purpose: a threshold moved
    after seeing results must produce a DIFFERENT experiment, which is what
    makes 'no moving the goalposts' checkable rather than merely stated."""
    loose = _spec(research_gate=_gate(maximum_alpha=0.10))
    assert _spec().spec_hash != loose.spec_hash


def test_changing_the_confirmation_parent_alters_the_hash():
    other_parent = _confirmation_spec(
        confirmation=ConfirmationSpec(
            parent_experiment_id="volatility-discovery-v1",
            parent_spec_hash=_HASH_C,
            parent_report_hash=_HASH_B,
        )
    )
    assert _confirmation_spec().spec_hash != other_parent.spec_hash


# --- immutability -----------------------------------------------------------


def test_nested_caller_mutation_cannot_change_a_constructed_spec():
    """frozen=True only blocks attribute reassignment. Without a deep
    freeze, a caller holding the original dict could change a cost
    assumption after construction and silently invalidate the spec_hash
    already recorded elsewhere."""
    assumptions = {"transaction_cost_bps": 5.0}
    spec = _spec(cost_tax_liquidity_assumptions=assumptions)
    original_hash = spec.spec_hash

    assumptions["transaction_cost_bps"] = 999.0

    assert spec.cost_tax_liquidity_assumptions["transaction_cost_bps"] == 5.0
    assert spec.spec_hash == original_hash


def test_frozen_nested_mapping_rejects_direct_mutation():
    spec = _spec()
    with pytest.raises(TypeError):
        spec.split_configuration["n_splits"] = 99


def test_research_look_dimension_lists_are_frozen():
    dimensions = {"models": ["a", "b"], "horizons": ["20"]}
    spec = _spec(research_look_dimensions=dimensions)
    dimensions["models"].append("c")
    assert spec.total_research_looks() == 2


# --- research-look derivation ----------------------------------------------


def test_research_looks_derive_from_the_variants_present_in_the_spec():
    spec = _spec(
        research_look_dimensions={
            "models": ["a", "b", "c"],
            "benchmarks": ["QQQ", "SOXX"],
            "horizons": ["5", "20"],
        }
    )
    assert spec.total_research_looks() == 12


def test_adding_a_variant_increases_the_look_count_automatically():
    before = _spec().total_research_looks()
    after = _spec(
        research_look_dimensions={
            "models": ["ridge_log_vol", "hist_gradient_boosting"],
            "horizons": ["20"],
            "benchmarks": ["QQQ", "SOXX"],
        }
    ).total_research_looks()
    assert after == before * 2


def test_duplicate_variants_are_refused():
    with pytest.raises(ExperimentContractError, match="duplicates"):
        _spec(research_look_dimensions={"models": ["a", "a"]})


def test_duplicate_candidate_models_are_refused():
    with pytest.raises(ExperimentContractError, match="duplicates"):
        _spec(candidate_models=("ridge", "ridge"))


def test_a_model_cannot_be_both_candidate_and_baseline():
    with pytest.raises(ExperimentContractError, match="both candidate and frozen baseline"):
        _spec(candidate_models=("ewma", "ridge"), frozen_baselines=("ewma",))


# --- mode / confirmation consistency ---------------------------------------


def test_confirmation_without_a_parent_hash_is_refused():
    with pytest.raises(ExperimentContractError, match="parent discovery"):
        _spec(mode="confirmation")


def test_discovery_carrying_a_confirmation_parent_is_refused():
    with pytest.raises(ExperimentContractError, match="must not carry a confirmation parent"):
        _spec(
            mode="discovery",
            confirmation=ConfirmationSpec(
                parent_experiment_id="p", parent_spec_hash=_HASH_A, parent_report_hash=_HASH_B
            ),
        )


def test_confirmation_must_have_a_different_id_than_its_parent():
    with pytest.raises(ExperimentContractError, match="different experiment_id"):
        _confirmation_spec(experiment_id="volatility-discovery-v1")


def test_a_valid_confirmation_spec_is_accepted():
    spec = _confirmation_spec()
    assert spec.mode == "confirmation"
    assert spec.confirmation.parent_spec_hash == _HASH_A


def test_an_unknown_mode_is_refused():
    with pytest.raises(ExperimentContractError, match="mode must be one of"):
        _spec(mode="production")


def test_confirmation_parent_hashes_must_be_real_digests():
    with pytest.raises(ExperimentContractError, match="sha256"):
        ConfirmationSpec(
            parent_experiment_id="p", parent_spec_hash="not-a-hash", parent_report_hash=_HASH_B
        )


# --- value validation -------------------------------------------------------


def test_naive_timestamps_are_refused():
    with pytest.raises(ExperimentContractError, match="timezone-aware"):
        _spec(created_at="2026-07-31T00:00:00")


def test_non_finite_nested_values_are_refused():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ExperimentContractError, match="not finite"):
            _spec(cost_tax_liquidity_assumptions={"transaction_cost_bps": bad})


def test_unknown_schema_version_is_refused():
    with pytest.raises(ExperimentContractError, match="unknown schema_version"):
        _spec(schema_version="99.0")


def test_non_positive_horizon_is_refused():
    with pytest.raises(ExperimentContractError, match="horizon_sessions"):
        _spec(horizon_sessions=0)


def test_empty_research_look_dimensions_are_refused():
    with pytest.raises(ExperimentContractError, match="non-empty mapping"):
        _spec(research_look_dimensions={})


# --- forbidden execution-shaped fields --------------------------------------


@pytest.mark.parametrize(
    "assumptions",
    [
        {"side": "buy"},
        {"target_weight": 0.2},
        {"approved": True},
        {"authorization": "granted"},
        {"nested": {"quantity": 10}},
        {"PRODUCTION": True},  # case-insensitive
    ],
)
def test_execution_shaped_fields_cannot_enter_a_spec(assumptions):
    """Plan 6.2 forbids these names. Checked on the SERIALIZED payload, so a
    key smuggled inside a nested mapping is caught too -- a declared-field
    check alone would miss it."""
    with pytest.raises(ExperimentContractError, match="execution-shaped"):
        _spec(cost_tax_liquidity_assumptions=assumptions)


def test_forbidden_fields_never_appear_in_serialized_output():
    payload = _spec().to_dict()
    forbidden = {
        "production", "approved", "authority", "authorization", "side",
        "quantity", "target_weight", "order_type", "execute",
    }
    assert not (forbidden & set(payload))


# --- research gate ----------------------------------------------------------


def test_gate_requires_more_than_one_fold():
    """Doc 14.1 requires beating the baseline in MORE THAN ONE untouched
    fold; a gate permitting 1 would silently contradict it."""
    with pytest.raises(ExperimentContractError, match="minimum_folds_won"):
        _gate(minimum_folds_won=1)


def test_gate_rejects_out_of_range_alpha_and_coverage():
    with pytest.raises(ExperimentContractError, match="maximum_alpha"):
        _gate(maximum_alpha=1.5)
    with pytest.raises(ExperimentContractError, match="minimum_coverage_fraction"):
        _gate(minimum_coverage_fraction=0.0)


def test_gate_rejects_duplicate_or_invalid_block_lengths():
    with pytest.raises(ExperimentContractError, match="duplicates"):
        _gate(block_lengths=(20, 20))
    with pytest.raises(ExperimentContractError, match="positive integers"):
        _gate(block_lengths=(0,))


def test_gate_requires_failure_slices():
    with pytest.raises(ExperimentContractError, match="failure_slices"):
        _gate(failure_slices=())


# --- identity and run record -------------------------------------------------


def test_identity_derives_from_the_spec():
    spec = _spec()
    identity = spec.identity()
    assert identity.experiment_id == spec.experiment_id
    assert identity.spec_hash == spec.spec_hash
    assert identity.mode == "discovery"


def _run_record(**overrides) -> ExperimentRunRecord:
    kwargs = dict(
        identity=_spec().identity(),
        dataset_id="ds-1",
        dataset_hash=_HASH_A,
        code_commit="0" * 40,
        started_at="2026-07-31T00:00:00+00:00",
        completed_at="2026-07-31T00:05:00+00:00",
        report_hash=_HASH_B,
        artifact_hashes={"model": _HASH_C},
        total_research_looks=2,
        verdict="exploratory",
        promotion_blockers=("not_point_in_time_data",),
    )
    kwargs.update(overrides)
    return ExperimentRunRecord(**kwargs)


def test_run_record_round_trips_and_is_never_authoritative():
    record = _run_record()
    payload = record.to_dict()
    assert payload["production_authoritative"] is False
    assert len(record.run_hash) == 64
    import json

    json.dumps(payload)


def test_run_record_rejects_a_promoted_verdict():
    """The verdict vocabulary is reused from EvaluationReport, which
    deliberately contains no 'promoted' value -- authority requires the
    separate human decision of ML-LR-9."""
    with pytest.raises(ExperimentContractError, match="verdict must be one of"):
        _run_record(verdict="promoted")


def test_run_record_rejects_completion_before_start():
    with pytest.raises(ExperimentContractError, match="must not precede"):
        _run_record(completed_at="2026-07-30T00:00:00+00:00")


def test_run_record_rejects_a_malformed_artifact_hash():
    with pytest.raises(ExperimentContractError, match="artifact_hashes"):
        _run_record(artifact_hashes={"model": "nope"})


def test_run_record_allows_no_promotion_blockers():
    assert _run_record(promotion_blockers=()).promotion_blockers == ()


def test_run_record_artifact_hashes_are_frozen():
    hashes = {"model": _HASH_C}
    record = _run_record(artifact_hashes=hashes)
    hashes["model"] = _HASH_A
    assert record.artifact_hashes["model"] == _HASH_C


# --- no side effects (plan 6.3) ---------------------------------------------


def test_constructing_contracts_creates_no_sqlite_or_execution_state(tmp_path, monkeypatch):
    """Pure contract construction must touch nothing: no database file, no
    proposal, no artifact."""
    monkeypatch.chdir(tmp_path)
    _spec()
    _confirmation_spec()
    _run_record()
    assert list(tmp_path.iterdir()) == []


# --- definition of done (plan 6.4) ------------------------------------------


def test_a_volatility_experiment_is_fully_describable():
    spec = _spec()
    assert spec.task == "volatility_forecast"
    assert "ewma" in spec.frozen_baselines
    assert spec.total_research_looks() == 2


def test_a_ranker_experiment_is_fully_describable():
    """Plan 6.4's definition of done: one volatility AND one ranker
    experiment must be completely describable by this spec."""
    spec = _spec(
        experiment_id="tech-ranker-discovery-v1",
        task="cross_sectional_excess_return_ranking",
        primary_outcome="date-level Spearman IC vs residual momentum",
        candidate_models=("elastic_net", "hist_gradient_boosting"),
        frozen_baselines=("no_skill", "residual_momentum"),
        label_version="forward_excess_return_20d_next_open_v1",
        research_look_dimensions={
            "models": ["elastic_net", "hist_gradient_boosting"],
            "benchmarks": ["QQQ", "SOXX"],
            "horizons": ["20"],
            "feature_families": ["price_only"],
        },
        research_gate=_gate(failure_slices=("year", "ticker", "volatility_regime")),
    )
    assert spec.total_research_looks() == 4
    assert spec.spec_hash != _spec().spec_hash
