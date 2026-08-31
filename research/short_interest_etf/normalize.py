"""Normalize source-shaped rows without silently dropping any input row."""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from research.short_interest_etf.contracts import (
    ShortInterestContractError,
    ShortInterestSnapshot,
    SourceSemantic,
    _canonical_date,
    _optional_text,
    _payload_fields,
    _required_text,
    parse_utc_timestamp,
)

REFUSAL_DAILY_SHORT_VOLUME = "daily_short_volume_substitution"
REFUSAL_DUPLICATE_SOURCE_RECORD = "duplicate_source_record_id"
REFUSAL_INVALID_SEMANTIC = "invalid_source_semantic"
REFUSAL_INVALID_SNAPSHOT = "invalid_snapshot_contract"


@dataclass(frozen=True)
class SnapshotRefusal:
    source_record_id: str | None
    settlement_date: str | None
    reason: str
    detail: str

    def __post_init__(self) -> None:
        _optional_text(self.source_record_id, "source_record_id")
        if self.settlement_date is not None:
            _canonical_date(self.settlement_date, "settlement_date")
        _required_text(self.reason, "reason")
        _required_text(self.detail, "detail")

    def to_payload(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "reason": self.reason,
            "settlement_date": self.settlement_date,
            "source_record_id": self.source_record_id,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SnapshotRefusal":
        return cls(**_payload_fields(cls, payload))


def _audit_text(row: Any, name: str) -> str | None:
    if not isinstance(row, Mapping):
        return None
    value = row.get(name)
    return (
        value
        if isinstance(value, str) and value and value == value.strip()
        else None
    )


def _audit_date(row: Any, name: str) -> str | None:
    value = _audit_text(row, name)
    if value is None:
        return None
    try:
        _canonical_date(value, name)
    except ShortInterestContractError:
        return None
    return value


def normalize_snapshot_payloads(
    rows: Iterable[Any],
) -> tuple[tuple[ShortInterestSnapshot, ...], tuple[SnapshotRefusal, ...]]:
    """Return canonical snapshots and one named disposition per refused row.

    Source-record identity is counted before validation. Every occurrence of a
    duplicated identifier is refused, including the first, so input ordering
    cannot decide which value wins.
    """
    materialized = tuple(rows)
    id_counts = collections.Counter(
        value
        for row in materialized
        if (value := _audit_text(row, "source_record_id")) is not None
    )
    accepted: list[ShortInterestSnapshot] = []
    refusals: list[SnapshotRefusal] = []

    for row in materialized:
        record_id = _audit_text(row, "source_record_id")
        settlement = _audit_date(row, "settlement_date")
        if isinstance(row, Mapping):
            semantic = row.get("semantic")
            if semantic == "daily_short_sale_volume":
                refusals.append(
                    SnapshotRefusal(
                        record_id,
                        settlement,
                        REFUSAL_DAILY_SHORT_VOLUME,
                        "daily short-sale transaction volume is not an open "
                        "short-position snapshot",
                    )
                )
                continue
            if semantic != SourceSemantic.OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT.value:
                refusals.append(
                    SnapshotRefusal(
                        record_id,
                        settlement,
                        REFUSAL_INVALID_SEMANTIC,
                        f"semantic={semantic!r}",
                    )
                )
                continue
            if record_id is not None and id_counts[record_id] > 1:
                refusals.append(
                    SnapshotRefusal(
                        record_id,
                        settlement,
                        REFUSAL_DUPLICATE_SOURCE_RECORD,
                        f"source_record_id appears {id_counts[record_id]} times",
                    )
                )
                continue
        try:
            accepted.append(ShortInterestSnapshot.from_payload(row))
        except ShortInterestContractError as exc:
            refusals.append(
                SnapshotRefusal(
                    record_id,
                    settlement,
                    REFUSAL_INVALID_SNAPSHOT,
                    str(exc),
                )
            )

    accepted.sort(
        key=lambda event: (
            event.settlement_date,
            event.security.security_id,
            parse_utc_timestamp(
                event.revision_published_at, "revision_published_at"
            ),
            event.event_id,
        )
    )
    refusals.sort(
        key=lambda refusal: (
            refusal.settlement_date or "",
            refusal.source_record_id or "",
            refusal.reason,
            refusal.detail,
        )
    )
    if len(accepted) + len(refusals) != len(materialized):
        raise AssertionError("normalization must disposition every input row")
    return tuple(accepted), tuple(refusals)
