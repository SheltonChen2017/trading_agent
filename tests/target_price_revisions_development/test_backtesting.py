"""Multi-session invented accounting; never market-return or QC evidence."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json

import pytest

from research.target_price_revisions_development import backtesting as backtest
from research.target_price_revisions_development import simulation as sim
from research.target_price_revisions_development.scoring import TargetResult, TargetWeight


def fixture_step(offset, weight="0.5", *, old=True):
    cutoff = (datetime.fromisoformat("2026-10-05T22:00:00+00:00") + timedelta(days=offset)).isoformat()
    opened = (datetime.fromisoformat("2026-10-06T13:30:00+00:00") + timedelta(days=offset)).isoformat()
    rows = (TargetWeight("SYNTHETIC-ETF-A", weight,
                         "bounded_fixture_target" if Decimal(weight) else "forced_zero_exit"),)
    if old:
        rows += (TargetWeight("SYNTHETIC-ETF-OLD", "0", "forced_zero_exit"),)
    target = TargetResult(rows, str(1 - Decimal(weight)), weight, "0", cutoff, 100 + offset)
    return {"target": target,
            "quotes": {row.etf_id: {"price": "10", "observed_at_utc": opened} for row in rows},
            "open_utc": opened, "open_session_index": 101 + offset}


def initial():
    return sim.freeze_fixture_portfolio("80", ({"etf_id": "SYNTHETIC-ETF-OLD", "shares": 2},))


def run(steps=None, state=None, **changes):
    state = initial() if state is None else state
    steps = (fixture_step(0), fixture_step(1, "0.2"), fixture_step(2, "0")) if steps is None else steps
    args = {"expected_initial_sha256": state.sha256, "fee_per_order": "0", "slippage_bps": "0", "name_cap": "0.5"}
    args.update(changes)
    return backtest.run_fixture_backtest(state, steps, **args)


def body(report):
    return json.loads(report.payload)


def rehash(report, value):
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    return replace(report, payload=payload, sha256=hashlib.sha256(payload).hexdigest())


def test_three_session_accounting_buys_then_reduces_then_exits():
    report = run()
    value = body(report)
    assert value["schema"] == "tpr-synthetic-order-backtest-v1"
    assert value["software_completed"] is True and value["status"] == "COMPLETED"
    assert value["totals"] == {"sessions": 3, "complete_sessions": 3, "refused_sessions": 0,
                              "fills": 4, "buy_fills": 1, "sell_fills": 3,
                              "fees": "0", "slippage_cost": "0"}
    assert report.terminal_state.cash == "100"
    assert all(row.shares == 0 for row in report.terminal_state.positions)
    assert [row["receipt"]["after"]["fills"] for row in value["sessions"]] == [
        [{"side": "sell", "etf_id": "SYNTHETIC-ETF-OLD", "shares": 2, "unit_price": "10", "fee": "0"},
         {"side": "buy", "etf_id": "SYNTHETIC-ETF-A", "shares": 5, "unit_price": "10", "fee": "0"}],
        [{"side": "sell", "etf_id": "SYNTHETIC-ETF-A", "shares": 3, "unit_price": "10", "fee": "0"}],
        [{"side": "sell", "etf_id": "SYNTHETIC-ETF-A", "shares": 2, "unit_price": "10", "fee": "0"}],
    ]
    assert backtest.verify_fixture_backtest(report, expected_report_sha256=report.sha256) == report


def test_fills_costs_and_balances_match_independent_exact_cash_oracle():
    report = run(fee_per_order="1", slippage_bps="100")
    cash, fees, slip = Fraction(80), Fraction(0), Fraction(0)
    shares = {"SYNTHETIC-ETF-OLD": 2}
    for session in body(report)["sessions"]:
        for fill in session["receipt"]["after"]["fills"]:
            value = Fraction(Decimal(fill["unit_price"])) * fill["shares"]
            fee = Fraction(Decimal(fill["fee"]))
            cash += value - fee if fill["side"] == "sell" else -value - fee
            shares[fill["etf_id"]] = shares.get(fill["etf_id"], 0) + (fill["shares"] if fill["side"] == "buy" else -fill["shares"])
            fees += fee
            slip += abs(Fraction(10) - Fraction(Decimal(fill["unit_price"]))) * fill["shares"]
            assert cash >= 0 and shares[fill["etf_id"]] >= 0
    assert Fraction(Decimal(report.terminal_state.cash)) == cash
    assert Fraction(Decimal(body(report)["totals"]["fees"])) == fees
    assert Fraction(Decimal(body(report)["totals"]["slippage_cost"])) == slip


def test_report_is_immutable_hash_stable_and_context_independent():
    steps = (fixture_step(0), fixture_step(1, "0.2"), fixture_step(2, "0"))
    first = run(steps)
    with localcontext() as context:
        context.prec = 2
        second = run(steps)
    assert first == second and first.sha256 == hashlib.sha256(first.payload).hexdigest()
    steps[0]["quotes"]["SYNTHETIC-ETF-A"]["price"] = "999"
    assert body(first)["sessions"][0]["receipt"]["inputs"]["quotes"][0]["price"] == "10"
    with pytest.raises(FrozenInstanceError):
        first.sha256 = "0" * 64
    assert backtest.verify_fixture_backtest(first, expected_report_sha256=first.sha256) == first


def test_quote_dictionary_order_does_not_change_report_hash():
    steps = (fixture_step(0), fixture_step(1, "0.2"))
    baseline = run(steps)
    for step in steps:
        step["quotes"] = dict(reversed(tuple(step["quotes"].items())))
    assert run(steps) == baseline


def test_later_execution_price_cannot_rewrite_earlier_target_or_receipt():
    steps = (fixture_step(0), fixture_step(1, "0.2"), fixture_step(2, "0"))
    baseline = body(run(steps))
    steps[-1]["quotes"]["SYNTHETIC-ETF-A"]["price"] = "12"
    changed = body(run(steps))
    assert changed["sessions"][:2] == baseline["sessions"][:2]
    assert changed["sessions"][-1]["decision_target_sha256"] == baseline["sessions"][-1]["decision_target_sha256"]
    assert changed["sessions"][-1]["receipt_sha256"] != baseline["sessions"][-1]["receipt_sha256"]


@pytest.mark.parametrize("observed", [None, "2026-10-05T22:00:00+00:00", "2026-10-06T13:30:01+00:00"])
def test_missing_stale_or_future_mark_is_retained_and_priced_zero_exit_survives(observed):
    step = fixture_step(0)
    if observed is None:
        del step["quotes"]["SYNTHETIC-ETF-A"]
    else:
        step["quotes"]["SYNTHETIC-ETF-A"]["observed_at_utc"] = observed
    report = run((step,))
    value = body(report)
    assert value["software_completed"] is True and value["status"] == "COMPLETED_WITH_REFUSALS"
    assert value["totals"]["refused_sessions"] == 1
    assert value["sessions"][0]["transition_complete"] is False
    assert [(row["side"], row["etf_id"]) for row in value["sessions"][0]["receipt"]["after"]["fills"]] == [
        ("sell", "SYNTHETIC-ETF-OLD")]
    assert report.terminal_state.cash == "100"
    assert backtest.verify_fixture_backtest(report, expected_report_sha256=report.sha256) == report


def test_refused_session_is_not_dropped_when_later_session_completes():
    first = fixture_step(0)
    del first["quotes"]["SYNTHETIC-ETF-A"]
    report = run((first, fixture_step(1, "0.2")))
    value = body(report)
    assert value["totals"]["sessions"] == 2
    assert value["totals"]["complete_sessions"] == value["totals"]["refused_sessions"] == 1
    assert value["status"] == "COMPLETED_WITH_REFUSALS"


@pytest.mark.parametrize("change", ["equal_cutoff", "earlier_cutoff", "duplicate_open", "backward_open", "bool_session"])
def test_decisions_cannot_precede_prior_execution_or_replay_as_new_sessions(change):
    first, second = fixture_step(0), fixture_step(1, "0.2")
    if change == "equal_cutoff":
        second["target"] = replace(second["target"], cutoff_utc=first["open_utc"])
    elif change == "earlier_cutoff":
        second["target"] = replace(second["target"], cutoff_utc=first["target"].cutoff_utc)
    elif change == "duplicate_open":
        second = first.copy()
    elif change == "backward_open":
        first, second = second, first
    else:
        second["open_session_index"] = True
    with pytest.raises(backtest.FixtureBacktestError):
        run((first, second))


def test_checkpoint_resume_is_exact_but_does_not_grant_durable_custody():
    first = run((fixture_step(0),))
    resumed = run((fixture_step(1, "0.2"), fixture_step(2, "0")), first.terminal_state)
    assert resumed.terminal_state == run().terminal_state
    assert body(resumed)["initial_checkpoint"]["sha256"] == first.terminal_state.sha256
    assert body(resumed)["custody"] == "supplied-memory-only-not-protected-durable-custody"
    assert backtest.verify_fixture_backtest(resumed, expected_report_sha256=resumed.sha256) == resumed
    with pytest.raises(backtest.FixtureBacktestError):
        run((fixture_step(0),), first.terminal_state)


@pytest.mark.parametrize("boundary", ["earlier", "equal"])
def test_resume_cutoff_guard_is_not_masked_by_replay(boundary):
    original = fixture_step(0)
    completed = run((original,))
    later = fixture_step(1, "0.2")
    cutoff = original["target"].cutoff_utc if boundary == "earlier" else original["open_utc"]
    later["target"] = replace(later["target"], cutoff_utc=cutoff)
    # Open and index remain a genuinely later, otherwise valid transition.
    # Repeating the old open would test replay, not this resume timing gate.
    with pytest.raises(backtest.FixtureBacktestError, match="checkpoint open"):
        run((later,), completed.terminal_state)


def test_exact_32_transition_bound_preserves_resume_capacity():
    state = sim.freeze_fixture_portfolio("100", ())
    steps = tuple(fixture_step(index, "0", old=False) for index in range(32))
    whole = run(steps, state)
    assert body(whole)["totals"]["sessions"] == 32
    assert len(whole.terminal_state.receipts) == 32
    prefix = run(steps[:31], state)
    terminal = run(steps[31:], prefix.terminal_state)
    assert terminal.terminal_state == whole.terminal_state
    with pytest.raises(backtest.FixtureBacktestError, match="bounded"):
        run((fixture_step(32, "0", old=False),), terminal.terminal_state)


def test_resume_refuses_corrupt_initial_history_and_missing_prior_target():
    prefix = run((fixture_step(0),))
    forged = replace(prefix.terminal_state, cash="999")
    with pytest.raises(backtest.FixtureBacktestError, match="state"):
        run((fixture_step(1, "0.2"),), forged)
    with pytest.raises(backtest.FixtureBacktestError, match="prior target"):
        run((fixture_step(1, "0.2", old=False),), prefix.terminal_state)


@pytest.mark.parametrize("initial_hash", ["0" * 64, None, True, "xyz"])
def test_initial_checkpoint_requires_exact_primitive_content_hash(initial_hash):
    with pytest.raises(backtest.FixtureBacktestError):
        run(expected_initial_sha256=initial_hash)


@pytest.mark.parametrize("steps", [(), [], (fixture_step(0),) * 33, (None,), ({"surprise": True},)])
def test_step_collection_and_schema_are_closed_and_bounded(steps):
    with pytest.raises(backtest.FixtureBacktestError):
        run(steps)


def test_custom_key_types_do_not_invoke_caller_equality():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("caller equality was invoked")
        __hash__ = str.__hash__
    step = fixture_step(0)
    step[Evil("extra")] = None
    with pytest.raises(backtest.FixtureBacktestError):
        run((step,))


@pytest.mark.parametrize("field,value", [("fee_per_order", True), ("slippage_bps", "NaN"), ("name_cap", "0.4")])
def test_invalid_cost_or_cap_does_not_enter_accounting(field, value):
    with pytest.raises(backtest.FixtureBacktestError):
        run(**{field: value})


@pytest.mark.parametrize("mutation", ["complete", "fees", "fill", "receipt", "target", "counter", "extra"])
def test_rehashed_report_truth_is_independently_recomputed(mutation):
    clean = run()
    assert backtest.verify_fixture_backtest(clean, expected_report_sha256=clean.sha256) == clean
    value = body(clean)
    if mutation == "complete":
        value["software_completed"] = 1
    elif mutation == "fees":
        value["totals"]["fees"] = "999"
    elif mutation == "fill":
        value["sessions"][0]["receipt"]["after"]["fills"][0]["shares"] = 2.0
    elif mutation == "receipt":
        value["sessions"][0]["receipt_sha256"] = "0" * 64
    elif mutation == "target":
        value["sessions"][0]["decision_target_sha256"] = "0" * 64
    elif mutation == "counter":
        value["external_access"]["qc_attempts"] = 1
    else:
        value["unexpected"] = True
    forged = rehash(clean, value)
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


def test_report_verification_checks_supplied_identity_and_terminal_portfolio():
    report = run()
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(report, expected_report_sha256="0" * 64)
    forged = replace(report, terminal_state=replace(report.terminal_state, cash="999"))
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


@pytest.mark.parametrize("field", ["authority", "positions", "receipts", "position_object"])
def test_terminal_checkpoint_rejects_equal_but_wrong_types(field):
    clean = run()
    state = clean.terminal_state
    if field == "authority":
        state = replace(state, authority=tuple((key, 0) for key, _ in state.authority))
    elif field == "positions":
        state = replace(state, positions=list(state.positions))
    elif field == "receipts":
        state = replace(state, receipts=list(state.receipts))
    else:
        class ForgedPosition:
            etf_id = state.positions[0].etf_id
            shares = state.positions[0].shares
        state = replace(state, positions=(ForgedPosition(),) + state.positions[1:])
    forged = replace(clean, terminal_state=state)
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


def test_terminal_custom_literal_does_not_execute_equality_callback():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("terminal equality callback executed")
        def __ne__(self, other):
            pytest.fail("terminal equality callback executed")
    clean = run()
    forged = replace(clean, terminal_state=replace(clean.terminal_state, mode=Evil("synthetic-fixture-only")))
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


@pytest.mark.parametrize("malformed", [b"[" * 30000 + b"0" + b"]" * 30000 + b"\n", b"NaN\n"])
def test_hash_correct_malformed_report_is_named_refusal(malformed):
    clean = run()
    forged = replace(clean, payload=malformed, sha256=hashlib.sha256(malformed).hexdigest())
    with pytest.raises(backtest.FixtureBacktestError):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


def test_report_payload_resource_bound_refuses_before_json_parser(monkeypatch):
    clean = run()
    huge = b"x" * (backtest.MAX_REPORT_BYTES + 1)
    forged = replace(clean, payload=huge, sha256=hashlib.sha256(huge).hexdigest())
    def refuse(*args, **kwargs):
        pytest.fail("oversized report reached parser")
    monkeypatch.setattr(backtest.json, "loads", refuse)
    with pytest.raises(backtest.FixtureBacktestError, match="bounded"):
        backtest.verify_fixture_backtest(forged, expected_report_sha256=forged.sha256)


def test_completed_synthetic_accounting_cannot_create_market_authority():
    value = body(run())
    assert value["mode"] == "synthetic-fixture-only" and value["real_backtest_ready"] is False
    assert all(flag is False for flag in value["authority"].values())
    assert all(type(count) is int and count == 0 for count in value["external_access"].values())
    assert value["context"]["role"] == "committed-aggregate-context-only-not-source-admission"
    assert not {"return", "returns", "alpha", "sharpe", "confidence", "market_performance"} & set(value)


def test_runner_and_verifier_do_not_read_files_network_or_operator_state(monkeypatch):
    import builtins
    import io
    import os
    import socket
    state, steps = initial(), (fixture_step(0), fixture_step(1, "0.2"))
    def refuse(*args, **kwargs):
        pytest.fail("external I/O attempted")
    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (socket, "socket"), (os, "getenv")):
        monkeypatch.setattr(module, name, refuse)
    report = run(steps, state)
    assert backtest.verify_fixture_backtest(report, expected_report_sha256=report.sha256) == report
