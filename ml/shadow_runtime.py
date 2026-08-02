"""Verified volatility scoring and outcome construction for ML-LR-6.

This module contains the model/data side of the shadow runtime.  It has no
database, proposal, broker, or execution imports.  The dedicated
``scripts/run_ml_shadow.py`` adapter owns persistence and operational alerts.

Only ``volatility_forecast`` is supported here.  ML-LR-6's definition of done
requires one supervised task to run predict/mature/monitor repeatedly; making
an untested generic adapter for the earnings and ranker models would only hide
task-specific label and feature semantics behind a common-looking interface.
"""
from __future__ import annotations

import dataclasses
import json
import math
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from assistant.schemas import EvidenceStatus
from ml.artifacts import load_model_artifact, load_model_manifest
from ml.contracts import ModelManifest, PredictionRecord, require_matching_feature_order
from ml.features import FeatureError, compute_point_in_time_features
from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.labels import compute_forward_realized_vol_labels
from ml.prospective import (
    DAILY_VOLATILITY_UNIT,
    ProspectiveContractError,
    ProspectiveInferenceContract,
    derive_volatility_uncertainty,
)
from ml.shadow import trading_sessions
from ml.volatility import (
    VolatilityModelError,
    annualize_pct,
    forecast_ewma_baseline,
    forecast_trailing_baseline,
    predict_volatility,
)

RUNTIME_SCHEMA_VERSION = "1"
SUPPORTED_TASK = "volatility_forecast"
REQUIRED_BENCHMARKS = ("SPY", "QQQ", "SOXX")
_SHA256_LENGTH = 64
_CONFIG_KEYS = frozenset(
    {
        "schema_version",
        "task",
        "schedule_key",
        "schedule_version",
        "model_id",
        "model_version",
        "manifest_filename",
        "manifest_hash",
        "artifact_filename",
        "evaluation_report_filename",
        "subjects",
        "horizon_sessions",
        "data_provider",
        "market_benchmark",
        "trailing_baseline_window",
        "ewma_halflife",
        "earnings_dates_by_subject",
    }
)


class ShadowRuntimeError(ValueError):
    """A shadow configuration, input, artifact, or model output is unsafe."""


class ShadowProviderError(ShadowRuntimeError):
    """The configured market-data provider failed or returned invalid data."""


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowRuntimeError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ShadowRuntimeError(f"{name} must not contain surrounding whitespace")
    return value


