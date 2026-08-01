"""ML-LR-3 section 9.7: the portfolio-target experiment runner.

Plan 9.4 requires "portfolio and per-security results separately", and 9.7's
definition of done names BOTH runners. This is the portfolio half.

Two things make this a different runner rather than a parameter on the
per-security one:

  1. the observation unit is an ACCOUNT-SESSION, not a (session, ticker)
     pair, so there is no cross-sectional dimension to slice by ticker; and
  2. the target has to be BUILT from position/equity records first, and that
     construction can legitimately refuse -- a session whose holdings lack
     forward prices, or whose external flows are unrecorded, produces no
     observation at all rather than a degraded one.

Underfill is a first-class outcome (plan 9.7): "Real portfolio research may
remain underfilled until enough daily position/equity snapshots have
accumulated; report this as unavailable rather than backfilling guessed
holdings." `build_portfolio_target_series()` therefore returns the refusals
alongside the targets, and `assess_portfolio_research_readiness()` reports
that the research cannot yet run rather than running it on three points.

This module takes ALREADY-LOADED records, like ml/portfolio_volatility.py.
It imports no broker, no execution service, and no storage class -- a caller
passes in what `AssistantStore.list_portfolio_position_snapshots()` and
`.list_portfolio_equity_snapshots()` returned.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.portfolio_volatility import (
    PortfolioVolatilityError,
    PortfolioVolatilityTarget,
    build_frozen_weight_targets,
    build_realized_account_targets,
)

# A volatility experiment needs enough account-sessions to support purged
# walk-forward folds with an embargo. Below this the honest answer is "not
# yet", not a number.
MIN_TARGETS_FOR_RESEARCH = 60


class PortfolioExperimentError(ValueError):
    """Portfolio records cannot support an experiment."""


def _canonical_session(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise PortfolioExperimentError(f"{name} must use canonical YYYY-MM-DD format")
    parsed = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != value:
        raise PortfolioExperimentError(f"{name} must use canonical YYYY-MM-DD format")
    return value


def _capture_instant(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioExperimentError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioExperimentError(
            f"{name} must be a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortfolioExperimentError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclasses.dataclass(frozen=True)
class TargetBuildResult:
    """Targets plus the sessions that refused, and why.

    Refusals are returned rather than logged and dropped: a run that
    silently produced 12 targets from 200 sessions looks identical to one
    that produced 12 from 12, and only the second is trustworthy.
    """

    targets: tuple[PortfolioVolatilityTarget, ...]
    refusals: tuple[Mapping[str, str], ...]

    @property
    def attempted_session_count(self) -> int:
        return len(self.targets) + len(self.refusals)

    @property
    def refusal_rate(self) -> float | None:
        if not self.attempted_session_count:
            return None
        return round(len(self.refusals) / self.attempted_session_count, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_count": len(self.targets),
            "refusal_count": len(self.refusals),
            "attempted_session_count": self.attempted_session_count,
            "refusal_rate": self.refusal_rate,
            "refusal_reason_counts": _count_reasons(self.refusals),
            "refusals": [dict(refusal) for refusal in self.refusals],
            "targets": [t.to_dict() for t in self.targets],
        }


def _count_reasons(refusals: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for refusal in refusals:
        # Bucket by the leading clause so a hundred distinct ticker names do
        # not become a hundred distinct "reasons".
        reason = str(refusal.get("reason", "")).split(":")[0].split(";")[0].strip()
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def group_position_snapshots_by_session(
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Group `AssistantStore.list_portfolio_position_snapshots()` rows by
    session, keeping the latest coherent capture cohort.

    Multiple captures of the same session are legitimate -- the briefing may
    run more than once a day. Taking the latest is right for a
    frozen-weight target because the forecast cutoff check downstream is
    what enforces that it was still knowable in time; taking the earliest
    would silently use a stale intraday snapshot.
    """
    cohorts: dict[tuple[str, datetime], dict[str, Mapping[str, Any]]] = {}
    for row in snapshots:
        for field in ("session_date", "ticker", "captured_at", "market_value"):
            if field not in row:
                raise PortfolioExperimentError(
                    f"position snapshot is missing {field!r}"
                )
        session = _canonical_session(row["session_date"], "position session_date")
        captured = _capture_instant(row["captured_at"], "position captured_at")
        ticker = row["ticker"]
        if not isinstance(ticker, str) or ticker != ticker.upper() or not ticker.strip():
            raise PortfolioExperimentError(
                "position snapshot ticker must be canonical uppercase"
            )
        cohort = cohorts.setdefault((session, captured), {})
        if ticker in cohort:
            raise PortfolioExperimentError(
                f"duplicate position snapshot for {session}/{ticker}/{captured.isoformat()}"
            )
        cohort[ticker] = row

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    sessions = sorted({session for session, _captured in cohorts})
    for session in sessions:
        captures = sorted(
            (captured, rows)
            for (cohort_session, captured), rows in cohorts.items()
            if cohort_session == session
        )
        _latest_captured, latest_rows = captures[-1]
        latest_tickers = set(latest_rows)
        if any(set(rows) != latest_tickers for _captured, rows in captures[:-1]):
            raise PortfolioExperimentError(
                f"position captures for {session} disagree on ticker membership; "
                "without a snapshot-set identity the latest capture cannot be proven complete"
            )
        grouped[session] = [latest_rows[ticker] for ticker in sorted(latest_rows)]
    return grouped


