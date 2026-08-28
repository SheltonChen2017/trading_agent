"""Frozen SI-0 choices that require no market outcomes to state.

The fixture milestone has a zero outcome-look budget. Later research looks,
licensed data, extensions, and any change to these choices require a new
owner-authorized milestone and a recorded preregistration change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.hashing import hash_payload


@dataclass(frozen=True)
class ShortInterestPreregistration:
    source_semantic: str = field(
        default="official_open_short_position_snapshot", init=False
    )
    execution_calendar: str = field(default="XNYS", init=False)
    canonical_denominator: str = field(
        default="point_in_time_shares_outstanding", init=False
    )
    audited_preferred_denominator: str = field(
        default="point_in_time_float", init=False
    )
    score_family: tuple[str, ...] = field(
        default=(
            "S0_level",
            "S1_delta",
            "S2_surprise",
            "S3_delta_dtc",
            "S4_residual",
        ),
        init=False,
    )
    canonical_score: str = field(default="S1_delta", init=False)
    primary_horizon_sessions: int = field(default=20, init=False)
    primary_cost_bps: int = field(default=10, init=False)
    cost_sensitivity_bps: tuple[int, ...] = field(default=(0, 5, 20), init=False)
    canonical_leverage: int = field(default=1, init=False)
    milestone_outcome_look_budget: int = field(default=0, init=False)
    outcome_looks_used: int = field(default=0, init=False)
    production_authoritative: bool = field(default=False, init=False)
    schema_version: str = field(default="1.0", init=False)

    def to_payload(self) -> dict[str, Any]:
        return {
            "audited_preferred_denominator": self.audited_preferred_denominator,
            "canonical_denominator": self.canonical_denominator,
            "canonical_leverage": self.canonical_leverage,
            "canonical_score": self.canonical_score,
            "cost_sensitivity_bps": list(self.cost_sensitivity_bps),
            "execution_calendar": self.execution_calendar,
            "milestone_outcome_look_budget": self.milestone_outcome_look_budget,
            "outcome_looks_used": self.outcome_looks_used,
            "primary_cost_bps": self.primary_cost_bps,
            "primary_horizon_sessions": self.primary_horizon_sessions,
            "production_authoritative": self.production_authoritative,
            "schema_version": self.schema_version,
            "score_family": list(self.score_family),
            "source_semantic": self.source_semantic,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


PREREGISTRATION = ShortInterestPreregistration()
