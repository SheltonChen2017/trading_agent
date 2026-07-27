"""
Versioned personal trading policy.

This is the deterministic definition of what the assistant is allowed to
propose and execute. The language-model/explanation layer may discuss a
trade, but only this policy plus risk.execution_gate can authorize it.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Literal

from config import MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "default_policy.json"


@dataclasses.dataclass(frozen=True)
class TradingPolicy:
    version: str
    name: str
    execution_mode: Literal["read_only", "paper"] = "read_only"
    max_position_pct: float = MAX_POSITION_PCT
    max_total_exposure_pct: float = MAX_TOTAL_EXPOSURE_PCT
    max_basket_pct: float = 0.40
    max_leveraged_etf_pct: float = 0.20
    min_cash_reserve_pct: float = 0.10
    max_order_value: float = 5_000.0
    max_stale_price_minutes: float = 15.0
    max_slippage_pct: float = 1.0
    earnings_blackout_days: int = 2
    require_earnings_data: bool = False
    allowed_sides: tuple[str, ...] = ("buy", "sell")
    allowed_order_types: tuple[str, ...] = ("market", "limit")
    allow_new_positions: bool = False
    enable_strategy_proposals: bool = False
    notes: str = ""

    def validate(self) -> None:
        percentage_fields = (
            "max_position_pct",
            "max_total_exposure_pct",
            "max_basket_pct",
            "max_leveraged_etf_pct",
            "min_cash_reserve_pct",
        )
        for field_name in percentage_fields:
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1, got {value}.")
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ValueError("max_position_pct cannot exceed max_total_exposure_pct.")
        if self.max_order_value <= 0:
            raise ValueError("max_order_value must be positive.")
        if self.max_stale_price_minutes <= 0:
            raise ValueError("max_stale_price_minutes must be positive.")

    def to_dict(self) -> dict:
        result = dataclasses.asdict(self)
        result["allowed_sides"] = list(self.allowed_sides)
        result["allowed_order_types"] = list(self.allowed_order_types)
        return result


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> TradingPolicy:
    policy_path = Path(path)
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    raw["allowed_sides"] = tuple(raw.get("allowed_sides", ("buy", "sell")))
    raw["allowed_order_types"] = tuple(raw.get("allowed_order_types", ("market", "limit")))
    policy = TradingPolicy(**raw)
    policy.validate()
    return policy
