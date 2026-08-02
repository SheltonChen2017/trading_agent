from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from ml.portfolio_experiments import TargetBuildResult
from ml.portfolio_research import (
    DAILY_TARGET_UNITS,
    OBSERVATION_UNIT,
    TASK,
    PortfolioDatasetContract,
    PortfolioResearchError,
    PortfolioVolatilityForecast,
    build_portfolio_dataset_frames,
)
from ml.portfolio_volatility import PortfolioVolatilityTarget


def _target(session: str, first: str, last: str) -> PortfolioVolatilityTarget:
    return PortfolioVolatilityTarget(
        account_key="alpaca:paper:account-1",
        as_of_session=session,
        target_kind="frozen_weight",
        horizon_sessions=5,
        daily_volatility_pct=1.25,
        observation_count=5,
        weights={"NVDA": 0.7},
        cash_weight=0.3,
        first_return_session=first,
        last_return_session=last,
        position_snapshot_hash="a" * 64,
        price_input_hash="b" * 64,
    )


def _fixture(n: int = 30):
    sessions = pd.bdate_range("2026-01-02", periods=n + 5)
    targets = tuple(
        _target(
            str(sessions[index].date()),
            str(sessions[index + 1].date()),
            str(sessions[index + 5].date()),
        )
        for index in range(n)
    )
    features = pd.DataFrame(
        {
            "ticker": ["alpaca:paper:account-1"] * n,
            "as_of_session": [target.as_of_session for target in targets],
            "cash_weight": [0.3] * n,
            "position_count": [1.0] * n,
            "trailing_return_20d_pct": [2.0 + index / 100 for index in range(n)],
            "trailing_portfolio_vol_pct": [1.4] * n,
            "ewma_portfolio_vol_pct": [1.3] * n,
        }
    )
    return features, TargetBuildResult(targets=targets, refusals=())


def _contract(**overrides) -> PortfolioDatasetContract:
    payload = dict(
        feature_set_version="portfolio-fs-v1",
        label_version="portfolio-vol-v1",
        target_kind="frozen_weight",
        horizon_sessions=5,
        ordered_feature_names=(
            "cash_weight", "position_count", "trailing_return_20d_pct",
        ),
        trailing_baseline_column="trailing_portfolio_vol_pct",
        ewma_baseline_column="ewma_portfolio_vol_pct",
        account_key="alpaca:paper:account-1",
    )
    payload.update(overrides)
    return PortfolioDatasetContract(**payload)


def test_frozen_contract_retains_cash_and_separates_portfolio_identity():
    contract = _contract()
    assert contract.observation_unit == OBSERVATION_UNIT
    assert contract.target_units == DAILY_TARGET_UNITS
    assert contract.contract_hash == _contract().contract_hash
    with pytest.raises(PortfolioResearchError, match="retain cash_weight"):
        _contract(ordered_feature_names=("position_count",))
    with pytest.raises(PortfolioResearchError, match="authority fields"):
        _contract(ordered_feature_names=("cash_weight", "shares"))


def test_ready_portfolio_history_builds_shared_runner_frames():
    features, targets = _fixture()
    built = build_portfolio_dataset_frames(
        features, targets, _contract(),
        minimum_targets=20, n_splits=2, embargo_sessions=5,
    )
    assert built.available is True
    assert len(built.features) == 30
    assert len(built.labels) == 30
    assert set(built.features["ticker"]) == {"alpaca:paper:account-1"}
    assert set(built.labels["label_version"]) == {"portfolio-vol-v1"}
    assert set(built.labels["value"]) == {1.25}
    assert "cash_weight" in built.features


def test_missing_feature_rows_remain_underfill_instead_of_guessed():
    features, targets = _fixture(n=20)
    features = features.iloc[:-1]
    built = build_portfolio_dataset_frames(
        features, targets, _contract(),
        minimum_targets=20, n_splits=2, embargo_sessions=5,
    )
    assert built.available is False
    assert built.features.empty and built.labels.empty
    assert any("missing frozen portfolio feature row" in item["reason"] for item in built.refusals)
    assert built.readiness["status"] == "underfilled"


def test_portfolio_forecast_is_typed_daily_and_never_authoritative():
    forecast = PortfolioVolatilityForecast(
        account_key="alpaca:paper:account-1",
        target_kind="frozen_weight",
        horizon_sessions=5,
        as_of_session="2026-07-31",
        daily_volatility_pct=1.2,
        prediction_interval_daily_pct=(0.9, 1.6),
        probability_above_mandate_ceiling=0.2,
        model_key="portfolio-vol-v1",
        dataset_hash="a" * 64,
        evaluation_report_hash="b" * 64,
        feature_snapshot_hash="c" * 64,
        evidence_status="exploratory",
        available=True,
    )
    payload = forecast.to_dict()
    assert payload["task"] == TASK
    assert payload["annualized_volatility_pct"] > payload["daily_volatility_pct"]
    assert payload["production_authoritative"] is False
    assert not set(payload) & {"side", "shares", "execute", "approved"}


def test_unavailable_portfolio_forecast_cannot_smuggle_predictions():
    unavailable = PortfolioVolatilityForecast(
        account_key="alpaca:paper:account-1",
        target_kind="frozen_weight",
        horizon_sessions=5,
        as_of_session="2026-07-31",
        daily_volatility_pct=None,
        prediction_interval_daily_pct=None,
        probability_above_mandate_ceiling=None,
        model_key="portfolio-vol-v1",
        dataset_hash="a" * 64,
        evaluation_report_hash="b" * 64,
        feature_snapshot_hash="c" * 64,
        evidence_status="unavailable",
        available=False,
        refusal_reasons=("portfolio history is underfilled",),
    )
    assert unavailable.annualized_volatility_pct is None
    with pytest.raises(PortfolioResearchError, match="cannot carry predictions"):
        PortfolioVolatilityForecast(
            **{
                **unavailable.__dict__,
                "daily_volatility_pct": 1.0,
            }
        )


def test_portfolio_research_module_has_no_execution_imports():
    tree = ast.parse(Path("ml/portfolio_research.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(
        name.startswith(("execution", "assistant.execution_service", "assistant.storage"))
        for name in imported
    )
