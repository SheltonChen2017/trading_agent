"""Frozen portfolio-volatility dataset and forecast contracts (ML-FS-4)."""
from __future__ import annotations

import dataclasses
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import pandas as pd

from ml.datasets import assemble_dataset_frames
from ml.experiment_contracts import ExperimentSpec
from ml.hashing import hash_payload
from ml.labels import LabelRow
from ml.portfolio_experiments import (
    TargetBuildResult,
    assess_portfolio_research_readiness,
)


TASK = "portfolio_volatility_forecast"
OBSERVATION_UNIT = "account_session"
DAILY_TARGET_UNITS = "daily_return_standard_deviation_pct"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN = frozenset(
    {"side", "shares", "quantity", "order_type", "limit_price", "execute", "approved"}
)


class PortfolioResearchError(ValueError):
    pass


def _strings(values: Sequence[str], name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or len(result) != len(set(result)):
        raise PortfolioResearchError(f"{name} must be non-empty and unique")
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise PortfolioResearchError(f"{name} must contain non-empty strings")
    return result


@dataclasses.dataclass(frozen=True)
class PortfolioDatasetContract:
    feature_set_version: str
    label_version: str
    target_kind: str
    horizon_sessions: int
    ordered_feature_names: tuple[str, ...]
    trailing_baseline_column: str
    ewma_baseline_column: str
    account_key: str
    observation_unit: str = OBSERVATION_UNIT
    target_units: str = DAILY_TARGET_UNITS

    def __post_init__(self) -> None:
        for name in (
            "feature_set_version", "label_version", "target_kind",
            "trailing_baseline_column", "ewma_baseline_column", "account_key",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PortfolioResearchError(f"{name} must be a non-empty string")
        if self.target_kind not in {"frozen_weight", "realized_account"}:
            raise PortfolioResearchError("target_kind must be frozen_weight or realized_account")
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions < 2
        ):
            raise PortfolioResearchError("horizon_sessions must be an integer >= 2")
        features = _strings(self.ordered_feature_names, "ordered_feature_names")
        if "cash_weight" not in features:
            raise PortfolioResearchError("portfolio features must retain cash_weight")
        forbidden = set(features) & _FORBIDDEN
        if forbidden:
            raise PortfolioResearchError(f"portfolio features contain authority fields: {sorted(forbidden)}")
        if self.trailing_baseline_column == self.ewma_baseline_column:
            raise PortfolioResearchError("portfolio baselines must use distinct columns")
        if self.observation_unit != OBSERVATION_UNIT:
            raise PortfolioResearchError(f"observation_unit must be {OBSERVATION_UNIT}")
        if self.target_units != DAILY_TARGET_UNITS:
            raise PortfolioResearchError(f"target_units must be {DAILY_TARGET_UNITS}")
        object.__setattr__(self, "ordered_feature_names", features)

    @property
    def contract_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PortfolioDatasetBuild:
    available: bool
    features: pd.DataFrame
    labels: pd.DataFrame
    readiness: Mapping[str, Any]
    refusals: tuple[Mapping[str, str], ...]
    contract_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise PortfolioResearchError("available must be boolean")
        object.__setattr__(self, "features", self.features.copy(deep=True))
        object.__setattr__(self, "labels", self.labels.copy(deep=True))
        object.__setattr__(self, "readiness", MappingProxyType(dict(self.readiness)))
        object.__setattr__(
            self, "refusals", tuple(MappingProxyType(dict(item)) for item in self.refusals)
        )


def build_portfolio_dataset_frames(
    feature_rows: pd.DataFrame,
    targets: TargetBuildResult,
    contract: PortfolioDatasetContract,
    *,
    minimum_targets: int = 60,
    n_splits: int = 2,
    embargo_sessions: int | None = None,
) -> PortfolioDatasetBuild:
    """Bind supplied account features to real targets; never guess missing rows."""
    if not isinstance(feature_rows, pd.DataFrame):
        raise PortfolioResearchError("feature_rows must be a DataFrame")
    required_columns = list(dict.fromkeys([
        "ticker", "as_of_session", *contract.ordered_feature_names,
        contract.trailing_baseline_column, contract.ewma_baseline_column,
    ]))
    missing = sorted(set(required_columns) - set(feature_rows.columns))
    if missing:
        raise PortfolioResearchError(f"portfolio feature rows are missing columns: {missing}")
    working = feature_rows[required_columns].copy()
    if working.duplicated(["as_of_session", "ticker"]).any():
        raise PortfolioResearchError("portfolio feature rows have duplicate account-session keys")
    if set(working["ticker"]) != {contract.account_key}:
        raise PortfolioResearchError("portfolio feature rows do not match contract.account_key")
    working = working.sort_values(["as_of_session", "ticker"]).reset_index(drop=True)
    numeric_columns = [
        *contract.ordered_feature_names,
        contract.trailing_baseline_column,
        contract.ewma_baseline_column,
    ]
    numeric = working[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not numeric.map(lambda value: math.isfinite(float(value))).all().all():
        raise PortfolioResearchError("portfolio feature and baseline values must be finite")
    working[numeric_columns] = numeric
    if ((working["cash_weight"] < 0) | (working["cash_weight"] > 1)).any():
        raise PortfolioResearchError("cash_weight must be within [0, 1]")
    if (
        (working[contract.trailing_baseline_column] <= 0).any()
        or (working[contract.ewma_baseline_column] <= 0).any()
    ):
        raise PortfolioResearchError("portfolio volatility baselines must be positive")

    target_rows = [
        target for target in targets.targets
        if target.account_key == contract.account_key
        and target.target_kind == contract.target_kind
        and target.horizon_sessions == contract.horizon_sessions
    ]
    excluded = len(targets.targets) - len(target_rows)
    refusals = [dict(item) for item in targets.refusals]
    if excluded:
        refusals.append({
            "as_of_session": "multiple",
            "reason": f"{excluded} target(s) did not match the frozen contract identity",
        })
    feature_keys = set(zip(working["as_of_session"], working["ticker"]))
    labels_by_ticker: dict[str, list[LabelRow]] = {contract.account_key: []}
    matched_targets = []
    for target in target_rows:
        key = (target.as_of_session, target.account_key)
        if key not in feature_keys:
            refusals.append({
                "as_of_session": target.as_of_session,
                "reason": "missing frozen portfolio feature row",
            })
            continue
        labels_by_ticker[contract.account_key].append(
            LabelRow(
                ticker=target.account_key,
                as_of_session=target.as_of_session,
                label_version=contract.label_version,
                entry_session=target.first_return_session,
                entry_price=1.0,
                exit_session=target.last_return_session,
                exit_price=1.0,
                value=float(target.daily_volatility_pct),
                components={
                    "daily_portfolio_volatility_pct": float(target.daily_volatility_pct),
                    "cash_weight": float(target.cash_weight),
                },
            )
        )
        matched_targets.append(target)
    effective_result = TargetBuildResult(
        targets=tuple(matched_targets), refusals=tuple(refusals)
    )
    readiness = assess_portfolio_research_readiness(
        effective_result,
        minimum_targets=minimum_targets,
        n_splits=n_splits,
        embargo_sessions=embargo_sessions or contract.horizon_sessions,
    )
    if not labels_by_ticker[contract.account_key]:
        return PortfolioDatasetBuild(
            available=False,
            features=pd.DataFrame(),
            labels=pd.DataFrame(),
            readiness=readiness,
            refusals=tuple(refusals),
            contract_hash=contract.contract_hash,
        )
    matched_keys = {
        (row.as_of_session, row.ticker) for row in labels_by_ticker[contract.account_key]
    }
    matched_features = working[
        working.apply(lambda row: (row["as_of_session"], row["ticker"]) in matched_keys, axis=1)
    ]
    features, labels = assemble_dataset_frames(
        {contract.account_key: matched_features}, labels_by_ticker
    )
    available = bool(readiness["ready"])
    return PortfolioDatasetBuild(
        available=available,
        features=features if available else pd.DataFrame(),
        labels=labels if available else pd.DataFrame(),
        readiness=readiness,
        refusals=tuple(refusals),
        contract_hash=contract.contract_hash,
    )


def validate_portfolio_experiment_spec(spec: ExperimentSpec) -> None:
    if spec.task != TASK:
        raise PortfolioResearchError(f"portfolio spec task must be {TASK}")
    parameters = dict(spec.task_parameters)
    expected = {"observation_unit", "target_kind", "target_units"}
    if set(parameters) != expected:
        raise PortfolioResearchError(
            f"portfolio task_parameters must contain exactly {sorted(expected)}"
        )
    if parameters["observation_unit"] != OBSERVATION_UNIT:
        raise PortfolioResearchError("portfolio observation_unit must be account_session")
    if parameters["target_kind"] not in {"frozen_weight", "realized_account"}:
        raise PortfolioResearchError("portfolio target_kind is invalid")
    if parameters["target_units"] != DAILY_TARGET_UNITS:
        raise PortfolioResearchError("portfolio target_units are invalid")


@dataclasses.dataclass(frozen=True)
class PortfolioVolatilityForecast:
    account_key: str
    target_kind: str
    horizon_sessions: int
    as_of_session: str
    daily_volatility_pct: float | None
    prediction_interval_daily_pct: tuple[float, float] | None
    probability_above_mandate_ceiling: float | None
    model_key: str
    dataset_hash: str
    evaluation_report_hash: str
    feature_snapshot_hash: str
    evidence_status: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("account_key", "target_kind", "as_of_session", "model_key", "evidence_status"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PortfolioResearchError(f"{name} must be a non-empty string")
        if self.target_kind not in {"frozen_weight", "realized_account"}:
            raise PortfolioResearchError("forecast target_kind is invalid")
        parsed = pd.to_datetime(self.as_of_session, format="%Y-%m-%d", errors="coerce")
        if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != self.as_of_session:
            raise PortfolioResearchError("as_of_session must be canonical YYYY-MM-DD")
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions < 2
        ):
            raise PortfolioResearchError("horizon_sessions must be an integer >= 2")
        for name in ("dataset_hash", "evaluation_report_hash", "feature_snapshot_hash"):
            if not isinstance(getattr(self, name), str) or not _SHA256.fullmatch(getattr(self, name)):
                raise PortfolioResearchError(f"{name} must be a lowercase SHA-256 hash")
        if not isinstance(self.available, bool):
            raise PortfolioResearchError("available must be boolean")
        if self.available:
            if self.refusal_reasons:
                raise PortfolioResearchError("available forecast cannot carry refusals")
            if self.daily_volatility_pct is None or not math.isfinite(self.daily_volatility_pct) or self.daily_volatility_pct <= 0:
                raise PortfolioResearchError("available forecast requires positive daily volatility")
            interval = self.prediction_interval_daily_pct
            if not isinstance(interval, tuple) or len(interval) != 2:
                raise PortfolioResearchError("available forecast requires a daily interval")
            if not (0 < interval[0] <= self.daily_volatility_pct <= interval[1]):
                raise PortfolioResearchError("daily interval must contain the point forecast")
            probability = self.probability_above_mandate_ceiling
            if probability is None or not 0 <= probability <= 1:
                raise PortfolioResearchError("ceiling probability must be within [0, 1]")
        elif (
            not self.refusal_reasons
            or self.daily_volatility_pct is not None
            or self.prediction_interval_daily_pct is not None
            or self.probability_above_mandate_ceiling is not None
        ):
            raise PortfolioResearchError(
                "unavailable forecast requires reasons and cannot carry predictions"
            )

    @property
    def task(self) -> str:
        return TASK

    @property
    def annualized_volatility_pct(self) -> float | None:
        return None if self.daily_volatility_pct is None else self.daily_volatility_pct * math.sqrt(252)

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            **dataclasses.asdict(self),
            "prediction_interval_daily_pct": (
                list(self.prediction_interval_daily_pct)
                if self.prediction_interval_daily_pct is not None else None
            ),
            "task": self.task,
            "annualized_volatility_pct": self.annualized_volatility_pct,
            "production_authoritative": False,
        }
