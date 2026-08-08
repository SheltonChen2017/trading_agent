"""GR-2: the risk-check registry contract (archived plan section 7).

The gate now RUNS an ordered registry of named checks. These tests pin the
plan's four requirements: the frozen inventory (a deleted or reordered
check is loud), registry-driven execution (a registered check runs without
touching the gate's code), original error identity on failure, and the
scatter rule that consolidation must not reduce what runs.

Run with: python -m pytest tests/test_risk_check_registry.py
"""
from __future__ import annotations

import ast
import inspect
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import risk.execution_gate as gate
from assistant.schemas import PortfolioSnapshot
from risk.execution_gate import (
    PRE_SUBMIT_PHASE,
    RISK_CHECK_REGISTRY,
    RiskCheck,
    TradeIntent,
    ViolationCode,
    checks_for_phase,
    validate_trade_intent,
)

# THE frozen inventory: (name, applies_to_side, terminal, phases). Changing
# the gate's checks -- adding, deleting, reordering, re-siding, or
# re-phasing -- MUST arrive together with a reviewed edit of this literal.
# Order is load-bearing: earlier checks derive the sanitized state later
# checks consume, and violation order is caller-visible frozen behavior.
FROZEN_INVENTORY = (
    ("kill_switch", "both", True, ("pre_submit",)),
    ("portfolio_numeric_integrity", "both", False, ("pre_submit",)),
    ("position_data_integrity", "both", False, ("pre_submit",)),
    ("share_quantity", "both", False, ("pre_submit",)),
    ("intent_side", "both", False, ("pre_submit",)),
    ("order_type", "both", False, ("pre_submit",)),
    ("reference_price_and_order_value", "both", False, ("pre_submit",)),
    ("pending_buy_values", "buy", False, ("pre_submit",)),
    ("max_position_pct", "buy", False, ("pre_submit",)),
    ("cash_and_reserve", "buy", False, ("pre_submit",)),
    ("max_total_exposure", "buy", False, ("pre_submit",)),
    ("basket_concentration", "buy", False, ("pre_submit",)),
    ("leveraged_etf_concentration", "buy", False, ("pre_submit",)),
    ("sell_exceeds_held", "non_buy", False, ("pre_submit",)),
    ("price_freshness", "both", False, ("pre_submit",)),
    ("trading_session", "both", False, ("pre_submit",)),
    ("duplicate_order", "both", False, ("pre_submit",)),
    ("limit_price_and_slippage", "both", False, ("pre_submit",)),
    ("bid_ask_quote_and_spread", "both", False, ("pre_submit",)),
    ("earnings_blackout", "both", False, ("pre_submit",)),
)


def _portfolio(**overrides) -> PortfolioSnapshot:
    defaults = dict(
        positions=[],
        cash=100_000.0,
        total_equity=100_000.0,
        as_of="2026-08-03",
        buying_power=100_000.0,
        source="test",
        account_mode="paper",
        account_id="paper-1",
        open_orders=[],
        open_orders_available=True,
    )
    defaults.update(overrides)
    return PortfolioSnapshot(**defaults)


def _intent(**overrides) -> TradeIntent:
    defaults = dict(ticker="AAPL", side="buy", shares=1, order_type="market")
    defaults.update(overrides)
    return TradeIntent(**defaults)


# --- the frozen inventory --------------------------------------------------


def test_registry_matches_the_frozen_inventory_exactly():
    actual = tuple(
        (
            check.name,
            check.applies_to_side,
            check.terminal,
            tuple(sorted(check.applies_at)),
        )
        for check in RISK_CHECK_REGISTRY
    )
    assert actual == FROZEN_INVENTORY, (
        "The risk-check registry changed. If deliberate, update "
        "FROZEN_INVENTORY in the same reviewed change and explain the "
        "risk-coverage consequence; a silent difference here means a check "
        "was added, deleted, reordered, re-sided, or re-phased by accident."
    )


def test_every_check_name_is_unique():
    names = [check.name for check in RISK_CHECK_REGISTRY]
    assert len(names) == len(set(names))


def test_frozen_inventory_binds_each_name_to_its_runner_function():
    """Metadata alone cannot detect two correctly named entries whose
    implementations were accidentally swapped."""
    assert tuple(
        (check.name, check.run.__name__) for check in RISK_CHECK_REGISTRY
    ) == tuple(
        (name, f"_check_{name}") for name, _, _, _ in FROZEN_INVENTORY
    )


