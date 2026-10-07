"""Offline QC data-boundary adapter; no SDK, subscriptions or cloud calls.

Snapshots model the documented QuoteBar bid/ask close and TradeBar volume
fields. An eventual licensed SDK bridge must explicitly normalize its source
clock/decimal/security identity; this module does not guess those mappings.
Only synthetic snapshots can enter the local order simulator. Passing its
tests is not LEAN compilation, QC execution, or acceptance of a fill model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.guidance_revision_drift.controls import refuse_external_action
from research.guidance_revision_drift.simulation import Minute, Simulation


class QcAdapterError(ValueError):
    """An offline bar snapshot cannot be mapped without ambiguity."""


def _sid(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"SYN-[A-Za-z0-9_-]{1,60}", value) is None:
        raise QcAdapterError("synthetic permanent security ID required")
    return value


def _clock(value: object) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0) or value.year not in (2024, 2025)):
        raise QcAdapterError("explicit UTC synthetic 2024/2025 clock required")
    return value


def _price(value: object) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise QcAdapterError("positive finite exact Decimal price required")
    if len(value.as_tuple().digits) > 128 or abs(int(value.as_tuple().exponent)) > 128:
        raise QcAdapterError("price exceeds resource bound")
    return value


@dataclass(frozen=True, slots=True)
class QcQuoteSnapshot:
    security_id: str
    start_utc: datetime
    end_utc: datetime
    bid_close: Decimal
    ask_close: Decimal
    fill_forward: bool = False
    normalization: str = "Raw"

    def __post_init__(self) -> None:
        _sid(self.security_id)
        if _clock(self.end_utc) - _clock(self.start_utc) != timedelta(minutes=1):
            raise QcAdapterError("complete one-minute quote interval required")
        if _price(self.ask_close) < _price(self.bid_close):
            raise QcAdapterError("crossed quote")
        if type(self.fill_forward) is not bool or self.fill_forward:
            raise QcAdapterError("fill-forward quotes cannot simulate executions")
        if type(self.normalization) is not str or self.normalization != "Raw":
            raise QcAdapterError("raw prices required; do not double-count actions")


@dataclass(frozen=True, slots=True)
class QcTradeSnapshot:
    security_id: str
    start_utc: datetime
    end_utc: datetime
    volume: int
    fill_forward: bool = False
    normalization: str = "Raw"

    def __post_init__(self) -> None:
        _sid(self.security_id)
        if _clock(self.end_utc) - _clock(self.start_utc) != timedelta(minutes=1):
            raise QcAdapterError("complete one-minute trade interval required")
        if type(self.volume) is not int or not 0 <= self.volume <= 10**12:
            raise QcAdapterError("bounded integer trade volume required")
        if type(self.fill_forward) is not bool or self.fill_forward:
            raise QcAdapterError("fill-forward trade volume refused")
        if type(self.normalization) is not str or self.normalization != "Raw":
            raise QcAdapterError("raw prices required")


@dataclass(frozen=True, slots=True)
class SecurityBinding:
    security_id: str
    issuer_id: str
    valid_from: date
    valid_through: date

    def __post_init__(self) -> None:
        _sid(self.security_id)
        _sid(self.issuer_id)
        if (type(self.valid_from) is not date or type(self.valid_through) is not date
                or self.valid_from > self.valid_through):
            raise QcAdapterError("dated security binding required")


class QcFixtureAdapter:
    """Map explicit paired snapshots to local simulator callbacks only."""

    def __init__(self, simulation: Simulation, bindings: tuple[SecurityBinding, ...]):
        if type(simulation) is not Simulation or type(bindings) is not tuple or not bindings:
            raise QcAdapterError("exact simulator and immutable bindings required")
        keys = set()
        for binding in bindings:
            if type(binding) is not SecurityBinding:
                raise QcAdapterError("exact security binding required")
            binding.__post_init__()
            if binding.security_id in keys:
                raise QcAdapterError("ambiguous security mapping")
            keys.add(binding.security_id)
        self._simulation = simulation
        self._bindings = tuple(SecurityBinding(b.security_id, b.issuer_id, b.valid_from, b.valid_through)
                               for b in bindings)
        self._receipts: dict[tuple[str, datetime], str] = {}

    def on_minute(self, quote: QcQuoteSnapshot, trade: QcTradeSnapshot, *,
                  adv20: Decimal, settlement_session: date):
        if type(quote) is not QcQuoteSnapshot or type(trade) is not QcTradeSnapshot:
            raise QcAdapterError("exact synthetic quote and trade snapshots required")
        quote.__post_init__()
        trade.__post_init__()
        if (quote.security_id, quote.start_utc, quote.end_utc) != (
                trade.security_id, trade.start_utc, trade.end_utc):
            raise QcAdapterError("quote/trade security and interval mismatch")
        _price(adv20)
        if type(settlement_session) is not date:
            raise QcAdapterError("explicit settlement date required")
        mapping = []
        for binding in self._bindings:
            binding.__post_init__()
            if binding.security_id == quote.security_id:
                mapping.append(binding)
        if len(mapping) != 1:
            raise QcAdapterError("unknown or ambiguous security ID")
        binding = mapping[0]
        if not binding.valid_from <= quote.end_utc.date() <= binding.valid_through:
            raise QcAdapterError("security mapping is outside its dated validity")
        digest = hash_payload({
            "security_id": quote.security_id, "issuer_id": binding.issuer_id,
            "start": quote.start_utc.isoformat(), "end": quote.end_utc.isoformat(),
            "bid": decimal_text(quote.bid_close), "ask": decimal_text(quote.ask_close),
            "volume": trade.volume, "adv20": decimal_text(adv20),
            "settlement": settlement_session.isoformat(),
        })
        key = (quote.security_id, quote.end_utc)
        if key in self._receipts:
            if self._receipts[key] != digest:
                raise QcAdapterError("conflicting replay of market-data callback")
            return ()
        fills = self._simulation.process_minute(Minute(
            binding.issuer_id, quote.end_utc, quote.bid_close, quote.ask_close,
            trade.volume, adv20, settlement_session,
        ))
        self._receipts[key] = digest
        return fills

    @property
    def receipt_hashes(self) -> tuple[str, ...]:
        return tuple(self._receipts.values())

    def launch(self) -> None:
        refuse_external_action("qc_launch")


def adapter_manifest() -> dict:
    """Read-only compatibility scope; null bindings deliberately remain null."""
    return {
        "schema": "gdr.synthetic.qc-adapter.v1",
        "candidate_status": "unreviewed", "engine": "offline_fixture_harness",
        "normalization": "Raw", "quote_fields": ["bid.close", "ask.close", "end_time"],
        "trade_fields": ["volume", "end_time"], "clock": "explicit_aware_UTC",
        "qc_engine_version": None, "qc_project_id": None, "qc_backtest_id": None,
        "cloud_completed": False, "qc_upload": False, "qc_launch": False,
        "point_in_time_data": False,
        "missing_acceptance": ["licensed_source_and_clock_bridge", "exact_engine_and_brokerage_freeze",
                               "LEAN_compile", "authorized_QC_execution", "independent_review"],
    }
