from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from assistant.schemas import EvidenceStatus
from ml.availability import (
    FeatureAvailabilityRecord,
    UniverseMembershipRecord,
    evaluate_point_in_time_coverage,
    hash_feature_value,
)
from ml.datasets import assemble_dataset_frames, build_dataset_manifest, save_dataset
from ml.experiment_contracts import (
    ExperimentRunRecord,
    ExperimentSpec,
    ResearchGateSpec,
)
from ml.hashing import canonical_json, hash_bytes
from ml.labels import LabelRow
from ml.research_orchestration import (
    ResearchOrchestrationError,
    SpecReviewAttestation,
    load_content_addressed_dataset,
    load_reviewed_spec,
    materialize_content_addressed_dataset,
    prepare_confirmation_request,
    run_reviewed_experiment,
)


def _spec(**overrides) -> ExperimentSpec:
    payload = dict(
        experiment_id="volatility-discovery-reviewed-v1",
        task="volatility_forecast",
        mode="discovery",
        created_at="2026-08-01T16:00:00+00:00",
        primary_outcome="QLIKE vs frozen EWMA baseline",
        candidate_models=("ridge_log_vol",),
        frozen_baselines=("trailing_realized", "ewma"),
        feature_set_version="authoritative-volatility-v1",
        label_version="forward-realized-vol-5d-v1",
        benchmark="QQQ",
        horizon_sessions=5,
        universe_definition="reviewed-historical-universe-v1",
        research_look_dimensions={"models": ["ridge_log_vol"], "horizons": ["5"]},
        split_configuration={"n_splits": 2, "embargo_sessions": 5},
        cost_tax_liquidity_assumptions={"transaction_cost_bps": 5.0},
        research_gate=ResearchGateSpec(
            minimum_folds_won=2,
            minimum_coverage_fraction=0.8,
            maximum_alpha=0.05,
            block_lengths=(5,),
            required_calibration_bins=5,
            failure_slices=("year", "volatility_regime"),
            mandate_ceiling_daily_pct=2.0,
            maximum_brier=0.25,
        ),
        random_seed=0,
        ordered_feature_names=("feature_a", "feature_b"),
        target_column="label_value",
        baseline_columns={
            "trailing_realized": "trailing_vol",
            "ewma": "ewma_vol",
        },
    )
    payload.update(overrides)
    return ExperimentSpec(**payload)


def _review(spec: ExperimentSpec, **overrides) -> SpecReviewAttestation:
    payload = dict(
        spec_hash=spec.spec_hash,
        reviewer="owner@example.com",
        reviewed_at="2026-08-01T17:00:00+00:00",
        decision="approved",
        review_scope="research_behavior_and_gates",
        notes="Fixture attestation for orchestration behavior tests.",
    )
    payload.update(overrides)
    return SpecReviewAttestation(**payload)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload), encoding="utf-8")


