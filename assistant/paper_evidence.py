"""Immutable paper-trading evidence, daily NAV, and operational drills."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from assistant.portfolio_ledger import ACCOUNT_CASH
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from backtest.research_report import compute_portfolio_metrics


_EASTERN = ZoneInfo("America/New_York")
_NYSE = mcal.get_calendar("NYSE")

REQUIRED_PROMOTION_DRILLS = (
    "kill_switch",
    "ambiguous_submission",
    "restart_recovery",
    "backup_restore",
    "alert_delivery",
)


class PaperEvidenceError(RuntimeError):
    """Paper evidence is missing, contradictory, or not safely attributable."""


def _parse_at(value: str | datetime, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PaperEvidenceError(
                f"{field} must be an ISO-8601 timestamp"
            ) from exc
    if parsed.tzinfo is None:
        raise PaperEvidenceError(f"{field} must be timezone-aware")
    return parsed


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperEvidenceError(f"{field} must be non-empty")
    return value.strip()


def build_paper_lineage(
    *,
    code_commit: str,
    mandate_fingerprint: str,
    policy_fingerprint: str,
    strategy_id: str,
    strategy_version: str,
    model_id: str,
) -> dict[str, str]:
    """Build the immutable identity shared by every observation in an epoch."""
    return {
        "code_commit": _required_text(code_commit, "code_commit"),
        "mandate_fingerprint": _required_text(
            mandate_fingerprint, "mandate_fingerprint"
        ),
        "policy_fingerprint": _required_text(
            policy_fingerprint, "policy_fingerprint"
        ),
        "strategy_id": _required_text(strategy_id, "strategy_id"),
        "strategy_version": _required_text(
            strategy_version, "strategy_version"
        ),
        "model_id": _required_text(model_id, "model_id"),
    }


def start_paper_evidence_epoch(
    store: AssistantStore,
    evidence_epoch: str,
    lineage: dict[str, str],
    *,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Start one evidence epoch whose lineage cannot change later."""
    epoch = _required_text(evidence_epoch, "evidence_epoch")
    expected_keys = {
        "code_commit",
        "mandate_fingerprint",
        "policy_fingerprint",
        "strategy_id",
        "strategy_version",
        "model_id",
    }
    if set(lineage) != expected_keys:
        raise PaperEvidenceError(
            "lineage must contain exactly: " + ", ".join(sorted(expected_keys))
        )
    normalized = build_paper_lineage(**lineage)
    when = _parse_at(
        started_at or datetime.now(timezone.utc), "started_at"
    ).astimezone(timezone.utc)
    return store.start_paper_evidence_epoch(
        epoch,
        started_at=when.isoformat(),
        lineage=normalized,
    )


def paper_session_schedule(
    captured_at: datetime,
) -> tuple[str, datetime] | None:
    """Return the NYSE session date and close for an instant, if applicable."""
    eastern_date = captured_at.astimezone(_EASTERN).date()
    schedule = _NYSE.schedule(
        start_date=eastern_date.isoformat(),
        end_date=eastern_date.isoformat(),
    )
    if schedule.empty:
        return None
    market_close = schedule.iloc[0]["market_close"].to_pydatetime()
    return eastern_date.isoformat(), market_close


def _validate_snapshot(snapshot: PortfolioSnapshot) -> None:
    if snapshot.account_mode != "paper":
        raise PaperEvidenceError(
            "Paper evidence can only be captured from an Alpaca paper account"
        )
    for field, value in (
        ("cash", snapshot.cash),
        ("total_equity", snapshot.total_equity),
    ):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise PaperEvidenceError(f"snapshot.{field} must be finite")
    if snapshot.total_equity <= 0:
        raise PaperEvidenceError("snapshot.total_equity must be positive")
    if snapshot.buying_power is not None and not math.isfinite(
        snapshot.buying_power
    ):
        raise PaperEvidenceError("snapshot.buying_power must be finite")
    seen: set[str] = set()
    for position in snapshot.positions:
        ticker = _required_text(position.ticker, "position.ticker").upper()
        if ticker in seen:
            raise PaperEvidenceError(
                f"snapshot contains duplicate position {ticker}"
            )
        seen.add(ticker)
        for field in (
            "shares",
            "entry_price",
            "current_price",
            "market_value",
        ):
            value = getattr(position, field)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise PaperEvidenceError(
                    f"{ticker}.{field} must be finite"
                )


