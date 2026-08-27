"""Measured provider-history eras and pre-contract quarantine policy."""
from __future__ import annotations

import dataclasses
from datetime import date
from enum import Enum


class ProviderHistoryError(ValueError):
    pass


class ProviderEra(str, Enum):
    PRE_2013_BACKFILL_UNVERIFIED = "pre_2013_backfill_unverified"
    POST_2013_CONTRACT_CANDIDATE = "post_2013_contract_candidate"


@dataclasses.dataclass(frozen=True)
class ProviderEraDecision:
    event_date: str
    era: ProviderEra
    admissible: bool
    refusal_reason: str | None


# Snapshot A measured five accepted events in 2011, 24,296 in 2012, and
# 28,609 in 2013. Those observations correct the factual claim that the bytes
# start in 2013, but they do not establish early backfill semantics.
MEASURED_ACCEPTED_COUNTS = {2011: 5, 2012: 24_296, 2013: 28_609}
CANONICAL_CONTRACT_CANDIDATE_START = date(2013, 1, 1)


def classify_provider_era(event_date: str) -> ProviderEraDecision:
    if not isinstance(event_date, str):
        raise ProviderHistoryError("event_date must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(event_date)
    except ValueError as exc:
        raise ProviderHistoryError(
            "event_date must use canonical YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != event_date:
        raise ProviderHistoryError("event_date must use canonical YYYY-MM-DD format")
    if parsed < CANONICAL_CONTRACT_CANDIDATE_START:
        return ProviderEraDecision(
            event_date=event_date,
            era=ProviderEra.PRE_2013_BACKFILL_UNVERIFIED,
            admissible=False,
            refusal_reason="provider_backfill_semantics_unverified_pre_2013",
        )
    return ProviderEraDecision(
        event_date=event_date,
        era=ProviderEra.POST_2013_CONTRACT_CANDIDATE,
        admissible=True,
        refusal_reason=None,
    )