def _dataset(directory: Path, dataset_id: str, *, offset: float = 0.0, pit: bool = True):
    rng = np.random.default_rng(7)
    sessions = [str(value.date()) for value in pd.bdate_range("2024-01-02", periods=180)]
    feature_a = np.round(np.abs(rng.normal(1.5 + offset, 0.25, len(sessions))), 6)
    feature_b = np.round(feature_a * 0.7 + rng.normal(0, 0.03, len(sessions)), 6)
    target = np.round(
        np.clip(feature_a * 0.9 + rng.normal(0, 0.02, len(sessions)), 0.01, None),
        6,
    )
    features = pd.DataFrame({
        "ticker": ["AAA"] * len(sessions),
        "as_of_session": sessions,
        "feature_a": feature_a,
        "feature_b": feature_b,
        "trailing_vol": np.round(feature_a * 1.3, 6),
        "ewma_vol": np.round(feature_a * 1.2, 6),
    })
    labels = tuple(
        LabelRow(
            ticker="AAA",
            as_of_session=session,
            label_version="forward-realized-vol-5d-v1",
            entry_session=session,
            entry_price=100.0,
            exit_session=sessions[min(index + 5, len(sessions) - 1)],
            exit_price=101.0,
            value=float(target[index]),
            components={"daily_volatility_pct": float(target[index])},
        )
        for index, session in enumerate(sessions)
    )
    features_df, labels_df = assemble_dataset_frames({"AAA": features}, {"AAA": labels})
    availability = []
    cutoffs = {}
    values = {}
    for row in features_df.itertuples(index=False):
        cutoff = f"{row.as_of_session}T21:00:00+00:00"
        observed = f"{row.as_of_session}T20:00:00+00:00"
        cutoffs[row.as_of_session] = cutoff
        for name in ("feature_a", "feature_b", "trailing_vol", "ewma_vol"):
            value = float(getattr(row, name))
            values[(row.as_of_session, row.ticker, name)] = value
            availability.append(FeatureAvailabilityRecord(
                as_of_session=row.as_of_session,
                ticker=row.ticker,
                feature_name=name,
                event_at=observed,
                available_at=observed,
                observed_at=observed,
                source_id="fixture-authoritative",
                source_version="1",
                revision_id=f"{row.as_of_session}:{name}",
                raw_value_hash=hash_feature_value(value),
            ))
    universe = (UniverseMembershipRecord(
        universe_id="reviewed-historical-universe-v1",
        ticker="AAA",
        effective_from=sessions[0],
        effective_to=sessions[-1],
        announced_at="2023-12-01T00:00:00+00:00",
        available_at="2023-12-01T00:00:00+00:00",
        source_id="fixture-universe",
        source_version="1",
    ),)
    coverage = evaluate_point_in_time_coverage(
        feature_keys=[(session, "AAA") for session in sessions],
        feature_columns=["feature_a", "feature_b", "trailing_vol", "ewma_vol"],
        availability=availability,
        universe=universe,
        universe_id="reviewed-historical-universe-v1",
        decision_cutoffs=cutoffs,
        feature_values=values,
    ) if pit else None
    availability_df = pd.DataFrame([item.to_dict() for item in availability]) if pit else None
    universe_df = pd.DataFrame([item.to_dict() for item in universe]) if pit else None
    manifest = build_dataset_manifest(
        features_df=features_df,
        labels_df=labels_df,
        dataset_id=dataset_id,
        created_at="2026-08-01T16:00:00+00:00",
        task="volatility_forecast",
        feature_set_version="authoritative-volatility-v1",
        label_version="forward-realized-vol-5d-v1",
        source_descriptions=("authoritative fixture",),
        point_in_time_data=False,
        universe_definition="reviewed-historical-universe-v1",
        entry_timing="next_open",
        target_horizon_sessions=5,
        embargo_sessions=5,
        dropped_label_row_count=0,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        git_commit="0" * 40,
        availability_df=availability_df,
        universe_df=universe_df,
        coverage=coverage,
        benchmark="QQQ",
    )
    save_dataset(
        features_df, labels_df, manifest,
        directory=directory,
        availability_df=availability_df,
        universe_df=universe_df,
    )
    return manifest


def test_only_authoritative_dataset_enters_hash_named_store(tmp_path):
    source = tmp_path / "source"
    manifest = _dataset(source, "discovery-ds")
    address = materialize_content_addressed_dataset(source, "discovery-ds", tmp_path / "store")
    destination = tmp_path / "store" / manifest.dataset_hash
    loaded, loaded_address = load_content_addressed_dataset(destination, "discovery-ds")
    assert address.dataset_hash == loaded.dataset_hash == manifest.dataset_hash
    assert loaded_address.directory == manifest.dataset_hash
    assert materialize_content_addressed_dataset(
        source, "discovery-ds", tmp_path / "store"
    ) == address


def test_exploratory_dataset_is_refused_by_authoritative_store(tmp_path):
    source = tmp_path / "source"
    _dataset(source, "exploratory-ds", pit=False)
    with pytest.raises(ResearchOrchestrationError, match="point_in_time_data=true"):
        materialize_content_addressed_dataset(source, "exploratory-ds", tmp_path / "store")


def test_spec_review_is_exact_and_cannot_approve_a_mutation(tmp_path):
    spec = _spec()
    review = _review(spec)
    spec_path = tmp_path / "spec.json"
    review_path = tmp_path / "review.json"
    _write_json(spec_path, spec.to_dict())
    _write_json(review_path, review.to_dict())
    assert load_reviewed_spec(spec_path, review_path)[0].spec_hash == spec.spec_hash
    _write_json(spec_path, _spec(random_seed=9).to_dict())
    with pytest.raises(ResearchOrchestrationError, match="review hash"):
        load_reviewed_spec(spec_path, review_path)


def test_reviewed_discovery_runs_only_from_content_addressed_pit_data(tmp_path):
    source = tmp_path / "source"
    manifest = _dataset(source, "discovery-ds")
    address = materialize_content_addressed_dataset(source, "discovery-ds", tmp_path / "store")
    spec = _spec()
    review = _review(spec)
    spec_path = tmp_path / "spec.json"
    review_path = tmp_path / "review.json"
    _write_json(spec_path, spec.to_dict())
    _write_json(review_path, review.to_dict())
    record, evidence = run_reviewed_experiment(
        spec_path=spec_path,
        review_path=review_path,
        dataset_directory=tmp_path / "store" / address.dataset_hash,
        dataset_id="discovery-ds",
        output_directory=tmp_path / "out",
        code_commit="0" * 40,
    )
    assert record.dataset_hash == manifest.dataset_hash
    assert evidence["review_hash"] == review.review_hash
    assert evidence["production_authoritative"] is False


