"""Provider-neutral portfolio-mandate data contract.

The trading assistant owns mandate defaults, approval policy, persistence, and
promotion decisions. This module owns only the deterministic, serializable
contract and explicit-path loading needed by research and assistant callers.
"""
from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Literal

from data.mandate_evaluation import compute_mandate_fingerprint


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

        for field_name in (
            "target_annualized_volatility_min_pct",
            "target_annualized_volatility_max_pct",
            "max_drawdown_pct",
            "max_downside_capture_pct",
            "min_upside_capture_pct",
        ):
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
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
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


def load_portfolio_mandate(path: str | Path) -> PortfolioMandate:
    """Load and validate a mandate from an explicit caller-owned path."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw["permitted_instruments"] = tuple(raw.get("permitted_instruments", ()))
    mandate = PortfolioMandate(**raw)
    mandate.validate()
    return mandate
