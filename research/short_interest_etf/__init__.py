"""Offline contracts for the Short Interest ETF research lane.

This package deliberately exports official short-interest snapshot types only.
Daily short-sale volume has a separate module and is never re-exported here,
so it cannot enter the canonical dataset through a convenient alias.
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
from research.short_interest_etf.preregistration import PREREGISTRATION

__all__ = [
    "CollectionManifest",
    "DenominatorKind",
    "DenominatorObservation",
    "ExecutionCohort",
    "PREREGISTRATION",
    "ReleaseCalendarEntry",
    "ReleasePrecision",
    "SecurityIdentity",
    "ShortInterestContractError",
    "ShortInterestSnapshot",
    "SourceEntitlement",
    "SourceSemantic",
    "VolumeBasis",
    "release_execution_cohort",
    "snapshot_execution_cohort",
]
