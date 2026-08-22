"""Machine-readable portfolio mandate and fail-closed promotion gates.

The mandate defines what a strategy must achieve. TradingPolicy defines what
an individual order is allowed to do. Keeping those concerns separate avoids
turning a promising backtest into execution authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from data.mandate_evaluation import (
    compute_mandate_fingerprint,
    evaluate_mandate_metrics,
)
from data.portfolio_mandate import PortfolioMandate, load_portfolio_mandate

DEFAULT_MANDATE_PATH = Path(__file__).resolve().parent / "default_mandate.json"


def load_mandate(path: str | Path = DEFAULT_MANDATE_PATH) -> PortfolioMandate:
    """Load the assistant-owned default through the neutral data contract."""
    return load_portfolio_mandate(path)


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
