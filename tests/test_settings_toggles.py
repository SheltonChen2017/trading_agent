"""Two owner-configurable safety settings (owner request 2026-08-14).

* `whole_shares_only` — a NEW policy field, default True, which keeps the
  project's whole-share-only ordering. Turning it off permits fractional
  quantities through the complete proposal-to-broker path.
* the existing `min_cash_reserve_pct` — already expressible as 0, which the
  Settings toggle writes. No second field is added, because one rule with
  two sources of truth is one refactor away from disagreeing.

The dangerous directions:

* a fractional quantity slipping through while the policy still says whole
  shares only, or a call site that forgets the flag defaulting to permissive;
* binary floats re-entering an order quantity under cover of "fractional is
  allowed now" — the SELREV-001/002 defects were exactly that; and
* a zero cash reserve being mistaken for "no cash checks at all", when the
  solvency floor must still hold.
"""
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.policy import TradingPolicy, compute_policy_fingerprint
from risk.execution_gate import is_valid_order_quantity, is_valid_share_quantity


def _policy(**overrides):
    base = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.10,
        max_order_value=50_000.0,
    )
    base.update(overrides)
    return TradingPolicy(**base)


# --- the new policy field --------------------------------------------------


def test_whole_shares_only_defaults_to_true():
    """The safe default must not depend on the policy file saying so."""
    assert _policy().whole_shares_only is True
    assert TradingPolicy(version="v", name="n").whole_shares_only is True


def test_turning_it_off_is_a_material_policy_change():
    """It belongs in the fingerprint: evidence gathered under fractional
    ordering must never silently pool with evidence gathered without it."""
    strict = compute_policy_fingerprint(_policy(whole_shares_only=True))
    loose = compute_policy_fingerprint(_policy(whole_shares_only=False))
    assert strict != loose


def test_a_policy_with_the_flag_still_validates():
    _policy(whole_shares_only=False).validate()
    _policy(whole_shares_only=True).validate()


# --- the quantity authority ------------------------------------------------


def test_the_default_is_strict_when_the_flag_is_not_passed():
    """A call site that forgets to thread the policy through must refuse,
    not admit a fractional order."""
    assert is_valid_order_quantity(Decimal("0.5")) is False
    assert is_valid_order_quantity(3) is True


def test_strict_mode_matches_the_original_authority_exactly():
    for value in (3, 1, 0, -1, 2.0, 0.5, True, False, "3", None, float("nan")):
        assert is_valid_order_quantity(value, whole_shares_only=True) == (
            is_valid_share_quantity(value)
        ), value


@pytest.mark.parametrize("value", [Decimal("0.5"), Decimal("1.25"), "0.001", 3])
def test_fractional_mode_accepts_exact_positive_quantities(value):
    assert is_valid_order_quantity(value, whole_shares_only=False) is True


@pytest.mark.parametrize(
    "value", [Decimal("0"), Decimal("-1"), "0", "-0.5", "nan", "inf", "abc", None, True, False]
)
def test_fractional_mode_still_refuses_everything_unusable(value):
    assert is_valid_order_quantity(value, whole_shares_only=False) is False


@pytest.mark.parametrize("value", [0.5, 1.5, 2.0, 0.1])
def test_float_stays_rejected_even_in_fractional_mode(value):
    """Permitting fractions is not a licence to reintroduce binary floats
    into an order quantity. 0.1 + 0.2 is not 0.3, and the 2026-08-13 review
    found that class of defect twice in one day. Fractional callers must
    present an exact Decimal or its string form."""
    assert is_valid_order_quantity(value, whole_shares_only=False) is False


def test_fractional_quantity_is_limited_to_alpacas_nine_decimal_places():
    assert is_valid_order_quantity("0.123456789", whole_shares_only=False)
    assert not is_valid_order_quantity("0.1234567891", whole_shares_only=False)


