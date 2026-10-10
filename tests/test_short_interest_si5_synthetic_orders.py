"""Exact software goldens for fixed synthetic SI-5 order/event scenarios.

Private-kernel cases deliberately contain invented prices and corporate actions.
They cannot produce a public fixed-fixture receipt or empirical authority.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import localcontext
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import subprocess

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import SourceEntitlement
from research.short_interest_etf.si5_offline_protocol import SI5_OFFLINE_PROTOCOL
from research.short_interest_etf import si5_synthetic_policy as synthetic_policy
from research.short_interest_etf.si5_synthetic_policy import (
    SI5_SYNTHETIC_POLICY_SHA256,
    synthetic_policy_payload,
)
from research.short_interest_etf import si5_synthetic_orders as synthetic_orders
from research.short_interest_etf.si5_synthetic_orders import (
    SI5_SYNTHETIC_ORDER_FIXTURE_SHA256,
    SI5_SYNTHETIC_ORDER_SCENARIO_ID,
    SI5SyntheticOrderError,
    _SyntheticEvent,
    _SyntheticEventKind,
    _SyntheticScenario,
    _run_synthetic_order_kernel,
    run_si5_synthetic_order_scenario,
)


LONG_ID = "a" * 64
AVOIDED_ID = "b" * 64
DECISION = "2024-01-02T20:00:00Z"
ENTRY = "2024-01-03T14:30:00Z"
MIDDLE = "2024-01-05T14:30:00Z"
LATER = "2024-01-08T14:30:00Z"
EXIT = "2024-01-17T14:30:00Z"
PAY = "2024-01-19T14:30:00Z"


def _amount(payload):
    assert set(payload) == {"numerator", "denominator"}
    assert type(payload["numerator"]) is int
    assert type(payload["denominator"]) is int
    result = Fraction(payload["numerator"], payload["denominator"])
    assert result.numerator == payload["numerator"]
    assert result.denominator == payload["denominator"]
    return result


def _money(result, name):
    return _amount(result[name])


def _assert_closed_positions(result):
    assert result["final_positions"] == []


def _event(event_id, at, kind, *, identity=LONG_ID, **values):
    return _SyntheticEvent(
        event_id=event_id,
        security_identity_sha256=identity,
        at=at,
        kind=kind,
        **values,
    )


def _open(event_id, at, price, *, identity=LONG_ID, **values):
    return _event(
        event_id, at, _SyntheticEventKind.OPEN,
        identity=identity, raw_open_usd=price, **values,
    )


def _scenario(events, *, initial_cash="2000", **values):
    return _SyntheticScenario(
        scenario_id="test-only-private-kernel",
        decision_at=DECISION,
        entry_open_at=ENTRY,
        exit_open_at=EXIT,
        initial_cash_usd=initial_cash,
        long_security_identity_sha256s=(LONG_ID,),
        avoided_security_identity_sha256s=(AVOIDED_ID,),
        events=tuple(events),
        **values,
    )


def _plain_events():
    return (
        _open("entry", ENTRY, "100"),
        _open("exit", EXIT, "110"),
        _open("avoid-entry", ENTRY, "100", identity=AVOIDED_ID),
        _open("avoid-exit", EXIT, "1", identity=AVOIDED_ID),
    )


@pytest.mark.parametrize("cost_bps", [0, 5, 10, 20])
def test_long_cash_ledger_reserves_both_fees_and_never_buys_avoided_tail(cost_bps):
    result = _run_synthetic_order_kernel(_scenario(_plain_events()), cost_bps=cost_bps)
    rate = Fraction(cost_bps, 10000)
    quantity = Fraction(2000, 100) / (1 + rate)
    expected_cash = quantity * 110 * (1 - rate)
    expected_fees = quantity * (100 + 110) * rate

    assert result["complete"] is True
    assert result["refusal_reasons"] == []
    assert _money(result, "initial_cash") == 2000
    assert _money(result, "ending_cash") == expected_cash
    assert _money(result, "total_equity") == expected_cash
    assert _money(result, "total_fees") == expected_fees
    assert _money(result, "realized_pnl") == expected_cash - 2000
    assert _money(result, "net_return") == expected_cash / 2000 - 1
    _assert_closed_positions(result)
    assert len(result["orders"]) == 2
    assert {order["security_identity_sha256"] for order in result["orders"]} == {LONG_ID}
    assert [_amount(order["quantity"]) for order in result["orders"]] == [quantity, quantity]
    assert _amount(result["orders"][0]["notional"]) + _amount(result["orders"][0]["fee"]) == 2000
    assert all(_amount(order["cash_after"]) >= 0 for order in result["orders"])


def test_cost_sensitivities_are_monotone_and_primary_cost_is_not_diagnostic_cost():
    scenario = _scenario(_plain_events())
    cash = [
        _money(_run_synthetic_order_kernel(scenario, cost_bps=value), "ending_cash")
        for value in (0, 5, 10, 20)
    ]
    assert cash[0] > cash[1] > cash[2] > cash[3]
    assert SI5_OFFLINE_PROTOCOL.primary_cost_bps_per_side == 10
    assert SI5_OFFLINE_PROTOCOL.diagnostic_cost_bps_per_side == 0


def test_split_changes_held_quantity_and_preserves_economic_value():
    events = (
        _open("entry", ENTRY, "100"),
        _event("split", MIDDLE, _SyntheticEventKind.SPLIT,
               split_numerator=2, split_denominator=1),
        _open("exit", EXIT, "55"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert [_amount(order["quantity"]) for order in result["orders"]] == [20, 40]
    assert _money(result, "ending_cash") == 2200
    assert _money(result, "realized_pnl") == 200


def test_dividend_entitlement_survives_later_split_and_sale_before_payment():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("split", LATER, _SyntheticEventKind.SPLIT,
               split_numerator=2, split_denominator=1),
        _open("exit", EXIT, "55"),
        _event("pay", PAY, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert _money(result, "dividends_paid") == 100
    assert _money(result, "outstanding_dividend_receivables") == 0
    assert _money(result, "ending_cash") == 2300
    assert _money(result, "total_equity") == 2300
    assert _money(result, "realized_pnl") == 300
    assert len(result["orders"]) == 2


def test_unpaid_positive_entitlement_blocks_complete_financial_comparison():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"unsettled_dividend_receivable:{LONG_ID}:div-1" in result["refusal_reasons"]
    assert result["financial_result"] is None
    for unsupported in (
        "orders", "cashflows", "ending_cash", "total_equity", "realized_pnl", "net_return",
    ):
        assert unsupported not in result


def test_zero_entitlement_without_payment_does_not_create_unsettled_value():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="zero-div", cash_per_share_usd="0"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is True
    assert _money(result, "ending_cash") == 2200
    assert _money(result, "outstanding_dividend_receivables") == 0


def test_fractional_second_payment_before_entitlement_is_atomic_refusal():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", "2024-01-05T14:30:00.000001Z",
               _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("pay", MIDDLE, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"dividend_payment_precedes_entitlement:{LONG_ID}:div-1" in result["refusal_reasons"]
    assert result["financial_result"] is None
    assert "orders" not in result


def test_fractional_second_payment_after_entitlement_settles_locked_cash():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("pay", "2024-01-05T14:30:00.000001Z",
               _SyntheticEventKind.DIVIDEND_PAYMENT, dividend_id="div-1"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is True
    assert _money(result, "dividends_paid") == 100
    assert _money(result, "ending_cash") == 2300


def test_dividend_payment_at_entitlement_instant_is_not_later_payment():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("pay", MIDDLE, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"dividend_payment_not_after_entitlement:{LONG_ID}:div-1" in result["refusal_reasons"]
    assert result["financial_result"] is None
    assert "orders" not in result


def test_same_entry_open_entitlement_and_split_do_not_benefit_new_position():
    events = (
        _event("split", ENTRY, _SyntheticEventKind.SPLIT,
               split_numerator=2, split_denominator=1),
        _event("ex", ENTRY, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _open("entry", ENTRY, "100"),
        _event("pay", LATER, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert [_amount(order["quantity"]) for order in result["orders"]] == [20, 20]
    assert _money(result, "dividends_paid") == 0
    assert _money(result, "ending_cash") == 2200


def test_same_exit_open_entitlement_uses_old_shares_then_exit_uses_split_shares():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", EXIT, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("split", EXIT, _SyntheticEventKind.SPLIT,
               split_numerator=2, split_denominator=1),
        _open("exit", EXIT, "55"),
        _event("pay", PAY, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert _amount(result["orders"][1]["quantity"]) == 40
    assert _money(result, "dividends_paid") == 100
    assert _money(result, "ending_cash") == 2300


@pytest.mark.parametrize("terminal_per_share,ending_cash", [("0", 0), ("50", 1000)])
def test_authenticated_terminal_cash_supports_zero_without_dropping_loss(terminal_per_share, ending_cash):
    events = (
        _open("entry", ENTRY, "100"),
        _event("terminal", MIDDLE, _SyntheticEventKind.TERMINAL_CASH,
               cash_per_share_usd=terminal_per_share),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is True
    assert _money(result, "terminal_cash_paid") == ending_cash
    assert _money(result, "ending_cash") == ending_cash
    assert _money(result, "realized_pnl") == ending_cash - 2000
    assert _money(result, "net_return") == Fraction(ending_cash, 2000) - 1
    _assert_closed_positions(result)
    assert len(result["orders"]) == 1


@pytest.mark.parametrize(
    "events,expected_reason",
    [
        ((_open("exit", EXIT, "110"),), f"missing_entry_open:{LONG_ID}"),
        ((_open("entry", ENTRY, "100"),), f"missing_exit_or_terminal:{LONG_ID}"),
        ((_open("entry", ENTRY, "100", fill_numerator=1, fill_denominator=2),
          _open("exit", EXIT, "110")), "partial_fill_not_supported:entry"),
        ((_open("entry", ENTRY, "100"),
          _event("suspend", MIDDLE, _SyntheticEventKind.SUSPENSION),
          _open("exit", EXIT, "110")), f"suspension:{LONG_ID}"),
        ((_open("entry", ENTRY, "100"),
          _event("unknown-terminal", MIDDLE, _SyntheticEventKind.UNKNOWN_TERMINAL)),
         f"unknown_terminal_cashflow:{LONG_ID}"),
    ],
)
def test_incomplete_execution_has_no_financial_comparison_or_partial_ledger(events, expected_reason):
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=10)
    assert result["complete"] is False
    assert expected_reason in result["refusal_reasons"]
    assert result["refusal_reasons"] == sorted(set(result["refusal_reasons"]))
    assert result["financial_result"] is None
    for unsupported in ("orders", "cashflows", "ending_cash", "realized_pnl", "net_return"):
        assert unsupported not in result


def test_exact_duplicate_event_is_idempotent_and_conflicting_duplicate_refused():
    events = _plain_events()
    original = _run_synthetic_order_kernel(_scenario(events), cost_bps=10)
    duplicated = _run_synthetic_order_kernel(_scenario((*events, events[0])), cost_bps=10)
    assert duplicated == original
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _run_synthetic_order_kernel(
            _scenario((*events, replace(events[0], raw_open_usd="101"))), cost_bps=10
        )


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "-Infinity", 2000, 2000.0, True, Fraction(2000)])
def test_cash_contract_refuses_invalid_or_noncanonical_money(value):
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _run_synthetic_order_kernel(_scenario(_plain_events(), initial_cash=value), cost_bps=10)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", 100, 100.0, True])
def test_fill_price_refuses_zero_negative_nonfinite_or_binary_money(value):
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _run_synthetic_order_kernel(
            _scenario((_open("entry", ENTRY, value), _open("exit", EXIT, "110"))),
            cost_bps=10,
        )


@pytest.mark.parametrize("cost_bps", [-1, 1, 21, 10.0, True])
def test_unfrozen_cost_choice_refused(cost_bps):
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _run_synthetic_order_kernel(_scenario(_plain_events()), cost_bps=cost_bps)


def test_exact_cash_arithmetic_is_independent_of_global_decimal_precision():
    scenario = _scenario(_plain_events(), initial_cash="2000.123456789")
    expected = _run_synthetic_order_kernel(scenario, cost_bps=10)
    with localcontext() as context:
        context.prec = 2
        assert _run_synthetic_order_kernel(scenario, cost_bps=10) == expected


@pytest.mark.parametrize("numerator,denominator", [(0, 1), (-1, 1), (2, 0), (2.0, 1), (True, 1)])
def test_split_ratio_requires_positive_exact_integer_terms(numerator, denominator):
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _event("split", MIDDLE, _SyntheticEventKind.SPLIT,
               split_numerator=numerator, split_denominator=denominator)


@pytest.mark.parametrize("cash", ["-1", "NaN", "Infinity", 0, 1.0])
def test_terminal_payout_allows_real_zero_but_refuses_invalid_amounts(cash):
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        _event("terminal", MIDDLE, _SyntheticEventKind.TERMINAL_CASH,
               cash_per_share_usd=cash)


def test_dividend_payment_without_entitlement_cannot_create_cash():
    events = (
        _open("entry", ENTRY, "100"),
        _event("pay", LATER, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="missing-entitlement"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"orphan_dividend_payment:{LONG_ID}:missing-entitlement" in result["refusal_reasons"]
    assert result["financial_result"] is None


def test_dividend_payment_must_match_locked_entitlement_amount():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("pay", LATER, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1", cash_per_share_usd="6"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"dividend_payment_amount_mismatch:{LONG_ID}:div-1" in result["refusal_reasons"]
    assert result["financial_result"] is None


def test_entitlement_id_cannot_be_paid_twice_under_different_event_ids():
    events = (
        _open("entry", ENTRY, "100"),
        _event("ex", MIDDLE, _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
               dividend_id="div-1", cash_per_share_usd="5"),
        _event("pay-1", LATER, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
        _event("pay-2", PAY, _SyntheticEventKind.DIVIDEND_PAYMENT,
               dividend_id="div-1"),
        _open("exit", EXIT, "110"),
    )
    result = _run_synthetic_order_kernel(_scenario(events), cost_bps=0)
    assert result["complete"] is False
    assert f"ambiguous_dividend_payment:{LONG_ID}:div-1" in result["refusal_reasons"]
    assert result["financial_result"] is None


def test_private_scenario_cannot_claim_licensed_source_or_selected_lookback():
    scenario = _scenario(_plain_events())
    for changes in (
        {"source_id": "licensed-provider-history"},
        {"entitlement": SourceEntitlement.LICENSED_HISTORICAL_VINTAGE},
        {"selected_lookback": 60},
    ):
        with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
            _run_synthetic_order_kernel(replace(scenario, **changes), cost_bps=10)


def test_public_run_accepts_no_external_rows_or_claimed_synthetic_scenario():
    for bad_id in ("external-provider", {}, _scenario(_plain_events()), True):
        with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
            run_si5_synthetic_order_scenario(bad_id)
    with pytest.raises(TypeError):
        run_si5_synthetic_order_scenario(rows=[{"price": "100", "synthetic": True}])


def test_public_fixed_fixture_is_repeatable_and_does_not_amend_empirical_protocol():
    before = SI5_OFFLINE_PROTOCOL.to_payload()
    first = run_si5_synthetic_order_scenario()
    second = run_si5_synthetic_order_scenario(SI5_SYNTHETIC_ORDER_SCENARIO_ID)
    assert first.to_payload() == second.to_payload()
    assert first.sha256 == second.sha256
    assert len(SI5_SYNTHETIC_ORDER_FIXTURE_SHA256) == 64
    assert SI5_OFFLINE_PROTOCOL.to_payload() == before
    assert before["terminal_value_rule"] is None
    assert before["order_cashflow_rule"] is None
    assert before["permanent_look_ids"] == []
    assert before["allocated_alpha"] == {"numerator": 0, "denominator": 1}


def test_public_result_identifies_fixed_fixture_and_all_closed_authority():
    result = run_si5_synthetic_order_scenario()
    payload = result.to_payload()
    assert payload["scenario_id"] == SI5_SYNTHETIC_ORDER_SCENARIO_ID
    assert payload["fixture_sha256"] == SI5_SYNTHETIC_ORDER_FIXTURE_SHA256
    assert payload["primary_cost_bps_per_side"] == 10
    assert payload["cost_sensitivities_bps_per_side"] == [0, 5, 20]
    assert [run["cost_bps_per_side"] for run in payload["cost_runs"]] == [0, 5, 10, 20]
    assert payload["empirical_terminal_value_rule"] is None
    assert payload["empirical_order_cashflow_rule"] is None
    assert payload["synthetic_only"] is True
    assert payload["selected_lookback"] is None
    for field in (
        "actual_source_admitted", "point_in_time_data_verified",
        "outcome_access_authorized", "qc_backtest_authorized",
        "production_authoritative", "trading_authority", "real_backtesting_ready",
    ):
        assert payload[field] is False
    assert payload["authorized_real_outcome_looks"] == 0
    assert payload["consumed_real_outcome_looks"] == 0
    for run in payload["cost_runs"]:
        assert run["complete"] is True
        assert run["source_entitlement"] == "synthetic_fixture_only"
        assert run["source_id"] == "synthetic-si5-order-events-v1"
        assert run["synthetic_only"] is True
        assert run["real_backtesting_ready"] is False
        assert run["authorized_real_outcome_looks"] == 0
        assert run["consumed_real_outcome_looks"] == 0
    assert result.sha256 == hash_payload({
        name: value for name, value in payload.items() if name != "result_sha256"
    })


def test_public_payload_is_deeply_detached_from_authenticated_result():
    result = run_si5_synthetic_order_scenario()
    expected = result.to_payload()
    returned = result.to_payload()
    returned["cost_runs"][0]["orders"].clear()
    returned["cost_runs"][0]["ending_cash"]["numerator"] += 1
    returned["actual_source_admitted"] = True
    assert result.to_payload() == expected


def test_coherently_rehashed_financial_or_authority_tampering_is_refused():
    for change in ("financial", "authority"):
        result = run_si5_synthetic_order_scenario()
        forged = result.to_payload()
        if change == "financial":
            forged["cost_runs"][0]["ending_cash"]["numerator"] += 1
        else:
            forged["actual_source_admitted"] = True
            forged["real_backtesting_ready"] = True
        forged["result_sha256"] = hash_payload({
            name: value for name, value in forged.items() if name != "result_sha256"
        })
        object.__setattr__(result, "_payload_json", canonical_json(forged))
        object.__setattr__(result, "_payload_sha256", forged["result_sha256"])
        with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
            result.to_payload()
        with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
            _ = result.sha256


def test_changed_builtin_fixture_cannot_reuse_its_pinned_identity(monkeypatch):
    changed = replace(synthetic_orders._BUILTIN_SCENARIO, initial_cash_usd="4001")
    monkeypatch.setattr(synthetic_orders, "_BUILTIN_SCENARIO", changed)
    with pytest.raises(SI5SyntheticOrderError, match="pinned digest"):
        run_si5_synthetic_order_scenario()


def test_unconstructed_public_receipt_is_not_authenticated():
    forged = object.__new__(synthetic_orders.SI5SyntheticOrderResult)
    with pytest.raises(SI5SyntheticOrderError, match="authenticated"):
        forged.to_payload()


def test_order_receipt_binds_exact_policy_and_committed_substantive_owner_decisions():
    policy = synthetic_policy_payload()
    assert hash_payload(policy) == SI5_SYNTHETIC_POLICY_SHA256
    source = policy["owner_decision_source"]
    root = Path(__file__).parents[1]
    committed = subprocess.run(
        ["git", "show", f"{source['commit']}:{source['path']}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    assert sha256(committed).hexdigest() == source["sha256"]
    text = committed.decode("utf-8")
    section = text.split("## 92. Owner-directed single continuous build", 1)[1]
    assert '> and by "build towards until project completion or the lane is ready for backtesting", i mean no interruptions. just build in single round until done' in section
    assert "> during the process, consider i preauthorize every move of yours." in section
    for clause in (
        "fixed-fixture-only",
        "fees reserve cash before full raw-open buys/sells",
        "exact rational share/cash arithmetic",
        "dividends locked on pre-ex-open holdings and later cash payment",
        "explicit known terminal payouts including zero",
        "Missing order engine is a genuine software gap",
        "cashflow/terminal fields stay `None`",
        "no winner or power/sample sufficiency inferred",
    ):
        assert clause in section
    for decision_id in source["decision_ids"]:
        assert decision_id in section
    receipt = run_si5_synthetic_order_scenario().to_payload()
    assert receipt["demonstration_policy_sha256"] == SI5_SYNTHETIC_POLICY_SHA256
    assert all(
        run["demonstration_policy_sha256"] == SI5_SYNTHETIC_POLICY_SHA256
        for run in receipt["cost_runs"]
    )


def test_policy_hash_refuses_boolean_to_equal_integer_substitution(monkeypatch):
    changed = synthetic_policy_payload()
    changed["source_admitted"] = 0
    assert changed["source_admitted"] == False
    monkeypatch.setattr(synthetic_policy, "_policy_payload", lambda: changed)
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_policy_payload()
    with pytest.raises(ValueError, match="REFUSED"):
        run_si5_synthetic_order_scenario()


def test_coherently_rehashed_boolean_zero_receipt_tamper_is_refused():
    result = run_si5_synthetic_order_scenario()
    forged = result.to_payload()
    assert forged["actual_source_admitted"] is False
    forged["actual_source_admitted"] = 0
    forged["result_sha256"] = hash_payload({
        name: value for name, value in forged.items() if name != "result_sha256"
    })
    object.__setattr__(result, "_payload_json", canonical_json(forged))
    object.__setattr__(result, "_payload_sha256", forged["result_sha256"])
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        result.to_payload()


def test_mutable_authority_configuration_cannot_admit_public_synthetic_run(monkeypatch):
    drifted = dict(getattr(synthetic_orders, "_ZERO_AUTHORITY", {}))
    drifted["real_backtesting_ready"] = True
    drifted["actual_source_admitted"] = True
    monkeypatch.setattr(synthetic_orders, "_ZERO_AUTHORITY", drifted, raising=False)
    try:
        payload = run_si5_synthetic_order_scenario().to_payload()
    except ValueError as exc:
        assert "REFUSED" in str(exc)
        return
    assert payload["actual_source_admitted"] is False
    assert payload["real_backtesting_ready"] is False
    assert all(run["actual_source_admitted"] is False for run in payload["cost_runs"])
    assert all(run["real_backtesting_ready"] is False for run in payload["cost_runs"])


@pytest.mark.parametrize(
    "constant,drifted",
    [
        ("_PRIMARY_COST_BPS", 5),
        ("_COST_SENSITIVITIES_BPS", (0, 2, 20)),
        ("_ALLOWED_COST_BPS", (0, 5, 10, 20, 30)),
    ],
)
def test_cost_knob_drift_cannot_mint_receipt_under_unchanged_demonstration_policy(
    monkeypatch, constant, drifted
):
    monkeypatch.setattr(synthetic_orders, constant, drifted)
    with pytest.raises(SI5SyntheticOrderError, match="REFUSED"):
        run_si5_synthetic_order_scenario()


def test_public_avoidance_is_proved_with_available_open_rows_and_no_orders():
    scenario = synthetic_orders._BUILTIN_SCENARIO
    avoided = set(scenario.avoided_security_identity_sha256s)
    assert avoided
    for identity in avoided:
        opens = {
            event.at for event in scenario.events
            if event.security_identity_sha256 == identity
            and event.kind is _SyntheticEventKind.OPEN
        }
        assert scenario.entry_open_at in opens
        assert scenario.exit_open_at in opens
    receipt = run_si5_synthetic_order_scenario().to_payload()
    for run in receipt["cost_runs"]:
        assert {order["security_identity_sha256"] for order in run["orders"]}.isdisjoint(avoided)
