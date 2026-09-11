"""Offline contracts for the Short Interest ETF research lane.

This package exports official short-interest snapshot types and the additive,
zero-authority SI-0M research gate. Daily short-sale volume has a separate
module and is never re-exported here, so it cannot enter the canonical dataset
through a convenient alias.
"""
from __future__ import annotations

from research.short_interest_etf.availability import (
    ExecutionCohort,
    release_execution_cohort,
    snapshot_execution_cohort,
)
from research.short_interest_etf.contracts import (
    CollectionManifest,
    DenominatorKind,
    DenominatorObservation,
    ReleaseCalendarEntry,
    ReleasePrecision,
    SecurityIdentity,
    ShortInterestContractError,
    ShortInterestSnapshot,
    SourceEntitlement,
    SourceSemantic,
    VolumeBasis,
)
from research.short_interest_etf.preregistration import (
    FIXED_STRATEGY_LANE_IDS,
    PREREGISTRATION,
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    ShortInterestAllocationState,
    ShortInterestPreregistrationError,
    ShortInterestResearchGate,
    ShortInterestSlotDisposition,
    require_short_interest_research_gate,
)

__all__ = [
    "CollectionManifest",
    "DenominatorKind",
    "DenominatorObservation",
    "ExecutionCohort",
    "FIXED_STRATEGY_LANE_IDS",
    "PREREGISTRATION",
    "ReleaseCalendarEntry",
    "ReleasePrecision",
    "SecurityIdentity",
    "ShortInterestContractError",
    "ShortInterestAllocationState",
    "ShortInterestPreregistrationError",
    "ShortInterestResearchGate",
    "ShortInterestSlotDisposition",
    "ShortInterestSnapshot",
    "SHORT_INTEREST_RESEARCH_GATE",
    "SHORT_INTEREST_RESEARCH_GATE_SHA256",
    "SourceEntitlement",
    "SourceSemantic",
    "VolumeBasis",
    "release_execution_cohort",
    "require_short_interest_research_gate",
    "snapshot_execution_cohort",
]
