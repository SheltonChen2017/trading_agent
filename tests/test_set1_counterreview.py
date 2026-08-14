"""Counter-review of the SET-1 fractional-share path (Codex `89156b7`).

Four findings, each with the dangerous direction it protects:

* SET1CR-001 -- the whole-share floor makes a real holding unsellable. A
  0.5-share position vanished from Discrete Selling entirely, and a 10.5-share
  position reported "10 whole share(s)" as if that were the holding. Stock the
  owner actually owns must never silently disappear from the page that sells
  it, and a conservative safeguard must never obstruct a risk-reducing sell
  without naming the way out.
* SET1CR-002 -- the quantity authority bounded PRECISION but not MAGNITUDE, so
  `1E+1000` was "valid" and became a 1001-digit integer in durable proposal
  JSON.
* SET1CR-003 -- an unreadable quantity was replaced with `Decimal("0")`, which
  is integral, which silently skipped the broker fractionable check.
* SET1CR-004 -- `Decimal(intent.shares)` became a bare string conversion once
  quantities travelled as text; it accepts "NaN"/"Infinity" and raises
  ArithmeticError rather than ValueError.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.policy import TradingPolicy
from risk.execution_gate import (
    MAX_ORDER_QUANTITY,
    canonical_order_quantity,
    order_quantity_decimal,
)


def _policy(**overrides):
    base = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=50_000.0,
    )
    base.update(overrides)
    return TradingPolicy(**base)


# --- SET1CR-002: magnitude bound ------------------------------------------


@pytest.mark.parametrize("mode", [True, False])
def test_absurd_magnitude_is_refused_in_both_modes(mode):
    """Precision alone was not enough: 1E+1000 has ZERO decimal places, so it
    passed the nine-decimal rule and was accepted as a real quantity."""
    assert order_quantity_decimal("1E+1000", whole_shares_only=mode) is None
    assert canonical_order_quantity("1E+1000", whole_shares_only=mode) is None


def test_a_huge_plain_int_is_refused_in_strict_mode():
    """Strict mode reaches the bound by a different branch (`int` via
    is_valid_share_quantity), so the rule has to hold on both sides or the
    stricter mode would be the permissive one."""
    assert order_quantity_decimal(10**40, whole_shares_only=True) is None


def test_the_bound_itself_is_still_usable():
    """A bound that also refuses ordinary quantities would be its own bug."""
    assert order_quantity_decimal(1, whole_shares_only=True) == Decimal(1)
    assert order_quantity_decimal(int(MAX_ORDER_QUANTITY), whole_shares_only=True) is not None
    assert order_quantity_decimal("0.5", whole_shares_only=False) == Decimal("0.5")


def test_sizing_and_the_gate_share_one_bound():
    """SET1CR-002 consolidated two copies of this rule. If they drift, a
    dollar amount could size a quantity the gate then refuses."""
    from assistant import discrete_trade

    assert discrete_trade._MAX_SIZABLE_SHARES == MAX_ORDER_QUANTITY


# --- SET1CR-001: the stranded holding -------------------------------------


def _packet(positions):
    from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
    from assistant.schemas import DecisionPacket, MarketRegime

    snapshot = build_portfolio_snapshot(positions, cash=10_000.0)
    return DecisionPacket(
        generated_at="2026-08-14T15:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-13",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def test_a_sub_one_share_holding_names_the_remedy_instead_of_just_refusing():
    """The acute case: the owner holds 0.5 shares and strict mode floors the
    sellable quantity to 0. Refusing is defensible; refusing WITHOUT saying
    the holding is real and how to release it is not."""
    from assistant.user_directed_sell import generate_user_directed_sell_proposal

    result = generate_user_directed_sell_proposal(
        _packet([{
            "ticker": "NVDA", "shares": "0.5",
            "current_price": 100.0, "entry_price": 90.0,
        }]),
        _policy(whole_shares_only=True),
        ticker="NVDA",
        shares=1,
    )
    assert result["created"] is False
    reason = result["reason"]
    assert "Whole shares only" in reason, reason
    assert "Settings & Features" in reason, reason


def test_the_remedy_is_not_offered_when_it_would_not_help():
    """A genuinely empty/unusable holding must not be told to flip a setting
    that changes nothing -- that would be advice the app cannot honour."""
    from assistant.user_directed_sell import generate_user_directed_sell_proposal

    result = generate_user_directed_sell_proposal(
        _packet([{
            "ticker": "NVDA", "shares": "2",
            "current_price": 100.0, "entry_price": 90.0,
        }]),
        _policy(whole_shares_only=True),
        ticker="MSFT",  # not held at all
        shares=1,
    )
    assert result["created"] is False
    assert "Settings & Features" not in result["reason"]


def test_fractional_mode_can_actually_close_the_stranded_position():
    """The remedy the refusal advertises must genuinely work, or the message
    is worse than silence."""
    from assistant.user_directed_sell import generate_user_directed_sell_proposal

    result = generate_user_directed_sell_proposal(
        _packet([{
            "ticker": "NVDA", "shares": "0.5",
            "current_price": 100.0, "entry_price": 90.0,
        }]),
        _policy(whole_shares_only=False),
        ticker="NVDA",
        shares="0.5",
    )
    assert result["created"] is True, result.get("reason")


# --- SET1CR-003 / SET1CR-004: fail-closed conversions ---------------------


def test_budget_notional_refuses_a_non_finite_quantity():
    """SET1CR-004: 'NaN' is valid Decimal SYNTAX. A bare conversion accepted
    it and poisoned the daily budget reservation."""
    from assistant.execution_kernel.submit import _execution_budget_notional
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="NVDA", side="buy", shares="NaN", order_type="market")
    with pytest.raises(ValueError):
        _execution_budget_notional(intent, 100.0)


def test_budget_notional_still_computes_a_valid_fractional_quantity():
    from assistant.execution_kernel.submit import _execution_budget_notional
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="NVDA", side="buy", shares="0.5", order_type="market")
    assert _execution_budget_notional(intent, 100.0) == Decimal("50.0")


def test_the_durable_path_refuses_an_unreadable_quantity_upstream(tmp_path):
    """SET1CR-003 reachability, recorded honestly.

    The branch this finding is about substituted ``Decimal("0")`` on a failed
    conversion, which is integral, which silently skipped the fractionable
    check below it. That substitution is a banned pattern and is now a
    refusal -- but it is NOT reachable through a durable proposal, because
    the stored-intent parser rejects the quantity first. This test pins the
    upstream refusal that makes it unreachable, so that if that parser is
    ever loosened, the loosening is what fails here rather than a silently
    re-enabled skip deeper in the path.
    """
    import dataclasses

    from assistant import execution_service
    from assistant.policy import compute_policy_fingerprint, load_policy
    from assistant.storage import AssistantStore
    from tests.test_execution_characterization import (
        NOW_ET,
        BrokerRecorder,
        _held_portfolio,
        _proposal,
        patched_broker,
    )

    permissive = dataclasses.replace(load_policy(), whole_shares_only=False)
    store = AssistantStore(tmp_path / "set1cr.db")
    proposal = _proposal(
        "p-set1cr-003", side="sell", intent_overrides={"shares": "NaN"}
    )
    proposal["policy_fingerprint"] = compute_policy_fingerprint(permissive)
    store.save_proposal(proposal)

    recorder = BrokerRecorder(
        is_configured=True,
        assert_account_and_asset_ready={
            "account": {"account_id": "paper-account-1", "paper": True, "status": "ACTIVE"},
            "asset": {"symbol": "AAPL", "status": "active", "tradable": True,
                      "fractionable": False},
        },
        get_latest_quote={
            "ticker": "AAPL", "price": 100.0, "price_decimal": "100.00",
            "bid": 99.99, "ask": 100.01,
            "bid_decimal": "99.99", "ask_decimal": "100.01",
            "timestamp": NOW_ET,
        },
    )
    with patched_broker(recorder):
        outcome = execution_service.validate_proposal_for_execution(
            "p-set1cr-003", _held_portfolio(), permissive, store, now_et=NOW_ET,
        )

    assert outcome.error is not None
    assert "Malformed stored intent" in outcome.error, outcome.error
    assert outcome.failure_class == "data_integrity"


def test_the_fractionable_skip_is_no_longer_reachable_by_substituted_zero():
    """The structural half of SET1CR-003: the guard itself.

    Behaviour cannot reach this branch (see the test above), so the property
    under review is the SHAPE of the handler -- a narrow refusal rather than
    a broad `except Exception` that manufactures an integral quantity and
    thereby skips the broker eligibility check.
    """
    source = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "execution_kernel" / "validate.py"
    ).read_text(encoding="utf-8")
    branch = source.split("if not policy.whole_shares_only:")[1].split("recent_intents")[0]
    assert "except (ValueError, TypeError, ArithmeticError)" in branch
    assert "except Exception" not in branch
    assert 'decimal_factory("0")' not in branch


# --- SET1CR-001: the Discrete Selling surface ------------------------------


_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline(monkeypatch):
    import streamlit as st

    st.cache_data.clear()
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})
    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def _selling_page(monkeypatch, positions):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import assistant.sample_portfolio as sample_portfolio
    import scripts.personal_assistant_ui as ui

    monkeypatch.setattr(sample_portfolio, "SAMPLE_POSITIONS", positions)
    monkeypatch.setattr(ui, "SAMPLE_POSITIONS", positions)
    st.cache_data.clear()
    ui._load_base_packet.clear()

    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Discrete Selling"
    app.run()
    return app


def test_a_sub_one_share_holding_is_disclosed_instead_of_vanishing(
    _offline, monkeypatch
):
    """Before SET1CR-001 a 0.5-share holding floored to 0, was filtered out of
    the dropdown, and left NO trace on the page -- the owner's own stock
    simply was not there."""
    app = _selling_page(
        monkeypatch,
        [{"ticker": "NVDA", "shares": "0.5", "entry_price": "90",
          "current_price": "100"}],
    )

    assert not app.exception
    warnings = "\n".join(w.value for w in app.warning)
    assert "NVDA" in warnings, warnings
    assert "0.5" in warnings, warnings
    assert "Whole shares only" in warnings, warnings


def test_a_fractional_remainder_on_a_sellable_holding_is_disclosed(
    _offline, monkeypatch
):
    """10.5 held reports "10 whole share(s)"; the remaining 0.5 must be named
    rather than left for the owner to discover after selling "everything"."""
    app = _selling_page(
        monkeypatch,
        [{"ticker": "NVDA", "shares": "10.5", "entry_price": "90",
          "current_price": "100"}],
    )

    assert not app.exception
    captions = "\n".join(c.value for c in app.caption)
    assert "0.5 share(s) are held but cannot be sold" in captions, captions


def test_a_clean_whole_holding_gets_no_spurious_warning(_offline, monkeypatch):
    """The disclosure must not fire for an ordinary whole-share holding."""
    app = _selling_page(
        monkeypatch,
        [{"ticker": "NVDA", "shares": "10", "entry_price": "90",
          "current_price": "100"}],
    )

    assert not app.exception
    text = "\n".join(w.value for w in app.warning) + "\n".join(
        c.value for c in app.caption
    )
    assert "cannot be sold while" not in text
