"""
Versioned personal trading policy.

This is the deterministic definition of what the assistant is allowed to
propose and execute. The language-model/explanation layer may discuss a
trade, but only this policy plus risk.execution_gate can authorize it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
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
    max_spread_pct: float = 0.5
    earnings_blackout_days: int = 2
    require_earnings_data: bool = False
    allowed_sides: tuple[str, ...] = ("buy", "sell")
    allowed_order_types: tuple[str, ...] = ("market", "limit")
    allow_new_positions: bool = False
    enable_strategy_proposals: bool = False
    notes: str = ""

    SUPPORTED_SIDES = ("buy", "sell")
    SUPPORTED_ORDER_TYPES = ("market", "limit")

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
            if not (math.isfinite(value) and 0 <= value <= 1):
                raise ValueError(f"{field_name} must be a finite number between 0 and 1, got {value}.")
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ValueError("max_position_pct cannot exceed max_total_exposure_pct.")
        # Every one of these feeds a plain `>`/`<` comparison in
        # risk/execution_gate.py -- a NaN there evaluates False no matter
        # what it's compared against, which would silently disable that
        # cap entirely rather than reject the trade (Codex review,
        # 2026-07-27). json.loads() also accepts a literal `NaN` in a
        # policy file by default, so this is reachable from a malformed
        # config, not just a caller bug.
        if not math.isfinite(self.max_order_value) or self.max_order_value <= 0:
            raise ValueError(f"max_order_value must be a positive, finite number, got {self.max_order_value}.")
        if not math.isfinite(self.max_stale_price_minutes) or self.max_stale_price_minutes <= 0:
            raise ValueError(
                f"max_stale_price_minutes must be a positive, finite number, got {self.max_stale_price_minutes}."
            )
        if not math.isfinite(self.max_slippage_pct) or self.max_slippage_pct < 0:
            raise ValueError(f"max_slippage_pct must be a non-negative, finite number, got {self.max_slippage_pct}.")
        if not math.isfinite(self.max_spread_pct) or self.max_spread_pct < 0:
            raise ValueError(f"max_spread_pct must be a non-negative, finite number, got {self.max_spread_pct}.")
        # isinstance(x, int), not a `< 0` comparison alone: NaN/inf/1.5 are
        # all `float`, not `int`, so this rejects them along with negative
        # values in one check -- a bare `< 0` comparison silently passed
        # NaN (NaN < 0 is False) and would have disabled the earnings
        # blackout check entirely (Codex review, 2026-07-27). bool is
        # excluded even though it's technically an int subclass, so
        # True/False can't silently pass as 1/0.
        if (
            not isinstance(self.earnings_blackout_days, int)
            or isinstance(self.earnings_blackout_days, bool)
            or self.earnings_blackout_days < 0
        ):
            raise ValueError(
                f"earnings_blackout_days must be a non-negative integer, got {self.earnings_blackout_days!r}."
            )
        if not self.allowed_sides:
            raise ValueError("allowed_sides cannot be empty.")
        unsupported_sides = set(self.allowed_sides) - set(self.SUPPORTED_SIDES)
        if unsupported_sides:
            raise ValueError(f"Unsupported allowed_sides: {sorted(unsupported_sides)}.")
        if not self.allowed_order_types:
            raise ValueError("allowed_order_types cannot be empty.")
        unsupported_order_types = set(self.allowed_order_types) - set(self.SUPPORTED_ORDER_TYPES)
        if unsupported_order_types:
            raise ValueError(
                f"Unsupported/unimplemented allowed_order_types: {sorted(unsupported_order_types)}."
            )
        for field_name in (
            "require_earnings_data",
            "allow_new_positions",
            "enable_strategy_proposals",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean, got {value!r}.")

    def to_dict(self) -> dict:
        result = dataclasses.asdict(self)
        result["allowed_sides"] = list(self.allowed_sides)
        result["allowed_order_types"] = list(self.allowed_order_types)
        return result


def compute_policy_fingerprint(policy: TradingPolicy) -> str:
    """Deterministic fingerprint over every policy field except `notes`
    (free-text/explanatory, not behavior-affecting). Proposals bind to
    this in ADDITION to `version` -- a manually-maintained version string
    alone can't catch an edited-but-not-rebumped policy file (GPT review,
    2026-07-28): two policy files (e.g. a personal one copied from the
    default) can share the same version string yet have materially
    different limits, and approval previously only compared that string.
    Any change to a behavior-affecting field changes this fingerprint
    regardless of whether `version` was bumped, so approval fails closed
    on drift instead of depending on a human remembering to bump it."""
    payload = {k: v for k, v in policy.to_dict().items() if k != "notes"}
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> TradingPolicy:
    policy_path = Path(path)
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    raw["allowed_sides"] = tuple(raw.get("allowed_sides", ("buy", "sell")))
    raw["allowed_order_types"] = tuple(raw.get("allowed_order_types", ("market", "limit")))
    policy = TradingPolicy(**raw)
    policy.validate()
    return policy