def test_pre_submit_phase_runs_the_entire_registry_today():
    assert checks_for_phase(PRE_SUBMIT_PHASE) == RISK_CHECK_REGISTRY


def test_unknown_phase_is_rejected_not_empty():
    with pytest.raises(ValueError):
        checks_for_phase("post_close")


# --- the gate runs the registry, not a hand-written sequence ---------------


def test_a_registered_check_runs_without_touching_the_gate(monkeypatch):
    """The plan's 'adding a risk rule is a one-line registry entry' test:
    append a check to the registry and the gate enforces it with zero gate
    edits -- which is only possible if the gate genuinely iterates the
    registry."""

    def _always_blocks(ctx) -> None:
        ctx.violate(
            ViolationCode.KILL_SWITCH,  # any existing code: identity is per-check
            "registry-injected test check fired",
        )

    injected = RiskCheck(
        name="test_injected_check",
        applies_to_side="both",
        terminal=False,
        applies_at=frozenset({PRE_SUBMIT_PHASE}),
        run=_always_blocks,
    )
    monkeypatch.setattr(
        gate, "RISK_CHECK_REGISTRY", RISK_CHECK_REGISTRY + (injected,)
    )

    result = validate_trade_intent(
        _intent(side="sell", shares=1),
        _portfolio(),
        100.0,
    )

    assert result.approved is False
    assert "registry-injected test check fired" in result.violations


def test_removing_a_check_from_the_registry_removes_its_enforcement(monkeypatch):
    """The dangerous direction the frozen inventory exists to catch: a
    check deleted from the registry silently stops running. This proves the
    inventory test is the ONLY thing standing between deletion and silent
    fail-open, i.e. it is load-bearing."""
    pruned = tuple(
        check for check in RISK_CHECK_REGISTRY if check.name != "sell_exceeds_held"
    )
    monkeypatch.setattr(gate, "RISK_CHECK_REGISTRY", pruned)

    # Selling 5 shares while holding none: blocked by the real registry,
    # silently approved by the pruned one.
    result = validate_trade_intent(_intent(side="sell", shares=5), _portfolio(), 100.0)

    assert result.approved is True  # the check really is gone
    assert (
        ViolationCode.SELL_EXCEEDS_HELD.value
        not in result.violation_codes
    )


# --- error identity and short-circuit semantics ----------------------------


def test_a_failing_check_keeps_its_original_error_identity():
    result = validate_trade_intent(_intent(side="sell", shares=5), _portfolio(), 100.0)
    assert result.approved is False
    assert result.violation_codes == (ViolationCode.SELL_EXCEEDS_HELD.value,)
    assert result.violations == (
        "Sell quantity 5 exceeds the 0 shares currently held.",
    )


def test_kill_switch_is_the_only_terminal_check_and_short_circuits():
    terminals = [check.name for check in RISK_CHECK_REGISTRY if check.terminal]
    assert terminals == ["kill_switch"]

    # Engaged kill switch on an otherwise wildly invalid intent: the
    # historical early return reported ONLY the kill switch.
    result = validate_trade_intent(
        _intent(side="banana", shares=-3),
        _portfolio(cash=float("nan")),
        -1.0,
        kill_switch_active=True,
    )
    assert result.violations == ("Kill switch is active — no trades are permitted.",)
    assert result.violation_codes == (ViolationCode.KILL_SWITCH.value,)


def test_terminal_check_stops_only_when_that_check_adds_a_violation(monkeypatch):
    """A later terminal check that passes must not mistake an earlier
    violation for its own and suppress the checks that follow it."""

    def _passes(ctx) -> None:
        return None

    def _always_blocks(ctx) -> None:
        ctx.violate(ViolationCode.DUPLICATE_ORDER, "later check still ran")

    passing_terminal = RiskCheck(
        name="passing_terminal",
        applies_to_side="both",
        terminal=True,
        applies_at=frozenset({PRE_SUBMIT_PHASE}),
        run=_passes,
    )
    later_check = RiskCheck(
        name="later_check",
        applies_to_side="both",
        terminal=False,
        applies_at=frozenset({PRE_SUBMIT_PHASE}),
        run=_always_blocks,
    )
    monkeypatch.setattr(
        gate,
        "RISK_CHECK_REGISTRY",
        RISK_CHECK_REGISTRY + (passing_terminal, later_check),
    )

    result = validate_trade_intent(
        _intent(side="banana", shares=1),
        _portfolio(),
        100.0,
    )

    assert "later check still ran" in result.violations


