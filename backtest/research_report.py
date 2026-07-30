"""Reproducible portfolio-research report and mandate scorecard."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from assistant.mandate import PortfolioMandate, evaluate_mandate_metrics
from backtest.risk_metrics import (
    downside_capture_pct,
    expected_shortfall_pct,
    max_drawdown_pct,
    time_under_water,
    upside_capture_pct,
)

TRADING_SESSIONS_PER_YEAR = 252
REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


class ResearchReportError(ValueError):
    """Research inputs cannot support a trustworthy report."""


def _series_digest(frame: pd.DataFrame) -> str:
    canonical = frame.sort_index().sort_index(axis=1).to_json(
        orient="split",
        date_format="iso",
        date_unit="ns",
        double_precision=15,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_data_manifest(
    data: dict[str, pd.DataFrame],
    *,
    requested_sessions: int | None = None,
    point_in_time: bool = False,
) -> dict[str, Any]:
    """Fingerprint every dataset and surface integrity/coverage weaknesses."""
    datasets: list[dict[str, Any]] = []
    all_issues: list[dict[str, str]] = []
    for raw_ticker in sorted(data):
        ticker = str(raw_ticker).upper()
        frame = data[raw_ticker]
        issues: list[str] = []
        if not isinstance(frame, pd.DataFrame):
            issues.append("not_a_dataframe")
            frame = pd.DataFrame()
        missing_columns = [
            column for column in REQUIRED_PRICE_COLUMNS if column not in frame
        ]
        if missing_columns:
            issues.append("missing_columns:" + ",".join(missing_columns))
        if frame.empty:
            issues.append("empty")
        if not frame.index.is_monotonic_increasing:
            issues.append("index_not_monotonic")
        if frame.index.has_duplicates:
            issues.append("duplicate_timestamps")

        available_price_columns = [
            column for column in REQUIRED_PRICE_COLUMNS if column in frame
        ]
        if available_price_columns and not frame.empty:
            numeric = frame[available_price_columns].apply(
                pd.to_numeric, errors="coerce"
            )
            if not np.isfinite(numeric.to_numpy(dtype=float)).all():
                issues.append("non_finite_values")
            price_columns = [
                column
                for column in ("open", "high", "low", "close")
                if column in numeric
            ]
            if price_columns and (numeric[price_columns] <= 0).any().any():
                issues.append("non_positive_price")
            if {"high", "low"}.issubset(numeric.columns) and (
                numeric["high"] < numeric["low"]
            ).any():
                issues.append("high_below_low")
            if {"open", "high", "low", "close"}.issubset(
                numeric.columns
            ):
                if (
                    numeric["high"]
                    < numeric[["open", "close"]].max(axis=1)
                ).any():
                    issues.append("high_below_open_or_close")
                if (
                    numeric["low"]
                    > numeric[["open", "close"]].min(axis=1)
                ).any():
                    issues.append("low_above_open_or_close")
            if "volume" in numeric and (numeric["volume"] < 0).any():
                issues.append("negative_volume")

        coverage_fraction = None
        if requested_sessions:
            coverage_fraction = len(frame) / requested_sessions
            if coverage_fraction < 0.9:
                issues.append("under_90pct_requested_history")
        for issue in issues:
            all_issues.append({"ticker": ticker, "issue": issue})
        datasets.append(
            {
                "ticker": ticker,
                "rows": len(frame),
                "start": (
                    str(frame.index.min()) if not frame.empty else None
                ),
                "end": str(frame.index.max()) if not frame.empty else None,
                "columns": sorted(str(column) for column in frame.columns),
                "sha256": _series_digest(frame),
                "coverage_fraction": (
                    round(coverage_fraction, 6)
                    if coverage_fraction is not None
                    else None
                ),
                "issues": issues,
            }
        )

    manifest_material = {
        "point_in_time": bool(point_in_time),
        "requested_sessions": requested_sessions,
        "pandas_version": pd.__version__,
        "datasets": datasets,
    }
    manifest_hash = hashlib.sha256(
        json.dumps(
            manifest_material, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        **manifest_material,
        "manifest_sha256": manifest_hash,
        "quality_passed": not all_issues and bool(datasets),
        "issues": all_issues,
    }


def embargoed_split_dates(
    dates: list[Any] | pd.Index,
    *,
    discovery_frac: float,
    embargo_sessions: int,
) -> dict[str, Any]:
    """Define a conservative symmetric embargo around a time split."""
    if (
        not isinstance(discovery_frac, (int, float))
        or isinstance(discovery_frac, bool)
        or not math.isfinite(discovery_frac)
        or not 0 < discovery_frac < 1
    ):
        raise ResearchReportError("discovery_frac must be between 0 and 1")
    if (
        not isinstance(embargo_sessions, int)
        or isinstance(embargo_sessions, bool)
        or embargo_sessions < 0
    ):
        raise ResearchReportError("embargo_sessions must be non-negative")
    ordered = sorted(set(dates))
    if len(ordered) < 2 + 2 * embargo_sessions:
        raise ResearchReportError("not enough dates for the requested embargo")
    split_index = min(
        len(ordered) - 1,
        max(1, int(len(ordered) * discovery_frac)),
    )
    discovery_end_index = split_index - embargo_sessions - 1
    confirmation_start_index = split_index + embargo_sessions
    if discovery_end_index < 0 or confirmation_start_index >= len(ordered):
        raise ResearchReportError("embargo leaves an empty research period")
    excluded = ordered[
        discovery_end_index + 1 : confirmation_start_index
    ]
    return {
        "discovery_end": str(ordered[discovery_end_index]),
        "confirmation_start": str(ordered[confirmation_start_index]),
        "embargo_sessions_each_side": embargo_sessions,
        "excluded_session_count": len(excluded),
        "excluded_start": str(excluded[0]) if excluded else None,
        "excluded_end": str(excluded[-1]) if excluded else None,
    }


def compute_portfolio_metrics(
    equity_curve: pd.Series, benchmark_close: pd.Series
) -> dict[str, Any]:
    if not isinstance(equity_curve, pd.Series) or len(equity_curve) < 2:
        raise ResearchReportError("equity_curve needs at least two observations")
    if not isinstance(benchmark_close, pd.Series) or len(benchmark_close) < 2:
        raise ResearchReportError(
            "benchmark_close needs at least two observations"
        )
    if equity_curve.index.has_duplicates or benchmark_close.index.has_duplicates:
        raise ResearchReportError("metric inputs cannot have duplicate timestamps")
    equity = pd.to_numeric(equity_curve.sort_index(), errors="coerce")
    benchmark = pd.to_numeric(benchmark_close.sort_index(), errors="coerce")
    if (
        not np.isfinite(equity.to_numpy(dtype=float)).all()
        or (equity <= 0).any()
    ):
        raise ResearchReportError("equity_curve must be positive and finite")

    common = equity.index.intersection(benchmark.index)
    if len(common) < 2:
        raise ResearchReportError(
            "equity curve and benchmark have insufficient overlap"
        )
    equity = equity.reindex(common)
    benchmark = benchmark.reindex(common)
    strategy_returns_fraction = equity.pct_change().dropna()
    benchmark_returns_fraction = benchmark.pct_change().dropna()
    aligned = strategy_returns_fraction.index.intersection(
        benchmark_returns_fraction.index
    )
    strategy_returns_pct = strategy_returns_fraction.reindex(aligned) * 100
    benchmark_returns_pct = benchmark_returns_fraction.reindex(aligned) * 100
    annualized_volatility = (
        float(strategy_returns_fraction.std(ddof=1))
        * math.sqrt(TRADING_SESSIONS_PER_YEAR)
        * 100
    )
    underwater = time_under_water(equity)
    return {
        "sessions": len(equity),
        "start": str(equity.index.min()),
        "end": str(equity.index.max()),
        "annualized_volatility_pct": round(annualized_volatility, 4),
        "max_drawdown_pct": round(max_drawdown_pct(equity), 4),
        "expected_shortfall_pct_95": round(
            expected_shortfall_pct(strategy_returns_pct, confidence=0.95), 4
        ),
        "max_time_under_water_sessions": underwater[
            "max_days_under_water"
        ],
        "current_time_under_water_sessions": underwater[
            "current_days_under_water"
        ],
        "pct_of_period_under_water": round(
            underwater["pct_of_period_under_water"], 4
        ),
        "downside_capture_pct": (
            None
            if (
                value := downside_capture_pct(
                    strategy_returns_pct, benchmark_returns_pct
                )
            )
            is None
            else round(value, 4)
        ),
        "upside_capture_pct": (
            None
            if (
                value := upside_capture_pct(
                    strategy_returns_pct, benchmark_returns_pct
                )
            )
            is None
            else round(value, 4)
        ),
    }


def build_research_report(
    *,
    strategy_name: str,
    equity_curve: pd.Series,
    benchmark_close: pd.Series,
    data: dict[str, pd.DataFrame],
    parameters: dict[str, Any],
    mandate: PortfolioMandate,
    code_commit: str,
    requested_sessions: int | None,
    point_in_time_data: bool,
    discovery_frac: float,
    hold_days: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not strategy_name.strip() or not code_commit.strip():
        raise ResearchReportError("strategy_name and code_commit are required")
    if not isinstance(hold_days, int) or isinstance(hold_days, bool) or hold_days < 1:
        raise ResearchReportError("hold_days must be a positive integer")
    manifest = build_data_manifest(
        data,
        requested_sessions=requested_sessions,
        point_in_time=point_in_time_data,
    )
    parameter_json = json.dumps(
        parameters, sort_keys=True, default=str, separators=(",", ":")
    )
    parameter_hash = hashlib.sha256(parameter_json.encode("utf-8")).hexdigest()
    split = embargoed_split_dates(
        equity_curve.index,
        discovery_frac=discovery_frac,
        embargo_sessions=hold_days,
    )
    discovery_end = pd.Timestamp(split["discovery_end"])
    confirmation_start = pd.Timestamp(split["confirmation_start"])
    discovery_curve = equity_curve[equity_curve.index <= discovery_end]
    confirmation_curve = equity_curve[
        equity_curve.index >= confirmation_start
    ]
    full_period_metrics = compute_portfolio_metrics(
        equity_curve, benchmark_close
    )
    discovery_metrics = compute_portfolio_metrics(
        discovery_curve, benchmark_close
    )
    confirmation_metrics = compute_portfolio_metrics(
        confirmation_curve, benchmark_close
    )
    mandate_evaluation = evaluate_mandate_metrics(
        mandate, confirmation_metrics
    )
    created = generated_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        raise ResearchReportError("generated_at must be timezone-aware")
    report = {
        "schema_version": "1.0",
        "generated_at": created.isoformat(),
        "strategy_name": strategy_name,
        "code_commit": code_commit,
        "parameters": parameters,
        "parameter_sha256": parameter_hash,
        "data_manifest": manifest,
        "research_protocol": {
            "entry_timing": parameters.get("entry_timing"),
            "hold_days": hold_days,
            "discovery_frac": discovery_frac,
            "split": split,
            "point_in_time_data": bool(point_in_time_data),
        },
        "metrics": confirmation_metrics,
        "discovery_metrics": discovery_metrics,
        "full_period_metrics": full_period_metrics,
        "mandate_evaluation": mandate_evaluation,
        "promotion_blockers": [
            blocker
            for blocker, condition in (
                ("data_quality_failed", not manifest["quality_passed"]),
                ("not_point_in_time_data", not point_in_time_data),
                ("mandate_metrics_failed", not mandate_evaluation["passed"]),
            )
            if condition
        ],
    }
    report_hash_material = json.dumps(
        report, sort_keys=True, default=str, separators=(",", ":")
    )
    report["report_sha256"] = hashlib.sha256(
        report_hash_material.encode("utf-8")
    ).hexdigest()
    return report


def verify_research_report(report: dict[str, Any]) -> bool:
    expected = report.get("report_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    material = dict(report)
    material.pop("report_sha256", None)
    encoded = json.dumps(
        material, sort_keys=True, default=str, separators=(",", ":")
    )
    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return actual == expected


def write_research_report(
    report: dict[str, Any], destination: str | Path
) -> Path:
    target = Path(destination)
    if target.exists():
        raise FileExistsError(
            f"research reports are immutable; destination exists: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target