def _positive_int(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ShadowRuntimeError(f"{name} must be an integer >= {minimum}")
    return value


def _positive_number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ShadowRuntimeError(f"{name} must be positive and finite")
    return float(value)


def _sha256(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if len(text) != _SHA256_LENGTH or any(c not in "0123456789abcdef" for c in text):
        raise ShadowRuntimeError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _plain_filename(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if text in {".", ".."} or Path(text).name != text or "/" in text or "\\" in text:
        raise ShadowRuntimeError(f"{name} must be one plain relative filename")
    return text


def _canonical_subject(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if text != text.upper() or not all(c.isalnum() or c in ".-" for c in text):
        raise ShadowRuntimeError(f"{name} must be a canonical uppercase ticker")
    return text


@dataclasses.dataclass(frozen=True)
class ShadowRuntimeConfig:
    """Frozen inputs that determine one scheduled shadow experiment."""

    task: str
    schedule_key: str
    schedule_version: str
    model_id: str
    model_version: str
    manifest_filename: str
    manifest_hash: str
    artifact_filename: str
    evaluation_report_filename: str
    subjects: tuple[str, ...]
    horizon_sessions: int
    data_provider: Mapping[str, Any]
    market_benchmark: str = "QQQ"
    trailing_baseline_window: int = 20
    ewma_halflife: float = 20.0
    earnings_dates_by_subject: Mapping[str, tuple[str, ...]] = dataclasses.field(
        default_factory=dict
    )
    schema_version: str = RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SCHEMA_VERSION:
            raise ShadowRuntimeError(
                f"unsupported shadow config schema_version {self.schema_version!r}"
            )
        if self.task != SUPPORTED_TASK:
            raise ShadowRuntimeError(
                f"unsupported shadow task {self.task!r}; supported: {SUPPORTED_TASK!r}"
            )
        for name in ("schedule_key", "schedule_version", "model_id", "model_version"):
            _required_text(getattr(self, name), name)
        _plain_filename(self.manifest_filename, "manifest_filename")
        _plain_filename(self.artifact_filename, "artifact_filename")
        _plain_filename(self.evaluation_report_filename, "evaluation_report_filename")
        _sha256(self.manifest_hash, "manifest_hash")
        if not isinstance(self.subjects, tuple) or not self.subjects:
            raise ShadowRuntimeError("subjects must contain at least one ticker")
        normalized_subjects = tuple(
            _canonical_subject(value, f"subjects[{index}]")
            for index, value in enumerate(self.subjects)
        )
        if len(set(normalized_subjects)) != len(normalized_subjects):
            raise ShadowRuntimeError("subjects must not contain duplicates")
        _positive_int(self.horizon_sessions, "horizon_sessions", minimum=2)
        _positive_int(self.trailing_baseline_window, "trailing_baseline_window", minimum=2)
        _positive_number(self.ewma_halflife, "ewma_halflife")
        market_benchmark = _canonical_subject(self.market_benchmark, "market_benchmark")
        if market_benchmark not in REQUIRED_BENCHMARKS:
            raise ShadowRuntimeError(
                f"market_benchmark must be one of {REQUIRED_BENCHMARKS}"
            )
        if not isinstance(self.data_provider, Mapping):
            raise ShadowRuntimeError("data_provider must be an object")
        provider = dict(self.data_provider)
        kind = _required_text(provider.get("kind"), "data_provider.kind")
        provider_id = _required_text(
            provider.get("provider_id"), "data_provider.provider_id"
        )
        if kind == "fixture_json":
            expected = {"kind", "provider_id", "path"}
            _required_text(provider.get("path"), "data_provider.path")
        elif kind == "yfinance_adjusted":
            expected = {"kind", "provider_id", "lookback_sessions"}
            _positive_int(
                provider.get("lookback_sessions"),
                "data_provider.lookback_sessions",
                minimum=260,
            )
            if "point_in_time=false" not in provider_id.lower():
                raise ShadowRuntimeError(
                    "yfinance_adjusted provider_id must explicitly contain "
                    "'point_in_time=false'; adjusted historical data cannot satisfy "
                    "the authoritative-data gate"
                )
        else:
            raise ShadowRuntimeError(
                "data_provider.kind must be 'fixture_json' or 'yfinance_adjusted'"
            )
        unknown_provider = set(provider) - expected
        missing_provider = expected - set(provider)
        if unknown_provider or missing_provider:
            raise ShadowRuntimeError(
                "data_provider keys do not match its kind: "
                f"missing={sorted(missing_provider)}, unknown={sorted(unknown_provider)}"
            )
        if not isinstance(self.earnings_dates_by_subject, Mapping):
            raise ShadowRuntimeError("earnings_dates_by_subject must be an object")
        earnings: dict[str, tuple[str, ...]] = {}
        for raw_subject, raw_dates in self.earnings_dates_by_subject.items():
            subject = _canonical_subject(raw_subject, "earnings_dates_by_subject key")
            if subject not in normalized_subjects:
                raise ShadowRuntimeError(
                    f"earnings_dates_by_subject contains unconfigured subject {subject!r}"
                )
            if not isinstance(raw_dates, (list, tuple)):
                raise ShadowRuntimeError(
                    f"earnings_dates_by_subject.{subject} must be an array"
                )
            dates: list[str] = []
            for index, raw_date in enumerate(raw_dates):
                text = _required_text(
                    raw_date, f"earnings_dates_by_subject.{subject}[{index}]"
                )
                try:
                    parsed = date.fromisoformat(text)
                except ValueError as exc:
                    raise ShadowRuntimeError(
                        f"earnings date {text!r} must use YYYY-MM-DD"
                    ) from exc
                if parsed.isoformat() != text:
                    raise ShadowRuntimeError(
                        f"earnings date {text!r} must use canonical YYYY-MM-DD"
                    )
                dates.append(text)
            if dates != sorted(set(dates)):
                raise ShadowRuntimeError(
                    f"earnings dates for {subject} must be sorted and unique"
                )
            earnings[subject] = tuple(dates)
        object.__setattr__(self, "subjects", normalized_subjects)
        object.__setattr__(self, "market_benchmark", market_benchmark)
        object.__setattr__(self, "data_provider", MappingProxyType(provider))
        object.__setattr__(self, "earnings_dates_by_subject", MappingProxyType(earnings))

    @property
    def model_key(self) -> str:
        return f"{self.model_id}:{self.model_version}"

    @property
    def provider_id(self) -> str:
        return str(self.data_provider["provider_id"])

    @property
    def configuration_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task": self.task,
            "schedule_key": self.schedule_key,
            "schedule_version": self.schedule_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "manifest_filename": self.manifest_filename,
            "manifest_hash": self.manifest_hash,
            "artifact_filename": self.artifact_filename,
            "evaluation_report_filename": self.evaluation_report_filename,
            "subjects": list(self.subjects),
            "horizon_sessions": self.horizon_sessions,
            "data_provider": dict(self.data_provider),
            "market_benchmark": self.market_benchmark,
            "trailing_baseline_window": self.trailing_baseline_window,
            "ewma_halflife": self.ewma_halflife,
            "earnings_dates_by_subject": {
                subject: list(dates)
                for subject, dates in self.earnings_dates_by_subject.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ShadowRuntimeConfig":
        if not isinstance(payload, Mapping):
            raise ShadowRuntimeError("shadow config must be one JSON object")
        unknown = set(payload) - _CONFIG_KEYS
        required = _CONFIG_KEYS - {
            "market_benchmark",
            "trailing_baseline_window",
            "ewma_halflife",
            "earnings_dates_by_subject",
        }
        missing = required - set(payload)
        if unknown or missing:
            raise ShadowRuntimeError(
                f"shadow config keys invalid: missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        kwargs = dict(payload)
        subjects = kwargs.get("subjects")
        if not isinstance(subjects, (list, tuple)):
            raise ShadowRuntimeError("subjects must be an array")
        kwargs["subjects"] = tuple(subjects)
        kwargs.setdefault("market_benchmark", "QQQ")
        kwargs.setdefault("trailing_baseline_window", kwargs.get("horizon_sessions", 20))
        kwargs.setdefault("ewma_halflife", 20.0)
        kwargs.setdefault("earnings_dates_by_subject", {})
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ShadowRuntimeError(f"invalid shadow config fields: {exc}") from exc


def load_shadow_config(path: Path) -> tuple[ShadowRuntimeConfig, dict[str, Any]]:
    """Load strict JSON config and prove its canonical representation."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowRuntimeError(f"could not read shadow config {path}: {exc}") from exc
    config = ShadowRuntimeConfig.from_dict(raw)
    # Hashing now catches NaN/infinity and unsupported JSON values, while
    # round-tripping through to_dict proves defaults are part of the frozen
    # configuration rather than invisible process behavior.
    canonical_json(config.to_dict())
    return config, config.to_dict()


def verify_runtime_artifacts(
    config: ShadowRuntimeConfig, artifact_directory: Path
) -> tuple[ModelManifest, Mapping[str, Any], Mapping[str, Any]]:
    """Verify manifest, evaluation report, and artifact before scoring."""
    directory = Path(artifact_directory)
    manifest = load_model_manifest(
        directory=directory,
        filename=config.manifest_filename,
        model_id=config.model_id,
        model_version=config.model_version,
        expected_manifest_hash=config.manifest_hash,
    )
    if manifest.task != config.task:
        raise ShadowRuntimeError(
            f"model manifest task {manifest.task!r} does not match {config.task!r}"
        )
    report_path = directory / _plain_filename(
        config.evaluation_report_filename, "evaluation_report_filename"
    )
    try:
        report_bytes = report_path.read_bytes()
    except OSError as exc:
        raise ShadowRuntimeError(f"could not read evaluation report {report_path}") from exc
    report_hash = hash_bytes(report_bytes)
    if report_hash != manifest.evaluation_report_hash:
        raise ShadowRuntimeError(
            f"evaluation report hash mismatch: manifest declares "
            f"{manifest.evaluation_report_hash}, file hashes to {report_hash}"
        )
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowRuntimeError("evaluation report is not valid UTF-8 JSON") from exc
    if not isinstance(report, Mapping):
        raise ShadowRuntimeError("evaluation report must contain one JSON object")
    bundle = load_model_artifact(
        manifest, directory=directory, filename=config.artifact_filename
    )
    _validate_model_bundle(manifest, bundle)
    return manifest, MappingProxyType(dict(bundle)), MappingProxyType(dict(report))


def _validate_model_bundle(manifest: ModelManifest, bundle: Any) -> None:
    if not isinstance(bundle, Mapping):
        raise ShadowRuntimeError("model artifact must contain a model bundle object")
    required = {"estimator", "standardizer", "ordered_feature_names"}
    if not required <= set(bundle):
        raise ShadowRuntimeError(
            f"model bundle is missing fields: {sorted(required - set(bundle))}"
        )
    ordered = tuple(bundle["ordered_feature_names"])
    require_matching_feature_order(manifest, ordered)
    standardizer = bundle["standardizer"]
    if not isinstance(standardizer, Mapping):
        raise ShadowRuntimeError("model bundle standardizer must be an object")
    standardizer_names = tuple(standardizer.get("feature_names", ()))
    if standardizer_names != ordered:
        raise ShadowRuntimeError("standardizer feature order does not match model manifest")
    means = standardizer.get("means")
    scales = standardizer.get("scales")
    if not isinstance(means, Mapping) or not isinstance(scales, Mapping):
        raise ShadowRuntimeError("standardizer means/scales must be objects")
    if set(means) != set(ordered) or set(scales) != set(ordered):
        raise ShadowRuntimeError("standardizer means/scales do not match model features")
    for name in ordered:
        try:
            mean = float(means[name])
            scale = float(scales[name])
        except (TypeError, ValueError) as exc:
            raise ShadowRuntimeError(
                f"standardizer value for {name!r} is not numeric"
            ) from exc
        if not math.isfinite(mean) or not math.isfinite(scale) or scale <= 0:
            raise ShadowRuntimeError(
                f"standardizer for {name!r} must have finite mean and positive scale"
            )
    if not callable(getattr(bundle["estimator"], "predict", None)):
        raise ShadowRuntimeError("model bundle estimator has no callable predict method")
    reference = bundle.get("feature_reference")
    if reference is not None:
        if not isinstance(reference, Mapping) or set(reference) != set(ordered):
            raise ShadowRuntimeError(
                "feature_reference must contain exactly the model's ordered features"
            )
        for name, summary in reference.items():
            if not isinstance(summary, Mapping):
                raise ShadowRuntimeError(f"feature_reference.{name} must be an object")
            edges = summary.get("bin_edges")
            counts = summary.get("bin_counts")
            independent_dates = summary.get("independent_date_count")
            if (
                not isinstance(edges, (list, tuple))
                or not isinstance(counts, (list, tuple))
                or len(counts) != len(edges) + 1
                or isinstance(independent_dates, bool)
                or not isinstance(independent_dates, int)
                or independent_dates < 1
            ):
                raise ShadowRuntimeError(
                    f"feature_reference.{name} has invalid bins or sample count"
                )
            try:
                numeric_edges = [float(value) for value in edges]
                numeric_counts = [int(value) for value in counts]
            except (TypeError, ValueError) as exc:
                raise ShadowRuntimeError(
                    f"feature_reference.{name} bins/counts must be numeric"
                ) from exc
            if (
                any(not math.isfinite(value) for value in numeric_edges)
                or numeric_edges != sorted(set(numeric_edges))
                or any(value < 0 for value in numeric_counts)
                or sum(numeric_counts) != independent_dates
            ):
                raise ShadowRuntimeError(
                    f"feature_reference.{name} is internally inconsistent"
                )


def _fixture_frame(rows: Any, ticker: str) -> pd.DataFrame:
    if not isinstance(rows, list) or not rows:
        raise ShadowProviderError(f"fixture bars for {ticker} must be a non-empty array")
    required = ("session", "open", "high", "low", "close", "volume")
    parsed_rows: list[dict[str, Any]] = []
    sessions: list[pd.Timestamp] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ShadowProviderError(f"fixture bars {ticker}[{index}] must be an object")
        missing = [name for name in required if name not in row]
        if missing:
            raise ShadowProviderError(
                f"fixture bars {ticker}[{index}] is missing {missing}"
            )
        raw_session = row["session"]
        if not isinstance(raw_session, str):
            raise ShadowProviderError(f"fixture bars {ticker}[{index}].session is invalid")
        session = pd.to_datetime(raw_session, format="%Y-%m-%d", errors="coerce")
        if pd.isna(session) or session.strftime("%Y-%m-%d") != raw_session:
            raise ShadowProviderError(
                f"fixture bars {ticker}[{index}].session must use canonical YYYY-MM-DD"
            )
        sessions.append(session)
        parsed_rows.append({name: row[name] for name in required if name != "session"})
    index = pd.DatetimeIndex(sessions)
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ShadowProviderError(f"fixture bars for {ticker} must be sorted and unique")
    return pd.DataFrame(parsed_rows, index=index)


def load_price_frames(
    config: ShadowRuntimeConfig,
    *,
    config_directory: Path,
    requested_tickers: Sequence[str],
) -> dict[str, pd.DataFrame]:
    """Load configured bars.  Callers still slice them at the decision cutoff."""
    tickers = tuple(dict.fromkeys(_canonical_subject(t, "requested ticker") for t in requested_tickers))
    if config.data_provider["kind"] == "fixture_json":
        raw_path = Path(str(config.data_provider["path"]))
        path = raw_path if raw_path.is_absolute() else Path(config_directory) / raw_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ShadowProviderError(f"could not read fixture provider data {path}: {exc}") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("bars"), Mapping):
            raise ShadowProviderError("fixture provider must contain a 'bars' object")
        frames = {
            ticker: _fixture_frame(payload["bars"][ticker], ticker)
            for ticker in tickers
            if ticker in payload["bars"]
        }
    else:
        try:
            from data.market_data import fetch_historical

            frames = fetch_historical(
                list(tickers),
                lookback_days=int(config.data_provider["lookback_sessions"]),
            )
        except Exception as exc:
            raise ShadowProviderError(
                f"yfinance provider failed: {type(exc).__name__}: {exc}"
            ) from exc
    missing_benchmarks = sorted(set(REQUIRED_BENCHMARKS) - set(frames))
    if missing_benchmarks:
        raise ShadowProviderError(
            f"provider omitted required benchmark bars: {missing_benchmarks}"
        )
    return frames


def build_unavailable_prediction(
    *,
    config: ShadowRuntimeConfig,
    manifest: ModelManifest,
    subject: str,
    as_of_session: str,
    generated_at: str,
    data_available_at: str,
    target_available_at: str,
    reasons: Sequence[str],
    feature_freshness: Mapping[str, Any],
    evidence_epoch: str,
    shadow_run_id: str,
    snapshot_material: Mapping[str, Any],
) -> dict[str, Any]:
    unique_reasons = tuple(dict.fromkeys(str(reason) for reason in reasons if str(reason)))
    snapshot_hash = hash_payload(
        {
            "provider_id": config.provider_id,
            "model_key": config.model_key,
            "subject": subject,
            "as_of_session": as_of_session,
            "available": False,
            "reasons": list(unique_reasons),
            "material": dict(snapshot_material),
        }
    )
    prediction_id = _prediction_id(config, subject, as_of_session)
    prospective = ProspectiveInferenceContract(
        prediction_id=prediction_id,
        task=config.task,
        subject_key=subject,
        as_of_session=as_of_session,
        generated_at=generated_at,
        horizon_sessions=config.horizon_sessions,
        target_available_at=target_available_at,
        point_estimate=None,
        prediction_interval=None,
        threshold_probability=None,
        calibration={"status": "unavailable", "reason": "prediction_unavailable"},
        frozen_baselines={
            "trailing_daily_pct": snapshot_material.get("trailing_baseline_daily_pct"),
            "ewma_daily_pct": snapshot_material.get("ewma_baseline_daily_pct"),
        },
        feature_observations=tuple(
            {
                "name": name,
                "value": None,
                "available_at": None,
                "age_sessions": None,
                "missing": True,
                "reason": unique_reasons[0] if unique_reasons else "unavailable_without_detail",
            }
            for name in manifest.ordered_feature_names
        ),
        reference_distribution={
            "status": "unavailable",
            "identity_hash": None,
            "reason": "prediction_inputs_or_artifact_unavailable",
        },
        regime_category="unavailable",
        event_category=(
            "earnings_session"
            if as_of_session in config.earnings_dates_by_subject.get(subject, ())
            else "ordinary_session"
        ),
        lineage=_prospective_lineage(
            config=config,
            manifest=manifest,
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            feature_snapshot_hash=snapshot_hash,
        ),
        available=False,
        refusal_reasons=unique_reasons or ("unavailable_without_detail",),
    )
    record = PredictionRecord(
        prediction_id=prediction_id,
        model_id=manifest.model_id,
        model_version=manifest.model_version,
        artifact_hash=manifest.artifact_hash,
        dataset_or_feature_snapshot_hash=snapshot_hash,
        task=config.task,
        subject_key=subject,
        as_of_session=as_of_session,
        generated_at=generated_at,
        horizon_sessions=config.horizon_sessions,
        target_available_at=target_available_at,
        values={},
        uncertainty={},
        data_available_at=data_available_at,
        feature_freshness=dict(feature_freshness),
        available=False,
        refusal_reasons=unique_reasons or ("unavailable_without_detail",),
        evidence_status=EvidenceStatus.UNAVAILABLE,
        prospective_contract=prospective.to_dict(),
    ).to_shadow_storage_dict()
    record["evidence_epoch"] = evidence_epoch
    record["shadow_run_id"] = shadow_run_id
    return record


def _prediction_id(
    config: ShadowRuntimeConfig, subject: str, as_of_session: str
) -> str:
    digest = hash_payload(
        {
            "model_key": config.model_key,
            "task": config.task,
            "subject_key": subject,
            "as_of_session": as_of_session,
            "horizon_sessions": config.horizon_sessions,
        }
    )
    return f"mlpred-{digest[:24]}"


def _prospective_lineage(
    *,
    config: ShadowRuntimeConfig,
    manifest: ModelManifest,
    evidence_epoch: str,
    shadow_run_id: str,
    feature_snapshot_hash: str,
) -> dict[str, str]:
    return {
        "model_key": config.model_key,
        "provider_id": config.provider_id,
        "dataset_id": manifest.dataset_id,
        "dataset_hash": manifest.dataset_hash,
        "artifact_hash": manifest.artifact_hash,
        "evaluation_report_hash": manifest.evaluation_report_hash,
        "feature_set_version": manifest.feature_set_version,
        "label_version": manifest.label_version,
        "configuration_hash": config.configuration_hash,
        "evidence_epoch": evidence_epoch,
        "shadow_run_id": shadow_run_id,
        "feature_snapshot_hash": feature_snapshot_hash,
        "schedule_version": config.schedule_version,
    }


def _prospective_reference(
    bundle: Mapping[str, Any], ordered_features: Sequence[str]
) -> tuple[dict[str, Any], str]:
    reference = bundle.get("feature_reference")
    if not isinstance(reference, Mapping) or set(reference) != set(ordered_features):
        raise ProspectiveContractError(
            "model artifact lacks the complete frozen feature reference distribution"
        )
    payload = {name: dict(reference[name]) for name in ordered_features}
    identity = hash_payload(payload)
    return payload, identity


def _prospective_regime(
    feature_values: Mapping[str, float], reference: Mapping[str, Any]
) -> tuple[str, str]:
    preferred = "realized_vol_20d_pct"
    name = preferred if preferred in feature_values else next(iter(feature_values))
    summary = reference.get(name)
    if not isinstance(summary, Mapping):
        raise ProspectiveContractError("regime reference feature is unavailable")
    mean = float(summary.get("mean"))
    if not math.isfinite(mean):
        raise ProspectiveContractError("regime reference mean is invalid")
    category = (
        "above_training_mean" if float(feature_values[name]) > mean
        else "at_or_below_training_mean"
    )
    return category, name


def build_volatility_prediction(
    config: ShadowRuntimeConfig,
    manifest: ModelManifest,
    bundle: Mapping[str, Any],
    frames: Mapping[str, pd.DataFrame],
    *,
    subject: str,
    as_of_session: str,
    generated_at: str,
    decision_cutoff: str,
    target_available_at: str,
    evidence_epoch: str,
    shadow_run_id: str,
) -> dict[str, Any]:
    """Build one available/refused attempt from data sliced at ``as_of``."""
    subject = _canonical_subject(subject, "subject")
    as_of = pd.Timestamp(as_of_session)
    if subject not in frames:
        return build_unavailable_prediction(
            config=config,
            manifest=manifest,
            subject=subject,
            as_of_session=as_of_session,
            generated_at=generated_at,
            data_available_at=decision_cutoff,
            target_available_at=target_available_at,
            reasons=("missing_subject_data",),
            feature_freshness={"missing_count": len(manifest.ordered_feature_names), "stale_count": 0, "maximum_age_sessions": 0},
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            snapshot_material={},
        )

    sliced_frames = {
        ticker: frame.loc[frame.index <= as_of].copy()
        for ticker, frame in frames.items()
    }
    subject_frame = sliced_frames[subject]
    if subject_frame.empty or as_of not in subject_frame.index:
        latest = (
            str(subject_frame.index[-1].date()) if not subject_frame.empty else None
        )
        stale_age = 0
        if latest is not None:
            stale_age = max(0, len(trading_sessions(date.fromisoformat(latest), as_of.date())) - 1)
        return build_unavailable_prediction(
            config=config,
            manifest=manifest,
            subject=subject,
            as_of_session=as_of_session,
            generated_at=generated_at,
            data_available_at=decision_cutoff,
            target_available_at=target_available_at,
            reasons=("as_of_session_unavailable",),
            feature_freshness={"missing_count": 0, "stale_count": len(manifest.ordered_feature_names), "maximum_age_sessions": stale_age},
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            snapshot_material={"latest_subject_session": latest},
        )

    benchmarks = {
        ticker: sliced_frames[ticker]["close"] for ticker in REQUIRED_BENCHMARKS
    }
    try:
        features = compute_point_in_time_features(
            subject,
            subject_frame,
            benchmarks=benchmarks,
            market_benchmark=config.market_benchmark,
            earnings_dates=config.earnings_dates_by_subject.get(subject, ()),
        )
    except (FeatureError, KeyError, TypeError, ValueError) as exc:
        return build_unavailable_prediction(
            config=config,
            manifest=manifest,
            subject=subject,
            as_of_session=as_of_session,
            generated_at=generated_at,
            data_available_at=decision_cutoff,
            target_available_at=target_available_at,
            reasons=(f"feature_builder_failure:{type(exc).__name__}",),
            feature_freshness={"missing_count": len(manifest.ordered_feature_names), "stale_count": 0, "maximum_age_sessions": 0},
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            snapshot_material={"error": str(exc)},
        )

    row = features.loc[features["as_of_session"] == as_of_session]
    if len(row) != 1:
        raise ShadowRuntimeError(
            f"feature builder returned {len(row)} rows for {subject}/{as_of_session}"
        )
    missing_names = [name for name in manifest.ordered_feature_names if name not in row]
    numeric_values: dict[str, float] = {}
    invalid_names: list[str] = []
    if not missing_names:
        for name in manifest.ordered_feature_names:
            try:
                value = float(row.iloc[0][name])
            except (TypeError, ValueError):
                invalid_names.append(name)
                continue
            if not math.isfinite(value):
                invalid_names.append(name)
            else:
                numeric_values[name] = value

    returns = pd.to_numeric(subject_frame["close"], errors="coerce").pct_change(
        fill_method=None
    )
    trailing = forecast_trailing_baseline(
        returns, horizon_sessions=config.trailing_baseline_window
    )
    ewma = forecast_ewma_baseline(returns, halflife=config.ewma_halflife)
    reasons: list[str] = []
    if missing_names:
        reasons.append(f"missing_features:{','.join(missing_names)}")
    if invalid_names:
        reasons.append(f"nonfinite_features:{','.join(invalid_names)}")
    if trailing is None or ewma is None:
        reasons.append("frozen_baseline_unavailable")
    if not isinstance(bundle.get("prospective_profile"), Mapping):
        reasons.append("prospective_profile_unavailable")
    if not isinstance(bundle.get("feature_reference"), Mapping):
        reasons.append("reference_distribution_unavailable")
    snapshot_material = {
        "ordered_features": numeric_values,
        "trailing_baseline_daily_pct": trailing,
        "ewma_baseline_daily_pct": ewma,
        "decision_cutoff": decision_cutoff,
    }
    if reasons:
        return build_unavailable_prediction(
            config=config,
            manifest=manifest,
            subject=subject,
            as_of_session=as_of_session,
            generated_at=generated_at,
            data_available_at=decision_cutoff,
            target_available_at=target_available_at,
            reasons=reasons,
            feature_freshness={"missing_count": len(missing_names) + len(invalid_names), "stale_count": 0, "maximum_age_sessions": 0},
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            snapshot_material=snapshot_material,
        )

    ordered = tuple(manifest.ordered_feature_names)
    require_matching_feature_order(manifest, ordered)
    standardizer = bundle["standardizer"]
    standardized = np.asarray(
        [
            (numeric_values[name] - float(standardizer["means"][name]))
            / float(standardizer["scales"][name])
            for name in ordered
        ],
        dtype=float,
    ).reshape(1, -1)
    try:
        daily_volatility = float(predict_volatility(bundle["estimator"], standardized)[0])
    except (VolatilityModelError, TypeError, ValueError, IndexError) as exc:
        raise ShadowRuntimeError(
            f"model output failed validation for {subject}: {type(exc).__name__}: {exc}"
        ) from exc
    feature_snapshot_hash = hash_payload(
        {
            "provider_id": config.provider_id,
            "model_key": config.model_key,
            "subject": subject,
            "as_of_session": as_of_session,
            **snapshot_material,
        }
    )
    uncertainty = derive_volatility_uncertainty(
        daily_volatility, bundle["prospective_profile"]
    )
    reference, reference_hash = _prospective_reference(bundle, ordered)
    regime_category, regime_feature = _prospective_regime(numeric_values, reference)
    prediction_id = _prediction_id(config, subject, as_of_session)
    event_category = (
        "earnings_session"
        if as_of_session in config.earnings_dates_by_subject.get(subject, ())
        else "ordinary_session"
    )
    prospective = ProspectiveInferenceContract(
        prediction_id=prediction_id,
        task=config.task,
        subject_key=subject,
        as_of_session=as_of_session,
        generated_at=generated_at,
        horizon_sessions=config.horizon_sessions,
        target_available_at=target_available_at,
        point_estimate={
            "value": round(daily_volatility, 6),
            "unit": DAILY_VOLATILITY_UNIT,
        },
        prediction_interval={
            "lower": uncertainty["prediction_interval_daily_pct"][0],
            "upper": uncertainty["prediction_interval_daily_pct"][1],
            "unit": DAILY_VOLATILITY_UNIT,
            "target_coverage": uncertainty["target_coverage"],
            "profile_hash": uncertainty["profile_hash"],
        },
        threshold_probability={
            "value": uncertainty["threshold_probability"],
            "label": uncertainty["probability_label"],
            "event": "daily_volatility_above_preregistered_ceiling",
            "ceiling_daily_pct": uncertainty["ceiling_daily_pct"],
        },
        calibration={
            "status": uncertainty["calibration_status"],
            "brier_score": uncertainty["calibration_brier_score"],
            "event_count": uncertainty["calibration_event_count"],
            "evaluation_report_hash": manifest.evaluation_report_hash,
            "profile_hash": uncertainty["profile_hash"],
        },
        frozen_baselines={
            "trailing_daily_pct": round(float(trailing), 6),
            "ewma_daily_pct": round(float(ewma), 6),
        },
        feature_observations=tuple(
            {
                "name": name,
                "value": numeric_values[name],
                "available_at": decision_cutoff,
                "age_sessions": 0,
                "missing": False,
            }
            for name in ordered
        ),
        reference_distribution={
            "status": "available",
            "identity_hash": reference_hash,
            "artifact_hash": manifest.artifact_hash,
            "features": reference,
        },
        regime_category=regime_category,
        event_category=event_category,
        lineage=_prospective_lineage(
            config=config,
            manifest=manifest,
            evidence_epoch=evidence_epoch,
            shadow_run_id=shadow_run_id,
            feature_snapshot_hash=feature_snapshot_hash,
        ),
        available=True,
    )
    record = PredictionRecord(
        prediction_id=prediction_id,
        model_id=manifest.model_id,
        model_version=manifest.model_version,
        artifact_hash=manifest.artifact_hash,
        dataset_or_feature_snapshot_hash=feature_snapshot_hash,
        task=config.task,
        subject_key=subject,
        as_of_session=as_of_session,
        generated_at=generated_at,
        horizon_sessions=config.horizon_sessions,
        target_available_at=target_available_at,
        values={
            "daily_volatility_pct": round(daily_volatility, 6),
            "annualized_volatility_pct": round(annualize_pct(daily_volatility), 6),
            "trailing_baseline_daily_pct": round(float(trailing), 6),
            "ewma_baseline_daily_pct": round(float(ewma), 6),
            "prediction_interval_daily_pct": uncertainty[
                "prediction_interval_daily_pct"
            ],
            uncertainty["probability_label"]: uncertainty[
                "threshold_probability"
            ],
            "mandate_ceiling_daily_pct": uncertainty["ceiling_daily_pct"],
        },
        uncertainty={
            "status": "available",
            "evaluation_report_hash": manifest.evaluation_report_hash,
            "prospective_profile_hash": uncertainty["profile_hash"],
            "calibration_status": uncertainty["calibration_status"],
        },
        data_available_at=decision_cutoff,
        feature_freshness={"missing_count": 0, "stale_count": 0, "maximum_age_sessions": 0},
        available=True,
        refusal_reasons=(),
        evidence_status=manifest.evidence_status,
        monitoring_features=numeric_values,
        monitoring_context={
            "event_category": event_category,
            "regime_category": regime_category,
            "regime_feature": regime_feature,
            "reference_distribution_hash": reference_hash,
        },
        prospective_contract=prospective.to_dict(),
    ).to_shadow_storage_dict()
    record["evidence_epoch"] = evidence_epoch
    record["shadow_run_id"] = shadow_run_id
    return record


def build_volatility_outcome(
    config: ShadowRuntimeConfig,
    prediction: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    target_session: str,
    label_version: str,
) -> dict[str, Any]:
    """Build the exact forward realized-volatility label for one prediction."""
    if not prediction.get("available"):
        raise ShadowRuntimeError("an unavailable prediction cannot produce an outcome")
    as_of_session = str(prediction.get("as_of_session"))
    horizon = prediction.get("horizon_sessions")
    if horizon != config.horizon_sessions:
        raise ShadowRuntimeError(
            f"prediction horizon {horizon!r} does not match config {config.horizon_sessions}"
        )
    expected_sessions = trading_sessions(
        date.fromisoformat(as_of_session), date.fromisoformat(target_session)
    )
    if (
        len(expected_sessions) != config.horizon_sessions + 1
        or expected_sessions[0].isoformat() != as_of_session
        or expected_sessions[-1].isoformat() != target_session
    ):
        raise ShadowRuntimeError("exchange-calendar target window is inconsistent")
    expected_index = pd.DatetimeIndex(expected_sessions)
    if "close" not in frame:
        raise ShadowProviderError("target bars are missing the close column")
    closes = pd.to_numeric(frame["close"], errors="coerce").reindex(expected_index)
    missing = [
        session.date().isoformat()
        for session, value in closes.items()
        if not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ]
    if missing:
        raise ShadowProviderError(
            f"target window is missing/non-positive close data for {missing[:5]}"
        )
    rows, dropped = compute_forward_realized_vol_labels(
        str(prediction["subject_key"]),
        closes,
        horizon_sessions=config.horizon_sessions,
        label_version=_required_text(label_version, "label_version"),
    )
    matching = [row for row in rows if row.as_of_session == as_of_session]
    if dropped != config.horizon_sessions or len(matching) != 1:
        # A window of horizon+1 sessions produces one complete label and
        # drops each later as-of row.  Anything else means label semantics
        # changed or the provider window was not what we verified above.
        raise ShadowRuntimeError(
            f"label builder produced matching={len(matching)}, dropped={dropped}; "
            "expected one exact target"
        )
    label = matching[0]
    return {
        "realized_daily_volatility_pct": label.value,
        "target_session": target_session,
        "entry_session": label.entry_session,
        "exit_session": label.exit_session,
        "label_version": label.label_version,
        "components": dict(label.components),
        "target_snapshot_hash": hash_payload(
            {
                "provider_id": config.provider_id,
                "subject": prediction["subject_key"],
                "sessions": [session.date().isoformat() for session in expected_index],
                "closes": [float(value) for value in closes],
            }
        ),
    }
