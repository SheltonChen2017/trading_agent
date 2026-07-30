"""Machine-readable portfolio mandate and fail-closed promotion gates.

The mandate defines what a strategy must achieve. TradingPolicy defines what
an individual order is allowed to do. Keeping those concerns separate avoids
turning a promising backtest into execution authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

DEFAULT_MANDATE_PATH = Path(__file__).resolve().parent / "default_mandate.json"


@dataclasses.dataclass(frozen=True)
class PortfolioMandate:
    version: str
    name: str
    status: Literal["proposed", "approved", "retired"] = "proposed"
    approved_at: str | None = None
    approved_by: str | None = None
    approved_fingerprint: str | None = None
    target_annualized_volatility_min_pct: float = 12.0
    target_annualized_volatility_max_pct: float = 18.0
    max_drawdown_pct: float = 25.0
    max_time_under_water_sessions: int = 180
    max_downside_capture_pct: float = 70.0
    min_upside_capture_pct: float = 70.0
    min_paper_sessions: int = 60
    min_paper_orders: int = 30
    max_unreconciled_items: int = 0
    max_critical_alerts: int = 0
    require_reproduced_research: bool = True
    require_point_in_time_data: bool = True
    require_backup_restore_drill: bool = True
    permitted_instruments: tuple[str, ...] = ("equity", "etf")
    allow_autonomous_execution: bool = False
    notes: str = ""

    def validate(self) -> None:
        if not self.version.strip() or not self.name.strip():
            raise ValueError("mandate version and name must be non-empty")
        if self.status not in ("proposed", "approved", "retired"):
            raise ValueError(f"unsupported mandate status: {self.status!r}")

        percentages = (
            "target_annualized_volatility_min_pct",
            "target_annualized_volatility_max_pct",
            "max_drawdown_pct",
            "max_downside_capture_pct",
            "min_upside_capture_pct",
        )
        for field_name in percentages:
            value = getattr(self, field_name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative finite number")
        if (
            self.target_annualized_volatility_min_pct
            > self.target_annualized_volatility_max_pct
        ):
            raise ValueError("minimum target volatility cannot exceed maximum")

        for field_name in (
            "max_time_under_water_sessions",
            "min_paper_sessions",
            "min_paper_orders",
            "max_unreconciled_items",
            "max_critical_alerts",
        ):
            value = getattr(self, field_name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer")

        for field_name in (
            "require_reproduced_research",
            "require_point_in_time_data",
            "require_backup_restore_drill",
            "allow_autonomous_execution",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be a boolean")
        if not self.permitted_instruments or any(
            not isinstance(item, str) or not item.strip()
            for item in self.permitted_instruments
        ):
            raise ValueError("permitted_instruments must contain non-empty names")

        if self.status == "approved":
            if not self.approved_at or not self.approved_by:
                raise ValueError(
                    "an approved mandate requires approved_at and approved_by"
                )
            expected = compute_mandate_fingerprint(self)
            if self.approved_fingerprint != expected:
                raise ValueError(
                    "approved_fingerprint does not match the mandate's behavior fields"
                )

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["permitted_instruments"] = list(self.permitted_instruments)
        return result


_APPROVAL_METADATA_FIELDS = {
    "status",
    "approved_at",
    "approved_by",
    "approved_fingerprint",
    "notes",
}


def compute_mandate_fingerprint(mandate: PortfolioMandate) -> str:
    payload = {
        key: value
        for key, value in mandate.to_dict().items()
        if key not in _APPROVAL_METADATA_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_mandate(path: str | Path = DEFAULT_MANDATE_PATH) -> PortfolioMandate:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw["permitted_instruments"] = tuple(raw.get("permitted_instruments", ()))
    mandate = PortfolioMandate(**raw)
    mandate.validate()
    return mandate


def _metric_check(
    name: str,
    actual: Any,
    *,
    predicate,
    target: str,
) -> dict[str, Any]:
    if actual is None:
        return {
            "name": name,
            "passed": False,
            "available": False,
            "actual": None,
            "target": target,
            "detail": "metric unavailable",
        }
    try:
        value = float(actual)
    except (TypeError, ValueError):
        value = math.nan
    valid = math.isfinite(value)
    return {
        "name": name,
        "passed": bool(valid and predicate(value)),
        "available": valid,
        "actual": value if valid else None,
        "target": target,
        "detail": "evaluated" if valid else "metric is not finite",
    }


def evaluate_mandate_metrics(
    mandate: PortfolioMandate, metrics: dict[str, Any]
) -> dict[str, Any]:
    """Score deterministic portfolio metrics against the mandate."""
    checks = [
        _metric_check(
            "annualized_volatility_pct",
            metrics.get("annualized_volatility_pct"),
            predicate=lambda value: (
                mandate.target_annualized_volatility_min_pct
                <= value
                <= mandate.target_annualized_volatility_max_pct
            ),
            target=(
                f"{mandate.target_annualized_volatility_min_pct}%–"
                f"{mandate.target_annualized_volatility_max_pct}%"
            ),
        ),
        _metric_check(
            "max_drawdown_pct",
            metrics.get("max_drawdown_pct"),
            predicate=lambda value: (
                value <= 0 and abs(value) <= mandate.max_drawdown_pct
            ),
            target=f"no worse than -{mandate.max_drawdown_pct}%",
        ),
        _metric_check(
            "max_time_under_water_sessions",
            metrics.get("max_time_under_water_sessions"),
            predicate=lambda value: value <= mandate.max_time_under_water_sessions,
            target=f"≤ {mandate.max_time_under_water_sessions}",
        ),
        _metric_check(
            "downside_capture_pct",
            metrics.get("downside_capture_pct"),
            predicate=lambda value: value <= mandate.max_downside_capture_pct,
            target=f"≤ {mandate.max_downside_capture_pct}%",
        ),
        _metric_check(
            "upside_capture_pct",
            metrics.get("upside_capture_pct"),
            predicate=lambda value: value >= mandate.min_upside_capture_pct,
            target=f"≥ {mandate.min_upside_capture_pct}%",
        ),
    ]
    return {
        "passed": all(check["passed"] for check in checks),
        "mandate_version": mandate.version,
        "mandate_fingerprint": compute_mandate_fingerprint(mandate),
        "checks": checks,
    }


def evaluate_live_promotion(
    mandate: PortfolioMandate,
    *,
    metric_report: dict[str, Any],
    paper_sessions: int,
    paper_orders: int,
    unreconciled_items: int,
    critical_alerts: int,
    research_reproduced: bool,
    point_in_time_data: bool,
    backup_restore_drill_passed: bool,
    operational_health_passed: bool,
    paper_evidence_integrity_passed: bool,
    operational_drills_passed: bool,
) -> dict[str, Any]:
    """Fail-closed evidence gate. This does not enable live trading."""
    mandate.validate()
    metric_evaluation = evaluate_mandate_metrics(mandate, metric_report)
    checks = [
        {
            "name": "owner_approved_mandate",
            "passed": mandate.status == "approved",
            "detail": f"status={mandate.status}",
        },
        {
            "name": "mandate_metrics",
            "passed": metric_evaluation["passed"],
            "detail": "all risk-shape targets pass",
        },
        {
            "name": "paper_sessions",
            "passed": paper_sessions >= mandate.min_paper_sessions,
            "detail": f"{paper_sessions}/{mandate.min_paper_sessions}",
        },
        {
            "name": "paper_orders",
            "passed": paper_orders >= mandate.min_paper_orders,
            "detail": f"{paper_orders}/{mandate.min_paper_orders}",
        },
        {
            "name": "ledger_reconciliation",
            "passed": unreconciled_items <= mandate.max_unreconciled_items,
            "detail": (
                f"{unreconciled_items} unresolved; "
                f"maximum={mandate.max_unreconciled_items}"
            ),
        },
        {
            "name": "critical_alerts",
            "passed": critical_alerts <= mandate.max_critical_alerts,
            "detail": f"{critical_alerts}; maximum={mandate.max_critical_alerts}",
        },
        {
            "name": "research_reproduced",
            "passed": (
                research_reproduced or not mandate.require_reproduced_research
            ),
            "detail": str(bool(research_reproduced)),
        },
        {
            "name": "point_in_time_data",
            "passed": point_in_time_data or not mandate.require_point_in_time_data,
            "detail": str(bool(point_in_time_data)),
        },
        {
            "name": "backup_restore_drill",
            "passed": (
                backup_restore_drill_passed
                or not mandate.require_backup_restore_drill
            ),
            "detail": str(bool(backup_restore_drill_passed)),
        },
        {
            "name": "operational_health",
            "passed": bool(operational_health_passed),
            "detail": str(bool(operational_health_passed)),
        },
        {
            "name": "paper_evidence_integrity",
            "passed": bool(paper_evidence_integrity_passed),
            "detail": str(bool(paper_evidence_integrity_passed)),
        },
        {
            "name": "operational_drills",
            "passed": bool(operational_drills_passed),
            "detail": str(bool(operational_drills_passed)),
        },
        {
            "name": "manual_execution_only",
            "passed": not mandate.allow_autonomous_execution,
            "detail": (
                "manual approval remains required"
                if not mandate.allow_autonomous_execution
                else "autonomous execution requested"
            ),
        },
    ]
    return {
        "ready_for_live_canary_review": all(check["passed"] for check in checks),
        "does_not_enable_live_trading": True,
        "mandate_version": mandate.version,
        "mandate_fingerprint": compute_mandate_fingerprint(mandate),
        "checks": checks,
        "metric_evaluation": metric_evaluation,
    }
