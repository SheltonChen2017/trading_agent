"""End-to-end tests for the completed ML-LR-6 shadow runtime."""
from __future__ import annotations

import ast
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge

from assistant.schemas import EvidenceStatus
from assistant.storage import AssistantStore
from ml.artifacts import save_model_artifact, save_model_manifest
from ml.contracts import ModelManifest
from ml.hashing import hash_bytes
from ml.presentation import UNAVAILABLE, build_observation
from ml.shadow import (
    build_lineage,
    epoch_key,
    resolve_decision_cutoff,
    resolve_target_availability,
    trading_sessions,
)
from ml.shadow_runtime import (
    ShadowRuntimeError,
    build_volatility_prediction,
    load_price_frames,
    load_shadow_config,
    verify_runtime_artifacts,
)
from scripts import run_ml_evidence_supervisor, run_ml_promotion_dossier, run_ml_shadow


def test_shadow_code_commit_argument_is_a_runtime_assertion(monkeypatch):
    seen = {}

    def _runtime_commit(**kwargs):
        seen.update(kwargs)
        return "d" * 40

    monkeypatch.setattr(run_ml_shadow, "current_commit", _runtime_commit)

    assert run_ml_shadow._current_commit("d" * 40) == "d" * 40
    assert seen == {"require_clean": True, "expected_commit": "d" * 40}


def _bar_payload(start: str = "2024-01-02", end: str = "2026-04-10"):
    sessions = trading_sessions(date.fromisoformat(start), date.fromisoformat(end))
    bars = {}
    for offset, ticker in enumerate(("AAA", "BBB", "SPY", "QQQ", "SOXX")):
        rows = []
        for index, session in enumerate(sessions):
            close = 100.0 * math.exp(
                0.00035 * index + 0.012 * math.sin(index / (7.0 + offset))
            )
            open_ = close * (1.0 + 0.001 * math.cos(index / 5.0))
            rows.append(
                {
                    "session": session.isoformat(),
                    "open": round(open_, 8),
                    "high": round(max(open_, close) * 1.005, 8),
                    "low": round(min(open_, close) * 0.995, 8),
                    "close": round(close, 8),
                    "volume": 1_000_000 + offset * 10_000 + index,
                }
            )
        bars[ticker] = rows
    return {"bars": bars}