def _net_external_flow(
    store: AssistantStore,
    *,
    after: datetime,
    through: datetime,
) -> float:
    flow = 0.0
    for posting in store.list_journal_postings():
        if (
            posting["source"] != "cash_transfer"
            or posting["account"] != ACCOUNT_CASH
        ):
            continue
        occurred_at = _parse_at(posting["occurred_at"], "posting.occurred_at")
        if after < occurred_at <= through:
            flow += float(posting["amount"])
    return flow


def capture_paper_account_observation(
    store: AssistantStore,
    snapshot: PortfolioSnapshot,
    *,
    benchmark_ticker: str,
    benchmark_close: float,
    captured_at: datetime | None = None,
    expected_lineage: dict[str, str] | None = None,
    max_reconciliation_age_minutes: float = 30.0,
) -> dict[str, Any]:
    """Capture one immutable, reconciled, post-close paper NAV observation."""
    epoch = store.get_active_paper_evidence_epoch()
    if epoch is None:
        raise PaperEvidenceError("No active paper evidence epoch")
    if expected_lineage is not None and epoch["lineage"] != expected_lineage:
        raise PaperEvidenceError(
            "Active evidence lineage differs from the current runtime"
        )
    _validate_snapshot(snapshot)
    when = _parse_at(
        captured_at or datetime.now(timezone.utc), "captured_at"
    ).astimezone(timezone.utc)
    session = paper_session_schedule(when)
    if session is None:
        eastern_date = when.astimezone(_EASTERN).date().isoformat()
        raise PaperEvidenceError(
            f"{eastern_date} is not an NYSE trading session"
        )
    session_date, market_close = session
    if when < market_close:
        raise PaperEvidenceError(
            f"Paper observation must be captured after the NYSE close "
            f"({market_close.isoformat()})"
        )
    ticker = _required_text(benchmark_ticker, "benchmark_ticker").upper()
    if (
        not isinstance(benchmark_close, (int, float))
        or isinstance(benchmark_close, bool)
        or not math.isfinite(benchmark_close)
        or benchmark_close <= 0
    ):
        raise PaperEvidenceError("benchmark_close must be positive and finite")
    if (
        not isinstance(max_reconciliation_age_minutes, (int, float))
        or isinstance(max_reconciliation_age_minutes, bool)
        or not math.isfinite(max_reconciliation_age_minutes)
        or max_reconciliation_age_minutes <= 0
    ):
        raise PaperEvidenceError(
            "max_reconciliation_age_minutes must be positive and finite"
        )

    reconciliation = store.get_latest_ledger_reconciliation()
    if not reconciliation or not reconciliation.get("matched"):
        raise PaperEvidenceError(
            "A matching ledger reconciliation is required before NAV capture"
        )
    reconciled_at = _parse_at(
        reconciliation.get("reconciled_at"), "reconciled_at"
    )
    age = when - reconciled_at
    if age < timedelta(0) or age > timedelta(
        minutes=max_reconciliation_age_minutes
    ):
        raise PaperEvidenceError(
            "The latest matching ledger reconciliation is not recent enough"
        )

    prior = store.list_paper_account_observations(epoch["evidence_epoch"])
    net_external_flow = 0.0
    if prior:
        previous_at = _parse_at(prior[-1]["captured_at"], "captured_at")
        if when < previous_at:
            raise PaperEvidenceError(
                "Paper observations must advance monotonically in time"
            )
        if prior[-1]["session_date"] == session_date:
            return {
                **prior[-1],
                "already_recorded": True,
            }
        if when > previous_at:
            net_external_flow = _net_external_flow(
                store, after=previous_at, through=when
            )

    observation = {
        "schema_version": "1.0",
        "evidence_epoch": epoch["evidence_epoch"],
        "lineage_hash": epoch["lineage_hash"],
        "session_date": session_date,
        "captured_at": when.isoformat(),
        "market_close": market_close.isoformat(),
        "source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "cash": float(snapshot.cash),
        "total_equity": float(snapshot.total_equity),
        "buying_power": (
            None
            if snapshot.buying_power is None
            else float(snapshot.buying_power)
        ),
        "benchmark_ticker": ticker,
        "benchmark_close": float(benchmark_close),
        "net_external_flow": net_external_flow,
        "positions": [
            {
                "ticker": position.ticker.upper(),
                "shares": float(position.shares),
                "entry_price": float(position.entry_price),
                "current_price": float(position.current_price),
                "market_value": float(position.market_value),
            }
            for position in sorted(
                snapshot.positions, key=lambda item: item.ticker.upper()
            )
        ],
        "ledger_reconciliation_id": reconciliation.get("reconciliation_id"),
        "ledger_reconciled_at": reconciled_at.isoformat(),
        "ledger_mismatch_count": int(
            reconciliation.get("mismatch_count", 0)
        ),
    }
    return store.append_paper_account_observation(observation)


