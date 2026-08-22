"""Reproducible portfolio-research report and mandate scorecard."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.mandate_evaluation import (
    MandateMetricContract,
    evaluate_mandate_metrics,
)
from data.portfolio_metrics import (
    PortfolioMetricsError as ResearchReportError,
    compute_portfolio_metrics,
)

REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


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


def build_research_report(
    *,
    strategy_name: str,
    equity_curve: pd.Series,
    benchmark_close: pd.Series,
    data: dict[str, pd.DataFrame],
    parameters: dict[str, Any],
    mandate: MandateMetricContract,
    code_commit: str,
    requested_sessions: int | None,
    point_in_time_data: bool,
    discovery_frac: float,
    hold_days: int,
    generated_at: datetime | None = None,
    min_confirmation_sessions: int = 60,
) -> dict[str, Any]:
    """
    `min_confirmation_sessions` (default 60, mirroring
    PortfolioMandate.min_paper_sessions' existing precedent for "this
    project's own idea of a minimally meaningful duration") is a scoped,
    partial mitigation for a real gap -- independent review, 2026-07-30:
    compute_portfolio_metrics() only requires >=2 observations, and this
    pipeline runs no bootstrap/significance testing at all (unlike
    backtest/engine.py's out_of_sample_significance_by_block() toolkit for
    return-edge claims), so a confirmation window of just a few sessions
    could clear the mandate's fixed numeric thresholds by chance alone.
    This does not add statistical significance testing to risk-shape
    metrics -- that is a real design decision (which test, what block
    length for the equity curve's serial dependence) left for a future,
    deliberate round -- it only stops a too-short window from silently
    passing unnoticed.
    """
    if not strategy_name.strip() or not code_commit.strip():
        raise ResearchReportError("strategy_name and code_commit are required")
    if not isinstance(hold_days, int) or isinstance(hold_days, bool) or hold_days < 1:
        raise ResearchReportError("hold_days must be a positive integer")
    if (
        not isinstance(min_confirmation_sessions, int)
        or isinstance(min_confirmation_sessions, bool)
        or min_confirmation_sessions < 1
    ):
        raise ResearchReportError("min_confirmation_sessions must be a positive integer")
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
            "min_confirmation_sessions": min_confirmation_sessions,
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
                (
                    "confirmation_window_too_short",
                    confirmation_metrics["sessions"] < min_confirmation_sessions,
                ),
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
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    # Independent review, 2026-07-31: exists() + os.replace() is NOT
    # atomic -- os.replace() unconditionally overwrites its destination on
    # both POSIX and Windows, and two concurrent writers targeting the
    # same path can both pass the existence check before either writes,
    # silently replacing the first report's content under the same
    # "immutable" identifier with no exception. A uuid-suffixed temp name
    # (so concurrent writers never collide on the temp file itself) plus
    # os.link() as the actual publish step fixes both problems: os.link()
    # is an atomic, OS-level create-exclusive that fails with
    # FileExistsError if `target` already exists, and the destination is
    # only ever visible fully-written (linked to the already-complete
    # temp file's contents), never partial.
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(payload, encoding="utf-8")
    try:
        os.link(temp, target)
    except FileExistsError as exc:
        raise FileExistsError(
            f"research reports are immutable; destination exists: {target}"
        ) from exc
    finally:
        temp.unlink(missing_ok=True)
    return target
