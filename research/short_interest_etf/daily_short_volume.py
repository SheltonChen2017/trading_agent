"""A deliberately separate type for non-canonical daily short-sale volume.

Daily short-sale volume measures transaction flow, not the twice-monthly open
short-position snapshot. The canonical short-interest package does not
re-export this class and its dataset builder refuses this semantic explicitly.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping

from research.short_interest_etf.contracts import (
    ShortInterestContractError,
    _canonical_date,
    _integer,
    _payload_fields,
    _required_text,
    _sha256,
)


class DailyVolumeSemantic(str, Enum):
    DAILY_SHORT_SALE_VOLUME = "daily_short_sale_volume"


@dataclasses.dataclass(frozen=True)
class DailyShortSaleVolumeRecord:
    semantic: DailyVolumeSemantic
    trade_date: str
    ticker: str
    short_sale_volume: int
    total_volume: int
    source_id: str
    source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        if self.semantic is not DailyVolumeSemantic.DAILY_SHORT_SALE_VOLUME:
            raise ShortInterestContractError(
                "daily volume semantic must be daily_short_sale_volume"
            )
        _canonical_date(self.trade_date, "trade_date")
        _required_text(self.ticker, "ticker")
        if self.ticker != self.ticker.upper():
            raise ShortInterestContractError("ticker must be canonical uppercase")
        short = _integer(self.short_sale_volume, "short_sale_volume")
        total = _integer(self.total_volume, "total_volume", minimum=1)
        if short > total:
            raise ShortInterestContractError(
                "short_sale_volume must not exceed total_volume"
            )
        _required_text(self.source_id, "source_id")
        _required_text(self.source_version, "source_version")
        _sha256(self.raw_record_sha256, "raw_record_sha256")

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["semantic"] = self.semantic.value
        return payload

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> "DailyShortSaleVolumeRecord":
        values = _payload_fields(cls, payload)
        try:
            values["semantic"] = DailyVolumeSemantic(values.get("semantic"))
        except (TypeError, ValueError):
            raise ShortInterestContractError(
                "semantic must be daily_short_sale_volume"
            ) from None
        return cls(**values)