def test_fractional_quantity_precision_is_independent_of_ambient_context():
    from risk.execution_gate import canonical_order_quantity

    with localcontext() as context:
        context.prec = 3
        assert not is_valid_order_quantity(
            "0.1234567891", whole_shares_only=False
        )
        # Trailing zeroes are representation, not material decimal places.
        assert canonical_order_quantity(
            "0.1234567890000", whole_shares_only=False
        ) == "0.123456789"
        assert canonical_order_quantity(
            "1.0000000000", whole_shares_only=False
        ) == 1


def test_the_real_gate_obeys_the_policy_granularity_without_weakening_money_checks():
    from assistant.context_builder import build_portfolio_snapshot
    from risk.execution_gate import TradeIntent, validate_trade_intent

    snapshot = build_portfolio_snapshot([], cash=1000.0)
    intent = TradeIntent(ticker="NVDA", side="buy", shares="0.5")
    strict = validate_trade_intent(
        intent,
        snapshot,
        reference_price="100",
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
    )
    fractional = validate_trade_intent(
        intent,
        snapshot,
        reference_price="100",
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
        whole_shares_only=False,
    )
    assert not strict.approved
    assert fractional.approved


def test_fractional_sell_still_cannot_exceed_the_exact_holding():
    from assistant.context_builder import build_portfolio_snapshot
    from risk.execution_gate import TradeIntent, validate_trade_intent

    snapshot = build_portfolio_snapshot(
        [{"ticker": "NVDA", "shares": "1.25", "entry_price": "90", "current_price": "100"}],
        cash=100.0,
    )
    result = validate_trade_intent(
        TradeIntent(ticker="NVDA", side="sell", shares="1.250000001"),
        snapshot,
        reference_price="100",
        whole_shares_only=False,
    )
    assert not result.approved
    assert any("exceeds" in violation for violation in result.violations)


def test_fractional_quantity_survives_durable_intent_rehydration_as_exact_text():
    from assistant.execution_kernel.intents import _intent_from_dict

    intent = _intent_from_dict(
        {"ticker": "NVDA", "side": "buy", "shares": "0.123456789"}
    )
    assert intent.shares == "0.123456789"
    with pytest.raises(ValueError):
        _intent_from_dict(
            {"ticker": "NVDA", "side": "buy", "shares": "0.1234567891"}
        )


def test_reconciliation_does_not_tolerate_a_one_nanoshare_identity_mismatch():
    from assistant.execution_kernel.outcomes import _order_matches_intent
    from execution.broker_contract import BrokerAccountIdentity
    from risk.execution_gate import TradeIntent

    account = BrokerAccountIdentity("paper-account-1", "paper")
    proposal = {
        "proposal_id": "proposal-nanoshare",
        "idempotency_key": "proposal-nanoshare:attempt-1",
        "broker_execution_context": {
            "account_id": account.account_id,
            "account_mode": account.account_mode,
            "snapshot_id": "a" * 64,
            "policy_fingerprint": "b" * 64,
        },
    }
    order = {
        "order_id": "order-nanoshare",
        "client_order_id": proposal["idempotency_key"],
        "ticker": "NVDA",
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "side": "buy",
        "shares": 0.5,
        "shares_decimal": "0.500000001",
        "notional": None,
        "notional_decimal": None,
        "type": "market",
        "limit_price": None,
        "limit_price_decimal": None,
        "time_in_force": "day",
        "status": "new",
        "filled_qty": 0.0,
        "filled_qty_decimal": "0",
        "filled_avg_price": None,
        "filled_avg_price_decimal": None,
        "replaces": None,
        "replaced_by": None,
        "replaced_at": None,
        "submitted_at": "2026-08-26T15:30:00+00:00",
        "updated_at": "2026-08-26T15:30:01+00:00",
        "filled_at": None,
        "canceled_at": None,
        "expired_at": None,
        "failed_at": None,
    }
    matches, detail = _order_matches_intent(
        order,
        TradeIntent(ticker="NVDA", side="buy", shares="0.5"),
        proposal=proposal,
        observed_account=account,
    )
    assert not matches
    assert "numeric_companion_mismatch" in detail
    assert "shares_decimal=0.500000001 disagrees with shares=0.5" in detail


