"""Provider-neutral portfolio-mandate data contract.

The trading assistant owns mandate defaults, approval policy, persistence, and
promotion decisions. This module owns only the deterministic, serializable
contract and explicit-path loading needed by research and assistant callers.
"""
from __future__ import annotations

import dataclasses
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from data.mandate_evaluation import compute_mandate_fingerprint


def _reject_non_finite_json_constant(token: str) -> None:
    raise ValueError(f"Mandate contains non-finite JSON constant {token!r}.")


def _canonical_aware_iso_timestamp(value: Any, *, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be a canonical timezone-aware ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
        offset = parsed.utcoffset()
        parsed.astimezone(timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be a canonical timezone-aware ISO-8601 string"
        ) from exc
    if offset is None or parsed.isoformat() != value:
        raise ValueError(f"{name} must be a canonical timezone-aware ISO-8601 string")
    return value


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
        if any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            for value in (self.version, self.name)
        ):
            raise ValueError("mandate version and name must be non-empty")
        if not isinstance(self.notes, str):
            raise ValueError("mandate notes must be text")
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
            valid_type = (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            )
            try:
                finite = valid_type and math.isfinite(value)
            except (OverflowError, TypeError, ValueError):
                finite = False
            if (
                not finite
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

        if self.approved_by is not None and (
            type(self.approved_by) is not str
            or not self.approved_by
            or self.approved_by != self.approved_by.strip()
        ):
            raise ValueError("approved_by must be canonical non-empty text")
        if self.approved_at is not None:
            _canonical_aware_iso_timestamp(self.approved_at, name="approved_at")

        if self.status == "approved":
            if self.approved_at is None or self.approved_by is None:
                raise ValueError(
                    "an approved mandate requires approved_at and approved_by"
                )
            expected = compute_mandate_fingerprint(self)
            if (
                type(self.approved_fingerprint) is not str
                or self.approved_fingerprint != expected
            ):
                raise ValueError(
                    "approved_fingerprint does not match the mandate's behavior fields"
                )

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["permitted_instruments"] = list(self.permitted_instruments)
        return result


def load_portfolio_mandate(path: str | Path) -> PortfolioMandate:
    """Load and validate a mandate from an explicit caller-owned path."""
    raw = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_non_finite_json_constant,
    )
    raw["permitted_instruments"] = tuple(raw.get("permitted_instruments", ()))
    mandate = PortfolioMandate(**raw)
    mandate.validate()
    return mandate
