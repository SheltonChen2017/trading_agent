"""Pure invented order-transition checks, not a market backtest or real orders."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from research.target_price_revisions_development import simulation as sim
from research.target_price_revisions_development.scoring import (
    TargetResult, TargetWeight, fixture_target_sha256,
)

CUTOFF = "2026-10-05T22:00:00+00:00"
OPEN = "2026-10-06T13:30:00+00:00"


def targets(rows=(("SYNTHETIC-ETF-A", "0.5"), ("SYNTHETIC-ETF-C", "0")), **changes):
    from decimal import Decimal
    weight = sum(Decimal(value) for _, value in rows)
    result = TargetResult(tuple(TargetWeight(sid, value, "bounded_fixture_target" if Decimal(value) else "forced_zero_exit")
                                for sid, value in rows), str(1 - weight), str(weight), "0", CUTOFF, 100)
    return replace(result, **changes)


def portfolio(cash="80", rows=(("SYNTHETIC-ETF-C", 2),)):
    return sim.freeze_fixture_portfolio(cash, tuple({"etf_id": sid, "shares": quantity} for sid, quantity in rows))


def quotes(rows=(("SYNTHETIC-ETF-A", "10"), ("SYNTHETIC-ETF-C", "10"))):
    return {sid: {"price": price, "observed_at_utc": OPEN} for sid, price in rows}


def execute(state=None, target=None, *, fee="0", slippage="0", quote_map=None, **changes):
    state = portfolio() if state is None else state
    target = targets() if target is None else target
    args = dict(quotes=quotes() if quote_map is None else quote_map, open_utc=OPEN,
                open_session_index=101, expected_target_sha256=fixture_target_sha256(target),
                expected_state_sha256=state.sha256, fee_per_order=fee, slippage_bps=slippage, name_cap="0.5")
    args.update(changes)
    return sim.execute_fixture_open(state, target, **args)


def quantities(state):
    return {row.etf_id: row.shares for row in state.positions}


def test_complete_synthetic_transition_sells_first_then_buys_whole_shares():
    result = execute()
    assert [(row.side, row.etf_id, row.shares) for row in result.fills] == [
        ("sell", "SYNTHETIC-ETF-C", 2), ("buy", "SYNTHETIC-ETF-A", 5)]
    assert result.portfolio.cash == "50"
    assert quantities(result.portfolio) == {"SYNTHETIC-ETF-A": 5, "SYNTHETIC-ETF-C": 0}
    assert result.replayed is False and result.real_backtest_ready is False
    assert all(flag is False for _, flag in result.authority)
    with pytest.raises(FrozenInstanceError):
        result.portfolio.cash = "999"


def test_fees_slippage_and_conservative_cost_margin_leave_residual_cash():
    result = execute(fee="1", slippage="100")
    assert result.portfolio.cash == "57.4"
    assert quantities(result.portfolio)["SYNTHETIC-ETF-A"] == 4
    assert [(fill.unit_price, fill.fee) for fill in result.fills] == [("9.9", "1"), ("10.1", "1")]


def test_same_transition_replay_returns_old_receipt_but_no_new_fills():
    first = execute()
    replay = execute(first.portfolio)
    assert replay.replayed is True and replay.fills == ()
    assert replay.portfolio == first.portfolio and replay.receipt == first.receipt


@pytest.mark.parametrize("change", ["price", "fee", "cap", "target"])
def test_changed_inputs_for_same_open_identity_refuse_instead_of_double_fill(change):
    first = execute()
    args = {}
    if change == "price":
        args["quote_map"] = quotes((("SYNTHETIC-ETF-A", "11"), ("SYNTHETIC-ETF-C", "10")))
    elif change == "fee":
        args["fee"] = "1"
    elif change == "cap":
        args["name_cap"] = "0.6"
    else:
        args["target"] = targets((("SYNTHETIC-ETF-A", "0.4"), ("SYNTHETIC-ETF-C", "0")))
    with pytest.raises(sim.FixtureSimulationError, match="inputs changed"):
        execute(first.portfolio, **args)


@pytest.mark.parametrize("kwargs", [
    {"open_utc": CUTOFF}, {"open_session_index": 100}, {"open_session_index": 102},
    {"open_session_index": True}, {"expected_target_sha256": "9" * 64},
    {"expected_state_sha256": "9" * 64},
])
def test_exact_cutoff_session_and_content_bindings_are_required(kwargs):
    with pytest.raises(sim.FixtureSimulationError):
        execute(**kwargs)


def test_missing_mark_prevents_new_risk_but_valid_zero_exit_still_fills():
    state = portfolio(rows=(("SYNTHETIC-ETF-B", 1), ("SYNTHETIC-ETF-C", 2)))
    target = targets((("SYNTHETIC-ETF-A", "0.5"), ("SYNTHETIC-ETF-B", "0.5"), ("SYNTHETIC-ETF-C", "0")))
    result = execute(state, target)
    assert [(fill.side, fill.etf_id) for fill in result.fills] == [("sell", "SYNTHETIC-ETF-C")]
    assert result.portfolio.cash == "100" and quantities(result.portfolio)["SYNTHETIC-ETF-B"] == 1
    assert any(row.reason == "incomplete_portfolio_marks" for row in result.dispositions)


@pytest.mark.parametrize("observed", [CUTOFF, "2026-10-06T13:30:01Z"])
def test_stale_or_future_buy_quote_does_not_block_priced_forced_exit(observed):
    data = quotes()
    data["SYNTHETIC-ETF-A"]["observed_at_utc"] = observed
    result = execute(quote_map=data)
    assert len(result.fills) == 1 and result.fills[0].side == "sell"
    assert quantities(result.portfolio)["SYNTHETIC-ETF-A"] == 0


def test_missing_prior_target_is_not_inferred_as_a_zero_exit():
    with pytest.raises(sim.FixtureSimulationError, match="prior target"):
        execute(target=targets((("SYNTHETIC-ETF-A", "0.5"),)))


def test_explicit_name_cap_and_cash_budget_cannot_be_overrun():
    with pytest.raises(sim.FixtureSimulationError, match="name cap"):
        execute(name_cap="0.4")
    result = execute(portfolio("1", ()), targets((("SYNTHETIC-ETF-A", "0.5"),)),
                     quote_map=quotes((("SYNTHETIC-ETF-A", "1000"),)))
    assert result.fills == () and result.portfolio.cash == "1"


def test_dust_exit_that_cannot_cover_fee_keeps_cash_and_position_nonnegative():
    result = execute(portfolio("1", (("SYNTHETIC-ETF-C", 1),)),
                     targets((("SYNTHETIC-ETF-C", "0"),)), fee="20",
                     quote_map=quotes((("SYNTHETIC-ETF-C", "10"),)))
    assert result.fills == () and result.portfolio.cash == "1"
    assert quantities(result.portfolio)["SYNTHETIC-ETF-C"] == 1
    assert result.dispositions[0].reason == "proceeds_below_fee"


@pytest.mark.parametrize("field,value", [("fee", "-1"), ("fee", True), ("fee", "NaN"),
                                         ("slippage", "10001"), ("slippage", "Infinity")])
def test_nonfinite_float_negative_or_unbounded_fixture_cost_refuses(field, value):
    with pytest.raises(sim.FixtureSimulationError):
        execute(**{field: value})


def test_custom_payload_keys_and_forged_authority_do_not_execute_callbacks():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("caller equality executed")
        __hash__ = str.__hash__
    data = quotes()
    data["SYNTHETIC-ETF-A"][Evil("surprise")] = None
    with pytest.raises(sim.FixtureSimulationError):
        execute(quote_map=data)
    forged = targets(authority=(("canonical_admission", True), ("point_in_time_data", True),
                                ("outcomes", True), ("qc", True), ("trading", True)))
    with pytest.raises(sim.FixtureSimulationError):
        state = portfolio()
        sim.execute_fixture_open(state, forged, quotes=quotes(), open_utc=OPEN, open_session_index=101,
                                 expected_target_sha256=fixture_target_sha256(targets()), expected_state_sha256=state.sha256,
                                 fee_per_order="0", slippage_bps="0", name_cap="0.5")


def test_rehashed_end_state_cannot_change_cash_or_drop_receipt_history():
    first = execute()
    forged = replace(first.portfolio, cash="999")
    with pytest.raises(sim.FixtureSimulationError, match="state"):
        execute(forged)


@pytest.mark.parametrize("field", ["completion", "fill_quantity"])
def test_rehashed_receipt_cannot_substitute_equal_but_wrong_primitive_types(field):
    import hashlib
    import json
    def digest(value):
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        return payload, hashlib.sha256(payload).hexdigest()
    first = execute()
    assert execute(first.portfolio).replayed is True  # clean control
    body = json.loads(first.receipt.payload)
    if field == "completion":
        body["after"]["transition_complete"] = 1  # int != bool in the closed schema
    else:
        body["after"]["fills"][0]["shares"] = 2.0  # float != whole-share int
    payload, receipt_hash = digest(body)
    receipt = sim.FixtureReceipt(payload, receipt_hash)
    state_body = {"schema": "tpr-synthetic-portfolio-v1", "mode": "synthetic-fixture-only",
                  "authority": dict(first.portfolio.authority),
                  "balances": {"cash": first.portfolio.cash,
                               "positions": [{"etf_id": row.etf_id, "shares": row.shares} for row in first.portfolio.positions]},
                  "receipts": [receipt_hash]}
    forged = replace(first.portfolio, receipts=(receipt,), sha256=digest(state_body)[1])
    with pytest.raises(sim.FixtureSimulationError, match="accounting history"):
        execute(forged)


def test_financial_accounting_is_independent_of_callers_decimal_context():
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 2
        result = execute(fee="1", slippage="100")
    assert result.portfolio.cash == "57.4"


def test_transition_has_no_file_network_or_order_side_effect(monkeypatch):
    import builtins
    import io
    import os
    import socket
    def refuse(*args, **kwargs):
        pytest.fail("I/O attempted")
    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    assert execute().real_backtest_ready is False


@pytest.mark.parametrize("cash,rows", [
    ("-1", ()), ("NaN", ()), (1.0, ()),
    ("1", (("SYNTHETIC-ETF-C", True),)), ("1", (("SYNTHETIC-ETF-C", -1),)),
    ("1", (("AAPL", 1),)), ("1", (("SYNTHETIC-ETF-C", 1), ("SYNTHETIC-ETF-C", 2))),
])
def test_initial_fixture_balances_refuse_nonfinite_nonwhole_or_real_identity(cash, rows):
    with pytest.raises(sim.FixtureSimulationError):
        portfolio(cash, rows)


def test_small_cash_and_multiple_buy_targets_cannot_overdraw_or_create_fractional_shares():
    target = targets((("SYNTHETIC-ETF-A", "0.5"), ("SYNTHETIC-ETF-B", "0.5")))
    result = execute(portfolio("5", ()), target, fee="1", slippage="100",
                     quote_map=quotes((("SYNTHETIC-ETF-A", "2"), ("SYNTHETIC-ETF-B", "2"))))
    assert result.portfolio.cash == "5" and result.fills == ()
    assert all(type(row.shares) is int and row.shares >= 0 for row in result.portfolio.positions)


def test_priced_positive_target_reduction_executes_without_new_risk():
    result = execute(portfolio("0", (("SYNTHETIC-ETF-A", 10),)),
                     targets((("SYNTHETIC-ETF-A", "0.25"),)), quote_map=quotes((("SYNTHETIC-ETF-A", "10"),)))
    assert [(row.side, row.shares) for row in result.fills] == [("sell", 8)]
    assert result.portfolio.cash == "80" and quantities(result.portfolio)["SYNTHETIC-ETF-A"] == 2


def test_quote_and_target_reordering_cannot_create_a_second_fill():
    first = execute()
    reordered = dict(reversed(list(quotes().items())))
    replay = execute(first.portfolio, quote_map=reordered)
    assert replay.replayed is True and replay.fills == ()
    changed_target_order = replace(targets(), targets=tuple(reversed(targets().targets)))
    with pytest.raises(sim.FixtureSimulationError, match="inputs changed"):
        execute(first.portfolio, changed_target_order)


def test_exact_fraction_transition_matches_independent_cash_conservation_oracle():
    from decimal import Decimal
    from fractions import Fraction
    result = execute(fee="1", slippage="100")
    expected = Fraction(80)
    shares = {"SYNTHETIC-ETF-C": 2}
    for row in result.fills:
        cost = row.shares * Fraction(Decimal(row.unit_price))
        fee = Fraction(Decimal(row.fee))
        expected += cost - fee if row.side == "sell" else -cost - fee
        shares[row.etf_id] = shares.get(row.etf_id, 0) + (row.shares if row.side == "buy" else -row.shares)
        assert expected >= 0 and shares[row.etf_id] >= 0
    assert Fraction(Decimal(result.portfolio.cash)) == expected
    assert quantities(result.portfolio) == shares


def test_history_is_monotone_and_bounded_without_terminal_replay_side_effects():
    from datetime import datetime, timedelta
    state = portfolio("100", ())
    for offset in range(sim.MAX_TRANSITIONS):
        opened = (datetime.fromisoformat(OPEN) + timedelta(days=offset)).isoformat()
        cutoff = (datetime.fromisoformat(CUTOFF) + timedelta(days=offset)).isoformat()
        target = targets((("SYNTHETIC-ETF-A", "0.5"),), cutoff_utc=cutoff, decision_session_index=100 + offset)
        data = {"SYNTHETIC-ETF-A": {"price": "10", "observed_at_utc": opened}}
        result = execute(state, target, quote_map=data, open_utc=opened, open_session_index=101 + offset)
        state = result.portfolio
        assert len(state.receipts) == offset + 1
    replay = execute(state, target, quote_map=data, open_utc=opened, open_session_index=101 + offset)
    assert replay.replayed is True and replay.fills == () and replay.portfolio == state
    next_open = (datetime.fromisoformat(OPEN) + timedelta(days=sim.MAX_TRANSITIONS)).isoformat()
    next_cutoff = (datetime.fromisoformat(CUTOFF) + timedelta(days=sim.MAX_TRANSITIONS)).isoformat()
    next_target = targets((("SYNTHETIC-ETF-A", "0.5"),), cutoff_utc=next_cutoff, decision_session_index=100 + sim.MAX_TRANSITIONS)
    with pytest.raises(sim.FixtureSimulationError, match="history resource bound"):
        execute(state, next_target, quote_map={"SYNTHETIC-ETF-A": {"price": "10", "observed_at_utc": next_open}},
                open_utc=next_open, open_session_index=101 + sim.MAX_TRANSITIONS)
    with pytest.raises(sim.FixtureSimulationError, match="earlier"):
        execute(state, targets((("SYNTHETIC-ETF-A", "0.5"),)), quote_map=quotes((("SYNTHETIC-ETF-A", "10"),)))


def test_a_hash_correct_deeply_nested_receipt_is_a_named_refusal():
    import hashlib
    payload = ("[" * 30000 + "0" + "]" * 30000 + "\n").encode()
    receipt = sim.FixtureReceipt(payload, hashlib.sha256(payload).hexdigest())
    state = replace(portfolio(), receipts=(receipt,))
    with pytest.raises(sim.FixtureSimulationError):
        execute(state)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), "\ud800"])
def test_hash_correct_nonfinite_or_unencodable_receipt_is_a_named_refusal(invalid):
    import hashlib
    import json
    first = execute()
    body = json.loads(first.receipt.payload)
    body["after"]["dispositions"][0]["reason"] = invalid
    # Deliberately malformed wire primitives, bounded and still hash-correct.
    payload = (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    assert len(payload) < sim.MAX_RECEIPT_BYTES
    receipt = sim.FixtureReceipt(payload, hashlib.sha256(payload).hexdigest())
    state = replace(first.portfolio, receipts=(receipt,))
    with pytest.raises(sim.FixtureSimulationError, match="receipt JSON"):
        execute(state)