def record_operational_drill(
    store: AssistantStore,
    *,
    drill_type: str,
    passed: bool,
    evidence: dict[str, Any],
    performed_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist a drill result bound to the active evidence epoch and commit."""
    normalized_type = _required_text(drill_type, "drill_type")
    if normalized_type not in REQUIRED_PROMOTION_DRILLS:
        raise PaperEvidenceError(
            f"Unsupported drill type {normalized_type!r}; expected one of "
            + ", ".join(REQUIRED_PROMOTION_DRILLS)
        )
    if not isinstance(passed, bool):
        raise PaperEvidenceError("passed must be boolean")
    if not isinstance(evidence, dict) or not evidence:
        raise PaperEvidenceError("drill evidence must be a non-empty object")
    _required_text(evidence.get("operator"), "evidence.operator")
    _required_text(evidence.get("artifact"), "evidence.artifact")
    when = _parse_at(
        performed_at or datetime.now(timezone.utc), "performed_at"
    ).astimezone(timezone.utc)
    epoch = store.get_active_paper_evidence_epoch()
    if epoch is None:
        raise PaperEvidenceError(
            "An active paper evidence epoch is required to record a drill"
        )
    return store.record_operational_drill(
        drill_type=normalized_type,
        performed_at=when.isoformat(),
        passed=passed,
        evidence_epoch=epoch["evidence_epoch"],
        code_commit=epoch["lineage"]["code_commit"],
        evidence=evidence,
    )


def _valid_sessions(start: str, end: str) -> list[str]:
    return [
        stamp.date().isoformat()
        for stamp in _NYSE.valid_days(start_date=start, end_date=end)
    ]


def _paper_order_summary(
    store: AssistantStore,
    *,
    started_at: datetime,
    through: datetime | None,
) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    order_ids: set[str] = set()
    for order in store.list_broker_orders(limit=1_000_000):
        submitted_at = _parse_at(order["submitted_at"], "submitted_at")
        if submitted_at < started_at or (
            through is not None and submitted_at > through
        ):
            continue
        order_id = str(order.get("order_id") or "")
        if not order_id or order_id in order_ids:
            continue
        order_ids.add(order_id)
        status = str(
            order.get("order_status") or order.get("status") or "unknown"
        )
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "definition": (
            "Distinct broker-observed paper order IDs submitted during the "
            "observed paper-session window, including accepted and terminal "
            "outcomes."
        ),
        "window_started_at": started_at.isoformat(),
        "window_ended_at": (
            through.isoformat() if through is not None else None
        ),
        "count": len(order_ids),
        "status_counts": dict(sorted(statuses.items())),
    }


def paper_evidence_summary(
    store: AssistantStore, evidence_epoch: str | None = None
) -> dict[str, Any]:
    """Derive paper sessions, TWR-adjusted metrics, orders, and drill evidence."""
    epoch = (
        store.get_paper_evidence_epoch(evidence_epoch)
        if evidence_epoch is not None
        else store.get_active_paper_evidence_epoch()
    )
    if epoch is None:
        raise PaperEvidenceError("Paper evidence epoch not found")
    observations = store.list_paper_account_observations(
        epoch["evidence_epoch"]
    )
    expected_sessions: list[str] = []
    missing_sessions: list[str] = []
    if observations:
        expected_sessions = _valid_sessions(
            observations[0]["session_date"],
            observations[-1]["session_date"],
        )
        observed_sessions = {
            observation["session_date"] for observation in observations
        }
        missing_sessions = [
            session
            for session in expected_sessions
            if session not in observed_sessions
        ]

    metrics: dict[str, Any] | None = None
    metric_error: str | None = None
    if len(observations) >= 2:
        adjusted_equity = [100_000.0]
        for previous, current in zip(observations, observations[1:]):
            previous_equity = float(previous["total_equity"])
            adjusted_current = float(current["total_equity"]) - float(
                current["net_external_flow"]
            )
            if previous_equity <= 0 or adjusted_current <= 0:
                metric_error = (
                    "External-flow-adjusted equity must remain positive"
                )
                break
            adjusted_equity.append(
                adjusted_equity[-1] * adjusted_current / previous_equity
            )
        if metric_error is None:
            index = pd.DatetimeIndex(
                [observation["session_date"] for observation in observations]
            )
            equity_series = pd.Series(adjusted_equity, index=index)
            benchmark_series = pd.Series(
                [
                    float(observation["benchmark_close"])
                    for observation in observations
                ],
                index=index,
            )
            try:
                metrics = compute_portfolio_metrics(
                    equity_series, benchmark_series
                )
            except Exception as exc:
                metric_error = str(exc)
    else:
        metric_error = "At least two paper observations are required"

    drills = store.list_operational_drills(
        evidence_epoch=epoch["evidence_epoch"], limit=1_000
    )
    latest_drills: dict[str, dict[str, Any]] = {}
    for drill in drills:
        latest_drills.setdefault(drill["drill_type"], drill)
    drill_status = {
        drill_type: {
            "passed": bool(
                latest_drills.get(drill_type, {}).get("passed", False)
            ),
            "latest": latest_drills.get(drill_type),
        }
        for drill_type in REQUIRED_PROMOTION_DRILLS
    }
    last_capture = (
        _parse_at(observations[-1]["captured_at"], "captured_at")
        if observations
        else None
    )
    epoch_started_at = _parse_at(epoch["started_at"], "started_at")
    order_window_start = epoch_started_at
    if observations:
        first_session_start = datetime.fromisoformat(
            observations[0]["session_date"]
        ).replace(tzinfo=_EASTERN)
        order_window_start = max(
            epoch_started_at,
            first_session_start.astimezone(timezone.utc),
        )
    order_summary = _paper_order_summary(
        store,
        started_at=order_window_start,
        through=last_capture,
    )
    lineage_consistent = all(
        observation.get("lineage_hash") == epoch["lineage_hash"]
        for observation in observations
    )
    return {
        "evidence_epoch": epoch["evidence_epoch"],
        "epoch_status": epoch["status"],
        "started_at": epoch["started_at"],
        "ended_at": epoch["ended_at"],
        "lineage": epoch["lineage"],
        "lineage_hash": epoch["lineage_hash"],
        "lineage_consistent": lineage_consistent,
        "paper_sessions": len(observations),
        "first_session": (
            observations[0]["session_date"] if observations else None
        ),
        "last_session": (
            observations[-1]["session_date"] if observations else None
        ),
        "expected_session_count": len(expected_sessions),
        "missing_sessions": missing_sessions,
        "coverage_complete": bool(observations) and not missing_sessions,
        "paper_orders": order_summary,
        "metrics": metrics,
        "metric_error": metric_error,
        "required_drills": drill_status,
        "all_required_drills_passed": all(
            item["passed"] for item in drill_status.values()
        ),
        "observation_hashes": [
            observation["payload_hash"] for observation in observations
        ],
    }
