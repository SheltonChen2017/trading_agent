"""Immutable paper-trading evidence, daily NAV, and operational drills."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from assistant.money import decimal_text, to_decimal
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
    broker_account_id: str,
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
        "broker_account_id": _required_text(
            broker_account_id, "broker_account_id"
        ),
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
        "broker_account_id",
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
    if snapshot.source == "alpaca" and not snapshot.account_id:
        raise PaperEvidenceError(
            "Paper evidence requires the connected broker account ID"
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
    # The exact fields are what actually gets persisted, so they are
    # validated rather than trusted: a malformed decimal string would
    # otherwise reach immutable evidence unchecked.
    for field, accessor in (
        ("cash", lambda: snapshot.cash_exact_decimal),
        ("total_equity", lambda: snapshot.total_equity_exact_decimal),
        ("buying_power", lambda: snapshot.buying_power_exact_decimal),
    ):
        try:
            exact = accessor()
        except ValueError as exc:
            raise PaperEvidenceError(
                f"snapshot.{field} exact value is not a finite decimal: {exc}"
            ) from exc
        if exact is not None and not exact.is_finite():
            raise PaperEvidenceError(f"snapshot.{field} must be finite")
    if snapshot.total_equity <= 0:
        raise PaperEvidenceError("snapshot.total_equity must be positive")
    if snapshot.total_equity_exact_decimal <= 0:
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
            try:
                exact = position.exact_field(field)
            except ValueError as exc:
                raise PaperEvidenceError(
                    f"{ticker}.{field} exact value is not a finite decimal: {exc}"
                ) from exc
            if not exact.is_finite():
                raise PaperEvidenceError(f"{ticker}.{field} must be finite")


def _net_external_flow(
    store: AssistantStore,
    *,
    after: datetime,
    through: datetime,
) -> Decimal:
    """Sum external cash transfers exactly.

    Accumulating in ``float`` here silently corrupted the result: four exact
    cent-denominated postings summing to 10000.30 accumulated to
    10000.300000000001, and the normalized portfolio tables then stored that
    error as though it were the broker's decimal value. The error also flows
    into the external-flow-adjusted return series, so it compounds across
    sessions rather than cancelling.
    """
    flow = Decimal("0")
    for posting in store.list_journal_postings():
        if (
            posting["source"] != "cash_transfer"
            or posting["account"] != ACCOUNT_CASH
        ):
            continue
        occurred_at = _parse_at(posting["occurred_at"], "posting.occurred_at")
        if after < occurred_at <= through:
            flow += to_decimal(posting["amount"], name="posting.amount")
    return flow


def _persist_normalized_portfolio_capture(
    store: AssistantStore,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Derive the ML portfolio history from the immutable paper observation.

    A retry may arrive with a different current broker snapshot after the paper
    observation for that session was already committed. Normalizing the stored
    observation, rather than the retrying caller's snapshot, prevents that
    mutable input from rewriting the historical portfolio.
    """
    source = _required_text(observation.get("source"), "observation.source")
    account_mode = _required_text(
        observation.get("account_mode"), "observation.account_mode"
    )
    if account_mode != "paper":
        raise PaperEvidenceError(
            "Normalized paper portfolio capture requires account_mode=paper"
        )
    account_id = _required_text(
        observation.get("account_id"), "observation.account_id"
    )
    account_key = f"{source}:{account_mode}:{account_id}"
    observation_id = _required_text(
        observation.get("observation_id"), "observation.observation_id"
    )
    observation_hash = _required_text(
        observation.get("payload_hash"), "observation.payload_hash"
    )
    evidence_epoch = _required_text(
        observation.get("evidence_epoch"), "observation.evidence_epoch"
    )
    lineage_hash = _required_text(
        observation.get("lineage_hash"), "observation.lineage_hash"
    )
    session_date = _required_text(
        observation.get("session_date"), "observation.session_date"
    )
    captured_at = _required_text(
        observation.get("captured_at"), "observation.captured_at"
    )
    capture_id = f"portfolio-{observation_id}"

    benchmark_ticker = _required_text(
        observation.get("benchmark_ticker"), "observation.benchmark_ticker"
    ).upper()
    equity = store.append_portfolio_equity_snapshot(
        {
            "schema_version": "1.1",
            "portfolio_capture_id": capture_id,
            "paper_observation_id": observation_id,
            "paper_observation_hash": observation_hash,
            "evidence_epoch": evidence_epoch,
            "lineage_hash": lineage_hash,
            "account_key": account_key,
            "session_date": session_date,
            "captured_at": captured_at,
            "source": source,
            "account_mode": account_mode,
            "account_id": account_id,
            "total_equity": decimal_text(
                to_decimal(observation.get("total_equity"), name="total_equity")
            ),
            "cash": decimal_text(to_decimal(observation.get("cash"), name="cash")),
            "net_external_flow": decimal_text(
                to_decimal(
                    observation.get("net_external_flow"),
                    name="net_external_flow",
                )
            ),
            "benchmarks": {
                benchmark_ticker: decimal_text(
                    to_decimal(
                        observation.get("benchmark_close"),
                        name="benchmark_close",
                    )
                )
            },
            "benchmark_basis": "recorded_post_close_session_value",
            "benchmark_unavailable": [],
        }
    )

    positions = observation.get("positions")
    if not isinstance(positions, list):
        raise PaperEvidenceError("observation.positions must be a list")
    if any(not isinstance(position, dict) for position in positions):
        raise PaperEvidenceError("observation position must be an object")
    normalized_positions: list[dict[str, Any]] = []
    for position in sorted(positions, key=lambda item: str(item.get("ticker", ""))):
        ticker = _required_text(position.get("ticker"), "position.ticker").upper()
        normalized_positions.append(
            {
                "account_key": account_key,
                "session_date": session_date,
                "captured_at": captured_at,
                "ticker": ticker,
                "shares": decimal_text(
                    to_decimal(position.get("shares"), name=f"{ticker}.shares")
                ),
                "market_value": decimal_text(
                    to_decimal(
                        position.get("market_value"),
                        name=f"{ticker}.market_value",
                    )
                ),
                "price": decimal_text(
                    to_decimal(
                        position.get("current_price"),
                        name=f"{ticker}.current_price",
                    )
                ),
                "source": source,
            }
        )
    written_positions = store.append_portfolio_position_snapshots(
        normalized_positions
    )
    manifest = store.append_portfolio_capture_session(
        {
            "schema_version": "1.0",
            "capture_id": capture_id,
            "observation_id": observation_id,
            "observation_payload_hash": observation_hash,
            "evidence_epoch": evidence_epoch,
            "lineage_hash": lineage_hash,
            "account_key": account_key,
            "account_mode": account_mode,
            "broker_account_id": account_id,
            "session_date": session_date,
            "captured_at": captured_at,
            "source": source,
            "equity_snapshot_id": equity["snapshot_id"],
            "equity_payload_hash": equity["payload_hash"],
            "position_snapshot_ids": [
                item["snapshot_id"] for item in written_positions
            ],
            "position_snapshot_hashes": [
                item["snapshot_hash"] for item in written_positions
            ],
            "position_count": len(written_positions),
        }
    )
    return manifest


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
    if snapshot.account_id != epoch["lineage"].get("broker_account_id"):
        raise PaperEvidenceError(
            "Connected broker account does not match the active evidence epoch"
        )
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
    reconciled_account_id = str(
        ((reconciliation.get("broker") or {}).get("account_id") or "")
    )
    if reconciled_account_id != snapshot.account_id:
        raise PaperEvidenceError(
            "The latest ledger reconciliation belongs to a different or "
            "unidentified broker account"
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
    net_external_flow = Decimal("0")
    if prior:
        previous_at = _parse_at(prior[-1]["captured_at"], "captured_at")
        if when < previous_at:
            raise PaperEvidenceError(
                "Paper observations must advance monotonically in time"
            )
        if prior[-1]["session_date"] == session_date:
            recorded = {
                **prior[-1],
                "already_recorded": True,
            }
            return {
                **recorded,
                "portfolio_capture": _persist_normalized_portfolio_capture(
                    store, recorded
                ),
            }
        if when > previous_at:
            net_external_flow = _net_external_flow(
                store, after=previous_at, through=when
            )

    observation = {
        # 1.2: every money and quantity field is exact decimal text taken
        # from the broker's own decimals, not a JSON float. Paper
        # observations are immutable, so precision discarded at write time
        # can never be reconstructed. `exact_numerics` records whether the
        # snapshot actually supplied preserved decimals, so a consumer can
        # tell exact capture from a rounded float that merely round-tripped
        # instead of having to assume.
        "schema_version": "1.2",
        "exact_numerics": snapshot.has_exact_numerics,
        "evidence_epoch": epoch["evidence_epoch"],
        "lineage_hash": epoch["lineage_hash"],
        "session_date": session_date,
        "captured_at": when.isoformat(),
        "market_close": market_close.isoformat(),
        "source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "account_id": snapshot.account_id,
        "cash": decimal_text(snapshot.cash_exact_decimal),
        "total_equity": decimal_text(snapshot.total_equity_exact_decimal),
        "buying_power": (
            None
            if snapshot.buying_power is None
            else decimal_text(snapshot.buying_power_exact_decimal)
        ),
        "benchmark_ticker": ticker,
        "benchmark_close": decimal_text(
            to_decimal(benchmark_close, name="benchmark_close")
        ),
        # Decimal text, not float: the normalized portfolio tables and the
        # flow-adjusted return series both re-read this field, and a float
        # here would hand them an already-corrupted value to preserve
        # "exactly". ml/portfolio_volatility.py already expects decimal text.
        "net_external_flow": decimal_text(net_external_flow),
        "positions": [
            {
                "ticker": position.ticker.upper(),
                "shares": decimal_text(position.exact_field("shares")),
                "entry_price": decimal_text(
                    position.exact_field("entry_price")
                ),
                "current_price": decimal_text(
                    position.exact_field("current_price")
                ),
                "market_value": decimal_text(
                    position.exact_field("market_value")
                ),
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
    recorded = store.append_paper_account_observation(observation)
    return {
        **recorded,
        "portfolio_capture": _persist_normalized_portfolio_capture(
            store, recorded
        ),
    }


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
