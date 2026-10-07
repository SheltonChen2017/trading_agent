"""Synthetic behavior proofs for the separate raw-proxy hypothetical engine."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import localcontext

import pytest

from research.target_price_revisions_development import raw_backtest as bt

CUTOFF = "2024-01-02T21:00:00Z"
OPEN = "2024-01-03T14:30:00Z"
CLOSE = "2024-01-03T21:00:00Z"
INVENTORY = tuple({"security_id": sid, "asset_type": "common-stock"} for sid in ("NATIVE:A", "NATIVE:B", "NATIVE:C"))


def bar(sid="NATIVE:A", **changes):
    value = {"security_id": sid, "open": "10", "close": "10", "lagged_volume": 100_000,
             "volume_available_at_utc": CUTOFF, "open_available_at_utc": OPEN,
             "close_available_at_utc": CLOSE, "tradable": True}
    value.update(changes)
    return value


def target(weights=(("NATIVE:A", "0.1"),), **changes):
    value = {"session_id": "2024-01-03", "cutoff_utc": CUTOFF,
             "weights": tuple({"security_id": sid, "weight": weight} for sid, weight in weights),
             "decision_marks": tuple({"security_id": sid, "price": "10", "available_at_utc": CUTOFF} for sid, _ in weights)}
    value.update(changes)
    return value


def run(*, rows=None, frame=None, cash="1000", positions=(), sessions=None, **changes):
    args = {"security_inventory": INVENTORY, "initial_cash": cash, "initial_positions": positions,
            "targets": (target() if frame is None else frame,),
            "sessions": ({"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE,
                          "bars": (bar(),) if rows is None else rows},) if sessions is None else sessions}
    args.update(changes)
    return bt.run_raw_revision_backtest(**args)


def positions(*rows):
    return tuple({"security_id": sid, "quantity": qty} for sid, qty in rows)


def quantities(result):
    return {row.security_id: row.quantity for row in result.final_positions}


def test_known_decision_marks_size_whole_shares_and_fixed_costs_conserve_nav():
    result = run()
    assert [(f.side, f.quantity, f.execution_price, f.commission, f.slippage_cost) for f in result.fills] == [("buy", 9, "10.01", "0.09", "0.09")]
    assert result.final_cash == "909.82"
    assert quantities(result) == {"NATIVE:A": 9}
    assert result.sessions[0].decision_equity == "1000"
    assert result.sessions[0].close_equity == "999.82"
    assert result.total_commission == "0.09" and result.total_slippage == "0.09"
    assert result.complete is True
    assert result.mode == "raw-target-change-proxy-development"
    assert result.costs_calibrated is False and result.point_in_time_data is False
    assert all(value is False for _, value in result.authority)
    with pytest.raises(FrozenInstanceError):
        result.final_cash = "9999"


def test_sells_before_buys_and_explicit_zero_exit_is_not_silently_removed():
    result = run(cash="0", positions=positions(("NATIVE:B", 50)),
                 frame=target((("NATIVE:A", "0.1"), ("NATIVE:B", "0"))), rows=(bar(), bar("NATIVE:B")))
    assert [(f.side, f.security_id, f.quantity) for f in result.fills] == [("sell", "NATIVE:B", 50), ("buy", "NATIVE:A", 4)]
    assert quantities(result) == {"NATIVE:A": 4}
    assert result.final_cash == "458.92" and result.sessions[0].close_equity == "498.92"
    assert result.total_commission == "0.54" and result.total_slippage == "0.54"


def test_open_gap_changes_affordability_but_not_decision_requested_quantity():
    first = run()
    gap = run(rows=(bar(open="1000", close="1000"),))
    assert first.orders[0].requested_quantity == gap.orders[0].requested_quantity == 9
    assert gap.fills == () and gap.final_cash == "1000"
    assert gap.orders[0].pending_quantity == 9 and gap.complete is False
    assert "insufficient_cash" in {r.reason for r in gap.exclusions}


def test_execution_name_cap_limits_gap_fill_without_changing_frozen_requested_quantity():
    result = run(rows=(bar(open="20", close="20"),))
    assert result.orders[0].requested_quantity == 9
    assert result.fills[0].quantity == 4 and result.orders[0].pending_quantity == 5
    assert result.sessions[0].close_equity == "999.88" and result.final_cash == "919.88"
    assert "execution_name_cap" in {r.reason for r in result.exclusions}


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_one_percent_lagged_volume_bounds_partial_fills_and_pending_quantity(side):
    if side == "buy":
        result = run(rows=(bar(lagged_volume=300),))
        assert quantities(result) == {"NATIVE:A": 3}
        assert result.orders[0].requested_quantity == 9
        assert result.orders[0].pending_quantity == 6
    else:
        result = run(cash="0", positions=positions(("NATIVE:A", 20)), frame=target((("NATIVE:A", "0"),)), rows=(bar(lagged_volume=300),))
        assert quantities(result) == {"NATIVE:A": 17}
        assert result.orders[0].pending_quantity == 17
    assert result.fills[0].quantity == 3 and result.complete is False
    assert "lagged_volume_capacity" in {r.reason for r in result.exclusions}


@pytest.mark.parametrize("changes", [{"lagged_volume": None, "volume_available_at_utc": None},
                                    {"volume_available_at_utc": OPEN}, {"lagged_volume": 0}])
def test_missing_or_future_liquidity_preserves_explicit_pending_zero_exit(changes):
    result = run(cash="0", positions=positions(("NATIVE:A", 20)), frame=target((("NATIVE:A", "0"),)), rows=(bar(**changes),))
    assert result.fills == () and quantities(result) == {"NATIVE:A": 20}
    assert result.orders[0].pending_quantity == 20 and result.complete is False


def test_unmarked_holding_is_not_written_off_and_priced_zero_exit_still_fills():
    frame = target((("NATIVE:A", "0.1"), ("NATIVE:B", "0"), ("NATIVE:C", "0")))
    frame["decision_marks"] = (frame["decision_marks"][0], frame["decision_marks"][2])
    result = run(positions=positions(("NATIVE:B", 2), ("NATIVE:C", 3)), frame=frame, rows=(bar(), bar("NATIVE:C")))
    assert [(f.side, f.security_id, f.quantity) for f in result.fills] == [("sell", "NATIVE:C", 3)]
    assert quantities(result) == {"NATIVE:B": 2}
    assert result.sessions[0].decision_equity is None and result.sessions[0].close_equity is None
    assert result.sessions[0].unpriced_security_ids == ("NATIVE:B",)
    assert result.complete is False


def test_nontradable_zero_exit_remains_held_pending_and_has_explicit_refusal():
    result = run(cash="0", positions=positions(("NATIVE:A", 20)), frame=target((("NATIVE:A", "0"),)), rows=(bar(tradable=False),))
    assert quantities(result) == {"NATIVE:A": 20} and result.fills == ()
    assert result.orders[0].pending_quantity == 20
    assert "nontradable" in {r.reason for r in result.exclusions}


def test_future_decision_mark_does_not_supply_nav_or_buy_quantity():
    frame = target(decision_marks=({"security_id": "NATIVE:A", "price": "10", "available_at_utc": OPEN},))
    result = run(frame=frame)
    assert result.fills == () and result.orders == () and result.complete is False
    assert "decision_mark_after_cutoff" in {r.reason for r in result.exclusions}


@pytest.mark.parametrize("cutoff", [OPEN, "2023-12-01T21:00:00Z", "2024-01-02T21:00:00"])
def test_equal_stale_or_naive_cutoff_refuses(cutoff):
    with pytest.raises(bt.RawBacktestError):
        run(frame=target(cutoff_utc=cutoff))


@pytest.mark.parametrize("field,value", [("open", "NaN"), ("open", "Infinity"), ("open", "0"), ("close", "-1"),
                                         ("open", 10.0), ("lagged_volume", True), ("tradable", 1)])
def test_invalid_bar_primitives_refuse(field, value):
    with pytest.raises(bt.RawBacktestError):
        run(rows=(bar(**{field: value}),))


@pytest.mark.parametrize("weights", [(("NATIVE:A", "0.10001"),), (("NATIVE:A", "-0.1"),), (("NATIVE:A", "NaN"),),
                                     (("NATIVE:A", "0.1"), ("NATIVE:A", "0.1"))])
def test_name_cap_bad_weights_and_duplicates_refuse(weights):
    with pytest.raises(bt.RawBacktestError):
        run(frame=target(weights))


def test_stock_only_identity_inventory_and_explicit_prior_targets_are_required():
    with pytest.raises(bt.RawBacktestError):
        run(security_inventory=({"security_id": "NATIVE:A", "asset_type": "etf"},))
    with pytest.raises(bt.RawBacktestError):
        run(rows=(bar("UNADMITTED"),))
    with pytest.raises(bt.RawBacktestError, match="prior target"):
        run(positions=positions(("NATIVE:B", 1)))


def test_input_values_are_detached_and_caller_decimal_context_cannot_change_results():
    frame, bars = target(), (bar(),)
    before = deepcopy((frame, bars))
    with localcontext() as ctx:
        ctx.prec = 2
        low = run(frame=frame, rows=bars)
    assert low == run(frame=frame, rows=bars)
    assert (frame, bars) == before


def test_duplicate_out_of_order_sessions_and_missing_target_session_refuse():
    first = {"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar(),)}
    with pytest.raises(bt.RawBacktestError):
        run(sessions=(first, first))
    with pytest.raises(bt.RawBacktestError):
        run(frame=target(session_id="MISSING"))


def test_no_automatic_pending_fill_on_later_session_without_new_target():
    first = {"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar(lagged_volume=300),)}
    second = {"session_id": "2024-01-04", "open_utc": "2024-01-04T14:30:00Z", "close_utc": "2024-01-04T21:00:00Z",
              "bars": (bar(open_available_at_utc="2024-01-04T14:30:00Z", close_available_at_utc="2024-01-04T21:00:00Z"),)}
    result = run(sessions=(first, second))
    assert len(result.fills) == 1 and result.fills[0].quantity == 3
    assert result.orders[0].pending_quantity == 6 and result.complete is False


def test_missing_open_mark_on_hold_only_day_retains_unknown_equity_and_incomplete_status():
    first = {"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar(),)}
    second = {"session_id": "2024-01-04", "open_utc": "2024-01-04T14:30:00Z", "close_utc": "2024-01-04T21:00:00Z",
              "bars": (bar(open=None, open_available_at_utc=None, close_available_at_utc="2024-01-04T21:00:00Z"),)}
    result = run(sessions=(first, second))
    assert result.sessions[1].open_equity is None
    assert result.sessions[1].close_equity == "999.82"
    assert result.complete is False
    assert "held_open_mark_missing" in {r.reason for r in result.exclusions}


def test_cash_can_cover_negative_net_dust_sale_without_blocking_risk_reduction():
    result = run(cash="1", positions=positions(("NATIVE:A", 20)), frame=target((("NATIVE:A", "0"),)),
                 rows=(bar(open="0.001", close="0.001"),))
    assert quantities(result) == {} and result.fills[0].quantity == 20
    assert result.final_cash == "0.81998"
    assert result.total_commission == "0.2" and result.total_slippage == "0.00002"


def test_missing_held_execution_mark_freezes_buys_despite_complete_decision_marks():
    frame = target((("NATIVE:A", "0.1"), ("NATIVE:B", "0")))
    result = run(positions=positions(("NATIVE:B", 20)), frame=frame, rows=(bar(),))
    assert result.sessions[0].decision_equity == "1200"
    assert result.sessions[0].open_equity is None
    assert result.fills == () and quantities(result) == {"NATIVE:B": 20}
    assert "incomplete_execution_marks" in {r.reason for r in result.exclusions}


def test_source_identity_separators_cannot_collide_hypothetical_order_ids():
    inventory = tuple({"security_id": sid, "asset_type": "common-stock"} for sid in ("A:B", "B"))
    first = {"session_id": "S", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar("A:B"),)}
    second_open, second_close = "2024-01-04T14:30:00Z", "2024-01-04T21:00:00Z"
    second = {"session_id": "S:A", "open_utc": second_open, "close_utc": second_close,
              "bars": tuple(bar(sid, open_available_at_utc=second_open, close_available_at_utc=second_close) for sid in ("A:B", "B"))}
    first_target = target((("A:B", "0.1"),), session_id="S")
    second_target = target((("A:B", "0"), ("B", "0.1")), session_id="S:A", cutoff_utc=CLOSE,
                           decision_marks=tuple({"security_id": sid, "price": "10", "available_at_utc": CLOSE} for sid in ("A:B", "B")))
    result = run(security_inventory=inventory, sessions=(first, second), targets=(first_target, second_target))
    assert len(result.orders) == 3
    assert len({order.order_id for order in result.orders}) == 3


def test_dust_sale_without_cash_to_cover_commission_remains_pending_not_negative():
    result = run(cash="0", positions=positions(("NATIVE:A", 20)), frame=target((("NATIVE:A", "0"),)),
                 rows=(bar(open="0.001", close="0.001"),))
    assert result.fills == () and quantities(result) == {"NATIVE:A": 20}
    assert result.final_cash == "0" and result.orders[0].pending_quantity == 20


def test_later_target_cutoff_before_previous_close_refuses_even_if_before_open():
    first = {"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar(),)}
    second = {"session_id": "2024-01-04", "open_utc": "2024-01-04T14:30:00Z", "close_utc": "2024-01-04T21:00:00Z",
              "bars": (bar(open_available_at_utc="2024-01-04T14:30:00Z", close_available_at_utc="2024-01-04T21:00:00Z"),)}
    with pytest.raises(bt.RawBacktestError, match="stale"):
        run(sessions=(first, second), targets=(target(), target(session_id="2024-01-04")))


def test_later_outcome_delivery_is_not_misclassified_as_decision_known():
    result = run(rows=(bar(open_available_at_utc="2026-10-07T00:00:00Z", close_available_at_utc="2026-10-07T00:00:00Z"),))
    assert result.fills[0].quantity == 9 and result.point_in_time_data is False
    assert result.sessions[0].close_equity == "999.82"


def test_total_weight_over_one_and_reordered_sessions_refuse():
    inventory = tuple({"security_id": f"NATIVE:{index}", "asset_type": "common-stock"} for index in range(11))
    with pytest.raises(bt.RawBacktestError, match="exceeds one"):
        run(security_inventory=inventory, rows=(), frame=target(tuple((f"NATIVE:{index}", "0.1") for index in range(11))))
    first = {"session_id": "2024-01-03", "open_utc": OPEN, "close_utc": CLOSE, "bars": (bar(),)}
    prior = {"session_id": "2024-01-02", "open_utc": "2024-01-02T14:30:00Z", "close_utc": CUTOFF, "bars": ()}
    with pytest.raises(bt.RawBacktestError, match="chronological"):
        run(sessions=(first, prior))


def test_pure_engine_performs_no_filesystem_network_or_credential_lookup(monkeypatch):
    import builtins
    import os
    import socket
    from pathlib import Path
    def forbidden(*args, **kwargs):
        pytest.fail("pure raw backtest attempted I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert run().fills[0].quantity == 9


def test_unknown_fields_and_custom_primitive_subclasses_refuse_without_callbacks():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("custom equality called")
        __hash__ = str.__hash__
    with pytest.raises(bt.RawBacktestError):
        run(rows=(bar(extra=True),))
    frame = target()
    frame["weights"] = ({"security_id": Evil("NATIVE:A"), "weight": "0.1"},)
    with pytest.raises(bt.RawBacktestError):
        run(frame=frame)