def _runtime_fixture(tmp_path: Path, *, feature_names=None):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    feature_names = tuple(
        feature_names or ("realized_vol_20d_pct", "realized_vol_60d_pct")
    )
    estimator = Ridge(alpha=1.0).fit(
        np.asarray([[0.0, 0.0], [1.0, -1.0], [-1.0, 1.0], [2.0, 0.5]]),
        np.log(np.asarray([0.9, 1.1, 0.8, 1.3])),
    )
    bundle = {
        "estimator": estimator,
        "standardizer": {
            "feature_names": feature_names,
            "means": {name: 0.0 for name in feature_names},
            "scales": {name: 1.0 for name in feature_names},
            "training_row_count": 100,
            "training_start": "2024-01-02",
            "training_end": "2025-12-31",
        },
        "ordered_feature_names": feature_names,
        "feature_reference": {
            name: {
                "independent_date_count": 100,
                "bin_edges": [-1.0, 0.0, 1.0],
                "bin_counts": [10, 40, 40, 10],
                "minimum": -2.0,
                "maximum": 2.0,
                "mean": 0.0,
                "standard_deviation": 1.0,
            }
            for name in feature_names
        },
        "prospective_profile": {
            "schema_version": "1",
            "interval": {
                "status": "available",
                "method": "out_of_fold_empirical_log_residual",
                "target_coverage": 0.9,
                "log_residual_quantiles": [-0.25, 0.25],
                "residual_count": 40,
            },
            "threshold": {
                "status": "available",
                "method": "out_of_fold_empirical_log_residual",
                "ceiling_daily_pct": 2.0,
                "calibration_status": "experimental",
                "brier_score": 0.2,
                "event_count": 40,
                "empirical_log_residuals": [-0.25] * 20 + [0.25] * 20,
            },
        },
    }
    artifact_hash = save_model_artifact(
        bundle, directory=artifact_dir, filename="vol.joblib"
    )
    report_bytes = b'{"aggregate_metrics":{},"production_authoritative":false}'
    (artifact_dir / "vol.report.json").write_bytes(report_bytes)
    manifest = ModelManifest(
        model_id="fixture-vol",
        model_version="0.1.0",
        task="volatility_forecast",
        created_at="2026-01-01T00:00:00+00:00",
        dataset_id="fixture-dataset",
        dataset_hash="a" * 64,
        feature_set_version="point-in-time-market-v1",
        ordered_feature_names=feature_names,
        label_version="forward_realized_vol_20d_v1",
        algorithm="Ridge",
        hyperparameters={"alpha": 1.0, "training_only_standardizer": True},
        random_seed=0,
        training_window={"start": "2024-01-02", "end": "2025-12-31"},
        validation_windows=({"start": "2026-01-02", "end": "2026-01-30"},),
        dependency_versions={"scikit-learn": "1.9.0"},
        artifact_hash=artifact_hash,
        evaluation_report_hash=hash_bytes(report_bytes),
        evidence_status=EvidenceStatus.EXPLORATORY,
    )
    manifest_hash = save_model_manifest(
        manifest, directory=artifact_dir, filename="vol.manifest.json"
    )
    provider_path = tmp_path / "provider.json"
    provider_path.write_text(json.dumps(_bar_payload()), encoding="utf-8")
    config_payload = {
        "schema_version": "1",
        "task": "volatility_forecast",
        "schedule_key": "fixture-volatility-daily",
        "schedule_version": "daily-close-v1",
        "model_id": manifest.model_id,
        "model_version": manifest.model_version,
        "manifest_filename": "vol.manifest.json",
        "manifest_hash": manifest_hash,
        "artifact_filename": "vol.joblib",
        "evaluation_report_filename": "vol.report.json",
        "subjects": ["AAA", "BBB"],
        "horizon_sessions": 20,
        "data_provider": {
            "kind": "fixture_json",
            "provider_id": "fixture:immutable-bars-v1",
            "path": provider_path.name,
        },
        "market_benchmark": "QQQ",
        "trailing_baseline_window": 20,
        "ewma_halflife": 20.0,
        "earnings_dates_by_subject": {},
    }
    config_path = tmp_path / "shadow-config.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    return config_path, artifact_dir, provider_path, manifest


def _registered_store(tmp_path: Path):
    config_path, artifact_dir, provider_path, manifest = _runtime_fixture(tmp_path)
    config, _ = load_shadow_config(config_path)
    store = AssistantStore(tmp_path / "assistant.db")
    summary = run_ml_shadow.command_register(store, config, artifact_dir)
    assert summary["ok"]
    return store, config, config_path, artifact_dir, provider_path, manifest


def test_evidence_supervisor_adapter_records_fail_closed_report_and_alerts(tmp_path):
    store, config, config_path, artifact_dir, _provider_path, _manifest = (
        _registered_store(tmp_path)
    )
    output = tmp_path / "supervisor.json"
    args = run_ml_evidence_supervisor.build_parser().parse_args([
        "--database",
        str(store.path),
        "--config",
        str(config_path),
        "--artifact-dir",
        str(artifact_dir),
        "--output",
        str(output),
        "--as-of",
        "2026-04-10T23:00:00+00:00",
    ])

    summary, exit_code = run_ml_evidence_supervisor.command_check(args)

    assert exit_code == 1
    assert summary["ok"] is False
    assert summary["production_authoritative"] is False
    assert output.exists()
    assert any(
        alert["category"] == "ml_evidence_operations"
        for alert in store.list_operational_alerts()
    )
    heartbeat = store.get_system_state(
        f"ml_evidence_supervisor_heartbeat:{config.schedule_key}"
    )
    assert heartbeat["ok"] is False