def build_portfolio_target_series(
    account_key: str,
    *,
    positions_by_session: Mapping[str, Sequence[Mapping[str, Any]]],
    cash_by_session: Mapping[str, Any],
    close_by_ticker: Mapping[str, pd.Series],
    forecast_cutoff_by_session: Mapping[str, str],
    horizon_sessions: int = 20,
) -> TargetBuildResult:
    """One frozen-weight target per session, with per-session refusals kept.

    A session that cannot produce an honest target is recorded as a refusal
    and excluded -- never approximated. The refusal reasons come straight
    from ml/portfolio_volatility.py, so the "why" is the same one that
    module already documents.
    """
    targets: list[PortfolioVolatilityTarget] = []
    refusals: list[dict[str, str]] = []

    for session in sorted(positions_by_session):
        snapshots = positions_by_session[session]
        if session not in cash_by_session:
            refusals.append(
                {"as_of_session": session, "reason": "cash balance unrecorded"}
            )
            continue
        if session not in forecast_cutoff_by_session:
            refusals.append(
                {"as_of_session": session, "reason": "forecast cutoff unrecorded"}
            )
            continue
        try:
            _canonical_session(session, "positions_by_session key")
            if not snapshots:
                raise PortfolioExperimentError("position snapshot cohort is empty")
            if any(not isinstance(row, Mapping) for row in snapshots):
                raise PortfolioExperimentError(
                    "position snapshot cohort must contain mapping records"
                )
            missing_fields = sorted(
                {
                    field
                    for row in snapshots
                    for field in ("ticker", "market_value", "captured_at")
                    if field not in row
                }
            )
            if missing_fields:
                raise PortfolioExperimentError(
                    f"position snapshot cohort is missing fields: {missing_fields}"
                )
            capture_instants = {
                _capture_instant(row["captured_at"], "position captured_at")
                for row in snapshots
            }
            if len(capture_instants) != 1:
                raise PortfolioExperimentError(
                    "position snapshot cohort mixes capture timestamps; refusing a "
                    "portfolio that may never have existed"
                )
            captured = next(iter(capture_instants)).isoformat()
            targets.append(
                build_frozen_weight_targets(
                    account_key,
                    as_of_session=session,
                    captured_at=captured,
                    forecast_cutoff=forecast_cutoff_by_session[session],
                    snapshots=[
                        {"ticker": row["ticker"], "market_value": row["market_value"]}
                        for row in snapshots
                    ],
                    cash=cash_by_session[session],
                    close_by_ticker=close_by_ticker,
                    horizon_sessions=horizon_sessions,
                )
            )
        except (PortfolioExperimentError, PortfolioVolatilityError, ValueError) as exc:
            refusals.append({"as_of_session": session, "reason": str(exc)})

    return TargetBuildResult(targets=tuple(targets), refusals=tuple(refusals))


def build_realized_account_target_series(
    account_key: str,
    *,
    equity_by_session: Mapping[str, Any],
    net_external_flow_by_session: Mapping[str, Any],
    horizon_sessions: int = 20,
) -> TargetBuildResult:
    """The realized-account counterpart. Kept separate from the frozen-weight
    series for the same reason the underlying builders are separate: the two
    measure different quantities and must never be pooled."""
    targets: list[PortfolioVolatilityTarget] = []
    refusals: list[dict[str, str]] = []
    for session in sorted(equity_by_session):
        try:
            targets.append(
                build_realized_account_targets(
                    account_key,
                    as_of_session=session,
                    equity_by_session=equity_by_session,
                    net_external_flow_by_session=net_external_flow_by_session,
                    horizon_sessions=horizon_sessions,
                )
            )
        except (PortfolioVolatilityError, ValueError) as exc:
            refusals.append({"as_of_session": session, "reason": str(exc)})
    return TargetBuildResult(targets=tuple(targets), refusals=tuple(refusals))


def targets_to_frame(targets: Sequence[PortfolioVolatilityTarget]) -> pd.DataFrame:
    """Flatten targets into a deterministic account-session research frame.

    `ticker` is the literal account key rather than a security: the
    observation unit here is an account-session. Naming it honestly keeps
    the ranker's cross-sectional metrics from being applied to a panel that
    has exactly one name per date, where a rank correlation is undefined.
    """
    if not targets:
        return pd.DataFrame(
            columns=[
                "as_of_session", "ticker", "target_kind", "label_value",
                "cash_weight", "position_snapshot_hash", "price_input_hash",
                "exit_session",
            ]
        )
    kinds = {t.target_kind for t in targets}
    if len(kinds) > 1:
        raise PortfolioExperimentError(
            f"refusing to pool different target kinds into one frame: {sorted(kinds)}"
        )
    rows = [
        {
            "as_of_session": t.as_of_session,
            "ticker": t.account_key,
            "target_kind": t.target_kind,
            "label_value": t.daily_volatility_pct,
            "cash_weight": t.cash_weight,
            "position_snapshot_hash": t.position_snapshot_hash,
            "price_input_hash": t.price_input_hash,
            # The label's outcome is realized on its last return session --
            # this is what ml/splits.py purges against.
            "exit_session": t.last_return_session,
        }
        for t in targets
    ]
    return pd.DataFrame(rows).sort_values(["as_of_session", "ticker"]).reset_index(
        drop=True
    )