def test_invalid_side_still_exercises_the_non_buy_branch():
    """The historical sequence ran the held-shares check in the buy
    branch's `else`, so side='banana' still hit it; 'non_buy' preserves
    that exactly (spelling it 'sell' would have silently skipped it)."""
    result = validate_trade_intent(
        _intent(side="banana", shares=5), _portfolio(), 100.0
    )
    assert ViolationCode.INVALID_SIDE.value in result.violation_codes
    assert ViolationCode.SELL_EXCEEDS_HELD.value in result.violation_codes


# --- scatter rule ----------------------------------------------------------


def test_every_violation_code_used_by_a_check_exists():
    """Every registry check's identity is drawn from ViolationCode; a code
    removed from the enum while a check still references it must be caught
    even when normal inputs do not happen to exercise that function."""
    referenced_members = set()
    for check in RISK_CHECK_REGISTRY:
        tree = ast.parse(inspect.getsource(check.run))
        referenced_members.update(
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ViolationCode"
        )
    assert referenced_members
    assert referenced_members <= set(ViolationCode.__members__)
    # The registry must cover at least every code the historical sequence
    # could emit -- spot-pin the safety-critical ones by name.
    for critical in (
        "kill_switch",
        "portfolio_numeric_integrity",
        "sell_exceeds_held",
        "duplicate_order",
        "earnings_blackout",
    ):
        assert any(check.name == critical for check in RISK_CHECK_REGISTRY)


# --------------------------------------------------------------------------
# FCS-008: pin the mixed unit convention on validate_trade_intent's limits.
#
# Three of the five limit parameters are FRACTIONS the gate multiplies by 100;
# two are already PERCENTS. All five are named `*_pct` and typed `float`, and
# the single caller compensates by hand on exactly two lines. Behavioural
# tests catch the dangerous direction today, but nothing states the convention
# where a new caller would read it -- and GR-2 built
# `checks_for_phase("proposal")` precisely so a second caller would exist.
# --------------------------------------------------------------------------

def test_the_gate_treats_basket_and_leveraged_limits_as_percent():
    """40.0 means 40%, not 4000%."""
    portfolio = _portfolio()
    intent = _intent(shares=10)
    permissive = validate_trade_intent(
        intent, portfolio, 100.0,
        max_basket_pct=40.0, max_leveraged_etf_pct=20.0,
    )
    assert not any(
        "basket concentration limit" in v or "leveraged-ETF limit" in v
        for v in permissive.violations
    ), permissive.violations


def test_the_gate_treats_position_and_exposure_limits_as_fractions():
    """0.05 means 5%; passing 5.0 would be a 500% cap.

    The fail-OPEN direction is the one that matters: a caller copying the
    `* 100` from the basket line onto this parameter turns a 5% per-position
    limit into 500%.
    """
    portfolio = _portfolio()
    intent = _intent(shares=100)  # $10,000 of a $100,000 account == 10%
    over = validate_trade_intent(
        intent, portfolio, 100.0, max_position_pct=0.05,
    )
    assert any("per-position limit" in v for v in over.violations), over.violations
    under = validate_trade_intent(
        intent, portfolio, 100.0, max_position_pct=5.0,
    )
    assert not any("per-position limit" in v for v in under.violations), (
        "max_position_pct=5.0 is a 500% cap. If this ever starts refusing, "
        "the unit convention changed and every caller must be revisited "
        "(FCS-008)"
    )


def test_the_unit_convention_is_documented_at_the_signature():
    """A future caller must meet the convention where the parameters are.

    The two behavioural tests above pin what the gate DOES; this pins that a
    reader is told, because the names (`*_pct` on all five) actively mislead.
    """
    import inspect

    source = inspect.getsource(validate_trade_intent)
    header = source[: source.index(") -> ValidationResult")]
    assert "FCS-008" in header
    assert "max_basket_pct: float = 40.0,  # PERCENT" in header
    assert "max_position_pct: float = MAX_POSITION_PCT,  # fraction" in header