def test_shadow_config_is_strict_and_hashes_defaults(tmp_path):
    config_path, _artifact_dir, _provider_path, _manifest = _runtime_fixture(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["unknown_behavior"] = True
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    try:
        load_shadow_config(config_path)
    except ShadowRuntimeError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown runtime behavior must be rejected")


def test_documented_yfinance_config_example_matches_the_runtime_contract():
    path = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "operations"
        / "ml_shadow_volatility_config.example.json"
    )
    config, payload = load_shadow_config(path)
    assert config.task == "volatility_forecast"
    assert config.data_provider["kind"] == "yfinance_adjusted"
    assert "point_in_time=false" in config.provider_id
    assert payload["horizon_sessions"] == 20


def test_yfinance_provider_cannot_be_mislabeled_as_point_in_time(tmp_path):
    config_path, _artifact_dir, _provider_path, _manifest = _runtime_fixture(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["data_provider"] = {
        "kind": "yfinance_adjusted",
        "provider_id": "yfinance:authoritative",
        "lookback_sessions": 320,
    }
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    try:
        load_shadow_config(config_path)
    except ShadowRuntimeError as exc:
        assert "point_in_time=false" in str(exc)
    else:
        raise AssertionError("yfinance must remain an explicit promotion blocker")


def test_predict_resume_mature_monitor_is_idempotent_and_non_authoritative(tmp_path):
    store, config, config_path, artifact_dir, _provider_path, manifest = _registered_store(
        tmp_path
    )
    scheduled_for = resolve_decision_cutoff("2026-02-25")
    started_at = "2026-02-25T21:05:00+00:00"
    code_commit = "d" * 40

    # Simulate a process crash after the first subject was committed but
    # before the run closed. The real rerun must reuse that immutable row and
    # fill only the missing subject.
    lineage = build_lineage(
        model_artifact_hash=manifest.artifact_hash,
        evaluation_report_hash=manifest.evaluation_report_hash,
        feature_set_version=manifest.feature_set_version,
        label_version=manifest.label_version,
        data_provider_id=config.provider_id,
        configuration_hash=config.configuration_hash,
        code_commit=code_commit,
        schedule_version=config.schedule_version,
    )
    evidence_epoch = epoch_key(config.model_key, config.task, lineage)
    store.open_ml_evidence_epoch(
        evidence_epoch=evidence_epoch,
        model_key=config.model_key,
        task=config.task,
        lineage=lineage,
        created_by="test-crashed-run",
        started_at=scheduled_for,
    )
    run = store.claim_ml_shadow_run(
        schedule_key=config.schedule_key,
        scheduled_for=scheduled_for,
        evidence_epoch=evidence_epoch,
        code_commit=code_commit,
        configuration_hash=config.configuration_hash,
        started_at=started_at,
    )
    verified_manifest, bundle, _report = verify_runtime_artifacts(config, artifact_dir)
    frames = load_price_frames(
        config,
        config_directory=config_path.parent,
        requested_tickers=(*config.subjects, "SPY", "QQQ", "SOXX"),
    )
    first_payload = build_volatility_prediction(
        config,
        verified_manifest,
        bundle,
        frames,
        subject="AAA",
        as_of_session="2026-02-25",
        generated_at=started_at,
        decision_cutoff=scheduled_for,
        target_available_at=resolve_target_availability("2026-02-25", 20),
        evidence_epoch=evidence_epoch,
        shadow_run_id=run["run_id"],
    )
    first = store.record_ml_prediction(first_payload)

    completed = run_ml_shadow.command_predict(
        store,
        config,
        config_path,
        artifact_dir,
        scheduled_for=scheduled_for,
        code_commit=code_commit,
        # A machine can restart the next day. The immutable run keeps its
        # original generation time; current wall-clock time must not block
        # recovery or rewrite the first prediction.
        started_at="2026-02-26T14:00:00+00:00",
    )
    assert completed["ok"]
    assert completed["available_count"] == 2
    predictions = store.list_ml_predictions(shadow_run_id=run["run_id"])
    assert len(predictions) == 2
    prospective = predictions[0]["prediction"]["prospective_contract"]
    stored_uncertainty = predictions[0]["prediction"]["uncertainty"]
    assert stored_uncertainty["schema_version"] == "1.0"
    assert stored_uncertainty["prediction_interval_daily_pct"]
    assert stored_uncertainty["threshold_probability_label"] == "experimental_probability"
    observation = build_observation(predictions[0], evidence_epoch=evidence_epoch)
    assert observation.prediction_interval != UNAVAILABLE
    assert prospective["point_estimate"]["unit"] == "daily_return_standard_deviation_pct"
    assert prospective["prediction_interval"]["lower"] <= prospective["point_estimate"]["value"]
    assert prospective["prediction_interval"]["upper"] >= prospective["point_estimate"]["value"]
    assert prospective["threshold_probability"]["label"] == "experimental_probability"
    assert prospective["calibration"]["status"] == "experimental"
    assert prospective["reference_distribution"]["identity_hash"]
    assert prospective["regime_category"] in {
        "above_training_mean", "at_or_below_training_mean"
    }
    assert prospective["event_category"] == "ordinary_session"
    assert prospective["lineage"]["evidence_epoch"] == evidence_epoch
    assert prospective["lineage"]["dataset_hash"] == manifest.dataset_hash
    assert prospective["production_authoritative"] is False
    assert next(p for p in predictions if p["subject_key"] == "AAA")["prediction_hash"] == first[
        "prediction_hash"
    ]

    retried = run_ml_shadow.command_predict(
        store,
        config,
        config_path,
        artifact_dir,
        scheduled_for=scheduled_for,
        code_commit=code_commit,
        started_at="2026-02-26T14:00:00+00:00",
    )
    assert retried["idempotent_retry"] is True
    assert len(store.list_ml_predictions(shadow_run_id=run["run_id"])) == 2

    target = resolve_target_availability("2026-02-25", 20)
    after_target = (datetime.fromisoformat(target) + timedelta(minutes=1)).isoformat()
    matured = run_ml_shadow.command_mature(
        store,
        config,
        config_path,
        artifact_dir,
        as_of=after_target,
        evidence_epoch=evidence_epoch,
    )
    assert matured["ok"]
    assert matured["matured_count"] == 2
    assert len(store.list_ml_prediction_outcomes()) == 2
    rerun_maturity = run_ml_shadow.command_mature(
        store,
        config,
        config_path,
        artifact_dir,
        as_of=(datetime.fromisoformat(target) + timedelta(days=1)).isoformat(),
        evidence_epoch=evidence_epoch,
    )
    assert rerun_maturity["matured_count"] == 0
    assert rerun_maturity["already_matured_count"] == 2

    output = tmp_path / "monitoring" / "current.json"
    report = run_ml_shadow.command_monitor(
        store, config, evidence_epoch=evidence_epoch, output=output
    )
    assert report["prediction_count"] == 2
    assert report["outcome_count"] == 2
    assert report["production_authoritative"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["monitoring"][
        "production_authoritative"
    ] is False

    assert store.list_proposals() == []
    with store._connect() as connection:
        for table in (
            "trade_proposals",
            "broker_orders",
            "broker_order_events",
            "execution_reservations",
            "allocation_batches",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_promotion_dossier_command_has_no_registry_or_execution_side_effect(tmp_path):
    store, config, _config_path, artifact_dir, _provider_path, manifest = _registered_store(
        tmp_path
    )
    lineage = build_lineage(
        model_artifact_hash=manifest.artifact_hash,
        evaluation_report_hash=manifest.evaluation_report_hash,
        feature_set_version=manifest.feature_set_version,
        label_version=manifest.label_version,
        data_provider_id=config.provider_id,
        configuration_hash=config.configuration_hash,
        code_commit="d" * 40,
        schedule_version=config.schedule_version,
    )
    evidence_epoch = epoch_key(config.model_key, config.task, lineage)
    store.open_ml_evidence_epoch(
        evidence_epoch=evidence_epoch,
        model_key=config.model_key,
        task=config.task,
        lineage=lineage,
        created_by="dossier-side-effect-test",
        started_at="2026-02-25T20:00:00+00:00",
    )
    with store._connect() as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "ml_model_registrations",
                "ml_evidence_epochs",
                "trade_proposals",
                "broker_orders",
                "execution_reservations",
                "allocation_batches",
            )
        }
    output = tmp_path / "dossier.json"
    args = run_ml_promotion_dossier.build_parser().parse_args(
        [
            "--database", str(store.path),
            "--config", str(_config_path),
            "--artifact-dir", str(artifact_dir),
            "--evidence-epoch", evidence_epoch,
            "--known-limitation", "fixture evidence only",
            "--output", str(output),
        ]
    )
    summary = run_ml_promotion_dossier.command_build(args)
    assert summary["ok"]
    assert summary["production_authoritative"] is False
    assert "separate_owner_promotion_review_required" in summary["promotion_blockers"]
    assert json.loads(output.read_text(encoding="utf-8"))[
        "production_authoritative"
    ] is False
    with store._connect() as connection:
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert after == before


def test_future_fixture_rows_cannot_change_an_as_of_prediction(tmp_path):
    store, config, config_path, artifact_dir, provider_path, manifest = _registered_store(
        tmp_path
    )
    verified_manifest, bundle, _report = verify_runtime_artifacts(config, artifact_dir)
    frames = load_price_frames(
        config,
        config_directory=config_path.parent,
        requested_tickers=(*config.subjects, "SPY", "QQQ", "SOXX"),
    )
    kwargs = dict(
        subject="AAA",
        as_of_session="2026-02-25",
        generated_at="2026-02-25T21:05:00+00:00",
        decision_cutoff=resolve_decision_cutoff("2026-02-25"),
        target_available_at=resolve_target_availability("2026-02-25", 20),
        evidence_epoch="epoch",
        shadow_run_id="run",
    )
    first = build_volatility_prediction(config, verified_manifest, bundle, frames, **kwargs)
    changed = {ticker: frame.copy() for ticker, frame in frames.items()}
    future = changed["AAA"].index > np.datetime64("2026-02-25")
    changed["AAA"].loc[future, "close"] *= 100.0
    second = build_volatility_prediction(config, verified_manifest, bundle, changed, **kwargs)
    assert first["values"] == second["values"]
    assert first["feature_snapshot_hash"] == second["feature_snapshot_hash"]


def test_incomplete_artifact_produces_complete_unavailable_contract(tmp_path):
    _store, config, config_path, artifact_dir, _provider_path, _manifest = _registered_store(
        tmp_path
    )
    verified_manifest, bundle, _report = verify_runtime_artifacts(config, artifact_dir)
    frames = load_price_frames(
        config,
        config_directory=config_path.parent,
        requested_tickers=(*config.subjects, "SPY", "QQQ", "SOXX"),
    )
    incomplete = dict(bundle)
    incomplete.pop("prospective_profile")
    result = build_volatility_prediction(
        config,
        verified_manifest,
        incomplete,
        frames,
        subject="AAA",
        as_of_session="2026-02-25",
        generated_at="2026-02-25T21:05:00+00:00",
        decision_cutoff=resolve_decision_cutoff("2026-02-25"),
        target_available_at=resolve_target_availability("2026-02-25", 20),
        evidence_epoch="epoch",
        shadow_run_id="run",
    )
    prospective = result["prospective_contract"]
    assert result["available"] is False
    assert "prospective_profile_unavailable" in result["refusal_reasons"]
    assert prospective["point_estimate"] is None
    assert prospective["prediction_interval"] is None
    assert prospective["threshold_probability"] is None
    assert prospective["lineage"]["evaluation_report_hash"] == verified_manifest.evaluation_report_hash
    assert all(feature["missing"] for feature in prospective["feature_observations"])


def test_artifact_corruption_fails_the_claimed_run_and_emits_a_durable_alert(
    tmp_path, capsys, monkeypatch
):
    store, config, config_path, artifact_dir, _provider_path, _manifest = _registered_store(
        tmp_path
    )
    monkeypatch.setattr(
        run_ml_shadow,
        "current_commit",
        lambda **_kwargs: "d" * 40,
    )
    (artifact_dir / "vol.joblib").write_bytes(b"tampered")
    exit_code = run_ml_shadow.main(
        [
            "--database",
            str(store.path),
            "--config",
            str(config_path),
            "--artifact-dir",
            str(artifact_dir),
            "predict",
            "--scheduled-for",
            resolve_decision_cutoff("2026-02-25"),
            "--started-at",
            "2026-02-25T21:05:00+00:00",
            "--code-commit",
            "d" * 40,
        ]
    )
    assert exit_code == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["error_kind"] == "artifact_mismatch"
    runs = store.list_ml_shadow_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"]["kind"] == "artifact_mismatch"
    alerts = store.list_operational_alerts()
    assert any(alert["category"] == "ml_shadow" for alert in alerts)
    predictions = store.list_ml_predictions()
    assert len(predictions) == 2
    assert all(not prediction["available"] for prediction in predictions)
    assert all(
        "artifact_mismatch" in prediction["refusal_reasons"]
        for prediction in predictions
    )
    assert all(
        prediction["prediction"]["prospective_contract"]["available"] is False
        for prediction in predictions
    )


def test_maturity_underfill_alerts_and_never_records_a_zero(tmp_path, capsys):
    store, config, config_path, artifact_dir, provider_path, _manifest = _registered_store(
        tmp_path
    )
    scheduled_for = resolve_decision_cutoff("2026-02-25")
    prediction = run_ml_shadow.command_predict(
        store,
        config,
        config_path,
        artifact_dir,
        scheduled_for=scheduled_for,
        code_commit="d" * 40,
        started_at="2026-02-25T21:05:00+00:00",
    )
    assert prediction["ok"]

    target_session = trading_sessions(
        date.fromisoformat("2026-02-25"), date.fromisoformat("2026-04-10")
    )[20].isoformat()
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["bars"]["AAA"] = [
        row for row in provider["bars"]["AAA"] if row["session"] != target_session
    ]
    provider_path.write_text(json.dumps(provider), encoding="utf-8")

    target_at = resolve_target_availability("2026-02-25", 20)
    exit_code = run_ml_shadow.main(
        [
            "--database",
            str(store.path),
            "--config",
            str(config_path),
            "--artifact-dir",
            str(artifact_dir),
            "mature",
            "--as-of",
            (datetime.fromisoformat(target_at) + timedelta(minutes=1)).isoformat(),
        ]
    )
    assert exit_code == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["outcome_underfill_count"] == 1
    assert len(store.list_ml_prediction_outcomes()) == 1
    outcomes = [row["outcome"] for row in store.list_ml_prediction_outcomes()]
    assert all(outcome["realized_daily_volatility_pct"] != 0 for outcome in outcomes)
    alerts = store.list_operational_alerts()
    assert any("outcome_underfill" in alert["message"] for alert in alerts)


def test_weekday_scheduler_skips_exchange_holidays_without_an_error():
    thanksgiving = datetime.fromisoformat("2026-11-26T22:00:00+00:00")
    assert run_ml_shadow._default_scheduled_for(thanksgiving) is None
    ordinary_session = datetime.fromisoformat("2026-11-25T22:00:00+00:00")
    assert run_ml_shadow._default_scheduled_for(ordinary_session) == resolve_decision_cutoff(
        "2026-11-25"
    )


def test_windows_scheduler_is_separate_bounded_and_caller_configured():
    path = Path(__file__).resolve().parent.parent / "scripts" / "install_windows_ml_shadow_tasks.ps1"
    source = path.read_text(encoding="utf-8")
    for required in (
        "$PythonPath",
        "$DatabasePath",
        "$ConfigPath",
        "$ArtifactPath",
        "MultipleInstances IgnoreNew",
        "RestartCount 3",
        "ExecutionTimeLimit",
        "run_ml_shadow.py",
        " predict",
        " mature",
        " monitor",
    ):
        assert required in source
    assert "run_personal_assistant.py" not in source
    assert "monitor-orders" not in source


def test_shadow_cli_has_no_execution_or_proposal_imports():
    path = Path(__file__).resolve().parent.parent / "scripts" / "run_ml_shadow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "execution",
        "risk.execution_gate",
        "assistant.execution_service",
        "assistant.allocation_batch",
        "assistant.proposals",
        "assistant.strategy_proposals",
    )
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [
        name for name in imported if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    ]