# --- the cash reserve ------------------------------------------------------


def test_a_zero_cash_reserve_is_a_valid_policy():
    """The toggle writes 0 rather than adding a second boolean; that is only
    honest if 0 is genuinely expressible."""
    _policy(min_cash_reserve_pct=0.0).validate()
    assert _policy(min_cash_reserve_pct=0.0).min_cash_reserve_pct == 0.0


def test_zero_reserve_still_changes_the_fingerprint():
    assert compute_policy_fingerprint(
        _policy(min_cash_reserve_pct=0.10)
    ) != compute_policy_fingerprint(_policy(min_cash_reserve_pct=0.0))


def test_a_zero_reserve_does_not_disable_the_solvency_floor():
    """Turning the reserve off removes the BUFFER, not the check that an
    order cannot take cash negative. The owner's stated reason for disabling
    it (Alpaca holds a small slice of their assets) depends on that
    distinction holding.
    """
    from datetime import datetime, timezone

    from assistant.context_builder import build_portfolio_snapshot
    from risk.execution_gate import TradeIntent, validate_trade_intent

    snapshot = build_portfolio_snapshot([], cash=100.0)
    now = datetime(2026, 8, 14, 14, 0, tzinfo=timezone.utc)
    # $500 of stock against $100 of cash, with NO reserve required.
    result = validate_trade_intent(
        TradeIntent(ticker="NVDA", side="buy", shares=5, order_type="market"),
        # `allow_new_positions` is not a gate parameter -- the execution
        # kernel checks it one layer up. min_cash_reserve_pct is a FRACTION
        # here (see the gate's FCS-008 unit warning).
        snapshot, reference_price=100.0, price_timestamp=now, now=now,
        max_order_value=50_000.0, min_cash_reserve_pct=0.0,
    )
    codes = " ".join(str(getattr(v, "code", v)) for v in result.violations)
    assert not result.approved, "spending more cash than exists must still refuse"
    assert "CASH" in codes.upper() or "cash" in codes.lower(), codes


# --- the Settings & Features surface --------------------------------------


def _settings_app():
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    app = AppTest.from_file(str(app_path), default_timeout=180)
    app.session_state["nav_page"] = "Settings & Features"
    app.run()
    return app


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


def test_both_toggles_appear_in_settings(_offline):
    app = _settings_app()
    assert not app.exception
    labels = [c.label for c in app.toggle]
    assert "Whole shares only" in labels, labels
    assert "Enforce a minimum cash reserve" in labels, labels


def test_the_toggles_sit_behind_the_typed_policy_confirmation(_offline):
    """These are authoritative policy, not preferences. A change must not be
    appliable without the same typed phrase the existing flags require."""
    app = _settings_app()
    box = next(c for c in app.toggle if c.label == "Whole shares only")
    box.set_value(False).run()

    assert not app.exception
    warnings = "\n".join(w.value for w in app.warning)
    assert "NEW policy fingerprint" in warnings
    assert any(
        i.label.startswith('Type exactly "UPDATE POLICY"') for i in app.text_input
    ), [i.label for i in app.text_input]
    apply_buttons = [b for b in app.button if b.label == "Apply policy change"]
    assert apply_buttons and apply_buttons[0].disabled, (
        "the apply button must stay disabled until the phrase is typed"
    )


def test_disabling_the_reserve_says_solvency_is_still_enforced(_offline):
    """The owner's reason for disabling it depends on that distinction."""
    app = _settings_app()
    box = next(c for c in app.toggle if c.label == "Enforce a minimum cash reserve")
    box.set_value(False).run()

    assert not app.exception
    captions = "\n".join(c.value for c in app.caption)
    assert "cannot take your cash balance negative" in captions
    # And the percentage input disappears rather than sitting there inert.
    assert not [
        n for n in app.number_input if n.label.startswith("Minimum cash reserve")
    ]