def _fake_successful_discovery(output: Path, spec: ExperimentSpec, dataset_hash: str):
    report = {"verdict": "confirmation_run_requested", "production_authoritative": False}
    report_bytes = canonical_json(report).encode("utf-8")
    run = ExperimentRunRecord(
        identity=spec.identity(),
        dataset_id="discovery-ds",
        dataset_hash=dataset_hash,
        code_commit="0" * 40,
        started_at=spec.created_at,
        completed_at=spec.created_at,
        report_hash=hash_bytes(report_bytes),
        artifact_hashes={"ridge_log_vol.artifact": "f" * 64},
        total_research_looks=spec.total_research_looks(),
        verdict="confirmation_run_requested",
        promotion_blockers=(),
    )
    _write_json(output / f"{spec.experiment_id}.spec.json", spec.to_dict())
    _write_json(output / f"{spec.experiment_id}.report.json", report)
    _write_json(output / f"{spec.experiment_id}.run.json", run.to_dict())
    return run


def test_confirmation_request_binds_distinct_untouched_dataset_and_needs_review(tmp_path):
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    first = _dataset(first_source, "discovery-ds", offset=0.0)
    second = _dataset(second_source, "confirmation-ds", offset=0.2)
    store = tmp_path / "store"
    first_address = materialize_content_addressed_dataset(first_source, "discovery-ds", store)
    second_address = materialize_content_addressed_dataset(second_source, "confirmation-ds", store)
    spec = _spec()
    _fake_successful_discovery(tmp_path / "out", spec, first.dataset_hash)
    confirmation, request = prepare_confirmation_request(
        discovery_output_directory=tmp_path / "out",
        discovery_experiment_id=spec.experiment_id,
        confirmation_dataset_directory=store / second_address.dataset_hash,
        confirmation_dataset_id="confirmation-ds",
        confirmation_experiment_id="volatility-confirmation-reviewed-v1",
        created_at="2026-08-01T18:00:00+00:00",
        spec_output_path=tmp_path / "confirmation.json",
        request_output_path=tmp_path / "confirmation.request.json",
    )
    assert confirmation.mode == "confirmation"
    assert request.discovery_dataset_hash == first_address.dataset_hash
    assert request.confirmation_dataset_hash == second_address.dataset_hash
    assert request.review_status == "review_required"
    assert confirmation.confirmation.parent_spec_hash == spec.spec_hash


def test_same_dataset_cannot_be_called_untouched_confirmation(tmp_path):
    source = tmp_path / "source"
    manifest = _dataset(source, "discovery-ds")
    address = materialize_content_addressed_dataset(source, "discovery-ds", tmp_path / "store")
    spec = _spec()
    _fake_successful_discovery(tmp_path / "out", spec, manifest.dataset_hash)
    with pytest.raises(ResearchOrchestrationError, match="not untouched"):
        prepare_confirmation_request(
            discovery_output_directory=tmp_path / "out",
            discovery_experiment_id=spec.experiment_id,
            confirmation_dataset_directory=tmp_path / "store" / address.dataset_hash,
            confirmation_dataset_id="discovery-ds",
            confirmation_experiment_id="volatility-confirmation-reviewed-v1",
            created_at="2026-08-01T18:00:00+00:00",
            spec_output_path=tmp_path / "confirmation.json",
            request_output_path=tmp_path / "confirmation.request.json",
        )


def test_campaign_modules_have_no_execution_or_registry_imports():
    for filename in ("ml/research_orchestration.py", "scripts/run_ml_research_campaign.py"):
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(
            name.startswith(("execution", "assistant.storage", "assistant.execution_service"))
            for name in imported
        )


def test_repository_discovery_spec_is_valid_and_explicitly_unapproved():
    root = Path(__file__).resolve().parent.parent
    spec_payload = json.loads(
        (root / "research/ml_specs/volatility-discovery-v1.json").read_text(
            encoding="utf-8"
        )
    )
    request = json.loads(
        (root / "research/ml_specs/volatility-discovery-v1.review-request.json").read_text(
            encoding="utf-8"
        )
    )
    spec = ExperimentSpec.from_dict(spec_payload)
    assert request["spec_hash"] == spec.spec_hash
    assert request["review_status"] == "review_required"
    assert request["reviewer"] is None and request["reviewed_at"] is None
