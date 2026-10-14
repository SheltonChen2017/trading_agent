"""Deterministic operation-count scaling proof; no timing benchmark or data.

The released prototype is instrumented in memory only and restored by each
MonkeyPatch context. Fabricated native aliases/orders are the only inputs.
This demonstrates a software complexity risk, not measured QC runtime/RAM.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace as NS

import pytest

from scripts import short_interest_lean_joint_transport as bridge
from research.short_interest_etf import native_qc_order_representation as rep
from test_short_interest_native_lean_joint_transport import FabricatedRuntime


@dataclasses.dataclass
class Counts:
    native_decimal_reads: int = 0
    snapshot_calls: int = 0
    snapshot_alias_visits: int = 0
    snapshot_decimal_reads: int = 0
    state_payload_builds: int = 0
    state_history_entries: int = 0
    state_position_entries: int = 0
    peak_positions: int = 0

    def reset(self):
        for field in dataclasses.fields(self):
            setattr(self, field.name, 0)


class CountedRuntime(FabricatedRuntime):
    def __init__(self, counts):
        super().__init__()
        self.counts = counts

    def decimal(self, obj, *path):
        self.counts.native_decimal_reads += 1
        return super().decimal(obj, *path)


class CountedHub(bridge.JointTransport):
    def __init__(self, runtime, counts):
        self.counts = counts
        super().__init__(runtime)

    def _snapshot(self, alias_fees=None):
        self.counts.snapshot_calls += 1
        self.counts.snapshot_alias_visits += len(self.securities)
        before = self.counts.native_decimal_reads
        result = super()._snapshot(alias_fees)
        self.counts.snapshot_decimal_reads += self.counts.native_decimal_reads - before
        return result


def instrument_state_payload(patch, counts):
    original = rep.CellTransportState._payload

    def counted(state):
        counts.state_payload_builds += 1
        counts.state_history_entries += len(state.consumed_order_ids) + len(state.consumed_event_keys)
        counts.state_position_entries += len(state.positions)
        counts.peak_positions = max(counts.peak_positions, len(state.positions))
        return original(state)

    patch.setattr(rep.CellTransportState, "_payload", counted)


def new_alias(hub, native):
    cell = rep.CELL_IDS[0]
    alias = rep.security_alias(cell, native)
    security = NS(Symbol=NS(Value=alias), Type="Base", QuoteCurrency=NS(Symbol="USD"),
        SymbolProperties=NS(LotSize=Decimal("1e-18"), MinimumPriceVariation=Decimal("1e-18"),
                            ContractMultiplier=Decimal(1)),
        Holdings=NS(Quantity=Decimal(0), AveragePrice=Decimal(0), TotalFees=Decimal(0)),
        Price=Decimal(30))
    hub.register_security(cell, native, security)
    security.FeeModel, security.FillModel = bridge.ExactFeeModel(hub), bridge.ExactFillModel(hub)
    security.BuyingPowerModel = bridge.CellBuyingPowerModel(hub)
    security.SettlementModel = bridge.PostedNotionalSettlement(hub)
    return security


def native_order(hub, *, native, at, index, side="buy"):
    cell = rep.CELL_IDS[0]
    hub.runtime.at = at
    scheduled = rep.prepare_cell_order(hub.book(cell), at=at, security_id=native,
        event_id=f"fabricated-event-{index:06d}", order_id=f"fabricated-order-{index:06d}",
        side=side, economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    hub.offer_raw_open(rep.security_alias(cell, native), at=at, raw_open=Fraction(30))
    hub.submit(scheduled)


def alias_profile(alias_count, order_count=20):
    counts = Counts()
    with pytest.MonkeyPatch.context() as patch:
        instrument_state_payload(patch, counts)
        runtime = CountedRuntime(counts)
        hub = CountedHub(runtime, counts)
        runtime.hub = hub
        for index in range(alias_count):
            new_alias(hub, f"native:fabricated-scale-{index:06d}")
        counts.reset()  # Registration itself is intentionally excluded.
        for index in range(order_count):
            native_order(hub, native=f"native:fabricated-scale-{index:06d}",
                         at="2023-01-03T14:30:00Z", index=index)
        result = dataclasses.asdict(counts)
    return result


def history_profile(order_count):
    counts = Counts()
    with pytest.MonkeyPatch.context() as patch:
        instrument_state_payload(patch, counts)
        runtime = CountedRuntime(counts)
        hub = CountedHub(runtime, counts)
        runtime.hub = hub
        native = "native:fabricated-history"
        new_alias(hub, native)
        counts.reset()
        for index in range(order_count):
            session = rep.resolve_nth_session_after("2023-01-02", index + 1)
            at = rep._open_instant(session).strftime("%Y-%m-%dT%H:%M:%SZ")
            native_order(hub, native=native, at=at, index=index,
                         side="buy" if index % 2 == 0 else "sell")
        assert hub.book(rep.CELL_IDS[0]).transport.positions == ()
        result = dataclasses.asdict(counts)
    return result


def test_released_bridge_three_full_native_snapshots_per_order_scale_with_every_alias():
    profiles = {n: alias_profile(n) for n in (50, 100, 200)}
    for n, counts in profiles.items():
        assert counts["snapshot_calls"] == 3 * 20
        assert counts["snapshot_alias_visits"] == 3 * 20 * n
        # Each snapshot reads Quantity and TotalFees for each alias, plus USD
        # Cash.Amount. These reads prove order-count × registered-alias count.
        assert counts["snapshot_decimal_reads"] == 3 * 20 * (2 * n + 1)
    assert profiles[200]["native_decimal_reads"] - profiles[100]["native_decimal_reads"] == 6 * 20 * 100
    assert profiles[100]["native_decimal_reads"] - profiles[50]["native_decimal_reads"] == 6 * 20 * 50
    print("fabricated alias-operation counts", profiles)


def test_released_sealed_state_history_serialization_scales_quadratically_without_position_growth():
    small, large = history_profile(20), history_profile(40)
    # The same single alias is alternately bought/closed. No large universe or
    # growing positions explain the cost; both full order-history arrays do.
    assert small["peak_positions"] == large["peak_positions"] == 1
    assert large["state_payload_builds"] < 3 * small["state_payload_builds"]
    assert large["state_history_entries"] > Fraction(7, 2) * small["state_history_entries"]
    assert large["snapshot_alias_visits"] == 2 * small["snapshot_alias_visits"]
    print("fabricated history-operation counts", {20: small, 40: large})