def assess_portfolio_research_readiness(
    result: TargetBuildResult,
    *,
    minimum_targets: int = MIN_TARGETS_FOR_RESEARCH,
    n_splits: int = 2,
    embargo_sessions: int = 20,
) -> dict[str, Any]:
    """Report whether portfolio research can honestly run yet (plan 9.7).

    Returns a report rather than raising, so a caller can SHOW the user why
    the portfolio forecaster is unavailable -- "42 of the 60 sessions needed"
    is actionable; a silent absence is not.

    The purged-fold arithmetic is included because target count alone is
    misleading: with a 20-session horizon and a 20-session embargo, a large
    fraction of every training fold is purged away, so the usable sample is
    materially smaller than the raw count suggests.
    """
    if (
        isinstance(minimum_targets, bool)
        or not isinstance(minimum_targets, int)
        or minimum_targets < 1
    ):
        raise PortfolioExperimentError("minimum_targets must be a positive integer")
    if isinstance(n_splits, bool) or not isinstance(n_splits, int) or n_splits < 2:
        raise PortfolioExperimentError("n_splits must be an integer >= 2")
    if (
        isinstance(embargo_sessions, bool)
        or not isinstance(embargo_sessions, int)
        or embargo_sessions < 0
    ):
        raise PortfolioExperimentError("embargo_sessions must be a non-negative integer")

    target_count = len(result.targets)
    horizons = {target.horizon_sessions for target in result.targets}
    if len(horizons) > 1:
        raise PortfolioExperimentError(
            "readiness cannot pool portfolio targets with different horizons"
        )
    if horizons and embargo_sessions < next(iter(horizons)):
        raise PortfolioExperimentError(
            "embargo_sessions must be at least the portfolio target horizon"
        )
    # Each fold needs at least the embargo plus horizon of separation; this
    # is a floor, not a guarantee of statistical power.
    required_for_folds = (n_splits + 1) * (embargo_sessions + 1)
    blockers: list[str] = []
    if target_count < minimum_targets:
        blockers.append(
            f"only {target_count} portfolio targets; {minimum_targets} required"
        )
    if target_count < required_for_folds:
        blockers.append(
            f"only {target_count} targets; {required_for_folds} needed for "
            f"{n_splits} purged folds with a {embargo_sessions}-session embargo"
        )
    return {
        "ready": not blockers,
        "target_count": target_count,
        "attempted_session_count": result.attempted_session_count,
        "refusal_count": len(result.refusals),
        "refusal_rate": result.refusal_rate,
        "refusal_reason_counts": _count_reasons(result.refusals),
        "minimum_targets": minimum_targets,
        "targets_needed_for_folds": required_for_folds,
        "blockers": tuple(blockers),
        "status": "ready" if not blockers else "underfilled",
        "note": (
            "Portfolio research is reported as unavailable rather than run on an "
            "inadequate sample or backfilled with guessed holdings (plan 9.7)."
        ),
    }


def summarize_portfolio_targets(
    result: TargetBuildResult,
) -> dict[str, Any]:
    """Descriptive summary of the target series itself.

    Deliberately descriptive only -- no model, no baseline comparison, no
    verdict. Those belong to the shared runner once the sample is adequate.
    """
    if not result.targets:
        return {
            "available": False,
            "reason": "no portfolio targets could be built",
            "refusal_reason_counts": _count_reasons(result.refusals),
        }
    values = np.array([t.daily_volatility_pct for t in result.targets], dtype=float)
    cash = np.array([t.cash_weight for t in result.targets], dtype=float)
    sessions = [t.as_of_session for t in result.targets]
    return {
        "available": True,
        "target_kind": result.targets[0].target_kind,
        "target_count": len(values),
        "first_session": min(sessions),
        "last_session": max(sessions),
        "daily_volatility_pct": {
            "mean": round(float(values.mean()), 6),
            "median": round(float(np.median(values)), 6),
            "min": round(float(values.min()), 6),
            "max": round(float(values.max()), 6),
        },
        "cash_weight": {
            "mean": round(float(cash.mean()), 6),
            "max": round(float(cash.max()), 6),
        },
        "refusal_rate": result.refusal_rate,
        "units": (
            "daily_volatility_pct is a daily-return standard deviation in percent; "
            "annualize only via an explicitly named field (plan 9.3)"
        ),
    }
